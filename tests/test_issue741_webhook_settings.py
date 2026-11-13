"""#741: the documented webhook settings take effect.

Found while fixing GHSA-r7rh-j9cj-h9hh:

- ``LLM_COUNCIL_WEBHOOK_HTTPS_ONLY`` was documented (README, .env.example,
  SECURITY.md) and read by nothing;
- ``LLM_COUNCIL_WEBHOOK_TIMEOUT`` reached ``webhooks.timeout_seconds`` but the
  dispatcher looked up ``timeout``, so it always used 5.0;
- both were frozen at import time.
"""

import pytest

from llm_council import unified_config
from llm_council.unified_config import get_effective_config
from llm_council.webhooks.dispatcher import WebhookDispatcher, webhook_settings


@pytest.fixture
def reload(monkeypatch):
    """Apply env vars to the GLOBAL config, and restore it afterwards."""

    def _apply(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return unified_config.reload_config()

    yield _apply
    monkeypatch.undo()
    unified_config.reload_config()


class TestHttpsOnlyEnv:
    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off", " false "])
    def test_explicit_false_turns_it_off(self, monkeypatch, value):
        monkeypatch.setenv("LLM_COUNCIL_WEBHOOK_HTTPS_ONLY", value)
        assert get_effective_config().webhooks.https_only is False

    @pytest.mark.parametrize("value", ["true", "1", "yes", "flase", "disable", "nope"])
    def test_anything_else_stays_on(self, monkeypatch, value):
        # Fail safe: a typo must not silently drop the HTTPS requirement.
        monkeypatch.setenv("LLM_COUNCIL_WEBHOOK_HTTPS_ONLY", value)
        assert get_effective_config().webhooks.https_only is True

    def test_unset_defaults_on(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_WEBHOOK_HTTPS_ONLY", raising=False)
        assert get_effective_config().webhooks.https_only is True


class TestDispatcherUsesConfiguredSettings:
    def test_defaults(self, reload):
        reload()
        d = WebhookDispatcher()
        assert (d._timeout, d._max_retries, d._https_only) == (5.0, 3, True)

    def test_timeout_env_reaches_the_dispatcher(self, reload):
        reload(LLM_COUNCIL_WEBHOOK_TIMEOUT="9.5")
        assert WebhookDispatcher()._timeout == 9.5

    def test_retries_env_reaches_the_dispatcher(self, reload):
        reload(LLM_COUNCIL_WEBHOOK_RETRIES="7")
        assert WebhookDispatcher()._max_retries == 7

    def test_https_only_env_reaches_the_dispatcher(self, reload):
        reload(LLM_COUNCIL_WEBHOOK_HTTPS_ONLY="false")
        assert WebhookDispatcher()._https_only is False
        assert webhook_settings()[2] is False

    def test_settings_are_read_at_construction_not_import(self, reload):
        reload(LLM_COUNCIL_WEBHOOK_TIMEOUT="2")
        first = WebhookDispatcher()
        reload(LLM_COUNCIL_WEBHOOK_TIMEOUT="4")
        assert (first._timeout, WebhookDispatcher()._timeout) == (2.0, 4.0)

    def test_explicit_arguments_win(self, reload):
        reload(LLM_COUNCIL_WEBHOOK_TIMEOUT="9", LLM_COUNCIL_WEBHOOK_HTTPS_ONLY="false")
        d = WebhookDispatcher(timeout=1.0, max_retries=1, https_only=True)
        assert (d._timeout, d._max_retries, d._https_only) == (1.0, 1, True)

    def test_yaml_timeout_reaches_the_dispatcher(self, tmp_path, monkeypatch):
        cfg = tmp_path / "llm_council.yaml"
        cfg.write_text("council:\n  webhooks:\n    timeout_seconds: 12.0\n    https_only: false\n")
        monkeypatch.setenv("LLM_COUNCIL_CONFIG", str(cfg))
        try:
            unified_config.reload_config()
            d = WebhookDispatcher()
            assert (d._timeout, d._https_only) == (12.0, False)
        finally:
            monkeypatch.undo()
            unified_config.reload_config()


class TestHttpsOnlyOffStillGuardsAddresses:
    async def test_plain_http_to_a_public_host_is_allowed_but_loopback_is_not(self, reload):
        from llm_council.webhooks.url_guard import WebhookTargetError, resolve_webhook_target

        reload(LLM_COUNCIL_WEBHOOK_HTTPS_ONLY="false")
        https_only = webhook_settings()[2]
        target = await resolve_webhook_target("http://hooks.example.com/h", https_only=https_only)
        assert target.pinned_ip == "93.184.216.34"
        with pytest.raises(WebhookTargetError):
            await resolve_webhook_target("http://127.0.0.1:9999/h", https_only=https_only)
