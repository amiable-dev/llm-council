# The Latency Tax: Parallel Execution Patterns

**Querying 4 models doesn't mean 4x latency. Here's how to pay the latency tax once.**

---

The first objection to multi-model systems is always latency. "You're querying 4 models? That's 4x slower!"

No. If you do it right, querying 4 models costs you the latency of the *slowest* model, not the sum. And with proper timeout handling, you don't even have to wait for the slowest.

## The Parallel Execution Pattern

Python's `asyncio.gather()` runs all queries concurrently:

```python
import asyncio
from typing import Dict, List, Optional

async def query_council_parallel(
    models: List[str],
    messages: List[Dict],
    timeout: float = 30.0
) -> Dict[str, Optional[Dict]]:
    """Query all models in parallel with per-model timeout."""

    async def query_with_timeout(model: str) -> tuple[str, Optional[Dict]]:
        try:
            result = await asyncio.wait_for(
                query_model(model, messages),
                timeout=timeout
            )
            return (model, result)
        except asyncio.TimeoutError:
            logger.warning(f"{model} timed out after {timeout}s")
            return (model, None)
        except Exception as e:
            logger.error(f"{model} failed: {e}")
            return (model, None)

    # All queries run concurrently
    results = await asyncio.gather(
        *[query_with_timeout(m) for m in models],
        return_exceptions=False  # Exceptions handled per-task
    )

    return {model: result for model, result in results}
```

**Latency analysis:**

| Scenario | Sequential | Parallel |
|----------|------------|----------|
| GPT-4o (2s) + Claude (3s) + Gemini (4s) + Grok (5s) | 14s | 5s |
| Same models, Grok times out at 30s | 39s | 30s |
| Same models, Grok excluded | 9s | 4s |

With parallel execution, total latency equals your slowest model—plus a small async overhead (~10ms).

## Timeout Strategy: Don't Wait for Stragglers

A 4-model council with a 30s timeout shouldn't wait 30s if 3 models respond in 5s:

```python
async def query_with_early_completion(
    models: List[str],
    messages: List[Dict],
    per_model_timeout: float = 30.0,
    min_responses: int = 3
) -> Dict[str, Optional[Dict]]:
    """Return early when we have enough responses."""

    tasks = {
        model: asyncio.create_task(query_model(model, messages))
        for model in models
    }

    results = {}
    pending = set(tasks.values())
    start_time = asyncio.get_event_loop().time()

    while pending and len(results) < len(models):
        # Wait for next completion or timeout
        remaining_timeout = per_model_timeout - (asyncio.get_event_loop().time() - start_time)
        if remaining_timeout <= 0:
            break

        done, pending = await asyncio.wait(
            pending,
            timeout=min(remaining_timeout, 1.0),  # Check every 1s
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in done:
            model = next(m for m, t in tasks.items() if t == task)
            try:
                results[model] = task.result()
            except Exception:
                results[model] = None

        # Early exit if we have enough responses
        successful = sum(1 for r in results.values() if r is not None)
        if successful >= min_responses:
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
            break

    return results
```

With `min_responses=3`, if 3 models respond in 5s and the 4th is still thinking, we proceed with 3 responses. The straggler gets cancelled.

## Tier-Based Model Selection

Not all queries need GPT-5 and Claude Opus. Simple queries can use faster, cheaper models:

```python
TIER_POOLS = {
    "quick": [
        "openai/gpt-4o-mini",       # ~2s, $0.15/1M tokens
        "anthropic/claude-3-5-haiku", # ~2s, $0.80/1M tokens
        "google/gemini-2.0-flash",    # ~1s, $0.10/1M tokens
    ],
    "balanced": [
        "openai/gpt-4o",              # ~4s, $2.50/1M tokens
        "anthropic/claude-3-5-sonnet", # ~5s, $3.00/1M tokens
        "google/gemini-1.5-pro",      # ~4s, $1.25/1M tokens
    ],
    "high": [
        "openai/gpt-4o",              # ~4s, $2.50/1M tokens
        "anthropic/claude-opus-4.5",  # ~10s, $15/1M tokens
        "google/gemini-3-pro",        # ~8s, $1.25/1M tokens
        "x-ai/grok-4",                # ~6s, $3.00/1M tokens
    ],
    "reasoning": [
        "openai/o1",                  # ~60s, $15/1M tokens
        "anthropic/claude-opus-4.5",  # ~10s, $15/1M tokens
        "deepseek/deepseek-r1",       # ~30s, $0.55/1M tokens
    ],
}

TIER_TIMEOUTS = {
    "quick": 30,      # 30s budget
    "balanced": 90,   # 90s budget
    "high": 180,      # 3 min budget
    "reasoning": 600, # 10 min budget
}
```

