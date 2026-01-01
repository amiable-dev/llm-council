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

    # Header with verdict and emoji
    verdict = result.get("verdict", "unclear").lower()
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

    return f"{emoji} {verdict} (confidence={confidence:.2f}, exit={exit_code}) [{verification_id}]"
