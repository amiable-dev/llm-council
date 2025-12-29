"""Tests for Jury Mode verdict types (ADR-025b).

These tests verify the VerdictType enum, VerdictResult dataclass,
and verdict processing logic for Binary, Tie-Breaker, and Constructive Dissent modes.

Reference: ADR-025b Council Validation (2025-12-23)
"""

import json
import pytest
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch, MagicMock


class TestVerdictType:
    """Tests for VerdictType enum."""

    def test_verdict_type_synthesis_is_default(self):
        """SYNTHESIS should be the default verdict type for backward compatibility."""
        from llm_council.verdict import VerdictType

        assert VerdictType.SYNTHESIS.value == "synthesis"

    def test_verdict_type_binary_exists(self):
        """BINARY verdict type should exist for go/no-go decisions."""
        from llm_council.verdict import VerdictType

        assert VerdictType.BINARY.value == "binary"

    def test_verdict_type_tie_breaker_exists(self):
        """TIE_BREAKER verdict type should exist for deadlocked decisions."""
        from llm_council.verdict import VerdictType

        assert VerdictType.TIE_BREAKER.value == "tie_breaker"

    def test_verdict_type_values_are_strings(self):
        """All verdict type values should be lowercase strings."""
        from llm_council.verdict import VerdictType

        for vt in VerdictType:
            assert isinstance(vt.value, str)
            assert vt.value == vt.value.lower()


class TestVerdictResult:
    """Tests for VerdictResult dataclass."""

    def test_verdict_result_required_fields(self):
        """VerdictResult should have required fields: verdict_type, verdict, confidence, rationale."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.BINARY,
            verdict="approved",
            confidence=0.85,
            rationale="All models agreed on quality.",
        )

        assert result.verdict_type == VerdictType.BINARY
        assert result.verdict == "approved"
        assert result.confidence == 0.85
        assert result.rationale == "All models agreed on quality."

    def test_verdict_result_optional_fields_have_defaults(self):
        """VerdictResult optional fields should have sensible defaults."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.SYNTHESIS,
            verdict="The synthesized answer...",
            confidence=0.9,
            rationale="Based on consensus.",
        )

        assert result.dissent is None
        assert result.deadlocked is False
        assert result.borda_spread == 0.0

    def test_verdict_result_with_dissent(self):
        """VerdictResult should support minority opinion via dissent field."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.BINARY,
            verdict="approved",
            confidence=0.7,
            rationale="Majority approved.",
            dissent="Minority perspective: One model raised security concerns.",
        )

        assert result.dissent is not None
        assert "security concerns" in result.dissent

    def test_verdict_result_with_deadlock(self):
        """VerdictResult should track when tie-breaker was used."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.TIE_BREAKER,
            verdict="approved",
            confidence=0.6,
            rationale="Chairman broke the tie.",
            deadlocked=True,
            borda_spread=0.05,
        )

        assert result.deadlocked is True
        assert result.borda_spread == 0.05

    def test_verdict_result_confidence_range(self):
        """Confidence should be a float between 0.0 and 1.0."""
        from llm_council.verdict import VerdictResult, VerdictType

        # Valid confidence values
        for conf in [0.0, 0.5, 1.0, 0.85]:
            result = VerdictResult(
                verdict_type=VerdictType.BINARY,
                verdict="approved",
                confidence=conf,
                rationale="Test",
            )
            assert 0.0 <= result.confidence <= 1.0


