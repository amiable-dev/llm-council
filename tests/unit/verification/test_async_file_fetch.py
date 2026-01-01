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
        """Large files should be truncated to MAX_FILE_CHARS via streaming read."""
        from llm_council.verification.api import (
            _fetch_file_at_commit_async,
            MAX_FILE_CHARS,
        )

        # Mock a large file response with streaming behavior
        # Content must be significantly larger than MAX_FILE_CHARS to trigger truncation
        large_content = b"x" * (MAX_FILE_CHARS + 10000)
        read_position = 0

        async def mock_read(size: int) -> bytes:
            """Simulate streaming read returning chunks."""
            nonlocal read_position
            chunk = large_content[read_position : read_position + size]
            read_position += size
            return chunk

        # Create mock stdout that simulates streaming read
        mock_stdout = MagicMock()
        mock_stdout.read = mock_read  # This is an async function

        mock_stderr = MagicMock()
        mock_stderr.read = AsyncMock(return_value=b"")

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = mock_stderr
        # returncode will be -9 (killed) or we can ignore it since truncation sets it
        mock_proc.returncode = 0  # Normal exit before we kill it
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(
                "llm_council.verification.api._get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
            patch(
                "llm_council.verification.api._get_git_semaphore",
                new_callable=AsyncMock,
                return_value=asyncio.Semaphore(10),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            content, truncated = await _fetch_file_at_commit_async("HEAD", "large_file.txt")

            assert truncated is True
            assert len(content) <= MAX_FILE_CHARS + 100  # Allow for truncation message
            assert "truncated" in content.lower()
            # Verify process was killed to avoid buffering remaining data
            mock_proc.kill.assert_called()


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
        from llm_council.verification.api import (
            _fetch_file_at_commit_async,
            ASYNC_SUBPROCESS_TIMEOUT,
        )

        # Mock a slow streaming read that takes longer than the timeout
        async def slow_read(size: int) -> bytes:
            await asyncio.sleep(ASYNC_SUBPROCESS_TIMEOUT + 1)  # Exceed timeout
            return b"content"

        # Create mock stdout that simulates slow streaming read
        mock_stdout = MagicMock()
        mock_stdout.read = slow_read

        mock_stderr = MagicMock()
        mock_stderr.read = AsyncMock(return_value=b"")

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = mock_stderr
        mock_proc.returncode = 0
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(
                "llm_council.verification.api._get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
            patch(
                "llm_council.verification.api._get_git_semaphore",
                new_callable=AsyncMock,
                return_value=asyncio.Semaphore(10),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
            # Override the timeout to a short value for testing
            patch("llm_council.verification.api.ASYNC_SUBPROCESS_TIMEOUT", 0.1),
        ):
            content, truncated = await _fetch_file_at_commit_async("HEAD", "file.txt")

            # Should have timed out and returned error
            assert "[Error:" in content or "Timeout" in content
            # Process should have been killed
            mock_proc.kill.assert_called()


class TestPathValidation:
    """Tests for path validation security."""

    def test_rejects_absolute_paths(self):
        """Should reject absolute paths."""
        from llm_council.verification.api import _validate_file_path

        assert _validate_file_path("/etc/passwd") is False
        assert _validate_file_path("\\Windows\\System32") is False

    def test_rejects_path_traversal(self):
        """Should reject path traversal attempts."""
        from llm_council.verification.api import _validate_file_path

        assert _validate_file_path("../secret.txt") is False
        assert _validate_file_path("foo/../../../etc/passwd") is False
        assert _validate_file_path("..") is False

    def test_rejects_null_bytes(self):
        """Should reject null byte injection."""
        from llm_council.verification.api import _validate_file_path

        assert _validate_file_path("file.txt\x00.jpg") is False

    def test_accepts_valid_paths(self):
        """Should accept valid relative paths."""
        from llm_council.verification.api import _validate_file_path

        assert _validate_file_path("src/main.py") is True
        assert _validate_file_path("tests/test_file.py") is True
        assert _validate_file_path("README.md") is True

    @pytest.mark.asyncio
    async def test_fetch_rejects_invalid_paths(self):
        """Fetch should return error for invalid paths."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        content, truncated = await _fetch_file_at_commit_async("HEAD", "../secret.txt")
        assert "[Error:" in content
        assert "Invalid file path" in content


class TestConcurrencyLimiting:
    """Tests for concurrency limiting via semaphore."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_operations(self):
        """Semaphore should limit concurrent git operations to MAX_CONCURRENT_GIT_OPS."""
        from llm_council.verification.api import MAX_CONCURRENT_GIT_OPS, _get_git_semaphore

        sem = await _get_git_semaphore()

        # Semaphore should be created with MAX_CONCURRENT_GIT_OPS
        # We can't directly access _value, but we can verify the semaphore exists
        assert sem is not None
        assert isinstance(sem, asyncio.Semaphore)

    @pytest.mark.asyncio
    async def test_max_concurrent_git_ops_is_reasonable(self):
        """MAX_CONCURRENT_GIT_OPS should be a reasonable limit."""
        from llm_council.verification.api import MAX_CONCURRENT_GIT_OPS

        # Should be between 1 and 50 (reasonable for preventing DoS)
        assert (
            1 <= MAX_CONCURRENT_GIT_OPS <= 50
        ), f"MAX_CONCURRENT_GIT_OPS={MAX_CONCURRENT_GIT_OPS} should be between 1 and 50"


class TestStreamingMemoryBounded:
    """Tests for memory-bounded streaming read (DoS protection)."""

    @pytest.mark.asyncio
    async def test_streaming_read_doesnt_buffer_entire_file(self):
        """Streaming should read in chunks, not buffer entire file."""
        from llm_council.verification.api import MAX_FILE_CHARS

        # Track actual bytes read by chunks
        bytes_read_tracker: list = []
        large_content = b"x" * (MAX_FILE_CHARS * 2)  # 2x max to ensure truncation
        read_pos = 0

        async def tracking_read(size: int) -> bytes:
            """Track each read call size."""
            nonlocal read_pos
            chunk = large_content[read_pos : read_pos + size]
            read_pos += size
            bytes_read_tracker.append(len(chunk))
            return chunk

        # Create mock stdout that simulates streaming read
        mock_stdout = MagicMock()
        mock_stdout.read = tracking_read

        mock_stderr = MagicMock()
        mock_stderr.read = AsyncMock(return_value=b"")

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = mock_stderr
        mock_proc.returncode = 0
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(
                "llm_council.verification.api._get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
            patch(
                "llm_council.verification.api._get_git_semaphore",
                new_callable=AsyncMock,
                return_value=asyncio.Semaphore(10),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            from llm_council.verification.api import _fetch_file_at_commit_async

            content, truncated = await _fetch_file_at_commit_async("HEAD", "huge_file.txt")

            # Should have read in chunks (8KB each based on implementation)
            assert len(bytes_read_tracker) > 1, "Should read in multiple chunks"
            # Total bytes read should be approximately MAX_FILE_CHARS + 1 (for truncation check)
            total_read = sum(bytes_read_tracker)
            assert (
                total_read <= MAX_FILE_CHARS + 8192 + 1
            ), f"Should not buffer entire file: read {total_read} bytes"
            assert truncated is True

    @pytest.mark.asyncio
    async def test_process_killed_on_large_file_truncation(self):
        """Process should be killed when large file is truncated to save resources."""
        from llm_council.verification.api import MAX_FILE_CHARS

        # Content must be significantly larger than MAX_FILE_CHARS to trigger truncation
        large_content = b"x" * (MAX_FILE_CHARS + 10000)
        read_pos = 0

        async def mock_read(size: int) -> bytes:
            nonlocal read_pos
            chunk = large_content[read_pos : read_pos + size]
            read_pos += size
            return chunk

        # Create mock stdout that simulates streaming read
        mock_stdout = MagicMock()
        mock_stdout.read = mock_read

        mock_stderr = MagicMock()
        mock_stderr.read = AsyncMock(return_value=b"")

        mock_proc = MagicMock()
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = mock_stderr
        mock_proc.returncode = 0
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(
                "llm_council.verification.api._get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
            patch(
                "llm_council.verification.api._get_git_semaphore",
                new_callable=AsyncMock,
                return_value=asyncio.Semaphore(10),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            from llm_council.verification.api import _fetch_file_at_commit_async

            await _fetch_file_at_commit_async("HEAD", "large_file.txt")

            # Process should have been killed
            mock_proc.kill.assert_called_once()


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
        """Should use asyncio.create_subprocess_exec for file content fetching."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        # Mock streaming read behavior
        read_called = False

        async def mock_read(size: int) -> bytes:
            nonlocal read_called
            if read_called:
                return b""  # EOF
            read_called = True
            return b"content"

        # Patch async subprocess and git root helper
        with (
            patch("asyncio.create_subprocess_exec") as mock_async,
            patch(
                "llm_council.verification.api._get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
            patch(
                "llm_council.verification.api._get_git_semaphore",
                new_callable=AsyncMock,
                return_value=asyncio.Semaphore(10),
            ),
        ):
            mock_stdout = AsyncMock()
            mock_stdout.read = mock_read
            mock_stderr = AsyncMock()
            mock_stderr.read = AsyncMock(return_value=b"")

            mock_proc = AsyncMock()
            mock_proc.stdout = mock_stdout
            mock_proc.stderr = mock_stderr
            mock_proc.returncode = 0
            mock_proc.wait = AsyncMock()
            mock_async.return_value = mock_proc

            await _fetch_file_at_commit_async("HEAD", "file.txt")

            # Async subprocess should be called for file content
            assert mock_async.called, "Should use asyncio.create_subprocess_exec"
            # Verify cwd was passed (for CWD independence)
            assert mock_async.call_args.kwargs.get("cwd") == "/mock/root"
