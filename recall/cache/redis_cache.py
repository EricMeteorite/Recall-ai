"""
Recall v7.0 - Redis Cache Layer
Hot data caching for frequently accessed data.
Requires: redis (optional dependency)

Multi-tier caching:
1. L1: In-process LRU cache (immediate, ~64MB default)
2. L2: Redis cache (shared across processes, ~256MB default)
3. Miss -> backend query -> populate both caches

Cache categories:
- search_results: cache recent search results (TTL 5min)
- entity_data: cache frequently accessed entities (TTL 30min)
- embeddings: cache computed embeddings (TTL 1h)
- context: cache built contexts (TTL 2min)

Invalidation:
- On memory add/update/delete -> invalidate related search results + entity data
- On consolidation -> invalidate all entity summaries
- TTL-based expiry for automatic cleanup

Configuration:
- REDIS_URL (default redis://localhost:6379/0)
- RECALL_CACHE_MAX_MEMORY (default 256MB)
- RECALL_CACHE_ENABLED (default true)
- RECALL_CACHE_TTL_SEARCH (default 300)
- RECALL_CACHE_TTL_ENTITY (default 1800)
- RECALL_CACHE_TTL_EMBEDDING (default 3600)
- RECALL_CACHE_TTL_CONTEXT (default 120)
- RECALL_CACHE_L1_MAX_SIZE (default 4096 entries)
"""

from __future__ import annotations

import os
import time
import json
import hashlib
import logging
import threading
import functools
from collections import OrderedDict
from enum import Enum
from typing import Any, Dict, Optional, Callable, Tuple
from dataclasses import dataclass, field

# Redis: optional dependency
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


# ==================== Cache Category ====================

class CacheCategory(str, Enum):
    """Cache categories with default TTLs (in seconds)."""
    SEARCH_RESULTS = "search"
    ENTITY_DATA = "entity"
    EMBEDDINGS = "embedding"
    CONTEXT = "context"


_DEFAULT_TTLS: Dict[CacheCategory, int] = {
    CacheCategory.SEARCH_RESULTS: 300,    # 5 min
    CacheCategory.ENTITY_DATA: 1800,      # 30 min
    CacheCategory.EMBEDDINGS: 3600,       # 1 hour
    CacheCategory.CONTEXT: 120,           # 2 min
}


# ==================== Cache Stats ====================

@dataclass
class CacheStats:
    """Cache hit/miss statistics."""
    l1_hits: int = 0
    l1_misses: int = 0
    l2_hits: int = 0
    l2_misses: int = 0
    invalidations: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_l1_hit(self) -> None:
        with self._lock:
            self.l1_hits += 1

    def record_l1_miss(self) -> None:
        with self._lock:
            self.l1_misses += 1

    def record_l2_hit(self) -> None:
        with self._lock:
            self.l2_hits += 1

    def record_l2_miss(self) -> None:
        with self._lock:
            self.l2_misses += 1

    def record_invalidation(self) -> None:
        with self._lock:
            self.invalidations += 1

    def record_error(self) -> None:
        with self._lock:
            self.errors += 1

    @property
    def total_hits(self) -> int:
        return self.l1_hits + self.l2_hits

    @property
    def total_misses(self) -> int:
        # An L1 miss that hits L2 counts as a "total hit" — only full misses count
        return self.l2_misses

    @property
    def total_requests(self) -> int:
        return self.l1_hits + self.l1_misses

    @property
    def hit_rate(self) -> float:
        total = self.total_requests
        if total == 0:
            return 0.0
        return self.total_hits / total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "l1_hits": self.l1_hits,
            "l1_misses": self.l1_misses,
            "l2_hits": self.l2_hits,
            "l2_misses": self.l2_misses,
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "hit_rate": round(self.hit_rate, 4),
            "invalidations": self.invalidations,
            "errors": self.errors,
        }


# ==================== L1: In-process LRU Cache ====================

