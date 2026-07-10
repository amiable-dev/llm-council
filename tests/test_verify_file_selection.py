"""Red-team + architecture tests for the verification file-selection chokepoint (#543).

`_is_text_file` and `_is_garbage_file` had exactly one call site: inside
`_expand_target_paths`. That function is only reached from the `if target_paths:`
branch of `_fetch_files_for_verification_async_with_metadata`. The `else` branch —
taken whenever `target_paths` is `None`, which is the DEFAULT at both
`run_verification` and the MCP `verify` tool — ran `git diff-tree --name-only`
and passed the result straight to the fetcher.

No text check. No garbage check. No warning. A commit touching `.env` transmitted
it to the configured LLM provider, along with binary blobs and lockfiles.

Nothing tested `target_paths=None`. That is why it shipped.

ADR-053 § "Q0 — Enforcement". Every producer of candidate paths now goes through
one selector, and an unfiltered fetch is not representable.
"""

import ast
import asyncio
import pathlib
import subprocess
from typing import List

import pytest

from llm_council.verification import file_ops


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def redteam_repo(tmp_path, monkeypatch):
    """A commit touching a secret, a binary, a lockfile, and one real source file.

    NOTE: the commit must have a parent — `git diff-tree` emits nothing for a root
    commit, which silently turns this fixture into a no-op that passes vacuously.
    """
    repo = tmp_path / "redteam"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "root")

    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("x = 1\n")
    (repo / ".env").write_text("OPENAI_API_KEY=sk-REDTEAM-SECRET-abc123\n")
    (repo / "id_rsa").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nREDTEAMKEY\n")
    (repo / "logo.png").write_bytes(b"\x89PNG\x00\x00\x0dIHDR\x00\x00REDTEAMBINARY\x00\n")
    (repo / "yarn.lock").write_text("# yarn lockfile v1\nredteam-lock-data\n")
    _git(repo, "add", "-A", "-f")
    _git(repo, "commit", "-qm", "touches secret, binary, lockfile, source")

    sha = _git(repo, "rev-parse", "HEAD")

    # file_ops caches the git root process-wide.
    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, sha


# #547 installed the chokepoint; #548 added the secret boundary. As of #548 every
# item below is blocked on every path (default / directory / explicit).
BLOCKED_BY_CHOKEPOINT = {
    "REDTEAMBINARY": "binary blob",
    "redteam-lock-data": "deny-listed lockfile",
}
BLOCKED_BY_DENYLIST = {
    "sk-REDTEAM-SECRET-abc123": ".env secret (#548 secret boundary)",
    "REDTEAMKEY": "id_rsa private key (#548 secret boundary)",
}


async def _prompt_for(sha: str, target_paths):
    content, _meta = await file_ops._fetch_files_for_verification_async_with_metadata(
        sha, target_paths
    )
    return content


@pytest.mark.parametrize(
    "target_paths,label",
    [
        (None, "target_paths=None (the DEFAULT invocation)"),
        ([""], "target_paths=[directory]"),
        ([".env", "src/app.py"], "target_paths=[explicit secret + source]"),
    ],
)
def test_no_binary_or_lockfile_ever_reaches_the_prompt(redteam_repo, target_paths, label):
    """#547: the filter must run on EVERY path, including target_paths=None."""
    _repo, sha = redteam_repo
    prompt = asyncio.run(_prompt_for(sha, target_paths))

    leaked = [why for needle, why in BLOCKED_BY_CHOKEPOINT.items() if needle in prompt]
    assert not leaked, f"{label}: leaked {leaked} into the verification prompt"


@pytest.mark.parametrize(
    "target_paths",
    [None, [""], [".env", "src/app.py"]],
    ids=["default", "directory", "explicit"],
)
def test_env_secret_never_reaches_the_prompt(redteam_repo, target_paths):
    # #548 landed: `.env` is denied by the compiled-in secret boundary (not merely
    # dropped as non-text), on the explicit path too.
    _repo, sha = redteam_repo
    prompt = asyncio.run(_prompt_for(sha, target_paths))
    leaked = [why for needle, why in BLOCKED_BY_DENYLIST.items() if needle in prompt]
    assert not leaked, f"leaked {leaked}"


def test_the_default_invocation_still_reviews_real_source(redteam_repo):
    """The fix must narrow, not blind: legitimate source is still reviewed."""
    _repo, sha = redteam_repo
    prompt = asyncio.run(_prompt_for(sha, None))
    assert "src/app.py" in prompt


def test_default_invocation_records_its_omissions(redteam_repo):
    """#543: `expansion_warnings` was empty on this path — omissions were invisible."""
    _repo, sha = redteam_repo
    _content, meta = asyncio.run(
        file_ops._fetch_files_for_verification_async_with_metadata(sha, None)
    )
    warnings = meta.get("expansion_warnings") or []
    assert warnings, "the diff-tree path drops files with no warning at all"
    joined = " ".join(warnings)
    assert "logo.png" in joined
    assert "yarn.lock" in joined


def test_garbage_matching_covers_directory_components(redteam_repo):
    """`node_modules`/`__pycache__`/`.git` are in GARBAGE_FILENAMES but are DIRECTORIES.

    `Path(p).name` of `node_modules/react/index.js` is `index.js`, so those entries
    never matched and committed `node_modules` was reviewed.
    """
    assert file_ops._is_garbage_file("node_modules/react/index.js")
    assert file_ops._is_garbage_file("src/__pycache__/x.pyc")
    assert not file_ops._is_garbage_file("src/app.py")


class TestArchitectureNoBypass:
    def test_fetch_has_exactly_one_caller_across_the_package(self):
        """The raw `git show` primitive must be reachable from one place only.

        Excluding `file_ops.py` wholesale would let a future bypass be added inside
        the very module that owns the gate. So: no callers anywhere else in the
        package, and inside `file_ops` exactly one -- the batch fetcher, which only
        ever iterates `SelectedBlob` values produced by `select_blobs`.
        """
        pkg = pathlib.Path(file_ops.__file__).parent.parent
        external: List[str] = []
        internal_callers = set()

        for py in pkg.rglob("*.py"):
            tree = ast.parse(py.read_text(), filename=str(py))
            enclosing = {}
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for node in ast.walk(fn):
                        enclosing[id(node)] = fn.name
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name != "_fetch_file_at_commit_async":
                    continue
                if py.name == "file_ops.py":
                    internal_callers.add(enclosing.get(id(node), "<module>"))
                else:
                    external.append(f"{py.name}:{node.lineno}")

        assert not external, f"fetch called outside file_ops: {external}"
        assert internal_callers == {"_fetch_files_for_verification_async_with_metadata"}, (
            f"fetch called from {sorted(internal_callers)}; expected only the batch fetcher"
        )

    def test_selected_blob_is_frozen(self):
        """A vetted path cannot be silently re-pointed after selection."""
        blob = file_ops.SelectedBlob(path="src/app.py", origin="explicit")
        with pytest.raises(Exception):
            blob.path = "/etc/passwd"

    def test_selector_is_the_single_evaluation_site_for_the_predicates(self):
        """`_is_text_file` / `_is_garbage_file` must be evaluated in exactly one function."""
        source = pathlib.Path(file_ops.__file__).read_text()
        tree = ast.parse(source)
        callers = set()
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None)
                    if name in {"_is_text_file", "_is_garbage_file"}:
                        callers.add(fn.name)
        assert callers == {"select_blobs"}, (
            f"selection predicates evaluated in {sorted(callers)}; expected only select_blobs"
        )
