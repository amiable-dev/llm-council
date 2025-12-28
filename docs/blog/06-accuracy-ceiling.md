# The Accuracy Ceiling

**A beautifully written hallucination scored 7.2/10. We capped it at 4.0. Here's why.**

---

We learned this the hard way: a confident lie can outscore a hesitant truth.

When we first implemented multi-dimensional scoring, a response with fabricated citations, perfect grammar, and clear organization scored 7.2/10. It was completely wrong, but it *sounded* authoritative.

That's when we introduced the accuracy ceiling.

## The Problem: Weighted Averages Fail

Our rubric scores responses on five dimensions:

| Dimension | Weight |
|-----------|--------|
| Accuracy | 35% |
| Relevance | 10% |
| Completeness | 20% |
| Conciseness | 15% |
| Clarity | 20% |

A well-written hallucination might score:

```
Accuracy:     3/10  (fabricated facts)
Relevance:   10/10  (directly addressed question)
Completeness: 9/10  (comprehensive, just wrong)
Conciseness:  9/10  (efficiently written)
Clarity:     10/10  (beautifully organized)

Weighted average: 0.35(3) + 0.10(10) + 0.20(9) + 0.15(9) + 0.20(10)
                = 1.05 + 1.0 + 1.8 + 1.35 + 2.0
                = 7.2/10
```

A 7.2 would rank this response in the top half. That's a problem.

## The Solution: Accuracy as a Ceiling

Instead of treating accuracy as just another weighted dimension, we make it a **ceiling** on the overall score:

```python
from typing import Dict

def calculate_score_with_ceiling(scores: Dict[str, int]) -> float:
    """
    Calculate weighted score with accuracy acting as a ceiling.

    Raises KeyError if accuracy is missing - fail-safe by design.
    """
    weights = {
        "accuracy": 0.35,
        "relevance": 0.10,
        "completeness": 0.20,
        "conciseness": 0.15,
        "clarity": 0.20,
    }

    # Require accuracy - missing accuracy is an error, not a default of 10
    if "accuracy" not in scores:
        raise KeyError("accuracy score is required")

    accuracy = scores["accuracy"]

    # Calculate base weighted score (only for present dimensions)
    base_score = sum(
        scores[dim] * weights[dim]
        for dim in weights
        if dim in scores
    )

    # Apply accuracy ceiling
    if accuracy < 5:
        ceiling = 4.0  # Max 40%
    elif accuracy < 7:
        ceiling = 7.0  # Max 70%
    else:
        ceiling = 10.0  # No ceiling

    return round(min(base_score, ceiling), 2)
```

Now our confident hallucination:

```
Base weighted score: 7.2
Accuracy: 3 → ceiling applies
Final score: min(7.2, 4.0) = 4.0/10
```

The beautiful lie drops from 7.2 to 4.0. It cannot rank in the top half.

## The Threshold Logic

The ceiling thresholds map to behavioral definitions:

| Accuracy | Meaning | Ceiling | Rationale |
|----------|---------|---------|-----------|
| < 5 | Significant errors or hallucinations | 4.0 | Fundamentally unreliable |
| 5-6 | Mixed accuracy, some errors | 7.0 | Useful but flawed |
| 7+ | Mostly or completely accurate | None | Quality differentiates |

These aren't arbitrary. They align with our scoring anchors:

**Accuracy 3-4: "Significant errors"**
> Major misconceptions or outdated information. Response cannot be trusted.

**Accuracy 5-6: "Mixed accuracy"**
> Several minor factual errors, but main point may be valid.

**Accuracy 7-8: "Mostly accurate"**
> One date slightly off, but core message correct.

If a reviewer scores accuracy below 5, they're saying "this response has significant errors." Such a response should not rank highly, regardless of how well it's written.

## Safety Gate: Hard Failures

Some content should never rank, period. We add a safety gate before rubric scoring:

```python
import re
from typing import List, Tuple

SAFETY_PATTERNS = {
    "dangerous_instructions": r"(how to|instructions for).*(bomb|explosive|weapon)",
    "malware_hacking": r"(hack into|exploit|bypass).*(account|system|security)",
    "pii_exposure": r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern
}

EXCLUSION_CONTEXTS = [
    "to prevent this attack",
    "for educational purposes",
    "i cannot provide",
    "this is dangerous and",
    "security researchers",
    "defensive measures",
]

def is_defensive_context(response: str) -> bool:
    """Check if harmful pattern appears in defensive/educational context."""
    lower_response = response.lower()
    return any(ctx in lower_response for ctx in EXCLUSION_CONTEXTS)

def check_response_safety(response: str) -> Tuple[bool, List[str]]:
    """
    Check response for harmful content.

    Returns (passed, flagged_patterns).
    Educational/defensive content is allowed.
    """
    # Skip safety check for defensive content
    if is_defensive_context(response):
        return True, []

    flagged = []
    for pattern_name, pattern in SAFETY_PATTERNS.items():
        # re.DOTALL allows .* to match across newlines
        if re.search(pattern, response, re.IGNORECASE | re.DOTALL):
            flagged.append(pattern_name)

    return len(flagged) == 0, flagged

def apply_safety_gate(score: float, safety_result: Tuple[bool, List[str]]) -> float:
    """Cap score if safety check fails."""
    passed, _ = safety_result
    if not passed:
        return 0.0  # Hard cap
    return score
```

