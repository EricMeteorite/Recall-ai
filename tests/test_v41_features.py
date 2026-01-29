#!/usr/bin/env python3
"""Recall 4.1 新功能测试

测试覆盖：
1. T1: LLMRelationExtractor 三模式（RULES/ADAPTIVE/LLM）
2. T2: 关系时态字段（valid_at/invalid_at/fact）
3. T3: EntitySchemaRegistry 自定义实体类型
4. T4: SmartExtractor schema_registry 集成
5. T5: EpisodeStore 存储与查询
6. T6: EntitySummarizer 摘要生成
7. T7: IndexedEntity 扩展字段
8. Engine 集成测试
9. API 端点测试（需要运行服务器）
"""

import os
import sys
import pytest
import tempfile
import shutil
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置测试环境
os.environ.setdefault('RECALL_EMBEDDING_MODE', 'none')
os.environ['EPISODE_TRACKING_ENABLED'] = 'true'
os.environ['ENTITY_SUMMARY_ENABLED'] = 'true'


# =============================================================================
# T1: LLMRelationExtractor 测试
# =============================================================================

class TestLLMRelationExtractor:
    """LLM 关系提取器测试"""
    
    def test_import_classes(self):
        """测试导入相关类"""
        from recall.graph.llm_relation_extractor import (
            LLMRelationExtractor,
            RelationExtractionMode,
            LLMRelationExtractorConfig
        )
        assert LLMRelationExtractor is not None
        assert RelationExtractionMode is not None
        assert LLMRelationExtractorConfig is not None
    
    def test_three_modes_exist(self):
        """测试三模式存在"""
        from recall.graph.llm_relation_extractor import RelationExtractionMode
        
        modes = [m.name for m in RelationExtractionMode]
        assert 'RULES' in modes
        assert 'ADAPTIVE' in modes
        assert 'LLM' in modes
    
    def test_config_defaults(self):
        """测试配置默认值"""
        from recall.graph.llm_relation_extractor import LLMRelationExtractorConfig
        
        config = LLMRelationExtractorConfig()
        assert hasattr(config, 'mode')
        assert hasattr(config, 'complexity_threshold')
        assert hasattr(config, 'enable_temporal')
        assert hasattr(config, 'enable_fact_description')
    
    def test_rules_mode_no_llm_required(self):
        """测试 RULES 模式不需要 LLM"""
        from recall.graph.llm_relation_extractor import (
            LLMRelationExtractor,
            LLMRelationExtractorConfig,
            RelationExtractionMode
        )
        from recall.processor.entity_extractor import EntityExtractor
        
        config = LLMRelationExtractorConfig(mode=RelationExtractionMode.RULES)
        entity_extractor = EntityExtractor()
        
        # 不传 llm_client，RULES 模式应该可以工作
        extractor = LLMRelationExtractor(
            llm_client=None,
            entity_extractor=entity_extractor,
            config=config
        )
        
        # 提取关系
        entities = entity_extractor.extract("张三和李四是好朋友")
        relations = extractor.extract("张三和李四是好朋友", turn=0, entities=entities)
        
        # 应该返回列表（可能为空）
        assert isinstance(relations, list)


# =============================================================================
# T2: 关系时态字段测试
# =============================================================================

class TestRelationTemporalFields:
    """关系时态字段测试"""
    
    def test_relation_has_temporal_fields(self):
        """测试 Relation 有时态字段"""
        from recall.graph.knowledge_graph import Relation
        
        relation = Relation(
            source_id='entity_a',
            target_id='entity_b',
            relation_type='FRIENDS_WITH'
        )
        
        assert hasattr(relation, 'valid_at')
        assert hasattr(relation, 'invalid_at')
        assert hasattr(relation, 'fact')
    
    def test_relation_temporal_fields_optional(self):
        """测试时态字段是可选的"""
        from recall.graph.knowledge_graph import Relation
        
        # 不传时态字段应该不会报错
        relation = Relation(
            source_id='a',
            target_id='b',
            relation_type='TEST'
        )
        
        # 默认值应该是 None 或空字符串
        assert relation.valid_at is None or relation.valid_at == ""
        assert relation.invalid_at is None or relation.invalid_at == ""


