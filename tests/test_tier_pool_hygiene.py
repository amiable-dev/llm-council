"""Tier-pool hygiene invariants (2026-09-18 OpenRouter model/cost review).

The pools in `llm_council.yaml` are the default councils. They were audited
against the live OpenRouter catalogue (445 models) and against this machine's
recorded performance index (`~/.llm-council/performance_metrics.jsonl`).

## What is derived, and what is not

Both the model set and the tier set are **read from the config**, so a future
pool entry — or a future *tier* — is covered automatically. That took two
council-gate rounds to get right, and the history is worth keeping:

* **Round 1** enumerated four model ids and sliced list prefixes. The budget
  check asserted `models[:count]` while this module's own docstring said
  selection is score-driven and order is only a fallback tiebreaker — and
  since `quick` had been reordered to put its slow member third, the test
  could only ever inspect the fastest models. It was green *because* it could
  not see the violation its own table recorded.
* **Round 2** fixed that at model granularity but left `DEFAULT_TIERS` a
  hardcoded tuple driving every tier-specific rule — the same defect one axis
  up — and a "tracked debt" test that checked only pool membership, so raising
  a budget would have turned a temporary waiver into a permanent silent one.

Two residues remain enumerated, deliberately and with their limits stated
rather than papered over:

* `MEASURED_LATENCY_S` is a hand-copied snapshot: CI has no performance store,
  so this is the only deterministic oracle available. It is both the audition
  gate and the budget oracle, which means **a fabricated line here would
  satisfy both**. Narrowing that to the ADR-029 audition state (the real
  authority on whether a model has earned a seat) is tracked separately.
* `PREVIEW_MARKERS` is a naming heuristic because `registry.yaml` carries no
  preview flag. It is matched on id segments to limit false positives, but a
  preview named without these tokens is still missed.
"""

import math
import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "llm_council.yaml"
REGISTRY = REPO_ROOT / "src/llm_council/models/registry.yaml"

# Loaded at import so the tier set can drive parametrization. `frontier` is the
# audition tier: it exists to carry models that have NOT yet earned a default
# seat, so it is excluded from the default-tier rules but still budget-checked.
_POOLS = yaml.safe_load(CONFIG.read_text())["council"]["tiers"]["pools"]
AUDITION_TIER = "frontier"
DEFAULT_TIERS = sorted(set(_POOLS) - {AUDITION_TIER})
ALL_TIERS = sorted(_POOLS)

VALID_QUALITY_TIERS = {"economy", "standard", "frontier", "local"}

# Snapshot of ~/.llm-council/performance_metrics.jsonl, 2026-09-18 (mean
# latency per model over that store). Latency and cost there are
# uncontaminated; the borda column is NOT — it contains negative values, the
# signature of the unsanitised-ballot bug fixed in #677 — so quality is never
# asserted from it.
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

# Tracked debt, not exemptions: each entry must STILL be a live violation, or
# `test_tracked_debt_is_still_a_real_violation` fails and the entry has to go.
KNOWN_BUDGET_VIOLATIONS = {
    # The configured chairman averages 204.3s against high's 180s budget, which
    # makes verify report unclear(infra_failure) on a completed deliberation.
    # The fix is a contract decision — stage floor vs waterfall share vs a
    # faster chairman — not a pool edit.
    ("high", "anthropic/claude-opus-5"): "#686",
}

# Matched against tokens of the id's LAST path segment, split on -, :, . and _,
# with trailing digits stripped so 'rc1' matches 'rc'. Round 3 of the gate found
# the previous version split only on '/' and '-', which made the "free" marker
# UNREACHABLE for the canonical `vendor/model:free` form — a dead invariant in
# the very module written to prevent them.
PREVIEW_MARKERS = {"preview", "exp", "experimental", "free", "beta", "rc", "alpha"}

# Per-1K USD plausibility bounds. Honest about what this is: it bounds GROSS
# unit errors (a per-token value pasted as per-1K, or dollars-per-million
# pasted raw). It does NOT detect an arbitrary x1000 slip — the band spans
# ~6.7 orders of magnitude, so 0.001 mistyped as 1e-6 sits inside it.
MIN_PRICE_PER_1K = 1e-7
MAX_PRICE_PER_1K = 0.5


def _is_free(model_id: str) -> bool:
    return model_id.endswith(":free")


