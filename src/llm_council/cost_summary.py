"""Human/LLM-facing cost + token summary formatting (ADR-011 Phase 1).

Progressive disclosure: ``format_cost_summary`` returns a single dense line by
default (safe for a calling LLM's context window) and the full per-model /
per-stage breakdown only when ``include_details=True``. It consumes the
``metadata["usage"]`` structure produced by ``council._build_usage_summary``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _fmt_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _fmt_cost(cost: float) -> str:
    return f"${cost:.4f}"


def format_cost_summary(
    usage: Optional[Dict[str, Any]], *, include_details: bool = False
) -> str:
    """Format a usage block for display.

    Returns an empty string when there is no usage data. The default (one-line)
    form is what surfaces in a chat by default; the full breakdown is gated
    behind ``include_details`` so it never floods the caller's context.
    """
    if not usage:
        return ""

    total = usage.get("total") or {}
    total_tokens = total.get("total_tokens", 0)
    cost = total.get("cost_usd", 0.0) or 0.0
    # Distinguish a genuine, reported $0 (free/local models) from unknown cost:
    # show the figure when a cost was actually reported OR is positive; omit it
    # only when cost is truly unknown.
    cost_known = bool(total.get("cost_known", False)) or cost > 0

    line = f"Council usage: ~{_fmt_tokens(total_tokens)} tokens"
    if cost_known:
        line += f" · ~{_fmt_cost(cost)}"
    cached = total.get("cached_tokens", 0)
    if cached:
        line += f" · {_fmt_tokens(cached)} cached"

    if not include_details:
        return line

    lines = [line]
    by_model = usage.get("by_model") or {}
    if by_model:
        lines += ["", "**By model:**"]
        for model, mu in by_model.items():
            entry = f"- {model}: {mu.get('total_tokens', 0)} tok"
            mc = mu.get("cost_usd", 0.0) or 0.0
            if mc:
                entry += f", {_fmt_cost(mc)}"
            lines.append(entry)

    by_stage = usage.get("by_stage") or {}
    if by_stage:
        lines += ["", "**By stage:**"]
        for stage, su in by_stage.items():
            tok = su.get("total_tokens", 0)
            if not tok:
                continue
            entry = f"- {stage}: {tok} tok"
            sc = su.get("cost_usd", 0.0) or 0.0
            if sc:
                entry += f", {_fmt_cost(sc)}"
            lines.append(entry)

    return "\n".join(lines)
