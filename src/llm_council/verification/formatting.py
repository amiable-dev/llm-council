"""
Verification result formatting per ADR-034.

Provides human-readable formatted output for verification results
with emoji indicators, tables, and structured sections.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# Verdict emoji mapping
VERDICT_EMOJIS = {
    "pass": "✅",
    "fail": "❌",
    "unclear": "⚠️",
}

# Rubric dimension display names
RUBRIC_DIMENSIONS = [
    ("accuracy", "Accuracy"),
    ("relevance", "Relevance"),
    ("completeness", "Completeness"),
    ("conciseness", "Conciseness"),
    ("clarity", "Clarity"),
]


def format_verification_result(result: Dict[str, Any]) -> str:
    """
    Format verification result for human-readable display.

    Produces formatted output with:
    - Verdict with emoji indicator
    - Confidence score
    - Exit code
    - Rubric scores table
    - Blocking issues (if any)
    - Transcript location
    - Rationale summary

    Args:
        result: Verification result dictionary from run_verification()

    Returns:
        Formatted string suitable for terminal/markdown display
    """
    lines: List[str] = []

    # #357: an input-cap rejection is NOT a deliberated verdict — surface it as
    # a distinct banner so a caller (or an agent) never mistakes the resulting
    # "unclear" for a gate the council actually evaluated.
    if result.get("error") == "input_too_large":
        lines.append("Council Verification Result: INPUT TOO LARGE 🚫")
        lines.append("")
        lines.append(
            "> The council **did not run** — the input exceeded the tier's size "
            "limit, so this is NOT a pass/fail/unclear verdict and must not be "
            "treated as a passed gate. Reduce scope, split the input, or use a "
            "higher tier."
        )
        lines.append("")
        rationale = result.get("rationale", "")
        if rationale:
            lines.append(f"**Detail**: {rationale}")
            lines.append("")
        transcript = result.get("transcript_location", "")
        if transcript:
            lines.append(f"**Transcript**: {transcript}")
        return "\n".join(lines)

    # #704: same shape as input_too_large. The council never ran, so this is
    # not a verdict and must not be formatted like one.
    if result.get("error") == "no_reviewable_content":
        lines.append("Council Verification Result: NOTHING REVIEWED 🚫")
        lines.append("")
        lines.append(
            "> The council **did not run**: no reviewable file resolved from the "
            "snapshot, so this is NOT a pass/fail/unclear verdict and must not be "
            "treated as a passed gate."
        )
        lines.append("")
        rationale = result.get("rationale", "")
        if rationale:
            lines.append(f"**Detail**: {rationale}")
        return "\n".join(lines)

    # Header with verdict and emoji
    verdict = (result.get("verdict") or "unclear").lower()
    emoji = VERDICT_EMOJIS.get(verdict, "❓")
    lines.append(f"Council Verification Result: {verdict.upper()} {emoji}")
    lines.append("")

    # Metrics table
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")

    # Verdict row
    exit_code = result.get("exit_code", 2)
    lines.append(f"| Verdict | {verdict.upper()} (exit code {exit_code}) |")

    # Confidence row
    confidence = result.get("confidence", 0.0)
    lines.append(f"| Confidence | {confidence:.2f} |")

    # ADR-047 P2 (#414): show calibrated confidence when it diverges from raw
    confidence_calibrated = result.get("confidence_calibrated")
    if confidence_calibrated is not None and confidence_calibrated != confidence:
        lines.append(f"| Confidence (calibrated) | {confidence_calibrated:.2f} |")

    # ADR-047 P1 (#413): machine-readable UNCLEAR cause
    unclear_reason = result.get("unclear_reason")
    if unclear_reason:
        hints = {
            "infra_failure": "chairman call errored — check billing/auth, then retry",
            "low_confidence": "deliberation completed below threshold — accept-and-audit per policy",
            "timeout": "global deadline fired — re-tier or reduce scope",
            "chairman_disabled": "chairman synthesis was skipped by config — no verdict was computed",
        }
        hint = hints.get(unclear_reason, "")
        lines.append(f"| Unclear reason | {unclear_reason} ({hint}) |")

    # Rubric scores
    rubric_scores = result.get("rubric_scores", {})
    for key, display_name in RUBRIC_DIMENSIONS:
        score = rubric_scores.get(key)
        if score is not None:
            lines.append(f"| {display_name} | {score}/10 |")
        else:
            lines.append(f"| {display_name} | N/A |")

    lines.append("")

    # Blocking issues section
    blocking_issues = result.get("blocking_issues", [])
    lines.append("### Blocking Issues")
    if blocking_issues:
        for issue in blocking_issues:
            severity = issue.get("severity", "unknown")
            description = issue.get("description", "No description")
            location = issue.get("location")
            loc_str = f" ({location})" if location else ""
            lines.append(f"- **{severity.upper()}**: {description}{loc_str}")
    else:
        lines.append("None")

    lines.append("")

    # ADR-040: Timeout and partial result indicators
    timeout_fired = result.get("timeout_fired", False)
    partial = result.get("partial", False)
    completed_stages = result.get("completed_stages")

    if timeout_fired:
        lines.append(f"**Timeout**: Global deadline exceeded")
    if partial and completed_stages is not None:
        stages_str = ", ".join(completed_stages) if completed_stages else "none"
        lines.append(f"**Completed Stages**: {stages_str}")
    if timeout_fired or partial:
        lines.append("")

    # #704: name what was reviewed. A verdict line alone cannot show that the
    # council reviewed nothing, which is how an empty-subject gate passed three
    # PRs unnoticed. With the files listed, a reader of the CI step summary
    # can see the subject the verdict is about.
    coverage = result.get("coverage") or {}
    if coverage:
        reviewed = coverage.get("reviewed") or []
        omitted = coverage.get("omitted") or []
        lines.append(f"### Files reviewed ({len(reviewed)})")
        lines.extend(f"- {path}" for path in reviewed[:50])
        if len(reviewed) > 50:
            lines.append(f"- … and {len(reviewed) - 50} more")
        if omitted:
            lines.append(
                f"**Omitted ({len(omitted)})**: "
                + ", ".join(f"{o.get('path')} ({o.get('reason')})" for o in omitted[:20])
            )
        lines.append("")

    # Transcript location
    transcript = result.get("transcript_location", "")
    lines.append(f"**Transcript**: {transcript}")
    lines.append("")

    # Rationale (summarized)
    rationale = result.get("rationale", "No rationale provided.")
    lines.append("### Rationale")
    # Take first 3 sentences or 500 chars, whichever is shorter
    sentences = rationale.split(". ")
    summary = ". ".join(sentences[:3])
    if len(summary) > 500:
        summary = summary[:497] + "..."
    elif len(sentences) > 3:
        summary += "..."
    lines.append(summary)

    return "\n".join(lines)


def format_verification_result_compact(result: Dict[str, Any]) -> str:
    """
    Format verification result in compact single-line format.

    Useful for CI/CD logs where minimal output is preferred.

    Args:
        result: Verification result dictionary

    Returns:
        Single-line formatted string
    """
    verdict = result.get("verdict", "unclear").upper()
    emoji = VERDICT_EMOJIS.get(result.get("verdict", "unclear"), "❓")
    confidence = result.get("confidence", 0.0)
    exit_code = result.get("exit_code", 2)
    verification_id = result.get("verification_id", "unknown")

    # ADR-040: Append timeout/partial indicators for observability
    suffix = ""
    if result.get("timeout_fired"):
        suffix += " TIMEOUT"
    if result.get("partial"):
        stages = result.get("completed_stages", [])
        suffix += f" partial=[{','.join(stages)}]" if stages else " partial"

    return f"{emoji} {verdict} (confidence={confidence:.2f}, exit={exit_code}) [{verification_id}]{suffix}"
