"""
Verification module for ADR-034 Agent Skills Integration.

Provides transcript persistence for work verification audit trails.
"""

from llm_council.verification.transcript import (
    TranscriptError,
    TranscriptIntegrityError,
    TranscriptNotFoundError,
    TranscriptStore,
    create_transcript_store,
    get_transcript_path,
)

__all__ = [
    # Transcript persistence (ADR-034 A3)
    "create_transcript_store",
    "get_transcript_path",
    "TranscriptStore",
    "TranscriptError",
    "TranscriptNotFoundError",
    "TranscriptIntegrityError",
]
