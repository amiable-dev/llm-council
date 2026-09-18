"""Ranking parsing, Borda aggregation, and shadow votes (ADR-046 P0, #408).

Verbatim moves from council.py; council.py re-exports every public name so
existing imports and test patch sites on ``llm_council.council.*`` keep
working (the orchestrators that call these stayed in council.py).
"""

import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from llm_council.layer_contracts import LayerEventType, emit_layer_event
from llm_council.voting import VotingAuthority, get_vote_weight

if TYPE_CHECKING:
    from llm_council.tier_contract import TierContract

logger = logging.getLogger(__name__)


def _get_exclude_self_votes() -> bool:
    """Call-time lookup through council so patched-attr semantics hold."""
    import llm_council.council as council_module

    return council_module._get_exclude_self_votes()


# =============================================================================
# Label-to-Model Mapping Helpers (v0.3.0+ Enhanced Format Support)
# =============================================================================
# Per council recommendation, label_to_model uses enhanced format:
# {"Response A": {"model": "gpt-4", "display_index": 0}}
# But also supports legacy format for backward compatibility:
# {"Response A": "gpt-4"}


def _get_model_from_label_value(value):
    """Extract model name from label_to_model value (enhanced or legacy format).

    Args:
        value: Either a string (legacy) or dict with 'model' key (enhanced)

    Returns:
        Model name string
    """
    if isinstance(value, dict):
        return value.get("model", "")
    return value

def _coerce_score(value: Any) -> float:
    """Best-effort coercion of a model-emitted score to a float.

    Model output is untrusted (Dict[str, Any]); a score may arrive as an int,
    float, numeric string ("9", "9.5") or junk ("N/A", "", None). Numeric
    values pass through; anything non-numeric coerces to the lowest possible
    value so it sorts last without raising (#354).
    """
    if isinstance(value, bool):
        # bool is a subclass of int; treat as non-numeric for scoring.
        return float("-inf")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, AttributeError):
            return float("-inf")
    return float("-inf")


def detect_score_rank_mismatch(ranking: List[str], scores: Dict[str, Any]) -> bool:
    """Detect if ranking order contradicts score order.

    LLMs are better at relative comparison than absolute calibration,
    so rankings should be trusted over scores. This function detects
    when they disagree for transparency in metadata.

    Args:
        ranking: List of labels in ranked order (best to worst)
        scores: Dict mapping labels to numeric scores

    Returns:
        True if there's a mismatch (score order != ranking order)
    """
    if not ranking or not scores:
        return False

    # Only check labels that have scores. `ranking` originates from parsed
    # model output (Dict[str, Any] JSON) with no element-type guarantee — a
    # non-string entry (e.g. a nested object) is unhashable and would crash
    # `label in scores` (found by Hypothesis fuzzing, #657); real labels are
    # always strings, so filtering first is both correct and crash-proof.
    ranked_with_scores = [
        label for label in ranking if isinstance(label, str) and label in scores
    ]

    if len(ranked_with_scores) < 2:
        return False

    # Get score-based ordering (highest score first).
    # Scores originate from parsed model output (Dict[str, Any]); a model may
    # emit a score as a string ("9", "N/A", "") which previously crashed the
    # whole verification with `bad operand type for unary -: 'str'` (#354).
    # Coerce defensively: non-numeric values sort lowest.
    score_order = sorted(ranked_with_scores, key=lambda x: -_coerce_score(scores.get(x)))

    # Compare to ranking order
    return ranked_with_scores != score_order


