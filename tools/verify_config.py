#!/usr/bin/env python3
"""验证配置项一致性脚本 - Phase 2"""

import re
import sys
from pathlib import Path

def main():
    root = Path(__file__).parent.parent
    
    # 1. 从 server.py 提取 SUPPORTED_CONFIG_KEYS
    server_file = root / 'recall' / 'server.py'
    with open(server_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'SUPPORTED_CONFIG_KEYS = \{([\s\S]*?)\n\}', content)
    if match:
        keys_block = match.group(1)
        server_keys = set(re.findall(r"'([A-Z][A-Z0-9_]*)'", keys_block))
        print(f'[OK] server.py keys: {len(server_keys)}')
    else:
        print('[ERROR] Cannot parse server.py')
        return 1
    
    # 2. 从 start.ps1 提取支持的配置项
    ps1_file = root / 'start.ps1'
    with open(ps1_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'\$supportedKeys = @\(([\s\S]*?)\n\s*\)', content)
    if match:
        keys_block = match.group(1)
        ps1_keys = set(re.findall(r"'([A-Z][A-Z0-9_]*)'", keys_block))
        print(f'[OK] start.ps1 keys: {len(ps1_keys)}')
    else:
        print('[ERROR] Cannot parse start.ps1')
        ps1_keys = set()
    
    # 3. 从 start.sh 提取支持的配置项
    sh_file = root / 'start.sh'
    with open(sh_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.search(r'local supported_keys="([^"]+)"', content)
    if match:
        sh_keys = set(match.group(1).split())
        print(f'[OK] start.sh keys: {len(sh_keys)}')
    else:
        print('[ERROR] Cannot parse start.sh')
        sh_keys = set()
    
    # 4. 对比结果
    print()
    print('=== Comparison Results ===')
    
    errors = 0
    
    # server.py 有但 start.ps1 没有
    diff1 = server_keys - ps1_keys
    if diff1:
        print(f'[FAIL] server.py has but start.ps1 missing: {sorted(diff1)}')
        errors += 1
    else:
        print('[PASS] start.ps1 contains all server.py keys')
    
    # server.py 有但 start.sh 没有
    diff2 = server_keys - sh_keys
    if diff2:
        print(f'[FAIL] server.py has but start.sh missing: {sorted(diff2)}')
        errors += 1
    else:
        print('[PASS] start.sh contains all server.py keys')
    
    # start.ps1 多出的
    extra1 = ps1_keys - server_keys
    if extra1:
        print(f'[WARN] start.ps1 has extra keys: {sorted(extra1)}')
    
    # start.sh 多出的
    extra2 = sh_keys - server_keys
    if extra2:
        print(f'[WARN] start.sh has extra keys: {sorted(extra2)}')
    
    if errors == 0:
        print()
        print('[SUCCESS] All configuration keys are consistent!')
    
    return errors

if __name__ == '__main__':
    sys.exit(main())
