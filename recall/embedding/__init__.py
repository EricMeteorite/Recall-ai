"""Embedding 后端模块

支持多种 embedding 后端：
- local: 本地 sentence-transformers（完整模式，需要 ~1GB 内存）
- openai: OpenAI text-embedding API（Hybrid 模式，需要 API key）
- siliconflow: 硅基流动 API（Hybrid 模式，国内可用）
- none: 轻量模式（无向量搜索）
"""

from .base import EmbeddingBackend, EmbeddingConfig, EmbeddingBackendType
from .factory import create_embedding_backend, get_available_backends

__all__ = [
    'EmbeddingBackend',
    'EmbeddingConfig',
    'EmbeddingBackendType',
    'create_embedding_backend',
    'get_available_backends',
]
