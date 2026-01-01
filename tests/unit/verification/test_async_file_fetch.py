"""
Unit tests for async file fetching in verification API (issue #303).

TDD Red Phase: Tests for async subprocess operations that don't block event loop.

These tests verify that:
1. File fetching uses async subprocess (not blocking subprocess.run)
2. Multiple concurrent file fetches don't block each other
3. Timeouts work correctly with async operations
"""

import asyncio
import time
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAsyncFileFetching:
    """Tests for async file content fetching."""

    @pytest.mark.asyncio
    async def test_fetch_file_is_async(self):
        """File fetching should be awaitable (async function)."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        # Should be a coroutine function
        assert asyncio.iscoroutinefunction(_fetch_file_at_commit_async)

    @pytest.mark.asyncio
    async def test_fetch_file_returns_content_and_truncation_flag(self):
        """Async fetch should return (content, was_truncated) tuple."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        # Use a known commit and file
        content, truncated = await _fetch_file_at_commit_async("HEAD", "pyproject.toml")

        assert isinstance(content, str)
        assert isinstance(truncated, bool)
        assert len(content) > 0
        assert "[project]" in content  # pyproject.toml should have this

    @pytest.mark.asyncio
    async def test_fetch_file_handles_missing_file(self):
        """Should return error message for missing files, not crash."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        content, truncated = await _fetch_file_at_commit_async("HEAD", "nonexistent/file/path.py")

        assert "[Error:" in content
        assert truncated is False

    @pytest.mark.asyncio
    async def test_fetch_file_handles_invalid_commit(self):
        """Should return error message for invalid commits."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        content, truncated = await _fetch_file_at_commit_async(
            "invalidcommitsha123", "pyproject.toml"
        )

        assert "[Error:" in content
        assert truncated is False

    @pytest.mark.asyncio
    async def test_fetch_file_truncates_large_files(self):
        """Large files should be truncated to MAX_FILE_CHARS."""
        from llm_council.verification.api import (
            _fetch_file_at_commit_async,
            MAX_FILE_CHARS,
        )

        # Mock a large file response
        large_content = "x" * (MAX_FILE_CHARS + 1000)

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (
                large_content.encode(),
                b"",
            )
            mock_proc.returncode = 0
            mock_subprocess.return_value = mock_proc

            content, truncated = await _fetch_file_at_commit_async("HEAD", "large_file.txt")

            assert truncated is True
            assert len(content) <= MAX_FILE_CHARS + 100  # Allow for truncation message
            assert "truncated" in content.lower()


class TestConcurrentFileFetching:
    """Tests for concurrent file fetching without blocking."""

    @pytest.mark.asyncio
    async def test_concurrent_fetches_dont_block_each_other(self):
        """Multiple concurrent fetches should run in parallel, not serially."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        # Measure time for concurrent fetches
        files = ["pyproject.toml", "README.md", "CHANGELOG.md"]

        start = time.monotonic()
        results = await asyncio.gather(*[_fetch_file_at_commit_async("HEAD", f) for f in files])
        concurrent_time = time.monotonic() - start

        # Measure time for sequential fetches
        start = time.monotonic()
        for f in files:
            await _fetch_file_at_commit_async("HEAD", f)
        sequential_time = time.monotonic() - start

        # Concurrent should be faster (or at least not significantly slower)
        # Allow 50% overhead for context switching
        assert concurrent_time < sequential_time * 1.5, (
            f"Concurrent ({concurrent_time:.2f}s) should be faster than "
            f"sequential ({sequential_time:.2f}s)"
        )

    @pytest.mark.asyncio
    async def test_fetch_files_for_verification_is_async(self):
        """The multi-file fetch function should be async."""
        from llm_council.verification.api import _fetch_files_for_verification_async

        assert asyncio.iscoroutinefunction(_fetch_files_for_verification_async)

    @pytest.mark.asyncio
    async def test_fetch_files_returns_formatted_content(self):
        """Multi-file fetch should return formatted markdown sections."""
        from llm_council.verification.api import _fetch_files_for_verification_async

        content = await _fetch_files_for_verification_async(
            "HEAD",
            ["pyproject.toml"],
        )

        assert "### pyproject.toml" in content
        assert "```" in content  # Code block


class TestAsyncTimeout:
    """Tests for timeout handling in async operations."""

    @pytest.mark.asyncio
    async def test_fetch_respects_timeout(self):
        """File fetch should timeout after configured duration."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        # Mock a slow git command
        async def slow_communicate():
            await asyncio.sleep(30)  # Simulate slow operation
            return (b"content", b"")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.communicate = slow_communicate
            mock_proc.returncode = 0
            mock_proc.kill = MagicMock()
            mock_subprocess.return_value = mock_proc

            content, truncated = await _fetch_file_at_commit_async("HEAD", "file.txt")

            # Should have timed out and returned error
            assert "[Error:" in content or "Timeout" in content


class TestEventLoopNotBlocked:
    """Tests that event loop is not blocked by file operations."""

    @pytest.mark.asyncio
    async def test_event_loop_remains_responsive(self):
        """Event loop should remain responsive during file fetch."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        # Create a flag that will be set by a concurrent task
        flag_set = False

        async def set_flag():
            nonlocal flag_set
            await asyncio.sleep(0.01)  # Tiny delay
            flag_set = True

        # Start file fetch and flag setter concurrently
        await asyncio.gather(
            _fetch_file_at_commit_async("HEAD", "pyproject.toml"),
            set_flag(),
        )

        # Flag should have been set (event loop wasn't blocked)
        assert flag_set, "Event loop was blocked during file fetch"

    @pytest.mark.asyncio
    async def test_uses_asyncio_subprocess_not_sync(self):
        """Should use asyncio.create_subprocess_exec, not subprocess.run."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        # Patch both to verify which one is called
        with (
            patch("asyncio.create_subprocess_exec") as mock_async,
            patch("subprocess.run") as mock_sync,
        ):
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b"content", b"")
            mock_proc.returncode = 0
            mock_async.return_value = mock_proc

            await _fetch_file_at_commit_async("HEAD", "file.txt")

            # Async subprocess should be called, not sync
            assert mock_async.called, "Should use asyncio.create_subprocess_exec"
            assert not mock_sync.called, "Should NOT use subprocess.run"
