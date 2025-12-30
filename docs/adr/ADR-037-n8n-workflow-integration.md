# ADR-037: n8n Workflow Automation Integration

**Status:** DRAFT
**Date:** 2025-12-30
**Context:** Enabling LLM Council as an "agent jury" in workflow automation
**Depends On:** ADR-009 (HTTP API), ADR-025 (Future Integration Capabilities)
**Author:** @amiable-dev
**Council Review:** 2025-12-30 (High Tier, 4/4 models)

## Context

LLM Council's HTTP API enables integration with workflow automation platforms. Among these, n8n stands out as a popular open-source alternative to Zapier with strong LLM integration capabilities and a visual workflow editor.

### Problem Statement

Engineers building automation workflows face a fundamental limitation: single-model AI decisions are binary and prone to hallucination. When automating high-stakes decisions (code reviews, support triage, design approvals), teams need:

1. **Consensus-based decisions** - Multiple perspectives reduce single-model bias
2. **Confidence signals** - Understanding when the AI is uncertain
3. **Auditability** - Transparent reasoning for compliance and debugging
4. **Flexibility** - Both binary (go/no-go) and synthesized (detailed analysis) outputs

### n8n Platform Analysis

**Why n8n as the first integration target:**

| Factor | n8n | Zapier | Make |
|--------|-----|--------|------|
| Open Source | Yes (Fair-code) | No | No |
| Self-hosted | Yes | No | No |
| LLM Integration | Native AI nodes | Add-ons | Add-ons |
| HTTP Flexibility | Full control | Limited | Limited |
| Community Templates | 7600+ | Larger | Medium |
| Target Audience | Engineers/DevOps | Business users | Mixed |

n8n's engineer-focused design, HTTP Request node flexibility, and self-hosting capability align with LLM Council's technical audience.

### Current State (Pre-ADR)

**ADR-025 identified n8n as P2 priority:**
> "Create n8n integration example/template"

**HTTP API availability (ADR-009):**
- `POST /v1/council/run` - Synchronous deliberation
- `GET /v1/council/stream` - SSE streaming
- `GET /v1/health` - Health check

**Gap:** No documented patterns, example workflows, or security guidance for n8n integration.

## Decision

Implement comprehensive n8n integration with three workflow templates, security patterns, and documentation targeting engineer audiences.

