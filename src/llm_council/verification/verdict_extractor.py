"""
Verdict extraction from council deliberation per ADR-034.

Extracts verdicts, confidence scores, and rubric scores from
council stage outputs for verification results.
"""

from __future__ import annotations

import logging
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# Verdict patterns in synthesis text
APPROVED_PATTERNS = [
    r"\bAPPROVED\b",
    r"\bPASS(?:ED)?\b",
    r"\bACCEPTED\b",
    r"\bRECOMMENDED\b",
]

REJECTED_PATTERNS = [
    r"\bREJECTED\b",
    r"\bFAIL(?:ED)?\b",
    r"\bDENIED\b",
    r"\bNOT\s+RECOMMENDED\b",
]

# Default rubric dimensions
RUBRIC_DIMENSIONS = ["accuracy", "relevance", "completeness", "conciseness", "clarity"]


def extract_verdict_from_synthesis(
    stage3_result: Dict[str, Any],
) -> Tuple[str, float]:
    """
    Extract verdict and base confidence from Stage 3 synthesis.

    Analyzes the chairman's synthesis to determine if the council
    approved or rejected the verification target.

    Args:
        stage3_result: Stage 3 result with 'response' key

    Returns:
        Tuple of (verdict, base_confidence)
        - verdict: "pass", "fail", or "unclear"
        - base_confidence: 0.0-1.0 based on signal strength
    """
    # Coalesce a missing/None synthesis to "" so an empty, failed, or partial
    # stage 3 (e.g. a reasoning-only model returning null content, or a
    # timed-out synthesis) degrades to an "unclear" verdict instead of raising
    # AttributeError. `.get("response", "")` is insufficient: the key is usually
    # present with a None value, so the "" default never applies.
    response = (stage3_result or {}).get("response") or ""
    response_upper = response.upper()

    # Check for explicit verdict markers
    approved_count = 0
    rejected_count = 0

    for pattern in APPROVED_PATTERNS:
        if re.search(pattern, response_upper):
            approved_count += 1

    for pattern in REJECTED_PATTERNS:
        if re.search(pattern, response_upper):
            rejected_count += 1

    # Determine verdict based on pattern matches
    if approved_count > 0 and rejected_count == 0:
        # Clear approval signal
        confidence = min(0.95, 0.70 + (approved_count * 0.10))
        return "pass", confidence
    elif rejected_count > 0 and approved_count == 0:
        # Clear rejection signal
        confidence = min(0.95, 0.70 + (rejected_count * 0.10))
        return "fail", confidence
    elif approved_count > rejected_count:
        # Mixed signals, leaning approved
        confidence = 0.55 + (0.05 * (approved_count - rejected_count))
        return "pass", min(0.75, confidence)
    elif rejected_count > approved_count:
        # Mixed signals, leaning rejected
        confidence = 0.55 + (0.05 * (rejected_count - approved_count))
        return "fail", min(0.75, confidence)
    else:
        # No clear signal or equal signals
        return "unclear", 0.50


def extract_rubric_scores_from_rankings(
    stage2_results: List[Dict[str, Any]],
) -> Dict[str, Optional[float]]:
    """
    Extract aggregated rubric scores from Stage 2 rankings.

    Handles multiple formats:
    1. Dimension-based rubric_scores: {"accuracy": 9.0, "clarity": 8.5, ...}
    2. Per-response scores: parsed_ranking.scores = {"Response A": 10, ...}

    Args:
        stage2_results: List of Stage 2 ranking results

    Returns:
        Dictionary mapping dimension names to scores (0-10) or None
    """
    dimension_scores: Dict[str, List[float]] = {dim: [] for dim in RUBRIC_DIMENSIONS}
    response_scores: List[float] = []

    for ranking in stage2_results:
        # Format 1: Dimension-based rubric_scores (ADR-016 format)
        rubric_scores = ranking.get("rubric_scores", {})
        if isinstance(rubric_scores, dict):
            for dimension in RUBRIC_DIMENSIONS:
                if dimension in rubric_scores:
                    score = rubric_scores[dimension]
                    if isinstance(score, (int, float)) and 0 <= score <= 10:
                        dimension_scores[dimension].append(float(score))

        # Format 2: Per-response scores in parsed_ranking
        parsed = ranking.get("parsed_ranking", {})
        if isinstance(parsed, dict):
            scores = parsed.get("scores", {})
            if isinstance(scores, dict):
                for score in scores.values():
                    if isinstance(score, (int, float)) and 0 <= score <= 10:
                        response_scores.append(float(score))

    # Calculate dimension averages from rubric_scores if available
    result: Dict[str, Optional[float]] = {}
    has_dimension_scores = False

    for dimension in RUBRIC_DIMENSIONS:
        scores = dimension_scores[dimension]
        if scores:
            result[dimension] = round(statistics.mean(scores), 1)
            has_dimension_scores = True
        else:
            result[dimension] = None

    # If no dimension scores but we have response scores, derive estimates
    if not has_dimension_scores and response_scores:
        overall = round(max(response_scores), 1)
        mean_score = statistics.mean(response_scores)

        result["accuracy"] = overall
        result["clarity"] = round(mean_score, 1)
        result["completeness"] = round(mean_score * 0.9, 1)

    return result


