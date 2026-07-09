"""Request/response schemas for the verification API (split from api.py, #380).

Verbatim move — no logic changes. Back-compat re-exports live in api.py.
"""

import logging
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Git SHA pattern for validation
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)

# Regex for evidence source strings. Constrains the attribute value that will
# be interpolated into the rendered XML wrapper, preventing prompt-injection
# via heading collisions, attribute escapes, or newline-breakouts.
SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9._@/\-+]{1,200}$")

# Regex for caller-supplied evidence_id values. Tighter than SOURCE_PATTERN
# since ids only need to disambiguate duplicate sources.
EVIDENCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")

class EvidenceItem(BaseModel):
    """Pre-computed analysis output from an upstream tool (ADR-042).

    See ``docs/adr/ADR-042-verify-evidence-injection.md`` for the full design.
    """

    evidence_id: Optional[str] = Field(
        default=None,
        description=(
            "Caller-supplied stable identifier. Disambiguates duplicate "
            "`source` values in the disposition output. If omitted, the "
            "server assigns `auto-<request_index>`. Must match "
            "^[A-Za-z0-9._\\-]{1,64}$ when provided."
        ),
        max_length=64,
    )
    source: str = Field(
        ...,
        description=(
            "Tool name + version (e.g. 'ai-slop-detector@3.7.3'). "
            "Strictly validated against SOURCE_PATTERN to prevent "
            "prompt-injection via the rendered heading."
        ),
        min_length=1,
        max_length=200,
    )
    format: Literal["markdown", "json", "text"] = Field(
        default="markdown",
        description=(
            "Content format hint for the LLM. NOTE: format does NOT switch "
            "structural fencing — all formats are wrapped in "
            "<evidence_item> tags with tilde-fence bodies."
        ),
    )
    content: str = Field(
        ...,
        description=(
            "The evidence body. Per-item cap of 50000 chars; the per-tier "
            "budget (MAX_EVIDENCE_CHARS_RATIO) is the binding constraint."
        ),
        min_length=1,
        max_length=50_000,
    )
    strength: Literal["informational", "blocking"] = Field(
        default="informational",
        description=(
            "How Council should weigh this evidence. 'informational' is "
            "context. 'blocking' asks Council to VERIFY (confirm or reject) "
            "the finding. Council ALWAYS retains final say — strength is a "
            "hint, not a vote-binding."
        ),
    )

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if not SOURCE_PATTERN.match(v):
            raise ValueError(
                "source must match ^[A-Za-z0-9._@/\\-+]{1,200}$ "
                "(prevents prompt-injection via the rendered heading)"
            )
        return v

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not EVIDENCE_ID_PATTERN.match(v):
            raise ValueError("evidence_id must match ^[A-Za-z0-9._\\-]{1,64}$")
        return v


class EvidenceWarning(BaseModel):
    """Structured warning about evidence handling (ADR-042)."""

    evidence_id: Optional[str] = None
    request_index: int = Field(..., ge=0)
    source: str
    reason: Literal[
        "budget_overflow_dropped",
        "format_mismatch_rendered_as_text",
        "duplicate_source_disambiguated",
    ]
    detail: str
    chars_attempted: int = Field(..., ge=0)
    chars_kept: int = Field(..., ge=0)


class EvidenceDisposition(BaseModel):
    """Council's per-source verdict on an evidence item (ADR-042)."""

    evidence_id: Optional[str] = None
    request_index: int = Field(..., ge=0)
    source: str
    strength: Literal["informational", "blocking"]
    status: Literal[
        "acknowledged",
        "confirmed",
        "rejected",
        "unresolved",
        "not_reviewed_due_to_budget",
        "parser_error",
    ]
    council_confirmed: Optional[bool] = Field(
        default=None,
        description=(
            "For blocking items: True if confirmed, False if rejected, "
            "None for status in {acknowledged, unresolved, "
            "not_reviewed_due_to_budget, parser_error}. "
            "For informational items: always None."
        ),
    )
    council_rationale: Optional[str] = None


