"""自动维护器 - 自动执行后台维护任务"""

import time
import threading
import schedule
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum


class MaintenanceType(Enum):
    """维护类型"""
    CONSOLIDATE = "consolidate"     # 记忆整合
    CLEANUP = "cleanup"             # 清理过期数据
    OPTIMIZE = "optimize"           # 索引优化
    BACKUP = "backup"               # 数据备份
    HEALTH_CHECK = "health_check"   # 健康检查


@dataclass
class MaintenanceTask:
    """维护任务"""
    name: str
    type: MaintenanceType
    handler: Callable[[], None]
    interval_hours: float
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    enabled: bool = True


class AutoMaintainer:
    """自动维护器
    
    后台运行，执行：
    1. 定期记忆整合（L2 -> L1）
    2. 清理过期缓存和临时文件
    3. 优化索引
    4. 健康检查
    """
    
    def __init__(self):
        self.tasks: Dict[str, MaintenanceTask] = {}
        self._lock = threading.Lock()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
    
    def register(
        self,
        name: str,
        task_type: MaintenanceType,
        handler: Callable[[], None],
        interval_hours: float = 24.0
    ):
        """注册维护任务"""
        task = MaintenanceTask(
            name=name,
            type=task_type,
            handler=handler,
            interval_hours=interval_hours,
            next_run=time.time() + interval_hours * 3600
        )
        
        with self._lock:
            self.tasks[name] = task
    
    def start(self):
        """启动维护调度器"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True
        )
        self._scheduler_thread.start()
        
        print("[Recall] 自动维护器已启动")
    
    def stop(self):
        """停止维护调度器"""
        self._stop_event.set()
        self._running = False
        
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)
        
        print("[Recall] 自动维护器已停止")
    
    def _scheduler_loop(self):
        """调度循环"""
        while not self._stop_event.is_set():
            current_time = time.time()
            
            with self._lock:
                tasks_to_run = [
                    task for task in self.tasks.values()
                    if task.enabled and task.next_run and task.next_run <= current_time
                ]
            
            for task in tasks_to_run:
                try:
                    print(f"[Recall] 执行维护任务: {task.name}")
                    task.handler()
                    task.last_run = time.time()
                    task.next_run = task.last_run + task.interval_hours * 3600
                except Exception as e:
                    print(f"[Recall] 维护任务失败 {task.name}: {e}")
            
            # 每分钟检查一次
            self._stop_event.wait(60)
    
    def run_now(self, name: str) -> bool:
        """立即执行某个任务"""
        if name not in self.tasks:
            return False
        
        task = self.tasks[name]
        try:
            print(f"[Recall] 手动执行维护任务: {task.name}")
            task.handler()
            task.last_run = time.time()
            task.next_run = task.last_run + task.interval_hours * 3600
            return True
        except Exception as e:
            print(f"[Recall] 维护任务失败 {task.name}: {e}")
            return False
    
    def enable(self, name: str):
        """启用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = True
    
    def disable(self, name: str):
        """禁用任务"""
        if name in self.tasks:
            self.tasks[name].enabled = False
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        current_time = time.time()
        
        tasks_status = []
        for task in self.tasks.values():
            time_until_next = None
            if task.next_run:
                time_until_next = max(0, task.next_run - current_time)
            
            tasks_status.append({
                'name': task.name,
                'type': task.type.value,
                'enabled': task.enabled,
                'interval_hours': task.interval_hours,
                'last_run': task.last_run,
                'next_run': task.next_run,
                'time_until_next_minutes': time_until_next / 60 if time_until_next else None
            })
        
        return {
            'running': self._running,
            'tasks': tasks_status
        }


def create_default_maintainer(
    storage=None,
    env_manager=None,
    index_manager=None
) -> AutoMaintainer:
    """创建带默认任务的维护器"""
    maintainer = AutoMaintainer()
    
    # 记忆整合任务
    if storage:
        def consolidate_task():
            if hasattr(storage, 'consolidate'):
                storage.consolidate()
        
        maintainer.register(
            'memory_consolidate',
            MaintenanceType.CONSOLIDATE,
            consolidate_task,
            interval_hours=6.0
        )
    
    # 清理任务
    if env_manager:
        def cleanup_task():
            if hasattr(env_manager, 'cleanup_cache'):
                env_manager.cleanup_cache(older_than_days=7)
            if hasattr(env_manager, 'cleanup_temp'):
                env_manager.cleanup_temp()
        
        maintainer.register(
            'cleanup',
            MaintenanceType.CLEANUP,
            cleanup_task,
            interval_hours=24.0
        )
    
    # 索引优化任务
    if index_manager:
        def optimize_task():
            if hasattr(index_manager, 'optimize'):
                index_manager.optimize()
        
        maintainer.register(
            'index_optimize',
            MaintenanceType.OPTIMIZE,
            optimize_task,
            interval_hours=12.0
        )
    
    # 健康检查任务
    def health_check_task():
        from .perf_monitor import get_monitor
        monitor = get_monitor()
        health = monitor.get_health()
        if not health['healthy']:
            print(f"[Recall] 健康检查警告: {health['issues']}")
    
    maintainer.register(
        'health_check',
        MaintenanceType.HEALTH_CHECK,
        health_check_task,
        interval_hours=1.0
    )
    
    return maintainer
