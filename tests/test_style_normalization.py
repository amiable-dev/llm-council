"""Tests for adaptive style normalization."""

import pytest
from llm_council.council import should_normalize_styles


class TestShouldNormalizeStyles:
    """Tests for the adaptive normalization detection function."""

    def test_single_response_returns_false(self):
        """Single response doesn't need normalization."""
        assert should_normalize_styles(["Only one response"]) is False

    def test_empty_responses_returns_false(self):
        """Empty list doesn't need normalization."""
        assert should_normalize_styles([]) is False

    def test_markdown_variance_triggers_normalization(self):
        """Mixed markdown/plain responses trigger normalization."""
        responses = [
            "# Heading\n\nThis is formatted with markdown.",
            "This is plain text without any markdown headers.",
        ]
        assert should_normalize_styles(responses) is True

    def test_uniform_markdown_no_normalization(self):
        """All markdown responses don't trigger normalization (based on markdown alone)."""
        responses = ["# Heading A\n\nSome content.", "# Heading B\n\nOther content."]
        # No markdown variance, but may trigger on other heuristics
        # For this specific case with similar lengths and no preambles, should be False
        assert should_normalize_styles(responses) is False

    def test_high_length_variance_triggers_normalization(self):
        """Highly variable response lengths trigger normalization."""
        responses = [
            "Short.",
            "This is a much longer response " * 50,  # ~1500 chars
        ]
        assert should_normalize_styles(responses) is True

    def test_similar_lengths_no_normalization(self):
        """Similar response lengths don't trigger normalization (based on length alone)."""
        responses = [
            "This is a response of moderate length with some detail.",
            "Another response with similar length and some content.",
        ]
        # Similar lengths, no markdown variance, no preambles
        assert should_normalize_styles(responses) is False

    def test_preamble_variance_triggers_normalization(self):
        """Mixed AI preambles trigger normalization."""
        responses = [
            "Certainly! I'd be happy to help with that. Here's the answer...",
            "The answer is 42.",
        ]
        assert should_normalize_styles(responses) is True

    def test_no_preambles_no_normalization(self):
        """No AI preambles don't trigger normalization (based on preambles alone)."""
        responses = ["The capital of France is Paris.", "Paris is the capital of France."]
        assert should_normalize_styles(responses) is False

    def test_all_preambles_no_normalization(self):
        """All having preambles doesn't trigger normalization (no variance)."""
        responses = ["Certainly! The answer is A.", "Great question! The answer is B."]
        # Both have preambles, so no variance to normalize
        assert should_normalize_styles(responses) is False

    def test_code_block_variance_triggers_normalization(self):
        """Mixed code blocks trigger normalization."""
        responses = [
            "Here's the code:\n```python\nprint('hello')\n```",
            "Use the print function to output hello.",
        ]
        assert should_normalize_styles(responses) is True

    def test_uniform_code_blocks_no_normalization(self):
        """All having code blocks doesn't trigger normalization."""
        responses = ["```python\nprint('a')\n```", "```python\nprint('b')\n```"]
        # Both have code blocks, similar lengths
        assert should_normalize_styles(responses) is False

    def test_multiple_heuristics_combined(self):
        """Multiple style differences should trigger normalization."""
        responses = [
            "# Response A\n\nCertainly! Here's my detailed answer with code:\n```python\nprint('hello')\n```\n"
            + "More content. " * 20,
            "It's 42.",
        ]
        # Has markdown variance, length variance, preamble variance, code variance
        assert should_normalize_styles(responses) is True

    def test_realistic_uniform_responses(self):
        """Realistically similar responses shouldn't trigger normalization."""
        responses = [
            "Python is a high-level programming language known for its readability.",
            "Python is a popular programming language with clear syntax.",
            "Python is a versatile language used for web development, data science, and more.",
        ]
        # Similar style, length, no preambles, no markdown, no code
        assert should_normalize_styles(responses) is False

    def test_realistic_diverse_responses(self):
        """Realistically diverse responses should trigger normalization."""
        responses = [
            "# Python Overview\n\n## Key Features\n- Readable syntax\n- Large ecosystem\n\n## Example\n```python\nprint('Hello')\n```",
            "As an AI language model, I'd be happy to explain Python! It's a great language.",
            "Python. Readable. Popular.",
        ]
        # Diverse styles, lengths, formats
        assert should_normalize_styles(responses) is True
