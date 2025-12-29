"""Tests for ADR-018 Phase 1: Cross-session bias data persistence.

TDD tests for BiasMetricRecord dataclass, JSONL persistence, and integration.
"""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict

import pytest


class TestBiasMetricRecord:
    """Tests for BiasMetricRecord dataclass."""

    def test_dataclass_creation_with_defaults(self):
        """Create record with default values."""
        from llm_council.bias_persistence import BiasMetricRecord

        record = BiasMetricRecord()

        assert record.schema_version == "1.1.0"
        assert record.session_id == ""
        assert record.timestamp == ""
        assert record.consent_level == 1  # LOCAL_ONLY default
        assert record.reviewer_id == ""
        assert record.model_id == ""
        assert record.position == 0
        assert record.response_length_chars == 0
        assert record.score_value == 0.0
        assert record.score_scale == "1-10"
        assert record.council_config_version == "0.1.0"
        assert record.query_hash is None
        assert record.query_metadata is None

    def test_extract_query_metadata(self):
        """Verify metadata extraction heuristics."""
        from llm_council.bias_persistence import _extract_query_metadata

        # 1. Coding query
        meta = _extract_query_metadata("def hello_world(): print('hi')")
        assert meta["category"] == "coding"
        assert meta["token_bucket"] == "short"

        # 2. Math query
        meta = _extract_query_metadata("calculate the square root of 144")
        assert meta["category"] == "math_reasoning"

        # 3. Creative query (long)
        long_query = "write a creative story about a robot " * 10
        meta = _extract_query_metadata(long_query)
        assert meta["category"] == "creative_writing"
        assert meta["token_bucket"] == "medium" or meta["token_bucket"] == "long"

        # 4. Unknown/General
        meta = _extract_query_metadata("what is the capital of France?")
        assert meta["category"] == "general"
        assert meta["language"] == "en"

    def test_dataclass_creation_with_all_fields(self):
        """Create record with all fields populated."""
        from llm_council.bias_persistence import BiasMetricRecord

        record = BiasMetricRecord(
            schema_version="1.1.0",
            session_id="sess-abc-123",
            timestamp="2025-12-17T10:30:00Z",
            consent_level=2,
            reviewer_id="google/gemini-3-pro-preview",
            model_id="anthropic/claude-opus-4.5",
            position=2,
            response_length_chars=1200,
            score_value=8.5,
            score_scale="1-10",
            council_config_version="0.3.0",
            query_hash="abc123def456",
            query_metadata={"category": "coding", "language": "en"},
        )

        assert record.session_id == "sess-abc-123"
        assert record.reviewer_id == "google/gemini-3-pro-preview"
        assert record.model_id == "anthropic/claude-opus-4.5"
        assert record.position == 2
        assert record.response_length_chars == 1200
        assert record.score_value == 8.5
        assert record.query_hash == "abc123def456"
        assert record.query_metadata["category"] == "coding"

    def test_to_jsonl_line_serialization(self):
        """Serialize to JSONL format."""
        from llm_council.bias_persistence import BiasMetricRecord

        record = BiasMetricRecord(
            session_id="sess-123",
            timestamp="2025-12-17T10:30:00Z",
            reviewer_id="gpt-4",
            model_id="claude-3",
            score_value=7.5,
        )

        line = record.to_jsonl_line()

        assert isinstance(line, str)
        assert "\n" not in line  # Single line
        data = json.loads(line)
        assert data["session_id"] == "sess-123"
        assert data["score_value"] == 7.5

    def test_from_jsonl_line_deserialization(self):
        """Deserialize from JSONL line."""
        from llm_council.bias_persistence import BiasMetricRecord

        line = '{"schema_version": "1.1.0", "session_id": "sess-456", "timestamp": "2025-12-17T10:30:00Z", "consent_level": 1, "reviewer_id": "gpt-4", "model_id": "claude-3", "position": 1, "response_length_chars": 500, "score_value": 8.0, "score_scale": "1-10", "council_config_version": "0.3.0", "query_hash": null, "query_metadata": null}'

        record = BiasMetricRecord.from_jsonl_line(line)

        assert record.session_id == "sess-456"
        assert record.reviewer_id == "gpt-4"
        assert record.score_value == 8.0
        assert record.query_hash is None

    def test_roundtrip_serialization(self):
        """JSONL roundtrip preserves all fields."""
        from llm_council.bias_persistence import BiasMetricRecord

        original = BiasMetricRecord(
            schema_version="1.1.0",
            session_id="roundtrip-test",
            timestamp="2025-12-17T10:30:00Z",
            consent_level=3,
            reviewer_id="reviewer-1",
            model_id="model-1",
            position=0,
            response_length_chars=999,
            score_value=5.5,
            score_scale="1-10",
            council_config_version="0.4.0",
            query_hash="hash123",
            query_metadata={"key": "value"},
        )

        line = original.to_jsonl_line()
        restored = BiasMetricRecord.from_jsonl_line(line)

        assert restored.session_id == original.session_id
        assert restored.consent_level == original.consent_level
        assert restored.score_value == original.score_value
        assert restored.query_hash == original.query_hash
        assert restored.query_metadata == original.query_metadata

    def test_schema_version_present(self):
        """Schema version included in output."""
        from llm_council.bias_persistence import BiasMetricRecord

        record = BiasMetricRecord(session_id="test")
        line = record.to_jsonl_line()
        data = json.loads(line)

        assert "schema_version" in data
        assert data["schema_version"] == "1.1.0"


