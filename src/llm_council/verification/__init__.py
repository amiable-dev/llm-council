"""
Verification module for ADR-034 Agent Skills Integration.

Provides types, context isolation, transcript persistence, and API
for structured work verification using LLM Council deliberation.
"""

from llm_council.verification.context import (
    ContextIsolationError,
    InvalidSnapshotError,
    IsolatedVerificationContext,
    VerificationContextManager,
    create_isolated_context,
    validate_snapshot_id,
)
from llm_council.verification.transcript import (
    TranscriptError,
    TranscriptIntegrityError,
    TranscriptNotFoundError,
    TranscriptStore,
    create_transcript_store,
    get_transcript_path,
)
from llm_council.verification.types import (
    AgentIdentifier,
    BlockingIssue,
    ConsensusResult,
    IssueSeverity,
    RubricScores,
    VerdictType,
    VerificationContext,
    VerificationRequest,
    VerificationResult,
    VerifierResponse,
)

__all__ = [
    # Types (ADR-034 A1)
    "AgentIdentifier",
    "BlockingIssue",
    "ConsensusResult",
    "IssueSeverity",
    "RubricScores",
    "VerdictType",
    "VerificationContext",
    "VerificationRequest",
    "VerificationResult",
    "VerifierResponse",
    # Context isolation (ADR-034 A2)
    "create_isolated_context",
    "validate_snapshot_id",
    "IsolatedVerificationContext",
    "VerificationContextManager",
    "InvalidSnapshotError",
    "ContextIsolationError",
    # Transcript persistence (ADR-034 A3)
    "create_transcript_store",
    "get_transcript_path",
    "TranscriptStore",
    "TranscriptError",
    "TranscriptNotFoundError",
    "TranscriptIntegrityError",
]

# API exports (ADR-034 A4) - requires fastapi optional dependency
# Import conditionally to avoid breaking when fastapi is not installed
try:
    from llm_council.verification.api import router as verification_router
    from llm_council.verification.api import run_verification

    __all__.extend(["verification_router", "run_verification"])
except ImportError:
    # FastAPI not installed - API not available
    # Users should install with: pip install llm-council-core[http]
    verification_router = None  # type: ignore
    run_verification = None  # type: ignore
