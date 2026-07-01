"""Tests for OTel GenAI usage-metrics emission (ADR-011 Phase 2, #361)."""

from llm_council.observability.usage_metrics import (
    COST_METRIC,
    TOKEN_USAGE_METRIC,
    emit_usage_metrics,
)


class _RecordingBackend:
    def __init__(self):
        self.histograms = []
        self.gauges = []
        self.counters = []

    def emit_counter(self, name, value, tags):
        self.counters.append((name, value, tags))

    def emit_gauge(self, name, value, tags):
        self.gauges.append((name, value, tags))

    def emit_histogram(self, name, value, tags):
        self.histograms.append((name, value, tags))


class _Adapter:
    def __init__(self, backend):
        self.backend = backend


def _emit(usage):
    backend = _RecordingBackend()
    emit_usage_metrics(usage, adapter=_Adapter(backend))
    return backend


_USAGE = {
    "by_model": {
        "openai/gpt-4o": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "cost_usd": 0.0125,
            "cost_known": True,
        }
    }
}


def test_emits_input_and_output_token_histograms_with_otel_names():
    backend = _emit(_USAGE)
    names = [h[0] for h in backend.histograms]
    assert names == [TOKEN_USAGE_METRIC, TOKEN_USAGE_METRIC]
    types = {h[2]["gen_ai.token.type"] for h in backend.histograms}
    assert types == {"input", "output"}
    # OTel GenAI tags present
    for _, _, tags in backend.histograms:
        assert tags["gen_ai.request.model"] == "openai/gpt-4o"
        assert tags["gen_ai.operation.name"] == "chat"


def test_emits_cost_gauge_when_known():
    backend = _emit(_USAGE)
    assert backend.gauges == [
        (
            COST_METRIC,
            0.0125,
            {
                "gen_ai.request.model": "openai/gpt-4o",
                "gen_ai.operation.name": "chat",
                "gen_ai.system": "openai",  # provider derived from model prefix
            },
        )
    ]


def test_no_cost_gauge_when_cost_unknown():
    usage = {"by_model": {"m": {"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.0}}}
    backend = _emit(usage)  # no cost_known -> unknown
    assert backend.gauges == []


def test_empty_or_none_usage_is_noop():
    assert _emit(None).histograms == []
    assert _emit({}).histograms == []


def test_gen_ai_system_derived_from_model_prefix():
    backend = _emit({"by_model": {"anthropic/claude-3-5-sonnet": {"prompt_tokens": 1}}})
    assert backend.histograms[0][2]["gen_ai.system"] == "anthropic"


def test_gen_ai_system_unknown_without_prefix():
    backend = _emit({"by_model": {"baremodel": {"prompt_tokens": 1}}})
    assert backend.histograms[0][2]["gen_ai.system"] == "unknown"


def test_zero_tokens_still_emitted():
    # 0 is a valid histogram observation; both input and output are emitted.
    usage = {"by_model": {"m": {"prompt_tokens": 0, "completion_tokens": 0}}}
    backend = _emit(usage)
    assert len(backend.histograms) == 2
    assert all(h[1] == 0.0 for h in backend.histograms)


def test_per_model_failure_isolated():
    # One model raising must not drop metrics for the others in the batch.
    class _PartialBackend(_RecordingBackend):
        def emit_histogram(self, name, value, tags):
            if tags["gen_ai.request.model"] == "bad/m":
                raise RuntimeError("boom")
            super().emit_histogram(name, value, tags)

    backend = _PartialBackend()
    usage = {
        "by_model": {
            "bad/m": {"prompt_tokens": 1, "completion_tokens": 1},
            "good/m": {"prompt_tokens": 2, "completion_tokens": 2},
        }
    }
    emit_usage_metrics(usage, adapter=_Adapter(backend))
    emitted = {h[2]["gen_ai.request.model"] for h in backend.histograms}
    assert "good/m" in emitted  # survived the bad model's failure


def test_never_raises_on_bad_backend():
    class _BadBackend:
        def emit_histogram(self, *a):
            raise RuntimeError("boom")

        emit_gauge = emit_histogram

    # Must swallow the error, not propagate.
    emit_usage_metrics(_USAGE, adapter=_Adapter(_BadBackend()))