class TestBinaryVerdict:
    """Tests for Binary verdict mode logic."""

    def test_binary_verdict_returns_approved_or_rejected(self):
        """Binary verdict should only return 'approved' or 'rejected'."""
        from llm_council.verdict import parse_binary_verdict

        # Test approved
        approved_json = '{"verdict": "approved", "confidence": 0.9, "rationale": "Good"}'
        result = parse_binary_verdict(approved_json)
        assert result.verdict in ["approved", "rejected"]
        assert result.verdict == "approved"

        # Test rejected
        rejected_json = '{"verdict": "rejected", "confidence": 0.8, "rationale": "Bad"}'
        result = parse_binary_verdict(rejected_json)
        assert result.verdict == "rejected"

    def test_binary_verdict_includes_confidence(self):
        """Binary verdict should include confidence score."""
        from llm_council.verdict import parse_binary_verdict

        json_str = '{"verdict": "approved", "confidence": 0.85, "rationale": "Quality assessment"}'
        result = parse_binary_verdict(json_str)

        assert result.confidence == 0.85

    def test_binary_verdict_includes_rationale(self):
        """Binary verdict should include rationale."""
        from llm_council.verdict import parse_binary_verdict

        json_str = '{"verdict": "approved", "confidence": 0.9, "rationale": "All criteria met"}'
        result = parse_binary_verdict(json_str)

        assert result.rationale == "All criteria met"

    def test_binary_verdict_invalid_verdict_value_raises_error(self):
        """Binary verdict with invalid verdict value should raise ValueError."""
        from llm_council.verdict import parse_binary_verdict

        invalid_json = '{"verdict": "maybe", "confidence": 0.5, "rationale": "Unsure"}'

        with pytest.raises(ValueError, match="Binary verdict must be 'approved' or 'rejected'"):
            parse_binary_verdict(invalid_json)

    def test_binary_verdict_malformed_json_raises_error(self):
        """Binary verdict with malformed JSON should raise ValueError."""
        from llm_council.verdict import parse_binary_verdict

        with pytest.raises(ValueError, match="Failed to parse"):
            parse_binary_verdict("not valid json")

    def test_binary_verdict_missing_fields_raises_error(self):
        """Binary verdict missing required fields should raise ValueError."""
        from llm_council.verdict import parse_binary_verdict

        # Missing confidence
        incomplete_json = '{"verdict": "approved", "rationale": "Test"}'

        with pytest.raises(ValueError, match="Missing required field"):
            parse_binary_verdict(incomplete_json)

    def test_binary_verdict_extracts_from_code_block(self):
        """Binary verdict should extract JSON from markdown code blocks."""
        from llm_council.verdict import parse_binary_verdict

        with_code_block = """
Here is my verdict:

```json
{"verdict": "approved", "confidence": 0.9, "rationale": "All tests pass"}
```
"""
        result = parse_binary_verdict(with_code_block)
        assert result.verdict == "approved"


class TestTieBreaker:
    """Tests for Tie-Breaker mode logic."""

    def test_detects_deadlock_within_threshold(self):
        """Should detect deadlock when top 2 scores are within threshold."""
        from llm_council.verdict import detect_deadlock

        # Scores within 0.1 threshold
        scores = [0.85, 0.84, 0.5, 0.3]
        assert detect_deadlock(scores, threshold=0.1) is True

    def test_no_deadlock_clear_winner(self):
        """Should not detect deadlock when there's a clear winner."""
        from llm_council.verdict import detect_deadlock

        # Clear winner (gap > 0.1)
        scores = [0.95, 0.7, 0.5, 0.3]
        assert detect_deadlock(scores, threshold=0.1) is False

    def test_deadlock_single_score(self):
        """Should not detect deadlock with only one score."""
        from llm_council.verdict import detect_deadlock

        scores = [0.8]
        assert detect_deadlock(scores, threshold=0.1) is False

    def test_deadlock_empty_scores(self):
        """Should handle empty scores gracefully."""
        from llm_council.verdict import detect_deadlock

        scores = []
        assert detect_deadlock(scores, threshold=0.1) is False

    def test_deadlock_threshold_configurable(self):
        """Deadlock threshold should be configurable."""
        from llm_council.verdict import detect_deadlock

        scores = [0.85, 0.80, 0.5]

        # With small threshold, this is NOT a deadlock
        assert detect_deadlock(scores, threshold=0.03) is False

        # With larger threshold, this IS a deadlock
        assert detect_deadlock(scores, threshold=0.1) is True

    def test_tie_breaker_verdict_includes_deadlock_flag(self):
        """Tie-breaker verdict should set deadlocked=True."""
        from llm_council.verdict import VerdictResult, VerdictType, parse_tie_breaker_verdict

        json_str = """
        {
            "verdict": "approved",
            "confidence": 0.6,
            "rationale": "Chose A over B",
            "deadlock_resolution": "A had better code quality"
        }
        """

        result = parse_tie_breaker_verdict(json_str)
        assert result.deadlocked is True
        assert result.verdict_type == VerdictType.TIE_BREAKER

    def test_tie_breaker_logs_decision(self):
        """Tie-breaker decisions should be logged for audit."""
        from llm_council.verdict import parse_tie_breaker_verdict
        import logging

        json_str = '{"verdict": "rejected", "confidence": 0.55, "rationale": "Edge case", "deadlock_resolution": "Tie broken by quality"}'

        with patch("llm_council.verdict.logger") as mock_logger:
            result = parse_tie_breaker_verdict(json_str)
            # Should log at INFO level
            mock_logger.info.assert_called()


