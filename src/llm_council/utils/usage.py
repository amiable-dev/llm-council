"""Usage and cost aggregation utilities."""

from typing import Dict, Any


def _aggregate_stage_usage(
    usage_info: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """Aggregate per-stage usage dicts into a single totals dict."""
    stages = list(usage_info.values())
    return {
        "prompt_tokens": sum(u.get("prompt_tokens", 0.0) for u in stages),
        "completion_tokens": sum(u.get("completion_tokens", 0.0) for u in stages),
        "total_tokens": sum(u.get("total_tokens", 0.0) for u in stages),
        "total_cost": sum(u.get("total_cost", 0.0) for u in stages),
        "stages": usage_info,
    }
