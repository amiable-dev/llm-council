"""ADR-048 P2: quality-per-dollar config matrix (#419). Mocked — no spend."""

import json

import pytest

from llm_council.bench.matrix import (
    MatrixConfig,
    format_matrix_table,
    quality_per_dollar,
    run_matrix,
)


def _write_item(d, iid):
    (d / f"{iid}.json").write_text(
        json.dumps(
            {
                "id": iid,
                "domain": "factual",
                "prompt": "say hello",
                "envelope": {"must_contain": [["hello"]], "min_score": 0.3},
            }
        )
    )


def _result(text, score=0.8, cost=0.02, known=True):
    return {
        "synthesis": text,
        "metadata": {
            "aggregate_rankings": [{"model": "m", "average_score": score}],
            "usage": {"total": {"cost_usd": cost, "cost_known": known}},
        },
    }


class TestQualityPerDollar:
    def test_basic_math(self):
        assert quality_per_dollar(pass_rate=1.0, cost_usd=0.50, cost_known=True) == 2.0

    def test_unknown_cost_is_none(self):
        assert quality_per_dollar(pass_rate=1.0, cost_usd=0.0, cost_known=False) is None

    def test_zero_cost_known_is_none_not_infinity(self):
        assert quality_per_dollar(pass_rate=1.0, cost_usd=0.0, cost_known=True) is None


