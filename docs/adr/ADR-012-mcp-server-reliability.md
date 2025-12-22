# ADR-012: MCP Server Reliability and Long-Running Operation Handling

**Status:** Accepted (Implemented via TDD)
**Date:** 2025-12-13
**Decision Makers:** Engineering

---

## Context

The LLM Council MCP server performs multi-model deliberation that can take 30-60+ seconds to complete. This creates several problems when used with MCP clients (Claude Code, Claude Desktop):

### Observed Issues

1. **Timeout failures**: MCP clients have transport-layer timeouts (typically 30-60s) that can expire before the council finishes deliberating across 4+ models
2. **Empty results on timeout**: When timeout occurs, the entire operation fails and returns empty results rather than partial data
3. **No visibility during execution**: Users see no feedback while the council is working, leading to uncertainty about whether the operation is progressing or hung
4. **No health verification**: No way to verify the MCP server is healthy before invoking expensive operations

### Current Architecture

```
┌─────────────────────────────────────────────────────────┐
│  MCP Client (Claude Code/Desktop)                       │
│  - Invokes consult_council tool                         │
│  - Waits synchronously for response                     │
│  - Times out after N seconds (client-controlled)        │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  MCP Server (llm-council)                               │
│  - Runs full 3-stage council synchronously              │
│  - Stage 1: Query all models (10-20s)                   │
│  - Stage 2: Peer review (15-30s)                        │
│  - Stage 3: Chairman synthesis (5-15s)                  │
│  - Returns only on completion or error                  │
└─────────────────────────────────────────────────────────┘
```

**Total time**: 30-65+ seconds for a 4-model council

### Critical Constraint (Council Insight)

**`ctx.report_progress()` does NOT extend client timeouts.** Progress notifications improve UX but the server is still racing against the client's hard timeout. Internal time budgets must be strictly managed.

---

## Decision

Implement a multi-layered reliability strategy:

### 1. Progress Notifications (Streaming Updates)

Use MCP's built-in progress notification mechanism to send real-time updates during council execution.

**Implementation**:
```python
@mcp.tool()
async def consult_council(query: str, ctx: Context, include_details: bool = False) -> str:
    total_steps = len(COUNCIL_MODELS) * 2 + 2  # stage1 + stage2 + synthesis + finalize
    current_step = 0

    # Stage 1: Individual responses
    for i, model in enumerate(COUNCIL_MODELS):
        await ctx.report_progress(current_step, total_steps, f"Querying {model}...")
        # Query model
        current_step += 1

    # Stage 2: Peer review
    await ctx.report_progress(current_step, total_steps, "Peer review in progress...")
    # ... continue with progress updates
```

**Benefits**:
- Keeps connection alive (prevents some timeout scenarios)
- Provides user visibility into operation progress
- Enables client-side timeout decisions based on stage

### 2. Partial Results on Failure

When timeout or partial failure occurs, return whatever data has been collected rather than failing entirely.

**Tiered Timeout Strategy** (Updated 2025-12-17):

Based on observed model response times (complex queries can take 40-60s per model), timeouts have been calibrated to prioritize completeness:

```
Confidence Level    Timeout    Use Case
─────────────────────────────────────────
quick               30s        Fast responses, may have fewer models
balanced            75s        Most models respond
high                120s       Full council deliberation (default)
```

**Note**: Original council recommendation was 15s/25s/40s/50s tiered deadlines, but real-world latencies required significant increases.

**Implementation**:
```python
async def run_full_council_with_fallback(query: str, synthesis_deadline: float = 40.0):
    results = {
        "synthesis": "",
        "model_responses": {},
        "metadata": {
            "status": "complete",  # or "partial", "failed"
            "completed_models": 0,
            "requested_models": len(COUNCIL_MODELS),
            "synthesis_type": "full"  # or "partial", "insufficient"
        }
    }

    try:
        async with asyncio.timeout(synthesis_deadline):
            # Run full council with per-model timeouts
            stage1, stage2, stage3, meta = await run_full_council(query)
            results["synthesis"] = stage3.get("response", "")
            # ... populate model_responses
    except asyncio.TimeoutError:
        results["metadata"]["status"] = "partial"
        # Synthesize from whatever we have
        if len(results["model_responses"]) > 0:
            results["synthesis"] = await quick_synthesis(query, results["model_responses"])
            results["metadata"]["synthesis_type"] = "partial"

    return results
```

**Implementation Note (2025-12-17)**: The above pseudocode has a subtle bug—when `asyncio.wait_for` times out, it cancels the inner coroutine before `model_responses` is populated. The fix uses a **shared dict pattern**:

