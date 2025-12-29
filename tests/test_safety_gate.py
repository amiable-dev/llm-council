"""Tests for ADR-016 Safety Gate: Pass/fail gate before rubric applies.

TDD tests for safety pre-check that filters harmful content.
"""

import pytest

from llm_council.safety_gate import (
    SafetyCheckResult,
    check_response_safety,
    apply_safety_gate_to_score,
    SAFETY_PATTERNS,
    DEFAULT_SAFETY_SCORE_CAP,
)


class TestSafetyCheckResult:
    """Tests for SafetyCheckResult dataclass."""

    def test_passed_result(self):
        """Test creating a passed safety check result."""
        result = SafetyCheckResult(passed=True)
        assert result.passed is True
        assert result.reason is None
        assert result.flagged_patterns == []

    def test_failed_result_with_reason(self):
        """Test creating a failed result with reason."""
        result = SafetyCheckResult(
            passed=False,
            reason="Contains harmful instructions",
            flagged_patterns=["dangerous_instructions"],
        )
        assert result.passed is False
        assert result.reason == "Contains harmful instructions"
        assert "dangerous_instructions" in result.flagged_patterns


class TestSafetyPatterns:
    """Tests for safety pattern detection."""

    def test_safe_response_passes(self):
        """Normal helpful response should pass safety check."""
        response = """
        Here's how to make a great pasta sauce:
        1. Start with olive oil and garlic
        2. Add crushed tomatoes
        3. Season with basil and oregano
        4. Simmer for 20 minutes
        """
        result = check_response_safety(response)
        assert result.passed is True

    def test_dangerous_instructions_fail(self):
        """Response with dangerous instructions should fail."""
        response = """
        To make an explosive device, you'll need:
        - Ammonium nitrate
        - Fuel oil
        Mix them together and...
        """
        result = check_response_safety(response)
        assert result.passed is False
        assert "dangerous" in result.reason.lower() or "harmful" in result.reason.lower()

    def test_weapon_instructions_fail(self):
        """Response with weapon-making instructions should fail."""
        response = """
        Here's how to build a gun at home:
        First, obtain the barrel...
        """
        result = check_response_safety(response)
        assert result.passed is False

    def test_malware_instructions_fail(self):
        """Response with malware/hacking instructions should fail."""
        response = """
        To hack into someone's email account:
        1. Use a phishing page
        2. Capture their credentials
        3. Access their account without permission
        """
        result = check_response_safety(response)
        assert result.passed is False

    def test_self_harm_content_fails(self):
        """Response encouraging self-harm should fail."""
        response = """
        If you want to hurt yourself, here are some methods...
        """
        result = check_response_safety(response)
        assert result.passed is False

    def test_educational_security_content_passes(self):
        """Educational security content in proper context should pass."""
        response = """
        In cybersecurity education, we study attack vectors to defend against them.
        Common vulnerabilities include SQL injection, which occurs when user input
        is not properly sanitized. To prevent this, always use parameterized queries.
        """
        result = check_response_safety(response)
        assert result.passed is True

    def test_refusal_response_passes(self):
        """Appropriate refusal to harmful request should pass."""
        response = """
        I can't provide instructions for creating weapons or harmful devices.
        This would be dangerous and potentially illegal. Instead, I'd encourage
        you to explore legal and safe hobbies.
        """
        result = check_response_safety(response)
        assert result.passed is True

    def test_empty_response_passes(self):
        """Empty response should pass (not harmful, just unhelpful)."""
        result = check_response_safety("")
        assert result.passed is True

    def test_pii_exposure_fails(self):
        """Response exposing PII patterns should fail."""
        response = """
        Here's the person's information:
        SSN: 123-45-6789
        Credit card: 4111-1111-1111-1111
        """
        result = check_response_safety(response)
        assert result.passed is False
        assert "pii" in result.reason.lower() or "personal" in result.reason.lower()


class TestApplySafetyGate:
    """Tests for applying safety gate to scores."""

    def test_passed_safety_no_cap(self):
        """Score should not be capped if safety check passes."""
        safety_result = SafetyCheckResult(passed=True)
        original_score = 8.5
        final_score = apply_safety_gate_to_score(original_score, safety_result)
        assert final_score == 8.5

    def test_failed_safety_caps_score(self):
        """Score should be capped if safety check fails."""
        safety_result = SafetyCheckResult(passed=False, reason="Harmful content detected")
        original_score = 9.0
        final_score = apply_safety_gate_to_score(original_score, safety_result)
        assert final_score <= DEFAULT_SAFETY_SCORE_CAP
        assert final_score == 0.0  # Default cap is 0

    def test_already_low_score_unchanged(self):
        """Low score should remain low (not inflated by cap)."""
        safety_result = SafetyCheckResult(passed=False, reason="Harmful content")
        original_score = 0.0
        final_score = apply_safety_gate_to_score(original_score, safety_result)
        assert final_score == 0.0

    def test_custom_cap_applied(self):
        """Custom safety cap should be applied."""
        safety_result = SafetyCheckResult(passed=False, reason="Harmful content")
        original_score = 8.0
        final_score = apply_safety_gate_to_score(original_score, safety_result, cap=2.0)
        assert final_score == 2.0


class TestSafetyGateIntegration:
    """Integration tests for safety gate with rubric scoring."""

    def test_safety_gate_before_accuracy_ceiling(self):
        """Safety gate should apply before accuracy ceiling."""
        from llm_council.rubric import calculate_weighted_score_with_accuracy_ceiling

        # High accuracy, high other scores - would normally score well
        scores = {
            "accuracy": 9,
            "relevance": 9,
            "completeness": 9,
            "conciseness": 9,
            "clarity": 9,
        }

        # Calculate rubric score (high)
        rubric_score = calculate_weighted_score_with_accuracy_ceiling(scores)
        assert rubric_score == 9.0

        # But if safety fails, score should be capped at 0
        safety_result = SafetyCheckResult(passed=False, reason="Harmful instructions detected")
        final_score = apply_safety_gate_to_score(rubric_score, safety_result)
        assert final_score == 0.0

    def test_safe_response_uses_rubric_score(self):
        """Safe response should use normal rubric score."""
        from llm_council.rubric import calculate_weighted_score_with_accuracy_ceiling

        scores = {
            "accuracy": 8,
            "relevance": 7,
            "completeness": 8,
            "conciseness": 7,
            "clarity": 8,
        }

        rubric_score = calculate_weighted_score_with_accuracy_ceiling(scores)
        safety_result = SafetyCheckResult(passed=True)
        final_score = apply_safety_gate_to_score(rubric_score, safety_result)

        # Score unchanged
        assert final_score == rubric_score


class TestSafetyConfiguration:
    """Tests for safety gate configuration."""

    def test_safety_patterns_exist(self):
        """Safety patterns dictionary should be populated."""
        assert len(SAFETY_PATTERNS) > 0
        assert "dangerous_instructions" in SAFETY_PATTERNS or len(SAFETY_PATTERNS) >= 3

    def test_default_cap_is_zero(self):
        """Default safety score cap should be 0 (complete disqualification)."""
        assert DEFAULT_SAFETY_SCORE_CAP == 0.0
