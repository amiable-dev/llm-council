"""LLM Council MCP Server - consult multiple LLMs and get synthesized guidance.

Implements ADR-012: MCP Server Reliability and Long-Running Operation Handling
- Progress notifications during council execution
- Health check tool
- Confidence levels (quick/balanced/high)
- Structured results with per-model status
"""
import json
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context

from llm_council.council import run_full_council
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
    model_limit = config["models"]

    # Select models based on confidence level
    models_to_use = COUNCIL_MODELS[:model_limit] if model_limit else COUNCIL_MODELS
    num_models = len(models_to_use)

    # Calculate total steps for progress: models + peer review + synthesis
    total_steps = num_models + num_models + 2  # stage1 + stage2 + synthesis + finalize

    # Progress reporting helper
    async def report_progress(step: int, message: str):
        if ctx:
            try:
                await ctx.report_progress(step, total_steps, message)
            except Exception:
                pass  # Progress reporting is best-effort

    await report_progress(0, f"Starting council with {num_models} models...")

    # Run the council with progress updates
    # Note: For now, we use the existing run_full_council which doesn't have
    # granular progress. In Phase 2, we'll refactor council.py to support callbacks.
    stage1, stage2, stage3, metadata = await run_full_council(query)

    await report_progress(total_steps - 1, "Formatting response...")

    chairman_response = stage3.get("response", "No response from Chairman.")

    # Build result with metadata (ADR-012 structured output)
    result = f"### Chairman's Synthesis\n\n{chairman_response}\n"

    # Add council metadata
    aggregate = metadata.get("aggregate_rankings", [])
    if aggregate:
        result += "\n### Council Rankings\n"
        for entry in aggregate[:5]:  # Top 5
            score = entry.get("borda_score", "N/A")
            result += f"- {entry['model']}: {score}\n"

    if include_details:
        result += "\n\n### Council Details\n"
        # Add Stage 1 details (Individual Responses)
        result += "\n#### Stage 1: Individual Opinions\n"
        for item in stage1:
            result += f"\n**{item['model']}**:\n{item['response']}\n"

        # Add Stage 2 details (Rankings)
        result += "\n#### Stage 2: Peer Review\n"
        for item in stage2:
            result += f"\n**{item['model']}** ranking:\n{item['ranking']}\n"

    await report_progress(total_steps, "Complete")

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
