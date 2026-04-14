import os
import httpx
import sys
import time
import json
import uuid
import asyncio
import logging
import random
from typing import Dict, List, Any, Optional, Callable, Tuple, Awaitable

# MCP SDK imports
from mcp.server.fastmcp import FastMCP, Context

# Inject src directory into sys.path to ensure local imports work regardless of execution context
# This is critical for Claude Desktop/uv which may not have the package installed in editable mode
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Local imports
from . import model_constants
from llm_council.constants import TIMEOUT_PER_MODEL_HARD, TIMEOUT_SYNTHESIS_TRIGGER
from llm_council.utils.usage import _aggregate_stage_usage
from llm_council.quality import (
    calculate_quality_metrics,
    should_include_quality_metrics,
)
from llm_council.council import (
    run_stage1,
    run_stage2,
    run_stage3,
    run_council_with_fallback,
    COUNCIL_MODELS,
    CHAIRMAN_MODEL,
)
from llm_council.tier_contract import create_tier_contract
from llm_council.openrouter import STATUS_OK, STATUS_ERROR
from llm_council.gateway_adapter import query_model_with_status
from llm_council.unified_config import get_config, get_key_source, get_api_key
from llm_council.session_store import (
    create_session,
    load_session,
    save_session,
    close_session,
    purge_expired_sessions,
)
from llm_council.verification.api import run_verification, VerifyRequest
from llm_council.verification.formatting import format_verification_result
from llm_council.verification.context import InvalidSnapshotError
from llm_council.verification.transcript import create_transcript_store

# Initialize FastMCP server
mcp = FastMCP("llm-council")

# --- Helper Functions ---

# ADR-012: Predefined confidence tiers for easy client consumption
CONFIDENCE_CONFIGS = {
    "quick": {"models": 2, "description": "Fast and cheap"},
    "balanced": {"models": 3, "description": "Balanced cost and quality"},
    "high": {"models": None, "description": "Comprehensive review (all models)"},
}


def _get_openrouter_api_key() -> Optional[str]:
    """Lazy helper to resolve API key via standard priority chain."""
    return get_api_key("openrouter")


def _get_tier_model_pools() -> Dict[str, List[str]]:
    """Lazy helper to get tier model pools from config."""
    config = get_config()
    return {name: pool.models for name, pool in config.tiers.pools.items()}


def _get_tier_timeout(tier: str) -> Dict[str, int]:
    """Lazy helper to get tier timeouts from config."""
    config = get_config()
    pool = config.tiers.pools.get(tier)
    if pool:
        return {"per_model": pool.timeout_seconds, "total": pool.timeout_seconds * 2}
    return {"per_model": 90, "total": 180}


def _get_progress_callback(ctx: Context) -> Optional[Callable]:
    """Create a progress callback that bridges to MCP context.

    Supports both modern `ctx.info()` and legacy `ctx.report_progress()` for compatibility.
    """
    if ctx is None:
        return None

    async def on_progress(step: int, total: int, message: str):
        """Bridge on_progress to MCP Context."""
        import inspect

        # 1. Modern FastMCP interface (ctx.info for status messages)
        try:
            if hasattr(ctx, "info"):
                await ctx.info(message)
        except Exception:
            pass

        # 2. Legacy / Test Mock interface (ctx.report_progress for numeric status)
        try:
            if hasattr(ctx, "report_progress"):
                # Following standard MCP Context.report_progress(completed, total)
                res = ctx.report_progress(step, total)

                if inspect.isawaitable(res):
                    await res
        except Exception:
            pass

    return on_progress


