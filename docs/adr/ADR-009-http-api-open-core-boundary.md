# ADR-009: HTTP API and Open Core Boundary

**Status:** Accepted
**Date:** 2024-12-01
**Deciders:** LLM Council (Unanimous)
**Technical Story:** Define where HTTP API functionality lives in the Open Core model

## Context and Problem Statement

With the package restructured (ADR-008), we need to decide where HTTP REST API functionality should live:

1. **OSS package (`llm-council`)**: The core algorithm, MIT-licensed
2. **Proprietary platform (`council-cloud`)**: Managed service with auth, billing, dashboards

The council-cloud business plan identifies "Managed API endpoint" as a Pro tier feature. However, council feedback recommended "Build plugins for LangChain, Vercel AI SDK - Don't force stack replacement."

**Key tension:** The core library is Python, but target integrations (Vercel AI SDK) are JavaScript/TypeScript. Without an HTTP interface in OSS, JS developers cannot use the library locally.

## Decision Drivers

* **Ecosystem Adoption**: Enable third-party integrations (LangChain, Vercel AI SDK)
* **Developer Experience**: Local dev → Production should be a config change, not a rewrite
* **Monetization**: Protect revenue streams in council-cloud
* **Open Core Principle**: "Monetize infrastructure, not intelligence"
* **BYOK Mandate**: Pro tier uses Bring Your Own Keys (from council feedback)

## Considered Options

### Option A: HTTP API only in council-cloud (Proprietary)

Keep all HTTP functionality proprietary. Self-hosters must build their own wrapper.

**Pros:**
- Clear OSS/proprietary boundary
- API hosting is directly monetized

**Cons:**
- JS/TS developers can't try the product locally
- Plugin authors must reverse-engineer the protocol or wait for official plugins
- Contradicts "don't force stack replacement" feedback
- Fragments the ecosystem (multiple unofficial wrappers)

### Option B: Thin HTTP wrapper in OSS + Full API in Proprietary

Add `llm-council[http]` extra with minimal, stateless HTTP server. council-cloud implements the same protocol with added infrastructure.

**Pros:**
- Enables third-party integrations with canonical protocol
- Local dev parity: change base URL to go from localhost to cloud
- BYOK enforced naturally (no key storage in OSS)
- Follows "monetize infrastructure, not intelligence"
- Clear boundary: stateless = OSS, stateful = paid

**Cons:**
- Requires careful scoping to avoid feature creep
- CLI entry point installed even for library-only users

### Option C: Full HTTP API in OSS

Everything HTTP is open source. council-cloud only adds dashboards and billing.

**Pros:**
- Maximum OSS appeal
- Fully turnkey self-hosting

**Cons:**
- Commoditizes council-cloud's value proposition
- Enables direct competition from forks
- Undermines monetization strategy

## Decision Outcome

**Chosen: Option B** - Thin HTTP wrapper in `llm-council[http]` (OSS) + Full platform API in `council-cloud` (Proprietary).

### Rationale (Council Consensus)

1. **The Language Gap**: Core is Python, target integrations are JS/TS. Without OSS HTTP, JS developers cannot try the product locally.

2. **The Protocol Strategy**: OSS defines the canonical API contract. Both local server and cloud implement the same spec, enabling seamless migration.

3. **The Stateless/Stateful Boundary**: Clear heuristic for what's OSS vs proprietary:
   - **Stateless** (no persistence) → OSS
   - **Stateful** (auth, billing, caching, audit logs) → Proprietary

4. **The Switch Strategy**: Developers build against localhost, change one env var for production.

## Implementation

### The Boundary

| Feature | `llm-council[http]` (OSS) | `council-cloud` (Proprietary) |
|---------|---------------------------|-------------------------------|
| **Role** | Local Dev / Single Tenant | Production / Multi-Tenant |
| **State** | Stateless (ephemeral) | Stateful (persistent) |
| **Auth** | None or basic env token | Users, Teams, API Keys, SSO, RBAC |
| **LLM Keys** | BYOK (in request or .env) | Managed Vault or Secure BYOK |
| **Observability** | stdout logging | Dashboards, Audit Logs, Traces |
| **Performance** | Direct execution | Semantic Caching, Rate Limiting |
| **Database** | None | PostgreSQL, Redis |

### Package Structure

```
src/
└── llm_council/
    ├── __init__.py
    ├── council.py          # Core algorithm
    ├── cli.py              # Entry point dispatcher
    ├── mcp_server.py       # MCP server (optional)
    └── http_server.py      # HTTP server (optional) ← NEW
```

