"""
ADR-036: Synthesis Attribution Score (SAS)

Measures how well the final synthesis traces back to peer-reviewed responses.
"""

import re
from typing import List, Optional, Protocol
import logging

from .types import SynthesisAttribution

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers (OpenRouter, local, etc.)."""

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts, returning vectors."""
        ...


def _tokenize(text: str) -> set:
    """Simple tokenization for Jaccard similarity fallback."""
    # Min 2 chars to include domain terms like AI, ML, IO, etc.
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    return set(tokens)


def _jaccard_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two texts."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)

    if not tokens1 and not tokens2:
        return 1.0

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union)


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5

    if norm1 > 0 and norm2 > 0:
        return dot_product / (norm1 * norm2)
    return 0.0


async def synthesis_attribution_score(
    synthesis: str,
    winning_responses: List[str],
    all_responses: List[str],
    embedding_provider: Optional[EmbeddingProvider] = None,
    grounding_threshold: float = 0.6,
) -> SynthesisAttribution:
    """
    Calculate Synthesis Attribution Score.

    Measures how well the final synthesis traces back to peer-reviewed responses.

    Args:
        synthesis: The Stage 3 synthesized response.
        winning_responses: Top-ranked responses (usually top 1-2).
        all_responses: All Stage 1 responses.
        embedding_provider: Optional provider for embedding-based similarity.
        grounding_threshold: Threshold for "grounded" determination (default 0.6).

    Returns:
        SynthesisAttribution with alignment scores and hallucination risk.
    """
    if not synthesis or not all_responses:
        return SynthesisAttribution(
            winner_alignment=0.0,
            max_source_alignment=0.0,
            hallucination_risk=1.0,
            grounded=False,
        )

    if embedding_provider:
        try:
            return await _attribution_with_embeddings(
                synthesis,
                winning_responses or all_responses[:1],
                all_responses,
                embedding_provider,
                grounding_threshold,
            )
        except Exception as e:
            logger.warning(f"Embedding attribution failed, using fallback: {e}")

    # Fallback to Jaccard similarity
    return _attribution_fallback(
        synthesis,
        winning_responses or all_responses[:1],
        all_responses,
        grounding_threshold,
    )


async def _attribution_with_embeddings(
    synthesis: str,
    winning_responses: List[str],
    all_responses: List[str],
    provider: EmbeddingProvider,
    grounding_threshold: float,
) -> SynthesisAttribution:
    """Calculate attribution using embedding similarity."""
    # Embed all texts together for efficiency
    all_texts = [synthesis] + winning_responses + all_responses
    embeddings = await provider.embed(all_texts)

    synthesis_emb = embeddings[0]
    winner_embs = embeddings[1 : 1 + len(winning_responses)]
    all_response_embs = embeddings[1 + len(winning_responses) :]

    # Winner alignment: average similarity to top-ranked responses
    if winner_embs:
        winner_similarities = [_cosine_similarity(synthesis_emb, emb) for emb in winner_embs]
        winner_alignment = sum(winner_similarities) / len(winner_similarities)
    else:
        winner_alignment = 0.0

    # Max source alignment: best match to any response
    all_similarities = [_cosine_similarity(synthesis_emb, emb) for emb in all_response_embs]
    max_source_alignment = max(all_similarities) if all_similarities else 0.0

    # Hallucination risk: how much synthesis diverges from all sources
    hallucination_risk = 1.0 - max_source_alignment

    # Grounded: synthesis traces back to at least one source
    grounded = max_source_alignment >= grounding_threshold

    return SynthesisAttribution(
        winner_alignment=round(winner_alignment, 3),
        max_source_alignment=round(max_source_alignment, 3),
        hallucination_risk=round(hallucination_risk, 3),
        grounded=grounded,
    )


def _attribution_fallback(
    synthesis: str,
    winning_responses: List[str],
    all_responses: List[str],
    grounding_threshold: float,
) -> SynthesisAttribution:
    """Calculate attribution using Jaccard similarity (no embeddings)."""
    # Winner alignment
    if winning_responses:
        winner_similarities = [_jaccard_similarity(synthesis, resp) for resp in winning_responses]
        winner_alignment = sum(winner_similarities) / len(winner_similarities)
    else:
        winner_alignment = 0.0

    # Max source alignment
    all_similarities = [_jaccard_similarity(synthesis, resp) for resp in all_responses]
    max_source_alignment = max(all_similarities) if all_similarities else 0.0

    # Hallucination risk
    hallucination_risk = 1.0 - max_source_alignment

    # Grounded
    grounded = max_source_alignment >= grounding_threshold

    return SynthesisAttribution(
        winner_alignment=round(winner_alignment, 3),
        max_source_alignment=round(max_source_alignment, 3),
        hallucination_risk=round(hallucination_risk, 3),
        grounded=grounded,
    )


def synthesis_attribution_score_sync(
    synthesis: str,
    winning_responses: List[str],
    all_responses: List[str],
    grounding_threshold: float = 0.6,
) -> SynthesisAttribution:
    """
    Synchronous version using Jaccard similarity fallback.

    Use this when async is not available or embeddings are not needed.
    """
    return _attribution_fallback(
        synthesis,
        winning_responses or all_responses[:1] if all_responses else [],
        all_responses,
        grounding_threshold,
    )
