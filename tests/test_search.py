"""测试 Recall 搜索和上下文构建能力"""
import requests
import json

base = 'http://127.0.0.1:18888'

# Test 1: 语义搜索
print('=' * 60)
print('Test 1: 语义搜索 - DeepSeek对英伟达股价的影响')
print('=' * 60)
r = requests.post(f'{base}/v1/memories/search', json={
    'query': 'DeepSeek对英伟达股价的影响',
    'user_id': 'news_collector',
    'top_k': 10
})
results = r.json()
if isinstance(results, dict):
    results = results.get('results', [])
print(f'结果数: {len(results)}')
for item in results:
    m = item.get('metadata', {})
    print(f'  [{item["score"]:.3f}] source={m.get("source")} event_time={m.get("event_time")}')
    print(f'    tags={m.get("tags")} category={m.get("category")}')
    print(f'    {item["content"][:80]}...')
    print()

def search(query, user_id='news_collector', top_k=10, **kwargs):
    payload = {'query': query, 'user_id': user_id, 'top_k': top_k, **kwargs}
    r = requests.post(f'{base}/v1/memories/search', json=payload)
    results = r.json()
    if isinstance(results, dict):
        results = results.get('results', [])
    return results

# Test 2: Source filter
print('=' * 60)
print('Test 2: source=bloomberg 过滤')
print('=' * 60)
results = search('AI', source='bloomberg')
print(f'结果数: {len(results)}')
for item in results:
    print(f'  source={item["metadata"].get("source")} | {item["content"][:60]}...')

# Test 3: Category filter
print()
print('=' * 60)
print('Test 3: category=finance 过滤')
print('=' * 60)
results = search('投资', category='finance')
print(f'结果数: {len(results)}')
for item in results:
    m = item.get('metadata', {})
    print(f'  cat={m.get("category")} src={m.get("source")} | {item["content"][:60]}...')

# Test 4: Tags filter
print()
print('=' * 60)
print('Test 4: tags=["英伟达"] 过滤')
print('=' * 60)
results = search('英伟达', tags=['英伟达'])
print(f'结果数: {len(results)}')
for item in results:
    m = item.get('metadata', {})
    print(f'  tags={m.get("tags")} | {item["content"][:60]}...')

# Test 5: Context building
print()
print('=' * 60)
print('Test 5: 上下文构建 (给外部LLM的prompt)')
print('=' * 60)
r = requests.post(f'{base}/v1/context', json={
    'query': '请分析DeepSeek R1发布后AI行业发生了哪些连锁反应？',
    'user_id': 'news_collector',
    'top_k': 10
})
data = r.json()
ctx = data.get('context', '') if isinstance(data, dict) else str(data)
print(f'上下文长度: {len(ctx)} 字符')
print()
print(ctx)

# Test 6: 查看统计
print()
print('=' * 60)
print('Test 6: 统计信息')
print('=' * 60)
r = requests.get(f'{base}/v1/stats', params={'user_id': 'news_collector'})
data = r.json()
print(json.dumps(data, indent=2, ensure_ascii=False))

# Test 7: 列出所有记忆
print()
print('=' * 60)
print('Test 7: 所有记忆列表')
print('=' * 60)
r = requests.get(f'{base}/v1/memories', params={'user_id': 'news_collector'})
data = r.json()
if isinstance(data, dict):
    memories = data.get('memories', [])
elif isinstance(data, list):
    memories = data
else:
    memories = []
print(f'总记忆数: {len(memories)}')
for mem in memories:
    m = mem.get('metadata', {})
    print(f'  id={mem["id"]}')
    print(f'    source={m.get("source")} event_time={m.get("event_time")} category={m.get("category")}')
    print(f'    entities={m.get("entities", [])[:5]}...')
    print(f'    {mem["content"][:60]}...')
    print()
