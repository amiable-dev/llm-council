"""Git snapshot + file-fetching operations (split from api.py, #380).

Verbatim move — no logic changes. Back-compat re-exports live in api.py.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    ASYNC_SUBPROCESS_TIMEOUT,
    GARBAGE_FILENAMES,
    MAX_BLOB_SIZE_BYTES,
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


@dataclass(frozen=True)
class SelectedBlob:
    """A path that has passed selection. Only ``select_blobs`` mints these.

    The batch fetcher accepts nothing else, so "a path nobody filtered" cannot be
    fetched by forgetting a call. (The low-level ``_fetch_file_at_commit_async``
    still takes a ``str``: it is the raw ``git show <sha>:<path>`` primitive and
    has no notion of policy. The enforced invariant — pinned by an AST test — is
    that it has exactly one caller, inside the batch fetcher, which only ever
    iterates ``SelectedBlob``.)
    """

    path: str
    origin: str  # "explicit" (caller named it) | "discovered" (expansion/diff-tree)


@dataclass(frozen=True)
class Omission:
    """A candidate path that selection rejected, and why."""

    path: str
    reason: str  # binary | garbage | not_found | unknown_object
    origin: str

    def as_warning(self) -> str:
        return f"Skipped {self.reason} file: {self.path}"


# =============================================================================
# ADR-053 Q3a (#540, #548): compiled-in secret-path trust boundary.
#
# Checked BEFORE the text/garbage predicates and BEFORE any blob is fetched, on
# explicit and discovered paths alike. Case-insensitive on purpose: `Secrets.yaml`
# and `.Env` are real files, and for a security floor over-matching is the safe
# direction (an over-match is a diagnosable `denied_secret` in the receipt; an
# under-match is a silent leak). NOT overridable by any in-repo file.
# =============================================================================

# Exact basenames (compared lowercased).
_SECRET_NAMES = frozenset(
    {
        ".env",
        ".envrc",
        ".npmrc",
        ".yarnrc",
        ".pypirc",
        ".git-credentials",
        ".dockercfg",
        ".netrc",
        "_netrc",
        ".pgpass",
        ".htpasswd",
        ".s3cfg",
        ".boto",
        ".terraformrc",
        ".databrickscfg",
        "kubeconfig",
        "credentials",  # .aws/credentials, .gem/credentials (dir-qualified below too)
        "config.json",  # only under a docker/gcloud/azure dir — guarded below
        "terraform.tfvars",
        "secrets.yaml",
        "secrets.yml",
    }
)

# Suffixes (lowercased). `.env.local`, `.env.production`, etc. are caught by the
# `.env.` prefix rule, not here.
_SECRET_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".keystore",
    ".jks",
    ".ovpn",
    ".asc",
    ".kubeconfig",
    ".auto.tfvars",
)

# Basename prefixes (lowercased).
_SECRET_PREFIXES = ("id_rsa", "id_ecdsa", "id_ed25519")

# Any path component equal to one of these ⇒ secret (dir-scoped secret stores).
_SECRET_DIRS = frozenset({".ssh", ".gnupg", ".aws", ".azure", ".kube", ".cargo", ".gem"})

# `<dir>/**` secret trees keyed by a leading component (broader than a basename
# match — everything under `.config/gcloud/` is a credential).
_SECRET_DIR_PREFIXES = (
    (".config", "gcloud"),
)

# Template suffixes that are conventionally secret-free and are explicitly kept.
_TEMPLATE_SUFFIXES = (".example", ".sample", ".template")


def _is_secret_path(file_path: str) -> bool:
    """True if a path must never be transmitted (ADR-053 Q3a). Case-insensitive."""
    p = Path(file_path.lower())
    name = p.name
    parts = p.parts

    # Templates win: `.env.example` is not a secret even though `.env.` matches.
    if name.endswith(_TEMPLATE_SUFFIXES):
        return False

    if any(part in _SECRET_DIRS for part in parts):
        return True
    for lead, sub in _SECRET_DIR_PREFIXES:
        if lead in parts and sub in parts:
            return True

    # `.env` and `.env.<anything-but-a-template>`
    if name == ".env" or name.startswith(".env."):
        return True

    if name in _SECRET_NAMES:
        # `config.json` is only a secret when directory-qualified, to avoid
        # denying an ordinary top-level `config.json` source file.
        if name == "config.json":
            return any(d in parts for d in (".docker", "docker"))
        return True

    if name.startswith(_SECRET_PREFIXES):
        return True
    if name.endswith(_SECRET_SUFFIXES):
        return True
    # `*service-account*.json` (GCP)
    if name.endswith(".json") and "service-account" in name:
        return True
    return False


def file_selection_mode() -> str:
    """ADR-053 Q1: `LLM_COUNCIL_FILE_SELECTION` in {allowlist,content,shadow}.

    Invalid / unset ⇒ `allowlist` (the safe, byte-identical default).
    """
    val = os.getenv("LLM_COUNCIL_FILE_SELECTION", "allowlist").strip().lower()
    return val if val in ("allowlist", "content", "shadow") else "allowlist"


async def _blob_sizes(snapshot_id: str, paths: List[str]) -> Dict[str, int]:
    """Byte size per path in the snapshot, via one `git ls-tree` call (#552).

    Serves the size cap AND empty-file disambiguation (an empty blob is text but
    `git grep` never lists it). Missing ⇒ absent from the returned map.
    """
    if not paths:
        return {}
    git_root = await _get_git_root_async()
    semaphore = await _get_git_semaphore()
    for fmt in ("--format=%(objectsize) %(path)", None):
        args = ["git", "ls-tree", "-rz"]
        if fmt:
            args.append(fmt)
        else:
            args.insert(2, "-l")  # `-rl`: long listing, size in a fixed column
        args += [snapshot_id, "--", *paths]
        async with semaphore:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=git_root,
                )
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=ASYNC_SUBPROCESS_TIMEOUT
                )
            except Exception as e:
                logger.warning("git ls-tree (sizes) raised: %s", e)
                return {}
        if proc.returncode != 0:
            continue  # try the fallback format
        out = stdout.decode("utf-8", errors="replace")
        sizes: Dict[str, int] = {}
        for entry in out.split("\0"):
            if not entry.strip():
                continue
            if fmt:
                size_str, _, path = entry.partition(" ")
            else:
                # "<mode> <type> <hash> <size>\t<path>"
                meta, _, path = entry.partition("\t")
                size_str = meta.split()[-1]
            try:
                sizes[path] = int(size_str)
            except ValueError:
                continue
        return sizes
    return {}


async def _text_paths(snapshot_id: str, paths: List[str]) -> set:
    """Subset of `paths` git classifies as text (NUL rule + `.gitattributes`).

    `git --attr-source=<sha> grep -Iz --name-only -e '' <sha> -- <paths>`:
    `-I` applies git's own binary heuristic (NUL in first 8000 bytes), and
    `--attr-source=<sha>` honours `binary`/`-diff` from the SNAPSHOT's
    `.gitattributes` (a top-level git option, not a grep flag — verified 2.50.1).
    Exit 1 = "no text file matched", not an error. Empty blobs never appear here
    (they are recovered via `_blob_sizes` size==0 by the caller).
    """
    if not paths:
        return set()
    git_root = await _get_git_root_async()
    semaphore = await _get_git_semaphore()
    async with semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", f"--attr-source={snapshot_id}", "grep", "-Iz", "--name-only",
                "-e", "", snapshot_id, "--", *paths,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=git_root,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=ASYNC_SUBPROCESS_TIMEOUT
            )
        except Exception as e:
            logger.warning("git grep (text sniff) raised: %s", e)
            return set()
    # rc 0 = matches, 1 = no matches (not an error), >1 = real failure.
    if proc.returncode not in (0, 1):
        logger.warning("git grep (text sniff) rc=%s", proc.returncode)
        return set()
    out = stdout.decode("utf-8", errors="replace")
    result = set()
    for entry in out.split("\0"):
        if not entry:
            continue
        # output is "<sha>:<path>"; strip the "<sha>:" prefix.
        _, _, path = entry.partition(":")
        result.add(path or entry)
    return result


async def _classify_decodable(
    snapshot_id: str, candidates: List[Tuple[str, str]]
) -> Tuple[List[SelectedBlob], List[Omission]]:
    """Content-mode decodability (ADR-053 Q1): size cap → binary/text via git."""
    paths = [p for p, _ in candidates]
    sizes = await _blob_sizes(snapshot_id, paths)
    text = await _text_paths(snapshot_id, paths)
    selected: List[SelectedBlob] = []
    omitted: List[Omission] = []
    for path, origin in candidates:
        size = sizes.get(path)
        if size is not None and size > MAX_BLOB_SIZE_BYTES:
            omitted.append(Omission(path, "too_large", origin))
        elif path in text or size == 0:  # size==0 recovers empty blobs grep omits
            selected.append(SelectedBlob(path, origin))
        else:
            omitted.append(Omission(path, "binary", origin))
    return selected, omitted


async def select_blobs(
    snapshot_id: str,
    candidates: List[Tuple[str, str]],
) -> Tuple[List[SelectedBlob], List[Omission]]:
    """The single place selection policy is evaluated (#543, ADR-053 Q0/Q1).

    ``candidates`` are ``(path, origin)`` pairs. Origin is a property of each
    CANDIDATE, not of the call: one request mixes explicitly-named paths with
    directory-expanded discoveries.

    Order: Q3 secret boundary → Q2 garbage → Q1 decodability. Q3/Q2 are path-only
    and always run. Q1 depends on ``LLM_COUNCIL_FILE_SELECTION`` (#552):
    ``allowlist`` (default) uses the extension predicate and makes NO git call —
    byte-identical to pre-#552; ``content`` sniffs blob bytes via git; ``shadow``
    acts on the allowlist but logs what content would have changed.
    """
    mode = file_selection_mode()
    selected: List[SelectedBlob] = []
    omitted: List[Omission] = []
    # Q3 + Q2 first — a secret is denied even if it is text (#540/#548).
    survivors: List[Tuple[str, str]] = []
    for path, origin in candidates:
        if _is_secret_path(path):
            omitted.append(Omission(path, "denied_secret", origin))
        elif _is_garbage_file(path):
            omitted.append(Omission(path, "garbage", origin))
        else:
            survivors.append((path, origin))

    if mode == "content":
        sel, om = await _classify_decodable(snapshot_id, survivors)
        selected += sel
        omitted += om
        return selected, omitted

    # allowlist (and the acted-on half of shadow): sync extension predicate.
    for path, origin in survivors:
        if _is_text_file(path):
            selected.append(SelectedBlob(path, origin))
        else:
            omitted.append(Omission(path, "non-text", origin))

    if mode == "shadow" and survivors:
        try:
            csel, _com = await _classify_decodable(snapshot_id, survivors)
            allow_set = {b.path for b in selected}
            content_set = {b.path for b in csel}
            would_add = sorted(content_set - allow_set)
            would_drop = sorted(allow_set - content_set)
            if would_add or would_drop:
                logger.info(
                    "LLM_COUNCIL_FILE_SELECTION=shadow: content would add %s, drop %s",
                    would_add, would_drop,
                )
        except Exception:  # shadow telemetry must never break selection
            logger.debug("shadow content classification failed", exc_info=True)

    return selected, omitted


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

    # #548: config templates (`.env.example`, `foo.conf.sample`) are reviewable —
    # this is the convention #540 wanted to preserve. `.env` itself never reaches
    # here (the secret boundary denies it first, in select_blobs).
    if name.endswith(_TEMPLATE_SUFFIXES):
        return True

    return False


def _is_garbage_file(file_path: str) -> bool:
    """Check if a path is deny-listed noise (lockfiles, generated dirs).

    #543: this compared only ``Path(p).name``, so the DIRECTORY entries in
    ``GARBAGE_FILENAMES`` (``node_modules``, ``__pycache__``, ``.git``) never
    matched — ``Path("node_modules/react/index.js").name`` is ``index.js`` — and
    committed ``node_modules`` was reviewed. Every path component is checked now.
    """
    return any(part in GARBAGE_FILENAMES for part in Path(file_path).parts)


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
            # An explicitly-named file. Same gate as everything else.
            selected, omitted = await select_blobs(snapshot_id, [(path, "explicit")])
            warnings.extend(o.as_warning() for o in omitted)
            expanded_files.extend(b.path for b in selected)

        elif obj_type == "tree":
            # A directory — expand, then gate. Discoveries are omitted quietly
            # (the caller did not name them); explicit paths are warned about.
            tree_files = await _git_ls_tree_z_name_only(snapshot_id, path)
            selected, _omitted = await select_blobs(snapshot_id, [(f, "discovered") for f in tree_files])

            for blob in selected:
                expanded_files.append(blob.path)
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
                    changed = [f for f in stdout.decode("utf-8").strip().split("\n") if f]
                    # #543: THIS is the bug. These paths went straight to the
                    # fetcher — no text check, no garbage check, no warning — so
                    # `target_paths=None` (the default at run_verification and the
                    # MCP verify tool) transmitted secrets, binaries and lockfiles.
                    # Every candidate producer goes through the selector now.
                    selected, omitted = await select_blobs(snapshot_id, [(f, "discovered") for f in changed])
                    files_to_fetch = [b.path for b in selected]
                    expansion_metadata["expanded_paths"] = files_to_fetch
                    expansion_metadata["expansion_warnings"] = [
                        o.as_warning() for o in omitted
                    ]
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


