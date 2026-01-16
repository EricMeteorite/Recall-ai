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
        """简单搜索记忆"""
        results = []
        query_lower = query.lower()
        
        for memory in self._memories:
            content = memory.get('content', '')
            if query_lower in content.lower():
                results.append(memory)
        
        return results[:limit]
    
    def get_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有记忆"""
        return self._memories[-limit:]
    
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
