#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recall-ai 数据迁移脚本 v1.1
============================

【用途】
将旧版数据结构迁移到新版数据结构：
  旧: data/foreshadowings/foreshadowing_{user_id}.json  →  新: data/{user_id}/default/foreshadowings.json
  旧: data/contexts/{user_id}_contexts.json             →  新: data/{user_id}/default/contexts.json

【使用方法】
直接运行脚本，会显示交互式菜单：
   python3 tools/migrate_data.py

高级用法（命令行参数）：
   python3 tools/migrate_data.py --analyze   # 仅分析
   python3 tools/migrate_data.py --dry-run   # 模拟运行
   python3 tools/migrate_data.py -y          # 自动确认迁移

【特点】
- 完全独立：不依赖项目中的任何模块，仅使用Python标准库
- 安全迁移：只复制数据，不删除原始数据
- 幂等操作：可重复运行，已迁移的数据不会重复迁移
- 交互式菜单：无需记忆命令，按数字选择即可

【用完即删】
迁移完成后，确认数据无误，可直接删除此脚本。

作者: Recall-ai
日期: 2026-01-21
"""

import os
import sys
import json
import shutil
import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


# ============================================================
# 常量定义
# ============================================================

VERSION = "1.1.0"
MIGRATION_MARKER_FILE = ".data_migrated_v3"

# 旧数据路径模式
OLD_FORESHADOWING_DIR = "foreshadowings"
OLD_CONTEXT_DIR = "contexts"
OLD_FORESHADOWING_PREFIX = "foreshadowing_"  # foreshadowing_{user_id}.json
OLD_CONTEXT_SUFFIX = "_contexts.json"         # {user_id}_contexts.json

# 新数据路径模式
NEW_FORESHADOWING_FILE = "foreshadowings.json"
NEW_CONTEXT_FILE = "contexts.json"
DEFAULT_CHARACTER_ID = "default"


# ============================================================
# 辅助函数
# ============================================================

def sanitize_path_component(name: str) -> str:
    """清理路径组件中的非法字符，与项目中的逻辑保持一致"""
    return "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in name)


def format_timestamp(ts: float) -> str:
    """格式化时间戳为可读字符串"""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def load_json_file(filepath: str) -> Optional[Any]:
    """安全加载JSON文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"  [错误] JSON解析失败: {filepath}")
        print(f"         {e}")
        return None
    except Exception as e:
        print(f"  [错误] 读取文件失败: {filepath}")
        print(f"         {e}")
        return None


