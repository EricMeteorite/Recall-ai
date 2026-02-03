"""后端任务追踪管理器

Recall 4.x: 提供统一的后端处理任务追踪机制
- 任务创建、更新、完成状态管理
- 支持通过 API 查询当前活动任务
- 可选 WebSocket 实时推送
- 线程安全设计，适用于多请求并发场景
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

__all__ = ['TaskManager', 'Task', 'TaskStatus', 'TaskType', 'get_task_manager']


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 取消


class TaskType(Enum):
    """任务类型"""
    # 记忆处理流程
    DEDUP_CHECK = "dedup_check"              # 去重检查
    ENTITY_EXTRACTION = "entity_extraction"  # 实体提取
    CONSISTENCY_CHECK = "consistency_check"  # 一致性检查
    CONTRADICTION_DETECTION = "contradiction_detection"  # 矛盾检测
    KNOWLEDGE_GRAPH = "knowledge_graph"      # 知识图谱更新
    INDEX_UPDATE = "index_update"            # 索引更新
    MEMORY_SAVE = "memory_save"              # 记忆保存
    
    # 伏笔分析
    FORESHADOW_ANALYSIS = "foreshadow_analysis"  # 伏笔分析
    CONTEXT_EXTRACTION = "context_extraction"    # 条件提取
    
    # LLM 调用
    LLM_CALL = "llm_call"        # LLM API 调用
    EMBEDDING = "embedding"      # 向量化
    
    # 通用
    SEARCH = "search"            # 搜索
    MAINTENANCE = "maintenance"  # 维护任务
    OTHER = "other"              # 其他


@dataclass
class Task:
    """任务数据结构"""
    id: str
    task_type: TaskType
    name: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 ~ 1.0
    message: str = ""
    user_id: str = "default"
    character_id: str = "default"
    parent_task_id: Optional[str] = None  # 父任务ID（用于嵌套任务）
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（API 响应用）"""
        return {
            'id': self.id,
            'type': self.task_type.value,
            'name': self.name,
            'status': self.status.value,
            'progress': self.progress,
            'message': self.message,
            'user_id': self.user_id,
            'character_id': self.character_id,
            'parent_task_id': self.parent_task_id,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'elapsed_ms': self._elapsed_ms(),
            'error': self.error,
            'metadata': self.metadata
        }
    
    def _elapsed_ms(self) -> Optional[float]:
        """计算已用时间（毫秒）"""
        if self.started_at is None:
            return None
        end_time = self.completed_at or time.time()
        return (end_time - self.started_at) * 1000