class TestMatrix:
    @pytest.mark.asyncio
    async def test_runs_each_config_and_tables(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def council(prompt):
            return _result("hello from council", cost=0.10)

        async def solo(prompt):
            # Solo runs produce NO consensus score — floors must not apply.
            r = _result("hello from solo", cost=0.01)
            r["metadata"]["aggregate_rankings"] = []
            return r

        configs = [
            MatrixConfig(name="solo:m/a", kind="solo", runner=solo),
            MatrixConfig(name="council", kind="council", runner=council),
        ]
        rows = await run_matrix(
            configs, dataset_dir=d, runs_dir=tmp_path / "runs", max_usd=2.0
        )
        by_name = {r["config"]: r for r in rows}
        assert by_name["solo:m/a"]["pass_rate"] == 1.0  # floor skipped for solo
        assert by_name["council"]["pass_rate"] == 1.0
        assert by_name["solo:m/a"]["quality_per_dollar"] > by_name["council"]["quality_per_dollar"]
        table = format_matrix_table(rows)
        assert "quality/$" in table and "council" in table

    @pytest.mark.asyncio
    async def test_config_error_reported_not_fatal(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def broken(prompt):
            raise RuntimeError("boom")

        async def council(prompt):
            return _result("hello", cost=0.10)

        rows = await run_matrix(
            [
                MatrixConfig(name="bad", kind="solo", runner=broken),
                MatrixConfig(name="council", kind="council", runner=council),
            ],
            dataset_dir=d,
            runs_dir=tmp_path / "runs",
            max_usd=2.0,
        )
        by_name = {r["config"]: r for r in rows}
        assert by_name["bad"]["pass_rate"] == 0.0
        assert by_name["council"]["pass_rate"] == 1.0

    def test_solo_missing_colon_raises_explicit_value_error(self):
        # Round 3 review: an explicit, clear message instead of a bare
        # "list index out of range" IndexError.
        from llm_council.bench.matrix import _default_runner

        with pytest.raises(ValueError, match="must be 'solo:<model>'"):
            _default_runner(MatrixConfig(name="no-colon-here", kind="solo"))

    @pytest.mark.asyncio
    async def test_config_exception_conservatively_exhausts_budget(
        self, tmp_path, monkeypatch
    ):
        # Round 3 review, against my OWN round-1 fix: before it, ANY
        # exception from run_bench crashed the whole matrix (loud). Catching
        # it silently assumed zero spend — but run_bench may have already
        # made real, costly API calls before failing partway through (e.g. in
        # the monthly-guard-lock exit path, after _run_items already spent),
        # with no reliable way to recover a partial cost figure. A failing
        # config must conservatively consume the WHOLE remaining budget so a
        # later config can never overspend on top of an unknown cost.
        #
        # A plain runner exception does NOT reach this path — harness's own
        # per-item loop (#507) already absorbs it as an infra_failure without
        # run_bench raising. To exercise run_bench raising directly (the
        # actual scenario the finding describes), patch it at the point
        # matrix.py calls it.
        import llm_council.bench.matrix as matrix_mod

        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        call_count = {"n": 0}
        real_run_bench = matrix_mod.run_bench

        async def flaky_run_bench(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("boom mid-run_bench")
            return await real_run_bench(*args, **kwargs)

        monkeypatch.setattr(matrix_mod, "run_bench", flaky_run_bench)

        async def good(prompt):
            return _result("hello", cost=0.05)

        configs = [
            MatrixConfig(name="broken", kind="solo", runner=good),
            MatrixConfig(name="good", kind="solo", runner=good),
        ]
        rows = await run_matrix(
            configs, dataset_dir=d, runs_dir=tmp_path / "runs", max_usd=2.0
        )
        by_name = {r["config"]: r for r in rows}
        assert "config_error" in by_name["broken"]["aborted"]
        # Round 4 review: the row must not silently show cost_usd=0.0 while
        # the ledger conservatively charges the whole remaining budget
        # elsewhere — cap_charged_usd surfaces exactly what was assumed.
        assert by_name["broken"]["cap_charged_usd"] == 2.0
        # "good" never actually ran — the failing config conservatively
        # consumed the whole budget, exactly like a real overspend would.
        assert by_name["good"]["items_run"] == 0
        assert "matrix_budget_exhausted" in by_name["good"]["aborted"]
        assert call_count["n"] == 1  # good's run_bench call was never reached

    @pytest.mark.asyncio
    async def test_malformed_config_name_does_not_crash_matrix(self, tmp_path):
        # Round-1 review (#511): _default_runner eagerly parses config.name
        # ("solo:<model>") and validates config.kind BEFORE any item runs —
        # unguarded, a colon-less name raised an uncaught IndexError that
        # crashed the WHOLE matrix mid-loop, discarding already-PAID-FOR
        # results from every earlier config. A later config's typo must not
        # destroy prior configs' results.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def good(prompt):
            return _result("hello", cost=0.05)

        configs = [
            MatrixConfig(name="council", kind="council", runner=good),
            MatrixConfig(name="solo-missing-colon", kind="solo"),  # no runner override
        ]
        rows = await run_matrix(
            configs, dataset_dir=d, runs_dir=tmp_path / "runs", max_usd=2.0
        )
        by_name = {r["config"]: r for r in rows}
        assert by_name["council"]["cost_usd"] == 0.05  # prior result PRESERVED
        assert by_name["solo-missing-colon"]["items_run"] == 0
        assert "config_error" in by_name["solo-missing-colon"]["aborted"]

    @pytest.mark.asyncio
    async def test_unknown_kind_does_not_crash_matrix(self, tmp_path):
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        async def good(prompt):
            return _result("hello", cost=0.05)

        configs = [
            MatrixConfig(name="council", kind="council", runner=good),
            MatrixConfig(name="bogus", kind="not-a-real-kind"),
        ]
        rows = await run_matrix(
            configs, dataset_dir=d, runs_dir=tmp_path / "runs", max_usd=2.0
        )
        by_name = {r["config"]: r for r in rows}
        assert by_name["council"]["cost_usd"] == 0.05
        assert "config_error" in by_name["bogus"]["aborted"]

    def test_table_escapes_pipe_in_abort_reason(self):
        # Round 4 review: a `|` in an exception message (config_error embeds
        # str(exc) verbatim) would otherwise split into extra columns and
        # corrupt the table's structure.
        rows = [{
            "config": "bad", "kind": "solo", "items_run": 0, "pass_rate": 0.0,
            "cost_usd": 0.0, "cost_known": False, "quality_per_dollar": None,
            "aborted": "config_error: boom | evil | injection",
        }]
        table = format_matrix_table(rows)
        # Escaped (\|), not a raw column-splitting pipe: a markdown renderer
        # treats \| as a literal character, not a cell boundary, so the row
        # still renders as ONE config cell instead of splitting into extra
        # columns.
        assert "boom \\| evil \\| injection" in table
        assert "boom | evil | injection" not in table  # the unescaped form is gone

    def test_table_shows_actual_abort_reason_not_generic(self):
        # Round 2 review: the table used to show a bare "(aborted)" suffix,
        # discarding exactly the config_error/matrix_budget_exhausted reason
        # this session's own fixes depend on being visible.
        rows = [{
            "config": "bad", "kind": "solo", "items_run": 0, "pass_rate": 0.0,
            "cost_usd": 0.0, "cost_known": False, "quality_per_dollar": None,
            "aborted": "config_error: bad config",
        }]
        table = format_matrix_table(rows)
        assert "config_error: bad config" in table

    @pytest.mark.asyncio
    async def test_matrix_wide_budget_shared_across_configs(self, tmp_path):
        # #511: max_usd is the TOTAL across every config, not per-config — the
        # old behaviour passed the SAME cap to each config, so N configs
        # could spend up to N x cap in one invocation. 3 configs at $1/item,
        # budget $2 total: only the first 2 may spend; the 3rd must be
        # skipped BEFORE it runs (its runner never called), not run-then-
        # capped.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")

        call_log = []

        def make_runner(name):
            async def runner(prompt):
                call_log.append(name)
                return _result("hello", cost=1.0)
            return runner

        configs = [
            MatrixConfig(name="one", kind="solo", runner=make_runner("one")),
            MatrixConfig(name="two", kind="solo", runner=make_runner("two")),
            MatrixConfig(name="three", kind="solo", runner=make_runner("three")),
        ]
        rows = await run_matrix(
            configs, dataset_dir=d, runs_dir=tmp_path / "runs", max_usd=2.0
        )
        assert call_log == ["one", "two"]  # "three"'s runner never invoked
        by_name = {r["config"]: r for r in rows}
        assert by_name["one"]["cost_usd"] == 1.0
        assert by_name["two"]["cost_usd"] == 1.0
        assert by_name["three"]["items_run"] == 0
        assert "matrix_budget_exhausted" in by_name["three"]["aborted"]
        total_spent = sum(r["cost_usd"] for r in rows)
        assert total_spent <= 2.0  # the whole point: bounded, not N x cap

    @pytest.mark.asyncio
    async def test_pass_rate_excludes_infra_errors_from_denominator(self, tmp_path):
        # #507 follow-through (Council round-8 finding, in-diff): an
        # infra-errored item must not deflate pass_rate — items_scored
        # excludes it from the denominator, same as BenchRun.exit_code.
        d = tmp_path / "ds"
        d.mkdir()
        _write_item(d, "a")
        _write_item(d, "b")

        calls = {"n": 0}

        async def mixed(prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("gateway down")
            return _result("hello")

        rows = await run_matrix(
            [MatrixConfig(name="mixed", kind="solo", runner=mixed)],
            dataset_dir=d,
            runs_dir=tmp_path / "runs",
            max_usd=2.0,
        )
        # 1 genuine pass, 1 infra error: NOT 50% (items_run) — 100% of what
        # actually got scored.
        assert rows[0]["pass_rate"] == 1.0


class TestCouncilRound1:
    @pytest.mark.asyncio
    async def test_graduated_flag_never_leaks_to_next_config(self, monkeypatch, tmp_path):
        # #440 r1: the graduated runner set LLM_COUNCIL_GRADUATED_DEPTH and
        # never reverted — a 'council' config running AFTER 'graduated' would
        # silently run graduated too, invalidating the comparison.
        import os

        from llm_council.bench.matrix import _default_runner

        monkeypatch.delenv("LLM_COUNCIL_GRADUATED_DEPTH", raising=False)
        observed = {}

        async def fake_council(prompt, **kwargs):
            observed["flag_during_call"] = os.environ.get("LLM_COUNCIL_GRADUATED_DEPTH")
            return {"synthesis": "x", "metadata": {}}

        import llm_council.council as council_mod

        monkeypatch.setattr(council_mod, "run_council_with_fallback", fake_council)

        graduated = _default_runner(MatrixConfig(name="graduated", kind="graduated"))
        await graduated("q")
        assert observed["flag_during_call"] == "true"  # on DURING the call
        assert "LLM_COUNCIL_GRADUATED_DEPTH" not in os.environ  # restored after

        plain = _default_runner(MatrixConfig(name="council", kind="council"))
        await plain("q")
        assert observed["flag_during_call"] is None  # plain config unaffected

    def test_unknown_kind_raises_never_spends(self):
        # #440 r2: an unknown kind fell through to the FULL COUNCIL runner —
        # a typo could silently spend real money.
        from llm_council.bench.matrix import _default_runner

        with pytest.raises(ValueError, match="unknown matrix kind"):
            _default_runner(MatrixConfig(name="oops", kind="banana"))
