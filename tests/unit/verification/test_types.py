"""
Tests for verification types per ADR-034.

TDD Red Phase: These tests should fail until types.py is implemented.
"""

import json
from datetime import datetime
from typing import List

import pytest

from llm_council.verification.types import (
    AgentIdentifier,
    BlockingIssue,
    ConsensusResult,
    IssueSeverity,
    RubricScores,
    VerdictType,
    VerificationContext,
    VerificationRequest,
    VerificationResult,
    VerifierResponse,
)


class TestVerificationRequest:
    """Tests for VerificationRequest schema."""

    def test_verification_request_requires_snapshot_id(self):
        """VerificationRequest requires snapshot_id."""
        with pytest.raises(ValueError):
            VerificationRequest(
                target_paths=["src/main.py"],
                # Missing snapshot_id
            )

    def test_verification_request_requires_target_paths(self):
        """VerificationRequest requires target_paths."""
        with pytest.raises(ValueError):
            VerificationRequest(
                snapshot_id="abc123",
                # Missing target_paths
            )

    def test_verification_request_valid_construction(self):
        """VerificationRequest with valid fields constructs correctly."""
        request = VerificationRequest(
            snapshot_id="abc123def456",
            target_paths=["src/main.py", "tests/test_main.py"],
            rubric_focus="Security",
        )
        assert request.snapshot_id == "abc123def456"
        assert len(request.target_paths) == 2
        assert request.rubric_focus == "Security"

    def test_verification_request_optional_fields(self):
        """VerificationRequest optional fields have sensible defaults."""
        request = VerificationRequest(
            snapshot_id="abc123",
            target_paths=["src/main.py"],
        )
        assert request.rubric_focus is None
        assert request.context is not None  # Should have default context

    def test_verification_request_serialization(self):
        """VerificationRequest serializes to JSON correctly."""
        request = VerificationRequest(
            snapshot_id="abc123",
            target_paths=["src/main.py"],
            rubric_focus="Performance",
        )
        json_str = request.model_dump_json()
        data = json.loads(json_str)
        assert data["snapshot_id"] == "abc123"
        assert data["target_paths"] == ["src/main.py"]
        assert data["rubric_focus"] == "Performance"


