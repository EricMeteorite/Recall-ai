#!/usr/bin/env python3
"""Recall 4.1 实现完整性检查 - 终极版"""

import os
import sys
import tempfile
import inspect

def main():
    print('=' * 60)
    print(' Recall 4.1 实现完整性检查 - 终极版')
    print('=' * 60)
    print()
    
    all_ok = True
    test_dir = tempfile.mkdtemp()  # 创建临时目录供后续测试使用
    
    # T1: LLM 关系提取增强
    print('[T1] LLM 关系提取增强...')
    try:
        from recall.graph.llm_relation_extractor import (
            LLMRelationExtractor, 
            RelationExtractionMode,
            LLMRelationExtractorConfig
        )
        # 检查三种模式
        modes = [m.name for m in RelationExtractionMode]
        expected = ['RULES', 'ADAPTIVE', 'LLM']
        if set(expected).issubset(set(modes)):
            print(f'  [OK] 三模式支持: {modes}')
        else:
            print(f'  [WARN] 模式不完整: {modes}')
            all_ok = False
        
        # 检查配置类
        cfg = LLMRelationExtractorConfig()
        fields = ['mode', 'complexity_threshold', 'enable_temporal', 'enable_fact_description']
        for f in fields:
            if hasattr(cfg, f):
                print(f'  [OK] LLMRelationExtractorConfig.{f}')
            else:
                print(f'  [MISS] LLMRelationExtractorConfig.{f}')
                all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # T2: 关系时态信息提取
    print('[T2] 关系时态信息提取...')
    try:
        from recall.graph.knowledge_graph import Relation
        r = Relation(source_id='A', target_id='B', relation_type='TEST')
        for f in ['valid_at', 'invalid_at', 'fact']:
            if hasattr(r, f):
                print(f'  [OK] Relation.{f}')
            else:
                print(f'  [MISS] Relation.{f}')
                all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # T3: 自定义实体类型 Schema
    print('[T3] 自定义实体类型 Schema...')
    try:
        from recall.models.entity_schema import (
            EntitySchemaRegistry,
            EntityTypeDefinition,
            AttributeDefinition
        )
        # 使用临时目录创建 registry
        registry = EntitySchemaRegistry(data_path=test_dir)
        builtin = [t.name for t in registry.get_all()]  # 使用 get_all() 获取所有类型
        expected_types = ['PERSON', 'ORGANIZATION', 'LOCATION', 'EVENT', 'ITEM', 'CONCEPT', 'TIME']
        for t in expected_types:
            if t in builtin:
                print(f'  [OK] 内置类型 {t}')
            else:
                print(f'  [MISS] 内置类型 {t}')
                all_ok = False
        
        # 检查注册自定义类型
        custom = EntityTypeDefinition(
            name='TEST_TYPE',
            display_name='测试类型',
            attributes=[AttributeDefinition(name='test_field')]
        )
        registry.register(custom)
        new_types = [t.name for t in registry.get_all()]
        if 'TEST_TYPE' in new_types:
            print('  [OK] 自定义类型注册')
        else:
            print('  [MISS] 自定义类型注册')
            all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # T4: SmartExtractor 集成
    print('[T4] SmartExtractor 集成...')
    try:
        from recall.processor.smart_extractor import SmartExtractor
        # 检查 entity_schema_registry 参数支持
        sig = inspect.signature(SmartExtractor.__init__)
        if 'entity_schema_registry' in sig.parameters:
            print('  [OK] SmartExtractor 支持 entity_schema_registry')
        else:
            print('  [MISS] SmartExtractor.entity_schema_registry 参数')
            all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # T5: Episode 概念引入
    print('[T5] Episode 概念引入...')
    try:
        from recall.storage.episode_store import EpisodeStore
        from recall.models.temporal import EpisodicNode
        
        # 检查 EpisodeStore 方法（使用实际方法名）
        methods = ['save', 'get', 'get_by_memory_id', 'update_links', 'get_by_user', 'get_recent']
        for m in methods:
            if hasattr(EpisodeStore, m):
                print(f'  [OK] EpisodeStore.{m}()')
            else:
                print(f'  [MISS] EpisodeStore.{m}()')
                all_ok = False
        
        # 检查 EpisodicNode 字段（继承自 UnifiedNode）
        node = EpisodicNode(
            uuid='test',
            content='test content',
            source_description='test source'
        )
        for f in ['uuid', 'content', 'source_type', 'source_description', 'memory_ids', 'relation_ids', 'entity_edges']:
            if hasattr(node, f):
                print(f'  [OK] EpisodicNode.{f}')
            else:
                print(f'  [MISS] EpisodicNode.{f}')
                all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # T6: 实体摘要生成
    print('[T6] 实体摘要生成...')
    try:
        from recall.processor.entity_summarizer import EntitySummarizer, EntitySummary
        
        # 检查 EntitySummary 数据类
        summary = EntitySummary(entity_name='test', summary='test summary')
        for f in ['entity_name', 'summary', 'key_facts', 'relation_count', 'mention_count']:
            if hasattr(summary, f):
                print(f'  [OK] EntitySummary.{f}')
            else:
                print(f'  [MISS] EntitySummary.{f}')
                all_ok = False
        
        # 检查生成方法
        if hasattr(EntitySummarizer, 'generate'):
            print('  [OK] EntitySummarizer.generate()')
        else:
            print('  [MISS] EntitySummarizer.generate()')
            all_ok = False
        
        # 检查 generate_summary 别名（如果有）
        if hasattr(EntitySummarizer, 'generate_summary'):
            print('  [OK] EntitySummarizer.generate_summary()')
        else:
            print('  [INFO] EntitySummarizer 使用 generate() 方法')
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # T7: 动态实体属性
    print('[T7] 动态实体属性...')
    try:
        from recall.index.entity_index import IndexedEntity, EntityIndex
        
        ie = IndexedEntity(
            id='1', 
            name='Test', 
            aliases=[], 
            entity_type='PERSON', 
            turn_references=[]
        )
        for f in ['summary', 'attributes', 'last_summary_update']:
            if hasattr(ie, f):
                print(f'  [OK] IndexedEntity.{f}')
            else:
                print(f'  [MISS] IndexedEntity.{f}')
                all_ok = False
        
        # 检查 EntityIndex 方法
        if hasattr(EntityIndex, 'update_entity_fields'):
            print('  [OK] EntityIndex.update_entity_fields()')
        else:
            print('  [MISS] EntityIndex.update_entity_fields()')
            all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # 检查 Engine 集成
    print('[Engine] 核心引擎集成...')
    try:
        os.environ['EPISODE_TRACKING_ENABLED'] = 'true'
        os.environ['ENTITY_SUMMARY_ENABLED'] = 'true'
        
        test_dir = tempfile.mkdtemp()
        from recall.engine import RecallEngine
        engine = RecallEngine(data_root=test_dir, lite=True)
        
        # 检查属性初始化
        attrs = [
            ('entity_schema_registry', '实体Schema注册表'),
            ('episode_store', 'Episode存储'),
            ('entity_summarizer', '实体摘要生成器'),
            ('_episode_tracking_enabled', 'Episode追踪开关'),
            ('_entity_summary_enabled', '实体摘要开关'),
        ]
        for attr, name in attrs:
            val = getattr(engine, attr, None)
            if isinstance(val, bool):
                status = 'OK' if val else 'WARN(False)'
            else:
                status = 'OK' if val is not None else 'MISS'
            print(f'  [{status}] {name}')
            if status == 'MISS':
                all_ok = False
        
        # 检查 add() 方法集成
        add_source = inspect.getsource(engine.add)
        integrations = [
            ('current_episode', 'Episode创建'),
            ('episode_store.save', 'Episode保存'),
            ('episode_store.update_links', 'Episode关联'),
            ('_maybe_update_entity_summary', '实体摘要更新'),
        ]
        for keyword, name in integrations:
            found = keyword in add_source
            status = 'OK' if found else 'MISS'
            print(f'  [{status}] add()中的{name}')
            if not found:
                all_ok = False
        
        # 检查辅助方法
        if hasattr(engine, '_maybe_update_entity_summary'):
            print('  [OK] _maybe_update_entity_summary()方法')
        else:
            print('  [MISS] _maybe_update_entity_summary()方法')
            all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # 检查 API 端点
    print('[Server] API端点检查...')
    try:
        server_path = os.path.join(os.path.dirname(__file__), '..', 'recall', 'server.py')
        with open(server_path, 'r', encoding='utf-8') as f:
            server_source = f.read()
        
        endpoints = [
            '/v1/episodes',
            '/v1/episodes/{episode_uuid}',
            '/v1/episodes/by-memory/{memory_id}',
            '/v1/entities/{name}/summary',
            '/v1/entities/{name}/generate-summary',
            '/v1/config/v41',
        ]
        for ep in endpoints:
            found = ep in server_source
            status = 'OK' if found else 'MISS'
            print(f'  [{status}] {ep}')
            if not found:
                all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # 检查配置项
    print('[Config] 配置项检查...')
    try:
        config_items = [
            'LLM_RELATION_MODE',
            'LLM_RELATION_COMPLEXITY_THRESHOLD',
            'LLM_RELATION_ENABLE_TEMPORAL',
            'LLM_RELATION_ENABLE_FACT_DESCRIPTION',
            'ENTITY_SUMMARY_ENABLED',
            'ENTITY_SUMMARY_MIN_FACTS',
            'EPISODE_TRACKING_ENABLED',
        ]
        
        # 检查 server.py 中的环境变量读取
        for item in config_items:
            found = item in server_source
            status = 'OK' if found else 'MISS'
            print(f'  [{status}] {item}')
            if not found:
                all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    # 检查 __init__.py 导出
    print('[Export] 模块导出检查...')
    try:
        from recall.graph import LLMRelationExtractor
        from recall.models import EntitySchemaRegistry
        from recall.storage import EpisodeStore
        from recall.processor import EntitySummarizer
        print('  [OK] 所有模块可从顶层包导入')
    except ImportError as e:
        print(f'  [FAIL] 导入失败: {e}')
        all_ok = False
    
    # 检查 chat_with_recall.py 命令
    print('[Tools] chat_with_recall.py 命令检查...')
    try:
        chat_path = os.path.join(os.path.dirname(__file__), 'chat_with_recall.py')
        with open(chat_path, 'r', encoding='utf-8') as f:
            chat_source = f.read()
        
        commands = ['/episodes', '/summary', '/contradictions', '/conditions', '/v41']
        for cmd in commands:
            found = cmd in chat_source
            status = 'OK' if found else 'MISS'
            print(f'  [{status}] {cmd} 命令')
            if not found:
                all_ok = False
    except Exception as e:
        print(f'  [FAIL] {e}')
        all_ok = False
    
    print()
    print('=' * 60)
    if all_ok:
        print(' ✅ Recall 4.1 所有实现完整性检查通过！')
    else:
        print(' ❌ 发现问题，请检查上方 [MISS] 或 [FAIL] 项')
    print('=' * 60)
    
    return 0 if all_ok else 1

if __name__ == '__main__':
    sys.exit(main())