### 1. Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     n8n Workflow                            │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐    ┌───────────────┐    ┌─────────────────┐  │
│  │ Trigger  │───▶│ HTTP Request  │───▶│ Parse Response  │  │
│  │ (Webhook)│    │ POST /v1/     │    │ (Set Node)      │  │
│  └──────────┘    │ council/run   │    └────────┬────────┘  │
│                  └───────────────┘             │            │
│                                                ▼            │
│                                    ┌───────────────────┐   │
│                                    │ Conditional Logic │   │
│                                    │ (IF verdict=...)  │   │
│                                    └─────────┬─────────┘   │
│                                              │              │
│                              ┌───────────────┼───────────┐ │
│                              ▼               ▼           ▼ │
│                        ┌─────────┐    ┌─────────┐  ┌──────┐│
│                        │ Approve │    │ Reject  │  │ Flag ││
│                        │ Action  │    │ Action  │  │Human ││
│                        └─────────┘    └─────────┘  └──────┘│
└─────────────────────────────────────────────────────────────┘
```

### 2. API Contract

#### Request Schema

```json
{
  "prompt": "Review this code for security issues:\n{{ $json.diff }}",
  "verdict_type": "synthesis | binary | tie_breaker",
  "confidence": "quick | balanced | high",
  "include_dissent": false,
  "metadata": {
    "correlation_id": "{{ $execution.id }}",
    "workflow_id": "code-review-v1",
    "idempotency_key": "{{ $json.event_id }}"
  }
}
```

#### Response Schema

```json
{
  "request_id": "council_abc123",
  "stage1": [
    {"model": "gpt-4", "content": "...", "tokens": 450}
  ],
  "stage2": [
    {"reviewer": "claude-3", "rankings": [...], "rationale": "..."}
  ],
  "stage3": {
    "synthesis": "The council identified three concerns...",
    "verdict": "approved | rejected",
    "confidence": 0.85,
    "dissent": [{"model": "gemini-pro", "opinion": "..."}]
  },
  "metadata": {
    "correlation_id": "exec_xyz789",
    "models_consulted": ["gpt-4", "claude-3", "gemini-pro"],
    "aggregate_rankings": {"Response A": 1.5, "Response B": 2.3},
    "timing": {
      "total_ms": 18500,
      "stage1_ms": 8200,
      "stage2_ms": 7100,
      "stage3_ms": 3200
    },
    "token_usage": {
      "input": 2400,
      "output": 1850,
      "total": 4250
    }
  }
}
```

#### Error Response Schema

```json
{
  "error": {
    "code": "COUNCIL_TIMEOUT | RATE_LIMITED | PARTIAL_FAILURE | VALIDATION_ERROR",
    "message": "Human-readable error description",
    "details": {
      "models_succeeded": ["gpt-4"],
      "models_failed": ["claude-3", "gemini-pro"],
      "retry_after_seconds": 30
    }
  }
}
```

### 3. Verdict Types for Automation

| Verdict Type | Use Case | Response Structure | Confidence Interpretation |
|--------------|----------|-------------------|---------------------------|
| `synthesis` | Detailed analysis (code review, design feedback) | `stage3.synthesis` (string) | Agreement level among models |
| `binary` | Go/no-go gates (triage, approval) | `stage3.verdict` (approved/rejected), `confidence` (0-1) | Proportion of models agreeing |
| `tie_breaker` | Deadlocked decisions | Chairman resolves split votes | N/A (chairman decides) |

**Confidence Score Semantics:**
- `0.0-0.5`: Strong disagreement, recommend human review
- `0.5-0.7`: Mixed consensus, proceed with caution
- `0.7-0.9`: Moderate agreement, generally reliable
- `0.9-1.0`: Strong consensus, high reliability

### 4. Workflow Templates

#### 4.1 Code Review Automation
- **Trigger:** GitHub PR webhook
- **Verdict:** `synthesis`
- **Output:** Detailed security, performance, and style analysis
- **Action:** Post review comment to PR

#### 4.2 Support Ticket Triage
- **Trigger:** Ticket creation webhook
- **Verdict:** `binary`
- **Output:** `approved` (URGENT) or `rejected` (STANDARD)
- **Action:** Route to appropriate queue based on verdict + confidence

#### 4.3 Technical Design Decision
- **Trigger:** Design doc submission
- **Verdict:** `synthesis` with `include_dissent: true`
- **Output:** Council recommendation + minority opinions
- **Action:** Send to Slack/email for human review

### 5. Security Model

#### 5.1 Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                    UNTRUSTED ZONE                               │
│  ┌─────────────┐                                                │
│  │ GitHub/Jira │──webhook──┐                                    │
│  │ (PR, Ticket)│           │                                    │
│  └─────────────┘           │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    n8n WORKFLOW (SEMI-TRUSTED)                  │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────────┐ │
│  │ Validate │───▶│ Sanitize     │───▶│ Call LLM Council      │ │
│  │ Webhook  │    │ Input        │    │ (API Key + TLS)       │ │
│  └──────────┘    └──────────────┘    └───────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
                             │
                             ▼ HTTPS + API Key
┌────────────────────────────────────────────────────────────────┐
│                    LLM COUNCIL API (TRUSTED)                   │
│  - Input validation                                            │
│  - Rate limiting                                               │
│  - Audit logging                                               │
└────────────────────────────────────────────────────────────────┘
```

#### 5.2 Authentication (Outbound to LLM Council)

**API Key Authentication:**
```javascript
// n8n HTTP Request node - Header Auth
{
  "headerAuth": {
    "name": "Authorization",
    "value": "Bearer {{ $credentials.llmCouncilApiKey }}"
  }
}
```

**Credential Storage Requirements:**
- Store API keys in **n8n Credential Objects** (encrypted at rest)
- Never hardcode in workflow JSON
- Use environment-specific credentials (dev/staging/prod)
- Rotate keys quarterly or on suspected compromise

#### 5.3 HMAC Signature Verification (Inbound Webhooks)

For webhook callbacks from LLM Council:

