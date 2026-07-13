"""#584: content-mode git calls must not spread an unbounded path list
directly into a subprocess argv.

`_blob_sizes`, `_text_paths`, and `_reviewability_attrs` (all reached only
in `LLM_COUNCIL_FILE_SELECTION=content`/`shadow` mode) each spread a
candidate-path list straight into a single `git` subprocess's argv. A commit
touching enough files (a large vendoring or initial-import commit) can
exceed the OS ARG_MAX; the call then fails and every one of those paths is
silently treated as omitted/binary rather than surfaced as a real error.
The fix chunks the path list across multiple git calls and merges results.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.verification import file_ops


def _paths(n: int) -> list:
    return [f"src/file_{i}.py" for i in range(n)]


def _argv_paths(call_args) -> list:
    """Extract the paths passed after the `--` separator in a subprocess call."""
    args = call_args.args
    return list(args[args.index("--") + 1 :])


class TestBlobSizesChunking:
    @pytest.mark.asyncio
    async def test_chunks_across_multiple_git_calls(self, monkeypatch):
        monkeypatch.setattr(file_ops, "GIT_ARGV_BATCH_SIZE", 5)
        paths = _paths(12)  # 3 chunks of 5, 5, 2 at batch size 5

        async def fake_exec(*args, **kwargs):
            chunk = list(args[args.index("--") + 1 :])
            proc = MagicMock()
            proc.returncode = 0
            out = "".join(f"10 {p}\0" for p in chunk).encode()
            proc.communicate = AsyncMock(return_value=(out, b""))
            return proc

        with (
            patch.object(
                file_ops, "_get_git_root_async", new_callable=AsyncMock, return_value="/mock"
            ),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec) as mock_exec,
        ):
            sizes = await file_ops._blob_sizes("HEAD", paths)

        assert mock_exec.call_count >= 3, "a 12-path list at batch size 5 must be chunked"
        for call in mock_exec.call_args_list:
            assert len(_argv_paths(call)) <= 5
        assert set(sizes.keys()) == set(paths), "results from every chunk must be merged"
        assert all(v == 10 for v in sizes.values())


class TestTextPathsChunking:
    @pytest.mark.asyncio
    async def test_chunks_across_multiple_git_calls(self, monkeypatch):
        monkeypatch.setattr(file_ops, "GIT_ARGV_BATCH_SIZE", 5)
        paths = _paths(12)

        async def fake_exec(*args, **kwargs):
            chunk = list(args[args.index("--") + 1 :])
            proc = MagicMock()
            proc.returncode = 0
            out = "".join(f"HEAD:{p}\0" for p in chunk).encode()
            proc.communicate = AsyncMock(return_value=(out, b""))
            return proc

        with (
            patch.object(
                file_ops, "_get_git_root_async", new_callable=AsyncMock, return_value="/mock"
            ),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec) as mock_exec,
        ):
            text = await file_ops._text_paths("HEAD", paths)

        assert mock_exec.call_count >= 3
        for call in mock_exec.call_args_list:
            assert len(_argv_paths(call)) <= 5
        assert text == set(paths), "results from every chunk must be merged"


class TestReviewabilityAttrsChunking:
    @pytest.mark.asyncio
    async def test_chunks_across_multiple_git_calls(self, monkeypatch):
        monkeypatch.setattr(file_ops, "GIT_ARGV_BATCH_SIZE", 5)
        paths = _paths(12)

        async def fake_exec(*args, **kwargs):
            chunk = list(args[args.index("--") + 1 :])
            proc = MagicMock()
            proc.returncode = 0
            # Every path in this chunk is "generated".
            triples = "".join(f"{p}\0linguist-generated\0set\0" for p in chunk)
            proc.communicate = AsyncMock(return_value=(triples.encode(), b""))
            return proc

        with (
            patch.object(
                file_ops, "_get_git_root_async", new_callable=AsyncMock, return_value="/mock"
            ),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec) as mock_exec,
        ):
            attrs = await file_ops._reviewability_attrs("HEAD", paths)

        assert mock_exec.call_count >= 3
        for call in mock_exec.call_args_list:
            assert len(_argv_paths(call)) <= 5
        assert set(attrs.keys()) == set(paths), "results from every chunk must be merged"
        assert all(v == "generated" for v in attrs.values())
