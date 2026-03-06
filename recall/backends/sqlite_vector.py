"""Recall v7.0 – SQLite Vector Storage Backend

Stores dense embedding vectors as BLOBs inside a regular SQLite table.
Search is brute-force cosine similarity over all stored vectors using
NumPy – suitable for small-to-medium corpora (< 50 k vectors).  For
larger datasets switch to the existing ``VectorIndexIVF`` or the
upcoming Qdrant backend (Recall 7.6).

The module can share the same database file as
:class:`~recall.backends.sqlite_memory.SQLiteMemoryBackend` and
:class:`~recall.backends.sqlite_fts.SQLiteFTS5Backend`.

Design notes
------------
* **Thread safety** – ``RLock`` on every public method.
* **Connection-per-thread** – ``threading.local()`` pool.
* **NumPy dependency** – required for cosine-similarity computation.
  If NumPy is unavailable the module still imports but raises at
  construction time.
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .interfaces import SearchResult, VectorBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional numpy import
# ---------------------------------------------------------------------------

_NP_AVAILABLE: bool = False
try:
    import numpy as np  # type: ignore

    _NP_AVAILABLE = True
except ImportError:
    np = None  # type: ignore

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_VECTOR_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS vectors (
    memory_id  TEXT PRIMARY KEY,
    vector     BLOB NOT NULL,
    dimension  INTEGER NOT NULL,
    namespace  TEXT NOT NULL DEFAULT 'default',
    created_at REAL
);

CREATE INDEX IF NOT EXISTS idx_vectors_ns ON vectors(namespace);
"""

# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _vec_to_blob(vec: Sequence[float]) -> bytes:
    """Pack a float vector into a compact binary BLOB (little-endian float32)."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _blob_to_vec(blob: bytes, dim: int) -> "np.ndarray":
    """Unpack a BLOB back into a NumPy float32 array."""
    return np.frombuffer(blob, dtype=np.float32, count=dim).copy()


# ---------------------------------------------------------------------------
# SQLiteVectorBackend
# ---------------------------------------------------------------------------


class SQLiteVectorBackend(VectorBackend):
    """Brute-force cosine-similarity vector search backed by SQLite BLOBs.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.
    default_namespace : str
        Namespace used when not explicitly provided.

    Raises
    ------
    ImportError
        If NumPy is not installed.
    """

    _LARGE_THRESHOLD = 50_000
    """When the number of stored vectors exceeds this threshold a
    warning is emitted suggesting migration to an IVF or ANN index."""

    def __init__(
        self,
        db_path: str = "recall_data/data/memories.db",
        default_namespace: str = "default",
    ) -> None:
        if not _NP_AVAILABLE:
            raise ImportError(
                "numpy is required for SQLiteVectorBackend.  "
                "Install it with:  pip install numpy"
            )

        self._db_path = str(db_path)
        self._default_ns = default_namespace
        self._lock = threading.RLock()
        self._local = threading.local()

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_schema()
        logger.info("SQLiteVectorBackend initialised  db=%s", self._db_path)

    # ---- connection management -------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return this thread's ``sqlite3.Connection``."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_VECTOR_SCHEMA_SQL)
        conn.commit()

    # ---- VectorBackend ABC -----------------------------------------------

    def add(
        self,
        id: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or replace a vector.

        Parameters
        ----------
        id : str
            Memory identifier.
        vector : list of float
            Dense embedding vector.
        metadata : dict, optional
            Recognised key: ``namespace``.
        """
        metadata = metadata or {}
        ns = metadata.get("namespace", self._default_ns)
        blob = _vec_to_blob(vector)
        dim = len(vector)
        now = time.time()

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO vectors "
                    "(memory_id, vector, dimension, namespace, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (id, blob, dim, ns, now),
                )
                conn.commit()
                logger.debug("Vector stored  id=%s  dim=%d", id, dim)

                # Emit a warning if the table is getting large.
                total = self._count_unlocked(conn)
                if total == self._LARGE_THRESHOLD:
                    logger.warning(
                        "Vector table has reached %d entries – consider "
                        "migrating to VectorIndexIVF or Qdrant for better "
                        "search performance.",
                        total,
                    )
            except Exception:
                conn.rollback()
                raise

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Brute-force cosine-similarity search.

        Parameters
        ----------
        query_vector : list of float
            The query embedding.
        top_k : int
            Maximum results.
        filters : dict, optional
            Supported keys: ``namespace`` (str), ``global`` (bool).

        Returns
        -------
        list of SearchResult
            Sorted descending by cosine similarity.
        """
        filters = filters or {}
        ns: Optional[str] = filters.get("namespace")
        global_search: bool = filters.get("global", False)

        q = np.asarray(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        q = q / q_norm

        with self._lock:
            conn = self._get_conn()
            if global_search:
                rows = conn.execute(
                    "SELECT memory_id, vector, dimension FROM vectors"
                ).fetchall()
            else:
                target_ns = ns or self._default_ns
                rows = conn.execute(
                    "SELECT memory_id, vector, dimension FROM vectors WHERE namespace = ?",
                    (target_ns,),
                ).fetchall()

        if not rows:
            return []

        ids: list[str] = []
        vecs: list["np.ndarray"] = []
        for row in rows:
            ids.append(row["memory_id"])
            vecs.append(_blob_to_vec(row["vector"], row["dimension"]))

        mat = np.stack(vecs)  # (N, dim)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10  # avoid division by zero
        mat = mat / norms

        scores = mat @ q  # cosine similarity  (N,)

        # Top-k
        if top_k >= len(scores):
            top_indices = np.argsort(-scores)
        else:
            # Use argpartition for efficiency then sort the top-k slice.
            part_idx = np.argpartition(-scores, top_k)[:top_k]
            top_indices = part_idx[np.argsort(-scores[part_idx])]

        results: list[SearchResult] = []
        for idx in top_indices:
            sim = float(scores[idx])
            if sim <= 0:
                continue
            results.append(SearchResult(id=ids[idx], score=sim))
        return results

    def delete(self, id: str) -> bool:
        """Delete a vector by memory id.

        Returns ``True`` if a row was deleted.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "DELETE FROM vectors WHERE memory_id = ?", (id,)
                )
                conn.commit()
                deleted = cur.rowcount > 0
                if deleted:
                    logger.debug("Vector deleted  id=%s", id)
                return deleted
            except Exception:
                conn.rollback()
                raise

    def count(self) -> int:
        """Return the total number of stored vectors."""
        with self._lock:
            conn = self._get_conn()
            return self._count_unlocked(conn)

    def rebuild(self) -> None:
        """No-op for the brute-force backend.

        Logged for informational purposes.  For optimised indices
        consider ``VectorIndexIVF`` or Qdrant.
        """
        logger.info(
            "SQLiteVectorBackend.rebuild() is a no-op "
            "(brute-force search has no index structure to rebuild)."
        )

    # ---- extra convenience methods ---------------------------------------

    def count_by_namespace(self, namespace: Optional[str] = None) -> int:
        """Count vectors in a specific namespace."""
        ns = namespace or self._default_ns
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM vectors WHERE namespace = ?",
                (ns,),
            ).fetchone()
            return row["cnt"] if row else 0

    def get_vector(self, memory_id: str) -> Optional[List[float]]:
        """Retrieve a stored vector by its memory id.

        Returns
        -------
        list of float or None
        """
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT vector, dimension FROM vectors WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                return None
            return _blob_to_vec(row["vector"], row["dimension"]).tolist()

    def clear(
        self,
        *,
        namespace: Optional[str] = None,
        global_clear: bool = False,
    ) -> int:
        """Delete vectors.

        Parameters
        ----------
        namespace : str, optional
            Restrict deletion to this namespace.
        global_clear : bool
            If ``True`` delete all vectors.

        Returns
        -------
        int
            Number of rows deleted.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                if global_clear:
                    cur = conn.execute("DELETE FROM vectors")
                else:
                    ns = namespace or self._default_ns
                    cur = conn.execute(
                        "DELETE FROM vectors WHERE namespace = ?", (ns,)
                    )
                conn.commit()
                logger.info("Vectors cleared: %d", cur.rowcount)
                return cur.rowcount
            except Exception:
                conn.rollback()
                raise

    # ---- internal --------------------------------------------------------

    @staticmethod
    def _count_unlocked(conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM vectors").fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        """Close this thread's connection."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
            logger.debug(
                "Vector connection closed for thread %s",
                threading.current_thread().name,
            )

    def __repr__(self) -> str:
        return f"<SQLiteVectorBackend db={self._db_path!r}>"