A bomb-making guide with perfect clarity and organization still scores 0.

## Real Example

Query: "What's the capital of Australia?"

**Response A:**
> Canberra is the capital of Australia. It was chosen as a compromise between Sydney and Melbourne in 1908.

Scores: Accuracy=10, Relevance=10, Completeness=9, Conciseness=10, Clarity=10

```
Weighted: 0.35(10) + 0.10(10) + 0.20(9) + 0.15(10) + 0.20(10)
        = 3.5 + 1.0 + 1.8 + 1.5 + 2.0
        = 9.8 → Final: 9.8 (no ceiling)
```

**Response B:**
> Sydney is the capital of Australia and its largest city, known for the Opera House.

Scores: Accuracy=2, Relevance=10, Completeness=8, Conciseness=10, Clarity=10

```
Weighted: 0.35(2) + 0.10(10) + 0.20(8) + 0.15(10) + 0.20(10)
        = 0.7 + 1.0 + 1.6 + 1.5 + 2.0
        = 6.8 → Final: 4.0 (ceiling applied, accuracy < 5)
```

Response B is wrong (Sydney is not the capital). Without the ceiling, it would score 6.8. With the ceiling, it drops to 4.0—properly penalized for fundamental incorrectness.

## The Five Dimensions

With the ceiling mechanism, our rubric becomes:

| Dimension | Weight | Role |
|-----------|--------|------|
| **Accuracy** | 35% + ceiling | Primary gate |
| **Relevance** | 10% | Stays on topic |
| **Completeness** | 20% | Addresses all parts |
| **Conciseness** | 15% | Efficient |
| **Clarity** | 20% | Well-organized |

**Why these weights?**

- **Accuracy dominates** because wrong answers are worse than incomplete ones
- **Relevance is low** because off-topic but accurate is better than on-topic hallucination
- **Conciseness is lower** than completeness because missing information is worse than extra information
- **Clarity matters** because a correct but confusing answer isn't useful

## Scoring Anchors

To reduce inter-reviewer noise, we define what each score means:

**Accuracy Anchors:**

| Score | Definition | Example |
|-------|------------|---------|
| 9-10 | Completely accurate, no errors | All facts verifiable |
| 7-8 | Mostly accurate, minor imprecisions | One date slightly off |
| 5-6 | Mixed accuracy, some errors | Several minor errors |
| 3-4 | Significant errors | Major misconceptions |
| 1-2 | Mostly incorrect or hallucinated | Fabricated facts |

**Conciseness Anchors:**

| Score | Definition | Example |
|-------|------------|---------|
| 9-10 | Every word adds value | Dense, efficient |
| 7-8 | Mostly efficient, minor padding | Slight verbosity |
| 5-6 | Some unnecessary content | Redundant explanations |
| 3-4 | Significant padding | Filler phrases |
| 1-2 | Extremely verbose | Bloated, buries the answer |

These anchors give reviewers concrete targets. "Is this a 7 or an 8?" becomes answerable.

## Configuration

```bash
# Enable rubric scoring (off by default)
export LLM_COUNCIL_RUBRIC_SCORING=true

# Enable safety gate
export LLM_COUNCIL_SAFETY_GATE=true

# Custom weights (must sum to 1.0)
export LLM_COUNCIL_WEIGHT_ACCURACY=0.35
export LLM_COUNCIL_WEIGHT_RELEVANCE=0.10
export LLM_COUNCIL_WEIGHT_COMPLETENESS=0.20
export LLM_COUNCIL_WEIGHT_CONCISENESS=0.15
export LLM_COUNCIL_WEIGHT_CLARITY=0.20
```

## Fallback Behavior

If a reviewer ignores the rubric and gives a single holistic score, we fall back to the original ranking-based aggregation. The system gracefully degrades.

## The Principle

> A confident lie is worse than a hesitant truth.

The accuracy ceiling encodes this principle into the scoring algorithm. No amount of eloquence can overcome fundamental incorrectness.

---

*This is post 6 of 7. Next: [Shadow Mode & Model Auditions](./07-shadow-mode-auditions.md)*

---

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
