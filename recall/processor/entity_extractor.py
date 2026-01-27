"""实体提取器 - NLP驱动的实体识别"""

import re
import os
from typing import List, Set, Dict
from dataclasses import dataclass, field


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


@dataclass
class ExtractedEntity:
    """提取的实体"""
    name: str
    entity_type: str  # PERSON, LOCATION, ITEM, ORG, CODE_SYMBOL
    confidence: float
    source_text: str
    aliases: List[str] = field(default_factory=list)  # 实体别名


class EntityExtractor:
    """实体提取器"""
    
    def __init__(self):
        # 延迟加载
        self._nlp = None
        self._jieba = None
        
        # 停用词（扩展版）
        self.stopwords = {
            # 中文停用词
            '的', '了', '是', '在', '和', '有', '这', '那', '就', '都', '也', '还', '要',
            '我', '你', '他', '她', '它', '我们', '你们', '他们', '这个', '那个', '什么',
            '怎么', '为什么', '可以', '能够', '应该', '比如', '比如说', '然后', '所以',
            '因为', '但是', '如果', '虽然', '不过', '而且', '或者', '以及', '通过',
            '一个', '一些', '很多', '非常', '特别', '其实', '基本上', '大概', '可能',
            '诸如', '例如', '包括', '等等', '之类', '这种', '那种', '各种', '某些',
            '中古', '目前', '现在', '以前', '之前', '之后', '后来', '当时', '那时',
            # 英文停用词
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'can', 'could', 'should', 'may', 'might', 'must',
            'this', 'that', 'these', 'those', 'it', 'its',
            'and', 'or', 'but', 'if', 'then', 'else', 'when', 'where', 'how', 'why',
            'for', 'to', 'from', 'with', 'by', 'at', 'in', 'on', 'of',
        }
        
        # 需要过滤的误识别词（jieba分词或spaCy的常见错误）
        self.filter_words = {
            '诸如', '例如', '包括', '等等', '之类', '和骏河', '比如说',
            '中古', '目前', '现在', '以前', '之前', '之后', '后来', '当时',
        }
        
        # 已知的平台/产品/品牌名（用于增强识别）
        self.known_entities = {
            # 电商平台
            '闲鱼': 'ORG', '淘宝': 'ORG', '京东': 'ORG', '拼多多': 'ORG',
            '骏河屋': 'ORG', '煤炉': 'ORG', '雅虎': 'ORG', 'ebay': 'ORG', 
            'amazon': 'ORG', 'etsy': 'ORG', 'shopify': 'ORG',
            # 技术平台
            'github': 'ORG', 'n8n': 'ORG', '扣子': 'ORG', 'coze': 'ORG',
            'discord': 'ORG', 'reddit': 'ORG', 'twitter': 'ORG', 'x': 'ORG',
            # 娃圈品牌
            'bjd': 'CONCEPT', 'mjd': 'CONCEPT', 'mamachapp': 'ORG', 'azone': 'ORG',
            'volks': 'ORG', 'dollfie': 'ITEM',
            # AI相关
            'ai': 'CONCEPT', 'chatgpt': 'ORG', 'claude': 'ORG', 'deepseek': 'ORG',
            'openai': 'ORG', 'anthropic': 'ORG',
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
        
        last_error = "未找到模型"  # 初始化错误信息
        
        # 优先尝试从本地缓存加载
        for model_name in ['zh_core_web_sm', 'en_core_web_sm']:
            local_model_path = os.path.join(model_cache_dir, model_name)
            
            # 检查本地是否已有模型
            if os.path.exists(local_model_path):
                try:
                    return spacy.load(local_model_path)
                except Exception as e:
                    last_error = str(e)
            
            # 尝试从全局加载（如果用户已安装）
            try:
                return spacy.load(model_name)
            except Exception as e:
                # 记录具体错误便于调试
                last_error = str(e)
        
        # 如果都失败，使用空白模型（基础功能仍可用）
        _safe_print(f"[Recall] 警告：无法加载 NLP 模型，实体识别功能将使用简化版本 (原因: {last_error})")
        return spacy.blank('zh')  # 空白模型，只有分词，没有NER
    
    def extract(self, text: str) -> List[ExtractedEntity]:
        """提取实体 - 增强版，结合多种方法"""
        entities = []
        
        # 限制处理长度，避免性能问题
        max_len = 10000
        truncated_text = text[:max_len] if len(text) > max_len else text
        text_lower = truncated_text.lower()
        
        # 1. 已知实体词典匹配（高优先级）
        for name, entity_type in self.known_entities.items():
            if name.lower() in text_lower:
                # 找到原文中的实际大小写形式
                idx = text_lower.find(name.lower())
                if idx >= 0:
                    original_name = truncated_text[idx:idx+len(name)]
                    entities.append(ExtractedEntity(
                        name=original_name,
                        entity_type=entity_type,
                        confidence=0.9,
                        source_text=truncated_text[max(0,idx-20):idx+len(name)+20]
                    ))
        
        # 2. 使用spaCy提取命名实体
        doc = self.nlp(truncated_text)
        for ent in doc.ents:
            # 清理实体文本（去除前后多余字符）
            clean_name = ent.text.strip()
            # 过滤掉太短或太长的
            if len(clean_name) < 2 or len(clean_name) > 30:
                continue
            # 过滤掉纯数字
            if clean_name.isdigit():
                continue
            # 过滤掉停用词开头的错误识别（如"比如说n"）
            skip = False
            for sw in ['比如说', '比如', '就是', '其实', '然后']:
                if clean_name.startswith(sw):
                    # 尝试提取后面的部分
                    rest = clean_name[len(sw):].strip()
                    if rest and len(rest) >= 2:
                        clean_name = rest
                    else:
                        skip = True
                    break
            if skip:
                continue
                
            entity_type = self._map_spacy_label(ent.label_)
            if entity_type:
                entities.append(ExtractedEntity(
                    name=clean_name,
                    entity_type=entity_type,
                    confidence=0.8,
                    source_text=ent.sent.text if ent.sent else truncated_text[:100]
                ))
        
        # 3. 中文专名提取（引号内容、书名号内容）
        quoted = re.findall(r'[「『"\'《](.*?)[」』"\'》]', truncated_text)
        for name in quoted:
            name = name.strip()
            if 2 <= len(name) <= 20 and name.lower() not in self.stopwords:
                entities.append(ExtractedEntity(
                    name=name,
                    entity_type='ITEM' if len(name) <= 4 else 'CONCEPT',
                    confidence=0.7,
                    source_text=truncated_text[:100]
                ))
        
        # 4. 英文专有名词提取（首字母大写的词、全大写缩写）
        # 匹配如 GitHub, AI, BJD, MJD, SillyTavern 等
        english_proper = re.findall(r'\b([A-Z][a-zA-Z0-9]{1,20})\b', truncated_text)
        english_abbr = re.findall(r'\b([A-Z]{2,10})\b', truncated_text)
        for word in set(english_proper + english_abbr):
            if word.lower() not in self.stopwords and len(word) >= 2:
                # 判断类型
                if word.isupper() and len(word) <= 5:
                    etype = 'CONCEPT'  # 缩写词如 AI, BJD
                else:
                    etype = 'ORG'  # 首字母大写可能是组织/产品
                entities.append(ExtractedEntity(
                    name=word,
                    entity_type=etype,
                    confidence=0.6,
                    source_text=truncated_text[:100]
                ))
        
        # 5. 混合词提取（如 n8n, mamachapp 等小写专有名词）
        # 匹配 字母+数字 混合 或 连续小写但看起来像专有名词的
        mixed_words = re.findall(r'\b([a-z]+[0-9]+[a-z0-9]*|[0-9]+[a-z]+[a-z0-9]*)\b', truncated_text, re.IGNORECASE)
        for word in set(mixed_words):
            if word.lower() not in self.stopwords and len(word) >= 2:
                entities.append(ExtractedEntity(
                    name=word,
                    entity_type='ORG',
                    confidence=0.6,
                    source_text=truncated_text[:100]
                ))
        
        # 6. jieba 名词短语提取（补充中文实体）
        try:
            import jieba.posseg as pseg
            words = pseg.cut(truncated_text)
            for word, flag in words:
                # nr=人名, ns=地名, nt=机构, nz=其他专名, n=名词
                if flag in ('nr', 'ns', 'nt', 'nz') and len(word) >= 2:
                    if word not in self.stopwords:
                        entity_type = {
                            'nr': 'PERSON',
                            'ns': 'LOCATION', 
                            'nt': 'ORG',
                            'nz': 'CONCEPT'
                        }.get(flag, 'CONCEPT')
                        entities.append(ExtractedEntity(
                            name=word,
                            entity_type=entity_type,
                            confidence=0.65,
                            source_text=truncated_text[:100]
                        ))
        except Exception:
            pass  # jieba.posseg 可能不可用
        
        # 去重（保留置信度最高的）+ 过滤误识别
        seen: Dict[str, ExtractedEntity] = {}
        for e in entities:
            key = e.name.lower()
            # 过滤误识别词
            if e.name in self.filter_words or key in self.filter_words:
                continue
            # 过滤太短的（单字符）
            if len(e.name) < 2:
                continue
            # 过滤以"和"开头的错误分词（如"和骏河"）
            if e.name.startswith('和') and len(e.name) > 2:
                continue
            if key not in seen or e.confidence > seen[key].confidence:
                seen[key] = e
        
        return list(seen.values())
    
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
        """映射spaCy标签到我们的类型（扩展版）"""
        mapping = {
            # 人物
            'PERSON': 'PERSON',
            'PER': 'PERSON',
            # 地点
            'GPE': 'LOCATION',      # 地缘政治实体（国家、城市等）
            'LOC': 'LOCATION',      # 非GPE地点
            'FAC': 'LOCATION',      # 设施
            # 组织
            'ORG': 'ORG',
            'NORP': 'ORG',          # 国籍、宗教、政治团体
            # 物品/作品
            'PRODUCT': 'ITEM',
            'WORK_OF_ART': 'ITEM',
            'EVENT': 'CONCEPT',     # 事件
            'LAW': 'CONCEPT',       # 法律文件
            # 时间（可选保留）
            # 'DATE': 'TIME',
            # 'TIME': 'TIME',
            # 数量（通常不需要）
            # 'MONEY': 'NUMBER',
            # 'QUANTITY': 'NUMBER',
            # 'CARDINAL': 'NUMBER',
            # 'ORDINAL': 'NUMBER',
            # 'PERCENT': 'NUMBER',
        }
        return mapping.get(label, None)