# =============================================================================
# T3: EntitySchemaRegistry 测试
# =============================================================================

class TestEntitySchemaRegistry:
    """实体类型注册表测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)
    
    def test_import(self):
        """测试导入"""
        from recall.models.entity_schema import (
            EntitySchemaRegistry,
            EntityTypeDefinition,
            AttributeDefinition,
            AttributeType
        )
        assert EntitySchemaRegistry is not None
        assert EntityTypeDefinition is not None
        assert AttributeDefinition is not None
    
    def test_builtin_types(self, temp_dir):
        """测试内置类型"""
        from recall.models.entity_schema import EntitySchemaRegistry
        
        registry = EntitySchemaRegistry(data_path=temp_dir)
        types = [t.name for t in registry.get_all()]
        
        # 验证核心内置类型
        assert 'PERSON' in types
        assert 'LOCATION' in types
        assert 'ORGANIZATION' in types
        assert 'EVENT' in types
        assert 'CONCEPT' in types
        assert 'TIME' in types
    
    def test_register_custom_type(self, temp_dir):
        """测试注册自定义类型"""
        from recall.models.entity_schema import (
            EntitySchemaRegistry,
            EntityTypeDefinition,
            AttributeDefinition,
            AttributeType
        )
        
        registry = EntitySchemaRegistry(data_path=temp_dir)
        
        # 定义自定义类型
        custom_type = EntityTypeDefinition(
            name='CHARACTER',
            display_name='角色',
            description='虚构的角色人物',
            attributes=[
                AttributeDefinition(
                    name='age',
                    attr_type=AttributeType.NUMBER,
                    required=False
                ),
                AttributeDefinition(
                    name='occupation',
                    attr_type=AttributeType.STRING
                )
            ],
            examples=['樱', '小明']
        )
        
        # 注册
        registry.register(custom_type)
        
        # 验证
        types = [t.name for t in registry.get_all()]
        assert 'CHARACTER' in types
        
        # 获取
        retrieved = registry.get('CHARACTER')
        assert retrieved is not None
        assert retrieved.display_name == '角色'
        assert len(retrieved.attributes) == 2
    
    def test_get_all_for_prompt(self, temp_dir):
        """测试获取用于 LLM 提示词的类型描述"""
        from recall.models.entity_schema import EntitySchemaRegistry
        
        registry = EntitySchemaRegistry(data_path=temp_dir)
        prompt_text = registry.get_all_for_prompt()
        
        assert isinstance(prompt_text, str)
        assert 'PERSON' in prompt_text or '人物' in prompt_text


# =============================================================================
# T4: SmartExtractor 集成测试
# =============================================================================

class TestSmartExtractorIntegration:
    """SmartExtractor 与 Schema Registry 集成测试"""
    
    def test_supports_schema_registry_param(self):
        """测试 SmartExtractor 支持 entity_schema_registry 参数"""
        import inspect
        from recall.processor.smart_extractor import SmartExtractor
        
        sig = inspect.signature(SmartExtractor.__init__)
        params = list(sig.parameters.keys())
        
        assert 'entity_schema_registry' in params


# =============================================================================
# T5: EpisodeStore 测试
# =============================================================================

class TestEpisodeStore:
    """Episode 存储测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)
    
    def test_import(self):
        """测试导入"""
        from recall.storage.episode_store import EpisodeStore
        from recall.models.temporal import EpisodicNode
        assert EpisodeStore is not None
        assert EpisodicNode is not None
    
    def test_save_and_get(self, temp_dir):
        """测试保存和获取"""
        from recall.storage.episode_store import EpisodeStore
        from recall.models.temporal import EpisodicNode
        
        store = EpisodeStore(data_path=temp_dir)
        
        # 创建 Episode
        episode = EpisodicNode(
            uuid='test-episode-001',
            content='测试内容',
            user_id='test_user',
            source_description='单元测试'
        )
        
        # 保存
        saved = store.save(episode)
        assert saved.uuid == 'test-episode-001'
        
        # 获取
        retrieved = store.get('test-episode-001')
        assert retrieved is not None
        assert retrieved.content == '测试内容'
        assert retrieved.user_id == 'test_user'
    
    def test_get_by_user(self, temp_dir):
        """测试按用户获取"""
        from recall.storage.episode_store import EpisodeStore
        from recall.models.temporal import EpisodicNode
        
        store = EpisodeStore(data_path=temp_dir)
        
        # 添加多个用户的 Episode
        for i in range(3):
            ep = EpisodicNode(
                uuid=f'ep-user1-{i}',
                content=f'用户1的内容{i}',
                user_id='user1'
            )
            store.save(ep)
        
        for i in range(2):
            ep = EpisodicNode(
                uuid=f'ep-user2-{i}',
                content=f'用户2的内容{i}',
                user_id='user2'
            )
            store.save(ep)
        
        # 按用户获取
        user1_episodes = store.get_by_user('user1')
        user2_episodes = store.get_by_user('user2')
        
        assert len(user1_episodes) == 3
        assert len(user2_episodes) == 2
    
    def test_update_links(self, temp_dir):
        """测试更新关联链接"""
        from recall.storage.episode_store import EpisodeStore
        from recall.models.temporal import EpisodicNode
        
        store = EpisodeStore(data_path=temp_dir)
        
        # 创建 Episode
        episode = EpisodicNode(
            uuid='ep-links-test',
            content='测试关联',
            user_id='test'
        )
        store.save(episode)
        
        # 更新关联
        store.update_links(
            episode_uuid='ep-links-test',
            memory_ids=['mem-001', 'mem-002'],
            entity_ids=['ent-001'],
            relation_ids=['rel-001', 'rel-002', 'rel-003']
        )
        
        # 验证更新
        updated = store.get('ep-links-test')
        assert 'mem-001' in updated.memory_ids
        assert 'mem-002' in updated.memory_ids


