"""ADR-048 P1: golden-dataset drift harness (#418).

Unit-tested with mocked councils — NO live spend in CI. Spend-cap abort,
monthly guard, envelope semantics, baseline drift, exit codes 0/1/2.
"""

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

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

    def test_word_boundary_no_substring_false_positive(self):
        # #506: "major" must NOT be satisfied by "majority" (substring bug).
        item = BenchItem(
            id="x", domain="factual", prompt="p",
            envelope={"must_contain": [["major"]]},
        )
        fails = check_envelope(item, "the majority voted", None)
        assert len(fails) == 1 and "major" in fails[0]
        # but a real whole-word "major" still passes
        assert check_envelope(item, "a major version bump", None) == []

    def test_word_boundary_numeric_token(self):
        # #506: "66" must not match "1966".
        item = BenchItem(
            id="x", domain="reasoning", prompt="p",
            envelope={"must_contain": [["66"]]},
        )
        assert check_envelope(item, "released in 1966", None) != []
        assert check_envelope(item, "the answer is 66 percent", None) == []

    def test_punctuation_token_still_matches(self):
        # #506: a token with no word boundary (e.g. "?") must still match by
        # presence — word-boundary anchoring only applies at word-char edges.
        item = BenchItem(
            id="x", domain="coding", prompt="p",
            envelope={"must_contain": [["?", "parameter"]]},
        )
        assert check_envelope(item, "use cur.execute(sql, (x,)) with a ?", None) == []
        # dotted/punctuated multi-char token matches as a whole word
        item2 = BenchItem(
            id="y", domain="coding", prompt="p",
            envelope={"must_contain": [["os.system"]]},
        )
        assert check_envelope(item2, "avoid os.system on user input", None) == []
        assert check_envelope(item2, "the ecosystem is large", None) != []

    def test_punctuation_token_matches_after_a_word(self):
        # Round 9 review: "?" (a REAL v1 token, code-sql-injection.json) is a
        # LIVE regression from round 4's "fix" for a synthetic "c++abc" edge
        # case — requiring no word char immediately BEFORE a trailing "?"
        # broke the overwhelmingly common real position of "?": right after a
        # word ("...use a parameter?"). Punctuation-edge tokens get no
        # boundary requirement at all; a false-positive risk on a purely
        # hypothetical token ("c++" is not in the dataset) is accepted in
        # exchange for correct matching of the real one.
        item = BenchItem(
            id="x", domain="coding", prompt="p",
            envelope={"must_contain": [["?"]]},
        )
        assert check_envelope(item, "should you use a parameter?", None) == []
        assert check_envelope(item, "use a ? placeholder", None) == []
        assert check_envelope(item, "no punctuation here at all", None) != []

    def test_score_floor(self):
        item = BenchItem(id="x", domain="f", prompt="p", envelope={"min_score": 0.5})
        assert check_envelope(item, "text", 0.6) == []
        assert check_envelope(item, "text", 0.4) != []
        # #439 r2: a floor with NO observable score is itself drift — the
        # council stopped producing the signal the envelope guards.
        assert check_envelope(item, "text", None) == ["score_unavailable"]
        no_floor = BenchItem(id="y", domain="f", prompt="p", envelope={})
        assert check_envelope(no_floor, "text", None) == []


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
    async def test_final_item_overshoot_not_silent_exit0(self, tmp_path):
        # #510/#511 (Council critical): the between-item cap check never sees
        # an overshoot caused by the FINAL item — a 1-item run over cap used to
        # complete as a silent exit-0. It must signal exit 2 with a cap reason.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "only")

        async def runner(prompt):
            return _fake_result("hello", cost=5.00)  # single item blows the cap

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs",
            council_runner=runner, max_usd=1.00,
        )
        assert run.items_run == 1  # the item did run (cap is between-item)
        assert run.aborted and "per_run_cap" in run.aborted
        assert run.exit_code == 2  # not a silent 0

    @pytest.mark.asyncio
    async def test_unknown_items_id_raises(self, tmp_path):
        # #508: a typo'd --items id must not silently produce a green 0/0 run.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "real")

        async def runner(prompt):
            return _fake_result("hello")

        with pytest.raises(ValueError, match="unknown --items"):
            await run_bench(
                dataset_dir=d, runs_dir=tmp_path / "runs",
                council_runner=runner, items_filter=["typo"],
            )

    @pytest.mark.asyncio
    async def test_empty_dataset_is_rejected_not_green(self, tmp_path):
        # #508: an empty dataset must not silently produce a green run. It is
        # rejected at load (load_dataset raises); the run-level items_run==0
        # guard is defence-in-depth for any other zero-item path.
        d = tmp_path / "ds"
        d.mkdir()  # no items

        async def runner(prompt):
            return _fake_result("hello")

        with pytest.raises(ValueError):
            await run_bench(
                dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=runner
            )

    def test_month_to_date_skips_unreadable_artefact_not_silent(self, tmp_path, caplog):
        # Council critical: a corrupt artefact must not silently vanish from the
        # financial guard — it's skipped WITH a warning, and readable spend still
        # counts (no crash, no fail-open silence).
        runs = tmp_path / "runs"
        runs.mkdir()
        prefix = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).strftime("%Y-%m")
        (runs / "run-good.json").write_text(
            json.dumps({"started_at": f"{prefix}-01T00:00:00+00:00", "cap_charged_usd": 1.5})
        )
        (runs / "run-corrupt.json").write_text("{not valid json")
        # null spend must not crash the tally either
        (runs / "run-null.json").write_text(
            json.dumps({"started_at": f"{prefix}-02T00:00:00+00:00", "cap_charged_usd": None,
                        "total_cost_usd": 0.5})
        )
        with caplog.at_level("WARNING"):
            total = month_to_date_spend(runs)
        assert total == 2.0  # 1.5 (good) + 0.5 (null→total fallback); corrupt skipped
        assert any("unreadable" in r.message for r in caplog.records)

    def test_format_report_shows_effective_cap(self):
        from llm_council.bench.harness import BenchRun

        run = BenchRun(
            started_at="2026-07-07T00:00:00+00:00",
            items_total=1, items_run=1, items_passed=1,
            total_cost_usd=0.1, cost_known=True, cap_usd=0.75,
        )
        report = format_report(run, {"baseline": None}, "md")
        assert "per-run cap $0.75" in report  # #509: effective, not env default

    @pytest.mark.asyncio
    async def test_filtered_run_flag_and_baseline_refuses(self, tmp_path):
        # #517: a --items-scoped run must be flagged, and set_baseline must
        # refuse it (silently shrinking baseline coverage is a real gap, but
        # a MAJOR one, not data-loss/security/crash-critical).
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")
        _write_item(d, "b")

        async def runner(prompt):
            return _fake_result("hello")

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs",
            council_runner=runner, items_filter=["a"],
        )
        assert run.filtered is True
        with pytest.raises(ValueError, match="filtered"):
            set_baseline(run, tmp_path / "baseline.json")

        # A full (unfiltered) run is NOT flagged and baselines normally.
        full_run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs2", council_runner=runner
        )
        assert full_run.filtered is False
        set_baseline(full_run, tmp_path / "baseline2.json")  # must not raise

    @pytest.mark.skipif(fcntl is None, reason="fcntl is Unix-only")
    @pytest.mark.asyncio
    async def test_monthly_guard_lock_is_exclusive(self, tmp_path):
        # #516: the lock must be a REAL OS-level exclusive lock on a shared
        # file, not just plumbing — probe it directly rather than relying on
        # asyncio orchestration (which can't reliably force the TOCTOU race).
        from llm_council.bench.harness import _monthly_guard_lock

        async with _monthly_guard_lock(tmp_path):
            lock_path = tmp_path / ".monthly-guard.lock"
            assert lock_path.exists()
            # A second, independent open on the SAME lock file must fail to
            # acquire non-blocking while the context manager holds it.
            with open(lock_path, "a+") as probe:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Released on exit: the probe can now acquire it.
        with open(lock_path, "a+") as probe:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(probe.fileno(), fcntl.LOCK_UN)

    @pytest.mark.asyncio
    async def test_monthly_guard_lock_does_not_block_event_loop(self, tmp_path):
        # Round 6 review: fcntl.flock is a blocking syscall; a naive
        # synchronous acquire held across awaits would, on contention, freeze
        # the WHOLE event loop (every task in the process), not just the
        # calling coroutine. Prove a concurrent heartbeat task keeps ticking
        # while _monthly_guard_lock waits on a lock held elsewhere.
        from llm_council.bench.harness import _monthly_guard_lock

        tmp_path.mkdir(parents=True, exist_ok=True)
        lock_path = tmp_path / ".monthly-guard.lock"
        holder_fh = open(lock_path, "a+")
        fcntl.flock(holder_fh.fileno(), fcntl.LOCK_EX)  # simulate another holder

        def release_after_delay():
            time.sleep(0.3)
            fcntl.flock(holder_fh.fileno(), fcntl.LOCK_UN)
            holder_fh.close()

        threading.Thread(target=release_after_delay, daemon=True).start()

        heartbeats = 0

        async def heartbeat():
            nonlocal heartbeats
            while True:
                heartbeats += 1
                await asyncio.sleep(0.02)

        hb_task = asyncio.create_task(heartbeat())
        try:
            async with _monthly_guard_lock(tmp_path):
                pass
        finally:
            hb_task.cancel()

        # ~0.3s of contention at a 0.02s heartbeat interval => many ticks if
        # the event loop stayed responsive; a blocking flock() would have
        # frozen it (heartbeats stuck at 0 or 1).
        assert heartbeats >= 5

    def test_persist_run_unique_filenames_same_second(self, tmp_path):
        # #510: whole-second stamps collided (second run overwrote the first),
        # dropping the lost run's spend from the monthly ledger.
        from llm_council.bench.harness import BenchRun, _persist_run

        runs = tmp_path / "runs"
        r1 = BenchRun(
            started_at="2026-07-07T08:21:26.111111+00:00",
            items_total=1, items_run=1, items_passed=1,
            total_cost_usd=0.5, cost_known=True,
        )
        r2 = BenchRun(
            started_at="2026-07-07T08:21:26.999999+00:00",  # same second
            items_total=1, items_run=1, items_passed=1,
            total_cost_usd=0.7, cost_known=True,
        )
        _persist_run(r1, runs)
        _persist_run(r2, runs)
        assert len(list(runs.glob("*.json"))) == 2  # both preserved

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

        run = await run_bench(
            dataset_dir=d, runs_dir=runs, council_runner=runner, max_usd=0.55
        )
        assert run.exit_code == 2
        assert "monthly_guard" in run.aborted
        assert called == []  # zero spend
        # Round 11 review: cap_usd must be populated even though the run
        # aborted before any items ran (previously only set at the end of
        # _run_items, which this path never reaches).
        assert run.cap_usd == 0.55

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
        # #507: a run where EVERY item errored is an infra/abort outcome
        # (exit 2), never envelope drift (exit 1) — a rate-limit/billing
        # lapse must not read as "quality collapsed".
        assert run.exit_code == 2
        assert run.infra_errors == 1
        assert run.items_scored == 0
        assert run.aborted and "infra_failure" in run.aborted
        assert run.results[0].is_infra is True
        assert "council_error" in run.results[0].failures[0]

    @pytest.mark.asyncio
    async def test_council_status_failed_counts_as_infra_not_drift(self, tmp_path):
        # #507 empirically-observed case: the runner does NOT raise (graceful
        # degradation — CLAUDE.md's "continue with whatever responses
        # succeed" policy) but reports total failure via metadata.status.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def runner(prompt):
            return {
                "synthesis": "Error: All models failed to respond.",
                "metadata": {"status": "failed"},
            }

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=runner
        )
        assert run.exit_code == 2  # infra/abort, not drift
        assert run.infra_errors == 1
        assert run.results[0].is_infra is True

    @pytest.mark.asyncio
    async def test_mixed_infra_and_drift_reports_both_separately(self, tmp_path):
        # #507 acceptance: "mixed run reports both counts; drift exit
        # reflects only genuinely-scored misses."
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")  # will infra-error
        _write_item(d, "b")  # will genuinely fail its envelope

        calls = {"n": 0}

        async def runner(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("gateway down")
            return _fake_result("wrong answer entirely")

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=runner
        )
        assert run.infra_errors == 1
        assert run.items_run == 2
        assert run.items_scored == 1  # only the genuinely-run item
        assert run.items_passed == 0  # that one item failed its envelope
        assert run.exit_code == 1  # DRIFT — a real miss, not infra-masked
        assert not run.aborted  # a mixed run is not itself "aborted"

    def test_format_report_surfaces_infra_errors(self):
        from llm_council.bench.harness import BenchRun, ItemResult

        run = BenchRun(
            started_at="t", items_total=1, items_run=1, items_passed=0,
            total_cost_usd=0.0, cost_known=False, infra_errors=1,
            aborted="infra_failure: 1/1 items errored",
            results=[ItemResult(
                item_id="a", domain="f", ok=False,
                failures=["council_error:boom"], is_infra=True,
            )],
        )
        report = format_report(run, {"baseline": None}, "md")
        assert "Council/infra errors: 1/1" in report
        assert "[INFRA] a" in report

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

    @pytest.mark.asyncio
    async def test_infra_error_excluded_from_baseline_items(self, tmp_path):
        # Round 10 review: set_baseline must NOT bake ok=False for an
        # infra-errored item — base.get("ok") frozen False can never satisfy
        # compare_to_baseline's "base.get('ok') and not r.ok" check, so a
        # REAL future regression on that item would be permanently
        # invisible. Excluding it (absent entry) is correctly ignored by
        # that check instead — no false record either way.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")
        _write_item(d, "b")

        calls = {"n": 0}

        async def mixed(prompt):
            calls["n"] += 1
            if calls["n"] == 2:  # "b" loads second (sorted glob) — infra-errors
                raise RuntimeError("gateway down")
            return _fake_result("hello")

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=mixed
        )
        bp = set_baseline(run, tmp_path / "baseline.json")
        baseline = json.loads(bp.read_text())
        assert "b" not in baseline["items"]  # excluded, not baked in as False
        assert "a" in baseline["items"]

        # A later GENUINE regression on "a" (which WAS properly baselined)
        # must still be detected — the fix doesn't affect non-infra items.
        async def later(prompt):
            return _fake_result("wrong answer")

        later_run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs2", council_runner=later
        )
        cmp = compare_to_baseline(later_run, bp)
        assert "a" in cmp["regressions"]
        assert "b" not in cmp["regressions"]  # no false record either way

    @pytest.mark.asyncio
    async def test_infra_error_not_reported_as_regression(self, tmp_path):
        # Council round-8 finding (in-diff, #507 follow-through): an item
        # that previously passed but now infra-errors must NOT show up as a
        # "regression" — that would re-conflate infra with quality drift,
        # exactly what #507 exists to prevent.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def good(prompt):
            return _fake_result("hello")

        async def erroring(prompt):
            raise RuntimeError("gateway down")

        base_run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=good
        )
        bp = set_baseline(base_run, tmp_path / "baseline.json")
        infra_run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs2", council_runner=erroring
        )
        cmp = compare_to_baseline(infra_run, bp)
        assert cmp["regressions"] == []  # NOT ["a"]
        assert cmp["pass_rate"] is None  # items_scored == 0


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

    def test_corrupt_baseline_reported_not_crash(self, tmp_path, caplog):
        from llm_council.bench.harness import BenchRun

        bp = tmp_path / "baseline.json"
        bp.write_text("{corrupt")
        run = BenchRun(
            started_at="t", items_total=0, items_run=0,
            items_passed=0, total_cost_usd=0.0, cost_known=False,
        )
        with caplog.at_level("WARNING"):
            cmp = compare_to_baseline(run, bp)
        assert cmp == {"baseline": None}
        # round-5 review: corrupt must be distinguishable from "no baseline
        # yet" (below) — via a warning, not an identical silent report.
        assert any("corrupt" in r.message for r in caplog.records)

    def test_missing_baseline_is_silent(self, tmp_path, caplog):
        # The "no baseline committed yet" case is expected/routine — NOT a
        # warning (only genuine corruption should log).
        from llm_council.bench.harness import BenchRun

        run = BenchRun(
            started_at="t", items_total=0, items_run=0,
            items_passed=0, total_cost_usd=0.0, cost_known=False,
        )
        with caplog.at_level("WARNING"):
            cmp = compare_to_baseline(run, tmp_path / "does-not-exist.json")
        assert cmp == {"baseline": None}
        assert not caplog.records


