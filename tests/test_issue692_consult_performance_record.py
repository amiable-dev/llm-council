"""#692 — the consult path must leave a cost trail.

`performance_metrics.jsonl` had exactly one writer: the verify path. Every
`consult` — the expensive path, and the one an operator is actually billed
for — wrote nothing at all. `InternalPerformanceTracker.record_session` had no
caller anywhere in `src/`.

The consequence was not a missing nicety. An operator reconciling a large
OpenRouter bill against the local file could not tell the difference between
"cheap" and "unrecorded", because the path where the money goes was not
represented in the file at all.

## The null-versus-zero rule, applied twice

This ticket exists because a `0` and a `None` were conflated once already. The
same distinction governs both fields recorded here:

* `cost_usd` is `None` when the provider reported no cost, never `0.0`. A zero
  is a measurement — a cached response or a free tier really did cost nothing.
* `borda_score` is `None` when peer review did not rank that model, never
  `0.0`. A zero means "ranked last"; a null means "never ranked". Recording a
  partial run as a pile of zero-scored models would silently poison the
  performance index that decides future model selection.

`ModelPerformanceIndex` already excluded `None` costs from its mean rather than
averaging them in as zeros; this change gives `borda_score` the same treatment,
following that precedent rather than inventing one.
"""

import ast
import json
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COUNCIL_SRC = REPO_ROOT / "src/llm_council/council.py"


def _read_records(store: pathlib.Path):
    if not store.exists():
        return []
    return [json.loads(line) for line in store.read_text().splitlines() if line.strip()]


class TestTheHelperRecordsWhatHappened:
    """`persist_council_performance` is the single place the consult path
    writes from, so both orchestrators cannot drift in what they record."""

    def test_one_record_per_ranked_model(self):
        from llm_council.council_usage import persist_council_performance
        from llm_council.performance import integration

        written = persist_council_performance(
            session_id="s-1",
            model_statuses={
                "a/one": {"status": "ok", "latency_ms": 1200},
                "b/two": {"status": "ok", "latency_ms": 3400},
            },
            aggregate_rankings=[
                {"model": "a/one", "borda_score": 1.0},
                {"model": "b/two", "borda_score": 0.5},
            ],
            stage2_results=[],
            usage_summary={},
        )
        assert written == 2

        rows = _read_records(integration.resolve_store_path())
        by_model = {r["model_id"]: r for r in rows}
        assert set(by_model) == {"a/one", "b/two"}
        assert by_model["a/one"]["latency_ms"] == 1200
        assert by_model["b/two"]["borda_score"] == 0.5

    def test_aggregate_rankings_may_arrive_as_a_list_or_a_dict(self):
        """The council carries rankings as a LIST of dicts; verify converts to
        a dict before persisting. The helper accepts either rather than making
        each call site remember which shape it holds."""
        from llm_council.council_usage import persist_council_performance

        as_list = persist_council_performance(
            session_id="s-list",
            model_statuses={"a/one": {"latency_ms": 10}},
            aggregate_rankings=[{"model": "a/one", "borda_score": 0.25}],
            stage2_results=[],
            usage_summary={},
        )
        as_dict = persist_council_performance(
            session_id="s-dict",
            model_statuses={"a/one": {"latency_ms": 10}},
            aggregate_rankings={"a/one": {"borda_score": 0.25}},
            stage2_results=[],
            usage_summary={},
        )
        assert as_list == as_dict == 1

    def test_cost_comes_from_the_usage_summary_and_is_none_when_unknown(self):
        from llm_council.council_usage import persist_council_performance
        from llm_council.performance import integration

        persist_council_performance(
            session_id="s-cost",
            model_statuses={"a/paid": {"latency_ms": 1}, "b/unknown": {"latency_ms": 1}},
            aggregate_rankings=[
                {"model": "a/paid", "borda_score": 1.0},
                {"model": "b/unknown", "borda_score": 0.0},
            ],
            stage2_results=[],
            usage_summary={
                "by_model": {
                    "a/paid": {"cost_usd": 0.0123, "cost_known": True},
                    # reported nothing: must stay None, NOT collapse to 0.0
                    "b/unknown": {"cost_usd": 0.0},
                }
            },
        )
        rows = {r["model_id"]: r for r in _read_records(integration.resolve_store_path())}
        assert rows["a/paid"]["cost_usd"] == pytest.approx(0.0123)
        assert rows["b/unknown"]["cost_usd"] is None, (
            "an unreported cost must be null, not a phantom $0 — summing those "
            "against an invoice is the failure this ticket exists to fix"
        )

    def test_a_reported_zero_is_kept_as_zero(self):
        """The mirror case. A free tier or a fully cached response really did
        cost nothing, and that is a measurement worth keeping."""
        from llm_council.council_usage import persist_council_performance
        from llm_council.performance import integration

        persist_council_performance(
            session_id="s-free",
            model_statuses={"a/free": {"latency_ms": 1}},
            aggregate_rankings=[{"model": "a/free", "borda_score": 1.0}],
            stage2_results=[],
            usage_summary={"by_model": {"a/free": {"cost_usd": 0.0, "cost_known": True}}},
        )
        rows = _read_records(integration.resolve_store_path())
        assert rows[0]["cost_usd"] == 0.0

    def test_never_raises_into_the_run(self):
        """Telemetry must not fail a completed deliberation. The verify path
        wraps its persist in try/except for this reason; the consult path is
        the one where the user is waiting on an answer."""
        from llm_council.council_usage import persist_council_performance

        assert (
            persist_council_performance(
                session_id="s-bad",
                model_statuses=None,
                aggregate_rankings="not a ranking structure",
                stage2_results=None,
                usage_summary=None,
            )
            == 0
        )