def save_json_file(filepath: str, data: Any) -> bool:
    """安全保存JSON文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"  [错误] 保存文件失败: {filepath}")
        print(f"         {e}")
        return False


def compare_json_files(file1: str, file2: str) -> bool:
    """比较两个JSON文件内容是否相同"""
    data1 = load_json_file(file1)
    data2 = load_json_file(file2)
    if data1 is None or data2 is None:
        return False
    return json.dumps(data1, sort_keys=True) == json.dumps(data2, sort_keys=True)


# ============================================================
# 数据分析
# ============================================================

class MigrationAnalyzer:
    """分析需要迁移的数据"""
    
    def __init__(self, data_dir: str, verbose: bool = False):
        self.data_dir = data_dir
        self.verbose = verbose
        self.old_fsh_dir = os.path.join(data_dir, OLD_FORESHADOWING_DIR)
        self.old_ctx_dir = os.path.join(data_dir, OLD_CONTEXT_DIR)
        
    def analyze(self) -> Dict[str, Any]:
        """分析数据目录，返回分析结果"""
        result = {
            "data_dir": self.data_dir,
            "exists": os.path.exists(self.data_dir),
            "foreshadowings": self._analyze_foreshadowings(),
            "contexts": self._analyze_contexts(),
            "migration_marker": self._check_migration_marker(),
            "new_structure_exists": self._check_new_structure(),
        }
        
        result["total_files_to_migrate"] = (
            result["foreshadowings"]["count"] + 
            result["contexts"]["count"]
        )
        result["total_size"] = (
            result["foreshadowings"]["total_size"] + 
            result["contexts"]["total_size"]
        )
        
        return result
    
    def _analyze_foreshadowings(self) -> Dict[str, Any]:
        """分析旧伏笔数据"""
        result = {
            "dir_exists": os.path.exists(self.old_fsh_dir),
            "count": 0,
            "files": [],
            "total_size": 0,
            "total_items": 0,
        }
        
        if not result["dir_exists"]:
            return result
        
        for filename in os.listdir(self.old_fsh_dir):
            if filename.startswith(OLD_FORESHADOWING_PREFIX) and filename.endswith('.json'):
                # 解析 user_id
                user_id = filename[len(OLD_FORESHADOWING_PREFIX):-5]  # 去掉前缀和 .json
                filepath = os.path.join(self.old_fsh_dir, filename)
                
                file_info = {
                    "filename": filename,
                    "filepath": filepath,
                    "user_id": user_id,
                    "size": os.path.getsize(filepath),
                    "items": 0,
                    "id_counter": 0,
                }
                
                # 尝试读取文件统计项数
                data = load_json_file(filepath)
                if data:
                    file_info["items"] = len(data.get("foreshadowings", {}))
                    file_info["id_counter"] = data.get("id_counter", 0)
                    result["total_items"] += file_info["items"]
                
                result["files"].append(file_info)
                result["count"] += 1
                result["total_size"] += file_info["size"]
        
        return result
    
    def _analyze_contexts(self) -> Dict[str, Any]:
        """分析旧条件数据"""
        result = {
            "dir_exists": os.path.exists(self.old_ctx_dir),
            "count": 0,
            "files": [],
            "total_size": 0,
            "total_items": 0,
        }
        
        if not result["dir_exists"]:
            return result
        
        for filename in os.listdir(self.old_ctx_dir):
            if filename.endswith(OLD_CONTEXT_SUFFIX):
                # 解析 user_id
                user_id = filename[:-len(OLD_CONTEXT_SUFFIX)]  # 去掉 _contexts.json
                filepath = os.path.join(self.old_ctx_dir, filename)
                
                file_info = {
                    "filename": filename,
                    "filepath": filepath,
                    "user_id": user_id,
                    "size": os.path.getsize(filepath),
                    "items": 0,
                }
                
                # 尝试读取文件统计项数
                data = load_json_file(filepath)
                if data and isinstance(data, list):
                    file_info["items"] = len(data)
                    result["total_items"] += file_info["items"]
                
                result["files"].append(file_info)
                result["count"] += 1
                result["total_size"] += file_info["size"]
        
        return result
    
    def _check_migration_marker(self) -> Dict[str, Any]:
        """检查迁移标记文件"""
        marker_path = os.path.join(self.data_dir, MIGRATION_MARKER_FILE)
        result = {
            "exists": os.path.exists(marker_path),
            "path": marker_path,
            "content": None,
        }
        
        if result["exists"]:
            try:
                with open(marker_path, 'r', encoding='utf-8') as f:
                    result["content"] = f.read()
            except:
                pass
        
        return result
    
    def _check_new_structure(self) -> Dict[str, Any]:
        """检查新结构是否已存在数据"""
        result = {
            "user_dirs": [],
            "has_data": False,
        }
        
        for item in os.listdir(self.data_dir):
            item_path = os.path.join(self.data_dir, item)
            if os.path.isdir(item_path) and item not in [
                OLD_FORESHADOWING_DIR, OLD_CONTEXT_DIR, 
                'L1_consolidated', 'L3_archive', 'foreshadowing_analyzer',
                'memories'
            ] and not item.startswith('.'):
                # 检查是否是新结构的用户目录
                for char_item in os.listdir(item_path):
                    char_path = os.path.join(item_path, char_item)
                    if os.path.isdir(char_path):
                        fsh_file = os.path.join(char_path, NEW_FORESHADOWING_FILE)
                        ctx_file = os.path.join(char_path, NEW_CONTEXT_FILE)
                        if os.path.exists(fsh_file) or os.path.exists(ctx_file):
                            result["user_dirs"].append({
                                "user_id": item,
                                "character_id": char_item,
                                "has_foreshadowings": os.path.exists(fsh_file),
                                "has_contexts": os.path.exists(ctx_file),
                            })
                            result["has_data"] = True
        
        return result
    
    def print_report(self, analysis: Dict[str, Any]):
        """打印分析报告"""
        print("\n" + "=" * 60)
        print("数据迁移分析报告")
        print("=" * 60)
        
        print(f"\n数据目录: {analysis['data_dir']}")
        print(f"目录状态: {'存在' if analysis['exists'] else '不存在'}")
        
        if not analysis['exists']:
            print("\n[警告] 数据目录不存在，无需迁移")
            return
        
        # 伏笔数据
        fsh = analysis['foreshadowings']
        print(f"\n【旧伏笔数据】")
        print(f"  目录: {self.old_fsh_dir}")
        print(f"  状态: {'存在' if fsh['dir_exists'] else '不存在'}")
        if fsh['dir_exists']:
            print(f"  文件数量: {fsh['count']}")
            print(f"  总大小: {format_size(fsh['total_size'])}")
            print(f"  伏笔总数: {fsh['total_items']}")
            if self.verbose and fsh['files']:
                print("  文件列表:")
                for f in fsh['files']:
                    print(f"    - {f['filename']} (user_id={f['user_id']}, "
                          f"items={f['items']}, size={format_size(f['size'])})")
        
        # 条件数据
        ctx = analysis['contexts']
        print(f"\n【旧条件数据】")
        print(f"  目录: {self.old_ctx_dir}")
        print(f"  状态: {'存在' if ctx['dir_exists'] else '不存在'}")
        if ctx['dir_exists']:
            print(f"  文件数量: {ctx['count']}")
            print(f"  总大小: {format_size(ctx['total_size'])}")
            print(f"  条件总数: {ctx['total_items']}")
            if self.verbose and ctx['files']:
                print("  文件列表:")
                for f in ctx['files']:
                    print(f"    - {f['filename']} (user_id={f['user_id']}, "
                          f"items={f['items']}, size={format_size(f['size'])})")
        
        # 迁移标记
        marker = analysis['migration_marker']
        print(f"\n【迁移标记】")
        print(f"  标记文件: {marker['path']}")
        print(f"  状态: {'已存在' if marker['exists'] else '不存在'}")
        if marker['exists'] and marker['content']:
            print(f"  内容预览: {marker['content'][:100]}...")
        
        # 新结构
        new_struct = analysis['new_structure_exists']
        print(f"\n【新数据结构】")
        print(f"  是否已有数据: {'是' if new_struct['has_data'] else '否'}")
        if new_struct['has_data'] and self.verbose:
            print("  已存在的用户/角色目录:")
            for ud in new_struct['user_dirs'][:10]:  # 最多显示10个
                print(f"    - {ud['user_id']}/{ud['character_id']} "
                      f"(伏笔={'是' if ud['has_foreshadowings'] else '否'}, "
                      f"条件={'是' if ud['has_contexts'] else '否'})")
            if len(new_struct['user_dirs']) > 10:
                print(f"    ... 还有 {len(new_struct['user_dirs']) - 10} 个目录")
        
        # 总结
        print(f"\n【迁移总结】")
        print(f"  待迁移文件数: {analysis['total_files_to_migrate']}")
        print(f"  待迁移数据量: {format_size(analysis['total_size'])}")
        
        if analysis['total_files_to_migrate'] == 0:
            print("\n✓ 没有需要迁移的旧数据")
        else:
            print(f"\n→ 将迁移 {fsh['count']} 个伏笔文件 + {ctx['count']} 个条件文件")
            print(f"→ 目标位置: data/{{user_id}}/{DEFAULT_CHARACTER_ID}/")
        
        print("\n" + "=" * 60)


# ============================================================
# 数据迁移
# ============================================================

class DataMigrator:
    """执行数据迁移"""
    
    def __init__(self, data_dir: str, dry_run: bool = False, verbose: bool = False):
        self.data_dir = data_dir
        self.dry_run = dry_run
        self.verbose = verbose
        self.old_fsh_dir = os.path.join(data_dir, OLD_FORESHADOWING_DIR)
        self.old_ctx_dir = os.path.join(data_dir, OLD_CONTEXT_DIR)
        
        # 迁移统计
        self.stats = {
            "foreshadowings_migrated": 0,
            "contexts_migrated": 0,
            "foreshadowings_skipped": 0,
            "contexts_skipped": 0,
            "foreshadowings_failed": 0,
            "contexts_failed": 0,
            "total_items_migrated": 0,
        }
        
    def migrate(self) -> Tuple[bool, Dict[str, Any]]:
        """执行迁移，返回 (是否成功, 统计信息)"""
        print("\n" + "=" * 60)
        print("开始数据迁移" + (" (预演模式)" if self.dry_run else ""))
        print("=" * 60)
        
        start_time = time.time()
        
        # 1. 迁移伏笔数据
        print("\n【步骤 1/3】迁移伏笔数据...")
        if os.path.exists(self.old_fsh_dir):
            self._migrate_foreshadowings()
        else:
            print("  [跳过] 旧伏笔目录不存在")
        
        # 2. 迁移条件数据
        print("\n【步骤 2/3】迁移条件数据...")
        if os.path.exists(self.old_ctx_dir):
            self._migrate_contexts()
        else:
            print("  [跳过] 旧条件目录不存在")
        
        # 3. 写入迁移标记
        print("\n【步骤 3/3】写入迁移标记...")
        if not self.dry_run:
            self._write_migration_marker()
        else:
            print("  [预演] 跳过写入迁移标记")
        
        # 计算耗时
        elapsed = time.time() - start_time
        self.stats["elapsed_seconds"] = elapsed
        
        # 打印结果
        self._print_results()
        
        # 判断是否成功
        success = (self.stats["foreshadowings_failed"] == 0 and 
                   self.stats["contexts_failed"] == 0)
        
        return success, self.stats
    
    def _migrate_foreshadowings(self):
        """迁移伏笔数据"""
        for filename in os.listdir(self.old_fsh_dir):
            if not (filename.startswith(OLD_FORESHADOWING_PREFIX) and filename.endswith('.json')):
                continue
            
            # 解析 user_id
            user_id = filename[len(OLD_FORESHADOWING_PREFIX):-5]
            safe_user_id = sanitize_path_component(user_id)
            
            src_path = os.path.join(self.old_fsh_dir, filename)
            dst_dir = os.path.join(self.data_dir, safe_user_id, DEFAULT_CHARACTER_ID)
            dst_path = os.path.join(dst_dir, NEW_FORESHADOWING_FILE)
            
            if self.verbose:
                print(f"  处理: {filename}")
                print(f"    源路径: {src_path}")
                print(f"    目标路径: {dst_path}")
            
            # 检查目标是否已存在
            if os.path.exists(dst_path):
                print(f"  [跳过] {filename} → 目标已存在: {dst_path}")
                self.stats["foreshadowings_skipped"] += 1
                continue
            
            # 验证源文件可读
            src_data = load_json_file(src_path)
            if src_data is None:
                print(f"  [失败] {filename} → 无法读取源文件")
                self.stats["foreshadowings_failed"] += 1
                continue
            
            # 统计项数
            item_count = len(src_data.get("foreshadowings", {}))
            
            if self.dry_run:
                print(f"  [预演] {filename} → {safe_user_id}/{DEFAULT_CHARACTER_ID}/ "
                      f"({item_count} 个伏笔)")
                self.stats["foreshadowings_migrated"] += 1
                self.stats["total_items_migrated"] += item_count
            else:
                # 执行迁移（复制文件）
                try:
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    
                    # 验证迁移结果
                    if compare_json_files(src_path, dst_path):
                        print(f"  [成功] {filename} → {safe_user_id}/{DEFAULT_CHARACTER_ID}/ "
                              f"({item_count} 个伏笔)")
                        self.stats["foreshadowings_migrated"] += 1
                        self.stats["total_items_migrated"] += item_count
                    else:
                        print(f"  [失败] {filename} → 数据校验失败")
                        # 删除可能损坏的目标文件
                        if os.path.exists(dst_path):
                            os.remove(dst_path)
                        self.stats["foreshadowings_failed"] += 1
                        
                except Exception as e:
                    print(f"  [失败] {filename} → {e}")
                    self.stats["foreshadowings_failed"] += 1
    
    def _migrate_contexts(self):
        """迁移条件数据"""
        for filename in os.listdir(self.old_ctx_dir):
            if not filename.endswith(OLD_CONTEXT_SUFFIX):
                continue
            
            # 解析 user_id
            user_id = filename[:-len(OLD_CONTEXT_SUFFIX)]
            safe_user_id = sanitize_path_component(user_id)
            
            src_path = os.path.join(self.old_ctx_dir, filename)
            dst_dir = os.path.join(self.data_dir, safe_user_id, DEFAULT_CHARACTER_ID)
            dst_path = os.path.join(dst_dir, NEW_CONTEXT_FILE)
            
            if self.verbose:
                print(f"  处理: {filename}")
                print(f"    源路径: {src_path}")
                print(f"    目标路径: {dst_path}")
            
            # 检查目标是否已存在
            if os.path.exists(dst_path):
                print(f"  [跳过] {filename} → 目标已存在: {dst_path}")
                self.stats["contexts_skipped"] += 1
                continue
            
            # 验证源文件可读
            src_data = load_json_file(src_path)
            if src_data is None:
                print(f"  [失败] {filename} → 无法读取源文件")
                self.stats["contexts_failed"] += 1
                continue
            
            # 统计项数
            item_count = len(src_data) if isinstance(src_data, list) else 0
            
            if self.dry_run:
                print(f"  [预演] {filename} → {safe_user_id}/{DEFAULT_CHARACTER_ID}/ "
                      f"({item_count} 个条件)")
                self.stats["contexts_migrated"] += 1
                self.stats["total_items_migrated"] += item_count
            else:
                # 执行迁移（复制文件）
                try:
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    
                    # 验证迁移结果
                    if compare_json_files(src_path, dst_path):
                        print(f"  [成功] {filename} → {safe_user_id}/{DEFAULT_CHARACTER_ID}/ "
                              f"({item_count} 个条件)")
                        self.stats["contexts_migrated"] += 1
                        self.stats["total_items_migrated"] += item_count
                    else:
                        print(f"  [失败] {filename} → 数据校验失败")
                        # 删除可能损坏的目标文件
                        if os.path.exists(dst_path):
                            os.remove(dst_path)
                        self.stats["contexts_failed"] += 1
                        
                except Exception as e:
                    print(f"  [失败] {filename} → {e}")
                    self.stats["contexts_failed"] += 1
    
    def _write_migration_marker(self):
        """写入迁移标记文件"""
        marker_path = os.path.join(self.data_dir, MIGRATION_MARKER_FILE)
        
        content = f"""migrated_at: {time.time()}
