"""
Unit tests for verification result formatting (issue #301).

TDD tests for format_verification_result() function that produces
human-readable output from verification results.
"""

import pytest


class TestFormatVerificationResult:
    """Tests for format_verification_result() function."""

    @pytest.fixture
    def pass_result(self):
        """Verification result with PASS verdict."""
        return {
            "verification_id": "abc12345",
            "verdict": "pass",
            "confidence": 0.85,
            "exit_code": 0,
            "rubric_scores": {
                "accuracy": 9.0,
                "relevance": 8.5,
                "completeness": 8.0,
                "conciseness": 7.5,
                "clarity": 9.0,
            },
            "blocking_issues": [],
            "rationale": "The code meets all quality standards. Implementation is correct and well-structured. No security vulnerabilities detected.",
            "transcript_location": ".council/logs/2026-01-01T14-00-00-abc12345",
        }

    @pytest.fixture
    def fail_result(self):
        """Verification result with FAIL verdict."""
        return {
            "verification_id": "def67890",
            "verdict": "fail",
            "confidence": 0.90,
            "exit_code": 1,
            "rubric_scores": {
                "accuracy": 3.0,
                "relevance": 8.0,
                "completeness": 5.0,
                "conciseness": None,
                "clarity": 6.0,
            },
            "blocking_issues": [
                {
                    "severity": "critical",
                    "description": "SQL injection vulnerability in user input handling",
                    "location": "src/api.py:45",
                },
                {
                    "severity": "major",
                    "description": "Missing input validation",
                    "location": "src/api.py:52",
                },
            ],
            "rationale": "Critical security issues found. SQL injection vulnerability must be fixed before deployment.",
            "transcript_location": ".council/logs/2026-01-01T14-00-00-def67890",
        }

    @pytest.fixture
    def unclear_result(self):
        """Verification result with UNCLEAR verdict."""
        return {
            "verification_id": "ghi11223",
            "verdict": "unclear",
            "confidence": 0.55,
            "exit_code": 2,
            "rubric_scores": {
                "accuracy": None,
                "relevance": None,
                "completeness": None,
                "conciseness": None,
                "clarity": None,
            },
            "blocking_issues": [],
            "rationale": "Unable to determine verdict due to low confidence scores.",
            "transcript_location": ".council/logs/2026-01-01T14-00-00-ghi11223",
        }

    def test_function_exists(self):
        """format_verification_result should be importable."""
        from llm_council.verification.formatting import format_verification_result

        assert callable(format_verification_result)

    def test_returns_string(self, pass_result):
        """Should return a string."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        assert isinstance(output, str)

    def test_includes_verdict_with_emoji_pass(self, pass_result):
        """PASS verdict should include checkmark emoji."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        assert "PASS" in output
        assert "✅" in output

    def test_includes_verdict_with_emoji_fail(self, fail_result):
        """FAIL verdict should include X emoji."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(fail_result)
        assert "FAIL" in output
        assert "❌" in output

    def test_includes_verdict_with_emoji_unclear(self, unclear_result):
        """UNCLEAR verdict should include warning emoji."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(unclear_result)
        assert "UNCLEAR" in output
        assert "⚠️" in output

    def test_includes_confidence_score(self, pass_result):
        """Should include confidence score."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        assert "0.85" in output or "85%" in output

    def test_includes_exit_code(self, pass_result):
        """Should include exit code."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        assert "exit code" in output.lower() or "Exit Code" in output
        assert "0" in output

    def test_includes_rubric_scores_table(self, pass_result):
        """Should include rubric scores in table format."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        # Check for table structure
        assert "|" in output
        # Check for dimension names
        assert "Accuracy" in output or "accuracy" in output
        # Check for score values
        assert "9.0" in output or "9" in output

    def test_handles_null_rubric_scores(self, unclear_result):
        """Should handle None rubric scores gracefully."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(unclear_result)
        # Should not raise exception
        assert "N/A" in output or "-" in output or "None" in output

    def test_includes_blocking_issues(self, fail_result):
        """Should list blocking issues for FAIL verdict."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(fail_result)
        assert "Blocking Issues" in output or "blocking" in output.lower()
        assert "SQL injection" in output
        assert "critical" in output.lower()

    def test_includes_transcript_location(self, pass_result):
        """Should include transcript location."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        assert ".council/logs/" in output
        assert "abc12345" in output

    def test_includes_rationale_summary(self, pass_result):
        """Should include rationale (possibly summarized)."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        assert "Rationale" in output or "rationale" in output.lower()
        # At least some of the rationale text should appear
        assert "quality standards" in output or "correct" in output

    def test_no_blocking_issues_message(self, pass_result):
        """Should show 'None' for empty blocking issues."""
        from llm_council.verification.formatting import format_verification_result

        output = format_verification_result(pass_result)
        # Should indicate no blocking issues
        assert "None" in output or "No blocking issues" in output


class TestFormatVerdictHeader:
    """Tests for the verdict header line formatting."""

    def test_header_format(self):
        """Header should follow format: Council Verification Result: VERDICT EMOJI."""
        from llm_council.verification.formatting import format_verification_result

        result = {
            "verification_id": "test",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "OK",
            "transcript_location": ".council/logs/test",
        }
        output = format_verification_result(result)
        first_line = output.split("\n")[0]
        assert "Council Verification" in first_line
        assert "PASS" in first_line


class TestRubricScoresFormatting:
    """Tests for rubric scores table formatting."""

    def test_all_dimensions_present(self):
        """All rubric dimensions should be in output."""
        from llm_council.verification.formatting import format_verification_result

        result = {
            "verification_id": "test",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {
                "accuracy": 8.0,
                "relevance": 7.5,
                "completeness": 9.0,
                "conciseness": 8.5,
                "clarity": 9.0,
            },
            "blocking_issues": [],
            "rationale": "OK",
            "transcript_location": ".council/logs/test",
        }
        output = format_verification_result(result)

        for dim in ["accuracy", "relevance", "completeness", "conciseness", "clarity"]:
            assert dim.lower() in output.lower() or dim.capitalize() in output

    def test_scores_formatted_with_denominator(self):
        """Scores should show X/10 format."""
        from llm_council.verification.formatting import format_verification_result

        result = {
            "verification_id": "test",
            "verdict": "pass",
            "confidence": 0.9,
            "exit_code": 0,
            "rubric_scores": {"accuracy": 8.5},
            "blocking_issues": [],
            "rationale": "OK",
            "transcript_location": ".council/logs/test",
        }
        output = format_verification_result(result)
        assert "8.5/10" in output or "8.5 / 10" in output
