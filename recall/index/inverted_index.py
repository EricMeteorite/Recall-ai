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
        
        # keyword → set of turn_ids
        self.index: Dict[str, Set[int]] = defaultdict(set)
        self._dirty_count = 0  # 脏计数，用于批量保存优化
        
        self._load()
    
    def _load(self):
        """加载索引"""
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for keyword, turns in data.items():
                    self.index[keyword] = set(turns)
    
    def _save(self):
        """保存索引（增量）"""
        os.makedirs(self.index_dir, exist_ok=True)
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump({k: list(v) for k, v in self.index.items()}, f, ensure_ascii=False)
    
    def add(self, keyword: str, turn_id: int):
        """添加索引项"""
        keyword = keyword.lower()
        self.index[keyword].add(turn_id)
        self._dirty_count += 1
        # 批量保存优化：每100次添加保存一次
        if self._dirty_count >= 100:
            self._save()
            self._dirty_count = 0
    
    def add_batch(self, keywords: List[str], turn_id: int):
        """批量添加"""
        for kw in keywords:
            self.index[kw.lower()].add(turn_id)
        self._save()
    
    def search(self, keyword: str) -> List[int]:
        """搜索包含关键词的轮次"""
        return sorted(self.index.get(keyword.lower(), set()))
    
    def search_all(self, keywords: List[str]) -> List[int]:
        """搜索包含所有关键词的轮次（AND逻辑）"""
        if not keywords:
            return []
        
        result_sets = [self.index.get(kw.lower(), set()) for kw in keywords]
        intersection = set.intersection(*result_sets) if result_sets else set()
        return sorted(intersection)
    
    def search_any(self, keywords: List[str]) -> List[int]:
        """搜索包含任一关键词的轮次（OR逻辑）"""
        result = set()
        for kw in keywords:
            result.update(self.index.get(kw.lower(), set()))
        return sorted(result)
