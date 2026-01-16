"""实体索引 - 支持名称和别名的快速查找"""

import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class IndexedEntity:
    """索引中的实体"""
    id: str
    name: str
    aliases: List[str]
    entity_type: str
    turn_references: List[int]  # 出现过的轮次


class EntityIndex:
    """实体索引"""
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.index_dir = os.path.join(data_path, 'indexes')
        self.index_file = os.path.join(self.index_dir, 'entity_index.json')
        
        # 内存索引
        self.entities: Dict[str, IndexedEntity] = {}   # id → entity
        self.name_index: Dict[str, str] = {}           # name/alias → id
        
        self._load()
    
    def _load(self):
        """加载索引"""
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    entity = IndexedEntity(**item)
                    self.entities[entity.id] = entity
                    self.name_index[entity.name.lower()] = entity.id
                    for alias in entity.aliases:
                        self.name_index[alias.lower()] = entity.id
    
    def _save(self):
        """保存索引"""
        os.makedirs(self.index_dir, exist_ok=True)
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(e) for e in self.entities.values()], f, ensure_ascii=False)
    
    def add(self, entity: IndexedEntity):
        """添加实体"""
        if entity.id in self.entities:
            # 合并引用
            existing = self.entities[entity.id]
            existing.turn_references = list(set(existing.turn_references + entity.turn_references))
            existing.aliases = list(set(existing.aliases + entity.aliases))
        else:
            self.entities[entity.id] = entity
        
        # 更新名称索引
        self.name_index[entity.name.lower()] = entity.id
        for alias in entity.aliases:
            self.name_index[alias.lower()] = entity.id
        
        self._save()
    
    def get_by_name(self, name: str) -> Optional[IndexedEntity]:
        """通过名称或别名查找"""
        entity_id = self.name_index.get(name.lower())
        if entity_id:
            return self.entities.get(entity_id)
        return None
    
    def get_by_id(self, entity_id: str) -> Optional[IndexedEntity]:
        """通过ID查找"""
        return self.entities.get(entity_id)
    
    def search(self, query: str) -> List[IndexedEntity]:
        """模糊搜索"""
        query_lower = query.lower()
        results = []
        seen_ids = set()
        
        for name, entity_id in self.name_index.items():
            if query_lower in name and entity_id not in seen_ids:
                entity = self.entities[entity_id]
                results.append(entity)
                seen_ids.add(entity_id)
        
        return results
    
    def all_entities(self) -> List[IndexedEntity]:
        """返回所有实体"""
        return list(self.entities.values())
    
    def get_top_entities(self, limit: int = 100) -> List[IndexedEntity]:
        """获取最常引用的实体（用于预热缓存）"""
        sorted_entities = sorted(
            self.entities.values(),
            key=lambda e: len(e.turn_references),
            reverse=True
        )
        return sorted_entities[:limit]
    
    def add_entity_occurrence(self, entity_name: str, turn_id: str, context: str = "") -> None:
        """添加实体出现记录
        
        Args:
            entity_name: 实体名称
            turn_id: 轮次/记忆ID
            context: 上下文文本
        """
        # 查找或创建实体
        existing = self.get_by_name(entity_name)
        
        if existing:
            # 更新已有实体
            if turn_id not in existing.turn_references:
                existing.turn_references.append(turn_id)
            self._save()
        else:
            # 创建新实体
            import uuid
            entity = IndexedEntity(
                id=f"ent_{uuid.uuid4().hex[:8]}",
                name=entity_name,
                aliases=[],
                entity_type="UNKNOWN",
                turn_references=[turn_id]
            )
            self.add(entity)
    
    def get_related_turns(self, entity_name: str) -> List[IndexedEntity]:
        """获取实体相关的轮次
        
        Args:
            entity_name: 实体名称
        
        Returns:
            List[IndexedEntity]: 包含该实体的实体列表（携带 turn_references）
        """
        results = self.search(entity_name)
        return results
    
    def get_entity(self, name: str) -> Optional[IndexedEntity]:
        """通过名称获取实体（get_by_name 的别名）"""
        return self.get_by_name(name)
