"""TDD tests for ADR-026 Phase 2: Reasoning Parameter Configuration.

Tests for ReasoningEffort enum, ReasoningConfig dataclass, and unified config
integration. Written BEFORE implementation per TDD workflow.
"""

import pytest
from unittest.mock import patch
import os


class TestReasoningEffortEnum:
    """Test ReasoningEffort enum definition."""

    def test_reasoning_effort_enum_has_all_levels(self):
        """ReasoningEffort should have MINIMAL, LOW, MEDIUM, HIGH, XHIGH."""
        from llm_council.reasoning.types import ReasoningEffort

        assert hasattr(ReasoningEffort, "MINIMAL")
        assert hasattr(ReasoningEffort, "LOW")
        assert hasattr(ReasoningEffort, "MEDIUM")
        assert hasattr(ReasoningEffort, "HIGH")
        assert hasattr(ReasoningEffort, "XHIGH")

    def test_reasoning_effort_enum_values(self):
        """ReasoningEffort values should be lowercase strings."""
        from llm_council.reasoning.types import ReasoningEffort

        assert ReasoningEffort.MINIMAL.value == "minimal"
        assert ReasoningEffort.LOW.value == "low"
        assert ReasoningEffort.MEDIUM.value == "medium"
        assert ReasoningEffort.HIGH.value == "high"
        assert ReasoningEffort.XHIGH.value == "xhigh"

    def test_effort_ratios_correct(self):
        """Effort ratios should match spec: 0.10, 0.20, 0.50, 0.80, 0.95."""
        from llm_council.reasoning.types import EFFORT_RATIOS, ReasoningEffort

        assert EFFORT_RATIOS[ReasoningEffort.MINIMAL] == 0.10
        assert EFFORT_RATIOS[ReasoningEffort.LOW] == 0.20
        assert EFFORT_RATIOS[ReasoningEffort.MEDIUM] == 0.50
        assert EFFORT_RATIOS[ReasoningEffort.HIGH] == 0.80
        assert EFFORT_RATIOS[ReasoningEffort.XHIGH] == 0.95


class TestReasoningConfig:
    """Test ReasoningConfig dataclass."""

    def test_reasoning_config_dataclass_exists(self):
        """ReasoningConfig should be a frozen dataclass."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort
        from dataclasses import is_dataclass

        config = ReasoningConfig(
            effort=ReasoningEffort.MEDIUM,
            budget_tokens=16000,
        )
        assert is_dataclass(config)

    def test_reasoning_config_has_required_fields(self):
        """ReasoningConfig should have effort, budget_tokens, enabled."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig(
            effort=ReasoningEffort.HIGH,
            budget_tokens=32000,
        )
        assert config.effort == ReasoningEffort.HIGH
        assert config.budget_tokens == 32000
        assert config.enabled is True  # Default

    def test_reasoning_config_enabled_default_true(self):
        """ReasoningConfig.enabled should default to True."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig(
            effort=ReasoningEffort.LOW,
            budget_tokens=6400,
        )
        assert config.enabled is True

    def test_reasoning_config_can_disable(self):
        """ReasoningConfig.enabled can be set to False."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig(
            effort=ReasoningEffort.LOW,
            budget_tokens=6400,
            enabled=False,
        )
        assert config.enabled is False


class TestReasoningConfigForTier:
    """Test ReasoningConfig.for_tier() factory method."""

    def test_for_tier_returns_config(self):
        """for_tier() should return a ReasoningConfig instance."""
        from llm_council.reasoning.types import ReasoningConfig

        config = ReasoningConfig.for_tier("high")
        assert isinstance(config, ReasoningConfig)

    def test_for_tier_quick_tier_minimal_effort(self):
        """Quick tier should use MINIMAL effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("quick")
        assert config.effort == ReasoningEffort.MINIMAL

    def test_for_tier_balanced_tier_low_effort(self):
        """Balanced tier should use LOW effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("balanced")
        assert config.effort == ReasoningEffort.LOW

    def test_for_tier_high_tier_medium_effort(self):
        """High tier should use MEDIUM effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("high")
        assert config.effort == ReasoningEffort.MEDIUM

    def test_for_tier_reasoning_tier_high_effort(self):
        """Reasoning tier should use HIGH effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("reasoning")
        assert config.effort == ReasoningEffort.HIGH


class TestDomainOverrides:
    """Test task domain overrides for reasoning effort."""

    def test_for_tier_applies_domain_override(self):
        """Task domain should override tier-default effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        # Math domain overrides to HIGH
        config = ReasoningConfig.for_tier("quick", task_domain="math")
        assert config.effort == ReasoningEffort.HIGH

    def test_domain_override_math_high(self):
        """Math domain should use HIGH effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("balanced", task_domain="math")
        assert config.effort == ReasoningEffort.HIGH

    def test_domain_override_coding_medium(self):
        """Coding domain should use MEDIUM effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("quick", task_domain="coding")
        assert config.effort == ReasoningEffort.MEDIUM

    def test_domain_override_creative_minimal(self):
        """Creative domain should use MINIMAL effort."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("high", task_domain="creative")
        assert config.effort == ReasoningEffort.MINIMAL

    def test_unknown_domain_uses_tier_default(self):
        """Unknown domain should fall back to tier default."""
        from llm_council.reasoning.types import ReasoningConfig, ReasoningEffort

        config = ReasoningConfig.for_tier("high", task_domain="unknown_domain")
        assert config.effort == ReasoningEffort.MEDIUM  # high tier default


