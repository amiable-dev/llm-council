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

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from llm_council.council import run_full_council


# Security scheme for Bearer token authentication (ADR-038)
security = HTTPBearer(auto_error=False)


def get_api_token() -> Optional[str]:
    """Get the configured API token from environment.

    Returns None if no token is configured, meaning auth is optional.
    """
    token = os.environ.get("LLM_COUNCIL_API_TOKEN")
    # Treat empty string as not configured
    return token if token else None


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> None:
    """Verify the Bearer token if LLM_COUNCIL_API_TOKEN is configured.

    ADR-038 Security Requirement:
    - If LLM_COUNCIL_API_TOKEN is set, all protected endpoints require auth
    - If not set, auth is optional (backwards compatible)
    - Health endpoint bypasses this check entirely

    Raises:
        HTTPException: 401 if token is required but missing/invalid
    """
    api_token = get_api_token()

    # No token configured = auth not required (backwards compatible)
    if api_token is None:
        return

    # Token configured = auth required
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token. Provide Authorization: Bearer <token>",
        )

    if credentials.credentials != api_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token. Provide Authorization: Bearer <token>",
        )


# Dependency for protected endpoints
auth_dependency = Depends(verify_token)
from llm_council.webhooks.sse import council_event_generator, get_sse_headers
from llm_council.webhooks.types import WebhookConfig
from llm_council.verdict import VerdictType

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
    # Webhook configuration (ADR-025a Issue #76)
    webhook_url: Optional[str] = Field(
        default=None, description="URL to receive webhook notifications"
    )
    webhook_events: Optional[List[str]] = Field(
        default=None,
        description="Events to subscribe to (default: council.complete, council.error)",
    )
    webhook_secret: Optional[str] = Field(
        default=None, description="HMAC secret for webhook signature verification"
    )
    # ADR-025b Jury Mode
    verdict_type: Optional[str] = Field(
        default="synthesis",
        description="Type of verdict: 'synthesis' (default), 'binary' (approved/rejected), or 'tie_breaker'",
    )
    include_dissent: Optional[bool] = Field(
        default=False, description="Extract minority opinions from Stage 2 evaluations (ADR-025b)"
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


@app.post(
    "/v1/council/run",
    response_model=CouncilResponse,
    tags=["Council"],
    dependencies=[auth_dependency],
)
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

    # Build webhook config if URL provided (ADR-025a Issue #76)
    webhook_config = None
    if request.webhook_url:
        webhook_config = WebhookConfig(
            url=request.webhook_url,
            events=request.webhook_events or ["council.complete", "council.error"],
            secret=request.webhook_secret,
        )

    # Parse verdict_type (ADR-025b)
    try:
        verdict_type_enum = VerdictType(
            request.verdict_type.lower() if request.verdict_type else "synthesis"
        )
    except ValueError:
        verdict_type_enum = VerdictType.SYNTHESIS

    try:
        # Run the full council deliberation
        stage1, stage2, stage3, metadata = await run_full_council(
            request.prompt,
            models=request.models,
            webhook_config=webhook_config,
            verdict_type=verdict_type_enum,
            include_dissent=request.include_dissent or False,
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


@app.get("/v1/council/stream", tags=["Council"], dependencies=[auth_dependency])
async def council_stream(
    prompt: str = Query(..., description="The question to deliberate"),
    models: Optional[str] = Query(
        default=None, description="Comma-separated list of models (uses defaults if omitted)"
    ),
    api_key: Optional[str] = Query(
        default=None, description="OpenRouter API key (or set OPENROUTER_API_KEY env)"
    ),
) -> StreamingResponse:
    """Stream council deliberation events via Server-Sent Events (SSE).

    This endpoint streams real-time events as the council progresses
    through its deliberation stages. Events are sent in SSE format.

    **Event Types:**
    - `council.deliberation_start`: Council execution starting
    - `council.stage1.complete`: Stage 1 responses collected
    - `council.stage2.complete`: Stage 2 rankings complete
    - `council.complete`: Final synthesis ready (includes full result)
    - `council.error`: An error occurred

    **Example Client (JavaScript):**
    ```javascript
    const eventSource = new EventSource('/v1/council/stream?prompt=What+is+AI');
    eventSource.addEventListener('council.complete', (e) => {
        const data = JSON.parse(e.data);
        console.log('Result:', data.result.synthesis);
    });
    ```

    API key can be provided as a query parameter or via OPENROUTER_API_KEY
    environment variable.
    """
    # BYOK: Use provided key or fall back to environment
    effective_api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not effective_api_key:
        raise HTTPException(
            status_code=400,
            detail="API key required. Pass 'api_key' query param or set OPENROUTER_API_KEY environment variable.",
        )

    return StreamingResponse(
        council_event_generator(prompt, models, effective_api_key),
        media_type="text/event-stream",
        headers=get_sse_headers(),
    )