class L1Cache:
    """Thread-safe LRU cache with TTL support (in-process).

    Uses an OrderedDict to maintain LRU ordering.
    Each entry stores (value, expire_time).
    """

    def __init__(self, max_size: int = 4096):
        self._max_size = max_size
        self._data: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Tuple[bool, Any]:
        """Get value. Returns (found, value)."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False, None
            value, expire_at = entry
            if expire_at > 0 and time.time() > expire_at:
                # Expired — remove
                del self._data[key]
                return False, None
            # Move to end (most recently used)
            self._data.move_to_end(key)
            return True, value

    def put(self, key: str, value: Any, ttl: int = 0) -> None:
        """Store value with optional TTL (seconds). ttl=0 means no expiry."""
        expire_at = (time.time() + ttl) if ttl > 0 else 0.0
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (value, expire_at)
            # Evict LRU if over capacity
            while len(self._data) > self._max_size:
                self._data.popitem(last=False)

    def delete(self, key: str) -> bool:
        """Delete a specific key. Returns True if found."""
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def delete_pattern(self, prefix: str) -> int:
        """Delete all keys starting with prefix. Returns count deleted."""
        with self._lock:
            keys_to_delete = [k for k in self._data if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._data[k]
            return len(keys_to_delete)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    @property
    def size(self) -> int:
        return len(self._data)

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._data.items() if 0 < exp < now]
            for k in expired:
                del self._data[k]
            return len(expired)


# ==================== L2: Redis Cache ====================

class L2Cache:
    """Redis-based cache layer (optional).

    If Redis is unavailable, all operations are no-ops.
    Uses key prefix ``recall:`` for namespace isolation.
    """

    KEY_PREFIX = "recall:"

    def __init__(self, redis_url: str = "redis://localhost:6379/0", max_memory: str = "256mb"):
        self._available = False
        self._client = None  # type: Any
        self._max_memory = max_memory

        if not REDIS_AVAILABLE:
            logger.info("[Cache] Redis 库未安装, L2 缓存已禁用")
            return

        try:
            self._client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=2,
                retry_on_timeout=True,
            )
            # Test connectivity
            self._client.ping()
            self._available = True
            # Set max memory policy
            try:
                self._client.config_set("maxmemory", max_memory)
                self._client.config_set("maxmemory-policy", "allkeys-lru")
            except Exception:
                pass  # Not always allowed (e.g. Redis Cloud)
            logger.info(f"[Cache] Redis L2 缓存已连接 ({redis_url})")
        except Exception as e:
            logger.warning(f"[Cache] Redis 连接失败, L2 缓存已禁用: {e}")
            self._client = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def _make_key(self, key: str) -> str:
        return f"{self.KEY_PREFIX}{key}"

    def get(self, key: str) -> Tuple[bool, Any]:
        """Get value from Redis. Returns (found, value)."""
        if not self._available:
            return False, None
        try:
            raw = self._client.get(self._make_key(key))
            if raw is None:
                return False, None
            return True, json.loads(raw)
        except Exception as e:
            logger.debug(f"[Cache] Redis GET 失败: {e}")
            return False, None

    def put(self, key: str, value: Any, ttl: int = 0) -> bool:
        """Store value in Redis with optional TTL."""
        if not self._available:
            return False
        try:
            serialized = json.dumps(value, ensure_ascii=False, default=str)
            rkey = self._make_key(key)
            if ttl > 0:
                self._client.setex(rkey, ttl, serialized)
            else:
                self._client.set(rkey, serialized)
            return True
        except Exception as e:
            logger.debug(f"[Cache] Redis SET 失败: {e}")
            return False

    def delete(self, key: str) -> bool:
        if not self._available:
            return False
        try:
            return self._client.delete(self._make_key(key)) > 0
        except Exception:
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching a glob pattern. Returns count deleted."""
        if not self._available:
            return 0
        try:
            full_pattern = self._make_key(pattern + "*")
            keys = list(self._client.scan_iter(match=full_pattern, count=500))
            if keys:
                return self._client.delete(*keys)
            return 0
        except Exception:
            return 0

    def clear(self) -> None:
        """Clear all recall: keys."""
        if not self._available:
            return
        try:
            keys = list(self._client.scan_iter(match=f"{self.KEY_PREFIX}*", count=1000))
            if keys:
                self._client.delete(*keys)
        except Exception:
            pass

    def info(self) -> Dict[str, Any]:
        """Return Redis connection info."""
        if not self._available:
            return {"available": False}
        try:
            info = self._client.info(section="memory")
            return {
                "available": True,
                "used_memory_human": info.get("used_memory_human", "?"),
                "maxmemory_human": info.get("maxmemory_human", "?"),
                "connected_clients": self._client.info("clients").get("connected_clients", 0),
            }
        except Exception:
            return {"available": True, "error": "info unavailable"}


