"""预热管理器 - 管理模型预加载"""

import time
import threading
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum


class WarmupStatus(Enum):
    """预热状态"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WarmupTask:
    """预热任务"""
    name: str
    loader: Callable[[], Any]
    priority: int = 0
    status: WarmupStatus = WarmupStatus.NOT_STARTED
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def duration_ms(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None


class WarmupManager:
    """预热管理器
    
    管理模型和资源的延迟加载和预热：
    1. 懒加载 - 首次使用时加载
    2. 后台预热 - 空闲时预加载
    3. 优先级管理 - 按重要性排序
    """
    
    def __init__(self):
        self.tasks: Dict[str, WarmupTask] = {}
        self.loaded: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._warmup_thread: Optional[threading.Thread] = None
    
    def register(
        self,
        name: str,
        loader: Callable[[], Any],
        priority: int = 0
    ):
        """注册预热任务"""
        with self._lock:
            self.tasks[name] = WarmupTask(
                name=name,
                loader=loader,
                priority=priority
            )
    
    def get(self, name: str) -> Optional[Any]:
        """获取已加载的资源（懒加载）"""
        # 如果已加载，直接返回
        if name in self.loaded:
            return self.loaded[name]
        
        # 尝试立即加载
        if name in self.tasks:
            return self._load_now(name)
        
        return None
    
    def _load_now(self, name: str) -> Optional[Any]:
        """立即加载资源"""
        task = self.tasks.get(name)
        if not task:
            return None
        
        if task.status == WarmupStatus.COMPLETED:
            return task.result
        
        with self._lock:
            # 双重检查
            if name in self.loaded:
                return self.loaded[name]
            
            task.status = WarmupStatus.IN_PROGRESS
            task.start_time = time.time()
            
            try:
                result = task.loader()
                task.result = result
                task.status = WarmupStatus.COMPLETED
                task.end_time = time.time()
                self.loaded[name] = result
                return result
            
            except Exception as e:
                task.status = WarmupStatus.FAILED
                task.error = str(e)
                task.end_time = time.time()
                return None
    
    def warmup_async(self, names: Optional[List[str]] = None):
        """异步预热（后台线程）"""
        if self._warmup_thread and self._warmup_thread.is_alive():
            return  # 已有预热在进行
        
        self._warmup_thread = threading.Thread(
            target=self._warmup_worker,
            args=(names,),
            daemon=True
        )
        self._warmup_thread.start()
    
    def _warmup_worker(self, names: Optional[List[str]] = None):
        """预热工作线程"""
        # 获取要预热的任务
        if names:
            tasks_to_warm = [self.tasks[n] for n in names if n in self.tasks]
        else:
            tasks_to_warm = list(self.tasks.values())
        
        # 按优先级排序
        tasks_to_warm.sort(key=lambda t: -t.priority)
        
        for task in tasks_to_warm:
            if task.status == WarmupStatus.NOT_STARTED:
                self._load_now(task.name)
    
    def warmup_sync(self, names: Optional[List[str]] = None):
        """同步预热"""
        self._warmup_worker(names)
    
    def get_status(self) -> Dict[str, Any]:
        """获取预热状态"""
        return {
            'tasks': {
                name: {
                    'status': task.status.value,
                    'priority': task.priority,
                    'duration_ms': task.duration_ms,
                    'error': task.error
                }
                for name, task in self.tasks.items()
            },
            'loaded_count': len(self.loaded),
            'total_count': len(self.tasks)
        }
    
    def is_ready(self, name: str) -> bool:
        """检查资源是否已就绪"""
        return name in self.loaded
    
    def unload(self, name: str):
        """卸载资源"""
        with self._lock:
            if name in self.loaded:
                del self.loaded[name]
            if name in self.tasks:
                self.tasks[name].status = WarmupStatus.NOT_STARTED
                self.tasks[name].result = None
    
    def unload_all(self):
        """卸载所有资源"""
        with self._lock:
            self.loaded.clear()
            for task in self.tasks.values():
                task.status = WarmupStatus.NOT_STARTED
                task.result = None


# 全局预热管理器
_global_warmup_manager: Optional[WarmupManager] = None


def get_warmup_manager() -> WarmupManager:
    """获取全局预热管理器"""
    global _global_warmup_manager
    if _global_warmup_manager is None:
        _global_warmup_manager = WarmupManager()
    return _global_warmup_manager
