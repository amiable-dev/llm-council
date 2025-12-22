# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2025-12-22

### Added

- **Triage Layer (ADR-020 Phase 3)**: Query classification and model selection optimization
  - `llm_council.triage` package with modular components
  - `TriageResult`, `TriageRequest`, `WildcardConfig`, `DomainCategory` types
  - Wildcard selection: Adds domain-specialized models based on query classification
  - Prompt optimization: Per-model prompt adaptation (Claude XML, etc.)
  - Complexity classifier: Heuristic-based with Not Diamond placeholder

- **Domain-Specialized Model Selection**:
  - CODE: DeepSeek, Codestral for programming queries
  - REASONING: o1-preview, DeepSeek-R1 for math/logic
  - CREATIVE: Claude Opus, Command-R+ for fiction/poetry
  - MULTILINGUAL: GPT-4o, Command-R+ for translation
  - GENERAL: Llama 3 fallback

- **Council Integration**:
  - `use_wildcard` parameter for `run_council_with_fallback()`
  - `optimize_prompts` parameter for per-model adaptation
  - Triage metadata included in council results

- **New Environment Variables**:
  - `LLM_COUNCIL_WILDCARD_ENABLED`: Enable wildcard selection (default: false)
  - `LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED`: Enable prompt optimization (default: false)

### Changed

- Triage layer is opt-in for backward compatibility
- 111 new tests for triage package (TDD approach)

## [0.7.0] - 2025-12-22

### Added

- **Gateway Abstraction Layer (ADR-023)**: Multi-router support with fault tolerance
  - `llm_council.gateway` package with provider-agnostic types
  - `OpenRouterGateway`: BaseRouter implementation for OpenRouter
  - `CircuitBreaker`: State machine (CLOSED → OPEN → HALF_OPEN) for fault tolerance
  - `GatewayRouter`: Orchestrates requests with circuit breaker integration
  - Canonical message formats: `CanonicalMessage`, `ContentBlock`, `GatewayRequest`, `GatewayResponse`
  - Error taxonomy: `TransportFailure`, `RateLimitError`, `AuthenticationError`, `CircuitOpenError`

- **Gateway Adapter Module**: Unified interface for council operations
  - `gateway_adapter.py` provides same interface as `openrouter` module
  - Automatically uses gateway layer when `USE_GATEWAY_LAYER=true`
  - Full backward compatibility when disabled (default)

- **New Environment Variables**:
  - `LLM_COUNCIL_USE_GATEWAY`: Enable gateway layer (default: false)

### Changed

- Gateway layer is opt-in via `LLM_COUNCIL_USE_GATEWAY=true`
- 88 new tests for gateway package (TDD approach)

## [0.6.0] - 2025-12-22

### Added

- **Tier-Appropriate Model Selection (ADR-022)**: Each confidence level now uses optimized model pools
  - `quick`: Fast models (gpt-4o-mini, claude-haiku, gemini-flash) for ~30s responses
  - `balanced`: Mid-tier models (gpt-4o, claude-sonnet, gemini-pro) for ~90s responses
  - `high`: Full council (gpt-4o, claude-opus, gemini-3-pro, grok-4) for ~180s responses
  - `reasoning`: Deep thinking models (gpt-5.2-pro, claude-opus, o1-preview, deepseek-r1) for ~600s responses

- **TierContract Dataclass**: Immutable contract defining tier execution parameters
  - `tier`, `deadline_ms`, `per_model_timeout_ms`, `token_budget`, `max_attempts`
  - `requires_peer_review`, `requires_verifier`, `allowed_models`, `aggregator_model`
  - `create_tier_contract()` factory function for easy creation
  - `TIER_AGGREGATORS`: Speed-matched aggregator models per tier

- **New Environment Variables**:
  - `LLM_COUNCIL_MODELS_QUICK`: Override quick tier models
  - `LLM_COUNCIL_MODELS_BALANCED`: Override balanced tier models
  - `LLM_COUNCIL_MODELS_HIGH`: Override high tier models
  - `LLM_COUNCIL_MODELS_REASONING`: Override reasoning tier models

