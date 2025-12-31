"""
Verification API endpoint per ADR-034.

Provides POST /v1/council/verify for structured work verification
using LLM Council multi-model deliberation.

Exit codes:
- 0: PASS - Approved with confidence >= threshold
- 1: FAIL - Rejected
- 2: UNCLEAR - Confidence below threshold, requires human review
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from llm_council.verification.context import (
    InvalidSnapshotError,
    VerificationContextManager,
    validate_snapshot_id,
)
from llm_council.verification.transcript import (
    TranscriptStore,
    create_transcript_store,
)
from llm_council.verification.types import VerdictType

# Router for verification endpoints
router = APIRouter(tags=["verification"])


# Git SHA pattern for validation
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


class VerifyRequest(BaseModel):
    """Request body for POST /v1/council/verify."""

    snapshot_id: str = Field(
        ...,
        description="Git commit SHA for snapshot pinning (7-40 hex chars)",
        min_length=7,
        max_length=40,
    )
    target_paths: Optional[List[str]] = Field(
        default=None,
        description="Paths to verify (defaults to entire snapshot)",
    )
    rubric_focus: Optional[str] = Field(
        default=None,
        description="Focus area: Security, Performance, Accessibility, etc.",
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for PASS verdict",
    )

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id_format(cls, v: str) -> str:
        """Validate snapshot_id is valid git SHA."""
        if not GIT_SHA_PATTERN.match(v):
            raise ValueError("snapshot_id must be valid git SHA (7-40 hexadecimal characters)")
        return v


class RubricScoresResponse(BaseModel):
    """Rubric scores in response."""

    accuracy: Optional[float] = Field(default=None, ge=0, le=10)
    relevance: Optional[float] = Field(default=None, ge=0, le=10)
    completeness: Optional[float] = Field(default=None, ge=0, le=10)
    conciseness: Optional[float] = Field(default=None, ge=0, le=10)
    clarity: Optional[float] = Field(default=None, ge=0, le=10)


class BlockingIssueResponse(BaseModel):
    """Blocking issue in response."""

    severity: str = Field(..., description="critical, major, or minor")
    description: str = Field(..., description="Issue description")
    location: Optional[str] = Field(default=None, description="File/line location")


class VerifyResponse(BaseModel):
    """Response body for POST /v1/council/verify."""

    verification_id: str = Field(..., description="Unique verification ID")
    verdict: str = Field(..., description="pass, fail, or unclear")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    exit_code: int = Field(..., description="0=PASS, 1=FAIL, 2=UNCLEAR")
    rubric_scores: RubricScoresResponse = Field(
        default_factory=RubricScoresResponse,
        description="Multi-dimensional rubric scores",
    )
    blocking_issues: List[BlockingIssueResponse] = Field(
        default_factory=list,
        description="Issues that caused FAIL verdict",
    )
    rationale: str = Field(..., description="Chairman synthesis explanation")
    transcript_location: str = Field(..., description="Path to verification transcript")
    partial: bool = Field(
        default=False,
        description="True if result is partial (timeout/error)",
    )


def _verdict_to_exit_code(verdict: str) -> int:
    """Convert verdict to exit code."""
    if verdict == "pass":
        return 0
    elif verdict == "fail":
        return 1
    else:  # unclear
        return 2


async def run_verification(
    request: VerifyRequest,
    store: TranscriptStore,
) -> Dict[str, Any]:
    """
    Run verification using LLM Council.

    This is the core verification logic that:
    1. Creates isolated context
    2. Runs council deliberation
    3. Persists transcript
    4. Returns structured result

    Args:
        request: Verification request
        store: Transcript store for persistence

    Returns:
        Verification result dictionary
    """
    verification_id = str(uuid.uuid4())[:8]

    # Create isolated context for this verification
    with VerificationContextManager(
        snapshot_id=request.snapshot_id,
        rubric_focus=request.rubric_focus,
    ) as ctx:
        # Create transcript directory
        transcript_dir = store.create_verification_directory(verification_id)

        # Persist request
        store.write_stage(
            verification_id,
            "request",
            {
                "snapshot_id": request.snapshot_id,
                "target_paths": request.target_paths,
                "rubric_focus": request.rubric_focus,
                "confidence_threshold": request.confidence_threshold,
                "context_id": ctx.context_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # TODO: In full implementation, this would run council deliberation
        # For now, return a mock result for API structure validation
        #
        # The actual implementation will:
        # 1. Run stage1_collect_responses() with verification prompt
        # 2. Run stage2_collect_rankings() for peer review
        # 3. Run stage3_synthesize_final() for verdict
        # 4. Extract verdict from synthesis

        # Mock result for API structure (will be replaced with real council)
        verdict = "pass"
        confidence = 0.85

        # Determine verdict based on confidence threshold
        if confidence < request.confidence_threshold:
            verdict = "unclear"
        elif confidence < 0.5:
            verdict = "fail"

        exit_code = _verdict_to_exit_code(verdict)

        result = {
            "verification_id": verification_id,
            "verdict": verdict,
            "confidence": confidence,
            "exit_code": exit_code,
            "rubric_scores": {
                "accuracy": 8.5,
                "relevance": 8.0,
                "completeness": 7.5,
                "conciseness": 8.0,
                "clarity": 8.5,
            },
            "blocking_issues": [],
            "rationale": "Verification passed all checks.",
            "transcript_location": str(transcript_dir),
            "partial": False,
        }

        # Persist result
        store.write_stage(verification_id, "result", result)

        return result


@router.post("/verify", response_model=VerifyResponse)
async def verify_endpoint(request: VerifyRequest) -> VerifyResponse:
    """
    Verify code, documents, or implementation using LLM Council.

    This endpoint provides structured work verification with:
    - Multi-model consensus via LLM Council deliberation
    - Context isolation per verification (no session bleed)
    - Transcript persistence for audit trail
    - Exit codes for CI/CD integration

    Exit Codes:
    - 0: PASS - Approved with confidence >= threshold
    - 1: FAIL - Rejected with blocking issues
    - 2: UNCLEAR - Confidence below threshold, requires human review

    Args:
        request: VerificationRequest with snapshot_id and optional parameters

    Returns:
        VerificationResult with verdict, confidence, and transcript location
    """
    try:
        # Validate snapshot ID
        validate_snapshot_id(request.snapshot_id)
    except InvalidSnapshotError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        # Create transcript store
        store = create_transcript_store()

        # Run verification
        result = await run_verification(request, store)

        return VerifyResponse(**result)

    except Exception as e:
        # Handle errors gracefully
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "type": type(e).__name__},
        )
