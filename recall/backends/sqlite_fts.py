"""Recall v7.0 – SQLite FTS5 Full-Text Search Backend

A three-in-one replacement for ``InvertedIndex``, ``NgramIndex`` and
``FullTextIndex`` using SQLite's built-in **FTS5** extension.  Provides
BM25 ranking, highlight snippets, and optional Chinese segmentation via
*jieba* (with a character-ngram fallback when jieba is unavailable).

The backend can share the same database file as
:class:`~recall.backends.sqlite_memory.SQLiteMemoryBackend` – simply
pass the same ``db_path``.

Design notes
------------
* **Thread safety** – an ``RLock`` protects every public method.
* **Connection-per-thread** – ``threading.local()`` gives each thread
  its own ``sqlite3.Connection``.
* **Chinese / CJK support** – if *jieba* is importable the query and
  indexed text are pre-segmented with spaces; otherwise CJK characters
  are split into overlapping 2-grams so FTS5's default ``unicode61``
  tokeniser can still match them.
* **BM25** – built into FTS5 via ``bm25()``; no extra dependency.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
import unicodedata
from typing import Any, Dict, List, Optional, Sequence

from .interfaces import SearchResult, TextSearchBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional jieba import
# ---------------------------------------------------------------------------

_JIEBA_AVAILABLE: bool = False
try:
    import jieba  # type: ignore

    _JIEBA_AVAILABLE = True
except ImportError:
    jieba = None  # type: ignore

# ---------------------------------------------------------------------------
# CJK detection helpers
# ---------------------------------------------------------------------------

_CJK_RANGES = re.compile(
    "["
    "\u4e00-\u9fff"    # CJK Unified Ideographs
    "\u3400-\u4dbf"    # CJK Extension A
    "\uf900-\ufaff"    # CJK Compatibility Ideographs
    "\U00020000-\U0002a6df"  # CJK Extension B
    "]"
)


def _has_cjk(text: str) -> bool:
    """Return True if *text* contains any CJK ideograph."""
    return bool(_CJK_RANGES.search(text))


def _segment_text(text: str) -> str:
    """Pre-segment *text* for FTS5 indexing.

    * **With jieba** – Chinese text is segmented with ``jieba.cut``;
      non-CJK runs are left as-is (FTS5 handles word breaking).
    * **Without jieba** – CJK characters are split into overlapping
      character bigrams.  This is a crude but functional fallback.
    """
    if not _has_cjk(text):
        return text

    if _JIEBA_AVAILABLE:
        return " ".join(jieba.cut(text))

    # Fallback: character bigrams for CJK, whitespace-delimited otherwise.
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if _CJK_RANGES.match(ch):
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        else:
            buf += ch
    if buf:
        tokens.append(buf)

    # Create bigrams only from consecutive CJK chars
    result: list[str] = []
    cjk_chars: list[str] = []
    for tok in tokens:
        if len(tok) == 1 and _CJK_RANGES.match(tok):
            cjk_chars.append(tok)
        else:
            if cjk_chars:
                result.extend(_bigrams(cjk_chars))
                cjk_chars = []
            result.append(tok)
    if cjk_chars:
        result.extend(_bigrams(cjk_chars))
    return " ".join(result)


def _bigrams(chars: Sequence[str]) -> list[str]:
    """Produce overlapping bigrams from a list of single characters."""
    if len(chars) <= 1:
        return list(chars)
    return [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]


# ---------------------------------------------------------------------------
# FTS5 schema SQL
# ---------------------------------------------------------------------------

_FTS_SCHEMA_SQL = """\
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    memory_id,
    content,
    keywords,
    entities,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS fts_metadata (
    memory_id  TEXT PRIMARY KEY,
    user_id    TEXT,
    namespace  TEXT,
    created_at REAL
);
"""

# ---------------------------------------------------------------------------
# SQLiteFTS5Backend
# ---------------------------------------------------------------------------


class SQLiteFTS5Backend(TextSearchBackend):
    """FTS5-powered full-text search backend.

    Replaces the legacy ``InvertedIndex + NgramIndex + FullTextIndex``
    trio with a single SQLite virtual table that provides BM25 ranking,
    prefix queries, and highlight snippets out of the box.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.  Pass the same path as
        ``SQLiteMemoryBackend`` to share a single database.
    default_namespace : str
        Namespace used when no explicit one is provided.
    """

    def __init__(
        self,
        db_path: str = "recall_data/data/memories.db",
        default_namespace: str = "default",
    ) -> None:
        self._db_path = str(db_path)
        self._default_ns = default_namespace
        self._lock = threading.RLock()
        self._local = threading.local()

        from pathlib import Path
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_schema()
        logger.info(
            "SQLiteFTS5Backend initialised  db=%s  jieba=%s",
            self._db_path,
            _JIEBA_AVAILABLE,
        )

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
        conn.executescript(_FTS_SCHEMA_SQL)
        conn.commit()

    # ---- TextSearchBackend ABC -------------------------------------------

    def add(self, id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Index a document.

        This is the ABC-mandated signature.  For richer indexing that
        also stores keywords and entities call :meth:`add_memory`
        directly.
        """
        self.add_memory(
            memory_id=id,
            content=text,
            metadata=metadata or {},
        )

    def search(  # type: ignore[override]
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Full-text search with BM25 ranking.

        Parameters
        ----------
        query : str
            Natural language or keyword query.
        top_k : int
            Maximum number of results.
        filters : dict, optional
            Supported keys: ``namespace``, ``user_id``, ``global``
            (bool, if True disables namespace filtering).
        """
        filters = filters or {}
        namespace: Optional[str] = filters.get("namespace")
        user_id: Optional[str] = filters.get("user_id")
        global_search: bool = filters.get("global", False)

        return self.search_memories(
            query=query,
            top_k=top_k,
            namespace=namespace,
            user_id=user_id,
            global_search=global_search,
        )

    def delete(self, id: str) -> bool:
        """Remove a document from the FTS index."""
        return self.delete_memory(id)

    # ---- extended API ----------------------------------------------------

    def add_memory(
        self,
        memory_id: str,
        content: str,
        keywords: Optional[Sequence[str]] = None,
        entities: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Index a memory with content, keywords, and entity terms.

        If *memory_id* already exists it is replaced (delete + insert).

        Parameters
        ----------
        memory_id : str
            Unique memory identifier.
        content : str
            Full text of the memory.
        keywords : list of str, optional
            Keyword tokens to co-index.
        entities : list of str, optional
            Entity names / terms to co-index.
        metadata : dict, optional
            Must include ``namespace`` and/or ``user_id`` for filtered
            retrieval.
        """
        metadata = metadata or {}
        kw_text = " ".join(keywords) if keywords else ""
        ent_text = " ".join(entities) if entities else ""

        seg_content = _segment_text(content)
        seg_kw = _segment_text(kw_text)
        seg_ent = _segment_text(ent_text)

        ns = metadata.get("namespace", self._default_ns)
        user_id = metadata.get("user_id", "default")
        created_at = metadata.get("created_at", time.time())

        with self._lock:
            conn = self._get_conn()
            try:
                # Remove any previous entry
                conn.execute(
                    "DELETE FROM memories_fts WHERE memory_id = ?",
                    (memory_id,),
                )
                conn.execute(
                    "DELETE FROM fts_metadata WHERE memory_id = ?",
                    (memory_id,),
                )
                # Insert into FTS table
                conn.execute(
                    "INSERT INTO memories_fts (memory_id, content, keywords, entities) "
                    "VALUES (?, ?, ?, ?)",
                    (memory_id, seg_content, seg_kw, seg_ent),
                )
                # Insert metadata
                conn.execute(
                    "INSERT INTO fts_metadata (memory_id, user_id, namespace, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (memory_id, user_id, ns, created_at),
                )
                conn.commit()
                logger.debug("FTS indexed memory %s", memory_id)
            except Exception:
                conn.rollback()
                raise

    def search_memories(
        self,
        query: str,
        top_k: int = 10,
        namespace: Optional[str] = None,
        user_id: Optional[str] = None,
        global_search: bool = False,
        highlight: bool = False,
    ) -> List[SearchResult]:
        """Search indexed memories with BM25 ranking.

        Parameters
        ----------
        query : str
            The search query.
        top_k : int
            Maximum results.
        namespace : str, optional
            Restrict results to this namespace.
        user_id : str, optional
            Restrict results to this user.
        global_search : bool
            Skip namespace filtering.
        highlight : bool
            If ``True``, include ``<b>…</b>`` highlight snippets in the
            result's ``text`` field.

        Returns
        -------
        list of SearchResult
        """
        if not query or not query.strip():
            return []

        seg_query = _segment_text(query.strip())
        # Escape FTS5 special characters for a MATCH-safe query
        fts_query = self._escape_fts_query(seg_query)
        if not fts_query:
            return []

        # Build SQL
        if highlight:
            select_text = "highlight(memories_fts, 1, '<b>', '</b>')"
        else:
            select_text = "memories_fts.content"

        sql_parts = [
            f"SELECT memories_fts.memory_id, "
            f"  bm25(memories_fts) AS score, "
            f"  {select_text} AS text_out "
            f"FROM memories_fts "
            f"INNER JOIN fts_metadata ON fts_metadata.memory_id = memories_fts.memory_id "
            f"WHERE memories_fts MATCH ?"
        ]
        params: list[Any] = [fts_query]

        if not global_search:
            ns = namespace or self._default_ns
            sql_parts.append("AND fts_metadata.namespace = ?")
            params.append(ns)
        if user_id:
            sql_parts.append("AND fts_metadata.user_id = ?")
            params.append(user_id)

        sql_parts.append("ORDER BY score ASC")  # bm25() returns negative; lower = better
        sql_parts.append("LIMIT ?")
        params.append(top_k)

        sql = " ".join(sql_parts)

        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError as exc:
                logger.warning("FTS query failed: %s  query=%r", exc, fts_query)
                return []

        results: list[SearchResult] = []
        for row in rows:
            # Normalise BM25 score to a positive value (negate)
            raw_score = row["score"]
            positive_score = -raw_score if raw_score < 0 else raw_score
            results.append(
                SearchResult(
                    id=row["memory_id"],
                    score=positive_score,
                    text=row["text_out"],
                )
            )
        return results

    def delete_memory(self, memory_id: str) -> bool:
        """Remove a memory from both the FTS index and metadata table.

        Returns ``True`` if a row was deleted.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "DELETE FROM memories_fts WHERE memory_id = ?",
                    (memory_id,),
                )
                conn.execute(
                    "DELETE FROM fts_metadata WHERE memory_id = ?",
                    (memory_id,),
                )
                conn.commit()
                deleted = cur.rowcount > 0
                if deleted:
                    logger.debug("FTS deleted memory %s", memory_id)
                return deleted
            except Exception:
                conn.rollback()
                raise

    def count(
        self,
        *,
        namespace: Optional[str] = None,
        global_search: bool = False,
    ) -> int:
        """Return the number of indexed memories."""
        clauses: list[str] = []
        params: list[Any] = []

        if not global_search:
            ns = namespace or self._default_ns
            clauses.append("namespace = ?")
            params.append(ns)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT COUNT(*) AS cnt FROM fts_metadata{where}"

        with self._lock:
            conn = self._get_conn()
            row = conn.execute(sql, params).fetchone()
            return row["cnt"] if row else 0

    def clear(
        self,
        *,
        namespace: Optional[str] = None,
        global_clear: bool = False,
    ) -> int:
        """Delete indexed entries."""
        with self._lock:
            conn = self._get_conn()
            try:
                if global_clear:
                    conn.execute("DELETE FROM memories_fts")
                    cur = conn.execute("DELETE FROM fts_metadata")
                else:
                    ns = namespace or self._default_ns
                    # Identify memory_ids to delete from FTS
                    ids = conn.execute(
                        "SELECT memory_id FROM fts_metadata WHERE namespace = ?",
                        (ns,),
                    ).fetchall()
                    id_list = [r["memory_id"] for r in ids]
                    if id_list:
                        placeholders = ",".join("?" * len(id_list))
                        conn.execute(
                            f"DELETE FROM memories_fts WHERE memory_id IN ({placeholders})",
                            id_list,
                        )
                    cur = conn.execute(
                        "DELETE FROM fts_metadata WHERE namespace = ?",
                        (ns,),
                    )
                conn.commit()
                count = cur.rowcount
                logger.info("FTS cleared %d entries", count)
                return count
            except Exception:
                conn.rollback()
                raise

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _escape_fts_query(text: str) -> str:
        """Escape an arbitrary string for safe use in an FTS5 MATCH clause.

        Strategy: tokenise the input into "words" (sequences of
        non-whitespace), wrap each in double quotes, and join with
        ``OR``.  This avoids FTS5 syntax errors from user-supplied
        special characters while still allowing multi-term matching.
        """
        words = text.split()
        if not words:
            return ""
        escaped = ['"' + w.replace('"', '""') + '"' for w in words]
        return " OR ".join(escaped)

    def close(self) -> None:
        """Close this thread's connection."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
            logger.debug("FTS connection closed for thread %s", threading.current_thread().name)

    def __repr__(self) -> str:
        return f"<SQLiteFTS5Backend db={self._db_path!r} jieba={_JIEBA_AVAILABLE}>"
