# ADR-038: One-Click Deployment Strategy

| Field | Value |
|-------|-------|
| **Status** | Draft |
| **Date** | 2025-12-30 |
| **Author** | Chris (amiable-dev) |
| **Supersedes** | - |
| **Related ADRs** | ADR-037 (n8n Workflow Integration), ADR-009 (HTTP API Boundary) |
| **Council Review** | High Tier (4/4 models) - 2025-12-30 |

---

## Context

LLM Council's HTTP API (ADR-009) enables integration with workflow automation platforms, but current deployment requires manual setup: cloning the repository, configuring environment variables, installing dependencies, and running the server. This creates friction for potential users who want to quickly evaluate the council's capabilities.

### User Feedback Pattern

The most common barrier to adoption is **deployment complexity**:
- "How do I run this locally?" appears frequently in GitHub discussions
- n8n integration (ADR-037) assumes users already have a running council server
- No "try before you commit" experience exists

### Industry Standards

Modern open-source Python projects provide one-click deployment options:
- **FastAPI projects**: Railway, Render, Vercel templates are common
- **LLM tools**: Ollama, LocalAI, LiteLLM all provide Railway templates
- **Workflow tools**: n8n, Windmill provide deploy buttons

### Research Findings (December 2025)

Platform comparison based on real market data:

| Platform | Deploy Button | Free Tier | Template Marketplace | FastAPI Support | Cold Start |
|----------|---------------|-----------|---------------------|-----------------|------------|
| **Railway** | Official SVG | $5 trial (30d), $5/mo after | 1,800+ templates, 50% kickbacks | Official template | No spin-down |
| **Render** | Official SVG | 750 hrs/mo free | Blueprint system | Official docs | 15 min spin-down |
| **Fly.io** | CLI-only | 3 VMs free | Limited | Official docs | No spin-down |
| **Koyeb** | Official SVG | 512MB, 0.1 vCPU | Supported | Official template | 1 hour spin-down |
| **PythonAnywhere** | No button | Free tier | None | Manual setup | No spin-down |

**Key Insight**: Railway has paid ~$1M to template creators through their Open Source Kickback program, indicating strong investment in OSS ecosystem.

### Target Personas

| Persona | Need | Recommended Platform |
|---------|------|---------------------|
| **Evaluator** | Quick test, may abandon | Render Free (acceptable cold-start) |
| **Builder** | Integrating with n8n workflows | Railway (no cold-start required) |
| **Enterprise** | Self-hosted, compliance | Docker/manual (docs provided) |

**Primary Target**: Builders integrating with workflow automation (n8n, Make, Zapier). This drives the Railway-primary decision due to webhook reliability requirements.

---

## Decision

Implement a **two-tier deployment button strategy** targeting Railway (primary) and Render (secondary).

### Target Platforms

#### 1. Railway (Primary)
**Rationale:**
- Best developer experience with one-click deploy
- Template marketplace drives organic discovery (1,800+ templates, 2M+ developers)
- Revenue sharing (25-50% kickbacks) provides sustainability path
- No cold-start spin-down (important for webhook-based workflows like n8n)
- Official FastAPI template validates technical fit

#### 2. Render (Secondary)
**Rationale:**
- Most generous true free tier (750 hours/month)
- Well-established platform with Blueprint infrastructure-as-code
- Good fallback for cost-conscious users
- 15-minute spin-down acceptable for evaluation use cases

> **n8n Compatibility Warning**: Render Free tier spins down after 15 minutes of inactivity. Cold-start takes 30-60 seconds, which may cause n8n HTTP Request nodes to timeout. **For reliable n8n/webhook integration, use Railway or paid Render tier.**

#### Not Selected

**Fly.io**: No official deploy button; requires CLI knowledge which defeats "low friction" goal.

**Koyeb**: Smaller ecosystem and community; 1-hour spin-down problematic for webhook workflows.

**Heroku**: No free tier since November 2022; $5/mo minimum with no competitive advantage.

**Vercel/Netlify**: Serverless function timeout limits (10-60s) incompatible with multi-LLM deliberation which can take 30-90 seconds.

**DigitalOcean App Platform**: $5/mo minimum (no free tier for services); no significant advantage over Railway.

