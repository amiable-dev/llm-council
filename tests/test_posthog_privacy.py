"""ADR-050 D3 (#475): content-free privacy + residual-leakage rules.

Council prompts carry customer code; only metadata/tokens/cost leave. Pins:
- $ai_input / $ai_output_choices are NEVER emitted (content-free by default).
- No property carries raw prompt/code content or a file path.
- Exception messages are scrubbed to a type name before any log/property, so a
  provider error that echoes the prompt can't leak.
"""

import pytest

from llm_council.observability import ai_generation as ag
from llm_council.observability import posthog_emitter as pe

# Every property key the emitter is allowed to produce (content keys absent).
_ALLOWED_KEYS = {
    "$ai_trace_id", "$ai_model", "$ai_provider", "$ai_input_tokens",
    "$ai_output_tokens", "$ai_cache_read_input_tokens",
    "$ai_cache_creation_input_tokens", "$ai_total_cost_usd",
    "tier", "route", "round", "subject_sha", "consumer",
}
_FORBIDDEN_KEYS = {"$ai_input", "$ai_output_choices", "$ai_output", "prompt",
                   "content", "messages", "file_contents"}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    pe.reset_for_testing()
    yield
    pe.reset_for_testing()


class TestContentFree:
    def test_properties_never_carry_content(self):
        # Even a usage entry polluted with content-shaped keys yields only the
        # allowed metadata keys — the mapper is an allowlist, not a passthrough.
        mu = {"prompt_tokens": 100, "completion_tokens": 10, "cost_known": True,
              "cost_usd": 0.01, "cached_tokens": 0,
              "$ai_input": [{"role": "user", "content": "SECRET CODE"}],
              "prompt": "SECRET", "content": "SECRET"}
        p = ag.build_generation_properties("anthropic/claude-opus-4.8", mu,
                                           verification_id="v", tier="balanced",
                                           subject_sha="deadbeef")
        assert set(p).issubset(_ALLOWED_KEYS)
        assert not (_FORBIDDEN_KEYS & set(p))
        assert "SECRET" not in repr(p)

    def test_emitted_events_are_content_free(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")
        sink = []
        monkeypatch.setattr(ag, "emit",
                            lambda event, properties, distinct_id: sink.append(properties))
        usage = {"by_model": {"m/x": {"prompt_tokens": 5, "completion_tokens": 1,
                                      "cost_known": True, "cost_usd": 0.0,
                                      "$ai_input": "leak"}}}
        ag.emit_generation_events(usage, verification_id="v1", subject_sha="sha1")
        assert sink and not (_FORBIDDEN_KEYS & set(sink[0]))

    def test_subject_sha_passes_through_opaque(self):
        # subject_sha is an opaque digest (a commit SHA); no raw path leaks.
        mu = {"prompt_tokens": 1, "completion_tokens": 1, "cost_known": False}
        p = ag.build_generation_properties("m/x", mu, verification_id="v",
                                           subject_sha="abc123def")
        assert p["subject_sha"] == "abc123def"
        assert "/" not in p["subject_sha"]  # not a file path


class TestExceptionScrub:
    def test_scrub_drops_message(self):
        exc = ValueError("prompt was: def transfer_funds(acct): SECRET")
        scrubbed = pe.scrub_exception(exc)
        assert scrubbed == "ValueError"
        assert "SECRET" not in scrubbed

    def test_scrub_handles_weird_exceptions(self):
        assert pe.scrub_exception(RuntimeError()) == "RuntimeError"

    def test_emit_soft_fail_logs_scrubbed(self, monkeypatch, caplog):
        import logging
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_x")

        class BadClient:
            def capture(self, **kw):
                raise RuntimeError("echoing SECRET prompt content")

        monkeypatch.setattr(pe, "_get_client", lambda: BadClient())
        with caplog.at_level(logging.DEBUG, logger="llm_council.observability.posthog_emitter"):
            pe.emit("$ai_generation", {"a": 1}, "did")
        # the soft-fail log must not echo the exception's SECRET-bearing message
        assert "SECRET" not in caplog.text
