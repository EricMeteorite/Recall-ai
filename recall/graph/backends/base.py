"""图存储后端抽象接口

Phase 3.5: 企业级性能引擎

定义统一的图后端接口，所有图后端必须实现此接口。
这确保了 RecallEngine 可以无缝切换不同的图存储后端。

设计原则：
1. 接口最小化 - 只定义必需的方法
2. 类型安全 - 使用 dataclass 定义统一的节点和边模型
3. 向后兼容 - 通过 LegacyKnowledgeGraphAdapter 支持现有数据
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GraphNode:
    """统一节点模型
    
    所有图后端使用统一的节点表示，确保可互换性。
    
    Attributes:
        id: 节点唯一标识符
        name: 节点名称（用于显示和搜索）
        node_type: 节点类型（entity, episode, community 等）
        properties: 动态属性字典
        embeddings: 可选的向量嵌入（name/content/summary）
        created_at: 创建时间
    """
    id: str
    name: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    embeddings: Optional[Dict[str, List[float]]] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.properties is None:
            self.properties = {}


@dataclass
class GraphEdge:
    """统一边模型
    
    所有图后端使用统一的边表示。
    
    Attributes:
        id: 边唯一标识符
        source_id: 源节点 ID
        target_id: 目标节点 ID
        edge_type: 边类型（关系类型）
        properties: 动态属性字典
        weight: 边权重（用于排序和时间衰减）
        created_at: 创建时间
    """
    id: str
    source_id: str
    target_id: str
    edge_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.properties is None:
            self.properties = {}


class GraphBackend(ABC):
    """图存储后端抽象接口
    
    所有图后端必须实现此接口，确保 RecallEngine 可以无缝切换。
    
    实现类：
    - LegacyKnowledgeGraphAdapter: 适配现有 KnowledgeGraph（默认）
    - JSONGraphBackend: 新的 JSON 文件存储
    - KuzuGraphBackend: Kuzu 嵌入式图数据库
    - Neo4jGraphBackend: Neo4j 分布式数据库（企业级）
    
    使用示例：
        backend = create_graph_backend(data_path, backend="auto")
        backend.add_node(GraphNode(id="1", name="Alice", node_type="person", properties={}))
        backend.add_edge(GraphEdge(id="e1", source_id="1", target_id="2", edge_type="KNOWS", properties={}))
        neighbors = backend.get_neighbors("1")
    """
    
    @abstractmethod
    def add_node(self, node: GraphNode) -> str:
        """添加节点
        
        Args:
            node: GraphNode 实例
            
        Returns:
            节点 ID（与输入的 node.id 相同）
        """
        pass
    
    @abstractmethod
    def add_edge(self, edge: GraphEdge) -> str:
        """添加边
        
        Args:
            edge: GraphEdge 实例
            
        Returns:
            边 ID
        """
        pass
    
    @abstractmethod
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """获取节点
        
        Args:
            node_id: 节点 ID
            
        Returns:
            GraphNode 实例，不存在则返回 None
        """
        pass
    
    @abstractmethod
    def get_neighbors(
        self, 
        node_id: str, 
        edge_type: Optional[str] = None,
        direction: str = "both",  # in | out | both
        limit: int = 100
    ) -> List[Tuple[GraphNode, GraphEdge]]:
        """获取邻居节点
        
        Args:
            node_id: 起始节点 ID
            edge_type: 可选的边类型过滤
            direction: 方向（in=入边, out=出边, both=双向）
            limit: 最大返回数量
            
        Returns:
            (邻居节点, 连接边) 元组列表
        """
        pass
    
    @abstractmethod
    def bfs(
        self,
        start_ids: List[str],
        max_depth: int = 2,
        edge_types: Optional[List[str]] = None,
        node_filter: Optional[Dict[str, Any]] = None,
        limit: int = 1000
    ) -> Dict[int, List[Tuple[GraphNode, GraphEdge]]]:
        """BFS 图遍历
        
        广度优先搜索，返回按深度分组的结果。
        
        Args:
            start_ids: 起始节点 ID 列表
            max_depth: 最大遍历深度
            edge_types: 可选的边类型过滤列表
            node_filter: 可选的节点属性过滤
            limit: 最大返回节点数
            
        Returns:
            深度 -> [(节点, 边)] 的字典
        """
        pass
    
    def query(self, cypher_like: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """执行类 Cypher 查询
        
        可选实现 - 不是所有后端都支持查询语言。
        默认抛出 NotImplementedError。
        
        Args:
            cypher_like: 类 Cypher 查询字符串
            params: 查询参数
            
        Returns:
            查询结果列表
            
        Raises:
            NotImplementedError: 如果后端不支持查询
        """
        raise NotImplementedError(f"{self.backend_name} 不支持 Cypher 查询")
    
    @abstractmethod
    def count_nodes(self, node_type: Optional[str] = None) -> int:
        """统计节点数量
        
        Args:
            node_type: 可选的节点类型过滤
            
        Returns:
            节点数量
        """
        pass
    
    @abstractmethod
    def count_edges(self, edge_type: Optional[str] = None) -> int:
        """统计边数量
        
        Args:
            edge_type: 可选的边类型过滤
            
        Returns:
            边数量
        """
        pass
    
    @property
    @abstractmethod
    def backend_name(self) -> str:
        """后端名称标识"""
        pass
    
    @property
    @abstractmethod
    def supports_transactions(self) -> bool:
        """是否支持事务"""
        pass
    
    def delete_node(self, node_id: str) -> bool:
        """删除节点（可选实现）
        
        Args:
            node_id: 节点 ID
            
        Returns:
            是否删除成功
        """
        raise NotImplementedError(f"{self.backend_name} 不支持删除节点")
    
    def delete_edge(self, edge_id: str) -> bool:
        """删除边（可选实现）
        
        Args:
            edge_id: 边 ID
            
        Returns:
            是否删除成功
        """
        raise NotImplementedError(f"{self.backend_name} 不支持删除边")
    
    def update_node(self, node_id: str, properties: Dict[str, Any]) -> bool:
        """更新节点属性（可选实现）
        
        Args:
            node_id: 节点 ID
            properties: 要更新的属性
            
        Returns:
            是否更新成功
        """
        raise NotImplementedError(f"{self.backend_name} 不支持更新节点")
    
    def update_edge(self, edge_id: str, properties: Dict[str, Any]) -> bool:
        """更新边属性（可选实现）
        
        Args:
            edge_id: 边 ID
            properties: 要更新的属性
            
        Returns:
            是否更新成功
        """
        raise NotImplementedError(f"{self.backend_name} 不支持更新边")
    
    def close(self):
        """关闭后端连接（可选实现）
        
        用于释放资源，如数据库连接。
        """
        pass
    
    def __enter__(self):
        """支持上下文管理器"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时关闭连接"""
        self.close()
        return False
