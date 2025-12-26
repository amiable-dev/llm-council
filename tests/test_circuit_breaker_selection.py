"""TDD Tests for ADR-030 Phase 3c: Circuit Breaker Selection Integration.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/142

Circuit breaker selection integration features:
1. Open circuit excludes model from selection
2. Closed circuit allows selection
3. Half-open allows limited selection
4. Circuit breaker can be disabled via config
"""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestCircuitBreakerSelectionIntegration:
    """Test circuit breaker integration with model selection."""

    def test_open_circuit_excludes_model_from_selection(self):
        """Models with open circuit breaker should be excluded from selection."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )
        from llm_council.metadata.selection import (
            _is_circuit_breaker_open,
        )

        _reset_registry()

        # Trip the circuit for a model
        config = EnhancedCircuitBreakerConfig(min_requests=2, failure_threshold=0.25)
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)
        breaker.record_failure()
        breaker.record_failure()  # 100% failure rate

        # Should detect open circuit
        is_open = _is_circuit_breaker_open("openai/gpt-4o")
        assert is_open is True

    def test_closed_circuit_allows_selection(self):
        """Models with closed circuit breaker should be allowed in selection."""
        from llm_council.gateway.circuit_breaker_registry import _reset_registry
        from llm_council.metadata.selection import _is_circuit_breaker_open

        _reset_registry()

        # Fresh model has closed circuit
        is_open = _is_circuit_breaker_open("openai/gpt-4o")
        assert is_open is False

    def test_half_open_allows_limited_selection(self):
        """Models in half-open state should be allowed (for probe requests)."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )
        from llm_council.metadata.selection import _is_circuit_breaker_open

        _reset_registry()

        # Trip the circuit then wait for cooldown
        config = EnhancedCircuitBreakerConfig(
            min_requests=2,
            failure_threshold=0.25,
            cooldown_seconds=0.1,
        )
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)
        breaker.record_failure()
        breaker.record_failure()

        # Wait for cooldown
        time.sleep(0.15)

        # Trigger transition to HALF_OPEN
        breaker.allow_request()

        # Half-open should allow requests
        is_open = _is_circuit_breaker_open("openai/gpt-4o")
        assert is_open is False

    def test_circuit_breaker_disabled_bypasses_check(self):
        """When circuit breaker is disabled, always return not open."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )
        from llm_council.metadata.selection import _is_circuit_breaker_open

        _reset_registry()

        # Trip the circuit
        config = EnhancedCircuitBreakerConfig(min_requests=2, failure_threshold=0.25)
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)
        breaker.record_failure()
        breaker.record_failure()

        # With circuit breaker disabled, should report as not open
        with patch("llm_council.metadata.selection._is_circuit_breaker_enabled") as mock:
            mock.return_value = False
            is_open = _is_circuit_breaker_open("openai/gpt-4o")
            assert is_open is False


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig in unified_config.py."""

    def test_circuit_breaker_config_exists(self):
        """CircuitBreakerConfig should exist in unified_config."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config is not None

    def test_circuit_breaker_config_default_enabled(self):
        """Circuit breaker should be enabled by default."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.enabled is True

    def test_circuit_breaker_config_default_failure_threshold(self):
        """Default failure_threshold should be 0.25 (25%)."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.failure_threshold == 0.25

    def test_circuit_breaker_config_default_min_requests(self):
        """Default min_requests should be 5."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.min_requests == 5

    def test_circuit_breaker_config_default_window_seconds(self):
        """Default window_seconds should be 600 (10 min)."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.window_seconds == 600

    def test_circuit_breaker_config_default_cooldown_seconds(self):
        """Default cooldown_seconds should be 1800 (30 min)."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.cooldown_seconds == 1800

    def test_circuit_breaker_config_default_half_open_max_requests(self):
        """Default half_open_max_requests should be 3."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.half_open_max_requests == 3

    def test_circuit_breaker_config_default_half_open_success_threshold(self):
        """Default half_open_success_threshold should be 0.67."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert config.half_open_success_threshold == pytest.approx(0.67, abs=0.01)

    def test_circuit_breaker_config_custom_values(self):
        """CircuitBreakerConfig should accept custom values."""
        from llm_council.unified_config import CircuitBreakerConfig

        config = CircuitBreakerConfig(
            enabled=False,
            failure_threshold=0.50,
            min_requests=10,
            window_seconds=300,
            cooldown_seconds=3600,
            half_open_max_requests=5,
            half_open_success_threshold=0.80,
        )
        assert config.enabled is False
        assert config.failure_threshold == 0.50
        assert config.min_requests == 10
        assert config.window_seconds == 300
        assert config.cooldown_seconds == 3600
        assert config.half_open_max_requests == 5
        assert config.half_open_success_threshold == 0.80


