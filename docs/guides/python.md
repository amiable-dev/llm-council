# Python Library Guide

Use LLM Council directly in your Python applications.

## Installation

```bash
pip install llm-council-core
```

## Basic Usage

```python
import asyncio
from llm_council import consult_council

async def main():
    result = await consult_council(
        "What are best practices for error handling?",
        confidence="balanced"
    )
    print(result.synthesis)

asyncio.run(main())
```

## Full Council Access

For stage-level detail, `run_full_council` returns the raw stage tuples
(`stage1_results` is a **list** of `{model, response}` dicts; `stage3_result`
is the chairman's `{model, response}` dict):

```python
import asyncio
from llm_council.council import run_full_council

async def detailed_query():
    stage1, stage2, stage3, metadata = await run_full_council(
        "Compare microservices vs monolith architecture"
    )

    # Individual model responses (a list, in completion order)
    for entry in stage1:
        print(f"{entry['model']}: {entry['response'][:100]}...")

    # Borda-aggregated rankings (best first)
    print(f"Top response: {metadata['aggregate_rankings'][0]}")

    # Chairman synthesis
    print(f"Final: {stage3['response']}")

    # ADR-011 cost transparency (usage is soft-fail: use .get)
    usage = metadata.get("usage", {}).get("total", {})
    print(f"Cost: {usage}")

asyncio.run(detailed_query())
```

The simpler `consult_council` facade above wraps this and is the right
choice unless you need the per-stage tuples.

## Jury Mode

```python
from llm_council import consult_council
from llm_council.verdict import VerdictType

async def review_pr(diff: str):
    result = await consult_council(
        f"Should this PR be approved?\n\n{diff}",
        verdict_type="binary",   # or VerdictType.BINARY
        include_dissent=True,
    )

    # verdict dict keys: verdict, confidence, rationale, dissent,
    # deadlocked, borda_spread (VerdictResult.to_dict)
    verdict = result.metadata["verdict"]
    if verdict["verdict"] == "approved" and verdict["confidence"] >= 0.7:
        return True, verdict["rationale"]
    return False, verdict.get("dissent") or "No dissent recorded"

asyncio.run(review_pr("..."))
```

## Configuration

```python
from llm_council.unified_config import get_config, reload_config

# Get current config
config = get_config()
print(config.tiers.default)

# Reload after env changes
reload_config()
```
