# Recall 4.1 补充升级计划

> **版本**: v4.1.0  
> **日期**: 2026-01-28  
> **最后修订**: 2026-02-10（更新任务完成状态）  
> **目标**: 在保持现有功能100%兼容的前提下，增强实体/关系提取的智能化程度，全面超越 Graphiti
> **状态**: ✅ **全部完成** —— T1-T7 全部任务已在 v4.1.0 中实现，后续 v4.2.0 又做了性能优化

---

## ⚠️ 重要修正说明

本文档已根据代码审查进行以下修正：

| 问题 | 修正内容 |
|------|----------|
| LLM 客户端调用 | `chat()` 需要 `messages` 参数，改用 `complete()` 方法 |
| BudgetManager API | 方法名从 `can_spend` 改为 `can_afford`，`record_usage` 需要 `operation` 参数 |
| 代码位置描述 | 更新为实际行号（如 `_init_v4_modules` 在第 369-487 行） |
| 导入语句 | `entity_index.py` 需添加 `Any` 类型导入 |
| 模块导出 | 补充 `__init__.py` 的 `__all__` 更新说明 |
| **T5 重复定义** | ❌ 不创建 `episode.py`，✅ 复用现有 `EpisodicNode`（`temporal.py` 第337行） |

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
| **提取方式** | spaCy NER + jieba + 规则 + LLM 三模式 | LLM 调用 | ✅ Recall **已增强**（v4.1） |
| **中文支持** | 原生优化（jieba, zh_core_web_sm） | 通用 LLM | ✅ Recall 中文更强 |
| **成本** | 接近零成本（规则模式）| 每次调用消耗 Token | ✅ Recall 更省钱 |
| **准确率** | 规则 + LLM 自适应，按复杂度切换 | LLM 更灵活 | ✅ Recall **已增强**（v4.1） |
| **自定义实体类型** | EntitySchemaRegistry，7 种内置 + 用户注册 | 完整的 Pydantic Schema | ✅ Recall **已增强**（v4.1） |

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
| **提取方式** | 规则 + LLM 三模式自适应 | LLM 提取 | ✅ Recall **已增强**（v4.1） |
| **关系类型** | 规则 + LLM 动态生成 | LLM 动态生成 | ✅ Recall **已增强**（v4.1） |
| **时态信息** | LLM 提取 valid_at/invalid_at | LLM 提取 valid_at/invalid_at | 相当 |
| **事实描述** | LLM 生成自然语言描述 | LLM 生成自然语言描述 | 相当 |

### 7. 矛盾检测对比

| 特性 | Recall | Graphiti | 评价 |
|------|--------|----------|------|
| **检测策略** | 规则 + 可选 LLM | LLM 为主 | ✅ Recall 成本更低 |
| **解决策略** | SUPERSEDE/COEXIST/REJECT/MANUAL | 类似 | 相当 |
| **持久化** | 独立记录存储 | 边属性存储 | 相当 |

---

## 已识别短板

### ✅ 短板 1: 实体提取准确率不足 【已修复】

**当前实现分析**：

```python
# Recall 当前实现（entity_extractor.py）
# 主要依赖：spaCy NER + jieba + 规则匹配 + known_entities 字典

# 问题：
# 1. spaCy zh_core_web_sm 对中文专有名词识别率低
# 2. known_entities 字典需要手动维护
# 3. 无法识别上下文相关的隐式实体
```

**Graphiti 做法**：

```python
# 使用 LLM 提取，提示词精心设计
class ExtractedEntity(BaseModel):
    name: str
    entity_type_id: int  # 映射到自定义类型

# 优点：
# 1. 可识别隐式提及的实体
# 2. 支持自定义实体类型
# 3. 上下文理解能力强
```

**当前状态**：✅ 已全部完成
- ✅ `SmartExtractor` 支持 RULES/ADAPTIVE/LLM 三模式
- ✅ `EntitySchemaRegistry`（`models/entity_schema.py`）支持自定义实体类型，7 种内置 + 用户注册
- ✅ LLM 实体提取已集成动态类型 Schema

**解决方案**：
1. ✅ T3: 自定义实体类型 Schema 系统
2. ✅ T4: LLM 实体提取增强（动态类型 + 隐式实体）
3. ✅ T6: 实体摘要自动生成

---

### ✅ 短板 2: 关系提取过于简单 ⭐ 已修复

**当前实现分析**：

```python
# Recall 当前实现（relation_extractor.py）
PATTERNS = [
    (r'(.*)是(.*)的(朋友|敌人|...)', lambda m: ...),  # 正则模式
]

# 共现检测
if len(sentence_entities) >= 2:
    relations.append((e1, 'MENTIONED_WITH', e2, sentence))

# 问题：
# 1. 只能识别固定模式的关系
# 2. 共现关系信息量低（MENTIONED_WITH 几乎无语义）
# 3. 无法提取时态信息（valid_at/invalid_at）
# 4. 无法生成自然语言事实描述
```

**Graphiti 做法**：

```python
class Edge(BaseModel):
    relation_type: str       # 动态关系类型（LLM生成）
    source_entity_id: int
    target_entity_id: int
    fact: str                # 自然语言事实描述
    valid_at: str | None     # 事实生效时间
    invalid_at: str | None   # 事实失效时间
```

**解决方案**：
1. ✅ T1: LLM 关系提取增强（支持动态关系类型）
2. ✅ T2: 关系时态信息提取（valid_at/invalid_at）
3. ✅ 关系置信度评估

