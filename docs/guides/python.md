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

```python
from llm_council.council import run_full_council

async def detailed_query():
    stage1, stage2, stage3, metadata = await run_full_council(
        "Compare microservices vs monolith architecture"
    )

    # Individual model responses
    for model, response in stage1.items():
        print(f"{model}: {response[:100]}...")

    # Rankings
    print(f"Top response: {metadata['aggregate_rankings'][0]}")

    # Synthesis
    print(f"Final: {stage3}")

asyncio.run(detailed_query())
```

## Jury Mode

```python
from llm_council.council import run_full_council
from llm_council.verdict import VerdictType

async def review_pr(diff: str):
    _, _, _, metadata = await run_full_council(
        f"Should this PR be approved?\n\n{diff}",
        verdict_type=VerdictType.BINARY,
        include_dissent=True
    )

    verdict = metadata["verdict"]
    if verdict["verdict"] == "approved" and verdict["confidence"] >= 0.7:
        return True, verdict["rationale"]
    return False, verdict.get("dissent", "No dissent")

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
