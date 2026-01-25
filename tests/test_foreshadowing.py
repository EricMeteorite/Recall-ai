"""测试伏笔系统"""
import requests
import json

BASE_URL = 'http://127.0.0.1:18888'

# 添加伏笔
print("=== 添加伏笔测试 ===")
data = {
    'user_id': 'rp_test',
    'character_id': 'sakura',
    'content': '樱提到妈妈美雪是日本画艺术家，但从未提及父亲，这可能暗示着家庭情况有隐藏故事',
    'hint': '家庭背景可能有隐藏故事线'
}
r = requests.post(f'{BASE_URL}/v1/foreshadowing', json=data)
print(f"添加伏笔1: {r.status_code}")
if r.status_code == 200:
    print(f"  ID: {r.json().get('id', 'N/A')}")

data2 = {
    'user_id': 'rp_test',
    'character_id': 'sakura',
    'content': '樱说自己最喜欢画日落和天空，这种偏好可能与某个重要回忆有关',
    'hint': '日落画与镰仓回忆的深层联系'
}
r = requests.post(f'{BASE_URL}/v1/foreshadowing', json=data2)
print(f"添加伏笔2: {r.status_code}")

# 获取伏笔列表
print("\n=== 伏笔列表 ===")
r = requests.get(f'{BASE_URL}/v1/foreshadowing', params={'user_id': 'rp_test', 'character_id': 'sakura'})
foreshadowings = r.json()
print(f"伏笔数: {len(foreshadowings)}")
for f in foreshadowings:
    status = f.get('status', 'active')
    content = f.get('content', '')[:50]
    print(f"  [{status}] {content}...")

# 测试伏笔分析 API
print("\n=== 伏笔分析测试 ===")
analyze_data = {
    'user_id': 'rp_test',
    'character_id': 'sakura',
    'content': '今天和樱聊到了她的家庭，她似乎有些回避关于父亲的话题'
}
r = requests.post(f'{BASE_URL}/v1/foreshadowing/analyze', json=analyze_data)
print(f"分析状态: {r.status_code}")
if r.status_code == 200:
    result = r.json()
    print(f"分析结果: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
else:
    print(f"错误: {r.text[:200]}")

