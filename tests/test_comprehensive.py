#!/usr/bin/env python3
"""
Recall-ai 综合检查脚本
彻底检查所有潜在问题
"""

import os
import sys
import tempfile
import time
import traceback

# 设置轻量模式
os.environ['RECALL_EMBEDDING_MODE'] = 'none'

def print_header(title):
    print()
    print('=' * 60)
    print(f' {title}')
    print('=' * 60)

def print_ok(msg):
    print(f'  ✓ {msg}')

def print_fail(msg):
    print(f'  ✗ {msg}')

def print_warn(msg):
    print(f'  ⚠ {msg}')

# 收集所有问题
ALL_ERRORS = []
ALL_WARNINGS = []

# ============================================================
# 1. 模块导入检查
# ============================================================
print_header('1. 模块导入检查')

modules = [
    'recall.models',
    'recall.storage', 
    'recall.index',
    'recall.graph',
    'recall.processor',
    'recall.retrieval',
    'recall.utils',
    'recall.embedding',
    'recall.engine',
    'recall.server',
    'recall.cli',
]

for mod in modules:
    try:
        __import__(mod)
        print_ok(mod)
    except Exception as e:
        ALL_ERRORS.append(f'导入失败 {mod}: {e}')
        print_fail(f'{mod}: {e}')

# ============================================================
# 2. Engine 方法检查
# ============================================================
print_header('2. Engine 方法签名检查')

from recall.engine import RecallEngine
import inspect

engine_methods = {
    'add': ['content', 'user_id', 'metadata'],
    'search': ['query', 'user_id', 'top_k'],
    'get': ['memory_id', 'user_id'],
    'get_all': ['user_id'],
    'delete': ['memory_id', 'user_id'],
    'update': ['memory_id', 'content', 'user_id'],
    'clear': ['user_id'],
    'build_context': ['query', 'user_id'],
    'stats': [],
    'get_stats': [],
}

for method, expected_params in engine_methods.items():
    if hasattr(RecallEngine, method):
        sig = inspect.signature(getattr(RecallEngine, method))
        params = [p for p in sig.parameters.keys() if p != 'self']
        print_ok(f'{method}({", ".join(params)})')
    else:
        ALL_ERRORS.append(f'Engine 缺少方法: {method}')
        print_fail(f'{method} 不存在')

# ============================================================
# 3. Server API 路由检查
# ============================================================
print_header('3. Server API 路由检查')

from recall.server import app

routes = [r.path for r in app.routes if hasattr(r, 'path')]
critical_routes = [
    '/health',
    '/v1/memories',
    '/v1/memories/search', 
    '/v1/config/reload',
    '/v1/config',
    '/v1/config/test',
    '/v1/foreshadowing',
    '/v1/context',
    '/v1/stats',
]

for route in critical_routes:
    if route in routes:
        print_ok(route)
    else:
        ALL_ERRORS.append(f'缺少路由: {route}')
        print_fail(f'{route} 不存在')

print(f'\n  总路由数: {len(routes)}')

# ============================================================
# 4. 配置系统检查
# ============================================================
print_header('4. 配置系统检查')

from recall.server import SUPPORTED_CONFIG_KEYS, get_config_file_path, load_api_keys_from_file

print(f'  支持的配置键 ({len(SUPPORTED_CONFIG_KEYS)}):')
for key in sorted(SUPPORTED_CONFIG_KEYS):
    print(f'    - {key}')

config_path = get_config_file_path()
print(f'\n  配置文件路径: {config_path}')
print(f'  配置文件存在: {config_path.exists()}')

# ============================================================
# 5. Embedding 系统检查
# ============================================================
print_header('5. Embedding 系统检查')

from recall.embedding import EmbeddingConfig, create_embedding_backend
from recall.embedding.base import EmbeddingBackendType

# 检查 MODEL_DIMENSIONS
if hasattr(EmbeddingConfig, 'MODEL_DIMENSIONS'):
    dims = EmbeddingConfig.MODEL_DIMENSIONS
    print(f'  MODEL_DIMENSIONS ({len(dims)} 个模型):')
    for model, dim in dims.items():
        print(f'    {model}: {dim}')
else:
    ALL_ERRORS.append('EmbeddingConfig 缺少 MODEL_DIMENSIONS')
    print_fail('MODEL_DIMENSIONS 不存在')

# 测试各种配置
print('\n  配置测试:')
try:
    c = EmbeddingConfig.lightweight()
    assert c.backend == EmbeddingBackendType.NONE
    print_ok('lightweight() 配置正确')
