# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### Changed

- `consult_council` MCP tool now uses `run_council_with_fallback()` for reliability
- `consult_council` MCP tool now accepts optional `confidence` parameter
- Council rankings now displayed in output when available
- Partial result warnings shown when some models timeout

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
