#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重建知识图谱关系

问题：
- 某些实体（如"娃圈"）虽然存在于 entity_index，但 knowledge_graph 中没有关系
- 这是因为添加记忆时实体提取器没有识别这些实体

解决方案：
- 基于现有的 entity_index 和原始记忆重新提取关系
"""

import json
import re
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recall.graph.relation_extractor import RelationExtractor
from recall.processor.entity_extractor import EntityExtractor


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_all_memories(data_dir):
    """查找所有 memories.json 文件并合并"""
    import glob
    all_memories = []
    pattern = os.path.join(data_dir, 'data', '**', 'memories.json')
    for mem_file in glob.glob(pattern, recursive=True):
        try:
            with open(mem_file, 'r', encoding='utf-8') as f:
                memories = json.load(f)
                if isinstance(memories, list):
                    all_memories.extend(memories)
                    print(f"  加载 {len(memories)} 条记忆: {mem_file}")
                elif isinstance(memories, dict):
                    all_memories.extend(memories.values())
                    print(f"  加载 {len(memories)} 条记忆: {mem_file}")
        except Exception as e:
            print(f"  跳过 {mem_file}: {e}")
    return all_memories


def main():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'recall_data')
    
    # 加载数据
    kg_path = os.path.join(data_dir, 'data', 'knowledge_graph.json')
    entity_path = os.path.join(data_dir, 'indexes', 'entity_index.json')
    
    print(f"加载知识图谱: {kg_path}")
    kg = load_json(kg_path)
    
    print(f"加载实体索引: {entity_path}")
    entities = load_json(entity_path)
    
    print(f"加载记忆...")
    memories = find_all_memories(data_dir)
    
    # 获取所有实体名
    entity_names = {e['name'] for e in entities}
    print(f"共 {len(entity_names)} 个实体")
    
    # 统计现有关系
    existing_relations = set()
    for rel in kg.get('relations', []):
        key = (rel['source_id'], rel['relation_type'], rel['target_id'])
        existing_relations.add(key)
    print(f"现有 {len(existing_relations)} 条关系")
    
    # 找出没有关系的实体
    entities_with_relations = set()
    for rel in kg.get('relations', []):
        entities_with_relations.add(rel['source_id'])
        entities_with_relations.add(rel['target_id'])
    
    entities_without_relations = entity_names - entities_with_relations
    print(f"没有关系的实体: {entities_without_relations}")
    
    # 遍历所有记忆，找包含这些实体的句子
    new_relations = []
    
    for mem_data in memories:
        content = mem_data.get('content', '')
        metadata = mem_data.get('metadata', {})
        mem_entities = metadata.get('entities', [])  # 已提取的实体列表
        
        if not content or not mem_entities:
            continue
        
        # 分句
        sentences = re.split(r'[。.!?！？\n]', content)
        
        for sentence in sentences:
            if len(sentence) < 5:
                continue
            
            # 找出此句子中的实体（从已提取的实体列表中匹配）
            sentence_entities = [name for name in mem_entities if name in sentence]
            
            if len(sentence_entities) >= 2:
                # 建立共现关系
                for i, e1 in enumerate(sentence_entities[:-1]):
                    for e2 in sentence_entities[i+1:]:
                        key = (e1, 'MENTIONED_WITH', e2)
                        key_rev = (e2, 'MENTIONED_WITH', e1)
                        
                        # 避免重复
                        if key not in existing_relations and key_rev not in existing_relations:
                            if key not in [(r['source_id'], r['relation_type'], r['target_id']) for r in new_relations]:
                                new_relations.append({
                                    'source_id': e1,
                                    'relation_type': 'MENTIONED_WITH',
                                    'target_id': e2,
                                    'source_text': sentence[:200],
                                    'weight': 1.0
                                })
                                existing_relations.add(key)
                                print(f"  新关系: {e1} <-> {e2}")
    
    if new_relations:
        print(f"\n共发现 {len(new_relations)} 条新关系")
        
        # 添加到 knowledge_graph
        if 'relations' not in kg:
            kg['relations'] = []
        kg['relations'].extend(new_relations)
        
        # 保存
        save_json(kg_path, kg)
        print(f"已保存到 {kg_path}")
    else:
        print("\n没有发现新关系")


if __name__ == '__main__':
    main()
