"""
Recall v7.7 - Data Lifecycle Management

Auto-archive old memories, auto-backup, cleanup temp files.
Endpoint: POST /v1/admin/lifecycle/run

Configuration (env vars):
- RECALL_LIFECYCLE_ARCHIVE_DAYS   (default 365) — archive memories older than N days
- RECALL_LIFECYCLE_BACKUP_ENABLED (default true)
- RECALL_LIFECYCLE_BACKUP_DIR     (default recall_data/backups)
- RECALL_LIFECYCLE_CLEANUP_TEMP   (default true)
"""

from __future__ import annotations

import os
import time
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_print(msg: str) -> None:
    """Safe print for Windows GBK encoding."""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class LifecycleManager:
    """Data lifecycle management for Recall.

    Responsibilities:
    1. Archive old memories (move to archive storage after N days)
    2. Backup data directory (snapshot to backup dir)
    3. Cleanup temporary files (recall_data/temp, __pycache__, etc.)
    """

    def __init__(
        self,
        data_root: str = "recall_data",
        archive_days: int = 365,
        backup_enabled: bool = True,
        backup_dir: Optional[str] = None,
        cleanup_temp: bool = True,
    ):
        self.data_root = Path(data_root)
        self.archive_days = archive_days
        self.backup_enabled = backup_enabled
        self.backup_dir = Path(backup_dir) if backup_dir else self.data_root / "backups"
        self.cleanup_temp = cleanup_temp

    @classmethod
    def from_env(cls, data_root: str = "recall_data") -> "LifecycleManager":
        """Create LifecycleManager from environment variables.
        
        v7.0.3: 优先从 RecallConfig 读取，保证默认值一致性。
        """
        try:
            from .config import RecallConfig
            cfg = RecallConfig.from_env()
            return cls(
                data_root=cfg.recall_data_root or data_root,
                archive_days=cfg.recall_lifecycle_archive_days,
                backup_enabled=cfg.recall_lifecycle_backup_enabled,
                backup_dir=cfg.recall_lifecycle_backup_dir or None,
                cleanup_temp=cfg.recall_lifecycle_cleanup_temp,
            )
        except Exception:
            # fallback: 直接读环境变量（默认值与 RecallConfig 对齐）
            return cls(
                data_root=data_root,
                archive_days=int(os.environ.get("RECALL_LIFECYCLE_ARCHIVE_DAYS", "90")),
                backup_enabled=os.environ.get("RECALL_LIFECYCLE_BACKUP_ENABLED", "false").lower()
                in ("1", "true", "yes"),
                backup_dir=os.environ.get("RECALL_LIFECYCLE_BACKUP_DIR"),
                cleanup_temp=os.environ.get("RECALL_LIFECYCLE_CLEANUP_TEMP", "true").lower()
                in ("1", "true", "yes"),
            )

    def run(self, engine: Any = None) -> Dict[str, Any]:
        """Execute all lifecycle tasks. Returns a summary dict."""
        start = time.time()
        results: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "archive": None,
            "backup": None,
            "cleanup": None,
        }

        # 1. Archive old memories
        try:
            results["archive"] = self._archive_old_memories(engine)
        except Exception as e:
            results["archive"] = {"error": str(e)}
            logger.error(f"[Lifecycle] Archive 失败: {e}")

        # 2. Backup
        if self.backup_enabled:
            try:
                results["backup"] = self._backup()
            except Exception as e:
                results["backup"] = {"error": str(e)}
                logger.error(f"[Lifecycle] Backup 失败: {e}")
        else:
            results["backup"] = {"skipped": True, "reason": "backup_disabled"}

        # 3. Cleanup temp files
        if self.cleanup_temp:
            try:
                results["cleanup"] = self._cleanup_temp_files()
            except Exception as e:
                results["cleanup"] = {"error": str(e)}
                logger.error(f"[Lifecycle] Cleanup 失败: {e}")
        else:
            results["cleanup"] = {"skipped": True, "reason": "cleanup_disabled"}

        elapsed = time.time() - start
        results["elapsed_seconds"] = round(elapsed, 2)
        _safe_print(f"[Lifecycle] [OK] 生命周期管理完成 ({elapsed:.1f}s)")
        return results

    # ---- Archive ----

    def _archive_old_memories(self, engine: Any = None) -> Dict[str, Any]:
        """Archive memories older than archive_days.

        Scans the data directory for JSON memory files and moves old ones
        to an ``archive/`` subdirectory.  If engine is provided and has
        a ``consolidated_memory``, uses that to identify stale entries.
        """
        archive_dir = self.data_root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        cutoff = datetime.now() - timedelta(days=self.archive_days)
        archived_count = 0
        scanned_count = 0

        # Strategy 1: Engine-based archival via consolidated memory
        if engine and hasattr(engine, "consolidated_memory"):
            try:
                cm = engine.consolidated_memory
                # If consolidated_memory exposes entities/memories
                all_entities = getattr(cm, "entities", {})
                for entity_name, entity in list(all_entities.items()):
                    scanned_count += 1
                    updated_at = getattr(entity, "updated_at", None)
                    if updated_at and isinstance(updated_at, datetime) and updated_at < cutoff:
                        # Mark as archived (soft archive)
                        if hasattr(entity, "metadata"):
                            entity.metadata = entity.metadata or {}
                            entity.metadata["archived"] = True
                            entity.metadata["archived_at"] = datetime.now().isoformat()
                            archived_count += 1
            except Exception as e:
                logger.warning(f"[Lifecycle] Engine-based archive partial failure: {e}")

        # Strategy 2: File-based archival — move old data files
        data_dir = self.data_root / "data"
        file_archived = 0
        if data_dir.exists():
            for fp in data_dir.rglob("*.json"):
                try:
                    scanned_count += 1
                    stat = fp.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    if mtime < cutoff:
                        # Move to archive, preserving relative path
                        rel = fp.relative_to(data_dir)
                        dest = archive_dir / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(fp), str(dest))
                        file_archived += 1
                except Exception:
                    pass  # skip individual file errors

        archived_count += file_archived

        return {
            "scanned": scanned_count,
            "archived": archived_count,
            "cutoff_date": cutoff.isoformat(),
            "archive_days": self.archive_days,
            "archive_dir": str(archive_dir),
        }

    # ---- Backup ----

    def _backup(self) -> Dict[str, Any]:
        """Create a timestamped backup of the data directory.

        Copies ``recall_data/data`` and ``recall_data/index`` into a
        timestamped folder under ``backup_dir``.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"backup_{timestamp}"
        dest.mkdir(parents=True, exist_ok=True)

        copied_files = 0
        total_size = 0

        dirs_to_backup = ["data", "index", "indexes", "config"]
        for subdir in dirs_to_backup:
            src = self.data_root / subdir
            if src.exists():
                dst = dest / subdir
                try:
                    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                    for f in dst.rglob("*"):
                        if f.is_file():
                            copied_files += 1
                            total_size += f.stat().st_size
                except Exception as e:
                    logger.warning(f"[Lifecycle] Backup {subdir} 部分失败: {e}")

        # Cleanup old backups — keep last 7
        self._rotate_backups(keep=7)

        return {
            "backup_path": str(dest),
            "files_copied": copied_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "timestamp": timestamp,
        }

    def _rotate_backups(self, keep: int = 7) -> int:
        """Remove oldest backups, keeping only ``keep`` most recent."""
        if not self.backup_dir.exists():
            return 0

        backups = sorted(
            [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")],
            key=lambda d: d.name,
            reverse=True,
        )
        removed = 0
        for old in backups[keep:]:
            try:
                shutil.rmtree(str(old))
                removed += 1
            except Exception:
                pass
        return removed

    # ---- Cleanup ----

    def _cleanup_temp_files(self) -> Dict[str, Any]:
        """Remove temporary files and caches.

        Targets:
        - recall_data/temp/*
        - recall_data/cache/* (file cache, not Redis)
        - __pycache__ under recall_data
        - *.pyc files
        - Empty directories
        """
        cleaned_files = 0
        cleaned_dirs = 0
        freed_bytes = 0

        # Temp directory
        temp_dir = self.data_root / "temp"
        if temp_dir.exists():
            for item in temp_dir.iterdir():
                try:
                    if item.is_file():
                        freed_bytes += item.stat().st_size
                        item.unlink()
                        cleaned_files += 1
                    elif item.is_dir():
                        size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                        freed_bytes += size
                        shutil.rmtree(str(item))
                        cleaned_dirs += 1
                except Exception:
                    pass

        # __pycache__ under recall_data
        for pycache in self.data_root.rglob("__pycache__"):
            try:
                if pycache.is_dir():
                    shutil.rmtree(str(pycache))
                    cleaned_dirs += 1
            except Exception:
                pass

        # *.pyc files
        for pyc in self.data_root.rglob("*.pyc"):
            try:
                freed_bytes += pyc.stat().st_size
                pyc.unlink()
                cleaned_files += 1
            except Exception:
                pass

        # Remove empty directories (bottom-up)
        for dirpath in sorted(self.data_root.rglob("*"), reverse=True):
            try:
                if dirpath.is_dir() and not any(dirpath.iterdir()):
                    dirpath.rmdir()
                    cleaned_dirs += 1
            except Exception:
                pass

        return {
            "files_removed": cleaned_files,
            "dirs_removed": cleaned_dirs,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        }


# ==================== Convenience ====================

def run_lifecycle(engine: Any = None, data_root: str = "recall_data") -> Dict[str, Any]:
    """Quick one-shot lifecycle run using env-based configuration."""
    mgr = LifecycleManager.from_env(data_root=data_root)
    return mgr.run(engine=engine)