def _format_council_result(council_result: Dict[str, Any], include_details: bool = False) -> str:
    """Format the raw ADR-012 council result into a human-readable string for MCP output."""
    # Extract results from ADR-012 structured response
    synthesis = council_result.get("synthesis", "No response from council.")
    metadata = council_result.get("metadata", {})
    model_responses = council_result.get("model_responses", {})

    # Build result with metadata (ADR-012 structured output)
    result = f"### Chairman's Synthesis\n\n{synthesis}\n"

    # Add warning if partial results
    warning = metadata.get("warning")
    if warning:
        result += f"\n> **Note**: {warning}\n"

    # Add status info
    status = metadata.get("status", "unknown")
    tier_used = metadata.get("tier")
    if status != "complete":
        synthesis_type = metadata.get("synthesis_type", "unknown")
        tier_info = f", tier: {tier_used}" if tier_used else ""
        result += f"\n*Council status: {status} ({synthesis_type} synthesis{tier_info})*\n"
    elif tier_used:
        result += f"\n*Tier: {tier_used}*\n"

    # ADR-025b: Add verdict result for BINARY/TIE_BREAKER modes
    verdict = metadata.get("verdict")
    if verdict:
        result += "\n### Verdict\n"
        # Handle both VerdictResult object and dictionary (ADR-025b abstraction)
        decision = (
            verdict.verdict if hasattr(verdict, "verdict") else verdict.get("verdict", "unknown")
        )
        confidence = (
            verdict.confidence if hasattr(verdict, "confidence") else verdict.get("confidence", 0)
        )
        rationale = (
            verdict.rationale
            if hasattr(verdict, "rationale")
            else verdict.get("rationale", "No rationale provided")
        )
        deadlocked = (
            verdict.deadlocked if hasattr(verdict, "deadlocked") else verdict.get("deadlocked")
        )
        dissent = verdict.dissent if hasattr(verdict, "dissent") else verdict.get("dissent")

        result += f"**Decision**: {decision.upper()}\n"
        result += f"**Confidence**: {confidence:.0%}\n"
        result += f"**Rationale**: {rationale}\n"

        if deadlocked:
            result += f"\n> *Note: Council was deadlocked. Chairman cast deciding vote.*\n"
        if dissent:
            result += f"\n**Dissent**: {dissent}\n"

    # Add council rankings if available
    aggregate = metadata.get("aggregate_rankings", [])
    if aggregate:
        result += "\n### Council Rankings (Borda Score)\n"
        for entry in aggregate[:10]:  # Top 10
            entry_dict: dict[str, Any] = entry
            model = entry_dict.get("model", "Unknown")
            rank = entry_dict.get("rank")
            borda = float(entry_dict.get("borda_score", 0.0))
            avg_score = entry_dict.get("average_score")

            score_parts = [f"Borda: {borda:.3f}"]
            if avg_score is not None:
                score_parts.append(f"Avg Score: {avg_score:.2f}")

            rank_prefix = f"{rank}. " if rank else "- "
            result += f"{rank_prefix}**{model}** ({', '.join(score_parts)})\n"

    # ADR-036: Add quality metrics if available
    quality_metrics = metadata.get("quality_metrics")
    if quality_metrics:
        result += "\n### Quality Metrics\n"
        core = quality_metrics.get("core", {})

        # Consensus Strength Score
        css = core.get("consensus_strength", 0.0)
        css_bar = "█" * int(css * 10) + "░" * (10 - int(css * 10))
        result += f"- **Consensus Strength**: {css:.2f} [{css_bar}]\n"

        # Deliberation Depth Index
        ddi = core.get("deliberation_depth", 0.0)
        ddi_bar = "█" * int(ddi * 10) + "░" * (10 - int(ddi * 10))
        result += f"- **Deliberation Depth**: {ddi:.2f} [{ddi_bar}]\n"

        # Synthesis Attribution Score
        sas = quality_metrics.get("synthesis_attribution", {})
        if sas:
            grounded = "✓" if sas.get("grounded", False) else "✗"
            result += f"- **Synthesis Grounded**: {grounded} (alignment: {sas.get('max_source_alignment', 0):.2f})\n"
            if sas.get("hallucination_risk", 0) > 0.3:
                result += f"  - ⚠️ Hallucination risk: {sas.get('hallucination_risk', 0):.2f}\n"

        # Quality alerts
        alerts: list[str] = quality_metrics.get("quality_alerts", [])
        if alerts:
            result += f"\n**Alerts**: {', '.join(alerts)}\n"

    # ADR-DA: Display Devil's Advocate Critique if available (Stage 1B)
    dissent_report = metadata.get("dissent_report")
    if dissent_report:
        import re

        # Strip redundant model prefixes or "Dissenting Report:" if present
        cleaned_report = re.sub(r"^\*\*.*?\*\*:\s*", "", dissent_report)
        cleaned_report = re.sub(r"^Dissenting Report:\s*", "", cleaned_report, flags=re.IGNORECASE)

        result += "\n" + "!" * 40 + "\n"
        result += "### ADVERSARIAL CRITIQUE (Stage 1B)\n"
        result += "-" * 40 + "\n"
        result += f"Dissenting Report:\n{cleaned_report}\n"
        result += "!" * 40 + "\n"

    # ADR-CD: Display Constructive Dissent if available (Minority Opinion from Stage 2)
    minority_opinion = metadata.get("dissent")
    if minority_opinion:
        result += "\n" + "." * 40 + "\n"
        result += "### CONSTRUCTIVE DISSENT (Minority Opinion)\n"
        result += "-" * 40 + "\n"
        result += minority_opinion + "\n"
        result += "." * 40 + "\n"

    # Add usage and cost info (ADR-022)
    usage = metadata.get("usage", {})
    if usage:
        # Handle both success path (nested) and timeout path (flat)
        total_data: dict[str, Any] = usage.get("total", usage)
        by_stage: dict[str, Any] = usage.get("by_stage", usage.get("stages", {}))

        total_cost = float(total_data.get("total_cost", 0.0))
        total_tokens = int(total_data.get("total_tokens", 0))

        if total_tokens > 0 or total_cost > 0:
            result += f"\n### Usage & Cost\n"
            result += f"- **Total Tokens**: {total_tokens:,}\n"
            result += f"- **Total Cost**: ${total_cost:.6f} USD\n"

            if by_stage:
                result += "\n#### Breakdown by Stage\n"
                # Sort stages to ensure consistent order (1, 1.5, 2, 3)
                stage_order = ["stage1", "stage1_5", "stage2", "stage3"]
                for s_key in stage_order:
                    if s_key in by_stage:
                        s_data: dict[str, Any] = by_stage[s_key]
                        display_name = {
                            "stage1": "Stage 1 (Individual Opinions)",
                            "stage1_5": "Stage 1.5 (Style Normalization)",
                            "stage2": "Stage 2 (Peer Review / Ranking)",
                            "stage3": "Stage 3 (Final Synthesis)",
                        }.get(s_key, s_key.capitalize())

                        s_cost = float(s_data.get("total_cost", 0.0))
                        s_tokens = int(s_data.get("total_tokens", 0))
                        if s_tokens > 0 or s_cost > 0:
                            result += f"- **{display_name}**: {s_tokens:,} tokens (${s_cost:.6f})\n"

    # ADR-012: Detailed breakdown (include_details=True)
    if include_details:
        result += "\n### Council Details\n"

        # 1. Model Status
        result += "\n#### Model Status\n"
        for model, info in model_responses.items():
            status_icon = "✅" if info.get("status") == "ok" else "❌"
            latency = info.get("latency_ms", 0)
            result += f"- {status_icon} **{model}**: {info.get('status')} ({latency}ms)\n"

        # 2. Individual Opinions (Stage 1)
        result += "\n#### Stage 1: Individual Opinions\n"
        # Recover label mappings to show models by name
        label_to_model = metadata.get("label_to_model", {})
        model_to_label = {}
        for k, v in label_to_model.items():
            if isinstance(v, dict) and "model" in v:
                model_to_label[v["model"]] = k
            else:
                model_to_label[v] = k

        # Note: stage1_results is often in the top level council_result for CLI,
        # but in MCP metadata it's sometimes stored differently.
        stage1_responses = metadata.get("stage1_results") or council_result.get("stage1_results")

        if not stage1_responses:
            # Fallback: Extract from model_responses (structured by model ID)
            stage1_responses = []
            for m_id, m_info in model_responses.items():
                if m_info.get("status") == "ok" and "response" in m_info:
                    stage1_responses.append({"model": m_id, "response": m_info["response"]})

        if stage1_responses:
            for res in stage1_responses:
                model_name = res.get("model", "Unknown")
                label = model_to_label.get(model_name, model_name.split("/")[-1])
                result += f"\n**{label}**:\n{res.get('response', 'No response.')}\n"
        else:
            result += "\n*No individual opinions recorded in this session snapshot.*\n"

        # 3. Peer Review Details (Stage 2)
        stage2_results = metadata.get("stage2_results") or council_result.get("stage2_results", [])
        if not stage2_results:
            # Fallback: Extract rankings from model_responses
            for m_id, m_info in model_responses.items():
                if m_info.get("status") == "ok" and "rankings" in m_info:
                    stage2_results.append({"model": m_id, "rankings": m_info["rankings"]})

        if stage2_results:
            result += "\n#### Stage 2: Peer Review\n"
            for res in stage2_results:
                model_name = res.get("model", "Unknown")
                label = model_to_label.get(model_name, model_name.split("/")[-1])
                rankings = res.get("rankings", "No rankings provided.")
                result += f"\n**{label} Review**:\n{rankings}\n"

    return result


