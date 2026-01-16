"""多用户/多会话支持"""

import os
import json
import shutil
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class MemoryScope:
    """记忆作用域"""
    user_id: str = "default"      # 用户ID
    session_id: str = "default"   # 会话ID（可选）
    character_id: str = "default" # 角色ID（RP场景）
    
    def to_path(self) -> str:
        """转换为存储路径"""
        return f"{self.user_id}/{self.character_id}/{self.session_id}"


class MultiTenantStorage:
    """多租户存储管理"""
    
    def __init__(self, base_path: str):
        self.base_path = base_path
    
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
