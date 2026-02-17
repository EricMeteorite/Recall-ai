"""Recall 4.0 时态数据模型

三时态模型（Tri-temporal Model）：
1. T1: 事实时间 (Fact Time) - 事实在现实中何时有效
2. T2: 知识时间 (Knowledge Time) - 我们何时获知此事实
3. T3: 系统时间 (System Time) - 数据库记录生命周期

设计原则：
- 向后兼容：现有模型 Entity, Relation 继续使用
- 增量添加：新模型独立于现有代码
- 零破坏：不修改任何现有数据结构
"""

from __future__ import annotations

import uuid
import time
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Set, TYPE_CHECKING

# 使用 TYPE_CHECKING 避免循环导入
if TYPE_CHECKING:
    import numpy as np


# =============================================================================
# 节点类型枚举 - 可扩展设计
# =============================================================================

class NodeType(str, Enum):
    """统一节点类型（可扩展）
    
    对标 Graphiti 的 4 种节点，扩展到 9+ 种
    """
    # === Graphiti 对标类型 ===
    ENTITY = "entity"           # 实体（人、物、地点）
    EPISODE = "episode"         # 情节/事件/原始输入
    COMMUNITY = "community"     # 社区/聚类
    SAGA = "saga"               # 相关情节序列
    
    # === Recall 独有类型 ===
    CONCEPT = "concept"         # 概念/抽象
    FORESHADOWING = "foreshadowing"  # 伏笔
    CONDITION = "condition"          # 持久条件
    RULE = "rule"                    # 规则
    
    # === 预留扩展 ===
    CUSTOM = "custom"           # 自定义（插件扩展）


class EdgeType(str, Enum):
    """边/关系类型（可扩展）
    
    对标 Graphiti 的 3 种边，扩展更多类型
    """
    # === Graphiti 对标类型 ===
    ENTITY_RELATION = "entity_relation"   # 实体间关系
    EPISODIC = "episodic"                 # 情节关联
    COMMUNITY = "community"               # 社区关联
    
    # === Recall 独有类型 ===
    TEMPORAL = "temporal"       # 时态关系（before/after/during）
    CAUSAL = "causal"           # 因果关系
    REFERENCE = "reference"     # 引用关系
    
    # === 预留扩展 ===
    CUSTOM = "custom"


class ContradictionType(str, Enum):
    """矛盾类型"""
    DIRECT = "direct"           # 直接矛盾：A=X vs A=Y
    TEMPORAL = "temporal"       # 时态矛盾：时间冲突
    LOGICAL = "logical"         # 逻辑矛盾：逻辑不一致
    SOFT = "soft"               # 软矛盾：可能共存


class ResolutionStrategy(str, Enum):
    """矛盾解决策略"""
    SUPERSEDE = "supersede"     # 新事实取代旧事实
    COEXIST = "coexist"         # 两个事实共存
    REJECT = "reject"           # 拒绝新事实
    MANUAL = "manual"           # 待人工处理


# =============================================================================
# 三时态事实模型
# =============================================================================

