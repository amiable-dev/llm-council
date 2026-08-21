"""ADR-044 P3 wiring, slice 1 (#618): shadow depth telemetry.

Shadow mode measures the counterfactual "was full depth necessary?" on every
full-depth run: full-run CSS, a subset-approximated mini-rung CSS (council
design review 2026-08-21 — the counterfactual IS observable from in-memory
Stage-2 data), a decision classification, and a durable JSONL record
(`.council/depth/decisions.jsonl` — the #595 lesson: log lines evaporate).

Zero behavior change: the response payload never carries the record, and the
hook soft-fails. Both orchestrators must call it (AST-pinned).
"""

import ast
import json
import pathlib

from llm_council import graduated_depth as gd

LABELS = ["Response A", "Response B", "Response C", "Response D", "Response E"]
MODELS = ["m1", "m2", "m3", "m4", "m5"]
L2M = {
    lab: {"model": m, "display_index": i}
    for i, (lab, m) in enumerate(zip(LABELS, MODELS))
}


def _stage2(orders, models=MODELS):
    return [
        {"model": m, "ranking": f"secret-review-text-{m}", "parsed_ranking": {"ranking": o}}
        for m, o in zip(models, orders)
    ]


def _aggregate(stage2, l2m=L2M):
    from llm_council.council_rankings import calculate_aggregate_rankings

    return calculate_aggregate_rankings(stage2, l2m)


UNANIMOUS = [LABELS[:]] * 5  # full CSS 0.7, mini subset CSS 0.8

# mini reviewers agree on A>B>C relative order; D/E placement scrambles the
# full aggregate (full CSS ≈ 0.404 < 0.7, mini subset CSS 0.8 ≥ 0.7)
MIXED = [
    ["Response A", "Response B", "Response C", "Response D", "Response E"],
    ["Response D", "Response A", "Response B", "Response E", "Response C"],
    ["Response E", "Response D", "Response A", "Response B", "Response C"],
    ["Response C", "Response E", "Response B", "Response D", "Response A"],
    ["Response B", "Response C", "Response D", "Response A", "Response E"],
]

# mini reviewers split 2-1 on the mini responses (subset CSS ≈ 0.53 < 0.7)
MINI_SPLIT = [
    ["Response A", "Response B", "Response C", "Response D", "Response E"],
    ["Response A", "Response B", "Response C", "Response D", "Response E"],
    ["Response C", "Response B", "Response A", "Response D", "Response E"],
    ["Response A", "Response B", "Response C", "Response D", "Response E"],
    ["Response A", "Response B", "Response C", "Response D", "Response E"],
]


def _run_hook(stage2, tmp_path, monkeypatch, models=MODELS, l2m=L2M, **kw):
    monkeypatch.setattr(
        gd, "DEFAULT_DEPTH_DECISIONS_PATH", tmp_path / "depth" / "decisions.jsonl"
    )
    record = gd.evaluate_and_log_shadow_depth(
        entry_point="test",
        stage2_results=stage2,
        label_to_model=l2m,
        aggregate_rankings=_aggregate(stage2, l2m),
        council_models=models,
        **kw,
    )
    return record, tmp_path / "depth" / "decisions.jsonl"


class TestDecisionClassification:
    def test_mini_would_suffice(self, tmp_path, monkeypatch):
        record, log = _run_hook(_stage2(UNANIMOUS), tmp_path, monkeypatch)
        assert record["decision"] == "mini_would_suffice"
        assert record["css_full"] == 0.7
        assert record["css_mini_counterfactual"] == 0.8
        assert record["hypothetical_saved_models"] == 2
        assert record["mini_council_models"] == MODELS[:3]
        assert log.exists()
        persisted = json.loads(log.read_text().splitlines()[-1])
        assert persisted["decision"] == "mini_would_suffice"
        assert "ts" in persisted

    def test_premature_halt_risk(self, tmp_path, monkeypatch):
        record, _ = _run_hook(_stage2(MIXED), tmp_path, monkeypatch)
        assert record["decision"] == "premature_halt_risk"
        assert record["css_full"] < 0.7
        assert record["css_mini_counterfactual"] >= 0.7
        assert record["hypothetical_saved_models"] == 0

    def test_would_escalate(self, tmp_path, monkeypatch):
        record, _ = _run_hook(_stage2(MINI_SPLIT), tmp_path, monkeypatch)
        assert record["decision"] == "would_escalate"
        assert record["css_mini_counterfactual"] < 0.7
        # an escalated ladder run pays an extra mini Stage-2 pass
        assert record["extra_stage2_reviews_if_escalated"] == 3

    def test_ladder_inapplicable_for_small_councils(self, tmp_path, monkeypatch):
        models = MODELS[:3]
        l2m = {lab: {"model": m, "display_index": i}
               for i, (lab, m) in enumerate(zip(LABELS[:3], models))}
        stage2 = _stage2([LABELS[:3]] * 3, models=models)
        record, log = _run_hook(stage2, tmp_path, monkeypatch, models=models, l2m=l2m)
        assert record["decision"] == "ladder_inapplicable"
        assert log.exists()  # still logged — the rate matters for tier data

    def test_signals_unavailable_on_empty_stage2(self, tmp_path, monkeypatch):
        record, _ = _run_hook([], tmp_path, monkeypatch)
        assert record["decision"] == "signals_unavailable"


