"""全文索引 - BM25 实现

设计理念：
1. 纯 Python 实现 BM25 算法，零外部依赖
2. 支持中英文混合文本
3. 与现有 InvertedIndex 互补（InvertedIndex 是精确匹配，这是相关性排序）
4. 增量更新，无需重建整个索引
"""

from __future__ import annotations

import os
import json
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict, Counter


@dataclass
class BM25Config:
    """BM25 参数配置"""
    k1: float = 1.5     # 词频饱和参数（1.2-2.0）
    b: float = 0.75     # 文档长度归一化参数（0-1）
    delta: float = 0.0  # BM25+ 的 delta 参数（0 表示经典 BM25）


class FullTextIndex:
    """全文索引 - BM25 实现
    
    特点：
    1. 支持中英文混合分词
    2. 增量更新
    3. 可配置的 BM25 参数
    4. 支持字段权重（可选）
    
    使用方式：
        index = FullTextIndex(data_path)
        index.add('doc1', '这是一段测试文本')
        results = index.search('测试', top_k=10)
    """
    
    def __init__(
        self,
        data_path: str,
        config: Optional[BM25Config] = None
    ):
        """初始化全文索引
        
        Args:
            data_path: 数据存储路径
            config: BM25 参数配置
        """
        self.data_path = data_path
        self.index_dir = os.path.join(data_path, 'indexes')
        self.index_file = os.path.join(self.index_dir, 'fulltext_index.json')
        
        self.config = config or BM25Config()
        
        # 核心数据结构
        self.doc_count = 0                                    # 文档总数
        self.avg_doc_length = 0.0                            # 平均文档长度
        self.total_doc_length = 0                            # 总文档长度
        
        # 倒排索引: term -> {doc_id -> term_frequency}
        self.inverted_index: Dict[str, Dict[str, int]] = defaultdict(dict)
        
        # 文档信息: doc_id -> {length, terms}
        self.doc_info: Dict[str, Dict[str, Any]] = {}
        
        # 文档频率: term -> 包含该词的文档数
        self.doc_freq: Dict[str, int] = defaultdict(int)
        
        # 停用词
        self.stopwords: Set[str] = self._default_stopwords()
        
        # 脏标记
        self._dirty = False
        
        # 加载
        self._load()
    
    def _default_stopwords(self) -> Set[str]:
        """默认停用词"""
        return {
            # 中文停用词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
            '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
            '自己', '这', '那', '啊', '吧', '吗', '呢', '哦', '嗯', '啦',
            # 英文停用词
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who',
            'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few',
            'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
            'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and', 'but', 'or',
            'as', 'if', 'then', 'else', 'for', 'of', 'at', 'by', 'from', 'to', 'in',
            'on', 'with', 'about', 'against', 'between', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over',
        }
    
    def _load(self):
        """加载索引"""
        if not os.path.exists(self.index_file):
            return
        
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.doc_count = data.get('doc_count', 0)
            self.avg_doc_length = data.get('avg_doc_length', 0.0)
            self.total_doc_length = data.get('total_doc_length', 0)
            self.inverted_index = defaultdict(dict, data.get('inverted_index', {}))
            self.doc_info = data.get('doc_info', {})
            self.doc_freq = defaultdict(int, data.get('doc_freq', {}))
            
            # 恢复配置
            if 'config' in data:
                cfg = data['config']
                self.config = BM25Config(
                    k1=cfg.get('k1', 1.5),
                    b=cfg.get('b', 0.75),
                    delta=cfg.get('delta', 0.0)
                )
            
        except Exception as e:
            print(f"[FullTextIndex] 加载索引失败: {e}")
    
    def _save(self):
        """保存索引"""
        if not self._dirty:
            return
        
        os.makedirs(self.index_dir, exist_ok=True)
        
        data = {
            'version': '4.0',
            'doc_count': self.doc_count,
            'avg_doc_length': self.avg_doc_length,
            'total_doc_length': self.total_doc_length,
            'inverted_index': dict(self.inverted_index),
            'doc_info': self.doc_info,
            'doc_freq': dict(self.doc_freq),
            'config': {
                'k1': self.config.k1,
                'b': self.config.b,
                'delta': self.config.delta
            }
        }
        
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        
        self._dirty = False
    
    def tokenize(self, text: str) -> List[str]:
        """分词
        
        策略：
        1. 英文按空格和标点分词
        2. 中文按字符分词（简单但有效）
        3. 过滤停用词和单字符
        """
        tokens = []
        
        # 转小写
        text = text.lower()
        
        # 分离中英文
        # 英文单词
        english_words = re.findall(r'[a-z]+', text)
        tokens.extend(w for w in english_words if len(w) > 1 and w not in self.stopwords)
        
        # 中文（提取连续中文，然后按2-gram切分）
        chinese_segments = re.findall(r'[\u4e00-\u9fff]+', text)
        for segment in chinese_segments:
            if len(segment) >= 2:
                # 保留完整词
                if segment not in self.stopwords:
                    tokens.append(segment)
                # 2-gram
                for i in range(len(segment) - 1):
                    bigram = segment[i:i+2]
                    if bigram not in self.stopwords:
                        tokens.append(bigram)
        
        return tokens
    
    def add(self, doc_id: str, text: str):
        """添加文档
        
        Args:
            doc_id: 文档ID
            text: 文档文本
        """
        # 如果已存在，先移除
        if doc_id in self.doc_info:
            self.remove(doc_id)
        
        # 分词
        tokens = self.tokenize(text)
        if not tokens:
            return
        
        # 词频统计
        term_freq = Counter(tokens)
        doc_length = len(tokens)
        
        # 更新倒排索引
        for term, freq in term_freq.items():
            self.inverted_index[term][doc_id] = freq
            
            # 更新文档频率（只在新词时增加）
            if len(self.inverted_index[term]) == 1 or doc_id not in self.inverted_index[term]:
                pass  # 已在上面添加
            # 首次添加该词到该文档
            if doc_id not in self.doc_info or term not in self.doc_info.get(doc_id, {}).get('terms', []):
                self.doc_freq[term] += 1
        
        # 修正：直接设置文档频率
        for term in term_freq:
            self.doc_freq[term] = len(self.inverted_index[term])
        
        # 保存文档信息
        self.doc_info[doc_id] = {
            'length': doc_length,
            'terms': list(term_freq.keys())
        }
        
        # 更新统计
        self.doc_count += 1
        self.total_doc_length += doc_length
        self.avg_doc_length = self.total_doc_length / self.doc_count if self.doc_count > 0 else 0
        
        self._dirty = True
    
    def remove(self, doc_id: str) -> bool:
        """移除文档
        
        Args:
            doc_id: 文档ID
        
        Returns:
            是否成功移除
        """
        if doc_id not in self.doc_info:
            return False
        
        info = self.doc_info[doc_id]
        
        # 从倒排索引移除
        for term in info['terms']:
            if term in self.inverted_index and doc_id in self.inverted_index[term]:
                del self.inverted_index[term][doc_id]
                
                # 更新文档频率
                self.doc_freq[term] = len(self.inverted_index[term])
                
                # 如果该词不再有文档，移除
                if not self.inverted_index[term]:
                    del self.inverted_index[term]
                    del self.doc_freq[term]
        
        # 更新统计
        self.doc_count -= 1
        self.total_doc_length -= info['length']
        self.avg_doc_length = self.total_doc_length / self.doc_count if self.doc_count > 0 else 0
        
        # 移除文档信息
        del self.doc_info[doc_id]
        
        self._dirty = True
        return True
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0
    ) -> List[Tuple[str, float]]:
        """搜索文档
        
        Args:
            query: 查询文本
            top_k: 返回数量
            min_score: 最小分数阈值
        
        Returns:
            [(doc_id, score), ...] 按分数降序
        """
        if self.doc_count == 0:
            return []
        
        # 分词
        query_terms = self.tokenize(query)
        if not query_terms:
            return []
        
        # 计算每个文档的 BM25 分数
        scores: Dict[str, float] = defaultdict(float)
        
        for term in query_terms:
            if term not in self.inverted_index:
                continue
            
            # IDF
            df = self.doc_freq.get(term, 0)
            if df == 0:
                continue
            
            idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)
            
            # 遍历包含该词的文档
            for doc_id, tf in self.inverted_index[term].items():
                doc_length = self.doc_info[doc_id]['length']
                
                # BM25 公式
                numerator = tf * (self.config.k1 + 1)
                denominator = tf + self.config.k1 * (
                    1 - self.config.b + self.config.b * doc_length / self.avg_doc_length
                )
                
                score = idf * numerator / denominator
                
                # BM25+ 修正
                if self.config.delta > 0:
                    score += self.config.delta
                
                scores[doc_id] += score
        
        # 排序并过滤
        results = [
            (doc_id, score) 
            for doc_id, score in scores.items() 
            if score >= min_score
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_k]
    
    def search_with_weights(
        self,
        query: str,
        field_weights: Dict[str, float] = None,
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """带字段权重的搜索（预留接口）
        
        Args:
            query: 查询文本
            field_weights: 字段权重 {'title': 2.0, 'content': 1.0}
            top_k: 返回数量
        
        Returns:
            [(doc_id, score), ...]
        """
        # 当前简化实现，直接调用 search
        # 未来可以扩展支持多字段索引
        return self.search(query, top_k)
    
    def flush(self):
        """强制保存"""
        self._dirty = True
        self._save()
    
    def count(self) -> int:
        """返回文档总数"""
        return self.doc_count
    
    def get_terms(self, doc_id: str) -> List[str]:
        """获取文档的词项"""
        info = self.doc_info.get(doc_id)
        return info['terms'] if info else []
    
    def get_doc_length(self, doc_id: str) -> int:
        """获取文档长度"""
        info = self.doc_info.get(doc_id)
        return info['length'] if info else 0
    
    def clear(self):
        """清空索引"""
        self.doc_count = 0
        self.avg_doc_length = 0.0
        self.total_doc_length = 0
        self.inverted_index.clear()
        self.doc_info.clear()
        self.doc_freq.clear()
        self._dirty = True
        self._save()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            'doc_count': self.doc_count,
            'avg_doc_length': self.avg_doc_length,
            'total_doc_length': self.total_doc_length,
            'vocabulary_size': len(self.inverted_index),
            'config': {
                'k1': self.config.k1,
                'b': self.config.b,
                'delta': self.config.delta
            }
        }


__all__ = [
    'BM25Config',
    'FullTextIndex',
]
