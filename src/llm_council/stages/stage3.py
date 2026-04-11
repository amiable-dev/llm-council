"""Stage 3: synthesis and final verdict generation."""

from typing import List, Dict, Any, Tuple, Optional, Callable

from llm_council.gateway_adapter import (
    query_model as _orig_query_model,
    STATUS_OK,
)
from llm_council.config_helpers import (
    _get_chairman_model,
    _get_synthesis_mode,
    _check_patched_attr,
)


async def query_model(*args, **kwargs):
    func = _check_patched_attr("llm_council.council", "query_model", _orig_query_model)
    return await func(*args, **kwargs)


from llm_council.verdict import (
    VerdictType,
    VerdictResult,
    get_chairman_prompt,
    parse_binary_verdict,
    parse_tie_breaker_verdict,
    calculate_borda_spread,
)


async def quick_synthesis(
    user_query: str,
    model_responses: Dict[str, Dict[str, Any]],
    council_id: Optional[str] = None,
) -> Tuple[str, Dict[str, float]]:
    """Generate a quick synthesis from partial responses (ADR-012 fallback)."""
    successful = {
        model: info
        for model, info in model_responses.items()
        if info.get("status") == STATUS_OK and info.get("response")
    }

    if not successful:
        return "Error: No model responses available for synthesis.", {
            "prompt_tokens": 0.0,
            "completion_tokens": 0.0,
            "total_tokens": 0.0,
            "total_cost": 0.0,
        }

    responses_text = "\n\n".join(
        [f"**{model}**:\n{info['response']}" for model, info in successful.items()]
    )

    synthesis_prompt = f"""You are synthesizing multiple AI responses into a single coherent answer.
Note: This is a PARTIAL synthesis - some models did not respond in time.

Original Question: {user_query}

Available Responses:
{responses_text}

Provide a concise synthesis of the available responses. Focus on areas of agreement
and highlight any important insights. Be clear that this is based on partial data."""

    messages = [{"role": "user", "content": synthesis_prompt}]
    response = await query_model(
        _get_chairman_model(),
        messages,
        timeout=15.0,
        disable_tools=True,
        council_id=council_id,
    )

    usage = {
        "prompt_tokens": 0.0,
        "completion_tokens": 0.0,
        "total_tokens": 0.0,
        "total_cost": 0.0,
    }

    if response is None:
        best_response = list(successful.values())[0].get("response", "")
        return f"(Fallback - single model response)\n\n{best_response}", usage

    response_usage = response.get("usage", {})
    usage["prompt_tokens"] = response_usage.get("prompt_tokens", 0.0)
    usage["completion_tokens"] = response_usage.get("completion_tokens", 0.0)
    usage["total_tokens"] = response_usage.get("total_tokens", 0.0)
    usage["total_cost"] = response_usage.get("total_cost", 0.0)
    return response.get("content", ""), usage


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    aggregate_rankings: Optional[List[Dict[str, Any]]] = None,
    verdict_type: VerdictType = VerdictType.SYNTHESIS,
    timeout: float = 120.0,
    session_id: Optional[str] = None,
    dissent_report: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, float], Optional[VerdictResult]]:
    """Stage 3: Chairman synthesizes final response."""
    stage1_text = "\n\n".join(
        [f"Model: {result['model']}\nResponse: {result['response']}" for result in stage1_results]
    )

    stage2_text = "\n\n".join(
        [f"Model: {result['model']}\nRanking: {result['ranking']}" for result in stage2_results]
    )

    rankings_context = ""
    if aggregate_rankings:
        rankings_list = "\n".join(
            [
                f"  #{r['rank']}. {r['model']} (avg score: {r.get('average_score', 'N/A')}, votes: {r.get('vote_count', 0)})"
                for r in aggregate_rankings
            ]
        )
        rankings_context = f"\n\nAGGREGATE RANKINGS (after excluding self-votes):\n{rankings_list}"

    if dissent_report:
        rankings_context += f"\n\nDEVIL'S ADVOCATE CRITIQUE:\n{dissent_report}\n\nNote: Consider the critique above when synthesizing the final answer to ensure all blind spots are addressed."

    if verdict_type in (VerdictType.BINARY, VerdictType.TIE_BREAKER):
        top_candidates = ""
        if verdict_type == VerdictType.TIE_BREAKER and aggregate_rankings:
            top_candidates = "\n".join(
                [
                    f"  - {r['model']}: Borda score {r.get('borda_score', 'N/A')}"
                    for r in aggregate_rankings[:3]
                ]
            )
        rankings_summary = f"{stage2_text}{rankings_context}"
        chairman_prompt = get_chairman_prompt(
            verdict_type=verdict_type,
            query=user_query,
            rankings=rankings_summary,
            top_candidates=top_candidates,
        )
    else:
        if _get_synthesis_mode() == "debate":
            mode_instructions = """Your task as Chairman is to present a STRUCTURED ANALYSIS with clear sections.
You MUST include ALL of these sections in your response, using EXACTLY these headers:
## 1. Consensus Points
## 2. Axes of Disagreement
## 3. Position Summaries
## 4. Crucial Assumptions
## 5. Minority Reports
## 6. Chairman's Assessment
IMPORTANT: Do NOT flatten nuance into a single "best" answer. Include ALL 6 sections."""
        else:
            mode_instructions = """Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer. Provide a clear, well-reasoned final answer."""

        chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses and then ranked each other.
