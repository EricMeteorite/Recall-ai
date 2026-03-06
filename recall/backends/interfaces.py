"""Recall v7.0 - Backend Abstraction Layer (BAL) Interfaces

This module defines the abstract base classes for all pluggable backends
in the Recall system. Each interface captures the minimal contract that
concrete implementations must fulfil, enabling zero-friction backend
swaps (e.g. JSON -> Kuzu, HNSW -> IVF, local -> cloud embeddings).

Interfaces (7 backends + 2 services):
    VectorBackend      – dense vector similarity search
    TextSearchBackend  – full-text / BM25 search
    KeywordBackend     – inverted-index keyword lookup
    GraphBackend       – knowledge-graph storage & traversal
    StorageBackend     – generic key-value / document persistence
    TemporalBackend    – time-range indexed storage
    EpisodeBackend     – episodic turn / conversation storage
    EmbeddingService   – text -> vector encoding (service)
    TenantRouter       – multi-tenant scope resolution (service)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Shared data classes
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """Unified search result returned by search-capable backends.

    Attributes:
        id: Unique identifier of the matched item.
        score: Relevance / similarity score (higher is better).
        metadata: Arbitrary metadata attached to the item.
        text: Optional textual content of the item.
    """

    id: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    text: Optional[str] = None


@dataclass
class StorageScope:
    """Identifies a tenant-scoped storage partition.

    Attributes:
        user_id: Primary user identifier.
        session_id: Session or conversation identifier.
        character_id: Optional character / persona identifier.
    """

    user_id: str
    session_id: str = "default"
    character_id: str = "default"

    def to_path(self) -> str:
        """Return a filesystem-friendly relative path for this scope."""
        return f"{self.user_id}/{self.character_id}/{self.session_id}"


# ---------------------------------------------------------------------------
# 1. VectorBackend
# ---------------------------------------------------------------------------

class VectorBackend(ABC):
    """Abstract interface for dense-vector similarity search.

    Unifies ``VectorIndex`` (HNSW) and ``VectorIndexIVF`` (FAISS IVF)
    behind a single contract.
    """

    @abstractmethod
    def add(self, id: str, vector: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        """Insert or update a vector.

        Args:
            id: Unique document / memory identifier.
            vector: Dense embedding vector.
            metadata: Optional metadata to store alongside the vector.
        """

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Find the nearest neighbours of *query_vector*.

        Args:
            query_vector: The query embedding.
            top_k: Maximum number of results to return.
            filters: Optional metadata filters.

        Returns:
            Ranked list of :class:`SearchResult` (descending by score).
        """

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Remove a vector by id.

        Returns:
            ``True`` if the item existed and was removed.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the total number of indexed vectors."""

    @abstractmethod
    def rebuild(self) -> None:
        """Rebuild / optimise the index (e.g. re-cluster IVF centroids)."""


# ---------------------------------------------------------------------------
# 2. TextSearchBackend
# ---------------------------------------------------------------------------

class TextSearchBackend(ABC):
    """Abstract interface for full-text / BM25 search."""

    @abstractmethod
    def add(self, id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Index a document for full-text search.

        Args:
            id: Unique document identifier.
            text: Textual content to index.
            metadata: Optional metadata.
        """

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Execute a full-text search query.

        Args:
            query: Natural language or keyword query string.
            top_k: Maximum number of results.
            filters: Optional metadata filters.

        Returns:
            Ranked list of :class:`SearchResult`.
        """

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Remove a document from the full-text index.

        Returns:
            ``True`` if the item existed and was removed.
        """


# ---------------------------------------------------------------------------
# 3. KeywordBackend
# ---------------------------------------------------------------------------

class KeywordBackend(ABC):
    """Abstract interface for keyword / inverted-index lookup.

    Maps individual keywords to document ids, supporting both
    AND (``search_all``) and OR (``search_any``) semantics.
    """

    @abstractmethod
    def add(self, id: str, keywords: Sequence[str]) -> None:
        """Associate *keywords* with a document.

        Args:
            id: Document / memory identifier.
            keywords: Iterable of keyword strings to index.
        """

    @abstractmethod
    def search(self, keywords: Sequence[str], top_k: int = 50) -> List[str]:
        """Return document ids matching **any** of the given keywords.

        Args:
            keywords: Keywords to look up.
            top_k: Maximum number of ids to return.

        Returns:
            List of matching document ids.
        """

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Remove all keyword associations for a document.

        Returns:
            ``True`` if the item existed and was removed.
        """


# ---------------------------------------------------------------------------
# 4. GraphBackend
# ---------------------------------------------------------------------------

class GraphBackend(ABC):
    """Abstract interface for knowledge-graph storage and traversal.

    Unifies JSON-file, Kuzu, and future Neo4j graph backends behind a
    consistent API.
    """

    @abstractmethod
    def add_node(self, id: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Create or update a graph node.

        Args:
            id: Unique node identifier.
            properties: Arbitrary key-value properties for the node.
        """

    @abstractmethod
    def add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a directed edge between two nodes.

        Args:
            source: Source node id.
            target: Target node id.
            relation: Edge / relationship type label.
            properties: Arbitrary key-value properties for the edge.
        """

    @abstractmethod
    def query(self, cypher_or_dict: Any) -> List[Dict[str, Any]]:
        """Execute a backend-specific query.

        For Cypher-capable backends this can be a Cypher string; for
        simpler backends a dict-based filter is accepted.

        Args:
            cypher_or_dict: Query expression (backend-dependent).

        Returns:
            List of result dicts.
        """

    @abstractmethod
    def get_neighbors(self, node_id: str, depth: int = 1) -> List[Dict[str, Any]]:
        """Return neighbours of *node_id* up to a given traversal depth.

        Args:
            node_id: Starting node.
            depth: Maximum hop distance (default 1).

        Returns:
            List of neighbour dicts containing node and edge information.
        """

    @abstractmethod
    def delete_node(self, id: str) -> bool:
        """Delete a node and all its incident edges.

        Returns:
            ``True`` if the node existed and was removed.
        """

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the backend (connections, files)."""