```python
# Create shared dict BEFORE the try block
shared_raw_responses: Dict[str, Any] = {}

async def run_council_pipeline():
    # Pass shared dict to model queries
    responses = await query_models_with_progress(
        models, messages,
        shared_results=shared_raw_responses  # Populated incrementally
    )
    # ... rest of pipeline

try:
    await asyncio.wait_for(run_council_pipeline(), timeout=deadline)
except asyncio.TimeoutError:
    # shared_raw_responses survives cancellation!
    # Build model_responses from it, marking missing models as "timeout"
```

**Structured Result Schema** (Council Recommendation):
```json
{
  "synthesis": "Based on available responses...",
  "model_responses": {
    "gpt-4": {"status": "ok", "latency_ms": 12340, "response": "..."},
    "claude": {"status": "timeout", "error": "timeout after 25s"},
    "gemini": {"status": "ok", "latency_ms": 8920, "response": "..."},
    "llama": {"status": "rate_limited", "retry_after": 30}
  },
  "metadata": {
    "status": "partial",
    "completed_models": 2,
    "requested_models": 4,
    "synthesis_type": "partial",
    "warning": "This answer is based on 2 of 4 intended models; Claude and Llama did not respond."
  }
}
```

**Failure Taxonomy** (Council Addition):
| Failure Type | Handling |
|--------------|----------|
| **Timeout** | Return partial results + synthesis |
| **Rate limiting (429)** | Retry with backoff before falling back |
| **Auth failure (401/403)** | Fail fast, don't waste time on other calls |
| **Network partition** | Different retry strategy than timeout |

**Fallback Synthesis Modes**:
| Condition | Fallback |
|-----------|----------|
| Stage 1 complete, Stage 2 timeout | Chairman synthesizes from Stage 1 only (skip peer review) |
| Stage 1 partial (some models responded) | Synthesize from available responses |
| All models timeout | Return error with diagnostic info |

### 3. Health Check Tool

Add a lightweight health check tool that verifies:
- MCP server is running
- OpenRouter API key is configured
- At least one model is reachable

**Implementation**:
```python
@mcp.tool()
async def council_health_check() -> str:
    """
    Check LLM Council health before expensive operations.
    Returns status of API connectivity and estimated response time.
    """
    checks = {
        "api_key_configured": bool(OPENROUTER_API_KEY),
        "models_configured": len(COUNCIL_MODELS),
        "chairman_model": CHAIRMAN_MODEL,
        "estimated_duration_seconds": estimate_duration(len(COUNCIL_MODELS)),
    }

    # Quick connectivity test (single cheap model, short prompt)
    if checks["api_key_configured"]:
        try:
            start = time.time()
            response = await query_model(
                "google/gemini-2.0-flash-001",  # Fast, cheap
                [{"role": "user", "content": "ping"}],
                timeout=10.0
            )
            checks["api_reachable"] = response is not None
            checks["latency_ms"] = int((time.time() - start) * 1000)
        except Exception as e:
            checks["api_reachable"] = False
            checks["error"] = str(e)

    return json.dumps(checks, indent=2)
```

### 4. Confidence Levels (Updated 2025-12-17)

Instead of a simple "fast mode" toggle, implement **confidence levels** that map to different timeout strategies:

```python
@mcp.tool()
async def consult_council(
    query: str,
    ctx: Context,
    confidence: str = "high",  # "quick", "balanced", "high"
    include_details: bool = False
) -> str:
    """
    Args:
        confidence: "quick" (~30s), "balanced" (~75s), "high" (~120s, default)
    """
    configs = {
        "quick": {"models": 2, "timeout": 30},
        "balanced": {"models": 3, "timeout": 75},
        "high": {"models": len(COUNCIL_MODELS), "timeout": 120}
    }
    config = configs.get(confidence, configs["high"])
    # ... proceed with selected configuration
```

**Progress Feedback**: During model queries, progress updates show which models have responded:
```
✓ claude-opus-4.5 (1/4) | waiting: gpt-5.1, gemini-3-pro, grok-4
✓ gemini-3-pro (2/4) | waiting: gpt-5.1, grok-4
```

**Alternative: Racing Pattern** (Council Suggestion)

Query more models than needed, return when sufficient responses arrive:
```python
# Query 5 models, return when 3 complete (first-past-the-post)
async def race_council(query: str, target_responses: int = 3):
    tasks = [query_model(m, query) for m in COUNCIL_MODELS[:5]]
    completed = []
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result:
            completed.append(result)
        if len(completed) >= target_responses:
            break
    return completed
```

