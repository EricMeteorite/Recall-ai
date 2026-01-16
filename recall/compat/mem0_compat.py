"""mem0 兼容层 - 提供与 mem0 API 完全兼容的接口

使用方法（作为 mem0 的替代品）：
```python
# 原来的 mem0 代码
from mem0 import Memory
m = Memory()
m.add("用户喜欢咖啡", user_id="alice")
results = m.search("咖啡", user_id="alice")

# 使用 Recall 替代（只需改导入）
from recall.compat import Memory
m = Memory()
m.add("用户喜欢咖啡", user_id="alice")
results = m.search("咖啡", user_id="alice")
```
"""

import os
import time
import uuid
from typing import List, Dict, Any, Optional, Union


class Memory:
    """mem0 兼容的 Memory 类
    
    提供与 mem0.Memory 完全兼容的 API 接口。
    内部使用 Recall 引擎实现。
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs
    ):
        """初始化 Memory
        
        Args:
            api_key: API Key（兼容性参数，Recall 中可忽略）
            host: API 主机（兼容性参数）
            org_id: 组织ID（兼容性参数）
            project_id: 项目ID（兼容性参数）
            **kwargs: 其他参数传递给 RecallEngine
        """
        # 延迟导入避免循环依赖
        from ..engine import RecallEngine
        
        self._engine = RecallEngine(
            lightweight=kwargs.get('lightweight', True),
            **{k: v for k, v in kwargs.items() if k != 'lightweight'}
        )
        
        # 存储 mem0 兼容参数
        self.api_key = api_key
        self.host = host
        self.org_id = org_id
        self.project_id = project_id
    
    def add(
        self,
        messages: Union[str, List[Dict[str, str]]],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """添加记忆
        
        Args:
            messages: 消息内容（字符串或消息列表）
            user_id: 用户ID
            agent_id: 代理ID（会合并到 user_id）
            run_id: 运行ID（存储在 metadata 中）
            metadata: 元数据
            filters: 过滤器（兼容性参数）
            prompt: 提示（兼容性参数）
        
        Returns:
            Dict: 添加结果，格式与 mem0 兼容
        """
        # 处理 user_id
        effective_user_id = user_id or agent_id or "default"
        
        # 处理 metadata
        effective_metadata = metadata or {}
        if run_id:
            effective_metadata['run_id'] = run_id
        if agent_id:
            effective_metadata['agent_id'] = agent_id
        
        # 处理消息格式
        if isinstance(messages, str):
            contents = [messages]
        elif isinstance(messages, list):
            contents = [
                m.get('content', '') for m in messages
                if isinstance(m, dict) and m.get('content')
            ]
        else:
            contents = []
        
        # 添加记忆
        results = []
        for content in contents:
            result = self._engine.add(
                content=content,
                user_id=effective_user_id,
                metadata=effective_metadata
            )
            results.append({
                'id': result.id,
                'memory': content,
                'event': 'ADD' if result.success else 'FAILED'
            })
        
        return {
            'results': results,
            'relations': []  # Recall 不返回关系
        }
    
    def get(
        self,
        memory_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取单条记忆
        
        Args:
            memory_id: 记忆ID
        
        Returns:
            Dict: 记忆内容，格式与 mem0 兼容
        """
        # Recall 没有直接按 ID 获取的方法，需要搜索
        # 这里简化处理
        all_memories = self._engine.get_all(limit=1000)
        
        for m in all_memories:
            if m.get('id') == memory_id:
                return {
                    'id': memory_id,
                    'memory': m.get('content', m.get('memory', '')),
                    'user_id': m.get('user_id', 'default'),
                    'metadata': m.get('metadata', {}),
                    'created_at': m.get('created_at'),
                    'updated_at': m.get('updated_at')
                }
        
        return None
    
    def get_all(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取所有记忆
        
        Args:
            user_id: 用户ID
            agent_id: 代理ID
            run_id: 运行ID
            limit: 限制数量
        
        Returns:
            List[Dict]: 记忆列表，格式与 mem0 兼容
        """
        effective_user_id = user_id or agent_id or "default"
        
        memories = self._engine.get_all(
            user_id=effective_user_id,
            limit=limit
        )
        
        # 转换为 mem0 格式
        results = []
        for m in memories:
            # 如果指定了 run_id，过滤
            if run_id and m.get('metadata', {}).get('run_id') != run_id:
                continue
            
            results.append({
                'id': m.get('id', ''),
                'memory': m.get('content', m.get('memory', '')),
                'user_id': effective_user_id,
                'metadata': m.get('metadata', {}),
                'created_at': m.get('created_at'),
                'updated_at': m.get('updated_at')
            })
        
        return results
    
    def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """搜索记忆
        
        Args:
            query: 搜索查询
            user_id: 用户ID
            agent_id: 代理ID
            run_id: 运行ID
            limit: 限制数量
            filters: 过滤器
        
        Returns:
            List[Dict]: 搜索结果，格式与 mem0 兼容
        """
        effective_user_id = user_id or agent_id or "default"
        
        results = self._engine.search(
            query=query,
            user_id=effective_user_id,
            top_k=limit,
            filters=filters
        )
        
        # 转换为 mem0 格式
        return [
            {
                'id': r.id,
                'memory': r.content,
                'score': r.score,
                'user_id': effective_user_id,
                'metadata': r.metadata
            }
            for r in results
        ]
    
    def update(
        self,
        memory_id: str,
        data: str
    ) -> Dict[str, Any]:
        """更新记忆
        
        Args:
            memory_id: 记忆ID
            data: 新内容
        
        Returns:
            Dict: 更新结果
        """
        success = self._engine.update(memory_id, data)
        
        return {
            'id': memory_id,
            'memory': data if success else None,
            'event': 'UPDATE' if success else 'FAILED'
        }
    
    def delete(
        self,
        memory_id: str
    ) -> Dict[str, Any]:
        """删除记忆
        
        Args:
            memory_id: 记忆ID
        
        Returns:
            Dict: 删除结果
        """
        success = self._engine.delete(memory_id)
        
        return {
            'id': memory_id,
            'event': 'DELETE' if success else 'FAILED'
        }
    
    def delete_all(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """删除所有记忆
        
        Args:
            user_id: 用户ID
            agent_id: 代理ID
            run_id: 运行ID
        
        Returns:
            Dict: 删除结果
        """
        effective_user_id = user_id or agent_id
        
        self._engine.reset(user_id=effective_user_id)
        
        return {
            'message': 'All memories deleted successfully'
        }
    
    def history(
        self,
        memory_id: str
    ) -> List[Dict[str, Any]]:
        """获取记忆历史（Recall 暂不支持）
        
        Args:
            memory_id: 记忆ID
        
        Returns:
            List[Dict]: 历史记录
        """
        # Recall 暂不支持历史记录
        memory = self.get(memory_id)
        if memory:
            return [memory]
        return []
    
    def reset(self) -> Dict[str, Any]:
        """重置所有记忆
        
        Returns:
            Dict: 重置结果
        """
        self._engine.reset()
        return {'message': 'Memory reset successfully'}


class MemoryClient(Memory):
    """mem0 MemoryClient 兼容类
    
    与 Memory 类功能相同，提供给使用 MemoryClient 的代码。
    """
    pass


# 便捷函数
def from_mem0():
    """从 mem0 迁移的便捷函数
    
    返回一个与 mem0.Memory 兼容的 Memory 实例。
    """
    return Memory()
