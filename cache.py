"""
Caching layer for production optimization.
Implements in-memory cache with TTL for frequently accessed data.
"""
from typing import Dict, Optional, Any, Callable
from datetime import datetime, timedelta
import json
import hashlib
import threading


class CacheEntry:
    """Represents a single cache entry with TTL."""

    def __init__(self, value: Any, ttl_seconds: int = 300):
        self.value = value
        self.created_at = datetime.now()
        self.ttl_seconds = ttl_seconds

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        age = (datetime.now() - self.created_at).total_seconds()
        return age > self.ttl_seconds

    def age_seconds(self) -> float:
        """Get age of cache entry in seconds."""
        return (datetime.now() - self.created_at).total_seconds()


class Cache:
    """Thread-safe in-memory cache with TTL and hit/miss tracking."""

    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache. Returns None if expired or missing."""
        with self._lock:
            if key not in self._cache:
                self.misses += 1
                return None

            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                self.misses += 1
                return None

            self.hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in cache with TTL."""
        with self._lock:
            self._cache[key] = CacheEntry(value, ttl_seconds)

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired()
            ]
            for k in expired_keys:
                del self._cache[k]
            return len(expired_keys)

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            return {
                "hits": self.hits,
                "misses": self.misses,
                "total_requests": total,
                "hit_rate_percent": round(hit_rate, 2),
                "entries_count": len(self._cache),
                "expired_entries": sum(1 for v in self._cache.values() if v.is_expired())
            }

    def reset_stats(self) -> None:
        """Reset hit/miss counters."""
        with self._lock:
            self.hits = 0
            self.misses = 0


class CacheKey:
    """Helper for generating consistent cache keys."""

    @staticmethod
    def progress_stats(user_id: str = "public") -> str:
        """Cache key for per-user progress statistics."""
        return f"progress_stats:{user_id}"

    @staticmethod
    def overall_stats() -> str:
        """Cache key for overall statistics."""
        return "overall_stats"

    @staticmethod
    def user_history(user_id: str, limit: int = 10) -> str:
        """Cache key for user analysis history."""
        return f"history:{user_id}:{limit}"

    @staticmethod
    def user_profile(user_id: str) -> str:
        """Cache key for user profile data."""
        return f"user:{user_id}"

    @staticmethod
    def analysis(analysis_id: str) -> str:
        """Cache key for individual analysis."""
        return f"analysis:{analysis_id}"


# Global cache instance
_cache = Cache()


def get_cache() -> Cache:
    """Get the global cache instance."""
    return _cache


def cached(ttl_seconds: int = 300, key_func: Optional[Callable] = None):
    """
    Decorator for caching function results.

    Args:
        ttl_seconds: Time to live for cache entry
        key_func: Optional function to generate cache key from function args
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: hash function name and all args
                key_parts = [func.__name__] + [str(arg) for arg in args] + [
                    f"{k}={v}" for k, v in sorted(kwargs.items())
                ]
                cache_key = hashlib.md5(
                    ":".join(key_parts).encode()
                ).hexdigest()

            # Try cache
            cached_value = _cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Compute and cache
            result = func(*args, **kwargs)
            _cache.set(cache_key, result, ttl_seconds)
            return result

        return wrapper
    return decorator
