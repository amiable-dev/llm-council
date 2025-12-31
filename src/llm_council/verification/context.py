"""
Context isolation for verification per ADR-034.

Provides isolated execution contexts for verification to ensure:
1. Fresh state for each verification (no session bleed)
2. Snapshot pinning via validated git SHA
3. Thread-safe concurrent verification support
4. Reproducibility through deterministic hashing

Context isolation is critical for verification integrity - the verifier
should not be biased by previous prompts or session history.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


class InvalidSnapshotError(ValueError):
    """Raised when a snapshot ID is invalid."""

    pass


class ContextIsolationError(RuntimeError):
    """Raised when context isolation is violated."""

    pass


# Git SHA validation pattern
# Valid: 7-40 hexadecimal characters
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


def validate_snapshot_id(snapshot_id: Optional[str]) -> bool:
    """
    Validate a git commit SHA snapshot ID.

    Args:
        snapshot_id: The snapshot ID to validate (git SHA)

    Returns:
        True if valid

    Raises:
        InvalidSnapshotError: If the snapshot ID is invalid
    """
    if snapshot_id is None:
        raise InvalidSnapshotError("Snapshot ID cannot be None")

    if not snapshot_id:
        raise InvalidSnapshotError("Snapshot ID cannot be empty")

    if len(snapshot_id) < 7:
        raise InvalidSnapshotError(f"Snapshot ID too short: {len(snapshot_id)} chars (minimum 7)")

    if len(snapshot_id) > 40:
        raise InvalidSnapshotError(f"Snapshot ID too long: {len(snapshot_id)} chars (maximum 40)")

    if not GIT_SHA_PATTERN.match(snapshot_id):
        raise InvalidSnapshotError(
            f"Invalid snapshot ID format: must be hexadecimal (got '{snapshot_id}')"
        )

    return True


def _compute_reproducibility_hash(
    snapshot_id: str,
    rubric_focus: Optional[str] = None,
) -> str:
    """
    Compute a reproducibility hash from verification inputs.

    Same inputs should always produce the same hash, enabling
    verification of reproducibility across runs.
    """
    hasher = hashlib.sha256()
    hasher.update(snapshot_id.encode("utf-8"))
    if rubric_focus:
        hasher.update(rubric_focus.encode("utf-8"))
    return hasher.hexdigest()[:16]


@dataclass
class IsolatedVerificationContext:
    """
    An isolated context for verification execution.

    Each verification runs in its own isolated context to prevent:
    - Session state bleeding between verifications
    - Bias from previous conversation history
    - Cross-contamination of concurrent verifications
    """

    context_id: str
    snapshot_id: str
    created_at: datetime
    rubric_focus: Optional[str] = None
    inherited_from_session: bool = False
    reproducibility_hash: str = ""

    # Internal state storage (isolated per context)
    _state: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Compute reproducibility hash after initialization."""
        if not self.reproducibility_hash:
            self.reproducibility_hash = _compute_reproducibility_hash(
                self.snapshot_id,
                self.rubric_focus,
            )

    def set_state(self, key: str, value: Any) -> None:
        """Set a state value in this context."""
        self._state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a state value from this context."""
        return self._state.get(key, default)

    def clear_state(self) -> None:
        """Clear all state in this context."""
        self._state.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dictionary."""
        return {
            "context_id": self.context_id,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at.isoformat(),
            "rubric_focus": self.rubric_focus,
            "inherited_from_session": self.inherited_from_session,
            "reproducibility_hash": self.reproducibility_hash,
        }


def create_isolated_context(
    snapshot_id: str,
    rubric_focus: Optional[str] = None,
) -> IsolatedVerificationContext:
    """
    Create a new isolated verification context.

    Each call creates a fresh context with:
    - Unique context ID
    - Validated snapshot ID
    - Fresh state (not inherited from session)
    - Reproducibility hash for verification

    Args:
        snapshot_id: Git commit SHA for snapshot pinning
        rubric_focus: Optional focus area (Security, Performance, etc.)

    Returns:
        A new isolated verification context

    Raises:
        InvalidSnapshotError: If snapshot_id is invalid
    """
    # Validate snapshot ID
    validate_snapshot_id(snapshot_id)

    # Generate unique context ID
    context_id = str(uuid.uuid4())

    return IsolatedVerificationContext(
        context_id=context_id,
        snapshot_id=snapshot_id,
        created_at=datetime.utcnow(),
        rubric_focus=rubric_focus,
        inherited_from_session=False,
    )


class VerificationContextManager:
    """
    Context manager for verification execution with isolation guarantees.

    Provides:
    - Automatic context creation and cleanup
    - Duration tracking
    - Reentry prevention
    - Exception-safe cleanup

    Can be used as sync or async context manager.
    """

    def __init__(
        self,
        snapshot_id: str,
        rubric_focus: Optional[str] = None,
    ):
        self.snapshot_id = snapshot_id
        self.rubric_focus = rubric_focus
        self._context: Optional[IsolatedVerificationContext] = None
        self._is_active = False
        self._start_time: Optional[float] = None
        self._duration_ms: Optional[float] = None

    @property
    def is_active(self) -> bool:
        """Check if the context manager is currently active."""
        return self._is_active

    @property
    def duration_ms(self) -> Optional[float]:
        """Get the duration of the context execution in milliseconds."""
        return self._duration_ms

    def _enter(self) -> IsolatedVerificationContext:
        """Common enter logic for sync and async."""
        if self._is_active:
            raise ContextIsolationError(
                "Context manager reentry not allowed - " "verification contexts must be isolated"
            )

        self._context = create_isolated_context(
            snapshot_id=self.snapshot_id,
            rubric_focus=self.rubric_focus,
        )
        self._is_active = True
        self._start_time = time.perf_counter()
        return self._context

    def _exit(self) -> None:
        """Common exit logic for sync and async."""
        if self._start_time is not None:
            self._duration_ms = (time.perf_counter() - self._start_time) * 1000

        self._is_active = False
        if self._context:
            self._context.clear_state()

    def __enter__(self) -> IsolatedVerificationContext:
        """Enter sync context manager."""
        return self._enter()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit sync context manager."""
        self._exit()

    async def __aenter__(self) -> IsolatedVerificationContext:
        """Enter async context manager."""
        return self._enter()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        self._exit()
