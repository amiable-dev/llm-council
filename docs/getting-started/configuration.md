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
    # `pools` is optional — see "Default model pools" below. Set it only for
    # the tiers you want to change; the rest keep the shipped defaults.
    pools:
      quick:
        models:
          - google/gemini-3.5-flash-lite
          - anthropic/claude-haiku-4.5
        timeout_seconds: 30

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

## Default model pools

You do not have to choose models. Each tier — `quick`, `balanced`, `high`,
`reasoning` and `frontier` — ships with a default council, and a fresh install
uses it with no configuration at all.

Those defaults live in one file inside the installed package,
`llm_council/models/default_pools.yaml`. To see the pool a tier will actually
use:

```bash
python -c "from llm_council.tier_contract import TIER_MODEL_POOLS; print(TIER_MODEL_POOLS['high'])"
```

**Overriding is per tier.** Anything you put under `tiers.pools.<tier>` wins
for that tier; every tier you leave out falls back to the packaged default. So
the snippet above changes `quick` only — `balanced`, `high`, `reasoning` and
`frontier` are untouched.

Two rules the defaults follow, worth keeping if you write your own:

- **Every model in a pool must fit that tier's `timeout_seconds`.** Selection
  can pick any member, not just the first, so one slow model makes the whole
  tier unreliable rather than occasionally slow.
- **New and preview models go in `frontier`.** That is the audition tier
  ([ADR-027](../adr/ADR-027-frontier-tier.md)): its members are scored and
  recorded but carry no weight in consensus until they have a track record.

`LLM_COUNCIL_MODELS` does **not** override a tier. A run picks its members in
this order: models passed explicitly to the call, else the selected tier's
pool, else `LLM_COUNCIL_MODELS`. Which of those applies depends on the entry
point:

| Entry point | Default council |
|---|---|
| MCP `consult_council`, `verify` | the selected tier's pool |
| HTTP `POST /v1/council/run` | `LLM_COUNCIL_MODELS` — this endpoint is tier-agnostic |
| Library `run_full_council()` | `LLM_COUNCIL_MODELS` |

So editing a tier pool changes what MCP consults run; setting
`LLM_COUNCIL_MODELS` changes what the HTTP endpoint runs. If you leave both
alone they agree: `LLM_COUNCIL_MODELS` defaults to the `high` pool.

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
