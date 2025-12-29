"""TDD Tests for ADR-030 Phase 3b: Per-Model Circuit Breaker Registry.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/141

Per-model circuit breaker registry features:
1. Thread-safe registry for per-model breakers
2. Event emission on state transitions
3. Check and record helper functions
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest


class TestCircuitBreakerRegistry:
    """Test per-model circuit breaker registry."""

    def test_get_or_create_breaker(self):
        """Should create new breaker if not exists."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )

        _reset_registry()

        breaker = get_circuit_breaker("openai/gpt-4o")
        assert breaker is not None
        assert breaker.model_id == "openai/gpt-4o"

    def test_reuses_existing_breaker(self):
        """Should return same breaker instance for same model."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )

        _reset_registry()

        breaker1 = get_circuit_breaker("openai/gpt-4o")
        breaker2 = get_circuit_breaker("openai/gpt-4o")

        assert breaker1 is breaker2

    def test_different_models_different_breakers(self):
        """Different models should have different breakers."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )

        _reset_registry()

        breaker1 = get_circuit_breaker("openai/gpt-4o")
        breaker2 = get_circuit_breaker("anthropic/claude-3")

        assert breaker1 is not breaker2

    def test_thread_safe_access(self):
        """Registry should be thread-safe."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )

        _reset_registry()

        results = []
        errors = []

        def get_breaker():
            try:
                breaker = get_circuit_breaker("openai/gpt-4o")
                results.append(breaker)
            except Exception as e:
                errors.append(e)

        # Create 10 threads all getting the same breaker
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_breaker) for _ in range(100)]
            for f in futures:
                f.result()

        assert len(errors) == 0
        # All should be the same instance
        assert all(b is results[0] for b in results)

    def test_custom_config_on_create(self):
        """Should accept custom config on first creation."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
        )

        _reset_registry()

        config = EnhancedCircuitBreakerConfig(min_requests=10, failure_threshold=0.50)
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)

        assert breaker.config.min_requests == 10
        assert breaker.config.failure_threshold == 0.50


class TestCheckCircuitBreaker:
    """Test check_circuit_breaker helper function."""

    def test_closed_circuit_allows_request(self):
        """Closed circuit should allow requests."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            check_circuit_breaker,
        )

        _reset_registry()

        allowed, reason = check_circuit_breaker("openai/gpt-4o")
        assert allowed is True
        assert reason is None

    def test_open_circuit_blocks_request(self):
        """Open circuit should block requests."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            check_circuit_breaker,
        )

        _reset_registry()

        # Trip the circuit
        config = EnhancedCircuitBreakerConfig(min_requests=2, failure_threshold=0.25)
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)
        breaker.record_failure()
        breaker.record_failure()  # 100% failure rate

        allowed, reason = check_circuit_breaker("openai/gpt-4o")
        assert allowed is False
        assert reason is not None
        assert "open" in reason.lower()


class TestRecordModelResult:
    """Test record_model_result helper function."""

    def test_record_success(self):
        """Should record success to model's breaker."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            record_model_result,
        )

        _reset_registry()

        record_model_result("openai/gpt-4o", success=True)

        breaker = get_circuit_breaker("openai/gpt-4o")
        assert breaker.request_count_in_window() == 1
        assert breaker.failure_count_in_window() == 0

    def test_record_failure(self):
        """Should record failure to model's breaker."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            record_model_result,
        )

        _reset_registry()

        record_model_result("openai/gpt-4o", success=False)

        breaker = get_circuit_breaker("openai/gpt-4o")
        assert breaker.request_count_in_window() == 1
        assert breaker.failure_count_in_window() == 1


