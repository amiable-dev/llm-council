"""Request-scoped prompt-cache context (ADR-049 D2, #460).

The verification pipeline publishes its D1 segment map + session key here
(async-safe ContextVar — the same request-scope pattern as
``unified_config``'s ``_request_api_key``); ``build_openrouter_payload``
consumes it to place Anthropic ``cache_control`` breakpoints and the
OpenRouter ``session_id`` affinity key, with zero signature changes in the
layers between.

Safety properties:
- Injection only when the outgoing prompt MATCHES the published segment map
  (length + head-byte equality) — stage-2/3 prompts, which embed different
  content, are a safe no-op.
- Never marks a prefix below the model's minimum cacheable size (verified
  per-model table; conservative 4,096-token default for unknown models —
  below-minimum breakpoints are silently ignored AND still bill the write
  premium risk, so we skip them).
- ``LLM_COUNCIL_PROMPT_CACHING=false`` kill-switch ⇒ byte-identical payloads.
- At most 4 breakpoints (Anthropic hard limit); this module places at most 2
  (after evidence, after subject), leaving headroom.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import os

__all__ = [
    "CacheContext",
    "set_cache_context",
    "get_cache_context",
    "clear_cache_context",
    "prompt_caching_enabled",
    "anthropic_min_prefix_tokens",
    "MAX_BREAKPOINTS",
]

MAX_BREAKPOINTS = 4  # Anthropic hard limit per request

# Verified per-model minimum cacheable prefix (tokens) — ADR-049 research
# matrix, checked 2026-07-04. Unknown models get the CONSERVATIVE maximum:
# marking a below-minimum prefix is silently uncached, so when in doubt we
# require the larger prefix rather than emit a useless breakpoint.
_ANTHROPIC_MIN_PREFIX: Dict[str, int] = {
    "anthropic/claude-fable-5": 512,
    "anthropic/claude-opus-4.8": 1024,
    "anthropic/claude-sonnet-5": 1024,
    "anthropic/claude-haiku-4.5": 4096,
}
_DEFAULT_MIN_PREFIX = 4096


def anthropic_min_prefix_tokens(model_id: str) -> int:
    """Minimum cacheable prefix for an anthropic/* model id."""
    return _ANTHROPIC_MIN_PREFIX.get(model_id, _DEFAULT_MIN_PREFIX)


def prompt_caching_enabled() -> bool:
    """Kill-switch: ``LLM_COUNCIL_PROMPT_CACHING`` (default enabled).

    Default-on is deliberate (unlike decision-affecting ADR-044/047 flags):
    the change is price-class-only — content is unchanged, and the exact
    payload format was verified empirically against the production route
    (ADR-049 §Context probe table).
    """
    return os.getenv("LLM_COUNCIL_PROMPT_CACHING", "true").lower() not in (
        "false",
        "0",
        "no",
    )


@dataclass
class CacheContext:
    """Segment map + affinity key for the CURRENT request scope."""

    segments: List[Dict[str, Any]] = field(default_factory=list)
    session_id: Optional[str] = None
    ttl: str = "1h"  # verification default per ADR-049 §Decision.5

    def matches(self, prompt: str) -> bool:
        """Does ``prompt`` correspond to this segment map?

        Length equality + no stronger check needed: segments carry offsets
        into exactly one assembled prompt, and total length collisions with
        a DIFFERENT stage prompt of identical length are not a correctness
        risk (breakpoints on the wrong text merely change price class, never
        content) — but we cheaply rule the common case out anyway.
        """
        return bool(self.segments) and self.segments[-1]["end"] == len(prompt)

    def breakpoint_offsets(self, model_id: str) -> List[int]:
        """Char offsets (segment ends) eligible for a cache breakpoint.

        Candidates: end of evidence, end of subject. A candidate qualifies
        only when the cumulative est_tokens up to it meets the model's
        minimum cacheable prefix.
        """
        minimum = anthropic_min_prefix_tokens(model_id)
        by_name = {s["name"]: s for s in self.segments}
        offsets: List[int] = []
        cumulative = 0
        for name in ("static_head", "evidence", "subject"):
            seg = by_name.get(name)
            if seg is None:
                continue
            cumulative += seg["est_tokens"]
            if name in ("evidence", "subject") and cumulative >= minimum:
                offsets.append(seg["end"])
        # At most 2 candidates by construction — well under the limit of 4,
        # leaving headroom for any future automatic-mode slot (ADR-049).
        return offsets


_cache_context: ContextVar[Optional[CacheContext]] = ContextVar(
    "llm_council_cache_context", default=None
)


def set_cache_context(ctx: CacheContext) -> None:
    _cache_context.set(ctx)


def get_cache_context() -> Optional[CacheContext]:
    return _cache_context.get()


def clear_cache_context() -> None:
    _cache_context.set(None)