class TestPartialRunsStillRecord:
    """The deliberate choice for #692: a consult that timed out still billed,
    and an unrecorded cost is a total that cannot be reconciled. Verify
    persists nothing on timeout; consult diverges, on purpose."""

    def test_a_model_that_answered_but_was_never_ranked_is_recorded(self):
        from llm_council.council_usage import persist_council_performance
        from llm_council.performance import integration

        written = persist_council_performance(
            session_id="s-partial",
            model_statuses={
                "a/ranked": {"latency_ms": 100},
                "b/unranked": {"latency_ms": 200},
            },
            # stage 2 only got to one of them
            aggregate_rankings=[{"model": "a/ranked", "borda_score": 1.0}],
            stage2_results=[],
            usage_summary={
                "by_model": {
                    "a/ranked": {"cost_usd": 0.01, "cost_known": True},
                    "b/unranked": {"cost_usd": 0.02, "cost_known": True},
                }
            },
        )
        assert written == 2, "the unranked model's spend was dropped"

        rows = {r["model_id"]: r for r in _read_records(integration.resolve_store_path())}
        assert rows["b/unranked"]["cost_usd"] == pytest.approx(0.02)
        assert rows["b/unranked"]["borda_score"] is None, (
            "an unranked model must record a null score, not 0.0 — a zero means "
            "'ranked last' and would poison the selection index"
        )
        assert rows["a/ranked"]["borda_score"] == 1.0

    def test_stage_two_never_ran_at_all_still_records_stage_one_spend(self):
        from llm_council.council_usage import persist_council_performance

        written = persist_council_performance(
            session_id="s-nostage2",
            model_statuses={"a/one": {"latency_ms": 100}, "b/two": {"latency_ms": 100}},
            aggregate_rankings=[],
            stage2_results=[],
            usage_summary={
                "by_model": {
                    "a/one": {"cost_usd": 0.01, "cost_known": True},
                    "b/two": {"cost_usd": 0.01, "cost_known": True},
                }
            },
        )
        assert written == 2


