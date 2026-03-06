"""Recall v7.0 - PostgreSQL Memory Backend

Implements :class:`StorageBackend` ABC for production-grade memory
persistence using PostgreSQL with JSONB metadata support.

Requires
--------
``psycopg2`` or ``psycopg2-binary`` (optional dependency).  The module
imports cleanly even when the package is absent; an ``ImportError`` is
raised only at construction time.

Configuration (environment variables)
--------------------------------------
PG_HOST          PostgreSQL hostname (default ``localhost``)
PG_PORT          PostgreSQL port (default ``5432``)
PG_USER          Database user (default ``recall``)
PG_PASSWORD      Database password (default empty)
PG_DATABASE      Database name (default ``recall``)
PG_POOL_MIN      Minimum connection pool size (default ``2``)
PG_POOL_MAX      Maximum connection pool size (default ``10``)

Design notes
------------
* **Connection pool** — uses ``psycopg2.pool.ThreadedConnectionPool``
  for thread-safe connection re-use.
* **JSONB metadata** — metadata is stored as a JSONB column with a GIN
  index for efficient containment queries.
* **Upsert** — ``ON CONFLICT DO UPDATE`` semantics mirroring the
  SQLite backend's behaviour.
* **Auto-create** — tables and indexes are created on first use.
* **Namespace isolation** — all queries optionally scope by namespace.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .interfaces import StorageBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional psycopg2 import
# ---------------------------------------------------------------------------

_PG_AVAILABLE: bool = False
_pool_cls = None

try:
    import psycopg2  # type: ignore
    import psycopg2.extras  # type: ignore
    import psycopg2.pool  # type: ignore

    _PG_AVAILABLE = True
    _pool_cls = psycopg2.pool.ThreadedConnectionPool
except ImportError:
    psycopg2 = None  # type: ignore

# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    external_id TEXT,
    content     TEXT NOT NULL,
    metadata    JSONB,
    user_id     TEXT DEFAULT 'default',
    session_id  TEXT,
    namespace   TEXT NOT NULL DEFAULT 'default',
    source      TEXT NOT NULL DEFAULT 'user',
    category    TEXT,
    event_time  TIMESTAMPTZ,
    importance  REAL DEFAULT 0.5,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
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
CREATE INDEX IF NOT EXISTS idx_metadata_gin
    ON memories USING GIN (metadata);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """Generate a new UUID-4 string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# PostgreSQLMemoryBackend
# ---------------------------------------------------------------------------


