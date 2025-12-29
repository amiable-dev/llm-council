import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from llm_council.bias_persistence import BiasMetricRecord
from llm_council.bias_aggregation import (
    generate_bias_report_csv,
    generate_bias_report_text,
    _generate_ascii_chart,
    BiasMetricRecord,
)


class TestBiasAggregation:
    """Tests for bias aggregation and reporting."""

    def test_ascii_chart_generation(self):
        """Chart renders correctly with scaled bars."""
        data = {"A": 10.0, "B": 5.0, "C": 0.0}
        chart = _generate_ascii_chart(data, "Test Chart", width=10)

        assert "Test Chart:" in chart
        # A is max (10.0), should be full width (10 blocks)
        assert "A" in chart and "██████████" in chart
        # B is half (5.0), should be ~5 blocks
        assert "B" in chart and "█████" in chart
        # C is 0, should be empty bar
        assert "C" in chart and "|          |" in chart or "| |" in chart

    @patch("llm_council.bias_aggregation.read_bias_records")
    def test_generate_csv_report(self, mock_read):
        """CSV output contains header and data rows."""
        # Mock data
        mock_read.return_value = [
            BiasMetricRecord(
                session_id="sess-1",
                timestamp="2025-01-01T12:00:00Z",
                reviewer_id="gpt-4",
                model_id="claude-3",
                position=0,
                score_value=8.5,
                response_length_chars=100,
                query_metadata={"category": "coding", "token_bucket": "short"},
            )
        ]

        csv_output = generate_bias_report_csv()

        # Check header
        assert "session_id,timestamp,reviewer_id" in csv_output
        assert "query_category,token_bucket" in csv_output

        # Check data row
        assert "sess-1" in csv_output
        assert "gpt-4" in csv_output
        assert "8.5" in csv_output
        assert "coding" in csv_output
        assert "short" in csv_output

    @patch("llm_council.bias_aggregation.run_aggregated_bias_audit")
    def test_generate_text_report_with_charts(self, mock_audit):
        """Text report includes ASCII charts."""
        # Mock audit result
        mock_result = MagicMock()
        mock_result.sessions_analyzed = 10
        mock_result.total_reviews = 50
        mock_result.confidence_level.name = "MODERATE"

        # Mock LengthCorrelationReport object
        mock_lc = MagicMock()
        mock_lc.point_estimate = 0.1
        mock_lc.ci_lower = -0.1
        mock_lc.ci_upper = 0.3
        mock_result.length_correlation = mock_lc

        # Position bias with data for chart
        # The code expects position_bias object with position_means dict
        mock_pb = MagicMock()
        mock_pb.position_means = {1: 8.0, 2: 7.5, 3: 7.0}
        mock_result.position_bias = mock_pb

        # Reviewer profiles
        mock_result.reviewer_profiles = {}

        mock_audit.return_value = mock_result

        report = generate_bias_report_text()

        assert "LLM Council - Cross-Session Bias Audit" in report
        # Check for chart elements
        assert "Average Score per Position" in report
        assert "Pos 1" in report
