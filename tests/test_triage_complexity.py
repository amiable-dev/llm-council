"""Tests for complexity classifier (ADR-020 Tier 1).

TDD: Write these tests first, then implement complexity.py.
"""

import pytest


class TestComplexityLevel:
    """Test ComplexityLevel enum."""

    def test_complexity_level_has_required_values(self):
        """ComplexityLevel should have SIMPLE, MEDIUM, COMPLEX."""
        from llm_council.triage.complexity import ComplexityLevel

        assert ComplexityLevel.SIMPLE.value == "simple"
        assert ComplexityLevel.MEDIUM.value == "medium"
        assert ComplexityLevel.COMPLEX.value == "complex"


class TestClassifyComplexity:
    """Test classify_complexity() entry point."""

    def test_classify_complexity_returns_complexity_level(self):
        """classify_complexity should return ComplexityLevel."""
        from llm_council.triage.complexity import classify_complexity, ComplexityLevel

        result = classify_complexity("What is 2 + 2?")

        assert isinstance(result, ComplexityLevel)

    def test_classify_complexity_simple_query(self):
        """Short, simple queries should be SIMPLE."""
        from llm_council.triage.complexity import classify_complexity, ComplexityLevel

        result = classify_complexity("What is the capital of France?")

        assert result == ComplexityLevel.SIMPLE

    def test_classify_complexity_complex_query(self):
        """Technical, multi-part queries should be COMPLEX."""
        from llm_council.triage.complexity import classify_complexity, ComplexityLevel

        # Multi-part query with technical keywords and explicit ordering
        query = """First, analyze the following code for security vulnerabilities.
        Second, explain the time complexity of the algorithm.
        Finally, suggest optimizations for better performance in a distributed system."""

        result = classify_complexity(query)

        assert result == ComplexityLevel.COMPLEX


class TestHeuristicComplexityClassifier:
    """Test HeuristicComplexityClassifier."""

    def test_classifier_exists(self):
        """HeuristicComplexityClassifier should be importable."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier

        classifier = HeuristicComplexityClassifier()
        assert classifier is not None

    def test_classifier_has_classify_method(self):
        """Classifier should have classify() method."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier

        classifier = HeuristicComplexityClassifier()
        assert hasattr(classifier, "classify")
        assert callable(classifier.classify)

    def test_short_query_is_simple(self):
        """Very short queries should be classified as SIMPLE."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier, ComplexityLevel

        classifier = HeuristicComplexityClassifier()
        result = classifier.classify("Hello")

        assert result == ComplexityLevel.SIMPLE

    def test_long_query_tends_complex(self):
        """Very long queries should tend toward COMPLEX."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier, ComplexityLevel

        classifier = HeuristicComplexityClassifier()
        query = "Please explain " + "in great detail " * 20 + "the topic."

        result = classifier.classify(query)

        assert result in (ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX)

    def test_technical_keywords_increase_complexity(self):
        """Technical keywords should increase complexity."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier, ComplexityLevel

        classifier = HeuristicComplexityClassifier()
        query = "Analyze the algorithm complexity and optimize the code"

        result = classifier.classify(query)

        assert result in (ComplexityLevel.MEDIUM, ComplexityLevel.COMPLEX)

    def test_multipart_questions_are_complex(self):
        """Multi-part questions should be COMPLEX."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier, ComplexityLevel

        classifier = HeuristicComplexityClassifier()
        query = "First, explain X. Then, analyze Y. Finally, compare Z."

        result = classifier.classify(query)

        assert result == ComplexityLevel.COMPLEX


class TestComplexitySignals:
    """Test individual complexity signal detection."""

    def test_detect_multipart(self):
        """Should detect multi-part questions."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier

        classifier = HeuristicComplexityClassifier()

        assert classifier._has_multipart_signals("First, do X. Second, do Y.")
        assert not classifier._has_multipart_signals("What is Python?")

    def test_detect_technical_keywords(self):
        """Should detect technical keywords."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier

        classifier = HeuristicComplexityClassifier()

        assert classifier._has_technical_keywords("analyze the algorithm")
        assert not classifier._has_technical_keywords("what time is it")


class TestNotDiamondClassifier:
    """Test NotDiamondClassifier placeholder."""

    def test_not_diamond_classifier_exists(self):
        """NotDiamondClassifier should be importable."""
        from llm_council.triage.complexity import NotDiamondClassifier

        classifier = NotDiamondClassifier()
        assert classifier is not None

    def test_not_diamond_raises_not_implemented(self):
        """NotDiamondClassifier.classify should raise NotImplementedError."""
        from llm_council.triage.complexity import NotDiamondClassifier

        classifier = NotDiamondClassifier()

        with pytest.raises(NotImplementedError):
            classifier.classify("test query")


class TestClassifierConfiguration:
    """Test classifier configuration options."""

    def test_heuristic_thresholds_configurable(self):
        """HeuristicComplexityClassifier should accept threshold config."""
        from llm_council.triage.complexity import HeuristicComplexityClassifier

        # Custom thresholds
        classifier = HeuristicComplexityClassifier(
            simple_max_length=50,
            complex_min_length=200,
        )

        assert classifier.simple_max_length == 50
        assert classifier.complex_min_length == 200


class TestComplexityResult:
    """Test ComplexityResult dataclass."""

    def test_complexity_result_has_level(self):
        """ComplexityResult should have complexity level."""
        from llm_council.triage.complexity import ComplexityResult, ComplexityLevel

        result = ComplexityResult(
            level=ComplexityLevel.MEDIUM,
            confidence=0.8,
        )

        assert result.level == ComplexityLevel.MEDIUM

    def test_complexity_result_has_confidence(self):
        """ComplexityResult should have confidence score."""
        from llm_council.triage.complexity import ComplexityResult, ComplexityLevel

        result = ComplexityResult(
            level=ComplexityLevel.SIMPLE,
            confidence=0.95,
        )

        assert result.confidence == 0.95

    def test_complexity_result_has_signals(self):
        """ComplexityResult should have detected signals."""
        from llm_council.triage.complexity import ComplexityResult, ComplexityLevel

        result = ComplexityResult(
            level=ComplexityLevel.COMPLEX,
            confidence=0.9,
            signals=["multipart", "technical_keywords", "long_query"],
        )

        assert "multipart" in result.signals


class TestClassifyComplexityDetailed:
    """Test classify_complexity_detailed for full results."""

    def test_classify_complexity_detailed_returns_result(self):
        """classify_complexity_detailed should return ComplexityResult."""
        from llm_council.triage.complexity import classify_complexity_detailed, ComplexityResult

        result = classify_complexity_detailed("Test query")

        assert isinstance(result, ComplexityResult)

    def test_classify_complexity_detailed_includes_signals(self):
        """Detailed classification should include detected signals."""
        from llm_council.triage.complexity import classify_complexity_detailed

        result = classify_complexity_detailed(
            "First, analyze the code. Then, optimize the algorithm."
        )

        assert result.signals is not None
        assert len(result.signals) > 0
