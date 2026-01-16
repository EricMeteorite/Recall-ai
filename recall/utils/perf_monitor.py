"""性能监控器 - 监控系统性能"""

import time
import threading
import psutil
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class MetricType(Enum):
    """指标类型"""
    LATENCY = "latency"           # 延迟（毫秒）
    THROUGHPUT = "throughput"     # 吞吐量
    MEMORY = "memory"             # 内存使用（MB）
    CPU = "cpu"                   # CPU使用率
    CACHE_HIT = "cache_hit"       # 缓存命中率
    ERROR_RATE = "error_rate"     # 错误率


@dataclass
class Metric:
    """指标数据"""
    type: MetricType
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class AggregatedMetric:
    """聚合指标"""
    type: MetricType
    count: int
    sum_value: float
    min_value: float
    max_value: float
    avg_value: float
    p50: float
    p95: float
    p99: float


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(
        self,
        window_size: int = 1000,
        auto_collect: bool = True,
        collect_interval: float = 5.0
    ):
        self.window_size = window_size
        self.auto_collect = auto_collect
        self.collect_interval = collect_interval
        
        # 指标存储
        self.metrics: Dict[MetricType, deque] = {
            t: deque(maxlen=window_size) for t in MetricType
        }
        
        # 锁
        self._lock = threading.Lock()
        
        # 自动收集线程
        self._collector_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        if auto_collect:
            self.start_collection()
    
    def record(self, metric_type: MetricType, value: float, tags: Optional[Dict[str, str]] = None):
        """记录指标"""
        metric = Metric(
            type=metric_type,
            value=value,
            tags=tags or {}
        )
        
        with self._lock:
            self.metrics[metric_type].append(metric)
    
    def timer(self, metric_type: MetricType = MetricType.LATENCY, tags: Optional[Dict[str, str]] = None):
        """计时器上下文管理器"""
        return _Timer(self, metric_type, tags)
    
    def get_stats(self, metric_type: MetricType) -> Optional[AggregatedMetric]:
        """获取指标统计"""
        with self._lock:
            metrics = list(self.metrics[metric_type])
        
        if not metrics:
            return None
        
        values = sorted([m.value for m in metrics])
        count = len(values)
        
        return AggregatedMetric(
            type=metric_type,
            count=count,
            sum_value=sum(values),
            min_value=min(values),
            max_value=max(values),
            avg_value=sum(values) / count,
            p50=values[int(count * 0.5)],
            p95=values[int(count * 0.95)] if count >= 20 else values[-1],
            p99=values[int(count * 0.99)] if count >= 100 else values[-1]
        )
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有指标统计"""
        stats = {}
        for metric_type in MetricType:
            stat = self.get_stats(metric_type)
            if stat:
                stats[metric_type.value] = {
                    'count': stat.count,
                    'avg': round(stat.avg_value, 2),
                    'min': round(stat.min_value, 2),
                    'max': round(stat.max_value, 2),
                    'p50': round(stat.p50, 2),
                    'p95': round(stat.p95, 2),
                    'p99': round(stat.p99, 2)
                }
        return stats
    
    def start_collection(self):
        """启动自动收集"""
        if self._collector_thread and self._collector_thread.is_alive():
            return
        
        self._stop_event.clear()
        self._collector_thread = threading.Thread(
            target=self._collect_loop,
            daemon=True
        )
        self._collector_thread.start()
    
    def stop_collection(self):
        """停止自动收集"""
        self._stop_event.set()
        if self._collector_thread:
            self._collector_thread.join(timeout=2.0)
    
    def _collect_loop(self):
        """收集循环"""
        while not self._stop_event.is_set():
            try:
                # 收集系统指标
                self._collect_system_metrics()
            except Exception:
                pass
            
            self._stop_event.wait(self.collect_interval)
    
    def _collect_system_metrics(self):
        """收集系统指标"""
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)
        self.record(MetricType.CPU, cpu_percent)
        
        # 内存使用
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.record(MetricType.MEMORY, memory_mb)
    
    def get_health(self) -> Dict[str, Any]:
        """获取健康状态"""
        stats = self.get_all_stats()
        
        # 判断健康状态
        issues = []
        
        if 'memory' in stats and stats['memory']['avg'] > 500:
            issues.append('内存使用较高')
        
        if 'cpu' in stats and stats['cpu']['avg'] > 80:
            issues.append('CPU使用率较高')
        
        if 'latency' in stats and stats['latency']['p95'] > 1000:
            issues.append('延迟较高')
        
        if 'error_rate' in stats and stats['error_rate']['avg'] > 0.01:
            issues.append('错误率较高')
        
        return {
            'healthy': len(issues) == 0,
            'issues': issues,
            'stats': stats
        }
    
    def reset(self):
        """重置所有指标"""
        with self._lock:
            for metric_type in MetricType:
                self.metrics[metric_type].clear()


class _Timer:
    """计时器上下文管理器"""
    
    def __init__(
        self,
        monitor: PerformanceMonitor,
        metric_type: MetricType,
        tags: Optional[Dict[str, str]]
    ):
        self.monitor = monitor
        self.metric_type = metric_type
        self.tags = tags
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            elapsed_ms = (time.time() - self.start_time) * 1000
            self.monitor.record(self.metric_type, elapsed_ms, self.tags)
        return False


# 全局监控器
_global_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """获取全局监控器"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor
