"""关系提取器 - 从对话中自动发现实体关系"""

import re
from typing import List, Tuple, Callable


class RelationExtractor:
    """从文本中自动提取实体关系"""
    
    # 关系模式（正则匹配）
    PATTERNS: List[Tuple[str, Callable]] = [
        # 中文模式 - 使用非贪婪匹配和适当的边界
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})是([\u4e00-\u9fa5A-Za-z]{1,15})的(朋友|敌人|家人|老师|学生|上司|下属)', 
         lambda m: (m.group(1), 'IS_' + {'朋友':'FRIEND', '敌人':'ENEMY', '家人':'FAMILY', 
                    '老师':'MENTOR', '学生':'STUDENT', '上司':'BOSS', '下属':'SUBORDINATE'}.get(m.group(3), 'RELATED') + '_OF', m.group(2))),
        
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})爱上了([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'LOVES', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})喜欢([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'LIKES', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})讨厌([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'HATES', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})住在([\u4e00-\u9fa5]{1,10})', lambda m: (m.group(1), 'LIVES_IN', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})去了([\u4e00-\u9fa5]{1,10})', lambda m: (m.group(1), 'TRAVELS_TO', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})拥有([\u4e00-\u9fa5A-Za-z]{1,15})', lambda m: (m.group(1), 'OWNS', m.group(2))),
        (r'([\u4e00-\u9fa5A-Za-z]{1,15})给([\u4e00-\u9fa5A-Za-z]{1,15})了(.{1,15})', lambda m: (m.group(1), 'GAVE_TO', m.group(2))),
        
        # 英文模式
        (r'(\w+) is (?:a )?friend of (\w+)', lambda m: (m.group(1), 'IS_FRIEND_OF', m.group(2))),
        (r'(\w+) loves (\w+)', lambda m: (m.group(1), 'LOVES', m.group(2))),
        (r'(\w+) lives in (\w+)', lambda m: (m.group(1), 'LIVES_IN', m.group(2))),
    ]
    
    def __init__(self, entity_extractor=None):
        self.entity_extractor = entity_extractor
    
    def extract(self, text: str, turn: int = 0, entities: list = None) -> List[Tuple[str, str, str, str]]:
        """
        从文本中提取关系
        
        Args:
            text: 原始文本
            turn: 轮次（暂未使用）
            entities: 可选，已提取的实体列表。如果提供则复用，否则重新提取。
                      支持 ExtractedEntity 对象列表或字符串列表。
        
        Returns:
            [(source, relation_type, target, source_text), ...]
        """
        relations = []
        
        # 1. 基于模式匹配
        for pattern, extractor in self.PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    source, rel_type, target = extractor(match)
                    relations.append((source.strip(), rel_type, target.strip(), match.group(0)))
                except Exception:
                    continue
        
        # 2. 基于共现（同一句话中出现的实体可能有关系）
        # 优先使用传入的实体列表，否则重新提取
        if entities is None and self.entity_extractor:
            entities = self.entity_extractor.extract(text)
        
        if entities:
            sentences = re.split(r'[。.!?！？\n]', text)
            
            # 统一转换为实体名列表
            entity_names = []
            for e in entities:
                if hasattr(e, 'name'):
                    entity_names.append(e.name)
                elif isinstance(e, str):
                    entity_names.append(e)
                elif isinstance(e, dict) and 'name' in e:
                    entity_names.append(e['name'])
            
            for sentence in sentences:
                if len(sentence) < 3:
                    continue
                # 找出此句子中包含的实体
                sentence_entities = [name for name in entity_names if name in sentence]
                # 如果同一句话有多个实体，建立弱关系
                if len(sentence_entities) >= 2:
                    for i, e1 in enumerate(sentence_entities[:-1]):
                        for e2 in sentence_entities[i+1:]:
                            relations.append((e1, 'MENTIONED_WITH', e2, sentence))
        
        return relations
