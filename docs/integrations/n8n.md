# n8n Integration

Integrate LLM Council with [n8n](https://n8n.io) to add multi-model AI deliberation to your automation workflows.

## Overview

n8n is a workflow automation platform that connects apps and services. By integrating with LLM Council, you can:

- **Automate code reviews** with multi-model consensus
- **Triage support tickets** using binary verdicts (escalate/standard)
- **Validate content** before publishing with go/no-go decisions
- **Make technical decisions** with a council of AI experts

## Prerequisites

- n8n instance (cloud or self-hosted)
- LLM Council HTTP server running and accessible
- OpenRouter API key (or other gateway credentials)

### Start the LLM Council Server

```bash
# Install with HTTP support
pip install "llm-council-core[http]"

# Set your API key
export OPENROUTER_API_KEY="sk-or-v1-..."

# Start the server
llm-council serve --host 0.0.0.0 --port 8000
```

## Quick Start (5 Minutes)

### 1. Add HTTP Request Node

In your n8n workflow, add an **HTTP Request** node with:

| Setting | Value |
|---------|-------|
| Method | POST |
| URL | `http://your-server:8000/v1/council/run` |
| Body Content Type | JSON |

### 2. Configure the Request Body

```json
{
  "prompt": "{{ $json.input_text }}",
  "verdict_type": "synthesis"
}
```

### 3. Parse the Response

The council returns:

```json
{
  "stage1": [...],
  "stage2": [...],
  "stage3": {
    "synthesis": "The council's final answer..."
  },
  "metadata": {
    "aggregate_rankings": {...}
  }
}
```

Use an **Set** node to extract `{{ $json.stage3.synthesis }}`.

## Webhook Configuration

For async workflows, configure webhook callbacks to receive events as the council deliberates.

### Enable Webhooks in Request

```json
{
  "prompt": "Review this PR for security issues",
  "webhook_url": "https://your-n8n.com/webhook/council-events",
  "webhook_secret": "{{ $env.WEBHOOK_SECRET }}",
  "webhook_events": ["council.complete", "council.error"]
}
```

### HMAC Signature Verification

LLM Council signs all webhook payloads with HMAC-SHA256. Verify signatures to ensure requests are authentic.

**Webhook Headers:**

| Header | Description |
|--------|-------------|
| `X-Council-Signature` | `sha256=<hex-signature>` |
| `X-Council-Timestamp` | Unix timestamp |
| `X-Council-Version` | API version (1.0) |

**Verification in n8n (Function Node):**

```javascript
// Add this as a Function node after your Webhook trigger
const crypto = require('crypto');

const payload = JSON.stringify($input.first().json);
const secret = $env.WEBHOOK_SECRET;
const receivedSig = $input.first().headers['x-council-signature'];

// Generate expected signature
const expectedSig = 'sha256=' + crypto
  .createHmac('sha256', secret)
  .update(payload)
  .digest('hex');

// Verify with timing-safe comparison
const verified = crypto.timingSafeEqual(
  Buffer.from(expectedSig),
  Buffer.from(receivedSig || '')
);

if (!verified) {
  throw new Error('Invalid webhook signature');
}

// Check timestamp (prevent replay attacks)
const timestamp = parseInt($input.first().headers['x-council-timestamp']);
const now = Math.floor(Date.now() / 1000);
if (Math.abs(now - timestamp) > 300) {
  throw new Error('Webhook timestamp too old');
}

return $input.first();
```

## Use Cases

### 1. Code Review Automation

Trigger a council review when a PR is opened:

**Workflow:**
```
GitHub Trigger (PR opened) →
  Fetch PR diff →
  HTTP Request (council) →
  Parse verdict →
  Post comment to PR
```

**Council Prompt:**
```json
{
  "prompt": "Review this code change for:\n1. Security vulnerabilities\n2. Performance issues\n3. Code style\n\nDiff:\n{{ $json.diff }}",
  "verdict_type": "synthesis"
}
```

### 2. Support Ticket Triage

Classify incoming tickets as urgent or standard:

**Workflow:**
```
Email/Form Trigger →
  HTTP Request (council with binary verdict) →
  IF verdict=approved → Route to urgent queue
  ELSE → Route to standard queue
```

**Council Prompt:**
```json
{
  "prompt": "Should this support ticket be escalated to urgent priority?\n\nTicket: {{ $json.subject }}\nBody: {{ $json.body }}\n\nRespond with approved (urgent) or rejected (standard).",
  "verdict_type": "binary"
}
```

**Binary Response:**
```json
{
  "stage3": {
    "verdict": "approved",
    "confidence": 0.85,
    "rationale": "Customer mentions data loss and production outage..."
  }
}
```

### 3. Technical Design Decisions

Use the council as a panel of experts for architecture decisions:

**Workflow:**
```
Manual Trigger (design doc) →
  HTTP Request (council) →
  Format response →
  Send to Slack/Email
```

**Council Prompt:**
```json
{
  "prompt": "As a council of software architects, evaluate this design:\n\n{{ $json.design_doc }}\n\nConsider:\n- Scalability\n- Maintainability\n- Security\n- Cost implications",
  "verdict_type": "synthesis",
  "include_dissent": true
}
```

### 4. Content Validation

Validate marketing content before publishing:

**Workflow:**
```
Content submitted →
  HTTP Request (council with binary verdict) →
  IF approved → Publish
  ELSE → Send back for revision with feedback
```

**Council Prompt:**
```json
{
  "prompt": "Should this marketing content be approved for publication?\n\nContent: {{ $json.content }}\n\nEvaluate for:\n- Factual accuracy\n- Brand voice consistency\n- Legal/compliance issues\n- Grammar and clarity",
  "verdict_type": "binary"
}
```

## Workflow Examples

Import these workflows directly into your n8n instance:

| Workflow | Description | File |
|----------|-------------|------|
| Code Review | PR-triggered multi-model review | [code-review-workflow.json](../examples/n8n/code-review-workflow.json) |
| Support Triage | Binary verdict for ticket routing | [support-triage-workflow.json](../examples/n8n/support-triage-workflow.json) |
| Design Decision | Council of experts for architecture | [design-decision-workflow.json](../examples/n8n/design-decision-workflow.json) |

## SSE Streaming with n8n

For real-time updates, use the streaming endpoint:

```
GET /v1/council/stream?prompt=...
```

**Note:** n8n's HTTP Request node doesn't natively support SSE. For streaming:

1. Use webhook callbacks instead (recommended)
2. Or implement a custom n8n node
3. Or use a proxy that buffers SSE to a single response

## Error Handling

### Timeout Configuration

Council deliberation can take 30-60 seconds. Configure adequate timeouts:

```json
{
  "timeout": 120000
}
```

### Retry Logic

Add an **IF** node after the HTTP Request to check for errors:

```javascript
// Check for council errors
const hasError = $json.error || !$json.stage3;
return [{ json: { hasError } }];
```

### Rate Limiting

If you hit rate limits, add exponential backoff:

1. Add a **Wait** node before retry
2. Use formula: `{{ Math.min(30, Math.pow(2, $runIndex)) }}` seconds

## Environment Variables

Store sensitive values as n8n credentials or environment variables:

| Variable | Description |
|----------|-------------|
| `LLM_COUNCIL_URL` | Base URL of council server |
| `WEBHOOK_SECRET` | HMAC secret for webhook verification |
| `OPENROUTER_API_KEY` | API key (if using BYOK mode) |

## Troubleshooting

### Connection Refused

Ensure the council server is running and accessible from your n8n instance:

```bash
curl http://your-server:8000/health
# Should return: {"status": "ok", "service": "llm-council-local"}
```

### Invalid Signature Errors

1. Verify the webhook secret matches between n8n and council request
2. Check timestamp is within 5 minutes
3. Ensure payload is JSON-stringified before signing

### Slow Responses

Council deliberation involves multiple LLM calls. For faster responses:

1. Use `confidence: "quick"` for faster but less thorough deliberation
2. Reduce the number of models in your council configuration
3. Consider caching common queries

## Security Best Practices

1. **Always verify HMAC signatures** on webhook endpoints
2. **Use HTTPS** for all production webhooks
3. **Rotate webhook secrets** periodically
4. **Validate timestamp** to prevent replay attacks
5. **Store API keys** in n8n credentials, not workflow JSON

## Next Steps

- [HTTP API Reference](../api.md) - Full API documentation
- [HTTP API Guide](../guides/http-api.md) - Endpoint reference and SSE streaming
- [Configuration Guide](../getting-started/configuration.md) - Customize your council