# ==================== RecallCache (Unified) ====================

class RecallCache:
    """
    Multi-tier caching for Recall:
    1. L1: In-process LRU (fast, per-process)
    2. L2: Redis (shared, optional)
    3. Miss -> backend query -> populate both caches

    Thread-safe.  All external imports are in try/except.
    """

    def __init__(
        self,
        enabled: bool = True,
        redis_url: str = "redis://localhost:6379/0",
        max_memory: str = "256mb",
        l1_max_size: int = 4096,
        ttl_overrides: Optional[Dict[CacheCategory, int]] = None,
    ):
        self.enabled = enabled
        self.stats = CacheStats()

        # TTLs per category
        self._ttls: Dict[CacheCategory, int] = dict(_DEFAULT_TTLS)
        if ttl_overrides:
            self._ttls.update(ttl_overrides)

        # L1 — always available
        self._l1 = L1Cache(max_size=l1_max_size)

        # L2 — optional Redis
        self._l2: Optional[L2Cache] = None
        if enabled:
            self._l2 = L2Cache(redis_url=redis_url, max_memory=max_memory)

        # Background cleanup thread for L1 expired entries
        self._cleanup_running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        if enabled:
            self._cleanup_thread.start()

        logger.info(
            f"[Cache] RecallCache 已初始化 (enabled={enabled}, "
            f"l1_max={l1_max_size}, redis={'OK' if self._l2 and self._l2.available else 'N/A'})"
        )

    # ---- Key generation ----

    @staticmethod
    def make_key(category: CacheCategory, *parts: str) -> str:
        """Build a cache key: ``{category}:{hash(parts)}``"""
        raw = "|".join(str(p) for p in parts)
        digest = hashlib.md5(raw.encode()).hexdigest()[:16]
        return f"{category.value}:{digest}"

    @staticmethod
    def make_key_raw(category: CacheCategory, identifier: str) -> str:
        """Build a cache key with raw identifier (no hashing)."""
        return f"{category.value}:{identifier}"

    # ---- Core operations ----

    def get(self, key: str) -> Tuple[bool, Any]:
        """Read-through: L1 -> L2 -> miss."""
        if not self.enabled:
            return False, None

        # L1
        found, value = self._l1.get(key)
        if found:
            self.stats.record_l1_hit()
            return True, value
        self.stats.record_l1_miss()

        # L2
        if self._l2 and self._l2.available:
            found, value = self._l2.get(key)
            if found:
                self.stats.record_l2_hit()
                # Promote to L1
                cat = self._category_from_key(key)
                ttl = self._ttls.get(cat, 300) if cat else 300
                self._l1.put(key, value, ttl=ttl)
                return True, value
            self.stats.record_l2_miss()
        else:
            self.stats.record_l2_miss()

        return False, None

    def put(self, key: str, value: Any, category: Optional[CacheCategory] = None, ttl: int = 0) -> None:
        """Write-through: put into both L1 and L2."""
        if not self.enabled:
            return

        if ttl <= 0 and category:
            ttl = self._ttls.get(category, 300)
        elif ttl <= 0:
            cat = self._category_from_key(key)
            ttl = self._ttls.get(cat, 300) if cat else 300

        self._l1.put(key, value, ttl=ttl)

        if self._l2 and self._l2.available:
            try:
                self._l2.put(key, value, ttl=ttl)
            except Exception:
                self.stats.record_error()

    def delete(self, key: str) -> None:
        """Delete from both layers."""
        self._l1.delete(key)
        if self._l2 and self._l2.available:
            self._l2.delete(key)

    # ---- Invalidation hooks ----

    def invalidate_search(self) -> None:
        """Invalidate all cached search results."""
        prefix = f"{CacheCategory.SEARCH_RESULTS.value}:"
        count = self._l1.delete_pattern(prefix)
        if self._l2 and self._l2.available:
            count += self._l2.delete_pattern(prefix)
        self.stats.record_invalidation()
        logger.debug(f"[Cache] 搜索缓存已失效 (deleted={count})")

    def invalidate_entity(self, entity_name: Optional[str] = None) -> None:
        """Invalidate entity data cache (specific entity or all)."""
        if entity_name:
            prefix = f"{CacheCategory.ENTITY_DATA.value}:{hashlib.md5(entity_name.encode()).hexdigest()[:16]}"
            self._l1.delete(prefix)
            if self._l2 and self._l2.available:
                self._l2.delete(prefix)
        else:
            prefix = f"{CacheCategory.ENTITY_DATA.value}:"
            self._l1.delete_pattern(prefix)
            if self._l2 and self._l2.available:
                self._l2.delete_pattern(prefix)
        self.stats.record_invalidation()

    def invalidate_context(self) -> None:
        """Invalidate all cached contexts."""
        prefix = f"{CacheCategory.CONTEXT.value}:"
        self._l1.delete_pattern(prefix)
        if self._l2 and self._l2.available:
            self._l2.delete_pattern(prefix)
        self.stats.record_invalidation()

    def invalidate_on_write(self, entity_names: Optional[list] = None) -> None:
        """Called after memory add/update/delete.

        Invalidates search results and optionally specific entity caches.
        """
        self.invalidate_search()
        self.invalidate_context()
        if entity_names:
            for name in entity_names:
                self.invalidate_entity(name)

    def invalidate_on_consolidation(self) -> None:
        """Called after consolidation — invalidate all entity summaries."""
        self.invalidate_entity()  # clear all entity caches
        self.invalidate_search()
        self.invalidate_context()

    def invalidate_all(self) -> None:
        """Nuclear option — clear everything."""
        self._l1.clear()
        if self._l2 and self._l2.available:
            self._l2.clear()
        self.stats.record_invalidation()
        logger.info("[Cache] 全部缓存已清除")

    # ---- Info / stats ----

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        info = self.stats.to_dict()
        info["l1_size"] = self._l1.size
        info["l2_available"] = bool(self._l2 and self._l2.available)
        if self._l2 and self._l2.available:
            info["l2_info"] = self._l2.info()
        info["enabled"] = self.enabled
        info["ttls"] = {cat.value: ttl for cat, ttl in self._ttls.items()}
        return info

    # ---- Lifecycle ----

    def close(self) -> None:
        """Shutdown cleanup thread."""
        self._cleanup_running = False
        logger.info("[Cache] RecallCache 已关闭")

    # ---- Internal ----

    def _category_from_key(self, key: str) -> Optional[CacheCategory]:
        """Extract category from key prefix."""
        for cat in CacheCategory:
            if key.startswith(cat.value + ":"):
                return cat
        return None

    def _cleanup_loop(self) -> None:
        """Background thread: periodically clean expired L1 entries."""
        while self._cleanup_running:
            try:
                time.sleep(60)  # every 60s
                removed = self._l1.cleanup_expired()
                if removed > 0:
                    logger.debug(f"[Cache] L1 过期清理: {removed} entries")
            except Exception:
                pass  # ignore errors in cleanup