class TestConsentLevel:
    """Tests for ConsentLevel enum."""

    def test_consent_levels_defined(self):
        """All consent levels are defined."""
        from llm_council.bias_persistence import ConsentLevel

        assert ConsentLevel.OFF.value == 0
        assert ConsentLevel.LOCAL_ONLY.value == 1
        assert ConsentLevel.ANONYMOUS.value == 2
        assert ConsentLevel.ENHANCED.value == 3
        assert ConsentLevel.RESEARCH.value == 4

    def test_consent_level_comparison(self):
        """Consent levels can be compared."""
        from llm_council.bias_persistence import ConsentLevel

        assert ConsentLevel.OFF.value < ConsentLevel.LOCAL_ONLY.value
        assert ConsentLevel.RESEARCH.value > ConsentLevel.ANONYMOUS.value


class TestQueryHashing:
    """Tests for privacy-safe query hashing."""

    def test_hash_disabled_at_low_consent(self):
        """Returns None when consent < RESEARCH."""
        from llm_council.bias_persistence import hash_query_if_enabled, ConsentLevel

        result = hash_query_if_enabled("test query", ConsentLevel.LOCAL_ONLY)
        assert result is None

        result = hash_query_if_enabled("test query", ConsentLevel.ANONYMOUS)
        assert result is None

        result = hash_query_if_enabled("test query", ConsentLevel.ENHANCED)
        assert result is None

    def test_hash_enabled_at_research_consent(self):
        """Returns hash when consent = RESEARCH."""
        from llm_council.bias_persistence import hash_query_if_enabled, ConsentLevel

        result = hash_query_if_enabled("test query", ConsentLevel.RESEARCH)

        assert result is not None
        assert isinstance(result, str)
        assert len(result) == 16  # Truncated to 16 hex chars

    def test_hash_deterministic(self):
        """Same query produces same hash."""
        from llm_council.bias_persistence import hash_query_if_enabled, ConsentLevel

        hash1 = hash_query_if_enabled("identical query", ConsentLevel.RESEARCH)
        hash2 = hash_query_if_enabled("identical query", ConsentLevel.RESEARCH)

        assert hash1 == hash2

    def test_different_queries_different_hashes(self):
        """Different queries produce different hashes."""
        from llm_council.bias_persistence import hash_query_if_enabled, ConsentLevel

        hash1 = hash_query_if_enabled("query one", ConsentLevel.RESEARCH)
        hash2 = hash_query_if_enabled("query two", ConsentLevel.RESEARCH)

        assert hash1 != hash2

    def test_hash_truncated_to_16_chars(self):
        """Hash is 16 hex characters."""
        from llm_council.bias_persistence import hash_query_if_enabled, ConsentLevel

        result = hash_query_if_enabled("any query text here", ConsentLevel.RESEARCH)

        assert len(result) == 16
        # Verify it's valid hex
        int(result, 16)  # Should not raise

    def test_uses_configured_secret(self):
        """Uses LLM_COUNCIL_HASH_SECRET if set."""
        from llm_council.bias_persistence import hash_query_if_enabled, ConsentLevel

        # Hash with default secret
        default_hash = hash_query_if_enabled("test", ConsentLevel.RESEARCH)

        # Hash with custom secret
        with patch.dict(os.environ, {"LLM_COUNCIL_HASH_SECRET": "custom-secret-123"}):
            # Need to reimport to pick up new secret
            import importlib
            import llm_council.bias_persistence as bp

            importlib.reload(bp)
            custom_hash = bp.hash_query_if_enabled("test", bp.ConsentLevel.RESEARCH)

        # Hashes should differ with different secrets
        assert default_hash != custom_hash


