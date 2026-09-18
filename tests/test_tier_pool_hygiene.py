"""Tier-pool hygiene invariants (2026-09-18 OpenRouter model/cost review).

The pools in `llm_council.yaml` are the default councils. They were audited
against the live OpenRouter catalogue (445 models) and against this machine's
own recorded performance index (1.8 MB, `~/.llm-council/performance_metrics.jsonl`).

Two structural findings drove the invariants below.

1. **Composition is the lever; order is a fallback tiebreaker.** Verified by
   calling `select_tier_models` directly rather than assuming: with model
   intelligence enabled the selection is SCORE-driven, so reordering a pool
   does not by itself change the picks. Order only decides on the
   `static_pool[:count]` fallback paths (no registry metadata, all circuits
   open, context filter empties the candidate set), so it is kept sane as a
   defensive measure — not as the headline change. What a pool CONTAINS is
   what reliably reaches a council.

   The measured profile of the quick pool, for reference:

   | quick member | measured latency | measured cost/run | selected? |
   |---|---|---|---|
   | `openai/gpt-5.6-luna` | 35.3 s — over the 30 s tier budget | $0.0100 | yes |
   | `anthropic/claude-haiku-4.5` | 15.1 s | $0.0192 | yes |
   | `google/gemini-3.5-flash-lite` | **3.2 s** | $0.0038 | no |
   | `deepseek/deepseek-v4-flash` | 12.2 s | **$0.0007** | no |

2. **Preview models belong in `frontier`.** ADR-027 makes the frontier tier the
   sanctioned entry path for cutting-edge/preview models, with ADVISORY voting
   and the audition pipeline gating promotion. A `-preview` model sitting in the
   default `high` pool bypasses all of that.

These tests pin the invariants, not the specific picks — a future model refresh
should keep passing without edits, while a regression (a preview model dropped
into a default tier, or a pool reordered so an over-budget model is selected)
fails loudly.
"""

import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "llm_council.yaml"

# Measured on 2026-09-18 from ~/.llm-council/performance_metrics.jsonl.
# Latency and cost are uncontaminated; the borda column of that store is NOT
# (it contains negative values — the signature of the unsanitised-ballot bug
# fixed in #677), so quality is deliberately not asserted here.
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
    "z-ai/glm-5.3": 153.9,
    "anthropic/claude-opus-5": 204.3,
}

# How many models each tier actually draws from its pool (CONFIDENCE_CONFIGS).
SELECTED = {"quick": 2, "balanced": 3}


@pytest.fixture(scope="module")
def pools():
    cfg = yaml.safe_load(CONFIG.read_text())
    return cfg["council"]["tiers"]["pools"]


def _selected(pools, tier):
    models = pools[tier]["models"]
    return models[: SELECTED[tier]] if tier in SELECTED else models


class TestPoolsAreWellFormed:
    def test_every_tier_has_models(self, pools):
        for tier, body in pools.items():
            assert body.get("models"), f"{tier} pool is empty"

    def test_no_duplicate_models_within_a_tier(self, pools):
        for tier, body in pools.items():
            models = body["models"]
            assert len(models) == len(set(models)), f"{tier} repeats a model"

    def test_selected_prefix_spans_multiple_providers(self, pools):
        """Anonymised peer review is worth less when the panel is one vendor."""
        for tier in SELECTED:
            providers = {m.split("/")[0] for m in _selected(pools, tier)}
            assert len(providers) >= 2, f"{tier} selects a single-provider council"


class TestSelectedModelsFitTheirTierBudget:
    """The measured latency of a selected model must fit the tier's own budget —
    a quick tier whose default member averages 35.3 s against a 30 s budget is
    mis-configured by its own definition."""

    @pytest.mark.parametrize("tier", sorted(SELECTED))
    def test_selected_models_are_within_budget(self, pools, tier):
        budget = pools[tier]["timeout_seconds"]
        for model in _selected(pools, tier):
            measured = MEASURED_LATENCY_S.get(model)
            if measured is None:
                continue  # unmeasured model: covered by the audition invariant
            assert measured <= budget, (
                f"{tier} selects {model} at a measured {measured}s "
                f"against a {budget}s tier budget"
            )


