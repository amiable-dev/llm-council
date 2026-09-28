"""#704 — the required quality gate reviewed no code, on every PR.

The ticket blamed the SHA: on a `pull_request` event `github.sha` is the merge
commit GitHub synthesises for `refs/pull/N/merge`. The SHA was fine; the object
exists in the checkout. What failed was discovery. With no `target_paths`,
verify asks `git diff-tree -r <sha>` what changed, and **`diff-tree` prints
nothing for a merge commit** unless told which parent to diff against. So every
PR gate sent the council an empty subject. The council declined to invent
findings, and the gate turned that refusal into a coin flip: three passes and a
fail over the same nothing.

Passing the PR head instead, as the ticket proposed, would have been worse in a
quieter way: `diff-tree <head>` shows only the PR's LAST commit.

Two fixes, both tested here:

1. Discovery diffs a merge commit against its **first parent**, which for a PR
   merge commit is exactly the PR's changes.
2. **A gate that resolves nothing to review stops.** It returns a non-deliberated
   result that no caller can read as a verdict, and `llm-council gate` exits 3,
   which the action maps to an error. Exit 2 would not do: the action turns
   UNCLEAR into a passing check with a warning.
"""

import asyncio
import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from llm_council.verification import file_ops


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def pr_repo(tmp_path, monkeypatch):
    """main + a two-commit feature branch merged with --no-ff, like a PR merge ref."""
    repo = tmp_path / "pr"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "root")

    _git(repo, "checkout", "-qb", "feature")
    (repo / "first.py").write_text("a = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "first change")
    (repo / "second.py").write_text("b = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "second change")
    head = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    (repo / "unrelated_on_main.py").write_text("c = 3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "main moved on")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    merge = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, merge, head


def _discover(sha):
    _content, meta = asyncio.run(
        file_ops._fetch_files_for_verification_async_with_metadata(sha, None)
    )
    return meta


class TestDiscoveryOnAMergeCommit:
    def test_a_merge_commit_reviews_every_file_the_branch_changed(self, pr_repo):
        _repo, merge, _head = pr_repo
        assert set(_discover(merge)["expanded_paths"]) == {"first.py", "second.py"}, (
            "diff-tree on a merge commit printed nothing, so the gate reviewed "
            "an empty subject. It must diff against the first parent."
        )

    def test_the_first_parent_side_is_not_reviewed(self, pr_repo):
        """What main did meanwhile is not part of the PR."""
        _repo, merge, _head = pr_repo
        assert "unrelated_on_main.py" not in _discover(merge)["expanded_paths"]

    def test_an_ordinary_commit_is_unchanged(self, pr_repo):
        _repo, _merge, head = pr_repo
        assert _discover(head)["expanded_paths"] == ["second.py"]

    def test_the_receipt_agrees_with_what_was_fetched(self, pr_repo):
        _repo, merge, _head = pr_repo
        meta = _discover(merge)
        assert set(meta["coverage"]["reviewed"]) == {"first.py", "second.py"}


@pytest.fixture
def binary_only_repo(tmp_path, monkeypatch):
    repo = tmp_path / "bin"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "root")
    (repo / "logo.png").write_bytes(b"\x89PNG\x00\x00\x0dIHDR\x00\x00\x00\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "binary only")
    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, _git(repo, "rev-parse", "HEAD")


def _verify(sha, target_paths=None):
    from llm_council.verification.api import VerifyRequest, run_verification

    store = MagicMock()
    store.create_verification_directory.return_value = pathlib.Path("/tmp/council-704")

    async def _council_must_not_run(*_a, **_k):
        raise AssertionError("the council ran over an empty subject")

    with patch("llm_council.verification.api._run_verification_pipeline", _council_must_not_run):
        return asyncio.run(
            run_verification(VerifyRequest(snapshot_id=sha, target_paths=target_paths), store)
        )


class TestAnEmptySubjectIsAnErrorNotAVerdict:
    def test_nothing_reviewable_stops_before_the_council_runs(self, binary_only_repo):
        _repo, sha = binary_only_repo
        result = _verify(sha)
        assert result["error"] == "no_reviewable_content"
        assert result["verdict"] == "unclear"
        assert result["confidence"] == 0.0

    def test_the_result_names_the_snapshot_and_what_was_omitted(self, binary_only_repo):
        _repo, sha = binary_only_repo
        result = _verify(sha)
        assert sha in result["rationale"]
        assert "logo.png" in result["rationale"]

    def test_the_result_carries_its_coverage_receipt(self, binary_only_repo):
        _repo, sha = binary_only_repo
        result = _verify(sha)
        assert result["coverage"]["reviewed"] == []
        assert [o["path"] for o in result["coverage"]["omitted"]] == ["logo.png"]

    def test_an_explicit_empty_list_is_still_honoured(self, binary_only_repo):
        """#584: `target_paths=[]` means "review zero files" (e.g. evidence
        only). The caller asked for it, so it is not this error."""
        _repo, sha = binary_only_repo
        # Through run_verification, where the guard lives: with `[]` the run
        # must get PAST the guard and reach the (patched, raising) pipeline. A
        # regression to a truthiness check would return the error instead.
        with pytest.raises(AssertionError, match="council ran"):
            _verify(sha, target_paths=[])


class TestTheGateCannotPassOverNothing:
    def _gate(self, result):
        from llm_council.cli import run_gate

        async def fake(request, store):
            return result

        with (
            patch("llm_council.verification.api.run_verification", fake),
            patch("llm_council.verification.transcript.create_transcript_store", MagicMock()),
        ):
            return run_gate(snapshot="abc1234")

    def test_an_empty_subject_exits_3_which_the_action_treats_as_an_error(self, capsys):
        code = self._gate(
            {
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
                "error": "no_reviewable_content",
                "rationale": "nothing resolved",
                "rubric_scores": {},
                "blocking_issues": [],
                "transcript_location": "/tmp/t",
            }
        )
        assert code == 3, (
            "exit 2 is UNCLEAR, which llm-council-action turns into a PASSING "
            "check with a warning. A gate that reviewed nothing must not pass."
        )
        assert "did not run" in capsys.readouterr().out

    def test_the_output_names_the_files_reviewed(self, capsys):
        """The acceptance test in #704: the step summary names the files."""
        self._gate(
            {
                "verdict": "pass",
                "confidence": 0.9,
                "exit_code": 0,
                "rationale": "fine",
                "rubric_scores": {},
                "blocking_issues": [],
                "transcript_location": "/tmp/t",
                "coverage": {
                    "reviewed": ["src/a.py", "src/b.py"],
                    "omitted": [{"path": "logo.png", "reason": "binary", "origin": "discovered"}],
                },
            }
        )
        out = capsys.readouterr().out
        assert "Files reviewed (2)" in out
        assert "src/a.py" in out and "src/b.py" in out
        assert "logo.png" in out


class TestTheWorkflowGatesTheFixedCode:
    WORKFLOW = pathlib.Path(__file__).resolve().parent.parent / ".github/workflows/council-gate.yml"

    def test_the_gate_installs_a_version_that_contains_this_fix(self):
        """The action installs llm-council-core from PyPI, defaulting to an old
        pin. Without an explicit `version:` the fix above never reaches the
        gate that needed it."""
        import yaml

        workflow = yaml.safe_load(self.WORKFLOW.read_text())
        steps = workflow["jobs"]["quality-gate"]["steps"]
        gate = next(s for s in steps if "llm-council-action" in s.get("uses", ""))
        assert gate["with"]["version"] == "latest"


@pytest.fixture
def root_commit_repo(tmp_path, monkeypatch):
    repo = tmp_path / "root"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "main.py").write_text("print('hi')\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "root")
    monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
    monkeypatch.chdir(repo)
    return repo, _git(repo, "rev-parse", "HEAD")


class TestGateRound1:
    """Council gate on #710, round 1."""

    def test_a_root_commit_reviews_the_files_it_added(self, root_commit_repo):
        """A root commit has no `^1`. It did add files, and those are its
        changes; reviewing nothing would now be a hard error."""
        _repo, sha = root_commit_repo
        assert _discover(sha)["expanded_paths"] == ["main.py"]

    def test_a_shallow_clone_reviews_nothing_and_says_why(self, pr_repo, tmp_path, monkeypatch):
        """A real `--depth 1` clone, as `actions/checkout` makes by default.
        The merge commit is the shallow boundary and LOOKS parentless. A
        `--root` fallback would report its whole tree: review everything, hit
        the input cap, exit 2, pass. It must review nothing and say why."""
        repo, merge, _head = pr_repo
        shallow = tmp_path / "shallow"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow)],
            check=True,
            capture_output=True,
        )
        assert _git(shallow, "rev-parse", "HEAD") == merge
        monkeypatch.setattr(file_ops, "_cached_git_root", str(shallow))
        monkeypatch.chdir(shallow)

        meta = _discover(merge)
        assert meta["expanded_paths"] == []
        assert "shallow clone" in " ".join(meta["expansion_warnings"])

    def test_the_nothing_reviewed_banner_shows_the_discovery_warning(self):
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {
                "error": "no_reviewable_content",
                "rationale": "nothing",
                "expansion_warnings": ["could not diff abc against its first parent: shallow clone"],
            }
        )
        assert "shallow clone" in text

    def test_the_full_formatter_survives_null_fields(self):
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {"verdict": None, "confidence": None, "rationale": None, "rubric_scores": None}
        )
        assert "UNCLEAR" in text

    def test_the_nothing_reviewed_output_names_transcript_and_omissions(self):
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {
                "error": "no_reviewable_content",
                "rationale": "nothing",
                "transcript_location": "/tmp/t704",
                "coverage": {
                    "reviewed": [],
                    "omitted": [{"path": "logo.png", "reason": "binary", "origin": "discovered"}],
                },
            }
        )
        assert "/tmp/t704" in text
        assert "logo.png (binary)" in text

    def test_the_compact_form_does_not_read_as_a_verdict(self):
        from llm_council.verification.formatting import format_verification_result_compact

        line = format_verification_result_compact(
            {"error": "no_reviewable_content", "verdict": "unclear", "exit_code": 2}
        )
        assert "NOTHING REVIEWED" in line
        assert "UNCLEAR" not in line

    def test_the_compact_form_survives_a_null_verdict_and_confidence(self):
        from llm_council.verification.formatting import format_verification_result_compact

        line = format_verification_result_compact({"verdict": None, "confidence": None})
        assert "UNCLEAR" in line

    def test_a_truncated_omission_list_says_so(self):
        from llm_council.verification.formatting import format_verification_result

        omitted = [{"path": f"f{i}.png", "reason": "binary"} for i in range(25)]
        text = format_verification_result(
            {"verdict": "pass", "confidence": 0.9, "coverage": {"reviewed": ["a.py"], "omitted": omitted}}
        )
        assert "and 5 more" in text


