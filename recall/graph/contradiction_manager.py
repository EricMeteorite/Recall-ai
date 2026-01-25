"""矛盾检测管理器 - 独立模块

设计理念：
1. 独立于 TemporalKnowledgeGraph，可单独使用
2. 支持多种检测策略（规则 + LLM）
3. 支持多种解决策略（取代/共存/拒绝/手动）
4. 持久化存储待处理矛盾
"""

from __future__ import annotations

import os
import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable, TYPE_CHECKING
from enum import Enum

from ..models.temporal import (
    TemporalFact, Contradiction, ContradictionType, 
    ResolutionStrategy, ResolutionResult
)

if TYPE_CHECKING:
    from ..utils.llm_client import LLMClient


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


class DetectionStrategy(str, Enum):
    """检测策略"""
    RULE = "rule"             # 仅规则检测
    LLM = "llm"               # 仅 LLM 检测
    MIXED = "mixed"           # 混合：规则初筛 + LLM 确认
    AUTO = "auto"             # 自动：简单矛盾用规则，复杂矛盾用 LLM
    
    @classmethod
    def _missing_(cls, value):
        """向后兼容：映射旧值到新值"""
        legacy_map = {
            'rule_only': cls.RULE,
            'llm_only': cls.LLM,
            'hybrid': cls.MIXED,
        }
        if isinstance(value, str):
            return legacy_map.get(value.lower())
        return None


# 向后兼容别名（支持 DetectionStrategy.RULE_ONLY 等旧用法）
DetectionStrategy.RULE_ONLY = DetectionStrategy.RULE
DetectionStrategy.LLM_ONLY = DetectionStrategy.LLM
DetectionStrategy.HYBRID = DetectionStrategy.MIXED


@dataclass
class ContradictionRecord:
    """矛盾记录（用于持久化）"""
    contradiction: Contradiction
    detected_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution: Optional[ResolutionStrategy] = None
    resolver: str = ""          # 解决者（system | user | llm）
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'contradiction': {
                'uuid': self.contradiction.uuid,
                'old_fact_uuid': self.contradiction.old_fact.uuid,
                'new_fact_uuid': self.contradiction.new_fact.uuid,
                'contradiction_type': self.contradiction.contradiction_type.value,
                'confidence': self.contradiction.confidence,
            },
            'detected_at': self.detected_at.isoformat(),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution': self.resolution.value if self.resolution else None,
            'resolver': self.resolver,
            'notes': self.notes
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], fact_lookup: Callable[[str], Optional[TemporalFact]] = None) -> 'ContradictionRecord':
        """从字典创建（需要 fact_lookup 函数来获取实际的 Fact 对象）"""
        c_data = data['contradiction']
        
        # 创建占位 Fact（如果没有 lookup 函数）
        old_fact = TemporalFact(uuid=c_data['old_fact_uuid'])
        new_fact = TemporalFact(uuid=c_data['new_fact_uuid'])
        
        if fact_lookup:
            old_fact = fact_lookup(c_data['old_fact_uuid']) or old_fact
            new_fact = fact_lookup(c_data['new_fact_uuid']) or new_fact
        
        contradiction = Contradiction(
            uuid=c_data['uuid'],
            old_fact=old_fact,
            new_fact=new_fact,
            contradiction_type=ContradictionType(c_data['contradiction_type']),
            confidence=c_data.get('confidence', 0.5)
        )
        
        return cls(
            contradiction=contradiction,
            detected_at=datetime.fromisoformat(data['detected_at']),
            resolved_at=datetime.fromisoformat(data['resolved_at']) if data.get('resolved_at') else None,
            resolution=ResolutionStrategy(data['resolution']) if data.get('resolution') else None,
            resolver=data.get('resolver', ''),
            notes=data.get('notes', '')
        )


