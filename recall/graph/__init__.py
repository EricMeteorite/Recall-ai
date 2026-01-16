"""图谱层模块"""

from .knowledge_graph import KnowledgeGraph, Relation
from .relation_extractor import RelationExtractor

__all__ = [
    'KnowledgeGraph',
    'Relation',
    'RelationExtractor',
]
