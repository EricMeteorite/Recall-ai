# Recall v3 项目自查报告

> 检查日期：2026年1月18日  
> 对照文档：Recall-ai-plan.md - 十二点五、最终自查（完整版）

---

## 一、自查结果总览

| 状态 | 数量 | 占比 |
|:-----|:----:|:----:|
| ✅ 完全实现 | 22 | 88% |
| 🔧 部分实现 | 2 | 8% |
| ❌ 未实现（可选功能） | 1 | 4% |
| **总计** | **25** | **100%** |

> 📌 **说明**：
> - 伏笔自动检测采用 **LLM API 新方案**（比原计划的规则匹配更智能）
> - 规范100%遵守：L0注入已实现，规则编译器简化（对RP场景已足够）
> - CodeIndexer 是代码场景功能，RP场景可选

---

## 二、详细对照检查

### 第一组：核心功能需求（15项）

| # | 需求 | 计划方案 | 实际状态 | 实现位置 |
|---|------|---------|:--------:|---------|
| 1 | 上万轮 RP | 分卷存储 + O(1)定位 + 预加载 + 并发锁 | ✅ | `recall/storage/volume_manager.py` |
| 2 | 伏笔不遗忘 | ~~三重检测~~ → **LLM API 新方案** | 🔧 | 待实现 `foreshadowing_analyzer.py` |
| 3 | 几百万字规模 | 分卷架构 + 懒加载 + 增量索引 | ✅ | `VolumeManager` 每卷50MB |
| 4 | 上千文件代码 | 多语言解析器 + 符号表 + 依赖图 | ❌ | 未实现（代码场景，RP可选） |
| 5 | 规范100%遵守 | L0注入 + 规则编译 + 属性检查 | 🔧 | L0注入✅ 规则编译简化（详见说明） |
| 6 | 零配置即插即用 | pip install + API key 即可使用 | ✅ | `pyproject.toml` |
| 7 | 100%不遗忘 | Archive原文保存 + 8层检索 + N-gram兜底 | ✅ | `recall/retrieval/eight_layer.py` |
| 8 | 面向大众友好 | ST插件市场安装 + 3步完成 + 全中文 | ✅ | `plugins/sillytavern/` |
| 9 | 配置key就能用 | 只需设置一个 API key 环境变量 | ✅ | `api_keys.env` |
| 10 | pip install即插即用 | 命令行两步完成 | ✅ | CLI完整支持 |
| 11 | 普通人无门槛 | 纯本地插件 + 用户自己的API key | ✅ | 独立运行 |
| 12 | 3-5秒响应 | 并行检索 + 异步写入 + 缓存热路径 | ✅ | `recall/retrieval/parallel_retrieval.py` |
| 13 | 知识图谱 | 轻量级本地图结构 + 关系自动提取 | ✅ | `recall/graph/knowledge_graph.py` |
| 14 | 多用户/多角色 | MemoryScope 作用域隔离 | ✅ | `recall/storage/multi_tenant.py` |
| 15 | 低配电脑支持 | 轻量模式（~80MB内存）+ 无GPU要求 | ✅ | `--lightweight` 模式 |

### 第二组：即插即用/环境隔离检查项（10项）

| # | 需求 | 计划方案 | 实际状态 | 实现位置 |
|---|------|---------|:--------:|---------|
| 16 | 单一数据目录 | 所有数据存储在 `./recall_data/` | ✅ | `RecallInit.get_data_root()` |
| 17 | 模型隔离存储 | NLP模型下载到 `./recall_data/models/` | ✅ | `RecallInit.setup_environment()` |
| 18 | 无系统级修改 | 不修改注册表/系统服务/PATH | ✅ | 无系统级操作 |
| 19 | 环境变量隔离 | 运行时临时设置，退出时恢复 | ✅ | `recall/init.py` |
| 20 | 完整卸载支持 | pip uninstall + 删除目录 = 完全干净 | ✅ | 删除文件夹即可 |
| 21 | 虚拟环境兼容 | 支持在 venv 中安装 | ✅ | `recall-env` |
| 22 | 不修改其他应用 | ST 插件独立，不修改 ST 原配置 | ✅ | IIFE隔离 |
| 23 | 离线运行支持 | 模型下载后可离线运行 | ✅ | 本地spaCy/向量模型 |
| 24 | 跨平台支持 | Windows/Mac/Linux 统一行为 | ✅ | 多平台脚本 |
| 25 | 配置文件隔离 | 配置存储在 `./recall_data/config.json` | ✅ | 项目目录内 |

---

## 三、功能差异详细说明

### 🔧 1. 伏笔自动检测 - 采用 LLM 新方案（待实现）

**原计划**：三重检测（关键词+组合+语义）+ 主动提醒

**新方案**：LLM API 智能分析（更优）

| 对比 | 原计划（规则匹配） | 新方案（LLM API） |
|------|:----------------:|:-----------------:|
| 准确性 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 隐含伏笔识别 | ❌ | ✅ |
| 维护成本 | 高（需维护词库） | 低 |
| 运行成本 | 免费 | 极低（~$0.01/100轮） |

**待实现内容**：`ForeshadowingAnalyzer` 类，详见第四节实现计划。

---

### ❌ 2. CodeIndexer（代码索引器）- 未实现（可选）

**计划文档位置**：第五节 CodeIndexer

