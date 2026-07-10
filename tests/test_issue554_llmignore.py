"""Honor the .llmignore family (#554, ADR-053 Q3b).

Content mode reads the first present ignore file from the SNAPSHOT, in precedence
order .llmignore → .aiexclude → .aiignore → .cursorignore → .codeiumignore, and
omits matching paths as `ignored` (via the `pathspec` gitwildmatch matcher — no
bespoke matcher). It is **additive narrowing only**: the Q3 secret boundary runs
FIRST, so a `!.env` negation cannot re-admit a denied secret.

The `llm-council ignore` CLI is ergonomics, never the security mechanism: it
prints the built-in denylist, explains a path, and only writes a file on an
explicit `--init`.
"""

import asyncio
import subprocess

import pytest

from llm_council.verification import file_ops


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit_repo(tmp_path, monkeypatch, files):
    repo = tmp_path / "ig"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(repo, "add", "-A", "-f")
    _git(repo, "commit", "-qm", "init")
    sha = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, sha


async def _select(sha, paths):
    return await file_ops.select_blobs(sha, [(p, "discovered") for p in paths])


class TestIgnoreMatching:
    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", "content")

    def test_llmignore_omits_matching_paths(self, tmp_path, monkeypatch):
        _repo, sha = _commit_repo(
            tmp_path,
            monkeypatch,
            {"app.py": "print(1)\n", "build/out.txt": "junk\n", ".llmignore": "build/\n"},
        )
        selected, omitted = asyncio.run(_select(sha, ["app.py", "build/out.txt"]))
        assert {b.path for b in selected} == {"app.py"}
        assert any(o.path == "build/out.txt" and o.reason == "ignored" for o in omitted)

    def test_ignore_read_from_snapshot_not_worktree(self, tmp_path, monkeypatch):
        repo, sha = _commit_repo(
            tmp_path,
            monkeypatch,
            {"app.py": "x\n", "gen.txt": "y\n", ".llmignore": "gen.txt\n"},
        )
        (repo / ".llmignore").unlink()  # worktree no longer ignores
        selected, _ = asyncio.run(_select(sha, ["gen.txt"]))
        assert selected == [], "ignore rules must come from the snapshot"

    @pytest.mark.parametrize(
        "fname", [".aiexclude", ".aiignore", ".cursorignore", ".codeiumignore"]
    )
    def test_whole_family_is_honored(self, tmp_path, monkeypatch, fname):
        _repo, sha = _commit_repo(
            tmp_path, monkeypatch, {"app.py": "x\n", "skip.txt": "y\n", fname: "skip.txt\n"}
        )
        selected, _ = asyncio.run(_select(sha, ["app.py", "skip.txt"]))
        assert {b.path for b in selected} == {"app.py"}

    def test_precedence_llmignore_wins(self, tmp_path, monkeypatch):
        # .llmignore ignores a.txt; .cursorignore ignores b.txt. Only .llmignore
        # (highest precedence) is consulted, so b.txt is still reviewed.
        _repo, sha = _commit_repo(
            tmp_path,
            monkeypatch,
            {"a.txt": "x\n", "b.txt": "y\n", ".llmignore": "a.txt\n", ".cursorignore": "b.txt\n"},
        )
        selected, _ = asyncio.run(_select(sha, ["a.txt", "b.txt"]))
        assert {b.path for b in selected} == {"b.txt"}

    def test_negation_cannot_readmit_a_secret(self, tmp_path, monkeypatch):
        # `!.env` in .llmignore must NOT re-admit the secret — Q3 runs first.
        _repo, sha = _commit_repo(
            tmp_path, monkeypatch, {".env": "SECRET=x\n", ".llmignore": "!.env\n"}
        )
        selected, omitted = asyncio.run(_select(sha, [".env"]))
        assert selected == []
        assert omitted[0].reason == "denied_secret"  # not re-admitted, not "ignored"

    def test_no_ignore_file_is_a_noop(self, tmp_path, monkeypatch):
        _repo, sha = _commit_repo(tmp_path, monkeypatch, {"app.py": "x\n"})
        selected, _ = asyncio.run(_select(sha, ["app.py"]))
        assert {b.path for b in selected} == {"app.py"}


class TestIgnoreCLI:
    def test_print_defaults_lists_the_builtin_denylist(self, capsys):
        from llm_council.cli import cmd_ignore

        rc = cmd_ignore(_Ns(print_defaults=True))
        out = capsys.readouterr().out
        assert rc == 0
        assert ".env" in out and "id_rsa" in out  # a sample of the compiled-in floor

    def test_explain_reports_layer_and_rule(self, capsys):
        from llm_council.cli import cmd_ignore

        cmd_ignore(_Ns(explain=".env"))
        out = capsys.readouterr().out.lower()
        assert "secret" in out or "denied" in out

    def test_explain_reviewable_path(self, capsys):
        from llm_council.cli import cmd_ignore

        cmd_ignore(_Ns(explain="src/main.py"))
        out = capsys.readouterr().out.lower()
        assert "review" in out or "text" in out or "included" in out

    def test_init_writes_only_on_explicit_request(self, tmp_path, monkeypatch):
        from llm_council.cli import cmd_ignore

        monkeypatch.chdir(tmp_path)
        target = tmp_path / ".llmignore"
        assert not target.exists()
        # a plain invocation (no --init) must never write
        cmd_ignore(_Ns())
        assert not target.exists(), "cmd_ignore must not write a file without --init"
        # --init writes a commented starter
        cmd_ignore(_Ns(init=True))
        assert target.exists()
        assert target.read_text().lstrip().startswith("#")

    def test_init_does_not_clobber_existing(self, tmp_path, monkeypatch, capsys):
        from llm_council.cli import cmd_ignore

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".llmignore").write_text("mine\n")
        cmd_ignore(_Ns(init=True))
        assert (tmp_path / ".llmignore").read_text() == "mine\n", "must not overwrite"


class _Ns:
    """Minimal argparse.Namespace stand-in with defaulted ignore-subcommand flags."""

    def __init__(self, print_defaults=False, init=False, explain=None):
        self.print_defaults = print_defaults
        self.init = init
        self.explain = explain
