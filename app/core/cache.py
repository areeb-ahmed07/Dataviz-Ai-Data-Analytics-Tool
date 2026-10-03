"""
DataViz Pro — High-Performance Caching Layer (Phase 13)

Provides:
- TTLCache: time-based expiration with LRU eviction
- UserCache: user-scoped caches that auto-invalidate on mutations
- DataframeCache: LRU cache for DataFrames (memory-bounded)
- QueryCache: transparent cache for expensive database aggregates

All caches are thread-safe and designed for Flask's multi-threaded model.
"""

import time
import threading
import logging
import hashlib
import pickle
from typing import Any, Optional, Callable, Dict, Tuple
from functools import wraps
from collections import OrderedDict

logger = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe LRU cache with per-entry TTL expiration.

    When maxsize is exceeded, the oldest (least recently used) entries
    are evicted. Expired entries are lazily cleaned on access.
    """

    def __init__(self, maxsize: int = 256, default_ttl: float = 60.0, name: str = "cache"):
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._name = name
        self._store: OrderedDict[str, Tuple[Any, float, float]] = OrderedDict()  # key -> (value, created, ttl)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if key in self._store:
                value, created, ttl = self._store[key]
                if time.time() - created < ttl:
                    self._store.move_to_end(key)  # Mark as recently used
                    self._hits += 1
                    return value
                else:
                    del self._store[key]  # Expired
            self._misses += 1
            return default

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            if key in self._store:
                del self._store[key]
            elif len(self._store) >= self._maxsize:
                self._store.popitem(last=False)  # Evict LRU
            self._store[key] = (value, time.time(), ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        """Delete all keys starting with prefix. Returns count of deleted entries."""
        with self._lock:
            to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in to_delete:
                del self._store[k]
            return len(to_delete)

    def invalidate_user(self, user_id: int) -> int:
        """Delete all cache entries for a specific user."""
        return self.invalidate_prefix(f"u:{user_id}:")

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "name": self._name,
                "entries": len(self._store),
                "maxsize": self._maxsize,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(hit_rate, 1),
            }


class DataframeCache:
    """Memory-bounded LRU cache specifically for pandas DataFrames.

    Tracks approximate memory usage and evicts oldest entries
    when the memory budget is exceeded.
    """

    def __init__(self, max_entries: int = 20, max_mb: float = 500.0):
        self._max_entries = max_entries
        self._max_bytes = int(max_mb * 1024 * 1024)
        self._store: OrderedDict[str, Tuple[Any, int]] = OrderedDict()  # key -> (df, bytes)
        self._current_bytes = 0
        self._lock = threading.Lock()

    def _df_bytes(self, df) -> int:
        try:
            return int(df.memory_usage(deep=True).sum())
        except Exception:
            return 0

    def get(self, key: str) -> Any:
        with self._lock:
            if key in self._store:
                df, _ = self._store[key]
                self._store.move_to_end(key)
                return df
            return None

    def set(self, key: str, df) -> None:
        nbytes = self._df_bytes(df)
        with self._lock:
            if key in self._store:
                _, old_bytes = self._store.pop(key)
                self._current_bytes -= old_bytes
            # Evict until we fit
            while (self._current_bytes + nbytes > self._max_bytes or
                   len(self._store) >= self._max_entries) and self._store:
                _, evicted_bytes = self._store.popitem(last=False)
                self._current_bytes -= evicted_bytes
            self._store[key] = (df, nbytes)
            self._current_bytes += nbytes

    def invalidate_user(self, user_id: int) -> int:
        with self._lock:
            to_delete = [k for k in self._store if k.startswith(f"u:{user_id}:")]
            for k in to_delete:
                _, b = self._store.pop(k)
                self._current_bytes -= b
            return len(to_delete)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._current_bytes = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._store),
                "max_entries": self._max_entries,
                "memory_mb": round(self._current_bytes / (1024 * 1024), 1),
                "max_mb": round(self._max_bytes / (1024 * 1024), 1),
            }


def _make_key(user_id: int, dataset_id: int, extra: str = "") -> str:
    """Build a cache key from user_id, dataset_id, and optional extra string."""
    return f"u:{user_id}:d:{dataset_id}:{extra}"


def cached(fn: Optional[Callable] = None, *, cache: TTLCache, key_fn: Callable,
           ttl: Optional[float] = None):
    """Decorator that caches function results in the given TTLCache.

    Usage::

        @cached(cache=dataset_meta_cache, key_fn=lambda u, d: _make_key(u, d, "info"))
        def get_dataset_info(user_id, dataset_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = key_fn(*args, **kwargs)
            result = cache.get(key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            if result is not None:
                cache.set(key, result, ttl=ttl)
            return result
        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


# ── Global Cache Instances ──────────────────────────────────────

# Dashboard KPI data (per-user, 30s TTL)
dashboard_cache = TTLCache(maxsize=128, default_ttl=30.0, name="dashboard")

# Dataset metadata — column info, quality info (per-dataset, 120s TTL)
dataset_meta_cache = TTLCache(maxsize=256, default_ttl=120.0, name="dataset_meta")

# Dataset list (per-user, 15s TTL)
dataset_list_cache = TTLCache(maxsize=128, default_ttl=15.0, name="dataset_list")

# ML dataset info — column analysis (per-dataset, 120s TTL)
ml_info_cache = TTLCache(maxsize=64, default_ttl=120.0, name="ml_info")

# Visualization data — aggregated chart data (per-dataset+params, 60s TTL)
viz_cache = TTLCache(maxsize=128, default_ttl=60.0, name="viz")

# DataFrame in-memory cache (LRU, memory-bounded)
dataframe_cache = DataframeCache(max_entries=20, max_mb=500.0)

# Admin system stats (global, 10s TTL)
system_stats_cache = TTLCache(maxsize=16, default_ttl=10.0, name="system_stats")


def invalidate_user_caches(user_id: int) -> None:
    """Invalidate ALL cache entries for a user. Call on data mutations."""
    for cache in (dashboard_cache, dataset_meta_cache, dataset_list_cache,
                 ml_info_cache, viz_cache, system_stats_cache):
        cache.invalidate_user(user_id)
    dataframe_cache.invalidate_user(user_id)


def invalidate_dataset(user_id: int, dataset_id: int) -> None:
    """Invalidate cache entries for a specific dataset."""
    prefix = f"u:{user_id}:d:{dataset_id}:"
    for cache in (dataset_meta_cache, ml_info_cache, viz_cache):
        cache.invalidate_prefix(prefix)
    dataframe_cache.invalidate_user(user_id)