class TestVerificationResult:
    """Tests for VerificationResult schema."""

    def test_verification_result_required_fields(self):
        """VerificationResult requires verdict, confidence, timestamp, version."""
        with pytest.raises(ValueError):
            VerificationResult(
                # Missing required fields
            )

    def test_verification_result_verdict_enum(self):
        """VerificationResult verdict must be pass, fail, or unclear."""
        result = VerificationResult(
            verification_id="test-123",
            verdict=VerdictType.PASS,
            confidence=0.95,
            timestamp=datetime.utcnow(),
            original_response_hash="abc123",
            verifier_responses=[],
            consensus_result=ConsensusResult(
                decision=VerdictType.PASS,
                agreement_ratio=1.0,
            ),
            invoking_agent=AgentIdentifier.CLAUDE_CODE,
            skill_version="1.0.0",
            transcript_location=".council/logs/test-123/",
            reproducibility_hash="hash123",
        )
        assert result.verdict == VerdictType.PASS

    def test_verification_result_confidence_bounds(self):
        """VerificationResult confidence must be between 0 and 1."""
        with pytest.raises(ValueError):
            VerificationResult(
                verification_id="test-123",
                verdict=VerdictType.PASS,
                confidence=1.5,  # Invalid: > 1
                timestamp=datetime.utcnow(),
                original_response_hash="abc123",
                verifier_responses=[],
                consensus_result=ConsensusResult(
                    decision=VerdictType.PASS,
                    agreement_ratio=1.0,
                ),
                invoking_agent=AgentIdentifier.CLAUDE_CODE,
                skill_version="1.0.0",
                transcript_location=".council/logs/test-123/",
                reproducibility_hash="hash123",
            )

    def test_verification_result_matches_adr034_schema(self):
        """VerificationResult matches ADR-034 JSON schema structure."""
        result = VerificationResult(
            verification_id="test-123",
            verdict=VerdictType.PASS,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            original_response_hash="abc123def456",
            verifier_responses=[
                VerifierResponse(
                    model_id="gpt-4o",
                    verdict=VerdictType.PASS,
                    confidence=0.9,
                    rationale="Code looks good.",
                )
            ],
            consensus_result=ConsensusResult(
                decision=VerdictType.PASS,
                agreement_ratio=1.0,
            ),
            rubric_scores=RubricScores(
                accuracy=8.5,
                completeness=7.0,
                clarity=9.0,
                conciseness=8.0,
            ),
            blocking_issues=[],
            rationale="All verifiers agreed the code meets requirements.",
            dissent=None,
            invoking_agent=AgentIdentifier.CLAUDE_CODE,
            skill_version="1.0.0",
            protocol_version="1.0",
            transcript_location=".council/logs/test-123/",
            reproducibility_hash="hash123",
        )

        # Verify JSON schema structure
        json_data = json.loads(result.model_dump_json())
        assert "verdict" in json_data
        assert json_data["verdict"] in ["pass", "fail", "unclear"]
        assert "confidence" in json_data
        assert 0 <= json_data["confidence"] <= 1
        assert "timestamp" in json_data
        assert "rubric_scores" in json_data

    def test_verification_result_blocking_issues_structure(self):
        """VerificationResult blocking_issues match ADR-034 schema."""
        result = VerificationResult(
            verification_id="test-123",
            verdict=VerdictType.FAIL,
            confidence=0.95,
            timestamp=datetime.utcnow(),
            original_response_hash="abc123",
            verifier_responses=[],
            consensus_result=ConsensusResult(
                decision=VerdictType.FAIL,
                agreement_ratio=1.0,
            ),
            blocking_issues=[
                BlockingIssue(
                    severity=IssueSeverity.CRITICAL,
                    file="src/main.py",
                    line=42,
                    message="SQL injection vulnerability detected",
                ),
                BlockingIssue(
                    severity=IssueSeverity.MAJOR,
                    file="src/auth.py",
                    line=15,
                    message="Missing input validation",
                ),
            ],
            invoking_agent=AgentIdentifier.CLAUDE_CODE,
            skill_version="1.0.0",
            transcript_location=".council/logs/test-123/",
            reproducibility_hash="hash123",
        )

        assert len(result.blocking_issues) == 2
        assert result.blocking_issues[0].severity == IssueSeverity.CRITICAL
        assert result.blocking_issues[0].line == 42


class TestCrossAgentConsistency:
    """Tests for cross-agent consistency validation (ADR-034 v2.0)."""

    def test_validate_cross_agent_consistency_same_results(self):
        """validate_cross_agent_consistency returns True for identical results."""
        base_kwargs = dict(
            verification_id="test-123",
            verdict=VerdictType.PASS,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            original_response_hash="abc123",
            verifier_responses=[],
            consensus_result=ConsensusResult(
                decision=VerdictType.PASS,
                agreement_ratio=1.0,
            ),
            skill_version="1.0.0",
            transcript_location=".council/logs/test-123/",
            reproducibility_hash="hash123",
        )

        result1 = VerificationResult(
            invoking_agent=AgentIdentifier.CLAUDE_CODE,
            **base_kwargs,
        )
        result2 = VerificationResult(
            invoking_agent=AgentIdentifier.GITHUB_COPILOT,
            **base_kwargs,
        )

        assert result1.validate_cross_agent_consistency(result2) is True

    def test_validate_cross_agent_consistency_different_hash(self):
        """validate_cross_agent_consistency returns False for different input hashes."""
        base_kwargs = dict(
            verification_id="test-123",
            verdict=VerdictType.PASS,
            confidence=0.85,
            timestamp=datetime.utcnow(),
            verifier_responses=[],
            consensus_result=ConsensusResult(
                decision=VerdictType.PASS,
                agreement_ratio=1.0,
            ),
            skill_version="1.0.0",
            transcript_location=".council/logs/test-123/",
            reproducibility_hash="hash123",
        )

        result1 = VerificationResult(
            invoking_agent=AgentIdentifier.CLAUDE_CODE,
            original_response_hash="abc123",
            **base_kwargs,
        )
        result2 = VerificationResult(
            invoking_agent=AgentIdentifier.GITHUB_COPILOT,
            original_response_hash="xyz789",  # Different hash
            **base_kwargs,
        )

        assert result1.validate_cross_agent_consistency(result2) is False

    def test_validate_cross_agent_consistency_different_verdict(self):
        """validate_cross_agent_consistency returns False for different verdicts."""
        base_kwargs = dict(
            verification_id="test-123",
            confidence=0.85,
            timestamp=datetime.utcnow(),
            original_response_hash="abc123",
            verifier_responses=[],
            skill_version="1.0.0",
            transcript_location=".council/logs/test-123/",
            reproducibility_hash="hash123",
        )

        result1 = VerificationResult(
            invoking_agent=AgentIdentifier.CLAUDE_CODE,
            verdict=VerdictType.PASS,
            consensus_result=ConsensusResult(
                decision=VerdictType.PASS,
                agreement_ratio=1.0,
            ),
            **base_kwargs,
        )
        result2 = VerificationResult(
            invoking_agent=AgentIdentifier.GITHUB_COPILOT,
            verdict=VerdictType.FAIL,  # Different verdict
            consensus_result=ConsensusResult(
                decision=VerdictType.FAIL,
                agreement_ratio=1.0,
            ),
            **base_kwargs,
        )

        assert result1.validate_cross_agent_consistency(result2) is False

    def test_validate_cross_agent_consistency_confidence_tolerance(self):
        """validate_cross_agent_consistency allows small confidence differences."""
        base_kwargs = dict(
            verification_id="test-123",
            verdict=VerdictType.PASS,
            timestamp=datetime.utcnow(),
            original_response_hash="abc123",
            verifier_responses=[],
            consensus_result=ConsensusResult(
                decision=VerdictType.PASS,
                agreement_ratio=1.0,
            ),
            skill_version="1.0.0",
            transcript_location=".council/logs/test-123/",
            reproducibility_hash="hash123",
        )

        result1 = VerificationResult(
            invoking_agent=AgentIdentifier.CLAUDE_CODE,
            confidence=0.850,
            **base_kwargs,
        )
        result2 = VerificationResult(
            invoking_agent=AgentIdentifier.GITHUB_COPILOT,
            confidence=0.855,  # Within 0.01 tolerance
            **base_kwargs,
        )

        assert result1.validate_cross_agent_consistency(result2) is True


