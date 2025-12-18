# ADR-018: Cross-Session Bias Aggregation

**Status:** Proposed → Accepted with Modifications (2025-12-17)
**Date:** 2025-12-17
**Decision Makers:** Engineering, LLM Council
**Related:** ADR-015 (Bias Auditing), ADR-017 (Response Order Randomization)

---

## Context

### The Problem: Statistical Power in Single Sessions

ADR-015 implemented per-session bias auditing with three detection mechanisms:
- Length-score correlation (Pearson r)
- Position bias (variance of position means)
- Reviewer calibration (harsh/generous detection)

However, a fundamental limitation exists: **single council sessions lack sufficient statistical power for meaningful bias detection.**

### Current Data Limitations

In a typical council session with N=4-5 models:

| Metric | Data Points | Minimum for Significance | Gap |
|--------|-------------|-------------------------|-----|
| Length correlation | 4-5 pairs | 30+ pairs | 6-7x short |
| Position bias | 1 ordering | 20+ orderings | 20x short |
| Reviewer calibration | N*(N-1) scores | 50+ scores/reviewer | ~3x short |

### Statistical Reality

- **Pearson correlation with n=5**: Even r=0.9 has p≈0.037 (barely significant)
- **Position variance with 1 ordering**: Cannot distinguish position effect from quality
- **Reviewer means with 4 scores**: High variance, unreliable characterization

The current per-session metrics are **indicators**, not **statistical proof**.

---

## Decision

### Status: Accepted with Modifications

The LLM Council unanimously approved cross-session aggregation as mathematically necessary, with key modifications to the implementation approach.

### Core Principle: Decouple Data Collection from Analysis

> "You cannot analyze data you haven't saved." — Council Consensus

The proposal is effectively **two projects**:
1. **Data Persistence** (implement now)
2. **Advanced Analysis** (defer until data exists)

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Council Session N                         │
├─────────────────────────────────────────────────────────────┤
│  Stage 1 → Stage 2 (with position randomization) → Stage 3  │
│      ↓                                                       │
│  Per-Session Bias Audit (ADR-015)                           │
│      ↓                                                       │
│  BiasMetricRecord (append to .jsonl)                        │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              bias_metrics.jsonl (Append-Only)                │
├─────────────────────────────────────────────────────────────┤
│  - One record per (session, model, reviewer) combination    │
│  - Rolling window: last 100 sessions or 30 days             │
│  - O(N) linear scan for aggregation                         │
│  - Schema versioned for future compatibility                │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│           Cross-Session Aggregation (Phase 2)                │
├─────────────────────────────────────────────────────────────┤
│  run_aggregated_bias_audit() →                              │
│    - Pooled length-score correlation with CIs               │
│    - Position bias with aggregated distributions            │
│    - Reviewer profiles (harshness z-scores)                 │
│    - Temporal trends (optional Phase 3)                     │
└─────────────────────────────────────────────────────────────┘
```

### Data Schema (JSONL Format)

```json
{
  "schema_version": 1,
  "session_id": "uuid",
  "timestamp": "2025-12-17T10:30:00Z",
  "reviewer_id": "google/gemini-3-pro-preview",
  "model_id": "anthropic/claude-opus-4.5",
  "position": 2,
  "response_length_chars": 1200,
  "score_value": 8.5,
  "score_scale": "1-10",
  "council_config_version": "0.3.0",
  "query_hash": null
}
```

**One record per (session, model, reviewer) combination** — enables fine-grained aggregation.

### Storage Format: JSONL (Not Individual JSON Files)

Per council recommendation, use **append-only JSONL** instead of one file per session:

```python
# bias_metrics.jsonl - append one line per record
{"schema_version": 1, "session_id": "abc", "reviewer_id": "gpt-4", ...}
{"schema_version": 1, "session_id": "abc", "reviewer_id": "claude-3", ...}
{"schema_version": 1, "session_id": "def", "reviewer_id": "gpt-4", ...}
```

**Benefits:**
- O(N) linear scan for aggregation (no file I/O hell with 100s of sessions)
- Atomic appends prevent corruption
- Human-readable and grep-able
- Easy export to analytics pipelines

### Configuration

```python
# config.py additions
BIAS_PERSISTENCE_ENABLED = os.getenv("LLM_COUNCIL_BIAS_PERSISTENCE", "false").lower() == "true"
BIAS_STORE_PATH = os.getenv("LLM_COUNCIL_BIAS_STORE", "~/.llm-council/bias_metrics.jsonl")
BIAS_WINDOW_SESSIONS = int(os.getenv("LLM_COUNCIL_BIAS_WINDOW_SESSIONS", "100"))
BIAS_WINDOW_DAYS = int(os.getenv("LLM_COUNCIL_BIAS_WINDOW_DAYS", "30"))
MIN_SESSIONS_FOR_AGGREGATION = int(os.getenv("LLM_COUNCIL_MIN_BIAS_SESSIONS", "20"))
```

---

## Council Review Feedback

**Reviewed:** 2025-12-17 (Gemini 3 Pro, Claude Opus 4.5, GPT-5.1)
**Grok 4:** Timeout (excluded from synthesis)

### Verdict: Accept with Modifications

All three responding models agreed cross-session aggregation is mathematically necessary but recommended significant implementation changes.

### Key Consensus Points

| Question | Council Consensus |
|----------|-------------------|
| **1. Approach** | Aggregation correct; also add per-session randomization now |
| **2. Minimum Sessions** | 20-30 soft floor; 50+ for robust insights; always show CIs |
| **3. Score Weighting** | **Do NOT alter live votes**; use profiles for analytics only |
| **4. Privacy** | Never store raw queries; salted hashes opt-in only |
| **5. Statistical Method** | Start frequentist; upgrade to Bayesian later |
| **6. Priority** | Implement persistence now; defer analysis UI |

### Critical Modifications Required

#### 1. Score Weighting: Analytics Only

> "Automatically modifying scores based on 'reviewer profiles' is a UX minefield. If a reviewer is 'harsh,' they might simply be the domain expert holding the standard high." — Gemini

**Decision:** Reviewer profiles inform a **"Calibrated View"** dashboard, not live council decisions.

```python
# CORRECT: Analytics/dashboard use
def get_normalized_scores_for_analytics(
    raw_scores: Dict[str, float],
    reviewer_profiles: Dict[str, ReviewerProfile]
) -> Dict[str, float]:
    """Z-score normalization for cross-reviewer comparison."""
    return {
        reviewer: (score - profiles[reviewer].mean) / profiles[reviewer].std
        for reviewer, score in raw_scores.items()
    }

