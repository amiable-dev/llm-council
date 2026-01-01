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


def _build_verification_prompt(
    snapshot_id: str,
    target_paths: Optional[List[str]] = None,
    rubric_focus: Optional[str] = None,
) -> str:
    """
    Build verification prompt for council deliberation.

    Creates a structured prompt that asks the council to review
    code/documentation at the given snapshot, including actual file contents.

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

    # Fetch actual file contents
    file_contents = _fetch_files_for_verification(snapshot_id, target_paths)

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

        # Build verification prompt for council
        verification_query = _build_verification_prompt(
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
