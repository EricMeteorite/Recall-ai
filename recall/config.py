"""配置管理 - 包含轻量模式配置"""

import re
from typing import List
from dataclasses import dataclass


class LightweightConfig:
    """轻量模式 - 适合低配电脑"""
    
    # 禁用重型组件
    ENABLE_VECTOR_INDEX = False      # 不加载 sentence-transformers (~400MB)
    ENABLE_SPACY_FULL = False        # 不加载完整 spaCy 模型 (~50MB)
    
    # 使用轻量替代
    ENTITY_EXTRACTOR = 'jieba_rules'  # 用 jieba + 规则替代 spaCy
    RETRIEVAL_LAYERS = [1, 2, 3, 5, 7, 8]  # 跳过第4层(向量)和第6层(语义)
    
    # 内存限制
    MAX_CACHED_TURNS = 1000          # 减少缓存
    MAX_INDEX_SIZE_MB = 30           # 限制索引大小
    
    @classmethod
    def apply(cls, engine):
        """应用轻量配置"""
        engine.config = engine.config or {}
        engine.config.update({
            'vector_enabled': False,
            'spacy_model': 'blank',
            'retrieval_layers': cls.RETRIEVAL_LAYERS,
            'max_cache': cls.MAX_CACHED_TURNS,
        })
        print("[Recall] 轻量模式已启用，内存占用约 ~80MB")


@dataclass
class LightweightExtractedEntity:
    """轻量版提取实体"""
    name: str
    entity_type: str
    confidence: float = 0.5
    source_text: str = ""


class LightweightEntityExtractor:
    """轻量级实体提取器 - 不依赖 spaCy"""
    
    def __init__(self):
        self.re = re
        self._jieba = None  # 懒加载
        
        # 简单的命名实体模式
        self.patterns = {
            'PERSON': r'[「『"]([\u4e00-\u9fa5]{2,4})[」』"]说|(\w{2,10})先生|(\w{2,10})女士',
            'LOCATION': r'在([\u4e00-\u9fa5]{2,10})|去([\u4e00-\u9fa5]{2,10})',
            'ITEM': r'[「『"]([\u4e00-\u9fa5a-zA-Z]{2,20})[」』"]',
        }
        
        # 停用词
        self.stopwords = {
            '的', '了', '是', '在', '和', '有', '这', '那', '就', '都', 
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would'
        }
    
    @property
    def jieba(self):
        """懒加载 jieba"""
        if self._jieba is None:
            import jieba
            self._jieba = jieba
        return self._jieba
    
    def extract(self, text: str) -> List[LightweightExtractedEntity]:
        """提取实体（轻量版），返回与 EntityExtractor 兼容的对象"""
        entities = []
        seen_names = set()
        
        # 1. 正则模式匹配
        for entity_type, pattern in self.patterns.items():
            for match in self.re.finditer(pattern, text):
                name = next((g for g in match.groups() if g), None)
                if name and len(name) >= 2 and name not in seen_names:
                    entities.append(LightweightExtractedEntity(
                        name=name,
                        entity_type=entity_type,
                        confidence=0.6,
                        source_text=text[max(0, match.start()-20):match.end()+20]
                    ))
                    seen_names.add(name)
        
        # 2. jieba 分词 + 词性标注
        try:
            import jieba.posseg as pseg
            words = pseg.cut(text[:5000])  # 限制长度
            for word, flag in words:
                if flag in ('nr', 'ns', 'nt', 'nz') and len(word) >= 2 and word not in seen_names:
                    entity_type = {
                        'nr': 'PERSON', 
                        'ns': 'LOCATION', 
                        'nt': 'ORG', 
                        'nz': 'ITEM'
                    }.get(flag, 'MISC')
                    entities.append(LightweightExtractedEntity(
                        name=word,
                        entity_type=entity_type,
                        confidence=0.5,
                        source_text=""
                    ))
                    seen_names.add(word)
        except ImportError:
            pass  # jieba 未安装时跳过
        
        return entities
    
    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词（轻量版）"""
        # 中文词组
        chinese = self.re.findall(r'[\u4e00-\u9fa5]{2,6}', text)
        # 英文单词
        english = self.re.findall(r'[a-zA-Z]{3,}', text.lower())
        # 过滤停用词
        return [w for w in chinese + english if w not in self.stopwords]
