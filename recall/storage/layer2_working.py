"""L2工作记忆 - 完整实现"""

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class WorkingEntity:
    """工作记忆中的实体"""
    name: str
    entity_type: str
    last_accessed: int  # turn number
    access_count: int
    data: Dict[str, Any]


class WorkingMemory:
    """工作记忆 - 当前会话的活跃上下文"""
    
    def __init__(self, capacity: int = 200):
        self.capacity = capacity
        self.entities: Dict[str, WorkingEntity] = {}      # name -> entity
        self.events: List[Dict] = []        # 最近事件
        self.focus_stack: List[str] = []    # 当前焦点栈（实体名列表）
        self.current_turn: int = 0
    
    def update_with_delta_rule(self, new_info):
        """Delta Rule: 新信息可以覆盖相关旧信息"""
        # new_info 可以是 ExtractedEntity 或 dict
        if hasattr(new_info, 'name'):
            name = new_info.name
            entity_type = getattr(new_info, 'entity_type', 'UNKNOWN')
            data = {'source': getattr(new_info, 'source_text', '')}
        else:
            name = new_info.get('name', str(new_info))
            entity_type = new_info.get('entity_type', 'UNKNOWN')
            data = new_info
        
        if name in self.entities:
            # 更新已有实体
            existing = self.entities[name]
            existing.last_accessed = self.current_turn
            existing.access_count += 1
            existing.data.update(data if isinstance(data, dict) else {})
        else:
            # 容量满则淘汰
            if len(self.entities) >= self.capacity:
                self._evict_one()
            
            # 添加新实体
            self.entities[name] = WorkingEntity(
                name=name,
                entity_type=entity_type,
                last_accessed=self.current_turn,
                access_count=1,
                data=data if isinstance(data, dict) else {'value': data}
            )
        
        # 更新焦点栈
        if name in self.focus_stack:
            self.focus_stack.remove(name)
        self.focus_stack.append(name)
        if len(self.focus_stack) > 20:
            self.focus_stack.pop(0)
    
    def _evict_one(self):
        """淘汰一个最不活跃的实体"""
        if not self.entities:
            return
        
        # 找到最久未访问且访问次数最少的
        min_score = float('inf')
        to_evict = None
        
        for name, entity in self.entities.items():
            # 分数 = 访问次数 / (当前轮次 - 最后访问轮次 + 1)
            recency = self.current_turn - entity.last_accessed + 1
            score = entity.access_count / recency
            if score < min_score:
                min_score = score
                to_evict = name
        
        if to_evict:
            del self.entities[to_evict]
            if to_evict in self.focus_stack:
                self.focus_stack.remove(to_evict)
    
    def get_active_entities(self, limit: int = 50) -> List[WorkingEntity]:
        """获取最活跃的实体"""
        sorted_entities = sorted(
            self.entities.values(),
            key=lambda e: (e.access_count, e.last_accessed),
            reverse=True
        )
        return sorted_entities[:limit]
    
    def increment_turn(self):
        """增加轮次计数"""
        self.current_turn += 1
