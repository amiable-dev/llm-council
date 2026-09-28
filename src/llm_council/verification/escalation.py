"""Retry guidance for a verify that ran out of time (#597).

Re-running the same or a lower tier during a slow-provider window is
self-defeating: a lower tier has a SHORTER global deadline (tier deadline ×
``VERIFICATION_TIMEOUT_MULTIPLIER``), so it starves the chairman harder. In the
2026-07-16 outage a quick-tier retry timed out while a balanced run seven
minutes later passed, largely because it had 3× the headroom.

``retry_hint`` is advice, not action: nothing here re-runs anything.
Automatic escalation would change cost and latency, so it belongs behind an
opt-in and an audit event (ADR-044), not in this helper.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

#: Tiers in increasing global-deadline order (test-pinned against the
#: contracts). ``frontier`` is deliberately absent: it is a model-lifecycle
#: tier, not a bigger budget, so it is never suggested and never escalated from.
TIER_LADDER = ("quick", "balanced", "high", "reasoning")

#: ``error_status`` the chairman call reports when its own timeout fired.
_STAGE3_TIMEOUT_STATUS = "timeout"


def retry_hint(
    tier: str,
    *,
    unclear_reason: Optional[str],
    completed_stages: Iterable[str],
    stage3_error_status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """What to do next when a run was starved of time, else None.

    Fires on the global deadline (``unclear_reason == "timeout"``) and on a
    chairman call that hit its own timeout (``infra_failure`` with
    ``error_status == "timeout"``, the #686 path). A genuine infra failure
    (auth, billing, rate limit, transport) gets no hint: retrying the same
    tier is the right response there.
    """
    starved_chairman = (
        unclear_reason == "infra_failure" and stage3_error_status == _STAGE3_TIMEOUT_STATUS
    )
    if unclear_reason != "timeout" and not starved_chairman:
        return None

    done = set(completed_stages)
    reason = "synthesis_starved" if "stage2" in done else "deadline_exhausted"

    if tier in TIER_LADDER[:-1]:
        up = TIER_LADDER[TIER_LADDER.index(tier) + 1]
        return {
            "action": "escalate_tier",
            "suggested_tier": up,
            "reason": reason,
            "message": (
                f"Retry at tier={up}: it has a longer deadline. Do not retry at "
                f"the same or a lower tier; a lower tier has less time, not more."
            ),
        }
    return {
        "action": "reduce_scope",
        "suggested_tier": None,
        "reason": reason,
        "message": (
            f"tier={tier} has no higher tier to escalate to. Reduce the scope "
            f"(fewer or smaller target_paths). Do not retry at the same or a "
            f"lower tier; a lower tier has less time, not more."
        ),
    }
