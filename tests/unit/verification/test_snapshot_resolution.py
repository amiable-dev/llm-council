"""Tests for snapshot resolution failure handling (issue #340).

TDD Red Phase: these fail until api.py exposes:
- SnapshotResolutionError raised when target_paths resolves to zero files
- expansion metadata threaded into _build_verification_prompt's render_info
- git stderr logged at WARN instead of swallowed

Background: v0.24.38 and earlier silently returned ~916-char prompts when
target_paths could not be resolved at the given snapshot_id (e.g. commit
not present in the daemon's local checkout, fetch race after push, etc).
The council "reviewed" boilerplate and returned UNCLEAR; skill rules said
do-not-retry, making this invisible to callers.
"""

import logging
import pytest
from unittest.mock import AsyncMock, patch


class TestSnapshotResolutionError:
    """The new exception type and where it gets raised."""

    def test_is_exception_subclass(self):
        from llm_council.verification.api import SnapshotResolutionError

        assert issubclass(SnapshotResolutionError, Exception)

    def test_carries_snapshot_id_paths_warnings(self):
        from llm_council.verification.api import SnapshotResolutionError

        err = SnapshotResolutionError(
            snapshot_id="deadbeef1234567",
            unresolved_paths=["a.rs", "b.rs"],
            expansion_warnings=["Path not found or invalid: a.rs"],
        )
        assert err.snapshot_id == "deadbeef1234567"
        assert err.unresolved_paths == ["a.rs", "b.rs"]
        assert err.expansion_warnings == ["Path not found or invalid: a.rs"]
        # Message should mention the snapshot + first unresolved path for
        # human-readable logs.
        assert "deadbeef1234567" in str(err)


