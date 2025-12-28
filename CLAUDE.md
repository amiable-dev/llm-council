# CLAUDE.md - Technical Notes for LLM Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Architecture

### Backend Structure (`backend/`)

**`tier_contract.py`** - ADR-022 Tier Contract
- `TierContract`: Frozen dataclass defining tier execution parameters
  - `tier`: Confidence level (quick|balanced|high|reasoning)
  - `deadline_ms`, `per_model_timeout_ms`: Timeout configuration
  - `token_budget`, `max_attempts`: Resource limits
  - `requires_peer_review`, `requires_verifier`: Stage flags
  - `allowed_models`, `aggregator_model`: Model configuration
  - `override_policy`: Escalation rules
- `create_tier_contract(tier, task_domain)`: Factory function to create contracts
  - **ADR-026**: Now accepts optional `task_domain` parameter for dynamic selection
  - Uses `select_tier_models()` when `LLM_COUNCIL_MODEL_INTELLIGENCE=true`
- `TIER_AGGREGATORS`: Speed-matched aggregator models per tier
- `DEFAULT_TIER_CONTRACTS`: Pre-built contracts for all tiers

**`metadata/`** - ADR-026 Model Intelligence Layer
- Provides model metadata abstraction for the Model Intelligence Layer
- Supports offline operation (StaticRegistryProvider) and dynamic metadata (DynamicMetadataProvider)

- **`types.py`**: Core types
  - `ModelInfo`: Frozen dataclass with id, context_window, pricing, modalities, quality_tier
  - `QualityTier`: Enum (FRONTIER, STANDARD, ECONOMY, LOCAL)
  - `Modality`: Enum (TEXT, VISION, AUDIO, etc.)
  - `ModelStatus`: Enum (AVAILABLE, DEPRECATED, PREVIEW, BETA) - ADR-028
- **`protocol.py`**: `MetadataProvider` Protocol (interface)
  - `get_model_info()`, `get_context_window()`, `get_pricing()`
  - `supports_reasoning()`, `list_available_models()`
- **`static_registry.py`**: `StaticRegistryProvider` (31 models from YAML)
  - Offline-safe provider using bundled registry + LiteLLM fallback
  - Registry at `src/llm_council/models/registry.yaml`
- **`dynamic_provider.py`**: `DynamicMetadataProvider` (ADR-026 Phase 1)
  - Fetches metadata from OpenRouter API with TTL caching
  - Falls back to StaticRegistryProvider when cache empty or offline
- **`cache.py`**: TTL caching infrastructure
  - `TTLCache`: Thread-safe cache with LRU eviction
  - `ModelIntelligenceCache`: Composite (registry 1hr, availability 5min TTL)
- **`openrouter_client.py`**: Async OpenRouter API client
  - `fetch_models()`: Fetches model metadata from OpenRouter
  - `transform_api_model()`: Transforms API response to ModelInfo
- **`selection.py`**: Tier selection algorithm (ADR-026 Phase 1)
  - `TIER_WEIGHTS`: Per-tier weight matrices (quick→latency, reasoning→quality)
  - `QUALITY_TIER_SCORES`: QualityTier → float mapping (ADR-030 benchmark-justified):
    - FRONTIER: 0.95 (MMLU 87-90%)
    - STANDARD: 0.85 (MMLU 80-86%, +0.10 from 0.75)
    - ECONOMY: 0.70 (MMLU 70-79%, +0.15 from 0.55)
    - LOCAL: 0.50 (MMLU 55-80%, +0.10 from 0.40)
  - `COST_REFERENCE_HIGH`: Reference price for cost normalization (0.015 per 1K tokens)
  - `ModelCandidate`: Dataclass for model scoring
  - `apply_anti_herding_penalty()`: Penalizes models with >30% traffic
  - `select_with_diversity()`: Enforces provider diversity (min 2 providers)
  - `select_tier_models()`: Main entry point for dynamic selection
  - **Metadata Integration Functions** (ADR-026 Phase 1 "Hollow" Fix):
    - `_get_provider_safe()`: Get provider without crashing (returns None on failure)
    - `_get_quality_score_from_metadata()`: Real QualityTier lookup (not regex)
    - `_get_cost_score_from_metadata()`: Real pricing data (not regex)
    - `_meets_context_requirement()`: Real context window filtering (not always True)
  - **Circuit Breaker Integration** (ADR-030):
    - `_is_circuit_breaker_enabled()`: Check if circuit breaker is enabled (env > config > default)
    - `_is_circuit_breaker_open(model_id)`: Check if model's circuit is open
    - `select_tier_models()` filters out models with open circuit breakers
