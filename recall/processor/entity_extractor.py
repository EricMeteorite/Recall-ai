"""实体提取器 - NLP驱动的实体识别"""

import re
import os
from typing import List, Set
from dataclasses import dataclass


@dataclass
class ExtractedEntity:
    """提取的实体"""
    name: str
    entity_type: str  # PERSON, LOCATION, ITEM, ORG, CODE_SYMBOL
    confidence: float
    source_text: str


class EntityExtractor:
    """实体提取器"""
    
    def __init__(self):
        # 延迟加载
        self._nlp = None
        self._jieba = None
        
        # 停用词
        self.stopwords = {
            '的', '了', '是', '在', '和', '有', '这', '那', '就', '都', 
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would'
        }
    
    @property
    def nlp(self):
        """懒加载 spaCy 模型"""
        if self._nlp is None:
            self._nlp = self._load_spacy_model()
        return self._nlp
    
    @property
    def jieba(self):
        """懒加载 jieba（缓存到项目目录）"""
        if self._jieba is None:
            import jieba
            # 设置 jieba 缓存到项目目录，不污染系统
            from ..init import RecallInit
            cache_dir = os.path.join(RecallInit.get_data_root(), 'cache')
            os.makedirs(cache_dir, exist_ok=True)
            jieba.dt.tmp_dir = cache_dir  # 设置临时目录
            self._jieba = jieba
        return self._jieba
    
    def _load_spacy_model(self):
        """加载 spaCy 模型，如果不存在则自动下载到本地目录（不污染全局）"""
        import spacy
        
        # 自定义模型缓存目录（隔离到项目目录 ./recall_data/models/）
        from ..init import RecallInit
        model_cache_dir = os.path.join(RecallInit.get_data_root(), 'models', 'spacy')
        os.makedirs(model_cache_dir, exist_ok=True)
        
        # 优先尝试从本地缓存加载
        for model_name in ['zh_core_web_sm', 'en_core_web_sm']:
            local_model_path = os.path.join(model_cache_dir, model_name)
            
            # 检查本地是否已有模型
            if os.path.exists(local_model_path):
                try:
                    return spacy.load(local_model_path)
                except Exception:
                    pass
            
            # 尝试从全局加载（如果用户已安装）
            try:
                return spacy.load(model_name)
            except OSError:
                pass
        
        # 如果都失败，使用空白模型（基础功能仍可用）
        print("[Recall] 警告：无法加载 NLP 模型，实体识别功能将使用简化版本")
        return spacy.blank('zh')  # 空白模型，只有分词，没有NER
    
    def extract(self, text: str) -> List[ExtractedEntity]:
        """提取实体"""
        entities = []
        
        # 限制处理长度，避免性能问题
        max_len = 10000
        truncated_text = text[:max_len] if len(text) > max_len else text
        
        # 1. 使用spaCy提取命名实体
        doc = self.nlp(truncated_text)
        for ent in doc.ents:
            entity_type = self._map_spacy_label(ent.label_)
            if entity_type:
                entities.append(ExtractedEntity(
                    name=ent.text,
                    entity_type=entity_type,
                    confidence=0.8,
                    source_text=ent.sent.text if ent.sent else truncated_text[:100]
                ))
        
        # 2. 中文专名提取（引号内容、书名号内容）
        quoted = re.findall(r'[「『"\'](.*?)[」』"\']', truncated_text)
        for name in quoted:
            if 2 <= len(name) <= 20:
                entities.append(ExtractedEntity(
                    name=name,
                    entity_type='ITEM' if len(name) <= 4 else 'MISC',
                    confidence=0.6,
                    source_text=truncated_text[:100]
                ))
        
        # 3. 代码符号提取（限制长度避免匹配超长字符串）
        # 只匹配 3-50 字符的符号
        code_symbols = re.findall(r'\b([A-Z][a-zA-Z0-9_]{2,49})\b', truncated_text)  # CamelCase
        code_symbols += re.findall(r'\b([a-z_][a-zA-Z0-9_]{2,49})\b', truncated_text)  # snake_case
        for symbol in set(code_symbols):
            if not symbol.lower() in self.stopwords:
                entities.append(ExtractedEntity(
                    name=symbol,
                    entity_type='CODE_SYMBOL',
                    confidence=0.5,
                    source_text=truncated_text[:100]
                ))
        
        # 去重
        seen: Set[str] = set()
        unique_entities = []
        for e in entities:
            if e.name.lower() not in seen:
                seen.add(e.name.lower())
                unique_entities.append(e)
        
        return unique_entities
    
    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        keywords = []
        
        # 限制处理长度
        max_len = 10000
        truncated_text = text[:max_len] if len(text) > max_len else text
        
        # jieba分词提取
        words = self.jieba.cut(truncated_text)
        for word in words:
            # 限制关键词长度在 2-50 字符
            if 2 <= len(word) <= 50 and word not in self.stopwords:
                keywords.append(word)
        
        # 英文关键词（限制长度 3-50 字符）
        english_words = re.findall(r'[a-zA-Z]{3,50}', truncated_text)
        keywords.extend([w.lower() for w in english_words if w.lower() not in self.stopwords])
        
        return list(set(keywords))
    
    def _map_spacy_label(self, label: str) -> str:
        """映射spaCy标签到我们的类型"""
        mapping = {
            'PERSON': 'PERSON',
            'PER': 'PERSON',
            'GPE': 'LOCATION',
            'LOC': 'LOCATION',
            'ORG': 'ORG',
            'PRODUCT': 'ITEM',
            'WORK_OF_ART': 'ITEM',
        }
        return mapping.get(label, None)