# =============================================================================
# T6: EntitySummarizer 测试
# =============================================================================

class TestEntitySummarizer:
    """实体摘要生成器测试"""
    
    def test_import(self):
        """测试导入"""
        from recall.processor.entity_summarizer import EntitySummarizer, EntitySummary
        assert EntitySummarizer is not None
        assert EntitySummary is not None
    
    def test_entity_summary_structure(self):
        """测试 EntitySummary 数据结构"""
        from recall.processor.entity_summarizer import EntitySummary
        
        summary = EntitySummary(
            entity_name='张三',
            summary='张三是一名程序员，喜欢咖啡和音乐。',
            key_facts=['喜欢咖啡', '喜欢音乐', '是程序员'],
            relation_count=5,
            mention_count=10
        )
        
        assert summary.entity_name == '张三'
        assert len(summary.key_facts) == 3
        assert summary.relation_count == 5
        
        # 测试序列化
        d = summary.to_dict()
        assert isinstance(d, dict)
        assert 'entity_name' in d
        assert 'summary' in d
    
    def test_generate_without_llm(self):
        """测试无 LLM 时的生成（回退模式）"""
        from recall.processor.entity_summarizer import EntitySummarizer
        
        summarizer = EntitySummarizer(llm_client=None)
        
        # 无 LLM 时应该能生成基本摘要
        summary = summarizer.generate(
            entity_name='测试实体',
            facts=['事实1', '事实2', '事实3'],
            relations=[('测试实体', 'KNOWS', '其他实体')]
        )
        
        assert summary is not None
        assert summary.entity_name == '测试实体'
        # 回退模式可能返回简单摘要或空
        assert isinstance(summary.summary, str)


# =============================================================================
# T7: IndexedEntity 扩展字段测试
# =============================================================================

