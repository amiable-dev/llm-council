# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.24.0] - 2026-01-03

### Added

- **Output Quality Quantification (ADR-036)**: Three metrics for multi-model deliberation quality
  - **Consensus Strength Score (CSS)**: Measures Stage 2 reviewer agreement
    - Winner margin (40%), ordering clarity (40%), non-tie factor (20%)
    - Interpretation thresholds: 0.85+ strong, 0.70-0.84 moderate, 0.50-0.69 weak
  - **Deliberation Depth Index (DDI)**: Measures thoroughness of deliberation
    - Response diversity (35%), review coverage (35%), critique richness (30%)
    - Uses Jaccard dissimilarity for diversity calculation
  - **Synthesis Attribution Score (SAS)**: Measures grounding of synthesis
    - `winner_alignment`, `max_source_alignment`, `hallucination_risk`, `grounded`
    - Threshold: `grounded=True` when `max_source_alignment >= 0.6`

- **Quality Metrics Module**: New `llm_council.quality` package
  - `types.py`: QualityMetrics, CoreMetrics, SynthesisAttribution dataclasses
  - `consensus.py`: CSS calculation from aggregate rankings
  - `deliberation.py`: DDI calculation with Jaccard-based diversity
  - `attribution.py`: SAS calculation for synthesis grounding
  - `integration.py`: Council integration with configurable enable/disable

- **MCP Tool Enhancement**: Visual quality metrics display
  - Progress bars for CSS and DDI in council responses
  - Grounded status with hallucination risk percentage
  - Warnings display for quality threshold violations

- **Quality Metrics Configuration**
  - `LLM_COUNCIL_QUALITY_METRICS`: Enable/disable (default: true)
  - `LLM_COUNCIL_QUALITY_TIER`: Tier selection (core|standard|enterprise)
  - YAML config support via `quality.enabled` and `quality.tier`

- **Quality Metrics Tests**: 44 TDD tests covering all components
  - Edge cases: empty inputs, single responses, all tied rankings
  - Boundary conditions: threshold values, interpretation ranges
  - Integration tests with council pipeline

- **Documentation Updates**
  - README: Added "Output Quality Metrics (ADR-036)" section
  - ADR-036: Updated status from Draft to Accepted with implementation notes
  - Blog Post 15: "Quantifying Council Quality: CSS, DDI, and SAS"
  - Community announcements for Twitter, Reddit, HN

### Technical Notes

- **Jaccard Similarity Fallback**: Phase 1 uses synchronous Jaccard-based calculations
  - Offline-compatible, no external dependencies
  - Async embedding functions preserved for Tier 2/3 (future phases)
- **Performance**: <30ms total overhead (CSS <5ms, DDI <10ms, SAS <15ms)
- **Tier System**: Core (OSS) tier implemented; Standard/Enterprise reserved for future

## [0.23.1] - 2026-01-03

### Fixed

- **README logo**: Corrected path from `docs/assets/logo.svg` to `docs/img/logo.svg`
- **Blog post broken link**: Removed curl reference to non-existent `examples/github-actions/` directory
- **Blog post clarity**: Added model name disclaimer and import clarification (`pip install llm-council-core` imports as `llm_council`)

## [0.23.0] - 2026-01-01

### Added

- **Directory Expansion for Verification (ADR-034 v2.7)**: Expand directory paths to constituent files
  - `_get_git_object_type()`: Detect blob (file) vs tree (directory) via `git cat-file -t`
  - `_git_ls_tree_z_name_only()`: NUL-delimited parsing for safe filename handling
  - `_expand_target_paths()`: Core expansion with text filtering and truncation
  - `TEXT_EXTENSIONS`: 80+ text file extensions (source code, config, documentation)
  - `GARBAGE_FILENAMES`: Lock files excluded (package-lock.json, yarn.lock, etc.)
  - `MAX_FILES_EXPANSION`: Hard cap of 100 files per expansion

- **Verification Response Schema Enhancement**
  - `expanded_paths`: List of files included after expansion
  - `paths_truncated`: Boolean indicating if MAX_FILES_EXPANSION was hit
  - `expansion_warnings`: Warnings about skipped files or truncation

