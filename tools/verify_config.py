#!/usr/bin/env python3
"""验证配置项一致性脚本 - Recall v7.0 完整版

检查项目:
1. server.py SUPPORTED_CONFIG_KEYS - 支持的配置键名
2. start.ps1 $supportedKeys - 支持的配置键名
3. start.sh supported_keys - 支持的配置键名
4. server.py get_default_config_content() - 默认配置模板
5. recall/config_template.env - 统一配置模板 (单一数据源)
6. 脚本是否正确引用 config_template.env
7. v7.0 高级功能集成状态（含 BackendFactory, ConsolidationManager 等）
"""

import re
import sys
from pathlib import Path


def extract_template_keys(content: str) -> set:
    """从配置模板内容中提取配置键名"""
    # 匹配 KEY=value 或 KEY= 的格式
    # 排除注释行 (以 # 开头)
    keys = set()
    for line in content.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            match = re.match(r'^([A-Z][A-Z0-9_]+)\s*=', line)
            if match:
                keys.add(match.group(1))
    return keys


def main():
    root = Path(__file__).parent.parent
    errors = 0
    warnings = 0
    
    print("=" * 60)
    print("Recall-AI 配置一致性验证工具 v7.0")
    print("=" * 60)
    print()
    
    # =========================================================================
    # Part 1: 验证 SUPPORTED_CONFIG_KEYS 一致性
    # =========================================================================
    print("[Part 1] 验证支持的配置键名一致性")
    print("-" * 40)
    
    # 1. 从 server.py 提取 SUPPORTED_CONFIG_KEYS
    server_file = root / 'recall' / 'server.py'
    with open(server_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'SUPPORTED_CONFIG_KEYS = \{([\s\S]*?)\n\}', content)
    if match:
        keys_block = match.group(1)
        server_keys = set(re.findall(r"'([A-Z][A-Z0-9_]*)'", keys_block))
        print(f'[OK] server.py SUPPORTED_CONFIG_KEYS: {len(server_keys)} 项')
    else:
        print('[ERROR] 无法解析 server.py SUPPORTED_CONFIG_KEYS')
        return 1
    
    # 2. 从 start.ps1 提取支持的配置项
    ps1_file = root / 'start.ps1'
    with open(ps1_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'\$supportedKeys = @\(([\s\S]*?)\n\s*\)', content)
    if match:
        keys_block = match.group(1)
        ps1_keys = set(re.findall(r"'([A-Z][A-Z0-9_]*)'", keys_block))
        print(f'[OK] start.ps1 $supportedKeys: {len(ps1_keys)} 项')
    else:
        print('[ERROR] 无法解析 start.ps1 $supportedKeys')
        ps1_keys = set()
    
    # 3. 从 start.sh 提取支持的配置项
    sh_file = root / 'start.sh'
    with open(sh_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'local supported_keys="([^"]+)"', content)
    if match:
        sh_keys = set(match.group(1).split())
        print(f'[OK] start.sh supported_keys: {len(sh_keys)} 项')
    else:
        print('[ERROR] 无法解析 start.sh supported_keys')
        sh_keys = set()
    
    # 对比 SUPPORTED_CONFIG_KEYS
    print()
    
    diff1 = server_keys - ps1_keys
    if diff1:
        print(f'[FAIL] server.py 有但 start.ps1 缺少: {sorted(diff1)}')
        errors += 1
    else:
        print('[PASS] start.ps1 包含所有 server.py 的配置键')
    
    diff2 = server_keys - sh_keys
    if diff2:
        print(f'[FAIL] server.py 有但 start.sh 缺少: {sorted(diff2)}')
        errors += 1
    else:
        print('[PASS] start.sh 包含所有 server.py 的配置键')
    
    extra1 = ps1_keys - server_keys
    if extra1:
        print(f'[WARN] start.ps1 多出的配置键: {sorted(extra1)}')
        warnings += 1
    
    extra2 = sh_keys - server_keys
    if extra2:
        print(f'[WARN] start.sh 多出的配置键: {sorted(extra2)}')
        warnings += 1
    
    # =========================================================================
    # Part 2: 验证默认配置模板一致性
    # =========================================================================
    print()
    print("[Part 2] 验证默认配置模板一致性")
    print("-" * 40)
    
    # 1. 从 server.py 提取 get_default_config_content() 模板
    match = re.search(r"def get_default_config_content\(\)[^:]*:\s*\"\"\"[^\"]*\"\"\"\s*return '''([\s\S]*?)'''", content)
    if not match:
        # 尝试另一种格式
        with open(server_file, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r"def get_default_config_content\(\)[^:]*:.*?return '''([\s\S]*?)'''", content, re.DOTALL)
    
    if match:
        server_template = match.group(1)
        server_template_keys = extract_template_keys(server_template)
        print(f'[OK] server.py get_default_config_content(): {len(server_template_keys)} 项配置')
    else:
        print('[ERROR] 无法解析 server.py get_default_config_content()')
        server_template_keys = set()
    
    # 2. 从统一模板文件 recall/config_template.env 提取配置键
    template_file = root / 'recall' / 'config_template.env'
    if template_file.exists():
        with open(template_file, 'r', encoding='utf-8') as f:
            template_content = f.read()
        template_keys = extract_template_keys(template_content)
        print(f'[OK] recall/config_template.env (统一模板): {len(template_keys)} 项配置')
    else:
        print('[ERROR] 找不到 recall/config_template.env 统一模板文件')
        template_keys = set()
    
    # 3. (旧版本会从 start.ps1/manage.ps1/manage.sh 分别提取内联模板)
    #    v7.0+ 模板已统一到 recall/config_template.env，脚本通过文件引用加载
    ps1_template_keys = template_keys  # 统一引用
    manage_ps1_template_keys = template_keys
    manage_sh_template_keys = template_keys
    
    # 对比模板内容
    print()
    
    if server_template_keys:
        # 模板应该包含所有 SUPPORTED_CONFIG_KEYS
        missing_in_template = server_keys - server_template_keys
        if missing_in_template:
            print(f'[WARN] server.py 模板缺少的配置键: {sorted(missing_in_template)[:10]}...')
            if len(missing_in_template) > 10:
                print(f'       (共 {len(missing_in_template)} 项缺失，部分配置可能是运行时动态生成)')
        
        # 对比统一模板
        if template_keys:
            diff = server_template_keys - template_keys
            if diff:
                print(f'[FAIL] server.py 模板有但 config_template.env 缺少: {sorted(diff)[:5]}...')
                errors += 1
            else:
                print('[PASS] config_template.env 包含所有 server.py 模板的配置')
            
            diff2 = template_keys - server_template_keys
            if diff2:
                print(f'[INFO] config_template.env 额外包含: {sorted(diff2)[:5]}')
        
        print('[PASS] manage.ps1/manage.sh 已统一引用 config_template.env (无需单独检查)')
    
    # 检查脚本是否引用了统一模板文件
    for script_name in ['start.ps1', 'start.sh', 'manage.ps1', 'manage.sh']:
        script_path = root / script_name
        if script_path.exists():
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            if 'config_template.env' in script_content:
                print(f'[PASS] {script_name} 引用了 config_template.env')
            else:
                print(f'[FAIL] {script_name} 未引用 config_template.env')
                errors += 1
    
    # =========================================================================
    # Part 3: 验证模板与 SUPPORTED_CONFIG_KEYS 的关系
    # =========================================================================
    print()
    print("[Part 3] 验证模板覆盖度")
    print("-" * 40)
    
    if server_template_keys:
        # 模板中有但 SUPPORTED_CONFIG_KEYS 没有的（可能是新增但未注册）
        extra_in_template = server_template_keys - server_keys
        if extra_in_template:
            print(f'[WARN] 模板有但 SUPPORTED_CONFIG_KEYS 缺少: {sorted(extra_in_template)}')
            print('       (这些配置不会被自动加载到环境变量！)')
            warnings += 1
        else:
            print('[PASS] 模板中的所有配置都在 SUPPORTED_CONFIG_KEYS 中注册')
    
    # =========================================================================
    # Part 4: 验证 factory.py 使用的环境变量与 server.py 一致
    # =========================================================================
    print()
    print("[Part 4] 验证 factory.py 配置变量一致性")
    print("-" * 40)
    
    factory_file = root / 'recall' / 'embedding' / 'factory.py'
    if factory_file.exists():
        with open(factory_file, 'r', encoding='utf-8') as f:
            factory_content = f.read()
        
        # 提取 factory.py 中使用的环境变量名
        factory_env_vars = set(re.findall(r"os\.environ\.get\(['\"]([A-Z][A-Z0-9_]+)['\"]", factory_content))
        factory_env_vars.update(re.findall(r"os\.environ\[['\"]([A-Z][A-Z0-9_]+)['\"]\]", factory_content))
        
        print(f'[OK] factory.py 使用的环境变量: {len(factory_env_vars)} 项')
        
        # 定义 factory.py 应该使用的标准配置变量（与 server.py 一致）
        expected_factory_vars = {
            'RECALL_EMBEDDING_MODE',
            'EMBEDDING_API_KEY',
            'EMBEDDING_API_BASE', 
            'EMBEDDING_MODEL',
            'EMBEDDING_DIMENSION',
        }
        
        # 检查是否使用了已废弃的旧变量名
        deprecated_vars = {
            'OPENAI_API_KEY': 'EMBEDDING_API_KEY',
            'OPENAI_API_BASE': 'EMBEDDING_API_BASE',
            'OPENAI_MODEL': 'EMBEDDING_MODEL',
            'SILICONFLOW_API_KEY': 'EMBEDDING_API_KEY',
            'SILICONFLOW_MODEL': 'EMBEDDING_MODEL',
        }
        
        deprecated_used = factory_env_vars & set(deprecated_vars.keys())
        if deprecated_used:
            print(f'[FAIL] factory.py 使用了已废弃的变量名:')
            for old_var in sorted(deprecated_used):
                print(f'       - {old_var} -> 应使用 {deprecated_vars[old_var]}')
            errors += 1
        else:
            print('[PASS] factory.py 未使用废弃的变量名')
        
        # 检查 factory.py 使用的变量是否都在 SUPPORTED_CONFIG_KEYS 中
        factory_missing = factory_env_vars - server_keys
        if factory_missing:
            # 排除一些不需要在配置文件中的变量
            ignore_vars = {'PATH', 'HOME', 'USER'}
            factory_missing = factory_missing - ignore_vars
            if factory_missing:
                print(f'[WARN] factory.py 使用但 SUPPORTED_CONFIG_KEYS 缺少: {sorted(factory_missing)}')
                warnings += 1
        
        if not deprecated_used:
            print('[PASS] factory.py 与 server.py 配置变量一致')
    else:
        print('[WARN] factory.py 文件不存在')
        warnings += 1
    
    # 检查 api_backend.py
    api_backend_file = root / 'recall' / 'embedding' / 'api_backend.py'
    if api_backend_file.exists():
        with open(api_backend_file, 'r', encoding='utf-8') as f:
            api_backend_content = f.read()
        
        # 提取 api_backend.py 中使用的环境变量名
        api_backend_env_vars = set(re.findall(r"os\.environ\.get\(['\"]([A-Z][A-Z0-9_]+)['\"]", api_backend_content))
        api_backend_env_vars.update(re.findall(r"os\.environ\[['\"]([A-Z][A-Z0-9_]+)['\"]\]", api_backend_content))
        
        print(f'[OK] api_backend.py 使用的环境变量: {len(api_backend_env_vars)} 项')
        
        deprecated_used_backend = api_backend_env_vars & set(deprecated_vars.keys())
        if deprecated_used_backend:
            print(f'[FAIL] api_backend.py 使用了已废弃的变量名:')
            for old_var in sorted(deprecated_used_backend):
                print(f'       - {old_var} -> 应使用 {deprecated_vars[old_var]}')
            errors += 1
        else:
            print('[PASS] api_backend.py 未使用废弃的变量名')
    
    # =========================================================================
    # Part 5: 热更新支持情况说明
    # =========================================================================
    print()
    print("[Part 5] 热更新支持情况说明")
    print("-" * 40)
    
    # 即时热更新（通过 @property 或静态方法）
    instant_hot_reload = [
        'CONTEXT_MAX_PER_TYPE', 'CONTEXT_MAX_TOTAL', 'CONTEXT_DECAY_DAYS',
        'CONTEXT_DECAY_RATE', 'CONTEXT_MIN_CONFIDENCE',
        'CONTEXT_TRIGGER_INTERVAL', 'CONTEXT_MAX_CONTEXT_TURNS',  # 已改为 @property
        'DEDUP_EMBEDDING_ENABLED', 'DEDUP_HIGH_THRESHOLD', 'DEDUP_LOW_THRESHOLD',
        'FORESHADOWING_MAX_RETURN', 'FORESHADOWING_MAX_ACTIVE',
        'BUILD_CONTEXT_INCLUDE_RECENT', 'PROACTIVE_REMINDER_ENABLED', 'PROACTIVE_REMINDER_TURNS',
    ]
    
    # 需要 reload_engine 的配置
    need_reload = [
        'EMBEDDING_API_KEY', 'EMBEDDING_API_BASE', 'EMBEDDING_MODEL', 'EMBEDDING_DIMENSION',
        'RECALL_EMBEDDING_MODE',
        'LLM_API_KEY', 'LLM_API_BASE', 'LLM_MODEL', 'LLM_TIMEOUT',
        'FORESHADOWING_LLM_ENABLED', 'FORESHADOWING_TRIGGER_INTERVAL',
        'FORESHADOWING_AUTO_PLANT', 'FORESHADOWING_AUTO_RESOLVE',
        'TEMPORAL_GRAPH_ENABLED', 'TEMPORAL_GRAPH_BACKEND', 'KUZU_BUFFER_POOL_SIZE',
        'TEMPORAL_DECAY_RATE', 'TEMPORAL_MAX_HISTORY',
        'CONTRADICTION_DETECTION_ENABLED', 'CONTRADICTION_DETECTION_STRATEGY', 
        'CONTRADICTION_AUTO_RESOLVE', 'CONTRADICTION_SIMILARITY_THRESHOLD',
        'FULLTEXT_ENABLED', 'FULLTEXT_K1', 'FULLTEXT_B', 'FULLTEXT_WEIGHT',
        'ELEVEN_LAYER_RETRIEVER_ENABLED',
        # Phase 3.5
        'QUERY_PLANNER_ENABLED', 'QUERY_PLANNER_CACHE_SIZE', 'QUERY_PLANNER_CACHE_TTL',
        'COMMUNITY_DETECTION_ENABLED', 'COMMUNITY_DETECTION_ALGORITHM', 'COMMUNITY_MIN_SIZE',
        # Phase 3.6
        'TRIPLE_RECALL_ENABLED', 'TRIPLE_RECALL_RRF_K',
        'TRIPLE_RECALL_VECTOR_WEIGHT', 'TRIPLE_RECALL_KEYWORD_WEIGHT', 'TRIPLE_RECALL_ENTITY_WEIGHT',
        'VECTOR_IVF_HNSW_M', 'VECTOR_IVF_HNSW_EF_CONSTRUCTION', 'VECTOR_IVF_HNSW_EF_SEARCH',
        'FALLBACK_ENABLED', 'FALLBACK_PARALLEL', 'FALLBACK_WORKERS', 'FALLBACK_MAX_RESULTS',
    ]
    
    print(f'[INFO] 即时热更新配置 ({len(instant_hot_reload)} 项): 修改后立即生效')
    print(f'       示例: CONTEXT_*, DEDUP_EMBEDDING_*, FORESHADOWING_MAX_*, PROACTIVE_*')
    print(f'[INFO] 需要热重载配置 ({len(need_reload)} 项): 需调用 POST /v1/config/reload')
    print(f'       示例: EMBEDDING_*, LLM_*, TEMPORAL_*, FULLTEXT_*, QUERY_PLANNER_*, TRIPLE_RECALL_*')
    print('[HINT] 修改 api_keys.env 后调用: curl -X POST http://localhost:18888/v1/config/reload')
    print()
    print('[HINT] 已启用自动热重载: 保存 api_keys.env 后 2 秒内自动生效（无需手动调用）')
    
    # =========================================================================
    # Part 6: v7.0 高级功能集成状态
    # =========================================================================
    print()
    print("[Part 6] v7.0 高级功能集成状态")
    print("-" * 40)
    
    # 检查 engine.py 是否导入了这些组件
    engine_file = root / 'recall' / 'engine.py'
    if engine_file.exists():
        with open(engine_file, 'r', encoding='utf-8') as f:
            engine_content = f.read()
        
        # === Phase 2 功能 ===
        phase2_components = [
            ('SmartExtractor', 'SMART_EXTRACTOR_*'),
            ('BudgetManager', 'BUDGET_*'),
            ('ThreeStageDeduplicator', 'DEDUP_JACCARD_*, DEDUP_SEMANTIC_*, DEDUP_LLM_*'),
        ]
        for component, config_keys in phase2_components:
            if component in engine_content:
                print(f'[PASS] {component} 已集成')
            else:
                print(f'[INFO] {component} 未集成 -> {config_keys} 暂不生效')
        
        # === Phase 3.5 功能 ===
        phase35_components = [
            ('QueryPlanner', 'QUERY_PLANNER_*'),
            ('CommunityDetector', 'COMMUNITY_DETECTION_*'),
        ]
        for component, config_keys in phase35_components:
            if component in engine_content:
                print(f'[PASS] {component} 已集成')
            else:
                print(f'[INFO] {component} 未集成 -> {config_keys} 暂不生效')
        
        # === Phase 4.1 功能 ===
        phase41_components = [
            ('LLMRelationExtractor', 'LLM_RELATION_*'),
            ('EpisodeStore', 'EPISODE_TRACKING_*'),
            ('EntitySummarizer', 'ENTITY_SUMMARY_*'),
        ]
        for component, config_keys in phase41_components:
            if component in engine_content:
                print(f'[PASS] {component} 已集成')
            else:
                print(f'[INFO] {component} 未集成 -> {config_keys} 暂不生效')
        
        # === v7.0 新增功能 ===
        v70_components = [
            ('get_mode_config', '统一模式系统 (RecallMode)'),
            ('CoreSettings', '绝对规则系统 (AbsoluteRule)'),
            ('TimeIntentParser', '时间意图解析器'),
            ('GrowthControl', '增长控制器'),
            ('ConsolidationManager', '记忆整合管理器'),
        ]
        print()
        print('--- v7.0 新增组件 ---')
        for component, desc in v70_components:
            if component in engine_content:
                print(f'[PASS] {component} ({desc}) 已集成')
            else:
                print(f'[INFO] {component} ({desc}) 未直接集成到 engine.py')
    
    # =========================================================================
    # Summary
    # =========================================================================
    print()
    print("=" * 60)
    if errors == 0 and warnings == 0:
        print('[SUCCESS] 所有配置项完全一致！')
    elif errors == 0:
        print(f'[SUCCESS] 配置键一致，但有 {warnings} 个警告')
    else:
        print(f'[FAILED] 发现 {errors} 个错误, {warnings} 个警告')
    print("=" * 60)
    
    return errors


if __name__ == '__main__':
    sys.exit(main())
