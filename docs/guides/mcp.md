# MCP Server Guide

Use LLM Council as a Model Context Protocol (MCP) server with Claude Code or Claude Desktop.

## Installation

```bash
pip install "llm-council-core[mcp]"
```

## Claude Code Setup

```bash
# Store API key securely
llm-council setup-key

# Add MCP server
claude mcp add llm-council --scope user -- llm-council
```

## Claude Desktop Setup

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "llm-council": {
      "command": "llm-council"
    }
  }
}
```

## Available Tools

### `consult_council`

Ask the LLM council a question.

**Arguments:**

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `query` | string | required | Question to ask |
| `confidence` | string | `"high"` | `quick`, `balanced`, `high`, `reasoning` |
| `verdict_type` | string | `"synthesis"` | `synthesis`, `binary`, `tie_breaker` |
| `include_details` | boolean | `false` | Include individual responses |
| `include_dissent` | boolean | `false` | Include minority opinions |

**Example:**

```
Use consult_council with confidence="balanced" to ask:
"What are the trade-offs between REST and GraphQL?"
```

### `council_health_check`

Verify the council is ready.

**Returns:**

- `api_key_configured`: Whether key is set
- `key_source`: Where key came from
- `council_size`: Number of models
- `ready`: Whether council is operational

## Jury Mode

For binary decisions:

```
Use consult_council with verdict_type="binary" to ask:
"Should we approve this architectural change?"
```

Returns:
```json
{
  "verdict": "approved",
  "confidence": 0.75,
  "rationale": "Council agreed..."
}
```
