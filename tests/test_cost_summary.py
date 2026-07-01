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


def test_sub_cent_cost_not_masked_as_zero():
    # An 8dp-resolved sub-cent cost must not display as $0.0000.
    usage = {"total": {"total_tokens": 100, "cost_usd": 0.00005, "cost_known": True}}
    out = format_cost_summary(usage)
    assert "$0.0000 " not in out and not out.endswith("$0.0000")
    assert "$0.000050" in out


def test_stage_with_cost_but_zero_tokens_is_kept():
    usage = {
        "total": {"total_tokens": 0, "cost_usd": 0.01, "cost_known": True},
        "by_stage": {"stage1": {"total_tokens": 0, "cost_usd": 0.01, "cost_known": True}},
    }
    out = format_cost_summary(usage, include_details=True)
    assert "stage1: 0 tok, $0.0100" in out


def test_none_nested_values_do_not_crash():
    # A malformed usage block with null sub-sections must not raise.
    usage = {"total": None, "by_model": None, "by_stage": None}
    assert format_cost_summary(usage) == "Council usage: ~0 tokens"
    # include_details path must also survive nulls.
    out = format_cost_summary(usage, include_details=True)
    assert out.startswith("Council usage:")


def test_cost_omitted_when_unknown():
    # cost_usd 0.0 with no cost_known signal == unknown -> omit the cost figure.
    usage = {"total": {"total_tokens": 100, "cost_usd": 0.0}}
    out = format_cost_summary(usage)
    assert "tokens" in out
    assert "$" not in out


def test_genuine_zero_cost_shown_when_known():
    # A reported $0 (free/local) is distinguished from unknown and IS shown.
    usage = {"total": {"total_tokens": 100, "cost_usd": 0.0, "cost_known": True}}
    out = format_cost_summary(usage)
    assert "$0.0000" in out


def test_detail_lines_show_known_zero_consistently():
    # A row with its own cost_known must show a genuine $0 (not suppress it).
    usage = {
        "total": {"total_tokens": 20, "cost_usd": 0.0, "cost_known": True},
        "by_model": {"ollama/llama3": {"total_tokens": 20, "cost_usd": 0.0, "cost_known": True}},
        "by_stage": {"stage1": {"total_tokens": 20, "cost_usd": 0.0, "cost_known": True}},
    }
    out = format_cost_summary(usage, include_details=True)
    assert out.count("$0.0000") >= 2  # one-liner + model + stage all show it


def test_unknown_row_not_shown_as_zero_even_if_aggregate_known():
    # Per-row provenance: an unknown-cost row must NOT display $0.0000 just
    # because some other row (and thus the aggregate) has a known cost.
    usage = {
        "total": {"total_tokens": 20, "cost_usd": 0.01, "cost_known": True},
        "by_model": {
            "known/m": {"total_tokens": 10, "cost_usd": 0.01, "cost_known": True},
            "unknown/m": {"total_tokens": 10, "cost_usd": 0.0},  # no cost_known
        },
    }
    out = format_cost_summary(usage, include_details=True)
    assert "known/m: 10 tok, $0.0100" in out
    assert "unknown/m: 10 tok" in out
    assert "unknown/m: 10 tok, $" not in out
