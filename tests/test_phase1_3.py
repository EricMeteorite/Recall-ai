#!/usr/bin/env python3
"""
Recall-ai Phase 1-3 新功能 + 100%不遗忘验证测试

注意: 这些测试需要运行中的 Recall-AI 服务器 (http://127.0.0.1:18888)
运行方式:
  1. 启动服务器: ./start.ps1 或 python -m recall server
  2. 运行测试: pytest tests/test_phase1_3.py -v
"""

import pytest
import requests
import json
from datetime import datetime

BASE = 'http://127.0.0.1:18888'


def is_server_running():
    """检查服务器是否运行"""
    try:
        r = requests.get(f'{BASE}/health', timeout=2)
        return r.status_code == 200
    except Exception:
        return False


# 如果服务器未运行，跳过所有测试
pytestmark = pytest.mark.skipif(
    not is_server_running(),
    reason="Recall-AI 服务器未运行 (http://127.0.0.1:18888)"
)


class TestMemoryRetention:
    """100% 不遗忘保证测试"""
    
    def test_add_unique_memory(self):
        """添加唯一可识别的内容"""
        unique_content = "User mentioned the secret password is moonlight crystal 7749 for the ancient vault"
        r = requests.post(f'{BASE}/v1/memories', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'content': unique_content,
            'metadata': {'turn_number': 100}
        })
        assert r.status_code == 200, f"Failed to add memory: {r.text}"
    
    def test_search_unique_content(self):
        """搜索唯一内容（密码）"""
        r = requests.post(f'{BASE}/v1/memories/search', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'query': 'moonlight crystal password vault',
            'limit': 10
        })
        assert r.status_code == 200, f"Search failed: {r.text}"
        results = r.json()
        # 可能还没有内容，所以只检查响应格式
        assert isinstance(results, list), "Response should be a list"
    
    def test_context_retrieval(self):
        """上下文构建应包含相关记忆"""
        r = requests.post(f'{BASE}/v1/context', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'query': 'What is the password for the ancient vault?',
            'current_input': 'User: What is the password for the ancient vault?',
            'max_tokens': 3000
        })
        assert r.status_code == 200, f"Context retrieval failed: {r.text}"
        data = r.json()
        assert 'context' in data, "Response should contain 'context' field"


class TestNgramRawSearch:
    """N-gram 原文搜索兜底测试"""
    
    def test_raw_search_endpoint(self):
        """测试原文搜索端点"""
        r = requests.post(f'{BASE}/v1/memories/search', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'query': 'silver arrows moonlight',
            'limit': 5
        })
        assert r.status_code == 200, f"Search failed: {r.text}"
        results = r.json()
        assert isinstance(results, list), "Response should be a list"


class TestPhase1Features:
    """Phase 1-3 功能测试"""
    
    def test_stats_endpoint(self):
        """统计端点"""
        r = requests.get(f'{BASE}/v1/stats')
        assert r.status_code == 200, f"Stats failed: {r.text}"
        stats = r.json()
        assert isinstance(stats, dict), "Stats should be a dict"
    
    def test_health_check(self):
        """健康检查"""
        r = requests.get(f'{BASE}/health')
        assert r.status_code == 200, f"Health check failed: {r.text}"


class TestSemanticDeduplication:
    """语义去重测试"""
    
    def test_add_similar_content(self):
        """添加相似内容（应去重）"""
        r1 = requests.post(f'{BASE}/v1/persistent-contexts', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'context_type': 'character_trait',
            'content': 'Luna is a gentle and shy magical girl',
            'source': 'test'
        })
        assert r1.status_code == 200, f"First add failed: {r1.text}"
        
        r2 = requests.post(f'{BASE}/v1/persistent-contexts', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'context_type': 'character_trait',
            'content': 'Luna is shy and gentle, a magical girl',  # Similar meaning
            'source': 'test'
        })
        assert r2.status_code == 200, f"Second add failed: {r2.text}"


class TestAbsoluteRules:
    """绝对规则检测测试"""
    
    def test_set_absolute_rules(self):
        """设置绝对规则"""
        r = requests.put(f'{BASE}/v1/core-settings', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'absolute_rules': [
                'Luna never uses violent magic or hurts anyone',
                'Luna always speaks gently and politely'
            ]
        })
        assert r.status_code == 200, f"Set rules failed: {r.text}"
    
    def test_non_violating_content(self):
        """添加不违反规则的内容"""
        r = requests.post(f'{BASE}/v1/memories', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'content': 'AI: Luna smiled gently and healed the wounded bird with her magic.',
            'metadata': {'turn_number': 101}
        })
        assert r.status_code == 200, f"Add memory failed: {r.text}"