class TestBudgetCalculation:
    """Test reasoning budget token calculation."""

    def test_budget_calculation_uses_ratio(self):
        """Budget should be calculated as max_tokens * effort_ratio."""
        from llm_council.reasoning.types import ReasoningConfig

        # HIGH effort (0.80) with 32000 max_tokens = 25600
        config = ReasoningConfig.for_tier("reasoning", max_tokens=32000)
        assert config.budget_tokens == 25600

    def test_budget_respects_min_bound(self):
        """Budget should not go below 1024."""
        from llm_council.reasoning.types import ReasoningConfig

        # MINIMAL effort (0.10) with 5000 max_tokens = 500, but min is 1024
        config = ReasoningConfig.for_tier("quick", max_tokens=5000)
        assert config.budget_tokens >= 1024

    def test_budget_respects_max_bound(self):
        """Budget should not exceed 32000."""
        from llm_council.reasoning.types import ReasoningConfig

        # XHIGH effort (0.95) with 100000 max_tokens = 95000, but max is 32000
        config = ReasoningConfig.for_tier("reasoning", max_tokens=100000)
        assert config.budget_tokens <= 32000

    def test_budget_with_custom_bounds(self):
        """for_tier should accept custom min/max bounds."""
        from llm_council.reasoning.types import ReasoningConfig

        config = ReasoningConfig.for_tier(
            "high",
            max_tokens=50000,
            min_budget=2048,
            max_budget=16000,
        )
        assert config.budget_tokens >= 2048
        assert config.budget_tokens <= 16000


class TestReasoningStageConfig:
    """Test stage-specific reasoning configuration."""

    def test_stage_config_defaults(self):
        """StageConfig should have correct defaults: stage1=True, stage2=False, stage3=True."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        stages = config.model_intelligence.reasoning.stages

        assert stages.stage1 is True
        assert stages.stage2 is False
        assert stages.stage3 is True

    def test_should_apply_reasoning_stage1_default_true(self):
        """should_apply_reasoning() for stage 1 should return True by default."""
        from llm_council.reasoning.types import should_apply_reasoning
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert should_apply_reasoning(stage=1, config=config) is True

    def test_should_apply_reasoning_stage2_default_false(self):
        """should_apply_reasoning() for stage 2 should return False by default."""
        from llm_council.reasoning.types import should_apply_reasoning
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert should_apply_reasoning(stage=2, config=config) is False

    def test_should_apply_reasoning_stage3_default_true(self):
        """should_apply_reasoning() for stage 3 should return True by default."""
        from llm_council.reasoning.types import should_apply_reasoning
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert should_apply_reasoning(stage=3, config=config) is True


class TestUnifiedConfigReasoningIntegration:
    """Test UnifiedConfig integration with reasoning configuration."""

    def test_unified_config_has_reasoning(self):
        """UnifiedConfig.model_intelligence should have reasoning section."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config.model_intelligence, "reasoning")

    def test_reasoning_config_has_enabled(self):
        """reasoning config should have enabled field."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        assert hasattr(config.model_intelligence.reasoning, "enabled")
        assert config.model_intelligence.reasoning.enabled is True  # Default

    def test_reasoning_config_has_effort_by_tier(self):
        """reasoning config should have effort_by_tier section."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        effort = config.model_intelligence.reasoning.effort_by_tier

        assert effort.quick == "minimal"
        assert effort.balanced == "low"
        assert effort.high == "medium"
        assert effort.reasoning == "high"

    def test_reasoning_config_has_domain_overrides(self):
        """reasoning config should have domain_overrides section."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        overrides = config.model_intelligence.reasoning.domain_overrides

        assert overrides.math == "high"
        assert overrides.coding == "medium"
        assert overrides.creative == "minimal"

    def test_reasoning_config_has_budget_bounds(self):
        """reasoning config should have min/max budget settings."""
        from llm_council.unified_config import UnifiedConfig

        config = UnifiedConfig()
        reasoning = config.model_intelligence.reasoning

        assert reasoning.max_budget_tokens == 32000
        assert reasoning.min_budget_tokens == 1024

    def test_reasoning_config_env_override(self):
        """LLM_COUNCIL_REASONING_ENABLED should override enabled field."""
        from llm_council.unified_config import get_effective_config, reload_config

        with patch.dict(os.environ, {"LLM_COUNCIL_REASONING_ENABLED": "false"}):
            reload_config()
            config = get_effective_config()
            assert config.model_intelligence.reasoning.enabled is False


class TestReasoningModuleExports:
    """Test reasoning module exports from __init__.py."""

    def test_module_exports_reasoning_effort(self):
        """reasoning module should export ReasoningEffort."""
        from llm_council.reasoning import ReasoningEffort

        assert ReasoningEffort.HIGH.value == "high"

    def test_module_exports_reasoning_config(self):
        """reasoning module should export ReasoningConfig."""
        from llm_council.reasoning import ReasoningConfig

        assert callable(ReasoningConfig.for_tier)

    def test_module_exports_effort_ratios(self):
        """reasoning module should export EFFORT_RATIOS."""
        from llm_council.reasoning import EFFORT_RATIOS

        assert isinstance(EFFORT_RATIOS, dict)

    def test_module_exports_should_apply_reasoning(self):
        """reasoning module should export should_apply_reasoning."""
        from llm_council.reasoning import should_apply_reasoning

        assert callable(should_apply_reasoning)