- **`scoring.py`**: Cost scoring algorithms (ADR-030)
  - `MIN_PRICE`: Floor to avoid log(0) ($0.0001)
  - `CostScaleAlgorithm`: Literal["linear", "log_ratio", "exponential"]
  - `get_cost_score_log_ratio()`: Log-ratio scoring for exponential price differences
  - `get_cost_score_exponential()`: Exponential decay scoring
  - `get_cost_score_with_config()`: Uses algorithm from config/env var
  - `QUALITY_TIER_BENCHMARK_SOURCES`: Citation URLs for quality tier justification
- **`offline.py`**: Offline mode detection
  - `is_offline_mode()`: Checks `LLM_COUNCIL_OFFLINE` env var
- **`registry.py`**: ADR-028 Model Registry (Background Registry Pattern)
  - `ModelRegistry`: Thread-safe singleton cache with asyncio.Lock
  - `RegistryEntry`: Cached model info with timestamp
  - `get_registry()`: Singleton factory
  - `refresh_registry()`: Background refresh with stale-while-revalidate
  - `get_candidates()`: Read-only access for request-time filtering
  - `get_health_status()`: Health check for observability
- **`worker.py`**: ADR-028 Background Discovery Worker
  - `run_discovery_worker()`: Periodic registry refresh task
  - Exponential backoff on failures
  - Graceful shutdown via asyncio.Event
- **`discovery.py`**: ADR-028 Request-Time Discovery
  - `discover_tier_candidates()`: In-memory filtering from cached registry
  - `_model_qualifies_for_tier()`: Tier-specific qualification logic
  - `KNOWN_REASONING_FAMILIES`: Set of reasoning model families
  - `_merge_deduplicate()`: Merge dynamic and static candidates
  - `emit_discovery_fallback()`: Emit fallback events
- **`startup.py`**: ADR-028 Application Lifecycle Hooks
  - `start_discovery_worker()`: Start worker at app startup
  - `stop_discovery_worker()`: Graceful shutdown
  - `get_worker_status()`: Health check for worker state
- **`__init__.py`**: `get_provider()` singleton factory
  - Returns `StaticRegistryProvider` by default
  - Returns `DynamicMetadataProvider` when `LLM_COUNCIL_MODEL_INTELLIGENCE=true`
  - Offline mode (`LLM_COUNCIL_OFFLINE=true`) forces static provider
  - ADR-028 exports: `get_registry`, `discover_tier_candidates`, lifecycle hooks

**Environment Variables (ADR-026):**
- `LLM_COUNCIL_MODEL_INTELLIGENCE=true`: Enable dynamic model selection
- `LLM_COUNCIL_OFFLINE=true`: Force offline mode (static provider only)

**Environment Variables (ADR-028 Discovery):**
- `LLM_COUNCIL_DISCOVERY_ENABLED=true`: Enable background discovery
- `LLM_COUNCIL_DISCOVERY_INTERVAL=300`: Refresh interval in seconds
- `LLM_COUNCIL_DISCOVERY_MIN_CANDIDATES=3`: Minimum candidates before fallback

**`performance/`** - ADR-026 Phase 3: Internal Performance Tracking
- Tracks model performance from actual council sessions
- Builds Internal Performance Index for quality scoring in model selection

- **`types.py`**: Core types
  - `ModelSessionMetric`: Per-session per-model performance data (session_id, model_id, latency_ms, borda_score, parse_success)
  - `ModelPerformanceIndex`: Aggregated performance (mean_borda_score, p50/p95_latency_ms, parse_success_rate, confidence_level)