class TestPreviewModelsStayInFrontier:
    """ADR-027: frontier is the sanctioned entry path for preview/cutting-edge
    models (ADVISORY voting + audition gating). A preview in a default tier
    bypasses that machinery."""

    @pytest.mark.parametrize("tier", ["quick", "balanced", "high", "reasoning"])
    def test_no_preview_models_in_default_tiers(self, pools, tier):
        offenders = [
            m
            for m in pools[tier]["models"]
            if any(tag in m for tag in ("-preview", "-exp", ":free", "-beta"))
        ]
        assert not offenders, (
            f"{tier} carries preview model(s) {offenders}; ADR-027 puts these in "
            "frontier so audition gates their promotion"
        )

    def test_frontier_exists_to_receive_them(self, pools):
        assert pools.get("frontier", {}).get("models"), (
            "frontier must stay populated — it is the audition entry path"
        )


class TestCheapestCapableFirst:
    """Defensive only: on the `static_pool[:count]` fallback paths the order is
    what gets used, so the quick tier should lead with its fastest measured
    members. On the normal scored path this ordering is not what decides."""

    def test_quick_leads_with_its_fastest_measured_models(self, pools):
        selected = _selected(pools, "quick")
        measured = [
            (m, MEASURED_LATENCY_S[m]) for m in pools["quick"]["models"] if m in MEASURED_LATENCY_S
        ]
        if len(measured) < 2:
            pytest.skip("not enough measured members to assert an ordering")
        fastest_two = {m for m, _ in sorted(measured, key=lambda kv: kv[1])[:2]}
        assert fastest_two <= set(selected), (
            f"quick selects {selected} but its fastest measured members are "
            f"{sorted(fastest_two)}"
        )


# --- registry coverage --------------------------------------------------
# A pool entry is a claim that a model may sit on a council; `registry.yaml`
# is what lets `select_tier_models` SCORE that claim (context window, pricing,
# quality tier). A pool model with no registry entry falls through to the crude
# `static_pool[:count]` path — chosen by position in a list rather than on
# merit, with no context or cost filtering. That is selection by assertion.

REGISTRY = REPO_ROOT / "src/llm_council/models/registry.yaml"

# Added 2026-09-18 from the live OpenRouter catalogue. They enter via
# `frontier` (ADR-027/029): ADVISORY voting, zero consensus weight, promoted
# only by the audition pipeline once real sessions back them.
NEWLY_REGISTERED = [
    "openai/gpt-6-astra",
    "anthropic/claude-fable-5.1",
    "google/gemini-3.8-flash",
    "deepseek/deepseek-v4.1-flash",
]


@pytest.fixture(scope="module")
def registry():
    return {m["id"]: m for m in yaml.safe_load(REGISTRY.read_text())["models"]}


class TestRegistryCoversEveryPoolModel:
    def test_no_pool_model_lacks_registry_metadata(self, pools, registry):
        gaps = {
            tier: [m for m in body["models"] if m not in registry]
            for tier, body in pools.items()
        }
        gaps = {t: g for t, g in gaps.items() if g}
        assert not gaps, (
            f"pool models with no registry entry: {gaps}. Without metadata they "
            "cannot be scored, so selection falls back to list position."
        )

    @pytest.mark.parametrize("model_id", NEWLY_REGISTERED)
    def test_new_models_are_registered_with_usable_metadata(self, registry, model_id):
        entry = registry.get(model_id)
        assert entry, f"{model_id} is not in registry.yaml"
        assert entry["context_window"] > 0
        pricing = entry["pricing"]
        # per-1K USD, matching the rest of the file
        assert pricing["prompt"] > 0 and pricing["completion"] > 0
        assert entry["quality_tier"] in {"economy", "standard", "frontier", "local"}
        assert entry["modalities"]

    @pytest.mark.parametrize("model_id", NEWLY_REGISTERED)
    def test_new_models_enter_via_frontier_not_a_default_tier(self, pools, model_id):
        assert model_id in pools["frontier"]["models"], (
            f"{model_id} should audition in frontier first (ADR-027/029)"
        )
        for tier in ("quick", "balanced", "high", "reasoning"):
            assert model_id not in pools[tier]["models"], (
                f"{model_id} is unmeasured here — it must not start in {tier}"
            )
