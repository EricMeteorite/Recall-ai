"""API Embedding 后端 - 支持 OpenAI 和硅基流动"""

import os
from typing import List, Optional
import numpy as np

from .base import EmbeddingBackend, EmbeddingConfig, EmbeddingBackendType


class APIEmbeddingBackend(EmbeddingBackend):
    """API Embedding 后端
    
    支持：
    - OpenAI text-embedding-3-small / text-embedding-3-large
    - 硅基流动 BAAI/bge-large-zh-v1.5
    - 其他 OpenAI 兼容 API
    
    优点：
    - 内存占用极低 (~50MB)
    - 无需下载大模型
    - 支持最新模型
    
    缺点：
    - 需要网络连接
    - 有 API 费用（很便宜）
    """
    
    # 模型维度映射
    MODEL_DIMENSIONS = {
        # OpenAI
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
        # 硅基流动
        "BAAI/bge-large-zh-v1.5": 1024,
        "BAAI/bge-large-en-v1.5": 1024,
        "BAAI/bge-m3": 1024,
    }
    
    # 默认 API 基地址
    DEFAULT_BASES = {
        EmbeddingBackendType.OPENAI: "https://api.openai.com/v1",
        EmbeddingBackendType.SILICONFLOW: "https://api.siliconflow.cn/v1",
    }
    
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._client = None
        
        # 确定 API 基地址
        self.api_base = config.api_base or self.DEFAULT_BASES.get(
            config.backend, 
            "https://api.openai.com/v1"
        )
        
        # 获取 API key
        self.api_key = config.api_key or self._get_api_key_from_env()
        
        # 确定维度
        self._dimension = self.MODEL_DIMENSIONS.get(
            config.api_model, 
            config.dimension
        )
    
    def _get_api_key_from_env(self) -> Optional[str]:
        """从环境变量获取 API key"""
        if self.config.backend == EmbeddingBackendType.OPENAI:
            return os.environ.get('OPENAI_API_KEY')
        elif self.config.backend == EmbeddingBackendType.SILICONFLOW:
            return os.environ.get('SILICONFLOW_API_KEY')
        return os.environ.get('EMBEDDING_API_KEY')
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def is_available(self) -> bool:
        """检查是否有 API key"""
        return bool(self.api_key)
    
    @property
    def client(self):
        """获取 OpenAI 客户端（兼容硅基流动）"""
        if self._client is None:
            if not self.is_available:
                raise ValueError(
                    f"未配置 API key。\n"
                    f"请设置环境变量或在配置中提供 api_key。\n"
                    f"OpenAI: OPENAI_API_KEY\n"
                    f"硅基流动: SILICONFLOW_API_KEY"
                )
            
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
        return self._client
    
    def encode(self, text: str) -> np.ndarray:
        """编码单个文本"""
        response = self.client.embeddings.create(
            model=self.config.api_model,
            input=text
        )
        embedding = np.array(response.data[0].embedding, dtype='float32')
        
        if self.config.normalize:
            embedding = embedding / np.linalg.norm(embedding)
        
        return embedding
    
    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """批量编码"""
        # API 通常有批量限制，分批处理
        all_embeddings = []
        batch_size = min(self.config.batch_size, 100)  # OpenAI 限制
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self.client.embeddings.create(
                model=self.config.api_model,
                input=batch
            )
            
            for item in response.data:
                embedding = np.array(item.embedding, dtype='float32')
                if self.config.normalize:
                    embedding = embedding / np.linalg.norm(embedding)
                all_embeddings.append(embedding)
        
        return np.array(all_embeddings)