A simple query like "What's 2+2?" uses quick tier: 3 fast models, 30s timeout, ~$0.001 total cost.

A complex query like "Design a distributed database schema" uses reasoning tier: 3 thinking models, 10 minute timeout, ~$0.50 total cost.

## Cost Analysis: When Multi-Model Pays Off

Multi-model isn't always the right choice. Here's the math:

**Single model (GPT-4o):**
- Latency: ~4s
- Cost: ~$0.01 per query
- Error rate: ~5% hallucination baseline

**4-model council (high tier):**
- Latency: ~10s (slowest model)
- Cost: ~$0.08 per query (4x generation + peer review + synthesis)
- Error rate: ~1% (peer review catches most hallucinations)

**Break-even analysis:**

If catching a hallucination saves you $X (user trust, manual review, downstream errors), then multi-model is worth it when:

```
Council cost - Single model cost < Error reduction × Value of avoided error

$0.08 - $0.01 < (5% - 1%) × $X
$0.07 < 4% × $X
$X > $1.75
```

If each hallucination costs you more than $1.75 to fix, the council pays for itself.

## The Three-Stage Pipeline

The full council pipeline has three stages:

```
Stage 1: Parallel Generation  ~5s  (slowest model)
     ↓
Stage 2: Peer Review         ~8s  (all models review all responses)
     ↓
Stage 3: Chairman Synthesis  ~3s  (single model)
                            ────
                            ~16s total
```

**Stage 1** runs in parallel—4 models, slowest wins.

**Stage 2** is the expensive part. Each model sees all responses (~2000 tokens input) and produces rankings. This is O(N × total_response_length).

**Stage 3** is a single model call with all context.

### Optimizing Stage 2

Stage 2 is where optimization matters most:

```python
# Naive: Each model reviews sequentially
for model in council_models:
    ranking = await get_ranking(model, all_responses)  # ~8s each
# Total: ~32s for 4 models

# Better: Parallel reviews
rankings = await asyncio.gather(
    *[get_ranking(m, all_responses) for m in council_models]
)
# Total: ~8s (slowest reviewer)
```

Even Stage 2 is parallelizable. Each reviewer works independently.

## Circuit Breakers: Fail Fast

When a model is consistently slow or erroring, stop trying:

```python
from dataclasses import dataclass, field
from collections import deque
import time

@dataclass
class CircuitBreaker:
    model_id: str
    failure_threshold: float = 0.25  # 25% failure rate
    window_seconds: int = 600        # 10 minute window
    cooldown_seconds: int = 1800     # 30 minute cooldown

    _failures: deque = field(default_factory=deque)
    _requests: deque = field(default_factory=deque)
    _opened_at: float = 0.0

    def is_open(self) -> bool:
        """Check if circuit is open (model blocked)."""
        if self._opened_at and time.time() - self._opened_at < self.cooldown_seconds:
            return True
        return False

    def record_success(self) -> None:
        now = time.time()
        self._requests.append(now)
        self._prune_old_entries(now)

    def record_failure(self) -> None:
        now = time.time()
        self._failures.append(now)
        self._requests.append(now)
        self._prune_old_entries(now)

        if self._failure_rate() > self.failure_threshold:
            self._opened_at = now
            logger.warning(f"Circuit opened for {self.model_id}")

    def _prune_old_entries(self, now: float) -> None:
        """Remove entries outside the sliding window."""
        cutoff = now - self.window_seconds
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _failure_rate(self) -> float:
        if len(self._requests) < 5:  # Minimum samples
            return 0.0
        return len(self._failures) / len(self._requests)
```

If a model fails 25% of requests in the last 10 minutes, we stop calling it for 30 minutes. The remaining models handle the load.

## Practical Recommendations

1. **Start with balanced tier** for most queries. Quick tier sacrifices too much quality for marginal latency gains.

2. **Set aggressive per-model timeouts** (30s for balanced, 60s for high). Don't let one slow model drag everyone down.

3. **Use min_responses** to proceed early. 3 out of 4 responses is usually enough.

4. **Monitor P95 latency, not average**. A model that's 3s average but 30s P95 will hurt your tail latency.

5. **Circuit break aggressively**. A model failing 25% of requests is worse than having 3 reliable models.

## What's Next

This is post 4 of 7. Coming up:
- **Post 5**: [Detecting Evaluator Bias](./05-detecting-evaluator-bias.md)
- **Post 6**: [The Accuracy Ceiling](./06-accuracy-ceiling.md)

---

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
