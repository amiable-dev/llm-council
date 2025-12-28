# Installation

## Requirements

- Python 3.11 or higher
- An API key from OpenRouter, Anthropic, OpenAI, or Google

## Installation Options

### With MCP Server (Recommended)

```bash
pip install "llm-council-core[mcp]"
```

### Core Library Only

```bash
pip install llm-council-core
```

### With All Extras

```bash
pip install "llm-council-core[mcp,http,secure,ollama]"
```

### From Source

```bash
git clone https://github.com/amiable-dev/llm-council.git
cd llm-council
pip install -e ".[dev]"
```

## Setting Up API Keys

### Option 1: System Keychain (Most Secure)

```bash
pip install "llm-council-core[secure]"
llm-council setup-key
```

### Option 2: Environment Variables

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

### Option 3: Environment File

```bash
cp .env.example .env
# Edit .env with your API keys
```

## Verify Installation

```bash
# Check version
python -c "import llm_council; print(llm_council.__version__)"

# Run health check
llm-council health-check
```

## Next Steps

- [Quick Start](quickstart.md) - Start using the council
- [Configuration](configuration.md) - Customize settings
