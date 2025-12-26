"""TDD Tests for ADR-030 Phase 3a: Enhanced Circuit Breaker.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/140

Enhanced circuit breaker features:
1. Sliding window for failure tracking (10 min default)
2. Minimum requests threshold before circuit can trip (5 requests)
3. Failure rate threshold (25%) instead of absolute count
"""

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


class TestEnhancedCircuitBreakerConfig:
    """Test EnhancedCircuitBreakerConfig dataclass."""

    def test_config_has_required_fields(self):
        """Config should have all required fields with defaults."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert hasattr(config, "failure_threshold")
        assert hasattr(config, "min_requests")
        assert hasattr(config, "window_seconds")
        assert hasattr(config, "cooldown_seconds")
        assert hasattr(config, "half_open_max_requests")
        assert hasattr(config, "half_open_success_threshold")

    def test_config_default_failure_threshold(self):
        """Default failure threshold should be 0.25 (25%)."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert config.failure_threshold == 0.25

    def test_config_default_min_requests(self):
        """Default min_requests should be 5."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert config.min_requests == 5

    def test_config_default_window_seconds(self):
        """Default window should be 600 seconds (10 minutes)."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert config.window_seconds == 600

    def test_config_default_cooldown_seconds(self):
        """Default cooldown should be 1800 seconds (30 minutes)."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert config.cooldown_seconds == 1800

    def test_config_default_half_open_max_requests(self):
        """Default half_open_max_requests should be 3."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert config.half_open_max_requests == 3

    def test_config_default_half_open_success_threshold(self):
        """Default half_open_success_threshold should be 0.67 (2/3)."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert config.half_open_success_threshold == pytest.approx(0.67, abs=0.01)

    def test_config_custom_values(self):
        """Config should accept custom values."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig(
            failure_threshold=0.50,
            min_requests=10,
            window_seconds=300,
            cooldown_seconds=3600,
        )
        assert config.failure_threshold == 0.50
        assert config.min_requests == 10
        assert config.window_seconds == 300
        assert config.cooldown_seconds == 3600


class TestSlidingWindow:
    """Test sliding window failure tracking."""

    def test_sliding_window_prunes_old_requests(self):
        """Requests older than window_seconds should be pruned."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        # Use a 60-second window for testing
        config = EnhancedCircuitBreakerConfig(window_seconds=60, min_requests=2)
        breaker = EnhancedCircuitBreaker(config)

        # Record failures at different times
        now = time.time()

        # Old failure (should be pruned)
        with patch("time.time", return_value=now - 120):  # 2 minutes ago
            breaker.record_failure()

        # Recent failure (should be kept)
        with patch("time.time", return_value=now):
            breaker.record_failure()

        # After pruning, only 1 failure should remain
        assert breaker.failure_count_in_window() == 1

    def test_sliding_window_default_10_minutes(self):
        """Default window should be 10 minutes (600 seconds)."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig()
        assert config.window_seconds == 600

    def test_failure_rate_calculated_within_window(self):
        """Failure rate should be calculated from requests within window."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(
            window_seconds=60,
            min_requests=4,
            failure_threshold=0.50,  # 50%
        )
        breaker = EnhancedCircuitBreaker(config)

        # Record 2 successes and 2 failures = 50% failure rate
        breaker.record_success()
        breaker.record_success()
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.request_count_in_window() == 4
        assert breaker.failure_rate() == pytest.approx(0.50, abs=0.01)

    def test_old_requests_dont_affect_rate(self):
        """Requests outside window should not affect failure rate."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(window_seconds=60, min_requests=2)
        breaker = EnhancedCircuitBreaker(config)

        now = time.time()

        # Old failures (outside window)
        with patch("time.time", return_value=now - 120):
            breaker.record_failure()
            breaker.record_failure()

        # Recent successes (inside window)
        with patch("time.time", return_value=now):
            breaker.record_success()
            breaker.record_success()

        # Only recent requests should count: 0% failure rate
        assert breaker.failure_rate() == 0.0


