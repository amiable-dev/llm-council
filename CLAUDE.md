# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Contains `COUNCIL_MODELS` (list of OpenRouter model identifiers)
- Contains `CHAIRMAN_MODEL` (model that synthesizes final answer)
- **ADR-022**: Contains `TIER_MODEL_POOLS` and `DEFAULT_TIER_MODEL_POOLS` for per-tier model selection
- `get_tier_models(tier)`: Returns models for a tier, with env var override support
- Uses environment variable `OPENROUTER_API_KEY` from `.env`
- Backend runs on **port 8001** (NOT 8000 - user had another app on 8000)

**`tier_contract.py`** - ADR-022 Tier Contract
- `TierContract`: Frozen dataclass defining tier execution parameters
  - `tier`: Confidence level (quick|balanced|high|reasoning)
  - `deadline_ms`, `per_model_timeout_ms`: Timeout configuration
  - `token_budget`, `max_attempts`: Resource limits
  - `requires_peer_review`, `requires_verifier`: Stage flags
  - `allowed_models`, `aggregator_model`: Model configuration
  - `override_policy`: Escalation rules
- `create_tier_contract(tier)`: Factory function to create contracts
- `TIER_AGGREGATORS`: Speed-matched aggregator models per tier
- `DEFAULT_TIER_CONTRACTS`: Pre-built contracts for all tiers

**`unified_config.py`** - ADR-024 Unified YAML Configuration
- Single source of truth consolidating ADR-020, ADR-022, ADR-023 settings
- Pydantic-based schema with validation
- **Main Classes**:
  - `UnifiedConfig`: Root configuration with tiers, triage, gateways
  - `TierConfig`: Tier pools, defaults, escalation settings
  - `TriageConfig`: Wildcard, prompt optimization, fast path settings
  - `GatewayConfig`: Default gateway, providers, model routing, fallback chain
- **Key Functions**:
  - `load_config(path)`: Load from YAML file with validation
  - `get_effective_config()`: Get config with env var overrides applied
  - `get_config()`, `reload_config()`: Global configuration management
- **Configuration Priority**: YAML file > Environment variables > Defaults
- **YAML File Locations** (searched in order):
  1. `LLM_COUNCIL_CONFIG` environment variable
  2. `./llm_council.yaml` (current directory)
  3. `~/.config/llm-council/llm_council.yaml`
- **Environment Variable Substitution**: Supports `${VAR_NAME}` syntax in YAML

**`layer_contracts.py`** - ADR-024 Layer Interface Contracts
- Formalizes L1→L2→L3→L4 layer boundaries with validation and observability
- **Re-exports all layer interface types**:
  - L1: `TierContract`, `create_tier_contract`
  - L2: `TriageResult`, `TriageRequest`, `DomainCategory`, `WildcardConfig`
  - L4: `GatewayRequest`, `GatewayResponse`, `CanonicalMessage`, `ContentBlock`
- **Validation Functions**:
  - `validate_tier_contract()`, `validate_triage_result()`, `validate_gateway_request()`
  - `validate_l1_to_l2_boundary()`, `validate_l2_to_l3_boundary()`, `validate_l3_to_l4_boundary()`
- **Observability Hooks**:
  - `LayerEventType`: Enum with L1/L2/L3/L4 event types
  - `LayerEvent`: Dataclass with event_type, data, timestamp
  - `emit_layer_event()`, `get_layer_events()`, `clear_layer_events()`
- **Boundary Crossing Helpers** (validate + emit event):
  - `cross_l1_to_l2(contract, query)` - L1→L2 with L1_TIER_SELECTED event
  - `cross_l2_to_l3(result, tier_contract)` - L2→L3 with L2_TRIAGE_COMPLETE event
  - `cross_l3_to_l4(request)` - L3→L4 with L4_GATEWAY_REQUEST event
- **Architectural Principles** (per ADR-024):
  - Layer Sovereignty: Each layer owns its decision
  - Explicit Escalation: All escalations logged and auditable
  - Failure Isolation: Gateway failures don't cascade to tier changes
  - Constraint Propagation: Tier constraints flow down
  - Observability by Default: Every layer emits events

