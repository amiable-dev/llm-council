"""Ollama gateway implementation for LLM Council (ADR-025).

This module provides local LLM support via Ollama using LiteLLM as the adapter.
Enables air-gapped deployments, cost-free testing, and privacy-first usage.

Quality degradation notices are included to inform users when local models
may have reduced capabilities compared to cloud models.
"""

import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING

# Import configuration from unified_config (ADR-025a alignment)
from llm_council.unified_config import OllamaProviderConfig, get_config

# Hardware profiles for deployment guidance (per ADR-025)
# These are recommendations, not enforced requirements
OLLAMA_HARDWARE_PROFILES = {
    "minimum": {
        "description": "8+ core CPU, 16GB RAM, SSD",
        "models": ["7b-q4"],
        "use_case": "Development/testing only",
    },
    "recommended": {
        "description": "Apple M-series Pro/Max, 32GB unified memory",
        "models": ["7b", "13b-q4"],
        "use_case": "Small council (2-3 local models)",
    },
    "professional": {
        "description": "2x RTX 4090/5090, 64GB+ system RAM",
        "models": ["70b-q4", "70b"],
        "use_case": "Production single-tenant",
    },
    "enterprise": {
        "description": "Mac Studio 64GB+ / multi-GPU workstation",
        "models": ["70b concurrent", "multiple 13b"],
        "use_case": "Air-gapped production, multi-model council",
    },
}

if TYPE_CHECKING:
    from llm_council.unified_config import OllamaProviderConfig

from .base import (
    BaseRouter,
    HealthStatus,
    RouterCapabilities,
    RouterHealth,
)
from .types import (
    CanonicalMessage,
    ContentBlock,
    GatewayRequest,
    GatewayResponse,
    UsageInfo,
)


@dataclass
class QualityDegradationNotice:
    """Notice about potential quality degradation with local models.

    Per ADR-025, local models may have reduced capabilities compared to
    cloud-hosted frontier models. This notice informs users of the trade-offs.
    """

    is_local_model: bool
    warning_message: str
    suggested_hardware_profile: Optional[str] = None
    model_size_estimate: Optional[str] = None


