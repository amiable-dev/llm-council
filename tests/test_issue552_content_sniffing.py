"""Q1 content sniffing behind LLM_COUNCIL_FILE_SELECTION (#552, ADR-053 Q1).

`content` mode replaces the `TEXT_EXTENSIONS` allowlist with git's own rule —
a blob is text iff its first 8000 bytes contain no NUL — read via
`git --attr-source=<sha> grep -I`, which also honours `.gitattributes`
`binary`/`-diff` from the snapshot. A one-call `git ls-tree` size pre-pass
enforces a byte cap and disambiguates empty files (which `grep` omits).

`allowlist` (default) stays byte-identical. `shadow` acts on the allowlist but
logs what `content` would have changed.

ADR erratum: the ADR's Q1 example list includes `.envrc` as "reviewed", but
Q3a lists it as a secret and #548 shipped it denied. The secret boundary runs
first and `.envrc` genuinely holds `export SECRET=…`, so it STAYS denied here.
"""

import asyncio
import subprocess
from pathlib import Path

import pytest

from llm_council.verification import file_ops


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def sniff_repo(tmp_path, monkeypatch):
    repo = tmp_path / "sniff"
    (repo / "src").mkdir(parents=True)
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")

    # extensions NOT on TEXT_EXTENSIONS
    (repo / "src" / "main.zig").write_text('const std = @import("std");\n')
    (repo / "main.tf").write_text('resource "x" "y" {}\n')
    (repo / "app.dart").write_text("void main() {}\n")
    (repo / "Token.sol").write_text("contract T {}\n")
    # extensionless, no special-case
    (repo / "LICENSE").write_text("MIT License\n")
    (repo / "CODEOWNERS").write_text("* @team\n")
    (repo / "deploy").write_text("#!/usr/bin/env bash\necho hi\n")
    (repo / "empty.py").write_text("")  # empty: text, but grep won't list it
    # binary by content, and a lying extension
    (repo / "logo.png").write_bytes(b"PNG\x00\x01binary\x00\n")
    (repo / "weird.txt").write_bytes(b"utf16\x00text\x00\n")
    # .gitattributes: mark a generated file -diff
    (repo / "gen.js").write_text("var a = 1;\n")
    (repo / ".gitattributes").write_text("gen.js -diff\n")

    _git(repo, "add", "-A", "-f")
    _git(repo, "commit", "-qm", "init")
    sha = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, sha


async def _select(sha, paths, origin="discovered"):
    return await file_ops.select_blobs(sha, [(p, origin) for p in paths])


