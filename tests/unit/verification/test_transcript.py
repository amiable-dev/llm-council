"""
Tests for transcript persistence per ADR-034.

TDD Red Phase: These tests should fail until transcript.py is implemented.

Transcript persistence provides:
1. Atomic writes for each verification stage
2. Directory structure for audit trail
3. Retrieval and integrity validation
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytest

from llm_council.verification.transcript import (
    TranscriptError,
    TranscriptIntegrityError,
    TranscriptNotFoundError,
    TranscriptStore,
    create_transcript_store,
    get_transcript_path,
)


class TestTranscriptStore:
    """Tests for transcript store initialization."""

    def test_create_transcript_store_default_path(self):
        """Transcript store should use default .council/logs path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            assert store.base_path == Path(tmpdir)

    def test_create_transcript_store_creates_directory(self):
        """Transcript store should create base directory if not exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_path = Path(tmpdir) / ".council" / "logs"
            assert not logs_path.exists()

            store = create_transcript_store(base_path=logs_path)
            assert logs_path.exists()

    def test_transcript_store_readonly_mode(self):
        """Transcript store can be opened in readonly mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir), readonly=True)
            assert store.readonly is True


class TestDirectoryStructure:
    """Tests for verification transcript directory creation."""

    def test_creates_verification_directory(self):
        """Should create timestamped directory for verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            verification_id = "abc1234"

            path = store.create_verification_directory(verification_id)

            assert path.exists()
            assert verification_id in path.name

    def test_directory_name_format(self):
        """Directory name should be ISO timestamp + verification_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            verification_id = "def5678"

            path = store.create_verification_directory(verification_id)

            # Format: 2025-12-31T10-30-00-def5678
            dir_name = path.name
            assert verification_id in dir_name
            # Should have timestamp prefix (YYYY-MM-DDTHH-MM-SS)
            assert dir_name[4] == "-"  # Year separator
            assert dir_name[10] == "T"  # Date-time separator

    def test_directory_isolation(self):
        """Each verification should get unique directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))

            path1 = store.create_verification_directory("abc1234")
            path2 = store.create_verification_directory("def5678")

            assert path1 != path2
            assert path1.exists()
            assert path2.exists()


class TestAtomicWrites:
    """Tests for atomic stage writes."""

    @pytest.fixture
    def store_with_dir(self) -> tuple:
        """Create store with verification directory."""
        tmpdir = tempfile.mkdtemp()
        store = create_transcript_store(base_path=Path(tmpdir))
        verification_id = "abc1234"
        path = store.create_verification_directory(verification_id)
        return store, path, verification_id, tmpdir

    def test_write_request_stage(self, store_with_dir):
        """Should write request.json atomically."""
        store, path, vid, tmpdir = store_with_dir
        try:
            request_data = {
                "snapshot_id": "abc1234",
                "target_paths": ["src/"],
                "rubric_focus": "Security",
            }

            store.write_stage(vid, "request", request_data)

            request_file = path / "request.json"
            assert request_file.exists()

            with open(request_file) as f:
                saved = json.load(f)
            assert saved["snapshot_id"] == "abc1234"
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_write_stage1_responses(self, store_with_dir):
        """Should write stage1.json with model responses."""
        store, path, vid, tmpdir = store_with_dir
        try:
            stage1_data = {
                "responses": {
                    "openai/gpt-4": {"content": "Response 1", "latency_ms": 100},
                    "anthropic/claude-3": {"content": "Response 2", "latency_ms": 150},
                },
                "timestamp": datetime.utcnow().isoformat(),
            }

            store.write_stage(vid, "stage1", stage1_data)

            stage1_file = path / "stage1.json"
            assert stage1_file.exists()
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_write_stage2_rankings(self, store_with_dir):
        """Should write stage2.json with peer rankings."""
        store, path, vid, tmpdir = store_with_dir
        try:
            stage2_data = {
                "rankings": [
                    {"reviewer": "model_a", "ranking": ["Response B", "Response A"]},
                    {"reviewer": "model_b", "ranking": ["Response A", "Response B"]},
                ],
                "label_to_model": {"Response A": "openai/gpt-4"},
            }

            store.write_stage(vid, "stage2", stage2_data)

            stage2_file = path / "stage2.json"
            assert stage2_file.exists()
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_write_stage3_synthesis(self, store_with_dir):
        """Should write stage3.json with final synthesis."""
        store, path, vid, tmpdir = store_with_dir
        try:
            stage3_data = {
                "synthesis": "Final synthesized response...",
                "chairman_model": "openai/gpt-4",
            }

            store.write_stage(vid, "stage3", stage3_data)

            stage3_file = path / "stage3.json"
            assert stage3_file.exists()
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_write_result(self, store_with_dir):
        """Should write result.json with verification verdict."""
        store, path, vid, tmpdir = store_with_dir
        try:
            result_data = {
                "verification_id": vid,
                "verdict": "pass",
                "confidence": 0.92,
                "blocking_issues": [],
            }

            store.write_stage(vid, "result", result_data)

            result_file = path / "result.json"
            assert result_file.exists()
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_atomic_write_survives_crash(self, store_with_dir):
        """Atomic write should not leave partial files on failure."""
        store, path, vid, tmpdir = store_with_dir
        try:
            # Write should either succeed completely or leave no trace
            # We can't easily simulate crash, but we can verify
            # that write uses atomic rename pattern

            data = {"test": "data"}
            store.write_stage(vid, "test", data)

            # No .tmp files should remain
            tmp_files = list(path.glob("*.tmp"))
            assert len(tmp_files) == 0
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_readonly_store_rejects_writes(self):
        """Readonly store should reject write operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir), readonly=True)

            with pytest.raises(TranscriptError) as exc_info:
                store.write_stage("abc1234", "test", {"data": "test"})
            assert "readonly" in str(exc_info.value).lower()


