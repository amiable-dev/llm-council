"""VerifyResponse.input_metrics surfaces token/cost totals (ADR-011 #366)."""

from llm_council.verification.api import _usage_input_metrics


def test_reads_grand_total():
    usage = {
        "total": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_usd": 0.02,
            "cost_known": True,
            "cached_tokens": 5,
        }
    }
    m = _usage_input_metrics(usage)
    assert m["prompt_tokens"] == 100
    assert m["completion_tokens"] == 50
    assert m["total_tokens"] == 150
    assert m["cost_usd"] == 0.02
    assert m["cost_known"] is True
    assert m["cached_tokens"] == 5


def test_empty_when_usage_absent():
    assert _usage_input_metrics(None) == {}
    assert _usage_input_metrics({}) == {}
    assert _usage_input_metrics({"total": {}}) == {}


def test_cost_known_false_for_unknown_cost():
    m = _usage_input_metrics({"total": {"total_tokens": 10, "cost_usd": 0.0}})
    assert m["cost_known"] is False  # no phantom "known $0"