```javascript
// n8n Function node - HMAC verification
const crypto = require('crypto');

const payload = JSON.stringify($input.first().json);
const secret = $credentials.llmCouncilWebhookSecret;
const receivedSig = $input.first().headers['x-council-signature'];
const receivedNonce = $input.first().headers['x-council-nonce'];
const receivedTimestamp = parseInt($input.first().headers['x-council-timestamp']);

// 1. Timestamp validation (±5 minutes)
const now = Math.floor(Date.now() / 1000);
if (Math.abs(now - receivedTimestamp) > 300) {
  throw new Error('Timestamp too old or in future');
}

// 2. Nonce replay protection (requires external store)
// Store nonces in Redis/DB with TTL matching timestamp window
const nonceKey = `nonce:${receivedNonce}`;
if (await $env.cache.exists(nonceKey)) {
  throw new Error('Nonce already used - replay attack detected');
}
await $env.cache.set(nonceKey, '1', { EX: 600 }); // 10 min TTL

// 3. HMAC verification with timing-safe comparison
const expectedSig = 'sha256=' + crypto
  .createHmac('sha256', secret)
  .update(`${receivedTimestamp}.${receivedNonce}.${payload}`)
  .digest('hex');

if (!crypto.timingSafeEqual(
  Buffer.from(expectedSig),
  Buffer.from(receivedSig)
)) {
  throw new Error('Invalid signature');
}

return $input.first();
```

#### 5.4 Input Validation & Prompt Injection Mitigation

**Input Sanitization:**
```javascript
// n8n Function node - Input sanitization
const input = $input.first().json;

// 1. Size limits
const MAX_DIFF_SIZE = 50000; // 50KB
const diff = input.diff?.substring(0, MAX_DIFF_SIZE) || '';

// 2. Remove potential prompt injection patterns
const sanitized = diff
  .replace(/```system/gi, '```code')  // Prevent system prompt injection
  .replace(/\[INST\]/gi, '[CODE]')    // Prevent instruction injection
  .replace(/<<SYS>>/gi, '<<CODE>>');  // Prevent Llama-style injection

// 3. Escape special characters in structured fields
const safeSubject = input.subject?.replace(/[<>]/g, '') || '';

return {
  json: {
    diff: sanitized,
    subject: safeSubject,
    // Preserve original for audit
    _original_size: input.diff?.length || 0,
    _was_truncated: (input.diff?.length || 0) > MAX_DIFF_SIZE
  }
};
```

**LLM Council Server-Side Protections:**
- Input length validation (reject oversized payloads)
- Rate limiting per API key
- Audit logging of all requests
- System prompt isolation from user content

#### 5.5 Secret Rotation Strategy

| Secret | Rotation Frequency | Procedure |
|--------|-------------------|-----------|
| API Key | 90 days or on compromise | Generate new key → update n8n credential → revoke old key |
| Webhook Secret | 90 days | Support dual secrets during rotation window |
| TLS Certificates | Auto-renew (Let's Encrypt) | Managed by reverse proxy |

### 6. Performance Configuration

| Confidence Tier | Models | Typical Latency | Timeout Setting | Est. Cost/Call |
|-----------------|--------|-----------------|-----------------|----------------|
| `quick` | 2 | 5-10s | 60000ms | ~$0.02 |
| `balanced` | 3 | 10-20s | 90000ms | ~$0.04 |
| `high` | 4 | 20-40s | 120000ms | ~$0.08 |

**Cost Estimation Formula:**
```
cost ≈ (input_tokens × $0.003 + output_tokens × $0.015) × num_models
```
*Assumes GPT-4 class models. Actual cost varies by model mix.*

**HTTP Request Node Settings:**
```json
{
  "options": {
    "timeout": 120000,
    "retry": {
      "maxRetries": 3,
      "retryOn": [429, 500, 502, 503, 504],
      "retryDelay": 5000
    }
  }
}
```

### 7. Partial Failure Handling

**Scenario:** 2 of 3 models respond successfully.

| Policy | Behavior | Use Case |
|--------|----------|----------|
| `require_all` | Fail entire request | High-stakes decisions |
| `require_majority` | Proceed with 2/3 | Default behavior |
| `best_effort` | Proceed with any response | Low-stakes, speed-critical |

**Default Behavior (require_majority):**
- If ≥ 50% of models respond, proceed with available responses
- Flag partial failure in response metadata
- Include `models_failed` array for debugging

### 8. Error Handling Strategy

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Council   │────▶│  IF Error?   │────▶│ Retry w/ Backoff│
│   Request   │     └──────┬───────┘     └────────┬────────┘
└─────────────┘            │                      │
                           │                      ▼
                    ┌──────┴──────┐        ┌─────────────┐
                    │ Process     │        │ Error Type? │
                    │ Success     │        └──────┬──────┘
                    └─────────────┘               │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                              ┌──────────┐ ┌──────────┐ ┌──────────┐
                              │ 429: Wait│ │ 5xx:     │ │ Timeout: │
                              │ & Retry  │ │ Fallback │ │ Human    │
                              └──────────┘ └──────────┘ └──────────┘
```