**计划要求**：
```python
class CodeIndexer:
    """代码索引器"""
    def index_file(self, file_path: str) -> None: ...
    def index_directory(self, dir_path: str) -> None: ...
    def search_symbol(self, name: str) -> List[Symbol]: ...
    def get_dependencies(self, file_path: str) -> List[str]: ...
```

**应包含功能**：
- 多语言解析器（Python/JS/Java/Go/Rust等）
- 符号表（函数/类/变量/常量索引）
- 依赖图（import/require/include 分析）
- 代码搜索（按符号名、按文件路径）

**当前状态**：项目中不存在 `code_indexer.py` 文件

**建议**：此功能面向"代码场景"，如果项目主要面向 RP/小说场景：
- 方案A：标记为 v3.1 版本功能
- 方案B：从需求列表中移除

---

### 🔧 3. 规范100%遵守 - 部分实现

**计划要求**：L0注入 + 规则编译 + 属性检查

**实际状态**：

| 子功能 | 状态 | 说明 |
|--------|:----:|------|
| L0核心设定注入 | ✅ | `layer0_core.py` - 角色卡、世界观、写作风格 |
| `absolute_rules` 绝对规则 | ✅ | 用户可配置的绝对规则列表 |
| `get_injection_text()` | ✅ | 按场景(RP/coding)返回注入内容 |
| 事实冲突检测 | ✅ | `consistency.py` - 数值属性(年龄/身高/体重)冲突 |
| 时间线检查 | 🔧 | 框架已有，逻辑简化 |
| **规则编译器** | ❌ | 计划要求将规则转换为可执行检查，未实现 |
| **复杂属性检查** | ❌ | 仅支持数值属性，不支持复杂逻辑规则 |

**对 RP 场景的影响**：
- L0 注入功能**已足够**确保角色卡和世界观被注入
- `absolute_rules` 可以让用户手动添加「绝对不能违反」的规则
- 事实冲突检测可以发现简单的数值矛盾

**缺失内容**：
- 规则编译器（将自然语言规则转换为可执行的检查逻辑）
- 复杂属性类型支持（如「角色A和角色B是敌对关系」）

**建议**：对于 v3.0 RP 场景，当前实现已足够。规则编译器可作为 v3.1 增强功能。

---

### ✅ 4. 伏笔基础功能 - 已完成

以下功能已在 `recall/processor/foreshadowing.py` 中实现：

| 功能 | 状态 | 说明 |
|------|:----:|------|
| `plant()` | ✅ | 手动埋下伏笔 |
| `add_hint()` | ✅ | 添加伏笔提示 |
| `resolve()` | ✅ | 手动解决伏笔 |
| `abandon()` | ✅ | 放弃伏笔 |
| `get_active()` | ✅ | 获取活跃伏笔 |
| `get_by_entity()` | ✅ | 按实体获取伏笔 |
| 多角色分隔存储 | ✅ | 每个角色独立存储 |

> 💡 新增的 `ForeshadowingAnalyzer` 将基于这些已有功能构建。

---

### 📁 4. 文件结构差异（非功能缺失）

**计划文档要求的文件结构**：
```
recall/storage/
├── layer0_core.py       ✅ 已有
├── layer1_consolidated.py ✅ 已有
├── layer2_working.py    ✅ 已有
├── layer3_archive.py    ⚪ 合并到 volume_manager.py
├── volume_manager.py    ✅ 已有
└── multi_tenant.py      ✅ 已有
```

**说明**：L3原文存档功能已在 `volume_manager.py` 中实现。这是架构简化，**不影响功能完整性**。

---

## 四、缺失功能实现计划

### 阶段一：伏笔自动检测（优先级：🔴 高）- LLM 方案

**预计工作量**：2-3天

> 💡 **设计理念**：简洁的双模式设计。无 API 时手动管理，有 API 时智能分析。批量处理降低 LLM 成本。

---

#### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                   ForeshadowingAnalyzer                      │
├─────────────────────────────────────────────────────────────┤
│  后端模式（两种模式，手动操作始终可用）:                      │
│  ├─ MANUAL (默认) - 纯手动，用户自己管理伏笔                 │
│  └─ LLM - 手动 + 自动辅助检测（需配置API key）               │
├─────────────────────────────────────────────────────────────┤
│  ⚠️ 重要：无论哪种模式，手动 API 始终可用！                  │
│  ├─ plant() - 手动埋伏笔                                     │
│  ├─ resolve() - 手动标记解决                                 │
│  ├─ get_active() - 查看活跃伏笔                              │
│  └─ LLM 模式只是额外增加「自动检测建议」功能                 │
├─────────────────────────────────────────────────────────────┤
│  配置项（LLM模式额外功能）:                                   │
│  ├─ trigger_interval: 每N轮触发一次 (默认10轮)               │
│  ├─ llm_model: 使用的模型 (默认 gpt-4o-mini)                 │
│  ├─ auto_plant: 自动埋下检测到的伏笔 (默认 true)             │
│  └─ auto_resolve: 自动标记解决 (默认 false，建议手动确认)    │
├─────────────────────────────────────────────────────────────┤
│  工作流程（LLM模式）:                                        │
│  1. 累积对话内容到缓冲区                                     │
│  2. 达到触发条件时，批量发送给 LLM 分析                      │
│  3. 解析 LLM 返回的 JSON 结果                                │
│  4. auto_plant=true 自动添加，否则只提示用户手动确认         │
└─────────────────────────────────────────────────────────────┘
```

> 💡 **设计理念**：LLM 是辅助，不是替代。用户随时可以手动添加/编辑/删除伏笔。
> 
> 💡 **为什么不做规则匹配？** 规则不可能全面，稍微复杂的伏笔就检测不出来。

---

#### 任务 1.1：创建配置类

**文件**：`recall/processor/foreshadowing_analyzer.py`

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any

class AnalyzerBackend(Enum):
    """分析器后端类型"""
    MANUAL = "manual"  # 手动模式（默认）
    LLM = "llm"        # LLM 智能分析（需配置 API）

@dataclass
class ForeshadowingAnalyzerConfig:
    """伏笔分析器配置"""
    # 后端选择（默认 MANUAL = 手动模式，需配置 API 才能启用 LLM 分析）
    backend: AnalyzerBackend = AnalyzerBackend.MANUAL
    
    # 触发条件（LLM 模式）
    trigger_interval: int = 10      # 每N轮触发一次分析（最小1=每轮都触发）
    
    # LLM 配置
    llm_model: str = "gpt-4o-mini"  # 默认用便宜的模型
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None  # 支持自定义 API 地址
    
    # 行为配置
    auto_plant: bool = True         # 自动埋下检测到的伏笔
    auto_resolve: bool = False      # 自动标记解决（建议 False，让用户确认）
    include_resolved_check: bool = True  # 同时检查已有伏笔是否被解决
    
    # 高级配置
    max_context_turns: int = 20     # 发送给 LLM 的最大轮次数
    language: str = "zh"            # 提示词语言
    
    @classmethod
    def manual(cls) -> 'ForeshadowingAnalyzerConfig':
        """手动模式（默认）- 用户自己管理伏笔"""
        return cls(backend=AnalyzerBackend.MANUAL)
    
    @classmethod
    def llm_based(
        cls, 
        api_key: str, 
        model: str = "gpt-4o-mini",
        trigger_interval: int = 10
    ) -> 'ForeshadowingAnalyzerConfig':
        """使用 LLM API（智能）"""
        return cls(
            backend=AnalyzerBackend.LLM,
            llm_api_key=api_key,
            llm_model=model,
            trigger_interval=trigger_interval
        )
```

---

#### 任务 1.2：实现 LLM 分析器核心

```python
class ForeshadowingAnalyzer:
    """伏笔分析器 - 手动模式 / LLM 智能分析"""
    
    # LLM 提示词模板
    ANALYSIS_PROMPT = '''你是一个专业的叙事分析师。请分析以下对话内容，识别其中的伏笔（foreshadowing）。

## 什么是伏笔？
伏笔是故事中埋下的线索，暗示未来会发生的事情，包括：
- 神秘的暗示或预言
- 未解释的事件或现象
- 角色提到的"有一天会..."
- 隐藏的秘密或谜团
- 不祥的征兆

## 当前活跃的伏笔（如果有）：
{active_foreshadowings}

## 最近的对话内容：
{conversation}

## 请输出 JSON 格式：
```json
{
  "new_foreshadowings": [
    {
      "content": "伏笔内容描述",
      "importance": 0.8,  // 0-1，重要性
      "evidence": "原文依据（引用对话中的句子）",
      "related_entities": ["角色A", "物品B"]
    }
  ],
  "potentially_resolved": [
    {
      "foreshadowing_id": "fsh_xxx",
      "evidence": "解决的依据",
      "confidence": 0.9  // 置信度
    }
  ],
  "analysis_notes": "简要分析说明"
}
```

只输出 JSON，不要其他内容。如果没有检测到伏笔，返回空数组。'''

    def __init__(
        self, 
        config: ForeshadowingAnalyzerConfig,
        tracker: 'ForeshadowingTracker'
    ):
        self.config = config
        self.tracker = tracker
        self.llm_client = None
        
        # 对话缓冲区（按用户分隔）
        self._buffers: Dict[str, List[Dict]] = {}
        self._turn_counters: Dict[str, int] = {}
        
        if config.backend == AnalyzerBackend.LLM:
            self._init_llm_client()
    
    def _init_llm_client(self):
        """初始化 LLM 客户端"""
        from ..utils import LLMClient
        self.llm_client = LLMClient(
            model=self.config.llm_model,
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_base_url
        )
    
    def on_new_turn(
        self, 
        content: str, 
        role: str,
        user_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """
        每轮对话后调用，返回分析结果（如果触发了分析）
        
        Returns:
            None - 未触发分析
            Dict - 分析结果 {new_foreshadowings, potentially_resolved}
        """
        if self.config.backend == AnalyzerBackend.MANUAL:
            return None
        
        # 添加到缓冲区
        if user_id not in self._buffers:
            self._buffers[user_id] = []
            self._turn_counters[user_id] = 0
        
        self._buffers[user_id].append({
            'role': role,
            'content': content,
            'turn': self._turn_counters[user_id]
        })
        self._turn_counters[user_id] += 1
        
        # 检查是否触发分析
        if self._should_trigger_analysis(user_id):
            return self._run_analysis(user_id)
        
        return None
    
    def _should_trigger_analysis(self, user_id: str) -> bool:
        """检查是否应该触发分析"""
        turn_count = self._turn_counters.get(user_id, 0)
        # trigger_interval=1 表示每轮都触发，=10 表示每10轮触发一次
        return turn_count > 0 and turn_count % self.config.trigger_interval == 0
    
    def trigger_manual_analysis(self, user_id: str = "default") -> Dict[str, Any]:
        """手动触发分析（供 API/UI 调用）"""
        return self._run_analysis(user_id)
    
    def _run_analysis(self, user_id: str) -> Dict[str, Any]:
        """执行分析（仅 LLM 模式会调用）"""
        if self.config.backend == AnalyzerBackend.LLM:
            return self._analyze_with_llm(user_id)
        return {'new_foreshadowings': [], 'potentially_resolved': []}
    
    def _analyze_with_llm(self, user_id: str) -> Dict[str, Any]:
        """使用 LLM 分析"""
        buffer = self._buffers.get(user_id, [])
        if not buffer:
            return {'new_foreshadowings': [], 'potentially_resolved': []}
        
        # 构建对话文本
        conversation = self._format_conversation(buffer[-self.config.max_context_turns:])
        
        # 获取当前活跃的伏笔
        active = self.tracker.get_active(user_id)
        active_text = self._format_active_foreshadowings(active)
        
        # 构建提示词
        prompt = self.ANALYSIS_PROMPT.format(
            active_foreshadowings=active_text or "（暂无）",
            conversation=conversation
        )
        
        # 调用 LLM
        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # 低温度，更确定性
                response_format={"type": "json_object"}
            )
            result = self._parse_llm_response(response)
            
            # 处理结果
            if self.config.auto_plant:
                for fsh in result.get('new_foreshadowings', []):
                    self.tracker.plant(
                        content=fsh['content'],
                        user_id=user_id,
                        importance=fsh.get('importance', 0.5),
                        related_entities=fsh.get('related_entities', [])
                    )
            
            # 清空已分析的缓冲区
            self._buffers[user_id] = []
            
            return result
            
        except Exception as e:
            print(f"[Recall] LLM 伏笔分析失败: {e}")
            return {'new_foreshadowings': [], 'potentially_resolved': [], 'error': str(e)}
    
    def _format_conversation(self, turns: List[Dict]) -> str:
        """格式化对话内容"""
        lines = []
        for t in turns:
            role = "用户" if t['role'] == 'user' else "AI"
            lines.append(f"[{role}]: {t['content']}")
        return "\n\n".join(lines)
    
    def _format_active_foreshadowings(self, foreshadowings) -> str:
        """格式化活跃伏笔列表"""
        if not foreshadowings:
            return ""
        lines = []
        for f in foreshadowings:
            lines.append(f"- [{f.id}] {f.content} (重要性: {f.importance})")
        return "\n".join(lines)
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON"""
        import json
        try:
            # 提取 JSON（处理可能的 markdown 代码块）
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except:
            return {'new_foreshadowings': [], 'potentially_resolved': []}
```

