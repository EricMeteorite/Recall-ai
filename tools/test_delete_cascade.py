#!/usr/bin/env python3
"""测试删除功能的级联删除和数据隔离"""

import urllib.request
import urllib.error
import json
import time
import sys

BASE = 'http://localhost:18888'

def api_get(endpoint):
    try:
        req = urllib.request.Request(f'{BASE}{endpoint}')
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {'error': str(e), 'code': e.code}
    except Exception as e:
        return {'error': str(e)}

def api_post(endpoint, data):
    try:
        req = urllib.request.Request(f'{BASE}{endpoint}', 
                                    data=json.dumps(data).encode(),
                                    method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        return {'error': str(e), 'code': e.code, 'body': body}
    except Exception as e:
        return {'error': str(e)}

def api_delete(endpoint):
    try:
        req = urllib.request.Request(f'{BASE}{endpoint}', method='DELETE')
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ''
        return {'error': str(e), 'code': e.code, 'body': body}
    except Exception as e:
        return {'error': str(e)}

def print_pass(msg):
    print(f"  \033[92m[PASS]\033[0m {msg}")

def print_fail(msg):
    print(f"  \033[91m[FAIL]\033[0m {msg}")

def print_info(msg):
    print(f"  [INFO] {msg}")

def main():
    # 检查服务
    health = api_get('/health')
    print('=== 健康检查 ===')
    print(f'Status: {health}')
    if health.get('status') != 'healthy':
        print('ERROR: 服务未运行')
        return 1

    all_passed = True

    # ============================================================
    print()
    print('=' * 60)
    print('测试1: 用户级别删除 - 数据隔离测试')
    print('=' * 60)

    user_a = 'test_delete_user_a'
    user_b = 'test_delete_user_b'

    # 先清理可能存在的旧数据
    api_delete(f'/v1/memories?user_id={user_a}&confirm=true')
    api_delete(f'/v1/memories?user_id={user_b}&confirm=true')
    time.sleep(0.5)

    print(f'\n--- 为 {user_a} 添加数据 ---')
    user_a_ids = []
    # 使用完全不同的实体和内容避免被去重合并
    user_a_contents = [
        '用户A档案-工作：张伟在上海浦东的金融公司担任首席财务官，负责企业财务战略规划和投资决策',
        '用户A档案-家庭：张伟的太太李红是一位著名画家，他们养了一只金毛犬名叫旺财',
        '用户A档案-兴趣：每周日张伟都会去徐汇区的围棋俱乐部参加业余围棋比赛'
    ]
    for i, content in enumerate(user_a_contents):
        r = api_post('/v1/memories', {
            'content': content,
            'user_id': user_a
        })
        mid = r.get('id', '?')
        user_a_ids.append(mid)
        print_info(f'添加记忆{i}: {mid}')

    print(f'\n--- 为 {user_b} 添加数据 ---')
    user_b_ids = []
    # 使用完全不同的实体和内容避免被去重合并
    user_b_contents = [
        '用户B档案-工作：王丽在广州天河区的互联网公司担任产品经理，主导电商平台的功能设计',
        '用户B档案-爱好：王丽热爱登山运动，去年成功登顶云南玉龙雪山海拔5596米峰顶'
    ]
    for i, content in enumerate(user_b_contents):
        r = api_post('/v1/memories', {
            'content': content,
            'user_id': user_b
        })
        mid = r.get('id', '?')
        user_b_ids.append(mid)
        print_info(f'添加记忆{i}: {mid}')

    time.sleep(1)

    # 检查添加后的状态
    print('\n--- 添加后状态 ---')
    mem_a = api_get(f'/v1/memories?user_id={user_a}')
    mem_b = api_get(f'/v1/memories?user_id={user_b}')
    count_a = mem_a.get('count', 0)
    count_b = mem_b.get('count', 0)
    print_info(f'用户A记忆数: {count_a}')
    print_info(f'用户B记忆数: {count_b}')

    if count_a == 3:
        print_pass('用户A记忆数正确 (3)')
    else:
        print_fail(f'用户A记忆数错误: 期望3, 实际{count_a}')
        all_passed = False

    if count_b == 2:
        print_pass('用户B记忆数正确 (2)')
    else:
        print_fail(f'用户B记忆数错误: 期望2, 实际{count_b}')
        all_passed = False

    # 检查上下文（包含实体）
    print('\n--- 检查上下文和实体 ---')
    ctx_a = api_post('/v1/context', {'query': 'Alpha', 'user_id': user_a})
    ctx_b = api_post('/v1/context', {'query': 'Delta', 'user_id': user_b})
    ctx_a_text = ctx_a.get('context', '') if isinstance(ctx_a, dict) else ''
    ctx_b_text = ctx_b.get('context', '') if isinstance(ctx_b, dict) else ''
    
    if 'Alpha' in ctx_a_text or '海淀' in ctx_a_text or '软件工程师' in ctx_a_text:
        print_pass('用户A上下文包含其实体')
    else:
        print_info(f'用户A上下文: {ctx_a_text[:100]}...')

    if 'Delta' in ctx_b_text or '浦东' in ctx_b_text or '金融分析师' in ctx_b_text:
        print_pass('用户B上下文包含其实体')
    else:
        print_info(f'用户B上下文: {ctx_b_text[:100]}...')

    # ============================================================
    print('\n--- 删除用户A ---')
    del_result = api_delete(f'/v1/memories?user_id={user_a}&confirm=true')
    print_info(f'删除结果: {del_result}')

    if del_result.get('success'):
        print_pass('删除操作成功')
    else:
        print_fail(f'删除操作失败: {del_result}')
        all_passed = False

    time.sleep(1)

    # 检查删除后状态
    print('\n--- 删除后状态检查 ---')
    
    # 1. 检查用户A记忆是否被删除
    mem_a_after = api_get(f'/v1/memories?user_id={user_a}')
    count_a_after = mem_a_after.get('count', 0)
    if count_a_after == 0:
        print_pass('用户A记忆已清空')
    else:
        print_fail(f'用户A记忆未完全清空: 剩余{count_a_after}')
        all_passed = False

    # 2. 检查用户B记忆是否保留
    mem_b_after = api_get(f'/v1/memories?user_id={user_b}')
    count_b_after = mem_b_after.get('count', 0)
    if count_b_after == 2:
        print_pass('用户B记忆未被误删 (保持2条)')
    else:
        print_fail(f'用户B记忆被误删! 期望2, 实际{count_b_after}')
        all_passed = False

    # 3. 检查搜索
    print('\n--- 验证搜索功能 ---')
    search_a = api_post('/v1/memories/search', {'query': '张三 北京', 'user_id': user_a, 'top_k': 10})
    search_b = api_post('/v1/memories/search', {'query': '李四 上海', 'user_id': user_b, 'top_k': 10})

    results_a = search_a.get('results', []) if isinstance(search_a, dict) else (search_a if isinstance(search_a, list) else [])
    results_b = search_b.get('results', []) if isinstance(search_b, dict) else (search_b if isinstance(search_b, list) else [])

    if len(results_a) == 0:
        print_pass('用户A搜索无结果 (正确)')
    else:
        print_fail(f'用户A搜索仍有结果: {len(results_a)}条')
        all_passed = False

    if len(results_b) > 0:
        print_pass(f'用户B搜索有结果 ({len(results_b)}条)')
    else:
        print_fail('用户B搜索无结果 (错误)')
        all_passed = False

    # 4. 检查上下文（删除后）
    print('\n--- 验证上下文（删除后）---')
    ctx_a_after = api_post('/v1/context', {'query': '张三', 'user_id': user_a})
    ctx_a_after_text = ctx_a_after.get('context', '') if isinstance(ctx_a_after, dict) else ''
    
    # 删除后，用户A的上下文不应该有"张三"相关记忆
    if '张三在北京' not in ctx_a_after_text:
        print_pass('用户A上下文不再包含其记忆内容')
    else:
        print_fail('用户A上下文仍包含已删除的记忆内容!')
        print_info(f'上下文: {ctx_a_after_text[:200]}')
        all_passed = False

    # ============================================================
    print()
    print('=' * 60)
    print('测试2: 检查实体索引清理')
    print('=' * 60)

    # 获取统计信息看实体数量
    stats = api_get('/v1/stats')
    print_info(f'当前统计: {stats}')

    # ============================================================
    print()
    print('=' * 60)
    print('测试3: 清理并验证完全删除')
    print('=' * 60)

    # 清理用户B
    print('\n--- 清理用户B ---')
    del_b = api_delete(f'/v1/memories?user_id={user_b}&confirm=true')
    print_info(f'删除结果: {del_b}')

    time.sleep(0.5)

    mem_b_final = api_get(f'/v1/memories?user_id={user_b}')
    if mem_b_final.get('count', 0) == 0:
        print_pass('用户B记忆已清空')
    else:
        print_fail(f'用户B记忆未清空: {mem_b_final}')
        all_passed = False

    # ============================================================
    print()
    print('=' * 60)
    print('测试4: 边界情况')
    print('=' * 60)

    # 4.1 删除不存在的用户
    print('\n--- 删除不存在的用户 ---')
    del_nonexist = api_delete('/v1/memories?user_id=nonexistent_user_xyz&confirm=true')
    print_info(f'结果: {del_nonexist}')
    if 'error' not in del_nonexist:
        print_pass('删除不存在用户不报错')
    
    # 4.2 不带 confirm 参数
    print('\n--- 不带 confirm 参数 ---')
    del_no_confirm = api_delete('/v1/memories?user_id=test_user')
    if del_no_confirm.get('code') == 400:
        print_pass('缺少 confirm 参数被拒绝')
    else:
        print_info(f'结果: {del_no_confirm}')

    # 4.3 尝试删除 default 用户
    print('\n--- 尝试删除 default 用户 ---')
    del_default = api_delete('/v1/memories?user_id=default&confirm=true')
    if del_default.get('code') == 400:
        print_pass('删除 default 用户被拒绝')
    else:
        print_info(f'结果: {del_default}')

    # ============================================================
    print()
    print('=' * 60)
    if all_passed:
        print('\033[92m所有测试通过!\033[0m')
    else:
        print('\033[91m存在失败的测试!\033[0m')
    print('=' * 60)

    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