def _is_preview(model_id: str) -> bool:
    tail = model_id.split("/")[-1]
    tokens = {t for t in re.split(r"[-:._]", tail) if t}
    tokens |= {t.rstrip("0123456789") for t in tokens}
    return bool(tokens & PREVIEW_MARKERS)


def _plausible_price(model_id: str, value) -> bool:
    """One rule for every price field, so the free-model carve-out cannot
    diverge between the prompt/completion path and the cache path — round 3 of
    the gate found it had. A `:free` model prices at exactly 0 by definition;
    everything else must sit inside the plausibility band."""
    if _is_free(model_id):
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value == 0
        )
    return _positive_number(value) and MIN_PRICE_PER_1K <= value <= MAX_PRICE_PER_1K


@pytest.fixture(scope="module")
def pools():
    return _POOLS


@pytest.fixture(scope="module")
def registry():
    raw = yaml.safe_load(REGISTRY.read_text())["models"]
    ids = [m["id"] for m in raw]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"registry.yaml registers these ids twice: {duplicates}"
    return {m["id"]: m for m in raw}


def _models(pools, tier):
    body = pools.get(tier)
    assert isinstance(body, dict), f"tier {tier!r} is missing or malformed"
    models = body.get("models") or []
    assert isinstance(models, list) and all(isinstance(m, str) for m in models), (
        f"tier {tier!r}: models must be a list of strings, got {models!r}"
    )
    return models


def _budget(pools, tier):
    body = pools.get(tier)
    assert isinstance(body, dict), f"tier {tier!r} is missing or malformed"
    budget = body.get("timeout_seconds")
    assert _positive_number(budget), f"{tier}: timeout_seconds={budget!r}"
    return budget


def _all_pool_models(pools):
    return sorted({m for tier in pools for m in _models(pools, tier)})


def _positive_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


class TestTierClassification:
    def test_the_audition_tier_exists(self, pools):
        assert AUDITION_TIER in pools, (
            f"{AUDITION_TIER} must exist — it is the ADR-027/029 entry path"
        )

    def test_the_tier_sets_partition_the_config(self, pools):
        """NOT the mechanism. The guarantee that a new tier gets covered comes
        from import-time derivation plus parametrization over ALL_TIERS /
        DEFAULT_TIERS. Round 3 of the gate correctly called the previous
        version of this test tautological — it compared DEFAULT_TIERS against
        the same object it was derived from, using the same expression. It
        survives only as a tripwire against someone re-hardcoding either set."""
        assert set(DEFAULT_TIERS) | {AUDITION_TIER} == set(ALL_TIERS)
        assert AUDITION_TIER not in DEFAULT_TIERS
        assert DEFAULT_TIERS, "no default tiers found"


class TestPoolsAreWellFormed:
    @pytest.mark.parametrize("tier", ALL_TIERS)
    def test_tier_has_models(self, pools, tier):
        assert _models(pools, tier), f"{tier} pool is empty"

    @pytest.mark.parametrize("tier", ALL_TIERS)
    def test_no_duplicate_models_within_a_tier(self, pools, tier):
        models = _models(pools, tier)
        assert len(models) == len(set(models)), f"{tier} repeats a model"

    @pytest.mark.parametrize("tier", DEFAULT_TIERS)
    def test_tier_spans_multiple_providers(self, pools, tier):
        """Anonymised peer review is worth less when the panel is one vendor."""
        providers = {m.split("/")[0] for m in _models(pools, tier)}
        assert len(providers) >= 2, f"{tier} is a single-provider council"


