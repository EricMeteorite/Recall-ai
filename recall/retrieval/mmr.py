"""Maximal Marginal Relevance (MMR) 重排序模块

Phase 7.4: 检索结果多样性优化

MMR 公式：
  MMR(d) = λ * Sim(d, Q) - (1 - λ) * max_{d_j ∈ S} Sim(d, d_j)

其中：
- λ 控制相关性与多样性的权衡 (0.7 = 偏重相关性)
- Sim(d, Q) 为文档与查询的相似度
- Sim(d, d_j) 为文档之间的相似度
- S 为已选集合

优点：
- 避免返回高度冗余的结果
- 在保持相关性的同时增加信息多样性
- 参数可调，灵活控制相关性-多样性平衡
"""

from typing import List, Dict, Optional, Tuple
import math


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """余弦相似度计算
    
    Args:
        vec_a: 向量 A
        vec_b: 向量 B
        
    Returns:
        余弦相似度 [-1, 1]
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def mmr_rerank(
    results: List[Dict],
    query_embedding: List[float],
    embeddings: Dict[str, List[float]],
    lambda_param: float = 0.7,
    top_k: int = 10
) -> List[Dict]:
    """Maximal Marginal Relevance 重排序，增加结果多样性
    
    从候选集中迭代选择文档：
    1. 第一轮选择与查询最相关的文档
    2. 之后每轮选择与查询相关但与已选文档不相似的文档
    
    Args:
        results: 候选结果列表，每个元素须包含 'id' 和 'score' 字段
        query_embedding: 查询的向量表示
        embeddings: 文档 ID -> 向量表示的映射
        lambda_param: MMR 参数 λ，越大越偏重相关性，范围 [0, 1]，默认 0.7
        top_k: 最终返回的文档数量
        
    Returns:
        MMR 重排后的结果列表（最多 top_k 个）
    """
    if not results:
        return []
    
    if not query_embedding:
        # 无查询向量时退化为按分数排序
        return sorted(results, key=lambda x: x.get('score', 0), reverse=True)[:top_k]
    
    # 构建 id -> result 映射
    result_map: Dict[str, Dict] = {}
    for r in results:
        doc_id = r.get('id', '')
        if doc_id:
            result_map[doc_id] = r
    
    if not result_map:
        return results[:top_k]
    
    # 预计算所有候选与查询的相似度
    query_sims: Dict[str, float] = {}
    for doc_id in result_map:
        if doc_id in embeddings:
            query_sims[doc_id] = cosine_similarity(query_embedding, embeddings[doc_id])
        else:
            # 无向量时用原始分数作为相似度近似
            query_sims[doc_id] = result_map[doc_id].get('score', 0.0)
    
    # 迭代式 MMR 选择
    selected: List[str] = []
    remaining = set(result_map.keys())
    
    for _ in range(min(top_k, len(result_map))):
        if not remaining:
            break
        
        best_id: Optional[str] = None
        best_mmr: float = float('-inf')
        
        for doc_id in remaining:
            # 相关性分量
            relevance = query_sims.get(doc_id, 0.0)
            
            # 多样性分量：与已选文档的最大相似度
            max_sim_to_selected = 0.0
            if selected:
                doc_emb = embeddings.get(doc_id)
                if doc_emb:
                    for sel_id in selected:
                        sel_emb = embeddings.get(sel_id)
                        if sel_emb:
                            sim = cosine_similarity(doc_emb, sel_emb)
                            max_sim_to_selected = max(max_sim_to_selected, sim)
            
            # MMR 公式
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim_to_selected
            
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_id = doc_id
        
        if best_id is not None:
            selected.append(best_id)
            remaining.discard(best_id)
    
    # 构建结果列表，更新分数为 MMR 分数
    mmr_results: List[Dict] = []
    for rank, doc_id in enumerate(selected):
        result = dict(result_map[doc_id])  # 浅拷贝
        # 保留原始分数，添加 MMR 排名信息
        result['mmr_rank'] = rank
        result['original_score'] = result.get('score', 0.0)
        mmr_results.append(result)
    
    return mmr_results


def mmr_rerank_by_content(
    results: List[Dict],
    similarity_fn=None,
    lambda_param: float = 0.7,
    top_k: int = 10
) -> List[Dict]:
    """基于文本内容的 MMR 重排序（无需向量）
    
    当没有预计算的向量时，使用文本相似度（如 Jaccard）进行 MMR。
    
    Args:
        results: 候选结果列表，每个元素须包含 'id', 'score', 'content' 字段
        similarity_fn: 可选的文本相似度函数 (str, str) -> float
                       默认使用 Jaccard 字符级相似度
        lambda_param: MMR 参数 λ，默认 0.7
        top_k: 最终返回的文档数量
        
    Returns:
        MMR 重排后的结果列表
    """
    if not results:
        return []
    
    if similarity_fn is None:
        similarity_fn = _jaccard_similarity
    
    # 构建 id -> result 映射
    result_map: Dict[str, Dict] = {}
    for r in results:
        doc_id = r.get('id', '')
        if doc_id:
            result_map[doc_id] = r
    
    if not result_map:
        return results[:top_k]
    
    # 迭代式 MMR 选择
    selected: List[str] = []
    remaining = set(result_map.keys())
    
    for _ in range(min(top_k, len(result_map))):
        if not remaining:
            break
        
        best_id: Optional[str] = None
        best_mmr: float = float('-inf')
        
        for doc_id in remaining:
            # 相关性分量：使用原始检索分数
            relevance = result_map[doc_id].get('score', 0.0)
            
            # 多样性分量
            max_sim_to_selected = 0.0
            if selected:
                doc_content = result_map[doc_id].get('content', '')
                for sel_id in selected:
                    sel_content = result_map[sel_id].get('content', '')
                    if doc_content and sel_content:
                        sim = similarity_fn(doc_content, sel_content)
                        max_sim_to_selected = max(max_sim_to_selected, sim)
            
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim_to_selected
            
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_id = doc_id
        
        if best_id is not None:
            selected.append(best_id)
            remaining.discard(best_id)
    
    # 构建结果
    mmr_results: List[Dict] = []
    for rank, doc_id in enumerate(selected):
        result = dict(result_map[doc_id])
        result['mmr_rank'] = rank
        result['original_score'] = result.get('score', 0.0)
        mmr_results.append(result)
    
    return mmr_results


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """基于词级的 Jaccard 相似度
    
    Args:
        text_a: 文本 A
        text_b: 文本 B
        
    Returns:
        Jaccard 相似度 [0, 1]
    """
    if not text_a or not text_b:
        return 0.0
    
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    
    if not words_a or not words_b:
        return 0.0
    
    intersection = words_a & words_b
    union = words_a | words_b
    
    return len(intersection) / len(union) if union else 0.0


# 模块导出
__all__ = [
    'mmr_rerank',
    'mmr_rerank_by_content',
    'cosine_similarity',
]
