"""关系提取器 - 从对话中自动发现实体关系"""

import re
from typing import List, Tuple, Callable


class RelationExtractor:
    """从文本中自动提取实体关系"""
    
    # 关系模式（正则匹配）
    PATTERNS: List[Tuple[str, Callable]] = [
        # 中文模式
        (r'(.{2,10})是(.{2,10})的(朋友|敌人|家人|老师|学生|上司|下属)', 
         lambda m: (m.group(1), 'IS_' + {'朋友':'FRIEND', '敌人':'ENEMY', '家人':'FAMILY', 
                    '老师':'MENTOR', '学生':'STUDENT', '上司':'BOSS', '下属':'SUBORDINATE'}.get(m.group(3), 'RELATED') + '_OF', m.group(2))),
        
        (r'(.{2,10})爱上了(.{2,10})', lambda m: (m.group(1), 'LOVES', m.group(2))),
        (r'(.{2,10})喜欢(.{2,10})', lambda m: (m.group(1), 'LIKES', m.group(2))),
        (r'(.{2,10})讨厌(.{2,10})', lambda m: (m.group(1), 'HATES', m.group(2))),
        (r'(.{2,10})住在(.{2,10})', lambda m: (m.group(1), 'LIVES_IN', m.group(2))),
        (r'(.{2,10})去了(.{2,10})', lambda m: (m.group(1), 'TRAVELS_TO', m.group(2))),
        (r'(.{2,10})拥有(.{2,10})', lambda m: (m.group(1), 'OWNS', m.group(2))),
        (r'(.{2,10})给(.{2,10})了(.{2,10})', lambda m: (m.group(1), 'GAVE_TO', m.group(2))),
        
        # 英文模式
        (r'(\w+) is (?:a )?friend of (\w+)', lambda m: (m.group(1), 'IS_FRIEND_OF', m.group(2))),
        (r'(\w+) loves (\w+)', lambda m: (m.group(1), 'LOVES', m.group(2))),
        (r'(\w+) lives in (\w+)', lambda m: (m.group(1), 'LIVES_IN', m.group(2))),
    ]
    
    def __init__(self, entity_extractor=None):
        self.entity_extractor = entity_extractor
    
    def extract(self, text: str, turn: int = 0) -> List[Tuple[str, str, str, str]]:
        """
        从文本中提取关系
        
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
                except:
                    continue
        
        # 2. 基于共现（同一句话中出现的实体可能有关系）
        if self.entity_extractor:
            sentences = re.split(r'[。.!?！？]', text)
            entities = self.entity_extractor.extract(text)
            
            for sentence in sentences:
                sentence_entities = [e for e in entities if e.name in sentence]
                # 如果同一句话有多个实体，建立弱关系
                if len(sentence_entities) >= 2:
                    for i, e1 in enumerate(sentence_entities[:-1]):
                        for e2 in sentence_entities[i+1:]:
                            relations.append((e1.name, 'MENTIONED_WITH', e2.name, sentence))
        
        return relations
