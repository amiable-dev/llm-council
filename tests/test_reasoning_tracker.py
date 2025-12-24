"""TDD tests for ADR-026 Phase 2: Reasoning Token Usage Tracking.

Tests for extracting and aggregating reasoning token usage from API responses.
Written BEFORE implementation per TDD workflow.
"""

import pytest


class TestReasoningUsageDataclass:
    """Test ReasoningUsage dataclass definition."""

    def test_reasoning_usage_dataclass_exists(self):
        """ReasoningUsage should be a dataclass."""
        from llm_council.reasoning.tracker import ReasoningUsage
        from dataclasses import is_dataclass

        usage = ReasoningUsage(
            model_id="openai/o1",
            reasoning_tokens=2000,
            budget_tokens=32000,
            efficiency=0.0625,
        )
        assert is_dataclass(usage)

    def test_reasoning_usage_has_required_fields(self):
        """ReasoningUsage should have model_id, reasoning_tokens, budget_tokens, efficiency."""
        from llm_council.reasoning.tracker import ReasoningUsage

        usage = ReasoningUsage(
            model_id="openai/o1",
            reasoning_tokens=5000,
            budget_tokens=10000,
            efficiency=0.5,
        )
        assert usage.model_id == "openai/o1"
        assert usage.reasoning_tokens == 5000
        assert usage.budget_tokens == 10000
        assert usage.efficiency == 0.5

    def test_under_budget_property_true(self):
        """under_budget should return True when reasoning_tokens <= budget_tokens."""
        from llm_council.reasoning.tracker import ReasoningUsage

        usage = ReasoningUsage(
            model_id="openai/o1",
            reasoning_tokens=5000,
            budget_tokens=10000,
            efficiency=0.5,
        )
        assert usage.under_budget is True

    def test_under_budget_property_false(self):
        """under_budget should return False when reasoning_tokens > budget_tokens."""
        from llm_council.reasoning.tracker import ReasoningUsage

        usage = ReasoningUsage(
            model_id="openai/o1",
            reasoning_tokens=15000,
            budget_tokens=10000,
            efficiency=1.5,
        )
        assert usage.under_budget is False


class TestExtractReasoningUsage:
    """Test extract_reasoning_usage function."""

    def test_extracts_reasoning_tokens_from_response(self):
        """Should extract reasoning_tokens from usage dict."""
        from llm_council.reasoning.tracker import extract_reasoning_usage

        response = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 500,
                "reasoning_tokens": 2000,
            },
        }
        usage = extract_reasoning_usage(response, "openai/o1", budget=32000)

        assert usage is not None
        assert usage.reasoning_tokens == 2000
        assert usage.budget_tokens == 32000

    def test_extracts_from_alternate_format(self):
        """Should extract from reasoning_details.tokens if available."""
        from llm_council.reasoning.tracker import extract_reasoning_usage

        response = {
            "choices": [{"message": {"content": "response"}}],
            "reasoning_details": {"tokens": 1500},
            "usage": {"prompt_tokens": 100, "completion_tokens": 500},
        }
        usage = extract_reasoning_usage(response, "openai/o1", budget=32000)

        assert usage is not None
        assert usage.reasoning_tokens == 1500

    def test_returns_none_for_non_reasoning_response(self):
        """Should return None if no reasoning tokens in response."""
        from llm_council.reasoning.tracker import extract_reasoning_usage

        response = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 500},
        }
        usage = extract_reasoning_usage(response, "openai/gpt-4o", budget=32000)

        assert usage is None

    def test_calculates_efficiency_ratio(self):
        """Should calculate efficiency as reasoning_tokens / budget_tokens."""
        from llm_council.reasoning.tracker import extract_reasoning_usage

        response = {
            "usage": {"reasoning_tokens": 8000},
        }
        usage = extract_reasoning_usage(response, "openai/o1", budget=32000)

        assert usage is not None
        assert usage.efficiency == 0.25  # 8000 / 32000