- **Directory Expansion Tests**: 34 unit and integration tests
  - Real git operations against actual repo
  - Mock tests for edge cases (spaces, newlines, symlinks, submodules)
  - Integration tests with docs/ and src/ directories

### Fixed

- **Verification with Directory Paths**: Now returns file contents instead of git tree listings
  - Previously: `target_paths=["docs/"]` returned tree listing (040000 tree, 100644 blob, etc.)
  - Now: Expands to actual markdown/text files for meaningful council review

### Security

- **Symlink Skipping**: Silently skip symlinks (mode 120000) to prevent path escape
- **Submodule Skipping**: Skip submodules (mode 160000) that lack snapshot context

## [0.22.0] - 2026-01-01

### Added

- **Council Deliberation for Verification (ADR-034 A7)**: Full 3-stage multi-model deliberation
  - Stage 1: Parallel code reviews from multiple models
  - Stage 2: Anonymous peer ranking with rubric scoring
  - Stage 3: Chairman synthesis with structured APPROVED/REJECTED verdict
  - Confidence calculation based on reviewer agreement (rubric score variance)
  - Binary verdict extraction with configurable threshold (default 0.7)
  - Exit codes: 0=PASS, 1=FAIL, 2=UNCLEAR (for CI/CD integration)

- **Verification Prompt Enhancement**: Include actual file contents in verification requests
  - Fetches changed files from git at specified commit SHA
  - Truncates large files to prevent token overflow
  - Supports target_paths filtering for focused verification

- **Blog Post**: "Multi-Model Deliberation: How LLM Council Verifies Code"
  - Explains 3-stage architecture with code examples
  - Documents confidence calculation and verdict extraction
  - Includes GitHub Actions CI/CD integration example
  - Performance considerations table (quick/balanced/high tiers)

### Changed

- **SkillLoader**: Enhanced robustness per council review
  - Better error handling for malformed SKILL.md files
  - Improved metadata caching

### Fixed

- **Async File Operations**: Replaced blocking subprocess calls with async
  - Uses `asyncio.create_subprocess_exec()` instead of `subprocess.run()`
  - Streaming file reads with 8KB chunks (DoS protection)
  - Batched file fetching with early termination
  - Semaphore-based concurrency limiting (10 concurrent git ops)
  - Path traversal attack prevention

- **Rubric Extraction**: Fixed format mismatch in Stage 2 rubric scores
  - Handles both JSON and text-based rubric formats
  - Graceful fallback when parsing fails

### Security

- **DoS Protection**: Multiple layers of protection in verification API
  - File size limits with streaming truncation
  - Batch processing prevents memory exhaustion on large commits
  - Early termination when character limits reached

## [0.21.0] - 2025-12-31

### Added

- **Agent Skills (ADR-034)**: AI-assisted verification, code review, and CI/CD quality gates
  - `council-verify`: General work verification with multi-dimensional scoring
  - `council-review`: Code review with 35% accuracy weight, security/performance/testing focus
  - `council-gate`: CI/CD quality gates with structured exit codes (0=PASS, 1=FAIL, 2=UNCLEAR)
  - Progressive disclosure for token efficiency (Level 1: ~200 tokens, Level 2: ~1000 tokens)
  - Cross-platform compatibility (Claude Code, VS Code Copilot, Cursor, Codex CLI)
  - Skills located at `.github/skills/` for cross-platform discovery

- **Skill Loader**: Python API for progressive skill loading
  - `SkillLoader` class with metadata caching
  - `load_metadata()`: Level 1 - YAML frontmatter only
  - `load_full()`: Level 2 - Complete SKILL.md content
  - `load_resource()`: Level 3 - On-demand resource loading
  - `list_skills()` and `list_resources()` discovery methods

- **Rubric Scoring**: ADR-016 multi-dimensional evaluation
  - 5 dimensions: Accuracy, Completeness, Clarity, Conciseness, Relevance
  - Configurable weights (council-review uses 35% accuracy vs 30% default)
  - Accuracy ceiling rule: prevents eloquent incorrect answers from ranking highly

