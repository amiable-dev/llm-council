"""LLM Council MCP Server - consult multiple LLMs and get synthesized guidance.

Implements ADR-012: MCP Server Reliability and Long-Running Operation Handling
- Progress notifications during council execution
- Health check tool
- Confidence levels (quick/balanced/high)
- Structured results with per-model status
- Tiered timeouts with fallback synthesis
- Partial results on timeout
"""
import json
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context

from llm_council.council import (
    run_council_with_fallback,
    TIMEOUT_SYNTHESIS_TRIGGER,
)
from llm_council.config import COUNCIL_MODELS, CHAIRMAN_MODEL, OPENROUTER_API_KEY
from llm_council.openrouter import query_model_with_status, STATUS_OK


mcp = FastMCP("LLM Council")


# Confidence level configurations (ADR-012)
CONFIDENCE_CONFIGS = {
    "quick": {"models": 2, "timeout": 15, "description": "Fast response with 2 models (~10s)"},
    "balanced": {"models": 3, "timeout": 25, "description": "Balanced response with 3 models (~25s)"},
    "high": {"models": None, "timeout": 40, "description": "Full council deliberation (~45s)"},
}


@mcp.tool()
async def consult_council(
    query: str,
    confidence: str = "high",
    include_details: bool = False,
    ctx: Optional[Context] = None,
) -> str:
    """
    Consult the LLM Council for guidance on a query.

    Args:
        query: The question to ask the council.
        confidence: Response quality level - "quick" (2 models, ~10s), "balanced" (3 models, ~25s), or "high" (full council, ~45s).
        include_details: If True, includes individual model responses and rankings.
        ctx: MCP context for progress reporting (injected automatically).
    """
    # Get confidence configuration
    config = CONFIDENCE_CONFIGS.get(confidence, CONFIDENCE_CONFIGS["high"])
    timeout = config.get("timeout", TIMEOUT_SYNTHESIS_TRIGGER)

    # Progress reporting helper that bridges MCP context to council callback
    async def on_progress(step: int, total: int, message: str):
        if ctx:
            try:
                await ctx.report_progress(step, total, message)
            except Exception:
                pass  # Progress reporting is best-effort

    # Run the council with ADR-012 reliability features:
    # - Tiered timeouts (15s/25s/40s/50s)
    # - Partial results on timeout
    # - Fallback synthesis
    # - Per-model status tracking
    council_result = await run_council_with_fallback(
        query,
        on_progress=on_progress,
        synthesis_deadline=timeout,
    )

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
    if status != "complete":
        synthesis_type = metadata.get("synthesis_type", "unknown")
        result += f"\n*Council status: {status} ({synthesis_type} synthesis)*\n"

    # Add council rankings if available
    aggregate = metadata.get("aggregate_rankings", [])
    if aggregate:
        result += "\n### Council Rankings\n"
        for entry in aggregate[:5]:  # Top 5
            score = entry.get("borda_score", "N/A")
            result += f"- {entry['model']}: {score}\n"

    if include_details:
        result += "\n\n### Council Details\n"

        # Add per-model status (ADR-012)
        result += "\n#### Model Status\n"
        for model, info in model_responses.items():
            model_short = model.split("/")[-1]
            status_icon = "✓" if info.get("status") == "ok" else "✗"
            latency = info.get("latency_ms", 0)
            result += f"- {status_icon} {model_short}: {info.get('status', 'unknown')} ({latency}ms)\n"

        # Add Stage 1 details (Individual Responses) - only successful ones
        result += "\n#### Stage 1: Individual Opinions\n"
        for model, info in model_responses.items():
            if info.get("status") == "ok" and info.get("response"):
                result += f"\n**{model}**:\n{info['response']}\n"

        # Add Stage 2 details (Rankings) if available
        label_to_model = metadata.get("label_to_model", {})
        if label_to_model:
            result += "\n#### Stage 2: Peer Review\n"
            result += f"*Label mappings: {json.dumps(label_to_model)}*\n"

    return result


@mcp.tool()
async def council_health_check() -> str:
    """
    Check LLM Council health before expensive operations (ADR-012).

    Returns status of API connectivity, configured models, and estimated response time.
    Use this to verify the council is working before calling consult_council.
    """
    checks = {
        "api_key_configured": bool(OPENROUTER_API_KEY),
        "council_size": len(COUNCIL_MODELS),
        "chairman_model": CHAIRMAN_MODEL,
        "models": COUNCIL_MODELS,
        "estimated_duration": {
            "quick": "~10 seconds (2 models)",
            "balanced": "~25 seconds (3 models)",
            "high": f"~45 seconds ({len(COUNCIL_MODELS)} models)",
        },
    }

    # Quick connectivity test with a fast, cheap model
    if checks["api_key_configured"]:
        try:
            start = time.time()
            response = await query_model_with_status(
                "google/gemini-2.0-flash-001",  # Fast and cheap
                [{"role": "user", "content": "ping"}],
                timeout=10.0
            )
            latency_ms = int((time.time() - start) * 1000)

            checks["api_connectivity"] = {
                "status": response["status"],
                "latency_ms": latency_ms,
                "test_model": "google/gemini-2.0-flash-001",
            }

            if response["status"] == STATUS_OK:
                checks["ready"] = True
                checks["message"] = "Council is ready. Use consult_council to ask questions."
            else:
                checks["ready"] = False
                checks["message"] = f"API connectivity issue: {response.get('error', 'Unknown error')}"

        except Exception as e:
            checks["api_connectivity"] = {
                "status": "error",
                "error": str(e),
            }
            checks["ready"] = False
            checks["message"] = f"Health check failed: {e}"
    else:
        checks["ready"] = False
        checks["message"] = "OPENROUTER_API_KEY not configured. Set it in environment or .env file."

    return json.dumps(checks, indent=2)


def main():
    """Entry point for the llm-council command."""
    mcp.run()


if __name__ == "__main__":
    main()
