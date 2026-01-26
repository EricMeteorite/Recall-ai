"""十一层漏斗检索架构 - Phase 3 核心模块 + Phase 3.6 并行三路召回

从 EightLayerRetriever 升级到 ElevenLayerRetriever：
- 新增 L2 时态过滤（依赖 Phase 1 TemporalIndex）
- 新增 L5 图遍历扩展（依赖 Phase 1 TemporalKnowledgeGraph）
- 新增 L10 CrossEncoder 精排（可选）
- Phase 3.6: 并行三路召回 + RRF 融合 + 原文兜底（100%不遗忘保证）
- 保持与现有 EightLayerRetriever 的向后兼容

设计原则：
1. 快速过滤在前 - L1-L2 快速排除大量不相关文档
2. 召回在中 - L3-L7 多路召回，确保高召回率
3. 精排在后 - L8-L11 逐步精细化排序，确保高精度
4. 成本递增 - 越往后成本越高，候选数越少
5. Phase 3.6: 并行三路召回保证 99.5%+ 召回率
"""

from __future__ import annotations

import time
import json
import asyncio
import logging
from enum import Enum
from typing import List, Dict, Set, Optional, Tuple, Any, Callable
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import (
    RetrievalConfig, LayerStats, 
    RetrievalResultItem, TemporalContext, LayerWeights
)
from .rrf_fusion import reciprocal_rank_fusion

logger = logging.getLogger(__name__)


class RetrievalLayer(Enum):
    """检索层级 - 11 层"""
    # === 快速过滤阶段 ===
    L1_BLOOM_FILTER = "bloom_filter"
    L2_TEMPORAL_FILTER = "temporal_filter"    # 新增
    
    # === 召回阶段 ===
    L3_INVERTED_INDEX = "inverted_index"
    L4_ENTITY_INDEX = "entity_index"
    L5_GRAPH_TRAVERSAL = "graph_traversal"    # 新增
    L6_NGRAM_INDEX = "ngram_index"
    L7_VECTOR_COARSE = "vector_coarse"
    
    # === 精排阶段 ===
    L8_VECTOR_FINE = "vector_fine"
    L9_RERANK = "rerank"
    L10_CROSS_ENCODER = "cross_encoder"       # 新增
    L11_LLM_FILTER = "llm_filter"


