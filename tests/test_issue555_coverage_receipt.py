"""Structural coverage receipt + conservation invariant (#555, ADR-053).

#542's serious failure mode: some target_paths resolve, some don't, the call
succeeds, and the drop appears only as a prose string in `expansion_warnings` —
which no CI gate parses. The receipt makes every omission a typed
`{path, reason, origin}` on the response, so a caller can tell a `.zig` drop
(`non-text`) from a `.png` drop (`binary`) from a secret (`denied_secret`).

Additive, default-ON, no clamp (that is #556). The conservation invariant —
`reviewed ∪ omitted == candidates`, disjoint — is asserted defensively (marker on
violation, never a crash), the ADR-051 C4 pattern.
"""

import asyncio
import random
import subprocess

import pytest

from llm_council.verification import file_ops


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(tmp_path, monkeypatch, files):
    repo = tmp_path / "cov"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("root\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "root")
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)
    _git(repo, "add", "-A", "-f")
    _git(repo, "commit", "-qm", "work")
    sha = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, sha


async def _meta(sha, target_paths):
    _content, meta = await file_ops._fetch_files_for_verification_async_with_metadata(
        sha, target_paths
    )
    return meta


class TestCoverageReceipt:
    def test_coverage_present_with_typed_omissions(self, tmp_path, monkeypatch):
        _repo, sha = _commit(
            tmp_path,
            monkeypatch,
            {"src/app.py": "x\n", "logo.png": b"PNG\x00\x01\x00\n", "yarn.lock": "lock\n"},
        )
        meta = asyncio.run(_meta(sha, None))
        cov = meta["coverage"]
        assert "src/app.py" in cov["reviewed"]
        by_path = {o["path"]: o["reason"] for o in cov["omitted"]}
        assert by_path.get("logo.png") == "non-text"  # allowlist: .png not text
        assert by_path.get("yarn.lock") == "garbage"
        # every omission carries origin, and denied_secret never a value
        assert all(set(o) == {"path", "reason", "origin"} for o in cov["omitted"])

    def test_reason_distinguishes_secret_from_binary(self, tmp_path, monkeypatch):
        _repo, sha = _commit(
            tmp_path,
            monkeypatch,
            {".env": "SECRET=leak\n", "logo.png": b"\x00bin\n", "app.py": "x\n"},
        )
        meta = asyncio.run(_meta(sha, None))
        by_path = {o["path"]: o["reason"] for o in meta["coverage"]["omitted"]}
        assert by_path[".env"] == "denied_secret"
        # the receipt never contains the secret value
        assert "leak" not in str(meta["coverage"])

    def test_explicit_omitted_flag_when_named_path_dropped(self, tmp_path, monkeypatch):
        _repo, sha = _commit(tmp_path, monkeypatch, {"a.zig": "const x=1;\n", "b.py": "y\n"})
        # allowlist mode: .zig is non-text; naming it explicitly ⇒ explicit_omitted
        meta = asyncio.run(_meta(sha, ["a.zig", "b.py"]))
        cov = meta["coverage"]
        assert cov["explicit_omitted"] is True
        assert any(o["path"] == "a.zig" and o["origin"] == "explicit" for o in cov["omitted"])

    def test_not_found_path_is_recorded(self, tmp_path, monkeypatch):
        _repo, sha = _commit(tmp_path, monkeypatch, {"real.py": "x\n"})
        meta = asyncio.run(_meta(sha, ["real.py", "does/not/exist.py"]))
        cov = meta["coverage"]
        assert any(
            o["path"] == "does/not/exist.py" and o["reason"] == "not_found" for o in cov["omitted"]
        )
        assert cov["explicit_omitted"] is True

    def test_requested_is_verbatim_target_paths(self, tmp_path, monkeypatch):
        _repo, sha = _commit(tmp_path, monkeypatch, {"a.py": "x\n"})
        meta = asyncio.run(_meta(sha, ["a.py", "missing.py"]))
        assert meta["coverage"]["requested"] == ["a.py", "missing.py"]


class TestConservationInvariant:
    def test_reviewed_and_omitted_partition_the_candidates(self, tmp_path, monkeypatch):
        _repo, sha = _commit(
            tmp_path,
            monkeypatch,
            {"src/app.py": "x\n", "logo.png": b"\x00\n", "yarn.lock": "l\n", "doc.md": "d\n"},
        )
        meta = asyncio.run(_meta(sha, None))
        cov = meta["coverage"]
        reviewed = set(cov["reviewed"])
        omitted = {o["path"] for o in cov["omitted"]}
        assert reviewed.isdisjoint(omitted)
        assert cov["conservation_ok"] is True

    def test_conservation_holds_over_random_trees(self, tmp_path, monkeypatch):
        rng = random.Random(1234)  # seeded; Date/random-free determinism
        files = {}
        for i in range(40):
            kind = rng.choice(["py", "zig", "png", "lock", "md", "env"])
            if kind == "py":
                files[f"d{i % 5}/f{i}.py"] = "x\n"
            elif kind == "zig":
                files[f"d{i % 5}/f{i}.zig"] = "const x=1;\n"
            elif kind == "png":
                files[f"d{i % 5}/f{i}.png"] = b"\x00bin\n"
            elif kind == "lock":
                files[f"d{i % 5}/yarn.lock"] = "l\n"
            elif kind == "md":
                files[f"d{i % 5}/f{i}.md"] = "d\n"
            else:
                files[f"d{i % 5}/.env"] = "S=x\n"
        _repo, sha = _commit(tmp_path, monkeypatch, files)
        meta = asyncio.run(_meta(sha, None))
        cov = meta["coverage"]
        reviewed = set(cov["reviewed"])
        omitted = {o["path"] for o in cov["omitted"]}
        assert reviewed.isdisjoint(omitted), "reviewed and omitted overlap"
        assert cov["conservation_ok"] is True


class TestSchema:
    def test_verify_response_has_coverage_field(self):
        from llm_council.verification.schemas import VerifyResponse

        assert "coverage" in VerifyResponse.model_fields

    def test_coverage_report_round_trips(self):
        from llm_council.verification.schemas import CoverageReport

        c = CoverageReport(
            requested=["a.py"],
            reviewed=["a.py"],
            omitted=[{"path": ".env", "reason": "denied_secret", "origin": "explicit"}],
            explicit_omitted=True,
            truncated=False,
            conservation_ok=True,
        )
        dumped = c.model_dump()
        assert dumped["omitted"][0]["reason"] == "denied_secret"
