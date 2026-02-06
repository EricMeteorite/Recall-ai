#!/usr/bin/env python3
"""验证配置项一致性脚本 - Recall v4.2 完整版

检查项目:
1. server.py SUPPORTED_CONFIG_KEYS - 支持的配置键名
2. start.ps1 $supportedKeys - 支持的配置键名
3. start.sh supported_keys - 支持的配置键名
4. server.py get_default_config_content() - 默认配置模板
5. start.ps1 $defaultConfig - 默认配置模板
6. manage.ps1 $defaultConfig - 默认配置模板
7. manage.sh 默认配置模板
8. Phase 2 高级功能集成状态
9. Phase 3.5 QueryPlanner & CommunityDetector 集成状态
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
    print("Recall-AI 配置一致性验证工具 v4.2")
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
    
    # 2. 从 start.ps1 提取 $defaultConfig 模板
    with open(ps1_file, 'r', encoding='utf-8') as f:
        ps1_content = f.read()
    
    match = re.search(r"\$defaultConfig = @'([\s\S]*?)'@", ps1_content)
    if match:
        ps1_template = match.group(1)
        ps1_template_keys = extract_template_keys(ps1_template)
        print(f'[OK] start.ps1 $defaultConfig: {len(ps1_template_keys)} 项配置')
    else:
        print('[WARN] 无法解析 start.ps1 $defaultConfig (可能未定义)')
        ps1_template_keys = set()
    
    # 3. 从 manage.ps1 提取 $defaultConfig 模板
    manage_ps1_file = root / 'manage.ps1'
    if manage_ps1_file.exists():
        with open(manage_ps1_file, 'r', encoding='utf-8') as f:
            manage_ps1_content = f.read()
        
        match = re.search(r"\$defaultConfig = @'([\s\S]*?)'@", manage_ps1_content)
        if match:
            manage_ps1_template = match.group(1)
            manage_ps1_template_keys = extract_template_keys(manage_ps1_template)
            print(f'[OK] manage.ps1 $defaultConfig: {len(manage_ps1_template_keys)} 项配置')
        else:
            print('[WARN] 无法解析 manage.ps1 $defaultConfig')
            manage_ps1_template_keys = set()
    else:
        manage_ps1_template_keys = set()
    
    # 4. 从 manage.sh 提取默认配置模板
    manage_sh_file = root / 'manage.sh'
    if manage_sh_file.exists():
        with open(manage_sh_file, 'r', encoding='utf-8') as f:
            manage_sh_content = f.read()
        
        # Bash heredoc 格式: cat > file << 'EOF' ... EOF
        match = re.search(r"cat\s*>\s*[^\n]+<<\s*'?EOF'?([\s\S]*?)EOF", manage_sh_content)
        if match:
            manage_sh_template = match.group(1)
            manage_sh_template_keys = extract_template_keys(manage_sh_template)
            print(f'[OK] manage.sh 默认模板: {len(manage_sh_template_keys)} 项配置')
        else:
            print('[WARN] 无法解析 manage.sh 默认模板')
            manage_sh_template_keys = set()
    else:
        manage_sh_template_keys = set()
    
    # 对比模板内容
    print()
    
    if server_template_keys:
        # 模板应该包含所有 SUPPORTED_CONFIG_KEYS
        missing_in_template = server_keys - server_template_keys
        if missing_in_template:
            print(f'[WARN] server.py 模板缺少的配置键: {sorted(missing_in_template)[:10]}...')
            if len(missing_in_template) > 10:
                print(f'       (共 {len(missing_in_template)} 项缺失，部分配置可能是运行时动态生成)')
        
        # 对比 start.ps1 模板
        if ps1_template_keys:
            diff = server_template_keys - ps1_template_keys
            if diff:
                print(f'[FAIL] server.py 模板有但 start.ps1 模板缺少: {sorted(diff)[:5]}...')
                errors += 1
            else:
                print('[PASS] start.ps1 模板包含所有 server.py 模板的配置')
        
        # 对比 manage.ps1 模板
        if manage_ps1_template_keys:
            diff = server_template_keys - manage_ps1_template_keys
            if diff:
                print(f'[FAIL] server.py 模板有但 manage.ps1 模板缺少: {sorted(diff)[:5]}...')
                errors += 1
            else:
                print('[PASS] manage.ps1 模板包含所有 server.py 模板的配置')
        
        # 对比 manage.sh 模板
        if manage_sh_template_keys:
            diff = server_template_keys - manage_sh_template_keys
            if diff:
                print(f'[FAIL] server.py 模板有但 manage.sh 模板缺少: {sorted(diff)[:5]}...')
                errors += 1
            else:
                print('[PASS] manage.sh 模板包含所有 server.py 模板的配置')
    
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
    # Part 6: Phase 2/3.5/4.1 高级功能集成状态
    # =========================================================================
    print()
    print("[Part 6] Phase 2/3.5/4.1 高级功能集成状态")
    print("-" * 40)
    
    # 检查 engine.py 是否导入了这些组件
    engine_file = root / 'recall' / 'engine.py'
    if engine_file.exists():
        with open(engine_file, 'r', encoding='utf-8') as f:
            engine_content = f.read()
        
        # === Phase 2 功能 ===
        # SmartExtractor 集成状态
        if 'SmartExtractor' in engine_content:
            print('[PASS] SmartExtractor 已集成到 engine.py')
        else:
            print('[INFO] SmartExtractor 未集成 (Phase 2 可选功能)')
            print('       -> 配置项 SMART_EXTRACTOR_* 在 engine.py 中暂不生效')
        
        # BudgetManager 集成状态
        if 'BudgetManager' in engine_content:
            print('[PASS] BudgetManager 已集成到 engine.py')
        else:
            print('[INFO] BudgetManager 未集成 (Phase 2 可选功能)')
            print('       -> 配置项 BUDGET_* 在 engine.py 中暂不生效')
        
        # ThreeStageDeduplicator 集成状态
        if 'ThreeStageDeduplicator' in engine_content:
            print('[PASS] ThreeStageDeduplicator 已集成到 engine.py')
        else:
            print('[INFO] ThreeStageDeduplicator 未集成 (Phase 2 可选功能)')
            print('       -> 配置项 DEDUP_JACCARD_*, DEDUP_SEMANTIC_*, DEDUP_LLM_* 在 engine.py 中暂不生效')
        
        # === Phase 3.5 功能 ===
        # QueryPlanner 集成状态
        if 'QueryPlanner' in engine_content:
            print('[PASS] QueryPlanner 已集成到 engine.py')
        else:
            print('[INFO] QueryPlanner 未集成 (Phase 3.5 可选功能)')
            print('       -> 配置项 QUERY_PLANNER_* 在 engine.py 中暂不生效')
        
        # CommunityDetector 集成状态
        if 'CommunityDetector' in engine_content:
            print('[PASS] CommunityDetector 已集成到 engine.py')
        else:
            print('[INFO] CommunityDetector 未集成 (Phase 3.5 可选功能)')
            print('       -> 配置项 COMMUNITY_DETECTION_* 在 engine.py 中暂不生效')
        
        # === Phase 4.1 功能 ===
        # LLMRelationExtractor 集成状态
        if 'LLMRelationExtractor' in engine_content:
            print('[PASS] LLMRelationExtractor 已集成到 engine.py')
        else:
            print('[INFO] LLMRelationExtractor 未集成 (Phase 4.1 可选功能)')
            print('       -> 配置项 LLM_RELATION_* 在 engine.py 中暂不生效')
        
        # EpisodeStore 集成状态
        if 'EpisodeStore' in engine_content:
            print('[PASS] EpisodeStore 已集成到 engine.py')
        else:
            print('[INFO] EpisodeStore 未集成 (Phase 4.1 可选功能)')
            print('       -> 配置项 EPISODE_TRACKING_* 在 engine.py 中暂不生效')
        
        # EntitySummarizer 集成状态
        if 'EntitySummarizer' in engine_content:
            print('[PASS] EntitySummarizer 已集成到 engine.py')
        else:
            print('[INFO] EntitySummarizer 未集成 (Phase 4.1 可选功能)')
            print('       -> 配置项 ENTITY_SUMMARY_* 在 engine.py 中暂不生效')
        
        print()
        print('[NOTE] 高级功能资源消耗说明:')
        print('       Phase 2:')
        print('         - SmartExtractor: RULES 模式零 LLM 成本，ADAPTIVE/LLM 模式按需调用')
        print('         - BudgetManager: 仅在配置了 BUDGET_DAILY_LIMIT > 0 时启用')
        print('         - ThreeStageDeduplicator: DEDUP_LLM_ENABLED=false 时不调用 LLM')
        print('       Phase 3.5:')
        print('         - QueryPlanner: 本地缓存优化，零 API 成本')
        print('         - CommunityDetector: 本地图算法，零 API 成本')
        print('       Phase 4.1:')
        print('         - LLMRelationExtractor: RULES 模式零 LLM 成本，ADAPTIVE/LLM 模式按需调用')
        print('         - EpisodeStore: 本地 JSONL 存储，零 API 成本')
        print('         - EntitySummarizer: 仅在 ENTITY_SUMMARY_ENABLED=true 时调用 LLM')
    
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