# INCORRECT: Do not implement in v0.4.0
def weighted_council_vote(scores, profiles):  # NO - affects live decisions
    ...
```

#### 2. Privacy: No Raw Query Storage

> "Never store raw query text in bias records." — All models

**Decision:**
- Default: No query information stored
- Optional: Salted HMAC hash for similarity grouping (opt-in)
- Never: Raw query text or semantic embeddings

```python
class PrivacyLevel(Enum):
    STRICT = "strict"      # No query info (default)
    HASHED = "hashed"      # HMAC(secret, query) for grouping
    # FULL = "full"        # NOT IMPLEMENTED - privacy risk

def hash_query_if_enabled(query: str, privacy_level: PrivacyLevel) -> Optional[str]:
    if privacy_level == PrivacyLevel.STRICT:
        return None
    # HMAC with deployment-specific secret
    secret = os.getenv("LLM_COUNCIL_HASH_SECRET", "default-dev-secret")
    return hmac.new(secret.encode(), query[:100].encode(), hashlib.sha256).hexdigest()[:16]
```

#### 3. Storage Format: JSONL Not JSON

> "If you store one JSON file per session, you will face I/O hell when aggregating 100 sessions." — Gemini

**Decision:** Use `bias_metrics.jsonl` with append-only writes.

#### 4. Reporting Requirements

Every reported bias metric MUST include:
- **N** (sample size)
- **Point estimate**
- **95% Confidence Interval**
- **Data window** (time range)

```python
@dataclass
class BiasMetricReport:
    metric_name: str
    point_estimate: float
    ci_lower: float
    ci_upper: float
    sample_size: int
    window_start: datetime
    window_end: datetime
    statistical_confidence: str  # "insufficient", "preliminary", "moderate", "high"
