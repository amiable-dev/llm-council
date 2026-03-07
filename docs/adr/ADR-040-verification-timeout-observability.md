# ADR-040: Verification Timeout Guardrails and Observability

**Status:** Accepted 2026-03-07
**Date:** 2026-03-07
**Decision Makers:** Chris Joseph, LLM Council
**Related:** ADR-012, ADR-022, ADR-034

---

## Context

Users of the `verify` and `review` MCP tools (invoked via council-verify and council-review skills) frequently experience excessively long execution times. A recent high-tier verification ran for **57 minutes** before being manually cancelled. Users regularly wait 10+ minutes with minimal feedback before killing the process. This leads to poor UX, resource waste, and trust erosion in the tool.

### Root Cause Analysis

Investigation of the codebase reveals **five compounding issues** that interact multiplicatively:

#### 1. No Global Timeout on Verification Pipeline

`run_verification()` in `verification/api.py` calls Stage 1, Stage 2, and Stage 3 **sequentially with no outer timeout**. While `run_council_with_fallback()` has an `asyncio.wait_for()` wrapper, the verification API bypasses this by calling stage functions directly. If any stage hangs, the entire verification hangs indefinitely.

```python
# verification/api.py - NO timeout wrapper around the full pipeline
stage1_results, stage1_usage, _model_statuses = await stage1_collect_responses_with_status(...)
stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(...)  # Can hang
stage3_result, stage3_usage, verdict_result = await stage3_synthesize_final(...)
```

#### 2. Stage 2 Tier Contract Violation (Bug)

`stage2_collect_rankings()` has two correctness bugs:
- Calls `query_models_parallel(reviewers, messages)` with **no timeout parameter**, defaulting to 120s per model regardless of tier
- Uses `_get_council_models()` (global config models) instead of the tier contract's `allowed_models`

This means a user who selects a "quick" tier may unknowingly invoke slow frontier models in Stage 2 that they never consented to. **This is a contract violation, not just a performance issue.**

#### 3. No Input Size Estimation or Guardrails

While individual files are capped at 15K chars and total content at 50K chars, there is **no estimation of total prompt token count** before starting the council. A commit touching 100 files with 50K chars of content generates a massive Stage 2 prompt: the original query + all Stage 1 responses (each 2-5K chars x 4-5 models = 10-25K chars) + rubric instructions. This can exceed 100K tokens per Stage 2 query.

#### 4. Inadequate Progress Reporting

Progress is reported as `num_models + 3` steps. Stage 2 (peer review of all models) is a single step: "Stage 2: Peer review in progress..." This gives the caller **zero visibility** into whether Stage 2 is 10% or 90% complete.

#### 5. No Estimated Duration or Complexity Signal

The MCP tool returns no upfront estimate of expected duration. The caller cannot make informed decisions about whether to proceed, reduce scope, or use a faster tier.

### Worst-Case Failure Composition

The 57-minute hang requires all failures to co-occur:

```
Worst case timeline (estimated):
+-- Stage 1: 5 models x no effective timeout = ~5-15min
+-- Stage 2: wrong slow models, no timeout, huge prompt = ~15-25min
+-- Stage 3: synthesis of massive context = ~5-10min
+-- No progress feedback = user assumes hang at ~2min
Total: 35-50min actual, perceived as "hung" from minute 2
```

## Mandatory Prerequisite: Stage 2 Tier Contract Fix

Before implementing any option, the following **correctness bugs** must be fixed:

### Fix 1: Stage 2 Timeout Propagation

`stage2_collect_rankings()` must accept and use tier-appropriate timeouts:

```python
async def stage2_collect_rankings(
    user_query, stage1_results,
    timeout: float = 120.0,  # NEW: Accept tier timeout
    models: Optional[List[str]] = None,  # NEW: Accept tier models
):
    reviewers = models or list(_get_council_models())
    responses = await query_models_parallel(reviewers, messages, timeout=timeout)
```

### Fix 2: Stage 2 Model Selection

Use tier contract models, not global config:

```python
stage2_results, label_to_model, stage2_usage = await stage2_collect_rankings(
    verification_query, stage1_results,
    timeout=tier_timeout["per_model"],
    models=tier_contract.allowed_models,
)
```

### Fix 3: Stage 3 Timeout

`stage3_synthesize_final()` uses a hardcoded 15s timeout for the chairman. Use tier-appropriate timeout.

These fixes alone may resolve many timeout issues by ensuring the tier SLA is actually honored.

## Options Considered

