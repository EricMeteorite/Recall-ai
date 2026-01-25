"""社区检测模块

Phase 3.5: 企业级性能引擎

用于发现图中的实体群组，支持多种算法：
- Louvain: 最常用，适合大规模图
- Label Propagation: 快速，适合动态图
- Connected Components: 基础连通分量

通用场景价值：
| 场景 | 用途 |
|------|------|
| 代码库分析 | 自动发现模块/包的关联群组，理解代码架构 |
| 知识库管理 | 发现主题聚类，自动分类 |
| 项目管理 | 识别相关任务/Issue 群组 |
| 企业知识图谱 | 发现部门/团队知识群落 |

⚠️ Lite模式兼容说明：
- NetworkX 是可选依赖（仅在 [enterprise] 或 [full] 安装时包含）
- 如果未安装 NetworkX，社区检测功能会优雅禁用（不报错）
- Lite 模式（~80MB内存）不受影响
"""

import logging
from typing import List, Dict, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime


# 检查 NetworkX 是否可用
try:
    import networkx as nx
    from networkx.algorithms import community as nx_community
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    nx = None
    nx_community = None


if TYPE_CHECKING:
    from .backends.base import GraphBackend
    import networkx


logger = logging.getLogger(__name__)


@dataclass
class Community:
    """社区/群组
    
    Attributes:
        id: 社区唯一标识
        name: 社区名称（可人工设置或自动生成）
        member_ids: 成员节点 ID 列表
        summary: 社区摘要（可由 LLM 生成）
        created_at: 创建时间
        properties: 额外属性
    """
    id: str
    name: str
    member_ids: List[str] = field(default_factory=list)
    summary: str = ""
    created_at: Optional[datetime] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def size(self) -> int:
        """社区大小（成员数量）"""
        return len(self.member_ids)
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class CommunityDetector:
    """图社区检测器
    
    使用方式：
        detector = CommunityDetector(graph_backend)
        communities = detector.detect_communities()
        
        # 获取节点所属社区
        community = detector.get_community_for_node("node_123")
        
        # 生成社区摘要
        summary = await detector.get_community_summary("community_1", llm_client)
    
    ⚠️ Lite模式兼容说明：
        - NetworkX 是可选依赖（仅在 [enterprise] 或 [full] 安装时包含）
        - 如果未安装 NetworkX，社区检测功能会优雅禁用（不报错）
        - Lite 模式（~80MB内存）不受影响
    """
    
    def __init__(
        self,
        graph_backend: "GraphBackend",
        algorithm: str = "louvain",  # louvain | label_propagation | connected
        min_community_size: int = 2,
        resolution: float = 1.0  # Louvain 分辨率参数
    ):
        """初始化社区检测器
        
        Args:
            graph_backend: GraphBackend 实例
            algorithm: 检测算法
                - "louvain": Louvain 算法（推荐，适合大规模图）
                - "label_propagation": 标签传播算法（快速）
                - "connected": 连通分量（基础）
            min_community_size: 最小社区大小
            resolution: Louvain 分辨率参数（越大社区越小）
        """
        # ⚠️ Lite模式优雅降级：没有NetworkX时不报错，只是禁用功能
        if not NETWORKX_AVAILABLE:
            self._enabled = False
            logger.warning(
                "[CommunityDetector] NetworkX not installed. Community detection disabled. "
                "Install with: pip install networkx"
            )
            self.backend = None
            return
        
        self._enabled = True
        self.backend = graph_backend
        self.algorithm = algorithm
        self.min_community_size = min_community_size
        self.resolution = resolution
        
        # 缓存
        self._communities: List[Community] = []
        self._node_to_community: Dict[str, str] = {}
        self._nx_graph: Optional[Any] = None  # networkx.Graph when available
    
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._enabled
    
    def _build_networkx_graph(self) -> Any:
        """从 GraphBackend 构建 NetworkX 图"""
        if not self._enabled:
            return None
        
        G = nx.Graph()
        
        # 从后端获取所有边
        if hasattr(self.backend, 'edges'):
            # JSONGraphBackend
            for edge_id, edge in self.backend.edges.items():
                G.add_node(edge.source_id)
                G.add_node(edge.target_id)
                G.add_edge(
                    edge.source_id, 
                    edge.target_id,
                    weight=edge.weight if hasattr(edge, 'weight') else 1.0,
                    edge_type=edge.edge_type
                )
        elif hasattr(self.backend, '_kg'):
            # LegacyKnowledgeGraphAdapter
            kg = self.backend._kg
            for source_id, relations in kg.outgoing.items():
                G.add_node(source_id)
                for rel in relations:
                    # 跳过 IS_A 内部关系
                    if rel.relation_type == "IS_A":
                        continue
                    G.add_node(rel.target_id)
                    G.add_edge(
                        source_id,
                        rel.target_id,
                        weight=rel.confidence,
                        edge_type=rel.relation_type
                    )
        else:
            # 通用方法：遍历所有节点获取邻居
            logger.warning("[CommunityDetector] Using slow graph construction method")
            # 这种情况下需要后端提供节点列表，暂不实现
        
        self._nx_graph = G
        logger.info(f"[CommunityDetector] Built NetworkX graph with {G.number_of_nodes()} nodes, "
                   f"{G.number_of_edges()} edges")
        return G
    
    def detect_communities(self, refresh: bool = False) -> List[Community]:
        """检测社区
        
        Args:
            refresh: 是否强制重新计算
            
        Returns:
            社区列表
        """
        if not self._enabled:
            logger.warning("[CommunityDetector] Community detection is disabled (NetworkX not installed)")
            return []
        
        if self._communities and not refresh:
            return self._communities
        
        G = self._build_networkx_graph()
        
        if len(G.nodes()) == 0:
            logger.info("[CommunityDetector] Graph is empty, no communities detected")
            return []
        
        # 根据算法选择
        try:
            if self.algorithm == "louvain":
                partition = nx_community.louvain_communities(
                    G, 
                    resolution=self.resolution,
                    seed=42
                )
            elif self.algorithm == "label_propagation":
                partition = nx_community.label_propagation_communities(G)
            elif self.algorithm == "connected":
                partition = list(nx.connected_components(G))
            else:
                raise ValueError(f"Unknown algorithm: {self.algorithm}")
        except Exception as e:
            logger.error(f"[CommunityDetector] Failed to detect communities: {e}")
            return []
        
        # 构建 Community 对象
        communities = []
        for idx, members in enumerate(partition):
            if len(members) < self.min_community_size:
                continue
            
            community = Community(
                id=f"community_{idx}",
                name=f"Group {idx + 1}",
                member_ids=list(members),
                created_at=datetime.now()
            )
            communities.append(community)
            
            # 更新节点到社区的映射
            for member_id in members:
                self._node_to_community[member_id] = community.id
        
        self._communities = communities
        logger.info(f"[CommunityDetector] Detected {len(communities)} communities")
        return communities
    
    def get_community_for_node(self, node_id: str) -> Optional[Community]:
        """获取节点所属社区
        
        Args:
            node_id: 节点 ID
            
        Returns:
            Community 实例，如果不属于任何社区则返回 None
        """
        if not self._enabled:
            return None
        
        if not self._communities:
            self.detect_communities()
        
        community_id = self._node_to_community.get(node_id)
        if not community_id:
            return None
        
        for c in self._communities:
            if c.id == community_id:
                return c
        return None
    
    async def get_community_summary(
        self, 
        community_id: str, 
        llm_client=None
    ) -> str:
        """生成社区摘要
        
        如果提供 LLM client，使用 LLM 生成；否则使用简单模板。
        
        Args:
            community_id: 社区 ID
            llm_client: LLM 客户端（可选）
            
        Returns:
            摘要字符串
        """
        if not self._enabled:
            return ""
        
        community = None
        for c in self._communities:
            if c.id == community_id:
                community = c
                break
        
        if not community:
            return ""
        
        # 获取成员节点名称
        member_names = []
        for member_id in community.member_ids[:10]:  # 限制数量
            node = self.backend.get_node(member_id)
            if node:
                member_names.append(node.name)
            else:
                member_names.append(member_id)
        
        if llm_client:
            # 使用 LLM 生成摘要
            prompt = f"""Summarize what this group of entities have in common:
            
Entities: {', '.join(member_names)}

Provide a brief 1-2 sentence summary of their shared theme or relationship."""
            
            try:
                response = await llm_client.generate(prompt)
                community.summary = response
                return response
            except Exception as e:
                logger.warning(f"[CommunityDetector] LLM summary failed: {e}")
        
        # 简单模板
        summary = f"Group of {len(community.member_ids)} related entities including: {', '.join(member_names[:5])}"
        if len(community.member_ids) > 5:
            summary += f" and {len(community.member_ids) - 5} more"
        community.summary = summary
        return summary
    
    def get_communities_for_nodes(self, node_ids: List[str]) -> Dict[str, Optional[Community]]:
        """批量获取节点所属社区
        
        Args:
            node_ids: 节点 ID 列表
            
        Returns:
            {node_id: Community} 字典
        """
        if not self._enabled:
            return {nid: None for nid in node_ids}
        
        return {nid: self.get_community_for_node(nid) for nid in node_ids}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取社区统计信息"""
        if not self._enabled:
            return {"enabled": False, "reason": "NetworkX not installed"}
        
        if not self._communities:
            self.detect_communities()
        
        sizes = [c.size for c in self._communities]
        return {
            "enabled": True,
            "algorithm": self.algorithm,
            "total_communities": len(self._communities),
            "total_nodes_in_communities": sum(sizes),
            "avg_community_size": sum(sizes) / len(sizes) if sizes else 0,
            "max_community_size": max(sizes) if sizes else 0,
            "min_community_size": min(sizes) if sizes else 0,
        }
    
    def clear_cache(self):
        """清空缓存，下次调用时重新计算"""
        self._communities = []
        self._node_to_community = {}
        self._nx_graph = None