### Changed

- `run_council_with_fallback()` now accepts `models` and `tier_contract` parameters
- MCP `consult_council` creates TierContract from confidence level
- Response metadata includes `tier` field when tier_contract provided

## [0.5.1] - 2025-12-22

### Changed

- **Doubled Reasoning Tier Timeouts**: Increased from 300s/150s to 600s/300s (total/per-model)
  - Addresses timeout issues with deep reasoning models (GPT-5.2-pro, o1)
  - 10-minute total timeout allows complex multi-model deliberation to complete

## [0.5.0] - 2025-12-19

### Added

- **Tier-Sovereign Timeout Architecture (ADR-012 Section 5)**: Configurable per-tier timeouts for reasoning models
  - New `reasoning` confidence tier: 600s total, 300s per-model (supports GPT-5.2-pro, o1, o1-preview)
  - Existing tiers updated: quick (30s/20s), balanced (90s/45s), high (180s/90s)
  - `get_tier_timeout()`: Retrieves timeout config with environment variable overrides
  - `infer_tier_from_models()`: Auto-selects tier based on slowest model in council
  - `per_model_timeout` parameter on `run_council_with_fallback()` for fine-grained control

- **New Environment Variables**:
  - `LLM_COUNCIL_TIMEOUT_<TIER>`: Override total timeout per tier (QUICK, BALANCED, HIGH, REASONING)
  - `LLM_COUNCIL_MODEL_TIMEOUT_<TIER>`: Override per-model timeout per tier

### Documentation

- ADR-012 Section 5: Tier-Sovereign Timeout Architecture with model compatibility matrix
- Infrastructure considerations for AWS ALB, Nginx, and proxy timeouts

## [0.4.1] - 2025-12-19

### Changed

- **Default Council Model Update**: Replaced `openai/gpt-5.1` with `openai/gpt-5.2-pro`
  - Upgraded to OpenAI's latest reasoning model for improved council quality

## [0.4.0] - 2025-12-18

### Added

- **Cross-Session Bias Aggregation (ADR-018)**: Statistically meaningful bias detection
  - Phase 1: JSONL-based bias metric persistence with schema versioning (v1.1.0)
  - Phase 2: Statistical aggregation with Fisher z-transforms and confidence intervals
  - Phase 3: Temporal trend detection and anomaly flagging
  - `BiasMetricRecord` dataclass with one record per (session, model, reviewer)
  - `ConsentLevel` enum: OFF(0), LOCAL_ONLY(1), ANONYMOUS(2), ENHANCED(3), RESEARCH(4)
  - Reviewer profiles with harshness z-scores for calibration analysis
  - Position bias aggregation via variance of position means
  - 74 new tests (44 Phase 1 + 30 Phase 2-3)

- **CLI `bias-report` Command**: Cross-session bias analysis from the command line
  - Text and JSON output formats
  - Filtering by sessions (`--sessions N`) and days (`--days N`)
  - Verbose mode (`--verbose`) for detailed reviewer profiles
  - Custom input path (`--input FILE`)

- **New Aggregation Functions**:
  - `run_aggregated_bias_audit()`: Main entry point for cross-session analysis
  - `pooled_correlation_with_ci()`: Pooled length-score correlation with 95% CI
  - `aggregate_reviewer_profiles()`: Per-reviewer mean, std, harshness z-score
  - `aggregate_position_bias()`: Variance of position means
  - `detect_temporal_trends()`: Rolling window trend detection
  - `detect_anomalies()`: Outlier session flagging

