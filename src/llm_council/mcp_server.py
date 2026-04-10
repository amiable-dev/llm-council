"""LLM Council MCP Server - consult multiple LLMs and get synthesized guidance.

Implements ADR-012: MCP Server Reliability and Long-Running Operation Handling
- Progress notifications during council execution
- Health check tool
- Confidence levels (quick/balanced/high/reasoning)
- Structured results with per-model status
- Tiered timeouts with fallback synthesis
- Partial results on timeout
- Tier-Sovereign timeout configuration (2025-12-19)
"""

import json
import time
import asyncio
from typing import List, Optional, Any, Dict

from mcp.server.fastmcp import FastMCP, Context

from llm_council.council import (
    run_council_with_fallback,
    run_stage1,
    run_stage2,
    run_stage3,
    TIMEOUT_SYNTHESIS_TRIGGER,
)
from llm_council.tier_contract import create_tier_contract
from llm_council.verdict import VerdictType
from llm_council.session_store import (
    create_session,
    load_session,
    save_session,
    close_session,
    purge_expired_sessions,
)
from llm_council.verification.api import run_verification, VerifyRequest
from llm_council.verification.context import InvalidSnapshotError
from llm_council.verification.formatting import format_verification_result
from llm_council.verification.transcript import (
    create_transcript_store,
    TranscriptNotFoundError,
    TranscriptIntegrityError,
)

# ADR-032: Migrated to unified_config
from llm_council.unified_config import get_config, get_api_key
from llm_council.tier_contract import create_tier_contract
from llm_council.openrouter import query_model_with_status, STATUS_OK


def _get_council_models() -> list:
    """Get council models from unified config."""
    return get_config().council.models


def _get_chairman_model() -> str:
    """Get chairman model from unified config."""
    return get_config().council.chairman


def _get_openrouter_api_key() -> str:
    """Get OpenRouter API key via ADR-013 resolution chain."""
    return get_api_key("openrouter") or ""


def _get_tier_model_pools() -> dict:
    """Get tier model pools from unified config."""
    config = get_config()
    return config.tiers.pools


def _get_tier_timeout(tier: str) -> dict:
    """Get tier timeout config from unified config."""
    config = get_config()
    timeouts = config.timeouts
    return {
        "total": timeouts.get_timeout(tier, "total") // 1000,  # Convert ms to seconds
        "per_model": timeouts.get_timeout(tier, "per_model") // 1000,
    }


def _get_key_source() -> str:
    """Determine the source of the API key."""
    import os

    if os.environ.get("OPENROUTER_API_KEY"):
        return "environment"
    # Could add keychain detection here
    return "unknown"


# Module-level function for backwards compatibility with tests
def get_key_source() -> str:
    """Public function wrapper for backwards compatibility."""
    return _get_key_source()


# Module-level aliases for backwards compatibility
COUNCIL_MODELS = _get_council_models()
CHAIRMAN_MODEL = _get_chairman_model()
OPENROUTER_API_KEY = _get_openrouter_api_key()
TIER_MODEL_POOLS = _get_tier_model_pools()


mcp = FastMCP("LLM Council")


def _build_confidence_configs() -> dict:
    """
    Build confidence configs dynamically from tier timeout settings.

    This allows environment variable overrides per ADR-012 Section 5.
    """
    return {
        "quick": {
            "models": 2,
            **_get_tier_timeout("quick"),
            "description": "Fast response (~20-30s)",
        },
        "balanced": {
            "models": 3,
            **_get_tier_timeout("balanced"),
            "description": "Balanced response (~45-60s)",
        },
        "high": {
            "models": None,
            **_get_tier_timeout("high"),
            "description": "Full council deliberation (~90s)",
        },
        "reasoning": {
            "models": None,
            **_get_tier_timeout("reasoning"),
            "description": "Deep reasoning models (~3-5min)",
        },
    }


# Build configs at import time (can be refreshed if needed)
CONFIDENCE_CONFIGS = _build_confidence_configs()


