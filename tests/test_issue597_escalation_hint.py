"""#597: a starved verify should be retried UP a tier, never at the same or a
lower one.

A lower tier has a shorter global deadline, so re-running it during a slow
provider window starves the chairman harder. During the 2026-07-16 outage a
quick-tier retry timed out while a balanced run seven minutes later passed:
"latency recovered" was mostly 3x the deadline headroom. The timeout rationale
said "Consider using a faster tier", which is exactly backwards.

The response now carries a machine-readable ``retry_hint`` whenever the run
ran out of time (the global deadline fired, or the chairman call itself timed
out), and the human text says the same.
"""

import pytest

from llm_council.verification.escalation import TIER_LADDER, retry_hint


class TestTheHint:
    @pytest.mark.parametrize(
        "tier,up", [("quick", "balanced"), ("balanced", "high"), ("high", "reasoning")]
    )
    def test_a_global_timeout_suggests_the_next_tier_up(self, tier, up):
        hint = retry_hint(tier, unclear_reason="timeout", completed_stages=["stage1"])
        assert hint["action"] == "escalate_tier"
        assert hint["suggested_tier"] == up

    def test_synthesis_starved_when_peer_review_had_finished(self):
        hint = retry_hint(
            "balanced", unclear_reason="timeout", completed_stages=["stage1", "stage2"]
        )
        assert hint["reason"] == "synthesis_starved"

    def test_deadline_exhausted_when_peer_review_had_not(self):
        hint = retry_hint("quick", unclear_reason="timeout", completed_stages=["stage1"])
        assert hint["reason"] == "deadline_exhausted"

    def test_a_chairman_call_timeout_is_starvation_not_infra(self):
        """After #686 a stage-3 call timeout comes back infra_failure with
        error_status=timeout. Retrying the same tier is the wrong move."""
        hint = retry_hint(
            "balanced",
            unclear_reason="infra_failure",
            completed_stages=["stage1", "stage2", "stage3"],
            stage3_error_status="timeout",
        )
        assert hint["action"] == "escalate_tier"
        assert hint["suggested_tier"] == "high"
        assert hint["reason"] == "synthesis_starved"

    @pytest.mark.parametrize("status", ["auth_error", "rate_limited", "error", None])
    def test_a_real_infra_failure_gets_no_hint(self, status):
        assert (
            retry_hint(
                "balanced",
                unclear_reason="infra_failure",
                completed_stages=["stage1", "stage2", "stage3"],
                stage3_error_status=status,
            )
            is None
        )

    @pytest.mark.parametrize(
        "reason", ["low_confidence", "chairman_disabled", "incomplete_coverage", None]
    )
    def test_other_outcomes_get_no_hint(self, reason):
        assert retry_hint("balanced", unclear_reason=reason, completed_stages=[]) is None

    def test_the_top_tier_suggests_reducing_scope(self):
        hint = retry_hint("reasoning", unclear_reason="timeout", completed_stages=["stage1"])
        assert hint["action"] == "reduce_scope"
        assert hint["suggested_tier"] is None

    def test_an_unknown_tier_is_treated_as_not_escalatable(self):
        hint = retry_hint("frontier", unclear_reason="timeout", completed_stages=[])
        assert hint["action"] == "reduce_scope"

    def test_the_ladder_orders_tiers_by_deadline(self):
        from llm_council.tier_contract import create_tier_contract

        deadlines = [create_tier_contract(t).deadline_ms for t in TIER_LADDER]
        assert deadlines == sorted(deadlines)
        assert len(set(deadlines)) == len(deadlines)

    def test_the_message_never_suggests_a_faster_tier(self):
        for tier in TIER_LADDER:
            hint = retry_hint(tier, unclear_reason="timeout", completed_stages=[])
            assert "faster" not in hint["message"].lower()
            assert "same or a lower" in hint["message"]


class TestTheResponseCarriesIt:
    def test_the_response_model_has_the_field(self):
        from llm_council.verification.schemas import VerifyResponse

        assert "retry_hint" in VerifyResponse.model_fields

    def test_the_formatted_output_shows_the_hint(self):
        from llm_council.verification.formatting import format_verification_result

        hint = retry_hint(
            "balanced", unclear_reason="timeout", completed_stages=["stage1", "stage2"]
        )
        text = format_verification_result(
            {
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
                "unclear_reason": "timeout",
                "retry_hint": hint,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "",
            }
        )
        assert "| Next step | Retry at tier=high:" in text

    def test_the_formatted_output_shows_reduce_scope_at_the_top(self):
        from llm_council.verification.formatting import format_verification_result

        hint = retry_hint("reasoning", unclear_reason="timeout", completed_stages=[])
        text = format_verification_result(
            {
                "verdict": "unclear",
                "confidence": 0.0,
                "exit_code": 2,
                "unclear_reason": "timeout",
                "retry_hint": hint,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "",
            }
        )
        assert "top of the ladder. Reduce the scope" in text
        assert "Retry at tier=" not in text


