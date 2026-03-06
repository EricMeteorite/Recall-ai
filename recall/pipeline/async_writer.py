"""
Recall v7.0 - Async Write Pipeline
Non-blocking write queue for memory storage operations.
Prevents bulk imports from blocking search requests.
"""
from __future__ import annotations

import asyncio
import enum
import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine import RecallEngine


# Windows GBK safe print
def _safe_print(msg: str) -> None:
    _map = {
        '📥': '[IN]', '📤': '[OUT]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '🔄': '[SYNC]', '🚀': '[START]', '⚡': '[FAST]',
    }
    for k, v in _map.items():
        msg = msg.replace(k, v)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class OperationType(str, enum.Enum):
    ADD = "add"
    ADD_BATCH = "add_batch"
    DELETE = "delete"
    UPDATE = "update"


@dataclass
class WriteOperation:
    """A single queued write operation."""
    op_type: OperationType
    payload: Dict[str, Any]
    op_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    retries: int = 0


@dataclass
class PipelineStatus:
    """Snapshot of pipeline health metrics."""
    queue_depth: int = 0
    queue_capacity: int = 0
    utilization_pct: float = 0.0
    total_enqueued: int = 0
    total_processed: int = 0
    total_errors: int = 0
    processing_rate_qps: float = 0.0
    is_running: bool = False
    workers: int = 0
    rate_limit_qps: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class AsyncWritePipeline:
    """Async queue that decouples write operations from request handlers.

    * ``enqueue()`` is safe to call from **both** sync and async code.
    * Background workers drain the queue and call the engine.
    * When the queue exceeds 80 % capacity, ``is_overloaded`` returns *True*
      so the server middleware can respond with *429 Retry-After*.
    """

    OVERFLOW_THRESHOLD = 0.80  # 80 % → signal back-pressure

    def __init__(
        self,
        engine: 'RecallEngine',
        max_size: int = 10_000,
        rate_limit_qps: float = 0.0,  # 0 = unlimited
        num_workers: int = 2,
    ):
        self._engine = engine
        self._max_size = max_size
        self._rate_limit_qps = rate_limit_qps
        self._num_workers = num_workers

        self._queue: asyncio.Queue[Optional[WriteOperation]] = asyncio.Queue(maxsize=max_size)
        self._running = False
        self._workers: List[asyncio.Task] = []

        # Metrics (thread-safe via atomics / GIL)
        self._total_enqueued = 0
        self._total_processed = 0
        self._total_errors = 0
        self._rate_window_start = time.monotonic()
        self._rate_window_count = 0
        self._current_qps: float = 0.0
        self._lock = threading.Lock()  # protects metric snapshots

        # For cross-thread enqueue
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start background workers.  Call once after the event loop is running."""
        if self._running:
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        for i in range(self._num_workers):
            task = asyncio.create_task(self._worker(i), name=f"pipeline-worker-{i}")
            self._workers.append(task)
        _safe_print(f"[Pipeline] [START] Async write pipeline started ({self._num_workers} workers, capacity={self._max_size})")

    async def stop(self, timeout: float = 30.0) -> None:
        """Gracefully drain the queue then cancel workers."""
        if not self._running:
            return
        self._running = False

        # Enqueue sentinel values so workers unblock
        for _ in self._workers:
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

        # Wait for workers to finish (with timeout)
        done, pending = await asyncio.wait(self._workers, timeout=timeout)
        for t in pending:
            t.cancel()
        self._workers.clear()
        _safe_print(f"[Pipeline] Pipeline stopped. Processed={self._total_processed}, Errors={self._total_errors}")

    # ------------------------------------------------------------------
    # Enqueue (thread-safe)
    # ------------------------------------------------------------------

    def enqueue(self, operation: WriteOperation) -> bool:
        """Add *operation* to the queue.

        Returns ``False`` if the queue is full (caller should retry later).
        This method is **thread-safe** and can be called from synchronous code.
        """
        if not self._running:
            return False

        # Fast-path: if we are already in the event-loop thread
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is self._loop:
            # Already on the event loop — non-blocking put
            try:
                self._queue.put_nowait(operation)
                with self._lock:
                    self._total_enqueued += 1
                return True
            except asyncio.QueueFull:
                return False
        else:
            # Called from a sync / different thread
            if self._loop is None:
                return False
            future = asyncio.run_coroutine_threadsafe(
                self._async_enqueue(operation), self._loop
            )
            try:
                return future.result(timeout=2.0)
            except Exception:
                return False

    async def _async_enqueue(self, operation: WriteOperation) -> bool:
        try:
            self._queue.put_nowait(operation)
            with self._lock:
                self._total_enqueued += 1
            return True
        except asyncio.QueueFull:
            return False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_overloaded(self) -> bool:
        """Return ``True`` when the queue exceeds the overflow threshold."""
        return self._queue.qsize() > int(self._max_size * self.OVERFLOW_THRESHOLD)

    @property
    def retry_after(self) -> int:
        """Suggested Retry-After seconds when overloaded."""
        utilization = self._queue.qsize() / max(self._max_size, 1)
        if utilization > 0.95:
            return 30
        if utilization > 0.90:
            return 15
        return 5

    def status(self) -> PipelineStatus:
        """Return a snapshot of current pipeline metrics."""
        now = time.monotonic()
        with self._lock:
            elapsed = now - self._rate_window_start
            if elapsed >= 1.0:
                self._current_qps = self._rate_window_count / elapsed
                self._rate_window_start = now
                self._rate_window_count = 0

        depth = self._queue.qsize()
        return PipelineStatus(
            queue_depth=depth,
            queue_capacity=self._max_size,
            utilization_pct=round(depth / max(self._max_size, 1) * 100, 2),
            total_enqueued=self._total_enqueued,
            total_processed=self._total_processed,
            total_errors=self._total_errors,
            processing_rate_qps=round(self._current_qps, 2),
            is_running=self._running,
            workers=self._num_workers,
            rate_limit_qps=self._rate_limit_qps,
        )

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    async def _worker(self, worker_id: int) -> None:
        """Background task that drains the queue."""
        min_interval = 1.0 / self._rate_limit_qps if self._rate_limit_qps > 0 else 0.0

        while True:
            op = await self._queue.get()
            if op is None:
                # Sentinel → shutdown
                self._queue.task_done()
                break

            try:
                if min_interval > 0:
                    await asyncio.sleep(min_interval)

                await self._execute(op)
                with self._lock:
                    self._total_processed += 1
                    self._rate_window_count += 1
            except Exception as exc:
                with self._lock:
                    self._total_errors += 1
                _safe_print(f"[Pipeline] [FAIL] Worker-{worker_id} op={op.op_id} type={op.op_type}: {exc}")
            finally:
                self._queue.task_done()

    async def _execute(self, op: WriteOperation) -> None:
        """Dispatch *op* to the engine (run in thread to avoid blocking)."""
        loop = asyncio.get_running_loop()
        engine = self._engine

        if op.op_type == OperationType.ADD:
            await loop.run_in_executor(
                None,
                lambda: engine.add(
                    op.payload["content"],
                    user_id=op.payload.get("user_id", "default"),
                    metadata=op.payload.get("metadata"),
                ),
            )
        elif op.op_type == OperationType.ADD_BATCH:
            items = op.payload.get("items", [])
            for item in items:
                await loop.run_in_executor(
                    None,
                    lambda i=item: engine.add(
                        i["content"],
                        user_id=i.get("user_id", "default"),
                        metadata=i.get("metadata"),
                    ),
                )
        elif op.op_type == OperationType.DELETE:
            await loop.run_in_executor(
                None,
                lambda: engine.delete(
                    op.payload["memory_id"],
                    user_id=op.payload.get("user_id", "default"),
                ),
            )
        elif op.op_type == OperationType.UPDATE:
            await loop.run_in_executor(
                None,
                lambda: engine.update(
                    op.payload["memory_id"],
                    content=op.payload.get("content", ""),
                    user_id=op.payload.get("user_id", "default"),
                    metadata=op.payload.get("metadata"),
                ),
            )
        else:
            raise ValueError(f"Unknown operation type: {op.op_type}")
