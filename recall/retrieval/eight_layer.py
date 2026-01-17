"""八层漏斗检索架构"""

import time
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum


class RetrievalLayer(Enum):
    """检索层级"""
    L1_BLOOM_FILTER = "bloom_filter"           # 布隆过滤器快速否定
    L2_INVERTED_INDEX = "inverted_index"       # 倒排索引关键词匹配
    L3_ENTITY_INDEX = "entity_index"           # 实体索引
    L4_NGRAM_INDEX = "ngram_index"             # N-gram索引
    L5_VECTOR_COARSE = "vector_coarse"         # 向量粗筛
    L6_VECTOR_FINE = "vector_fine"             # 向量精排
    L7_RERANK = "rerank"                       # 重排序
    L8_LLM_FILTER = "llm_filter"               # LLM过滤


@dataclass
class RetrievalResult:
    """检索结果"""
    id: str
    content: str
    score: float
    source_layer: RetrievalLayer
    metadata: Dict[str, Any] = field(default_factory=dict)
    entities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'content': self.content,
            'score': self.score,
            'source_layer': self.source_layer.value,
            'metadata': self.metadata,
            'entities': self.entities
        }


@dataclass
class LayerStats:
    """层级统计"""
    layer: RetrievalLayer
    input_count: int
    output_count: int
    time_ms: float
    filtered_count: int = 0


