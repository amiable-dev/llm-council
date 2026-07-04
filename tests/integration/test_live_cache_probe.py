"""ADR-049 D5 (#463): opt-in LIVE two-call prompt-cache probe.

REAL SPEND (~$0.05/run). Never runs in CI or `make test-fast`:
it is gated on BOTH an explicit opt-in flag and a resolvable OpenRouter key.

    LLM_COUNCIL_LIVE_CACHE_PROBE=true pytest tests/integration/test_live_cache_probe.py -q

What it asserts (the 2026-07-04 empirical probe from ADR-049 §Context,
now repeatable): two identical calls with an Anthropic ``cache_control``
breakpoint via the production OpenRouter route — the second call must
report cache-READ tokens > 0 and a discounted ``usage.cost`` (< the first
call's cost; the verified read price is 0.1x input).

Quarterly re-probe (ADR-049 §Compliance): the REFUTED matrix rows —
OpenAI / Gemini / DeepSeek via OpenRouter (no cache discount passed
through as tested 2026-07-04) — should be re-checked with this same
two-call shape each quarter; if a second-call discount appears for those
vendors, update the ADR matrix and extend `_apply_cache_breakpoints`
beyond ``anthropic/*``.
"""

import os

import pytest

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("LLM_COUNCIL_LIVE_CACHE_PROBE", "").lower() != "true",
        reason="live probe is opt-in: set LLM_COUNCIL_LIVE_CACHE_PROBE=true (real spend ~$0.05)",
    ),
]

PROBE_MODEL = "anthropic/claude-haiku-4.5"  # cheapest anthropic route
# Haiku's minimum cacheable prefix is 4,096 tokens — pad well past it.
PROBE_PROMPT = ("You are a code reviewer. " * 1200) + "\nReply with the single word: ok"


async def test_second_call_hits_cache_with_discounted_cost():
    import httpx

    from llm_council.unified_config import get_api_key

    api_key = get_api_key("openrouter")
    if not api_key:
        pytest.skip("no OpenRouter key resolvable")

    payload = {
        "model": PROBE_MODEL,
        "max_tokens": 8,
        "usage": {"include": True},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": PROBE_PROMPT,
                        "cache_control": {"type": "ephemeral", "ttl": "5m"},
                    }
                ],
            }
        ],
    }

    async def call():
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["usage"]

    first = await call()
    second = await call()

    details = second.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") or 0
    assert cached > 0, f"second call reported no cache reads: {second}"
    assert second.get("cost") is not None and first.get("cost") is not None
    assert second["cost"] < first["cost"], (
        f"no discount on the cached call: first={first['cost']} second={second['cost']}"
    )
