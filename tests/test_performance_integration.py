"""TDD tests for ADR-026 Phase 3: Council Integration.

Tests for metrics extraction, persistence helper, and singleton tracker.
Written BEFORE implementation per TDD workflow.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


class TestPersistSessionPerformanceData:
    """Test persist_session_performance_data() function."""

    def test_function_exists(self):
        """persist_session_performance_data should be importable."""
        from llm_council.performance import persist_session_performance_data

        assert callable(persist_session_performance_data)

    def test_creates_records_from_session_data(self):
        """Should create ModelSessionMetric records from session data."""
        from llm_council.performance import persist_session_performance_data
        from llm_council.performance.store import read_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            model_statuses = {
                "openai/gpt-4o": {"status": "ok", "latency_ms": 1500},
                "anthropic/claude": {"status": "ok", "latency_ms": 2000},
            }
            aggregate_rankings = {
                "openai/gpt-4o": {"borda_score": 0.75, "rank": 1},
                "anthropic/claude": {"borda_score": 0.65, "rank": 2},
            }
            stage2_results = [
                {"model": "openai/gpt-4o", "parsed_ranking": ["Response A", "Response B"]},
                {"model": "anthropic/claude", "parsed_ranking": ["Response B", "Response A"]},
            ]

            with patch("llm_council.performance.integration.PERFORMANCE_STORE_PATH", store_path):
                count = persist_session_performance_data(
                    session_id="test-session",
                    model_statuses=model_statuses,
                    aggregate_rankings=aggregate_rankings,
                    stage2_results=stage2_results,
                )

            assert count == 2
            records = read_performance_records(store_path)
            assert len(records) == 2

    def test_extracts_latency_from_model_statuses(self):
        """Should extract latency_ms from model_statuses."""
        from llm_council.performance import persist_session_performance_data
        from llm_council.performance.store import read_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            model_statuses = {
                "openai/gpt-4o": {"status": "ok", "latency_ms": 1234},
            }
            aggregate_rankings = {
                "openai/gpt-4o": {"borda_score": 0.5},
            }

            with patch("llm_council.performance.integration.PERFORMANCE_STORE_PATH", store_path):
                persist_session_performance_data(
                    session_id="s1",
                    model_statuses=model_statuses,
                    aggregate_rankings=aggregate_rankings,
                )

            records = read_performance_records(store_path)
            assert records[0].latency_ms == 1234

    def test_extracts_borda_score_from_aggregate_rankings(self):
        """Should extract borda_score from aggregate_rankings."""
        from llm_council.performance import persist_session_performance_data
        from llm_council.performance.store import read_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            model_statuses = {"model-a": {"status": "ok", "latency_ms": 1000}}
            aggregate_rankings = {"model-a": {"borda_score": 0.85}}

            with patch("llm_council.performance.integration.PERFORMANCE_STORE_PATH", store_path):
                persist_session_performance_data(
                    session_id="s1",
                    model_statuses=model_statuses,
                    aggregate_rankings=aggregate_rankings,
                )

            records = read_performance_records(store_path)
            assert records[0].borda_score == 0.85

    def test_handles_missing_model_in_rankings(self):
        """Should handle models that responded but weren't ranked."""
        from llm_council.performance import persist_session_performance_data
        from llm_council.performance.store import read_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            # Model in statuses but not in rankings
            model_statuses = {
                "model-a": {"status": "ok", "latency_ms": 1000},
                "model-b": {"status": "timeout", "latency_ms": 30000},  # Not ranked
            }
            aggregate_rankings = {
                "model-a": {"borda_score": 0.75},
                # model-b not in rankings
            }

            with patch("llm_council.performance.integration.PERFORMANCE_STORE_PATH", store_path):
                count = persist_session_performance_data(
                    session_id="s1",
                    model_statuses=model_statuses,
                    aggregate_rankings=aggregate_rankings,
                )

            # Should only record model-a (the one with rankings)
            assert count == 1
            records = read_performance_records(store_path)
            assert len(records) == 1
            assert records[0].model_id == "model-a"

    def test_respects_enabled_flag(self):
        """Should no-op when PERFORMANCE_TRACKING_ENABLED=false."""
        from llm_council.performance import persist_session_performance_data

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            with patch("llm_council.performance.integration.PERFORMANCE_TRACKING_ENABLED", False):
                count = persist_session_performance_data(
                    session_id="s1",
                    model_statuses={"m1": {"latency_ms": 1000}},
                    aggregate_rankings={"m1": {"borda_score": 0.5}},
                )

            assert count == 0
            assert not store_path.exists()

    def test_sets_session_id_on_records(self):
        """Should set session_id on all records."""
        from llm_council.performance import persist_session_performance_data
        from llm_council.performance.store import read_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            with patch("llm_council.performance.integration.PERFORMANCE_STORE_PATH", store_path):
                persist_session_performance_data(
                    session_id="unique-session-id",
                    model_statuses={"m1": {"latency_ms": 1000}},
                    aggregate_rankings={"m1": {"borda_score": 0.5}},
                )

            records = read_performance_records(store_path)
            assert records[0].session_id == "unique-session-id"

    def test_sets_timestamp_on_records(self):
        """Should set current timestamp on all records."""
        from llm_council.performance import persist_session_performance_data
        from llm_council.performance.store import read_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            with patch("llm_council.performance.integration.PERFORMANCE_STORE_PATH", store_path):
                persist_session_performance_data(
                    session_id="s1",
                    model_statuses={"m1": {"latency_ms": 1000}},
                    aggregate_rankings={"m1": {"borda_score": 0.5}},
                )

            records = read_performance_records(store_path)
            assert records[0].timestamp != ""
            # Should be a valid ISO timestamp
            datetime.fromisoformat(records[0].timestamp.replace("Z", "+00:00"))


