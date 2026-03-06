#!/usr/bin/env python
"""最终配置同步检查工具"""

import re
import os
import sys

# 切换到项目根目录
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 目标配置值 (v7.0)
TARGET_CONFIGS = {
    'RECALL_MODE': 'universal',
    'FORESHADOWING_LLM_ENABLED': 'true',
    'ELEVEN_LAYER_RETRIEVER_ENABLED': 'true',
    'RETRIEVAL_L10_CROSS_ENCODER_ENABLED': 'true',
    'RETRIEVAL_L11_LLM_ENABLED': 'true',
    'QUERY_PLANNER_ENABLED': 'true',
    'COMMUNITY_DETECTION_ENABLED': 'false',
    'LLM_RELATION_MODE': 'llm',
    'ENTITY_SUMMARY_ENABLED': 'true',
}

# v7.0 性能优化配置
V70_CONFIGS = {
    'EMBEDDING_REUSE_ENABLED': 'true',
    'UNIFIED_ANALYZER_ENABLED': 'true',
    'UNIFIED_ANALYSIS_MAX_TOKENS': '4000',
    'TURN_API_ENABLED': 'true',
    'SMART_EXTRACTOR_MODE': 'RULES',
}

def check_template_files():
    """检查配置模板文件"""
    template_files = [
        'recall/server.py',
        'recall/config_template.env',
    ]
    
    print('\n📋 1. 配置模板文件检查 ({0}个目标配置)'.format(len(TARGET_CONFIGS) + len(V70_CONFIGS)))
    print('-' * 50)
    
    all_ok = True
    for filepath in template_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        issues = []
        for key, expected_value in {**TARGET_CONFIGS, **V70_CONFIGS}.items():
            # 匹配行首的配置定义 (排除中文说明中的文本)
            pattern = rf'^{key}=(\S+)\s*$'
            matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
            if matches:
                for val in matches:
                    val_clean = val.strip('"\'').lower()
                    if val_clean != expected_value.lower():
                        issues.append(f'{key}={val_clean} (应为 {expected_value})')
        
        if issues:
            print(f'❌ {filepath}:')
            for issue in issues:
                print(f'   - {issue}')
            all_ok = False
        else:
            print(f'✅ {filepath}')
    
    return all_ok


def check_python_defaults():
    """检查 Python 代码中的 os.environ.get 默认值"""
    print('\n📋 2. Python os.environ.get 默认值检查')
    print('-' * 50)
    
    python_files = [
        ('recall/engine.py', ['ELEVEN_LAYER_RETRIEVER_ENABLED', 'QUERY_PLANNER_ENABLED', 
                              'LLM_RELATION_MODE', 'ENTITY_SUMMARY_ENABLED']),
        ('recall/server.py', ['FORESHADOWING_LLM_ENABLED', 'LLM_RELATION_MODE']),
        ('recall/retrieval/config.py', ['RETRIEVAL_L10_CROSS_ENCODER_ENABLED', 'RETRIEVAL_L11_LLM_ENABLED']),
    ]
    
    all_ok = True
    for filepath, keys_to_check in python_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        issues = []
        for key in keys_to_check:
            expected_value = TARGET_CONFIGS[key]
            
            # 匹配 os.environ.get('KEY', 'value') 或 os.getenv('KEY', 'value')
            pattern = rf"os\.(?:environ\.get|getenv)\s*\(\s*['\"]({key})['\"],\s*['\"](\w+)['\"]"
            matches = re.findall(pattern, content)
            for _, val in matches:
                if val.lower() != expected_value.lower():
                    issues.append(f"{key} 默认值 '{val}' (应为 '{expected_value}')")
            
            # 检查 get_bool 模式 (用于 retrieval/config.py)
            if key in ['RETRIEVAL_L10_CROSS_ENCODER_ENABLED', 'RETRIEVAL_L11_LLM_ENABLED']:
                bool_pattern = rf"get_bool\s*\(\s*['\"]({key})['\"],\s*(True|False)"
                bool_matches = re.findall(bool_pattern, content)
                for _, val in bool_matches:
                    expected_bool = 'True' if expected_value == 'true' else 'False'
                    if val != expected_bool:
                        issues.append(f"{key} get_bool 默认值 {val} (应为 {expected_bool})")
        
        if issues:
            print(f'❌ {filepath}:')
            for issue in issues:
                print(f'   - {issue}')
            all_ok = False
        else:
            print(f'✅ {filepath}')
    
    return all_ok


