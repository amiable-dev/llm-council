"""Tests for circuit breaker implementation (ADR-023).

TDD: Write these tests first, then implement the CircuitBreaker.
"""

import pytest
from unittest.mock import AsyncMock, patch
import asyncio


class TestCircuitBreakerStates:
    """Test circuit breaker state machine."""

    def test_circuit_breaker_starts_closed(self):
        """Circuit should start in CLOSED state."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_circuit_state_enum_values(self):
        """CircuitState should have CLOSED, OPEN, HALF_OPEN states."""
        from llm_council.gateway.circuit_breaker import CircuitState

        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestCircuitBreakerConfig:
    """Test circuit breaker configuration."""

    def test_default_config(self):
        """Circuit breaker should have sensible defaults."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()

        assert cb.failure_threshold >= 3  # At least 3 failures to trip
        assert cb.success_threshold >= 1  # At least 1 success to close
        assert cb.timeout_seconds >= 30  # At least 30s recovery timeout

    def test_custom_config(self):
        """Circuit breaker should accept custom configuration."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            timeout_seconds=60,
        )

        assert cb.failure_threshold == 5
        assert cb.success_threshold == 2
        assert cb.timeout_seconds == 60


class TestCircuitBreakerFailures:
    """Test circuit breaker failure counting."""

    def test_record_failure_increments_count(self):
        """record_failure() should increment failure count."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=5)

        assert cb.failure_count == 0
        cb.record_failure()
        assert cb.failure_count == 1
        cb.record_failure()
        assert cb.failure_count == 2

    def test_circuit_trips_after_threshold(self):
        """Circuit should OPEN after failure_threshold failures."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()  # Third failure trips the circuit
        assert cb.state == CircuitState.OPEN

    def test_record_success_resets_failure_count(self):
        """record_success() should reset failure count."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=5)

        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        cb.record_success()
        assert cb.failure_count == 0


class TestCircuitBreakerOpen:
    """Test circuit breaker in OPEN state."""

    def test_allow_request_returns_false_when_open(self):
        """allow_request() should return False when circuit is OPEN."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()  # Trip the circuit

        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_allow_request_returns_true_when_closed(self):
        """allow_request() should return True when circuit is CLOSED."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()

        assert cb.allow_request() is True


class TestCircuitBreakerHalfOpen:
    """Test circuit breaker in HALF_OPEN state."""

    def test_circuit_transitions_to_half_open_after_timeout(self):
        """Circuit should transition from OPEN to HALF_OPEN after timeout."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState
        import time

        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.1)

        cb.record_failure()  # Trip the circuit
        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.15)

        # Should transition to HALF_OPEN when checking
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_limited_requests(self):
        """HALF_OPEN state should allow limited requests to test recovery."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState
        import time

        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.1)

        cb.record_failure()  # Trip
        time.sleep(0.15)  # Wait for recovery timeout

        # First request allowed (transitions to HALF_OPEN)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_success_in_half_open_closes_circuit(self):
        """Success in HALF_OPEN state should close the circuit."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState
        import time

        cb = CircuitBreaker(failure_threshold=1, success_threshold=1, timeout_seconds=0.1)

        cb.record_failure()  # Trip
        time.sleep(0.15)
        cb.allow_request()  # Transition to HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens_circuit(self):
        """Failure in HALF_OPEN state should reopen the circuit."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState
        import time

        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.1)

        cb.record_failure()  # Trip
        time.sleep(0.15)
        cb.allow_request()  # Transition to HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerMetrics:
    """Test circuit breaker metrics and observability."""

    def test_get_stats_returns_metrics(self):
        """get_stats() should return current metrics."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=5)

        cb.record_failure()
        cb.record_failure()

        stats = cb.get_stats()

        assert stats["state"] == CircuitState.CLOSED.value
        assert stats["failure_count"] == 2
        assert stats["success_count"] == 0
        assert "last_failure_time" in stats


class TestCircuitBreakerRouterIntegration:
    """Test circuit breaker integration with router."""

    def test_circuit_breaker_has_router_id(self):
        """Circuit breaker should be associated with a router."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(router_id="openrouter")
        assert cb.router_id == "openrouter"

    def test_circuit_breaker_default_router_id(self):
        """Circuit breaker should have default router_id."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        assert cb.router_id == "default"


class TestCircuitBreakerWrapper:
    """Test circuit breaker wrapper for async operations."""

    @pytest.mark.asyncio
    async def test_execute_calls_function_when_closed(self):
        """execute() should call the function when circuit is closed."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()

        async def mock_fn():
            return "success"

        result = await cb.execute(mock_fn)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_execute_raises_when_open(self):
        """execute() should raise CircuitOpenError when circuit is open."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker
        from llm_council.gateway.errors import CircuitOpenError

        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()  # Trip the circuit

        async def mock_fn():
            return "success"

        with pytest.raises(CircuitOpenError):
            await cb.execute(mock_fn)

    @pytest.mark.asyncio
    async def test_execute_records_success_on_success(self):
        """execute() should record success when function succeeds."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        cb.record_failure()  # Add a failure

        async def mock_fn():
            return "success"

        await cb.execute(mock_fn)
        assert cb.failure_count == 0  # Reset by success

    @pytest.mark.asyncio
    async def test_execute_records_failure_on_exception(self):
        """execute() should record failure when function raises."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=5)

        async def mock_fn():
            raise ValueError("Error!")

        with pytest.raises(ValueError):
            await cb.execute(mock_fn)

        assert cb.failure_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_fallback(self):
        """execute() should call fallback when circuit is open."""
        from llm_council.gateway.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()  # Trip the circuit

        async def mock_fn():
            return "primary"

        async def fallback_fn():
            return "fallback"

        result = await cb.execute(mock_fn, fallback=fallback_fn)
        assert result == "fallback"