class TestTranscriptRetrieval:
    """Tests for reading transcripts back."""

    def test_read_stage(self):
        """Should read stage data by verification_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            vid = "abc1234"
            store.create_verification_directory(vid)

            original = {"key": "value", "number": 42}
            store.write_stage(vid, "request", original)

            retrieved = store.read_stage(vid, "request")
            assert retrieved == original

    def test_read_all_stages(self):
        """Should read all stages for a verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            vid = "abc1234"
            store.create_verification_directory(vid)

            store.write_stage(vid, "request", {"stage": "request"})
            store.write_stage(vid, "stage1", {"stage": "stage1"})
            store.write_stage(vid, "result", {"stage": "result"})

            all_stages = store.read_all_stages(vid)

            assert "request" in all_stages
            assert "stage1" in all_stages
            assert "result" in all_stages

    def test_read_nonexistent_verification(self):
        """Should raise error for nonexistent verification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))

            with pytest.raises(TranscriptNotFoundError):
                store.read_stage("nonexistent", "request")

    def test_read_nonexistent_stage(self):
        """Should raise error for nonexistent stage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            vid = "abc1234"
            store.create_verification_directory(vid)
            store.write_stage(vid, "request", {"data": "test"})

            with pytest.raises(TranscriptNotFoundError):
                store.read_stage(vid, "nonexistent_stage")

    def test_list_verifications(self):
        """Should list all verification IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))

            store.create_verification_directory("abc1234")
            store.create_verification_directory("def5678")

            verifications = store.list_verifications()

            assert len(verifications) == 2
            # Should contain the verification IDs
            ids = [v["verification_id"] for v in verifications]
            assert "abc1234" in ids
            assert "def5678" in ids


class TestTranscriptIntegrity:
    """Tests for transcript integrity validation."""

    def test_compute_integrity_hash(self):
        """Should compute SHA256 hash of transcript contents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            vid = "abc1234"
            store.create_verification_directory(vid)

            store.write_stage(vid, "request", {"data": "test"})
            store.write_stage(vid, "result", {"verdict": "pass"})

            hash1 = store.compute_integrity_hash(vid)
            hash2 = store.compute_integrity_hash(vid)

            # Same content should produce same hash
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA256 hex

    def test_different_content_different_hash(self):
        """Different content should produce different hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))

            vid1 = "abc1234"
            vid2 = "def5678"
            store.create_verification_directory(vid1)
            store.create_verification_directory(vid2)

            store.write_stage(vid1, "request", {"data": "test1"})
            store.write_stage(vid2, "request", {"data": "test2"})

            hash1 = store.compute_integrity_hash(vid1)
            hash2 = store.compute_integrity_hash(vid2)

            assert hash1 != hash2

    def test_validate_integrity_success(self):
        """Should validate integrity when hash matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            vid = "abc1234"
            store.create_verification_directory(vid)
            store.write_stage(vid, "request", {"data": "test"})

            expected_hash = store.compute_integrity_hash(vid)

            # Should not raise
            store.validate_integrity(vid, expected_hash)

    def test_validate_integrity_failure(self):
        """Should raise error when hash doesn't match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = create_transcript_store(base_path=Path(tmpdir))
            vid = "abc1234"
            store.create_verification_directory(vid)
            store.write_stage(vid, "request", {"data": "test"})

            wrong_hash = "0" * 64  # Invalid hash

            with pytest.raises(TranscriptIntegrityError):
                store.validate_integrity(vid, wrong_hash)


class TestTranscriptPath:
    """Tests for transcript path utilities."""

    def test_get_transcript_path_default(self):
        """Should return default .council/logs path."""
        path = get_transcript_path()
        assert path.name == "logs"
        assert ".council" in str(path)

    def test_get_transcript_path_from_env(self, monkeypatch):
        """Should use LLM_COUNCIL_TRANSCRIPT_PATH if set."""
        monkeypatch.setenv("LLM_COUNCIL_TRANSCRIPT_PATH", "/custom/path")
        path = get_transcript_path()
        assert path == Path("/custom/path")

    def test_get_transcript_path_from_project_root(self):
        """Should find .council/logs relative to project root."""
        # This tests the actual behavior - may vary based on cwd
        path = get_transcript_path()
        assert isinstance(path, Path)


class TestConcurrentWrites:
    """Tests for concurrent write safety."""

    def test_concurrent_writes_different_verifications(self):
        """Concurrent writes to different verifications should not conflict."""
        import asyncio

        async def write_verification(store: TranscriptStore, vid: str):
            store.create_verification_directory(vid)
            store.write_stage(vid, "request", {"vid": vid})
            store.write_stage(vid, "result", {"verdict": "pass"})
            await asyncio.sleep(0.01)
            return vid

        async def run_concurrent():
            with tempfile.TemporaryDirectory() as tmpdir:
                store = create_transcript_store(base_path=Path(tmpdir))

                results = await asyncio.gather(
                    write_verification(store, "abc1234"),
                    write_verification(store, "def5678"),
                    write_verification(store, "aabb112"),
                )

                # All should succeed
                assert len(results) == 3

                # All should be readable
                for vid in results:
                    data = store.read_stage(vid, "request")
                    assert data["vid"] == vid

        asyncio.run(run_concurrent())
