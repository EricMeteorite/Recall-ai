"""元数据索引 — 支持按 source/tags/category/content_type/event_time 过滤"""

import os
import json
import atexit
from collections import defaultdict
from datetime import datetime, date
from typing import Dict, Set, Optional, List


class MetadataIndex:
    """元数据倒排索引"""

    def __init__(self, data_path):
        self.data_path = data_path
        self._index_file = os.path.join(data_path, 'metadata_index.json')
        # 多字段倒排索引
        self._by_source: Dict[str, Set[str]] = defaultdict(set)     # source → memory_ids
        self._by_tag: Dict[str, Set[str]] = defaultdict(set)        # tag → memory_ids
        self._by_category: Dict[str, Set[str]] = defaultdict(set)   # category → memory_ids
        self._by_content_type: Dict[str, Set[str]] = defaultdict(set)
        self._by_event_date: Dict[str, Set[str]] = defaultdict(set) # date_str(YYYY-MM-DD) → memory_ids
        self._dirty_count = 0
        self._load()
        # 注册退出时自动刷盘，防止 dirty_count < 100 时进程退出丢数据
        atexit.register(self.flush)

    def add(self, memory_id, source="", tags=None, category="", content_type="", event_time=""):
        if source:
            self._by_source[source].add(memory_id)
        for tag in (tags or []):
            self._by_tag[tag].add(memory_id)
        if category:
            self._by_category[category].add(memory_id)
        if content_type:
            self._by_content_type[content_type].add(memory_id)
        if event_time:
            date_key = self._parse_date_key(event_time)
            if date_key:
                self._by_event_date[date_key].add(memory_id)
        self._dirty_count += 1
        if self._dirty_count >= 100:
            self._save()
            self._dirty_count = 0

    @staticmethod
    def _parse_date_key(event_time) -> Optional[str]:
        """将各种时间格式统一解析为 YYYY-MM-DD 日期键"""
        if not event_time:
            return None
        if isinstance(event_time, datetime):
            return event_time.strftime('%Y-%m-%d')
        if isinstance(event_time, date):
            return event_time.isoformat()
        if isinstance(event_time, str):
            # 尝试解析 ISO 格式字符串（如 2025-01-20T10:00:00+08:00 或 2025-01-20）
            try:
                dt = datetime.fromisoformat(event_time)
                return dt.strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                pass
            # 兜底：直接取前10个字符（YYYY-MM-DD）
            if len(event_time) >= 10 and event_time[4] == '-' and event_time[7] == '-':
                return event_time[:10]
        return None

    def query(self, source=None, tags=None, category=None, content_type=None,
              event_time_start=None, event_time_end=None) -> Set[str]:
        """多条件 AND 查询，支持 event_time 日期范围过滤"""
        result = None
        if source:
            candidates = self._by_source.get(source, set())
            result = candidates if result is None else result & candidates
        if tags:
            for tag in tags:
                candidates = self._by_tag.get(tag, set())
                result = candidates if result is None else result & candidates
        if category:
            candidates = self._by_category.get(category, set())
            result = candidates if result is None else result & candidates
        if content_type:
            candidates = self._by_content_type.get(content_type, set())
            result = candidates if result is None else result & candidates
        if event_time_start or event_time_end:
            candidates = self._query_by_date_range(event_time_start, event_time_end)
            result = candidates if result is None else result & candidates
        return result or set()

    def _query_by_date_range(self, start=None, end=None) -> Set[str]:
        """按日期范围查询，start/end 可以是字符串或 datetime/date 对象"""
        start_key = self._parse_date_key(start) if start else None
        end_key = self._parse_date_key(end) if end else None
        matched = set()
        for date_key, ids in self._by_event_date.items():
            if start_key and date_key < start_key:
                continue
            if end_key and date_key > end_key:
                continue
            matched |= ids
        return matched

    def remove(self, memory_id: str):
        """从所有倒排索引中移除指定 memory_id"""
        for source_set in self._by_source.values():
            source_set.discard(memory_id)
        for tag_set in self._by_tag.values():
            tag_set.discard(memory_id)
        for cat_set in self._by_category.values():
            cat_set.discard(memory_id)
        for ct_set in self._by_content_type.values():
            ct_set.discard(memory_id)
        for date_set in self._by_event_date.values():
            date_set.discard(memory_id)
        self._dirty_count += 1
        if self._dirty_count >= 100:
            self._save()
            self._dirty_count = 0

    def remove_batch(self, memory_ids: set):
        """批量移除多个 memory_id"""
        for source_set in self._by_source.values():
            source_set -= memory_ids
        for tag_set in self._by_tag.values():
            tag_set -= memory_ids
        for cat_set in self._by_category.values():
            cat_set -= memory_ids
        for ct_set in self._by_content_type.values():
            ct_set -= memory_ids
        for date_set in self._by_event_date.values():
            date_set -= memory_ids
        self._dirty_count += len(memory_ids)
        if self._dirty_count >= 100:
            self._save()
            self._dirty_count = 0

    def clear(self):
        """清空所有索引数据"""
        self._by_source.clear()
        self._by_tag.clear()
        self._by_category.clear()
        self._by_content_type.clear()
        self._by_event_date.clear()
        self._dirty_count = 0
        self._save()

    def _save(self):
        """持久化到 JSON 文件"""
        os.makedirs(os.path.dirname(self._index_file), exist_ok=True)
        data = {
            'by_source': {k: list(v) for k, v in self._by_source.items()},
            'by_tag': {k: list(v) for k, v in self._by_tag.items()},
            'by_category': {k: list(v) for k, v in self._by_category.items()},
            'by_content_type': {k: list(v) for k, v in self._by_content_type.items()},
            'by_event_date': {k: list(v) for k, v in self._by_event_date.items()},
        }
        with open(self._index_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def _load(self):
        """从 JSON 文件加载"""
        if os.path.exists(self._index_file):
            with open(self._index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, v in data.get('by_source', {}).items():
                self._by_source[k] = set(v)
            for k, v in data.get('by_tag', {}).items():
                self._by_tag[k] = set(v)
            for k, v in data.get('by_category', {}).items():
                self._by_category[k] = set(v)
            for k, v in data.get('by_content_type', {}).items():
                self._by_content_type[k] = set(v)
            for k, v in data.get('by_event_date', {}).items():
                self._by_event_date[k] = set(v)

    def flush(self):
        """显式刷盘"""
        if self._dirty_count > 0:
            self._save()
            self._dirty_count = 0
