"""ADR-048 P3: publication page + DeepEval/RAGAS bridges (#420). No spend."""

import json

import pytest

from llm_council.bench.adapters import (
    council_to_ragas_row,
    make_council_eval_callable,
)
from llm_council.bench.harness import BenchRun, ItemResult
from llm_council.bench.publication import render_results_page, write_results_page


def _run():
    return BenchRun(
        started_at="2026-07-03T14:00:00+00:00",
        items_total=2,
        items_run=2,
        items_passed=1,
        total_cost_usd=0.1234,
        cost_known=True,
        results=[
            ItemResult(item_id="a", domain="coding", ok=True, score=0.8, cost_usd=0.06, cost_known=True),
            ItemResult(item_id="b", domain="factual", ok=False, failures=["missing_any_of:['x']"], cost_usd=0.06, cost_known=True),
        ],
    )


class TestResultsPage:
    def test_reproducibility_fields_present(self):
        page = render_results_page(_run(), dataset_version="v1", matrix_rows=None)
        for needle in ("v1", "2026-07-03", "$0.1234", "METHODOLOGY", "1/2"):
            assert needle in page, needle

    def test_matrix_table_embedded_when_given(self):
        rows = [{
            "config": "council", "kind": "council", "items_run": 2,
            "pass_rate": 0.5, "cost_usd": 0.12, "cost_known": True,
            "quality_per_dollar": 4.167, "aborted": None,
        }]
        page = render_results_page(_run(), dataset_version="v1", matrix_rows=rows)
        assert "quality/$" in page

    def test_write_page_regenerates_file(self, tmp_path):
        out = tmp_path / "bench-results.md"
        write_results_page(_run(), out, dataset_version="v1")
        first = out.read_text()
        assert "Bench Results" in first
        write_results_page(_run(), out, dataset_version="v1")  # idempotent regen
        assert out.read_text() == first


class TestDeepEvalBridge:
    @pytest.mark.asyncio
    async def test_callable_round_trip(self):
        async def fake_council(prompt):
            return {"synthesis": f"answer to: {prompt}", "metadata": {}}

        generate = make_council_eval_callable(council_runner=fake_council)
        out = await generate("what is 2+2?")
        assert out == "answer to: what is 2+2?"


class TestRagasBridge:
    def test_row_shape(self):
        result = {
            "synthesis": "the answer",
            "model_responses": {
                "m/a": {"status": "ok", "response": "draft a"},
                "m/b": {"status": "ok", "response": "draft b"},
                "m/c": {"status": "error"},
            },
            "metadata": {},
        }
        row = council_to_ragas_row("the question", result)
        assert row["question"] == "the question"
        assert row["answer"] == "the answer"
        # Stage-1 drafts serve as retrieved contexts; failures excluded.
        assert row["contexts"] == ["draft a", "draft b"]


class TestCouncilRound1:
    def test_pipes_in_failures_escaped(self):
        # #441 r1: an unescaped '|' in a failure message splits the row.
        run = BenchRun(
            started_at="2026-07-03T14:00:00+00:00",
            items_total=1, items_run=1, items_passed=0,
            total_cost_usd=0.0, cost_known=True,
            results=[ItemResult(
                item_id="a", domain="coding", ok=False,
                failures=["missing_any_of:['x|y']"],
            )],
        )
        import re

        page = render_results_page(run, dataset_version="v1")
        row = [line for line in page.splitlines() if line.startswith("| a |")][0]
        # 5 columns => exactly 6 UNESCAPED pipes; the content pipe is escaped.
        assert len(re.findall(r"(?<!\\)\|", row)) == 6
        assert "x\\|y" in row

    def test_written_page_is_utf8(self, tmp_path):
        run = _run()
        run.results[1].failures = ["café — non-ascii"]  # the FAILING item renders failures
        out = tmp_path / "r.md"
        write_results_page(run, out, dataset_version="v1")
        assert "café" in out.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_sync_runner_accepted(self):
        # #441 r2: eval harnesses may inject a plain function.
        def sync_runner(prompt):
            return {"synthesis": "sync answer"}

        generate = make_council_eval_callable(council_runner=sync_runner)
        assert await generate("q") == "sync answer"
