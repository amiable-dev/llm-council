"""A file much larger than the read limit must not hang the fetch.

Seen on every council-gate run whose diff included CHANGELOG.md (~218 KB):

    git show for <sha>:CHANGELOG.md produced all stdout but did not exit
    within 10s ... force-killed

and the file came back as ``[Error: git show ... hung]`` instead of its
truncated content.

Cause. Once the limit is reached the fetch kills ``git`` and stops reading its
stdout. asyncio keeps reading in the background, and pauses when its buffer
passes the high-water mark — with the end-of-file still unread. Up to Python
3.12 ``Process.wait()`` is only woken once EVERY pipe has disconnected,
and a paused pipe never does, so ``wait()`` blocks although the process is
dead. Small files never reach the high-water mark, which is why only the one
very large file was affected. (Confirmed on 3.11 and 3.12. Python 3.13 wakes
``wait()`` on process exit, so this test cannot fail there.)

The test makes the pause deterministic by shrinking the stream buffer.
"""

import asyncio
import sys
import time
from unittest.mock import patch

from llm_council.verification import file_ops

BIG = 400_000
CHILD = f"import sys; sys.stdout.write('x' * {BIG}); sys.stdout.flush()"


async def test_truncated_large_file_returns_content_without_hanging():
    real_exec = asyncio.create_subprocess_exec

    async def tiny_buffer_exec(*args, **kwargs):
        if args[:2] != ("git", "show"):
            return await real_exec(*args, **kwargs)
        # A 1 KB stream limit pauses the reader on the first chunk, which is
        # the state a large file reaches on its own once enough has arrived.
        return await real_exec(sys.executable, "-c", CHILD, limit=1024, **kwargs)

    with (
        patch.object(file_ops.asyncio, "create_subprocess_exec", tiny_buffer_exec),
        patch.object(file_ops, "ASYNC_SUBPROCESS_TIMEOUT", 3),
    ):
        started = time.monotonic()
        content, truncated = await file_ops._fetch_file_at_commit_async(
            "0" * 40, "CHANGELOG.md", max_file_chars=30_000
        )
        elapsed = time.monotonic() - started

    assert "hung" not in content and not content.startswith("[Error")
    assert truncated is True
    assert content.startswith("x" * 30_000)
    assert elapsed < 2.0, f"fetch took {elapsed:.1f}s — wait() blocked on an undrained pipe"


async def test_drain_is_bounded_when_stdout_never_ends():
    """A stdout that never reaches EOF must not turn the drain into a spin."""
    from unittest.mock import AsyncMock, MagicMock

    reads = 0

    async def endless(size: int) -> bytes:
        nonlocal reads
        reads += 1
        return b"x" * size

    proc = MagicMock()
    proc.stdout.read = endless
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.returncode = -9
    proc.wait = AsyncMock()

    with (
        patch.object(file_ops, "_get_git_root_async", AsyncMock(return_value="/mock/root")),
        patch.object(file_ops, "_get_git_semaphore", AsyncMock(return_value=asyncio.Semaphore(1))),
        patch.object(file_ops.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)),
    ):
        content, truncated = await asyncio.wait_for(
            file_ops._fetch_file_at_commit_async("HEAD", "huge.txt", max_file_chars=30_000),
            timeout=2.0,
        )

    assert truncated is True and content.startswith("x" * 30_000)
    assert len(content) < 31_000  # nothing drained is kept
    assert reads < 100