**n8n Implementation:**
```javascript
// Error handling with n8n Error Trigger
{
  "nodes": [
    {
      "name": "Council Request",
      "type": "n8n-nodes-base.httpRequest",
      "continueOnFail": true  // Don't stop workflow on error
    },
    {
      "name": "Check Error",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "string": [{
            "value1": "={{ $json.error?.code }}",
            "operation": "isNotEmpty"
          }]
        }
      }
    },
    {
      "name": "Handle 429",
      "type": "n8n-nodes-base.wait",
      "parameters": {
        "amount": "={{ $json.error?.details?.retry_after_seconds || 30 }}"
      }
    }
  ]
}
```

**Fallback Chain:**
1. **Retry** (3x with exponential backoff) - For transient errors
2. **Degrade** (single model) - For persistent council failures (configurable per workflow)
3. **Human escalation** - For critical decisions, never auto-approve

**Policy Configuration (per workflow):**
```javascript
const FALLBACK_POLICY = {
  "code-review": {
    allow_single_model_fallback: true,  // Code review can degrade
    human_escalation_threshold: 0.5     // Escalate if confidence < 0.5
  },
  "security-approval": {
    allow_single_model_fallback: false, // Security requires council
    human_escalation_threshold: 0.8     // Higher bar for auto-approve
  }
};
```

### 9. Observability & Debugging

#### 9.1 Correlation ID Propagation

```javascript
// Pass correlation ID through entire workflow
const correlationId = $json.correlation_id || `n8n_${$execution.id}`;

// Include in LLM Council request
{
  "metadata": {
    "correlation_id": correlationId,
    "n8n_execution_id": $execution.id,
    "n8n_workflow_id": $workflow.id
  }
}

// Log for tracing
console.log(`[${correlationId}] Council request initiated`);
```

#### 9.2 Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `council_latency_p95` | 95th percentile response time | > 60s |
| `council_error_rate` | Percentage of failed requests | > 5% |
| `council_consensus_rate` | Requests with confidence > 0.7 | < 80% |
| `council_fallback_rate` | Requests using single-model fallback | > 10% |

#### 9.3 Troubleshooting Guide

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `COUNCIL_TIMEOUT` | High tier + large input | Reduce tier or truncate input |
| `RATE_LIMITED` (429) | Too many concurrent requests | Implement request queueing |
| `PARTIAL_FAILURE` | Model API issues | Check `models_failed`, retry later |
| Inconsistent verdicts | Ambiguous prompt | Improve prompt specificity |
| Low confidence scores | Models disagree | Review dissent, consider human review |
| HMAC validation failed | Clock drift or secret mismatch | Sync NTP, verify secret |

### 10. Versioning Strategy

**API Versioning:**
- Templates target LLM Council API v1 (`/v1/council/*`)
- v1 will remain supported for 18 months after v2 GA
- Breaking changes require major version bump
- Additive changes (new fields) are non-breaking

**Template Versioning:**
```json
{
  "name": "LLM Council - Code Review",
  "meta": {
    "llm_council_template_version": "1.0.0",
    "llm_council_api_version": "v1",
    "n8n_min_version": "1.20.0"
  }
}
```

**Compatibility Matrix:**

| Template Version | API Version | n8n Version |
|------------------|-------------|-------------|
| 1.0.x | v1 | ≥1.20.0 |
| 2.0.x (future) | v1, v2 | ≥1.30.0 |

## Consequences

### Positive

1. **Lower integration barrier** - Engineers can import ready-to-use templates
2. **Best practices encoded** - Security patterns (HMAC, input validation) built into examples
3. **Discoverability** - n8n Creator Hub expands reach to automation engineers
4. **Reference architecture** - Patterns applicable to other platforms (Make, Zapier)

### Negative

1. **Maintenance burden** - Templates need updates when API changes
2. **Version coupling** - n8n workflow format may evolve
3. **Limited scope** - Only covers HTTP integration, not MCP
4. **Sync limitations** - Long deliberations may exceed timeouts

### Trade-offs

| Choice | Alternative | Rationale |
|--------|-------------|-----------|
| n8n first | Zapier, Make | Open source, engineer audience, self-hosted |
| HTTP API | MCP Server | HTTP is universal, n8n lacks MCP support |
| 3 templates | More use cases | Quality over quantity; community can extend |
| Sync-first | Async-first | Simpler to document; covers 95% of use cases |
| HTTP Request node | Custom n8n node | Faster to ship; custom node for future roadmap |