class BlockingEvidenceTooLarge(Exception):
    """Raised when a single blocking evidence item exceeds the tier budget.

    The route handler / MCP wrapper translates this to HTTP 422 (or a
    structured MCP error blob) with the offending item's index, source,
    char count, and budget. Silently dropping a blocking finding is the
    exact failure mode ADR-042 is designed to prevent.
    """

    def __init__(self, *, index: int, source: str, chars: int, budget: int) -> None:
        self.index = index
        self.source = source
        self.chars = chars
        self.budget = budget
        super().__init__(
            f"Blocking evidence item at index {index} (source={source}) "
            f"is {chars} chars; exceeds tier budget of {budget} chars."
        )


class SnapshotResolutionError(Exception):
    """Raised when caller-supplied target_paths cannot be resolved at the
    given snapshot_id (issue #340).

    Fixes the silent-failure mode where verify would send a boilerplate-only
    prompt (~916 chars) to the council, get UNCLEAR back, and instruct the
    caller to "accept and move on." The route handler / MCP wrapper maps
    this to HTTP 422 (or a structured error blob) so callers can distinguish
    "verification ran and was inconclusive" from "verification could not
    read your code."

    Common upstream causes:
      - snapshot_id is on a branch not fetched in the daemon's local clone
      - push-replication race: commit was just pushed and hasn't propagated
      - paths refer to files that don't exist at this commit
    """

    def __init__(
        self,
        *,
        snapshot_id: str,
        unresolved_paths: List[str],
        expansion_warnings: List[str],
    ) -> None:
        self.snapshot_id = snapshot_id
        self.unresolved_paths = unresolved_paths
        self.expansion_warnings = expansion_warnings
        first = unresolved_paths[0] if unresolved_paths else "<none>"
        super().__init__(
            f"None of the {len(unresolved_paths)} target_paths could be "
            f"resolved at snapshot {snapshot_id} (first: {first}). "
            "Verify the snapshot exists in the daemon's checkout and that "
            "the paths exist at that commit."
        )


# =============================================================================
# End ADR-042 Evidence Injection Types
# =============================================================================


class VerifyRequest(BaseModel):
    """Request body for POST /v1/council/verify."""

    snapshot_id: str = Field(
        ...,
        description="Git commit SHA for snapshot pinning (7-40 hex chars)",
        min_length=7,
        max_length=40,
    )
    target_paths: Optional[List[str]] = Field(
        default=None,
        description="Paths to verify (defaults to entire snapshot)",
    )
    rubric_focus: Optional[str] = Field(
        default=None,
        description="Focus area: Security, Performance, Accessibility, etc.",
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for PASS verdict",
    )
    tier: str = Field(
        default="balanced",
        description="Confidence tier for model selection: quick, balanced, high, reasoning",
        pattern="^(quick|balanced|high|reasoning)$",
    )
    # ADR-042: Evidence injection
    evidence: Optional[List[EvidenceItem]] = Field(
        default=None,
        description=(
            "Pre-computed analysis from upstream tools (ADR-042). Rendered "
            "as a Pre-computed Evidence section in the verification prompt. "
            "Carved from tier_max_chars via MAX_EVIDENCE_CHARS_RATIO BEFORE "
            "file content is sized."
        ),
        max_length=20,  # Pydantic v2: max_length on List = max_items
    )

    @field_validator("snapshot_id")
    @classmethod
    def validate_snapshot_id_format(cls, v: str) -> str:
        """Validate snapshot_id is valid git SHA."""
        if not GIT_SHA_PATTERN.match(v):
            raise ValueError("snapshot_id must be valid git SHA (7-40 hexadecimal characters)")
        return v

    @field_validator("evidence")
    @classmethod
    def validate_evidence_total_size(
        cls,
        v: Optional[List[EvidenceItem]],
    ) -> Optional[List[EvidenceItem]]:
        """ADR-042: cap total evidence content at 250k chars per request."""
        if v is None:
            return v
        total = sum(len(item.content) for item in v)
        if total > 250_000:
            raise ValueError(
                f"Total evidence content ({total} chars) exceeds 250000-char "
                "request cap. Summarise upstream before submission."
            )
        return v


