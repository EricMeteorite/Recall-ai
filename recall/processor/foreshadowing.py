"""伏笔追踪器 - 追踪未解决的叙事线索（支持多角色）"""

import time
import os
import json
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
    """伏笔追踪器 - 支持多角色分隔存储"""
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Args:
            storage_dir: 存储目录路径，每个角色的伏笔存储在单独的文件中
        """
        self.storage_dir = storage_dir
        # 按 user_id 分隔的伏笔存储
        self._user_data: Dict[str, Dict[str, Any]] = {}
        
        if storage_dir:
            os.makedirs(storage_dir, exist_ok=True)
    
    def _get_user_storage_path(self, user_id: str) -> str:
        """获取用户的存储路径"""
        # 清理文件名中的非法字符
        safe_user_id = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in user_id)
        return os.path.join(self.storage_dir, f"foreshadowing_{safe_user_id}.json")
    
    def _load_user_data(self, user_id: str) -> Dict[str, Any]:
        """加载用户的伏笔数据"""
        if user_id in self._user_data:
            return self._user_data[user_id]
        
        data = {
            'id_counter': 0,
            'foreshadowings': {}
        }
        
        if self.storage_dir:
            path = self._get_user_storage_path(user_id)
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    data['id_counter'] = loaded.get('id_counter', 0)
                    data['foreshadowings'] = {
                        k: Foreshadowing.from_dict(v)
                        for k, v in loaded.get('foreshadowings', {}).items()
                    }
                except Exception as e:
                    print(f"[Recall] 加载伏笔数据失败 ({user_id}): {e}")
        
        self._user_data[user_id] = data
        return data
    
    def _save_user_data(self, user_id: str):
        """保存用户的伏笔数据"""
        if not self.storage_dir:
            return
        
        data = self._user_data.get(user_id, {})
        if not data:
            return
        
        path = self._get_user_storage_path(user_id)
        save_data = {
            'id_counter': data.get('id_counter', 0),
            'foreshadowings': {
                k: v.to_dict() for k, v in data.get('foreshadowings', {}).items()
            }
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    def plant(
        self,
        content: str,
        user_id: str = "default",
        related_entities: Optional[List[str]] = None,
        importance: float = 0.5
    ) -> Foreshadowing:
        """埋下伏笔"""
        user_data = self._load_user_data(user_id)
        user_data['id_counter'] += 1
        
        foreshadowing_id = f"fsh_{user_data['id_counter']}_{int(time.time())}"
        
        foreshadowing = Foreshadowing(
            id=foreshadowing_id,
            content=content,
            status=ForeshadowingStatus.PLANTED,
            related_entities=related_entities or [],
            importance=importance
        )
        
        user_data['foreshadowings'][foreshadowing_id] = foreshadowing
        self._save_user_data(user_id)
        
        return foreshadowing
    
    def add_hint(self, foreshadowing_id: str, hint: str, user_id: str = "default") -> bool:
        """添加伏笔提示"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        fsh = foreshadowings[foreshadowing_id]
        fsh.hints.append(hint)
        
        if fsh.status == ForeshadowingStatus.PLANTED:
            fsh.status = ForeshadowingStatus.DEVELOPING
        
        self._save_user_data(user_id)
        return True
    
    def resolve(self, foreshadowing_id: str, resolution: str, user_id: str = "default") -> bool:
        """解决伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        fsh = foreshadowings[foreshadowing_id]
        fsh.status = ForeshadowingStatus.RESOLVED
        fsh.resolution = resolution
        fsh.resolved_at = time.time()
        
        self._save_user_data(user_id)
        return True
    
    def abandon(self, foreshadowing_id: str, user_id: str = "default") -> bool:
        """放弃伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        foreshadowings[foreshadowing_id].status = ForeshadowingStatus.ABANDONED
        self._save_user_data(user_id)
        return True
    
    def get_active(self, user_id: str = "default") -> List[Foreshadowing]:
        """获取活跃的伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        return [
            f for f in foreshadowings.values()
            if f.status in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.DEVELOPING)
        ]
    
    def get_by_entity(self, entity_name: str, user_id: str = "default") -> List[Foreshadowing]:
        """获取与实体相关的伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        return [
            f for f in foreshadowings.values()
            if entity_name in f.related_entities
        ]
    
    def get_summary(self, user_id: str = "default") -> str:
        """获取伏笔摘要"""
        active = self.get_active(user_id)
        if not active:
            return "当前没有活跃的伏笔。"
        
        lines = ["活跃的伏笔："]
        for f in sorted(active, key=lambda x: -x.importance):
            status_emoji = "🌱" if f.status == ForeshadowingStatus.PLANTED else "🌿"
            lines.append(f"  {status_emoji} {f.content[:50]}{'...' if len(f.content) > 50 else ''}")
            if f.hints:
                lines.append(f"     提示: {len(f.hints)} 条")
        
        return "\n".join(lines)
    
    def get_context_for_prompt(
        self,
        user_id: str = "default",
        max_count: int = 5,
        current_turn: Optional[int] = None
    ) -> str:
        """生成用于注入 prompt 的伏笔上下文
        
        Args:
            user_id: 用户ID
            max_count: 最多返回的伏笔数量
            current_turn: 当前轮次（用于主动提醒判断）
        
        Returns:
            str: 格式化的伏笔上下文，可直接注入 prompt
        """
        active = self.get_active(user_id)
        if not active:
            return ""
        
        # 按重要性排序，取前 max_count 个
        active = sorted(active, key=lambda x: -x.importance)[:max_count]
        
        lines = ["<foreshadowings>", "【活跃伏笔 - AI需要在适当时机推进或解决这些伏笔】"]
        
        for i, f in enumerate(active, 1):
            status = "埋下" if f.status == ForeshadowingStatus.PLANTED else "发展中"
            lines.append(f"{i}. [{status}] {f.content}")
            if f.hints:
                lines.append(f"   已有提示: {', '.join(f.hints[-3:])}")  # 只显示最近3条提示
            
            # 主动提醒逻辑：如果伏笔很重要且长时间未发展，提醒AI
            if current_turn and f.importance >= 0.7:
                age = (time.time() - f.planted_at) / 3600  # 小时
                if age > 2 and f.status == ForeshadowingStatus.PLANTED:
                    lines.append(f"   ⚠️ 这个重要伏笔已埋下较长时间，考虑推进或给出提示")
        
        lines.append("</foreshadowings>")
        return "\n".join(lines)


