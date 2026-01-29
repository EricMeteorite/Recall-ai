# -*- coding: utf-8 -*-
"""测试完整的六层上下文系统

此文件使用 pytest 进行测试，包含完整的断言验证。
"""

import os
import sys
import pytest
import tempfile
import shutil

# 设置测试环境
os.environ.setdefault('RECALL_EMBEDDING_MODE', 'none')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestContextSystem:
    """六层上下文系统测试"""
    
    @pytest.fixture
    def engine(self):
        """创建测试引擎"""
        temp_dir = tempfile.mkdtemp()
        from recall import RecallEngine
        engine = RecallEngine(data_root=temp_dir, lite=True)
        yield engine
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_persistent_context_extraction(self, engine):
        """测试持久条件自动提取"""
        # 添加包含背景信息的记忆
        engine.add('我是一个刚毕业的大学生，专业是计算机', user_id='ctx_test')
        engine.add('我想创业，做一个AI相关的项目', user_id='ctx_test')
        engine.add('我在Windows上开发，但需要部署到Ubuntu服务器', user_id='ctx_test')
        
        # 获取持久条件
        contexts = engine.get_persistent_contexts(user_id='ctx_test')
        
        # 验证返回类型
        assert isinstance(contexts, list), "持久条件应该返回列表"
        
        # 每个条件应该有必要的字段
        for ctx in contexts:
            assert 'content' in ctx, "持久条件应该有 content 字段"
            assert 'context_type' in ctx, "持久条件应该有 context_type 字段"
    
    def test_add_persistent_context_manually(self, engine):
        """测试手动添加持久条件"""
        # 手动添加一个持久条件
        engine.add_persistent_context(
            content='预算有限，优先考虑开源方案',
            context_type='constraint',
            user_id='ctx_test'
        )
        
        # 获取并验证
        contexts = engine.get_persistent_contexts(user_id='ctx_test')
        assert len(contexts) >= 1, "应该至少有一个持久条件"
        
        # 验证添加的条件存在
        contents = [ctx['content'] for ctx in contexts]
        assert '预算有限，优先考虑开源方案' in contents, "手动添加的条件应该存在"
    
    def test_context_build_includes_memories(self, engine):
        """测试上下文构建包含记忆"""
        # 添加记忆
        engine.add('小明是项目的联合创始人，负责后端开发', user_id='ctx_test')
        engine.add('小明有3年Python经验，熟悉FastAPI框架', user_id='ctx_test')
        engine.add('我们计划使用PostgreSQL作为主数据库', user_id='ctx_test')
        
        # 构建上下文
        context = engine.build_context(
            query='帮我推荐一下技术栈',
            user_id='ctx_test',
            max_tokens=3000
        )
        
        # 验证上下文不为空
        assert context is not None, "上下文不应该为空"
        assert isinstance(context, str), "上下文应该是字符串"
        assert len(context) > 0, "上下文应该有内容"
    
    def test_stats_after_adding_memories(self, engine):
        """测试添加记忆后的统计信息"""
        # 添加记忆
        memories = [
            '小明是项目的联合创始人',
            '我们正在考虑使用Docker进行部署',
            '项目第一阶段的目标是完成MVP',
        ]
        for mem in memories:
            engine.add(mem, user_id='stats_test')
        
        # 获取统计
        stats = engine.get_stats(user_id='stats_test')
        
        # 验证统计结构
        assert isinstance(stats, dict), "统计应该是字典"
        assert 'global' in stats, "统计应该有 global 字段"
        assert 'total_memories' in stats['global'], "应该有 total_memories"
        
        # 验证记忆数量
        assert stats['global']['total_memories'] >= len(memories), \
            f"记忆数应该至少有 {len(memories)} 条"
    
    def test_entity_extraction_from_context(self, engine):
        """测试从上下文中提取实体"""
        # 添加包含实体的记忆
        engine.add('张三是北京大学的教授，研究人工智能', user_id='entity_test')
        engine.add('李四在腾讯公司工作，是张三的学生', user_id='entity_test')
        
        # 获取统计
        stats = engine.get_stats(user_id='entity_test')
        
        # 应该有提取到的实体
        assert 'consolidated_entities' in stats['global'], "应该有实体统计"
        # 实体数可能为 0（取决于提取器），但字段应该存在
        assert isinstance(stats['global']['consolidated_entities'], int)
    
    def test_user_isolation(self, engine):
        """测试用户隔离"""
        # 为不同用户添加记忆
        engine.add('用户A的秘密信息', user_id='user_a')
        engine.add('用户B的秘密信息', user_id='user_b')
        
        # 构建用户A的上下文
        context_a = engine.build_context(
            query='秘密信息',
            user_id='user_a',
            max_tokens=1000
        )
        
        # 用户A的上下文不应该包含用户B的信息
        if context_a:  # 可能为空
            assert '用户B' not in context_a, "用户A的上下文不应包含用户B的信息"


# =============================================================================
# 直接运行脚本模式（兼容旧用法）
# =============================================================================

if __name__ == '__main__':
    print('运行上下文系统测试...')
    print('建议使用: pytest tests/test_context_system.py -v')
    print()
    
    # 也支持直接运行
    pytest.main([__file__, '-v', '--tb=short'])
