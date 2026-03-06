"""
Recall v7.0 - Universal Document Chunker

Intelligently splits long text into indexable memory units.

Chunking strategies (auto-selected by data type):
- Conversations: by dialogue turn, each chunk = one complete turn
- Articles/web pages: by paragraph, large paragraphs split by token count
- Video transcripts: by timestamp segments (2-5 min per chunk)
- Structured data: by entry/record

Overlap strategy:
- Adjacent chunks overlap by last 2 sentences (~50-100 tokens)
- Ensures cross-chunk boundary semantics are preserved

Parent-child relationships:
- Each chunk records parent_id (original document ID)
- Search hits on chunks can expand to original text
- metadata: {parent_id, chunk_index, total_chunks, source_type}
"""

from __future__ import annotations

import re
import uuid
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Patterns for auto-detecting source type
_CONVERSATION_PATTERN = re.compile(
    r'(?:^|\n)\s*(?:User|AI|Assistant|Human|System|Bot)\s*[:：]',
    re.IGNORECASE,
)
_TRANSCRIPT_PATTERN = re.compile(
    r'\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]',
)
_JSON_LIKE_PATTERN = re.compile(
    r'^\s*[\[{]', re.MULTILINE,
)
_CSV_LIKE_PATTERN = re.compile(
    r'^[^\n]*(?:,|\t)[^\n]*\n[^\n]*(?:,|\t)', re.MULTILINE,
)

# Sentence-ending punctuation (English + CJK)
_SENTENCE_END = re.compile(r'(?<=[.!?。！？\n])\s*')

# CJK character range
_CJK_RANGE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uF900-\uFAFF]')


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    """Supported source types for chunking strategy selection."""
    AUTO = "auto"
    CONVERSATION = "conversation"
    TRANSCRIPT = "transcript"
    ARTICLE = "article"
    STRUCTURED = "structured"


@dataclass
class ChunkResult:
    """Represents a single chunk produced by the document chunker.

    Attributes:
        text: The chunk content.
        parent_id: ID of the original (parent) document.
        chunk_index: 0-based index of this chunk within the parent.
        total_chunks: Total number of chunks produced for the parent.
        source_type: Detected or specified source type.
        metadata: Arbitrary metadata passthrough + chunk-specific fields.
    """

    text: str
    parent_id: str
    chunk_index: int
    total_chunks: int
    source_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Token counting helpers
# ---------------------------------------------------------------------------

def _is_mostly_cjk(text: str, threshold: float = 0.3) -> bool:
    """Return True if *text* contains >= *threshold* fraction of CJK chars."""
    if not text:
        return False
    cjk_count = len(_CJK_RANGE.findall(text))
    return (cjk_count / len(text)) >= threshold


