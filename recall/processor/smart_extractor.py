"""智能抽取器 - Recall 4.0 Phase 2

设计理念：
1. 三模式自适应：Local（纯本地）、Hybrid（混合）、LLM（纯 LLM）
2. 复杂度评估：根据文本复杂度自动选择策略
3. 成本控制：集成预算管理，避免超支
4. 向后兼容：不破坏现有 EntityExtractor 功能
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum

from .entity_extractor import EntityExtractor, ExtractedEntity
from ..utils.llm_client import LLMClient
from ..utils.budget_manager import BudgetManager, BudgetConfig


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


class ExtractionMode(str, Enum):
    """抽取模式"""
    RULES = "rules"           # 纯规则：spaCy + jieba + 规则
    ADAPTIVE = "adaptive"     # 自适应：规则初筛 + LLM 精炼（默认）
    LLM = "llm"               # 纯 LLM：最高质量
    
    @classmethod
    def _missing_(cls, value):
        """向后兼容：映射旧值到新值"""
        legacy_map = {
            'local': cls.RULES,
            'hybrid': cls.ADAPTIVE,
            'llm_full': cls.LLM,
        }
        if isinstance(value, str):
            return legacy_map.get(value.lower())
        return None


# 向后兼容别名（支持 ExtractionMode.LOCAL 等旧用法）
ExtractionMode.LOCAL = ExtractionMode.RULES
ExtractionMode.HYBRID = ExtractionMode.ADAPTIVE
ExtractionMode.LLM_FULL = ExtractionMode.LLM


@dataclass
class ExtractedRelation:
    """抽取的关系"""
    subject: str
    predicate: str
    object: str
    confidence: float = 0.5
    source_text: str = ""
    temporal_info: Optional[str] = None  # 时态信息（如"从2023年开始"）


@dataclass
class ExtractionResult:
    """抽取结果"""
    entities: List[ExtractedEntity]
    relations: List[ExtractedRelation]
    temporal_markers: List[Dict[str, Any]]  # 时态标记
    keywords: List[str]
    
    # 元信息
    mode_used: ExtractionMode = ExtractionMode.RULES
    complexity_score: float = 0.0
    llm_used: bool = False
    cost: float = 0.0
    latency_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'entities': [
                {
                    'name': e.name,
                    'entity_type': e.entity_type,
                    'confidence': e.confidence,
                    'source_text': e.source_text
                }
                for e in self.entities
            ],
            'relations': [asdict(r) for r in self.relations],
            'temporal_markers': self.temporal_markers,
            'keywords': self.keywords,
            'mode_used': self.mode_used.value,
            'complexity_score': self.complexity_score,
            'llm_used': self.llm_used,
            'cost': self.cost,
            'latency_ms': self.latency_ms
        }


@dataclass
class SmartExtractorConfig:
    """智能抽取器配置"""
    mode: ExtractionMode = ExtractionMode.ADAPTIVE
    complexity_threshold: float = 0.6       # 复杂度阈值（超过此值使用 LLM）
    max_text_length: int = 10000            # 最大处理文本长度
    enable_relation_extraction: bool = True # 是否抽取关系
    enable_temporal_detection: bool = True  # 是否检测时态
    
    @classmethod
    def rules_only(cls) -> 'SmartExtractorConfig':
        """纯规则模式配置"""
        return cls(mode=ExtractionMode.RULES)
    
    @classmethod
    def adaptive(cls, threshold: float = 0.6) -> 'SmartExtractorConfig':
        """自适应模式配置"""
        return cls(mode=ExtractionMode.ADAPTIVE, complexity_threshold=threshold)
    
    @classmethod
    def llm(cls) -> 'SmartExtractorConfig':
        """纯 LLM 模式配置"""
        return cls(mode=ExtractionMode.LLM)
    
    # 向后兼容别名
    @classmethod
    def local_only(cls) -> 'SmartExtractorConfig':
        """[已弃用] 请使用 rules_only()"""
        return cls.rules_only()
    
    @classmethod
    def hybrid(cls, threshold: float = 0.6) -> 'SmartExtractorConfig':
        """[已弃用] 请使用 adaptive()"""
        return cls.adaptive(threshold)
    
    @classmethod
    def llm_full(cls) -> 'SmartExtractorConfig':
        """[已弃用] 请使用 llm()"""
        return cls.llm()


class SmartExtractor:
    """智能抽取器 - 三模式自适应
    
    功能：
    1. 实体抽取（Local/LLM）
    2. 关系抽取（Local/LLM）
    3. 时态检测（规则 + LLM）
    4. 复杂度评估
    5. 成本控制
    
    使用方式：
        extractor = SmartExtractor(llm_client=llm_client)
        result = extractor.extract("Alice joined OpenAI in 2023")
    """
    
    # 时态关键词（用于规则检测）
    TEMPORAL_KEYWORDS_ZH = {
        '从', '自从', '开始', '结束', '直到', '之前', '之后', '期间',
        '年', '月', '日', '今天', '昨天', '明天', '现在', '以前', '以后',
        '一直', '已经', '曾经', '将要', '正在'
    }
    
    TEMPORAL_KEYWORDS_EN = {
        'from', 'since', 'until', 'before', 'after', 'during', 'when',
        'started', 'ended', 'began', 'finished', 'now', 'currently',
        'previously', 'formerly', 'recently', 'already', 'still'
    }
    
    # 关系动词模式（用于规则抽取）
    RELATION_PATTERNS = [
        # 中文
        (r'(.{2,10})是(.{2,20})的(.{2,10})', 'is_a'),
        (r'(.{2,10})在(.{2,20})工作', 'works_at'),
        (r'(.{2,10})住在(.{2,20})', 'lives_in'),
        (r'(.{2,10})喜欢(.{2,20})', 'likes'),
        (r'(.{2,10})和(.{2,10})是(.{2,10})', 'relationship'),
        # 英文
        (r'(\w+)\s+is\s+(?:a|an|the)\s+(\w+)', 'is_a'),
        (r'(\w+)\s+works?\s+(?:at|for)\s+(\w+)', 'works_at'),
        (r'(\w+)\s+lives?\s+in\s+(\w+)', 'lives_in'),
        (r'(\w+)\s+(?:likes?|loves?)\s+(\w+)', 'likes'),
    ]
    
    # LLM 抽取 Prompt
    EXTRACTION_PROMPT = '''请从以下文本中抽取实体、关系和时态信息。

文本：
{text}

请以 JSON 格式返回：
{{
  "entities": [
    {{"name": "实体名", "type": "PERSON/ORG/LOCATION/ITEM/CONCEPT", "confidence": 0.9}}
  ],
  "relations": [
    {{"subject": "主体", "predicate": "关系类型", "object": "客体", "temporal": "时态信息（可选）"}}
  ],
  "temporal_markers": [
    {{"text": "原文片段", "type": "START/END/DURATION/POINT", "normalized": "标准化时间"}}
  ]
}}

注意：
1. 只抽取明确提到的实体和关系
2. 时态信息包括：开始时间、结束时间、持续时间、时间点
3. 置信度反映抽取的确定性
4. 如果没有相关信息，对应数组为空'''

    def __init__(
        self,
        config: Optional[SmartExtractorConfig] = None,
        local_extractor: Optional[EntityExtractor] = None,
        llm_client: Optional[LLMClient] = None,
        budget_manager: Optional[BudgetManager] = None
    ):
        """初始化智能抽取器
        
        Args:
            config: 抽取器配置
            local_extractor: 本地实体抽取器（复用现有）
            llm_client: LLM 客户端
            budget_manager: 预算管理器
        """
        self.config = config or SmartExtractorConfig()
        self.local_extractor = local_extractor or EntityExtractor()
        self.llm_client = llm_client
        self.budget_manager = budget_manager
        
        # 编译关系模式
        self._relation_patterns = [
            (re.compile(pattern, re.IGNORECASE), rel_type)
            for pattern, rel_type in self.RELATION_PATTERNS
        ]
    
    def extract(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        force_mode: Optional[ExtractionMode] = None
    ) -> ExtractionResult:
        """执行智能抽取
        
        Args:
            text: 要抽取的文本
            context: 上下文信息（可选）
            force_mode: 强制使用的模式（忽略自适应）
            
        Returns:
            ExtractionResult: 抽取结果
        """
        start_time = time.time()
        
        # 文本预处理
        text = self._preprocess(text)
        if not text:
            return ExtractionResult(
                entities=[], relations=[], temporal_markers=[], keywords=[],
                mode_used=ExtractionMode.RULES, latency_ms=0
            )
        
        # 确定使用的模式
        mode = force_mode or self.config.mode
        complexity = 0.0
        
        # 1. 始终执行本地抽取（免费、快速）
        local_result = self._local_extract(text)
        
        # 如果是纯本地模式，直接返回
        if mode == ExtractionMode.RULES:
            local_result.mode_used = ExtractionMode.RULES
            local_result.latency_ms = (time.time() - start_time) * 1000
            return local_result
        
        # 2. 评估复杂度
        complexity = self._assess_complexity(text, local_result)
        local_result.complexity_score = complexity
        
        # 3. 决策是否需要 LLM
        need_llm = (
            mode == ExtractionMode.LLM or
            (mode == ExtractionMode.ADAPTIVE and complexity >= self.config.complexity_threshold)
        )
        
        # 4. 检查预算
        if need_llm and self.budget_manager:
            # 估算 LLM 调用成本
            estimated_tokens = len(text) // 4 + 200  # 粗略估算
            estimated_cost = self.budget_manager.estimate_cost(
                tokens_in=estimated_tokens,
                tokens_out=200
            )
            if not self.budget_manager.can_afford(estimated_cost, operation="extraction"):
                # 预算不足，降级到本地模式
                need_llm = False
                _safe_print("[SmartExtractor] 预算不足，降级到本地模式")
        
        # 5. 执行 LLM 抽取（如果需要且可用）
        if need_llm and self.llm_client:
            llm_result = self._llm_extract(text, local_result, context)
            if llm_result:
                # 合并结果
                merged = self._merge_results(local_result, llm_result)
                merged.mode_used = mode
                merged.llm_used = True
                merged.latency_ms = (time.time() - start_time) * 1000
                return merged
        
        # 返回本地结果
        local_result.mode_used = mode
        local_result.latency_ms = (time.time() - start_time) * 1000
        return local_result
    
    def _preprocess(self, text: str) -> str:
        """文本预处理"""
        if not text:
            return ""
        
        # 截断过长文本
        if len(text) > self.config.max_text_length:
            text = text[:self.config.max_text_length]
        
        # 清理多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _local_extract(self, text: str) -> ExtractionResult:
        """本地抽取（使用现有 EntityExtractor + 规则）"""
        # 实体抽取
        entities = self.local_extractor.extract(text)
        
        # 关键词抽取
        keywords = self.local_extractor.extract_keywords(text)
        
        # 关系抽取（规则匹配）
        relations = []
        if self.config.enable_relation_extraction:
            relations = self._extract_relations_by_rules(text, entities)
        
        # 时态检测（规则匹配）
        temporal_markers = []
        if self.config.enable_temporal_detection:
            temporal_markers = self._detect_temporal_markers(text)
        
        return ExtractionResult(
            entities=entities,
            relations=relations,
            temporal_markers=temporal_markers,
            keywords=keywords
        )
    
    def _extract_relations_by_rules(
        self,
        text: str,
        entities: List[ExtractedEntity]
    ) -> List[ExtractedRelation]:
        """使用规则抽取关系"""
        relations = []
        entity_names = {e.name.lower() for e in entities}
        
        for pattern, rel_type in self._relation_patterns:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) >= 2:
                    subject = groups[0].strip()
                    obj = groups[1].strip() if len(groups) > 1 else ""
                    
                    # 验证主体和客体是否为已知实体
                    # 这里放宽条件，只要有一个是已知实体就记录
                    if subject.lower() in entity_names or obj.lower() in entity_names:
                        relations.append(ExtractedRelation(
                            subject=subject,
                            predicate=rel_type,
                            object=obj,
                            confidence=0.6,
                            source_text=match.group(0)
                        ))
        
        return relations
    
    def _detect_temporal_markers(self, text: str) -> List[Dict[str, Any]]:
        """检测时态标记"""
        markers = []
        
        # 中文日期模式
        zh_date_patterns = [
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日?', 'POINT'),
            (r'(\d{4})年(\d{1,2})月', 'POINT'),
            (r'(\d{4})年', 'POINT'),
            (r'(从|自)(.{2,20})(开始|起)', 'START'),
            (r'(到|至|直到)(.{2,20})(结束|为止)?', 'END'),
            (r'(.{2,10})(期间|之间)', 'DURATION'),
        ]
        
        # 英文日期模式
        en_date_patterns = [
            (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}', 'POINT'),
            (r'\d{1,2}/\d{1,2}/\d{4}', 'POINT'),
            (r'\d{4}-\d{2}-\d{2}', 'POINT'),
            (r'(since|from)\s+(.{2,20})', 'START'),
            (r'(until|to|till)\s+(.{2,20})', 'END'),
            (r'(during|between)\s+(.{2,20})', 'DURATION'),
        ]
        
        all_patterns = zh_date_patterns + en_date_patterns
        
        for pattern, marker_type in all_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                markers.append({
                    'text': match.group(0),
                    'type': marker_type,
                    'start': match.start(),
                    'end': match.end()
                })
        
        # 检测时态关键词
        for keyword in self.TEMPORAL_KEYWORDS_ZH | self.TEMPORAL_KEYWORDS_EN:
            if keyword in text.lower():
                # 找到包含关键词的上下文
                idx = text.lower().find(keyword)
                context_start = max(0, idx - 10)
                context_end = min(len(text), idx + len(keyword) + 20)
                markers.append({
                    'text': text[context_start:context_end],
                    'type': 'KEYWORD',
                    'keyword': keyword,
                    'start': idx,
                    'end': idx + len(keyword)
                })
        
        # 去重
        seen = set()
        unique_markers = []
        for m in markers:
            key = (m['text'], m['type'])
            if key not in seen:
                seen.add(key)
                unique_markers.append(m)
        
        return unique_markers
    
    def _assess_complexity(
        self,
        text: str,
        local_result: ExtractionResult
    ) -> float:
        """评估文本复杂度
        
        返回 0-1 的分数，越高越复杂，越需要 LLM
        """
        score = 0.0
        
        # 1. 长度因素
        if len(text) > 500:
            score += 0.15
        if len(text) > 1000:
            score += 0.15
        
        # 2. 实体密度
        entity_count = len(local_result.entities)
        entity_density = entity_count / max(len(text) / 100, 1)
        if entity_density > 0.5:
            score += 0.2
        
        # 3. 关系复杂度
        if entity_count > 3:
            score += 0.15
        if entity_count > 5:
            score += 0.1
        
        # 4. 时态标记
        if local_result.temporal_markers:
            score += 0.15
        
        # 5. 本地抽取置信度
        if local_result.entities:
            avg_confidence = sum(e.confidence for e in local_result.entities) / len(local_result.entities)
            if avg_confidence < 0.6:
                score += 0.2
        
        # 6. 句子结构复杂度（简单启发式）
        sentence_count = len(re.split(r'[.!?。！？]', text))
        if sentence_count > 5:
            score += 0.1
        
        return min(1.0, score)
    
    def _llm_extract(
        self,
        text: str,
        local_result: ExtractionResult,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[ExtractionResult]:
        """使用 LLM 抽取"""
        if not self.llm_client:
            return None
        
        try:
            prompt = self.EXTRACTION_PROMPT.format(text=text)
            
            response = self.llm_client.complete(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.1
            )
            
            # 解析 JSON 响应
            import json
            
            # 尝试提取 JSON 部分
            json_str = response
            if '```json' in response:
                json_str = response.split('```json')[1].split('```')[0]
            elif '```' in response:
                json_str = response.split('```')[1].split('```')[0]
            
            data = json.loads(json_str.strip())
            
            # 转换为 ExtractionResult
            entities = []
            for e in data.get('entities', []):
                entities.append(ExtractedEntity(
                    name=e.get('name', ''),
                    entity_type=e.get('type', 'UNKNOWN'),
                    confidence=e.get('confidence', 0.8),
                    source_text=text[:100]
                ))
            
            relations = []
            for r in data.get('relations', []):
                relations.append(ExtractedRelation(
                    subject=r.get('subject', ''),
                    predicate=r.get('predicate', ''),
                    object=r.get('object', ''),
                    confidence=0.8,
                    temporal_info=r.get('temporal')
                ))
            
            # 记录预算使用
            if self.budget_manager:
                self.budget_manager.record_usage(
                    operation="extraction",
                    tokens_in=len(text) // 4,
                    tokens_out=len(response) // 4,
                    model=self.llm_client.model
                )
            
            return ExtractionResult(
                entities=entities,
                relations=relations,
                temporal_markers=data.get('temporal_markers', []),
                keywords=local_result.keywords,  # 关键词用本地结果
                llm_used=True
            )
        
        except Exception as e:
            _safe_print(f"[SmartExtractor] LLM 抽取失败: {e}")
            return None
    
    def _merge_results(
        self,
        local_result: ExtractionResult,
        llm_result: ExtractionResult
    ) -> ExtractionResult:
        """合并本地和 LLM 抽取结果"""
        # 实体去重合并（以 LLM 结果为主，补充本地结果）
        merged_entities = list(llm_result.entities)
        llm_entity_names = {e.name.lower() for e in llm_result.entities}
        
        for e in local_result.entities:
            if e.name.lower() not in llm_entity_names:
                # 降低本地结果的置信度
                e.confidence *= 0.8
                merged_entities.append(e)
        
        # 关系合并
        merged_relations = list(llm_result.relations)
        llm_rel_keys = {(r.subject.lower(), r.predicate, r.object.lower()) for r in llm_result.relations}
        
        for r in local_result.relations:
            key = (r.subject.lower(), r.predicate, r.object.lower())
            if key not in llm_rel_keys:
                r.confidence *= 0.7
                merged_relations.append(r)
        
        # 时态标记合并
        merged_temporal = list(llm_result.temporal_markers)
        seen_texts = {m.get('text', '') for m in merged_temporal}
        for m in local_result.temporal_markers:
            if m.get('text', '') not in seen_texts:
                merged_temporal.append(m)
        
        # 关键词合并
        merged_keywords = list(set(local_result.keywords + llm_result.keywords))
        
        return ExtractionResult(
            entities=merged_entities,
            relations=merged_relations,
            temporal_markers=merged_temporal,
            keywords=merged_keywords,
            cost=llm_result.cost,
            llm_used=True
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取抽取器统计信息"""
        stats = {
            'mode': self.config.mode.value,
            'complexity_threshold': self.config.complexity_threshold,
            'llm_available': self.llm_client is not None,
        }
        
        if self.budget_manager:
            stats['budget'] = self.budget_manager.get_stats()
        
        return stats
