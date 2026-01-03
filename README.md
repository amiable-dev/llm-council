<p align="center">
  <a href="https://amiable-dev.github.io/llm-council">
    <img src="https://raw.githubusercontent.com/amiable-dev/llm-council/master/docs/img/logo.svg" alt="LLM Council Logo" width="200">
  </a>
</p>

<h1 align="center">LLM Council Core</h1>

<p align="center">
  <a href="https://github.com/amiable-dev/llm-council/actions/workflows/ci.yml"><img src="https://github.com/amiable-dev/llm-council/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/amiable-dev/llm-council/actions/workflows/security.yml"><img src="https://github.com/amiable-dev/llm-council/actions/workflows/security.yml/badge.svg" alt="Security Scanning"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/amiable-dev/llm-council"><img src="https://api.scorecard.dev/projects/github.com/amiable-dev/llm-council/badge" alt="OpenSSF Scorecard"></a>
  <a href="https://pypi.org/project/llm-council-core/"><img src="https://img.shields.io/pypi/v/llm-council-core.svg" alt="PyPI version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://llm-council.dev"><img src="https://img.shields.io/badge/docs-llm--council.dev-blue" alt="Documentation"></a>
  <a href="https://discord.gg/y467DGHF"><img src="https://img.shields.io/badge/Discord-Join%20Chat-7289da?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://github.com/users/amiable-dev/projects/1"><img src="https://img.shields.io/badge/roadmap-project%20board-blue?logo=github" alt="Roadmap"></a>
</p>

<p align="center">
  <em>A multi-LLM deliberation system where multiple LLMs collaboratively answer questions through peer review and synthesis. Available as a Python library, MCP server, or HTTP API.</em>
</p>

## What is This?

Instead of asking a single LLM for answers, this MCP server:
1. **Stage 1**: Sends your question to multiple LLMs in parallel (GPT, Claude, Gemini, Grok, etc.)
2. **Stage 2**: Each LLM reviews and ranks the other responses (anonymized to prevent bias)
3. **Stage 3**: A Chairman LLM synthesizes all responses into a final, high-quality answer

## Quick Deploy

Deploy your own LLM Council instance:

| Platform | Deploy | Best For |
|----------|--------|----------|
| **Railway** | [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/llm-council?referralCode=K9dsYj) | Production, webhooks |
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/amiable-dev/llm-council) | Evaluation, free tier |

