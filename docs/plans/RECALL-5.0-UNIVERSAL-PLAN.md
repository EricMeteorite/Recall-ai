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
8. [Phase 6：多 LLM 提供商支持](#八phase-6多-llm-提供商支持)
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
| 2 | `storage/layer0_core.py` | L77-83 | `get_injection_text()` 硬编码 `roleplay/coding` 双分支 | 中 |
| 3 | `graph/knowledge_graph.py` | L28-56 | `RELATION_TYPES` — 20 种关系全部 RP 倾向，注释写 "针对 RP 场景优化" | 中 |
| 4 | `processor/consistency.py` | L56-75 | `AttributeType` 枚举 — 15 种属性中 11 种 RP 特化（HAIR_COLOR/SPECIES 等） | 中 |
| 5 | `processor/consistency.py` | L142-200 | `COLOR_SYNONYMS`, `RELATIONSHIP_OPPOSITES`, `STATE_OPPOSITES` 纯 RP 词典 | 中 |
| 6 | `processor/context_tracker.py` | L68-73 | `ContextType` 枚举 — 6/15 种为 RP 特化（CHARACTER_TRAIT/WORLD_SETTING 等） | 低 |
| 7 | `processor/foreshadowing.py` | 全文 1235 行 | 伏笔追踪器 — 纯 RP 叙事功能 | **高** |
| 8 | `processor/foreshadowing_analyzer.py` | 全文 853 行 | 伏笔 LLM 分析器 — 纯 RP | **高** |
| 9 | `engine.py` | L287-298 | 初始化 `foreshadowing_tracker/analyzer` | 高 |
| 10 | `engine.py` | L3278-3285 | `build_context()` 第 5 层硬注入活跃伏笔 | 高 |
| 11 | `engine.py` | L1304/2084/3175 | `character_id` 作为参数贯穿 `add()/add_turn()/build_context()` | 中 |
| 12 | `server.py` | 16 个端点 | `/v1/foreshadowing/*` — 全部伏笔 API | 高 |
| 13 | `server.py` | 20+ 处 | `character_id` 参数贯穿几乎所有端点 | 中 |
| 14 | `storage/multi_tenant.py` | L16-19 | `character_id` 作为存储路径第二级维度 | 中 |
| 15 | `models/base.py` | L17-27 | `EventType.ITEM_TRANSFER/FORESHADOWING/PLOT_POINT` + `ForeshadowingStatus` 枚举 | 低 |
| 16 | `models/foreshadowing.py` | 全文 | 纯 RP 伏笔数据模型 | 低 |
| 17 | `models/temporal.py` | L48 | `NodeType.FORESHADOWING` | 低 |
| 18 | `processor/scenario.py` | L44-56 | RP 关键词/正则硬编码检测 | 低 |
| 19 | `processor/scenario.py` | L92 | `ROLEPLAY → entity_focused` 策略硬绑定 | 低 |

### 1.2 性能瓶颈清单

| # | 文件 | 行号 | 问题 | 严重度 |
|---|------|------|------|:------:|
| 1 | `index/temporal_index.py` | L296-338 | `query_at_time()` / `query_range()` — O(n) 全扫描，不用已有的排序列表 | **高** |
| 2 | `index/temporal_index.py` | L439/L463 | `query_before()` / `query_after()` — 同样 O(n) | 高 |
| 3 | `index/inverted_index.py` | L30-33 | `_save()` — 每次全量 JSON dump 整个索引 | **高** |
| 4 | `graph/backends/json_backend.py` | L133-136 | `add_node()` — 每次写操作触发全量 `_save()` | **高** |
| 5 | `storage/volume_manager.py` | L142-183 | `get_turn_by_memory_id()` — O(全磁盘) 逐行扫描 | 中 |
| 6 | `storage/volume_manager.py` | L185-230 | `search_content()` — O(全磁盘) 逐行扫描 | 中 |
| 7 | `index/ngram_index.py` | L151-178 | `_raw_text_fallback_search()` — O(n) 全内存扫描 | 中 |
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
| 7 | LLM 仅支持 OpenAI 兼容 API | 不支持 Anthropic/Gemini 原生 SDK |
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

> **目标**：通过配置开关让 Recall 能在 RP/通用/知识库 三种模式间切换，不删不改一行现有逻辑。  
> **预计工作量**：3-4 天

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
**改动行号**：L21-29, L287-298, L1304, L3278-3285

| 改动 | 原代码 | 新代码 | 行为变化 |
|------|--------|--------|----------|
| 导入 | 无条件导入 foreshadowing | 条件导入 | 通用模式不导入 |
| 初始化 | 无条件创建 tracker/analyzer | `if mode.foreshadowing_enabled:` | 通用模式跳过 |
| `add()` | `character_id` 固定使用 | `if mode.character_dimension_enabled:` 使用，否则忽略 | 通用模式不隔离角色 |
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
**改动行号**：L77-83

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
**改动行号**：L28-56

**改动方式**：保留现有 20 种 RP 关系，新增通用关系类型，根据模式合并：

```python
# 原有 RP 关系（完全保留）
RP_RELATION_TYPES = {
    'IS_FRIEND_OF': '是朋友',
    'IS_ENEMY_OF': '是敌人',
    # ... 原有 20 种不变 ...
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
            self._check_character_attributes(...)
            self._check_relationship_consistency(...)
            self._check_state_consistency(...)
        
        # 通用检测（数值矛盾、时间线）始终启用
        self._check_numerical_contradictions(...)
        self._check_timeline_consistency(...)
```

**效果**：通用模式下跳过发色/物种/生死等 RP 属性检测，保留数值矛盾和时间线检测。

---

### 任务 1.7：持久条件类型过滤

**改动文件**：`recall/processor/context_tracker.py`  
**改动行号**：L55-78 枚举定义处

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

---

### 任务 1.9：ScenarioDetector 通用场景支持

**改动文件**：`recall/processor/scenario.py`  
**改动行号**：L91-99

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

---

## 四、Phase 2：性能瓶颈修复

> **目标**：修复所有 O(n) 查询和全量序列化问题，使 Recall 能够处理百万级数据。  
> **预计工作量**：4-5 天

### 任务 2.1：时态索引利用排序列表实现 O(log n) 查询

**改动文件**：`recall/index/temporal_index.py`  
**改动行号**：L296-338, L439-487

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

**query_before / query_after 同理改用 bisect**。

---

### 任务 2.2：倒排索引改增量持久化

**改动文件**：`recall/index/inverted_index.py`  
**改动行号**：L30-33

**方案**：将 `_save()` 从全量 JSON dump 改为增量 JSONL append + 定期压缩：

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
        self._save_full()
        if os.path.exists(self._wal_file):
            os.remove(self._wal_file)
        self._wal_count = 0
    
    def _save_full(self):
        """全量保存（仅压缩时调用）"""
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
                    entry = json.loads(line)
                    self.index[entry['k']].add(entry['t'])
                    self._wal_count += 1
```

---

### 任务 2.3：JSON 图后端改延迟保存

**改动文件**：`recall/graph/backends/json_backend.py`  
**改动行号**：L133-136

**方案**：将每次操作的全量 `_save()` 改为脏标记 + 延迟批量保存：

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
    
    # 1. 批量计算 embedding
    contents = [item['content'] for item in items]
    embeddings = self.embedding_backend.embed_batch(contents)  # 单次 API
    
    # 2. 逐条处理但合并 IO
    all_keywords = []
    all_entities = []
    
    for item, embedding in zip(items, embeddings):
        memory_id = self._add_single_fast(
            content=item['content'],
            embedding=embedding,
            metadata=item.get('metadata', {}),
            user_id=user_id,
            skip_dedup=skip_dedup,
            skip_llm=skip_llm,
        )
        if memory_id:
            memory_ids.append(memory_id)
            all_keywords.extend([(kw, memory_id) for kw in item.get('keywords', [])])
    
    # 3. 批量更新索引（一次 IO）
    self._batch_update_indexes(all_keywords, all_entities)
    
    return memory_ids
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

class MetadataIndex:
    """元数据倒排索引"""
    
    def __init__(self, data_path):
        self.data_path = data_path
        # 多字段倒排索引
        self._by_source: Dict[str, Set[str]] = defaultdict(set)     # source → memory_ids
        self._by_tag: Dict[str, Set[str]] = defaultdict(set)        # tag → memory_ids
        self._by_category: Dict[str, Set[str]] = defaultdict(set)   # category → memory_ids
        self._by_content_type: Dict[str, Set[str]] = defaultdict(set)
        self._load()
    
    def add(self, memory_id, source="", tags=None, category="", content_type=""):
        if source:
            self._by_source[source].add(memory_id)
        for tag in (tags or []):
            self._by_tag[tag].add(memory_id)
        if category:
            self._by_category[category].add(memory_id)
        if content_type:
            self._by_content_type[content_type].add(memory_id)
    
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
```

### 任务 3.4：检索系统集成元数据过滤

**改动文件**：`recall/retrieval/eleven_layer.py`, `recall/engine.py`

在 `search()` 方法中新增可选的元数据过滤参数：

```python
def search(self, query, user_id="default", top_k=10,
           source=None, tags=None, category=None, content_type=None):
    """搜索记忆 — 支持元数据过滤"""
    # 1. 如果有元数据过滤条件，先缩小候选集
    if any([source, tags, category, content_type]):
        allowed_ids = self.metadata_index.query(
            source=source, tags=tags, category=category, content_type=content_type
        )
        # 在后续检索中只考虑 allowed_ids 内的结果
    
    # 2. 原有 11 层检索逻辑不变，最后用 allowed_ids 过滤
```

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
- SSE（远程部署）
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, Resource, TextContent

app = Server("recall-memory")

# ... 注册 tools/resources ...

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
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
| `recall_stats` | GET /v1/admin/stats | 统计信息 |
| `recall_entities` | GET /v1/entities | 实体列表 |
| `recall_graph_query` | POST /v1/graph/query | 图谱查询 |
| `recall_add_batch` | POST /v1/memories/batch | 批量添加（v5.0） |
| `recall_search_filtered` | GET /v1/memories/search?source=... | 过滤搜索（v5.0） |

### 任务 4.3：MCP Resources 实现

**新建文件**：`recall/mcp/resources.py`

```python
# recall:// URI 方案
# recall://memories          → 所有记忆
# recall://memories/{id}     → 单条记忆
# recall://entities          → 所有实体
# recall://entities/{name}   → 单个实体详情
# recall://graph/{entity}    → 实体关系图
# recall://stats             → 统计信息
```

### 任务 4.4：MCP Transport — SSE 支持

**新建文件**：`recall/mcp/transport.py`

支持远程部署的 Server-Sent Events 传输。

### 任务 4.5：新增依赖与入口点

**改动文件**：`pyproject.toml`

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0.0", "httpx-sse>=0.4.0"]

[project.scripts]
recall-mcp = "recall.mcp_server:main"
```

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
| `recall/prompts/__init__.py` | 导出 PromptManager |
| `recall/prompts/manager.py` | PromptManager 类 — 加载/缓存/渲染 prompt 模板 |
| `recall/prompts/templates/` | YAML/Jinja2 模板目录 |
| `recall/prompts/templates/entity_extraction.yaml` | 实体抽取 prompt |
| `recall/prompts/templates/relation_extraction.yaml` | 关系抽取 prompt |
| `recall/prompts/templates/contradiction_detection.yaml` | 矛盾检测 prompt |
| `recall/prompts/templates/foreshadowing_analysis.yaml` | 伏笔分析 prompt |
| `recall/prompts/templates/context_extraction.yaml` | 持久条件抽取 prompt |
| `recall/prompts/templates/entity_summary.yaml` | 实体摘要 prompt |
| `recall/prompts/templates/unified_analysis.yaml` | 统一分析 prompt |

### 任务 5.2：PromptManager 实现

```python
class PromptManager:
    """Prompt 模板管理器
    
    支持：
    1. YAML 模板定义 + Jinja2 变量渲染
    2. 多语言支持（zh/en）
    3. 模式感知（RP/通用/知识库模式不同 prompt）
    4. 用户自定义覆盖（在 recall_data/prompts/ 中放同名文件）
    """
    
    def __init__(self, mode: RecallMode):
        self.mode = mode
        self._templates = {}
        self._load_templates()
    
    def render(self, template_name: str, **kwargs) -> str:
        """渲染 prompt 模板"""
        template = self._templates[template_name]
        # 选择模式对应的变体
        variant = template.get(self.mode.value, template.get('default'))
        return variant.format(**kwargs)
```

### 任务 5.3：迁移现有硬编码 Prompt

**改动文件清单**：

| 文件 | 当前硬编码位置 | 迁移到 |
|------|--------------|--------|
| `processor/smart_extractor.py` | 内联 prompt 字符串 | `templates/entity_extraction.yaml` |
| `graph/llm_relation_extractor.py` | 内联 prompt | `templates/relation_extraction.yaml` |
| `processor/consistency.py` | LLM 检测 prompt | `templates/contradiction_detection.yaml` |
| `processor/foreshadowing_analyzer.py` | 分析 prompt | `templates/foreshadowing_analysis.yaml` |
| `processor/context_tracker.py` | 提取 prompt | `templates/context_extraction.yaml` |
| `processor/entity_summarizer.py` | 摘要 prompt | `templates/entity_summary.yaml` |
| `processor/unified_analyzer.py` | 统一分析 prompt | `templates/unified_analysis.yaml` |

**改动方式**：每个文件只需改一行——将硬编码字符串替换为 `self.prompt_manager.render('template_name', ...)`。原字符串成为 YAML 模板中的 `default` 变体。

---

## 八、Phase 6：多 LLM 提供商支持

> **目标**：支持 Anthropic、Google Gemini 的原生 SDK 调用。  
> **预计工作量**：2-3 天

### 任务 6.1：LLMClient 重构为多后端

**改动文件**：`recall/utils/llm_client.py`

**方案**：在现有 OpenAI 后端基础上，新增 Anthropic 和 Gemini 后端：

```python
class LLMClient:
    def __init__(self, model="gpt-4o-mini", api_key=None, api_base=None, 
                 provider=None, ...):  # 新增 provider 参数
        self.provider = provider or self._detect_provider(model)
        # ...
    
    def _detect_provider(self, model):
        """根据模型名自动检测提供商"""
        if model.startswith('claude'):
            return 'anthropic'
        elif model.startswith('gemini'):
            return 'google'
        else:
            return 'openai'  # 兼容所有 OpenAI API
    
    def chat(self, messages, ...):
        if self.provider == 'anthropic':
            return self._chat_anthropic(messages, ...)
        elif self.provider == 'google':
            return self._chat_google(messages, ...)
        else:
            return self._chat_openai(messages, ...)  # 原逻辑
    
    def _chat_anthropic(self, messages, ...):
        """Anthropic Claude 原生 SDK"""
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
            )
            return LLMResponse(content=response.content[0].text, ...)
        except ImportError:
            raise ImportError("anthropic 未安装。请运行: pip install anthropic")
    
    def _chat_google(self, messages, ...):
        """Google Gemini 原生 SDK"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(...)
            return LLMResponse(content=response.text, ...)
        except ImportError:
            raise ImportError("google-generativeai 未安装。请运行: pip install google-generativeai")
```

### 任务 6.2：新增依赖（可选）

**改动文件**：`pyproject.toml`

```toml
[project.optional-dependencies]
anthropic = ["anthropic>=0.30.0"]
google = ["google-generativeai>=0.8.0"]
all-llm = ["anthropic>=0.30.0", "google-generativeai>=0.8.0"]
```

### 任务 6.3：新增配置项

**改动文件**：`recall/server.py` SUPPORTED_CONFIG_KEYS

```python
'LLM_PROVIDER',        # openai / anthropic / google / auto
'ANTHROPIC_API_KEY',    # Anthropic 专用 key
'GOOGLE_API_KEY',       # Google 专用 key
```

---

## 九、Phase 7：重排序器多样性

> **目标**：支持 Cohere Rerank 和自定义模型重排序。  
> **预计工作量**：1-2 天

### 任务 7.1：重排序器抽象层

**新建文件**：`recall/retrieval/reranker.py`

```python
"""重排序器 — 可插拔的重排序后端"""

class RerankerBase:
    """重排序器基类"""
    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        raise NotImplementedError

class BuiltinReranker(RerankerBase):
    """内置重排序器（当前行为，多因素加权）"""
    # 原有逻辑搬迁

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
            return BuiltinReranker()
```

### 任务 7.2：集成到 11 层检索

**改动文件**：`recall/retrieval/eleven_layer.py`

在 L9 (Rerank) 和 L10 (Cross-Encoder) 层替换为可插拔的重排序器：

```python
# eleven_layer.py
self.reranker = RerankerFactory.create(
    os.getenv('RERANKER_BACKEND', 'builtin')
)
```

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
| 1 | `recall/processor/consistency.py` | ~15 行 | 低 |
| 1 | `recall/processor/context_tracker.py` | ~10 行 | 低 |
| 1 | `recall/processor/scenario.py` | ~10 行 | 低 |
| 1 | `recall/models/turn.py` | ~15 行 | 低（新增字段，向后兼容） |
| 1 | `recall/config.py` | ~5 行 | 极低 |
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
| 6 | `recall/utils/llm_client.py` | ~80 行 | 低（新增方法） |
| 7 | `recall/retrieval/eleven_layer.py` | ~10 行 | 低 |
| — | `pyproject.toml` | ~15 行 | 极低 |

**共改动 ~23 个现有文件，总改动量约 ~550 行**

### 10.3 零影响保证

| 保证项 | 机制 |
|--------|------|
| RP 模式不受影响 | `RECALL_MODE` 默认值 `roleplay` → 所有行为与 v4.2 完全一致 |
| 现有 API 不破坏 | 所有新 API 是追加的，原端点不修改签名 |
| 现有数据不迁移 | Turn 模型新增字段都有默认值，旧数据自动兼容 |
| 现有配置不失效 | 所有新增环境变量都有默认值 |
| 伏笔功能完整保留 | 只在通用模式下跳过伏笔注入，RP 模式完全不变 |
| 原有测试全部通过 | 测试默认走 RP 模式，不受新代码影响 |

---

## 十一、实施顺序与时间估算

```
┌──────────────────────────────────────────────────────────────┐
│                    实施路线图                                 │
├──────┬───────────────┬──────────┬───────────────────────────┤
│ 阶段 │ 内容          │ 工期     │ 依赖                      │
├──────┼───────────────┼──────────┼───────────────────────────┤
│ P1   │ 核心通用化     │ 3-4 天  │ 无（第一步必须做）        │
│ P2   │ 性能瓶颈修复   │ 4-5 天  │ 无（可与 P1 并行）        │
│ P3   │ 批量写入+元数据 │ 3-4 天  │ 依赖 P1（Turn 模型）+P2  │
│ P4   │ MCP Server    │ 3-4 天  │ 依赖 P1 + P3（批量 API）  │
│ P5   │ Prompt 工程    │ 2-3 天  │ 依赖 P1（模式感知）       │
│ P6   │ 多 LLM 支持    │ 2-3 天  │ 无（独立模块）            │
│ P7   │ 重排序器       │ 1-2 天  │ 无（独立模块）            │
├──────┼───────────────┼──────────┼───────────────────────────┤
│ 总计 │               │ 18-25 天 │                           │
└──────┴───────────────┴──────────┴───────────────────────────┘
```

### 推荐实施顺序

```
第 1 周：P1（通用化）+ P2（性能）并行推进
第 2 周：P3（批量写入）→ P6（多 LLM）
第 3 周：P4（MCP Server）→ P5（Prompt）→ P7（重排序）
第 4 周：集成测试 + 文档更新 + FEATURE-STATUS.md 更新
```

---

## 十二、验证检查清单

### 12.1 Phase 1 验证

- [ ] `RECALL_MODE` 不设置 → 所有现有测试通过（RP 行为不变）
- [ ] `RECALL_MODE=general` → 伏笔 API 返回禁用提示，不注入伏笔
- [ ] `RECALL_MODE=general` → character_id 被忽略，数据不按角色隔离
- [ ] `RECALL_MODE=general` → 一致性检查跳过 HAIR_COLOR/SPECIES 等
- [ ] `RECALL_MODE=general` → 图谱关系类型包含通用类型
- [ ] `RECALL_MODE=general` + `FORESHADOWING_ENABLED=true` → 伏笔功能正常
- [ ] Turn 模型新增字段不影响现有数据加载
- [ ] `/v1/mode` 端点返回正确的模式信息

### 12.2 Phase 2 验证

- [ ] temporal_index `query_at_time()` 结果与旧实现一致（正确性）
- [ ] temporal_index `query_range()` 结果与旧实现一致
- [ ] 10 万条数据下 temporal_index 查询 < 10ms（性能）
- [ ] inverted_index WAL 追加写入正常，重启后 WAL 重放正确
- [ ] inverted_index 压缩后主文件与内存状态一致
- [ ] json_backend 延迟保存不丢数据，`flush()` 后全部持久化
- [ ] volume_manager memory_id 索引 O(1) 查找正确

### 12.3 Phase 3 验证

- [ ] `POST /v1/memories/batch` 批量添加 100 条 < 30 秒
- [ ] 批量添加后所有索引（倒排/向量/实体/元数据）正确更新
- [ ] `search(source="bilibili")` 只返回来源为 bilibili 的记忆
- [ ] `search(tags=["热点"])` 过滤正确

### 12.4 Phase 4 验证

- [ ] MCP Server stdio 模式正常启动
- [ ] Claude Desktop 通过 MCP 调用 `recall_add` 成功
- [ ] Claude Desktop 通过 MCP 调用 `recall_search` 成功
- [ ] MCP Resources `recall://memories` 返回正确
- [ ] `recall-mcp` 命令行入口可用

### 12.5 Phase 5 验证

- [ ] PromptManager 加载所有 YAML 模板无错误
- [ ] 各模块使用 PromptManager 渲染的 prompt 与原硬编码结果一致
- [ ] 用户自定义 prompt 覆盖正常工作

### 12.6 Phase 6 验证

- [ ] `LLM_MODEL=claude-3-5-sonnet` 自动检测 Anthropic 并正常调用
- [ ] `LLM_MODEL=gemini-pro` 自动检测 Google 并正常调用
- [ ] 未安装 `anthropic` 时使用 Claude 模型给出清晰错误提示
- [ ] OpenAI 兼容 API 行为完全不变

### 12.7 Phase 7 验证

- [ ] `RERANKER_BACKEND=builtin` → 行为与现在完全一致
- [ ] `RERANKER_BACKEND=cohere` → 使用 Cohere Rerank API
- [ ] `RERANKER_BACKEND=cross-encoder` → 使用本地 Cross-Encoder 模型

### 12.8 全局回归验证

- [ ] **所有 18 个现有测试文件通过**
- [ ] RP 模式下 SillyTavern 插件功能完整（伏笔/角色/一致性检查）
- [ ] 通用模式下爬虫数据批量写入 + 元数据过滤正常
- [ ] 知识库模式下纯知识管理正常（无 RP 功能干扰）

---

> **本文档版本**：v1.0  
> **状态**：待审批  
> **下一步**：确认计划后，按 Phase 顺序逐步实施