def check_v70_configs():
    """检查 v7.0 配置同步"""
    print('\n📋 2.5 v7.0 性能优化配置同步检查')
    print('-' * 50)
    
    # 需要检查的文件位置（模板已统一到 recall/config_template.env）
    check_locations = {
        'server.py SUPPORTED_CONFIG_KEYS': 'recall/server.py',
        'server.py 默认配置模板': 'recall/server.py',
        'config_template.env 统一模板': 'recall/config_template.env',
        'start.ps1 supportedKeys': 'start.ps1',
        'start.sh supported_keys': 'start.sh',
    }
    
    all_ok = True
    for name, filepath in check_locations.items():
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        found = []
        missing = []
        for key in V70_CONFIGS.keys():
            if key in content:
                found.append(key)
            else:
                missing.append(key)
        
        if len(found) == len(V70_CONFIGS):
            print(f'✅ {name}: {len(found)}/{len(V70_CONFIGS)} 配置项')
        else:
            print(f'❌ {name}: {len(found)}/{len(V70_CONFIGS)} 配置项')
            print(f'   缺少: {missing}')
            all_ok = False
    
    # 检查配置是否被注释掉（关键检查！）
    print()
    print('   v7.0 配置注释检查（确保配置未被 # 注释）:')
    
    v42_active_configs = ['EMBEDDING_REUSE_ENABLED', 'UNIFIED_ANALYZER_ENABLED', 'TURN_API_ENABLED']
    template_files = ['recall/server.py', 'recall/config_template.env']
    
    for filepath in template_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        commented_configs = []
        active_configs = []
        
        for key in v42_active_configs:
            # 检查是否有被注释的配置行 (行首有 #)
            commented_pattern = rf'^#\s*{key}=.+$'
            if re.search(commented_pattern, content, re.MULTILINE):
                commented_configs.append(key)
            
            # 检查是否有未被注释的配置行
            active_pattern = rf'^{key}=.+$'
            if re.search(active_pattern, content, re.MULTILINE):
                active_configs.append(key)
        
        if commented_configs:
            print(f'   ❌ {filepath}: 以下配置被注释: {commented_configs}')
            all_ok = False
        elif len(active_configs) == len(v42_active_configs):
            print(f'   ✅ {filepath}: 所有 v7.0 配置已启用')
        else:
            missing = set(v42_active_configs) - set(active_configs)
            if missing:
                print(f'   ⚠️  {filepath}: 缺少配置: {list(missing)}')
    
    # 检查 Python 代码中的默认值
    print()
    print('   v7.0 Python 默认值检查:')
    
    v42_python_checks = [
        ('recall/memory_ops.py', 'EMBEDDING_REUSE_ENABLED', 'true'),
        ('recall/engine.py', 'UNIFIED_ANALYZER_ENABLED', 'true'),
        ('recall/processor/unified_analyzer.py', 'UNIFIED_ANALYSIS_MAX_TOKENS', '4000'),
        ('recall/server.py', 'TURN_API_ENABLED', 'true'),
    ]
    
    for filepath, key, expected in v42_python_checks:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 匹配 os.environ.get('KEY', 'default')
            pattern = rf"os\.environ\.get\s*\(\s*['\"]({key})['\"],\s*['\"]([^'\"]+)['\"]"
            matches = re.findall(pattern, content)
            
            if matches:
                # 过滤掉仅用于日志显示的默认值（如 'not set', 'unknown' 等）
                real_matches = [(k, v) for k, v in matches if v.lower() not in ('not set', 'unknown', 'n/a')]
                log_matches = [(k, v) for k, v in matches if v.lower() in ('not set', 'unknown', 'n/a')]
                
                if real_matches:
                    for _, val in real_matches:
                        if val.lower() == expected.lower():
                            print(f'   ✅ {filepath}: {key}={val}')
                        else:
                            print(f'   ❌ {filepath}: {key}={val} (应为 {expected})')
                            all_ok = False
                elif log_matches:
                    print(f'   ⚠️  {filepath}: {key} 仅在日志中引用，无实际默认值')
                else:
                    print(f'   ⚠️  {filepath}: {key} 未找到默认值定义')
            else:
                # 尝试匹配 int(os.environ.get(...)) 模式
                int_pattern = rf"int\s*\(\s*os\.environ\.get\s*\(\s*['\"]({key})['\"],\s*['\"]([^'\"]+)['\"]"
                int_matches = re.findall(int_pattern, content)
                if int_matches:
                    for _, val in int_matches:
                        if val == expected:
                            print(f'   ✅ {filepath}: {key}={val}')
                        else:
                            print(f'   ❌ {filepath}: {key}={val} (应为 {expected})')
                            all_ok = False
                else:
                    print(f'   ⚠️  {filepath}: {key} 未找到默认值定义')
        except FileNotFoundError:
            print(f'   ❌ {filepath}: 文件不存在')
            all_ok = False
    
    return all_ok