class TestTheIndexIgnoresUnscoredRecords:
    """A null Borda must be excluded from the mean, not averaged in as zero —
    the same rule `mean_cost_usd` already follows."""

    def test_mean_borda_excludes_nulls(self):
        from llm_council.performance.tracker import InternalPerformanceTracker
        from llm_council.performance.types import ModelSessionMetric

        tracker = InternalPerformanceTracker()
        now = "2026-09-24T00:00:00+00:00"
        records = [
            ModelSessionMetric(
                session_id="a", model_id="m", timestamp=now, latency_ms=1,
                borda_score=1.0, parse_success=True,
            ),
            ModelSessionMetric(
                session_id="b", model_id="m", timestamp=now, latency_ms=1,
                borda_score=None, parse_success=True,
            ),
        ]
        index = tracker._index_from_records("m", records)  # type: ignore[attr-defined]
        assert index.mean_borda_score == pytest.approx(1.0), (
            "a null score was averaged in as a zero, halving the mean"
        )
        assert index.sample_size == 2, "the record still counts for sample size"


class TestBothOrchestratorsPersist:
    """AST-pinned. The original defect was an absent call, which reads as
    correct code everywhere — exactly the #648/#660 failure class."""

    @pytest.mark.parametrize(
        "orchestrator", ["run_council_with_fallback", "run_full_council"]
    )
    def test_the_orchestrator_calls_the_persist_helper(self, orchestrator):
        tree = ast.parse(COUNCIL_SRC.read_text())
        fn = next(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == orchestrator
            ),
            None,
        )
        assert fn is not None, f"{orchestrator} not found"
        called = {
            n.func.id
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "persist_council_performance" in called, (
            f"{orchestrator} does not persist a performance record. #692: the "
            f"consult path is where the money goes and it left no cost trail."
        )


class TestEndToEndAConsultLeavesARecord:
    """The acceptance criterion as written: *a consult run writes records*.

    Mocked at the network boundary rather than at the stage functions, so the
    real stage-1/2/3 logic, the real Borda aggregation and the real usage
    accounting all run. Patching the stages instead would have made this a
    tautology — it would assert that the code I wrote calls the code I wrote.
    """

    @pytest.mark.asyncio
    async def test_run_full_council_writes_one_record_per_model(self, monkeypatch):
        from unittest.mock import AsyncMock, patch

        from llm_council.performance import integration

        # The council's own membership, not a forced one: `LLM_COUNCIL_MODELS`
        # is resolved through the cached config singleton, so setting it here
        # would not take effect (the same import-order trap as #693, one layer
        # up — noted, out of scope for this ticket).
        from llm_council.council import _get_council_models

        models = list(_get_council_models())
        assert models, "no council configured; the test would prove nothing"

        # Stage 1 and stage 2 both go through query_models_parallel.
        def _answers(model_list, messages, **kwargs):
            return {
                m: {
                    "content": "FINAL RANKING:\n1. Response A\n2. Response B",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                        "cost": 0.002,
                    },
                }
                for m in model_list
            }

        with (
            patch(
                "llm_council.council_stages.query_models_parallel",
                new_callable=AsyncMock,
                side_effect=_answers,
            ),
            patch(
                "llm_council.council_stages.query_model",
                new_callable=AsyncMock,
                return_value={
                    "content": "synthesis",
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "cost": 0.001,
                    },
                },
            ),
        ):
            from llm_council.council import run_full_council

            await run_full_council("what is 2+2?", bypass_cache=True)

        rows = _read_records(integration.resolve_store_path())
        assert rows, "a completed consult wrote no performance record at all"
        by_model = {r["model_id"]: r for r in rows}
        assert set(by_model) >= set(models), (
            f"expected records for {models}, got {list(by_model)}"
        )
        for model in models:
            assert by_model[model]["cost_usd"] is not None, (
                f"{model} recorded no cost though the provider reported one — "
                "this is the trail #692 exists to create"
            )
            # run_full_council does not measure latency: None, not a fake 0.
            assert by_model[model]["latency_ms"] is None


