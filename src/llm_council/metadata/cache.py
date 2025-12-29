"""TTL Cache Infrastructure for Model Intelligence (ADR-026 Phase 1).

This module provides time-based caching for model metadata with:
- Thread-safe TTL (time-to-live) cache with LRU eviction
- Composite cache for registry and availability data
- Statistics tracking for monitoring
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class TTLCache:
    """Thread-safe TTL cache with LRU eviction.

    Entries expire after the configured TTL (time-to-live) seconds.
    When maxsize is exceeded, the oldest entry is evicted (LRU).

    Args:
        maxsize: Maximum number of entries to store
        ttl: Time-to-live in seconds for each entry
    """

    def __init__(self, maxsize: int = 500, ttl: int = 3600):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.

        Returns None if the key is not found or has expired.

        Args:
            key: Cache key to look up

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expiry = self._cache[key]

            # Check if expired
            if time.time() > expiry:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            # Move to end for LRU ordering
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key
            value: Value to store
        """
        with self._lock:
            expiry = time.time() + self.ttl

            # If key exists, update it
            if key in self._cache:
                self._cache[key] = (value, expiry)
                self._cache.move_to_end(key)
            else:
                # Evict oldest if at capacity
                while len(self._cache) >= self.maxsize:
                    self._cache.popitem(last=False)

                self._cache[key] = (value, expiry)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def size(self) -> int:
        """Return the current number of entries in the cache."""
        with self._lock:
            # Clean up expired entries
            self._cleanup_expired()
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        with self._lock:
            if key not in self._cache:
                return False

            _, expiry = self._cache[key]
            if time.time() > expiry:
                del self._cache[key]
                return False

            return True

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, size, maxsize
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "maxsize": self.maxsize,
            }

    def _cleanup_expired(self) -> None:
        """Remove expired entries from the cache."""
        now = time.time()
        expired_keys = [key for key, (_, expiry) in self._cache.items() if now > expiry]
        for key in expired_keys:
            del self._cache[key]


class ModelIntelligenceCache:
    """Composite cache for model metadata.

    Provides separate caches for:
    - Registry: Model information (1 hour TTL by default)
    - Availability: Model availability status (5 minute TTL by default)

    Args:
        registry_ttl: TTL for registry cache in seconds (default 3600)
        availability_ttl: TTL for availability cache in seconds (default 300)
        maxsize: Maximum entries per cache (default 500)
    """

    def __init__(
        self,
        registry_ttl: int = 3600,
        availability_ttl: int = 300,
        maxsize: int = 500,
    ):
        self.registry_cache = TTLCache(maxsize=maxsize, ttl=registry_ttl)
        self.availability_cache = TTLCache(maxsize=maxsize, ttl=availability_ttl)

    def clear_all(self) -> None:
        """Clear both caches."""
        self.registry_cache.clear()
        self.availability_cache.clear()

    def stats(self) -> Dict[str, Dict[str, Any]]:
        """Return combined statistics for both caches.

        Returns:
            Dict with 'registry' and 'availability' sub-dicts
        """
        return {
            "registry": self.registry_cache.stats(),
            "availability": self.availability_cache.stats(),
        }