@mcp.tool()
async def consult_council(
    query: str,
    ctx: Context,
    confidence: str = "balanced",
) -> str:
    """
    DEPRECATED: Use start_council -> council_review -> council_synthesize instead.
    This monolithic tool is DISABLED to ensure real-time progress visibility.
    """
    return (
        "ERROR: consult_council is disabled. You must use the three-stage flow to get visibility into deliberation stages:\n"
        "1. start_council(query=..., confidence=...)\n"
        "2. council_review(session_id=...)\n"
        "3. council_synthesize(session_id=...)\n"
        "Please use the split tools for this query."
    )


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
        result += f"**Decision**: {verdict.get('verdict', 'unknown').upper()}\n"
        result += f"**Confidence**: {verdict.get('confidence', 0):.0%}\n"
        result += f"**Rationale**: {verdict.get('rationale', 'No rationale provided')}\n"
        if verdict.get("deadlocked"):
            result += f"\n> *Note: Council was deadlocked. Chairman cast deciding vote.*\n"
        if verdict.get("dissent"):
            result += f"\n**Dissent**: {verdict.get('dissent')}\n"

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
        result += "\n" + "!" * 40 + "\n"
        result += "### DEVIL'S ADVOCATE - DISSENTING REPORT\n"
        result += "-" * 40 + "\n"
        result += dissent_report + "\n"
        result += "!" * 40 + "\n"

    # ADR-CD: Display Constructive Dissent if available (Minority Opinion from Stage 2)
    # Note: query.py calls this 'dissent', mcp_server metadata has it as 'dissent'
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

    return result


@mcp.tool()
async def start_council(
    query: str,
    ctx: Context,
    confidence: str = "balanced",
    adversarial_mode: bool = False,
) -> str:
    """
    Phase 1: Begin a council deliberation. Runs Stage 1 (individual opinions)
    and optionally Stage 1B (Devil's Advocate). Returns a session_id — pass it
    to council_review() to continue.
    """
    # ADR-012: Opportunistic cleanup of expired sessions
    purge_expired_sessions()

    # Get configuration via lazy-loaded helpers
    tier_pools = _get_tier_model_pools()
    tier = confidence if confidence in tier_pools else "high"
    tier_contract = create_tier_contract(tier)
    tier_config = _get_tier_timeout(tier)

    # Progress reporting bridge - Fire-and-forget to avoid deadlocks (ADR-012)
    async def on_progress(step, total, message):
        if not ctx:
            return

        async def _send():
            try:
                await asyncio.wait_for(ctx.report_progress(step, total), timeout=0.5)
            except Exception:
                pass
            try:
                await asyncio.wait_for(ctx.info(message), timeout=0.5)
            except Exception:
                pass

        asyncio.create_task(_send())

    # Phase 1: Collect responses
    # Note: we use our refactored run_stage1 directly
    stage1_data = await run_stage1(
        query,
        on_progress=on_progress,
        per_model_timeout=tier_config.get("per_model", 90),
        tier_contract=tier_contract,
        adversarial_mode=adversarial_mode,
    )

    # Persist session to disk
    session_id = create_session(
        query=query,
        tier=tier,
        confidence=confidence,
        stage="stage1_complete",
        stage1=stage1_data,
    )

    model_count = stage1_data.get("requested_models", 0)
    ok_count = len(stage1_data.get("stage1_results", []))

    return json.dumps({
        "session_id": session_id,
        "status": "stage1_complete",
        "models_total": model_count,
        "models_ok": ok_count,
        "next_step": f"Call council_review(session_id='{session_id}') to run peer review.",
    }, indent=2)


