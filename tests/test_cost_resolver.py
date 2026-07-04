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

    def test_unknown_pricing_returns_none_with_empty_lookup(self):
        # An explicit empty lookup models "pricing unknown".
        r = CostResolver(pricing_lookup=lambda m: {})
        cost, source = r.resolve(
            gateway="direct",
            model_id="unpriced/model",
            prompt_tokens=1000,
            completion_tokens=1000,
        )
        assert cost is None
        assert source is None

    def test_non_numeric_provider_cost_falls_through(self):
        # A malformed provider cost must not crash; fall back to a registry estimate.
        r = CostResolver(pricing_lookup=_pricing_lookup)
        cost, source = r.resolve(
            gateway="direct",
            model_id="openai/gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            provider_cost_usd="not-a-number",
        )
        assert source == "registry_estimate"
        assert cost == 0.0075

    def test_invalid_provider_costs_fall_through(self):
        # NaN / infinity / negative are not valid ground truth; they must not
        # corrupt accounting — fall through to a registry estimate instead.
        r = CostResolver(pricing_lookup=_pricing_lookup)
        for bad in (float("nan"), float("inf"), float("-inf"), -0.01):
            cost, source = r.resolve(
                gateway="direct",
                model_id="openai/gpt-4o",
                prompt_tokens=1000,
                completion_tokens=500,
                provider_cost_usd=bad,
            )
            assert source == "registry_estimate", bad
            assert cost == 0.0075

    def test_null_registry_price_does_not_crash(self):
        # A present-but-null price must not reach the arithmetic (TypeError).
        r = CostResolver(pricing_lookup=lambda m: {"prompt": None, "completion": 0.01})
        cost, source = r.resolve(
            gateway="direct", model_id="x/y", prompt_tokens=1000, completion_tokens=1000
        )
        assert source == "registry_estimate"
        assert cost == 0.01  # prompt None -> 0; 1000/1000 * 0.01

    def test_all_prices_invalid_returns_none(self):
        r = CostResolver(pricing_lookup=lambda m: {"prompt": None, "completion": "n/a"})
        cost, source = r.resolve(
            gateway="direct", model_id="x/y", prompt_tokens=1000, completion_tokens=1000
        )
        assert cost is None and source is None

    def test_negative_registry_price_ignored(self):
        r = CostResolver(pricing_lookup=lambda m: {"prompt": -1.0, "completion": 0.01})
        cost, source = r.resolve(
            gateway="direct", model_id="x/y", prompt_tokens=1000, completion_tokens=1000
        )
        assert source == "registry_estimate"
        assert cost == 0.01  # negative prompt price treated as 0

    def test_negative_token_counts_clamped(self):
        r = CostResolver(pricing_lookup=_pricing_lookup)
        cost, source = r.resolve(
            gateway="direct",
            model_id="openai/gpt-4o",
            prompt_tokens=-100,
            completion_tokens=-50,
        )
        assert source == "registry_estimate"
        assert cost == 0.0  # clamped, never negative

    def test_default_resolver_uses_registry_lookup(self, monkeypatch):
        # A bare CostResolver() defaults to the registry lookup so Direct-API
        # calls are still priced (finding: missing default fallback).
        monkeypatch.setattr(
            "llm_council.gateway.cost_resolver.registry_pricing_lookup",
            lambda m: {"prompt": 0.001, "completion": 0.002},
        )
        r = CostResolver()
        cost, source = r.resolve(
            gateway="direct",
            model_id="x/y",
            prompt_tokens=1000,
            completion_tokens=1000,
        )
        assert source == "registry_estimate"
        assert cost == 0.003