class TestCircuitBreakerEventEmission:
    """Test event emission on circuit state transitions."""

    def test_emits_circuit_open_event(self):
        """Should emit L4_CIRCUIT_BREAKER_OPEN event when circuit opens."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            record_model_result,
        )
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_registry()
        clear_layer_events()

        # Create breaker with low threshold
        config = EnhancedCircuitBreakerConfig(min_requests=2, failure_threshold=0.25)
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)

        # Trip the circuit (using registry function to get events)
        record_model_result("openai/gpt-4o", success=False)
        record_model_result("openai/gpt-4o", success=False)

        events = get_layer_events()
        open_events = [e for e in events if e.event_type == LayerEventType.L4_CIRCUIT_BREAKER_OPEN]
        assert len(open_events) >= 1

        event = open_events[-1]
        assert event.data["model_id"] == "openai/gpt-4o"
        assert "failure_rate" in event.data

    def test_emits_circuit_close_event(self):
        """Should emit L4_CIRCUIT_BREAKER_CLOSE event when circuit closes."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            record_model_result,
        )
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_registry()
        clear_layer_events()

        # Create breaker with fast cooldown
        config = EnhancedCircuitBreakerConfig(
            min_requests=2,
            failure_threshold=0.25,
            cooldown_seconds=0.1,
            half_open_max_requests=2,
            half_open_success_threshold=0.50,
        )
        breaker = get_circuit_breaker("openai/gpt-4o", config=config)

        # Trip the circuit
        record_model_result("openai/gpt-4o", success=False)
        record_model_result("openai/gpt-4o", success=False)

        # Wait for cooldown
        time.sleep(0.15)

        # Allow request to transition to HALF_OPEN
        breaker.allow_request()

        # Record successes to close
        record_model_result("openai/gpt-4o", success=True)
        record_model_result("openai/gpt-4o", success=True)

        events = get_layer_events()
        close_events = [
            e for e in events if e.event_type == LayerEventType.L4_CIRCUIT_BREAKER_CLOSE
        ]
        assert len(close_events) >= 1

        event = close_events[-1]
        assert event.data["model_id"] == "openai/gpt-4o"

    def test_event_includes_failure_rate(self):
        """Open event should include failure_rate."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            record_model_result,
        )
        from llm_council.layer_contracts import LayerEventType, clear_layer_events, get_layer_events

        _reset_registry()
        clear_layer_events()

        config = EnhancedCircuitBreakerConfig(min_requests=2, failure_threshold=0.25)
        get_circuit_breaker("openai/gpt-4o", config=config)

        record_model_result("openai/gpt-4o", success=False)
        record_model_result("openai/gpt-4o", success=False)

        events = get_layer_events()
        open_events = [e for e in events if e.event_type == LayerEventType.L4_CIRCUIT_BREAKER_OPEN]
        assert len(open_events) >= 1

        event = open_events[-1]
        assert event.data["failure_rate"] == pytest.approx(1.0, abs=0.01)  # 100% failure rate


class TestRegistryHelpers:
    """Test registry helper functions."""

    def test_reset_registry(self):
        """_reset_registry should clear all breakers."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            get_all_breakers,
        )

        get_circuit_breaker("openai/gpt-4o")
        get_circuit_breaker("anthropic/claude-3")

        assert len(get_all_breakers()) == 2

        _reset_registry()

        assert len(get_all_breakers()) == 0

    def test_get_all_breakers(self):
        """get_all_breakers should return all registered breakers."""
        from llm_council.gateway.circuit_breaker_registry import (
            _reset_registry,
            get_circuit_breaker,
            get_all_breakers,
        )

        _reset_registry()

        get_circuit_breaker("openai/gpt-4o")
        get_circuit_breaker("anthropic/claude-3")

        breakers = get_all_breakers()
        assert len(breakers) == 2
        assert "openai/gpt-4o" in breakers
        assert "anthropic/claude-3" in breakers


class TestModuleExports:
    """Test module exports."""

    def test_exports_get_circuit_breaker(self):
        """get_circuit_breaker should be exported."""
        from llm_council.gateway.circuit_breaker_registry import get_circuit_breaker

        assert get_circuit_breaker is not None

    def test_exports_check_circuit_breaker(self):
        """check_circuit_breaker should be exported."""
        from llm_council.gateway.circuit_breaker_registry import check_circuit_breaker

        assert check_circuit_breaker is not None

    def test_exports_record_model_result(self):
        """record_model_result should be exported."""
        from llm_council.gateway.circuit_breaker_registry import record_model_result

        assert record_model_result is not None

    def test_exports_get_all_breakers(self):
        """get_all_breakers should be exported."""
        from llm_council.gateway.circuit_breaker_registry import get_all_breakers

        assert get_all_breakers is not None