class PostgreSQLMemoryBackend(StorageBackend):
    """PostgreSQL-backed memory storage with JSONB metadata and connection pooling.

    Parameters
    ----------
    host : str or None
        Database hostname.  Falls back to ``PG_HOST`` or ``"localhost"``.
    port : int or None
        Database port.  Falls back to ``PG_PORT`` or ``5432``.
    user : str or None
        Database user.  Falls back to ``PG_USER`` or ``"recall"``.
    password : str or None
        Database password.  Falls back to ``PG_PASSWORD`` or ``""``.
    database : str or None
        Database name.  Falls back to ``PG_DATABASE`` or ``"recall"``.
    pool_min : int or None
        Min pool size.  Falls back to ``PG_POOL_MIN`` or ``2``.
    pool_max : int or None
        Max pool size.  Falls back to ``PG_POOL_MAX`` or ``10``.
    default_namespace : str
        Default namespace for queries.

    Raises
    ------
    ImportError
        If ``psycopg2`` is not installed.
    RuntimeError
        If a database connection cannot be established.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        pool_min: int | None = None,
        pool_max: int | None = None,
        default_namespace: str = "default",
    ) -> None:
        if not _PG_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PostgreSQLMemoryBackend. "
                "Install it with:  pip install psycopg2-binary"
            )

        self._host = host or os.environ.get("PG_HOST", "localhost")
        self._port = port or int(os.environ.get("PG_PORT", "5432"))
        self._user = user or os.environ.get("PG_USER", "recall")
        self._password = password or os.environ.get("PG_PASSWORD", "")
        self._database = database or os.environ.get("PG_DATABASE", "recall")
        self._pool_min = pool_min or int(os.environ.get("PG_POOL_MIN", "2"))
        self._pool_max = pool_max or int(os.environ.get("PG_POOL_MAX", "10"))
        self._default_ns = default_namespace
        self._lock = threading.RLock()

        # Establish connection pool
        try:
            self._pool = _pool_cls(
                minconn=self._pool_min,
                maxconn=self._pool_max,
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                database=self._database,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create PostgreSQL connection pool "
                f"({self._host}:{self._port}/{self._database}): {exc}"
            ) from exc

        # Auto-create schema
        self._init_schema()
        logger.info(
            "PostgreSQLMemoryBackend initialised  host=%s:%s  db=%s  pool=%d-%d",
            self._host,
            self._port,
            self._database,
            self._pool_min,
            self._pool_max,
        )

    # ---- connection management -------------------------------------------

    def _get_conn(self):
        """Obtain a connection from the pool."""
        return self._pool.getconn()

    def _put_conn(self, conn) -> None:
        """Return a connection to the pool."""
        self._pool.putconn(conn)

    def _init_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA_SQL)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    # ---- StorageBackend ABC implementation --------------------------------

    def save(self, id: str, data: Dict[str, Any]) -> None:
        """Persist *data* under *id* (delegates to :meth:`upsert`)."""
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

    def list(self, prefix: str = "") -> List[str]:
        """Return memory ids, optionally filtered by id prefix."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if prefix:
                    cur.execute(
                        "SELECT id FROM memories WHERE id LIKE %s ORDER BY created_at DESC",
                        (prefix + "%",),
                    )
                else:
                    cur.execute("SELECT id FROM memories ORDER BY created_at DESC")
                return [row[0] for row in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def exists(self, id: str) -> bool:
        """Check whether a memory with *id* exists."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM memories WHERE id = %s", (id,))
                return cur.fetchone() is not None
        finally:
            self._put_conn(conn)

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

        Uses ``ON CONFLICT`` upsert when *external_id* is supplied.

        Returns
        -------
        str
            The id of the inserted / updated memory.
        """
        ns = namespace or self._default_ns
        now = _now_iso()
        mem_id = id or _new_id()
        meta_json = json.dumps(metadata) if metadata else None

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                if external_id is not None:
                    # Try to find existing row
                    cur.execute(
                        "SELECT id FROM memories "
                        "WHERE source = %s AND namespace = %s AND external_id = %s",
                        (source, ns, external_id),
                    )
                    existing = cur.fetchone()
                    if existing:
                        mem_id = existing[0]
                        cur.execute(
                            """UPDATE memories SET
                                content = %s, metadata = %s::jsonb, user_id = %s,
                                session_id = %s, category = %s, event_time = %s,
                                importance = %s, updated_at = %s
                            WHERE id = %s""",
                            (
                                content, meta_json, user_id,
                                session_id, category, event_time,
                                importance, now, mem_id,
                            ),
                        )
                        conn.commit()
                        logger.debug("Updated memory %s (external_id=%s)", mem_id, external_id)
                        return mem_id

                # Insert new row
                cur.execute(
                    """INSERT INTO memories
                    (id, external_id, content, metadata, user_id, session_id,
                     namespace, source, category, event_time, importance,
                     created_at, updated_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at""",
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
        finally:
            self._put_conn(conn)

    def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single memory by primary key."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM memories WHERE id = %s", (id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._put_conn(conn)

    def list_memories(
        self,
        *,
        namespace: Optional[str] = None,
        source: Optional[str] = None,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_dir: str = "DESC",
    ) -> List[Dict[str, Any]]:
        """List memories with flexible filtering and pagination.

        Parameters
        ----------
        namespace, source, user_id, category
            Optional equality filters.
        limit
            Maximum number of results (default 100).
        offset
            Number of results to skip (for pagination).
        order_by
            Column to sort by (default ``created_at``).
        order_dir
            Sort direction (``ASC`` or ``DESC``).

        Returns
        -------
        list of dict
        """
        # Whitelist sortable columns to prevent SQL injection
        allowed_columns = {
            "created_at", "updated_at", "importance", "id", "namespace", "source",
        }
        if order_by not in allowed_columns:
            order_by = "created_at"
        if order_dir.upper() not in ("ASC", "DESC"):
            order_dir = "DESC"

        conditions: List[str] = []
        params: List[Any] = []

        if namespace:
            conditions.append("namespace = %s")
            params.append(namespace)
        if source:
            conditions.append("source = %s")
            params.append(source)
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if category:
            conditions.append("category = %s")
            params.append(category)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM memories{where} ORDER BY {order_by} {order_dir} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def count(
        self,
        *,
        namespace: Optional[str] = None,
        source: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> int:
        """Count memories matching the given filters."""
        conditions: List[str] = []
        params: List[Any] = []

        if namespace:
            conditions.append("namespace = %s")
            params.append(namespace)
        if source:
            conditions.append("source = %s")
            params.append(source)
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT COUNT(*) FROM memories{where}"

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row else 0
        finally:
            self._put_conn(conn)

    def delete_by_id(self, id: str) -> bool:
        """Delete a single memory by primary key."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM memories WHERE id = %s", (id,))
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    def delete_by_namespace(self, namespace: str) -> int:
        """Delete all memories in a namespace.

        Returns the number of deleted rows.
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM memories WHERE namespace = %s", (namespace,))
                count = cur.rowcount
                conn.commit()
                logger.info("Deleted %d memories from namespace '%s'", count, namespace)
                return count
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    def search_metadata(
        self,
        contains: Dict[str, Any],
        *,
        namespace: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search memories whose JSONB metadata contains the given keys/values.

        Uses the ``@>`` containment operator which is accelerated by the
        GIN index.

        Parameters
        ----------
        contains
            Key-value pairs that must be present in the metadata JSONB.
        namespace
            Optional namespace filter.
        limit
            Maximum results.
        """
        conditions = ["metadata @> %s::jsonb"]
        params: List[Any] = [json.dumps(contains)]

        if namespace:
            conditions.append("namespace = %s")
            params.append(namespace)

        where = " WHERE " + " AND ".join(conditions)
        sql = f"SELECT * FROM memories{where} ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._put_conn(conn)

    def batch_upsert(self, items: Sequence[Dict[str, Any]]) -> int:
        """Bulk-insert or update memories in a single transaction.

        Each item should be a dict compatible with :meth:`save`.

        Returns
        -------
        int
            Number of upserted rows.
        """
        if not items:
            return 0

        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                for item in items:
                    mem_id = item.get("id") or _new_id()
                    ns = item.get("namespace", self._default_ns)
                    now = _now_iso()
                    meta_json = json.dumps(item.get("metadata")) if item.get("metadata") else None

                    cur.execute(
                        """INSERT INTO memories
                        (id, external_id, content, metadata, user_id, session_id,
                         namespace, source, category, event_time, importance,
                         created_at, updated_at)
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            metadata = EXCLUDED.metadata,
                            updated_at = EXCLUDED.updated_at""",
                        (
                            mem_id,
                            item.get("external_id"),
                            item.get("content", ""),
                            meta_json,
                            item.get("user_id", "default"),
                            item.get("session_id"),
                            ns,
                            item.get("source", "user"),
                            item.get("category"),
                            item.get("event_time"),
                            item.get("importance", 0.5),
                            now,
                            now,
                        ),
                    )
                conn.commit()
                count = len(items)
                logger.info("Batch-upserted %d memories.", count)
                return count
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    # ---- transaction support ---------------------------------------------

    def execute_in_transaction(self, operations: Sequence[Dict[str, Any]]) -> None:
        """Execute multiple operations atomically.

        Each operation is a dict with ``"action"`` (``"save"`` |
        ``"delete"``) and the corresponding payload.

        Parameters
        ----------
        operations
            List of ``{"action": "save", "id": ..., "data": {...}}``
            or ``{"action": "delete", "id": ...}`` dicts.
        """
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                for op in operations:
                    action = op.get("action")
                    if action == "save":
                        data = op.get("data", {})
                        mem_id = op.get("id") or data.get("id") or _new_id()
                        ns = data.get("namespace", self._default_ns)
                        now = _now_iso()
                        meta_json = json.dumps(data.get("metadata")) if data.get("metadata") else None
                        cur.execute(
                            """INSERT INTO memories
                            (id, external_id, content, metadata, user_id, session_id,
                             namespace, source, category, event_time, importance,
                             created_at, updated_at)
                            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                content = EXCLUDED.content,
                                metadata = EXCLUDED.metadata,
                                updated_at = EXCLUDED.updated_at""",
                            (
                                mem_id,
                                data.get("external_id"),
                                data.get("content", ""),
                                meta_json,
                                data.get("user_id", "default"),
                                data.get("session_id"),
                                ns,
                                data.get("source", "user"),
                                data.get("category"),
                                data.get("event_time"),
                                data.get("importance", 0.5),
                                now,
                                now,
                            ),
                        )
                    elif action == "delete":
                        cur.execute(
                            "DELETE FROM memories WHERE id = %s",
                            (op["id"],),
                        )
                    else:
                        raise ValueError(f"Unknown transaction action: {action!r}")
                conn.commit()
                logger.info("Executed %d operations in transaction.", len(operations))
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    # ---- health / lifecycle ----------------------------------------------

    def health_check(self) -> bool:
        """Return ``True`` if the database is reachable."""
        conn = None
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False
        finally:
            if conn:
                self._put_conn(conn)

    def close(self) -> None:
        """Close all connections in the pool."""
        try:
            self._pool.closeall()
            logger.info("PostgreSQLMemoryBackend connection pool closed.")
        except Exception:
            pass