class OllamaGateway(BaseRouter):
    """Ollama gateway implementing BaseRouter protocol.

    Provides access to local LLMs via Ollama, using LiteLLM as the adapter.
    Includes quality degradation notices per ADR-025.
    """

    def __init__(
        self,
        config: Optional[OllamaProviderConfig] = None,
        *,
        # Legacy parameters (deprecated, kept for backwards compatibility)
        base_url: Optional[str] = None,
        default_timeout: Optional[float] = None,
    ):
        """Initialize the Ollama gateway.

        Args:
            config: OllamaProviderConfig from unified_config.py (preferred).
            base_url: DEPRECATED - Ollama API URL. Use config instead.
            default_timeout: DEPRECATED - Request timeout. Use config instead.

        Example:
            # Preferred (ADR-025a aligned):
            from llm_council.unified_config import get_config
            config = get_config()
            gateway = OllamaGateway(config.gateways.providers["ollama"])

            # Legacy (deprecated, still works):
            gateway = OllamaGateway(base_url="http://localhost:11434")
        """
        if config is not None:
            # Use provided config directly
            self._config = config
        elif base_url is not None or default_timeout is not None:
            # Legacy params - emit deprecation warning
            warnings.warn(
                "base_url and default_timeout parameters are deprecated. "
                "Pass OllamaProviderConfig from unified_config instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._config = OllamaProviderConfig(
                base_url=base_url or "http://localhost:11434",
                timeout_seconds=default_timeout or 120.0,
            )
        else:
            # Default: load from unified config
            unified_config = get_config()
            ollama_provider = unified_config.gateways.providers.get("ollama")
            if isinstance(ollama_provider, OllamaProviderConfig):
                self._config = ollama_provider
            else:
                # Fallback to default config
                self._config = OllamaProviderConfig()

        # Set instance variables from config
        self._base_url = self._config.base_url
        self._default_timeout = self._config.timeout_seconds
        self._litellm = None  # Lazy import
        self._capabilities = RouterCapabilities(
            supports_streaming=True,
            supports_tools=True,  # Model-dependent, but LiteLLM handles it
            supports_vision=True,  # Model-dependent (llava, etc.)
            supports_json_mode=True,  # Model-dependent
            supports_byok=False,  # No API key needed for local
            requires_byok=False,
        )

    @property
    def router_id(self) -> str:
        """Return the router identifier."""
        return "ollama"

    @property
    def capabilities(self) -> RouterCapabilities:
        """Return the capabilities of this router."""
        return self._capabilities

    def _get_litellm(self):
        """Lazily import and return the LiteLLM module.

        Raises:
            ImportError: If LiteLLM is not installed with helpful message.
        """
        if self._litellm is None:
            try:
                import litellm

                self._litellm = litellm
            except ImportError as e:
                raise ImportError(
                    "LiteLLM is required for Ollama support. "
                    "Install it with: pip install 'llm-council-core[ollama]'"
                ) from e
        return self._litellm

    def _is_local_model(self, model: str) -> bool:
        """Check if model is a local Ollama model.

        Args:
            model: Model identifier.

        Returns:
            True if model starts with 'ollama/'.
        """
        return model.startswith("ollama/")

    def _get_model_name(self, model: str) -> str:
        """Get the model name in LiteLLM format.

        Args:
            model: Model identifier (may or may not have 'ollama/' prefix).

        Returns:
            Model name with 'ollama/' prefix for LiteLLM.
        """
        if model.startswith("ollama/"):
            return model
        return f"ollama/{model}"

    def _extract_model_name(self, model: str) -> str:
        """Extract the raw model name without prefix.

        Args:
            model: Model identifier with 'ollama/' prefix.

        Returns:
            Model name without 'ollama/' prefix.
        """
        if model.startswith("ollama/"):
            return model[7:]  # len("ollama/") = 7
        return model

    def _convert_message(self, msg: CanonicalMessage) -> Dict[str, Any]:
        """Convert CanonicalMessage to LiteLLM message format.

        Args:
            msg: Canonical message to convert.

        Returns:
            LiteLLM-format message dict.
        """
        # Check if we have any image content
        has_images = any(block.type == "image" for block in msg.content)

        if has_images:
            # Multi-part content for vision models
            content_parts = []
            for block in msg.content:
                if block.type == "text" and block.text:
                    content_parts.append({"type": "text", "text": block.text})
                elif block.type == "image" and block.image_url:
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": block.image_url}}
                    )
            return {"role": msg.role, "content": content_parts}
        else:
            # Simple text content - concatenate all text blocks
            text_content = " ".join(
                block.text for block in msg.content if block.type == "text" and block.text
            )
            return {"role": msg.role, "content": text_content}

    def _convert_messages(self, messages: List[CanonicalMessage]) -> List[Dict[str, Any]]:
        """Convert list of CanonicalMessages to LiteLLM format."""
        return [self._convert_message(msg) for msg in messages]

    def _create_quality_degradation_notice(self, model: str) -> QualityDegradationNotice:
        """Create a quality degradation notice for local models.

        Per ADR-025, local models may have reduced capabilities compared to
        cloud-hosted frontier models. This provides transparency to users.

        Args:
            model: Model identifier.

        Returns:
            QualityDegradationNotice with warning and hardware suggestions.
        """
        model_name = self._extract_model_name(model)

        # Estimate model size from name for hardware profile suggestion
        suggested_profile = "recommended"  # Default
        model_size = None

        # Parse common model size indicators
        lower_model = model_name.lower()
        if "70b" in lower_model:
            suggested_profile = "professional"
            model_size = "70B"
        elif "13b" in lower_model or "14b" in lower_model:
            suggested_profile = "recommended"
            model_size = "13-14B"
        elif "7b" in lower_model or "8b" in lower_model:
            suggested_profile = "minimum"
            model_size = "7-8B"
        elif "3b" in lower_model or "2b" in lower_model or "1b" in lower_model:
            suggested_profile = "minimum"
            model_size = "1-3B"
        else:
            # Unknown size, suggest minimum for small models
            suggested_profile = "minimum"

        return QualityDegradationNotice(
            is_local_model=True,
            warning_message=(
                f"Using local model '{model_name}' via Ollama. "
                "Local models may have reduced quality compared to cloud-hosted frontier models. "
                "Consider using cloud models for production workloads."
            ),
            suggested_hardware_profile=suggested_profile,
            model_size_estimate=model_size,
        )

    async def _query_ollama(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: float,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a query to Ollama via LiteLLM.

        This is the core method that calls LiteLLM's async completion.

        Args:
            model: Model identifier in 'ollama/model' format.
            messages: LiteLLM-format messages.
            timeout: Request timeout.
            max_tokens: Max tokens to generate.
            temperature: Sampling temperature.

        Returns:
            Structured result dict with status, content, latency_ms, etc.
        """
        litellm = self._get_litellm()

        start_time = time.time()

        try:
            # Build kwargs for LiteLLM
            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "api_base": self._base_url,
                "timeout": timeout,
            }

            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                kwargs["temperature"] = temperature

            # Call LiteLLM async completion
            response = await litellm.acompletion(**kwargs)

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract content from response
            content = response.choices[0].message.content

            # Extract usage if available
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return {
                "status": "ok",
                "content": content,
                "latency_ms": latency_ms,
                "usage": usage,
            }

        except ConnectionRefusedError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "status": "error",
                "latency_ms": latency_ms,
                "error": (
                    f"Connection refused to Ollama at {self._base_url}. "
                    "Is Ollama running? Start it with: ollama serve"
                ),
            }

        except TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "status": "timeout",
                "latency_ms": latency_ms,
                "error": f"Timeout after {timeout}s waiting for Ollama",
            }

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_str = str(e).lower()

            # Check for connection-related errors
            if "connection" in error_str or "refused" in error_str:
                return {
                    "status": "error",
                    "latency_ms": latency_ms,
                    "error": (
                        f"Connection error to Ollama at {self._base_url}. "
                        "Is Ollama running? Start it with: ollama serve"
                    ),
                }

            # Check for timeout-related errors
            if "timeout" in error_str:
                return {
                    "status": "timeout",
                    "latency_ms": latency_ms,
                    "error": f"Timeout: {e}",
                }

            return {
                "status": "error",
                "latency_ms": latency_ms,
                "error": str(e),
            }

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """Send a completion request and return the response.

        Args:
            request: The gateway request with model and messages.

        Returns:
            GatewayResponse with the generated content.
        """
        # Convert messages to LiteLLM format
        messages = self._convert_messages(request.messages)

        # Ensure model has correct format
        model = self._get_model_name(request.model)

        # Determine timeout
        timeout = request.timeout if request.timeout is not None else self._default_timeout

        # Make the request
        result = await self._query_ollama(
            model=model,
            messages=messages,
            timeout=timeout,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        # Convert usage to UsageInfo if present
        usage = None
        if result.get("usage"):
            usage_data = result["usage"]
            usage = UsageInfo(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

        return GatewayResponse(
            content=result.get("content", ""),
            model=request.model,
            status=result["status"],
            usage=usage,
            latency_ms=result.get("latency_ms"),
            error=result.get("error"),
        )

    async def complete_stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        """Send a streaming completion request.

        Args:
            request: The gateway request with model and messages.

        Yields:
            String chunks of the generated content.

        Note:
            Currently yields the complete response as a single chunk.
            True streaming can be added in a future iteration.
        """
        # For now, just yield the complete response
        response = await self.complete(request)
        if response.content:
            yield response.content

    async def health_check(self) -> RouterHealth:
        """Check the health of this router.

        Sends a ping to Ollama to verify connectivity.

        Returns:
            RouterHealth with current status and metrics.
        """
        start_time = time.time()

        try:
            # Try to complete a simple request
            result = await self._query_ollama(
                model="ollama/llama3.2",  # Common model for health check
                messages=[{"role": "user", "content": "ping"}],
                timeout=10.0,
                max_tokens=10,
            )

            now = datetime.now()
            latency = float(result.get("latency_ms", 0))

            if result["status"] == "ok":
                return RouterHealth(
                    router_id=self.router_id,
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency,
                    last_check=now,
                )
            else:
                return RouterHealth(
                    router_id=self.router_id,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency,
                    last_check=now,
                    error_message=result.get("error"),
                )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return RouterHealth(
                router_id=self.router_id,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                last_check=datetime.now(),
                error_message=str(e),
            )
