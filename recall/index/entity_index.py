"""实体索引 - 支持名称和别名的快速查找"""

import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


@dataclass
class IndexedEntity:
    """索引中的实体"""
    id: str
    name: str
    aliases: List[str]
    entity_type: str
    turn_references: List[str]  # 出现过的记忆ID (如 mem_xxx)
    confidence: float = 0.5  # 置信度 (0-1)
    # === Recall 4.1 新增字段 ===
    summary: str = ""                           # 实体摘要
    attributes: Dict[str, Any] = field(default_factory=dict)  # 动态属性
    last_summary_update: Optional[str] = None   # 摘要最后更新时间


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
            # 如果已有实体类型是 UNKNOWN 且新实体类型有效，则更新类型
            if existing.entity_type == "UNKNOWN" and entity.entity_type != "UNKNOWN":
                existing.entity_type = entity.entity_type
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
    
    def add_entity_occurrence(self, entity_name: str, turn_id: str, context: str = "", 
                              entity_type: str = "UNKNOWN", aliases: List[str] = None,
                              confidence: float = 0.5) -> None:
        """添加实体出现记录
        
        Args:
            entity_name: 实体名称
            turn_id: 轮次/记忆ID
            context: 上下文文本
            entity_type: 实体类型 (PERSON, LOCATION, ITEM, ORG, CODE_SYMBOL 等)
            aliases: 实体别名列表
            confidence: 置信度 (0-1)
        """
        # 查找或创建实体
        existing = self.get_by_name(entity_name)
        
        if existing:
            # 更新已有实体
            if turn_id not in existing.turn_references:
                existing.turn_references.append(turn_id)
            # 如果已有实体类型是 UNKNOWN 且新传入的类型有效，则更新类型
            if existing.entity_type == "UNKNOWN" and entity_type != "UNKNOWN":
                existing.entity_type = entity_type
            # 合并别名
            if aliases:
                existing.aliases = list(set(existing.aliases + aliases))
                # 同时更新别名索引
                for alias in aliases:
                    self.name_index[alias.lower()] = existing.id
            # 更新置信度（取较高值）
            if confidence > existing.confidence:
                existing.confidence = confidence
            self._save()
        else:
            # 创建新实体
            import uuid
            entity = IndexedEntity(
                id=f"ent_{uuid.uuid4().hex[:8]}",
                name=entity_name,
                aliases=aliases or [],
                entity_type=entity_type,
                turn_references=[turn_id],
                confidence=confidence
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
    
    def remove_by_turn_references(self, turn_ids: List[str]) -> int:
        """移除与指定记忆ID关联的实体引用
        
        遍历所有实体，从 turn_references 中移除指定的记忆ID。
        如果实体的 turn_references 变为空，则删除该实体。
        
        Args:
            turn_ids: 要移除的记忆ID列表
        
        Returns:
            int: 被完全删除的实体数量
        """
        if not turn_ids:
            return 0
        
        turn_id_set = set(turn_ids)
        entities_to_delete = []
        
        for entity_id, entity in self.entities.items():
            # 过滤掉被删除的记忆引用
            remaining_refs = [
                ref for ref in entity.turn_references 
                if ref not in turn_id_set
            ]
            
            if not remaining_refs:
                # 没有剩余引用，标记删除
                entities_to_delete.append(entity_id)
            elif len(remaining_refs) != len(entity.turn_references):
                # 有部分引用被移除，更新
                entity.turn_references = remaining_refs
        
        # 删除无引用的实体
        for entity_id in entities_to_delete:
            entity = self.entities[entity_id]
            # 清理名称索引
            if entity.name.lower() in self.name_index:
                del self.name_index[entity.name.lower()]
            for alias in entity.aliases:
                if alias.lower() in self.name_index:
                    del self.name_index[alias.lower()]
            del self.entities[entity_id]
        
        if entities_to_delete or turn_ids:
            self._save()
        
        return len(entities_to_delete)
    
    def clear(self):
        """清空所有实体索引"""
        self.entities.clear()
        self.name_index.clear()
        self._save()
    
    # === Recall 4.1 新增方法 ===
    
    def update_entity_fields(
        self,
        entity_name: str,
        summary: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        last_summary_update: Optional[str] = None
    ) -> bool:
        """更新实体的扩展字段 (Recall 4.1)
        
        Args:
            entity_name: 实体名称
            summary: 实体摘要
            attributes: 动态属性字典
            last_summary_update: 摘要最后更新时间
        
        Returns:
            bool: 是否成功
        """
        entity = self.get_entity(entity_name)
        if not entity:
            return False
        
        if summary is not None:
            entity.summary = summary
        if attributes is not None:
            entity.attributes.update(attributes)
        if last_summary_update is not None:
            entity.last_summary_update = last_summary_update
        
        self._save()
        return True
    
    def get_entities_needing_summary(self, min_facts: int = 5) -> List[IndexedEntity]:
        """获取需要生成摘要的实体 (Recall 4.1)
        
        Args:
            min_facts: 最小事实数阈值
        
        Returns:
            List[IndexedEntity]: 需要摘要的实体列表
        """
        return [
            entity for entity in self.entities.values()
            if len(entity.turn_references) >= min_facts and not entity.summary
        ]
