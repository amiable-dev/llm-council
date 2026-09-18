"""Tier-pool hygiene invariants (2026-09-18 OpenRouter model/cost review).

The pools in `llm_council.yaml` are the default councils. They were audited
against the live OpenRouter catalogue (445 models) and against this machine's
recorded performance index (`~/.llm-council/performance_metrics.jsonl`).

**Every invariant here is DERIVED from the pools, never enumerated.** The first
cut of this module enumerated four model ids and sliced list prefixes; the
#685 council gate rejected it with three criticals, all correct:

* the metadata and placement checks were parametrized over a hardcoded list, so
  any *future* addition was checked for bare presence and nothing else — which
  is precisely the regression this module exists to prevent;
* the budget check asserted `models[:count]`, a list prefix, while this
  module's own docstring says selection is score-driven and order is only a
  fallback tiebreaker. Since the quick pool had been reordered to put its slow
  member third, the test could only ever inspect the fastest models. It was
  green *because* it could not see the violation its own table recorded
  (`openai/gpt-5.6-luna` at 35.3 s in a 30 s tier).

So: a pool member is checked because it is in a pool, not because someone
remembered to add it to a list here.

Two structural facts the invariants encode:

1. **Any pool member can convene**, so every pool member must fit its tier's
   budget — not just whichever ones happen to sort first.
2. **Preview and unmeasured models belong in `frontier`.** ADR-027/029 make it
   the audition entry path: ADVISORY voting, zero consensus weight, promotion
   only once real sessions back the model. A model in a default tier that
   nothing has measured bypasses that machinery.
"""

import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "llm_council.yaml"
REGISTRY = REPO_ROOT / "src/llm_council/models/registry.yaml"

# Tiers that serve real traffic. `frontier` is deliberately excluded: it exists
# to carry models that have NOT yet earned a default seat.
DEFAULT_TIERS = ("quick", "balanced", "high", "reasoning")

VALID_QUALITY_TIERS = {"economy", "standard", "frontier", "local"}

# Snapshot of ~/.llm-council/performance_metrics.jsonl, 2026-09-18. It is a
# hand-copied developer-machine sample — CI has no performance store — so it is
# the *floor* of what we know, not a live feed. Latency and cost are
# uncontaminated; the borda column of that store is NOT (it contains negative
# values, the signature of the unsanitised-ballot bug fixed in #677), so
# quality is deliberately never asserted from it.
MEASURED_LATENCY_S = {
    "google/gemini-3.5-flash-lite": 3.2,
    "deepseek/deepseek-v4-flash": 12.2,
    "anthropic/claude-haiku-4.5": 15.1,
    "google/gemini-3.7-flash": 16.2,
    "anthropic/claude-sonnet-5": 32.1,
    "openai/gpt-5.6-luna": 35.3,
    "deepseek/deepseek-v4-pro-0813": 49.7,
    "openai/gpt-5.6-sol": 69.2,
    "google/gemini-3.1-pro-preview": 74.1,
    "openai/gpt-5.6-sol-pro": 134.4,
    "z-ai/glm-5.3": 153.9,
    "anthropic/claude-opus-5": 204.3,
}

# Known, TRACKED violations. An entry here is visible debt with an issue behind
# it, not an exemption — anything not listed fails.
KNOWN_BUDGET_VIOLATIONS = {
    # The configured chairman averages 204.3s against high's 180s budget. This
    # is the subject of #686 (it makes verify report unclear(infra_failure) on
    # a completed deliberation) and the fix is a contract decision — stage
    # floor vs waterfall share vs a faster chairman — not a pool edit.
    ("high", "anthropic/claude-opus-5"): "#686",
}

# ID substrings that mark a pre-GA model. A naming heuristic, not authoritative
# metadata — registry.yaml carries no preview flag. Kept because the failure it
# guards (a preview silently seated on a default council) is worth catching
# even imperfectly.
PREVIEW_MARKERS = ("-preview", "-exp", ":free", "-beta", "-rc")


@pytest.fixture(scope="module")
def pools():
    return yaml.safe_load(CONFIG.read_text())["council"]["tiers"]["pools"]


@pytest.fixture(scope="module")
def registry():
    return {m["id"]: m for m in yaml.safe_load(REGISTRY.read_text())["models"]}


def _all_pool_models(pools):
    return sorted({m for body in pools.values() for m in body.get("models", [])})


class TestPoolsAreWellFormed:
    def test_every_tier_has_models(self, pools):
        for tier, body in pools.items():
            assert body.get("models"), f"{tier} pool is empty"

    def test_no_duplicate_models_within_a_tier(self, pools):
        for tier, body in pools.items():
            models = body.get("models", [])
            assert len(models) == len(set(models)), f"{tier} repeats a model"

    def test_every_default_tier_spans_multiple_providers(self, pools):
        """Anonymised peer review is worth less when the panel is one vendor."""
        for tier in DEFAULT_TIERS:
            providers = {m.split("/")[0] for m in pools[tier].get("models", [])}
            assert len(providers) >= 2, f"{tier} is a single-provider council"


