"""recall/retrieval/reranker.py — 可插拔的重排序后端"""

import os
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class RerankerBase:
    """重排序器基类"""
    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        raise NotImplementedError


class BuiltinReranker(RerankerBase):
    """内置重排序器（从 eleven_layer.py _l9_rerank 搬迁）

    原逻辑：遍历候选文档，关键词匹配 +0.05/次，查询整体匹配 +0.2
    """
    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        query_lower = query.lower()
        query_keywords = query_lower.split()

        scored = []
        for idx, doc in enumerate(documents):
            bonus = 0.0
            doc_lower = doc.lower()

            # 关键词匹配加分
            for kw in query_keywords:
                if kw in doc_lower:
                    bonus += 0.05

            # 查询整体匹配额外加分
            if query_lower in doc_lower:
                bonus += 0.2

            scored.append((idx, bonus))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


class CohereReranker(RerankerBase):
    """Cohere Rerank API"""
    def __init__(self, api_key: str = None, model: str = "rerank-multilingual-v3.0"):
        import cohere
        self.client = cohere.Client(api_key or os.getenv('COHERE_API_KEY'))
        self.model = model

    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        response = self.client.rerank(
            model=self.model, query=query, documents=documents, top_k=top_k
        )
        return [(r.index, r.relevance_score) for r in response.results]


class CrossEncoderReranker(RerankerBase):
    """Cross-Encoder 本地模型"""
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        pairs = [(query, doc) for doc in documents]
        scores = self.model.predict(pairs)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


class RerankerFactory:
    @staticmethod
    def create(backend: str = "builtin") -> RerankerBase:
        if backend == "cohere":
            return CohereReranker()
        elif backend == "cross-encoder":
            return CrossEncoderReranker()
        else:
            if backend != "builtin":
                logger.warning(f"未知的 RERANKER_BACKEND='{backend}'，降级到 builtin")
            return BuiltinReranker()
