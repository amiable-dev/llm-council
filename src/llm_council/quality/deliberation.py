"""
ADR-036: Deliberation Depth Index (DDI)

Quantifies how thoroughly the council considered the query.
"""

import re
from typing import List, Optional, Protocol, Tuple
import logging

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers (OpenRouter, local, etc.)."""

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts, returning vectors."""
        ...


def _tokenize(text: str) -> set:
    """Simple tokenization for Jaccard similarity fallback."""
    # Lowercase, split on non-alphanumeric, filter single-char tokens
    # Min 2 chars to include domain terms like AI, ML, IO, etc.
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    return set(tokens)


def _jaccard_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two texts."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)

    if not tokens1 and not tokens2:
        return 1.0  # Both empty = identical

    if not tokens1 or not tokens2:
        return 0.0  # One empty = completely different

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union)


def _calculate_diversity_fallback(responses: List[str]) -> float:
    """
    Calculate response diversity using Jaccard similarity (no embeddings).

    Returns average pairwise dissimilarity (1 - similarity).
    """
    if len(responses) < 2:
        return 0.0

    dissimilarities = []
    for i, resp1 in enumerate(responses):
        for resp2 in responses[i + 1 :]:
            similarity = _jaccard_similarity(resp1, resp2)
            dissimilarities.append(1.0 - similarity)

    return sum(dissimilarities) / len(dissimilarities) if dissimilarities else 0.0


async def _calculate_diversity_with_embeddings(
    responses: List[str], provider: EmbeddingProvider
) -> float:
    """
    Calculate response diversity using embedding cosine distances.

    Returns average pairwise cosine distance.
    """
    if len(responses) < 2:
        return 0.0

    try:
        embeddings = await provider.embed(responses)

        distances = []
        for i, emb1 in enumerate(embeddings):
            for emb2 in embeddings[i + 1 :]:
                # Cosine similarity
                dot_product = sum(a * b for a, b in zip(emb1, emb2))
                norm1 = sum(a * a for a in emb1) ** 0.5
                norm2 = sum(b * b for b in emb2) ** 0.5

                if norm1 > 0 and norm2 > 0:
                    similarity = dot_product / (norm1 * norm2)
                    distances.append(1.0 - similarity)
                else:
                    distances.append(1.0)

        return sum(distances) / len(distances) if distances else 0.0

    except Exception as e:
        logger.warning(f"Embedding diversity calculation failed, using fallback: {e}")
        return _calculate_diversity_fallback(responses)


def _calculate_coverage(stage2_rankings: List[dict], num_stage1_responses: int) -> float:
    """
    Calculate review coverage: what fraction of expected reviews were received.

    In a full council, each of N models reviews all N responses (including their own
    response anonymously), so expected = N reviews, each covering N responses.
    We simplify to: actual_reviewers / expected_reviewers.
    """
    if num_stage1_responses == 0:
        return 0.0

    expected_reviewers = num_stage1_responses
    actual_reviewers = len(stage2_rankings)

    return min(1.0, actual_reviewers / expected_reviewers)


def _calculate_richness(justifications: List[str]) -> float:
    """
    Calculate critique richness based on justification length/detail.

    Longer, more detailed justifications indicate more thorough review.
    Target: 50 tokens = 1.0 richness.
    """
    if not justifications:
        return 0.0

    token_counts = [len(j.split()) for j in justifications if j.strip()]

    if not token_counts:
        return 0.0

    avg_tokens = sum(token_counts) / len(token_counts)

    # Normalize: 50 tokens = 1.0, scale linearly up to that
    return min(1.0, avg_tokens / 50.0)


def _extract_justifications(stage2_rankings: List[dict]) -> List[str]:
    """
    Extract justification text from Stage 2 results.

    Stage 2 results contain the full evaluation text before the FINAL RANKING.
    """
    justifications = []

    for result in stage2_rankings:
        content = result.get("content", "") or result.get("raw_text", "")

        # Extract text before FINAL RANKING (the justification/evaluation part)
        if "FINAL RANKING:" in content:
            justification = content.split("FINAL RANKING:")[0].strip()
        else:
            justification = content.strip()

        if justification:
            justifications.append(justification)

    return justifications


async def deliberation_depth_index(
    stage1_responses: List[str],
    stage2_rankings: List[dict],
    embedding_provider: Optional[EmbeddingProvider] = None,
) -> Tuple[float, dict]:
    """
    Calculate Deliberation Depth Index (DDI).

    Formula: DDI = (diversity * 0.35) + (coverage * 0.35) + (richness * 0.30)

    Args:
        stage1_responses: List of Stage 1 response texts.
        stage2_rankings: List of Stage 2 ranking results.
        embedding_provider: Optional provider for embedding-based diversity.

    Returns:
        Tuple of (ddi_score, component_breakdown).
    """
    if not stage1_responses:
        return 0.0, {"diversity": 0.0, "coverage": 0.0, "richness": 0.0}

    # Calculate components
    if embedding_provider:
        diversity = await _calculate_diversity_with_embeddings(stage1_responses, embedding_provider)
    else:
        diversity = _calculate_diversity_fallback(stage1_responses)

    coverage = _calculate_coverage(stage2_rankings, len(stage1_responses))

    justifications = _extract_justifications(stage2_rankings)
    richness = _calculate_richness(justifications)

    # Weighted combination
    ddi = (diversity * 0.35) + (coverage * 0.35) + (richness * 0.30)

    components = {
        "diversity": round(diversity, 3),
        "coverage": round(coverage, 3),
        "richness": round(richness, 3),
    }

    return round(ddi, 3), components


def deliberation_depth_index_sync(
    stage1_responses: List[str],
    stage2_rankings: List[dict],
) -> Tuple[float, dict]:
    """
    Synchronous version using Jaccard similarity fallback.

    Use this when async is not available or embeddings are not needed.
    """
    if not stage1_responses:
        return 0.0, {"diversity": 0.0, "coverage": 0.0, "richness": 0.0}

    diversity = _calculate_diversity_fallback(stage1_responses)
    coverage = _calculate_coverage(stage2_rankings, len(stage1_responses))

    justifications = _extract_justifications(stage2_rankings)
    richness = _calculate_richness(justifications)

    ddi = (diversity * 0.35) + (coverage * 0.35) + (richness * 0.30)

    components = {
        "diversity": round(diversity, 3),
        "coverage": round(coverage, 3),
        "richness": round(richness, 3),
    }

    return round(ddi, 3), components
