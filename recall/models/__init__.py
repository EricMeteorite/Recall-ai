"""Recall 数据模型"""

from .base import EntityType, EventType, ForeshadowingStatus
from .entity import Entity, Relation
from .turn import Turn
from .foreshadowing import Foreshadowing
from .event import Event

# v4.0 新增: 时态模型
from .temporal import (
    NodeType,
    EdgeType,
    ContradictionType,
    ResolutionStrategy,
    TemporalFact,
    UnifiedNode,
    EpisodicNode,
    Contradiction,
    ResolutionResult,
    GraphIndexes,
    # 兼容函数
    entity_to_unified_node,
    relation_to_temporal_fact,
)

# === Recall 4.1 新增: 实体类型 Schema ===
from .entity_schema import (
    AttributeType,
    AttributeDefinition,
    EntityTypeDefinition,
    EntitySchemaRegistry,
)

__all__ = [
    # v3 原有导出（保持向后兼容）
    'EntityType',
    'EventType', 
    'ForeshadowingStatus',
    'Entity',
    'Relation',
    'Turn',
    'Foreshadowing',
    'Event',
    
    # v4.0 新增导出
    'NodeType',
    'EdgeType',
    'ContradictionType',
    'ResolutionStrategy',
    'TemporalFact',
    'UnifiedNode',
    'EpisodicNode',
    'Contradiction',
    'ResolutionResult',
    'GraphIndexes',
    'entity_to_unified_node',
    'relation_to_temporal_fact',
    
    # === Recall 4.1 新增导出 ===
    'AttributeType',
    'AttributeDefinition',
    'EntityTypeDefinition',
    'EntitySchemaRegistry',
]