class TestRegistryCoversEveryPoolModel:
    """A pool entry claims a model may sit on a council; the registry is what
    lets `select_tier_models` SCORE that claim. Without an entry the selection
    falls through to `static_pool[:count]` — chosen by list position, with no
    context or cost filtering. That is selection by assertion."""

    def test_no_pool_model_lacks_registry_metadata(self, pools, registry):
        gaps = {
            tier: [m for m in body.get("models", []) if m not in registry]
            for tier, body in pools.items()
        }
        gaps = {t: g for t, g in gaps.items() if g}
        assert not gaps, f"pool models with no registry entry: {gaps}"

    def test_every_pool_model_has_usable_metadata(self, pools, registry):
        """Derived over the pools — a future addition is checked automatically."""
        problems = []
        for model_id in _all_pool_models(pools):
            entry = registry.get(model_id)
            if entry is None:
                continue  # reported by the test above
            ctx = entry.get("context_window")
            pricing = entry.get("pricing") or {}
            if not isinstance(ctx, int) or ctx <= 0:
                problems.append(f"{model_id}: context_window={ctx!r}")
            for field in ("prompt", "completion"):
                price = pricing.get(field)
                # per-1K USD. The band catches a x1000 transcription slip in
                # either direction, which a bare `> 0` would pass silently.
                if not isinstance(price, (int, float)) or not (1e-7 < price < 0.5):
                    problems.append(f"{model_id}: pricing.{field}={price!r} per 1K")
            if entry.get("quality_tier") not in VALID_QUALITY_TIERS:
                problems.append(f"{model_id}: quality_tier={entry.get('quality_tier')!r}")
            if not entry.get("modalities"):
                problems.append(f"{model_id}: no modalities")
        assert not problems, "unusable registry metadata:\n  " + "\n  ".join(problems)

    def test_cache_pricing_is_cheaper_than_prompt_pricing(self, pools, registry):
        """Cache classes are registered so ADR-049 D3 can price cache reads. A
        cache_read at or above the prompt price is a transcription error."""
        problems = []
        for model_id in _all_pool_models(pools):
            pricing = (registry.get(model_id) or {}).get("pricing") or {}
            prompt = pricing.get("prompt")
            cache_read = pricing.get("cache_read")
            if isinstance(prompt, (int, float)) and isinstance(cache_read, (int, float)):
                if cache_read >= prompt:
                    problems.append(
                        f"{model_id}: cache_read {cache_read} >= prompt {prompt}"
                    )
        assert not problems, "implausible cache pricing:\n  " + "\n  ".join(problems)


class TestEveryPoolMemberFitsItsTierBudget:
    """Any pool member can be selected, so the budget applies to all of them —
    not to whichever ones happen to sort first (the #685 gate's finding)."""

    @pytest.mark.parametrize("tier", DEFAULT_TIERS)
    def test_measured_models_fit_the_tier_budget(self, pools, tier):
        budget = pools[tier].get("timeout_seconds")
        assert budget, f"{tier} has no timeout_seconds"
        violations = []
        for model in pools[tier].get("models", []):
            measured = MEASURED_LATENCY_S.get(model)
            if measured is None:
                continue  # unmeasured: caught by the audition invariant below
            if measured > budget and (tier, model) not in KNOWN_BUDGET_VIOLATIONS:
                violations.append(f"{model} measured {measured}s > {budget}s budget")
        assert not violations, f"{tier}:\n  " + "\n  ".join(violations)

    def test_known_violations_are_still_real(self, pools):
        """If a tracked violation gets fixed, stop advertising it as debt."""
        stale = []
        for (tier, model), issue in KNOWN_BUDGET_VIOLATIONS.items():
            if model not in pools.get(tier, {}).get("models", []):
                stale.append(f"{model} is no longer in {tier} — drop the {issue} entry")
        assert not stale, "\n  ".join(stale)


class TestAuditionGatesDefaultTiers:
    """ADR-027/029: `frontier` is the entry path. A model with no measured
    history sitting in a default tier has skipped the audition."""

    @pytest.mark.parametrize("tier", DEFAULT_TIERS)
    def test_no_preview_models_in_default_tiers(self, pools, tier):
        offenders = [
            m
            for m in pools[tier].get("models", [])
            if any(tag in m for tag in PREVIEW_MARKERS)
        ]
        assert not offenders, (
            f"{tier} carries preview model(s) {offenders}; ADR-027 puts these in "
            "frontier so audition gates their promotion"
        )

    @pytest.mark.parametrize("tier", DEFAULT_TIERS)
    def test_no_unmeasured_models_in_default_tiers(self, pools, tier):
        """Derived, not enumerated: this is what keeps a newly-registered model
        out of a default council until something has actually measured it."""
        unmeasured = [
            m for m in pools[tier].get("models", []) if m not in MEASURED_LATENCY_S
        ]
        assert not unmeasured, (
            f"{tier} carries model(s) with no measured history: {unmeasured}. "
            "New models audition in frontier first (ADR-027/029)."
        )

    def test_frontier_is_populated(self, pools):
        assert pools.get("frontier", {}).get("models"), (
            "frontier must stay populated — it is the audition entry path"
        )
