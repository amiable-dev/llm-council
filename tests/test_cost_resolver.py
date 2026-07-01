"""Tests for the per-gateway CostResolver (ADR-011 Phase 1, #360).

The resolver assigns a USD cost and a provenance tag (`cost_source`) to a
model call, honouring the gateway's cost fidelity:

- provider ground-truth (OpenRouter/Requesty return `usage.cost`)  -> "provider"
- registry-pricing estimate (Direct APIs return tokens only)        -> "registry_estimate"
- local models (Ollama)                                             -> "local_zero"
- pricing unknown                                                    -> (None, None)
"""

from llm_council.gateway.cost_resolver import CostResolver
from llm_council.gateway.types import UsageInfo


# --- registry pricing double: gpt-4o-ish, per 1K tokens --------------------
def _pricing_lookup(model_id):
    table = {
        "openai/gpt-4o": {"prompt": 0.0025, "completion": 0.01},
        "anthropic/claude-3-5-sonnet": {"prompt": 0.003, "completion": 0.015},
    }
    return table.get(model_id, {})


class TestCostResolver:
    def test_provider_reported_cost_wins(self):
        r = CostResolver(pricing_lookup=_pricing_lookup)
        cost, source = r.resolve(
            gateway="openrouter",
            model_id="openai/gpt-4o",
            prompt_tokens=1000,
            completion_tokens=1000,
            provider_cost_usd=0.0125,
        )
        # Ground truth is used verbatim, never recomputed from the table.
        assert cost == 0.0125
        assert source == "provider"

    def test_registry_estimate_when_no_provider_cost(self):
        r = CostResolver(pricing_lookup=_pricing_lookup)
        cost, source = r.resolve(
            gateway="direct",
            model_id="openai/gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        # (1000/1000)*0.0025 + (500/1000)*0.01 = 0.0025 + 0.005 = 0.0075
        assert cost == 0.0075
        assert source == "registry_estimate"

    def test_local_gateway_is_zero(self):
        r = CostResolver(pricing_lookup=_pricing_lookup)
        cost, source = r.resolve(
            gateway="ollama",
            model_id="ollama/llama3",
            prompt_tokens=5000,
            completion_tokens=5000,
        )
        assert cost == 0.0
        assert source == "local_zero"

    def test_unknown_pricing_returns_none(self):
        r = CostResolver(pricing_lookup=_pricing_lookup)
        cost, source = r.resolve(
            gateway="direct",
            model_id="some/unpriced-model",
            prompt_tokens=1000,
            completion_tokens=1000,
        )
        assert cost is None
        assert source is None

    def test_apply_mutates_usage_in_place(self):
        r = CostResolver(pricing_lookup=_pricing_lookup)
        usage = UsageInfo(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        out = r.apply(
            usage,
            gateway="direct",
            model_id="openai/gpt-4o",
        )
        assert out is usage  # returns the same object for convenience
        assert usage.cost_usd == 0.0075
        assert usage.cost_source == "registry_estimate"

    def test_apply_records_cached_tokens(self):
        r = CostResolver(pricing_lookup=_pricing_lookup)
        usage = UsageInfo(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        r.apply(
            usage,
            gateway="openrouter",
            model_id="openai/gpt-4o",
            provider_cost_usd=0.01,
            cached_tokens=200,
        )
        assert usage.cost_usd == 0.01
        assert usage.cost_source == "provider"
        assert usage.cached_tokens == 200

    def test_missing_pricing_lookup_falls_back_to_none(self):
        # No lookup injected: only provider/local paths can produce a cost.
        r = CostResolver()
        cost, source = r.resolve(
            gateway="direct",
            model_id="openai/gpt-4o",
            prompt_tokens=1000,
            completion_tokens=1000,
        )
        assert cost is None
        assert source is None


class TestUsageInfoCostFields:
    def test_new_fields_default_safely(self):
        usage = UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        assert usage.cost_usd is None
        assert usage.cost_source is None
        assert usage.cached_tokens == 0