class ContradictionManager:
    """矛盾检测管理器
    
    功能：
    1. 检测事实之间的矛盾
    2. 分类矛盾类型
    3. 支持多种解决策略
    4. 持久化矛盾记录
    5. 可选 LLM 辅助检测
    
    使用方式：
        manager = ContradictionManager(data_path)
        
        # 检测矛盾
        contradictions = manager.detect(new_fact, existing_facts)
        
        # 解决矛盾
        for c in contradictions:
            result = manager.resolve(c, ResolutionStrategy.SUPERSEDE)
    """
    
    def __init__(
        self,
        data_path: str,
        llm_client: Optional['LLMClient'] = None,
        strategy: DetectionStrategy = DetectionStrategy.RULE,
        auto_resolve: bool = False,
        default_resolution: ResolutionStrategy = ResolutionStrategy.MANUAL
    ):
        """初始化矛盾管理器
        
        Args:
            data_path: 数据存储路径
            llm_client: 可选的 LLM 客户端
            strategy: 检测策略
            auto_resolve: 是否自动解决（低置信度矛盾）
            default_resolution: 默认解决策略
        """
        self.data_path = data_path
        self.llm_client = llm_client
        self.strategy = strategy
        self.auto_resolve = auto_resolve
        self.default_resolution = default_resolution
        
        # 存储
        self.storage_dir = os.path.join(data_path, 'contradictions')
        self.records_file = os.path.join(self.storage_dir, 'records.json')
        
        # 内存存储
        self.pending: List[ContradictionRecord] = []    # 待处理
        self.resolved: List[ContradictionRecord] = []   # 已解决
        
        # 规则库
        self._rules: List[Callable[[TemporalFact, TemporalFact], Optional[ContradictionType]]] = []
        self._register_default_rules()
        
        # 加载
        self._load()
    
    def _register_default_rules(self):
        """注册默认检测规则"""
        
        # 规则1：同主体、同谓词、不同客体 = 直接矛盾
        def rule_direct_conflict(old: TemporalFact, new: TemporalFact) -> Optional[ContradictionType]:
            if old.subject == new.subject and old.predicate == new.predicate:
                if old.object != new.object:
                    # 检查时间重叠
                    if self._time_overlaps(old, new):
                        return ContradictionType.DIRECT
            return None
        
        # 规则2：时态冲突
        def rule_temporal_conflict(old: TemporalFact, new: TemporalFact) -> Optional[ContradictionType]:
            if old.subject == new.subject and old.predicate == new.predicate:
                if old.object == new.object:
                    # 同一事实但时间范围冲突
                    if self._time_conflicts(old, new):
                        return ContradictionType.TEMPORAL
            return None
        
        # 规则3：互斥谓词（如 LOVES vs HATES）
        def rule_exclusive_predicates(old: TemporalFact, new: TemporalFact) -> Optional[ContradictionType]:
            exclusive_pairs = [
                ('LOVES', 'HATES'),
                ('IS_FRIEND_OF', 'IS_ENEMY_OF'),
                ('ALIVE', 'DEAD'),
                ('MARRIED_TO', 'DIVORCED_FROM'),
            ]
            
            if old.subject == new.subject and old.object == new.object:
                for p1, p2 in exclusive_pairs:
                    if (old.predicate == p1 and new.predicate == p2) or \
                       (old.predicate == p2 and new.predicate == p1):
                        if self._time_overlaps(old, new):
                            return ContradictionType.LOGICAL
            return None
        
        self._rules.extend([rule_direct_conflict, rule_temporal_conflict, rule_exclusive_predicates])
    
    def _time_overlaps(self, fact1: TemporalFact, fact2: TemporalFact) -> bool:
        """检查两个事实的有效时间是否重叠"""
        start1 = fact1.valid_from or datetime.min
        end1 = fact1.valid_until or datetime.max
        start2 = fact2.valid_from or datetime.min
        end2 = fact2.valid_until or datetime.max
        
        return not (end1 < start2 or end2 < start1)
    
    def _time_conflicts(self, fact1: TemporalFact, fact2: TemporalFact) -> bool:
        """检查时间范围是否冲突（非正常重叠）"""
        # 如果都没有时间范围，不算冲突
        if not fact1.valid_from and not fact2.valid_from:
            return False
        
        # 如果一个有时间范围，另一个没有，可能冲突
        if bool(fact1.valid_from) != bool(fact2.valid_from):
            return True
        
        return False
    
    def _load(self):
        """加载矛盾记录"""
        if not os.path.exists(self.records_file):
            return
        
        try:
            with open(self.records_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for item in data.get('pending', []):
                record = ContradictionRecord.from_dict(item)
                self.pending.append(record)
            
            for item in data.get('resolved', []):
                record = ContradictionRecord.from_dict(item)
                self.resolved.append(record)
                
        except Exception as e:
            _safe_print(f"[ContradictionManager] 加载失败: {e}")
    
    def _save(self):
        """保存矛盾记录"""
        os.makedirs(self.storage_dir, exist_ok=True)
        
        data = {
            'pending': [r.to_dict() for r in self.pending],
            'resolved': [r.to_dict() for r in self.resolved],
            'version': '4.0'
        }
        
        with open(self.records_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_rule(self, rule: Callable[[TemporalFact, TemporalFact], Optional[ContradictionType]]):
        """添加自定义检测规则
        
        Args:
            rule: 规则函数，接收两个事实，返回矛盾类型或 None
        """
        self._rules.append(rule)
    
    def detect(
        self,
        new_fact: TemporalFact,
        existing_facts: List[TemporalFact],
        context: Optional[str] = None
    ) -> List[Contradiction]:
        """检测矛盾
        
        Args:
            new_fact: 新事实
            existing_facts: 现有事实列表
            context: 可选的上下文（用于 LLM）
        
        Returns:
            检测到的矛盾列表
        """
        contradictions = []
        
        for old_fact in existing_facts:
            if old_fact.uuid == new_fact.uuid:
                continue
            
            # 跳过已失效的事实
            if old_fact.expired_at:
                continue
            
            contradiction = self._detect_single(old_fact, new_fact, context)
            if contradiction:
                contradictions.append(contradiction)
        
        return contradictions
    
    def _detect_single(
        self,
        old_fact: TemporalFact,
        new_fact: TemporalFact,
        context: Optional[str] = None
    ) -> Optional[Contradiction]:
        """检测两个事实之间的矛盾"""
        
        # 策略1：仅规则
        if self.strategy == DetectionStrategy.RULE:
            return self._detect_by_rules(old_fact, new_fact)
        
        # 策略2：仅 LLM
        if self.strategy == DetectionStrategy.LLM:
            if self.llm_client:
                return self._detect_by_llm(old_fact, new_fact, context)
            return None
        
        # 策略3：混合
        if self.strategy == DetectionStrategy.MIXED:
            # 先规则检测
            rule_result = self._detect_by_rules(old_fact, new_fact)
            if rule_result:
                # 如果有 LLM，确认一下
                if self.llm_client:
                    llm_result = self._detect_by_llm(old_fact, new_fact, context)
                    if llm_result:
                        # 取更高置信度
                        rule_result.confidence = max(rule_result.confidence, llm_result.confidence)
                return rule_result
            return None
        
        # 策略4：自动
        if self.strategy == DetectionStrategy.AUTO:
            # 先尝试规则
            rule_result = self._detect_by_rules(old_fact, new_fact)
            if rule_result:
                return rule_result
            
            # 复杂情况用 LLM
            if self.llm_client and self._is_complex_case(old_fact, new_fact):
                return self._detect_by_llm(old_fact, new_fact, context)
            
            return None
        
        return None
    
    def _detect_by_rules(
        self,
        old_fact: TemporalFact,
        new_fact: TemporalFact
    ) -> Optional[Contradiction]:
        """规则检测"""
        for rule in self._rules:
            contradiction_type = rule(old_fact, new_fact)
            if contradiction_type:
                confidence = self._compute_confidence(old_fact, new_fact, contradiction_type)
                return Contradiction(
                    old_fact=old_fact,
                    new_fact=new_fact,
                    contradiction_type=contradiction_type,
                    confidence=confidence
                )
        return None
    
    def _detect_by_llm(
        self,
        old_fact: TemporalFact,
        new_fact: TemporalFact,
        context: Optional[str] = None
    ) -> Optional[Contradiction]:
        """LLM 检测"""
        if not self.llm_client:
            return None
        
        # 构建 prompt
        prompt = f"""判断以下两个事实是否存在矛盾：

事实1: {old_fact.fact}
- 主体: {old_fact.subject}
- 谓词: {old_fact.predicate}
- 客体: {old_fact.object}
- 有效时间: {old_fact.valid_from} 到 {old_fact.valid_until}

事实2: {new_fact.fact}
- 主体: {new_fact.subject}
- 谓词: {new_fact.predicate}
- 客体: {new_fact.object}
- 有效时间: {new_fact.valid_from} 到 {new_fact.valid_until}

{f"上下文: {context}" if context else ""}

请分析是否存在矛盾，如果存在，请指出：
1. 矛盾类型：direct（直接矛盾）/ temporal（时态矛盾）/ logical（逻辑矛盾）/ soft（软矛盾/可共存）
2. 置信度（0-1）
3. 简要说明

请用JSON格式回复：
{{"has_contradiction": true/false, "type": "...", "confidence": 0.x, "reason": "..."}}
"""
        
        try:
            response = self.llm_client.generate(prompt)
            # 解析响应
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                if result.get('has_contradiction'):
                    type_map = {
                        'direct': ContradictionType.DIRECT,
                        'temporal': ContradictionType.TEMPORAL,
                        'logical': ContradictionType.LOGICAL,
                        'soft': ContradictionType.SOFT
                    }
                    return Contradiction(
                        old_fact=old_fact,
                        new_fact=new_fact,
                        contradiction_type=type_map.get(result.get('type', 'direct'), ContradictionType.DIRECT),
                        confidence=result.get('confidence', 0.5),
                        notes=result.get('reason', '')
                    )
        except Exception as e:
            _safe_print(f"[ContradictionManager] LLM 检测失败: {e}")
        
        return None
    
    def _is_complex_case(self, old_fact: TemporalFact, new_fact: TemporalFact) -> bool:
        """判断是否是复杂情况（需要 LLM）"""
        # 长文本描述
        if len(old_fact.fact) > 100 or len(new_fact.fact) > 100:
            return True
        
        # 不同谓词但可能有语义关联
        if old_fact.predicate != new_fact.predicate:
            if old_fact.subject == new_fact.subject and old_fact.object == new_fact.object:
                return True
        
        return False
    
    def _compute_confidence(
        self,
        old_fact: TemporalFact,
        new_fact: TemporalFact,
        contradiction_type: ContradictionType
    ) -> float:
        """计算矛盾置信度"""
        base = 0.5
        
        # 直接矛盾置信度更高
        if contradiction_type == ContradictionType.DIRECT:
            base = 0.8
        elif contradiction_type == ContradictionType.LOGICAL:
            base = 0.7
        elif contradiction_type == ContradictionType.TEMPORAL:
            base = 0.6
        
        # 基于事实本身的置信度调整
        fact_confidence = (old_fact.confidence + new_fact.confidence) / 2
        base = base * 0.7 + fact_confidence * 0.3
        
        return min(1.0, base)
    
    def resolve(
        self,
        contradiction: Contradiction,
        strategy: Optional[ResolutionStrategy] = None,
        resolver: str = "system",
        notes: str = ""
    ) -> ResolutionResult:
        """解决矛盾
        
        Args:
            contradiction: 矛盾对象
            strategy: 解决策略（None 使用默认）
            resolver: 解决者
            notes: 备注
        
        Returns:
            解决结果
        """
        strategy = strategy or self.default_resolution
        
        old_fact = contradiction.old_fact
        new_fact = contradiction.new_fact
        
        result = ResolutionResult(
            success=True,
            action=strategy.value,
            old_fact_id=old_fact.uuid,
            new_fact_id=new_fact.uuid
        )
        
        if strategy == ResolutionStrategy.SUPERSEDE:
            # 新事实取代旧事实
            old_fact.valid_until = new_fact.valid_from or datetime.now()
            old_fact.superseded_at = datetime.now()
            result.message = "旧事实已被取代"
            
        elif strategy == ResolutionStrategy.COEXIST:
            # 允许共存
            result.message = "两个事实将共存"
            
        elif strategy == ResolutionStrategy.REJECT:
            # 拒绝新事实
            new_fact.expired_at = datetime.now()
            result.success = False
            result.message = "新事实已被拒绝"
            
        else:  # MANUAL
            result.message = "等待人工处理"
        
        # 记录解决
        record = self._find_record(contradiction.uuid)
        if record:
            record.resolved_at = datetime.now()
            record.resolution = strategy
            record.resolver = resolver
            record.notes = notes
            
            # 从待处理移到已解决
            if record in self.pending:
                self.pending.remove(record)
                self.resolved.append(record)
        
        self._save()
        return result
    
    def _find_record(self, contradiction_uuid: str) -> Optional[ContradictionRecord]:
        """查找矛盾记录"""
        for record in self.pending:
            if record.contradiction.uuid == contradiction_uuid:
                return record
        return None
    
    def add_pending(self, contradiction: Contradiction):
        """添加待处理矛盾"""
        record = ContradictionRecord(contradiction=contradiction)
        self.pending.append(record)
        self._save()
    
    def get_pending(self) -> List[Contradiction]:
        """获取待处理矛盾"""
        return [r.contradiction for r in self.pending]
    
    def get_resolved(self, limit: int = 100) -> List[ContradictionRecord]:
        """获取已解决矛盾"""
        return self.resolved[-limit:]
    
    def get_contradiction(self, contradiction_id: str) -> Optional[Contradiction]:
        """获取单个矛盾记录
        
        Args:
            contradiction_id: 矛盾 ID
            
        Returns:
            Contradiction 对象，不存在则返回 None
        """
        # 先从待处理中查找
        for record in self.pending:
            if record.contradiction.id == contradiction_id:
                return record.contradiction
        # 再从已解决中查找
        for record in self.resolved:
            if record.contradiction.id == contradiction_id:
                return record.contradiction
        return None
    
    def get_contradictions(
        self, 
        status: Optional[str] = None, 
        limit: int = 100
    ) -> List[Contradiction]:
        """获取矛盾列表
        
        Args:
            status: 过滤状态 ('pending', 'resolved', None=全部)
            limit: 最大返回数量
            
        Returns:
            矛盾列表
        """
        results = []
        
        if status is None or status == 'pending':
            results.extend([r.contradiction for r in self.pending])
        
        if status is None or status == 'resolved':
            results.extend([r.contradiction for r in self.resolved[-limit:]])
        
        return results[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息（API 兼容方法）"""
        return self.stats()
    
    def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'pending_count': len(self.pending),
            'resolved_count': len(self.resolved),
            'strategy': self.strategy.value,
            'auto_resolve': self.auto_resolve,
            'default_resolution': self.default_resolution.value,
            'rules_count': len(self._rules),
            'llm_enabled': self.llm_client is not None
        }


__all__ = [
    'DetectionStrategy',
    'ContradictionRecord',
    'ContradictionManager',
]
