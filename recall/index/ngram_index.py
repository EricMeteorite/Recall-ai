"""优化的N-gram索引 - 避免空间爆炸"""

import re
from typing import List, Dict, Set


class OptimizedNgramIndex:
    """优化的N-gram索引 - 只索引名词短语，不做全文n-gram"""
    
    def __init__(self):
        # 只索引名词短语，不做全文n-gram
        self.noun_phrases: Dict[str, List[str]] = {}   # 名词短语 → [memory_ids]
        self._bloom_filter = None  # 可选的布隆过滤器
    
    @property
    def bloom_filter(self):
        """懒加载布隆过滤器"""
        if self._bloom_filter is None:
            try:
                from pybloom_live import BloomFilter
                self._bloom_filter = BloomFilter(capacity=1000000, error_rate=0.01)
            except ImportError:
                # 如果没有安装 pybloom_live，使用简单 set 替代
                self._bloom_filter = set()
        return self._bloom_filter
    
    def add(self, turn: str, content: str):
        """添加索引（只提取名词短语）
        
        Args:
            turn: memory_id（如 mem_xxx）
            content: 记忆内容
        """
        # 提取名词短语而非所有n-gram
        phrases = self._extract_noun_phrases(content)
        
        for phrase in phrases:
            # 添加到布隆过滤器
            if isinstance(self.bloom_filter, set):
                self.bloom_filter.add(phrase)
            else:
                self.bloom_filter.add(phrase)
            
            if phrase not in self.noun_phrases:
                self.noun_phrases[phrase] = []
            self.noun_phrases[phrase].append(turn)
    
    def _extract_noun_phrases(self, content: str) -> List[str]:
        """提取名词短语（而非所有n-gram）"""
        # 使用简单规则：2-4字的中文词组 + 英文单词
        chinese_phrases = re.findall(r'[\u4e00-\u9fa5]{2,4}', content)
        english_words = re.findall(r'[a-zA-Z]{3,}', content)
        
        # 过滤停用词
        stopwords = {
            '的', '了', '是', '在', '和', '有', '这', '那', 
            'the', 'a', 'is', 'are', 'to', 'and', 'of', 'in'
        }
        phrases = [p for p in chinese_phrases + english_words if p.lower() not in stopwords]
        
        return phrases
    
    def search(self, query: str) -> List[str]:
        """搜索
        
        Returns:
            List[str]: 匹配的 memory_id 列表
        """
        phrases = self._extract_noun_phrases(query)
        
        candidate_turns: Set[str] = set()
        for phrase in phrases:
            # 先用布隆过滤器快速排除
            if isinstance(self.bloom_filter, set):
                if phrase not in self.bloom_filter:
                    continue
            else:
                try:
                    if not self.bloom_filter.might_contain(phrase):
                        continue
                except AttributeError:
                    pass
            
            if phrase in self.noun_phrases:
                candidate_turns.update(self.noun_phrases[phrase])
        
        return list(candidate_turns)
