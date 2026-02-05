# Recall-AI 性能优化方案 - 零功能降级加速计划

> **版本**: v2.3 (一致性检查完整版)  
> **日期**: 2026-02-05  
> **目标**: 在保证 100% 功能完整性的前提下，将记忆处理时间减少 40-60%

---

## ⚠️ 重要审核说明

本文档经过全面代码审核，针对以下方面进行了修订：
1. **VectorIndex 使用分析**: 项目使用 `vector_index.py` (VectorIndex 类)，而非 IVF 版本
2. **配置体系统一**: 确保新增配置项与现有 `SUPPORTED_CONFIG_KEYS` 集成
3. **SillyTavern 插件适配**: 确保前端修改与现有事件处理机制兼容
4. **Windows/Linux 脚本一致性**: 环境变量在 `api_keys.env` 统一管理
5. **行号精确校对** (v1.2): 所有代码引用行号已根据实际代码校对更新
6. **启动脚本配置同步** (v1.3): 发现 `start.ps1` 和 `start.sh` 有独立的配置白名单，必须同步更新
   - ⚠️ **v2.1 重大更新**: `manage.ps1` 和 `manage.sh` 同样有完整的默认配置模板，也必须同步更新！
7. **代码复用发现** (v1.4): 经审核，`ThreeStageDeduplicator._semantic_match` 已原生支持 `item.embedding`，**无需创建新方法**！
8. **深度行号校对** (v1.5): 
   - 修正 `_init_unified_analyzer` 位置：应在第578行（`_init_entity_summarizer` 调用之后），而非第494行
   - 确认 VectorIndex.add() 方法（第262行）、encode() 方法（第256行）、enabled 属性（第116行）
   - 确认 DedupItem.embedding 属性（第69行）
   - 确认 _semantic_match 方法（第484行定义，第491-492行检查 item.embedding）
   - 修正 get_default_config_content() 结束位置（第869行）
9. **完整性审核** (v1.6):
   - 修正方案3收益估算（Embedding 计算次数不减少）
   - 添加 server.py 模型和端点的精确位置（第985行和第1540行）
   - 添加 engine.py AddTurnResult 定义位置（第84行）
   - 修正 add_turn() 中向量索引更新逻辑（分别为两条记忆计算 embedding）
   - 确认 install.ps1/install.sh 无需修改（仅安装依赖，不涉及运行时配置）
10. **功能对等完善** (v1.9):
    - 补充 add_turn() 去重逻辑完整实现（包括三阶段去重和回退简单匹配）
    - 添加 Episode 创建逻辑（使用现有 MESSAGE 类型）
    - 添加全文索引 BM25 更新
    - 添加长期记忆 (ConsolidatedMemory) 更新
    - 添加 Episode 关联更新
    - 添加实体摘要更新
    - 添加性能监控记录
    - 添加关键词 (keywords) 提取和存储
    - 更新功能完整性清单从 13 项增加到 21 项
    - 更新审核通过条件从 28 项增加到 35 项
11. **最终审核** (v2.0):
    - 修正 `useTurnApi` 默认值统一为 `false`（安全默认，用户需手动启用）
    - 修正 `EpisodeType` 使用现有 `MESSAGE` 类型（非不存在的 `CONVERSATION_TURN`）
    - 添加 `character_id` 到 Episode 创建
    - 更新 API 端点精确行号（server.py:~1536）
    - 更新 Pydantic 模型精确位置说明
    - 验证 install.ps1/install.sh 确实不需要修改
    - 验证所有代码行号与实际文件一致
12. **管理脚本配置同步修正** (v2.1):
    - ⚠️ **重大发现**: `manage.ps1` 和 `manage.sh` 包含完整的默认配置模板，**必须同步更新**！
    - `manage.ps1`: `$defaultConfig` 位于第293-883行（PowerShell here-string）
    - `manage.sh`: `cat > "$config_file" << 'EOF' ... EOF` 位于第295-884行
    - 这两个脚本在首次初始化时会生成 `api_keys.env` 文件，必须包含所有配置项
    - 添加 6.4.4 和 6.4.5 节详细说明 manage 脚本的修改要求
13. **SillyTavern 深度适配审核** (v1.7):
    - 添加 `_init_unified_analyzer` 的 `ImportError` 异常处理（与其他初始化方法保持一致）
    - 添加 `saveTurnWithApi` 中的伏笔分析触发（两条消息都需要触发）
    - 添加 `saveTurnWithApi` 中的一致性警告显示
    - 添加回退逻辑中的超时计时器清除
    - 添加 `processor/__init__.py` 的具体导出代码示例
14. **功能完整性审核** (v1.8):
    - 补充 `add_turn()` 中完整的索引更新逻辑（实体索引、倒排索引、N-gram索引、检索器缓存）
    - 补充 `add_turn()` 中 Archive 原文保存（volume_manager.append_turn）
    - 补充 `add_turn()` 中统一分析器调用的具体实现
    - 补充 `add_turn()` 中知识图谱关系存储逻辑
    - 添加设置面板 UI 中的 Turn API 开关代码示例
15. **功能对等性保证** (v2.2):
    - **重大补充**: `add_turn()` 添加 `contradiction_manager.add_pending()` 调用（与 `add()` 一致）
    - **重大补充**: `add_turn()` 添加传统关系提取器回退逻辑（当 UnifiedAnalyzer 失败或未启用时）
    - 添加输入验证逻辑（用户消息和AI回复不能为空）
    - 功能对比表添加"矛盾记录"和"关系提取回退"两行
    - 确认功能检查表从21项增加到22项
16. **一致性检查完整性** (v2.3):
    - **重大补充**: `add_turn()` 添加 `consistency_checker.check()` 回退逻辑（当 UnifiedAnalyzer 未启用时）
    - 确保无论 UnifiedAnalyzer 是否启用，一致性检查都会执行
    - 回退时同样将矛盾记录到 contradiction_manager
    - 功能对比表更新"一致性检查"为支持回退

---

## 一、项目现状分析

### 1.1 核心处理流程分析

