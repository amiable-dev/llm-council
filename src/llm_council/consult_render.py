"""Honest presentation of a consult result (#660).

The consult surface used to open every answer with ``### Chairman's Synthesis``
regardless of what happened, and to append the "N of M models" disclosure below
the content. A field report on v0.45.1 showed what that costs: a ``high``-tier
run lost the chairman and one member to timeout, fell back to a single surviving
member's *raw response*, and presented it under a heading that was wrong twice —
it was not a synthesis, and the chairman is what failed.

The disclosure is not merely a sampling caveat, either. Models that time out are
the slowest, which are generally the strongest reasoners, so the survivor set is
skewed toward the faster and weaker members. A reader who skims past a footnote
treats one fast model's take as a deliberated verdict.

So the rules here are:

1. The heading is a function of the outcome, never a constant.
2. Degradation is disclosed *above* the content it qualifies.
3. A machine-readable block accompanies every answer — emitted unconditionally,
   because a block that appears only on failure is one more thing a caller has
   to detect by parsing prose.

Pure functions, no I/O: the council decides what happened, this module only says
so. Consumed by ``mcp_server.consult_council``.
"""

import json
from typing import Any, Dict, List, Optional

__all__ = [
    "responded_models",
    "failed_models",
    "peer_review_ran",
    "synthesis_heading",
    "degradation_notice",
    "status_block",
    "render_consult_body",
]

# Synthesis types that mean "stage 2 never ran" — the quick_synthesis fallback
# path skips peer review entirely, which is most of what a council *is*.
_NO_PEER_REVIEW = frozenset({"partial", "stage1_only", "single_model_raw", "none"})

_OK = "ok"


def responded_models(model_responses: Dict[str, Dict[str, Any]]) -> List[str]:
    """Models that returned a usable stage-1 response."""
    return [m for m, info in model_responses.items() if info.get("status") == _OK]


def failed_models(model_responses: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    """Every model that did not respond, with the reason it didn't."""
    return [
        {"model": model, "status": info.get("status", "unknown")}
        for model, info in model_responses.items()
        if info.get("status") != _OK
    ]


def peer_review_ran(metadata: Dict[str, Any]) -> bool:
    """Whether stage 2 completed — the difference between a council and a poll."""
    return metadata.get("synthesis_type", "none") not in _NO_PEER_REVIEW


def _counts(metadata: Dict[str, Any], model_responses: Dict[str, Dict[str, Any]]) -> tuple:
    """(responded, requested), preferring the council's own accounting.

    ``completed_models`` can legitimately differ from the number of ok statuses
    (a model may answer stage 1 and then drop out), so trust metadata first and
    fall back to counting only when it is absent.
    """
    responded = metadata.get("completed_models")
    if responded is None:
        responded = len(responded_models(model_responses))
    requested = metadata.get("requested_models")
    if requested is None:
        requested = len(model_responses) or responded
    return responded, requested


def synthesis_heading(
    metadata: Dict[str, Any], model_responses: Dict[str, Dict[str, Any]]
) -> str:
    """The heading this particular result has earned.

    ``### Chairman's Synthesis`` is reserved for output the chairman actually
    produced. Everything else says what it is in the heading itself, because
    that is the one line a skim-reader is guaranteed to see.
    """
    status = metadata.get("status")
    synthesis_type = metadata.get("synthesis_type")
    responded, requested = _counts(metadata, model_responses)

    if status == "failed" or synthesis_type == "none":
        return "### Council Failed"

    if synthesis_type == "single_model_raw":
        # Not a synthesis at all: the chairman failed, so this is one surviving
        # member's raw text, chosen arbitrarily among the survivors.
        source = metadata.get("fallback_source_model", "unknown model")
        return (
            f"### Single-model response from {source} — council incomplete "
            f"({responded}/{requested}), chairman unavailable"
        )

    if synthesis_type in _NO_PEER_REVIEW:
        # quick_synthesis did produce a synthesis, but over stage-1 drafts only.
        return (
            f"### Partial synthesis — {responded} of {requested} models, no peer review"
        )

    if synthesis_type == "full" and status == "complete":
        return "### Chairman's Synthesis"

    if synthesis_type == "full":
        # Stage 2 ran and the chairman synthesised; only the membership was
        # short. That is still a chairman synthesis — with the shortfall named.
        return f"### Chairman's Synthesis — {responded} of {requested} models"

    # Unknown/absent status: fail honest rather than inheriting the success
    # heading by default. An unlabelled result is the failure mode this module
    # exists to prevent.
    return f"### Council response — status unknown ({responded}/{requested} models)"


def degradation_notice(metadata: Dict[str, Any]) -> Optional[str]:
    """The human-readable "what you are not getting" line, or None if complete."""
    warning = metadata.get("warning")
    if not warning:
        return None
    return f"> **Note**: {warning}"


def status_block(
    metadata: Dict[str, Any], model_responses: Dict[str, Dict[str, Any]]
) -> str:
    """Machine-readable outcome, so a caller can branch without parsing prose.

    Emitted for complete runs too: a block that shows up only on degradation is
    itself something you have to detect.
    """
    responded, requested = _counts(metadata, model_responses)
    payload = {
        "status": metadata.get("status", "unknown"),
        "synthesis_type": metadata.get("synthesis_type", "unknown"),
        "models_responded": responded,
        "models_requested": requested,
        "peer_review": peer_review_ran(metadata),
        "tier": metadata.get("tier"),
        "failed_models": failed_models(model_responses),
    }
    return "```json\n" + json.dumps(payload) + "\n```"


def render_consult_body(
    metadata: Dict[str, Any],
    model_responses: Dict[str, Dict[str, Any]],
    synthesis: str,
) -> str:
    """Heading, then the caveat, then the content it qualifies."""
    parts = [synthesis_heading(metadata, model_responses)]
    notice = degradation_notice(metadata)
    if notice:
        parts.append(notice)
    parts.append(synthesis)
    return "\n\n".join(parts) + "\n"