- **Code Review Rubrics**: Specialized scoring for PR reviews
  - Security focus: SQL injection, XSS, secrets, authentication
  - Performance focus: Algorithm complexity, N+1 queries, memory leaks
  - Testing focus: Coverage gaps, flaky tests, mocking issues
  - Blocking issues by severity: Critical (auto-FAIL), Major, Minor

- **CI/CD Rubrics**: Pipeline integration patterns
  - GitHub Actions, GitLab CI, Azure DevOps examples
  - Exit code documentation (0/1/2 mapping)
  - Security, Performance, Compliance focus areas
  - Confidence threshold configuration

- **Documentation**: Comprehensive guides for agent skills
  - User guide: `docs/guides/skills.md`
  - Developer guide: `docs/guides/creating-skills.md`
  - README section with quick reference table
  - ADR-034 implementation status update

- **Blog Posts**: Three posts documenting the release
  - "Introducing Agent Skills" - Feature announcement
  - "Defense-in-Depth Security" - 8-layer security architecture
  - "CI/CD Quality Gates" - Pipeline integration guide

- **Social Media Announcements**: Launch content prepared
  - Twitter/X threads (feature + technical deep dive)
  - Hacker News "Show HN" post
  - Reddit posts (r/LocalLLaMA, r/MachineLearning)
  - LinkedIn and Discord/Slack announcements

### Changed

- **mkdocs.yml**: Added navigation for skills guides and blog posts
- **README.md**: Added Agent Skills section with installation and usage

## [0.20.0] - 2025-12-30

### Added

- **One-Click Deployment (ADR-038)**: Deploy LLM Council to cloud platforms in minutes
  - Railway template with deploy button and marketplace listing
  - Render blueprint with free tier support
  - Docker Compose for local development
  - `deploy/railway/Dockerfile` optimized for cloud deployment
  - `railway.json` configuration for Railway platform
  - `render.yaml` blueprint for Render platform
  - `docker-compose.yml` for local development
  - `.github/workflows/validate-templates.yml` CI for template validation
  - Comprehensive deployment documentation (`docs/deployment/`)
  - Blog post: "From Clone to Cloud in 60 Seconds"

- **API Token Authentication**: Secure HTTP API endpoints
  - `LLM_COUNCIL_API_TOKEN` environment variable for Bearer token auth
  - Protected endpoints require `Authorization: Bearer <token>` header
  - `/health` endpoint remains public for load balancer checks
  - Backwards compatible: auth optional when token not configured

- **n8n Workflow Integration**: Connect LLM Council to workflow automation
  - Blog post with code review, support triage, and design decision examples
  - HTTP Request node configuration guide
  - Webhook security with HMAC verification
  - Authentication best practices

- **ADR-035 DevSecOps Implementation**: Complete 5-layer security pipeline
  - `.github/dependabot.yml`: Automated dependency updates (pip + GitHub Actions)
  - `.github/workflows/security.yml`: Main security workflow with all scans
  - `.github/workflows/release-security.yml`: SBOM attachment to releases
  - `.gitleaks.toml`: Custom secret patterns for OpenRouter, Anthropic, OpenAI
  - `.pre-commit-config.yaml`: Ruff + Gitleaks pre-commit hooks
  - `.semgrep/llm-security.yaml`: LLM-specific security rules
  - `sonar-project.properties`: SonarCloud configuration
  - Security badge added to README
  - Automated scanning section added to SECURITY.md
  - TDD test suites for security configurations