### Option A: Global Timeout Wrapper + Partial Results (Recommended)

Wrap `run_verification()` in `asyncio.wait_for()` using a single global deadline with waterfall time budgeting across stages.

**Time Budget Model:**

Use a single global deadline representing maximum user-facing wall-clock time. Pass remaining budget to each stage sequentially (waterfall pattern):

```python
async def run_verification(request, store, on_progress=None):
    tier_contract = create_tier_contract(request.tier)
    deadline = tier_contract.deadline_ms / 1000 * 1.5  # 1.5x for 3-stage pipeline
    deadline_at = time.monotonic() + deadline

    try:
        return await asyncio.wait_for(
            _run_verification_pipeline(request, store, on_progress, tier_contract, deadline_at),
            timeout=deadline
        )
    except asyncio.TimeoutError:
        return _build_partial_result(verification_id, completed_stages, partial_data)
```

Stage budget waterfall:
```python
# Each stage gets remaining time, with proportional allocation
remaining = deadline_at - time.monotonic()
stage1_budget = remaining * 0.50  # 50% for Stage 1
# After Stage 1 completes:
remaining = deadline_at - time.monotonic()
stage2_budget = remaining * 0.70  # 70% of remaining for Stage 2
# After Stage 2 completes:
stage3_budget = deadline_at - time.monotonic()  # All remaining for Stage 3
```

**Tier deadlines (verification pipeline):**

| Tier | Global Deadline | Per-Model | Expected Duration |
|------|----------------|-----------|-------------------|
| quick | 45s | 20s | 15-30s |
| balanced | 135s | 45s | 45-90s |
| high | 270s (4.5 min) | 90s | 2-4 min |
| reasoning | 900s (15 min) | 300s | 5-10 min |

Note: Deadlines are `deadline_ms * 1.5` to accommodate 3 sequential stages within a single user-facing SLA.

**Timeout Behavior Policy:**

The system must produce a predictable response regardless of when timeout fires:

| Timeout During | Behavior | Result Fields |
|---|---|---|
| Stage 1 | Return raw model outputs received so far | `status: "timeout_partial"`, `completed_stages: ["stage1_partial"]` |
| Stage 2 | Return Stage 1 results + completed reviews | `status: "timeout_partial"`, `completed_stages: ["stage1"]`, `missing_reviews: [...]` |
| Stage 3 | Return Stage 2 rankings without chairman synthesis | `status: "timeout_partial"`, `completed_stages: ["stage1", "stage2"]` |

Partial results always include `partial: true` and `timeout_fired: true` in the response schema.

**Pros:** Simple, reliable upper bound. Reuses existing partial result pattern from ADR-012.
**Cons:** Hard cutoff may lose work. Doesn't address root cause of slowness.

### Option B: Input Complexity Estimation + Tier Compliance Check (Recommended)

Before starting deliberation, estimate prompt complexity and emit a tier compliance warning. Framed as a **compliance check** rather than a precise duration prediction (LLM latency is non-linear and depends on provider load).

**Implementation:**
```python
async def estimate_verification_complexity(request, tier_contract):
    """Estimate complexity as first progress event (<100ms)."""
    file_contents = await _fetch_files_for_verification_async(request.snapshot_id, request.target_paths)
    content_chars = len(file_contents)
    num_models = len(tier_contract.allowed_models)

    # Stage 2 token multiplication
    stage2_estimated_tokens = (content_chars // 3) + (num_models * 3000) + 2000

    return {
        "stage": "preflight",
        "content_chars": content_chars,
        "num_models": num_models,
        "estimated_stage2_tokens": stage2_estimated_tokens,
        "tier": request.tier,
        "tier_deadline_seconds": tier_contract.deadline_ms / 1000 * 1.5,
        "warning": _get_compliance_warning(content_chars, request.tier),
    }
```

Warning examples:
- `"Input size 45K chars may exceed balanced tier deadline of 2m15s. Consider using 'high' tier or reducing scope."`
- `None` (no warning, within expected bounds)

**Tiered input limits:**

| Tier | MAX_TOTAL_CHARS | Rationale |
|------|----------------|-----------|
| quick | 15,000 | Must complete in <45s |
| balanced | 30,000 | Must complete in <2.5min |
| high | 50,000 | Current limit, fits in 4.5min deadline |
| reasoning | 50,000 | Extended timeout accommodates larger input |

Inputs exceeding the tier limit are rejected with a helpful error suggesting scope reduction or tier upgrade.

