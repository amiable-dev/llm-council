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
import logging
import re
import time
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

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
from llm_council.performance.integration import persist_session_performance_data

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
        default="balanced",
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
    # ADR-040: Timeout guardrail fields
    timeout_fired: bool = Field(
        default=False,
        description="True if global deadline was exceeded",
    )
    completed_stages: Optional[List[str]] = Field(
        default=None,
        description="Stages completed before timeout (e.g. ['stage1', 'stage2'])",
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
    # ADR-041: Verification telemetry fields
    timing: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Per-stage and total timing in milliseconds",
    )
    input_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Input size metrics (content_chars, tier_max_chars, num_models, num_reviewers, tier)",
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


# =============================================================================
# ADR-040: Timeout Guardrail Constants
# =============================================================================

# Multiplier for global deadline: tier_contract.deadline_ms * MULTIPLIER
VERIFICATION_TIMEOUT_MULTIPLIER = 1.5

# Per-tier maximum input characters (prompt size guardrails)
TIER_MAX_CHARS: Dict[str, int] = {
    "quick": 15000,
    "balanced": 30000,
    "high": 50000,
    "reasoning": 50000,
}

# =============================================================================
# End ADR-040 Constants
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


ProgressCallback = Callable[[int, int, str], Awaitable[None]]


def _build_preflight_info(content_chars: int, tier_contract: Any, tier: str) -> str:
    """Build pre-flight info message with complexity estimation.

    Args:
        content_chars: Number of characters in verification prompt
        tier_contract: TierContract for this verification
        tier: Tier name string

    Returns:
        Preflight info message string
    """
    max_chars = TIER_MAX_CHARS.get(tier, 50000)
    num_models = len(tier_contract.allowed_models)
    deadline_s = tier_contract.deadline_ms / 1000
    pct_used = (content_chars / max_chars) * 100 if max_chars > 0 else 0

    msg = (
        f"Preflight: tier={tier}, {content_chars} chars "
        f"({pct_used:.0f}% of {max_chars} limit), "
        f"{num_models} models, deadline={deadline_s:.0f}s"
    )

    if pct_used > 80:
        msg += " | WARNING: near tier input size limit, consider reducing scope"

    return msg


