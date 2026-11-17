"""#747: what the council is shown must fit, and must be the code.

Three defects made the CI gate review no source code from 28 September 2026:

- files could fill the whole tier cap, and the rest of the prompt was added on
  top, so a change of about the cap's size was refused as ``input_too_large``;
- files were taken in path order, so ``CHANGELOG.md`` / ``CLAUDE.md`` /
  ``README.md`` used the budget before ``src/`` was reached;
- the first file that did not fit ended the review, and the receipt still
  listed every selected file as reviewed.

No network, no git: the per-file fetch is replaced.
"""

import ast
import pathlib
from typing import Dict
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from llm_council.verification import file_ops, prompt, subject_budget
from llm_council.verification.constants import TIER_MAX_CHARS
from llm_council.verification.coverage import DEFAULT_ACK_REASONS, clamping_omissions
from llm_council.verification.subject_budget import (
    assemble_subject,
    order_for_review,
    review_priority,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


def _fetcher(files: Dict[str, str]):
    async def fetch(snapshot_id, path, max_file_chars=None):
        return files[path], False

    return fetch


async def _fetch_with_metadata(files: Dict[str, str], target_paths, tier="balanced", **kw):
    async def expand(snapshot_id, paths):
        return list(paths), False, [], []

    with (
        patch.object(file_ops, "_fetch_file_at_commit_async", side_effect=_fetcher(files)),
        patch.object(file_ops, "_expand_target_paths", side_effect=expand),
        patch.object(file_ops, "_get_git_root_async", new_callable=AsyncMock, return_value="/r"),
    ):
        return await file_ops._fetch_files_for_verification_async_with_metadata(
            "abc123", target_paths, tier=tier, **kw
        )


class TestReviewOrder:
    @pytest.mark.parametrize(
        "path,rank",
        [
            ("src/llm_council/council.py", 0),
            ("deploy/railway/Dockerfile", 0),
            ("tests/test_council.py", 1),
            ("src/app/widget.test.ts", 1),
            ("pkg/server_test.go", 1),
            ("pyproject.toml", 2),
            (".github/workflows/ci.yml", 2),
            ("uv.lock", 2),
            ("CHANGELOG.md", 3),
            ("CLAUDE.md", 3),
            ("docs/guides/verify.md", 3),
            ("docs/conf.py", 3),
            ("LICENSE", 3),
        ],
    )
    def test_rank(self, path, rank):
        assert review_priority(path) == rank

    def test_source_then_tests_then_config_then_docs(self):
        paths = ["CHANGELOG.md", "CLAUDE.md", "pyproject.toml", "src/a.py", "tests/test_a.py"]
        assert order_for_review(paths) == [
            "src/a.py",
            "tests/test_a.py",
            "pyproject.toml",
            "CHANGELOG.md",
            "CLAUDE.md",
        ]

    def test_order_within_a_rank_is_kept(self):
        assert order_for_review(["src/z.py", "src/a.py"]) == ["src/z.py", "src/a.py"]


class TestFit:
    async def test_large_docs_no_longer_crowd_out_the_code(self):
        # The #744 shape: a changelog that fills the budget alone, sorted first.
        files = {"CHANGELOG.md": "c" * 218_000, "src/a.py": "CODE_A", "tests/test_a.py": "TEST_A"}
        content, meta = await _fetch_with_metadata(files, list(files))
        assert "CODE_A" in content and "TEST_A" in content
        assert "### CHANGELOG.md" not in content
        assert meta["coverage"]["reviewed"] == ["src/a.py", "tests/test_a.py"]

    async def test_a_file_that_does_not_fit_does_not_end_the_review(self):
        files = {"src/a.py": "a" * 20_000, "src/big.py": "b" * 20_000, "src/c.py": "SMALL_C"}
        content, _ = await _fetch_with_metadata(files, list(files))
        assert "### src/a.py" in content
        assert "### src/big.py" not in content
        assert "SMALL_C" in content

    @pytest.mark.parametrize("budget", [500, 5_000, 29_000])
    async def test_output_never_exceeds_the_room_given(self, budget):
        files = {f"src/f{i}.py": "x" * 1_700 for i in range(40)}
        text, _, not_fitted = await assemble_subject(
            "abc", list(files), "balanced", _fetcher(files), budget
        )
        assert len(text) <= budget
        assert not_fitted

    async def test_a_single_oversized_file_is_cut_to_fit_not_dropped(self):
        files = {"src/huge.py": "h" * 90_000}
        text, warnings, not_fitted = await assemble_subject(
            "abc", ["src/huge.py"], "balanced", _fetcher(files), 10_000
        )
        assert len(text) <= 10_000
        assert text.startswith("### src/huge.py")
        assert not not_fitted
        assert any("src/huge.py" in w and "truncated" in w for w in warnings)

    async def test_small_inputs_render_exactly_as_before(self):
        # Prompt-cache byte stability (ADR-049): same headings, fences, joins.
        files = {"src/a.py": "A", "src/b.py": "B"}
        text, warnings, not_fitted = await assemble_subject(
            "abc", list(files), "balanced", _fetcher(files)
        )
        assert text == "### src/a.py\n```\nA\n```\n\n### src/b.py\n```\nB\n```"
        assert warnings == [] and not_fitted == []


class TestReceiptIsHonest:
    async def test_unfitted_files_are_omitted_not_reviewed(self):
        files = {"CHANGELOG.md": "c" * 218_000, "src/a.py": "CODE"}
        _, meta = await _fetch_with_metadata(files, list(files))
        receipt = meta["coverage"]
        assert receipt["reviewed"] == ["src/a.py"]
        assert {"path": "CHANGELOG.md", "reason": "too_large", "origin": "explicit"} in receipt[
            "omitted"
        ]
        assert receipt["conservation_ok"] is True
        assert any("CHANGELOG.md" in w and "NOT reviewed" in w for w in meta["expansion_warnings"])

    async def test_a_named_file_that_did_not_fit_clamps_a_pass(self):
        files = {"CHANGELOG.md": "c" * 218_000, "src/a.py": "CODE"}
        _, meta = await _fetch_with_metadata(files, list(files))
        assert meta["coverage"]["explicit_omitted"] is True
        assert clamping_omissions(meta["coverage"], DEFAULT_ACK_REASONS)

    def test_a_discovered_file_that_did_not_fit_is_acknowledged(self):
        # The gate's case: nobody named CHANGELOG.md, the diff contained it.
        receipt = subject_budget.coverage_receipt(
            None, ["src/a.py", "CHANGELOG.md"], [], False, ["CHANGELOG.md"]
        )
        assert receipt["reviewed"] == ["src/a.py"]
        assert receipt["explicit_omitted"] is False
        assert clamping_omissions(receipt, DEFAULT_ACK_REASONS) == []


class TestWholePromptFitsTheTier:
    """The original refusal: files sized against the cap, prompt added on top."""

    @pytest.mark.parametrize("tier", ["quick", "balanced", "high"])
    async def test_prompt_is_within_the_cap_however_much_changed(self, tier):
        files = {f"src/f{i}.py": "x" * 4_000 for i in range(30)}

        async def expand(snapshot_id, paths):
            return list(paths), False, [], []

        with (
            patch.object(file_ops, "_fetch_file_at_commit_async", side_effect=_fetcher(files)),
            patch.object(file_ops, "_expand_target_paths", side_effect=expand),
            patch.object(
                file_ops, "_get_git_root_async", new_callable=AsyncMock, return_value="/r"
            ),
        ):
            text, info = await prompt._build_verification_prompt(
                "abc123", list(files), rubric_focus="Security", tier=tier
            )
        assert len(text) <= TIER_MAX_CHARS[tier]
        # ...and the room is used, not thrown away.
        assert len(text) > TIER_MAX_CHARS[tier] - 4_500
        assert info["expansion"]["coverage"]["reviewed"]


class TestWiring:
    def test_the_fitter_has_exactly_one_caller(self):
        # Companion to TestArchitectureNoBypass: the fitter is handed a fetch
        # closure, so it must only be reachable from the batch fetcher.
        pkg = pathlib.Path(file_ops.__file__).parent.parent
        callers = []
        for py in pkg.rglob("*.py"):
            for node in ast.walk(ast.parse(py.read_text())):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                    if name == "assemble_subject":
                        callers.append(py.name)
        assert callers == ["file_ops.py"]

    def test_ci_gate_fails_when_the_council_did_not_review(self):
        # An UNCLEAR gate (no credit, input refused, timeout) used to show a
        # green tick on the PR.
        workflow = yaml.safe_load((REPO / ".github/workflows/council-gate.yml").read_text())
        steps = workflow["jobs"]["quality-gate"]["steps"]
        gate = next(s for s in steps if "llm-council-action" in str(s.get("uses", "")))
        assert gate["with"]["fail-on-unclear"] is True