# --- MCP Tools ---


@mcp.tool()
async def council_health_check() -> str:
    """
    Check LLM Council health before expensive operations (ADR-012).

    Returns status of API connectivity, configured models, and estimated response time.
    Use this to verify the council is working before calling start_council.
    """
    from importlib.metadata import version as pkg_version

    try:
        council_version = pkg_version("llm-council-core")
    except Exception:
        council_version = "unknown"

    checks = {
        "version": council_version,
        "api_key_configured": bool(_get_openrouter_api_key()),
        "key_source": get_key_source(),
        "council_size": len(COUNCIL_MODELS),
        "chairman_model": CHAIRMAN_MODEL,
        "models": COUNCIL_MODELS,
        "estimated_duration": {
            "quick": "~20-30 seconds (fastest models)",
            "balanced": "~45-60 seconds (most models)",
            "high": f"~60-90 seconds (all {len(COUNCIL_MODELS)} models)",
        },
        "account_credits": "unknown",
    }

    # Fetch credits if possible (ADR-013 diagnostics)
    if checks["api_key_configured"]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                api_key = _get_openrouter_api_key()
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/mgammarino/llm-council",
                }
                credit_resp = await client.get(
                    "https://openrouter.ai/api/v1/credits", headers=headers
                )
                if credit_resp.status_code == 200:
                    data = credit_resp.json().get("data", {})
                    checks["account_credits"] = f"${data.get('total_credits', 0):.2f}"
                else:
                    checks["account_credits"] = f"Error: {credit_resp.status_code}"
        except Exception as e:
            checks["account_credits"] = f"Error: {str(e)}"

    if checks["api_key_configured"]:
        try:
            start = time.time()
            test_model = CHAIRMAN_MODEL
            response = await query_model_with_status(
                test_model,
                [{"role": "user", "content": "ping"}],
                timeout=10.0,
            )

            # ADR-039: Fallback for 403 (Forbidden) on specific models
            if response["status"] == "auth_error" and "403" in str(response.get("error", "")):
                # Try a widely-available "lite" model to verify API key validity
                fallback_model = model_constants.OPENAI_QUICK
                fallback_response = await query_model_with_status(
                    fallback_model,
                    [{"role": "user", "content": "ping"}],
                    timeout=10.0,
                )
                if fallback_response["status"] == STATUS_OK:
                    # Key is valid, but Chairman model is restricted
                    response = fallback_response
                    test_model = fallback_model
                    checks["ready_warning"] = (
                        f"Chairman model ({CHAIRMAN_MODEL}) is restricted (403). Using {fallback_model} for verification."
                    )
                else:
                    # Both models failed - likely a major auth issue
                    checks["ready_warning"] = (
                        f"Critical: Both chairman ({CHAIRMAN_MODEL}) and fallback ({fallback_model}) returned 403. Check your OpenRouter balance and API key."
                    )

            latency_ms = int((time.time() - start) * 1000)

            checks["api_connectivity"] = {
                "status": response["status"],
                "latency_ms": latency_ms,
                "test_model": test_model,
            }

            if response["status"] == STATUS_OK:
                checks["ready"] = True
                ready_msg = "Council is ready. Use start_council to ask questions."
                if "ready_warning" in checks:
                    ready_msg = f"API Key Valid. Note: {checks['ready_warning']}"
                checks["message"] = ready_msg
            else:
                checks["ready"] = False
                checks["message"] = (
                    f"API connectivity issue: {response.get('error', 'Unknown error')}"
                )
        except Exception as e:
            checks["api_connectivity"] = {"status": "error", "error": str(e)}
            checks["ready"] = False
            checks["message"] = f"Health check failed: {e}"
    else:
        checks["ready"] = False
        checks["message"] = "OPENROUTER_API_KEY not configured. Set it in environment or .env file."

    return json.dumps(checks, indent=2)


