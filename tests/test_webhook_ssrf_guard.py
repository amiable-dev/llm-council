"""Regression tests for GHSA-r7rh-j9cj-h9hh (webhook SSRF, CWE-918).

A caller of ``POST /v1/council/run`` chooses ``webhook_url``. Before the fix
the server POSTed to its own loopback services, opened TLS connections to
private addresses, and — in SYNC dispatch — leaked loopback port state through
response time. These tests pin the three properties of the fix:

1. targets are judged by the address they RESOLVE to, not by how the URL is
   spelled, and the connection goes to the address that was judged;
2. a rejected target causes no outbound connection at all (so there is no
   open/closed timing difference left to observe);
3. an unauthenticated server does not accept caller-supplied webhooks unless
   the operator allowlisted the destination.

No test here touches the network: DNS is replaced through the
``url_guard._resolve_host`` seam and httpx is mocked.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from llm_council.webhooks import url_guard
from llm_council.webhooks.dispatcher import WebhookDispatcher
from llm_council.webhooks.types import WebhookConfig, WebhookPayload
from llm_council.webhooks.url_guard import (
    WebhookTargetError,
    is_public_address,
    resolve_webhook_target,
)

PUBLIC_IP = "93.184.216.34"
ALLOW_ENV = "LLM_COUNCIL_WEBHOOK_ALLOWED_HOSTS"


def _payload() -> WebhookPayload:
    return WebhookPayload(
        event="council.complete", request_id="req-1", timestamp=datetime.now(), data={}
    )


def _dns(mapping):
    """Patch the resolver seam with a fixed host -> [addresses] table."""

    async def fake(host, port):
        if host not in mapping:
            raise OSError("NXDOMAIN")
        return list(mapping[host])

    return patch.object(url_guard, "_resolve_host", side_effect=fake)


@pytest.fixture(autouse=True)
def _no_allowlist(monkeypatch):
    monkeypatch.delenv(ALLOW_ENV, raising=False)


class TestIsPublicAddress:
    @pytest.mark.parametrize(
        "addr",
        [
            "127.0.0.1",
            "127.8.8.8",
            "0.0.0.0",
            "10.0.0.5",
            "172.16.3.4",
            "192.168.97.2",
            "169.254.169.254",  # cloud metadata
            "100.64.0.1",  # CGNAT
            "224.0.0.1",  # multicast
            "::1",
            "::",
            "fe80::1",
            "fe80::1%eth0",
            "fc00::1",
            "fd12:3456::1",
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "::ffff:10.0.0.1",
            "64:ff9b::7f00:1",  # NAT64-embedded loopback
            "64:ff9b::a9fe:a9fe",  # NAT64-embedded metadata
            "2002:7f00:1::1",  # 6to4-embedded loopback
            "not-an-ip",
        ],
    )
    def test_non_public_rejected(self, addr):
        assert is_public_address(addr) is False

    @pytest.mark.parametrize(
        "addr", [PUBLIC_IP, "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"]
    )
    def test_public_accepted(self, addr):
        assert is_public_address(addr) is True


class TestResolveWebhookTarget:
    async def test_public_https_is_pinned_to_checked_address(self):
        with _dns({"hooks.example.com": [PUBLIC_IP]}):
            target = await resolve_webhook_target("https://hooks.example.com/h?x=1")
        assert target.pinned_ip == PUBLIC_IP
        assert target.host == "hooks.example.com"

    @pytest.mark.parametrize(
        "url",
        [
            "https://127.0.0.1:9443/h",
            "https://192.168.97.2:9443/h",  # advisory case H
            "https://[::1]/h",
            "https://169.254.169.254/latest/meta-data/",
            "https://[::ffff:127.0.0.1]/h",
        ],
    )
    async def test_private_literal_rejected_without_resolving(self, url):
        with _dns({}) as resolver:
            with pytest.raises(WebhookTargetError):
                await resolve_webhook_target(url)
        resolver.assert_not_called()

    @pytest.mark.parametrize(
        "addrs",
        [
            ["127.0.0.1"],
            ["10.1.2.3"],
            ["169.254.169.254"],
            ["::1"],
            [PUBLIC_IP, "127.0.0.1"],  # one private record poisons the set
        ],
    )
    async def test_dns_name_resolving_to_private_rejected(self, addrs):
        with _dns({"internal.example.com": addrs}):
            with pytest.raises(WebhookTargetError):
                await resolve_webhook_target("https://internal.example.com/h")

    @pytest.mark.parametrize("host", ["localhost", "2130706433", "0x7f.1", "127.1"])
    async def test_loopback_spellings_rejected(self, host):
        # Whatever the spelling, the verdict is on the resolved address.
        with _dns({host: ["127.0.0.1"]}):
            with pytest.raises(WebhookTargetError):
                await resolve_webhook_target(f"https://{host}/h")

    async def test_http_localhost_no_longer_exempt(self):
        # Advisory case A: the old unconditional dev exception.
        for url in ("http://127.0.0.1:9999/hook", "http://localhost:9999/hook", "http://[::1]/h"):
            with _dns({"localhost": ["127.0.0.1"]}):
                with pytest.raises(WebhookTargetError):
                    await resolve_webhook_target(url)

    async def test_address_check_survives_https_only_off(self):
        # https_only=False relaxes the SCHEME only, never the address check.
        with pytest.raises(WebhookTargetError):
            await resolve_webhook_target("http://127.0.0.1:9999/h", https_only=False)
        with _dns({"hooks.example.com": [PUBLIC_IP]}):
            target = await resolve_webhook_target("http://hooks.example.com/h", https_only=False)
        assert target.pinned_ip == PUBLIC_IP

    @pytest.mark.parametrize(
        "url",
        ["ftp://hooks.example.com/h", "file:///etc/passwd", "gopher://x/", "https:///nohost", ""],
    )
    async def test_bad_scheme_or_host_rejected(self, url):
        with _dns({"hooks.example.com": [PUBLIC_IP]}):
            with pytest.raises(WebhookTargetError):
                await resolve_webhook_target(url, https_only=False)

    async def test_unresolvable_rejected(self):
        with _dns({}):
            with pytest.raises(WebhookTargetError):
                await resolve_webhook_target("https://nope.example.com/h")

    async def test_unresolvable_and_private_are_indistinguishable(self):
        # The message is logged; it must not turn into an internal-DNS oracle.
        with _dns({"internal.example.com": ["10.0.0.1"]}):
            with pytest.raises(WebhookTargetError) as private:
                await resolve_webhook_target("https://internal.example.com/h")
            with pytest.raises(WebhookTargetError) as missing:
                await resolve_webhook_target("https://nope.example.com/h")
        assert str(private.value) == str(missing.value)

    async def test_allowlisted_host_may_be_private_and_plain_http(self, monkeypatch):
        monkeypatch.setenv(ALLOW_ENV, "n8n, LocalHost:5678 ,[::1]:5678")
        with _dns({}) as resolver:
            a = await resolve_webhook_target("http://n8n:5678/webhook/x")
            b = await resolve_webhook_target("http://localhost:5678/webhook/x")
            c = await resolve_webhook_target("http://[::1]:5678/webhook/x")
        assert a.allowlisted and b.allowlisted and c.allowlisted
        assert a.pinned_ip is None
        resolver.assert_not_called()  # operator-trusted: connect as written

    async def test_allowlist_port_is_exact(self, monkeypatch):
        monkeypatch.setenv(ALLOW_ENV, "localhost:5678")
        with _dns({"localhost": ["127.0.0.1"]}):
            with pytest.raises(WebhookTargetError):
                await resolve_webhook_target("http://localhost:6379/")

    async def test_allowlist_is_not_a_suffix_or_userinfo_match(self, monkeypatch):
        monkeypatch.setenv(ALLOW_ENV, "n8n")
        with _dns({"n8n.evil.example": ["127.0.0.1"], "evil.example": ["127.0.0.1"]}):
            for url in ("https://n8n.evil.example/", "https://n8n@evil.example/"):
                with pytest.raises(WebhookTargetError):
                    await resolve_webhook_target(url)


def _mock_httpx(status=200):
    client_cls = patch("llm_council.webhooks.dispatcher.httpx.AsyncClient")
    return client_cls, MagicMock(status_code=status, headers={})


class TestDispatcherEnforcesGuard:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:9999/hook?case=A",
            "https://192.168.97.2:9443/hook",
            "https://internal.example.com/hook",
        ],
    )
    async def test_rejected_target_makes_no_connection_and_does_not_retry(self, url):
        dispatcher = WebhookDispatcher(max_retries=3)
        with _dns({"internal.example.com": ["10.0.0.9"]}):
            with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as client:
                with patch("llm_council.webhooks.dispatcher.asyncio.sleep") as sleep:
                    result = await dispatcher.dispatch(WebhookConfig(url=url), _payload())
        assert result.success is False
        client.assert_not_called()  # no socket ⇒ no open/closed timing signal
        sleep.assert_not_called()

    async def test_rejection_error_does_not_echo_the_url(self):
        # The error is logged; a caller-controlled URL must not reach the log.
        url = "http://127.0.0.1:9999/hook\nINJECTED"
        result = await WebhookDispatcher().dispatch(WebhookConfig(url=url), _payload())
        assert "INJECTED" not in (result.error or "")
        assert "9999" not in (result.error or "")

    async def test_public_target_connects_to_pinned_ip_with_original_host(self):
        dispatcher = WebhookDispatcher()
        config = WebhookConfig(url="https://hooks.example.com:8443/h?x=1")
        with _dns({"hooks.example.com": [PUBLIC_IP]}):
            with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as client:
                post = AsyncMock(return_value=MagicMock(status_code=200, headers={}))
                client.return_value.__aenter__.return_value.post = post
                result = await dispatcher.dispatch(config, _payload())

        assert result.success is True
        args, kwargs = post.call_args
        assert str(args[0]) == f"https://{PUBLIC_IP}:8443/h?x=1"
        assert kwargs["headers"]["Host"] == "hooks.example.com:8443"
        # TLS must still be verified against the NAME, not the pinned IP.
        assert kwargs["extensions"] == {"sni_hostname": "hooks.example.com"}
        assert client.call_args.kwargs["follow_redirects"] is False

    async def test_dns_resolved_once_across_retries(self):
        # Rebinding defence: a second lookup could return a different answer.
        dispatcher = WebhookDispatcher(max_retries=3)
        with _dns({"hooks.example.com": [PUBLIC_IP]}) as resolver:
            with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as client:
                post = AsyncMock(return_value=MagicMock(status_code=500, headers={}))
                client.return_value.__aenter__.return_value.post = post
                with patch("llm_council.webhooks.dispatcher.asyncio.sleep", new=AsyncMock()):
                    await dispatcher.dispatch(
                        WebhookConfig(url="https://hooks.example.com/h"), _payload()
                    )
        assert post.call_count == 3
        assert resolver.call_count == 1
        assert {str(c.args[0]) for c in post.call_args_list} == {f"https://{PUBLIC_IP}/h"}

    async def test_allowlisted_private_target_is_delivered_as_written(self, monkeypatch):
        monkeypatch.setenv(ALLOW_ENV, "localhost:5678")
        with patch("llm_council.webhooks.dispatcher.httpx.AsyncClient") as client:
            post = AsyncMock(return_value=MagicMock(status_code=200, headers={}))
            client.return_value.__aenter__.return_value.post = post
            result = await WebhookDispatcher().dispatch(
                WebhookConfig(url="http://localhost:5678/webhook/x"), _payload()
            )
        assert result.success is True
        assert str(post.call_args.args[0]) == "http://localhost:5678/webhook/x"


class TestHttpEndpointPolicy:
    """`POST /v1/council/run` — who may name a webhook destination at all."""

    BODY = {"prompt": "hi", "api_key": "placeholder-not-a-real-key"}

    def _post(self, extra, headers=None):
        from llm_council.http_server import app

        with patch("llm_council.http_server.run_full_council", new_callable=AsyncMock) as run:
            run.return_value = ([], [], {}, {})
            response = TestClient(app).post(
                "/v1/council/run", json={**self.BODY, **extra}, headers=headers or {}
            )
        return response, run

    def test_advisory_poc_refused_on_unauthenticated_server(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_API_TOKEN", raising=False)
        response, run = self._post(
            {
                "webhook_url": "http://127.0.0.1:9999/hook?case=A",
                "webhook_events": ["council.deliberation_start"],
            }
        )
        assert response.status_code == 403
        run.assert_not_called()

    def test_public_webhook_also_refused_without_token(self, monkeypatch):
        # No token ⇒ anyone who can reach the port could aim the server at a
        # third party. Not the server's call to make without an operator opt-in.
        monkeypatch.delenv("LLM_COUNCIL_API_TOKEN", raising=False)
        response, run = self._post({"webhook_url": "https://hooks.example.com/h"})
        assert response.status_code == 403
        assert "LLM_COUNCIL_API_TOKEN" in response.json()["detail"]
        assert ALLOW_ENV in response.json()["detail"]
        run.assert_not_called()

    def test_no_webhook_still_works_without_token(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_API_TOKEN", raising=False)
        response, run = self._post({})
        assert response.status_code == 200
        assert run.call_args.kwargs["webhook_config"] is None

    def test_allowlisted_host_accepted_without_token(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_API_TOKEN", raising=False)
        monkeypatch.setenv(ALLOW_ENV, "localhost:5678")
        response, run = self._post({"webhook_url": "http://localhost:5678/webhook/x"})
        assert response.status_code == 200
        assert run.call_args.kwargs["webhook_config"].url == "http://localhost:5678/webhook/x"

    def test_authenticated_public_webhook_accepted(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_API_TOKEN", "s3cret")
        response, run = self._post(
            {"webhook_url": "https://hooks.example.com/h"},
            headers={"Authorization": "Bearer s3cret"},
        )
        assert response.status_code == 200
        assert run.call_args.kwargs["webhook_config"].url == "https://hooks.example.com/h"

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:9999/hook",
            "https://192.168.97.2:9443/hook",
            "https://[::1]/hook",
            "http://hooks.example.com/h",  # plain http, https_only default
            "file:///etc/passwd",
        ],
    )
    def test_authenticated_caller_still_cannot_name_a_bad_literal(self, monkeypatch, url):
        # A token authenticates the caller; it does not make loopback a
        # legitimate destination. Fail early with 400 instead of silently.
        monkeypatch.setenv("LLM_COUNCIL_API_TOKEN", "s3cret")
        response, run = self._post({"webhook_url": url}, headers={"Authorization": "Bearer s3cret"})
        assert response.status_code == 400
        assert "9999" not in response.text
        run.assert_not_called()
