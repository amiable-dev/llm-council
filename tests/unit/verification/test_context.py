"""
Tests for verification context isolation per ADR-034.

TDD Red Phase: These tests should fail until context.py is implemented.

Context isolation ensures:
1. Each verification runs in fresh context (no session bleed)
2. Snapshot IDs are validated (git SHA format)
3. Multiple concurrent verifications don't share state
"""

import asyncio
import re
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.verification.context import (
    ContextIsolationError,
    InvalidSnapshotError,
    VerificationContextManager,
    create_isolated_context,
    validate_snapshot_id,
)


class TestSnapshotValidation:
    """Tests for git SHA snapshot validation."""

    def test_validate_snapshot_id_valid_short_sha(self):
        """Valid short SHA (7+ chars) should pass."""
        assert validate_snapshot_id("abc1234") is True
        assert validate_snapshot_id("1234567") is True

    def test_validate_snapshot_id_valid_full_sha(self):
        """Valid full SHA (40 chars) should pass."""
        full_sha = "a" * 40
        assert validate_snapshot_id(full_sha) is True
        full_sha_mixed = "abc123def456789012345678901234567890abcd"
        assert validate_snapshot_id(full_sha_mixed) is True

    def test_validate_snapshot_id_invalid_too_short(self):
        """SHA shorter than 7 chars should fail."""
        with pytest.raises(InvalidSnapshotError) as exc_info:
            validate_snapshot_id("abc123")  # 6 chars
        assert "too short" in str(exc_info.value).lower()

    def test_validate_snapshot_id_invalid_chars(self):
        """SHA with non-hex chars should fail."""
        with pytest.raises(InvalidSnapshotError) as exc_info:
            validate_snapshot_id("ghijklm")  # non-hex
        assert "invalid" in str(exc_info.value).lower()

    def test_validate_snapshot_id_invalid_too_long(self):
        """SHA longer than 40 chars should fail."""
        with pytest.raises(InvalidSnapshotError) as exc_info:
            validate_snapshot_id("a" * 41)
        assert "too long" in str(exc_info.value).lower()

    def test_validate_snapshot_id_empty(self):
        """Empty string should fail."""
        with pytest.raises(InvalidSnapshotError):
            validate_snapshot_id("")

    def test_validate_snapshot_id_none(self):
        """None should fail."""
        with pytest.raises(InvalidSnapshotError):
            validate_snapshot_id(None)  # type: ignore


class TestCreateIsolatedContext:
    """Tests for creating isolated verification contexts."""

    def test_create_isolated_context_fresh_state(self):
        """Each context should have fresh state, not inherited from session."""
        ctx1 = create_isolated_context(snapshot_id="abc1234")
        ctx2 = create_isolated_context(snapshot_id="def5678")

        # Contexts should be independent
        assert ctx1.context_id != ctx2.context_id
        assert ctx1.snapshot_id != ctx2.snapshot_id

        # Neither should inherit from a session
        assert ctx1.inherited_from_session is False
        assert ctx2.inherited_from_session is False

    def test_create_isolated_context_has_unique_id(self):
        """Each context should have a unique identifier."""
        ctx1 = create_isolated_context(snapshot_id="abc1234")
        ctx2 = create_isolated_context(snapshot_id="abc1234")  # Same snapshot

        # Even with same snapshot, context IDs should differ
        assert ctx1.context_id != ctx2.context_id

    def test_create_isolated_context_validates_snapshot(self):
        """Context creation should validate snapshot ID."""
        with pytest.raises(InvalidSnapshotError):
            create_isolated_context(snapshot_id="bad")  # Too short

    def test_create_isolated_context_captures_timestamp(self):
        """Context should capture creation timestamp."""
        before = datetime.utcnow()
        ctx = create_isolated_context(snapshot_id="abc1234")
        after = datetime.utcnow()

        assert before <= ctx.created_at <= after

    def test_create_isolated_context_with_rubric_focus(self):
        """Context should accept optional rubric focus."""
        ctx = create_isolated_context(
            snapshot_id="abc1234",
            rubric_focus="Security",
        )
        assert ctx.rubric_focus == "Security"

    def test_create_isolated_context_default_rubric_focus(self):
        """Rubric focus should default to None."""
        ctx = create_isolated_context(snapshot_id="abc1234")
        assert ctx.rubric_focus is None


class TestVerificationContextManager:
    """Tests for the verification context manager."""

    def test_context_manager_creates_isolated_context(self):
        """Context manager should create isolated context on enter."""
        with VerificationContextManager(snapshot_id="abc1234") as ctx:
            assert ctx is not None
            assert ctx.snapshot_id == "abc1234"
            assert ctx.inherited_from_session is False

    def test_context_manager_cleans_up_on_exit(self):
        """Context manager should clean up resources on exit."""
        manager = VerificationContextManager(snapshot_id="abc1234")
        with manager as ctx:
            context_id = ctx.context_id
            assert manager.is_active is True

        # After exit, context should be inactive
        assert manager.is_active is False

    def test_context_manager_cleans_up_on_exception(self):
        """Context manager should clean up even if exception occurs."""
        manager = VerificationContextManager(snapshot_id="abc1234")

        with pytest.raises(ValueError):
            with manager as ctx:
                raise ValueError("Test exception")

        # Should still clean up
        assert manager.is_active is False

    def test_context_manager_prevents_reentry(self):
        """Context manager should not allow nested entry."""
        manager = VerificationContextManager(snapshot_id="abc1234")

        with manager as ctx:
            with pytest.raises(ContextIsolationError) as exc_info:
                with manager as ctx2:
                    pass
            assert "reentry" in str(exc_info.value).lower()

    def test_context_manager_tracks_duration(self):
        """Context manager should track execution duration."""
        import time

        manager = VerificationContextManager(snapshot_id="abc1234")
        with manager as ctx:
            time.sleep(0.01)  # Small delay

        assert manager.duration_ms is not None
        assert manager.duration_ms >= 10  # At least 10ms