### pyproject.toml

```toml
[project.optional-dependencies]
http = ["fastapi>=0.100.0", "uvicorn>=0.20.0"]
mcp = ["mcp>=1.22.0"]
all = ["llm-council[http,mcp]"]
```

### CLI Entry Point

```python
# llm_council/cli.py
import sys

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        return serve_http()
    else:
        return serve_mcp()

def serve_http():
    try:
        from llm_council.http_server import app
        import uvicorn
    except ImportError:
        print("Error: HTTP dependencies not installed.", file=sys.stderr)
        print("\nInstall with: pip install 'llm-council[http]'", file=sys.stderr)
        sys.exit(1)

    uvicorn.run(app, host="0.0.0.0", port=8000)

def serve_mcp():
    try:
        from llm_council.mcp_server import mcp
    except ImportError:
        print("Error: MCP dependencies not installed.", file=sys.stderr)
        print("\nInstall with: pip install 'llm-council[mcp]'", file=sys.stderr)
        sys.exit(1)

    mcp.run()
```

### HTTP Server (Minimal)

```python
# llm_council/http_server.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os

from llm_council import run_full_council

app = FastAPI(
    title="LLM Council",
    description="Local development server for LLM Council",
    version="1.0.0"
)

class CouncilRequest(BaseModel):
    prompt: str
    models: Optional[List[str]] = None
    # BYOK: API keys passed in request or read from environment
    api_key: Optional[str] = None

class CouncilResponse(BaseModel):
    stage1: List[dict]
    stage2: List[dict]
    stage3: dict
    metadata: dict

@app.post("/v1/council/run", response_model=CouncilResponse)
async def council_run(request: CouncilRequest):
    """Run the full council deliberation."""
    # Use provided key or fall back to environment
    api_key = request.api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(400, "API key required (pass in request or set OPENROUTER_API_KEY)")

    stage1, stage2, stage3, metadata = await run_full_council(
        request.prompt,
        models=request.models
    )

    return CouncilResponse(
        stage1=stage1,
        stage2=stage2,
        stage3=stage3,
        metadata=metadata
    )

@app.get("/health")
async def health():
    return {"status": "ok", "service": "llm-council-local"}
```

### API Protocol Specification

Both OSS and council-cloud implement this contract:

```yaml
# OpenAPI spec (simplified)
openapi: 3.0.0
info:
  title: LLM Council API
  version: v1
paths:
  /v1/council/run:
    post:
      summary: Run council deliberation
      requestBody:
        content:
          application/json:
            schema:
              type: object
              required: [prompt]
              properties:
                prompt:
                  type: string
                models:
                  type: array
                  items:
                    type: string
      responses:
        200:
          description: Council result
          content:
            application/json:
              schema:
                type: object
                properties:
                  stage1: array
                  stage2: array
                  stage3: object
                  metadata: object
```

### Developer Workflow ("The Switch")

```javascript
// Vercel AI SDK / LangChain integration
const council = new CouncilProvider({
  // Development: http://localhost:8000
  // Production: https://api.council.cloud
  baseUrl: process.env.COUNCIL_URL,
  apiKey: process.env.COUNCIL_API_KEY  // Optional in OSS, required in Cloud
});

const result = await council.run("What's the best approach?");
```

## Usage Examples

### Local Development
```bash
pip install "llm-council[http]"
export OPENROUTER_API_KEY=sk-...
llm-council serve
# Server running at http://localhost:8000
```

### Production (council-cloud)
```bash
# Just change the URL
export COUNCIL_URL=https://api.council.cloud
export COUNCIL_API_KEY=cc_...
```

### Integration Testing
```bash
curl -X POST http://localhost:8000/v1/council/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the best database for this use case?"}'
```

## Consequences

### Positive
- Enables JS/TS ecosystem integrations (Vercel AI SDK, LangChain)
- Clear, memorable boundary (stateless vs stateful)
- Canonical protocol for community plugins
- BYOK naturally enforced in OSS
- Seamless local → production migration

### Negative
- HTTP server adds maintenance surface
- Must resist scope creep (keep OSS stateless)
- Additional CLI complexity (serve vs default MCP)

### Risks
- Sophisticated self-hosters might extend OSS server
  - *Mitigation*: Cloud value is in the stateful layer (auth, caching, dashboards)
- Protocol divergence between OSS and Cloud
  - *Mitigation*: Publish OpenAPI spec, test compatibility in CI

## References

- [ADR-008: Package Structure](./ADR-008-package-structure.md)
- Similar patterns: Supabase (OSS + Cloud), Grafana, Redis