migration_date: {datetime.now().isoformat()}
migration_script_version: {VERSION}
foreshadowings_migrated: {self.stats['foreshadowings_migrated']}
contexts_migrated: {self.stats['contexts_migrated']}
total_items_migrated: {self.stats['total_items_migrated']}
"""
        
        try:
            with open(marker_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  [成功] 写入迁移标记: {marker_path}")
        except Exception as e:
            print(f"  [警告] 写入迁移标记失败: {e}")
    
    def _print_results(self):
        """打印迁移结果"""
        print("\n" + "=" * 60)
        print("迁移结果" + (" (预演模式)" if self.dry_run else ""))
        print("=" * 60)
        
        print(f"\n【伏笔数据】")
        print(f"  成功迁移: {self.stats['foreshadowings_migrated']}")
        print(f"  已跳过: {self.stats['foreshadowings_skipped']}")
        print(f"  失败: {self.stats['foreshadowings_failed']}")
        
        print(f"\n【条件数据】")
        print(f"  成功迁移: {self.stats['contexts_migrated']}")
        print(f"  已跳过: {self.stats['contexts_skipped']}")
        print(f"  失败: {self.stats['contexts_failed']}")
        
        print(f"\n【总计】")
        print(f"  迁移项目数: {self.stats['total_items_migrated']}")
        print(f"  耗时: {self.stats['elapsed_seconds']:.2f} 秒")
        
        total_migrated = self.stats['foreshadowings_migrated'] + self.stats['contexts_migrated']
        total_failed = self.stats['foreshadowings_failed'] + self.stats['contexts_failed']
        
        if total_failed > 0:
            print(f"\n⚠ 迁移完成，但有 {total_failed} 个文件失败")
        elif total_migrated > 0:
            print(f"\n✓ 迁移成功完成！")
        else:
            print(f"\n✓ 没有需要迁移的数据")
        
        if not self.dry_run and total_migrated > 0:
            print(f"\n【后续操作】")
            print(f"  1. 确认迁移后的数据正常工作")
            print(f"  2. 可选：删除旧数据目录")
            print(f"     - {self.old_fsh_dir}")
            print(f"     - {self.old_ctx_dir}")
            print(f"  3. 用完此脚本后可直接删除: tools/migrate_data.py")
        
        print("\n" + "=" * 60)


# ============================================================
# 数据验证
# ============================================================

class MigrationVerifier:
    """验证迁移结果"""
    
    def __init__(self, data_dir: str, verbose: bool = False):
        self.data_dir = data_dir
        self.verbose = verbose
        self.old_fsh_dir = os.path.join(data_dir, OLD_FORESHADOWING_DIR)
        self.old_ctx_dir = os.path.join(data_dir, OLD_CONTEXT_DIR)
    
    def verify(self) -> Tuple[bool, Dict[str, Any]]:
        """验证迁移结果，返回 (是否全部正确, 验证报告)"""
        print("\n" + "=" * 60)
        print("验证迁移结果")
        print("=" * 60)
        
        report = {
            "foreshadowings": [],
            "contexts": [],
            "all_passed": True,
        }
        
        # 验证伏笔
        print("\n【验证伏笔数据】")
        if os.path.exists(self.old_fsh_dir):
            for filename in os.listdir(self.old_fsh_dir):
                if not (filename.startswith(OLD_FORESHADOWING_PREFIX) and filename.endswith('.json')):
                    continue
                
                user_id = filename[len(OLD_FORESHADOWING_PREFIX):-5]
                safe_user_id = sanitize_path_component(user_id)
                
                src_path = os.path.join(self.old_fsh_dir, filename)
                dst_path = os.path.join(self.data_dir, safe_user_id, DEFAULT_CHARACTER_ID, NEW_FORESHADOWING_FILE)
                
                result = self._verify_file(src_path, dst_path, filename)
                report["foreshadowings"].append(result)
                if not result["passed"]:
                    report["all_passed"] = False
        else:
            print("  [跳过] 旧伏笔目录不存在")
        
        # 验证条件
        print("\n【验证条件数据】")
        if os.path.exists(self.old_ctx_dir):
            for filename in os.listdir(self.old_ctx_dir):
                if not filename.endswith(OLD_CONTEXT_SUFFIX):
                    continue
                
                user_id = filename[:-len(OLD_CONTEXT_SUFFIX)]
                safe_user_id = sanitize_path_component(user_id)
                
                src_path = os.path.join(self.old_ctx_dir, filename)
                dst_path = os.path.join(self.data_dir, safe_user_id, DEFAULT_CHARACTER_ID, NEW_CONTEXT_FILE)
                
                result = self._verify_file(src_path, dst_path, filename)
                report["contexts"].append(result)
                if not result["passed"]:
                    report["all_passed"] = False
        else:
            print("  [跳过] 旧条件目录不存在")
        
        # 总结
        print("\n" + "-" * 40)
        fsh_passed = sum(1 for r in report["foreshadowings"] if r["passed"])
        ctx_passed = sum(1 for r in report["contexts"] if r["passed"])
        
        print(f"伏笔: {fsh_passed}/{len(report['foreshadowings'])} 验证通过")
        print(f"条件: {ctx_passed}/{len(report['contexts'])} 验证通过")
        
        if report["all_passed"]:
            print("\n✓ 所有数据验证通过！")
        else:
            print("\n⚠ 部分数据验证失败，请检查上述错误")
        
        print("\n" + "=" * 60)
        
        return report["all_passed"], report
    
    def _verify_file(self, src_path: str, dst_path: str, display_name: str) -> Dict[str, Any]:
        """验证单个文件"""
        result = {
            "filename": display_name,
            "src_path": src_path,
            "dst_path": dst_path,
            "passed": False,
            "message": "",
        }
        
        # 检查目标文件存在
        if not os.path.exists(dst_path):
            result["message"] = "目标文件不存在"
            print(f"  [失败] {display_name}: 目标文件不存在")
            print(f"         期望: {dst_path}")
            return result
        
        # 比较内容
        if compare_json_files(src_path, dst_path):
            result["passed"] = True
            result["message"] = "数据一致"
            print(f"  [通过] {display_name}")
        else:
            result["message"] = "数据不一致"
            print(f"  [失败] {display_name}: 数据不一致")
        
        return result


# ============================================================
# 主程序
# ============================================================

def find_data_dir() -> Optional[str]:
    """自动查找数据目录"""
    # 常见位置
    candidates = [
        # 相对于脚本位置
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'recall_data', 'data'),
        # 相对于当前工作目录
        os.path.join(os.getcwd(), 'recall_data', 'data'),
        # 直接在当前目录
        os.path.join(os.getcwd(), 'data'),
    ]
    
    for candidate in candidates:
        candidate = os.path.normpath(candidate)
        if os.path.exists(candidate):
            return candidate
    
    return None


def main():
    parser = argparse.ArgumentParser(
        description='Recall-ai 数据迁移脚本 - 将旧数据结构迁移到新的 {user_id}/{character_id}/ 结构',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/migrate_data.py                    # 自动检测数据目录并迁移
  python tools/migrate_data.py --dry-run          # 预演模式，不实际执行
  python tools/migrate_data.py --analyze          # 仅分析，不迁移
  python tools/migrate_data.py --verify           # 验证迁移结果
  python tools/migrate_data.py -d /path/to/data   # 指定数据目录
        """
    )
    
    parser.add_argument('-d', '--data-dir', 
                        help='数据目录路径（默认自动检测）')
    parser.add_argument('--dry-run', action='store_true',
                        help='预演模式：显示将要执行的操作，但不实际执行')
    parser.add_argument('--analyze', action='store_true',
                        help='仅分析数据，不执行迁移')
    parser.add_argument('--verify', action='store_true',
                        help='验证迁移结果')
    parser.add_argument('-y', '--yes', action='store_true',
                        help='自动确认，不提示')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='显示详细信息')
    parser.add_argument('--no-menu', action='store_true',
                        help='禁用交互式菜单（直接执行迁移）')
    parser.add_argument('--version', action='version', 
                        version=f'%(prog)s {VERSION}')
    
    args = parser.parse_args()
    
    # 确定数据目录
    data_dir = args.data_dir
    if not data_dir:
        data_dir = find_data_dir()
        if data_dir:
            print(f"自动检测到数据目录: {data_dir}")
        else:
            print("错误: 无法自动检测数据目录")
            print("请使用 --data-dir 参数指定数据目录")
            sys.exit(1)
    
    data_dir = os.path.normpath(data_dir)
    
    if not os.path.exists(data_dir):
        print(f"错误: 数据目录不存在: {data_dir}")
        sys.exit(1)
    
    # 判断是否使用交互式菜单
    # 如果有任何操作参数，则直接执行；否则显示菜单
    has_action = args.analyze or args.verify or args.dry_run or args.yes or args.no_menu
    
    if not has_action:
        # 交互式菜单模式
        return interactive_menu(data_dir, args.verbose)
    
    # 命令行模式（原逻辑）
    return command_line_mode(data_dir, args)


