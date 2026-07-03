"""ADR-048 P1: golden-dataset drift harness (#418).

Unit-tested with mocked councils — NO live spend in CI. Spend-cap abort,
monthly guard, envelope semantics, baseline drift, exit codes 0/1/2.
"""

import json
from pathlib import Path

import pytest

from llm_council.bench import (
    BenchItem,
    check_envelope,
    compare_to_baseline,
    format_report,
    load_dataset,
    month_to_date_spend,
    run_bench,
    set_baseline,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _fake_result(text, score=0.8, cost=0.01):
    return {
        "synthesis": text,
        "metadata": {
            "aggregate_rankings": [{"model": "m", "average_score": score}],
            "usage": {"total": {"cost_usd": cost, "cost_known": True}},
        },
    }


def _write_item(d, iid, must=(("hello",),), min_score=0.3):
    (d / f"{iid}.json").write_text(
        json.dumps(
            {
                "id": iid,
                "domain": "factual",
                "prompt": f"say hello ({iid})",
                "envelope": {"must_contain": [list(g) for g in must], "min_score": min_score},
            }
        )
    )


class TestDataset:
    def test_committed_v1_loads_and_validates(self):
        items = load_dataset(REPO_ROOT / "bench" / "dataset" / "v1")
        assert len(items) >= 20
        domains = {i.domain for i in items}
        assert domains == {"coding", "reasoning", "factual", "judgment"}

    def test_malformed_item_fails_fast(self, tmp_path):
        (tmp_path / "bad.json").write_text('{"id": "x"}')
        with pytest.raises(ValueError, match="missing"):
            load_dataset(tmp_path)

    def test_empty_dataset_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="no dataset items"):
            load_dataset(tmp_path)


class TestEnvelope:
    def test_any_of_groups(self):
        item = BenchItem(
            id="x", domain="factual", prompt="p",
            envelope={"must_contain": [["fizz", "buzz"], ["required"]]},
        )
        assert check_envelope(item, "FIZZ and the REQUIRED word", None) == []
        fails = check_envelope(item, "only fizz here", None)
        assert len(fails) == 1 and "required" in fails[0]

    def test_score_floor(self):
        item = BenchItem(id="x", domain="f", prompt="p", envelope={"min_score": 0.5})
        assert check_envelope(item, "text", 0.6) == []
        assert check_envelope(item, "text", 0.4) != []
        assert check_envelope(item, "text", None) == []  # unknown score never fails


class TestRun:
    @pytest.mark.asyncio
    async def test_all_pass_exit_0(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")
        _write_item(d, "b")

        async def runner(prompt):
            return _fake_result("hello world")

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=runner
        )
        assert run.exit_code == 0
        assert run.items_passed == 2

    @pytest.mark.asyncio
    async def test_drift_exit_1(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a", must=(("absent-token",),))

        async def runner(prompt):
            return _fake_result("does not contain it")

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=runner
        )
        assert run.exit_code == 1

    @pytest.mark.asyncio
    async def test_spend_cap_aborts_gracefully_exit_2(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        for i in range(4):
            _write_item(d, f"i{i}")

        async def runner(prompt):
            return _fake_result("hello", cost=0.60)  # 2 items cross a $1 cap

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs",
            council_runner=runner, max_usd=1.00,
        )
        assert run.exit_code == 2
        assert run.aborted and "per_run_cap" in run.aborted
        assert run.items_run == 2  # partial results kept
        assert len(run.results) == 2

    @pytest.mark.asyncio
    async def test_monthly_guard_refuses_run(self, tmp_path, monkeypatch):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")
        runs = tmp_path / "runs"
        runs.mkdir()
        from datetime import datetime, timezone

        stamp = datetime.now(timezone.utc).isoformat()
        (runs / "run-old.json").write_text(
            json.dumps({"started_at": stamp, "total_cost_usd": 31.0})
        )

        called = []

        async def runner(prompt):
            called.append(prompt)
            return _fake_result("hello")

        run = await run_bench(dataset_dir=d, runs_dir=runs, council_runner=runner)
        assert run.exit_code == 2
        assert "monthly_guard" in run.aborted
        assert called == []  # zero spend

    @pytest.mark.asyncio
    async def test_council_error_marks_item_failed_not_crash(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def runner(prompt):
            raise RuntimeError("gateway down")

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=runner
        )
        assert run.exit_code == 1
        assert "council_error" in run.results[0].failures[0]

    @pytest.mark.asyncio
    async def test_run_artefact_persisted(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def runner(prompt):
            return _fake_result("hello", cost=0.02)

        runs = tmp_path / "runs"
        await run_bench(dataset_dir=d, runs_dir=runs, council_runner=runner)
        artefacts = list(runs.glob("run-*.json"))
        assert len(artefacts) == 1
        assert month_to_date_spend(runs) == pytest.approx(0.02)


class TestBaseline:
    @pytest.mark.asyncio
    async def test_baseline_round_trip_and_regressions(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def good(prompt):
            return _fake_result("hello")

        async def bad(prompt):
            return _fake_result("nope")

        base_run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=good
        )
        bp = set_baseline(base_run, tmp_path / "baseline.json")
        drifted = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=bad
        )
        cmp = compare_to_baseline(drifted, bp)
        assert cmp["regressions"] == ["a"]
        text = format_report(drifted, cmp)
        assert "REGRESSIONS" in text
        assert "exit code 1" in text

    def test_missing_baseline_reported(self, tmp_path):
        from llm_council.bench.harness import BenchRun

        run = BenchRun(
            started_at="t", items_total=0, items_run=0,
            items_passed=0, total_cost_usd=0.0, cost_known=False,
        )
        cmp = compare_to_baseline(run, tmp_path / "missing.json")
        assert cmp == {"baseline": None}
        assert "No committed baseline" in format_report(run, cmp)


class TestCouncilRound1:
    @pytest.mark.asyncio
    async def test_unknown_cost_items_charge_the_cap_conservatively(self, tmp_path, monkeypatch):
        # #439 r1: items whose cost the provider didn't report counted $0
        # against the cap — unbounded worst-case spend. Unknown-cost items
        # now charge a conservative default against CAP ACCOUNTING ONLY
        # (reported spend stays actuals — never fabricated).
        monkeypatch.setenv("LLM_COUNCIL_BENCH_UNKNOWN_ITEM_USD", "0.50")
        d = tmp_path / "ds"
        d.mkdir()
        for i in range(4):
            _write_item(d, f"i{i}")

        async def runner(prompt):
            r = _fake_result("hello")
            r["metadata"]["usage"]["total"] = {}  # no cost reported
            return r

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs",
            council_runner=runner, max_usd=1.00,
        )
        # 2 x $0.50 conservative charges reach the $1 cap => abort partial.
        assert run.exit_code == 2
        assert run.items_run == 2
        assert run.total_cost_usd == 0.0  # actuals never fabricated

    def test_corrupt_baseline_reported_not_crash(self, tmp_path):
        from llm_council.bench.harness import BenchRun

        bp = tmp_path / "baseline.json"
        bp.write_text("{corrupt")
        run = BenchRun(
            started_at="t", items_total=0, items_run=0,
            items_passed=0, total_cost_usd=0.0, cost_known=False,
        )
        cmp = compare_to_baseline(run, bp)
        assert cmp == {"baseline": None}
