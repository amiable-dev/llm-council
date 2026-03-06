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
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from llm_council.council import (
    calculate_aggregate_rankings,
    stage1_collect_responses,
    stage1_collect_responses_with_status,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from llm_council.tier_contract import create_tier_contract, get_tier_timeout
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
    tier: str = Field(
        default="high",
        description="Confidence tier for model selection: quick, balanced, high, reasoning",
        pattern="^(quick|balanced|high|reasoning)$",
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
    # ADR-034 v2.6: Directory expansion metadata (Issue #311)
    expanded_paths: Optional[List[str]] = Field(
        default=None,
        description="Files included after directory expansion",
    )
    paths_truncated: Optional[bool] = Field(
        default=None,
        description="True if MAX_FILES_EXPANSION limit was reached",
    )
    expansion_warnings: Optional[List[str]] = Field(
        default=None,
        description="Warnings from directory expansion (skipped files, etc.)",
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

# =============================================================================
# ADR-034 v2.6: Directory Expansion Constants
# =============================================================================

# Maximum files to include after directory expansion (Issue #309)
MAX_FILES_EXPANSION = 100

# Text file extensions to include (whitelist approach per council decision)
# 80+ extensions covering common source code, config, and documentation files
TEXT_EXTENSIONS: Set[str] = frozenset(
    {
        # Source code
        ".py",
        ".pyi",
        ".pyx",
        ".pxd",  # Python
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",  # JavaScript
        ".ts",
        ".tsx",
        ".mts",
        ".cts",  # TypeScript
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".groovy",  # JVM
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".hh",
        ".cxx",
        ".hxx",  # C/C++
        ".cs",
        ".fs",
        ".fsx",  # .NET
        ".go",  # Go
        ".rs",  # Rust
        ".rb",
        ".rake",
        ".gemspec",  # Ruby
        ".php",
        ".phtml",  # PHP
        ".swift",  # Swift
        ".m",
        ".mm",  # Objective-C
        ".lua",  # Lua
        ".pl",
        ".pm",
        ".t",  # Perl
        ".r",
        ".R",  # R
        ".jl",  # Julia
        ".ex",
        ".exs",  # Elixir
        ".erl",
        ".hrl",  # Erlang
        ".clj",
        ".cljs",
        ".cljc",
        ".edn",  # Clojure
        ".hs",
        ".lhs",  # Haskell
        ".elm",  # Elm
        ".ml",
        ".mli",  # OCaml
        ".nim",  # Nim
        ".v",
        ".sv",
        ".svh",  # Verilog/SystemVerilog
        ".vhd",
        ".vhdl",  # VHDL
        ".asm",
        ".s",  # Assembly
        ".sh",
        ".bash",
        ".zsh",
        ".fish",  # Shell
        ".ps1",
        ".psm1",
        ".psd1",  # PowerShell
        ".bat",
        ".cmd",  # Windows batch
        # Web
        ".html",
        ".htm",
        ".xhtml",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".styl",
        ".vue",
        ".svelte",
        # Data/Config
        ".json",
        ".jsonl",
        ".json5",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".xsd",
        ".xsl",
        ".xslt",
        ".svg",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".env.example",
        ".env.sample",
        ".properties",
        ".plist",
        # Documentation
        ".md",
        ".markdown",
        ".mdx",
        ".rst",
        ".txt",
        ".text",
        ".adoc",
        ".asciidoc",
        ".tex",
        ".latex",
        ".org",
        # Build/CI
        ".makefile",
        ".mk",
        ".cmake",
        ".gradle",
        ".dockerfile",
        # GraphQL/API
        ".graphql",
        ".gql",
        ".proto",
        ".thrift",
        ".avsc",  # Avro schema
        # SQL
        ".sql",
        # Misc
        ".vim",
        ".vimrc",
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        ".editorconfig",
        ".eslintrc",
        ".prettierrc",
        ".stylelintrc",
        ".babelrc",
        ".npmrc",
        ".yarnrc",
        ".dockerignore",
    }
)

# Garbage filenames to exclude (lock files, generated files)
GARBAGE_FILENAMES: Set[str] = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "composer.lock",
        "Gemfile.lock",
        "Cargo.lock",
        "go.sum",
        "flake.lock",
        "bun.lockb",
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        "__pycache__",
        "node_modules",
        ".git",
    }
)

# =============================================================================
# End ADR-034 v2.6 Constants
# =============================================================================


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


# =============================================================================
# ADR-034 v2.6: Directory Expansion Helpers (Issues #307, #308, #309)
# =============================================================================


async def _get_git_object_type(snapshot_id: str, path: str) -> Optional[str]:
    """
    Get git object type for a path at a specific commit.

    Uses `git cat-file -t` to determine if path is a blob (file),
    tree (directory), or doesn't exist.

    Issue #307: Foundation helper for directory expansion.

    Args:
        snapshot_id: Git commit SHA
        path: Path relative to repo root

    Returns:
        "blob" for files, "tree" for directories, None for errors/not found.
    """
    git_root = await _get_git_root_async()
    semaphore = await _get_git_semaphore()

    async with semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "cat-file",
                "-t",
                f"{snapshot_id}:{path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=git_root,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=ASYNC_SUBPROCESS_TIMEOUT)
            if proc.returncode == 0:
                return stdout.decode("utf-8").strip()
        except Exception:
            pass

    return None


async def _git_ls_tree_z_name_only(snapshot_id: str, tree_path: str) -> List[str]:
    """
    List all files in a git tree recursively using NUL-delimited output.

    Uses `git ls-tree -rz --name-only` for safe parsing of filenames
    containing spaces, newlines, or other special characters.

    Skips symlinks (mode 120000) and submodules (mode 160000).

    Issue #308: Foundation helper for directory expansion.

    Args:
        snapshot_id: Git commit SHA
        tree_path: Path to directory relative to repo root

    Returns:
        List of file paths (with tree_path prepended).
    """
    git_root = await _get_git_root_async()
    semaphore = await _get_git_semaphore()

    async with semaphore:
        try:
            # Use ls-tree with -z for NUL delimiters and --name-status to get modes
            # We need modes to skip symlinks and submodules
            proc = await asyncio.create_subprocess_exec(
                "git",
                "ls-tree",
                "-rz",  # Recursive, NUL-delimited
                f"{snapshot_id}:{tree_path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=git_root,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=ASYNC_SUBPROCESS_TIMEOUT)

            if proc.returncode != 0:
                return []

            # Parse NUL-delimited output
            # Format: "mode type hash\tpath\0mode type hash\tpath\0..."
            output = stdout.decode("utf-8", errors="replace")
            files: List[str] = []

            for entry in output.split("\0"):
                if not entry.strip():
                    continue

                # Split mode/type/hash from path
                parts = entry.split("\t", 1)
                if len(parts) != 2:
                    continue

                metadata, file_path = parts
                mode_parts = metadata.split(" ")
                if len(mode_parts) < 2:
                    continue

                mode = mode_parts[0]
                obj_type = mode_parts[1]

                # Skip symlinks (120000) and submodules (160000)
                if mode in ("120000", "160000"):
                    continue

                # Only include blobs (files)
                if obj_type != "blob":
                    continue

                # Prepend tree path to get full path
                full_path = f"{tree_path}/{file_path}" if tree_path else file_path
                files.append(full_path)

            return files

        except Exception:
            return []


def _is_text_file(file_path: str) -> bool:
    """Check if file has a text extension."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    name = path.name.lower()

    # Check if full name matches (e.g., .gitignore, Makefile)
    if name in TEXT_EXTENSIONS or f".{name}" in TEXT_EXTENSIONS:
        return True

    # Check if extension matches
    if suffix and suffix in TEXT_EXTENSIONS:
        return True

    # Special case: files without extension that are likely text
    if not suffix and name in {"makefile", "dockerfile", "jenkinsfile", "cmakelists"}:
        return True

    return False


def _is_garbage_file(file_path: str) -> bool:
    """Check if file is a garbage file that should be excluded."""
    name = Path(file_path).name
    return name in GARBAGE_FILENAMES


async def _expand_target_paths(
    snapshot_id: str,
    target_paths: List[str],
) -> Tuple[List[str], bool, List[str]]:
    """
    Expand directories in target_paths to their constituent text files.

    Issue #309: Core expansion logic with text filtering.

    Args:
        snapshot_id: Git commit SHA
        target_paths: List of paths (may include directories)

    Returns:
        Tuple of:
        - expanded_files: List of file paths after expansion
        - was_truncated: True if MAX_FILES_EXPANSION was hit
        - warnings: List of warning messages
    """
    expanded_files: List[str] = []
    warnings: List[str] = []
    truncated = False

    for path in target_paths:
        # Normalize path (remove trailing slashes)
        path = path.rstrip("/")

        # Check object type
        obj_type = await _get_git_object_type(snapshot_id, path)

        if obj_type is None:
            warnings.append(f"Path not found or invalid: {path}")
            continue

        if obj_type == "blob":
            # It's a file - check if it passes filters
            if _is_garbage_file(path):
                warnings.append(f"Skipped garbage file: {path}")
                continue
            if not _is_text_file(path):
                warnings.append(f"Skipped non-text file: {path}")
                continue
            expanded_files.append(path)

        elif obj_type == "tree":
            # It's a directory - expand it
            tree_files = await _git_ls_tree_z_name_only(snapshot_id, path)

            for file_path in tree_files:
                # Apply filters
                if _is_garbage_file(file_path):
                    continue
                if not _is_text_file(file_path):
                    continue

                expanded_files.append(file_path)

                # Check if we've hit the limit
                if len(expanded_files) >= MAX_FILES_EXPANSION:
                    truncated = True
                    warnings.append(
                        f"Truncated at {MAX_FILES_EXPANSION} files. "
                        f"Directory '{path}' contains more files than limit."
                    )
                    break

            if truncated:
                break

        else:
            warnings.append(f"Unknown object type '{obj_type}' for path: {path}")

        # Check limit after each path
        if len(expanded_files) >= MAX_FILES_EXPANSION:
            truncated = True
            break

    return expanded_files, truncated, warnings


# =============================================================================
# End ADR-034 v2.6 Directory Expansion Helpers
# =============================================================================


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

    ADR-034 v2.6: Now supports directory expansion via _expand_target_paths().

    Args:
        snapshot_id: Git commit SHA
        target_paths: Optional list of specific paths (files or directories)

    Returns:
        Formatted string with file contents
    """
    content, _ = await _fetch_files_for_verification_async_with_metadata(snapshot_id, target_paths)
    return content


async def _fetch_files_for_verification_async_with_metadata(
    snapshot_id: str,
    target_paths: Optional[List[str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Fetch file contents for verification prompt with expansion metadata.

    ADR-034 v2.6: This is the core implementation that handles directory
    expansion and returns metadata about what was expanded.

    Args:
        snapshot_id: Git commit SHA
        target_paths: Optional list of specific paths (files or directories)

    Returns:
        Tuple of (formatted content string, metadata dict)
        Metadata includes: expanded_paths, paths_truncated, expansion_warnings
    """
    files_to_fetch: List[str] = []
    expansion_metadata: Dict[str, Any] = {
        "expanded_paths": [],
        "paths_truncated": False,
        "expansion_warnings": [],
    }
    git_root = await _get_git_root_async()

    # ADR-034 v2.6: Expand directories in target_paths
    if target_paths:
        files_to_fetch, truncated, warnings = await _expand_target_paths(snapshot_id, target_paths)
        expansion_metadata["expanded_paths"] = files_to_fetch
        expansion_metadata["paths_truncated"] = truncated
        expansion_metadata["expansion_warnings"] = warnings
    else:
        # If no target paths, get files changed in this commit
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
                    expansion_metadata["expanded_paths"] = files_to_fetch
        except Exception:
            pass

    if not files_to_fetch:
        return "[No files specified and could not determine changed files]", expansion_metadata

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

    return "\n\n".join(sections), expansion_metadata


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

        # Get tier-appropriate models and timeouts (Issue #325)
        tier_contract = create_tier_contract(request.tier)
        tier_timeout = get_tier_timeout(request.tier)

        # Stage 1: Collect individual model responses with tier-appropriate models
        stage1_results, stage1_usage, _model_statuses = await stage1_collect_responses_with_status(
            verification_query,
            timeout=tier_timeout["per_model"],
            models=tier_contract.allowed_models,
        )

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
