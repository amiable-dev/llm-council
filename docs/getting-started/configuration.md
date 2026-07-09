# Configuration

LLM Council can be configured through environment variables or YAML configuration files.

## Configuration Priority

1. Environment variables (highest priority)
2. YAML configuration file
3. Default values

## YAML Configuration

Create `llm_council.yaml` in your project root or `~/.config/llm-council/`:

```yaml
council:
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
          - anthropic/claude-opus-4-7
          - google/gemini-3-pro
        timeout_seconds: 180

  gateways:
    default: openrouter
    # Per-provider overrides and per-gateway model-id translation
    providers:
      requesty:
        enabled: true
        base_url: https://router.requesty.ai/v1/chat/completions
    model_name_map:
      requesty:
        "some/model:free": "some/model"  # Requesty rejects OpenRouter's ":free" suffix
```

## Environment Variables

### Essential

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `LLM_COUNCIL_MODELS` | Comma-separated model list |
| `LLM_COUNCIL_CHAIRMAN` | Chairman model |
| `LLM_COUNCIL_CHAIRMAN_DISABLED` | Skip chairman synthesis, return top-ranked response directly. **Never enable for `council-verify`/`council-gate`** — see [Verification guide](../guides/verify.md#reading-an-unclear-verdict-adr-047). |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_COUNCIL_RUBRIC_SCORING` | `false` | Multi-dimensional scoring |
| `LLM_COUNCIL_BIAS_AUDIT` | `false` | Bias detection |
| `LLM_COUNCIL_SAFETY_GATE` | `false` | Content safety checks |

### Modes

| Variable | Options | Description |
|----------|---------|-------------|
| `LLM_COUNCIL_MODE` | `consensus`, `debate` | Synthesis mode |
| `LLM_COUNCIL_VERDICT_TYPE` | `synthesis`, `binary` | Verdict format |

## Gateway Options

LLM Council supports multiple gateways:

| Gateway | Best For | Setup |
|---------|----------|-------|
| OpenRouter | Easy setup | `OPENROUTER_API_KEY` |
| Direct | Control | Provider API keys |
| Requesty | Analytics | `REQUESTY_API_KEY` |
| Ollama | Local/Air-gapped | No key needed |

Model IDs sometimes differ across gateways (e.g. Requesty rejects OpenRouter's
`:free` suffix); use `gateways.model_name_map` in the YAML config above to
translate a canonical model ID per gateway.

> **Note:** `gateways.default` (above) is the config that actually routes
> live traffic today. The class-based `GatewayRouter`/circuit-breaker
> abstraction described in the [ADR-023 spec](../adr/ADR-023-multi-router-gateway-support.md)
> is not currently reachable via configuration — see
> [#524](https://github.com/amiable-dev/llm-council/issues/524).

See [README](https://github.com/amiable-dev/llm-council#setup) for complete configuration reference.
