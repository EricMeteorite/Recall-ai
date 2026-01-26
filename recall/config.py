"""配置管理 - 包含 Lite 模式配置 + Phase 3.6 三路召回配置"""

import os
import re
from typing import List
from dataclasses import dataclass


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class LiteConfig:
    """Lite 模式 - 适合低配电脑（原 LightweightConfig）"""
    
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
        _safe_print("[Recall] Lite 模式已启用，内存占用约 ~80MB")


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


# ============================================================================
# 向后兼容别名
# ============================================================================
LightweightConfig = LiteConfig  # 兼容旧代码


# ============================================================================
# Phase 3.6: 三路召回配置
# ============================================================================
@dataclass
class TripleRecallConfig:
    """Phase 3.6: 三路召回配置
    
    支持三种预设模式:
    - default(): 平衡模式
    - max_recall(): 最大召回模式（100% 不遗忘优先）
    - fast(): 快速模式（速度优先）
    """
    
    # 并行召回开关
    enabled: bool = True
    
    # 路径权重（用于 RRF 融合）
    vector_weight: float = 1.0       # 语义召回权重
    keyword_weight: float = 1.2      # 关键词召回权重（100%召回，权重更高）
    entity_weight: float = 1.0       # 实体召回权重
    
    # RRF 参数
    rrf_k: int = 60                  # RRF 常数
    
    # 原文兜底配置
    fallback_enabled: bool = True    # 启用原文兜底
    fallback_parallel: bool = True   # 并行扫描
    fallback_workers: int = 4        # 并行线程数
    fallback_max_results: int = 50   # 兜底最大结果数
    
    # IVF-HNSW 参数
    hnsw_m: int = 32                 # HNSW 图连接数
    hnsw_ef_construction: int = 200  # 构建精度
    hnsw_ef_search: int = 64         # 搜索精度
    
    @classmethod
    def default(cls) -> 'TripleRecallConfig':
        """默认配置（平衡模式）"""
        return cls()
    
    @classmethod
    def max_recall(cls) -> 'TripleRecallConfig':
        """最大召回模式（100% 不遗忘优先）"""
        return cls(
            hnsw_m=48,
            hnsw_ef_construction=300,
            hnsw_ef_search=128,
            keyword_weight=1.5,
        )
    
    @classmethod
    def fast(cls) -> 'TripleRecallConfig':
        """快速模式（速度优先）"""
        return cls(
            hnsw_m=16,
            hnsw_ef_construction=100,
            hnsw_ef_search=32,
            fallback_workers=2,
        )
    
    @classmethod
    def from_env(cls) -> 'TripleRecallConfig':
        """从环境变量加载配置"""
        return cls(
            enabled=os.getenv('TRIPLE_RECALL_ENABLED', 'true').lower() == 'true',
            vector_weight=float(os.getenv('TRIPLE_RECALL_VECTOR_WEIGHT', '1.0')),
            keyword_weight=float(os.getenv('TRIPLE_RECALL_KEYWORD_WEIGHT', '1.2')),
            entity_weight=float(os.getenv('TRIPLE_RECALL_ENTITY_WEIGHT', '1.0')),
            rrf_k=int(os.getenv('TRIPLE_RECALL_RRF_K', '60')),
            hnsw_m=int(os.getenv('VECTOR_IVF_HNSW_M', '32')),
            hnsw_ef_construction=int(os.getenv('VECTOR_IVF_HNSW_EF_CONSTRUCTION', '200')),
            hnsw_ef_search=int(os.getenv('VECTOR_IVF_HNSW_EF_SEARCH', '64')),
            fallback_enabled=os.getenv('FALLBACK_ENABLED', 'true').lower() == 'true',
            fallback_parallel=os.getenv('FALLBACK_PARALLEL', 'true').lower() == 'true',
            fallback_workers=int(os.getenv('FALLBACK_WORKERS', '4')),
            fallback_max_results=int(os.getenv('FALLBACK_MAX_RESULTS', '50')),
        )
