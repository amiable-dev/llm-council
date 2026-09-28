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
from typing import Any, Dict, Optional, Tuple

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
                f"{_ENDPOINT_VAR} is set but the OpenTelemetry SDK is not "
                f"installed. Reinstall with the [otel] extra, or unset the "
                f"endpoint. Nothing is being reported externally."
            ),
        }
    return {"enabled": True, "reason": None, "endpoint": endpoint}


def _sdk_available() -> bool:
    """Whether the optional dependency is importable, without importing it.

    `find_spec` rather than a try/import, so that asking the question does not
    itself pull the SDK into a process that has no endpoint configured.
    """
    try:
        from importlib.util import find_spec

        return find_spec("opentelemetry.sdk") is not None
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


#: Below this, a negative difference is float residue, not an inconsistency.
_RESIDUE = 1e-9


def _finite_amount(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def cost_attributes(usage_summary: Dict[str, Any]) -> Dict[str, Any]:
    """The contract-v2 cost attributes for one run, each present only if known.

    Contract v2 (#707) separates what was **observed** from what was
    **estimated**:

    * ``std.external.cost_usd`` carries only observed spend. For a mixed run
      that is the total minus the estimated portion. Nothing downstream can
      catch a mistake here, because both numbers would look valid.
    * ``std.external.cost_source`` says how the observed part was come by:
      ``provider`` if any of it was provider-reported, else ``local`` (a
      structural zero). It is sent only alongside a ``cost_usd``.
    * ``std.external.cost_estimated_usd`` carries a #694 registry estimate, in
      its own attribute, so an estimate is never summed as a bill.

    Two rules this release has stated at every other layer still hold. An
    unobserved amount is **omitted**, never sent as 0 or null: a zero is a
    measurement. And an **incomplete** total, where some call reported no cost
    and the registry had no price, sends no ``cost_usd``: the observed sum is
    then a lower bound, and v2 has no attribute that says so.
    """
    total = usage_summary.get("total") or {}
    attrs: Dict[str, Any] = {}

    sources = set(total.get("cost_sources") or ())
    # A hand-built total (an older caller, or a test fixture) may carry only
    # the collapsed label. The real aggregate always carries the set.
    if not sources and total.get("cost_source") not in (None, "mixed"):
        sources = {total["cost_source"]}

    estimated = _finite_amount(total.get("cost_estimated_usd"))
    # Keyed on the SOURCE as well as the amount: a model the registry prices at
    # zero was estimated, at zero, and omitting that would make it read as no
    # estimate at all.
    if estimated is not None and (estimated > 0 or "registry_estimate" in sources):
        attrs["std.external.cost_estimated_usd"] = estimated

    if not total.get("cost_known") or total.get("cost_incomplete"):
        return attrs
    if "provider" in sources:
        contract_source = "provider"
    elif "local_zero" in sources:
        contract_source = "local"
    else:
        if not sources:
            # A cost with no provenance at all. v2 requires a source beside a
            # cost_usd, and inventing one would claim an observation, so it is
            # omitted, but not silently.
            logger.debug("omitting a cost with no provenance label from the external span")
        return attrs

    reported = _finite_amount(total.get("cost_usd"))
    if reported is None:
        return attrs
    observed = reported - (estimated or 0.0)
    if observed < -_RESIDUE:
        # An estimate larger than the total it is part of is not float residue;
        # the aggregate is inconsistent. Publishing it as a measured 0.0 would
        # hide that, so the observed amount is withheld.
        logger.debug(
            "omitting cost_usd: estimated portion exceeds the total (%s > %s)",
            estimated,
            reported,
        )
        return attrs
    # Float subtraction can leave -1e-18 where the answer is zero.
    attrs["std.external.cost_usd"] = max(0.0, round(observed, 12))
    attrs["std.external.cost_source"] = contract_source
    return attrs


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
    by_model = usage_summary.get("by_model") or {}

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
    # requests. `len(by_model)` survives only for a total built without the
    # counter (a hand-built fixture).
    requests = total.get("requests")
    if isinstance(requests, int) and not isinstance(requests, bool) and requests > 0:
        attrs["std.external.requests"] = requests
    elif by_model:
        attrs["std.external.requests"] = len(by_model)
    if duration_ms is not None:
        attrs["std.external.duration_ms"] = int(duration_ms)

    # A council has many models; the contract has one `gen_ai.request.model`.
    # The caller names the one that characterises the run (the chairman for a
    # synthesis), and it is omitted rather than guessed.
    if model:
        attrs["gen_ai.request.model"] = model

    for attr_key, usage_key in (
        ("gen_ai.usage.input_tokens", "prompt_tokens"),
        ("gen_ai.usage.output_tokens", "completion_tokens"),
        ("gen_ai.usage.cache_read_input_tokens", "cached_tokens"),
        ("gen_ai.usage.cache_creation_input_tokens", "cache_write_tokens"),
    ):
        value = total.get(usage_key)
        if isinstance(value, int) and not isinstance(value, bool):
            attrs[attr_key] = value

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
    """Emit one `external` activation span. Returns whether a span was sent.

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


def _get_tracer() -> Optional[Any]:
    """Lazily build a tracer, once. None when the SDK is unavailable."""
    global _tracer, _tracer_attempted
    if _tracer_attempted:
        return _tracer
    _tracer_attempted = True
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
        _tracer = trace.get_tracer(__name__, tracer_provider=provider)
    except Exception as exc:
        logger.debug("OpenTelemetry SDK unavailable: %s", type(exc).__name__)
        _tracer = None
    return _tracer


def _reset_for_tests() -> None:
    """Drop the memoised tracer so a test can change the environment."""
    global _tracer, _tracer_attempted
    _tracer = None
    _tracer_attempted = False
