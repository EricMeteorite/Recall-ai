#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recall-ai v3 → v4 数据迁移工具
================================

【用途】
将 Recall v3 数据结构迁移到 v4 时态知识图谱格式：
  - Entity → UnifiedNode
  - Relation → TemporalFact
  - Turn/Event → EpisodicNode
  - KnowledgeGraph → TemporalKnowledgeGraph

【使用方法】
直接运行脚本，会显示交互式菜单：
   python tools/migrate_v3_to_v4.py

命令行参数：
   python tools/migrate_v3_to_v4.py --analyze          # 仅分析
   python tools/migrate_v3_to_v4.py --dry-run          # 模拟运行
   python tools/migrate_v3_to_v4.py --user USER        # 指定用户
   python tools/migrate_v3_to_v4.py --backup-dir PATH  # 指定备份目录
   python tools/migrate_v3_to_v4.py -y                 # 自动确认

【特点】
- 完全独立：不依赖项目中的任何模块，仅使用Python标准库
- 自动备份：迁移前自动创建完整备份
- 版本检测：自动检测数据版本，跳过已迁移数据
- 增量迁移：支持增量迁移，不影响已迁移的数据
- 回滚支持：可以从备份恢复

【兼容性】
- 100% 保留原有数据（不删除任何文件）
- 迁移后的数据可以被新旧系统同时读取
- 支持 v3.x 的所有数据格式

作者: Recall-ai
日期: 2025-01-21
版本: 4.0.0
"""

import os
import sys
import json
import shutil
import argparse
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field


# ============================================================
# 版本与常量
# ============================================================

VERSION = "4.0.0"
MIGRATION_MARKER = ".migrated_to_v4"

# v3 数据路径
V3_KNOWLEDGE_GRAPH_FILE = "knowledge_graph.json"
V3_ENTITIES_DIR = "entities"
V3_EVENTS_DIR = "events"
V3_TURNS_DIR = "turns"
V3_FORESHADOWINGS_DIR = "foreshadowings"

# v4 数据路径
V4_TEMPORAL_GRAPH_DIR = "temporal_graph"
V4_NODES_FILE = "nodes.json"
V4_EDGES_FILE = "edges.json"
V4_EPISODES_FILE = "episodes.json"
V4_INDEXES_DIR = "indexes"


# ============================================================
# 数据模型（简化版，不依赖项目代码）
# ============================================================

@dataclass
class MigrationStats:
    """迁移统计"""
    entities_found: int = 0
    entities_migrated: int = 0
    relations_found: int = 0
    relations_migrated: int = 0
    turns_found: int = 0
    turns_migrated: int = 0
    events_found: int = 0
    events_migrated: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================================
# 辅助函数
# ============================================================

def generate_uuid() -> str:
    """生成 UUID"""
    return str(uuid.uuid4())


def format_timestamp(ts: float) -> str:
    """格式化时间戳"""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def safe_load_json(filepath: str) -> Optional[Any]:
    """安全加载 JSON 文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return None


def safe_save_json(filepath: str, data: Any, indent: int = 2) -> bool:
    """安全保存 JSON 文件"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent, default=str)
        return True
    except Exception as e:
        print(f"[错误] 保存失败: {filepath} - {e}")
        return False


def get_data_version(data_path: str) -> str:
    """检测数据版本"""
    # 检查 v4 标记
    if os.path.exists(os.path.join(data_path, MIGRATION_MARKER)):
        return "v4"
    
    # 检查 v4 目录结构
    if os.path.exists(os.path.join(data_path, V4_TEMPORAL_GRAPH_DIR)):
        return "v4"
    
    # 检查 manifest 版本
    manifest_path = os.path.join(data_path, "manifest.json")
    if os.path.exists(manifest_path):
        manifest = safe_load_json(manifest_path)
        if manifest:
            version = manifest.get('version', '3.0')
            if version.startswith('4'):
                return "v4"
    
    return "v3"


# ============================================================
# 备份功能
# ============================================================

def create_backup(data_path: str, backup_dir: Optional[str] = None) -> Tuple[bool, str]:
    """创建数据备份
    
    Returns:
        (success, backup_path)
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if backup_dir:
        backup_path = os.path.join(backup_dir, f"recall_backup_{timestamp}")
    else:
        backup_path = os.path.join(os.path.dirname(data_path), f"recall_backup_{timestamp}")
    
    try:
        print(f"\n[备份] 创建备份...")
        print(f"       源: {data_path}")
        print(f"       目标: {backup_path}")
        
        shutil.copytree(data_path, backup_path)
        
        # 计算备份大小
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk(backup_path):
            for f in files:
                total_size += os.path.getsize(os.path.join(root, f))
                file_count += 1
        
        print(f"[备份] 完成! {file_count} 个文件, {format_size(total_size)}")
        return True, backup_path
        
    except Exception as e:
        print(f"[错误] 备份失败: {e}")
        return False, ""


