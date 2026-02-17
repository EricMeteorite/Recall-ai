"""JSON 文件图后端

Phase 3.5: 企业级性能引擎

零依赖的 JSON 文件存储后端，适合小规模场景。

特点：
- 零外部依赖
- 文件可读可编辑
- 支持 Git 版本控制
- 适合 <10万节点

存储格式：
- nodes.json: 节点列表
- edges.json: 边列表
"""

import os
import json
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime

from .base import GraphBackend, GraphNode, GraphEdge


class JSONGraphBackend(GraphBackend):
    """JSON 文件图后端 - 零依赖，适合小规模场景
    
    性能特点：
    - 适合 <10万节点
    - 内存占用：~1GB / 10万节点
    - 启动时全量加载
    
    优点：
    - 零外部依赖
    - 文件可读可编辑
    - 支持 Git 版本控制
    
    缺点：
    - 全量加载，大数据集启动慢
    - 每次修改都需要保存整个文件
    - 不支持并发写入
    
    使用方式：
        backend = JSONGraphBackend(data_path="./recall_data/graph")
        backend.add_node(GraphNode(id="1", name="Alice", node_type="person", properties={}))
        neighbors = backend.get_neighbors("1")
    """
    
    def __init__(self, data_path: str, auto_save: bool = True):
        """初始化 JSON 后端
        
        Args:
            data_path: 数据存储路径
            auto_save: 是否自动保存（每次修改后）
        """
        self.data_path = data_path
        self.auto_save = auto_save
        
        self.nodes_file = os.path.join(data_path, "nodes.json")
        self.edges_file = os.path.join(data_path, "edges.json")
        
        # 内存索引
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}
        self.outgoing: Dict[str, List[str]] = defaultdict(list)  # node_id -> edge_ids
        self.incoming: Dict[str, List[str]] = defaultdict(list)  # node_id -> edge_ids
        
        # 延迟保存追踪
        self._dirty = False
        self._dirty_count = 0
        self._save_interval = 100
        
        self._load()
        
        import atexit
        atexit.register(self.flush)
    
    def _load(self):
        """加载数据"""
        os.makedirs(self.data_path, exist_ok=True)
        
        # 加载节点
        if os.path.exists(self.nodes_file):
            try:
                with open(self.nodes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        # 处理 datetime 字段
                        if 'created_at' in item and item['created_at']:
                            item['created_at'] = datetime.fromisoformat(item['created_at'])
                        node = GraphNode(**item)
                        self.nodes[node.id] = node
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[JSONGraphBackend] Warning: Failed to load nodes: {e}")
        
        # 加载边
        if os.path.exists(self.edges_file):
            try:
                with open(self.edges_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        # 处理 datetime 字段
                        if 'created_at' in item and item['created_at']:
                            item['created_at'] = datetime.fromisoformat(item['created_at'])
                        edge = GraphEdge(**item)
                        self.edges[edge.id] = edge
                        self.outgoing[edge.source_id].append(edge.id)
                        self.incoming[edge.target_id].append(edge.id)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[JSONGraphBackend] Warning: Failed to load edges: {e}")
    
    def _save(self):
        """保存数据"""
        os.makedirs(self.data_path, exist_ok=True)
        
        # 保存节点
        nodes_data = []
        for node in self.nodes.values():
            node_dict = {
                'id': node.id,
                'name': node.name,
                'node_type': node.node_type,
                'properties': node.properties,
                'embeddings': node.embeddings,
                'created_at': node.created_at.isoformat() if node.created_at else None
            }
            nodes_data.append(node_dict)
        
        with open(self.nodes_file, 'w', encoding='utf-8') as f:
            json.dump(nodes_data, f, ensure_ascii=False, indent=2)
        
        # 保存边
        edges_data = []
        for edge in self.edges.values():
            edge_dict = {
                'id': edge.id,
                'source_id': edge.source_id,
                'target_id': edge.target_id,
                'edge_type': edge.edge_type,
                'properties': edge.properties,
                'weight': edge.weight,
                'created_at': edge.created_at.isoformat() if edge.created_at else None
            }
            edges_data.append(edge_dict)
        
        with open(self.edges_file, 'w', encoding='utf-8') as f:
            json.dump(edges_data, f, ensure_ascii=False, indent=2)
    
    def add_node(self, node: GraphNode) -> str:
        """添加节点"""
        self.nodes[node.id] = node
        self._mark_dirty()
        return node.id
    
    def add_edge(self, edge: GraphEdge) -> str:
        """添加边"""
        self.edges[edge.id] = edge
        self.outgoing[edge.source_id].append(edge.id)
        self.incoming[edge.target_id].append(edge.id)
        self._mark_dirty()
        return edge.id
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """获取节点"""
        return self.nodes.get(node_id)
    
    def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100
    ) -> List[Tuple[GraphNode, GraphEdge]]:
        """获取邻居 - O(degree) 复杂度"""
        results = []
        edge_ids = set()
        
        if direction in ("out", "both"):
            edge_ids.update(self.outgoing.get(node_id, []))
        if direction in ("in", "both"):
            edge_ids.update(self.incoming.get(node_id, []))
        
        for edge_id in list(edge_ids)[:limit * 2]:  # 多取一些用于过滤
            edge = self.edges.get(edge_id)
            if not edge:
                continue
            if edge_type and edge.edge_type != edge_type:
                continue
            
            # 确定邻居节点
            neighbor_id = edge.target_id if edge.source_id == node_id else edge.source_id
            neighbor = self.nodes.get(neighbor_id)
            
            if neighbor:
                results.append((neighbor, edge))
            
            if len(results) >= limit:
                break
        
        return results
    
    def bfs(
        self,
        start_ids: List[str],
        max_depth: int = 2,
        edge_types: Optional[List[str]] = None,
        node_filter: Optional[Dict[str, Any]] = None,
        limit: int = 1000
    ) -> Dict[int, List[Tuple[GraphNode, GraphEdge]]]:
        """BFS 遍历 - Python 实现"""
        from collections import deque
        
        visited = set(start_ids)
        queue = deque([(sid, 0) for sid in start_ids])
        by_depth: Dict[int, List[Tuple[GraphNode, GraphEdge]]] = {}
        total = 0
        
        while queue and total < limit:
            node_id, current_depth = queue.popleft()
            
            if current_depth >= max_depth:
                continue
            
            neighbors = self.get_neighbors(node_id, direction="both", limit=100)
            
            for neighbor, edge in neighbors:
                if neighbor.id in visited:
                    continue
                
                # 边类型过滤
                if edge_types and edge.edge_type not in edge_types:
                    continue
                
                # 节点属性过滤
                if node_filter:
                    match = True
                    for key, value in node_filter.items():
                        if neighbor.properties.get(key) != value:
                            match = False
                            break
                    if not match:
                        continue
                
                visited.add(neighbor.id)
                next_depth = current_depth + 1
                
                if next_depth not in by_depth:
                    by_depth[next_depth] = []
                by_depth[next_depth].append((neighbor, edge))
                total += 1
                
                if total >= limit:
                    break
                
                queue.append((neighbor.id, next_depth))
        
        return by_depth
    
    def count_nodes(self, node_type: Optional[str] = None) -> int:
        """统计节点数量"""
        if node_type:
            return sum(1 for n in self.nodes.values() if n.node_type == node_type)
        return len(self.nodes)
    
    def count_edges(self, edge_type: Optional[str] = None) -> int:
        """统计边数量"""
        if edge_type:
            return sum(1 for e in self.edges.values() if e.edge_type == edge_type)
        return len(self.edges)
    
    @property
    def backend_name(self) -> str:
        """后端名称"""
        return "json"
    
    @property
    def supports_transactions(self) -> bool:
        """是否支持事务"""
        return False
    
    def delete_node(self, node_id: str) -> bool:
        """删除节点及其相关边"""
        if node_id not in self.nodes:
            return False
        
        # 删除相关边
        edges_to_delete = []
        edges_to_delete.extend(self.outgoing.get(node_id, []))
        edges_to_delete.extend(self.incoming.get(node_id, []))
        
        for edge_id in set(edges_to_delete):
            self.delete_edge(edge_id)
        
        # 删除节点
        del self.nodes[node_id]
        
        # 清理索引
        if node_id in self.outgoing:
            del self.outgoing[node_id]
        if node_id in self.incoming:
            del self.incoming[node_id]
        
        self._mark_dirty()
        return True
    
    def delete_edge(self, edge_id: str) -> bool:
        """删除边"""
        if edge_id not in self.edges:
            return False
        
        edge = self.edges[edge_id]
        
        # 更新索引
        if edge_id in self.outgoing.get(edge.source_id, []):
            self.outgoing[edge.source_id].remove(edge_id)
        if edge_id in self.incoming.get(edge.target_id, []):
            self.incoming[edge.target_id].remove(edge_id)
        
        # 删除边
        del self.edges[edge_id]
        
        self._mark_dirty()
        return True
    
    def update_node(self, node_id: str, properties: Dict[str, Any]) -> bool:
        """更新节点属性"""
        if node_id not in self.nodes:
            return False
        
        self.nodes[node_id].properties.update(properties)
        
        self._mark_dirty()
        return True
    
    def update_edge(self, edge_id: str, properties: Dict[str, Any]) -> bool:
        """更新边属性"""
        if edge_id not in self.edges:
            return False
        
        self.edges[edge_id].properties.update(properties)
        
        self._mark_dirty()
        return True
    
    def _mark_dirty(self):
        self._dirty = True
        self._dirty_count += 1
        if self.auto_save and self._dirty_count >= self._save_interval:
            self._save()
            self._dirty_count = 0

    def flush(self):
        """显式刷盘"""
        if self._dirty:
            self._save()
            self._dirty = False
            self._dirty_count = 0

    def save(self):
        """手动保存（当 auto_save=False 时使用）"""
        self._save()
    
    def clear(self):
        """清空所有数据"""
        self.nodes.clear()
        self.edges.clear()
        self.outgoing.clear()
        self.incoming.clear()
        
        self._mark_dirty()