class TestRecordHygiene:
    def test_no_response_content_in_record(self, tmp_path, monkeypatch):
        _, log = _run_hook(_stage2(UNANIMOUS), tmp_path, monkeypatch)
        assert "secret-review-text" not in log.read_text()

    def test_est_saved_usd_absent_without_cost_history(self, tmp_path, monkeypatch):
        import llm_council.budget as budget_mod

        class _NoHistory:
            def estimate(self, models):
                return type("E", (), {"expected": 0.0, "low": 0.0, "high": 0.0})()

        monkeypatch.setattr(budget_mod, "CostEstimator", _NoHistory)
        record, _ = _run_hook(_stage2(UNANIMOUS), tmp_path, monkeypatch)
        assert "est_saved_usd" not in record

    def test_est_saved_usd_present_with_history(self, tmp_path, monkeypatch):
        import llm_council.budget as budget_mod

        class _WithHistory:
            def estimate(self, models):
                return type("E", (), {"expected": 0.042, "low": 0.02, "high": 0.08})()

        monkeypatch.setattr(budget_mod, "CostEstimator", _WithHistory)
        record, _ = _run_hook(_stage2(UNANIMOUS), tmp_path, monkeypatch)
        assert record["est_saved_usd"] == 0.042

    def test_independent_of_quality_metrics_flag(self, tmp_path, monkeypatch):
        # Council design review: LLM_COUNCIL_QUALITY_METRICS is an
        # output-annotation flag; shadow telemetry computes CSS internally.
        monkeypatch.setenv("LLM_COUNCIL_QUALITY_METRICS", "false")
        record, log = _run_hook(_stage2(UNANIMOUS), tmp_path, monkeypatch)
        assert record["decision"] == "mini_would_suffice"
        assert log.exists()


class TestSoftFail:
    def test_unwritable_path_never_raises(self, tmp_path, monkeypatch):
        blocker = tmp_path / "blocker"
        blocker.write_text("")  # a FILE where a directory is needed
        monkeypatch.setattr(
            gd, "DEFAULT_DEPTH_DECISIONS_PATH", blocker / "decisions.jsonl"
        )
        stage2 = _stage2(UNANIMOUS)
        record = gd.evaluate_and_log_shadow_depth(
            entry_point="test",
            stage2_results=stage2,
            label_to_model=L2M,
            aggregate_rankings=_aggregate(stage2),
            council_models=MODELS,
        )
        # evaluation still returns the record; only persistence failed
        assert record is not None and record["decision"] == "mini_would_suffice"

    def test_garbage_inputs_never_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            gd, "DEFAULT_DEPTH_DECISIONS_PATH", tmp_path / "d.jsonl"
        )
        record = gd.evaluate_and_log_shadow_depth(
            entry_point="test",
            stage2_results=[{"bogus": True}],
            label_to_model={"Response A": "not-a-dict-value"},
            aggregate_rankings=[{"also": "bogus"}],
            council_models=MODELS,
        )
        assert record is None or record["decision"] in (
            "signals_unavailable",
            "counterfactual_unavailable",
        )


class TestOrchestratorWiring:
    """Both orchestrators must call the shadow hook (AST-pinned, cf. ADR-053)."""

    def _calls_in(self, func_names):
        src = pathlib.Path("src/llm_council/council.py").read_text()
        tree = ast.parse(src)
        called_from = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call):
                        name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                        if name == "evaluate_and_log_shadow_depth":
                            called_from.add(fn.name)
        return {f for f in func_names if any(f in c or c in f for c in called_from)} or called_from & set(func_names)

    def test_both_orchestrators_call_the_hook(self):
        src = pathlib.Path("src/llm_council/council.py").read_text()
        tree = ast.parse(src)
        enclosing = set()

        def visit(fn_node, stack):
            for node in ast.iter_child_nodes(fn_node):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit(node, stack + [node.name])
                else:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            name = getattr(sub.func, "id", getattr(sub.func, "attr", ""))
                            if name == "evaluate_and_log_shadow_depth":
                                enclosing.update(stack)
                    for sub in ast.iter_child_nodes(node):
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            visit(sub, stack + [sub.name])

        visit(tree, [])
        assert any("run_full_council" == f for f in enclosing), enclosing
        assert any(
            f in ("run_council_with_fallback", "run_council_pipeline") for f in enclosing
        ), enclosing