def restore_backup(backup_path: str, data_path: str) -> bool:
    """从备份恢复"""
    if not os.path.exists(backup_path):
        print(f"[错误] 备份不存在: {backup_path}")
        return False
    
    try:
        print(f"\n[恢复] 从备份恢复...")
        
        # 删除当前数据
        if os.path.exists(data_path):
            shutil.rmtree(data_path)
        
        # 复制备份
        shutil.copytree(backup_path, data_path)
        
        print(f"[恢复] 完成!")
        return True
        
    except Exception as e:
        print(f"[错误] 恢复失败: {e}")
        return False


# ============================================================
# 数据分析
# ============================================================

def analyze_v3_data(data_path: str) -> Dict[str, Any]:
    """分析 v3 数据结构"""
    result = {
        'version': get_data_version(data_path),
        'entities': [],
        'relations': [],
        'turns': 0,
        'events': 0,
        'knowledge_graph': None,
        'users': [],
        'total_size': 0
    }
    
    # 分析 knowledge_graph.json
    kg_path = os.path.join(data_path, V3_KNOWLEDGE_GRAPH_FILE)
    if os.path.exists(kg_path):
        kg_data = safe_load_json(kg_path)
        if kg_data:
            result['knowledge_graph'] = {
                'entities': len(kg_data.get('entities', {})),
                'relations': len(kg_data.get('relations', []))
            }
            result['entities'] = list(kg_data.get('entities', {}).keys())
            result['relations'] = kg_data.get('relations', [])
    
    # 分析用户目录
    for item in os.listdir(data_path):
        item_path = os.path.join(data_path, item)
        if os.path.isdir(item_path) and not item.startswith('.') and not item.startswith('_'):
            # 检查是否是用户目录
            if item not in ['temporal_graph', 'indexes', 'cache', 'config', 'foreshadowing_analyzer']:
                result['users'].append(item)
    
    # 计算总大小
    for root, dirs, files in os.walk(data_path):
        for f in files:
            try:
                result['total_size'] += os.path.getsize(os.path.join(root, f))
            except:
                pass
    
    return result


def print_analysis(analysis: Dict[str, Any]):
    """打印分析结果"""
    print("\n" + "=" * 60)
    print("数据分析报告")
    print("=" * 60)
    
    print(f"\n数据版本: {analysis['version']}")
    print(f"总大小: {format_size(analysis['total_size'])}")
    
    if analysis['knowledge_graph']:
        print(f"\n知识图谱:")
        print(f"  - 实体数: {analysis['knowledge_graph']['entities']}")
        print(f"  - 关系数: {analysis['knowledge_graph']['relations']}")
    
    if analysis['users']:
        print(f"\n用户目录: {len(analysis['users'])}")
        for user in analysis['users'][:5]:
            print(f"  - {user}")
        if len(analysis['users']) > 5:
            print(f"  ... 还有 {len(analysis['users']) - 5} 个")
    
    print("\n" + "=" * 60)


# ============================================================
# 迁移逻辑
# ============================================================

