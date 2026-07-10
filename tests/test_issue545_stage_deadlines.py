"""Regression tests for #545 — per-stage / per-model wall-clock deadlines.

ADR-040's waterfall computed `stage1_budget = remaining * 0.50` and then used it
*only* to derive a per-model `timeout=` value. That value was handed to
`httpx.AsyncClient(timeout=...)`, which sets four SEPARATE per-operation
timeouts (connect / read / write / pool) — none of which bounds total elapsed
time, and httpx exposes no total-wall-clock option. Nothing anywhere wrapped the
model call in `asyncio.wait_for`.

Consequence, observed in production (`verification_id` 2bf8d8c8, tier=high,
per_model=90s): stage1 ran 233.7s, stage2 126.3s, and stage3 received **1.0s** of
a 360s global deadline (`budget_utilization: 1.003`). The chairman timed out at
1.0s and the run returned `unclear(infra_failure)` — a fully billed run with no
verdict.

The pre-existing `TestWaterfallTimeBudgeting` asserts the *arithmetic* (what
number is passed as `timeout=`), never the *enforcement* (that elapsed time is
actually bounded). That is exactly how this shipped green.
"""

import asyncio
import time

import pytest


class TestQueryModelBoundsWallClock:
    """`timeout=` must mean elapsed seconds, not an httpx per-operation timeout."""

    @staticmethod
    def _install_stalling_transport(monkeypatch):
        """Substitute the httpx client so httpx's own per-operation timeouts cannot fire.

        What is left under test is whether the caller enforces its own wall-clock
        bound. Pre-fix it does not, and the call runs for the transport's full
        stall duration.
        """
        from llm_council import openrouter

        class _StallingClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                # Simulates a provider that keeps the socket fed (streamed tokens
                # or OpenRouter processing heartbeats) so no read timeout fires.
                await asyncio.sleep(5.0)
                raise AssertionError("should have been cancelled by the deadline")

        monkeypatch.setattr(openrouter.httpx, "AsyncClient", _StallingClient)
        monkeypatch.setattr(openrouter, "_get_openrouter_api_key", lambda: "test-key")
        return openrouter

    @pytest.mark.asyncio
    async def test_query_model_with_status_times_out_at_the_wall_clock_bound(self, monkeypatch):
        """`query_model_with_status` owns the only HTTP call; `timeout=` must bound elapsed."""
        openrouter = self._install_stalling_transport(monkeypatch)

        start = time.monotonic()
        result = await asyncio.wait_for(
            openrouter.query_model_with_status(
                "test/model", [{"role": "user", "content": "hi"}], timeout=0.5
            ),
            timeout=3.0,  # test-harness guard; the fix must trip well before this
        )
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, (
            f"query_model_with_status(timeout=0.5) took {elapsed:.2f}s — `timeout=` "
            "is not a wall-clock bound. httpx's connect/read/write/pool timeouts do "
            "not bound total elapsed time."
        )
        assert result["status"] == openrouter.STATUS_TIMEOUT

    @pytest.mark.asyncio
    async def test_query_model_degrades_to_none_within_the_bound(self, monkeypatch):
        """`query_model` keeps its documented None-on-failure contract, now promptly."""
        openrouter = self._install_stalling_transport(monkeypatch)

        start = time.monotonic()
        result = await asyncio.wait_for(
            openrouter.query_model("test/model", [{"role": "user", "content": "hi"}], timeout=0.5),
            timeout=3.0,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"query_model(timeout=0.5) took {elapsed:.2f}s"
        assert result is None  # graceful degradation (CLAUDE.md: None on failure)

    @pytest.mark.asyncio
    async def test_outer_cancellation_still_propagates(self, monkeypatch):
        """The ADR-040 global deadline must not be swallowed as a per-model timeout.

        `asyncio.wait_for` re-raises `CancelledError`, which derives from
        `BaseException` and so is not caught by the `except Exception` fallback.
        """
        openrouter = self._install_stalling_transport(monkeypatch)

        task = asyncio.create_task(
            openrouter.query_model_with_status(
                "test/model", [{"role": "user", "content": "hi"}], timeout=30.0
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


class TestStage3BudgetFloor:
    """Stage 3 must never be starved to a uselessly small, yet billed, budget."""

    def test_stage3_min_budget_constant_exists(self):
        from llm_council.verification import constants

        assert hasattr(constants, "STAGE3_MIN_BUDGET_SECONDS"), (
            "no reserved floor for stage 3 — stages 1+2 can consume the whole "
            "global deadline (observed: stage3 got 1.0s of 360s)"
        )
        assert constants.STAGE3_MIN_BUDGET_SECONDS >= 15.0

    def test_stage1_budget_reserves_the_stage3_floor(self):
        """Stage 1's slice is taken from (remaining - stage3 reserve), not `remaining`."""
        from llm_council.verification.api import _stage_budget
        from llm_council.verification.constants import STAGE3_MIN_BUDGET_SECONDS

        # tier=high: 360s global deadline, nothing consumed yet. 15% of 360 = 54,
        # so the reserve saturates at the 30s cap.
        budget = _stage_budget(remaining=360.0, fraction=0.50)
        expected = (360.0 - STAGE3_MIN_BUDGET_SECONDS) * 0.50

        assert budget == pytest.approx(expected), (
            f"stage1 budget {budget} ignores the stage-3 floor; expected {expected}"
        )

    def test_reserve_is_proportional_so_quick_tier_is_not_starved(self):
        """A flat 30s reserve would eat half of `quick`'s 60s deadline (#545 review).

        Regression guard for test_verify_tier_support::test_run_verification_uses_tier_timeout,
        which caught exactly this: stage 1 must still reach quick's 20s per-model cap.
        """
        from llm_council.verification.api import _stage_budget, _stage3_reserve

        assert _stage3_reserve(60.0) == pytest.approx(9.0)  # 15% of 60, under the 30s cap
        assert _stage3_reserve(360.0) == pytest.approx(30.0)  # capped

        quick_stage1 = _stage_budget(remaining=60.0, fraction=0.50)
        assert min(quick_stage1, 20.0) == pytest.approx(20.0), (
            "quick tier stage 1 no longer reaches its 20s per-model cap"
        )

    def test_stage_budget_never_negative_when_deadline_already_blown(self):
        from llm_council.verification.api import _stage_budget

        assert _stage_budget(remaining=1.0, fraction=0.50) >= 1.0
