# -*- coding: utf-8 -*-
"""测试持久条件的增长控制"""

import os
import tempfile

# 使用临时目录
tmpdir = tempfile.mkdtemp()
os.environ['RECALL_DATA_ROOT'] = tmpdir

from recall import RecallEngine

e = RecallEngine(lite=True)  # 也可以用 lightweight=True

print('=== 测试持久条件增长控制 ===')

# 添加大量相似条件
topics = ["Web", "AI", "数据", "自动化"]
for i in range(20):
    topic = topics[i % 4]
    e.add(f'我是Python开发者，专注于{topic}开发', user_id='test')

print('添加20条记忆后的持久条件数量:')
contexts = e.get_persistent_contexts(user_id='test')
print(f'  活跃条件数: {len(contexts)}')
for ctx in contexts:
    print(f'    [{ctx["context_type"]}] {ctx["content"]} (置信度:{ctx["confidence"]})')

# 检查数量限制
stats = e.context_tracker.get_stats('test')
print(f'\n统计: {stats}')
print(f'  每类型上限: {stats["limits"]["max_per_type"]}')
print(f'  总数上限: {stats["limits"]["max_total"]}')

# 验证数量确实被限制
assert len(contexts) <= 30, f"条件数量 {len(contexts)} 超过限制 30"
for ctx_type in stats["by_type"]:
    assert stats["by_type"][ctx_type] <= 5, f"类型 {ctx_type} 数量超过限制 5"

print('\n=== 测试通过! ===')
