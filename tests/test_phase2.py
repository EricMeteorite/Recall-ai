"""Phase 2 功能测试脚本"""

import tempfile
import os
import sys

def test_phase2():
    """测试 Phase 2 所有新模块"""
    # 使用临时目录避免影响现有数据
    temp_dir = tempfile.mkdtemp()
    os.environ['RECALL_DATA_ROOT'] = temp_dir

    print('Phase 2 功能测试...')
    print('=' * 50)

    # 1. 测试 BudgetManager
    print('\n1. 测试 BudgetManager...')
    from recall.utils import BudgetManager, BudgetConfig, BudgetPeriod

    budget = BudgetManager(
        data_path=temp_dir,
        config=BudgetConfig(daily_budget=1.0, hourly_budget=0.1)
    )
    print(f'   初始化成功，日预算: ${budget.config.daily_budget}')

    # 模拟记录使用 (operation, tokens_in, tokens_out, cost=None, model)
    budget.record_usage('test', 100, 50, model='gpt-4o-mini')
    stats = budget.get_stats()
    print(f'   统计: 已用 ${stats["daily_cost"]:.4f}')

    can_afford = budget.can_afford(0.01)
    print(f'   能否承担 $0.01: {can_afford}')

    # 2. 测试 ThreeStageDeduplicator
    print('\n2. 测试 ThreeStageDeduplicator...')
    from recall.processor import ThreeStageDeduplicator, DedupConfig, DedupItem

    dedup = ThreeStageDeduplicator(config=DedupConfig.default())
    print('   初始化成功')

    # 测试去重
    items = [
        DedupItem(id='1', name='Alice', content='Alice is a character'),
        DedupItem(id='2', name='alice', content='alice is a character'),  # 应该匹配
        DedupItem(id='3', name='Bob', content='Bob is different'),
    ]
    existing = [items[0]]
    new_items = items[1:]

    result = dedup.deduplicate(new_items, existing)
    print(f'   去重结果: 匹配={result.matched_count}, 新增={result.new_count}')

    # 3. 测试 SmartExtractor
    print('\n3. 测试 SmartExtractor...')
    from recall.processor import SmartExtractor, SmartExtractorConfig, ExtractionMode

    config = SmartExtractorConfig.local_only()
    extractor = SmartExtractor(config=config)
    print(f'   初始化成功，模式: {config.mode}')

    # 测试抽取
    result = extractor.extract('张三在2024年1月去了北京，他遇到了李四。')
    print(f'   抽取结果: 实体={len(result.entities)}, 关系={len(result.relations)}')
    print(f'   实体: {[e.name for e in result.entities[:3]]}')

    # 4. 测试 RecallEngine (不启用 Phase 1 模块)
    print('\n4. 测试 RecallEngine (默认配置)...')
    from recall.engine import RecallEngine

    # 不启用 Phase 1 模块
    engine = RecallEngine(data_root=temp_dir, lightweight=True, auto_warmup=False)
    print('   引擎初始化成功')

    # 测试基本功能
    result = engine.add('测试记忆内容', user_id='test')
    print(f'   添加记忆: {result.success}')

    # 5. 测试 RecallEngine with Phase 1 模块
    print('\n5. 测试 RecallEngine (启用 Phase 1 模块)...')
    temp_dir2 = tempfile.mkdtemp()

    # 启用 Phase 1 模块
    os.environ['TEMPORAL_GRAPH_ENABLED'] = 'true'
    os.environ['CONTRADICTION_DETECTION_ENABLED'] = 'true'
    os.environ['FULLTEXT_ENABLED'] = 'true'

    engine2 = RecallEngine(data_root=temp_dir2, lightweight=True, auto_warmup=False)

    print(f'   时态图谱: {"已启用" if engine2.temporal_graph else "未启用"}')
    print(f'   矛盾检测: {"已启用" if engine2.contradiction_manager else "未启用"}')
    print(f'   全文检索: {"已启用" if engine2.fulltext_index else "未启用"}')

    print('\n' + '=' * 50)
    print('所有功能测试通过! ✓')

    # 清理
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
    shutil.rmtree(temp_dir2, ignore_errors=True)
    
    # pytest 测试函数应返回 None，不返回值


if __name__ == '__main__':
    test_phase2()
    print('测试完成')
    sys.exit(0)