class TestCouncilRound2:
    @pytest.mark.asyncio
    async def test_error_items_still_charge_the_cap(self, tmp_path, monkeypatch):
        # #439 r2: an item that raises may already have spent (stage 1 ran,
        # stage 3 raised) — errors must charge the conservative default, not
        # bypass cap accounting.
        monkeypatch.setenv("LLM_COUNCIL_BENCH_UNKNOWN_ITEM_USD", "0.50")
        d = tmp_path / "ds"
        d.mkdir()
        for i in range(4):
            _write_item(d, f"i{i}")

        async def runner(prompt):
            raise RuntimeError("mid-run failure")

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs",
            council_runner=runner, max_usd=1.00,
        )
        assert run.exit_code == 2  # cap abort after 2 error charges
        assert run.items_run == 2

    @pytest.mark.asyncio
    async def test_cost_known_means_all_items_known(self, tmp_path):
        # #439 r2: OR-accumulation flipped 'fully known' on the FIRST known
        # item; the report claims 'not fully known' semantics.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")
        _write_item(d, "b")
        calls = {"n": 0}

        async def runner(prompt):
            calls["n"] += 1
            r = _fake_result("hello")
            if calls["n"] == 2:
                r["metadata"]["usage"]["total"] = {"cost_usd": 0.0}  # unknown
            return r

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs", council_runner=runner
        )
        assert run.cost_known is False  # one unknown item => NOT fully known


class TestCouncilRound3:
    @pytest.mark.asyncio
    async def test_monthly_ledger_counts_charged_not_just_actuals(self, tmp_path, monkeypatch):
        # #439 r3: unknown-cost runs recorded $0 actuals, silently eroding
        # the monthly guard; the ledger now sums the cap-charged figure.
        monkeypatch.setenv("LLM_COUNCIL_BENCH_UNKNOWN_ITEM_USD", "0.50")
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def runner(prompt):
            r = _fake_result("hello")
            r["metadata"]["usage"]["total"] = {}  # unknown cost
            return r

        runs = tmp_path / "runs"
        await run_bench(dataset_dir=d, runs_dir=runs, council_runner=runner)
        assert month_to_date_spend(runs) == pytest.approx(0.50)

    @pytest.mark.asyncio
    async def test_baseline_refuses_aborted_run(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")
        _write_item(d, "b")

        async def runner(prompt):
            return _fake_result("hello", cost=2.0)

        run = await run_bench(
            dataset_dir=d, runs_dir=tmp_path / "runs",
            council_runner=runner, max_usd=1.0,
        )
        assert run.aborted
        with pytest.raises(ValueError, match="aborted"):
            set_baseline(run, tmp_path / "baseline.json")
