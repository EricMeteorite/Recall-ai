"""检索层

模块结构：
- eight_layer: 原 8 层检索器（向后兼容）
- eleven_layer: 新 11 层检索器（Phase 3）
- config: 检索配置类
- context_builder: 上下文构建器
- parallel_retrieval: 并行检索器
- rrf_fusion: RRF 融合算法（Phase 3.6）
"""

# 原有模块（向后兼容）
from .eight_layer import EightLayerRetriever, RetrievalResult, RetrievalLayer
from .context_builder import ContextBuilder, BuiltContext
from .parallel_retrieval import ParallelRetriever, RetrievalTask

# Phase 3 新模块
from .config import (
    RetrievalConfig, LayerWeights, TemporalContext, 
    LayerStats, RetrievalResultItem
)
from .eleven_layer import (
    ElevenLayerRetriever, EightLayerRetrieverCompat,
    RetrievalLayer as ElevenLayerRetrievalLayer
)

# Phase 3.6 新模块：RRF 融合
from .rrf_fusion import reciprocal_rank_fusion, weighted_score_fusion

__all__ = [
    # 原有导出（向后兼容）
    'EightLayerRetriever',
    'RetrievalResult',
    'RetrievalLayer',
    'ContextBuilder',
    'BuiltContext',
    'ParallelRetriever',
    'RetrievalTask',
    # Phase 3 新导出
    'RetrievalConfig',
    'LayerWeights',
    'TemporalContext',
    'LayerStats',
    'RetrievalResultItem',
    'ElevenLayerRetriever',
    'EightLayerRetrieverCompat',
    'ElevenLayerRetrievalLayer',
    # Phase 3.6 新导出：RRF 融合
    'reciprocal_rank_fusion',
    'weighted_score_fusion',
]
