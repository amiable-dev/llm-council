"""#725: each tier synthesises with its own aggregator unless one is configured.

``TierContract.aggregator_model`` was dead config: stage 3 read the flat
``council.chairman`` (default ``claude-opus-5``) for every tier. The test that
looked like coverage asserted the constant the contract was built from, never
the synthesis call (#607). These tests assert the model the chairman call is
MADE with.
"""

from unittest.mock import AsyncMock, patch

import pytest

from llm_council.chairman import current_tier, reset_current_tier, resolve_chairman, set_current_tier
from llm_council.tier_contract import TIER_AGGREGATORS, create_tier_contract


@pytest.fixture(autouse=True)
def _no_configured_chairman(monkeypatch):
    """Isolate from the operator's environment and any YAML."""
    from llm_council import unified_config

    monkeypatch.delenv("LLM_COUNCIL_CHAIRMAN", raising=False)
    monkeypatch.setenv("LLM_COUNCIL_CONFIG", "/nonexistent/llm_council.yaml")
    unified_config.reload_config()
    yield
    # Restore the environment BEFORE reloading, or the cached config keeps the
    # test's values (monkeypatch's own finalizer runs after this one).
    monkeypatch.undo()
    unified_config.reload_config()


class TestResolution:
    @pytest.mark.parametrize("tier", ["quick", "balanced", "high", "reasoning"])
    def test_an_unconfigured_chairman_is_the_tiers_aggregator(self, tier):
        assert resolve_chairman(tier) == create_tier_contract(tier).aggregator_model

    def test_the_default_is_no_longer_one_model_for_every_tier(self):
        models = {resolve_chairman(t) for t in ("quick", "balanced", "high", "reasoning")}
        assert len(models) > 1

    def test_the_tier_in_scope_is_used_when_none_is_passed(self):
        token = set_current_tier("balanced")
        try:
            assert resolve_chairman() == TIER_AGGREGATORS["balanced"]
        finally:
            reset_current_tier(token)
        assert current_tier() is None

    def test_no_tier_in_scope_uses_the_default_tiers_aggregator(self):
        from llm_council.unified_config import get_config

        assert resolve_chairman() == TIER_AGGREGATORS[get_config().tiers.default]

    def test_an_unknown_tier_falls_back_to_the_default(self):
        from llm_council.unified_config import get_config

        assert resolve_chairman("nonsense") == TIER_AGGREGATORS[get_config().tiers.default]

    def test_a_configured_chairman_wins_for_every_tier(self, monkeypatch):
        from llm_council import unified_config

        monkeypatch.setenv("LLM_COUNCIL_CHAIRMAN", "openai/some-chairman")
        unified_config.reload_config()
        for tier in ("quick", "balanced", "high", "reasoning"):
            assert resolve_chairman(tier) == "openai/some-chairman"

    def test_an_empty_configured_chairman_means_unset(self, monkeypatch):
        from llm_council import unified_config

        monkeypatch.setenv("LLM_COUNCIL_CHAIRMAN", "")
        unified_config.reload_config()
        assert resolve_chairman("balanced") == TIER_AGGREGATORS["balanced"]

    def test_a_mixed_case_tier_name_resolves(self):
        assert resolve_chairman("Balanced") == TIER_AGGREGATORS["balanced"]
        token = set_current_tier("HIGH")
        try:
            assert resolve_chairman() == TIER_AGGREGATORS["high"]
        finally:
            reset_current_tier(token)

    def test_a_customised_contracts_aggregator_is_honoured(self):
        """Review round 1: the resolver rebuilt the contract from the tier name,
        discarding an aggregator_model the caller had set."""
        import dataclasses

        custom = dataclasses.replace(
            create_tier_contract("balanced"), aggregator_model="custom/chair"
        )
        token = set_current_tier(custom)
        try:
            assert resolve_chairman() == "custom/chair"
        finally:
            reset_current_tier(token)

    def test_an_unknown_default_tier_degrades_instead_of_raising(self, monkeypatch):
        """Resolution runs at import time; a bad tiers.default must not crash
        the package import."""
        from llm_council import chairman
        from llm_council.unified_config import get_config

        monkeypatch.setattr(get_config().tiers, "default", "no-such-tier")
        assert chairman.resolve_chairman() == TIER_AGGREGATORS[chairman._LAST_RESORT_TIER]
        assert chairman.resolve_chairman("also-bad") == TIER_AGGREGATORS["high"]

    def test_the_cache_key_follows_the_tier_in_scope(self):
        """Review round 1 critical: the key embedded an import-time chairman and
        no tier, so one tier's cached synthesis could be served for another."""
        from llm_council.cache import get_cache_key

        keys = set()
        for tier in ("quick", "balanced", "high", "reasoning"):
            token = set_current_tier(tier)
            try:
                keys.add(get_cache_key("same query"))
            finally:
                reset_current_tier(token)
        assert len(keys) == 4
        assert get_cache_key("same query") == get_cache_key("same query")

    def test_the_public_constant_is_still_a_string(self):
        import llm_council

        assert isinstance(llm_council.CHAIRMAN_MODEL, str) and llm_council.CHAIRMAN_MODEL


