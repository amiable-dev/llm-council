"""
Verification API endpoint per ADR-034.

Provides POST /v1/council/verify for structured work verification
using LLM Council multi-model deliberation.

Exit codes:
- 0: PASS - Approved with confidence >= threshold
- 1: FAIL - Rejected
- 2: UNCLEAR - Confidence below threshold, requires human review
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from llm_council.council import (
    calculate_aggregate_rankings,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from llm_council.verdict import VerdictType as CouncilVerdictType
from llm_council.verification.context import (
    InvalidSnapshotError,
    VerificationContextManager,
    validate_snapshot_id,
)
from llm_council.verification.transcript import (
    TranscriptStore,
    create_transcript_store,
)
from llm_council.verification.verdict_extractor import (
    build_verification_result,
    extract_rubric_scores_from_rankings,
    extract_verdict_from_synthesis,
    calculate_confidence_from_agreement,
)

# Router for verification endpoints
router = APIRouter(tags=["verification"])


# Git SHA pattern for validation
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


class VerifyRequest(BaseModel):
    """Request body for POST /v1/council/verify."""

    snapshot_id: str = Field(
        ...,
        description="Git commit SHA for snapshot pinning (7-40 hex chars)",
        min_length=7,
        max_length=40,
    )
    target_paths: Optional[List[str]] = Field(
        default=None,
        description="Paths to verify (defaults to entire snapshot)",
    )
    rubric_focus: Optional[str] = Field(
        default=None,
        description="Focus area: Security, Performance, Accessibility, etc.",
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for PASS verdict",
    )

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id_format(cls, v: str) -> str:
        """Validate snapshot_id is valid git SHA."""
        if not GIT_SHA_PATTERN.match(v):
            raise ValueError("snapshot_id must be valid git SHA (7-40 hexadecimal characters)")
        return v


class RubricScoresResponse(BaseModel):
    """Rubric scores in response."""

    accuracy: Optional[float] = Field(default=None, ge=0, le=10)
    relevance: Optional[float] = Field(default=None, ge=0, le=10)
    completeness: Optional[float] = Field(default=None, ge=0, le=10)
    conciseness: Optional[float] = Field(default=None, ge=0, le=10)
    clarity: Optional[float] = Field(default=None, ge=0, le=10)


class BlockingIssueResponse(BaseModel):
    """Blocking issue in response."""

    severity: str = Field(..., description="critical, major, or minor")
    description: str = Field(..., description="Issue description")
    location: Optional[str] = Field(default=None, description="File/line location")


class VerifyResponse(BaseModel):
    """Response body for POST /v1/council/verify."""

    verification_id: str = Field(..., description="Unique verification ID")
    verdict: str = Field(..., description="pass, fail, or unclear")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    exit_code: int = Field(..., description="0=PASS, 1=FAIL, 2=UNCLEAR")
    rubric_scores: RubricScoresResponse = Field(
        default_factory=RubricScoresResponse,
        description="Multi-dimensional rubric scores",
    )
    blocking_issues: List[BlockingIssueResponse] = Field(
        default_factory=list,
        description="Issues that caused FAIL verdict",
    )
    rationale: str = Field(..., description="Chairman synthesis explanation")
    transcript_location: str = Field(..., description="Path to verification transcript")
    partial: bool = Field(
        default=False,
        description="True if result is partial (timeout/error)",
    )


def _verdict_to_exit_code(verdict: str) -> int:
    """Convert verdict to exit code."""
    if verdict == "pass":
        return 0
    elif verdict == "fail":
        return 1
    else:  # unclear
        return 2


# Maximum characters per file to include in prompt
MAX_FILE_CHARS = 15000
# Maximum total characters for all files
MAX_TOTAL_CHARS = 50000


def _fetch_file_at_commit(snapshot_id: str, file_path: str) -> Tuple[str, bool]:
    """
    Fetch file contents from git at a specific commit.

    Args:
        snapshot_id: Git commit SHA
        file_path: Path to file relative to repo root

    Returns:
        Tuple of (content, was_truncated)
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{snapshot_id}:{file_path}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return f"[Error: Could not read {file_path} at {snapshot_id}]", False

        content = result.stdout
        truncated = False

        if len(content) > MAX_FILE_CHARS:
            content = (
                content[:MAX_FILE_CHARS] + f"\n\n... [truncated, {len(result.stdout)} chars total]"
            )
            truncated = True

        return content, truncated

    except subprocess.TimeoutExpired:
        return f"[Error: Timeout reading {file_path}]", False
    except Exception as e:
        return f"[Error: {e}]", False


# Async timeout for subprocess operations (seconds)
ASYNC_SUBPROCESS_TIMEOUT = 10

# Maximum concurrent git subprocess operations to prevent DoS
MAX_CONCURRENT_GIT_OPS = 10

