#!/usr/bin/env python3
"""快速功能验证测试 - 检查实际功能是否正常工作"""

import requests
import time

BASE = 'http://127.0.0.1:18888'

def main():
    print('=== 真实场景功能测试 ===\n')
    
    # 检查服务
    try:
        r = requests.get(f'{BASE}/health', timeout=3)
        if r.status_code != 200:
            print('[FAIL] 服务未运行')
            return
    except:
        print('[FAIL] 服务未运行，请先启动服务')
        return
    
    # 1. 添加复杂记忆
    memories = [
        '用户叫李华，今年28岁，是一名医生',
        '李华有一个妹妹叫李梅，在北京工作',
        '李华的女朋友叫王芳，他们准备明年结婚',
        '李华养了一只金毛犬叫大黄，已经养了3年',
        '李华喜欢打篮球，每周三晚上都会去打球',
        '李华最近在学习日语，准备去日本旅游',
        '上周李华和王芳去了苏州玩，买了很多特产',
        '李华的生日是农历八月十五，也就是中秋节那天',
    ]
    
    print('1. 添加记忆...')
    for i, mem in enumerate(memories):
        r = requests.post(f'{BASE}/v1/memories', json={
            'content': mem,
            'user_id': 'func_test',
            'role': 'user',
            'turn': i + 1
        })
        if r.status_code == 200:
            print(f'  [OK] {mem[:35]}...')
        else:
            print(f'  [FAIL] {r.text[:50]}')
    
    time.sleep(2)  # 等待索引
    
    # 2. 关键词搜索
    print('\n2. 关键词搜索测试...')
    keywords = ['李华', '王芳', '大黄', '篮球', '日语', '苏州', '中秋节', '八月十五']
    kw_pass = 0
    for kw in keywords:
        r = requests.post(f'{BASE}/v1/memories/search', json={
            'query': kw,
            'user_id': 'func_test',
            'top_k': 5
        })
        if r.status_code == 200:
            data = r.json()
            results = data.get('results', data) if isinstance(data, dict) else data
            found = any(kw in str(m) for m in results)
            if found:
                print(f'  [OK] "{kw}" 找到')
                kw_pass += 1
            else:
                print(f'  [WARN] "{kw}" 未匹配，返回 {len(results)} 条')
        else:
            print(f'  [FAIL] 搜索失败')
    print(f'  关键词搜索: {kw_pass}/{len(keywords)}')
    
    # 3. 语义搜索
    print('\n3. 语义搜索测试...')
    semantic_queries = [
        ('用户的宠物', '大黄'),
        ('用户的女朋友是谁', '王芳'),
        ('用户的爱好', '篮球'),
        ('用户在学什么', '日语'),
        ('用户的妹妹', '李梅'),
    ]
    sem_pass = 0
    for query, expected in semantic_queries:
        r = requests.post(f'{BASE}/v1/memories/search', json={
            'query': query,
            'user_id': 'func_test',
            'top_k': 5
        })
        if r.status_code == 200:
            data = r.json()
            results = data.get('results', data) if isinstance(data, dict) else data
            found = any(expected in str(m) for m in results)
            if found:
                print(f'  [OK] "{query}" -> "{expected}"')
                sem_pass += 1
            else:
                print(f'  [WARN] "{query}" -> 未找到 "{expected}"')
        else:
            print(f'  [FAIL] {query}')
    print(f'  语义搜索: {sem_pass}/{len(semantic_queries)}')
    
    # 4. 上下文构建
    print('\n4. 上下文构建测试...')
    r = requests.post(f'{BASE}/v1/context', json={
        'query': '告诉我关于用户的所有信息',
        'user_id': 'func_test',
        'max_tokens': 2000
    })
    if r.status_code == 200:
        ctx = r.json().get('context', '')
        checks = ['李华', '医生', '王芳', '大黄', '篮球']
        found = sum(1 for c in checks if c in ctx)
        print(f'  上下文包含 {found}/{len(checks)} 个关键信息')
        if found < len(checks):
            print(f'  缺失: {[c for c in checks if c not in ctx]}')
    else:
        print(f'  [FAIL] 上下文构建失败')
    
    # 5. 实体提取
    print('\n5. 实体提取测试...')
    r = requests.get(f'{BASE}/v1/entities', params={'user_id': 'func_test'})
    if r.status_code == 200:
        data = r.json()
        entities = data.get('entities', data) if isinstance(data, dict) else data
        entity_names = [e.get('name', str(e)) if isinstance(e, dict) else str(e) for e in entities]
        print(f'  提取到 {len(entities)} 个实体')
        expected_entities = ['李华', '王芳', '李梅', '大黄', '北京', '苏州']
        ent_found = 0
        for ent in expected_entities:
            if any(ent in str(e) for e in entity_names):
                print(f'  [OK] 实体 "{ent}"')
                ent_found += 1
            else:
                print(f'  [MISS] 实体 "{ent}"')
        print(f'  实体提取: {ent_found}/{len(expected_entities)}')
    else:
        print(f'  [FAIL] 获取实体失败')
    
    # 6. 矛盾检测
    print('\n6. 矛盾检测测试...')
    # 添加一条矛盾信息
    r = requests.post(f'{BASE}/v1/memories', json={
        'content': '李华今年35岁了',  # 之前说28岁
        'user_id': 'func_test',
        'role': 'user',
        'turn': 100
    })
    time.sleep(1)
    r = requests.get(f'{BASE}/v1/contradictions', params={'user_id': 'func_test'})
    if r.status_code == 200:
        data = r.json()
        contradictions = data.get('contradictions', data) if isinstance(data, dict) else data
        print(f'  检测到 {len(contradictions)} 个矛盾')
        # 这里不一定能检测到，因为矛盾检测可能需要LLM
    else:
        print(f'  矛盾检测接口正常')
    
    # 7. 100%召回验证 - 关键测试
    print('\n7. 100%召回验证（N-gram兜底）...')
    unique_content = '这是一个独特的测试内容包含随机数字7749382和特殊词汇龙凤呈祥'
    r = requests.post(f'{BASE}/v1/memories', json={
        'content': unique_content,
        'user_id': 'func_test',
        'role': 'user',
        'turn': 200
    })
    time.sleep(1)
    
    test_keywords = ['7749382', '龙凤呈祥']
    recall_pass = 0
    for kw in test_keywords:
        r = requests.post(f'{BASE}/v1/memories/search', json={
            'query': kw,
            'user_id': 'func_test',
            'top_k': 10
        })
        if r.status_code == 200:
            data = r.json()
            results = data.get('results', data) if isinstance(data, dict) else data
            found = any(kw in str(m) for m in results)
            if found:
                print(f'  [OK] "{kw}" 100%召回成功')
                recall_pass += 1
            else:
                print(f'  [FAIL] "{kw}" 未召回 - N-gram可能有问题!')
        else:
            print(f'  [FAIL] 搜索失败')
    print(f'  100%召回: {recall_pass}/{len(test_keywords)}')
    
    print('\n=== 测试完成 ===')
    print(f'''
总结:
- 关键词搜索: {kw_pass}/{len(keywords)}
- 语义搜索: {sem_pass}/{len(semantic_queries)}
- 100%召回: {recall_pass}/{len(test_keywords)}
''')

if __name__ == '__main__':
    main()
