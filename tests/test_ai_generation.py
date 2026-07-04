"""ADR-050 D2 (#474): $ai_generation property mapping + per-member emission.

One $ai_generation per council-member model, mapped from the ADR-011
usage.by_model summary. The load-bearing rule: $ai_input_tokens is the
NON-cached input count (max(0, prompt - cache_read)) so PostHog's hit-rate
tile cache_read/(cache_read+input) isn't double-counted.
"""

import pytest

from llm_council.observability import ai_generation as ag
from llm_council.observability import posthog_emitter as pe


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    pe.reset_for_testing()
    yield
    pe.reset_for_testing()


class TestBuildProperties:
    def test_core_mapping(self):
        mu = {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200,
              "cost_usd": 0.05, "cached_tokens": 0, "cache_write_tokens": 0,
              "cost_known": True}
        p = ag.build_generation_properties("anthropic/claude-opus-4.8", mu,
                                           verification_id="v1", tier="balanced")
        assert p["$ai_trace_id"] == "v1"
        assert p["$ai_model"] == "anthropic/claude-opus-4.8"
        assert p["$ai_provider"] == "anthropic"
        assert p["$ai_input_tokens"] == 1000
        assert p["$ai_output_tokens"] == 200
        assert p["$ai_cache_read_input_tokens"] == 0
        assert p["$ai_total_cost_usd"] == 0.05
        assert p["tier"] == "balanced"

    def test_cache_subtraction(self):
        # prompt includes cache reads (inclusive route) → input excludes them
        mu = {"prompt_tokens": 5000, "completion_tokens": 100, "cached_tokens": 4000,
              "cache_write_tokens": 800, "cost_known": True, "cost_usd": 0.01}
        p = ag.build_generation_properties("anthropic/claude-haiku-4.5", mu,
                                           verification_id="v")
        assert p["$ai_input_tokens"] == 1000  # 5000 - 4000
        assert p["$ai_cache_read_input_tokens"] == 4000
        assert p["$ai_cache_creation_input_tokens"] == 800

    def test_clamp_never_negative(self):
        # cached > prompt (anomaly / already-exclusive route) must clamp to 0
        mu = {"prompt_tokens": 100, "completion_tokens": 0, "cached_tokens": 500,
              "cost_known": False}
        p = ag.build_generation_properties("m/x", mu, verification_id="v")
        assert p["$ai_input_tokens"] == 0

    def test_cost_omitted_when_unknown(self):
        mu = {"prompt_tokens": 10, "completion_tokens": 5, "cost_known": False,
              "cost_usd": 0.0}
        p = ag.build_generation_properties("m/x", mu, verification_id="v")
        assert "$ai_total_cost_usd" not in p  # never present a fabricated cost

    def test_cache_creation_omitted_when_zero(self):
        mu = {"prompt_tokens": 10, "completion_tokens": 5, "cached_tokens": 0,
              "cache_write_tokens": 0, "cost_known": True, "cost_usd": 0.001}
        p = ag.build_generation_properties("m/x", mu, verification_id="v")
        assert "$ai_cache_creation_input_tokens" not in p

    def test_custom_props_only_when_set(self):
        mu = {"prompt_tokens": 1, "completion_tokens": 1, "cost_known": True,
              "cost_usd": 0.0}
        p = ag.build_generation_properties(
            "m/x", mu, verification_id="v", tier="high", route="openrouter",
            round=2, subject_sha="abc123", consumer="opaque-1")
        assert p["route"] == "openrouter"
        assert p["round"] == 2
        assert p["subject_sha"] == "abc123"
        assert p["consumer"] == "opaque-1"
        # unset custom keys absent
        p2 = ag.build_generation_properties("m/x", mu, verification_id="v")
        assert "route" not in p2 and "subject_sha" not in p2

    def test_provider_from_model_prefix(self):
        mu = {"prompt_tokens": 1, "completion_tokens": 1, "cost_known": False}
        assert ag.build_generation_properties("openai/gpt-5.4", mu,
                                              verification_id="v")["$ai_provider"] == "openai"
        assert ag.build_generation_properties("localmodel", mu,
                                              verification_id="v")["$ai_provider"] == "unknown"


class TestEmitGenerationEvents:
    def _usage(self):
        return {"by_model": {
            "anthropic/claude-opus-4.8": {"prompt_tokens": 100, "completion_tokens": 10,
                                          "cached_tokens": 0, "cache_write_tokens": 0,
                                          "cost_usd": 0.02, "cost_known": True},
            "openai/gpt-5.4": {"prompt_tokens": 200, "completion_tokens": 20,
                               "cached_tokens": 50, "cache_write_tokens": 0,
                               "cost_usd": 0.03, "cost_known": True},
        }}

    def test_one_event_per_member(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        sink = []
        monkeypatch.setattr(ag, "emit",
                            lambda event, properties, distinct_id: sink.append((event, properties, distinct_id)))
        ag.emit_generation_events(self._usage(), verification_id="v1",
                                  tier="balanced", consumer="opaque")
        assert len(sink) == 2
        assert all(e == "$ai_generation" for e, _, _ in sink)
        models = {p["$ai_model"] for _, p, _ in sink}
        assert models == {"anthropic/claude-opus-4.8", "openai/gpt-5.4"}
        # trace_id keyed to verification_id; distinct_id = consumer
        assert all(p["$ai_trace_id"] == "v1" for _, p, _ in sink)
        assert all(did == "opaque" for _, _, did in sink)

    def test_distinct_id_defaults_to_llm_council(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        sink = []
        monkeypatch.setattr(ag, "emit",
                            lambda event, properties, distinct_id: sink.append(distinct_id))
        ag.emit_generation_events(self._usage(), verification_id="v1")
        assert all(did == "llm-council" for did in sink)

    def test_disabled_is_noop(self, monkeypatch):
        # No POSTHOG_API_KEY → emit_generation_events does nothing, no raise.
        called = []
        monkeypatch.setattr(ag, "emit", lambda *a, **k: called.append(1))
        ag.emit_generation_events(self._usage(), verification_id="v1")
        assert called == []  # gated by posthog_emission_enabled()

    def test_soft_fail_on_bad_usage(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        # by_model with a non-dict value must not raise
        ag.emit_generation_events({"by_model": {"m": None}}, verification_id="v1")

    def test_empty_usage_noop(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        ag.emit_generation_events(None, verification_id="v1")
        ag.emit_generation_events({}, verification_id="v1")
        ag.emit_generation_events(self._usage(), verification_id="")  # no trace id
