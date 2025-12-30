# LLM Council as an Agent Jury: n8n Workflow Automation

**What if every PR got reviewed by four AI experts before you even saw it? Or support tickets automatically triaged by a council that never sleeps?**

---

Automation workflows are binary by nature: IF this THEN that. But real decisions are nuanced. Should this PR be approved? Is this ticket urgent? Is this design scalable? Single-model AI can answer these questions, but a council of models—deliberating and reaching consensus—provides more reliable answers.

This post shows how to integrate LLM Council with n8n to build AI-powered automation that thinks before it acts.

## The Problem with Single-Model Automation

Consider a typical automation: "When a PR is opened, ask GPT-4 to review it."

```javascript
// Simple but fragile
const review = await gpt4.chat("Review this code: " + diff);
postComment(review);
```

Problems:
1. **Single point of failure**: If GPT-4 hallucinates, you get a hallucinated review
2. **No confidence signal**: How do you know if the model is guessing?
3. **Model bias**: Each model has blind spots

What you actually want is a *deliberation*—multiple models reviewing the code, critiquing each other's findings, and reaching consensus.

## The Council Pattern for Automation

LLM Council provides exactly this. Here's what happens under the hood:

```
Your automation → POST /v1/council/run →
  Stage 1: 4 models generate responses in parallel
  Stage 2: Each model ranks the others (anonymized)
  Stage 3: Chairman model synthesizes consensus
← Final answer with confidence metrics
```

**What's the Chairman?** A designated model (configurable, defaults to Claude) that reviews all Stage 1 responses and Stage 2 rankings, then produces the final synthesis. It doesn't participate in peer review—it acts as a neutral arbiter.

**Model selection**: By default, the council uses a balanced mix (GPT-4, Claude, Gemini, etc.). You can configure specific models via `llm_council.yaml` or environment variables. See the [Configuration Guide](../getting-started/configuration.md) for details.

For automation workflows, this means:

| Mode | Use Case | Output |
|------|----------|--------|
| `synthesis` | Code review, design feedback | Detailed analysis |
| `binary` | Go/no-go gates, triage | `approved` / `rejected` + confidence |
| `tie_breaker` | Deadlocked decisions | Chairman breaks the tie |

## n8n Integration Architecture

n8n calls LLM Council via HTTP Request node:

```
[Trigger] → [HTTP Request to Council] → [Parse Response] → [Conditional Action]
```

### Prerequisites

LLM Council is open source and self-hosted. You'll need:

1. **Deploy the council server** (one-click or manual):

   **Option A: One-click deploy** (recommended):

   [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/github)

   **Option B: Local/manual:**
   ```bash
   pip install "llm-council-core[http]"
   export OPENROUTER_API_KEY="sk-or-v1-..."
   export LLM_COUNCIL_API_TOKEN=$(openssl rand -hex 16)
   llm-council serve --host 0.0.0.0 --port 8000
   ```

2. **Configure n8n environment variables**:
   - `LLM_COUNCIL_URL`: Your council server URL (e.g., `https://your-app.railway.app`)
   - `LLM_COUNCIL_TOKEN`: Your API token for authentication

### Basic Workflow Pattern

```javascript
// n8n HTTP Request node configuration
{
  "method": "POST",
  "url": "{{ $env.LLM_COUNCIL_URL }}/v1/council/run",
  "headers": {
    "Authorization": "Bearer {{ $env.LLM_COUNCIL_TOKEN }}",
    "Content-Type": "application/json"
  },
  "body": {
    "prompt": "Review this code for security issues:\n{{ $json.diff }}",
    "verdict_type": "synthesis"
  },
  "options": {
    "timeout": 120000  // 2 minutes - council deliberation takes time
  }
}
```

!!! warning "Authentication Required"
    All council endpoints (except `/health`) require Bearer token authentication. Store your token in n8n credentials or environment variables—never hardcode it in workflows.

**Note on timeouts**: Council deliberation involves multiple LLM calls. Set the HTTP Request node timeout to at least 60-120 seconds to avoid premature failures.

The council returns:

```json
{
  "stage1": [/* individual model responses */],
  "stage2": [/* peer evaluations */],
  "stage3": {
    "synthesis": "The council identified three concerns: 1) SQL injection risk in line 42..."
  },
  "metadata": {
    "aggregate_rankings": {"Response A": 1.5, "Response C": 2.0, ...}
  }
}
```

## Real-World Use Cases

### 1. Code Review Automation

**Trigger**: GitHub webhook (PR opened)
**Council**: Synthesis mode for detailed feedback
**Action**: Post review comment to PR

```javascript
// Prompt engineering for code review
{
  "prompt": `You are a code review expert. Review this change for:
1. Security vulnerabilities (injection, XSS, etc.)
2. Performance issues
3. Code style violations
4. Potential bugs

Diff:
${$json.diff}

Provide specific, actionable feedback with line references.`,
  "verdict_type": "synthesis"
}
```

**Why council?** A single model might miss the SQL injection but catch the performance issue. Another spots the race condition. The synthesis combines all findings.

### 2. Support Ticket Triage

**Trigger**: New ticket submitted
**Council**: Binary verdict mode
**Action**: Route to urgent or standard queue

```javascript
{
  "prompt": `Should this ticket be escalated to URGENT priority?

Criteria for URGENT:
- Production system down
- Data loss or corruption
- Security incident
- Multiple users affected

Ticket: ${$json.subject}
Body: ${$json.body}