async def _run_verification_pipeline(
    request: VerifyRequest,
    store: TranscriptStore,
    on_progress: Optional[ProgressCallback],
    verification_id: str,
    transcript_dir: str,
    verification_query: str,
    tier_contract: Any,
    tier_timeout: Dict[str, int],
    ctx: Any,
    partial_state: Dict[str, Any],
    deadline_at: float,
) -> Dict[str, Any]:
    """Inner pipeline that runs the 3-stage council deliberation.

    Extracted from run_verification to allow wrapping with asyncio.wait_for()
    for global timeout enforcement (ADR-040).

    Uses waterfall time budgeting: each stage receives a proportional share of
    the remaining time budget rather than a static per-model timeout.

    Args:
        request: Verification request
        store: Transcript store
        on_progress: Progress callback
        verification_id: Unique verification ID
        transcript_dir: Path to transcript directory
        verification_query: Built verification prompt
        tier_contract: TierContract for this tier
        tier_timeout: Timeout config dict
        ctx: Verification context
        partial_state: Shared mutable dict for partial results (survives cancellation)
        deadline_at: Monotonic clock deadline for waterfall budgeting

    Returns:
        Verification result dictionary
    """
    num_models = len(tier_contract.allowed_models)

    # ADR-041: Initialize timing capture
    pipeline_start = time.monotonic()
    partial_state["stage_timings"] = {}

    # Progress: num_models (stage1) + num_models (stage2) + 2 (stage3 + finalize)
    total_steps = num_models + num_models + 2
    current_step = 0

    async def report_progress(message: str):
        nonlocal current_step
        current_step += 1
        if on_progress:
            try:
                await on_progress(current_step, total_steps, message)
            except Exception:
                pass  # Progress reporting is best-effort

    # Bridge stage1 per-model progress to our callback
    async def stage1_progress(completed: int, total: int, message: str):
        nonlocal current_step
        current_step = max(current_step, completed)  # Monotonic (models finish out-of-order)
        if on_progress:
            try:
                await on_progress(completed, total_steps, f"Stage 1: {message}")
            except Exception:
                pass

    # ADR-040: Waterfall time budgeting - Stage 1 gets 50% of remaining time
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage1_budget = remaining * 0.50
    stage1_per_model = min(stage1_budget, tier_timeout["per_model"])

    # Stage 1: Collect individual model responses with tier-appropriate models
    stage1_start = time.monotonic()
    try:
        stage1_results, stage1_usage, model_statuses = await stage1_collect_responses_with_status(
            verification_query,
            timeout=stage1_per_model,
            models=tier_contract.allowed_models,
            on_progress=stage1_progress,
        )
    finally:
        partial_state["stage_timings"]["stage1_elapsed_ms"] = int(
            (time.monotonic() - stage1_start) * 1000
        )
    current_step = num_models

    # ADR-040: Persist stage1 results to partial_state (survives cancellation)
    partial_state["completed_stages"].append("stage1")
    partial_state["stage1_results"] = stage1_results
    # ADR-041: Preserve model_statuses for performance tracker
    partial_state["model_statuses"] = model_statuses

    # Persist Stage 1
    store.write_stage(
        verification_id,
        "stage1",
        {
            "responses": stage1_results,
            "usage": stage1_usage,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # Stage 2: Peer ranking with rubric evaluation
    # ADR-040: Pass tier timeout and models to stage2
    if on_progress:
        try:
            await on_progress(num_models, total_steps, "Stage 2: Peer review starting...")
        except Exception:
            pass

    # Bridge stage2 per-model progress
    async def stage2_progress(completed: int, total: int, message: str):
        nonlocal current_step
        step = num_models + completed  # Offset by stage1 steps
        current_step = max(current_step, step)
        if on_progress:
            try:
                await on_progress(step, total_steps, f"Stage 2: {message}")
            except Exception:
                pass

    # ADR-040: Waterfall - Stage 2 gets 70% of remaining time after Stage 1
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage2_budget = remaining * 0.70
    stage2_per_model = min(stage2_budget, tier_timeout["per_model"])

    stage2_start = time.monotonic()
    try:
        stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(
            verification_query,
            stage1_results,
            timeout=stage2_per_model,
            models=tier_contract.allowed_models,
            on_progress=stage2_progress,
        )
    finally:
        partial_state["stage_timings"]["stage2_elapsed_ms"] = int(
            (time.monotonic() - stage2_start) * 1000
        )
    current_step = num_models + num_models

    # ADR-040: Persist stage2 results to partial_state
    partial_state["completed_stages"].append("stage2")
    partial_state["stage2_results"] = stage2_results
    partial_state["label_to_model"] = label_to_model

    # Persist Stage 2
    store.write_stage(
        verification_id,
        "stage2",
        {
            "rankings": stage2_results,
            "label_to_model": label_to_model,
            "usage": stage2_usage,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
    # ADR-041: Preserve aggregate_rankings for performance tracker
    partial_state["aggregate_rankings"] = aggregate_rankings

    # Stage 3: Chairman synthesis with verdict
    # ADR-040: Waterfall - Stage 3 gets all remaining time
    remaining = max(deadline_at - time.monotonic(), 1.0)
    stage3_budget = min(remaining, tier_timeout["per_model"])

    await report_progress("Stage 3: Synthesizing verdict...")
    stage3_start = time.monotonic()
    try:
        stage3_result, stage3_usage, verdict_result = await stage3_synthesize_final(
            verification_query,
            stage1_results,
            stage2_results,
            aggregate_rankings=aggregate_rankings,
            verdict_type=CouncilVerdictType.BINARY,
            timeout=stage3_budget,
        )
    finally:
        partial_state["stage_timings"]["stage3_elapsed_ms"] = int(
            (time.monotonic() - stage3_start) * 1000
        )

    # ADR-040: Persist stage3 results to partial_state
    partial_state["completed_stages"].append("stage3")

    # Persist Stage 3
    store.write_stage(
        verification_id,
        "stage3",
        {
            "synthesis": stage3_result,
            "aggregate_rankings": aggregate_rankings,
            "usage": stage3_usage,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    await report_progress("Finalizing verification result...")

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

    # ADR-041: Build timing summary
    total_elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
    global_deadline_ms = int(
        (tier_contract.deadline_ms / 1000) * VERIFICATION_TIMEOUT_MULTIPLIER * 1000
    )
    timing = {
        **partial_state.get("stage_timings", {}),
        "total_elapsed_ms": total_elapsed_ms,
        "global_deadline_ms": global_deadline_ms,
        "budget_utilization": round(total_elapsed_ms / max(global_deadline_ms, 1), 3),
    }
    input_metrics = {
        "content_chars": len(verification_query),
        "tier_max_chars": TIER_MAX_CHARS.get(request.tier, 50000),
        "num_models": num_models,
        "num_reviewers": num_models,
        "tier": request.tier,
    }

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
        "timeout_fired": False,
        "completed_stages": ["stage1", "stage2", "stage3"],
        "timing": timing,
        "input_metrics": input_metrics,
    }

    # Persist result
    store.write_stage(verification_id, "result", result)

    return result


async def run_verification(
    request: VerifyRequest,
    store: TranscriptStore,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """
    Run verification using LLM Council.

    This is the core verification logic that:
    1. Creates isolated context
    2. Runs council deliberation (with global timeout guardrail)
    3. Persists transcript
    4. Returns structured result (partial if timeout fires)

    ADR-040: Wraps pipeline in asyncio.wait_for() with global deadline
    derived from tier_contract.deadline_ms * VERIFICATION_TIMEOUT_MULTIPLIER.

    Args:
        request: Verification request
        store: Transcript store for persistence
        on_progress: Optional async callback(step, total, message) for progress

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
                "timestamp": datetime.now(UTC).isoformat(),
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

        # ADR-040 Step 5: Tiered input size limit check
        max_chars = TIER_MAX_CHARS.get(request.tier, 50000)
        if len(verification_query) > max_chars:
            return {
                "verification_id": verification_id,
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": (
                    f"Input size ({len(verification_query)} chars) exceeds "
                    f"{request.tier} tier limit ({max_chars} chars). "
                    f"Consider reducing scope or using a higher tier."
                ),
                "transcript_location": str(transcript_dir),
                "partial": True,
                "timeout_fired": False,
                "completed_stages": [],
            }

        # ADR-040 Step 6: Pre-flight info as first progress callback
        if on_progress:
            preflight_msg = _build_preflight_info(
                len(verification_query), tier_contract, request.tier
            )
            try:
                await on_progress(0, len(tier_contract.allowed_models) * 2 + 2, preflight_msg)
            except Exception:
                pass

        # ADR-040 Step 4: Global timeout wrapper with waterfall budgeting
        global_deadline = (tier_contract.deadline_ms / 1000) * VERIFICATION_TIMEOUT_MULTIPLIER
        deadline_at = time.monotonic() + global_deadline

        # Shared mutable state that survives asyncio.CancelledError on timeout
        partial_state: Dict[str, Any] = {
            "completed_stages": [],
            "stage1_results": None,
            "stage2_results": None,
            "label_to_model": None,
        }

        try:
            result = await asyncio.wait_for(
                _run_verification_pipeline(
                    request=request,
                    store=store,
                    on_progress=on_progress,
                    verification_id=verification_id,
                    transcript_dir=str(transcript_dir),
                    verification_query=verification_query,
                    tier_contract=tier_contract,
                    tier_timeout=tier_timeout,
                    ctx=ctx,
                    partial_state=partial_state,
                    deadline_at=deadline_at,
                ),
                timeout=global_deadline,
            )

            # ADR-041: Wire performance tracker (telemetry must never fail verification)
            try:
                model_statuses = partial_state.get("model_statuses", {})
                agg_list = partial_state.get("aggregate_rankings", [])
                agg_dict = {r["model"]: r for r in agg_list} if agg_list else {}
                if model_statuses and agg_dict:
                    persist_session_performance_data(
                        session_id=verification_id,
                        model_statuses=model_statuses,
                        aggregate_rankings=agg_dict,
                        stage2_results=partial_state.get("stage2_results"),
                    )
            except Exception:
                logger.debug("ADR-041: Performance telemetry persistence failed", exc_info=True)

            return result

        except asyncio.TimeoutError:
            # Global deadline exceeded - return partial result with completed stages
            completed = partial_state["completed_stages"]
            stage_timings = partial_state.get("stage_timings", {})
            global_deadline_ms = int(global_deadline * 1000)
            return {
                "verification_id": verification_id,
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": (
                    f"Verification timed out after {global_deadline:.0f}s "
                    f"(tier={request.tier}, deadline={tier_contract.deadline_ms}ms "
                    f"x {VERIFICATION_TIMEOUT_MULTIPLIER} multiplier). "
                    f"Completed stages: {completed}. "
                    f"Consider using a faster tier or reducing input scope."
                ),
                "transcript_location": str(transcript_dir),
                "partial": True,
                "timeout_fired": True,
                "completed_stages": completed,
                "timing": {
                    **stage_timings,
                    "total_elapsed_ms": global_deadline_ms,
                    "global_deadline_ms": global_deadline_ms,
                    "budget_utilization": 1.0,
                },
                "input_metrics": {
                    "content_chars": len(verification_query),
                    "tier_max_chars": TIER_MAX_CHARS.get(request.tier, 50000),
                    "num_models": len(tier_contract.allowed_models),
                    "num_reviewers": len(tier_contract.allowed_models),
                    "tier": request.tier,
                },
            }


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
