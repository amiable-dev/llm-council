import pytest
from llm_council import model_constants as mc
from llm_council.triage.types import WildcardConfig, DomainCategory, DEFAULT_SPECIALIST_POOLS
from llm_council.unified_config import get_config


def test_fallback_model_wiring():
    """Verify that WildcardConfig correctly defaults to centralized constants (ADR-020)."""
    config = WildcardConfig()

    # Assert fallback model alignment
    assert config.fallback_model == mc.WILDCARD_FALLBACK_MODEL

    # Verify pool integration
    general_pool = DEFAULT_SPECIALIST_POOLS[DomainCategory.GENERAL]
    assert mc.WILDCARD_FALLBACK_MODEL in general_pool


def test_specialist_pool_centralization():
    """Verify all domain specialist pools are linked to model_constants."""
    # Code pool
    assert mc.WILDCARD_CODE_QWEN in DEFAULT_SPECIALIST_POOLS[DomainCategory.CODE]
    assert mc.WILDCARD_CODE_MISTRAL in DEFAULT_SPECIALIST_POOLS[DomainCategory.CODE]

    # Reasoning pool
    assert mc.WILDCARD_REASONING_O1 in DEFAULT_SPECIALIST_POOLS[DomainCategory.REASONING]
    assert mc.WILDCARD_REASONING_QWQ in DEFAULT_SPECIALIST_POOLS[DomainCategory.REASONING]

    # Creative pool
    assert mc.WILDCARD_CREATIVE_OPUS in DEFAULT_SPECIALIST_POOLS[DomainCategory.CREATIVE]


def test_sovereign_config_defaults(monkeypatch):
    """Verify that the system correctly defaults to centralized baseline without YAML (ADR-024)."""
    # Force the loader to look for a non-existent YAML file
    monkeypatch.setenv("LLM_COUNCIL_CONFIG_PATH", "non_existent_config.yaml")

    config = get_config()

    # 1. Verify Chairman Default
    assert config.council.chairman == mc.CHAIRMAN_MODEL

    # 2. Verify Fleet Defaults
    pools = config.tiers.pools
    assert mc.OPENAI_BALANCED in pools["balanced"].models
    assert mc.GOOGLE_BALANCED in pools["balanced"].models

    assert mc.GOOGLE_REASONING in pools["reasoning"].models

    # 3. Verify Normalizer Default
    assert config.council.normalizer_model == mc.UTILITY_NORMALIZER_MODEL


def test_model_id_registry_prefix():
    """Sanity check that all centralized constants follow the required <provider>/<model> format."""
    constants = [
        mc.OPENAI_QUICK,
        mc.OPENAI_BALANCED,
        mc.OPENAI_HIGH,
        mc.OPENAI_REASONING,
        mc.GOOGLE_BALANCED,
        mc.GOOGLE_REASONING,
        mc.ANTHROPIC_BALANCED,
        mc.ANTHROPIC_HIGH,
        mc.WILDCARD_FALLBACK_MODEL,
    ]

    for model_id in constants:
        assert "/" in model_id, f"Model ID '{model_id}' is missing provider prefix"
        assert not model_id.startswith("/"), f"Model ID '{model_id}' has invalid prefix"
        assert not model_id.endswith("/"), f"Model ID '{model_id}' has invalid suffix"