- **New Configuration Options**:
  - `LLM_COUNCIL_BIAS_PERSISTENCE`: Enable cross-session storage (default: false)
  - `LLM_COUNCIL_BIAS_STORE`: Path to JSONL file (default: ~/.llm-council/bias_metrics.jsonl)
  - `LLM_COUNCIL_BIAS_CONSENT`: Privacy consent level 0-4 (default: 1)
  - `LLM_COUNCIL_BIAS_WINDOW_SESSIONS`: Rolling window max sessions (default: 100)
  - `LLM_COUNCIL_BIAS_WINDOW_DAYS`: Rolling window max days (default: 30)
  - `LLM_COUNCIL_MIN_BIAS_SESSIONS`: Minimum sessions for aggregation (default: 20)
  - `LLM_COUNCIL_HASH_SECRET`: Secret for query hashing (RESEARCH consent only)

- **Statistical Confidence Tiers**:
  - INSUFFICIENT (N < 10): "Collecting data..."
  - PRELIMINARY (10-19): High volatility warning
  - MODERATE (20-49): Confidence intervals displayed
  - HIGH (N >= 50): Full analysis with narrow CIs

### Documentation

- ADR-018: Implementation status section with CLI usage examples
- README.md: Cross-session bias aggregation section and environment variables
- CLAUDE.md: Documentation for bias_persistence.py and bias_aggregation.py modules

## [0.3.0] - 2025-12-17

### Added

- **Bias Auditing (ADR-015)**: Per-session bias indicators for peer review scoring
  - Length-score correlation detection (Pearson r, threshold |r| > 0.3)
  - Position bias detection via `display_index` tracking
  - Reviewer calibration analysis (harsh/generous reviewers)
  - Overall bias risk assessment ("low", "medium", "high")
  - Pure Python implementation (no scipy/numpy dependency)
  - Configuration: `LLM_COUNCIL_BIAS_AUDIT=true`
  - **Note**: With 4-5 models per session, these are indicators for extreme anomalies, not statistically robust proof

- **Structured Rubric Scoring (ADR-016)**: Multi-dimensional evaluation
  - Five dimensions: accuracy (35%), relevance (10%), completeness (20%), conciseness (15%), clarity (20%)
  - Accuracy ceiling mechanism: prevents confident lies from ranking well
  - Scoring anchors with behavioral examples for each 1-10 level
  - Customizable weights via `LLM_COUNCIL_WEIGHT_*` environment variables
  - Configuration: `LLM_COUNCIL_RUBRIC_SCORING=true`

- **Safety Gate (ADR-016)**: Pass/fail pre-check for harmful content
  - Detects: dangerous instructions, weapon making, malware/hacking, self-harm, PII exposure
  - Context-aware: allows educational/defensive security content
  - Failed responses capped at score 0
  - Configuration: `LLM_COUNCIL_SAFETY_GATE=true`

- **Enhanced Position Tracking (Council-Recommended)**: Robust position bias detection
  - Enhanced `label_to_model` format with explicit `display_index`
  - Eliminates string parsing fragility
  - Backward compatible with legacy format
  - Documented invariant for label assignment order

- **New Bias Audit Functions**:
  - `run_bias_audit()`: Main entry point for bias analysis
  - `calculate_length_correlation()`: Pure Python Pearson correlation
  - `audit_reviewer_calibration()`: Detect harsh/generous reviewers
  - `calculate_position_bias()`: Position effect detection
  - `derive_position_mapping()`: Extract positions from label mapping
  - `extract_scores_from_stage2()`: Convert Stage 2 results for analysis

- **New Safety Functions**:
  - `check_response_safety()`: Scan for harmful content patterns
  - `apply_safety_gate_to_score()`: Cap scores for failed safety checks

- **New Rubric Functions**:
  - `calculate_weighted_score()`: Weighted average from dimension scores
  - `calculate_weighted_score_with_accuracy_ceiling()`: Accuracy-capped scoring
  - `parse_rubric_evaluation()`: Extract rubric JSON from model responses

### Changed

- `label_to_model` now uses enhanced format: `{"Response A": {"model": "...", "display_index": 0}}`
- Stage 2 evaluation prompts updated for rubric scoring when enabled
- Council metadata now includes `bias_audit` results when enabled