- **`store.py`**: JSONL persistence (follows bias_persistence.py pattern)
  - `append_performance_records()`: Atomic append to JSONL file
  - `read_performance_records()`: Read with max_days and model_id filtering
- **`tracker.py`**: Main tracker class
  - `InternalPerformanceTracker`: Aggregates metrics with exponential decay
  - `record_session()`: Record metrics from completed council session
  - `get_model_index()`: Get aggregated ModelPerformanceIndex
  - `get_quality_score()`: Get 0-100 normalized score for selection.py
- **`integration.py`**: Council integration
  - `persist_session_performance_data()`: Extract and persist session metrics
  - `get_tracker()`: Singleton factory for tracker
- **`__init__.py`**: Module exports

**Performance Tracking Environment Variables:**
- `LLM_COUNCIL_PERFORMANCE_TRACKING`: Enable/disable (default: true)
- `LLM_COUNCIL_PERFORMANCE_STORE`: Custom store path

**Confidence Levels (sample size thresholds):**
- INSUFFICIENT: <10 samples
- PRELIMINARY: 10-30 samples
- MODERATE: 30-100 samples
- HIGH: 100+ samples

**`unified_config.py`** - ADR-024 Unified YAML Configuration
- Single source of truth consolidating ADR-020, ADR-022, ADR-023, ADR-026 settings
- Pydantic-based schema with validation
- **Main Classes**:
  - `UnifiedConfig`: Root configuration with tiers, triage, gateways, model_intelligence, evaluation
  - `TierConfig`: Tier pools, defaults, escalation settings
  - `TriageConfig`: Wildcard, prompt optimization, fast path settings
  - `GatewayConfig`: Default gateway, providers, model routing, fallback chain
  - `ModelIntelligenceConfig` (ADR-026): Dynamic model selection settings
    - `enabled`: Whether dynamic selection is active (default: false)
    - `refresh`: Cache TTL settings (registry_ttl, availability_ttl)
    - `selection`: Selection algorithm settings (min_providers, default_count)
    - `anti_herding`: Traffic concentration prevention (enabled, threshold, penalty)
  - `EvaluationConfig` (ADR-031): Evaluation-time settings for scoring, safety, and bias
    - `rubric`: RubricConfig (enabled, weights with validation)
    - `safety`: SafetyConfig (enabled, score_cap)
    - `bias`: BiasConfig (audit_enabled, persistence_enabled, thresholds, store_path, consent_level)
    - `scoring` (ADR-030): Cost scoring algorithm configuration
      - `cost_scale`: "linear" | "log_ratio" | "exponential" (default: "log_ratio")
      - `cost_reference_high`: Reference expensive price (default: 0.015)
    - `circuit_breaker` (ADR-030): Per-model circuit breaker configuration
      - `enabled`: Enable circuit breaker (default: true)
      - `failure_threshold`: Failure rate to trip (default: 0.25)
      - `min_requests`: Min requests before evaluation (default: 5)
      - `window_seconds`: Sliding window size (default: 600)
      - `cooldown_seconds`: Cooldown when open (default: 1800)
      - `half_open_max_requests`: Probe requests (default: 3)
      - `half_open_success_threshold`: Success rate to close (default: 0.67)
    - `audition` (ADR-029): Model audition configuration
      - `enabled`: Enable audition mechanism (default: true)
      - `max_audition_seats`: Max audition models per session (default: 1)
      - `shadow`/`probation`/`evaluation`/`quarantine`: Phase-specific settings
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
- **EvaluationConfig Environment Variables** (ADR-031):
  - `RUBRIC_SCORING_ENABLED`: Enable rubric-based scoring
  - `SAFETY_GATE_ENABLED`: Enable safety gate
  - `BIAS_AUDIT_ENABLED`: Enable per-session bias auditing
  - `BIAS_PERSISTENCE_ENABLED`: Enable cross-session bias persistence

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
  - `LayerEventType`: Enum with L1/L2/L3/L4/Discovery event types
  - `LayerEvent`: Dataclass with event_type, data, timestamp
  - `emit_layer_event()`, `get_layer_events()`, `clear_layer_events()`
