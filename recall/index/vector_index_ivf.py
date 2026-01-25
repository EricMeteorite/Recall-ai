"""FAISS IVF 向量索引

Phase 3.5: 企业级性能引擎

支持大规模向量检索（50万-500万向量），使用磁盘+内存混合存储。

特点：
- 支持百万级向量
- 磁盘 + 内存混合存储
- 可配置的精度/速度权衡
- 多租户隔离（通过 user_id 过滤）

适用场景：
- 50万-500万向量
- 内存受限环境
"""

import os
import json
import logging
from typing import List, Tuple, Optional, Dict, Any

import numpy as np


# 检查 FAISS 是否可用
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False


logger = logging.getLogger(__name__)


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class VectorIndexIVF:
    """FAISS IVF 向量索引 - 支持磁盘存储
    
    特点：
    - 支持百万级向量（50万-500万）
    - 磁盘 + 内存混合存储
    - 可配置的精度/速度权衡
    - 多租户隔离（通过 user_id 过滤）
    
    适用场景：
    - 50万-500万向量
    - 内存受限环境
    
    使用方式：
        index = VectorIndexIVF(
            data_path="./recall_data/indexes",
            dimension=1024,
            nlist=100,
            nprobe=10
        )
        
        # 添加向量
        index.add("doc_1", embedding, user_id="user_123")
        
        # 搜索（支持多租户过滤）
        results = index.search(query_embedding, top_k=10, user_id="user_123")
        
    ⚠️ 需要先安装 faiss：
        pip install faiss-cpu  # CPU 版本
        pip install faiss-gpu  # GPU 版本（需要 CUDA）
    """
    
    def __init__(
        self,
        data_path: str,
        dimension: int = 1024,
        nlist: int = 100,         # 聚类中心数量
        nprobe: int = 10,         # 搜索时检查的聚类数
        use_gpu: bool = False,
        min_train_size: int = None  # 最小训练样本数，默认为 nlist
    ):
        """初始化 IVF 索引
        
        Args:
            data_path: 数据存储路径
            dimension: 向量维度
            nlist: 聚类中心数量（越大精度越高但速度越慢）
            nprobe: 搜索时检查的聚类数（越大召回率越高但速度越慢）
            use_gpu: 是否使用 GPU
            min_train_size: 最小训练样本数
            
        Raises:
            ImportError: 如果 faiss 未安装
        """
        if not FAISS_AVAILABLE:
            raise ImportError(
                "FAISS not installed. Install with: pip install faiss-cpu\n"
                "Or for GPU: pip install faiss-gpu"
            )
        
        self.data_path = data_path
        self.dimension = dimension
        self.nlist = nlist
        self.nprobe = nprobe
        self.use_gpu = use_gpu
        self.min_train_size = min_train_size or nlist
        
        # 文件路径
        os.makedirs(data_path, exist_ok=True)
        self.index_file = os.path.join(data_path, "vector_index_ivf.faiss")
        self.mapping_file = os.path.join(data_path, "vector_mapping_ivf.npy")
        self.metadata_file = os.path.join(data_path, "vector_metadata_ivf.json")
        self.pending_file = os.path.join(data_path, "vector_pending_ivf.npy")
        
        # 内存数据
        self.index: Optional[faiss.Index] = None
        self.id_mapping: List[str] = []  # 内部 ID -> 文档 ID
        self.doc_metadata: Dict[str, Dict[str, Any]] = {}  # 文档 ID -> 元数据（含 user_id）
        self._pending_vectors: List[np.ndarray] = []  # 待训练的向量
        self._pending_ids: List[str] = []  # 待训练的文档 ID
        
        self._load_or_create()
        
        logger.info(f"[VectorIndexIVF] Initialized at {data_path}, dimension={dimension}, nlist={nlist}")
    
    def _load_or_create(self):
        """加载或创建索引"""
        if os.path.exists(self.index_file):
            self._load()
        else:
            self._create()
    
    def _load(self):
        """加载已有索引"""
        try:
            self.index = faiss.read_index(self.index_file)
            self.index.nprobe = self.nprobe
            
            # 加载 ID 映射
            if os.path.exists(self.mapping_file):
                self.id_mapping = list(np.load(self.mapping_file, allow_pickle=True))
            
            # 加载元数据
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    self.doc_metadata = json.load(f)
            
            # 加载待处理向量
            if os.path.exists(self.pending_file):
                pending_data = np.load(self.pending_file, allow_pickle=True).item()
                self._pending_vectors = list(pending_data.get('vectors', []))
                self._pending_ids = list(pending_data.get('ids', []))
            
            logger.info(f"[VectorIndexIVF] Loaded {self.index.ntotal} vectors, "
                       f"{len(self._pending_vectors)} pending")
        except Exception as e:
            logger.error(f"[VectorIndexIVF] Failed to load index: {e}")
            self._create()
    
    def _create(self):
        """创建新索引"""
        # 创建 IVF 索引
        quantizer = faiss.IndexFlatIP(self.dimension)  # 内积（用于归一化向量）
        self.index = faiss.IndexIVFFlat(
            quantizer,
            self.dimension,
            self.nlist,
            faiss.METRIC_INNER_PRODUCT
        )
        self.index.nprobe = self.nprobe
        
        logger.info(f"[VectorIndexIVF] Created new IVF index with nlist={self.nlist}")
    
    def add(
        self,
        doc_id: str,
        embedding: List[float],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """添加向量
        
        Args:
            doc_id: 文档ID
            embedding: 向量（列表或 numpy 数组）
            user_id: 用户ID（用于多租户隔离）
            metadata: 额外元数据
            
        Returns:
            是否成功添加
        """
        try:
            vector = np.array([embedding], dtype=np.float32)
            
            # 检查维度
            if vector.shape[1] != self.dimension:
                logger.warning(f"[VectorIndexIVF] Dimension mismatch: expected {self.dimension}, "
                              f"got {vector.shape[1]}")
                return False
            
            # 归一化（用于余弦相似度）
            faiss.normalize_L2(vector)
            
            # 存储元数据（用于用户过滤）
            meta = metadata.copy() if metadata else {}
            if user_id:
                meta['user_id'] = user_id
            if meta:
                self.doc_metadata[doc_id] = meta
            
            # 检查索引是否已训练
            if not self.index.is_trained:
                # IVF 索引需要训练，先累积数据
                self._pending_vectors.append(vector[0])
                self._pending_ids.append(doc_id)
                
                # 检查是否可以开始训练
                if len(self._pending_vectors) >= self.min_train_size:
                    self._train_and_add()
                else:
                    self._save_pending()
                
                return True
            
            # 已训练，直接添加
            self.index.add(vector)
            self.id_mapping.append(doc_id)
            self._save()
            
            return True
        except Exception as e:
            logger.error(f"[VectorIndexIVF] Failed to add vector for {doc_id}: {e}")
            return False
    
    def _train_and_add(self):
        """训练索引并添加待处理的向量"""
        if not self._pending_vectors:
            return
        
        vectors = np.array(self._pending_vectors, dtype=np.float32)
        
        _safe_print(f"[VectorIndexIVF] Training on {len(vectors)} vectors...")
        
        # 训练
        self.index.train(vectors)
        
        # 添加所有待处理向量
        self.index.add(vectors)
        self.id_mapping.extend(self._pending_ids)
        
        # 清空待处理
        self._pending_vectors = []
        self._pending_ids = []
        
        # 删除待处理文件
        if os.path.exists(self.pending_file):
            os.remove(self.pending_file)
        
        self._save()
        
        _safe_print(f"[VectorIndexIVF] [DONE] Training complete, {self.index.ntotal} vectors indexed")
    
    def train(self, embeddings: List[List[float]]):
        """手动训练索引（用于批量导入场景）
        
        Args:
            embeddings: 训练用的向量列表
        """
        if len(embeddings) < self.nlist:
            _safe_print(f"[VectorIndexIVF] [WARN] Not enough vectors for training "
                       f"({len(embeddings)} < {self.nlist})")
            return
        
        vectors = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)
        
        self.index.train(vectors)
        self._save()
        
        _safe_print(f"[VectorIndexIVF] [DONE] Manual training complete")
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        user_id: Optional[str] = None
    ) -> List[Tuple[str, float]]:
        """搜索相似向量
        
        Args:
            query_embedding: 查询向量
            top_k: 返回数量
            user_id: 用户ID过滤（多租户隔离）
            
        Returns:
            [(文档ID, 相似度分数), ...]
        """
        if not self.index.is_trained or self.index.ntotal == 0:
            return []
        
        try:
            query = np.array([query_embedding], dtype=np.float32)
            
            # 检查维度
            if query.shape[1] != self.dimension:
                logger.warning(f"[VectorIndexIVF] Query dimension mismatch: "
                              f"expected {self.dimension}, got {query.shape[1]}")
                return []
            
            faiss.normalize_L2(query)
            
            # 多取一些用于过滤（如果需要用户过滤）
            search_k = top_k * 5 if user_id else top_k
            search_k = min(search_k, self.index.ntotal)
            
            distances, indices = self.index.search(query, search_k)
            
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(self.id_mapping):
                    continue
                
                doc_id = self.id_mapping[idx]
                
                # 用户过滤（多租户隔离保障）
                if user_id and doc_id in self.doc_metadata:
                    meta = self.doc_metadata[doc_id]
                    if meta.get('user_id') != user_id:
                        continue  # 跳过其他用户的文档
                
                results.append((doc_id, float(dist)))
                
                if len(results) >= top_k:
                    break
            
            return results
        except Exception as e:
            logger.error(f"[VectorIndexIVF] Search failed: {e}")
            return []
    
    def _save(self):
        """保存索引和元数据"""
        try:
            # 保存索引
            faiss.write_index(self.index, self.index_file)
            
            # 保存 ID 映射
            np.save(self.mapping_file, np.array(self.id_mapping, dtype=object))
            
            # 保存元数据
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.doc_metadata, f, ensure_ascii=False)
            
            logger.debug(f"[VectorIndexIVF] Saved {self.index.ntotal} vectors")
        except Exception as e:
            logger.error(f"[VectorIndexIVF] Failed to save: {e}")
    
    def _save_pending(self):
        """保存待处理的向量"""
        try:
            pending_data = {
                'vectors': self._pending_vectors,
                'ids': self._pending_ids
            }
            np.save(self.pending_file, pending_data)
        except Exception as e:
            logger.error(f"[VectorIndexIVF] Failed to save pending vectors: {e}")
    
    def remove(self, doc_id: str) -> bool:
        """移除向量（标记删除，不实际删除）
        
        注意：FAISS IVF 不支持直接删除向量，这里只是标记。
        实际删除需要重建索引。
        
        Args:
            doc_id: 文档ID
            
        Returns:
            是否找到并标记
        """
        if doc_id in self.doc_metadata:
            self.doc_metadata[doc_id]['_deleted'] = True
            self._save()
            return True
        return False
    
    def rebuild(self):
        """重建索引（删除标记为删除的向量）"""
        if not self.index.is_trained or self.index.ntotal == 0:
            return
        
        # 收集未删除的向量
        valid_ids = []
        valid_indices = []
        
        for i, doc_id in enumerate(self.id_mapping):
            if doc_id not in self.doc_metadata or not self.doc_metadata.get(doc_id, {}).get('_deleted'):
                valid_ids.append(doc_id)
                valid_indices.append(i)
        
        if len(valid_indices) == len(self.id_mapping):
            logger.info("[VectorIndexIVF] No deleted vectors to rebuild")
            return
        
        # 获取有效向量
        valid_vectors = np.zeros((len(valid_indices), self.dimension), dtype=np.float32)
        for new_idx, old_idx in enumerate(valid_indices):
            valid_vectors[new_idx] = self.index.reconstruct(old_idx)
        
        # 重建索引
        self._create()
        self.index.train(valid_vectors)
        self.index.add(valid_vectors)
        self.id_mapping = valid_ids
        
        # 清理元数据
        self.doc_metadata = {k: v for k, v in self.doc_metadata.items() if not v.get('_deleted')}
        
        self._save()
        
        _safe_print(f"[VectorIndexIVF] [DONE] Rebuilt index with {self.index.ntotal} vectors")
    
    @property
    def size(self) -> int:
        """向量数量"""
        return self.index.ntotal if self.index else 0
    
    @property
    def pending_size(self) -> int:
        """待处理向量数量"""
        return len(self._pending_vectors)
    
    @property
    def is_trained(self) -> bool:
        """索引是否已训练"""
        return self.index.is_trained if self.index else False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            "size": self.size,
            "pending_size": self.pending_size,
            "is_trained": self.is_trained,
            "dimension": self.dimension,
            "nlist": self.nlist,
            "nprobe": self.nprobe,
            "metadata_count": len(self.doc_metadata),
        }
