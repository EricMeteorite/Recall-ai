"""伏笔追踪器 — v7.0 兼容性存根

原始实现已在 v7.0 中移除（非通用记忆功能）。
此存根保持向后兼容：
  - SillyTavern 插件仍可调用伏笔相关 API
  - 所有方法返回空结果或 no-op
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import os, json, uuid


class ForeshadowingStatus(str, Enum):
    """伏笔状态（兼容存根）"""
    UNRESOLVED = "UNRESOLVED"
    POSSIBLY_TRIGGERED = "POSSIBLY_TRIGGERED"
    RESOLVED = "RESOLVED"
    ARCHIVED = "ARCHIVED"


@dataclass
class Foreshadowing:
    """伏笔数据模型（存根）"""
    id: str = ""
    content: str = ""
    hints: List[str] = field(default_factory=list)
    user_id: str = "default"
    character_id: str = "default"
    status: str = "UNRESOLVED"
    created_at: str = ""
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    related_entities: List[str] = field(default_factory=list)
    archived: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'content': self.content,
            'hints': self.hints,
            'user_id': self.user_id,
            'character_id': self.character_id,
            'status': self.status,
            'created_at': self.created_at,
            'resolved_at': self.resolved_at,
            'resolution': self.resolution,
            'metadata': self.metadata,
            'importance': self.importance,
            'related_entities': self.related_entities,
            'archived': self.archived,
        }


class ForeshadowingTracker:
    """伏笔追踪器（v7.0 兼容性存根 — 支持基本去重）"""
    
    def __init__(self, base_path: str = "", storage_dir: str = "", embedding_backend=None, **kwargs):
        self._base_path = base_path or storage_dir
        self._embedding_backend = embedding_backend
        self._storage_file = os.path.join(self._base_path, "foreshadowing.json") if self._base_path else ""
        self._items: Dict[str, Foreshadowing] = {}
        self._load()
    
    def _load(self):
        if self._storage_file and os.path.exists(self._storage_file):
            try:
                with open(self._storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for item_data in data:
                    fs = Foreshadowing(**{k: v for k, v in item_data.items() if k in Foreshadowing.__dataclass_fields__})
                    if fs.id:
                        self._items[fs.id] = fs
            except Exception:
                pass

    def _save(self):
        """v7.0.10: 原子写入保护"""
        if self._storage_file:
            try:
                os.makedirs(os.path.dirname(self._storage_file), exist_ok=True)
                from recall.utils.atomic_write import atomic_json_dump
                atomic_json_dump(
                    [item.to_dict() for item in self._items.values()],
                    self._storage_file, ensure_ascii=False, indent=2
                )
            except Exception:
                pass
    
    def plant(self, content: str, hints=None, user_id: str = "default",
              character_id: str = "default", metadata: Dict[str, Any] = None,
              importance: float = 0.5, related_entities: List[str] = None, **kwargs) -> Foreshadowing:
        """种下伏笔（支持去重）"""
        # 向后兼容：第二个位置参数如果是字符串，当作 user_id
        if isinstance(hints, str):
            user_id = hints
            hints = None
        
        # 去重检查：精确匹配
        for existing in self._items.values():
            if existing.content == content and existing.user_id == user_id and not existing.archived:
                existing.importance = min(1.0, existing.importance + 0.1)
                self._save()
                return existing
        
        # 去重检查：embedding 语义相似
        if self._embedding_backend:
            try:
                new_vec = self._get_embedding(content)
                if new_vec is not None:
                    threshold = float(os.environ.get('DEDUP_HIGH_THRESHOLD', '0.85'))
                    for existing in self._items.values():
                        if existing.user_id == user_id and not existing.archived:
                            old_vec = self._get_embedding(existing.content)
                            if old_vec is not None:
                                sim = self._cosine_similarity(new_vec, old_vec)
                                if sim >= threshold:
                                    existing.importance = min(1.0, existing.importance + 0.1)
                                    self._save()
                                    return existing
            except Exception:
                pass
        
        fs = Foreshadowing(
            id=str(uuid.uuid4()),
            content=content,
            hints=hints or [],
            user_id=user_id,
            character_id=character_id,
            created_at=datetime.now().isoformat(),
            metadata=metadata or {},
            importance=importance,
            related_entities=related_entities or [],
        )
        self._items[fs.id] = fs
        self._save()
        return fs
    
    def _get_embedding(self, text: str):
        """获取文本的 embedding 向量"""
        if not self._embedding_backend:
            return None
        if hasattr(self._embedding_backend, 'vectors'):
            return self._embedding_backend.vectors.get(text)
        if hasattr(self._embedding_backend, 'encode'):
            return self._embedding_backend.encode(text)
        if hasattr(self._embedding_backend, 'embed'):
            return self._embedding_backend.embed(text)
        return None
    
    @staticmethod
    def _cosine_similarity(a, b):
        """计算余弦相似度"""
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    def resolve(self, foreshadowing_id: str, resolution: str = "",
                user_id: str = "default", character_id: str = "default", **kwargs) -> bool:
        """解决伏笔"""
        fs = self._items.get(foreshadowing_id)
        if fs:
            fs.status = "RESOLVED"
            fs.resolution = resolution
            fs.resolved_at = datetime.now().isoformat()
            self._save()
            return True
        return False
    
    def get(self, foreshadowing_id: str) -> Optional[Foreshadowing]:
        return self._items.get(foreshadowing_id)
    
    def get_all(self, user_id: str = None, character_id: str = None,
                status: str = None, **kwargs) -> List[Foreshadowing]:
        """获取所有伏笔"""
        result = list(self._items.values())
        if user_id:
            result = [f for f in result if f.user_id == user_id]
        if character_id:
            result = [f for f in result if f.character_id == character_id]
        if status:
            result = [f for f in result if f.status == status]
        result = [f for f in result if not f.archived]
        return result
    
    def get_active(self, user_id: str = None, character_id: str = None, **kwargs) -> List[Foreshadowing]:
        """获取活跃（未解决）伏笔"""
        return self.get_all(user_id=user_id, character_id=character_id, status="UNRESOLVED")
    
    def get_archived(self, user_id: str = None, character_id: str = None, **kwargs) -> List[Foreshadowing]:
        result = [f for f in self._items.values() if f.archived]
        if user_id:
            result = [f for f in result if f.user_id == user_id]
        if character_id:
            result = [f for f in result if f.character_id == character_id]
        return result
    
    def add_hint(self, foreshadowing_id: str, hint: str, user_id: str = None, **kwargs) -> Optional[Foreshadowing]:
        """为伏笔添加提示"""
        fs = self._items.get(foreshadowing_id)
        if fs:
            fs.hints.append(hint)
            self._save()
        return fs

    def archive(self, foreshadowing_id: str, **kwargs) -> Optional[Foreshadowing]:
        fs = self._items.get(foreshadowing_id)
        if fs:
            fs.archived = True
            self._save()
        return fs
    
    def restore(self, foreshadowing_id: str, **kwargs) -> Optional[Foreshadowing]:
        fs = self._items.get(foreshadowing_id)
        if fs:
            fs.archived = False
            self._save()
        return fs
    
    def delete(self, foreshadowing_id: str, **kwargs) -> bool:
        if foreshadowing_id in self._items:
            del self._items[foreshadowing_id]
            self._save()
            return True
        return False
    
    def update(self, foreshadowing_id: str, **kwargs) -> Optional[Foreshadowing]:
        fs = self._items.get(foreshadowing_id)
        if fs:
            for key, value in kwargs.items():
                if hasattr(fs, key) and value is not None:
                    setattr(fs, key, value)
            self._save()
        return fs
    
    def check_triggers(self, content: str, user_id: str = "default",
                       character_id: str = "default", **kwargs) -> List[Dict[str, Any]]:
        """检查是否触发伏笔"""
        return []
    
    def get_context_for_prompt(self, user_id: str = "default", character_id: str = "default",
                               max_count: int = 5, current_turn: int = None, **kwargs) -> str:
        """为 prompt 构建伏笔上下文（兼容存根）"""
        active = self.get_active(user_id=user_id, character_id=character_id)
        if not active:
            return ""
        lines = ["【活跃伏笔】"]
        for fs in active[:max_count]:
            lines.append(f"- {fs.content}")
        return "\n".join(lines)
    
    def clear(self):
        self._items.clear()
        self._save()
    
    def clear_user(self, user_id: str, all_characters: bool = False):
        to_remove = [fid for fid, fs in self._items.items() if fs.user_id == user_id]
        for fid in to_remove:
            del self._items[fid]
        self._save()
    
    def count(self, user_id: str = None, character_id: str = None) -> int:
        items = list(self._items.values())
        if user_id:
            items = [f for f in items if f.user_id == user_id]
        if character_id:
            items = [f for f in items if f.character_id == character_id]
        return len(items)


class ForeshadowingTrackerLite(ForeshadowingTracker):
    """轻量版伏笔追踪器（兼容存根）"""
    pass
