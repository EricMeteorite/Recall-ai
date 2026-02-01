"""图谱层模块

v4.0 统一图谱架构：
- KnowledgeGraph 现在是 TemporalKnowledgeGraph 的别名（向后兼容）
- 所有图数据存储在统一的 TemporalKnowledgeGraph 中
- 支持 file 和 kuzu 两种存储后端
"""

# v4.0: 时态知识图谱（统一图谱）
from .temporal_knowledge_graph import TemporalKnowledgeGraph, KUZU_AVAILABLE
from .relation_extractor import RelationExtractor

# 向后兼容：KnowledgeGraph 作为 TemporalKnowledgeGraph 的别名
# 保留老的 Relation 类供兼容使用
from .knowledge_graph import Relation
KnowledgeGraph = TemporalKnowledgeGraph  # 别名，保持向后兼容

# v4.0 新增: 矛盾管理
from .contradiction_manager import ContradictionManager, DetectionStrategy, ContradictionRecord

# v4.0 Phase 3.5: 企业级性能引擎
from .query_planner import QueryPlanner, QueryPlan, QueryOperation
from .community_detector import CommunityDetector, Community

# v4.0 Phase 3.5: 图后端抽象层
from .backends import GraphBackend, GraphNode, GraphEdge, create_graph_backend

# === Recall 4.1 新增: LLM 关系提取 ===
from .llm_relation_extractor import (
    LLMRelationExtractor,
    LLMRelationExtractorConfig,
    RelationExtractionMode,
    ExtractedRelationV2
)

__all__ = [
    # v3 原有导出（保持向后兼容）
    'KnowledgeGraph',
    'Relation',
    'RelationExtractor',
    
    # v4.0 新增导出
    'TemporalKnowledgeGraph',
    'ContradictionManager',
    'DetectionStrategy',
    'ContradictionRecord',
    
    # v4.0 Phase 3.5: 企业级性能引擎
    'QueryPlanner',
    'QueryPlan',
    'QueryOperation',
    'CommunityDetector',
    'Community',
    
    # v4.0 Phase 3.5: 图后端抽象层
    'GraphBackend',
    'GraphNode',
    'GraphEdge',
    'create_graph_backend',
    
    # === Recall 4.1 新增导出 ===
    'LLMRelationExtractor',
    'LLMRelationExtractorConfig',
    'RelationExtractionMode',
    'ExtractedRelationV2',
]