def parse_ranking_from_text(ranking_text: str) -> Dict[str, Any]:
    """
    Parse the ranking JSON from the model's response.

    Handles:
    - Normal JSON rankings
    - Legacy "FINAL RANKING:" format
    - Safety refusals (marks as abstained)
    - Parse failures (marks as abstained)
    - Score/rank mismatches (detected and flagged)

    Args:
        ranking_text: The full text response from the model

    Returns:
        Dict with 'ranking' (list), 'scores' (dict), and optionally:
        - 'abstained' (bool): If model refused to evaluate
        - 'score_rank_mismatch' (bool): If scores contradict ranking
    """
    import re
    import json

    result: Dict[str, Any] = {"ranking": [], "scores": {}}

    # Check for safety refusals or inability to evaluate
    # Note: patterns are lowercase since we search in lowercased text
    refusal_patterns = [
        r"i cannot evaluate",
        r"i'm not able to (rank|evaluate|assess)",
        r"i don't feel comfortable",
        r"i must decline",
        r"i can't provide a ranking",
        r"i'm unable to rank",
        r"i cannot compare",
        r"i won't be able to",
        r"i apologize,? but i cannot",
    ]

    ranking_text_lower = ranking_text.lower()
    for pattern in refusal_patterns:
        if re.search(pattern, ranking_text_lower):
            result["abstained"] = True
            result["abstention_reason"] = "Safety refusal detected"
            return result

    # Try to extract JSON block from markdown code fence
    json_match = re.search(r"```json\s*([\s\S]*?)\s*```", ranking_text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            # The fenced block can be *any* valid JSON, not just an object
            # (e.g. `null`, a bare array/number) — `.get` on a non-dict would
            # crash (found by Hypothesis fuzzing, #657).
            if not isinstance(parsed, dict):
                parsed = {}
            if isinstance(parsed.get("ranking"), list):
                result["ranking"] = parsed["ranking"]
            if isinstance(parsed.get("scores"), dict):
                result["scores"] = parsed["scores"]
            # Check for score/rank mismatch
            if detect_score_rank_mismatch(result["ranking"], result["scores"]):
                result["score_rank_mismatch"] = True
            return result
        except json.JSONDecodeError:
            pass

    # Fallback: try to find raw JSON object
    json_obj_match = re.search(r'\{\s*"ranking"\s*:', ranking_text)
    if json_obj_match:
        # Find the matching closing brace
        start = json_obj_match.start()
        brace_count = 0
        end = start
        for i, char in enumerate(ranking_text[start:], start):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        try:
            parsed = json.loads(ranking_text[start:end])
            if isinstance(parsed.get("ranking"), list):
                result["ranking"] = parsed["ranking"]
            if isinstance(parsed.get("scores"), dict):
                result["scores"] = parsed["scores"]
            # Check for score/rank mismatch
            if detect_score_rank_mismatch(result["ranking"], result["scores"]):
                result["score_rank_mismatch"] = True
            return result
        except json.JSONDecodeError:
            pass

    # Legacy fallback: Look for "FINAL RANKING:" section (backwards compatibility)
    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(r"\d+\.\s*Response [A-Z]", ranking_section)
            if numbered_matches:
                result["ranking"] = [
                    re.search(r"Response [A-Z]", m).group() for m in numbered_matches
                ]
                return result
            matches = re.findall(r"Response [A-Z]", ranking_section)
            if matches:
                result["ranking"] = matches
                return result

    # Final fallback: try to find any "Response X" patterns in order
    matches = re.findall(r"Response [A-Z]", ranking_text)
    result["ranking"] = matches
    return result


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
    voting_authorities: Optional[Dict[str, "VotingAuthority"]] = None,
    return_shadow_votes: bool = False,
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings using Normalized Borda Count method.

    Borda Count assigns points based on ranking position, then normalizes
    to [0, 1] range for cross-council comparability:
    - 1st place = 1.0 (was N-1 points, normalized by dividing by N-1)
    - 2nd place = (N-2)/(N-1)
    - Last place = 0.0

    Normalization is critical: without it, a 3-model council (max 2 points)
    and 10-model council (max 9 points) produce incomparable scores.

    When _get_exclude_self_votes() is True, excludes votes where the reviewer
    is evaluating their own response (prevents self-preference bias).

    ADR-027 Shadow Mode: When voting_authorities is provided, votes from models
    with ADVISORY authority (Shadow Mode) are tracked but have zero weight in
    the final rankings. EXCLUDED models are skipped entirely.

    Args:
        stage2_results: Rankings from each model (includes 'model' as reviewer)
        label_to_model: Mapping from anonymous labels to model names
        voting_authorities: Optional dict mapping reviewer model IDs to VotingAuthority.
                           If None, all voters have FULL authority (backward compatible).
        return_shadow_votes: If True, include shadow_votes in result entries.

    Returns:
        List of dicts with model name, normalized Borda score [0,1], sorted best to worst
    """
    from collections import defaultdict

    num_candidates = len(label_to_model)

    # Edge case: single candidate can't be ranked
    if num_candidates <= 1:
        if num_candidates == 1:
            model = _get_model_from_label_value(list(label_to_model.values())[0])
            return [
                {
                    "model": model,
                    "borda_score": 1.0,  # Only candidate gets perfect score
                    "average_position": 1.0,
                    "average_score": None,
                    "vote_count": 0,
                    "self_votes_excluded": _get_exclude_self_votes(),
                    "rank": 1,
                }
            ]
        return []

    # Track normalized Borda scores and raw scores for each model
    model_borda_scores = defaultdict(list)  # Now stores normalized [0,1] scores
    model_raw_scores = defaultdict(list)
    model_positions = defaultdict(list)
    self_votes_excluded = 0

    # ADR-027: Track shadow votes separately for observability
    shadow_votes = []

    # Normalization factor: max possible Borda points
    max_borda = num_candidates - 1

    for ranking in stage2_results:
        reviewer_model = ranking.get("model", "")
        parsed = ranking.get("parsed_ranking", {})
        ranking_list = parsed.get("ranking", [])
        scores = parsed.get("scores", {})

        # Skip if this ranking was marked as abstained
        if parsed.get("abstained"):
            continue

        # ADR-027: Determine voting authority for this reviewer
        if voting_authorities is not None:
            authority = voting_authorities.get(reviewer_model, VotingAuthority.FULL)
        else:
            authority = VotingAuthority.FULL

        # Skip EXCLUDED reviewers entirely
        if authority == VotingAuthority.EXCLUDED:
            continue

        # Get vote weight (1.0 for FULL, 0.0 for ADVISORY)
        vote_weight = get_vote_weight(authority)

        # #677: sanitise the ballot BEFORE it drives any position.
        # `ranking_list` is raw model output. Left alone it corrupts the
        # aggregate three ways, all measured: an unknown label consumed a
        # position (pushing a valid label to index >= N, producing a
        # `borda = -1.0` outside the documented [0,1] range), a repeated label
        # let one reviewer vote several times (`vote_count = 3`), and an
        # unhashable label raised TypeError at `label in label_to_model` (the
        # #657 crash class). Keep known labels only, first occurrence only,
        # and renumber positions over what survives.
        ranking_list = _sanitize_ballot(ranking_list, label_to_model)

        # Track shadow votes for ADVISORY reviewers
        if authority == VotingAuthority.ADVISORY and ranking_list:
            # Get the top pick (first in ranking)
            top_label = ranking_list[0]
            if top_label in label_to_model:
                top_model = _get_model_from_label_value(label_to_model[top_label])
                shadow_votes.append(
                    {
                        "reviewer": reviewer_model,
                        "top_pick": top_model,
                        "ranking": [
                            _get_model_from_label_value(label_to_model[lbl])
                            for lbl in ranking_list
                            if lbl in label_to_model
                        ],
                    }
                )

        # Calculate normalized Borda scores from ranking positions
        for position, label in enumerate(ranking_list):
            if label in label_to_model:
                author_model = _get_model_from_label_value(label_to_model[label])

                # Exclude self-votes if configured
                if _get_exclude_self_votes() and reviewer_model == author_model:
                    self_votes_excluded += 1
                    continue

                # ADR-027: Only count votes with weight > 0 (FULL authority)
                if vote_weight > 0:
                    # Raw Borda points: 1st = (N-1), 2nd = (N-2), last = 0
                    raw_borda = max_borda - position
                    # Normalize to [0, 1]: divide by max possible points
                    normalized_borda = raw_borda / max_borda
                    model_borda_scores[author_model].append(normalized_borda)
                    model_positions[author_model].append(position + 1)  # 1-indexed for display

        # Also track raw scores (as secondary signal, normalized to [0,1])
        # Only for FULL authority votes
        if vote_weight > 0:
            for label, score in scores.items():
                if label in label_to_model:
                    author_model = _get_model_from_label_value(label_to_model[label])

                    if _get_exclude_self_votes() and reviewer_model == author_model:
                        continue

                    # Normalize raw score to [0,1] (assuming 1-10 scale)
                    normalized_raw = score / 10.0 if isinstance(score, (int, float)) else None
                    if normalized_raw is not None:
                        model_raw_scores[author_model].append(normalized_raw)

    # Calculate aggregates for each model
    aggregate = []

    # ADR-027: Include all candidate models, even those with 0 effective votes
    # This ensures ADVISORY-only councils still return all candidates
    all_candidate_models = {
        _get_model_from_label_value(label_to_model[label]) for label in label_to_model
    }
    all_models = (
        all_candidate_models | set(model_borda_scores.keys()) | set(model_raw_scores.keys())
    )

    for model in all_models:
        borda_scores = model_borda_scores.get(model, [])
        raw_scores = model_raw_scores.get(model, [])
        positions = model_positions.get(model, [])

        entry = {
            "model": model,
            # Average of normalized Borda scores [0,1]
            "borda_score": round(sum(borda_scores) / len(borda_scores), 3)
            if borda_scores
            else None,
            "average_position": round(sum(positions) / len(positions), 2) if positions else None,
            # Average of normalized raw scores [0,1]
            "average_score": round(sum(raw_scores) / len(raw_scores), 3) if raw_scores else None,
            "vote_count": len(borda_scores),
            "self_votes_excluded": _get_exclude_self_votes(),
        }

        # ADR-027: Optionally include shadow votes for observability
        if return_shadow_votes:
            entry["shadow_votes"] = shadow_votes

        aggregate.append(entry)

    # Sort by Borda score (higher is better), then by raw score as tiebreaker
    # #677: `or -999` treated a legitimate last-place borda of 0.0 as missing,
    # sorting a genuinely ranked candidate down among the unranked. Test None
    # explicitly; unranked candidates sort last by construction.
    # #678 gate: `all_models` is a set and list.sort is stable, so a fully tied
    # aggregate (e.g. an ADVISORY-only council where every score is None) got
    # hash-order-dependent ranks, making any downstream `aggregate[0]` winner
    # nondeterministic across runs. Model id is the final, deterministic key.
    aggregate.sort(
        key=lambda x: (
            -(x["borda_score"] if x["borda_score"] is not None else -999),
            -(x["average_score"] if x["average_score"] is not None else 0),
            x["model"],
        )
    )

    # Add rank numbers
    for i, entry in enumerate(aggregate, start=1):
        entry["rank"] = i

    return aggregate


def should_track_shadow_votes(tier_contract: Optional["TierContract"]) -> bool:
    """Determine if shadow votes should be tracked for this tier.

    Per ADR-027, shadow vote tracking is enabled only for the frontier tier.
    This avoids unnecessary overhead for non-frontier tiers.

    Args:
        tier_contract: Optional tier contract specifying the tier.

    Returns:
        True if shadow votes should be tracked, False otherwise.
    """
    if tier_contract is None:
        return False
    return tier_contract.tier == "frontier"


def emit_shadow_vote_events(
    shadow_votes: List[Dict[str, Any]],
    consensus_winner: Optional[str] = None,
) -> None:
    """Emit FRONTIER_SHADOW_VOTE events for each shadow vote.

    Per ADR-027, shadow votes from ADVISORY reviewers are logged
    for observability and model evaluation.

    Args:
        shadow_votes: List of shadow vote dicts from calculate_aggregate_rankings.
        consensus_winner: The model that won consensus (top of aggregate rankings).
    """
    from .layer_contracts import LayerEventType, emit_layer_event

    for vote in shadow_votes:
        reviewer = vote.get("reviewer", "unknown")
        top_pick = vote.get("top_pick")

        # Calculate agreement with consensus
        agreed_with_consensus = top_pick == consensus_winner if consensus_winner else None

        emit_layer_event(
            LayerEventType.FRONTIER_SHADOW_VOTE,
            {
                "model_id": reviewer,
                "top_pick": top_pick,
                "agreed_with_consensus": agreed_with_consensus,
                "ranking": vote.get("ranking", []),
            },
        )




def rankings_to_position_tuples(aggregate_rankings: Any) -> List[Tuple[str, float]]:
    """Aggregate entries → ``(model, average_position)`` tuples for ADR-036 CSS (#677).

    A model that received no position votes carries ``average_position: None``
    (ADR-027 keeps 0-vote candidates in the aggregate; the single-model degraded
    path in ``council.py`` sets it too). Such an entry is **dropped**: a model
    nobody ranked carries no consensus information, and the caller can decide
    whether what remains is enough.

    Deliberately NO ``borda_score`` fallback. Borda is higher-is-better on 0–1
    while a position is lower-is-better on 1–N, so substituting one for the
    other inside a single list corrupts the ordering CSS measures — and in the
    zero-vote case borda is ``None`` as well, so it buys nothing. The previous
    expression ``r.get("average_position", r.get("borda_score", 0.0))`` never
    fell back at all: ``.get`` returns the STORED ``None`` for a present key
    (the #594 bug class), so the ``None`` reached the CSS math and raised.

    Total function: malformed entries are skipped rather than raised on.
    """
    tuples: List[Tuple[str, float]] = []
    if not isinstance(aggregate_rankings, (list, tuple)):
        # #677: the docstring promises a total function, but `x or []` raised
        # TypeError for any truthy non-iterable.
        return tuples
    for entry in aggregate_rankings:
        if not isinstance(entry, dict):
            continue
        model = entry.get("model")
        position = entry.get("average_position")
        # bool is an int subclass — never a position
        if not isinstance(model, str) or isinstance(position, bool):
            continue
        if isinstance(position, (int, float)) and math.isfinite(position) and position >= 1:
            # #677: NaN/inf/0/negative all passed a bare isinstance check. NaN is
            # worse than the TypeError this function exists to prevent — it
            # silently corrupts CSS's ordering instead of reporting the signal
            # as unavailable. A position is 1-based by construction.
            tuples.append((model, float(position)))
    return tuples


def _sanitize_ballot(ranking_list: Any, label_to_model: Dict[str, Any]) -> List[str]:
    """Known labels only, first occurrence only (#677).

    Unhashable entries (a nested list/dict from a malformed parse) are skipped
    rather than raised on — the same defence `detect_score_rank_mismatch`
    already applies for #657.
    """
    if not isinstance(ranking_list, (list, tuple)):
        return []
    seen: set = set()
    clean: List[str] = []
    for label in ranking_list:
        try:
            if label in seen or label not in label_to_model:
                continue
            seen.add(label)
        except TypeError:  # unhashable label
            continue
        clean.append(label)
    return clean
