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
                "gen_ai.system": "llm_council",
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


def test_never_raises_on_bad_backend():
    class _BadBackend:
        def emit_histogram(self, *a):
            raise RuntimeError("boom")

        emit_gauge = emit_histogram

    # Must swallow the error, not propagate.
    emit_usage_metrics(_USAGE, adapter=_Adapter(_BadBackend()))
