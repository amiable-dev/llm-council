"""Complexity classifier for ADR-020 Tier 1.

Provides heuristic-based complexity classification for query triage.
Per council recommendation, this is a placeholder for the future
"Confidence-Gated Fast Path" design.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ComplexityLevel(Enum):
    """Query complexity levels for routing decisions."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class ComplexityResult:
    """Result of complexity classification.

    Contains the complexity level along with confidence and
    detected signals for transparency.
    """

    level: ComplexityLevel
    confidence: float
    signals: List[str] = field(default_factory=list)


# Technical keywords that indicate higher complexity
TECHNICAL_KEYWORDS = {
    "algorithm",
    "complexity",
    "analyze",
    "analysis",
    "optimize",
    "performance",
    "distributed",
    "security",
    "vulnerability",
    "architecture",
    "implement",
    "design",
    "debug",
    "refactor",
    "integration",
    "scalability",
    "concurrency",
    "parallel",
    "theorem",
    "proof",
    "derive",
    "mathematical",
}

# Multi-part question indicators
MULTIPART_INDICATORS = {
    "first,",
    "second,",
    "third,",
    "then,",
    "next,",
    "finally,",
    "additionally,",
    "also,",
    "furthermore,",
    "1.",
    "2.",
    "3.",
    "step 1",
    "step 2",
    "part 1",
    "part 2",
}


class HeuristicComplexityClassifier:
    """Heuristic-based complexity classifier.

    Uses simple rules to estimate query complexity:
    - Query length
    - Technical keywords
    - Multi-part question structure
    """

    def __init__(
        self,
        simple_max_length: int = 100,
        complex_min_length: int = 300,
    ):
        """Initialize classifier with thresholds.

        Args:
            simple_max_length: Max chars for SIMPLE classification
            complex_min_length: Min chars for COMPLEX tendency
        """
        self.simple_max_length = simple_max_length
        self.complex_min_length = complex_min_length

    def classify(self, query: str) -> ComplexityLevel:
        """Classify query complexity.

        Args:
            query: User query to classify

        Returns:
            ComplexityLevel (SIMPLE, MEDIUM, or COMPLEX)
        """
        result = self.classify_detailed(query)
        return result.level

    def classify_detailed(self, query: str) -> ComplexityResult:
        """Classify query with detailed result.

        Args:
            query: User query to classify

        Returns:
            ComplexityResult with level, confidence, and signals
        """
        signals = []
        complexity_score = 0

        # Length-based scoring
        query_len = len(query)
        if query_len <= self.simple_max_length:
            complexity_score -= 1
        elif query_len >= self.complex_min_length:
            complexity_score += 1
            signals.append("long_query")

        # Technical keywords
        if self._has_technical_keywords(query):
            complexity_score += 1
            signals.append("technical_keywords")

        # Multi-part questions
        if self._has_multipart_signals(query):
            complexity_score += 2  # Stronger signal
            signals.append("multipart")

        # Determine level from score
        if complexity_score <= -1:
            level = ComplexityLevel.SIMPLE
            confidence = 0.8 + (0.1 if query_len < 50 else 0)
        elif complexity_score >= 2:
            level = ComplexityLevel.COMPLEX
            confidence = 0.7 + (0.1 * min(complexity_score - 1, 2))
        else:
            level = ComplexityLevel.MEDIUM
            confidence = 0.6

        return ComplexityResult(
            level=level,
            confidence=min(confidence, 0.95),
            signals=signals,
        )

    def _has_technical_keywords(self, query: str) -> bool:
        """Check for technical keywords."""
        query_lower = query.lower()
        for keyword in TECHNICAL_KEYWORDS:
            if keyword in query_lower:
                return True
        return False

    def _has_multipart_signals(self, query: str) -> bool:
        """Check for multi-part question indicators."""
        query_lower = query.lower()
        for indicator in MULTIPART_INDICATORS:
            if indicator in query_lower:
                return True
        return False


class NotDiamondClassifier:
    """Not Diamond API classifier (placeholder).

    This is a placeholder for future integration with Not Diamond's
    complexity classification API. Currently raises NotImplementedError.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize classifier.

        Args:
            api_key: Not Diamond API key (optional)
        """
        self.api_key = api_key

    def classify(self, query: str) -> ComplexityLevel:
        """Classify query using Not Diamond API.

        Raises:
            NotImplementedError: Always (placeholder implementation)
        """
        raise NotImplementedError(
            "Not Diamond integration is not yet implemented. "
            "Use HeuristicComplexityClassifier as fallback."
        )


# Default classifier instance
_default_classifier = HeuristicComplexityClassifier()


def classify_complexity(query: str) -> ComplexityLevel:
    """Classify query complexity.

    Convenience function using the default heuristic classifier.

    Args:
        query: User query to classify

    Returns:
        ComplexityLevel (SIMPLE, MEDIUM, or COMPLEX)
    """
    return _default_classifier.classify(query)


def classify_complexity_detailed(query: str) -> ComplexityResult:
    """Classify query complexity with detailed result.

    Args:
        query: User query to classify

    Returns:
        ComplexityResult with level, confidence, and signals
    """
    return _default_classifier.classify_detailed(query)