- **Discovery Events (ADR-028)**:
  - `DISCOVERY_REFRESH_STARTED`: Emitted when registry refresh begins
  - `DISCOVERY_REFRESH_COMPLETE`: Emitted on successful refresh with duration_ms
  - `DISCOVERY_REFRESH_FAILED`: Emitted on refresh failure with error details
  - `DISCOVERY_FALLBACK_TRIGGERED`: Emitted when static fallback is used
  - `DISCOVERY_STALE_SERVE`: Emitted when serving stale data after failures
- **Circuit Breaker Events (ADR-030)**:
  - `L4_CIRCUIT_BREAKER_OPEN`: Emitted when circuit trips (model_id, failure_rate, cooldown_seconds)
  - `L4_CIRCUIT_BREAKER_CLOSE`: Emitted when circuit closes after recovery (model_id, from_state)
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

**`gateway/circuit_breaker.py`** - ADR-023/ADR-030 Circuit Breaker Implementation
- Prevents cascading failures by temporarily blocking requests to failing models
- **`CircuitState`**: Enum (CLOSED, OPEN, HALF_OPEN)
- **`CircuitBreaker`**: Basic circuit breaker with absolute failure count (ADR-023)
- **`EnhancedCircuitBreakerConfig`** (ADR-030):
  - `failure_threshold`: 0.25 (25% failure rate)
  - `min_requests`: 5 (minimum before evaluation)
  - `window_seconds`: 600 (10 minute sliding window)
  - `cooldown_seconds`: 1800 (30 minute cooldown)
  - `half_open_max_requests`: 3 (probe requests)
  - `half_open_success_threshold`: 0.67 (2/3 success to close)
- **`EnhancedCircuitBreaker`** (ADR-030):
  - Sliding window failure tracking with timestamp-based pruning
  - `failure_rate()`: Current failure rate in window
  - `request_count_in_window()`: Total requests in window
  - `failure_count_in_window()`: Failed requests in window
  - `allow_request()`: Check if request allowed (handles OPEN→HALF_OPEN transition)
  - `record_success()` / `record_failure()`: Track request outcomes

**`gateway/circuit_breaker_registry.py`** - ADR-030 Per-Model Circuit Breaker Registry
- Thread-safe global registry for per-model circuit breakers
- **Key Functions**:
  - `get_circuit_breaker(model_id, config)`: Get or create breaker for model
  - `check_circuit_breaker(model_id)`: Returns (allowed, reason) tuple
  - `record_model_result(model_id, success)`: Record result with automatic event emission
  - `get_all_breakers()`: Return all registered breakers (for monitoring)
  - `_reset_registry()`: Clear registry (for testing)
- **Event Emission**: Automatically emits L4_CIRCUIT_BREAKER_OPEN/CLOSE events on state transitions

**`observability/`** - ADR-030 Metrics Export
- Bridges internal LayerEvents to external metrics backends (Prometheus, StatsD)
- **`metrics_adapter.py`**: Main adapter implementation
  - `MetricsBackend`: Protocol for metrics backends (emit_counter, emit_gauge, emit_histogram)
  - `NoOpBackend`: No-operation backend when metrics disabled
  - `StatsDBackend`: UDP-based StatsD backend with DogStatsD tag support
  - `PrometheusBackend`: In-memory Prometheus metrics with text format export
  - `MetricsAdapter`: Translates LayerEvents to metrics
    - Handles `L4_CIRCUIT_BREAKER_OPEN` → counter + failure_rate gauge
    - Handles `L4_CIRCUIT_BREAKER_CLOSE` → counter with from_state tag
  - `get_metrics_adapter()`: Factory function (uses config for backend selection)
  - `subscribe_metrics_adapter()`: Subscribe to receive LayerEvents
  - `unsubscribe_metrics_adapter()`: Unsubscribe from events
  - `_notify_adapters()`: Internal hook called by `emit_layer_event()`
