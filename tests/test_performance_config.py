"""TDD tests for ADR-026 Phase 3: Configuration Integration.

Tests for PerformanceTrackerConfig in unified_config.py.
Written BEFORE implementation per TDD workflow.
"""

import tempfile
from pathlib import Path

import pytest


class TestPerformanceTrackerConfig:
    """Test PerformanceTrackerConfig in unified_config.py."""

    def test_config_class_exists(self):
        """PerformanceTrackerConfig should exist in unified_config."""
        from llm_council.unified_config import PerformanceTrackerConfig

        config = PerformanceTrackerConfig()
        assert config is not None

    def test_default_enabled_true(self):
        """Performance tracker should be enabled by default."""
        from llm_council.unified_config import PerformanceTrackerConfig

        config = PerformanceTrackerConfig()
        assert config.enabled is True

    def test_default_decay_days(self):
        """Default decay_days should be 30."""
        from llm_council.unified_config import PerformanceTrackerConfig

        config = PerformanceTrackerConfig()
        assert config.decay_days == 30

    def test_configurable_decay_days(self):
        """decay_days should be configurable."""
        from llm_council.unified_config import PerformanceTrackerConfig

        config = PerformanceTrackerConfig(decay_days=60)
        assert config.decay_days == 60

    def test_default_confidence_thresholds(self):
        """Default confidence thresholds should match ADR-026."""
        from llm_council.unified_config import PerformanceTrackerConfig

        config = PerformanceTrackerConfig()
        assert config.min_samples_preliminary == 10
        assert config.min_samples_moderate == 30
        assert config.min_samples_high == 100

    def test_configurable_thresholds(self):
        """Confidence thresholds should be configurable."""
        from llm_council.unified_config import PerformanceTrackerConfig

        config = PerformanceTrackerConfig(
            min_samples_preliminary=5,
            min_samples_moderate=20,
            min_samples_high=50,
        )
        assert config.min_samples_preliminary == 5
        assert config.min_samples_moderate == 20
        assert config.min_samples_high == 50

    def test_default_store_path(self):
        """Default store_path should be ~/.llm-council/performance_metrics.jsonl."""
        from llm_council.unified_config import PerformanceTrackerConfig

        config = PerformanceTrackerConfig()
        assert "performance_metrics.jsonl" in config.store_path


class TestModelIntelligenceConfigHasPerformanceTracker:
    """Test ModelIntelligenceConfig includes performance_tracker."""

    def test_model_intelligence_has_performance_tracker_field(self):
        """ModelIntelligenceConfig should have performance_tracker field."""
        from llm_council.unified_config import ModelIntelligenceConfig

        config = ModelIntelligenceConfig()
        assert hasattr(config, "performance_tracker")

    def test_performance_tracker_default_instance(self):
        """performance_tracker should be PerformanceTrackerConfig by default."""
        from llm_council.unified_config import (
            ModelIntelligenceConfig,
            PerformanceTrackerConfig,
        )

        config = ModelIntelligenceConfig()
        assert isinstance(config.performance_tracker, PerformanceTrackerConfig)


class TestUnifiedConfigIntegration:
    """Test unified config loading with performance tracker."""

    def test_load_config_includes_performance_tracker(self):
        """load_config should include performance_tracker in model_intelligence."""
        from llm_council.unified_config import load_config

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
model_intelligence:
  enabled: true
""")
            f.flush()

            config = load_config(Path(f.name))
            # Verify performance_tracker exists and has correct type
            assert hasattr(config.model_intelligence, "performance_tracker")
            assert config.model_intelligence.performance_tracker is not None
            # Default enabled should be True
            assert config.model_intelligence.performance_tracker.enabled is True

    def test_defaults_when_not_specified(self):
        """Should use defaults when performance_tracker not in YAML."""
        from llm_council.unified_config import load_config

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
model_intelligence:
  enabled: true
""")
            f.flush()

            config = load_config(Path(f.name))
            # Should have default PerformanceTrackerConfig
            assert config.model_intelligence.performance_tracker.enabled is True
            assert config.model_intelligence.performance_tracker.decay_days == 30