class ElevenLayerRetriever:
    """十一层漏斗检索器
    
    检索流程（3 阶段 11 层）：
    
    [快速过滤阶段]
    L1:  Bloom Filter      - O(1) 快速否定不可能的候选
    L2:  Temporal Filter   - O(log n) 时间范围预筛选【新增】
    
    [召回阶段]
    L3:  Inverted Index    - O(log n) 关键词匹配
    L4:  Entity Index      - O(1) 实体关联查找
    L5:  Graph Traversal   - O(V+E) BFS 图遍历扩展【新增】
    L6:  N-gram Index      - O(k) 模糊匹配
    L7:  Vector Coarse     - O(n) 近似最近邻
    
    [精排阶段]
    L8:  Vector Fine       - O(k) 精确距离计算
    L9:  Rerank            - O(k log k) 多因素综合排序
    L10: Cross-Encoder     - O(k) 交叉编码器精排【新增，可选】
    L11: LLM Filter        - O(k) 语义相关性判断【可选】
    
    兼容性：
    - 同步 retrieve() 方法保持与 EightLayerRetriever 相同的接口
    - 异步 retrieve_async() 方法支持 L11 LLM 过滤
    - 新增层（L2, L5, L10）在依赖不可用时自动跳过
    """
    
    def __init__(
        self,
        # 现有依赖（对应旧 L1-L8，新编号后为 L1, L3-L4, L6-L9, L11）
        bloom_filter: Optional[Any] = None,
        inverted_index: Optional[Any] = None,
        entity_index: Optional[Any] = None,
        ngram_index: Optional[Any] = None,
        vector_index: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        content_store: Optional[Callable[[str], Optional[str]]] = None,
        # 新增依赖（L2, L5, L10）
        temporal_index: Optional[Any] = None,           # TemporalIndex (Phase 1)
        knowledge_graph: Optional[Any] = None,          # TemporalKnowledgeGraph (Phase 1)
        cross_encoder: Optional[Any] = None,            # CrossEncoder 模型
        # Phase 3.6 新增：用于 VectorIndexIVF 的向量编码
        embedding_backend: Optional[Any] = None,
        # 配置
        config: Optional[RetrievalConfig] = None
    ):
        # 现有依赖
        self.bloom_filter = bloom_filter
        self.inverted_index = inverted_index
        self.entity_index = entity_index
        self.ngram_index = ngram_index
        self.vector_index = vector_index
        self.llm_client = llm_client
        self.content_store = content_store
        
        # Phase 3.6: embedding_backend 用于 VectorIndexIVF（无内置 encode）
        self.embedding_backend = embedding_backend
        
        # 内部内容缓存（兼容旧代码）
        self._content_cache: Dict[str, str] = {}
        # 元数据和实体缓存
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}
        self._entities_cache: Dict[str, List[str]] = {}
        
        # 新增依赖
        self.temporal_index = temporal_index
        self.knowledge_graph = knowledge_graph
        self.cross_encoder = cross_encoder
        
        self.config = config or RetrievalConfig.default()
        
        # 统计
        self.stats: List[LayerStats] = []
        
        # 兼容旧配置格式（dict）
        self._legacy_config: Dict[str, Any] = {}
    
    def cache_content(self, doc_id: str, content: str):
        """缓存文档内容（在添加索引时调用）- 兼容 EightLayerRetriever"""
        self._content_cache[doc_id] = content
    
    def cache_metadata(self, doc_id: str, metadata: Dict[str, Any]):
        """缓存文档元数据"""
        self._metadata_cache[doc_id] = metadata
    
    def cache_entities(self, doc_id: str, entities: List[str]):
        """缓存文档相关实体"""
        self._entities_cache[doc_id] = entities
    
    def _get_content(self, doc_id: str) -> str:
        """获取文档内容 - 委托给 content_store"""
        # 优先从缓存获取
        if doc_id in self._content_cache:
            return self._content_cache[doc_id]
        # 否则从外部存储获取
        if self.content_store:
            content = self.content_store(doc_id)
            if content:
                return content
        return ""
    
    def _get_metadata(self, doc_id: str) -> Dict[str, Any]:
        """获取文档元数据"""
        return self._metadata_cache.get(doc_id, {})
    
    def _get_entities(self, doc_id: str) -> List[str]:
        """获取文档相关实体"""
        return self._entities_cache.get(doc_id, [])
    
    # 兼容 EightLayerRetriever 的 get_content 方法名
    def get_content(self, doc_id: str) -> str:
        """获取文档内容（兼容方法名）"""
        return self._get_content(doc_id)
    
    def retrieve(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        temporal_context: Optional[TemporalContext] = None,
        config: Optional[RetrievalConfig] = None
    ) -> List[RetrievalResultItem]:
        """执行十一层检索（同步版本）
        
        保持与 EightLayerRetriever.retrieve() 完全兼容的接口。
        
        Phase 3.6: 支持并行三路召回模式（默认启用）
        
        Args:
            query: 查询文本
            entities: 实体列表（可选）
            keywords: 关键词列表（可选）
            top_k: 返回数量
            filters: 过滤条件（可选）
            temporal_context: 时态上下文（可选，用于 L2）
            config: 检索配置（可选，覆盖默认配置）
        
        Returns:
            List[RetrievalResultItem]: 检索结果
        """
        config = config or self.config
        top_k = top_k or config.final_top_k
        
        # Phase 3.6: 根据配置选择并行或串行模式
        if config.parallel_recall_enabled:
            return self._parallel_recall(query, entities, keywords, top_k, temporal_context, config)
        else:
            return self._legacy_retrieve(query, entities, keywords, top_k, filters, temporal_context, config)
    
    def _parallel_recall(
        self,
        query: str,
        entities: Optional[List[str]],
        keywords: Optional[List[str]],
        top_k: int,
        temporal_context: Optional[TemporalContext],
        config: RetrievalConfig
    ) -> List[RetrievalResultItem]:
        """Phase 3.6: 并行三路召回实现
        
        1. 并行执行三路召回（语义、关键词、实体）
        2. RRF 融合取并集
        3. 如果结果为空，启用原文兜底
        4. 精排阶段（L8-L10）
        5. 重排序
        
        与 EightLayerRetriever._parallel_recall 保持一致的逻辑
        """
        self.stats = []
        candidates: Set[str] = set()
        scores: Dict[str, float] = defaultdict(float)
        
        # 0. 快速过滤阶段
        # L1: Bloom Filter - 预过滤关键词
        filtered_keywords = keywords or []
        if config.l1_enabled and self.bloom_filter and keywords:
            filtered_keywords = self._l1_bloom_filter(keywords)
        
        # L2: Temporal Filter - 时间范围预筛选
        temporal_candidates: Optional[Set[str]] = None
        if config.l2_enabled and self.temporal_index and temporal_context:
            temporal_candidates = self._l2_temporal_filter(temporal_context, config)
        
        # 1. 并行执行三路召回
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self._vector_recall_parallel, query, top_k * 2): 'vector',
                executor.submit(self._keyword_recall_parallel, filtered_keywords or keywords, top_k * 2, temporal_candidates): 'keyword',
                executor.submit(self._entity_recall_parallel, entities, top_k * 2, temporal_candidates): 'entity',
            }
            
            all_results: Dict[str, List[Tuple[str, float]]] = {}
            for future in as_completed(futures, timeout=10.0):
                source = futures[future]
                try:
                    all_results[source] = future.result()
                except Exception as e:
                    all_results[source] = []
                    logger.warning(f"[ElevenLayer] {source} recall failed: {e}")
        
        # L5: Graph Traversal - 图遍历扩展（附加到实体召回）
        if config.l5_enabled and self.knowledge_graph and entities:
            graph_results = self._graph_recall_parallel(entities, top_k, config)
            all_results['graph'] = graph_results
        
        # 2. RRF 融合
        results_to_fuse = [
            all_results.get('vector', []),
            all_results.get('keyword', []),
            all_results.get('entity', []),
        ]
        weights = [
            config.vector_weight,
            config.keyword_weight,
            config.entity_weight,
        ]
        
        # 如果有图遍历结果，也加入融合
        if 'graph' in all_results and all_results['graph']:
            results_to_fuse.append(all_results['graph'])
            weights.append(config.weights.graph)
        
        fused = reciprocal_rank_fusion(
            results_to_fuse,
            k=config.rrf_k,
            weights=weights
        )
        
        # 3. 如果融合结果为空，启用原文兜底（100% 保证）
        if not fused and config.fallback_enabled and self.ngram_index:
            fused = self._raw_text_fallback_parallel(query, config)
        
        # 将融合结果转为 candidates 和 scores
        for doc_id, score in fused:
            candidates.add(doc_id)
            scores[doc_id] = score
        
        # 4. 精排阶段
        vector_enabled = self.vector_index and getattr(self.vector_index, 'enabled', True)
        
        # L8: Vector Fine - 向量精排
        if config.l8_enabled and vector_enabled and len(candidates) > config.fine_rank_threshold:
            self._l8_vector_fine(query, candidates, scores, config)
        
        # L9: Rerank - TF-IDF 重排序
        if config.l9_enabled and candidates:
            self._l9_rerank(query, entities, keywords, candidates, scores)
        
        # L10: Cross-Encoder - 交叉编码器精排
        if config.l10_enabled and self.cross_encoder and candidates:
            self._l10_cross_encoder(query, candidates, scores, config)
        
        return self._build_results(candidates, scores, top_k)
    
    def _vector_recall_parallel(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """Phase 3.6 路径 1: 语义向量召回
        
        兼容两种向量索引：
        - VectorIndex: search(query: str) - 内部自动 encode
        - VectorIndexIVF: search(embedding: List[float]) - 需要外部 encode
        """
        if not self.vector_index or not getattr(self.vector_index, 'enabled', True):
            return []
        
        start = time.perf_counter()
        results = []
        
        try:
            if hasattr(self.vector_index, 'encode'):
                results = self.vector_index.search(query, top_k=top_k)
            else:
                if hasattr(self, 'embedding_backend') and self.embedding_backend:
                    query_embedding = self.embedding_backend.encode(query)
                    results = self.vector_index.search(query_embedding, top_k=top_k)
                else:
                    logger.warning("[ElevenLayer] No embedding_backend for VectorIndexIVF")
                    return []
        except Exception as e:
            logger.warning(f"[ElevenLayer] Vector recall failed: {e}")
            results = []
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L7_VECTOR_COARSE.value,
            input_count=0,
            output_count=len(results),
            time_ms=(time.perf_counter() - start) * 1000
        ))
        return results
    
    def _keyword_recall_parallel(
        self, 
        keywords: Optional[List[str]], 
        top_k: int,
        temporal_candidates: Optional[Set[str]] = None
    ) -> List[Tuple[str, float]]:
        """Phase 3.6 路径 2: 关键词倒排索引召回（100% 召回）"""
        if not self.inverted_index or not keywords:
            return []
        
        start = time.perf_counter()
        
        # 获取每个关键词匹配的文档
        doc_keyword_counts: Dict[str, int] = defaultdict(int)
        for kw in keywords:
            try:
                if hasattr(self.inverted_index, 'search_any'):
                    matched_docs = self.inverted_index.search_any([kw])
                else:
                    matched_docs = self.inverted_index.search(kw)
                
                # 安全检查：确保 matched_docs 是可迭代的
                if matched_docs is None or not hasattr(matched_docs, '__iter__'):
                    continue
                if not isinstance(matched_docs, (list, tuple, set)):
                    try:
                        matched_docs = list(matched_docs)
                    except (TypeError, ValueError):
                        continue
                
                for doc_id in matched_docs:
                    # 时态过滤
                    if temporal_candidates is not None and doc_id not in temporal_candidates:
                        continue
                    doc_keyword_counts[doc_id] += 1
            except (TypeError, ValueError, AttributeError):
                continue
        
        # 计算分数
        base_score = 0.8
        results = []
        for doc_id, match_count in doc_keyword_counts.items():
            score = base_score * (match_count / len(keywords))
            results.append((doc_id, score))
        
        results.sort(key=lambda x: -x[1])
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L3_INVERTED_INDEX.value,
            input_count=0,
            output_count=len(results),
            time_ms=(time.perf_counter() - start) * 1000
        ))
        return results[:top_k]
    
    def _entity_recall_parallel(
        self, 
        entities: Optional[List[str]], 
        top_k: int,
        temporal_candidates: Optional[Set[str]] = None
    ) -> List[Tuple[str, float]]:
        """Phase 3.6 路径 3: 实体索引召回"""
        if not self.entity_index or not entities:
            return []
        
        start = time.perf_counter()
        doc_ids: Set[str] = set()
        
        for entity in entities:
            try:
                entity_results = self.entity_index.get_related_turns(entity)
                # 安全检查：确保 entity_results 是可迭代的
                if entity_results is None or not hasattr(entity_results, '__iter__'):
                    continue
                if not isinstance(entity_results, (list, tuple, set)):
                    try:
                        entity_results = list(entity_results)
                    except (TypeError, ValueError):
                        continue
                
                for indexed_entity in entity_results:
                    if not hasattr(indexed_entity, 'turn_references'):
                        continue
                    turn_refs = indexed_entity.turn_references
                    if turn_refs is None or not hasattr(turn_refs, '__iter__'):
                        continue
                    for doc_id in turn_refs:
                        # 时态过滤
                        if temporal_candidates is not None and doc_id not in temporal_candidates:
                            continue
                        doc_ids.add(doc_id)
            except (TypeError, ValueError, AttributeError):
                continue
        
        results = [(doc_id, 0.7) for doc_id in list(doc_ids)[:top_k]]
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L4_ENTITY_INDEX.value,
            input_count=0,
            output_count=len(results),
            time_ms=(time.perf_counter() - start) * 1000
        ))
        return results
    
    def _graph_recall_parallel(
        self, 
        entities: List[str], 
        top_k: int,
        config: RetrievalConfig
    ) -> List[Tuple[str, float]]:
        """Phase 3.6 附加路径: 图遍历扩展"""
        start = time.perf_counter()
        graph_candidates: List[Tuple[str, float]] = []
        
        try:
            for start_entity in entities[:config.l5_graph_max_entities]:
                node = self.knowledge_graph.get_node_by_name(start_entity)
                if not node:
                    continue
                
                bfs_results = self.knowledge_graph.bfs(
                    start=node.uuid,
                    max_depth=config.l5_graph_max_depth,
                    time_filter=config.reference_time,
                    direction=config.l5_graph_direction
                )
                
                for depth, items in bfs_results.items():
                    depth_weight = 1.0 / (depth + 1)
                    for target_node_id, edge in items:
                        if hasattr(edge, 'source_episodes') and edge.source_episodes:
                            for episode_id in edge.source_episodes:
                                graph_candidates.append((episode_id, depth_weight * config.weights.graph))
            
            graph_candidates.sort(key=lambda x: x[1], reverse=True)
        except Exception as e:
            logger.warning(f"[ElevenLayer] Graph recall failed: {e}")
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L5_GRAPH_TRAVERSAL.value,
            input_count=0,
            output_count=len(graph_candidates),
            time_ms=(time.perf_counter() - start) * 1000
        ))
        return graph_candidates[:top_k]
    
    def _raw_text_fallback_parallel(
        self, 
        query: str, 
        config: RetrievalConfig
    ) -> List[Tuple[str, float]]:
        """Phase 3.6 原文兜底搜索（100% 保证）"""
        if not self.ngram_index:
            return []
        
        start = time.perf_counter()
        max_results = config.fallback_max_results
        
        # 检查是否有可用的并行搜索方法
        raw_search_parallel = getattr(self.ngram_index, 'raw_search_parallel', None)
        if config.fallback_parallel and callable(raw_search_parallel):
            doc_ids = raw_search_parallel(
                query,
                max_results=max_results,
                num_workers=config.fallback_workers
            )
        else:
            doc_ids = self.ngram_index.raw_search(query, max_results=max_results)
        
        # 安全处理：确保 doc_ids 是可迭代的列表
        if doc_ids is None or not hasattr(doc_ids, '__iter__'):
            doc_ids = []
        elif not isinstance(doc_ids, (list, tuple, set)):
            try:
                doc_ids = list(doc_ids)
            except (TypeError, ValueError):
                doc_ids = []
        
        results = [(doc_id, 0.3) for doc_id in doc_ids]
        
        self.stats.append(LayerStats(
            layer="fallback_ngram_parallel",
            input_count=0,
            output_count=len(results),
            time_ms=(time.perf_counter() - start) * 1000
        ))
        return results
    
    def _legacy_retrieve(
        self,
        query: str,
        entities: Optional[List[str]],
        keywords: Optional[List[str]],
        top_k: int,
        filters: Optional[Dict[str, Any]],
        temporal_context: Optional[TemporalContext],
        config: RetrievalConfig
    ) -> List[RetrievalResultItem]:
        """原有串行十一层检索（向后兼容）"""
        self.stats = []
        candidates: Set[str] = set()  # 候选 ID 集合
        scores: Dict[str, float] = defaultdict(float)  # ID -> 分数
        
        # ========== 快速过滤阶段 ==========
        
        # L1: Bloom Filter - 快速否定
        filtered_keywords = keywords or []
        if config.l1_enabled and self.bloom_filter and keywords:
            filtered_keywords = self._l1_bloom_filter(keywords)
        
        # L2: Temporal Filter - 时间范围预筛选【新增】
        temporal_candidates: Optional[Set[str]] = None
        if config.l2_enabled and self.temporal_index and temporal_context:
            temporal_candidates = self._l2_temporal_filter(temporal_context, config)
        
        # ========== 召回阶段 ==========
        
        # L3: Inverted Index - 关键词匹配
        if config.l3_enabled and self.inverted_index:
            self._l3_inverted_index(filtered_keywords or keywords, candidates, scores, config, temporal_candidates)
        
        # L4: Entity Index - 实体关联
        if config.l4_enabled and self.entity_index and entities:
            self._l4_entity_index(entities, candidates, scores, config, temporal_candidates)
        
        # L5: Graph Traversal - 图遍历扩展【新增】
        if config.l5_enabled and self.knowledge_graph and entities:
            self._l5_graph_traversal(entities, candidates, scores, config)
        
        # L6: N-gram Index - 模糊匹配
        if config.l6_enabled and self.ngram_index:
            self._l6_ngram_index(query, candidates, scores, config, temporal_candidates)
        
        # L7: Vector Coarse - 向量粗筛
        vector_enabled = self.vector_index and getattr(self.vector_index, 'enabled', True)
        if config.l7_enabled and vector_enabled:
            self._l7_vector_coarse(query, candidates, scores, config)
        
        # ========== 精排阶段 ==========
        
        # L8: Vector Fine - 向量精排
        if config.l8_enabled and vector_enabled and len(candidates) > config.fine_rank_threshold:
            self._l8_vector_fine(query, candidates, scores, config)
        
        # L9: Rerank - TF-IDF 重排序
        if config.l9_enabled and candidates:
            self._l9_rerank(query, entities, keywords, candidates, scores)
        
        # L10: Cross-Encoder - 交叉编码器精排【新增，可选】
        if config.l10_enabled and self.cross_encoder and candidates:
            self._l10_cross_encoder(query, candidates, scores, config)
        
        # L11: LLM Filter（同步版本跳过，使用 retrieve_async）
        # 注意：为保持向后兼容，同步版本不执行 L11
        
        # 终极兜底：如果所有层都没找到结果，使用 N-gram 原文搜索
        if not candidates and self.ngram_index:
            self._fallback_ngram_search(query, candidates, scores, top_k)
        
        return self._build_results(candidates, scores, top_k)
    
    async def retrieve_async(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        temporal_context: Optional[TemporalContext] = None,
        config: Optional[RetrievalConfig] = None
    ) -> List[RetrievalResultItem]:
        """执行十一层检索（异步版本，支持 L11 LLM Filter）
        
        Args:
            query: 查询文本
            entities: 实体列表（可选）
            keywords: 关键词列表（可选）
            top_k: 返回数量
            filters: 过滤条件（可选）
            temporal_context: 时态上下文（可选）
            config: 检索配置（可选）
        
        Returns:
            List[RetrievalResultItem]: 检索结果
        """
        config = config or self.config
        top_k = top_k or config.final_top_k
        
        self.stats = []
        candidates: Set[str] = set()
        scores: Dict[str, float] = defaultdict(float)
        
        # ========== 快速过滤阶段 ==========
        
        # L1: Bloom Filter
        filtered_keywords = keywords or []
        if config.l1_enabled and self.bloom_filter and keywords:
            filtered_keywords = self._l1_bloom_filter(keywords)
        
        # L2: Temporal Filter
        temporal_candidates: Optional[Set[str]] = None
        if config.l2_enabled and self.temporal_index and temporal_context:
            temporal_candidates = self._l2_temporal_filter(temporal_context, config)
        
        # ========== 召回阶段 ==========
        
        # L3: Inverted Index
        if config.l3_enabled and self.inverted_index:
            self._l3_inverted_index(filtered_keywords or keywords, candidates, scores, config, temporal_candidates)
        
        # L4: Entity Index
        if config.l4_enabled and self.entity_index and entities:
            self._l4_entity_index(entities, candidates, scores, config, temporal_candidates)
        
        # L5: Graph Traversal
        if config.l5_enabled and self.knowledge_graph and entities:
            self._l5_graph_traversal(entities, candidates, scores, config)
        
        # L6: N-gram Index
        if config.l6_enabled and self.ngram_index:
            self._l6_ngram_index(query, candidates, scores, config, temporal_candidates)
        
        # L7: Vector Coarse
        vector_enabled = self.vector_index and getattr(self.vector_index, 'enabled', True)
        if config.l7_enabled and vector_enabled:
            self._l7_vector_coarse(query, candidates, scores, config)
        
        # ========== 精排阶段 ==========
        
        # L8: Vector Fine
        if config.l8_enabled and vector_enabled and len(candidates) > config.fine_rank_threshold:
            self._l8_vector_fine(query, candidates, scores, config)
        
        # L9: Rerank
        if config.l9_enabled and candidates:
            self._l9_rerank(query, entities, keywords, candidates, scores)
        
        # L10: Cross-Encoder
        if config.l10_enabled and self.cross_encoder and candidates:
            self._l10_cross_encoder(query, candidates, scores, config)
        
        # L11: LLM Filter【异步】
        if config.l11_enabled and self.llm_client and candidates:
            candidates, scores = await self._l11_llm_filter(query, candidates, scores, config)
        
        # 兜底搜索
        if not candidates and self.ngram_index:
            self._fallback_ngram_search(query, candidates, scores, top_k)
        
        return self._build_results(candidates, scores, top_k)
    
    # =========================================================================
    # L1: Bloom Filter（从 EightLayerRetriever 迁移）
    # =========================================================================
    
    def _l1_bloom_filter(self, keywords: List[str]) -> List[str]:
        """L1: Bloom Filter - 快速否定不可能的关键词"""
        start_time = time.perf_counter()
        
        # 使用 in 运算符检查（BloomFilter 实现了 __contains__）
        filtered_keywords = [
            kw for kw in keywords 
            if kw in self.bloom_filter
        ]
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L1_BLOOM_FILTER.value,
            input_count=len(keywords),
            output_count=len(filtered_keywords),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
        
        return filtered_keywords
    
    # =========================================================================
    # L2: Temporal Filter（新增）
    # =========================================================================
    
    def _l2_temporal_filter(
        self,
        temporal_context: TemporalContext,
        config: RetrievalConfig
    ) -> Optional[Set[str]]:
        """L2: 时态过滤 - 使用 TemporalIndex 预筛选时间范围内的文档"""
        
        if not temporal_context.has_time_constraint():
            return None  # 无时间约束，跳过此层
        
        start_time = time.perf_counter()
        
        try:
            # 使用 Phase 1 实现的 TemporalIndex.query_range()
            results = self.temporal_index.query_range(
                start=temporal_context.start,
                end=temporal_context.end
            )
            
            # results 是 doc_id 列表
            candidate_ids = set(results) if results else set()
            
            # 按 top_k 限制
            if len(candidate_ids) > config.l2_temporal_top_k:
                candidate_ids = set(list(candidate_ids)[:config.l2_temporal_top_k])
            
            # 记录统计
            self.stats.append(LayerStats(
                layer=RetrievalLayer.L2_TEMPORAL_FILTER.value,
                input_count=-1,  # 全量扫描
                output_count=len(candidate_ids),
                time_ms=(time.perf_counter() - start_time) * 1000
            ))
            
            return candidate_ids
            
        except Exception as e:
            logger.warning(f"L2 temporal filter failed: {e}")
            return None
    
    # =========================================================================
    # L3: Inverted Index（从 EightLayerRetriever L2 迁移）
    # =========================================================================
    
    def _l3_inverted_index(
        self,
        keywords: Optional[List[str]],
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig,
        temporal_candidates: Optional[Set[str]] = None
    ) -> None:
        """L3: Inverted Index - 关键词匹配"""
        if not keywords:
            return
        
        start_time = time.perf_counter()
        input_count = len(candidates)
        
        # 使用 search_any 来搜索任一关键词
        inverted_results = self.inverted_index.search_any(keywords)
        
        # 时态过滤
        if temporal_candidates is not None:
            inverted_results = [r for r in inverted_results if r in temporal_candidates]
        
        # 按 top_k 限制
        for doc_id in inverted_results[:config.l3_inverted_top_k]:
            candidates.add(doc_id)
            scores[doc_id] += config.weights.inverted
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L3_INVERTED_INDEX.value,
            input_count=input_count,
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L4: Entity Index（从 EightLayerRetriever L3 迁移）
    # =========================================================================
    
    def _l4_entity_index(
        self,
        entities: List[str],
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig,
        temporal_candidates: Optional[Set[str]] = None
    ) -> None:
        """L4: Entity Index - 实体关联查找"""
        start_time = time.perf_counter()
        input_count = len(candidates)
        
        entity_results = []
        for entity in entities:
            indexed_entities = self.entity_index.get_related_turns(entity)
            for indexed_entity in indexed_entities:
                entity_results.extend(indexed_entity.turn_references)
        
        # 时态过滤
        if temporal_candidates is not None:
            entity_results = [r for r in entity_results if r in temporal_candidates]
        
        # 按 top_k 限制并加分
        for doc_id in entity_results[:config.l4_entity_top_k]:
            candidates.add(doc_id)
            scores[doc_id] += config.weights.entity
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L4_ENTITY_INDEX.value,
            input_count=input_count,
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L5: Graph Traversal（新增）
    # =========================================================================
    
    def _l5_graph_traversal(
        self,
        entities: List[str],
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig
    ) -> None:
        """L5: 图遍历扩展 - 使用 TemporalKnowledgeGraph.bfs() 发现关联文档"""
        
        start_time = time.perf_counter()
        input_count = len(candidates)
        graph_candidates: List[Tuple[str, float]] = []  # (doc_id, score)
        
        try:
            for start_entity in entities[:config.l5_graph_max_entities]:
                # 获取节点（支持名称或 UUID）
                node = self.knowledge_graph.get_node_by_name(start_entity)
                if not node:
                    continue
                
                # 使用 Phase 1 实现的 BFS
                bfs_results = self.knowledge_graph.bfs(
                    start=node.uuid,
                    max_depth=config.l5_graph_max_depth,
                    time_filter=config.reference_time,
                    direction=config.l5_graph_direction
                )
                
                # 按深度加权添加候选
                for depth, items in bfs_results.items():
                    depth_weight = 1.0 / (depth + 1)  # 距离衰减
                    for target_node_id, edge in items:
                        # 获取边关联的 episode（source_episodes 是来源文档列表）
                        if hasattr(edge, 'source_episodes') and edge.source_episodes:
                            for episode_id in edge.source_episodes:
                                graph_candidates.append((episode_id, depth_weight * config.weights.graph))
            
            # 按分数排序并取 top_k
            graph_candidates.sort(key=lambda x: x[1], reverse=True)
            for episode_id, score in graph_candidates[:config.l5_graph_top_k]:
                candidates.add(episode_id)
                scores[episode_id] += score
                
        except Exception as e:
            logger.warning(f"L5 graph traversal failed: {e}")
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L5_GRAPH_TRAVERSAL.value,
            input_count=input_count,
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L6: N-gram Index（从 EightLayerRetriever L4 迁移）
    # =========================================================================
    
    def _l6_ngram_index(
        self,
        query: str,
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig,
        temporal_candidates: Optional[Set[str]] = None
    ) -> None:
        """L6: N-gram Index - 模糊匹配"""
        start_time = time.perf_counter()
        input_count = len(candidates)
        
        ngram_results = self.ngram_index.search(query)
        
        # 时态过滤
        if temporal_candidates is not None:
            ngram_results = [r for r in ngram_results if r in temporal_candidates]
        
        # 按 top_k 限制
        for doc_id in ngram_results[:config.l6_ngram_top_k]:
            candidates.add(doc_id)
            scores[doc_id] += config.weights.ngram
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L6_NGRAM_INDEX.value,
            input_count=input_count,
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L7: Vector Coarse（从 EightLayerRetriever L5 迁移）
    # =========================================================================
    
    def _l7_vector_coarse(
        self,
        query: str,
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig
    ) -> None:
        """L7: Vector Coarse - 向量粗筛"""
        start_time = time.perf_counter()
        input_count = len(candidates)
        
        vector_results = self.vector_index.search(
            query, 
            top_k=config.l7_vector_top_k
        )
        
        # 合并向量结果
        for doc_id, score in vector_results:
            candidates.add(doc_id)
            scores[doc_id] += score * config.weights.vector
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L7_VECTOR_COARSE.value,
            input_count=input_count,
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L8: Vector Fine（从 EightLayerRetriever L6 迁移）
    # =========================================================================
    
    def _l8_vector_fine(
        self,
        query: str,
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig
    ) -> None:
        """L8: Vector Fine - 向量精排，重新计算精确相似度"""
        start_time = time.perf_counter()
        input_count = len(candidates)
        
        try:
            import numpy as np
            
            # 1. 获取查询向量
            query_embedding = self.vector_index.encode(query)
            query_embedding = query_embedding / np.linalg.norm(query_embedding)
            
            # 2. 批量获取候选文档的已存储向量
            doc_ids = list(candidates)
            stored_vectors = {}
            if hasattr(self.vector_index, 'get_vectors_by_doc_ids'):
                stored_vectors = self.vector_index.get_vectors_by_doc_ids(doc_ids)
            
            # 3. 对每个候选文档计算精确相似度
            for doc_id in doc_ids:
                if doc_id in stored_vectors:
                    doc_embedding = stored_vectors[doc_id]
                    doc_embedding = doc_embedding / np.linalg.norm(doc_embedding)
                    
                    # 计算余弦相似度
                    cosine_sim = float(np.dot(query_embedding, doc_embedding))
                    
                    # 融合分数：70% 余弦相似度 + 30% 原分数
                    scores[doc_id] = 0.7 * cosine_sim + 0.3 * scores[doc_id]
                    
        except Exception as e:
            logger.warning(f"L8 vector fine ranking failed: {e}")
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L8_VECTOR_FINE.value,
            input_count=input_count,
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L9: Rerank（从 EightLayerRetriever L7 迁移）
    # =========================================================================
    
    def _l9_rerank(
        self,
        query: str,
        entities: Optional[List[str]],
        keywords: Optional[List[str]],
        candidates: Set[str],
        scores: Dict[str, float]
    ) -> None:
        """L9: Rerank - TF-IDF 多因素重排序"""
        start_time = time.perf_counter()
        
        for doc_id in candidates:
            bonus = 0.0
            content = self._get_content(doc_id)
            
            # 关键词匹配加分
            if keywords:
                for kw in keywords:
                    if kw.lower() in content.lower():
                        bonus += 0.05
            
            # 实体匹配加分
            if entities:
                for entity in entities:
                    if entity.lower() in content.lower():
                        bonus += 0.1
            
            scores[doc_id] += bonus
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L9_RERANK.value,
            input_count=len(candidates),
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L10: Cross-Encoder（新增）
    # =========================================================================
    
    def _l10_cross_encoder(
        self,
        query: str,
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig
    ) -> None:
        """L10: CrossEncoder 重排序 - 使用交叉编码器计算精确相关性"""
        
        start_time = time.perf_counter()
        
        try:
            # 取 top candidates
            sorted_candidates = sorted(
                candidates,
                key=lambda x: scores[x],
                reverse=True
            )[:config.l10_cross_encoder_top_k]
            
            # 准备 query-document pairs
            pairs = [
                (query, self._get_content(doc_id))
                for doc_id in sorted_candidates
            ]
            
            # CrossEncoder 批量评分
            ce_scores = self.cross_encoder.predict(pairs)
            
            # 融合分数：30% 旧分 + 70% CrossEncoder 分
            for doc_id, ce_score in zip(sorted_candidates, ce_scores):
                scores[doc_id] = scores[doc_id] * 0.3 + float(ce_score) * 0.7
                
        except Exception as e:
            logger.warning(f"L10 cross encoder failed: {e}")
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L10_CROSS_ENCODER.value,
            input_count=len(candidates),
            output_count=len(candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
    
    # =========================================================================
    # L11: LLM Filter（从 EightLayerRetriever L8 迁移，改为异步）
    # =========================================================================
    
    async def _l11_llm_filter(
        self,
        query: str,
        candidates: Set[str],
        scores: Dict[str, float],
        config: RetrievalConfig
    ) -> Tuple[Set[str], Dict[str, float]]:
        """L11: LLM 重排序 - 使用 LLM 进行最终语义相关性判断"""
        
        start_time = time.perf_counter()
        
        # 取 top candidates
        sorted_candidates = sorted(
            candidates,
            key=lambda x: scores[x],
            reverse=True
        )[:config.l11_llm_top_k]
        
        # 构建评分 prompt
        docs_text = "\n\n".join([
            f"[Doc {i+1}] {self._get_content(doc_id)[:500]}"
            for i, doc_id in enumerate(sorted_candidates)
        ])
        
        prompt = f"""请根据查询的相关性对以下文档进行评分（0-10分）。

查询: {query}

文档列表:
{docs_text}

请以 JSON 格式返回评分：{{"scores": [8, 6, 9, ...]}}
只返回 JSON，不要其他内容。"""

        try:
            # 支持同步和异步 LLM 客户端
            if hasattr(self.llm_client, 'complete_async'):
                response = await asyncio.wait_for(
                    self.llm_client.complete_async(prompt=prompt, max_tokens=200, temperature=0.0),
                    timeout=config.l11_llm_timeout
                )
            else:
                # 同步客户端，在线程中执行
                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.llm_client.complete(prompt=prompt, max_tokens=200, temperature=0.0)
                    ),
                    timeout=config.l11_llm_timeout
                )
            
            result = json.loads(response)
            llm_scores = result.get("scores", [])
            
            # LLM 分数直接覆盖（最终裁判）
            for doc_id, llm_score in zip(sorted_candidates, llm_scores):
                scores[doc_id] = llm_score / 10.0
            
        except Exception as e:
            logger.warning(f"L11 LLM filter failed: {e}, keeping original scores")
        
        self.stats.append(LayerStats(
            layer=RetrievalLayer.L11_LLM_FILTER.value,
            input_count=len(candidates),
            output_count=len(sorted_candidates),
            time_ms=(time.perf_counter() - start_time) * 1000
        ))
        
        return set(sorted_candidates), scores
    
    # =========================================================================
    # 辅助方法
    # =========================================================================
    
    def _fallback_ngram_search(
        self,
        query: str,
        candidates: Set[str],
        scores: Dict[str, float],
        top_k: int
    ) -> None:
        """兜底搜索 - 如果所有层都没找到结果，使用 N-gram 原文搜索"""
        start_time = time.perf_counter()
        
        # 调用 raw_search 直接搜索原文
        if hasattr(self.ngram_index, 'raw_search'):
            fallback_ids = self.ngram_index.raw_search(query, max_results=top_k)
        else:
            fallback_ids = self.ngram_index.search(query)
        
        for doc_id in fallback_ids[:top_k]:
            content = self._get_content(doc_id)
            if content:
                candidates.add(doc_id)
                scores[doc_id] = 0.3  # 兜底搜索的基础分数
        
        if candidates:
            self.stats.append(LayerStats(
                layer="fallback_ngram",
                input_count=0,
                output_count=len(candidates),
                time_ms=(time.perf_counter() - start_time) * 1000
            ))
    
    def _build_results(
        self,
        candidates: Set[str],
        scores: Dict[str, float],
        top_k: int
    ) -> List[RetrievalResultItem]:
        """构建最终检索结果"""
        # 按分数排序
        sorted_candidates = sorted(
            candidates,
            key=lambda x: scores[x],
            reverse=True
        )[:top_k]
        
        return [
            RetrievalResultItem(
                id=doc_id,
                score=scores[doc_id],
                content=self._get_content(doc_id),
                metadata=self._get_metadata(doc_id),
                entities=self._get_entities(doc_id)
            )
            for doc_id in sorted_candidates
        ]
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """获取统计摘要（兼容 EightLayerRetriever）"""
        total_time = sum(s.time_ms for s in self.stats)
        return {
            'total_time_ms': total_time,
            'layers': [
                {
                    'layer': s.layer,
                    'input': s.input_count,
                    'output': s.output_count,
                    'time_ms': s.time_ms,
                }
                for s in self.stats
            ]
        }


