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
