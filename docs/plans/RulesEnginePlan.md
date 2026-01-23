# 规则引擎 v3.1 - 完整实现计划

## 🎯 设计目标

| 目标 | 要求 |
|------|------|
| **100% 规则遵守** | 任何违规都能被检测到 |
| **低成本** | 本地优先，LLM 按需 |
| **快速响应** | <100ms 本地检测，<2s LLM 检测 |
| **100% 不遗忘** | 规则持久化 + 与记忆系统联动 |
| **通用设计** | 不依赖 SillyTavern，纯 API 驱动 |

---

## 📐 架构设计

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        RuleEngine (规则引擎)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    RuleStore (规则存储)                          │   │
│  │  ├─ 绝对规则 (absolute_rules)      ← 用户手动添加                │   │
│  │  ├─ 角色属性规则 (attribute_rules) ← 从角色卡自动提取            │   │
│  │  ├─ 关系规则 (relationship_rules)  ← 从对话/知识图谱提取         │   │
│  │  └─ 世界观规则 (world_rules)       ← 从世界设定提取              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                  RuleCompiler (规则编译器)                        │   │
│  │  输入: 自然语言规则                                               │   │
│  │  输出: CompiledRule (结构化规则 + 检测模式 + 向量嵌入)            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              三层检测系统 (Three-Layer Detection)                 │   │
│  │                                                                   │   │
│  │  L1: 快速本地检测 (Fast Local)           ~10ms                   │   │
│  │      ├─ 关键词匹配                                                │   │
│  │      ├─ 正则模式匹配                                              │   │
│  │      └─ 数值属性检测                                              │   │
│  │                          ↓ 可疑内容                               │   │
│  │  L2: 语义向量检测 (Semantic Vector)      ~50ms                   │   │
│  │      ├─ 规则向量 vs 输出向量 相似度                               │   │
│  │      └─ 矛盾语义检测                                              │   │
│  │                          ↓ 高风险内容                             │   │
│  │  L3: LLM 精确判断 (LLM Verify)           ~1-2s                   │   │
│  │      └─ 只对 L1/L2 标记的可疑内容进行 LLM 验证                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                ViolationHandler (违规处理器)                      │   │
│  │  ├─ WARN: 警告用户但不阻止                                        │   │
│  │  ├─ BLOCK: 阻止输出并返回错误                                     │   │
│  │  └─ SUGGEST: 提供修正建议                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   REST API               Python SDK                    Recall Engine
   /v1/rules/*            engine.rules.*               build_context()
```

---

## 📋 模块设计

### 1. 数据模型

```python
# recall/processor/rule_engine/models.py

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime

class RuleType(Enum):
    """规则类型"""
    PROHIBITION = "prohibition"      # 禁止：不会/不能/禁止
    REQUIREMENT = "requirement"      # 必须：必须/一定/总是
    ATTRIBUTE = "attribute"          # 属性：X的Y是Z
    RELATIONSHIP = "relationship"    # 关系：A和B是X关系
    CONDITION = "condition"          # 条件：如果X则Y
    WORLD = "world"                  # 世界观：这个世界没有X

class RuleSeverity(Enum):
    """违规严重程度"""
    CRITICAL = "critical"    # 严重：必须阻止
    HIGH = "high"            # 高：强烈警告
    MEDIUM = "medium"        # 中：普通警告
    LOW = "low"              # 低：提示

class ViolationAction(Enum):
    """违规处理方式"""
    BLOCK = "block"          # 阻止输出
    WARN = "warn"            # 警告但不阻止
    SUGGEST = "suggest"      # 提供修正建议
    LOG = "log"              # 仅记录

@dataclass
class CompiledRule:
    """编译后的规则"""
    id: str
    original_text: str                          # 原始自然语言
    rule_type: RuleType
    severity: RuleSeverity = RuleSeverity.HIGH
    action: ViolationAction = ViolationAction.WARN
    
    # 规则参数（解析后）
    subject: str = ""                           # 主体
    predicate: str = ""                         # 谓词/动作/属性名
    object: str = ""                            # 宾语/属性值
    
    # 检测模式（L1 快速检测用）
    keywords: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)      # 正则
    anti_patterns: List[str] = field(default_factory=list) # 反向模式（违规模式）
    
    # 语义检测（L2 用）
    embedding: Optional[List[float]] = None     # 规则的向量嵌入
    contradiction_keywords: List[str] = field(default_factory=list)  # 矛盾关键词
    
    # 元信息
    enabled: bool = True
    user_id: str = "default"
    character_id: str = "default"
    created_at: datetime = field(default_factory=datetime.now)
    source: str = "manual"                      # manual / extracted / imported
    
    # 统计
    check_count: int = 0
    violation_count: int = 0

@dataclass
class Violation:
    """违规记录"""
    rule_id: str
    rule_text: str
    rule_type: RuleType
    severity: RuleSeverity
    
    evidence: str                               # 违规证据（原文片段）
    detection_layer: str                        # L1/L2/L3
    confidence: float                           # 置信度 0-1
    
    suggestion: Optional[str] = None            # 修正建议
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class CheckResult:
    """检测结果"""
    is_compliant: bool                          # 是否合规
    violations: List[Violation] = field(default_factory=list)
    warnings: List[Violation] = field(default_factory=list)
    check_time_ms: float = 0
    layers_used: List[str] = field(default_factory=list)  # ["L1", "L2", "L3"]
```

---

### 2. 规则编译器

```python
# recall/processor/rule_engine/compiler.py

class RuleCompiler:
    """规则编译器 - 将自然语言规则转换为可执行检测"""
    
    # === 规则模式库 ===
    PATTERNS = {
        'prohibition': [
            # 中文禁止模式
            (r'^(.+?)(不会|不能|禁止|绝不|从不|永远不|决不|不可以|不准)(.+)$', 'zh'),
            # 英文禁止模式
            (r'^(.+?)\s+(will not|cannot|must not|never|won\'t|can\'t)\s+(.+)$', 'en'),
        ],
        'requirement': [
            (r'^(.+?)(必须|一定要?|总是|始终|应该|需要)(.+)$', 'zh'),
            (r'^(.+?)\s+(must|always|should|needs? to)\s+(.+)$', 'en'),
        ],
        'attribute': [
            (r'^(.+?)的(.+?)(是|为|叫做?)(.+)$', 'zh'),
            (r'^(.+?)\'s\s+(.+?)\s+(is|are|equals?)\s+(.+)$', 'en'),
        ],
        'relationship': [
            (r'^(.+?)(和|与|跟)(.+?)(是|的关系是)(.+)$', 'zh'),
            (r'^(.+?)\s+(and|with)\s+(.+?)\s+(are|is)\s+(.+)$', 'en'),
        ],
        'world': [
            (r'^(这个世界|世界观|设定中?)(没有|不存在|禁止|不允许)(.+)$', 'zh'),
            (r'^(this world|the setting)\s+(has no|doesn\'t have|forbids)\s+(.+)$', 'en'),
        ],
    }
    
    # === 动作同义词/变体词库 ===
    ACTION_VARIANTS = {
        '杀人': ['杀', '杀死', '杀害', '弑', '谋杀', '刺杀', '斩杀', '杀掉'],
        '说谎': ['说谎', '撒谎', '欺骗', '骗', '谎称', '假装'],
        '偷窃': ['偷', '盗', '窃', '偷窃', '盗窃', '顺手牵羊'],
        '飞行': ['飞', '飞行', '飞翔', '飞起', '腾空', '升空'],
        '魔法': ['魔法', '法术', '咒语', '施法', '念咒', '魔力'],
        # ... 可扩展
    }
    
    # === 关系对立词典 ===
    RELATIONSHIP_OPPOSITES = {
        '敌人': ['朋友', '盟友', '恋人', '伙伴', '同伴', '好友'],
        '朋友': ['敌人', '仇人', '对手', '仇敌'],
        '恋人': ['敌人', '陌生人', '仇人', '前任'],
        '主人': ['奴隶', '仆人', '下属'],
        '师傅': ['徒弟', '学生'],
        '父亲': ['儿子', '女儿'],
        '母亲': ['儿子', '女儿'],
        # ... 可扩展
    }
    
    def __init__(self, embedding_backend=None):
        self.embedding_backend = embedding_backend
    
    def compile(self, rule_text: str, **kwargs) -> CompiledRule:
        """编译单条规则"""
        import hashlib
        rule_id = f"rule_{hashlib.md5(rule_text.encode()).hexdigest()[:8]}"
        
        # 1. 识别规则类型并解析
        rule_type, parsed = self._parse_rule(rule_text)
        
        # 2. 生成检测模式
        keywords, patterns, anti_patterns = self._generate_detection_patterns(
            rule_type, parsed, rule_text
        )
        
        # 3. 生成矛盾关键词
        contradiction_keywords = self._generate_contradiction_keywords(rule_type, parsed)
        
        # 4. 生成向量嵌入（可选）
        embedding = None
        if self.embedding_backend:
            embedding = self.embedding_backend.encode(rule_text).tolist()
        
        # 5. 确定严重程度
        severity = self._determine_severity(rule_type, rule_text)
        
        return CompiledRule(
            id=rule_id,
            original_text=rule_text,
            rule_type=rule_type,
            severity=severity,
            subject=parsed.get('subject', ''),
            predicate=parsed.get('predicate', ''),
            object=parsed.get('object', ''),
            keywords=keywords,
            patterns=patterns,
            anti_patterns=anti_patterns,
            contradiction_keywords=contradiction_keywords,
            embedding=embedding,
            **kwargs
        )
    
    def compile_batch(self, rules: List[str], **kwargs) -> List[CompiledRule]:
        """批量编译规则"""
        return [self.compile(r, **kwargs) for r in rules]
    
    def _parse_rule(self, text: str) -> tuple:
        """解析规则文本"""
        import re
        
        for rule_type, patterns in self.PATTERNS.items():
            for pattern, lang in patterns:
                match = re.match(pattern, text.strip(), re.IGNORECASE)
                if match:
                    groups = match.groups()
                    parsed = self._extract_parsed_fields(rule_type, groups)
                    return RuleType(rule_type), parsed
        
        # 未匹配到模式，尝试智能解析
        return RuleType.PROHIBITION, {'raw': text}
    
    def _extract_parsed_fields(self, rule_type: str, groups: tuple) -> dict:
        """从匹配组提取字段"""
        if rule_type == 'prohibition':
            return {
                'subject': groups[0].strip(),
                'predicate': 'not',
                'object': groups[2].strip() if len(groups) > 2 else ''
            }
        elif rule_type == 'attribute':
            return {
                'subject': groups[0].strip(),
                'predicate': groups[1].strip(),
                'object': groups[3].strip() if len(groups) > 3 else ''
            }
        elif rule_type == 'relationship':
            return {
                'subject': groups[0].strip(),
                'object': groups[2].strip(),
                'predicate': groups[4].strip() if len(groups) > 4 else ''
            }
        elif rule_type == 'world':
            return {
                'subject': '世界',
                'predicate': 'not_exist',
                'object': groups[2].strip() if len(groups) > 2 else ''
            }
        return {'raw': ' '.join(groups)}
    
    def _generate_detection_patterns(self, rule_type: RuleType, parsed: dict, text: str) -> tuple:
        """生成检测模式"""
        keywords = []
        patterns = []
        anti_patterns = []  # 违规模式
        
        subject = parsed.get('subject', '')
        obj = parsed.get('object', '')
        
        if rule_type == RuleType.PROHIBITION:
            # 禁止规则：检测是否出现了被禁止的动作
            keywords = [subject] if subject else []
            
            # 获取动作变体
            action_variants = self._get_action_variants(obj)
            keywords.extend(action_variants[:3])  # 取前3个关键词
            
            # 生成违规模式
            for variant in action_variants:
                anti_patterns.extend([
                    f'{subject}.*{variant}了',
                    f'{subject}.*正在{variant}',
                    f'{subject}.*开始{variant}',
                    f'{subject}.*{variant}着',
                    f'{variant}.*{subject}',  # 被动句
                ])
        
        elif rule_type == RuleType.ATTRIBUTE:
            # 属性规则：检测是否出现了矛盾属性
            predicate = parsed.get('predicate', '')
            keywords = [subject, predicate]
            
            # 属性变更模式
            anti_patterns = [
                f'{subject}的{predicate}(是|为|变成了?)(?!{obj})',
            ]
        
        elif rule_type == RuleType.RELATIONSHIP:
            # 关系规则：检测是否出现了矛盾关系
            predicate = parsed.get('predicate', '')
            keywords = [subject, obj]
            
            # 获取对立关系
            opposites = self.RELATIONSHIP_OPPOSITES.get(predicate, [])
            for opposite in opposites:
                anti_patterns.extend([
                    f'{subject}.*{obj}.*{opposite}',
                    f'{obj}.*{subject}.*{opposite}',
                    f'{subject}.*和.*{obj}.*成为.*{opposite}',
                ])
        
        elif rule_type == RuleType.WORLD:
            # 世界观规则：检测是否出现了不存在的事物
            keywords = self._get_action_variants(obj)[:5]
            anti_patterns = [f'.*{kw}.*' for kw in keywords]
        
        return keywords, patterns, anti_patterns
    
    def _get_action_variants(self, action: str) -> List[str]:
        """获取动作的所有变体"""
        # 先查词库
        for base, variants in self.ACTION_VARIANTS.items():
            if action in variants or action == base:
                return variants
        # 没找到则返回原词 + 简单变体
        return [action, action + '了', action + '着', '正在' + action]
    
    def _generate_contradiction_keywords(self, rule_type: RuleType, parsed: dict) -> List[str]:
        """生成矛盾关键词（用于语义检测）"""
        if rule_type == RuleType.RELATIONSHIP:
            predicate = parsed.get('predicate', '')
            return self.RELATIONSHIP_OPPOSITES.get(predicate, [])
        return []
    
    def _determine_severity(self, rule_type: RuleType, text: str) -> RuleSeverity:
        """确定规则严重程度"""
        critical_keywords = ['绝对', '永远', '必须', '禁止', '严禁', '不可', 'must', 'never', 'absolutely']
        if any(kw in text.lower() for kw in critical_keywords):
            return RuleSeverity.CRITICAL
        if rule_type in [RuleType.PROHIBITION, RuleType.WORLD]:
            return RuleSeverity.HIGH
        return RuleSeverity.MEDIUM
```

---

### 3. 三层检测系统

```python
# recall/processor/rule_engine/detector.py

class ThreeLayerDetector:
    """三层检测系统 - 快速 + 准确 + 低成本"""
    
    def __init__(
        self,
        embedding_backend=None,
        llm_client=None,
        config: dict = None
    ):
        self.embedding_backend = embedding_backend
        self.llm_client = llm_client
        self.config = config or {
            'l1_enabled': True,
            'l2_enabled': True,           # 需要 embedding_backend
            'l3_enabled': True,           # 需要 llm_client
            'l2_similarity_threshold': 0.75,  # 语义相似度阈值
            'l3_trigger_threshold': 0.6,      # 触发 L3 的置信度阈值
        }
    
    def check(self, text: str, rules: List[CompiledRule]) -> CheckResult:
        """检测文本是否违反规则"""
        import time
        start_time = time.time()
        
        violations = []
        warnings = []
        layers_used = []
        
        # === L1: 快速本地检测 ===
        if self.config['l1_enabled']:
            layers_used.append('L1')
            l1_results = self._l1_fast_check(text, rules)
            
            for rule, confidence, evidence in l1_results:
                if confidence >= 0.9:
                    # 高置信度，直接判定违规
                    violations.append(self._create_violation(
                        rule, evidence, 'L1', confidence
                    ))
                elif confidence >= 0.5:
                    # 中等置信度，标记为可疑，进入 L2
                    warnings.append((rule, confidence, evidence))
        
        # === L2: 语义向量检测 ===
        if self.config['l2_enabled'] and self.embedding_backend and warnings:
            layers_used.append('L2')
            l2_results = self._l2_semantic_check(text, warnings)
            
            new_warnings = []
            for rule, confidence, evidence in l2_results:
                if confidence >= 0.85:
                    violations.append(self._create_violation(
                        rule, evidence, 'L2', confidence
                    ))
                elif confidence >= self.config['l3_trigger_threshold']:
                    new_warnings.append((rule, confidence, evidence))
            warnings = new_warnings
        
        # === L3: LLM 精确判断 ===
        if self.config['l3_enabled'] and self.llm_client and warnings:
            layers_used.append('L3')
            l3_results = self._l3_llm_verify(text, warnings)
            
            for rule, confidence, evidence, suggestion in l3_results:
                if confidence >= 0.8:
                    v = self._create_violation(rule, evidence, 'L3', confidence)
                    v.suggestion = suggestion
                    violations.append(v)
        
        # 转换剩余 warnings
        final_warnings = [
            self._create_violation(r, e, 'L1', c)
            for r, c, e in warnings
        ]
        
        check_time_ms = (time.time() - start_time) * 1000
        
        return CheckResult(
            is_compliant=len(violations) == 0,
            violations=violations,
            warnings=final_warnings,
            check_time_ms=check_time_ms,
            layers_used=layers_used
        )
    
    def _l1_fast_check(self, text: str, rules: List[CompiledRule]) -> List[tuple]:
        """L1: 快速本地检测（关键词 + 正则）"""
        import re
        results = []
        
        for rule in rules:
            if not rule.enabled:
                continue
            
            confidence = 0.0
            evidence = ""
            
            # 1. 关键词检测
            keyword_matches = sum(1 for kw in rule.keywords if kw in text)
            if keyword_matches > 0:
                confidence = min(0.3, keyword_matches * 0.1)
            
            # 2. 违规模式检测（核心）
            for pattern in rule.anti_patterns:
                try:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        confidence = max(confidence, 0.8)
                        evidence = match.group(0)[:100]
                        break
                except re.error:
                    continue
            
            # 3. 矛盾关键词检测
            if rule.contradiction_keywords:
                for ck in rule.contradiction_keywords:
                    if ck in text and rule.subject in text:
                        confidence = max(confidence, 0.6)
                        # 找到包含矛盾词的句子
                        for sent in text.split('。'):
                            if ck in sent:
                                evidence = sent[:100]
                                break
            
            if confidence > 0.3:
                results.append((rule, confidence, evidence))
        
        return results
    
    def _l2_semantic_check(self, text: str, suspects: List[tuple]) -> List[tuple]:
        """L2: 语义向量检测"""
        import numpy as np
        
        results = []
        text_embedding = self.embedding_backend.encode(text)
        
        for rule, l1_confidence, evidence in suspects:
            if rule.embedding is None:
                # 没有向量，保持 L1 结果
                results.append((rule, l1_confidence, evidence))
                continue
            
            rule_embedding = np.array(rule.embedding)
            
            # 计算余弦相似度
            similarity = np.dot(text_embedding, rule_embedding) / (
                np.linalg.norm(text_embedding) * np.linalg.norm(rule_embedding)
            )
            
            # 对于禁止规则，高相似度反而说明可能违规
            if rule.rule_type == RuleType.PROHIBITION:
                # 检测文本是否在"执行"被禁止的动作
                action_embedding = self.embedding_backend.encode(rule.object)
                action_similarity = np.dot(text_embedding, action_embedding) / (
                    np.linalg.norm(text_embedding) * np.linalg.norm(action_embedding)
                )
                
                if action_similarity > self.config['l2_similarity_threshold']:
                    # 语义上确实在描述被禁止的动作
                    confidence = min(0.95, l1_confidence + 0.2)
                    results.append((rule, confidence, evidence))
                    continue
            
            # 综合 L1 和 L2 置信度
            final_confidence = l1_confidence * 0.6 + similarity * 0.4
            results.append((rule, final_confidence, evidence))
        
        return results
    
    def _l3_llm_verify(self, text: str, suspects: List[tuple]) -> List[tuple]:
        """L3: LLM 精确判断（只处理可疑内容）"""
        results = []
        
        # 批量处理以节省成本
        rules_to_check = [(r, c, e) for r, c, e in suspects if c >= self.config['l3_trigger_threshold']]
        
        if not rules_to_check:
            return results
        
        prompt = self._build_llm_prompt(text, rules_to_check)
        
        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            parsed = self._parse_llm_response(response)
            
            for rule, _, evidence in rules_to_check:
                rule_result = parsed.get(rule.id, {})
                if rule_result.get('violated', False):
                    results.append((
                        rule,
                        rule_result.get('confidence', 0.9),
                        rule_result.get('evidence', evidence),
                        rule_result.get('suggestion', None)
                    ))
        
        except Exception as e:
            print(f"[RuleEngine] L3 LLM 检测失败: {e}")
            # 失败时保守处理：将高置信度的标记为违规
            for rule, confidence, evidence in rules_to_check:
                if confidence >= 0.7:
                    results.append((rule, confidence, evidence, None))
        
        return results
    
    def _build_llm_prompt(self, text: str, suspects: List[tuple]) -> str:
        """构建 LLM 检测提示词"""
        rules_text = "\n".join([
            f"- [{r.id}] {r.original_text} (类型: {r.rule_type.value})"
            for r, _, _ in suspects
        ])
        
        return f'''你是一个规则合规检测专家。请判断以下文本是否违反了给定的规则。

## 需要检查的规则：
{rules_text}

## 待检测的文本：
{text[:2000]}

## 请以 JSON 格式返回检测结果：
```json
{{
  "rule_xxx": {{
    "violated": true/false,
    "confidence": 0.0-1.0,
    "evidence": "违规证据（引用原文）",
    "suggestion": "修正建议（如果违规）"
  }}
}}
```

只返回 JSON，不要其他内容。对于未违规的规则，可以省略或设置 violated=false。'''
    
    def _parse_llm_response(self, response: str) -> dict:
        """解析 LLM 响应"""
        import json
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except:
            return {}
    
    def _create_violation(self, rule: CompiledRule, evidence: str, 
                          layer: str, confidence: float) -> Violation:
        """创建违规记录"""
        return Violation(
            rule_id=rule.id,
            rule_text=rule.original_text,
            rule_type=rule.rule_type,
            severity=rule.severity,
            evidence=evidence,
            detection_layer=layer,
            confidence=confidence
        )
```

---

### 4. 规则存储 & 管理

```python
# recall/processor/rule_engine/store.py

class RuleStore:
    """规则存储 - 持久化 + 多租户隔离"""
    
    def __init__(self, data_path: str, compiler: RuleCompiler):
        self.data_path = data_path
        self.compiler = compiler
        self._rules: Dict[str, Dict[str, List[CompiledRule]]] = {}  # user_id -> char_id -> rules
        self._load_all()
    
    def _get_storage_path(self, user_id: str, character_id: str) -> str:
        """获取规则存储路径"""
        return os.path.join(self.data_path, user_id, character_id, 'rules.json')
    
    def _load_all(self):
        """加载所有用户的规则"""
        if not os.path.exists(self.data_path):
            return
        
        for user_id in os.listdir(self.data_path):
            user_path = os.path.join(self.data_path, user_id)
            if not os.path.isdir(user_path):
                continue
            
            for char_id in os.listdir(user_path):
                char_path = os.path.join(user_path, char_id)
                if not os.path.isdir(char_path):
                    continue
                
                rules_file = os.path.join(char_path, 'rules.json')
                if os.path.exists(rules_file):
                    self._load_rules(user_id, char_id, rules_file)
    
    def _load_rules(self, user_id: str, char_id: str, file_path: str):
        """加载规则文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if user_id not in self._rules:
                self._rules[user_id] = {}
            if char_id not in self._rules[user_id]:
                self._rules[user_id][char_id] = []
            
            for rule_data in data.get('rules', []):
                rule = self._deserialize_rule(rule_data)
                self._rules[user_id][char_id].append(rule)
        
        except Exception as e:
            print(f"[RuleStore] 加载规则失败 ({user_id}/{char_id}): {e}")
    
    def _save_rules(self, user_id: str, character_id: str):
        """保存规则到文件"""
        file_path = self._get_storage_path(user_id, character_id)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        rules = self.get_rules(user_id, character_id)
        data = {
            'rules': [self._serialize_rule(r) for r in rules],
            'updated_at': datetime.now().isoformat()
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_rule(
        self, 
        rule_text: str, 
        user_id: str = "default",
        character_id: str = "default",
        **kwargs
    ) -> CompiledRule:
        """添加规则"""
        rule = self.compiler.compile(rule_text, user_id=user_id, character_id=character_id, **kwargs)
        
        if user_id not in self._rules:
            self._rules[user_id] = {}
        if character_id not in self._rules[user_id]:
            self._rules[user_id][character_id] = []
        
        # 检查重复
        for existing in self._rules[user_id][character_id]:
            if existing.original_text == rule_text:
                return existing
        
        self._rules[user_id][character_id].append(rule)
        self._save_rules(user_id, character_id)
        return rule
    
    def add_rules_batch(
        self, 
        rules: List[str], 
        user_id: str = "default",
        character_id: str = "default"
    ) -> List[CompiledRule]:
        """批量添加规则"""
        compiled = []
        for rule_text in rules:
            compiled.append(self.add_rule(rule_text, user_id, character_id))
        return compiled
    
    def get_rules(
        self, 
        user_id: str = "default", 
        character_id: str = "default"
    ) -> List[CompiledRule]:
        """获取规则列表"""
        return self._rules.get(user_id, {}).get(character_id, [])
    
    def get_all_rules(self, user_id: str = "default") -> List[CompiledRule]:
        """获取用户所有角色的规则"""
        all_rules = []
        for char_rules in self._rules.get(user_id, {}).values():
            all_rules.extend(char_rules)
        return all_rules
    
    def remove_rule(
        self, 
        rule_id: str, 
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """删除规则"""
        rules = self._rules.get(user_id, {}).get(character_id, [])
        for i, rule in enumerate(rules):
            if rule.id == rule_id:
                rules.pop(i)
                self._save_rules(user_id, character_id)
                return True
        return False
    
    def update_rule(
        self, 
        rule_id: str, 
        updates: dict,
        user_id: str = "default",
        character_id: str = "default"
    ) -> Optional[CompiledRule]:
        """更新规则"""
        rules = self._rules.get(user_id, {}).get(character_id, [])
        for rule in rules:
            if rule.id == rule_id:
                for key, value in updates.items():
                    if hasattr(rule, key):
                        setattr(rule, key, value)
                self._save_rules(user_id, character_id)
                return rule
        return None
    
    def import_from_character_card(
        self, 
        character_card: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> List[CompiledRule]:
        """从角色卡提取规则"""
        # 使用正则提取属性描述
        import re
        
        extracted_rules = []
        
        # 提取"X是Y"格式的属性
        attr_patterns = [
            r'(姓名|名字|年龄|身高|体重|发色|瞳色|性格|职业)[:：是为]?\s*(.+?)(?:[,，。\n]|$)',
            r'(name|age|height|weight|hair|eyes|personality|occupation)[:：]?\s*(.+?)(?:[,.\n]|$)',
        ]
        
        for pattern in attr_patterns:
            for match in re.finditer(pattern, character_card, re.IGNORECASE):
                attr_name = match.group(1)
                attr_value = match.group(2).strip()
                if attr_value:
                    rule_text = f"角色的{attr_name}是{attr_value}"
                    extracted_rules.append(rule_text)
        
        # 提取"不会/不能"格式的禁止规则
        prohibition_patterns = [
            r'(不会|不能|禁止|绝不|从不)(.+?)(?:[,，。\n]|$)',
        ]
        
        for pattern in prohibition_patterns:
            for match in re.finditer(pattern, character_card):
                action = match.group(2).strip()
                if action:
                    rule_text = f"角色{match.group(1)}{action}"
                    extracted_rules.append(rule_text)
        
        # 编译并添加
        return self.add_rules_batch(extracted_rules, user_id, character_id)
    
    def _serialize_rule(self, rule: CompiledRule) -> dict:
        """序列化规则"""
        return {
            'id': rule.id,
            'original_text': rule.original_text,
            'rule_type': rule.rule_type.value,
            'severity': rule.severity.value,
            'action': rule.action.value,
            'subject': rule.subject,
            'predicate': rule.predicate,
            'object': rule.object,
            'keywords': rule.keywords,
            'patterns': rule.patterns,
            'anti_patterns': rule.anti_patterns,
            'contradiction_keywords': rule.contradiction_keywords,
            'embedding': rule.embedding,
            'enabled': rule.enabled,
            'source': rule.source,
            'created_at': rule.created_at.isoformat(),
        }
    
    def _deserialize_rule(self, data: dict) -> CompiledRule:
        """反序列化规则"""
        return CompiledRule(
            id=data['id'],
            original_text=data['original_text'],
            rule_type=RuleType(data['rule_type']),
            severity=RuleSeverity(data.get('severity', 'high')),
            action=ViolationAction(data.get('action', 'warn')),
            subject=data.get('subject', ''),
            predicate=data.get('predicate', ''),
            object=data.get('object', ''),
            keywords=data.get('keywords', []),
            patterns=data.get('patterns', []),
            anti_patterns=data.get('anti_patterns', []),
            contradiction_keywords=data.get('contradiction_keywords', []),
            embedding=data.get('embedding'),
            enabled=data.get('enabled', True),
            source=data.get('source', 'imported'),
            created_at=datetime.fromisoformat(data['created_at']) if 'created_at' in data else datetime.now()
        )
```

---

### 5. 主引擎类

```python
# recall/processor/rule_engine/engine.py

class RuleEngine:
    """规则引擎 - 统一入口"""
    
    def __init__(
        self,
        data_path: str,
        embedding_backend=None,
        llm_client=None,
        config: dict = None
    ):
        self.data_path = data_path
        self.embedding_backend = embedding_backend
        self.llm_client = llm_client
        
        # 初始化组件
        self.compiler = RuleCompiler(embedding_backend)
        self.store = RuleStore(data_path, self.compiler)
        self.detector = ThreeLayerDetector(
            embedding_backend=embedding_backend,
            llm_client=llm_client,
            config=config
        )
        
        # 配置
        self.config = config or {}
        self.default_action = ViolationAction(
            self.config.get('default_action', 'warn')
        )
    
    # === 规则管理 API ===
    
    def add_rule(self, rule_text: str, **kwargs) -> CompiledRule:
        """添加规则"""
        return self.store.add_rule(rule_text, **kwargs)
    
    def add_rules(self, rules: List[str], **kwargs) -> List[CompiledRule]:
        """批量添加规则"""
        return self.store.add_rules_batch(rules, **kwargs)
    
    def get_rules(self, **kwargs) -> List[CompiledRule]:
        """获取规则"""
        return self.store.get_rules(**kwargs)
    
    def remove_rule(self, rule_id: str, **kwargs) -> bool:
        """删除规则"""
        return self.store.remove_rule(rule_id, **kwargs)
    
    def import_from_character(self, character_card: str, **kwargs) -> List[CompiledRule]:
        """从角色卡导入规则"""
        return self.store.import_from_character_card(character_card, **kwargs)
    
    # === 检测 API ===
    
    def check(
        self, 
        text: str, 
        user_id: str = "default",
        character_id: str = "default",
        include_global: bool = True
    ) -> CheckResult:
        """检测文本是否违规"""
        # 收集适用的规则
        rules = self.store.get_rules(user_id, character_id)
        
        if include_global:
            # 也包含全局规则（user_id="global"）
            global_rules = self.store.get_rules("global", "global")
            rules = rules + global_rules
        
        # 执行检测
        result = self.detector.check(text, rules)
        
        # 更新统计
        for rule in rules:
            rule.check_count += 1
        for v in result.violations:
            for rule in rules:
                if rule.id == v.rule_id:
                    rule.violation_count += 1
        
        return result
    
    def check_and_handle(
        self, 
        text: str,
        **kwargs
    ) -> tuple:
        """检测并处理违规
        
        Returns:
            (is_allowed, result, handled_text)
        """
        result = self.check(text, **kwargs)
        
        if result.is_compliant:
            return True, result, text
        
        # 根据最严重的违规决定处理方式
        most_severe = max(result.violations, key=lambda v: v.severity.value)
        
        # 查找对应规则的 action
        rules = self.get_rules(**kwargs)
        action = self.default_action
        for rule in rules:
            if rule.id == most_severe.rule_id:
                action = rule.action
                break
        
        if action == ViolationAction.BLOCK:
            return False, result, None
        elif action == ViolationAction.WARN:
            return True, result, text
        elif action == ViolationAction.SUGGEST:
            # 如果有修正建议，可以返回
            if most_severe.suggestion:
                return True, result, most_severe.suggestion
            return True, result, text
        else:
            return True, result, text
    
    # === 与 Recall Engine 集成 ===
    
    def inject_rules_context(
        self, 
        user_id: str = "default",
        character_id: str = "default"
    ) -> str:
        """生成规则上下文注入文本（用于 build_context）"""
        rules = self.get_rules(user_id=user_id, character_id=character_id)
        
        if not rules:
            return ""
        
        lines = ["【必须遵守的规则】"]
        
        for rule in rules:
            if rule.enabled:
                severity_icon = {
                    RuleSeverity.CRITICAL: "🔴",
                    RuleSeverity.HIGH: "🟠",
                    RuleSeverity.MEDIUM: "🟡",
                    RuleSeverity.LOW: "🟢",
                }.get(rule.severity, "⚪")
                lines.append(f"{severity_icon} {rule.original_text}")
        
        return "\n".join(lines)
```

---

### 6. REST API

```python
# 在 recall/server.py 中添加

# === 规则引擎 API ===

@app.post("/v1/rules", tags=["Rules"])
async def add_rule(
    rule_text: str = Body(..., embed=True),
    user_id: str = Query(default="default"),
    character_id: str = Query(default="default"),
    severity: str = Query(default="high"),
    action: str = Query(default="warn")
):
    """添加规则"""
    rule = engine.rule_engine.add_rule(
        rule_text,
        user_id=user_id,
        character_id=character_id,
        severity=RuleSeverity(severity),
        action=ViolationAction(action)
    )
    return {
        "id": rule.id,
        "type": rule.rule_type.value,
        "severity": rule.severity.value,
        "parsed": {
            "subject": rule.subject,
            "predicate": rule.predicate,
            "object": rule.object
        }
    }

@app.post("/v1/rules/batch", tags=["Rules"])
async def add_rules_batch(
    rules: List[str] = Body(...),
    user_id: str = Query(default="default"),
    character_id: str = Query(default="default")
):
    """批量添加规则"""
    compiled = engine.rule_engine.add_rules(rules, user_id=user_id, character_id=character_id)
    return {"added": len(compiled), "rules": [r.id for r in compiled]}

@app.get("/v1/rules", tags=["Rules"])
async def list_rules(
    user_id: str = Query(default="default"),
    character_id: str = Query(default="default")
):
    """获取规则列表"""
    rules = engine.rule_engine.get_rules(user_id=user_id, character_id=character_id)
    return [
        {
            "id": r.id,
            "text": r.original_text,
            "type": r.rule_type.value,
            "severity": r.severity.value,
            "enabled": r.enabled,
            "check_count": r.check_count,
            "violation_count": r.violation_count
        }
        for r in rules
    ]

@app.delete("/v1/rules/{rule_id}", tags=["Rules"])
async def delete_rule(
    rule_id: str,
    user_id: str = Query(default="default"),
    character_id: str = Query(default="default")
):
    """删除规则"""
    success = engine.rule_engine.remove_rule(rule_id, user_id=user_id, character_id=character_id)
    return {"success": success}

@app.post("/v1/rules/check", tags=["Rules"])
async def check_text(
    text: str = Body(..., embed=True),
    user_id: str = Query(default="default"),
    character_id: str = Query(default="default")
):
    """检测文本是否违规"""
    result = engine.rule_engine.check(text, user_id=user_id, character_id=character_id)
    return {
        "compliant": result.is_compliant,
        "check_time_ms": result.check_time_ms,
        "layers_used": result.layers_used,
        "violations": [
            {
                "rule_id": v.rule_id,
                "rule_text": v.rule_text,
                "severity": v.severity.value,
                "evidence": v.evidence,
                "confidence": v.confidence,
                "suggestion": v.suggestion
            }
            for v in result.violations
        ],
        "warnings": len(result.warnings)
    }

@app.post("/v1/rules/import/character", tags=["Rules"])
async def import_from_character(
    character_card: str = Body(..., embed=True),
    user_id: str = Query(default="default"),
    character_id: str = Query(default="default")
):
    """从角色卡自动提取规则"""
    rules = engine.rule_engine.import_from_character(
        character_card, 
        user_id=user_id, 
        character_id=character_id
    )
    return {
        "extracted": len(rules),
        "rules": [{"id": r.id, "text": r.original_text, "type": r.rule_type.value} for r in rules]
    }
```

---

## 📅 实现计划

| 阶段 | 任务 | 工时 | 产出 |
|------|------|:----:|------|
| **Phase 1** | 数据模型 + 规则编译器 | 1天 | `models.py`, `compiler.py` |
| **Phase 2** | 三层检测系统 | 1.5天 | `detector.py` |
| **Phase 3** | 规则存储 + 主引擎 | 1天 | `store.py`, engine.py |
| **Phase 4** | REST API + 集成测试 | 0.5天 | API 端点 |
| **Phase 5** | 与 RecallEngine 集成 | 0.5天 | `build_context` 注入 |
| **Phase 6** | ST 插件前端（可选） | 1天 | UI 更新 |
| **总计** | | **5-6天** | |

---

## ✅ 验收标准

| 测试场景 | 输入 | 期望结果 |
|----------|------|----------|
| 禁止规则-直接违规 | 规则="角色不会杀人"<br>文本="角色杀死了敌人" | L1 检测，置信度≥0.8 |
| 禁止规则-变体违规 | 规则="角色不会杀人"<br>文本="角色刺杀了敌人" | L1/L2 检测，置信度≥0.7 |
| 禁止规则-无违规 | 规则="角色不会杀人"<br>文本="角色打伤了敌人" | 无违规 |
| 属性规则 | 规则="角色的发色是黑色"<br>文本="角色的金色长发" | L1 检测 |
| 关系规则 | 规则="A和B是敌人"<br>文本="A和B成为了朋友" | L1/L2 检测 |
| 世界观规则 | 规则="这个世界没有魔法"<br>文本="他施展了火球术" | L1 检测 |
| 性能测试 | 100条规则检测 | L1 <100ms |
| 批量导入 | 角色卡文本 | 自动提取属性规则 |

---

## 💰 成本估算

| 场景 | L1 成本 | L2 成本 | L3 成本 | 总成本 |
|------|:-------:|:-------:|:-------:|:------:|
| 大多数情况（无违规） | 免费 | - | - | **免费** |
| 可疑内容（需L2） | 免费 | 免费 | - | **免费** |
| 高风险内容（需L3） | 免费 | 免费 | ~$0.001 | **~$0.001** |
| 每100轮对话估算 | - | - | - | **<$0.01** |

> 💡 **设计优势**：90%+ 的检测在 L1 完成（免费），只有真正可疑的内容才触发 L3（LLM）

---

**这个计划满足你的要求吗？如果确认，我可以开始实现 Phase 1。**