<div class="hero" markdown>
  <img src="assets/logo.svg" alt="LLM Council">
  <h1>LLM Council</h1>
  <p>Multi-LLM deliberation through peer review and synthesis</p>
  <div class="hero-buttons">
    <a href="getting-started/quickstart/" class="primary">Get Started</a>
    <a href="https://github.com/amiable-dev/llm-council" class="secondary">GitHub</a>
  </div>
</div>

## What is LLM Council?

Instead of asking a single LLM for answers, LLM Council:

1. **Stage 1**: Sends your question to multiple LLMs in parallel (GPT, Claude, Gemini, Grok, etc.)
2. **Stage 2**: Each LLM reviews and ranks the other responses (anonymized to prevent bias)
3. **Stage 3**: A Chairman LLM synthesizes all responses into a final, high-quality answer

## Key Features

- **Multi-model deliberation** - Get answers validated across multiple AI models
- **Peer review** - Anonymous evaluation prevents model favoritism
- **Flexible integration** - Use as MCP server, HTTP API, or Python library
- **Confidence tiers** - Quick, balanced, high, and reasoning modes
- **Jury mode** - Binary verdicts for go/no-go decisions

## Quick Start

```bash
# Install
pip install "llm-council-core[mcp]"

# Set API key
export OPENROUTER_API_KEY="sk-or-v1-..."

# Use with Claude Code
claude mcp add llm-council --scope user -- llm-council
```

Then in Claude Code:

```
Consult the LLM council about best practices for error handling
```

## Use Cases

- **Code review** - Get multiple AI perspectives on code changes
- **Architecture decisions** - Validate design choices with AI jury
- **Content validation** - Check factual accuracy across models
- **Complex problem solving** - Leverage diverse AI reasoning

## Community

- **[Discord](https://discord.gg/y467DGHF)** - Real-time chat and support
- **[GitHub Discussions](https://github.com/amiable-dev/llm-council/discussions)** - Q&A and ideas
- **[Contributing Guide](contributing.md)** - Help improve LLM Council

## Next Steps

- [Installation](getting-started/installation.md) - Detailed setup instructions
- [Quick Start](getting-started/quickstart.md) - Get up and running in 5 minutes
- [Configuration](getting-started/configuration.md) - Customize your council
