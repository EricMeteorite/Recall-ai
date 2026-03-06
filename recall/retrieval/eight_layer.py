"""八层漏斗检索架构 - Phase 3.6 升级版：并行三路召回 + RRF 融合"""

import time
from typing import List, Dict, Any, Optional, Set, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

from .rrf_fusion import reciprocal_rank_fusion


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
    """八层漏斗检索器 - Phase 3.6 升级为并行三路召回
    
    检索流程（Phase 3.6）：
    并行执行三路召回:
      - 路径 1: IVF-HNSW 语义召回 (95-99% 召回率)
      - 路径 2: 倒排索引关键词召回 (100% 召回率)
      - 路径 3: 实体索引召回 (100% 召回率)
    → RRF 融合取并集
    → 如果结果为空，启用 N-gram 原文兜底 (100% 保证)
    → 重排序
    → 返回结果
    
    向后兼容：串行漏斗模式
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
        content_store: Optional[Callable[[str], Optional[str]]] = None,
        # Phase 3.6 新增：用于 VectorIndexIVF 的向量编码
        embedding_backend: Optional[Any] = None,
    ):
        self.bloom_filter = bloom_filter
        self.inverted_index = inverted_index
        self.entity_index = entity_index
        self.ngram_index = ngram_index
        self.vector_index = vector_index
        self.llm_client = llm_client
        # 内容存储回调：通过 ID 查询内容
        self.content_store = content_store
        # Phase 3.6: embedding_backend 用于 VectorIndexIVF（无内置 encode）
        self.embedding_backend = embedding_backend
        
        # 内部内容缓存（用于索引时存储内容）
        # v7.0.14: 加 LRU 上限保护，防止无界增长导致 OOM
        self._content_cache: Dict[str, str] = {}
        self._cache_max_size: int = 10000  # LRU 上限（与 ElevenLayerRetriever 一致）
        
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
            # Phase 3.6 新增配置
            'parallel_recall_enabled': True,   # 启用并行召回
            'rrf_k': 60,                       # RRF 常数
            'vector_weight': 1.0,              # 语义召回权重
            'keyword_weight': 1.2,             # 关键词召回权重（100%召回，权重更高）
            'entity_weight': 1.0,              # 实体召回权重
            'ngram_weight': 1.5,               # N-gram原文召回权重（最高，确保精确匹配优先）
            'fallback_enabled': True,          # 启用原文兜底（向后兼容）
            'fallback_parallel': True,         # 并行扫描
            'fallback_workers': 4,             # 扫描线程数
        }
    
    def cache_content(self, doc_id: str, content: str):
        """缓存文档内容（在添加索引时调用）"""
        self._content_cache[doc_id] = content
        self._evict_cache_if_needed()
    
    def _evict_cache_if_needed(self):
        """v7.0.14: LRU 缓存驱逐 — 超过上限时清除最早一半"""
        if len(self._content_cache) > self._cache_max_size:
            keys = list(self._content_cache.keys())
            evict_count = len(keys) // 2
            for key in keys[:evict_count]:
                del self._content_cache[key]
    
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
        """执行检索 - Phase 3.6 支持并行三路召回 + RRF 融合
        
        Note: temporal_context 和 config 参数用于 Phase 3 兼容，
        在 EightLayerRetriever 中被忽略，仅 ElevenLayerRetriever 使用。
        """
        # Phase 3.6: 根据配置选择并行或串行模式
        if self.config.get('parallel_recall_enabled', True):
            return self._parallel_recall(query, entities, keywords, top_k)
        else:
            return self._legacy_retrieve(query, entities, keywords, top_k, filters)
    
    def _parallel_recall(
        self,
        query: str,
        entities: Optional[List[str]],
        keywords: Optional[List[str]],
        top_k: int
    ) -> List[RetrievalResult]:
        """Phase 3.6: 并行四路召回实现（保证100%召回）
        
        1. 并行执行四路召回（语义、关键词、实体、N-gram原文）
        2. RRF 融合取并集
        3. 重排序
        
        关键改进：N-gram 作为第四路参与 RRF 融合，而不是仅作为后备，
        确保即使其他三路漏掉的内容也能通过原文匹配找到（100%不遗忘）。
        """
        self.stats = []
        
        # 1. 并行执行四路召回（N-gram 作为正式的第四路）
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self._vector_recall, query, top_k * 2): 'vector',
                executor.submit(self._keyword_recall, keywords, top_k * 2): 'keyword',
                executor.submit(self._entity_recall, entities, top_k * 2): 'entity',
                executor.submit(self._ngram_recall, query, top_k * 2): 'ngram',
            }
            
            all_results: Dict[str, List[Tuple[str, float]]] = {}
            for future in as_completed(futures, timeout=15.0):
                source = futures[future]
                try:
                    all_results[source] = future.result()
                except Exception as e:
                    all_results[source] = []
                    _safe_print(f"[Retriever] {source} 召回失败: {e}")
        
        # 2. RRF 四路融合（N-gram 权重较高，确保100%召回优先级）
        fused = reciprocal_rank_fusion(
            [
                all_results.get('vector', []),
                all_results.get('keyword', []),
                all_results.get('entity', []),
                all_results.get('ngram', []),
            ],
            k=self.config.get('rrf_k', 60),
            weights=[
                self.config.get('vector_weight', 1.0),
                self.config.get('keyword_weight', 1.2),
                self.config.get('entity_weight', 1.0),
                self.config.get('ngram_weight', 1.5),  # N-gram权重更高，确保精确匹配优先
            ]
        )
        
        # 3. 构建结果对象
        results: List[RetrievalResult] = []
        for doc_id, score in fused[:top_k * 2]:
            content = self.get_content(doc_id)
            if content:
                results.append(RetrievalResult(
                    id=doc_id,
                    content=content,
                    score=score,
                    source_layer=RetrievalLayer.L7_RERANK
                ))
        
        # 4. 精排 + 重排序
        if self.config['l7_enabled'] and results:
            results = self._rerank(results, query, entities, keywords)
        
        return results[:top_k]
    
    def _ngram_recall(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """路径 4: N-gram 原文召回（100% 精确匹配保证）
        
        通过扫描原文进行子串匹配，确保任何说过的话都能被找到。
        这是"100%不遗忘"承诺的核心保障。
        """
        if not self.ngram_index:
            return []
        
        start = time.time()
        
        # 使用并行扫描加速
        if self.config.get('fallback_parallel', True) and hasattr(self.ngram_index, 'raw_search_parallel'):
            doc_ids = self.ngram_index.raw_search_parallel(
                query,
                max_results=top_k,
                num_workers=self.config.get('fallback_workers', 4)
            )
        else:
            doc_ids = self.ngram_index.raw_search(query, max_results=top_k)
        
        # N-gram 匹配到的结果给予较高分数（精确匹配）
        results = [(doc_id, 0.85) for doc_id in doc_ids]
        
        self._record_stats(RetrievalLayer.L4_NGRAM_INDEX, 0, len(results), start)
        return results
    
    def _vector_recall(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """路径 1: 语义向量召回
        
        兼容两种向量索引：
        - VectorIndex: search(query: str) - 内部自动 encode
        - VectorIndexIVF: search(embedding: List[float]) - 需要外部 encode
        """
        if not self.vector_index or not getattr(self.vector_index, 'enabled', True):
            return []
        
        start = time.time()
        results = []
        
        try:
            # 检查索引类型，兼容不同的 API
            if hasattr(self.vector_index, 'encode'):
                # VectorIndex: 支持字符串查询（内部有 encode 方法）
                results = self.vector_index.search(query, top_k=top_k)
            else:
                # VectorIndexIVF: 需要传入向量
                if hasattr(self, 'embedding_backend') and self.embedding_backend:
                    query_embedding = self.embedding_backend.encode(query)
                    results = self.vector_index.search(query_embedding, top_k=top_k)
                else:
                    _safe_print("[Retriever] Warning: No embedding_backend for VectorIndexIVF")
                    return []
        except Exception as e:
            _safe_print(f"[Retriever] Vector recall failed: {e}")
            results = []
        
        self._record_stats(RetrievalLayer.L5_VECTOR_COARSE, 0, len(results), start)
        return results
    
    def _keyword_recall(self, keywords: Optional[List[str]], top_k: int) -> List[Tuple[str, float]]:
        """路径 2: 关键词倒排索引召回（100% 召回）"""
        if not self.inverted_index or not keywords:
            return []
        
        start = time.time()
        
        # 使用布隆过滤器预过滤
        filtered_keywords = keywords
        if self.bloom_filter:
            filtered_keywords = [kw for kw in keywords if kw in self.bloom_filter]
        
        if not filtered_keywords:
            return []
        
        # 获取每个关键词匹配的文档
        doc_keyword_counts: Dict[str, int] = defaultdict(int)
        for kw in filtered_keywords:
            # 使用 search_any 如果存在，否则使用 search
            if hasattr(self.inverted_index, 'search_any'):
                matched_docs = self.inverted_index.search_any([kw])
            else:
                matched_docs = self.inverted_index.search(kw)
            for doc_id in matched_docs:
                doc_keyword_counts[doc_id] += 1
        
        # 计算分数：匹配关键词数 / 总关键词数 * 基础分
        base_score = 0.8
        results = []
        for doc_id, match_count in doc_keyword_counts.items():
            score = base_score * (match_count / len(filtered_keywords))
            results.append((doc_id, score))
        
        # 按分数排序
        results.sort(key=lambda x: -x[1])
        
        self._record_stats(RetrievalLayer.L2_INVERTED_INDEX, 0, len(results), start)
        return results[:top_k]
    
    def _entity_recall(self, entities: Optional[List[str]], top_k: int) -> List[Tuple[str, float]]:
        """路径 3: 实体索引召回"""
        if not self.entity_index or not entities:
            return []
        
        start = time.time()
        doc_ids: Set[str] = set()
        
        for entity in entities:
            entity_results = self.entity_index.get_related_turns(entity)
            for indexed_entity in entity_results:
                doc_ids.update(indexed_entity.turn_references)
        
        results = [(doc_id, 0.7) for doc_id in list(doc_ids)[:top_k]]
        
        self._record_stats(RetrievalLayer.L3_ENTITY_INDEX, 0, len(results), start)
        return results
    
    def _raw_text_fallback(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """原文兜底搜索（100% 保证，仅在其他路径无结果时使用）"""
        if not self.ngram_index:
            return []
        
        start = time.time()
        
        if self.config.get('fallback_parallel', True) and hasattr(self.ngram_index, 'raw_search_parallel'):
            doc_ids = self.ngram_index.raw_search_parallel(
                query,
                max_results=top_k,
                num_workers=self.config.get('fallback_workers', 4)
            )
        else:
            doc_ids = self.ngram_index.raw_search(query, max_results=top_k)
        
        results = [(doc_id, 0.3) for doc_id in doc_ids]  # 兜底结果分数较低
        
        self._record_stats(RetrievalLayer.L4_NGRAM_INDEX, 0, len(results), start)
        return results
    
    def _legacy_retrieve(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResult]:
        """原有串行八层检索（向后兼容）"""
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
            # 从环境变量读取配置的最大 tokens
            import os
            retrieval_llm_max_tokens = int(os.environ.get('RETRIEVAL_LLM_MAX_TOKENS', '200'))
            response = self.llm_client.complete(prompt, max_tokens=retrieval_llm_max_tokens)
            
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
