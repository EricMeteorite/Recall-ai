"""向量索引 - 语义相似度检索"""

import os
from typing import List, Tuple, Optional, Any

import numpy as np


class VectorIndex:
    """向量索引 - 使用FAISS实现高效相似度搜索"""
    
    def __init__(self, data_path: str, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        self.data_path = data_path
        self.index_dir = os.path.join(data_path, 'indexes')
        self.index_file = os.path.join(self.index_dir, 'vector_index.faiss')
        self.mapping_file = os.path.join(self.index_dir, 'vector_mapping.json')
        self.model_name = model_name
        
        # 延迟加载
        self._model = None
        self._index = None
        self._dimension = None
        self.turn_mapping: List[int] = []  # FAISS内部ID → turn_id
        
        self._setup_environment()
    
    def _setup_environment(self):
        """设置环境变量确保模型下载到项目目录"""
        from ..init import RecallInit
        model_cache_dir = os.path.join(RecallInit.get_data_root(), 'models', 'sentence-transformers')
        os.makedirs(model_cache_dir, exist_ok=True)
        os.environ['SENTENCE_TRANSFORMERS_HOME'] = model_cache_dir
    
    @property
    def model(self):
        """懒加载embedding模型"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model
    
    @property
    def dimension(self) -> int:
        """获取向量维度"""
        if self._dimension is None:
            self._dimension = self.model.get_sentence_embedding_dimension()
        return self._dimension
    
    @property
    def index(self):
        """懒加载FAISS索引"""
        if self._index is None:
            self._load()
        return self._index
    
    def _load(self):
        """加载索引"""
        import faiss
        
        if os.path.exists(self.index_file):
            self._index = faiss.read_index(self.index_file)
            
            import json
            if os.path.exists(self.mapping_file):
                with open(self.mapping_file, 'r') as f:
                    self.turn_mapping = json.load(f)
        else:
            # 创建新索引 (Inner Product for cosine similarity with normalized vectors)
            self._index = faiss.IndexFlatIP(self.dimension)
    
    def _save(self):
        """保存索引"""
        import faiss
        import json
        
        os.makedirs(self.index_dir, exist_ok=True)
        faiss.write_index(self._index, self.index_file)
        
        with open(self.mapping_file, 'w') as f:
            json.dump(self.turn_mapping, f)
    
    def encode(self, text: str) -> np.ndarray:
        """文本转向量"""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.astype('float32')
    
    def add(self, doc_id: Any, embedding: np.ndarray):
        """添加向量
        
        Args:
            doc_id: 文档ID（可以是 int 或 str）
            embedding: 向量
        """
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        self.index.add(embedding)
        self.turn_mapping.append(doc_id)
        
        # 每100次添加保存一次
        if len(self.turn_mapping) % 100 == 0:
            self._save()
    
    def add_text(self, doc_id: Any, text: str):
        """直接添加文本
        
        Args:
            doc_id: 文档ID（可以是 int 或 str）
            text: 文本内容
        """
        embedding = self.encode(text)
        self.add(doc_id, embedding)
    
    def search(self, query: str, top_k: int = 20) -> List[Tuple[Any, float]]:
        """搜索最相似的文档"""
        if self.index.ntotal == 0:
            return []
        
        query_embedding = self.encode(query).reshape(1, -1)
        
        # FAISS搜索
        distances, indices = self.index.search(query_embedding, min(top_k, self.index.ntotal))
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self.turn_mapping):
                doc_id = self.turn_mapping[idx]
                results.append((doc_id, float(dist)))
        
        return results
    
    def search_by_embedding(self, embedding: np.ndarray, top_k: int = 20) -> List[Tuple[Any, float]]:
        """通过向量搜索"""
        if self.index.ntotal == 0:
            return []
        
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)
        
        distances, indices = self.index.search(embedding, min(top_k, self.index.ntotal))
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0 and idx < len(self.turn_mapping):
                doc_id = self.turn_mapping[idx]
                results.append((doc_id, float(dist)))
        
        return results
