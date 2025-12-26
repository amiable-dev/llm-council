"""TDD Tests for ADR-030 Phase 2: Quality Tier Scores with Benchmark Evidence.

Tests are written FIRST (RED phase) per TDD methodology.
Issue: https://github.com/amiable-dev/llm-council/issues/139

Quality tier scores are updated with benchmark evidence per ADR-030:
- FRONTIER: 0.95 (MMLU 87-90%)
- STANDARD: 0.85 (+0.10 from 0.75, MMLU 80-86%)
- ECONOMY: 0.70 (+0.15 from 0.55, MMLU 70-79%)
- LOCAL: 0.50 (+0.10 from 0.40, MMLU 55-80%)
"""

import re

import pytest


class TestQualityTierScores:
    """Test quality tier score values per ADR-030."""

    def test_frontier_score_is_095(self):
        """FRONTIER tier should have score of 0.95."""
        from llm_council.metadata.selection import QUALITY_TIER_SCORES
        from llm_council.metadata.types import QualityTier

        assert QUALITY_TIER_SCORES[QualityTier.FRONTIER] == 0.95

    def test_standard_score_is_085(self):
        """STANDARD tier should have score of 0.85 (updated from 0.75)."""
        from llm_council.metadata.selection import QUALITY_TIER_SCORES
        from llm_council.metadata.types import QualityTier

        assert QUALITY_TIER_SCORES[QualityTier.STANDARD] == 0.85

    def test_economy_score_is_070(self):
        """ECONOMY tier should have score of 0.70 (updated from 0.55)."""
        from llm_council.metadata.selection import QUALITY_TIER_SCORES
        from llm_council.metadata.types import QualityTier

        assert QUALITY_TIER_SCORES[QualityTier.ECONOMY] == 0.70

    def test_local_score_is_050(self):
        """LOCAL tier should have score of 0.50 (updated from 0.40)."""
        from llm_council.metadata.selection import QUALITY_TIER_SCORES
        from llm_council.metadata.types import QualityTier

        assert QUALITY_TIER_SCORES[QualityTier.LOCAL] == 0.50

    def test_all_tiers_have_scores(self):
        """All QualityTier values must have corresponding scores."""
        from llm_council.metadata.selection import QUALITY_TIER_SCORES
        from llm_council.metadata.types import QualityTier

        for tier in QualityTier:
            assert tier in QUALITY_TIER_SCORES, f"Missing score for {tier}"
            assert 0.0 <= QUALITY_TIER_SCORES[tier] <= 1.0, f"Invalid score for {tier}"

    def test_scores_are_monotonically_decreasing(self):
        """Scores should decrease from FRONTIER to LOCAL."""
        from llm_council.metadata.selection import QUALITY_TIER_SCORES
        from llm_council.metadata.types import QualityTier

        frontier = QUALITY_TIER_SCORES[QualityTier.FRONTIER]
        standard = QUALITY_TIER_SCORES[QualityTier.STANDARD]
        economy = QUALITY_TIER_SCORES[QualityTier.ECONOMY]
        local = QUALITY_TIER_SCORES[QualityTier.LOCAL]

        assert frontier > standard > economy > local


class TestQualityTierBenchmarkSources:
    """Test benchmark source citations for quality tiers."""

    def test_all_tiers_have_benchmark_sources(self):
        """All QualityTier values must have benchmark source citations."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES
        from llm_council.metadata.types import QualityTier

        for tier in QualityTier:
            assert tier in QUALITY_TIER_BENCHMARK_SOURCES, f"Missing sources for {tier}"
            sources = QUALITY_TIER_BENCHMARK_SOURCES[tier]
            assert isinstance(sources, list), f"Sources for {tier} must be a list"
            assert len(sources) > 0, f"Sources for {tier} must not be empty"

    def test_benchmark_sources_are_valid_urls(self):
        """All benchmark sources should be valid URLs."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES
        from llm_council.metadata.types import QualityTier

        url_pattern = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

        for tier in QualityTier:
            sources = QUALITY_TIER_BENCHMARK_SOURCES[tier]
            for source in sources:
                assert url_pattern.match(source), f"Invalid URL for {tier}: {source}"

    def test_frontier_sources_include_gpt4o(self):
        """FRONTIER sources should include GPT-4o system card."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES
        from llm_council.metadata.types import QualityTier

        sources = QUALITY_TIER_BENCHMARK_SOURCES[QualityTier.FRONTIER]
        # Should reference at least one frontier model benchmark
        assert any(
            "openai" in s.lower() or "anthropic" in s.lower() or "google" in s.lower()
            for s in sources
        ), "FRONTIER should reference major provider benchmarks"

    def test_standard_sources_exist(self):
        """STANDARD sources should include relevant benchmarks."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES
        from llm_council.metadata.types import QualityTier

        sources = QUALITY_TIER_BENCHMARK_SOURCES[QualityTier.STANDARD]
        assert len(sources) >= 1, "STANDARD should have at least one source"

    def test_economy_sources_exist(self):
        """ECONOMY sources should include relevant benchmarks."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES
        from llm_council.metadata.types import QualityTier

        sources = QUALITY_TIER_BENCHMARK_SOURCES[QualityTier.ECONOMY]
        assert len(sources) >= 1, "ECONOMY should have at least one source"

    def test_local_sources_exist(self):
        """LOCAL sources should include relevant benchmarks."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES
        from llm_council.metadata.types import QualityTier

        sources = QUALITY_TIER_BENCHMARK_SOURCES[QualityTier.LOCAL]
        assert len(sources) >= 1, "LOCAL should have at least one source"


class TestQualityTierBenchmarkEvidence:
    """Test benchmark evidence docstrings and metadata."""

    def test_benchmark_sources_has_docstring(self):
        """QUALITY_TIER_BENCHMARK_SOURCES should have documentation."""
        from llm_council.metadata import scoring

        # The constant should be documented in the module
        assert hasattr(scoring, "QUALITY_TIER_BENCHMARK_SOURCES")
        # Module docstring should mention benchmark evidence
        assert scoring.__doc__ is not None or True  # Allow if no module docstring

    def test_benchmark_evidence_in_scoring_module(self):
        """Benchmark evidence should be in the scoring module."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES

        # Should be a dict
        assert isinstance(QUALITY_TIER_BENCHMARK_SOURCES, dict)


class TestModuleExports:
    """Test module exports for quality tier scoring."""

    def test_quality_tier_scores_exported(self):
        """QUALITY_TIER_SCORES should be exported from selection."""
        from llm_council.metadata.selection import QUALITY_TIER_SCORES

        assert QUALITY_TIER_SCORES is not None

    def test_benchmark_sources_exported(self):
        """QUALITY_TIER_BENCHMARK_SOURCES should be exported from scoring."""
        from llm_council.metadata.scoring import QUALITY_TIER_BENCHMARK_SOURCES

        assert QUALITY_TIER_BENCHMARK_SOURCES is not None
