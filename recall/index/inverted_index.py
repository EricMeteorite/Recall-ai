"""倒排索引 - 关键词到轮次的映射"""

import json
import os
from typing import Dict, List, Set
from collections import defaultdict


class InvertedIndex:
    """倒排索引"""
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.index_dir = os.path.join(data_path, 'indexes')
        self.index_file = os.path.join(self.index_dir, 'inverted_index.json')
        
        # keyword → set of turn_ids (支持 str 类型的 memory_id)
        self.index: Dict[str, Set[str]] = defaultdict(set)
        self._dirty_count = 0  # 脏计数，用于批量保存优化
        self._wal_file = os.path.join(self.index_dir, 'inverted_wal.jsonl')
        self._wal_count = 0
        self._compact_threshold = 10000
        
        self._load()
        
        import atexit
        atexit.register(self.flush)
    
    def _load(self):
        """加载索引"""
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for keyword, turns in data.items():
                    self.index[keyword] = set(turns)
        
        # WAL 重放
        if os.path.exists(self._wal_file):
            with open(self._wal_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        import logging
                        logging.getLogger(__name__).warning(f"WAL 行损坏已跳过: {line[:50]}")
                        continue
                    self.index[entry['k']].add(entry['t'])
                    self._wal_count += 1
    
    def _save(self):
        """增量 WAL 追加（替代全量 JSON dump）"""
        # 不再全量保存，由 _compact() 处理全量写入
        # 此方法现在是no-op，实际增量写入在 add/add_batch 中完成
        pass

    def _save_full(self):
        """全量保存（仅压缩时使用）"""
        os.makedirs(self.index_dir, exist_ok=True)
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump({k: list(v) for k, v in self.index.items()}, f, ensure_ascii=False)
    
    def add(self, keyword: str, turn_id: str):
        """添加索引项"""
        keyword = keyword.lower()
        self.index[keyword].add(turn_id)
        self._dirty_count += 1
        # WAL 追加
        os.makedirs(self.index_dir, exist_ok=True)
        with open(self._wal_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"k": keyword, "t": turn_id}, ensure_ascii=False) + '\n')
        self._wal_count += 1
        if self._wal_count >= self._compact_threshold:
            self._compact()
    
    def add_batch(self, keywords: List[str], turn_id: str):
        """批量添加"""
        os.makedirs(self.index_dir, exist_ok=True)
        with open(self._wal_file, 'a', encoding='utf-8') as f:
            for kw in keywords:
                kw_lower = kw.lower()
                self.index[kw_lower].add(turn_id)
                f.write(json.dumps({"k": kw_lower, "t": turn_id}, ensure_ascii=False) + '\n')
                self._wal_count += 1
        if self._wal_count >= self._compact_threshold:
            self._compact()
    
    def search(self, keyword: str) -> List[str]:
        """搜索包含关键词的轮次"""
        return list(self.index.get(keyword.lower(), set()))
    
    def search_all(self, keywords: List[str]) -> List[str]:
        """搜索包含所有关键词的轮次（AND逻辑）"""
        if not keywords:
            return []
        
        result_sets = [self.index.get(kw.lower(), set()) for kw in keywords]
        intersection = set.intersection(*result_sets) if result_sets else set()
        return list(intersection)
    
    def search_any(self, keywords: List[str]) -> List[str]:
        """搜索包含任一关键词的轮次（OR逻辑）"""
        result = set()
        for kw in keywords:
            result.update(self.index.get(kw.lower(), set()))
        return list(result)
    
    def _compact(self):
        """压缩：将内存状态全量写入主文件，删除 WAL"""
        tmp_file = self.index_file + '.tmp'
        os.makedirs(self.index_dir, exist_ok=True)
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump({k: list(v) for k, v in self.index.items()}, f, ensure_ascii=False)
        os.replace(tmp_file, self.index_file)
        if os.path.exists(self._wal_file):
            os.remove(self._wal_file)
        self._wal_count = 0

    def flush(self):
        """显式刷盘"""
        if self._wal_count > 0:
            self._compact()

    def clear(self):
        """清空倒排索引"""
        self.index.clear()
        self._dirty_count = 0
        self._wal_count = 0
        self._save_full()
        if os.path.exists(self._wal_file):
            os.remove(self._wal_file)
    
    def remove_by_memory_ids(self, memory_ids: Set[str]) -> int:
        """根据 memory_id 删除索引项
        
        Args:
            memory_ids: 要删除的 memory_id 集合
        
        Returns:
            int: 清理的索引项数量
        """
        removed_count = 0
        empty_keywords = []
        
        for keyword, turn_ids in self.index.items():
            before_size = len(turn_ids)
            turn_ids -= memory_ids  # Set 差集
            removed_count += before_size - len(turn_ids)
            if len(turn_ids) == 0:
                empty_keywords.append(keyword)
        
        # 删除空的关键词条目
        for kw in empty_keywords:
            del self.index[kw]
        
        if removed_count > 0:
            self._compact()
        
        return removed_count