# ---------------------------------------------------------------------------
# 5. StorageBackend
# ---------------------------------------------------------------------------

class StorageBackend(ABC):
    """Abstract interface for generic key-value / document persistence.

    Provides simple CRUD operations used by memory consolidation,
    working-memory, and volume managers.
    """

    @abstractmethod
    def save(self, id: str, data: Dict[str, Any]) -> None:
        """Persist a JSON-serialisable document.

        Args:
            id: Unique document identifier.
            data: Serialisable data payload.
        """

    @abstractmethod
    def load(self, id: str) -> Optional[Dict[str, Any]]:
        """Load a document by id.

        Returns:
            The stored data dict, or ``None`` if not found.
        """

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Delete a document.

        Returns:
            ``True`` if the item existed and was removed.
        """

    @abstractmethod
    def list(self, prefix: str = "") -> List[str]:
        """List document ids, optionally filtered by prefix.

        Args:
            prefix: Only return ids starting with this string.

        Returns:
            List of matching document ids.
        """

    @abstractmethod
    def exists(self, id: str) -> bool:
        """Check whether a document exists.

        Returns:
            ``True`` if the document is present.
        """


# ---------------------------------------------------------------------------
# 6. TemporalBackend
# ---------------------------------------------------------------------------

class TemporalBackend(ABC):
    """Abstract interface for time-range indexed storage.

    Allows efficient querying of memories by timestamp ranges,
    supporting temporal reasoning features.
    """

    @abstractmethod
    def add(self, id: str, timestamp: datetime, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Index an item with a timestamp.

        Args:
            id: Unique item identifier.
            timestamp: The point-in-time associated with this item.
            metadata: Optional additional metadata.
        """

    @abstractmethod
    def query_range(
        self,
        start: datetime,
        end: datetime,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return items whose timestamp falls within [start, end].

        Args:
            start: Inclusive range start.
            end: Inclusive range end.
            filters: Optional metadata filters.

        Returns:
            List of matching item dicts (including id, timestamp, metadata).
        """

    @abstractmethod
    def delete(self, id: str) -> bool:
        """Remove an item from the temporal index.

        Returns:
            ``True`` if the item existed and was removed.
        """


# ---------------------------------------------------------------------------
# 7. EpisodeBackend
# ---------------------------------------------------------------------------

class EpisodeBackend(ABC):
    """Abstract interface for episode / conversation-turn storage.

    Episodes capture raw interaction turns before they are consolidated
    into long-term memories.
    """

    @abstractmethod
    def add_episode(self, episode: Dict[str, Any]) -> str:
        """Store a new episode.

        Args:
            episode: Episode data dict (must contain at minimum a
                ``user_id`` key; an ``id`` will be generated if absent).

        Returns:
            The episode id (generated or provided).
        """

    @abstractmethod
    def get_episode(self, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single episode by id.

        Returns:
            The episode dict, or ``None`` if not found.
        """

    @abstractmethod
    def list_episodes(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """List recent episodes for a user.

        Args:
            user_id: The user to filter by.
            limit: Maximum number of episodes to return.

        Returns:
            List of episode dicts, most-recent first.
        """

    @abstractmethod
    def delete_episode(self, id: str) -> bool:
        """Delete an episode.

        Returns:
            ``True`` if the episode existed and was removed.
        """


# ---------------------------------------------------------------------------
# Service: EmbeddingService
# ---------------------------------------------------------------------------

class EmbeddingService(ABC):
    """Abstract interface for text-to-vector encoding.

    Unlike the backend interfaces, this is a *stateless service* –
    it does not own any persistent storage.  Wraps local
    sentence-transformers, OpenAI, SiliconFlow, or any future provider.
    """

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Encode a single text string into a dense vector.

        Args:
            text: Input text.

        Returns:
            Embedding vector as a list of floats.
        """

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Encode multiple texts in a single call.

        Args:
            texts: List of input strings.

        Returns:
            List of embedding vectors (same order as input).
        """

    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of produced embeddings."""


# ---------------------------------------------------------------------------
# Service: TenantRouter
# ---------------------------------------------------------------------------

class TenantRouter(ABC):
    """Abstract interface for multi-tenant scope resolution.

    Maps user identifiers to :class:`StorageScope` instances and
    manages tenant lifecycle.
    """

    @abstractmethod
    def get_scope(self, user_id: str, session_id: str = "default", character_id: str = "default") -> StorageScope:
        """Resolve a storage scope for the given identifiers.

        Args:
            user_id: Primary user identifier.
            session_id: Session / conversation id.
            character_id: Character / persona id.

        Returns:
            A :class:`StorageScope` instance.
        """

    @abstractmethod
    def list_users(self) -> List[str]:
        """Return all known user ids."""

    @abstractmethod
    def delete_user(self, user_id: str) -> bool:
        """Delete all data associated with a user.

        Returns:
            ``True`` if the user existed and was removed.
        """
