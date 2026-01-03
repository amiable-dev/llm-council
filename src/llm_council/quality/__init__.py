"""
ADR-036: Output Quality Quantification (OQQ) Framework

Provides metrics for quantifying the reliability and quality of council outputs:

- Consensus Strength Score (CSS): Agreement among council members
- Deliberation Depth Index (DDI): Thoroughness of deliberation
- Synthesis Attribution Score (SAS): Grounding of synthesis in sources

Tier 1 (OSS): CSS, DDI, SAS - included in all responses
Tier 2 (Standard): Rubric breakdown, calibration reports, temporal consistency
Tier 3 (Enterprise): DeepEval/RAGAS integration, golden datasets, monitoring
"""

from .types import (
    QualityMetrics,
    CoreMetrics,
    SynthesisAttribution,
)

from .consensus import (
    consensus_strength_score,
    get_consensus_interpretation,
)

from .deliberation import (
    deliberation_depth_index,
    deliberation_depth_index_sync,
    EmbeddingProvider,
)

from .attribution import (
    synthesis_attribution_score,
    synthesis_attribution_score_sync,
)

from .integration import (
    calculate_quality_metrics,
    should_include_quality_metrics,
)

__all__ = [
    # Types
    "QualityMetrics",
    "CoreMetrics",
    "SynthesisAttribution",
    # Consensus
    "consensus_strength_score",
    "get_consensus_interpretation",
    # Deliberation
    "deliberation_depth_index",
    "deliberation_depth_index_sync",
    "EmbeddingProvider",
    # Attribution
    "synthesis_attribution_score",
    "synthesis_attribution_score_sync",
    # Integration
    "calculate_quality_metrics",
    "should_include_quality_metrics",
]
