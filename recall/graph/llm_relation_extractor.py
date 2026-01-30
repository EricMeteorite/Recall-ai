"""LLM 关系提取器 - Recall 4.1 增强模块

设计理念：
1. 三模式支持：RULES / ADAPTIVE / LLM
2. 复用现有 RelationExtractor 的规则逻辑
3. LLM 模式支持动态关系类型、时态信息、事实描述
4. 向后兼容：不修改现有 RelationExtractor
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from datetime import datetime

from .relation_extractor import RelationExtractor
from ..utils.llm_client import LLMClient
from ..utils.budget_manager import BudgetManager


class RelationExtractionMode(str, Enum):
    """关系提取模式"""
    RULES = "rules"           # 纯规则（默认，零成本）
    ADAPTIVE = "adaptive"     # 自适应（规则 + LLM 精炼）
    LLM = "llm"               # 纯 LLM（最高质量）


@dataclass
class ExtractedRelationV2:
    """增强版关系结构 - 兼容 Graphiti 的 Edge 模型"""
    source_id: str              # 源实体
    target_id: str              # 目标实体
    relation_type: str          # 关系类型（如 WORKS_AT, FRIENDS_WITH）
    fact: str                   # 自然语言事实描述
    source_text: str            # 原文依据
    confidence: float = 0.5     # 置信度
    valid_at: Optional[str] = None    # 事实生效时间（ISO 8601）
    invalid_at: Optional[str] = None  # 事实失效时间（ISO 8601）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relation_type': self.relation_type,
            'fact': self.fact,
            'source_text': self.source_text,
            'confidence': self.confidence,
            'valid_at': self.valid_at,
            'invalid_at': self.invalid_at,
        }
    
    def to_legacy_tuple(self) -> Tuple[str, str, str, str]:
        """转换为旧格式元组，兼容现有代码"""
        return (self.source_id, self.relation_type, self.target_id, self.source_text)


@dataclass
class LLMRelationExtractorConfig:
    """配置"""
    mode: RelationExtractionMode = RelationExtractionMode.RULES
    complexity_threshold: float = 0.5  # 自适应模式下触发 LLM 的阈值
    max_relations_per_call: int = 20   # 单次 LLM 调用最大关系数
    enable_temporal: bool = True       # 是否提取时态信息
    enable_fact_description: bool = True  # 是否生成事实描述


# LLM 提示词模板
RELATION_EXTRACTION_PROMPT = '''你是一个专业的知识图谱关系提取专家。请从以下文本中提取实体之间的关系。

## 已识别的实体列表：
{entities}

## 原始文本：
{text}

## 提取要求：
1. 只提取上述实体列表中存在的实体之间的关系
2. 关系类型使用 SCREAMING_SNAKE_CASE 格式（如 WORKS_AT, FRIENDS_WITH, LIVES_IN）
3. 为每个关系生成简洁的自然语言事实描述
4. 如果文本中包含时间信息，提取 valid_at（生效时间）和 invalid_at（失效时间）
5. 评估每个关系的置信度（0.0-1.0）

## 输出格式（JSON数组）：
[
  {{
    "source_id": "实体A",
    "target_id": "实体B",
    "relation_type": "RELATION_TYPE",
    "fact": "实体A与实体B的关系描述",
    "confidence": 0.8,
    "valid_at": "2023-01-01" 或 null,
    "invalid_at": null
  }}
]

请只输出 JSON 数组，不要输出其他内容。'''


class LLMRelationExtractor:
    """LLM 增强的关系提取器
    
    使用方式：
        # 方式1：纯规则模式（默认，零成本）
        extractor = LLMRelationExtractor()
        relations = extractor.extract(text, 0, entities)
        
        # 方式2：自适应模式（推荐）
        extractor = LLMRelationExtractor(
            llm_client=llm_client,
            config=LLMRelationExtractorConfig(mode=RelationExtractionMode.ADAPTIVE)
        )
        relations = extractor.extract(text, 0, entities)
        
        # 方式3：纯 LLM 模式（最高质量）
        extractor = LLMRelationExtractor(
            llm_client=llm_client,
            config=LLMRelationExtractorConfig(mode=RelationExtractionMode.LLM)
        )
        relations = extractor.extract(text, 0, entities)
        
    Note:
        参数顺序 (text, turn, entities) 与现有 RelationExtractor.extract() 保持一致
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        budget_manager: Optional[BudgetManager] = None,
        entity_extractor=None,
        config: Optional[LLMRelationExtractorConfig] = None
    ):
        self.llm_client = llm_client
        self.budget_manager = budget_manager
        self.config = config or LLMRelationExtractorConfig()
        
        # 复用现有的规则提取器
        self._rule_extractor = RelationExtractor(entity_extractor=entity_extractor)
    
    def extract(
        self,
        text: str,
        turn: int = 0,
        entities: Optional[List] = None
    ) -> List[ExtractedRelationV2]:
        """提取关系
        
        Args:
            text: 原始文本
            turn: 轮次
            entities: 已提取的实体列表
        
        Returns:
            List[ExtractedRelationV2]: 提取的关系列表
        
        Note:
            参数顺序与 RelationExtractor.extract() 保持一致，确保向后兼容
        """
        mode = self.config.mode
        
        if mode == RelationExtractionMode.RULES:
            return self._extract_by_rules(text, entities, turn)
        elif mode == RelationExtractionMode.LLM:
            return self._extract_by_llm(text, entities)
        else:  # ADAPTIVE
            return self._extract_adaptive(text, entities, turn)
    
    def _extract_by_rules(
        self,
        text: str,
        entities: Optional[List],
        turn: int
    ) -> List[ExtractedRelationV2]:
        """规则模式提取"""
        # 复用现有逻辑
        raw_relations = self._rule_extractor.extract(text, turn, entities)
        
        # 转换为新格式
        return [
            ExtractedRelationV2(
                source_id=source,
                target_id=target,
                relation_type=rel_type,
                fact=f"{source} {rel_type} {target}",
                source_text=src_text,
                confidence=0.5 if rel_type == 'MENTIONED_WITH' else 0.8
            )
            for source, rel_type, target, src_text in raw_relations
        ]
    
    def _extract_by_llm(
        self,
        text: str,
        entities: Optional[List]
    ) -> List[ExtractedRelationV2]:
        """LLM 模式提取"""
        if not self.llm_client:
            # 降级到规则模式
            return self._extract_by_rules(text, entities, 0)
        
        # 检查预算（使用正确的 can_afford 方法）
        if self.budget_manager and not self.budget_manager.can_afford(0.01, operation="relation_extraction"):
            return self._extract_by_rules(text, entities, 0)
        
        # 准备实体列表字符串
        entity_names = self._get_entity_names(entities)
        entities_str = ", ".join(entity_names) if entity_names else "（未提供实体列表）"
        
        # 构建提示词
        prompt = RELATION_EXTRACTION_PROMPT.format(
            entities=entities_str,
            text=text[:3000]  # 限制长度
        )
        
        try:
            # 使用 complete() 方法（接受字符串 prompt）
            # 从环境变量读取配置的最大 tokens，或根据实体数量动态计算
            import os
            config_max_tokens = int(os.environ.get('LLM_RELATION_MAX_TOKENS', '4000'))
            entity_count = len(entity_names) if entity_names else 10
            # 动态计算：每实体约80 tokens，但不超过配置的上限
            dynamic_tokens = min(config_max_tokens, max(1000, entity_count * 80))
            
            response = self.llm_client.complete(prompt, max_tokens=dynamic_tokens)
            relations = self._parse_llm_response(response, text)
            
            # 记录成本（使用正确的参数格式）
            if self.budget_manager:
                self.budget_manager.record_usage(
                    operation="relation_extraction",
                    tokens_in=len(prompt) // 4,
                    tokens_out=len(response) // 4,
                    model=self.llm_client.model
                )
            
            return relations
        except Exception as e:
            print(f"[LLMRelationExtractor] LLM 提取失败，降级到规则模式: {e}")
            return self._extract_by_rules(text, entities, 0)
    
    def _extract_adaptive(
        self,
        text: str,
        entities: Optional[List],
        turn: int
    ) -> List[ExtractedRelationV2]:
        """自适应模式：规则 + LLM 精炼"""
        # 1. 先用规则提取
        rule_relations = self._extract_by_rules(text, entities, turn)
        
        # 2. 评估文本复杂度
        complexity = self._evaluate_complexity(text, entities)
        
        # 3. 如果复杂度高且有 LLM，使用 LLM 补充
        if complexity > self.config.complexity_threshold and self.llm_client:
            llm_relations = self._extract_by_llm(text, entities)
            # 合并去重
            return self._merge_relations(rule_relations, llm_relations)
        
        return rule_relations
    
    def _evaluate_complexity(self, text: str, entities: Optional[List]) -> float:
        """评估文本复杂度"""
        score = 0.0
        
        # 1. 文本长度
        if len(text) > 500:
            score += 0.2
        if len(text) > 1000:
            score += 0.1
        
        # 2. 实体数量
        entity_count = len(self._get_entity_names(entities))
        if entity_count > 5:
            score += 0.2
        if entity_count > 10:
            score += 0.1
        
        # 3. 句子复杂度（分号、逗号数量）
        complex_punct = len(re.findall(r'[;；,，]', text))
        if complex_punct > 10:
            score += 0.2
        
        # 4. 时态词汇
        temporal_words = ['从', '到', '开始', '结束', '之前', '之后', '年', '月', '日']
        for word in temporal_words:
            if word in text:
                score += 0.05
        
        return min(score, 1.0)
    
    def _get_entity_names(self, entities: Optional[List]) -> List[str]:
        """统一获取实体名列表"""
        if not entities:
            return []
        
        names = []
        for e in entities:
            if hasattr(e, 'name'):
                names.append(e.name)
            elif isinstance(e, str):
                names.append(e)
            elif isinstance(e, dict) and 'name' in e:
                names.append(e['name'])
        return names
    
    def _parse_llm_response(self, response: str, source_text: str) -> List[ExtractedRelationV2]:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\[[\s\S]*\]', response)
            
            # 如果没找到完整的 JSON 数组，尝试修复被截断的 JSON
            if not json_match:
                # 检查是否是被截断的 JSON（以 [ 开头但没有 ]）
                if response.strip().startswith('['):
                    # 尝试修复：找到最后一个完整的对象，然后闭合数组
                    truncated_json = response.strip()
                    # 找到最后一个 }
                    last_brace = truncated_json.rfind('}')
                    if last_brace > 0:
                        # 截取到最后一个完整对象，并闭合数组
                        truncated_json = truncated_json[:last_brace + 1] + ']'
                        print(f"[LLMRelationExtractor] JSON 被截断，尝试修复...")
                        json_match = re.search(r'\[[\s\S]*\]', truncated_json)
            
            if json_match:
                data = json.loads(json_match.group())
                print(f"[LLMRelationExtractor] 解析成功, 原始关系数={len(data)}")
                relations = [
                    ExtractedRelationV2(
                        source_id=item.get('source_id', ''),
                        target_id=item.get('target_id', ''),
                        relation_type=item.get('relation_type', 'RELATED'),
                        fact=item.get('fact', ''),
                        source_text=source_text[:200],
                        confidence=float(item.get('confidence', 0.7)),
                        valid_at=item.get('valid_at'),
                        invalid_at=item.get('invalid_at'),
                    )
                    for item in data
                    if item.get('source_id') and item.get('target_id')
                ]
                print(f"[LLMRelationExtractor] 有效关系数={len(relations)}")
                return relations
            else:
                print(f"[LLMRelationExtractor] 未找到 JSON 数组, response前200字符: {response[:200]}")
        except (json.JSONDecodeError, Exception) as e:
            print(f"[LLMRelationExtractor] 解析失败: {e}, response前200字符: {response[:200]}")
        
        return []
    
    def _merge_relations(
        self,
        rule_relations: List[ExtractedRelationV2],
        llm_relations: List[ExtractedRelationV2]
    ) -> List[ExtractedRelationV2]:
        """合并规则和 LLM 提取的关系"""
        seen = set()
        merged = []
        
        # LLM 结果优先（质量更高）
        for rel in llm_relations:
            key = (rel.source_id, rel.target_id)
            if key not in seen:
                seen.add(key)
                merged.append(rel)
        
        # 补充规则结果
        for rel in rule_relations:
            key = (rel.source_id, rel.target_id)
            if key not in seen:
                seen.add(key)
                merged.append(rel)
        
        return merged
    
    # 兼容旧接口
    def extract_legacy(
        self,
        text: str,
        turn: int = 0,
        entities: Optional[List] = None
    ) -> List[Tuple[str, str, str, str]]:
        """兼容旧接口，返回元组格式"""
        relations = self.extract(text, turn, entities)
        return [rel.to_legacy_tuple() for rel in relations]