class TestAgentIdentifier:
    """Tests for AgentIdentifier enum."""

    def test_agent_identifier_values(self):
        """AgentIdentifier includes major platforms."""
        assert AgentIdentifier.CLAUDE_CODE.value == "claude-code"
        assert AgentIdentifier.GITHUB_COPILOT.value == "github-copilot"
        assert AgentIdentifier.CURSOR.value == "cursor"
        assert AgentIdentifier.CODEX_CLI.value == "codex-cli"


class TestVerdictType:
    """Tests for VerdictType enum."""

    def test_verdict_type_values(self):
        """VerdictType has pass, fail, unclear values."""
        assert VerdictType.PASS.value == "pass"
        assert VerdictType.FAIL.value == "fail"
        assert VerdictType.UNCLEAR.value == "unclear"


class TestRubricScores:
    """Tests for RubricScores model."""

    def test_rubric_scores_bounds(self):
        """RubricScores values must be between 0 and 10."""
        with pytest.raises(ValueError):
            RubricScores(
                accuracy=11.0,  # Invalid: > 10
                completeness=5.0,
                clarity=5.0,
                conciseness=5.0,
            )

    def test_rubric_scores_valid(self):
        """RubricScores accepts valid values."""
        scores = RubricScores(
            accuracy=8.5,
            completeness=7.0,
            clarity=9.0,
            conciseness=8.0,
        )
        assert scores.accuracy == 8.5


class TestVerificationContext:
    """Tests for VerificationContext model."""

    def test_verification_context_isolation(self):
        """VerificationContext should be isolated (not inherit from session)."""
        ctx = VerificationContext()
        assert ctx.session_id is None or ctx.session_id == ""
        # Context should be fresh, not inherited


class TestJSONSchemaExport:
    """Tests for JSON Schema export capability."""

    def test_verification_result_json_schema_export(self):
        """VerificationResult can export JSON Schema."""
        schema = VerificationResult.model_json_schema()
        assert schema["type"] == "object"
        assert "verdict" in schema["properties"]
        assert "confidence" in schema["properties"]
        assert "timestamp" in schema["properties"]

    def test_verification_request_json_schema_export(self):
        """VerificationRequest can export JSON Schema."""
        schema = VerificationRequest.model_json_schema()
        assert schema["type"] == "object"
        assert "snapshot_id" in schema["properties"]
        assert "target_paths" in schema["properties"]
