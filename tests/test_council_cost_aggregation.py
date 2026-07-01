"""Cost/token aggregation in the council (ADR-011 #360, slice 4).

`_add_cost_to_usage` is additive to the existing token aggregation: it sums
cost_usd + cached_tokens onto a stage bucket and, when a model is supplied,
also accumulates per-model spend under `by_model`.
"""

from llm_council.council import _add_cost_to_usage


def test_accumulates_cost_and_cached():
    bucket = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    _add_cost_to_usage(bucket, {"cost": 0.01, "cached_tokens": 5})
    assert bucket["cost_usd"] == 0.01
    assert bucket["cached_tokens"] == 5


def test_none_cost_is_zero_contribution():
    bucket = {}
    _add_cost_to_usage(bucket, {"prompt_tokens": 10})  # no cost/cached keys
    assert bucket["cost_usd"] == 0.0
    assert bucket["cached_tokens"] == 0
    assert not bucket.get("cost_known")  # cost genuinely unknown


def test_cost_known_set_even_for_reported_zero():
    bucket = {}
    _add_cost_to_usage(bucket, {"cost": 0.0})  # a reported $0 is "known"
    assert bucket.get("cost_known") is True


def test_per_model_accumulation():
    bucket = {}
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "cost": 0.02,
        "cached_tokens": 3,
    }
    _add_cost_to_usage(bucket, usage, model="openai/gpt-4o")
    bm = bucket["by_model"]["openai/gpt-4o"]
    assert bm["prompt_tokens"] == 100
    assert bm["cost_usd"] == 0.02
    assert bm["cached_tokens"] == 3

    # A second call for the same model accumulates.
    _add_cost_to_usage(
        bucket,
        {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost": 0.02},
        model="openai/gpt-4o",
    )
    bm = bucket["by_model"]["openai/gpt-4o"]
    assert bm["prompt_tokens"] == 200
    assert bm["cost_usd"] == 0.04


def test_no_model_skips_by_model():
    bucket = {}
    _add_cost_to_usage(bucket, {"cost": 0.01})
    assert "by_model" not in bucket