# Cached git root to avoid repeated subprocess calls
_cached_git_root: Optional[str] = None
_git_root_lock = asyncio.Lock()


async def _get_git_root_async() -> Optional[str]:
    """
    Get the git repository root directory (async, cached).

    Uses async subprocess to avoid blocking the event loop.
    Result is cached to avoid repeated calls.

    Returns:
        Git repository root path or None if not in a git repo.
    """
    global _cached_git_root

    # Return cached value if available
    if _cached_git_root is not None:
        return _cached_git_root

    # Use lock to prevent multiple concurrent lookups
    async with _git_root_lock:
        # Double-check after acquiring lock
        if _cached_git_root is not None:
            return _cached_git_root

        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--show-toplevel",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0:
                _cached_git_root = stdout.decode("utf-8").strip()
                return _cached_git_root
        except Exception:
            pass

    return None


def _validate_file_path(file_path: str) -> bool:
    """
    Validate file path to prevent path traversal attacks.

    Args:
        file_path: Path to validate

    Returns:
        True if path is safe, False otherwise.
    """
    # Reject absolute paths
    if file_path.startswith("/") or file_path.startswith("\\"):
        return False

    # Reject path traversal attempts
    if ".." in file_path:
        return False

    # Reject null bytes (path injection)
    if "\x00" in file_path:
        return False

    return True


# Thread-safe semaphore creation for async contexts
_semaphore_lock = asyncio.Lock()
_git_semaphore: Optional[asyncio.Semaphore] = None


async def _get_git_semaphore() -> asyncio.Semaphore:
    """
    Get or create the git semaphore for limiting concurrency.

    Thread-safe initialization using async lock.
    """
    global _git_semaphore

    if _git_semaphore is not None:
        return _git_semaphore

    async with _semaphore_lock:
        if _git_semaphore is None:
            _git_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GIT_OPS)
        return _git_semaphore


async def _fetch_file_at_commit_async(snapshot_id: str, file_path: str) -> Tuple[str, bool]:
    """
    Fetch file contents from git at a specific commit (async version).

    Uses asyncio.create_subprocess_exec to avoid blocking the event loop.
    Uses semaphore to limit concurrent git operations (DoS prevention).
    Uses streaming read to avoid buffering entire large files (DoS prevention).

    Args:
        snapshot_id: Git commit SHA
        file_path: Path to file relative to repo root

    Returns:
        Tuple of (content, was_truncated)
    """
    # Validate file path to prevent path traversal
    if not _validate_file_path(file_path):
        return f"[Error: Invalid file path: {file_path}]", False

    # Get git root for reliable CWD (avoids CWD dependency)
    git_root = await _get_git_root_async()

    # Acquire semaphore to limit concurrent git operations
    semaphore = await _get_git_semaphore()
    async with semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "show",
                f"{snapshot_id}:{file_path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=git_root,  # Use git root to avoid CWD dependency
            )

            # Stream read to avoid buffering entire file (DoS prevention)
            chunks: List[bytes] = []
            bytes_read = 0
            truncated = False

            try:
                assert proc.stdout is not None  # Type narrowing for mypy

                async def read_with_limit() -> None:
                    """Read chunks until limit or EOF."""
                    nonlocal bytes_read, truncated
                    while bytes_read < MAX_FILE_CHARS:
                        # Read in chunks of 8KB
                        chunk = await proc.stdout.read(8192)  # type: ignore[union-attr]
                        if not chunk:
                            break
                        chunks.append(chunk)
                        bytes_read += len(chunk)

                    # Check if there's more data (truncation needed)
                    if bytes_read >= MAX_FILE_CHARS:
                        extra = await proc.stdout.read(1)  # type: ignore[union-attr]
                        if extra:
                            truncated = True
                            # Kill process to avoid wasting resources on remaining data
                            proc.kill()

                await asyncio.wait_for(read_with_limit(), timeout=ASYNC_SUBPROCESS_TIMEOUT)

            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"[Error: Timeout reading {file_path}]", False

            # Wait for process to complete (already killed if truncated)
            await proc.wait()

            if proc.returncode != 0 and not truncated:
                # Only check return code if we didn't kill it for truncation
                # Try to read stderr for error message
                stderr_data = b""
                if proc.stderr:
                    try:
                        stderr_data = await asyncio.wait_for(proc.stderr.read(1024), timeout=1)
                    except Exception:
                        pass
                return f"[Error: Could not read {file_path} at {snapshot_id}]", False

            # Combine chunks and decode
            content_bytes = b"".join(chunks)
            content = content_bytes.decode("utf-8", errors="replace")

            if truncated or len(content) > MAX_FILE_CHARS:
                content = (
                    content[:MAX_FILE_CHARS]
                    + f"\n\n... [truncated, original file larger than {MAX_FILE_CHARS} chars]"
                )
                truncated = True

            return content, truncated

        except Exception as e:
            return f"[Error: {e}]", False


