"""原子写入工具 — 防止断电/崩溃导致数据损坏

使用 tmp + rename 模式：先写入临时文件，成功后原子重命名替换目标文件。
即使在写入过程中进程崩溃，原文件也不会被截断或损坏。

Windows 上 os.replace() 是原子操作（NTFS）；Linux/Mac 上 os.rename() 同样原子。
"""

import os
import sys
import json
import time
import tempfile
from typing import Any

# Windows 上 os.replace() 可能因文件锁/杀毒软件暂时失败，需要重试
_IS_WINDOWS = sys.platform == 'win32'
_REPLACE_MAX_RETRIES = 5 if _IS_WINDOWS else 1
_REPLACE_RETRY_DELAY = 0.05  # 50ms


def atomic_json_dump(data: Any, filepath: str, *, ensure_ascii: bool = False, indent: int | None = None) -> None:
    """原子写入 JSON 文件
    
    流程：
    1. 在同目录创建临时文件
    2. JSON 序列化写入临时文件
    3. flush + fsync 确保落盘
    4. os.replace() 原子替换目标文件
    
    如果步骤 2/3 中崩溃，临时文件会残留但原文件完好。
    如果步骤 4 中崩溃（极低概率），NTFS/ext4 保证原子性。
    
    Args:
        data: 要序列化的数据
        filepath: 目标文件路径
        ensure_ascii: json.dump 参数
        indent: json.dump 参数
    """
    dir_path = os.path.dirname(filepath) or '.'
    os.makedirs(dir_path, exist_ok=True)
    
    # 在同目录创建临时文件（确保同一文件系统，rename 才是原子的）
    fd, tmp_path = tempfile.mkstemp(
        suffix='.tmp',
        prefix='.recall_atomic_',
        dir=dir_path
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        # 原子替换（Windows 上可能因文件锁需要重试）
        last_err = None
        for attempt in range(_REPLACE_MAX_RETRIES):
            try:
                os.replace(tmp_path, filepath)
                last_err = None
                break
            except PermissionError as e:
                last_err = e
                if attempt < _REPLACE_MAX_RETRIES - 1:
                    time.sleep(_REPLACE_RETRY_DELAY * (attempt + 1))
        if last_err is not None:
            raise last_err
    except Exception:
        # 写入失败，清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
