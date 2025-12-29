"""TDD tests for ADR-026 Phase 3: Performance Metric Types and Storage.

Tests for ModelSessionMetric, ModelPerformanceIndex, and JSONL persistence.
Written BEFORE implementation per TDD workflow.
"""

import json
import tempfile
from dataclasses import is_dataclass
from pathlib import Path

import pytest


class TestModelSessionMetricDataclass:
    """Test ModelSessionMetric dataclass definition."""

    def test_dataclass_exists(self):
        """ModelSessionMetric should be a dataclass."""
        from llm_council.performance.types import ModelSessionMetric

        metric = ModelSessionMetric(
            session_id="test-session",
            model_id="openai/gpt-4o",
            timestamp="2025-12-24T00:00:00Z",
            latency_ms=1500,
            borda_score=0.75,
            parse_success=True,
        )
        assert is_dataclass(metric)

    def test_has_required_fields(self):
        """ModelSessionMetric should have all required fields."""
        from llm_council.performance.types import ModelSessionMetric

        metric = ModelSessionMetric(
            session_id="sess-123",
            model_id="anthropic/claude-3-opus",
            timestamp="2025-12-24T12:00:00Z",
            latency_ms=2000,
            borda_score=0.85,
            parse_success=True,
        )
        assert metric.session_id == "sess-123"
        assert metric.model_id == "anthropic/claude-3-opus"
        assert metric.timestamp == "2025-12-24T12:00:00Z"
        assert metric.latency_ms == 2000
        assert metric.borda_score == 0.85
        assert metric.parse_success is True

    def test_has_schema_version(self):
        """ModelSessionMetric should have schema_version field."""
        from llm_council.performance.types import ModelSessionMetric

        metric = ModelSessionMetric()
        assert hasattr(metric, "schema_version")
        assert metric.schema_version == "1.0.0"

    def test_optional_reasoning_tokens(self):
        """ModelSessionMetric should have optional reasoning_tokens_used."""
        from llm_council.performance.types import ModelSessionMetric

        # Without reasoning tokens
        metric1 = ModelSessionMetric()
        assert metric1.reasoning_tokens_used is None

        # With reasoning tokens
        metric2 = ModelSessionMetric(reasoning_tokens_used=5000)
        assert metric2.reasoning_tokens_used == 5000

    def test_defaults_for_empty_construction(self):
        """ModelSessionMetric should have sensible defaults."""
        from llm_council.performance.types import ModelSessionMetric

        metric = ModelSessionMetric()
        assert metric.session_id == ""
        assert metric.model_id == ""
        assert metric.timestamp == ""
        assert metric.latency_ms == 0
        assert metric.borda_score == 0.0
        assert metric.parse_success is True

    def test_borda_score_normalized_range(self):
        """Borda score should be normalized 0-1."""
        from llm_council.performance.types import ModelSessionMetric

        # Valid range
        metric = ModelSessionMetric(borda_score=0.5)
        assert 0.0 <= metric.borda_score <= 1.0


class TestModelSessionMetricSerialization:
    """Test ModelSessionMetric JSONL serialization."""

    def test_to_jsonl_line(self):
        """Should serialize to single JSONL line."""
        from llm_council.performance.types import ModelSessionMetric

        metric = ModelSessionMetric(
            session_id="sess-456",
            model_id="openai/gpt-4o",
            timestamp="2025-12-24T00:00:00Z",
            latency_ms=1500,
            borda_score=0.75,
            parse_success=True,
        )
        line = metric.to_jsonl_line()

        # Should be valid JSON
        parsed = json.loads(line)
        assert parsed["session_id"] == "sess-456"
        assert parsed["model_id"] == "openai/gpt-4o"
        assert parsed["borda_score"] == 0.75

    def test_from_jsonl_line(self):
        """Should deserialize from JSONL line."""
        from llm_council.performance.types import ModelSessionMetric

        line = json.dumps(
            {
                "schema_version": "1.0.0",
                "session_id": "sess-789",
                "model_id": "anthropic/claude-3-opus",
                "timestamp": "2025-12-24T00:00:00Z",
                "latency_ms": 2000,
                "borda_score": 0.85,
                "parse_success": True,
                "reasoning_tokens_used": None,
            }
        )

        metric = ModelSessionMetric.from_jsonl_line(line)
        assert metric.session_id == "sess-789"
        assert metric.model_id == "anthropic/claude-3-opus"
        assert metric.borda_score == 0.85

    def test_roundtrip_serialization(self):
        """JSONL roundtrip should preserve all fields."""
        from llm_council.performance.types import ModelSessionMetric

        original = ModelSessionMetric(
            schema_version="1.0.0",
            session_id="sess-roundtrip",
            model_id="google/gemini-2.0-flash",
            timestamp="2025-12-24T12:00:00Z",
            latency_ms=1200,
            borda_score=0.90,
            parse_success=False,
            reasoning_tokens_used=3000,
        )

        line = original.to_jsonl_line()
        restored = ModelSessionMetric.from_jsonl_line(line)

        assert restored.schema_version == original.schema_version
        assert restored.session_id == original.session_id
        assert restored.model_id == original.model_id
        assert restored.timestamp == original.timestamp
        assert restored.latency_ms == original.latency_ms
        assert restored.borda_score == original.borda_score
        assert restored.parse_success == original.parse_success
        assert restored.reasoning_tokens_used == original.reasoning_tokens_used

    def test_schema_version_in_output(self):
        """Schema version should be present in serialized output."""
        from llm_council.performance.types import ModelSessionMetric

        metric = ModelSessionMetric()
        line = metric.to_jsonl_line()
        parsed = json.loads(line)

        assert "schema_version" in parsed
        assert parsed["schema_version"] == "1.0.0"

    def test_handles_missing_fields_from_older_schema(self):
        """Should handle missing fields from older schema versions."""
        from llm_council.performance.types import ModelSessionMetric

        # Simulate older schema without reasoning_tokens_used
        line = json.dumps(
            {
                "schema_version": "0.9.0",
                "session_id": "old-session",
                "model_id": "openai/gpt-4",
                "timestamp": "2025-01-01T00:00:00Z",
                "latency_ms": 1000,
                "borda_score": 0.5,
                "parse_success": True,
                # Missing: reasoning_tokens_used
            }
        )

        metric = ModelSessionMetric.from_jsonl_line(line)
        assert metric.session_id == "old-session"
        assert metric.reasoning_tokens_used is None  # Default for missing