except Exception as e:
    ALL_ERRORS.append(f'lightweight() 失败: {e}')
    print_fail(f'lightweight(): {e}')

try:
    c = EmbeddingConfig.hybrid_openai('sk-test', model='text-embedding-3-large')
    assert c.dimension == 3072, f'expected 3072, got {c.dimension}'
    print_ok(f'hybrid_openai(text-embedding-3-large) dimension={c.dimension}')
except Exception as e:
    ALL_ERRORS.append(f'hybrid_openai() 失败: {e}')
    print_fail(f'hybrid_openai(): {e}')

try:
    c = EmbeddingConfig.hybrid_siliconflow('sf-test')
    assert c.dimension == 1024, f'expected 1024, got {c.dimension}'
    print_ok(f'hybrid_siliconflow() dimension={c.dimension}')
except Exception as e:
    ALL_ERRORS.append(f'hybrid_siliconflow() 失败: {e}')
    print_fail(f'hybrid_siliconflow(): {e}')

# ============================================================
# 6. 功能测试（使用临时目录）
# ============================================================
print_header('6. 功能测试')

with tempfile.TemporaryDirectory() as tmpdir:
    try:
        engine = RecallEngine(data_root=tmpdir, lightweight=True)
        print_ok('引擎初始化')
    except Exception as e:
        ALL_ERRORS.append(f'引擎初始化失败: {e}')
        print_fail(f'引擎初始化: {e}')
        # 无法继续测试
        engine = None
    
    if engine:
        # 6.1 添加记忆
        try:
            r = engine.add('Alice住在北京', user_id='test')
            assert r.success, f'add failed: {r.message}'
            mem_id = r.id
            print_ok(f'add() 返回 id={mem_id[:20]}...')
        except Exception as e:
            ALL_ERRORS.append(f'add() 失败: {e}')
            print_fail(f'add(): {e}')
            mem_id = None
        
        # 6.2 获取记忆
        if mem_id:
            try:
                mem = engine.get(mem_id, user_id='test')
                assert mem is not None, 'get returned None'
                assert 'content' in mem or 'memory' in mem, 'no content field'
                print_ok(f'get() 返回记忆')
            except Exception as e:
                ALL_ERRORS.append(f'get() 失败: {e}')
                print_fail(f'get(): {e}')
        
        # 6.3 搜索
        try:
            results = engine.search('Alice', user_id='test')
            assert isinstance(results, list), f'search returned {type(results)}'
            print_ok(f'search() 返回 {len(results)} 条结果')
        except Exception as e:
            ALL_ERRORS.append(f'search() 失败: {e}')
            print_fail(f'search(): {e}')
        
        # 6.4 获取所有
        try:
            all_mems = engine.get_all(user_id='test')
            assert isinstance(all_mems, list), f'get_all returned {type(all_mems)}'
            print_ok(f'get_all() 返回 {len(all_mems)} 条记忆')
        except Exception as e:
            ALL_ERRORS.append(f'get_all() 失败: {e}')
            print_fail(f'get_all(): {e}')
        
        # 6.5 更新
        if mem_id:
            try:
                success = engine.update(mem_id, '更新后的内容', user_id='test')
                assert success, 'update returned False'
                print_ok('update() 成功')
            except Exception as e:
                ALL_ERRORS.append(f'update() 失败: {e}')
                print_fail(f'update(): {e}')
        
        # 6.6 删除
        if mem_id:
            try:
                success = engine.delete(mem_id, user_id='test')
                assert success, 'delete returned False'
                print_ok('delete() 成功')
            except Exception as e:
                ALL_ERRORS.append(f'delete() 失败: {e}')
                print_fail(f'delete(): {e}')
        
        # 6.7 统计
        try:
            stats = engine.stats()
            assert isinstance(stats, dict), f'stats returned {type(stats)}'
            assert 'version' in stats, 'no version in stats'
            print_ok(f'stats() version={stats.get("version")}')
        except Exception as e:
            ALL_ERRORS.append(f'stats() 失败: {e}')
            print_fail(f'stats(): {e}')

# ============================================================
# 7. 边界条件测试
# ============================================================
print_header('7. 边界条件测试')

