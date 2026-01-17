"""Embedding 后端基类和配置"""

from abc import ABC, abstractmethod
from typing import List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class EmbeddingBackendType(str, Enum):
    """Embedding 后端类型"""
    LOCAL = "local"           # 本地 sentence-transformers
    OPENAI = "openai"         # OpenAI API
    SILICONFLOW = "siliconflow"  # 硅基流动 API
    NONE = "none"             # 禁用（轻量模式）


@dataclass
class EmbeddingConfig:
    """Embedding 配置"""
    backend: EmbeddingBackendType = EmbeddingBackendType.LOCAL
    
    # 本地模型配置
    local_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    
    # API 配置
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_model: str = "text-embedding-3-small"  # OpenAI 默认
    
    # 通用配置
    dimension: int = 384  # 向量维度（会根据后端自动调整）
    batch_size: int = 32
    normalize: bool = True
    
    # 性能配置
    cache_embeddings: bool = True
    max_cache_size: int = 10000
    
    @classmethod
    def lightweight(cls) -> 'EmbeddingConfig':
        """轻量模式配置（禁用向量索引）"""
        return cls(backend=EmbeddingBackendType.NONE)
    
    @classmethod
    def hybrid_openai(cls, api_key: str) -> 'EmbeddingConfig':
        """Hybrid 模式 - OpenAI"""
        return cls(
            backend=EmbeddingBackendType.OPENAI,
            api_key=api_key,
            api_model="text-embedding-3-small",
            dimension=1536,  # OpenAI small 维度
        )
    
    @classmethod
    def hybrid_siliconflow(cls, api_key: str) -> 'EmbeddingConfig':
        """Hybrid 模式 - 硅基流动"""
        return cls(
            backend=EmbeddingBackendType.SILICONFLOW,
            api_key=api_key,
            api_base="https://api.siliconflow.cn/v1",
            api_model="BAAI/bge-large-zh-v1.5",
            dimension=1024,  # BGE-large 维度
        )
    
    @classmethod
    def full(cls) -> 'EmbeddingConfig':
        """完整模式配置（本地模型）"""
        return cls(
            backend=EmbeddingBackendType.LOCAL,
            local_model="paraphrase-multilingual-MiniLM-L12-v2",
            dimension=384,
        )


class EmbeddingBackend(ABC):
    """Embedding 后端抽象基类"""
    
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._cache = {}  # 简单缓存
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        pass
    
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """后端是否可用"""
        pass
    
    @abstractmethod
    def encode(self, text: str) -> np.ndarray:
        """单文本编码"""
        pass
    
    @abstractmethod
    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """批量编码"""
        pass
    
    def encode_with_cache(self, text: str) -> np.ndarray:
        """带缓存的编码"""
        if not self.config.cache_embeddings:
            return self.encode(text)
        
        cache_key = hash(text)
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        embedding = self.encode(text)
        
        # LRU 简单实现：超出大小时清空一半
        if len(self._cache) >= self.config.max_cache_size:
            keys = list(self._cache.keys())[:len(self._cache) // 2]
            for k in keys:
                del self._cache[k]
        
        self._cache[cache_key] = embedding
        return embedding
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()


class NoneBackend(EmbeddingBackend):
    """空后端（轻量模式）"""
    
    @property
    def dimension(self) -> int:
        return 0
    
    @property
    def is_available(self) -> bool:
        return True
    
    def encode(self, text: str) -> np.ndarray:
        raise RuntimeError("轻量模式不支持向量编码，请切换到 Hybrid 或完整模式")
    
    def encode_batch(self, texts: List[str]) -> np.ndarray:
        raise RuntimeError("轻量模式不支持向量编码，请切换到 Hybrid 或完整模式")