def calculate_confidence_from_agreement(
    stage2_results: List[Dict[str, Any]],
    stage3_verdict: str,
) -> float:
    """
    Calculate confidence score based on council agreement.

    Factors in:
    - Score variance (low variance = high confidence)
    - Ranking agreement (reviewers ranking similarly = high confidence)
    - Overall score levels (high scores for pass = high confidence)
    - Number of reviewers (more reviewers = higher confidence)

    Handles multiple Stage 2 formats:
    1. parsed_ranking as list: ["Response A", "Response B", ...]
    2. parsed_ranking as dict: {"ranking": [...], "scores": {...}}

    Args:
        stage2_results: Stage 2 ranking results
        stage3_verdict: The extracted verdict ("pass", "fail", "unclear")

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not stage2_results:
        return 0.50  # No reviews = unclear

    all_scores: List[float] = []
    top_responses: List[str] = []

    for ranking in stage2_results:
        # Handle parsed_ranking in multiple formats
        parsed = ranking.get("parsed_ranking")

        if isinstance(parsed, list):
            # Format 1: Direct list of rankings
            if parsed:
                top_responses.append(parsed[0])
        elif isinstance(parsed, dict):
            # Format 2: Dict with ranking and scores
            ranking_order = parsed.get("ranking", [])
            scores = parsed.get("scores", {})

            if ranking_order:
                top_responses.append(ranking_order[0])

            if isinstance(scores, dict):
                for score in scores.values():
                    if isinstance(score, (int, float)):
                        all_scores.append(float(score))

        # Collect scores from rubric_scores (dimension-based)
        rubric_scores = ranking.get("rubric_scores", {})
        if isinstance(rubric_scores, dict):
            for score in rubric_scores.values():
                if isinstance(score, (int, float)):
                    all_scores.append(float(score))

    if not all_scores:
        return 0.50  # No scores = unclear

    # Calculate mean and variance
    mean_score = statistics.mean(all_scores)
    variance = statistics.variance(all_scores) if len(all_scores) > 1 else 0

    # Calculate ranking agreement (what % of reviewers agree on #1)
    ranking_agreement = 0.0
    if top_responses:
        from collections import Counter

        counts = Counter(top_responses)
        most_common_count = counts.most_common(1)[0][1]
        ranking_agreement = most_common_count / len(top_responses)

    # Base confidence on mean score
    # For "pass": high scores = high confidence
    # For "fail": low scores = high confidence
    if stage3_verdict == "pass":
        # Score of 8+ = high confidence, 5-8 = medium, <5 = low
        score_confidence = min(1.0, max(0.3, (mean_score - 5) / 5))
    elif stage3_verdict == "fail":
        # Score of 4 or less = high confidence in failure
        score_confidence = min(1.0, max(0.3, (5 - mean_score) / 5 + 0.5))
    else:
        # Unclear - mid-range confidence
        score_confidence = 0.50

    # Adjust for variance (lower variance = higher confidence)
    # Max variance reduction is 0.20
    variance_penalty = min(0.20, variance / 10)
    confidence = score_confidence - variance_penalty

    # Adjust for ranking agreement (higher agreement = higher confidence)
    # Up to 15% boost for unanimous agreement
    agreement_boost = ranking_agreement * 0.15
    confidence += agreement_boost

    # Adjust for number of reviewers
    # More reviewers = higher confidence (up to 10% boost)
    reviewer_boost = min(0.10, len(stage2_results) * 0.02)
    confidence += reviewer_boost

    # Clamp to valid range
    return round(max(0.0, min(1.0, confidence)), 2)


def extract_blocking_issues(
    stage3_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Extract blocking issues from Stage 3 synthesis.

    Looks for explicit issue markers in the synthesis text.

    Args:
        stage3_result: Stage 3 result with synthesis text

    Returns:
        List of blocking issue dictionaries with severity, description, location
    """
    # Same None-coalescing as extract_verdict_from_synthesis: a None synthesis
    # would otherwise make re.finditer() raise on a non-string. Treat empty/None
    # as "no blocking issues found".
    response = (stage3_result or {}).get("response") or ""
    issues: List[Dict[str, Any]] = []

    # Look for *genuinely marked* critical/major/minor issues only.
    #
    # The previous pattern `(CRITICAL|MAJOR|MINOR)[:\s]+(...)` matched the bare
    # word anywhere in prose, so approval text like "the critical issues have
    # been resolved" or "No blocking issues were identified" was extracted as a
    # CRITICAL blocking issue, fabricating gate-blocking findings (#355).
    #
    # A real marker is the severity token at the start of a line (optionally
    # bulleted and/or bold-wrapped) immediately followed by a colon, e.g.
    # "- **CRITICAL**: ...", "MAJOR: ...". Mid-sentence "critical issues" (a
    # word, not a colon, follows) no longer matches.
    issue_pattern = (
        r"^\s*(?:[-*]\s+)?(?:\*\*)?"
        r"(?P<severity>CRITICAL|MAJOR|MINOR)"
        r"(?:\*\*)?\s*:\s+(?P<description>[^\n]+)"
    )

    for match in re.finditer(issue_pattern, response, re.IGNORECASE | re.MULTILINE):
        severity = match.group("severity").lower()
        description = match.group("description").strip()

        # Try to extract location from description
        location = None
        loc_match = re.search(r"(?:in|at)\s+([^\s]+\.py:\d+|\S+\.py)", description)
        if loc_match:
            location = loc_match.group(1)

        issues.append(
            {
                "severity": severity,
                "description": description,
                "location": location,
            }
        )

    return issues