### Documentation

- ADR-015: Bias Auditing - Implementation status and invariants documented
- ADR-016: Structured Rubric Scoring - Scoring anchors and safety gate details
- ADR-017: Response Order Randomization - Position tracking implementation and future scenarios
- README.md: New environment variables and feature documentation
- CLAUDE.md: Developer documentation for new modules

## [0.2.0] - 2025-12-13

### Added

- **MCP Server Reliability (ADR-012)**: Comprehensive improvements for long-running operations
  - Progress notifications via `ctx.report_progress()` during council execution
  - Health check tool `council_health_check()` to verify API connectivity before expensive operations
  - Confidence levels parameter: "quick" (2 models, ~10s), "balanced" (3 models, ~25s), "high" (full council, ~45s)

- **Tiered Timeout Strategy (ADR-012 Phase 2)**: Graceful degradation under time pressure
  - Per-model soft deadline: 15s (start planning fallback)
  - Per-model hard deadline: 25s (abandon that model)
  - Global synthesis trigger: 40s (must start synthesis)
  - Response deadline: 50s (must return something)

- **Partial Results on Timeout**: Return whatever data has been collected
  - `run_council_with_fallback()`: New function with ADR-012 structured result schema
  - `quick_synthesis()`: Fast fallback synthesis from Stage 1 responses when Stage 2 times out
  - `generate_partial_warning()`: Clear warning messages indicating partial results
  - Per-model status tracking throughout the pipeline

- **Structured Error Handling**: Better failure taxonomy for model queries
  - Status types: `ok`, `timeout`, `rate_limited`, `auth_error`, `error`
  - Each response includes `latency_ms`, error messages, `retry_after` where applicable
  - Distinguishes between timeout, rate limiting (429), and auth errors (401/403)

- **New Council Functions**:
  - `stage1_collect_responses_with_status()`: Stage 1 with per-model status tracking
  - `run_council_with_fallback()`: Full pipeline with tiered timeouts and fallback synthesis

- **New OpenRouter Functions**:
  - `query_model_with_status()`: Returns structured result with status instead of None on failure
  - `query_models_with_progress()`: Parallel queries with real-time progress callbacks

- **Secure API Key Handling (ADR-013)**: Multi-tier secure key resolution
  - Key resolution priority: Environment variable → System Keychain → Config file
  - Optional `keyring` dependency for system keychain integration
  - `setup-key` CLI command for securely storing API keys
  - Key source tracking via `get_key_source()` for diagnostics
  - Warning emitted when key loaded from insecure config file (suppressible)

- **New CLI Command**:
  - `llm-council setup-key`: Securely store API key in system keychain
  - `llm-council setup-key --stdin`: Read key from stdin for CI/CD automation

- **New Optional Dependency**:
  - `[secure]` extra: `pip install "llm-council-core[secure]"` for keychain support

### Changed

- `consult_council` MCP tool now uses `run_council_with_fallback()` for reliability
- `consult_council` MCP tool now accepts optional `confidence` parameter
- Council rankings now displayed in output when available
- Partial result warnings shown when some models timeout
- Health check now includes `key_source` field showing where API key came from

## [0.1.0] - 2024-12-01

### Changed

- **Package Renamed**: PyPI package renamed from `llm-council` to `llm-council-core`
  - Import remains `llm_council` (no code changes needed)
  - CLI command remains `llm-council`
  - Install: `pip install llm-council-core[mcp]`

### Added

- **Version Export**: `__version__` and `__version_tuple__` now exported from package root
  - Enables version checking: `from llm_council import __version__`

## [0.3.0] - 2024-11-29

### Added

- **Cost Transparency**: Token usage tracking across all pipeline stages
  - Per-stage breakdown (Stage 1, 1.5, 2, 3)
  - Grand total tokens (prompt, completion, total)
  - Included in response metadata for cost monitoring