class TestModelPerformanceIndexDataclass:
    """Test ModelPerformanceIndex dataclass definition."""

    def test_dataclass_exists(self):
        """ModelPerformanceIndex should be a dataclass."""
        from llm_council.performance.types import ModelPerformanceIndex

        index = ModelPerformanceIndex(
            model_id="openai/gpt-4o",
            sample_size=50,
            mean_borda_score=0.75,
            p50_latency_ms=1500,
            p95_latency_ms=3000,
            parse_success_rate=0.95,
            confidence_level="MODERATE",
        )
        assert is_dataclass(index)

    def test_has_required_fields(self):
        """ModelPerformanceIndex should have all required fields."""
        from llm_council.performance.types import ModelPerformanceIndex

        index = ModelPerformanceIndex(
            model_id="anthropic/claude-3-opus",
            sample_size=100,
            mean_borda_score=0.80,
            p50_latency_ms=2000,
            p95_latency_ms=4000,
            parse_success_rate=0.98,
            confidence_level="HIGH",
        )

        assert index.model_id == "anthropic/claude-3-opus"
        assert index.sample_size == 100
        assert index.mean_borda_score == 0.80
        assert index.p50_latency_ms == 2000
        assert index.p95_latency_ms == 4000
        assert index.parse_success_rate == 0.98
        assert index.confidence_level == "HIGH"

    def test_confidence_levels(self):
        """Confidence level should be one of the defined values."""
        from llm_council.performance.types import ModelPerformanceIndex

        for level in ["INSUFFICIENT", "PRELIMINARY", "MODERATE", "HIGH"]:
            index = ModelPerformanceIndex(
                model_id="test-model",
                sample_size=10,
                mean_borda_score=0.5,
                p50_latency_ms=1000,
                p95_latency_ms=2000,
                parse_success_rate=0.9,
                confidence_level=level,
            )
            assert index.confidence_level == level


class TestAppendPerformanceRecords:
    """Test JSONL append operations."""

    def test_append_creates_file_if_missing(self):
        """Should create file if it doesn't exist."""
        from llm_council.performance.store import append_performance_records
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "new_file.jsonl"
            assert not path.exists()

            records = [ModelSessionMetric(session_id="s1", model_id="m1")]
            count = append_performance_records(records, path)

            assert path.exists()
            assert count == 1

    def test_append_creates_directory_if_missing(self):
        """Should create parent directory if it doesn't exist."""
        from llm_council.performance.store import append_performance_records
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "metrics.jsonl"
            assert not path.parent.exists()

            records = [ModelSessionMetric(session_id="s1", model_id="m1")]
            append_performance_records(records, path)

            assert path.parent.exists()
            assert path.exists()

    def test_append_adds_lines(self):
        """Should append multiple records as JSONL lines."""
        from llm_council.performance.store import append_performance_records
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            records = [
                ModelSessionMetric(session_id="s1", model_id="m1", borda_score=0.5),
                ModelSessionMetric(session_id="s1", model_id="m2", borda_score=0.7),
            ]
            append_performance_records(records, path)

            lines = path.read_text().strip().split("\n")
            assert len(lines) == 2

    def test_append_preserves_existing_data(self):
        """Should preserve existing records when appending."""
        from llm_council.performance.store import append_performance_records
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            # First append
            records1 = [ModelSessionMetric(session_id="s1", model_id="m1")]
            append_performance_records(records1, path)

            # Second append
            records2 = [ModelSessionMetric(session_id="s2", model_id="m2")]
            append_performance_records(records2, path)

            lines = path.read_text().strip().split("\n")
            assert len(lines) == 2

            # Verify first record preserved
            first = json.loads(lines[0])
            assert first["session_id"] == "s1"

    def test_returns_count_of_records_written(self):
        """Should return count of records written."""
        from llm_council.performance.store import append_performance_records
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            records = [ModelSessionMetric(session_id=f"s{i}", model_id=f"m{i}") for i in range(5)]
            count = append_performance_records(records, path)

            assert count == 5

    def test_handles_empty_record_list(self):
        """Should handle empty list gracefully."""
        from llm_council.performance.store import append_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            count = append_performance_records([], path)

            assert count == 0
            # File may or may not be created for empty list


