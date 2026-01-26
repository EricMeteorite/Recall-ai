"""Phase 3.6: RRF (Reciprocal Rank Fusion) 单元测试

测试内容：
1. 基本 RRF 融合功能
2. 权重参数效果
3. 空结果处理
4. 多路结果去重
5. 分数计算正确性
6. 加权分数融合
7. 多路命中加分
"""

import sys
import os
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recall.retrieval.rrf_fusion import reciprocal_rank_fusion, weighted_score_fusion


class TestRRFFusion(unittest.TestCase):
    """RRF 融合测试套件"""
    
    def test_basic_fusion(self):
        """测试基本融合功能"""
        results_list = [
            [("doc1", 0.9), ("doc2", 0.8), ("doc3", 0.7)],  # 路径1
            [("doc2", 0.85), ("doc4", 0.75), ("doc1", 0.6)],  # 路径2
            [("doc3", 0.95), ("doc5", 0.65), ("doc2", 0.5)],  # 路径3
        ]
        
        fused = reciprocal_rank_fusion(results_list)
        
        # 验证所有文档都被包含
        doc_ids = [doc_id for doc_id, _ in fused]
        self.assertIn("doc1", doc_ids)
        self.assertIn("doc2", doc_ids)
        self.assertIn("doc3", doc_ids)
        self.assertIn("doc4", doc_ids)
        self.assertIn("doc5", doc_ids)
        
        # doc2 出现在所有三路中，应该排名较高
        doc2_rank = doc_ids.index("doc2")
        self.assertLess(doc2_rank, 3, "doc2 应该在前3名")
    
    def test_rrf_k_parameter(self):
        """测试 k 参数效果"""
        results_list = [
            [("doc1", 0.9), ("doc2", 0.8)],
            [("doc2", 0.85), ("doc3", 0.75)],
        ]
        
        # 较小的 k 值会让排名差异更大
        fused_k10 = reciprocal_rank_fusion(results_list, k=10)
        fused_k100 = reciprocal_rank_fusion(results_list, k=100)
        
        # 获取 doc1 和 doc2 的分数
        scores_k10 = {doc_id: score for doc_id, score in fused_k10}
        scores_k100 = {doc_id: score for doc_id, score in fused_k100}
        
        # 验证分数差异：k=10 时差异应该更大
        diff_k10 = abs(scores_k10.get("doc2", 0) - scores_k10.get("doc1", 0))
        diff_k100 = abs(scores_k100.get("doc2", 0) - scores_k100.get("doc1", 0))
        
        # 较大的 k 值会使分数差异更平滑
        self.assertGreater(diff_k10, diff_k100)
    
    def test_weights(self):
        """测试权重参数"""
        results_list = [
            [("doc1", 0.9)],  # 路径1
            [("doc2", 0.9)],  # 路径2
        ]
        
        # 路径1 权重更高
        fused = reciprocal_rank_fusion(results_list, weights=[2.0, 1.0])
        
        scores = {doc_id: score for doc_id, score in fused}
        self.assertGreater(scores.get("doc1", 0), scores.get("doc2", 0))
    
    def test_empty_results(self):
        """测试空结果处理"""
        # 全空
        fused = reciprocal_rank_fusion([])
        self.assertEqual(fused, [])
        
        # 部分空
        results_list = [
            [("doc1", 0.9)],
            [],
            [("doc2", 0.8)],
        ]
        fused = reciprocal_rank_fusion(results_list)
        self.assertEqual(len(fused), 2)
    
    def test_single_path(self):
        """测试单路结果"""
        results_list = [
            [("doc1", 0.9), ("doc2", 0.8), ("doc3", 0.7)],
        ]
        
        fused = reciprocal_rank_fusion(results_list)
        
        # 顺序应该保持不变
        doc_ids = [doc_id for doc_id, _ in fused]
        self.assertEqual(doc_ids, ["doc1", "doc2", "doc3"])
    
    def test_score_calculation(self):
        """测试分数计算正确性"""
        results_list = [
            [("doc1", 0.9)],  # rank=1, score = 1/(60+1) = 0.01639
        ]
        
        fused = reciprocal_rank_fusion(results_list, k=60)
        
        self.assertEqual(len(fused), 1)
        doc_id, score = fused[0]
        self.assertEqual(doc_id, "doc1")
        self.assertAlmostEqual(score, 1.0 / (60 + 1), places=5)
    
    def test_multi_hit_bonus(self):
        """测试多路命中"""
        results_list = [
            [("doc1", 0.9), ("doc2", 0.8)],
            [("doc1", 0.85), ("doc3", 0.75)],
            [("doc1", 0.8), ("doc4", 0.7)],
        ]
        
        fused = reciprocal_rank_fusion(results_list)
        
        # doc1 出现在所有三路中，应该排名第一
        doc_ids = [doc_id for doc_id, _ in fused]
        self.assertEqual(doc_ids[0], "doc1")


