"""现有 KnowledgeGraph 适配器

Phase 3.5: 企业级性能引擎

将现有的 KnowledgeGraph 类包装为 GraphBackend 接口，
确保所有使用 GraphBackend 的新代码可以无缝使用现有的 KnowledgeGraph 实现。

⚠️ 关键兼容性保障：
- 这是默认后端，确保零迁移成本
- 不修改任何现有 KnowledgeGraph 代码
- 使用适配器模式，完全透明

设计原则：
1. 只做包装，不做修改
2. 透传所有操作到底层 KnowledgeGraph
3. 转换数据模型（Relation ↔ GraphNode/GraphEdge）
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from .base import GraphBackend, GraphNode, GraphEdge


class LegacyKnowledgeGraphAdapter(GraphBackend):
    """现有 KnowledgeGraph 类的 GraphBackend 适配器
    
    这个适配器将现有的 KnowledgeGraph 包装为 GraphBackend 接口，
    确保所有使用 GraphBackend 的新代码可以无缝使用现有的 KnowledgeGraph 实现。
    
    ⚠️ 重要：这是默认后端，确保零迁移成本！
    
    使用方式：
        from recall.graph import KnowledgeGraph
        from recall.graph.backends import LegacyKnowledgeGraphAdapter
        
        kg = KnowledgeGraph(data_path="./recall_data/data")
        backend = LegacyKnowledgeGraphAdapter(kg)
        
        # 现在可以用 GraphBackend 接口操作
        neighbors = backend.get_neighbors("Alice")
    
    与其他后端的对比：
    - LegacyKnowledgeGraphAdapter: 使用现有 knowledge_graph.json 格式（向后兼容）
    - JSONGraphBackend: 使用新的 nodes.json + edges.json 格式
    - KuzuGraphBackend: 使用 Kuzu 嵌入式数据库
    """
    
    def __init__(self, knowledge_graph):
        """初始化适配器
        
        Args:
            knowledge_graph: KnowledgeGraph 实例
        """
        # 类型提示避免循环导入
        from ..knowledge_graph import KnowledgeGraph
        if not isinstance(knowledge_graph, KnowledgeGraph):
            raise TypeError(f"Expected KnowledgeGraph, got {type(knowledge_graph)}")
        
        self._kg = knowledge_graph
    
    def add_node(self, node: GraphNode) -> str:
        """添加节点
        
        KnowledgeGraph 的节点是隐式创建的（通过关系），
        这里使用 IS_A 关系来显式记录节点信息。
        """
        # 使用 add_entity 方法（它内部通过 IS_A 关系实现）
        self._kg.add_entity(node.id, node.node_type)
        return node.id
    
    def add_edge(self, edge: GraphEdge) -> str:
        """添加边"""
        self._kg.add_relation(
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_type=edge.edge_type,
            properties=edge.properties or {},
            source_text=edge.properties.get("source_text", "") if edge.properties else ""
        )
        return edge.id
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """获取节点
        
        从关系中推断节点是否存在。
        KnowledgeGraph 不存储独立的节点信息，
        我们通过检查该 ID 是否出现在任何关系中来判断。
        """
        outgoing = self._kg.outgoing.get(node_id, [])
        incoming = self._kg.incoming.get(node_id, [])
        
        if not outgoing and not incoming:
            return None
        
        # 推断节点类型（从 IS_A 关系）
        node_type = "entity"
        for rel in outgoing:
            if rel.relation_type == "IS_A":
                node_type = rel.target_id
                break
        
        return GraphNode(
            id=node_id,
            name=node_id,  # KnowledgeGraph 用 ID 作为名称
            node_type=node_type,
            properties={}
        )
    
    def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
        direction: str = "both",
        limit: int = 100
    ) -> List[Tuple[GraphNode, GraphEdge]]:
        """获取邻居节点
        
        直接复用 KnowledgeGraph 的 get_neighbors 方法，
        并转换返回格式。
        """
        # 调用原始方法（注意参数名不同）
        kg_neighbors = self._kg.get_neighbors(
            entity_id=node_id,
            relation_type=edge_type,
            direction="out" if direction == "out" else ("in" if direction == "in" else "both")
        )
        
        results = []
        for neighbor_id, rel in kg_neighbors[:limit]:
            # 跳过 IS_A 类型关系（这是用于节点类型记录的内部关系）
            if rel.relation_type == "IS_A":
                continue
            
            node = GraphNode(
                id=neighbor_id,
                name=neighbor_id,
                node_type="entity",
                properties={}
            )
            
            edge = GraphEdge(
                id=f"{rel.source_id}_{rel.target_id}_{rel.relation_type}",
                source_id=rel.source_id,
                target_id=rel.target_id,
                edge_type=rel.relation_type,
                properties=rel.properties if rel.properties else {},
                weight=rel.confidence
            )
            
            results.append((node, edge))
        
        return results
    
    def bfs(
        self,
        start_ids: List[str],
        max_depth: int = 2,
        edge_types: Optional[List[str]] = None,
        node_filter: Optional[Dict[str, Any]] = None,
        limit: int = 1000
    ) -> Dict[int, List[Tuple[GraphNode, GraphEdge]]]:
        """BFS 图遍历
        
        对每个起始节点执行 BFS，合并结果。
        """
        from collections import deque
        
        results: Dict[int, List[Tuple[GraphNode, GraphEdge]]] = defaultdict(list)
        visited = set(start_ids)
        total_count = 0
        
        # 初始化队列：(node_id, depth)
        queue = deque([(start_id, 0) for start_id in start_ids])
        
        while queue and total_count < limit:
            current_id, current_depth = queue.popleft()
            
            if current_depth >= max_depth:
                continue
            
            # 获取当前节点的所有邻居
            neighbors = self._kg.get_neighbors(current_id, direction='both')
            
            for neighbor_id, rel in neighbors:
                # 跳过已访问节点
                if neighbor_id in visited:
                    continue
                
                # 边类型过滤
                if edge_types and rel.relation_type not in edge_types:
                    continue
                
                # 跳过 IS_A 内部关系
                if rel.relation_type == "IS_A":
                    continue
                
                visited.add(neighbor_id)
                
                # 构建 GraphNode 和 GraphEdge
                node = GraphNode(
                    id=neighbor_id,
                    name=neighbor_id,
                    node_type="entity",
                    properties={}
                )
                
                edge = GraphEdge(
                    id=f"{rel.source_id}_{rel.target_id}_{rel.relation_type}",
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    edge_type=rel.relation_type,
                    properties=rel.properties if rel.properties else {},
                    weight=rel.confidence
                )
                
                # 添加到对应深度的结果
                next_depth = current_depth + 1
                results[next_depth].append((node, edge))
                total_count += 1
                
                if total_count >= limit:
                    break
                
                # 继续 BFS
                queue.append((neighbor_id, next_depth))
        
        return dict(results)
    
    def query(self, cypher_like: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """执行类 Cypher 查询
        
        Legacy KnowledgeGraph 支持简单的图查询语法。
        """
        try:
            return self._kg.query(cypher_like)
        except Exception:
            raise NotImplementedError(
                "Legacy KnowledgeGraph 仅支持简单的图查询语法 (如 'PERSON -LOVES-> PERSON')"
            )
    
    def count_nodes(self, node_type: Optional[str] = None) -> int:
        """统计节点数量
        
        通过收集所有出现在关系中的实体 ID 来统计。
        """
        all_nodes = set()
        
        for source_id in self._kg.outgoing.keys():
            all_nodes.add(source_id)
        
        for source_id, relations in self._kg.outgoing.items():
            for rel in relations:
                all_nodes.add(rel.target_id)
        
        if node_type:
            # 过滤指定类型的节点
            typed_nodes = set()
            for rel in self._kg.relation_index.get("IS_A", []):
                if rel.target_id == node_type:
                    typed_nodes.add(rel.source_id)
            return len(typed_nodes)
        
        return len(all_nodes)
    
    def count_edges(self, edge_type: Optional[str] = None) -> int:
        """统计边数量"""
        if edge_type:
            return len(self._kg.relation_index.get(edge_type, []))
        
        total = 0
        for relations in self._kg.outgoing.values():
            total += len(relations)
        return total
    
    @property
    def backend_name(self) -> str:
        """后端名称"""
        return "legacy_json"
    
    @property
    def supports_transactions(self) -> bool:
        """是否支持事务"""
        return False
    
    def delete_node(self, node_id: str) -> bool:
        """删除节点
        
        删除所有与该节点相关的关系。
        """
        # 删除出边
        if node_id in self._kg.outgoing:
            for rel in self._kg.outgoing[node_id]:
                # 从 relation_index 中删除
                if rel.relation_type in self._kg.relation_index:
                    self._kg.relation_index[rel.relation_type] = [
                        r for r in self._kg.relation_index[rel.relation_type]
                        if r.source_id != node_id or r.target_id != rel.target_id
                    ]
                # 从目标的 incoming 中删除
                if rel.target_id in self._kg.incoming:
                    self._kg.incoming[rel.target_id] = [
                        r for r in self._kg.incoming[rel.target_id]
                        if r.source_id != node_id
                    ]
            del self._kg.outgoing[node_id]
        
        # 删除入边
        if node_id in self._kg.incoming:
            for rel in self._kg.incoming[node_id]:
                # 从 relation_index 中删除
                if rel.relation_type in self._kg.relation_index:
                    self._kg.relation_index[rel.relation_type] = [
                        r for r in self._kg.relation_index[rel.relation_type]
                        if r.target_id != node_id or r.source_id != rel.source_id
                    ]
                # 从源的 outgoing 中删除
                if rel.source_id in self._kg.outgoing:
                    self._kg.outgoing[rel.source_id] = [
                        r for r in self._kg.outgoing[rel.source_id]
                        if r.target_id != node_id
                    ]
            del self._kg.incoming[node_id]
        
        self._kg._save()
        return True
    
    @property
    def kg(self):
        """获取底层 KnowledgeGraph 实例
        
        用于需要直接访问原始 KnowledgeGraph 的场景。
        """
        return self._kg
