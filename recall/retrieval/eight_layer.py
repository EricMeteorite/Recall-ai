"""八层漏斗检索架构"""

import time
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum


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
        llm_client: Optional[Any] = None,
        content_store: Optional[Callable[[str], Optional[str]]] = None
    ):
        self.bloom_filter = bloom_filter
        self.inverted_index = inverted_index
        self.entity_index = entity_index
        self.ngram_index = ngram_index
        self.vector_index = vector_index
        self.llm_client = llm_client
        # 内容存储回调：通过 ID 查询内容
        self.content_store = content_store
        
        # 内部内容缓存（用于索引时存储内容）
        self._content_cache: Dict[str, str] = {}
        
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
    
    def cache_content(self, doc_id: str, content: str):
        """缓存文档内容（在添加索引时调用）"""
        self._content_cache[doc_id] = content
    
    def get_content(self, doc_id: str) -> str:
        """获取文档内容"""
        # 优先从缓存获取
        if doc_id in self._content_cache:
            return self._content_cache[doc_id]
        # 否则从外部存储获取
        if self.content_store:
            content = self.content_store(doc_id)
            if content:
                return content
        return ""
    
    def retrieve(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        temporal_context: Optional[Any] = None,  # Phase 3 兼容：接受但忽略
        config: Optional[Any] = None  # Phase 3 兼容：接受但忽略
    ) -> List[RetrievalResult]:
        """执行八层检索
        
        Note: temporal_context 和 config 参数用于 Phase 3 兼容，
        在 EightLayerRetriever 中被忽略，仅 ElevenLayerRetriever 使用。
        """
        self.stats = []
        candidates: Set[str] = set()  # 候选ID集合
        results: List[RetrievalResult] = []
        
        # L1: 布隆过滤器（预过滤关键词）
        filtered_keywords = keywords or []
        if self.config['l1_enabled'] and self.bloom_filter and keywords:
            start = time.time()
            # 布隆过滤器用于快速排除不存在的关键词
            # 使用 in 运算符检查（BloomFilter 实现了 __contains__）
            filtered_keywords = [
                kw for kw in keywords 
                if kw in self.bloom_filter
            ]
            self._record_stats(RetrievalLayer.L1_BLOOM_FILTER, len(keywords), len(filtered_keywords), start)
        
        # L2: 倒排索引
        if self.config['l2_enabled'] and self.inverted_index:
            start = time.time()
            input_count = len(candidates)
            
            # 使用过滤后的关键词（如果L1启用）或原始关键词
            search_keywords = filtered_keywords if filtered_keywords else keywords
            if search_keywords:
                # 使用 search_any 来搜索任一关键词
                inverted_results = self.inverted_index.search_any(search_keywords)
                candidates.update(inverted_results)
            
            self._record_stats(RetrievalLayer.L2_INVERTED_INDEX, input_count, len(candidates), start)
        
        # L3: 实体索引
        if self.config['l3_enabled'] and self.entity_index and entities:
            start = time.time()
            input_count = len(candidates)
            
            for entity in entities:
                entity_results = self.entity_index.get_related_turns(entity)
                # entity_results 是 IndexedEntity 列表，需要提取 turn_references
                for indexed_entity in entity_results:
                    candidates.update(indexed_entity.turn_references)
            
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
        # 检查向量索引是否存在且启用（支持 Lite 模式）
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
                # 获取实际内容
                content = self.get_content(doc_id)
                results.append(RetrievalResult(
                    id=doc_id,
                    content=content,
                    score=score,
                    source_layer=RetrievalLayer.L5_VECTOR_COARSE
                ))
            
            self._record_stats(RetrievalLayer.L5_VECTOR_COARSE, input_count, len(results), start)
        
        # 关键：将 L2-L4 收集的候选 ID 也转换为结果
        # 这确保了 Lite 模式（无向量索引）也能返回结果
        seen_ids = {r.id for r in results}
        for doc_id in candidates:
            if doc_id not in seen_ids:
                content = self.get_content(doc_id)
                if content:  # 只添加有内容的结果
                    results.append(RetrievalResult(
                        id=doc_id,
                        content=content,
                        score=0.5,  # 关键词/实体匹配的基础分数
                        source_layer=RetrievalLayer.L4_NGRAM_INDEX
                    ))
                    seen_ids.add(doc_id)
        
        # L6: 向量精排（完整实现 - 重新计算精确向量距离）
        if self.config['l6_enabled'] and vector_enabled and results:
            start = time.time()
            input_count = len(results)
            
            # 完整实现：重新计算查询与候选文档的精确余弦相似度
            results = self._vector_fine_ranking(query, results)
            results = results[:self.config['l6_top_k']]
            
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
        
        # 终极兜底：如果所有层都没找到结果，使用 N-gram 原文搜索
        # 这确保了"100%不遗忘"——只要原文中包含查询内容就能找到
        if not results and self.ngram_index:
            start = time.time()
            # 调用 raw_search 直接搜索原文
            if hasattr(self.ngram_index, 'raw_search'):
                fallback_ids = self.ngram_index.raw_search(query, max_results=top_k)
            else:
                fallback_ids = self.ngram_index.search(query)
            
            for doc_id in fallback_ids[:top_k]:
                content = self.get_content(doc_id)
                if content:
                    results.append(RetrievalResult(
                        id=doc_id,
                        content=content,
                        score=0.3,  # 兜底搜索的基础分数
                        source_layer=RetrievalLayer.L4_NGRAM_INDEX,
                        metadata={'fallback': True}  # 标记为兜底结果
                    ))
            
            if results:
                self._record_stats(RetrievalLayer.L4_NGRAM_INDEX, 0, len(results), start)
        
        return results[:top_k]
    
    def _vector_fine_ranking(
        self,
        query: str,
        results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """L6 向量精排 - 使用已存储的向量计算精确相似度
        
        优化：直接从 FAISS 索引获取已存储的文档向量，
        避免重复调用 encode() API（这会消耗大量配额）。
        
        Args:
            query: 查询文本
            results: L5 粗筛后的候选结果
        
        Returns:
            按精确相似度重新排序的结果
        """
        if not self.vector_index or not results:
            # 没有向量索引，回退到简单排序
            return sorted(results, key=lambda r: -r.score)
        
        try:
            import numpy as np
            
            # 1. 获取查询向量（只需要编码一次）
            query_embedding = self.vector_index.encode(query)
            query_embedding = query_embedding / np.linalg.norm(query_embedding)  # 归一化
            
            # 2. 批量获取候选文档的已存储向量（不调用 API！）
            doc_ids = [r.id for r in results]
            stored_vectors = {}
            if hasattr(self.vector_index, 'get_vectors_by_doc_ids'):
                stored_vectors = self.vector_index.get_vectors_by_doc_ids(doc_ids)
            
            # 3. 对每个候选文档计算精确相似度
            for result in results:
                doc_id = result.id
                
                # 优先使用已存储的向量
                if doc_id in stored_vectors:
                    doc_embedding = stored_vectors[doc_id]
                    doc_embedding = doc_embedding / np.linalg.norm(doc_embedding)  # 归一化
                    
                    # 计算余弦相似度
                    cosine_sim = float(np.dot(query_embedding, doc_embedding))
                    
                    # 更新分数
                    result.score = 0.7 * cosine_sim + 0.3 * result.score
                    result.metadata['l6_cosine_sim'] = cosine_sim
                    result.metadata['l6_source'] = 'stored_vector'
                else:
                    # 没有存储的向量（可能是旧数据），保持原分数
                    result.metadata['l6_source'] = 'no_vector'
            
            # 4. 按新分数排序
            return sorted(results, key=lambda r: -r.score)
            
        except Exception as e:
            # 整体失败，回退到简单排序
            _safe_print(f"[EightLayerRetriever] L6 精排失败，回退到简单排序: {e}")
            return sorted(results, key=lambda r: -r.score)
    
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
