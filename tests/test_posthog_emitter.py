"""ADR-050 D1 (#473): opt-in, soft-fail PostHog emitter foundation.

Off by default: no POSTHOG_API_KEY ⇒ disabled ⇒ byte-identical to pre-ADR
(no posthog import, no capture). Emission is soft-fail (never raises into a
verification). Flush is bounded (a stuck flush never hangs the process).
"""

import sys
import time
import types

import pytest

from llm_council.observability import posthog_emitter as pe


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    pe.reset_for_testing()
    yield
    pe.reset_for_testing()


def _fake_posthog(monkeypatch, capture_sink=None, init_sink=None, raise_on_init=None):
    class FakePosthog:
        def __init__(self, project_api_key=None, host=None, **kw):
            if raise_on_init:
                raise raise_on_init
            if init_sink is not None:
                init_sink["key"] = project_api_key
                init_sink["host"] = host

        def capture(self, **kw):
            if capture_sink is not None:
                capture_sink.append(kw)

    monkeypatch.setitem(sys.modules, "posthog", types.SimpleNamespace(Posthog=FakePosthog))


class TestDisabledByDefault:
    def test_disabled_without_key(self):
        assert pe.posthog_emission_enabled() is False

    def test_emit_is_noop_and_imports_nothing(self, monkeypatch):
        # A poisoned posthog module proves emit() never imports it when disabled.
        monkeypatch.setitem(sys.modules, "posthog", None)
        pe.emit("$ai_generation", {"a": 1}, "did")  # no raise
        assert pe._get_client() is None

    def test_enabled_with_key(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
        assert pe.posthog_emission_enabled() is True


class TestClientBuild:
    def test_builds_with_key_and_default_eu_host(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_abc")
        init = {}
        _fake_posthog(monkeypatch, init_sink=init)
        assert pe._get_client() is not None
        assert init["key"] == "phc_abc"
        assert init["host"] == "https://eu.i.posthog.com"

    def test_host_override(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_abc")
        monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")
        init = {}
        _fake_posthog(monkeypatch, init_sink=init)
        pe._get_client()
        assert init["host"] == "https://us.i.posthog.com"

    def test_client_is_cached(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_abc")
        _fake_posthog(monkeypatch)
        assert pe._get_client() is pe._get_client()

    def test_emit_calls_capture(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_abc")
        sink = []
        _fake_posthog(monkeypatch, capture_sink=sink)
        pe.emit("$ai_generation", {"$ai_model": "m"}, "trace-1")
        assert sink and sink[0]["event"] == "$ai_generation"
        assert sink[0]["distinct_id"] == "trace-1"
        assert sink[0]["properties"] == {"$ai_model": "m"}


class TestSoftFail:
    def test_emit_soft_fails_on_capture_error(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")

        class BadClient:
            def capture(self, **kw):
                raise RuntimeError("network down")

        monkeypatch.setattr(pe, "_get_client", lambda: BadClient())
        pe.emit("$ai_generation", {"a": 1}, "did")  # must not raise

    def test_init_soft_fails_when_sdk_missing(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
        monkeypatch.setitem(sys.modules, "posthog", None)  # import → error
        assert pe._get_client() is None
        pe.emit("$ai_generation", {"a": 1}, "did")  # no-op, no raise

    def test_init_soft_fails_on_bad_config(self, monkeypatch):
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
        _fake_posthog(monkeypatch, raise_on_init=ValueError("bad key"))
        assert pe._get_client() is None  # swallowed


class TestShutdown:
    def test_shutdown_flushes(self, monkeypatch):
        flushed = {}

        class C:
            def shutdown(self):
                flushed["s"] = True

        pe._client = C()
        pe._init_attempted = True
        pe.shutdown(timeout=1.0)
        assert flushed.get("s") is True

    def test_shutdown_bounded_on_hang(self):
        class C:
            def shutdown(self):
                time.sleep(5)  # simulate a stuck flush

        pe._client = C()
        pe._init_attempted = True
        t0 = time.monotonic()
        pe.shutdown(timeout=0.2)
        assert time.monotonic() - t0 < 2.0  # returned promptly, never waited 5s

    def test_shutdown_noop_without_client(self):
        pe.shutdown()  # no client → no-op, no raise

    def test_shutdown_soft_fails(self):
        class C:
            def shutdown(self):
                raise RuntimeError("boom")

        pe._client = C()
        pe._init_attempted = True
        pe.shutdown(timeout=1.0)  # must not raise