class TestVerdictAPI:
    """Tests for verdict API integration."""

    def test_default_verdict_type_is_synthesis(self):
        """Default verdict_type should be SYNTHESIS for backward compatibility."""
        from llm_council.verdict import get_default_verdict_type, VerdictType

        assert get_default_verdict_type() == VerdictType.SYNTHESIS

    def test_binary_mode_chairman_prompt_is_different(self):
        """Binary mode should use a different chairman prompt."""
        from llm_council.verdict import get_chairman_prompt, VerdictType

        synthesis_prompt = get_chairman_prompt(VerdictType.SYNTHESIS, query="test", rankings="...")
        binary_prompt = get_chairman_prompt(VerdictType.BINARY, query="test", rankings="...")

        assert synthesis_prompt != binary_prompt
        assert "BINARY VERDICT" in binary_prompt
        assert "approved" in binary_prompt.lower() or "rejected" in binary_prompt.lower()

    def test_tie_breaker_mode_chairman_prompt_mentions_deadlock(self):
        """Tie-breaker mode should mention deadlock in prompt."""
        from llm_council.verdict import get_chairman_prompt, VerdictType

        prompt = get_chairman_prompt(VerdictType.TIE_BREAKER, query="test", rankings="...")

        assert "deadlock" in prompt.lower() or "tie" in prompt.lower()

    def test_verdict_type_from_string(self):
        """Should convert string to VerdictType enum."""
        from llm_council.verdict import verdict_type_from_string, VerdictType

        assert verdict_type_from_string("synthesis") == VerdictType.SYNTHESIS
        assert verdict_type_from_string("binary") == VerdictType.BINARY
        assert verdict_type_from_string("tie_breaker") == VerdictType.TIE_BREAKER

        # Case insensitive
        assert verdict_type_from_string("BINARY") == VerdictType.BINARY
        assert verdict_type_from_string("Binary") == VerdictType.BINARY

    def test_verdict_type_from_string_invalid_raises_error(self):
        """Invalid verdict type string should raise ValueError."""
        from llm_council.verdict import verdict_type_from_string

        with pytest.raises(ValueError, match="Unknown verdict type"):
            verdict_type_from_string("invalid_type")


class TestVerdictResultSerialization:
    """Tests for VerdictResult serialization."""

    def test_verdict_result_to_dict(self):
        """VerdictResult should be serializable to dict."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.BINARY,
            verdict="approved",
            confidence=0.9,
            rationale="All good",
        )

        d = result.to_dict()

        assert d["verdict_type"] == "binary"
        assert d["verdict"] == "approved"
        assert d["confidence"] == 0.9
        assert d["rationale"] == "All good"

    def test_verdict_result_to_json(self):
        """VerdictResult should be serializable to JSON."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.BINARY,
            verdict="rejected",
            confidence=0.8,
            rationale="Failed checks",
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["verdict"] == "rejected"

    def test_verdict_result_from_dict(self):
        """VerdictResult should be constructable from dict."""
        from llm_council.verdict import VerdictResult, VerdictType

        d = {
            "verdict_type": "binary",
            "verdict": "approved",
            "confidence": 0.95,
            "rationale": "Excellent",
        }

        result = VerdictResult.from_dict(d)

        assert result.verdict_type == VerdictType.BINARY
        assert result.verdict == "approved"


