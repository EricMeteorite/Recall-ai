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
        return f"{self.user_id}/{self.character_id}/{self.session_id}"


class ScopedMemory:
    """作用域内的记忆存储"""
    
    def __init__(self, data_path: str, scope: MemoryScope):
        self.data_path = data_path
        self.scope = scope
        self.working_memory = WorkingMemory()
        self._memories: List[Dict[str, Any]] = []
        self._memory_file = os.path.join(data_path, 'memories.json')
        self._load()
    
    def _load(self):
        """加载记忆"""
        if os.path.exists(self._memory_file):
            try:
                with open(self._memory_file, 'r', encoding='utf-8') as f:
                    self._memories = json.load(f)
            except:
                self._memories = []
    
    def _save(self):
        """保存记忆"""
        # 确保目录存在
        memory_dir = os.path.dirname(self._memory_file)
        if memory_dir:
            os.makedirs(memory_dir, exist_ok=True)
        with open(self._memory_file, 'w', encoding='utf-8') as f:
            json.dump(self._memories, f, ensure_ascii=False, indent=2)
    
    def add(self, content: str, metadata: Dict[str, Any] = None):
        """添加记忆"""
        memory = {
            'content': content,
            'metadata': metadata or {},
            'timestamp': __import__('time').time()
        }
        self._memories.append(memory)
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
        self._save()
        self.working_memory = WorkingMemory()


class MultiTenantStorage:
    """多租户存储管理"""
    
    def __init__(self, base_path: str):
        self.base_path = base_path
        self._scopes: Dict[str, ScopedMemory] = {}
    
    def get_scope(self, user_id: str, session_id: str = "default", 
                  character_id: str = "default") -> ScopedMemory:
        """获取或创建作用域"""
        scope = MemoryScope(user_id=user_id, session_id=session_id, 
                           character_id=character_id)
        scope_key = scope.to_path()
        
        if scope_key not in self._scopes:
            data_path = self.get_data_path(scope)
            self._scopes[scope_key] = ScopedMemory(data_path, scope)
        
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
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
