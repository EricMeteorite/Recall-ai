"""L1长期记忆 - 完整实现"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ConsolidatedEntity:
    """长期记忆实体 - 经过验证的持久知识"""
    
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    entity_type: str = "UNKNOWN"  # CHARACTER, ITEM, LOCATION, CONCEPT, CODE_SYMBOL
    
    # 当前状态
    current_state: Dict[str, Any] = field(default_factory=dict)
    
    # 验证信息
    confidence: float = 0.5           # 置信度 (0-1)
    verification_count: int = 0       # 被验证次数
    source_turns: List[int] = field(default_factory=list)     # 原始来源（轮次）
    source_memory_ids: List[str] = field(default_factory=list)  # 来源记忆ID列表
    last_verified: str = ""           # ISO格式时间戳
    
    # 关系
    relations: List[Dict] = field(default_factory=list)


class ConsolidatedMemory:
    """L1长期记忆管理器"""
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.storage_dir = os.path.join(data_path, 'L1_consolidated')
        self.entities: Dict[str, ConsolidatedEntity] = {}
        self._load()
    
    def _load(self):
        """加载所有长期记忆"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)
            return
        
        for file in os.listdir(self.storage_dir):
            if file.startswith('entities_') and file.endswith('.json'):
                file_path = os.path.join(self.storage_dir, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        entity = ConsolidatedEntity(**item)
                        self.entities[entity.id] = entity
    
    def _save(self):
        """保存长期记忆（分片存储）"""
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # 每1000个实体一个文件
        entities_list = list(self.entities.values())
        chunk_size = 1000
        
        for i in range(0, len(entities_list), chunk_size):
            chunk = entities_list[i:i+chunk_size]
            file_path = os.path.join(self.storage_dir, f'entities_{i//chunk_size+1:04d}.json')
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([asdict(e) for e in chunk], f, ensure_ascii=False, indent=2)
    
    def add_or_update(self, entity: ConsolidatedEntity):
        """添加或更新实体"""
        if entity.id in self.entities:
            existing = self.entities[entity.id]
            existing.verification_count += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
            existing.last_verified = datetime.now().isoformat()
            # 合并状态
            existing.current_state.update(entity.current_state)
            # 合并来源记忆ID（确保不重复）
            if not hasattr(existing, 'source_memory_ids'):
                existing.source_memory_ids = []
            for mid in getattr(entity, 'source_memory_ids', []):
                if mid and mid not in existing.source_memory_ids:
                    existing.source_memory_ids.append(mid)
        else:
            self.entities[entity.id] = entity
        self._save()
    
    def get(self, entity_id: str) -> Optional[ConsolidatedEntity]:
        """获取实体"""
        return self.entities.get(entity_id)
    
    def get_entity(self, name: str) -> Optional[ConsolidatedEntity]:
        """通过名称获取实体"""
        for entity in self.entities.values():
            if entity.name.lower() == name.lower():
                return entity
            if name.lower() in [a.lower() for a in entity.aliases]:
                return entity
        return None
    
    def search_by_name(self, name: str) -> List[ConsolidatedEntity]:
        """按名称搜索"""
        name_lower = name.lower()
        results = []
        for entity in self.entities.values():
            if name_lower in entity.name.lower():
                results.append(entity)
            elif any(name_lower in alias.lower() for alias in entity.aliases):
                results.append(entity)
        return results
    
    def get_all_entity_names(self) -> List[str]:
        """获取所有实体名称（包括别名）"""
        names = []
        for entity in self.entities.values():
            names.append(entity.name)
            names.extend(entity.aliases)
        return names
    
    def clear(self):
        """清空所有长期记忆实体"""
        self.entities.clear()
        # 删除存储目录中的所有实体文件
        if os.path.exists(self.storage_dir):
            import shutil
            shutil.rmtree(self.storage_dir)
            os.makedirs(self.storage_dir, exist_ok=True)
    
    def remove_by_memory_ids(self, memory_ids: List[str]) -> int:
        """移除与指定记忆ID关联的实体
        
        从每个实体的 source_memory_ids 中移除指定的记忆ID。
        如果实体的 source_memory_ids 变为空，则删除该实体。
        
        Args:
            memory_ids: 要移除的记忆ID列表
        
        Returns:
            int: 被完全删除的实体数量
        """
        if not memory_ids:
            return 0
        
        memory_id_set = set(memory_ids)
        entities_to_delete = []
        modified = False
        
        for entity_id, entity in self.entities.items():
            # 检查是否有 source_memory_ids 属性（兼容旧数据）
            if not hasattr(entity, 'source_memory_ids'):
                entity.source_memory_ids = []
            
            if not entity.source_memory_ids:
                # 旧数据没有 source_memory_ids，保留实体
                continue
            
            # 过滤掉被删除的记忆引用
            remaining_refs = [
                ref for ref in entity.source_memory_ids 
                if ref not in memory_id_set
            ]
            
            if not remaining_refs:
                # 没有剩余引用，标记删除
                entities_to_delete.append(entity_id)
            elif len(remaining_refs) != len(entity.source_memory_ids):
                # 有部分引用被移除，更新
                entity.source_memory_ids = remaining_refs
                modified = True
        
        # 删除无引用的实体
        for entity_id in entities_to_delete:
            del self.entities[entity_id]
        
        if entities_to_delete or modified:
            self._save()
        
        return len(entities_to_delete)
