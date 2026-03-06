"""Recall v7.0 - Cache Layer

Multi-tier caching:
- L1: In-process LRU (immediate)
- L2: Redis (shared across processes, optional)
"""

from .redis_cache import RecallCache, cacheable, get_cache, CacheCategory

__all__ = [
    'RecallCache',
    'cacheable',
    'get_cache',
    'CacheCategory',
]