**Required Environment Variables:**
- `OPENROUTER_API_KEY` - Your [OpenRouter](https://openrouter.ai) API key
- `LLM_COUNCIL_API_TOKEN` - A secure token for API authentication (generate with `openssl rand -hex 16`)

> **Note**: Railway is recommended for [n8n integration](https://llm-council.dev/integrations/n8n/) (no cold-start). Render Free tier spins down after 15 minutes which may cause webhook timeouts.

For detailed deployment instructions, see the [Deployment Guide](https://llm-council.dev/deployment/).


## Credits & Attribution

This project is a derivative work based on the original [llm-council](https://github.com/karpathy/llm-council) by Andrej Karpathy.

Karpathy's original README stated:
> "I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like."

...the irony of producing a derivative work that packages the core concept for broader use via the Model Context Protocol!

## Installation

```bash
pip install "llm-council-core[mcp]"
```

For core library only (no MCP server):
```bash
pip install llm-council-core
```

## Setup

### 1. Choose Your Gateway

The council supports three gateway options for accessing LLMs:

| Gateway | Best For | API Keys Needed |
|---------|----------|-----------------|
| **OpenRouter** (default) | Easiest setup, 100+ models via single key | `OPENROUTER_API_KEY` |
| **Requesty** | BYOK mode, analytics, cost tracking | `REQUESTY_API_KEY` + provider keys |
| **Direct** | Maximum control, direct provider APIs | Provider keys (Anthropic, OpenAI, Google) |

**Quick Start (OpenRouter):**
```bash
# Sign up at openrouter.ai and get your API key
export OPENROUTER_API_KEY="sk-or-v1-..."
```

**Direct Provider Access:**
```bash
# Use your existing provider API keys directly
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="..."
export LLM_COUNCIL_DEFAULT_GATEWAY=direct
```

**Requesty with BYOK:**
```bash
export REQUESTY_API_KEY="..."
export ANTHROPIC_API_KEY="sk-ant-..."  # Your own key, routed through Requesty
export LLM_COUNCIL_DEFAULT_GATEWAY=requesty
```

### 2. Store Your API Keys Securely

Choose one of these options (in order of recommendation):

#### Option A: System Keychain (Most Secure)

Store keys encrypted in your OS keychain:

```bash
# Install with keychain support
pip install "llm-council-core[mcp,secure]"

# Store key securely (prompts for key, no echo)
llm-council setup-key

# For CI/CD automation, pipe from stdin:
echo "$OPENROUTER_API_KEY" | llm-council setup-key --stdin
```

#### Option B: Environment Variables

Set in your shell profile (`~/.zshrc`, `~/.bashrc`):

```bash
# OpenRouter (default gateway)
export OPENROUTER_API_KEY="sk-or-v1-..."

# Or use direct provider APIs
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="..."
```

#### Option C: Environment File

Create a `.env` file (ensure it's in `.gitignore`):

```bash
# For OpenRouter
echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env

# Or for direct APIs
cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
LLM_COUNCIL_DEFAULT_GATEWAY=direct
EOF
```

> **Security Note**: Never put API keys in command-line arguments or JSON config files that might be committed to version control.

### 3. Customize Models (Optional)

You can customize which models participate in the council using three methods (in priority order):

#### Option 1: Environment Variables (Recommended)

```bash
# Comma-separated list of council models
export LLM_COUNCIL_MODELS="openai/gpt-4,anthropic/claude-3-opus,google/gemini-pro"

# Chairman model (synthesizes final response)
export LLM_COUNCIL_CHAIRMAN="anthropic/claude-3-opus"
```

#### Option 2: YAML Configuration (Recommended)

Create `llm_council.yaml` in your project root or `~/.config/llm-council/llm_council.yaml`:

```yaml
council:
  # Tier configuration (ADR-022)
  tiers:
    default: high
    pools:
      quick:
        models:
          - openai/gpt-4o-mini
          - anthropic/claude-3-5-haiku-20241022
        timeout_seconds: 30
      balanced:
        models:
          - openai/gpt-4o
          - anthropic/claude-3-5-sonnet-20241022
        timeout_seconds: 90
      high:
        models:
          - openai/gpt-4o
          - anthropic/claude-opus-4-5-20250514
          - google/gemini-3-pro
        timeout_seconds: 180

  # Triage configuration (ADR-020)
  triage:
    enabled: false
    wildcard:
      enabled: true
    prompt_optimization:
      enabled: true

  # Gateway configuration (ADR-023, ADR-025a)
  gateways:
    default: openrouter
    fallback:
      enabled: true
      chain: [openrouter, ollama]  # Can use Ollama as fallback

    # Provider-specific configuration
    providers:
      ollama:
        enabled: true
        base_url: http://localhost:11434
        timeout_seconds: 120.0
        hardware_profile: recommended  # minimum|recommended|professional|enterprise

      openrouter:
        enabled: true
        base_url: https://openrouter.ai/api/v1/chat/completions

  # Webhook notifications (ADR-025a)
  webhooks:
    enabled: false  # Opt-in
    timeout_seconds: 5.0
    max_retries: 3
    https_only: true
    default_events:
      - council.complete
      - council.error

  observability:
    log_escalations: true
```

**Priority**: YAML config > Environment variables > Defaults

#### Option 3: JSON Configuration (Legacy)

Create `~/.config/llm-council/config.json`:

```json
{
  "council_models": [
    "openai/gpt-4-turbo",
    "anthropic/claude-3-opus",
    "google/gemini-pro",
    "meta-llama/llama-3-70b-instruct"
  ],
  "chairman_model": "anthropic/claude-3-opus",
  "synthesis_mode": "consensus",
  "exclude_self_votes": true,
  "style_normalization": false,
  "max_reviewers": null
}
```

#### Option 4: Use Defaults

If you don't configure anything, these defaults are used:
- Council: GPT-5.1, Gemini 3 Pro, Claude Sonnet 4.5, Grok 4
- Chairman: Gemini 3 Pro
- Mode: consensus
- Self-vote exclusion: enabled

**Finding Models**:
- OpenRouter: [openrouter.ai/models](https://openrouter.ai/models)
- Anthropic: [docs.anthropic.com/models](https://docs.anthropic.com/en/docs/about-claude/models)
- OpenAI: [platform.openai.com/docs/models](https://platform.openai.com/docs/models)
- Google: [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models/gemini)

## Usage

### With Claude Code

```bash
# First, store your API key securely (one-time setup)
llm-council setup-key

# Then add the MCP server (key is read from keychain or environment)
claude mcp add --transport stdio llm-council --scope user -- llm-council
```

Then in Claude Code:
```
Consult the LLM council about best practices for error handling
```

### With Claude Desktop

First ensure your API key is available (via keychain, environment variable, or `.env` file).

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "llm-council": {
      "command": "llm-council"
    }
  }
}
```

> **Note**: No `env` block needed—the key is resolved from your system keychain or environment automatically.

### With Other MCP Clients

Any MCP client can use the server by running:
```bash
llm-council
```

## Available Tools

### `consult_council`

Ask the LLM council a question and get synthesized guidance.

**Arguments:**
- `query` (string, required): The question to ask the council
- `confidence` (string, optional): Response quality level (default: "high")
  - `"quick"`: Fast models (mini/flash/haiku), ~30 seconds - fast responses for simple questions
  - `"balanced"`: Mid-tier models (GPT-4o, Sonnet), ~90 seconds - good balance of speed and quality
  - `"high"`: Full council (Opus, GPT-4o), ~180 seconds - comprehensive deliberation
  - `"reasoning"`: Deep thinking models (GPT-5.2, o1, DeepSeek-R1), ~600 seconds - complex reasoning
- `include_details` (boolean, optional): Include individual model responses and rankings (default: false)
- `verdict_type` (string, optional): Type of verdict to render (default: "synthesis")
  - `"synthesis"`: Free-form natural language synthesis
  - `"binary"`: Go/no-go decision (approved/rejected) with confidence score
  - `"tie_breaker"`: Chairman resolves deadlocked decisions
- `include_dissent` (boolean, optional): Extract minority opinions from Stage 2 (default: false)

**Example:**
```
Use consult_council to ask: "What are the trade-offs between microservices and monolithic architecture?"
```

**Example with confidence level:**
```
Use consult_council with confidence="quick" to ask: "What's the syntax for a Python list comprehension?"
```

**Example with Jury Mode (binary verdict):**
```
Use consult_council with verdict_type="binary" and include_dissent=true to ask: "Should we approve this PR that adds caching?"
```

### `council_health_check`

Verify the council is working before expensive operations. Returns API connectivity status, configured models, and estimated response times.

**Arguments:** None

**Returns:**
- `api_key_configured`: Whether an API key was found
- `key_source`: Where the key came from ("environment", "keychain", or "config_file")
- `council_size`: Number of models in the council
- `estimated_duration`: Expected response times for each confidence level
- `ready`: Whether the council is ready to accept queries

**Example:**
```
Run council_health_check to verify the LLM council is working
```

## How It Works

The council uses a multi-stage process inspired by ensemble methods and peer review:

```
User Query
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 1: Independent Responses              │
│ • All council models queried in parallel    │
│ • No knowledge of other responses           │
│ • Graceful degradation if some fail         │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 1.5: Style Normalization (optional)   │
│ • Rewrites responses in neutral style       │
│ • Removes AI preambles and fingerprints     │
│ • Strengthens anonymization                 │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 2: Anonymous Peer Review              │
│ • Responses labeled A, B, C (randomized)    │
│ • XML sandboxing prevents prompt injection  │
│ • JSON-structured rankings with scores      │
│ • Self-votes excluded from aggregation      │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 3: Chairman Synthesis                 │
│ • Receives all responses + rankings         │
│ • Consensus mode: single best answer        │
│ • Debate mode: highlights disagreements     │
└─────────────────────────────────────────────┘
    ↓
Final Response + Metadata
```

This approach helps surface diverse perspectives, identify consensus, and produce more balanced, well-reasoned answers.

## Advanced Features

### Self-Vote Exclusion

By default, each model's vote for its own response is excluded from the aggregate rankings. This prevents self-preference bias.

```bash
export LLM_COUNCIL_EXCLUDE_SELF_VOTES=true  # default
```

### Synthesis Modes

**Consensus Mode** (default): Chairman synthesizes a single best answer.

**Debate Mode**: Chairman highlights areas of agreement, key disagreements, and trade-offs between perspectives.

```bash
export LLM_COUNCIL_MODE=debate
```

### Style Normalization (Stage 1.5)

Optional preprocessing that rewrites all responses in a neutral style before peer review. This strengthens anonymization by removing stylistic "fingerprints" that might allow models to recognize each other.

```bash
export LLM_COUNCIL_STYLE_NORMALIZATION=true
export LLM_COUNCIL_NORMALIZER_MODEL=google/gemini-2.0-flash-001  # fast/cheap
```

### Stratified Sampling (Large Councils)

For councils with more than 5 models, you can limit the number of reviewers per response to reduce API costs (O(N²) → O(N×k)):

```bash
export LLM_COUNCIL_MAX_REVIEWERS=3
```

### Reliability Features

The council includes built-in reliability features for long-running operations:

**Tiered Timeouts**: Graceful degradation under time pressure:
- Per-model soft deadline: 15s (start planning fallback)
- Per-model hard deadline: 25s (abandon slow model)
- Global synthesis trigger: 40s (must start synthesis)
- Response deadline: 50s (must return something)

**Partial Results**: If some models timeout, the council returns results from the models that responded, with a clear warning indicating which models were excluded.

**Confidence Levels**: Use the `confidence` parameter to trade off speed vs. thoroughness:
- `quick`: ~20-30 seconds (fastest models)
- `balanced`: ~45-60 seconds (most models)
- `high`: ~60-90 seconds (full council, default)

**Progress Feedback**: During deliberation, progress updates show which models have responded and which are still pending:
```
✓ claude-opus-4.5 (1/4) | waiting: gpt-5.1, gemini-3-pro, grok-4
✓ gemini-3-pro (2/4) | waiting: gpt-5.1, grok-4
```

### Jury Mode (ADR-025b)

Transform the council from a "summary generator" to a "decision engine" with structured verdicts.

**Verdict Types:**

| Mode | Output | Use Case |
|------|--------|----------|
| `synthesis` (default) | Free-form synthesis | General questions, exploration |
| `binary` | approved/rejected + confidence | CI/CD gates, PR reviews, policy checks |
| `tie_breaker` | Chairman decides on deadlock | Contentious decisions |

**Binary Verdict Mode:**

Returns structured go/no-go decisions with confidence scores:

```python
# MCP Tool
result = await consult_council(
    query="Should we approve this architectural change?",
    verdict_type="binary"
)

# Returns:
{
  "verdict": "approved",      # or "rejected"
  "confidence": 0.75,         # 0.0-1.0 based on council agreement
  "rationale": "Council agreed the change improves modularity..."
}
```

**Tie-Breaker Mode:**

When the council is deadlocked (top scores within 0.1 of each other), the chairman casts the deciding vote:

```python
result = await consult_council(
    query="Option A vs Option B for caching strategy?",
    verdict_type="binary"
)

# If deadlocked, returns:
{
  "verdict": "approved",
  "confidence": 0.60,
  "rationale": "Chairman resolved deadlock based on...",
  "deadlocked": true  # Flag indicates tie-breaker was needed
}
```

**Constructive Dissent:**

Extract minority opinions from Stage 2 peer reviews:

```python
result = await consult_council(
    query="Should we migrate to microservices?",
    verdict_type="binary",
    include_dissent=True
)

# Returns:
{
  "verdict": "approved",
  "confidence": 0.70,
  "rationale": "Majority supports migration...",
  "dissent": "Minority perspective: One reviewer noted scalability concerns with current team size."
}
```

**Dissent Algorithm:**
1. Collect all scores from Stage 2 peer reviews
2. Calculate median and standard deviation per response
3. Identify outliers (score < median - 1.5 × std)
4. Extract evaluation text from outliers
5. Format as minority perspective

**Example: CI/CD Gate Integration:**

```python
import asyncio
from llm_council.council import run_full_council
from llm_council.verdict import VerdictType

async def review_pull_request(pr_diff: str, pr_description: str):
    """Use LLM Council as a PR review gate."""
    query = f"""
    Review this pull request and determine if it should be approved.

    Description: {pr_description}

    Changes:
    {pr_diff}
    """

    stage1, stage2, stage3, metadata = await run_full_council(
        query,
        verdict_type=VerdictType.BINARY,
        include_dissent=True
    )

    verdict = metadata.get("verdict", {})

    if verdict.get("verdict") == "approved" and verdict.get("confidence", 0) >= 0.7:
        return True, verdict.get("rationale")
    else:
        return False, f"{verdict.get('rationale')}\n\nDissent: {verdict.get('dissent', 'None')}"
```

**Environment Variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_COUNCIL_VERDICT_TYPE` | Default verdict type | synthesis |
| `LLM_COUNCIL_DEADLOCK_THRESHOLD` | Borda score difference for deadlock | 0.1 |
| `LLM_COUNCIL_DISSENT_THRESHOLD` | Std deviations below median for outlier | 1.5 |
| `LLM_COUNCIL_MIN_BORDA_SPREAD` | Minimum spread to surface dissent | 0.0 |

### Structured Rubric Scoring (ADR-016)

By default, reviewers provide a single 1-10 holistic score. With rubric scoring enabled, reviewers score each response on five dimensions:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| **Accuracy** | 35% | Factual correctness, no hallucinations |
| **Relevance** | 10% | Addresses the actual question asked |
| **Completeness** | 20% | Covers all aspects of the question |
| **Conciseness** | 15% | Efficient communication, no padding |
| **Clarity** | 20% | Well-organized, easy to understand |

**Accuracy Ceiling**: When enabled (default), accuracy acts as a ceiling on the overall score:
- Accuracy < 5: Score caps at 4.0 (40%) — "significant errors or worse"
- Accuracy 5-6: Score caps at 7.0 (70%) — "mixed accuracy"
- Accuracy ≥ 7: No ceiling — "mostly accurate or better"

This prevents well-written hallucinations from ranking well.

**Scoring Anchors**: Each score level has defined behavioral meaning (see [ADR-016](docs/adr/ADR-016-structured-rubric-scoring.md)):
- 9-10: Excellent (completely accurate, comprehensive, crystal clear)
- 7-8: Good (mostly accurate, covers main points)
- 5-6: Mixed (some errors or gaps)
- 3-4: Poor (significant issues)
- 1-2: Failing (fundamentally flawed)

```bash
# Enable rubric scoring
export LLM_COUNCIL_RUBRIC_SCORING=true

# Customize weights (must sum to 1.0)
export LLM_COUNCIL_WEIGHT_ACCURACY=0.40
export LLM_COUNCIL_WEIGHT_RELEVANCE=0.10
export LLM_COUNCIL_WEIGHT_COMPLETENESS=0.20
export LLM_COUNCIL_WEIGHT_CONCISENESS=0.10
export LLM_COUNCIL_WEIGHT_CLARITY=0.20
```

### Safety Gate (ADR-016)

When enabled, a pass/fail safety check runs before rubric scoring to filter harmful content:

| Pattern | Description |
|---------|-------------|
| **dangerous_instructions** | Weapons, explosives, harmful devices |
| **weapon_making** | Firearm/weapon construction |
| **malware_hacking** | Unauthorized access, malware |
| **self_harm** | Self-harm encouragement |
| **pii_exposure** | Personal information leakage |

Responses that fail safety checks are capped at score 0 regardless of other dimension scores. Educational/defensive content is context-aware and allowed.

```bash
# Enable safety gate
export LLM_COUNCIL_SAFETY_GATE=true

# Customize score cap (default: 0)
export LLM_COUNCIL_SAFETY_SCORE_CAP=0.0
```

### Bias Auditing (ADR-015)

When enabled, the council reports per-session bias indicators from peer review scoring:

| Bias Type | Description | Detection Threshold |
|-----------|-------------|---------------------|
| **Length-Score Correlation** | Do longer responses score higher? | \|r\| > 0.3 |
| **Reviewer Calibration** | Are some reviewers harsh/generous relative to peers? | Mean ± 1 std from median |
| **Position Bias** | Does presentation order affect scores? | Variance > 0.5 |

**Output**: The metadata includes a `bias_audit` object with:
- `length_score_correlation`: Pearson correlation coefficient
- `length_bias_detected`: Boolean flag
- `position_score_variance`: Variance of mean scores by presentation position
- `position_bias_detected`: Boolean flag (derived from anonymization labels A, B, C...)
- `harsh_reviewers` / `generous_reviewers`: Lists of biased reviewers
- `overall_bias_risk`: "low", "medium", or "high"

**Important Limitations**: With only 4-5 models per session, these metrics have limited statistical power:
- Length correlation with n=5 data points can only detect *extreme* biases
- Position bias from a single ordering cannot distinguish position effects from quality differences
- Reviewer calibration is relative to the current session only

These are **per-session indicators** (red flags for extreme anomalies), not statistically robust proof of systematic bias. Interpret with appropriate caution.

```bash
# Enable bias auditing
export LLM_COUNCIL_BIAS_AUDIT=true

# Customize thresholds (optional)
export LLM_COUNCIL_LENGTH_CORRELATION_THRESHOLD=0.3
export LLM_COUNCIL_POSITION_VARIANCE_THRESHOLD=0.5
```

### Cross-Session Bias Aggregation (ADR-018)

For statistically meaningful bias detection across multiple sessions, enable bias persistence:

```bash
# Enable bias persistence (stores metrics locally)
export LLM_COUNCIL_BIAS_PERSISTENCE=true

# Consent level: 0=off, 1=local only (default), 2=anonymous, 3=enhanced, 4=research
export LLM_COUNCIL_BIAS_CONSENT=1

# Store path (default: ~/.llm-council/bias_metrics.jsonl)
export LLM_COUNCIL_BIAS_STORE=~/.llm-council/bias_metrics.jsonl
```

**Generate cross-session bias reports:**

```bash
# Text report (default)
llm-council bias-report

# JSON output
llm-council bias-report --format json

# Include detailed reviewer profiles
llm-council bias-report --verbose

# Limit to last 50 sessions
llm-council bias-report --sessions 50
```

**Statistical confidence tiers:**

| Sessions | Confidence | UI Treatment |
|----------|------------|--------------|
| N < 10 | Insufficient | "Collecting data..." |
| 10-19 | Preliminary | Warning shown |
| 20-49 | Moderate | CIs displayed |
| N >= 50 | High | Full analysis |

### Output Quality Metrics (ADR-036)

Quantify the reliability and quality of council outputs with three core metrics:

| Metric | Range | Description |
|--------|-------|-------------|
| **Consensus Strength Score (CSS)** | 0.0-1.0 | Agreement among council members in Stage 2 rankings |
| **Deliberation Depth Index (DDI)** | 0.0-1.0 | Thoroughness of the deliberation process |
| **Synthesis Attribution Score (SAS)** | 0.0-1.0 | How well synthesis traces back to source responses |

**CSS Interpretation:**

| Score | Interpretation | Action |
|-------|---------------|--------|
| 0.85+ | Strong consensus | High confidence in synthesis |
| 0.70-0.84 | Moderate consensus | Note minority views |
| 0.50-0.69 | Weak consensus | Consider `include_dissent=true` |
| <0.50 | Significant disagreement | Use debate mode |

**SAS Components:**
- `winner_alignment`: Similarity to top-ranked responses
- `max_source_alignment`: Best match to any response
- `hallucination_risk`: 1 - max_source_alignment
- `grounded`: True if synthesis traces to sources (threshold: 0.6)

**Usage:**

Quality metrics are automatically included in metadata:

```python
stage1, stage2, stage3, metadata = await run_full_council(query)

quality = metadata.get("quality_metrics", {})
core = quality.get("core", {})

print(f"Consensus: {core['consensus_strength']:.2f}")
print(f"Depth: {core['deliberation_depth']:.2f}")
print(f"Grounded: {core['synthesis_attribution']['grounded']}")
```

**MCP Tool Output:**

The `consult_council` MCP tool displays quality metrics with visual bars:

```
### Quality Metrics
- **Consensus Strength**: 0.82 [████████░░]
- **Deliberation Depth**: 0.74 [███████░░░]
- **Synthesis Grounded**: ✓ (alignment: 0.89)
```

**Environment Variables:**

```bash
# Enable/disable quality metrics (default: true)
export LLM_COUNCIL_QUALITY_METRICS=true

# Quality tier: core (OSS), standard, enterprise
export LLM_COUNCIL_QUALITY_TIER=core
```

### Gateway Layer (ADR-023)

The gateway layer provides an abstraction over LLM API requests with multiple gateway options:

**Available Gateways:**
| Gateway | Description | Key Features |
|---------|-------------|--------------|
| `OpenRouterGateway` | Routes through OpenRouter | 100+ models, single API key |
| `RequestyGateway` | Routes through Requesty | BYOK support, analytics |
| `DirectGateway` | Direct provider APIs | Anthropic, OpenAI, Google |
| `OllamaGateway` | Local LLMs via Ollama | Air-gapped, cost-free, privacy-first |

**Core Features:**
- **Circuit Breaker**: Prevents cascading failures (CLOSED → OPEN → HALF_OPEN → CLOSED)
- **Fallback Chains**: Automatic retry with secondary gateways on failure
- **Per-Gateway Metrics**: Track failure counts, latency, and health status
- **BYOK Support**: Bring Your Own Key for Requesty and Direct gateways

**Basic Usage:**

```python
from llm_council.gateway import (
    GatewayRouter, GatewayRequest, CanonicalMessage, ContentBlock,
    OpenRouterGateway, RequestyGateway, DirectGateway
)

# Single gateway (OpenRouter)
router = GatewayRouter()

# Multi-gateway with fallback
router = GatewayRouter(
    gateways={
        "openrouter": OpenRouterGateway(),
        "requesty": RequestyGateway(byok_enabled=True, byok_keys={"anthropic": "sk-ant-..."}),
        "direct": DirectGateway(provider_keys={"openai": "sk-..."}),
    },
    default_gateway="openrouter",
    fallback_chains={"openrouter": ["requesty", "direct"]}
)

request = GatewayRequest(
    model="openai/gpt-4o",
    messages=[CanonicalMessage(role="user", content=[ContentBlock(type="text", text="Hello")])]
)
response = await router.complete(request)
```

**Enable the gateway layer:**

```bash
export LLM_COUNCIL_USE_GATEWAY=true

# Optional: Configure specific gateways
export REQUESTY_API_KEY=your-requesty-key    # For Requesty
export ANTHROPIC_API_KEY=sk-ant-...           # For Direct (Anthropic)
export OPENAI_API_KEY=sk-...                  # For Direct (OpenAI)
export GOOGLE_API_KEY=...                     # For Direct (Google)
```

**Circuit Breaker Behavior:**
- Default: 5 failures to trip the circuit
- Recovery timeout: 60 seconds
- Half-open state allows test requests to check recovery
- Open circuits are skipped in fallback chain

The gateway layer is currently **opt-in** (default: disabled) for backward compatibility.

### Triage Layer (ADR-020)

The triage layer provides query classification, model selection optimizations, and confidence-gated routing:

- **Confidence-Gated Fast Path**: Routes simple queries to a single model, escalating to full council when confidence is low
- **Shadow Council Sampling**: Random 5% sampling validates fast path quality against full council
- **Rollback Monitoring**: Automatic rollback when disagreement/escalation rates breach thresholds
- **Wildcard Selection**: Adds domain-specialized models to the council based on query classification
- **Prompt Optimization**: Per-model prompt adaptation (Claude gets XML, OpenAI gets Markdown)
- **Complexity Classification**: Heuristic-based with optional Not Diamond API integration

**Domain Categories:**
| Domain | Description | Specialist Models |
|--------|-------------|-------------------|
| CODE | Programming, debugging, algorithms | DeepSeek, Codestral |
| REASONING | Math, logic, proofs | o1-preview, DeepSeek-R1 |
| CREATIVE | Stories, poems, fiction | Claude Opus, Command-R+ |
| MULTILINGUAL | Translation, language | GPT-4o, Command-R+ |
| GENERAL | General knowledge | Llama 3 (fallback) |

**Enable wildcard selection:**

```bash
export LLM_COUNCIL_WILDCARD_ENABLED=true
```

This automatically adds a domain specialist to the council based on query classification. For example, a Python coding question will add a DeepSeek model alongside the default council.

**Enable prompt optimization:**

```bash
export LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED=true
```

This applies per-model prompt formatting. Claude receives XML-structured prompts, while other providers receive their preferred format.

**Enable confidence-gated fast path:**

```bash
export LLM_COUNCIL_FAST_PATH_ENABLED=true
export LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD=0.92  # default
```

When enabled, simple queries are routed to a single model. If the model's confidence is below the threshold, the query automatically escalates to the full council. This can reduce costs by 45-55% on simple queries while maintaining quality.

**Fast Path Quality Monitoring:**

The fast path includes built-in quality monitoring:

| Metric | Threshold | Action |
|--------|-----------|--------|
| Shadow disagreement rate | > 8% | Automatic rollback |
| User escalation rate | > 15% | Automatic rollback |
| Error rate | > 1.5x baseline | Automatic rollback |

Configure monitoring:

```bash
export LLM_COUNCIL_SHADOW_SAMPLE_RATE=0.05  # 5% shadow sampling
export LLM_COUNCIL_ROLLBACK_ENABLED=true
export LLM_COUNCIL_ROLLBACK_WINDOW=100  # rolling window size
```

**Optional Not Diamond Integration:**

For advanced model routing, integrate with [Not Diamond](https://notdiamond.ai):

```bash
export NOT_DIAMOND_API_KEY="your-key"
export LLM_COUNCIL_USE_NOT_DIAMOND=true
```

When Not Diamond is unavailable, the system gracefully falls back to heuristic-based classification.

The triage layer is currently **opt-in** (default: disabled) for backward compatibility.

### Local LLM Support (ADR-025)

Run council deliberations entirely on local hardware using Ollama:

```bash
# Install with Ollama support
pip install "llm-council-core[ollama]"

# Start Ollama (if not already running)
ollama serve

# Pull a model
ollama pull llama3.2
```

**Use local models in your council:**

```bash
# Mix local and cloud models
export LLM_COUNCIL_MODELS="ollama/llama3.2,openai/gpt-4o,anthropic/claude-3-5-sonnet"

# Or use only local models (air-gapped mode)
export LLM_COUNCIL_MODELS="ollama/llama3.2,ollama/mistral,ollama/codellama"
export LLM_COUNCIL_CHAIRMAN="ollama/llama3.2"
```

**Hardware Requirements:**

| Profile | Hardware | Models | Use Case |
|---------|----------|--------|----------|
| Minimum | 8+ core CPU, 16GB RAM | 7B quantized | Dev/testing |
| Recommended | M-series Pro, 32GB unified | 7B-13B | Small council |
| Professional | 2x RTX 4090, 64GB+ | 70B quantized | Production |
| Enterprise | Mac Studio 64GB+ | Multiple 70B | Air-gapped |

**Quality Degradation Notice**: Local models typically have reduced capabilities compared to cloud-hosted frontier models. The gateway includes quality notices in responses to inform users when local models are used.

**Configuration:**

```bash
# Ollama endpoint (default: http://localhost:11434)
export LLM_COUNCIL_OLLAMA_BASE_URL=http://localhost:11434

# Timeout for local models (default: 120s - first load can be slow)
export LLM_COUNCIL_OLLAMA_TIMEOUT=120.0
```

### Webhook Notifications (ADR-025)

Receive real-time notifications as the council deliberates:

```python
from llm_council.webhooks import WebhookConfig, WebhookDispatcher, WebhookPayload

# Configure webhook endpoint
config = WebhookConfig(
    url="https://your-server.com/webhook",
    events=["council.complete", "council.error"],
    secret="your-hmac-secret"  # Optional, for signature verification
)

# Dispatch events (used internally by council)
dispatcher = WebhookDispatcher()
result = await dispatcher.dispatch(config, payload)
```

**Event Types:**

| Event | Description | Payload |
|-------|-------------|---------|
| `council.deliberation_start` | Council begins | request_id, models |
| `council.stage1.complete` | All initial responses received | response_count |
| `model.vote_cast` | A model submitted rankings | voter, ranking |
| `council.stage2.complete` | All rankings complete | aggregate_rankings |
| `council.complete` | Final answer ready | stage3_response, duration_ms |
| `council.error` | Error occurred | error, partial_results |

**HMAC Signature Verification:**

Webhooks are signed using HMAC-SHA256 for security:

```python
from llm_council.webhooks import verify_webhook_request

# Verify incoming webhook (in your server)
is_valid = verify_webhook_request(
    payload=request.body,
    headers=request.headers,
    secret="your-hmac-secret"
)
```

Headers included:
- `X-Council-Signature`: `sha256=<hex-digest>`
- `X-Council-Timestamp`: Unix timestamp
- `X-Council-Version`: `1.0`

**Configuration:**

```bash
# Webhook timeout (default: 5s)
export LLM_COUNCIL_WEBHOOK_TIMEOUT=5.0

# Max retry attempts (default: 3)
export LLM_COUNCIL_WEBHOOK_RETRIES=3

# Require HTTPS (except localhost) - default: true
export LLM_COUNCIL_WEBHOOK_HTTPS_ONLY=true
```

### SSE Streaming (ADR-025)

Stream council events in real-time using Server-Sent Events.

**Built-in HTTP Server:**

The library includes a built-in HTTP server with SSE streaming:

```bash
# Install with HTTP server support
pip install "llm-council-core[http]"

# Start the server
llm-council serve
```

The SSE endpoint is available at `GET /v1/council/stream`:

```bash
# Stream council deliberation
curl -N "http://localhost:8000/v1/council/stream?prompt=What+is+AI"
```

**Custom Integration:**

For custom FastAPI/Starlette applications:

```python
from llm_council.webhooks import (
    council_event_generator,
    SSE_CONTENT_TYPE,
    get_sse_headers
)

# In your FastAPI/Starlette endpoint
@app.get("/v1/council/stream")
async def stream_council(prompt: str):
    return StreamingResponse(
        council_event_generator(prompt, models=None, api_key=None),
        media_type=SSE_CONTENT_TYPE,
        headers=get_sse_headers()
    )
```

**Client-side (JavaScript):**

```javascript
const source = new EventSource('/v1/council/stream?prompt=...');

source.addEventListener('council.deliberation_start', (e) => {
  console.log('Started:', JSON.parse(e.data));
});

source.addEventListener('council.complete', (e) => {
  const result = JSON.parse(e.data);
  console.log('Final answer:', result.stage3_response);
  source.close();
});
```

### Offline Mode (ADR-026)

Run LLM Council without any external metadata calls using the bundled model registry:

```bash
# Enable offline mode
export LLM_COUNCIL_OFFLINE=true
```

When offline mode is enabled:
- Uses `StaticRegistryProvider` exclusively with 31 bundled models
- No external API calls for metadata (context windows, pricing, capabilities)
- All core council operations continue to work
- Unknown models use safe defaults (4096 context window)

This implements the "Sovereign Orchestrator" philosophy: the system must function as a complete, independent utility without external dependencies.

**Bundled Models (31 total):**

| Provider | Count | Examples |
|----------|-------|----------|
| OpenAI | 7 | gpt-4o, gpt-4o-mini, o1, o1-preview, o1-mini, o3-mini, gpt-5.2-pro |
| Anthropic | 5 | claude-opus-4.5, claude-3-5-sonnet, claude-3-5-haiku |
| Google | 5 | gemini-3-pro, gemini-2.5-pro, gemini-2.0-flash, gemini-1.5-pro |
| xAI | 2 | grok-4, grok-4.1-fast |
| DeepSeek | 2 | deepseek-r1, deepseek-chat |
| Meta | 2 | llama-3.3-70b, llama-3.1-405b |
| Mistral | 2 | mistral-large-2411, mistral-medium |
| Ollama | 6 | llama3.2, mistral, qwen2.5:14b, codellama, phi3 |

**Model Metadata API:**

```python
from llm_council.metadata import get_provider

# Get the metadata provider
provider = get_provider()

# Query model information
info = provider.get_model_info("openai/gpt-4o")
print(f"Context window: {info.context_window}")  # 128000
print(f"Quality tier: {info.quality_tier}")      # frontier

# Check capabilities
window = provider.get_context_window("anthropic/claude-opus-4.5")  # 200000
supports = provider.supports_reasoning("openai/o1")  # True

# List all available models
models = provider.list_available_models()  # 31 models
```

### Agent Skills (ADR-034)

LLM Council includes agent skills for AI-assisted code verification, review, and CI/CD quality gates. Skills use progressive disclosure to minimize token usage while providing detailed scoring rubrics when needed.

**Available Skills:**

| Skill | Category | Use Case |
|-------|----------|----------|
| `council-verify` | verification | General work verification with multi-dimensional scoring |
| `council-review` | code-review | PR reviews with security, performance, and testing focus |
| `council-gate` | ci-cd | Quality gates for pipelines with exit codes (0=PASS, 1=FAIL, 2=UNCLEAR) |

**Exit Codes for CI/CD:**

```bash
# In GitHub Actions or any CI pipeline
llm-council gate --snapshot $GITHUB_SHA --rubric-focus Security

# Exit codes:
# 0 = PASS (confidence >= threshold, no blocking issues)
# 1 = FAIL (blocking issues present)
# 2 = UNCLEAR (needs human review)
```

**Skills are located in `.github/skills/`** and work with Claude Code, VS Code Copilot, Cursor, and other MCP-compatible clients.

For detailed documentation, see the [Skills Guide](https://llm-council.dev/guides/skills/).

### All Environment Variables

#### Gateway Configuration (ADR-023)

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key | Required for OpenRouter gateway |
| `REQUESTY_API_KEY` | Requesty API key | Required for Requesty gateway |
| `ANTHROPIC_API_KEY` | Anthropic API key | Required for Direct gateway (Anthropic) |
| `OPENAI_API_KEY` | OpenAI API key | Required for Direct gateway (OpenAI) |
| `GOOGLE_API_KEY` | Google API key | Required for Direct gateway (Google) |
| `LLM_COUNCIL_DEFAULT_GATEWAY` | Default gateway (openrouter/requesty/direct) | openrouter |
| `LLM_COUNCIL_USE_GATEWAY` | Enable gateway layer with circuit breaker | false |

#### Ollama Configuration (ADR-025)

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_COUNCIL_OLLAMA_BASE_URL` | Ollama API endpoint | http://localhost:11434 |
| `LLM_COUNCIL_OLLAMA_TIMEOUT` | Timeout for Ollama requests (seconds) | 120.0 |
| `LLM_COUNCIL_USE_LITELLM` | Enable LiteLLM wrapper for Ollama | true |

#### Webhook Configuration (ADR-025)

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_COUNCIL_WEBHOOK_TIMEOUT` | Webhook POST timeout (seconds) | 5.0 |
| `LLM_COUNCIL_WEBHOOK_RETRIES` | Max retry attempts | 3 |
| `LLM_COUNCIL_WEBHOOK_HTTPS_ONLY` | Require HTTPS (except localhost) | true |

#### Council Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_COUNCIL_MODELS` | Comma-separated model list | GPT-5.1, Gemini 3 Pro, Claude 4.5, Grok 4 |
| `LLM_COUNCIL_CHAIRMAN` | Chairman model | google/gemini-3-pro-preview |
| `LLM_COUNCIL_MODE` | `consensus` or `debate` | consensus |
| `LLM_COUNCIL_EXCLUDE_SELF_VOTES` | Exclude self-votes | true |
| `LLM_COUNCIL_STYLE_NORMALIZATION` | Enable style normalization | false |
| `LLM_COUNCIL_NORMALIZER_MODEL` | Model for normalization | google/gemini-2.0-flash-001 |
| `LLM_COUNCIL_MAX_REVIEWERS` | Max reviewers per response | null (all) |
| `LLM_COUNCIL_RUBRIC_SCORING` | Enable multi-dimensional rubric scoring | false |
| `LLM_COUNCIL_ACCURACY_CEILING` | Use accuracy as score ceiling | true |
| `LLM_COUNCIL_WEIGHT_*` | Rubric dimension weights (ACCURACY, RELEVANCE, COMPLETENESS, CONCISENESS, CLARITY) | See above |
| `LLM_COUNCIL_SAFETY_GATE` | Enable safety pre-check gate | false |
| `LLM_COUNCIL_SAFETY_SCORE_CAP` | Score cap for failed safety checks | 0.0 |
| `LLM_COUNCIL_BIAS_AUDIT` | Enable bias auditing (ADR-015) | false |
| `LLM_COUNCIL_LENGTH_CORRELATION_THRESHOLD` | Length-score correlation threshold for bias detection | 0.3 |
| `LLM_COUNCIL_POSITION_VARIANCE_THRESHOLD` | Position variance threshold for bias detection | 0.5 |
| `LLM_COUNCIL_BIAS_PERSISTENCE` | Enable cross-session bias storage (ADR-018) | false |
| `LLM_COUNCIL_BIAS_STORE` | Path to bias metrics JSONL file | ~/.llm-council/bias_metrics.jsonl |
| `LLM_COUNCIL_BIAS_CONSENT` | Consent level: 0=off, 1=local, 2=anonymous, 3=enhanced, 4=research | 1 |
| `LLM_COUNCIL_BIAS_WINDOW_SESSIONS` | Rolling window: max sessions for aggregation | 100 |
| `LLM_COUNCIL_BIAS_WINDOW_DAYS` | Rolling window: max days for aggregation | 30 |
| `LLM_COUNCIL_MIN_BIAS_SESSIONS` | Minimum sessions for aggregation analysis | 20 |
| `LLM_COUNCIL_HASH_SECRET` | Secret for query hashing (RESEARCH consent only) | dev-secret |
| `LLM_COUNCIL_SUPPRESS_WARNINGS` | Suppress security warnings | false |
| `LLM_COUNCIL_MODELS_QUICK` | Models for quick tier (ADR-022) | gpt-4o-mini, haiku, gemini-flash |
| `LLM_COUNCIL_MODELS_BALANCED` | Models for balanced tier (ADR-022) | gpt-4o, sonnet, gemini-pro |
| `LLM_COUNCIL_MODELS_HIGH` | Models for high tier (ADR-022) | gpt-4o, opus, gemini-3-pro, grok-4 |
| `LLM_COUNCIL_MODELS_REASONING` | Models for reasoning tier (ADR-022) | gpt-5.2-pro, opus, o1-preview, deepseek-r1 |
| `LLM_COUNCIL_WILDCARD_ENABLED` | Enable wildcard specialist selection (ADR-020) | false |
| `LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED` | Enable per-model prompt optimization (ADR-020) | false |
| `LLM_COUNCIL_FAST_PATH_ENABLED` | Enable confidence-gated fast path (ADR-020) | false |
| `LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD` | Confidence threshold for fast path (0.0-1.0) | 0.92 |
| `LLM_COUNCIL_FAST_PATH_MODEL` | Model for fast path routing | auto |
| `LLM_COUNCIL_SHADOW_SAMPLE_RATE` | Shadow sampling rate (0.0-1.0) | 0.05 |
| `LLM_COUNCIL_SHADOW_DISAGREEMENT_THRESHOLD` | Disagreement threshold for shadow samples | 0.08 |
| `LLM_COUNCIL_ROLLBACK_ENABLED` | Enable rollback metric tracking | true |
| `LLM_COUNCIL_ROLLBACK_WINDOW` | Rolling window size for metrics | 100 |
| `LLM_COUNCIL_ROLLBACK_DISAGREEMENT_THRESHOLD` | Shadow disagreement rollback threshold | 0.08 |
| `LLM_COUNCIL_ROLLBACK_ESCALATION_THRESHOLD` | User escalation rollback threshold | 0.15 |
| `NOT_DIAMOND_API_KEY` | Not Diamond API key (optional) | - |
| `LLM_COUNCIL_USE_NOT_DIAMOND` | Enable Not Diamond API integration | false |
| `LLM_COUNCIL_NOT_DIAMOND_TIMEOUT` | Not Diamond API timeout in seconds | 5.0 |
| `LLM_COUNCIL_NOT_DIAMOND_CACHE_TTL` | Not Diamond response cache TTL in seconds | 300 |

## Credits & Attribution Continued

This project is a derivative work based on the original [llm-council](https://github.com/karpathy/llm-council) by Andrej Karpathy.

**Original Work:**
- Concept and 3-stage council orchestration: Andrej Karpathy
- Core council logic (Stage 1-3 process)
- OpenRouter integration

**Derivative Work by Amiable:**
- MCP (Model Context Protocol) server implementation
- Removal of web frontend (focus on MCP functionality)
- Python package structure for PyPI distribution
- User-configurable model selection
- Enhanced features (style normalization, self-vote exclusion, synthesis modes)
- Test suite and modern packaging standards

## License

MIT License - see [LICENSE](LICENSE) file for details.