class TestAggregatedUsage:
    """Test AggregatedUsage dataclass."""

    def test_aggregated_usage_dataclass_exists(self):
        """AggregatedUsage should be a dataclass."""
        from llm_council.reasoning.tracker import AggregatedUsage
        from dataclasses import is_dataclass

        agg = AggregatedUsage(
            total_reasoning_tokens=10000,
            total_budget_tokens=64000,
            overall_efficiency=0.15625,
            per_model=[],
            models_over_budget=0,
        )
        assert is_dataclass(agg)

    def test_aggregated_usage_has_required_fields(self):
        """AggregatedUsage should have all required fields."""
        from llm_council.reasoning.tracker import AggregatedUsage, ReasoningUsage

        per_model = [
            ReasoningUsage("openai/o1", 5000, 32000, 0.156),
            ReasoningUsage("openai/o3-mini", 3000, 16000, 0.188),
        ]
        agg = AggregatedUsage(
            total_reasoning_tokens=8000,
            total_budget_tokens=48000,
            overall_efficiency=0.167,
            per_model=per_model,
            models_over_budget=0,
        )
        assert agg.total_reasoning_tokens == 8000
        assert agg.total_budget_tokens == 48000
        assert len(agg.per_model) == 2
        assert agg.models_over_budget == 0


class TestAggregateReasoningUsage:
    """Test aggregate_reasoning_usage function."""

    def test_aggregates_usage_across_models(self):
        """Should sum totals across all models."""
        from llm_council.reasoning.tracker import (
            ReasoningUsage,
            aggregate_reasoning_usage,
        )

        usages = [
            ReasoningUsage("openai/o1", 5000, 32000, 0.156),
            ReasoningUsage("openai/o3-mini", 3000, 16000, 0.188),
        ]
        agg = aggregate_reasoning_usage(usages)

        assert agg.total_reasoning_tokens == 8000
        assert agg.total_budget_tokens == 48000

    def test_aggregate_calculates_overall_efficiency(self):
        """Should calculate overall efficiency as total_reasoning / total_budget."""
        from llm_council.reasoning.tracker import (
            ReasoningUsage,
            aggregate_reasoning_usage,
        )

        usages = [
            ReasoningUsage("openai/o1", 16000, 32000, 0.5),
            ReasoningUsage("openai/o3-mini", 8000, 16000, 0.5),
        ]
        agg = aggregate_reasoning_usage(usages)

        assert agg.overall_efficiency == 0.5  # 24000 / 48000

    def test_aggregate_counts_models_over_budget(self):
        """Should count how many models exceeded their budget."""
        from llm_council.reasoning.tracker import (
            ReasoningUsage,
            aggregate_reasoning_usage,
        )

        usages = [
            ReasoningUsage("openai/o1", 16000, 32000, 0.5),  # under budget
            ReasoningUsage("openai/o3-mini", 20000, 16000, 1.25),  # over budget
        ]
        agg = aggregate_reasoning_usage(usages)

        assert agg.models_over_budget == 1

    def test_aggregate_handles_empty_list(self):
        """Should handle empty list gracefully."""
        from llm_council.reasoning.tracker import aggregate_reasoning_usage

        agg = aggregate_reasoning_usage([])

        assert agg.total_reasoning_tokens == 0
        assert agg.total_budget_tokens == 0
        assert agg.overall_efficiency == 0.0
        assert agg.models_over_budget == 0
        assert len(agg.per_model) == 0


class TestReasoningModuleExportsTracker:
    """Test that tracker types are exported from reasoning module."""

    def test_module_exports_reasoning_usage(self):
        """reasoning module should export ReasoningUsage."""
        from llm_council.reasoning import ReasoningUsage

        assert ReasoningUsage is not None

    def test_module_exports_aggregated_usage(self):
        """reasoning module should export AggregatedUsage."""
        from llm_council.reasoning import AggregatedUsage

        assert AggregatedUsage is not None

    def test_module_exports_extract_function(self):
        """reasoning module should export extract_reasoning_usage."""
        from llm_council.reasoning import extract_reasoning_usage

        assert callable(extract_reasoning_usage)

    def test_module_exports_aggregate_function(self):
        """reasoning module should export aggregate_reasoning_usage."""
        from llm_council.reasoning import aggregate_reasoning_usage

        assert callable(aggregate_reasoning_usage)