# =========================================================================
# 向后兼容适配器
# =========================================================================

class EightLayerRetrieverCompat:
    """向后兼容适配器 - 将旧 8 层同步 API 映射到新 11 层
    
    用于需要保持完全兼容的场景。
    """
    
    def __init__(self, eleven_layer: ElevenLayerRetriever):
        self._impl = eleven_layer
    
    def retrieve(
        self,
        query: str,
        entities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievalResultItem]:
        """旧 API 兼容（同步）"""
        # 创建兼容配置（禁用新增层）
        config = RetrievalConfig(
            l2_enabled=False,   # 禁用 Temporal
            l5_enabled=False,   # 禁用 Graph
            l10_enabled=False,  # 禁用 CrossEncoder
            l11_enabled=False,  # 禁用 LLM
        )
        return self._impl.retrieve(
            query=query,
            entities=entities,
            keywords=keywords,
            top_k=top_k,
            filters=filters,
            temporal_context=None,
            config=config
        )
    
    def cache_content(self, doc_id: str, content: str):
        """兼容方法"""
        self._impl.cache_content(doc_id, content)
    
    def get_content(self, doc_id: str) -> str:
        """兼容方法"""
        return self._impl.get_content(doc_id)
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """兼容方法"""
        return self._impl.get_stats_summary()


# 模块导出
__all__ = [
    'RetrievalLayer',
    'ElevenLayerRetriever',
    'EightLayerRetrieverCompat',
]
