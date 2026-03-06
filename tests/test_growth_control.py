# -*- coding: utf-8 -*-
"""测试持久条件的增长控制"""

import os
import tempfile
from recall import RecallEngine


def test_growth_control():
    """测试持久条件增长控制 — 数量应被限制在合理范围内"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        prev_mode = os.environ.get('RECALL_EMBEDDING_MODE')
        os.environ['RECALL_EMBEDDING_MODE'] = 'none'
        try:
            e = RecallEngine(data_root=tmpdir, lightweight=True)

            # 添加大量相似条件
            topics = ["Web", "AI", "数据", "自动化"]
            for i in range(20):
                topic = topics[i % 4]
                e.add(f'我是Python开发者，专注于{topic}开发', user_id='test')

            # 验证持久条件数量
            contexts = e.get_persistent_contexts(user_id='test')
            assert len(contexts) <= 30, f"条件数量 {len(contexts)} 超过限制 30"

            # 验证每类型数量限制
            stats = e.context_tracker.get_stats('test')
            for ctx_type in stats["by_type"]:
                assert stats["by_type"][ctx_type] <= 5, (
                    f"类型 {ctx_type} 数量超过限制 5"
                )

            e.close()
        finally:
            if prev_mode is None:
                os.environ.pop('RECALL_EMBEDDING_MODE', None)
            else:
                os.environ['RECALL_EMBEDDING_MODE'] = prev_mode


if __name__ == '__main__':
    test_growth_control()
    print('\n=== 测试通过! ===')