class TestReadPerformanceRecords:
    """Test JSONL read operations."""

    def test_read_all_records(self):
        """Should read all records from file."""
        from llm_council.performance.store import (
            append_performance_records,
            read_performance_records,
        )
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            records = [
                ModelSessionMetric(session_id="s1", model_id="m1"),
                ModelSessionMetric(session_id="s2", model_id="m2"),
                ModelSessionMetric(session_id="s3", model_id="m3"),
            ]
            append_performance_records(records, path)

            result = read_performance_records(path)
            assert len(result) == 3

    def test_filter_by_model_id(self):
        """Should filter records by model_id."""
        from llm_council.performance.store import (
            append_performance_records,
            read_performance_records,
        )
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            records = [
                ModelSessionMetric(session_id="s1", model_id="openai/gpt-4o"),
                ModelSessionMetric(session_id="s2", model_id="anthropic/claude"),
                ModelSessionMetric(session_id="s3", model_id="openai/gpt-4o"),
            ]
            append_performance_records(records, path)

            result = read_performance_records(path, model_id="openai/gpt-4o")
            assert len(result) == 2
            assert all(r.model_id == "openai/gpt-4o" for r in result)

    def test_filter_by_max_days(self):
        """Should filter records by max_days from now."""
        from datetime import datetime, timedelta, timezone

        from llm_council.performance.store import (
            append_performance_records,
            read_performance_records,
        )
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            now = datetime.now(timezone.utc)
            old_date = (now - timedelta(days=60)).isoformat()
            recent_date = (now - timedelta(days=5)).isoformat()

            records = [
                ModelSessionMetric(session_id="old", model_id="m1", timestamp=old_date),
                ModelSessionMetric(session_id="recent", model_id="m2", timestamp=recent_date),
            ]
            append_performance_records(records, path)

            # Only recent records (within 30 days)
            result = read_performance_records(path, max_days=30)
            assert len(result) == 1
            assert result[0].session_id == "recent"

    def test_returns_chronological_order(self):
        """Should return records in chronological order."""
        from llm_council.performance.store import (
            append_performance_records,
            read_performance_records,
        )
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            records = [
                ModelSessionMetric(session_id="s1", timestamp="2025-12-01T00:00:00Z"),
                ModelSessionMetric(session_id="s2", timestamp="2025-12-15T00:00:00Z"),
                ModelSessionMetric(session_id="s3", timestamp="2025-12-10T00:00:00Z"),
            ]
            append_performance_records(records, path)

            result = read_performance_records(path)
            # Should be sorted by timestamp
            assert result[0].session_id == "s1"
            assert result[1].session_id == "s3"
            assert result[2].session_id == "s2"

    def test_handles_missing_file(self):
        """Should return empty list for missing file."""
        from llm_council.performance.store import read_performance_records

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.jsonl"

            result = read_performance_records(path)
            assert result == []

    def test_handles_malformed_lines(self):
        """Should skip malformed lines gracefully."""
        from llm_council.performance.store import read_performance_records
        from llm_council.performance.types import ModelSessionMetric

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"

            # Write some valid and some invalid lines
            valid = ModelSessionMetric(session_id="valid").to_jsonl_line()
            path.write_text(f"{valid}\n{{invalid json\n{valid}\n")

            result = read_performance_records(path)
            # Should have 2 valid records, skipped the malformed one
            assert len(result) == 2


class TestPerformanceModuleExports:
    """Test that types are exported from performance module."""

    def test_exports_model_session_metric(self):
        """performance module should export ModelSessionMetric."""
        from llm_council.performance import ModelSessionMetric

        assert ModelSessionMetric is not None

    def test_exports_model_performance_index(self):
        """performance module should export ModelPerformanceIndex."""
        from llm_council.performance import ModelPerformanceIndex

        assert ModelPerformanceIndex is not None

    def test_exports_append_function(self):
        """performance module should export append_performance_records."""
        from llm_council.performance import append_performance_records

        assert callable(append_performance_records)

    def test_exports_read_function(self):
        """performance module should export read_performance_records."""
        from llm_council.performance import read_performance_records

        assert callable(read_performance_records)
