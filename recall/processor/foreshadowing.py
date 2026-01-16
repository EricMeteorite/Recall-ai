"""伏笔追踪器 - 追踪未解决的叙事线索"""

import time
from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


class ForeshadowingStatus(Enum):
    """伏笔状态"""
    PLANTED = "planted"        # 已埋下
    DEVELOPING = "developing"  # 发展中
    RESOLVED = "resolved"      # 已解决
    ABANDONED = "abandoned"    # 已放弃


@dataclass
class Foreshadowing:
    """伏笔实体"""
    id: str
    content: str
    status: ForeshadowingStatus = ForeshadowingStatus.PLANTED
    planted_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    related_entities: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    resolution: Optional[str] = None
    importance: float = 0.5  # 0-1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'content': self.content,
            'status': self.status.value,
            'planted_at': self.planted_at,
            'resolved_at': self.resolved_at,
            'related_entities': self.related_entities,
            'hints': self.hints,
            'resolution': self.resolution,
            'importance': self.importance
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Foreshadowing':
        """从字典创建"""
        data = data.copy()
        data['status'] = ForeshadowingStatus(data['status'])
        return cls(**data)


class ForeshadowingTracker:
    """伏笔追踪器 - 完整版"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.foreshadowings: Dict[str, Foreshadowing] = {}
        self.storage_path = storage_path
        self._id_counter = 0
        
        if storage_path:
            self._load()
    
    def plant(
        self,
        content: str,
        related_entities: Optional[List[str]] = None,
        importance: float = 0.5
    ) -> Foreshadowing:
        """埋下伏笔"""
        self._id_counter += 1
        foreshadowing_id = f"fsh_{self._id_counter}_{int(time.time())}"
        
        foreshadowing = Foreshadowing(
            id=foreshadowing_id,
            content=content,
            status=ForeshadowingStatus.PLANTED,
            related_entities=related_entities or [],
            importance=importance
        )
        
        self.foreshadowings[foreshadowing_id] = foreshadowing
        self._save()
        
        return foreshadowing
    
    def add_hint(self, foreshadowing_id: str, hint: str) -> bool:
        """添加伏笔提示"""
        if foreshadowing_id not in self.foreshadowings:
            return False
        
        fsh = self.foreshadowings[foreshadowing_id]
        fsh.hints.append(hint)
        
        # 有提示时状态变为发展中
        if fsh.status == ForeshadowingStatus.PLANTED:
            fsh.status = ForeshadowingStatus.DEVELOPING
        
        self._save()
        return True
    
    def resolve(self, foreshadowing_id: str, resolution: str) -> bool:
        """解决伏笔"""
        if foreshadowing_id not in self.foreshadowings:
            return False
        
        fsh = self.foreshadowings[foreshadowing_id]
        fsh.status = ForeshadowingStatus.RESOLVED
        fsh.resolution = resolution
        fsh.resolved_at = time.time()
        
        self._save()
        return True
    
    def abandon(self, foreshadowing_id: str) -> bool:
        """放弃伏笔"""
        if foreshadowing_id not in self.foreshadowings:
            return False
        
        self.foreshadowings[foreshadowing_id].status = ForeshadowingStatus.ABANDONED
        self._save()
        return True
    
    def get_active(self) -> List[Foreshadowing]:
        """获取活跃的伏笔"""
        return [
            f for f in self.foreshadowings.values()
            if f.status in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.DEVELOPING)
        ]
    
    def get_by_entity(self, entity_name: str) -> List[Foreshadowing]:
        """获取与实体相关的伏笔"""
        return [
            f for f in self.foreshadowings.values()
            if entity_name in f.related_entities
        ]
    
    def get_summary(self) -> str:
        """获取伏笔摘要"""
        active = self.get_active()
        if not active:
            return "当前没有活跃的伏笔。"
        
        lines = ["活跃的伏笔："]
        for f in sorted(active, key=lambda x: -x.importance):
            status_emoji = "🌱" if f.status == ForeshadowingStatus.PLANTED else "🌿"
            lines.append(f"  {status_emoji} {f.content[:50]}{'...' if len(f.content) > 50 else ''}")
            if f.hints:
                lines.append(f"     提示: {len(f.hints)} 条")
        
        return "\n".join(lines)
    
    def _save(self):
        """保存到文件"""
        if not self.storage_path:
            return
        
        import json
        import os
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        data = {
            'id_counter': self._id_counter,
            'foreshadowings': {k: v.to_dict() for k, v in self.foreshadowings.items()}
        }
        
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load(self):
        """从文件加载"""
        import json
        import os
        
        if not os.path.exists(self.storage_path):
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._id_counter = data.get('id_counter', 0)
            self.foreshadowings = {
                k: Foreshadowing.from_dict(v)
                for k, v in data.get('foreshadowings', {}).items()
            }
        except Exception as e:
            print(f"[Recall] 加载伏笔数据失败: {e}")


class ForeshadowingTrackerLite:
    """伏笔追踪器 - 轻量版（无持久化）"""
    
    def __init__(self):
        self.foreshadowings: List[Dict[str, Any]] = []
    
    def plant(self, content: str, **kwargs) -> Dict[str, Any]:
        """埋下伏笔"""
        fsh = {
            'id': len(self.foreshadowings),
            'content': content,
            'status': 'planted',
            'planted_at': time.time(),
            **kwargs
        }
        self.foreshadowings.append(fsh)
        return fsh
    
    def get_active(self) -> List[Dict[str, Any]]:
        """获取活跃伏笔"""
        return [f for f in self.foreshadowings if f.get('status') in ('planted', 'developing')]
    
    def resolve(self, foreshadowing_id: int, resolution: str) -> bool:
        """解决伏笔"""
        for fsh in self.foreshadowings:
            if fsh['id'] == foreshadowing_id:
                fsh['status'] = 'resolved'
                fsh['resolution'] = resolution
                return True
        return False
