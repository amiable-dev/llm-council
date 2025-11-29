# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
