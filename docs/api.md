# LLM Council HTTP API

This document describes the HTTP REST API for LLM Council. The API is available via the optional `[http]` extra.

## Installation

```bash
pip install "llm-council[http]"
```

## Starting the Server

```bash
# Default: 0.0.0.0:8000
llm-council serve

# Custom host and port
llm-council serve --host 127.0.0.1 --port 9000
```

## OpenAPI Specification

The server provides auto-generated OpenAPI documentation:

- **Interactive docs (Swagger UI)**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

## API Reference

### Health Check

Check if the server is running.

```
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "service": "llm-council-local"
}
```

### Run Council Deliberation

Execute the full 3-stage council deliberation process.

```
POST /v1/council/run
```

**Request Body:**
```json
{
  "prompt": "What is the best approach for implementing user authentication?",
  "models": ["openai/gpt-4", "anthropic/claude-3-opus"],  // optional
  "api_key": "sk-..."  // optional if OPENROUTER_API_KEY is set
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | Yes | The question for the council to deliberate |
| `models` | string[] | No | Specific models to use (defaults to configured council) |
| `api_key` | string | No | API key for the default gateway (falls back to env vars) |
| `gateway` | string | No | Gateway to use: `openrouter`, `requesty`, or `direct` |

**Response:**
```json
{
  "stage1": [
    {
      "model": "openai/gpt-4",
      "response": "Individual model response..."
    }
  ],
  "stage2": [
    {
      "model": "anthropic/claude-3-opus",
      "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
      "parsed_ranking": {
        "ranking": ["Response A", "Response B"],
        "scores": {"Response A": 9, "Response B": 7}
      }
    }
  ],
  "stage3": {
    "model": "chairman",
    "response": "Synthesized final answer..."
  },
  "metadata": {
    "label_to_model": {
      "Response A": "openai/gpt-4",
      "Response B": "anthropic/claude-3-opus"
    },
    "aggregate_rankings": [
      {"model": "openai/gpt-4", "borda_score": 0.85, "votes": 3}
    ]
  }
}
```

**Error Responses:**

| Status | Description |
|--------|-------------|
| 400 | API key required but not provided |
| 422 | Validation error (e.g., missing prompt) |
| 500 | Internal server error |

## Authentication

The local development server uses BYOK (Bring Your Own Keys) with multiple gateway options:

### Gateway Options

| Gateway | Environment Variable | Description |
|---------|---------------------|-------------|
| OpenRouter (default) | `OPENROUTER_API_KEY` | 100+ models via single key |
| Requesty | `REQUESTY_API_KEY` | BYOK mode, analytics |
| Direct | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` | Direct provider APIs |

### Configuration

1. **In request body**: Pass `api_key` field (OpenRouter key)
2. **Environment variables**: Set gateway-specific keys

```bash
# OpenRouter (default)
export OPENROUTER_API_KEY=sk-or-v1-...

# Or use direct provider APIs
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=...
export LLM_COUNCIL_DEFAULT_GATEWAY=direct
```

Request body takes precedence over environment variables.

## Protocol Compatibility

This API protocol is shared between:

- **`llm-council[http]`** (OSS): Local development, stateless
- **council-cloud** (Proprietary): Production, with auth/billing/caching

To migrate from local to production, simply change the base URL:

```javascript
// Development
const baseUrl = "http://localhost:8000";

// Production
const baseUrl = "https://api.council.cloud";
```

## Examples

### cURL

```bash
# Using environment variable
export OPENROUTER_API_KEY=sk-...
curl -X POST http://localhost:8000/v1/council/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the best database for this use case?"}'

# Using API key in request
curl -X POST http://localhost:8000/v1/council/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the best approach?", "api_key": "sk-..."}'
```

### Python

```python
import httpx

response = httpx.post(
    "http://localhost:8000/v1/council/run",
    json={
        "prompt": "What is the best approach for X?",
        "api_key": "sk-..."
    }
)
result = response.json()
print(result["stage3"]["response"])  # Final synthesized answer
```

### JavaScript/TypeScript

```javascript
const response = await fetch("http://localhost:8000/v1/council/run", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    prompt: "What is the best approach for X?",
    api_key: "sk-..."
  })
});
const result = await response.json();
console.log(result.stage3.response);  // Final synthesized answer
```

## Design Principles

Per [ADR-009](adr/ADR-009-http-api-open-core-boundary.md):

1. **Stateless**: No database, no persistent storage
2. **Single-tenant**: No multi-user authentication
3. **BYOK**: API keys passed in request or read from environment
4. **Ephemeral**: Logs go to stdout only

For stateful features (auth, caching, audit logs), see council-cloud.
