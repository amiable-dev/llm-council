"""#686: verify's chairman gets the rest of the global deadline.

Stage 3 was ``min(remaining, per_model)``: 45s on balanced, 90s on high. The
configured chairman averages ~204s, so a deliberation that had completed was
reported as ``unclear(infra_failure)``. The per-model cap exists to bound the
slowest of N parallel members in stages 1 and 2; stage 3 is one call, and the
global deadline (``tier deadline × VERIFICATION_TIMEOUT_MULTIPLIER``) already
bounds it, so it now gets everything left less a short tail
(``_stage3_tail_reserve``), which lets its own timeout fire before the outer
``asyncio.wait_for`` does.

The pipeline's clock is faked, so the budget arithmetic is asserted exactly —
including after stages 1-2 have consumed part of the deadline, which a
constant "full global budget" would get wrong.
"""

import asyncio
import time as real_time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.tier_contract import create_tier_contract
from llm_council.verification.api import VERIFICATION_TIMEOUT_MULTIPLIER
from llm_council.verification.pipeline import _stage3_tail_reserve

API = "llm_council.verification.api"
PIPE = "llm_council.verification.pipeline"


class _Clock:
    """Stands in for the pipeline's ``time`` module: real monotonic + offset."""

    def __init__(self):
        self.offset = 0.0

    def monotonic(self):
        return real_time.monotonic() + self.offset


def _global_s(tier: str) -> float:
    return create_tier_contract(tier).deadline_ms / 1000 * VERIFICATION_TIMEOUT_MULTIPLIER


async def _run(tier: str, *, stage2_elapsed: float = 0.0, stage3=None, clock=None):
    """Run verify with stubbed stages; return (stage3 mock, result)."""
    from llm_council.verification.api import VerifyRequest, run_verification

    clock = clock or _Clock()
    prompt = ("p", {"kept": [], "warnings": [], "chars_rendered": 0, "chars_submitted": 0})
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    async def stage2(*args, **kwargs):
        clock.offset += stage2_elapsed  # stages 1-2 consumed this much
        return ([], {}, {})

    with (
        patch(f"{PIPE}.time", clock),
        patch(f"{PIPE}.stage1_collect_responses_with_status") as s1,
        patch(f"{PIPE}.stage2_collect_rankings", side_effect=stage2),
        patch(f"{PIPE}.stage3_synthesize_final", **(stage3 or {})) as s3,
        patch(f"{PIPE}.calculate_aggregate_rankings", return_value=[]),
        patch(f"{PIPE}.build_verification_result") as build,
        patch(f"{API}.VerificationContextManager") as ctx,
        patch(f"{API}._build_verification_prompt", new_callable=AsyncMock, return_value=prompt),
    ):
        ctx.return_value.__enter__ = MagicMock(return_value=MagicMock(context_id="c"))
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        s1.return_value = ([{"model": "m", "response": "ok"}], usage, {})
        if not stage3:
            s3.return_value = ({"model": "m", "response": "s"}, {}, None)
        build.return_value = {
            "verdict": "pass",
            "confidence": 0.9,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "OK",
        }
        store = MagicMock()
        store.create_verification_directory.return_value = "/tmp/test"
        result = await run_verification(VerifyRequest(snapshot_id="abc1234", tier=tier), store)
        return s3, result


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["balanced", "high"])
async def test_the_chairman_is_not_capped_at_the_per_model_budget(tier):
    per_model_s = create_tier_contract(tier).per_model_timeout_ms / 1000
    s3, _ = await _run(tier)
    timeout = s3.call_args.kwargs["timeout"]

    assert timeout > per_model_s  # the old cap: exactly per_model_s
    expected = _global_s(tier) - _stage3_tail_reserve(_global_s(tier))
    assert timeout == pytest.approx(expected, abs=1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,elapsed", [("balanced", 100.0), ("high", 250.0)])
async def test_the_chairman_gets_what_stages_one_and_two_left(tier, elapsed):
    s3, _ = await _run(tier, stage2_elapsed=elapsed)
    timeout = s3.call_args.kwargs["timeout"]

    left = _global_s(tier) - elapsed
    assert timeout == pytest.approx(left - _stage3_tail_reserve(left), abs=1.0)


def test_the_tail_is_small_and_proportional():
    assert _stage3_tail_reserve(360.0) == 5.0
    assert _stage3_tail_reserve(20.0) == pytest.approx(1.0)
    assert _stage3_tail_reserve(0.0) == 0.0


@pytest.mark.asyncio
async def test_the_global_deadline_still_bounds_a_hanging_chairman():
    """Removing the per-model cap is safe only because the outer wait_for
    bounds the run. A chairman that never returns must still end the run at
    the global deadline, with stages 1-2 salvaged."""

    async def hang(*args, **kwargs):
        await asyncio.sleep(3600)

    started = real_time.monotonic()
    with patch(f"{API}.VERIFICATION_TIMEOUT_MULTIPLIER", 0.005):  # quick: 0.3s
        _, result = await _run("quick", stage3={"side_effect": hang})

    assert real_time.monotonic() - started < 10
    assert result["timeout_fired"] is True
    assert "stage2" in result["completed_stages"]
    assert "stage3" not in result["completed_stages"]