- **Configuration** (in `unified_config.py`):
  - `MetricsConfig`: enabled, backend, statsd_host, statsd_port, statsd_prefix, prometheus_port
  - Defaults: disabled, backend="none", localhost:8125 for StatsD, port 9090 for Prometheus
- **Environment Variables**:
  - `LLM_COUNCIL_METRICS_ENABLED`: Enable/disable metrics export (default: false)
  - `LLM_COUNCIL_METRICS_BACKEND`: Backend type (none, statsd, prometheus)
  - `LLM_COUNCIL_STATSD_HOST`: StatsD server host
  - `LLM_COUNCIL_STATSD_PORT`: StatsD server port

**`voting.py`** - ADR-027 Shadow Mode Voting Authority
- Implements voting authority levels for the council's tier system
- Frontier tier models operate in Shadow Mode by default
- **`VotingAuthority` Enum**:
  - `FULL`: Vote counts in consensus calculation (weight = 1.0)
  - `ADVISORY`: Vote logged/evaluated but has zero weight (Shadow Mode)
  - `EXCLUDED`: Model not included in deliberation
- **`TIER_VOTING_AUTHORITY`**: Default authority by tier
  - quick/balanced/high/reasoning: `VotingAuthority.FULL`
  - frontier: `VotingAuthority.ADVISORY` (Shadow Mode by default)
- **Key Functions**:
  - `get_vote_weight(authority)`: Returns 1.0 for FULL, 0.0 for ADVISORY/EXCLUDED
  - `get_model_voting_authority(model_id, tier, override)`: Get authority for model
  - `calculate_shadow_agreement(consensus_winner, shadow_votes)`: Calculate agreement ratio
- **Shadow Mode Purpose**: Prevents experimental/preview models from affecting production consensus while still logging their votes for evaluation

**`graduation.py`** - ADR-027 Frontier Graduation Criteria
- Determines when a frontier model is ready for promotion to high tier
- **`GraduationCriteria`**: Frozen dataclass with ADR-027 defaults
  - `min_age_days`: 30 (days of evaluation)
  - `min_completed_sessions`: 100 (council sessions)
  - `max_error_rate`: 0.02 (< 2% errors)
  - `min_quality_percentile`: 0.75 (>= 75th percentile)
- **`ModelStats`**: Tracked performance statistics for evaluation
- **`should_graduate(stats, criteria)`**: Returns (passed, failures) tuple
- **`get_graduation_candidates(tier)`**: Get all potential graduation candidates

**`cost_ceiling.py`** - ADR-027 Cost Ceiling Protection
- Prevents runaway costs for frontier tier models
- **`FRONTIER_COST_MULTIPLIER`**: Default 5.0x multiplier
- **`apply_cost_ceiling(model_id, model_cost, tier, high_tier_avg_cost)`**:
  - Returns (allowed, reason) tuple
  - Frontier models capped at 5x high-tier average cost
  - Non-frontier tiers bypass check
- **`check_model_cost_ceiling()`**: Convenience wrapper

**`frontier_fallback.py`** - ADR-027 Hard Fallback
- Automatic fallback from frontier tier to high tier on failure
- **`RateLimitError`**, **`APIError`**: Exception classes
- **`FallbackResult`**: Dataclass with response + fallback metadata
- **`execute_with_fallback(query, frontier_model, fallback_tier="high")`**:
  - Tries frontier model first
  - Falls back on timeout/rate limit/API error
  - Logs warning on fallback
- **`execute_with_fallback_detailed()`**: Same as above but returns FallbackResult with metadata
  - Emits `FRONTIER_FALLBACK_TRIGGERED` event on fallback
- **`emit_fallback_event(frontier_model, fallback_model, reason)`**: Emit fallback event
- **`should_use_fallback_wrapper(tier_contract)`**: Returns True for frontier tier only
- **`get_fallback_tier_from_config()`**: Get fallback tier from unified config
- **`DEFAULT_FRONTIER_TIMEOUT`**: 300 seconds