```

#### 5. Tiered Confidence Display

| Sessions | Confidence Level | UI Treatment |
|----------|------------------|--------------|
| N < 10 | `insufficient_data` | "Collecting data..." (no metrics shown) |
| 10 ≤ N < 20 | `preliminary` | Show with "High Volatility" warning |
| 20 ≤ N < 50 | `moderate` | Show with confidence intervals |
| N ≥ 50 | `high` | Full metrics with narrow CIs |

---

## Implementation Phases (Revised)

### Phase 1: Data Persistence (v0.4.0) — Implement Now

> "Do NOT wait for explicit demand to implement Phase 1: once missed, that data can't be retroactively recovered." — GPT-5.1

**Scope:**
- Add `BiasMetricRecord` dataclass with schema versioning
- Implement JSONL append-only storage
- Store one record per (session, model, reviewer) combination
- Add `LLM_COUNCIL_BIAS_PERSISTENCE=true` config flag
- Ensure position randomization is logged

**Not in Phase 1:**
- Aggregation functions
- CLI commands
- Dashboard/visualization

### Phase 2: Basic Aggregation (v0.5.0) — When 500+ Records Exist

**Trigger:** Accumulated 500+ bias records in production

**Scope:**
- `run_aggregated_bias_audit()` function
- Pooled length-score correlation with CIs
- Basic reviewer profiles (mean, std, harshness z-score)
- CLI command: `llm-council bias-report`
- Tiered confidence display

### Phase 3: Advanced Analysis (v0.6.0+) — When Patterns Emerge

**Trigger:** Clear bias patterns identified in Phase 2 data

**Scope:**
- Bayesian updating for better uncertainty quantification
- Temporal trend detection (rolling windows)
- Position bias with cross-session position variation
- Optional: "Calibrated View" dashboard toggle
- Optional: Anomaly alerting

### Not Implementing (Explicitly Rejected)

| Feature | Reason |
|---------|--------|
| Live score weighting | Premature; risks penalizing expert reviewers |
| Raw query storage | Privacy violation |
| Semantic embeddings | Privacy and complexity |
| Per-session multiple randomizations | Cost prohibitive (3× API calls) |
| Real-time dashboard | Over-engineering for current scale |

---

## Licensing & Placement (Open Core Strategy)

**Reviewed:** 2025-12-18 (Gemini 3 Pro, Claude Opus 4.5, GPT-5.1, Grok 4)
**Verdict:** "Math vs. Map" — Algorithm stays open, infrastructure is commercial

### The Guiding Principle

> "If the algorithm knows how to calculate that 'GPT-4 is a harsh grader,' but the software refuses to tell the free user that result, you have paywalled the algorithm." — Council Consensus

**The Boundary:**
- **Algorithm (OSS)**: The *ability* to compute bias metrics, profiles, and trends
- **Infrastructure (Commercial)**: The *convenience* of hosted storage, dashboards, and team collaboration

### Placement by Component

| Component | Tier | Rationale |
|-----------|------|-----------|
| **Phase 1: Local JSONL persistence** | OSS | Local file I/O, no infrastructure cost |
| **Phase 2: Aggregation logic** (Pearson, Bayesian, z-scores) | OSS | Core algorithm — "the math" |
| **Phase 2: CLI reports** (`llm-council bias-report`) | OSS | Algorithm output, builds trust |
| **Phase 2: Reviewer profiles** (computation) | OSS | Statistical derivative, not infrastructure |
| **Phase 2: Reviewer profiles** (cloud UI) | Pro | Visualization convenience |
| **Phase 3: Cloud-hosted history** | Pro | Storage infrastructure cost |
| **Phase 3: Team/org-wide aggregation** | Enterprise | Multi-tenant infrastructure |
| **Phase 3: Temporal alerts & webhooks** | Enterprise | Monitoring infrastructure |
| **Phase 3: Compliance audit exports** | Enterprise | Governance feature |

### The "Friction Moat" Strategy

Use natural friction, not artificial code-gates:

| Tier | User Experience |
|------|-----------------|
| **OSS** | Run `llm-council bias-report --input ./logs.jsonl`. Manual, 15-second parse, text tables. Powerful but hands-on. |
| **Pro** | Log into web dashboard. Data already synced. Interactive graphs. Zero ops. |
| **Enterprise** | Team aggregation + audit logs + compliance exports + SSO |

### Marketing Positioning

- **OSS**: "The first mathematically rigorous, open-source bias auditor for your local LLM prompts."
- **Pro**: "Same open algorithms. We host and secure them for you."
- **Enterprise**: "Governance and bias monitoring for your entire AI engineering team."

### Honoring "The Open Promise"

This placement ensures:

1. **"Never paywall the algorithm"**: All bias computation (correlations, profiles, trends) runnable locally via OSS CLI
2. **"Monetize infrastructure, not intelligence"**: Cloud storage, dashboards, and team features are genuine infrastructure costs
3. **"Transparent telemetry"**: Users can audit their own data locally without cloud dependency

### Cross-Project Compatibility

**Reviewed:** 2025-12-18 (Gemini 3 Pro, Claude Opus 4.5, GPT-5.1, Grok 4)
**Verdict:** "Local Detail, Global Summary" — compatible with adjustments

#### Compatibility with council-cloud ADR-001 (Telemetry Architecture)

The council evaluated alignment between ADR-018 (bias aggregation) and council-cloud's ADR-001 (telemetry for leaderboard). Key findings:

| Aspect | ADR-018 (Bias) | ADR-001 (Telemetry) | Action Needed |
|--------|----------------|---------------------|---------------|
| **Granularity** | Per (session, model, reviewer) | Per session (aggregate) | Compatible — different purposes |
| **Schema version** | Integer (`1`) | Semver string (`"1.0"`) | **Align to semver** |
| **Query context** | None | Category, token bucket, language | **Add to ADR-018** |
| **Bias metrics** | Full detail | None | **Add summary to ADR-001** |
| **Privacy model** | `PrivacyLevel` enum | `ConsentLevel` (0-3) | **Unify on ConsentLevel** |

#### Required Schema Updates

**ADR-018 v1.1 — Add query_metadata and align versioning:**

```json
{
  "schema_version": "1.1.0",
  "session_id": "uuid",
  "timestamp": "2025-12-17T10:30:00Z",
  "consent_level": 1,

  "query_metadata": {
    "category": "coding",
    "token_count_bucket": "100-500",
    "language": "en"
  },

  "reviewer_id": "google/gemini-3-pro-preview",
  "model_id": "anthropic/claude-opus-4.5",
  "position": 2,
  "response_length_chars": 1200,
  "score_value": 8.5,
  "score_scale": "1-10",
  "council_config_version": "0.3.0",
  "query_hash": null
}
```

**ADR-001 — Add bias_indicators summary:**

```json
{
  "schema_version": "1.1.0",
  "event_id": "uuid-v4",
  "session_id": "uuid",

  "bias_indicators": {
    "position_variance": 0.23,
    "length_correlation": 0.12,
    "reviewer_agreement": 0.78,
    "flags": ["POSITION_BIAS_DETECTED"]
  },

  "rankings": [...],
  "query_metadata": {...}
}
```

#### Unified Consent Model

| Level | Name | Local Storage | Cloud Transmission |
|-------|------|---------------|-------------------|
| **0** | Off | Disabled | Disabled |
| **1** | Local Only | Enabled | Disabled |
| **2** | Anonymous | Enabled | Rankings only |
| **3** | Enhanced | Enabled | Rankings + bias summary |
| **4** | Research | Enabled | + query hashes |

#### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        llm-council (OSS)                                │
│                                                                         │
│   Council Session                                                       │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────┐                                                  │
│   │  Bias Computer  │ ◄─── ADR-018 algorithms (MIT)                    │
│   │  (local)        │                                                  │
│   └────────┬────────┘                                                  │
│            │                                                            │
│            ▼                                                            │
│   ~/.llm-council/bias_metrics.jsonl                                    │
│   [Fine-grained: per session/model/reviewer]                           │
│            │                                                            │
│            │ Aggregation (runs locally)                                │
│            ▼                                                            │
│   ┌─────────────────┐                                                  │
│   │ Bias Summary    │                                                  │
│   │ Generator       │                                                  │
│   └────────┬────────┘                                                  │
│            │                                                            │
└────────────┼────────────────────────────────────────────────────────────┘
             │
             │ If consent_level >= 2
             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      council-cloud (Commercial)                         │
│                                                                         │
│   POST /v1/events                                                      │
│   {                                                                     │
│     "bias_indicators": {...}  ◄─── Summary only, not raw data          │
│     "rankings": [...],                                                  │
│   }                                                                     │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────┐      ┌─────────────────┐                         │
│   │   Leaderboard   │      │  Bias Dashboard │ ◄─── Enterprise         │
│   │   (Pro tier)    │      │  (Enterprise)   │                         │
│   └─────────────────┘      └─────────────────┘                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Licensing Clarity

> "The bias computation algorithms in this ADR are MIT licensed. Users may compute, store, and analyze their own bias metrics without restriction. Cross-user aggregation and comparative analysis services are provided by council-cloud under separate commercial terms."

---

## Alternatives Considered

### Alternative 1: Richer Per-Session Analysis

Run each query through the council multiple times with different randomizations.

**Rejected:**
- 3× cost multiplier per query
- Impractical for real-time use
- Council agreed: "Brings a bazooka to a knife fight"

### Alternative 2: Bayesian Updating from Day 1

Use Bayesian priors that update with each session.

**Deferred to Phase 3:**
- Adds implementation complexity
- Frequentist pooling sufficient for MVP
- Can be layered on later without schema changes

### Alternative 3: External Analytics Pipeline

Export to DataDog, Prometheus, etc.

**Considered for Enterprise:**
- Good for production deployments
- Phase 2 data export could feed external systems
- Not required for core functionality

---

## Model Drift Consideration

> "Aggregating 'GPT-4' performance over 6 months is statistically invalid if the underlying model version changed." — Gemini

**Mitigation:**
- Store `council_config_version` in each record
- Aggregation uses time windows (default 30 days)
- Filter by model version string when analyzing
- Phase 3: Change-point detection for model updates

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Storage overhead | < 1KB per session |
| Aggregation latency | < 100ms for 1000 sessions |
| Pooled correlation significance | p < 0.05 achievable at 30+ sessions |
| Reviewer profiles stability | < 0.5 std deviation drift after 20+ sessions |
| False positive rate for bias detection | < 5% |

---

## Implementation Status

**Implementation Date:** 2025-12-18
**Version:** v0.4.0-dev
**Tests:** 74 passing (44 Phase 1 + 30 Phase 2-3)

### Phase 1: Data Persistence - COMPLETE

| Component | Status | Location |
|-----------|--------|----------|
| `BiasMetricRecord` dataclass | Implemented | `src/llm_council/bias_persistence.py` |
| `ConsentLevel` enum (0-4) | Implemented | `src/llm_council/bias_persistence.py` |
| JSONL append/read operations | Implemented | `src/llm_council/bias_persistence.py` |
| Session-to-records conversion | Implemented | `src/llm_council/bias_persistence.py` |
| Query hashing (RESEARCH consent) | Implemented | `src/llm_council/bias_persistence.py` |
| Config variables | Implemented | `src/llm_council/config.py` |

### Phase 2: Basic Aggregation - COMPLETE

| Component | Status | Location |
|-----------|--------|----------|
| Fisher z-transform utilities | Implemented | `src/llm_council/bias_aggregation.py` |
| `StatisticalConfidence` enum | Implemented | `src/llm_council/bias_aggregation.py` |
| Pooled correlation with CIs | Implemented | `src/llm_council/bias_aggregation.py` |
| Reviewer profiles (harshness z-scores) | Implemented | `src/llm_council/bias_aggregation.py` |
| Position bias aggregation | Implemented | `src/llm_council/bias_aggregation.py` |
| `run_aggregated_bias_audit()` | Implemented | `src/llm_council/bias_aggregation.py` |
| CLI `bias-report` command | Implemented | `src/llm_council/cli.py` |

### Phase 3: Advanced Analysis - COMPLETE

| Component | Status | Location |
|-----------|--------|----------|
| Temporal trend detection | Implemented | `src/llm_council/bias_aggregation.py` |
| Anomaly detection | Implemented | `src/llm_council/bias_aggregation.py` |

### Configuration Options

```bash
# Enable bias persistence (default: false)
LLM_COUNCIL_BIAS_PERSISTENCE=true