async def _fetch_files_for_verification_async(
    snapshot_id: str,
    target_paths: Optional[List[str]] = None,
) -> str:
    """
    Fetch file contents for verification prompt (async version).

    Uses async subprocess to avoid blocking the event loop.
    Fetches multiple files concurrently for better performance.

    Args:
        snapshot_id: Git commit SHA
        target_paths: Optional list of specific paths

    Returns:
        Formatted string with file contents
    """
    files_to_fetch = list(target_paths) if target_paths else []
    git_root = await _get_git_root_async()

    # If no target paths, get files changed in this commit
    if not files_to_fetch:
        try:
            semaphore = await _get_git_semaphore()
            async with semaphore:
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    snapshot_id,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=git_root,  # Use git root to avoid CWD dependency
                )

                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=ASYNC_SUBPROCESS_TIMEOUT
                )

                if proc.returncode == 0:
                    files_to_fetch = [f for f in stdout.decode("utf-8").strip().split("\n") if f]
        except Exception:
            pass

    if not files_to_fetch:
        return "[No files specified and could not determine changed files]"

    # Fetch files with early termination when limit is reached
    # This avoids wasting resources on files we won't include
    sections: List[str] = []
    total_chars = 0

    # Limit concurrent fetches to avoid DoS on large commits
    # Fetch in batches of up to 5 files at a time
    BATCH_SIZE = 5
    files_fetched = 0

    for i in range(0, len(files_to_fetch), BATCH_SIZE):
        # Check limit before fetching next batch
        if total_chars >= MAX_TOTAL_CHARS:
            sections.append(
                f"\n... [remaining files omitted, {MAX_TOTAL_CHARS} char limit reached]"
            )
            break

        batch = files_to_fetch[i : i + BATCH_SIZE]
        results = await asyncio.gather(
            *[_fetch_file_at_commit_async(snapshot_id, fp) for fp in batch]
        )

        for file_path, (content, truncated) in zip(batch, results):
            if total_chars >= MAX_TOTAL_CHARS:
                sections.append(
                    f"\n... [remaining files omitted, {MAX_TOTAL_CHARS} char limit reached]"
                )
                break

            total_chars += len(content)
            files_fetched += 1
            section = f"### {file_path}\n```\n{content}\n```"
            sections.append(section)

    return "\n\n".join(sections)


def _fetch_files_for_verification(
    snapshot_id: str,
    target_paths: Optional[List[str]] = None,
) -> str:
    """
    Fetch file contents for verification prompt.

    If target_paths specified, fetches those files.
    Otherwise, fetches changed files in the commit.

    Args:
        snapshot_id: Git commit SHA
        target_paths: Optional list of specific paths

    Returns:
        Formatted string with file contents
    """
    files_to_fetch = target_paths or []

    # If no target paths, get files changed in this commit
    if not files_to_fetch:
        try:
            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", snapshot_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                files_to_fetch = [f for f in result.stdout.strip().split("\n") if f]
        except Exception:
            pass

    if not files_to_fetch:
        return "[No files specified and could not determine changed files]"

    sections = []
    total_chars = 0

    for file_path in files_to_fetch:
        if total_chars >= MAX_TOTAL_CHARS:
            sections.append(
                f"\n... [remaining files omitted, {MAX_TOTAL_CHARS} char limit reached]"
            )
            break

        content, truncated = _fetch_file_at_commit(snapshot_id, file_path)
        total_chars += len(content)

        section = f"### {file_path}\n```\n{content}\n```"
        sections.append(section)

    return "\n\n".join(sections)


async def _build_verification_prompt(
    snapshot_id: str,
    target_paths: Optional[List[str]] = None,
    rubric_focus: Optional[str] = None,
) -> str:
    """
    Build verification prompt for council deliberation.

    Creates a structured prompt that asks the council to review
    code/documentation at the given snapshot, including actual file contents.

    Uses async file fetching to avoid blocking the event loop.

    Args:
        snapshot_id: Git commit SHA for the code version
        target_paths: Optional list of paths to focus on
        rubric_focus: Optional focus area (Security, Performance, etc.)

    Returns:
        Formatted verification prompt for council
    """
    focus_section = ""
    if rubric_focus:
        focus_section = f"\n\n**Focus Area**: {rubric_focus}\nPay particular attention to {rubric_focus.lower()}-related concerns."

    # Fetch actual file contents (async to avoid blocking event loop)
    file_contents = await _fetch_files_for_verification_async(snapshot_id, target_paths)

    prompt = f"""You are reviewing code at commit `{snapshot_id}`.{focus_section}

## Code to Review

{file_contents}

## Instructions

Please provide a thorough review with the following structure:

1. **Summary**: Brief overview of what the code does
2. **Quality Assessment**: Evaluate code quality, readability, and maintainability
3. **Potential Issues**: Identify any bugs, security vulnerabilities, or performance concerns
4. **Recommendations**: Suggest improvements if any

At the end of your review, provide a clear verdict:
- **APPROVED** if the code is ready for production
- **REJECTED** if there are critical issues that must be fixed
- **NEEDS REVIEW** if you're uncertain and recommend human review

Be specific and cite file paths and line numbers when identifying issues."""

    return prompt


