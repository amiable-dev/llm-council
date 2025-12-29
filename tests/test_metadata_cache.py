"""TDD tests for ADR-026: TTL Cache Infrastructure.

Tests for the caching layer that supports dynamic model metadata.
"""

import pytest
import time
from typing import Any, Optional


class TestTTLCache:
    """Test TTLCache basic functionality."""

    def test_cache_stores_and_retrieves_values(self):
        """Cache should store and retrieve values by key."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        cache.set("key1", {"value": "test"})

        assert cache.get("key1") == {"value": "test"}

    def test_cache_returns_none_for_missing_key(self):
        """Cache should return None for missing keys."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        assert cache.get("nonexistent") is None

    def test_cache_expires_after_ttl(self):
        """Cache entries should expire after TTL."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=0.1)  # 100ms TTL
        cache.set("key1", "value1")

        time.sleep(0.15)  # Wait for expiry
        assert cache.get("key1") is None

    def test_cache_respects_maxsize(self):
        """Cache should evict oldest entries when maxsize exceeded."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=2, ttl=3600)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_cache_clear_removes_all_entries(self):
        """cache.clear() should remove all entries."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_size_returns_current_count(self):
        """cache.size() should return current entry count."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        assert cache.size() == 0

        cache.set("key1", "value1")
        assert cache.size() == 1

        cache.set("key2", "value2")
        assert cache.size() == 2

    def test_cache_update_refreshes_expiry(self):
        """Setting same key should refresh its expiry."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=0.2)  # 200ms TTL
        cache.set("key1", "value1")

        time.sleep(0.1)  # Wait 100ms
        cache.set("key1", "value1_updated")  # Refresh

        time.sleep(0.15)  # Wait another 150ms (total 250ms from first set)
        # Original would have expired, but refresh should keep it alive
        assert cache.get("key1") == "value1_updated"

    def test_cache_contains_check(self):
        """Cache should support 'in' operator."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        cache.set("key1", "value1")

        assert "key1" in cache
        assert "key2" not in cache


class TestCacheStatistics:
    """Test cache statistics and monitoring."""

    def test_cache_tracks_hits_and_misses(self):
        """Cache should track hit/miss statistics."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        cache.set("key1", "value1")

        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("missing")  # Miss

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1

    def test_cache_hit_rate_calculation(self):
        """Cache should calculate hit rate."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        cache.set("key1", "value1")

        cache.get("key1")  # Hit
        cache.get("missing")  # Miss

        stats = cache.stats()
        assert stats["hit_rate"] == 0.5

    def test_cache_hit_rate_zero_when_no_requests(self):
        """Hit rate should be 0 when no requests made."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        stats = cache.stats()
        assert stats["hit_rate"] == 0.0

    def test_cache_stats_includes_size(self):
        """Stats should include current cache size."""
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=100, ttl=3600)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["maxsize"] == 100


class TestModelIntelligenceCache:
    """Test ModelIntelligenceCache composite cache."""

    def test_has_registry_cache_with_1hr_ttl(self):
        """Registry cache should have 1 hour TTL."""
        from llm_council.metadata.cache import ModelIntelligenceCache

        cache = ModelIntelligenceCache()
        assert cache.registry_cache.ttl == 3600

    def test_has_availability_cache_with_5min_ttl(self):
        """Availability cache should have 5 minute TTL."""
        from llm_council.metadata.cache import ModelIntelligenceCache

        cache = ModelIntelligenceCache()
        assert cache.availability_cache.ttl == 300

    def test_registry_maxsize_is_500(self):
        """Registry cache should hold 500 entries."""
        from llm_council.metadata.cache import ModelIntelligenceCache

        cache = ModelIntelligenceCache()
        assert cache.registry_cache.maxsize == 500

    def test_availability_maxsize_is_500(self):
        """Availability cache should hold 500 entries."""
        from llm_council.metadata.cache import ModelIntelligenceCache

        cache = ModelIntelligenceCache()
        assert cache.availability_cache.maxsize == 500

    def test_caches_can_be_configured_via_init(self):
        """Cache TTLs should be configurable."""
        from llm_council.metadata.cache import ModelIntelligenceCache

        cache = ModelIntelligenceCache(registry_ttl=7200, availability_ttl=600)
        assert cache.registry_cache.ttl == 7200
        assert cache.availability_cache.ttl == 600

    def test_clear_all_clears_both_caches(self):
        """clear_all() should clear both caches."""
        from llm_council.metadata.cache import ModelIntelligenceCache

        cache = ModelIntelligenceCache()
        cache.registry_cache.set("model1", {"data": "test"})
        cache.availability_cache.set("model1", True)

        cache.clear_all()

        assert cache.registry_cache.get("model1") is None
        assert cache.availability_cache.get("model1") is None

    def test_stats_combines_both_caches(self):
        """stats() should return combined statistics."""
        from llm_council.metadata.cache import ModelIntelligenceCache

        cache = ModelIntelligenceCache()
        cache.registry_cache.set("model1", {"data": "test"})
        cache.registry_cache.get("model1")  # Hit
        cache.availability_cache.get("missing")  # Miss

        stats = cache.stats()
        assert "registry" in stats
        assert "availability" in stats
        assert stats["registry"]["hits"] == 1
        assert stats["availability"]["misses"] == 1


class TestCacheThreadSafety:
    """Test cache thread safety."""

    def test_concurrent_reads_and_writes(self):
        """Cache should handle concurrent access."""
        import threading
        from llm_council.metadata.cache import TTLCache

        cache = TTLCache(maxsize=1000, ttl=3600)
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"key_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"key_{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
