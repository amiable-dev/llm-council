# Integrations

Connect LLM Council to your existing tools and workflows.

## Available Integrations

| Integration | Description | Use Cases |
|-------------|-------------|-----------|
| [n8n](n8n.md) | Workflow automation platform | Code review, ticket triage, content validation |

## Integration Patterns

LLM Council supports multiple integration patterns:

### HTTP API (Recommended for Automation)

Use the HTTP API for workflow automation tools like n8n, Make, or Zapier:

```bash
# Start the HTTP server
llm-council serve --port 8000

# Call the council endpoint
curl -X POST http://localhost:8000/v1/council/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Review this code for security issues: ..."}'
```

### MCP Server (For AI Assistants)

Use the MCP server for AI assistants like Claude Code or Claude Desktop:

```bash
claude mcp add llm-council --scope user -- llm-council
```

#### Configuring MCP Client Timeouts

The council's `high` and `reasoning` tiers can take 3–10 minutes when frontier
reasoning models review large inputs (e.g. multi-thousand-line ADRs). MCP
clients have their own transport-layer timeout that is **independent of the
server's tier budget**. If the client times out first, you'll see "MCP layer
timeout" errors even though the council is still working — see
[ADR-012](https://github.com/amiable-dev/llm-council/blob/master/docs/adr/ADR-012-mcp-server-reliability.md)
and issue [#327](https://github.com/amiable-dev/llm-council/issues/327) for
the underlying constraint.

Set `MCP_TIMEOUT` (milliseconds) on the **client** to at least the tier's
server budget:

| Tier        | Server budget | Minimum client `MCP_TIMEOUT` |
|-------------|---------------|-----------------------------|
| `quick`     | ~30s          | `60000` (1 min)             |
| `balanced`  | ~90s          | `120000` (2 min)            |
| `high`      | ~180s         | `300000` (5 min)            |
| `reasoning` | ~600s         | `900000` (15 min)           |

In Claude Code, set it per-server in `.mcp.json`:

```json
{
  "mcpServers": {
    "llm-council": {
      "type": "stdio",
      "command": "llm-council",
      "args": [],
      "env": {
        "MCP_TIMEOUT": "900000"
      }
    }
  }
}
```

Or set it globally as a shell env var before launching the client:

```bash
export MCP_TIMEOUT=900000
```

This is the only fix for "consult_council times out at high tier" — the
server is running fine, the client is hanging up early.

### Python SDK (For Custom Applications)

Use the Python SDK for custom integrations:

```python
from llm_council import consult_council

result = await consult_council("Should we approve this PR?", verdict_type="binary")
```

## Webhook Callbacks

LLM Council supports webhook callbacks for async notifications:

- **HMAC-SHA256 signatures** for request verification
- **Configurable events** (stage completion, errors)
- **Retry with exponential backoff**

See [n8n Integration](n8n.md) for webhook configuration examples.

## Coming Soon

- Zapier integration
- Make (Integromat) templates
- Slack bot integration
- GitHub Actions workflow
