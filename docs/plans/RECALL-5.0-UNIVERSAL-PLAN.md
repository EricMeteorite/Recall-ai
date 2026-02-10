# Recall 5.0 通用化升级计划

> **创建日期**: 2026-02-10  
> **目标版本**: v5.0.0  
> **核心原则**: 👉 **所有改动通过配置开关控制，RP 模式功能完全保留，零破坏性变更** 👈

---

## 📋 目录

1. [现状诊断](#一现状诊断)
2. [全局模式开关设计](#二全局模式开关设计)
3. [Phase 1：核心通用化（无破坏改造）](#三phase-1核心通用化无破坏改造)
4. [Phase 2：性能瓶颈修复](#四phase-2性能瓶颈修复)
5. [Phase 3：批量写入与元数据索引](#五phase-3批量写入与元数据索引)
6. [Phase 4：MCP Server 实现](#六phase-4mcp-server-实现)
7. [Phase 5：Prompt 工程系统化](#七phase-5prompt-工程系统化)
8. [Phase 6：多 LLM 提供商自适应](#八phase-6多-llm-提供商自适应)
9. [Phase 7：重排序器多样性](#九phase-7重排序器多样性)
10. [改动文件清单与影响范围](#十改动文件清单与影响范围)
11. [实施顺序与时间估算](#十一实施顺序与时间估算)
12. [验证检查清单](#十二验证检查清单)

---

## 一、现状诊断

### 1.1 RP 耦合点清单（精确到行号）

| # | 文件 | 行号 | 耦合内容 | 严重度 |
|---|------|------|----------|:------:|
| 1 | `storage/layer0_core.py` | L14-16 | `character_card`, `world_setting`, `writing_style` 字段 | 中 |
| 2 | `storage/layer0_core.py` | L67-92 | `get_injection_text()` 硬编码 `roleplay/coding` 双分支 | 中 |
| 3 | `graph/knowledge_graph.py` | L30-57 | `RELATION_TYPES` — 19 种关系全部 RP 倾向，注释写 "针对 RP 场景优化" | 中 |
| 4 | `processor/consistency.py` | L50-71 | `AttributeType` 枚举 — 15 种属性中 11 种 RP 特化（HAIR_COLOR/SPECIES 等） | 中 |
| 5 | `processor/consistency.py` | L139-179 | `COLOR_SYNONYMS`, `RELATIONSHIP_OPPOSITES`, `STATE_OPPOSITES` 纯 RP 词典 | 中 |
| 6 | `processor/context_tracker.py` | L50-73 | `ContextType` 枚举 — 6/15 种为 RP 特化（CHARACTER_TRAIT/WORLD_SETTING 等） | 低 |
| 7 | `processor/foreshadowing.py` | 全文 1234 行 | 伏笔追踪器 — 纯 RP 叙事功能 | **高** |
| 8 | `processor/foreshadowing_analyzer.py` | 全文 852 行 | 伏笔 LLM 分析器 — 纯 RP | **高** |
| 9 | `engine.py` | L287-300 | 初始化 `foreshadowing_tracker/analyzer` | 高 |
| 10 | `engine.py` | L3297-3306 | `build_context()` 第 5 层硬注入活跃伏笔 | 高 |
| 11 | `engine.py` | L1303/2077/3179 | `character_id` 贯穿 `add()`(metadata提取)/`add_turn()`(显式参数)/`build_context()`(显式参数) | 中 |
| 12 | `server.py` | 16 个端点 | `/v1/foreshadowing/*` — 全部伏笔 API | 高 |
| 13 | `server.py` | 20+ 处 | `character_id` 参数贯穿几乎所有端点 | 中 |
| 14 | `storage/multi_tenant.py` | L17-21 | `character_id` 作为存储路径第二级维度 | 中 |
| 15 | `models/base.py` | L15-29 | `EventType.ITEM_TRANSFER/FORESHADOWING/PLOT_POINT` + `ForeshadowingStatus` 枚举 | 低 |
| 16 | `models/foreshadowing.py` | 全文 | 纯 RP 伏笔数据模型 | 低 |
| 17 | `models/temporal.py` | L45 | `NodeType.FORESHADOWING` | 低 |
| 18 | `processor/scenario.py` | L44-52 | RP 关键词/正则硬编码检测 | 低 |
| 19 | `processor/scenario.py` | L89 | `ROLEPLAY → entity_focused` 策略硬绑定 | 低 |

### 1.2 性能瓶颈清单

| # | 文件 | 行号 | 问题 | 严重度 |
|---|------|------|------|:------:|
| 1 | `index/temporal_index.py` | L276-338 | `query_at_time()` / `query_range()` — O(n) 全扫描，不用已有的排序列表 | **高** |
| 2 | `index/temporal_index.py` | L426/L454 | `query_before()` / `query_after()` — 同样 O(n) | 高 |
| 3 | `index/inverted_index.py` | L31-35 | `_save()` — 每次全量 JSON dump 整个索引 | **高** |
| 4 | `graph/backends/json_backend.py` | L143-157 | `add_node()` / `add_edge()` — 每次写操作触发全量 `_save()` | **高** |
| 5 | `storage/volume_manager.py` | L142-183 | `get_turn_by_memory_id()` — O(全磁盘) 逐行扫描 | 中 |
| 6 | `storage/volume_manager.py` | L185-245 | `search_content()` — O(全磁盘) 逐行扫描 | 中 |
| 7 | `index/ngram_index.py` | L154-191 | `_raw_text_fallback_search()` — O(n) 全内存扫描 | 中 |
| 8 | `engine.py` | L1280+ | 单次 `add()` — 10+ 次磁盘 IO、2-3 次网络调用、无批量优化 | **高** |
| 9 | （全局） | — | 无 batch/bulk API 端点 | **高** |

### 1.3 缺失能力清单

| # | 缺失能力 | 影响 |
|---|----------|------|
| 1 | 无全局模式开关（RP / 通用 / 知识库） | 无法切换场景 |
| 2 | 无元数据索引（source / tags / category） | 无法按来源/标签过滤 |
| 3 | 无批量写入 API | 爬虫等场景每条独立处理，吞吐量极低 |
| 4 | Turn 模型硬编码 user/assistant | 不支持单方数据（文章/爬虫内容） |
| 5 | 无 MCP Server | 无法接入 Claude Desktop/Cursor 等 |
| 6 | Prompt 硬编码散落在各模块 | 维护困难，无法定制 |
| 7 | LLM 仅支持 OpenAI 兼容 API | 不支持 Anthropic/Gemini 原生 SDK（需基于现有配置自适应） |
| 8 | 重排序器仅内置简单规则 | 无 Cohere Rerank 等专业重排序 |
| 9 | 通用关系类型缺失 | 知识图谱无法表达非 RP 关系 |

---

## 二、全局模式开关设计

### 2.1 核心原则

```
现有 RP 功能 → 100% 保留，默认行为不变
通用模式    → 通过 RECALL_MODE 环境变量切换
所有模块    → 检查模式开关，条件启用/禁用
```

### 2.2 新增环境变量

```bash
# 全局模式开关（新增）
RECALL_MODE=roleplay          # roleplay | general | knowledge_base
                               # 默认 roleplay（向后兼容）

# 模式控制的子开关（自动由 RECALL_MODE 推导，也可手动覆盖）
FORESHADOWING_ENABLED=true     # 伏笔系统开关（roleplay=true, 其他=false）
CHARACTER_DIMENSION_ENABLED=true  # character_id 维度开关（roleplay=true, 其他=false）
RP_CONSISTENCY_ENABLED=true    # RP 一致性检查开关（roleplay=true, 其他=false）
RP_RELATION_TYPES=true         # RP 关系类型开关（roleplay=true, 其他=false）
```

### 2.3 新增文件：`recall/mode.py`

```python
"""全局模式管理器 — 控制 RP/通用/知识库 模式切换"""

import os
from enum import Enum
from dataclasses import dataclass


class RecallMode(Enum):
    ROLEPLAY = "roleplay"          # RP 模式（默认，向后兼容）
    GENERAL = "general"            # 通用模式（爬虫、知识库、Agent）
    KNOWLEDGE_BASE = "knowledge_base"  # 知识库模式（纯知识管理）


@dataclass
class ModeConfig:
    """模式配置 — 根据模式自动推导子开关"""
    mode: RecallMode
    
    # RP 特性开关
    foreshadowing_enabled: bool
    character_dimension_enabled: bool
    rp_consistency_enabled: bool
    rp_relation_types: bool
    rp_context_types: bool
    
    @classmethod
    def from_env(cls) -> 'ModeConfig':
        mode_str = os.getenv('RECALL_MODE', 'roleplay').lower()
        if mode_str not in [m.value for m in RecallMode]:
            import logging
            logging.getLogger('recall.mode').warning(
                f"未知的 RECALL_MODE 值 '{mode_str}'，已回退到 'roleplay'。"
                f"有效值: {[m.value for m in RecallMode]}")
        mode = RecallMode(mode_str) if mode_str in [m.value for m in RecallMode] else RecallMode.ROLEPLAY
        
        # 模式默认值
        defaults = {
            RecallMode.ROLEPLAY: dict(foreshadowing=True, character=True, rp_consistency=True, rp_relations=True, rp_context=True),
            RecallMode.GENERAL: dict(foreshadowing=False, character=False, rp_consistency=False, rp_relations=False, rp_context=False),
            RecallMode.KNOWLEDGE_BASE: dict(foreshadowing=False, character=False, rp_consistency=False, rp_relations=False, rp_context=False),
        }
        d = defaults[mode]
        
        # 允许环境变量手动覆盖任意子开关
        def env_bool(key, default):
            val = os.getenv(key)
            return val.lower() in ('true', '1', 'yes') if val else default
        
        return cls(
            mode=mode,
            foreshadowing_enabled=env_bool('FORESHADOWING_ENABLED', d['foreshadowing']),
            character_dimension_enabled=env_bool('CHARACTER_DIMENSION_ENABLED', d['character']),
            rp_consistency_enabled=env_bool('RP_CONSISTENCY_ENABLED', d['rp_consistency']),
            rp_relation_types=env_bool('RP_RELATION_TYPES', d['rp_relations']),
            rp_context_types=env_bool('RP_CONTEXT_TYPES', d['rp_context']),
        )

# 全局单例
_mode_config: ModeConfig = None

def get_mode_config() -> ModeConfig:
    global _mode_config
    if _mode_config is None:
        _mode_config = ModeConfig.from_env()
    return _mode_config
```

### 2.4 各模块接入方式（零破坏）

每个受影响的模块只需在关键路径添加一行检查：

```python
from recall.mode import get_mode_config

# engine.py — build_context() 伏笔层
if get_mode_config().foreshadowing_enabled:
    foreshadowing_context = self.foreshadowing_tracker.get_context_for_prompt(...)
    if foreshadowing_context:
        parts.append(foreshadowing_context)

# engine.py — 初始化
if get_mode_config().foreshadowing_enabled:
    self.foreshadowing_tracker = ForeshadowingTracker(...)
    self.foreshadowing_analyzer = ForeshadowingAnalyzer(...)
else:
    self.foreshadowing_tracker = None
    self.foreshadowing_analyzer = None
```

---

## 三、Phase 1：核心通用化（无破坏改造）

> **目标**：通过配置开关让 Recall 能在 RP/通用/知识库 三种模式间切换，不删不改一行现有逻辑。同时统一所有配置管道。  
> **预计工作量**：4-5 天

### 任务 1.1：新建 `recall/mode.py` 模式管理器

**新建文件**：`recall/mode.py`

内容如上 §2.3 所示。定义 `RecallMode` 枚举、`ModeConfig` 数据类、`get_mode_config()` 全局单例。

**测试要求**：
- `RECALL_MODE` 不设置 → 默认 `roleplay` → 所有子开关为 `True`
- `RECALL_MODE=general` → 所有 RP 子开关为 `False`
- `RECALL_MODE=general` + `FORESHADOWING_ENABLED=true` → 只有伏笔开启

---

### 任务 1.2：engine.py 接入模式开关

**改动文件**：`recall/engine.py`  
**改动点**：4 处  
**改动行号**：L21-29, L287-300, L1303, L3297-3306

| 改动 | 原代码 | 新代码 | 行为变化 |
|------|--------|--------|----------|
| 导入 | 无条件导入 foreshadowing | 条件导入 | 通用模式不导入 |

> **⚠️ 重要**：engine.py 顶部（L22-27 范围）有 `from recall.processor.foreshadowing import ForeshadowingTracker` 和 `from recall.processor.foreshadowing_analyzer import ForeshadowingAnalyzer` 的顶层导入。实施时必须**删除这些顶层导入**，改为下方 `__init__` 中 `if self._mode.foreshadowing_enabled:` 内的条件导入。否则通用模式仍会加载伏笔模块并可能触发不必要的依赖。
| 初始化 | 无条件创建 tracker/analyzer | `if mode.foreshadowing_enabled:` | 通用模式跳过 |
| `add()` L1303 | `character_id` 从 metadata 提取后直接使用 | `if mode.character_dimension_enabled:` 使用，否则强制 `"default"` | 通用模式不隔离角色 |
| `build_context()` L5 伏笔层 | 无条件注入伏笔 | `if mode.foreshadowing_enabled:` | 通用模式跳过伏笔层 |

**关键实现**：

```python
# engine.py 顶部
from recall.mode import get_mode_config

class RecallEngine:
    def __init__(self, ...):
        self._mode = get_mode_config()
        
        # 伏笔系统（仅 RP 模式）
        if self._mode.foreshadowing_enabled:
            from recall.processor.foreshadowing import ForeshadowingTracker
            from recall.processor.foreshadowing_analyzer import ForeshadowingAnalyzer
            self.foreshadowing_tracker = ForeshadowingTracker(...)
            self.foreshadowing_analyzer = ForeshadowingAnalyzer(...)
        else:
            self.foreshadowing_tracker = None
            self.foreshadowing_analyzer = None
    
    def add(self, content, user_id="default", metadata=None, check_consistency=True):
        # ...
        # character_id 从 metadata 提取（L1303），非显式参数
        character_id = metadata.get('character_id', 'default') if metadata else 'default'
        
        # 非 RP 模式下强制为 default
        if not self._mode.character_dimension_enabled:
            character_id = "default"
        # ... 使用 character_id 进行存储隔离 ...
    
    def build_context(self, ..., character_id="default", ...):
        # character_id 在非 RP 模式下强制为 "default"
        if not self._mode.character_dimension_enabled:
            character_id = "default"
        
        # ... 其他层不变 ...
        
        # ========== 5. 伏笔层 ==========
        if self._mode.foreshadowing_enabled and self.foreshadowing_tracker:
            foreshadowing_context = self.foreshadowing_tracker.get_context_for_prompt(...)
            if foreshadowing_context:
                parts.append(foreshadowing_context)
```

**向后兼容保证**：
- `RECALL_MODE` 默认值是 `roleplay` → 所有行为与现在完全一致
- `character_id` 参数仍然接受，只是通用模式下忽略
- 伏笔 API 端点仍然注册，只是通用模式下返回空结果

---

### 任务 1.3：server.py 接入模式开关

**改动文件**：`recall/server.py`  
**改动点**：2 处

| 改动 | 说明 |
|------|------|
| 伏笔 API 端点 | 在 16 个伏笔端点入口添加模式检查，非 RP 模式返回 `{"message": "Foreshadowing is disabled in current mode", "mode": "general"}` |
| 新增 `/v1/mode` 端点 | GET 查询当前模式、所有子开关状态 |

```python
# server.py 新增端点
@app.get("/v1/mode")
async def get_mode():
    """查询当前模式配置"""
    mode = get_mode_config()
    return {
        "mode": mode.mode.value,
        "foreshadowing_enabled": mode.foreshadowing_enabled,
        "character_dimension_enabled": mode.character_dimension_enabled,
        "rp_consistency_enabled": mode.rp_consistency_enabled,
        "rp_relation_types": mode.rp_relation_types,
    }

# 伏笔端点加守卫
@app.post("/v1/foreshadowing")
async def create_foreshadowing(...):
    if not get_mode_config().foreshadowing_enabled:
        return JSONResponse(status_code=200, content={
            "message": "Foreshadowing disabled in current mode",
            "mode": get_mode_config().mode.value
        })
    # ... 原逻辑不变 ...
```

---

### 任务 1.4：CoreSettings 支持通用场景

**改动文件**：`recall/storage/layer0_core.py`  
**改动行号**：L67-92

**原代码**：
```python
if scenario == 'roleplay':
    scene_parts = [self.character_card, self.world_setting, self.writing_style]
elif scenario == 'coding':
    scene_parts = [self.code_standards, self.naming_conventions]
```

**新增逻辑**（在 `elif scenario == 'coding'` 之后追加）：
```python
elif scenario == 'general':
    # 通用模式：只注入绝对规则（absolute_rules 已在上方处理）
    scene_parts = []
```

**新增字段**（可选，在 CoreSettings 类中追加）：
```python
# 通用模式扩展字段（不影响现有字段）
domain_context: str = ""         # 领域上下文说明
data_schema: str = ""            # 数据结构描述
custom_instructions: str = ""    # 自定义指令
```

---

### 任务 1.5：关系类型通用化

**改动文件**：`recall/graph/knowledge_graph.py`  
**改动行号**：L30-57

**改动方式**：保留现有 19 种 RP 关系，新增通用关系类型，根据模式合并。同时需同步更新 `temporal_knowledge_graph.py`（L1609）中的 `RELATION_TYPES` 副本：

```python
# 原有 RP 关系（完全保留，原 19 种全部归入 RP）
RP_RELATION_TYPES = {
    # 人物关系（8）
    'IS_FRIEND_OF': '是朋友',
    'IS_ENEMY_OF': '是敌人',
    'IS_FAMILY_OF': '是家人',
    'LOVES': '爱慕',
    'HATES': '憎恨',
    'KNOWS': '认识',
    'WORKS_FOR': '为...工作',
    'MENTORS': '指导',
    # 空间关系（4）
    'LOCATED_IN': '位于',
    'TRAVELS_TO': '前往',
    'OWNS': '拥有',
    'LIVES_IN': '居住于',
    # 事件关系（3）
    'PARTICIPATED_IN': '参与了',
    'CAUSED': '导致了',
    'WITNESSED': '目击了',
    # 物品关系（4）
    'CARRIES': '携带',
    'USES': '使用',
    'GAVE_TO': '给予',
    'RECEIVED_FROM': '收到来自',
}

# 新增通用关系类型
GENERAL_RELATION_TYPES = {
    'RELATED_TO': '相关',
    'BELONGS_TO': '属于',
    'CONTAINS': '包含',
    'DEPENDS_ON': '依赖',
    'DESCRIBES': '描述',
    'DERIVED_FROM': '来源于',
    'CONTRADICTS': '矛盾',
    'SUPPORTS': '支持',
    'PRECEDES': '先于',
    'FOLLOWS': '后于',
    'SIMILAR_TO': '类似',
    'OPPOSITE_OF': '相反',
    'PART_OF': '是...的一部分',
    'INSTANCE_OF': '是...的实例',
    'HAS_PROPERTY': '具有属性',
}

# 动态合并
def get_relation_types():
    from recall.mode import get_mode_config
    mode = get_mode_config()
    types = GENERAL_RELATION_TYPES.copy()  # 通用类型始终可用
    if mode.rp_relation_types:
        types.update(RP_RELATION_TYPES)    # RP 模式追加 RP 类型
    return types

RELATION_TYPES = get_relation_types()  # 向后兼容
```

> **⚠️ 注意事项**：
> 1. `temporal_knowledge_graph.py`（L1609）中也有 `RELATION_TYPES` 的完整副本，必须同步改为引用 `knowledge_graph.py` 的 `get_relation_types()` 或删除重复定义。
> 2. `RELATION_TYPES = get_relation_types()` 在模块首次导入时执行。需确保 `recall.mode` 的环境变量在此之前已加载（正常启动流程保证此顺序；单元测试中可能需要设置 `RECALL_MODE` 环境变量）。

---

### 任务 1.6：一致性检查器条件化

**改动文件**：`recall/processor/consistency.py`  
**改动行号**：L126 类定义处

**改动方式**：在 `ConsistencyChecker.__init__()` 中读取模式：

```python
class ConsistencyChecker:
    def __init__(self, ...):
        from recall.mode import get_mode_config
        self._mode = get_mode_config()
        # ... 原逻辑不变 ...
    
    def check(self, ...):
        # RP 属性检测（发色/物种/生死等）仅在 RP 模式启用
        if self._mode.rp_consistency_enabled:
            self._check_attribute_conflicts(...)    # 原 _check_attribute_conflicts
            self._check_relationship_conflicts(...)  # 原 _check_relationship_conflicts
            self._check_state_conflicts(...)          # 原 _check_state_conflicts
            self._check_negation_violations(...)      # 原 _check_negation_violations
            self._check_death_consistency(...)        # 原 _check_death_consistency
        
        # 通用检测（时间线、绝对规则）始终启用
        self._check_timeline_full(...)                # 原 _check_timeline_full
        self._check_absolute_rules(...)               # 原 _check_absolute_rules
```

**效果**：通用模式下跳过发色/物种/生死/关系/否定句等 RP 属性检测，保留时间线检测和绝对规则检查。

---

### 任务 1.7：持久条件类型过滤

**改动文件**：`recall/processor/context_tracker.py`  
**改动行号**：L50-73 枚举定义处

**改动方式**：不修改枚举，在提取和注入时过滤：

```python
# 定义 RP 特化类型集合
RP_CONTEXT_TYPES = {
    ContextType.CHARACTER_TRAIT,
    ContextType.WORLD_SETTING,
    ContextType.RELATIONSHIP,
    ContextType.EMOTIONAL_STATE,
    ContextType.SKILL_ABILITY,
    ContextType.ITEM_PROP,
}

def extract_from_text(self, text, user_id, character_id):
    from recall.mode import get_mode_config
    mode = get_mode_config()
    
    contexts = self._do_extract(text, ...)  # 原逻辑
    
    # 非 RP 模式过滤掉 RP 特化类型
    if not mode.rp_context_types:
        contexts = [c for c in contexts if c.type not in RP_CONTEXT_TYPES]
    
    return contexts
```

---

### 任务 1.8：Turn 模型通用化

**改动文件**：`recall/models/turn.py`

**改动方式**：保留 `user/assistant` 字段，新增通用字段（向后兼容）：

```python
class Turn(BaseModel):
    """对话轮次 / 通用数据记录"""
    turn: int
    timestamp: datetime
    
    # 原有对话字段（向后兼容）
    user: str = ""                      # 改为可选（原为必填）
    assistant: str = ""                 # 改为可选（原为必填）
    
    # 通用字段（v5.0 新增）
    content: str = ""                   # 通用内容字段（爬虫/文档/文章等）
    source: str = ""                    # 数据来源（bilibili/github/manual 等）
    content_type: str = "conversation"  # conversation | article | document | crawled | custom
    title: str = ""                     # 标题（文章/帖子）
    url: str = ""                       # 原始 URL
    tags: List[str] = []                # 标签列表
    category: str = ""                  # 分类
    
    # 共有字段
    metadata: Dict[str, Any] = {}
    entities_mentioned: List[str] = []
    events_detected: List[str] = []
    ngrams_3: List[str] = []
    keywords: List[str] = []
    
    @property
    def effective_content(self) -> str:
        """获取有效内容（兼容对话和通用模式）"""
        if self.content:
            return self.content
        parts = []
        if self.user:
            parts.append(self.user)
        if self.assistant:
            parts.append(self.assistant)
        return "\n".join(parts)
```

**engine.py `add_turn()` 改动**：

```python
def add_turn(self, user_message="", ai_response="", 
             content="", source="", content_type="conversation",  # 新增
             user_id="default", character_id="default", metadata=None):
    """添加对话轮次或通用数据"""
    if content_type != "conversation" and content:
        # 通用模式：content 字段包含全部内容
        self.add(content, user_id=user_id, metadata={
            **(metadata or {}),
            'source': source,
            'content_type': content_type,
        })
    else:
        # 对话模式：原逻辑完全不变
        # ... 现有代码 ...
```

> **⚠️ 下游影响注意**：Turn 模型的 `user` 和 `assistant` 字段改为可选后（默认 `""`），以下代码路径可能受影响，实施时需检查：
> - `engine.py` 中 `turn.user` 的直接访问 → 通用模式下为空字符串，不会报错但语义可能不完整
> - `smart_extractor.py` 拼接 `turn.user + turn.assistant` 作为抽取内容 → 通用模式下应使用 `turn.effective_content`
> - `volume_manager.py` 中 `search_content()` 搜索 `turn.user` 和 `turn.assistant` → 通用模式下需同时搜索 `turn.content`
> - 建议：所有读取 Turn 内容的代码统一使用 `turn.effective_content` 属性，确保对话和通用模式下行为一致
```

---

### 任务 1.9：ScenarioDetector 通用场景支持

**改动文件**：`recall/processor/scenario.py`  
**改动行号**：L88-96

**改动方式**：新增通用场景的检索策略映射：

```python
# 原有映射保留
STRATEGY_MAP = {
    ScenarioType.ROLEPLAY: 'entity_focused',
    ScenarioType.CODE_ASSIST: 'keyword_focused',
    # ...
}

# 新增：通用模式下的策略覆盖
def get_strategy(self, scenario_type):
    from recall.mode import get_mode_config
    mode = get_mode_config()
    if mode.mode != RecallMode.ROLEPLAY and scenario_type == ScenarioType.ROLEPLAY:
        return 'balanced'  # 通用模式下不偏向实体检索
    return STRATEGY_MAP.get(scenario_type, 'balanced')
```

---

### 任务 1.10：新增配置到 SUPPORTED_CONFIG_KEYS

**改动文件**：`recall/server.py`  
**改动行号**：L97+

新增：
```python
# v5.0 全局模式配置
'RECALL_MODE',
'FORESHADOWING_ENABLED',
'CHARACTER_DIMENSION_ENABLED',
'RP_CONSISTENCY_ENABLED',
'RP_RELATION_TYPES',
'RP_CONTEXT_TYPES',
```

**v5.0 默认配置模板文本**（以下 5 处配置模板必须使用此精确文本：start.ps1 模板 / start.sh 模板 / manage.ps1 模板 / manage.sh 模板 / server.py get_default_config_content；另外 2 处仅需同步变量名：SUPPORTED_CONFIG_KEYS + engine.py/mode.py os.environ.get）：

```bash
# ============================================================================
# v5.0 全局模式配置 - RECALL 5.0 MODE CONFIGURATION
# ============================================================================

# ----------------------------------------------------------------------------
# 全局模式开关 / Global Mode Switch
# ----------------------------------------------------------------------------
# 模式: roleplay（角色扮演，默认）/ general（通用）/ knowledge_base（知识库）
# Mode: roleplay (default) / general / knowledge_base
RECALL_MODE=roleplay

# ----------------------------------------------------------------------------
# 模式子开关（自动由 RECALL_MODE 推导，也可手动覆盖）
# Mode Sub-switches (auto-derived from RECALL_MODE, can be overridden)
# ----------------------------------------------------------------------------
# 伏笔系统开关 / Foreshadowing system (roleplay=true, others=false)
FORESHADOWING_ENABLED=true
# 角色维度隔离 / Character dimension isolation (roleplay=true, others=false)
CHARACTER_DIMENSION_ENABLED=true
# RP 一致性检查 / RP consistency check (roleplay=true, others=false)
RP_CONSISTENCY_ENABLED=true
# RP 关系类型 / RP relation types (roleplay=true, others=false)
RP_RELATION_TYPES=true
# RP 上下文类型 / RP context types (roleplay=true, others=false)
RP_CONTEXT_TYPES=true

# ============================================================================
# v5.0 重排序器配置 - RECALL 5.0 RERANKER CONFIGURATION
# ============================================================================
# 重排序后端: builtin（内置）/ cohere / cross-encoder
# Reranker backend: builtin (default) / cohere / cross-encoder
RERANKER_BACKEND=builtin
# Cohere API 密钥（仅 cohere 后端需要）/ Cohere API key (cohere backend only)
COHERE_API_KEY=
# 自定义重排序模型名 / Custom reranker model name
RERANKER_MODEL=
```

---

### 任务 1.11：配置管道统一同步（跨平台一致性保证）

> **本任务是 5.0 升级的基础保障**：确保所有新增配置变量在 Windows/Linux 脚本、server.py、engine.py 中完全统一——包括变量名、默认值、注释说明。

**改动文件**：6 个脚本 + 2 个核心文件

| 文件 | 改动说明 |
|------|----------|
| `start.ps1` | `$supportedKeys` 数组追加 9 个 5.0 新变量；默认配置模板追加对应 section 和注释 |
| `start.sh` | `supported_keys` 字符串追加 9 个 5.0 新变量；默认配置模板追加对应 section 和注释 |
| `manage.ps1` | 嵌入的默认配置模板追加 v5.0 section；**UI 语言统一为中文**（当前为英文，与 manage.sh 不一致） |
| `manage.sh` | 嵌入的默认配置模板追加 v5.0 section |
| `server.py` | `get_default_config_content()` 函数追加 v5.0 section |
| `engine.py` | 修复 3 个硬编码默认值不一致问题（见下方） |

#### 1.11.1 修复 engine.py 现有默认值不一致

**问题**：`engine.py` L414-416 中，以下 3 个环境变量的硬编码默认值为 `'false'`，但配置模板中默认值为 `true`。当用户不经过 start 脚本直接启动时，这 3 个功能会意外禁用。

```python
# engine.py 当前代码（L414-416）— 需修复
temporal_enabled = os.environ.get('TEMPORAL_GRAPH_ENABLED', 'false')    # 应为 'true'
contradiction_enabled = os.environ.get('CONTRADICTION_DETECTION_ENABLED', 'false')  # 应为 'true'
fulltext_enabled = os.environ.get('FULLTEXT_ENABLED', 'false')          # 应为 'true'
```

**修复**：将这 3 处默认值从 `'false'` 改为 `'true'`，与配置模板保持一致。

#### 1.11.2 每个 Phase 完成后的配置同步清单

**Phase 1 完成后**，以下 6 个新变量必须同步到所有位置：

| 变量 | 默认值 | 配置模板注释 |
|------|--------|-------------|
| `RECALL_MODE` | `roleplay` | `# 全局模式：roleplay / general / knowledge_base` |
| `FORESHADOWING_ENABLED` | （留空，由 RECALL_MODE 推导） | `# 伏笔系统开关（自动由 RECALL_MODE 推导，手动设置可覆盖）` |
| `CHARACTER_DIMENSION_ENABLED` | （留空，由 RECALL_MODE 推导） | `# 角色维度隔离开关（自动由 RECALL_MODE 推导）` |
| `RP_CONSISTENCY_ENABLED` | （留空，由 RECALL_MODE 推导） | `# RP 一致性检查开关（自动由 RECALL_MODE 推导）` |
| `RP_RELATION_TYPES` | （留空，由 RECALL_MODE 推导） | `# RP 关系类型开关（自动由 RECALL_MODE 推导）` |
| `RP_CONTEXT_TYPES` | （留空，由 RECALL_MODE 推导） | `# RP 持久条件类型开关（自动由 RECALL_MODE 推导）` |

**Phase 6 完成后**：无新增配置变量。多 LLM 提供商支持完全基于现有的 `LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL` 自动检测，零配置变更。仅需在 `pyproject.toml` 中添加 anthropic / google-generativeai 可选依赖。

**Phase 7 完成后**，以下 3 个新变量必须同步：

| 变量 | 默认值 | 注释 |
|------|--------|------|
| `RERANKER_BACKEND` | `builtin` | `# 重排序后端：builtin / cohere / cross-encoder` |
| `COHERE_API_KEY` | （留空） | `# Cohere Rerank API 密钥` |
| `RERANKER_MODEL` | （留空） | `# 自定义重排序模型名` |

**同步目标位置清单**（每次新增环境变量必须同时更新以下 7 处）：

1. `recall/server.py` → `SUPPORTED_CONFIG_KEYS`
2. `recall/server.py` → `get_default_config_content()`
3. `start.ps1` → `$supportedKeys` 数组
4. `start.sh` → `supported_keys` 字符串
5. `manage.ps1` → 嵌入的默认配置模板
6. `manage.sh` → 嵌入的默认配置模板
7. `recall/engine.py` / `recall/mode.py` → `os.environ.get()` 调用

#### 1.11.3 统一 manage.ps1 / manage.sh UI 语言

**问题**：`manage.ps1` 全英文界面（`Main Menu`, `Install Recall-ai`, `Start Service` 等），`manage.sh` 全中文界面（`主菜单`, `🔧 安装 Recall-ai`, `🚀 启动服务` 等）。

**修复**：将 `manage.ps1` 的 UI 文本统一为中文（与 `manage.sh` 一致），包括：
- Banner 副标题
- 主菜单选项文本
- 子菜单文本
- 状态显示文本
- 所有提示信息

#### 1.11.4 统一 start.ps1 / start.sh 配置模板微差异

**问题**（共 15 处差异）：

**start.ps1 vs start.sh 差异（9 处，以 start.ps1 为基准）：**

| # | 差异位置 | start.ps1（基准） | start.sh（待修复） |
|---|---------|------------|----------|
| 1 | Phase 3.6 英文标题 | `Triple Recall Configuration` | `Triple Parallel Recall` |
| 2 | Triple Recall 中文括号 | 半角 `(100% 不遗忘保证)` | 全角 `（100%不遗忘保证）` |
| 3 | TRIPLE_RECALL 描述 | `IVF-HNSW + 倒排 + 实体，RRF融合` | `语义+关键词+实体` |
| 4 | RRF 子节标题 | `RRF 融合配置` | `Triple Recall 主开关与 RRF 融合配置` |
| 5 | RRF_K 注释 | `越大排名差异越平滑` | `越大排名越平滑` |
| 6 | 权重注释详细度 | 详细 (`Path 1: IVF-HNSW`) | 简略 (`path 1`)（3 条路径均如此） |
| 7 | IVF-HNSW 子节标题 | `IVF-HNSW 参数 (提升召回率至 95-99%)` | `IVF-HNSW 向量索引参数` |
| 8 | Fallback 子节标题 | `原文兜底配置 (100% 保证)` | `原文兜底配置`（缺 `100% 保证`） |
| 9 | v4.1 section 标题格式 | `╔═══╗` box 包裹 | `============` 标准分隔线 |

**跨模板额外差异（6 处）：**

| # | 差异位置 | 说明 | 修复方式 |
|---|---------|------|---------|
| 10 | "时态知识图谱配置"子标题格式 | start.ps1 有完整标题+双分隔线；start.sh 仅双分隔线无标题文字；server.py 仅中文+单分隔线；**manage.ps1 和 manage.sh 完全缺失此子标题** | 统一为 start.ps1 格式（manage.ps1/manage.sh 需新增） |
| 11 | server.py LLM Max Tokens 节 | server.py 有 4 行额外说明文字，其他 4 个模板无 | 删除 server.py 多余说明 |
| 12 | server.py Retrieval/Dedup LLM Max Tokens 注释 | server.py: `通常较小`/`filtering`；其他: `只需 yes/no，较小即可`/`filter (only yes/no, keep small)` | 统一为后者 |
| 13 | server.py Smart Extractor Max Tokens 英文注释 | server.py: `smart extraction`；其他: `smart extractor` | 统一为 `smart extractor` |
| 14 | manage.sh v4.1 section 标题格式 | manage.sh 也使用 `============` 而非 `╔═══╗`（与 #9 同一问题） | 统一为 `╔═══╗` 格式 |
| 15 | start.sh 路径权重注释 | start.sh 的 Path 2/3 权重注释也简略（非仅 Path 1） | 3 条路径全部统一为详细格式 |
| 16 | server.py LLM Max Tokens 各条注释措辞 | server.py: `通用场景`/`Default max tokens for LLM calls`/`实体多时需要更多`；其他: `通用默认值`/`Default max tokens for LLM output`/`实体多时需要大值` | 统一为其他 4 个模板格式 |
| 17 | start.sh IVF-HNSW 单参数注释格式 | start.ps1: `HNSW 图连接数（越大召回越高，内存越大，推荐 32）`；start.sh: `HNSW 图连接数 M（推荐 32，越大精度越高但构建越慢）`（EF_CONSTRUCTION/EF_SEARCH 同理） | 统一为 start.ps1 格式 |

**修复**：以 `start.ps1` 为基准，将 `start.sh` 的 9 处全部统一。同时修复跨模板的 8 处差异：统一“时态知识图谱配置”子标题格式；删除 `server.py` 中 LLM Max Tokens 节多余说明文字；统一注释措辞；修复 `manage.sh` 的 v4.1 标题格式；统一 LLM Max Tokens 各条注释；统一 IVF-HNSW 单参数注释。

> **原则**：所有 5 处配置模板（start.ps1, start.sh, manage.ps1, manage.sh, server.py get_default_config_content）的每一行必须字符级别完全一致。共计 **17 处差异**需统一。

---

## 四、Phase 2：性能瓶颈修复

> **目标**：修复所有 O(n) 查询和全量序列化问题，使 Recall 能够处理百万级数据。  
> **预计工作量**：4-5 天

### 任务 2.1：时态索引利用排序列表实现 O(log n) 查询

**改动文件**：`recall/index/temporal_index.py`  
**改动行号**：L276-338, L426-487

**问题**：代码已用 `bisect.insort()` 维护了 `_sorted_by_fact_start` 等排序列表，但 `query_at_time()`、`query_range()`、`query_before()`、`query_after()` 全部使用 `for doc_id, entry in self.entries.items()` 暴力遍历。

**修复方案**：

```python
def query_at_time(self, point, time_type='fact'):
    """使用二分查找 — O(log n) + O(k) 而非 O(n)"""
    ts = point.timestamp()
    
    if time_type == 'fact':
        # 找到所有 fact_start <= point 的条目（二分搜索）
        idx = bisect.bisect_right(self._sorted_by_fact_start, (ts, '\xff'))
        candidates = [doc_id for _, doc_id in self._sorted_by_fact_start[:idx]]
        
        # 再过滤 fact_end >= point
        results = []
        for doc_id in candidates:
            entry = self.entries.get(doc_id)
            if entry and entry.fact_range.contains(point):
                results.append(doc_id)
        return results
    
    elif time_type == 'known':
        idx = bisect.bisect_right(self._sorted_by_known_at, (ts, '\xff'))
        return [doc_id for _, doc_id in self._sorted_by_known_at[:idx]]
    
    elif time_type == 'system':
        idx = bisect.bisect_right(self._sorted_by_system_start, (ts, '\xff'))
        candidates = [doc_id for _, doc_id in self._sorted_by_system_start[:idx]]
        results = []
        for doc_id in candidates:
            entry = self.entries.get(doc_id)
            if entry and entry.system_range.contains(point):
                results.append(doc_id)
        return results

def query_range(self, start, end, time_type='fact'):
    """使用二分查找范围 — O(log n + k)"""
    if time_type == 'fact':
        sorted_list = self._sorted_by_fact_start
    elif time_type == 'system':
        sorted_list = self._sorted_by_system_start
    else:
        return []
    
    query_tr = TimeRange(start=start, end=end)
    
    # 二分找到 start 位置
    if end:
        end_ts = end.timestamp()
        right = bisect.bisect_right(sorted_list, (end_ts, '\xff'))
    else:
        right = len(sorted_list)
    
    # 筛选重叠条目
    results = []
    for i in range(right):
        _, doc_id = sorted_list[i]
        entry = self.entries.get(doc_id)
        if entry:
            target_range = entry.fact_range if time_type == 'fact' else entry.system_range
            if target_range.overlaps(query_tr):
                results.append(doc_id)
    return results
```

**query_before / query_after 同理改用 bisect**：

```python
def query_before(self, point, limit=100, time_type='fact'):
    """查询某时间点之前结束的条目 — bisect 优化"""
    if time_type == 'fact':
        sorted_list = self._sorted_by_fact_end
    elif time_type == 'system':
        sorted_list = self._sorted_by_system_end
    else:
        raise ValueError(f"time_type 必须为 'fact' 或 'system'，收到: '{time_type}'")
    
    point_ts = point.timestamp()
    # 找到 point 在排序列表中的插入位置
    right = bisect.bisect_right(sorted_list, (point_ts, '\xff'))
    
    # 从 right 向左取 limit 个
    results = []
    for i in range(right - 1, max(right - 1 - limit, -1), -1):
        _, doc_id = sorted_list[i]
        results.append(doc_id)
    return results

def query_after(self, point, limit=100, time_type='fact'):
    """查询某时间点之后开始的条目 — bisect 优化"""
    if time_type == 'fact':
        sorted_list = self._sorted_by_fact_start
    elif time_type == 'system':
        sorted_list = self._sorted_by_system_start
    else:
        raise ValueError(f"time_type 必须为 'fact' 或 'system'，收到: '{time_type}'")
    
    point_ts = point.timestamp()
    # 找到 point 在排序列表中的插入位置
    left = bisect.bisect_left(sorted_list, (point_ts,))
    
    # 从 left 向右取 limit 个
    results = []
    for i in range(left, min(left + limit, len(sorted_list))):
        _, doc_id = sorted_list[i]
        results.append(doc_id)
    return results
```

> **注意**：`query_before` 需额外维护 `_sorted_by_fact_end` / `_sorted_by_system_end` 按 **结束时间** 排序的列表。当前代码仅有 `_sorted_by_fact_start` / `_sorted_by_known_at` / `_sorted_by_system_start` 三个按开始时间排序的列表（L143-145），需在 `__init__` 中新增两个结束时间列表并在 `add_entry()` / `remove_entry()` / `_unindex_entry()` 中同步维护：
> ```python
> # __init__ 中新增（紧接 L145 之后）
> self._sorted_by_fact_end: List[Tuple[float, str]] = []    # (fact_end_ts, doc_id)
> self._sorted_by_system_end: List[Tuple[float, str]] = []  # (system_end_ts, doc_id)
> 
> # add_entry() 中新增（在现有 bisect.insort 之后）
> if entry.fact_range.end:
>     bisect.insort(self._sorted_by_fact_end, (entry.fact_range.end.timestamp(), doc_id))
> if entry.system_range and entry.system_range.end:
>     bisect.insort(self._sorted_by_system_end, (entry.system_range.end.timestamp(), doc_id))
> 
> # _unindex_entry() 中也必须同步移除（当前 L224-250 只移除 start 列表）
> # 在移除 _sorted_by_fact_start 的代码之后追加：
> if entry.fact_range.end:
>     end_ts = entry.fact_range.end.timestamp()
>     try:
>         self._sorted_by_fact_end.remove((end_ts, doc_id))
>     except ValueError:
>         pass
> if entry.system_range and entry.system_range.end:
>     end_ts = entry.system_range.end.timestamp()
>     try:
>         self._sorted_by_system_end.remove((end_ts, doc_id))
>     except ValueError:
>         pass
> ```
> `query_after` 则直接使用已有的 `_sorted_by_fact_start` / `_sorted_by_system_start`。

---

### 任务 2.2：倒排索引改增量持久化

**改动文件**：`recall/index/inverted_index.py`  
**改动行号**：L31-35

**方案**：将 `_save()` 从全量 JSON dump 改为增量 JSONL append + 定期压缩：

> **注意**：当前代码已有 `dirty_count >= 100` 优化（每 100 次修改才调用 `_save()`），但 `_save()` 本身仍是全量 dump。本改动将 `_save()` 内部逻辑升级为 WAL 增量追加。

```python
class InvertedIndex:
    def __init__(self, data_path):
        # ... 原逻辑 ...
        self._wal_file = os.path.join(self.index_dir, 'inverted_wal.jsonl')  # 新增
        self._wal_count = 0
        self._compact_threshold = 10000  # 每 1 万条 WAL 压缩一次
    
    def add_batch(self, keywords, turn_id):
        """批量添加 — 改用 WAL 增量追加"""
        entries = []
        for kw in keywords:
            kw_lower = kw.lower()
            self.index[kw_lower].add(turn_id)
            entries.append({"k": kw_lower, "t": turn_id})
        
        # 追加 WAL（增量，不重写全文件）
        os.makedirs(self.index_dir, exist_ok=True)
        with open(self._wal_file, 'a', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        
        self._wal_count += len(entries)
        if self._wal_count >= self._compact_threshold:
            self._compact()  # 定期压缩：合并 WAL 到主索引文件
    
    def _compact(self):
        """压缩：将内存状态全量写入主文件，删除 WAL"""
        # 原子写入：先写临时文件再 os.replace()，避免崩溃时主文件损坏
        tmp_file = self.index_file + '.tmp'
        os.makedirs(self.index_dir, exist_ok=True)
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump({k: list(v) for k, v in self.index.items()}, f, ensure_ascii=False)
        os.replace(tmp_file, self.index_file)  # 原子替换
        if os.path.exists(self._wal_file):
            os.remove(self._wal_file)
        self._wal_count = 0
    
    def _save_full(self):
        """全量保存（仅压缩时调用，已集成到 _compact 中）"""
        # 原 _save() 逻辑
        os.makedirs(self.index_dir, exist_ok=True)
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump({k: list(v) for k, v in self.index.items()}, f, ensure_ascii=False)
    
    def _load(self):
        """加载 = 主文件 + WAL 重放"""
        # 1. 加载主文件（原逻辑）
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for keyword, turns in data.items():
                    self.index[keyword] = set(turns)
        
        # 2. 重放 WAL
        if os.path.exists(self._wal_file):
            with open(self._wal_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        # 崩溃时可能留下不完整的最后一行，安全跳过
                        logger.warning(f"WAL 行损坏已跳过: {line[:50]}")
                        continue
                    self.index[entry['k']].add(entry['t'])
                    self._wal_count += 1
```

---

### 任务 2.3：JSON 图后端改延迟保存

**改动文件**：`recall/graph/backends/json_backend.py`  
**改动行号**：L143-157

**方案**：将每次操作的全量 `_save()` 改为脏标记 + 延迟批量保存（`add_node()` 和 `add_edge()` 都需替换）：

```python
class JSONGraphBackend(GraphBackend):
    def __init__(self, data_path, auto_save=True):
        # ... 原逻辑 ...
        self._dirty = False
        self._dirty_count = 0
        self._save_interval = 100  # 每 100 次写操作保存一次
    
    def add_node(self, node):
        self.nodes[node.id] = node
        self._outgoing_index_add(node.id)
        self._mark_dirty()
        return node.id
    
    def _mark_dirty(self):
        self._dirty = True
        self._dirty_count += 1
        if self.auto_save and self._dirty_count >= self._save_interval:
            self._save()
            self._dirty_count = 0
    
    def flush(self):
        """显式刷盘（关闭/重要操作后调用）"""
        if self._dirty:
            self._save()
            self._dirty = False
            self._dirty_count = 0
    
    def __del__(self):
        try:
            self.flush()
        except:
            pass
```

> **⚠️ 可靠性注意**：Python 的 `__del__` 在解释器退出时不保证被调用（尤其 daemon 线程、信号终止等场景）。建议在 `__init__` 中额外注册 `import atexit; atexit.register(self.flush)`，确保正常退出时数据不丢失。`__del__` 作为额外安全网保留。

---

### 任务 2.4：VolumeManager 添加 memory_id 索引

**改动文件**：`recall/storage/volume_manager.py`  
**改动行号**：L142+

**方案**：维护 `memory_id → (volume_id, turn_number)` 的反向索引：

```python
class VolumeManager:
    def __init__(self, data_path):
        # ... 原逻辑 ...
        self._memory_id_index: Dict[str, int] = {}  # memory_id → turn_number
        self._index_file = os.path.join(data_path, "memory_id_index.json")
        self._load_memory_id_index()
    
    def append_turn(self, turn_data):
        turn_number = ...  # 原逻辑
        # 更新 memory_id 索引
        memory_id = turn_data.get('memory_id')
        if memory_id:
            self._memory_id_index[memory_id] = turn_number
            if len(self._memory_id_index) % 100 == 0:
                self._save_memory_id_index()
        return turn_number
    
    def get_turn_by_memory_id(self, memory_id):
        """O(1) 查找（有索引时）→ O(n) 兜底（无索引时）"""
        # 1. 索引快速查找
        if memory_id in self._memory_id_index:
            turn_number = self._memory_id_index[memory_id]
            return self.get_turn(turn_number)
        
        # 2. 兜底：原有全扫描逻辑（向后兼容旧数据）
        return self._full_scan_by_memory_id(memory_id)
```

---

## 五、Phase 3：批量写入与元数据索引

> **目标**：支持爬虫/批量导入等高吞吐场景。  
> **预计工作量**：3-4 天

### 任务 3.1：engine.py 新增批量写入 API

**改动文件**：`recall/engine.py`

**新增方法**：

```python
def add_batch(
    self,
    items: List[Dict[str, Any]],
    user_id: str = "default",
    skip_dedup: bool = False,
    skip_llm: bool = True,  # 批量模式默认跳过 LLM
) -> List[str]:
    """批量添加记忆（高吞吐）
    
    优化策略：
    1. 批量计算 embedding（单次 API 调用）
    2. 批量更新索引（合并 IO）
    3. 可选跳过去重和 LLM（提高吞吐）
    
    Args:
        items: [{"content": "...", "source": "bilibili", "tags": [...], "metadata": {...}}, ...]
        user_id: 用户ID
        skip_dedup: 跳过去重检查
        skip_llm: 跳过 LLM 调用（实体提取用规则模式）
    
    Returns:
        List[str]: 成功添加的 memory_id 列表
    """
    memory_ids = []
    
    # 0. 检查 embedding 后端（必须初始化才能批量添加）
    if not self.embedding_backend:
        raise RuntimeError("Embedding backend 未初始化（需启用 VECTOR_INDEX），无法执行批量添加")
    
    # 1. 批量计算 embedding
    contents = [item['content'] for item in items]
    embeddings = self.embedding_backend.encode_batch(contents)  # 单次 API
    
    # 2. 逐条处理但合并 IO
    all_keywords = []
    all_entities = []
    all_ngram_data = []  # (memory_id, content) 对 — ngram_index.add(turn, content) 需要完整原文
    
    for item, embedding in zip(items, embeddings):
        result = self._add_single_fast(
            content=item['content'],
            embedding=embedding,
            metadata=item.get('metadata', {}),
            user_id=user_id,
            skip_dedup=skip_dedup,
            skip_llm=skip_llm,
        )
        if result:
            memory_id, entities, keywords = result
            memory_ids.append(memory_id)
            all_entities.extend([(e.name, memory_id) for e in entities])
            all_keywords.extend([(kw, memory_id) for kw in keywords])
            all_ngram_data.append((memory_id, item['content']))  # ngram 需要完整原文
    
    # 3. 批量更新索引（一次 IO）
    self._batch_update_indexes(all_keywords, all_entities, all_ngram_data)
    
    return memory_ids

def _add_single_fast(self, content, embedding, metadata, user_id, skip_dedup, skip_llm):
    """单条快速添加（add_batch 内部使用，跳过重复计算）
    
    与 add() 的区别：
    1. embedding 已预算好，不再调用 encode()
    2. skip_dedup=True 时跳过三阶段去重
    3. skip_llm=True 时跳过 LLM 实体提取，改用规则提取
    
    Returns:
        None: 如果去重命中（跳过）
        Tuple[str, List, List]: (memory_id, entities, keywords) — 用于外层批量索引更新
    """
    memory_id = str(uuid.uuid4())
    
    # 去重检查（可跳过）
    if not skip_dedup:
        scope = self.storage.get_scope(user_id)
        existing = scope.get_all(limit=100)
        # 用已有 embedding 做快速向量相似度检查
        for mem in existing:
            if content.strip() == mem.get('content', '').strip():
                return None  # 完全重复，跳过
    
    # 实体提取（LLM 或规则）
    # 注意：SmartExtractor.extract() 返回 ExtractionResult dataclass，
    # 包含 .entities, .relations, .keywords 属性
    # extract() 支持 force_mode 参数：force_mode=ExtractionMode.RULES 强制使用规则模式
    extraction_result = None
    if self.smart_extractor:
        if skip_llm:
            from recall.processor.smart_extractor import ExtractionMode
            extraction_result = self.smart_extractor.extract(content, force_mode=ExtractionMode.RULES)
        else:
            extraction_result = self.smart_extractor.extract(content)
    entities = extraction_result.entities if extraction_result else []
    keywords = extraction_result.keywords if extraction_result else []
    
    # 存储记忆（与 engine.add() L1751 的调用方式一致）
    scope = self.storage.get_scope(user_id)
    scope.add(content, metadata={
        'id': memory_id,
        'entities': [e.name for e in entities],
        'keywords': keywords,
        **(metadata or {})
    })
    
    # 更新向量索引（用预算好的 embedding）
    # 注意：VectorIndex.add() 签名为 add(doc_id, embedding)，无 add_with_embedding
    if self._vector_index and self._vector_index.enabled:
        self._vector_index.add(memory_id, embedding)
    
    return (memory_id, entities, keywords)

def _batch_update_indexes(self, all_keywords, all_entities, all_ngram_data):
    """批量更新索引 — 合并 IO 操作
    
    Args:
        all_keywords: [(keyword, memory_id), ...] 
        all_entities: [(entity_name, memory_id), ...]
    """
    # 批量更新倒排索引（通过公开 API 以兼容 Phase 2 WAL 改造）
    if self._inverted_index and all_keywords:
        # 按 memory_id 分组，调用 add_batch(keywords, turn_id)
        from collections import defaultdict
        kw_by_mid = defaultdict(list)
        for kw, mid in all_keywords:
            kw_by_mid[mid].append(kw)
        for mid, kws in kw_by_mid.items():
            self._inverted_index.add_batch(kws, mid)  # 走公开 API，兼容 WAL
    
    # 批量更新实体索引
    # 注意：EntityIndex.add() 接受 IndexedEntity 对象，不是 (str, str)
    # 正确方法是 add_entity_occurrence(entity_name, turn_id)（L114），
    # 它内部会自动调用 _save()，无需显式 save
    if self._entity_index and all_entities:
        for entity_name, mid in all_entities:
            self._entity_index.add_entity_occurrence(entity_name, mid)
    
    # 批量更新 N-gram 索引
    # 注意：OptimizedNgramIndex.add(turn, content) 签名接受 (memory_id, 完整原文)，
    # 内部自动提取名词短语并索引，因此需传入 (memory_id, content) 对而非 (keyword, memory_id) 对
    if self._ngram_index and all_ngram_data:
        for mid, content in all_ngram_data:
            self._ngram_index.add(mid, content)  # add(turn, content) at ngram_index.py L73
        self._ngram_index.save()  # 单次 IO
```

### 任务 3.2：server.py 新增批量 API 端点

**改动文件**：`recall/server.py`

**新增端点**：

```python
@app.post("/v1/memories/batch")
async def add_memories_batch(request: BatchAddRequest):
    """批量添加记忆（高吞吐模式）
    
    Body:
    {
        "items": [
            {"content": "...", "source": "bilibili", "tags": ["热点"], "metadata": {}},
            {"content": "...", "source": "github", "tags": ["trending"], "metadata": {}}
        ],
        "user_id": "default",
        "skip_dedup": false,
        "skip_llm": true
    }
    """
    memory_ids = engine.add_batch(
        items=request.items,
        user_id=request.user_id,
        skip_dedup=request.skip_dedup,
        skip_llm=request.skip_llm,
    )
    return {"memory_ids": memory_ids, "count": len(memory_ids)}
```

### 任务 3.3：新增元数据索引

**新建文件**：`recall/index/metadata_index.py`

```python
"""元数据索引 — 支持按 source/tags/category/content_type 过滤"""

import os
import json
from collections import defaultdict
from typing import Dict, Set, Optional, List

class MetadataIndex:
    """元数据倒排索引"""
    
    def __init__(self, data_path):
        self.data_path = data_path
        self._index_file = os.path.join(data_path, 'metadata_index.json')
        # 多字段倒排索引
        self._by_source: Dict[str, Set[str]] = defaultdict(set)     # source → memory_ids
        self._by_tag: Dict[str, Set[str]] = defaultdict(set)        # tag → memory_ids
        self._by_category: Dict[str, Set[str]] = defaultdict(set)   # category → memory_ids
        self._by_content_type: Dict[str, Set[str]] = defaultdict(set)
        self._dirty_count = 0
        self._load()
        # 注册退出时自动刷盘，防止 dirty_count < 100 时进程退出丢数据
        import atexit
        atexit.register(self.flush)
    
    def add(self, memory_id, source="", tags=None, category="", content_type=""):
        if source:
            self._by_source[source].add(memory_id)
        for tag in (tags or []):
            self._by_tag[tag].add(memory_id)
        if category:
            self._by_category[category].add(memory_id)
        if content_type:
            self._by_content_type[content_type].add(memory_id)
        self._dirty_count += 1
        if self._dirty_count >= 100:
            self._save()
            self._dirty_count = 0
    
    def query(self, source=None, tags=None, category=None, content_type=None) -> Set[str]:
        """多条件 AND 查询"""
        result = None
        if source:
            candidates = self._by_source.get(source, set())
            result = candidates if result is None else result & candidates
        if tags:
            for tag in tags:
                candidates = self._by_tag.get(tag, set())
                result = candidates if result is None else result & candidates
        if category:
            candidates = self._by_category.get(category, set())
            result = candidates if result is None else result & candidates
        if content_type:
            candidates = self._by_content_type.get(content_type, set())
            result = candidates if result is None else result & candidates
        return result or set()
    
    def _save(self):
        """持久化到 JSON 文件"""
        os.makedirs(os.path.dirname(self._index_file), exist_ok=True)
        data = {
            'by_source': {k: list(v) for k, v in self._by_source.items()},
            'by_tag': {k: list(v) for k, v in self._by_tag.items()},
            'by_category': {k: list(v) for k, v in self._by_category.items()},
            'by_content_type': {k: list(v) for k, v in self._by_content_type.items()},
        }
        with open(self._index_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    
    def _load(self):
        """从 JSON 文件加载"""
        if os.path.exists(self._index_file):
            with open(self._index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, v in data.get('by_source', {}).items():
                self._by_source[k] = set(v)
            for k, v in data.get('by_tag', {}).items():
                self._by_tag[k] = set(v)
            for k, v in data.get('by_category', {}).items():
                self._by_category[k] = set(v)
            for k, v in data.get('by_content_type', {}).items():
                self._by_content_type[k] = set(v)
    
    def flush(self):
        """显式刷盘"""
        if self._dirty_count > 0:
            self._save()
            self._dirty_count = 0
```

### 任务 3.4：检索系统集成元数据过滤

**改动文件**：`recall/retrieval/eleven_layer.py`, `recall/engine.py`, `recall/index/__init__.py`

**3.4.1 engine.py 中初始化 MetadataIndex**：

在 `RecallEngine.__init__()` 中（紧接其他索引初始化 L266-269 之后）新增：
```python
from recall.index.metadata_index import MetadataIndex
self._metadata_index = MetadataIndex(
    data_path=os.path.join(self.data_dir, 'indexes')  # 与其他索引同目录
)
```

**3.4.2 engine.py add() / add_batch() 中写入 MetadataIndex**：

在 `add()` 方法中（scope.add 之后）新增：
```python
# 更新元数据索引
if self._metadata_index:
    self._metadata_index.add(
        memory_id=memory_id,
        source=metadata.get('source', '') if metadata else '',
        tags=metadata.get('tags', []) if metadata else [],
        category=metadata.get('category', '') if metadata else '',
        content_type=metadata.get('content_type', '') if metadata else '',
    )
```

在 `_add_single_fast()` 中同理新增 `self._metadata_index.add(...)` 调用。

**3.4.3 recall/index/__init__.py 更新**：

追加导出：
```python
from .metadata_index import MetadataIndex
```

**3.4.4 search() 集成元数据过滤**：

在 `search()` 方法中新增可选的元数据过滤参数：

```python
def search(self, query, user_id="default", top_k=10,
           source=None, tags=None, category=None, content_type=None):
    """搜索记忆 — 支持元数据过滤"""
    # 1. 如果有元数据过滤条件，先缩小候选集
    if any([source, tags, category, content_type]):
        allowed_ids = self._metadata_index.query(
            source=source, tags=tags, category=category, content_type=content_type
        )
    else:
        allowed_ids = None  # None 表示不过滤
    
    # 2. 原有 11 层检索逻辑不变
    results = self._eleven_layer_search(query, user_id, top_k=top_k * 2 if allowed_ids else top_k)
    
    # 3. 最终用 allowed_ids 过滤（过采样后截断）
    if allowed_ids is not None:
        results = [r for r in results if r.id in allowed_ids][:top_k]
    
    return results
```

> **设计说明**：元数据过滤采用"后过滤"策略（检索后过滤），而非"预过滤"（修改 11 层内部逻辑），以保持 11 层检索器的独立性。为防止过滤后结果不足，检索时过采样 `top_k * 2`。

---

## 六、Phase 4：MCP Server 实现

> **目标**：实现 Model Context Protocol 支持，一次开发适配所有 MCP 客户端。  
> **预计工作量**：3-4 天

### 任务 4.1：新建 MCP Server 核心

**新建文件**：`recall/mcp_server.py`

```python
"""Recall MCP Server — Model Context Protocol 支持

支持的 MCP 客户端：
- Claude Desktop
- VS Code / Cursor (Copilot)
- 任何支持 MCP 的 AI 应用

传输方式：
- stdio（默认，本地使用）
- SSE（远程部署，见任务 4.4）
"""
# 此文件的完整实现见下方「recall/mcp_server.py 完整入口」
```

**新建文件**：`recall/mcp/__init__.py`

```python
"""Recall MCP 支持包"""
from .tools import register_tools
from .resources import register_resources
from .transport import create_sse_app

__all__ = ['register_tools', 'register_resources', 'create_sse_app']
```

### 任务 4.2：MCP Tools 实现

**新建文件**：`recall/mcp/tools.py`

| Tool 名称 | 对应 API | 说明 |
|-----------|----------|------|
| `recall_add` | POST /v1/memories | 添加记忆 |
| `recall_search` | GET /v1/memories/search | 搜索记忆 |
| `recall_context` | POST /v1/context | 构建上下文 |
| `recall_add_turn` | POST /v1/memories/turn | 添加对话轮次 |
| `recall_list` | GET /v1/memories | 列出记忆 |
| `recall_delete` | DELETE /v1/memories/{id} | 删除记忆 |
| `recall_stats` | GET /v1/stats | 统计信息 |
| `recall_entities` | GET /v1/entities | 实体列表 |
| `recall_graph_traverse` | POST /v1/graph/traverse | 图谱遍历 |
| `recall_add_batch` | POST /v1/memories/batch | 批量添加（v5.0） |
| `recall_search_filtered` | GET /v1/memories/search?source=... | 过滤搜索（v5.0） |

**实现伪代码**：

> **⚠️ 前置依赖**：MCP Tools 中调用的以下 engine 方法**当前不存在**，需在实施 Phase 4 前先在 `engine.py` 中新增：
> - `list_entities(user_id, entity_type, limit)` — 基于 `_entity_index` 封装
> - `traverse_graph(start_entity, max_depth, relation_types, user_id)` — 基于 `knowledge_graph` 封装
> - `list_memories(limit)` — 基于 `get_paginated()` 封装
> - `get_entity_detail(entity_name)` — 基于 `_entity_index` 封装
> 
> 已有方法：`get_paginated()`(L2821)、`get()`(L2854)、`get_stats()`(L4117)、`add_turn()`(L2077)、`delete()`(L3137)、`search()`
>
> **四个新方法的实现要求**：
> 
> ```python
> def list_entities(self, user_id="default", entity_type=None, limit=100):
>     """列出实体 — 从 _entity_index 获取
>     
>     注意：EntityIndex.all_entities() 返回 List[IndexedEntity]，
>     每个 IndexedEntity 有 .name, .entity_type, .summary, .facts 等属性。
>     EntityIndex 本身不按 user_id 隔离，user_id 参数留侜后续扩展。
>     """
>     if not self._entity_index:
>         return []
>     entities = self._entity_index.all_entities()  # 返回 List[IndexedEntity]
>     if entity_type:
>         entities = [e for e in entities if getattr(e, 'entity_type', '') == entity_type]
>     # 转为字典格式以便 JSON 序列化
>     return [{'name': e.name, 'type': getattr(e, 'entity_type', ''), 
>              'summary': getattr(e, 'summary', '')} for e in entities[:limit]]
> 
> def traverse_graph(self, start_entity, max_depth=2, relation_types=None, user_id="default"):
>     """图遍历 — 从 knowledge_graph BFS 遍历关系
>     
>     注意：self.knowledge_graph 是 TemporalKnowledgeGraph 实例（engine.py L342）。
>     get_relations_for_entity(entity_name) 返回 List[LegacyRelation]，
>     LegacyRelation 有 .source_id, .target_id, .relation_type 属性。
>     """
>     if not self.knowledge_graph:
>         return {"nodes": [], "edges": []}
>     # BFS 从 start_entity 出发，遍历最多 max_depth 层关系
>     from collections import deque
>     visited = set()
>     queue = deque([(start_entity, 0)])  # 使用 deque 而非 list（pop(0) 是 O(n)）
>     nodes, edges = [], []
>     while queue:
>         entity, depth = queue.popleft()  # O(1)
>         if entity in visited or depth > max_depth:
>             continue
>         visited.add(entity)
>         nodes.append({"name": entity, "depth": depth})
>         for rel in self.knowledge_graph.get_relations_for_entity(entity):
>             if relation_types and rel.relation_type not in relation_types:
>                 continue
>             edges.append({"source": rel.source_id, "target": rel.target_id, 
>                          "type": rel.relation_type})
>             next_entity = rel.target_id if rel.source_id == entity else rel.source_id
>             queue.append((next_entity, depth + 1))
>     return {"nodes": nodes, "edges": edges}
> 
> def list_memories(self, limit=100, user_id="default"):
>     """列出记忆 — 封装 get_paginated()"""
>     memories, total = self.get_paginated(user_id=user_id, offset=0, limit=limit)
>     return memories
> 
> def get_entity_detail(self, entity_name, user_id="default"):
>     """获取实体详情 — 从 _entity_index 查询
>     
>     注意：EntityIndex.get_entity(name) 不接受 user_id 参数。
>     返回 IndexedEntity 对象，需转为 dict。
>     """
>     if not self._entity_index:
>         return {"name": entity_name, "error": "entity index not initialized"}
>     entity = self._entity_index.get_entity(entity_name)
>     if entity:
>         return {"name": entity_name, "type": getattr(entity, 'entity_type', ''),
>                 "summary": getattr(entity, 'summary', ''),
>                 "facts": [str(f) for f in getattr(entity, 'facts', [])]}
>     return {"name": entity_name, "error": "entity not found"}
> ```

```python
"""recall/mcp/tools.py — MCP Tools 注册与桥接"""

import json
from mcp.server import Server
from mcp.types import Tool, TextContent
from recall.engine import RecallEngine

def register_tools(app: Server, engine: RecallEngine):
    """将 Recall API 注册为 MCP Tools"""
    
    @app.list_tools()
    async def list_tools():
        return [
            Tool(
                name="recall_add",
                description="添加一条记忆到 Recall",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "记忆内容"},
                        "user_id": {"type": "string", "description": "用户ID", "default": "default"},
                        "metadata": {"type": "object", "description": "元数据", "default": {}},
                    },
                    "required": ["content"]
                }
            ),
            Tool(
                name="recall_search",
                description="在 Recall 中搜索相关记忆",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "user_id": {"type": "string", "default": "default"},
                        "top_k": {"type": "integer", "default": 10},
                        "source": {"type": "string", "description": "按来源过滤（可选）"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "按标签过滤"},
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="recall_context",
                description="构建上下文（包含相关记忆 + 实体 + 知识图谱）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string", "default": "default"},
                        "character_id": {"type": "string", "default": "default"},
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="recall_add_batch",
                description="批量添加记忆（高吞吐）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                    "source": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["content"]
                            }
                        },
                        "user_id": {"type": "string", "default": "default"},
                    },
                    "required": ["items"]
                }
            ),
            Tool(
                name="recall_add_turn",
                description="添加一轮对话（用户消息 + AI 回复）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_message": {"type": "string", "description": "用户消息"},
                        "ai_response": {"type": "string", "description": "AI回复"},
                        "user_id": {"type": "string", "default": "default"},
                        "character_id": {"type": "string", "default": "default"},
                        "metadata": {"type": "object", "default": {}},
                    },
                    "required": ["user_message", "ai_response"]
                }
            ),
            Tool(
                name="recall_list",
                description="分页列出记忆",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "default": "default"},
                        "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 1000},
                        "offset": {"type": "integer", "default": 0, "minimum": 0},
                    }
                }
            ),
            Tool(
                name="recall_delete",
                description="删除一条记忆",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string", "description": "记忆ID"},
                        "user_id": {"type": "string", "default": "default"},
                    },
                    "required": ["memory_id"]
                }
            ),
            Tool(
                name="recall_stats",
                description="获取 Recall 系统统计信息",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="recall_entities",
                description="获取实体列表",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "default": "default"},
                        "character_id": {"type": "string", "default": "default"},
                        "entity_type": {"type": "string", "description": "按类型过滤(PERSON/LOCATION等)"},
                        "limit": {"type": "integer", "default": 100},
                    }
                }
            ),
            Tool(
                name="recall_graph_traverse",
                description="从指定实体出发遍历知识图谱",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_entity": {"type": "string", "description": "起始实体名称"},
                        "max_depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
                        "relation_types": {"type": "array", "items": {"type": "string"}, "description": "关系类型过滤"},
                        "user_id": {"type": "string", "default": "default"},
                    },
                    "required": ["start_entity"]
                }
            ),
            Tool(
                name="recall_search_filtered",
                description="按来源/标签过滤搜索记忆（v5.0）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string", "default": "default"},
                        "source": {"type": "string", "description": "按来源过滤"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "top_k": {"type": "integer", "default": 10},
                    },
                    "required": ["query"]
                }
            ),
        ]
    
    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Tool 调用入口 — 桥接到 RecallEngine"""
        if name == "recall_add":
            result = engine.add(
                content=arguments["content"],
                user_id=arguments.get("user_id", "default"),
                metadata=arguments.get("metadata", {}),
            )
            # AddResult dataclass 字段名是 .id（非 .memory_id）
            return [TextContent(type="text", text=f"已添加记忆: {result.id}")]
        
        elif name == "recall_search":
            results = engine.search(
                query=arguments["query"],
                user_id=arguments.get("user_id", "default"),
                top_k=arguments.get("top_k", 10),
            )
            # SearchResult 是 dataclass（字段: id, content, score, metadata, entities）
            # source/tags 存于 metadata 字典中，需从 metadata 获取
            if "source" in arguments:
                results = [r for r in results if r.metadata.get("source", "") == arguments["source"]]
            if "tags" in arguments:
                results = [r for r in results if set(arguments["tags"]) & set(r.metadata.get("tags", []))]
            
            text = "\n\n".join([f"[{r.score:.2f}] {r.content[:200]}" for r in results])
            return [TextContent(type="text", text=text or "未找到相关记忆")]
        
        elif name == "recall_context":
            context = engine.build_context(
                query=arguments["query"],
                user_id=arguments.get("user_id", "default"),
                character_id=arguments.get("character_id", "default"),
            )
            return [TextContent(type="text", text=context)]
        
        elif name == "recall_add_batch":
            ids = engine.add_batch(
                items=arguments["items"],
                user_id=arguments.get("user_id", "default"),
            )
            return [TextContent(type="text", text=f"批量添加完成: {len(ids)} 条")]
        
        elif name == "recall_add_turn":
            result = engine.add_turn(
                user_message=arguments["user_message"],
                ai_response=arguments["ai_response"],
                user_id=arguments.get("user_id", "default"),
                character_id=arguments.get("character_id", "default"),
                metadata=arguments.get("metadata"),
            )
            # AddTurnResult 是 dataclass，需显式格式化
            return [TextContent(type="text", text=f"已添加对话轮次: user={result.user_memory_id}, ai={result.ai_memory_id}")]
        
        elif name == "recall_list":
            # get_paginated() 返回 tuple: (memories, total_count)
            memories, total = engine.get_paginated(
                user_id=arguments.get("user_id", "default"),
                offset=arguments.get("offset", 0),
                limit=arguments.get("limit", 100),
            )
            # memories 中每条记忆格式为 {'content': ..., 'metadata': {'id': ..., ...}, 'timestamp': ...}
            text = "\n".join([f"[{m.get('metadata', {}).get('id', 'N/A')}] {m['content'][:100]}" for m in memories])
            return [TextContent(type="text", text=text or "暂无记忆")]
        
        elif name == "recall_delete":
            success = engine.delete(
                arguments["memory_id"],
                user_id=arguments.get("user_id", "default"),
            )
            if success:
                return [TextContent(type="text", text=f"已删除记忆: {arguments['memory_id']}")]
            else:
                return [TextContent(type="text", text=f"记忆不存在: {arguments['memory_id']}")]
        
        elif name == "recall_stats":
            stats = engine.get_stats()
            return [TextContent(type="text", text=json.dumps(stats, ensure_ascii=False, indent=2))]
        
        elif name == "recall_entities":
            # ⚠️ list_entities() 需在 engine.py 中新增（当前不存在）
            entities = engine.list_entities(
                user_id=arguments.get("user_id", "default"),
                entity_type=arguments.get("entity_type"),
                limit=arguments.get("limit", 100),
            )
            text = "\n".join([f"{e['name']} ({e['type']}): {e.get('summary', '')[:80]}" for e in entities])
            return [TextContent(type="text", text=text or "暂无实体")]
        
        elif name == "recall_graph_traverse":
            # ⚠️ traverse_graph() 需在 engine.py 中新增（当前不存在）
            graph_result = engine.traverse_graph(
                start_entity=arguments["start_entity"],
                max_depth=arguments.get("max_depth", 2),
                relation_types=arguments.get("relation_types"),
                user_id=arguments.get("user_id", "default"),
            )
            return [TextContent(type="text", text=json.dumps(graph_result, ensure_ascii=False, indent=2))]
        
        elif name == "recall_search_filtered":
            results = engine.search(
                query=arguments["query"],
                user_id=arguments.get("user_id", "default"),
                top_k=arguments.get("top_k", 10),
            )
            if "source" in arguments:
                results = [r for r in results if r.metadata.get("source", "") == arguments["source"]]
            if "tags" in arguments:
                results = [r for r in results if set(arguments["tags"]) & set(r.metadata.get("tags", []))]
            text = "\n\n".join([f"[{r.score:.2f}] {r.content[:200]}" for r in results])
            return [TextContent(type="text", text=text or "未找到相关记忆")]
        
        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]
```

**`recall/mcp_server.py` 完整入口**：

```python
"""Recall MCP Server 入口"""
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from recall.engine import RecallEngine
from recall.mcp.tools import register_tools
from recall.mcp.resources import register_resources

def create_app():
    app = Server("recall-memory")
    engine = RecallEngine()  # 使用默认配置初始化
    register_tools(app, engine)
    register_resources(app, engine)
    return app

async def _async_main():
    app = create_app()
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

def main():
    """同步入口 — pyproject.toml console_scripts 指向此函数"""
    asyncio.run(_async_main())

if __name__ == "__main__":
    main()
```

### 任务 4.3：MCP Resources 实现

**新建文件**：`recall/mcp/resources.py`

```python
"""recall/mcp/resources.py — MCP Resources 注册"""

from mcp.server import Server
from mcp.types import Resource, TextContent
from recall.engine import RecallEngine
from urllib.parse import unquote
import json

def register_resources(app: Server, engine: RecallEngine):
    
    @app.list_resources()
    async def list_resources():
        return [
            Resource(uri="recall://memories", name="所有记忆", mimeType="application/json"),
            Resource(uri="recall://entities", name="所有实体", mimeType="application/json"),
            Resource(uri="recall://stats", name="统计信息", mimeType="application/json"),
        ]
    
    @app.read_resource()
    async def read_resource(uri: str):
        if uri == "recall://memories":
            memories = engine.list_memories(limit=100)
            return json.dumps(memories, ensure_ascii=False, indent=2)
        elif uri == "recall://entities":
            entities = engine.list_entities()
            return json.dumps(entities, ensure_ascii=False, indent=2)
        elif uri == "recall://stats":
            stats = engine.get_stats()
            return json.dumps(stats, ensure_ascii=False, indent=2)
        elif uri.startswith("recall://memories/"):
            memory_id = unquote(uri.split("/")[-1])  # URL 解码
            memory = engine.get(memory_id)
            return json.dumps(memory, ensure_ascii=False, indent=2)
        elif uri.startswith("recall://entities/"):
            entity_name = unquote(uri.split("/")[-1])  # URL 解码（中文实体名等）
            entity = engine.get_entity_detail(entity_name)
            return json.dumps(entity, ensure_ascii=False, indent=2)
        else:
            return json.dumps({"error": f"Unknown resource: {uri}"})
```

### 任务 4.4：MCP Transport — SSE 支持

**新建文件**：`recall/mcp/transport.py`

支持远程部署的 Server-Sent Events 传输，使 MCP 客户端可通过 HTTP 连接到远程 Recall 服务。

```python
"""recall/mcp/transport.py — SSE 传输层

在 stdio（本地）之外，提供 HTTP+SSE 远程传输。
MCP SDK 已内置 SSE server，此处做配置封装。
"""

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse

def create_sse_app(mcp_server):
    """将 MCP Server 包装为 SSE HTTP 应用
    
    Args:
        mcp_server: 已注册好 tools/resources 的 mcp.server.Server 实例
    
    Returns:
        Starlette ASGI 应用，可用 uvicorn 启动
    """
    sse_transport = SseServerTransport("/messages/")
    
    async def handle_sse(request):
        """SSE 端点 — 客户端在此建立长连接"""
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1],
                mcp_server.create_initialization_options()
            )
    
    async def health(request):
        return JSONResponse({"status": "ok", "server": "recall-mcp"})
    
    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/sse", app=handle_sse),         # GET /sse — SSE 长连接
            Mount("/messages/", app=sse_transport.handle_post_message),  # POST /messages/ — 客户端发消息
        ]
    )
```

**在 `mcp_server.py` 中集成**（已在 create_app 后追加）：

```python
# mcp_server.py _async_main() 中判断传输方式
async def _async_main():
    transport = os.environ.get('MCP_TRANSPORT', 'stdio')  # stdio | sse
    app = create_app()
    
    if transport == 'sse':
        import uvicorn
        from recall.mcp.transport import create_sse_app
        sse_app = create_sse_app(app)
        port = int(os.environ.get('MCP_PORT', '8765'))
        uvicorn.run(sse_app, host="0.0.0.0", port=port)
    else:
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

def main():
    """pyproject.toml console_scripts 入口（同步包装）"""
    asyncio.run(_async_main())
```

**pyproject.toml 可选依赖更新**：SSE 传输需要 `uvicorn` 和 `starlette`，已包含在 `mcp` 可选依赖组内：

```toml
mcp = ["mcp>=1.0.0", "httpx-sse>=0.4.0", "uvicorn>=0.30.0", "starlette>=0.38.0"]
```

### 任务 4.5：新增依赖与入口点

**改动文件**：`pyproject.toml`

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0.0", "httpx-sse>=0.4.0", "uvicorn>=0.30.0", "starlette>=0.38.0"]

[project.scripts]
recall-mcp = "recall.mcp_server:main"
```

> **注意**：`recall-mcp` 入口指向同步的 `main()` 函数（内部调用 `asyncio.run(_async_main())`），
> 因为 console_scripts 无法直接调用 async 函数。

### 任务 4.6：Claude Desktop 配置文档

**新建文件**：`docs/MCP-SETUP.md`

使用指南，包含 `claude_desktop_config.json` 配置示例。

---

## 七、Phase 5：Prompt 工程系统化

> **目标**：将散落在各模块中的 LLM prompt 集中管理，支持定制化。  
> **预计工作量**：2-3 天

### 任务 5.1：创建 Prompt 模板管理器

**新建目录**：`recall/prompts/`  
**新建文件**：

| 文件 | 说明 |
|------|------|
| `recall/prompts/__init__.py` | 导出 PromptManager（内容见任务 5.1） |
| `recall/prompts/manager.py` | PromptManager 类 — 加载/缓存/渲染 prompt 模板 |
| `recall/prompts/templates/` | YAML 模板目录（str.format 变量渲染） |
| `recall/prompts/templates/entity_extraction.yaml` | 实体抽取 prompt |
| `recall/prompts/templates/relation_extraction.yaml` | 关系抽取 prompt |
| `recall/prompts/templates/contradiction_detection.yaml` | 矛盾检测 prompt |
| `recall/prompts/templates/foreshadowing_analysis.yaml` | 伏笔分析 prompt |
| `recall/prompts/templates/context_extraction.yaml` | 持久条件抽取 prompt |
| `recall/prompts/templates/entity_summary.yaml` | 实体摘要 prompt |
| `recall/prompts/templates/unified_analysis.yaml` | 统一分析 prompt |

**`recall/prompts/__init__.py` 内容**：

```python
from .manager import PromptManager

__all__ = ['PromptManager']
```

### 任务 5.2：PromptManager 实现

```python
import os

class PromptManager:
    """Prompt 模板管理器
    
    支持：
    1. YAML 模板定义 + Python str.format() 变量渲染
    2. 多语言支持（zh/en）
    3. 模式感知（RP/通用/知识库模式不同 prompt）
    4. 用户自定义覆盖（在 recall_data/prompts/ 中放同名文件）
    
    注意：使用 Python 原生 str.format() 渲染变量（非 Jinja2），
    模板中 JSON 的 { } 需要写成 {{ }}。
    """
    
    def __init__(self, mode: RecallMode):
        self.mode = mode
        self._templates = {}
        self._load_templates()
    
    def render(self, template_name: str, **kwargs) -> str:
        """渲染 prompt 模板"""
        if template_name not in self._templates:
            raise ValueError(f"模板 '{template_name}' 不存在，可用: {list(self._templates.keys())}")
        template = self._templates[template_name]
        # 选择模式对应的变体
        variant = template.get(self.mode.value, template.get('default'))
        if variant is None:
            raise ValueError(
                f"模板 '{template_name}' 缺少 '{self.mode.value}' 和 'default' 变体，"
                f"可用 key: {list(template.keys())}"
            )
        return variant.format(**kwargs)
    
    def _load_templates(self):
        """从 YAML 加载模板，优先用户自定义覆盖"""
        import yaml
        
        # 1. 加载内置模板
        builtin_dir = os.path.join(os.path.dirname(__file__), 'templates')
        if os.path.exists(builtin_dir):
            for f in os.listdir(builtin_dir):
                if f.endswith('.yaml'):
                    name = f[:-5]  # 去掉 .yaml
                    with open(os.path.join(builtin_dir, f), 'r', encoding='utf-8') as fh:
                        self._templates[name] = yaml.safe_load(fh)
        
        # 2. 用户覆盖（recall_data/prompts/ 中的同名文件优先）
        user_dir = os.path.join(os.environ.get('RECALL_DATA_ROOT', 'recall_data'), 'prompts')
        if os.path.exists(user_dir):
            for f in os.listdir(user_dir):
                if f.endswith('.yaml'):
                    name = f[:-5]
                    with open(os.path.join(user_dir, f), 'r', encoding='utf-8') as fh:
                        self._templates[name] = yaml.safe_load(fh)
```

**YAML 模板格式示例**（`templates/entity_extraction.yaml`）：

```yaml
# entity_extraction.yaml — 实体抽取 prompt 模板
# 每个 key 对应一种 RecallMode，'default' 为兜底

default: |
  请从以下文本中提取所有实体（人物、地点、组织、物品等）。
  
  文本：{content}
  
  请以 JSON 格式返回：
  [{{"name": "实体名", "type": "实体类型", "description": "简要描述"}}]

roleplay: |
  请从以下角色扮演对话中提取所有实体（角色、地点、物品、事件等）。
  注意识别角色名、NPC名、地名、道具名等 RP 特有实体。
  
  对话内容：{content}
  
  请以 JSON 格式返回：
  [{{"name": "实体名", "type": "实体类型", "description": "简要描述"}}]

knowledge_base: |
  请从以下知识文档中提取所有关键实体（概念、术语、人物、组织等）。
  重点关注专业术语和核心概念。
  
  文档内容：{content}
  
  请以 JSON 格式返回：
  [{{"name": "实体名", "type": "实体类型", "description": "简要描述"}}]
```

> **迁移原则**：每个模板的 `default` 变体内容 = 原硬编码字符串的精确复制。`roleplay`/`knowledge_base` 变体可后续逐步优化。迁移时原文件只需改一行：`prompt = self.prompt_manager.render('entity_extraction', content=text)`

### 任务 5.3：迁移现有硬编码 Prompt

**改动文件清单**：

| 文件 | 当前硬编码位置（精确行号/变量名） | 迁移到 |
|------|--------------------------------------|--------|
| `processor/smart_extractor.py` | `EXTRACTION_PROMPT`(L202) + `EXTRACTION_PROMPT_V2`(L227) — 类变量 | `templates/entity_extraction.yaml` |
| `graph/llm_relation_extractor.py` | `RELATION_EXTRACTION_PROMPT`(L71) — 模块级变量 | `templates/relation_extraction.yaml` |
| `processor/consistency.py` | L1351 内联 f-string（`你是一个严格的规则检查器…`） | `templates/contradiction_detection.yaml` |
| `processor/foreshadowing_analyzer.py` | `ANALYSIS_PROMPT_ZH`(L200) + `ANALYSIS_PROMPT_EN`(L246) — 类变量 | `templates/foreshadowing_analysis.yaml` |
| `processor/context_tracker.py` | `self.extraction_prompt`(L290) + L1812 内联 f-string — 共 2 处 | `templates/context_extraction.yaml` |
| `processor/entity_summarizer.py` | `SUMMARIZE_PROMPT`(L36) — 模块级变量 | `templates/entity_summary.yaml` |
| `processor/unified_analyzer.py` | `UNIFIED_ANALYSIS_PROMPT`(L67) — 模块级变量 | `templates/unified_analysis.yaml` |

**改动方式**：每个文件只需改一行——将硬编码字符串替换为 `self.prompt_manager.render('template_name', ...)`。原字符串成为 YAML 模板中的 `default` 变体。

**⚠️ PromptManager 注入路径**（AI 实施必读）：

1. **实例创建**：在 `engine.py` 的 `RecallEngine.__init__()` 中创建 PromptManager 实例：
   ```python
   from recall.prompts.manager import PromptManager
   self.prompt_manager = PromptManager(mode=get_mode_config())
   ```

2. **注入到各 processor**：在 `engine.py` 初始化各 processor 时传入 `prompt_manager`，例如：
   ```python
   self.smart_extractor = SmartExtractor(..., prompt_manager=self.prompt_manager)
   self.consistency_checker = ConsistencyChecker(..., prompt_manager=self.prompt_manager)
   ```

3. **各 processor 接收**：在每个 processor 的 `__init__` 中新增可选参数 `prompt_manager=None`，保存为 `self.prompt_manager`。若为 `None` 则回退使用原硬编码字符串（向后兼容）。

---

## 八、Phase 6：多 LLM 提供商自适应

> **目标**：基于现有 `LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL` 和 `EMBEDDING_*` 配置自动识别提供商，零新增配置变量。  
> **核心原则**：👉 **不新增任何 LLM 配置变量，完全复用现有配置，自动检测提供商** 👈  
> **预计工作量**：2-3 天

### 设计理念

用户只需像以前一样配置：

```bash
# 场景 1：OpenAI 兼容（硅基流动/Ollama/DeepSeek 等）— 与现在完全一样
LLM_API_KEY=sk-xxx
LLM_API_BASE=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-chat

# 场景 2：Anthropic Claude — 只需改 API_BASE 和 MODEL
LLM_API_KEY=sk-ant-xxx
LLM_API_BASE=https://api.anthropic.com
LLM_MODEL=claude-3-5-sonnet-20241022

# 场景 3：Google Gemini — 只需改 API_BASE 和 MODEL
LLM_API_KEY=AIzaSy-xxx
LLM_API_BASE=https://generativelanguage.googleapis.com
LLM_MODEL=gemini-pro

# 场景 4：任何 OpenAI 兼容中转站
LLM_API_KEY=xxx
LLM_API_BASE=https://my-proxy.com/v1
LLM_MODEL=claude-3-5-sonnet    # 中转站转发，走 OpenAI SDK
```

`LLMClient` 自动根据 `LLM_API_BASE` 域名 + `LLM_MODEL` 模型名推断使用哪个 SDK，用户无需关心底层差异。

### 任务 6.1：LLMClient 新增提供商自动检测与多后端

**改动文件**：`recall/utils/llm_client.py`

**改动方式**：在现有 `__init__` 中新增 `_detect_provider()` 逻辑，保留原有 OpenAI 路径不变，新增 Anthropic 和 Google 路径：

```python
class LLMClient:
    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        self.model = model
        self.api_key = api_key or os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')
        self.api_base = api_base or os.environ.get('LLM_API_BASE')
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 自动检测提供商（新增，零配置）
        self._provider = self._detect_provider()
        
        self._client = None
    
    def _detect_provider(self) -> str:
        """根据 api_base 域名和 model 名称自动检测提供商
        
        检测优先级：
        1. api_base 域名精确匹配（最可靠）
        2. model 名称前缀匹配（兜底）
        3. 默认 openai（兼容所有 OpenAI 格式的中转站）
        """
        # 1. 按 api_base 域名检测
        if self.api_base:
            base_lower = self.api_base.lower()
            if 'anthropic.com' in base_lower:
                return 'anthropic'
            if 'googleapis.com' in base_lower or 'generativelanguage' in base_lower:
                return 'google'
            # 其他任何地址（包括中转站）→ 走 OpenAI SDK
            return 'openai'
        
        # 2. 无 api_base 时，按 model 名称检测
        if self.model:
            model_lower = self.model.lower()
            if model_lower.startswith('claude'):
                return 'anthropic'
            if model_lower.startswith('gemini'):
                return 'google'
        
        # 3. 默认 OpenAI
        return 'openai'
    
    @property
    def client(self):
        """获取客户端（根据提供商自动选择）"""
        if self._client is None:
            if self._provider == 'anthropic':
                self._client = self._create_anthropic_client()
            elif self._provider == 'google':
                self._client = self._create_google_client()
            else:
                self._client = self._create_openai_client()  # 原逻辑
        return self._client
    
    def _create_openai_client(self):
        """原有 OpenAI 客户端创建逻辑（完全不变）"""
        from openai import OpenAI
        client_kwargs = {"api_key": self.api_key, "timeout": self.timeout}
        if self.api_base:
            client_kwargs["base_url"] = self.api_base
        return OpenAI(**client_kwargs)
    
    def _create_anthropic_client(self):
        """创建 Anthropic 客户端"""
        try:
            from anthropic import Anthropic
            return Anthropic(api_key=self.api_key, timeout=self.timeout)
        except ImportError:
            raise ImportError("使用 Claude 模型需要安装 anthropic: pip install anthropic")
    
    def _create_google_client(self):
        """创建 Google 客户端（返回模型名标记，实际调用在 chat 中处理）"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            return genai  # 返回 module 本身作为客户端标记
        except ImportError:
            raise ImportError("使用 Gemini 模型需要安装 google-generativeai: pip install google-generativeai")
    
    def chat(self, messages, max_tokens=None, temperature=0.7, stop=None, **kwargs):
        """聊天补全 — 根据提供商自动路由"""
        if max_tokens is None:
            max_tokens = int(os.environ.get('LLM_DEFAULT_MAX_TOKENS', '2000'))
        
        if self._provider == 'anthropic':
            return self._chat_anthropic(messages, max_tokens, temperature, stop)
        elif self._provider == 'google':
            return self._chat_google(messages, max_tokens, temperature, stop)
        else:
            return self._chat_openai(messages, max_tokens, temperature, stop, **kwargs)
    
    def _chat_openai(self, messages, max_tokens, temperature, stop, **kwargs):
        """OpenAI 路径（原有逻辑，完全保留）
        
        搬迁指南：将原 chat() 方法 L117-174 中 `if max_tokens is None` 之后的
        全部代码（重试循环 + client.chat.completions.create + LLMResponse 构建）
        原封不动移到此方法中。不修改任何逻辑。
        """
        start_time = time.time()
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop,
                    **kwargs
                )
                latency = (time.time() - start_time) * 1000
                return LLMResponse(
                    content=response.choices[0].message.content,
                    model=response.model,
                    usage={
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                        'total_tokens': response.usage.total_tokens,
                    },
                    latency_ms=latency,
                    raw_response=response
                )
            except Exception as e:
                if '429' in str(e).lower() and attempt < self.max_retries - 1:
                    time.sleep((attempt + 1) * 15)
                    continue
                raise
    
    def _chat_anthropic(self, messages, max_tokens, temperature, stop):
        """Anthropic Claude 原生 SDK 路径
        
        关键适配：
        - OpenAI 的 system message 转为 Anthropic 的 system 参数
        - 使用同一个 LLM_API_KEY（用户已配置）
        """
        start_time = time.time()
        
        # 转换 messages 格式：提取 system message
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg += msg['content'] + "\n"
            else:
                chat_messages.append(msg)
        
        response = self.client.messages.create(
            model=self.model,
            system=system_msg.strip() or None,  # 空字符串也转为 None
            messages=chat_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **({"stop_sequences": stop} if stop else {}),  # 空列表不传，避免 API 报错
        )
        
        latency = (time.time() - start_time) * 1000
        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            usage={
                'prompt_tokens': response.usage.input_tokens,
                'completion_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.input_tokens + response.usage.output_tokens
            },
            latency_ms=latency,
            raw_response=response
        )
    
    def _chat_google(self, messages, max_tokens, temperature, stop):
        """Google Gemini 原生 SDK 路径
        
        关键适配：
        - 提取 system message 作为 system_instruction（Gemini 原生支持）
        - OpenAI 的 messages 格式转为 Gemini 的 contents 格式
        - 使用同一个 LLM_API_KEY（用户已配置）
        """
        start_time = time.time()
        
        # 提取 system message
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg += msg['content'] + "\n"
            else:
                chat_messages.append(msg)
        
        # 创建模型（含 system instruction）
        model_kwargs = {}
        if system_msg.strip():
            model_kwargs['system_instruction'] = system_msg.strip()
        model = self.client.GenerativeModel(self.model, **model_kwargs)
        
        # 转换 messages → Gemini contents
        contents = []
        for msg in chat_messages:
            role = 'user' if msg['role'] == 'user' else 'model'
            contents.append({'role': role, 'parts': [msg['content']]})
        
        response = model.generate_content(
            contents,
            generation_config={
                'max_output_tokens': max_tokens,
                'temperature': temperature,
                'stop_sequences': stop or [],
            }
        )
        
        latency = (time.time() - start_time) * 1000
        return LLMResponse(
            content=response.text,
            model=self.model,
            usage={
                'prompt_tokens': getattr(response.usage_metadata, 'prompt_token_count', 0),
                'completion_tokens': getattr(response.usage_metadata, 'candidates_token_count', 0),
                'total_tokens': getattr(response.usage_metadata, 'total_token_count', 0),
            },
            latency_ms=latency,
            raw_response=response
        )
```

**向后兼容保证**：
- `__init__` 签名完全不变（model, api_key, api_base, timeout, max_retries）
- 所有现有调用方代码零修改
- 没有 `LLM_API_BASE` 或 `LLM_API_BASE` 是任何 OpenAI 兼容地址时 → 自动走原有 OpenAI 路径，行为与现在 100% 一致
- 只有当 `api_base` 包含 `anthropic.com` 或 `googleapis.com` 时才启用新路径

**⚠️ 需同步适配的其他方法**：

`LLMClient` 还有以下方法也需按 `_provider` 路由（目前全部走 OpenAI SDK）：

| 方法 | 行号 | 改动 |
|------|------|------|
| `achat()` | L176 | 异步版 `chat()`，需新增 `_achat_anthropic()` / `_achat_google()`。当前每次创建新 `AsyncOpenAI` 客户端。Anthropic 用 `AsyncAnthropic`，Google 用 `genai.GenerativeModel.generate_content_async()` |
| `complete()` | L92 | 内部调用 `self.chat()`，已自动路由，**无需改动** |
| `embed()` | L227 | 硬编码 `text-embedding-ada-002`。此方法是辅助方法，主 Embedding 逻辑在 `APIEmbeddingBackend`。建议：若 `_provider != 'openai'`，抛出 `NotImplementedError("请使用 APIEmbeddingBackend 进行 Embedding")` |
| `extract_entities()` | L245 | 内部调用 `self.complete()` → `self.chat()`，已自动路由，**无需改动** |
| `summarize()` | L263 | 内部调用 `self.complete()` → `self.chat()`，已自动路由，**无需改动** |
| `check_relevance()` | L273 | 内部调用 `self.complete()` → `self.chat()`，已自动路由，**无需改动** |

`achat()` 异步路由伪代码：

```python
async def achat(self, messages, max_tokens=None, temperature=0.7, **kwargs):
    if max_tokens is None:
        max_tokens = int(os.environ.get('LLM_DEFAULT_MAX_TOKENS', '2000'))
    
    if self._provider == 'anthropic':
        return await self._achat_anthropic(messages, max_tokens, temperature, stop=kwargs.get('stop'))
    elif self._provider == 'google':
        return await self._achat_google(messages, max_tokens, temperature)
    else:
        return await self._achat_openai(messages, max_tokens, temperature, **kwargs)

async def _achat_openai(self, messages, max_tokens, temperature, **kwargs):
    """原有 achat() L176-226 逻辑搬迁：用 AsyncOpenAI 调用"""
    from openai import AsyncOpenAI
    client_kwargs = {"api_key": self.api_key, "timeout": self.timeout}
    if self.api_base:
        client_kwargs["base_url"] = self.api_base
    async_client = AsyncOpenAI(**client_kwargs)
    
    start_time = time.time()
    response = await async_client.chat.completions.create(
        model=self.model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs
    )
    latency = (time.time() - start_time) * 1000
    
    return LLMResponse(
        content=response.choices[0].message.content,
        model=response.model,
        usage={
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        },
        latency_ms=latency,
        raw_response=response
    )

async def _achat_anthropic(self, messages, max_tokens, temperature, stop=None):
    """Anthropic 异步路径"""
    import time
    start_time = time.time()
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=self.api_key, timeout=self.timeout)
    system_msg, chat_messages = "", []
    for msg in messages:
        if msg['role'] == 'system':
            system_msg += msg['content'] + "\n"
        else:
            chat_messages.append(msg)
    kwargs = {}
    if system_msg.strip():
        kwargs['system'] = system_msg.strip()
    if stop:
        kwargs['stop_sequences'] = stop if isinstance(stop, list) else [stop]
    response = await client.messages.create(
        model=self.model,
        messages=chat_messages, max_tokens=max_tokens, temperature=temperature,
        **kwargs,
    )
    latency = (time.time() - start_time) * 1000
    return LLMResponse(
        content=response.content[0].text,
        model=response.model,
        usage={
            'prompt_tokens': response.usage.input_tokens,
            'completion_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens
        },
        latency_ms=latency,
        raw_response=response
    )

async def _achat_google(self, messages, max_tokens, temperature):
    """Google 异步路径（对齐同步版 _chat_google，正确提取 system_instruction）"""
    import time
    start_time = time.time()
    # 提取 system 消息（与同步版 _chat_google 逻辑一致）
    system_msg = ""
    chat_messages = []
    for msg in messages:
        if msg['role'] == 'system':
            system_msg += msg['content'] + "\n"
        else:
            chat_messages.append(msg)
    model_kwargs = {}
    if system_msg.strip():
        model_kwargs['system_instruction'] = system_msg.strip()
    model = self.client.GenerativeModel(self.model, **model_kwargs)
    contents = [{'role': 'user' if m['role'] == 'user' else 'model',
                 'parts': [m['content']]} for m in chat_messages]
    response = await model.generate_content_async(
        contents, generation_config={'max_output_tokens': max_tokens, 'temperature': temperature}
    )
    latency = (time.time() - start_time) * 1000
    return LLMResponse(
        content=response.text,
        model=self.model,
        usage={
            'prompt_tokens': getattr(response.usage_metadata, 'prompt_token_count', 0),
            'completion_tokens': getattr(response.usage_metadata, 'candidates_token_count', 0),
            'total_tokens': getattr(response.usage_metadata, 'total_token_count', 0),
        },
        latency_ms=latency,
        raw_response=response
    )
```

### 任务 6.2：Embedding 后端同理自适应

**改动文件**：`recall/embedding/api_backend.py`

**现状分析**：`APIEmbeddingBackend` 的 `client` 属性（L167-185）直接用 `from openai import OpenAI` 创建客户端，读取 `EMBEDDING_API_KEY` / `EMBEDDING_API_BASE` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION`。与 LLM 一样，只支持 OpenAI 兼容 API。

**改动方式**：与 LLMClient 相同的自适应策略，基于 `EMBEDDING_API_BASE` 域名 + `EMBEDDING_MODEL` 名称自动选择 SDK：

```python
class APIEmbeddingBackend(EmbeddingBackend):
    def __init__(self, config, cache_dir=None):
        super().__init__(config, cache_dir=cache_dir)
        
        self.api_base = (
            config.api_base or
            os.environ.get('EMBEDDING_API_BASE') or
            self.DEFAULT_BASES.get(config.backend, "https://api.openai.com/v1")
        )
        self.api_key = config.api_key or self._get_api_key_from_env()
        
        # 自动检测提供商（新增，零配置）
        self._provider = self._detect_embedding_provider()
        
        # ... 其余原逻辑不变 ...
    
    def _detect_embedding_provider(self) -> str:
        """根据 EMBEDDING_API_BASE 域名和 EMBEDDING_MODEL 名称自动检测
        
        检测优先级：
        1. api_base 域名匹配（最可靠）
        2. model 名称匹配（兜底）
        3. 默认 openai（兼容所有中转站）
        
        注意：Anthropic 目前无独立 Embedding API，
        使用 Anthropic 时 Embedding 通常搭配 Voyage AI 或其他兼容服务。
        """
        model = self.config.api_model.lower() if self.config.api_model else ''
        
        # 1. 按 api_base 域名检测
        if self.api_base:
            base_lower = self.api_base.lower()
            if 'googleapis.com' in base_lower or 'generativelanguage' in base_lower:
                return 'google'
            if 'voyageai.com' in base_lower:
                return 'voyage'  # Voyage AI（Anthropic 推荐的 Embedding 服务）
            if 'cohere.com' in base_lower or 'cohere.ai' in base_lower:
                return 'cohere'
            # 其他任何地址 → 走 OpenAI SDK
            return 'openai'
        
        # 2. 按 model 名称检测
        if model.startswith('voyage'):
            return 'voyage'
        if model.startswith('embed-') and ('cohere' in model or 'english' in model or 'multilingual' in model):
            return 'cohere'
        if model.startswith('text-embedding') or model.startswith('embedding-'):
            # 可能是 Google 的 text-embedding-004 或 OpenAI 的
            pass
        
        # 3. 默认 OpenAI
        return 'openai'
    
    @property
    def client(self):
        """获取 Embedding 客户端（根据提供商自动选择）"""
        if self._client is None:
            if self._provider == 'google':
                self._client = self._create_google_embed_client()
            elif self._provider == 'voyage':
                self._client = self._create_voyage_client()
            else:
                # OpenAI / 硅基流动 / 中转站 / Cohere 兼容 — 原有逻辑
                self._client = self._create_openai_client()
        return self._client
    
    def _create_openai_client(self):
        """原有 OpenAI 客户端创建逻辑（完全不变）"""
        from openai import OpenAI
        return OpenAI(api_key=self.api_key, base_url=self.api_base)
    
    def _create_google_embed_client(self):
        """Google Embedding 客户端"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            return genai
        except ImportError:
            raise ImportError("使用 Google Embedding 需要安装: pip install google-generativeai")
    
    def _create_voyage_client(self):
        """Voyage AI 客户端（Anthropic 推荐的 Embedding 服务）"""
        try:
            import voyageai
            return voyageai.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError("使用 Voyage AI Embedding 需要安装: pip install voyageai")
    
    def encode(self, text):
        """编码 — 根据提供商自动路由"""
        if self._provider == 'google':
            return self._encode_google(text)
        elif self._provider == 'voyage':
            return self._encode_voyage(text)
        else:
            return self._encode_openai(text)  # 原有逻辑
    
    def _encode_openai(self, text):
        """OpenAI 路径（搬迁原 encode() L186-221 全部代码）"""
        max_retries = 3
        for attempt in range(max_retries):
            if not self._rate_limiter.acquire():
                raise RuntimeError("Embedding API 速率限制超时")
            try:
                response = self.client.embeddings.create(
                    model=self.config.api_model,
                    input=text
                )
                embedding = np.array(response.data[0].embedding, dtype='float32')
                if self.config.normalize:
                    embedding = embedding / np.linalg.norm(embedding)
                return embedding
            except Exception as e:
                if '429' in str(e).lower() and attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 3)
                    continue
                raise
    
    def _encode_google(self, text):
        """Google Embedding 路径"""
        result = self.client.embed_content(
            model=self.config.api_model,
            content=text
        )
        embedding = np.array(result['embedding'], dtype='float32')
        if self.config.normalize:
            embedding = embedding / np.linalg.norm(embedding)
        return embedding
    
    def _encode_voyage(self, text):
        """Voyage AI 路径"""
        result = self.client.embed([text], model=self.config.api_model)
        embedding = np.array(result.embeddings[0], dtype='float32')
        if self.config.normalize:
            embedding = embedding / np.linalg.norm(embedding)
        return embedding
    
    def encode_batch(self, texts):
        """批量编码 — 按 _provider 路由"""
        if self._provider == 'google':
            return self._encode_batch_google(texts)
        elif self._provider == 'voyage':
            return self._encode_batch_voyage(texts)
        else:
            return self._encode_batch_openai(texts)  # 原有逻辑
    
    def _encode_batch_openai(self, texts):
        """原有 encode_batch() L223-265 全部代码搬迁至此"""
        all_embeddings = []
        batch_size = min(self.config.batch_size, 100)  # OpenAI 限制
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            max_retries = 3
            for attempt in range(max_retries):
                if not self._rate_limiter.acquire():
                    raise RuntimeError("Embedding API 速率限制超时")
                
                try:
                    response = self.client.embeddings.create(
                        model=self.config.api_model,
                        input=batch
                    )
                    for item in response.data:
                        embedding = np.array(item.embedding, dtype='float32')
                        if self.config.normalize:
                            embedding = embedding / np.linalg.norm(embedding)
                        all_embeddings.append(embedding)
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    if '429' in error_str or 'rate limit' in error_str:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 3
                            time.sleep(wait_time)
                            continue
                    raise
        
        return np.array(all_embeddings)
    
    def _encode_batch_google(self, texts):
        """Google 批量 Embedding"""
        result = self.client.embed_content(
            model=self.config.api_model,
            content=texts  # Google API 原生支持批量
        )
        embeddings = np.array(result['embedding'], dtype='float32')
        if self.config.normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / np.where(norms > 0, norms, 1)
        return embeddings
    
    def _encode_batch_voyage(self, texts):
        """Voyage AI 批量 Embedding"""
        result = self.client.embed(texts, model=self.config.api_model)
        embeddings = np.array(result.embeddings, dtype='float32')
        if self.config.normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / np.where(norms > 0, norms, 1)
        return embeddings
```

**Embedding 配置场景示例**（全部使用现有变量）：

```bash
# 场景 1：OpenAI / 硅基流动（与现在完全一样）
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
EMBEDDING_DIMENSION=1024

# 场景 2：Google Embedding
EMBEDDING_API_KEY=AIzaSy-xxx
EMBEDDING_API_BASE=https://generativelanguage.googleapis.com
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIMENSION=768

# 场景 3：Voyage AI（Anthropic 推荐，配合 Claude 使用）
EMBEDDING_API_KEY=pa-xxx
EMBEDDING_API_BASE=https://api.voyageai.com/v1
EMBEDDING_MODEL=voyage-3
EMBEDDING_DIMENSION=1024

# 场景 4：Cohere Embed（OpenAI 兼容格式）
EMBEDDING_API_KEY=co-xxx
EMBEDDING_API_BASE=https://api.cohere.com/v1
EMBEDDING_MODEL=embed-multilingual-v3.0
EMBEDDING_DIMENSION=1024
```

**MODEL_DIMENSIONS 扩展**（在现有映射基础上追加）：

```python
MODEL_DIMENSIONS = {
    # === 现有（不动）===
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "BAAI/bge-large-zh-v1.5": 1024,
    "BAAI/bge-large-en-v1.5": 1024,
    "BAAI/bge-m3": 1024,
    "text-embedding-004": 768,
    "embedding-001": 768,
    # === v5.0 新增 ===
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-code-3": 1024,
    "embed-multilingual-v3.0": 1024,
    "embed-english-v3.0": 1024,
    "embed-multilingual-light-v3.0": 384,
}
```

**向后兼容保证**：
- `__init__` 签名完全不变
- 所有现有 Embedding 配置（OpenAI / 硅基流动 / 自定义 API）行为 100% 不变
- `EMBEDDING_DIMENSION` 仍然生效——手动设置时覆盖自动检测，未设置时从 `MODEL_DIMENSIONS` 查表
- 只有 `EMBEDDING_API_BASE` 指向非 OpenAI 兼容官方域名时才启用新路径

> **❗ 同步注意**：`recall/embedding/base.py`（L54-65，共 261 行）也有一份 `MODEL_DIMENSIONS` 副本，但缺少 `text-embedding-004` 和 `embedding-001` 两个 Google 模型。实施时应将 `base.py` 和 `api_backend.py`（共 265 行）的 `MODEL_DIMENSIONS` 合并为单一来源（以 `api_backend.py` 为准），避免重复定义。

### 任务 6.3：新增可选依赖

**改动文件**：`pyproject.toml`

```toml
[project.optional-dependencies]
anthropic = ["anthropic>=0.30.0"]
google = ["google-generativeai>=0.8.0"]
voyage = ["voyageai>=0.3.0"]
reranker = ["cohere>=5.0"]
all-llm = ["anthropic>=0.30.0", "google-generativeai>=0.8.0", "voyageai>=0.3.0"]
```

> **⚠️ 核心依赖补充**：Phase 5 的 PromptManager 使用了 `import yaml`（`yaml.safe_load`），而 `pyyaml` 不在当前 `pyproject.toml` 的 `dependencies` 中。必须将 `"pyyaml>=6.0"` 添加到 **核心依赖**（`[project] dependencies`）中，否则 PromptManager 将在运行时抛出 `ModuleNotFoundError`。

> **注意**：不新增任何配置项到 `SUPPORTED_CONFIG_KEYS`。用户只需修改现有的 `LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL` 即可切换提供商。

---

## 九、Phase 7：重排序器多样性

> **目标**：支持 Cohere Rerank 和自定义模型重排序。  
> **预计工作量**：1-2 天

### 任务 7.1：重排序器抽象层

**新建文件**：`recall/retrieval/reranker.py`

```python
"""recall/retrieval/reranker.py — 可插拔的重排序后端"""

import os
from typing import List, Tuple

class RerankerBase:
    """重排序器基类"""
    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        raise NotImplementedError

class BuiltinReranker(RerankerBase):
    """内置重排序器（从 eleven_layer.py _l9_rerank L1036-1074 搬迁）
    
    原逻辑：遍历候选文档，关键词匹配 +0.05/次，实体匹配 +0.1/次
    搬迁后作为独立重排序器，签名统一为 rerank(query, documents, top_k)
    """
    def rerank(self, query, documents, top_k):
        # 简单 TF-IDF 多因素加权（原 _l9_rerank 逻辑）
        query_lower = query.lower()
        query_keywords = query_lower.split()
        
        scored = []
        for idx, doc in enumerate(documents):
            bonus = 0.0
            doc_lower = doc.lower()
            
            # 关键词匹配加分
            for kw in query_keywords:
                if kw in doc_lower:
                    bonus += 0.05
            
            # 查询整体匹配额外加分
            if query_lower in doc_lower:
                bonus += 0.2
            
            scored.append((idx, bonus))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

class CohereReranker(RerankerBase):
    """Cohere Rerank API"""
    def __init__(self, api_key=None, model="rerank-multilingual-v3.0"):
        import cohere
        self.client = cohere.Client(api_key or os.getenv('COHERE_API_KEY'))
        self.model = model
    
    def rerank(self, query, documents, top_k):
        response = self.client.rerank(
            model=self.model, query=query, documents=documents, top_k=top_k
        )
        return [(r.index, r.relevance_score) for r in response.results]

class CrossEncoderReranker(RerankerBase):
    """Cross-Encoder 本地模型"""
    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name)
    
    def rerank(self, query, documents, top_k):
        pairs = [(query, doc) for doc in documents]
        scores = self.model.predict(pairs)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

class RerankerFactory:
    @staticmethod
    def create(backend="builtin"):
        if backend == "cohere":
            return CohereReranker()
        elif backend == "cross-encoder":
            return CrossEncoderReranker()
        else:
            if backend != "builtin":
                import logging
                logging.getLogger(__name__).warning(
                    f"未知的 RERANKER_BACKEND='{backend}'，降级到 builtin"
                )
            return BuiltinReranker()
```

### 任务 7.2：集成到 11 层检索

**改动文件**：`recall/retrieval/eleven_layer.py`

在 L9 (Rerank) 和 L10 (Cross-Encoder) 层替换为可插拔的重排序器：

```python
# eleven_layer.py __init__ 中添加（在现有 17 个参数之后）
from recall.retrieval.reranker import RerankerFactory
self.reranker = RerankerFactory.create(
    os.getenv('RERANKER_BACKEND', 'builtin')
)
```

**⚠️ 接口适配注意**（AI 实施必读）：

原 `_l9_rerank()` 的接口（L1036-1070）是 **in-place 修改 `scores: Dict[str, float]`**，签名为：
```python
def _l9_rerank(self, query, entities, keywords, candidates, scores) -> None
```

而新 `RerankerBase.rerank()` 返回 `List[Tuple[int, float]]`，签名不同。集成时需要写一个**适配器包装**：

```python
def _l9_rerank(self, query, entities, keywords, candidates, scores):
    """L9: Rerank — 使用可插拔重排序器"""
    start_time = time.perf_counter()
    
    # 准备文档列表
    doc_ids = list(candidates)
    documents = [self._get_content(doc_id) for doc_id in doc_ids]
    
    if isinstance(self.reranker, BuiltinReranker):
        # 内置重排序器使用原有逻辑（保留 entities/keywords 加分）
        for doc_id in candidates:
            bonus = 0.0
            content = self._get_content(doc_id)
            if keywords:
                for kw in keywords:
                    if kw.lower() in content.lower():
                        bonus += 0.05
            if entities:
                for entity in entities:
                    if entity.lower() in content.lower():
                        bonus += 0.1
            scores[doc_id] += bonus
    else:
        # 外部重排序器（Cohere/CrossEncoder）
        ranked = self.reranker.rerank(query, documents, top_k=len(documents))
        for idx, score in ranked:
            scores[doc_ids[idx]] += score * 0.3  # 将外部分数缩放后叠加
    
    self.stats.append(LayerStats(
        layer=RetrievalLayer.L9_RERANK.value,
        input_count=len(candidates),
        output_count=len(candidates),
        time_ms=(time.perf_counter() - start_time) * 1000
    ))
```

> **关键**：内置模式（`BuiltinReranker`）原封不动保留原 `_l9_rerank` 逻辑（含 entities/keywords 加分），仅外部重排序器走新接口。这确保 `RERANKER_BACKEND=builtin`（默认值）时行为与 v4.2 100% 一致。

### 任务 7.3：新增配置项

```python
'RERANKER_BACKEND',     # builtin / cohere / cross-encoder
'COHERE_API_KEY',       # Cohere API 密钥
'RERANKER_MODEL',       # 自定义模型名
```

---

## 十、改动文件清单与影响范围

### 10.1 新建文件清单

| Phase | 新建文件 | 说明 |
|:-----:|----------|------|
| 1 | `recall/mode.py` | 全局模式管理器 |
| 3 | `recall/index/metadata_index.py` | 元数据索引 |
| 4 | `recall/mcp_server.py` | MCP Server 入口 |
| 4 | `recall/mcp/__init__.py` | MCP 包 |
| 4 | `recall/mcp/tools.py` | MCP Tools |
| 4 | `recall/mcp/resources.py` | MCP Resources |
| 4 | `recall/mcp/transport.py` | SSE 传输 |
| 4 | `docs/MCP-SETUP.md` | MCP 使用指南 |
| 5 | `recall/prompts/__init__.py` | Prompt 包 |
| 5 | `recall/prompts/manager.py` | Prompt 管理器 |
| 5 | `recall/prompts/templates/*.yaml` | 7 个模板文件 |
| 7 | `recall/retrieval/reranker.py` | 重排序器抽象层 |
| — | `tests/test_mode_switch.py` | 模式切换测试 |
| — | `tests/test_batch_api.py` | 批量 API 测试 |
| — | `tests/test_mcp.py` | MCP Server 测试 |

**共计新建 ~18 个文件**

### 10.2 改动文件清单

| Phase | 改动文件 | 改动量 | 风险 |
|:-----:|----------|:------:|:----:|
| 1 | `recall/engine.py` | ~50 行 | 低（加 if 守卫） |
| 1 | `recall/server.py` | ~40 行 | 低（加守卫 + 新端点） |
| 1 | `recall/storage/layer0_core.py` | ~10 行 | 极低 |
| 1 | `recall/graph/knowledge_graph.py` | ~30 行 | 低 |
| 1 | `recall/graph/temporal_knowledge_graph.py` | ~5 行 | 极低（同步 RELATION_TYPES） |
| 1 | `recall/processor/consistency.py` | ~15 行 | 低 |
| 1 | `recall/processor/context_tracker.py` | ~10 行 | 低 |
| 1 | `recall/processor/scenario.py` | ~10 行 | 低 |
| 1 | `recall/models/turn.py` | ~15 行 | 低（新增字段，向后兼容） |
| 1 | `recall/config.py` | ~5 行 | 极低（新增 `from .mode import RecallMode, get_mode_config` 便捷再导出，方便 `from recall.config import RecallMode`） |
| 1 | `start.ps1` | ~20 行 | 低（追加配置键 + 模板） |
| 1 | `start.sh` | ~20 行 | 低（追加配置键 + 模板） |
| 1 | `manage.ps1` | ~80 行 | 低（配置模板 + UI 语言统一） |
| 1 | `manage.sh` | ~15 行 | 极低（配置模板追加） |
| 2 | `recall/engine.py` | ~5 行 | 低（修复 3 个默认值） |
| 2 | `recall/index/temporal_index.py` | ~60 行 | 中（核心算法改） |
| 2 | `recall/index/inverted_index.py` | ~40 行 | 中（持久化改） |
| 2 | `recall/graph/backends/json_backend.py` | ~20 行 | 低 |
| 2 | `recall/storage/volume_manager.py` | ~30 行 | 低 |
| 3 | `recall/engine.py` | ~60 行 | 低（新增方法） |
| 3 | `recall/server.py` | ~30 行 | 低（新端点） |
| 3 | `recall/retrieval/eleven_layer.py` | ~15 行 | 低 |
| 5 | `recall/processor/smart_extractor.py` | ~5 行 | 极低（替换变量） |
| 5 | `recall/graph/llm_relation_extractor.py` | ~5 行 | 极低 |
| 5 | `recall/processor/unified_analyzer.py` | ~5 行 | 极低 |
| 5 | 其他 4 个 processor 文件 | 各 ~5 行 | 极低 |
| 6 | `recall/utils/llm_client.py` | ~80 行 | 低（新增路径，原路径不变） |
| 6 | `recall/embedding/api_backend.py` | ~120 行 | 低（新增检测逻辑 + 多路由，原路径不动） |
| 7 | `recall/retrieval/eleven_layer.py` | ~10 行 | 低 |
| 7 | `start.ps1` / `start.sh` | 各 ~10 行 | 极低（追加配置键） |
| 7 | `manage.ps1` / `manage.sh` | 各 ~10 行 | 极低（配置模板追加） |
| — | `pyproject.toml` | ~15 行 | 极低 |
| — | `recall/version.py` | 1 行 | 极低（版本号 4.2.0 → 5.0.0） |

**共改动 ~32 个现有文件，总改动量约 ~815 行**

### 10.2.1 版本号更新（跨阶段，最后执行）

所有 Phase 完成后，更新版本号：

| 文件 | 改动 |
|------|------|
| `recall/version.py` | `__version__ = '4.2.0'` → `__version__ = '5.0.0'` |
| `pyproject.toml` | `version = "4.2.0"` → `version = "5.0.0"` |
| `docs/FEATURE-STATUS.md` | 新增 v5.0 功能状态章节 |

> **注意**：`recall/__init__.py` 通过 `from .version import __version__` 自动继承版本号，无需单独改动。

### 10.2.2 `recall/config.py` 改动说明

**改动文件**：`recall/config.py`（~5 行）

```python
# 在文件顶部的 import 区域新增：
from .mode import RecallMode, get_mode_config  # v5.0 便捷再导出

# 使用方：
# from recall.config import RecallMode, get_mode_config
```

> 这样外部代码可以统一从 `recall.config` 导入所有配置相关类，而不需要知道 `recall.mode` 的存在。

### 10.3 零影响保证

| 保证项 | 机制 |
|--------|------|
| RP 模式不受影响 | `RECALL_MODE` 默认值 `roleplay` → 所有行为与 v4.2 完全一致 |
| 现有 API 不破坏 | 所有新 API 是追加的，原端点不修改签名 |
| 现有数据不迁移 | Turn 模型新增字段都有默认值，旧数据自动兼容 |
| 现有配置不失效 | 所有新增环境变量都有默认值 |
| 伏笔功能完整保留 | 只在通用模式下跳过伏笔注入，RP 模式完全不变 |
| 原有测试全部通过 | 测试默认走 RP 模式，不受新代码影响 |
| 配置管道完全统一 | 所有新变量同步到 7 处位置（server.py + start/manage × 2 平台 + get_default_config_content） |
| Windows/Linux 行为一致 | manage.ps1 统一为中文；所有脚本配置模板、变量名、默认值、注释**字符级别**完全一致 |
| 性能只升不降 | Phase 2 改 O(n)→O(log n)、全量保存→增量追加、逐条→批量；不删除任何索引 |
| LLM/Embedding 零感知切换 | 只有 api_base 包含官方域名时才启用新路径，其他情况 100% 走原 OpenAI SDK |
| 模式切换安全 | 切换 `RECALL_MODE` 需重启服务；RP 模式下按 `character_id` 隔离的数据在通用模式下仍可通过 `character_id="default"` 正常检索全量数据；不同模式写入的数据物理上共存不冲突 |
| 数据定义去重 | `MODEL_DIMENSIONS` 和 `RELATION_TYPES` 的多处副本合并为单一来源 |

---

## 十一、实施顺序与时间估算

```
┌──────────────────────────────────────────────────────────────┐
│                    实施路线图                                 │
├──────┬───────────────┬──────────┬───────────────────────────┤
│ 阶段 │ 内容          │ 工期     │ 依赖                      │
├──────┼───────────────┼──────────┼───────────────────────────┤
│ P1   │ 核心通用化+配置统一│ 4-5 天  │ 无（第一步必须做）        │
│ P2   │ 性能瓶颈修复   │ 4-5 天  │ 无（可与 P1 并行）        │
│ P3   │ 批量写入+元数据 │ 3-4 天  │ 依赖 P1（Turn 模型）+P2  │
│ P4   │ MCP Server    │ 3-4 天  │ 依赖 P1 + P3（批量 API）  │
│ P5   │ Prompt 工程    │ 2-3 天  │ 依赖 P1（模式感知）       │
│ P6   │ 多 LLM 自适应  │ 2-3 天  │ 无（独立模块，零新增配置）│
│ P7   │ 重排序器       │ 1-2 天  │ 无（独立模块）            │
├──────┼───────────────┼──────────┼───────────────────────────┤
│ 总计 │               │ 19-26 天 │                           │
└──────┴───────────────┴──────────┴───────────────────────────┘
```

### 推荐实施顺序

```
第 1 周：P1（通用化+配置统一）+ P2（性能）并行推进
第 2 周：P3（批量写入）→ P6（多 LLM）
第 3 周：P4（MCP Server）→ P5（Prompt）→ P7（重排序）
第 4 周：集成测试 + 文档更新 + FEATURE-STATUS.md 更新
```

---

## 十二、验证检查清单

### 12.1 Phase 1 验证

- [ ] `RECALL_MODE` 不设置 → 所有现有测试通过（RP 行为不变）
- [ ] `RECALL_MODE=invalid_value` → 日志输出 warning 并回退到 roleplay 模式
- [ ] `RECALL_MODE=general` → 伏笔 API 返回禁用提示，不注入伏笔
- [ ] `RECALL_MODE=general` → character_id 被忽略，数据不按角色隔离
- [ ] `RECALL_MODE=general` → 一致性检查跳过 HAIR_COLOR/SPECIES 等
- [ ] `RECALL_MODE=general` → 图谱关系类型包含通用类型
- [ ] `RECALL_MODE=general` + `FORESHADOWING_ENABLED=true` → 伏笔功能正常
- [ ] Turn 模型新增字段不影响现有数据加载
- [ ] `/v1/mode` 端点返回正确的模式信息
- [ ] engine.py 顶层不再有 foreshadowing 的无条件 import（已改为 `__init__` 内条件导入）
- [ ] 通用模式下 `turn.effective_content` 正确返回 `content` 字段内容
- [ ] 模式切换（修改 `RECALL_MODE`）后重启服务，行为正确切换

### 12.1.1 Phase 1 配置统一验证

- [ ] `start.ps1` 和 `start.sh` 的 supportedKeys 包含所有 6 个 P1 新变量
- [ ] `manage.ps1` 和 `manage.sh` 的默认配置模板包含 v5.0 section
- [ ] `server.py` `get_default_config_content()` 包含 v5.0 section
- [ ] `manage.ps1` UI 为中文，与 `manage.sh` 完全一致
- [ ] `start.ps1` 和 `start.sh` 配置模板 section 标题完全一致
- [ ] `engine.py` 3 个默认值已修复为 `'true'`（TEMPORAL_GRAPH_ENABLED / CONTRADICTION_DETECTION_ENABLED / FULLTEXT_ENABLED）
- [ ] 原先通过脚本启动和直接 Python 启动的行为完全一致

### 12.2 Phase 2 验证

- [ ] temporal_index `query_at_time()` 结果与旧实现一致（正确性）
- [ ] temporal_index `query_range()` 结果与旧实现一致
- [ ] temporal_index `query_before()` 新增 `_sorted_by_fact_end` / `_sorted_by_system_end` 排序列表已正确初始化和维护
- [ ] temporal_index `query_after()` 使用 `_sorted_by_fact_start` / `_sorted_by_system_start`（非 `_sorted_fact`）
- [ ] 10 万条数据下 temporal_index 查询 < 10ms（性能）
- [ ] inverted_index WAL 追加写入正常，重启后 WAL 重放正确
- [ ] inverted_index WAL 重放含 `try/except json.JSONDecodeError` 保护，崩溃后不完整行被安全跳过
- [ ] inverted_index 压缩后主文件与内存状态一致
- [ ] inverted_index `_compact()` 使用 `os.replace()` 原子替换（先写 `.tmp` 再替换），崩溃时不损坏主文件
- [ ] json_backend 延迟保存不丢数据，`flush()` 后全部持久化
- [ ] json_backend `__init__` 中注册了 `atexit.register(self.flush)` 确保正常退出不丢数据
- [ ] json_backend `_unindex_entry()` 正确从 `_sorted_by_fact_end` / `_sorted_by_system_end` 移除条目
- [ ] volume_manager memory_id 索引 O(1) 查找正确

### 12.3 Phase 3 验证

- [ ] `POST /v1/memories/batch` 批量添加 100 条 < 30 秒
- [ ] `add_batch()` 在 `embedding_backend` 未初始化时抛出明确错误
- [ ] `_add_single_fast()` 在 `skip_llm=True` 时使用 `force_mode=ExtractionMode.RULES` 而非 LLM
- [ ] `_add_single_fast()` 返回 `(memory_id, entities, keywords)` 元组，外层正确累积
- [ ] 批量添加后所有索引（倒排/向量/实体/元数据/ngram）正确更新
- [ ] `_batch_update_indexes` 使用公开 API（`add_batch()`、`add_entity_occurrence()`、`ngram_index.add(mid, content)`），不直接操作内部数据结构
- [ ] `_batch_update_indexes` 接收 `all_ngram_data` 参数（`(memory_id, content)` 对列表），`ngram_index.add()` 接收完整原文而非关键词
- [ ] `search(source="bilibili")` 只返回来源为 bilibili 的记忆
- [ ] `search(tags=["热点"])` 过滤正确
- [ ] `MetadataIndex.__init__()` 注册了 `atexit.register(self.flush)` 确保退出不丢数据
- [ ] `_add_single_fast()` 中 `**(metadata or {})` 防御 None 值（非 `**metadata`）

### 12.4 Phase 4 验证

- [ ] MCP Server stdio 模式正常启动
- [ ] Claude Desktop 通过 MCP 调用 `recall_add` 成功
- [ ] Claude Desktop 通过 MCP 调用 `recall_search` 成功
- [ ] MCP Resources `recall://memories` 返回正确
- [ ] `recall-mcp` 命令行入口可用
- [ ] engine.py 新增方法 `list_entities()`、`traverse_graph()`、`list_memories()`、`get_entity_detail()` 均可正常调用
- [ ] `recall_list` 正确解包 `get_paginated()` 返回的 `(memories, total)` 元组
- [ ] `recall_search` 使用 `r.metadata.get("source")` 而非 `getattr(r, "source")` 进行过滤
- [ ] `recall_search` 使用属性访问（`r.score`）而非字典索引访问 `SearchResult`
- [ ] `list_entities()` 调用 `_entity_index.all_entities()` 而非不存在的 `get_all_entities()`
- [ ] `traverse_graph()` 调用 `knowledge_graph.get_relations_for_entity()` 而非不存在的 `get_edges_for_node()`
- [ ] `traverse_graph()` BFS 使用 `collections.deque.popleft()` 而非 `list.pop(0)`
- [ ] `recall_delete` 检查 `engine.delete()` 的布尔返回值，不存在时返回"记忆不存在"
- [ ] MCP Resources 中 URI 路径经过 `urllib.parse.unquote()` 解码（支持中文实体名）
- [ ] `recall-mcp` 入口指向同步 `main()` 函数（内部 `asyncio.run(_async_main())`），非直接 async

### 12.5 Phase 5 验证

- [ ] PromptManager 加载所有 YAML 模板无错误
- [ ] PromptManager `render()` 对不存在的 template_name 抛出明确 `ValueError`（非 KeyError）
- [ ] PromptManager `render()` 对缺少 mode key 和 'default' key 的模板抛出明确 `ValueError`（非 AttributeError）
- [ ] PromptManager `_load_templates()` 在内置模板目录不存在时不报错（首次安装场景）
- [ ] 各模块使用 PromptManager 渲染的 prompt 与原硬编码结果一致
- [ ] 用户自定义 prompt 覆盖正常工作
- [ ] PromptManager 使用 `RECALL_DATA_ROOT`（非 `RECALL_DATA_PATH`）读取用户自定义模板
- [ ] PromptManager docstring 描述为 `str.format()` 变量渲染（非 Jinja2）
- [ ] `pyyaml>=6.0` 已添加到 `pyproject.toml` 核心依赖中

### 12.6 Phase 6 验证

**LLM 自适应：**
- [ ] `LLM_API_BASE=https://api.anthropic.com` + `LLM_MODEL=claude-3-5-sonnet` → 自动检测 Anthropic 并正常调用
- [ ] `LLM_API_BASE=https://generativelanguage.googleapis.com` + `LLM_MODEL=gemini-pro` → 自动检测 Google 并正常调用
- [ ] 无 `LLM_API_BASE` + `LLM_MODEL=claude-3-5-sonnet` → 按模型名兜底检测 Anthropic
- [ ] `LLM_API_BASE=https://my-proxy.com/v1` + `LLM_MODEL=claude-3-5-sonnet` → 走 OpenAI SDK（中转站场景）
- [ ] 未安装 `anthropic` 时指向 `anthropic.com` 给出清晰错误提示
- [ ] OpenAI / 硅基流动 / Ollama 等现有 OpenAI 兼容配置行为完全不变
- [ ] 不存在任何新的 LLM 配置变量（无 LLM_PROVIDER / ANTHROPIC_API_KEY / GOOGLE_API_KEY）
- [ ] `_chat_anthropic` 中 `system=""` 或 `system="  "` 不会传给 API（`strip() or None` 处理）
- [ ] `_chat_anthropic` 中 `stop=None` 时不传 `stop_sequences` 参数（避免 API 报错）
- [ ] `_chat_google` 正确将 system 消息提取为 `system_instruction` 参数传给 `GenerativeModel()`
- [ ] `_achat_google` 与同步版 `_chat_google` 行为一致：提取 system 消息为 `system_instruction`，非 system 消息不映射为 `role='user'`
- [ ] `_achat_anthropic` 正确转发 `stop` 参数为 `stop_sequences`（与同步版 `_chat_anthropic` 一致）
- [ ] `achat()` 路由 Anthropic 时传递 `stop=kwargs.get('stop')`
- [ ] `RerankerFactory.create()` 遇到未知 backend 值时输出 warning 日志后降级为 builtin

**Embedding 自适应：**
- [ ] `EMBEDDING_API_BASE=https://generativelanguage.googleapis.com` + `EMBEDDING_MODEL=text-embedding-004` → 自动检测 Google 并通过 `google-generativeai` SDK 调用
- [ ] `EMBEDDING_API_BASE=https://api.voyageai.com/v1` + `EMBEDDING_MODEL=voyage-3` → 自动检测 Voyage AI 并通过 `voyageai` SDK 调用
- [ ] `EMBEDDING_API_BASE=https://api.siliconflow.cn/v1` + OpenAI 兼容模型 → 行为与现在完全一致
- [ ] `EMBEDDING_API_BASE=https://api.openai.com/v1` → 行为与现在完全一致
- [ ] 未设 `EMBEDDING_DIMENSION` 时 → 从扩展后的 `MODEL_DIMENSIONS` 自动查表
- [ ] 手动设 `EMBEDDING_DIMENSION=512` 时 → 覆盖自动查表值
- [ ] 未安装 `google-generativeai` 时指向 `googleapis.com` 给出清晰错误提示
- [ ] 未安装 `voyageai` 时指向 `voyageai.com` 给出清晰错误提示
- [ ] 不存在任何新的 Embedding 配置变量（仍只使用 EMBEDDING_API_KEY / EMBEDDING_API_BASE / EMBEDDING_MODEL / EMBEDDING_DIMENSION）

### 12.7 Phase 7 验证

- [ ] `RERANKER_BACKEND=builtin` → 行为与现在完全一致
- [ ] `RERANKER_BACKEND=cohere` → 使用 Cohere Rerank API
- [ ] `RERANKER_BACKEND=cross-encoder` → 使用本地 Cross-Encoder 模型

### 12.8 全局回归验证

- [ ] **所有 18 个现有测试文件通过**
- [ ] RP 模式下 SillyTavern 插件功能完整（伏笔/角色/一致性检查）
- [ ] 通用模式下爬虫数据批量写入 + 元数据过滤正常
- [ ] 知识库模式下纯知识管理正常（无 RP 功能干扰）

### 12.9 配置统一全局验证

- [ ] `start.ps1` 和 `start.sh` 的 supportedKeys 完全一致（逻辑等价）
- [ ] `manage.ps1` 和 `manage.sh` 的默认配置模板完全一致（变量名 + 默认值 + 注释）
- [ ] `start.ps1` 和 `start.sh` 的默认配置模板**字符级别完全一致**（含 section 标题、括号、注释详细度）
- [ ] `server.py` `get_default_config_content()` 与脚本模板完全一致
- [ ] `server.py` `SUPPORTED_CONFIG_KEYS` 包含所有 9 个 5.0 新变量
- [ ] 通过脚本启动和直接 `python -m recall` 启动，行为完全一致
- [ ] 新安装用户默认配置包含所有 v5.0 配置项
- [ ] `start.sh` 的 9 处配置模板差异已全部修复（见任务 1.11.4 清单）
- [ ] 新增的 2 处跨模板差异（#16 LLM Max Tokens 注释措辞、#17 IVF-HNSW 参数注释）已修复
- [ ] `start.ps1` 遗留的多余“时态知识图谱配置”子标题已清理
- [ ] `base.py` 和 `api_backend.py` 的 `MODEL_DIMENSIONS` 已合并为单一来源
- [ ] `knowledge_graph.py` 和 `temporal_knowledge_graph.py` 的 `RELATION_TYPES` 已统一为单一来源

### 12.10 版本与依赖验证

- [ ] `recall/version.py` 版本号已更新为 `5.0.0`
- [ ] `pyproject.toml` 版本号已更新为 `5.0.0`
- [ ] `recall/__init__.py` 通过 `from .version import __version__` 自动继承正确版本
- [ ] `recall/config.py` 已新增 `from .mode import RecallMode, get_mode_config` 便捷再导出
- [ ] `pyproject.toml` 核心依赖已包含 `pyyaml>=6.0`（PromptManager 需要）
- [ ] `docs/FEATURE-STATUS.md` 已新增 v5.0 功能状态章节

---

> **本文档版本**：v1.12（伪代码终极校准版）  
> **状态**：待审批  
> **v1.1 审计**：修正了 ~20 处行号引用、文件行数统计、RELATION_TYPES 数量；新增任务 1.11 配置管道统一同步  
> **v1.2 更新**：任务 6.2 从存根扩展为完整 Embedding 自适应方案  
> **v1.3 更新**：全面二次审计修正 — 修复了 foreshadowing.py(1211→1234) / foreshadowing_analyzer.py(823→853) 行数；修正 15+ 处行号偏差；修正任务 1.6 一致性检查器 5 个不存在的方法名；修正 Phase 3 `embed_batch`→`encode_batch`；修正任务 1.2 `add()` 的 character_id 描述（metadata 提取非显式参数）；新增 `voyageai`/`cohere` 到 pyproject.toml 可选依赖；新增 `temporal_knowledge_graph.py` RELATION_TYPES 同步注意事项；新增 `base.py` MODEL_DIMENSIONS 去重注意事项；扩展任务 1.11.4 从 1 处差异到 9 处完整清单；验证清单 12.9 新增 4 项检查  
> **v1.4 更新**：三次审计修正 — 修正 `api_backend.py` client 属性行号(L182-192→L167-184)；修正 `inverted_index.py` `_save()` 行号(L32-35→L34-38)；发现并补录第 9 处 start.ps1/start.sh 配置模板差异(v4.1 section 标题格式 ╔═══╗ vs ============)  
> **v1.5 更新**：AI 可执行完善 — (1) 展开 RP_RELATION_TYPES 全部 19 种（原 `# ... 原有 19 种不变 ...`）；(2) Phase 6 _chat_openai 填充完整搬迁代码（原空壳注释）；(3) 新增 achat() 异步多提供商路由 + 6 个辅助方法适配说明表；(4) Phase 6.2 _encode_openai 填充完整搬迁代码 + encode_batch 三路由完整伪代码（原 "同理" 一句话）；(5) Phase 4 MCP Tools 从纯表格扩展为完整 register_tools/call_tool 伪代码 + mcp_server.py 完整入口；(6) MCP Resources 从 URI 注释扩展为完整 register_resources/read_resource 伪代码；(7) Phase 5 PromptManager 新增 _load_templates() 实现 + YAML 模板格式示例；(8) Task 5.3 迁移表精确到变量名和行号（原仅"内联 prompt"）；(9) Task 1.10 新增 v5.0 默认配置模板精确文本（9 个变量的完整 section）  
> **v1.6 更新**：Zero-Gap 终审修复 — (1) `_achat_openai` 从空桩填充完整异步代码（对齐 _chat_openai 完成度）；(2) `_encode_batch_openai` 从 pass 填充完整分批+重试+限流代码；(3) 任务 4.4 MCP SSE Transport 从一句话扩展为完整 `create_sse_app()` 实现 + uvicorn 集成；(4) `query_before`/`query_after` 从"同理"扩展为完整 bisect 实现 + end-time 排序列表说明；(5) MCP 剩余 6 个 Tool 补全 inputSchema + call_tool 分发实现（含 recall_graph_traverse 修正原 /v1/graph/query → /v1/graph/traverse、recall_stats 修正原 /v1/admin/stats → /v1/stats）；(6) `BuiltinReranker` 从空壳标注完整搬迁来源(eleven_layer.py _l9_rerank L1036-1074) + 完整实现；(7) `_achat_anthropic`/`_achat_google` 的 LLMResponse 从 `...` 截断补全 usage 字段映射 + latency 计算；(8) 新增 `_add_single_fast` + `_batch_update_indexes` 完整方法定义（原只被引用未定义）；(9) 清理早期 MCP 草稿重复代码块  
> **v1.7 更新**：全面交叉审计修正（6 个子审计并行验证）—  
> **CRITICAL 修复(5)**：(1) `_add_single_fast()` 伪代码 `self._smart_extractor` → `self.smart_extractor`（无下划线前缀，匹配 engine.py L830）；(2) `extract_fast()` → `extract()`（SmartExtractor 无 extract_fast 方法）；(3) MCP `recall_search` / `recall_search_filtered` 的 `r['score']` 字典访问 → `r.score` 属性访问（SearchResult 是 dataclass）；(4) MCP `recall_list` 修复 `get_paginated()` 元组解包（返回 (memories, total)）；(5) MCP `recall_add_turn` 修复 AddTurnResult dataclass 格式化  
> **行号修正(20+)**：§1.1 表 9 处（layer0_core L73→L67、consistency L55→L50/L141→L139、context_tracker L55→L50、engine L288→L287/L2082→L2077、scenario L44-56→L44-52/L92→L89、base L17→L15）；§1.2 表 5 处（temporal_index L277→L276、inverted_index L34→L31、volume_manager L191→L185、ngram_index L153→L154）；任务正文行号同步修正（1.2/1.4/1.7/1.9/2.1/2.2/2.3）；Phase 6 方法表 5 处（achat L173→L175、complete L92→L97、embed L227→L228、summarize L263→L264、check_relevance L273→L275）；搬迁注释行号修正（chat L117→L118、achat L191→L193、encode L185→L186、encode_batch L216-256→L216-265、api_backend client L167→L170、base.py L55-63→L57-66 共 261 行）  
> **配置统一扩展**：任务 1.11.4 从 9 处差异扩展为 15 处（新增 6 处跨模板差异：时态知识图谱子标题格式三方不一致、server.py LLM Max Tokens 多余说明、Retrieval/Dedup/SmartExtractor 注释措辞差异、manage.sh v4.1 标题格式、start.sh 三路径权重注释均简略）  
> **MCP 完善**：新增 5 个缺失 engine 方法的"需新增"注解（list_entities/traverse_graph/list_memories/get_entity_detail + get→get_memory 别名说明）；新增前置依赖说明块列出已有 vs 待建方法  
> **其他**：json_backend 性能条目从 add_node 扩展为 add_node()/add_edge() 双触发；inverted_index 新增"已有 dirty_count 优化"注解；_achat_anthropic 补充遗漏的 start_time 初始化；_create_openai_client docstring 修正  
> **下一步**：确认计划后，按 Phase 顺序逐步实施
> **v1.8 更新**：精确行号重校准（基于 grep_search 终端精确验证，修正 v1.7 子审计错误校准）—  
> **行号修正(18处)**：§1.1 表 2 处（context_tracker L72→L73、foreshadowing_analyzer 853→852 行）；§1.2 表 2 处（json_backend L149→L157、volume_manager search_content L185→L190）；任务正文 2 处（1.7 L72→L73、2.3 L149→L157）；Phase 4 前置依赖 1 处（get() L2855→L2854）；Phase 6 方法表 5 处回退修正（complete L97→L92、achat L175→L176、embed L228→L227、summarize L264→L263、check_relevance L275→L273）——v1.7 子审计误校准导致反向偏移，本次基于 grep 精确行号全部修正；Phase 6 搬迁注释 4 处（chat L118-170→L117-174、achat L193-227→L176-226、encode L186-214→L186-221、encode_batch L216-265→L223-265）；Phase 6.2 api_backend client L170-184→L167-185；base.py L57-66→L54-65  
> **描述修正(3处)**：extract_entities/summarize/check_relevance 的调用链描述从"内部调用 `self.chat()`"修正为"内部调用 `self.complete()` → `self.chat()`"（它们调用 complete() 而非直接调用 chat()）  
> **验证方法变更**：本次审计放弃子代理估算行号，改用 `grep_search` 对每个方法定义做精确终端行号匹配，确保零偏差
> **v1.9 更新**：AI 可执行性修复（4 个并行子代理交叉验证 + grep 精确确认）—  
> **CRITICAL 修复(4)**：(1) `_add_single_fast()` 中 `scope.add(memory_id, content, metadata=metadata, embedding=embedding)` → `scope.add(content, metadata={'id': memory_id, **metadata})`（与 engine.add() L1751 的调用方式对齐，scope.add 实际签名为 `(content, metadata)`）；(2) `_add_single_fast()` 中 `entities = self.smart_extractor.extract(content)` → `result = self.smart_extractor.extract(content); entities = result.entities`（extract() 返回 ExtractionResult dataclass，含 .entities/.relations/.keywords 属性）；(3) MCP `recall_add` 中 `result.memory_id` → `result.id`（AddResult dataclass 字段名为 `id`，非 `memory_id`）；(4) MCP `recall_list` 中 `m['id']` → `m.get('metadata', {}).get('id', 'N/A')`（memory dict 格式为 `{'content': ..., 'metadata': {'id': ..., ...}, 'timestamp': ...}`，id 在 metadata 内）  
> **行号修正(3处)**：§1.1 表 1 处（knowledge_graph RELATION_TYPES L31-57→L30-57，`RELATION_TYPES = {` 在 L30）；§1.2 表 2 处（volume_manager get_turn_by_memory_id L142-188→L142-183，volume_manager search_content L190-253→L185-245——v1.8 误将 L185 校为 L190，本次 grep 确认实际为 L185，此处回退）  
> **AI 可执行性增强(4处)**：(1) 新增 PromptManager 注入路径说明（engine.py 创建实例 → 传入各 processor → processor __init__ 可选参数）；(2) 新增 4 个待建 engine 方法（list_entities/traverse_graph/list_memories/get_entity_detail）的完整伪代码实现；(3) 任务 7.2 从一行代码扩展为完整的 _l9_rerank 接口适配方案（内置模式保留原始逻辑+entities/keywords 加分，外部模式走新 reranker 接口）；(4) 任务 1.5 RELATION_TYPES 行号校正  
> **验证报告**：Phase 1-3 31 项检查（25 PASS + 2 ⚠️ + 4 修复）；Phase 4-7 39 项检查（37 PASS + 2 ⚠️微偏不影响实施）；配置统一 7 项全部通过；AI 可执行性 5 CRITICAL（已全部修复）+ 6 MEDIUM（4 已修复，2 为设计级注意事项）
> **v1.10 更新**：深度伪代码交叉验证（3 个并行子代理 + 方法签名精确确认）—  
> **CRITICAL 修复(8)**：(1) Phase 3 `_add_single_fast()` 中 `_vector_index.add_with_embedding(memory_id, embedding)` → `_vector_index.add(memory_id, embedding)`（VectorIndex 无 `add_with_embedding` 方法，实际方法为 `add(doc_id, embedding)` at vector_index.py L262）；(2) Phase 3 `add_batch()` 中 `all_entities` 永远为空列表导致实体索引批更新失效 → 改为 `_add_single_fast` 返回 `(memory_id, entities, keywords)` 元组，外层正确累积；(3) Phase 3 `_add_single_fast()` 中 `skip_llm=True` 未实际强制规则模式 → 新增 `force_mode=ExtractionMode.RULES` 调用（SmartExtractor.extract() 支持 `force_mode` 参数）；(4) Phase 3 `add_batch()` 缺少 `self.embedding_backend` 空值防护 → 新增 RuntimeError 检查；(5) Phase 4 MCP `recall_search`/`recall_search_filtered` 的 `getattr(r, "source", "")` 过滤永假 → 改为 `r.metadata.get("source", "")`（SearchResult 无 source/tags 字段，需从 metadata 字典获取）；(6) Phase 4 `traverse_graph()` 中 `self.knowledge_graph.get_edges_for_node()` 不存在 → 改为 `get_relations_for_entity()`（返回 LegacyRelation，属性为 `.source_id`/`.target_id`/`.relation_type`）；(7) Phase 4 `list_entities()` 中 `self._entity_index.get_all_entities(user_id)` 不存在 → 改为 `self._entity_index.all_entities()`（返回 List[IndexedEntity]，不接受 user_id）；(8) Phase 2 `query_after` 中列表名 `_sorted_fact`/`_sorted_system` 与实际不匹配 → 改为 `_sorted_by_fact_start`/`_sorted_by_system_start`  
> **行号验证**：55/63 精确匹配 PASS，7 项 off-by-1（均为文件末尾换行差异），1 项 engine.py L2077 为 `def add_turn(` 而非 character_id（character_id 参数在 L2082，属上下文正确但不精确）  
> **配置统一扩展**：任务 1.11.4 从 15 处差异扩展为 17 处（新增 #16 server.py LLM Max Tokens 各条注释措辞差异、#17 start.sh IVF-HNSW 单参数注释格式差异）  
> **AI 可执行性修复(5)**：(1) `recall/mcp/tools.py` 补充 `import json`；(2) `recall/retrieval/reranker.py` 补充 `import os` 和类型导入；(3) `recall/prompts/manager.py` 补充 `import os`；(4) Phase 2 `query_before` 补充 `_sorted_by_fact_end`/`_sorted_by_system_end` 的完整初始化和维护伪代码（原仅注释说明无代码）；(5) Phase 4 `get_entity_detail()` 修正 `get_entity(entity_name, user_id)` → `get_entity(entity_name)`（EntityIndex.get_entity 不接受 user_id）  
> **验证清单扩展**：12.2 新增 2 项（query_before 新列表初始化、query_after 列表名）；12.3 新增 3 项（embedding_backend 空值、skip_llm 规则模式、_add_single_fast 返回值）；12.4 新增 3 项（metadata.get 过滤、all_entities 方法、get_relations_for_entity 方法）；12.9 新增 1 项（#16/#17 新差异）  
> **任务 1.10 措辞修正**："所有 7 处位置必须使用此精确文本" → 明确区分 5 处配置模板（精确文本）+ 2 处仅需同步变量名
> **v1.11 更新**：完整性终审（4 个并行子代理交叉验证 — 源码行号+签名验证 76/77 PASS、伪代码逻辑深度审查 6C+12M+5L、配置模板一致性 17 CONFIRMED+1 NEW、AI 可执行性 7B+15I+10N）—  
> **CRITICAL 修复(3)**：(1) `_batch_update_indexes` 中 `entity_index.add(name, mid)` → `add_entity_occurrence(name, mid)`（EntityIndex 无公开 `add(str,str)` 方法，实际为 `add_entity_occurrence()` at L114）；(2) `_batch_update_indexes` 中 ngram_index 仅调用 `save()` 从未添加数据 → 新增 `add_ngrams(kw, mid)` 调用；(3) `_batch_update_indexes` 直接操作 `_inverted_index.index[kw].add()` + 私有 `_save()` → 改用公开 `add_batch()` API（兼容 Phase 2 WAL）  
> **BLOCKING 修复(6)**：(1) `recall/mcp/__init__.py` 新增完整内容规范（exports: register_tools, register_resources, create_sse_app）；(2) `recall/prompts/__init__.py` 新增完整内容规范；(3) `recall/config.py` 改动从"~5行无说明"明确为 `from .mode import RecallMode, get_mode_config` 再导出；(4) MetadataIndex 补充完整 `_save()`/`_load()`/`flush()` 实现含 dirty_count 批量优化；(5) Task 3.4 扩展为完整 MetadataIndex 集成路径（engine.py init → add/add_batch write → search post-filter with oversampling）；(6) 版本号更新任务新增（recall/version.py + pyproject.toml 从 4.2.0 → 5.0.0）  
> **伪代码逻辑修复(9)**：(1) MCP `recall_delete` 新增 `engine.delete()` 布尔返回值检查；(2) MCP Resources URI 路径新增 `urllib.parse.unquote()` 解码；(3) `traverse_graph` BFS 从 `list.pop(0)` → `deque.popleft()`；(4) Anthropic `system=""` 边界处理 `strip() or None`、`stop_sequences=None` 条件传参；(5) Gemini system 消息提取为 `system_instruction` 参数；(6) RerankerFactory 未知 backend 新增 warning 日志；(7) `_unindex_entry()` 补充 `_sorted_by_fact_end`/`_sorted_by_system_end` 移除逻辑；(8) json_backend 新增 `atexit.register(self.flush)` 可靠性建议；(9) PromptManager 环境变量从 `RECALL_DATA_PATH` → `RECALL_DATA_ROOT`、docstring 从 Jinja2 → str.format()  
> **AI 可执行性增强(6)**：(1) `ModeConfig.from_env()` 新增无效 RECALL_MODE 值的 warning 日志；(2) mcp_server.py 入口拆分为 `_async_main()`(async) + `main()`(sync wrapper)，pyproject.toml 指向同步入口；(3) pyproject.toml MCP 可选依赖合并统一（SSE deps 消除重复）；(4) engine.py 顶层 foreshadowing 无条件导入标注为"需删除，改为条件导入"；(5) Turn model 下游影响文档化（effective_content 使用指南）；(6) 模式切换数据一致性说明（需重启、数据物理共存）  
> **依赖修复(1)**：`pyyaml>=6.0` 标注为必须添加到 pyproject.toml 核心依赖（PromptManager `import yaml`）  
> **配置模板修复(1)**：#10 扩展为 4 方变体（manage.ps1/manage.sh 原完全缺失"时态知识图谱配置"子标题）  
> **验证清单扩展**：12.1 新增 4 项（无效 RECALL_MODE / foreshadowing 条件导入 / effective_content / 模式切换重启）；12.2 新增 2 项（atexit / _unindex_entry 移除）；12.3 新增 1 项（公开 API 使用）；12.4 新增 4 项（deque / recall_delete / URI decode / 同步入口）；12.5 新增 3 项（RECALL_DATA_ROOT / str.format / pyyaml）；12.6 新增 4 项（Anthropic system / stop_sequences / Gemini system_instruction / RerankerFactory warning）；12.9 新增 1 项（manage 时态子标题）；新增 12.10 版本与依赖验证（6 项）  
> **改动清单更新**：10.2 表新增 `recall/version.py`（1行）；新增 §10.2.1 版本号更新说明；新增 §10.2.2 config.py 改动说明；10.3 零影响保证新增"模式切换安全"条目；总改动量从 ~810 行更新为 ~815 行
> **v1.12 更新**：伪代码终极校准（4 个并行子代理交叉验证 — 源码方法签名 16 PASS/3 WARN/1 FAIL、伪代码逻辑 3C+6M+7L、配置模板 5/5 CONFIRMED、AI 可执行性 6 ISSUE）—  
> **CRITICAL 修复(4)**：(1) `_batch_update_indexes` 中 `ngram_index.add_ngrams(kw, mid)` → `ngram_index.add(mid, content)`（`OptimizedNgramIndex` 无 `add_ngrams()` 方法，实际为 `add(turn, content)` at L73，接收 memory_id+完整原文，内部自动提取名词短语。参数语义完全不同会导致 AttributeError 崩溃）；(2) WAL 重放 `json.loads(line)` 无异常保护 → 新增 `try/except json.JSONDecodeError` 跳过损坏行（崩溃后不完整行导致全量 _load 失败）；(3) PromptManager `render()` variant=None 时 `.format()` 抛 AttributeError → 新增 `if variant is None: raise ValueError(...)` 明确报错；(4) `_achat_google` 未提取 system_instruction（直接映射 system→user），与同步版不一致 → 对齐完整 system_instruction 提取  
> **MEDIUM 修复(7)**：(1) `query_before`/`query_after` time_type else 兜底 → 显式 if/elif/raise ValueError；(2) `_compact()` 写主文件非原子 → 先写 `.tmp` 后 `os.replace()`；(3) `_add_single_fast` `**metadata` None crash → `**(metadata or {})`；(4) MetadataIndex 缺 atexit → `__init__` 注册 `atexit.register(self.flush)`；(5) PromptManager KeyError → 显式检查+ValueError；(6) `_load_templates` 目录不存在 → `os.path.exists()` 保护；(7) `_achat_anthropic` 缺 stop 转发 → 签名加 `stop=None` + achat 路由透传  
> **数据流修复(1)**：`_batch_update_indexes` 签名从 `(all_keywords, all_entities)` → `(all_keywords, all_entities, all_ngram_data)`，add_batch 新增收集 `(memory_id, content)` 对  
> **验证清单扩展(11项)**：12.2+2（WAL crash 保护 + compact 原子写入）；12.3+3（MetadataIndex atexit + metadata=None + ngram API 修正）；12.5+3（render ValueError + template KeyError + builtin_dir）；12.6+3（_achat_google + _achat_anthropic stop + achat 路由）  
> **配置模板验证**：5 项全部 CONFIRMED（start.ps1/sh 5/17 抽检真实、manage.ps1 英文 UI + 时态子标题缺失、server.py 126 键、engine.py 3 默认值 'false'、9 新变量不存在）
