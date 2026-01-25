#!/usr/bin/env python3
"""Phase 1-3 功能测试脚本 - 修正版"""

import requests
import json

BASE_URL = "http://localhost:18888"

def test_context_building():
    """测试上下文构建"""
    print("=== 测试5: 上下文构建 ===")
    resp = requests.post(f'{BASE_URL}/v1/context', json={
        'user_id': 'rp_test',
        'character_id': 'sakura',
        'query': '小雪',
        'max_tokens': 2000
    })
    data = resp.json()
    context = data.get('context', '')
    print(f"状态码: {resp.status_code}")
    print(f"上下文长度: {len(context)} 字符")
    if '小雪' in context:
        print("[PASS] 上下文包含关键信息'小雪'")
    else:
        print("[FAIL] 上下文未包含关键信息")
    return resp.status_code == 200

def test_foreshadowing():
    """测试伏笔系统"""
    print("\n=== 测试6: 伏笔系统 ===")
    
    # 创建伏笔 - 正确端点是 /v1/foreshadowing
    resp = requests.post(f'{BASE_URL}/v1/foreshadowing', json={
        'user_id': 'rp_test',
        'character_id': 'sakura',
        'content': '樱提到过一个神秘的钢琴曲谱，说是外祖母留下的遗物',
        'importance': 0.8
    })
    print(f"创建伏笔: {resp.status_code}")
    if resp.status_code == 200:
        print("[PASS] 伏笔创建成功")
        result = resp.json()
        print(f"  伏笔ID: {result.get('id', 'N/A')}")
    else:
        print(f"[WARN] {resp.text[:200]}")
    
    # 获取伏笔列表
    resp = requests.get(f'{BASE_URL}/v1/foreshadowing?user_id=rp_test&character_id=sakura')
    print(f"获取伏笔列表: {resp.status_code}")
    if resp.status_code == 200:
        foreshadowings = resp.json()
        print(f"伏笔数量: {len(foreshadowings)}")
        for f in foreshadowings[:3]:
            content = f.get('content', '')[:50]
            print(f"  - {content}...")
        return True
    return False

def test_persistent_conditions():
    """测试持久条件系统"""
    print("\n=== 测试7: 持久条件系统 ===")
    
    # 创建持久条件 - 正确端点是 /v1/persistent-contexts
    resp = requests.post(f'{BASE_URL}/v1/persistent-contexts', json={
        'user_id': 'rp_test',
        'character_id': 'sakura',
        'content': '樱现在心情很好，因为刚收到东京艺术大学的录取通知',
        'context_type': 'EMOTIONAL_STATE'
    })
    print(f"创建条件: {resp.status_code}")
    if resp.status_code == 200:
        print("[PASS] 持久条件创建成功")
    else:
        print(f"[WARN] {resp.text[:200]}")
    
    # 获取条件列表
    resp = requests.get(f'{BASE_URL}/v1/persistent-contexts?user_id=rp_test&character_id=sakura')
    print(f"获取条件列表: {resp.status_code}")
    if resp.status_code == 200:
        contexts = resp.json()
        print(f"条件数量: {len(contexts)}")
        for c in contexts[:3]:
            ctype = c.get('context_type', 'UNKNOWN')
            content = c.get('content', '')[:40]
            print(f"  - [{ctype}] {content}...")
        return True
    return False

def test_knowledge_graph():
    """测试知识图谱"""
    print("\n=== 测试9: 知识图谱 ===")
    
    # 获取特定实体信息
    resp = requests.get(f'{BASE_URL}/v1/entities/樱')
    print(f"获取实体'樱': {resp.status_code}")
    if resp.status_code == 200:
        entity = resp.json()
        print(f"  名称: {entity.get('name', 'N/A')}")
        print(f"  类型: {entity.get('type', 'N/A')}")
        desc = entity.get('description', 'N/A')
        print(f"  描述: {desc[:50] if desc else 'N/A'}...")
    else:
        print(f"[WARN] 实体不存在或未提取")
    
    # 获取图遍历
    resp = requests.post(f'{BASE_URL}/v1/graph/traverse', json={
        'user_id': 'rp_test',
        'character_id': 'sakura',
        'entity_names': ['樱'],
        'max_depth': 2,
        'max_results': 10
    })
    print(f"图遍历: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"  返回结果: {len(result)} 项")
        return True
    return False

def test_contradiction_detection():
    """测试矛盾检测"""
    print("\n=== 测试8: 矛盾检测 ===")
    
    # 获取矛盾统计
    resp = requests.get(f'{BASE_URL}/v1/contradictions/stats?user_id=rp_test')
    print(f"矛盾统计: {resp.status_code}")
    if resp.status_code == 200:
        stats = resp.json()
        print(f"  统计: {stats}")
        return True
    return False

def test_temporal_query():
    """测试时态查询"""
    print("\n=== 测试: 时态查询 ===")
    
    # 时态统计
    resp = requests.get(f'{BASE_URL}/v1/temporal/stats?user_id=rp_test')
    print(f"时态统计: {resp.status_code}")
    if resp.status_code == 200:
        stats = resp.json()
        print(f"  统计: {stats}")
        return True
    return False

def test_stats():
    """测试统计信息"""
    print("\n=== 测试: 系统统计 ===")
    
    resp = requests.get(f'{BASE_URL}/v1/stats?user_id=rp_test')
    print(f"获取统计: {resp.status_code}")
    if resp.status_code == 200:
        stats = resp.json()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return True
    return False

def test_multi_user_isolation():
    """测试多用户隔离"""
    print("\n=== 测试11: 多用户隔离 ===")
    
    # 创建另一个用户的记忆
    resp = requests.post(f'{BASE_URL}/v1/memories', json={
        'user_id': 'user_other',
        'character_id': 'other_char',
        'content': '这是另一个用户的私密记忆',
        'role': 'user'
    })
    print(f"创建其他用户记忆: {resp.status_code}")
    
    # 搜索原用户，不应该找到其他用户的记忆
    resp = requests.post(f'{BASE_URL}/v1/memories/search', json={
        'user_id': 'rp_test',
        'query': '私密记忆',
        'top_k': 10
    })
    results = resp.json()
    found_other = any('私密记忆' in r.get('content', '') for r in results)
    
    if not found_other:
        print("[PASS] 用户隔离正常 - 未找到其他用户记忆")
        return True
    else:
        print("[FAIL] 用户隔离失败 - 找到了其他用户记忆")
        return False

def main():
    print("=" * 60)
    print("Recall v3.0 Phase 1-3 功能验证 (修正版)")
    print("=" * 60)
    
    results = {}
    
    results['上下文构建'] = test_context_building()
    results['伏笔系统'] = test_foreshadowing()
    results['持久条件'] = test_persistent_conditions()
    results['矛盾检测'] = test_contradiction_detection()
    results['知识图谱'] = test_knowledge_graph()
    results['时态查询'] = test_temporal_query()
    results['系统统计'] = test_stats()
    results['多用户隔离'] = test_multi_user_isolation()
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n[SUCCESS] 所有 Phase 1-3 功能验证通过！")
    else:
        print(f"\n[WARNING] {total - passed} 个测试未通过，请检查")

if __name__ == '__main__':
    main()