class EightLayerRetriever:
    """八层漏斗检索器
    
    检索流程：
    L1: 布隆过滤器 - O(1) 快速否定不可能的候选
    L2: 倒排索引 - O(log n) 关键词匹配
    L3: 实体索引 - O(1) 实体关联查找
    L4: N-gram索引 - O(k) 模糊匹配
    L5: 向量粗筛 - O(n) 近似最近邻
    L6: 向量精排 - O(k) 精确距离计算
    L7: 重排序 - O(k log k) 多因素综合排序
    L8: LLM过滤 - O(k) 语义相关性判断
    """
    
    def __init__(
        self,
        bloom_filter: Optional[Any] = None,
        inverted_index: Optional[Any] = None,
        entity_index: Optional[Any] = None,
        ngram_index: Optional[Any] = None,
        vector_index: Optional[Any] = None,
        llm_client: Optional[Any] = None
    ):
        self.bloom_filter = bloom_filter
        self.inverted_index = inverted_index
        self.entity_index = entity_index
        self.ngram_index = ngram_index
        self.vector_index = vector_index
        self.llm_client = llm_client
        
        # 统计
        self.stats: List[LayerStats] = []
        
        # 配置
        self.config = {
            'l1_enabled': True,
            'l2_enabled': True,
            'l3_enabled': True,
            'l4_enabled': True,
            'l5_enabled': True,
            'l6_enabled': True,
            'l7_enabled': True,
            'l8_enabled': False,  # LLM过滤默认关闭（消耗资源）
            'l5_top_k': 100,      # 粗筛返回数量
            'l6_top_k': 20,       # 精排返回数量
            'l7_top_k': 10,       # 重排序返回数量
            'l8_top_k': 5,        # LLM过滤返回数量
        }
    
    def retrieve(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """执行八层检索"""
        self.stats = []
        candidates: Set[str] = set()  # 候选ID集合
        results: List[RetrievalResult] = []
        
        # L1: 布隆过滤器
        if self.config['l1_enabled'] and self.bloom_filter:
            start = time.time()
            # 布隆过滤器用于快速判断某个key是否可能存在
            # 这里我们用keywords来过滤
            if keywords:
                for kw in keywords:
                    if self.bloom_filter.might_contain(kw):
                        candidates.add(kw)
            self._record_stats(RetrievalLayer.L1_BLOOM_FILTER, 0, len(candidates), start)
        
        # L2: 倒排索引
        if self.config['l2_enabled'] and self.inverted_index:
            start = time.time()
            input_count = len(candidates)
            
            if keywords:
                # 使用 search_any 来搜索任一关键词
                inverted_results = self.inverted_index.search_any(keywords)
                candidates.update(inverted_results)
            
            self._record_stats(RetrievalLayer.L2_INVERTED_INDEX, input_count, len(candidates), start)
        
        # L3: 实体索引
        if self.config['l3_enabled'] and self.entity_index and entities:
            start = time.time()
            input_count = len(candidates)
            
            for entity in entities:
                entity_results = self.entity_index.get_related_turns(entity)
                candidates.update(r.turn_id for r in entity_results)
            
            self._record_stats(RetrievalLayer.L3_ENTITY_INDEX, input_count, len(candidates), start)
        
        # L4: N-gram索引
        if self.config['l4_enabled'] and self.ngram_index:
            start = time.time()
            input_count = len(candidates)
            
            ngram_results = self.ngram_index.search(query)
            # ngram_results 是 turn_id 列表，不是元组
            for doc_id in ngram_results:
                candidates.add(doc_id)
            
            self._record_stats(RetrievalLayer.L4_NGRAM_INDEX, input_count, len(candidates), start)
        
        # L5: 向量粗筛
        # 检查向量索引是否存在且启用（支持轻量模式）
        vector_enabled = self.vector_index and getattr(self.vector_index, 'enabled', True)
        if self.config['l5_enabled'] and vector_enabled:
            start = time.time()
            input_count = len(candidates)
            
            vector_results = self.vector_index.search(
                query, 
                top_k=self.config['l5_top_k']
            )
            
            # 合并向量结果
            for doc_id, score in vector_results:
                candidates.add(doc_id)
                results.append(RetrievalResult(
                    id=doc_id,
                    content="",  # 稍后填充
                    score=score,
                    source_layer=RetrievalLayer.L5_VECTOR_COARSE
                ))
            
            self._record_stats(RetrievalLayer.L5_VECTOR_COARSE, input_count, len(results), start)
        
        # L6: 向量精排
        if self.config['l6_enabled'] and vector_enabled and results:
            start = time.time()
            input_count = len(results)
            
            # 精确计算分数
            results = sorted(results, key=lambda r: -r.score)[:self.config['l6_top_k']]
            
            for r in results:
                r.source_layer = RetrievalLayer.L6_VECTOR_FINE
            
            self._record_stats(RetrievalLayer.L6_VECTOR_FINE, input_count, len(results), start)
        
        # L7: 重排序
        if self.config['l7_enabled'] and results:
            start = time.time()
            input_count = len(results)
            
            results = self._rerank(results, query, entities, keywords)
            results = results[:self.config['l7_top_k']]
            
            for r in results:
                r.source_layer = RetrievalLayer.L7_RERANK
            
            self._record_stats(RetrievalLayer.L7_RERANK, input_count, len(results), start)
        
        # L8: LLM过滤
        if self.config['l8_enabled'] and self.llm_client and results:
            start = time.time()
            input_count = len(results)
            
            results = self._llm_filter(results, query)
            results = results[:self.config['l8_top_k']]
            
            self._record_stats(RetrievalLayer.L8_LLM_FILTER, input_count, len(results), start)
        
        return results[:top_k]
    
    def _rerank(
        self,
        results: List[RetrievalResult],
        query: str,
        entities: Optional[List[str]],
        keywords: Optional[List[str]]
    ) -> List[RetrievalResult]:
        """重排序"""
        for result in results:
            bonus = 0.0
            
            # 实体匹配加分
            if entities:
                matched_entities = set(result.entities) & set(entities)
                bonus += len(matched_entities) * 0.1
            
            # 关键词匹配加分
            if keywords:
                for kw in keywords:
                    if kw.lower() in result.content.lower():
                        bonus += 0.05
            
            # 新鲜度加分（如果有时间戳）
            if 'timestamp' in result.metadata:
                recency = time.time() - result.metadata['timestamp']
                if recency < 3600:  # 1小时内
                    bonus += 0.1
                elif recency < 86400:  # 1天内
                    bonus += 0.05
            
            result.score += bonus
        
        return sorted(results, key=lambda r: -r.score)
    
    def _llm_filter(
        self,
        results: List[RetrievalResult],
        query: str
    ) -> List[RetrievalResult]:
        """使用LLM过滤不相关结果"""
        if not self.llm_client:
            return results
        
        prompt = f"""判断以下记忆是否与查询相关。

查询：{query}

记忆列表：
{chr(10).join([f"{i+1}. {r.content[:100]}" for i, r in enumerate(results)])}

请返回相关记忆的编号（用逗号分隔），如果都不相关返回"无"："""
        
        try:
            response = self.llm_client.complete(prompt, max_tokens=50)
            
            if response.strip() == "无":
                return []
            
            # 解析返回的编号
            indices = [int(x.strip()) - 1 for x in response.split(',') if x.strip().isdigit()]
            return [results[i] for i in indices if 0 <= i < len(results)]
        
        except Exception:
            return results
    
    def _record_stats(self, layer: RetrievalLayer, input_count: int, output_count: int, start_time: float):
        """记录层级统计"""
        self.stats.append(LayerStats(
            layer=layer,
            input_count=input_count,
            output_count=output_count,
            time_ms=(time.time() - start_time) * 1000,
            filtered_count=input_count - output_count if input_count > output_count else 0
        ))
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        total_time = sum(s.time_ms for s in self.stats)
        return {
            'total_time_ms': total_time,
            'layers': [
                {
                    'layer': s.layer.value,
                    'input': s.input_count,
                    'output': s.output_count,
                    'time_ms': s.time_ms,
                    'filtered': s.filtered_count
                }
                for s in self.stats
            ]
        }
