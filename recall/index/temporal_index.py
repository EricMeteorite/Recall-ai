"""时态索引 - 支持时间范围查询的高效索引

设计理念：
1. 支持三时态查询（事实时间、知识时间、系统时间）
2. 基于区间树的高效范围查询
3. 与现有 InvertedIndex 互补，不替代
"""

from __future__ import annotations
import atexit

import os
import json
import bisect
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


@dataclass
class TimeRange:
    """时间范围"""
    start: Optional[datetime] = None  # None 表示无限早
    end: Optional[datetime] = None    # None 表示无限晚
    
    def contains(self, point: datetime) -> bool:
        """判断时间点是否在范围内"""
        if self.start and point < self.start:
            return False
        if self.end and point > self.end:
            return False
        return True
    
    def overlaps(self, other: 'TimeRange') -> bool:
        """判断是否与另一个范围重叠"""
        # 如果 self.end < other.start 或 self.start > other.end，则不重叠
        if self.end and other.start and self.end < other.start:
            return False
        if self.start and other.end and self.start > other.end:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'start': self.start.isoformat() if self.start else None,
            'end': self.end.isoformat() if self.end else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeRange':
        return cls(
            start=datetime.fromisoformat(data['start']) if data.get('start') else None,
            end=datetime.fromisoformat(data['end']) if data.get('end') else None
        )


@dataclass
class TemporalEntry:
    """时态索引条目"""
    doc_id: str                       # 文档/边/节点 ID
    
    # 三时态
    fact_range: TimeRange = field(default_factory=TimeRange)      # T1: 事实时间范围
    known_at: Optional[datetime] = None                           # T2: 知识时间
    system_range: TimeRange = field(default_factory=TimeRange)    # T3: 系统时间范围
    
    # 元数据
    subject: str = ""                 # 主体（用于快速过滤）
    predicate: str = ""               # 谓词
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'doc_id': self.doc_id,
            'fact_range': self.fact_range.to_dict(),
            'known_at': self.known_at.isoformat() if self.known_at else None,
            'system_range': self.system_range.to_dict(),
            'subject': self.subject,
            'predicate': self.predicate
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TemporalEntry':
        return cls(
            doc_id=data['doc_id'],
            fact_range=TimeRange.from_dict(data['fact_range']),
            known_at=datetime.fromisoformat(data['known_at']) if data.get('known_at') else None,
            system_range=TimeRange.from_dict(data['system_range']),
            subject=data.get('subject', ''),
            predicate=data.get('predicate', '')
        )