### 5. Tier-Sovereign Timeout Architecture (Added 2025-12-19)

**Council Verdict:** Move from hardcoded per-model timeouts to a **Tier-Sovereign** configuration where each tier defines its own time budget.

**Problem:** Reasoning models (GPT-5.2-pro, o1) require 60-110s per query, far exceeding the original 25s per-model timeout. A global timeout increase would break fast-path tiers.

**Solution:** 4-tier system with per-tier configurable timeouts:

| Tier | Total Timeout | Per-Model Cap | Target Models | Use Case |
|------|---------------|---------------|---------------|----------|
| **quick** | 30s | 20s | GPT-4o-mini, Haiku | Fast answers, fewer models |
| **balanced** | 90s | 45s | Sonnet 3.5, GPT-4o | Most models respond |
| **high** | 180s | 90s | Full council (non-reasoning) | Complete deliberation |
| **reasoning** | 600s | 300s | o1, GPT-5.2-pro | Deep reasoning models (doubled 2025-12-22) |

**Configuration via Environment Variables:**

```bash
# Per-tier total timeout (seconds)
LLM_COUNCIL_TIMEOUT_QUICK=30
LLM_COUNCIL_TIMEOUT_BALANCED=90
LLM_COUNCIL_TIMEOUT_HIGH=180
LLM_COUNCIL_TIMEOUT_REASONING=600

# Per-tier per-model timeout (seconds)
LLM_COUNCIL_MODEL_TIMEOUT_QUICK=20
LLM_COUNCIL_MODEL_TIMEOUT_BALANCED=45
LLM_COUNCIL_MODEL_TIMEOUT_HIGH=90
LLM_COUNCIL_MODEL_TIMEOUT_REASONING=300

# Global multiplier (emergency override)
LLM_COUNCIL_TIMEOUT_MULTIPLIER=1.0
```

**Implementation:**

```python
# config.py additions
DEFAULT_TIER_TIMEOUTS = {
    "quick": {"total": 30, "per_model": 20},
    "balanced": {"total": 90, "per_model": 45},
    "high": {"total": 180, "per_model": 90},
    "reasoning": {"total": 600, "per_model": 300},
}

def get_tier_timeout(tier: str) -> dict:
    """Get timeout configuration for a tier, with env var overrides."""
    defaults = DEFAULT_TIER_TIMEOUTS.get(tier, DEFAULT_TIER_TIMEOUTS["high"])
    tier_upper = tier.upper()

    total = int(os.getenv(f"LLM_COUNCIL_TIMEOUT_{tier_upper}", defaults["total"]))
    per_model = int(os.getenv(f"LLM_COUNCIL_MODEL_TIMEOUT_{tier_upper}", defaults["per_model"]))

    # Apply global multiplier if set
    multiplier = float(os.getenv("LLM_COUNCIL_TIMEOUT_MULTIPLIER", "1.0"))

    return {
        "total": int(total * multiplier),
        "per_model": int(per_model * multiplier),
    }
```

**MCP Server Integration:**

```python
CONFIDENCE_CONFIGS = {
    "quick": {"models": 2, **get_tier_timeout("quick")},
    "balanced": {"models": 3, **get_tier_timeout("balanced")},
    "high": {"models": None, **get_tier_timeout("high")},
    "reasoning": {"models": None, **get_tier_timeout("reasoning")},
}
```

**Infrastructure Considerations:**

| Component | Default | Risk | Mitigation |
|-----------|---------|------|------------|
| AWS ALB idle timeout | 60s | Kills connection during model "thinking" | Increase to 300s or use WebSocket |
| Nginx proxy_read_timeout | 60s | Same as ALB | Set `proxy_read_timeout 300s;` |
| Client-side timeout | Varies | User assumes crash | Stream progress updates |

**Concurrency Safeguard:**

```python
# Limit concurrent reasoning-tier requests to prevent resource exhaustion
REASONING_TIER_SEMAPHORE = asyncio.Semaphore(2)

async def consult_council_reasoning(query: str, ...):
    async with REASONING_TIER_SEMAPHORE:
        return await run_council_with_fallback(query, ...)
```

**Model-Tier Compatibility Matrix:**