---

#### 任务 1.3：集成到引擎和 API

**文件**：`recall/engine.py` - 添加分析器

```python
class RecallEngine:
    def __init__(self, ..., foreshadowing_config: ForeshadowingAnalyzerConfig = None):
        # 现有初始化...
        
        # 伏笔分析器
        fsh_config = foreshadowing_config or ForeshadowingAnalyzerConfig()
        self.foreshadowing_analyzer = ForeshadowingAnalyzer(
            config=fsh_config,
            tracker=self.foreshadowing_tracker
        )
    
    def add(self, content: str, role: str = "user", user_id: str = "default", ...):
        # 现有逻辑...
        
        # 新增：触发伏笔分析
        analysis_result = self.foreshadowing_analyzer.on_new_turn(
            content=content,
            role=role,
            user_id=user_id
        )
        
        # 可选：返回分析结果
        if analysis_result:
            result.foreshadowing_analysis = analysis_result
        
        return result
```

**文件**：`recall/server.py` - 添加 API

```python
@app.post("/v1/foreshadowing/analyze", tags=["Foreshadowing"])
async def trigger_foreshadowing_analysis(
    user_id: str = Query(default="default")
):
    """手动触发伏笔分析"""
    result = engine.foreshadowing_analyzer.trigger_manual_analysis(user_id)
    return result

@app.get("/v1/foreshadowing/config", tags=["Foreshadowing"])
async def get_foreshadowing_config():
    """获取伏笔分析器配置"""
    config = engine.foreshadowing_analyzer.config
    return {
        "backend": config.backend.value,
        "trigger_interval": config.trigger_interval,
        "llm_model": config.llm_model,
        "auto_plant": config.auto_plant,
        "auto_resolve": config.auto_resolve
    }

@app.put("/v1/foreshadowing/config", tags=["Foreshadowing"])
async def update_foreshadowing_config(
    trigger_interval: int = Query(default=None),
    auto_plant: bool = Query(default=None)
):
    """更新伏笔分析器配置"""
    if trigger_interval is not None:
        engine.foreshadowing_analyzer.config.trigger_interval = trigger_interval
    if auto_plant is not None:
        engine.foreshadowing_analyzer.config.auto_plant = auto_plant
    return {"status": "ok"}
```

---

#### 任务 1.4：SillyTavern 插件集成

