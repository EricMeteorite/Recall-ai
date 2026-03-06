"""Recall v7.0 – SQLite Memory Backend

A thread-safe, file-based memory storage backend built on Python's
built-in ``sqlite3`` module.  Implements :class:`StorageBackend` and adds
richer relational queries (namespace filtering, upsert, import/export,
backup).

Design notes
------------
* **Thread safety** – every public method acquires an ``RLock`` so the
  backend can be shared across threads without external synchronisation.
* **Connection-per-thread** – uses ``threading.local()`` so each thread
  gets its own ``sqlite3.Connection`` (SQLite connections cannot be
  shared across threads in most builds).
* **Atomic writes** – mutating operations run inside an explicit
  transaction (``BEGIN IMMEDIATE … COMMIT``).
* **JSON metadata** – the ``metadata`` column is stored as TEXT and
  transparently (de)serialised on read/write.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .interfaces import StorageBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    external_id TEXT,
    content     TEXT NOT NULL,
    metadata    TEXT,
    user_id     TEXT DEFAULT 'default',
    session_id  TEXT,
    namespace   TEXT NOT NULL DEFAULT 'default',
    source      TEXT NOT NULL DEFAULT 'user',
    category    TEXT,
    event_time  TEXT,
    importance  REAL DEFAULT 0.5,
    created_at  REAL,
    updated_at  REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_upsert
    ON memories(source, namespace, external_id)
    WHERE external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user       ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_time       ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_namespace  ON memories(namespace);
CREATE INDEX IF NOT EXISTS idx_source     ON memories(source);
CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance);
CREATE INDEX IF NOT EXISTS idx_source_ns_time
    ON memories(source, namespace, created_at);
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now() -> float:
    """Return the current UNIX timestamp as a float."""
    return time.time()


def _new_id() -> str:
    """Generate a new UUID-4 string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# SQLiteMemoryBackend
# ---------------------------------------------------------------------------

