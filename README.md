# LLM Council MCP Server

[![PyPI version](https://badge.fury.io/py/llm-council-mcp.svg)](https://pypi.org/project/llm-council-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that allows AI assistants to consult a council of multiple LLMs and receive synthesized guidance.

## What is This?

Instead of asking a single LLM for answers, this MCP server:
1. **Stage 1**: Sends your question to multiple LLMs in parallel (GPT, Claude, Gemini, Grok, etc.)
2. **Stage 2**: Each LLM reviews and ranks the other responses (anonymized to prevent bias)
3. **Stage 3**: A Chairman LLM synthesizes all responses into a final, high-quality answer

## Installation

```bash
pip install llm-council-mcp
```

## Setup

### 1. Get an OpenRouter API Key

The council uses [OpenRouter](https://openrouter.ai/) to access multiple LLMs:
1. Sign up at [openrouter.ai](https://openrouter.ai/)
2. Add credits or enable auto-top-up
3. Get your API key from the dashboard

### 2. Configure Environment Variables

Set your OpenRouter API key:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

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
claude mcp add --transport stdio llm-council --scope user \
  --env OPENROUTER_API_KEY=your-key-here \
  -- llm-council
```

Then in Claude Code:
```
Consult the LLM council about best practices for error handling
```

### With Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "llm-council": {
      "command": "llm-council",
      "env": {
        "OPENROUTER_API_KEY": "sk-or-v1-..."
      }
    }
  }
}
```

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
- `include_details` (boolean, optional): Include individual model responses and rankings (default: false)

**Example:**
```
Use consult_council to ask: "What are the trade-offs between microservices and monolithic architecture?"
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

## Credits

Based on the original [llm-council](https://github.com/karpathy/llm-council) by Andrej Karpathy.

## License

MIT License - see [LICENSE](LICENSE) file for details.
