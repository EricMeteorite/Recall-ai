"""FAISS IVF 向量索引

Phase 3.5: 企业级性能引擎
Phase 3.6: 升级为 IVF-HNSW，召回率从 90-95% 提升到 95-99%

支持大规模向量检索（50万-10亿向量），使用磁盘+内存混合存储。

特点：
- 支持亿级向量（Phase 3.6: 1-10亿）
- 磁盘 + 内存混合存储
- 可配置的精度/速度权衡
- 多租户隔离（通过 user_id 过滤）
- Phase 3.6: HNSW quantizer 提升召回率

适用场景：
- 50万-10亿向量
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
    
    Phase 3.6 升级：使用 HNSW 作为 quantizer，召回率从 90-95% 提升到 95-99%
    
    特点：
    - 支持亿级向量（Phase 3.6: 1-10亿）
    - 磁盘 + 内存混合存储
    - 可配置的精度/速度权衡
    - 多租户隔离（通过 user_id 过滤）
    - Phase 3.6: HNSW quantizer 提升召回率
    
    适用场景：
    - 50万-10亿向量
    - 内存受限环境
    
    使用方式：
        index = VectorIndexIVF(
            data_path="./recall_data/indexes",
            dimension=1024,
            nlist=100,
            nprobe=10,
            # Phase 3.6: HNSW 参数（可选）
            use_hnsw_quantizer=True,
            hnsw_m=32,
            hnsw_ef_construction=200,
            hnsw_ef_search=64
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
        min_train_size: int = None,  # 最小训练样本数，默认为 nlist
        # Phase 3.6 新增：HNSW 参数
        use_hnsw_quantizer: bool = True,     # 是否使用 HNSW 作为 quantizer（推荐）
        hnsw_m: int = 32,                    # HNSW 图连接数（越大召回越高）
        hnsw_ef_construction: int = 200,     # 构建精度
        hnsw_ef_search: int = 64,            # 搜索精度（越大召回越高）
    ):
        """初始化 IVF 索引
        
        Args:
            data_path: 数据存储路径
            dimension: 向量维度
            nlist: 聚类中心数量（越大精度越高但速度越慢）
            nprobe: 搜索时检查的聚类数（越大召回率越高但速度越慢）
            use_gpu: 是否使用 GPU
            min_train_size: 最小训练样本数
            use_hnsw_quantizer: 是否使用 HNSW 作为 quantizer（Phase 3.6，提升召回率到 95-99%）
            hnsw_m: HNSW 图连接数（越大召回越高，推荐 32）
            hnsw_ef_construction: HNSW 构建精度（越大越精确但构建越慢，推荐 200）
            hnsw_ef_search: HNSW 搜索精度（越大召回越高但搜索越慢，推荐 64）
            
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
        
        # Phase 3.6: HNSW 参数
        self.use_hnsw_quantizer = use_hnsw_quantizer
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construction = hnsw_ef_construction
        self.hnsw_ef_search = hnsw_ef_search
        
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
        
        # v7.0.12: atexit 注册（之前遗漏，进程退出时可能丢失未保存的 pending 向量）
        import atexit
        atexit.register(self._atexit_save)
        
        logger.info(f"[VectorIndexIVF] Initialized at {data_path}, dimension={dimension}, nlist={nlist}")
    
    def _atexit_save(self):
        """atexit 回调 — 安全保存"""
        try:
            # v7.0.12: 检查数据目录是否仍存在（pytest 清理临时目录后 atexit 仍会触发）
            if not os.path.exists(self.data_path):
                return
            if self._pending_vectors:
                self._save_pending()
            self._save()
        except Exception:
            pass
    
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
            
            # Phase 3.6: 如果加载的索引使用 HNSW quantizer，更新 efSearch
            if self.use_hnsw_quantizer and hasattr(self.index, 'quantizer'):
                quantizer = self.index.quantizer
                if hasattr(quantizer, 'hnsw'):
                    quantizer.hnsw.efSearch = self.hnsw_ef_search
            
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
        """创建新索引
        
        Phase 3.6: 支持两种 quantizer 模式：
        - HNSW quantizer（默认）：召回率 95-99%，适合大规模数据
        - Flat quantizer（回退）：召回率 90-95%，兼容旧版本
        """
        if self.use_hnsw_quantizer:
            # Phase 3.6: 使用 HNSW 作为 quantizer（召回率 95-99%）
            quantizer = faiss.IndexHNSWFlat(self.dimension, self.hnsw_m)
            quantizer.hnsw.efConstruction = self.hnsw_ef_construction
            quantizer.hnsw.efSearch = self.hnsw_ef_search
            _safe_print(f"[VectorIndexIVF] Using HNSW quantizer (M={self.hnsw_m}, "
                       f"efConstruction={self.hnsw_ef_construction}, efSearch={self.hnsw_ef_search})")
        else:
            # 传统 Flat quantizer（召回率 90-95%）
            quantizer = faiss.IndexFlatIP(self.dimension)
            _safe_print("[VectorIndexIVF] Using Flat quantizer (legacy mode)")
        
        self.index = faiss.IndexIVFFlat(
            quantizer,
            self.dimension,
            self.nlist,
            faiss.METRIC_INNER_PRODUCT
        )
        self.index.nprobe = self.nprobe
        
        logger.info(f"[VectorIndexIVF] Created new IVF index with nlist={self.nlist}, "
                   f"hnsw={self.use_hnsw_quantizer}")
    
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
                
                # v7.0.6: 过滤已标记删除的向量（之前缺失，导致幽灵数据出现在搜索结果中）
                if doc_id in self.doc_metadata and self.doc_metadata[doc_id].get('_deleted'):
                    continue
                
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
            # v7.0.13: 检查数据目录是否仍存在（pytest 临时目录可能已被清理）
            if not os.path.exists(self.data_path):
                return
            # 保存索引
            faiss.write_index(self.index, self.index_file)
            
            # 保存 ID 映射
            np.save(self.mapping_file, np.array(self.id_mapping, dtype=object))
            
            # 保存元数据（v7.0.10: 原子写入）
            from recall.utils.atomic_write import atomic_json_dump
            atomic_json_dump(self.doc_metadata, self.metadata_file, ensure_ascii=False)
            
            logger.debug(f"[VectorIndexIVF] Saved {self.index.ntotal} vectors")
        except Exception as e:
            logger.error(f"[VectorIndexIVF] Failed to save: {e}")
    
    def _save_pending(self):
        """保存待处理的向量"""
        try:
            # v7.0.13: 检查数据目录是否仍存在
            if not os.path.exists(self.data_path):
                return
            pending_data = {
                'vectors': self._pending_vectors,
                'ids': self._pending_ids
            }
            np.save(self.pending_file, pending_data)
        except Exception as e:
            logger.error(f"[VectorIndexIVF] Failed to save pending vectors: {e}")
    
    def flush(self):
        """刷新待处理的向量到索引
        
        强制将所有待处理向量训练并添加到索引中。
        如果待处理向量数量不足以训练（< min_train_size），
        将使用 IndexFlatIP 作为降级方案或强制训练。
        
        Returns:
            int: 已刷新的向量数量
        """
        if not self._pending_vectors:
            return 0
        
        count = len(self._pending_vectors)
        
        if not self.index.is_trained:
            if count >= self.nlist:
                # 足够的向量，正常训练
                self._train_and_add()
            else:
                # 向量不足，强制训练（会降低质量但能工作）
                _safe_print(f"[VectorIndexIVF] [WARN] Force training with only {count} vectors (nlist={self.nlist})")
                vectors = np.array(self._pending_vectors, dtype=np.float32)
                
                # 创建临时的 Flat 索引来"训练"
                if count < self.nlist:
                    # 复制向量以达到最小训练数量
                    repeat_times = (self.nlist // count) + 1
                    training_vectors = np.tile(vectors, (repeat_times, 1))[:self.nlist]
                    self.index.train(training_vectors)
                else:
                    self.index.train(vectors)
                
                # 添加原始向量
                self.index.add(vectors)
                self.id_mapping.extend(self._pending_ids)
                
                # 清空待处理
                self._pending_vectors = []
                self._pending_ids = []
                
                if os.path.exists(self.pending_file):
                    os.remove(self.pending_file)
                
                self._save()
                _safe_print(f"[VectorIndexIVF] [DONE] Force flush complete, {self.index.ntotal} vectors indexed")
        else:
            # 索引已训练，直接添加
            vectors = np.array(self._pending_vectors, dtype=np.float32)
            self.index.add(vectors)
            self.id_mapping.extend(self._pending_ids)
            
            self._pending_vectors = []
            self._pending_ids = []
            
            if os.path.exists(self.pending_file):
                os.remove(self.pending_file)
            
            self._save()
            _safe_print(f"[VectorIndexIVF] [DONE] Flush complete, {self.index.ntotal} vectors indexed")
        
        return count
    
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
        else:
            # v7.0.6: 即使没有 metadata 条目，也要创建一个并标记删除
            # （add() 在没有 metadata/user_id 时不会写 doc_metadata，导致 remove 静默失败）
            self.doc_metadata[doc_id] = {'_deleted': True}
        self._save()
        return True
    
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
        stats = {
            "size": self.size,
            "pending_size": self.pending_size,
            "is_trained": self.is_trained,
            "dimension": self.dimension,
            "nlist": self.nlist,
            "nprobe": self.nprobe,
            "metadata_count": len(self.doc_metadata),
            # Phase 3.6: HNSW 参数
            "use_hnsw_quantizer": self.use_hnsw_quantizer,
        }
        if self.use_hnsw_quantizer:
            stats.update({
                "hnsw_m": self.hnsw_m,
                "hnsw_ef_construction": self.hnsw_ef_construction,
                "hnsw_ef_search": self.hnsw_ef_search,
            })
        return stats
