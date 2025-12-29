"""Confidence-Gated Fast Path for ADR-020 Tier 1.

Implements the council-recommended "Confidence-Gated Fast Path" that allows
simple queries to bypass the full council when model confidence is high.

Flow:
    1. Route query to single model
    2. Model responds with confidence score
    3. Decision gate:
       - confidence >= 0.92 AND low_risk: Return single response
       - else: Escalate to full council

Audit: 5% shadow council sampling (see shadow_sampling.py)
Rollback trigger: shadow_council_disagreement_rate > 8%
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from llm_council.tier_contract import TierContract
from llm_council.triage.complexity import (
    ComplexityLevel,
    classify_complexity_detailed,
)
from llm_council.layer_contracts import (
    LayerEventType,
    emit_layer_event,
)


@dataclass
class FastPathConfig:
    """Configuration for fast path routing.

    Attributes:
        enabled: Whether fast path is enabled (default: False)
        confidence_threshold: Minimum confidence to use fast path (default: 0.92)
        model: Model to use for fast path ("auto" or specific model ID)
        max_query_length: Maximum query length for fast path eligibility
    """

    enabled: bool = False
    confidence_threshold: float = 0.92
    model: str = "auto"
    max_query_length: int = 500

    def __post_init__(self):
        """Validate configuration."""
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError(
                f"Confidence threshold must be between 0 and 1, got {self.confidence_threshold}"
            )

    @classmethod
    def from_env(cls) -> "FastPathConfig":
        """Create config from environment variables.

        Environment variables:
            LLM_COUNCIL_FAST_PATH_ENABLED: true/false
            LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD: 0.0-1.0
            LLM_COUNCIL_FAST_PATH_MODEL: auto or model ID
        """
        enabled_str = os.environ.get("LLM_COUNCIL_FAST_PATH_ENABLED", "false")
        enabled = enabled_str.lower() in ("true", "1", "yes")

        threshold_str = os.environ.get("LLM_COUNCIL_FAST_PATH_CONFIDENCE_THRESHOLD", "0.92")
        threshold = float(threshold_str)

        model = os.environ.get("LLM_COUNCIL_FAST_PATH_MODEL", "auto")

        max_length_str = os.environ.get("LLM_COUNCIL_FAST_PATH_MAX_QUERY_LENGTH", "500")
        max_length = int(max_length_str)

        return cls(
            enabled=enabled,
            confidence_threshold=threshold,
            model=model,
            max_query_length=max_length,
        )


@dataclass
class FastPathResult:
    """Result of fast path routing.

    Attributes:
        used_fast_path: Whether fast path was attempted
        response: Model response content (if fast path used)
        model: Model used for fast path
        confidence: Extracted confidence score
        escalated: Whether query was escalated to full council
        escalation_reason: Reason for escalation (if any)
    """

    used_fast_path: bool
    response: Optional[str] = None
    model: Optional[str] = None
    confidence: float = 0.0
    escalated: bool = False
    escalation_reason: Optional[str] = None


# High confidence keywords
HIGH_CONFIDENCE_KEYWORDS = {
    "certain",
    "definitely",
    "absolutely",
    "clearly",
    "obviously",
    "undoubtedly",
    "without doubt",
    "certainly",
    "surely",
    "confident",
}

# Low confidence keywords
LOW_CONFIDENCE_KEYWORDS = {
    "maybe",
    "perhaps",
    "possibly",
    "might",
    "could be",
    "not sure",
    "uncertain",
    "unclear",
    "I think",
    "I believe",
    "seems like",
    "probably",
    "likely",
    "appears to",
    "guess",
    "assume",
}


class ConfidenceExtractor:
    """Extract confidence scores from model responses.

    Supports multiple extraction methods:
    1. Structured: Direct confidence field in response
    2. Explicit: "X% confident" in text
    3. Keyword-based: High/low confidence language patterns
    """

    def __init__(self, default_confidence: float = 0.7):
        """Initialize extractor.

        Args:
            default_confidence: Default when confidence not extractable
        """
        self.default_confidence = default_confidence

    def extract(self, response: Optional[Dict[str, Any]]) -> float:
        """Extract confidence from model response.

        Args:
            response: Model response dict with 'content' and optional 'confidence'

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if response is None:
            return 0.0

        # Method 1: Direct confidence field
        if "confidence" in response:
            return float(response["confidence"])

        # Get text content
        content = response.get("content", "")
        if not content:
            return 0.0

        # Method 2: Explicit percentage in text
        explicit = self._extract_explicit_percentage(content)
        if explicit is not None:
            return explicit

        # Method 3: Keyword-based detection
        return self._extract_from_keywords(content)

    def _extract_explicit_percentage(self, text: str) -> Optional[float]:
        """Extract explicit confidence percentage from text.

        Matches patterns like:
        - "I am 95% confident"
        - "95% sure"
        - "confidence: 0.95"
        """
        # Match percentage patterns
        percentage_pattern = r"(\d{1,3})%\s*(?:confident|sure|certain)"
        match = re.search(percentage_pattern, text.lower())
        if match:
            return int(match.group(1)) / 100

        # Match decimal patterns
        decimal_pattern = r"confidence[:\s]+(\d*\.?\d+)"
        match = re.search(decimal_pattern, text.lower())
        if match:
            value = float(match.group(1))
            return value if value <= 1 else value / 100

        return None

    def _extract_from_keywords(self, text: str) -> float:
        """Estimate confidence from language patterns."""
        text_lower = text.lower()

        # Count high and low confidence indicators
        high_count = sum(1 for kw in HIGH_CONFIDENCE_KEYWORDS if kw in text_lower)
        low_count = sum(1 for kw in LOW_CONFIDENCE_KEYWORDS if kw in text_lower)

        # Adjust from default based on keywords
        if high_count > low_count:
            # High confidence language
            return min(0.9 + (high_count * 0.02), 0.98)
        elif low_count > high_count:
            # Low confidence language
            return max(0.6 - (low_count * 0.05), 0.3)
        else:
            return self.default_confidence


