"""轻量级 Prometheus 指标收集器

不依赖 prometheus_client，自行实现计数器/直方图/仪表盘。
支持 Prometheus 文本暴露格式 和 JSON 格式。
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from typing import Dict, Any, Optional, List


class _Counter:
    """线程安全计数器"""

    def __init__(self, name: str, help_text: str):
        self.name = name
        self.help = help_text
        self._value: float = 0.0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        return self._value

    def prometheus_lines(self) -> List[str]:
        return [
            f"# HELP {self.name} {self.help}",
            f"# TYPE {self.name} counter",
            f"{self.name} {self._value}",
        ]


class _Gauge:
    """线程安全仪表盘"""

    def __init__(self, name: str, help_text: str):
        self.name = name
        self.help = help_text
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        return self._value

    def prometheus_lines(self) -> List[str]:
        return [
            f"# HELP {self.name} {self.help}",
            f"# TYPE {self.name} gauge",
            f"{self.name} {self._value}",
        ]


class _Histogram:
    """简化版直方图 — 只跟踪 count / sum / buckets"""

    DEFAULT_BUCKETS = (10, 25, 50, 100, 200, 500, 1000, 2500, 5000, 10000, float('inf'))

    def __init__(self, name: str, help_text: str, buckets: Optional[tuple] = None):
        self.name = name
        self.help = help_text
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._lock = threading.Lock()
        self._sum: float = 0.0
        self._count: int = 0
        self._bucket_counts: Dict[float, int] = {b: 0 for b in self.buckets}

    def observe(self, value: float) -> None:
        with self._lock:
            self._sum += value
            self._count += 1
            for b in self.buckets:
                if value <= b:
                    self._bucket_counts[b] += 1

    @property
    def count(self) -> int:
        return self._count

    @property
    def avg(self) -> float:
        return self._sum / self._count if self._count else 0.0

    def prometheus_lines(self) -> List[str]:
        lines = [
            f"# HELP {self.name} {self.help}",
            f"# TYPE {self.name} histogram",
        ]
        for b, cnt in self._bucket_counts.items():
            le = "+Inf" if b == float('inf') else str(b)
            lines.append(f'{self.name}_bucket{{le="{le}"}} {cnt}')
        lines.append(f"{self.name}_sum {self._sum}")
        lines.append(f"{self.name}_count {self._count}")
        return lines


# ==================== 全局指标收集器 ====================

class MetricsCollector:
    """Recall 全局指标收集器"""

    def __init__(self):
        self._start_time = time.time()

        # 计数器
        self.request_count = _Counter(
            "recall_request_total",
            "Total number of HTTP requests",
        )
        self.error_count = _Counter(
            "recall_error_total",
            "Total number of errors",
        )
        self.memory_add_count = _Counter(
            "recall_memory_add_total",
            "Total memories added",
        )
        self.memory_search_count = _Counter(
            "recall_memory_search_total",
            "Total memory searches",
        )
        self.cache_hit_count = _Counter(
            "recall_cache_hit_total",
            "Total cache hits",
        )
        self.cache_miss_count = _Counter(
            "recall_cache_miss_total",
            "Total cache misses",
        )

        # 仪表盘
        self.memory_count = _Gauge(
            "recall_memory_count",
            "Current number of memories",
        )
        self.active_connections = _Gauge(
            "recall_active_connections",
            "Current active HTTP connections",
        )

        # 直方图
        self.request_latency = _Histogram(
            "recall_request_latency_ms",
            "Request latency in milliseconds",
        )
        self.search_latency = _Histogram(
            "recall_search_latency_ms",
            "Search latency in milliseconds",
        )
        self.add_latency = _Histogram(
            "recall_add_latency_ms",
            "Memory add latency in milliseconds",
        )

    # ---- 便捷方法 ----

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        """记录一次 HTTP 请求"""
        self.request_count.inc()
        self.request_latency.observe(duration_ms)
        if status_code >= 400:
            self.error_count.inc()

    def record_search(self, duration_ms: float) -> None:
        self.memory_search_count.inc()
        self.search_latency.observe(duration_ms)

    def record_add(self, duration_ms: float) -> None:
        self.memory_add_count.inc()
        self.add_latency.observe(duration_ms)

    def record_cache_hit(self) -> None:
        self.cache_hit_count.inc()

    def record_cache_miss(self) -> None:
        self.cache_miss_count.inc()

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hit_count.value + self.cache_miss_count.value
        if total == 0:
            return 0.0
        return self.cache_hit_count.value / total

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    # ---- 导出 ----

    def to_prometheus(self) -> str:
        """导出 Prometheus 文本暴露格式"""
        all_metrics = [
            self.request_count, self.error_count,
            self.memory_add_count, self.memory_search_count,
            self.cache_hit_count, self.cache_miss_count,
            self.memory_count, self.active_connections,
            self.request_latency, self.search_latency, self.add_latency,
        ]
        lines: List[str] = []
        for m in all_metrics:
            lines.extend(m.prometheus_lines())
            lines.append("")

        # 附加 uptime gauge
        lines.extend([
            "# HELP recall_uptime_seconds Uptime in seconds",
            "# TYPE recall_uptime_seconds gauge",
            f"recall_uptime_seconds {self.uptime_seconds:.1f}",
            "",
            "# HELP recall_cache_hit_rate Cache hit rate 0-1",
            "# TYPE recall_cache_hit_rate gauge",
            f"recall_cache_hit_rate {self.cache_hit_rate:.4f}",
            "",
        ])
        return "\n".join(lines)

    def to_json(self) -> Dict[str, Any]:
        """导出 JSON 格式指标"""
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "request_count": self.request_count.value,
            "error_count": self.error_count.value,
            "memory_add_count": self.memory_add_count.value,
            "memory_search_count": self.memory_search_count.value,
            "cache_hit_count": self.cache_hit_count.value,
            "cache_miss_count": self.cache_miss_count.value,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "memory_count": self.memory_count.value,
            "active_connections": self.active_connections.value,
            "request_latency_avg_ms": round(self.request_latency.avg, 2),
            "request_latency_count": self.request_latency.count,
            "search_latency_avg_ms": round(self.search_latency.avg, 2),
            "search_latency_count": self.search_latency.count,
            "add_latency_avg_ms": round(self.add_latency.avg, 2),
            "add_latency_count": self.add_latency.count,
        }


# ==================== 单例 ====================

_metrics: Optional[MetricsCollector] = None
_metrics_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    """获取全局指标收集器实例（惰性单例）"""
    global _metrics
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                _metrics = MetricsCollector()
    return _metrics
