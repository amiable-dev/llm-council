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
    council_models: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    shared_raw_responses: Optional[Dict[str, Any]] = None,
    webhook_config: Optional[WebhookConfig] = None,
    triage_result: Optional[TriageResult] = None,
) -> Tuple[str, Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Unified entry point for the 3-stage LLM Council pipeline.
    """
    print("DEBUG: Entered run_full_council")
    if verdict_type is None:
        verdict_type = VerdictType.SYNTHESIS

    if session_id is None:
        session_id = str(uuid.uuid4())

    # Initialize Webhook EventBridge if config provided
    event_bridge = None
    if webhook_config:
        from llm_council.webhooks.event_bridge import EventBridge
        event_bridge = EventBridge(webhook_config)
        await event_bridge.start()

    try:
        # --- NAVIGATION: LAYER BOUNDARIES (ADR-024) ---
        if tier_contract:
            # L1 -> L2 Boundary
            cross_l1_to_l2(tier_contract, user_query)

        # --- TELEMETRY: START ---
        emit_layer_event(LayerEventType.L3_COUNCIL_START, {
            "query": user_query,
            "session_id": session_id,
            "models": council_models or _get_council_models(),
            "tier": tier_contract.tier if tier_contract else "custom"
        })
        if event_bridge:
            await event_bridge.emit(LayerEvent(
                event_type=LayerEventType.L3_COUNCIL_START,
                data={
                    "query": user_query,
                    "session_id": session_id
                }
            ))

        # --- PHASE 1: IDEATION ---
        print("DEBUG: Calling run_stage1")
        stage1_data = await run_stage1(
            user_query,
            on_progress=on_progress,
            tier_contract=tier_contract,
            adversarial_mode=adversarial_mode,
            session_id=session_id,
            council_models=council_models,
            shared_raw_responses=shared_raw_responses,
        )
        print(f"DEBUG: run_stage1 complete, results={len(stage1_data.get('stage1_results', []))}")

        if event_bridge:
            await event_bridge.emit(LayerEvent(
                event_type=LayerEventType.L3_STAGE_COMPLETE,
                data={
                    "session_id": session_id,
                    "stage": 1,
                    "results_count": len(stage1_data["stage1_results"])
                }
            ))

        # --- PHASE 2: PEER REVIEW ---
        print("DEBUG: Calling run_stage2")
        # L2 -> L3 Boundary (Implicit or explicit via triage)
        # If we skipped triage, we still emit the boundary event for traceability
        emit_layer_event(LayerEventType.BOUNDARY_CROSSING, {
            "from": "L2",
            "to": "L3",
            "session_id": session_id
        })

        stage2_data = await run_stage2(
            user_query,
            stage1_data,
            on_progress=on_progress,
            tier_contract=tier_contract,
            council_models=council_models,
        )
        print(f"DEBUG: run_stage2 complete, rankings={len(stage2_data.get('aggregate_rankings', []))}")

        if event_bridge:
            await event_bridge.emit(LayerEvent(
                event_type=LayerEventType.L3_STAGE_COMPLETE,
                data={
                    "session_id": session_id,
                    "stage": 2,
                    "rankings_count": len(stage2_data["aggregate_rankings"])
                }
            ))

        # --- PHASE 3: SYNTHESIS ---
        print("DEBUG: Calling run_stage3")
        stage3_data = await run_stage3(
            user_query,
            stage1_data,
            stage2_data,
            on_progress=on_progress,
            verdict_type=verdict_type,
            include_dissent=include_dissent,
        )
        print("DEBUG: run_stage3 complete")

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
            "tier": tier_contract.tier if tier_contract else "custom",
            "tier_contract": tier_contract,
            "triage": triage_result.metadata if triage_result else None,
        }

        # --- SIDE EFFECTS: Persistence (ADR-018, ADR-026) ---
        if metadata["status"] == "complete":
            # Persist bias metrics
            persist_session_bias_data(
                session_id=session_id,
                stage1_results=stage1_data["stage1_results"],
                stage2_results=stage2_data["stage2_results"],
                label_to_model=stage2_data["label_to_model"],
                query=user_query
            )
            # Persist performance metrics
            agg_rankings_dict = {
                r["model"]: r for r in stage2_data["aggregate_rankings"]
            }
            persist_session_performance_data(
                session_id=session_id,
                model_statuses=stage1_data.get("model_statuses", {}),
                aggregate_rankings=agg_rankings_dict,
                stage2_results=stage2_data["stage2_results"]
            )

        # --- TELEMETRY: COMPLETE ---
        emit_layer_event(LayerEventType.L3_COUNCIL_COMPLETE, {
            "session_id": session_id,
            "status": metadata["status"]
        })
        if event_bridge:
            await event_bridge.emit(LayerEvent(
                event_type=LayerEventType.L3_COUNCIL_COMPLETE,
                data={
                    "session_id": session_id,
                    "status": metadata["status"],
                    "usage": overall_usage
                }
            ))

        # --- TELEMETRY: PROTOCOL SYNC (ADR-032) ---
        # Ensure standard telemetry event is sent for external analytics
        telemetry = get_telemetry()
        print(f"DEBUG: Telemetry is_enabled={telemetry.is_enabled()}")
        if telemetry.is_enabled():
            await telemetry.send_event({
                "type": "council_completed",
                "session_id": session_id,
                "status": metadata["status"],
                "council_size": len(metadata["models"]),
                "responses_received": metadata["completed_models"],
                "rankings": metadata["rankings"],
                "usage": overall_usage,
                "composition": metadata["models"]
            })

        return (
            stage3_data["chairman_result"]["response"],
            metadata,
            stage2_data["label_to_model"],
            stage2_data["aggregate_rankings"],
        )

    except Exception as e:
        emit_layer_event(LayerEventType.L3_COUNCIL_ERROR, {
            "session_id": session_id,
            "error": str(e)
        })
        if event_bridge:
            await event_bridge.emit(LayerEvent(
                event_type=LayerEventType.L3_COUNCIL_ERROR,
                data={
                    "session_id": session_id,
                    "error": str(e)
                }
            ))
        raise
    finally:
        if event_bridge:
            from llm_council.webhooks.event_bridge import EventBridge
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
    Legacy entry point with robust timeout fallback (ADR-012).
    """
    print("DEBUG: Entered run_council_with_fallback")
    session_id = str(uuid.uuid4())
    shared_raw_responses = {}

    try:
        # --- LAYER 2: TRIAGE ---
        triage_result = None
        if kwargs.get("use_wildcard") or kwargs.get("optimize_prompt"):
            # L1 -> L2 Boundary
            if tier_contract:
                cross_l1_to_l2(tier_contract, user_query)

            triage_result = run_triage(
                user_query,
                tier_contract=tier_contract,
                include_wildcard=kwargs.get("use_wildcard", False),
                optimize_prompts=kwargs.get("optimize_prompt", False)
            )

            # L2 -> L3 Boundary
            cross_l2_to_l3(triage_result, tier_contract)

            # Apply triage results
            models = triage_result.resolved_models

        pipeline_task = asyncio.create_task(
            run_full_council(
                user_query,
                bypass_cache=bypass_cache,
                on_progress=on_progress,
                tier_contract=tier_contract,
                council_models=models,
                adversarial_mode=kwargs.get("adversarial_mode"),
                session_id=session_id,
                shared_raw_responses=shared_raw_responses,
                webhook_config=webhook_config,
                triage_result=triage_result,
            )
        )

        response, metadata, label_mapping, rankings = await asyncio.wait_for(
            pipeline_task, timeout=synthesis_deadline
        )

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
