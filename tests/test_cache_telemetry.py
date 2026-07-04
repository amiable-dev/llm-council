"""ADR-049 D4 (#462): cache-write + route/session telemetry.

Cache-READ telemetry already flows end-to-end; this adds cache-WRITE token
capture (OpenRouter `prompt_tokens_details.cache_write_tokens`, Anthropic
direct `cache_creation_input_tokens` + per-TTL sub-object), carries it
through ADR-011 aggregation into verify input_metrics, and records the
serving route + session affinity key per call. Missing fields degrade to 0
(full-price accounting) — never a crash or a fabricated figure.
"""

import json

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_council.openrouter import _extract_cache_write_tokens
from llm_council.council_usage import _add_cost_to_usage, _build_usage_summary


class TestExtractCacheWriteTokens:
    def test_openrouter_prompt_tokens_details_field(self):
        usage = {"prompt_tokens_details": {"cached_tokens": 5, "cache_write_tokens": 700}}
        assert _extract_cache_write_tokens(usage) == 700

    def test_anthropic_direct_cache_creation_input_tokens(self):
        usage = {"cache_creation_input_tokens": 1234}
        assert _extract_cache_write_tokens(usage) == 1234

    def test_anthropic_per_ttl_sub_object_summed(self):
        usage = {
            "cache_creation": {
                "ephemeral_5m_input_tokens": 100,
                "ephemeral_1h_input_tokens": 900,
            }
        }
        assert _extract_cache_write_tokens(usage) == 1000

    def test_top_level_wins_over_sub_object(self):
        # Anthropic reports both; the top-level total is authoritative.
        usage = {
            "cache_creation_input_tokens": 1000,
            "cache_creation": {"ephemeral_1h_input_tokens": 900},
        }
        assert _extract_cache_write_tokens(usage) == 1000

    def test_missing_fields_degrade_to_zero(self):
        assert _extract_cache_write_tokens({}) == 0
        assert _extract_cache_write_tokens({"prompt_tokens_details": None}) == 0
        assert _extract_cache_write_tokens({"cache_creation": None}) == 0
        assert _extract_cache_write_tokens({"prompt_tokens_details": {}}) == 0

    def test_reported_zero_is_zero_not_missing(self):
        usage = {"prompt_tokens_details": {"cache_write_tokens": 0}}
        assert _extract_cache_write_tokens(usage) == 0


class _OkResponse:
    @staticmethod
    def build(usage):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "hi"}}],
            "usage": usage,
        }
        return resp


@pytest.mark.asyncio
async def test_query_model_captures_cache_write_and_route():
    from llm_council.openrouter import query_model

    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "cost": 0.001,
        "prompt_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 60},
    }
    with (
        patch("llm_council.openrouter.OPENROUTER_API_KEY", "test-key"),
        patch("httpx.AsyncClient") as mock_client,
    ):
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=_OkResponse.build(usage)
        )
        result = await query_model("anthropic/claude-opus-4.8", [{"role": "user", "content": "hi"}])

    assert result["usage"]["cache_write_tokens"] == 60
    assert result["usage"]["cached_tokens"] == 20
    # Route/session attribution (ADR-049 §Decision.4): every call records
    # which route served it; session_id mirrors the affinity key (None when
    # no cache context is active).
    assert result["route"] == "openrouter"
    assert result["session_id"] is None


@pytest.mark.asyncio
async def test_query_model_records_session_id_from_cache_context():
    from llm_council.cache_context import (
        CacheContext,
        clear_cache_context,
        set_cache_context,
    )
    from llm_council.openrouter import query_model

    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    set_cache_context(CacheContext(segments=[], session_id="verify:abc123def456"))
    try:
        with (
            patch("llm_council.openrouter.OPENROUTER_API_KEY", "test-key"),
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=_OkResponse.build(usage)
            )
            result = await query_model("openai/gpt-5.4", [{"role": "user", "content": "hi"}])
    finally:
        clear_cache_context()

    assert result["session_id"] == "verify:abc123def456"
    assert result["usage"]["cache_write_tokens"] == 0  # absent => 0, never a crash