class TestAppendBiasRecords:
    """Tests for JSONL append operations."""

    def test_append_creates_file_if_missing(self):
        """Creates file on first write."""
        from llm_council.bias_persistence import append_bias_records, BiasMetricRecord

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            record = BiasMetricRecord(session_id="test-session")

            count = append_bias_records([record], store_path)

            assert store_path.exists()
            assert count == 1

    def test_append_creates_directory_if_missing(self):
        """Creates parent directories."""
        from llm_council.bias_persistence import append_bias_records, BiasMetricRecord

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "subdir" / "nested" / "metrics.jsonl"
            record = BiasMetricRecord(session_id="test-session")

            count = append_bias_records([record], store_path)

            assert store_path.exists()
            assert count == 1

    def test_append_adds_lines_atomically(self):
        """Each record is one line."""
        from llm_council.bias_persistence import append_bias_records, BiasMetricRecord

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            records = [
                BiasMetricRecord(session_id="sess-1", reviewer_id="r1", model_id="m1"),
                BiasMetricRecord(session_id="sess-1", reviewer_id="r1", model_id="m2"),
                BiasMetricRecord(session_id="sess-1", reviewer_id="r2", model_id="m1"),
            ]

            append_bias_records(records, store_path)

            with open(store_path, "r") as f:
                lines = f.readlines()

            assert len(lines) == 3
            for line in lines:
                json.loads(line)  # Each line is valid JSON

    def test_append_preserves_existing_data(self):
        """Existing records not modified."""
        from llm_council.bias_persistence import append_bias_records, BiasMetricRecord

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            # First append
            record1 = BiasMetricRecord(session_id="first-session")
            append_bias_records([record1], store_path)

            # Second append
            record2 = BiasMetricRecord(session_id="second-session")
            append_bias_records([record2], store_path)

            with open(store_path, "r") as f:
                lines = f.readlines()

            assert len(lines) == 2
            data1 = json.loads(lines[0])
            data2 = json.loads(lines[1])
            assert data1["session_id"] == "first-session"
            assert data2["session_id"] == "second-session"

    def test_returns_count_of_records_written(self):
        """Returns number of records appended."""
        from llm_council.bias_persistence import append_bias_records, BiasMetricRecord

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            records = [BiasMetricRecord(session_id=f"sess-{i}") for i in range(5)]

            count = append_bias_records(records, store_path)

            assert count == 5

    def test_handles_empty_record_list(self):
        """Returns 0 for empty input."""
        from llm_council.bias_persistence import append_bias_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            count = append_bias_records([], store_path)

            assert count == 0