class TestGetTracker:
    """Test get_tracker() singleton factory."""

    def test_get_tracker_exists(self):
        """get_tracker should be importable."""
        from llm_council.performance import get_tracker

        assert callable(get_tracker)

    def test_get_tracker_returns_tracker(self):
        """get_tracker() should return InternalPerformanceTracker."""
        from llm_council.performance import InternalPerformanceTracker, get_tracker

        with patch("llm_council.performance.integration.PERFORMANCE_TRACKING_ENABLED", True):
            tracker = get_tracker()
            assert isinstance(tracker, InternalPerformanceTracker)

    def test_get_tracker_returns_singleton(self):
        """get_tracker() should return same instance on multiple calls."""
        from llm_council.performance import get_tracker
        from llm_council.performance.integration import _reset_tracker_singleton

        _reset_tracker_singleton()  # Clear any cached instance

        with patch("llm_council.performance.integration.PERFORMANCE_TRACKING_ENABLED", True):
            tracker1 = get_tracker()
            tracker2 = get_tracker()
            assert tracker1 is tracker2

    def test_get_tracker_returns_none_when_disabled(self):
        """get_tracker() should return None when tracking disabled."""
        from llm_council.performance import get_tracker
        from llm_council.performance.integration import _reset_tracker_singleton

        _reset_tracker_singleton()

        with patch("llm_council.performance.integration.PERFORMANCE_TRACKING_ENABLED", False):
            tracker = get_tracker()
            assert tracker is None


class TestExtractParseSuccess:
    """Test parse success extraction from stage2 results."""

    def test_detects_successful_parse(self):
        """Should detect successful parse from stage2 results."""
        from llm_council.performance.integration import _extract_parse_success

        stage2_results = [
            {"model": "model-a", "parsed_ranking": ["A", "B", "C"]},
        ]

        success = _extract_parse_success("model-a", stage2_results)
        assert success is True

    def test_detects_abstained_as_failure(self):
        """Should detect abstained=True as parse failure."""
        from llm_council.performance.integration import _extract_parse_success

        stage2_results = [
            {"model": "model-a", "abstained": True, "parsed_ranking": []},
        ]

        success = _extract_parse_success("model-a", stage2_results)
        assert success is False

    def test_detects_empty_ranking_as_failure(self):
        """Should detect empty parsed_ranking as failure."""
        from llm_council.performance.integration import _extract_parse_success

        stage2_results = [
            {"model": "model-a", "parsed_ranking": []},
        ]

        success = _extract_parse_success("model-a", stage2_results)
        assert success is False

    def test_missing_model_defaults_to_true(self):
        """Should default to True for models not in stage2."""
        from llm_council.performance.integration import _extract_parse_success

        stage2_results = [
            {"model": "other-model", "parsed_ranking": ["A", "B"]},
        ]

        success = _extract_parse_success("missing-model", stage2_results)
        assert success is True


class TestModuleExports:
    """Test that integration functions are exported."""

    def test_exports_persist_function(self):
        """performance module should export persist_session_performance_data."""
        from llm_council.performance import persist_session_performance_data

        assert callable(persist_session_performance_data)

    def test_exports_get_tracker(self):
        """performance module should export get_tracker."""
        from llm_council.performance import get_tracker

        assert callable(get_tracker)
