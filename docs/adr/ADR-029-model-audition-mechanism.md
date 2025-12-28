# ADR-029: Model Audition Mechanism

**Status:** ACCEPTED (Revised per Council Review 2025-12-24)
**Date:** 2025-12-24
**Decision Makers:** Engineering, Architecture
**Depends On:** ADR-028 (Dynamic Candidate Discovery), ADR-027 (Frontier Tier)
**Council Review:** Reasoning tier (gpt-5.2-pro, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast)

---

## Context

When new models are discovered via ADR-028, they lack performance history. The system cannot accurately score them because:

1. No latency measurements exist
2. No quality observations from past sessions
3. No availability/reliability data

**Cold Start Problem:** New models are either never selected (no history → low score) or selected blindly (no data to validate quality).

---

## Decision

Implement a **volume-based audition mechanism** with Shadow Mode integration and explicit state machine progression.

### Model Lifecycle State Machine (Council Requirement)

**Critical Feedback:** Time-based graduation is unreliable. A model used once in 30 days isn't "proven."

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Model Lifecycle State Machine                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────┐    10 sessions    ┌───────────┐    25 sessions    ┌──────┐  │
│   │  SHADOW  │ ─────────────────▶│ PROBATION │ ─────────────────▶│ EVAL │  │
│   │          │    (min 3 days)   │           │    (min 7 days)   │      │  │
│   └──────────┘                   └───────────┘                   └──────┘  │
│        │                              │                              │      │
│        │ 3+ failures                  │ 5+ failures                  │      │
│        ▼                              ▼                              ▼      │
│   ┌──────────────────────────────────────────────────────────────────────┐ │
│   │                           QUARANTINE                                  │ │
│   │           (Cooldown: 24h shadow, then retry from SHADOW)              │ │
│   └──────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ┌──────┐    50 sessions    ┌──────┐                                      │
│   │ EVAL │ ─────────────────▶│ FULL │  (Normal selection, full authority)  │
│   │      │   (quality ≥75th  │      │                                      │
│   └──────┘    percentile)    └──────┘                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### State Definitions

```python
from enum import Enum, auto
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

class AuditionState(Enum):
    """Model audition lifecycle states."""
    SHADOW = auto()      # Non-binding votes, observation only
    PROBATION = auto()   # Limited selection, paired with proven models
    EVALUATION = auto()  # Weighted selection, building confidence
    FULL = auto()        # Normal selection, full voting authority
    QUARANTINE = auto()  # Temporarily excluded due to failures


@dataclass
class AuditionStatus:
    """Tracks model's audition progress."""
    model_id: str
    state: AuditionState
    session_count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    consecutive_failures: int = 0
    quality_percentile: Optional[float] = None
    quarantine_until: Optional[datetime] = None

    def days_tracked(self) -> int:
        """Days since first session."""
        if self.first_seen is None:
            return 0
        return (datetime.utcnow() - self.first_seen).days


@dataclass(frozen=True)
class GraduationCriteria:
    """Criteria for state transitions (volume-based)."""
    # SHADOW → PROBATION
    shadow_min_sessions: int = 10
    shadow_min_days: int = 3
    shadow_max_failures: int = 3

    # PROBATION → EVALUATION
    probation_min_sessions: int = 25
    probation_min_days: int = 7
    probation_max_failures: int = 5

    # EVALUATION → FULL
    eval_min_sessions: int = 50
    eval_min_quality_percentile: float = 0.75  # Must be in top 25%

    # QUARANTINE
    quarantine_cooldown_hours: int = 24
```

### State Transition Logic

```python
def evaluate_state_transition(
    status: AuditionStatus,
    criteria: GraduationCriteria
) -> Optional[AuditionState]:
    """
    Determine if model should transition states.
    Volume-based graduation per Council recommendation.
    """
    now = datetime.utcnow()

    # Check quarantine expiry
    if status.state == AuditionState.QUARANTINE:
        if status.quarantine_until and now >= status.quarantine_until:
            return AuditionState.SHADOW  # Retry from shadow
        return None  # Stay quarantined

    # Check failure thresholds (any state → QUARANTINE)
    if status.state == AuditionState.SHADOW:
        if status.consecutive_failures >= criteria.shadow_max_failures:
            return AuditionState.QUARANTINE

    if status.state == AuditionState.PROBATION:
        if status.consecutive_failures >= criteria.probation_max_failures:
            return AuditionState.QUARANTINE

    # SHADOW → PROBATION
    if status.state == AuditionState.SHADOW:
        if (status.session_count >= criteria.shadow_min_sessions
            and status.days_tracked() >= criteria.shadow_min_days):
            return AuditionState.PROBATION

    # PROBATION → EVALUATION
    if status.state == AuditionState.PROBATION:
        if (status.session_count >= criteria.probation_min_sessions
            and status.days_tracked() >= criteria.probation_min_days):
            return AuditionState.EVALUATION

    # EVALUATION → FULL
    if status.state == AuditionState.EVALUATION:
        if (status.session_count >= criteria.eval_min_sessions
            and status.quality_percentile is not None
            and status.quality_percentile >= criteria.eval_min_quality_percentile):
            return AuditionState.FULL

    return None  # No transition
```