@mcp.tool()
async def council_review(session_id: str, ctx: Context) -> str:
    """
    Phase 2: Run Stage 2 peer review and ranking on a started council session.
    Returns the Borda rankings table. Pass session_id to council_synthesize() next.
    """
    try:
        session = load_session(session_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    if session["stage"] != "stage1_complete":
        return json.dumps({"error": f"Session is in stage '{session['stage']}', expected 'stage1_complete'."})

    # Progress reporting bridge - Fire-and-forget to avoid deadlocks (ADR-012)
    async def on_progress(step, total, message):
        if not ctx:
            return

        async def _send():
            try:
                await asyncio.wait_for(ctx.report_progress(step, total), timeout=0.5)
            except Exception:
                pass
            try:
                await asyncio.wait_for(ctx.info(message), timeout=0.5)
            except Exception:
                pass

        asyncio.create_task(_send())

    # Create tier contract based on session tier
    tier_contract = create_tier_contract(session["tier"])

    # Phase 2: Peer Review
    stage2_data = await run_stage2(
        user_query=session["query"],
        stage1_data=session["stage1"],
        on_progress=on_progress,
        tier_contract=tier_contract,
    )

    # Fast JSON scrubbing for safety (ADR-032 / BUG-FIX)
    try:
        # Use json.dumps with default=str to force serializability
        safe_stage2 = json.loads(json.dumps(stage2_data, default=str))
    except Exception:
        # Fallback to crude string conversion if anything goes wrong
        safe_stage2 = {"error": "serialization_failed", "original": str(stage2_data)}

    # Update session
    save_session(session_id, {"stage": "stage2_complete", "stage2": safe_stage2})

    # Build preview of rankings
    aggregate = stage2_data.get("aggregate_rankings", [])
    rankings_text = "\n".join(
        f"{i+1}. {e.get('model','?').split('/')[-1]} (Borda: {float(e.get('borda_score',0)):.3f})"
        for i, e in enumerate(aggregate[:8])
    )

    return json.dumps({
        "session_id": session_id,
        "status": "stage2_complete",
        "rankings_preview": rankings_text,
        "next_step": f"Call council_synthesize(session_id='{session_id}') for the Chairman's verdict.",
    }, indent=2)


@mcp.tool()
async def council_synthesize(
    session_id: str,
    ctx: Context,
    include_details: bool = False,
) -> str:
    """
    Phase 3: Run Stage 3 Chairman synthesis on a reviewed council session.
    Returns the full council result and cleans up the session file.
    """
    try:
        session = load_session(session_id)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    if session["stage"] != "stage2_complete":
        return json.dumps({"error": f"Session is in stage '{session['stage']}', expected 'stage2_complete'."})

    # Progress reporting bridge - Fire-and-forget to avoid deadlocks (ADR-012)
    async def on_progress(step, total, message):
        if not ctx:
            return

        async def _send():
            try:
                await asyncio.wait_for(ctx.report_progress(step, total), timeout=0.5)
            except Exception:
                pass
            try:
                await asyncio.wait_for(ctx.info(message), timeout=0.5)
            except Exception:
                pass

        asyncio.create_task(_send())

    # Phase 3: Synthesis
    # Note: we use our refactored run_stage3
    council_result = await run_stage3(
        user_query=session["query"],
        stage1_data=session["stage1"],
        stage2_data=session["stage2"],
        on_progress=on_progress,
        verdict_type=None,  # default to synthesis
        include_dissent=False,  # default
    )

    # Clean up the session file
    close_session(session_id)

    # Format result using our shared helper
    return _format_council_result(council_result, include_details=include_details)


@mcp.tool()
async def council_health_check() -> str:
    """
    Check LLM Council health before expensive operations (ADR-012).

    Returns status of API connectivity, configured models, and estimated response time.
    Use this to verify the council is working before calling consult_council.
    """
    from importlib.metadata import version as pkg_version

    try:
        council_version = pkg_version("llm-council-core")
    except Exception:
        council_version = "unknown"

    checks = {
        "version": council_version,
        "api_key_configured": bool(OPENROUTER_API_KEY),
        "key_source": get_key_source(),  # ADR-013: Show where key came from (not the key itself)
        "council_size": len(COUNCIL_MODELS),
        "chairman_model": CHAIRMAN_MODEL,
        "models": COUNCIL_MODELS,
        "estimated_duration": {
            "quick": "~20-30 seconds (fastest models)",
            "balanced": "~45-60 seconds (most models)",
            "high": f"~60-90 seconds (all {len(COUNCIL_MODELS)} models)",
        },
    }

    # Quick connectivity test with a fast, cheap model
    if checks["api_key_configured"]:
        try:
            start = time.time()
            response = await query_model_with_status(
                "google/gemini-2.0-flash-001",  # Fast and cheap
                [{"role": "user", "content": "ping"}],
                timeout=10.0,
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
                checks["message"] = (
                    f"API connectivity issue: {response.get('error', 'Unknown error')}"
                )

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


@mcp.tool()
async def verify(
    snapshot_id: str,
    ctx: Context,
    target_paths: Optional[List[str]] = None,
    rubric_focus: Optional[str] = None,
    confidence_threshold: float = 0.7,
    tier: str = "balanced",
) -> str:
    """
    Verify agent work using the LLM Council verification system (ADR-034).

    Uses multi-model consensus to verify code changes, implementations, or other
    work artifacts against quality rubrics. Returns a structured verdict with
    confidence score and rationale.

    Args:
        snapshot_id: Git commit SHA to verify (7-40 hex characters).
        target_paths: Optional list of specific file paths to verify.
        rubric_focus: Optional rubric focus area (e.g., "security", "performance").
        confidence_threshold: Minimum confidence for pass verdict (0.0-1.0, default 0.7).
        tier: Confidence tier for model selection - "quick", "balanced" (default), "high", or "reasoning".
        ctx: MCP context for progress reporting (injected automatically).

    Returns:
        JSON string containing verification result with verdict, confidence,
        exit_code (0=PASS, 1=FAIL, 2=UNCLEAR), rubric scores, blocking issues,
        rationale, and transcript location for audit trail.
    """

    # Add progress reporting for verification (long-running ADR-034 task)
    async def on_progress(step: int, total: int, message: str):
        if ctx:
            try:
                await ctx.report_progress(step, total)
                await ctx.info(message)
            except Exception as e:
                import sys
                print(f"[verify] progress failed: {e}", file=sys.stderr)

    try:
        # Create request object and transcript store
        request = VerifyRequest(
            snapshot_id=snapshot_id,
            target_paths=target_paths,
            rubric_focus=rubric_focus,
            confidence_threshold=confidence_threshold,
            tier=tier,
        )
        store = create_transcript_store()

        # Run the verification with progress callback
        result = await run_verification(request, store, on_progress=on_progress if ctx else None)

        # Return formatted output for human readability
        # JSON is also included at the end for programmatic parsing
        formatted = format_verification_result(result)
        json_output = json.dumps(result, indent=2)

        return f"{formatted}\n\n---\n\n<details>\n<summary>Raw JSON</summary>\n\n```json\n{json_output}\n```\n</details>"

    except InvalidSnapshotError as e:
        return json.dumps(
            {
                "error": str(e),
                "exit_code": 2,  # UNCLEAR for invalid input
                "verdict": "unclear",
                "confidence": 0.0,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "error": f"Unexpected error: {e}",
                "exit_code": 2,  # UNCLEAR for unexpected errors
                "verdict": "unclear",
                "confidence": 0.0,
            },
            indent=2,
        )


@mcp.tool()
async def audit(
    ctx: Context,
    verification_id: Optional[str] = None,
    validate_integrity: bool = False,
    expected_hash: Optional[str] = None,
) -> str:
    """
    Retrieve and validate verification audit transcripts (ADR-034).

    Provides access to verification audit trails for compliance, debugging,
    and integrity validation. Can retrieve a single verification by ID or
    list all verifications.

    Args:
        verification_id: Optional ID to retrieve specific verification.
            If not provided, lists all available verifications.
        validate_integrity: If True, validates transcript integrity against
            expected_hash.
        expected_hash: Expected SHA256 hash for integrity validation.
            Required when validate_integrity is True.
        ctx: MCP context (injected automatically).

    Returns:
        JSON string containing:
        - For single verification: stages, integrity_hash, optional validation result
        - For listing: verifications array with metadata, total_count
    """
    try:
        store = create_transcript_store(readonly=True)

        # If no verification_id, list all verifications
        if verification_id is None:
            verifications = store.list_verifications()
            return json.dumps(
                {
                    "verifications": verifications,
                    "total_count": len(verifications),
                },
                indent=2,
            )

        # Retrieve specific verification
        stages = store.read_all_stages(verification_id)
        integrity_hash = store.compute_integrity_hash(verification_id)

        result: dict = {
            "verification_id": verification_id,
            "stages": stages,
            "integrity_hash": integrity_hash,
        }

        # Validate integrity if requested
        if validate_integrity and expected_hash:
            try:
                store.validate_integrity(verification_id, expected_hash)
                result["integrity_valid"] = True
            except TranscriptIntegrityError as e:
                result["integrity_valid"] = False
                result["integrity_error"] = str(e)

        return json.dumps(result, indent=2)

    except TranscriptNotFoundError as e:
        return json.dumps(
            {
                "error": f"Verification not found: {e}",
                "verification_id": verification_id,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {
                "error": f"Unexpected error: {e}",
                "verification_id": verification_id,
            },
            indent=2,
        )


def main():
    """Entry point for the llm-council command."""
    mcp.run()


if __name__ == "__main__":
    main()