@dataclass
class TemporalFact:
    """三时态事实模型 - 超越 Graphiti 的双时态
    
    三时态设计：
    - T1: 事实时间 - 事实在现实中何时有效
    - T2: 知识时间 - 我们何时获知此事实（Graphiti没有）
    - T3: 系统时间 - 数据库记录生命周期
    
    示例：
        "Alice 从 2023-01 开始在 OpenAI 工作"
        - valid_from = 2023-01-01   (T1: 事实开始)
        - known_at = 2024-07-15     (T2: 我们得知的时间)
        - created_at = 2024-07-15   (T3: 入库时间)
        
        后来得知 "Alice 于 2024-06 离开 OpenAI"
        - valid_until = 2024-06-30  (T1: 事实结束)
        - superseded_at = 2024-07-16 (T2: 此知识被更新)
    """
    
    # === 唯一标识 ===
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # === 三元组核心 ===
    subject: str = ""           # 主体（实体ID或名称）
    predicate: str = ""         # 谓词（关系类型）
    object: str = ""            # 客体（实体ID或名称）
    
    # === 自然语言描述 ===
    fact: str = ""              # 事实的自然语言描述
    
    # === T1: 事实时间 (Fact Time) ===
    valid_from: Optional[datetime] = None       # 事实开始有效时间
    valid_until: Optional[datetime] = None      # 事实结束有效时间
    
    # === T2: 知识时间 (Knowledge Time) - 【新增】===
    known_at: datetime = field(default_factory=datetime.now)  # 获知时间
    superseded_at: Optional[datetime] = None    # 被新信息取代的时间
    
    # === T3: 系统时间 (System Time) ===
    created_at: datetime = field(default_factory=datetime.now)
    expired_at: Optional[datetime] = None       # 数据库记录失效时间
    
    # === 多租户隔离 ===
    group_id: str = "default"   # 分组ID（用于多租户）
    user_id: str = "default"    # 用户ID
    
    # === 来源追踪 ===
    source_episodes: List[str] = field(default_factory=list)  # 来源情节UUID列表
    source_text: str = ""       # 原文依据
    
    # === 置信度与验证 ===
    confidence: float = 0.5     # 置信度 (0-1)
    verification_count: int = 0 # 被验证次数
    
    # === 向量嵌入（可选）===
    fact_embedding: Optional[List[float]] = None  # 事实描述的向量
    
    # === 动态属性 ===
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def is_valid_at(self, point_in_time: datetime) -> bool:
        """判断事实在某时间点是否有效"""
        if self.expired_at and self.expired_at <= point_in_time:
            return False  # 已在数据库中失效
        
        if self.valid_from and point_in_time < self.valid_from:
            return False  # 还未开始
        
        if self.valid_until and point_in_time > self.valid_until:
            return False  # 已经结束
        
        return True
    
    def is_superseded(self) -> bool:
        """判断此知识是否已被新信息取代"""
        return self.superseded_at is not None
    
    def supersede(self, new_fact_time: Optional[datetime] = None):
        """标记此事实被新信息取代"""
        self.superseded_at = datetime.now()
        if new_fact_time:
            self.valid_until = new_fact_time
    
    def expire(self):
        """在数据库中标记为失效"""
        self.expired_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典"""
        result = asdict(self)
        # 转换 datetime 为 ISO 格式字符串（兼容已经是字符串的情况）
        for key in ['valid_from', 'valid_until', 'known_at', 'superseded_at', 
                    'created_at', 'expired_at']:
            if result[key] is not None:
                if isinstance(result[key], datetime):
                    result[key] = result[key].isoformat()
                elif not isinstance(result[key], str):
                    result[key] = str(result[key])
                # 已经是 str 则保持不变
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TemporalFact':
        """从字典创建实例"""
        # 转换 ISO 字符串为 datetime
        for key in ['valid_from', 'valid_until', 'known_at', 'superseded_at', 
                    'created_at', 'expired_at']:
            if data.get(key) and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)


# =============================================================================
# 统一节点模型
# =============================================================================

@dataclass
class UnifiedNode:
    """统一节点模型 - 超越 Graphiti 的 4 种节点
    
    设计理念：
    1. 单一模型覆盖所有节点类型
    2. 通过 node_type 区分不同类型
    3. 多向量嵌入支持（名称+内容+摘要）
    4. 动态属性 + Schema 验证
    """
    
    # === 唯一标识 ===
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    
    # === 类型与分组 ===
    node_type: NodeType = NodeType.ENTITY
    group_id: str = "default"       # 多租户隔离
    user_id: str = "default"
    labels: List[str] = field(default_factory=list)  # 标签列表
    
    # === 内容与摘要 ===
    content: str = ""               # 节点内容（对于 EPISODE 是原始文本）
    summary: str = ""               # 摘要
    
    # === 多向量嵌入【超越点】===
    name_embedding: Optional[List[float]] = None
    content_embedding: Optional[List[float]] = None
    summary_embedding: Optional[List[float]] = None
    
    # === 时态信息 ===
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    valid_at: Optional[datetime] = None     # 节点生效时间（用于 EPISODE）
    expired_at: Optional[datetime] = None   # 节点失效时间
    
    # === 来源追踪【增强】===
    source_episodes: List[str] = field(default_factory=list)  # 来源情节UUID
    
    # === 置信度与验证 ===
    confidence: float = 0.5
    verification_count: int = 0
    
    # === 动态属性 + Schema 验证【超越点】===
    attributes: Dict[str, Any] = field(default_factory=dict)
    _attribute_schema: Optional[Dict[str, type]] = field(default=None, repr=False)
    
    # === 别名（兼容现有 Entity 模型）===
    aliases: List[str] = field(default_factory=list)
    
    def set_attribute(self, key: str, value: Any, expected_type: type = None):
        """设置属性，可选类型检查"""
        if expected_type and not isinstance(value, expected_type):
            raise TypeError(f"属性 '{key}' 期望类型 {expected_type}, 实际 {type(value)}")
        
        self.attributes[key] = value
        self.updated_at = datetime.now()
        
        # 记录 Schema
        if self._attribute_schema is None:
            self._attribute_schema = {}
        if expected_type:
            self._attribute_schema[key] = expected_type
    
    def get_attribute(self, key: str, default: Any = None) -> Any:
        """获取属性"""
        return self.attributes.get(key, default)
    
    def validate_attributes(self) -> bool:
        """验证所有属性符合 Schema"""
        if not self._attribute_schema:
            return True
        
        for key, expected_type in self._attribute_schema.items():
            if key in self.attributes:
                if not isinstance(self.attributes[key], expected_type):
                    return False
        return True
    
    def is_active(self) -> bool:
        """判断节点是否活跃"""
        return self.expired_at is None
    
    def expire(self):
        """标记节点失效"""
        self.expired_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典"""
        result = asdict(self)
        result['node_type'] = self.node_type.value
        
        # 转换 datetime 为 ISO 格式（兼容已经是字符串的情况）
        for key in ['created_at', 'updated_at', 'valid_at', 'expired_at']:
            if result[key] is not None:
                if isinstance(result[key], datetime):
                    result[key] = result[key].isoformat()
                elif not isinstance(result[key], str):
                    result[key] = str(result[key])
                # 已经是 str 则保持不变
        
        # 移除私有字段
        result.pop('_attribute_schema', None)
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedNode':
        """从字典创建实例"""
        # 转换 node_type
        if isinstance(data.get('node_type'), str):
            data['node_type'] = NodeType(data['node_type'])
        
        # 转换 datetime
        for key in ['created_at', 'updated_at', 'valid_at', 'expired_at']:
            if data.get(key) and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        
        # 移除不存在的字段
        data.pop('_attribute_schema', None)
        
        return cls(**data)


