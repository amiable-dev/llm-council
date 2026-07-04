"""ADR-049 D2 (#460): cache_control injection + session_id affinity.

The payload builder splits the prompt into content parts with Anthropic
cache_control breakpoints at the D1 segment boundaries — for anthropic/*
models only, only when the request-scoped cache context matches the prompt,
and never below the model's minimum cacheable prefix. Flag-off payloads are
byte-identical.
"""

import pytest

from llm_council.cache_context import (
    CacheContext,
    anthropic_min_prefix_tokens,
    clear_cache_context,
    get_cache_context,
    prompt_caching_enabled,
    set_cache_context,
)
from llm_council.gateway.openrouter import build_openrouter_payload

HEAD = "H" * 6000      # ~1500 est tokens
EVIDENCE = "E" * 2000  # head+evidence ~2000 tokens
SUBJECT = "S" * 8000
TAIL = "\nCommit under review: `abc1234`"
PROMPT = HEAD + EVIDENCE + SUBJECT + TAIL


def _segments():
    bounds = [
        ("static_head", 0, len(HEAD)),
        ("evidence", len(HEAD), len(HEAD) + len(EVIDENCE)),
        ("subject", len(HEAD) + len(EVIDENCE), len(HEAD) + len(EVIDENCE) + len(SUBJECT)),
        ("volatile_tail", len(HEAD) + len(EVIDENCE) + len(SUBJECT), len(PROMPT)),
    ]
    return [
        {"name": n, "start": a, "end": b, "est_tokens": (b - a) // 4}
        for n, a, b in bounds
    ]


@pytest.fixture(autouse=True)
def _clean_context():
    clear_cache_context()
    yield
    clear_cache_context()


def _messages():
    return [{"role": "user", "content": PROMPT}]


class TestInjection:
    def test_anthropic_payload_gets_breakpoints_at_boundaries(self):
        set_cache_context(CacheContext(
            segments=_segments(), session_id="verify:r:abc", ttl="1h",
        ))
        payload = build_openrouter_payload("anthropic/claude-opus-4.8", _messages())
        parts = payload["messages"][0]["content"]
        assert isinstance(parts, list)
        # Reassembly must be byte-identical to the original prompt.
        assert "".join(p["text"] for p in parts) == PROMPT
        cc = [p.get("cache_control") for p in parts]
        # Breakpoints after evidence and after subject; tail unmarked.
        assert cc[0] == {"type": "ephemeral", "ttl": "1h"}
        assert cc[1] == {"type": "ephemeral", "ttl": "1h"}
        assert cc[-1] is None
        assert sum(1 for c in cc if c) <= 4

    def test_session_id_in_payload(self):
        set_cache_context(CacheContext(segments=_segments(), session_id="verify:r:abc"))
        payload = build_openrouter_payload("anthropic/claude-opus-4.8", _messages())
        assert payload["session_id"] == "verify:r:abc"

    def test_non_anthropic_model_untouched_but_session_kept(self):
        set_cache_context(CacheContext(segments=_segments(), session_id="verify:r:abc"))
        payload = build_openrouter_payload("openai/gpt-5.4", _messages())
        assert payload["messages"][0]["content"] == PROMPT  # plain string
        assert payload["session_id"] == "verify:r:abc"  # affinity still helps

    def test_no_context_byte_identical(self):
        baseline = build_openrouter_payload("anthropic/claude-opus-4.8", _messages())
        assert baseline["messages"][0]["content"] == PROMPT
        assert "session_id" not in baseline

    def test_flag_off_byte_identical(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_PROMPT_CACHING", "false")
        set_cache_context(CacheContext(segments=_segments(), session_id="s"))
        payload = build_openrouter_payload("anthropic/claude-opus-4.8", _messages())
        assert payload["messages"][0]["content"] == PROMPT
        assert "session_id" not in payload

    def test_prompt_mismatch_skips_injection(self):
        # Stage-2/3 prompts differ from the segment map's prompt — the guard
        # is content-length + head-byte equality; mismatch => safe no-op.
        set_cache_context(CacheContext(segments=_segments(), session_id="s"))
        other = [{"role": "user", "content": "a completely different prompt"}]
        payload = build_openrouter_payload("anthropic/claude-opus-4.8", other)
        assert payload["messages"][0]["content"] == "a completely different prompt"

    def test_min_prefix_guard_skips_small_segments(self):
        # Haiku 4.5 minimum is 4096 tokens: head+evidence (~2000) is below,
        # so its breakpoint is skipped; head+evidence+subject (~4000) is also
        # below => no breakpoints at all, payload stays a plain string.
        set_cache_context(CacheContext(segments=_segments(), session_id="s"))
        payload = build_openrouter_payload("anthropic/claude-haiku-4.5", _messages())
        assert payload["messages"][0]["content"] == PROMPT

    def test_min_prefix_uses_conservative_default_for_unknown_models(self):
        assert anthropic_min_prefix_tokens("anthropic/claude-unknown-99") == 4096
        assert anthropic_min_prefix_tokens("anthropic/claude-opus-4.8") == 1024


class TestContextLifecycle:
    def test_set_get_clear(self):
        assert get_cache_context() is None
        ctx = CacheContext(segments=_segments(), session_id="x")
        set_cache_context(ctx)
        assert get_cache_context() is ctx
        clear_cache_context()
        assert get_cache_context() is None

    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_PROMPT_CACHING", raising=False)
        assert prompt_caching_enabled() is True


class TestPipelinePublishesContext:
    @pytest.mark.asyncio
    async def test_run_verification_sets_stable_session_and_clears(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification.api import VerifyRequest, run_verification

        seen = {}

        async def probe_pipeline(*a, **kw):
            ctx = get_cache_context()
            seen["ctx"] = ctx
            return {"verification_id": "x", "verdict": "pass", "confidence": 0.9,
                    "exit_code": 0, "rubric_scores": {}, "blocking_issues": [],
                    "rationale": "r", "transcript_location": "/tmp/t",
                    "partial": False, "timeout_fired": False,
                    "completed_stages": ["stage1", "stage2", "stage3"]}

        segments = [{"name": "static_head", "start": 0, "end": 100, "est_tokens": 25}]
        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=("short prompt", {"kept": [], "warnings": [],
                                                "segments": segments}),
            ),
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=probe_pipeline,
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)
            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            r1 = await run_verification(
                VerifyRequest(snapshot_id="abc1234", tier="quick",
                              target_paths=["src/x.py"]), mock_store)
            r2 = await run_verification(
                VerifyRequest(snapshot_id="fff9999", tier="quick",
                              target_paths=["src/x.py"]), mock_store)

        ctx = seen["ctx"]
        assert ctx is not None
        assert ctx.segments == segments
        assert ctx.ttl == "1h"
        # Stable across rounds: same subject, DIFFERENT SHAs, same session key
        # — and the key never contains the per-round SHA.
        assert ctx.session_id.startswith("verify:")
        assert "abc1234" not in ctx.session_id and "fff9999" not in ctx.session_id
        # Cleared after each run (no leak into the next request).
        assert get_cache_context() is None


class TestCapabilityDescriptor:
    def test_openrouter_declares_verified_caching(self):
        from llm_council.gateway.openrouter import OpenRouterGateway

        gw = OpenRouterGateway(api_key="test-key")
        caching = gw.capabilities.caching
        assert caching.semantics == "explicit"
        assert caching.directive == "anthropic_cache_control"
        assert caching.billing_passthrough is True

    def test_default_descriptor_is_none(self):
        from llm_council.gateway.base import RouterCapabilities

        assert RouterCapabilities().caching.semantics == "none"