class TestBuilderRaisesOnEmptyResolution:
    """_build_verification_prompt must hard-fail rather than silently send
    a boilerplate-only prompt when target_paths is non-empty but expansion
    returns no files."""

    @pytest.mark.asyncio
    async def test_raises_when_target_paths_all_unresolved(self):
        from llm_council.verification.api import (
            SnapshotResolutionError,
            _build_verification_prompt,
        )

        # Mock the expansion to simulate the daemon-doesnt-have-this-SHA case.
        with patch(
            "llm_council.verification.api._fetch_files_for_verification_async_with_metadata",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = (
                "[No files specified and could not determine changed files]",
                {
                    "expanded_paths": [],
                    "paths_truncated": False,
                    "expansion_warnings": [
                        "Path not found or invalid: tests/route_config_test.rs",
                        "Path not found or invalid: tests/route_validation_test.rs",
                    ],
                },
            )

            with pytest.raises(SnapshotResolutionError) as exc_info:
                await _build_verification_prompt(
                    snapshot_id="b50f2b3d",
                    target_paths=[
                        "tests/route_config_test.rs",
                        "tests/route_validation_test.rs",
                    ],
                )

            err = exc_info.value
            assert err.snapshot_id == "b50f2b3d"
            assert err.unresolved_paths == [
                "tests/route_config_test.rs",
                "tests/route_validation_test.rs",
            ]
            assert any("Path not found" in w for w in err.expansion_warnings)

    @pytest.mark.asyncio
    async def test_does_not_raise_when_target_paths_is_none(self):
        """Snapshot-wide verification (no target_paths) must continue to
        work even if no files come back — the old fallback behavior is
        valid for that case (callers explicitly chose to verify whatever
        the snapshot touches)."""
        from llm_council.verification.api import _build_verification_prompt

        with patch(
            "llm_council.verification.api._fetch_files_for_verification_async_with_metadata",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = (
                "[No files specified and could not determine changed files]",
                {
                    "expanded_paths": [],
                    "paths_truncated": False,
                    "expansion_warnings": [],
                },
            )

            # Should not raise.
            prompt, render_info = await _build_verification_prompt(
                snapshot_id="b50f2b3d",
                target_paths=None,
            )
            assert isinstance(prompt, str)

    @pytest.mark.asyncio
    async def test_does_not_raise_on_partial_resolution(self):
        """Partial resolution (some paths resolve, some don't) yields a
        normal verdict path — warnings surface on the response, not via
        exception."""
        from llm_council.verification.api import _build_verification_prompt

        with patch(
            "llm_council.verification.api._fetch_files_for_verification_async_with_metadata",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = (
                "### a.rs\n```\nfn main() {}\n```",
                {
                    "expanded_paths": ["a.rs"],
                    "paths_truncated": False,
                    "expansion_warnings": ["Path not found or invalid: b.rs"],
                },
            )

            prompt, render_info = await _build_verification_prompt(
                snapshot_id="abc1234",
                target_paths=["a.rs", "b.rs"],
            )
            # Partial resolution: must not raise.
            assert "fn main()" in prompt

    @pytest.mark.asyncio
    async def test_render_info_carries_expansion_metadata(self):
        """The builder must expose expansion metadata to the pipeline so
        it can be surfaced on VerifyResponse."""
        from llm_council.verification.api import _build_verification_prompt

        with patch(
            "llm_council.verification.api._fetch_files_for_verification_async_with_metadata",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = (
                "### a.rs\n```\nx\n```",
                {
                    "expanded_paths": ["a.rs"],
                    "paths_truncated": False,
                    "expansion_warnings": ["Skipped non-text file: b.bin"],
                },
            )

            _prompt, render_info = await _build_verification_prompt(
                snapshot_id="abc1234",
                target_paths=["a.rs", "b.bin"],
            )

            assert "expansion" in render_info, (
                "render_info must carry the expansion metadata dict "
                "so _run_verification_pipeline can copy it to the response"
            )
            exp = render_info["expansion"]
            assert exp["expanded_paths"] == ["a.rs"]
            assert exp["paths_truncated"] is False
            assert exp["expansion_warnings"] == ["Skipped non-text file: b.bin"]


class TestGitStderrCaptured:
    """_get_git_object_type and _git_ls_tree_z_name_only must log git's
    stderr at WARN instead of swallowing it silently."""

    @pytest.mark.asyncio
    async def test_get_object_type_logs_stderr_for_unknown_sha(self, caplog):
        from llm_council.verification.api import _get_git_object_type

        # Use a SHA that definitely does not exist in any git repo (all f's
        # at 40 chars is technically valid hex but vanishingly unlikely).
        impossible_sha = "f" * 40
        with caplog.at_level(logging.WARNING, logger="llm_council.verification.api"):
            result = await _get_git_object_type(impossible_sha, "pyproject.toml")

        assert result is None
        # The git stderr should now be captured at WARN with the snapshot
        # and path in the message.
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warn_records, (
            "Expected at least one WARNING record when git cat-file fails; "
            "stderr is being silently swallowed"
        )
        # At least one warning should reference the snapshot ID or path so
        # operators can correlate.
        joined = " ".join(r.getMessage() for r in warn_records)
        assert impossible_sha[:7] in joined or "pyproject.toml" in joined

    @pytest.mark.asyncio
    async def test_ls_tree_logs_stderr_for_unknown_sha(self, caplog):
        from llm_council.verification.api import _git_ls_tree_z_name_only

        impossible_sha = "f" * 40
        with caplog.at_level(logging.WARNING, logger="llm_council.verification.api"):
            result = await _git_ls_tree_z_name_only(impossible_sha, "src")

        assert result == []
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warn_records, "Expected at least one WARNING record when git ls-tree fails"


class TestPipelineSurfacesExpansionMetadata:
    """The verify response must expose expansion metadata when partial
    resolution succeeds. Operators need this paper trail."""

    @pytest.mark.asyncio
    async def test_response_includes_expansion_warnings_on_partial(self):
        """Partial resolution: response carries the warnings list."""
        from unittest.mock import MagicMock
        from llm_council.verification.api import VerifyRequest, run_verification

        request = VerifyRequest(
            snapshot_id="abc1234",
            target_paths=["a.rs", "b.rs"],
        )

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses_with_status"
            ) as mock_stage1,
            patch("llm_council.verification.api.stage2_collect_rankings") as mock_stage2,
            patch("llm_council.verification.api.stage3_synthesize_final") as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
            patch("llm_council.verification.api.build_verification_result") as mock_build,
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=(
                    "### a.rs\n```\nfn main() {}\n```",
                    {
                        "kept": [],
                        "warnings": [],
                        "chars_rendered": 0,
                        "chars_submitted": 0,
                        "expansion": {
                            "expanded_paths": ["a.rs"],
                            "paths_truncated": False,
                            "expansion_warnings": ["Path not found or invalid: b.rs"],
                        },
                    },
                ),
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            mock_stage1.return_value = (
                [{"model": "test", "content": "ok"}],
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                {},
            )
            mock_stage2.return_value = ([], {}, {})
            mock_stage3.return_value = ("synthesis", {}, None)
            mock_agg.return_value = []
            mock_build.return_value = {
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "OK",
            }

            store = MagicMock()
            store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, store)

            assert result["expanded_paths"] == ["a.rs"]
            assert result["paths_truncated"] is False
            assert result["expansion_warnings"] == ["Path not found or invalid: b.rs"]

    @pytest.mark.asyncio
    async def test_run_verification_propagates_resolution_error(self):
        """run_verification does not catch SnapshotResolutionError —
        verify_endpoint and the MCP wrapper map it to a structured error."""
        from unittest.mock import MagicMock
        from llm_council.verification.api import (
            SnapshotResolutionError,
            VerifyRequest,
            run_verification,
        )

        request = VerifyRequest(
            snapshot_id="b50f2b3d",
            target_paths=["a.rs"],
        )

        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                side_effect=SnapshotResolutionError(
                    snapshot_id="b50f2b3d",
                    unresolved_paths=["a.rs"],
                    expansion_warnings=["Path not found or invalid: a.rs"],
                ),
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)

            store = MagicMock()
            store.create_verification_directory.return_value = "/tmp/test"

            with pytest.raises(SnapshotResolutionError):
                await run_verification(request, store)
