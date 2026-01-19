"""优化的N-gram索引 - 支持名词短语索引 + 原文全文兜底搜索"""

import re
from typing import List, Dict, Set, Optional


class OptimizedNgramIndex:
    """优化的N-gram索引 - 名词短语索引 + 原文兜底
    
    设计原则（按计划十二点五"100%不遗忘"要求）：
    1. 主索引：只索引名词短语，避免空间爆炸
    2. 原文存储：保留完整原文，支持"终极兜底"搜索
    3. 两层搜索：先查名词短语索引，无结果时扫描原文
    """
    
    def __init__(self):
        # 主索引：名词短语 → [memory_ids]
        self.noun_phrases: Dict[str, List[str]] = {}
        
        # 原文存储：memory_id → content（用于兜底搜索）
        self._raw_content: Dict[str, str] = {}
        
        # 可选的布隆过滤器
        self._bloom_filter = None
    
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
        """添加索引（名词短语索引 + 原文存储）
        
        Args:
            turn: memory_id（如 mem_xxx）
            content: 记忆内容
        """
        # 1. 存储原文（用于兜底搜索）
        self._raw_content[turn] = content
        
        # 2. 提取并索引名词短语（主索引）
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
        """搜索（先查名词短语索引，无结果时原文兜底）
        
        Returns:
            List[str]: 匹配的 memory_id 列表
        """
        # 第一层：名词短语索引搜索
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
        
        if candidate_turns:
            return list(candidate_turns)
        
        # 第二层：原文兜底搜索（"终极兜底"，确保100%不遗忘）
        return self._raw_text_fallback_search(query)
    
    def _raw_text_fallback_search(self, query: str, max_results: int = 50) -> List[str]:
        """原文兜底搜索 - 扫描所有原文寻找包含查询子串的记忆
        
        这是"终极兜底"机制，确保即使名词短语索引未命中，
        只要原文中包含查询内容就能找到。
        
        Args:
            query: 搜索查询
            max_results: 最大返回数量（避免返回太多）
        
        Returns:
            List[str]: 匹配的 memory_id 列表
        """
        results = []
        query_lower = query.lower()
        
        # 提取查询中的关键子串（2-6字符）
        search_terms = self._extract_search_terms(query)
        
        for memory_id, content in self._raw_content.items():
            content_lower = content.lower()
            
            # 直接子串匹配
            if query_lower in content_lower:
                results.append(memory_id)
                continue
            
            # 检查任一关键子串是否匹配
            for term in search_terms:
                if term in content_lower:
                    results.append(memory_id)
                    break
            
            if len(results) >= max_results:
                break
        
        return results
    
    def _extract_search_terms(self, query: str) -> List[str]:
        """从查询中提取搜索词（用于兜底搜索）"""
        terms = []
        query_lower = query.lower()
        
        # 中文：2-6字符子串
        for length in [4, 3, 2, 5, 6]:
            for i in range(len(query) - length + 1):
                substr = query[i:i+length]
                if re.match(r'^[\u4e00-\u9fa5]+$', substr):
                    terms.append(substr.lower())
        
        # 英文：3-8字符单词
        english_words = re.findall(r'[a-zA-Z]{3,8}', query)
        terms.extend([w.lower() for w in english_words])
        
        return list(set(terms))[:10]  # 去重并限制数量
    
    def raw_search(self, query: str, max_results: int = 50) -> List[str]:
        """直接进行原文搜索（跳过名词短语索引）
        
        用于需要精确原文匹配的场景
        """
        return self._raw_text_fallback_search(query, max_results)
    
    def get_raw_content(self, memory_id: str) -> Optional[str]:
        """获取原文内容"""
        return self._raw_content.get(memory_id)
