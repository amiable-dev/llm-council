"""Jury Mode verdict types for LLM Council (ADR-025b).

This module implements verdict typing that transforms the council from a
"Summary Generator" into a "Decision Engine" for high-stakes automated decisions.

Verdict Types:
- SYNTHESIS: Default behavior, unstructured natural language output
- BINARY: Go/no-go decisions (approved/rejected)
- TIE_BREAKER: Chairman resolves deadlocked decisions

Reference: ADR-025b Council Validation (2025-12-23)
Council Consensus: 4/4 models agreed Binary + Tie-Breaker are high-value/low-effort

Example Usage:
    from llm_council.verdict import VerdictType, VerdictResult

    # Request binary verdict
    result = await run_full_council(
        query="Should we deploy this PR?",
        verdict_type=VerdictType.BINARY
    )

    if result.verdict == "approved":
        deploy()
"""

import json

from llm_council.json_extract import extract_json_object
import logging
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    # ADR-042: only used for type hints; deferred import breaks the
    # circular dependency at runtime (verdict.py is imported by api.py).
    from llm_council.verification.api import (
        EvidenceDisposition,
        EvidenceItem,
        EvidenceWarning,
    )

logger = logging.getLogger(__name__)


class VerdictType(Enum):
    """Types of council verdicts.

    SYNTHESIS: Default behavior - Chairman produces free-form synthesis (backward compatible)
    BINARY: Go/no-go decision - returns approved/rejected with confidence
    TIE_BREAKER: Deadlock resolution - Chairman breaks tie with explicit rationale
    """

    SYNTHESIS = "synthesis"
    BINARY = "binary"
    TIE_BREAKER = "tie_breaker"


@dataclass
class VerdictResult:
    """Result from council deliberation with verdict typing.

    Attributes:
        verdict_type: The type of verdict rendered (SYNTHESIS, BINARY, TIE_BREAKER)
        verdict: The actual verdict ("approved"/"rejected" for binary, or synthesis text)
        confidence: Confidence score from 0.0 to 1.0
        rationale: Explanation of the decision basis
        dissent: Optional minority opinion from Stage 2 extraction
        deadlocked: True if tie-breaker was used to resolve deadlock
        borda_spread: Spread between highest and lowest Borda scores
    """

    verdict_type: VerdictType
    verdict: str
    confidence: float
    rationale: str
    dissent: Optional[str] = None
    deadlocked: bool = False
    borda_spread: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "verdict_type": self.verdict_type.value,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "dissent": self.dissent,
            "deadlocked": self.deadlocked,
            "borda_spread": self.borda_spread,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerdictResult":
        """Create VerdictResult from dictionary."""
        verdict_type = verdict_type_from_string(data["verdict_type"])
        return cls(
            verdict_type=verdict_type,
            verdict=data["verdict"],
            confidence=data["confidence"],
            rationale=data["rationale"],
            dissent=data.get("dissent"),
            deadlocked=data.get("deadlocked", False),
            borda_spread=data.get("borda_spread", 0.0),
        )


def get_default_verdict_type() -> VerdictType:
    """Return the default verdict type for backward compatibility."""
    return VerdictType.SYNTHESIS


def verdict_type_from_string(s: str) -> VerdictType:
    """Convert string to VerdictType enum.

    Args:
        s: String representation ("synthesis", "binary", "tie_breaker")

    Returns:
        Corresponding VerdictType enum value

    Raises:
        ValueError: If string doesn't match any verdict type
    """
    s_lower = s.lower()
    for vt in VerdictType:
        if vt.value == s_lower:
            return vt
    raise ValueError(f"Unknown verdict type: {s}")


def detect_deadlock(borda_scores: List[float], threshold: float = 0.1) -> bool:
    """Detect if council is deadlocked based on Borda scores.

    A deadlock occurs when the top 2 scores are within the threshold,
    indicating no clear winner among the council members.

    Args:
        borda_scores: List of Borda scores for each response
        threshold: Maximum difference between top 2 scores to be considered deadlocked

    Returns:
        True if deadlocked (top 2 within threshold), False otherwise
    """
    if len(borda_scores) < 2:
        return False

    sorted_scores = sorted(borda_scores, reverse=True)
    return abs(sorted_scores[0] - sorted_scores[1]) < threshold


