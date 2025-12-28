# Offline-First LLM Orchestration

**Your LLM system shouldn't crash when OpenAI is down. Here's how we built metadata that survives network failures.**

---

LLM Council's first council review was harsh: "You've built the core brain of your system on APIs you don't control."

They were right. Our initial design required live API calls to OpenRouter just to *start*. For a self-hosted project, this was unacceptable.

## The Sovereign Orchestrator Philosophy

We adopted a principle we call the "Sovereign Orchestrator":

> External services are **plugins**, not foundations. If the internet is disconnected, the software must still boot and run—even if degraded.

## The Problem: Brittle Dependencies

Our first implementation:

```python
# DON'T DO THIS: Fails when external API is unavailable
import httpx

async def get_model_context_window(model_id: str) -> int:
    async with httpx.AsyncClient() as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        models = response.json()["data"]
        for model in models:
            if model["id"] == model_id:
                return model["context_length"]
    raise ModelNotFoundError(model_id)
```

Problems:
- **Cold start failure**: System can't initialize without network
- **Runtime brittleness**: API rate limits or outages break production
- **No fallback**: Unknown models cause hard failures

## The Solution: Priority Chain Architecture

We replaced direct API calls with a three-tier priority chain:

```python
class StaticRegistryProvider:
    """Offline-safe metadata provider (ADR-026)."""

    def get_context_window(self, model_id: str) -> int:
        # 1. Check bundled registry (always available)
        info = self._registry.get(model_id)
        if info:
            return info.context_window

        # 2. Try LiteLLM library (installed, no network)
        litellm_window = self._litellm_adapter.get_context_window(model_id)
        if litellm_window is not None:
            return litellm_window

        # 3. Safe default (conservative—triggers truncation warnings, not crashes)
        logger.warning(f"Using default context window for unknown model: {model_id}")
        return 4096
```

The key insight: **never crash, always return something usable**.

## Bundled Model Registry

We ship a YAML registry with 31 models from 8 providers:

```yaml
# src/llm_council/models/registry.yaml - Shipped with package
version: "1.0"
updated: "2025-12-23"
models:
  - id: "openai/gpt-4o"
    context_window: 128000
    pricing:
      prompt: 0.0025
      completion: 0.01
    quality_tier: "frontier"

  - id: "anthropic/claude-opus-4.5"
    context_window: 200000
    pricing:
      prompt: 0.015
      completion: 0.075
    quality_tier: "frontier"

  - id: "ollama/llama3.2"
    context_window: 128000
    pricing:
      prompt: 0
      completion: 0
    quality_tier: "local"
```

This file is bundled with the package. Even on an air-gapped server, model metadata works.

**Staleness management**: The registry is updated with each release. Between releases, the dynamic provider (when enabled) fetches fresh data. The static registry is the floor, not the ceiling.

## Offline Mode

For environments with no external connectivity:

```bash
export LLM_COUNCIL_OFFLINE=true
```

When offline mode is enabled:
1. Uses `StaticRegistryProvider` exclusively
2. Disables all external metadata calls
3. Logs info about limited/stale metadata
4. **All core council operations succeed**

```python
def get_provider() -> MetadataProvider:
    """Factory function for metadata provider.

    Note: All providers implement the same sync interface.
    The DynamicMetadataProvider uses async internally but exposes
    sync methods via run_in_executor for interface consistency.
    """
    if is_offline_mode():
        return StaticRegistryProvider()

    if os.environ.get("LLM_COUNCIL_MODEL_INTELLIGENCE") == "true":
        return DynamicMetadataProvider()

    return StaticRegistryProvider()
```

## LiteLLM as Hidden Fallback

LiteLLM bundles metadata for 100+ models. We use it as a second-tier fallback with lazy loading:

```python
class LiteLLMAdapter:
    """Lazy-loaded LiteLLM metadata adapter."""

    def __init__(self):
        self._loaded = False
        self._model_map: Dict[str, Any] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            import litellm
            self._model_map = getattr(litellm, "model_cost", {})
            self._loaded = True
        except ImportError:
            # LiteLLM not installed—that's fine
            self._loaded = True

    def get_context_window(self, model_id: str) -> Optional[int]:
        self._ensure_loaded()

        # Try full ID first (preserves provider context)
        if model_id in self._model_map:
            info = self._model_map[model_id]
            return info.get("max_input_tokens") or info.get("max_tokens")

        # Fallback: try without provider prefix
        # Only for well-known models where provider doesn't affect limits
        short_id = model_id.split("/")[-1]
        info = self._model_map.get(short_id)
        if info:
            return info.get("max_input_tokens") or info.get("max_tokens")

        return None
```

Benefits of lazy loading:
- **No startup penalty** if LiteLLM not needed
- **No crash** if LiteLLM not installed
- **Graceful degradation** with stale versions

## Dynamic Metadata (Optional Enhancement)

For environments *with* connectivity, we offer dynamic metadata via OpenRouter:

```python
class DynamicMetadataProvider:
    """Real-time metadata from OpenRouter API."""

    def __init__(self):
        self._cache = TTLCache(ttl_seconds=3600)  # 1 hour
        self._static_fallback = StaticRegistryProvider()

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        # Check cache first
        cached = self._cache.get(model_id)
        if cached is not None:
            return cached

        # Try API (blocking—runs in thread pool for async callers)
        try:
            info = self._fetch_from_api_sync(model_id)
            self._cache.set(model_id, info)
            return info
        except (NetworkError, RateLimitError) as e:
            logger.warning(f"API fetch failed for {model_id}: {e}. Using static fallback.")
            return self._static_fallback.get_model_info(model_id)
```

The dynamic provider wraps the static provider—never replacing it, only enhancing it.

## The Tradeoff: Freshness vs. Reliability

| Mode | Metadata Source | Freshness | Reliability |
|------|-----------------|-----------|-------------|
| Offline | Bundled YAML | Stale (package version) | 100% |
| Static | YAML + LiteLLM | Days-weeks old | 100% |
| Dynamic | API + Cache | Minutes old | 95%+ |

We default to static mode. Dynamic requires explicit opt-in:

```bash
export LLM_COUNCIL_MODEL_INTELLIGENCE=true
```

## What This Enables

With offline-first architecture, LLM Council works in:

- **Air-gapped environments**: Government, healthcare, finance
- **Intermittent connectivity**: Mobile, edge deployments
- **Development without API keys**: Test locally first
- **CI/CD pipelines**: No external dependencies in tests
- **Self-hosted with local models**: Ollama, llama.cpp

## Practical Example: New Model Appears

When a new model like `openai/o3` releases:

**Without offline-first design:**
```
API returns unknown model → Exception → System crash
```

**With priority chain:**
```
Registry: not found
LiteLLM: not found
Default: return 4096 (with warning log)
→ System continues with degraded metadata
→ Update registry.yaml in next release
```

The system runs with stale data until you update. Stale is better than broken.

---

*This is post 2 of 7. Next: [Why Majority Vote Fails for Small Groups](./03-voting-logic-borda.md)*

---

*LLM Council is open source: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