Original Question: {user_query}
STAGE 1 - Individual Responses:
{stage1_text}
STAGE 2 - Peer Rankings:
{stage2_text}{rankings_context}
{mode_instructions}"""

    messages = [{"role": "user", "content": chairman_prompt}]
    response = await query_model(
        _get_chairman_model(),
        messages,
        disable_tools=True,
        timeout=timeout,
        council_id=session_id,
    )

    total_usage = {
        "prompt_tokens": 0.0,
        "completion_tokens": 0.0,
        "total_tokens": 0.0,
        "total_cost": 0.0,
    }

    if response is None:
        return (
            {
                "model": _get_chairman_model(),
                "response": "Error: Unable to generate final synthesis.",
            },
            total_usage,
            None,
        )

    usage = response.get("usage", {})
    total_usage["prompt_tokens"] = usage.get("prompt_tokens", 0.0)
    total_usage["completion_tokens"] = usage.get("completion_tokens", 0.0)
    total_usage["total_tokens"] = usage.get("total_tokens", 0.0)
    total_usage["total_cost"] = usage.get("total_cost", 0.0)

    response_content = response.get("content", "")
    verdict_result: Optional[VerdictResult] = None
    if verdict_type == VerdictType.BINARY:
        try:
            verdict_result = parse_binary_verdict(response_content)
            if aggregate_rankings:
                borda_scores = {
                    r["model"]: r.get("borda_score", 0.0)
                    for r in aggregate_rankings
                    if "borda_score" in r
                }
                verdict_result.borda_spread = calculate_borda_spread(borda_scores)
        except ValueError:
            pass
    elif verdict_type == VerdictType.TIE_BREAKER:
        try:
            verdict_result = parse_tie_breaker_verdict(response_content)
            if aggregate_rankings:
                borda_scores = {
                    r["model"]: r.get("borda_score", 0.0)
                    for r in aggregate_rankings
                    if "borda_score" in r
                }
                verdict_result.borda_spread = calculate_borda_spread(borda_scores)
        except ValueError:
            pass

    return (
        {"model": _get_chairman_model(), "response": response_content},
        total_usage,
        verdict_result,
    )


async def run_stage3(
    user_query: str,
    stage1_data: Dict[str, Any],
    stage2_data: Dict[str, Any],
    on_progress: Optional[Callable] = None,
    per_model_timeout: int = 30,
    verdict_type: VerdictType = VerdictType.SYNTHESIS,
    include_dissent: bool = True,
) -> Dict[str, Any]:
    """Phase 3 Orchestrator: Chairman synthesis and final verdict generation."""
    stage1_results = stage1_data["stage1_results"]
    stage2_results = stage2_data["stage2_results"]
    aggregate_rankings = stage2_data["aggregate_rankings"]
    session_id = stage1_data.get("session_id")
    dissent_report = stage1_data.get("dissent_report")
    requested_models = stage1_data.get("requested_models", 3)
    total_steps = stage1_data.get("total_steps", requested_models * 2 + 3)

    async def report_progress(step: int, total: int, message: str):
        if on_progress:
            try:
                await on_progress(step, total, message)
            except Exception:
                pass

    await report_progress(
        total_steps - 1, total_steps, "[*] Stage 3: Chairman is synthesizing final verdict..."
    )

    chairman_result, stage3_usage, verdict_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results,
        aggregate_rankings=aggregate_rankings,
        verdict_type=verdict_type,
        timeout=per_model_timeout,
        session_id=session_id,
        dissent_report=dissent_report if include_dissent else None,
    )

    await report_progress(total_steps, total_steps, "[*] Council complete!")

    return {
        "chairman_result": chairman_result,
        "usage": stage3_usage,
        "verdict_result": verdict_result,
    }