def _estimate_tokens(text: str) -> int:
    """Approximate token count.

    - English-like text: ``len(text.split())``
    - CJK-dominant text: ``len(text) // 2``
    """
    if _is_mostly_cjk(text):
        return max(1, len(text) // 2)
    return max(1, len(text.split()))


# ---------------------------------------------------------------------------
# Sentence splitting helper
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """Split *text* into sentences, preserving whitespace reasonably."""
    parts = _SENTENCE_END.split(text)
    return [s for s in parts if s.strip()]


def _last_n_sentences(text: str, n: int = 2) -> str:
    """Return the last *n* sentences of *text* (for overlap)."""
    sentences = _split_sentences(text)
    if len(sentences) <= n:
        return text
    return " ".join(sentences[-n:])


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def detect_source_type(text: str) -> SourceType:
    """Heuristically detect the source type of *text*.

    Priority order:
    1. Conversation (has ``User:/AI:`` style patterns)
    2. Transcript (has ``[HH:MM:SS]`` timestamps)
    3. Structured (JSON array/object or CSV/TSV rows)
    4. Article (default fallback – paragraph-based)
    """
    # Sample the first 2000 chars for speed
    sample = text[:2000]

    if _CONVERSATION_PATTERN.search(sample):
        return SourceType.CONVERSATION

    if _TRANSCRIPT_PATTERN.search(sample):
        return SourceType.TRANSCRIPT

    if _JSON_LIKE_PATTERN.search(sample):
        # Validate actual JSON structure
        try:
            obj = json.loads(text)
            if isinstance(obj, (list, dict)):
                return SourceType.STRUCTURED
        except (json.JSONDecodeError, ValueError):
            pass

    if _CSV_LIKE_PATTERN.search(sample):
        return SourceType.STRUCTURED

    return SourceType.ARTICLE


# ---------------------------------------------------------------------------
# Splitting strategies
# ---------------------------------------------------------------------------

def _split_conversation(text: str) -> List[str]:
    """Split by dialogue turn boundaries."""
    # Match turn headers like "User:", "AI:", "Assistant:", etc.
    turn_pattern = re.compile(
        r'(?=(?:^|\n)\s*(?:User|AI|Assistant|Human|System|Bot)\s*[:：])',
        re.IGNORECASE,
    )
    parts = turn_pattern.split(text)
    segments = [p.strip() for p in parts if p.strip()]
    return segments if segments else [text]


def _split_transcript(text: str) -> List[str]:
    """Split by timestamp segments, grouping into 2-5 minute windows."""
    # Parse timestamps
    ts_pattern = re.compile(
        r'\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]'
    )

    lines = text.split('\n')
    segments: List[str] = []
    current_segment: List[str] = []
    segment_start_seconds: Optional[int] = None

    for line in lines:
        match = ts_pattern.search(line)
        if match:
            h_or_m = int(match.group(1))
            m_or_s = int(match.group(2))
            s = int(match.group(3)) if match.group(3) else 0
            # Determine if HH:MM:SS or MM:SS
            if match.group(3) is not None:
                total_seconds = h_or_m * 3600 + m_or_s * 60 + s
            else:
                total_seconds = h_or_m * 60 + m_or_s

            if segment_start_seconds is None:
                segment_start_seconds = total_seconds

            # If >= 3 minutes (180s) have elapsed, start new segment
            elapsed = total_seconds - segment_start_seconds
            if elapsed >= 180 and current_segment:
                segments.append('\n'.join(current_segment))
                current_segment = []
                segment_start_seconds = total_seconds

        current_segment.append(line)

    if current_segment:
        segments.append('\n'.join(current_segment))

    return segments if segments else [text]


def _split_structured(text: str) -> List[str]:
    """Split structured data by entry/record."""
    text_stripped = text.strip()

    # JSON array → one chunk per element
    if text_stripped.startswith('['):
        try:
            arr = json.loads(text_stripped)
            if isinstance(arr, list) and len(arr) > 1:
                return [json.dumps(item, ensure_ascii=False, indent=2) for item in arr]
        except (json.JSONDecodeError, ValueError):
            pass

    # JSON object → one chunk per top-level key
    if text_stripped.startswith('{'):
        try:
            obj = json.loads(text_stripped)
            if isinstance(obj, dict) and len(obj) > 1:
                return [
                    json.dumps({k: v}, ensure_ascii=False, indent=2)
                    for k, v in obj.items()
                ]
        except (json.JSONDecodeError, ValueError):
            pass

    # CSV/TSV → group rows (header + N data rows per chunk)
    lines = text_stripped.split('\n')
    if len(lines) > 2:
        header = lines[0]
        rows_per_chunk = 20
        chunks = []
        for i in range(1, len(lines), rows_per_chunk):
            batch = [header] + lines[i:i + rows_per_chunk]
            chunks.append('\n'.join(batch))
        return chunks

    return [text]


def _split_article(text: str) -> List[str]:
    """Split by paragraph (double newline), keeping single-newline groups."""
    paragraphs = re.split(r'\n\s*\n', text)
    return [p.strip() for p in paragraphs if p.strip()]


# ---------------------------------------------------------------------------
# Core: enforce token limits with overlap
# ---------------------------------------------------------------------------

def _enforce_token_limit(
    segments: List[str],
    max_chunk_tokens: int,
    overlap_tokens: int,
) -> List[str]:
    """Ensure each segment fits within *max_chunk_tokens*.

    Large segments are further split at sentence boundaries.
    Adjacent chunks are given overlap from the end of the prior chunk.
    """
    result: List[str] = []

    for segment in segments:
        if _estimate_tokens(segment) <= max_chunk_tokens:
            result.append(segment)
        else:
            # Sub-split at sentence boundaries
            sentences = _split_sentences(segment)
            current: List[str] = []
            current_tokens = 0

            for sent in sentences:
                sent_tokens = _estimate_tokens(sent)
                if current and (current_tokens + sent_tokens) > max_chunk_tokens:
                    result.append(' '.join(current))
                    current = []
                    current_tokens = 0
                current.append(sent)
                current_tokens += sent_tokens

            if current:
                result.append(' '.join(current))

    # Apply overlap between adjacent chunks
    if overlap_tokens > 0 and len(result) > 1:
        overlapped: List[str] = [result[0]]
        for i in range(1, len(result)):
            overlap_text = _last_n_sentences(result[i - 1], n=2)
            if _estimate_tokens(overlap_text) > overlap_tokens:
                # Trim the overlap to ~overlap_tokens
                words = overlap_text.split()
                overlap_text = ' '.join(words[-overlap_tokens:])
            combined = overlap_text + '\n' + result[i]
            # Only add overlap if it doesn't exceed limit too much
            if _estimate_tokens(combined) <= max_chunk_tokens * 1.15:
                overlapped.append(combined)
            else:
                overlapped.append(result[i])
        result = overlapped

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk(
    text: str,
    *,
    source_type: str = 'auto',
    max_chunk_tokens: int = 512,
    overlap_tokens: int = 64,
    parent_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[ChunkResult]:
    """Split *text* into indexable memory chunks.

    Parameters
    ----------
    text : str
        The full document / input text to chunk.
    source_type : str
        One of ``'auto'``, ``'conversation'``, ``'transcript'``,
        ``'article'``, ``'structured'``.  When ``'auto'``, the type is
        detected heuristically from content patterns.
    max_chunk_tokens : int
        Maximum approximate token count per chunk (default 512).
    overlap_tokens : int
        Number of overlap tokens between adjacent chunks (default 64).
    parent_id : str, optional
        ID for the parent document.  Auto-generated if not provided.
    metadata : dict, optional
        Extra metadata to attach to every chunk (passthrough).

    Returns
    -------
    list[ChunkResult]
        Ordered list of chunks with parent-child metadata.
    """
    if not text or not text.strip():
        return []

    # Resolve parent_id
    pid = parent_id or f"doc_{uuid.uuid4().hex[:12]}"

    # Resolve source type
    if source_type == 'auto' or source_type == SourceType.AUTO:
        detected = detect_source_type(text)
    else:
        try:
            detected = SourceType(source_type)
        except ValueError:
            detected = SourceType.ARTICLE

    # Strategy dispatch
    if detected == SourceType.CONVERSATION:
        raw_segments = _split_conversation(text)
    elif detected == SourceType.TRANSCRIPT:
        raw_segments = _split_transcript(text)
    elif detected == SourceType.STRUCTURED:
        raw_segments = _split_structured(text)
    else:
        raw_segments = _split_article(text)

    # If the whole text fits in one chunk, return as-is
    if len(raw_segments) == 1 and _estimate_tokens(raw_segments[0]) <= max_chunk_tokens:
        base_meta = dict(metadata) if metadata else {}
        base_meta.update({
            'parent_id': pid,
            'chunk_index': 0,
            'total_chunks': 1,
            'source_type': detected.value,
        })
        return [
            ChunkResult(
                text=raw_segments[0].strip(),
                parent_id=pid,
                chunk_index=0,
                total_chunks=1,
                source_type=detected.value,
                metadata=base_meta,
            )
        ]

    # Enforce token limits and add overlap
    final_segments = _enforce_token_limit(raw_segments, max_chunk_tokens, overlap_tokens)

    # Build results
    total = len(final_segments)
    results: List[ChunkResult] = []
    for idx, seg in enumerate(final_segments):
        chunk_meta = dict(metadata) if metadata else {}
        chunk_meta.update({
            'parent_id': pid,
            'chunk_index': idx,
            'total_chunks': total,
            'source_type': detected.value,
        })
        results.append(
            ChunkResult(
                text=seg.strip(),
                parent_id=pid,
                chunk_index=idx,
                total_chunks=total,
                source_type=detected.value,
                metadata=chunk_meta,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Convenience: check if text needs chunking
# ---------------------------------------------------------------------------

def needs_chunking(text: str, max_chunk_tokens: int = 512) -> bool:
    """Return True if *text* would be split into multiple chunks."""
    return _estimate_tokens(text) > max_chunk_tokens