| Model | quick | balanced | high | reasoning |
|-------|-------|----------|------|-----------|
| GPT-4o-mini | ✓ | ✓ | ✓ | ✓ |
| Claude Haiku | ✓ | ✓ | ✓ | ✓ |
| Claude Sonnet 3.5 | ✗ | ✓ | ✓ | ✓ |
| GPT-4o | ✗ | ✓ | ✓ | ✓ |
| Claude Opus 4.5 | ✗ | ✗ | ✓ | ✓ |
| Gemini 3 Pro | ✗ | ✗ | ✓ | ✓ |
| GPT-5.2-pro | ✗ | ✗ | ✗ | ✓ |
| o1 | ✗ | ✗ | ✗ | ✓ |

**Automatic Tier Selection (Future):**

```python
REASONING_MODELS = {"openai/o1", "openai/gpt-5.2-pro", "openai/o1-preview"}

def infer_tier_from_models(models: List[str]) -> str:
    """Auto-select tier based on slowest model in council."""
    if any(m in REASONING_MODELS for m in models):
        return "reasoning"
    # ... additional logic
    return "high"
```

### 6. Job-Based Async Pattern (Deferred)

**Council Verdict: Defer indefinitely.** The job-based pattern adds significant complexity (persistence, job lifecycle, cleanup, polling UX) that conflicts with MCP's stateless design.

**When to reconsider:**
- Operations consistently exceed 5 minutes
- Multiple clients need to check the same job
- Resumability across server restarts is required

If implemented later, use in-memory job tracking with TTL (jobs expire after 5 minutes) rather than persistent storage.

---

## Implementation Phases

| Phase | Scope | Effort |
|-------|-------|--------|
| **Phase 1** | Progress notifications + tiered timeouts | 1-2 days |
| **Phase 2** | Partial results with structured metadata | 2-3 days |
| **Phase 3** | Health check tool | 1 day |
| **Phase 4** | Confidence levels parameter | 1-2 days |
| **Deferred** | Job-based async pattern | Not planned |

---

## Alternatives Considered

### Alternative 1: Increase Client Timeouts

**Rejected**: We don't control client-side timeouts. Users configure their MCP clients independently.

### Alternative 2: Reduce Council Size

**Rejected**: Defeats the purpose of multi-model deliberation. Users should be able to use 4+ models. However, confidence levels provide this as an option.

### Alternative 3: Pre-compute Common Queries

**Partially Adopted**: We already have caching (ADR-008), but this only helps for repeated queries.

### Alternative 4: Server-Sent Events (SSE) Transport

**Considered for Future**: MCP supports streamable-http transport which could enable true streaming. However, this requires client support and is more complex to implement.

### Alternative 5: Racing Pattern (Council Suggestion)

**Adopted as Option**: Query more models than needed, return when sufficient responses arrive. Reduces latency by not waiting for slow models.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Progress notifications not supported by all clients | Graceful degradation - notifications are advisory |
| Partial results may be lower quality | Clear labeling in metadata: "synthesis_type": "partial" |
| Health check adds latency before main operation | Make health check optional; recommend calling once per session |
| Rate limiting (429) during parallel queries | Distinguish from timeouts; retry with backoff before falling back |
| Memory pressure from concurrent councils | Limit concurrency per request and globally |

---

## Success Metrics

1. **Timeout rate reduction**: < 5% of council operations should timeout (currently estimated 20-30%)
2. **User visibility**: Progress updates visible in supporting clients
3. **Partial result utility**: When partial results returned, user satisfaction > 70%
4. **Transparency**: Users can identify which models contributed to any answer

---

## Council Review Decisions

| Question | Council Verdict |
|----------|-----------------|
| Job-based async vs streaming? | **Streaming progress + tiered timeouts.** Defer async pattern indefinitely. |
| Optimal deadline? | **40-45s** (not 55s). Tiered per-model deadlines preferred over single global. |
| Indicate which models responded? | **Yes, explicitly.** Structured metadata with per-model status is essential. |
| Fast mode valuable? | **Yes, as "confidence levels"** (quick/balanced/high) mapping to model count + timeout. |
| Reasoning model timeouts? (2025-12-19) | **Tier-Sovereign architecture.** 4 tiers with per-tier configurable timeouts. Reasoning tier: 600s total, 300s per-model (doubled 2025-12-22). |
| Per-tier vs global timeout config? (2025-12-19) | **Per-tier configuration.** Global overrides are dangerous; use per-tier env vars with optional multiplier. |

---

## References

- [MCP Python SDK - Progress Reporting](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP Context API](https://deepwiki.com/punkpeye/fastmcp/8.4-logging-and-progress-reporting)
- [Streamable HTTP Transport](https://blog.cloudflare.com/streamable-http-mcp-servers-python/)
