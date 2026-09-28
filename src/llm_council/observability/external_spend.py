"""Opt-in OTLP spans reporting council spend (ADR-056, #695).

`skills-telemetry` attributes the cost of agent work to the artefacts that
caused it. Council spend is invisible to it: the harness sees that a command
ran, not what it cost. Its ADR-010 defines a fifth artefact kind, `external`,
for the one case it must *receive* rather than observe — a process the agent
shells out to, or reaches as an MCP server, that spends real money on models of
its own. This is council's half of that contract.

Off by default: with no ``OTEL_EXPORTER_OTLP_ENDPOINT`` the emitter is disabled,
the OpenTelemetry SDK is **never imported**, and every entry point is a no-op —
byte-identical to pre-ADR-056 behaviour. Emission is soft-fail: a missing SDK,
an unreachable collector or a malformed usage summary is logged at debug and
never raises into, or delays, a council run.

## The allowlist is the whole design

`EXTERNAL_ATTRIBUTES` is the single source of truth for what may be sent. It
matters more than it looks, because an attribute outside the published set is
**dropped silently downstream** rather than rejected: a typo here, or a rename
on their side, produces a column of nulls nobody can date rather than an error.

`tests/test_issue695_external_spend.py` writes the expected set out longhand
and compares it to this constant in both directions. A test that compared the
constant to itself would pass through any rename, which is the failure mode
this guards. `skills-telemetry` holds the mirror-image test on their side.

Pinned against the published contract: `stdtel` 0.5.0 (`contract_version` 2,
`stdtel-conform --print-contract`). v1 was pinned at commit `3d93d8b`; v2 (#707)
added cost provenance.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
from urllib.parse import urlsplit
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SPAN_NAME = "std.artefact.activation"
ARTEFACT_KIND = "external"
ARTEFACT_NAME = "llm-council"
EXTERNAL_SYSTEM = "llm-council"

#: `std.artefact.source` records HOW a value was come by. The other two values
#: in the vocabulary are not ours to use: `hook` means the Claude Code harness
#: handed it over, `transcript` means stdtel inferred it from a session file.
#: Nothing outside council's own process saw this spend, so either would assert
#: an observation that never happened, and their checker rejects them.
#: (The ticket said `hook` when filed; corrected upstream 2026-09-23.)
ARTEFACT_SOURCE = "emitter"

#: Bounded verbs. Never a description of the work — that would be free text on
#: a metrics dimension, and the contract has no room for it.
OPERATION_CONSULT = "consult"
OPERATION_VERIFY = "verify"
OPERATIONS = frozenset({OPERATION_CONSULT, OPERATION_VERIFY})

#: The published contract version this module implements. CI diffs it against
#: `stdtel-conform --print-contract`; a new version is announced on #707.
CONTRACT_VERSION = 2

#: The contract's `std.external.cost_source` vocabulary. Council's own labels
#: (`registry_estimate`, `local_zero`, `mixed`) are internal and are rejected by
#: `stdtel-conform`; they are translated below and never sent.
CONTRACT_COST_SOURCES = frozenset({"provider", "local"})

#: Exhaustive. Anything not here is dropped by the collector without complaint,
#: so this set is a contract, not a convenience. `std.scope.*` is deliberately
#: absent: stdtel sets it, not the emitter.
EXTERNAL_ATTRIBUTES = frozenset(
    {
        "std.artefact.kind",
        "std.artefact.name",
        "std.artefact.source",
        "std.external.system",
        "std.external.operation",
        "std.external.cost_usd",
        "std.external.cost_source",
        "std.external.cost_estimated_usd",
        "std.external.requests",
        "std.external.duration_ms",
        "gen_ai.request.model",
        "gen_ai.operation.name",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.cache_read_input_tokens",
        "gen_ai.usage.cache_creation_input_tokens",
        "session.id",
    }
)

#: A full UUID, which is what Claude Code exports. Their checker rejects a
#: `session.id` that is not in this shape, precisely so that stamping one of
#: council's own ids (an 8-char truncated UUID on the verify path, a full one
#: on the council path — neither of which joins to anything on the telemetry
#: side) fails loudly instead of producing rows that join to nothing.
_CLAUDE_SESSION_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_ENDPOINT_VAR = "OTEL_EXPORTER_OTLP_ENDPOINT"
_SESSION_VAR = "CLAUDE_CODE_SESSION_ID"


def external_spend_enabled() -> bool:
    """True iff an OTLP endpoint is configured (opt-in, off by default)."""
    return bool(os.getenv(_ENDPOINT_VAR, "").strip())


def telemetry_status() -> Dict[str, Any]:
    """What `council_health_check` reports about external spend telemetry.

    ADR-056 D8: a no-op emit path when the extra is absent is correct; silence
    is not. Without this, a council with no `[otel]` extra installed looks
    exactly like a council that spent nothing — which is the confusion #692
    exists to end, reintroduced one layer down.
    """
    endpoint = os.getenv(_ENDPOINT_VAR, "").strip()
    if not endpoint:
        return {
            "enabled": False,
            "reason": "no_endpoint",
            "detail": (
                f"{_ENDPOINT_VAR} is not set, so council spend is not reported "
                f"externally. Local cost records are unaffected."
            ),
        }
    if not _sdk_available():
        return {
            "enabled": False,
            "reason": "sdk_missing",
            "detail": (
                f"{_ENDPOINT_VAR} is set but the OpenTelemetry SDK or its OTLP/HTTP "
                f"exporter is not installed. Reinstall with the [otel] extra, or "
                f"unset the endpoint. Nothing is being reported externally."
            ),
        }
    return {"enabled": True, "reason": None, "endpoint": _redact_endpoint(endpoint)}


def _redact_endpoint(endpoint: str) -> str:
    """Scheme, host and port only. An OTLP endpoint can carry credentials in
    its userinfo or query string, and this value is shown in a health check."""
    try:
        parts = urlsplit(endpoint)
        if not parts.scheme or not parts.hostname:
            return "<configured>"
        # From netloc, minus any userinfo, so an IPv6 literal keeps its brackets.
        host = parts.netloc.rsplit("@", 1)[-1]
        return f"{parts.scheme}://{host}"
    except ValueError:
        return "<configured>"


def _sdk_available() -> bool:
    """Whether the optional dependency is importable, without importing it.

    `find_spec` rather than a try/import, so that asking the question does not
    itself pull the SDK into a process that has no endpoint configured.
    """
    try:
        from importlib.util import find_spec

        # Both, because they ship as separate distributions: with the SDK but
        # not the exporter, `_get_tracer` fails and every span is dropped.
        return all(
            find_spec(name) is not None
            for name in (
                "opentelemetry.sdk",
                "opentelemetry.exporter.otlp.proto.http.trace_exporter",
            )
        )
    except Exception:  # pragma: no cover - defensive
        return False


def claude_session_id() -> Optional[str]:
    """The **Claude** session id, or None.

    Council's own ids are not this. A CLI or CI run has no Claude session at
    all, and that is fine — ADR-056 D5 emits anyway, because a run that is
    never reported is spend that cannot be reconciled, and omits the attribute.
    Absent is honest; a made-up id is not.
    """
    raw = os.getenv(_SESSION_VAR, "").strip()
    # fullmatch: `$` under `re.match` accepts a trailing newline.
    return raw if raw and _CLAUDE_SESSION_RE.fullmatch(raw) else None


#: OTLP carries integers as int64.
_INT64_MAX = 2**63 - 1


def _finite_amount(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        amount = float(value)  # OverflowError for an int beyond float range
    except OverflowError:
        return None
    return amount if math.isfinite(amount) and amount >= 0 else None


def cost_attributes(usage_summary: Dict[str, Any]) -> Dict[str, Any]:
    """The contract-v2 cost attributes for one run, each present only if known.

    Contract v2 (#707) separates what was **observed** from what was
    **estimated**:

    * ``std.external.cost_usd`` carries only observed spend: the aggregate's
      own ``cost_observed_usd``, summed per call from provider and local
      figures. It is never derived by subtracting an estimate from a total,
      and nothing downstream could catch it if it were wrong, because every
      candidate number looks valid.
    * ``std.external.cost_source`` says how the observed part was come by:
      ``provider`` if any of it was provider-reported, else ``local`` (a
      structural zero). It is sent only alongside a ``cost_usd``.
    * ``std.external.cost_estimated_usd`` carries a #694 registry estimate, in
      its own attribute, so an estimate is never summed as a bill.

    Two rules this release has stated at every other layer still hold. An
    unobserved amount is **omitted**, never sent as 0 or null: a zero is a
    measurement. And an **incomplete** total, where some call reported no cost
    and the registry had no price, sends no cost attributes at all: both sums
    are then lower bounds, and v2 has no attribute that says so. An
    **unattributed** total, where some usable amount had no mappable
    provenance, sends none either.
    """
    try:
        return _cost_attributes(usage_summary.get("total") or {})
    except Exception as exc:  # a malformed summary must never raise
        logger.debug("omitting cost attributes from a malformed total: %s", type(exc).__name__)
        return {}


def _cost_attributes(total: Dict[str, Any]) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    # An incomplete total is a lower bound for BOTH amounts, and v2 has no
    # attribute that says so. So nothing is sent, not even the estimate.
    if total.get("cost_incomplete"):
        return attrs
    # A usable amount council could not attribute (no label, an unknown one, or
    # a non-zero `local_zero`) is inside the total with no provenance. Sending
    # the rest would still describe a total that is not what it says.
    if total.get("cost_unattributed"):
        logger.debug("omitting cost attributes: part of the total has no mappable provenance")
        return attrs

    raw_sources = total.get("cost_sources")
    sources = (
        {x for x in raw_sources if isinstance(x, str)}
        if isinstance(raw_sources, (list, tuple, set, frozenset))
        else set()
    )
    # A hand-built total (an older caller, or a test fixture) may carry only
    # the collapsed label. The real aggregate always carries the set.
    label = total.get("cost_source")
    if not sources and isinstance(label, str) and label != "mixed":
        sources = {label}
    unknown = sources - {"provider", "local_zero", "registry_estimate"}
    if unknown or (not sources and total.get("cost_known")):
        logger.debug(
            "omitting a cost with no mappable provenance from the external span: %s",
            sorted(unknown) or "none",
        )
        return attrs

    estimated = _finite_amount(total.get("cost_estimated_usd"))
    # Keyed on the SOURCE as well as the amount: a model the registry prices at
    # zero was estimated, at zero, and omitting that would make it read as no
    # estimate at all.
    if estimated is not None and (estimated > 0 or "registry_estimate" in sources):
        attrs["std.external.cost_estimated_usd"] = estimated

    if not total.get("cost_known"):
        return attrs
    if "provider" in sources:
        contract_source = "provider"
    elif "local_zero" in sources:
        contract_source = "local"
    else:
        return attrs  # estimate only: nothing was observed

    # The observed amount is tracked on its own by the aggregate, so it is
    # never derived by subtracting an estimate from a total. A hand-built total
    # without it may use `cost_usd` only when nothing in it was estimated.
    observed = _finite_amount(total.get("cost_observed_usd"))
    if observed is None and "registry_estimate" not in sources:
        observed = _finite_amount(total.get("cost_usd"))
    if observed is None:
        return attrs
    attrs["std.external.cost_usd"] = observed
    attrs["std.external.cost_source"] = contract_source
    return attrs


def _count(value: Any) -> Optional[int]:
    """A non-negative whole count, or None. The aggregate coerces a numeric
    string to a float, so an integral float is accepted and made an int."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= _INT64_MAX else None
    if isinstance(value, float) and math.isfinite(value) and value >= 0 and value.is_integer():
        return int(value) if value <= _INT64_MAX else None
    return None


def build_span_attributes(
    *,
    operation: str,
    usage_summary: Optional[Dict[str, Any]],
    duration_ms: Optional[int] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the attribute dict for one council run.

    Metadata only, by construction: nothing here reads a prompt, a response, a
    question, a file list or an argument. Every key is drawn from
    `EXTERNAL_ATTRIBUTES`, and the result is filtered against it as a
    belt-and-braces measure before return.
    """
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of {sorted(OPERATIONS)}, got {operation!r}")

    usage_summary = usage_summary or {}
    total = usage_summary.get("total") or {}

    attrs: Dict[str, Any] = {
        "std.artefact.kind": ARTEFACT_KIND,
        "std.artefact.name": ARTEFACT_NAME,
        "std.artefact.source": ARTEFACT_SOURCE,
        "std.external.system": EXTERNAL_SYSTEM,
        "std.external.operation": operation,
        "gen_ai.operation.name": "chat",
    }

    attrs.update(cost_attributes(usage_summary))

    # Calls, not distinct models: a model reviewed in all three stages is three
    # requests. A total without the counter omits the attribute; the distinct-
    # model count it used to fall back to is knowingly wrong.
    requests = _count(total.get("requests"))
    if requests is not None:
        attrs["std.external.requests"] = requests
    # A duration may be fractional milliseconds. Reject a negative BEFORE
    # truncating, or -0.4 would become a measured 0.
    if isinstance(duration_ms, float) and math.isfinite(duration_ms) and duration_ms >= 0:
        duration_ms = int(duration_ms)
    duration = _count(duration_ms)
    if duration is not None:
        attrs["std.external.duration_ms"] = duration

    # A council has many models; the contract has one `gen_ai.request.model`.
    # The caller names the one that characterises the run (the chairman for a
    # synthesis), and it is omitted rather than guessed.
    if isinstance(model, str) and model:
        attrs["gen_ai.request.model"] = model[:256]

    for attr_key, usage_key in (
        ("gen_ai.usage.input_tokens", "prompt_tokens"),
        ("gen_ai.usage.output_tokens", "completion_tokens"),
        ("gen_ai.usage.cache_read_input_tokens", "cached_tokens"),
        ("gen_ai.usage.cache_creation_input_tokens", "cache_write_tokens"),
    ):
        count = _count(total.get(usage_key))
        if count is not None:
            attrs[attr_key] = count

    session = claude_session_id()
    if session:
        attrs["session.id"] = session

    unknown = set(attrs) - EXTERNAL_ATTRIBUTES
    if unknown:  # pragma: no cover - the tests make this unreachable
        logger.debug("dropping attributes outside the contract: %s", sorted(unknown))
        for key in unknown:
            attrs.pop(key, None)
    return attrs


def emit_external_spend(
    *,
    operation: str,
    usage_summary: Optional[Dict[str, Any]],
    duration_ms: Optional[int] = None,
    model: Optional[str] = None,
) -> bool:
    """Emit one `external` activation span. Returns whether a span was handed to
    the exporter (queued for export, not confirmed delivered).

    Soft-fail and non-blocking by contract. With no endpoint this returns False
    before importing anything, so an install without the `[otel]` extra behaves
    exactly as it did before ADR-056.
    """
    if not external_spend_enabled():
        return False
    try:
        attrs = build_span_attributes(
            operation=operation,
            usage_summary=usage_summary,
            duration_ms=duration_ms,
            model=model,
        )
        tracer = _get_tracer()
        if tracer is None:
            return False
        with tracer.start_as_current_span(SPAN_NAME) as span:
            span.set_attributes(attrs)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("external spend emission failed: %s", type(exc).__name__)
        return False


_tracer: Optional[Any] = None
_tracer_attempted = False
_tracer_lock = threading.Lock()


def _get_tracer() -> Optional[Any]:
    """Lazily build a tracer, once. None when the SDK is unavailable."""
    global _tracer, _tracer_attempted
    if _tracer_attempted:
        return _tracer
    # The HTTP server and the MCP path can both reach here first; without the
    # lock each builds a provider and leaks an exporter thread.
    with _tracer_lock:
        if _tracer_attempted:
            return _tracer
        _tracer = _build_tracer()
        _tracer_attempted = True
    return _tracer


def _build_tracer() -> Optional[Any]:
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": ARTEFACT_NAME}))
        # Bounded: the batch processor flushes at interpreter exit, and an
        # unreachable collector must not hold an MCP server's shutdown for the
        # exporter's default 10s.
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(timeout=3), export_timeout_millis=3000)
        )
        return trace.get_tracer(__name__, tracer_provider=provider)
    except Exception as exc:
        logger.debug("OpenTelemetry SDK unavailable: %s", type(exc).__name__)
        return None


def _reset_for_tests() -> None:
    """Drop the memoised tracer so a test can change the environment."""
    global _tracer, _tracer_attempted
    with _tracer_lock:
        _tracer = None
        _tracer_attempted = False
