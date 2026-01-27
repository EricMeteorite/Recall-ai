#!/usr/bin/env python3
"""综合测试: 验证删除后上下文完全干净"""

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
print('综合测试: 验证删除后上下文完全干净')
print('=' * 60)

test_user = 'context_clean_test'

# 清理旧数据
api_delete(f'/v1/memories?user_id={test_user}&confirm=true')
time.sleep(0.5)

# 添加带有独特实体的记忆
print('\n--- 添加独特实体记忆 ---')
unique_entities = ['阿波罗登月计划', '马斯克的SpaceX', '特斯拉电动车']
for i, entity in enumerate(unique_entities):
    r = api_post('/v1/memories', {
        'content': f'{entity}是人类科技进步的重要里程碑',
        'user_id': test_user
    })
    print(f'  添加: {entity} -> {r.get("id")}')

time.sleep(1)

# 检查上下文
print('\n--- 删除前上下文 ---')
ctx_before = api_post('/v1/context', {'query': '科技进步', 'user_id': test_user})
ctx_before_text = ctx_before.get('context', '')
print(f'  长度: {len(ctx_before_text)} 字符')

found_before = []
for entity in unique_entities:
    # 检查实体名称的关键部分
    key_part = entity.split('的')[-1] if '的' in entity else entity[:4]
    if key_part in ctx_before_text:
        found_before.append(entity)
print(f'  包含的实体: {found_before}')

# 执行删除
print('\n--- 执行删除 ---')
del_result = api_delete(f'/v1/memories?user_id={test_user}&confirm=true')
print(f'  结果: {del_result}')

time.sleep(1)

# 检查删除后上下文
print('\n--- 删除后上下文 ---')
ctx_after = api_post('/v1/context', {'query': '科技进步', 'user_id': test_user})
ctx_after_text = ctx_after.get('context', '')
print(f'  长度: {len(ctx_after_text)} 字符')

found_after = []
for entity in unique_entities:
    key_part = entity.split('的')[-1] if '的' in entity else entity[:4]
    if key_part in ctx_after_text:
        found_after.append(entity)
print(f'  包含的实体: {found_after}')

# 验证记忆
print('\n--- 验证记忆 ---')
memories = api_get(f'/v1/memories?user_id={test_user}')
print(f'  记忆数: {memories.get("count", 0)}')

# 验证搜索
print('\n--- 验证搜索 ---')
for entity in unique_entities:
    search = api_post('/v1/memories/search', {
        'query': entity,
        'user_id': test_user,
        'top_k': 5
    })
    results = search.get('results', []) if isinstance(search, dict) else (search if isinstance(search, list) else [])
    count = len(results)
    status = 'OK' if count == 0 else 'FAIL'
    print(f'  搜索 "{entity[:10]}...": {count} 条 [{status}]')

# 总结
print('\n' + '=' * 60)
if not found_after and memories.get('count', 0) == 0:
    print('\033[92m[PASS] 所有测试通过! 删除功能工作正常!\033[0m')
else:
    print('\033[91m[FAIL] 存在问题:\033[0m')
    if found_after:
        print(f'  - 上下文中仍有实体: {found_after}')
    if memories.get('count', 0) > 0:
        print(f'  - 记忆未完全清空: {memories.get("count")}')
print('=' * 60)

# 显示残留上下文
if ctx_after_text:
    print('\n--- 残留上下文内容 ---')
    print(ctx_after_text[:500])
