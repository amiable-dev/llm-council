"""Issue #342: file truncation must scale with tier, and per-file
truncation must surface in expansion_warnings instead of being silently
discarded.

Bug discovered when ADR-034 (56,093 chars) was verified at the reasoning
tier and reviewers received only 15,942 chars — the legacy per-file cap
of 15,000 amputated the document long before the tier-aware 50,000-char
budget had a chance to apply, and the per-file `truncated` boolean
returned by the fetcher was thrown away.
"""

import asyncio
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tier-aware per-file streaming cap
# ---------------------------------------------------------------------------


class TestFetchFileAtCommitAcceptsTierAwareLimit:
    """`_fetch_file_at_commit_async` must accept a per-call `max_file_chars`
    so the streaming read and clamp can scale with the active tier instead
    of being fixed at the legacy 15K value."""

    @pytest.mark.asyncio
    async def test_keeps_full_content_when_under_supplied_limit(self):
        """A 40K file with max_file_chars=50000 must NOT be truncated."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        size = 40_000
        payload = b"y" * size
        read_position = 0

        async def mock_read(n: int) -> bytes:
            nonlocal read_position
            chunk = payload[read_position : read_position + n]
            read_position += n
            return chunk

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
            content, truncated = await _fetch_file_at_commit_async(
                "HEAD", "doc.md", max_file_chars=50_000
            )

        assert truncated is False, "40K file with 50K limit must not be flagged truncated"
        assert len(content) == size, (
            f"expected full {size} chars but got {len(content)} — the per-file "
            "cap is not honouring the supplied max_file_chars"
        )
        assert "truncated" not in content.lower()
        mock_proc.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_truncates_when_exceeding_supplied_limit(self):
        """A 60K file with max_file_chars=50000 must be clamped to 50K + marker."""
        from llm_council.verification.api import _fetch_file_at_commit_async

        limit = 50_000
        payload = b"z" * (limit + 10_000)
        read_position = 0

        async def mock_read(n: int) -> bytes:
            nonlocal read_position
            chunk = payload[read_position : read_position + n]
            read_position += n
            return chunk

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
            content, truncated = await _fetch_file_at_commit_async(
                "HEAD", "big.md", max_file_chars=limit
            )

        assert truncated is True
        assert "truncated" in content.lower()
        # Body before the marker should be exactly the limit
        assert content.startswith("z" * limit)


# ---------------------------------------------------------------------------
# Per-tier wiring on the multi-file fetcher
# ---------------------------------------------------------------------------


class TestFetchFilesUsesTierLimit:
    """`_fetch_files_for_verification_async_with_metadata` must accept a
    `tier` and propagate it down to per-file fetches."""

    @pytest.mark.asyncio
    async def test_reasoning_tier_passes_50k_to_per_file_fetcher(self):
        from llm_council.verification import file_ops as api

        captured_limits: list[int] = []

        async def fake_fetch(snapshot_id, file_path, max_file_chars=None):
            captured_limits.append(max_file_chars)
            return "stub-content", False

        async def fake_expand(snapshot_id, target_paths):
            return list(target_paths), False, [], []

        with (
            patch.object(api, "_fetch_file_at_commit_async", side_effect=fake_fetch),
            patch.object(api, "_expand_target_paths", side_effect=fake_expand),
            patch.object(
                api,
                "_get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
        ):
            await api._fetch_files_for_verification_async_with_metadata(
                "HEAD", ["docs/big.md"], tier="reasoning"
            )

        assert captured_limits, "fetcher should have been called at least once"
        assert all(
            limit == 50_000 for limit in captured_limits
        ), f"reasoning tier should pass max_file_chars=50000; got {captured_limits}"

    @pytest.mark.asyncio
    async def test_quick_tier_passes_15k_to_per_file_fetcher(self):
        from llm_council.verification import file_ops as api

        captured_limits: list[int] = []

        async def fake_fetch(snapshot_id, file_path, max_file_chars=None):
            captured_limits.append(max_file_chars)
            return "stub", False

        async def fake_expand(snapshot_id, target_paths):
            return list(target_paths), False, [], []

        with (
            patch.object(api, "_fetch_file_at_commit_async", side_effect=fake_fetch),
            patch.object(api, "_expand_target_paths", side_effect=fake_expand),
            patch.object(
                api,
                "_get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
        ):
            await api._fetch_files_for_verification_async_with_metadata(
                "HEAD", ["docs/small.md"], tier="quick"
            )

        assert captured_limits == [15_000]


class TestBatchBudgetDoesNotOvershoot:
    """#584: the per-batch check ran BEFORE adding a file's content, so a
    single file up to the full per-file budget could push `total_chars` well
    past `per_batch_budget` before the *next* file's check caught it —
    overshooting by up to one whole per-file budget's worth of characters."""

    @pytest.mark.asyncio
    async def test_second_large_file_is_omitted_not_overshot(self):
        from llm_council.verification import file_ops as api

        # reasoning tier: per-file and per-batch budget are both 50_000.
        big = "y" * 40_000

        async def fake_fetch(snapshot_id, file_path, max_file_chars=None):
            return big, False

        async def fake_expand(snapshot_id, target_paths):
            return list(target_paths), False, [], []

        with (
            patch.object(api, "_fetch_file_at_commit_async", side_effect=fake_fetch),
            patch.object(api, "_expand_target_paths", side_effect=fake_expand),
            patch.object(
                api,
                "_get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
        ):
            content, metadata = await api._fetch_files_for_verification_async_with_metadata(
                "HEAD", ["docs/a.md", "docs/b.md"], tier="reasoning"
            )

        assert "docs/a.md" in content
        assert "docs/b.md" not in content, (
            "a second 40K file must be omitted, not appended past the 50K "
            "batch budget — including it would overshoot to ~80K chars"
        )
        assert "omitted" in content

    @pytest.mark.asyncio
    async def test_first_file_is_never_dropped_even_if_its_own_truncation_marker_overshoots(
        self,
    ):
        """A council review of PR #586 caught a regression the overshoot fix
        above introduced: `_fetch_file_at_commit_async` appends a truncation
        marker AFTER clamping to the limit (`content[:limit] + "...marker"`),
        so a truncated file's returned length is slightly ABOVE
        `per_file_budget`, not equal to it. Since `per_file_budget ==
        per_batch_budget`, checking `total_chars + len(content) >
        per_batch_budget` unconditionally — even at `total_chars == 0` —
        would drop the very first file entirely instead of including it
        truncated. CLAUDE.md documents "reasoning/high can read a full 50K
        file" as a guarantee; the first file must always be included."""
        from llm_council.verification import file_ops as api

        limit = 50_000
        # Exactly what _fetch_file_at_commit_async returns for a truncated file:
        # content clamped to `limit`, PLUS a marker that pushes length over it.
        truncated_content = ("y" * limit) + (
            f"\n\n... [truncated, original file larger than {limit} chars]"
        )
        assert len(truncated_content) > limit, "sanity: marker must push length over the limit"

        async def fake_fetch(snapshot_id, file_path, max_file_chars=None):
            return truncated_content, True

        async def fake_expand(snapshot_id, target_paths):
            return list(target_paths), False, [], []

        with (
            patch.object(api, "_fetch_file_at_commit_async", side_effect=fake_fetch),
            patch.object(api, "_expand_target_paths", side_effect=fake_expand),
            patch.object(
                api,
                "_get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
        ):
            content, metadata = await api._fetch_files_for_verification_async_with_metadata(
                "HEAD", ["docs/huge.md"], tier="reasoning"
            )

        assert "docs/huge.md" in content, (
            "the first file must always be included, even if its own "
            "truncation marker makes it slightly exceed the batch budget"
        )


# ---------------------------------------------------------------------------
# expansion_warnings plumbing
# ---------------------------------------------------------------------------


class TestPerFileTruncationSurfacesAsWarning:
    """When a file is clamped, the metadata dict must carry a warning
    naming the file and the limit. Today this signal is dropped on the
    floor."""

    @pytest.mark.asyncio
    async def test_truncation_emits_expansion_warning(self):
        from llm_council.verification import file_ops as api

        async def fake_fetch(snapshot_id, file_path, max_file_chars=None):
            # Simulate a clamped fetch — the truncation flag is on.
            return ("content..." + "[truncated]"), True

        async def fake_expand(snapshot_id, target_paths):
            return list(target_paths), False, [], []

        with (
            patch.object(api, "_fetch_file_at_commit_async", side_effect=fake_fetch),
            patch.object(api, "_expand_target_paths", side_effect=fake_expand),
            patch.object(
                api,
                "_get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
        ):
            _, metadata = await api._fetch_files_for_verification_async_with_metadata(
                "HEAD", ["docs/huge.md"], tier="reasoning"
            )

        warnings = metadata.get("expansion_warnings") or []
        text = " | ".join(str(w) for w in warnings).lower()
        assert (
            "docs/huge.md" in text
        ), f"expected a warning mentioning the truncated file; got {warnings!r}"
        assert (
            "truncat" in text or "clamp" in text or "exceed" in text
        ), f"warning text should indicate truncation; got {warnings!r}"

    @pytest.mark.asyncio
    async def test_no_truncation_no_warning(self):
        from llm_council.verification import file_ops as api

        async def fake_fetch(snapshot_id, file_path, max_file_chars=None):
            return "small", False

        async def fake_expand(snapshot_id, target_paths):
            return list(target_paths), False, [], []

        with (
            patch.object(api, "_fetch_file_at_commit_async", side_effect=fake_fetch),
            patch.object(api, "_expand_target_paths", side_effect=fake_expand),
            patch.object(
                api,
                "_get_git_root_async",
                new_callable=AsyncMock,
                return_value="/mock/root",
            ),
        ):
            _, metadata = await api._fetch_files_for_verification_async_with_metadata(
                "HEAD", ["docs/small.md"], tier="reasoning"
            )

        warnings = metadata.get("expansion_warnings") or []
        joined = " ".join(str(w).lower() for w in warnings)
        assert (
            "truncat" not in joined
        ), f"no file was truncated; warnings should not mention truncation: {warnings!r}"


# ---------------------------------------------------------------------------
# _build_verification_prompt must pass tier down
# ---------------------------------------------------------------------------


class TestBuildPromptPropagatesTier:
    """Today `_build_verification_prompt` accepts a `tier` argument but
    doesn't pass it to the file fetcher, so the per-file cap defaults
    silently."""

    @pytest.mark.asyncio
    async def test_build_prompt_passes_tier_to_fetcher(self):
        from llm_council.verification import api

        captured = {}

        async def fake_fetch_with_metadata(snapshot_id, target_paths, tier="balanced"):
            captured["tier"] = tier
            return (
                "### docs/x.md\n```\nstub\n```",
                {
                    "expanded_paths": list(target_paths or []),
                    "paths_truncated": False,
                    "expansion_warnings": [],
                },
            )

        with patch.object(
            api,
            "_fetch_files_for_verification_async_with_metadata",
            side_effect=fake_fetch_with_metadata,
        ):
            await api._build_verification_prompt(
                snapshot_id="HEAD",
                target_paths=["docs/x.md"],
                rubric_focus=None,
                evidence=None,
                tier="reasoning",
            )

        assert (
            captured.get("tier") == "reasoning"
        ), f"build_verification_prompt must pass tier to the fetcher; got {captured}"


# ---------------------------------------------------------------------------
# render_info["expansion"] carries per-file truncation forward
# ---------------------------------------------------------------------------


class TestBuilderRenderInfoCarriesTruncation:
    """The prompt builder must expose per-file truncation in its render_info
    so the pipeline can copy it onto VerifyResponse.expansion_warnings.
    The pipeline already does `expansion.get("expansion_warnings")` on line
    1967 — this test guards the upstream side of that wire."""

    @pytest.mark.asyncio
    async def test_render_info_expansion_includes_truncation_warning(self):
        from llm_council.verification import api

        warning_substr = "docs/big.md"

        async def fake_fetch_with_metadata(snapshot_id, target_paths, tier="balanced"):
            return (
                "### docs/big.md\n```\nstub\n```",
                {
                    "expanded_paths": list(target_paths or []),
                    "paths_truncated": False,
                    "expansion_warnings": [f"file '{warning_substr}' truncated at 50000 chars"],
                },
            )

        with patch.object(
            api,
            "_fetch_files_for_verification_async_with_metadata",
            side_effect=fake_fetch_with_metadata,
        ):
            _, render_info = await api._build_verification_prompt(
                snapshot_id="HEAD",
                target_paths=["docs/big.md"],
                rubric_focus=None,
                evidence=None,
                tier="reasoning",
            )

        expansion = render_info.get("expansion") or {}
        warnings = expansion.get("expansion_warnings") or []
        joined = " ".join(str(w) for w in warnings)
        assert warning_substr in joined, (
            f"render_info['expansion']['expansion_warnings'] must carry "
            f"per-file truncation forward; got {warnings!r}"
        )
