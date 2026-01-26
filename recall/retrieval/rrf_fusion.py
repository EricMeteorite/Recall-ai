"""Reciprocal Rank Fusion - 多路召回结果融合

Phase 3.6: 100% 不遗忘最优架构

RRF 公式：score(d) = Σ 1 / (k + rank_i(d))
其中 k 通常取 60

优点：
- 不需要归一化不同检索器的分数
- 对排名靠前的结果给予更高权重
- 自动处理不同召回路径的结果合并
"""

from typing import List, Dict, Tuple, Optional
from collections import defaultdict


def reciprocal_rank_fusion(
    results_list: List[List[Tuple[str, float]]],
    k: int = 60,
    weights: Optional[List[float]] = None
) -> List[Tuple[str, float]]:
    """RRF 融合多路召回结果
    
    Args:
        results_list: 多路召回结果，每路为 [(doc_id, score), ...]
        k: RRF 常数，默认 60
        weights: 各路权重，默认全为 1.0
        
    Returns:
        融合后的结果 [(doc_id, rrf_score), ...]，按分数降序
    """
    if not results_list:
        return []
    
    if not weights:
        weights = [1.0] * len(results_list)
    
    # 计算 RRF 分数
    rrf_scores: Dict[str, float] = defaultdict(float)
    
    for weight, results in zip(weights, results_list):
        for rank, (doc_id, _) in enumerate(results, start=1):
            rrf_scores[doc_id] += weight * (1.0 / (k + rank))
    
    # 排序返回
    sorted_results = sorted(
        rrf_scores.items(),
        key=lambda x: -x[1]
    )
    
    return sorted_results


def weighted_score_fusion(
    results_list: List[List[Tuple[str, float]]],
    weights: Optional[List[float]] = None,
    normalize: bool = True
) -> List[Tuple[str, float]]:
    """加权分数融合（替代方案）
    
    当需要考虑原始分数时使用
    
    Args:
        results_list: 多路召回结果，每路为 [(doc_id, score), ...]
        weights: 各路权重，默认全为 1.0
        normalize: 是否归一化各路分数到 [0, 1]
        
    Returns:
        融合后的结果 [(doc_id, fused_score), ...]，按分数降序
    """
    if not results_list:
        return []
    
    if not weights:
        weights = [1.0] * len(results_list)
    
    # 归一化各路分数到 [0, 1]
    normalized_results = []
    for results in results_list:
        if not results:
            normalized_results.append([])
            continue
        
        if normalize:
            scores = [s for _, s in results]
            min_s, max_s = min(scores), max(scores)
            range_s = max_s - min_s if max_s > min_s else 1.0
            # 如果所有分数相同，归一化为 1.0（而不是 0.0）
            if max_s == min_s:
                normalized = [(doc_id, 1.0) for doc_id, s in results]
            else:
                normalized = [(doc_id, (s - min_s) / range_s) for doc_id, s in results]
        else:
            normalized = results
        
        normalized_results.append(normalized)
    
    # 加权融合
    fused_scores: Dict[str, float] = defaultdict(float)
    doc_counts: Dict[str, int] = defaultdict(int)
    
    for weight, results in zip(weights, normalized_results):
        for doc_id, score in results:
            fused_scores[doc_id] += weight * score
            doc_counts[doc_id] += 1
    
    # 多路命中加分（出现在多个路径中的结果更可信）
    for doc_id in fused_scores:
        if doc_counts[doc_id] > 1:
            fused_scores[doc_id] *= (1 + 0.1 * (doc_counts[doc_id] - 1))
    
    return sorted(fused_scores.items(), key=lambda x: -x[1])
