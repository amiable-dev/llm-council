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
