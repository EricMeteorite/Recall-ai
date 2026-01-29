"""知识图谱 - 实体关系的结构化存储"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class Relation:
    """实体间的关系"""
    source_id: str           # 源实体ID
    target_id: str           # 目标实体ID
    relation_type: str       # 关系类型
    properties: Dict = field(default_factory=dict)  # 关系属性
    created_turn: int = 0    # 创建轮次
    confidence: float = 0.5  # 置信度
    source_text: str = ""    # 原文依据
    # === Recall 4.1 新增时态字段 ===
    valid_at: Optional[str] = None      # 事实生效时间 (ISO 8601)
    invalid_at: Optional[str] = None    # 事实失效时间 (ISO 8601)
    fact: str = ""                      # 自然语言事实描述


class KnowledgeGraph:
    """轻量级知识图谱 - 无需 Neo4j"""
    
    # 预定义的关系类型（针对 RP 场景优化）
    RELATION_TYPES = {
        # 人物关系
        'IS_FRIEND_OF': '是朋友',
        'IS_ENEMY_OF': '是敌人',
        'IS_FAMILY_OF': '是家人',
        'LOVES': '爱慕',
        'HATES': '憎恨',
        'KNOWS': '认识',
        'WORKS_FOR': '为...工作',
        'MENTORS': '指导',
        
        # 空间关系
        'LOCATED_IN': '位于',
        'TRAVELS_TO': '前往',
        'OWNS': '拥有',
        'LIVES_IN': '居住于',
        
        # 事件关系
        'PARTICIPATED_IN': '参与了',
        'CAUSED': '导致了',
        'WITNESSED': '目击了',
        
        # 物品关系
        'CARRIES': '携带',
        'USES': '使用',
        'GAVE_TO': '给予',
        'RECEIVED_FROM': '收到来自',
    }
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.graph_file = os.path.join(data_path, 'knowledge_graph.json')
        
        # 邻接表存储
        self.outgoing: Dict[str, List[Relation]] = defaultdict(list)  # source → relations
        self.incoming: Dict[str, List[Relation]] = defaultdict(list)  # target → relations
        self.relation_index: Dict[str, List[Relation]] = defaultdict(list)  # type → relations
        
        self._load()
    
    def _load(self):
        """加载图谱"""
        if os.path.exists(self.graph_file):
            with open(self.graph_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data.get('relations', []):
                    rel = Relation(**item)
                    self._index_relation(rel)
    
    def _save(self):
        """保存图谱"""
        os.makedirs(os.path.dirname(self.graph_file) if os.path.dirname(self.graph_file) else '.', exist_ok=True)
        
        # 收集所有关系
        all_relations = []
        seen = set()
        for relations in self.outgoing.values():
            for rel in relations:
                key = (rel.source_id, rel.target_id, rel.relation_type)
                if key not in seen:
                    seen.add(key)
                    all_relations.append(asdict(rel))
        
        with open(self.graph_file, 'w', encoding='utf-8') as f:
            json.dump({'relations': all_relations}, f, ensure_ascii=False, indent=2)
    
    def _index_relation(self, rel: Relation):
        """索引一个关系"""
        self.outgoing[rel.source_id].append(rel)
        self.incoming[rel.target_id].append(rel)
        self.relation_index[rel.relation_type].append(rel)
    
    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                     properties: Dict = None, turn: int = 0, source_text: str = "",
                     confidence: float = 0.5,
                     valid_at: Optional[str] = None, invalid_at: Optional[str] = None,
                     fact: str = "") -> Relation:
        """添加关系
        
        Args:
            source_id: 源实体ID
            target_id: 目标实体ID
            relation_type: 关系类型
            properties: 关系属性
            turn: 创建轮次
            source_text: 原文依据
            confidence: 置信度 (0-1)
            valid_at: 事实生效时间 (ISO 8601) - Recall 4.1
            invalid_at: 事实失效时间 (ISO 8601) - Recall 4.1
            fact: 自然语言事实描述 - Recall 4.1
        """
        # 检查是否已存在
        for rel in self.outgoing[source_id]:
            if rel.target_id == target_id and rel.relation_type == relation_type:
                # 更新置信度
                rel.confidence = min(1.0, rel.confidence + 0.1)
                self._save()
                return rel
        
        rel = Relation(
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
        self._index_relation(rel)
        self._save()
        return rel
    
    def add_entity(self, entity_id: str, entity_type: str = "ENTITY") -> bool:
        """添加实体（创建一个自环关系来记录实体）
        
        Args:
            entity_id: 实体ID/名称
            entity_type: 实体类型
        
        Returns:
            bool: 是否成功
        """
        # 通过添加一个 IS_A 关系来记录实体
        self.add_relation(
            source_id=entity_id,
            target_id=entity_type,
            relation_type="IS_A"
        )
        return True
    
    def get_neighbors(self, entity_id: str, relation_type: str = None, 
                      direction: str = 'both') -> List[Tuple[str, Relation]]:
        """获取邻居实体
        
        Args:
            entity_id: 实体ID
            relation_type: 可选，过滤关系类型
            direction: 'out'=出边, 'in'=入边, 'both'=双向
        
        Returns:
            [(邻居ID, 关系对象), ...]
        """
        neighbors = []
        
        if direction in ('out', 'both'):
            for rel in self.outgoing.get(entity_id, []):
                if relation_type is None or rel.relation_type == relation_type:
                    neighbors.append((rel.target_id, rel))
        
        if direction in ('in', 'both'):
            for rel in self.incoming.get(entity_id, []):
                if relation_type is None or rel.relation_type == relation_type:
                    neighbors.append((rel.source_id, rel))
        
        return neighbors
    
    def find_path(self, source_id: str, target_id: str, max_depth: int = 3) -> Optional[List[str]]:
        """查找两个实体间的路径（BFS）"""
        if source_id == target_id:
            return [source_id]
        
        visited = {source_id}
        queue = [(source_id, [source_id])]
        
        while queue:
            current, path = queue.pop(0)
            
            if len(path) > max_depth:
                continue
            
            for neighbor_id, rel in self.get_neighbors(current, direction='out'):
                if neighbor_id == target_id:
                    return path + [neighbor_id]
                
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [neighbor_id]))
        
        return None
    
    def get_subgraph(self, entity_id: str, depth: int = 2) -> Dict:
        """获取以某实体为中心的子图"""
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
            
            for neighbor_id, rel in self.get_neighbors(current):
                edges.append({
                    'source': rel.source_id,
                    'target': rel.target_id,
                    'type': rel.relation_type
                })
                if neighbor_id not in visited:
                    queue.append((neighbor_id, current_depth + 1))
        
        return {'nodes': nodes, 'edges': edges}
    
    def query(self, pattern: str) -> List[Dict]:
        """简单的图查询（类似 Cypher 但更简单）
        
        示例: "PERSON -LOVES-> PERSON"
        """
        import re
        # 解析模式
        match = re.match(r'(\w+)\s*-(\w+)->\s*(\w+)', pattern)
        if not match:
            return []
        
        source_type, rel_type, target_type = match.groups()
        
        results = []
        for rel in self.relation_index.get(rel_type, []):
            # 这里简化处理，实际应该检查实体类型
            results.append({
                'source': rel.source_id,
                'relation': rel_type,
                'target': rel.target_id,
                'confidence': rel.confidence
            })
        
        return results
    
    def clear(self):
        """清空知识图谱"""
        self.outgoing.clear()
        self.incoming.clear()
        self.relation_index.clear()
        self._save()
