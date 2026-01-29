"""Episode 存储 - Recall 4.1

负责 Episode 的持久化存储和查询。
复用现有的 EpisodicNode（来自 recall/models/temporal.py）。
"""

from __future__ import annotations

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

# 复用现有的 EpisodicNode
from ..models.temporal import EpisodicNode, EpisodeType


class EpisodeStore:
    """Episode 持久化存储
    
    使用 JSONL 格式存储，支持：
    - 追加写入
    - 按 UUID 查询
    - 按 memory_id 查询
    - 按 entity_id 查询
    """
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.episodes_file = os.path.join(data_path, 'episodes.jsonl')
        self._episodes: Dict[str, EpisodicNode] = {}
        self._load()
    
    def _load(self):
        """加载所有 Episode"""
        if not os.path.exists(self.episodes_file):
            return
        
        try:
            with open(self.episodes_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        ep = EpisodicNode.from_dict(data)
                        self._episodes[ep.uuid] = ep
        except Exception as e:
            print(f"[EpisodeStore] 加载失败: {e}")
    
    def save(self, episode: EpisodicNode) -> EpisodicNode:
        """保存单个 Episode"""
        self._episodes[episode.uuid] = episode
        self._append_to_file(episode)
        return episode
    
    def _append_to_file(self, episode: EpisodicNode):
        """追加到文件"""
        os.makedirs(os.path.dirname(self.episodes_file), exist_ok=True)
        with open(self.episodes_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(episode.to_dict(), ensure_ascii=False) + '\n')
    
    def get(self, uuid: str) -> Optional[EpisodicNode]:
        """获取 Episode"""
        return self._episodes.get(uuid)
    
    def get_by_memory_id(self, memory_id: str) -> List[EpisodicNode]:
        """通过记忆ID查找关联的 Episode"""
        return [ep for ep in self._episodes.values() if memory_id in ep.memory_ids]
    
    def get_by_entity_id(self, entity_id: str) -> List[EpisodicNode]:
        """通过实体ID查找关联的 Episode"""
        # 使用 entity_edges 字段
        return [ep for ep in self._episodes.values() if entity_id in ep.entity_edges]
    
    def get_by_relation_id(self, relation_id: str) -> List[EpisodicNode]:
        """通过关系ID查找关联的 Episode"""
        return [ep for ep in self._episodes.values() if relation_id in ep.relation_ids]
    
    def get_by_user(self, user_id: str) -> List[EpisodicNode]:
        """通过用户ID查找 Episode"""
        return [ep for ep in self._episodes.values() if ep.user_id == user_id]
    
    def get_by_character(self, character_id: str) -> List[EpisodicNode]:
        """通过角色ID查找 Episode"""
        return [ep for ep in self._episodes.values() if ep.character_id == character_id]
    
    def update_links(
        self,
        episode_uuid: str,
        memory_ids: Optional[List[str]] = None,
        entity_ids: Optional[List[str]] = None,
        relation_ids: Optional[List[str]] = None
    ):
        """更新 Episode 的关联信息"""
        ep = self._episodes.get(episode_uuid)
        if not ep:
            return
        
        if memory_ids:
            ep.memory_ids.extend([m for m in memory_ids if m not in ep.memory_ids])
        if entity_ids:
            ep.entity_edges.extend([e for e in entity_ids if e not in ep.entity_edges])
        if relation_ids:
            ep.relation_ids.extend([r for r in relation_ids if r not in ep.relation_ids])
        
        # 重写整个文件以更新
        self._rewrite_all()
    
    def _rewrite_all(self):
        """重写所有 Episode 到文件"""
        os.makedirs(os.path.dirname(self.episodes_file), exist_ok=True)
        with open(self.episodes_file, 'w', encoding='utf-8') as f:
            for ep in self._episodes.values():
                f.write(json.dumps(ep.to_dict(), ensure_ascii=False) + '\n')
    
    def count(self) -> int:
        """返回 Episode 数量"""
        return len(self._episodes)
    
    def get_all(self) -> List[EpisodicNode]:
        """获取所有 Episode"""
        return list(self._episodes.values())
    
    def get_recent(self, limit: int = 100) -> List[EpisodicNode]:
        """获取最近的 Episode"""
        episodes = sorted(
            self._episodes.values(),
            key=lambda x: x.created_at if x.created_at else datetime.min,
            reverse=True
        )
        return episodes[:limit]