with tempfile.TemporaryDirectory() as tmpdir:
    engine = RecallEngine(data_root=tmpdir, lightweight=True)
    
    # 7.1 空字符串
    try:
        r = engine.add('')
        print_ok(f'空字符串: success={r.success}')
    except Exception as e:
        ALL_WARNINGS.append(f'空字符串添加异常: {e}')
        print_warn(f'空字符串: {e}')
    
    # 7.2 空搜索
    try:
        results = engine.search('')
        print_ok(f'空搜索: {len(results)} 条结果')
    except Exception as e:
        ALL_WARNINGS.append(f'空搜索异常: {e}')
        print_warn(f'空搜索: {e}')
    
    # 7.3 不存在的 ID
    try:
        mem = engine.get('non_existent_id')
        assert mem is None, f'expected None, got {mem}'
        print_ok('不存在的ID: 返回 None')
    except Exception as e:
        ALL_ERRORS.append(f'get(不存在ID) 失败: {e}')
        print_fail(f'不存在的ID: {e}')
    
    # 7.4 删除不存在的
    try:
        success = engine.delete('non_existent_id')
        assert success == False, f'expected False, got {success}'
        print_ok('删除不存在: 返回 False')
    except Exception as e:
        ALL_ERRORS.append(f'delete(不存在ID) 失败: {e}')
        print_fail(f'删除不存在: {e}')
    
    # 7.5 特殊字符
    try:
        r = engine.add('测试<script>alert(1)</script>&"\' 特殊')
        assert r.success, f'add failed: {r.message}'
        print_ok('特殊字符: 添加成功')
    except Exception as e:
        ALL_ERRORS.append(f'特殊字符失败: {e}')
        print_fail(f'特殊字符: {e}')
    
    # 7.6 Unicode/Emoji
    try:
        r = engine.add('😀🎉🔥测试emoji')
        assert r.success, f'add failed: {r.message}'
        print_ok('Emoji: 添加成功')
    except Exception as e:
        ALL_ERRORS.append(f'Emoji失败: {e}')
        print_fail(f'Emoji: {e}')
    
    # 7.7 长内容（限制在合理范围，不要太长导致卡住）
    try:
        # 只测试 10KB，不要 100KB
        long_content = 'A' * 10000
        start = time.time()
        r = engine.add(long_content)
        elapsed = time.time() - start
        if elapsed > 5:
            ALL_WARNINGS.append(f'长内容(10KB)耗时 {elapsed:.1f}s，可能有性能问题')
            print_warn(f'长内容(10KB): 耗时 {elapsed:.1f}s')
        else:
            print_ok(f'长内容(10KB): {elapsed:.2f}s')
    except Exception as e:
        ALL_ERRORS.append(f'长内容失败: {e}')
        print_fail(f'长内容: {e}')

# ============================================================
# 8. InvertedIndex 调用检查
# ============================================================
print_header('8. 索引调用检查')

from recall.index import InvertedIndex
import inspect

# 检查 add 方法签名
sig = inspect.signature(InvertedIndex.add)
params = list(sig.parameters.keys())
print(f'  InvertedIndex.add 参数: {params}')

sig_batch = inspect.signature(InvertedIndex.add_batch)
params_batch = list(sig_batch.parameters.keys())
print(f'  InvertedIndex.add_batch 参数: {params_batch}')

# 检查 engine.py 中的调用
import re
engine_path = os.path.join(os.path.dirname(__file__), '..', 'recall', 'engine.py')
with open(engine_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 查找 _inverted_index 的调用
inverted_calls = re.findall(r'self\._inverted_index\.(add\w*)\((.*?)\)', content)
print(f'\n  engine.py 中 _inverted_index 调用:')
for method, args in inverted_calls:
    print(f'    .{method}({args})')
    # 检查是否正确
    if method == 'add' and 'keywords' in args:
        ALL_ERRORS.append('engine.py 中 _inverted_index.add() 调用错误，应使用 add_batch()')
        print_fail('    ^ 应该使用 add_batch()')

# ============================================================
# 9. 汇总报告
# ============================================================
print_header('检查报告')

print(f'  错误: {len(ALL_ERRORS)}')
print(f'  警告: {len(ALL_WARNINGS)}')

if ALL_ERRORS:
    print('\n  ❌ 错误列表:')
    for i, err in enumerate(ALL_ERRORS, 1):
        print(f'    {i}. {err}')

if ALL_WARNINGS:
    print('\n  ⚠️ 警告列表:')
    for i, warn in enumerate(ALL_WARNINGS, 1):
        print(f'    {i}. {warn}')

if not ALL_ERRORS and not ALL_WARNINGS:
    print('\n  ✅ 所有检查通过！')

print()