class FastPathRouter:
    """Router for confidence-gated fast path.

    Determines if a query can bypass the full council based on:
    1. Query complexity (simple queries eligible)
    2. Model confidence (high confidence required)
    3. Safety flags (safety concerns escalate)
    """

    def __init__(self, config: Optional[FastPathConfig] = None):
        """Initialize router.

        Args:
            config: Fast path configuration (default: from env)
        """
        self.config = config or FastPathConfig.from_env()
        self.confidence_extractor = ConfidenceExtractor()

    def should_use_fast_path(self, query: str) -> bool:
        """Check if query is eligible for fast path.

        Args:
            query: User query

        Returns:
            True if query is eligible for fast path
        """
        if not self.config.enabled:
            return False

        # Check query length
        if len(query) > self.config.max_query_length:
            return False

        # Check complexity
        complexity = classify_complexity_detailed(query)
        if complexity.level == ComplexityLevel.COMPLEX:
            return False

        # Simple and medium queries are eligible
        return True

    def select_fast_path_model(self, tier_contract: Optional[TierContract] = None) -> str:
        """Select model for fast path.

        Args:
            tier_contract: Optional tier contract constraining model selection

        Returns:
            Model ID to use for fast path
        """
        if self.config.model != "auto":
            return self.config.model

        # Use first model from tier's allowed list
        if tier_contract is not None and tier_contract.allowed_models:
            return tier_contract.allowed_models[0]

        # Default fast path models (fast/cheap)
        return "openai/gpt-4o-mini"

    def get_timeout(self, tier_contract: Optional[TierContract] = None) -> float:
        """Get timeout for fast path query.

        Args:
            tier_contract: Optional tier contract with timeout constraints

        Returns:
            Timeout in seconds
        """
        if tier_contract is not None:
            return tier_contract.per_model_timeout_ms / 1000

        # Default: 30 seconds
        return 30.0

    def _emit_fast_path_event(
        self,
        query: str,
        result: "FastPathResult",
    ) -> None:
        """Emit L2_FAST_PATH_TRIGGERED event (ADR-024)."""
        # Get complexity for the query
        complexity_result = classify_complexity_detailed(query)

        emit_layer_event(
            LayerEventType.L2_FAST_PATH_TRIGGERED,
            {
                "query_complexity": complexity_result.level.value,
                "model": result.model,
                "confidence": result.confidence,
                "escalated": result.escalated,
                "escalation_reason": result.escalation_reason,
            },
            layer_from="L2",
            layer_to="L2",
        )

    async def route(
        self,
        query: str,
        tier_contract: Optional[TierContract] = None,
    ) -> FastPathResult:
        """Route query through fast path.

        Args:
            query: User query
            tier_contract: Optional tier contract

        Returns:
            FastPathResult with routing decision
        """
        if not self.should_use_fast_path(query):
            return FastPathResult(
                used_fast_path=False,
                escalated=True,
                escalation_reason="query_not_eligible",
            )

        # Select model and get response
        model = self.select_fast_path_model(tier_contract)
        response = await self._query_model(query, model, tier_contract)

        # Handle model failure
        if response is None:
            result = FastPathResult(
                used_fast_path=True,
                model=model,
                escalated=True,
                escalation_reason="model_error",
            )
            self._emit_fast_path_event(query, result)
            return result

        # Extract confidence
        confidence = self.confidence_extractor.extract(response)

        # Check safety flag
        if response.get("safety_flag", False):
            result = FastPathResult(
                used_fast_path=True,
                response=response.get("content"),
                model=model,
                confidence=confidence,
                escalated=True,
                escalation_reason="safety_flag_triggered",
            )
            self._emit_fast_path_event(query, result)
            return result

        # Check confidence threshold
        if confidence < self.config.confidence_threshold:
            result = FastPathResult(
                used_fast_path=True,
                response=response.get("content"),
                model=model,
                confidence=confidence,
                escalated=True,
                escalation_reason="confidence_below_threshold",
            )
            self._emit_fast_path_event(query, result)
            return result

        # Fast path successful
        result = FastPathResult(
            used_fast_path=True,
            response=response.get("content"),
            model=model,
            confidence=confidence,
            escalated=False,
        )
        self._emit_fast_path_event(query, result)
        return result

    async def _query_model(
        self,
        query: str,
        model: str,
        tier_contract: Optional[TierContract] = None,
    ) -> Optional[Dict[str, Any]]:
        """Query a single model.

        This method should be overridden or mocked in tests.

        Args:
            query: User query
            model: Model to query
            tier_contract: Optional tier contract

        Returns:
            Model response dict or None on error
        """
        from llm_council.gateway_adapter import query_model

        timeout = self.get_timeout(tier_contract)
        messages = [{"role": "user", "content": query}]

        try:
            return await query_model(model, messages, timeout=timeout)
        except Exception:
            return None


# Global fast path router instance
_fast_path_router: Optional[FastPathRouter] = None


def get_fast_path_router() -> FastPathRouter:
    """Get the global fast path router instance."""
    global _fast_path_router
    if _fast_path_router is None:
        _fast_path_router = FastPathRouter()
    return _fast_path_router


def is_fast_path_enabled() -> bool:
    """Check if fast path is enabled."""
    router = get_fast_path_router()
    return router.config.enabled
