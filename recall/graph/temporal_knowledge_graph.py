"""时序知识图谱 - Recall 4.0 核心模块

设计理念：
1. 三时态支持（事实时间、知识时间、系统时间）
2. 零依赖本地存储，可选外部数据库
3. 与现有 KnowledgeGraph 完全兼容，可并行使用
4. 高效索引：时态索引 + 全文索引 + 向量索引

不修改现有 KnowledgeGraph，而是作为新的增强版本。
"""

from __future__ import annotations

import os
import json
import uuid as uuid_lib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Optional, Tuple, Any, Union
from collections import defaultdict

from ..models.temporal import (
    NodeType, EdgeType, ContradictionType, ResolutionStrategy,
    TemporalFact, UnifiedNode, EpisodicNode, EpisodeType,
    Contradiction, ResolutionResult, GraphIndexes
)
from ..index.temporal_index import TemporalIndex, TemporalEntry, TimeRange
from ..index.fulltext_index import FullTextIndex


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


@dataclass
class QueryResult:
    """查询结果"""
    nodes: List[UnifiedNode] = field(default_factory=list)
    edges: List[TemporalFact] = field(default_factory=list)
    total_count: int = 0
    query_time_ms: float = 0.0


class TemporalKnowledgeGraph:
    """时序知识图谱 - 超越 Graphiti 的三时态支持
    
    核心特性：
    1. 三时态模型：事实时间 + 知识时间 + 系统时间
    2. 零依赖：纯本地 JSON 存储
    3. 高效索引：时态索引 + 全文索引
    4. 矛盾检测：自动检测并支持多种解决策略
    5. 图遍历：BFS/DFS + 时态过滤
    
    与现有 KnowledgeGraph 的关系：
    - 完全独立，不修改现有类
    - 可以通过迁移工具将旧数据导入
    - 新功能使用此类，旧功能继续使用原有类
    """
    
    VERSION = "4.0.0"
    
    def __init__(
        self,
        data_path: str,
        backend: str = "file",          # file | neo4j | falkordb（预留）
        scope: str = "global",          # global | isolated
        enable_fulltext: bool = True,   # 是否启用全文索引
        enable_temporal: bool = True,   # 是否启用时态索引
        auto_save: bool = True          # 是否自动保存
    ):
        """初始化时序知识图谱
        
        Args:
            data_path: 数据存储路径
            backend: 存储后端（file=本地JSON文件，支持旧值 'local'）
            scope: 作用域
            enable_fulltext: 是否启用全文索引
            enable_temporal: 是否启用时态索引
            auto_save: 是否自动保存
        """
        self.data_path = data_path
        # 向后兼容：映射旧值 'local' 到 'file'
        if backend == "local":
            backend = "file"
        self.backend = backend
        self.scope = scope
        self.auto_save = auto_save
        
        # 存储目录
        self.graph_dir = os.path.join(data_path, 'temporal_graph')
        self.nodes_file = os.path.join(self.graph_dir, 'nodes.json')
        self.edges_file = os.path.join(self.graph_dir, 'edges.json')
        self.episodes_file = os.path.join(self.graph_dir, 'episodes.json')
        self.meta_file = os.path.join(self.graph_dir, 'meta.json')
        
        # 核心存储
        self.nodes: Dict[str, UnifiedNode] = {}
        self.edges: Dict[str, TemporalFact] = {}
        self.episodes: Dict[str, EpisodicNode] = {}
        
        # 内存索引
        self._indexes = GraphIndexes()
        
        # 名称到 UUID 的映射（用于快速查找）
        self._name_to_uuid: Dict[str, str] = {}
        
        # 可选索引
        self._temporal_index: Optional[TemporalIndex] = None
        self._fulltext_index: Optional[FullTextIndex] = None
        
        if enable_temporal:
            self._temporal_index = TemporalIndex(data_path)
        
        if enable_fulltext:
            self._fulltext_index = FullTextIndex(data_path)
        
        # 待处理的矛盾
        self._pending_contradictions: List[Contradiction] = []
        
        # 脏标记
        self._dirty = False
        
        # 加载数据
        self._load()
    
    # =========================================================================
    # 持久化
    # =========================================================================
    
    def _load(self):
        """加载图谱数据"""
        os.makedirs(self.graph_dir, exist_ok=True)
        
        # 加载节点
        if os.path.exists(self.nodes_file):
            try:
                with open(self.nodes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item in data:
                    node = UnifiedNode.from_dict(item)
                    self.nodes[node.uuid] = node
                    self._index_node(node)
            except Exception as e:
                _safe_print(f"[TemporalKnowledgeGraph] 加载节点失败: {e}")
        
        # 加载边
        if os.path.exists(self.edges_file):
            try:
                with open(self.edges_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item in data:
                    edge = TemporalFact.from_dict(item)
                    self.edges[edge.uuid] = edge
                    self._index_edge(edge)
            except Exception as e:
                _safe_print(f"[TemporalKnowledgeGraph] 加载边失败: {e}")
        
        # 加载情节
        if os.path.exists(self.episodes_file):
            try:
                with open(self.episodes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item in data:
                    episode = EpisodicNode.from_dict(item)
                    self.episodes[episode.uuid] = episode
            except Exception as e:
                _safe_print(f"[TemporalKnowledgeGraph] 加载情节失败: {e}")
    
    def _save(self):
        """保存图谱数据"""
        if not self._dirty and not self.auto_save:
            return
        
        os.makedirs(self.graph_dir, exist_ok=True)
        
        # 保存节点
        with open(self.nodes_file, 'w', encoding='utf-8') as f:
            json.dump([n.to_dict() for n in self.nodes.values()], f, ensure_ascii=False, indent=2)
        
        # 保存边
        with open(self.edges_file, 'w', encoding='utf-8') as f:
            json.dump([e.to_dict() for e in self.edges.values()], f, ensure_ascii=False, indent=2)
        
        # 保存情节
        with open(self.episodes_file, 'w', encoding='utf-8') as f:
            json.dump([e.to_dict() for e in self.episodes.values()], f, ensure_ascii=False, indent=2)
        
        # 保存元数据
        meta = {
            'version': self.VERSION,
            'node_count': len(self.nodes),
            'edge_count': len(self.edges),
            'episode_count': len(self.episodes),
            'updated_at': datetime.now().isoformat()
        }
        with open(self.meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        
        # 保存索引
        if self._temporal_index:
            self._temporal_index.flush()
        if self._fulltext_index:
            self._fulltext_index.flush()
        
        self._dirty = False
    
    def flush(self):
        """强制保存"""
        self._dirty = True
        self._save()
    
    # =========================================================================
    # 内存索引管理
    # =========================================================================
    
    def _index_node(self, node: UnifiedNode):
        """索引节点到内存"""
        self._indexes.add_node(node.uuid, node.node_type)
        self._name_to_uuid[node.name.lower()] = node.uuid
        for alias in node.aliases:
            self._name_to_uuid[alias.lower()] = node.uuid
        
        # 全文索引
        if self._fulltext_index:
            text = f"{node.name} {node.summary} {node.content}"
            self._fulltext_index.add(f"node:{node.uuid}", text)
    
    def _index_edge(self, edge: TemporalFact):
        """索引边到内存"""
        self._indexes.add_edge(edge.uuid, edge.subject, edge.object, edge.predicate)
        
        # 时态索引
        if self._temporal_index:
            entry = TemporalEntry(
                doc_id=edge.uuid,
                fact_range=TimeRange(start=edge.valid_from, end=edge.valid_until),
                known_at=edge.known_at,
                system_range=TimeRange(start=edge.created_at, end=edge.expired_at),
                subject=edge.subject,
                predicate=edge.predicate
            )
            self._temporal_index.add(entry)
        
        # 全文索引
        if self._fulltext_index:
            self._fulltext_index.add(f"edge:{edge.uuid}", edge.fact)
    
    def _unindex_node(self, node: UnifiedNode):
        """从内存索引移除节点"""
        self._indexes.remove_node(node.uuid, node.node_type)
        self._name_to_uuid.pop(node.name.lower(), None)
        for alias in node.aliases:
            self._name_to_uuid.pop(alias.lower(), None)
        
        if self._fulltext_index:
            self._fulltext_index.remove(f"node:{node.uuid}")
    
    def _unindex_edge(self, edge: TemporalFact):
        """从内存索引移除边"""
        self._indexes.remove_edge(edge.uuid, edge.subject, edge.object, edge.predicate)
        
        if self._temporal_index:
            self._temporal_index.remove(edge.uuid)
        
        if self._fulltext_index:
            self._fulltext_index.remove(f"edge:{edge.uuid}")
    
    # =========================================================================
    # 节点 CRUD
    # =========================================================================
    
    def add_node(
        self,
        name_or_node: Union[str, UnifiedNode],
        node_type: NodeType = NodeType.ENTITY,
        content: str = "",
        summary: str = "",
        attributes: Dict[str, Any] = None,
        aliases: List[str] = None,
        group_id: str = "default",
        user_id: str = "default",
        **kwargs
    ) -> UnifiedNode:
        """添加节点
        
        Args:
            name_or_node: 节点名称（字符串）或 UnifiedNode 对象
            node_type: 节点类型（当 name_or_node 是字符串时使用）
            content: 内容
            summary: 摘要
            attributes: 属性
            aliases: 别名列表
            group_id: 分组ID
            user_id: 用户ID
        
        Returns:
            创建的节点
        """
        # 如果传入的是 UnifiedNode 对象，直接使用
        if isinstance(name_or_node, UnifiedNode):
            node = name_or_node
            name = node.name
            
            # 检查是否已存在同名节点
            existing = self.get_node_by_name(name)
            if existing:
                # 合并属性
                if node.content:
                    existing.content = node.content
                if node.summary:
                    existing.summary = node.summary
                if node.attributes:
                    existing.attributes.update(node.attributes)
                if node.aliases:
                    existing.aliases = list(set(existing.aliases + node.aliases))
                existing.updated_at = datetime.now()
                existing.verification_count += 1
                self._dirty = True
                if self.auto_save:
                    self._save()
                return existing
            
            # 直接添加传入的节点
            self.nodes[node.uuid] = node
            self._index_node(node)
            self._dirty = True
            
            if self.auto_save:
                self._save()
            
            return node
        
        # 否则，name_or_node 是字符串，创建新节点
        name = name_or_node
        
        # 检查是否已存在同名节点
        existing = self.get_node_by_name(name)
        if existing:
            # 更新现有节点
            if content:
                existing.content = content
            if summary:
                existing.summary = summary
            if attributes:
                existing.attributes.update(attributes)
            if aliases:
                existing.aliases = list(set(existing.aliases + aliases))
            existing.updated_at = datetime.now()
            existing.verification_count += 1
            self._dirty = True
            if self.auto_save:
                self._save()
            return existing
        
        # 创建新节点
        node = UnifiedNode(
            uuid=str(uuid_lib.uuid4()),
            name=name,
            node_type=node_type,
            content=content,
            summary=summary,
            attributes=attributes or {},
            aliases=aliases or [],
            group_id=group_id,
            user_id=user_id,
            **kwargs
        )
        
        self.nodes[node.uuid] = node
        self._index_node(node)
        self._dirty = True
        
        if self.auto_save:
            self._save()
        
        return node
    
    def get_node(self, uuid: str) -> Optional[UnifiedNode]:
        """通过 UUID 获取节点"""
        return self.nodes.get(uuid)
    
    def get_node_by_name(self, name: str) -> Optional[UnifiedNode]:
        """通过名称获取节点（支持别名）"""
        uuid = self._name_to_uuid.get(name.lower())
        if uuid:
            return self.nodes.get(uuid)
        return None
    
    def update_node(self, uuid: str, **updates) -> Optional[UnifiedNode]:
        """更新节点"""
        node = self.nodes.get(uuid)
        if not node:
            return None
        
        for key, value in updates.items():
            if hasattr(node, key):
                setattr(node, key, value)
        
        node.updated_at = datetime.now()
        self._dirty = True
        
        if self.auto_save:
            self._save()
        
        return node
    
    def remove_node(self, uuid: str) -> bool:
        """移除节点（软删除）"""
        node = self.nodes.get(uuid)
        if not node:
            return False
        
        node.expire()
        self._unindex_node(node)
        self._dirty = True
        
        if self.auto_save:
            self._save()
        
        return True
    
    def get_nodes_by_type(self, node_type: NodeType) -> List[UnifiedNode]:
        """获取指定类型的所有节点"""
        node_ids = self._indexes.by_node_type.get(node_type, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]
    
    # =========================================================================
    # 边/事实 CRUD
    # =========================================================================
    
    def add_edge(
        self,
        subject_or_fact: Union[str, TemporalFact],
        predicate: str = "",
        object_: str = "",
        fact: str = "",
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
        source_text: str = "",
        confidence: float = 0.5,
        group_id: str = "default",
        user_id: str = "default",
        check_contradiction: bool = True,
        **kwargs
    ) -> Tuple[TemporalFact, List[Contradiction]]:
        """添加边/事实
        
        Args:
            subject_or_fact: 主体（节点名称或UUID）或 TemporalFact 对象
            predicate: 谓词/关系类型
            object_: 客体（节点名称或UUID）
            fact: 事实的自然语言描述
            valid_from: 事实开始有效时间
            valid_until: 事实结束有效时间
            source_text: 原文依据
            confidence: 置信度
            group_id: 分组ID
            user_id: 用户ID
            check_contradiction: 是否检查矛盾
        
        Returns:
            (创建的边, 检测到的矛盾列表)
        """
        # 如果传入的是 TemporalFact 对象，直接使用
        if isinstance(subject_or_fact, TemporalFact):
            edge = subject_or_fact
            
            # 检查矛盾
            contradictions = []
            if check_contradiction:
                contradictions = self.detect_contradictions(edge)
            
            # 添加到存储
            self.edges[edge.uuid] = edge
            self._index_edge(edge)
            
            self._dirty = True
            if self.auto_save:
                self._save()
            
            return edge, contradictions
        
        # 否则，按照参数创建边
        subject = subject_or_fact
        
        # 确保主体和客体节点存在
        subject_node = self.get_node_by_name(subject) or self.get_node(subject)
        object_node = self.get_node_by_name(object_) or self.get_node(object_)
        
        if not subject_node:
            subject_node = self.add_node(subject, group_id=group_id, user_id=user_id)
        if not object_node:
            object_node = self.add_node(object_, group_id=group_id, user_id=user_id)
        
        # 创建事实
        if not fact:
            fact = f"{subject} {predicate} {object_}"
        
        edge = TemporalFact(
            uuid=str(uuid_lib.uuid4()),
            subject=subject_node.uuid,
            predicate=predicate,
            object=object_node.uuid,
            fact=fact,
            valid_from=valid_from,
            valid_until=valid_until,
            source_text=source_text,
            confidence=confidence,
            group_id=group_id,
            user_id=user_id,
            **kwargs
        )
        
        # 检查矛盾
        contradictions = []
        if check_contradiction:
            contradictions = self.detect_contradictions(edge)
        
        # 添加到存储
        self.edges[edge.uuid] = edge
        self._index_edge(edge)
        
        # 更新节点的来源情节
        subject_node.source_episodes.append(edge.uuid)
        object_node.source_episodes.append(edge.uuid)
        
        self._dirty = True
        if self.auto_save:
            self._save()
        
        return edge, contradictions
    
    def get_edge(self, uuid: str) -> Optional[TemporalFact]:
        """通过 UUID 获取边"""
        return self.edges.get(uuid)
    
    def get_edges_by_subject(
        self,
        subject: str,
        predicate: Optional[str] = None,
        valid_at: Optional[datetime] = None
    ) -> List[TemporalFact]:
        """获取某主体的所有边
        
        Args:
            subject: 主体名称或UUID
            predicate: 可选谓词过滤
            valid_at: 可选时间点过滤
        """
        # 获取主体 UUID
        subject_node = self.get_node_by_name(subject) or self.get_node(subject)
        if not subject_node:
            return []
        
        subject_uuid = subject_node.uuid
        edge_ids = self._indexes.outgoing.get(subject_uuid, set())
        
        results = []
        for eid in edge_ids:
            edge = self.edges.get(eid)
            if not edge:
                continue
            
            # 谓词过滤
            if predicate and edge.predicate != predicate:
                continue
            
            # 时态过滤
            if valid_at and not edge.is_valid_at(valid_at):
                continue
            
            results.append(edge)
        
        return results
    
    def update_edge(self, uuid: str, **updates) -> Optional[TemporalFact]:
        """更新边"""
        edge = self.edges.get(uuid)
        if not edge:
            return None
        
        for key, value in updates.items():
            if hasattr(edge, key):
                setattr(edge, key, value)
        
        self._dirty = True
        if self.auto_save:
            self._save()
        
        return edge
    
    def expire_edge(self, uuid: str) -> bool:
        """使边失效"""
        edge = self.edges.get(uuid)
        if not edge:
            return False
        
        edge.expire()
        self._unindex_edge(edge)
        self._dirty = True
        
        if self.auto_save:
            self._save()
        
        return True
    
    # =========================================================================
    # 情节 CRUD
    # =========================================================================
    
    def add_episode(
        self,
        content: str,
        source_type: EpisodeType = EpisodeType.TEXT,
        source_description: str = "",
        valid_at: Optional[datetime] = None,
        turn_number: int = 0,
        role: str = "",
        group_id: str = "default",
        user_id: str = "default",
        **kwargs
    ) -> EpisodicNode:
        """添加情节
        
        Args:
            content: 内容
            source_type: 来源类型
            source_description: 来源描述
            valid_at: 原始文档创建时间
            turn_number: 对话轮次
            role: 角色
            group_id: 分组ID
            user_id: 用户ID
        
        Returns:
            创建的情节节点
        """
        episode = EpisodicNode(
            uuid=str(uuid_lib.uuid4()),
            name=f"episode_{turn_number}_{int(datetime.now().timestamp())}",
            content=content,
            source_type=source_type,
            source_description=source_description,
            valid_at=valid_at or datetime.now(),
            turn_number=turn_number,
            role=role,
            group_id=group_id,
            user_id=user_id,
            **kwargs
        )
        
        self.episodes[episode.uuid] = episode
        self._dirty = True
        
        if self.auto_save:
            self._save()
        
        return episode
    
    def get_episode(self, uuid: str) -> Optional[EpisodicNode]:
        """获取情节"""
        return self.episodes.get(uuid)
    
    def get_recent_episodes(
        self,
        limit: int = 20,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None
    ) -> List[EpisodicNode]:
        """获取最近的情节"""
        episodes = list(self.episodes.values())
        
        # 过滤
        if user_id:
            episodes = [e for e in episodes if e.user_id == user_id]
        if group_id:
            episodes = [e for e in episodes if e.group_id == group_id]
        
        # 按创建时间排序
        episodes.sort(key=lambda x: x.created_at, reverse=True)
        
        return episodes[:limit]
    
    # =========================================================================
    # 时态查询 API
    # =========================================================================
    
    def query_at_time(
        self,
        subject: str,
        as_of: datetime,
        predicate: Optional[str] = None
    ) -> List[TemporalFact]:
        """查询某时间点的有效事实
        
        Args:
            subject: 主体名称或UUID
            as_of: 查询时间点
            predicate: 可选谓词过滤
        
        Returns:
            有效的事实列表
        """
        return self.get_edges_by_subject(subject, predicate=predicate, valid_at=as_of)
    
    def query_timeline(
        self,
        subject: str,
        predicate: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Tuple[datetime, TemporalFact, str]]:
        """获取实体时间线
        
        Args:
            subject: 主体名称或UUID
            predicate: 可选谓词过滤
            start: 时间范围起始
            end: 时间范围结束
        
        Returns:
            [(时间点, 事实, 事件类型), ...] 按时间排序
            事件类型: 'started' | 'ended' | 'superseded'
        """
        edges = self.get_edges_by_subject(subject, predicate=predicate)
        
        timeline: List[Tuple[datetime, TemporalFact, str]] = []
        
        for edge in edges:
            if edge.valid_from:
                timeline.append((edge.valid_from, edge, "started"))
            if edge.valid_until:
                timeline.append((edge.valid_until, edge, "ended"))
            if edge.superseded_at:
                timeline.append((edge.superseded_at, edge, "superseded"))
        
        # 按时间排序
        timeline.sort(key=lambda x: x[0])
        
        # 时间范围过滤
        if start:
            timeline = [t for t in timeline if t[0] >= start]
        if end:
            timeline = [t for t in timeline if t[0] <= end]
        
        return timeline
    
    def compare_snapshots(
        self,
        subject: str,
        time1: datetime,
        time2: datetime
    ) -> Dict[str, Any]:
        """对比两个时间点的状态差异
        
        Args:
            subject: 主体名称或UUID
            time1: 时间点1
            time2: 时间点2
        
        Returns:
            差异报告
        """
        facts1 = self.query_at_time(subject, time1)
        facts2 = self.query_at_time(subject, time2)
        
        # 转换为可比较的格式
        facts1_set = {(f.predicate, f.object): f for f in facts1}
        facts2_set = {(f.predicate, f.object): f for f in facts2}
        
        keys1 = set(facts1_set.keys())
        keys2 = set(facts2_set.keys())
        
        added = keys2 - keys1
        removed = keys1 - keys2
        unchanged = keys1 & keys2
        
        return {
            'subject': subject,
            'time1': time1.isoformat(),
            'time2': time2.isoformat(),
            'added': [facts2_set[k].to_dict() for k in added],
            'removed': [facts1_set[k].to_dict() for k in removed],
            'unchanged_count': len(unchanged),
            'total_changes': len(added) + len(removed)
        }
    
    # =========================================================================
    # 矛盾检测与处理
    # =========================================================================
    
    def detect_contradictions(
        self,
        new_fact: TemporalFact,
        strategy: str = "auto"
    ) -> List[Contradiction]:
        """检测矛盾
        
        Args:
            new_fact: 新事实
            strategy: 检测策略（auto | strict | permissive）
        
        Returns:
            检测到的矛盾列表
        """
        contradictions = []
        
        # 查找同主体、同谓词的现有事实
        existing = self.query_at_time(
            new_fact.subject,
            new_fact.valid_from or datetime.now(),
            new_fact.predicate
        )
        
        for old_fact in existing:
            if old_fact.uuid == new_fact.uuid:
                continue  # 跳过自身
            
            if old_fact.object != new_fact.object:
                # 检测到潜在矛盾
                contradiction_type = self._classify_contradiction(old_fact, new_fact)
                
                if strategy == "permissive" and contradiction_type == ContradictionType.SOFT:
                    continue  # 宽松模式忽略软矛盾
                
                contradiction = Contradiction(
                    old_fact=old_fact,
                    new_fact=new_fact,
                    contradiction_type=contradiction_type,
                    confidence=self._compute_contradiction_confidence(old_fact, new_fact)
                )
                contradictions.append(contradiction)
        
        return contradictions
    
    def _classify_contradiction(
        self,
        old_fact: TemporalFact,
        new_fact: TemporalFact
    ) -> ContradictionType:
        """分类矛盾类型"""
        # 检查时态是否重叠
        old_start = old_fact.valid_from or datetime.min
        old_end = old_fact.valid_until or datetime.max
        new_start = new_fact.valid_from or datetime.min
        new_end = new_fact.valid_until or datetime.max
        
        # 时间不重叠 = 非矛盾（状态变化）
        if old_end < new_start or new_end < old_start:
            return ContradictionType.SOFT
        
        # 时间完全包含 = 可能是更新
        if new_start <= old_start and new_end >= old_end:
            return ContradictionType.DIRECT
        
        # 部分重叠 = 时态矛盾
        return ContradictionType.TEMPORAL
    
    def _compute_contradiction_confidence(
        self,
        old_fact: TemporalFact,
        new_fact: TemporalFact
    ) -> float:
        """计算矛盾置信度"""
        # 基于两个事实的置信度
        base = (old_fact.confidence + new_fact.confidence) / 2
        
        # 如果新事实来源更可靠，提高置信度
        if new_fact.verification_count > old_fact.verification_count:
            base *= 1.1
        
        return min(1.0, base)
    
    def resolve_contradiction(
        self,
        contradiction: Contradiction,
        resolution: ResolutionStrategy = ResolutionStrategy.SUPERSEDE
    ) -> ResolutionResult:
        """解决矛盾
        
        Args:
            contradiction: 矛盾对象
            resolution: 解决策略
        
        Returns:
            解决结果
        """
        old_fact = contradiction.old_fact
        new_fact = contradiction.new_fact
        
        if resolution == ResolutionStrategy.SUPERSEDE:
            # 新事实取代旧事实
            old_fact.valid_until = new_fact.valid_from
            old_fact.superseded_at = datetime.now()
            contradiction.resolve(resolution, "新事实取代旧事实")
            self._dirty = True
            if self.auto_save:
                self._save()
            return ResolutionResult(
                success=True,
                action="superseded",
                old_fact_id=old_fact.uuid,
                new_fact_id=new_fact.uuid,
                message="旧事实已被新事实取代"
            )
        
        elif resolution == ResolutionStrategy.COEXIST:
            # 两个事实共存
            contradiction.resolve(resolution, "允许共存")
            return ResolutionResult(
                success=True,
                action="coexist",
                old_fact_id=old_fact.uuid,
                new_fact_id=new_fact.uuid,
                message="两个事实将共存"
            )
        
        elif resolution == ResolutionStrategy.REJECT:
            # 拒绝新事实
            if new_fact.uuid in self.edges:
                self.expire_edge(new_fact.uuid)
            contradiction.resolve(resolution, "拒绝新事实")
            return ResolutionResult(
                success=False,
                action="rejected",
                old_fact_id=old_fact.uuid,
                new_fact_id=new_fact.uuid,
                message="新事实已被拒绝"
            )
        
        else:
            # 待人工处理
            self._pending_contradictions.append(contradiction)
            return ResolutionResult(
                success=True,
                action="pending_manual",
                old_fact_id=old_fact.uuid,
                new_fact_id=new_fact.uuid,
                message="已加入待处理队列"
            )
    
    def get_pending_contradictions(self) -> List[Contradiction]:
        """获取待处理的矛盾"""
        return self._pending_contradictions.copy()
    
    # =========================================================================
    # 图遍历 API
    # =========================================================================
    
    def bfs(
        self,
        start: str,
        max_depth: int = 3,
        predicate_filter: Optional[List[str]] = None,
        time_filter: Optional[datetime] = None,
        direction: str = "both"
    ) -> Dict[int, List[Tuple[str, TemporalFact]]]:
        """广度优先搜索
        
        Args:
            start: 起始节点名称或UUID
            max_depth: 最大深度
            predicate_filter: 谓词过滤列表
            time_filter: 时间过滤
            direction: 方向（out | in | both）
        
        Returns:
            按深度分组的结果 {depth: [(node_id, edge), ...]}
        """
        # 获取起始节点 UUID
        start_node = self.get_node_by_name(start) or self.get_node(start)
        if not start_node:
            return {}
        
        start_uuid = start_node.uuid
        visited = {start_uuid}
        queue = [(start_uuid, 0)]
        results: Dict[int, List[Tuple[str, TemporalFact]]] = defaultdict(list)
        
        while queue:
            node_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            
            # 获取边
            edge_ids: Set[str] = set()
            if direction in ("out", "both"):
                edge_ids.update(self._indexes.outgoing.get(node_id, set()))
            if direction in ("in", "both"):
                edge_ids.update(self._indexes.incoming.get(node_id, set()))
            
            for edge_id in edge_ids:
                edge = self.edges.get(edge_id)
                if not edge:
                    continue
                
                # 时态过滤
                if time_filter and not edge.is_valid_at(time_filter):
                    continue
                
                # 谓词过滤
                if predicate_filter and edge.predicate not in predicate_filter:
                    continue
                
                # 确定目标节点
                target = edge.object if edge.subject == node_id else edge.subject
                
                results[depth].append((target, edge))
                
                if target not in visited:
                    visited.add(target)
                    queue.append((target, depth + 1))
        
        return dict(results)
    
    def dfs(
        self,
        start: str,
        max_depth: int = 3,
        predicate_filter: Optional[List[str]] = None,
        time_filter: Optional[datetime] = None,
        direction: str = "both"
    ) -> List[Tuple[str, TemporalFact, int]]:
        """深度优先搜索
        
        Args:
            start: 起始节点名称或UUID
            max_depth: 最大深度
            predicate_filter: 谓词过滤列表
            time_filter: 时间过滤
            direction: 方向
        
        Returns:
            [(node_id, edge, depth), ...] 按访问顺序
        """
        start_node = self.get_node_by_name(start) or self.get_node(start)
        if not start_node:
            return []
        
        start_uuid = start_node.uuid
        visited = {start_uuid}
        results: List[Tuple[str, TemporalFact, int]] = []
        
        def _dfs(node_id: str, depth: int):
            if depth >= max_depth:
                return
            
            edge_ids: Set[str] = set()
            if direction in ("out", "both"):
                edge_ids.update(self._indexes.outgoing.get(node_id, set()))
            if direction in ("in", "both"):
                edge_ids.update(self._indexes.incoming.get(node_id, set()))
            
            for edge_id in edge_ids:
                edge = self.edges.get(edge_id)
                if not edge:
                    continue
                
                if time_filter and not edge.is_valid_at(time_filter):
                    continue
                
                if predicate_filter and edge.predicate not in predicate_filter:
                    continue
                
                target = edge.object if edge.subject == node_id else edge.subject
                
                results.append((target, edge, depth))
                
                if target not in visited:
                    visited.add(target)
                    _dfs(target, depth + 1)
        
        _dfs(start_uuid, 0)
        return results
    
    def find_path(
        self,
        source: str,
        target: str,
        max_depth: int = 5,
        time_filter: Optional[datetime] = None
    ) -> Optional[List[Tuple[str, TemporalFact]]]:
        """查找两个节点间的路径
        
        Args:
            source: 源节点
            target: 目标节点
            max_depth: 最大深度
            time_filter: 时间过滤
        
        Returns:
            路径 [(node_id, edge), ...] 或 None
        """
        source_node = self.get_node_by_name(source) or self.get_node(source)
        target_node = self.get_node_by_name(target) or self.get_node(target)
        
        if not source_node or not target_node:
            return None
        
        if source_node.uuid == target_node.uuid:
            return []
        
        source_uuid = source_node.uuid
        target_uuid = target_node.uuid
        
        visited = {source_uuid}
        queue = [(source_uuid, [])]
        
        while queue:
            current, path = queue.pop(0)
            
            if len(path) >= max_depth:
                continue
            
            edge_ids = self._indexes.outgoing.get(current, set())
            
            for edge_id in edge_ids:
                edge = self.edges.get(edge_id)
                if not edge:
                    continue
                
                if time_filter and not edge.is_valid_at(time_filter):
                    continue
                
                neighbor = edge.object
                
                if neighbor == target_uuid:
                    return path + [(neighbor, edge)]
                
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [(neighbor, edge)]))
        
        return None
    
    # =========================================================================
    # 搜索 API
    # =========================================================================
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        search_nodes: bool = True,
        search_edges: bool = True,
        time_filter: Optional[datetime] = None
    ) -> QueryResult:
        """全文搜索
        
        Args:
            query: 查询文本
            top_k: 返回数量
            search_nodes: 是否搜索节点
            search_edges: 是否搜索边
            time_filter: 时间过滤
        
        Returns:
            查询结果
        """
        import time as time_module
        start_time = time_module.time()
        
        result = QueryResult()
        
        if not self._fulltext_index:
            return result
        
        # 全文搜索
        search_results = self._fulltext_index.search(query, top_k * 2)
        
        for doc_id, score in search_results:
            if doc_id.startswith("node:") and search_nodes:
                node_uuid = doc_id[5:]
                node = self.nodes.get(node_uuid)
                if node and node.is_active():
                    result.nodes.append(node)
            
            elif doc_id.startswith("edge:") and search_edges:
                edge_uuid = doc_id[5:]
                edge = self.edges.get(edge_uuid)
                if edge:
                    if time_filter and not edge.is_valid_at(time_filter):
                        continue
                    result.edges.append(edge)
        
        # 限制结果数量
        result.nodes = result.nodes[:top_k]
        result.edges = result.edges[:top_k]
        result.total_count = len(result.nodes) + len(result.edges)
        result.query_time_ms = (time_module.time() - start_time) * 1000
        
        return result
    
    # =========================================================================
    # 统计与工具
    # =========================================================================
    
    def stats(self) -> Dict[str, Any]:
        """获取图谱统计信息"""
        return {
            'version': self.VERSION,
            'node_count': len(self.nodes),
            'edge_count': len(self.edges),
            'episode_count': len(self.episodes),
            'node_types': {
                nt.value: len(self._indexes.by_node_type.get(nt, set()))
                for nt in NodeType
            },
            'predicate_count': len(self._indexes.by_predicate),
            'pending_contradictions': len(self._pending_contradictions),
            'fulltext_enabled': self._fulltext_index is not None,
            'temporal_enabled': self._temporal_index is not None
        }
    
    def clear(self):
        """清空图谱"""
        self.nodes.clear()
        self.edges.clear()
        self.episodes.clear()
        self._indexes = GraphIndexes()
        self._name_to_uuid.clear()
        self._pending_contradictions.clear()
        
        if self._temporal_index:
            self._temporal_index.clear()
        if self._fulltext_index:
            self._fulltext_index.clear()
        
        self._dirty = True
        self._save()


__all__ = [
    'QueryResult',
    'TemporalKnowledgeGraph',
]
