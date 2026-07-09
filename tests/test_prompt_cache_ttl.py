"""ADR-049 D5 (#463): prompt-cache TTL knob.

`LLM_COUNCIL_PROMPT_CACHE_TTL` (`5m` | `1h`) overrides the per-path default:
the verify path defaults to `1h` (observed 3-11 min round gaps straddle the
5-minute boundary; ADR-049 §Decision.5 table), interactive/consult use gets
the dataclass default `5m`. NOTE: the ADR/issue drafted this knob as
`LLM_COUNCIL_CACHE_TTL`, but that name already belongs to the RESPONSE cache
(seconds) — the prompt-cache knob deliberately uses the distinct name.
"""

import pytest

from llm_council.cache_context import (
    CacheContext,
    clear_cache_context,
    prompt_cache_ttl,
    set_cache_context,
)
from llm_council.gateway.openrouter import build_openrouter_payload


@pytest.fixture(autouse=True)
def _clean_context():
    clear_cache_context()
    yield
    clear_cache_context()


class TestTtlKnob:
    def test_default_is_path_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_PROMPT_CACHE_TTL", raising=False)
        assert prompt_cache_ttl("1h") == "1h"
        assert prompt_cache_ttl("5m") == "5m"

    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_PROMPT_CACHE_TTL", "5m")
        assert prompt_cache_ttl("1h") == "5m"
        monkeypatch.setenv("LLM_COUNCIL_PROMPT_CACHE_TTL", "1h")
        assert prompt_cache_ttl("5m") == "1h"

    def test_invalid_value_falls_back_to_path_default(self, monkeypatch):
        # Anthropic accepts only 5m/1h; an unknown value must not reach the
        # API (silently uncached at best, request error at worst).
        monkeypatch.setenv("LLM_COUNCIL_PROMPT_CACHE_TTL", "2h")
        assert prompt_cache_ttl("1h") == "1h"
        monkeypatch.setenv("LLM_COUNCIL_PROMPT_CACHE_TTL", "")
        assert prompt_cache_ttl("1h") == "1h"

    def test_interactive_dataclass_default_is_5m(self):
        # Non-verify paths that publish a context without an explicit ttl
        # get the interactive default (ADR-049 §Decision.5).
        assert CacheContext().ttl == "5m"


class TestTtlRendersIntoDirective:
    def test_directive_carries_configured_ttl(self, monkeypatch):
        prompt = "H" * 6000 + "S" * 2000 + "T" * 40
        segments = [
            {"name": "static_head", "start": 0, "end": 6000, "est_tokens": 1500},
            {"name": "subject", "start": 6000, "end": 8000, "est_tokens": 500},
            {"name": "volatile_tail", "start": 8000, "end": 8040, "est_tokens": 10},
        ]
        set_cache_context(
            CacheContext(segments=segments, session_id="s", ttl="5m")
        )
        payload = build_openrouter_payload(
            "anthropic/claude-opus-4.8", [{"role": "user", "content": prompt}]
        )
        parts = payload["messages"][0]["content"]
        assert parts[0]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}


class TestVerifyPathDefault:
    @pytest.mark.asyncio
    async def test_verify_publishes_1h_and_env_overrides(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.cache_context import get_cache_context
        from llm_council.verification.api import VerifyRequest, run_verification

        seen = {}

        async def probe_pipeline(*a, **kw):
            seen["ttl"] = get_cache_context().ttl
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

            monkeypatch.delenv("LLM_COUNCIL_PROMPT_CACHE_TTL", raising=False)
            await run_verification(
                VerifyRequest(snapshot_id="abc1234", tier="quick",
                              target_paths=["src/x.py"]), mock_store)
            assert seen["ttl"] == "1h"  # verify default

            monkeypatch.setenv("LLM_COUNCIL_PROMPT_CACHE_TTL", "5m")
            await run_verification(
                VerifyRequest(snapshot_id="abc1234", tier="quick",
                              target_paths=["src/x.py"]), mock_store)
            assert seen["ttl"] == "5m"  # knob overrides the path default