def calculate_borda_spread(scores: Dict[str, float]) -> float:
    """Calculate the spread between highest and lowest Borda scores.

    Args:
        scores: Dictionary mapping response labels to Borda scores

    Returns:
        Spread (max - min), or 0.0 if insufficient scores
    """
    if len(scores) < 2:
        return 0.0

    values = list(scores.values())
    return max(values) - min(values)


def _extract_json_from_text(text: str) -> str:
    """Extract JSON from text, handling markdown code blocks.

    Args:
        text: Text that may contain JSON in code blocks

    Returns:
        Extracted JSON string
    """
    # Try to extract from code block first
    code_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(code_block_pattern, text, re.DOTALL)
    if match:
        return match.group(1)

    # Otherwise, try to find raw JSON object
    json_pattern = r"\{[^{}]*\}"
    match = re.search(json_pattern, text, re.DOTALL)
    if match:
        return match.group(0)

    return text


def parse_binary_verdict(chairman_response: str) -> VerdictResult:
    """Parse chairman response into binary verdict.

    Args:
        chairman_response: Raw response from chairman model

    Returns:
        VerdictResult with BINARY type

    Raises:
        ValueError: If response cannot be parsed or verdict is invalid
    """
    # #561: use the LLM-resilient extractor, not the legacy regex. The old
    # `_extract_json_from_text` fell back to `\{[^{}]*\}` — the first BRACE-FREE
    # object — which, since ADR-051 made the payload findings-first, is
    # `findings[0]`, not the verdict. Well-formed chairman output that merely
    # omitted the closing code fence raised "Missing required field: verdict".
    # `preferred_key` skips any decoy object that precedes the real payload.
    try:
        data = extract_json_object(chairman_response, preferred_key="verdict")
    except ValueError as e:
        raise ValueError(f"Failed to parse binary verdict JSON: {e}")

    # Validate required fields
    required_fields = ["verdict", "confidence", "rationale"]
    for field_name in required_fields:
        if field_name not in data:
            raise ValueError(f"Missing required field: {field_name}")

    # Validate verdict value
    verdict = data["verdict"].lower()
    if verdict not in ["approved", "rejected"]:
        raise ValueError(f"Binary verdict must be 'approved' or 'rejected', got '{verdict}'")

    return VerdictResult(
        verdict_type=VerdictType.BINARY,
        verdict=verdict,
        confidence=float(data["confidence"]),
        rationale=data["rationale"],
    )


def parse_tie_breaker_verdict(chairman_response: str) -> VerdictResult:
    """Parse chairman response into tie-breaker verdict.

    Args:
        chairman_response: Raw response from chairman model

    Returns:
        VerdictResult with TIE_BREAKER type and deadlocked=True

    Raises:
        ValueError: If response cannot be parsed
    """
    # #561: same robust extractor as the binary parser.
    try:
        data = extract_json_object(chairman_response, preferred_key="winner")
    except ValueError as e:
        raise ValueError(f"Failed to parse tie-breaker verdict JSON: {e}")

    verdict = data.get("verdict", "").lower()
    if verdict not in ["approved", "rejected"]:
        # For tie-breaker, we allow any verdict value
        verdict = data.get("verdict", "")

    result = VerdictResult(
        verdict_type=VerdictType.TIE_BREAKER,
        verdict=verdict,
        confidence=float(data.get("confidence", 0.5)),
        rationale=data.get("rationale", ""),
        deadlocked=True,
    )

    # Log for audit trail
    logger.info(
        f"Tie-breaker verdict: {result.verdict} "
        f"(confidence={result.confidence:.2f}, "
        f"resolution={data.get('deadlock_resolution', 'N/A')})"
    )

    return result


