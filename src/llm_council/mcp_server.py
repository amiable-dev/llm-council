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
from typing import List, Optional

from mcp.server.fastmcp import FastMCP, Context

from llm_council.council import (
    run_council_with_fallback,
    TIMEOUT_SYNTHESIS_TRIGGER,
)
from llm_council.verdict import VerdictType
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
    confidence: str = "high",
    include_details: bool = False,
    verdict_type: str = "synthesis",
    include_dissent: bool = False,
    ctx: Optional[Context] = None,
) -> str:
    """
    Consult the LLM Council for guidance on a query.

    Args:
        query: The question to ask the council.
        confidence: Response quality level - "quick" (2 models, ~10s), "balanced" (3 models, ~25s), or "high" (full council, ~45s).
        include_details: If True, includes individual model responses and rankings.
        verdict_type: Type of verdict to render (ADR-025b Jury Mode):
            - "synthesis": Default behavior, unstructured natural language synthesis
            - "binary": Go/no-go decision (approved/rejected) with confidence score
            - "tie_breaker": Chairman resolves deadlocked decisions
        include_dissent: If True, extract minority opinions from Stage 2 evaluations (ADR-025b).
        ctx: MCP context for progress reporting (injected automatically).

    Returns:
        Formatted string containing the council's synthesis, rankings, and quality metrics (ADR-036).
        Quality metrics include:
        - Consensus Strength Score (CSS): Agreement among council members (0.0-1.0)
        - Deliberation Depth Index (DDI): Thoroughness of deliberation (0.0-1.0)
        - Synthesis Attribution Score (SAS): How well synthesis is grounded in sources
    """
    # Parse verdict_type string to enum
    try:
        verdict_type_enum = VerdictType(verdict_type.lower())
    except ValueError:
        verdict_type_enum = VerdictType.SYNTHESIS
    # Get confidence configuration (ADR-012 Section 5: Tier-Sovereign Timeouts)
    config = CONFIDENCE_CONFIGS.get(confidence, CONFIDENCE_CONFIGS["high"])
    total_timeout = config.get("total", TIMEOUT_SYNTHESIS_TRIGGER)
    per_model_timeout = config.get("per_model", 90)  # Default to high tier

    # Create TierContract for tier-appropriate model selection (ADR-022)
    tier = confidence if confidence in TIER_MODEL_POOLS else "high"
    tier_contract = create_tier_contract(tier)

    # Progress reporting helper that bridges MCP context to council callback
    async def on_progress(step: int, total: int, message: str):
        if ctx:
            try:
                await ctx.report_progress(step, total, message)
            except Exception:
                pass  # Progress reporting is best-effort

    # Run the council with ADR-012, ADR-022, and ADR-025b features:
    # - Tier-sovereign timeouts (per-tier total and per-model)
    # - Tier-appropriate model selection (ADR-022)
    # - Partial results on timeout
    # - Fallback synthesis
    # - Per-model status tracking
    # - Jury Mode verdict types (ADR-025b)
    council_result = await run_council_with_fallback(
        query,
        on_progress=on_progress,
        synthesis_deadline=total_timeout,
        per_model_timeout=per_model_timeout,
        tier_contract=tier_contract,
        verdict_type=verdict_type_enum,
        include_dissent=include_dissent,
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
        result += "\n### Council Rankings\n"
        for entry in aggregate[:5]:  # Top 5
            score = entry.get("borda_score", "N/A")
            result += f"- {entry['model']}: {score}\n"

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
        sas = core.get("synthesis_attribution", {})
        if sas:
            grounded = "✓" if sas.get("grounded", False) else "✗"
            result += f"- **Synthesis Grounded**: {grounded} (alignment: {sas.get('max_source_alignment', 0):.2f})\n"
            if sas.get("hallucination_risk", 0) > 0.3:
                result += f"  - ⚠️ Hallucination risk: {sas.get('hallucination_risk', 0):.2f}\n"

        # Quality alerts
        alerts = quality_metrics.get("quality_alerts", [])
        if alerts:
            result += f"\n**Alerts**: {', '.join(alerts)}\n"

    if include_details:
        result += "\n\n### Council Details\n"

        # Add per-model status (ADR-012)
        result += "\n#### Model Status\n"
        for model, info in model_responses.items():
            model_short = model.split("/")[-1]
            status_icon = "✓" if info.get("status") == "ok" else "✗"
            latency = info.get("latency_ms", 0)
            result += (
                f"- {status_icon} {model_short}: {info.get('status', 'unknown')} ({latency}ms)\n"
            )

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
    import os as _os

    # Debug: show key prefix and working directory to diagnose key loading issues
    key_preview = f"{OPENROUTER_API_KEY[:20]}..." if OPENROUTER_API_KEY else None
    cwd = _os.getcwd()

    checks = {
        "api_key_configured": bool(OPENROUTER_API_KEY),
        "key_source": get_key_source(),  # ADR-013: Show where key came from
        "key_preview": key_preview,  # Debug: first 20 chars
        "working_directory": cwd,  # Debug: where is .env loaded from?
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
    target_paths: Optional[List[str]] = None,
    rubric_focus: Optional[str] = None,
    confidence_threshold: float = 0.7,
    ctx: Optional[Context] = None,
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
        ctx: MCP context for progress reporting (injected automatically).

    Returns:
        JSON string containing verification result with verdict, confidence,
        exit_code (0=PASS, 1=FAIL, 2=UNCLEAR), rubric scores, blocking issues,
        rationale, and transcript location for audit trail.
    """
    # Report initial progress
    if ctx:
        try:
            await ctx.report_progress(1, 3, "Starting verification...")
        except Exception:
            pass  # Progress reporting is best-effort

    try:
        # Report verification in progress
        if ctx:
            try:
                await ctx.report_progress(2, 3, "Running council verification...")
            except Exception:
                pass

        # Create request object and transcript store
        request = VerifyRequest(
            snapshot_id=snapshot_id,
            target_paths=target_paths,
            rubric_focus=rubric_focus,
            confidence_threshold=confidence_threshold,
        )
        store = create_transcript_store()

        # Run the verification
        result = await run_verification(request, store)

        # Report completion
        if ctx:
            try:
                await ctx.report_progress(3, 3, "Verification complete")
            except Exception:
                pass

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

    except asyncio.TimeoutError as e:
        return json.dumps(
            {
                "error": f"Verification timed out: {e}",
                "exit_code": 2,  # UNCLEAR for timeouts
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
    verification_id: Optional[str] = None,
    validate_integrity: bool = False,
    expected_hash: Optional[str] = None,
    ctx: Optional[Context] = None,
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