**Pros:** Informed decision-making. Fast (<100ms). Prevents wasted time on oversized inputs.
**Cons:** Estimates may be inaccurate for duration. Adds a rejection path.

### Option C: Chunked Verification for Large Inputs (Rejected)

**Rejected.** Unanimous council agreement. Chunking breaks cross-file reasoning, dependency checks, and architectural consistency analysis. It also creates a **false confidence** problem where users believe they received a complete review when they actually received N independent reviews with no cross-chunk analysis.

If a user submits input exceeding the tier's MAX_TOTAL_CHARS, the system rejects with a clear error suggesting manual scope reduction.

### Option D: Enhanced Progress Reporting with Structured Schema (Recommended)

Improve progress granularity with a committed JSON schema so the calling LLM can make informed abort decisions.

**Progress Event Schema:**

```json
{
  "stage": "stage_2_peer_review",
  "stage_index": 2,
  "stage_total": 3,
  "elapsed_seconds": 47,
  "estimated_remaining_seconds": 90,
  "deadline_seconds": 270,
  "models_completed": 3,
  "models_total": 5,
  "can_synthesize_partial": true,
  "input_complexity": {
    "content_chars": 45200,
    "tier": "high"
  }
}
```

**Stage 2 per-model progress (using `asyncio.as_completed`):**

```python
async def stage2_with_progress(query, stage1_results, reviewers, timeout, on_progress):
    tasks = {
        asyncio.create_task(query_model(model, messages, timeout=timeout)): model
        for model in reviewers
    }
    completed = 0
    for coro in asyncio.as_completed(tasks.keys()):
        result = await coro
        completed += 1
        model = tasks[...]  # resolve model from task
        await on_progress(completed, len(reviewers),
            f"Stage 2: {model.split('/')[-1]} reviewed ({completed}/{len(reviewers)})")
```

Using `asyncio.as_completed` instead of `asyncio.gather` ensures that one slow reviewer doesn't block progress reporting for completed reviewers.

**Pros:** Non-breaking improvement. Caller can make abort decisions. Committed schema enables stable client integration.
**Cons:** Doesn't prevent slowness, just improves visibility. Schema becomes a compatibility surface.

### Option E: Tiered Stage 2 Optimization (Deferred)

**Deferred** until Options A+D provide observability data. Optimizing Stage 2 before we can measure it is premature. Once we have stage duration metrics, we can make data-driven decisions about sampling strategies.

### Option F: Early Consensus Termination (Future Consideration)

Council-suggested addition: if a threshold of reviewers (e.g., 3 out of 5) establish strong agreement early, cancel remaining pending reviewer tasks to save time and tokens.

**Deferred** as a Phase 4 optimization. Requires defining "strong agreement" thresholds and handling the cancelled-task cleanup.

## Decision

**Implement mandatory bug fixes + Options A + B + D** in two phases:

### Phase 1: Stop the Bleeding (Priority: Critical)

1. **Fix Stage 2 tier contract bugs** (prerequisite) - pass tier timeouts and models
2. **Fix Stage 3 timeout** - use tier-appropriate timeout instead of hardcoded 15s
3. **Option A: Global timeout wrapper** with waterfall time budgeting
4. **Partial result synthesis** with explicit timeout behavior policy

### Phase 2: UX Enhancement (Priority: High)

1. **Option D: Enhanced progress reporting** with committed JSON schema
2. **Option B: Pre-flight tier compliance check** integrated into first progress callback
3. **Tiered input size limits** with helpful rejection messages
4. Add observability metrics (stage durations, timeout frequency, estimated vs actual duration)

### Success Criteria

- P95 verification latency for high tier < 270s (4.5 min)
- Zero occurrences of > 600s hangs across all tiers
- User receives first structured progress event within 5s of invocation
- Partial results on timeout are schema-compliant (valid VerifyResponse)

### Rollback Plan

If the global timeout wrapper introduces regressions (false timeouts on legitimate work):
1. Increase tier deadline multiplier from 1.5x to 2.0x via `LLM_COUNCIL_TIMEOUT_MULTIPLIER`
2. If still problematic, disable global timeout wrapper via feature flag (revert to unbounded)
3. Root cause analysis using observability metrics from Phase 2

## Consequences

### Positive
- **No more indefinite hangs**: Global timeout guarantees bounded execution time
- **Tier contract honored**: Stage 2 respects the tier the user selected
- **Informed callers**: Structured progress data enables intelligent abort/wait decisions
- **Better UX**: Per-model progress instead of opaque "peer review in progress..."
- **Partial results**: Even on timeout, users get actionable output
- **Debuggability**: Stage duration metrics aid troubleshooting

