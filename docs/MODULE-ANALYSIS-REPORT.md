# Recall-ai 模块全面分析报告

> 分析范围：`recall/processor/`、`recall/graph/`、`recall/models/`、`recall/mode.py`、`recall/prompts/`
> 生成目的：为 Recall 7.0 UNIVERSAL MEMORY PLAN 提供模块级精确参考

---

## 目录

1. [recall/processor/ 模块分析](#1-recallprocessor-模块分析)
2. [recall/graph/ 模块分析](#2-recallgraph-模块分析)
3. [recall/models/ 模块分析](#3-recallmodels-模块分析)
4. [recall/mode.py 分析](#4-recallmodepy-分析)
5. [recall/prompts/ 分析](#5-recallprompts-分析)
6. [交叉引用与依赖图](#6-交叉引用与依赖图)
7. [RP 专用 vs 通用代码清单](#7-rp-专用-vs-通用代码清单)
8. [删除候选清单与风险评估](#8-删除候选清单与风险评估)
9. [Dead Code 分析](#9-dead-code-分析)

---

## 1. recall/processor/ 模块分析

**总文件数**：12 + `__init__.py` = 13 个 Python 文件  
**总代码行数**：约 7,999 行

### 1.1 `__init__.py` (83 行)

**用途**：统一导出所有 processor 类  
**导出清单**：

| 导出符号 | 来源文件 |
|---------|---------|
| `EntityExtractor`, `ExtractedEntity` | `entity_extractor.py` |
| `ConsistencyChecker`, `ViolationType`, `Violation`, `ConsistencyResult`, `AttributeType` | `consistency.py` |
| `MemorySummarizer`, `MemoryPriority`, `MemoryItem` | `memory_summarizer.py` |
| `ScenarioDetector`, `ScenarioType`, `ScenarioInfo` | `scenario.py` |
| `ContextTracker`, `ContextType`, `PersistentContext` | `context_tracker.py` |
| `SmartExtractor`, `SmartExtractorConfig`, `ExtractionMode`, `ExtractionResult`, `ExtractedRelation` | `smart_extractor.py` |
| `ThreeStageDeduplicator`, `DedupConfig`, `DedupResult` | `three_stage_deduplicator.py` |
| `EntitySummarizer`, `EntitySummary` | `entity_summarizer.py` |
| `UnifiedAnalyzer`, `UnifiedAnalysisResult`, `AnalysisTask` | `unified_analyzer.py` |
| `ForeshadowingTracker`, `Foreshadowing` | `foreshadowing.py` |
| `ForeshadowingAnalyzer`, `ForeshadowingAnalyzerConfig`, `AnalysisResult` | `foreshadowing_analyzer.py` |

---

### 1.2 `foreshadowing.py` (1,211 行) — ⛔ 待删除

**用途**：伏笔跟踪系统（纯 RP 功能）  
**RP 引用**：`character_id` 参数贯穿全部方法；存储路径 `{base}/{user_id}/{character_id}/foreshadowings.json`

**类与关键方法**：

| 类名 | 行号范围 | 描述 |
|------|---------|------|
| `ForeshadowingStatus(Enum)` | ~L47-51 | UNRESOLVED / POSSIBLY_TRIGGERED / RESOLVED |
| `Foreshadowing(dataclass)` | ~L54-113 | 伏笔数据模型（id, content, keywords, embedding, status 等） |
| `ForeshadowingTracker` | ~L116-1155 | 主跟踪器 |
| `ForeshadowingTrackerLite` | ~L1158-末尾 | 轻量版（无 embedding 依赖） |

**ForeshadowingTracker 方法一览**：

| 方法 | 描述 |
|------|------|
| `plant()` | 种植伏笔（含三级语义去重） |
| `resolve()` | 解决伏笔 |
| `abandon()` | 放弃伏笔 |
| `get_active()` | 获取活跃伏笔 |
| `get_by_entity()` | 按实体查找伏笔 |
| `get_summary()` | 获取伏笔摘要 |
| `get_context_for_prompt()` | 生成 prompt 注入文本 |
| `get_archived_foreshadowings()` | 获取归档伏笔（分页） |
| `restore_from_archive()` | 从归档恢复 |
| `delete_archived()` | 删除归档中的伏笔 |
| `clear_archived()` | 清空归档 |
| `clear_user()` | 清空用户数据 |
| `clear()` | 清空所有数据 |
| `archive_foreshadowing()` | 手动归档 |
| `update_foreshadowing()` | 更新伏笔 |
| `add_hint()` | 添加提示词 |

**engine.py 引用**：条件导入，仅当 `_mode.foreshadowing_enabled` 时加载（engine.py ~L292-298）

---

### 1.3 `foreshadowing_analyzer.py` (823 行) — ⛔ 待删除

**用途**：LLM 辅助伏笔分析器  

| 类名 | 行号范围 | 描述 |
|------|---------|------|
| `AnalyzerBackend(Enum)` | ~L65-67 | MANUAL / LLM |
| `ForeshadowingAnalyzerConfig(dataclass)` | ~L70-170 | 分析器配置 |
| `AnalysisResult(dataclass)` | ~L172-190 | 分析结果 |
| `ForeshadowingAnalyzer` | ~L193-823 | LLM 伏笔分析主类 |

**关键方法**：`on_new_turn()`, `trigger_analysis()`, `_trigger_llm_analysis()`, `_parse_llm_response()`, `enable_llm_mode()`, `disable_llm_mode()`, `update_config()`, `clear_user()`

**engine.py 引用**：条件导入（engine.py ~L294-296）

---

### 1.4 `scenario.py` (229 行) — ⚠️ 标记待删除但活跃使用中

**用途**：场景类型检测器

| 类名 | 行号范围 | 描述 |
|------|---------|------|
| `ScenarioType(Enum)` | ~L10-18 | ROLEPLAY / CODE_ASSIST / KNOWLEDGE_QA / CREATIVE / TASK / CHAT / UNKNOWN |
| `ScenarioInfo(dataclass)` | ~L21-34 | 场景信息 |
| `ScenarioDetector` | ~L37-229 | 场景检测器 |

**RP 引用**：  
- `ScenarioType.ROLEPLAY` 明确存在
- `detect()` ~L154：`from recall.mode import get_mode_config, RecallMode`，在通用模式下覆盖 RP 场景的检索策略

**⚠️ 关键发现**：虽然用户标记为删除，但 **engine.py 深度依赖此文件**：
- engine.py L24: `from .processor import ScenarioDetector`（顶层导入）
- engine.py L331: 实例化 `ScenarioDetector`
- engine.py L3029: 调用 `scenario = self._scenario_detector.detect(query)`
- engine.py L3544-3551: 根据 `scenario.type.value` 判断 roleplay/novel_writing/worldbuilding/coding 场景

**结论**：**不能直接删除**。需要先重构 engine.py 的场景检测逻辑，或改造 ScenarioDetector 去除 RP 专用代码。

---

### 1.5 `consistency.py` (1,440 行) — 🔀 RP/通用混合

**用途**：一致性检查器（属性冲突、状态冲突、时间线冲突、绝对规则检测）  

| 类名 | 行号范围 | 描述 |
|------|---------|------|
| `ViolationType(Enum)` | ~L37-44 | CHARACTER_CONFLICT / FACT_CONFLICT / STATE_CONFLICT / RELATIONSHIP_CONFLICT / TIMELINE_CONFLICT / AGE_INCONSISTENCY / LOGIC_ERROR |
| `AttributeType(Enum)` | ~L47-65 | AGE / HEIGHT / WEIGHT / HAIR_COLOR / EYE_COLOR / SKIN_COLOR / BLOOD_TYPE / GENDER / SPECIES / VITAL_STATUS / MARITAL_STATUS |
| `Violation(dataclass)` | ~L68-82 | 冲突结果 |
| `ConsistencyResult(dataclass)` | ~L85-97 | 检查结果汇总 |
| `TimelineEvent(dataclass)` | ~L100-108 | 时间线事件 |
| `ConsistencyChecker` | ~L111-末尾 | 主检查器 |

**RP 专用部分（需要改造/删除）**：

| 内容 | 行号范围 | RP 程度 |
|------|---------|---------|
| `from recall.mode import get_mode_config` | ~L207 | 模式系统依赖 |
| `self._mode = get_mode_config()` | ~L210 | 模式系统依赖 |
| `COLOR_SYNONYMS` | ~L139-170 | RP 强相关（角色外貌） |
| `RELATIONSHIP_OPPOSITES` | ~L173-185 | RP 强相关（朋友/敌人） |
| `STATE_OPPOSITES` | ~L188-202 | 部分通用（生死）、部分 RP（婚姻） |
| `STATE_NORMALIZATION` | ~L205-220 | RP 强相关 |
| 年龄/身高/体重提取模式 | ~L223-500 | **RP 专用**（角色属性提取） |
| 发色/眼色/血型/性别/种族提取 | ~L500-650 | **RP 专用**（角色外貌） |
| 生死/婚姻状态提取 | ~L650-720 | RP 强相关 |
| 关系/否定句提取 | ~L720-770 | 部分通用 |
| 属性冲突检测 | ~L780-860 | 通用框架，RP 属性类型 |
| 状态冲突检测 | ~L860-930 | 通用框架 |
| 时间线检测（完整版） | ~L960-1130 | **通用**（时态冲突、年龄推算、事件顺序） |
| 生死矛盾检测 | ~L1130-1200 | RP 强相关（角色死后行动） |
| 绝对规则检测（LLM） | ~L1250-1440 | **通用**（用户自定义规则 + LLM 语义检测） |

**通用部分（应保留）**：
- 时间线检测全套（`_check_tense_conflicts`, `_check_age_consistency`, `_check_event_sequence`）
- 绝对规则系统（`_check_absolute_rules`, `_check_rules_with_llm`, `update_rules`）
- 基础冲突框架（`record_fact`, `record_relationship`, `get_conflicts`, `get_entity_profile`, `get_summary`）

**模式门控**：`check()` 方法 ~L333: `rp_enabled = self._mode.rp_consistency_enabled` — RP 检查已有开关保护

**engine.py 引用**：L24 顶层导入，活跃使用

---

### 1.6 `context_tracker.py` (1,898 行) — 🔀 RP/通用混合

**用途**：持久上下文跟踪器（条件管理、LLM 提取、归档系统）

| 类名 | 行号范围 | 描述 |
|------|---------|------|
| `ContextType(Enum)` | ~L43-72 | 15 种上下文类型 |
| `RP_CONTEXT_TYPES` (set) | ~L75-82 | RP 专有类型集合 |
| `PersistentContext(dataclass)` | ~L86-138 | 持久上下文数据模型 |
| `ContextTracker` | ~L141-末尾 | 主跟踪器 |

**ContextType 枚举值分类**：

| 类型 | 值 | 分类 |
|------|-----|------|
| USER_IDENTITY | "user_identity" | ✅ 通用 |
| USER_GOAL | "user_goal" | ✅ 通用 |
| USER_PREFERENCE | "user_preference" | ✅ 通用 |
| ENVIRONMENT | "environment" | ✅ 通用 |
| PROJECT | "project" | ✅ 通用 |
| TIME_CONSTRAINT | "time_constraint" | ✅ 通用 |
| CHARACTER_TRAIT | "character_trait" | ⛔ RP |
| WORLD_SETTING | "world_setting" | ⛔ RP |
| RELATIONSHIP | "relationship" | ⛔ RP |
| EMOTIONAL_STATE | "emotional_state" | ⛔ RP |
| SKILL_ABILITY | "skill_ability" | ⛔ RP |
| ITEM_PROP | "item_prop" | ⛔ RP |
| ASSUMPTION | "assumption" | ✅ 通用 |
| CONSTRAINT | "constraint" | ✅ 通用 |
| CUSTOM | "custom" | ✅ 通用 |

**`RP_CONTEXT_TYPES` 集合**（L75-82）：
```python
RP_CONTEXT_TYPES = {
    ContextType.CHARACTER_TRAIT, ContextType.WORLD_SETTING,
    ContextType.RELATIONSHIP, ContextType.EMOTIONAL_STATE,
    ContextType.SKILL_ABILITY, ContextType.ITEM_PROP
}
```

**模式门控** (`extract_from_text()` ~L1563)：
```python
from recall.mode import get_mode_config
if not get_mode_config().rp_context_types:
    result = [ctx for ctx in result if ctx.context_type not in RP_CONTEXT_TYPES]
```

**关键方法一览**：

| 方法 | 描述 |
|------|------|
| `add()` | 添加持久上下文（三级去重：exact → embedding → word） |
| `get_active()` | 获取活跃上下文 |
| `get_by_type()` | 按类型过滤 |
| `deactivate()` | 停用上下文 |
| `mark_used()` / `mark_used_batch()` | 标记使用 |
| `extract_from_text()` | 从文本提取（LLM/规则） |
| `format_for_prompt()` | 生成 prompt 注入 |
| `get_relevant()` | 查询相关上下文 |
| `consolidate_contexts()` | LLM 压缩合并 |
| `archive_context()` | 手动归档 |
| `restore_from_archive()` | 从归档恢复 |
| `delete_archived()` | 删除归档 |
| `clear_archived()` | 清空归档 |
| `clear_user()` | 清空用户数据 |
| `clear()` | 清空所有数据 |
| `update_context()` | 更新条件字段 |
| `get_context_by_id()` | 按 ID 获取（含归档搜索） |
| `get_archived_contexts()` | 分页获取归档 |
| `get_stats()` | 统计信息 |

**存储路径**：`{base_path}/{user_id}/{character_id}/contexts.json`（含 archive/ 子目录）

**engine.py 引用**：L25 顶层导入 `ContextTracker, ContextType`

---

### 1.7 `entity_extractor.py` (324 行) — ✅ 通用

**用途**：实体提取（spaCy + jieba + regex）  

| 类名 | 描述 |
|------|------|
| `ExtractedEntity(dataclass)` | 提取结果 |
| `EntityExtractor` | 主提取器 |

**关键方法**：`extract()`, `_extract_with_regex()`, `_extract_with_spacy()`

**无 RP/character_id 引用。engine.py L23 导入。**

---

### 1.8 `entity_summarizer.py` (164 行) — ✅ 通用

**用途**：LLM 辅助实体摘要生成

| 类名 | 描述 |
|------|------|
| `EntitySummary(dataclass)` | 摘要结果 |
| `EntitySummarizer` | 主生成器 |

**方法**：`summarize_entity()`, `batch_summarize()`

**无 RP 引用。engine.py 延迟导入 ~L690。**

---

### 1.9 `memory_summarizer.py` (261 行) — ✅ 通用

**用途**：记忆压缩与摘要

| 类名 | 描述 |
|------|------|
| `MemoryPriority(Enum)` | LOW / NORMAL / HIGH / CRITICAL |
| `MemoryItem(dataclass)` | 记忆项 |
| `MemorySummarizer` | 主摘要器 |

**无 RP 引用。engine.py L24 导入。**

---

### 1.10 `smart_extractor.py` (660 行) — ✅ 通用

**用途**：三模式智能关系提取（Rules / Adaptive / LLM）

| 类名 | 描述 |
|------|------|
| `ExtractionMode(Enum)` | RULES / ADAPTIVE / LLM |
| `ExtractedRelation(dataclass)` | 提取的关系 |
| `ExtractionResult(dataclass)` | 提取结果 |
| `SmartExtractorConfig(dataclass)` | 配置 |
| `SmartExtractor` | 主提取器 |

**集成**：EntityExtractor + LLMClient + BudgetManager + EntitySchemaRegistry

**无 RP 引用。engine.py 延迟导入 ~L842。**

---

### 1.11 `three_stage_deduplicator.py` (625 行) — ✅ 通用

**用途**：三阶段去重（deterministic → semantic → LLM）

| 类名 | 描述 |
|------|------|
| `MatchType(Enum)` | EXACT / MINHASH / EMBEDDING / LLM |
| `DedupItem(dataclass)` | 去重项 |
| `DedupMatch(dataclass)` | 匹配结果 |
| `DedupResult(dataclass)` | 去重结果 |
| `DedupConfig(dataclass)` | 配置 |
| `MinHasher` | MinHash 指纹 |
| `LSHIndex` | LSH 索引 |
| `ThreeStageDeduplicator` | 主去重器 |

**无 RP 引用。engine.py 延迟导入 ~L896。**

---

### 1.12 `unified_analyzer.py` (281 行) — ✅ 通用

**用途**：统一分析器（单次 LLM 调用执行矛盾检测 + 关系提取 + 摘要生成）

| 类名 | 描述 |
|------|------|
| `AnalysisTask(Enum)` | CONTRADICTION / RELATION / SUMMARY |
| `UnifiedAnalysisInput(dataclass)` | 输入 |
| `UnifiedAnalysisResult(dataclass)` | 输出 |
| `UnifiedAnalyzer` | 主分析器 |

**无 RP 引用。engine.py 延迟导入 ~L717。**

---

## 2. recall/graph/ 模块分析

**总文件数**：7 + `__init__.py` + `backends/`(5+1) = 14 个 Python 文件  
**总代码行数**：约 5,379 行（不含 `__pycache__`）

### 2.1 `__init__.py` (58 行)

**导出**：

| 符号 | 来源 |
|------|------|
| `TemporalKnowledgeGraph` (别名 `KnowledgeGraph`) | `temporal_knowledge_graph.py` |
| `RelationExtractor` | `relation_extractor.py` |
| `ContradictionManager` | `contradiction_manager.py` |
| `QueryPlanner` | `query_planner.py` |
| `CommunityDetector` | `community_detector.py` |
| `GraphBackend`, `GraphNode`, `GraphEdge` | `backends/base.py` |
| `JSONGraphBackend` | `backends/json_backend.py` |
| `LegacyKnowledgeGraphAdapter` | `backends/legacy_adapter.py` |
| `create_graph_backend` | `backends/factory.py` |
| `LLMRelationExtractor` | `llm_relation_extractor.py` |

---

### 2.2 `knowledge_graph.py` (301 行) — 🔀 RP/通用混合

**用途**：知识图谱基类（被 TemporalKnowledgeGraph 取代但仍存在）

**RP_RELATION_TYPES 定义位置**（核心 RP 数据）：

```
L10-18:  get_relation_types() 函数 — 合并 RP + GENERAL types
L16:     from recall.mode import get_mode_config, RecallMode
L45-66:  RP_RELATION_TYPES (17 种)
L69-85:  GENERAL_RELATION_TYPES (15 种)
L88:     RELATION_TYPES = merged dict
```

**RP_RELATION_TYPES 完整列表**：
```
IS_FRIEND_OF, IS_ENEMY_OF, IS_FAMILY_OF, LOVES, HATES, KNOWS,
WORKS_FOR, MENTORS, LOCATED_IN, TRAVELS_TO, OWNS, LIVES_IN,
PARTICIPATED_IN, CAUSED, WITNESSED, CARRIES, USES, GAVE_TO, RECEIVED_FROM
```

**GENERAL_RELATION_TYPES 完整列表**：
```
RELATED_TO, BELONGS_TO, CONTAINS, DEPENDS_ON, DESCRIBES, DERIVED_FROM,
CONTRADICTS, SUPPORTS, PRECEDES, FOLLOWS, SIMILAR_TO, OPPOSITE_OF,
PART_OF, INSTANCE_OF, HAS_PROPERTY
```

| 类名 | 行号范围 | 描述 |
|------|---------|------|
| `Relation(dataclass)` | ~L22-38 | source_id, relation_type, target_id, confidence, source_text |
| `KnowledgeGraph` | ~L41-301 | 基础知识图谱（outgoing/incoming 字典、add_relation/query_relations/get_neighbors 等） |

---

### 2.3 `relation_extractor.py` (84 行) — 🔀 RP/通用混合

**用途**：基于正则的关系提取器

| 类名 | 描述 |
|------|------|
| `RelationExtractor` | 正则模式 + 共现关系提取 |

**RP 模式** (PATTERNS 列表)：包含中文 RP 关系模式（朋友/敌人/家人/老师/学生/上司/下属/爱上/喜欢/讨厌/住在/去了/拥有/给了）

**⚠️ 注意**：这些模式大部分适用于叙事场景，不仅限 RP。但 `IS_FRIEND_OF`, `IS_ENEMY_OF` 等关系类型来自 RP_RELATION_TYPES。

**engine.py 引用**：L21 顶层导入

---

### 2.4 `temporal_knowledge_graph.py` (2,130 行) — ✅ 通用

**用途**：v4.0 核心 — 三时态知识图谱

| 类名 | 行号范围 | 描述 |
|------|---------|------|
| `QueryResult(dataclass)` | ~L91-97 | 查询结果 |
| `TemporalKnowledgeGraph` | ~L100-2130 | 主类（nodes/edges/episodes 存储 + BFS/DFS + 矛盾检测） |

**特性**：
- 三时态：事实时间 + 知识时间 + 系统时间
- 双后端：file (JSON) / kuzu (嵌入式图数据库)
- 全文索引 + 时态索引
- 矛盾检测

**无 RP/character_id/mode 引用。engine.py L21 导入。**

---

### 2.5 `llm_relation_extractor.py` (370 行) — ✅ 通用

**用途**：v4.1 LLM 增强关系提取

| 类名 | 描述 |
|------|------|
| `RelationExtractionMode(Enum)` | RULES / ADAPTIVE / LLM |
| `ExtractedRelationV2(dataclass)` | 增强关系结构（含时态信息） |
| `LLMRelationExtractorConfig(dataclass)` | 配置 |
| `LLMRelationExtractor` | LLM 关系提取（在 `smart_extractor.py` 中集成） |

---

### 2.6 `contradiction_manager.py` (616 行) — ✅ 通用

**用途**：矛盾检测管理器

| 类名 | 描述 |
|------|------|
| `DetectionStrategy(Enum)` | RULE / LLM / MIXED / AUTO |
| `ContradictionRecord(dataclass)` | 矛盾记录 |
| `ContradictionManager` | 规则 + LLM 矛盾检测，支持自动/手动解决 |

**⚠️ 小问题**：`_register_default_rules()` 包含 `LOVES vs HATES`、`IS_FRIEND_OF vs IS_ENEMY_OF` 等 RP 互斥谓词对

---

### 2.7 `community_detector.py` (352 行) — ✅ 通用

**用途**：图社区检测（Louvain / Label Propagation / Connected Components）

| 类名 | 描述 |
|------|------|
| `Community(dataclass)` | 社区数据 |
| `CommunityDetector` | 检测器（需要 NetworkX，Lite 模式自动禁用） |

---

### 2.8 `query_planner.py` (361 行) — ✅ 通用

**用途**：图查询规划器（BFS 优化、路径缓存）

| 类名 | 描述 |
|------|------|
| `QueryOperation(Enum)` | SCAN / INDEX_LOOKUP / NEIGHBOR / FILTER / JOIN / CACHE_HIT |
| `QueryPlan(dataclass)` | 查询计划 |
| `QueryStats(dataclass)` | 查询统计 |
| `QueryPlanner` | 规划器 |

---

### 2.9 `backends/` 子目录 (5 + 1 文件)

| 文件 | 行数 | 描述 |
|------|------|------|
| `__init__.py` | 24 | 导出 |
| `base.py` | 282 | `GraphNode` / `GraphEdge` / `GraphBackend`(ABC) — 抽象接口 |
| `factory.py` | 215 | `create_graph_backend()` — 工厂函数（auto/file/kuzu/legacy） |
| `json_backend.py` | 362 | `JSONGraphBackend` — JSON 文件存储 |
| `kuzu_backend.py` | 446 | `KuzuGraphBackend` — Kuzu 嵌入式数据库 |
| `legacy_adapter.py` | 331 | `LegacyKnowledgeGraphAdapter` — 适配旧 KnowledgeGraph |

**所有 backends 文件均为通用代码，无 RP 引用。**

---

## 3. recall/models/ 模块分析

**总文件数**：7 + `__init__.py` = 8 个 Python 文件  
**总代码行数**：约 943 行

### 3.1 `__init__.py` (60 行)

**导出**：Entity, EntityType, EventType, ForeshadowingStatus, Relation, Turn, Foreshadowing, Event, EntitySchemaRegistry, AttributeType, AttributeDefinition, EntityTypeDefinition, + temporal 模型

### 3.2 `base.py` (22 行) — 🔀 RP/通用混合

| 枚举 | 值 |
|------|-----|
| `EntityType` | CHARACTER ⛔, ITEM ⛔, LOCATION ⛔, CONCEPT ✅, CODE_SYMBOL ✅ |
| `EventType` | STATE_CHANGE ✅, RELATIONSHIP ✅, ITEM_TRANSFER ⛔, FORESHADOWING ⛔, PLOT_POINT ⛔, CODE_CHANGE ✅ |
| `ForeshadowingStatus` | UNRESOLVED / POSSIBLY_TRIGGERED / RESOLVED ⛔ |

### 3.3 `foreshadowing.py` (20 行) — ⛔ 待删除

**用途**：Pydantic Foreshadowing 模型  
**注意**：这是与 `processor/foreshadowing.py` 中 `Foreshadowing(dataclass)` **不同**的模型定义。Pydantic 版本，字段包括：id, created_turn, content, summary, trigger_keywords, trigger_combinations, trigger_entities, content_embedding, status, resolution_turn, resolution_content, remind_after_turns, last_reminded, importance

### 3.4 `entity.py` (24 行) — ✅ 通用

Pydantic Entity / Relation 模型

### 3.5 `entity_schema.py` (207 行) — ✅ 通用

| 类名 | 描述 |
|------|------|
| `AttributeType(Enum)` | TEXT / NUMBER / ENUM / DATE / BOOLEAN |
| `AttributeDefinition(dataclass)` | 属性定义 |
| `EntityTypeDefinition(dataclass)` | 实体类型定义（含属性列表） |
| `EntitySchemaRegistry` | 注册表（BUILTIN_TYPES + 自定义类型，v4.1） |

**BUILTIN_TYPES**：person, organization, location, event, concept — **通用**

### 3.6 `event.py` (15 行) — ✅ 通用

Pydantic Event 模型

### 3.7 `temporal.py` (553 行) — ✅ 通用

v4.0 三时态数据模型：

| 类名 | 描述 |
|------|------|
| `NodeType(Enum)` | ENTITY / EPISODE / COMMUNITY |
| `EdgeType(Enum)` | FACT / TEMPORAL / SEMANTIC / CAUSAL / EPISODE_LINK |
| `ContradictionType(Enum)` | DIRECT / TEMPORAL / LOGICAL / CONTEXTUAL |
| `ResolutionStrategy(Enum)` | SUPERSEDE / COEXIST / REJECT / MANUAL |
| `TemporalFact(dataclass)` | 三时态事实 |
| `UnifiedNode(dataclass)` | 统一节点 |
| `EpisodicNode(dataclass)` | 情节节点 |
| `Contradiction(dataclass)` | 矛盾 |
| `ResolutionResult(dataclass)` | 解决结果 |
| `GraphIndexes` | 内存索引 |
| `entity_to_unified_node()` | 兼容转换 |
| `relation_to_temporal_fact()` | 兼容转换 |

### 3.8 `turn.py` (42 行) — ✅ 通用 (v5.0 已通用化)

字段：content, source, content_type, title, url, tags, category（通用） + user, assistant（兼容旧格式）

---

## 4. recall/mode.py 分析 (68 行) — ⛔ 待删除

**用途**：模式系统（控制 RP vs 通用功能开关）

| 类名/函数 | 描述 |
|---------|------|
| `RecallMode(Enum)` | ROLEPLAY / GENERAL / KNOWLEDGE_BASE |
| `ModeConfig(dataclass)` | mode + 5 个 boolean 开关 |
| `ModeConfig.from_env()` | 从 RECALL_MODE 环境变量读取 |
| `get_mode_config()` | 全局单例 |

**ModeConfig 字段**：
```python
mode: RecallMode
foreshadowing_enabled: bool
character_dimension_enabled: bool
rp_consistency_enabled: bool
rp_relation_types: bool
rp_context_types: bool
```

**被引用位置**：

| 文件 | 引用方式 |
|------|---------|
| `recall/engine.py` L11 | `from .mode import get_mode_config` |
| `recall/server.py` L18 | 导入 |
| `recall/processor/scenario.py` ~L154 | `from recall.mode import get_mode_config, RecallMode` |
| `recall/processor/consistency.py` ~L207 | `from recall.mode import get_mode_config` |
| `recall/processor/context_tracker.py` ~L1563 | `from recall.mode import get_mode_config` |
| `recall/graph/knowledge_graph.py` L16 | `from recall.mode import get_mode_config, RecallMode` |
| `recall/prompts/manager.py` L14 | `from recall.mode import RecallMode` |

**⚠️ 删除影响巨大**——有 7 个文件直接导入 mode.py。删除前必须在所有引用位置替换或移除模式系统。

---

## 5. recall/prompts/ 分析

> **重要发现**：`recall/prompts/manager.py` **已存在**（之前认为不存在是因为搜索 `prompt_manager.py` 而非 `prompts/manager.py`）

### 5.1 `manager.py` (58 行) — ⛔ 100% Dead Code

| 类名 | 描述 |
|------|------|
| `PromptManager` | YAML 模板加载 + str.format() 渲染 + 模式感知 |

**功能**：从 `recall/prompts/templates/*.yaml` 加载内置模板，从 `recall_data/prompts/` 加载用户覆盖模板

**依赖**：`from recall.mode import RecallMode`、`import yaml`

**⚠️ Dead Code 确认**：
- `engine.py` **零引用** PromptManager
- `server.py` **零引用** PromptManager
- 仅 `recall/prompts/__init__.py` 导出它
- `docs/PROMISE-AUDIT-REPORT.md` 明确标注："PromptManager ~1500行存在, engine.py 零引用 → 100% 死代码"

**templates/ 目录存在但内容未检查。**

---

## 6. 交叉引用与依赖图

### engine.py 的 processor/graph/models 导入

```
顶层导入:
├── from .mode import get_mode_config                    → mode.py
├── from .models import Entity, EntityType               → models/
├── from .graph import RelationExtractor, TemporalKnowledgeGraph → graph/
├── from .processor import (
│       EntityExtractor,                                  → processor/entity_extractor.py
│       ConsistencyChecker,                               → processor/consistency.py
│       MemorySummarizer,                                 → processor/memory_summarizer.py
│       ScenarioDetector,                                 → processor/scenario.py ⚠️
│       ContextTracker, ContextType                       → processor/context_tracker.py
│   )

条件导入 (仅 RP 模式):
├── ForeshadowingTracker      (~L300)                    → processor/foreshadowing.py ⛔
├── ForeshadowingAnalyzer     (~L308)                    → processor/foreshadowing_analyzer.py ⛔

延迟导入:
├── EntitySummarizer          (~L690)                    → processor/entity_summarizer.py
├── UnifiedAnalyzer           (~L717)                    → processor/unified_analyzer.py
├── SmartExtractor            (~L842)                    → processor/smart_extractor.py
├── ThreeStageDeduplicator    (~L896)                    → processor/three_stage_deduplicator.py
├── ExtractionMode            (~L2202)                   → processor/smart_extractor.py
```

### mode.py 的被依赖图

```
recall/mode.py
├── recall/engine.py
├── recall/server.py
├── recall/processor/scenario.py
├── recall/processor/consistency.py
├── recall/processor/context_tracker.py
├── recall/graph/knowledge_graph.py
└── recall/prompts/manager.py
```

---

## 7. RP 专用 vs 通用代码清单

### 纯 RP 文件（可整体删除）

| 文件 | 行数 | 说明 |
|------|------|------|
| `processor/foreshadowing.py` | 1,211 | 伏笔跟踪系统 |
| `processor/foreshadowing_analyzer.py` | 823 | LLM 伏笔分析 |
| `models/foreshadowing.py` | 20 | Pydantic 伏笔模型 |

### RP/通用混合文件（需要改造）

| 文件 | 行数 | RP 部分 | 通用部分 |
|------|------|---------|---------|
| `processor/scenario.py` | 229 | ScenarioType.ROLEPLAY, mode 检查 | 场景检测框架 ✅ |
| `processor/consistency.py` | 1,440 | 角色属性提取(~500行), 关系反义词, 颜色同义词 | 时间线检测, 绝对规则系统 |
| `processor/context_tracker.py` | 1,898 | 6 种 RP ContextTypes, RP_CONTEXT_TYPES 集合 | 9 种通用 ContextTypes, 完整跟踪/归档/去重系统 |
| `graph/knowledge_graph.py` | 301 | RP_RELATION_TYPES (17种) | GENERAL_RELATION_TYPES (15种) |
| `graph/relation_extractor.py` | 84 | 中文 RP 关系模式 | 共现提取框架 |
| `graph/contradiction_manager.py` | 616 | 互斥谓词对(LOVES/HATES) | 完整矛盾检测框架 |
| `models/base.py` | 22 | CHARACTER, ITEM, FORESHADOWING, PLOT_POINT, ITEM_TRANSFER | CONCEPT, CODE_SYMBOL, STATE_CHANGE, CODE_CHANGE |
| `mode.py` | 68 | 整个文件（模式系统） | — |

### 纯通用文件（无需修改）

| 文件 | 行数 |
|------|------|
| `processor/entity_extractor.py` | 324 |
| `processor/entity_summarizer.py` | 164 |
| `processor/memory_summarizer.py` | 261 |
| `processor/smart_extractor.py` | 660 |
| `processor/three_stage_deduplicator.py` | 625 |
| `processor/unified_analyzer.py` | 281 |
| `graph/temporal_knowledge_graph.py` | 2,130 |
| `graph/llm_relation_extractor.py` | 370 |
| `graph/community_detector.py` | 352 |
| `graph/query_planner.py` | 361 |
| `graph/backends/*` (全部) | 1,660 |
| `models/entity.py` | 24 |
| `models/entity_schema.py` | 207 |
| `models/event.py` | 15 |
| `models/temporal.py` | 553 |
| `models/turn.py` | 42 |

---

## 8. 删除候选清单与风险评估

### 可安全删除

| 文件 | 行数 | 风险 | 说明 |
|------|------|------|------|
| `processor/foreshadowing.py` | 1,211 | 🟢 低 | engine.py 条件导入，不影响通用模式 |
| `processor/foreshadowing_analyzer.py` | 823 | 🟢 低 | 同上 |
| `models/foreshadowing.py` | 20 | 🟢 低 | 仅 models/__init__.py 导出，需同步清理 |

### 需谨慎处理

| 文件 | 行数 | 风险 | 说明 |
|------|------|------|------|
| `processor/scenario.py` | 229 | 🔴 高 | engine.py L24/L331/L3029/L3544 深度依赖，**不能直接删除** |
| `mode.py` | 68 | 🔴 高 | 7 个文件直接导入，删除需全部替换 |
| `prompts/manager.py` | 58 | 🟢 低 | Dead code，但删除前确认 templates/ 不被其他地方引用 |

### 需改造而非删除

| 文件 | 改造内容 |
|------|---------|
| `consistency.py` | 剥离 ~500 行角色属性提取代码，保留时间线 + 绝对规则 |
| `context_tracker.py` | 移除 6 种 RP ContextTypes 及 RP_CONTEXT_TYPES 集合 |
| `knowledge_graph.py` | 移除 RP_RELATION_TYPES，仅保留 GENERAL_RELATION_TYPES |
| `relation_extractor.py` | 移除中文 RP 关系模式（朋友/敌人等） |
| `contradiction_manager.py` | 移除 RP 互斥谓词对或改为可配置 |
| `models/base.py` | 移除 CHARACTER, ITEM 等 RP EntityType；移除 FORESHADOWING, PLOT_POINT EventType |
| `models/__init__.py` | 清理 Foreshadowing, ForeshadowingStatus 导出 |
| `processor/__init__.py` | 清理 Foreshadowing*, ForeshadowingAnalyzer* 导出 |

---

## 9. Dead Code 分析

### 确认为 Dead Code（engine.py 和 server.py 均未使用）

| 符号 | 定义位置 | 原因 |
|------|---------|------|
| `PromptManager` | `recall/prompts/manager.py` | engine.py 零引用（audit 报告确认） |
| `ForeshadowingStatus` (base.py版) | `recall/models/base.py` | 仅被 models/__init__.py 导出，processor 有自己的版本 |

### 条件活跃代码（仅 RP 模式）

| 符号 | 定义位置 | 条件 |
|------|---------|------|
| `ForeshadowingTracker` | `processor/foreshadowing.py` | `_mode.foreshadowing_enabled` |
| `ForeshadowingAnalyzer` | `processor/foreshadowing_analyzer.py` | 同上 |
| `RP_RELATION_TYPES` | `graph/knowledge_graph.py` | `_mode.rp_relation_types` |
| `RP_CONTEXT_TYPES` 过滤 | `processor/context_tracker.py` | `_mode.rp_context_types` |
| RP 一致性检查 | `processor/consistency.py` | `_mode.rp_consistency_enabled` |

### 全量活跃代码

所有其余 processor、graph、models 模块均被 engine.py 或 server.py 直接/间接使用。

---

## 代码行数统计汇总

| 模块 | 文件数 | 总行数 | RP 代码行(估) | 通用代码行(估) |
|------|--------|--------|-------------|--------------|
| processor/ | 13 | ~7,999 | ~2,700 | ~5,299 |
| graph/ | 14 | ~5,379 | ~350 | ~5,029 |
| models/ | 8 | ~943 | ~60 | ~883 |
| mode.py | 1 | 68 | 68 | 0 |
| prompts/ | 3+ | ~80+ | 0 | 80 (dead) |
| **合计** | **39** | **~14,469** | **~3,178 (~22%)** | **~11,291 (~78%)** |

---

> **报告结论**：约 22% 的代码为 RP 专用或 RP/通用混合。纯 RP 文件（foreshadowing 系列）可安全删除约 2,054 行。混合文件改造涉及约 1,124 行 RP 代码的剥离/替换。`mode.py` 删除影响最广（7 个文件），应作为 7.0 改造的第一步。`scenario.py` **不能直接删除**（engine.py 深度依赖），需要先重构。`PromptManager` 是 100% dead code，应在 7.0 中决定是接入还是删除。
