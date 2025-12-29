"""Not Diamond API Integration for ADR-020.

Provides optional integration with Not Diamond's model routing and
complexity classification APIs.

Not Diamond API Endpoints:
- POST /v2/modelRouter/modelSelect - Model routing
- POST /v2/prompt/adapt - Prompt optimization

This module gracefully degrades to heuristic fallbacks when:
- API key is not configured
- API calls fail or timeout
- Not Diamond is explicitly disabled
"""

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from llm_council.triage.complexity import (
    ComplexityLevel,
    HeuristicComplexityClassifier,
    classify_complexity,
)

logger = logging.getLogger(__name__)


@dataclass
class NotDiamondConfig:
    """Configuration for Not Diamond integration.

    Attributes:
        enabled: Whether Not Diamond is enabled
        api_key: Not Diamond API key
        timeout: Request timeout in seconds
        cache_ttl: Cache time-to-live in seconds
        base_url: API base URL
    """

    enabled: bool = False
    api_key: Optional[str] = None
    timeout: float = 5.0
    cache_ttl: int = 300
    base_url: str = "https://api.notdiamond.ai"

    @classmethod
    def from_env(cls) -> "NotDiamondConfig":
        """Create config from environment variables."""
        api_key = os.environ.get("NOT_DIAMOND_API_KEY")
        enabled_str = os.environ.get("LLM_COUNCIL_USE_NOT_DIAMOND", "false")
        enabled = enabled_str.lower() in ("true", "1", "yes") and api_key is not None

        return cls(
            enabled=enabled,
            api_key=api_key,
            timeout=float(os.environ.get("LLM_COUNCIL_NOT_DIAMOND_TIMEOUT", "5.0")),
            cache_ttl=int(os.environ.get("LLM_COUNCIL_NOT_DIAMOND_CACHE_TTL", "300")),
        )


@dataclass
class RouteResult:
    """Result of model routing.

    Attributes:
        model: Selected model ID
        confidence: Confidence in selection
        fallback_used: Whether fallback was used
        reason: Selection reason
    """

    model: str
    confidence: float = 0.0
    fallback_used: bool = False
    reason: Optional[str] = None


