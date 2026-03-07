# ADR-041: Verification Telemetry Wiring

**Status:** Proposed 2026-03-07
**Date:** 2026-03-07
**Decision Makers:** Chris Joseph, LLM Council
**Related:** ADR-026 (Phase 3), ADR-040 (Phase 2 item 4)

---

## Context

Two existing ADRs promise telemetry capabilities that are not functioning in production:

### ADR-026 Phase 3: Dead Code

ADR-026 Phase 3 is marked `IMPLEMENTED` and delivered a complete `performance/` module (~700 lines, 70 tests) with:
- `ModelSessionMetric` — per-model per-session latency, Borda score, parse success
- `InternalPerformanceTracker` — rolling window aggregation with exponential decay
- `ModelPerformanceIndex` — p50/p95 latency, mean Borda, confidence levels
- `persist_session_performance_data()` — integration entry point
- JSONL storage following the `bias_persistence.py` pattern

**The problem:** `persist_session_performance_data()` is never called from any production code path. It is only called from tests. The performance store at `~/.llm-council/performance_metrics.jsonl` does not exist on any installation. The entire Phase 3 module is dead code.

This means:
- `get_quality_score()` always returns 50.0 (cold start) for every model
- `select_tier_models()` cannot use internal performance data for selection
- The ADR-029 audition mechanism's quality percentile graduation gate (`>= 75th percentile`) can never fire
- ADR-026's validation gate ("100+ sessions tracked") has never been met

### ADR-040 Phase 2 Item 4: Missing Observability

ADR-040 Phase 2 explicitly requires:
> "Add observability metrics (stage durations, timeout frequency, estimated vs actual duration)"

With success criteria:
> "P95 verification latency for high tier < 270s (4.5 min)"

And resolved question Q4:
> "Add instrumentation to track `char_count -> actual_duration` for data-driven refinement"

**The problem:** The verification pipeline (`verification/api.py`) uses `time.monotonic()` internally for waterfall budgeting but **discards all timing data**. No per-stage duration is recorded in transcripts. No total elapsed time appears in `result.json`. The success criteria cannot be measured.

Additionally, ADR-040's deferred options depend on this data:
- **Option E** (Tiered Stage 2 Optimization): "Deferred until Options A+D provide observability data"
- **Option F** (Early Consensus Termination): Requires stage duration data to tune thresholds

### Impact: High-Tier Timeouts Cannot Be Tuned

Users report frequent timeouts on high-tier verification. Without timing telemetry, we cannot:
1. Determine which stage is the bottleneck (Stage 1 vs Stage 2 vs Stage 3)
2. Identify which models are consistently slow
3. Validate whether the 1.5x timeout multiplier is appropriate
4. Measure whether waterfall budget ratios (50%/70%/remaining) are well-calibrated
5. Compare `char_count` to actual duration for input size limit refinement
6. Make data-driven decisions about ADR-040 Option E or F

### Current Data Available

The only data source is verification transcripts (`.council/logs/`), which contain:
- `request.json` — tier, paths, rubric_focus (no timing)
- `stage1.json` — model responses (no per-model latency)
- `stage2.json` — rankings (no per-reviewer latency)
- `stage3.json` — synthesis (no duration)
- `result.json` — verdict, confidence, `timeout_fired` (no elapsed time)

26 transcripts exist locally but none contain timing data.

## Decision

Wire the existing telemetry infrastructure into the verification pipeline. This is primarily an integration task — the storage, aggregation, and analysis code already exists.

### Phase 1: Transcript Timing (Verification Pipeline)

Record wall-clock timing in verification transcripts for immediate observability.

**1.1 Per-stage timing in `_run_verification_pipeline()`**

Add `stage_elapsed_ms` to each stage's transcript entry:

```python
# Already have: remaining = max(deadline_at - time.monotonic(), 1.0)
stage1_start = time.monotonic()
# ... stage 1 execution ...
stage1_elapsed_ms = int((time.monotonic() - stage1_start) * 1000)
partial_state["stage_timings"]["stage1"] = stage1_elapsed_ms
```

**1.2 Per-model latency in Stage 1 and Stage 2**

Stage 1 already returns `model_statuses` with `latency_ms` from the gateway. Persist this in `stage1.json`.