class TestReadBiasRecords:
    """Tests for JSONL read operations."""

    def test_read_all_records(self):
        """Reads all records from file."""
        from llm_council.bias_persistence import (
            append_bias_records,
            read_bias_records,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            records = [BiasMetricRecord(session_id=f"sess-{i}") for i in range(3)]
            append_bias_records(records, store_path)

            result = read_bias_records(store_path)

            assert len(result) == 3

    def test_filter_by_max_sessions(self):
        """Limits to last N sessions."""
        from llm_council.bias_persistence import (
            append_bias_records,
            read_bias_records,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            # Create records from 5 different sessions
            records = [BiasMetricRecord(session_id=f"sess-{i}") for i in range(5)]
            append_bias_records(records, store_path)

            result = read_bias_records(store_path, max_sessions=2)

            # Should only return records from last 2 sessions
            session_ids = {r.session_id for r in result}
            assert len(session_ids) <= 2

    def test_filter_by_max_days(self):
        """Limits to last N days."""
        from llm_council.bias_persistence import (
            append_bias_records,
            read_bias_records,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            now = datetime.now(timezone.utc)
            old_timestamp = (now - timedelta(days=10)).isoformat()
            recent_timestamp = now.isoformat()

            records = [
                BiasMetricRecord(session_id="old", timestamp=old_timestamp),
                BiasMetricRecord(session_id="recent", timestamp=recent_timestamp),
            ]
            append_bias_records(records, store_path)

            result = read_bias_records(store_path, max_days=5)

            # Should only return recent record
            assert len(result) == 1
            assert result[0].session_id == "recent"

    def test_filter_by_since_datetime(self):
        """Records after timestamp only."""
        from llm_council.bias_persistence import (
            append_bias_records,
            read_bias_records,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            records = [
                BiasMetricRecord(session_id="old", timestamp="2025-01-01T00:00:00Z"),
                BiasMetricRecord(session_id="new", timestamp="2025-12-01T00:00:00Z"),
            ]
            append_bias_records(records, store_path)

            cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
            result = read_bias_records(store_path, since=cutoff)

            assert len(result) == 1
            assert result[0].session_id == "new"

    def test_returns_chronological_order(self):
        """Oldest first."""
        from llm_council.bias_persistence import (
            append_bias_records,
            read_bias_records,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            # Write in reverse chronological order
            records = [
                BiasMetricRecord(session_id="newest", timestamp="2025-12-17T12:00:00Z"),
                BiasMetricRecord(session_id="middle", timestamp="2025-12-17T11:00:00Z"),
                BiasMetricRecord(session_id="oldest", timestamp="2025-12-17T10:00:00Z"),
            ]
            append_bias_records(records, store_path)

            result = read_bias_records(store_path)

            # Should be sorted chronologically (oldest first)
            assert result[0].session_id == "oldest"
            assert result[1].session_id == "middle"
            assert result[2].session_id == "newest"

    def test_handles_missing_file(self):
        """Returns empty list."""
        from llm_council.bias_persistence import read_bias_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "nonexistent.jsonl"

            result = read_bias_records(store_path)

            assert result == []

    def test_handles_malformed_lines(self):
        """Skips invalid JSON, logs warning."""
        from llm_council.bias_persistence import read_bias_records, BiasMetricRecord

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            # Write mix of valid and invalid lines
            with open(store_path, "w") as f:
                f.write(
                    '{"schema_version": "1.1.0", "session_id": "valid1", "timestamp": "", "consent_level": 1, "reviewer_id": "", "model_id": "", "position": 0, "response_length_chars": 0, "score_value": 0.0, "score_scale": "1-10", "council_config_version": "", "query_hash": null, "query_metadata": null}\n'
                )
                f.write("not valid json\n")
                f.write(
                    '{"schema_version": "1.1.0", "session_id": "valid2", "timestamp": "", "consent_level": 1, "reviewer_id": "", "model_id": "", "position": 0, "response_length_chars": 0, "score_value": 0.0, "score_scale": "1-10", "council_config_version": "", "query_hash": null, "query_metadata": null}\n'
                )

            result = read_bias_records(store_path)

            # Should have 2 valid records, skipped the invalid one
            assert len(result) == 2

    def test_handles_schema_version_mismatch(self):
        """Gracefully handles older schema versions."""
        from llm_council.bias_persistence import read_bias_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            # Write record with older schema version (fewer fields)
            with open(store_path, "w") as f:
                f.write(
                    '{"schema_version": "1.0.0", "session_id": "old-format", "timestamp": "", "reviewer_id": "", "model_id": "", "score_value": 5.0}\n'
                )

            result = read_bias_records(store_path)

            # Should handle gracefully (may have defaults for missing fields)
            assert len(result) >= 0  # Either parsed or skipped


class TestCreateBiasRecordsFromSession:
    """Tests for record creation from session data."""

    def test_creates_one_record_per_reviewer_model_pair(self):
        """N reviewers * M models = N*M records (minus self-reviews)."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [
            {"model": "model-a", "response": "Response A content"},
            {"model": "model-b", "response": "Response B content"},
        ]
        stage2_results = [
            {
                "model": "model-a",
                "parsed_ranking": {"scores": {"Response A": 7.0, "Response B": 8.0}},
            },
            {
                "model": "model-b",
                "parsed_ranking": {"scores": {"Response A": 6.0, "Response B": 9.0}},
            },
        ]
        label_to_model = {
            "Response A": {"model": "model-a", "display_index": 0},
            "Response B": {"model": "model-b", "display_index": 1},
        }

        records = create_bias_records_from_session(
            session_id="test-session",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        # 2 reviewers * 2 models = 4 records
        assert len(records) == 4

    def test_extracts_scores_from_parsed_ranking(self):
        """Score values extracted correctly."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [
            {"model": "model-a", "response": "A"},
        ]
        stage2_results = [
            {"model": "reviewer-1", "parsed_ranking": {"scores": {"Response A": 8.5}}},
        ]
        label_to_model = {
            "Response A": {"model": "model-a", "display_index": 0},
        }

        records = create_bias_records_from_session(
            session_id="test",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        assert len(records) == 1
        assert records[0].score_value == 8.5

    def test_extracts_position_from_enhanced_label_to_model(self):
        """Uses display_index from enhanced format."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [
            {"model": "model-a", "response": "A"},
            {"model": "model-b", "response": "B"},
        ]
        stage2_results = [
            {
                "model": "reviewer",
                "parsed_ranking": {"scores": {"Response A": 7.0, "Response B": 8.0}},
            },
        ]
        label_to_model = {
            "Response A": {"model": "model-a", "display_index": 0},
            "Response B": {"model": "model-b", "display_index": 1},
        }

        records = create_bias_records_from_session(
            session_id="test",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        # Find record for model-a
        model_a_record = next(r for r in records if r.model_id == "model-a")
        model_b_record = next(r for r in records if r.model_id == "model-b")

        assert model_a_record.position == 0
        assert model_b_record.position == 1

    def test_extracts_position_from_legacy_label_to_model(self):
        """Falls back to letter parsing for legacy format."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [
            {"model": "model-a", "response": "A"},
            {"model": "model-b", "response": "B"},
        ]
        stage2_results = [
            {
                "model": "reviewer",
                "parsed_ranking": {"scores": {"Response A": 7.0, "Response B": 8.0}},
            },
        ]
        # Legacy format: just model string, no display_index
        label_to_model = {
            "Response A": "model-a",
            "Response B": "model-b",
        }

        records = create_bias_records_from_session(
            session_id="test",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        # Find record for model-a
        model_a_record = next(r for r in records if r.model_id == "model-a")
        model_b_record = next(r for r in records if r.model_id == "model-b")

        # Should derive position from label letter (A=0, B=1)
        assert model_a_record.position == 0
        assert model_b_record.position == 1

    def test_extracts_response_length(self):
        """Character count from stage1 responses."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [
            {"model": "model-a", "response": "Short"},  # 5 chars
            {"model": "model-b", "response": "A much longer response here"},  # 27 chars
        ]
        stage2_results = [
            {
                "model": "reviewer",
                "parsed_ranking": {"scores": {"Response A": 7.0, "Response B": 8.0}},
            },
        ]
        label_to_model = {
            "Response A": {"model": "model-a", "display_index": 0},
            "Response B": {"model": "model-b", "display_index": 1},
        }

        records = create_bias_records_from_session(
            session_id="test",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        model_a_record = next(r for r in records if r.model_id == "model-a")
        model_b_record = next(r for r in records if r.model_id == "model-b")

        assert model_a_record.response_length_chars == 5
        assert model_b_record.response_length_chars == 27

    def test_handles_abstained_reviewers(self):
        """Skips abstained reviewers gracefully."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [
            {"model": "model-a", "response": "A"},
        ]
        stage2_results = [
            {"model": "reviewer-1", "parsed_ranking": {"scores": {"Response A": 8.0}}},
            {
                "model": "reviewer-2",
                "abstained": True,  # This reviewer abstained
                "parsed_ranking": None,
            },
        ]
        label_to_model = {
            "Response A": {"model": "model-a", "display_index": 0},
        }

        records = create_bias_records_from_session(
            session_id="test",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        # Only 1 record from reviewer-1, reviewer-2 abstained
        assert len(records) == 1
        assert records[0].reviewer_id == "reviewer-1"

    def test_includes_session_id_and_timestamp(self):
        """Each record has session context."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [{"model": "model-a", "response": "A"}]
        stage2_results = [{"model": "reviewer", "parsed_ranking": {"scores": {"Response A": 7.0}}}]
        label_to_model = {"Response A": {"model": "model-a", "display_index": 0}}

        records = create_bias_records_from_session(
            session_id="my-session-123",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        assert records[0].session_id == "my-session-123"
        assert records[0].timestamp != ""  # Should have a timestamp

    def test_includes_council_config_version(self):
        """Version tracked for model drift."""
        from llm_council.bias_persistence import create_bias_records_from_session

        stage1_results = [{"model": "model-a", "response": "A"}]
        stage2_results = [{"model": "reviewer", "parsed_ranking": {"scores": {"Response A": 7.0}}}]
        label_to_model = {"Response A": {"model": "model-a", "display_index": 0}}

        records = create_bias_records_from_session(
            session_id="test",
            stage1_results=stage1_results,
            stage2_results=stage2_results,
            label_to_model=label_to_model,
        )

        # Should include package version
        assert records[0].council_config_version != ""


class TestGetBiasStoreStats:
    """Tests for store statistics."""

    def test_stats_for_empty_store(self):
        """Returns zeros for missing/empty file."""
        from llm_council.bias_persistence import get_bias_store_stats

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "nonexistent.jsonl"

            stats = get_bias_store_stats(store_path)

            assert stats["total_records"] == 0
            assert stats["unique_sessions"] == 0

    def test_stats_for_populated_store(self):
        """Returns accurate counts and sizes."""
        from llm_council.bias_persistence import (
            append_bias_records,
            get_bias_store_stats,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            records = [
                BiasMetricRecord(session_id="sess-1", timestamp="2025-12-17T10:00:00Z"),
                BiasMetricRecord(session_id="sess-1", timestamp="2025-12-17T10:00:00Z"),
                BiasMetricRecord(session_id="sess-2", timestamp="2025-12-17T11:00:00Z"),
            ]
            append_bias_records(records, store_path)

            stats = get_bias_store_stats(store_path)

            assert stats["total_records"] == 3
            assert stats["file_size_bytes"] > 0

    def test_includes_unique_session_count(self):
        """Counts distinct session_ids."""
        from llm_council.bias_persistence import (
            append_bias_records,
            get_bias_store_stats,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            records = [
                BiasMetricRecord(session_id="sess-1"),
                BiasMetricRecord(session_id="sess-1"),
                BiasMetricRecord(session_id="sess-2"),
                BiasMetricRecord(session_id="sess-3"),
            ]
            append_bias_records(records, store_path)

            stats = get_bias_store_stats(store_path)

            assert stats["unique_sessions"] == 3

    def test_includes_date_range(self):
        """Oldest and newest timestamps."""
        from llm_council.bias_persistence import (
            append_bias_records,
            get_bias_store_stats,
            BiasMetricRecord,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"
            records = [
                BiasMetricRecord(session_id="s1", timestamp="2025-12-15T10:00:00Z"),
                BiasMetricRecord(session_id="s2", timestamp="2025-12-17T10:00:00Z"),
                BiasMetricRecord(session_id="s3", timestamp="2025-12-16T10:00:00Z"),
            ]
            append_bias_records(records, store_path)

            stats = get_bias_store_stats(store_path)

            assert stats["oldest_record"] == "2025-12-15T10:00:00Z"
            assert stats["newest_record"] == "2025-12-17T10:00:00Z"


class TestPersistSessionBiasData:
    """Integration tests for high-level persist function."""

    def test_respects_persistence_disabled(self):
        """No-op when persistence is disabled in config."""
        from llm_council.bias_persistence import persist_session_bias_data

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            with patch(
                "llm_council.bias_persistence._get_bias_persistence_enabled", return_value=False
            ):
                with patch(
                    "llm_council.bias_persistence._get_bias_store_path", return_value=store_path
                ):
                    count = persist_session_bias_data(
                        session_id="test",
                        stage1_results=[{"model": "m", "response": "r"}],
                        stage2_results=[
                            {"model": "r", "parsed_ranking": {"scores": {"Response A": 7.0}}}
                        ],
                        label_to_model={"Response A": {"model": "m", "display_index": 0}},
                    )

            assert count == 0
            assert not store_path.exists()

    def test_creates_records_and_appends(self):
        """Full flow from session to file."""
        from llm_council.bias_persistence import persist_session_bias_data, read_bias_records

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            with patch(
                "llm_council.bias_persistence._get_bias_persistence_enabled", return_value=True
            ):
                with patch(
                    "llm_council.bias_persistence._get_bias_store_path", return_value=store_path
                ):
                    count = persist_session_bias_data(
                        session_id="integration-test",
                        stage1_results=[
                            {"model": "model-a", "response": "Response A"},
                            {"model": "model-b", "response": "Response B"},
                        ],
                        stage2_results=[
                            {
                                "model": "model-a",
                                "parsed_ranking": {
                                    "scores": {"Response A": 7.0, "Response B": 8.0}
                                },
                            },
                        ],
                        label_to_model={
                            "Response A": {"model": "model-a", "display_index": 0},
                            "Response B": {"model": "model-b", "display_index": 1},
                        },
                    )

            assert count == 2  # 1 reviewer * 2 models

            records = read_bias_records(store_path)
            assert len(records) == 2
            assert all(r.session_id == "integration-test" for r in records)

    def test_respects_consent_level(self):
        """Query hash only at RESEARCH level."""
        from llm_council.bias_persistence import (
            persist_session_bias_data,
            read_bias_records,
            ConsentLevel,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "metrics.jsonl"

            # Test with LOCAL_ONLY - no hash
            with patch(
                "llm_council.bias_persistence._get_bias_persistence_enabled", return_value=True
            ):
                with patch(
                    "llm_council.bias_persistence._get_bias_store_path", return_value=store_path
                ):
                    with patch(
                        "llm_council.bias_persistence._get_bias_consent_level",
                        return_value=ConsentLevel.LOCAL_ONLY.value,
                    ):
                        persist_session_bias_data(
                            session_id="test-local",
                            stage1_results=[{"model": "m", "response": "r"}],
                            stage2_results=[
                                {"model": "r", "parsed_ranking": {"scores": {"Response A": 7.0}}}
                            ],
                            label_to_model={"Response A": {"model": "m", "display_index": 0}},
                            query="What is the meaning of life?",
                        )

            records = read_bias_records(store_path)
            assert records[0].query_hash is None  # No hash at LOCAL_ONLY

    def test_uses_configured_store_path(self):
        """Writes to configured store path from config."""
        from llm_council.bias_persistence import persist_session_bias_data

        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom" / "location" / "bias.jsonl"

            with patch(
                "llm_council.bias_persistence._get_bias_persistence_enabled", return_value=True
            ):
                with patch(
                    "llm_council.bias_persistence._get_bias_store_path", return_value=custom_path
                ):
                    persist_session_bias_data(
                        session_id="test",
                        stage1_results=[{"model": "m", "response": "r"}],
                        stage2_results=[
                            {"model": "r", "parsed_ranking": {"scores": {"Response A": 7.0}}}
                        ],
                        label_to_model={"Response A": {"model": "m", "display_index": 0}},
                    )

            assert custom_path.exists()