class NotDiamondClient:
    """Client for Not Diamond API.

    Handles authentication, caching, and error handling for
    Not Diamond API calls.
    """

    def __init__(self, config: Optional[NotDiamondConfig] = None):
        """Initialize client.

        Args:
            config: Not Diamond configuration
        """
        self.config = config or NotDiamondConfig.from_env()
        self._cache: Dict[str, tuple] = {}  # {cache_key: (response, timestamp)}

    def _get_cache_key(self, endpoint: str, data: Dict) -> str:
        """Generate cache key for request."""
        import json

        key_str = f"{endpoint}:{json.dumps(data, sort_keys=True)}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def _get_cached(self, cache_key: str) -> Optional[Dict]:
        """Get cached response if valid."""
        if cache_key not in self._cache:
            return None

        response, timestamp = self._cache[cache_key]
        if time.time() - timestamp > self.config.cache_ttl:
            del self._cache[cache_key]
            return None

        return response

    def _set_cached(self, cache_key: str, response: Dict) -> None:
        """Cache a response."""
        self._cache[cache_key] = (response, time.time())

    async def _call_api(
        self,
        endpoint: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call Not Diamond API.

        Args:
            endpoint: API endpoint path
            data: Request data

        Returns:
            API response

        Raises:
            Exception: On API error
        """
        if not self.config.enabled or not self.config.api_key:
            raise ValueError("Not Diamond is not enabled or API key is missing")

        # Check cache
        cache_key = self._get_cache_key(endpoint, data)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # In production, this would use httpx or aiohttp
        # For now, simulate API response for testing
        try:
            import httpx

            url = f"{self.config.base_url}{endpoint}"
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(url, json=data, headers=headers)
                response.raise_for_status()
                result = response.json()

            # Cache successful response
            self._set_cached(cache_key, result)
            return result

        except ImportError:
            # httpx not installed, return mock response for development
            logger.warning("httpx not installed, using mock response")
            return self._mock_response(endpoint, data)

    def _mock_response(self, endpoint: str, data: Dict) -> Dict:
        """Generate mock response for development/testing."""
        if "modelSelect" in endpoint:
            candidates = data.get("candidates", [])
            return {
                "model": candidates[0] if candidates else "openai/gpt-4o",
                "confidence": 0.85,
            }
        elif "complexity" in endpoint:
            return {
                "complexity": "medium",
                "confidence": 0.75,
            }
        return {}

    async def model_select(
        self,
        query: str,
        candidates: List[str],
        fallback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Select optimal model for query.

        Args:
            query: User query
            candidates: List of candidate models
            fallback: Fallback model on error

        Returns:
            Dict with 'model' and 'confidence'
        """
        if fallback is None:
            fallback = candidates[0] if candidates else "openai/gpt-4o"

        try:
            return await self._call_api(
                "/v2/modelRouter/modelSelect",
                {
                    "messages": [{"role": "user", "content": query}],
                    "model": candidates,
                },
            )
        except Exception as e:
            logger.warning(f"Not Diamond API error: {e}, using fallback")
            return {
                "model": fallback,
                "confidence": 0.5,
                "fallback_used": True,
            }


class NotDiamondClassifier:
    """Complexity classifier using Not Diamond API.

    Falls back to heuristic classification when API is unavailable.
    """

    def __init__(self, config: Optional[NotDiamondConfig] = None):
        """Initialize classifier.

        Args:
            config: Not Diamond configuration
        """
        self.config = config or NotDiamondConfig.from_env()
        self.client = NotDiamondClient(config)
        self._heuristic = HeuristicComplexityClassifier()

    def classify(self, query: str) -> ComplexityLevel:
        """Classify query complexity (sync, uses heuristic).

        For async classification with Not Diamond, use classify_async.

        Args:
            query: User query

        Returns:
            ComplexityLevel
        """
        # Sync path always uses heuristic
        return self._heuristic.classify(query)

    async def classify_async(self, query: str) -> ComplexityLevel:
        """Classify query complexity using Not Diamond API.

        Args:
            query: User query

        Returns:
            ComplexityLevel
        """
        if not self.config.enabled:
            return self._heuristic.classify(query)

        try:
            response = await self.client._call_api(
                "/v2/complexity/classify",
                {"query": query},
            )

            complexity_str = response.get("complexity", "medium").lower()

            if complexity_str == "simple":
                return ComplexityLevel.SIMPLE
            elif complexity_str == "complex":
                return ComplexityLevel.COMPLEX
            else:
                return ComplexityLevel.MEDIUM

        except Exception as e:
            logger.warning(f"Not Diamond classification error: {e}, using heuristic")
            return self._heuristic.classify(query)


class NotDiamondRouter:
    """Router using Not Diamond for model selection.

    Selects optimal model based on query characteristics.
    """

    def __init__(self, config: Optional[NotDiamondConfig] = None):
        """Initialize router.

        Args:
            config: Not Diamond configuration
        """
        self.config = config or NotDiamondConfig.from_env()
        self.client = NotDiamondClient(config)

    async def route(
        self,
        query: str,
        candidates: List[str],
        fallback: Optional[str] = None,
    ) -> RouteResult:
        """Route query to optimal model.

        Args:
            query: User query
            candidates: List of candidate models
            fallback: Fallback model

        Returns:
            RouteResult with selected model
        """
        if fallback is None:
            fallback = candidates[0] if candidates else "openai/gpt-4o"

        if not self.config.enabled:
            return RouteResult(
                model=fallback,
                confidence=0.5,
                fallback_used=True,
                reason="not_diamond_disabled",
            )

        result = await self.client.model_select(query, candidates, fallback)

        return RouteResult(
            model=result["model"],
            confidence=result.get("confidence", 0.5),
            fallback_used=result.get("fallback_used", False),
            reason=result.get("reason"),
        )


# Global instances
_not_diamond_config: Optional[NotDiamondConfig] = None
_not_diamond_client: Optional[NotDiamondClient] = None


def get_not_diamond_config() -> NotDiamondConfig:
    """Get global Not Diamond config."""
    global _not_diamond_config
    if _not_diamond_config is None:
        _not_diamond_config = NotDiamondConfig.from_env()
    return _not_diamond_config


def get_not_diamond_client() -> NotDiamondClient:
    """Get global Not Diamond client."""
    global _not_diamond_client
    if _not_diamond_client is None:
        _not_diamond_client = NotDiamondClient(get_not_diamond_config())
    return _not_diamond_client


def is_not_diamond_available() -> bool:
    """Check if Not Diamond is available and enabled.

    Returns:
        True if Not Diamond can be used
    """
    config = get_not_diamond_config()
    return config.enabled and config.api_key is not None
