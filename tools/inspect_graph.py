#!/usr/bin/env python3
"""Recall 图谱诊断工具 - 在命令行查看实体关系

使用方法:
    python tools/inspect_graph.py                    # 查看默认用户的图谱
    python tools/inspect_graph.py --user 角色名      # 查看特定用户的图谱
    python tools/inspect_graph.py --ascii            # ASCII 树形图（更兼容）
    python tools/inspect_graph.py --detail           # 显示详细信息
"""

import os
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def safe_print(msg: str) -> None:
    """安全打印，兼容 Windows GBK"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def load_knowledge_graph(data_root: str) -> dict:
    """加载知识图谱数据"""
    # 尝试多个可能的位置
    possible_paths = [
        os.path.join(data_root, "knowledge_graph.json"),
        os.path.join(data_root, "data", "knowledge_graph.json"),
    ]
    for kg_file in possible_paths:
        if os.path.exists(kg_file):
            with open(kg_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    return {"entities": {}, "relations": []}


def load_entity_index(data_root: str) -> dict:
    """加载实体索引"""
    # 尝试多个可能的位置
    possible_paths = [
        os.path.join(data_root, "indexes", "entity_index.json"),
        os.path.join(data_root, "data", "entity_index.json"),
        os.path.join(data_root, "entity_index.json"),
    ]
    for idx_file in possible_paths:
        if os.path.exists(idx_file):
            with open(idx_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 兼容不同格式：列表或字典
                if isinstance(data, list):
                    # 新格式：实体列表
                    entities = {}
                    for e in data:
                        if isinstance(e, dict):
                            eid = e.get('id', e.get('name', str(len(entities))))
                            entities[eid] = e
                    return {"entities": entities, "raw_list": data}
                return data
    return {"entities": {}}


def load_memories(data_root: str, user_id: str) -> list:
    """加载用户记忆"""
    memories = []
    
    # 尝试多个可能的路径结构
    possible_paths = [
        # 新结构: data/{user_id}/default/default/memories.json
        os.path.join(data_root, "data", user_id, "default", "default", "memories.json"),
        # 旧结构: data/{user_id}/memories.json
        os.path.join(data_root, "data", user_id, "memories.json"),
        # 更旧结构: {user_id}/memories.json
        os.path.join(data_root, user_id, "memories.json"),
        # default 用户
        os.path.join(data_root, "data", "default", "default", "default", "memories.json"),
    ]
    
    for memories_file in possible_paths:
        if os.path.exists(memories_file):
            with open(memories_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    memories = data
                elif isinstance(data, dict) and 'memories' in data:
                    memories = data['memories']
            if memories:
                break
    
    return memories


def print_separator(char='=', width=60):
    safe_print(char * width)


def print_header(title: str):
    print_separator()
    safe_print(f"  {title}")
    print_separator()


def inspect_graph(data_root: str, user_id: str, ascii_mode: bool = False, detail: bool = False):
    """检查并显示图谱"""
    
    data_path = os.path.join(data_root, "data")
    
    safe_print(f"\n[Recall 图谱诊断工具]")
    safe_print(f"数据根目录: {data_root}")
    safe_print(f"用户ID: {user_id}")
    
    # 1. 检查目录结构
    print_header("1. 数据文件检查")
    
    # 检查知识图谱文件（多个可能位置）
    kg_paths = [
        os.path.join(data_root, "knowledge_graph.json"),
        os.path.join(data_root, "data", "knowledge_graph.json"),
    ]
    kg_found = None
    for p in kg_paths:
        if os.path.exists(p):
            kg_found = p
            break
    if kg_found:
        size = os.path.getsize(kg_found)
        safe_print(f"  knowledge_graph.json: [OK] {size:,} bytes ({kg_found})")
    else:
        safe_print(f"  knowledge_graph.json: [--] 不存在")
    
    # 检查实体索引（多个可能位置）
    idx_paths = [
        os.path.join(data_root, "indexes", "entity_index.json"),
        os.path.join(data_root, "data", "entity_index.json"),
        os.path.join(data_root, "entity_index.json"),
    ]
    idx_found = None
    for p in idx_paths:
        if os.path.exists(p):
            idx_found = p
            break
    if idx_found:
        size = os.path.getsize(idx_found)
        safe_print(f"  entity_index.json: [OK] {size:,} bytes ({idx_found})")
    else:
        safe_print(f"  entity_index.json: [--] 不存在")
    
    # 检查用户记忆文件（多个可能位置）
    mem_paths = [
        os.path.join(data_root, "data", user_id, "default", "default", "memories.json"),
        os.path.join(data_root, "data", user_id, "memories.json"),
        os.path.join(data_root, user_id, "memories.json"),
    ]
    mem_found = None
    for p in mem_paths:
        if os.path.exists(p):
            mem_found = p
            break
    if mem_found:
        size = os.path.getsize(mem_found)
        safe_print(f"  memories.json: [OK] {size:,} bytes ({mem_found})")
    else:
        safe_print(f"  memories.json ({user_id}): [--] 不存在")
    
    # 检查L1_consolidated目录
    l1_path = os.path.join(data_root, "L1_consolidated")
    if os.path.exists(l1_path) and os.path.isdir(l1_path):
        size = sum(os.path.getsize(os.path.join(l1_path, f)) for f in os.listdir(l1_path) if os.path.isfile(os.path.join(l1_path, f)))
        safe_print(f"  L1_consolidated/: [OK] {size:,} bytes")
    else:
        safe_print(f"  L1_consolidated/: [--] 不存在")
    
    # 2. 加载知识图谱
    print_header("2. 知识图谱概览")
    
    kg_data = load_knowledge_graph(data_root)
    entities = kg_data.get("entities", {})
    relations = kg_data.get("relations", [])
    
    # 兼容不同格式
    if isinstance(relations, dict):
        # 旧格式: {"outgoing": {...}, "incoming": {...}}
        all_relations = []
        outgoing = relations.get("outgoing", {})
        for source, rels in outgoing.items():
            for rel in rels:
                all_relations.append({
                    "source": source,
                    "target": rel.get("target_id", rel.get("target", "")),
                    "type": rel.get("relation_type", rel.get("type", "RELATED")),
                    "confidence": rel.get("confidence", 0.5)
                })
        relations = all_relations
    
    safe_print(f"  实体数量: {len(entities)}")
    safe_print(f"  关系数量: {len(relations)}")
    
    if not entities and not relations:
        safe_print("\n  [!] 图谱为空！可能原因:")
        safe_print("      - 还没有添加任何记忆")
        safe_print("      - 实体提取器未正常工作")
        safe_print("      - 数据存储在其他位置")
    
    # 3. 显示实体列表
    if entities:
        print_header("3. 实体列表")
        
        # 按类型分组
        by_type = defaultdict(list)
        for eid, entity in entities.items():
            if isinstance(entity, dict):
                etype = entity.get("type", entity.get("entity_type", "UNKNOWN"))
                ename = entity.get("name", eid)
            else:
                etype = "UNKNOWN"
                ename = str(entity)
            by_type[etype].append(ename)
        
        for etype, names in sorted(by_type.items()):
            safe_print(f"\n  [{etype}] ({len(names)}个)")
            for name in names[:20]:  # 最多显示20个
                safe_print(f"    - {name}")
            if len(names) > 20:
                safe_print(f"    ... 还有 {len(names) - 20} 个")
    
    # 4. 显示关系
    if relations:
        print_header("4. 实体关系")
        
        if ascii_mode:
            # ASCII 模式：简单列表
            for rel in relations[:30]:
                src = rel.get("source", rel.get("source_id", "?"))
                tgt = rel.get("target", rel.get("target_id", "?"))
                rtype = rel.get("type", rel.get("relation_type", "RELATED"))
                conf = rel.get("confidence", 0.5)
                safe_print(f"  {src} --[{rtype}]--> {tgt}  (置信度: {conf:.2f})")
        else:
            # 树形图模式
            # 构建邻接表
            adj = defaultdict(list)
            for rel in relations:
                src = rel.get("source", rel.get("source_id", "?"))
                tgt = rel.get("target", rel.get("target_id", "?"))
                rtype = rel.get("type", rel.get("relation_type", "RELATED"))
                adj[src].append((tgt, rtype))
            
            # 找出根节点（入度为0或出度最高）
            targets = set()
            for rel in relations:
                targets.add(rel.get("target", rel.get("target_id", "")))
            
            roots = [s for s in adj.keys() if s not in targets]
            if not roots:
                roots = list(adj.keys())[:5]
            
            shown = set()
            for root in roots[:10]:
                if root in shown:
                    continue
                safe_print(f"\n  {root}")
                shown.add(root)
                for target, rtype in adj.get(root, [])[:10]:
                    safe_print(f"    |--[{rtype}]--> {target}")
                    shown.add(target)
                    # 二级关系
                    for t2, r2 in adj.get(target, [])[:5]:
                        if t2 not in shown:
                            safe_print(f"    |      |--[{r2}]--> {t2}")
        
        if len(relations) > 30:
            safe_print(f"\n  ... 还有 {len(relations) - 30} 条关系")
    
    # 5. 加载实体索引
    print_header("5. 实体索引")
    
    idx_data = load_entity_index(data_root)
    idx_entities = idx_data.get("entities", {})
    raw_list = idx_data.get("raw_list", [])
    
    safe_print(f"  索引实体数: {len(idx_entities) if idx_entities else len(raw_list)}")
    
    if detail and (idx_entities or raw_list):
        safe_print("\n  索引详情:")
        items = list(idx_entities.items())[:10] if idx_entities else [(str(i), e) for i, e in enumerate(raw_list[:10])]
        for eid, entity in items:
            name = entity.get("name", eid) if isinstance(entity, dict) else eid
            refs = entity.get("turn_references", []) if isinstance(entity, dict) else []
            safe_print(f"    - {name}: 出现 {len(refs)} 次")
    
    # 6. 用户记忆检查
    print_header("6. 用户记忆")
    
    memories = load_memories(data_root, user_id)
    safe_print(f"  记忆数量: {len(memories)}")
    
    if detail and memories:
        safe_print("\n  最近记忆:")
        for mem in memories[-5:]:
            content = mem.get("content", mem.get("memory", ""))[:60]
            safe_print(f"    - {content}...")
    
    # 7. 诊断建议
    print_header("7. 诊断结论")
    
    issues = []
    
    if not entities:
        issues.append("- 图谱无实体：检查实体提取器是否正常工作")
    
    if not relations:
        issues.append("- 图谱无关系：检查关系提取器是否正常工作")
    
    if not memories:
        issues.append("- 无记忆数据：请先通过 API 添加一些记忆")
    
    if memories and not entities:
        issues.append("- 有记忆但无实体：实体提取可能未生效，检查 EntityExtractor")
    
    if len(idx_entities) != len(entities):
        issues.append(f"- 实体数量不一致：索引={len(idx_entities)}, 图谱={len(entities)}")
    
    if issues:
        safe_print("  发现以下问题:")
        for issue in issues:
            safe_print(f"    {issue}")
    else:
        safe_print("  [OK] 图谱数据正常!")
        safe_print(f"       实体: {len(entities)} | 关系: {len(relations)} | 记忆: {len(memories)}")
    
    print_separator()


def main():
    parser = argparse.ArgumentParser(description='Recall 图谱诊断工具')
    parser.add_argument('--user', '-u', default='default', help='用户ID')
    parser.add_argument('--data-root', '-d', default='./recall_data', help='数据根目录')
    parser.add_argument('--ascii', '-a', action='store_true', help='使用 ASCII 模式显示')
    parser.add_argument('--detail', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    # 检查数据目录
    if not os.path.exists(args.data_root):
        safe_print(f"[ERROR] 数据目录不存在: {args.data_root}")
        safe_print("请确保 Recall 服务已运行并添加过数据")
        sys.exit(1)
    
    inspect_graph(
        data_root=args.data_root,
        user_id=args.user,
        ascii_mode=args.ascii,
        detail=args.detail
    )


if __name__ == "__main__":
    main()
