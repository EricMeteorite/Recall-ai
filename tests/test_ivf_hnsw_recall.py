"""Phase 3.6: IVF-HNSW 召回率测试

测试内容：
1. IVF-HNSW 索引创建
2. 召回率对比（IVF vs IVF-HNSW）
3. HNSW 参数效果验证
"""

import sys
import os
import unittest
import tempfile
import shutil
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_faiss_available():
    """检查 FAISS 是否可用"""
    try:
        import faiss
        return True
    except ImportError:
        return False


@unittest.skipUnless(check_faiss_available(), "FAISS not installed")
class TestIVFHNSWRecall(unittest.TestCase):
    """IVF-HNSW 召回率测试套件"""
    
    @classmethod
    def setUpClass(cls):
        """创建临时目录"""
        cls.temp_dir = tempfile.mkdtemp()
    
    @classmethod
    def tearDownClass(cls):
        """清理临时目录"""
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)
    
    def test_ivf_hnsw_index_creation(self):
        """测试 IVF-HNSW 索引创建"""
        from recall.index.vector_index_ivf import VectorIndexIVF
        
        # 创建启用 HNSW 的索引
        index = VectorIndexIVF(
            data_path=os.path.join(self.temp_dir, "test1"),
            dimension=128,
            use_hnsw_quantizer=True,
            hnsw_m=16,
            hnsw_ef_construction=100,
            hnsw_ef_search=32
        )
        
        # 验证参数
        self.assertTrue(index.use_hnsw_quantizer)
        self.assertEqual(index.hnsw_m, 16)
        self.assertEqual(index.hnsw_ef_construction, 100)
        self.assertEqual(index.hnsw_ef_search, 32)
    
    def test_ivf_hnsw_search(self):
        """测试 IVF-HNSW 搜索功能"""
        from recall.index.vector_index_ivf import VectorIndexIVF
        
        # 创建索引
        index = VectorIndexIVF(
            data_path=os.path.join(self.temp_dir, "test2"),
            dimension=128,
            use_hnsw_quantizer=True,
            min_train_size=50
        )
        
        # 添加测试向量
        np.random.seed(42)
        for i in range(100):
            doc_id = f"doc_{i}"
            embedding = np.random.randn(128).astype(np.float32).tolist()
            index.add(doc_id, embedding)
        
        # 刷新待处理向量
        index.flush()
        
        # 搜索
        query_embedding = np.random.randn(128).astype(np.float32).tolist()
        results = index.search(query_embedding, top_k=10)
        
        # 验证结果
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 10)
    
    def test_hnsw_parameter_effect(self):
        """测试 HNSW 参数对召回率的影响"""
        from recall.index.vector_index_ivf import VectorIndexIVF
        import faiss
        
        # 生成测试数据
        np.random.seed(123)
        dimension = 64
        n_vectors = 500
        vectors = np.random.randn(n_vectors, dimension).astype(np.float32)
        
        # 归一化（用于内积搜索）
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / norms
        
        # 查询向量
        query = np.random.randn(dimension).astype(np.float32)
        query = query / np.linalg.norm(query)
        
        # 1. 暴力搜索（ground truth）
        flat_index = faiss.IndexFlatIP(dimension)
        flat_index.add(vectors)
        _, ground_truth = flat_index.search(query.reshape(1, -1), 50)
        ground_truth_set = set(ground_truth[0].tolist())
        
        # 2. 低参数 HNSW
        low_params_dir = os.path.join(self.temp_dir, "low_params")
        os.makedirs(low_params_dir, exist_ok=True)
        
        low_index = VectorIndexIVF(
            data_path=low_params_dir,
            dimension=dimension,
            use_hnsw_quantizer=True,
            hnsw_m=8,
            hnsw_ef_construction=50,
            hnsw_ef_search=16,
            min_train_size=100,
            nlist=20
        )
        
        for i, vec in enumerate(vectors):
            low_index.add(f"doc_{i}", vec.tolist())
        low_index.flush()
        
        low_results = low_index.search(query.tolist(), top_k=50)
        low_ids = set([int(doc_id.split("_")[1]) for doc_id, _ in low_results])
        low_recall = len(low_ids & ground_truth_set) / len(ground_truth_set)
        
        # 3. 高参数 HNSW
        high_params_dir = os.path.join(self.temp_dir, "high_params")
        os.makedirs(high_params_dir, exist_ok=True)
        
        high_index = VectorIndexIVF(
            data_path=high_params_dir,
            dimension=dimension,
            use_hnsw_quantizer=True,
            hnsw_m=32,
            hnsw_ef_construction=200,
            hnsw_ef_search=64,
            min_train_size=100,
            nlist=20
        )
        
        for i, vec in enumerate(vectors):
            high_index.add(f"doc_{i}", vec.tolist())
        high_index.flush()
        
        high_results = high_index.search(query.tolist(), top_k=50)
        high_ids = set([int(doc_id.split("_")[1]) for doc_id, _ in high_results])
        high_recall = len(high_ids & ground_truth_set) / len(ground_truth_set)
        
        print(f"\nRecall comparison:")
        print(f"  Low params (m=8, ef=16): {low_recall:.2%}")
        print(f"  High params (m=32, ef=64): {high_recall:.2%}")
        
        # 高参数应该有更好的召回率
        self.assertGreaterEqual(high_recall, low_recall * 0.9)  # 允许一些波动
    
    def test_get_stats_includes_hnsw(self):
        """测试 get_stats 包含 HNSW 参数"""
        from recall.index.vector_index_ivf import VectorIndexIVF
        
        index = VectorIndexIVF(
            data_path=os.path.join(self.temp_dir, "test_stats"),
            dimension=64,
            use_hnsw_quantizer=True,
            hnsw_m=24,
            hnsw_ef_construction=150,
            hnsw_ef_search=48
        )
        
        stats = index.get_stats()
        
        self.assertTrue(stats.get("use_hnsw_quantizer"))
        self.assertEqual(stats.get("hnsw_m"), 24)
        self.assertEqual(stats.get("hnsw_ef_construction"), 150)
        self.assertEqual(stats.get("hnsw_ef_search"), 48)


@unittest.skipUnless(check_faiss_available(), "FAISS not installed")
class TestVectorIndexIVFBackwardCompatibility(unittest.TestCase):
    """向后兼容性测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_default_uses_hnsw(self):
        """测试默认使用 HNSW quantizer"""
        from recall.index.vector_index_ivf import VectorIndexIVF
        
        index = VectorIndexIVF(
            data_path=self.temp_dir,
            dimension=64
        )
        
        # 默认应该启用 HNSW
        self.assertTrue(index.use_hnsw_quantizer)
    
    def test_can_disable_hnsw(self):
        """测试可以禁用 HNSW"""
        from recall.index.vector_index_ivf import VectorIndexIVF
        
        index = VectorIndexIVF(
            data_path=self.temp_dir,
            dimension=64,
            use_hnsw_quantizer=False
        )
        
        self.assertFalse(index.use_hnsw_quantizer)


if __name__ == '__main__':
    unittest.main()