def test_every_deadline_tier_is_on_the_ladder():
    """A new budget tier left off the ladder would silently get reduce_scope."""
    from llm_council.tier_contract import TIER_AGGREGATORS

    lifecycle_tiers = {"frontier"}
    assert set(TIER_AGGREGATORS) - lifecycle_tiers == set(TIER_LADDER)


def test_the_status_is_shared_with_the_provider_layer():
    from llm_council.openrouter import STATUS_TIMEOUT
    from llm_council.verification import escalation

    assert escalation._STAGE3_TIMEOUT_STATUS is STATUS_TIMEOUT


API = "llm_council.verification.api"
PIPE = "llm_council.verification.pipeline"


async def _verify(tier, *, stage3, verdict="pass", multiplier=None):
    import contextlib
    from unittest.mock import AsyncMock, MagicMock, patch

    from llm_council.verification.api import VerifyRequest, run_verification

    prompt = ("p", {"kept": [], "warnings": [], "chars_rendered": 0, "chars_submitted": 0})
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    with contextlib.ExitStack() as stack:
        enter = stack.enter_context
        s1 = enter(patch(f"{PIPE}.stage1_collect_responses_with_status"))
        enter(patch(f"{PIPE}.stage2_collect_rankings", return_value=([], {}, {})))
        enter(patch(f"{PIPE}.stage3_synthesize_final", **stage3))
        enter(patch(f"{PIPE}.calculate_aggregate_rankings", return_value=[]))
        build = enter(patch(f"{PIPE}.build_verification_result"))
        ctx = enter(patch(f"{API}.VerificationContextManager"))
        enter(
            patch(f"{API}._build_verification_prompt", new_callable=AsyncMock, return_value=prompt)
        )
        if multiplier is not None:
            enter(patch(f"{API}.VERIFICATION_TIMEOUT_MULTIPLIER", multiplier))
        ctx.return_value.__enter__ = MagicMock(return_value=MagicMock(context_id="c"))
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        s1.return_value = ([{"model": "m", "response": "ok"}], usage, {})
        build.return_value = {
            "verdict": verdict,
            "confidence": 0.5,
            "rubric_scores": {},
            "blocking_issues": [],
            "rationale": "r",
        }
        store = MagicMock()
        store.create_verification_directory.return_value = "/tmp/test"
        return await run_verification(VerifyRequest(snapshot_id="abc1234", tier=tier), store)


@pytest.mark.asyncio
class TestEndToEnd:
    async def test_a_global_timeout_carries_the_hint_and_honest_text(self):
        import asyncio

        async def hang(*a, **k):
            await asyncio.sleep(3600)

        result = await _verify("quick", stage3={"side_effect": hang}, multiplier=0.005)
        assert result["unclear_reason"] == "timeout"
        assert result["retry_hint"]["suggested_tier"] == "balanced"
        assert result["retry_hint"]["reason"] == "synthesis_starved"
        assert "faster tier" not in result["rationale"]
        assert "Retry at tier=balanced" in result["rationale"]

    async def test_a_screening_error_does_not_leak_the_cache_context(self, monkeypatch):
        """#724 review: the context was set before the try whose finally clears
        it, so an exception in screening leaked it into the next verify."""
        from llm_council import cache_context

        async def boom(**kwargs):
            raise RuntimeError("screen exploded")

        monkeypatch.setattr(f"{API}.screening_mode", lambda: "shadow")
        monkeypatch.setattr(f"{API}.evaluate_screen", boom)
        with pytest.raises(RuntimeError, match="screen exploded"):
            await _verify(
                "balanced", stage3={"return_value": ({"model": "m", "response": "ok"}, {}, None)}
            )
        assert cache_context.get_cache_context() is None

    async def test_a_chairman_call_timeout_carries_the_hint(self):
        stage3_result = {"model": "m", "response": "Error", "error_status": "timeout"}
        result = await _verify(
            "balanced",
            stage3={"return_value": (stage3_result, {}, None)},
            verdict="unclear",
        )
        assert result["unclear_reason"] == "infra_failure"
        assert result["retry_hint"]["action"] == "escalate_tier"
        assert result["retry_hint"]["suggested_tier"] == "high"

    async def test_a_timeout_at_the_top_tier_says_reduce_scope_not_escalate(self):
        """The rationale must agree with the hint: there is no tier above
        reasoning, so telling the operator to go higher would be #597 again."""
        import asyncio

        async def hang(*a, **k):
            await asyncio.sleep(3600)

        result = await _verify("reasoning", stage3={"side_effect": hang}, multiplier=0.0005)
        assert result["retry_hint"]["action"] == "reduce_scope"
        assert "higher tier" not in result["rationale"]
        assert "Retry at tier=" not in result["rationale"]
        assert "Reduce the scope" in result["rationale"]

    async def test_a_clean_pass_has_no_hint(self):
        result = await _verify(
            "balanced", stage3={"return_value": ({"model": "m", "response": "ok"}, {}, None)}
        )
        assert result["retry_hint"] is None