### Technical Requirements

Before implementing one-click deployment, the following must be verified:

| Requirement | Status | Notes |
|-------------|--------|-------|
| **Stateless Operation** | ✅ Required | No database needed; all state via client |
| **Memory Footprint** | ✅ Verified | < 512MB RAM (fits free tier limits) |
| **Health Endpoint** | ✅ `/health` | Returns `{"status": "ok"}` |
| **Port Binding** | ✅ `$PORT` | Binds to platform-provided port |
| **Startup Time** | ✅ < 30s | Fast cold-start for Render |

**Note**: LLM Council is stateless by design. Deliberation state is not persisted; each request is independent. No database or volume mounts required.

### Implementation Plan

#### Phase 1: Railway Template (Week 1)

1. **Create `railway.json` configuration:**
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "llm-council serve --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

2. **Create production Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install with HTTP support
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir ".[http]"

# Non-root user for security
RUN useradd --create-home appuser
USER appuser

ENV PORT=8000
EXPOSE $PORT

CMD ["llm-council", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

3. **Create template repository structure:**
```
llm-council-railway/
├── railway.json
├── Dockerfile
├── .env.example
└── README.md (with usage instructions)
```

4. **Add deploy button to README.md:**
```markdown
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/XXX?referralCode=amiable-dev)
```

5. **Submit to Railway Template Marketplace**

#### Phase 2: Render Blueprint (Week 2)

1. **Create `render.yaml` Blueprint:**
```yaml
services:
  - type: web
    name: llm-council
    runtime: python
    buildCommand: pip install ".[http]"
    startCommand: llm-council serve --host 0.0.0.0 --port $PORT
    envVars:
      - key: OPENROUTER_API_KEY
        sync: false
      - key: LLM_COUNCIL_TIER
        value: balanced
    healthCheckPath: /health
    autoDeploy: false  # Important: prevent cascading deploys
```

2. **Add deploy button to README.md:**
```markdown
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/amiable-dev/llm-council)
```

#### Phase 3: Documentation (Week 3)

1. **Create `docs/deployment/` section:**
   - `docs/deployment/index.md` - Overview of deployment options
   - `docs/deployment/railway.md` - Railway-specific guide
   - `docs/deployment/render.md` - Render-specific guide
   - `docs/deployment/manual.md` - Manual deployment guide

2. **Update `README.md` with deployment section:**
```markdown
## Quick Deploy

Deploy your own LLM Council instance in one click:

| Platform | Deploy | Free Tier |
|----------|--------|-----------|
| Railway | [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/XXX) | $5/month |
| Render | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=...) | 750 hrs/mo |

### Manual Setup

See [deployment guide](https://llm-council.dev/deployment/) for manual setup instructions.
```

3. **Update mkdocs.yml navigation:**
```yaml
nav:
  - Deployment:
    - Overview: deployment/index.md
    - Railway: deployment/railway.md
    - Render: deployment/render.md
    - Manual Setup: deployment/manual.md
```

#### Phase 4: n8n Integration Validation (Week 4)

With deployed instances:
1. Validate ADR-037 workflows against Railway deployment
2. Create Railway+n8n combined template (optional)
3. Update n8n integration docs with Railway endpoint examples

### Environment Variables

Both platforms require these environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | **Yes** | OpenRouter API key (outgoing calls) |
| `LLM_COUNCIL_API_TOKEN` | **Yes** | Bearer token for API authentication (incoming calls) |
| `LLM_COUNCIL_TIER` | No | Default tier (quick/balanced/high) |
| `LLM_COUNCIL_MODELS` | No | Override default models |
| `LLM_COUNCIL_WEBHOOK_SECRET` | No | HMAC secret for n8n webhooks |

### Security Requirements (Critical)

> **Council Review Finding**: The original draft lacked incoming request authentication. Without it, deployed endpoints are publicly accessible and malicious actors could drain users' OpenRouter credits.

#### Required Security Controls

| Control | Implementation | Status |
|---------|----------------|--------|
| **API Authentication** | `LLM_COUNCIL_API_TOKEN` env var; reject requests without valid `Authorization: Bearer <token>` | **Required** |
| **Outgoing Key Protection** | `OPENROUTER_API_KEY` via platform secrets (never in repo) | **Required** |
| **TLS Encryption** | Platform-provided; no HTTP endpoints | **Required** |
| **Rate Limiting** | Platform-level or application-level (configurable) | Recommended |
| **Request Size Limits** | Max body size to prevent resource exhaustion | Recommended |
| **Logging Sanitization** | Redact prompts/responses in logs by default | Recommended |

#### First-Run Error Handling

Templates must handle invalid/missing credentials gracefully:
- **Missing `OPENROUTER_API_KEY`**: Server starts but returns clear error on first request
- **Invalid `OPENROUTER_API_KEY`**: Returns 401 with descriptive message
- **Missing `LLM_COUNCIL_API_TOKEN`**: Server refuses to start (fail-safe)

### Cost Projections

For typical evaluation usage (10 council queries/day):

| Platform | Estimated Monthly Cost | Notes |
|----------|----------------------|-------|
| Railway Hobby | $5 (included) | Plenty of capacity |
| Render Free | $0 | May hit 750-hour limit with heavy use |
| Production (Railway Pro) | ~$20-50 | Based on actual CPU/memory usage |

### Success Metrics

1. **Adoption**: Track template deployments via Railway analytics
2. **Retention**: Monitor active instances after 30 days
3. **Conversion**: Track progression from free tier to paid
4. **Community**: Template marketplace rating and reviews

---

## Consequences

### Positive

1. **Reduced Time-to-Value**: Users can evaluate LLM Council in < 5 minutes
2. **Organic Discovery**: Railway marketplace exposes project to 2M+ developers
3. **Revenue Potential**: Template kickbacks provide sustainability path
4. **Documentation Improvement**: Forces clear documentation of deployment requirements
5. **n8n Validation**: Enables real-world testing of ADR-037 workflows

### Negative

1. **Maintenance Overhead**: Two platforms to maintain and test
2. **Version Sync**: Deploy button URLs must stay synchronized with releases
3. **Platform Risk**: Dependency on third-party platform stability
4. **Support Burden**: More users may mean more support requests

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Platform pricing changes** | Medium | High | Document self-hosted fallback prominently |
| **Template/blueprint drift** | High | Medium | CI job validates configs build on every PR |
| **Railway marketplace rejection** | Low | High | Review requirements before submission |
| **API key exposure in logs** | Medium | High | Logging sanitization by default |
| **Abuse via public endpoint** | High | High | **Require** `LLM_COUNCIL_API_TOKEN` auth |
| **Invalid API key on first run** | High | Medium | Graceful error messages, startup validation |
| **Version sync issues** | Medium | Medium | Pin templates to tagged releases, not `main` |
| **Support burden increase** | Medium | Low | FAQ, troubleshooting docs, GitHub Discussions |

### Template Lifecycle Management

To prevent template drift and ensure reliability:

```yaml
# .github/workflows/validate-templates.yml
name: Validate Deploy Templates
on:
  push:
    paths:
      - 'deploy/**'
      - 'railway.json'
      - 'render.yaml'
  release:
    types: [published]

jobs:
  validate-railway:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate railway.json syntax
        run: jq . railway.json
      - name: Build Docker image
        run: docker build -t llm-council-test .
      - name: Test health endpoint
        run: |
          docker run -d -p 8000:8000 --env-file .env.test llm-council-test
          sleep 10
          curl -f http://localhost:8000/health
```

**Release Process**:
1. Templates pinned to specific git tags (not `main` branch)
2. CI validates templates build successfully on every release
3. Template URLs updated in README after successful marketplace submission

---

## Alternatives Considered

### 1. Docker Compose (Complementary, Not Rejected)
**Description:** Provide `docker-compose.yml` for local one-command deployment.

**Status: Accepted as Complementary Path**
- Many n8n users self-host via Docker; this is a natural fit
- Supports "try locally before cloud deploy" workflow
- Added to Phase 3 documentation scope

```yaml
# docker-compose.yml (simplified)
services:
  llm-council:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - LLM_COUNCIL_API_TOKEN=${LLM_COUNCIL_API_TOKEN}
```

### 2. Docker Hub Only
**Description:** Publish official Docker images without platform-specific templates.

**Rejected because:**
- Still requires users to provision hosting
- No one-click experience
- Doesn't solve discovery problem

### 3. Single Platform (Railway Only)
**Description:** Focus exclusively on Railway.

**Rejected because:**
- Render's free tier is significantly more generous
- Platform diversity reduces vendor lock-in risk
- Different users have different platform preferences

### 4. All Major Platforms
**Description:** Support Railway, Render, Fly.io, Koyeb, Heroku, etc.

**Rejected because:**
- Maintenance burden too high
- Fly.io lacks deploy button
- Koyeb has smaller ecosystem
- Heroku has no free tier
- Diminishing returns after top 2 platforms

### 5. Self-Hosted Only
**Description:** Focus on documentation for self-hosted deployment only.

**Rejected because:**
- Defeats goal of reducing friction
- Misses marketplace discovery opportunity
- Users who want self-hosted can still use manual setup

---

## Implementation Checklist

### Phase 1: Railway Template
- [ ] Create `deploy/railway/` directory with Dockerfile and railway.json
- [ ] Test deployment locally with Railway CLI
- [ ] Submit template to Railway marketplace
- [ ] Add deploy button to README.md

### Phase 2: Render Blueprint
- [ ] Create `render.yaml` in repository root
- [ ] Test deployment via Render dashboard
- [ ] Add deploy button to README.md

### Phase 3: Documentation
- [ ] Create `docs/deployment/` directory
- [ ] Write platform-specific guides
- [ ] Create `docker-compose.yml` for local deployment
- [ ] Update mkdocs.yml navigation
- [ ] Update main README.md with deployment section

### Phase 4: Integration
- [ ] Validate ADR-037 n8n workflows with Railway deployment
- [ ] Update n8n integration docs with deployed endpoint examples
- [ ] Create integration test suite for deployed instances

---

## References

### Research Sources
- [Railway Template Marketplace](https://railway.app/templates)
- [Railway Open Source Kickback Program](https://blog.railway.com/p/1M-open-source-kickbacks) - $1M paid to creators
- [Render Deploy to Render Button](https://render.com/docs/deploy-to-render)
- [Render Free Tier Documentation](https://render.com/docs/free)
- [Cloud Deploy Buttons Collection](https://github.com/cloudcommunity/Cloud-Deploy-Buttons)
- [Railway vs Render Comparison (Northflank)](https://northflank.com/blog/railway-vs-render)
- [Top Heroku Alternatives 2025](https://northflank.com/blog/top-heroku-alternatives)

### Related Projects Using This Pattern
- [LocalAI Railway Template](https://railway.com/deploy/localai)
- [Authorizer Railway Template](https://github.com/authorizerdev/authorizer-railway)
- [LibreChat Railway Deployment](https://www.librechat.ai/docs/remote/railway)
- [Vendure Railway Deployment](https://docs.vendure.io/guides/deployment/deploy-to-railway/)

---

## Council Review Summary

**Review Date**: 2025-12-30
**Tier**: High (4/4 models responded)
**Verdict**: Conditionally Approved with Critical Revisions

### Key Findings Incorporated

| Finding | Source | Resolution |
|---------|--------|------------|
| **Missing API authentication** | Gemini, GPT-5.2 | Added `LLM_COUNCIL_API_TOKEN` requirement |
| **Render cold-start breaks n8n** | All models | Added explicit warning in Render section |
| **Resource sizing unverified** | Gemini, Claude | Added Technical Requirements table |
| **Template drift risk** | All models | Added CI validation workflow |
| **First-run error handling** | Claude | Added error handling requirements |
| **Docker Compose option** | GPT-5.2 | Added as complementary path |
| **Missing Vercel/DO rejection** | Claude | Added to Not Selected section |
| **Target persona unclear** | Claude | Added Target Personas section |

### Models Contributing
- `x-ai/grok-4.1-fast` - Approved with minor revisions
- `google/gemini-3-pro-preview` - Approved with modifications (security)
- `anthropic/claude-opus-4.5` - Approved with revisions
- `openai/gpt-5.2` - Conditional approval (security controls required)
