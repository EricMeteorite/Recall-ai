#!/usr/bin/env python3
"""测试 chat_with_recall 的 /clear 命令"""

import urllib.request
import json
import time

BASE = 'http://localhost:18888'

def api_get(endpoint):
    req = urllib.request.Request(f'{BASE}{endpoint}')
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def api_post(endpoint, data):
    req = urllib.request.Request(f'{BASE}{endpoint}', 
                                data=json.dumps(data).encode(),
                                method='POST')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

def api_delete(endpoint):
    req = urllib.request.Request(f'{BASE}{endpoint}', method='DELETE')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

print('=' * 60)
print('测试: 模拟 chat_with_recall /clear 命令')
print('=' * 60)

test_user = 'chat_clear_test'

# 清理旧数据
api_delete(f'/v1/memories?user_id={test_user}&confirm=true')

# 模拟聊天添加数据
print('\n--- 模拟聊天对话 ---')
messages = [
    ('user', '你好，我叫小明，今年25岁'),
    ('assistant', '你好小明！很高兴认识你，25岁正是人生的黄金时期'),
    ('user', '我住在杭州，在一家科技公司工作'),
    ('assistant', '杭州是个很不错的城市，科技公司工作应该很有趣'),
    ('user', '我有个女朋友叫小红，她是老师'),
]

for role, content in messages:
    r = api_post('/v1/memories', {
        'content': content,
        'user_id': test_user,
        'metadata': {'role': role}
    })
    print(f'  [{role}] {content[:30]}... -> {r.get("id")}')

time.sleep(1)

# 检查数据
print('\n--- 检查添加后状态 ---')
memories = api_get(f'/v1/memories?user_id={test_user}')
print(f'记忆数: {memories.get("count", 0)}')

context = api_post('/v1/context', {'query': '小明的女朋友', 'user_id': test_user})
ctx_text = context.get('context', '')
print(f'上下文包含 "小红": {"是" if "小红" in ctx_text else "否"}')
print(f'上下文包含 "杭州": {"是" if "杭州" in ctx_text else "否"}')

# 执行 /clear（模拟 chat_with_recall.py 的 clear_memories 方法）
print('\n--- 执行 /clear 命令 ---')
# 这就是 chat_with_recall.py 的 clear_memories 调用
clear_result = api_delete(f'/v1/memories?user_id={test_user}&confirm=true')
print(f'结果: {clear_result}')

time.sleep(0.5)

# 验证清理效果
print('\n--- 验证清理效果 ---')
memories_after = api_get(f'/v1/memories?user_id={test_user}')
print(f'记忆数: {memories_after.get("count", 0)}')

context_after = api_post('/v1/context', {'query': '小明的女朋友', 'user_id': test_user})
ctx_after = context_after.get('context', '')
print(f'上下文包含 "小红": {"是" if "小红" in ctx_after else "否"}')
print(f'上下文包含 "杭州": {"是" if "杭州" in ctx_after else "否"}')

# 搜索验证
search = api_post('/v1/memories/search', {
    'query': '小明 杭州 小红',
    'user_id': test_user,
    'top_k': 10
})
results = search.get('results', []) if isinstance(search, dict) else search
print(f'搜索结果数: {len(results) if isinstance(results, list) else 0}')

# 判断结果
if memories_after.get('count', 0) == 0 and len(results) == 0:
    print('\n\033[92m[PASS] /clear 命令测试成功!\033[0m')
else:
    print('\n\033[91m[FAIL] /clear 命令可能存在问题\033[0m')

# 输出上下文看看残留什么
if ctx_after:
    print('\n--- 残留上下文内容 ---')
    print(ctx_after[:500])