class SQLiteMemoryBackend(StorageBackend):
    """SQLite-backed memory storage with namespace isolation.

    Parameters
    ----------
    db_path : str or Path
        File-system path to the SQLite database.  Use ``":memory:"`` for
        an ephemeral in-memory database (mainly useful for testing).
    default_namespace : str, optional
        Namespace used when the caller does not specify one.
    """

    # ---- construction / lifecycle ----------------------------------------

    def __init__(
        self,
        db_path: str | Path = "recall_data/data/memories.db",
        default_namespace: str = "default",
    ) -> None:
        self._db_path = str(db_path)
        self._default_ns = default_namespace
        self._lock = threading.RLock()
        self._local = threading.local()

        # Ensure parent directory exists (unless in-memory)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialise schema on the calling thread's connection.
        self._init_schema()
        logger.info("SQLiteMemoryBackend initialised  db=%s", self._db_path)

    # ---- connection management -------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return the ``sqlite3.Connection`` for the current thread.

        Creates one on first access and applies common PRAGMAs.
        """
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
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    # ---- StorageBackend ABC implementation --------------------------------

    def save(self, id: str, data: Dict[str, Any]) -> None:
        """Persist *data* under *id*.

        This is a thin adapter that delegates to :meth:`upsert` so
        callers using the generic ``StorageBackend`` interface still get
        upsert semantics automatically.
        """
        self.upsert(
            content=data.get("content", json.dumps(data)),
            id=id,
            metadata=data.get("metadata"),
            namespace=data.get("namespace", self._default_ns),
            source=data.get("source", "user"),
            external_id=data.get("external_id"),
            user_id=data.get("user_id", "default"),
            session_id=data.get("session_id"),
            category=data.get("category"),
            event_time=data.get("event_time"),
            importance=data.get("importance", 0.5),
        )

    def load(self, id: str) -> Optional[Dict[str, Any]]:
        """Load a single memory by its primary-key *id*."""
        return self.get_by_id(id)

    def delete(self, id: str) -> bool:
        """Delete a memory by *id*."""
        return self.delete_by_id(id)

    def list(self, prefix: str = "") -> List[str]:  # type: ignore[override]
        """Return memory ids, optionally filtered by id prefix."""
        with self._lock:
            conn = self._get_conn()
            if prefix:
                rows = conn.execute(
                    "SELECT id FROM memories WHERE id LIKE ? ORDER BY created_at DESC",
                    (prefix + "%",),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM memories ORDER BY created_at DESC"
                ).fetchall()
            return [r["id"] for r in rows]

    def exists(self, id: str) -> bool:
        """Check whether a memory with *id* exists."""
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT 1 FROM memories WHERE id = ?", (id,)
            ).fetchone()
            return row is not None

    # ---- extended CRUD ----------------------------------------------------

    def upsert(
        self,
        content: str,
        *,
        id: Optional[str] = None,
        external_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
        session_id: Optional[str] = None,
        namespace: Optional[str] = None,
        source: str = "user",
        category: Optional[str] = None,
        event_time: Optional[str] = None,
        importance: float = 0.5,
    ) -> str:
        """Insert a new memory or update an existing one.

        When *external_id* is supplied and a row with the same
        ``(source, namespace, external_id)`` triple already exists the
        row is updated in place; otherwise a new row is inserted.

        Returns
        -------
        str
            The id of the inserted / updated memory.
        """
        ns = namespace or self._default_ns
        now = _now()
        meta_json = json.dumps(metadata) if metadata else None

        with self._lock:
            conn = self._get_conn()
            try:
                # Try to find existing row by external_id composite key
                if external_id is not None:
                    existing = conn.execute(
                        "SELECT id FROM memories "
                        "WHERE source = ? AND namespace = ? AND external_id = ?",
                        (source, ns, external_id),
                    ).fetchone()
                    if existing:
                        mem_id = existing["id"]
                        conn.execute(
                            "UPDATE memories SET "
                            "  content = ?, metadata = ?, user_id = ?, "
                            "  session_id = ?, category = ?, event_time = ?, "
                            "  importance = ?, updated_at = ? "
                            "WHERE id = ?",
                            (
                                content, meta_json, user_id,
                                session_id, category, event_time,
                                importance, now, mem_id,
                            ),
                        )
                        conn.commit()
                        logger.debug("Updated memory %s (external_id=%s)", mem_id, external_id)
                        return mem_id

                # Insert new row (use INSERT OR REPLACE to support upsert by id)
                mem_id = id or _new_id()
                conn.execute(
                    "INSERT OR REPLACE INTO memories "
                    "(id, external_id, content, metadata, user_id, session_id, "
                    " namespace, source, category, event_time, importance, "
                    " created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        mem_id, external_id, content, meta_json, user_id,
                        session_id, ns, source, category, event_time,
                        importance, now, now,
                    ),
                )
                conn.commit()
                logger.debug("Inserted memory %s", mem_id)
                return mem_id
            except Exception:
                conn.rollback()
                raise

    def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single memory by primary key.

        Returns
        -------
        dict or None
            The memory as a plain dict with parsed ``metadata``, or
            ``None`` if not found.
        """
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def list_memories(
        self,
        *,
        namespace: Optional[str] = None,
        source: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        ascending: bool = False,
        global_search: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return a paginated list of memories.

        Parameters
        ----------
        namespace : str, optional
            Filter by namespace.  Ignored when *global_search* is True.
        source, user_id : str, optional
            Additional column filters.
        limit, offset : int
            Pagination controls.
        order_by : str
            Column name used for ordering.
        ascending : bool
            Sort direction.
        global_search : bool
            If ``True``, skip namespace filtering (cross-namespace).
        """
        clauses: list[str] = []
        params: list[Any] = []

        if not global_search:
            ns = namespace or self._default_ns
            clauses.append("namespace = ?")
            params.append(ns)

        if source:
            clauses.append("source = ?")
            params.append(source)
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        direction = "ASC" if ascending else "DESC"
        # Safeguard order_by against injection
        allowed_columns = {
            "created_at", "updated_at", "importance", "id", "namespace",
        }
        if order_by not in allowed_columns:
            order_by = "created_at"

        sql = (
            f"SELECT * FROM memories{where} "
            f"ORDER BY {order_by} {direction} "
            f"LIMIT ? OFFSET ?"
        )
        params += [limit, offset]

        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def count(
        self,
        *,
        namespace: Optional[str] = None,
        source: Optional[str] = None,
        global_search: bool = False,
    ) -> int:
        """Return the number of memories matching the filters.

        Parameters
        ----------
        namespace : str, optional
            Filter by namespace.  Ignored when *global_search*.
        source : str, optional
            Filter by source.
        global_search : bool
            If ``True``, count across all namespaces.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if not global_search:
            ns = namespace or self._default_ns
            clauses.append("namespace = ?")
            params.append(ns)
        if source:
            clauses.append("source = ?")
            params.append(source)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT COUNT(*) as cnt FROM memories{where}"

        with self._lock:
            conn = self._get_conn()
            row = conn.execute(sql, params).fetchone()
            return row["cnt"] if row else 0

    def delete_by_id(self, id: str) -> bool:
        """Delete a memory by primary key.

        Returns ``True`` if a row was actually deleted.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("DELETE FROM memories WHERE id = ?", (id,))
                conn.commit()
                deleted = cur.rowcount > 0
                if deleted:
                    logger.debug("Deleted memory %s", id)
                return deleted
            except Exception:
                conn.rollback()
                raise

    def clear(
        self,
        *,
        namespace: Optional[str] = None,
        global_clear: bool = False,
    ) -> int:
        """Remove memories.

        Parameters
        ----------
        namespace : str, optional
            Delete only within this namespace.  Ignored when *global_clear*.
        global_clear : bool
            If ``True``, delete **all** memories regardless of namespace.

        Returns
        -------
        int
            Number of rows deleted.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                if global_clear:
                    cur = conn.execute("DELETE FROM memories")
                else:
                    ns = namespace or self._default_ns
                    cur = conn.execute(
                        "DELETE FROM memories WHERE namespace = ?", (ns,)
                    )
                conn.commit()
                logger.info("Cleared %d memories", cur.rowcount)
                return cur.rowcount
            except Exception:
                conn.rollback()
                raise

    # ---- import / export / backup ----------------------------------------

    def import_memories(self, records: Sequence[Dict[str, Any]]) -> int:
        """Bulk-import memories from a list of dicts.

        Each dict should contain at least a ``content`` key.  Other
        recognised keys mirror the column names of the memories table.

        Returns
        -------
        int
            Number of records imported.
        """
        count = 0
        for rec in records:
            content = rec.get("content")
            if not content:
                logger.warning("Skipping record without content: %s", rec.get("id"))
                continue
            self.upsert(
                content=content,
                id=rec.get("id"),
                external_id=rec.get("external_id"),
                metadata=rec.get("metadata"),
                user_id=rec.get("user_id", "default"),
                session_id=rec.get("session_id"),
                namespace=rec.get("namespace", self._default_ns),
                source=rec.get("source", "user"),
                category=rec.get("category"),
                event_time=rec.get("event_time"),
                importance=rec.get("importance", 0.5),
            )
            count += 1
        logger.info("Imported %d memories", count)
        return count

    def export_memories(
        self,
        *,
        namespace: Optional[str] = None,
        global_export: bool = False,
    ) -> List[Dict[str, Any]]:
        """Export memories as a list of plain dicts.

        Parameters
        ----------
        namespace : str, optional
            Export only this namespace.  Ignored when *global_export*.
        global_export : bool
            If ``True``, export everything.
        """
        return self.list_memories(
            namespace=namespace,
            global_search=global_export,
            limit=2**31,
        )

    def backup(self, dest_path: str | Path) -> None:
        """Create a file-level copy of the database.

        Parameters
        ----------
        dest_path : str or Path
            Destination file path.  Parent directories are created if
            needed.

        Raises
        ------
        RuntimeError
            If the backend uses an in-memory database.
        """
        if self._db_path == ":memory:":
            raise RuntimeError("Cannot backup an in-memory database")

        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            # Checkpoint WAL to ensure everything is flushed.
            conn = self._get_conn()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            shutil.copy2(self._db_path, dest)
        logger.info("Database backed up to %s", dest)

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a ``sqlite3.Row`` to a plain dict, parsing metadata JSON."""
        d = dict(row)
        raw = d.get("metadata")
        if raw:
            try:
                d["metadata"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = {}
        else:
            d["metadata"] = {}
        return d

    def close(self) -> None:
        """Close the current thread's connection (if open)."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
            logger.debug("Connection closed for thread %s", threading.current_thread().name)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"<SQLiteMemoryBackend db={self._db_path!r}>"
