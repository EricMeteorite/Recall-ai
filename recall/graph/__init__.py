"""图谱层模块"""

from .knowledge_graph import KnowledgeGraph, Relation
from .relation_extractor import RelationExtractor

# v4.0 新增: 时态知识图谱与矛盾管理
from .temporal_knowledge_graph import TemporalKnowledgeGraph
from .contradiction_manager import ContradictionManager, DetectionStrategy, ContradictionRecord

# v4.0 Phase 3.5: 企业级性能引擎
from .query_planner import QueryPlanner, QueryPlan, QueryOperation
from .community_detector import CommunityDetector, Community

# v4.0 Phase 3.5: 图后端抽象层
from .backends import GraphBackend, GraphNode, GraphEdge, create_graph_backend

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
]