Stage 2's `asyncio.as_completed` path (ADR-040) can record per-reviewer timing. Persist in `stage2.json`.

**1.3 Summary timing in `result.json`**

Add to transcript result:
```json
{
  "timing": {
    "total_elapsed_ms": 142000,
    "stage1_elapsed_ms": 45000,
    "stage2_elapsed_ms": 78000,
    "stage3_elapsed_ms": 19000,
    "global_deadline_ms": 270000,
    "timeout_fired": false,
    "budget_utilization": 0.53
  },
  "input_metrics": {
    "content_chars": 32000,
    "tier_max_chars": 50000,
    "num_models": 4,
    "num_reviewers": 4
  }
}
```

### Phase 2: Performance Tracker Integration

Wire `persist_session_performance_data()` into the verification pipeline so the ADR-026 Phase 3 tracker actually accumulates data.

**2.1 Call site in `run_verification()`**

After successful (or partial) verification, call:
```python
from llm_council.performance import persist_session_performance_data

persist_session_performance_data(
    session_id=verification_id,
    model_statuses=model_statuses,  # from stage1
    aggregate_rankings=aggregate_rankings,  # from stage2
    stage2_results=stage2_results,
)
```

**2.2 Call site in `consult_council` MCP tool**

The main council deliberation path in `mcp_server.py` also never calls the tracker. Wire it there too.

### Phase 3: Analysis CLI

Extend the existing `bias-report` CLI pattern to add a `timing-report` command:

```bash
llm-council timing-report [--days N] [--tier TIER] [--format text|json]
```

Output:
- Per-tier P50/P95/P99 total elapsed time
- Per-stage P50/P95 breakdown
- Per-model P50/P95 latency
- Timeout frequency by tier
- `char_count` vs `actual_duration` correlation
- Budget utilization distribution

### What This Enables

Once data accumulates (target: 30+ sessions for PRELIMINARY confidence):
- **Timeout tuning**: Adjust `VERIFICATION_TIMEOUT_MULTIPLIER` based on P95 data
- **Budget ratio tuning**: Adjust 50%/70%/remaining waterfall based on actual stage proportions
- **Input limit refinement**: Adjust `TIER_MAX_CHARS` based on `char_count -> duration` correlation
- **Model selection feedback**: `select_tier_models()` uses real latency/quality data
- **ADR-040 Option E**: Data-driven Stage 2 optimization decisions
- **ADR-029 graduation**: Audition quality percentile gate becomes functional

### ADR Updates Required

1. **ADR-026 Phase 3**: Change `IMPLEMENTED` to `IMPLEMENTED (wiring incomplete)` with note pointing to ADR-041
2. **ADR-040 Phase 2**: Add implementation status for item 4 pointing to ADR-041

## Consequences

### Positive
- **Existing investment pays off**: ~700 lines of performance tracking code becomes functional
- **Data-driven timeout tuning**: Replace guesswork with measured P95 latencies
- **ADR-040 success criteria measurable**: Can finally validate "P95 < 270s for high tier"
- **ADR-029 audition unblocked**: Quality percentile graduation gate becomes functional
- **Low risk**: No new abstractions — wiring existing code to existing call sites

### Negative
- **Disk usage**: JSONL files grow over time (~200 bytes per model per session)
- **Minor latency**: File I/O for persistence adds ~1-2ms per session (negligible vs 60-270s sessions)
- **Migration**: Old transcripts lack timing data; analysis tools must handle missing fields

### Neutral
- **No schema changes to VerifyResponse**: Timing data goes to transcripts and JSONL, not API response
- **Backward compatible**: transcript `result.json` gains new `timing` field (additive)

## Compliance / Validation

1. **Transcript timing test**: Verify `result.json` contains `timing` object with all required fields
2. **Performance store test**: Verify `~/.llm-council/performance_metrics.jsonl` is created and populated after a verification session
3. **CLI test**: `llm-council timing-report` produces output when data exists
4. **Integration test**: Run 5 verification sessions, verify timing data is consistent and `budget_utilization` is between 0 and 1
5. **ADR-040 validation**: After 30+ sessions, measure P95 high-tier latency against 270s target
