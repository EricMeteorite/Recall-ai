"""Recall v7.0 - Qdrant Vector Backend

Implements :class:`VectorBackend` ABC for distributed vector search
using a Qdrant server.  Suitable for large-scale corpora that exceed
what the brute-force SQLite backend can handle efficiently.

Requires
--------
``qdrant-client`` (optional dependency).  The module imports cleanly
even when the package is absent; an ``ImportError`` is raised only at
construction time.

Configuration (environment variables)
--------------------------------------
QDRANT_HOST          Qdrant server hostname (default ``localhost``)
QDRANT_PORT          gRPC / HTTP port (default ``6333``)
QDRANT_API_KEY       Optional API key for Qdrant Cloud
QDRANT_HTTPS         Use HTTPS transport (``1`` / ``true``)
QDRANT_COLLECTION    Collection name (default ``recall_vectors``)
QDRANT_TIMEOUT       Request timeout in seconds (default ``30``)

Design notes
------------
* **Auto-create collection** — on first use the backend checks whether
  the configured collection exists and creates it with the correct
  dimensionality if needed.
* **Auto-retry** — transient connection errors are retried with
  exponential back-off (up to 3 attempts).
* **Graceful degradation** — clear ``RuntimeError`` messages when the
  Qdrant server is unreachable.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .interfaces import SearchResult, VectorBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional qdrant-client import
# ---------------------------------------------------------------------------

_QDRANT_AVAILABLE: bool = False

try:
    from qdrant_client import QdrantClient  # type: ignore
    from qdrant_client.http import models as qmodels  # type: ignore
    from qdrant_client.http.exceptions import (  # type: ignore
        ResponseHandlingException,
        UnexpectedResponse,
    )

    _QDRANT_AVAILABLE = True
except ImportError:
    QdrantClient = None  # type: ignore
    qmodels = None  # type: ignore
    ResponseHandlingException = Exception  # type: ignore
    UnexpectedResponse = Exception  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_COLLECTION = "recall_vectors"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5  # seconds
_BATCH_SIZE = 256

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean from an environment variable."""
    val = os.environ.get(key, "").strip().lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