class RubricScoresResponse(BaseModel):
    """Rubric scores in response."""

    accuracy: Optional[float] = Field(default=None, ge=0, le=10)
    relevance: Optional[float] = Field(default=None, ge=0, le=10)
    completeness: Optional[float] = Field(default=None, ge=0, le=10)
    conciseness: Optional[float] = Field(default=None, ge=0, le=10)
    clarity: Optional[float] = Field(default=None, ge=0, le=10)


class BlockingIssueResponse(BaseModel):
    """Blocking issue in response."""

    severity: str = Field(..., description="critical, major, or minor")
    description: str = Field(..., description="Issue description")
    location: Optional[str] = Field(default=None, description="File/line location")


class Finding(BaseModel):
    """A structured finding from the chairman (ADR-051).

    The full severity range; ``blocking_issues`` is derived from the
    ``critical`` subset (C3). Same shape as ``BlockingIssueResponse`` plus a
    ``dimension`` link, so object→object with no type break.
    """

    severity: Literal["critical", "major", "minor", "info"] = Field(
        ..., description="critical | major | minor | info"
    )
    description: str = Field(..., description="Finding description")
    location: Optional[str] = Field(
        default=None, description="File/line ('file.py:42') or 'global'/None for holistic"
    )
    dimension: Optional[str] = Field(
        default=None, description="Rubric axis this finding maps to, when derivable"
    )


class VerifyDiagnostics(BaseModel):
    """Telemetry-only diagnostics (ADR-051) — NOT control flow.

    Nested so consumers don't parse ``inner_verdict`` to bypass the
    low-confidence gate. ``verdict_evidence_mismatch`` is a defensive invariant
    assertion (should never fire under the mechanical gate).
    """

    inner_verdict: Optional[str] = Field(
        default=None, description="Structured verdict before UNCLEAR softening"
    )
    inner_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    inner_confidence_calibrated: Optional[float] = Field(default=None, ge=0, le=1)
    verdict_evidence_mismatch: Optional[str] = Field(
        default=None, description="Invariant assertion marker; None in normal operation"
    )
    findings_source: Literal["structured", "fallback"] = Field(
        default="fallback", description="Where findings came from"
    )
    fallback_reason: Optional[str] = Field(default=None)
    verdict_source: Literal["mechanical", "legacy"] = Field(
        default="legacy", description="mechanical = policy(findings); legacy = prose parse"
    )
    # ADR-051 C4 (#488): severity distribution — surfaces severity mis-labelling
    # (the mechanical gate's residual failure mode) over time.
    findings_by_severity: Dict[str, int] = Field(default_factory=dict)