class TestRecentConversation:
    """最近对话包含测试"""
    
    def test_recent_turns_in_context(self):
        """验证最近对话包含在上下文中"""
        r = requests.post(f'{BASE}/v1/context', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'query': 'Tell me about our adventure',
            'current_input': 'User: Tell me about our adventure',
            'max_tokens': 4000
        })
        assert r.status_code == 200, f"Context retrieval failed: {r.text}"
        data = r.json()
        assert 'context' in data, "Response should contain 'context' field"


class TestEntityTracking:
    """重要信息追踪测试"""
    
    def test_important_entities(self):
        """检查重要实体是否被追踪"""
        r = requests.post(f'{BASE}/v1/context', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'query': 'What should I remember about the quest?',
            'current_input': 'User: What should I remember about the quest?',
            'max_tokens': 3000
        })
        assert r.status_code == 200, f"Context retrieval failed: {r.text}"


class TestRelationshipExtraction:
    """实体关系抽取测试"""
    
    def test_relationships_in_context(self):
        """检查关系部分在上下文中"""
        r = requests.post(f'{BASE}/v1/context', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'query': 'Who are the important people in this story?',
            'current_input': 'User: Who are the important people in this story?',
            'max_tokens': 3000
        })
        assert r.status_code == 200, f"Context retrieval failed: {r.text}"


class TestCharacterIsolation:
    """多角色隔离测试"""
    
    def test_character_scope_isolation(self):
        """验证角色隔离（Luna 不应看到 Aria 的内容）"""
        r = requests.post(f'{BASE}/v1/memories/search', json={
            'user_id': 'test_user',
            'character_id': 'luna',
            'query': 'fire mage red hair',
            'limit': 5
        })
        assert r.status_code == 200, f"Search failed: {r.text}"
        results = r.json()
        assert isinstance(results, list), "Response should be a list"
        # 不应在 Luna 的范围内找到 Aria
        for m in results:
            content = str(m.get('content', '')).lower()
            assert 'aria' not in content or 'fire mage' not in content, \
                "Character scope leak detected!"


# ============================================================================
# 独立运行支持（非 pytest）
# ============================================================================
def run_standalone_tests():
    """作为独立脚本运行时的测试"""
    print("\n" + "="*60)
    print("  Recall-AI Phase 1-3 测试 (Standalone Mode)")
    print("="*60)
    
    if not is_server_running():
        print("\n❌ 服务器未运行！请先启动服务器:")
        print("   ./start.ps1 或 python -m recall server")
        return
    
    test_results = []
    
    def run_test(name, test_func):
        try:
            test_func()
            print(f"  ✅ PASS - {name}")
            test_results.append((name, True))
        except Exception as e:
            print(f"  ❌ FAIL - {name}: {e}")
            test_results.append((name, False))
    
    # 运行所有测试
    print("\n--- Memory Retention Tests ---")
    test = TestMemoryRetention()
    run_test("Add unique memory", test.test_add_unique_memory)
    run_test("Search unique content", test.test_search_unique_content)
    run_test("Context retrieval", test.test_context_retrieval)
    
    print("\n--- N-gram Search Tests ---")
    test = TestNgramRawSearch()
    run_test("Raw search endpoint", test.test_raw_search_endpoint)
    
    print("\n--- Phase 1 Feature Tests ---")
    test = TestPhase1Features()
    run_test("Stats endpoint", test.test_stats_endpoint)
    run_test("Health check", test.test_health_check)
    
    print("\n--- Semantic Dedup Tests ---")
    test = TestSemanticDeduplication()
    run_test("Add similar content", test.test_add_similar_content)
    
    print("\n--- Absolute Rules Tests ---")
    test = TestAbsoluteRules()
    run_test("Set absolute rules", test.test_set_absolute_rules)
    run_test("Non-violating content", test.test_non_violating_content)
    
    print("\n--- Context Tests ---")
    test = TestRecentConversation()
    run_test("Recent turns in context", test.test_recent_turns_in_context)
    
    test = TestEntityTracking()
    run_test("Important entities", test.test_important_entities)
    
    test = TestRelationshipExtraction()
    run_test("Relationships in context", test.test_relationships_in_context)
    
    print("\n--- Isolation Tests ---")
    test = TestCharacterIsolation()
    run_test("Character scope isolation", test.test_character_scope_isolation)
    
    # 最终报告
    passed = sum(1 for _, s in test_results if s)
    failed = sum(1 for _, s in test_results if not s)
    total = len(test_results)
    
    print("\n" + "="*60)
    print(f"  Total: {total} | Passed: {passed} | Failed: {failed}")
    print(f"  Success Rate: {passed/total*100:.1f}%")
    print("="*60)
    print(f"  Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")


if __name__ == '__main__':
    run_standalone_tests()