def parse_evidence_dispositions(
    chairman_response: str,
    submitted_items: List[Tuple[int, "EvidenceItem"]],
) -> Tuple[List["EvidenceDisposition"], List["EvidenceWarning"]]:
    """Parse the evidence_dispositions JSON block from Chairman synthesis (ADR-042).

    Args:
        chairman_response: Full chairman synthesis text (may contain a verdict
            JSON block first, then the dispositions block).
        submitted_items: The (request_index, item) tuples the budgeter kept.
            Used for hallucination guard + missing-item fill.

    Returns:
        (dispositions, warnings) where:
        - dispositions is List[EvidenceDisposition] with one entry per
          submitted item (no entries for hallucinated sources).
        - warnings is List[EvidenceWarning] containing
          `duplicate_source_disambiguated` notes when ids/indices were needed.

    Failure modes (none of which raise):
        - No JSON block found → all items get status=parser_error.
        - JSON parses but structure is wrong → all items get status=parser_error.
        - Item missing from JSON but submitted → status=parser_error.
        - JSON includes a source not in submitted_items → silently dropped.
    """
    # Deferred import — verdict.py is imported by verification.api, so a
    # top-level import would create a circular dependency at runtime.
    from llm_council.verification.api import (
        EvidenceDisposition,
        EvidenceWarning,
    )

    # Build the index of submitted items by evidence_id (or auto-N fallback).
    by_id: Dict[str, Tuple[int, "EvidenceItem"]] = {}
    for req_idx, item in submitted_items:
        item_id = item.evidence_id or f"auto-{req_idx}"
        by_id[item_id] = (req_idx, item)

    # Find ALL fenced json blocks; pick the first one with evidence_dispositions key.
    fenced_blocks = re.findall(r"```(?:json)?\s*\n(.*?)```", chairman_response, re.DOTALL)
    parsed_dispositions: Optional[List[Dict[str, Any]]] = None
    for block in fenced_blocks:
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and "evidence_dispositions" in data:
            candidate = data["evidence_dispositions"]
            if isinstance(candidate, list):
                parsed_dispositions = candidate
                break

    warnings: List["EvidenceWarning"] = []

    if parsed_dispositions is None:
        # Parser-error fallback for ALL submitted items.
        return (
            [
                EvidenceDisposition(
                    evidence_id=item.evidence_id or f"auto-{req_idx}",
                    request_index=req_idx,
                    source=item.source,
                    strength=item.strength,
                    status="parser_error",
                    council_confirmed=None,
                    council_rationale=None,
                )
                for req_idx, item in submitted_items
            ],
            warnings,
        )

    # Match dispositions to submitted items by evidence_id; hallucinations
    # silently drop.
    matched: Dict[str, Dict[str, Any]] = {}
    for raw in parsed_dispositions:
        if not isinstance(raw, dict):
            continue
        ev_id = raw.get("evidence_id")
        if not isinstance(ev_id, str) or ev_id not in by_id:
            continue  # hallucinated source — drop silently
        matched[ev_id] = raw

    dispositions: List["EvidenceDisposition"] = []
    for req_idx, item in submitted_items:
        item_id = item.evidence_id or f"auto-{req_idx}"
        raw = matched.get(item_id)
        if raw is None:
            # Submitted but Chairman didn't produce a disposition — parser_error.
            dispositions.append(
                EvidenceDisposition(
                    evidence_id=item_id,
                    request_index=req_idx,
                    source=item.source,
                    strength=item.strength,
                    status="parser_error",
                    council_confirmed=None,
                    council_rationale=None,
                )
            )
            continue

        # Sanitise + validate fields.
        status_raw = raw.get("status")
        if status_raw not in {
            "acknowledged",
            "confirmed",
            "rejected",
            "unresolved",
        }:
            status_raw = "parser_error"

        if status_raw in {"confirmed", "rejected"}:
            council_confirmed: Optional[bool] = status_raw == "confirmed"
        else:
            council_confirmed = None  # Force None for other statuses.

        rationale = raw.get("council_rationale")
        if not isinstance(rationale, str):
            rationale = None

        dispositions.append(
            EvidenceDisposition(
                evidence_id=item_id,
                request_index=req_idx,
                source=item.source,
                strength=item.strength,
                status=status_raw,
                council_confirmed=council_confirmed,
                council_rationale=rationale,
            )
        )

    return dispositions, warnings