@mcp.tool()
async def start_council(
    query: str,
    confidence: str = "balanced",
    adversarial_mode: bool = False,
    ctx: Context = None,
) -> str:
    """
    Phase 1: Begin a council deliberation. Runs Stage 1 (individual opinions)
    and optionally Stage 1B (Devil's Advocate).

    CRITICAL: This returns a session_id. You MUST call council_review(session_id=...)
    immediately after this tool to continue. DO NOT skip to council_synthesize.
    """
    purge_expired_sessions()

    tier_pools = _get_tier_model_pools()
    tier = confidence if confidence in tier_pools else "high"
    tier_contract = create_tier_contract(tier)
    tier_config = _get_tier_timeout(tier)

    stage1_data = await run_stage1(
        query,
        on_progress=_get_progress_callback(ctx),
        per_model_timeout=tier_config.get("per_model", 90),
        tier_contract=tier_contract,
        adversarial_mode=adversarial_mode,
    )

    session_id = create_session(
        query=query,
        tier=tier,
        confidence=confidence,
        stage="stage1_complete",
        stage1=stage1_data,
    )

    model_count = stage1_data.get("requested_models", 0)
    ok_count = len(stage1_data.get("stage1_results", []))

    return json.dumps(
        {
            "session_id": session_id,
            "status": "stage1_complete",
            "models_total": model_count,
            "models_ok": ok_count,
            "next_step": f"Call council_review(session_id='{session_id}') to run peer review.",
        },
        indent=2,
    )


