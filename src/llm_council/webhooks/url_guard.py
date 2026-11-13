"""Webhook destination guard (GHSA-r7rh-j9cj-h9hh, CWE-918).

A webhook URL is chosen by whoever calls the HTTP API, and the server then
connects to it. Without a guard that is server-side request forgery: the
caller can aim the server at its own loopback services, at private hosts, or
at a cloud metadata endpoint.

Rules, in order:

1. **Operator allowlist** — a host listed in ``LLM_COUNCIL_WEBHOOK_ALLOWED_HOSTS``
   (``host`` or ``host:port``, comma-separated, exact match) is trusted as
   written: it may be private and may use plain http. This is the only way to
   reach a non-public destination (a local n8n, a compose-network service).
2. **Scheme** — ``https`` only, or ``http``/``https`` when ``https_only`` is off.
   ``https_only`` relaxes the scheme and nothing else.
3. **Address** — the verdict is on the address the host RESOLVES to, never on
   how the URL is spelled (``localhost``, ``127.1``, ``2130706433``, an
   attacker's DNS name with an A record of ``10.0.0.1`` all end up here). Every
   resolved address must be public; one private record rejects the set.
4. **Pin** — the caller connects to the address that was checked
   (``WebhookTarget.pinned_ip``), so a second DNS answer cannot differ
   (DNS rebinding).

Rejections carry one fixed message per class and never echo the URL: the text
is logged, and "does not resolve" must be indistinguishable from "resolves to
a private address" or the log/behaviour becomes an internal-DNS oracle.
"""

import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Tuple, Union
from urllib.parse import urlsplit

ALLOWED_HOSTS_ENV = "LLM_COUNCIL_WEBHOOK_ALLOWED_HOSTS"

_DEFAULT_PORTS = {"http": 80, "https": 443}
_NAT64 = ipaddress.ip_network("64:ff9b::/96")

_MSG_MALFORMED = "Webhook URL is malformed or uses an unsupported scheme"
_MSG_HTTPS = "HTTPS required for webhook URLs"
_MSG_DESTINATION = (
    "Webhook destination is not permitted: it must resolve to public addresses, "
    f"or its host must be listed in {ALLOWED_HOSTS_ENV}"
)


class WebhookTargetError(ValueError):
    """A webhook URL that must not be connected to."""


@dataclass(frozen=True)
class WebhookTarget:
    """A webhook destination that passed the guard.

    ``pinned_ip`` is the checked address to connect to; ``None`` for an
    allowlisted host, which is connected to as written.
    """

    url: str
    scheme: str
    host: str
    port: int
    allowlisted: bool
    pinned_ip: Optional[str] = None


def is_public_address(addr: str) -> bool:
    """True only for a globally routable unicast address.

    IPv6 forms that embed an IPv4 address (IPv4-mapped, 6to4, NAT64) are judged
    by the embedded address — otherwise ``::ffff:127.0.0.1`` is a loopback
    bypass. Anything unparseable is not public.
    """
    try:
        ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address] = ipaddress.ip_address(
            addr.split("%", 1)[0]
        )
    except ValueError:
        return False

    if isinstance(ip, ipaddress.IPv6Address):
        if "%" in addr:
            return False  # zone-scoped ⇒ link-local by definition
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None:
            ip = embedded

    return bool(ip.is_global) and not ip.is_multicast


def allowed_hosts() -> FrozenSet[str]:
    """Operator allowlist, read per call so a restart is not needed in tests."""
    raw = os.environ.get("LLM_COUNCIL_WEBHOOK_ALLOWED_HOSTS", "")
    return frozenset(e.strip().lower().rstrip(".") for e in raw.split(",") if e.strip())


def _split(url: str) -> Tuple[str, str, int]:
    """Return (scheme, host, port) or raise WebhookTargetError."""
    try:
        parts = urlsplit(url)
        scheme = (parts.scheme or "").lower()
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except (ValueError, AttributeError):
        raise WebhookTargetError(_MSG_MALFORMED) from None
    if scheme not in _DEFAULT_PORTS or not host:
        raise WebhookTargetError(_MSG_MALFORMED)
    return scheme, host, port if port is not None else _DEFAULT_PORTS[scheme]


def _is_allowlisted(host: str, port: int) -> bool:
    allowed = allowed_hosts()
    if not allowed:
        return False
    bracketed = f"[{host}]" if ":" in host else host
    return host in allowed or bracketed in allowed or f"{bracketed}:{port}" in allowed


def is_allowlisted(url: str) -> bool:
    """True when the operator allowlisted this URL's host (or host:port)."""
    try:
        _, host, port = _split(url)
    except WebhookTargetError:
        return False
    return _is_allowlisted(host, port)


def check_webhook_url(url: str, https_only: bool = True) -> WebhookTarget:
    """Everything that can be decided WITHOUT resolving a name.

    Used at the HTTP boundary to fail early; ``resolve_webhook_target`` is the
    authoritative check and runs again at dispatch.
    """
    scheme, host, port = _split(url)
    if _is_allowlisted(host, port):
        return WebhookTarget(url=url, scheme=scheme, host=host, port=port, allowlisted=True)
    if https_only and scheme != "https":
        raise WebhookTargetError(_MSG_HTTPS)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return WebhookTarget(url=url, scheme=scheme, host=host, port=port, allowlisted=False)
    if not is_public_address(host):
        raise WebhookTargetError(_MSG_DESTINATION)
    return WebhookTarget(
        url=url, scheme=scheme, host=host, port=port, allowlisted=False, pinned_ip=host
    )


async def _resolve_host(host: str, port: int) -> List[str]:
    """Resolve ``host`` to its addresses. The seam tests replace."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def resolve_webhook_target(url: str, https_only: bool = True) -> WebhookTarget:
    """Validate ``url`` and return the destination to connect to.

    Raises:
        WebhookTargetError: the URL must not be connected to.
    """
    target = check_webhook_url(url, https_only=https_only)
    if target.allowlisted or target.pinned_ip is not None:
        return target

    try:
        addresses = await _resolve_host(target.host, target.port)
    except (OSError, UnicodeError):
        addresses = []
    if not addresses or not all(is_public_address(a) for a in addresses):
        raise WebhookTargetError(_MSG_DESTINATION)

    return WebhookTarget(
        url=url,
        scheme=target.scheme,
        host=target.host,
        port=target.port,
        allowlisted=False,
        pinned_ip=addresses[0],
    )
