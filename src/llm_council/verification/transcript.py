"""
Transcript persistence for verification audit trail per ADR-034.

Provides atomic writes, directory management, and integrity validation
for verification transcripts. Each verification creates a timestamped
directory containing JSON files for each stage.

Directory structure:
    .council/logs/
    ├── 2025-12-31T10-30-00-abc123/
    │   ├── request.json
    │   ├── stage1.json
    │   ├── stage2.json
    │   ├── stage3.json
    │   └── result.json
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class TranscriptError(Exception):
    """Base exception for transcript operations."""

    pass


class TranscriptNotFoundError(TranscriptError):
    """Raised when a transcript or stage is not found."""

    pass


class TranscriptIntegrityError(TranscriptError):
    """Raised when transcript integrity validation fails."""

    pass


def get_transcript_path() -> Path:
    """
    Get the path for transcript storage.

    Priority:
    1. LLM_COUNCIL_TRANSCRIPT_PATH environment variable
    2. .council/logs relative to current working directory

    Returns:
        Path to transcript storage directory
    """
    env_path = os.environ.get("LLM_COUNCIL_TRANSCRIPT_PATH")
    if env_path:
        return Path(env_path)

    return Path.cwd() / ".council" / "logs"


@dataclass
class TranscriptStore:
    """
    Store for verification transcripts.

    Provides atomic writes, directory management, and integrity validation.
    Each verification gets its own timestamped directory.
    """

    base_path: Path
    readonly: bool = False
    _verification_dirs: Dict[str, Path] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure base directory exists unless readonly."""
        if not self.readonly:
            self.base_path.mkdir(parents=True, exist_ok=True)

    def create_verification_directory(self, verification_id: str) -> Path:
        """
        Create a timestamped directory for a verification.

        Args:
            verification_id: The verification identifier

        Returns:
            Path to the created directory

        Raises:
            TranscriptError: If in readonly mode
        """
        if self.readonly:
            raise TranscriptError("Cannot create directory in readonly mode")

        # Format: 2025-12-31T10-30-00-abc123
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        dir_name = f"{timestamp}-{verification_id}"

        path = self.base_path / dir_name
        path.mkdir(parents=True, exist_ok=True)

        # Cache the mapping for later retrieval
        self._verification_dirs[verification_id] = path

        return path

    def _find_verification_dir(self, verification_id: str) -> Path:
        """
        Find the directory for a verification ID.

        Searches cached mappings first, then scans base_path.

        Args:
            verification_id: The verification identifier

        Returns:
            Path to the verification directory

        Raises:
            TranscriptNotFoundError: If directory not found
        """
        # Check cache first
        if verification_id in self._verification_dirs:
            path = self._verification_dirs[verification_id]
            if path.exists():
                return path

        # Scan base_path for matching directory
        if self.base_path.exists():
            for item in self.base_path.iterdir():
                if item.is_dir() and item.name.endswith(f"-{verification_id}"):
                    self._verification_dirs[verification_id] = item
                    return item

        raise TranscriptNotFoundError(f"No transcript found for verification: {verification_id}")

    def write_stage(self, verification_id: str, stage: str, data: Dict[str, Any]) -> Path:
        """
        Write stage data atomically to the transcript.

        Uses atomic rename pattern: write to temp file, then rename.
        This ensures either complete success or no partial writes.

        Args:
            verification_id: The verification identifier
            stage: Stage name (request, stage1, stage2, stage3, result)
            data: Stage data to write

        Returns:
            Path to the written file

        Raises:
            TranscriptError: If in readonly mode
            TranscriptNotFoundError: If verification directory not found
        """
        if self.readonly:
            raise TranscriptError("Cannot write in readonly mode")

        verification_dir = self._find_verification_dir(verification_id)
        target_path = verification_dir / f"{stage}.json"

        # Atomic write pattern: write to temp, then rename
        fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=verification_dir, prefix=f"{stage}_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, default=str)

            # Atomic rename
            os.rename(tmp_path, target_path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return target_path

    def read_stage(self, verification_id: str, stage: str) -> Dict[str, Any]:
        """
        Read stage data from a transcript.

        Args:
            verification_id: The verification identifier
            stage: Stage name to read

        Returns:
            Stage data as dictionary

        Raises:
            TranscriptNotFoundError: If stage file not found
        """
        verification_dir = self._find_verification_dir(verification_id)
        stage_path = verification_dir / f"{stage}.json"

        if not stage_path.exists():
            raise TranscriptNotFoundError(
                f"Stage '{stage}' not found for verification: {verification_id}"
            )

        with open(stage_path) as f:
            return json.load(f)

    def read_all_stages(self, verification_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Read all stages from a transcript.

        Args:
            verification_id: The verification identifier

        Returns:
            Dictionary mapping stage names to stage data
        """
        verification_dir = self._find_verification_dir(verification_id)

        stages = {}
        for stage_file in verification_dir.glob("*.json"):
            stage_name = stage_file.stem
            with open(stage_file) as f:
                stages[stage_name] = json.load(f)

        return stages

    def list_verifications(self) -> List[Dict[str, Any]]:
        """
        List all verifications in the store.

        Returns:
            List of verification metadata dictionaries
        """
        verifications: List[Dict[str, Any]] = []

        if not self.base_path.exists():
            return verifications

        for item in sorted(self.base_path.iterdir(), reverse=True):
            if item.is_dir():
                # Parse directory name: 2025-12-31T10-30-00-abc123
                parts = item.name.rsplit("-", 1)
                if len(parts) == 2:
                    verification_id = parts[1]
                    timestamp_str = parts[0]

                    verifications.append(
                        {
                            "verification_id": verification_id,
                            "directory": item.name,
                            "path": str(item),
                            "timestamp": timestamp_str,
                        }
                    )

        return verifications

    def compute_integrity_hash(self, verification_id: str) -> str:
        """
        Compute SHA256 hash of all transcript contents.

        Includes all stage files sorted by name for determinism.

        Args:
            verification_id: The verification identifier

        Returns:
            SHA256 hex digest
        """
        verification_dir = self._find_verification_dir(verification_id)

        hasher = hashlib.sha256()

        # Process files in sorted order for determinism
        for stage_file in sorted(verification_dir.glob("*.json")):
            # Hash the filename and content
            hasher.update(stage_file.name.encode("utf-8"))
            with open(stage_file, "rb") as f:
                hasher.update(f.read())

        return hasher.hexdigest()

    def validate_integrity(self, verification_id: str, expected_hash: str) -> None:
        """
        Validate transcript integrity against expected hash.

        Args:
            verification_id: The verification identifier
            expected_hash: Expected SHA256 hex digest

        Raises:
            TranscriptIntegrityError: If hash doesn't match
        """
        actual_hash = self.compute_integrity_hash(verification_id)

        if actual_hash != expected_hash:
            raise TranscriptIntegrityError(
                f"Integrity check failed for verification {verification_id}: "
                f"expected {expected_hash}, got {actual_hash}"
            )


def create_transcript_store(
    base_path: Optional[Path] = None,
    readonly: bool = False,
) -> TranscriptStore:
    """
    Create a transcript store.

    Args:
        base_path: Path to store transcripts (defaults to get_transcript_path())
        readonly: If True, reject write operations

    Returns:
        Configured TranscriptStore instance
    """
    if base_path is None:
        base_path = get_transcript_path()

    return TranscriptStore(base_path=base_path, readonly=readonly)
