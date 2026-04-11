"""Stage 1: Collect individual responses, run adversarial audit, and normalize styles."""

import uuid
import random
import asyncio
from typing import List, Dict, Any, Tuple, Optional, Callable, Awaitable

from llm_council.gateway_adapter import (
    query_models_parallel,
    query_model,
    query_models_with_progress as _orig_query_models_with_progress,
    query_model_with_status as _orig_query_model_with_status,
    STATUS_OK,
    STATUS_ERROR,
)
from llm_council.constants import (
    TIMEOUT_PER_MODEL_HARD,
    MODEL_STATUS_ERROR,
)
from llm_council.unified_config import get_config
from llm_council.config_helpers import (
    _get_council_models,
    _get_adversarial_mode,
    _get_adversarial_model,
    _get_style_normalization,
    _get_normalizer_model,
    _check_patched_attr,
)


async def query_models_with_progress(*args, **kwargs):
    func = _check_patched_attr(
        "llm_council.council", "query_models_with_progress", _orig_query_models_with_progress
    )
    return await func(*args, **kwargs)


async def query_model_with_status(*args, **kwargs):
    func = _check_patched_attr(
        "llm_council.council", "query_model_with_status", _orig_query_model_with_status
    )
    return await func(*args, **kwargs)


ProgressCallback = Callable[[int, int, str], Awaitable[None]]