class TemporalIndex:
    """时态索引 - 支持三时态查询
    
    实现策略：
    1. 使用排序列表 + 二分查找实现基本的时间范围查询
    2. 维护多个索引视图：按 subject、按 predicate
    3. 支持增量持久化
    
    查询能力：
    - query_at_time(point): 查询某时间点有效的所有条目
    - query_range(start, end): 查询与时间范围重叠的条目
    - query_by_subject(subject, point): 查询某主体在某时间点的状态
    - query_timeline(subject): 获取某主体的完整时间线
    """
    
    def __init__(self, data_path: str):
        """初始化时态索引
        
        Args:
            data_path: 数据存储路径
        """
        self.data_path = data_path
        self.index_dir = os.path.join(data_path, 'indexes')
        self.index_file = os.path.join(self.index_dir, 'temporal_index.json')
        
        # 核心存储
        self.entries: Dict[str, TemporalEntry] = {}  # doc_id -> entry
        
        # 按起始时间排序的列表（用于范围查询）
        # 格式: [(timestamp, doc_id), ...]
        self._sorted_by_fact_start: List[Tuple[float, str]] = []
        self._sorted_by_known_at: List[Tuple[float, str]] = []
        self._sorted_by_system_start: List[Tuple[float, str]] = []
        self._sorted_by_fact_end: List[Tuple[float, str]] = []    # (fact_end_ts, doc_id)
        self._sorted_by_system_end: List[Tuple[float, str]] = []  # (system_end_ts, doc_id)
        
        # 辅助索引
        self._by_subject: Dict[str, Set[str]] = defaultdict(set)    # subject -> doc_ids
        self._by_predicate: Dict[str, Set[str]] = defaultdict(set)  # predicate -> doc_ids
        
        # 脏标记
        self._dirty = False
        
        # 加载
        self._load()
        
        # v7.0.9: atexit 安全网 — 确保进程退出时脏数据被持久化
        atexit.register(self._atexit_flush)
    
    def _atexit_flush(self):
        """atexit 回调：确保脏数据持久化"""
        try:
            if self._dirty:
                self._save()
        except Exception:
            pass
    
    def _load(self):
        """加载索引"""
        if not os.path.exists(self.index_file):
            return
        
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for entry_data in data.get('entries', []):
                entry = TemporalEntry.from_dict(entry_data)
                self.entries[entry.doc_id] = entry
                self._index_entry(entry)
                
        except Exception as e:
            _safe_print(f"[TemporalIndex] 加载索引失败: {e}")
    
    def _save(self):
        """保存索引（原子写入）"""
        if not self._dirty:
            return
        
        os.makedirs(self.index_dir, exist_ok=True)
        
        data = {
            'entries': [e.to_dict() for e in self.entries.values()],
            'version': '4.0'
        }
        
        # v7.0.9: 原子写入 — tmp + fsync + rename
        tmp_file = self.index_file + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self.index_file)
        
        self._dirty = False
    
    def _index_entry(self, entry: TemporalEntry):
        """索引单个条目（内存中）"""
        # 按时间排序的列表
        if entry.fact_range.start:
            ts = entry.fact_range.start.timestamp()
            bisect.insort(self._sorted_by_fact_start, (ts, entry.doc_id))
        
        if entry.known_at:
            ts = entry.known_at.timestamp()
            bisect.insort(self._sorted_by_known_at, (ts, entry.doc_id))
        
        if entry.system_range.start:
            ts = entry.system_range.start.timestamp()
            bisect.insort(self._sorted_by_system_start, (ts, entry.doc_id))
        
        if entry.fact_range.end:
            bisect.insort(self._sorted_by_fact_end, (entry.fact_range.end.timestamp(), entry.doc_id))
        if entry.system_range and entry.system_range.end:
            bisect.insort(self._sorted_by_system_end, (entry.system_range.end.timestamp(), entry.doc_id))
        
        # 辅助索引
        if entry.subject:
            self._by_subject[entry.subject].add(entry.doc_id)
        if entry.predicate:
            self._by_predicate[entry.predicate].add(entry.doc_id)
    
    def _unindex_entry(self, entry: TemporalEntry):
        """从内存索引中移除条目"""
        # 从排序列表移除（效率较低，但移除操作不频繁）
        if entry.fact_range.start:
            ts = entry.fact_range.start.timestamp()
            try:
                self._sorted_by_fact_start.remove((ts, entry.doc_id))
            except ValueError:
                pass
        
        if entry.known_at:
            ts = entry.known_at.timestamp()
            try:
                self._sorted_by_known_at.remove((ts, entry.doc_id))
            except ValueError:
                pass
        
        if entry.system_range.start:
            ts = entry.system_range.start.timestamp()
            try:
                self._sorted_by_system_start.remove((ts, entry.doc_id))
            except ValueError:
                pass
        
        if entry.fact_range.end:
            end_ts = entry.fact_range.end.timestamp()
            try:
                self._sorted_by_fact_end.remove((end_ts, entry.doc_id))
            except ValueError:
                pass
        if entry.system_range and entry.system_range.end:
            end_ts = entry.system_range.end.timestamp()
            try:
                self._sorted_by_system_end.remove((end_ts, entry.doc_id))
            except ValueError:
                pass
        
        # 辅助索引
        if entry.subject:
            self._by_subject[entry.subject].discard(entry.doc_id)
        if entry.predicate:
            self._by_predicate[entry.predicate].discard(entry.doc_id)
    
    def add(self, entry: TemporalEntry):
        """添加条目"""
        # 如果已存在，先移除旧索引
        if entry.doc_id in self.entries:
            self._unindex_entry(self.entries[entry.doc_id])
        
        self.entries[entry.doc_id] = entry
        self._index_entry(entry)
        self._dirty = True
    
    def remove(self, doc_id: str) -> bool:
        """移除条目"""
        if doc_id not in self.entries:
            return False
        
        entry = self.entries[doc_id]
        self._unindex_entry(entry)
        del self.entries[doc_id]
        self._dirty = True
        return True
    
    def get(self, doc_id: str) -> Optional[TemporalEntry]:
        """获取条目"""
        return self.entries.get(doc_id)
    
    def flush(self):
        """强制保存"""
        self._dirty = True
        self._save()
    
    # =========================================================================
    # 时态查询 API
    # =========================================================================
    
    def query_at_time(
        self,
        point: datetime,
        time_type: str = 'fact'  # fact | known | system
    ) -> List[str]:
        """双端 bisect 剪枝 — O(log n + min(k_start, k_end)) 而非 O(n)

        利用 _sorted_by_fact_start 和 _sorted_by_fact_end 两个有序列表：
        - 集合 A: start <= point  (通过 bisect_right on _sorted_by_fact_start)
        - 集合 B: end >= point    (通过 bisect_left on _sorted_by_fact_end)
        - 结果 = A ∩ B

        选择较小的候选集遍历 + 交叉验证，避免全量扫描。

        Args:
            point: 查询时间点
            time_type: 时间类型
                - 'fact': 事实时间（默认）
                - 'known': 知识时间
                - 'system': 系统时间

        Returns:
            有效的 doc_id 列表
        """
        ts = point.timestamp()

        if time_type == 'fact':
            # 集合 A 大小: start <= point
            idx_start = bisect.bisect_right(self._sorted_by_fact_start, (ts, '\xff'))
            # 集合 B 大小: end >= point
            idx_end = bisect.bisect_left(self._sorted_by_fact_end, (ts,))
            count_ended_after = len(self._sorted_by_fact_end) - idx_end

            # 选择较小的候选集遍历，用 contains() 交叉验证
            if idx_start <= count_ended_after:
                results = []
                for i in range(idx_start):
                    _, doc_id = self._sorted_by_fact_start[i]
                    entry = self.entries.get(doc_id)
                    if entry and entry.fact_range.contains(point):
                        results.append(doc_id)
                return results
            else:
                results = []
                for i in range(idx_end, len(self._sorted_by_fact_end)):
                    _, doc_id = self._sorted_by_fact_end[i]
                    entry = self.entries.get(doc_id)
                    if entry and entry.fact_range.contains(point):
                        results.append(doc_id)
                return results

        elif time_type == 'known':
            idx = bisect.bisect_right(self._sorted_by_known_at, (ts, '\xff'))
            return [doc_id for _, doc_id in self._sorted_by_known_at[:idx]]

        elif time_type == 'system':
            # 同样双端剪枝
            idx_start = bisect.bisect_right(self._sorted_by_system_start, (ts, '\xff'))
            idx_end = bisect.bisect_left(self._sorted_by_system_end, (ts,))
            count_ended_after = len(self._sorted_by_system_end) - idx_end

            if idx_start <= count_ended_after:
                results = []
                for i in range(idx_start):
                    _, doc_id = self._sorted_by_system_start[i]
                    entry = self.entries.get(doc_id)
                    if entry and entry.system_range.contains(point):
                        results.append(doc_id)
                return results
            else:
                results = []
                for i in range(idx_end, len(self._sorted_by_system_end)):
                    _, doc_id = self._sorted_by_system_end[i]
                    entry = self.entries.get(doc_id)
                    if entry and entry.system_range.contains(point):
                        results.append(doc_id)
                return results

        return []
    
    def query_range(
        self,
        start: Optional[datetime],
        end: Optional[datetime],
        time_type: str = 'fact'
    ) -> List[str]:
        """双端 bisect 范围查询 — O(log n + min(k_left, k_right))

        区间重叠条件: entry.start <= query.end AND entry.end >= query.start
        利用两个有序列表剪枝：
        - 候选 A: entry.start <= query.end  (bisect on _sorted_by_*_start)
        - 候选 B: entry.end >= query.start  (bisect on _sorted_by_*_end)
        选择较小的候选集遍历。

        Args:
            start: 范围起始（None 表示无限早）
            end: 范围结束（None 表示无限晚）
            time_type: 时间类型

        Returns:
            重叠的 doc_id 列表
        """
        if time_type == 'fact':
            start_list = self._sorted_by_fact_start
            end_list = self._sorted_by_fact_end
        elif time_type == 'system':
            start_list = self._sorted_by_system_start
            end_list = self._sorted_by_system_end
        else:
            return []

        query_tr = TimeRange(start=start, end=end)

        # 候选 A: entry.start <= query.end
        if end:
            count_a = bisect.bisect_right(start_list, (end.timestamp(), '\xff'))
        else:
            count_a = len(start_list)

        # 候选 B: entry.end >= query.start
        if start:
            idx_b = bisect.bisect_left(end_list, (start.timestamp(),))
            count_b = len(end_list) - idx_b
        else:
            idx_b = 0
            count_b = len(end_list)

        # 选择较小的候选集
        if count_a <= count_b:
            results = []
            for i in range(count_a):
                _, doc_id = start_list[i]
                entry = self.entries.get(doc_id)
                if entry:
                    target_range = entry.fact_range if time_type == 'fact' else entry.system_range
                    if target_range.overlaps(query_tr):
                        results.append(doc_id)
            return results
        else:
            results = []
            for i in range(idx_b, len(end_list)):
                _, doc_id = end_list[i]
                entry = self.entries.get(doc_id)
                if entry:
                    target_range = entry.fact_range if time_type == 'fact' else entry.system_range
                    if target_range.overlaps(query_tr):
                        results.append(doc_id)
            return results
    
    def query_by_subject(
        self,
        subject: str,
        point: Optional[datetime] = None,
        predicate: Optional[str] = None
    ) -> List[str]:
        """查询某主体的条目
        
        Args:
            subject: 主体ID
            point: 可选的时间点（仅返回该时间点有效的）
            predicate: 可选的谓词过滤
        
        Returns:
            doc_id 列表
        """
        candidates = self._by_subject.get(subject, set())
        
        if predicate:
            predicate_docs = self._by_predicate.get(predicate, set())
            candidates = candidates & predicate_docs
        
        if point is None:
            return list(candidates)
        
        # 时间过滤
        results = []
        for doc_id in candidates:
            entry = self.entries.get(doc_id)
            if entry and entry.fact_range.contains(point):
                results.append(doc_id)
        
        return results
    
    def query_timeline(
        self,
        subject: str,
        predicate: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Tuple[datetime, str, str]]:
        """获取某主体的时间线
        
        Args:
            subject: 主体ID
            predicate: 可选谓词过滤
            start: 时间范围起始
            end: 时间范围结束
        
        Returns:
            [(时间点, doc_id, 事件类型), ...] 按时间排序
            事件类型: 'started' | 'ended' | 'known'
        """
        timeline: List[Tuple[datetime, str, str]] = []
        
        candidates = self._by_subject.get(subject, set())
        
        if predicate:
            predicate_docs = self._by_predicate.get(predicate, set())
            candidates = candidates & predicate_docs
        
        for doc_id in candidates:
            entry = self.entries.get(doc_id)
            if not entry:
                continue
            
            # 添加事实开始时间
            if entry.fact_range.start:
                timeline.append((entry.fact_range.start, doc_id, 'started'))
            
            # 添加事实结束时间
            if entry.fact_range.end:
                timeline.append((entry.fact_range.end, doc_id, 'ended'))
            
            # 添加知识获知时间
            if entry.known_at:
                timeline.append((entry.known_at, doc_id, 'known'))
        
        # 按时间排序
        timeline.sort(key=lambda x: x[0])
        
        # 时间范围过滤
        if start:
            timeline = [t for t in timeline if t[0] >= start]
        if end:
            timeline = [t for t in timeline if t[0] <= end]
        
        return timeline
    
    def query_before(
        self,
        point: datetime,
        limit: int = 100,
        time_type: str = 'fact'
    ) -> List[str]:
        """查询某时间点之前结束的条目 — bisect 优化
        
        Args:
            point: 时间点
            limit: 返回数量限制
            time_type: 时间类型
        
        Returns:
            doc_id 列表（按结束时间倒序）
        """
        if time_type == 'fact':
            sorted_list = self._sorted_by_fact_end
        elif time_type == 'system':
            sorted_list = self._sorted_by_system_end
        else:
            raise ValueError(f"time_type 必须为 'fact' 或 'system'，收到: '{time_type}'")
        
        point_ts = point.timestamp()
        right = bisect.bisect_right(sorted_list, (point_ts, '\xff'))
        
        results = []
        for i in range(right - 1, max(right - 1 - limit, -1), -1):
            _, doc_id = sorted_list[i]
            results.append(doc_id)
        return results
    
    def query_after(
        self,
        point: datetime,
        limit: int = 100,
        time_type: str = 'fact'
    ) -> List[str]:
        """查询某时间点之后开始的条目 — bisect 优化
        
        Args:
            point: 时间点
            limit: 返回数量限制
            time_type: 时间类型
        
        Returns:
            doc_id 列表（按开始时间正序）
        """
        if time_type == 'fact':
            sorted_list = self._sorted_by_fact_start
        elif time_type == 'system':
            sorted_list = self._sorted_by_system_start
        else:
            raise ValueError(f"time_type 必须为 'fact' 或 'system'，收到: '{time_type}'")
        
        point_ts = point.timestamp()
        left = bisect.bisect_left(sorted_list, (point_ts,))
        
        results = []
        for i in range(left, min(left + limit, len(sorted_list))):
            _, doc_id = sorted_list[i]
            results.append(doc_id)
        return results
    
    # =========================================================================
    # 统计与工具
    # =========================================================================
    
    def count(self) -> int:
        """返回条目总数"""
        return len(self.entries)
    
    def get_subjects(self) -> List[str]:
        """获取所有主体"""
        return list(self._by_subject.keys())
    
    def get_predicates(self) -> List[str]:
        """获取所有谓词"""
        return list(self._by_predicate.keys())
    
    def clear(self):
        """清空索引"""
        self.entries.clear()
        self._sorted_by_fact_start.clear()
        self._sorted_by_known_at.clear()
        self._sorted_by_system_start.clear()
        self._sorted_by_fact_end.clear()
        self._sorted_by_system_end.clear()
        self._by_subject.clear()
        self._by_predicate.clear()
        self._dirty = True
        self._save()


__all__ = [
    'TimeRange',
    'TemporalEntry',
    'TemporalIndex',
]