**Deferred: Async Webhook Callbacks**
- **Why not now:** Adds complexity (callback URL registration, delivery guarantees, state management)
- **When to revisit:** If users report timeout failures > 5% of calls

## Implementation

### Files Created

| File | Purpose |
|------|---------|
| `docs/integrations/index.md` | Integration landing page |
| `docs/integrations/n8n.md` | Comprehensive n8n guide |
| `docs/examples/n8n/code-review-workflow.json` | PR review template |
| `docs/examples/n8n/support-triage-workflow.json` | Triage template |
| `docs/examples/n8n/design-decision-workflow.json` | Design review template |
| `docs/blog/08-n8n-workflow-automation.md` | Blog post |
| `tests/test_n8n_examples.py` | TDD test suite (28 tests) |

### Files Modified

| File | Change |
|------|--------|
| `mkdocs.yml` | Added Integrations section, blog entry |

### Future Work

1. **Async webhook callbacks** - When timeout failures exceed 5%
2. **Custom n8n node** - Better UX, typed fields, versioned behavior
3. **n8n Creator Hub** - Submit templates for official listing
4. **Additional platforms** - Make, Zapier adapters
5. **MCP integration** - When n8n adds MCP support

## Validation

### Acceptance Criteria

- [x] All workflow JSON files are valid and importable
- [x] Documentation covers security (HMAC, auth, input validation)
- [x] Documentation covers timeouts and error handling
- [x] Blog post reviewed by LLM Council for engineer audience
- [x] 28 TDD tests pass
- [x] mkdocs builds without warnings

### Test Results

```
tests/test_n8n_examples.py::TestN8nWorkflowExamples - 19 passed
tests/test_n8n_examples.py::TestIntegrationDocs - 5 passed
tests/test_n8n_examples.py::TestBlogPost - 4 passed
Total: 28 passed
```

## References

### Related ADRs
- [ADR-009: HTTP API Open Core Boundary](ADR-009-http-api-open-core-boundary.md)
- [ADR-025: Future Integration Capabilities](ADR-025-future-integration-capabilities.md)
- [ADR-038: One-Click Deployment Strategy](ADR-038-one-click-deployment-strategy.md) - Enables easy deployment for n8n integration

### External Resources
- [n8n HTTP Request Node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/)
- [n8n Community Templates](https://n8n.io/workflows/)
- [n8n LLM Agents Guide](https://blog.n8n.io/llm-agents/)
- [OWASP API Security Top 10](https://owasp.org/API-Security/)

## Appendix A: Prompt Engineering Patterns

### Code Review Prompt

```
You are a code review expert. Review this code change for:
1. Security vulnerabilities (injection, XSS, etc.)
2. Performance issues
3. Code style and best practices
4. Potential bugs

Diff:
{{ $json.diff }}

Provide specific, actionable feedback with line references.
```

### Triage Prompt

```
Should this ticket be escalated to URGENT priority?

Criteria for URGENT:
- Production system down
- Data loss or corruption
- Security incident
- Multiple users affected

Ticket Subject: {{ $json.subject }}
Ticket Body: {{ $json.body }}

Respond approved (URGENT) or rejected (STANDARD).
```

### Design Review Prompt

```
As a council of senior architects, evaluate this design:

{{ $json.design_doc }}

Consider: Scalability, Maintainability, Security, Cost, Complexity.

Provide:
- Recommendation (proceed/revise/reject)
- Critical concerns
- Suggested improvements
```

## Appendix B: Council Review Summary

**Review Date:** 2025-12-30
**Tier:** High (4 models)
**Models:** grok-4.1-fast, gemini-3-pro-preview, gpt-5.2, claude-opus-4.5

### Key Feedback Incorporated

1. **API Schemas** - Added complete request/response/error schemas (Section 2)
2. **Security Depth** - Expanded to include authentication, input validation, prompt injection mitigation, nonce-based replay protection, secret rotation (Section 5)
3. **Partial Failure Semantics** - Documented require_all/require_majority/best_effort policies (Section 7)
4. **Error Handling** - Added n8n-specific implementation patterns (Section 8)
5. **Observability** - Added correlation ID propagation, metrics, troubleshooting guide (Section 9)
6. **Versioning** - Added API and template versioning strategy (Section 10)
7. **Cost Estimation** - Added per-tier cost estimates and formula (Section 6)
8. **Async Trade-off** - Documented why sync-first, when to revisit (Trade-offs section)

### Deferred Recommendations

- Custom n8n node (prioritized for future roadmap)
- Extension points for custom verdict types (future work)
- mTLS for enterprise deployments (not yet required)