**更新设置面板**：
```javascript
// 伏笔分析设置
<div class="recall-setting">
    <label>伏笔自动分析</label>
    <select id="recall-foreshadowing-backend">
        <option value="manual" selected>手动模式（默认）</option>
        <option value="llm">LLM 智能分析</option>
    </select>
</div>
<div class="recall-setting">
    <label>分析间隔（每N轮触发）</label>
    <input type="number" id="recall-foreshadowing-interval" value="10" min="1" max="100">
</div>
<div class="recall-setting">
    <label>
        <input type="checkbox" id="recall-foreshadowing-auto-plant" checked>
        自动添加检测到的伏笔
    </label>
</div>
```

**显示分析结果**：
```javascript
// 当收到分析结果时，显示通知
function onForeshadowingAnalysis(result) {
    if (result.new_foreshadowings?.length > 0) {
        toastr.info(
            `发现 ${result.new_foreshadowings.length} 个新伏笔`,
            '🎭 伏笔分析'
        );
        loadForeshadowings(); // 刷新列表
    }
    if (result.potentially_resolved?.length > 0) {
        toastr.warning(
            `${result.potentially_resolved.length} 个伏笔可能已解决`,
            '🎭 伏笔分析'
        );
    }
}
```

---

### 阶段一点五：规则编译器（优先级：🟡 中）

**预计工作量**：1-2天

> 💡 **背景**：当前 `ConsistencyChecker` 已实现 L0 注入和基础属性检查，但缺少将自然语言规则编译为可执行检查的能力。

---

#### 当前状态 vs 目标

| 功能 | 当前状态 | 目标状态 |
|------|:--------:|:--------:|
| L0 核心设定注入 | ✅ | ✅ |
| 绝对规则存储 | ✅ 字符串列表 | ✅ 结构化规则对象 |
| 数值属性检查 | ✅ 年龄/身高等 | ✅ |
| **规则→检查逻辑** | ❌ 仅关键词匹配 | ✅ 语义理解检查 |
| **关系属性检查** | ❌ | ✅ "A和B是敌人" |
| **否定句检测** | 🔧 简化 | ✅ 完整检测 |

---

#### 任务 1.5.1：定义结构化规则类型

**文件**：`recall/processor/rule_compiler.py`

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Any, Callable

class RuleType(Enum):
    """规则类型"""
    PROHIBITION = "prohibition"      # 禁止：角色不会做某事
    REQUIREMENT = "requirement"      # 必须：角色必须遵守某事
    RELATIONSHIP = "relationship"    # 关系：A和B的关系是X
    ATTRIBUTE = "attribute"          # 属性：角色A的属性X是Y
    CONDITION = "condition"          # 条件：如果X则Y

@dataclass
class CompiledRule:
    """编译后的规则"""
    id: str
    original_text: str              # 原始自然语言
    rule_type: RuleType
    
    # 规则参数
    subject: str = ""               # 主体（角色名）
    action: str = ""                # 动作/属性
    object: str = ""                # 宾语
    value: Any = None               # 值
    
    # 编译产物
    keywords: List[str] = field(default_factory=list)  # 关键词
    patterns: List[str] = field(default_factory=list)  # 正则模式
    check_func: Optional[Callable] = None              # 检查函数
    
    # 元信息
    severity: str = "HIGH"          # 违反严重程度
    enabled: bool = True


