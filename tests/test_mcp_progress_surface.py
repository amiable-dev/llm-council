"""ADR-046 P3: MCP progress surface (#411).

Per-reviewer stage-2 progress reaches the on_progress channel (which the MCP
server bridges to ctx.report_progress) — wired ONLY when a progress consumer
exists, keeping consumer-less runs byte-identical.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestStage2ProgressWiring:
    @pytest.mark.asyncio
    async def test_stage2_receives_progress_when_consumer_exists(self, monkeypatch):
        from llm_council import council

        messages = []

        async def on_progress(step, total, msg):
            messages.append(msg)

        async def fake_stage1(*a, **kw):
            return (
                [{"model": "m/a", "response": "A"}, {"model": "m/b", "response": "B"}],
                {},
                {
                    "m/a": {"status": "ok", "response": "A"},
                    "m/b": {"status": "ok", "response": "B"},
                },
            )

        with (
            patch.object(
                council, "stage1_collect_responses_with_status", side_effect=fake_stage1
            ),
            patch.object(council, "stage2_collect_rankings", new_callable=AsyncMock) as s2,
            patch.object(council, "stage3_synthesize_final", new_callable=AsyncMock) as s3,
            patch.object(council, "stage1_5_normalize_styles", new_callable=AsyncMock) as s15,
        ):
            s15.return_value = (
                [
                    {"model": "m/a", "response": "A"},
                    {"model": "m/b", "response": "B"},
                ],
                {},
            )
            s2.return_value = ([], {}, {})
            s3.return_value = ({"model": "c", "response": "s"}, {}, None)
            await council.run_council_with_fallback(
                "q", bypass_cache=True, on_progress=on_progress
            )
            assert s2.await_count == 1
            stage2_progress = s2.call_args.kwargs.get("on_progress")
            assert stage2_progress is not None
            # The wrapper must actually deliver to the consumer, prefixed and
            # offset into the overall step budget.
            await stage2_progress(1, 2, "m/a reviewed (1/2)")
            assert any("Stage 2: m/a reviewed (1/2)" in m for m in messages)

    @pytest.mark.asyncio
    async def test_stage2_gets_no_progress_without_consumer(self):
        # Byte-identical guard: no on_progress consumer => stage2 must NOT be
        # flipped onto the incremental path by a progress wrapper.
        from llm_council import council

        async def fake_stage1(*a, **kw):
            return (
                [{"model": "m/a", "response": "A"}],
                {},
                {"m/a": {"status": "ok", "response": "A"}},
            )

        with (
            patch.object(
                council, "stage1_collect_responses_with_status", side_effect=fake_stage1
            ),
            patch.object(council, "stage2_collect_rankings", new_callable=AsyncMock) as s2,
            patch.object(council, "stage3_synthesize_final", new_callable=AsyncMock) as s3,
            patch.object(council, "stage1_5_normalize_styles", new_callable=AsyncMock) as s15,
        ):
            s15.return_value = ([{"model": "m/a", "response": "A"}], {})
            s2.return_value = ([], {}, {})
            s3.return_value = ({"model": "c", "response": "s"}, {}, None)
            await council.run_council_with_fallback("q", bypass_cache=True)
            assert s2.await_count == 1
            assert s2.call_args.kwargs.get("on_progress") is None


class TestToolDescriptions:
    def test_consult_council_documents_progress(self):
        pytest.importorskip("mcp")
        from llm_council import mcp_server

        doc = mcp_server.consult_council.__doc__ or ""
        assert "progress notifications" in doc.lower()

    def test_verify_documents_progress(self):
        pytest.importorskip("mcp")
        from llm_council import mcp_server

        doc = mcp_server.verify.__doc__ or ""
        assert "progress notifications" in doc.lower()
