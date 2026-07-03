"""#444: consult_council facade — ship the API the docs promised (docs-as-spec).

The published quickstart documents `from llm_council import consult_council`
returning an object with `.synthesis`; that API never existed. These tests
pin the exact documented shape.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestDocumentedQuickstartShape:
    @pytest.mark.asyncio
    async def test_exact_quickstart_snippet_runs(self):
        # Verbatim shape from docs/getting-started/quickstart.md
        from llm_council import consult_council

        fake = {
            "synthesis": "the answer",
            "metadata": {"status": "complete"},
            "model_responses": {"m/a": {"status": "ok"}},
        }
        with patch(
            "llm_council.facade.run_council_with_fallback",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            result = await consult_council(
                "What are the best practices for error handling in Python?",
                confidence="balanced",
            )
        assert result.synthesis == "the answer"
        assert result.metadata["status"] == "complete"
        assert result.model_responses["m/a"]["status"] == "ok"
        assert result.raw is fake

    @pytest.mark.asyncio
    async def test_confidence_maps_to_tier_contract(self):
        from llm_council import consult_council

        with patch(
            "llm_council.facade.run_council_with_fallback",
            new_callable=AsyncMock,
            return_value={"synthesis": "", "metadata": {}, "model_responses": {}},
        ) as run:
            await consult_council("q", confidence="quick")
        kwargs = run.call_args.kwargs
        assert kwargs["tier_contract"].tier == "quick"
        # Timeouts derived from the tier contract (MCP-server parity).
        assert kwargs["synthesis_deadline"] == pytest.approx(
            kwargs["tier_contract"].deadline_ms / 1000
        )
        assert kwargs["per_model_timeout"] == pytest.approx(
            kwargs["tier_contract"].per_model_timeout_ms / 1000
        )

    @pytest.mark.asyncio
    async def test_unknown_confidence_falls_back_to_high(self):
        # Same forgiving semantics as the MCP consult_council tool.
        from llm_council import consult_council

        with patch(
            "llm_council.facade.run_council_with_fallback",
            new_callable=AsyncMock,
            return_value={"synthesis": "", "metadata": {}, "model_responses": {}},
        ) as run:
            await consult_council("q", confidence="banana")
        assert run.call_args.kwargs["tier_contract"].tier == "high"

    @pytest.mark.asyncio
    async def test_verdict_type_and_dissent_pass_through(self):
        from llm_council import consult_council
        from llm_council.verdict import VerdictType

        with patch(
            "llm_council.facade.run_council_with_fallback",
            new_callable=AsyncMock,
            return_value={"synthesis": "", "metadata": {}, "model_responses": {}},
        ) as run:
            await consult_council(
                "q", verdict_type="binary", include_dissent=True, models=["m/a"]
            )
        kwargs = run.call_args.kwargs
        assert kwargs["verdict_type"] == VerdictType.BINARY
        assert kwargs["include_dissent"] is True
        assert kwargs["models"] == ["m/a"]

    def test_invalid_verdict_type_raises_clearly(self):
        import asyncio

        from llm_council import consult_council

        with pytest.raises(ValueError, match="verdict_type"):
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                consult_council("q", verdict_type="banana")
            )