**`audition/`** - ADR-029 Model Audition Mechanism
- Implements volume-based audition for newly discovered models
- Solves the cold start problem: new models progress through states before voting
- **State Machine**: SHADOW → PROBATION → EVALUATION → FULL (+ QUARANTINE for failures)
- **`types.py`**: Core types
  - `AuditionState`: Enum (SHADOW, PROBATION, EVALUATION, FULL, QUARANTINE)
  - `AuditionStatus`: Dataclass tracking model progress (session_count, first_seen, consecutive_failures, quality_percentile)
  - `AuditionCriteria`: Frozen dataclass with graduation thresholds
  - `evaluate_state_transition()`: Determine if model should change states
  - `record_session_result()`: Update status after session
- **`tracker.py`**: Main tracker class
  - `AuditionTracker`: In-memory cache + JSONL persistence
  - `get_status(model_id)`: Get current audition status
  - `record_session(model_id, success, criteria)`: Record session and check transitions
  - `update_quality_percentile(model_id, percentile)`: Update quality score
  - `check_transitions(criteria)`: Evaluate all models for state changes
  - `get_audition_tracker()`: Singleton factory
- **`selection.py`**: Selection weighting
  - Weight progression: SHADOW/PROBATION=30%, EVALUATION=30-100%, FULL=100%, QUARANTINE=0%
  - `get_selection_weight(status)`: Returns weight factor (0-1)
  - `select_with_audition(candidates, tracker, count, max_audition_seats)`: Apply weights + seat limits
  - `is_auditioning_model(status)`: Check if in audition state
- **`voting.py`**: Voting integration
  - `STATE_VOTING_AUTHORITY`: Maps AuditionState to VotingAuthority
  - SHADOW/PROBATION/EVALUATION → ADVISORY (non-binding votes)
  - FULL → FULL (binding votes), QUARANTINE → EXCLUDED
  - `get_audition_voting_authority(model_id, tracker)`: Get authority for model
- **`store.py`**: JSONL persistence
  - `append_audition_record()`: Atomic append to JSONL
  - `read_audition_records()`: Read with optional model_id filter
- **Graduation Criteria** (per ADR-029):
  - SHADOW → PROBATION: 10 sessions + 3 days
  - PROBATION → EVALUATION: 25 sessions + 7 days
  - EVALUATION → FULL: 50 sessions + quality ≥ 75th percentile
  - Quarantine: consecutive failures exceed threshold (SHADOW: 3, PROBATION: 5)
- **Environment Variables**:
  - `LLM_COUNCIL_AUDITION_ENABLED`: Enable/disable audition (default: true)
  - `LLM_COUNCIL_AUDITION_MAX_SEATS`: Max audition models per session (default: 1)
  - `LLM_COUNCIL_AUDITION_SHADOW_SESSIONS`: Min sessions for SHADOW exit (default: 10)
  - `LLM_COUNCIL_AUDITION_EVAL_SESSIONS`: Min sessions for EVALUATION exit (default: 50)
- **Observability Events**:
  - `AUDITION_STATE_TRANSITION`: Model changed state
  - `AUDITION_MODEL_SELECTED`: Auditioning model selected for council
  - `AUDITION_FAILURE_RECORDED`: Session failure recorded
  - `AUDITION_QUARANTINE_TRIGGERED`: Model entered quarantine
  - `AUDITION_GRADUATION_COMPLETE`: Model graduated to FULL

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
  - **ADR-027**: Accepts optional `voting_authorities` dict mapping reviewer IDs to VotingAuthority
  - **ADR-027**: Accepts optional `return_shadow_votes` bool to include shadow vote metadata
  - ADVISORY votes (Shadow Mode) are tracked but have zero weight in rankings