def get_chairman_prompt(
    verdict_type: VerdictType,
    query: str,
    rankings: str,
    top_candidates: str = "",
    dispositions_instruction: Optional[str] = None,
) -> str:
    """Get the appropriate chairman prompt for the verdict type.

    Args:
        verdict_type: Type of verdict to render
        query: Original user query
        rankings: Formatted rankings summary from Stage 2
        top_candidates: For tie-breaker, the top candidates within threshold
        dispositions_instruction: ADR-042 — when evidence was provided, the
            verification pipeline passes an instruction string requiring the
            Chairman to emit a fenced JSON block with evidence_dispositions.
            None when no evidence (preserves pre-ADR-042 prompt verbatim).

    Returns:
        Formatted chairman prompt string
    """
    if verdict_type == VerdictType.BINARY:
        return _get_binary_chairman_prompt(query, rankings, dispositions_instruction)
    elif verdict_type == VerdictType.TIE_BREAKER:
        return _get_tie_breaker_chairman_prompt(
            query, rankings, top_candidates, dispositions_instruction
        )
    else:
        # SYNTHESIS - use default prompt (handled elsewhere for backward compatibility)
        return _get_synthesis_chairman_prompt(query, rankings, dispositions_instruction)


def _get_binary_chairman_prompt(
    query: str,
    rankings: str,
    dispositions_instruction: Optional[str] = None,
) -> str:
    """Generate chairman prompt for binary verdict mode."""
    dispositions_block = dispositions_instruction or ""

    # ADR-051 C2: behind the flag, ask the chairman to enumerate structured
    # findings FIRST, then the verdict — so the verdict is grounded in the
    # findings ("Proof-Before-Preference"). Lazy import avoids a module cycle.
    from llm_council.verification.findings import structured_findings_enabled

    if structured_findings_enabled():
        findings_instruction = (
            "First enumerate every concrete finding, THEN render the verdict as a"
            " function of those findings. Use severity `critical` for anything"
            " that should block approval.\n\n"
        )
        json_schema = """{
  "findings": [
    {"severity": "critical|major|minor|info", "description": "...", "location": "file.py:line or null"}
  ],
  "verdict": "approved" or "rejected",
  "confidence": 0.0 to 1.0,
  "rationale": "Brief explanation grounded in the findings above"
}"""
    else:
        findings_instruction = ""
        json_schema = """{
  "verdict": "approved" or "rejected",
  "confidence": 0.0 to 1.0,
  "rationale": "Brief explanation of the decision basis"
}"""

    return f"""You are the Chairman synthesizing the council's deliberation.

The council has reviewed and ranked responses to the following query:

QUERY: {query}

Based on the rankings and evaluations below, you must render a BINARY VERDICT.

Your task: Determine whether the proposed action/answer should be APPROVED or REJECTED.

Consider:
- Overall quality and accuracy of the top-ranked responses
- Consensus among council members
- Any safety or quality concerns raised in evaluations

RANKINGS SUMMARY:
{rankings}
{dispositions_block}
{findings_instruction}Output ONLY valid JSON with no additional text:
{json_schema}"""


def _get_tie_breaker_chairman_prompt(
    query: str,
    rankings: str,
    top_candidates: str,
    dispositions_instruction: Optional[str] = None,
) -> str:
    """Generate chairman prompt for tie-breaker mode."""
    dispositions_block = dispositions_instruction or ""
    return f"""You are the Chairman resolving a DEADLOCKED deliberation.

The council is evenly split on the following query:

QUERY: {query}

You must cast the DECIDING VOTE to break the tie.

TOP CANDIDATES (within scoring threshold):
{top_candidates}

FULL RANKINGS:
{rankings}
{dispositions_block}
As Chairman, carefully consider:
1. Subtle quality differences between top candidates
2. Any edge cases or concerns raised in evaluations
3. Which response best serves the user's intent

Output ONLY valid JSON with no additional text:
{{
  "verdict": "approved" or "rejected",
  "confidence": 0.0 to 1.0,
  "rationale": "Explain which candidate you chose and why",
  "deadlock_resolution": "Brief explanation of how you broke the tie"
}}"""


def _get_synthesis_chairman_prompt(
    query: str,
    rankings: str,
    dispositions_instruction: Optional[str] = None,
) -> str:
    """Generate chairman prompt for synthesis mode (default behavior)."""
    dispositions_block = dispositions_instruction or ""
    return f"""You are the Chairman synthesizing the council's deliberation.

The council has reviewed and ranked responses to:

QUERY: {query}

RANKINGS SUMMARY:
{rankings}
{dispositions_block}
Synthesize the best elements from the top-ranked responses into a comprehensive,
well-structured final answer. Incorporate the strongest arguments and address
any concerns raised during peer review.

Provide your synthesized response:"""
