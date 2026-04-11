"""Unified LLM Council Orchestrator (Facade).

This module act as the primary entry point for the Council system.
Implementation details are delegated to specialized sub-modules (stages, utils, config).
Backward compatibility is maintained for all legacy attributes and patching shims.
"""

import asyncio
import uuid
from typing import TYPE_CHECKING, List, Dict, Any, Tuple, Optional, Callable, Awaitable

# 1. Core Constants & Config (Centralized)
from llm_council.constants import (
    MODEL_STATUS_OK,
    TIMEOUT_PER_MODEL_HARD,
    TIMEOUT_SYNTHESIS_TRIGGER,
)
from llm_council.config_helpers import (
    _get_council_models,
    _get_chairman_model,
    _get_synthesis_mode,
    _get_exclude_self_votes,
    _get_style_normalization,
    _get_normalizer_model,
    _get_max_reviewers,
    _get_adversarial_mode,
    _get_adversarial_model,
    _get_cache_enabled,
    _check_patched_attr,
)

# 2. Re-export Stage Logic (Centralized)
from llm_council.stages.stage1 import (
    run_stage1,
    stage1_collect_responses,
    stage1_collect_responses_with_status,
    stage1_5_normalize_styles,
    should_normalize_styles,
)
from llm_council.stages.stage2 import (
    run_stage2,
    stage2_collect_rankings,
    calculate_aggregate_rankings,
    parse_ranking_from_text,
    detect_score_rank_mismatch,
    should_track_shadow_votes,
    emit_shadow_vote_events,
)
from llm_council.stages.stage3 import (
    run_stage3,
    stage3_synthesize_final,
    quick_synthesis,
)

# 3. Utility Re-exports
from llm_council.utils.usage import _aggregate_stage_usage
from llm_council.utils.formatting import (
    generate_partial_warning,
    generate_conversation_title,
)

# 4. Deferred/External Imports (maintained for backward compatibility)
from llm_council.gateway_adapter import (
    query_models_parallel,
    query_model,
    query_model_with_status,
    query_models_with_progress,
    STATUS_OK,
    STATUS_TIMEOUT,
    STATUS_RATE_LIMITED,
    STATUS_AUTH_ERROR,
    STATUS_ERROR,
)

from llm_council.bias_audit import (
    run_bias_audit,
    extract_scores_from_stage2,
    derive_position_mapping,
)
from llm_council.bias_persistence import persist_session_bias_data
from llm_council.cache import get_cache_key, get_cached_response, save_to_cache
from llm_council.dissent import extract_dissent_from_stage2
from llm_council.layer_contracts import (
    LayerEventType,
    emit_layer_event,
)
from llm_council.quality import (
    calculate_quality_metrics,
    should_include_quality_metrics,
)
from llm_council.safety_gate import (
    check_response_safety,
    apply_safety_gate_to_score,
)
from llm_council.telemetry import get_telemetry
from llm_council.verdict import VerdictType, VerdictResult
from llm_council.webhooks import WebhookConfig

# Extra constants for compatibility
MODEL_STATUS_AUTH_ERROR = STATUS_AUTH_ERROR
ProgressCallback = Callable[[int, int, str], Awaitable[None]]

# Type-only imports
if TYPE_CHECKING:
    from llm_council.tier_contract import TierContract

# =============================================================================
# Legacy Attribute Support (ADR-032)
# =============================================================================

_DEPRECATED_CONFIG_ATTRS = {
    "COUNCIL_MODELS": _get_council_models,
    "CHAIRMAN_MODEL": _get_chairman_model,
    "SYNTHESIS_MODE": _get_synthesis_mode,
    "EXCLUDE_SELF_VOTES": _get_exclude_self_votes,
    "STYLE_NORMALIZATION": _get_style_normalization,
    "NORMALIZER_MODEL": _get_normalizer_model,
    "MAX_REVIEWERS": _get_max_reviewers,
    "CACHE_ENABLED": _get_cache_enabled,
    "ADVERSARIAL_MODE": _get_adversarial_mode,
    "ADVERSARIAL_MODEL": _get_adversarial_model,
}


