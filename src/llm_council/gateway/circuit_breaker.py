"""Circuit breaker implementation for LLM Council gateway (ADR-023).

The circuit breaker pattern prevents cascading failures by temporarily
stopping requests to a failing service, allowing it time to recover.

State Machine:
    CLOSED -> (failures >= threshold) -> OPEN
    OPEN -> (timeout expires) -> HALF_OPEN
    HALF_OPEN -> (success) -> CLOSED
    HALF_OPEN -> (failure) -> OPEN
"""

import time
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

from .errors import CircuitOpenError


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Testing recovery, limited requests allowed


class CircuitBreaker:
    """Circuit breaker for fault tolerance.

    Monitors failures and temporarily blocks requests when a service
    becomes unhealthy, preventing cascading failures.

    Example:
        cb = CircuitBreaker(failure_threshold=5, timeout_seconds=30)

        async def make_request():
            return await external_service.call()

        result = await cb.execute(make_request)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 1,
        timeout_seconds: float = 60.0,
        router_id: str = "default",
    ):
        """Initialize the circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit.
            success_threshold: Number of successes in HALF_OPEN to close circuit.
            timeout_seconds: Time to wait before transitioning from OPEN to HALF_OPEN.
            router_id: Identifier for the associated router.
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.router_id = router_id

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: float = time.time()

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Return the current failure count."""
        return self._failure_count

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

    def record_failure(self) -> None:
        """Record a failure and potentially trip the circuit."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN reopens the circuit
            self._transition_to(CircuitState.OPEN)

    def record_success(self) -> None:
        """Record a success and potentially close the circuit."""
        if self._state == CircuitState.CLOSED:
            # Reset failure count on success in CLOSED state
            self._failure_count = 0
        elif self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to(CircuitState.CLOSED)

    def allow_request(self) -> bool:
        """Check if a request should be allowed.

        Returns:
            True if the request should proceed, False otherwise.
        """
        if self._state == CircuitState.CLOSED:
            return True
        elif self._state == CircuitState.OPEN:
            # Check if timeout has expired
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.timeout_seconds:
                    self._transition_to(CircuitState.HALF_OPEN)
                    return True
            return False
        elif self._state == CircuitState.HALF_OPEN:
            # Allow limited requests in HALF_OPEN
            return True

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return current circuit breaker statistics.

        Returns:
            Dict with state, counts, and timing information.
        """
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
            "router_id": self.router_id,
        }

    async def execute(
        self,
        fn: Callable[[], Awaitable[Any]],
        fallback: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> Any:
        """Execute a function with circuit breaker protection.

        Args:
            fn: Async function to execute.
            fallback: Optional fallback function to call if circuit is open.

        Returns:
            Result of fn() or fallback().

        Raises:
            CircuitOpenError: If circuit is open and no fallback provided.
            Exception: Any exception raised by fn() is re-raised after recording failure.
        """
        if not self.allow_request():
            if fallback is not None:
                return await fallback()
            raise CircuitOpenError(
                f"Circuit is open for router {self.router_id}",
                router_id=self.router_id,
            )

        try:
            result = await fn()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise


# =============================================================================
# Enhanced Circuit Breaker (ADR-030)
# =============================================================================


from collections import deque
from dataclasses import dataclass
from typing import Deque, Tuple


@dataclass
class EnhancedCircuitBreakerConfig:
    """Configuration for enhanced circuit breaker (ADR-030).

    Attributes:
        failure_threshold: Failure rate (0-1) to trigger circuit open (default: 0.25)
        min_requests: Minimum requests before circuit can trip (default: 5)
        window_seconds: Sliding window for failure tracking (default: 600 = 10 min)
        cooldown_seconds: Time before OPEN transitions to HALF_OPEN (default: 1800 = 30 min)
        half_open_max_requests: Max requests in HALF_OPEN state (default: 3)
        half_open_success_threshold: Success rate to close circuit (default: 0.67)
    """

    failure_threshold: float = 0.25
    min_requests: int = 5
    window_seconds: int = 600
    cooldown_seconds: int = 1800
    half_open_max_requests: int = 3
    half_open_success_threshold: float = 0.67


class EnhancedCircuitBreaker:
    """Enhanced circuit breaker with sliding window and min_requests (ADR-030).

    Improvements over basic CircuitBreaker:
    1. Sliding window: Failures expire after window_seconds
    2. Minimum requests: Circuit won't trip until min_requests reached
    3. Failure rate: Uses percentage threshold instead of absolute count

    Example:
        config = EnhancedCircuitBreakerConfig(
            failure_threshold=0.25,  # 25% failure rate
            min_requests=5,
            window_seconds=600,  # 10 minutes
        )
        breaker = EnhancedCircuitBreaker(config)
        breaker.record_success()
        breaker.record_failure()
        if breaker.allow_request():
            # Make request
    """

    def __init__(
        self,
        config: Optional[EnhancedCircuitBreakerConfig] = None,
        model_id: str = "default",
    ):
        """Initialize enhanced circuit breaker.

        Args:
            config: Configuration settings (uses defaults if not provided)
            model_id: Identifier for the model this breaker protects
        """
        self._config = config or EnhancedCircuitBreakerConfig()
        self.model_id = model_id

        self._state = CircuitState.CLOSED
        self._request_history: Deque[Tuple[float, bool]] = deque()  # (timestamp, success)
        self._last_state_change: float = time.time()
        self._open_time: Optional[float] = None

        # HALF_OPEN tracking
        self._half_open_requests: int = 0
        self._half_open_successes: int = 0

    @property
    def config(self) -> EnhancedCircuitBreakerConfig:
        """Return the configuration."""
        return self._config

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state."""
        return self._state

    def _prune_old_requests(self) -> None:
        """Remove requests older than window_seconds."""
        now = time.time()
        cutoff = now - self._config.window_seconds
        while self._request_history and self._request_history[0][0] < cutoff:
            self._request_history.popleft()

    def request_count_in_window(self) -> int:
        """Return count of requests in the sliding window."""
        self._prune_old_requests()
        return len(self._request_history)

    def failure_count_in_window(self) -> int:
        """Return count of failures in the sliding window."""
        self._prune_old_requests()
        return sum(1 for _, success in self._request_history if not success)

    def failure_rate(self) -> float:
        """Return failure rate (0-1) in the sliding window.

        Returns 0.0 if no requests in window.
        """
        self._prune_old_requests()
        total = len(self._request_history)
        if total == 0:
            return 0.0
        failures = sum(1 for _, success in self._request_history if not success)
        return failures / total

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.OPEN:
            self._open_time = time.time()
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_requests = 0
            self._half_open_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._request_history.clear()

    def _evaluate_closed_state(self) -> None:
        """Evaluate whether to trip the circuit in CLOSED state."""
        self._prune_old_requests()

        # Need minimum requests before evaluating
        if len(self._request_history) < self._config.min_requests:
            return

        # Check failure rate
        if self.failure_rate() > self._config.failure_threshold:
            self._transition_to(CircuitState.OPEN)

    def record_failure(self) -> None:
        """Record a failure."""
        now = time.time()
        self._request_history.append((now, False))

        if self._state == CircuitState.CLOSED:
            self._evaluate_closed_state()
        elif self._state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN reopens the circuit
            self._transition_to(CircuitState.OPEN)

    def record_success(self) -> None:
        """Record a success."""
        now = time.time()
        self._request_history.append((now, True))

        if self._state == CircuitState.CLOSED:
            # Stay closed, but still evaluate (might reset failure count)
            pass
        elif self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            self._half_open_requests += 1

            # Check if we can close the circuit
            if self._half_open_requests >= self._config.half_open_max_requests:
                success_rate = self._half_open_successes / self._half_open_requests
                if success_rate >= self._config.half_open_success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                else:
                    self._transition_to(CircuitState.OPEN)

    def allow_request(self) -> bool:
        """Check if a request should be allowed.

        Returns:
            True if the request should proceed, False otherwise.
        """
        if self._state == CircuitState.CLOSED:
            return True
        elif self._state == CircuitState.OPEN:
            # Check if cooldown has expired
            if self._open_time is not None:
                elapsed = time.time() - self._open_time
                if elapsed >= self._config.cooldown_seconds:
                    self._transition_to(CircuitState.HALF_OPEN)
                    return True
            return False
        elif self._state == CircuitState.HALF_OPEN:
            # Allow limited requests
            return self._half_open_requests < self._config.half_open_max_requests

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return current circuit breaker statistics."""
        self._prune_old_requests()
        return {
            "state": self._state.value,
            "failure_rate": self.failure_rate(),
            "request_count": len(self._request_history),
            "failure_count": self.failure_count_in_window(),
            "window_seconds": self._config.window_seconds,
            "min_requests": self._config.min_requests,
            "failure_threshold": self._config.failure_threshold,
            "cooldown_seconds": self._config.cooldown_seconds,
            "last_state_change": self._last_state_change,
            "model_id": self.model_id,
        }
