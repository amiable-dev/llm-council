"""Unified LLM Council Orchestrator (Facade).

This module act as the primary entry point for the Council system.
Implementation details are delegated to specialized sub-modules (stages, utils, config).
Backward compatibility is maintained for all legacy attributes and patching shims.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Dict, Any, Tuple, Optional, Callable, Awaitable

# 1. Core Constants & Config (Centralized)
from llm_council.constants import (
    MODEL_STATUS_OK,
    MODEL_STATUS_TIMEOUT,
    MODEL_STATUS_ERROR,
    MODEL_STATUS_RATE_LIMITED,
    TIMEOUT_PER_MODEL_SOFT,
    TIMEOUT_PER_MODEL_HARD,
    TIMEOUT_SYNTHESIS_TRIGGER,
    TIMEOUT_RESPONSE_DEADLINE,
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
    LayerEvent,
    LayerEventType,
    emit_layer_event,
    validate_tier_contract,
    validate_triage_result,
    validate_l1_to_l2_boundary,
    validate_l2_to_l3_boundary,
    validate_l3_to_l4_boundary,
    cross_l1_to_l2,
    cross_l2_to_l3,
    cross_l3_to_l4,
    clear_layer_events,
)
from llm_council.performance.integration import persist_session_performance_data
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
from llm_council.webhooks.types import WebhookEventType
from llm_council.triage import run_triage, TriageResult

# =============================================================================
# Legacy Attribute Support (ADR-032)
# =============================================================================

# Explicitly define common constants at top-level for direct imports
COUNCIL_MODELS = _get_council_models()
CHAIRMAN_MODEL = _get_chairman_model()
SYNTHESIS_MODE = _get_synthesis_mode()

_DEPRECATED_CONFIG_ATTRS = {
    "EXCLUDE_SELF_VOTES": _get_exclude_self_votes,
    "STYLE_NORMALIZATION": _get_style_normalization,
    "NORMALIZER_MODEL": _get_normalizer_model,
    "MAX_REVIEWERS": _get_max_reviewers,
    "CACHE_ENABLED": _get_cache_enabled,
    "ADVERSARIAL_MODE": _get_adversarial_mode,
    "ADVERSARIAL_MODEL": _get_adversarial_model,
}


def __getattr__(name: str):
    """Provide lazy access to deprecated config constants."""
    if name in _DEPRECATED_CONFIG_ATTRS:
        return _DEPRECATED_CONFIG_ATTRS[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Extra constants for compatibility
MODEL_STATUS_AUTH_ERROR = STATUS_AUTH_ERROR
ProgressCallback = Callable[[int, int, str], Awaitable[None]]

# Type-only imports
if TYPE_CHECKING:
    from llm_council.tier_contract import TierContract

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
    webhook_config: Optional[WebhookConfig] = None,
    triage_result: Optional[TriageResult] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """
    Unified entry point for the 3-stage LLM Council pipeline.
    """
    clear_layer_events()

    if verdict_type is None:
        verdict_type = VerdictType.SYNTHESIS

    if session_id is None:
        session_id = str(uuid.uuid4())

    event_bridge = None
    if webhook_config:
        from llm_council.webhooks.event_bridge import EventBridge

        event_bridge = EventBridge(webhook_config, request_id=session_id)
        await event_bridge.start()

    # Pre-initialize metadata for robustness
    metadata = {
        "session_id": session_id,
        "status": "started",
        "models": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "quality": None,
        "rankings": [],
        "model_statuses": {},
        "label_to_model": {},
        "dissent": None,
        "constructive_dissent": None,
        "verdict": None,
    }

    try:
        # --- PHASE 0: Pre-flight ---
        if tier_contract:
            cross_l1_to_l2(tier_contract, user_query)

        emit_layer_event(
            LayerEventType.L3_COUNCIL_START,
            {
                "query": user_query,
                "session_id": session_id,
                "tier": tier_contract.tier if tier_contract else "custom",
            },
        )
        # Determine requested model count for status reporting
        if models:
            requested_configs = len(models)
        elif tier_contract:
            requested_configs = len(tier_contract.allowed_models)
        else:
            requested_configs = len(_get_council_models())

        if event_bridge:
            await event_bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_COUNCIL_START,
                    data={"query": user_query, "session_id": session_id},
                )
            )

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

        metadata["models"] = [r["model"] for r in stage1_data.get("stage1_results", [])]
        metadata["model_statuses"] = stage1_data.get("model_statuses", {})
        metadata["usage"] = _aggregate_stage_usage({"stage1": stage1_data["usage"]})
        metadata["dissent"] = stage1_data.get("dissent_report")

        if event_bridge:
            await event_bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_STAGE_COMPLETE,
                    data={
                        "session_id": session_id,
                        "stage": 1,
                        "results_count": len(metadata["models"]),
                    },
                )
            )

        # Early exit if no models responded
        if not metadata["models"]:
            metadata["status"] = "failed"
            return ([], [], {}, metadata)

        # --- PHASE 2: PEER REVIEW ---
        if on_progress:
            await on_progress(40, 100, "[*] Stage 1 complete, starting peer review...")

        emit_layer_event(
            LayerEventType.BOUNDARY_CROSSING, {"from": "L2", "to": "L3", "session_id": session_id}
        )

        stage2_data = await run_stage2(
            user_query,
            stage1_data,
            on_progress=on_progress,
            tier_contract=tier_contract,
            council_models=models,
        )

        metadata["rankings"] = stage2_data.get("aggregate_rankings", [])
        metadata["label_to_model"] = stage2_data.get("label_to_model", {})
        metadata["constructive_dissent"] = stage2_data.get("constructive_dissent")
        metadata["usage"] = _aggregate_stage_usage(
            {"stage1": stage1_data["usage"], "stage2": stage2_data["usage"]}
        )

        if event_bridge:
            await event_bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_STAGE_COMPLETE,
                    data={
                        "session_id": session_id,
                        "stage": 2,
                        "rankings_count": len(metadata["rankings"]),
                    },
                )
            )

        # --- PHASE 3: SYNTHESIS ---
        if on_progress:
            await on_progress(80, 100, "[*] Peer review complete, synthesizing final verdict...")
        stage3_data = await run_stage3(
            user_query,
            stage1_data,
            stage2_data,
            on_progress=on_progress,
            verdict_type=verdict_type,
            include_dissent=include_dissent,
        )

        metadata["usage"] = _aggregate_stage_usage(
            {
                "stage1": stage1_data["usage"],
                "stage2": stage2_data["usage"],
                "stage3": stage3_data["usage"],
            }
        )

        # ADR-012 Quorum Status Logic
        if requested_configs > 0 and len(metadata["models"]) < requested_configs:
            metadata["status"] = "partial"
        else:
            metadata["status"] = "complete"

        metadata["verdict"] = stage3_data.get("verdict_result")

        # Enrichment
        if should_include_quality_metrics():
            metadata["quality"] = calculate_quality_metrics(
                stage1_responses={
                    r["model"]: {"content": r["response"]} for r in stage1_data["stage1_results"]
                },
                stage2_rankings=stage2_data["stage2_results"],
                stage3_synthesis={
                    "content": stage3_data.get("chairman_result", {}).get("response", "")
                },
                aggregate_rankings=[
                    (r["model"], r["borda_score"] or 0.0) for r in metadata["rankings"]
                ],
                label_to_model=metadata["label_to_model"],
            )

        # Persistence
        persist_session_bias_data(
            session_id=session_id,
            stage1_results=stage1_data["stage1_results"],
            stage2_results=stage2_data["stage2_results"],
            label_to_model=metadata["label_to_model"],
            query=user_query,
        )
        persist_session_performance_data(
            session_id=session_id,
            model_statuses=metadata["model_statuses"],
            aggregate_rankings={r["model"]: r for r in metadata["rankings"]},
            stage2_results=stage2_data["stage2_results"],
        )

        # Final Telemetry (ADR-041 Alignment)
        telemetry = get_telemetry()
        if telemetry.is_enabled():
            await telemetry.send_event(
                {
                    "type": "council_completed",
                    "session_id": session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "council_size": len(metadata["models"]),
                    "responses_received": len(
                        [s for s in metadata["model_statuses"].values() if s.get("status") == "ok"]
                    ),
                    "rankings": [
                        {
                            "model": r["model"],
                            "borda_score": r.get("borda_score", 0.0),
                        }
                        for r in metadata["rankings"]
                    ],
                    "usage": metadata.get(
                        "usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    ),
                    "synthesis_type": "full",
                }
            )

        emit_layer_event(
            LayerEventType.L3_COUNCIL_COMPLETE, {"session_id": session_id, "status": "complete"}
        )
        if event_bridge:
            await event_bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_COUNCIL_COMPLETE,
                    data={
                        "session_id": session_id,
                        "status": "complete",
                        "usage": metadata["usage"],
                    },
                )
            )

        return (
            stage1_data["stage1_results"],
            stage2_data["stage2_results"],
            stage3_data["chairman_result"],
            metadata,
        )

    except Exception as e:
        metadata["status"] = "failed"
        metadata["error"] = str(e)
        emit_layer_event(
            LayerEventType.L3_COUNCIL_ERROR, {"session_id": session_id, "error": str(e)}
        )
        if event_bridge:
            await event_bridge.emit(
                LayerEvent(
                    event_type=LayerEventType.L3_COUNCIL_ERROR,
                    data={"session_id": session_id, "error": str(e)},
                )
            )
        raise e
    finally:
        if event_bridge:
            await event_bridge.shutdown()


async def run_council_with_fallback(
    user_query: str,
    bypass_cache: bool = False,
    on_progress: Optional[Callable] = None,
    synthesis_deadline: float = TIMEOUT_SYNTHESIS_TRIGGER,
    per_model_timeout: float = TIMEOUT_PER_MODEL_HARD,
    models: Optional[List[str]] = None,
    tier_contract: Optional["TierContract"] = None,
    webhook_config: Optional[WebhookConfig] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Legacy entry point with robust timeout fallback.
    """
    session_id = str(uuid.uuid4())
    shared_raw_responses = {}

    empty_result = {
        "response": "",
        "synthesis": "",
        "metadata": {
            "session_id": session_id,
            "status": "failed",
            "dissent": None,
            "constructive_dissent": None,
            "verdict": None,
        },
        "label_mapping": {},
        "rankings": [],
        "model_responses": {},
        "model_statuses": {},
        "requested_models": 0,
        "completed_models": 0,
        "synthesis_type": "none",
    }

    try:
        triage_result = None
        if kwargs.get("use_wildcard") or kwargs.get("optimize_prompt"):
            triage_result = run_triage(
                user_query,
                tier_contract=tier_contract,
                include_wildcard=kwargs.get("use_wildcard", False),
                optimize_prompts=kwargs.get("optimize_prompt", False),
            )
            cross_l2_to_l3(triage_result, tier_contract)
            models = triage_result.resolved_models

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
                webhook_config=webhook_config,
                triage_result=triage_result,
            )
        )

        try:
            stage1, stage2, stage3, metadata = await asyncio.wait_for(
                pipeline_task, timeout=synthesis_deadline
            )
            return {
                "response": stage3.get("response", ""),
                "synthesis": stage3.get("response", ""),
                "metadata": metadata,
                "label_mapping": metadata.get("label_to_model", {}),
                "rankings": metadata.get("rankings", []),
                "model_responses": metadata.get("model_statuses", {}),
                "model_statuses": metadata.get("model_statuses", {}),
                "requested_models": len(models) if models else 0,
                "completed_models": len(stage1),
                "synthesis_type": "full",
                "constructive_dissent": metadata.get("constructive_dissent"),
            }
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if on_progress:
                await on_progress(
                    99, 100, "[!] Pipeline reached deadline, generating partial synthesis..."
                )

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
                "dissent": None,
                "constructive_dissent": None,
                "verdict": None,
            }
            res = {
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
            }

            # Final Telemetry (Fallback)
            telemetry = get_telemetry()
            if telemetry.is_enabled():
                await telemetry.send_event(
                    {
                        "type": "council_completed",
                        "session_id": session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "council_size": fallback_metadata["completed_models"],
                        "responses_received": fallback_metadata["completed_models"],
                        "rankings": [],
                        "usage": fallback_metadata["usage"],
                        "synthesis_type": "partial",
                    }
                )
            return res
    except Exception as e:
        empty_result["metadata"]["error"] = str(e)
        empty_result["metadata"]["status"] = "failed"
        # Final Telemetry (Error)
        telemetry = get_telemetry()
        if telemetry.is_enabled():
            await telemetry.send_event(
                {
                    "type": "council_failed",
                    "session_id": session_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
            )
        return empty_result