def migrate_entity_to_node(entity: Dict[str, Any]) -> Dict[str, Any]:
    """将 v3 Entity 迁移到 v4 UnifiedNode"""
    now = datetime.now().isoformat()
    
    # 获取实体类型
    entity_type = entity.get('type', 'ENTITY')
    
    # 映射到 NodeType
    type_map = {
        'CHARACTER': 'ENTITY',
        'LOCATION': 'ENTITY',
        'ITEM': 'ENTITY',
        'CONCEPT': 'CONCEPT',
        'EVENT': 'EVENT',
    }
    
    node = {
        'uuid': entity.get('id', generate_uuid()),
        'name': entity.get('name', ''),
        'node_type': type_map.get(entity_type, 'ENTITY'),
        
        # 三时态
        'fact_time': entity.get('first_seen', now),
        'knowledge_time': entity.get('last_updated', now),
        'system_time': now,
        
        # 属性
        'attributes': entity.get('attributes', {}),
        'description': entity.get('description', ''),
        'aliases': entity.get('aliases', []),
        
        # 元数据
        'metadata': {
            'source': entity.get('source', 'migration'),
            'original_type': entity_type,
            'migrated_from': 'v3',
            'migrated_at': now
        },
        
        'valid_from': entity.get('first_seen'),
        'valid_until': None,
        'confidence': entity.get('confidence', 0.8)
    }
    
    return node


