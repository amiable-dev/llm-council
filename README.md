# LLM Council Core

[![PyPI version](https://img.shields.io/pypi/v/llm-council-core.svg)](https://pypi.org/project/llm-council-core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A multi-LLM deliberation system where multiple LLMs collaboratively answer questions through peer review and synthesis. Available as a Python library, MCP server, or HTTP API.

## What is This?

Instead of asking a single LLM for answers, this MCP server:
1. **Stage 1**: Sends your question to multiple LLMs in parallel (GPT, Claude, Gemini, Grok, etc.)
2. **Stage 2**: Each LLM reviews and ranks the other responses (anonymized to prevent bias)
3. **Stage 3**: A Chairman LLM synthesizes all responses into a final, high-quality answer

## Installation

```bash
pip install "llm-council-core[mcp]"
```

For core library only (no MCP server):
```bash
pip install llm-council-core
```

## Setup

### 1. Get an OpenRouter API Key

The council uses [OpenRouter](https://openrouter.ai/) to access multiple LLMs:
1. Sign up at [openrouter.ai](https://openrouter.ai/)
2. Add credits or enable auto-top-up
3. Get your API key from the dashboard

### 2. Store Your API Key Securely

Choose one of these options (in order of recommendation):

#### Option A: System Keychain (Most Secure)

Store your key encrypted in your OS keychain:

```bash
# Install with keychain support
pip install "llm-council-core[mcp,secure]"

# Store key securely (prompts for key, no echo)
llm-council setup-key

# For CI/CD automation, pipe from stdin:
echo "$OPENROUTER_API_KEY" | llm-council setup-key --stdin
```

#### Option B: Environment Variable

Set in your shell profile (`~/.zshrc`, `~/.bashrc`):

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

#### Option C: Environment File

Create a `.env` file (ensure it's in `.gitignore`):

```bash
echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env
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

  # Gateway configuration (ADR-023)
  gateways:
    default: openrouter
    fallback:
      enabled: true
      chain: [openrouter, requesty, direct]

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

**Finding Models**: Browse available models at [openrouter.ai/models](https://openrouter.ai/models)

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

**Example:**
```
Use consult_council to ask: "What are the trade-offs between microservices and monolithic architecture?"
```

**Example with confidence level:**
```
Use consult_council with confidence="quick" to ask: "What's the syntax for a Python list comprehension?"
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

### Gateway Layer (ADR-023)

The gateway layer provides an abstraction over LLM API requests with multiple gateway options:

**Available Gateways:**
| Gateway | Description | Key Features |
|---------|-------------|--------------|
| `OpenRouterGateway` | Routes through OpenRouter | 100+ models, single API key |
| `RequestyGateway` | Routes through Requesty | BYOK support, analytics |
| `DirectGateway` | Direct provider APIs | Anthropic, OpenAI, Google |

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

### All Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key | Required |
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
| `LLM_COUNCIL_USE_GATEWAY` | Enable gateway layer with circuit breaker (ADR-023) | false |
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

## Credits & Attribution

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

Karpathy's original README stated:
> "I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like."

This derivative work respects that spirit while packaging the core concept for broader use via the Model Context Protocol.

## License

MIT License - see [LICENSE](LICENSE) file for details.