class TestGateRound3:
    """Council gate on #710, round 3: the formatter must survive every
    present-but-null field, and nothing without a verdict may read as one."""

    def test_every_nullable_field_explicitly_null(self):
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {
                "verdict": None,
                "confidence": None,
                "exit_code": None,
                "rationale": None,
                "rubric_scores": None,
                "blocking_issues": None,
                "transcript_location": None,
                "coverage": None,
                "expansion_warnings": None,
            }
        )
        assert "UNCLEAR" in text
        assert "Transcript**: None" not in text

    def test_malformed_blocking_issues_do_not_crash(self):
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {"verdict": "fail", "blocking_issues": ["plain string", {"severity": None, "description": "d"}]}
        )
        assert "plain string" in text
        assert "UNKNOWN" in text

    @pytest.mark.parametrize("error", ["discovery_failed", "some_future_marker"])
    def test_an_unknown_error_marker_is_not_formatted_as_a_verdict(self, error):
        from llm_council.verification.formatting import (
            format_verification_result,
            format_verification_result_compact,
        )

        result = {"error": error, "verdict": "unclear", "exit_code": 2}
        text = format_verification_result(result)
        assert "DID NOT RUN" in text and "| Verdict |" not in text
        assert "DID NOT RUN" in format_verification_result_compact(result)

    def test_discovery_warnings_show_on_an_ordinary_verdict_too(self):
        """A root-commit fallback still resolves files; the reader must see
        discovery was degraded."""
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {
                "verdict": "pass",
                "confidence": 0.9,
                "expansion_warnings": ["abc has no first parent (a root commit); reviewing the files it added"],
            }
        )
        assert "root commit" in text

    def test_a_long_warning_list_says_how_many_more(self):
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {"error": "no_reviewable_content", "expansion_warnings": [f"w{i}" for i in range(13)]}
        )
        assert "and 3 more" in text


class TestGateRound4:
    """Council gate on #710, round 4 (PASS); its two remaining majors."""

    def test_the_compact_form_normalises_a_null_exit_code(self):
        from llm_council.verification.formatting import format_verification_result_compact

        line = format_verification_result_compact({"verdict": "pass", "exit_code": None})
        assert "exit=None" not in line and "exit=2" in line

    def test_a_malformed_receipt_cannot_crash_the_banner_that_reports_it(self):
        from llm_council.verification.formatting import format_verification_result

        text = format_verification_result(
            {
                "error": "no_reviewable_content",
                "coverage": {"reviewed": "a.py", "omitted": ["x.png", None, {"path": "y.bin", "reason": "binary"}]},
            }
        )
        assert "NOTHING REVIEWED" in text
        assert "y.bin (binary)" in text