class TestTheIndexAdmitsWhatItDoesNotKnow:
    """Round 2 of the council gate.

    Round 1 made the *record* honest; the aggregation layer then quietly put
    the fabrications back. `_calculate_percentile([])` returned 0 — "answered
    instantly" — for a model whose latencies were all unmeasured, and
    `parse_success_rate` fell back to a confident 1.0 on no evidence at all.
    Worse, `sample_size` counted signal-free rows, so once #692 began recording
    models peer review never reached, a model could climb to MODERATE or HIGH
    confidence — and clear the ADR-029 graduation gate — on rows containing
    nothing.

    The lesson is the one this whole release keeps re-learning: making a field
    nullable is only half the job. Every consumer that averages, counts or
    defaults it has to learn the difference too.
    """

    def _records(self, n, **kwargs):
        from llm_council.performance.types import ModelSessionMetric

        now = "2026-09-24T00:00:00+00:00"
        return [
            ModelSessionMetric(session_id=f"s{i}", model_id="m", timestamp=now, **kwargs)
            for i in range(n)
        ]

    def _index(self, records):
        from llm_council.performance.tracker import InternalPerformanceTracker

        return InternalPerformanceTracker()._index_from_records("m", records)

    def test_unmeasured_latency_reports_unknown_not_instant(self):
        index = self._index(self._records(3, borda_score=0.5))
        assert index.p50_latency_ms is None, (
            "a model with no measured latency reported a p50 of 0 — which reads "
            "as 'answered instantly' to the tier-budget decisions downstream"
        )
        assert index.p95_latency_ms is None

    def test_a_measured_latency_is_still_reported(self):
        index = self._index(self._records(3, borda_score=0.5, latency_ms=1200))
        assert index.p50_latency_ms == 1200

    def test_no_parse_signal_reports_unknown_not_perfect(self):
        index = self._index(self._records(3, borda_score=0.5))
        assert index.parse_success_rate is None, (
            "a 1.0 parse-success rate was claimed on zero evidence"
        )

    def test_parse_rate_divides_by_records_carrying_the_signal(self):
        records = self._records(1, borda_score=0.5, parse_success=True) + self._records(
            1, borda_score=0.5, parse_success=False
        ) + self._records(2, borda_score=0.5)  # no signal either way
        index = self._index(records)
        assert index.parse_success_rate == pytest.approx(0.5), (
            "records with no parse signal were counted in the denominator, "
            "diluting the rate toward zero"
        )

    def test_signal_free_records_do_not_confer_confidence(self):
        """The ADR-029 graduation gate reads this. Fifteen rows that record a
        cost but no quality signal are fifteen observations of nothing."""
        index = self._index(self._records(15))
        assert index.confidence_level == "INSUFFICIENT"
        assert index.sample_size == 15, "the rows still exist and still count as rows"

    def test_scored_records_do_confer_confidence(self):
        index = self._index(self._records(15, borda_score=0.5))
        assert index.confidence_level == "PRELIMINARY"

    def test_the_selection_gate_counts_scored_records_too(self):
        """`get_all_model_scores` required 10 records before routing on a
        model. Nine unranked rows plus one ranked row used to clear it and
        route selection on a single observation."""
        from llm_council.performance.tracker import InternalPerformanceTracker

        tracker = InternalPerformanceTracker()
        grouped = {"m": self._records(9) + self._records(1, borda_score=0.9)}
        assert tracker._scores_from_grouped(grouped) == {}

        grouped_real = {"m": self._records(10, borda_score=0.9)}
        assert "m" in tracker._scores_from_grouped(grouped_real)


class TestParseSuccessHasNoSecondBackDoor:
    """Round 2 found that round 1 fixed one of the two `return True` exits.
    Both are pinned here, because the one that mattered was the one on the
    default path — `stage2_results` is optional and defaults to None."""

    @pytest.mark.parametrize(
        "stage2",
        [None, [], [{"model": "someone/else", "parsed_ranking": ["Response A"]}]],
        ids=["none", "empty", "other-model-only"],
    )
    def test_a_model_with_no_stage2_data_is_unknown(self, stage2):
        from llm_council.performance.integration import _extract_parse_success

        assert _extract_parse_success("a/model", stage2) is None

    def test_a_model_that_did_parse_is_true(self):
        from llm_council.performance.integration import _extract_parse_success

        assert (
            _extract_parse_success(
                "a/model", [{"model": "a/model", "parsed_ranking": ["Response A"]}]
            )
            is True
        )

    def test_an_abstention_is_false_not_unknown(self):
        from llm_council.performance.integration import _extract_parse_success

        assert (
            _extract_parse_success(
                "a/model", [{"model": "a/model", "abstained": True}]
            )
            is False
        )
