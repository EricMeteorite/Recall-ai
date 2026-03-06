"""时序知识图谱 - Recall 4.0 核心模块

设计理念：
1. 三时态支持（事实时间、知识时间、系统时间）
2. 零依赖本地存储，可选外部数据库（Kuzu）
3. 与现有 KnowledgeGraph 完全兼容，可并行使用
4. 高效索引：时态索引 + 全文索引 + 向量索引

不修改现有 KnowledgeGraph，而是作为新的增强版本。

Kuzu 集成：
- 设置 TEMPORAL_GRAPH_BACKEND=kuzu 启用 Kuzu 后端
- 设置 KUZU_BUFFER_POOL_SIZE=1024 配置缓冲池大小（MB）
- Kuzu 提供高性能图存储，比文件后端快 2-10x
"""

from __future__ import annotations

import os
import json
import logging
import atexit
import uuid as uuid_lib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Optional, Tuple, Any, Union, TYPE_CHECKING
from collections import defaultdict

from ..models.temporal import (
    NodeType, EdgeType, ContradictionType, ResolutionStrategy,
    TemporalFact, UnifiedNode, EpisodicNode, EpisodeType,
    Contradiction, ResolutionResult, GraphIndexes
)
from ..index.temporal_index import TemporalIndex, TemporalEntry, TimeRange
from ..index.fulltext_index import FullTextIndex


# Kuzu 可用性检查
KUZU_AVAILABLE = False
KuzuGraphBackend = None
GraphNode = None
GraphEdge = None

try:
    from .backends.kuzu_backend import KuzuGraphBackend as _KuzuBackend, KUZU_AVAILABLE as _KUZU_AVAIL
    from .backends.base import GraphNode as _GraphNode, GraphEdge as _GraphEdge
    KUZU_AVAILABLE = _KUZU_AVAIL
    KuzuGraphBackend = _KuzuBackend
    GraphNode = _GraphNode
    GraphEdge = _GraphEdge
except ImportError:
    pass