class TestMinRequestsThreshold:
    """Test minimum requests threshold before circuit can trip."""

    def test_circuit_does_not_trip_below_min_requests(self):
        """Circuit should not trip when below min_requests."""
        from llm_council.gateway.circuit_breaker import (
            CircuitState,
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(
            min_requests=5,
            failure_threshold=0.25,  # 25%
        )
        breaker = EnhancedCircuitBreaker(config)

        # Record 4 failures (below min_requests of 5)
        for _ in range(4):
            breaker.record_failure()

        # Circuit should remain CLOSED (not enough data)
        assert breaker.state == CircuitState.CLOSED

    def test_circuit_trips_at_threshold_after_min_requests(self):
        """Circuit should trip when threshold exceeded after min_requests."""
        from llm_council.gateway.circuit_breaker import (
            CircuitState,
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(
            min_requests=5,
            failure_threshold=0.25,  # 25%
        )
        breaker = EnhancedCircuitBreaker(config)

        # Record 3 successes and 2 failures (5 total, 40% failure rate)
        breaker.record_success()
        breaker.record_success()
        breaker.record_success()
        breaker.record_failure()
        breaker.record_failure()

        # 40% > 25%, should trip
        assert breaker.state == CircuitState.OPEN

    def test_circuit_stays_closed_at_low_failure_rate(self):
        """Circuit should stay closed when failure rate is below threshold."""
        from llm_council.gateway.circuit_breaker import (
            CircuitState,
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(
            min_requests=5,
            failure_threshold=0.25,  # 25%
        )
        breaker = EnhancedCircuitBreaker(config)

        # Record 4 successes and 1 failure (20% failure rate)
        breaker.record_success()
        breaker.record_success()
        breaker.record_success()
        breaker.record_success()
        breaker.record_failure()

        # 20% < 25%, should stay closed
        assert breaker.state == CircuitState.CLOSED

    def test_min_requests_default_is_5(self):
        """Default min_requests should be 5."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        config = EnhancedCircuitBreakerConfig()
        assert config.min_requests == 5


class TestEnhancedCircuitBreakerStateTransitions:
    """Test state transitions for enhanced circuit breaker."""

    def test_half_open_after_cooldown(self):
        """Circuit should transition to HALF_OPEN after cooldown."""
        from llm_council.gateway.circuit_breaker import (
            CircuitState,
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(
            min_requests=2,
            failure_threshold=0.25,
            cooldown_seconds=60,  # 1 minute
        )
        breaker = EnhancedCircuitBreaker(config)

        # Trip the circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Simulate cooldown elapsed
        now = time.time()
        with patch("time.time", return_value=now + 61):
            allowed = breaker.allow_request()

        assert allowed is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        """HALF_OPEN circuit should close on sufficient successes."""
        from llm_council.gateway.circuit_breaker import (
            CircuitState,
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(
            min_requests=2,
            failure_threshold=0.50,
            cooldown_seconds=1,
            half_open_max_requests=3,
            half_open_success_threshold=0.67,  # 2/3 successes
        )
        breaker = EnhancedCircuitBreaker(config)

        # Trip and wait for cooldown
        breaker.record_failure()
        breaker.record_failure()
        time.sleep(1.1)
        breaker.allow_request()  # Transition to HALF_OPEN

        assert breaker.state == CircuitState.HALF_OPEN

        # Record 2 successes (2/3 = 0.67 success rate)
        breaker.record_success()
        breaker.record_success()

        # Circuit should close (not strictly after 2, but after evaluation)
        # Depending on implementation, might need 3rd request
        breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        """HALF_OPEN circuit should reopen on failure."""
        from llm_council.gateway.circuit_breaker import (
            CircuitState,
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(
            min_requests=2,
            failure_threshold=0.50,
            cooldown_seconds=1,
            half_open_max_requests=3,
            half_open_success_threshold=0.67,
        )
        breaker = EnhancedCircuitBreaker(config)

        # Trip and wait for cooldown
        breaker.record_failure()
        breaker.record_failure()
        time.sleep(1.1)
        breaker.allow_request()

        # Record failure in HALF_OPEN
        breaker.record_failure()

        # Should reopen
        assert breaker.state == CircuitState.OPEN


class TestEnhancedCircuitBreakerStats:
    """Test statistics and monitoring for enhanced circuit breaker."""

    def test_failure_rate_property(self):
        """Should expose failure_rate property."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig(min_requests=4)
        breaker = EnhancedCircuitBreaker(config)

        breaker.record_success()
        breaker.record_success()
        breaker.record_failure()
        breaker.record_failure()

        assert hasattr(breaker, "failure_rate")
        assert breaker.failure_rate() == pytest.approx(0.50, abs=0.01)

    def test_request_count_in_window(self):
        """Should expose request_count_in_window."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig()
        breaker = EnhancedCircuitBreaker(config)

        breaker.record_success()
        breaker.record_success()
        breaker.record_failure()

        assert breaker.request_count_in_window() == 3

    def test_failure_count_in_window(self):
        """Should expose failure_count_in_window."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig()
        breaker = EnhancedCircuitBreaker(config)

        breaker.record_success()
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.failure_count_in_window() == 2

    def test_get_stats_includes_enhanced_fields(self):
        """get_stats should include enhanced fields."""
        from llm_council.gateway.circuit_breaker import (
            EnhancedCircuitBreaker,
            EnhancedCircuitBreakerConfig,
        )

        config = EnhancedCircuitBreakerConfig()
        breaker = EnhancedCircuitBreaker(config)

        stats = breaker.get_stats()
        assert "failure_rate" in stats
        assert "request_count" in stats
        assert "window_seconds" in stats
        assert "min_requests" in stats


class TestModuleExports:
    """Test module exports."""

    def test_enhanced_config_exported(self):
        """EnhancedCircuitBreakerConfig should be exported."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreakerConfig

        assert EnhancedCircuitBreakerConfig is not None

    def test_enhanced_breaker_exported(self):
        """EnhancedCircuitBreaker should be exported."""
        from llm_council.gateway.circuit_breaker import EnhancedCircuitBreaker

        assert EnhancedCircuitBreaker is not None
