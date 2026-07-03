"""Reviewer-agreement decomposition — bias-amplification check (ADR-047 P4, #416).

2026 judge research warns that multi-agent judges can AMPLIFY rather than
cancel shared bias: reviewers agreeing strongly is evidence of quality only
if their consensus does not simply track a shared confound. This module
decomposes agreement per session over the existing ADR-015/018 bias store:

- ``agreement_index`` — how much of the score variance is between models
  rather than between reviewers (ICC-flavoured; 1.0 = perfect convergence).
- ``position_alignment`` — Pearson correlation between each model's consensus
  score and its (negated) display position; high values mean the agreed
  ranking follows presentation order.
- ``amplification_suspect`` — high agreement AND high position alignment:
  the council converged, but along the position confound.

STRICTLY REPORT-ONLY (ADR-047 §P4): pure functions, no writes, no gating
side-effects. Same caveats as ADR-015: with 3–5 models per session these are
anomaly indicators, not significance tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .bias_persistence import BiasMetricRecord

AGREEMENT_THRESHOLD = 0.7
POSITION_ALIGNMENT_THRESHOLD = 0.5


@dataclass
class SessionDecomposition:
    """Agreement decomposition for one council session."""

    session_id: str
    n_reviewers: int
    n_models: int
    agreement_index: float
    position_alignment: float
    amplification_suspect: bool


def _pearson(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n < 2 or len(y) != n:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return 0.0
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / (sxx * syy) ** 0.5


def session_agreement_decomposition(
    records: List[BiasMetricRecord],
) -> List[SessionDecomposition]:
    """Decompose reviewer agreement per session. Pure; report-only."""
    by_session: Dict[str, List[BiasMetricRecord]] = {}
    for r in records:
        by_session.setdefault(r.session_id, []).append(r)

    out: List[SessionDecomposition] = []
    for session_id, rows in sorted(by_session.items()):
        reviewers = {r.reviewer_id for r in rows}
        models = {r.model_id for r in rows}
        if len(reviewers) < 2 or len(models) < 2:
            continue  # agreement needs at least two of each

        # Per-model score lists across reviewers + consensus means.
        scores_by_model: Dict[str, List[float]] = {}
        positions_by_model: Dict[str, List[float]] = {}
        for r in rows:
            scores_by_model.setdefault(r.model_id, []).append(r.score_value)
            # ADR-017 randomization can show the same model at DIFFERENT
            # positions per reviewer — average them (last-write-wins would
            # silently drop the counterbalancing, #437 review).
            positions_by_model.setdefault(r.model_id, []).append(float(r.position))
        position_by_model = {
            m: sum(ps) / len(ps) for m, ps in positions_by_model.items()
        }

        all_scores = [s for scores in scores_by_model.values() for s in scores]
        n = len(all_scores)
        grand_mean = sum(all_scores) / n
        total_var = sum((s - grand_mean) ** 2 for s in all_scores) / n
        # Within-model variance: how much reviewers disagree about the SAME
        # model. Agreement = the share of variance that is between models.
        within = 0.0
        for scores in scores_by_model.values():
            mean = sum(scores) / len(scores)
            within += sum((s - mean) ** 2 for s in scores)
        within /= n
        agreement_index = 1.0 - (within / total_var) if total_var > 0 else 0.0

        consensus = {m: sum(v) / len(v) for m, v in scores_by_model.items()}
        model_order = sorted(consensus)
        position_alignment = _pearson(
            [-position_by_model[m] for m in model_order],
            [consensus[m] for m in model_order],
        )

        # Earlier-is-better is the known confound, so only POSITIVE
        # alignment counts (a negative correlation is not the threat model).
        suspect = (
            agreement_index > AGREEMENT_THRESHOLD
            and position_alignment > POSITION_ALIGNMENT_THRESHOLD
        )
        out.append(
            SessionDecomposition(
                session_id=session_id,
                n_reviewers=len(reviewers),
                n_models=len(models),
                agreement_index=round(agreement_index, 3),
                position_alignment=round(position_alignment, 3),
                amplification_suspect=suspect,
            )
        )
    return out


def amplification_report(records: List[BiasMetricRecord]) -> Dict[str, Any]:
    """Aggregate the decomposition across sessions. Pure; report-only."""
    sessions = session_agreement_decomposition(records)
    high_agreement = [s for s in sessions if s.agreement_index > AGREEMENT_THRESHOLD]
    suspects = [s for s in sessions if s.amplification_suspect]
    return {
        "sessions_analyzed": len(sessions),
        "high_agreement_sessions": len(high_agreement),
        "amplification_suspects": len(suspects),
        "amplification_rate_among_agreement": (
            round(len(suspects) / len(high_agreement), 3) if high_agreement else 0.0
        ),
        "suspect_session_ids": [s.session_id for s in suspects],
        "mean_agreement_index": (
            round(sum(s.agreement_index for s in sessions) / len(sessions), 3)
            if sessions
            else None
        ),
        "report_only": True,  # ADR-047 P4 invariant: never gates anything
    }


def format_amplification_report(report: Dict[str, Any]) -> str:
    """Human-readable rendering for the CLI."""
    lines = ["## Reviewer-Agreement Decomposition (ADR-047 P4 — report-only)"]
    n = report["sessions_analyzed"]
    if n == 0:
        lines.append(
            "Insufficient data: no multi-reviewer sessions in the bias store."
        )
        return "\n".join(lines)
    lines.append(f"Sessions analyzed: {n}")
    lines.append(
        f"High-agreement sessions (index > {AGREEMENT_THRESHOLD}): "
        f"{report['high_agreement_sessions']}"
    )
    lines.append(
        f"Amplification suspects (agreement tracks display position): "
        f"{report['amplification_suspects']} "
        f"({report['amplification_rate_among_agreement']:.0%} of high-agreement)"
    )
    if report["suspect_session_ids"]:
        lines.append(f"Suspect sessions: {', '.join(report['suspect_session_ids'])}")
    lines.append(f"Mean agreement index: {report['mean_agreement_index']}")
    lines.append(
        "Interpretation: convergence WITH position alignment suggests reviewers "
        "amplified a shared position confound rather than judging quality. "
        "Anomaly indicator only (N per session is small); no gating occurs."
    )
    return "\n".join(lines)