class TestConcurrentContextIsolation:
    """Tests for concurrent verification isolation."""

    @pytest.mark.asyncio
    async def test_concurrent_verifications_isolated(self):
        """Multiple parallel verifications should not share state."""
        results = {}

        async def run_verification(name: str, snapshot: str):
            ctx = create_isolated_context(snapshot_id=snapshot)
            # Simulate some work
            await asyncio.sleep(0.01)
            results[name] = {
                "context_id": ctx.context_id,
                "snapshot_id": ctx.snapshot_id,
            }

        # Run multiple verifications concurrently
        # Note: Snapshots must be valid hex (0-9, a-f only)
        await asyncio.gather(
            run_verification("v1", "abc1234"),
            run_verification("v2", "def5678"),
            run_verification("v3", "aabb001"),
        )

        # Each should have unique context
        context_ids = [r["context_id"] for r in results.values()]
        assert len(context_ids) == len(set(context_ids))  # All unique

        # Each should have correct snapshot
        assert results["v1"]["snapshot_id"] == "abc1234"
        assert results["v2"]["snapshot_id"] == "def5678"
        assert results["v3"]["snapshot_id"] == "aabb001"

    @pytest.mark.asyncio
    async def test_concurrent_context_managers_isolated(self):
        """Multiple concurrent context managers should be isolated."""
        active_contexts = []

        async def run_with_manager(snapshot: str):
            manager = VerificationContextManager(snapshot_id=snapshot)
            async with manager as ctx:
                active_contexts.append(ctx.context_id)
                await asyncio.sleep(0.02)
                return ctx.context_id

        # Run concurrently (using valid hex strings)
        results = await asyncio.gather(
            run_with_manager("abc1234"),
            run_with_manager("def5678"),
            run_with_manager("aabb001"),
        )

        # All should have unique context IDs
        assert len(results) == len(set(results))


class TestContextStateIsolation:
    """Tests for state isolation within contexts."""

    def test_context_state_not_shared(self):
        """State set in one context should not affect another."""
        ctx1 = create_isolated_context(snapshot_id="abc1234")
        ctx2 = create_isolated_context(snapshot_id="def5678")

        # Set state in ctx1
        ctx1.set_state("key", "value1")

        # ctx2 should not see it
        assert ctx2.get_state("key") is None

    def test_context_state_persists_within_context(self):
        """State set within a context should persist in that context."""
        ctx = create_isolated_context(snapshot_id="abc1234")

        ctx.set_state("key", "value")
        assert ctx.get_state("key") == "value"

    def test_context_state_cleared_on_reset(self):
        """Context state should be clearable."""
        ctx = create_isolated_context(snapshot_id="abc1234")

        ctx.set_state("key", "value")
        ctx.clear_state()

        assert ctx.get_state("key") is None


class TestContextMetadata:
    """Tests for context metadata."""

    def test_context_has_reproducibility_hash(self):
        """Context should generate reproducibility hash from inputs."""
        ctx = create_isolated_context(
            snapshot_id="abc1234",
            rubric_focus="Security",
        )

        assert ctx.reproducibility_hash is not None
        assert len(ctx.reproducibility_hash) > 0

    def test_same_inputs_same_reproducibility_hash(self):
        """Same inputs should produce same reproducibility hash."""
        ctx1 = create_isolated_context(
            snapshot_id="abc1234",
            rubric_focus="Security",
        )
        ctx2 = create_isolated_context(
            snapshot_id="abc1234",
            rubric_focus="Security",
        )

        assert ctx1.reproducibility_hash == ctx2.reproducibility_hash

    def test_different_inputs_different_reproducibility_hash(self):
        """Different inputs should produce different reproducibility hash."""
        ctx1 = create_isolated_context(
            snapshot_id="abc1234",
            rubric_focus="Security",
        )
        ctx2 = create_isolated_context(
            snapshot_id="abc1234",
            rubric_focus="Performance",  # Different focus
        )

        assert ctx1.reproducibility_hash != ctx2.reproducibility_hash

    def test_context_to_dict(self):
        """Context should be serializable to dict."""
        ctx = create_isolated_context(
            snapshot_id="abc1234",
            rubric_focus="Security",
        )

        data = ctx.to_dict()

        assert "context_id" in data
        assert "snapshot_id" in data
        assert data["snapshot_id"] == "abc1234"
        assert "rubric_focus" in data
        assert data["rubric_focus"] == "Security"
        assert "created_at" in data
        assert "reproducibility_hash" in data