**`triage/`** - ADR-020 Query Triage Layer
- **`types.py`**: Core types for triage
  - `TriageResult`: resolved_models, optimized_prompts, fast_path, escalation fields
  - `TriageRequest`: query with optional tier_contract and domain_hint
  - `WildcardConfig`: specialist pools, fallback model, diversity constraints
  - `DomainCategory`: CODE, REASONING, CREATIVE, MULTILINGUAL, GENERAL
  - `DEFAULT_SPECIALIST_POOLS`: Per-domain model recommendations
- **`wildcard.py`**: Domain-specialized model selection
  - `classify_query_domain()`: Keyword-based domain classification
  - `select_wildcard()`: Select specialist from pool with diversity constraints
- **`prompt_optimizer.py`**: Per-model prompt adaptation
  - `PromptOptimizer`: Applies provider-specific formatting (Claude XML, etc.)
  - `get_model_provider()`: Extract provider from model ID
- **`complexity.py`**: Complexity classification (placeholder)
  - `HeuristicComplexityClassifier`: Keyword/length-based heuristics
  - `NotDiamondClassifier`: Placeholder for future integration
  - `classify_complexity()`: Entry point for complexity classification
- **`__init__.py`**: Exports `run_triage()` entry point
- Configuration: `WILDCARD_ENABLED`, `PROMPT_OPTIMIZATION_ENABLED`

**`openrouter.py`**
- `query_model()`: Single async model query
- `query_models_parallel()`: Parallel queries using `asyncio.gather()`
- Returns dict with 'content' and optional 'reasoning_details'
- Graceful degradation: returns None on failure, continues with successful responses

**`council.py`** - The Core Logic
- `stage1_collect_responses()`: Parallel queries to all council models
- `stage2_collect_rankings()`:
  - Anonymizes responses as "Response A, B, C, etc."
  - Creates `label_to_model` mapping for de-anonymization
  - Prompts models to evaluate and rank (with strict format requirements)
  - Returns tuple: (rankings_list, label_to_model_dict)
  - Each ranking includes both raw text and `parsed_ranking` list
  - **ADR-016**: When `RUBRIC_SCORING_ENABLED=true`, uses multi-dimensional rubric prompt
- `stage3_synthesize_final()`: Chairman synthesizes from all responses + rankings
- `parse_ranking_from_text()`: Extracts "FINAL RANKING:" section, handles both numbered lists and plain format
- `calculate_aggregate_rankings()`: Computes average rank position across all peer evaluations

**`rubric.py`** - ADR-016 Structured Rubric Scoring
- `RubricScore`: Dataclass for multi-dimensional scores (accuracy, relevance, completeness, conciseness, clarity)
- `calculate_weighted_score()`: Weighted average from dimension scores
- `calculate_weighted_score_with_accuracy_ceiling()`: Weighted score with accuracy acting as ceiling
  - Accuracy < 5: caps at 4.0 ("significant errors or worse" per scoring anchors)
  - Accuracy 5-6: caps at 7.0 ("mixed accuracy")
  - Accuracy ≥ 7: no ceiling ("mostly accurate or better")
  - **Rationale**: Prevents confident lies from ranking well; thresholds map to scoring anchor definitions
- `parse_rubric_evaluation()`: Extracts rubric JSON from model response, handles code blocks
- `validate_weights()`: Ensures weights sum to 1.0 and include all dimensions
- **Fallback**: If rubric parsing fails, falls back to holistic scoring via `parse_ranking_from_text()`
- **Scoring Anchors**: Defined in ADR-016 with behavioral examples for each score level (1-10)

**`safety_gate.py`** - ADR-016 Safety Gate
- `SafetyCheckResult`: Dataclass with passed, reason, flagged_patterns
- `check_response_safety()`: Scans response for harmful patterns
- `apply_safety_gate_to_score()`: Caps score if safety check fails
- **Patterns detected**: dangerous_instructions, weapon_making, malware_hacking, self_harm, pii_exposure
- **Context-aware**: Exclusion contexts allow educational/defensive content
- Configuration in `config.py`: `SAFETY_GATE_ENABLED`, `SAFETY_SCORE_CAP`