class ForeshadowingTrackerLite:
    """伏笔追踪器 - 轻量版（无持久化，支持多角色）"""
    
    def __init__(self):
        # 按 user_id 分隔
        self._user_foreshadowings: Dict[str, List[Dict[str, Any]]] = {}
    
    def plant(self, content: str, user_id: str = "default", **kwargs) -> Dict[str, Any]:
        """埋下伏笔"""
        if user_id not in self._user_foreshadowings:
            self._user_foreshadowings[user_id] = []
        
        fsh_list = self._user_foreshadowings[user_id]
        fsh = {
            'id': f"fsh_{len(fsh_list)}_{int(time.time())}",
            'content': content,
            'status': 'planted',
            'planted_at': time.time(),
            'importance': kwargs.get('importance', 0.5),
            'related_entities': kwargs.get('related_entities', []),
            'hints': [],
            'resolution': None
        }
        fsh_list.append(fsh)
        return fsh
    
    def get_active(self, user_id: str = "default") -> List[Dict[str, Any]]:
        """获取活跃伏笔"""
        fsh_list = self._user_foreshadowings.get(user_id, [])
        return [f for f in fsh_list if f.get('status') in ('planted', 'developing')]
    
    def resolve(self, foreshadowing_id: str, resolution: str, user_id: str = "default") -> bool:
        """解决伏笔"""
        fsh_list = self._user_foreshadowings.get(user_id, [])
        for fsh in fsh_list:
            if fsh['id'] == foreshadowing_id:
                fsh['status'] = 'resolved'
                fsh['resolution'] = resolution
                return True
        return False