class VerifyResponse(BaseModel):
    """Response body for POST /v1/council/verify."""

    verification_id: str = Field(..., description="Unique verification ID")
    verdict: str = Field(..., description="pass, fail, or unclear")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    exit_code: int = Field(..., description="0=PASS, 1=FAIL, 2=UNCLEAR")
    rubric_scores: RubricScoresResponse = Field(
        default_factory=RubricScoresResponse,
        description="Multi-dimensional rubric scores",
    )
    blocking_issues: List[BlockingIssueResponse] = Field(
        default_factory=list,
        description="Issues that caused FAIL verdict (the critical subset of findings)",
    )
    # ADR-051 (#485): additive structured findings channel. Empty until the
    # LLM_COUNCIL_STRUCTURED_FINDINGS flag emits them (C2); non-breaking.
    findings: List[Finding] = Field(
        default_factory=list,
        description="Full structured findings (all severities); blocking_issues = critical subset",
    )
    diagnostics: VerifyDiagnostics = Field(
        default_factory=VerifyDiagnostics,
        description="Telemetry-only diagnostics (inner verdict, findings_source, ...) — not control flow",
    )
    rationale: str = Field(..., description="Chairman synthesis explanation")
    transcript_location: str = Field(..., description="Path to verification transcript")
    partial: bool = Field(
        default=False,
        description="True if result is partial (timeout/error)",
    )
    # #357: distinguishes a non-deliberated failure (e.g. "input_too_large")
    # from a real verdict so callers don't treat it as a passed/accepted gate.
    error: Optional[str] = Field(
        default=None,
        description="Non-verdict error marker (e.g. 'input_too_large'); None for a real verdict",
    )
    # ADR-047 P3 (#415): screening-judge audit trail. None when screening is
    # off (default). When the ACTIVE screen short-circuited, verdict is
    # "pass" and screening.acted is True — the full council did not run.
    screening: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Screening-judge decision (mode, eligible, reasons, scores,"
            " acted). Present only when LLM_COUNCIL_SCREENING is shadow or"
            " active; acted=true means the screen short-circuited to PASS."
        ),
    )
    # ADR-047 P2 (#414): calibrated confidence — raw stays in `confidence`.
    confidence_calibrated: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Confidence after the persisted monotonic calibration mapping"
            " (.council/calibration/mapping.json; identity when absent, so it"
            " equals the raw value until a mapping is fitted). The PASS"
            " threshold uses this ONLY when LLM_COUNCIL_CALIBRATED_CONFIDENCE"
            " is enabled (default off)."
        ),
    )
    # ADR-047 P1 (#413): machine-readable UNCLEAR cause. None unless
    # verdict == "unclear" (and None on non-deliberated cap results, where
    # the `error` marker governs). Values: infra_failure | low_confidence
    # | timeout. Exit code stays 2 for compat — this field is additive.
    unclear_reason: Optional[str] = Field(
        default=None,
        description=(
            "Why the verdict is unclear: infra_failure (chairman call errored"
            " — retry after checking billing/auth), low_confidence"
            " (deliberation completed below threshold — accept-and-audit per"
            " policy), timeout (global deadline — re-tier or reduce scope)."
            " None for pass/fail."
        ),
    )
    # ADR-040: Timeout guardrail fields
    timeout_fired: bool = Field(
        default=False,
        description="True if global deadline was exceeded",
    )
    completed_stages: Optional[List[str]] = Field(
        default=None,
        description="Stages completed before timeout (e.g. ['stage1', 'stage2'])",
    )
    # ADR-034 v2.6: Directory expansion metadata (Issue #311)
    expanded_paths: Optional[List[str]] = Field(
        default=None,
        description="Files included after directory expansion",
    )
    paths_truncated: Optional[bool] = Field(
        default=None,
        description="True if MAX_FILES_EXPANSION limit was reached",
    )
    expansion_warnings: Optional[List[str]] = Field(
        default=None,
        description="Warnings from directory expansion (skipped files, etc.)",
    )
    # ADR-041: Verification telemetry fields
    timing: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Per-stage and total timing in milliseconds",
    )
    input_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Input size metrics (content_chars, tier_max_chars, num_models, num_reviewers, tier)",
    )
    # ADR-042: Evidence injection
    evidence_summary: Optional[List[EvidenceDisposition]] = Field(
        default=None,
        description=(
            "Per-evidence-item Council disposition. None when no evidence "
            "was provided. Contains one entry per submitted item — including "
            "dropped items with status=not_reviewed_due_to_budget."
        ),
    )
    evidence_warnings: Optional[List[EvidenceWarning]] = Field(
        default=None,
        description=(
            "Structured warnings about evidence handling "
            "(truncation, format errors, duplicate-source disambiguation)."
        ),
    )


def _verdict_to_exit_code(verdict: str) -> int:
    """Convert verdict to exit code."""
    if verdict == "pass":
        return 0
    elif verdict == "fail":
        return 1
    else:  # unclear
        return 2


