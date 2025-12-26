"""Per-Model Circuit Breaker Registry for ADR-030.

This module provides a thread-safe registry for per-model circuit breakers
with event emission on state transitions.

Usage:
    >>> from llm_council.gateway.circuit_breaker_registry import (
    ...     get_circuit_breaker,
    ...     check_circuit_breaker,
    ...     record_model_result,
    ... )
    >>>
    >>> # Get or create a circuit breaker for a model
    >>> breaker = get_circuit_breaker("openai/gpt-4o")
    >>>
    >>> # Check if requests are allowed
    >>> allowed, reason = check_circuit_breaker("openai/gpt-4o")
    >>>
    >>> # Record results (with automatic event emission)
    >>> record_model_result("openai/gpt-4o", success=True)
"""

import logging
import threading
from typing import Dict, Optional, Tuple

from .circuit_breaker import (
    CircuitState,
    EnhancedCircuitBreaker,
    EnhancedCircuitBreakerConfig,
)

logger = logging.getLogger(__name__)

# Thread-safe registry
_circuit_breakers: Dict[str, EnhancedCircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit_breaker(
    model_id: str,
    config: Optional[EnhancedCircuitBreakerConfig] = None,
) -> EnhancedCircuitBreaker:
    """Get or create a circuit breaker for a model.

    Thread-safe. If a breaker already exists for the model_id, returns
    the existing instance (config parameter is ignored in that case).

    Args:
        model_id: Full model identifier (e.g., "openai/gpt-4o")
        config: Optional config for new breakers (ignored if breaker exists)

    Returns:
        EnhancedCircuitBreaker for the model
    """
    with _registry_lock:
        if model_id not in _circuit_breakers:
            _circuit_breakers[model_id] = EnhancedCircuitBreaker(
                config=config,
                model_id=model_id,
            )
        return _circuit_breakers[model_id]


def check_circuit_breaker(model_id: str) -> Tuple[bool, Optional[str]]:
    """Check if requests to a model are allowed.

    Args:
        model_id: Full model identifier

    Returns:
        (allowed, reason) tuple:
        - allowed: True if requests should proceed
        - reason: None if allowed, or explanation string if blocked
    """
    breaker = get_circuit_breaker(model_id)

    if breaker.allow_request():
        return True, None
    else:
        return False, f"Circuit breaker open for {model_id} (state: {breaker.state.value})"


def record_model_result(model_id: str, success: bool) -> None:
    """Record a request result for a model with event emission.

    Automatically emits L4_CIRCUIT_BREAKER_OPEN or L4_CIRCUIT_BREAKER_CLOSE
    events when state transitions occur.

    Args:
        model_id: Full model identifier
        success: True if request succeeded, False if failed
    """
    breaker = get_circuit_breaker(model_id)
    old_state = breaker.state

    if success:
        breaker.record_success()
    else:
        breaker.record_failure()

    new_state = breaker.state

    # Emit events on state transitions
    if old_state != new_state:
        _emit_state_change_event(breaker, old_state, new_state)


def _emit_state_change_event(
    breaker: EnhancedCircuitBreaker,
    old_state: CircuitState,
    new_state: CircuitState,
) -> None:
    """Emit layer event for circuit breaker state change.

    Args:
        breaker: The circuit breaker that changed state
        old_state: Previous state
        new_state: New state
    """
    try:
        from ..layer_contracts import LayerEventType, emit_layer_event

        if new_state == CircuitState.OPEN:
            emit_layer_event(
                LayerEventType.L4_CIRCUIT_BREAKER_OPEN,
                {
                    "model_id": breaker.model_id,
                    "failure_rate": breaker.failure_rate(),
                    "request_count": breaker.request_count_in_window(),
                    "cooldown_seconds": breaker.config.cooldown_seconds,
                    "from_state": old_state.value,
                },
            )
            logger.warning(
                "Circuit breaker OPEN for %s (failure_rate=%.2f%%)",
                breaker.model_id,
                breaker.failure_rate() * 100,
            )
        elif new_state == CircuitState.CLOSED:
            emit_layer_event(
                LayerEventType.L4_CIRCUIT_BREAKER_CLOSE,
                {
                    "model_id": breaker.model_id,
                    "from_state": old_state.value,
                },
            )
            logger.info(
                "Circuit breaker CLOSED for %s",
                breaker.model_id,
            )

    except ImportError:
        # layer_contracts not available
        pass


def get_all_breakers() -> Dict[str, EnhancedCircuitBreaker]:
    """Return all registered circuit breakers.

    Returns:
        Dict mapping model_id to EnhancedCircuitBreaker
    """
    with _registry_lock:
        return dict(_circuit_breakers)


def _reset_registry() -> None:
    """Reset the registry (for testing only)."""
    global _circuit_breakers
    with _registry_lock:
        _circuit_breakers = {}


# Module exports
__all__ = [
    "get_circuit_breaker",
    "check_circuit_breaker",
    "record_model_result",
    "get_all_breakers",
    "_reset_registry",
]