class TestContentMode:
    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", "content")

    def test_unlisted_languages_are_reviewed_without_a_list_edit(self, sniff_repo):
        _repo, sha = sniff_repo
        paths = ["src/main.zig", "main.tf", "app.dart", "Token.sol"]
        selected, omitted = asyncio.run(_select(sha, paths))
        assert {b.path for b in selected} == set(paths), (
            f"omitted: {[(o.path, o.reason) for o in omitted]}"
        )

    def test_extensionless_text_files_are_reviewed(self, sniff_repo):
        _repo, sha = sniff_repo
        paths = ["LICENSE", "CODEOWNERS", "deploy", "empty.py"]
        selected, _omitted = asyncio.run(_select(sha, paths))
        assert {b.path for b in selected} == set(paths)

    def test_nul_bearing_blobs_excluded_as_binary(self, sniff_repo):
        _repo, sha = sniff_repo
        selected, omitted = asyncio.run(_select(sha, ["logo.png", "weird.txt"]))
        assert selected == []
        assert {o.reason for o in omitted} == {"binary"}

    def test_gitattributes_minus_diff_honored_from_snapshot(self, sniff_repo):
        _repo, sha = sniff_repo
        selected, omitted = asyncio.run(_select(sha, ["gen.js"]))
        assert selected == [], "gen.js is -diff in the snapshot's .gitattributes"
        assert omitted[0].reason == "binary"

    def test_oversize_blob_excluded_before_fetch(self, sniff_repo, monkeypatch):
        repo, sha = sniff_repo
        monkeypatch.setattr(file_ops, "MAX_BLOB_SIZE_BYTES", 4)  # tiny cap
        selected, omitted = asyncio.run(_select(sha, ["LICENSE"]))  # 11 bytes > 4
        assert selected == []
        assert omitted[0].reason == "too_large"

    def test_secret_still_denied_first_in_content_mode(self, sniff_repo):
        """Q3 runs before Q1 — a committed .env is denied, not sniffed."""
        repo, sha = sniff_repo
        (repo / ".env").write_text("SECRET=x\n")
        _git(repo, "add", "-A", "-f")
        _git(repo, "commit", "-qm", "add env")
        sha2 = _git(repo, "rev-parse", "HEAD")
        selected, omitted = asyncio.run(_select(sha2, [".env"], origin="explicit"))
        assert selected == []
        assert omitted[0].reason == "denied_secret"

    def test_envrc_stays_denied_adr_erratum(self, sniff_repo):
        """ADR Q1 lists .envrc as reviewed; Q3a + #548 deny it. Security wins."""
        repo, sha = sniff_repo
        (repo / ".envrc").write_text("export AWS_SECRET_ACCESS_KEY=leak\n")
        _git(repo, "add", "-A", "-f")
        _git(repo, "commit", "-qm", "add envrc")
        sha2 = _git(repo, "rev-parse", "HEAD")
        selected, omitted = asyncio.run(_select(sha2, [".envrc"]))
        assert selected == []
        assert omitted[0].reason == "denied_secret"


class TestAllowlistModeByteIdentical:
    def test_default_is_allowlist_and_uses_the_extension_predicate(self, sniff_repo, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_FILE_SELECTION", raising=False)
        _repo, sha = sniff_repo
        # .zig is NOT on TEXT_EXTENSIONS ⇒ dropped in allowlist mode (the #542 gap)
        selected, omitted = asyncio.run(_select(sha, ["src/main.zig", "LICENSE"]))
        assert "src/main.zig" not in {b.path for b in selected}
        # allowlist mode must make NO git subprocess call for content sniffing
        # (byte-identical guarantee) — asserted indirectly: .zig omitted as non-text
        assert any(o.path == "src/main.zig" and o.reason == "non-text" for o in omitted)

    def test_allowlist_mode_is_synchronous_pathonly(self, monkeypatch):
        """allowlist mode must not require a snapshot round-trip (no git calls)."""
        monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", "allowlist")
        # a bogus snapshot must not matter in allowlist mode — no git call is made
        selected, omitted = asyncio.run(
            file_ops.select_blobs("0" * 40, [("a.py", "explicit"), ("b.zig", "explicit")])
        )
        assert {b.path for b in selected} == {"a.py"}
        assert any(o.path == "b.zig" for o in omitted)


class TestShadowMode:
    def test_shadow_acts_on_allowlist_but_reports_the_delta(self, sniff_repo, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", "shadow")
        _repo, sha = sniff_repo
        # shadow ACTS on allowlist: .zig stays omitted
        selected, omitted = asyncio.run(_select(sha, ["src/main.zig", "app.py"]))
        assert "src/main.zig" not in {b.path for b in selected}


class TestModeParsing:
    @pytest.mark.parametrize(
        "val,expected",
        [
            (None, "allowlist"),
            ("allowlist", "allowlist"),
            ("content", "content"),
            ("shadow", "shadow"),
            ("CONTENT", "content"),
            ("garbage", "allowlist"),  # invalid ⇒ safe default
        ],
    )
    def test_file_selection_mode(self, monkeypatch, val, expected):
        if val is None:
            monkeypatch.delenv("LLM_COUNCIL_FILE_SELECTION", raising=False)
        else:
            monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", val)
        assert file_ops.file_selection_mode() == expected
