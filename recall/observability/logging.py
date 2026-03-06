"""结构化日志模块

功能:
- JSON 格式输出 (可选)
- 请求级别 trace_id 上下文
- 慢查询自动检测 (>200ms 告警)
- 线程安全的上下文管理
- 按天轮转日志文件 (v7.5)
"""

from __future__ import annotations

import logging
import logging.handlers
import json
import os
import re
import sys
import time
import uuid
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any


# ==================== 请求上下文 (thread-local) ====================

class RequestContext:
    """线程级请求上下文，携带 trace_id 等信息"""

    _local = threading.local()

    @classmethod
    def set(cls, trace_id: str, **extra: Any) -> None:
        cls._local.trace_id = trace_id
        cls._local.extra = extra
        cls._local.start_time = time.monotonic()

    @classmethod
    def get_trace_id(cls) -> str:
        return getattr(cls._local, 'trace_id', '-')

    @classmethod
    def get_extra(cls) -> Dict[str, Any]:
        return getattr(cls._local, 'extra', {})

    @classmethod
    def get_start_time(cls) -> float:
        return getattr(cls._local, 'start_time', 0.0)

    @classmethod
    def clear(cls) -> None:
        cls._local.trace_id = '-'
        cls._local.extra = {}
        cls._local.start_time = 0.0

    @classmethod
    def elapsed_ms(cls) -> float:
        st = cls.get_start_time()
        if st <= 0:
            return 0.0
        return (time.monotonic() - st) * 1000


# ==================== JSON Formatter ====================

class JSONFormatter(logging.Formatter):
    """将日志记录格式化为 JSON 行"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": RequestContext.get_trace_id(),
        }
        # 附加 extra 字段
        ctx_extra = RequestContext.get_extra()
        if ctx_extra:
            log_entry["ctx"] = ctx_extra

        # 异常信息
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # 自定义 extra 属性
        for key in ("duration_ms", "status_code", "method", "path", "user_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, ensure_ascii=False)


class ReadableFormatter(logging.Formatter):
    """人类可读格式 (带 trace_id)"""

    FMT = "%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s - %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        record.trace_id = RequestContext.get_trace_id()  # type: ignore[attr-defined]
        self._fmt = self.FMT
        self.datefmt = "%Y-%m-%d %H:%M:%S"
        return super().format(record)


# ==================== 慢查询过滤器 ====================

SLOW_QUERY_THRESHOLD_MS = 200.0


class SlowQueryFilter(logging.Filter):
    """给慢查询日志自动添加 [SLOW] 标记"""

    def filter(self, record: logging.LogRecord) -> bool:
        duration = getattr(record, 'duration_ms', None)
        if duration is not None and duration > SLOW_QUERY_THRESHOLD_MS:
            record.msg = f"[SLOW {duration:.0f}ms] {record.msg}"
        return True


# ==================== stdout/stderr 日志捕获 ====================

class _TeeStream:
    """将 print() 输出同时写入控制台和日志文件"""

    def __init__(self, original_stream, file_handler: logging.FileHandler):
        self._original = original_stream
        self._file_handler = file_handler

    def write(self, msg: str) -> int:
        # 写入原始控制台
        if self._original and not self._original.closed:
            try:
                self._original.write(msg)
            except Exception:
                pass
        # 写入日志文件（跳过空行）
        if msg and msg.strip():
            try:
                stream = self._file_handler.stream
                if stream and not stream.closed:
                    stream.write(msg if msg.endswith('\n') else msg + '\n')
                    stream.flush()
            except Exception:
                pass
        return len(msg) if msg else 0

    def flush(self) -> None:
        if self._original and not self._original.closed:
            try:
                self._original.flush()
            except Exception:
                pass
        try:
            self._file_handler.stream.flush()
        except Exception:
            pass

    def fileno(self):
        if self._original and not self._original.closed:
            return self._original.fileno()
        raise OSError("stream has no fileno")

    @property
    def encoding(self):
        return getattr(self._original, 'encoding', 'utf-8')

    def isatty(self) -> bool:
        return False

    @property
    def closed(self) -> bool:
        return False


# ==================== 公共 API ====================

_initialized = False


def _daily_namer(default_name: str) -> str:
    """将轮转文件命名为 recall-YYYY-MM-DD.log 格式"""
    # default_name 形如 /path/to/recall.log.2026-03-01
    # 提取日期后缀
    match = re.search(r'\.(\d{4}-\d{2}-\d{2})$', default_name)
    if match:
        date_str = match.group(1)
        base_dir = os.path.dirname(default_name)
        return os.path.join(base_dir, f"recall-{date_str}.log")
    return default_name


def _daily_rotator(source: str, dest: str) -> None:
    """自定义轮转器：重命名文件"""
    if os.path.exists(source):
        # 如果目标已存在（不应该发生），追加而非覆盖
        if os.path.exists(dest):
            with open(dest, 'a', encoding='utf-8') as dst_f:
                with open(source, 'r', encoding='utf-8') as src_f:
                    dst_f.write(src_f.read())
            os.remove(source)
        else:
            os.rename(source, dest)


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """初始化结构化日志系统

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        json_output: 是否输出 JSON 格式
        log_file: 日志文件路径（可选）。传入路径后自动启用按天轮转，
                  每天生成 recall-YYYY-MM-DD.log，永不删除旧日志。
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 选择 formatter
    formatter: logging.Formatter
    if json_output:
        formatter = JSONFormatter()
    else:
        formatter = ReadableFormatter()

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SlowQueryFilter())
    root.addHandler(console_handler)

    # 文件 handler — 按天轮转 (v7.5)
    if log_file:
        os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=0,       # 0 = 永不删除旧日志
            encoding='utf-8',
            utc=False,           # 使用本地时区的午夜
        )
        file_handler.suffix = "%Y-%m-%d"           # 轮转后缀
        file_handler.namer = _daily_namer           # recall-2026-03-01.log
        file_handler.rotator = _daily_rotator       # 自定义重命名
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SlowQueryFilter())
        root.addHandler(file_handler)

        # 捕获 _safe_print() 的 print() 输出也写入日志文件
        sys.stdout = _TeeStream(sys.stdout, file_handler)  # type: ignore[assignment]
        sys.stderr = _TeeStream(sys.stderr, file_handler)  # type: ignore[assignment]

    # 降低第三方库日志级别
    for noisy in ("httpcore", "httpx", "uvicorn.access", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger"""
    return logging.getLogger(name)


def log_slow_query(logger: logging.Logger, operation: str, duration_ms: float, **extra: Any) -> None:
    """记录慢查询（>200ms 自动 warning）"""
    if duration_ms > SLOW_QUERY_THRESHOLD_MS:
        logger.warning(
            "慢查询: %s 耗时 %.0fms",
            operation, duration_ms,
            extra={"duration_ms": duration_ms, **extra},
        )
