"""测试 Recall 搜索和上下文构建能力 (API 集成测试)

这些测试需要 Recall 服务器运行在 127.0.0.1:18888。
conftest.py 的 recall_server 夹具会自动启动服务器。
"""
import pytest
import requests
import json

BASE = 'http://127.0.0.1:18888'


def _search(query, user_id='news_collector', top_k=10, **kwargs):
    """Helper: 调用搜索 API"""
    payload = {'query': query, 'user_id': user_id, 'top_k': top_k, **kwargs}
    r = requests.post(f'{BASE}/v1/memories/search', json=payload)
    assert r.status_code == 200, f"Search failed: {r.status_code} {r.text[:200]}"
    results = r.json()
    if isinstance(results, dict):
        results = results.get('results', [])
    return results


class TestSearchAPI:
    """搜索 API 集成测试"""

    def test_semantic_search(self):
        """语义搜索基本功能"""
        r = requests.post(f'{BASE}/v1/memories/search', json={
            'query': 'DeepSeek对英伟达股价的影响',
            'user_id': 'news_collector',
            'top_k': 10
        })
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_source_filter(self):
        """source 过滤搜索"""
        results = _search('AI', source='bloomberg')
        assert isinstance(results, list)

    def test_category_filter(self):
        """category 过滤搜索"""
        results = _search('投资', category='finance')
        assert isinstance(results, list)

    def test_tags_filter(self):
        """tags 过滤搜索"""
        results = _search('英伟达', tags=['英伟达'])
        assert isinstance(results, list)

    def test_context_building(self):
        """上下文构建 API"""
        r = requests.post(f'{BASE}/v1/context', json={
            'query': '请分析DeepSeek R1发布后AI行业发生了哪些连锁反应？',
            'user_id': 'news_collector',
            'top_k': 10
        })
        assert r.status_code == 200

    def test_stats(self):
        """统计信息 API"""
        r = requests.get(f'{BASE}/v1/stats', params={'user_id': 'news_collector'})
        assert r.status_code == 200

    def test_list_memories(self):
        """列出记忆 API"""
        r = requests.get(f'{BASE}/v1/memories', params={'user_id': 'news_collector'})
        assert r.status_code == 200