def interactive_menu(data_dir: str, verbose: bool = False):
    """交互式菜单模式"""
    while True:
        print("\n")
        print("=" * 60)
        print("       Recall-ai 数据迁移工具 v" + VERSION)
        print("=" * 60)
        print(f"\n数据目录: {data_dir}\n")
        print("请选择操作：\n")
        print("  [1] 📊 分析数据     - 查看需要迁移的数据")
        print("  [2] 🔍 模拟迁移     - 预览迁移过程（不实际执行）")
        print("  [3] 🚀 执行迁移     - 开始数据迁移")
        print("  [4] ✅ 验证结果     - 检查迁移是否成功")
        print("  [5] 🧹 清理旧目录   - 删除已迁移的旧数据（谨慎）")
        print("  [0] ❌ 退出")
        print()
        
        try:
            choice = input("请输入数字 [0-5]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            return 0
        
        if choice == '0':
            print("\n再见！")
            return 0
        
        elif choice == '1':
            # 分析数据
            print("\n" + "-" * 60)
            analyzer = MigrationAnalyzer(data_dir, verbose=verbose)
            analysis = analyzer.analyze()
            analyzer.print_report(analysis)
            input("\n按回车键继续...")
        
        elif choice == '2':
            # 模拟迁移
            print("\n" + "-" * 60)
            analyzer = MigrationAnalyzer(data_dir, verbose=verbose)
            analysis = analyzer.analyze()
            analyzer.print_report(analysis)
            
            if analysis['total_files_to_migrate'] == 0:
                print("\n没有需要迁移的数据。")
            else:
                print("\n开始模拟迁移...\n")
                migrator = DataMigrator(data_dir, dry_run=True, verbose=verbose)
                migrator.migrate()
            input("\n按回车键继续...")
        
        elif choice == '3':
            # 执行迁移
            print("\n" + "-" * 60)
            analyzer = MigrationAnalyzer(data_dir, verbose=verbose)
            analysis = analyzer.analyze()
            analyzer.print_report(analysis)
            
            if analysis['total_files_to_migrate'] == 0:
                print("\n没有需要迁移的数据。")
                input("\n按回车键继续...")
                continue
            
            print("\n" + "!" * 60)
            print("  ⚠️  即将执行数据迁移")
            print("!" * 60)
            print(f"\n将迁移 {analysis['total_files_to_migrate']} 个文件")
            print("原始数据不会被删除，仅复制到新位置")
            
            try:
                confirm = input("\n确认执行迁移？(输入 yes 继续): ")
                if confirm.lower() != 'yes':
                    print("已取消迁移")
                    input("\n按回车键继续...")
                    continue
            except KeyboardInterrupt:
                print("\n已取消迁移")
                input("\n按回车键继续...")
                continue
            
            # 执行迁移
            migrator = DataMigrator(data_dir, dry_run=False, verbose=verbose)
            success, stats = migrator.migrate()
            
            if success:
                print("\n自动执行迁移验证...")
                verifier = MigrationVerifier(data_dir, verbose=verbose)
                all_passed, _ = verifier.verify()
                if all_passed:
                    print("\n✅ 迁移完成并验证通过！")
                    print("\n下一步：选择 [5] 清理旧目录，或手动删除：")
                    print(f"  rm -rf {os.path.join(data_dir, OLD_FORESHADOWING_DIR)}")
                    print(f"  rm -rf {os.path.join(data_dir, OLD_CONTEXT_DIR)}")
                else:
                    print("\n⚠️ 迁移完成，但验证发现问题，请检查")
            
            input("\n按回车键继续...")
        
        elif choice == '4':
            # 验证结果
            print("\n" + "-" * 60)
            verifier = MigrationVerifier(data_dir, verbose=verbose)
            all_passed, _ = verifier.verify()
            input("\n按回车键继续...")
        
        elif choice == '5':
            # 清理旧目录
            print("\n" + "-" * 60)
            old_fsh_dir = os.path.join(data_dir, OLD_FORESHADOWING_DIR)
            old_ctx_dir = os.path.join(data_dir, OLD_CONTEXT_DIR)
            
            dirs_to_clean = []
            if os.path.exists(old_fsh_dir):
                dirs_to_clean.append(old_fsh_dir)
            if os.path.exists(old_ctx_dir):
                dirs_to_clean.append(old_ctx_dir)
            
            if not dirs_to_clean:
                print("\n没有需要清理的旧目录。")
                input("\n按回车键继续...")
                continue
            
            print("\n将删除以下目录：")
            for d in dirs_to_clean:
                # 统计文件数
                file_count = sum(1 for _ in Path(d).rglob('*') if _.is_file())
                print(f"  - {d} ({file_count} 个文件)")
            
            print("\n" + "!" * 60)
            print("  ⚠️  警告：此操作不可恢复！")
            print("!" * 60)
            
            try:
                confirm = input("\n确认删除？(输入 DELETE 继续): ")
                if confirm != 'DELETE':
                    print("已取消删除")
                    input("\n按回车键继续...")
                    continue
            except KeyboardInterrupt:
                print("\n已取消删除")
                input("\n按回车键继续...")
                continue
            
            # 执行删除
            for d in dirs_to_clean:
                try:
                    shutil.rmtree(d)
                    print(f"  ✅ 已删除: {d}")
                except Exception as e:
                    print(f"  ❌ 删除失败: {d}")
                    print(f"     错误: {e}")
            
            print("\n清理完成！")
            input("\n按回车键继续...")
        
        else:
            print("\n无效选项，请输入 0-5 之间的数字")


def command_line_mode(data_dir: str, args):
    """命令行模式（原逻辑）"""
    # 执行分析
    analyzer = MigrationAnalyzer(data_dir, verbose=args.verbose)
    analysis = analyzer.analyze()
    analyzer.print_report(analysis)
    
    if args.analyze:
        # 仅分析模式
        sys.exit(0)
    
    if args.verify:
        # 验证模式
        verifier = MigrationVerifier(data_dir, verbose=args.verbose)
        all_passed, _ = verifier.verify()
        sys.exit(0 if all_passed else 1)
    
    # 检查是否需要迁移
    if analysis['total_files_to_migrate'] == 0:
        print("\n没有需要迁移的数据，退出。")
        sys.exit(0)
    
    # 确认迁移
    if not args.dry_run and not args.yes:
        print("\n" + "!" * 60)
        print("即将执行数据迁移")
        print("!" * 60)
        print(f"\n将迁移 {analysis['total_files_to_migrate']} 个文件")
        print("原始数据不会被删除，仅复制到新位置")
        
        try:
            confirm = input("\n确认执行迁移？(输入 yes 继续): ")
            if confirm.lower() != 'yes':
                print("已取消迁移")
                sys.exit(0)
        except KeyboardInterrupt:
            print("\n已取消迁移")
            sys.exit(0)
    
    # 执行迁移
    migrator = DataMigrator(data_dir, dry_run=args.dry_run, verbose=args.verbose)
    success, stats = migrator.migrate()
    
    # 如果不是预演模式，执行验证
    if not args.dry_run and success:
        print("\n自动执行迁移验证...")
        verifier = MigrationVerifier(data_dir, verbose=args.verbose)
        all_passed, _ = verifier.verify()
        if not all_passed:
            print("\n⚠ 警告: 迁移验证发现问题，请检查")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
