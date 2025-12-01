"""LLM Council - Multi-LLM council system with peer review and synthesis.

Usage:
    from llm_council import run_full_council

    # Run the full 3-stage council process
    stage1, stage2, stage3, metadata = await run_full_council(
        "What's the best approach for error handling?"
    )
    print(stage3["response"])

For MCP server usage:
    pip install "llm-council[mcp]"
    llm-council
"""

from llm_council.council import (
    run_full_council,
    stage1_collect_responses,
    stage1_5_normalize_styles,
    stage2_collect_rankings,
    stage3_synthesize_final,
    calculate_aggregate_rankings,
    parse_ranking_from_text,
)
from llm_council.config import (
    COUNCIL_MODELS,
    CHAIRMAN_MODEL,
    SYNTHESIS_MODE,
    EXCLUDE_SELF_VOTES,
    STYLE_NORMALIZATION,
)
from llm_council.telemetry import (
    TelemetryProtocol,
    get_telemetry,
    set_telemetry,
    reset_telemetry,
)

__all__ = [
    # Core orchestration
    "run_full_council",
    "stage1_collect_responses",
    "stage1_5_normalize_styles",
    "stage2_collect_rankings",
    "stage3_synthesize_final",
    # Utilities
    "calculate_aggregate_rankings",
    "parse_ranking_from_text",
    # Configuration
    "COUNCIL_MODELS",
    "CHAIRMAN_MODEL",
    "SYNTHESIS_MODE",
    "EXCLUDE_SELF_VOTES",
    "STYLE_NORMALIZATION",
    # Telemetry
    "TelemetryProtocol",
    "get_telemetry",
    "set_telemetry",
    "reset_telemetry",
]
