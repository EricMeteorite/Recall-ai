"""Recall v7.0 - Backend Factory

Auto-selects and instantiates the appropriate backend implementations
based on available services and environment configuration.

Tier Detection
--------------
+----------+---------------------------------------------------+
| Tier     | Backends                                          |
+==========+===================================================+
| Lite     | SQLite only (default, no external services)       |
| Standard | SQLite + local Qdrant                             |
| Scale    | PostgreSQL + Qdrant + Elasticsearch                |
| Ultra    | PostgreSQL + Qdrant + NebulaGraph + Elasticsearch |
+----------+---------------------------------------------------+

Auto-detect
    Probes each service's health endpoint and selects the highest
    tier whose dependencies are all reachable.

Override
    Set ``RECALL_BACKEND_TIER`` to one of ``lite``, ``standard``,
    ``scale``, or ``ultra`` to force a specific tier.

Health checking
    :meth:`BackendFactory.health_check` tests every active backend and
    returns a summary.  The factory can be asked to auto-degrade if a
    service becomes unavailable (see :meth:`auto_degrade`).
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Dict, Optional

from .interfaces import (
    GraphBackend,
    StorageBackend,
    TextSearchBackend,
    VectorBackend,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier enum
# ---------------------------------------------------------------------------


class BackendTier(str, Enum):
    """Supported backend deployment tiers."""

    LITE = "lite"
    STANDARD = "standard"
    SCALE = "scale"
    ULTRA = "ultra"


# ---------------------------------------------------------------------------
# Service availability probes
# ---------------------------------------------------------------------------


def _is_qdrant_available() -> bool:
    """Return ``True`` if a Qdrant server is reachable."""
    try:
        from .qdrant_vector import QdrantVectorBackend, _QDRANT_AVAILABLE

        if not _QDRANT_AVAILABLE:
            return False
        from qdrant_client import QdrantClient  # type: ignore

        host = os.environ.get("QDRANT_HOST", "localhost")
        port = int(os.environ.get("QDRANT_PORT", "6333"))
        client = QdrantClient(host=host, port=port, timeout=3)
        client.get_collections()
        client.close()
        return True
    except Exception:
        return False


def _is_pg_available() -> bool:
    """Return ``True`` if a PostgreSQL server is reachable."""
    try:
        from .pg_memory import _PG_AVAILABLE

        if not _PG_AVAILABLE:
            return False
        import psycopg2  # type: ignore

        host = os.environ.get("PG_HOST", "localhost")
        port = int(os.environ.get("PG_PORT", "5432"))
        user = os.environ.get("PG_USER", "recall")
        password = os.environ.get("PG_PASSWORD", "")
        database = os.environ.get("PG_DATABASE", "recall")
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password,
            database=database, connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def _is_nebula_available() -> bool:
    """Return ``True`` if a NebulaGraph server is reachable."""
    try:
        from .nebula_graph import _NEBULA_AVAILABLE

        if not _NEBULA_AVAILABLE:
            return False
        from nebula3.gclient.net import ConnectionPool  # type: ignore
        from nebula3.Config import Config as NConfig  # type: ignore

        host = os.environ.get("NEBULA_HOST", "127.0.0.1")
        port = int(os.environ.get("NEBULA_PORT", "9669"))
        cfg = NConfig()
        cfg.max_connection_pool_size = 1
        cfg.timeout = 3000
        pool = ConnectionPool()
        ok = pool.init([(host, port)], cfg)
        pool.close()
        return ok
    except Exception:
        return False


def _is_es_available() -> bool:
    """Return ``True`` if an Elasticsearch cluster is reachable."""
    try:
        from .es_fulltext import _ES_AVAILABLE

        if not _ES_AVAILABLE:
            return False
        from elasticsearch import Elasticsearch  # type: ignore

        host = os.environ.get("ES_HOST", "http://localhost:9200")
        client = Elasticsearch(hosts=[host], request_timeout=3)
        ok = client.ping()
        client.close()
        return ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# BackendFactory
# ---------------------------------------------------------------------------


class BackendFactory:
    """Auto-selects backend implementations based on available services.

    Usage::

        factory = BackendFactory()
        vector = factory.create_vector_backend()
        storage = factory.create_storage_backend()

    Parameters
    ----------
    tier : str or BackendTier or None
        Explicitly set the tier.  Falls back to ``RECALL_BACKEND_TIER``
        env var, then auto-detection.
    vector_dimension : int
        Embedding dimensionality passed to vector backends (default 1024).
    """

    def __init__(
        self,
        tier: str | BackendTier | None = None,
        vector_dimension: int = 1024,
    ) -> None:
        self._vector_dim = vector_dimension

        # Resolve tier
        if tier is not None:
            self._tier = BackendTier(tier if isinstance(tier, str) else tier.value)
        else:
            env = os.environ.get("RECALL_BACKEND_TIER", "").strip().lower()
            if env and env in {t.value for t in BackendTier}:
                self._tier = BackendTier(env)
            else:
                self._tier = self.detect_tier()

        logger.info("BackendFactory initialised  tier=%s", self._tier.value)

        # Cache created backends
        self._vector: Optional[VectorBackend] = None
        self._storage: Optional[StorageBackend] = None
        self._graph: Optional[GraphBackend] = None
        self._text_search: Optional[TextSearchBackend] = None

    # ---- tier detection --------------------------------------------------

    @staticmethod
    def detect_tier() -> BackendTier:
        """Probe available services and return the highest achievable tier.

        The probes are ordered from highest to lowest tier so the first
        fully-satisfied tier wins.
        """
        pg = _is_pg_available()
        qdrant = _is_qdrant_available()
        nebula = _is_nebula_available()
        es = _is_es_available()

        logger.info(
            "Service probes: PG=%s  Qdrant=%s  Nebula=%s  ES=%s",
            pg, qdrant, nebula, es,
        )

        if pg and qdrant and nebula and es:
            return BackendTier.ULTRA
        if pg and qdrant and es:
            return BackendTier.SCALE
        if qdrant:
            return BackendTier.STANDARD
        return BackendTier.LITE

    @property
    def tier(self) -> BackendTier:
        """The resolved deployment tier."""
        return self._tier

    # ---- factory methods -------------------------------------------------

    def create_vector_backend(self, **kwargs) -> VectorBackend:
        """Return a :class:`VectorBackend` appropriate for the current tier.

        - **Lite**: :class:`SQLiteVectorBackend`
        - **Standard / Scale / Ultra**: :class:`QdrantVectorBackend`
        """
        if self._vector is not None:
            return self._vector

        if self._tier in (BackendTier.STANDARD, BackendTier.SCALE, BackendTier.ULTRA):
            try:
                from .qdrant_vector import QdrantVectorBackend

                self._vector = QdrantVectorBackend(
                    dimension=self._vector_dim, **kwargs
                )
                logger.info("Created QdrantVectorBackend for tier %s", self._tier.value)
                return self._vector
            except Exception as exc:
                logger.warning(
                    "QdrantVectorBackend unavailable, falling back to SQLite: %s", exc
                )

        # Fallback: SQLite
        from .sqlite_vector import SQLiteVectorBackend

        self._vector = SQLiteVectorBackend(**kwargs)
        logger.info("Created SQLiteVectorBackend (lite / fallback)")
        return self._vector

    def create_storage_backend(self, **kwargs) -> StorageBackend:
        """Return a :class:`StorageBackend` appropriate for the current tier.

        - **Lite / Standard**: :class:`SQLiteMemoryBackend`
        - **Scale / Ultra**: :class:`PostgreSQLMemoryBackend`
        """
        if self._storage is not None:
            return self._storage

        if self._tier in (BackendTier.SCALE, BackendTier.ULTRA):
            try:
                from .pg_memory import PostgreSQLMemoryBackend

                self._storage = PostgreSQLMemoryBackend(**kwargs)
                logger.info("Created PostgreSQLMemoryBackend for tier %s", self._tier.value)
                return self._storage
            except Exception as exc:
                logger.warning(
                    "PostgreSQLMemoryBackend unavailable, falling back to SQLite: %s", exc
                )

        # Fallback: SQLite
        from .sqlite_memory import SQLiteMemoryBackend

        self._storage = SQLiteMemoryBackend(**kwargs)
        logger.info("Created SQLiteMemoryBackend (lite / fallback)")
        return self._storage

    def create_graph_backend(self, **kwargs) -> GraphBackend:
        """Return a :class:`GraphBackend` appropriate for the current tier.

        - **Ultra**: :class:`NebulaGraphBackend`
        - **All others**: raises ``NotImplementedError`` (no built-in
          graph backend for lower tiers; use the Kuzu backend from
          ``recall.graph`` instead).
        """
        if self._graph is not None:
            return self._graph

        if self._tier == BackendTier.ULTRA:
            try:
                from .nebula_graph import NebulaGraphBackend

                self._graph = NebulaGraphBackend(**kwargs)
                logger.info("Created NebulaGraphBackend for tier ultra")
                return self._graph
            except Exception as exc:
                logger.warning(
                    "NebulaGraphBackend unavailable: %s", exc
                )
                raise RuntimeError(
                    "No graph backend available.  NebulaGraph is required for "
                    "the Ultra tier.  For lower tiers use recall.graph.KuzuGraph."
                ) from exc

        raise NotImplementedError(
            f"No built-in graph backend for tier '{self._tier.value}'.  "
            "Use recall.graph.KuzuGraph for Lite/Standard/Scale tiers."
        )

    def create_text_search_backend(self, **kwargs) -> TextSearchBackend:
        """Return a :class:`TextSearchBackend` appropriate for the current tier.

        - **Lite / Standard**: :class:`SQLiteFTS5Backend`
        - **Scale / Ultra**: :class:`ElasticsearchFulltextBackend`
        """
        if self._text_search is not None:
            return self._text_search

        if self._tier in (BackendTier.SCALE, BackendTier.ULTRA):
            try:
                from .es_fulltext import ElasticsearchFulltextBackend

                self._text_search = ElasticsearchFulltextBackend(**kwargs)
                logger.info("Created ElasticsearchFulltextBackend for tier %s", self._tier.value)
                return self._text_search
            except Exception as exc:
                logger.warning(
                    "ElasticsearchFulltextBackend unavailable, falling back to SQLite FTS5: %s",
                    exc,
                )

        # Fallback: SQLite FTS5
        from .sqlite_fts import SQLiteFTS5Backend

        self._text_search = SQLiteFTS5Backend(**kwargs)
        logger.info("Created SQLiteFTS5Backend (lite / fallback)")
        return self._text_search

    # ---- health check ----------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Test connectivity of all active backends.

        Returns
        -------
        dict
            ``{"tier": ..., "backends": {"vector": True, ...}, "healthy": True}``
        """
        report: Dict[str, Any] = {
            "tier": self._tier.value,
            "backends": {},
            "healthy": True,
        }

        for name, backend in [
            ("vector", self._vector),
            ("storage", self._storage),
            ("graph", self._graph),
            ("text_search", self._text_search),
        ]:
            if backend is None:
                report["backends"][name] = None  # not instantiated
                continue
            checker = getattr(backend, "health_check", None)
            if callable(checker):
                try:
                    ok = checker()
                except Exception:
                    ok = False
                report["backends"][name] = ok
                if not ok:
                    report["healthy"] = False
            else:
                report["backends"][name] = "no_health_check"

        return report

    def auto_degrade(self) -> BackendTier:
        """Re-probe services and downgrade tier if any backend is unhealthy.

        This resets the cached backends so the next ``create_*`` call
        will rebuild them at the appropriate tier.

        Returns
        -------
        BackendTier
            The (possibly lowered) tier after re-probing.
        """
        old_tier = self._tier
        self._tier = self.detect_tier()

        if self._tier != old_tier:
            logger.warning(
                "Auto-degraded from tier '%s' to '%s' due to service unavailability.",
                old_tier.value,
                self._tier.value,
            )
            # Reset cached backends
            self._close_all()
            self._vector = None
            self._storage = None
            self._graph = None
            self._text_search = None

        return self._tier

    # ---- lifecycle -------------------------------------------------------

    def _close_all(self) -> None:
        """Close all active backends."""
        for backend in (self._vector, self._storage, self._graph, self._text_search):
            closer = getattr(backend, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass

    def close(self) -> None:
        """Close all active backends and release resources."""
        self._close_all()
        self._vector = None
        self._storage = None
        self._graph = None
        self._text_search = None
        logger.info("BackendFactory closed all backends.")

    def __repr__(self) -> str:
        return f"<BackendFactory tier={self._tier.value}>"
