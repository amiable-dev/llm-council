"""Post a human adjudication onto a verify trace (ADR-050 Part 3, revised).

The cross-repo hook: epic-loop's retro records a per-verification human
disposition (``real`` / ``marginal`` / ``refuted`` / ``pass-clean``) by
emitting a follow-up PostHog ``$ai_metric`` event keyed to the SAME
``$ai_trace_id = verification_id``. A numeric ``metric_value`` drives TPR/FPR
trends; a text ``adjudication_label`` carries the raw category.

This is NOT PostHog's automated Evaluations product (which runs LLM-as-a-judge
at sample time). The follow-up-event-by-trace_id join is the documented path.

**Verify-before-implementation** (ADR-050 §Decision Part 3): PostHog's public
docs don't pin ``$ai_metric``'s value type or whether a metric keyed to a
trace renders trace-scoped vs generation-scoped — confirm empirically against
the live project before relying on this in production. The fallback, if
``$ai_metric`` doesn't behave, is a plain custom event carrying the same
``$ai_trace_id``.
"""

from __future__ import annotations

import logging
from typing import Optional

from .ai_generation import DEFAULT_DISTINCT_ID
from .posthog_emitter import emit, posthog_emission_enabled, scrub_exception

logger = logging.getLogger(__name__)

# ADR-050 Part 3 vocabulary → numeric scalar (Council rev-2: numeric for trends
# AND a text label). real/pass-clean are "good" (1.0); refuted is "bad" (0.0);
# marginal sits between.
ADJUDICATION_VALUES = {
    "real": 1.0,
    "marginal": 0.5,
    "refuted": 0.0,
    "pass-clean": 1.0,
}


def emit_adjudication(
    verification_id: str,
    disposition: str,
    *,
    notes: Optional[str] = None,
    consumer: Optional[str] = None,
) -> None:
    """Emit an ``$ai_metric`` adjudication keyed to ``verification_id``.

    Input validation is UNCONDITIONAL: an invalid ``disposition`` raises
    ``ValueError`` even when emission is disabled, so a caller's typo surfaces
    immediately (the no-op-when-disabled contract governs the emission
    side-effect, not argument validation). Emission itself is soft-fail and
    opt-in.
    """
    # Required-input validation is unconditional and consistent: both a bad
    # disposition AND a missing verification_id are caller errors that must
    # surface even when emission is disabled.
    if disposition not in ADJUDICATION_VALUES:
        raise ValueError(
            f"disposition must be one of {sorted(ADJUDICATION_VALUES)}, "
            f"got {disposition!r}"
        )
    if not verification_id or not verification_id.strip():
        raise ValueError(
            "verification_id is required and non-blank (the $ai_trace_id to key the metric)"
        )
    if not posthog_emission_enabled():
        return
    try:
        props = {
            "$ai_trace_id": verification_id,
            "metric_name": "adjudication",
            "metric_value": ADJUDICATION_VALUES[disposition],
            "adjudication_label": disposition,
        }
        if notes and notes.strip():  # omit empty/whitespace-only notes
            props["adjudication_notes"] = notes
        # Empty/whitespace consumer falls back to the default actor.
        distinct_id = (consumer or "").strip() or DEFAULT_DISTINCT_ID
        emit("$ai_metric", props, distinct_id=distinct_id)
    except Exception as exc:  # telemetry must never break the caller
        logger.debug("emit_adjudication failed (ignored): %s", scrub_exception(exc))
