# HTTP API Guide

Use LLM Council as an HTTP server with REST API and SSE streaming.

## Installation

```bash
pip install "llm-council-core[http]"
```

## Start Server

```bash
llm-council serve --port 8001
```

## Endpoints

### POST /v1/council/query

Submit a query to the council.

```bash
curl -X POST http://localhost:8001/v1/council/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are best practices for error handling?",
    "confidence": "balanced"
  }'
```

### GET /v1/council/stream

Stream council events via SSE.

```bash
curl -N "http://localhost:8001/v1/council/stream?prompt=What+is+AI"
```

### GET /v1/health

Health check endpoint.

```bash
curl http://localhost:8001/v1/health
```

## SSE Events

| Event | Description |
|-------|-------------|
| `council.deliberation_start` | Council begins |
| `council.stage1.complete` | Initial responses ready |
| `model.vote_cast` | Model submitted ranking |
| `council.stage2.complete` | Rankings complete |
| `council.complete` | Final answer ready |

## Client Example (JavaScript)

```javascript
const source = new EventSource('/v1/council/stream?prompt=...');

source.addEventListener('council.complete', (e) => {
  const result = JSON.parse(e.data);
  console.log('Answer:', result.stage3_response);
  source.close();
});
```