# ==================== @cacheable decorator ====================

def cacheable(category: CacheCategory, ttl: int = 0, key_func: Optional[Callable] = None):
    """Decorator for caching function results through RecallCache.

    Usage::

        @cacheable(CacheCategory.SEARCH_RESULTS, ttl=300)
        def search_memories(query: str, user_id: str, top_k: int = 10):
            ...

    The cache key is built from the function name + all arguments.
    If ``key_func`` is provided, it's called with (*args, **kwargs) and should
    return a tuple of strings used as key parts.

    The function must be called with a ``_cache`` keyword argument containing
    a RecallCache instance, OR register via ``get_cache()``.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Retrieve cache instance
            cache: Optional[RecallCache] = kwargs.pop("_cache", None) or get_cache()
            if cache is None or not cache.enabled:
                return func(*args, **kwargs)

            # Build key
            if key_func:
                parts = key_func(*args, **kwargs)
            else:
                parts = (func.__qualname__,) + tuple(str(a) for a in args) + tuple(
                    f"{k}={v}" for k, v in sorted(kwargs.items())
                )
            cache_key = RecallCache.make_key(category, *parts)

            # Check cache
            found, value = cache.get(cache_key)
            if found:
                return value

            # Miss — call function
            result = func(*args, **kwargs)

            # Store result
            effective_ttl = ttl if ttl > 0 else cache._ttls.get(category, 300)
            cache.put(cache_key, result, category=category, ttl=effective_ttl)

            return result

        return wrapper

    return decorator


# ==================== Global singleton ====================

_global_cache: Optional[RecallCache] = None
_cache_lock = threading.Lock()


def get_cache() -> Optional[RecallCache]:
    """Get or create the global RecallCache instance (lazy singleton)."""
    global _global_cache
    if _global_cache is not None:
        return _global_cache

    with _cache_lock:
        if _global_cache is not None:
            return _global_cache

        enabled = os.environ.get("RECALL_CACHE_ENABLED", "true").lower() in ("1", "true", "yes")
        if not enabled:
            logger.info("[Cache] 缓存已通过 RECALL_CACHE_ENABLED 禁用")
            return None

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        max_memory = os.environ.get("RECALL_CACHE_MAX_MEMORY", "256mb")
        l1_max = int(os.environ.get("RECALL_CACHE_L1_MAX_SIZE", "4096"))

        ttl_overrides: Dict[CacheCategory, int] = {}
        env_ttl_search = os.environ.get("RECALL_CACHE_TTL_SEARCH")
        if env_ttl_search:
            ttl_overrides[CacheCategory.SEARCH_RESULTS] = int(env_ttl_search)
        env_ttl_entity = os.environ.get("RECALL_CACHE_TTL_ENTITY")
        if env_ttl_entity:
            ttl_overrides[CacheCategory.ENTITY_DATA] = int(env_ttl_entity)
        env_ttl_embed = os.environ.get("RECALL_CACHE_TTL_EMBEDDING")
        if env_ttl_embed:
            ttl_overrides[CacheCategory.EMBEDDINGS] = int(env_ttl_embed)
        env_ttl_ctx = os.environ.get("RECALL_CACHE_TTL_CONTEXT")
        if env_ttl_ctx:
            ttl_overrides[CacheCategory.CONTEXT] = int(env_ttl_ctx)

        _global_cache = RecallCache(
            enabled=True,
            redis_url=redis_url,
            max_memory=max_memory,
            l1_max_size=l1_max,
            ttl_overrides=ttl_overrides if ttl_overrides else None,
        )
        return _global_cache


def reset_cache() -> None:
    """Reset the global cache singleton (useful for tests)."""
    global _global_cache
    if _global_cache is not None:
        _global_cache.close()
        _global_cache = None
