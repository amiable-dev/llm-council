"""Request-scoped prompt-cache context (ADR-049 D2, #460).

The verification pipeline publishes its D1 segment map + session key here
(async-safe ContextVar — the same request-scope pattern as
``unified_config``'s ``_request_api_key``); ``build_openrouter_payload``
consumes it to place Anthropic ``cache_control`` breakpoints and the
OpenRouter ``session_id`` affinity key, with zero signature changes in the
layers between.

Safety properties:
- ``cache_control`` breakpoints only when the outgoing prompt MATCHES the
  published segment map (length + head-byte equality) — stage-2/3 prompts,
  which embed different content, are a safe no-op. The ``session_id``
  affinity key is DELIBERATELY session-wide (every call in the verify
  scope): it is a routing hint, not a content marker, and same-provider
  routing across stages and rounds is exactly the affinity ADR-049 wants.
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
    "prompt_cache_ttl",
    "anthropic_min_prefix_tokens",
    "MAX_BREAKPOINTS",
]

_VALID_TTLS = ("5m", "1h")

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


def prompt_cache_ttl(path_default: str) -> str:
    """ADR-049 D5 TTL knob: ``LLM_COUNCIL_PROMPT_CACHE_TTL`` (``5m``|``1h``).

    Returns the env value when valid, else ``path_default`` (verify passes
    ``"1h"`` — observed 3-11 min round gaps straddle the 5-minute boundary;
    interactive paths get the ``5m`` dataclass default). An invalid value
    falls back rather than reaching the API (Anthropic accepts only 5m/1h).

    NOTE: deliberately NOT ``LLM_COUNCIL_CACHE_TTL`` — that name already
    belongs to the response cache (seconds).
    """
    ttl = os.getenv("LLM_COUNCIL_PROMPT_CACHE_TTL", "").strip().lower()
    return ttl if ttl in _VALID_TTLS else path_default


@dataclass
class CacheContext:
    """Segment map + affinity key for the CURRENT request scope."""

    segments: List[Dict[str, Any]] = field(default_factory=list)
    session_id: Optional[str] = None
    ttl: str = "5m"  # interactive default; verify passes 1h (ADR-049 §Dec.5)
    prompt_head: str = ""  # first bytes of the prompt the segments describe

    def matches(self, prompt: str) -> bool:
        """Does ``prompt`` correspond to this segment map?

        Length equality + head-byte equality. A mismatch is not a
        correctness risk (breakpoints on the wrong text merely change price
        class, never content), but the two cheap checks together make
        accidental injection into a different stage's prompt practically
        impossible.
        """
        if not self.segments or self.segments[-1].get("end") != len(prompt):
            return False
        return prompt.startswith(self.prompt_head)

    def breakpoint_offsets(self, model_id: str) -> List[int]:
        """Char offsets (segment ends) eligible for a cache breakpoint.

        Candidates: end of evidence, end of subject. A candidate qualifies
        only when the cumulative est_tokens up to it meets the model's
        minimum cacheable prefix. Segments are walked in list order and
        EVERY segment's tokens count toward the cumulative prefix (they are
        contiguous from offset 0, so the running sum is the true prefix
        size even if a future builder inserts a segment name this module
        has never heard of). Malformed segments contribute nothing and can
        only suppress a breakpoint, never misplace one.
        """
        minimum = anthropic_min_prefix_tokens(model_id)
        offsets: List[int] = []
        cumulative = 0
        for seg in self.segments:
            cumulative += seg.get("est_tokens") or 0
            end = seg.get("end")
            if (
                seg.get("name") in ("evidence", "subject")
                and isinstance(end, int)
                and cumulative >= minimum
            ):
                offsets.append(end)
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