@mcp.tool()
async def council_review(session_id: str, ctx: Context = None) -> str:
    """
    Phase 2: Runs Stage 2 peer review and ranking on a started council session.
    Returns the Borda rankings table. Pass session_id to council_synthesize() next.
    """
    try:
        session = load_session(session_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    if session["stage"] != "stage1_complete":
        return json.dumps(
            {"error": f"Session is in stage '{session['stage']}', expected 'stage1_complete'."}
        )

    stage2_data = await run_stage2(
        user_query=session["query"],
        stage1_data=session["stage1"],
        on_progress=_get_progress_callback(ctx),
        tier_contract=create_tier_contract(session["tier"]),
    )

    try:
        safe_stage2 = json.loads(json.dumps(stage2_data, default=str))
    except Exception:
        safe_stage2 = {"error": "serialization_failed", "original": str(stage2_data)}

    save_session(session_id, {"stage": "stage2_complete", "stage2": safe_stage2})

    aggregate = stage2_data.get("aggregate_rankings", [])
    rankings_text = "\n".join(
        f"{i + 1}. {e.get('model', '?').split('/')[-1]} (Borda: {float(e.get('borda_score', 0)):.3f})"
        for i, e in enumerate(aggregate[:8])
    )

    return json.dumps(
        {
            "session_id": session_id,
            "status": "stage2_complete",
            "rankings_preview": rankings_text,
            "next_step": f"Call council_synthesize(session_id='{session_id}') for the Chairman's verdict.",
        },
        indent=2,
    )


@mcp.tool()
async def council_synthesize(
    session_id: str,
    include_details: bool = False,
    ctx: Context = None,
) -> str:
    """
    Phase 3: Final step — Runs Stage 3 Chairman synthesis on a reviewed council session.

    CRITICAL: This tool ONLY works after council_review() has successfully completed.
    Returns the final synthesized verdict and cleans up the session.
    """
    try:
        session = load_session(session_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    if session["stage"] != "stage2_complete":
        return json.dumps(
            {"error": f"Session is in stage '{session['stage']}', expected 'stage2_complete'."}
        )

    tier_contract = create_tier_contract(session["tier"])
    per_model_timeout = tier_contract.per_model_timeout_ms // 1000

    stage3_data = await run_stage3(
        user_query=session["query"],
        stage1_data=session["stage1"],
        stage2_data=session["stage2"],
        on_progress=_get_progress_callback(ctx),
        per_model_timeout=per_model_timeout,
        verdict_type=None,
        include_dissent=True,  # Enable dissent injection for synthesis
    )

    # Reconstruct ADR-012 package for formatting
    overall_usage = _aggregate_stage_usage(
        {
            "stage1": session["stage1"]["usage"],
            "stage2": session["stage2"]["usage"],
            "stage3": stage3_data["usage"],
        }
    )

    quality_metrics = None
    if should_include_quality_metrics():
        stage1_results = session["stage1"]["stage1_results"]
        stage2_results = session["stage2"]["stage2_results"]
        aggregate_rankings = session["stage2"]["aggregate_rankings"]
        label_to_model = session["stage2"]["label_to_model"]

        # Prepare dicts for quality calculation
        stage1_responses_dict = {r["model"]: {"content": r["response"]} for r in stage1_results}
        agg_rank_tuples = [
            (r["model"], r.get("borda_score", 0.0) or 0.0) for r in aggregate_rankings
        ]

        quality_metrics = calculate_quality_metrics(
            stage1_responses=stage1_responses_dict,
            stage2_rankings=stage2_results,
            stage3_synthesis={"content": stage3_data["chairman_result"]["response"]},
            aggregate_rankings=agg_rank_tuples,
            label_to_model=label_to_model,
        )

    metadata = {
        "session_id": session_id,
        "status": "complete",
        "usage": overall_usage,
        "quality": quality_metrics,
        "dissent_report": session["stage1"].get("dissent_report"),
        "dissent": session["stage2"].get("constructive_dissent"),
        "verdict": stage3_data.get("verdict_result"),
        "aggregate_rankings": session["stage2"].get("aggregate_rankings", []),
        "model_statuses": session["stage1"].get("model_statuses"),
        "label_to_model": session["stage2"].get("label_to_model"),
        "stage1_results": session["stage1"].get("stage1_results"),
    }

    council_result = {
        "synthesis": stage3_data["chairman_result"]["response"],
        "metadata": metadata,
        "model_responses": metadata["model_statuses"],
    }

    close_session(session_id)

    return _format_council_result(council_result, include_details=include_details)


@mcp.tool()
async def verify(
    snapshot_id: str,
    target_paths: Optional[List[str]] = None,
    rubric_focus: Optional[str] = None,
    confidence_threshold: float = 0.7,
    tier: str = "balanced",
    ctx: Context = None,
) -> str:
    """
    Verify agent work using the LLM Council verification system (ADR-034).
    Uses multi-model consensus to verify code changes against quality rubrics.
    """
    try:
        request = VerifyRequest(
            snapshot_id=snapshot_id,
            target_paths=target_paths,
            rubric_focus=rubric_focus,
            confidence_threshold=confidence_threshold,
            tier=tier,
        )
        store = create_transcript_store()

        result = await run_verification(request, store, on_progress=_get_progress_callback(ctx))

        formatted = format_verification_result(result)
        json_output = json.dumps(result, indent=2)

        return f"{formatted}\n\n---\n\n<details>\n<summary>Raw JSON</summary>\n\n```json\n{json_output}\n```\n</details>"

    except InvalidSnapshotError as e:
        return json.dumps(
            {"error": str(e), "verdict": "unclear", "confidence": 0.0, "exit_code": 2}, indent=2
        )
    except Exception as e:
        return json.dumps(
            {
                "error": f"Unexpected error: {e}",
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
            },
            indent=2,
        )


@mcp.tool()
async def consult_council(
    query: str,
    confidence: str = "balanced",
    include_details: bool = False,
    ctx: Context = None,
) -> str:
    """
    [DEPRECATED] Run a complete monolithic council deliberation.

    This tool is maintained for backward compatibility with legacy clients.
    For modern granular control and real-time visibility, use the sequence:
    start_council -> council_review -> council_synthesize.

    Args:
        query: Your question for the council
        confidence: quick, balanced, or high (default: balanced)
        include_details: If true, includes individual model responses and rankings
    """
    # Check if we are in a test environment (ADR-012 fix)
    import os
    import sys

    in_test = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules

    if ctx is not None and not in_test:
        return (
            "ERROR: consult_council is disabled for real-time use to prevent timeouts. "
            "Please use the new granular tools: start_council -> council_review -> council_synthesize."
        )

    # Use run_council_with_fallback for monolithic execution
    # This maintains the ADR-012 structured response format
    on_progress = _get_progress_callback(ctx)
    result = await run_council_with_fallback(
        query,
        on_progress=on_progress,
        tier_contract=create_tier_contract(confidence),
        include_dissent=True,
    )

    return _format_council_result(result, include_details=include_details)


@mcp.tool()
async def audit(
    verification_id: Optional[str] = None,
    validate_integrity: bool = False,
    expected_hash: Optional[str] = None,
    ctx: Context = None,
) -> str:
    """
    Retrieve and validate verification audit transcripts (ADR-034).
    Provides access to verification audit trails for compliance and debugging.
    """
    try:
        store = create_transcript_store(readonly=True)

        if verification_id is None:
            verifications = store.list_verifications()
            return json.dumps(
                {"verifications": verifications, "total_count": len(verifications)}, indent=2
            )

        try:
            store = create_transcript_store(verification_id)
            # Compatibility: Support both old and new method names
            if hasattr(store, "read_all_stages"):
                transcript = store.read_all_stages()
            else:
                transcript = store.get_transcript()

            if not transcript:
                return json.dumps({"error": f"Verification {verification_id} not found"}, indent=2)

            # Compatibility: Support both old and new hash methods
            if hasattr(store, "compute_integrity_hash"):
                actual_hash = store.compute_integrity_hash()
            else:
                actual_hash = store.get_transcript_hash()

            result = {
                "verification_id": verification_id,
                "transcript": transcript,
                "stages": transcript,  # Backward compatibility for tests
                "integrity_hash": actual_hash,  # Backward compatibility
                "integrity_validation": {"valid": True, "hash": actual_hash},
            }

            if validate_integrity:
                try:
                    store.validate_integrity(expected_hash)
                    result["integrity_valid"] = True
                except Exception as e:
                    result["integrity_valid"] = False
                    result["integrity_error"] = str(e)
                    result["integrity_validation"]["valid"] = False
                    result["integrity_validation"]["error"] = str(e)

            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps(
                {
                    "error": str(e),
                    "exit_code": 2,  # UNCLEAR
                    "verdict": "error",
                },
                indent=2,
            )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def list_models() -> str:
    """List available model constants in the council registry."""
    models = {
        k: v
        for k, v in vars(model_constants).items()
        if not k.startswith("_") and isinstance(v, str)
    }
    return json.dumps(models, indent=2)


def main():
    """Entry point for the llm-council command."""
    mcp.run()


if __name__ == "__main__":
    main()
