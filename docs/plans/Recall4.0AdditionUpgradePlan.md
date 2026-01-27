# Recall 4.1 补充升级计划

> **版本**: v4.1.0  
> **日期**: 2026-01-28  
> **目标**: 在保持现有功能100%兼容的前提下，增强实体/关系提取的智能化程度，全面超越 Graphiti

---

## 📋 文档导航

1. [对比分析](#对比分析) - Recall vs Graphiti 全方位对比
2. [已识别短板](#已识别短板) - 需要改进的5个关键短板
3. [升级任务清单](#升级任务清单) - 具体的实现任务
4. [详细实现方案](#详细实现方案) - 每个任务的代码级实现
5. [配置说明](#配置说明) - 新增配置项
6. [测试验证](#测试验证) - 验证升级成功的测试用例
7. [回滚方案](#回滚方案) - 如何安全回滚

---

## 对比分析

### 1. 核心架构对比

| 维度 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **数据库依赖** | 零依赖（纯本地 JSON） | 依赖 Neo4j/FalkorDB/Neptune | ✅ Recall 更轻量 |
| **部署复杂度** | 单文件运行 | 需配置图数据库 | ✅ Recall 更简单 |
| **嵌入模式** | Lite/Local/Cloud 三模式 | 仅 Cloud API | ✅ Recall 更灵活 |
| **LLM 依赖** | 可选（大部分功能不需要） | 核心流程强依赖 | ✅ Recall 成本更低 |

### 2. 实体提取对比

| 特性 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **提取方式** | spaCy NER + jieba + 规则 + 已知词典 | LLM 调用 | ⚠️ 各有优劣 |
| **中文支持** | 原生优化（jieba, zh_core_web_sm） | 通用 LLM | ✅ Recall 中文更强 |
| **成本** | 接近零成本 | 每次调用消耗 Token | ✅ Recall 更省钱 |
| **准确率** | 规则受限，可能漏提 | LLM 更灵活 | ❌ **Recall 较弱** |
| **自定义实体类型** | 有限支持（known_entities 字典） | 完整的 Pydantic Schema | ❌ **Recall 较弱** |

### 3. 去重系统对比

| 特性 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **阶段数** | 三阶段 | 两阶段 | ✅ Recall 更精细 |
| **阶段 1** | 精确匹配 + MinHash + LSH | 精确匹配 + MinHash + LSH | 相当 |
| **阶段 2** | **语义相似度** | 直接 LLM | ✅ Recall 更高效 |
| **阶段 3** | 可选 LLM 确认 | LLM 确认 | 相当 |
| **设计优势** | 语义层过滤减少 LLM 调用 | - | ✅ Recall 成本更低 |

### 4. 时态系统对比

| 特性 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **时态模型** | **三时态**（事实/知识/系统） | 双时态（valid_at/invalid_at + expired_at） | ✅ Recall 更完整 |
| **时态索引** | TemporalIndex 专用索引 | 依赖图数据库索引 | ✅ Recall 更高效 |
| **时态查询** | 原生支持 | 通过 Cypher 查询 | 相当 |

### 5. 检索系统对比

| 特性 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **检索层数** | **11 层漏斗** | 混合检索（BM25 + Vector + BFS） | ✅ Recall 更精细 |
| **召回方式** | 并行三路召回 | 并行多路召回 | 相当 |
| **融合算法** | RRF | RRF | 相当 |
| **重排序** | L9 多因素 + L10 CrossEncoder | Cross-Encoder 可选 | 相当 |
| **兜底机制** | N-gram 原文匹配（100% 不遗忘） | 无明确机制 | ✅ Recall 更可靠 |
| **图遍历** | L5 BFS 扩展 | BFS 图遍历 | 相当 |

### 6. 关系/事实提取对比

| 特性 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **提取方式** | 正则模式 + 共现 | LLM 提取 | ❌ **Recall 较弱** |
| **关系类型** | 预定义 + MENTIONED_WITH | LLM 动态生成 | ❌ **Recall 较弱** |
| **时态信息** | 从文本提取有限 | LLM 提取 valid_at/invalid_at | ❌ **Recall 较弱** |
| **事实描述** | 原文截取 | LLM 生成自然语言描述 | ❌ **Recall 较弱** |

### 7. 矛盾检测对比

| 特性 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **检测策略** | 规则 + 可选 LLM | LLM 为主 | ✅ Recall 成本更低 |
| **解决策略** | SUPERSEDE/COEXIST/REJECT/MANUAL | 类似 | 相当 |
| **持久化** | 独立记录存储 | 边属性存储 | 相当 |

---

## 已识别短板

### 短板 1: 实体提取准确率不足 ⭐ 已有 SmartExtractor 部分解决

**问题分析**：
- spaCy zh_core_web_sm 对中文专有名词识别率低
- known_entities 字典需要手动维护
- 无法识别上下文相关的隐式实体

**当前状态**：
- `SmartExtractor` 已支持 RULES/ADAPTIVE/LLM 三模式
- 但 LLM 模式的实体类型定义仍然有限

**需要补充**：
1. 自定义实体类型 Schema 系统
2. 实体摘要自动生成

---

### 短板 2: 关系提取过于简单 ⭐ 核心短板

**问题分析**：
```python
# 当前实现（relation_extractor.py）只有：
# 1. 正则模式匹配（固定模式）
# 2. 共现检测（只产生 MENTIONED_WITH）
```

**需要补充**：
1. LLM 关系提取选项
2. 事实时态自动提取（valid_at/invalid_at）
3. 自然语言事实描述生成
4. 关系置信度评估

---

### 短板 3: 实体-关系一致性 ✅ 已修复

**已完成**：修改 `relation_extractor.extract()` 方法，支持传入已提取的实体列表，避免重复提取导致不一致。

---

### 短板 4: 缺少 Episode（情节）概念

**问题分析**：
- Recall 只有 Memory 概念
- 没有 Episode → Memory → Entity/Relation 的层次结构
- 无法追溯原始输入

**需要补充**：
1. EpisodeNode 数据模型
2. Episode 与 Memory/Entity/Relation 的关联

---

### 短板 5: 缺少节点摘要生成

**问题分析**：
- 实体只有名称和类型
- 没有自动生成的摘要
- 没有动态属性

**需要补充**：
1. 实体摘要自动生成（可选 LLM）
2. 动态属性支持

---

## ✅ Recall 的优势（保持不变）

1. **零依赖部署** - 无需图数据库
2. **三阶段去重** - 比 Graphiti 多一层语义过滤，降低 LLM 成本
3. **三时态模型** - 比 Graphiti 的双时态更完整
4. **十一层检索** - 更精细的召回控制
5. **100% 不遗忘保证** - N-gram 原文兜底
6. **中文优化** - jieba + spaCy 中文模型
7. **成本控制** - 大部分功能不依赖 LLM

---

## 升级任务清单

### 任务优先级

| 优先级 | 任务ID | 任务名称 | 复杂度 | 影响 | 状态 |
|--------|--------|----------|--------|------|------|
| P0 | T1 | LLM 关系提取增强 | 中 | 高 | 待开始 |
| P0 | T2 | 关系时态信息提取 | 中 | 高 | 待开始 |
| P1 | T3 | 自定义实体类型 Schema | 高 | 高 | 待开始 |
| P1 | T4 | LLM 实体提取增强 | 中 | 高 | 部分完成 |
| P2 | T5 | Episode 概念引入 | 高 | 中 | 待开始 |
| P2 | T6 | 实体摘要生成 | 低 | 中 | 待开始 |
| P3 | T7 | 动态实体属性 | 中 | 低 | 待开始 |

---

## 详细实现方案

### T1: LLM 关系提取增强

#### 1.1 目标

在不影响现有 `RelationExtractor` 的前提下，添加可选的 LLM 关系提取能力。

#### 1.2 设计原则

- **向后兼容**：默认使用规则模式，LLM 模式需要显式启用
- **成本可控**：集成 BudgetManager，防止超支
- **渐进式**：规则模式 → 自适应模式 → LLM 模式

#### 1.3 新增文件

**文件路径**: `recall/graph/llm_relation_extractor.py`

```python
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
        relations = extractor.extract(text, entities)
        
        # 方式2：自适应模式（推荐）
        extractor = LLMRelationExtractor(
            llm_client=llm_client,
            config=LLMRelationExtractorConfig(mode=RelationExtractionMode.ADAPTIVE)
        )
        relations = extractor.extract(text, entities)
        
        # 方式3：纯 LLM 模式（最高质量）
        extractor = LLMRelationExtractor(
            llm_client=llm_client,
            config=LLMRelationExtractorConfig(mode=RelationExtractionMode.LLM)
        )
        relations = extractor.extract(text, entities)
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
        entities: Optional[List] = None,
        turn: int = 0
    ) -> List[ExtractedRelationV2]:
        """提取关系
        
        Args:
            text: 原始文本
            entities: 已提取的实体列表
            turn: 轮次
        
        Returns:
            List[ExtractedRelationV2]: 提取的关系列表
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
        
        # 检查预算
        if self.budget_manager and not self.budget_manager.can_spend(0.01):
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
            response = self.llm_client.chat(prompt)
            relations = self._parse_llm_response(response, text)
            
            # 记录成本
            if self.budget_manager:
                self.budget_manager.record_usage(0.01)
            
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
            if json_match:
                data = json.loads(json_match.group())
                return [
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
        except (json.JSONDecodeError, Exception) as e:
            print(f"[LLMRelationExtractor] 解析失败: {e}")
        
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
        relations = self.extract(text, entities, turn)
        return [rel.to_legacy_tuple() for rel in relations]
```

#### 1.4 修改文件清单

**文件 1**: `recall/graph/__init__.py`

在文件末尾添加：

```python
# === Recall 4.1 新增 ===
from .llm_relation_extractor import (
    LLMRelationExtractor,
    LLMRelationExtractorConfig,
    RelationExtractionMode,
    ExtractedRelationV2
)
```

**文件 2**: `recall/engine.py`

在 `__init__` 方法中（约第 200 行，在 `self.relation_extractor` 初始化之后）添加：

```python
# === Recall 4.1: LLM 关系提取器（可选，向后兼容）===
self._llm_relation_extractor = None
llm_relation_mode = os.environ.get('LLM_RELATION_MODE', 'rules').lower()
if llm_relation_mode != 'rules' and self.llm_client:
    try:
        from .graph.llm_relation_extractor import (
            LLMRelationExtractor, LLMRelationExtractorConfig, RelationExtractionMode
        )
        mode_map = {
            'adaptive': RelationExtractionMode.ADAPTIVE,
            'llm': RelationExtractionMode.LLM,
        }
        self._llm_relation_extractor = LLMRelationExtractor(
            llm_client=self.llm_client,
            budget_manager=self.budget_manager if hasattr(self, 'budget_manager') else None,
            entity_extractor=self.entity_extractor,
            config=LLMRelationExtractorConfig(
                mode=mode_map.get(llm_relation_mode, RelationExtractionMode.RULES),
                enable_temporal=True,
                enable_fact_description=True
            )
        )
        _safe_print(f"[Recall v4.1] LLM 关系提取器已启用 (模式: {llm_relation_mode})")
    except ImportError:
        pass  # 模块不存在时静默跳过
```

在 `add()` 方法的关系提取部分（约第 1405 行），将原有代码：

```python
# 6. 更新知识图谱（失败不影响主流程）
try:
    # 复用已提取的实体列表，避免重复提取导致不一致
    relations = self.relation_extractor.extract(content, 0, entities=entities)
    for rel in relations:
        source_id, relation_type, target_id, source_text = rel
        self.knowledge_graph.add_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            source_text=source_text
        )
except Exception as e:
    _safe_print(f"[Recall] 知识图谱更新失败（不影响主流程）: {e}")
```

修改为：

```python
# 6. 更新知识图谱（失败不影响主流程）
try:
    # === Recall 4.1: 优先使用 LLM 关系提取器（如果启用）===
    if self._llm_relation_extractor:
        relations_v2 = self._llm_relation_extractor.extract(content, entities)
        for rel in relations_v2:
            self.knowledge_graph.add_relation(
                source_id=rel.source_id,
                target_id=rel.target_id,
                relation_type=rel.relation_type,
                source_text=rel.source_text,
                confidence=rel.confidence,
                valid_at=getattr(rel, 'valid_at', None),
                invalid_at=getattr(rel, 'invalid_at', None),
                fact=getattr(rel, 'fact', '')
            )
    else:
        # 使用传统规则提取器
        relations = self.relation_extractor.extract(content, 0, entities=entities)
        for rel in relations:
            source_id, relation_type, target_id, source_text = rel
            self.knowledge_graph.add_relation(
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                source_text=source_text
            )
except Exception as e:
    _safe_print(f"[Recall] 知识图谱更新失败（不影响主流程）: {e}")
```

#### 1.5 新增配置项

在 `recall_data/config/api_keys.env` 末尾添加：

```bash
# ============================================
# Recall 4.1 新增配置
# ============================================

# === LLM 关系提取配置 ===
# 模式: rules（纯规则，默认）/ adaptive（自适应）/ llm（纯LLM）
LLM_RELATION_MODE=rules

# 自适应模式下触发 LLM 的复杂度阈值 (0.0-1.0)
LLM_RELATION_COMPLEXITY_THRESHOLD=0.5

# 是否提取时态信息
LLM_RELATION_ENABLE_TEMPORAL=true

# 是否生成事实描述
LLM_RELATION_ENABLE_FACT_DESCRIPTION=true
```

---

### T2: 关系时态信息存储

#### 2.1 目标

将 LLM 提取的 `valid_at`/`invalid_at` 时态信息存储到 `KnowledgeGraph`。

#### 2.2 修改文件

**文件**: `recall/graph/knowledge_graph.py`

在 `Relation` 数据类中添加时态字段（约第 10 行）：

将：
```python
@dataclass
class Relation:
    """实体间的关系"""
    source_id: str           # 源实体ID
    target_id: str           # 目标实体ID
    relation_type: str       # 关系类型
    properties: Dict = field(default_factory=dict)  # 关系属性
    created_turn: int = 0    # 创建轮次
    confidence: float = 0.5  # 置信度
    source_text: str = ""    # 原文依据
```

修改为：
```python
@dataclass
class Relation:
    """实体间的关系"""
    source_id: str           # 源实体ID
    target_id: str           # 目标实体ID
    relation_type: str       # 关系类型
    properties: Dict = field(default_factory=dict)  # 关系属性
    created_turn: int = 0    # 创建轮次
    confidence: float = 0.5  # 置信度
    source_text: str = ""    # 原文依据
    # === Recall 4.1 新增时态字段 ===
    valid_at: Optional[str] = None      # 事实生效时间 (ISO 8601)
    invalid_at: Optional[str] = None    # 事实失效时间 (ISO 8601)
    fact: str = ""                      # 自然语言事实描述
```

同时在文件顶部添加导入：
```python
from typing import Dict, List, Optional, Tuple
```

修改 `add_relation` 方法签名（约第 98 行）：

将：
```python
def add_relation(self, source_id: str, target_id: str, relation_type: str,
                 properties: Dict = None, turn: int = 0, source_text: str = "",
                 confidence: float = 0.5) -> Relation:
```

修改为：
```python
def add_relation(self, source_id: str, target_id: str, relation_type: str,
                 properties: Dict = None, turn: int = 0, source_text: str = "",
                 confidence: float = 0.5,
                 valid_at: str = None, invalid_at: str = None,
                 fact: str = "") -> Relation:
```

修改方法内部的 `Relation` 创建（约第 120 行）：

将：
```python
rel = Relation(
    source_id=source_id,
    target_id=target_id,
    relation_type=relation_type,
    properties=properties or {},
    created_turn=turn,
    confidence=confidence,
    source_text=source_text
)
```

修改为：
```python
rel = Relation(
    source_id=source_id,
    target_id=target_id,
    relation_type=relation_type,
    properties=properties or {},
    created_turn=turn,
    confidence=confidence,
    source_text=source_text,
    valid_at=valid_at,
    invalid_at=invalid_at,
    fact=fact
)
```

---

### T3: 自定义实体类型 Schema

#### 3.1 新增文件

**文件路径**: `recall/models/entity_schema.py`

```python
"""自定义实体类型 Schema - Recall 4.1

支持用户定义自定义实体类型，包括：
1. 类型名称和描述
2. 必需/可选属性
3. 验证规则
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from enum import Enum


class AttributeType(str, Enum):
    """属性类型"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    LIST = "list"


@dataclass
class AttributeDefinition:
    """属性定义"""
    name: str
    attr_type: AttributeType = AttributeType.STRING
    required: bool = False
    default: Any = None
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'type': self.attr_type.value,
            'required': self.required,
            'default': self.default,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AttributeDefinition':
        return cls(
            name=data['name'],
            attr_type=AttributeType(data.get('type', 'string')),
            required=data.get('required', False),
            default=data.get('default'),
            description=data.get('description', '')
        )


@dataclass
class EntityTypeDefinition:
    """实体类型定义"""
    name: str                               # 类型名称（如 PERSON, LOCATION）
    display_name: str = ""                  # 显示名称（如 "人物", "地点"）
    description: str = ""                   # 类型描述
    attributes: List[AttributeDefinition] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)  # 示例实体
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name or self.name,
            'description': self.description,
            'attributes': [a.to_dict() for a in self.attributes],
            'examples': self.examples
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntityTypeDefinition':
        return cls(
            name=data['name'],
            display_name=data.get('display_name', data['name']),
            description=data.get('description', ''),
            attributes=[AttributeDefinition.from_dict(a) for a in data.get('attributes', [])],
            examples=data.get('examples', [])
        )


class EntitySchemaRegistry:
    """实体类型注册表
    
    使用方式：
        registry = EntitySchemaRegistry(data_path)
        
        # 注册自定义类型
        registry.register(EntityTypeDefinition(
            name="CHARACTER",
            display_name="角色",
            description="故事中的角色人物",
            attributes=[
                AttributeDefinition(name="age", attr_type=AttributeType.NUMBER),
                AttributeDefinition(name="occupation", attr_type=AttributeType.STRING),
            ],
            examples=["艾琳", "小明", "老王"]
        ))
        
        # 获取类型
        char_type = registry.get("CHARACTER")
        
        # 获取所有类型（用于 LLM 提示词）
        all_types = registry.get_all_for_prompt()
    """
    
    # 预定义的基础类型
    BUILTIN_TYPES = [
        EntityTypeDefinition(
            name="PERSON",
            display_name="人物",
            description="真实或虚构的人物",
            examples=["张三", "李四"]
        ),
        EntityTypeDefinition(
            name="LOCATION",
            display_name="地点",
            description="地理位置、地名",
            examples=["北京", "东京", "咖啡厅"]
        ),
        EntityTypeDefinition(
            name="ORGANIZATION",
            display_name="组织",
            description="公司、机构、团体",
            examples=["微软", "清华大学"]
        ),
        EntityTypeDefinition(
            name="ITEM",
            display_name="物品",
            description="物品、道具",
            examples=["手机", "魔法剑"]
        ),
        EntityTypeDefinition(
            name="CONCEPT",
            display_name="概念",
            description="抽象概念、术语",
            examples=["AI", "机器学习"]
        ),
        EntityTypeDefinition(
            name="EVENT",
            display_name="事件",
            description="事件、活动",
            examples=["春节", "婚礼"]
        ),
        EntityTypeDefinition(
            name="TIME",
            display_name="时间",
            description="时间点、时间段",
            examples=["2023年", "下午三点"]
        ),
    ]
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.schema_file = os.path.join(data_path, 'config', 'entity_schema.json')
        
        self._types: Dict[str, EntityTypeDefinition] = {}
        
        # 加载内置类型
        for t in self.BUILTIN_TYPES:
            self._types[t.name] = t
        
        # 加载自定义类型
        self._load()
    
    def _load(self):
        """加载自定义类型"""
        if os.path.exists(self.schema_file):
            try:
                with open(self.schema_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data.get('custom_types', []):
                        t = EntityTypeDefinition.from_dict(item)
                        self._types[t.name] = t
            except Exception as e:
                print(f"[EntitySchemaRegistry] 加载失败: {e}")
    
    def _save(self):
        """保存自定义类型"""
        os.makedirs(os.path.dirname(self.schema_file), exist_ok=True)
        
        # 只保存非内置类型
        builtin_names = {t.name for t in self.BUILTIN_TYPES}
        custom_types = [
            t.to_dict() for name, t in self._types.items()
            if name not in builtin_names
        ]
        
        with open(self.schema_file, 'w', encoding='utf-8') as f:
            json.dump({'custom_types': custom_types}, f, ensure_ascii=False, indent=2)
    
    def register(self, entity_type: EntityTypeDefinition):
        """注册自定义类型"""
        self._types[entity_type.name] = entity_type
        self._save()
    
    def get(self, name: str) -> Optional[EntityTypeDefinition]:
        """获取类型定义"""
        return self._types.get(name)
    
    def get_all(self) -> List[EntityTypeDefinition]:
        """获取所有类型"""
        return list(self._types.values())
    
    def get_all_for_prompt(self) -> str:
        """生成用于 LLM 提示词的类型描述"""
        lines = []
        for i, t in enumerate(self._types.values()):
            examples = ", ".join(t.examples[:3]) if t.examples else "无"
            lines.append(f"{i+1}. {t.name}（{t.display_name}）: {t.description}。示例: {examples}")
        return "\n".join(lines)
    
    def get_type_id_map(self) -> Dict[str, int]:
        """获取类型名称到ID的映射（用于 LLM 输出解析）"""
        return {t.name: i for i, t in enumerate(self._types.values())}
```

---

### T5: Episode 概念引入

#### 5.1 新增文件

**文件路径**: `recall/models/episode.py`

```python
"""Episode 数据模型 - Recall 4.1

Episode（情节）是原始输入的追溯单元，与 Memory、Entity、Relation 形成关联链：
Episode → Memory → Entity/Relation
"""

from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from enum import Enum


class EpisodeType(str, Enum):
    """情节类型"""
    TEXT = "text"           # 纯文本
    MESSAGE = "message"     # 对话消息
    JSON = "json"           # 结构化数据
    DOCUMENT = "document"   # 文档


@dataclass
class EpisodeNode:
    """情节节点 - 原始输入的追溯单元"""
    uuid: str = field(default_factory=lambda: str(uuid_lib.uuid4()))
    
    # 基本信息
    source_type: EpisodeType = EpisodeType.TEXT
    source_description: str = ""        # 来源描述（如 "用户对话"）
    content: str = ""                   # 原始内容
    
    # 时态信息
    valid_at: Optional[datetime] = None  # 原始文档时间（如果有）
    created_at: datetime = field(default_factory=datetime.now)
    
    # 关联信息
    user_id: str = ""
    character_id: str = ""
    group_id: str = ""
    
    # 产生的实体和关系
    memory_ids: List[str] = field(default_factory=list)
    entity_ids: List[str] = field(default_factory=list)
    relation_ids: List[str] = field(default_factory=list)
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'uuid': self.uuid,
            'source_type': self.source_type.value,
            'source_description': self.source_description,
            'content': self.content,
            'valid_at': self.valid_at.isoformat() if self.valid_at else None,
            'created_at': self.created_at.isoformat(),
            'user_id': self.user_id,
            'character_id': self.character_id,
            'group_id': self.group_id,
            'memory_ids': self.memory_ids,
            'entity_ids': self.entity_ids,
            'relation_ids': self.relation_ids,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodeNode':
        return cls(
            uuid=data.get('uuid', str(uuid_lib.uuid4())),
            source_type=EpisodeType(data.get('source_type', 'text')),
            source_description=data.get('source_description', ''),
            content=data.get('content', ''),
            valid_at=datetime.fromisoformat(data['valid_at']) if data.get('valid_at') else None,
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            user_id=data.get('user_id', ''),
            character_id=data.get('character_id', ''),
            group_id=data.get('group_id', ''),
            memory_ids=data.get('memory_ids', []),
            entity_ids=data.get('entity_ids', []),
            relation_ids=data.get('relation_ids', []),
            metadata=data.get('metadata', {}),
        )
```

---

### T6: 实体摘要生成

#### 6.1 新增文件

**文件路径**: `recall/processor/entity_summarizer.py`

```python
"""实体摘要生成器 - Recall 4.1

为实体自动生成摘要，总结实体的所有已知信息。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ..utils.llm_client import LLMClient


@dataclass
class EntitySummary:
    """实体摘要"""
    entity_name: str
    summary: str
    key_facts: List[str]
    relation_count: int
    mention_count: int
    last_updated: str = ""


SUMMARIZE_PROMPT = '''请为以下实体生成一个简洁的摘要。

## 实体名称：{entity_name}

## 相关事实：
{facts}

## 相关关系：
{relations}

## 输出要求：
1. 生成一个 2-3 句话的摘要，总结实体的核心信息
2. 列出 3-5 个关键事实要点

请用以下格式输出：
摘要：[摘要内容]
关键事实：
- [事实1]
- [事实2]
- [事实3]
'''


class EntitySummarizer:
    """实体摘要生成器"""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
    
    def generate(
        self,
        entity_name: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]],
        force_llm: bool = False
    ) -> EntitySummary:
        """生成实体摘要"""
        if self.llm_client and (force_llm or len(facts) > 3):
            return self._generate_with_llm(entity_name, facts, relations)
        else:
            return self._generate_simple(entity_name, facts, relations)
    
    def _generate_simple(
        self,
        entity_name: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]]
    ) -> EntitySummary:
        """简单规则生成"""
        key_facts = facts[:5]
        summary = f"{entity_name}。" + " ".join(key_facts[:2]) if key_facts else f"{entity_name}。"
        
        return EntitySummary(
            entity_name=entity_name,
            summary=summary,
            key_facts=key_facts,
            relation_count=len(relations),
            mention_count=len(facts)
        )
    
    def _generate_with_llm(
        self,
        entity_name: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]]
    ) -> EntitySummary:
        """LLM 生成"""
        facts_str = "\n".join([f"- {f}" for f in facts[:10]])
        relations_str = "\n".join([f"- {s} {r} {t}" for s, r, t in relations[:10]])
        
        prompt = SUMMARIZE_PROMPT.format(
            entity_name=entity_name,
            facts=facts_str or "（无）",
            relations=relations_str or "（无）"
        )
        
        try:
            response = self.llm_client.chat(prompt)
            return self._parse_response(entity_name, response, facts, relations)
        except Exception as e:
            print(f"[EntitySummarizer] LLM 失败: {e}")
            return self._generate_simple(entity_name, facts, relations)
    
    def _parse_response(
        self,
        entity_name: str,
        response: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]]
    ) -> EntitySummary:
        """解析 LLM 响应"""
        summary = ""
        key_facts = []
        
        lines = response.strip().split('\n')
        parsing_facts = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('摘要：') or line.startswith('摘要:'):
                summary = line.split('：', 1)[-1].split(':', 1)[-1].strip()
            elif '关键事实' in line:
                parsing_facts = True
            elif parsing_facts and line.startswith('-'):
                key_facts.append(line[1:].strip())
        
        if not summary:
            summary = response[:200]
        
        return EntitySummary(
            entity_name=entity_name,
            summary=summary,
            key_facts=key_facts or facts[:5],
            relation_count=len(relations),
            mention_count=len(facts)
        )
```

---

### T7: 动态实体属性

#### 7.1 修改文件

**文件**: `recall/index/entity_index.py`

在 `IndexedEntity` 数据类中添加新字段。将：

```python
@dataclass
class IndexedEntity:
    """索引中的实体"""
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    entity_type: str = "UNKNOWN"
    turn_references: List[str] = field(default_factory=list)
    confidence: float = 0.5
```

修改为：

```python
@dataclass
class IndexedEntity:
    """索引中的实体"""
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    entity_type: str = "UNKNOWN"
    turn_references: List[str] = field(default_factory=list)
    confidence: float = 0.5
    # === Recall 4.1 新增字段 ===
    summary: str = ""                           # 实体摘要
    attributes: Dict[str, Any] = field(default_factory=dict)  # 动态属性
    last_summary_update: Optional[str] = None   # 摘要最后更新时间
```

同时在文件顶部确保有导入：
```python
from typing import List, Dict, Any, Optional
```

---

## 配置说明

### 新增环境变量

在 `recall_data/config/api_keys.env` 末尾添加：

```bash
# ============================================
# Recall 4.1 新增配置
# ============================================

# === LLM 关系提取 ===
# 模式: rules / adaptive / llm
LLM_RELATION_MODE=rules
LLM_RELATION_COMPLEXITY_THRESHOLD=0.5
LLM_RELATION_ENABLE_TEMPORAL=true
LLM_RELATION_ENABLE_FACT_DESCRIPTION=true

# === 实体摘要 ===
# 是否启用实体摘要生成
ENTITY_SUMMARY_ENABLED=false
# 触发 LLM 摘要的最小事实数
ENTITY_SUMMARY_MIN_FACTS=5

# === Episode 追溯 ===
# 是否启用 Episode 追溯
EPISODE_TRACKING_ENABLED=false
```

### 配置优先级

1. 环境变量 > api_keys.env > 默认值
2. 所有新功能默认关闭，需要显式启用
3. 启用新功能不会影响现有数据

---

## 测试验证

### 测试用例清单

**文件**: `tests/test_v41_upgrade.py`

```python
"""Recall 4.1 升级测试"""

import pytest
import tempfile
import os


def test_llm_relation_extractor_rules_mode():
    """测试 LLM 关系提取器 - 规则模式"""
    from recall.graph.llm_relation_extractor import (
        LLMRelationExtractor, LLMRelationExtractorConfig, RelationExtractionMode
    )
    
    extractor = LLMRelationExtractor(
        config=LLMRelationExtractorConfig(mode=RelationExtractionMode.RULES)
    )
    
    text = "张三是李四的朋友，他们住在北京。"
    entities = ["张三", "李四", "北京"]
    
    relations = extractor.extract(text, entities)
    
    assert len(relations) >= 1
    assert any(r.relation_type == "IS_FRIEND_OF" for r in relations)


def test_llm_relation_extractor_backward_compatible():
    """测试向后兼容性"""
    from recall.graph.llm_relation_extractor import LLMRelationExtractor
    
    extractor = LLMRelationExtractor()
    
    # 使用 legacy 接口
    relations = extractor.extract_legacy("张三喜欢李四", entities=["张三", "李四"])
    
    assert isinstance(relations, list)
    assert all(isinstance(r, tuple) and len(r) == 4 for r in relations)


def test_entity_schema_registry():
    """测试实体类型注册表"""
    from recall.models.entity_schema import EntitySchemaRegistry, EntityTypeDefinition
    
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = EntitySchemaRegistry(tmpdir)
        
        # 检查内置类型
        assert registry.get("PERSON") is not None
        assert registry.get("LOCATION") is not None
        
        # 注册自定义类型
        registry.register(EntityTypeDefinition(
            name="CHARACTER",
            display_name="角色",
            description="故事中的角色"
        ))
        
        assert registry.get("CHARACTER") is not None


def test_episode_node():
    """测试 Episode 节点"""
    from recall.models.episode import EpisodeNode, EpisodeType
    
    ep = EpisodeNode(
        source_type=EpisodeType.MESSAGE,
        content="测试内容",
        user_id="user1",
        character_id="char1"
    )
    
    assert ep.uuid is not None
    assert ep.content == "测试内容"
    
    # 测试序列化
    data = ep.to_dict()
    assert data['source_type'] == 'message'
    
    # 测试反序列化
    ep2 = EpisodeNode.from_dict(data)
    assert ep2.content == ep.content


def test_entity_summarizer_simple():
    """测试实体摘要生成器 - 简单模式"""
    from recall.processor.entity_summarizer import EntitySummarizer
    
    summarizer = EntitySummarizer()  # 无 LLM
    
    summary = summarizer.generate(
        entity_name="张三",
        facts=["张三是程序员", "张三喜欢喝咖啡"],
        relations=[("张三", "WORKS_AT", "腾讯")]
    )
    
    assert summary.entity_name == "张三"
    assert len(summary.key_facts) <= 5


def test_existing_relation_extractor_unchanged():
    """测试现有 RelationExtractor 不受影响"""
    from recall.graph.relation_extractor import RelationExtractor
    
    extractor = RelationExtractor()
    relations = extractor.extract("张三喜欢李四", entities=["张三", "李四"])
    
    assert isinstance(relations, list)
    # 验证返回格式
    for rel in relations:
        assert isinstance(rel, tuple)
        assert len(rel) == 4


def test_existing_entity_extractor_unchanged():
    """测试现有 EntityExtractor 不受影响"""
    from recall.processor.entity_extractor import EntityExtractor
    
    extractor = EntityExtractor()
    entities = extractor.extract("张三和李四在北京见面")
    
    assert isinstance(entities, list)


def test_knowledge_graph_backward_compatible():
    """测试 KnowledgeGraph 向后兼容"""
    from recall.graph.knowledge_graph import KnowledgeGraph
    
    with tempfile.TemporaryDirectory() as tmpdir:
        kg = KnowledgeGraph(tmpdir)
        
        # 旧接口仍然可用
        rel = kg.add_relation(
            source_id="A",
            target_id="B",
            relation_type="KNOWS"
        )
        
        assert rel is not None
        
        # 新接口可选使用
        rel2 = kg.add_relation(
            source_id="C",
            target_id="D",
            relation_type="WORKS_AT",
            valid_at="2023-01-01",
            fact="C 在 D 工作"
        )
        
        assert rel2 is not None
```

### 运行测试

```bash
# 运行所有 v4.1 测试
python -m pytest tests/test_v41_upgrade.py -v

# 运行完整回归测试
python -m pytest tests/ -v --ignore=tests/test_stress.py
```

---

## 回滚方案

### 如何安全回滚

1. **配置回滚**：将所有新增配置设为关闭状态
   ```bash
   LLM_RELATION_MODE=rules
   ENTITY_SUMMARY_ENABLED=false
   EPISODE_TRACKING_ENABLED=false
   ```

2. **代码回滚**：删除新增文件（不影响现有功能）
   ```bash
   rm recall/graph/llm_relation_extractor.py
   rm recall/models/entity_schema.py
   rm recall/models/episode.py
   rm recall/processor/entity_summarizer.py
   ```

3. **数据兼容**：新增字段（如 `valid_at`、`summary`）在加载时会被忽略，不会导致错误

### 兼容性保证

| 组件 | 向后兼容 | 说明 |
|------|----------|------|
| RelationExtractor | ✅ 100% | 新方法在旧类基础上增加，不修改原有方法签名 |
| EntityExtractor | ✅ 100% | 不修改 |
| KnowledgeGraph | ✅ 100% | 新增字段有默认值，旧数据可正常加载 |
| Engine.add() | ✅ 100% | 使用条件分支，无 LLM 时降级到规则模式 |
| 检索系统 | ✅ 100% | 不修改 |

---

## 实施检查清单

### Phase 1: T1 + T2（LLM 关系提取 + 时态信息）

- [ ] 创建 `recall/graph/llm_relation_extractor.py`
- [ ] 修改 `recall/graph/__init__.py` 导出新类
- [ ] 修改 `recall/graph/knowledge_graph.py` 添加时态字段
- [ ] 修改 `recall/engine.py` 集成 LLM 关系提取器
- [ ] 添加配置项到 `api_keys.env`
- [ ] 添加配置项到 `start.ps1` / `start.sh`
- [ ] 编写测试用例
- [ ] 运行回归测试

### Phase 2: T3 + T4（自定义实体类型）

- [ ] 创建 `recall/models/entity_schema.py`
- [ ] 修改 `recall/processor/smart_extractor.py` 集成 Schema
- [ ] 修改 `recall/engine.py` 初始化 Schema Registry
- [ ] 编写测试用例
- [ ] 运行回归测试

### Phase 3: T5（Episode 追溯）

- [ ] 创建 `recall/models/episode.py`
- [ ] 创建 `recall/storage/episode_store.py`（可选）
- [ ] 修改 `recall/engine.py` 集成 Episode 追溯
- [ ] 编写测试用例
- [ ] 运行回归测试

### Phase 4: T6 + T7（摘要 + 动态属性）

- [ ] 创建 `recall/processor/entity_summarizer.py`
- [ ] 修改 `recall/index/entity_index.py` 添加字段
- [ ] 修改 `recall/engine.py` 集成摘要生成
- [ ] 编写测试用例
- [ ] 运行回归测试

---

## 总结

本升级计划的核心原则：

1. **向后兼容**：所有新功能默认关闭，需要显式启用
2. **渐进式**：可以按 Phase 分步实施，每个 Phase 独立可测试
3. **成本可控**：LLM 功能都有规则模式降级
4. **数据安全**：新增字段有默认值，不影响旧数据加载

预计实施时间：
- Phase 1：2-3 小时
- Phase 2：2-3 小时
- Phase 3：2-3 小时
- Phase 4：1-2 小时

总计：约 8-11 小时