**`bias_audit.py`** - ADR-015 Per-Session Bias Indicators
- `BiasAuditResult`: Dataclass containing all bias metrics
- `calculate_length_correlation()`: Pure Python Pearson correlation (no scipy/numpy)
- `audit_reviewer_calibration()`: Detects harsh/generous reviewers (mean ± 1 std from median)
- `calculate_position_bias()`: Detects position effects in scoring
- `derive_position_mapping()`: Converts `label_to_model` → position indices
  - Supports enhanced format (v0.3.0+): Uses `display_index` directly
  - Supports legacy format: Derives from label letter (A → 0, B → 1)
- `run_bias_audit()`: Main entry point, runs all bias checks and returns overall risk assessment
- `extract_scores_from_stage2()`: Converts Stage 2 results to format needed for bias audit
- Configuration in `config.py`: `BIAS_AUDIT_ENABLED`, `LENGTH_CORRELATION_THRESHOLD`, `POSITION_VARIANCE_THRESHOLD`

**Statistical Limitations**: Per-session bias auditing has inherent limitations with small sample sizes:
- With N=4-5 models, length correlation has only 4-5 data points (minimum 30+ needed for significance)
- Position bias from a single ordering cannot distinguish position effects from quality differences
- Reviewer calibration is relative to the current session only, not across sessions
- These metrics are **indicators for extreme anomalies**, not statistically robust proof of systematic bias

**`bias_persistence.py`** - ADR-018 Phase 1: Data Persistence
- `BiasMetricRecord`: Dataclass for individual bias measurements (schema version 1.1.0)
- `ConsentLevel`: Enum for privacy consent levels (OFF=0, LOCAL_ONLY=1, ANONYMOUS=2, ENHANCED=3, RESEARCH=4)
- `hash_query_if_enabled()`: HMAC hash for query grouping (RESEARCH consent only)
- `append_bias_records()`: Atomic JSONL append
- `read_bias_records()`: Read with filtering (max_sessions, max_days, since)
- `create_bias_records_from_session()`: Convert Stage 2 results to records
- `persist_session_bias_data()`: High-level integration point for council.py
- Configuration in `config.py`: `BIAS_PERSISTENCE_ENABLED`, `BIAS_STORE_PATH`, etc.

**`bias_aggregation.py`** - ADR-018 Phase 2-3: Cross-Session Analysis
- `StatisticalConfidence`: Enum for confidence tiers (INSUFFICIENT, PRELIMINARY, MODERATE, HIGH)
- `fisher_z_transform()` / `inverse_fisher_z()`: Fisher z-transformation for correlation CIs
- `determine_confidence_level()`: Map sample size to confidence tier
- `pooled_correlation_with_ci()`: Pooled length-score correlation with 95% CI
- `aggregate_reviewer_profiles()`: Per-reviewer mean, std, harshness z-score
- `aggregate_position_bias()`: Variance of position means
- `run_aggregated_bias_audit()`: Main entry point for cross-session analysis
- `generate_bias_report_text()` / `generate_bias_report_json()`: CLI report generation
- `detect_temporal_trends()`: Phase 3 - rolling window trend detection
- `detect_anomalies()`: Phase 3 - outlier session flagging

**CLI (`cli.py`) - bias-report command**
```bash
llm-council bias-report [--input FILE] [--sessions N] [--days N] [--format text|json] [--verbose]
```

**Enhanced `label_to_model` Format (v0.3.0+)**
Per council recommendation for robustness, anonymization now uses explicit position indices:
```python
# Enhanced format (eliminates string parsing fragility)
{"Response A": {"model": "openai/gpt-4", "display_index": 0}, ...}

# INVARIANT: Labels are assigned in lexicographic order (A=0, B=1, etc.)
```

**`storage.py`**
- JSON-based conversation storage in `data/conversations/`
- Each conversation: `{id, created_at, messages[]}`
- Assistant messages contain: `{role, stage1, stage2, stage3}`
- Note: metadata (label_to_model, aggregate_rankings) is NOT persisted to storage, only returned via API

**`main.py`**
- FastAPI app with CORS enabled for localhost:5173 and localhost:3000
- POST `/api/conversations/{id}/message` returns metadata in addition to stages
- Metadata includes: label_to_model mapping and aggregate_rankings

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Main orchestration: manages conversations list and current conversation
- Handles message sending and metadata storage
- Important: metadata is stored in the UI state for display but not persisted to backend JSON

