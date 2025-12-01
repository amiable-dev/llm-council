"""Minimal HTTP server for LLM Council (ADR-009).

This module provides a stateless, single-tenant HTTP server for local development
and third-party integrations (LangChain, Vercel AI SDK).

Design principles (per ADR-009):
- Stateless: No database, no persistent storage
- Single-tenant: No multi-user auth (optional basic token only)
- BYOK: API keys passed in request or read from environment
- Ephemeral: Logs go to stdout

Usage:
    pip install "llm-council[http]"
    llm-council serve

Or programmatically:
    from llm_council.http_server import app
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from llm_council.council import run_full_council

# FastAPI app instance
app = FastAPI(
    title="LLM Council",
    description="Local development server for LLM Council deliberations",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


class CouncilRequest(BaseModel):
    """Request body for council deliberation."""

    prompt: str = Field(..., description="The question to deliberate")
    models: Optional[List[str]] = Field(
        default=None, description="Optional list of models (uses defaults if omitted)"
    )
    api_key: Optional[str] = Field(
        default=None, description="OpenRouter API key (or set OPENROUTER_API_KEY env)"
    )


class CouncilResponse(BaseModel):
    """Response from council deliberation."""

    stage1: List[Dict[str, Any]] = Field(..., description="Individual model responses")
    stage2: List[Dict[str, Any]] = Field(..., description="Peer review rankings")
    stage3: Dict[str, Any] = Field(..., description="Final synthesis")
    metadata: Dict[str, Any] = Field(..., description="Aggregate rankings and config")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns service status for load balancers and monitoring.
    """
    return HealthResponse(status="ok", service="llm-council-local")


@app.post("/v1/council/run", response_model=CouncilResponse, tags=["Council"])
async def council_run(request: CouncilRequest) -> CouncilResponse:
    """Run the full council deliberation.

    Executes the 3-stage council process:
    1. Stage 1: Collect individual model responses
    2. Stage 2: Peer review and ranking
    3. Stage 3: Chairman synthesis

    API key can be provided in the request body or via OPENROUTER_API_KEY
    environment variable.
    """
    # BYOK: Use provided key or fall back to environment
    api_key = request.api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="API key required. Pass 'api_key' in request or set OPENROUTER_API_KEY environment variable.",
        )

    # Temporarily set the API key in environment for the council to use
    original_key = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = api_key

    try:
        # Run the full council deliberation
        stage1, stage2, stage3, metadata = await run_full_council(
            request.prompt,
            models=request.models,
        )

        return CouncilResponse(
            stage1=stage1,
            stage2=stage2,
            stage3=stage3,
            metadata=metadata,
        )
    finally:
        # Restore original environment
        if original_key is not None:
            os.environ["OPENROUTER_API_KEY"] = original_key
        elif "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
