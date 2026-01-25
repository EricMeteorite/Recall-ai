"""索引层模块"""

from .entity_index import EntityIndex, IndexedEntity
from .inverted_index import InvertedIndex
from .vector_index import VectorIndex
from .ngram_index import OptimizedNgramIndex

# v4.0 新增: 时态索引与全文索引
from .temporal_index import TemporalIndex, TemporalEntry, TimeRange
from .fulltext_index import FullTextIndex, BM25Config

# v4.0 Phase 3.5: FAISS IVF 磁盘索引（可选，大规模场景）
from .vector_index_ivf import VectorIndexIVF

__all__ = [
    # v3 原有导出（保持向后兼容）
    'EntityIndex',
    'IndexedEntity',
    'InvertedIndex',
    'VectorIndex',
    'OptimizedNgramIndex',
    
    # v4.0 新增导出
    'TemporalIndex',
    'TemporalEntry',
    'TimeRange',
    'FullTextIndex',
    'BM25Config',
    
    # v4.0 Phase 3.5: 企业级向量索引
    'VectorIndexIVF',
]