class TestUsageInfoCostFields:
    def test_new_fields_default_safely(self):
        usage = UsageInfo(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        assert usage.cost_usd is None
        assert usage.cost_source is None
        assert usage.cached_tokens == 0


class TestRegistryPricingLookup:
    def test_delegates_to_metadata_provider(self, monkeypatch):
        from llm_council.gateway.cost_resolver import registry_pricing_lookup

        class _FakeProvider:
            def get_pricing(self, model_id):
                return {"prompt": 0.001, "completion": 0.002}

        monkeypatch.setattr("llm_council.metadata.get_provider", lambda: _FakeProvider())
        assert registry_pricing_lookup("any/model") == {"prompt": 0.001, "completion": 0.002}

    def test_swallows_provider_errors(self, monkeypatch):
        from llm_council.gateway.cost_resolver import registry_pricing_lookup

        def _boom():
            raise RuntimeError("provider unavailable")

        monkeypatch.setattr("llm_council.metadata.get_provider", _boom)
        # Never raises into the hot path; unknown pricing -> empty dict.
        assert registry_pricing_lookup("any/model") == {}


# --- ADR-049 D3: cache price classes on the registry_estimate path ---------
def _cache_pricing_lookup(model_id):
    table = {
        # Anthropic verified multipliers: read 0.1x, write-5m 1.25x, write-1h 2x
        "anthropic/claude-opus-4.8": {
            "prompt": 0.005,
            "completion": 0.025,
            "cache_read": 0.0005,
            "cache_write_5m": 0.00625,
            "cache_write_1h": 0.01,
        },
        # No cache prices: unknowns default to the prompt price.
        "openai/gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    }
    return table.get(model_id, {})


class TestCachePriceClasses:
    """ADR-049 §Decision.3 golden paths: hit / miss / write-5m / write-1h /
    unknown-cache-price-defaults-to-prompt-price. Cache token counts are the
    provider's SEPARATE fields (Anthropic direct: input_tokens excludes
    cache_read/cache_creation) — they are priced in ADDITION to prompt_tokens.
    """

    def test_cache_read_hit_priced_at_cache_read_price(self):
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        cost, source = r.resolve(
            gateway="direct",
            model_id="anthropic/claude-opus-4.8",
            prompt_tokens=1000,
            completion_tokens=1000,
            cache_read_tokens=10000,
        )
        # 1000/1K*0.005 + 1000/1K*0.025 + 10000/1K*0.0005 = 0.005+0.025+0.005
        assert cost == 0.035
        assert source == "registry_estimate"

    def test_cache_miss_is_pre_d3_arithmetic(self):
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        cost, source = r.resolve(
            gateway="direct",
            model_id="anthropic/claude-opus-4.8",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost == 0.005 + 0.0125
        assert source == "registry_estimate"

    def test_cache_write_5m_priced_at_write_premium(self):
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        cost, _ = r.resolve(
            gateway="direct",
            model_id="anthropic/claude-opus-4.8",
            prompt_tokens=1000,
            completion_tokens=0,
            cache_write_5m_tokens=8000,
        )
        # 0.005 + 8000/1K*0.00625 = 0.005 + 0.05
        assert cost == 0.055

    def test_cache_write_1h_priced_at_2x(self):
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        cost, _ = r.resolve(
            gateway="direct",
            model_id="anthropic/claude-opus-4.8",
            prompt_tokens=1000,
            completion_tokens=0,
            cache_write_1h_tokens=8000,
        )
        # 0.005 + 8000/1K*0.01 = 0.005 + 0.08
        assert cost == 0.085

    def test_unknown_cache_prices_default_to_prompt_price(self):
        # gpt-4o entry carries no cache price classes: every cache token is
        # billed at the prompt price (conservative, never under-reported).
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        cost, source = r.resolve(
            gateway="direct",
            model_id="openai/gpt-4o",
            prompt_tokens=1000,
            completion_tokens=0,
            cache_read_tokens=2000,
            cache_write_5m_tokens=1000,
            cache_write_1h_tokens=1000,
        )
        # 0.0025 + (2000+1000+1000)/1K*0.0025 = 0.0025 + 0.01
        assert cost == 0.0125
        assert source == "registry_estimate"

    def test_provider_cost_path_ignores_cache_tokens(self):
        # Ground truth wins unconditionally — the provider figure already
        # includes any cache discount; cache params must not perturb it.
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        cost, source = r.resolve(
            gateway="openrouter",
            model_id="anthropic/claude-opus-4.8",
            prompt_tokens=1000,
            completion_tokens=1000,
            provider_cost_usd=0.01,
            cache_read_tokens=999999,
            cache_write_1h_tokens=999999,
        )
        assert cost == 0.01
        assert source == "provider"

    def test_negative_cache_token_counts_clamped(self):
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        cost, _ = r.resolve(
            gateway="direct",
            model_id="anthropic/claude-opus-4.8",
            prompt_tokens=1000,
            completion_tokens=0,
            cache_read_tokens=-500,
        )
        assert cost == 0.005  # clamped to zero, never negative

    def test_bundled_registry_carries_cache_prices_for_anthropic(self):
        # The shipped registry.yaml prices the verified Anthropic classes;
        # absent cache fields elsewhere must not break pricing lookups.
        import yaml
        from pathlib import Path

        reg = yaml.safe_load(
            Path("src/llm_council/models/registry.yaml").read_text()
        )
        models = {m["id"]: m for m in reg["models"]}
        opus = models["anthropic/claude-opus-4.8"]["pricing"]
        assert opus["cache_read"] == round(opus["prompt"] * 0.1, 8)
        assert opus["cache_write_5m"] == round(opus["prompt"] * 1.25, 8)
        assert opus["cache_write_1h"] == round(opus["prompt"] * 2.0, 8)
        # Schema tolerance: at least one entry has no cache fields and the
        # resolver defaults are exercised above.
        assert any("cache_read" not in m.get("pricing", {}) for m in reg["models"])

    def test_apply_threads_cache_tokens_to_resolve(self):
        # apply() is the gateway entry point: cache counts must reach the
        # registry-estimate arithmetic (round-1 council finding).
        r = CostResolver(pricing_lookup=_cache_pricing_lookup)
        usage = UsageInfo(prompt_tokens=1000, completion_tokens=0, total_tokens=1000)
        r.apply(
            usage,
            gateway="direct",
            model_id="anthropic/claude-opus-4.8",
            cache_read_tokens=10000,
        )
        assert usage.cost_usd == 0.005 + 0.005  # prompt + 10K cache reads
        assert usage.cost_source == "registry_estimate"