- **ADR-027 Shadow Vote Integration**:
  - `should_track_shadow_votes(tier_contract)`: Returns True for frontier tier only
  - `emit_shadow_vote_events(shadow_votes, consensus_winner)`: Emits FRONTIER_SHADOW_VOTE events
  - Automatically enabled in `run_council_with_fallback` for frontier tier

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
- Configuration in `unified_config.py`: `scoring.safety_gate_enabled`

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
- **Configuration** (ADR-031): Uses `get_config().evaluation.bias.*` from unified_config
  - `audit_enabled`, `length_correlation_threshold`, `position_variance_threshold`

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
- **Configuration** (ADR-031): Uses helper functions accessing `get_config().evaluation.bias.*`
  - `_get_bias_persistence_enabled()`, `_get_bias_store_path()`, `_get_bias_consent_level()`

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

**`metadata/`** - ADR-026 Model Metadata Provider
- **`types.py`**: Core data structures
  - `ModelInfo`: Frozen dataclass with id, context_window, pricing, supported_parameters, modalities, quality_tier, is_preview, supports_reasoning
  - `QualityTier`: Enum (FRONTIER, STANDARD, ECONOMY, LOCAL)
  - `Modality`: Enum (TEXT, VISION, AUDIO)
- **`intersection.py`**: ADR-027 Tier intersection logic
  - `resolve_tier_intersection(tier, model_info, allow_preview)`: Determine if model qualifies for tier
  - Handles models belonging to multiple tiers (e.g., o1-preview is both reasoning and frontier)
  - Precedence rules: frontier includes previews, reasoning excludes previews by default
- **`protocol.py`**: Abstract protocol definition
  - `MetadataProvider`: `@runtime_checkable` Protocol with 5 methods
    - `get_model_info(model_id)` → Optional[ModelInfo]
    - `get_context_window(model_id)` → int (default 4096)
    - `get_pricing(model_id)` → Dict[str, float]
    - `supports_reasoning(model_id)` → bool
    - `list_available_models()` → List[str]
- **`static_registry.py`**: Offline-safe provider
  - `StaticRegistryProvider`: Implements MetadataProvider
  - Priority chain: local registry > LiteLLM > 4096 default
  - Loads bundled `models/registry.yaml` (31 models)
- **`litellm_adapter.py`**: LiteLLM metadata extraction
  - Lazy import prevents startup failures
  - Model ID normalization (openai/gpt-4o → gpt-4o)
- **`offline.py`**: Offline mode management
  - `is_offline_mode()`: Checks `LLM_COUNCIL_OFFLINE` env var
  - `check_offline_mode_startup()`: Logs INFO about offline mode
  - Truthy values: "true", "1", "yes", "on"
- **`__init__.py`**: Module exports and factory
  - `get_provider()`: Returns singleton StaticRegistryProvider
  - `reload_provider()`: Refreshes cached instance (for testing)
  - Exports: ModelInfo, QualityTier, Modality, MetadataProvider

**`reasoning/`** - ADR-026 Phase 2 Reasoning Parameter Optimization
- **`types.py`**: Core reasoning types
  - `ReasoningEffort`: Enum (MINIMAL, LOW, MEDIUM, HIGH, XHIGH)
  - `EFFORT_RATIOS`: Effort to ratio mapping (0.10, 0.20, 0.50, 0.80, 0.95)
  - `ReasoningConfig`: Frozen dataclass with `for_tier()` factory method
  - `should_apply_reasoning(stage, config)`: Check if reasoning applies to stage
- **`tracker.py`**: Usage tracking
  - `ReasoningUsage`: Per-model usage dataclass
  - `AggregatedUsage`: Cross-model aggregation
  - `extract_reasoning_usage()`: Parse OpenRouter response
  - `aggregate_reasoning_usage()`: Combine multiple usages
- **`__init__.py`**: Module exports

**Reasoning Effort Levels:**
- MINIMAL (10%): quick tier, creative tasks
- LOW (20%): balanced tier
- MEDIUM (50%): high tier, coding tasks
- HIGH (80%): reasoning tier, math tasks
- XHIGH (95%): explicit opt-in only

**Stage Configuration:**
- `stage1: true` (primary responses - default ON)
- `stage2: false` (peer reviews - default OFF)
- `stage3: true` (synthesis - default ON)