def __getattr__(name: str):
    """Provide lazy access to deprecated config constants for backward compatibility."""
    if name in _DEPRECATED_CONFIG_ATTRS:
        return _DEPRECATED_CONFIG_ATTRS[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# =============================================================================
# Main Orchestration Entry Points
# =============================================================================


async def run_full_council(
    user_query: str,
    bypass_cache: bool = False,
    on_progress: Optional[Callable] = None,
    tier_contract: Optional["TierContract"] = None,
    verdict_type: Optional[VerdictType] = None,
    include_dissent: bool = True,
    adversarial_mode: Optional[bool] = None,
    models: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    shared_raw_responses: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """
    Unified entry point for the 3-stage LLM Council pipeline.
    """
    if verdict_type is None:
        verdict_type = VerdictType.SYNTHESIS

    if session_id is None:
        session_id = str(uuid.uuid4())

    # --- PHASE 1: IDEATION ---
    stage1_data = await run_stage1(
        user_query,
        on_progress=on_progress,
        tier_contract=tier_contract,
        adversarial_mode=adversarial_mode,
        session_id=session_id,
        council_models=models,
        shared_raw_responses=shared_raw_responses,
    )

    # --- PHASE 2: PEER REVIEW ---
    stage2_data = await run_stage2(
        user_query,
        stage1_data,
        on_progress=on_progress,
        tier_contract=tier_contract,
        council_models=models,
    )

    # --- PHASE 3: SYNTHESIS ---
    stage3_data = await run_stage3(
        user_query,
        stage1_data,
        stage2_data,
        on_progress=on_progress,
        verdict_type=verdict_type,
        include_dissent=include_dissent,
    )

    # --- ENRICHMENT: Metadata & Telemetry ---
    overall_usage = _aggregate_stage_usage(
        {
            "stage1": stage1_data["usage"],
            "stage2": stage2_data["usage"],
            "stage3": stage3_data["usage"],
        }
    )

    quality_metrics = None
    if should_include_quality_metrics():
        stage1_responses_dict = {
            r["model"]: {"content": r["response"]} for r in stage1_data["stage1_results"]
        }
        agg_rank_tuples = [
            (r["model"], r["borda_score"] or 0.0) for r in stage2_data["aggregate_rankings"]
        ]
        quality_metrics = calculate_quality_metrics(
            stage1_responses=stage1_responses_dict,
            stage2_rankings=stage2_data["stage2_results"],
            stage3_synthesis={"content": stage3_data["chairman_result"]["response"]},
            aggregate_rankings=agg_rank_tuples,
            label_to_model=stage2_data["label_to_model"],
        )

    metadata = {
        "session_id": session_id,
        "status": "complete" if stage1_data["stage1_results"] else "failed",
        "models": [r["model"] for r in stage1_data["stage1_results"]],
        "usage": overall_usage,
        "quality": quality_metrics,
        "dissent_report": stage1_data.get("dissent_report"),
        "dissent": stage2_data.get("constructive_dissent"),
        "verdict": stage3_data.get("verdict_result"),
        "rankings": stage2_data["aggregate_rankings"],
        "model_statuses": stage1_data.get("model_statuses"),
        "requested_models": stage1_data.get("requested_models", 0),
        "completed_models": len(stage1_data.get("stage1_results", [])),
        "label_to_model": stage2_data["label_to_model"],
    }

    # Restore legacy 4-tuple return signature for backward compatibility
    # Format: (stage1_results, stage2_results, stage3_result, metadata)
    return (
        stage1_data["stage1_results"],
        stage2_data["stage2_results"],
        stage3_data["chairman_result"],
        metadata,
    )


async def run_council_with_fallback(
    user_query: str,
    bypass_cache: bool = False,
    on_progress: Optional[Callable] = None,
    synthesis_deadline: float = TIMEOUT_SYNTHESIS_TRIGGER,
    per_model_timeout: float = TIMEOUT_PER_MODEL_HARD,
    models: Optional[List[str]] = None,
    tier_contract: Optional["TierContract"] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Legacy entry point with robust timeout fallback (ADR-012).
    """
    session_id = str(uuid.uuid4())
    shared_raw_responses = {}

    try:
        pipeline_task = asyncio.create_task(
            run_full_council(
                user_query,
                bypass_cache=bypass_cache,
                on_progress=on_progress,
                tier_contract=tier_contract,
                models=models,
                adversarial_mode=kwargs.get("adversarial_mode"),
                session_id=session_id,
                shared_raw_responses=shared_raw_responses,
            )
        )

        stage1, stage2, stage3, metadata = await asyncio.wait_for(
            pipeline_task, timeout=synthesis_deadline
        )

        response = stage3["response"]
        label_mapping = metadata.get("label_to_model", {})
        rankings = metadata.get("rankings", [])

        return {
            "response": response,
            "synthesis": response,
            "metadata": metadata,
            "label_mapping": label_mapping,
            "rankings": rankings,
            "model_responses": metadata.get("model_statuses", {}),
            "model_statuses": metadata.get("model_statuses", {}),
            "requested_models": metadata.get("requested_models", 0),
            "completed_models": metadata.get("completed_models", 0),
            "synthesis_type": "full",
            "constructive_dissent": metadata.get("constructive_dissent"),
        }


    except (asyncio.TimeoutError, asyncio.CancelledError):
        if on_progress:
            try:
                await on_progress(
                    99, 100, "[!] Pipeline reached deadline, generating partial synthesis..."
                )
            except Exception:
                pass

        fallback_text, fallback_usage = await quick_synthesis(
            user_query, shared_raw_responses, council_id=session_id
        )

        fallback_metadata = {
            "session_id": session_id,
            "status": "partial",
            "is_partial": True,
            "usage": _aggregate_stage_usage({"fallback": fallback_usage}),
            "model_statuses": shared_raw_responses,
            "requested_models": len(models) if models else 0,
            "completed_models": len(
                [r for r in shared_raw_responses.values() if r.get("status") == STATUS_OK]
            ),
        }

        return {
            "response": fallback_text,
            "synthesis": fallback_text,
            "metadata": fallback_metadata,
            "label_mapping": {},
            "rankings": [],
            "model_responses": shared_raw_responses,
            "model_statuses": shared_raw_responses,
            "requested_models": fallback_metadata["requested_models"],
            "completed_models": fallback_metadata["completed_models"],
            "synthesis_type": "partial",
            "constructive_dissent": None,
        }