def _status_ok(model):
    return {"status": "ok", "content": "synthesis", "model": model, "usage": {}}


class TestTheSynthesisCallUsesIt:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier", ["quick", "balanced", "high", "reasoning"])
    async def test_consult_synthesises_with_the_tiers_aggregator(self, tier):
        from llm_council.council import run_council_with_fallback

        seen = {}

        async def chairman_call(model, messages, **kwargs):
            seen["model"] = model
            return _status_ok(model)

        stage1 = ([{"model": "m/a", "response": "a"}, {"model": "m/b", "response": "b"}], {}, {})
        with (
            patch(
                "llm_council.council_stages.query_model_with_status", side_effect=chairman_call
            ),
            patch(
                "llm_council.council.stage1_collect_responses_with_status",
                new_callable=AsyncMock,
                return_value=stage1,
            ),
            patch(
                "llm_council.council.stage2_collect_rankings",
                new_callable=AsyncMock,
                return_value=([], {"Response A": {"model": "m/a", "display_index": 0}}, {}),
            ),
        ):
            await run_council_with_fallback(
                "q", bypass_cache=True, tier_contract=create_tier_contract(tier)
            )
        assert seen["model"] == create_tier_contract(tier).aggregator_model
        assert current_tier() is None  # reset after the run

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier", ["balanced", "high"])
    async def test_verify_synthesises_with_the_tiers_aggregator(self, tier):
        """The #686 case: balanced verify's chairman is sonnet-5, not opus-5."""
        from unittest.mock import MagicMock

        from llm_council.verification.api import VerifyRequest, run_verification

        seen = {}

        async def chairman_call(model, messages, **kwargs):
            seen["model"] = model
            return _status_ok(model)

        api, pipe = "llm_council.verification.api", "llm_council.verification.pipeline"
        prompt = ("p", {"kept": [], "warnings": [], "chars_rendered": 0, "chars_submitted": 0})
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        with (
            patch(
                "llm_council.council_stages.query_model_with_status", side_effect=chairman_call
            ),
            patch(f"{pipe}.stage1_collect_responses_with_status") as s1,
            patch(f"{pipe}.stage2_collect_rankings", return_value=([], {}, {})),
            patch(f"{pipe}.calculate_aggregate_rankings", return_value=[]),
            patch(f"{api}.VerificationContextManager") as ctx,
            patch(f"{api}._build_verification_prompt", new_callable=AsyncMock, return_value=prompt),
        ):
            ctx.return_value.__enter__ = MagicMock(return_value=MagicMock(context_id="c"))
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            s1.return_value = ([{"model": "m", "response": "ok"}], usage, {})
            store = MagicMock()
            store.create_verification_directory.return_value = "/tmp/test"
            await run_verification(VerifyRequest(snapshot_id="abc1234", tier=tier), store)

        assert seen["model"] == create_tier_contract(tier).aggregator_model
        assert current_tier() is None

    @pytest.mark.asyncio
    async def test_the_tier_is_reset_when_the_run_raises(self):
        """run_council_with_fallback turns a stage error into an error result
        rather than raising (ADR-012), so there is no pytest.raises here; what
        matters is that the tier does not outlive the run either way."""
        from llm_council.council import run_council_with_fallback

        with patch(
            "llm_council.council.stage1_collect_responses_with_status",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await run_council_with_fallback(
                "q", bypass_cache=True, tier_contract=create_tier_contract("balanced")
            )
        assert current_tier() is None

    @pytest.mark.asyncio
    async def test_a_test_patch_on_council_still_wins(self):
        from llm_council.council import _get_chairman_model

        with patch("llm_council.council.CHAIRMAN_MODEL", "patched/chair", create=True):
            assert _get_chairman_model() == "patched/chair"
