"""ElevenLayerRetriever 测试模块 - Phase 3

测试策略：
1. 单元测试：测试每个层的独立功能
2. 集成测试：测试完整检索流程
3. 兼容性测试：验证与 EightLayerRetriever 的兼容性
4. 配置测试：验证 RetrievalConfig 的各种模式
"""

import pytest
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from unittest.mock import Mock, MagicMock

from recall.retrieval.config import (
    RetrievalConfig, LayerWeights, TemporalContext,
    LayerStats, RetrievalResultItem
)
from recall.retrieval.eleven_layer import (
    ElevenLayerRetriever, RetrievalLayer, EightLayerRetrieverCompat
)


# =========================================================================
# 测试 Fixtures
# =========================================================================

@pytest.fixture
def mock_bloom_filter():
    """模拟布隆过滤器"""
    bf = Mock()
    bf.__contains__ = Mock(side_effect=lambda x: x in ['apple', 'banana', 'coffee'])
    return bf


@pytest.fixture
def mock_inverted_index():
    """模拟倒排索引"""
    index = Mock()
    index.search_any = Mock(return_value=['doc1', 'doc2', 'doc3'])
    return index


@pytest.fixture
def mock_entity_index():
    """模拟实体索引"""
    index = Mock()
    # 返回模拟的 IndexedEntity 对象
    mock_entity = Mock()
    mock_entity.turn_references = ['doc2', 'doc4']
    index.get_related_turns = Mock(return_value=[mock_entity])
    return index


@pytest.fixture
def mock_ngram_index():
    """模拟 N-gram 索引"""
    index = Mock()
    index.search = Mock(return_value=['doc1', 'doc5'])
    index.raw_search = Mock(return_value=['doc6'])
    return index


@pytest.fixture
def mock_vector_index():
    """模拟向量索引"""
    index = Mock()
    index.enabled = True
    index.search = Mock(return_value=[('doc1', 0.95), ('doc3', 0.85), ('doc7', 0.75)])
    index.encode = Mock(return_value=[0.1, 0.2, 0.3, 0.4])
    index.get_vectors_by_doc_ids = Mock(return_value={
        'doc1': [0.1, 0.2, 0.3, 0.4],
        'doc3': [0.15, 0.25, 0.35, 0.45]
    })
    return index


@pytest.fixture
def mock_temporal_index():
    """模拟时态索引"""
    index = Mock()
    index.query_range = Mock(return_value=['doc1', 'doc2', 'doc3'])
    return index


@pytest.fixture
def mock_knowledge_graph():
    """模拟知识图谱"""
    graph = Mock()
    
    # 模拟节点
    mock_node = Mock()
    mock_node.uuid = 'node-uuid-1'
    graph.get_node_by_name = Mock(return_value=mock_node)
    
    # 模拟 BFS 结果
    mock_edge = Mock()
    mock_edge.source_episodes = ['doc8', 'doc9']
    graph.bfs = Mock(return_value={
        0: [('node-uuid-2', mock_edge)],
        1: []
    })
    
    return graph


@pytest.fixture
def content_store():
    """模拟内容存储"""
    contents = {
        'doc1': 'Alice likes coffee and tea.',
        'doc2': 'Bob works at a tech company.',
        'doc3': 'Charlie enjoys reading books.',
        'doc4': 'Alice met Bob at the coffee shop.',
        'doc5': 'The weather is nice today.',
        'doc6': 'Fallback search result.',
        'doc7': 'Vector search result.',
        'doc8': 'Graph traversal result 1.',
        'doc9': 'Graph traversal result 2.',
    }
    return lambda doc_id: contents.get(doc_id, '')


@pytest.fixture
def basic_retriever(
    mock_bloom_filter, mock_inverted_index, mock_entity_index,
    mock_ngram_index, mock_vector_index, content_store
):
    """基础检索器（不含 Phase 3 新依赖）"""
    return ElevenLayerRetriever(
        bloom_filter=mock_bloom_filter,
        inverted_index=mock_inverted_index,
        entity_index=mock_entity_index,
        ngram_index=mock_ngram_index,
        vector_index=mock_vector_index,
        content_store=content_store,
        config=RetrievalConfig.default()
    )


@pytest.fixture
def full_retriever(
    mock_bloom_filter, mock_inverted_index, mock_entity_index,
    mock_ngram_index, mock_vector_index, mock_temporal_index,
    mock_knowledge_graph, content_store
):
    """完整检索器（含 Phase 3 新依赖）"""
    return ElevenLayerRetriever(
        bloom_filter=mock_bloom_filter,
        inverted_index=mock_inverted_index,
        entity_index=mock_entity_index,
        ngram_index=mock_ngram_index,
        vector_index=mock_vector_index,
        temporal_index=mock_temporal_index,
        knowledge_graph=mock_knowledge_graph,
        content_store=content_store,
        config=RetrievalConfig.default()
    )