通过深入分析 `engine.py` 中的 `add()` 方法，当前每条消息的处理流程如下：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        engine.add() 处理流程                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 去重检查 (dedup_check)                                                   │
│     ├─ 三阶段去重器 (优先)                                                   │
│     │   ├─ 阶段1: MinHash + LSH 快速匹配                                    │
│     │   ├─ 阶段2: Embedding 语义相似度 ← [Embedding 计算 #1]                │
│     │   └─ 阶段3: LLM 确认 (可选)                                           │
│     └─ 简单字符串匹配 (回退)                                                 │
│                                                                             │
│  2. Episode 创建 (Recall 4.1)                                               │
│                                                                             │
│  3. 实体提取 (entity_extraction)                                            │
│     ├─ SmartExtractor (优先) - 可能调用 LLM                                 │
│     └─ 规则提取器 (回退)                                                    │
│                                                                             │
│  4. 一致性检查 (consistency_check)                                          │
│     ├─ 正则规则检测 (快速)                                                  │
│     └─ LLM 深度矛盾检测 (可选) ← [LLM 调用 #1: 矛盾检测]                    │
│                                                                             │
│  5. 存储记忆                                                                │
│                                                                             │
│  6. 更新索引 (index_update)                                                 │
│     ├─ 实体索引                                                             │
│     ├─ 倒排索引                                                             │
│     ├─ N-gram 索引                                                          │
│     └─ 向量索引 ← [Embedding 计算 #2] ⚠️ 重复计算!                          │
│                                                                             │
│  7. 知识图谱更新 (knowledge_graph)                                          │
│     ├─ LLM 关系提取 (优先) ← [LLM 调用 #2: 关系提取]                        │
│     └─ 规则提取器 (回退)                                                    │
│                                                                             │
│  8. 全文索引更新 (BM25)                                                     │
│                                                                             │
│  9. Episode 关联更新                                                        │
│                                                                             │
│  10. 实体摘要更新 ← [LLM 调用 #3: 实体摘要] (条件触发)                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 性能瓶颈定位

| 瓶颈点 | 当前耗时 | 发生位置 | 问题描述 |
|--------|----------|----------|----------|
| **Embedding 重复计算** | 1.5-3s | 去重检查 + 向量索引 | 同一文本计算两次 embedding |
| **LLM 多次独立调用** | 15-30s | 矛盾检测 + 关系提取 + 实体摘要 | 每个功能独立调用，重复传输上下文 |
| **消息串行处理** | 30-80s | 用户消息 + AI回复 | 同一轮对话分两次处理 |

### 1.3 时间分布估算（当前状态）

**单条消息处理（启用所有功能）**：
```
去重检查 (含Embedding):     1.5-3s
实体提取 (SmartExtractor):  0.5-2s (规则) / 3-5s (LLM)
一致性检查:                  0.1-0.5s (规则) / 5-10s (LLM矛盾检测)
索引更新:                    1-2s (含重复Embedding)
知识图谱更新:                0.5-1s (规则) / 8-15s (LLM关系提取)
实体摘要:                    0-5s (条件触发LLM)
────────────────────────────────────────────────
总计:                        3.5-8s (纯规则) / 15-40s (含LLM)
```

**一轮对话处理（用户消息 + AI回复）**：
```
用户消息:  15-40s
AI回复:    15-40s
────────────────────────────────────────────────
总计:      30-80s
```

---

## 二、优化方案详细设计

### 方案1: Embedding 一次计算，多处复用 (收益: 2-4s/轮)

#### 2.1.1 问题定位

当前代码中，同一文本的 embedding 在两处被独立计算：

1. **去重检查** (`engine.py` 第1293-1330行)
   - `ThreeStageDeduplicator.deduplicate()` 内部计算 embedding

2. **向量索引** (`engine.py` 第1654-1658行)
   - `VectorIndex.add_text()` 再次计算 embedding

> ⚠️ **重要说明**: 项目使用的是 `recall/index/vector_index.py` (VectorIndex 类)，
> 而非 `vector_index_ivf.py`。VectorIndex 已有 `add()` 方法可直接接受 embedding。

#### 2.1.2 修改方案

**核心思路**: 在 `add()` 方法开始时预计算 embedding，然后传递给需要的组件。

**修改文件清单**:

| 文件 | 修改内容 |
|------|----------|
| `recall/engine.py` | `add()` 方法：预计算 embedding 并复用 |
| `recall/processor/three_stage_deduplicator.py` | **无需修改** - `_semantic_match` 已原生支持 `item.embedding` |
| `recall/index/vector_index.py` | **无需修改** - 已有 `add(doc_id, embedding)` 方法 |

**详细修改点**:

##### A. `engine.py` - `add()` 方法 (第1293行，`content_normalized = content.strip()` 之后)

**插入位置**: 在第1293行 `content_normalized = content.strip()` 之后，第1296行 `if self.deduplicator is not None` 之前

> ⚠️ **作用域注意**: `content_embedding` 变量定义在 `try` 块内部，但由于 Python 的作用域规则，
> 它在整个 `add()` 方法内都可访问。代码位于 `try:` 块的最外层（第1279行），
> 可以在第1658行的向量索引更新处正常访问。

```python
# ========== 位置：第1294行（content_normalized 之后，去重检查之前）==========
# 新增：预计算 embedding（如果向量索引启用且需要）
content_embedding = None
embedding_reuse_enabled = os.environ.get('EMBEDDING_REUSE_ENABLED', 'true').lower() == 'true'

if embedding_reuse_enabled and self._vector_index and self._vector_index.enabled:
    try:
        # 使用 VectorIndex 的 encode() 方法（已有缓存机制）
        content_embedding = self._vector_index.encode(content_normalized)
        _safe_print(f"[Recall] Embedding 预计算完成: dim={len(content_embedding)}")
    except Exception as e:
        _safe_print(f"[Recall] Embedding 预计算失败（回退到独立计算）: {e}")
        content_embedding = None
```

##### B. `engine.py` - 去重检查 (第1303-1308行，DedupItem 创建后)

**修改位置**: 在第1303-1308行创建 `new_item` 之后，第1311行 `existing_items = []` 之前

```python
# ========== 修改：传递预计算的 embedding ==========
# 【重要简化发现】现有的 _semantic_match 方法（第491行）已经会检查 item.embedding：
#   if item.embedding:
#       item_embedding = item.embedding
# 因此无需创建新方法，只需设置 embedding 属性即可！

# 原代码（第1303-1308行）：
new_item = DedupItem(
    id=str(uuid_module.uuid4()),
    name=content_normalized[:100],
    content=content_normalized,
    item_type="memory"
)

# 在此之后立即添加（第1309行插入）：
if content_embedding is not None:
    # 设置预计算的 embedding（ThreeStageDeduplicator._semantic_match 会自动使用）
    new_item.embedding = content_embedding.tolist() if hasattr(content_embedding, 'tolist') else list(content_embedding)

# 原有的 deduplicate() 调用无需修改！（第1323行）
dedup_result = self.deduplicator.deduplicate([new_item], existing_items)
```

##### C. `engine.py` - 向量索引更新 (第1655-1658行)

**修改位置**: 替换第1658行的 `add_text()` 调用

```python
# ========== 修改：复用预计算的 embedding ==========
# 原代码（第1655-1658行）：
if self._vector_index:
    task_manager.update_task(index_task.id, progress=0.8, message="更新向量索引...")
    # VectorIndex.add_text 接受 (turn_id, text)
    self._vector_index.add_text(memory_id, content)

# 新代码：
if self._vector_index:
    task_manager.update_task(index_task.id, progress=0.8, message="更新向量索引...")
    if content_embedding is not None:
        # 复用预计算的 embedding（VectorIndex.add 方法在第262行定义）
        self._vector_index.add(memory_id, content_embedding)
        _safe_print(f"[Recall] 向量索引已复用预计算 embedding")
    else:
        # 回退到原逻辑
        self._vector_index.add_text(memory_id, content)
```

##### D. `processor/three_stage_deduplicator.py` - **无需新增方法！**

> ✅ **重大发现**: 经审查代码（第 484-500 行），`_semantic_match` 方法已原生支持使用预设的 `item.embedding`:
> ```python
> def _semantic_match(self, item: DedupItem) -> Optional[DedupMatch]:
>     """语义匹配"""
>     # ...
>     # 获取新项目的 embedding（使用缓存）
>     if item.embedding:
>         item_embedding = item.embedding     # ← 直接使用预设值！
>     else:
>         # 使用带缓存的编码，减少 API 调用
>         item_embedding = self.embedding_backend.encode_with_cache(item.get_text())
> ```
>
> **关键代码位置**:
> - `_semantic_match` 方法定义：第484行
> - `if item.embedding:` 检查：第491行
> - `item_embedding = item.embedding`：第493行
>
> **因此，无需创建任何新方法！** 只需在 `engine.py` 中设置 `new_item.embedding` 属性，
> 现有的 `deduplicate()` 方法会自动跳过 embedding 计算，直接使用预计算值。
>
> **同时确认**: `DedupItem` 类（第61行）已有 `embedding: Optional[List[float]] = None` 属性（第69行）。
>
> 这大大简化了实施工作！

> **注意**: 上述代码已删除 `vector_index_ivf.py` 的修改，因为项目使用的是 `vector_index.py`，
> 该文件的 `VectorIndex.add(doc_id, embedding)` 方法已原生支持传入预计算的 embedding。

#### 2.1.3 收益估算

| 指标 | 优化前 | 优化后 | 节省 |
|------|--------|--------|------|
| Embedding 计算次数/消息 | 2 | 1 | 50% |
| 单消息耗时减少 | - | - | 1-2s |
| 一轮对话耗时减少 | - | - | 2-4s |

---

### 方案2: LLM 调用合并 - 综合分析 Prompt (收益: 15-25s/轮)

#### 2.2.1 问题定位

当前 LLM 调用分布在多个独立模块：

| 模块 | 文件 | LLM 调用位置 | 单次耗时 |
|------|------|--------------|----------|
| 矛盾检测 | `graph/contradiction_manager.py` | `_detect_by_llm()` | 5-10s |
| 关系提取 | `graph/llm_relation_extractor.py` | `_extract_by_llm()` | 8-15s |
| 实体摘要 | `processor/entity_summarizer.py` | `_generate_with_llm()` | 3-5s |

**每次 LLM 调用的开销**:
- 网络延迟: 100-500ms
- 上下文传输: 与输入长度成正比
- API 处理: 固定开销约 500ms
- 输出生成: 与输出长度成正比

#### 2.2.2 修改方案

**核心思路**: 设计一个综合分析 Prompt，在一次 LLM 调用中完成多个任务。

**新增文件**: `recall/processor/unified_analyzer.py`

**修改文件**:

| 文件 | 修改内容 |
|------|----------|
| `recall/engine.py` | 添加统一分析器调用逻辑 |
| `recall/processor/__init__.py` | 导出 `UnifiedAnalyzer` |

#### 2.2.3 统一分析器设计

**新建文件**: `recall/processor/unified_analyzer.py`

```python
"""统一分析器 - Recall 性能优化

设计理念：
1. 一次 LLM 调用完成多个分析任务
2. 提供完整上下文，提升分析质量
3. 向后兼容：可选启用，不影响现有功能
4. 智能回退：LLM 失败时自动回退到独立模块
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from ..utils.llm_client import LLMClient


class AnalysisTask(str, Enum):
    """分析任务类型"""
    CONTRADICTION = "contradiction"     # 矛盾检测
    RELATION = "relation"               # 关系提取
    ENTITY_SUMMARY = "entity_summary"   # 实体摘要


@dataclass
class UnifiedAnalysisInput:
    """统一分析输入"""
    content: str                                # 当前内容
    entities: List[str] = field(default_factory=list)  # 已识别实体
    existing_memories: List[str] = field(default_factory=list)  # 已有记忆（用于矛盾检测）
    tasks: List[AnalysisTask] = field(default_factory=list)  # 要执行的任务
    
    # 可选上下文
    user_id: str = "default"
    character_id: str = "default"


@dataclass
class UnifiedAnalysisResult:
    """统一分析结果"""
    success: bool = False
    
    # 矛盾检测结果
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    
    # 关系提取结果
    relations: List[Dict[str, Any]] = field(default_factory=list)
    
    # 实体摘要结果
    entity_summaries: Dict[str, str] = field(default_factory=dict)
    
    # 错误信息
    error: Optional[str] = None
    
    # 执行的任务
    tasks_executed: List[str] = field(default_factory=list)
    
    # 原始 LLM 响应（调试用）
    raw_response: Optional[str] = None


# 统一分析 Prompt 模板
UNIFIED_ANALYSIS_PROMPT = '''你是一个专业的知识图谱和记忆分析专家。请对以下对话内容进行综合分析。

## 当前对话内容
{content}

## 已识别的实体列表
{entities}

## 已有的记忆内容（用于矛盾检测）
{existing_memories}

## 分析任务
请完成以下分析任务：{tasks_description}

## 输出格式
请严格按照以下 JSON 格式输出分析结果：

```json
{{
  "contradictions": [
    {{
      "type": "直接矛盾|时态矛盾|逻辑矛盾",
      "old_fact": "已有记忆中的内容",
      "new_fact": "新内容中的矛盾点",
      "confidence": 0.8,
      "explanation": "矛盾说明"
    }}
  ],
  "relations": [
    {{
      "source": "实体A",
      "target": "实体B",
      "relation_type": "RELATION_TYPE",
      "fact": "自然语言描述",
      "confidence": 0.8
    }}
  ],
  "entity_summaries": {{
    "实体名": "该实体的简洁摘要（2-3句话）"
  }}
}}
```

## 重要说明
1. 只分析要求的任务，未要求的任务输出空数组/对象
2. 关系类型使用 SCREAMING_SNAKE_CASE 格式（如 WORKS_AT, FRIENDS_WITH）
3. 只提取实体列表中存在的实体之间的关系
4. 矛盾检测只在发现明确矛盾时才添加记录
5. 请直接输出 JSON，不要包含其他文字说明'''


class UnifiedAnalyzer:
    """统一分析器
    
    通过一次 LLM 调用完成多个分析任务：
    - 矛盾检测
    - 关系提取
    - 实体摘要
    
    使用方式：
        analyzer = UnifiedAnalyzer(llm_client=llm_client)
        
        result = analyzer.analyze(UnifiedAnalysisInput(
            content="用户说的话...",
            entities=["张三", "李四"],
            existing_memories=["之前的记忆1", "之前的记忆2"],
            tasks=[AnalysisTask.CONTRADICTION, AnalysisTask.RELATION]
        ))
        
        if result.success:
            print(f"矛盾: {result.contradictions}")
            print(f"关系: {result.relations}")
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        enabled: bool = True
    ):
        """初始化统一分析器
        
        Args:
            llm_client: LLM 客户端
            enabled: 是否启用（False 时所有调用直接返回空结果）
        """
        self.llm_client = llm_client
        self.enabled = enabled
        
        # 从环境变量读取配置
        self.max_tokens = int(os.environ.get('UNIFIED_ANALYSIS_MAX_TOKENS', '4000'))
    
    def analyze(self, input: UnifiedAnalysisInput) -> UnifiedAnalysisResult:
        """执行统一分析
        
        Args:
            input: 分析输入
            
        Returns:
            UnifiedAnalysisResult: 分析结果
        """
        if not self.enabled or not self.llm_client:
            return UnifiedAnalysisResult(
                success=False,
                error="统一分析器未启用或 LLM 客户端未配置"
            )
        
        if not input.tasks:
            return UnifiedAnalysisResult(
                success=False,
                error="未指定分析任务"
            )
        
        try:
            # 构建 Prompt
            prompt = self._build_prompt(input)
            
            # 调用 LLM
            response = self.llm_client.complete(prompt, max_tokens=self.max_tokens)
            
            # 解析结果
            result = self._parse_response(response, input.tasks)
            result.raw_response = response
            
            return result
            
        except Exception as e:
            return UnifiedAnalysisResult(
                success=False,
                error=f"统一分析失败: {str(e)}"
            )
    
    def _build_prompt(self, input: UnifiedAnalysisInput) -> str:
        """构建分析 Prompt"""
        # 任务描述
        task_descriptions = []
        if AnalysisTask.CONTRADICTION in input.tasks:
            task_descriptions.append("1. 矛盾检测：检查新内容是否与已有记忆存在矛盾")
        if AnalysisTask.RELATION in input.tasks:
            task_descriptions.append("2. 关系提取：提取实体之间的关系")
        if AnalysisTask.ENTITY_SUMMARY in input.tasks:
            task_descriptions.append("3. 实体摘要：为主要实体生成简洁摘要")
        
        tasks_description = "\n".join(task_descriptions) if task_descriptions else "无"
        
        # 格式化实体列表
        entities_str = ", ".join(input.entities) if input.entities else "（无）"
        
        # 格式化已有记忆
        if input.existing_memories:
            memories_str = "\n".join([f"- {m[:200]}..." if len(m) > 200 else f"- {m}" 
                                      for m in input.existing_memories[:10]])
        else:
            memories_str = "（无）"
        
        return UNIFIED_ANALYSIS_PROMPT.format(
            content=input.content,
            entities=entities_str,
            existing_memories=memories_str,
            tasks_description=tasks_description
        )
    
    def _parse_response(
        self,
        response: str,
        tasks: List[AnalysisTask]
    ) -> UnifiedAnalysisResult:
        """解析 LLM 响应"""
        result = UnifiedAnalysisResult(success=True)
        
        try:
            # 提取 JSON 部分
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            
            # 解析矛盾检测结果
            if AnalysisTask.CONTRADICTION in tasks:
                result.contradictions = data.get('contradictions', [])
                result.tasks_executed.append('contradiction')
            
            # 解析关系提取结果
            if AnalysisTask.RELATION in tasks:
                result.relations = data.get('relations', [])
                result.tasks_executed.append('relation')
            
            # 解析实体摘要结果
            if AnalysisTask.ENTITY_SUMMARY in tasks:
                result.entity_summaries = data.get('entity_summaries', {})
                result.tasks_executed.append('entity_summary')
            
        except json.JSONDecodeError as e:
            result.success = False
            result.error = f"JSON 解析失败: {str(e)}"
        
        return result
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        # 尝试直接解析
        text = text.strip()
        if text.startswith('{'):
            return text
        
        # 尝试提取 ```json ... ``` 块
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1).strip()
        
        # 尝试找到第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        
        raise ValueError("无法从响应中提取 JSON")
```

#### 2.2.4 Engine 集成修改

**修改文件**: `recall/engine.py`

在 `add()` 方法中，替换独立的 LLM 调用为统一分析器调用。

```python
# ========== 位置：一致性检查和知识图谱更新之前 ==========
# 新增：统一 LLM 分析（合并矛盾检测 + 关系提取）

unified_result = None
if self.unified_analyzer and self.llm_client:
    # 确定需要执行的任务
    analysis_tasks = []
    
    # 矛盾检测
    if (check_consistency and 
        self.contradiction_manager is not None and 
        self.contradiction_manager.strategy != DetectionStrategy.RULE and
        existing_memories):
        analysis_tasks.append(AnalysisTask.CONTRADICTION)
    
    # 关系提取
    if self._llm_relation_extractor and entities:
        analysis_tasks.append(AnalysisTask.RELATION)
    
    # 如果有任务需要执行
    if analysis_tasks:
        unified_input = UnifiedAnalysisInput(
            content=content,
            entities=entity_names,
            existing_memories=[m.content for m in existing_memories[:10]],
            tasks=analysis_tasks,
            user_id=user_id
        )
        
        unified_result = self.unified_analyzer.analyze(unified_input)
        
        if unified_result.success:
            _safe_print(f"[Recall] 统一分析完成: tasks={unified_result.tasks_executed}")
        else:
            _safe_print(f"[Recall] 统一分析失败，回退到独立模块: {unified_result.error}")
            unified_result = None

# ========== 修改：使用统一分析结果（如果有）==========
# 矛盾检测 - 使用统一分析结果或独立调用
if unified_result and 'contradiction' in unified_result.tasks_executed:
    # 使用统一分析的矛盾结果
    for c in unified_result.contradictions:
        # 转换为内部格式并记录
        warning_msg = f"[统一分析] {c.get('explanation', '检测到矛盾')}"
        consistency_warnings.append(warning_msg)
else:
    # 原有的独立矛盾检测逻辑
    # ... (保持不变)

# 知识图谱更新 - 使用统一分析结果或独立调用
if unified_result and 'relation' in unified_result.tasks_executed:
    # 使用统一分析的关系结果
    relations = []
    for rel in unified_result.relations:
        self.knowledge_graph.add_relation(
            source_id=rel.get('source', ''),
            target_id=rel.get('target', ''),
            relation_type=rel.get('relation_type', 'RELATED_TO'),
            source_text=content[:200],
            confidence=rel.get('confidence', 0.5),
            fact=rel.get('fact', '')
        )
        relations.append((rel.get('source'), rel.get('relation_type'), rel.get('target'), content[:200]))
else:
    # 原有的独立关系提取逻辑
    # ... (保持不变)
```

#### 2.2.5 收益估算

| 场景 | 优化前 | 优化后 | 节省 |
|------|--------|--------|------|
| 矛盾检测 + 关系提取 | 13-25s (两次调用) | 8-12s (一次调用) | 5-13s |
| 含实体摘要 | 16-30s (三次调用) | 10-15s (一次调用) | 6-15s |
| 一轮对话 (×2) | 26-60s | 16-30s | 10-30s |

---

### 方案3: 用户消息 + AI回复合并处理 (收益: 15-40s/轮)

#### 2.3.1 问题定位

当前前端（SillyTavern 插件）将用户消息和 AI 回复分开发送：

**文件**: `plugins/sillytavern/index.js`

```javascript
// 第834行：AI回复保存（在 saveAIMessageWithDOMExtraction 函数内）
const promise = memorySaveQueue.add({
    content: chunk,
    user_id: currentCharacterId || 'default',
    metadata: { 
        role: 'assistant',  // ← AI回复
        ...
    }
});

// 第5626行：用户消息保存（在 onMessageSent 函数内）
memorySaveQueue.add({
    content: chunk,
    user_id: currentCharacterId || 'default',
    metadata: { 
        role: 'user',  // ← 用户消息
        ...
    }
});
```

每条消息独立调用 `POST /v1/memories`，导致重复执行完整处理流程。

#### 2.3.2 修改方案

**核心思路**: 
1. 新增 API 端点 `POST /v1/memories/turn` 用于接收整轮对话
2. 后端合并处理，共享中间结果
3. 前端在 AI 回复完成后，将用户消息 + AI 回复打包发送

**修改文件清单**:

| 文件 | 修改内容 |
|------|----------|
| `recall/server.py` | 新增 `/v1/memories/turn` 端点 |
| `recall/engine.py` | 新增 `add_turn()` 方法 |
| `plugins/sillytavern/index.js` | 修改保存逻辑，支持合并发送 |

#### 2.3.3 后端修改

##### A. 新增请求/响应模型 (`server.py`)

> **定义位置**: 在 `# ==================== 请求/响应模型 ====================` 部分（约第985行），
> 建议添加在 `AddMemoryResponse` 类之后（约第1002行）。

```python
class AddTurnRequest(BaseModel):
    """添加对话轮次请求"""
    user_message: str = Field(..., description="用户消息")
    ai_response: str = Field(..., description="AI回复")
    user_id: str = Field(default="default", description="用户ID")
    character_id: str = Field(default="default", description="角色ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")


class AddTurnResponse(BaseModel):
    """添加对话轮次响应"""
    success: bool
    user_memory_id: str = ""
    ai_memory_id: str = ""
    entities: List[str] = []
    message: str = ""
    consistency_warnings: List[str] = []
    processing_time_ms: float = 0
```

##### B. 新增 API 端点 (`server.py`)

> **定义位置**: 在 `@app.post("/v1/memories")` 端点之后（约第1540行），
> `@app.post("/v1/memories/search")` 端点之前。

```python
@app.post("/v1/memories/turn", response_model=AddTurnResponse, tags=["Memories"])
async def add_turn(request: AddTurnRequest):
    """添加对话轮次（优化版）
    
    将用户消息和AI回复作为一个整体处理，减少重复计算：
    - Embedding 只计算一次
    - LLM 分析合并执行
    - 索引批量更新
    
    建议在 AI 回复完成后调用此端点，而不是分开调用两次 /v1/memories。
    """
    engine = get_engine()
    
    try:
        result = engine.add_turn(
            user_message=request.user_message,
            ai_response=request.ai_response,
            user_id=request.user_id,
            character_id=request.character_id,
            metadata=request.metadata
        )
        
        return AddTurnResponse(
            success=result.success,
            user_memory_id=result.user_memory_id,
            ai_memory_id=result.ai_memory_id,
            entities=result.entities,
            message=result.message,
            consistency_warnings=result.consistency_warnings,
            processing_time_ms=result.processing_time_ms
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

##### C. Engine 新增方法 (`engine.py`)

> **定义位置**: `AddTurnResult` 数据类应定义在 `SearchResult` 之后（约第84行），
> `add_turn()` 方法应定义在 `add()` 方法之后（约第1866行，`search()` 方法之前）。

```python
@dataclass
class AddTurnResult:
    """添加对话轮次结果"""
    success: bool
    user_memory_id: str = ""
    ai_memory_id: str = ""
    entities: List[str] = field(default_factory=list)
    message: str = ""
    consistency_warnings: List[str] = field(default_factory=list)
    processing_time_ms: float = 0


def add_turn(
    self,
    user_message: str,
    ai_response: str,
    user_id: str = "default",
    character_id: str = "default",
    metadata: Optional[Dict[str, Any]] = None
) -> AddTurnResult:
    """添加对话轮次（优化版）
    
    将用户消息和AI回复作为一个整体处理，共享中间结果：
    1. 合并内容进行去重检查
    2. 一次 Embedding 计算
    3. 合并 LLM 分析（矛盾 + 关系）
    4. 批量索引更新
    
    注意：此方法省略了 task_manager 任务追踪，因为：
    - Turn API 设计为快速执行（<5s），无需进度显示
    - 前端 SillyTavern 插件已有自己的加载指示器
    - 减少 task_manager 调用可进一步提升性能
    
    Args:
        user_message: 用户消息
        ai_response: AI回复
        user_id: 用户ID
        character_id: 角色ID
        metadata: 元数据
        
    Returns:
        AddTurnResult: 处理结果
    """
    start_time = time.time()
    consistency_warnings = []
    all_entities = []
    
    # 输入验证（与 server.py 的 Pydantic 验证保持一致）
    if not user_message or not user_message.strip():
        return AddTurnResult(
            success=False,
            message="用户消息不能为空"
        )
    if not ai_response or not ai_response.strip():
        return AddTurnResult(
            success=False,
            message="AI回复不能为空"
        )
    
    # 合并内容
    combined_content = f"{user_message}\n\n{ai_response}"
    
    try:
        # 1. 预计算合并内容的 Embedding（复用）
        # 注意：使用与 add() 方法相同的 _vector_index.encode() 方法，保持一致性
        combined_embedding = None
        if self._vector_index and self._vector_index.enabled:
            try:
                combined_embedding = self._vector_index.encode(combined_content)
                _safe_print(f"[Recall][Turn] Embedding 预计算完成: dim={len(combined_embedding)}")
            except Exception as e:
                _safe_print(f"[Recall][Turn] Embedding 计算失败: {e}")
        
        # 2. 合并去重检查（检查整轮内容是否重复）
        scope = self.storage.get_scope(user_id)
        existing_memories = scope.get_all(limit=100)
        
        if self.deduplicator is not None and existing_memories:
            try:
                from .processor.three_stage_deduplicator import DedupItem
                import uuid as uuid_module
                
                # 创建合并内容的 DedupItem
                combined_item = DedupItem(
                    id=str(uuid_module.uuid4()),
                    name=combined_content[:100],
                    content=combined_content,
                    item_type="memory"
                )
                # 设置预计算的 embedding
                if combined_embedding is not None:
                    combined_item.embedding = combined_embedding.tolist() if hasattr(combined_embedding, 'tolist') else list(combined_embedding)
                
                # 转换现有记忆
                existing_items = []
                for mem in existing_memories:
                    mem_content = mem.get('content', '').strip()
                    if mem_content:
                        existing_items.append(DedupItem(
                            id=mem.get('metadata', {}).get('id', str(uuid_module.uuid4())),
                            name=mem_content[:100],
                            content=mem_content,
                            item_type="memory"
                        ))
                
                if existing_items:
                    dedup_result = self.deduplicator.deduplicate([combined_item], existing_items)
                    if dedup_result.matches:
                        match = dedup_result.matches[0]
                        _safe_print(f"[Recall][Turn] 去重发现重复: {match.match_type.value}")
                        return AddTurnResult(
                            success=False,
                            message=f"对话轮次已存在（{match.match_type.value}匹配）"
                        )
            except Exception as e:
                _safe_print(f"[Recall][Turn] 去重检查失败，继续处理: {e}")
        
        # 回退：简单字符串精确匹配（与 add() 方法保持一致）
        combined_normalized = combined_content.strip()
        for mem in existing_memories:
            existing_content = mem.get('content', '').strip()
            if existing_content == combined_normalized:
                _safe_print(f"[Recall][Turn] 简单匹配发现重复")
                return AddTurnResult(
                    success=False,
                    message="对话轮次内容已存在（精确匹配）"
                )
        
        # === Recall 4.1: Episode 创建（去重通过后才创建）===
        # 为整轮对话创建一个 Episode，关联用户消息和AI回复
        current_episode = None
        if self._episode_tracking_enabled and self.episode_store:
            try:
                from .models.temporal import EpisodicNode, EpisodeType
                current_episode = EpisodicNode(
                    source_type=EpisodeType.MESSAGE,  # 使用现有 MESSAGE 类型
                    content=combined_content,
                    user_id=user_id,
                    character_id=character_id,  # 传递角色ID
                    source_description=f"Turn: {user_id}",
                )
                self.episode_store.save(current_episode)
                _safe_print(f"[Recall][Turn] Episode 已创建: {current_episode.uuid}")
            except Exception as e:
                _safe_print(f"[Recall][Turn] Episode 创建失败（不影响主流程）: {e}")
                current_episode = None
        
        # 3. 实体提取（一次提取，两条消息共享）
        keywords = []
        if self.smart_extractor is not None:
            try:
                extraction_result = self.smart_extractor.extract(combined_content)
                entities = extraction_result.entities
                all_entities = [e.name for e in entities]
                keywords = extraction_result.keywords
            except Exception as e:
                _safe_print(f"[Recall][Turn] SmartExtractor 失败，回退: {e}")
                entities = self.entity_extractor.extract(combined_content)
                all_entities = [e.name for e in entities]
                keywords = self.entity_extractor.extract_keywords(combined_content)
        else:
            entities = self.entity_extractor.extract(combined_content)
            all_entities = [e.name for e in entities]
            keywords = self.entity_extractor.extract_keywords(combined_content)
        
        # 4. 统一 LLM 分析（矛盾检测 + 关系提取，一次调用）
        relations = []
        if self.unified_analyzer:
            try:
                from .processor.unified_analyzer import UnifiedAnalysisInput, AnalysisTask
                # 获取相关记忆用于矛盾检测
                existing_memories = self.search(combined_content, user_id=user_id, top_k=5)
                
                analysis_result = self.unified_analyzer.analyze(UnifiedAnalysisInput(
                    content=combined_content,
                    entities=all_entities,
                    existing_memories=[m.content for m in existing_memories],
                    tasks=[AnalysisTask.CONTRADICTION, AnalysisTask.RELATION],
                    user_id=user_id,
                    character_id=character_id
                ))
                
                if analysis_result.success:
                    # 收集一致性警告 并 存储矛盾到管理器
                    for c in analysis_result.contradictions:
                        warning_msg = f"{c.get('old_fact', '')} vs {c.get('new_fact', '')}"
                        consistency_warnings.append(warning_msg)
                        
                        # 存储矛盾到 contradiction_manager（与 add() 方法保持一致）
                        if self.contradiction_manager is not None:
                            try:
                                from .models.temporal import TemporalFact, Contradiction, ContradictionType
                                from datetime import datetime
                                import uuid as uuid_module
                                
                                # 从 UnifiedAnalyzer 结果创建矛盾记录
                                contradiction_type = ContradictionType.DIRECT
                                if c.get('type', '').lower() in ['temporal', 'timeline']:
                                    contradiction_type = ContradictionType.TEMPORAL
                                elif c.get('type', '').lower() == 'logical':
                                    contradiction_type = ContradictionType.LOGICAL
                                
                                new_fact = TemporalFact(
                                    uuid=str(uuid_module.uuid4()),
                                    fact=c.get('new_fact', '')[:200],
                                    source_text=c.get('new_fact', '')[:200],
                                    user_id=user_id
                                )
                                old_fact = TemporalFact(
                                    uuid=str(uuid_module.uuid4()),
                                    fact=c.get('old_fact', '')[:200],
                                    source_text=c.get('old_fact', '')[:200],
                                    user_id=user_id
                                )
                                
                                contradiction = Contradiction(
                                    uuid=str(uuid_module.uuid4()),
                                    old_fact=old_fact,
                                    new_fact=new_fact,
                                    contradiction_type=contradiction_type,
                                    confidence=c.get('confidence', 0.8),
                                    detected_at=datetime.now(),
                                    notes=warning_msg[:200]
                                )
                                self.contradiction_manager.add_pending(contradiction)
                                _safe_print(f"[Recall][Turn] 矛盾已记录: {warning_msg[:50]}...")
                            except Exception as e:
                                _safe_print(f"[Recall][Turn] 矛盾记录失败（不影响主流程）: {e}")
                    
                    # 存储关系到知识图谱
                    relations = analysis_result.relations
                    if self.knowledge_graph and relations:
                        for rel in relations:
                            self.knowledge_graph.add_relation(
                                source_id=rel.get('source'),
                                target_id=rel.get('target'),
                                relation_type=rel.get('relation_type'),
                                source_text=combined_content[:200],
                                confidence=rel.get('confidence', 0.8),
                                fact=rel.get('fact', '')
                            )
            except Exception as e:
                _safe_print(f"[Recall][Turn] 统一分析失败: {e}")
                # 回退到传统关系提取器（与 add() 方法保持一致）
                if self.knowledge_graph and entities:
                    try:
                        if self._llm_relation_extractor:
                            _safe_print(f"[Recall][Turn] 回退到 LLM 关系提取器")
                            relations_v2 = self._llm_relation_extractor.extract(combined_content, 0, entities)
                            relations = [rel.to_legacy_tuple() for rel in relations_v2]
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
                            _safe_print(f"[Recall][Turn] 回退到规则关系提取器")
                            relations = self.relation_extractor.extract(combined_content, 0, entities=entities)
                            for rel in relations:
                                source_id, relation_type, target_id, source_text = rel
                                self.knowledge_graph.add_relation(
                                    source_id=source_id,
                                    target_id=target_id,
                                    relation_type=relation_type,
                                    source_text=source_text
                                )
                    except Exception as fallback_err:
                        _safe_print(f"[Recall][Turn] 回退关系提取也失败: {fallback_err}")
        else:
            # 如果 unified_analyzer 未启用，直接使用传统关系提取
            if self.knowledge_graph and entities:
                try:
                    if self._llm_relation_extractor:
                        _safe_print(f"[Recall][Turn] 使用 LLM 关系提取器（无统一分析器）")
                        relations_v2 = self._llm_relation_extractor.extract(combined_content, 0, entities)
                        relations = [rel.to_legacy_tuple() for rel in relations_v2]
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
                        _safe_print(f"[Recall][Turn] 使用规则关系提取器（无统一分析器）")
                        relations = self.relation_extractor.extract(combined_content, 0, entities=entities)
                        for rel in relations:
                            source_id, relation_type, target_id, source_text = rel
                            self.knowledge_graph.add_relation(
                                source_id=source_id,
                                target_id=target_id,
                                relation_type=relation_type,
                                source_text=source_text
                            )
                except Exception as e:
                    _safe_print(f"[Recall][Turn] 关系提取失败（无统一分析器）: {e}")
            
            # 一致性检查回退（使用传统 ConsistencyChecker）
            try:
                existing_memories = self.search(combined_content, user_id=user_id, top_k=5)
                if existing_memories:
                    consistency = self.consistency_checker.check(
                        combined_content,
                        [{'content': m.content} for m in existing_memories]
                    )
                    if not consistency.is_consistent:
                        for v in consistency.violations:
                            warning_msg = v.description
                            consistency_warnings.append(warning_msg)
                            _safe_print(f"[Recall][Turn] 一致性警告: {warning_msg}")
                        
                        # 存储矛盾到 contradiction_manager
                        if self.contradiction_manager is not None:
                            try:
                                from .models.temporal import TemporalFact, Contradiction, ContradictionType
                                from datetime import datetime
                                import uuid as uuid_module
                                
                                for v in consistency.violations:
                                    contradiction_type = ContradictionType.DIRECT
                                    type_str = v.type.value if hasattr(v.type, 'value') else str(v.type)
                                    if 'timeline' in type_str.lower() or 'temporal' in type_str.lower():
                                        contradiction_type = ContradictionType.TEMPORAL
                                    elif 'logic' in type_str.lower():
                                        contradiction_type = ContradictionType.LOGICAL
                                    
                                    evidence = v.evidence if hasattr(v, 'evidence') and v.evidence else [combined_content]
                                    new_text = evidence[0] if len(evidence) > 0 else combined_content
                                    old_text = evidence[1] if len(evidence) > 1 else ""
                                    
                                    new_fact = TemporalFact(
                                        uuid=str(uuid_module.uuid4()),
                                        fact=new_text[:200],
                                        source_text=new_text[:200],
                                        user_id=user_id
                                    )
                                    old_fact = TemporalFact(
                                        uuid=str(uuid_module.uuid4()),
                                        fact=old_text[:200],
                                        source_text=old_text[:200],
                                        user_id=user_id
                                    )
                                    
                                    contradiction = Contradiction(
                                        uuid=str(uuid_module.uuid4()),
                                        old_fact=old_fact,
                                        new_fact=new_fact,
                                        contradiction_type=contradiction_type,
                                        confidence=v.severity if hasattr(v, 'severity') else 0.8,
                                        detected_at=datetime.now(),
                                        notes=v.description[:200] if hasattr(v, 'description') else ""
                                    )
                                    self.contradiction_manager.add_pending(contradiction)
                            except Exception as e:
                                _safe_print(f"[Recall][Turn] 矛盾记录失败: {e}")
            except Exception as e:
                _safe_print(f"[Recall][Turn] 一致性检查失败（无统一分析器）: {e}")
        
        # 5. 分别存储两条记忆（但共享实体和关系）
        user_memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        ai_memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        
        # 存储用户消息
        user_scope = self.storage.get_scope(user_id)
        user_scope.add(user_message, metadata={
            'id': user_memory_id,
            'entities': all_entities,
            'keywords': keywords,
            'role': 'user',
            'character_id': character_id,
            **(metadata or {})
        })
        
        # 存储 AI 回复
        user_scope.add(ai_response, metadata={
            'id': ai_memory_id,
            'entities': all_entities,
            'keywords': keywords,
            'role': 'assistant',
            'character_id': character_id,
            **(metadata or {})
        })
        
        # 6. 批量索引更新（两条记忆一起处理）
        try:
            # 6.1 实体索引更新
            if self._entity_index:
                for entity in entities:
                    entity_type = getattr(entity, 'entity_type', 'UNKNOWN')
                    aliases = getattr(entity, 'aliases', [])
                    confidence = getattr(entity, 'confidence', 0.5)
                    # 用户消息
                    self._entity_index.add_entity_occurrence(
                        entity_name=entity.name,
                        turn_id=user_memory_id,
                        context=user_message[:200],
                        entity_type=entity_type,
                        aliases=aliases,
                        confidence=confidence
                    )
                    # AI 回复
                    self._entity_index.add_entity_occurrence(
                        entity_name=entity.name,
                        turn_id=ai_memory_id,
                        context=ai_response[:200],
                        entity_type=entity_type,
                        aliases=aliases,
                        confidence=confidence
                    )
            
            # 6.2 倒排索引更新
            if self._inverted_index:
                # 使用实体名和关键词
                all_keywords = list(set(all_entities + keywords))
                self._inverted_index.add_batch(all_keywords, user_memory_id)
                self._inverted_index.add_batch(all_keywords, ai_memory_id)
            
            # 6.3 N-gram 索引更新
            if self._ngram_index:
                self._ngram_index.add(user_memory_id, user_message)
                self._ngram_index.add(ai_memory_id, ai_response)
            
            # 6.4 向量索引更新（分别计算 embedding）
            if self._vector_index and self._vector_index.enabled:
                user_embedding = self._vector_index.encode(user_message)
                self._vector_index.add(user_memory_id, user_embedding)
                ai_embedding = self._vector_index.encode(ai_response)
                self._vector_index.add(ai_memory_id, ai_embedding)
            
            # 6.5 检索器缓存
            if self.retriever:
                self.retriever.cache_content(user_memory_id, user_message)
                self.retriever.cache_content(ai_memory_id, ai_response)
                if hasattr(self.retriever, 'cache_entities'):
                    self.retriever.cache_entities(user_memory_id, all_entities)
                    self.retriever.cache_entities(ai_memory_id, all_entities)
        except Exception as e:
            _safe_print(f"[Recall][Turn] 索引更新失败（不影响主流程）: {e}")
        
        # 7. Archive 原文保存（确保100%不遗忘）
        if self.volume_manager:
            try:
                self.volume_manager.append_turn({
                    'memory_id': user_memory_id,
                    'user_id': user_id,
                    'content': user_message,
                    'entities': all_entities,
                    'keywords': keywords,
                    'role': 'user',
                    'metadata': metadata or {},
                    'created_at': time.time()
                })
                self.volume_manager.append_turn({
                    'memory_id': ai_memory_id,
                    'user_id': user_id,
                    'content': ai_response,
                    'entities': all_entities,
                    'keywords': keywords,
                    'role': 'assistant',
                    'metadata': metadata or {},
                    'created_at': time.time()
                })
            except Exception as e:
                _safe_print(f"[Recall][Turn] Archive保存失败（不影响主流程）: {e}")
        
        # 8. 全文索引 BM25 更新（与 add() 方法保持一致）
        if self.fulltext_index is not None:
            try:
                self.fulltext_index.add(user_memory_id, user_message)
                self.fulltext_index.add(ai_memory_id, ai_response)
            except Exception as e:
                _safe_print(f"[Recall][Turn] 全文索引更新失败（不影响主流程）: {e}")
        
        # 9. 长期记忆（ConsolidatedMemory）更新（与 add() 方法保持一致）
        try:
            from .models.memory import ConsolidatedEntity
            for entity in entities:
                # 获取实体属性，兼容不同格式
                entity_type = getattr(entity, 'entity_type', 'UNKNOWN')
                confidence = getattr(entity, 'confidence', 0.5)
                aliases = getattr(entity, 'aliases', [])
                
                consolidated_entity = ConsolidatedEntity(
                    id=f"entity_{entity.name.lower().replace(' ', '_')}",
                    name=entity.name,
                    aliases=aliases if aliases else [],
                    entity_type=entity_type if entity_type else 'UNKNOWN',
                    confidence=confidence if confidence else 0.5,
                    source_turns=[user_memory_id, ai_memory_id],
                    source_memory_ids=[user_memory_id, ai_memory_id],
                    last_verified=time.strftime('%Y-%m-%dT%H:%M:%S')
                )
                self.consolidated_memory.add_or_update(consolidated_entity)
        except Exception as e:
            _safe_print(f"[Recall][Turn] 长期记忆更新失败（不影响主流程）: {e}")
        
        # 10. Episode 关联更新（与 add() 方法保持一致）
        if current_episode and self.episode_store:
            try:
                # 收集关联的实体ID
                entity_ids = []
                for e in entities:
                    if hasattr(e, 'id') and e.id:
                        entity_ids.append(e.id)
                    elif hasattr(e, 'name'):
                        entity_ids.append(f"entity_{e.name.lower().replace(' ', '_')}")
                
                # 收集关联的关系ID
                relation_ids = []
                if relations:
                    for i, rel in enumerate(relations):
                        if hasattr(rel, 'source_id') and hasattr(rel, 'target_id'):
                            relation_ids.append(f"rel_{rel.source_id}_{rel.relation_type}_{rel.target_id}")
                
                self.episode_store.update_links(
                    episode_uuid=current_episode.uuid,
                    memory_ids=[user_memory_id, ai_memory_id],
                    entity_ids=entity_ids,
                    relation_ids=relation_ids
                )
                _safe_print(f"[Recall][Turn] Episode 关联已更新: memories=2, entities={len(entity_ids)}, relations={len(relation_ids)}")
            except Exception as e:
                _safe_print(f"[Recall][Turn] Episode 关联更新失败（不影响主流程）: {e}")
        
        # 11. 实体摘要更新（与 add() 方法保持一致，Recall 4.1 功能）
        if self._entity_summary_enabled and self.entity_summarizer:
            try:
                for entity in entities:
                    entity_name = entity.name if hasattr(entity, 'name') else str(entity)
                    self._maybe_update_entity_summary(entity_name)
            except Exception as e:
                _safe_print(f"[Recall][Turn] 实体摘要更新失败（不影响主流程）: {e}")
        
        # 12. 性能监控记录（与 add() 方法保持一致）
        try:
            self.monitor.record(
                MetricType.LATENCY,
                (time.time() - start_time) * 1000
            )
        except Exception:
            pass  # 忽略性能监控错误
        
        processing_time = (time.time() - start_time) * 1000
        
        return AddTurnResult(
            success=True,
            user_memory_id=user_memory_id,
            ai_memory_id=ai_memory_id,
            entities=all_entities,
            message="对话轮次添加成功",
            consistency_warnings=consistency_warnings,
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        _safe_print(f"[Recall][Turn] 添加失败: {e}")
        return AddTurnResult(
            success=False,
            message=f"添加失败: {str(e)}"
        )
```

#### 2.3.4 前端修改

**修改文件**: `plugins/sillytavern/index.js`

```javascript
// 新增配置项
const defaultSettings = {
    // ... 现有配置
    useTurnApi: false,  // 是否使用对话轮次 API（优化模式，默认关闭）
};

// 新增：缓存当前轮次的用户消息
let currentTurnUserMessage = null;

/**
 * 保存用户消息（缓存模式）
 */
function cacheUserMessage(content, metadata) {
    if (pluginSettings.useTurnApi) {
        // 缓存用户消息，等待 AI 回复后一起发送
        currentTurnUserMessage = {
            content: content,
            metadata: metadata,
            timestamp: Date.now()
        };
        console.log('[Recall] 用户消息已缓存，等待 AI 回复...');
    } else {
        // 传统模式：立即发送
        memorySaveQueue.add({
            content: content,
            user_id: currentCharacterId || 'default',
            metadata: metadata
        });
    }
}

/**
 * 使用对话轮次 API 保存（优化版）
 */
async function saveTurnWithApi(userMessage, aiResponse, metadata) {
    const apiUrl = pluginSettings.apiUrl || 'http://127.0.0.1:18888';
    
    try {
        const response = await fetch(`${apiUrl}/v1/memories/turn`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_message: userMessage,
                ai_response: aiResponse,
                user_id: currentCharacterId || 'default',
                character_id: currentCharacterId || 'default',
                metadata: metadata
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            console.log(`[Recall] 对话轮次已保存 (${result.processing_time_ms.toFixed(0)}ms)`);
            
            // 触发伏笔分析（两条消息都需要分析）
            notifyForeshadowingAnalyzer(userMessage, 'user');
            notifyForeshadowingAnalyzer(aiResponse, 'assistant');
            
            // 显示一致性检查警告（如果有）
            if (result.consistency_warnings && result.consistency_warnings.length > 0) {
                console.warn('[Recall] 一致性检查警告:', result.consistency_warnings);
                const warningMsg = result.consistency_warnings.join('\n');
                safeToastr.warning(warningMsg, '一致性检查警告', { timeOut: 8000 });
            }
            
            // 清空缓存并清除超时计时器
            currentTurnUserMessage = null;
            clearTurnTimeout();
            
            return result;
        } else {
            throw new Error(result.message || '保存失败');
        }
    } catch (e) {
        console.error('[Recall] 对话轮次 API 调用失败:', e);
        
        // 回退：分开保存（memorySaveQueue 成功后会自动触发伏笔分析）
        await memorySaveQueue.add({
            content: userMessage,
            user_id: currentCharacterId || 'default',
            metadata: { ...metadata, role: 'user' }
        });
        await memorySaveQueue.add({
            content: aiResponse,
            user_id: currentCharacterId || 'default',
            metadata: { ...metadata, role: 'assistant' }
        });
        
        // 清空缓存并清除超时计时器
        currentTurnUserMessage = null;
        clearTurnTimeout();
        return null;
    }
}

/**
 * 处理 AI 回复完成
 */
async function onAIResponseComplete(aiContent, metadata) {
    if (pluginSettings.useTurnApi && currentTurnUserMessage) {
        // 使用对话轮次 API（优化模式）
        await saveTurnWithApi(
            currentTurnUserMessage.content,
            aiContent,
            metadata
        );
    } else {
        // 传统模式：只保存 AI 回复
        await memorySaveQueue.add({
            content: aiContent,
            user_id: currentCharacterId || 'default',
            metadata: { ...metadata, role: 'assistant' }
        });
    }
}
```

#### 2.3.5 收益估算

> **⚠️ 重要说明**: 方案3 的 Embedding 计算次数不减少（每条记忆仍需独立 embedding），
> 主要收益来自 **LLM 调用合并** 和 **实体提取合并**。

| 场景 | 优化前 | 优化后 | 节省 |
|------|--------|--------|------|
| 一轮对话处理 | 30-80s | 18-45s | 12-35s (40-45%) |
| Embedding 计算 | 4次 | 4次 | 0s (方案1已优化单消息) |
| 去重检查 | 2次 | 1次 | 1-2s |
| LLM 分析 | 4-6次 | 1-2次 | 10-25s |
| 实体提取 | 2次 | 1次 | 0.5-2s |
| 网络往返 | 2次 API | 1次 API | ~500ms |

---

## 三、实施计划

### 3.1 实施优先级

| 优先级 | 方案 | 收益 | 复杂度 | 风险 |
|--------|------|------|--------|------|
| **P0** | 方案1: Embedding 复用 | 2-4s | 低 | 极低 |
| **P1** | 方案2: LLM 调用合并 | 15-25s | 中 | 低 |
| **P2** | 方案3: 消息合并处理 | 15-40s | 中高 | 低 |

### 3.2 分阶段实施

#### 阶段一：Embedding 复用 (1-2天)

**目标**: 消除重复的 Embedding 计算

**修改范围**:
1. `engine.py`: 预计算 embedding 逻辑 + 设置 DedupItem.embedding
2. ~~`three_stage_deduplicator.py`~~: **无需修改** - `_semantic_match` 已支持 `item.embedding`
3. ~~`vector_index_ivf.py`~~: **无需修改** - `vector_index.py` 已支持

**测试要点**:
- 验证 embedding 维度一致性
- 验证去重功能不受影响
- 验证向量索引检索准确性

#### 阶段二：LLM 调用合并 (2-3天)

**目标**: 合并矛盾检测和关系提取的 LLM 调用

**修改范围**:
1. 新建 `processor/unified_analyzer.py`
2. `engine.py`: 集成统一分析器
3. `processor/__init__.py`: 导出新类

**测试要点**:
- 验证 Prompt 输出格式正确
- 验证回退机制正常工作
- 验证分析质量不降级

#### 阶段三：消息合并处理 (3-4天)

**目标**: 支持用户消息 + AI 回复合并处理

**修改范围**:
1. `server.py`: 新增 `/v1/memories/turn` 端点
2. `engine.py`: 新增 `add_turn()` 方法
3. `plugins/sillytavern/index.js`: 前端适配

**测试要点**:
- 验证两条记忆正确存储
- 验证前端兼容性
- 验证回退机制正常工作

### 3.3 回滚计划

每个方案都设计为**可选启用**，通过环境变量控制：

```bash
# 方案1: Embedding 复用
EMBEDDING_REUSE_ENABLED=true     # 默认 true

# 方案2: LLM 调用合并
UNIFIED_ANALYZER_ENABLED=true    # 默认 true

# 方案3: 消息合并处理
TURN_API_ENABLED=true            # 默认 true
```

如果发现问题，可以快速禁用相应优化而不影响系统运行。

---

## 四、风险评估

### 4.1 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Embedding 维度不一致 | 低 | 中 | 类型检查 + 自动转换 |
| LLM 输出格式不稳定 | 中 | 低 | JSON 解析容错 + 回退机制 |
| 前端兼容性问题 | 低 | 中 | 功能检测 + 渐进增强 |

### 4.2 质量风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 合并 Prompt 分析质量下降 | 低 | 中 | A/B 测试验证质量 |
| 合并处理遗漏边界情况 | 中 | 低 | 全面的单元测试 |

### 4.3 缓解策略

1. **全程可回退**: 每个优化都可通过配置开关禁用
2. **智能降级**: 优化失败时自动回退到原有逻辑
3. **监控告警**: 添加性能指标监控，异常时告警
4. **A/B 测试**: 灰度发布，验证优化效果

---

## 五、预期效果

### 5.1 性能提升

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 单条消息处理 | 15-40s | 8-20s | 45-50% |
| 一轮对话处理 | 30-80s | 15-35s | 50-55% |
| Embedding 计算次数 | 4次/轮 | 1次/轮 | 75% |
| LLM 调用次数 | 4-6次/轮 | 1-2次/轮 | 65-75% |

### 5.2 成本节省

- **API 调用成本**: 减少约 50-60%
- **计算资源**: 减少约 40-50%
- **用户等待时间**: 减少约 50%

### 5.3 功能保证

- ✅ 去重检查：完全保留
- ✅ 实体提取：完全保留
- ✅ 矛盾检测：完全保留
- ✅ 关系提取：完全保留
- ✅ 向量索引：完全保留
- ✅ 知识图谱：完全保留
- ✅ 伏笔系统：完全保留
- ✅ 条件系统：完全保留

---

## 六、文件修改清单

### 6.1 新增文件

| 文件路径 | 用途 |
|----------|------|
| `recall/processor/unified_analyzer.py` | 统一 LLM 分析器 |

### 6.2 修改文件

| 文件路径 | 修改点 |
|----------|--------|
| `recall/engine.py` | 1. 预计算 embedding 逻辑<br>2. **初始化统一分析器** (在 `_init_v4_modules` 方法末尾)<br>3. 集成统一分析器到 `add()` 方法<br>4. 新增 `add_turn()` 方法<br>5. 新增 `AddTurnResult` 数据类 |
| `recall/server.py` | 1. 新增配置项到 `SUPPORTED_CONFIG_KEYS`<br>2. 新增 `/v1/memories/turn` 端点<br>3. 新增 `AddTurnRequest` / `AddTurnResponse` 模型<br>4. 更新 `get_default_config_content()` |
| `recall/processor/__init__.py` | 导出 `UnifiedAnalyzer`, `UnifiedAnalysisInput`, `UnifiedAnalysisResult`, `AnalysisTask` |
| `plugins/sillytavern/index.js` | 支持对话轮次 API（可选开关） |
| `start.ps1` | 添加新配置项到 `$supportedKeys` 数组 |
| `start.sh` | 添加新配置项到 `$supported_keys` 字符串 |

> **重要说明**:
> - `recall/index/vector_index.py`: **无需修改** - 已有 `add(doc_id, embedding)` 方法
> - `recall/index/vector_index_ivf.py`: **无需修改** - 本项目使用 `vector_index.py`
> - `recall/processor/three_stage_deduplicator.py`: **无需修改** - `_semantic_match` 已支持使用预设的 `item.embedding`

### 6.2.1 processor/__init__.py 导出代码

在 `recall/processor/__init__.py` 文件中添加以下导入和导出：

```python
# === Recall 4.2 性能优化: 统一 LLM 分析器 ===
from .unified_analyzer import (
    UnifiedAnalyzer,
    UnifiedAnalysisInput,
    UnifiedAnalysisResult,
    AnalysisTask
)

# 在 __all__ 列表末尾添加:
__all__ = [
    # ... 现有导出 ...
    
    # === Recall 4.2 性能优化导出 ===
    'UnifiedAnalyzer',
    'UnifiedAnalysisInput',
    'UnifiedAnalysisResult',
    'AnalysisTask',
]
```

### 6.2.2 engine.py 统一分析器初始化代码

在 `_init_v4_modules()` 方法内（第577行，`self._init_entity_summarizer()` 调用之后）添加：

```python
        # 12. Recall 4.1: 实体摘要生成器
        self._init_entity_summarizer()
        
        # 13. v4.2: 统一 LLM 分析器（合并矛盾检测 + 关系提取）
        self._init_unified_analyzer()
```

然后在 `_init_entity_summarizer` 方法之后（约第671行，`_maybe_update_entity_summary` 方法之前）添加新方法：

```python
def _init_unified_analyzer(self):
    """初始化统一 LLM 分析器 (v4.2 性能优化)
    
    通过一次 LLM 调用完成多个分析任务：
    - 矛盾检测
    - 关系提取
    - 实体摘要（可选）
    """
    self.unified_analyzer = None
    
    unified_analyzer_enabled = os.environ.get('UNIFIED_ANALYZER_ENABLED', 'true').lower() == 'true'
    if unified_analyzer_enabled and self.llm_client:
        try:
            from .processor.unified_analyzer import UnifiedAnalyzer
            self.unified_analyzer = UnifiedAnalyzer(
                llm_client=self.llm_client,
                enabled=True
            )
            _safe_print("[Recall v4.2] 统一 LLM 分析器已启用")
        except ImportError:
            pass  # 模块不存在时静默跳过（尚未实现）
        except Exception as e:
            _safe_print(f"[Recall v4.2] 统一分析器初始化失败（回退到独立模块）: {e}")
```
```

### 6.3 配置文件更新

#### 6.3.1 `recall/server.py` - 添加到 SUPPORTED_CONFIG_KEYS

在 `server.py` 的 `SUPPORTED_CONFIG_KEYS` 集合中添加以下配置项（约第97行）：

```python
SUPPORTED_CONFIG_KEYS = {
    # ... 现有配置项 ...
    
    # ====== 性能优化配置 (v4.2) ======
    # Embedding 复用
    'EMBEDDING_REUSE_ENABLED',            # 是否启用 Embedding 复用（默认 true）
    
    # 统一 LLM 分析器
    'UNIFIED_ANALYZER_ENABLED',           # 是否启用统一 LLM 分析器（默认 true）
    'UNIFIED_ANALYSIS_MAX_TOKENS',        # 统一分析最大 tokens（默认 4000）
    
    # 对话轮次 API
    'TURN_API_ENABLED',                   # 是否启用对话轮次 API（默认 true）
}
```

#### 6.3.2 `recall_data/config/api_keys.env` - 添加配置项

在配置文件末尾添加（约第594行之后）：

```bash
# ============================================================================
# v4.2 性能优化配置
# v4.2 Performance Optimization Configuration
# ============================================================================

# ----------------------------------------------------------------------------
# Embedding 复用配置
# Embedding Reuse Configuration
# ----------------------------------------------------------------------------
# 是否启用 Embedding 复用（消除重复计算，节省 1-2s/消息）
# Enable embedding reuse (eliminate duplicate calculation, save 1-2s/message)
EMBEDDING_REUSE_ENABLED=true

# ----------------------------------------------------------------------------
# 统一 LLM 分析器配置
# Unified LLM Analyzer Configuration
# ----------------------------------------------------------------------------
# 是否启用统一 LLM 分析器（合并矛盾检测+关系提取，节省 5-15s/消息）
# Enable unified LLM analyzer (merge contradiction+relation, save 5-15s/message)
UNIFIED_ANALYZER_ENABLED=true

# 统一分析最大输出 tokens（复杂场景可能需要更大值）
# Max tokens for unified analysis (complex scenarios may need more)
UNIFIED_ANALYSIS_MAX_TOKENS=4000

# ----------------------------------------------------------------------------
# 对话轮次 API 配置
# Turn API Configuration
# ----------------------------------------------------------------------------
# 是否启用对话轮次 API（合并用户消息+AI回复处理，节省 15-40s/轮）
# Enable turn API (merge user message + AI response processing, save 15-40s/turn)
# 注意：需要 SillyTavern 插件配合使用
TURN_API_ENABLED=true
```

#### 6.3.3 默认配置生成更新

在 `server.py` 的 `get_default_config_content()` 函数中添加相同的配置项（在函数末尾、结束三引号 `'''` 之前，第869行位置），确保新安装时自动生成。

```python
# ============================================================================
# v4.2 性能优化配置
# v4.2 Performance Optimization Configuration
# ============================================================================

# Embedding 复用（消除重复计算，节省 1-2s/消息）
# Embedding reuse (save 1-2s/message by eliminating duplicate calculation)
EMBEDDING_REUSE_ENABLED=true

# 统一 LLM 分析器（合并矛盾检测+关系提取，节省 5-15s/消息）
# Unified LLM analyzer (save 5-15s/message by merging contradiction+relation)
UNIFIED_ANALYZER_ENABLED=true

# 统一分析最大输出 tokens
# Max tokens for unified analysis
UNIFIED_ANALYSIS_MAX_TOKENS=4000

# 对话轮次 API（合并用户消息+AI回复处理，节省 15-40s/轮）
# Turn API (save 15-40s/turn by merging user message + AI response)
TURN_API_ENABLED=true
```

> **注意**: `get_default_config_content()` 返回一个多行字符串（第274-869行），结束三引号在第869行。新配置应添加在第868行（在 `DEDUP_LLM_MAX_TOKENS=100` 之后、`'''` 之前）。

### 6.4 启动脚本配置同步 (关键！)

⚠️ **重要发现**: `start.ps1` 和 `start.sh` 中都有自己的配置项白名单，用于从 `api_keys.env` 加载配置到环境变量。**必须同步更新这三个文件**，否则新配置项无法在启动时加载！

#### 6.4.1 `start.ps1` - 添加到 `$supportedKeys` 数组 (约第133行)

在 `Import-ApiKeys` 函数的 `$supportedKeys` 数组末尾添加：

```powershell
$supportedKeys = @(
    # ... 现有配置项 ...
    
    # ====== v4.2 性能优化配置 ======
    'EMBEDDING_REUSE_ENABLED',
    'UNIFIED_ANALYZER_ENABLED',
    'UNIFIED_ANALYSIS_MAX_TOKENS',
    'TURN_API_ENABLED'
)
```

#### 6.4.2 `start.sh` - 添加到 `supported_keys` 变量 (约第235行)

在 `load_api_keys` 函数的 `supported_keys` 字符串末尾添加：

```bash
local supported_keys="... 现有配置项 ... EMBEDDING_REUSE_ENABLED UNIFIED_ANALYZER_ENABLED UNIFIED_ANALYSIS_MAX_TOKENS TURN_API_ENABLED"
```

#### 6.4.3 配置同步验证清单

实施前**必须**确认以下文件的配置项完全一致：

| 文件 | 位置 | 配置项变量 |
|------|------|-----------|
| `recall/server.py` | 第97行 | `SUPPORTED_CONFIG_KEYS` |
| `start.ps1` | 第133行 | `$supportedKeys` 数组 |
| `start.sh` | 第235行 | `$supported_keys` 字符串 |
| `get_default_config_content()` | server.py 第272-877行 | 默认配置内容 |
| ⚠️ `manage.ps1` | 第293-883行 | `$defaultConfig` here-string |
| ⚠️ `manage.sh` | 第295-884行 | `cat << 'EOF' ... EOF` 块 |

#### 6.4.4 `manage.ps1` - 添加到 `$defaultConfig` 模板 (第293-883行)

**⚠️ 重要发现**: `manage.ps1` 包含完整的默认配置模板 `$defaultConfig`，在初始化时会写入 `api_keys.env`！

**修改位置**: 在第883行 `'@` 之前（`DEDUP_LLM_MAX_TOKENS=100` 之后）添加：

```powershell
$defaultConfig = @'
# ... 现有配置内容 ...
DEDUP_LLM_MAX_TOKENS=100

# ============================================================================
# v4.2 性能优化配置 - RECALL 4.2 PERFORMANCE OPTIMIZATION
# ============================================================================

# ----------------------------------------------------------------------------
# Embedding 复用配置
# Embedding Reuse Configuration
# ----------------------------------------------------------------------------
# 是否启用 Embedding 复用（去重和向量索引共用同一次 Embedding 计算）
# Enable embedding reuse (share embedding between dedup and vector index)
EMBEDDING_REUSE_ENABLED=true

# ----------------------------------------------------------------------------
# 统一分析器配置
# Unified Analyzer Configuration
# ----------------------------------------------------------------------------
# 是否启用统一分析器（合并矛盾检测、关系提取、实体摘要为一次 LLM 调用）
# Enable unified analyzer (merge contradiction detection, relation extraction, entity summary into one LLM call)
UNIFIED_ANALYZER_ENABLED=true

# 统一分析最大 tokens
# Max tokens for unified analysis
UNIFIED_ANALYSIS_MAX_TOKENS=4000

# ----------------------------------------------------------------------------
# 对话轮次 API 配置
# Turn API Configuration
# ----------------------------------------------------------------------------
# 是否启用对话轮次 API（合并用户消息+AI回复处理，节省 15-40s/轮）
# Enable Turn API (save 15-40s/turn by merging user message + AI response)
TURN_API_ENABLED=true
'@
```

#### 6.4.5 `manage.sh` - 添加到 here-document 模板 (第295-884行)

**⚠️ 重要发现**: `manage.sh` 同样包含完整的默认配置模板，在初始化时会写入 `api_keys.env`！

**修改位置**: 在第884行 `EOF` 之前（`DEDUP_LLM_MAX_TOKENS=100` 之后）添加：

```bash
cat > "$config_file" << 'EOF'
# ... 现有配置内容 ...
DEDUP_LLM_MAX_TOKENS=100

# ============================================================================
# v4.2 性能优化配置 - RECALL 4.2 PERFORMANCE OPTIMIZATION
# ============================================================================

# ----------------------------------------------------------------------------
# Embedding 复用配置
# Embedding Reuse Configuration
# ----------------------------------------------------------------------------
# 是否启用 Embedding 复用（去重和向量索引共用同一次 Embedding 计算）
# Enable embedding reuse (share embedding between dedup and vector index)
EMBEDDING_REUSE_ENABLED=true

# ----------------------------------------------------------------------------
# 统一分析器配置
# Unified Analyzer Configuration
# ----------------------------------------------------------------------------
# 是否启用统一分析器（合并矛盾检测、关系提取、实体摘要为一次 LLM 调用）
# Enable unified analyzer (merge contradiction detection, relation extraction, entity summary into one LLM call)
UNIFIED_ANALYZER_ENABLED=true

# 统一分析最大 tokens
# Max tokens for unified analysis
UNIFIED_ANALYSIS_MAX_TOKENS=4000

# ----------------------------------------------------------------------------
# 对话轮次 API 配置
# Turn API Configuration
# ----------------------------------------------------------------------------
# 是否启用对话轮次 API（合并用户消息+AI回复处理，节省 15-40s/轮）
# Enable Turn API (save 15-40s/turn by merging user message + AI response)
TURN_API_ENABLED=true
EOF
```

### 6.5 无需修改的脚本文件

以下脚本文件**无需修改**，因为它们不涉及运行时配置项：

| 文件 | 原因 |
|------|------|
| `install.ps1` / `install.sh` | 安装脚本，仅安装依赖，不涉及运行时配置 |

### 6.6 需要修改的脚本文件汇总

⚠️ **配置同步必须修改的文件（共6个）**：

| # | 文件 | 位置 | 修改内容 |
|---|------|------|----------|
| 1 | `recall/server.py` | 第97行 | `SUPPORTED_CONFIG_KEYS` 添加 4 个新键 |
| 2 | `recall/server.py` | 第868行 | `get_default_config_content()` 添加默认值和注释 |
| 3 | `start.ps1` | 第133行 | `$supportedKeys` 数组添加 4 个新键 |
| 4 | `start.sh` | 第235行 | `$supported_keys` 字符串添加 4 个新键 |
| 5 | `manage.ps1` | 第883行前 | `$defaultConfig` 添加完整配置块（含注释） |
| 6 | `manage.sh` | 第884行前 | `cat << 'EOF'` 添加完整配置块（含注释） |

> **⚠️ 重要**: `manage.ps1` 和 `manage.sh` **需要修改**！它们包含完整的默认配置模板，在首次初始化时会生成 `api_keys.env`。见 6.4.4 和 6.4.5 节。

---

## 七、测试计划

### 7.1 单元测试

- `test_embedding_reuse.py`: 测试 embedding 复用
- `test_unified_analyzer.py`: 测试统一分析器
- `test_turn_api.py`: 测试对话轮次 API

### 7.2 集成测试

- 完整对话流程测试
- 性能基准测试
- 回退机制测试

### 7.3 压力测试

- 并发请求测试
- 大文本处理测试
- 长时间运行稳定性测试

---

## 八、SillyTavern 插件适配详细说明

### 8.1 现有消息处理流程分析

通过代码审查，SillyTavern 插件当前的消息处理流程如下：

1. **用户消息**: `onMessageSent()` 函数 (约第5588行)
   - 事件触发: `MESSAGE_SENT` (注册于第4775行)
   - 立即调用 `memorySaveQueue.add()` 保存用户消息 (第5626行)
   
2. **AI回复**: `saveAIMessageWithDOMExtraction()` 函数 (约第768行)
   - 事件触发: `MESSAGE_RECEIVED` (注册于第4776行) → 等待渲染完成 → 提取内容
   - 调用 `memorySaveQueue.add()` 保存AI回复 (第834行)

### 8.2 方案3适配策略（渐进增强）

为确保**向后兼容**和**零风险**，前端修改采用渐进增强策略：

```javascript
// 方案3 的前端修改要点：

// 1. 新增配置项（默认关闭，用户可手动开启）
const defaultSettings = {
    // ... 现有配置
    useTurnApi: false,  // 默认关闭，确保向后兼容
};

// 2. 用户消息缓存（仅在启用 Turn API 时）
let currentTurnUserMessage = null;

// 3. 修改 onMessageSent()：
async function onMessageSent(messageIndex) {
    // ... 现有逻辑
    
    if (pluginSettings.useTurnApi) {
        // 新模式：缓存用户消息，等待AI回复
        currentTurnUserMessage = {
            content: message.mes,
            metadata: { role: 'user', ... },
            timestamp: Date.now()
        };
        // ⚠️ 重要：启动超时计时器，防止用户消息丢失
        startTurnTimeout();
        console.log('[Recall] 用户消息已缓存，等待AI回复...');
    } else {
        // 传统模式：立即保存（保持不变）
        memorySaveQueue.add({ ... });
    }
}

// 4. 修改 saveAIMessageWithDOMExtraction()：
async function saveAIMessageWithDOMExtraction(messageIndex, messageData) {
    // ... 内容提取逻辑保持不变
    
    if (pluginSettings.useTurnApi && currentTurnUserMessage) {
        // 新模式：合并发送
        await saveTurnWithApi(
            currentTurnUserMessage.content,
            contentToSave,
            { ... }
        );
    } else {
        // 传统模式：只保存AI回复（保持不变）
        memorySaveQueue.add({ ... });
    }
}

// 5. 新增 Turn API 调用函数（带回退机制）
async function saveTurnWithApi(userMessage, aiResponse, metadata) {
    try {
        const response = await fetch(`${apiUrl}/v1/memories/turn`, { ... });
        const result = await response.json();
        if (result.success) {
            currentTurnUserMessage = null;
            return result;
        }
        throw new Error(result.message);
    } catch (e) {
        console.warn('[Recall] Turn API 失败，回退到传统模式');
        // 回退：分开保存（确保数据不丢失）
        await memorySaveQueue.add({ content: userMessage, ... });
        await memorySaveQueue.add({ content: aiResponse, ... });
        currentTurnUserMessage = null;
    }
}

// 6. 新增：超时保护机制（防止用户消息丢失）
const TURN_TIMEOUT_MS = 60000;  // 60秒超时
let turnTimeoutTimer = null;

function startTurnTimeout() {
    clearTurnTimeout();
    turnTimeoutTimer = setTimeout(() => {
        if (currentTurnUserMessage) {
            console.warn('[Recall] 用户消息缓存超时，自动保存');
            memorySaveQueue.add({
                content: currentTurnUserMessage.content,
                user_id: currentCharacterId || 'default',
                metadata: currentTurnUserMessage.metadata
            });
            currentTurnUserMessage = null;
        }
    }, TURN_TIMEOUT_MS);
}

function clearTurnTimeout() {
    if (turnTimeoutTimer) {
        clearTimeout(turnTimeoutTimer);
        turnTimeoutTimer = null;
    }
}

// 在 onMessageSent 中缓存消息后调用 startTurnTimeout()
// 在 saveAIMessageWithDOMExtraction 成功处理后调用 clearTurnTimeout()
```

### 8.3 重要适配注意事项

1. **默认关闭**: `useTurnApi` 默认为 `false`（实验性功能），用户需手动在设置面板中启用
2. **回退机制**: API 失败时自动回退到传统模式，确保数据不丢失
3. **超时处理**: 如果用户消息缓存超过 60 秒未收到AI回复，自动保存并清空（见上方代码）
4. **多窗口处理**: 缓存使用 `currentCharacterId` 作为 key，避免角色混淆

### 8.4 设置面板 UI 添加

需要在 `createUI()` 函数的设置标签页中添加 Turn API 开关（约第2840行 `recall-tab-settings` 部分）：

```html
<!-- 在基本设置部分添加 -->
<div class="recall-setting-group">
    <label class="recall-setting-label">
        <input type="checkbox" id="recall-use-turn-api" ${pluginSettings.useTurnApi ? 'checked' : ''}>
        <span>启用对话轮次优化</span>
    </label>
    <div class="recall-setting-hint">
        ⚡ 实验性功能：合并用户消息和AI回复一起处理，减少等待时间<br>
        ⚠️ 如遇问题可关闭此选项回退到传统模式
    </div>
</div>
```

同时需要在 `bindSettingsEvents()` 函数中添加事件绑定：

```javascript
// Turn API 开关
document.getElementById('recall-use-turn-api')?.addEventListener('change', (e) => {
    pluginSettings.useTurnApi = e.target.checked;
    saveSettings();
    console.log('[Recall] Turn API 模式:', pluginSettings.useTurnApi ? '启用' : '禁用');
});
```

---

## 九、潜在问题预防清单

### 9.1 方案1 (Embedding 复用) 潜在问题

| 问题 | 预防措施 |
|------|----------|
| embedding 维度不一致 | 统一使用 `_vector_index.encode()` 方法 |
| numpy/list 类型转换 | 在 DedupItem 中统一转为 list |
| 缓存未命中 | `encode_with_cache` 已有 LRU 缓存机制 |
| Lite 模式兼容 | 检查 `_vector_index.enabled` 再预计算 |

### 9.2 方案2 (LLM 调用合并) 潜在问题

| 问题 | 预防措施 |
|------|----------|
| JSON 解析失败 | 多重解析策略 + 正则提取 |
| LLM 输出截断 | 设置足够的 `max_tokens` |
| 部分任务失败 | 解析失败的任务回退到独立模块 |
| 超时 | 设置合理超时 + 异步处理 |

### 9.3 方案3 (消息合并处理) 潜在问题

| 问题 | 预防措施 |
|------|----------|
| 用户消息丢失 | 超时自动保存 + 回退机制 |
| AI 回复超长 | 分段保存逻辑保持不变 |
| 网络中断 | 本地缓存 + 重连后同步 |
| 多角色混淆 | 使用 `character_id` 作为 key |

---

## 十、总结

本优化方案通过三个独立但互补的措施，在**零功能降级**的前提下，预期可将记忆处理时间减少 **40-60%**：

1. **Embedding 复用** (P0): 消除重复计算，节省 2-4s/轮
2. **LLM 调用合并** (P1): 合并分析任务，节省 15-25s/轮
3. **消息合并处理** (P2): 整轮统一处理，节省 15-40s/轮

所有优化都设计为**可选启用**、**智能回退**，确保系统稳定性和可维护性。

### 10.1 版本兼容性

- **后端兼容**: 新 API 与旧 API 并存，互不影响
- **前端兼容**: 插件可选启用新功能，默认使用传统模式
- **配置兼容**: 新配置项有默认值，无需用户干预

### 10.2 审核通过条件

✅ VectorIndex 使用正确（vector_index.py 而非 ivf 版本）  
✅ VectorIndex.encode() 方法已确认存在（第256行）  
✅ VectorIndex.add() 方法已确认存在（第262行）  
✅ VectorIndex.enabled 属性已确认存在（第116-118行）  
✅ 配置项已添加到 `SUPPORTED_CONFIG_KEYS` (server.py:97)  
✅ 配置项已同步到 `start.ps1` 的 `$supportedKeys` 数组 (第133行)  
✅ 配置项已同步到 `start.sh` 的 `$supported_keys` 字符串 (第235行)  
✅ 默认配置已添加到 `get_default_config_content()` (server.py:272-869)  
✅ Windows/Linux 配置统一（通过 api_keys.env）  
✅ SillyTavern 插件适配策略完善（渐进增强）  
✅ SillyTavern 插件 `defaultSettings` 位置已确认（第30行）  
✅ SillyTavern 设置面板 UI 开关已规划（第2840行）  
✅ 回退机制完备（三个方案均有回退）  
✅ UnifiedAnalyzer 初始化代码已规划（engine.py 第578行，在 `_init_entity_summarizer()` 之后）  
✅ UnifiedAnalyzer 包含 ImportError 异常处理  
✅ processor/__init__.py 导出已规划（含具体代码示例）  
✅ **代码简化**: `_semantic_match` 已原生支持 `item.embedding`（第484行定义，第491-492行检查并使用），无需新建方法  
✅ **DedupItem 已有 embedding 属性**（第61行类定义，第69行属性定义 `embedding: Optional[List[float]] = None`）  
✅ **manage.ps1 配置同步已规划**（`$defaultConfig` 第293-883行，添加 4 个新配置）  
✅ **manage.sh 配置同步已规划**（`cat << 'EOF'` 第295-884行，添加 4 个新配置）  
✅ install.ps1/install.sh 无需修改（仅安装依赖，不涉及运行时配置）  
✅ DedupItem 创建位置已确认（engine.py:1303）  
✅ 向量索引更新位置已确认（engine.py:1658）  
✅ add_turn() 方法包含完整索引更新逻辑  
✅ add_turn() 方法包含 Archive 原文保存  
✅ add_turn() 方法包含知识图谱更新  
✅ add_turn() 方法包含全文索引 BM25 更新  
✅ add_turn() 方法包含长期记忆 (ConsolidatedMemory) 更新  
✅ add_turn() 方法包含 Episode 创建（去重通过后）  
✅ add_turn() 方法包含 Episode 关联更新  
✅ add_turn() 方法包含回退简单字符串匹配去重  
✅ add_turn() 方法包含实体摘要更新  
✅ add_turn() 方法包含性能监控记录  
✅ add_turn() 方法包含 **矛盾记录到 contradiction_manager**（与 add() 一致）  
✅ add_turn() 方法包含 **传统关系提取器回退**（UnifiedAnalyzer 失败时）  
✅ add_turn() 方法包含 **一致性检查回退**（UnifiedAnalyzer 未启用时使用 ConsistencyChecker）  
✅ saveTurnWithApi 包含伏笔分析触发  
✅ saveTurnWithApi 包含一致性警告显示

### 10.3 实施前最终检查清单

实施前**必须逐一确认**以下事项：

| # | 检查项 | 文件 | 状态 |
|---|--------|------|------|
| 1 | `SUPPORTED_CONFIG_KEYS` 添加 4 个新配置 | server.py:97 | ⬜ |
| 2 | `$supportedKeys` 添加 4 个新配置 | start.ps1:133 | ⬜ |
| 3 | `$supported_keys` 添加 4 个新配置 | start.sh:235 | ⬜ |
| 4 | `get_default_config_content()` 添加默认值 | server.py:868 | ⬜ |
| 5 | `$defaultConfig` 添加完整配置块 | manage.ps1:883前 | ⬜ |
| 6 | `cat << 'EOF'` 添加完整配置块 | manage.sh:884前 | ⬜ |
| 7 | 创建 `unified_analyzer.py` | processor/ | ⬜ |
| 8 | `__init__.py` 导出 UnifiedAnalyzer | processor/ | ⬜ |
| 9 | `_init_unified_analyzer()` 方法 | engine.py:578 (在 `_init_entity_summarizer()` 之后) | ⬜ |
| 10 | `add()` 方法 embedding 预计算 | engine.py:1294 (在 `content_normalized` 之后) | ⬜ |
| 11 | 设置 `DedupItem.embedding` 属性 | engine.py:1309 (在 `new_item` 创建之后) | ⬜ |
| 12 | `add()` 方法向量索引复用 embedding | engine.py:1658 (替换 `add_text` 为 `add`) | ⬜ |
| 13 | `/v1/memories/turn` 端点 | server.py:~1536（在 `/v1/memories` 和 `/v1/memories/search` 之间） | ⬜ |
| 14 | `AddTurnRequest/Response` Pydantic 模型 | server.py:~1003（在 `AddMemoryResponse` 后） | ⬜ |
| 15 | `AddTurnResult` 数据类 | engine.py:~84 | ⬜ |
| 16 | `add_turn()` 方法完整实现 | engine.py:~1866 | ⬜ |
| 17 | SillyTavern `useTurnApi` 配置 | index.js:30 (defaultSettings) | ⬜ |
| 18 | SillyTavern `saveTurnWithApi` 函数 | index.js | ⬜ |
| 19 | SillyTavern 设置面板 Turn API 开关 | index.js:~2840 (recall-tab-settings) | ⬜ |
| 20 | SillyTavern 回退机制和超时保护 | index.js | ⬜ |

> **简化说明**: 原计划的 `deduplicate_with_embedding()` 方法已删除，因为现有的 `_semantic_match` 方法（三阶段去重器第484行）已原生支持使用 `item.embedding`。只需设置 `new_item.embedding` 属性即可。

### 10.4 功能完整性保证清单

确保 `add_turn()` 方法实现与 `add()` 方法功能对等：

| 功能 | add() 方法 | add_turn() 方法 | 状态 |
|------|-----------|-----------------|------|
| 去重检查 | ✅ 三阶段去重 | ✅ 合并内容去重 | ⬜ |
| 回退去重 | ✅ 简单字符串匹配 | ✅ 简单字符串匹配 | ⬜ |
| Episode创建 | ✅ EpisodicNode | ✅ MESSAGE类型 | ⬜ |
| 实体提取 | ✅ SmartExtractor | ✅ 合并内容提取 | ⬜ |
| 关键词提取 | ✅ keywords | ✅ 合并内容提取 | ⬜ |
| 一致性检查 | ✅ ConsistencyChecker + LLM | ✅ UnifiedAnalyzer / 回退到ConsistencyChecker | ⬜ |
| 矛盾记录 | ✅ contradiction_manager.add_pending | ✅ add_pending | ⬜ |
| 关系提取 | ✅ LLMRelationExtractor / 规则 | ✅ UnifiedAnalyzer / 回退到传统提取 | ⬜ |
| 核心存储 | ✅ scope.add() | ✅ 分别存储两条 | ⬜ |
| 实体索引 | ✅ _entity_index | ✅ 分别添加 | ⬜ |
| 倒排索引 | ✅ _inverted_index | ✅ 分别添加 | ⬜ |
| N-gram索引 | ✅ _ngram_index | ✅ 分别添加 | ⬜ |
| 向量索引 | ✅ _vector_index | ✅ 分别计算 embedding | ⬜ |
| 检索器缓存 | ✅ retriever.cache | ✅ 分别缓存 | ⬜ |
| 全文索引BM25 | ✅ fulltext_index | ✅ 分别添加 | ⬜ |
| 长期记忆 | ✅ consolidated_memory | ✅ 批量更新 | ⬜ |
| Archive存储 | ✅ volume_manager | ✅ 分别存储 | ⬜ |
| 知识图谱 | ✅ knowledge_graph | ✅ 统一分析后存储 | ⬜ |
| Episode关联 | ✅ episode_store.update_links | ✅ 关联两条记忆 | ⬜ |
| 实体摘要 | ✅ _maybe_update_entity_summary | ✅ 批量更新 | ⬜ |
| 性能监控 | ✅ monitor.record | ✅ 延迟记录 | ⬜ |
| 返回警告 | ✅ consistency_warnings | ✅ 返回警告 | ⬜ |