# =============================================================================
# 情节节点（Episode）- 原始输入单元
# =============================================================================

class EpisodeType(str, Enum):
    """情节来源类型"""
    TEXT = "text"               # 纯文本
    MESSAGE = "message"         # 对话消息
    JSON = "json"               # 结构化 JSON


@dataclass
class EpisodicNode(UnifiedNode):
    """情节节点 - 原始数据输入单元
    
    继承 UnifiedNode，添加情节特有属性
    """
    
    # === 覆盖默认值 ===
    node_type: NodeType = field(default=NodeType.EPISODE)
    
    # === 情节特有属性 ===
    source_type: EpisodeType = EpisodeType.TEXT  # 来源类型
    source_description: str = ""                  # 来源描述
    
    # === 关联的边 ===
    entity_edges: List[str] = field(default_factory=list)  # 关联的实体边UUID
    
    # === 元数据 ===
    turn_number: int = 0        # 对话轮次（兼容现有系统）
    role: str = ""              # 角色（user/assistant）
    
    # === Recall 4.1 新增：SillyTavern 关联 ===
    # 注意：user_id 和 group_id 已从 UnifiedNode 继承
    character_id: str = ""      # 角色ID（SillyTavern 特有）
    
    # === Recall 4.1 新增：追溯链 ===
    memory_ids: List[str] = field(default_factory=list)    # 关联的记忆ID
    relation_ids: List[str] = field(default_factory=list)  # 关联的关系ID
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典"""
        result = super().to_dict()
        result['source_type'] = self.source_type.value
        # Recall 4.1: 新增字段（user_id/group_id 已由父类处理）
        result['character_id'] = self.character_id
        result['memory_ids'] = self.memory_ids
        result['relation_ids'] = self.relation_ids
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodicNode':
        """从字典创建实例"""
        # 转换 source_type
        if isinstance(data.get('source_type'), str):
            data['source_type'] = EpisodeType(data['source_type'])
        
        # 调用父类转换
        if isinstance(data.get('node_type'), str):
            data['node_type'] = NodeType(data['node_type'])
        
        for key in ['created_at', 'updated_at', 'valid_at', 'expired_at']:
            if data.get(key) and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        
        data.pop('_attribute_schema', None)
        
        return cls(**data)


# =============================================================================
# 矛盾与解决
# =============================================================================

@dataclass
class Contradiction:
    """矛盾记录"""
    
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    old_fact: TemporalFact = field(default_factory=TemporalFact)
    new_fact: TemporalFact = field(default_factory=TemporalFact)
    
    contradiction_type: ContradictionType = ContradictionType.DIRECT
    confidence: float = 0.5     # 矛盾置信度
    
    detected_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution: Optional[ResolutionStrategy] = None
    
    notes: str = ""             # 备注
    
    def is_resolved(self) -> bool:
        """是否已解决"""
        return self.resolved_at is not None
    
    def resolve(self, strategy: ResolutionStrategy, notes: str = ""):
        """解决矛盾"""
        self.resolution = strategy
        self.resolved_at = datetime.now()
        self.notes = notes


@dataclass
class ResolutionResult:
    """矛盾解决结果"""
    success: bool
    action: str                 # 采取的动作
    old_fact_id: str = ""
    new_fact_id: str = ""
    message: str = ""


# =============================================================================
# 图索引结构（用于高效查询）
# =============================================================================

@dataclass
class GraphIndexes:
    """图谱索引集合"""
    
    # 邻接表索引
    outgoing: Dict[str, Set[str]] = field(default_factory=lambda: {})  # node_id -> edge_ids
    incoming: Dict[str, Set[str]] = field(default_factory=lambda: {})  # node_id -> edge_ids
    
    # 类型索引
    by_node_type: Dict[NodeType, Set[str]] = field(default_factory=lambda: {})  # type -> node_ids
    by_predicate: Dict[str, Set[str]] = field(default_factory=lambda: {})       # predicate -> edge_ids
    
    def add_edge(self, edge_id: str, source_id: str, target_id: str, predicate: str):
        """添加边到索引"""
        # 邻接表
        if source_id not in self.outgoing:
            self.outgoing[source_id] = set()
        self.outgoing[source_id].add(edge_id)
        
        if target_id not in self.incoming:
            self.incoming[target_id] = set()
        self.incoming[target_id].add(edge_id)
        
        # 谓词索引
        if predicate not in self.by_predicate:
            self.by_predicate[predicate] = set()
        self.by_predicate[predicate].add(edge_id)
    
    def add_node(self, node_id: str, node_type: NodeType):
        """添加节点到索引"""
        if node_type not in self.by_node_type:
            self.by_node_type[node_type] = set()
        self.by_node_type[node_type].add(node_id)
    
    def remove_edge(self, edge_id: str, source_id: str, target_id: str, predicate: str):
        """从索引移除边"""
        if source_id in self.outgoing:
            self.outgoing[source_id].discard(edge_id)
        if target_id in self.incoming:
            self.incoming[target_id].discard(edge_id)
        if predicate in self.by_predicate:
            self.by_predicate[predicate].discard(edge_id)
    
    def remove_node(self, node_id: str, node_type: NodeType):
        """从索引移除节点"""
        if node_type in self.by_node_type:
            self.by_node_type[node_type].discard(node_id)


# =============================================================================
# 兼容层：旧模型到新模型的转换
# =============================================================================

def entity_to_unified_node(entity: Any) -> UnifiedNode:
    """将旧的 Entity 模型转换为 UnifiedNode
    
    兼容 recall/models/entity.py 中的 Entity 类
    """
    from .entity import Entity
    
    if not isinstance(entity, Entity):
        raise TypeError(f"期望 Entity 类型，实际 {type(entity)}")
    
    # 映射实体类型
    from .base import EntityType as OldEntityType
    type_mapping = {
        OldEntityType.CHARACTER: NodeType.ENTITY,
        OldEntityType.ITEM: NodeType.ENTITY,
        OldEntityType.LOCATION: NodeType.ENTITY,
        OldEntityType.CONCEPT: NodeType.CONCEPT,
        OldEntityType.CODE_SYMBOL: NodeType.ENTITY,
    }
    
    node = UnifiedNode(
        uuid=entity.id,
        name=entity.name,
        node_type=type_mapping.get(entity.entity_type, NodeType.ENTITY),
        aliases=entity.aliases,
        attributes=entity.current_state,
        confidence=entity.confidence,
        verification_count=entity.verification_count,
        source_episodes=[str(t) for t in entity.source_turns],
    )
    
    # 保留原始类型作为标签
    node.labels.append(entity.entity_type.value)
    
    # 保留 embedding
    if entity.embedding:
        node.content_embedding = entity.embedding
    
    return node


def relation_to_temporal_fact(relation: Any, source_entity: str = None) -> TemporalFact:
    """将旧的 Relation 模型转换为 TemporalFact
    
    兼容 recall/graph/knowledge_graph.py 中的 Relation 类
    """
    from ..graph.knowledge_graph import Relation as GraphRelation
    
    if not isinstance(relation, GraphRelation):
        raise TypeError(f"期望 Relation 类型，实际 {type(relation)}")
    
    fact = TemporalFact(
        subject=relation.source_id,
        predicate=relation.relation_type,
        object=relation.target_id,
        fact=relation.source_text or f"{relation.source_id} {relation.relation_type} {relation.target_id}",
        confidence=relation.confidence,
        source_text=relation.source_text,
        attributes=relation.properties,
    )
    
    return fact


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 枚举
    'NodeType',
    'EdgeType',
    'EpisodeType',
    'ContradictionType',
    'ResolutionStrategy',
    
    # 核心模型
    'TemporalFact',
    'UnifiedNode',
    'EpisodicNode',
    
    # 矛盾处理
    'Contradiction',
    'ResolutionResult',
    
    # 索引
    'GraphIndexes',
    
    # 兼容函数
    'entity_to_unified_node',
    'relation_to_temporal_fact',
]
