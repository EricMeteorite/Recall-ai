"""异步导入任务管理器

功能:
- POST /v1/jobs/import → 提交导入任务，返回 job_id
- GET /v1/jobs/{id} → 查询状态 (pending/running/done/failed)
- GET /v1/jobs → 列出所有任务（分页）
- DELETE /v1/jobs/{id} → 取消运行中的任务

特性:
- 状态跟踪: pending → running → done/failed/partial
- 检查点恢复: 记录已导入偏移量，中断后可续费
- 去重: 通过 external_id 或 content_hash 去重
- 重试: 单条失败不影响批次
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine import RecallEngine

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


@dataclass
class JobCheckpoint:
    """任务检查点"""
    offset: int = 0         # 已处理的偏移量
    success_count: int = 0  # 成功数
    error_count: int = 0    # 失败数
    errors: List[Dict[str, Any]] = field(default_factory=list)  # 错误详情（最多100条）
    dedup_count: int = 0    # 去重跳过数
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "offset": self.offset,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "dedup_count": self.dedup_count,
            "errors": self.errors[:20],  # 只返回前20条
            "updated_at": self.updated_at,
        }


@dataclass
class Job:
    """一个异步导入任务"""
    id: str
    status: JobStatus = JobStatus.PENDING
    total_items: int = 0
    user_id: str = "default"
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    checkpoint: JobCheckpoint = field(default_factory=JobCheckpoint)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _cancel_flag: bool = field(default=False, repr=False)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def progress(self) -> float:
        if self.total_items <= 0:
            return 0.0
        return min(1.0, self.checkpoint.offset / self.total_items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "total_items": self.total_items,
            "progress": round(self.progress, 4),
            "user_id": self.user_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "checkpoint": self.checkpoint.to_dict(),
            "metadata": self.metadata,
        }


class JobManager:
    """异步导入任务管理器

    使用线程池执行导入任务，支持检查点和去重。
    """

    MAX_JOBS = 1000         # 最大保留任务数
    MAX_CONCURRENT = 2      # 最大并发任务数
    CHECKPOINT_INTERVAL = 50  # 每 N 条记录保存一次检查点

    def __init__(self, data_path: str = ""):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}
        self._job_order: List[str] = []  # 按创建时间排序的 job_id
        self._executor = ThreadPoolExecutor(
            max_workers=self.MAX_CONCURRENT,
            thread_name_prefix="recall-job",
        )
        self._futures: Dict[str, Future] = {}
        self._data_path = data_path
        self._checkpoint_dir = os.path.join(data_path, 'job_checkpoints') if data_path else ''

        # 已处理的 content hash 集合（用于去重）
        self._processed_hashes: set = set()

        if self._checkpoint_dir:
            os.makedirs(self._checkpoint_dir, exist_ok=True)

    def submit_import(
        self,
        items: List[Dict[str, Any]],
        user_id: str = "default",
        engine: Optional['RecallEngine'] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Job:
        """提交导入任务

        Args:
            items: 待导入的记忆列表, 每项: { "content": "...", "external_id": "...", "metadata": {...} }
            user_id: 用户 ID
            engine: RecallEngine 实例
            metadata: 任务元数据

        Returns:
            Job 对象
        """
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            total_items=len(items),
            user_id=user_id,
            metadata=metadata or {},
        )

        with self._lock:
            # 淘汰旧任务
            while len(self._jobs) >= self.MAX_JOBS and self._job_order:
                old_id = self._job_order.pop(0)
                self._jobs.pop(old_id, None)
                self._futures.pop(old_id, None)

            self._jobs[job_id] = job
            self._job_order.append(job_id)

        # 提交到线程池
        future = self._executor.submit(self._run_import, job, items, engine)
        self._futures[job_id] = future

        logger.info("Job %s submitted: %d items for user=%s", job_id, len(items), user_id)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """获取任务"""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        offset: int = 0,
        limit: int = 20,
        status: Optional[JobStatus] = None,
    ) -> Dict[str, Any]:
        """列出所有任务（分页）"""
        with self._lock:
            all_jobs = [self._jobs[jid] for jid in reversed(self._job_order) if jid in self._jobs]
        if status:
            all_jobs = [j for j in all_jobs if j.status == status]

        total = len(all_jobs)
        page = all_jobs[offset: offset + limit]
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "jobs": [j.to_dict() for j in page],
        }

    def cancel_job(self, job_id: str) -> bool:
        """取消任务"""
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            return False

        job._cancel_flag = True
        future = self._futures.get(job_id)
        if future and not future.done():
            future.cancel()

        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now().isoformat()
        logger.info("Job %s cancelled", job_id)
        return True

    def cleanup_completed(self, max_age_seconds: int = 86400) -> int:
        """清理已完成的旧任务"""
        now = time.time()
        removed = 0
        with self._lock:
            to_remove = []
            for jid, job in self._jobs.items():
                if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                    if job.finished_at:
                        try:
                            fin = datetime.fromisoformat(job.finished_at).timestamp()
                            if now - fin > max_age_seconds:
                                to_remove.append(jid)
                        except Exception:
                            pass
            for jid in to_remove:
                self._jobs.pop(jid, None)
                self._futures.pop(jid, None)
                if jid in self._job_order:
                    self._job_order.remove(jid)
                removed += 1
        return removed

    # ==================== 内部方法 ====================

    def _run_import(
        self,
        job: Job,
        items: List[Dict[str, Any]],
        engine: Optional['RecallEngine'],
    ) -> None:
        """执行导入任务（在线程中运行）"""
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now().isoformat()

        # 从检查点恢复
        start_offset = self._load_checkpoint(job.id)
        if start_offset > 0:
            job.checkpoint.offset = start_offset
            logger.info("Job %s: 从检查点 offset=%d 恢复", job.id, start_offset)

        try:
            for i in range(start_offset, len(items)):
                if job._cancel_flag:
                    job.status = JobStatus.CANCELLED
                    job.finished_at = datetime.now().isoformat()
                    return

                item = items[i]
                try:
                    content = item.get('content', '')
                    if not content:
                        job.checkpoint.error_count += 1
                        if len(job.checkpoint.errors) < 100:
                            job.checkpoint.errors.append({
                                "index": i, "error": "空内容",
                            })
                        continue

                    # 去重检查
                    external_id = item.get('external_id', '')
                    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

                    dedup_key = external_id or content_hash
                    if dedup_key in self._processed_hashes:
                        job.checkpoint.dedup_count += 1
                        job.checkpoint.offset = i + 1
                        continue
                    self._processed_hashes.add(dedup_key)

                    # 添加到引擎
                    if engine:
                        metadata = item.get('metadata', {})
                        metadata['_import_job_id'] = job.id
                        metadata['_import_index'] = i
                        if external_id:
                            metadata['external_id'] = external_id

                        engine.add(
                            content=content,
                            user_id=job.user_id,
                            metadata=metadata,
                        )

                    job.checkpoint.success_count += 1

                except Exception as e:
                    job.checkpoint.error_count += 1
                    if len(job.checkpoint.errors) < 100:
                        job.checkpoint.errors.append({
                            "index": i, "error": str(e),
                        })

                job.checkpoint.offset = i + 1
                job.checkpoint.updated_at = datetime.now().isoformat()

                # 定期保存检查点
                if (i + 1) % self.CHECKPOINT_INTERVAL == 0:
                    self._save_checkpoint(job)

            # 完成
            if job.checkpoint.error_count > 0 and job.checkpoint.success_count > 0:
                job.status = JobStatus.PARTIAL
            elif job.checkpoint.error_count > 0 and job.checkpoint.success_count == 0:
                job.status = JobStatus.FAILED
            else:
                job.status = JobStatus.DONE

        except Exception as e:
            logger.error("Job %s failed: %s", job.id, e, exc_info=True)
            job.status = JobStatus.FAILED
            if len(job.checkpoint.errors) < 100:
                job.checkpoint.errors.append({"index": -1, "error": str(e)})

        finally:
            job.finished_at = datetime.now().isoformat()
            self._save_checkpoint(job)
            self._cleanup_checkpoint(job.id)

    def _save_checkpoint(self, job: Job) -> None:
        """保存检查点到磁盘"""
        if not self._checkpoint_dir:
            return
        try:
            path = os.path.join(self._checkpoint_dir, f"{job.id}.json")
            data = {
                "job_id": job.id,
                "offset": job.checkpoint.offset,
                "success_count": job.checkpoint.success_count,
                "error_count": job.checkpoint.error_count,
                "dedup_count": job.checkpoint.dedup_count,
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning("Job %s: 保存检查点失败: %s", job.id, e)

    def _load_checkpoint(self, job_id: str) -> int:
        """从磁盘加载检查点偏移量"""
        if not self._checkpoint_dir:
            return 0
        path = os.path.join(self._checkpoint_dir, f"{job_id}.json")
        if not os.path.exists(path):
            return 0
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('offset', 0)
        except Exception:
            return 0

    def _cleanup_checkpoint(self, job_id: str) -> None:
        """完成后清理检查点文件"""
        if not self._checkpoint_dir:
            return
        path = os.path.join(self._checkpoint_dir, f"{job_id}.json")
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


# ==================== 单例 ====================

_job_manager: Optional[JobManager] = None
_job_lock = threading.Lock()


def get_job_manager(data_path: str = "") -> JobManager:
    """获取全局 JobManager 实例"""
    global _job_manager
    if _job_manager is None:
        with _job_lock:
            if _job_manager is None:
                _job_manager = JobManager(data_path=data_path)
    return _job_manager