**`components/ChatInterface.jsx`**
- Multiline textarea (3 rows, resizable)
- Enter to send, Shift+Enter for new line
- User messages wrapped in markdown-content class for padding

**`components/Stage1.jsx`**
- Tab view of individual model responses
- ReactMarkdown rendering with markdown-content wrapper

**`components/Stage2.jsx`**
- **Critical Feature**: Tab view showing RAW evaluation text from each model
- De-anonymization happens CLIENT-SIDE for display (models receive anonymous labels)
- Shows "Extracted Ranking" below each evaluation so users can validate parsing
- Aggregate rankings shown with average position and vote count
- Explanatory text clarifies that boldface model names are for readability only

**`components/Stage3.jsx`**
- Final synthesized answer from chairman
- Green-tinted background (#f0fff0) to highlight conclusion

**Styling (`*.css`)**
- Light mode theme (not dark mode)
- Primary color: #4a90e2 (blue)
- Global markdown styling in `index.css` with `.markdown-content` class
- 12px padding on all markdown content to prevent cluttered appearance

## Key Design Decisions

### Stage 2 Prompt Format
The Stage 2 prompt is very specific to ensure parseable output:
```
1. Evaluate each response individually first
2. Provide "FINAL RANKING:" header
3. Numbered list format: "1. Response C", "2. Response A", etc.
4. No additional text after ranking section
```

This strict format allows reliable parsing while still getting thoughtful evaluations.

### De-anonymization Strategy
- Models receive: "Response A", "Response B", etc.
- Backend creates mapping: `{"Response A": "openai/gpt-5.1", ...}`
- Frontend displays model names in **bold** for readability
- Users see explanation that original evaluation used anonymous labels
- This prevents bias while maintaining transparency

### Error Handling Philosophy
- Continue with successful responses if some models fail (graceful degradation)
- Never fail the entire request due to single model failure
- Log errors but don't expose to user unless all models fail

### UI/UX Transparency
- All raw outputs are inspectable via tabs
- Parsed rankings shown below raw text for validation
- Users can verify system's interpretation of model outputs
- This builds trust and allows debugging of edge cases

## Important Implementation Details

### Relative Imports
All backend modules use relative imports (e.g., `from .config import ...`) not absolute imports. This is critical for Python's module system to work correctly when running as `python -m backend.main`.

### Port Configuration
- Backend: 8001 (changed from 8000 to avoid conflict)
- Frontend: 5173 (Vite default)
- Update both `backend/main.py` and `frontend/src/api.js` if changing

### Markdown Rendering
All ReactMarkdown components must be wrapped in `<div className="markdown-content">` for proper spacing. This class is defined globally in `index.css`.

### Model Configuration
Models are hardcoded in `backend/config.py`. Chairman can be same or different from council members. The current default is Gemini as chairman per user preference.

## Common Gotchas

1. **Module Import Errors**: Always run backend as `python -m backend.main` from project root, not from backend directory
2. **CORS Issues**: Frontend must match allowed origins in `main.py` CORS middleware
3. **Ranking Parse Failures**: If models don't follow format, fallback regex extracts any "Response X" patterns in order
4. **Missing Metadata**: Metadata is ephemeral (not persisted), only available in API responses

## Future Enhancement Ideas

- Configurable council/chairman via UI instead of config file
- Streaming responses instead of batch loading
- Export conversations to markdown/PDF
- Model performance analytics over time
- Custom ranking criteria (not just accuracy/insight)
- Support for reasoning models (o1, etc.) with special handling

## Testing Notes

Use `test_openrouter.py` to verify API connectivity and test different model identifiers before adding to council. The script tests both streaming and non-streaming modes.

## Data Flow Summary

```
User Query
    ↓
Stage 1: Parallel queries → [individual responses]
    ↓
Stage 1.5 (optional): Style normalization
    ↓
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings]
    ↓
Aggregate Rankings Calculation → [sorted by Borda score]
    ↓
Bias Audit (if enabled): Per-session indicators (length correlation, reviewer calibration, position bias)
    ↓
Stage 3: Chairman synthesis with full context
    ↓
Return: {stage1, stage2, stage3, metadata (including bias_audit if enabled)}
    ↓
Frontend: Display with tabs + validation UI
```

The entire flow is async/parallel where possible to minimize latency.
