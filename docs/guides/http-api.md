# HTTP API Guide

Use LLM Council as an HTTP server with REST API and SSE streaming.

## Installation

```bash
pip install "llm-council-core[http]"
```

## Quick Start

```bash
# Set your API keys
export OPENROUTER_API_KEY=sk-or-v1-...
export LLM_COUNCIL_API_TOKEN=$(openssl rand -hex 16)

# Start server
llm-council serve --port 8000
```

## Authentication

When `LLM_COUNCIL_API_TOKEN` is set, all protected endpoints require Bearer token authentication:

```bash
curl -X POST http://localhost:8000/v1/council/run \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?"}'
```

!!! warning "Security"
    Without `LLM_COUNCIL_API_TOKEN` set, the API allows unauthenticated access. This is useful for local development but **never deploy publicly without setting a token**.

## Endpoints

### GET /health

Health check endpoint. **Does not require authentication.**

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{"status": "ok", "service": "llm-council-local"}
```

### POST /v1/council/run

Run a full council deliberation. **Requires authentication.**

```bash
curl -X POST http://localhost:8000/v1/council/run \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What are best practices for error handling?",
    "verdict_type": "synthesis"
  }'
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | **Yes** | The question to deliberate |
| `models` | string[] | No | List of models (uses defaults if omitted) |
| `api_key` | string | No | OpenRouter API key (overrides env var) |
| `verdict_type` | string | No | `synthesis` (default), `binary`, or `tie_breaker` |
| `include_dissent` | boolean | No | Include minority opinions (default: false) |
| `webhook_url` | string | No | URL for webhook notifications |
| `webhook_events` | string[] | No | Events to subscribe to |
| `webhook_secret` | string | No | HMAC secret for webhook verification |

**Response:**
```json
{
  "stage1": [
    {"model": "openai/gpt-4o", "response": "..."},
    {"model": "anthropic/claude-3.5-sonnet", "response": "..."}
  ],
  "stage2": [
    {"reviewer": "openai/gpt-4o", "rankings": [...], "raw_evaluation": "..."}
  ],
  "stage3": {
    "synthesis": "Final synthesized answer...",
    "chairman": "anthropic/claude-3.5-sonnet"
  },
  "metadata": {
    "aggregate_rankings": [...],
    "label_to_model": {...}
  }
}
```

### GET /v1/council/stream

Stream council events via Server-Sent Events (SSE). **Requires authentication.**

```bash
curl -N "http://localhost:8000/v1/council/stream?prompt=What+is+AI" \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `prompt` | **Yes** | The question to deliberate |
| `models` | No | Comma-separated list of models |
| `api_key` | No | OpenRouter API key |

## SSE Events

| Event | Description |
|-------|-------------|
| `council.deliberation_start` | Council execution starting |
| `council.stage1.complete` | Stage 1 responses collected |
| `council.stage2.complete` | Stage 2 rankings complete |
| `council.complete` | Final synthesis ready (includes full result) |
| `council.error` | An error occurred |

## Client Examples

### JavaScript (Browser)

```javascript
const token = 'YOUR_API_TOKEN';
const url = new URL('/v1/council/stream', 'http://localhost:8000');
url.searchParams.set('prompt', 'What is the meaning of life?');

const source = new EventSource(url, {
  headers: { 'Authorization': `Bearer ${token}` }
});

source.addEventListener('council.complete', (e) => {
  const result = JSON.parse(e.data);
  console.log('Answer:', result.result.synthesis);
  source.close();
});

source.addEventListener('council.error', (e) => {
  console.error('Error:', JSON.parse(e.data));
  source.close();
});
```

### Python

```python
import httpx

response = httpx.post(
    "http://localhost:8000/v1/council/run",
    headers={"Authorization": "Bearer YOUR_API_TOKEN"},
    json={"prompt": "What is 2+2?"}
)
result = response.json()
print(result["stage3"]["synthesis"])
```

### cURL with Webhook

```bash
curl -X POST http://localhost:8000/v1/council/run \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Review this code for security issues",
    "verdict_type": "binary",
    "webhook_url": "https://your-n8n.example.com/webhook/council",
    "webhook_secret": "your-hmac-secret"
  }'
```

## Verdict Types

| Type | Description | Use Case |
|------|-------------|----------|
| `synthesis` | Natural language synthesis (default) | General questions |
| `binary` | Go/no-go decision (approved/rejected) | Code review, approvals |
| `tie_breaker` | Chairman resolves deadlocked decisions | Close votes |

## Error Responses

| Status | Description |
|--------|-------------|
| 400 | Missing required field or invalid request |
| 401 | Missing or invalid API token |
| 500 | Internal server error |

**Example error:**
```json
{
  "detail": "Invalid or missing API token. Provide Authorization: Bearer <token>"
}
```

## Deployment

For production deployment, see:

- [Railway Deployment](../deployment/railway.md)
- [Render Deployment](../deployment/render.md)
- [Local Docker](../deployment/local.md)