Respond approved (URGENT) or rejected (STANDARD).`,
  "verdict_type": "binary"
}
```

**Response structure:**
```json
{
  "stage3": {
    "verdict": "approved",
    "confidence": 0.85,
    "rationale": "Customer mentions 'production down' and 'data loss'..."
  }
}
```

Use the confidence score for edge cases: high confidence → auto-route, low confidence → human review.

### 3. Technical Design Decisions

**Trigger**: Design doc submitted for review
**Council**: Synthesis with dissent tracking
**Action**: Send feedback to Slack/email

```javascript
{
  "prompt": `As a council of senior architects, evaluate this design:

${$json.design_doc}

Consider: Scalability, Maintainability, Security, Cost, Complexity.

Provide:
- Recommendation (proceed/revise/reject)
- Critical concerns
- Suggested improvements`,
  "verdict_type": "synthesis",
  "include_dissent": true
}
```

**Why include dissent?** Sometimes the minority opinion is right. If 3/4 models say "proceed" but one flags a critical scaling issue, you want to see that.

## Webhook Security: HMAC Verification

When using webhook callbacks, verify signatures to prevent spoofing:

```javascript
// n8n Function node for HMAC verification
const crypto = require('crypto');

const payload = JSON.stringify($input.first().json);
const secret = $env.WEBHOOK_SECRET;
const receivedSig = $input.first().headers['x-council-signature'];

// Generate expected signature
const expectedSig = 'sha256=' + crypto
  .createHmac('sha256', secret)
  .update(payload)
  .digest('hex');

// Timing-safe comparison
if (!crypto.timingSafeEqual(Buffer.from(expectedSig), Buffer.from(receivedSig))) {
  throw new Error('Invalid signature');
}

// Validate timestamp (prevent replay attacks)
const timestamp = parseInt($input.first().headers['x-council-timestamp']);
if (Math.abs(Date.now() / 1000 - timestamp) > 300) {
  throw new Error('Timestamp too old');
}

return $input.first();
```

## Performance Considerations

Council deliberation takes time. Plan accordingly:

| Confidence Tier | Models | Typical Latency |
|-----------------|--------|-----------------|
| `quick` | 2 | 5-10s |
| `balanced` | 3 | 10-20s |
| `high` | 4 | 20-40s |

**For latency-sensitive workflows:**
1. Use `quick` tier for simple decisions
2. Use webhook callbacks instead of blocking
3. Cache common queries

```javascript
// Async with webhook callback
{
  "prompt": "...",
  "webhook_url": "https://your-n8n.com/webhook/council-result",
  "webhook_secret": "{{ $env.WEBHOOK_SECRET }}",
  "webhook_events": ["council.complete", "council.error"]
}
```

## Error Handling

Council calls can fail (rate limits, timeouts, model errors). Build resilience:

```
[Council Request] → [IF Error?] → [Yes] → [Fallback Logic]
                               → [No] → [Process Result]
```

Fallback options:
- Retry with exponential backoff
- Fall back to single model
- Queue for human review

## The Real Tradeoffs

**Cost**: Council deliberation costs more than single-model calls. With 4 models × 3 stages, expect 10-15x the token cost of a single call.

**Latency**: Sequential stages mean 3x the latency of a single call. Use async webhooks for non-blocking workflows.

**When it's worth it**:
- High-stakes decisions (production deployments, security reviews)
- Decisions that would otherwise need human review
- Quality-critical automation where consistency matters

**When it's overkill**:
- Simple classification tasks
- High-volume, low-stakes decisions
- Time-critical real-time systems

## Getting Started

1. **Deploy the council server:**

   **Option A: One-click deploy** (recommended for production):

   [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/github)

   **Option B: Local development:**
   ```bash
   pip install "llm-council-core[http]"
   export OPENROUTER_API_KEY="sk-or-v1-..."
   export LLM_COUNCIL_API_TOKEN=$(openssl rand -hex 16)
   llm-council serve --port 8000
   ```

2. **Import a workflow template:**
   - [Code Review Workflow](../examples/n8n/code-review-workflow.json)
   - [Support Triage Workflow](../examples/n8n/support-triage-workflow.json)
   - [Design Decision Workflow](../examples/n8n/design-decision-workflow.json)

3. **Configure n8n environment:**
   - Set `LLM_COUNCIL_URL` (e.g., `https://your-app.railway.app`)
   - Set `LLM_COUNCIL_TOKEN` for API authentication
   - Set `WEBHOOK_SECRET` for secure callbacks

4. **Test and iterate:**
   - Start with `quick` tier for faster iteration
   - Graduate to `high` tier for production

## What's Next

The council pattern works anywhere you'd use an LLM for decision-making. Beyond n8n:
- GitHub Actions for CI/CD gates
- Slack bots for on-call escalation
- Content pipelines for editorial review

The key insight: automation doesn't have to be dumb. With a council of models deliberating, your workflows can make nuanced decisions—and you get transparency into *why* each decision was made.

**Related guides:**
- [One-Click Deployment](09-one-click-deployment.md) - Deploy to Railway or Render in 60 seconds
- [Deployment Guide](../deployment/index.md) - Platform-specific deployment instructions
- [HTTP API Reference](../guides/http-api.md) - Full API documentation

---

*This is post 8 of the LLM Council series. Previous: [Shadow Mode & Auditions](07-shadow-mode-auditions.md). Next: [One-Click Deployment](09-one-click-deployment.md)*

LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)