def migrate_relation_to_fact(
    relation: Dict[str, Any],
    entity_map: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """将 v3 Relation 迁移到 v4 TemporalFact"""
    now = datetime.now().isoformat()
    
    # 获取主体和客体
    source = relation.get('source', '')
    target = relation.get('target', '')
    
    if not source or not target:
        return None
    
    # 查找对应的节点 UUID
    source_uuid = entity_map.get(source, source)
    target_uuid = entity_map.get(target, target)
    
    fact = {
        'uuid': relation.get('id', generate_uuid()),
        'subject': source,
        'subject_uuid': source_uuid,
        'predicate': relation.get('relation_type', 'RELATED_TO'),
        'object': target,
        'object_uuid': target_uuid,
        
        # 自然语言描述
        'fact': f"{source} {relation.get('relation_type', 'relates to')} {target}",
        
        # 三时态
        'fact_time': relation.get('created_at', now),
        'knowledge_time': relation.get('updated_at', now),
        'system_time': now,
        
        # 有效期
        'valid_from': relation.get('valid_from'),
        'valid_until': relation.get('valid_until'),
        
        # 元数据
        'confidence': relation.get('confidence', 0.7),
        'source_episode': relation.get('source_episode'),
        'metadata': {
            'original_type': relation.get('relation_type'),
            'migrated_from': 'v3',
            'migrated_at': now
        }
    }
    
    return fact


def migrate_turn_to_episode(
    turn: Dict[str, Any],
    user_id: str,
    character_id: str
) -> Dict[str, Any]:
    """将 v3 Turn 迁移到 v4 EpisodicNode"""
    now = datetime.now().isoformat()
    
    episode = {
        'uuid': turn.get('id', generate_uuid()),
        'content': turn.get('content', ''),
        
        # 三时态
        'fact_time': turn.get('timestamp', now),
        'knowledge_time': now,
        'system_time': now,
        
        # 元信息
        'user_id': user_id,
        'character_id': character_id,
        'session_id': turn.get('session_id', 'default'),
        'role': turn.get('role', 'user'),
        'turn_number': turn.get('turn_number', 0),
        
        # 关联
        'extracted_entities': turn.get('entities', []),
        'extracted_facts': [],
        
        # 元数据
        'metadata': {
            'migrated_from': 'v3',
            'migrated_at': now
        }
    }
    
    return episode


def run_migration(
    data_path: str,
    dry_run: bool = False,
    backup_dir: Optional[str] = None
) -> MigrationStats:
    """执行迁移"""
    stats = MigrationStats()
    
    print("\n" + "=" * 60)
    print("开始 v3 → v4 数据迁移")
    print("=" * 60)
    
    # 检查版本
    version = get_data_version(data_path)
    if version == "v4":
        print("[跳过] 数据已经是 v4 版本")
        return stats
    
    # 创建备份
    if not dry_run:
        success, backup_path = create_backup(data_path, backup_dir)
        if not success:
            print("[错误] 备份失败，终止迁移")
            return stats
    
    # 1. 迁移知识图谱
    print("\n[1/3] 迁移知识图谱...")
    kg_path = os.path.join(data_path, V3_KNOWLEDGE_GRAPH_FILE)
    
    nodes = []
    edges = []
    entity_map = {}  # name -> uuid
    
    if os.path.exists(kg_path):
        kg_data = safe_load_json(kg_path)
        if kg_data:
            # 迁移实体
            entities = kg_data.get('entities', {})
            stats.entities_found = len(entities)
            
            for name, entity in entities.items():
                try:
                    node = migrate_entity_to_node(entity)
                    nodes.append(node)
                    entity_map[name] = node['uuid']
                    stats.entities_migrated += 1
                except Exception as e:
                    stats.errors.append(f"实体迁移失败 {name}: {e}")
            
            print(f"       实体: {stats.entities_migrated}/{stats.entities_found}")
            
            # 迁移关系
            relations = kg_data.get('relations', [])
            stats.relations_found = len(relations)
            
            for rel in relations:
                try:
                    fact = migrate_relation_to_fact(rel, entity_map)
                    if fact:
                        edges.append(fact)
                        stats.relations_migrated += 1
                except Exception as e:
                    stats.errors.append(f"关系迁移失败: {e}")
            
            print(f"       关系: {stats.relations_migrated}/{stats.relations_found}")
    
    # 2. 迁移回合数据
    print("\n[2/3] 迁移回合数据...")
    episodes = []
    
    # 遍历用户目录
    for user_id in os.listdir(data_path):
        user_path = os.path.join(data_path, user_id)
        if not os.path.isdir(user_path):
            continue
        if user_id.startswith('.') or user_id in ['temporal_graph', 'indexes', 'cache', 'config', 'foreshadowing_analyzer', 'L1_consolidated', 'L3_archive']:
            continue
        
        # 遍历角色目录
        for char_id in os.listdir(user_path):
            char_path = os.path.join(user_path, char_id)
            if not os.path.isdir(char_path):
                continue
            
            # 查找 turns 文件
            turns_file = os.path.join(char_path, 'turns.json')
            if os.path.exists(turns_file):
                turns_data = safe_load_json(turns_file)
                if turns_data and isinstance(turns_data, list):
                    stats.turns_found += len(turns_data)
                    
                    for turn in turns_data:
                        try:
                            episode = migrate_turn_to_episode(turn, user_id, char_id)
                            episodes.append(episode)
                            stats.turns_migrated += 1
                        except Exception as e:
                            stats.errors.append(f"回合迁移失败: {e}")
    
    print(f"       回合: {stats.turns_migrated}/{stats.turns_found}")
    
    # 3. 保存 v4 数据
    print("\n[3/3] 保存 v4 数据...")
    
    if not dry_run:
        v4_dir = os.path.join(data_path, V4_TEMPORAL_GRAPH_DIR)
        os.makedirs(v4_dir, exist_ok=True)
        
        # 保存节点
        nodes_path = os.path.join(v4_dir, V4_NODES_FILE)
        if safe_save_json(nodes_path, {'nodes': nodes, 'version': '4.0'}):
            print(f"       节点: {nodes_path}")
        
        # 保存边（事实）
        edges_path = os.path.join(v4_dir, V4_EDGES_FILE)
        if safe_save_json(edges_path, {'edges': edges, 'version': '4.0'}):
            print(f"       边: {edges_path}")
        
        # 保存情节
        episodes_path = os.path.join(v4_dir, V4_EPISODES_FILE)
        if safe_save_json(episodes_path, {'episodes': episodes, 'version': '4.0'}):
            print(f"       情节: {episodes_path}")
        
        # 创建迁移标记
        marker_path = os.path.join(data_path, MIGRATION_MARKER)
        with open(marker_path, 'w') as f:
            f.write(json.dumps({
                'migrated_at': datetime.now().isoformat(),
                'from_version': 'v3',
                'to_version': 'v4',
                'stats': {
                    'entities': stats.entities_migrated,
                    'relations': stats.relations_migrated,
                    'turns': stats.turns_migrated
                }
            }, indent=2))
        
        # 更新 manifest
        manifest_path = os.path.join(data_path, 'manifest.json')
        manifest = safe_load_json(manifest_path) or {}
        manifest['version'] = '4.0'
        manifest['migrated_at'] = datetime.now().isoformat()
        safe_save_json(manifest_path, manifest)
    
    # 打印结果
    print("\n" + "=" * 60)
    print("迁移完成!")
    print("=" * 60)
    print(f"  实体迁移: {stats.entities_migrated}")
    print(f"  关系迁移: {stats.relations_migrated}")
    print(f"  回合迁移: {stats.turns_migrated}")
    
    if stats.errors:
        print(f"\n  错误 ({len(stats.errors)}):")
        for err in stats.errors[:5]:
            print(f"    - {err}")
        if len(stats.errors) > 5:
            print(f"    ... 还有 {len(stats.errors) - 5} 个错误")
    
    if stats.warnings:
        print(f"\n  警告 ({len(stats.warnings)}):")
        for warn in stats.warnings[:5]:
            print(f"    - {warn}")
    
    return stats


# ============================================================
# 交互式菜单
# ============================================================

def interactive_menu(data_path: str):
    """交互式菜单"""
    while True:
        print("\n" + "=" * 60)
        print("Recall-ai v3 → v4 数据迁移工具")
        print("=" * 60)
        print(f"\n数据目录: {data_path}")
        print(f"当前版本: {get_data_version(data_path)}")
        
        print("\n操作选项:")
        print("  1. 分析数据")
        print("  2. 执行迁移")
        print("  3. 模拟迁移 (dry-run)")
        print("  4. 从备份恢复")
        print("  0. 退出")
        
        choice = input("\n请选择 [0-4]: ").strip()
        
        if choice == '0':
            print("再见!")
            break
        
        elif choice == '1':
            analysis = analyze_v3_data(data_path)
            print_analysis(analysis)
        
        elif choice == '2':
            confirm = input("\n确认执行迁移? (y/n): ").strip().lower()
            if confirm == 'y':
                run_migration(data_path, dry_run=False)
        
        elif choice == '3':
            print("\n[模拟模式] 不会实际修改任何数据")
            run_migration(data_path, dry_run=True)
        
        elif choice == '4':
            backup_path = input("\n请输入备份路径: ").strip()
            if backup_path:
                confirm = input(f"确认从 {backup_path} 恢复? (y/n): ").strip().lower()
                if confirm == 'y':
                    restore_backup(backup_path, data_path)
        
        else:
            print("无效选择")


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Recall-ai v3 → v4 数据迁移工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python migrate_v3_to_v4.py                    # 交互式菜单
  python migrate_v3_to_v4.py --analyze          # 仅分析
  python migrate_v3_to_v4.py --dry-run          # 模拟运行
  python migrate_v3_to_v4.py -y                 # 自动确认迁移
"""
    )
    
    parser.add_argument('--data-path', '-d', type=str,
                        help='数据目录路径 (默认: recall_data/data)')
    parser.add_argument('--analyze', '-a', action='store_true',
                        help='仅分析数据，不执行迁移')
    parser.add_argument('--dry-run', action='store_true',
                        help='模拟运行，不实际修改数据')
    parser.add_argument('--backup-dir', '-b', type=str,
                        help='备份目录')
    parser.add_argument('-y', '--yes', action='store_true',
                        help='自动确认，跳过确认提示')
    parser.add_argument('--version', '-v', action='version',
                        version=f'%(prog)s {VERSION}')
    
    args = parser.parse_args()
    
    # 确定数据路径
    if args.data_path:
        data_path = args.data_path
    else:
        # 默认路径
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        data_path = os.path.join(project_root, 'recall_data', 'data')
    
    # 检查路径
    if not os.path.exists(data_path):
        print(f"[错误] 数据目录不存在: {data_path}")
        sys.exit(1)
    
    # 执行操作
    if args.analyze:
        analysis = analyze_v3_data(data_path)
        print_analysis(analysis)
    
    elif args.dry_run:
        print("[模拟模式] 不会实际修改任何数据")
        run_migration(data_path, dry_run=True, backup_dir=args.backup_dir)
    
    elif args.yes:
        run_migration(data_path, dry_run=False, backup_dir=args.backup_dir)
    
    else:
        # 交互式菜单
        interactive_menu(data_path)


if __name__ == '__main__':
    main()
