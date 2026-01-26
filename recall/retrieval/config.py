"""检索配置模块 - Phase 3 核心配置类

提供类型安全的检索配置，支持 11 层检索器的完整配置。

设计原则：
1. 类型安全：使用 dataclass 替代 dict
2. 向后兼容：to_dict() 方法兼容旧 EightLayerRetriever
3. 预设模式：default/fast/accurate 三种预设
4. 环境变量支持：from_env() 工厂方法
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime


@dataclass
class LayerWeights:
    """各层权重配置
    
    用于多路召回时的分数加权融合。
    """
    inverted: float = 1.0      # L3 倒排索引权重
    entity: float = 1.2        # L4 实体索引权重
    graph: float = 1.0         # L5 图遍历权重
    ngram: float = 0.8         # L6 N-gram 权重
    vector: float = 1.0        # L7/L8 向量权重
    temporal: float = 0.5      # L2 时态权重


@dataclass
class TemporalContext:
    """时态查询上下文
    
    用于 L2 时态过滤层，指定时间范围约束。
    """
    start: Optional[datetime] = None    # 时间范围起点
    end: Optional[datetime] = None      # 时间范围终点
    reference: Optional[datetime] = None  # 参考时间点（用于图遍历时态过滤）
    
    def has_time_constraint(self) -> bool:
        """是否有时间约束"""
        return self.start is not None or self.end is not None


@dataclass
class LayerStats:
    """层级执行统计
    
    记录每层的输入输出数量和执行时间。
    """
    layer: str                  # 层名称（如 "L2_TEMPORAL_FILTER"）
    input_count: int            # 输入候选数
    output_count: int           # 输出候选数
    time_ms: float              # 耗时（毫秒）


@dataclass
class RetrievalResultItem:
    """检索结果项
    
    注意：此类与 eight_layer.py 中的 RetrievalResult 不同，
    这是简化版本，用于 ElevenLayerRetriever 返回值。
    """
    id: str                     # 文档 ID
    score: float                # 综合得分
    content: str = ""           # 文档内容（可选填充）
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    entities: List[str] = field(default_factory=list)  # 相关实体列表
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'score': self.score,
            'content': self.content,
            'metadata': self.metadata,
            'entities': self.entities
        }


@dataclass
class RetrievalConfig:
    """检索配置 - 类型安全 + 默认值
    
    配置 11 层检索器的所有参数。
    
    层级结构：
    - 快速过滤阶段：L1 Bloom, L2 Temporal
    - 召回阶段：L3 Inverted, L4 Entity, L5 Graph, L6 N-gram, L7 Vector
    - 精排阶段：L8 Vector Fine, L9 Rerank, L10 CrossEncoder, L11 LLM
    """
    
    # === 层开关（L1-L11）===
    l1_enabled: bool = True     # Bloom Filter
    l2_enabled: bool = True     # Temporal Filter【新增】
    l3_enabled: bool = True     # Inverted Index
    l4_enabled: bool = True     # Entity Index
    l5_enabled: bool = True     # Graph Traversal【新增】
    l6_enabled: bool = True     # N-gram Index
    l7_enabled: bool = True     # Vector Coarse
    l8_enabled: bool = True     # Vector Fine
    l9_enabled: bool = True     # Rerank
    l10_enabled: bool = False   # Cross-Encoder【新增，默认关闭】
    l11_enabled: bool = False   # LLM Filter【默认关闭】
    
    # === Top-K 配置 ===
    l2_temporal_top_k: int = 500       # 时态层保留数
    l3_inverted_top_k: int = 100       # 倒排索引保留数
    l4_entity_top_k: int = 50          # 实体索引保留数
    l5_graph_top_k: int = 100          # 图遍历保留数
    l6_ngram_top_k: int = 30           # N-gram 保留数
    l7_vector_top_k: int = 200         # 向量粗筛保留数
    fine_rank_threshold: int = 100     # 触发 L8 精排的候选数阈值
    l10_cross_encoder_top_k: int = 50  # CrossEncoder 处理数
    l11_llm_top_k: int = 20            # LLM 处理数
    final_top_k: int = 20              # 最终返回数
    
    # === L5 图遍历配置 ===
    l5_graph_max_depth: int = 2        # BFS 最大深度
    l5_graph_max_entities: int = 3     # 起始实体数量限制
    l5_graph_direction: str = "both"   # out | in | both
    
    # === L11 LLM 配置 ===
    l11_llm_timeout: float = 10.0      # 超时时间（秒）
    
    # === Phase 3.6: 并行三路召回配置（100%不遗忘保证）===
    parallel_recall_enabled: bool = True   # 启用并行三路召回
    rrf_k: int = 60                        # RRF 常数
    vector_weight: float = 1.0             # 语义召回权重
    keyword_weight: float = 1.2            # 关键词召回权重（100%召回，权重更高）
    entity_weight: float = 1.0             # 实体召回权重
    fallback_enabled: bool = True          # 启用原文兜底
    fallback_parallel: bool = True         # 并行兜底扫描
    fallback_workers: int = 4              # 兜底扫描线程数
    fallback_max_results: int = 50         # 兜底最大结果数
    
    # === 权重 ===
    weights: LayerWeights = field(default_factory=LayerWeights)
    
    # === 时态上下文（运行时设置）===
    reference_time: Optional[datetime] = None
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    
    @classmethod
    def default(cls) -> "RetrievalConfig":
        """默认配置 - L10/L11 关闭"""
        return cls()
    
    @classmethod
    def fast(cls) -> "RetrievalConfig":
        """快速模式 - 禁用重量级层"""
        return cls(
            l8_enabled=False,      # 跳过向量精排
            l9_enabled=False,      # 跳过重排序
            l10_enabled=False,     # 跳过 CrossEncoder
            l11_enabled=False,     # 跳过 LLM
            l7_vector_top_k=100
        )
    
    @classmethod
    def accurate(cls) -> "RetrievalConfig":
        """精准模式 - 启用所有层"""
        return cls(
            l10_enabled=True,      # 启用 CrossEncoder
            l11_enabled=True,      # 启用 LLM
            l7_vector_top_k=300,
            l10_cross_encoder_top_k=100
        )
    
    @classmethod
    def from_env(cls) -> "RetrievalConfig":
        """从环境变量构建配置"""
        def get_bool(key: str, default: bool) -> bool:
            return os.getenv(key, str(default)).lower() == 'true'
        
        def get_int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                return default
        
        def get_float(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, str(default)))
            except ValueError:
                return default
        
        return cls(
            # 层开关
            l1_enabled=get_bool('RETRIEVAL_L1_BLOOM_ENABLED', True),
            l2_enabled=get_bool('RETRIEVAL_L2_TEMPORAL_ENABLED', True),
            l3_enabled=get_bool('RETRIEVAL_L3_INVERTED_ENABLED', True),
            l4_enabled=get_bool('RETRIEVAL_L4_ENTITY_ENABLED', True),
            l5_enabled=get_bool('RETRIEVAL_L5_GRAPH_ENABLED', True),
            l6_enabled=get_bool('RETRIEVAL_L6_NGRAM_ENABLED', True),
            l7_enabled=get_bool('RETRIEVAL_L7_VECTOR_COARSE_ENABLED', True),
            l8_enabled=get_bool('RETRIEVAL_L8_VECTOR_FINE_ENABLED', True),
            l9_enabled=get_bool('RETRIEVAL_L9_RERANK_ENABLED', True),
            l10_enabled=get_bool('RETRIEVAL_L10_CROSS_ENCODER_ENABLED', False),
            l11_enabled=get_bool('RETRIEVAL_L11_LLM_ENABLED', False),
            # Top-K 配置
            l2_temporal_top_k=get_int('RETRIEVAL_L2_TEMPORAL_TOP_K', 500),
            l3_inverted_top_k=get_int('RETRIEVAL_L3_INVERTED_TOP_K', 100),
            l4_entity_top_k=get_int('RETRIEVAL_L4_ENTITY_TOP_K', 50),
            l5_graph_top_k=get_int('RETRIEVAL_L5_GRAPH_TOP_K', 100),
            l6_ngram_top_k=get_int('RETRIEVAL_L6_NGRAM_TOP_K', 30),
            l7_vector_top_k=get_int('RETRIEVAL_L7_VECTOR_TOP_K', 200),
            l10_cross_encoder_top_k=get_int('RETRIEVAL_L10_CROSS_ENCODER_TOP_K', 50),
            l11_llm_top_k=get_int('RETRIEVAL_L11_LLM_TOP_K', 20),
            # 阈值配置
            fine_rank_threshold=get_int('RETRIEVAL_FINE_RANK_THRESHOLD', 100),
            final_top_k=get_int('RETRIEVAL_FINAL_TOP_K', 20),
            # L5 图遍历配置
            l5_graph_max_depth=get_int('RETRIEVAL_L5_GRAPH_MAX_DEPTH', 2),
            l5_graph_max_entities=get_int('RETRIEVAL_L5_GRAPH_MAX_ENTITIES', 3),
            l5_graph_direction=os.getenv('RETRIEVAL_L5_GRAPH_DIRECTION', 'both'),
            # L11 LLM 配置
            l11_llm_timeout=get_float('RETRIEVAL_L11_LLM_TIMEOUT', 10.0),
            # Phase 3.6: 并行三路召回配置
            parallel_recall_enabled=get_bool('TRIPLE_RECALL_ENABLED', True),
            rrf_k=get_int('TRIPLE_RECALL_RRF_K', 60),
            vector_weight=get_float('TRIPLE_RECALL_VECTOR_WEIGHT', 1.0),
            keyword_weight=get_float('TRIPLE_RECALL_KEYWORD_WEIGHT', 1.2),
            entity_weight=get_float('TRIPLE_RECALL_ENTITY_WEIGHT', 1.0),
            fallback_enabled=get_bool('FALLBACK_ENABLED', True),
            fallback_parallel=get_bool('FALLBACK_PARALLEL', True),
            fallback_workers=get_int('FALLBACK_WORKERS', 4),
            fallback_max_results=get_int('FALLBACK_MAX_RESULTS', 50),
            # 权重配置
            weights=LayerWeights(
                inverted=get_float('RETRIEVAL_WEIGHT_INVERTED', 1.0),
                entity=get_float('RETRIEVAL_WEIGHT_ENTITY', 1.2),
                graph=get_float('RETRIEVAL_WEIGHT_GRAPH', 1.0),
                ngram=get_float('RETRIEVAL_WEIGHT_NGRAM', 0.8),
                vector=get_float('RETRIEVAL_WEIGHT_VECTOR', 1.0),
                temporal=get_float('RETRIEVAL_WEIGHT_TEMPORAL', 0.5),
            ),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（兼容旧 EightLayerRetriever）
        
        映射关系：
        - 旧 L1 = 新 L1 (Bloom)
        - 旧 L2 = 新 L3 (Inverted)
        - 旧 L3 = 新 L4 (Entity)
        - 旧 L4 = 新 L6 (N-gram)
        - 旧 L5 = 新 L7 (Vector Coarse)
        - 旧 L6 = 新 L8 (Vector Fine)
        - 旧 L7 = 新 L9 (Rerank)
        - 旧 L8 = 新 L11 (LLM)
        """
        return {
            'l1_enabled': self.l1_enabled,
            'l2_enabled': self.l3_enabled,   # 旧 L2 = 新 L3
            'l3_enabled': self.l4_enabled,   # 旧 L3 = 新 L4
            'l4_enabled': self.l6_enabled,   # 旧 L4 = 新 L6
            'l5_enabled': self.l7_enabled,   # 旧 L5 = 新 L7
            'l6_enabled': self.l8_enabled,   # 旧 L6 = 新 L8
            'l7_enabled': self.l9_enabled,   # 旧 L7 = 新 L9
            'l8_enabled': self.l11_enabled,  # 旧 L8 = 新 L11
            'l5_top_k': self.l7_vector_top_k,
            'l6_top_k': self.fine_rank_threshold,
            'l7_top_k': self.final_top_k,
            'l8_top_k': self.l11_llm_top_k,
            # Phase 3.6 配置
            'parallel_recall_enabled': self.parallel_recall_enabled,
            'rrf_k': self.rrf_k,
            'vector_weight': self.vector_weight,
            'keyword_weight': self.keyword_weight,
            'entity_weight': self.entity_weight,
            'fallback_enabled': self.fallback_enabled,
            'fallback_parallel': self.fallback_parallel,
            'fallback_workers': self.fallback_workers,
        }
    
    def with_temporal_context(self, temporal_context: TemporalContext) -> "RetrievalConfig":
        """创建带有时态上下文的配置副本"""
        import copy
        config = copy.copy(self)
        config.reference_time = temporal_context.reference
        config.time_range_start = temporal_context.start
        config.time_range_end = temporal_context.end
        return config


# 模块导出
__all__ = [
    'LayerWeights',
    'TemporalContext',
    'LayerStats',
    'RetrievalResultItem',
    'RetrievalConfig',
]