class TestCircuitBreakerInModelIntelligence:
    """Test CircuitBreakerConfig in ModelIntelligenceConfig."""

    def test_model_intelligence_config_has_circuit_breaker(self):
        """ModelIntelligenceConfig should have circuit_breaker field."""
        from llm_council.unified_config import ModelIntelligenceConfig

        config = ModelIntelligenceConfig()
        assert hasattr(config, "circuit_breaker")

    def test_model_intelligence_default_circuit_breaker(self):
        """ModelIntelligenceConfig should have default CircuitBreakerConfig."""
        from llm_council.unified_config import CircuitBreakerConfig, ModelIntelligenceConfig

        config = ModelIntelligenceConfig()
        assert isinstance(config.circuit_breaker, CircuitBreakerConfig)
        assert config.circuit_breaker.enabled is True


class TestCircuitBreakerEnvOverride:
    """Test environment variable override for circuit breaker."""

    def test_env_var_disables_circuit_breaker(self):
        """LLM_COUNCIL_CIRCUIT_BREAKER=false should disable."""
        import os

        from llm_council.metadata.selection import _is_circuit_breaker_enabled

        original = os.environ.get("LLM_COUNCIL_CIRCUIT_BREAKER")
        try:
            os.environ["LLM_COUNCIL_CIRCUIT_BREAKER"] = "false"
            enabled = _is_circuit_breaker_enabled()
            assert enabled is False
        finally:
            if original is not None:
                os.environ["LLM_COUNCIL_CIRCUIT_BREAKER"] = original
            else:
                os.environ.pop("LLM_COUNCIL_CIRCUIT_BREAKER", None)

    def test_env_var_enables_circuit_breaker(self):
        """LLM_COUNCIL_CIRCUIT_BREAKER=true should enable."""
        import os

        from llm_council.metadata.selection import _is_circuit_breaker_enabled

        original = os.environ.get("LLM_COUNCIL_CIRCUIT_BREAKER")
        try:
            os.environ["LLM_COUNCIL_CIRCUIT_BREAKER"] = "true"
            enabled = _is_circuit_breaker_enabled()
            assert enabled is True
        finally:
            if original is not None:
                os.environ["LLM_COUNCIL_CIRCUIT_BREAKER"] = original
            else:
                os.environ.pop("LLM_COUNCIL_CIRCUIT_BREAKER", None)


class TestSelectTierModelsWithCircuitBreaker:
    """Test select_tier_models respects circuit breaker state."""

    def test_select_tier_models_excludes_open_circuit(self):
        """select_tier_models should exclude models with open circuits."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )
        from llm_council.metadata.selection import select_tier_models

        _reset_registry()

        # Trip the circuit for gpt-4o
        config = EnhancedCircuitBreakerConfig(min_requests=2, failure_threshold=0.25)
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)
        breaker.record_failure()
        breaker.record_failure()

        # Select models - gpt-4o should not be selected
        models = select_tier_models(tier="balanced", count=3)

        # Verify gpt-4o is excluded
        assert "openai/gpt-4o" not in models

    def test_select_tier_models_includes_closed_circuit(self):
        """select_tier_models should include models with closed circuits."""
        from llm_council.gateway.circuit_breaker_registry import _reset_registry
        from llm_council.metadata.selection import select_tier_models

        _reset_registry()

        # Select models with fresh registry
        models = select_tier_models(tier="balanced", count=5)

        # Should include some models
        assert len(models) > 0


class TestModuleExports:
    """Test module exports for circuit breaker integration."""

    def test_exports_is_circuit_breaker_open(self):
        """_is_circuit_breaker_open should be available."""
        from llm_council.metadata.selection import _is_circuit_breaker_open

        assert _is_circuit_breaker_open is not None

    def test_exports_is_circuit_breaker_enabled(self):
        """_is_circuit_breaker_enabled should be available."""
        from llm_council.metadata.selection import _is_circuit_breaker_enabled

        assert _is_circuit_breaker_enabled is not None
