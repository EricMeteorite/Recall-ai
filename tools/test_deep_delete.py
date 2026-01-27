#!/usr/bin/env python3
"""深度测试: 实体索引和向量索引清理"""

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
print('深度测试: 实体索引和向量索引清理')
print('=' * 60)

test_user = 'deep_test_user'

# 清理
api_delete(f'/v1/memories?user_id={test_user}&confirm=true')
time.sleep(0.5)

# 获取清理前统计
stats_before = api_get('/v1/stats')
print(f'清理前 - 总记忆数: {stats_before["global"]["total_memories"]}')
print(f'清理前 - 实体缓存: {stats_before["indexes"]["cached_contents"]}')

# 添加带有独特实体的记忆
print('\n--- 添加独特实体记忆 ---')
unique_entities = ['独角兽公司', '火星基地', '量子计算机']
for i, entity in enumerate(unique_entities):
    r = api_post('/v1/memories', {
        'content': f'测试记忆{i}: {entity}是一个非常重要的存在，它改变了世界',
        'user_id': test_user
    })
    print(f'  添加: {entity} -> {r.get("id")}')

time.sleep(1)

# 检查这些实体是否出现在搜索中
print('\n--- 验证实体可搜索 ---')
for entity in unique_entities:
    search = api_post('/v1/memories/search', {
        'query': entity,
        'user_id': test_user,
        'top_k': 5
    })
    results = search.get('results', search) if isinstance(search, dict) else search
    count = len(results) if isinstance(results, list) else 0
    print(f'  搜索 "{entity}": {count} 条结果')

# 统计
stats_mid = api_get('/v1/stats')
print(f'\n添加后 - 总记忆数: {stats_mid["global"]["total_memories"]}')

# 删除
print('\n--- 执行删除 ---')
del_result = api_delete(f'/v1/memories?user_id={test_user}&confirm=true')
print(f'删除结果: {del_result}')

time.sleep(1)

# 检查删除后搜索
print('\n--- 验证删除后搜索 ---')
all_empty = True
for entity in unique_entities:
    search = api_post('/v1/memories/search', {
        'query': entity,
        'user_id': test_user,
        'top_k': 5
    })
    results = search.get('results', search) if isinstance(search, dict) else search
    count = len(results) if isinstance(results, list) else 0
    status = 'OK' if count == 0 else 'FAIL'
    if count > 0:
        all_empty = False
    print(f'  搜索 "{entity}": {count} 条结果 [{status}]')

# 最终统计
stats_after = api_get('/v1/stats')
print(f'\n删除后 - 总记忆数: {stats_after["global"]["total_memories"]}')

if all_empty:
    print('\n[PASS] 所有独特实体搜索结果已清空')
else:
    print('\n[FAIL] 部分实体搜索仍有结果')

# 检查向量搜索
print('\n--- 验证向量搜索（语义相似）---')
semantic_search = api_post('/v1/memories/search', {
    'query': '独角兽 火星 量子',  # 语义组合
    'user_id': test_user,
    'top_k': 10
})
sem_results = semantic_search.get('results', semantic_search) if isinstance(semantic_search, dict) else semantic_search
sem_count = len(sem_results) if isinstance(sem_results, list) else 0
print(f'  语义搜索结果: {sem_count} 条')
if sem_count == 0:
    print('  [PASS] 向量索引已清理')
else:
    print('  [FAIL] 向量索引可能未清理')