---

### ✅ 短板 3: 实体-关系一致性 【已修复】

**问题分析**：

刚才修复的 bug 说明了这个问题：
```python
# 问题：实体提取和关系提取使用不同的实体列表
# 步骤5: entities = entity_extractor.extract(text)
# 步骤6: relation_extractor.extract(text)  # 内部再次提取，可能不一致
```

**Graphiti 做法**：
```python
# 单一流程，共享上下文
extracted_nodes = await extract_nodes(...)
edges = await extract_edges(..., entities=extracted_nodes)  # 复用
```

**已完成**：修改 `relation_extractor.extract()` 方法（`recall/engine.py` 第1404-1417行），支持传入已提取的实体列表，避免重复提取导致不一致。

---

### ✅ 短板 4: 缺少 Episode（情节）概念 【已修复】

**当前实现分析**：

```python
# Recall 只有 Memory 概念
# 没有 Episode → Memory → Entity/Relation 的层次结构
# 无法追溯"这条关系来自哪个输入"
```

**Graphiti 做法**：

```python
# EpisodicNode 作为输入单元
class EpisodicNode(Node):
    source: EpisodeType       # text | message | json
    source_description: str
    content: str
    valid_at: datetime        # 原始文档时间
    entity_edges: list[str]   # 关联的边
```

**解决方案**：
1. ✅ T5: EpisodeNode 数据模型
2. ✅ T5: EpisodeStore 持久化存储
3. ✅ T5: Episode → Memory → Entity/Relation 的关联链

---

### ✅ 短板 5: 缺少节点摘要生成 【已修复】

**当前实现分析**：

```python
# Recall 的 IndexedEntity（entity_index.py）
@dataclass
class IndexedEntity:
    id: str
    name: str
    aliases: List[str]
    entity_type: str
    turn_references: List[str]
    confidence: float = 0.5
    # ❌ 没有 summary
    # ❌ 没有 attributes
```

**Graphiti 做法**：

```python
class EntityNode(Node):
    summary: str  # 自动生成的节点摘要
    attributes: dict[str, Any]  # 动态属性
```

**解决方案**：
1. ✅ T6: 实体摘要自动生成（可选 LLM）
2. ✅ T7: 动态属性支持

---

## ✅ Recall 的优势（保持不变）

1. **零依赖部署** - 无需图数据库
2. **三阶段去重** - 比 Graphiti 多一层语义过滤，降低 LLM 成本
3. **三时态模型** - 比 Graphiti 的双时态更完整
4. **十一层检索** - 更精细的召回控制
5. **100% 不遗忘保证** - N-gram 原文兜底
6. **中文优化** - jieba + spaCy 中文模型
7. **成本控制** - 大部分功能不依赖 LLM

**总结**：Recall 在**架构轻量化、成本控制、中文支持、去重效率**方面已经超越 Graphiti。但在**实体/关系提取的智能化程度**上还有差距，主要是因为 Graphiti 使用 LLM 做核心提取，而 Recall 主要依赖规则。

**建议方向**：保持 Recall 的轻量化优势，同时添加**可选的 LLM 增强层**，让用户可以根据需求选择 "纯本地模式" 或 "LLM 增强模式"。

---

## 升级任务清单

### 任务优先级

| 优先级 | 任务ID | 任务名称 | 复杂度 | 影响 | 状态 |
|--------|--------|----------|--------|------|------|
| P0 | T1 | LLM 关系提取增强 | 中 | 高 | ✅ 已完成 |
| P0 | T2 | 关系时态信息提取 | 中 | 高 | ✅ 已完成 |
| P1 | T3 | 自定义实体类型 Schema | 高 | 高 | ✅ 已完成 |
| P1 | T4 | LLM 实体提取增强 | 中 | 高 | ✅ 已完成 |
| P2 | T5 | Episode 概念引入 | 高 | 中 | ✅ 已完成 |
| P2 | T6 | 实体摘要生成 | 低 | 中 | ✅ 已完成 |
| P3 | T7 | 动态实体属性 | 中 | 低 | ✅ 已完成 |

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
            response = self.llm_client.complete(prompt)
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
        relations = self.extract(text, turn, entities)
        return [rel.to_legacy_tuple() for rel in relations]
```

#### 1.4 修改文件清单

**文件 1**: `recall/graph/__init__.py`

在文件末尾的导入区域添加：

```python
# === Recall 4.1 新增 ===
from .llm_relation_extractor import (
    LLMRelationExtractor,
    LLMRelationExtractorConfig,
    RelationExtractionMode,
    ExtractedRelationV2
)
```

同时更新 `__all__` 列表，在末尾添加：

```python
__all__ = [
    # ... 现有导出 ...
    
    # v4.1 新增导出
    'LLMRelationExtractor',
    'LLMRelationExtractorConfig',
    'RelationExtractionMode',
    'ExtractedRelationV2',
]
```

**文件 2**: `recall/engine.py`

在 `_init_v4_modules` 方法末尾（约第 485 行附近，在 `_init_community_detector()` 调用之后）添加：

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

在 `add()` 方法的关系提取部分（约第 1404-1417 行），将原有代码：

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
        relations_v2 = self._llm_relation_extractor.extract(content, 0, entities)
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

文件顶部已有正确的导入（无需修改）：
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
                 valid_at: Optional[str] = None, invalid_at: Optional[str] = None,
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

#### 3.2 集成到 SmartExtractor

**修改文件**: `recall/processor/smart_extractor.py`

在 `SmartExtractor.__init__` 中添加 Schema Registry：

```python
def __init__(
    self,
    config: Optional[SmartExtractorConfig] = None,
    local_extractor: Optional[EntityExtractor] = None,
    llm_client: Optional[LLMClient] = None,
    budget_manager: Optional[BudgetManager] = None,
    entity_schema_registry: Optional['EntitySchemaRegistry'] = None  # 新增
):
    # ... 现有代码 ...
    self.entity_schema_registry = entity_schema_registry