# Store path (default: ~/.llm-council/bias_metrics.jsonl)
LLM_COUNCIL_BIAS_STORE=/path/to/metrics.jsonl

# Rolling window: sessions (default: 100)
LLM_COUNCIL_BIAS_WINDOW_SESSIONS=100

# Rolling window: days (default: 30)
LLM_COUNCIL_BIAS_WINDOW_DAYS=30

# Minimum sessions for aggregation (default: 20)
LLM_COUNCIL_MIN_BIAS_SESSIONS=20

# Consent level: 0-4 (default: 1 = LOCAL_ONLY)
LLM_COUNCIL_BIAS_CONSENT=1

# Hash secret for RESEARCH consent (default: dev secret)
LLM_COUNCIL_HASH_SECRET=your-deployment-secret
```

### CLI Usage

```bash
# Generate text report
llm-council bias-report

# Generate JSON report
llm-council bias-report --format json

# Limit to last 50 sessions
llm-council bias-report --sessions 50

# Include detailed reviewer profiles
llm-council bias-report --verbose

# Custom input path
llm-council bias-report --input /path/to/metrics.jsonl
```

---

## Cross-ADR Dependencies

```
ADR-015 (Per-Session Bias Auditing)
    │
    ├──► ADR-018 (Cross-Session Aggregation) ← THIS ADR
    │        │
    │        └──► Requires position data from ADR-017
    │
    └──► ADR-017 (Position Randomization)
             │
             └──► Position data stored in BiasMetricRecord
```

---

## References

- ADR-015: Bias Auditing (per-session implementation)
- ADR-017: Response Order Randomization (position tracking)
- [Statistical Power Analysis](https://www.statisticshowto.com/probability-and-statistics/statistics-definitions/statistical-power/)
- [Fisher's z-transformation](https://en.wikipedia.org/wiki/Fisher_transformation) for correlation confidence intervals
- Council Review: 2025-12-17 (Gemini 3 Pro, Claude Opus 4.5, GPT-5.1)
