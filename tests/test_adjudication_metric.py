"""ADR-050 D4 (#476): adjudication $ai_metric contract keyed to verification_id.

epic-loop's retro posts a human disposition onto a verify trace by emitting a
follow-up $ai_metric event keyed to $ai_trace_id = verification_id, with a
numeric metric_value (for TPR/FPR trends) plus a text adjudication_label.
Verify-before-implementation: the exact $ai_metric value-type / trace-vs-
generation scope is confirmed empirically against the live project before
production use (public docs don't pin it); the follow-up-event-by-trace_id
join itself IS documented.
"""

import pytest

from llm_council.observability import adjudication as adj
from llm_council.observability import posthog_emitter as pe


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    pe.reset_for_testing()
    yield
    pe.reset_for_testing()


class TestEmitAdjudication:
    def _capture(self, monkeypatch):
        sink = []
        monkeypatch.setattr(adj, "emit",
                            lambda event, properties, distinct_id: sink.append((event, properties, distinct_id)))
        return sink

    @pytest.mark.parametrize("disposition,value", [
        ("real", 1.0), ("marginal", 0.5), ("refuted", 0.0), ("pass-clean", 1.0),
    ])
    def test_numeric_value_and_label(self, monkeypatch, disposition, value):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        sink = self._capture(monkeypatch)
        adj.emit_adjudication("verif-123", disposition)
        assert len(sink) == 1
        event, props, did = sink[0]
        assert event == "$ai_metric"
        assert props["$ai_trace_id"] == "verif-123"
        assert props["metric_name"] == "adjudication"
        assert props["metric_value"] == value
        assert props["adjudication_label"] == disposition
        assert did == "llm-council"

    def test_notes_and_consumer(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        sink = self._capture(monkeypatch)
        adj.emit_adjudication("v1", "marginal", notes="borderline on edge case",
                              consumer="opaque-7")
        _, props, did = sink[0]
        assert props["adjudication_notes"] == "borderline on edge case"
        assert did == "opaque-7"

    def test_notes_absent_by_default(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        sink = self._capture(monkeypatch)
        adj.emit_adjudication("v1", "real")
        assert "adjudication_notes" not in sink[0][1]

    def test_invalid_disposition_raises_even_when_disabled(self):
        # Input validation is unconditional (a caller typo must surface); the
        # no-op-when-disabled contract governs EMISSION, not validation.
        with pytest.raises(ValueError):
            adj.emit_adjudication("v1", "REAL")  # wrong case / not in vocab
        with pytest.raises(ValueError):
            adj.emit_adjudication("v1", "bogus")

    def test_disabled_is_noop(self, monkeypatch):
        sink = self._capture(monkeypatch)
        adj.emit_adjudication("v1", "real")  # no key → no emit
        assert sink == []

    def test_empty_verification_id_raises(self):
        # Required input: an empty trace id is a caller error (consistent with
        # the disposition validation), raised even when emission is disabled.
        with pytest.raises(ValueError):
            adj.emit_adjudication("", "real")

    def test_soft_fail_on_emit_error(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")

        def boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(adj, "emit", boom)
        adj.emit_adjudication("v1", "real")  # must not raise

    def test_vocabulary_is_the_adr_set(self):
        assert set(adj.ADJUDICATION_VALUES) == {"real", "marginal", "refuted", "pass-clean"}