### Negative
- **Partial results may be lower quality**: Timeout-forced synthesis uses incomplete data
- **Input rejections**: Oversized inputs for a tier are now rejected (previously just slow)
- **Schema commitment**: Progress event schema becomes a compatibility surface
- **Complexity**: Waterfall time budgeting adds code complexity

### Neutral
- **Backward compatible output**: VerifyResponse schema unchanged (new fields are additive)
- **No config changes required**: Uses existing tier contract deadlines (with 1.5x multiplier)

## Compliance / Validation

1. **Timeout enforcement test**: Verify no verification exceeds tier deadline * 1.1 (10% grace)
2. **Tier contract test**: Verify Stage 2 uses tier contract models and timeouts
3. **Progress granularity test**: Verify Stage 2 emits per-model progress events
4. **Partial result test**: Verify timeout produces valid VerifyResponse with `partial: true`
5. **Input limit test**: Verify oversized inputs are rejected with helpful error
6. **Schema compliance test**: Verify progress events match committed JSON schema
7. **Integration test**: High-tier verification on 50K char commit completes within 4.5 min

## Resolved Questions (Council Deliberation 2026-03-07)

**Q1: Global deadline scope?**
Use a single global deadline representing the maximum user-facing wall-clock time (`deadline_ms * 1.5`). Manage internally via waterfall time budgeting where each stage receives the remaining budget. Do not multiply by 2x.

**Q2: Chunked verification or input cap?**
Cap input size with per-tier limits. Reject chunking (Option C) due to loss of cross-file context and false confidence problem. Unanimous council agreement.

**Q3: Pre-flight estimation: separate tool or integrated?**
Integrated into the first structured progress callback. A separate tool adds friction and users will skip it. Unanimous council agreement.

**Q4: Is 50K MAX_TOTAL_CHARS too generous?**
Yes for lower tiers, appropriate for high/reasoning. Implement tiered limits: quick=15K, balanced=30K, high/reasoning=50K. Add instrumentation to track `char_count -> actual_duration` for data-driven refinement.

**Q5: Approaches not considered?**
Council identified two additional approaches:
- **Early Consensus Termination** (Option F): Cancel remaining reviewers when strong agreement achieved. Deferred to Phase 4.
- **Speculative Stage 2 execution**: Begin Stage 2 as Stage 1 results arrive (don't wait for all). Deferred as architecturally complex.

**Q6: Is A+B+D correct?**
Yes. Unanimous approval. Council emphasized elevating Stage 2 bug fixes to mandatory prerequisite status, defining explicit timeout behavior policy, and implementing in two phases (critical fixes first, UX polish second).

## Council Deliberation Summary

**Models consulted:** gemini-3.1-flash-lite-preview, gpt-5.3-chat, claude-sonnet-4.6, deepseek-v3.2
**Consensus level:** High (unanimous on core recommendations)
**Key council contributions incorporated:**
1. Stage 2 bugs elevated from "implementation detail" to "mandatory prerequisite"
2. Waterfall time budgeting model (instead of `deadline_ms * 2`)
3. Explicit timeout behavior policy per scenario (mid-Stage 1/2/3)
4. Progress event JSON schema commitment
5. Tiered input size limits
6. Framing pre-flight as "tier compliance check" not "duration prediction"
7. Two-phase implementation (critical fixes first, UX polish second)
8. Success criteria, rollback plan, and observability metrics
9. Early consensus termination as future Option F
10. Rejection of chunking due to "false confidence" argument

## Appendix: Timing Data

### Expected Duration by Tier (after fixes)

| Tier | Stage 1 | Stage 2 | Stage 3 | Total |
|------|---------|---------|---------|-------|
| quick | 10-15s | 15-20s | 5-10s | 30-45s |
| balanced | 20-30s | 30-45s | 10-15s | 60-90s |
| high | 30-60s | 60-120s | 15-30s | 105-210s |
| reasoning | 60-180s | 120-300s | 30-60s | 210-540s |

### Stage 2 Prompt Size Multiplication

For N models and C content chars:
- Stage 2 prompt per reviewer = C + (N * avg_response_size) + rubric_template
- With N=5, C=50K, avg_response=3K: prompt = 50K + 15K + 2K = 67K chars (~22K tokens)
- 5 reviewers x 22K input tokens each = 110K total input tokens in Stage 2 alone
