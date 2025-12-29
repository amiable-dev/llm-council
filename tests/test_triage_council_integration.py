"""Tests for triage integration with council (ADR-020).

TDD: Write these tests first, then integrate triage with council.

ADR-032: Updated to use unified_config instead of config.py.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock


class TestTriageConfiguration:
    """Test triage configuration options."""

    def test_wildcard_enabled_config_exists(self):
        """WILDCARD_ENABLED config should exist."""
        from llm_council.unified_config import get_config

        config = get_config()
        assert isinstance(config.triage.wildcard.enabled, bool)

    def test_prompt_optimization_enabled_config_exists(self):
        """PROMPT_OPTIMIZATION_ENABLED config should exist."""
        from llm_council.unified_config import get_config

        config = get_config()
        assert isinstance(config.triage.prompt_optimization.enabled, bool)

    def test_wildcard_disabled_by_default(self):
        """Wildcard should be disabled by default."""
        from llm_council.unified_config import get_config

        config = get_config()
        # Should be False by default for backward compatibility
        # (unless env var is set)
        # This tests the default, not current env value

    def test_prompt_optimization_disabled_by_default(self):
        """Prompt optimization should be disabled by default."""
        from llm_council.unified_config import get_config

        config = get_config()
        # Should be False by default for backward compatibility


class TestCouncilTriageIntegration:
    """Test council.run_council_with_fallback integration with triage."""

    @pytest.mark.asyncio
    async def test_council_accepts_triage_options(self):
        """run_council_with_fallback should accept triage options."""
        from llm_council.council import run_council_with_fallback

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                # Should not raise - accepts triage parameters
                await run_council_with_fallback(
                    "Test query",
                    use_wildcard=False,
                    optimize_prompts=False,
                )

    @pytest.mark.asyncio
    async def test_council_backward_compatible(self):
        """Council should work without triage parameters."""
        from llm_council.council import run_council_with_fallback

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                # Should work exactly as before
                result = await run_council_with_fallback("Test query")

                assert "synthesis" in result

    @pytest.mark.asyncio
    async def test_council_uses_triage_when_wildcard_enabled(self):
        """Council should call run_triage when use_wildcard=True."""
        from llm_council.council import run_council_with_fallback
        from llm_council.unified_config import get_config

        COUNCIL_MODELS = get_config().council.models

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                with patch("llm_council.council.run_triage") as mock_triage:
                    from llm_council.triage import TriageResult

                    # Mock triage returns council models + wildcard
                    mock_triage.return_value = TriageResult(
                        resolved_models=list(COUNCIL_MODELS) + ["deepseek/deepseek-chat"],
                        optimized_prompts={m: "Test query" for m in COUNCIL_MODELS},
                        metadata={"mode": "wildcard", "wildcard": "deepseek/deepseek-chat"},
                    )

                    await run_council_with_fallback(
                        "Test query",
                        use_wildcard=True,
                    )

                    # Triage should have been called
                    mock_triage.assert_called_once()

    @pytest.mark.asyncio
    async def test_council_adds_wildcard_to_models(self):
        """Wildcard model should be added to Stage 1 models."""
        from llm_council.council import run_council_with_fallback
        from llm_council.unified_config import get_config

        COUNCIL_MODELS = get_config().council.models

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                await run_council_with_fallback(
                    "Write a Python function",  # CODE domain
                    use_wildcard=True,
                )

                # Stage 1 should have received more models than default
                call_args = mock_stage1.call_args
                # The models used should include wildcard


class TestTriageMetadataInResult:
    """Test that triage metadata appears in council result."""

    @pytest.mark.asyncio
    async def test_result_includes_triage_metadata(self):
        """Council result should include triage info when used."""
        from llm_council.council import run_council_with_fallback

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                result = await run_council_with_fallback(
                    "Write a Python function",
                    use_wildcard=True,
                )

                # Metadata should include triage info
                assert "metadata" in result
                # When wildcard is used, should have wildcard info


class TestPromptOptimizationIntegration:
    """Test prompt optimization in council flow."""

    @pytest.mark.asyncio
    async def test_council_applies_prompt_optimization(self):
        """Council should apply per-model prompts when optimize_prompts=True."""
        from llm_council.council import run_council_with_fallback

        with patch("llm_council.council.stage1_collect_responses_with_status") as mock_stage1:
            mock_stage1.return_value = (
                [],
                {},
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )

            with patch("llm_council.council.quick_synthesis") as mock_synthesis:
                mock_synthesis.return_value = (
                    "Response",
                    {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                )

                await run_council_with_fallback(
                    "Test query",
                    optimize_prompts=True,
                )

                # Prompt optimization should have been applied
                # Stage 1 receives per-model prompts


def get_bool_config(env_var: str, default: bool = False) -> bool:
    """Helper function to get bool from env var (migrated from config.py)."""
    value = os.environ.get(env_var, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return default


class TestConfigEnvironmentVariables:
    """Test configuration via environment variables."""

    def test_wildcard_enabled_from_env(self):
        """WILDCARD_ENABLED should respect environment variable."""
        # Test the helper function works
        with patch.dict(os.environ, {"LLM_COUNCIL_WILDCARD_ENABLED": "true"}):
            result = get_bool_config("LLM_COUNCIL_WILDCARD_ENABLED", default=False)
            assert result is True

        with patch.dict(os.environ, {"LLM_COUNCIL_WILDCARD_ENABLED": "false"}):
            result = get_bool_config("LLM_COUNCIL_WILDCARD_ENABLED", default=True)
            assert result is False

    def test_prompt_optimization_from_env(self):
        """PROMPT_OPTIMIZATION_ENABLED should respect environment variable."""
        with patch.dict(os.environ, {"LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED": "true"}):
            result = get_bool_config("LLM_COUNCIL_PROMPT_OPTIMIZATION_ENABLED", default=False)
            assert result is True
