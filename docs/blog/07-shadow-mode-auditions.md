# Shadow Mode & Model Auditions

**Stop guessing. Use production traffic to A/B test models without breaking the user experience.**

---

New models drop every week. GPT-5, Claude Opus, Gemini 3 Pro, Grok 4. Each promises to be better than the last. But how do you know if they're actually better for *your* use case?

You can't trust benchmarks. You can't trust vibes. You need production data.

The problem: putting an untested model into your council can break things. Hallucinations. Timeouts. Rate limits. A single bad model can poison your consensus.

Our solution: Shadow Mode and a volume-based audition system.

## Shadow Mode: Vote Without Power

When a new model joins the council in Shadow Mode, it:

1. **Generates responses** alongside other models
2. **Participates in peer review** (evaluating other responses)
3. **Gets ranked** by peers like any other model
4. **Has zero vote weight** in the final consensus

```python
from enum import Enum

class VotingAuthority(Enum):
    FULL = "full"           # Vote counts in consensus (weight = 1.0)
    ADVISORY = "advisory"   # Vote logged but weight = 0.0 (Shadow Mode)
    EXCLUDED = "excluded"   # Not included at all

def get_vote_weight(authority: VotingAuthority) -> float:
    if authority == VotingAuthority.FULL:
        return 1.0
    return 0.0  # ADVISORY and EXCLUDED have no weight
```

**The key insight:** You collect all the data you need to evaluate the model, without risking production quality.

## Why Shadow Mode Matters

Consider this scenario:

A new model joins the council. It's confident, articulate, and completely wrong. Without Shadow Mode:

1. It generates a hallucinated response
2. It ranks itself #1 (models show self-preference)
3. Its vote shifts the consensus toward the wrong answer
4. The chairman synthesizes a flawed conclusion

With Shadow Mode:

1. It generates a hallucinated response
2. It ranks itself #1 (vote logged but weight = 0)
3. Established models vote correctly; consensus unaffected
4. Post-session analysis reveals: "Shadow model disagreed with consensus 80% of the time"

You learned the model isn't ready—without breaking anything.

## The Audition State Machine

New models progress through stages before earning full voting rights:

```
SHADOW → PROBATION → EVALUATION → FULL
    ↓         ↓           ↓
    └─────────┴───────────┴──→ QUARANTINE ──→ DEAD
```

### State Definitions

| State | Sessions | Voting | Selection Rate |
|-------|----------|--------|----------------|
| **SHADOW** | 0-10 | Advisory (0%) | 30% of requests |
| **PROBATION** | 10-25 | Advisory (0%) | 30% of requests |
| **EVALUATION** | 25-50 | Advisory (0%) | 30-100% of requests |
| **FULL** | 50+ | Full (100%) | 100% of requests |
| **QUARANTINE** | N/A | Excluded (0%) | 0% of requests |
| **DEAD** | N/A | Excluded (0%) | Never selected |

**Note on Selection Rate:** This is *traffic sampling*. A 30% selection rate means the model is only included in 30% of council sessions. This slows data collection but limits exposure to unreliable models.

### Graduation Criteria (Volume-Based)

Time-based graduation is unreliable. A model used once in 30 days isn't "proven."

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class GraduationCriteria:
    """Volume-based graduation thresholds."""

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
    eval_min_quality_percentile: float = 0.75  # Top 25%
    eval_max_failures: int = 10

    # Quarantine escape hatch
    max_quarantine_cycles: int = 3  # After 3 quarantines, move to DEAD
```

A model must:
1. Complete enough sessions (statistical significance)
2. Meet minimum age (catch slow-emerging issues)
3. Avoid too many consecutive failures
4. Rank in the top 25% of quality (for final promotion)

### Quarantine and the Kill Switch

If a model fails repeatedly, it goes to quarantine:

```python
from enum import Enum

class AuditionState(Enum):
    SHADOW = "shadow"
    PROBATION = "probation"
    EVALUATION = "evaluation"
    FULL = "full"
    QUARANTINE = "quarantine"
    DEAD = "dead"  # Permanently disabled

@dataclass
class AuditionStatus:
    state: AuditionState
    consecutive_failures: int
    quarantine_count: int = 0

def check_quarantine_trigger(
    status: AuditionStatus,
    criteria: GraduationCriteria
) -> bool:
    """Check if model should be quarantined."""
    if status.state == AuditionState.SHADOW:
        return status.consecutive_failures >= criteria.shadow_max_failures
    if status.state == AuditionState.PROBATION:
        return status.consecutive_failures >= criteria.probation_max_failures
    if status.state == AuditionState.EVALUATION:
        return status.consecutive_failures >= criteria.eval_max_failures
    return False

def check_dead_trigger(status: AuditionStatus, criteria: GraduationCriteria) -> bool:
    """Check if model should be permanently disabled."""
    return status.quarantine_count >= criteria.max_quarantine_cycles
```

Quarantine lasts 24 hours, then the model restarts from SHADOW. **But after 3 quarantine cycles, the model moves to DEAD state**—permanently disabled until manual intervention. This prevents infinite loops from permanently broken models.

## A Note on Consensus Agreement

We track `consensus_agreement`: how often a shadow model's vote would have matched the established council's verdict.

**Important caveat:** This metric measures *conformity*, not necessarily *quality*. If a new model is genuinely smarter than your current council, it *should* disagree. High agreement means safe, not superior.

Use consensus agreement for:
- Detecting obvious failures (< 50% agreement = something's wrong)
- Validating stability (consistent agreement over time)

Don't use it for:
- Quality assessment (use peer rankings instead)
- Deciding if a model is "better" (it might just be different)

## Frontier Tier: The Testing Ground

We created a dedicated tier for cutting-edge models:

```python
TIER_POOLS = {
    # ... production tiers ...
    "frontier": [
        "openai/gpt-5-preview",
        "anthropic/claude-opus-next",
        "google/gemini-3-ultra-preview",
    ],
}

