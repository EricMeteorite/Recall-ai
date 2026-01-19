"""一致性检查器 - 检测记忆中的矛盾"""

import re
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ViolationType(Enum):
    """违规类型"""
    FACT_CONFLICT = "fact_conflict"           # 事实冲突
    TIMELINE_CONFLICT = "timeline_conflict"   # 时间线冲突
    CHARACTER_CONFLICT = "character_conflict" # 角色设定冲突
    LOCATION_CONFLICT = "location_conflict"   # 地点冲突
    LOGIC_ERROR = "logic_error"               # 逻辑错误


@dataclass
class Violation:
    """违规/冲突记录"""
    type: ViolationType
    description: str
    evidence: List[str]
    severity: float  # 0-1
    suggested_resolution: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'type': self.type.value,
            'description': self.description,
            'evidence': self.evidence,
            'severity': self.severity,
            'suggested_resolution': self.suggested_resolution,
            'created_at': self.created_at
        }


@dataclass
class ConsistencyResult:
    """一致性检查结果"""
    is_consistent: bool
    violations: List[Violation] = field(default_factory=list)
    confidence: float = 1.0
    checked_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'is_consistent': self.is_consistent,
            'violations': [v.to_dict() for v in self.violations],
            'confidence': self.confidence,
            'checked_at': self.checked_at
        }


class ConsistencyChecker:
    """一致性检查器"""
    
    def __init__(self):
        # 数值模式匹配
        self.number_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(岁|年|天|米|厘米|公里|kg|斤|个|次|%)')
        self.date_pattern = re.compile(r'(\d{4})[年/-](\d{1,2})[月/-]?(\d{1,2})?')
        
        # 属性缓存：entity -> {attribute -> [(value, timestamp, source)]}
        self.entity_facts: Dict[str, Dict[str, List[Tuple[str, float, str]]]] = {}
    
    def check(self, new_content: str, existing_memories: List[Dict[str, Any]]) -> ConsistencyResult:
        """检查新内容与现有记忆的一致性"""
        violations = []
        
        # 1. 提取新内容中的事实
        new_facts = self._extract_facts(new_content)
        
        # 2. 与现有记忆比对
        for memory in existing_memories:
            memory_content = memory.get('content', memory.get('text', ''))
            memory_facts = self._extract_facts(memory_content)
            
            # 检查数值冲突
            for entity, attrs in new_facts.items():
                if entity in memory_facts:
                    for attr, new_value in attrs.items():
                        old_value = memory_facts[entity].get(attr)
                        if old_value and old_value != new_value:
                            # 发现冲突
                            violations.append(Violation(
                                type=ViolationType.FACT_CONFLICT,
                                description=f"{entity}的{attr}存在冲突：新值'{new_value}' vs 旧值'{old_value}'",
                                evidence=[new_content[:100], memory_content[:100]],
                                severity=0.7,
                                suggested_resolution=f"确认{entity}的{attr}应该是{new_value}还是{old_value}"
                            ))
        
        # 3. 时间线检查
        timeline_violations = self._check_timeline(new_content, existing_memories)
        violations.extend(timeline_violations)
        
        return ConsistencyResult(
            is_consistent=len(violations) == 0,
            violations=violations,
            confidence=0.8 if violations else 1.0
        )
    
    def _extract_facts(self, text: str) -> Dict[str, Dict[str, str]]:
        """从文本中提取事实"""
        facts: Dict[str, Dict[str, str]] = {}
        
        # 提取数值属性
        # 模式：主语 + 数值 + 单位（如"小明今年25岁"）
        patterns = [
            (r'(\w+)(?:今年|现在)?(\d+)岁', 'age'),
            (r'(\w+)(?:身高)?(\d+(?:\.\d+)?)\s*(?:cm|厘米|米)', 'height'),
            (r'(\w+)(?:体重)?(\d+(?:\.\d+)?)\s*(?:kg|公斤|斤)', 'weight'),
        ]
        
        for pattern, attr in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                entity = match[0]
                value = match[1]
                if entity not in facts:
                    facts[entity] = {}
                facts[entity][attr] = value
        
        return facts
    
    def _check_timeline(
        self,
        new_content: str,
        existing_memories: List[Dict[str, Any]]
    ) -> List[Violation]:
        """检查时间线一致性
        
        注意：当前为简化实现，只检测明显的时间顺序问题。
        完整的时间线推理需要更复杂的NLP或LLM支持，计划在v3.1实现。
        """
        violations = []
        
        # 提取新内容中的日期
        new_dates = self.date_pattern.findall(new_content)
        if not new_dates:
            return violations
        
        # 时间副词检测（声称过去发生但与已知事实冲突）
        past_indicators = ['之前', '以前', '去年', '上个月', '昨天', '曾经']
        future_indicators = ['之后', '以后', '明年', '下个月', '明天', '将来']
        
        new_has_past = any(ind in new_content for ind in past_indicators)
        new_has_future = any(ind in new_content for ind in future_indicators)
        
        # 检查与已有记忆的时间冲突
        for memory in existing_memories:
            memory_content = memory.get('content', memory.get('text', ''))
            memory_dates = self.date_pattern.findall(memory_content)
            
            if not memory_dates:
                continue
            
            # 简单冲突检测：同一日期不同时态描述
            for new_date in new_dates:
                for mem_date in memory_dates:
                    if new_date == mem_date:
                        # 同一日期，检查是否有时态冲突
                        mem_has_past = any(ind in memory_content for ind in past_indicators)
                        mem_has_future = any(ind in memory_content for ind in future_indicators)
                        
                        # 冲突：同一日期，一个说过去一个说将来
                        if (new_has_past and mem_has_future) or (new_has_future and mem_has_past):
                            violations.append(Violation(
                                type=ViolationType.TIMELINE_CONFLICT,
                                description=f"时间线冲突：日期 {'-'.join(new_date)} 的时态描述不一致",
                                evidence=[new_content[:100], memory_content[:100]],
                                severity=0.5,
                                suggested_resolution="请确认该日期是过去还是将来"
                            ))
        
        return violations
    
    def record_fact(
        self,
        entity: str,
        attribute: str,
        value: str,
        source: str
    ):
        """记录事实到缓存"""
        if entity not in self.entity_facts:
            self.entity_facts[entity] = {}
        if attribute not in self.entity_facts[entity]:
            self.entity_facts[entity][attribute] = []
        
        self.entity_facts[entity][attribute].append((value, time.time(), source))
    
    def get_conflicts(self, entity: str) -> List[str]:
        """获取某实体的冲突"""
        if entity not in self.entity_facts:
            return []
        
        conflicts = []
        for attr, values in self.entity_facts[entity].items():
            if len(values) > 1:
                unique_values = set(v[0] for v in values)
                if len(unique_values) > 1:
                    conflicts.append(f"{attr}: {unique_values}")
        
        return conflicts
    
    def get_summary(self) -> Dict[str, Any]:
        """获取一致性检查摘要"""
        total_entities = len(self.entity_facts)
        entities_with_conflicts = 0
        total_conflicts = 0
        
        for entity, attrs in self.entity_facts.items():
            has_conflict = False
            for attr, values in attrs.items():
                unique_values = set(v[0] for v in values)
                if len(unique_values) > 1:
                    has_conflict = True
                    total_conflicts += 1
            if has_conflict:
                entities_with_conflicts += 1
        
        return {
            'total_entities': total_entities,
            'entities_with_conflicts': entities_with_conflicts,
            'total_conflicts': total_conflicts,
            'health_score': 1.0 - (entities_with_conflicts / max(total_entities, 1))
        }