class TestRegistryCoversEveryPoolModel:
    """A pool entry claims a model may sit on a council; the registry is what
    lets `select_tier_models` SCORE that claim. Without an entry the selection
    falls through to `static_pool[:count]` — chosen by list position, with no
    context or cost filtering. That is selection by assertion."""

    def test_no_pool_model_lacks_registry_metadata(self, pools, registry):
        gaps = {
            tier: [m for m in _models(pools, tier) if m not in registry]
            for tier in pools
        }
        gaps = {t: g for t, g in gaps.items() if g}
        assert not gaps, f"pool models with no registry entry: {gaps}"

    def test_every_pool_model_has_usable_metadata(self, pools, registry):
        problems = []
        for model_id in _all_pool_models(pools):
            entry = registry.get(model_id)
            if entry is None:
                continue  # reported by the test above
            ctx = entry.get("context_window")
            if not (isinstance(ctx, int) and not isinstance(ctx, bool) and ctx > 0):
                problems.append(f"{model_id}: context_window={ctx!r}")
            pricing = entry.get("pricing") or {}
            for field in ("prompt", "completion"):
                price = pricing.get(field)
                if not _plausible_price(model_id, price):
                    problems.append(f"{model_id}: pricing.{field}={price!r} per 1K")
            if entry.get("quality_tier") not in VALID_QUALITY_TIERS:
                problems.append(f"{model_id}: quality_tier={entry.get('quality_tier')!r}")
            if not isinstance(entry.get("modalities"), list) or not entry["modalities"]:
                problems.append(f"{model_id}: modalities={entry.get('modalities')!r}")
        assert not problems, "unusable registry metadata:\n  " + "\n  ".join(problems)

    def test_cache_pricing_is_plausible(self, pools, registry):
        """Cache classes are registered so ADR-049 D3 can price cache reads. A
        cache_read at or above the prompt price, or outside the price band, is
        a transcription error."""
        problems = []
        for model_id in _all_pool_models(pools):
            pricing = (registry.get(model_id) or {}).get("pricing") or {}
            prompt = pricing.get("prompt")
            for field in ("cache_read", "cache_write_5m", "cache_write_1h"):
                value = pricing.get(field)
                if value is None:
                    continue  # optional
                if not _plausible_price(model_id, value):
                    problems.append(f"{model_id}: pricing.{field}={value!r} per 1K")
                elif field == "cache_read" and _positive_number(prompt) and value >= prompt:
                    problems.append(
                        f"{model_id}: cache_read {value} >= prompt {prompt}"
                    )
        assert not problems, "implausible cache pricing:\n  " + "\n  ".join(problems)


class TestEveryPoolMemberFitsItsTierBudget:
    """Any pool member can be selected, so the budget applies to all of them —
    not to whichever ones happen to sort first (the round-1 gate finding).
    Frontier is included: its members convene too, in ADVISORY mode."""

    @pytest.mark.parametrize("tier", ALL_TIERS)
    def test_measured_models_fit_the_tier_budget(self, pools, tier):
        budget = _budget(pools, tier)
        violations = [
            f"{m} measured {MEASURED_LATENCY_S[m]}s > {budget}s budget"
            for m in _models(pools, tier)
            if m in MEASURED_LATENCY_S
            and MEASURED_LATENCY_S[m] > budget
            and (tier, m) not in KNOWN_BUDGET_VIOLATIONS
        ]
        assert not violations, f"{tier}:\n  " + "\n  ".join(violations)

    def test_tracked_debt_is_still_a_real_violation(self, pools):
        """A waiver that outlives its violation is a permanent silent
        exemption. Each entry must still be in the pool AND still exceed the
        budget, or it has to be deleted."""
        stale = []
        for (tier, model), issue in KNOWN_BUDGET_VIOLATIONS.items():
            if model not in _models(pools, tier):
                stale.append(f"{model} is no longer in {tier} — drop the {issue} entry")
                continue
            measured = MEASURED_LATENCY_S.get(model)
            budget = _budget(pools, tier)
            if measured is None:
                stale.append(f"{model} has no measured latency — {issue} unprovable")
            elif measured <= budget:
                stale.append(
                    f"{model} now measures {measured}s <= {budget}s in {tier}: "
                    f"{issue} is resolved, drop the waiver"
                )
        assert not stale, "\n  ".join(stale)


class TestAuditionGatesDefaultTiers:
    """ADR-027/029: `frontier` is the entry path. A model with no measured
    history sitting in a default tier has skipped the audition."""

    @pytest.mark.parametrize("tier", DEFAULT_TIERS)
    def test_no_preview_models_in_default_tiers(self, pools, tier):
        offenders = [
            m for m in _models(pools, tier) if _is_preview(m)
        ]
        assert not offenders, (
            f"{tier} carries preview model(s) {offenders}; ADR-027 puts these in "
            f"{AUDITION_TIER} so audition gates their promotion"
        )

    @pytest.mark.parametrize("tier", DEFAULT_TIERS)
    def test_no_unmeasured_models_in_default_tiers(self, pools, tier):
        unmeasured = [m for m in _models(pools, tier) if m not in MEASURED_LATENCY_S]
        assert not unmeasured, (
            f"{tier} carries model(s) with no measured history: {unmeasured}. "
            f"New models audition in {AUDITION_TIER} first (ADR-027/029)."
        )