**Offline Mode** - ADR-026 "Sovereign Orchestrator" Philosophy
```bash
# Force offline operation - all core operations work without external calls
export LLM_COUNCIL_OFFLINE=true
```

When offline:
1. Uses StaticRegistryProvider exclusively
2. Disables external metadata/routing calls
3. Logs INFO about limited/stale metadata
4. All core council operations succeed

**Bundled Registry** (`src/llm_council/models/registry.yaml`)
- 31 models from 8 providers
- OpenAI, Anthropic, Google, xAI, DeepSeek, Meta, Mistral, Ollama
- Includes reasoning models (o1, o3-mini, deepseek-r1)
- Local models have LOCAL quality tier and $0 pricing

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
All backend modules use relative imports (e.g., `from .unified_config import ...`) not absolute imports. This is critical for Python's module system to work correctly when running as `python -m backend.main`.

### Port Configuration
- Backend: 8001 (changed from 8000 to avoid conflict)
- Frontend: 5173 (Vite default)
- Update both `backend/main.py` and `frontend/src/api.js` if changing

### Markdown Rendering
All ReactMarkdown components must be wrapped in `<div className="markdown-content">` for proper spacing. This class is defined globally in `index.css`.

### Model Configuration
Models are configured in `llm_council.yaml` and loaded via `unified_config.py`. Chairman can be same or different from council members. Configuration can be overridden via environment variables (e.g., `LLM_COUNCIL_MODELS`).

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

## Release Workflow

**Branch Protection**: The repository has branch protection rules requiring PRs and CI checks. **Never push directly to master** - all changes must go through PRs, even for releases.

### 1. Ensure Starting from Latest Master
```bash
git checkout master
git pull origin master
```

### 2. Create Release Branch
```bash
git checkout -b release/v0.X.0
```

### 3. Update CHANGELOG.md
Add release notes following [Keep a Changelog](https://keepachangelog.com/) format:
- **Added**: New features
- **Changed**: Changes to existing functionality
- **Fixed**: Bug fixes
- **Removed**: Removed features

### 4. Commit and Push Branch
```bash
git add CHANGELOG.md
git commit --signoff -m "chore(release): Prepare v0.X.0 release"
git push -u origin release/v0.X.0
```

### 5. Open Pull Request
```bash
gh pr create --title "Release v0.X.0" --body "## Release Notes

[changelog excerpt]

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

### 6. Wait for CI
Let GitHub Actions run tests and checks. **Do not merge until all required checks pass.**

Required checks:
- `Test` - Unit and integration tests
- `Lint` - Code style checks
- `Type Check` - Static type analysis
- `DCO` - Developer Certificate of Origin (requires `--signoff`)

### 7. Merge PR
After CI passes, merge via GitHub UI or CLI:
```bash
gh pr merge --squash --delete-branch
```

### 8. Tag the Release (After Merge)
**Only after PR is merged**, create and push the version tag:
```bash
git checkout master
git pull origin master
git tag -a v0.X.0 -m "v0.X.0 - Brief description"
git push origin v0.X.0
```

This triggers the `publish.yml` workflow which automatically:
- Builds the package
- Tests installation from wheel
- Publishes to PyPI

### 9. Verify Publication
```bash
# Check workflow status
gh run list --workflow=publish.yml --limit=1

# Verify on PyPI (after ~2 minutes)
pip index versions llm-council-core
```

### Versioning

- **Version source**: Git tags via `setuptools-scm` (configured in `pyproject.toml`)
- **Version file**: `src/llm_council/_version.py` is auto-generated and gitignored
- **Semantic versioning**: MAJOR.MINOR.PATCH
  - MAJOR: Breaking API changes
  - MINOR: New features, backward compatible
  - PATCH: Bug fixes only

### Why PRs Matter for OSS
- Runs CI checks before merge (tests, linting)
- Provides audit trail for contributors
- Models the workflow expected from contributors
- Allows async review if needed

### Enforcing Branch Protection
To prevent accidental direct pushes (even by admins), enable in GitHub:
**Settings → Branches → Branch protection rules → master → "Do not allow bypassing the above settings"**

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