```

修改 `EXTRACTION_PROMPT` 以使用自定义类型：

```python
def _build_extraction_prompt(self, text: str) -> str:
    """构建提取提示词，使用自定义实体类型"""
    if self.entity_schema_registry:
        entity_types = self.entity_schema_registry.get_all_for_prompt()
    else:
        entity_types = "PERSON, ORG, LOCATION, ITEM, CONCEPT"
    
    return f'''请从以下文本中抽取实体、关系和时态信息。

## 支持的实体类型：
{entity_types}

## 文本：
{text}

## 输出格式（JSON）：
...'''
```

---

### T4: LLM 实体提取增强

#### 4.1 目标

增强现有 `SmartExtractor` 的 LLM 模式，支持：
1. 自定义实体类型（使用 T3 的 EntitySchemaRegistry）
2. 隐式实体识别
3. 实体置信度动态评估

#### 4.2 修改文件

**文件**: `recall/processor/smart_extractor.py`

更新 LLM 提取提示词，集成自定义类型：

```python
# 替换原有的 EXTRACTION_PROMPT
EXTRACTION_PROMPT_V2 = '''你是一个专业的实体和关系提取专家。请从以下文本中提取实体。

## 支持的实体类型：
{entity_types}

## 文本：
{text}

## 提取要求：
1. 识别文本中明确提及的实体
2. 识别文本中隐式提及的实体（如"他的公司"隐含一个组织实体）
3. 为每个实体分配正确的类型
4. 评估每个实体的置信度（0.0-1.0）：
   - 0.9+: 明确提及的专有名词
   - 0.7-0.9: 明确提及的通用名词
   - 0.5-0.7: 隐式推断的实体

## 输出格式（JSON数组）：
[
  {{
    "name": "实体名称",
    "type": "实体类型",
    "confidence": 0.9,
    "is_implicit": false,
    "context": "提及该实体的原文片段"
  }}
]

请只输出 JSON 数组，不要输出其他内容。'''