### Shadow Mode Integration (ADR-027)

**Critical Council Feedback:** Audition models must NOT influence consensus until proven.

```python
from llm_council.voting import VotingAuthority

# State → Voting Authority mapping
STATE_VOTING_AUTHORITY = {
    AuditionState.SHADOW: VotingAuthority.ADVISORY,      # Non-binding
    AuditionState.PROBATION: VotingAuthority.ADVISORY,   # Non-binding
    AuditionState.EVALUATION: VotingAuthority.ADVISORY,  # Non-binding until FULL
    AuditionState.FULL: VotingAuthority.FULL,            # Full voting rights
    AuditionState.QUARANTINE: VotingAuthority.EXCLUDED,  # Not selected
}


def get_voting_authority(model_id: str, tracker: AuditionTracker) -> VotingAuthority:
    """Get voting authority based on audition state."""
    status = tracker.get_status(model_id)

    if status is None:
        # Unknown model - treat as new (SHADOW)
        return VotingAuthority.ADVISORY

    return STATE_VOTING_AUTHORITY.get(status.state, VotingAuthority.ADVISORY)
```

### Selection with Audition (Revised)

**Council Feedback:** Code inconsistency fixed. Progressive weight replaces epsilon-greedy binary.

```python
def select_with_audition(
    scored_candidates: List[Tuple[str, float]],
    tracker: AuditionTracker,
    count: int = 4,
) -> List[str]:
    """
    Select models with state-appropriate weighting.

    Progressive weight approach (NOT epsilon-greedy):
    - SHADOW/PROBATION: 30% selection weight
    - EVALUATION: 30-100% (scaled by session count)
    - FULL: 100% selection weight
    """
    weighted_candidates = []

    for model_id, score in scored_candidates:
        status = tracker.get_status(model_id)
        weight = get_selection_weight(status)
        weighted_score = score * weight
        weighted_candidates.append((model_id, weighted_score, weight))

    # Sort by weighted score
    weighted_candidates.sort(key=lambda x: -x[1])

    # Enforce max audition seats (protect council quality)
    selected = []
    audition_count = 0
    max_audition_seats = 1  # Only 1 audition model per session

    for model_id, weighted_score, weight in weighted_candidates:
        if len(selected) >= count:
            break

        # Is this an audition model (weight < 1.0)?
        is_audition = weight < 1.0

        if is_audition:
            if audition_count >= max_audition_seats:
                continue  # Skip, already have max audition models
            audition_count += 1

        selected.append(model_id)

    return selected


def get_selection_weight(status: Optional[AuditionStatus]) -> float:
    """
    Get selection weight based on audition state.
    Consistent with table definitions (fixes code/table mismatch).
    """
    if status is None:
        return 0.3  # New model: SHADOW weight

    if status.state == AuditionState.SHADOW:
        return 0.3

    if status.state == AuditionState.PROBATION:
        return 0.3

    if status.state == AuditionState.EVALUATION:
        # Scale from 0.3 to 1.0 based on session progress
        # At 25 sessions (EVAL entry): 0.3
        # At 50 sessions (FULL graduation): 1.0
        progress = min(1.0, (status.session_count - 25) / 25)
        return 0.3 + (0.7 * progress)

    if status.state == AuditionState.FULL:
        return 1.0

    if status.state == AuditionState.QUARANTINE:
        return 0.0  # Never select

    return 0.3  # Default: cautious


# REMOVED: Epsilon-greedy approach (inconsistent with progressive weights)
```

### Probationary Periods (Revised - Volume-Based)

| State | Sessions | Min Days | Selection Weight | Max Seats | Voting |
|-------|----------|----------|------------------|-----------|--------|
| Shadow | 0-10 | 3 | 30% | 1 | Advisory |
| Probation | 10-25 | 7 | 30% | 1 | Advisory |
| Evaluation | 25-50 | - | 30-100% | 1 | Advisory |
| Full | 50+ | - | 100% | Any | Full |
| Quarantine | - | - | 0% | 0 | Excluded |