# =========================================================================
# RetrievalConfig 测试
# =========================================================================

class TestRetrievalConfig:
    """测试 RetrievalConfig"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = RetrievalConfig.default()
        
        # L1-L9 默认启用
        assert config.l1_enabled is True
        assert config.l2_enabled is True
        assert config.l9_enabled is True
        
        # L10-L11 默认关闭
        assert config.l10_enabled is False
        assert config.l11_enabled is False
        
        # Top-K 默认值
        assert config.final_top_k == 20
        assert config.l7_vector_top_k == 200
    
    def test_fast_config(self):
        """测试快速模式"""
        config = RetrievalConfig.fast()
        
        # 精排层应该关闭
        assert config.l8_enabled is False
        assert config.l9_enabled is False
        assert config.l10_enabled is False
        assert config.l11_enabled is False
        
        # 向量粗筛数量应该减少
        assert config.l7_vector_top_k == 100
    
    def test_accurate_config(self):
        """测试精准模式"""
        config = RetrievalConfig.accurate()
        
        # L10/L11 应该启用
        assert config.l10_enabled is True
        assert config.l11_enabled is True
        
        # 向量粗筛数量应该增加
        assert config.l7_vector_top_k == 300
    
    def test_to_dict_compatibility(self):
        """测试 to_dict 兼容性（映射到旧 8 层）"""
        config = RetrievalConfig.default()
        d = config.to_dict()
        
        # 应该有旧的 8 层配置键
        assert 'l1_enabled' in d
        assert 'l2_enabled' in d  # 旧 L2 = 新 L3
        assert 'l8_enabled' in d  # 旧 L8 = 新 L11
        
        # 映射关系验证
        assert d['l1_enabled'] == config.l1_enabled
        assert d['l2_enabled'] == config.l3_enabled  # 旧 L2 = 新 L3
    
    def test_layer_weights(self):
        """测试层权重配置"""
        weights = LayerWeights(
            inverted=2.0,
            entity=1.5,
            graph=1.0
        )
        config = RetrievalConfig(weights=weights)
        
        assert config.weights.inverted == 2.0
        assert config.weights.entity == 1.5
        assert config.weights.graph == 1.0


class TestTemporalContext:
    """测试 TemporalContext"""
    
    def test_has_time_constraint(self):
        """测试时间约束检测"""
        # 无约束
        ctx = TemporalContext()
        assert ctx.has_time_constraint() is False
        
        # 有起始时间
        ctx = TemporalContext(start=datetime.now())
        assert ctx.has_time_constraint() is True
        
        # 有结束时间
        ctx = TemporalContext(end=datetime.now())
        assert ctx.has_time_constraint() is True


# =========================================================================
# ElevenLayerRetriever 测试
# =========================================================================

class TestElevenLayerRetriever:
    """测试 ElevenLayerRetriever"""
    
    def test_basic_retrieve(self, basic_retriever):
        """测试基础检索（不含新层）"""
        results = basic_retriever.retrieve(
            query="coffee",
            keywords=['coffee', 'tea'],
            top_k=5
        )
        
        # 应该返回结果
        assert len(results) > 0
        
        # 结果应该是 RetrievalResultItem
        for r in results:
            assert isinstance(r, RetrievalResultItem)
            assert r.id is not None
            assert r.score >= 0
    
    def test_l1_bloom_filter(self, basic_retriever, mock_bloom_filter):
        """测试 L1 布隆过滤器"""
        # 使用 retrieve 触发 L1
        basic_retriever.retrieve(
            query="test",
            keywords=['apple', 'orange', 'banana'],  # apple 和 banana 在布隆过滤器中
            top_k=5
        )
        
        # 验证 L1 被调用
        stats = basic_retriever.get_stats_summary()
        l1_stats = [s for s in stats['layers'] if s['layer'] == 'bloom_filter']
        assert len(l1_stats) == 1
        assert l1_stats[0]['input'] == 3
        assert l1_stats[0]['output'] == 2  # apple, banana 通过
    
    def test_l2_temporal_filter(self, full_retriever, mock_temporal_index):
        """测试 L2 时态过滤"""
        temporal_ctx = TemporalContext(
            start=datetime.now() - timedelta(days=7),
            end=datetime.now()
        )
        
        results = full_retriever.retrieve(
            query="test",
            temporal_context=temporal_ctx,
            top_k=5
        )
        
        # 验证时态索引被调用
        mock_temporal_index.query_range.assert_called_once()
        
        # 检查统计
        stats = full_retriever.get_stats_summary()
        l2_stats = [s for s in stats['layers'] if s['layer'] == 'temporal_filter']
        assert len(l2_stats) == 1
    
    def test_l5_graph_traversal(self, full_retriever, mock_knowledge_graph):
        """测试 L5 图遍历"""
        results = full_retriever.retrieve(
            query="Alice",
            entities=['Alice'],
            top_k=10
        )
        
        # 验证图遍历被调用
        mock_knowledge_graph.get_node_by_name.assert_called()
        mock_knowledge_graph.bfs.assert_called()
        
        # 检查统计
        stats = full_retriever.get_stats_summary()
        l5_stats = [s for s in stats['layers'] if s['layer'] == 'graph_traversal']
        assert len(l5_stats) == 1
    
    def test_l7_vector_coarse(self, basic_retriever, mock_vector_index):
        """测试 L7 向量粗筛"""
        results = basic_retriever.retrieve(
            query="test query",
            top_k=5
        )
        
        # 验证向量索引被调用
        mock_vector_index.search.assert_called()
        
        # 检查统计
        stats = basic_retriever.get_stats_summary()
        l7_stats = [s for s in stats['layers'] if s['layer'] == 'vector_coarse']
        assert len(l7_stats) == 1
    
    def test_content_cache(self, basic_retriever):
        """测试内容缓存"""
        # 缓存内容
        basic_retriever.cache_content('test_doc', 'Test content')
        
        # 验证可以获取
        content = basic_retriever.get_content('test_doc')
        assert content == 'Test content'
    
    def test_stats_summary(self, basic_retriever):
        """测试统计摘要"""
        basic_retriever.retrieve(query="test", top_k=5)
        
        summary = basic_retriever.get_stats_summary()
        
        assert 'total_time_ms' in summary
        assert 'layers' in summary
        assert summary['total_time_ms'] >= 0
    
    def test_fallback_ngram_search(self, content_store):
        """测试兜底搜索"""
        # 创建一个只有 ngram_index 的检索器
        mock_ngram = Mock()
        mock_ngram.search = Mock(return_value=[])  # 常规搜索无结果
        mock_ngram.raw_search = Mock(return_value=['doc6'])  # 兜底搜索有结果
        
        retriever = ElevenLayerRetriever(
            ngram_index=mock_ngram,
            content_store=content_store,
            config=RetrievalConfig(
                l1_enabled=False,
                l3_enabled=False,
                l4_enabled=False,
                l5_enabled=False,
                l6_enabled=True,
                l7_enabled=False,
                l8_enabled=False,
                l9_enabled=False,
            )
        )
        
        results = retriever.retrieve(query="fallback test", top_k=5)
        
        # 应该使用兜底搜索
        mock_ngram.raw_search.assert_called()
        assert len(results) > 0


class TestEightLayerRetrieverCompat:
    """测试向后兼容适配器"""
    
    def test_compat_retrieve(self, full_retriever):
        """测试兼容适配器"""
        compat = EightLayerRetrieverCompat(full_retriever)
        
        results = compat.retrieve(
            query="test",
            keywords=['coffee'],
            top_k=5
        )
        
        # 应该返回结果
        assert isinstance(results, list)
    
    def test_compat_disables_new_layers(self, full_retriever, mock_temporal_index, mock_knowledge_graph):
        """测试兼容适配器禁用新层"""
        compat = EightLayerRetrieverCompat(full_retriever)
        
        # 重置 mock 调用计数
        mock_temporal_index.reset_mock()
        mock_knowledge_graph.reset_mock()
        
        compat.retrieve(query="test", top_k=5)
        
        # L2 和 L5 不应该被调用
        mock_temporal_index.query_range.assert_not_called()
        mock_knowledge_graph.bfs.assert_not_called()


# =========================================================================
# 集成测试
# =========================================================================

class TestIntegration:
    """集成测试"""
    
    def test_full_pipeline(self, full_retriever):
        """测试完整检索流程"""
        temporal_ctx = TemporalContext(
            start=datetime.now() - timedelta(days=30),
            end=datetime.now()
        )
        
        results = full_retriever.retrieve(
            query="Alice coffee meeting",
            entities=['Alice', 'Bob'],
            keywords=['coffee', 'meeting'],
            temporal_context=temporal_ctx,
            top_k=10
        )
        
        # 验证结果
        assert len(results) > 0
        
        # 验证分数排序
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
        
        # 验证统计
        stats = full_retriever.get_stats_summary()
        assert stats['total_time_ms'] > 0
        assert len(stats['layers']) > 0
    
    def test_config_presets(self, full_retriever):
        """测试配置预设"""
        # 快速模式
        fast_config = RetrievalConfig.fast()
        results_fast = full_retriever.retrieve(
            query="test",
            config=fast_config,
            top_k=5
        )
        
        # 精准模式（没有 CrossEncoder，所以 L10 不会执行）
        accurate_config = RetrievalConfig.accurate()
        results_accurate = full_retriever.retrieve(
            query="test",
            config=accurate_config,
            top_k=5
        )
        
        # 两种模式都应该返回结果
        assert len(results_fast) > 0
        assert len(results_accurate) > 0


# =========================================================================
# 主入口
# =========================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