async def stage1_collect_responses(
    user_query: str, council_id: Optional[str] = None, models: Optional[List[str]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Stage 1: Collect individual responses from all council models."""
    messages = [{"role": "user", "content": user_query}]
    target_models = models or _get_council_models()
    responses = await query_models_parallel(target_models, messages, council_id=council_id)

    stage1_results = []
    total_usage = {
        "prompt_tokens": 0.0,
        "completion_tokens": 0.0,
        "total_tokens": 0.0,
        "total_cost": 0.0,
    }

    for model, response in responses.items():
        if response is not None:
            stage1_results.append({"model": model, "response": response.get("content", "")})
            usage = response.get("usage", {})
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)
            total_usage["total_cost"] += usage.get("total_cost", 0.0)

    return stage1_results, total_usage


async def stage1_collect_responses_with_status(
    user_query: str,
    timeout: float = TIMEOUT_PER_MODEL_HARD,
    on_progress: Optional[ProgressCallback] = None,
    shared_raw_responses: Optional[Dict[str, Dict[str, Any]]] = None,
    models: Optional[List[str]] = None,
    session_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, Dict[str, Any]]]:
    """Stage 1: Collect individual responses with per-model status tracking (ADR-012)."""
    council_models = models if models is not None else _get_council_models()
    messages = [{"role": "user", "content": user_query}]

    responses = await query_models_with_progress(
        council_models,
        messages,
        on_progress=on_progress,
        timeout=timeout,
        shared_results=shared_raw_responses,
        council_id=session_id,
    )

    stage1_results = []
    total_usage = {
        "prompt_tokens": 0.0,
        "completion_tokens": 0.0,
        "total_tokens": 0.0,
        "total_cost": 0.0,
    }
    model_statuses: Dict[str, Dict[str, Any]] = {}

    for model, response in responses.items():
        model_statuses[model] = {
            "status": response.get("status", MODEL_STATUS_ERROR),
            "latency_ms": response.get("latency_ms", 0),
        }

        if response.get("error"):
            model_statuses[model]["error"] = response["error"]

        if response.get("retry_after"):
            model_statuses[model]["retry_after"] = response["retry_after"]

        if response.get("status") == STATUS_OK:
            stage1_results.append({"model": model, "response": response.get("content", "")})
            model_statuses[model]["response"] = response.get("content", "")

            usage = response.get("usage", {})
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)
            total_usage["total_cost"] += usage.get("total_cost", 0.0)

    return stage1_results, total_usage, model_statuses


def should_normalize_styles(responses: List[str]) -> bool:
    """Detect if responses are stylistically diverse enough to warrant normalization."""
    import re
    import statistics

    if len(responses) < 2:
        return False

    has_markdown = [bool(re.search(r"^#+\s", r, re.MULTILINE)) for r in responses]
    if len(set(has_markdown)) > 1:
        return True

    lengths = [len(r) for r in responses]
    mean_length = statistics.mean(lengths)
    if mean_length > 0:
        try:
            cv = statistics.stdev(lengths) / mean_length
            if cv > 0.5:
                return True
        except statistics.StatisticsError:
            pass

    preambles = ["as an ai", "as a language model", "certainly!", "great question", "sure!"]
    preamble_counts = [sum(1 for p in preambles if p in r.lower()[:200]) for r in responses]
    if max(preamble_counts) > 0 and min(preamble_counts) == 0:
        return True

    has_code = [bool(re.search(r"```", r)) for r in responses]
    if len(set(has_code)) > 1:
        return True

    return False


async def stage1_5_normalize_styles(
    stage1_results: List[Dict[str, Any]], session_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Stage 1.5: Normalize response styles to reduce stylistic fingerprinting."""
    total_usage = {
        "prompt_tokens": 0.0,
        "completion_tokens": 0.0,
        "total_tokens": 0.0,
        "total_cost": 0.0,
    }

    mode = _get_style_normalization()
    if mode == "auto":
        if not should_normalize_styles([r["response"] for r in stage1_results]):
            return stage1_results, total_usage
    elif not mode:
        return stage1_results, total_usage

    normalized_results = []
    for result in stage1_results:
        normalize_prompt = f"""Rewrite the following text to have a neutral, consistent style while preserving ALL content and meaning exactly.
        
Original text:
{result["response"]}

Rewritten text:"""
        messages = [{"role": "user", "content": normalize_prompt}]
        response = await query_model(
            _get_normalizer_model(), messages, timeout=60.0, council_id=session_id
        )

        if response is not None:
            normalized_results.append(
                {
                    "model": result["model"],
                    "response": response.get("content", result["response"]),
                    "original_response": result["response"],
                }
            )
            usage = response.get("usage", {})
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0.0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0.0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0.0)
            total_usage["total_cost"] += usage.get("total_cost", 0.0)
        else:
            normalized_results.append(
                {
                    "model": result["model"],
                    "response": result["response"],
                    "original_response": result["response"],
                }
            )

    return normalized_results, total_usage


async def run_stage1(
    user_query: str,
    on_progress: Optional[Callable] = None,
    total_steps: Optional[int] = None,
    per_model_timeout: int = 30,
    tier_contract: Optional[Any] = None,
    adversarial_mode: Optional[bool] = None,
    shared_raw_responses: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    council_models: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Phase 1 Orchestrator: Individual responses and adversarial audit."""
    if council_models is None:
        if tier_contract:
            council_models = tier_contract.allowed_models
        else:
            council_models = _get_council_models()

    requested_models = len(council_models)
    if total_steps is None:
        total_steps = requested_models * 2 + 3

    if session_id is None:
        session_id = str(uuid.uuid4())

    if shared_raw_responses is None:
        shared_raw_responses = {}

    async def report_progress(step: int, total: int, message: str):
        if on_progress:
            try:
                await on_progress(step, total, message)
            except Exception:
                pass

    async def stage1_progress(completed, total, msg):
        await report_progress(completed, total_steps, f"[*] Stage 1: {msg}")

    # ADR-DA: Reactive Adversarial Critique Logic
    da_enabled = adversarial_mode if adversarial_mode is not None else _get_adversarial_mode()
    is_adversarial = da_enabled and len(council_models) >= 3

    adversary_model = None
    current_council_models = council_models
    if is_adversarial:
        adversary_model = _get_adversarial_model()
        if adversary_model and adversary_model in council_models:
            current_council_models = [m for m in council_models if m != adversary_model]
        else:
            current_council_models = list(council_models)
            adversary_model = random.choice(current_council_models)
            current_council_models.remove(adversary_model)

    # 1. Collect initial responses
    stage1_results, stage1_usage, model_statuses = await stage1_collect_responses_with_status(
        user_query,
        timeout=per_model_timeout,
        on_progress=stage1_progress,
        shared_raw_responses=shared_raw_responses,
        models=current_council_models,
        session_id=session_id,
    )

    # 1.5. Style Normalization (ADR-032 stabilization)
    if stage1_results:
        await stage1_progress(len(stage1_results), requested_models, "Normalizing styles...")
        normalized_results, norm_usage = await stage1_5_normalize_styles(
            stage1_results, session_id=session_id
        )
        stage1_results = normalized_results
        # Consolidate usage
        for k in stage1_usage:
            stage1_usage[k] += norm_usage.get(k, 0.0)

    # 1B. Adversarial Critique
    dissent_report = None
    if is_adversarial and stage1_results:
        await report_progress(
            len(stage1_results),
            total_steps,
            f"[*] Stage 1B: ADVERSARIAL CRITIQUE ({adversary_model}) is auditing {len(stage1_results)} responses...",
        )
        responses_text = "\n\n".join(
            [f"Model: {r['model']}\nResponse: {r['response']}" for r in stage1_results]
        )
        from llm_council.adversary_prompt import get_adversary_report_prompt

        da_prompt = get_adversary_report_prompt(user_query, responses_text)
        da_response = await query_model_with_status(
            adversary_model,
            [{"role": "user", "content": da_prompt}],
            timeout=per_model_timeout,
            council_id=session_id,
            disable_tools=True,
        )

        if da_response and da_response.get("status") == STATUS_OK:
            dissent_report = da_response.get("content")
            model_statuses[adversary_model] = {
                "status": STATUS_OK,
                "latency_ms": da_response.get("latency_ms", 0),
                "response": dissent_report,
            }
            da_usage = da_response.get("usage", {})
            for k in stage1_usage:
                stage1_usage[k] += da_usage.get(k, 0.0)
        else:
            model_statuses[adversary_model] = {
                "status": da_response.get("status", STATUS_ERROR) if da_response else STATUS_ERROR,
                "latency_ms": da_response.get("latency_ms", 0) if da_response else 0,
                "error": da_response.get("error", "Adversary failed to respond")
                if da_response
                else "No response",
            }

    await report_progress(
        requested_models, total_steps, "[*] Stage 1 complete, starting peer review..."
    )

    return {
        "stage1_results": stage1_results,
        "model_statuses": model_statuses,
        "usage": stage1_usage,
        "dissent_report": dissent_report,
        "session_id": session_id,
        "requested_models": requested_models,
        "total_steps": total_steps,
    }
