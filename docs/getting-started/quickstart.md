# Quick Start

Get up and running with LLM Council in 5 minutes.

## Prerequisites

- Python 3.11+
- OpenRouter API key (get one at [openrouter.ai](https://openrouter.ai))

## Step 1: Install

```bash
pip install "llm-council-core[mcp]"
```

## Step 2: Set API Key

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

## Step 3: Use with Claude Code

```bash
claude mcp add llm-council --scope user -- llm-council
```

Then in Claude Code:

```
Consult the LLM council about best practices for error handling
```

## Alternative: Python Library

```python
import asyncio
from llm_council import consult_council

async def main():
    result = await consult_council(
        "What are the best practices for error handling in Python?",
        confidence="balanced"
    )
    print(result.synthesis)

asyncio.run(main())
```

## Confidence Levels

| Level | Models | Time | Use Case |
|-------|--------|------|----------|
| `quick` | Fast models | ~30s | Simple questions |
| `balanced` | Mid-tier | ~90s | Most questions |
| `high` | Full council | ~180s | Important decisions |
| `reasoning` | Deep thinking | ~600s | Complex analysis |

## Next Steps

- [Configuration](configuration.md) - Customize your council
- [MCP Server Guide](../guides/mcp.md) - MCP integration details
