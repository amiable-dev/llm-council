# The Case for Multi-Model Architecture

**When one model hallucinates, four models usually catch it. Here's how we built a peer-review system for LLMs.**

---

LLM Council queries multiple models in parallel, has them critique each other anonymously, and synthesizes a consensus. This post explains the architecture and the tradeoffs.

## The Three-Stage Pipeline

### Stage 1: Parallel Generation

Query all council models simultaneously:

```python
import asyncio
from llm_council.openrouter import query_models_parallel

council_models = [
    "openai/gpt-4o",
    "anthropic/claude-3-5-sonnet",
    "google/gemini-2.0-pro",
    "x-ai/grok-2"
]

async def main():
    # All models queried in parallel—latency = slowest model
    responses = await query_models_parallel(
        council_models,
        messages=[{"role": "user", "content": "What's the time complexity of Python's list.sort()?"}]
    )
    return responses

responses = asyncio.run(main())
```

**Latency note**: Stage 1 latency equals your slowest model, not the sum. If GPT-4o responds in 2s and Grok in 5s, you wait 5s.

### Stage 2: Anonymous Peer Review

Each model evaluates and ranks the responses—but they don't know which model produced which. They see "Response A", "Response B", etc.

```python
# Anonymize responses before peer review
label_to_model = {}
anonymized = []
for i, (model, response) in enumerate(responses.items()):
    label = f"Response {chr(65 + i)}"  # A, B, C, D
    label_to_model[label] = {"model": model, "display_index": i}
    anonymized.append({"label": label, "content": response["content"]})

# Each model ranks all responses (excluding their own vote for themselves)
rankings = await collect_peer_rankings(anonymized, council_models)
```

Why anonymize? Models show favoritism. In our testing, GPT-4 consistently ranked other GPT responses higher. Claude preferred Claude-style formatting. Anonymization eliminates this.

**Cost note**: Stage 2 is expensive. Each reviewer sees *all* responses concatenated, so token usage scales as O(N * total_response_length). With 4 models producing 500 tokens each, each Stage 2 call processes ~2000 input tokens. Budget accordingly.

### Stage 3: Chairman Synthesis

A designated "chairman" model synthesizes the final answer:

```python
final_response = await synthesize_final(
    user_query="What's the time complexity of Python's list.sort()?",
    stage1_responses=responses,
    stage2_rankings=rankings,
    chairman_model="anthropic/claude-3-5-sonnet"
)
```

The chairman sees the original responses, the peer evaluations, and aggregate rankings. It produces a synthesis incorporating the best elements.

## A Concrete Example

We asked: "What's the time complexity of Python's `list.sort()`?"

| Model | Response | Peer Rank |
|-------|----------|-----------|
| GPT-4o | "O(n log n) using Timsort" | 3rd |
| Claude | "O(n log n) average and worst case, using Timsort" | 2nd |
| Gemini | "O(n log n), but O(n) for already-sorted data" | **1st** |
| Grok | "O(n log n) using a modified merge sort" | 4th |

Gemini ranked highest for including the best-case optimization. The synthesis:

> Python's `list.sort()` uses Timsort, an adaptive algorithm with O(n log n) average and worst-case complexity. For already-sorted or nearly-sorted data, it achieves O(n) due to its run-detection optimization.

No single model produced this complete answer. The council did.

## Self-Vote Exclusion

Models can't vote for their own responses. This is implemented in the ranking aggregation:

```python
def calculate_aggregate_rankings(stage2_results, label_to_model, exclude_self_votes=True):
    scores = defaultdict(list)

    for result in stage2_results:
        reviewer = result["model"]
        for position, label in enumerate(result["parsed_ranking"]):
            candidate = label_to_model[label]["model"]

            # Skip self-votes
            if exclude_self_votes and reviewer == candidate:
                continue

            # Borda count: lower position = better score
            scores[candidate].append(position + 1)

    # Average position (lower is better)
    return sorted(
        [(model, sum(positions) / len(positions)) for model, positions in scores.items()],
        key=lambda x: x[1]
    )
```

## The Real Tradeoffs

### Latency
Total pipeline latency is **Stage 1 + Stage 2 + Stage 3**, not just Stage 1. For our production setup:
- Stage 1: ~5s (slowest model)
- Stage 2: ~8s (processing all responses)
- Stage 3: ~3s (synthesis)
- **Total: ~16s** vs ~3s for single-model

### Cost
With 4 models at $0.01/1K tokens:
- Stage 1: 4 completions (~$0.08)
- Stage 2: 4 reviews with all responses (~$0.16)
- Stage 3: 1 synthesis (~$0.02)
- **Total: ~$0.26** vs ~$0.02 for single-model

### When It's Worth It
- **High-stakes decisions**: Legal, medical, financial queries
- **Code generation**: Bugs are expensive; peer review catches them
- **Disagreement detection**: If models split 2-2, you know the question is ambiguous

### When It's Not
- High-volume, low-stakes queries
- Real-time chat (16s is too slow)
- Simple factual lookups

That's why we built [tiers](./04-latency-tax-parallel.md)—use the full council for complex queries, fast single-model for simple ones.

## Failure Modes

**What if models disagree 2-2?** We flag this as low-confidence and either escalate to the chairman's judgment or return the disagreement to the user.

**What if the chairman hallucinates?** The chairman prompt includes all peer feedback and rankings. It's instructed to reconcile disagreements, not invent. In practice, chairman errors are rare because it's synthesizing, not generating novel claims.

**What if one model times out?** We continue with the remaining models. A 3-model council is still more reliable than single-model.

## Full API

```python
import asyncio
from llm_council import run_full_council

async def main():
    result = await run_full_council(
        "Explain the CAP theorem and its implications for distributed databases"
    )

    print(f"Stage 1: {len(result['stage1'])} responses")
    print(f"Stage 2: {len(result['stage2'])} evaluations")
    print(f"Final: {result['stage3']['content'][:200]}...")

    # Rankings show which response the council preferred
    for model, score in result['aggregate_rankings']:
        print(f"  {model}: {score:.2f}")

asyncio.run(main())
```

## What's Next

This is post 1 of 7. Coming up:
- **Post 2**: [Building a Fault-Tolerant LLM Gateway](./02-fault-tolerant-gateway.md)
- **Post 3**: [Why Majority Vote Fails for Small Groups](./03-voting-logic-borda.md)
- **Post 4**: [The Latency Tax: Parallel Execution Patterns](./04-latency-tax-parallel.md)

---

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council). Install with `pip install llm-council-core`.*