### Audition Safeguards

1. **Shadow Mode by default** - New models don't affect consensus
2. **Volume-based graduation** - Requires actual usage, not just time
3. **Max 1 audition per council session** - Limit risk exposure
4. **Paired with proven models** - Always have reliable responses
5. **Quality gate for FULL status** - Must be top 25% to graduate
6. **Quarantine on failures** - Automatic exclusion with cooldown
7. **Consensus exclusion** - Audition models excluded from tie-breaking

### Configuration

```yaml
council:
  model_intelligence:
    audition:
      enabled: true

      # State progression (volume-based)
      shadow:
        min_sessions: 10
        min_days: 3
        max_failures: 3

      probation:
        min_sessions: 25
        min_days: 7
        max_failures: 5

      evaluation:
        min_sessions: 50
        min_quality_percentile: 0.75

      quarantine:
        cooldown_hours: 24

      # Selection limits
      max_audition_seats: 1
```

### Environment Variables

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `LLM_COUNCIL_AUDITION_ENABLED` | bool | true | Enable audition mechanism |
| `LLM_COUNCIL_AUDITION_MAX_SEATS` | int | 1 | Max audition models per session |
| `LLM_COUNCIL_AUDITION_SHADOW_SESSIONS` | int | 10 | Sessions before probation |
| `LLM_COUNCIL_AUDITION_EVAL_SESSIONS` | int | 50 | Sessions for full graduation |

---

## Observability (Council Requirement)

```python
# Metrics to emit
audition.state_transition{model_id, from_state, to_state}
audition.selection{model_id, state, selected}
audition.failure{model_id, state, failure_type}
audition.quarantine{model_id, reason, cooldown_hours}
audition.graduation{model_id, quality_percentile}

# Structured logging
{
    "event": "audition_state_change",
    "model_id": "openai/gpt-5.2",
    "from_state": "PROBATION",
    "to_state": "EVALUATION",
    "session_count": 25,
    "days_tracked": 8,
    "quality_percentile": null
}
```

---

## Consequences

### Positive
- Solves cold start problem for new models
- Volume-based graduation ensures actual usage
- Shadow Mode protects consensus from unproven models
- Explicit state machine provides clear lifecycle
- Quality gate prevents low-quality model graduation

### Negative
- Audition models contribute responses but not votes
- Longer path to full status (50 sessions minimum)
- Additional complexity in selection logic
- Quarantine may miss temporary issues vs systemic

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Audition model pollutes context | Shadow Mode (advisory only) |
| Volume manipulation (spam requests) | Min days requirement alongside sessions |
| Good model stuck in evaluation | Clear quality percentile metric |
| Quarantine too aggressive | Configurable thresholds, auto-retry |

---

## Testing Strategy

```python
class TestAuditionMechanism:
    def test_state_transitions_volume_based(self):
        """State transitions require session count, not just time."""

    def test_shadow_mode_no_voting(self):
        """Shadow state models have ADVISORY voting authority."""

    def test_quarantine_on_failures(self):
        """Consecutive failures trigger quarantine."""

    def test_quarantine_cooldown_and_retry(self):
        """Models retry from SHADOW after cooldown."""

    def test_max_audition_seats(self):
        """Only 1 audition model selected per session."""

    def test_quality_gate_for_full(self):
        """EVALUATION → FULL requires 75th percentile quality."""

    def test_selection_weight_progression(self):
        """Weight scales 0.3 → 1.0 during EVALUATION."""
```

---

## Implementation Plan

1. [ ] Define `AuditionState` enum and `AuditionStatus` dataclass
2. [ ] Implement state transition logic with volume-based criteria
3. [ ] Add `AuditionTracker` with persistence (JSONL)
4. [ ] Integrate with `VotingAuthority` from ADR-027
5. [ ] Implement `select_with_audition()` with progressive weights
6. [ ] Add metrics and structured logging
7. [ ] Add configuration via YAML and env vars
8. [ ] Add comprehensive tests

---

## References

- [ADR-027: Frontier Tier](./ADR-027-frontier-tier.md) (Shadow Mode)
- [ADR-028: Dynamic Candidate Discovery](./ADR-028-dynamic-candidate-discovery.md)
- [ADR-026: Dynamic Model Intelligence](./ADR-026-dynamic-model-intelligence.md)
