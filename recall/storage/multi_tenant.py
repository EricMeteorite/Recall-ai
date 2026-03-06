"""多用户/多会话支持"""

import os
import json
import shutil
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .layer2_working import WorkingMemory


@dataclass
class MemoryScope:
    """记忆作用域"""
    user_id: str = "default"      # 用户ID
    session_id: str = "default"   # 会话ID（可选）
    character_id: str = "default" # 角色ID（RP场景）
    
    def to_path(self) -> str:
        """转换为存储路径"""
        return os.path.join(self.user_id, self.character_id, self.session_id)


class ScopedMemory:
    """作用域内的记忆存储"""
    
    MAX_MEMORIES = 5000  # A12: LRU 内存保护上限
    
    def __init__(self, data_path: str, scope: MemoryScope):
        self.data_path = data_path
        self.scope = scope
        self.working_memory = WorkingMemory()
        self._memories: List[Dict[str, Any]] = []
        self._memory_index: Dict[str, Dict[str, Any]] = {}  # A11: memory_id → memory (O(1) lookup)
        self._memory_file = os.path.join(data_path, 'memories.json')
        # v7.0.2: 驱逐回调 — 用于通知引擎清理被驱逐记忆的索引条目
        self._on_evict_callback: Optional[Any] = None
        self._load()
    
    def _load(self):
        """加载记忆"""
        if os.path.exists(self._memory_file):
            try:
                with open(self._memory_file, 'r', encoding='utf-8') as f:
                    self._memories = json.load(f)
            except Exception as e:
                # v7.0.14: 修复 M5 — 损坏时记录警告日志，而非静默丢弃
                import logging
                logging.warning(
                    f"[Recall] memories.json 加载失败，数据可能已损坏，回退为空列表: "
                    f"file={self._memory_file}, error={e}"
                )
                self._memories = []
        self._rebuild_index()
        # A12: 加载时如果超出上限，裁剪最旧的条目
        if len(self._memories) > self.MAX_MEMORIES:
            self._evict_oldest(len(self._memories) - self.MAX_MEMORIES)
    
    def _rebuild_index(self):
        """重建 memory_id → memory 的 O(1) 索引"""
        self._memory_index = {}
        for memory in self._memories:
            mid = memory.get('metadata', {}).get('id')
            if mid:
                self._memory_index[mid] = memory
    
    def _evict_oldest(self, count: int):
        """驱逐最旧的 count 条记忆 (LRU 保护)"""
        if count <= 0:
            return
        evicted = self._memories[:count]
        self._memories = self._memories[count:]
        # 同步索引
        evicted_ids = []
        for memory in evicted:
            mid = memory.get('metadata', {}).get('id')
            if mid and mid in self._memory_index:
                del self._memory_index[mid]
                evicted_ids.append(mid)
        self._save()
        # v7.0.2: 通知引擎清理被驱逐记忆的所有索引条目（消除幽灵条目）
        if evicted_ids and self._on_evict_callback:
            try:
                self._on_evict_callback(evicted_ids)
            except Exception as e:
                import logging
                logging.warning(f"[Recall] ScopedMemory 驱逐回调失败: {e}")
    
    def get_content_by_id(self, memory_id: str) -> Optional[str]:
        """通过 ID 获取记忆内容 — O(1) 查找"""
        memory = self._memory_index.get(memory_id)
        if memory:
            return memory.get('content', '')
        return None
    
    def _save(self):
        """保存记忆（原子写入：tmp+rename 防止断电损坏）"""
        from recall.utils.atomic_write import atomic_json_dump
        atomic_json_dump(self._memories, self._memory_file, indent=2)
    
    def add(self, content: str, metadata: Dict[str, Any] = None):
        """添加记忆"""
        memory = {
            'content': content,
            'metadata': metadata or {},
            'timestamp': __import__('time').time()
        }
        self._memories.append(memory)
        # A11: 维护 O(1) 索引
        mid = memory.get('metadata', {}).get('id')
        if mid:
            self._memory_index[mid] = memory
        # A12: LRU 驱逐
        if len(self._memories) > self.MAX_MEMORIES:
            self._evict_oldest(len(self._memories) - self.MAX_MEMORIES)
        self._save()
        
        # 更新工作记忆
        self.working_memory.update_with_delta_rule({
            'name': content[:50],  # 用内容摘要作为key
            'entity_type': 'MEMORY',
            'content': content,
            **(metadata or {})
        })
    
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """智能搜索记忆 - 使用关键词匹配
        
        搜索策略：
        1. 完全匹配查询字符串（最高分）
        2. 匹配查询中的所有关键词
        3. 匹配部分关键词
        4. 匹配实体名称
        """
        results = []
        query_lower = query.lower()
        
        # 提取查询中的关键词（简单分词）
        import re
        # 中文按单字符分割，英文按空格分割
        keywords = set()
        # 提取中文词
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', query_lower)
        for chars in chinese_chars:
            if len(chars) >= 2:
                keywords.add(chars)
                # 也添加两字词组合
                for i in range(len(chars) - 1):
                    keywords.add(chars[i:i+2])
        # 提取英文词
        english_words = re.findall(r'[a-z]+', query_lower)
        keywords.update(w for w in english_words if len(w) > 2)
        
        # 过滤掉常见停用词
        stopwords = {'的', '了', '是', '在', '有', '和', '与', '或', '但', '如果', '这', '那'}
        keywords = keywords - stopwords
        
        for memory in self._memories:
            content = memory.get('content', '')
            content_lower = content.lower()
            entities = memory.get('metadata', {}).get('entities', [])
            
            score = 0
            
            # 完全匹配
            if query_lower in content_lower:
                score += 1.0
            
            # 关键词匹配
            if keywords:
                matched_keywords = sum(1 for kw in keywords if kw in content_lower)
                score += matched_keywords / len(keywords) * 0.8
            
            # 实体匹配
            for entity in entities:
                if entity.lower() in query_lower or query_lower in entity.lower():
                    score += 0.3
            
            if score > 0:
                result = memory.copy()
                result['score'] = score
                results.append(result)
        
        # 按分数排序
        results.sort(key=lambda x: -x.get('score', 0))
        return results[:limit]
    
    def get_all(self, limit: int = None) -> List[Dict[str, Any]]:
        """获取所有记忆
        
        Args:
            limit: 限制数量，None表示返回全部
        """
        if limit is None:
            return self._memories.copy()
        return self._memories[-limit:]
    
    def get_paginated(self, offset: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """分页获取记忆（高效版本，不复制整个列表）
        
        Args:
            offset: 偏移量（跳过的记录数）
            limit: 每页数量
        
        Returns:
            List[Dict]: 分页后的记忆列表
        """
        # 直接切片，不需要复制整个列表
        return self._memories[offset:offset + limit]
    
    def count(self) -> int:
        """获取记忆总数（O(1)操作）
        
        Returns:
            int: 记忆总数
        """
        return len(self._memories)
    
    def get_recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取最近的记忆"""
        return self._memories[-limit:]
    
    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        for i, memory in enumerate(self._memories):
            if memory.get('metadata', {}).get('id') == memory_id:
                del self._memories[i]
                # A11: 同步索引
                self._memory_index.pop(memory_id, None)
                self._save()
                return True
        return False
    
    def update(self, memory_id: str, content: str, metadata: Dict[str, Any] = None) -> bool:
        """更新记忆"""
        for memory in self._memories:
            if memory.get('metadata', {}).get('id') == memory_id:
                memory['content'] = content
                if metadata:
                    memory['metadata'].update(metadata)
                memory['updated_at'] = __import__('time').time()
                self._save()
                return True
        return False
    
    def clear(self):
        """清空所有记忆"""
        self._memories = []
        self._memory_index = {}  # A11: 清空索引
        self._save()
        self.working_memory = WorkingMemory()


class MultiTenantStorage:
    """多租户存储管理"""
    
    def __init__(self, base_path: str):
        self.base_path = base_path
        self._scopes: Dict[str, ScopedMemory] = {}
        # v7.0.2: 驱逐回调 — 引擎注册此回调来清理被驱逐记忆的索引
        self._on_evict_callback: Optional[Any] = None
    
    def set_evict_callback(self, callback):
        """v7.0.2: 设置驱逐回调（引擎调用此方法注册级联清理）"""
        self._on_evict_callback = callback
        # 同步到已有 scopes
        for scope in self._scopes.values():
            scope._on_evict_callback = callback
    
    def get_scope(self, user_id: str, session_id: str = "default", 
                  character_id: str = "default") -> ScopedMemory:
        """获取或创建作用域"""
        scope = MemoryScope(user_id=user_id, session_id=session_id, 
                           character_id=character_id)
        scope_key = scope.to_path()
        
        if scope_key not in self._scopes:
            data_path = self.get_data_path(scope)
            scoped = ScopedMemory(data_path, scope)
            # v7.0.2: 注册驱逐回调
            if self._on_evict_callback:
                scoped._on_evict_callback = self._on_evict_callback
            self._scopes[scope_key] = scoped
        
        return self._scopes[scope_key]
    
    def get_data_path(self, scope: MemoryScope) -> str:
        """获取特定作用域的数据路径"""
        path = os.path.join(self.base_path, scope.to_path())
        os.makedirs(path, exist_ok=True)
        return path
    
    def list_users(self) -> List[str]:
        """列出所有用户"""
        if not os.path.exists(self.base_path):
            return []
        return [d for d in os.listdir(self.base_path) 
                if os.path.isdir(os.path.join(self.base_path, d))]
    
    def list_characters(self, user_id: str) -> List[str]:
        """列出用户的所有角色"""
        user_path = os.path.join(self.base_path, user_id)
        if not os.path.exists(user_path):
            return []
        return [d for d in os.listdir(user_path) 
                if os.path.isdir(os.path.join(user_path, d))]
    
    def delete_session(self, scope: MemoryScope):
        """删除特定会话的记忆"""
        path = self.get_data_path(scope)
        if os.path.exists(path):
            shutil.rmtree(path)
        # 清除缓存
        scope_key = scope.to_path()
        if scope_key in self._scopes:
            del self._scopes[scope_key]
    
    def export_memories(self, scope: MemoryScope) -> dict:
        """导出某作用域的所有记忆（用于备份/迁移）"""
        path = self.get_data_path(scope)
        
        export_data = {'scope': scope.__dict__, 'files': {}}
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.json'):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, path)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        export_data['files'][rel_path] = json.load(f)
        
        return export_data
    
    def import_memories(self, export_data: dict, target_scope: MemoryScope = None):
        """导入记忆"""
        scope = target_scope or MemoryScope(**export_data['scope'])
        path = self.get_data_path(scope)
        
        for rel_path, content in export_data['files'].items():
            file_path = os.path.join(path, rel_path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            # v7.0.12: 修复 — 使用原子写入保护导入数据
            from recall.utils.atomic_write import atomic_json_dump
            atomic_json_dump(content, file_path, ensure_ascii=False)
