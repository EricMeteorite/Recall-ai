"""Recall v7.0 - NebulaGraph Graph Backend

Implements :class:`GraphBackend` ABC for distributed graph storage and
traversal using NebulaGraph as the backing engine.

Requires
--------
``nebula3-python`` (optional dependency).  The module imports cleanly
even when the package is absent; an ``ImportError`` is raised only at
construction time.

Configuration (environment variables)
--------------------------------------
NEBULA_HOST        NebulaGraph graphd hostname (default ``127.0.0.1``)
NEBULA_PORT        graphd port (default ``9669``)
NEBULA_USER        Username (default ``root``)
NEBULA_PASSWORD    Password (default ``nebula``)
NEBULA_SPACE       Graph space name (default ``recall``)

Design notes
------------
* **nGQL** — all graph operations are expressed as nGQL statements.
* **Session pool** — a pool of sessions is maintained for concurrency.
* **Auto-create space** — the configured space (and tags / edge types)
  are created on first use if they do not already exist.
* **Graceful degradation** — clear error messages if NebulaGraph is
  unreachable.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from .interfaces import GraphBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional nebula3-python import
# ---------------------------------------------------------------------------

_NEBULA_AVAILABLE: bool = False

try:
    from nebula3.gclient.net import ConnectionPool as NebulaConnectionPool  # type: ignore
    from nebula3.Config import Config as NebulaConfig  # type: ignore
    from nebula3.common.ttypes import ErrorCode as NebulaErrorCode  # type: ignore

    _NEBULA_AVAILABLE = True
except ImportError:
    NebulaConnectionPool = None  # type: ignore
    NebulaConfig = None  # type: ignore
    NebulaErrorCode = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5

# nGQL schema statements
_SPACE_SCHEMA_NGQL = """\
CREATE SPACE IF NOT EXISTS {space} (
    vid_type=FIXED_STRING(128),
    partition_num=10,
    replica_factor=1
);
"""

_TAG_SCHEMA_NGQL = """\
USE {space};
CREATE TAG IF NOT EXISTS entity (
    name string,
    type string DEFAULT "unknown",
    properties string DEFAULT "",
    created_at int DEFAULT 0
);
"""

_EDGE_SCHEMA_NGQL = """\
USE {space};
CREATE EDGE IF NOT EXISTS relates_to (
    relation string,
    weight double DEFAULT 1.0,
    properties string DEFAULT "",
    created_at int DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escape_ngql(value: str) -> str:
    """Escape a string for safe inclusion in nGQL queries."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


# ---------------------------------------------------------------------------
# NebulaGraphBackend
# ---------------------------------------------------------------------------


class NebulaGraphBackend(GraphBackend):
    """Distributed knowledge-graph backend powered by NebulaGraph.

    Parameters
    ----------
    host : str or None
        NebulaGraph graphd host.  Falls back to ``NEBULA_HOST`` or ``"127.0.0.1"``.
    port : int or None
        graphd port.  Falls back to ``NEBULA_PORT`` or ``9669``.
    user : str or None
        Username.  Falls back to ``NEBULA_USER`` or ``"root"``.
    password : str or None
        Password.  Falls back to ``NEBULA_PASSWORD`` or ``"nebula"``.
    space : str or None
        Graph space.  Falls back to ``NEBULA_SPACE`` or ``"recall"``.
    pool_size : int
        Session pool size (default ``10``).

    Raises
    ------
    ImportError
        If ``nebula3-python`` is not installed.
    RuntimeError
        If NebulaGraph is unreachable.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        space: str | None = None,
        pool_size: int = 10,
    ) -> None:
        if not _NEBULA_AVAILABLE:
            raise ImportError(
                "nebula3-python is required for NebulaGraphBackend. "
                "Install it with:  pip install nebula3-python"
            )

        self._host = host or os.environ.get("NEBULA_HOST", "127.0.0.1")
        self._port = port or int(os.environ.get("NEBULA_PORT", "9669"))
        self._user = user or os.environ.get("NEBULA_USER", "root")
        self._password = password or os.environ.get("NEBULA_PASSWORD", "nebula")
        self._space = space or os.environ.get("NEBULA_SPACE", "recall")
        self._pool_size = pool_size

        # Initialize connection pool
        config = NebulaConfig()
        config.max_connection_pool_size = pool_size
        config.timeout = 10000  # ms

        self._pool = NebulaConnectionPool()
        ok = self._pool.init([(self._host, self._port)], config)
        if not ok:
            raise RuntimeError(
                f"Failed to connect to NebulaGraph at {self._host}:{self._port}"
            )

        # Ensure space and schema exist
        self._ensure_schema()
        logger.info(
            "NebulaGraphBackend initialised  host=%s:%s  space=%s",
            self._host,
            self._port,
            self._space,
        )

    # ---- schema management -----------------------------------------------

    def _get_session(self):
        """Obtain a session from the pool."""
        return self._pool.get_session(self._user, self._password)

    def _execute(self, ngql: str, session=None) -> Any:
        """Execute an nGQL statement with retry logic.

        Parameters
        ----------
        ngql : str
            nGQL query string.
        session : optional
            Reuse an existing session.

        Returns
        -------
        ResultSet from NebulaGraph.
        """
        own_session = session is None
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            sess = session
            try:
                if own_session:
                    sess = self._get_session()
                result = sess.execute(ngql)
                if result.is_succeeded():
                    return result
                # Non-success but not an exception — log and return
                err_msg = result.error_msg()
                logger.warning("nGQL execution warning: %s  (query: %s)", err_msg, ngql[:200])
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "NebulaGraph request failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt, _MAX_RETRIES, delay, exc,
                    )
                    time.sleep(delay)
            finally:
                if own_session and sess is not None:
                    try:
                        sess.release()
                    except Exception:
                        pass

        raise RuntimeError(
            f"NebulaGraph request failed after {_MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    def _ensure_schema(self) -> None:
        """Create the graph space, tags, and edge types if needed."""
        session = self._get_session()
        try:
            # Create space
            session.execute(_SPACE_SCHEMA_NGQL.format(space=self._space))
            # NebulaGraph needs a few seconds for space creation to propagate
            time.sleep(1)

            # Create tag and edge type
            session.execute(_TAG_SCHEMA_NGQL.format(space=self._space))
            session.execute(_EDGE_SCHEMA_NGQL.format(space=self._space))
            time.sleep(1)

            logger.info("NebulaGraph schema ensured for space '%s'.", self._space)
        except Exception as exc:
            logger.error("Failed to ensure NebulaGraph schema: %s", exc)
            raise
        finally:
            session.release()

    # ---- GraphBackend ABC ------------------------------------------------

    def add_node(self, id: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Create or update a graph node (entity tag)."""
        props = properties or {}
        name = _escape_ngql(props.get("name", id))
        node_type = _escape_ngql(props.get("type", "unknown"))
        # Serialize remaining properties as JSON string
        import json
        extra = {k: v for k, v in props.items() if k not in ("name", "type")}
        props_str = _escape_ngql(json.dumps(extra, ensure_ascii=False)) if extra else ""
        created_at = int(props.get("created_at", int(time.time())))

        safe_id = _escape_ngql(id)
        ngql = (
            f'USE {self._space}; '
            f'INSERT VERTEX IF NOT EXISTS entity(name, type, properties, created_at) '
            f'VALUES "{safe_id}":("{name}", "{node_type}", "{props_str}", {created_at});'
        )
        self._execute(ngql)

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a directed edge between two nodes."""
        props = properties or {}
        import json
        extra = {k: v for k, v in props.items() if k not in ("relation", "weight")}
        weight = float(props.get("weight", 1.0))
        props_str = _escape_ngql(json.dumps(extra, ensure_ascii=False)) if extra else ""
        created_at = int(props.get("created_at", int(time.time())))
        safe_rel = _escape_ngql(relation)
        safe_src = _escape_ngql(source)
        safe_tgt = _escape_ngql(target)

        ngql = (
            f'USE {self._space}; '
            f'INSERT EDGE IF NOT EXISTS relates_to(relation, weight, properties, created_at) '
            f'VALUES "{safe_src}"->"{safe_tgt}":'
            f'("{safe_rel}", {weight}, "{props_str}", {created_at});'
        )
        self._execute(ngql)

    def query(self, cypher_or_dict: Any) -> List[Dict[str, Any]]:
        """Execute a raw nGQL query or dict-based filter.

        If *cypher_or_dict* is a string it is executed directly as an
        nGQL statement (after prepending ``USE <space>``).

        If it is a dict, a simple ``LOOKUP`` is constructed:
        * ``{"tag": "entity", "where": "name == 'foo'"}``
        """
        if isinstance(cypher_or_dict, str):
            ngql = f"USE {self._space}; {cypher_or_dict}"
        elif isinstance(cypher_or_dict, dict):
            tag = cypher_or_dict.get("tag", "entity")
            where = cypher_or_dict.get("where", "")
            if where:
                ngql = f"USE {self._space}; LOOKUP ON {tag} WHERE {where} YIELD id(vertex) AS vid;"
            else:
                ngql = f"USE {self._space}; LOOKUP ON {tag} YIELD id(vertex) AS vid;"
        else:
            raise TypeError(f"Expected str or dict, got {type(cypher_or_dict).__name__}")

        result = self._execute(ngql)
        return self._result_to_dicts(result)

    def get_neighbors(self, node_id: str, depth: int = 1) -> List[Dict[str, Any]]:
        """Return neighbours of *node_id* up to *depth* hops.

        Uses ``GO`` traversal on the ``relates_to`` edge type.
        """
        safe_id = _escape_ngql(node_id)
        ngql = (
            f'USE {self._space}; '
            f'GO {depth} STEPS FROM "{safe_id}" OVER relates_to '
            f'YIELD dst(edge) AS dst, properties(edge).relation AS relation, '
            f'properties(edge).weight AS weight, '
            f'properties($$).name AS dst_name;'
        )
        result = self._execute(ngql)
        return self._result_to_dicts(result)

    def delete_node(self, id: str) -> bool:
        """Delete a node and all incident edges."""
        safe_id = _escape_ngql(id)
        try:
            # Delete edges first (both directions)
            self._execute(
                f'USE {self._space}; '
                f'GO FROM "{safe_id}" OVER relates_to '
                f'YIELD src(edge) AS s, dst(edge) AS d '
                f'| DELETE EDGE relates_to $-.s -> $-.d;'
            )
            self._execute(
                f'USE {self._space}; '
                f'GO FROM "{safe_id}" OVER relates_to REVERSELY '
                f'YIELD src(edge) AS s, dst(edge) AS d '
                f'| DELETE EDGE relates_to $-.s -> $-.d;'
            )
            # Delete vertex
            self._execute(
                f'USE {self._space}; DELETE VERTEX "{safe_id}" WITH EDGE;'
            )
            return True
        except Exception:
            logger.warning("Failed to delete node %s", id, exc_info=True)
            return False

    def close(self) -> None:
        """Release all sessions and close the connection pool."""
        try:
            self._pool.close()
            logger.info("NebulaGraphBackend connection pool closed.")
        except Exception:
            pass

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _result_to_dicts(result) -> List[Dict[str, Any]]:
        """Convert a NebulaGraph ResultSet to a list of plain dicts."""
        rows: List[Dict[str, Any]] = []
        if result is None or not result.is_succeeded():
            return rows
        try:
            col_names = result.keys()
            for i in range(result.row_size()):
                row_values = result.row_values(i)
                row_dict: Dict[str, Any] = {}
                for j, col in enumerate(col_names):
                    val = row_values[j]
                    # NebulaGraph returns wrapped types; extract Python native
                    if hasattr(val, "as_string"):
                        try:
                            row_dict[col] = val.as_string()
                        except Exception:
                            row_dict[col] = str(val)
                    elif hasattr(val, "as_int"):
                        try:
                            row_dict[col] = val.as_int()
                        except Exception:
                            row_dict[col] = str(val)
                    elif hasattr(val, "as_double"):
                        try:
                            row_dict[col] = val.as_double()
                        except Exception:
                            row_dict[col] = str(val)
                    elif hasattr(val, "as_bool"):
                        try:
                            row_dict[col] = val.as_bool()
                        except Exception:
                            row_dict[col] = str(val)
                    else:
                        row_dict[col] = str(val)
                rows.append(row_dict)
        except Exception as exc:
            logger.warning("Failed to parse NebulaGraph result: %s", exc)
        return rows

    # ---- health ----------------------------------------------------------

    def health_check(self) -> bool:
        """Return ``True`` if NebulaGraph is reachable."""
        try:
            session = self._get_session()
            try:
                result = session.execute("SHOW SPACES;")
                return result.is_succeeded()
            finally:
                session.release()
        except Exception:
            return False