async def run_verification(
    request: VerifyRequest,
    store: TranscriptStore,
) -> Dict[str, Any]:
    """
    Run verification using LLM Council.

    This is the core verification logic that:
    1. Creates isolated context
    2. Runs council deliberation
    3. Persists transcript
    4. Returns structured result

    Args:
        request: Verification request
        store: Transcript store for persistence

    Returns:
        Verification result dictionary
    """
    verification_id = str(uuid.uuid4())[:8]

    # Create isolated context for this verification
    with VerificationContextManager(
        snapshot_id=request.snapshot_id,
        rubric_focus=request.rubric_focus,
    ) as ctx:
        # Create transcript directory
        transcript_dir = store.create_verification_directory(verification_id)

        # Persist request
        store.write_stage(
            verification_id,
            "request",
            {
                "snapshot_id": request.snapshot_id,
                "target_paths": request.target_paths,
                "rubric_focus": request.rubric_focus,
                "confidence_threshold": request.confidence_threshold,
                "context_id": ctx.context_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Build verification prompt for council (async to avoid blocking)
        verification_query = await _build_verification_prompt(
            snapshot_id=request.snapshot_id,
            target_paths=request.target_paths,
            rubric_focus=request.rubric_focus,
        )

        # Stage 1: Collect individual model responses
        stage1_results, stage1_usage = await stage1_collect_responses(verification_query)

        # Persist Stage 1
        store.write_stage(
            verification_id,
            "stage1",
            {
                "responses": stage1_results,
                "usage": stage1_usage,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Stage 2: Peer ranking with rubric evaluation
        stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(
            verification_query, stage1_results
        )

        # Persist Stage 2
        store.write_stage(
            verification_id,
            "stage2",
            {
                "rankings": stage2_results,
                "label_to_model": label_to_model,
                "usage": stage2_usage,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Calculate aggregate rankings
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

        # Stage 3: Chairman synthesis with verdict
        stage3_result, stage3_usage, verdict_result = await stage3_synthesize_final(
            verification_query,
            stage1_results,
            stage2_results,
            aggregate_rankings=aggregate_rankings,
            verdict_type=CouncilVerdictType.BINARY,
        )

        # Persist Stage 3
        store.write_stage(
            verification_id,
            "stage3",
            {
                "synthesis": stage3_result,
                "aggregate_rankings": aggregate_rankings,
                "usage": stage3_usage,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Extract verdict and scores from council output
        verification_output = build_verification_result(
            stage1_results,
            stage2_results,
            stage3_result,
            confidence_threshold=request.confidence_threshold,
        )

        verdict = verification_output["verdict"]
        confidence = verification_output["confidence"]
        exit_code = _verdict_to_exit_code(verdict)

        result = {
            "verification_id": verification_id,
            "verdict": verdict,
            "confidence": confidence,
            "exit_code": exit_code,
            "rubric_scores": verification_output["rubric_scores"],
            "blocking_issues": verification_output["blocking_issues"],
            "rationale": verification_output["rationale"],
            "transcript_location": str(transcript_dir),
            "partial": False,
        }

        # Persist result
        store.write_stage(verification_id, "result", result)

        return result


@router.post("/verify", response_model=VerifyResponse)
async def verify_endpoint(request: VerifyRequest) -> VerifyResponse:
    """
    Verify code, documents, or implementation using LLM Council.

    This endpoint provides structured work verification with:
    - Multi-model consensus via LLM Council deliberation
    - Context isolation per verification (no session bleed)
    - Transcript persistence for audit trail
    - Exit codes for CI/CD integration

    Exit Codes:
    - 0: PASS - Approved with confidence >= threshold
    - 1: FAIL - Rejected with blocking issues
    - 2: UNCLEAR - Confidence below threshold, requires human review

    Args:
        request: VerificationRequest with snapshot_id and optional parameters

    Returns:
        VerificationResult with verdict, confidence, and transcript location
    """
    try:
        # Validate snapshot ID
        validate_snapshot_id(request.snapshot_id)
    except InvalidSnapshotError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        # Create transcript store
        store = create_transcript_store()

        # Run verification
        result = await run_verification(request, store)

        return VerifyResponse(**result)

    except Exception as e:
        # Handle errors gracefully
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "type": type(e).__name__},
        )
