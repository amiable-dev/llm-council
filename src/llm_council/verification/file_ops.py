"""Git snapshot + file-fetching operations (split from api.py, #380).

Verbatim move — no logic changes. Back-compat re-exports live in api.py.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    ASYNC_SUBPROCESS_TIMEOUT,
    GARBAGE_FILENAMES,
    MAX_FILE_CHARS,
    MAX_FILES_EXPANSION,
    MAX_TOTAL_CHARS,
    TEXT_EXTENSIONS,
    TIER_MAX_CHARS,
)
from .schemas import SnapshotResolutionError

logger = logging.getLogger(__name__)

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
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=ASYNC_SUBPROCESS_TIMEOUT
            )
            if proc.returncode == 0:
                return stdout.decode("utf-8").strip()
            # Issue #340: surface stderr instead of swallowing it silently.
            # Common cause: snapshot not in the daemon's local clone.
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            logger.warning(
                "git cat-file failed for %s:%s (rc=%s): %s",
                snapshot_id,
                path,
                proc.returncode,
                stderr_text or "<no stderr>",
            )
        except Exception as e:
            # Issue #340: log the exception so subprocess failures are
            # diagnosable (timeouts, missing git binary, etc).
            logger.warning("git cat-file raised for %s:%s: %s", snapshot_id, path, e)

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
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=ASYNC_SUBPROCESS_TIMEOUT
            )

            if proc.returncode != 0:
                # Issue #340: surface git stderr at WARN.
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                logger.warning(
                    "git ls-tree failed for %s:%s (rc=%s): %s",
                    snapshot_id,
                    tree_path,
                    proc.returncode,
                    stderr_text or "<no stderr>",
                )
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

        except Exception as e:
            # Issue #340: log so subprocess/timeout failures are diagnosable.
            logger.warning("git ls-tree raised for %s:%s: %s", snapshot_id, tree_path, e)
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


async def _fetch_file_at_commit_async(
    snapshot_id: str,
    file_path: str,
    max_file_chars: Optional[int] = None,
) -> Tuple[str, bool]:
    """
    Fetch file contents from git at a specific commit (async version).

    Uses asyncio.create_subprocess_exec to avoid blocking the event loop.
    Uses semaphore to limit concurrent git operations (DoS prevention).
    Uses streaming read to avoid buffering entire large files (DoS prevention).

    Args:
        snapshot_id: Git commit SHA
        file_path: Path to file relative to repo root
        max_file_chars: Per-call cap on bytes read and final content length.
            Defaults to the legacy MAX_FILE_CHARS constant when None.
            Issue #342: the multi-file fetcher passes a tier-derived value
            so a single big file is not silently amputated to 15K when the
            tier budget is 50K.

    Returns:
        Tuple of (content, was_truncated)
    """
    limit = MAX_FILE_CHARS if max_file_chars is None else max_file_chars

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
                    while bytes_read < limit:
                        # Read in chunks of 8KB
                        chunk = await proc.stdout.read(8192)  # type: ignore[union-attr]
                        if not chunk:
                            break
                        chunks.append(chunk)
                        bytes_read += len(chunk)

                    # Check if there's more data (truncation needed)
                    if bytes_read >= limit:
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

            if truncated or len(content) > limit:
                content = (
                    content[:limit]
                    + f"\n\n... [truncated, original file larger than {limit} chars]"
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
    tier: str = "balanced",
) -> Tuple[str, Dict[str, Any]]:
    """
    Fetch file contents for verification prompt with expansion metadata.

    ADR-034 v2.6: This is the core implementation that handles directory
    expansion and returns metadata about what was expanded.

    Issue #342: per-file and per-batch byte caps now scale with `tier`,
    derived from TIER_MAX_CHARS. Per-file truncation is surfaced as a
    structured warning in `expansion_warnings` instead of being silently
    dropped (the original `truncated` boolean was bound and discarded).

    Args:
        snapshot_id: Git commit SHA
        target_paths: Optional list of specific paths (files or directories)
        tier: Active tier name; controls per-file / per-batch char budgets

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

    # Issue #342: derive per-file and per-batch caps from the tier so the
    # legacy 15K per-file limit cannot silently amputate a single big file
    # at the reasoning tier (which has 50K of headroom).
    tier_budget = TIER_MAX_CHARS.get(tier, 50000)
    per_file_budget = tier_budget
    per_batch_budget = tier_budget

    # ADR-034 v2.6: Expand directories in target_paths
    if target_paths:
        files_to_fetch, truncated, warnings = await _expand_target_paths(snapshot_id, target_paths)
        expansion_metadata["expanded_paths"] = files_to_fetch
        expansion_metadata["paths_truncated"] = truncated
        expansion_metadata["expansion_warnings"] = list(warnings)
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
        if total_chars >= per_batch_budget:
            sections.append(
                f"\n... [remaining files omitted, {per_batch_budget} char limit reached]"
            )
            break

        batch = files_to_fetch[i : i + BATCH_SIZE]
        results = await asyncio.gather(
            *[
                _fetch_file_at_commit_async(snapshot_id, fp, max_file_chars=per_file_budget)
                for fp in batch
            ]
        )

        for file_path, (content, truncated) in zip(batch, results):
            if total_chars >= per_batch_budget:
                sections.append(
                    f"\n... [remaining files omitted, {per_batch_budget} char limit reached]"
                )
                break

            total_chars += len(content)
            files_fetched += 1
            section = f"### {file_path}\n```\n{content}\n```"
            sections.append(section)

            # Issue #342: surface per-file truncation. Previously the
            # `truncated` boolean was bound and immediately discarded so
            # callers had no structured signal — only the inline
            # `[truncated, ...]` marker inside the file body itself.
            if truncated:
                expansion_metadata["expansion_warnings"].append(
                    f"file '{file_path}' truncated at {per_file_budget} chars "
                    f"({tier} tier per-file budget)"
                )

    return "\n\n".join(sections), expansion_metadata


