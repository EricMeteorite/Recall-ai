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
    CUSTOM = "custom"         # 自定义 OpenAI 兼容 API
    NONE = "none"             # 禁用（Lite 模式）


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
    dimension: Optional[int] = 384  # 向量维度（None 时自动查表）
    batch_size: int = 32
    normalize: bool = True
    
    # 性能配置
    cache_embeddings: bool = True
    max_cache_size: int = 10000
    
    @classmethod
    def lite(cls) -> 'EmbeddingConfig':
        """Lite 模式配置（禁用向量索引）"""
        return cls(backend=EmbeddingBackendType.NONE)
    
    # 向后兼容别名
    @classmethod
    def lightweight(cls) -> 'EmbeddingConfig':
        """[已弃用] 请使用 lite()"""
        return cls.lite()
    
    # 模型维度映射（单一来源：从 api_backend.py 导入）
    @staticmethod
    def _get_model_dimensions() -> dict:
        try:
            from .api_backend import APIEmbeddingBackend
            return APIEmbeddingBackend.MODEL_DIMENSIONS
        except ImportError:
            # 兜底：最小维度表
            return {
                "text-embedding-3-small": 1536,
                "text-embedding-3-large": 3072,
                "text-embedding-ada-002": 1536,
                "BAAI/bge-large-zh-v1.5": 1024,
                "BAAI/bge-large-en-v1.5": 1024,
                "BAAI/bge-m3": 1024,
            }
    
    @classmethod
    def cloud_openai(cls, api_key: str, api_base: str = None, model: str = "text-embedding-3-small") -> 'EmbeddingConfig':
        """Cloud 模式 - OpenAI API"""
        dimension = cls._get_model_dimensions().get(model, 1536)
        return cls(
            backend=EmbeddingBackendType.OPENAI,
            api_key=api_key,
            api_base=api_base,  # 可自定义 base URL
            api_model=model,
            dimension=dimension,
        )
    
    # 向后兼容别名
    @classmethod
    def hybrid_openai(cls, api_key: str, api_base: str = None, model: str = "text-embedding-3-small") -> 'EmbeddingConfig':
        """[已弃用] 请使用 cloud_openai()"""
        return cls.cloud_openai(api_key, api_base, model)
    
    @classmethod
    def cloud_siliconflow(cls, api_key: str, model: str = "BAAI/bge-large-zh-v1.5") -> 'EmbeddingConfig':
        """Cloud 模式 - 硅基流动 API"""
        dimension = cls._get_model_dimensions().get(model, 1024)
        return cls(
            backend=EmbeddingBackendType.SILICONFLOW,
            api_key=api_key,
            api_base="https://api.siliconflow.cn/v1",
            api_model=model,
            dimension=dimension,
        )
    
    # 向后兼容别名
    @classmethod
    def hybrid_siliconflow(cls, api_key: str, model: str = "BAAI/bge-large-zh-v1.5") -> 'EmbeddingConfig':
        """[已弃用] 请使用 cloud_siliconflow()"""
        return cls.cloud_siliconflow(api_key, model)
    
    @classmethod
    def cloud_custom(cls, api_key: str, api_base: str, api_model: str, dimension: int = None) -> 'EmbeddingConfig':
        """Cloud 模式 - 自定义 OpenAI 兼容 API
        
        适用于：
        - OpenAI 中转站
        - Azure OpenAI
        - 本地部署的兼容 API（如 Ollama, vLLM）
        - 其他 OpenAI 兼容服务
        """
        return cls(
            backend=EmbeddingBackendType.CUSTOM,
            api_key=api_key,
            api_base=api_base,
            api_model=api_model,
            dimension=dimension,
        )
    
    # 向后兼容别名
    @classmethod
    def hybrid_custom(cls, api_key: str, api_base: str, api_model: str, dimension: int = 1536) -> 'EmbeddingConfig':
        """[已弃用] 请使用 cloud_custom()"""
        return cls.cloud_custom(api_key, api_base, api_model, dimension)
    
    @classmethod
    def local(cls) -> 'EmbeddingConfig':
        """Local 模式配置（本地模型）"""
        return cls(
            backend=EmbeddingBackendType.LOCAL,
            local_model="paraphrase-multilingual-MiniLM-L12-v2",
            dimension=384,
        )
    
    # 向后兼容别名
    @classmethod
    def full(cls) -> 'EmbeddingConfig':
        """[已弃用] 请使用 local()"""
        return cls.local()


class EmbeddingBackend(ABC):
    """Embedding 后端抽象基类"""
    
    def __init__(self, config: EmbeddingConfig, cache_dir: str = None):
        self.config = config
        self._cache = {}  # 内存缓存
        self._cache_dir = cache_dir
        self._disk_cache = {}  # 磁盘缓存（延迟加载）
        self._disk_cache_loaded = False
        
        # 如果配置了缓存目录，尝试加载磁盘缓存
        if cache_dir:
            self._load_disk_cache()
    
    def _load_disk_cache(self):
        """加载磁盘缓存"""
        if self._disk_cache_loaded or not self._cache_dir:
            return
        
        import os
        import pickle
        
        cache_file = os.path.join(self._cache_dir, 'embedding_cache.pkl')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    self._disk_cache = pickle.load(f)
                # 合并到内存缓存
                self._cache.update(self._disk_cache)
            except Exception:
                pass
        self._disk_cache_loaded = True
    
    def _save_disk_cache(self):
        """保存磁盘缓存"""
        if not self._cache_dir:
            return
        
        import os
        import pickle
        
        os.makedirs(self._cache_dir, exist_ok=True)
        cache_file = os.path.join(self._cache_dir, 'embedding_cache.pkl')
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self._cache, f)
        except Exception:
            pass
    
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
        """带缓存的编码（内存 + 磁盘持久化）"""
        if not self.config.cache_embeddings:
            return self.encode(text)
        
        # 确保磁盘缓存已加载
        if not self._disk_cache_loaded:
            self._load_disk_cache()
        
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
        
        # 每 50 次新缓存保存一次到磁盘
        if self._cache_dir and len(self._cache) % 50 == 0:
            self._save_disk_cache()
        
        return embedding
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()


class NoneBackend(EmbeddingBackend):
    """空后端（Lite 模式）"""
    
    @property
    def dimension(self) -> int:
        return 0
    
    @property
    def is_available(self) -> bool:
        return True
    
    def encode(self, text: str) -> np.ndarray:
        raise RuntimeError("Lite 模式不支持向量编码，请切换到 Cloud 或 Local 模式")
    
    def encode_batch(self, texts: List[str]) -> np.ndarray:
        raise RuntimeError("Lite 模式不支持向量编码，请切换到 Cloud 或 Local 模式")
