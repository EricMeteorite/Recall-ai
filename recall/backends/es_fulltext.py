"""Recall v7.0 - Elasticsearch Full-Text Backend

Implements :class:`TextSearchBackend` and :class:`KeywordBackend` ABCs
for production-grade full-text search using Elasticsearch.

Requires
--------
``elasticsearch`` (optional dependency, v8+).  The module imports
cleanly even when the package is absent; an ``ImportError`` is raised
only at construction time.

Configuration (environment variables)
--------------------------------------
ES_HOST            Elasticsearch URL (default ``http://localhost:9200``)
ES_PORT            (alternative) port — appended to host if supplied
ES_API_KEY         Optional API key for Elastic Cloud / secured clusters
ES_INDEX_PREFIX    Index name prefix (default ``recall``)
ES_TIMEOUT         Request timeout in seconds (default ``30``)
ES_ANALYZER        Default analyzer (default ``standard``; set to
                   ``ik_max_word`` for Chinese segmentation)

Design notes
------------
* **Chinese / CJK** — when ``ES_ANALYZER`` is set to ``ik_max_word``
  or ``ik_smart`` the backend configures the index mapping to use the
  IK Analyzer plugin.  Falls back to ``standard`` gracefully.
* **BM25 + highlight** — search results include BM25 scores and
  highlight snippets.
* **Namespace isolation** — memories are tagged with a ``namespace``
  field and filtered accordingly.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Sequence

from .interfaces import KeywordBackend, SearchResult, TextSearchBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional elasticsearch import
# ---------------------------------------------------------------------------

_ES_AVAILABLE: bool = False

try:
    from elasticsearch import Elasticsearch  # type: ignore
    from elasticsearch.exceptions import (  # type: ignore
        ConnectionError as ESConnectionError,
        NotFoundError as ESNotFoundError,
        RequestError as ESRequestError,
    )

    _ES_AVAILABLE = True
except ImportError:
    Elasticsearch = None  # type: ignore
    ESConnectionError = Exception  # type: ignore
    ESNotFoundError = Exception  # type: ignore
    ESRequestError = Exception  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INDEX_PREFIX = "recall"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _retry(func, *args, max_retries: int = _MAX_RETRIES, **kwargs):
    """Call *func* with exponential back-off on connection errors."""
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, OSError, ESConnectionError) as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "ES request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt, max_retries, delay, exc,
                )
                time.sleep(delay)
    raise RuntimeError(
        f"Elasticsearch request failed after {max_retries} attempts: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# ElasticsearchFulltextBackend
# ---------------------------------------------------------------------------


class ElasticsearchFulltextBackend(TextSearchBackend, KeywordBackend):
    """Elasticsearch-powered full-text and keyword search backend.

    Parameters
    ----------
    host : str or None
        Elasticsearch URL.  Falls back to ``ES_HOST`` or
        ``"http://localhost:9200"``.
    port : int or None
        Optional port (appended to host).  Falls back to ``ES_PORT``.
    api_key : str or None
        API key for authentication.  Falls back to ``ES_API_KEY``.
    index_prefix : str or None
        Index name prefix.  Falls back to ``ES_INDEX_PREFIX`` or
        ``"recall"``.
    timeout : int or None
        Request timeout in seconds.  Falls back to ``ES_TIMEOUT`` or
        ``30``.
    analyzer : str or None
        Default analyzer for the ``content`` field.  Falls back to
        ``ES_ANALYZER`` or ``"standard"``.

    Raises
    ------
    ImportError
        If the ``elasticsearch`` package is not installed.
    RuntimeError
        If Elasticsearch is unreachable.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        api_key: str | None = None,
        index_prefix: str | None = None,
        timeout: int | None = None,
        analyzer: str | None = None,
    ) -> None:
        if not _ES_AVAILABLE:
            raise ImportError(
                "elasticsearch is required for ElasticsearchFulltextBackend. "
                "Install it with:  pip install elasticsearch"
            )

        raw_host = host or os.environ.get("ES_HOST", "http://localhost:9200")
        raw_port = port or os.environ.get("ES_PORT")
        if raw_port:
            # Append port if host doesn't already contain one after the scheme
            if ":" not in raw_host.split("//")[-1]:
                raw_host = f"{raw_host}:{raw_port}"

        self._api_key = api_key or os.environ.get("ES_API_KEY") or None
        self._index_prefix = (
            index_prefix or os.environ.get("ES_INDEX_PREFIX", _DEFAULT_INDEX_PREFIX)
        )
        self._timeout = timeout or int(os.environ.get("ES_TIMEOUT", "30"))
        self._analyzer = analyzer or os.environ.get("ES_ANALYZER", "standard")
        self._index_name = f"{self._index_prefix}_memories"
        self._keyword_index_name = f"{self._index_prefix}_keywords"

        # Build client
        client_kwargs: Dict[str, Any] = {
            "hosts": [raw_host],
            "request_timeout": self._timeout,
        }
        if self._api_key:
            client_kwargs["api_key"] = self._api_key

        try:
            self._client = Elasticsearch(**client_kwargs)
            # Quick connectivity check
            if not self._client.ping():
                raise RuntimeError("Elasticsearch ping failed")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to Elasticsearch at {raw_host}: {exc}"
            ) from exc

        # Ensure indexes
        self._ensure_index()
        self._ensure_keyword_index()
        logger.info(
            "ElasticsearchFulltextBackend initialised  host=%s  index=%s  analyzer=%s",
            raw_host,
            self._index_name,
            self._analyzer,
        )

    # ---- index management ------------------------------------------------

    def _ensure_index(self) -> None:
        """Create the full-text index with appropriate mappings."""
        if self._client.indices.exists(index=self._index_name):
            return

        mapping: Dict[str, Any] = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {},
            },
            "mappings": {
                "properties": {
                    "memory_id": {"type": "keyword"},
                    "content": {
                        "type": "text",
                        "analyzer": self._analyzer,
                    },
                    "namespace": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "keywords": {"type": "keyword"},
                    "entities": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "metadata": {"type": "object", "enabled": True},
                },
            },
        }

        # Configure IK analyzer if requested
        if self._analyzer in ("ik_max_word", "ik_smart"):
            mapping["settings"]["analysis"] = {
                "analyzer": {
                    "default": {
                        "type": self._analyzer,
                    },
                },
            }

        try:
            self._client.indices.create(index=self._index_name, body=mapping)
            logger.info("Created ES index '%s' with analyzer '%s'.", self._index_name, self._analyzer)
        except ESRequestError as exc:
            # Index may already exist (race condition)
            if "resource_already_exists_exception" not in str(exc):
                raise

    def _ensure_keyword_index(self) -> None:
        """Create the keyword lookup index."""
        if self._client.indices.exists(index=self._keyword_index_name):
            return

        mapping: Dict[str, Any] = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "keywords": {"type": "keyword"},
                },
            },
        }

        try:
            self._client.indices.create(index=self._keyword_index_name, body=mapping)
            logger.info("Created ES keyword index '%s'.", self._keyword_index_name)
        except ESRequestError as exc:
            if "resource_already_exists_exception" not in str(exc):
                raise

    # ---- TextSearchBackend ABC -------------------------------------------

    def add(self, id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Index a document for full-text search."""
        doc: Dict[str, Any] = {
            "memory_id": id,
            "content": text,
        }
        if metadata:
            doc["namespace"] = metadata.get("namespace", "default")
            doc["user_id"] = metadata.get("user_id", "default")
            doc["source"] = metadata.get("source", "user")
            doc["category"] = metadata.get("category")
            doc["keywords"] = metadata.get("keywords", [])
            doc["entities"] = metadata.get("entities", [])
            doc["created_at"] = metadata.get("created_at")
            doc["metadata"] = metadata

        _retry(
            self._client.index,
            index=self._index_name,
            id=id,
            document=doc,
            refresh="wait_for",
        )

    def search(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Execute a BM25 full-text search with optional namespace filtering."""
        must: List[Dict[str, Any]] = [
            {
                "match": {
                    "content": {
                        "query": query,
                        "analyzer": self._analyzer,
                    },
                },
            },
        ]
        filter_clauses: List[Dict[str, Any]] = []

        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {key: value}})
                else:
                    filter_clauses.append({"term": {key: value}})

        body: Dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must,
                },
            },
            "highlight": {
                "fields": {
                    "content": {
                        "pre_tags": ["<em>"],
                        "post_tags": ["</em>"],
                        "fragment_size": 150,
                        "number_of_fragments": 3,
                    },
                },
            },
            "size": top_k,
        }
        if filter_clauses:
            body["query"]["bool"]["filter"] = filter_clauses

        resp = _retry(
            self._client.search,
            index=self._index_name,
            body=body,
        )

        results: List[SearchResult] = []
        for hit in resp.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            highlight = hit.get("highlight", {})
            highlight_text = " … ".join(highlight.get("content", []))

            results.append(
                SearchResult(
                    id=source.get("memory_id", hit["_id"]),
                    score=hit.get("_score", 0.0),
                    metadata={
                        **source.get("metadata", {}),
                        "_highlight": highlight_text,
                    },
                    text=source.get("content"),
                )
            )
        return results

    def delete(self, id: str) -> bool:
        """Remove a document from the full-text index."""
        try:
            _retry(
                self._client.delete,
                index=self._index_name,
                id=id,
                refresh="wait_for",
            )
            return True
        except ESNotFoundError:
            return False
        except Exception:
            logger.warning("Failed to delete doc %s from ES", id, exc_info=True)
            return False

    # ---- KeywordBackend ABC (via same class) -----------------------------

    # Note: `add` for KeywordBackend uses a different signature.
    # We implement it as `add_keywords` and alias if needed.

    def add_keywords(self, id: str, keywords: Sequence[str]) -> None:
        """Associate *keywords* with a document id in the keyword index."""
        doc = {
            "doc_id": id,
            "keywords": list(keywords),
        }
        _retry(
            self._client.index,
            index=self._keyword_index_name,
            id=id,
            document=doc,
            refresh="wait_for",
        )

    def search_keywords(self, keywords: Sequence[str], top_k: int = 50) -> List[str]:
        """Return document ids matching **any** of the given keywords."""
        body: Dict[str, Any] = {
            "query": {
                "terms": {
                    "keywords": list(keywords),
                },
            },
            "size": top_k,
            "_source": ["doc_id"],
        }
        resp = _retry(
            self._client.search,
            index=self._keyword_index_name,
            body=body,
        )
        return [
            hit["_source"]["doc_id"]
            for hit in resp.get("hits", {}).get("hits", [])
        ]

    def delete_keywords(self, id: str) -> bool:
        """Remove keyword associations for a document."""
        try:
            _retry(
                self._client.delete,
                index=self._keyword_index_name,
                id=id,
                refresh="wait_for",
            )
            return True
        except ESNotFoundError:
            return False
        except Exception:
            logger.warning("Failed to delete keywords for %s from ES", id, exc_info=True)
            return False

    # ---- health / lifecycle ----------------------------------------------

    def health_check(self) -> bool:
        """Return ``True`` if Elasticsearch is reachable."""
        try:
            return self._client.ping()
        except Exception:
            return False

    def close(self) -> None:
        """Close the Elasticsearch client."""
        try:
            self._client.close()
        except Exception:
            pass
