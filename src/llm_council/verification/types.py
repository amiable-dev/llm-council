"""
Verification types for ADR-034 Agent Skills Integration.

Defines Pydantic models for:
- VerificationRequest: Input schema for verification API
- VerificationResult: Output schema with machine-actionable verdict
- Supporting types: VerdictType, RubricScores, BlockingIssue, etc.

These types match the JSON schema defined in ADR-034 and support
cross-agent consistency validation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class VerdictType(str, Enum):
    """Verification verdict types per ADR-034."""

    PASS = "pass"
    FAIL = "fail"
    UNCLEAR = "unclear"


class IssueSeverity(str, Enum):
    """Severity levels for blocking issues."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class AgentIdentifier(str, Enum):
    """Known agent platforms for cross-agent consistency tracking."""

    CLAUDE_CODE = "claude-code"
    GITHUB_COPILOT = "github-copilot"
    CURSOR = "cursor"
    CODEX_CLI = "codex-cli"
    VS_CODE = "vs-code"
    WINDSURF = "windsurf"
    CLINE = "cline"
    UNKNOWN = "unknown"


class RubricScores(BaseModel):
    """Multi-dimensional rubric scores per ADR-016."""

    accuracy: float = Field(..., ge=0, le=10, description="Correctness score (0-10)")
    completeness: float = Field(..., ge=0, le=10, description="Completeness score (0-10)")
    clarity: float = Field(..., ge=0, le=10, description="Clarity score (0-10)")
    conciseness: float = Field(..., ge=0, le=10, description="Conciseness score (0-10)")
    relevance: Optional[float] = Field(None, ge=0, le=10, description="Relevance score (0-10)")


class BlockingIssue(BaseModel):
    """A blocking issue that caused verification to fail."""

    severity: IssueSeverity = Field(..., description="Issue severity level")
    file: str = Field(..., description="File path where issue was found")
    line: Optional[int] = Field(None, description="Line number (1-based)")
    message: str = Field(..., description="Description of the issue")


class VerificationContext(BaseModel):
    """
    Isolated verification context per ADR-034.

    Context is fresh for each verification, not inherited from session.
    This ensures verification independence and reproducibility.
    """

    session_id: Optional[str] = Field(
        default=None, description="Session ID (empty for isolated context)"
    )
    inherited_from_session: bool = Field(
        default=False, description="Whether context was inherited (should be False)"
    )


class VerificationRequest(BaseModel):
    """
    Request schema for verification API per ADR-034.

    Requires snapshot_id for reproducibility and target_paths
    to specify what should be verified.
    """

    snapshot_id: str = Field(..., min_length=1, description="Git commit SHA for reproducibility")
    target_paths: List[str] = Field(..., min_length=1, description="Files or directories to verify")
    rubric_focus: Optional[str] = Field(
        None, description="Optional focus area (Security, Performance, etc.)"
    )
    context: VerificationContext = Field(
        default_factory=VerificationContext,
        description="Isolated verification context",
    )
    confidence_threshold: float = Field(
        default=0.7, ge=0, le=1, description="Minimum confidence for PASS verdict"
    )

    @field_validator("target_paths")
    @classmethod
    def validate_target_paths(cls, v: List[str]) -> List[str]:
        """Ensure target_paths is not empty."""
        if not v:
            raise ValueError("target_paths must contain at least one path")
        return v


class VerifierResponse(BaseModel):
    """Response from a single verifier model."""

    model_id: str = Field(..., description="Model identifier")
    verdict: VerdictType = Field(..., description="Model's verdict")
    confidence: float = Field(..., ge=0, le=1, description="Model's confidence")
    rationale: Optional[str] = Field(None, description="Model's reasoning")
    rubric_scores: Optional[RubricScores] = Field(None, description="Detailed rubric scores")


class ConsensusResult(BaseModel):
    """Aggregated consensus from all verifiers."""

    decision: VerdictType = Field(..., description="Final consensus verdict")
    agreement_ratio: float = Field(..., ge=0, le=1, description="Ratio of verifiers agreeing")
    dissenting_models: List[str] = Field(default_factory=list, description="Models that disagreed")


class VersionInfo(BaseModel):
    """Version information for reproducibility."""

    rubric: str = Field(default="1.0", description="Rubric version")
    models: List[str] = Field(default_factory=list, description="Model versions used")
    aggregator: Optional[str] = Field(None, description="Aggregator/chairman model")


class VerificationResult(BaseModel):
    """
    Result schema for verification API per ADR-034.

    Provides machine-actionable output with verdict, confidence,
    blocking issues, and full audit trail support.

    Supports cross-agent consistency validation for multi-platform
    verification (Claude Code, GitHub Copilot, Cursor, etc.).
    """

    # Core identification
    verification_id: str = Field(..., description="Unique verification ID")

    # Core verification properties
    verdict: VerdictType = Field(..., description="Final verdict: pass/fail/unclear")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    timestamp: datetime = Field(..., description="Verification timestamp (UTC)")

    # Response integrity
    original_response_hash: str = Field(
        ..., description="Hash of original content for reproducibility"
    )

    # Verifier details
    verifier_responses: List[VerifierResponse] = Field(
        ..., description="Individual verifier responses"
    )
    consensus_result: ConsensusResult = Field(..., description="Aggregated consensus result")

    # Detailed scoring (optional)
    rubric_scores: Optional[RubricScores] = Field(None, description="Aggregated rubric scores")
    blocking_issues: List[BlockingIssue] = Field(
        default_factory=list, description="Issues that block approval"
    )

    # Synthesis
    rationale: Optional[str] = Field(None, description="Chairman's synthesis rationale")
    dissent: Optional[str] = Field(None, description="Notable dissenting opinions")

    # Cross-agent consistency fields (ADR-034 v2.0)
    invoking_agent: AgentIdentifier = Field(..., description="Platform that invoked verification")
    skill_version: str = Field(..., description="SKILL.md version used")
    protocol_version: str = Field(default="1.0", description="Verification protocol version")

    # Audit trail
    transcript_location: str = Field(..., description="Path to full transcript (.council/logs/...)")
    reproducibility_hash: str = Field(..., description="Hash of all inputs for reproducibility")

    # Version info
    version: Optional[VersionInfo] = Field(default=None, description="Version information")

    def validate_cross_agent_consistency(
        self, reference: VerificationResult, confidence_tolerance: float = 0.01
    ) -> bool:
        """
        Verify results are consistent across different invoking agents.

        Per ADR-034 v2.0, verification results should be consistent
        regardless of the invoking platform (Claude Code, Copilot, etc.).

        Args:
            reference: Another VerificationResult to compare against
            confidence_tolerance: Maximum allowed confidence difference

        Returns:
            True if results are consistent, False otherwise
        """
        # Same input must produce same output
        if self.original_response_hash != reference.original_response_hash:
            return False

        # Verdict must match
        if self.consensus_result.decision != reference.consensus_result.decision:
            return False

        # Confidence must be within tolerance
        if abs(self.confidence - reference.confidence) > confidence_tolerance:
            return False

        return True