- **Supply Chain Security**: SLSA Level 3 provenance and OpenSSF Scorecard
  - SLSA provenance attestations for releases (#234)
  - OpenSSF Scorecard workflow for security visibility (#233)

- **Documentation Site**: Custom domain and branding
  - `llm-council.dev` custom domain
  - Brand typography and styling
  - Improved navigation with ADRs and blog

### Changed

- **Security Visibility**: Updated SECURITY.md with automated scanning documentation
  - Documents 5-layer security architecture
  - Pre-commit installation instructions
  - Links to ADR-035 for architecture details

### Fixed

- **Railway Deployment**: Fixed `$PORT` variable expansion (#253)
  - Wrapped start command in `sh -c` for proper shell expansion
- **Render Blueprint**: Set `plan: free` to use free tier by default
- **SBOM/Snyk Workflows**: Fixed Layer 3 workflow failures (#230)

## [0.19.2] - 2025-12-28

### Changed

- **Release Workflow Documentation**: Updated CLAUDE.md with correct PR-based release process
  - Emphasizes never pushing directly to master
  - Documents required CI checks (Test, Lint, Type Check, DCO)
  - Adds verification steps and enforcement notes

### Fixed

- **CI Pipeline**: Disabled failing `Notify Council Cloud` job temporarily (#202)
  - Job requires `CROSS_REPO_TOKEN` secret which is not configured
  - Will be reinstated when secret is set up

## [0.19.1] - 2025-12-28

### Added

- **Model Registry**: Added 6 missing models to `registry.yaml` for offline mode support
  - `openai/gpt-5-mini`: 400K context, economy tier
  - `openai/gpt-5.2`: 400K context, frontier tier
  - `anthropic/claude-sonnet-4.5`: 200K context, frontier tier
  - `anthropic/claude-haiku-4.5`: 200K context, economy tier
  - `google/gemini-3-flash-preview`: 1M context, economy tier
  - `x-ai/grok-code-fast-1`: 256K context, economy tier

### Fixed

- **Branch Protection**: Fixed CI status check name mismatch (`test` → `Test`)

## [0.19.0] - 2025-12-28

### Added

- **ADR-035 DevSecOps Implementation**: Comprehensive security pipeline for OSS
  - 5-layer security pipeline (Pre-commit → PR → Main → Release → Runtime)
  - Fork-compatible CI design (PR checks work without repo secrets)
  - GitHub Actions workflows: CodeQL, Trivy, Semgrep, Gitleaks, Dependency Review
  - SBOM generation with CycloneDX for supply chain transparency
  - Council-reviewed with reasoning tier feedback incorporated

### Fixed

- **Discovery Import Bug**: Fixed `discovery.py` importing from deleted `config.py`
  - Now correctly imports from `tier_contract._get_tier_model_pools()`

### Changed

- **Model Pool Configuration**: Updated tier model pools to next-gen identifiers
  - quick: gpt-5-mini, claude-haiku-4.5, gemini-3-flash-preview
  - balanced: gpt-5-mini, claude-sonnet-4.5, gemini-3-flash-preview, grok-code-fast-1
  - high: gpt-5.2, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast
  - reasoning/frontier: gpt-5.2-pro, claude-opus-4.5, gemini-3-pro-preview, grok-4.1-fast
- Synced `llm_council.yaml` with `unified_config.py` TierConfig defaults

## [0.18.1] - 2025-12-28

### Fixed

- **CI/CD Pipeline**: Fixed GitHub Actions failures
  - Added `pydantic>=2.0.0` to core dependencies (required by unified_config.py)
  - Relaxed ruff lint rules to ignore intentional patterns (E402, I001, F401, etc.)
  - Skip MCP tests when `mcp` package not installed (optional dependency)
  - Skip mkdocs build test when `mkdocs` not installed (docs optional dependency)
  - Updated test expectation for `site_name` to match mkdocs.yml

## [0.18.0] - 2025-12-28

### Added

- **ADR-034 Agent Skills Integration**: Standard skill interface for work verification
  - Comparison of Banteg's multi-CLI approach vs LLM Council deliberation
  - Proposed skill wrappers: `council-verify`, `council-review`, `council-gate`
  - Verification API design (`POST /v1/council/verify`) with machine-actionable JSON
  - Pluggable backend architecture supporting multiple verification engines
  - Defense-in-depth security model with context isolation
  - Council-reviewed with feedback incorporated

- **ADR-033 OSS Community Infrastructure**: Documentation and branding
  - MkDocs Material theme with brand typography (Montserrat + JetBrains Mono)
  - Custom domain `llm-council.dev` configured
  - 28 ADRs and 7 blog posts added to navigation
  - Hero section with styled CTAs
  - GitHub issue templates for bugs, features, and ADRs

### Fixed

- MkDocs navigation: All 28 ADRs now properly listed
- MkDocs navigation: All 7 blog posts now in Blog section
- 9 broken links in ADR documentation files

### Changed

- Documentation URL updated to `https://llm-council.dev`
- README.md: Added documentation badge linking to llm-council.dev

## [0.17.0] - 2025-12-27

### Added

- **ADR-031 EvaluationConfig**: Unified evaluation configuration schema
  - `EvaluationConfig` class with benchmark, comparison, and reporting settings
  - Environment variable overrides for all evaluation settings
  - Integration with unified configuration system

- **ADR-032 Complete Configuration Migration**: Single source of truth
  - All configuration now flows through `unified_config.py`
  - Added `get_api_key()` with ADR-013 resolution chain (env → keychain → dotenv)
  - Added `get_key_source()` for API key diagnostics
  - Added `dump_effective_config()` for debugging
  - Public `get_tier_timeout()` function in `tier_contract.py`

### Removed

- **Deleted `config.py`**: 823 lines of legacy configuration code removed
  - All 16 import sites migrated to `unified_config.py` and `tier_contract.py`
  - Tier model pools now accessed via `tier_contract._get_tier_model_pools()`
  - `OLLAMA_HARDWARE_PROFILES` moved to `gateway/ollama.py`

### Changed

- Updated 15 test files to use new configuration imports
- `metadata/selection.py` now imports from `tier_contract` instead of `config`
- Documentation updated to reflect configuration changes

## [0.16.0] - 2025-12-24

### Added

- **ADR-027 Frontier Tier**: Cutting-edge model support with Shadow Mode
  - `VotingAuthority` enum (FULL, ADVISORY, EXCLUDED) for tier-based voting
  - Shadow Mode: Frontier models vote but don't affect consensus
  - `GraduationCriteria` for promoting models from frontier to high tier
  - Cost ceiling protection (5x high-tier average)
  - Hard fallback from frontier to high tier on failure

- **ADR-028 Dynamic Candidate Discovery**: Real-time model discovery
  - Background worker for periodic model refresh
  - Circuit breaker integration for model health tracking
  - Automatic candidate pool updates from OpenRouter API

- **ADR-029 Model Audition Mechanism**: Controlled model evaluation
  - Structured audition process for new models
  - Performance tracking during audition period
  - Graduation criteria based on quality metrics

- **ADR-030 Scoring Refinements**: Improved model scoring
  - `CostScaleAlgorithm` options: linear, log_ratio, exponential
  - Benchmark-justified `QUALITY_TIER_SCORES` with citations
  - `MetricsAdapter` for circuit breaker telemetry
  - Cost scoring with configurable algorithms

### Changed

- Tier model pools now include `frontier` tier
- Quality tier scores updated based on MMLU benchmarks
- Circuit breaker integration with model selection

## [0.15.0] - 2025-12-24

### Added

- **ADR-026 Model Intelligence Layer**: Dynamic model metadata and selection
  - **Phase 1**: Dynamic metadata with TTL caching
    - `DynamicMetadataProvider` with OpenRouter API integration
    - `StaticRegistryProvider` with 31 bundled models
    - `select_tier_models()` for weighted model selection
    - Anti-herding penalties for traffic concentration
    - Provider diversity enforcement (min 2 providers)
  - **Phase 2**: Reasoning parameter optimization
    - `ReasoningConfig` with effort levels (MINIMAL to XHIGH)
    - Automatic reasoning injection for o1/R1 models
    - Usage tracking for reasoning tokens
  - **Phase 3**: Internal performance tracking
    - `InternalPerformanceTracker` with exponential decay
    - JSONL persistence for performance metrics
    - Quality scores based on Borda rankings

- **Offline Mode**: `LLM_COUNCIL_OFFLINE=true` for air-gapped deployments
  - Forces `StaticRegistryProvider` exclusively
  - All core operations work without external calls

- **Bundled Model Registry**: `models/registry.yaml` with 31 models
  - OpenAI, Anthropic, Google, xAI, DeepSeek, Meta, Mistral, Ollama
  - Includes context windows, pricing, and quality tiers

### Changed

- `create_tier_contract()` now accepts optional `task_domain` parameter
- Model selection uses real metadata instead of regex heuristics

## [0.14.0] - 2025-12-23

### Added

- **ADR-025b Jury Mode**: Transform the council from "Summary Generator" to "Decision Engine"
  - **Binary Verdict Mode**: Go/no-go decisions with confidence scores (0.0-1.0)
    - `verdict_type="binary"` returns `{verdict: "approved"|"rejected", confidence, rationale}`
    - Confidence derived from council ranking agreement
    - Use cases: CI/CD gates, PR reviews, policy enforcement
  - **Tie-Breaker Mode**: Chairman resolves deadlocked decisions
    - Auto-escalates when top Borda scores within 0.1 threshold
    - `deadlocked: true` flag indicates chairman intervention
    - Explicit rationale for tie-breaker decisions
  - **Constructive Dissent**: Extract minority opinions from Stage 2
    - `include_dissent=True` surfaces outlier evaluations
    - Statistical detection: score < median - 1.5 × std
    - Formatted as "Minority perspective: ..." in output

- **New Files**:
  - `src/llm_council/verdict.py`: VerdictType enum, VerdictResult dataclass
  - `src/llm_council/dissent.py`: Dissent extraction from Stage 2 evaluations
  - `tests/test_verdict.py`: 8 TDD tests for verdict functionality
  - `tests/test_dissent.py`: 15 TDD tests for dissent extraction

- **API Changes**:
  - `consult_council` MCP tool: Added `verdict_type` and `include_dissent` parameters
  - `run_full_council()`: Added `verdict_type` and `include_dissent` parameters
  - `run_council_with_fallback()`: Added `verdict_type` and `include_dissent` parameters
  - HTTP API `/v1/council/run`: Added `verdict_type` and `include_dissent` fields

### Changed

- README.md: Added comprehensive Jury Mode documentation section
- ADR-025: Updated with ADR-025b implementation status (100% complete)
- `webhooks/__init__.py`: Updated docstring to include EventBridge examples

### Documentation

- Jury Mode section in README with:
  - Verdict types table (synthesis, binary, tie_breaker)
  - Code examples for each mode
  - CI/CD gate integration example
  - Environment variables reference
- Updated `consult_council` tool documentation with new parameters
- ADR-025b implementation status with files created/modified

## [0.12.3] - 2025-12-23

### Added

- **ADR-025: Future Integration Capabilities**: Strategic roadmap for 2025+ integrations
  - Industry landscape analysis (Agentic AI, MCP adoption, Local LLM trends)
  - Council-reviewed priorities for OllamaGateway, webhooks, streaming API
  - Consensus: Native OllamaGateway as top priority for privacy/compliance
  - Agentic positioning as "agent jury" for multi-agent consensus

- **CLI Version Flag**: `llm-council --version` / `llm-council -V`
  - Displays installed package version

### Documentation

- Comprehensive industry analysis with December 2025 trends
- Council review with unanimous verdicts on all 5 key questions
- Phased implementation roadmap (3-6 months)
- Hardware requirements for fully local council deployment

## [0.12.2] - 2025-12-22

### Added

- **RequestyGateway (ADR-023 Phase 2, Issue #66)**: Requesty API integration with BYOK support
  - `RequestyGateway` class implementing `BaseRouter` protocol
  - BYOK (Bring Your Own Key) for provider API keys
  - Full message format conversion and health checking
  - Integration with `GatewayRouter` fallback chains
  - 20 TDD tests

- **DirectGateway (ADR-023 Phase 3, Issue #67)**: Direct provider API access
  - `DirectGateway` class implementing `BaseRouter` protocol
  - Direct API calls to Anthropic, OpenAI, and Google
  - Provider-specific message format handling
  - Anthropic Messages API support (differs from OpenAI format)
  - Google Gemini API support
  - 24 TDD tests

### Changed

- ADR-023 status updated to COMPLETE (all gateways implemented)
- Gateway package now exports `RequestyGateway` and `DirectGateway`
- 44 new tests for gateway implementations

## [0.12.1] - 2025-12-22

### Added

- **Gateway Fallback Chain (ADR-023)**: Seamless retry with secondary gateways on failure
  - `GatewayRouter.complete()` now iterates through fallback chain
  - `fallback_chains` parameter for configuring fallback order
  - Emits `L4_GATEWAY_FALLBACK` event on gateway switch
  - Circuit breaker integration skips unavailable gateways

- **Full Observability Wiring (ADR-024)**: Layer events emitted throughout execution
  - `L2_FAST_PATH_TRIGGERED`: Emitted when fast path routing is attempted (Issue #64)
  - `L2_WILDCARD_SELECTED`: Emitted when wildcard specialist is selected (Issue #65)
  - `L3_COUNCIL_START`: Emitted at council execution start
  - `L3_COUNCIL_COMPLETE`: Emitted at council completion (success, timeout, error)
  - `L4_GATEWAY_RESPONSE`: Emitted for all gateway responses (success and error)
  - Layer boundary crossings: `cross_l1_to_l2()`, `cross_l2_to_l3()`, `cross_l3_to_l4()`

### Fixed

- Gateway router indentation issue
- L4_GATEWAY_RESPONSE now emitted for error/timeout responses (not just success)

### Changed

- 11 new tests for gateway fallback, observability wiring, fast path events, and wildcard events

## [0.12.0] - 2025-12-22

### Added

- **Confidence-Gated Fast Path (ADR-020 Tier 1, Issue #57)**: Route simple queries to single model
  - `FastPathRouter`: Routes queries based on complexity classification
  - `FastPathConfig`: Configuration for confidence threshold (default: 0.92), model selection
  - `ConfidenceExtractor`: Extracts confidence scores from model responses
  - `FastPathResult`: Structured result with confidence, escalation status
  - Graceful escalation to full council when confidence is below threshold
  - Environment variables: `LLM_COUNCIL_FAST_PATH_ENABLED`, `LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD`

- **Shadow Council Sampling (ADR-020 Tier 1, Issue #58)**: Quality validation for fast path
  - `ShadowSampler`: Random 5% sampling of fast-path queries through full council
  - `DisagreementDetector`: Text similarity comparison (word-based Jaccard)
  - `ShadowMetricStore`: JSONL persistence for disagreement tracking
  - `ShadowSampleResult`: Structured result with agreement score and analysis
  - Configurable sampling rate and disagreement threshold
  - Environment variables: `LLM_COUNCIL_SHADOW_SAMPLE_RATE`, `LLM_COUNCIL_SHADOW_DISAGREEMENT_THRESHOLD`

- **Rollback Metric Tracking (ADR-020 Tier 1, Issue #60)**: Automatic rollback triggers
  - `RollbackMonitor`: Tracks metrics and checks thresholds for automatic rollback
  - `RollbackMetricStore`: JSONL persistence with rolling window
  - `MetricType`: Shadow disagreement, user escalation, error rate, wildcard timeout
  - `RollbackEvent`: Structured event with breach detection
  - Council-defined thresholds: 8% disagreement, 15% escalation
  - Environment variables: `LLM_COUNCIL_ROLLBACK_ENABLED`, `LLM_COUNCIL_ROLLBACK_WINDOW`

- **Not Diamond API Integration (ADR-020 Tier 1, Issue #59)**: Optional external routing
  - `NotDiamondClient`: API client with caching and graceful fallback
  - `NotDiamondClassifier`: Complexity classification with heuristic fallback
  - `NotDiamondRouter`: Model routing with tier constraint support
  - `NotDiamondConfig`: Configuration from environment variables
  - Graceful degradation to heuristics when API unavailable
  - Environment variables: `NOT_DIAMOND_API_KEY`, `LLM_COUNCIL_USE_NOT_DIAMOND`

### Changed

- 73 new tests for ADR-020 Tier 1 (TDD approach)
- Triage package exports updated with all new modules

## [0.11.1] - 2025-12-22

### Fixed

- **CRITICAL: Gateway Layer Execution Wiring (ADR-024)**
  - `council.py` now imports from `gateway_adapter` instead of `openrouter` directly
  - This enables the gateway layer features (CircuitBreaker, fallback routing) to actually execute
  - Previously, gateway layer code was implemented but never called ("dead code")
  - Gateway wiring is now verified by 4 new integration tests

### Added

- **Gateway Wiring Tests**: `TestGatewayWiring` class in `test_layer_integration.py`
  - `test_council_imports_gateway_adapter`: Verifies council uses gateway_adapter
  - `test_council_module_has_correct_imports`: Validates function object identity
  - `test_gateway_adapter_routes_to_direct_by_default`: Tests backward compatibility
  - `test_gateway_adapter_uses_router_when_enabled`: Tests gateway routing path

## [0.11.0] - 2025-12-22

### Added

- **Integration Testing (ADR-024 Phase 4)**: Comprehensive cross-layer testing
  - 21 integration tests validating layer interactions
  - Tier escalation paths (L1 → L2)
  - Gateway failure isolation (L4 failures NEVER escalate tier)
  - Auto-tier selection via complexity classification
  - End-to-end flow through all four layers
  - Circuit breaker behavior validation
  - Rollback trigger tracking (escalation_rate, fallback_rate)

### Key Invariants Tested

- Gateway failures trigger L4 fallback, NOT L1 tier escalation
- Tier escalation is explicit and logged via LayerEvent
- Layer sovereignty: each layer owns its decision
- Events emitted in layer order (L1 → L2 → L4)

## [0.10.0] - 2025-12-22

### Added

- **Layer Interface Contracts (ADR-024 Phase 3)**: Formal layer boundaries with validation
  - `llm_council.layer_contracts` module formalizing L1→L2→L3→L4 boundaries
  - Re-exports all layer interface types (TierContract, TriageResult, GatewayRequest)
  - `validate_tier_contract()`, `validate_triage_result()`, `validate_gateway_request()`
  - `validate_l1_to_l2_boundary()`, `validate_l2_to_l3_boundary()`, `validate_l3_to_l4_boundary()`

- **Observability Hooks at Layer Boundaries**:
  - `LayerEvent` and `LayerEventType` for event emission
  - `emit_layer_event()`, `get_layer_events()`, `clear_layer_events()`
  - Event types: L1_TIER_SELECTED, L2_TRIAGE_COMPLETE, L4_GATEWAY_REQUEST, etc.
  - Escalation events: L1_TIER_ESCALATION, L2_DELIBERATION_ESCALATION, L4_GATEWAY_FALLBACK

- **Boundary Crossing Helpers**:
  - `cross_l1_to_l2()`, `cross_l2_to_l3()`, `cross_l3_to_l4()`
  - Combined validation + event emission for audit trail

### Changed

- 31 new tests for layer contracts (TDD approach)

## [0.9.0] - 2025-12-22

### Added

- **Unified YAML Configuration (ADR-024 Phase 2)**: Single source of truth for all settings
  - `llm_council.yaml` file support with Pydantic validation
  - Consolidates settings from ADR-020, ADR-022, ADR-023
  - Environment variable substitution with `${VAR_NAME}` syntax
  - Automatic config discovery in current directory and `~/.config/llm-council/`

- **`llm_council.unified_config` module**:
  - `UnifiedConfig`: Main configuration class with all settings
  - `TierConfig`, `TriageConfig`, `GatewayConfig`: Sub-configurations
  - `load_config()`: Load from YAML file with validation
  - `get_effective_config()`: Get config with env var overrides applied
  - `get_config()`, `reload_config()`: Global configuration management

- **Configuration Priority**: YAML > Environment Variables > Defaults
  - All existing environment variables continue to work
  - New YAML configuration is optional and additive

- **Schema Validation**:
  - Invalid tier names rejected (must be: quick, balanced, high, reasoning)
  - Invalid gateway names rejected (must be: openrouter, requesty, direct, auto)
  - Confidence thresholds validated (0.0-1.0 range)
  - Escalation limits validated (0-5 range)

### Changed

- PyYAML added as dependency
- 36 new tests for unified configuration (TDD approach)

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
