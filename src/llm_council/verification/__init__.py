"""
Verification module for ADR-034 Agent Skills Integration.

Provides context isolation, types, and transcript persistence
for work verification by LLM Council.
"""

from llm_council.verification.context import (
    ContextIsolationError,
    InvalidSnapshotError,
    IsolatedVerificationContext,
    VerificationContextManager,
    create_isolated_context,
    validate_snapshot_id,
)

__all__ = [
    # Context isolation (ADR-034 A2)
    "create_isolated_context",
    "validate_snapshot_id",
    "IsolatedVerificationContext",
    "VerificationContextManager",
    "InvalidSnapshotError",
    "ContextIsolationError",
]