class TestAggregation:
    def test_add_cost_accumulates_cache_write_per_model(self):
        total = {}
        _add_cost_to_usage(
            total,
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
             "cost": 0.01, "cached_tokens": 4, "cache_write_tokens": 6},
            model="anthropic/claude-opus-4.8",
        )
        _add_cost_to_usage(
            total,
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
             "cost": 0.01, "cached_tokens": 0, "cache_write_tokens": 9},
            model="anthropic/claude-opus-4.8",
        )
        assert total["cache_write_tokens"] == 15
        assert total["by_model"]["anthropic/claude-opus-4.8"]["cache_write_tokens"] == 15

    def test_missing_cache_write_defaults_to_zero(self):
        total = {}
        _add_cost_to_usage(total, {"prompt_tokens": 10, "cost": None}, model="m")
        assert total["cache_write_tokens"] == 0
        assert total["by_model"]["m"]["cache_write_tokens"] == 0

    def test_usage_summary_totals_cache_write_across_stages(self):
        by_stage = {
            "stage1": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                       "cost_usd": 0.01, "cached_tokens": 2, "cache_write_tokens": 30,
                       "cost_known": True,
                       "by_model": {"m1": {"prompt_tokens": 10, "completion_tokens": 5,
                                            "total_tokens": 15, "cost_usd": 0.01,
                                            "cached_tokens": 2, "cache_write_tokens": 30,
                                            "cost_known": True}}},
            "stage3": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30,
                       "cost_usd": 0.02, "cached_tokens": 8, "cache_write_tokens": 12,
                       "cost_known": True,
                       "by_model": {"m1": {"prompt_tokens": 20, "completion_tokens": 10,
                                            "total_tokens": 30, "cost_usd": 0.02,
                                            "cached_tokens": 8, "cache_write_tokens": 12,
                                            "cost_known": True}}},
        }
        summary = _build_usage_summary(by_stage)
        assert summary["total"]["cache_write_tokens"] == 42
        assert summary["by_model"]["m1"]["cache_write_tokens"] == 42

    def test_summary_tolerates_pre_d4_stage_buckets(self):
        # Old buckets without cache_write_tokens must not crash the summary.
        by_stage = {"stage1": {"prompt_tokens": 10, "completion_tokens": 5,
                               "total_tokens": 15, "cost_usd": 0.0,
                               "cached_tokens": 0}}
        summary = _build_usage_summary(by_stage)
        assert summary["total"]["cache_write_tokens"] == 0


class TestVerifyInputMetrics:
    def test_usage_input_metrics_carries_cache_write(self):
        from llm_council.verification.evidence_render import _usage_input_metrics

        metrics = _usage_input_metrics(
            {"total": {"prompt_tokens": 100, "completion_tokens": 10,
                       "total_tokens": 110, "cost_usd": 0.1, "cost_known": True,
                       "cached_tokens": 40, "cache_write_tokens": 25}}
        )
        assert metrics["cache_write_tokens"] == 25
        assert metrics["cached_tokens"] == 40

    def test_pre_d4_usage_defaults_cache_write_to_zero(self):
        from llm_council.verification.evidence_render import _usage_input_metrics

        metrics = _usage_input_metrics({"total": {"prompt_tokens": 100}})
        assert metrics["cache_write_tokens"] == 0


class TestHitRateReconstructionFromLogs:
    """ADR-049 §Decision.4: hit-rate per PR reconstructable from .council/logs
    ALONE — a zero cache-read count across rounds is the diagnostic for a
    broken prefix or a lapsed TTL.
    """

    def test_hit_rate_from_synthetic_transcripts(self, tmp_path):
        # Two verify rounds on the same subject: round 1 writes the cache
        # (write tokens, no reads), round 2 reads it. Only result.json files
        # are consulted — the same shape store.write_stage persists.
        rounds = [
            {"verification_id": "r1",
             "input_metrics": {"prompt_tokens": 1000, "cached_tokens": 0,
                               "cache_write_tokens": 800,
                               "cache_session_id": "verify:abc123def456"}},
            {"verification_id": "r2",
             "input_metrics": {"prompt_tokens": 1000, "cached_tokens": 800,
                               "cache_write_tokens": 0,
                               "cache_session_id": "verify:abc123def456"}},
        ]
        for r in rounds:
            d = tmp_path / f"2026-07-04T12-00-00-{r['verification_id']}"
            d.mkdir()
            (d / "result.json").write_text(json.dumps(r))

        # Reconstruction: group by session key, hit rate = reads / prompt.
        by_session = {}
        for result_file in tmp_path.glob("*/result.json"):
            data = json.loads(result_file.read_text())
            m = data["input_metrics"]
            bucket = by_session.setdefault(
                m["cache_session_id"],
                {"prompt": 0, "reads": 0, "writes": 0},
            )
            bucket["prompt"] += m["prompt_tokens"]
            bucket["reads"] += m["cached_tokens"]
            bucket["writes"] += m["cache_write_tokens"]

        stats = by_session["verify:abc123def456"]
        assert stats["writes"] == 800
        assert stats["reads"] / stats["prompt"] == 0.4  # 800 of 2000


class TestMalformedProviderShapes:
    def test_non_numeric_values_degrade_to_zero(self):
        # Untrusted provider payloads: strings/None/bools never crash capture.
        assert _extract_cache_write_tokens({"cache_creation_input_tokens": "800"}) == 0
        assert _extract_cache_write_tokens({"cache_creation_input_tokens": None}) == 0
        assert _extract_cache_write_tokens(
            {"cache_creation": {"ephemeral_1h_input_tokens": "x"}}
        ) == 0
        assert _extract_cache_write_tokens(
            {"prompt_tokens_details": {"cache_write_tokens": True}}
        ) == 0
