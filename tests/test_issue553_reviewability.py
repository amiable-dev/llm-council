"""Q2 reviewability: linguist-generated/vendored + .svg-as-noise (#553, ADR-053 Q2).

Content mode gains a reviewability layer between the garbage filter (Q2 basenames)
and decodability (Q1): a path marked `linguist-generated` / `linguist-vendored` in
the SNAPSHOT's `.gitattributes` is omitted (`generated` / `vendored`), and `.svg`
— which decodes as text but is usually a large generated asset — is omitted as
`noise` unless the operator sets `LLM_COUNCIL_REVIEW_SVG=true`.

All of this is content-mode only, so `allowlist` stays byte-identical: there,
`.svg` is still on `TEXT_EXTENSIONS` and is reviewed, and no `check-attr` runs.
"""

import asyncio
import subprocess

import pytest

from llm_council.verification import file_ops


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def attr_repo(tmp_path, monkeypatch):
    repo = tmp_path / "attr"
    (repo / "vendor").mkdir(parents=True)
    (repo / "gen").mkdir()
    (repo / "src").mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "vendor" / "lib.js").write_text("var a = 1;\n")
    (repo / "gen" / "out.js").write_text("var b = 2;\n")
    (repo / "src" / "app.py").write_text("print(1)\n")
    (repo / "icon.svg").write_text("<svg><path d='M0 0'/></svg>\n")
    (repo / ".gitattributes").write_text("vendor/** linguist-vendored\ngen/** linguist-generated\n")
    _git(repo, "add", "-A", "-f")
    _git(repo, "commit", "-qm", "init")
    sha = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, sha


async def _select(sha, paths):
    return await file_ops.select_blobs(sha, [(p, "discovered") for p in paths])


class TestContentModeReviewability:
    @pytest.fixture(autouse=True)
    def _on(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", "content")
        monkeypatch.delenv("LLM_COUNCIL_REVIEW_SVG", raising=False)

    def test_linguist_generated_is_omitted(self, attr_repo):
        _repo, sha = attr_repo
        selected, omitted = asyncio.run(_select(sha, ["gen/out.js", "src/app.py"]))
        assert {b.path for b in selected} == {"src/app.py"}
        assert any(o.path == "gen/out.js" and o.reason == "generated" for o in omitted)

    def test_linguist_vendored_is_omitted(self, attr_repo):
        _repo, sha = attr_repo
        selected, omitted = asyncio.run(_select(sha, ["vendor/lib.js", "src/app.py"]))
        assert {b.path for b in selected} == {"src/app.py"}
        assert any(o.path == "vendor/lib.js" and o.reason == "vendored" for o in omitted)

    def test_attrs_read_from_snapshot_not_worktree(self, attr_repo):
        repo, sha = attr_repo
        (repo / ".gitattributes").unlink()  # worktree no longer marks vendor/**
        selected, omitted = asyncio.run(_select(sha, ["vendor/lib.js"]))
        assert selected == [], "attrs must come from the snapshot, not the worktree"
        assert omitted[0].reason == "vendored"

    def test_svg_is_noise_by_default(self, attr_repo):
        _repo, sha = attr_repo
        selected, omitted = asyncio.run(_select(sha, ["icon.svg", "src/app.py"]))
        assert {b.path for b in selected} == {"src/app.py"}
        assert any(o.path == "icon.svg" and o.reason == "noise" for o in omitted)

    def test_svg_reviewable_when_operator_opts_in(self, attr_repo, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_REVIEW_SVG", "true")
        _repo, sha = attr_repo
        selected, _omitted = asyncio.run(_select(sha, ["icon.svg"]))
        assert {b.path for b in selected} == {"icon.svg"}


class TestAllowlistByteIdentical:
    def test_svg_still_reviewed_in_allowlist_mode(self, attr_repo, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", "allowlist")
        _repo, sha = attr_repo
        # .svg is on TEXT_EXTENSIONS; allowlist mode must review it, unchanged.
        selected, _omitted = asyncio.run(_select(sha, ["icon.svg"]))
        assert {b.path for b in selected} == {"icon.svg"}

    def test_linguist_not_consulted_in_allowlist_mode(self, attr_repo, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_FILE_SELECTION", "allowlist")
        _repo, sha = attr_repo
        # vendor/lib.js is a .js on TEXT_EXTENSIONS ⇒ reviewed; no check-attr runs.
        selected, _omitted = asyncio.run(_select(sha, ["vendor/lib.js"]))
        assert {b.path for b in selected} == {"vendor/lib.js"}


class TestReviewSvgFlag:
    @pytest.mark.parametrize(
        "val,reviewed",
        [(None, False), ("true", True), ("1", True), ("false", False), ("", False)],
    )
    def test_review_svg_flag(self, monkeypatch, val, reviewed):
        if val is None:
            monkeypatch.delenv("LLM_COUNCIL_REVIEW_SVG", raising=False)
        else:
            monkeypatch.setenv("LLM_COUNCIL_REVIEW_SVG", val)
        assert file_ops.review_svg_enabled() is reviewed
