"""Prompt optimizer for ADR-020 Tier 2.

Applies per-model prompt adaptation while preserving semantic equivalence.
Per council recommendation: "Translation, not Rewriting"
"""

from typing import Dict, List


def get_model_provider(model_id: str) -> str:
    """Extract provider from model ID (e.g., 'anthropic/claude' -> 'anthropic')."""
    if "/" not in model_id:
        return "unknown"

    provider = model_id.split("/")[0].lower()

    # Normalize known providers
    known_providers = {
        "anthropic",
        "openai",
        "google",
        "meta-llama",
        "mistralai",
        "cohere",
        "deepseek",
        "x-ai",
    }

    if provider in known_providers:
        return provider

    return "unknown"


class PromptOptimizer:
    """Per-model prompt adapter for council queries.

    Applies syntactic adaptations based on model provider preferences
    while preserving the canonical intent of the query.

    Per ADR-020 council recommendation:
    - Apply "Translation" not "Rewriting"
    - Extract canonical intent (immutable core)
    - Apply syntactic adapters per model preferences
    - Fallback to original prompt if adaptation fails
    """

    def __init__(
        self,
        enabled: bool = True,
        verify_semantic_equivalence: bool = False,
    ):
        """Initialize optimizer.

        Args:
            enabled: Whether optimization is enabled (False = passthrough)
            verify_semantic_equivalence: Whether to verify adapted prompts
        """
        self.enabled = enabled
        self.verify_semantic_equivalence = verify_semantic_equivalence

    def optimize(self, prompt: str, models: List[str]) -> Dict[str, str]:
        """Optimize prompt for each model.

        Args:
            prompt: Original user query
            models: List of model identifiers

        Returns:
            Dict mapping model ID to adapted prompt
        """
        if not self.enabled:
            return {model: prompt for model in models}

        result = {}
        for model in models:
            provider = get_model_provider(model)
            adapted = self._adapt_for_provider(prompt, provider)
            result[model] = adapted

        return result

    def _adapt_for_provider(self, prompt: str, provider: str) -> str:
        """Apply provider-specific prompt adaptation.

        Args:
            prompt: Original prompt
            provider: Model provider name

        Returns:
            Adapted prompt for the provider
        """
        if provider == "anthropic":
            return self._adapt_anthropic(prompt)
        elif provider == "openai":
            return self._adapt_openai(prompt)
        elif provider == "google":
            return self._adapt_google(prompt)
        else:
            # Fallback: return original prompt
            return prompt

    def _adapt_anthropic(self, prompt: str) -> str:
        """Adapt prompt for Anthropic Claude models.

        Claude works well with XML-structured prompts.
        """
        return f"<query>\n{prompt}\n</query>"

    def _adapt_openai(self, prompt: str) -> str:
        """Adapt prompt for OpenAI models.

        OpenAI works well with clear, markdown-formatted text.
        Using minimal adaptation to preserve original intent.
        """
        return prompt

    def _adapt_google(self, prompt: str) -> str:
        """Adapt prompt for Google Gemini models.

        Gemini works well with structured, clear prompts.
        Using minimal adaptation to preserve original intent.
        """
        return prompt

    def extract_intent(self, prompt: str) -> str:
        """Extract canonical intent from prompt.

        This is the immutable core of the query that must be
        preserved across all adaptations.

        Args:
            prompt: Original user prompt

        Returns:
            Canonical intent string
        """
        # For now, canonical intent is the prompt itself
        # Future: could use NLP to extract key concepts
        return prompt

    def verify_equivalence(self, prompts: Dict[str, str]) -> bool:
        """Verify semantic equivalence across adapted prompts.

        Args:
            prompts: Dict mapping model to adapted prompt

        Returns:
            True if all prompts are semantically equivalent
        """
        if not self.verify_semantic_equivalence:
            return True

        # Simple heuristic: check all prompts contain same core content
        # Future: could use embeddings for semantic similarity
        if len(prompts) < 2:
            return True

        # Extract content (strip XML tags, etc.)
        contents = []
        for prompt in prompts.values():
            # Strip XML tags
            import re

            content = re.sub(r"<[^>]+>", "", prompt).strip()
            contents.append(content)

        # All contents should be identical
        return len(set(contents)) == 1