logger = logging.getLogger(__name__)


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
    2. 零依赖：纯本地 JSON 存储 或 Kuzu 嵌入式图数据库
    3. 高效索引：时态索引 + 全文索引
    4. 矛盾检测：自动检测并支持多种解决策略
    5. 图遍历：BFS/DFS + 时态过滤
    
    与现有 KnowledgeGraph 的关系：
    - 完全独立，不修改现有类
    - 可以通过迁移工具将旧数据导入
    - 新功能使用此类，旧功能继续使用原有类
    
    后端选项：
    - file: 本地 JSON 文件（默认，零依赖）
    - kuzu: Kuzu 嵌入式图数据库（高性能，需安装 kuzu）
    """
    
    VERSION = "4.0.0"
    
    def __init__(
        self,
        data_path: str,
        backend: str = "file",          # file | kuzu
        scope: str = "global",          # global | isolated
        enable_fulltext: bool = True,   # 是否启用全文索引
        enable_temporal: bool = True,   # 是否启用时态索引
        auto_save: bool = True,         # 是否自动保存
        kuzu_buffer_pool_size: int = 1024  # Kuzu 缓冲池大小（MB）
    ):
        """初始化时序知识图谱
        
        Args:
            data_path: 数据存储路径
            backend: 存储后端
                - file: 本地 JSON 文件（默认）
                - kuzu: Kuzu 嵌入式图数据库
                - local: 旧名称，等同于 file
            scope: 作用域
            enable_fulltext: 是否启用全文索引
            enable_temporal: 是否启用时态索引
            auto_save: 是否自动保存
            kuzu_buffer_pool_size: Kuzu 缓冲池大小（MB），默认 1024MB
        """
        self.data_path = data_path
        # 向后兼容：映射旧值 'local' 到 'file'
        if backend == "local":
            backend = "file"
        self.backend = backend
        self.scope = scope
        self.auto_save = auto_save
        self._kuzu_buffer_pool_size = kuzu_buffer_pool_size
        
        # Kuzu 后端实例（当 backend='kuzu' 时使用）
        self._kuzu_backend: Optional[Any] = None
        
        # 存储目录
        self.graph_dir = os.path.join(data_path, 'temporal_graph')
        self.nodes_file = os.path.join(self.graph_dir, 'nodes.json')
        self.edges_file = os.path.join(self.graph_dir, 'edges.json')
        self.episodes_file = os.path.join(self.graph_dir, 'episodes.json')
        self.meta_file = os.path.join(self.graph_dir, 'meta.json')
        
        # 核心存储（内存缓存 + 后端）
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
        
        # v7.0: 延迟批量保存（避免每次 add_node/add_edge 都全量 dump 4 个 JSON）
        self._save_count = 0
        self._save_threshold = 50   # 每 50 次修改才做一次全量保存
        
        # v7.0.2: 加载阶段标志位（防止从 Kuzu 加载数据时又写回 Kuzu 造成循环）
        self._loading_from_backend = False
        
        # 初始化后端
        self._init_backend()
        
        # 进程退出安全网：确保未刷盘的修改不丢失
        atexit.register(self._atexit_flush)
        
        # 加载数据
        self._load()
    
    def _init_backend(self):
        """初始化存储后端
        
        根据 self.backend 选择初始化：
        - file: 使用 JSON 文件存储
        - kuzu: 使用 Kuzu 嵌入式图数据库
        """
        if self.backend == "kuzu":
            if not KUZU_AVAILABLE:
                raise ImportError(
                    "Kuzu backend requested but kuzu is not installed.\n"
                    "Install with: pip install kuzu\n"
                    "Or set TEMPORAL_GRAPH_BACKEND=file to use file backend."
                )
            
            kuzu_path = os.path.join(self.data_path, 'kuzu')
            os.makedirs(kuzu_path, exist_ok=True)
            
            try:
                self._kuzu_backend = KuzuGraphBackend(
                    data_path=kuzu_path,
                    buffer_pool_size=self._kuzu_buffer_pool_size
                )
                _safe_print(f"[TemporalKnowledgeGraph] Kuzu backend initialized at {kuzu_path}")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Kuzu backend: {e}")
        else:
            # 文件后端，确保目录存在
            os.makedirs(self.graph_dir, exist_ok=True)
            _safe_print(f"[TemporalKnowledgeGraph] File backend initialized at {self.graph_dir}")
    
    # =========================================================================
    # 持久化
    # =========================================================================
    
    def _load(self):
        """加载图谱数据
        
        根据后端类型选择加载方式：
        - file: 从 JSON 文件加载
        - kuzu: 从 Kuzu 数据库加载
        """
        if self.backend == "kuzu" and self._kuzu_backend:
            self._load_from_kuzu()
        else:
            self._load_from_file()
    
    def _load_from_file(self):
        """从 JSON 文件加载图谱数据"""
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
    
    def _load_from_kuzu(self):
        """从 Kuzu 数据库加载图谱数据"""
        if not self._kuzu_backend:
            return
        
        # v7.0.2: 设置标志位，防止 _index_node/_index_edge 将数据回写 Kuzu
        self._loading_from_backend = True
        try:
            # 从 Kuzu 查询所有节点
            result = self._kuzu_backend.conn.execute(
                "MATCH (n:Node) RETURN n.id, n.name, n.node_type, n.properties, n.created_at"
            )
            
            for row in result:
                node_id, name, node_type, props_json, created_at = row
                props = json.loads(props_json) if props_json else {}
                
                # 从 properties 中恢复完整的 UnifiedNode
                # 注意：Kuzu 返回的时间字段可能是字符串
                created_at_val = created_at
                if isinstance(created_at_val, str):
                    try:
                        created_at_val = datetime.fromisoformat(created_at_val)
                    except ValueError:
                        created_at_val = datetime.now()
                
                updated_at_raw = props.get('updated_at')
                if isinstance(updated_at_raw, str):
                    try:
                        updated_at_val = datetime.fromisoformat(updated_at_raw)
                    except ValueError:
                        updated_at_val = datetime.now()
                elif isinstance(updated_at_raw, datetime):
                    updated_at_val = updated_at_raw
                else:
                    updated_at_val = datetime.now()
                
                node = UnifiedNode(
                    uuid=node_id,
                    name=name,
                    node_type=NodeType(node_type) if node_type else NodeType.ENTITY,
                    content=props.get('content', ''),
                    summary=props.get('summary', ''),
                    attributes=props.get('attributes', {}),
                    aliases=props.get('aliases', []),
                    group_id=props.get('group_id', 'default'),
                    user_id=props.get('user_id', 'default'),
                    created_at=created_at_val or datetime.now(),
                    updated_at=updated_at_val,
                    verification_count=props.get('verification_count', 0)
                )
                self.nodes[node.uuid] = node
                self._index_node(node)
            
            # 从 Kuzu 查询所有边
            edge_result = self._kuzu_backend.conn.execute(
                "MATCH (a:Node)-[r:Edge]->(b:Node) RETURN r.edge_id, a.id, b.id, r.edge_type, r.properties, r.weight, r.created_at"
            )
            
            for row in edge_result:
                edge_id, source_id, target_id, edge_type, props_json, weight, created_at = row
                props = json.loads(props_json) if props_json else {}
                
                # 从 properties 中恢复完整的 TemporalFact
                # 注意：props 中的时间字段是字符串，需要转换
                valid_from_val = props.get('valid_from')
                if valid_from_val and isinstance(valid_from_val, str):
                    try:
                        valid_from_val = datetime.fromisoformat(valid_from_val)
                    except ValueError:
                        valid_from_val = None
                valid_until_val = props.get('valid_until')
                if valid_until_val and isinstance(valid_until_val, str):
                    try:
                        valid_until_val = datetime.fromisoformat(valid_until_val)
                    except ValueError:
                        valid_until_val = None
                created_at_val = created_at
                if isinstance(created_at_val, str):
                    try:
                        created_at_val = datetime.fromisoformat(created_at_val)
                    except ValueError:
                        created_at_val = datetime.now()
                
                edge = TemporalFact(
                    uuid=edge_id,
                    subject=source_id,
                    object=target_id,
                    predicate=edge_type or '',
                    fact=props.get('fact', ''),
                    valid_from=valid_from_val,
                    valid_until=valid_until_val,
                    source_text=props.get('source_text', ''),
                    confidence=weight if weight else props.get('confidence', 0.5),
                    group_id=props.get('group_id', 'default'),
                    user_id=props.get('user_id', 'default'),
                    created_at=created_at_val or datetime.now()
                )
                self.edges[edge.uuid] = edge
                self._index_edge(edge)
            
            _safe_print(f"[TemporalKnowledgeGraph] Loaded from Kuzu: {len(self.nodes)} nodes, {len(self.edges)} edges")
            
        except Exception as e:
            logger.error(f"[TemporalKnowledgeGraph] Failed to load from Kuzu: {e}")
            _safe_print(f"[TemporalKnowledgeGraph] 从 Kuzu 加载失败: {e}")
        finally:
            # v7.0.2: 恢复标志位
            self._loading_from_backend = False
        
        # 情节仍然使用 JSON 文件存储（Kuzu 主要用于节点和边）
        if os.path.exists(self.episodes_file):
            try:
                with open(self.episodes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item in data:
                    episode = EpisodicNode.from_dict(item)
                    self.episodes[episode.uuid] = episode
            except Exception as e:
                _safe_print(f"[TemporalKnowledgeGraph] 加载情节失败: {e}")
    
    def _mark_dirty(self):
        """标记脏数据并使用延迟保存策略

        每次写操作调用此方法代替直接 _save()，
        仅当累积修改达到阈值时才执行全量 JSON dump，
        将单次写入从 O(N) 降低到分摊 O(1)。
        """
        self._dirty = True
        self._save_count += 1
        if self.auto_save and self._save_count >= self._save_threshold:
            self._save()
            self._save_count = 0

    def _atexit_flush(self):
        """进程退出时确保所有脏数据刷盘"""
        if self._dirty:
            try:
                self._save()
            except Exception:
                pass  # 退出时不抛异常

    def _save(self):
        """保存图谱数据
        
        根据后端类型选择保存方式：
        - file: 保存到 JSON 文件（同时用作备份）
        - kuzu: Kuzu 是实时同步的，这里主要保存情节和元数据
        """
        if not self._dirty and not self.auto_save:
            return
        
        os.makedirs(self.graph_dir, exist_ok=True)
        
        # JSON 文件始终作为备份保存（即使使用 Kuzu）
        # 原子写入：tmp+rename 防止断电损坏
        from recall.utils.atomic_write import atomic_json_dump
        
        # 保存节点
        atomic_json_dump([n.to_dict() for n in self.nodes.values()], self.nodes_file, indent=2)
        
        # 保存边
        atomic_json_dump([e.to_dict() for e in self.edges.values()], self.edges_file, indent=2)
        
        # 保存情节
        atomic_json_dump([e.to_dict() for e in self.episodes.values()], self.episodes_file, indent=2)
        
        # 保存元数据
        meta = {
            'version': self.VERSION,
            'backend': self.backend,
            'node_count': len(self.nodes),
            'edge_count': len(self.edges),
            'episode_count': len(self.episodes),
            'updated_at': datetime.now().isoformat()
        }
        atomic_json_dump(meta, self.meta_file, indent=2)
        
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
    
    @property
    def kuzu_backend(self) -> Optional[Any]:
        """获取 Kuzu 后端实例（如果启用）
        
        Returns:
            KuzuGraphBackend 实例，如果未使用 Kuzu 则返回 None
        """
        return self._kuzu_backend
    
    @property
    def is_kuzu_enabled(self) -> bool:
        """检查是否启用了 Kuzu 后端"""
        return self.backend == "kuzu" and self._kuzu_backend is not None
    
    # =========================================================================
    # 内存索引管理
    # =========================================================================
    
    def _index_node(self, node: UnifiedNode):
        """索引节点到内存并同步到后端"""
        self._indexes.add_node(node.uuid, node.node_type)
        self._name_to_uuid[node.name.lower()] = node.uuid
        for alias in node.aliases:
            self._name_to_uuid[alias.lower()] = node.uuid
        
        # 全文索引
        if self._fulltext_index:
            text = f"{node.name} {node.summary} {node.content}"
            self._fulltext_index.add(f"node:{node.uuid}", text)
        
        # 同步到 Kuzu（加载阶段跳过，避免循环写入）
        if self.backend == "kuzu" and self._kuzu_backend and not self._loading_from_backend:
            self._sync_node_to_kuzu(node)
    
    def _sync_node_to_kuzu(self, node: UnifiedNode):
        """同步节点到 Kuzu 后端"""
        if not self._kuzu_backend or not GraphNode:
            return
        
        try:
            # 将 UnifiedNode 转换为 GraphNode
            # 将额外属性存储在 properties 中
            properties = {
                'content': node.content,
                'summary': node.summary,
                'attributes': node.attributes,
                'aliases': node.aliases,
                'group_id': node.group_id,
                'user_id': node.user_id,
                'updated_at': node.updated_at.isoformat() if node.updated_at else None,
                'verification_count': node.verification_count,
                'source_episodes': node.source_episodes
            }
            
            graph_node = GraphNode(
                id=node.uuid,
                name=node.name,
                node_type=node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type),
                properties=properties,
                created_at=node.created_at
            )
            
            self._kuzu_backend.add_node(graph_node)
        except Exception as e:
            logger.warning(f"[TemporalKnowledgeGraph] Failed to sync node to Kuzu: {e}")
    
    def _index_edge(self, edge: TemporalFact):
        """索引边到内存并同步到后端"""
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
        
        # 同步到 Kuzu（加载阶段跳过，避免循环写入）
        if self.backend == "kuzu" and self._kuzu_backend and not self._loading_from_backend:
            self._sync_edge_to_kuzu(edge)
    
    def _sync_edge_to_kuzu(self, edge: TemporalFact):
        """同步边到 Kuzu 后端"""
        if not self._kuzu_backend or not GraphEdge:
            return
        
        try:
            # 将 TemporalFact 转换为 GraphEdge
            # 将额外属性存储在 properties 中
            properties = {
                'fact': edge.fact,
                'valid_from': edge.valid_from.isoformat() if edge.valid_from else None,
                'valid_until': edge.valid_until.isoformat() if edge.valid_until else None,
                'known_at': edge.known_at.isoformat() if edge.known_at else None,
                'source_text': edge.source_text,
                'confidence': edge.confidence,
                'group_id': edge.group_id,
                'user_id': edge.user_id
            }
            
            graph_edge = GraphEdge(
                id=edge.uuid,
                source_id=edge.subject,
                target_id=edge.object,
                edge_type=edge.predicate,
                properties=properties,
                weight=edge.confidence,
                created_at=edge.created_at
            )
            
            self._kuzu_backend.add_edge(graph_edge)
        except Exception as e:
            logger.warning(f"[TemporalKnowledgeGraph] Failed to sync edge to Kuzu: {e}")
    
    def _unindex_node(self, node: UnifiedNode):
        """从内存索引移除节点"""
        self._indexes.remove_node(node.uuid, node.node_type)
        self._name_to_uuid.pop(node.name.lower(), None)
        for alias in node.aliases:
            self._name_to_uuid.pop(alias.lower(), None)
        
        if self._fulltext_index:
            self._fulltext_index.remove(f"node:{node.uuid}")
        
        # 从 Kuzu 删除
        if self.backend == "kuzu" and self._kuzu_backend:
            try:
                self._kuzu_backend.delete_node(node.uuid)
            except Exception as e:
                logger.warning(f"[TemporalKnowledgeGraph] Failed to delete node from Kuzu: {e}")
    
    def _unindex_edge(self, edge: TemporalFact):
        """从内存索引移除边"""
        self._indexes.remove_edge(edge.uuid, edge.subject, edge.object, edge.predicate)
        
        if self._temporal_index:
            self._temporal_index.remove(edge.uuid)
        
        if self._fulltext_index:
            self._fulltext_index.remove(f"edge:{edge.uuid}")
        
        # 从 Kuzu 删除
        if self.backend == "kuzu" and self._kuzu_backend:
            try:
                self._kuzu_backend.delete_edge(edge.uuid)
            except Exception as e:
                logger.warning(f"[TemporalKnowledgeGraph] Failed to delete edge from Kuzu: {e}")
    
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
                self._mark_dirty()
                return existing
            
            # 直接添加传入的节点
            self.nodes[node.uuid] = node
            self._index_node(node)
            self._mark_dirty()
            
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
            self._mark_dirty()
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
        self._mark_dirty()
        
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
        self._mark_dirty()
        
        return node
    
    def remove_node(self, uuid: str) -> bool:
        """移除节点（软删除）"""
        node = self.nodes.get(uuid)
        if not node:
            return False
        
        node.expire()
        self._unindex_node(node)
        self._mark_dirty()
        
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
            
            self._mark_dirty()
            
            return edge, contradictions
        
        # 否则，按照参数创建边
        subject = subject_or_fact
        
        # 支持传入 UnifiedNode 对象
        if isinstance(subject, UnifiedNode):
            subject_node = subject
            subject = subject.name
        else:
            subject_node = self.get_node_by_name(subject) or self.get_node(subject)
        
        if isinstance(object_, UnifiedNode):
            object_node = object_
            object_ = object_node.name
        else:
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
        
        self._mark_dirty()
        
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
        
        self._mark_dirty()
        
        return edge
    
    def expire_edge(self, uuid: str) -> bool:
        """使边失效"""
        edge = self.edges.get(uuid)
        if not edge:
            return False
        
        edge.expire()
        self._unindex_edge(edge)
        self._mark_dirty()
        
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
        self._mark_dirty()
        
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
    
    def get_entity_timeline(
        self,
        entity_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取实体的完整时间线（REST API 友好格式）
        
        封装 query_timeline()，返回可序列化的字典列表。
        
        Args:
            entity_name: 实体名称
            start_time: 时间范围起始（可选）
            end_time: 时间范围结束（可选）
            limit: 最大返回条数
        
        Returns:
            [{"time": ..., "predicate": ..., "object": ..., "event_type": ..., "confidence": ...}, ...]
        """
        raw = self.query_timeline(
            subject=entity_name,
            start=start_time,
            end=end_time
        )
        
        results: List[Dict[str, Any]] = []
        for ts, fact, event_type in raw:
            # 获取 object 节点名称
            object_node = self.get_node(fact.object_uuid)
            object_name = object_node.name if object_node else fact.object_uuid
            
            results.append({
                "time": ts.isoformat() if ts else None,
                "predicate": fact.predicate,
                "object": object_name,
                "event_type": event_type,
                "confidence": fact.confidence,
                "fact_uuid": fact.uuid,
            })
            if len(results) >= limit:
                break
        
        return results
    
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
            self._mark_dirty()
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
    
    def clear_user(self, user_id: str) -> int:
        """清空指定用户的所有数据（节点、边、episodes）
        
        这是用户级别的清空操作，不会影响其他用户的数据。
        
        Args:
            user_id: 要清空的用户ID
        
        Returns:
            int: 删除的节点数量
        """
        deleted_count = 0
        
        # 1. 找出该用户的所有节点并清理索引
        user_node_ids = set()
        for node_id, node in list(self.nodes.items()):
            if getattr(node, 'user_id', None) == user_id:
                user_node_ids.add(node_id)
                # 清理全文索引
                if self._fulltext_index:
                    self._fulltext_index.remove(f"node:{node.uuid}")
                # 清理名称索引
                if node.name in self._name_to_uuid:
                    del self._name_to_uuid[node.name]
                for alias in getattr(node, 'aliases', []):
                    if alias in self._name_to_uuid:
                        del self._name_to_uuid[alias]
                del self.nodes[node_id]
                deleted_count += 1
        
        # 2. 删除与这些节点相关的所有边
        edges_to_delete = []
        for edge_id, edge in self.edges.items():
            # 边的 subject 和 object 对应节点 UUID
            if edge.subject in user_node_ids or edge.object in user_node_ids:
                edges_to_delete.append(edge_id)
            # 同时检查边本身的 user_id
            elif getattr(edge, 'user_id', None) == user_id:
                edges_to_delete.append(edge_id)
        for edge_id in edges_to_delete:
            edge = self.edges[edge_id]
            # 清理时态索引
            if self._temporal_index:
                self._temporal_index.remove(edge.uuid)
            # 清理全文索引
            if self._fulltext_index:
                self._fulltext_index.remove(f"edge:{edge.uuid}")
            del self.edges[edge_id]
        
        # 3. 删除该用户的 episodes
        episodes_to_delete = []
        for episode_id, episode in self.episodes.items():
            if getattr(episode, 'user_id', None) == user_id:
                episodes_to_delete.append(episode_id)
        for episode_id in episodes_to_delete:
            del self.episodes[episode_id]
        
        # 4. 重建索引并保存
        total_deleted = deleted_count + len(edges_to_delete) + len(episodes_to_delete)
        if total_deleted > 0:
            self._rebuild_indexes()
            self._dirty = True
            self._save()
        
        return deleted_count
    
    def _rebuild_indexes(self):
        """重建所有索引"""
        self._indexes = GraphIndexes()
        for node_id, node in self.nodes.items():
            self._indexes.add_node(node_id, node.node_type)
        for edge_id, edge in self.edges.items():
            self._indexes.add_edge(edge_id, edge.subject, edge.object, edge.predicate)
    
    def clear(self):
        """清空图谱（全部数据）"""
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
    
    # =========================================================================
    # KnowledgeGraph 兼容层
    # 
    # 以下方法提供与老版 KnowledgeGraph 的 API 兼容性，
    # 使得可以无缝替换使用，实现统一的图存储后端。
    # =========================================================================
    
    # 预定义的关系类型（v5.0 支持模式感知，从 KnowledgeGraph 统一获取）
    from .knowledge_graph import get_relation_types as _get_relation_types
    RELATION_TYPES = _get_relation_types()
    
    @property
    def outgoing(self) -> Dict[str, List[Any]]:
        """兼容属性：返回出边字典（source_id -> [Relation, ...]）
        
        返回格式与老版 KnowledgeGraph.outgoing 兼容，
        将 TemporalFact 转换为类似 Relation 的对象。
        """
        from dataclasses import dataclass
        
        @dataclass
        class LegacyRelation:
            """兼容老版 Relation 的数据结构"""
            source_id: str
            target_id: str
            relation_type: str
            properties: Dict = None
            created_turn: int = 0
            confidence: float = 0.5
            source_text: str = ""
            valid_at: Optional[str] = None
            invalid_at: Optional[str] = None
            fact: str = ""
        
        result: Dict[str, List[LegacyRelation]] = {}
        
        for source_uuid, edge_ids in self._indexes.outgoing.items():
            # 获取源节点名称
            source_node = self.nodes.get(source_uuid)
            if not source_node:
                continue
            source_name = source_node.name
            
            if source_name not in result:
                result[source_name] = []
            
            for edge_id in edge_ids:
                edge = self.edges.get(edge_id)
                if not edge:
                    continue
                
                # 获取目标节点名称
                target_node = self.nodes.get(edge.object)
                target_name = target_node.name if target_node else edge.object
                
                rel = LegacyRelation(
                    source_id=source_name,
                    target_id=target_name,
                    relation_type=edge.predicate,
                    properties={},
                    created_turn=0,
                    confidence=edge.confidence,
                    source_text=edge.source_text,
                    valid_at=edge.valid_from.isoformat() if edge.valid_from else None,
                    invalid_at=edge.valid_until.isoformat() if edge.valid_until else None,
                    fact=edge.fact
                )
                result[source_name].append(rel)
        
        return result
    
    @property
    def incoming(self) -> Dict[str, List[Any]]:
        """兼容属性：返回入边字典（target_id -> [Relation, ...]）"""
        from dataclasses import dataclass
        
        @dataclass
        class LegacyRelation:
            source_id: str
            target_id: str
            relation_type: str
            properties: Dict = None
            created_turn: int = 0
            confidence: float = 0.5
            source_text: str = ""
            valid_at: Optional[str] = None
            invalid_at: Optional[str] = None
            fact: str = ""
        
        result: Dict[str, List[LegacyRelation]] = {}
        
        for target_uuid, edge_ids in self._indexes.incoming.items():
            target_node = self.nodes.get(target_uuid)
            if not target_node:
                continue
            target_name = target_node.name
            
            if target_name not in result:
                result[target_name] = []
            
            for edge_id in edge_ids:
                edge = self.edges.get(edge_id)
                if not edge:
                    continue
                
                source_node = self.nodes.get(edge.subject)
                source_name = source_node.name if source_node else edge.subject
                
                rel = LegacyRelation(
                    source_id=source_name,
                    target_id=target_name,
                    relation_type=edge.predicate,
                    properties={},
                    created_turn=0,
                    confidence=edge.confidence,
                    source_text=edge.source_text,
                    valid_at=edge.valid_from.isoformat() if edge.valid_from else None,
                    invalid_at=edge.valid_until.isoformat() if edge.valid_until else None,
                    fact=edge.fact
                )
                result[target_name].append(rel)
        
        return result
    
    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: Dict = None,
        turn: int = 0,
        source_text: str = "",
        confidence: float = 0.5,
        valid_at: Optional[str] = None,
        invalid_at: Optional[str] = None,
        fact: str = ""
    ) -> Any:
        """兼容方法：添加关系（与老版 KnowledgeGraph.add_relation 签名兼容）
        
        内部转换为 add_edge 调用。
        
        Args:
            source_id: 源实体ID/名称
            target_id: 目标实体ID/名称
            relation_type: 关系类型
            properties: 关系属性（保留但不使用）
            turn: 创建轮次（保留但不使用）
            source_text: 原文依据
            confidence: 置信度 (0-1)
            valid_at: 事实生效时间 (ISO 8601)
            invalid_at: 事实失效时间 (ISO 8601)
            fact: 自然语言事实描述
        
        Returns:
            兼容的 Relation-like 对象
        """
        from dataclasses import dataclass
        
        @dataclass
        class LegacyRelation:
            source_id: str
            target_id: str
            relation_type: str
            properties: Dict = None
            created_turn: int = 0
            confidence: float = 0.5
            source_text: str = ""
            valid_at: Optional[str] = None
            invalid_at: Optional[str] = None
            fact: str = ""
        
        # 解析时间
        valid_from = None
        valid_until = None
        if valid_at:
            try:
                valid_from = datetime.fromisoformat(valid_at)
            except ValueError:
                pass
        if invalid_at:
            try:
                valid_until = datetime.fromisoformat(invalid_at)
            except ValueError:
                pass
        
        # 检查是否已存在相同关系
        existing_edges = self.get_edges_by_subject(source_id, predicate=relation_type)
        for edge in existing_edges:
            target_node = self.nodes.get(edge.object)
            if target_node and target_node.name.lower() == target_id.lower():
                # 更新置信度
                edge.confidence = min(1.0, edge.confidence + 0.1)
                self._mark_dirty()
                
                return LegacyRelation(
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation_type,
                    properties=properties or {},
                    created_turn=turn,
                    confidence=edge.confidence,
                    source_text=edge.source_text,
                    valid_at=valid_at,
                    invalid_at=invalid_at,
                    fact=edge.fact
                )
        
        # 创建新关系
        edge, _ = self.add_edge(
            subject_or_fact=source_id,
            predicate=relation_type,
            object_=target_id,
            fact=fact or f"{source_id} {relation_type} {target_id}",
            valid_from=valid_from,
            valid_until=valid_until,
            source_text=source_text,
            confidence=confidence,
            check_contradiction=False  # 兼容模式下不检查矛盾
        )
        
        return LegacyRelation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=properties or {},
            created_turn=turn,
            confidence=confidence,
            source_text=source_text,
            valid_at=valid_at,
            invalid_at=invalid_at,
            fact=fact
        )
    
    def add_entity(self, entity_id: str, entity_type: str = "ENTITY") -> bool:
        """兼容方法：添加实体
        
        Args:
            entity_id: 实体ID/名称
            entity_type: 实体类型
        
        Returns:
            bool: 是否成功
        """
        # 检查是否已存在
        existing = self.get_node_by_name(entity_id)
        if existing:
            return True
        
        # 通过添加一个 IS_A 关系来记录实体
        self.add_relation(
            source_id=entity_id,
            target_id=entity_type,
            relation_type="IS_A"
        )
        return True
    
    def get_neighbors(
        self,
        entity_id: str,
        relation_type: str = None,
        direction: str = 'both'
    ) -> List[Tuple[str, Any]]:
        """兼容方法：获取邻居实体
        
        与老版 KnowledgeGraph.get_neighbors 签名兼容。
        
        Args:
            entity_id: 实体ID/名称
            relation_type: 可选，过滤关系类型
            direction: 'out'=出边, 'in'=入边, 'both'=双向
        
        Returns:
            [(邻居名称, Relation对象), ...]
        """
        from dataclasses import dataclass
        
        @dataclass
        class LegacyRelation:
            source_id: str
            target_id: str
            relation_type: str
            properties: Dict = None
            created_turn: int = 0
            confidence: float = 0.5
            source_text: str = ""
            valid_at: Optional[str] = None
            invalid_at: Optional[str] = None
            fact: str = ""
        
        neighbors = []
        
        # 获取节点
        node = self.get_node_by_name(entity_id) or self.get_node(entity_id)
        if not node:
            return neighbors
        
        node_uuid = node.uuid
        
        # 出边
        if direction in ('out', 'both'):
            edge_ids = self._indexes.outgoing.get(node_uuid, set())
            for edge_id in edge_ids:
                edge = self.edges.get(edge_id)
                if not edge:
                    continue
                if relation_type and edge.predicate != relation_type:
                    continue
                
                target_node = self.nodes.get(edge.object)
                target_name = target_node.name if target_node else edge.object
                
                rel = LegacyRelation(
                    source_id=node.name,
                    target_id=target_name,
                    relation_type=edge.predicate,
                    confidence=edge.confidence,
                    source_text=edge.source_text,
                    valid_at=edge.valid_from.isoformat() if edge.valid_from else None,
                    invalid_at=edge.valid_until.isoformat() if edge.valid_until else None,
                    fact=edge.fact
                )
                neighbors.append((target_name, rel))
        
        # 入边
        if direction in ('in', 'both'):
            edge_ids = self._indexes.incoming.get(node_uuid, set())
            for edge_id in edge_ids:
                edge = self.edges.get(edge_id)
                if not edge:
                    continue
                if relation_type and edge.predicate != relation_type:
                    continue
                
                source_node = self.nodes.get(edge.subject)
                source_name = source_node.name if source_node else edge.subject
                
                rel = LegacyRelation(
                    source_id=source_name,
                    target_id=node.name,
                    relation_type=edge.predicate,
                    confidence=edge.confidence,
                    source_text=edge.source_text,
                    valid_at=edge.valid_from.isoformat() if edge.valid_from else None,
                    invalid_at=edge.valid_until.isoformat() if edge.valid_until else None,
                    fact=edge.fact
                )
                neighbors.append((source_name, rel))
        
        return neighbors
    
    def get_relations_for_entity(self, entity_name: str) -> List[Any]:
        """兼容方法：获取实体的所有关系
        
        Args:
            entity_name: 实体名称
        
        Returns:
            [Relation, ...] - 与该实体相关的所有关系（出边和入边）
        """
        neighbors = self.get_neighbors(entity_name, direction='both')
        return [rel for _, rel in neighbors]
    
    def get_subgraph(self, entity_id: str, depth: int = 2) -> Dict:
        """兼容方法：获取以某实体为中心的子图
        
        Args:
            entity_id: 实体名称
            depth: 遍历深度
        
        Returns:
            {'nodes': [节点名称列表], 'edges': [边信息列表]}
        """
        visited = set()
        nodes = []
        edges = []
        queue = [(entity_id, 0)]
        
        while queue:
            current, current_depth = queue.pop(0)
            
            if current in visited or current_depth > depth:
                continue
            
            visited.add(current)
            nodes.append(current)
            
            for neighbor_name, rel in self.get_neighbors(current):
                edges.append({
                    'source': rel.source_id,
                    'target': rel.target_id,
                    'type': rel.relation_type
                })
                if neighbor_name not in visited:
                    queue.append((neighbor_name, current_depth + 1))
        
        return {'nodes': nodes, 'edges': edges}
    
    def traverse(
        self,
        start_entity: str,
        max_depth: int = 2,
        relation_types: Optional[List[str]] = None
    ) -> Dict:
        """兼容方法：图遍历
        
        Args:
            start_entity: 起始实体名称
            max_depth: 最大遍历深度
            relation_types: 可选，限制的关系类型列表
        
        Returns:
            {'nodes': [...], 'edges': [...], 'depth_reached': int}
        """
        visited = set()
        nodes = []
        edges = []
        max_reached = 0
        queue = [(start_entity, 0)]
        
        while queue:
            current, current_depth = queue.pop(0)
            
            if current in visited or current_depth > max_depth:
                continue
            
            visited.add(current)
            max_reached = max(max_reached, current_depth)
            
            # 获取节点信息
            node = self.get_node_by_name(current)
            if node:
                nodes.append({
                    'name': node.name,
                    'type': node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type),
                    'aliases': node.aliases
                })
            else:
                nodes.append({'name': current, 'type': 'unknown', 'aliases': []})
            
            # 遍历邻居
            for neighbor_name, rel in self.get_neighbors(current, direction='both'):
                # 关系类型过滤
                if relation_types and rel.relation_type not in relation_types:
                    continue
                
                edges.append({
                    'source': rel.source_id,
                    'target': rel.target_id,
                    'type': rel.relation_type,
                    'confidence': rel.confidence
                })
                
                if neighbor_name not in visited:
                    queue.append((neighbor_name, current_depth + 1))
        
        return {
            'nodes': nodes,
            'edges': edges,
            'depth_reached': max_reached
        }
    
    def query(self, pattern: str) -> List[Dict]:
        """兼容方法：简单的图查询（类似 Cypher 但更简单）
        
        示例: "PERSON -LOVES-> PERSON"
        
        Args:
            pattern: 查询模式
        
        Returns:
            [{'source': ..., 'relation': ..., 'target': ..., 'confidence': ...}, ...]
        """
        import re
        match = re.match(r'(\w+)\s*-(\w+)->\s*(\w+)', pattern)
        if not match:
            return []
        
        source_type, rel_type, target_type = match.groups()
        
        results = []
        edge_ids = self._indexes.by_predicate.get(rel_type, set())
        
        for edge_id in edge_ids:
            edge = self.edges.get(edge_id)
            if not edge:
                continue
            
            source_node = self.nodes.get(edge.subject)
            target_node = self.nodes.get(edge.object)
            
            source_name = source_node.name if source_node else edge.subject
            target_name = target_node.name if target_node else edge.object
            
            results.append({
                'source': source_name,
                'relation': rel_type,
                'target': target_name,
                'confidence': edge.confidence
            })
        
        return results


__all__ = [
    'QueryResult',
    'TemporalKnowledgeGraph',
    'KUZU_AVAILABLE',
]
