"""Tests for response caching."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from llm_council.cache import (
    get_cache_key,
    get_cached_response,
    save_to_cache,
    clear_cache,
    get_cache_stats,
)


class TestGetCacheKey:
    """Tests for cache key generation."""

    def test_deterministic_key(self):
        """Same query produces same key."""
        key1 = get_cache_key("What is Python?")
        key2 = get_cache_key("What is Python?")
        assert key1 == key2

    def test_different_queries_different_keys(self):
        """Different queries produce different keys."""
        key1 = get_cache_key("What is Python?")
        key2 = get_cache_key("What is JavaScript?")
        assert key1 != key2

    def test_key_length(self):
        """Cache key is 16 hex characters."""
        key = get_cache_key("Test query")
        assert len(key) == 16
        assert all(c in "0123456789abcdef" for c in key)

    def test_config_affects_key(self):
        """Different config produces different key."""
        with patch("llm_council.cache.COUNCIL_MODELS", ["model-a", "model-b"]):
            key1 = get_cache_key("Test query")

        with patch("llm_council.cache.COUNCIL_MODELS", ["model-c", "model-d"]):
            key2 = get_cache_key("Test query")

        assert key1 != key2


class TestCacheOperations:
    """Tests for cache read/write operations."""

    def test_save_and_retrieve(self):
        """Save to cache and retrieve."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            with patch("llm_council.cache.CACHE_ENABLED", True):
                with patch("llm_council.cache.CACHE_DIR", cache_dir):
                    with patch("llm_council.cache.CACHE_TTL", 0):
                        cache_key = "test123456789abc"

                        stage1 = [{"model": "test", "response": "Hello"}]
                        stage2 = [{"model": "test", "ranking": "1. A"}]
                        stage3 = {"final_answer": "Test answer"}
                        metadata = {"config": {"mode": "consensus"}}

                        save_to_cache(cache_key, stage1, stage2, stage3, metadata)

                        cached = get_cached_response(cache_key)

                        assert cached is not None
                        assert cached["stage1_results"] == stage1
                        assert cached["stage2_results"] == stage2
                        assert cached["stage3_result"] == stage3

    def test_cache_miss(self):
        """Return None for non-existent cache entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            with patch("llm_council.cache.CACHE_ENABLED", True):
                with patch("llm_council.cache.CACHE_DIR", cache_dir):
                    cached = get_cached_response("nonexistent12345")
                    assert cached is None

    def test_cache_disabled(self):
        """Return None when caching is disabled."""
        with patch("llm_council.cache.CACHE_ENABLED", False):
            cached = get_cached_response("anykey123456789")
            assert cached is None

    def test_ttl_expiry(self):
        """Expired cache entries return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            with patch("llm_council.cache.CACHE_ENABLED", True):
                with patch("llm_council.cache.CACHE_DIR", cache_dir):
                    # Save with TTL = 0 (infinite)
                    with patch("llm_council.cache.CACHE_TTL", 0):
                        cache_key = "ttltest123456789"
                        save_to_cache(cache_key, [], [], {}, {})

                    # Manually set cached_at to past
                    cache_file = cache_dir / f"{cache_key}.json"
                    with open(cache_file, "r") as f:
                        data = json.load(f)
                    data["_cached_at"] = time.time() - 100
                    with open(cache_file, "w") as f:
                        json.dump(data, f)

                    # Now check with TTL = 60 (entry should be expired)
                    with patch("llm_council.cache.CACHE_TTL", 60):
                        cached = get_cached_response(cache_key)
                        assert cached is None

    def test_infinite_ttl(self):
        """TTL = 0 means infinite (no expiry)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            with patch("llm_council.cache.CACHE_ENABLED", True):
                with patch("llm_council.cache.CACHE_DIR", cache_dir):
                    with patch("llm_council.cache.CACHE_TTL", 0):
                        cache_key = "infinitettl12345"
                        save_to_cache(cache_key, [], [], {}, {})

                        # Manually set cached_at to very old time
                        cache_file = cache_dir / f"{cache_key}.json"
                        with open(cache_file, "r") as f:
                            data = json.load(f)
                        data["_cached_at"] = time.time() - 86400 * 365  # 1 year ago
                        with open(cache_file, "w") as f:
                            json.dump(data, f)

                        # Should still be valid with TTL = 0
                        cached = get_cached_response(cache_key)
                        assert cached is not None


class TestCacheManagement:
    """Tests for cache management functions."""

    def test_clear_cache(self):
        """Clear all cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            with patch("llm_council.cache.CACHE_ENABLED", True):
                with patch("llm_council.cache.CACHE_DIR", cache_dir):
                    with patch("llm_council.cache.CACHE_TTL", 0):
                        # Add some cache entries
                        save_to_cache("key1_123456789ab", [], [], {}, {})
                        save_to_cache("key2_123456789ab", [], [], {}, {})

                        assert len(list(cache_dir.glob("*.json"))) == 2

                        count = clear_cache()

                        assert count == 2
                        assert len(list(cache_dir.glob("*.json"))) == 0

    def test_get_cache_stats(self):
        """Get cache statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            with patch("llm_council.cache.CACHE_ENABLED", True):
                with patch("llm_council.cache.CACHE_DIR", cache_dir):
                    with patch("llm_council.cache.CACHE_TTL", 3600):
                        save_to_cache("stats_test123456", [], [], {}, {})

                        stats = get_cache_stats()

                        assert stats["enabled"] is True
                        assert stats["entries"] == 1
                        assert stats["total_size_bytes"] > 0
                        assert stats["ttl_seconds"] == 3600
                        assert "oldest_entry" in stats
                        assert "newest_entry" in stats

    def test_empty_cache_stats(self):
        """Get stats for empty cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)

            with patch("llm_council.cache.CACHE_ENABLED", True):
                with patch("llm_council.cache.CACHE_DIR", cache_dir):
                    stats = get_cache_stats()

                    assert stats["entries"] == 0
                    assert stats["total_size_bytes"] == 0
