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
| `evidence` | list | none | Caller-supplied grounding context (#619, ADR-042) |

Every response ends with a one-line **Cost & Tokens** summary (ADR-011);
`include_details=true` adds the per-model/per-stage breakdown.

**Grounding the council with your own context (`evidence`).** If your client
already has retrieval — web search, a RAG index, repo files — you can hand the
retrieved snippets to the council instead of hoping the models know them.
Each item is a dict: `source` (required, `tool@version`-style name), `content`
(required), optional `format` (`markdown`/`json`/`text`), `evidence_id`, and
`strength`. The items are rendered into the question for **every** council
member, clearly fenced as data (models are instructed not to follow
instructions inside evidence bodies), under the same per-tier budget as
`verify`'s evidence (quick 1.5K / balanced 6K / high & reasoning 10K chars —
whole items are dropped when over budget, never truncated mid-string, and the
response tells you which). Two things to know:

- `consult_council` has no pass/fail gate, so `strength="blocking"` has no
  meaning here — such items are **downgraded to informational with an explicit
  note** in the response. Use `verify()` when you want gate semantics.
- No `evidence` ⇒ the query is sent byte-identically as before.

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
issues, `unclear_reason` on UNCLEAR, and the transcript location. Under
`LLM_COUNCIL_STRUCTURED_FINDINGS` (ADR-051) it also returns a typed `findings`
array and computes the verdict from it — see the verify guide's
[Response fields](verify.md#response-fields) and structured-findings sections.

### `audit`

Retrieve the persisted transcript for a past verification (by
`verification_id`) — the audit trail behind every verdict.

### `council_health_check`

Verify the council is ready.

**Parameters:**

- `tier` (default `"high"`): report readiness for the tier a real run would use. Mirrors `consult_council`'s resolution, including its fallback to `high` for an unrecognised value.
- `deep` (default `false`): also probe the configured **chairman** model. Costs one real chairman call. The default probe only checks general API reachability via a cheap lite model, which cannot detect a chairman-specific outage.

**Returns:**

- `api_key_configured`: Whether key is set
- `key_source`: Where key came from
- `default_tier`: The tier whose models are reported below
- `council_size` / `models`: The models a real `consult_council` run would use — resolved from the tier pool, which is what the council actually runs
- `configured_council_models` / `config_warnings`: Present **only** when the flat `council.models` list disagrees with the resolved tier pool, so the two cannot diverge silently
- `api_connectivity.probe_scope`: `connectivity_only` for the default probe, with a `caveat` naming what it does not cover
- `chairman_connectivity`: Present only with `deep=true`
- `ready`: Whether council is operational

!!! warning "`ready: true` does not mean synthesis will succeed"

    The default probe pings a lite model, so it answers *"is the API reachable"*, not *"will the council complete"*. During a chairman outage those diverge: stage-3 synthesis is a single point of failure, so a healthy API can still yield runs with no verdict. Pass `deep=true` before a high-stakes run to probe the chairman itself.

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
