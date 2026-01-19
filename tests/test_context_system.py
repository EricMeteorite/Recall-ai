# -*- coding: utf-8 -*-
"""测试完整的六层上下文系统"""

from recall import RecallEngine

e = RecallEngine()

# ========== 测试持久条件 ==========
print('=== 测试持久条件系统 ===')

# 模拟用户说出自己的背景
e.add('我是一个刚毕业的大学生，专业是计算机', user_id='test')
e.add('我想创业，做一个AI相关的项目', user_id='test')
e.add('我在Windows上开发，但需要部署到Ubuntu服务器', user_id='test')

# 查看自动提取的持久条件
print('\n自动提取的持久条件:')
contexts = e.get_persistent_contexts(user_id='test')
for ctx in contexts:
    print(f"  [{ctx['context_type']}] {ctx['content']}")

# 手动添加一个持久条件
e.add_persistent_context(
    content='预算有限，优先考虑开源方案',
    context_type='constraint',
    user_id='test'
)

print('\n添加约束后的持久条件:')
contexts = e.get_persistent_contexts(user_id='test')
for ctx in contexts:
    print(f"  [{ctx['context_type']}] {ctx['content']}")

# ========== 测试完整上下文构建 ==========
print('\n=== 添加更多记忆 ===')
memories = [
    '小明是项目的联合创始人，负责后端开发',
    '小明有3年Python经验，熟悉FastAPI框架',
    '我们计划使用PostgreSQL作为主数据库',
    '项目第一阶段的目标是完成MVP',
    '我们正在考虑使用Docker进行部署',
]
for mem in memories:
    e.add(mem, user_id='test')
print(f'已添加 {len(memories)} 条记忆')

# 构建上下文
print('\n=== 构建完整上下文 ===')
context = e.build_context(
    query='帮我推荐一下技术栈',
    user_id='test',
    max_tokens=3000
)
print(context)

# 统计
print('\n=== 统计信息 ===')
stats = e.get_stats(user_id='test')
print(f"总记忆数: {stats['global']['total_memories']}")
print(f"整合实体数: {stats['global']['consolidated_entities']}")
print(f"活跃伏笔数: {stats['global']['active_foreshadowings']}")
