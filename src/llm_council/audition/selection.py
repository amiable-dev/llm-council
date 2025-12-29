"""Selection Integration for ADR-029 Model Audition Mechanism.

This module provides selection weighting and seat limiting for audition models:
- get_selection_weight(): Returns 0-1 weight based on audition state
- select_with_audition(): Applies weights and limits audition seats
- is_auditioning_model(): Check if model is in audition state

Weight Progression per ADR-029:
| State       | Weight    | Notes                          |
|-------------|-----------|--------------------------------|
| SHADOW      | 0.3       | 30% chance, non-binding votes  |
| PROBATION   | 0.3       | 30% chance, still proving      |
| EVALUATION  | 0.3-1.0   | Progressive based on sessions  |
| FULL        | 1.0       | Normal selection               |
| QUARANTINE  | 0.0       | Never selected                 |

Example:
    >>> from llm_council.audition.selection import get_selection_weight, select_with_audition
    >>> weight = get_selection_weight(status)
    >>> selected = select_with_audition(scored_candidates, tracker, count=4)
"""

from typing import TYPE_CHECKING, List, Optional, Tuple

from .types import AuditionState, AuditionStatus


def _emit_selection_event(model_id: str, state: str, selected: bool) -> None:
    """Emit an audition model selection event.

    Args:
        model_id: The model identifier
        state: Current audition state value
        selected: Whether model was selected
    """
    try:
        from llm_council.layer_contracts import LayerEventType, emit_layer_event

        emit_layer_event(
            LayerEventType.AUDITION_MODEL_SELECTED,
            {
                "model_id": model_id,
                "state": state,
                "selected": selected,
            },
        )
    except ImportError:
        pass  # layer_contracts not available


if TYPE_CHECKING:
    from .tracker import AuditionTracker

# Weight constants per ADR-029
SHADOW_WEIGHT = 0.3
PROBATION_WEIGHT = 0.3
FULL_WEIGHT = 1.0
QUARANTINE_WEIGHT = 0.0

# Evaluation phase session thresholds for progressive weighting
EVAL_START_SESSIONS = 25  # When model enters EVALUATION
EVAL_END_SESSIONS = 50  # When model graduates to FULL


def get_selection_weight(status: Optional[AuditionStatus]) -> float:
    """Get selection weight based on audition state.

    Returns a weight factor (0-1) that is applied to the model's score
    during selection. This implements the progressive weighting from ADR-029.

    Args:
        status: AuditionStatus for the model, or None for unknown models

    Returns:
        Weight factor between 0 and 1
    """
    # Unknown models are treated as SHADOW
    if status is None:
        return SHADOW_WEIGHT

    state = status.state

    if state == AuditionState.SHADOW:
        return SHADOW_WEIGHT

    elif state == AuditionState.PROBATION:
        return PROBATION_WEIGHT

    elif state == AuditionState.EVALUATION:
        # Progressive weight: 0.3 to 1.0 based on session count
        # Linear interpolation between EVAL_START and EVAL_END sessions
        sessions = status.session_count
        if sessions >= EVAL_END_SESSIONS:
            return FULL_WEIGHT
        elif sessions <= EVAL_START_SESSIONS:
            return SHADOW_WEIGHT

        # Linear interpolation
        progress = (sessions - EVAL_START_SESSIONS) / (EVAL_END_SESSIONS - EVAL_START_SESSIONS)
        return SHADOW_WEIGHT + (FULL_WEIGHT - SHADOW_WEIGHT) * progress

    elif state == AuditionState.FULL:
        return FULL_WEIGHT

    elif state == AuditionState.QUARANTINE:
        return QUARANTINE_WEIGHT

    # Default for unexpected states
    return SHADOW_WEIGHT


def is_auditioning_model(status: Optional[AuditionStatus]) -> bool:
    """Check if a model is in an audition state.

    Audition states are: SHADOW, PROBATION, EVALUATION
    Non-audition states are: FULL, QUARANTINE

    Args:
        status: AuditionStatus for the model

    Returns:
        True if model is in an audition state
    """
    if status is None:
        return True  # Unknown models are treated as auditioning (SHADOW)

    return status.state in (
        AuditionState.SHADOW,
        AuditionState.PROBATION,
        AuditionState.EVALUATION,
    )


def select_with_audition(
    scored_candidates: List[Tuple[str, float]],
    tracker: "AuditionTracker",
    count: int = 4,
    max_audition_seats: int = 1,
) -> List[str]:
    """Select models with state-appropriate weighting.

    Applies audition weights to candidate scores, then selects the top
    models while respecting the max_audition_seats constraint.

    Args:
        scored_candidates: List of (model_id, score) tuples with base scores
        tracker: AuditionTracker for looking up model states
        count: Number of models to select
        max_audition_seats: Maximum audition models allowed (default: 1)

    Returns:
        List of selected model_ids
    """
    # Apply weights to scores
    weighted: List[Tuple[str, float, bool]] = []
    for model_id, score in scored_candidates:
        status = tracker.get_status(model_id)
        weight = get_selection_weight(status)

        # Skip QUARANTINE models entirely
        if weight == 0.0:
            continue

        weighted_score = score * weight
        is_audition = is_auditioning_model(status)
        weighted.append((model_id, weighted_score, is_audition))

    # Sort by weighted score (descending)
    weighted.sort(key=lambda x: x[1], reverse=True)

    # Select with audition seat limit
    selected: List[str] = []
    audition_count = 0

    for model_id, _, is_audition in weighted:
        if len(selected) >= count:
            break

        if is_audition:
            if audition_count >= max_audition_seats:
                continue
            audition_count += 1

            # Emit selection event for auditioning models
            status = tracker.get_status(model_id)
            state_value = status.state.value if status else "shadow"
            _emit_selection_event(model_id, state_value, True)

        selected.append(model_id)

    return selected