class TaskManager:
    """后端任务追踪管理器（单例模式）"""
    
    _instance: Optional['TaskManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'TaskManager':
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._tasks: Dict[str, Task] = {}  # 所有任务
        self._active_tasks: Dict[str, Task] = {}  # 活动任务（未完成）
        self._task_lock = threading.Lock()
        self._subscribers: List[Callable[[Task, str], None]] = []  # 订阅者列表
        self._max_completed_tasks = 100  # 保留的已完成任务数量
        self._completed_tasks: List[Task] = []  # 最近完成的任务
        self._enabled = True  # 是否启用任务追踪
        self._initialized = True
    
    def set_enabled(self, enabled: bool):
        """启用或禁用任务追踪"""
        self._enabled = enabled
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enabled
    
    def create_task(
        self,
        task_type: TaskType,
        name: str,
        user_id: str = "default",
        character_id: str = "default",
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Task:
        """创建新任务
        
        Args:
            task_type: 任务类型
            name: 任务名称（显示用）
            user_id: 用户ID
            character_id: 角色ID
            parent_task_id: 父任务ID
            metadata: 附加元数据
        
        Returns:
            Task: 创建的任务对象
        """
        if not self._enabled:
            # 禁用时返回一个空任务，但不追踪
            return Task(
                id=f"noop_{uuid.uuid4().hex[:8]}",
                task_type=task_type,
                name=name,
                user_id=user_id,
                character_id=character_id
            )
        
        task = Task(
            id=f"task_{uuid.uuid4().hex[:12]}",
            task_type=task_type,
            name=name,
            user_id=user_id,
            character_id=character_id,
            parent_task_id=parent_task_id,
            metadata=metadata or {}
        )
        
        with self._task_lock:
            self._tasks[task.id] = task
            self._active_tasks[task.id] = task
        
        self._notify_subscribers(task, 'created')
        return task
    
    def start_task(self, task_id: str, message: str = "") -> Optional[Task]:
        """开始执行任务
        
        Args:
            task_id: 任务ID
            message: 状态消息
        
        Returns:
            Task: 更新后的任务，如果任务不存在返回 None
        """
        if not self._enabled:
            return None
        
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                task.message = message or f"正在执行: {task.name}"
        
        if task:
            self._notify_subscribers(task, 'started')
        return task
    
    def update_task(
        self,
        task_id: str,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Task]:
        """更新任务进度
        
        Args:
            task_id: 任务ID
            progress: 进度 (0.0 ~ 1.0)
            message: 状态消息
            metadata: 更新的元数据
        
        Returns:
            Task: 更新后的任务
        """
        if not self._enabled:
            return None
        
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                if progress is not None:
                    task.progress = min(1.0, max(0.0, progress))
                if message is not None:
                    task.message = message
                if metadata:
                    task.metadata.update(metadata)
        
        if task:
            self._notify_subscribers(task, 'updated')
        return task
    
    def complete_task(
        self,
        task_id: str,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Task]:
        """完成任务
        
        Args:
            task_id: 任务ID
            message: 完成消息
            metadata: 最终元数据
        
        Returns:
            Task: 完成的任务
        """
        if not self._enabled:
            return None
        
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.progress = 1.0
                task.completed_at = time.time()
                task.message = message or f"完成: {task.name}"
                if metadata:
                    task.metadata.update(metadata)
                
                # 从活动任务移除
                self._active_tasks.pop(task_id, None)
                
                # 添加到已完成列表
                self._completed_tasks.append(task)
                if len(self._completed_tasks) > self._max_completed_tasks:
                    self._completed_tasks.pop(0)
        
        if task:
            self._notify_subscribers(task, 'completed')
        return task
    
    def fail_task(
        self,
        task_id: str,
        error: str,
        message: str = ""
    ) -> Optional[Task]:
        """标记任务失败
        
        Args:
            task_id: 任务ID
            error: 错误信息
            message: 状态消息
        
        Returns:
            Task: 失败的任务
        """
        if not self._enabled:
            return None
        
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                task.error = error
                task.message = message or f"失败: {error}"
                
                # 从活动任务移除
                self._active_tasks.pop(task_id, None)
                
                # 添加到已完成列表
                self._completed_tasks.append(task)
                if len(self._completed_tasks) > self._max_completed_tasks:
                    self._completed_tasks.pop(0)
        
        if task:
            self._notify_subscribers(task, 'failed')
        return task
    
    def cancel_task(self, task_id: str, message: str = "") -> Optional[Task]:
        """取消任务
        
        Args:
            task_id: 任务ID
            message: 取消原因
        
        Returns:
            Task: 取消的任务
        """
        if not self._enabled:
            return None
        
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED
                task.completed_at = time.time()
                task.message = message or "任务已取消"
                
                # 从活动任务移除
                self._active_tasks.pop(task_id, None)
        
        if task:
            self._notify_subscribers(task, 'cancelled')
        return task
    
    def get_active_tasks(
        self,
        user_id: Optional[str] = None,
        character_id: Optional[str] = None,
        task_type: Optional[TaskType] = None
    ) -> List[Task]:
        """获取活动任务列表
        
        Args:
            user_id: 可选，按用户过滤
            character_id: 可选，按角色过滤
            task_type: 可选，按任务类型过滤
        
        Returns:
            List[Task]: 活动任务列表
        """
        with self._task_lock:
            tasks = list(self._active_tasks.values())
        
        # 应用过滤器
        if user_id:
            tasks = [t for t in tasks if t.user_id == user_id]
        if character_id:
            tasks = [t for t in tasks if t.character_id == character_id]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        
        # 按创建时间排序（最新的在前）
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks
    
    def get_recent_tasks(
        self,
        limit: int = 20,
        include_active: bool = True,
        include_completed: bool = True
    ) -> List[Task]:
        """获取最近的任务
        
        Args:
            limit: 返回数量限制
            include_active: 是否包含活动任务
            include_completed: 是否包含已完成任务
        
        Returns:
            List[Task]: 任务列表
        """
        tasks = []
        
        with self._task_lock:
            if include_active:
                tasks.extend(self._active_tasks.values())
            if include_completed:
                tasks.extend(self._completed_tasks)
        
        # 按创建时间排序（最新的在前）
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取指定任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            Task: 任务对象，不存在返回 None
        """
        with self._task_lock:
            return self._tasks.get(task_id)
    
    def subscribe(self, callback: Callable[[Task, str], None]):
        """订阅任务变更通知
        
        Args:
            callback: 回调函数 (task, event_type) -> None
                     event_type: 'created', 'started', 'updated', 'completed', 'failed', 'cancelled'
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[Task, str], None]):
        """取消订阅"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    def _notify_subscribers(self, task: Task, event_type: str):
        """通知所有订阅者"""
        for callback in self._subscribers:
            try:
                callback(task, event_type)
            except Exception as e:
                # 不让订阅者异常影响主流程
                pass
    
    def clear_completed_tasks(self):
        """清除已完成任务记录"""
        with self._task_lock:
            self._completed_tasks.clear()
            # 从主字典中移除已完成的任务
            completed_ids = [
                tid for tid, task in self._tasks.items()
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            ]
            for tid in completed_ids:
                del self._tasks[tid]


# 全局单例获取函数
def get_task_manager() -> TaskManager:
    """获取全局任务管理器实例"""
    return TaskManager()


class TaskContext:
    """任务上下文管理器，支持 with 语句自动管理任务生命周期
    
    用法:
        with TaskContext(TaskType.ENTITY_EXTRACTION, "提取实体", user_id) as task:
            # 执行任务
            task.update(progress=0.5, message="处理中...")
        # 自动完成或失败
    """
    
    def __init__(
        self,
        task_type: TaskType,
        name: str,
        user_id: str = "default",
        character_id: str = "default",
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.task_type = task_type
        self.name = name
        self.user_id = user_id
        self.character_id = character_id
        self.parent_task_id = parent_task_id
        self.metadata = metadata
        self._task: Optional[Task] = None
        self._manager = get_task_manager()
    
    def __enter__(self) -> 'TaskContext':
        self._task = self._manager.create_task(
            task_type=self.task_type,
            name=self.name,
            user_id=self.user_id,
            character_id=self.character_id,
            parent_task_id=self.parent_task_id,
            metadata=self.metadata
        )
        self._manager.start_task(self._task.id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._task is None:
            return False
        
        if exc_type is not None:
            # 有异常发生，标记任务失败
            self._manager.fail_task(
                self._task.id,
                error=str(exc_val),
                message=f"执行失败: {exc_type.__name__}"
            )
        else:
            # 正常完成
            self._manager.complete_task(self._task.id)
        
        return False  # 不抑制异常
    
    @property
    def task_id(self) -> Optional[str]:
        """获取任务ID"""
        return self._task.id if self._task else None
    
    def update(
        self,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """更新任务状态"""
        if self._task:
            self._manager.update_task(
                self._task.id,
                progress=progress,
                message=message,
                metadata=metadata
            )
    
    def fail(self, error: str, message: str = ""):
        """手动标记任务失败"""
        if self._task:
            self._manager.fail_task(self._task.id, error=error, message=message)
    
    def complete(self, message: str = "", metadata: Optional[Dict[str, Any]] = None):
        """手动标记任务完成"""
        if self._task:
            self._manager.complete_task(self._task.id, message=message, metadata=metadata)