def check_script_parity():
    """检查 Windows/Linux 脚本一致性"""
    print('\n📋 3. Windows/Linux 脚本一致性检查')
    print('-' * 50)
    
    def extract_env_configs(filepath):
        """只提取环境配置变量 (排除脚本局部变量)"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 匹配典型的配置变量名 (全大写,带下划线)
        # 排除 bash 特有的变量如 RED=, YELLOW=, SCRIPT_DIR= 等
        exclude_patterns = [
            'RED=', 'GREEN=', 'YELLOW=', 'BLUE=', 'WHITE=', 'NC=', 'CYAN=', 'MAGENTA=',
            'SCRIPT_DIR=', 'DATA_PATH=', 'PORT=', 'DEFAULT_PORT=', 'HOST=',
        ]
        
        pattern = r'^([A-Z][A-Z0-9_]+)=(true|false|llm|rules|hybrid|[0-9.]+|auto|ms-marco|[a-z0-9._/-]+)$'
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        
        configs = {}
        for key, val in matches:
            # 排除脚本变量
            if any(key + '=' in excl for excl in exclude_patterns):
                continue
            # 只保留真正的配置变量 (至少有一个下划线且全大写)
            if '_' in key and key == key.upper():
                configs[key] = val.lower()
        
        return configs
    
    script_pairs = [
        ('start.ps1', 'start.sh'),
        ('manage.ps1', 'manage.sh'),
    ]
    
    all_ok = True
    for win, linux in script_pairs:
        win_configs = extract_env_configs(win)
        linux_configs = extract_env_configs(linux)
        
        # 比较配置键
        win_keys = set(win_configs.keys())
        linux_keys = set(linux_configs.keys())
        
        if win_keys == linux_keys:
            # 检查值是否一致
            value_diffs = []
            for key in win_keys:
                if win_configs[key] != linux_configs[key]:
                    value_diffs.append(f'{key}: {win_configs[key]} vs {linux_configs[key]}')
            
            if value_diffs:
                print(f'⚠️  {win} 与 {linux} 配置值不一致:')
                for diff in value_diffs[:5]:
                    print(f'   - {diff}')
                all_ok = False
            else:
                print(f'✅ {win} ({len(win_configs)} 项) == {linux} ({len(linux_configs)} 项)')
        else:
            print(f'⚠️  {win} ({len(win_configs)} 项) != {linux} ({len(linux_configs)} 项)')
            only_win = win_keys - linux_keys
            only_linux = linux_keys - win_keys
            if only_win:
                print(f'   仅在 {win}: {list(only_win)[:5]}...')
            if only_linux:
                print(f'   仅在 {linux}: {list(only_linux)[:5]}...')
            all_ok = False
    
    return all_ok


def check_hot_reload():
    """检查热更新机制"""
    print('\n📋 4. 热更新机制检查')
    print('-' * 50)
    
    with open('recall/server.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查 ConfigFileWatcher 类
    if 'class ConfigFileWatcher' in content:
        print('✅ ConfigFileWatcher 类存在')
    else:
        print('❌ ConfigFileWatcher 类缺失')
    
    # 检查 reload_engine 函数
    if 'def reload_engine' in content:
        print('✅ reload_engine 函数存在')
    else:
        print('❌ reload_engine 函数缺失')
    
    # 检查监控的文件
    if 'api_keys.env' in content:
        print('✅ api_keys.env 监控配置存在')
    else:
        print('⚠️  api_keys.env 监控配置可能缺失')


def main():
    print('=' * 70)
    print('配置同步最终验证报告 (v7.0)')
    print('=' * 70)
    
    t1 = check_template_files()
    t2 = check_python_defaults()
    t2_5 = check_v70_configs()  # v7.0
    t3 = check_script_parity()
    check_hot_reload()
    
    print('\n' + '=' * 70)
    if t1 and t2 and t2_5 and t3:
        print('✅ 所有配置已同步!')
    else:
        print('❌ 发现配置不一致，请检查上方详情')
    print('=' * 70)


if __name__ == '__main__':
    main()
