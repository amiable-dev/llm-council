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
| `include_details` | boolean | `false` | Individual responses + full cost breakdown |
| `include_dissent` | boolean | `false` | Include minority opinions |

Every response ends with a one-line **Cost & Tokens** summary (ADR-011);
`include_details=true` adds the per-model/per-stage breakdown.

!!! warning "Set MCP_TIMEOUT for `high`/`reasoning`"
    These tiers exceed many clients' default transport timeout (~60s). Set
    `MCP_TIMEOUT` (milliseconds) in your client config — e.g. 180000 for
    `high`, 600000 for `reasoning` — or the client will drop the connection
    while the council deliberates.

**Example:**

```
Use consult_council with confidence="balanced" to ask:
"What are the trade-offs between REST and GraphQL?"
```

### `verify`

Multi-model verification of code, documents, or any work product with a
machine-actionable verdict — the CI-gate surface. See the
[Verification & CI Gating guide](verify.md) for tiers, `unclear_reason`
routing, calibrated confidence, screening, and evidence injection.

**Arguments:**

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `snapshot_id` | string | required | Git commit SHA (≥7 hex chars) |
| `target_paths` | list | none | Files/dirs to verify (scope to the change) |
| `tier` | string | `"balanced"` | `quick`, `balanced`, `high`, `reasoning` |
| `rubric_focus` | string | none | e.g. `Security`, `Performance` |
| `confidence_threshold` | float | `0.7` | Minimum confidence for PASS |
| `evidence` | list | none | Upstream tool findings (ADR-042) |

Returns verdict/confidence (raw + calibrated), rubric scores, blocking
issues, `unclear_reason` on UNCLEAR, and the transcript location.

### `audit`

Retrieve the persisted transcript for a past verification (by
`verification_id`) — the audit trail behind every verdict.

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
