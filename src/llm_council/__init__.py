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

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_config


def _get_council_config():
    """Get council configuration from unified config."""
    return get_config().council


# Module-level aliases for backwards compatibility (re-exports)
COUNCIL_MODELS = _get_council_config().models
CHAIRMAN_MODEL = _get_council_config().chairman
SYNTHESIS_MODE = _get_council_config().synthesis_mode
EXCLUDE_SELF_VOTES = _get_council_config().exclude_self_votes
STYLE_NORMALIZATION = _get_council_config().style_normalization

from llm_council.telemetry import (
    TelemetryProtocol,
    get_telemetry,
    set_telemetry,
    reset_telemetry,
)
from llm_council._version import __version__, __version_tuple__

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
    # Version
    "__version__",
    "__version_tuple__",
]