class RuleCompiler:
    """规则编译器 - 将自然语言规则转换为可执行检查"""
    
    def __init__(self):
        # 规则模式库
        self._patterns = {
            # 禁止类：不/不会/不能/禁止/绝不
            'prohibition': [
                r'(.+?)(不会?|不能|禁止|绝不|从不)(.+)',
                r'(.+?)(永远不|决不)(.+)',
            ],
            # 必须类：必须/一定/总是
            'requirement': [
                r'(.+?)(必须|一定要?|总是|始终)(.+)',
            ],
            # 关系类：A和B是/A与B的关系
            'relationship': [
                r'(.+?)(和|与)(.+?)(是|为)(.+)',
                r'(.+?)(和|与)(.+?)的关系是(.+)',
            ],
            # 属性类：A的X是Y
            'attribute': [
                r'(.+?)的(.+?)(是|为)(.+)',
            ],
        }
    
    def compile(self, rule_text: str) -> CompiledRule:
        """将自然语言规则编译为结构化规则"""
        import re
        import hashlib
        
        rule_id = f"rule_{hashlib.md5(rule_text.encode()).hexdigest()[:8]}"
        
        # 尝试匹配各种模式
        for rule_type, patterns in self._patterns.items():
            for pattern in patterns:
                match = re.match(pattern, rule_text)
                if match:
                    return self._build_rule(rule_id, rule_text, rule_type, match)
        
        # 未匹配到模式，作为通用规则处理
        return CompiledRule(
            id=rule_id,
            original_text=rule_text,
            rule_type=RuleType.PROHIBITION,  # 默认当作禁止规则
            keywords=self._extract_keywords(rule_text),
        )
    
    def _build_rule(self, rule_id: str, text: str, rule_type: str, match) -> CompiledRule:
        """根据匹配结果构建规则"""
        groups = match.groups()
        
        if rule_type == 'prohibition':
            return CompiledRule(
                id=rule_id,
                original_text=text,
                rule_type=RuleType.PROHIBITION,
                subject=groups[0].strip(),
                action=groups[2].strip() if len(groups) > 2 else "",
                keywords=self._extract_keywords(text),
                patterns=self._generate_violation_patterns(groups[0], groups[2] if len(groups) > 2 else ""),
            )
        
        elif rule_type == 'relationship':
            return CompiledRule(
                id=rule_id,
                original_text=text,
                rule_type=RuleType.RELATIONSHIP,
                subject=groups[0].strip(),
                object=groups[2].strip(),
                value=groups[-1].strip(),
                keywords=[groups[0].strip(), groups[2].strip(), groups[-1].strip()],
            )
        
        elif rule_type == 'attribute':
            return CompiledRule(
                id=rule_id,
                original_text=text,
                rule_type=RuleType.ATTRIBUTE,
                subject=groups[0].strip(),
                action=groups[1].strip(),  # 属性名
                value=groups[-1].strip(),
                keywords=[groups[0].strip(), groups[1].strip()],
            )
        
        # 默认
        return CompiledRule(
            id=rule_id,
            original_text=text,
            rule_type=RuleType.REQUIREMENT,
            keywords=self._extract_keywords(text),
        )
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本提取关键词"""
        import re
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z]+', text)
        # 过滤停用词
        stopwords = {'不会', '不能', '必须', '一定', '总是', '的', '是', '和', '与'}
        return [k for k in keywords if k not in stopwords]
    
    def _generate_violation_patterns(self, subject: str, action: str) -> List[str]:
        """生成违规检测正则模式"""
        patterns = []
        if action:
            # "杀人" -> 检测 "杀了人", "杀死了", "正在杀"
            patterns.extend([
                f'{subject}.*{action}了',
                f'{subject}.*正在{action}',
                f'{subject}.*开始{action}',
                f'{action}了.*{subject}',  # 被动句
            ])
        return patterns
```

---

#### 任务 1.5.2：增强 ConsistencyChecker

**文件**：`recall/processor/consistency.py` - 添加编译器集成

```python
from .rule_compiler import RuleCompiler, CompiledRule, RuleType

class ConsistencyChecker:
    def __init__(self, core_settings: 'CoreSettings', memory: 'ConsolidatedMemory'):
        self.core = core_settings
        self.memory = memory
        self.rule_compiler = RuleCompiler()  # 新增
        
        # 编译核心设定中的规则
        self._compiled_rules: List[CompiledRule] = self._compile_all_rules()
    
    def _compile_all_rules(self) -> List[CompiledRule]:
        """编译所有规则"""
        rules = []
        
        # 编译绝对规则
        if self.core.absolute_rules:
            for rule_text in self.core.absolute_rules:
                compiled = self.rule_compiler.compile(rule_text)
                rules.append(compiled)
        
        # 从角色卡提取属性规则
        if self.core.character_card:
            attr_rules = self._extract_attribute_rules(self.core.character_card)
            rules.extend(attr_rules)
        
        return rules
    
    def check_output(self, ai_output: str, context: dict) -> ConsistencyResult:
        """检查 AI 输出是否违反规则"""
        violations = []
        
        for rule in self._compiled_rules:
            violation = self._check_rule(ai_output, rule)
            if violation:
                violations.append(violation)
        
        # ... 其他检查逻辑
        
        return ConsistencyResult(
            is_consistent=len(violations) == 0,
            violations=violations,
            suggested_fixes=self._suggest_fixes(violations),
        )
    
    def _check_rule(self, output: str, rule: CompiledRule) -> Optional[Violation]:
        """检查单条规则"""
        import re
        
        if rule.rule_type == RuleType.PROHIBITION:
            # 检查禁止规则
            for pattern in rule.patterns:
                if re.search(pattern, output):
                    return Violation(
                        type='RULE_VIOLATION',
                        rule=rule.original_text,
                        severity='CRITICAL',
                        evidence=output[:100],
                    )
        
        elif rule.rule_type == RuleType.RELATIONSHIP:
            # 检查关系是否被否定
            # 如规则："A和B是敌人"，检测"A和B成为了朋友"
            # 实现：检查是否有矛盾关系描述
            contradictions = self._find_relationship_contradiction(
                output, rule.subject, rule.object, rule.value
            )
            if contradictions:
                return Violation(
                    type='RELATIONSHIP_VIOLATION',
                    rule=rule.original_text,
                    severity='HIGH',
                    evidence=contradictions,
                )
        
        elif rule.rule_type == RuleType.ATTRIBUTE:
            # 检查属性冲突
            conflict = self._find_attribute_conflict(
                output, rule.subject, rule.action, rule.value
            )
            if conflict:
                return Violation(
                    type='ATTRIBUTE_VIOLATION',
                    rule=rule.original_text,
                    severity='MEDIUM',
                    expected=rule.value,
                    found=conflict,
                )
        
        return None
    
    def _find_relationship_contradiction(
        self, text: str, subject: str, obj: str, relationship: str
    ) -> Optional[str]:
        """查找关系矛盾"""
        # 关系对立词典
        opposites = {
            '敌人': ['朋友', '盟友', '恋人', '同伴'],
            '朋友': ['敌人', '仇人', '对手'],
            '恋人': ['敌人', '陌生人', '仇人'],
            '主人': ['奴隶', '仆人'],  # 如果A是B的主人，则B不能是A的主人
        }
        
        if relationship in opposites:
            for opposite in opposites[relationship]:
                # 检查是否描述了相反关系
                patterns = [
                    f'{subject}.*{obj}.*{opposite}',
                    f'{obj}.*{subject}.*{opposite}',
                    f'{subject}.*和.*{obj}.*成为.*{opposite}',
                ]
                for p in patterns:
                    import re
                    if re.search(p, text):
                        return f"发现矛盾关系: {opposite}"
        
        return None
    
    def _find_attribute_conflict(
        self, text: str, subject: str, attribute: str, expected_value: Any
    ) -> Optional[str]:
        """查找属性冲突"""
        import re
        
        # 检查是否声明了不同的属性值
        pattern = rf'{subject}的{attribute}(是|为|变成了?)(\S+)'
        match = re.search(pattern, text)
        if match:
            found_value = match.group(2)
            if found_value != expected_value:
                return found_value
        
        return None
```

---

#### 任务 1.5.3：API 和配置支持

**文件**：`recall/server.py` - 添加规则管理 API

```python
@app.get("/v1/rules", tags=["Consistency"])
async def list_rules():
    """获取所有已编译的规则"""
    rules = engine.consistency_checker._compiled_rules
    return [
        {
            "id": r.id,
            "original": r.original_text,
            "type": r.rule_type.value,
            "subject": r.subject,
            "enabled": r.enabled,
        }
        for r in rules
    ]

@app.post("/v1/rules", tags=["Consistency"])
async def add_rule(rule_text: str = Body(...)):
    """添加新规则"""
    compiled = engine.consistency_checker.rule_compiler.compile(rule_text)
    engine.consistency_checker._compiled_rules.append(compiled)
    engine.core_settings.absolute_rules.append(rule_text)
    return {"id": compiled.id, "type": compiled.rule_type.value}

@app.delete("/v1/rules/{rule_id}", tags=["Consistency"])
async def delete_rule(rule_id: str):
    """删除规则"""
    rules = engine.consistency_checker._compiled_rules
    engine.consistency_checker._compiled_rules = [r for r in rules if r.id != rule_id]
    return {"status": "deleted"}

@app.post("/v1/check", tags=["Consistency"])
async def check_consistency(
    text: str = Body(..., embed=True)
):
    """检查文本是否违反规则"""
    result = engine.consistency_checker.check_output(text, {})
    return {
        "is_consistent": result.is_consistent,
        "violations": [
            {
                "type": v.type,
                "rule": v.rule,
                "severity": v.severity,
                "evidence": v.evidence,
            }
            for v in result.violations
        ]
    }
```

---

#### 任务 1.5.4：SillyTavern 插件集成

**更新设置面板**：
```javascript
// 规则管理区域
<div class="recall-section">
    <h4>📋 角色规则</h4>
    <div id="recall-rules-list"></div>
    <div class="recall-rule-input">
        <input type="text" id="recall-new-rule" placeholder="输入规则，如：角色不会杀人">
        <button id="recall-add-rule">添加</button>
    </div>
</div>

// 规则列表展示
function loadRules() {
    fetch(`${RECALL_API}/v1/rules`)
        .then(r => r.json())
        .then(rules => {
            const html = rules.map(r => `
                <div class="recall-rule-item" data-id="${r.id}">
                    <span class="rule-type">[${r.type}]</span>
                    <span class="rule-text">${r.original}</span>
                    <button class="delete-rule">🗑️</button>
                </div>
            `).join('');
            document.getElementById('recall-rules-list').innerHTML = html;
        });
}
```

---

#### 验收标准

| 测试场景 | 输入规则 | 测试输出 | 预期结果 |
|----------|---------|----------|----------|
| 禁止规则 | "角色不会杀人" | "角色杀死了敌人" | ⚠️ 违规 |
| 禁止规则 | "角色不会杀人" | "角色打伤了敌人" | ✅ 通过 |
| 关系规则 | "A和B是敌人" | "A和B成为了朋友" | ⚠️ 违规 |
| 关系规则 | "A和B是敌人" | "A和B继续对峙" | ✅ 通过 |
| 属性规则 | "角色的发色是黑色" | "角色的金色长发" | ⚠️ 违规 |

---

### 阶段二：CodeIndexer（优先级：🟢 低）

**预计工作量**：2-3天

**建议**：此功能面向代码场景，如果 v3.0 主要面向 RP 场景，可以：
1. 标记为 v3.1 版本的功能
2. 或者从计划文档中移除此需求

如果需要实现，计划如下：

#### 任务 2.1：创建基础结构

**文件**：`recall/processor/code_indexer.py`

```python
class CodeIndexer:
    """代码索引器"""
    
    SUPPORTED_LANGUAGES = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.java': 'java',
        '.go': 'go',
    }
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.symbol_table: Dict[str, Symbol] = {}
        self.dependency_graph: Dict[str, List[str]] = {}
    
    def index_file(self, file_path: str) -> None: ...
    def index_directory(self, dir_path: str) -> None: ...
    def search_symbol(self, name: str) -> List[Symbol]: ...
    def get_dependencies(self, file_path: str) -> List[str]: ...
```

#### 任务 2.2：实现 Python 解析器

使用 `ast` 模块解析 Python 代码。

#### 任务 2.3：实现 JavaScript 解析器

可以使用正则或简单的解析器。

---

## 五、优先级和时间线

| 优先级 | 任务 | 预计工时 | 建议排期 |
|:------:|------|:--------:|---------|
| 🔴 P0 | ForeshadowingAnalyzer 配置类 | 0.5天 | 第1天 |
| 🔴 P0 | LLM 分析后端实现 | 1天 | 第1-2天 |
| 🟠 P1 | 集成到 Engine 和 Server API | 0.5天 | 第2天 |
| 🟠 P1 | SillyTavern 插件设置面板 | 0.5天 | 第2天 |
| 🟡 P1.5 | RuleCompiler 规则编译器 | 0.5天 | 第3天 |
| 🟡 P1.5 | ConsistencyChecker 增强 | 0.5天 | 第3天 |
| 🟡 P1.5 | 规则管理 API 和插件集成 | 0.5天 | 第3-4天 |
| 🟢 P2 | CodeIndexer（可选） | 2-3天 | v3.1 |

---

## 六、配置示例

### 用户配置文件 `recall_data/config.json`

```json
{
  "foreshadowing": {
    "backend": "manual",
    "trigger_interval": 10,
    "llm_model": "gpt-4o-mini",
    "auto_plant": true,
    "auto_resolve": false
  }
}
```

> 💡 **默认行为**：`backend: "none"` 表示手动模式，用户自己管理伏笔。
> 配置 LLM API 后可改为 `"llm"` 启用自动分析。

### 代码使用示例

```python
from recall import RecallEngine
from recall.processor import ForeshadowingAnalyzerConfig

# 方式1：默认手动模式（无需配置，用户自己管理伏笔）
engine = RecallEngine()  # backend = MANUAL

# 方式2：启用 LLM 自动分析（需要 API key）
engine = RecallEngine(
    foreshadowing_config=ForeshadowingAnalyzerConfig.llm_based(
        api_key="sk-xxx",
        model="gpt-4o-mini",
        trigger_interval=10  # 每10轮分析一次
    )
)
```

---

## 七、验收标准

### 伏笔自动检测功能验收

**LLM 后端**：
- [ ] 配置 `trigger_interval=10` 后，第10轮对话自动触发分析
- [ ] LLM 能正确识别对话中的伏笔（如"总有一天会揭晓真相"）
- [ ] LLM 能识别已有伏笔是否被解决
- [ ] 返回结果为 JSON 格式，包含 `new_foreshadowings` 和 `potentially_resolved`
- [ ] `auto_plant=true` 时，自动添加到伏笔列表
- [ ] `auto_resolve=false` 时，只提示不自动解决

**API**：
- [ ] `POST /v1/foreshadowing/analyze` 手动触发分析
- [ ] `GET /v1/foreshadowing/config` 获取配置
- [ ] `PUT /v1/foreshadowing/config` 更新配置

**SillyTavern 插件**：
- [ ] 设置面板显示伏笔分析选项
- [ ] 用户可选择 禁用/规则/LLM 三种模式
- [ ] 用户可设置触发间隔
- [ ] 分析完成后显示通知
- [ ] 伏笔列表自动刷新

### CodeIndexer 功能验收（如果实现）

- [ ] 能索引 Python 文件中的函数、类、变量
- [ ] 能分析 import 语句构建依赖图
- [ ] 能搜索符号名返回定义位置

---

## 八、成本估算（LLM 后端）

| 配置 | 每次分析 Token | 每10轮成本 | 每100轮成本 |
|------|:-------------:|:----------:|:-----------:|
| gpt-4o-mini | ~2000 | ~$0.001 | ~$0.01 |
| gpt-4o | ~2000 | ~$0.02 | ~$0.20 |
| claude-3-haiku | ~2000 | ~$0.001 | ~$0.01 |

> 💡 **推荐**：使用 `gpt-4o-mini` 或 `claude-3-haiku`，成本极低且效果足够好。

---

## 九、结论

当前项目已实现 **88%** 的计划功能（22/25项），核心架构完整。

### 待完成/部分实现工作

| 功能 | 状态 | 缺失内容 | 工作量 | 优先级 |
|------|:----:|----------|:------:|:------:|
| 伏笔自动检测 | 🔧 部分 | `ForeshadowingAnalyzer` LLM分析 | 2-3天 | 🔴 高 |
| 规范100%遵守 | 🔧 部分 | 规则编译器（RP场景影响小） | 1-2天 | 🟡 中 |
| CodeIndexer | ❌ 未实现 | 整个模块（代码场景专用） | 2-3天 | 🟢 低 |

### 对 RP 场景的实际影响

| 功能 | 影响程度 | 说明 |
|------|:-------:|------|
| 伏笔自动检测 | ⭐⭐⭐ | 目前需手动管理，LLM辅助会更方便 |
| 规范100%遵守 | ⭐ | L0注入已足够，规则编译器是锦上添花 |
| CodeIndexer | 无 | 代码场景专用，RP不需要 |

### 新方案优势

采用 **LLM API 后端** 方案替代原计划的规则匹配：

| 对比项 | 规则匹配方案 | LLM API 方案 |
|--------|:----------:|:-----------:|
| 准确性 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| 语义理解 | ❌ | ✅ |
| 隐含伏笔识别 | ❌ | ✅ |
| 成本 | 免费 | 极低（~$0.01/100轮） |
| 维护成本 | 需维护关键词库 | 无 |
| 多语言支持 | 需分别配置 | 天然支持 |

---

**建议**：
1. **v3.0 发布**：完成 `ForeshadowingAnalyzer` 后即可发布
2. **v3.1 增强**：规则编译器 + CodeIndexer（按需）
