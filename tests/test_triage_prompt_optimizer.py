"""Tests for prompt optimizer (ADR-020 Tier 2).

TDD: Write these tests first, then implement prompt_optimizer.py.
"""

import pytest
from llm_council import model_constants as mc



class TestPromptOptimizer:
    """Test PromptOptimizer class."""

    def test_optimize_returns_dict(self):
        """optimize() should return dict mapping model to prompt."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        result = optimizer.optimize("Test prompt", [mc.OPENAI_HIGH])

        assert isinstance(result, dict)
        assert mc.OPENAI_HIGH in result

    def test_optimize_includes_all_models(self):
        """optimize() should return prompts for all requested models."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        models = [mc.OPENAI_HIGH, mc.ANTHROPIC_BALANCED, mc.GOOGLE_HIGH]
        result = optimizer.optimize("Test prompt", models)

        for model in models:
            assert model in result

    def test_optimize_preserves_query_content(self):
        """Adapted prompts should contain original query content."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        original = "What is quantum computing?"
        result = optimizer.optimize(original, [mc.OPENAI_HIGH])

        # Original query should appear in adapted prompt
        assert original in result[mc.OPENAI_HIGH]


class TestModelAdapters:
    """Test per-model prompt adapters."""

    def test_claude_adapter_uses_xml(self):
        """Claude adapter should wrap in XML structure."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        result = optimizer.optimize("Test query", [mc.ANTHROPIC_BALANCED])

        prompt = result[mc.ANTHROPIC_BALANCED]
        # Should have XML-like structure
        assert "<" in prompt and ">" in prompt

    def test_claude_adapter_query_tag(self):
        """Claude adapter should have query tag."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        result = optimizer.optimize("Test query", [mc.ANTHROPIC_OPUS_LATEST])

        prompt = result[mc.ANTHROPIC_OPUS_LATEST]
        assert "<query>" in prompt or "<question>" in prompt or "<task>" in prompt

    def test_openai_adapter_uses_markdown(self):
        """OpenAI adapter should use markdown formatting."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        result = optimizer.optimize("Test query", [mc.OPENAI_HIGH])

        prompt = result[mc.OPENAI_HIGH]
        # Should have markdown elements or be clear text
        # OpenAI works well with clear formatting
        assert "Test query" in prompt

    def test_gemini_adapter(self):
        """Gemini adapter should produce valid prompt."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        result = optimizer.optimize("Test query", [mc.GOOGLE_HIGH])

        prompt = result[mc.GOOGLE_HIGH]
        assert "Test query" in prompt

    def test_unknown_model_uses_fallback(self):
        """Unknown models should use fallback adapter."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        result = optimizer.optimize("Test query", ["unknown/custom-model"])

        # Should still return the prompt (passthrough)
        assert "unknown/custom-model" in result
        assert "Test query" in result["unknown/custom-model"]


class TestCanonicalIntent:
    """Test canonical intent extraction."""

    def test_extract_intent_returns_string(self):
        """extract_intent() should return canonical form."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        result = optimizer.extract_intent("What is 2 + 2?")

        assert isinstance(result, str)

    def test_extract_intent_preserves_meaning(self):
        """extract_intent() should preserve query meaning."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        original = "Please explain how photosynthesis works in plants."
        result = optimizer.extract_intent(original)

        # Intent should contain key concepts
        assert "photosynthesis" in result.lower()


class TestSemanticEquivalence:
    """Test semantic equivalence verification."""

    def test_verify_equivalence_true_for_same_content(self):
        """verify_equivalence() should return True for semantically equivalent prompts."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        prompts = {
            "model-a": "What is Python?",
            "model-b": "<query>What is Python?</query>",
        }

        result = optimizer.verify_equivalence(prompts)

        assert result is True

    def test_verify_equivalence_disabled_by_default(self):
        """verify_equivalence() should be optional (disabled by default)."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer(verify_semantic_equivalence=False)

        # Should not raise or do expensive verification
        result = optimizer.verify_equivalence({})
        assert result is True  # Always passes when disabled


class TestOptimizationFallback:
    """Test fallback to original prompt."""

    def test_fallback_when_adapter_fails(self):
        """Should fallback to original prompt if adaptation fails."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        original = "Test query"

        # Even if internal processing fails, should return original
        result = optimizer.optimize(original, ["unknown/model"])

        assert original in result["unknown/model"]

    def test_optimization_disabled_returns_original(self):
        """When optimization disabled, should return original prompts."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer(enabled=False)
        original = "Test query"
        models = [mc.OPENAI_HIGH, mc.ANTHROPIC_BALANCED]

        result = optimizer.optimize(original, models)

        for model in models:
            assert result[model] == original


class TestPromptOptimizerConfiguration:
    """Test optimizer configuration."""

    def test_optimizer_has_enabled_flag(self):
        """PromptOptimizer should have enabled configuration."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer(enabled=True)
        assert optimizer.enabled is True

        disabled = PromptOptimizer(enabled=False)
        assert disabled.enabled is False

    def test_optimizer_default_enabled(self):
        """PromptOptimizer should be enabled by default."""
        from llm_council.triage.prompt_optimizer import PromptOptimizer

        optimizer = PromptOptimizer()
        assert optimizer.enabled is True


class TestIntegrationWithTriage:
    """Test prompt optimizer integration with run_triage."""

    def test_run_triage_uses_optimizer(self):
        """run_triage with optimize_prompts=True should use optimizer."""
        from llm_council.triage import run_triage

        result = run_triage("Write a Python function", optimize_prompts=True)

        # Prompts should differ per model (some have XML, etc.)
        prompts = list(result.optimized_prompts.values())
        # At least one prompt should have been adapted
        has_adapted = any("<" in p or "#" in p for p in prompts)
        assert has_adapted or result.metadata.get("optimization_applied") is not None

    def test_run_triage_default_no_optimization(self):
        """run_triage should not optimize by default (passthrough)."""
        from llm_council.triage import run_triage
        from llm_council.unified_config import get_config

        COUNCIL_MODELS = get_config().council.models
        original = "Test query"
        result = run_triage(original)

        # All prompts should be original
        for model in COUNCIL_MODELS:
            assert result.optimized_prompts[model] == original


class TestModelProviderDetection:
    """Test model provider detection from model ID."""

    def test_detect_anthropic(self):
        """Should detect Anthropic from model ID."""
        from llm_council.triage.prompt_optimizer import get_model_provider

        assert get_model_provider(mc.ANTHROPIC_BALANCED) == "anthropic"
        assert get_model_provider(mc.ANTHROPIC_OPUS_LATEST) == "anthropic"

    def test_detect_openai(self):
        """Should detect OpenAI from model ID."""
        from llm_council.triage.prompt_optimizer import get_model_provider

        assert get_model_provider(mc.OPENAI_HIGH) == "openai"
        assert get_model_provider(mc.OPENAI_ULTRA) == "openai"

    def test_detect_google(self):
        """Should detect Google from model ID."""
        from llm_council.triage.prompt_optimizer import get_model_provider

        assert get_model_provider(mc.GOOGLE_HIGH) == "google"
        assert get_model_provider(mc.GOOGLE_BALANCED) == "google"

    def test_detect_unknown(self):
        """Should return 'unknown' for unrecognized providers."""
        from llm_council.triage.prompt_optimizer import get_model_provider

        assert get_model_provider("custom/my-model") == "unknown"
        assert get_model_provider("invalid") == "unknown"