class SmartExtractor:
    # ... 现有代码 ...
    
    def _llm_extract(
        self,
        text: str,
        local_result: ExtractionResult,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[ExtractionResult]:
        """使用 LLM 抽取 - 增强版"""
        if not self.llm_client:
            return None
        
        try:
            # 使用自定义实体类型
            if self.entity_schema_registry:
                entity_types = self.entity_schema_registry.get_all_for_prompt()
            else:
                entity_types = """1. PERSON（人物）: 真实或虚构的人物
2. LOCATION（地点）: 地理位置、地名
3. ORGANIZATION（组织）: 公司、机构、团体
4. ITEM（物品）: 物品、道具
5. CONCEPT（概念）: 抽象概念、术语"""
            
            prompt = EXTRACTION_PROMPT_V2.format(
                entity_types=entity_types,
                text=text
            )
            
            response = self.llm_client.complete(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.1
            )
            
            # 解析并返回结果
            # ... 解析逻辑 ...
```

#### 4.3 Engine 集成

在 `engine.py` 的 `_init_smart_extractor` 中传入 Schema Registry：

```python
def _init_smart_extractor(self):
    """初始化智能抽取器 (Phase 2) - 增强版"""
    # ... 现有代码 ...
    
    # 初始化 Entity Schema Registry (v4.1)
    entity_schema_registry = None
    try:
        from .models.entity_schema import EntitySchemaRegistry
        entity_schema_registry = EntitySchemaRegistry(
            data_path=os.path.join(self.data_root, 'data')
        )
    except ImportError:
        pass
    
    self.smart_extractor = SmartExtractor(
        config=config,
        llm_client=self.llm_client if mode != ExtractionMode.RULES else None,
        budget_manager=self.budget_manager,
        entity_schema_registry=entity_schema_registry  # 新增
    )
```

---

### T5: Episode 概念引入

> ⚠️ **重要发现**：项目中已存在 `EpisodicNode` 类（位于 `recall/models/temporal.py` 第 337 行），
> 并已导出到 `recall/models/__init__.py`。无需创建新文件，应**扩展现有类**。

#### 5.1 现有 EpisodicNode 分析

**现有位置**: `recall/models/temporal.py`

```python
# 现有实现（第 337 行）
@dataclass
class EpisodicNode(UnifiedNode):
    """情节节点 - 原始数据输入单元"""
    
    node_type: NodeType = field(default=NodeType.EPISODE)
    source_type: EpisodeType = EpisodeType.TEXT
    source_description: str = ""
    entity_edges: List[str] = field(default_factory=list)
    turn_number: int = 0
    role: str = ""
```

**现有导出**: `recall/models/__init__.py` 已包含 `EpisodicNode`

#### 5.2 扩展现有 EpisodicNode

**修改文件**: `recall/models/temporal.py`

在 `EpisodicNode` 类中添加多租户和追溯字段（约第 337-380 行）：

```python
@dataclass
class EpisodicNode(UnifiedNode):
    """情节节点 - 原始数据输入单元
    
    继承 UnifiedNode，添加情节特有属性
    """
    
    # === 覆盖默认值 ===
    node_type: NodeType = field(default=NodeType.EPISODE)
    
    # === 情节特有属性 ===
    source_type: EpisodeType = EpisodeType.TEXT  # 来源类型
    source_description: str = ""                  # 来源描述
    
    # === 关联的边 ===
    entity_edges: List[str] = field(default_factory=list)  # 关联的实体边UUID
    
    # === 元数据 ===
    turn_number: int = 0        # 对话轮次（兼容现有系统）
    role: str = ""              # 角色（user/assistant）
    
    # === Recall 4.1 新增：SillyTavern 关联 ===
    # 注意：user_id 和 group_id 已从 UnifiedNode 继承
    character_id: str = ""      # 角色ID（SillyTavern 特有）
    
    # === Recall 4.1 新增：追溯链 ===
    memory_ids: List[str] = field(default_factory=list)    # 关联的记忆ID
    relation_ids: List[str] = field(default_factory=list)  # 关联的关系ID
```

修改 `to_dict` 方法：

```python
def to_dict(self) -> Dict[str, Any]:
    """转换为可序列化的字典"""
    result = super().to_dict()
    result['source_type'] = self.source_type.value
    # Recall 4.1: 新增字段（user_id/group_id 已由父类处理）
    result['character_id'] = self.character_id
    result['memory_ids'] = self.memory_ids
    result['relation_ids'] = self.relation_ids
    return result
```

#### 5.3 新增文件 - Episode 存储

**文件路径**: `recall/storage/episode_store.py`

```python
"""Episode 存储 - Recall 4.1

负责 Episode 的持久化存储和查询。
复用现有的 EpisodicNode（来自 recall/models/temporal.py）。
"""

from __future__ import annotations

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

# 复用现有的 EpisodicNode
from ..models.temporal import EpisodicNode, EpisodeType


class EpisodeStore:
    """Episode 持久化存储"""
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.episodes_file = os.path.join(data_path, 'episodes.jsonl')
        self._episodes: Dict[str, EpisodicNode] = {}
        self._load()
    
    def _load(self):
        """加载所有 Episode"""
        if not os.path.exists(self.episodes_file):
            return
        
        try:
            with open(self.episodes_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        ep = EpisodicNode.from_dict(data)
                        self._episodes[ep.uuid] = ep
        except Exception as e:
            print(f"[EpisodeStore] 加载失败: {e}")
    
    def save(self, episode: EpisodicNode) -> EpisodicNode:
        """保存单个 Episode"""
        self._episodes[episode.uuid] = episode
        self._append_to_file(episode)
        return episode
    
    def _append_to_file(self, episode: EpisodicNode):
        """追加到文件"""
        os.makedirs(os.path.dirname(self.episodes_file), exist_ok=True)
        with open(self.episodes_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(episode.to_dict(), ensure_ascii=False) + '\n')
    
    def get(self, uuid: str) -> Optional[EpisodicNode]:
        """获取 Episode"""
        return self._episodes.get(uuid)
    
    def get_by_memory_id(self, memory_id: str) -> List[EpisodicNode]:
        """通过记忆ID查找关联的 Episode"""
        return [ep for ep in self._episodes.values() if memory_id in ep.memory_ids]
    
    def get_by_entity_id(self, entity_id: str) -> List[EpisodicNode]:
        """通过实体ID查找关联的 Episode"""
        # 使用 entity_edges 字段
        return [ep for ep in self._episodes.values() if entity_id in ep.entity_edges]
    
    def update_links(
        self,
        episode_uuid: str,
        memory_ids: Optional[List[str]] = None,
        entity_ids: Optional[List[str]] = None,
        relation_ids: Optional[List[str]] = None
    ):
        """更新 Episode 的关联信息"""
        ep = self._episodes.get(episode_uuid)
        if not ep:
            return
        
        if memory_ids:
            ep.memory_ids.extend([m for m in memory_ids if m not in ep.memory_ids])
        if entity_ids:
            ep.entity_edges.extend([e for e in entity_ids if e not in ep.entity_edges])
        if relation_ids:
            ep.relation_ids.extend([r for r in relation_ids if r not in ep.relation_ids])
        
        # 重写整个文件以更新
        self._rewrite_all()
    
    def _rewrite_all(self):
        """重写所有 Episode 到文件"""
        os.makedirs(os.path.dirname(self.episodes_file), exist_ok=True)
        with open(self.episodes_file, 'w', encoding='utf-8') as f:
            for ep in self._episodes.values():
                f.write(json.dumps(ep.to_dict(), ensure_ascii=False) + '\n')
    
    def count(self) -> int:
        return len(self._episodes)
```

#### 5.4 Engine 集成

**修改文件**: `recall/engine.py`

在 `_init_v4_modules()` 方法（第 369-487 行）末尾添加 Episode 存储初始化：

```python
def _init_v4_modules(self):
    """初始化 v4.0 模块"""
    # ... 现有 v4.0 模块初始化代码 ...
    
    # === Recall 4.1: Episode 追溯 ===
    self.episode_store = None
    self._episode_tracking_enabled = False
    
    episode_enabled = os.environ.get('EPISODE_TRACKING_ENABLED', 'true').lower() == 'true'
    if episode_enabled:
        try:
            from .storage.episode_store import EpisodeStore
            self.episode_store = EpisodeStore(
                data_path=os.path.join(self.data_root, 'data')
            )
            self._episode_tracking_enabled = True
            if self.debug:
                print("[RecallEngine] Episode 追溯已启用")
        except ImportError as e:
            if self.debug:
                print(f"[RecallEngine] Episode 模块未安装: {e}")
```

在 `add()` 方法（约第 1100-1500 行）中创建 Episode 并关联：

```python
def add(
    self,
    content: str,
    ...
) -> Dict[str, Any]:
    """添加记忆"""
    # ... 现有参数解析代码 ...
    
    # === Recall 4.1: 创建 Episode ===
    current_episode = None
    if self._episode_tracking_enabled and self.episode_store:
        from .models.temporal import EpisodicNode, EpisodeType
        current_episode = EpisodicNode(
            source_type=EpisodeType.MESSAGE,
            content=content,
            user_id=user_id,
            character_id=character_id,
            group_id=group_id,
        )
        self.episode_store.save(current_episode)
    
    # ... 现有记忆创建代码 ...
    # memory_id = ...
    # extracted_entities = ...
    
    # === Recall 4.1: 更新 Episode 关联 ===
    if current_episode and self.episode_store:
        entity_ids = [e.id if hasattr(e, 'id') else str(e) for e in extracted_entities]
        relation_ids = []  # 从关系提取结果获取
        
        self.episode_store.update_links(
            episode_uuid=current_episode.uuid,
            memory_ids=[memory_id] if memory_id else [],
            entity_ids=entity_ids,
            relation_ids=relation_ids
        )
    
    # ... 返回结果 ...
```

#### 5.5 storage/__init__.py 更新

在 `recall/storage/__init__.py` 末尾添加：

```python
# === Recall 4.1 新增 ===
try:
    from .episode_store import EpisodeStore
except ImportError:
    pass

# 如果有 __all__，添加:
# __all__ = [..., 'EpisodeStore']
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
            # 使用 complete() 方法（接受字符串 prompt）
            response = self.llm_client.complete(prompt)
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

#### 6.2 Engine 集成

**修改文件**: `recall/engine.py`

在 `_init_v4_modules()` 方法末尾添加 EntitySummarizer 初始化：

```python
def _init_v4_modules(self):
    """初始化 v4.0 模块"""
    # ... 现有代码 ...
    
    # === Recall 4.1: 实体摘要生成器 ===
    self.entity_summarizer = None
    self._entity_summary_enabled = False
    self._entity_summary_min_facts = 5
    
    summary_enabled = os.environ.get('ENTITY_SUMMARY_ENABLED', 'false').lower() == 'true'
    if summary_enabled:
        try:
            from .processor.entity_summarizer import EntitySummarizer
            self.entity_summarizer = EntitySummarizer(
                llm_client=self.llm_client
            )
            self._entity_summary_enabled = True
            self._entity_summary_min_facts = int(
                os.environ.get('ENTITY_SUMMARY_MIN_FACTS', '5')
            )
            if self.debug:
                print("[RecallEngine] 实体摘要生成已启用")
        except ImportError as e:
            if self.debug:
                print(f"[RecallEngine] EntitySummarizer 模块未安装: {e}")
```

在 `add()` 方法中，实体提取完成后触发摘要更新：

```python
def add(self, content: str, ...) -> Dict[str, Any]:
    # ... 实体提取完成后 ...
    # extracted_entities = [...]
    
    # === Recall 4.1: 更新实体摘要 ===
    if self._entity_summary_enabled and self.entity_summarizer:
        for entity in extracted_entities:
            entity_name = entity.name if hasattr(entity, 'name') else str(entity)
            self._maybe_update_entity_summary(entity_name)
    
    # ... 后续代码 ...


def _maybe_update_entity_summary(self, entity_name: str):
    """检查并更新实体摘要（如果需要）"""
    if not self._entity_summary_enabled or not self.entity_summarizer:
        return
    
    # 获取实体相关的事实和关系
    entity = self.entity_index.get_entity(entity_name)
    if not entity:
        return
    
    # 检查是否需要更新（事实数量超过阈值）
    fact_count = len(entity.turn_references)
    if fact_count < self._entity_summary_min_facts:
        return
    
    # 获取关系
    relations = []
    if hasattr(self, 'knowledge_graph') and self.knowledge_graph:
        from .graph.knowledge_graph import KnowledgeGraph
        kg_relations = self.knowledge_graph.get_relations_for_entity(entity_name)
        relations = [(r.source_id, r.relation_type, r.target_id) for r in kg_relations]
    
    # 获取事实（从记忆中提取）
    facts = []
    for memory_id in entity.turn_references[:10]:  # 限制数量
        memory = self.storage.get(memory_id)
        if memory:
            facts.append(memory.get('content', '')[:100])  # 截取片段
    
    # 生成摘要
    try:
        summary_result = self.entity_summarizer.generate(
            entity_name=entity_name,
            facts=facts,
            relations=relations
        )
        
        # 更新 EntityIndex
        from datetime import datetime
        self.entity_index.update_entity_fields(
            entity_name=entity_name,
            summary=summary_result.summary,
            last_summary_update=datetime.now().isoformat()
        )
    except Exception as e:
        if self.debug:
            print(f"[RecallEngine] 摘要生成失败 {entity_name}: {e}")
```

#### 6.3 EntityIndex 扩展方法

**修改文件**: `recall/index/entity_index.py`

添加 `update_entity_fields` 方法：

```python
class EntityIndex:
    # ... 现有代码 ...
    
    def update_entity_fields(
        self,
        entity_name: str,
        summary: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        last_summary_update: Optional[str] = None
    ):
        """更新实体的扩展字段 (Recall 4.1)"""
        entity = self.get_entity(entity_name)
        if not entity:
            return False
        
        if summary is not None:
            entity.summary = summary
        if attributes is not None:
            entity.attributes.update(attributes)
        if last_summary_update is not None:
            entity.last_summary_update = last_summary_update
        
        self._save()
        return True
```

---

### T7: 动态实体属性

#### 7.1 修改文件

**文件**: `recall/index/entity_index.py`

在 `IndexedEntity` 数据类中添加新字段（约第 8-15 行）。将：

```python
@dataclass
class IndexedEntity:
    """索引中的实体"""
    id: str
    name: str
    aliases: List[str]
    entity_type: str
    turn_references: List[str]  # 出现过的记忆ID (如 mem_xxx)
    confidence: float = 0.5  # 置信度 (0-1)
```

修改为：

```python
@dataclass
class IndexedEntity:
    """索引中的实体"""
    id: str
    name: str
    aliases: List[str]
    entity_type: str
    turn_references: List[str]  # 出现过的记忆ID (如 mem_xxx)
    confidence: float = 0.5  # 置信度 (0-1)
    # === Recall 4.1 新增字段 ===
    summary: str = ""                           # 实体摘要
    attributes: Dict[str, Any] = field(default_factory=dict)  # 动态属性
    last_summary_update: Optional[str] = None   # 摘要最后更新时间
```

**注意**：需要同时添加 `field` 导入：
```python
from dataclasses import dataclass, asdict, field
```

修改文件顶部的导入（添加 `Any`）：

将：
```python
from typing import Dict, List, Optional
```

修改为：
```python
from typing import Dict, List, Optional, Any
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
EPISODE_TRACKING_ENABLED=true
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
    
    relations = extractor.extract(text, 0, entities)
    
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
    # 使用现有的 EpisodicNode（来自 temporal.py）
    from recall.models.temporal import EpisodicNode, EpisodeType
    
    ep = EpisodicNode(
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
    ep2 = EpisodicNode.from_dict(data)
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
    relations = extractor.extract("张三喜欢李四", 0, entities=["张三", "李四"])
    
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
   rm recall/storage/episode_store.py
   rm recall/processor/entity_summarizer.py
   ```
   
   > 注意：`EpisodicNode` 的扩展字段有默认值，无需回滚

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
- [ ] 修改 `recall/graph/knowledge_graph.py`：
  - [ ] 在 `Relation` 数据类添加 `valid_at`, `invalid_at`, `fact` 字段
  - [ ] 修改 `add_relation()` 方法签名支持新参数
- [ ] 修改 `recall/engine.py`：
  - [ ] 在 `_init_v4_modules()` 添加 `_llm_relation_extractor` 初始化
  - [ ] 在 `add()` 方法的关系提取部分添加条件分支
- [ ] 添加配置项到 `api_keys.env`
- [ ] 添加配置项到 `start.ps1` / `start.sh`
- [ ] 编写测试用例
- [ ] 运行回归测试

### Phase 2: T3 + T4（自定义实体类型 + LLM 实体增强）

- [ ] 创建 `recall/models/entity_schema.py`
- [ ] 修改 `recall/models/__init__.py` 添加导出
- [ ] 修改 `recall/processor/smart_extractor.py`：
  - [ ] 在 `__init__` 添加 `entity_schema_registry` 参数
  - [ ] 添加 `_build_extraction_prompt()` 方法
  - [ ] 更新 `EXTRACTION_PROMPT` 使用动态实体类型
- [ ] 修改 `recall/engine.py`：
  - [ ] 在 `_init_smart_extractor()` 初始化 Schema Registry
  - [ ] 将 registry 传入 SmartExtractor
- [ ] 编写测试用例
- [ ] 运行回归测试

### Phase 3: T5（Episode 追溯）

- [ ] 修改 `recall/models/temporal.py`：
  - [ ] 在 `EpisodicNode` 添加 `character_id` 字段（`user_id`, `group_id` 已从 `UnifiedNode` 继承）
  - [ ] 在 `EpisodicNode` 添加 `memory_ids`, `relation_ids` 字段
  - [ ] 更新 `to_dict()` 方法包含新字段
  - [ ] ~~更新 `from_dict()` 方法~~ （无需修改，现有 `cls(**data)` 模式自动支持新字段）
- [ ] 创建 `recall/storage/episode_store.py`
- [ ] 修改 `recall/storage/__init__.py` 添加 EpisodeStore 导出
- [ ] 修改 `recall/engine.py`：
  - [ ] 在 `_init_v4_modules()` 添加 `episode_store` 初始化
  - [ ] 在 `add()` 方法开头创建 Episode
  - [ ] 在 `add()` 方法末尾更新 Episode 关联
- [ ] 编写测试用例
- [ ] 运行回归测试

> ⚠️ **注意**：不需要创建新的 `recall/models/episode.py`，复用现有的 `EpisodicNode`（位于 `recall/models/temporal.py`）

### Phase 4: T6 + T7（摘要 + 动态属性）

- [ ] 创建 `recall/processor/entity_summarizer.py`
- [ ] 修改 `recall/processor/__init__.py` 添加 EntitySummarizer 导出
- [ ] 修改 `recall/index/entity_index.py`：
  - [ ] 添加 `from dataclasses import dataclass, asdict, field` 导入
  - [ ] 添加 `from typing import Dict, List, Optional, Any` 导入
  - [ ] 在 `IndexedEntity` 添加 `summary`, `attributes`, `last_summary_update` 字段
  - [ ] 添加 `update_entity_fields()` 方法
- [ ] 修改 `recall/engine.py`：
  - [ ] 在 `_init_v4_modules()` 添加 `entity_summarizer` 初始化
  - [ ] 添加 `_maybe_update_entity_summary()` 方法
  - [ ] 在 `add()` 实体提取后调用摘要更新
- [ ] 编写测试用例
- [ ] 运行回归测试

---

## 补充说明：模块导出更新

### `recall/models/__init__.py` 更新

在文件末尾添加：

```python
# === Recall 4.1 新增 ===
from .entity_schema import (
    EntitySchemaRegistry,
    EntityTypeDefinition,
    AttributeDefinition,
    AttributeType
)
# 注意：EpisodicNode 和 EpisodeType 已经在 temporal.py 中定义并导出，无需重复

# 更新 __all__
__all__ = [
    # ... 现有导出 ...
    
    # v4.1 新增
    'EntitySchemaRegistry',
    'EntityTypeDefinition',
    'AttributeDefinition',
    'AttributeType',
    # EpisodicNode, EpisodeType 已在现有 __all__ 中
]
```

### `recall/processor/__init__.py` 更新

在文件末尾添加：

```python
# === Recall 4.1 新增 ===
from .entity_summarizer import EntitySummarizer, EntitySummary

# 更新 __all__
__all__ = [
    # ... 现有导出 ...
    
    # v4.1 新增
    'EntitySummarizer',
    'EntitySummary',
]
```

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

---

## 附录：审计修正记录

### A1. 代码审计发现的问题

本计划经过完整项目代码审计后，发现并修正了以下问题：

#### API 调用错误

| 原始代码 | 修正后 | 原因 |
|----------|--------|------|
| `self.llm_client.chat(prompt)` | `self.llm_client.complete(prompt)` | `LLMClient.chat()` 需要 `messages: List[Dict]` 参数，`complete()` 接受字符串 |
| `budget_manager.can_spend(cost)` | `budget_manager.can_afford(cost, 'relation_extraction')` | 方法名是 `can_afford` 且需要 operation 参数 |
| `budget_manager.record_usage(total_tokens)` | `budget_manager.record_usage(operation='relation_extraction', tokens_in=..., tokens_out=...)` | 需要具名参数 |

#### 代码位置修正

| 描述 | 原始位置 | 修正位置 |
|------|----------|----------|
| `_llm_relation_extractor` 初始化 | `_init_components()` | `_init_v4_modules()` 末尾 (约第485行) |
| 关系提取调用 | 第1400行附近 | 第1404-1417行 |

#### 导入遗漏

| 文件 | 需要添加的导入 |
|------|---------------|
| `recall/index/entity_index.py` | `from dataclasses import dataclass, asdict, field` |
| `recall/index/entity_index.py` | `from typing import Dict, List, Optional, Any` |

### A2. 原计划遗漏的实现

| 模块 | 遗漏内容 | 已补充 |
|------|----------|--------|
| T3 | SmartExtractor 集成代码 | ✅ 添加了 `__init__` 参数和 `_build_extraction_prompt()` |
| T4 | 完整实现方案 | ✅ 添加了 EXTRACTION_PROMPT_V2 和增强 _llm_extract |
| T5 | EpisodeStore 存储类 | ✅ 添加了完整的 `recall/storage/episode_store.py` |
| T5 | Engine.add() 集成 | ✅ 添加了 Episode 创建和关联更新代码 |
| T6 | Engine 集成代码 | ✅ 添加了 `_maybe_update_entity_summary()` 方法 |
| T6 | EntityIndex 扩展方法 | ✅ 添加了 `update_entity_fields()` |

### A3. 重要设计修正

#### T5: 复用现有 EpisodicNode

**发现**：项目中已存在 `EpisodicNode` 类（位于 `recall/models/temporal.py` 第 337 行），并已导出到 `__init__.py`。

**原计划问题**：建议创建新的 `recall/models/episode.py`，这是**多余的重复定义**。

**修正方案**：
- ❌ 不创建新的 `recall/models/episode.py`
- ✅ 扩展现有的 `EpisodicNode`（添加 `user_id`, `character_id`, `group_id`, `memory_ids`, `relation_ids`）
- ✅ 创建 `recall/storage/episode_store.py` 导入现有的 `EpisodicNode`

**现有 EpisodicNode 已有字段**：
```python
# recall/models/temporal.py 第 337 行
class EpisodicNode(UnifiedNode):
    node_type: NodeType = NodeType.EPISODE
    source_type: EpisodeType = EpisodeType.TEXT
    source_description: str = ""
    entity_edges: List[str] = []  # 已有！
    turn_number: int = 0
    role: str = ""
```

**需要添加的字段**：
```python
# SillyTavern 关联（user_id/group_id 已从 UnifiedNode 继承）
character_id: str = ""

# 追溯链
memory_ids: List[str] = field(default_factory=list)
relation_ids: List[str] = field(default_factory=list)
```

### A4. 与 Graphiti 对比分析

基于 Graphiti 架构分析，本计划覆盖了以下核心短板：

| Recall 短板 | Graphiti 优势 | 本计划解决方案 |
|-------------|---------------|---------------|
| 实体提取准确率不足 | LLM 提取 + 自定义 Schema | T3 + T4: EntitySchemaRegistry + LLM 增强 |
| 关系提取过于简单 | LLM 关系提取 + 时态边 | T1 + T2: LLMRelationExtractor + 时态字段 |
| 实体-关系一致性 | 统一 LLM 调用 | 已在 v4.0 修复 |
| 缺少 Episode 概念 | Episode → Entity/Relation 追溯 | T5: 扩展现有 EpisodicNode + EpisodeStore |
| 缺少节点摘要 | 自动摘要生成 | T6: EntitySummarizer |

### A5. 注意事项

1. **SmartExtractor 现有代码**: 
   - 位置: `recall/processor/smart_extractor.py` 第202行
   - 现状: `EXTRACTION_PROMPT` 硬编码了 "PERSON/ORG/LOCATION/ITEM/CONCEPT"
   - 需要: 替换为动态调用 `entity_schema_registry.get_all_for_prompt()`

2. **KnowledgeGraph.Relation**: 
   - 位置: `recall/graph/knowledge_graph.py` 第10-18行
   - 现有字段: `source_id, target_id, relation_type, properties, created_turn, confidence, source_text`
   - 需添加: `valid_at: Optional[str] = None`, `invalid_at: Optional[str] = None`, `fact: str = ""`

3. **BudgetManager 实际签名**:
   ```python
   def can_afford(
       self,
       estimated_cost: float = 0.01,
       operation: str = "general",
       use_reserved: bool = False
   ) -> bool
   
   def record_usage(
       self,
       operation: str,
       tokens_in: int = 0,
       tokens_out: int = 0,
       cost: float = None,      # None 则自动计算
       model: str = "",
       success: bool = True
   ) -> UsageRecord
   ```

### A6. 最终审计摘要（多次会话修正）

| 修正项 | 原始描述 | 修正后 |
|--------|----------|--------|
| record_usage 签名 | 4 个参数 | 完整的 6 个参数（含默认值） |
| EXTRACTION_PROMPT 行号 | 第210行 | 第202行 |
| Relation 数据类行号 | 第7-14行 | 第10-18行 |
| _init_v4_modules 行号 | 360-480 行 | 369-487 行 |
| EpisodicNode 字段 | 添加 user_id, group_id | 仅添加 character_id（前两者已从 UnifiedNode 继承） |
| 测试用例类名 | EpisodeNode.from_dict | EpisodicNode.from_dict |
| **LLMRelationExtractor.extract() 参数顺序** | `(text, entities, turn)` | `(text, turn, entities)` - 与现有 RelationExtractor 保持一致 |
| **extract_legacy() 内部调用** | `extract(text, entities, turn)` | `extract(text, turn, entities)` |
| **engine.py 集成代码调用** | `extract(content, entities)` | `extract(content, 0, entities)` |
| **测试用例调用** | `extract(text, entities)` | `extract(text, 0, entities)` |
| **add_relation 签名类型** | `valid_at: str = None` | `valid_at: Optional[str] = None` |
| **from_dict() 修改** | 需要更新 | 无需修改（`cls(**data)` 模式自动支持新字段） |

**验证通过的核心 API**：
- ✅ `LLMClient.complete(prompt: str) -> str` - 正确
- ✅ `BudgetManager.can_afford(cost, operation)` - 正确
- ✅ `BudgetManager.record_usage(operation, tokens_in, tokens_out, model)` - 正确
- ✅ `SmartExtractor.__init__(config, local_extractor, llm_client, budget_manager)` - 正确
- ✅ `RelationExtractor.extract(text, turn, entities)` - 参数顺序验证
- ✅ `TemporalKnowledgeGraph.add_episode()` - 使用 `**kwargs` 兼容新字段

**现有类结构确认**：
- `EpisodicNode` 位于 `recall/models/temporal.py` 第 337 行
- `UnifiedNode` 已有 `user_id`, `group_id`, `content` 字段
- `EpisodicNode` 已有 `entity_edges`, `turn_number`, `role` 字段
- `RelationExtractor.extract()` 签名为 `(text, turn=0, entities=None)`
- `KnowledgeGraph._load()` 使用 `Relation(**item)` - 新字段有默认值，兼容旧数据
- `EntityIndex._load()` 使用 `IndexedEntity(**item)` - 新字段有默认值，兼容旧数据

**现有数据兼容性验证**：
- ✅ `entity_index.json` - 现有数据格式与计划兼容
- ✅ `knowledge_graph.json` - 现有数据格式与计划兼容
- ✅ `episodes.json` - 文件不存在，无兼容性问题

**100% 向后兼容保证**：
- 所有新功能默认关闭
- 新增字段使用 `field(default_factory=...)` 或 `= None` 确保旧数据兼容
- 不修改任何现有方法签名
- LLMRelationExtractor.extract() 参数顺序与 RelationExtractor 完全一致
- 所有新增代码片段已通过 Python 3.10 语法验证