class TestBordaSpread:
    """Tests for Borda score spread calculation."""

    def test_calculate_borda_spread(self):
        """Should calculate spread between highest and lowest Borda scores."""
        from llm_council.verdict import calculate_borda_spread

        scores = {"A": 3.5, "B": 2.0, "C": 1.5}
        spread = calculate_borda_spread(scores)

        assert spread == 2.0  # 3.5 - 1.5

    def test_borda_spread_single_score(self):
        """Spread with single score should be 0."""
        from llm_council.verdict import calculate_borda_spread

        scores = {"A": 3.0}
        spread = calculate_borda_spread(scores)

        assert spread == 0.0

    def test_borda_spread_empty_scores(self):
        """Spread with empty scores should be 0."""
        from llm_council.verdict import calculate_borda_spread

        scores = {}
        spread = calculate_borda_spread(scores)

        assert spread == 0.0

    def test_borda_spread_identical_scores(self):
        """Spread with identical scores should be 0."""
        from llm_council.verdict import calculate_borda_spread

        scores = {"A": 2.0, "B": 2.0, "C": 2.0}
        spread = calculate_borda_spread(scores)

        assert spread == 0.0


class TestDeadlockEscalation:
    """Tests for automatic deadlock detection and escalation."""

    def test_deadlock_detection_with_close_scores(self):
        """Deadlock should be detected when top 2 scores are close."""
        from llm_council.verdict import detect_deadlock

        # Scores where top 2 are within 0.1
        scores = [0.85, 0.84, 0.5, 0.3]
        assert detect_deadlock(scores, threshold=0.1) is True

    def test_no_deadlock_with_clear_winner(self):
        """No deadlock when there's a clear winner."""
        from llm_council.verdict import detect_deadlock

        # Clear winner (gap > 0.1)
        scores = [0.95, 0.7, 0.5, 0.3]
        assert detect_deadlock(scores, threshold=0.1) is False

    def test_escalation_changes_verdict_type(self):
        """When deadlock is detected, verdict type should escalate to TIE_BREAKER."""
        from llm_council.verdict import VerdictType, detect_deadlock

        # Simulate deadlock detection
        scores = [0.55, 0.54, 0.3, 0.2]
        is_deadlocked = detect_deadlock(scores, threshold=0.1)

        verdict_type = VerdictType.BINARY
        if is_deadlocked:
            effective_verdict_type = VerdictType.TIE_BREAKER
        else:
            effective_verdict_type = verdict_type

        assert is_deadlocked is True
        assert effective_verdict_type == VerdictType.TIE_BREAKER

    def test_tie_breaker_prompt_includes_deadlock_context(self):
        """Tie-breaker prompt should include deadlock context."""
        from llm_council.verdict import get_chairman_prompt, VerdictType

        prompt = get_chairman_prompt(
            VerdictType.TIE_BREAKER,
            query="Should we deploy?",
            rankings="A: 0.55, B: 0.54",
            top_candidates="Model A, Model B",
        )

        assert "DEADLOCK" in prompt.upper() or "TIE" in prompt.upper()
        assert "Model A" in prompt or "DECIDING" in prompt.upper()

    def test_verdict_result_preserves_deadlock_flag(self):
        """VerdictResult should preserve deadlocked flag through serialization."""
        from llm_council.verdict import VerdictResult, VerdictType

        result = VerdictResult(
            verdict_type=VerdictType.TIE_BREAKER,
            verdict="approved",
            confidence=0.6,
            rationale="Chairman broke the tie",
            deadlocked=True,
        )

        d = result.to_dict()
        assert d["deadlocked"] is True

        restored = VerdictResult.from_dict(d)
        assert restored.deadlocked is True
