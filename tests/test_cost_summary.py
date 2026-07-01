"""Tests for cost/token summary formatting + progressive disclosure (ADR-011)."""

from llm_council.cost_summary import format_cost_summary

_USAGE = {
    "total": {"total_tokens": 8500, "cost_usd": 0.0212, "cached_tokens": 200},
    "by_model": {
        "openai/gpt-4o": {"total_tokens": 5000, "cost_usd": 0.015},
        "anthropic/claude-3-5-sonnet": {"total_tokens": 3500, "cost_usd": 0.0062},
    },
    "by_stage": {
        "stage1": {"total_tokens": 4000, "cost_usd": 0.01},
        "stage2": {"total_tokens": 3500, "cost_usd": 0.009},
        "stage3": {"total_tokens": 1000, "cost_usd": 0.0022},
    },
}


def test_empty_usage_is_empty_string():
    assert format_cost_summary(None) == ""
    assert format_cost_summary({}) == ""


def test_default_is_one_line():
    out = format_cost_summary(_USAGE)
    assert "\n" not in out  # progressive disclosure: single line by default
    assert "~8.5k tokens" in out
    assert "$0.0212" in out
    assert "cached" in out


def test_details_include_per_model_and_stage():
    out = format_cost_summary(_USAGE, include_details=True)
    assert "By model:" in out
    assert "openai/gpt-4o" in out
    assert "By stage:" in out
    assert "stage2" in out
    # Still leads with the one-line summary.
    assert out.splitlines()[0].startswith("Council usage:")


def test_none_nested_values_do_not_crash():
    # A malformed usage block with null sub-sections must not raise.
    usage = {"total": None, "by_model": None, "by_stage": None}
    assert format_cost_summary(usage) == "Council usage: ~0 tokens"
    # include_details path must also survive nulls.
    out = format_cost_summary(usage, include_details=True)
    assert out.startswith("Council usage:")


def test_cost_omitted_when_zero_or_unknown():
    usage = {"total": {"total_tokens": 100, "cost_usd": 0.0}}
    out = format_cost_summary(usage)
    assert "tokens" in out
    assert "$" not in out  # never show a $0.0000 bill when cost is unknown/free
