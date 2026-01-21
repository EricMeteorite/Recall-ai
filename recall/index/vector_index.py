"""向量索引 - 支持多种 Embedding 后端"""

import os
import json
from typing import List, Tuple, Optional, Any, Dict

import numpy as np

from ..embedding import EmbeddingBackend, EmbeddingConfig, create_embedding_backend
from ..embedding.base import EmbeddingBackendType


class VectorIndex:
    """向量索引 - 使用 FAISS 实现高效相似度搜索
    
    支持三种模式：
    1. 完整模式（local）: 本地 sentence-transformers，~800MB 内存
    2. Hybrid 模式（openai/siliconflow）: API 调用，~50MB 内存
    3. 轻量模式（none）: 禁用向量索引
    """
    
    def __init__(
        self, 
        data_path: str, 
        embedding_config: Optional[EmbeddingConfig] = None
    ):
        """初始化向量索引
        
        Args:
            data_path: 数据存储路径
            embedding_config: Embedding 配置，为 None 时自动选择
        """
        self.data_path = data_path
        self.index_dir = os.path.join(data_path, 'indexes')
        self.index_file = os.path.join(self.index_dir, 'vector_index.faiss')
        self.mapping_file = os.path.join(self.index_dir, 'vector_mapping.json')
        self.config_file = os.path.join(self.index_dir, 'vector_config.json')
        
        # Embedding 后端
        self.embedding_config = embedding_config
        self._embedding_backend: Optional[EmbeddingBackend] = None
        
        # FAISS 索引
        self._index = None
        self.turn_mapping: List[int] = []  # FAISS 内部 ID → turn_id
        
        # 是否启用
        self._enabled = True
        
        self._setup()
    
    def _setup(self):
        """初始化设置"""
        os.makedirs(self.index_dir, exist_ok=True)
        
        # 加载或创建配置
        if self.embedding_config is None:
            self.embedding_config = self._load_or_create_config()
        
        # 检查是否启用
        if self.embedding_config.backend == EmbeddingBackendType.NONE:
            self._enabled = False
            print("[VectorIndex] 轻量模式，向量索引已禁用")
    
    def _load_or_create_config(self) -> EmbeddingConfig:
        """加载已有配置或自动选择"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                return EmbeddingConfig(
                    backend=EmbeddingBackendType(data.get('backend', 'local')),
                    local_model=data.get('local_model', 'paraphrase-multilingual-MiniLM-L12-v2'),
                    api_model=data.get('api_model', 'text-embedding-3-small'),
                    dimension=data.get('dimension', 384)
                )
            except Exception as e:
                print(f"[VectorIndex] 配置加载失败，自动选择: {e}")
        
        # 自动选择
        from ..embedding.factory import auto_select_backend
        return auto_select_backend()
    
    def _save_config(self):
        """保存配置"""
        data = {
            'backend': self.embedding_config.backend.value,
            'local_model': self.embedding_config.local_model,
            'api_model': self.embedding_config.api_model,
            'dimension': self.dimension
        }
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    @property
    def enabled(self) -> bool:
        """是否启用向量索引"""
        return self._enabled
    
    @property
    def embedding_backend(self) -> EmbeddingBackend:
        """获取 Embedding 后端（懒加载）"""
        if self._embedding_backend is None:
            self._embedding_backend = create_embedding_backend(self.embedding_config)
        return self._embedding_backend
    
    @property
    def dimension(self) -> int:
        """获取向量维度"""
        return self.embedding_backend.dimension
    
    @property
    def index(self):
        """获取 FAISS 索引（懒加载）"""
        if self._index is None:
            self._load()
        return self._index
    
    def _load(self):
        """加载索引"""
        if not self._enabled:
            return
        
        import faiss
        
        if os.path.exists(self.index_file):
            self._index = faiss.read_index(self.index_file)
            
            # 检查维度是否匹配
            if self._index.d != self.dimension:
                print(f"[VectorIndex] 警告: 索引维度({self._index.d})与当前模型维度({self.dimension})不匹配")
                print(f"[VectorIndex] 正在重建索引...")
                self._index = faiss.IndexFlatIP(self.dimension)
                self.turn_mapping = []
                self._save_config()
            elif os.path.exists(self.mapping_file):
                with open(self.mapping_file, 'r') as f:
                    self.turn_mapping = json.load(f)
        else:
            # 创建新索引
            self._index = faiss.IndexFlatIP(self.dimension)
            self._save_config()
    
    def _save(self):
        """保存索引"""
        if not self._enabled or self._index is None:
            return
        
        import faiss
        
        faiss.write_index(self._index, self.index_file)
        
        with open(self.mapping_file, 'w') as f:
            json.dump(self.turn_mapping, f)
    
    def encode(self, text: str) -> np.ndarray:
        """文本转向量"""
        if not self._enabled:
            raise RuntimeError("向量索引未启用")
        return self.embedding_backend.encode_with_cache(text)
    
    def add(self, doc_id: Any, embedding: np.ndarray):
        """添加向量"""
        if not self._enabled:
            return
        
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        self.index.add(embedding)
        self.turn_mapping.append(doc_id)
        
        # 每 100 次添加保存一次
        if len(self.turn_mapping) % 100 == 0:
            self._save()
    
    def add_text(self, doc_id: Any, text: str):
        """直接添加文本"""
        if not self._enabled:
            return
        embedding = self.encode(text)
        self.add(doc_id, embedding)
    
    def search(self, query: str, top_k: int = 20) -> List[Tuple[Any, float]]:
        """搜索最相似的文档"""
        if not self._enabled:
            return []
        
        if self.index.ntotal == 0:
            return []
        
        query_embedding = self.encode(query).reshape(1, -1)
        
        distances, indices = self.index.search(
            query_embedding, 
            min(top_k, self.index.ntotal)
        )
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self.turn_mapping):
                doc_id = self.turn_mapping[idx]
                results.append((doc_id, float(dist)))
        
        return results
    
    def search_by_embedding(self, embedding: np.ndarray, top_k: int = 20) -> List[Tuple[Any, float]]:
        """通过向量搜索"""
        if not self._enabled:
            return []
        
        if self.index.ntotal == 0:
            return []
        
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        distances, indices = self.index.search(
            embedding, 
            min(top_k, self.index.ntotal)
        )
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self.turn_mapping):
                doc_id = self.turn_mapping[idx]
                results.append((doc_id, float(dist)))
        
        return results
    
    def get_vector_by_doc_id(self, doc_id: Any) -> Optional[np.ndarray]:
        """通过文档ID获取已存储的向量
        
        用于 L6 精排等场景，避免重复调用 encode() API
        
        Args:
            doc_id: 文档ID
            
        Returns:
            存储的向量，如果不存在则返回 None
        """
        if not self._enabled or self._index is None:
            return None
        
        try:
            # 查找 doc_id 在 turn_mapping 中的索引位置
            if doc_id in self.turn_mapping:
                idx = self.turn_mapping.index(doc_id)
                # 使用 FAISS 的 reconstruct 方法获取已存储的向量
                return self.index.reconstruct(idx)
        except Exception:
            pass
        return None
    
    def get_vectors_by_doc_ids(self, doc_ids: List[Any]) -> Dict[Any, np.ndarray]:
        """批量获取已存储的向量
        
        Args:
            doc_ids: 文档ID列表
            
        Returns:
            文档ID到向量的映射
        """
        if not self._enabled or self._index is None:
            return {}
        
        result = {}
        # 构建 doc_id -> index 的映射（避免重复查找）
        doc_id_to_idx = {}
        for idx, did in enumerate(self.turn_mapping):
            if did in doc_ids:
                doc_id_to_idx[did] = idx
        
        # 批量获取向量
        for doc_id in doc_ids:
            if doc_id in doc_id_to_idx:
                try:
                    idx = doc_id_to_idx[doc_id]
                    result[doc_id] = self.index.reconstruct(idx)
                except Exception:
                    pass
        
        return result
    
    def close(self):
        """关闭并保存"""
        self._save()
        if self._embedding_backend:
            self._embedding_backend.clear_cache()
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'enabled': self._enabled,
            'backend': self.embedding_config.backend.value if self.embedding_config else 'unknown',
            'dimension': self.dimension if self._enabled else 0,
            'total_vectors': self.index.ntotal if self._enabled and self._index else 0,
            'model': (
                self.embedding_config.local_model 
                if self.embedding_config.backend == EmbeddingBackendType.LOCAL 
                else self.embedding_config.api_model
            ) if self.embedding_config else 'unknown'
        }