def _retry(func, *args, max_retries: int = _MAX_RETRIES, **kwargs):
    """Call *func* with exponential back-off on connection errors."""
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, OSError, ResponseHandlingException) as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Qdrant request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt,
                    max_retries,
                    delay,
                    exc,
                )
                time.sleep(delay)
    raise RuntimeError(
        f"Qdrant request failed after {max_retries} attempts: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# QdrantVectorBackend
# ---------------------------------------------------------------------------


class QdrantVectorBackend(VectorBackend):
    """Distributed vector search backed by a Qdrant server.

    Parameters
    ----------
    host : str or None
        Qdrant server hostname.  Falls back to ``QDRANT_HOST`` env var
        or ``"localhost"``.
    port : int or None
        Qdrant server port.  Falls back to ``QDRANT_PORT`` or ``6333``.
    api_key : str or None
        Optional API key.  Falls back to ``QDRANT_API_KEY``.
    https : bool or None
        Whether to use HTTPS.  Falls back to ``QDRANT_HTTPS``.
    collection : str or None
        Collection name.  Falls back to ``QDRANT_COLLECTION`` or
        ``"recall_vectors"``.
    dimension : int
        Expected vector dimensionality.  Used when auto-creating the
        collection.
    timeout : int or None
        Request timeout in seconds.  Falls back to ``QDRANT_TIMEOUT``
        or ``30``.

    Raises
    ------
    ImportError
        If ``qdrant-client`` is not installed.
    RuntimeError
        If the Qdrant server is unreachable.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        api_key: str | None = None,
        https: bool | None = None,
        collection: str | None = None,
        dimension: int = 1024,
        timeout: int | None = None,
    ) -> None:
        if not _QDRANT_AVAILABLE:
            raise ImportError(
                "qdrant-client is required for QdrantVectorBackend. "
                "Install it with:  pip install qdrant-client"
            )

        self._host = host or os.environ.get("QDRANT_HOST", "localhost")
        self._port = port or int(os.environ.get("QDRANT_PORT", "6333"))
        self._api_key = api_key or os.environ.get("QDRANT_API_KEY") or None
        self._https = https if https is not None else _env_bool("QDRANT_HTTPS")
        self._collection = (
            collection or os.environ.get("QDRANT_COLLECTION", _DEFAULT_COLLECTION)
        )
        self._dimension = dimension
        self._timeout = timeout or int(os.environ.get("QDRANT_TIMEOUT", "30"))

        # Build client
        try:
            self._client = QdrantClient(
                host=self._host,
                port=self._port,
                api_key=self._api_key,
                https=self._https,
                timeout=self._timeout,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create Qdrant client ({self._host}:{self._port}): {exc}"
            ) from exc

        # Ensure collection exists
        self._ensure_collection()
        logger.info(
            "QdrantVectorBackend initialised  host=%s:%s  collection=%s  dim=%d",
            self._host,
            self._port,
            self._collection,
            self._dimension,
        )

    # ---- collection management -------------------------------------------

    def _ensure_collection(self) -> None:
        """Create the collection if it does not already exist."""
        try:
            collections = _retry(self._client.get_collections).collections
            names = [c.name for c in collections]
            if self._collection not in names:
                logger.info("Creating Qdrant collection '%s' (dim=%d)", self._collection, self._dimension)
                _retry(
                    self._client.create_collection,
                    collection_name=self._collection,
                    vectors_config=qmodels.VectorParams(
                        size=self._dimension,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to ensure Qdrant collection '{self._collection}': {exc}"
            ) from exc

    # ---- VectorBackend ABC -----------------------------------------------

    def add(self, id: str, vector: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        """Insert or update a single vector with optional metadata payload."""
        point = qmodels.PointStruct(
            id=self._to_point_id(id),
            vector=vector,
            payload=self._build_payload(id, metadata),
        )
        _retry(
            self._client.upsert,
            collection_name=self._collection,
            points=[point],
            wait=True,
        )

    def search(
        self,
        query_vector: List[float],
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Find nearest neighbours using Qdrant's HNSW index."""
        qdrant_filter = self._build_filter(filters) if filters else None

        hits = _retry(
            self._client.search,
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        results: List[SearchResult] = []
        for hit in hits:
            payload = hit.payload or {}
            original_id = payload.pop("_recall_id", str(hit.id))
            results.append(
                SearchResult(
                    id=original_id,
                    score=hit.score,
                    metadata=payload,
                )
            )
        return results

    def delete(self, id: str) -> bool:
        """Remove a vector by its Recall id."""
        try:
            _retry(
                self._client.delete,
                collection_name=self._collection,
                points_selector=qmodels.PointIdsList(
                    points=[self._to_point_id(id)],
                ),
                wait=True,
            )
            return True
        except Exception:
            logger.warning("Failed to delete point %s", id, exc_info=True)
            return False

    def count(self) -> int:
        """Return the total number of vectors in the collection."""
        info = _retry(
            self._client.get_collection,
            collection_name=self._collection,
        )
        return info.points_count or 0

    def rebuild(self) -> None:
        """Recreate the collection (drops all data, re-creates with same config)."""
        logger.warning("Rebuilding Qdrant collection '%s' — all data will be lost!", self._collection)
        try:
            _retry(self._client.delete_collection, collection_name=self._collection)
        except Exception:
            pass  # collection may not exist
        self._ensure_collection()
        logger.info("Qdrant collection '%s' rebuilt successfully.", self._collection)

    # ---- batch operations ------------------------------------------------

    def batch_add(
        self,
        items: Sequence[Dict[str, Any]],
        batch_size: int = _BATCH_SIZE,
    ) -> int:
        """Bulk-insert vectors.

        Each item in *items* must have keys ``id`` (str), ``vector``
        (List[float]), and optionally ``metadata`` (dict).

        Parameters
        ----------
        items
            Iterable of dicts with ``id``, ``vector``, ``metadata``.
        batch_size
            Number of points per upsert call.

        Returns
        -------
        int
            Total number of points inserted.
        """
        total = 0
        batch: List = []

        for item in items:
            point = qmodels.PointStruct(
                id=self._to_point_id(item["id"]),
                vector=item["vector"],
                payload=self._build_payload(item["id"], item.get("metadata")),
            )
            batch.append(point)

            if len(batch) >= batch_size:
                _retry(
                    self._client.upsert,
                    collection_name=self._collection,
                    points=batch,
                    wait=True,
                )
                total += len(batch)
                batch = []

        if batch:
            _retry(
                self._client.upsert,
                collection_name=self._collection,
                points=batch,
                wait=True,
            )
            total += len(batch)

        logger.info("Batch-added %d vectors to Qdrant.", total)
        return total

    # ---- filter helpers --------------------------------------------------

    def _build_filter(self, filters: Dict[str, Any]) -> "qmodels.Filter":
        """Translate a simple key-value dict into a Qdrant filter.

        Supports:
        * Exact match:  ``{"namespace": "default"}``
        * List (any-of): ``{"source": ["user", "system"]}``
        """
        must: List = []
        for key, value in filters.items():
            if isinstance(value, list):
                must.append(
                    qmodels.FieldCondition(
                        key=key,
                        match=qmodels.MatchAny(any=value),
                    )
                )
            else:
                must.append(
                    qmodels.FieldCondition(
                        key=key,
                        match=qmodels.MatchValue(value=value),
                    )
                )
        return qmodels.Filter(must=must)

    # ---- id helpers ------------------------------------------------------

    @staticmethod
    def _to_point_id(recall_id: str) -> str:
        """Convert a Recall string id to a Qdrant-compatible point id.

        Qdrant accepts UUIDs or unsigned ints.  We use UUID-5 derived
        from the Recall id to ensure deterministic, collision-free
        mapping.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, recall_id))

    @staticmethod
    def _build_payload(
        recall_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Assemble the Qdrant payload, injecting ``_recall_id``."""
        payload: Dict[str, Any] = dict(metadata) if metadata else {}
        payload["_recall_id"] = recall_id
        return payload

    # ---- health ----------------------------------------------------------

    def health_check(self) -> bool:
        """Return ``True`` if the Qdrant server is reachable."""
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close the Qdrant client connection."""
        try:
            self._client.close()
        except Exception:
            pass