TIER_VOTING_AUTHORITY = {
    "quick": VotingAuthority.FULL,
    "balanced": VotingAuthority.FULL,
    "high": VotingAuthority.FULL,
    "reasoning": VotingAuthority.FULL,
    "frontier": VotingAuthority.ADVISORY,  # Shadow mode by default
}
```

The frontier tier:
- Allows preview/beta models
- Accepts higher latency
- Tolerates rate limits
- Uses Shadow Mode by default
- Prioritizes quality (85% weight) over cost/speed

## Cost Ceiling Protection

Frontier models can be expensive. We check costs *before* calling the model using rate card pricing:

```python
from typing import Tuple

FRONTIER_COST_MULTIPLIER = 5.0  # Max 5x high-tier average

def apply_cost_ceiling(
    model_id: str,
    model_price_per_1k: float,  # From rate card, not per-query cost
    tier: str,
    high_tier_avg_price: float
) -> Tuple[bool, str]:
    """
    Pre-flight check: is this model too expensive?

    Uses rate card pricing ($/1k tokens), not actual query cost.
    This check happens BEFORE calling the model.
    """
    if tier != "frontier":
        return True, ""  # No check for non-frontier

    ceiling = high_tier_avg_price * FRONTIER_COST_MULTIPLIER
    if model_price_per_1k > ceiling:
        return False, f"Rate ${model_price_per_1k:.4f}/1k exceeds ceiling ${ceiling:.4f}/1k"
    return True, ""
```

If your high-tier models average $0.01/1k tokens, a frontier model can't exceed $0.05/1k tokens. This prevents adding absurdly expensive experimental models.

## Hard Fallback

If a frontier model fails (timeout, rate limit, API error), we fall back to high tier:

```python
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class FallbackResult:
    response: str
    used_fallback: bool
    reason: Optional[str] = None

async def execute_with_fallback(
    query: str,
    frontier_model: str,
    fallback_tier: str = "high"
) -> FallbackResult:
    """Execute with automatic fallback on failure."""
    try:
        response = await query_model(frontier_model, query, timeout=300)
        return FallbackResult(response=response, used_fallback=False)
    except (TimeoutError, RateLimitError, APIError) as e:
        logger.warning(f"Frontier {frontier_model} failed: {e}. Falling back to {fallback_tier}")
        fallback_models = get_tier_models(fallback_tier)
        response = await query_council(fallback_models, query)
        return FallbackResult(response=response, used_fallback=True, reason=str(e))
```

The user gets a response. The system logs the fallback. You learn which frontier models aren't reliable.

## Metrics to Track

For each auditioning model, we track:

```python
@dataclass
class ModelAuditionMetrics:
    model_id: str
    state: AuditionState
    session_count: int
    days_tracked: int

    # Quality metrics
    avg_borda_score: float      # Average ranking position (lower = better)
    quality_percentile: float   # vs. established models
    consensus_agreement: float  # How often it agreed with consensus

    # Reliability metrics
    timeout_rate: float
    error_rate: float
    consecutive_failures: int
    quarantine_count: int

    # Shadow metrics
    shadow_votes_cast: int
    shadow_consensus_match: float  # Would its votes have matched consensus?
```

## Practical Example

**Day 1:** `openai/gpt-5-preview` appears in OpenRouter.

```
State: SHADOW
Sessions: 0
Voting: Advisory (0%)
Selection rate: 30%
```

**Day 5:** 15 sessions completed, no failures.

```
State: PROBATION
Sessions: 15
Quality percentile: 72%
Consensus agreement: 85%
```

**Day 14:** 30 sessions, one timeout.

```
State: EVALUATION
Sessions: 30
Quality percentile: 78%
Consensus agreement: 88%
Selection rate: 60%
```

**Day 28:** 55 sessions, quality at 80th percentile.

```
State: FULL
Sessions: 55
Quality percentile: 80%
Voting: Full (100%)
Selection rate: 100%
```

Model graduated in 28 days with 55 sessions. It proved itself through production traffic, not benchmarks.

## Configuration

```yaml
council:
  audition:
    enabled: true
    max_audition_seats: 1  # Max shadow models per session

    shadow:
      min_sessions: 10
      min_days: 3
      max_failures: 3
      selection_rate: 0.30  # 30% of requests

    probation:
      min_sessions: 25
      min_days: 7
      max_failures: 5
      selection_rate: 0.30

    evaluation:
      min_sessions: 50
      min_quality_percentile: 0.75
      max_failures: 10
      selection_rate_range: [0.30, 1.0]  # Ramps up with quality

    quarantine:
      cooldown_hours: 24
      max_cycles: 3  # After 3, move to DEAD
```

## The Principle

> Don't guess. Measure.

Shadow Mode gives you production data on experimental models without production risk. The audition system ensures models earn their voting rights through demonstrated performance.

New model drops? Add it to frontier tier. Watch the metrics. Promote when ready. No guessing required.

---

*This is post 7 of 7. You've completed the LLM Council technical series!*

---

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