- **Borda Count Ranking**: More robust ranking aggregation
  - 1st place = (N-1) points, 2nd = (N-2), ..., last = 0 points
  - Uses relative rankings (which LLMs are good at) instead of absolute scores
  - Scores still tracked as secondary signal

- **Small Council Handling**: Graceful degradation for N ≤ 2
  - Single model (N=1): Skip Stage 2 peer review entirely
  - Two models (N=2): Proceed but mark rankings as "degraded" (single vote each)
  - Clear warnings in metadata for transparency

- **Reviewer Refusal Detection**: Handle safety refusals gracefully
  - Detects common refusal patterns ("I cannot evaluate", "I must decline", etc.)
  - Marks abstained reviewers in metadata with reason
  - Abstentions excluded from ranking aggregation

- **HTML Escaping for XML Defense**: Enhanced prompt injection protection
  - Response content HTML-escaped within XML tags
  - Prevents injection via HTML/XML special characters

- **Tool Calling Disabled**: Stage 2/3 now explicitly disable tool calling
  - Prevents prompt injection via tool invocation
  - Uses OpenRouter's `tools: []` and `tool_choice: "none"` options

### Changed

- All stage functions now return usage data alongside results
- Metadata structure updated to include `usage.by_stage` and `usage.total`

### Fixed

- Aggregate rankings now use Borda Count for more stable results
- Reviewer abstentions no longer corrupt ranking calculations

## [0.2.0] - 2024-11-29

### Added

- **JSON-based Rankings**: Stage 2 now uses structured JSON output instead of string parsing
  - Rankings include both ordered list and numeric scores (1-10)
  - Robust parsing with multiple fallback strategies
  - Backwards compatible with legacy "FINAL RANKING:" format

- **Self-Vote Exclusion**: Models' votes for their own responses are excluded from aggregation
  - Prevents self-preference bias
  - Configurable via `LLM_COUNCIL_EXCLUDE_SELF_VOTES` (default: true)
  - Each response still receives N-1 peer reviews

- **XML Sandboxing**: Prompt injection defense for Stage 2
  - Responses wrapped in `<candidate_response>` tags
  - Explicit instruction to ignore embedded commands
  - Protects against adversarial response content

- **Style Normalization (Stage 1.5)**: Optional preprocessing to strengthen anonymization
  - Rewrites responses in neutral style before peer review
  - Removes AI preambles and stylistic fingerprints
  - Configurable via `LLM_COUNCIL_STYLE_NORMALIZATION` (default: false)
  - Uses fast/cheap model for efficiency

- **Consensus/Debate Modes**: Configurable synthesis strategy
  - `consensus` (default): Chairman synthesizes single best answer
  - `debate`: Chairman highlights disagreements and trade-offs
  - Configurable via `LLM_COUNCIL_MODE`

- **Stratified Sampling**: Scalability for large councils
  - Limits reviewers per response to reduce O(N²) complexity
  - Configurable via `LLM_COUNCIL_MAX_REVIEWERS`
  - Recommended: 3 reviewers for councils > 5 models

- **Position Randomization**: Response order shuffled before Stage 2
  - Prevents position bias in peer review

- **Enhanced Metadata**: Council responses now include configuration details
  - Synthesis mode, self-vote settings, council size
  - Aggregate rankings with scores and vote counts

### Changed

- Updated default council models to latest versions:
  - GPT-5.1, Gemini 3 Pro Preview, Claude Sonnet 4.5, Grok 4
- Default chairman changed to Gemini 3 Pro Preview
- Stage 3 now receives aggregate rankings for better synthesis context

### Fixed

- Ranking aggregation now correctly parses JSON structure
- Position bias reduced via response order randomization

## [0.1.0] - 2024-11-28

### Added

- Initial MCP server release
- 3-stage council process (collect, rank, synthesize)
- OpenRouter integration for multi-model access
- User-configurable model selection via env vars and config file
- Graceful degradation when individual models fail
- PyPI package distribution
- GitHub Actions CI/CD pipeline