def _verdict_from_structured(
    verdict_result: Optional[Any],
) -> Optional[Tuple[str, float]]:
    """Map a structured BINARY ``VerdictResult`` to (verdict, confidence).

    Returns ``("pass"|"fail", confidence)`` when ``verdict_result`` is a valid
    binary verdict ("approved"/"rejected"), else ``None`` so the caller falls
    back to prose-based extraction. Defensive against malformed objects so a
    bad verdict object never crashes verification.
    """
    if verdict_result is None:
        return None
    raw = getattr(verdict_result, "verdict", None)
    if not isinstance(raw, str):
        return None
    raw = raw.strip().lower()
    if raw == "approved":
        verdict = "pass"
    elif raw == "rejected":
        verdict = "fail"
    else:
        return None
    try:
        confidence = round(float(getattr(verdict_result, "confidence", 0.0)), 2)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return verdict, confidence


def build_verification_result(
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    stage3_result: Dict[str, Any],
    confidence_threshold: float = 0.7,
    verdict_result: Optional[Any] = None,
    calibrate: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Build complete verification result from council stages.

    Combines all stage outputs into a structured verification result
    per ADR-034 specification.

    Args:
        stage1_results: Individual model responses
        stage2_results: Peer review rankings with rubric scores
        stage3_result: Chairman synthesis
        confidence_threshold: Minimum confidence for PASS verdict
        verdict_result: Optional structured BINARY ``VerdictResult`` produced by
            the chairman (ADR-025b). When present and valid this is authoritative
            (#355): the council's own go/no-go decision is trusted over a fragile
            regex over the synthesis prose, which mis-reads negated mentions
            ("no failures", "critical issues resolved") as rejection signals.

    Returns:
        Verification result dictionary
    """
    rubric_scores = extract_rubric_scores_from_rankings(stage2_results)

    # PR #519: when chairman synthesis is disabled, stage3_result carries the
    # raw top-ranked Stage-1 answer (not a verdict) and verdict_result is
    # always None. Neither the legacy regex extractor nor the ADR-051
    # structured-findings parser were designed to score an arbitrary answer
    # to the original query — running them here would silently fabricate a
    # pass/fail verdict with a confidence number that has no relationship to
    # an actual review. Report this state explicitly instead: an "unclear"
    # verdict with a dedicated diagnostics/unclear_reason marker so BINARY
    # callers (council-verify/council-gate) can't mistake it for a real
    # deliberated decision.
    if isinstance(stage3_result, dict) and stage3_result.get("chairman_disabled") is True:
        return {
            "verdict": "unclear",
            "confidence": 0.0,
            "confidence_calibrated": None,
            "rubric_scores": rubric_scores,
            "blocking_issues": [],
            "rationale": (
                "Chairman synthesis was disabled (chairman_disabled=true); the "
                "returned response is the top-ranked peer answer, not a council "
                "verdict, so no automated pass/fail decision was made."
            ),
            "findings": [],
            "diagnostics": {
                "findings_source": "skipped",
                "verdict_source": "chairman_disabled",
            },
        }

    # ADR-051 C5 (#489): capture the pre-softening state whenever an
    # "approved @ c" is softened to "unclear" (c < threshold), for the
    # telemetry-only diagnostics block.
    inner_verdict: Optional[str] = None
    inner_confidence: Optional[float] = None
    inner_confidence_calibrated: Optional[float] = None

    structured_verdict = _verdict_from_structured(verdict_result)
    if structured_verdict is not None:
        # Trust the council's structured BINARY verdict.
        verdict, confidence = structured_verdict
        # An explicit approval whose self-reported confidence is below the gate
        # threshold is the only case we soften to "unclear".
        # ADR-047 P2 (#414): behind the flag, the gate compares the CALIBRATED
        # confidence (raw is always reported alongside).
        effective = calibrate(confidence) if calibrate is not None else confidence
        if verdict == "pass" and effective < confidence_threshold:
            inner_verdict, inner_confidence, inner_confidence_calibrated = (
                "pass", confidence, effective,
            )
            verdict = "unclear"
    else:
        # Fallback: legacy regex extraction over the synthesis prose.
        verdict, base_confidence = extract_verdict_from_synthesis(stage3_result)
        agreement_confidence = calculate_confidence_from_agreement(stage2_results, verdict)
        # Weighted average of synthesis confidence and reviewer agreement.
        confidence = round((base_confidence * 0.4) + (agreement_confidence * 0.6), 2)
        effective = calibrate(confidence) if calibrate is not None else confidence
        if verdict == "pass" and effective < confidence_threshold:
            inner_verdict, inner_confidence, inner_confidence_calibrated = (
                "pass", confidence, effective,
            )
            verdict = "unclear"

    # Extract blocking issues (only for fail/unclear)
    blocking_issues = []
    if verdict in ("fail", "unclear"):
        blocking_issues = extract_blocking_issues(stage3_result)

    # Get rationale from synthesis (None-coalesced like the sibling
    # extractors — a missing/None stage3_result must not raise, #434 review)
    rationale = (stage3_result or {}).get("response") or "No synthesis available."

    result = {
        "verdict": verdict,
        "confidence": confidence,
        # ADR-047 P2: None when no calibrator was applied here — the API
        # layer fills it from the persisted mapping for reporting either way.
        "confidence_calibrated": calibrate(confidence) if calibrate is not None else None,
        "rubric_scores": rubric_scores,
        "blocking_issues": blocking_issues,
        "rationale": rationale,
    }

    # ADR-051 (#486 C2 emission / #487 C3 mechanical verdict): behind the flag,
    # parse the chairman's structured findings and — when they parse cleanly —
    # DERIVE the verdict and blocking_issues from them (the mechanical gate),
    # replacing the legacy prose-scraped values. Soft-fail to the legacy path.
    from .findings import parse_findings, structured_findings_enabled, verdict_policy

    findings_dicts: List[Dict[str, Any]] = []
    diagnostics: Dict[str, Any] = {"findings_source": "fallback", "verdict_source": "legacy"}

    # #544: record how the chairman's ADR-025b BINARY verdict block fared. This is
    # set UNCONDITIONALLY — outside the structured-findings flag — because a
    # malformed verdict is exactly as informative when the flag is off, and
    # `verdict_source="legacy"` cannot otherwise be told apart from "flag off".
    # `fallback_reason` describes the FINDINGS parser and is a different signal.
    _verdict_parse_error = (stage3_result or {}).get("verdict_parse_error")
    if _verdict_parse_error:
        diagnostics["verdict_parse"] = "error"
        diagnostics["verdict_parse_error"] = _verdict_parse_error
    elif verdict_result is not None:
        diagnostics["verdict_parse"] = "ok"
    else:
        # No structured verdict and no parse error: a non-BINARY run, a chairman
        # error, or a disabled chairman. Not a degradation signal.
        diagnostics["verdict_parse"] = "absent"
    if structured_findings_enabled():
        try:
            parsed, source, reason = parse_findings((stage3_result or {}).get("response") or "")
            findings_dicts = [f.model_dump() for f in parsed]
            diagnostics["findings_source"] = source
            if reason:
                diagnostics["fallback_reason"] = reason
            if source == "structured":
                # C3 mechanical gate: verdict = policy(findings) (pure host code);
                # blocking_issues = the critical subset. Compute EVERYTHING into
                # locals first, then mutate `result` atomically at the end — so a
                # mid-computation exception leaves the legacy result intact rather
                # than a half-updated verdict/confidence (Council C5 round 2).
                # #560: the verdict is `policy(findings)` and NOTHING else. It is
                # no longer softened by a confidence heuristic. Across 539 local
                # transcripts that softening turned 21 of 22 chairman-approved
                # mechanical runs into `unclear` (4.5% pass vs 81% on the legacy
                # path) because `calculate_confidence_from_agreement` scores the
                # QUALITY OF THE COUNCIL'S REVIEWS, directionally -- so a
                # well-argued FAIL was reported at the 0.3 floor. Neither that
                # number nor the chairman's self-report (min 0.85, stdev 0.034 --
                # saturated, non-discriminating) is a usable gate input.
                policy_verdict = verdict_policy(parsed)
                has_critical = any(f.severity == "critical" for f in parsed)

                # Invariant is asserted on the PURE function, before any gating,
                # so a gate-induced `unclear` can't mask a policy violation.
                mismatch = None
                if (policy_verdict == "fail") != has_critical:
                    mismatch = (
                        "fail_without_critical"
                        if policy_verdict == "fail"
                        else "nonfail_with_critical"
                    )

                # #560(c): report a confidence that corresponds to the verdict.
                # The chairman's self-report is used only when its own verdict
                # CONCORDS with policy(findings) (the C5 round-1 concern); the
                # agreement heuristic is retained, honestly named, as fallback.
                deliberation_agreement = calculate_confidence_from_agreement(
                    stage2_results, policy_verdict
                )
                chairman_verdict = getattr(verdict_result, "verdict", None)
                chairman_conf = getattr(verdict_result, "confidence", None)
                concordant = (
                    None
                    if chairman_verdict is None
                    else ((chairman_verdict == "approved") == (policy_verdict == "pass"))
                )
                if concordant and isinstance(chairman_conf, (int, float)):
                    mech_conf = round(float(chairman_conf), 2)
                else:
                    mech_conf = deliberation_agreement
                # Calibrate ONCE, here in the compute section — the apply block
                # below must contain no throwing calls (Council C5 round 3).
                mech_calibrated = calibrate(mech_conf) if calibrate is not None else None

                # #560(b): a `pass` requires a deliberation that actually happened.
                # This replaces the confidence veto, which was accidentally doing
                # double duty as a degenerate-output backstop.
                #
                # DELIBERATELY NARROW. Both conditions are evidence that the run
                # itself was degraded — NOT judgements about the artifact:
                #   * verdict_parse == "error": the chairman's JSON violated the
                #     ADR-025b schema (#544). `absent` does not block: a missing
                #     verdict channel is not evidence of degradation, and ADR-051
                #     made that channel non-authoritative on purpose.
                #   * stage-3 error_status (#403): the chairman call itself failed.
                #
                # NOT gated on chairman/findings concordance. A chairman that says
                # "rejected" while labelling no finding `critical` is overruled by
                # policy(findings) — that is ADR-051's central decision, pinned by
                # test_mechanical_verdict::test_no_critical_passes_with_empty_blocking.
                # The contradiction is recorded as a marker below (it was previously
                # invisible: 0 of 4 real occurrences flagged) but changing the verdict
                # on it would re-establish the chairman's authority that ADR-051
                # removed, and belongs in an ADR revision, not a bug fix.
                deliberation_valid = diagnostics.get("verdict_parse") != "error" and not (
                    stage3_result or {}
                ).get("error_status")

                if chairman_verdict is not None and concordant is False:
                    mismatch = mismatch or "chairman_contradicts_findings"

                mechanical = policy_verdict
                pass_blocked_by: Optional[str] = None
                _inner: Optional[Tuple[str, float, Optional[float]]] = None
                if policy_verdict == "pass" and not deliberation_valid:
                    pass_blocked_by = "deliberation_invalid"
                    _inner = ("pass", mech_conf, mech_calibrated)
                    mechanical = "unclear"

                mech_blocking = [
                    {"severity": f.severity, "description": f.description, "location": f.location}
                    for f in parsed
                    if f.severity == "critical"
                ]
                by_sev: Dict[str, int] = {}
                for f in parsed:
                    by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

                # --- all computed; apply atomically (no throwing calls below) ---
                result["verdict"] = mechanical
                result["confidence"] = mech_conf
                result["confidence_calibrated"] = mech_calibrated
                result["blocking_issues"] = mech_blocking
                diagnostics["verdict_source"] = "mechanical"
                diagnostics["findings_by_severity"] = by_sev
                # #560(c): publish the agreement number under its real name — it
                # measures how well the council REVIEWED, not how sure we are.
                diagnostics["deliberation_agreement"] = deliberation_agreement
                if pass_blocked_by is not None:
                    diagnostics["pass_blocked_by"] = pass_blocked_by
                # Discard any inner-verdict captured during the (now-overridden)
                # legacy softening; re-set only if the mechanical verdict softened.
                inner_verdict = inner_confidence = inner_confidence_calibrated = None
                if _inner is not None:
                    inner_verdict, inner_confidence, inner_confidence_calibrated = _inner
                if mismatch is not None:
                    diagnostics["verdict_evidence_mismatch"] = mismatch
                    logger.error(
                        "ADR-051 mechanical-gate invariant violated: verdict=%s has_critical=%s",
                        mechanical,
                        has_critical,
                    )
        except Exception:  # telemetry must never break a verdict
            diagnostics["fallback_reason"] = "findings_exception"
    # ADR-051 C5: surface the pre-softening inner verdict under diagnostics
    # (telemetry-only) so automation can tell "approved but under threshold"
    # from "genuinely undecided" without parsing prose.
    if inner_verdict is not None:
        diagnostics["inner_verdict"] = inner_verdict
        diagnostics["inner_confidence"] = inner_confidence
        diagnostics["inner_confidence_calibrated"] = inner_confidence_calibrated
    result["findings"] = findings_dicts
    result["diagnostics"] = diagnostics
    return result


def derive_unclear_reason(
    verdict: str,
    stage3_result: Any,
    timeout_fired: bool = False,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """ADR-047 P1: machine-readable cause for an UNCLEAR verdict (#413).

    Returns one of {"infra_failure", "low_confidence", "timeout",
    "chairman_disabled"} when the verdict is "unclear", else None. Lets
    automation apply distinct policies (retry infra, accept-and-audit low
    confidence, re-tier timeouts, or skip entirely) instead of treating every
    exit-code-2 identically.

    - timeout: the ADR-040 global deadline fired (checked first — a starved
      chairman is a scheduling problem, not an infra one)
    - chairman_disabled: chairman synthesis was skipped by config (PR #519);
      no verdict was ever computed, deliberate not incidental
    - infra_failure: the chairman call itself errored (#403 error_status —
      billing/auth/rate-limit/transport)
    - low_confidence: deliberation completed; confidence below threshold
    """
    if verdict != "unclear":
        return None
    if timeout_fired:
        return "timeout"
    if isinstance(stage3_result, dict) and stage3_result.get("chairman_disabled") is True:
        return "chairman_disabled"
    if isinstance(stage3_result, dict) and stage3_result.get("error_status"):
        return "infra_failure"
    # #560: a mechanical `pass` blocked by the validity precondition or by the
    # chairman contradicting its own findings is NOT "the artifact is borderline".
    # Routing it as low_confidence tells automation "accept and audit" (ADR-047 P1)
    # for a run that should be retried or escalated.
    blocked = (diagnostics or {}).get("pass_blocked_by")
    if blocked == "deliberation_invalid":
        return "infra_failure"
    return "low_confidence"