class TestWeightedScoreFusion(unittest.TestCase):
    """加权分数融合测试套件"""
    
    def test_basic_weighted_fusion(self):
        """测试基本加权融合"""
        results_list = [
            [("doc1", 0.9), ("doc2", 0.8)],
            [("doc2", 0.85), ("doc3", 0.75)],
        ]
        
        fused = weighted_score_fusion(results_list)
        
        # 验证所有文档都被包含
        doc_ids = [doc_id for doc_id, _ in fused]
        self.assertIn("doc1", doc_ids)
        self.assertIn("doc2", doc_ids)
        self.assertIn("doc3", doc_ids)
    
    def test_normalization(self):
        """测试分数归一化"""
        results_list = [
            [("doc1", 100.0), ("doc2", 50.0)],  # 原始分数很大
            [("doc3", 0.9), ("doc4", 0.5)],     # 原始分数小
        ]
        
        fused = weighted_score_fusion(results_list, normalize=True)
        
        # 归一化后分数应该在合理范围内
        for doc_id, score in fused:
            self.assertLessEqual(score, 3.0)  # 权重1.0 + 多路加分
    
    def test_multi_hit_score_boost(self):
        """测试多路命中加分"""
        results_list = [
            [("doc1", 1.0)],
            [("doc1", 1.0)],
            [("doc2", 1.0)],
        ]
        
        fused = weighted_score_fusion(results_list)
        scores = {doc_id: score for doc_id, score in fused}
        
        # doc1 出现在两路中，应该有加分
        self.assertGreater(scores.get("doc1", 0), scores.get("doc2", 0))
    
    def test_empty_handling(self):
        """测试空结果处理"""
        fused = weighted_score_fusion([])
        self.assertEqual(fused, [])
        
        fused = weighted_score_fusion([[], []])
        self.assertEqual(fused, [])
    
    def test_custom_weights(self):
        """测试自定义权重"""
        results_list = [
            [("doc1", 1.0)],  # 高权重路径
            [("doc2", 1.0)],  # 低权重路径
        ]
        
        fused = weighted_score_fusion(results_list, weights=[2.0, 0.5])
        scores = {doc_id: score for doc_id, score in fused}
        
        # doc1 来自高权重路径
        self.assertGreater(scores.get("doc1", 0), scores.get("doc2", 0))


class TestRRFPerformance(unittest.TestCase):
    """RRF 性能测试"""
    
    def test_large_scale_fusion(self):
        """测试大规模融合性能"""
        import time
        
        # 模拟三路各 1000 个结果
        results_list = [
            [(f"doc_{i}_{j}", 1.0 - i * 0.001) for i in range(1000)]
            for j in range(3)
        ]
        
        start = time.time()
        fused = reciprocal_rank_fusion(results_list)
        elapsed = time.time() - start
        
        # 应该在 100ms 内完成
        self.assertLess(elapsed, 0.1, f"融合耗时 {elapsed:.3f}s 超过 100ms")
        
        # 验证结果数量
        self.assertGreater(len(fused), 0)


if __name__ == '__main__':
    unittest.main()
