# LLM Council Core

[![PyPI version](https://badge.fury.io/py/llm-council-core.svg)](https://pypi.org/project/llm-council-core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A multi-LLM deliberation system where multiple LLMs collaboratively answer questions through peer review and synthesis. Available as a Python library, MCP server, or HTTP API.

## What is This?

Instead of asking a single LLM for answers, this MCP server:
1. **Stage 1**: Sends your question to multiple LLMs in parallel (GPT, Claude, Gemini, Grok, etc.)
2. **Stage 2**: Each LLM reviews and ranks the other responses (anonymized to prevent bias)
3. **Stage 3**: A Chairman LLM synthesizes all responses into a final, high-quality answer

## Installation

```bash
pip install llm-council-core[mcp]
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

#### Option 2: Configuration File

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

#### Option 3: Use Defaults

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
  - `"quick"`: 2 models, ~10 seconds - fast responses for simple questions
  - `"balanced"`: 3 models, ~25 seconds - good balance of speed and quality
  - `"high"`: Full council (~45 seconds) - comprehensive deliberation
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
- `quick`: 2 models, ~10 seconds
- `balanced`: 3 models, ~25 seconds
- `high`: Full council, ~45 seconds (default)

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
| `LLM_COUNCIL_SUPPRESS_WARNINGS` | Suppress security warnings | false |

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
