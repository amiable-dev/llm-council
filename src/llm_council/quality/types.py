"""
ADR-036: Output Quality Quantification - Type Definitions

Core dataclasses for the 3-tier quality metrics framework.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass(frozen=True)
class SynthesisAttribution:
    """
    Synthesis Attribution Score (SAS) result.

    Measures how well the final synthesis traces back to peer-reviewed responses.
    """

    winner_alignment: float
    """Cosine similarity between synthesis and top-ranked responses (0.0-1.0)."""

    max_source_alignment: float
    """Best match to any Stage 1 response (0.0-1.0)."""

    hallucination_risk: float
    """Risk of novel claims not grounded in sources: 1.0 - max_source_alignment."""

    grounded: bool
    """True if max_source_alignment > 0.6 (synthesis traces to sources)."""


@dataclass(frozen=True)
class CoreMetrics:
    """
    Tier 1 (OSS) quality metrics - included in all council responses.

    These metrics leverage the unique multi-model deliberation architecture
    to provide signals unavailable from single-model systems.
    """

    consensus_strength: float
    """
    Consensus Strength Score (CSS): 0.0-1.0

    Quantifies agreement among council members during Stage 2 peer review.
    - 0.85-1.0: Strong consensus, high confidence
    - 0.70-0.84: Moderate consensus, note minority views
    - 0.50-0.69: Weak consensus, consider include_dissent=true
    - <0.50: Significant disagreement, recommend debate mode
    """

    deliberation_depth: float
    """
    Deliberation Depth Index (DDI): 0.0-1.0

    Quantifies how thoroughly the council considered the query.
    Components: response diversity (35%), review coverage (35%), critique richness (30%).
    """

    synthesis_attribution: SynthesisAttribution
    """Attribution analysis for the Stage 3 synthesis."""


@dataclass(frozen=True)
class QualityMetrics:
    """
    Complete quality metrics container for council responses.

    Supports 3 tiers: core (OSS), standard (paid), enterprise (paid).
    """

    tier: str
    """Quality tier: 'core', 'standard', or 'enterprise'."""

    core: CoreMetrics
    """Tier 1 metrics - always included."""

    # Tier 2 (Standard) metrics - populated when tier in ('standard', 'enterprise')
    rubric_breakdown: Optional[dict] = None
    """Per-dimension rubric scores when ADR-016 scoring is enabled."""

    calibration_notes: Optional[List[str]] = None
    """Cross-model calibration observations."""

    temporal_consistency: Optional[float] = None
    """Temporal Consistency Score (TCS) for similar past queries."""

    # Tier 3 (Enterprise) metrics - populated when tier == 'enterprise'
    external_validation: Optional[dict] = None
    """DeepEval/RAGAS validation results."""

    regression_baseline_delta: Optional[float] = None
    """Delta from golden dataset baseline."""

    # Metadata
    warnings: List[str] = field(default_factory=list)
    """Quality warnings (e.g., 'low_consensus', 'hallucination_risk')."""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "tier": self.tier,
            "core": {
                "consensus_strength": self.core.consensus_strength,
                "deliberation_depth": self.core.deliberation_depth,
                "synthesis_attribution": {
                    "winner_alignment": self.core.synthesis_attribution.winner_alignment,
                    "max_source_alignment": self.core.synthesis_attribution.max_source_alignment,
                    "hallucination_risk": self.core.synthesis_attribution.hallucination_risk,
                    "grounded": self.core.synthesis_attribution.grounded,
                },
            },
        }

        # Include tier 2 metrics if available
        if self.tier in ("standard", "enterprise"):
            if self.rubric_breakdown is not None:
                result["standard"] = {"rubric_breakdown": self.rubric_breakdown}
            if self.calibration_notes:
                result.setdefault("standard", {})["calibration_notes"] = self.calibration_notes
            if self.temporal_consistency is not None:
                result.setdefault("standard", {})["temporal_consistency"] = (
                    self.temporal_consistency
                )

        # Include tier 3 metrics if available
        if self.tier == "enterprise":
            if self.external_validation is not None:
                result["enterprise"] = {"external_validation": self.external_validation}
            if self.regression_baseline_delta is not None:
                result.setdefault("enterprise", {})["regression_baseline_delta"] = (
                    self.regression_baseline_delta
                )

        # Include warnings if any
        if self.warnings:
            result["quality_alerts"] = self.warnings

        return result