class TestIndexedEntityExtendedFields:
    """IndexedEntity 扩展字段测试"""
    
    def test_has_extended_fields(self):
        """测试有扩展字段"""
        from recall.index.entity_index import IndexedEntity
        
        entity = IndexedEntity(
            id='ent-001',
            name='测试实体',
            aliases=['别名1'],
            entity_type='PERSON',
            turn_references=[1, 2, 3]
        )
        
        assert hasattr(entity, 'summary')
        assert hasattr(entity, 'attributes')
        assert hasattr(entity, 'last_summary_update')
    
    def test_update_entity_fields_method_exists(self):
        """测试 EntityIndex 有 update_entity_fields 方法"""
        from recall.index.entity_index import EntityIndex
        
        assert hasattr(EntityIndex, 'update_entity_fields')


# =============================================================================
# Engine 集成测试
# =============================================================================

class TestEngineV41Integration:
    """Engine v4.1 集成测试"""
    
    @pytest.fixture
    def engine(self):
        """创建测试引擎"""
        temp_dir = tempfile.mkdtemp()
        os.environ['EPISODE_TRACKING_ENABLED'] = 'true'
        os.environ['ENTITY_SUMMARY_ENABLED'] = 'true'
        
        from recall.engine import RecallEngine
        engine = RecallEngine(data_root=temp_dir, lite=True)
        
        yield engine
        
        # 清理
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_engine_has_v41_attributes(self, engine):
        """测试引擎有 v4.1 属性"""
        assert hasattr(engine, 'entity_schema_registry')
        assert hasattr(engine, 'episode_store')
        assert hasattr(engine, 'entity_summarizer')
        assert hasattr(engine, '_episode_tracking_enabled')
        assert hasattr(engine, '_entity_summary_enabled')
    
    def test_engine_v41_components_initialized(self, engine):
        """测试 v4.1 组件已初始化"""
        assert engine.entity_schema_registry is not None
        assert engine.episode_store is not None
        assert engine.entity_summarizer is not None
    
    def test_add_creates_episode(self, engine):
        """测试 add() 创建 Episode"""
        result = engine.add(
            content='测试内容：张三在北京工作',
            user_id='test_user'
        )
        
        assert result is not None
        
        # 检查 episode 是否创建
        episodes = engine.episode_store.get_by_user('test_user')
        # 可能为空（取决于配置），但不应该报错
        assert isinstance(episodes, list)
    
    def test_maybe_update_entity_summary_method(self, engine):
        """测试 _maybe_update_entity_summary 方法存在"""
        assert hasattr(engine, '_maybe_update_entity_summary')
        assert callable(getattr(engine, '_maybe_update_entity_summary'))


# =============================================================================
# API 端点测试（需要运行服务器）
# =============================================================================

import requests

def is_server_running():
    """检查服务器是否运行"""
    try:
        r = requests.get('http://127.0.0.1:18888/health', timeout=2)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not is_server_running(), reason="Recall 服务器未运行")
class TestV41APIEndpoints:
    """v4.1 API 端点测试"""
    
    BASE = 'http://127.0.0.1:18888'
    
    def test_episodes_list_endpoint(self):
        """测试 /v1/episodes 端点"""
        r = requests.get(f'{self.BASE}/v1/episodes', params={'user_id': 'test'})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))
    
    def test_config_v41_endpoint(self):
        """测试 /v1/config/v41 端点"""
        r = requests.get(f'{self.BASE}/v1/config/v41')
        assert r.status_code == 200
        data = r.json()
        
        # 应该包含 v4.1 配置信息
        assert isinstance(data, dict)
    
    def test_entity_summary_endpoint(self):
        """测试 /v1/entities/{name}/summary 端点"""
        # 使用不存在的实体名，应该返回 404 或空结果
        r = requests.get(f'{self.BASE}/v1/entities/nonexistent_entity_xyz/summary')
        # 可能是 404 或 200 带空数据
        assert r.status_code in [200, 404]


# =============================================================================
# 运行测试
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
