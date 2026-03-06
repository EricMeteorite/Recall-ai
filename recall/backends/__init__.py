"""Recall v7.0 - Backend Abstraction Layer (BAL)

Defines abstract interfaces for all backend components, enabling
pluggable storage, indexing, graph, and embedding implementations.
"""

from .interfaces import (
    SearchResult,
    StorageScope,
    VectorBackend,
    TextSearchBackend,
    KeywordBackend,
    GraphBackend,
    StorageBackend,
    TemporalBackend,
    EpisodeBackend,
    EmbeddingService,
    TenantRouter,
)

# Concrete SQLite-based backends
from .sqlite_memory import SQLiteMemoryBackend
from .sqlite_fts import SQLiteFTS5Backend
from .sqlite_vector import SQLiteVectorBackend

# Distributed backends (optional dependencies — import errors are deferred)
from .qdrant_vector import QdrantVectorBackend
from .pg_memory import PostgreSQLMemoryBackend
from .nebula_graph import NebulaGraphBackend
from .es_fulltext import ElasticsearchFulltextBackend

# Factory
from .factory import BackendFactory, BackendTier

__all__ = [
    # Data classes
    "SearchResult",
    "StorageScope",
    # 7 Backend interfaces
    "VectorBackend",
    "TextSearchBackend",
    "KeywordBackend",
    "GraphBackend",
    "StorageBackend",
    "TemporalBackend",
    "EpisodeBackend",
    # 2 Service interfaces
    "EmbeddingService",
    "TenantRouter",
    # Concrete SQLite backends
    "SQLiteMemoryBackend",
    "SQLiteFTS5Backend",
    "SQLiteVectorBackend",
    # Distributed backends
    "QdrantVectorBackend",
    "PostgreSQLMemoryBackend",
    "NebulaGraphBackend",
    "ElasticsearchFulltextBackend",
    # Factory
    "BackendFactory",
    "BackendTier",
]
