# 命名重构计划表

> 📅 创建日期：2026-01-24
> 📅 更新日期：2026-01-24（第六轮检查完成）⭐
> 🎯 目标：消除命名混淆，统一术语规范
> ✅ 状态：**验证完成，可执行**（共 25 个文件，~425 行修改）

---

## 📊 问题分析

### 当前存在的混淆命名

| 维度 | 当前命名 | 问题 |
|------|----------|------|
| 部署模式 | `lightweight` / `hybrid` / `full` | ⚠️ `hybrid` 与抽取模式冲突 |
| 抽取模式 | `LOCAL` / `HYBRID` / `LLM_FULL` | ⚠️ `HYBRID`/`LOCAL` 与其他冲突 |
| 检索策略 | `fast` / `default` / `accurate` | ✅ 无冲突 |
| 矛盾检测策略 | `RULE_ONLY` / `LLM_ONLY` / `HYBRID` / `AUTO` | ⚠️ `HYBRID` 与其他冲突 |
| 图谱后端 | `local` / `neo4j` / `falkordb` | ⚠️ `local` 与抽取模式冲突 |
| EmbeddingConfig 方法 | `hybrid_openai()` / `hybrid_siliconflow()` / `hybrid_custom()` | ⚠️ 方法名也含 `hybrid` |

**核心问题：**
1. `hybrid` 被使用了 **5 次**（部署模式、抽取模式、矛盾策略、EmbeddingConfig方法×3）
2. `local` 被使用了 2 次（抽取模式、图谱后端）
3. 用户无法区分哪个是哪个

---

## 🎯 重构方案

### 统一命名规范

| 维度 | 旧命名 | 新命名 | 说明 |
|------|--------|--------|------|
| **部署模式** | `lightweight` | `lite` | 更短更清晰 |
| | `hybrid` | `cloud` | 强调云API |
| | `full` | `local` | 保持（本地模型） |
| **抽取模式** | `LOCAL` | `RULES` | 基于规则抽取 |
| | `HYBRID` | `ADAPTIVE` | 表示自适应 |
| | `LLM_FULL` | `LLM` | 简化 |
| **检索策略** | `fast` | `fast` | **保持不变**（无冲突） |
| | `default` | `default` | **保持不变**（无冲突） |
| | `accurate` | `accurate` | **保持不变**（无冲突） |
| **矛盾策略** | `RULE_ONLY` | `RULE` | 简化 |
| | `LLM_ONLY` | `LLM` | 简化 |
| | `HYBRID` | `MIXED` | 避免冲突 |
| | `AUTO` | `AUTO` | 保持 |
| **图谱后端** | `local` | `file` | 强调文件存储 |
| | `neo4j` | `neo4j` | 保持 |
| | `falkordb` | `falkordb` | 保持 |
| **EmbeddingConfig方法** | `hybrid_openai()` | `cloud_openai()` | 与部署模式对应 |
| | `hybrid_siliconflow()` | `cloud_siliconflow()` | 与部署模式对应 |
| | `hybrid_custom()` | `cloud_custom()` | 与部署模式对应 |

### ⚠️ 审查修正说明

| 原计划 | 问题 | 修正 |
|--------|------|------|
| `full` → `offline` | 与抽取模式 `OFFLINE` 冲突 | 改为保持 `local`（本地模型） |
| `LOCAL` → `OFFLINE` | 与 `full→offline` 冲突 | 改为 `RULES`（基于规则） |
| 检索策略全改 | 本身无冲突，改了增加学习成本 | **保持不变** |
| 漏了 `base.py` | 这才是 `EmbeddingConfig` 定义位置 | 已补充 |
| 漏了 `__init__.py` 文件 | 模块导出也需要更新 | 已补充 |

---

## 📝 需要修改的文件清单

### ✅ 第一类：核心代码文件（Python）

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `recall/config.py` | `LightweightConfig` → `LiteConfig` | P0 |
| `recall/embedding/base.py` | `lightweight()` → `lite()`, `full()` → `local()`, `hybrid_*()` → `cloud_*()` | **P0** ⭐新增 |
| `recall/embedding/factory.py` | 调用 `EmbeddingConfig.lite()` + `local()` + `cloud_*()` | P0 |
| `recall/utils/budget_manager.py` | `suggest_degradation()` 返回值 `local/hybrid/full` → `lite/cloud/local`（对应部署模式） | **P1** ⭐新增 |
| `recall/index/vector_index.py` | 默认 backend 值 `'local'` - **保持**（EmbeddingBackendType.LOCAL 正确描述本地模型） | - |
| `recall/graph/temporal_knowledge_graph.py` | 参数 `backend: str = "local"` → `"file"`（图谱存储后端） | **P1** ⭐新增 |
| `recall/embedding/base.py` 中的 `EmbeddingBackendType.LOCAL` | **保持不变** - 这是嵌入后端类型，表示本地模型，命名正确 | - |
| `recall/processor/smart_extractor.py` | `ExtractionMode` 枚举值 + `SmartExtractorConfig` 方法名 | P0 |
| `recall/processor/__init__.py` | 导出 `ExtractionMode`（无需改，已正确导出） | - |
| `recall/retrieval/config.py` | **保持不变**（检索策略无冲突） | - |
| `recall/graph/contradiction_manager.py` | `DetectionStrategy` 枚举值 | P0 |
| `recall/graph/__init__.py` | 导出 `DetectionStrategy`（无需改，已正确导出） | - |
| `recall/engine.py` | 参数名 `lightweight` → `lite` + 策略映射 + API 响应保留 `lightweight` 字段兼容 | P0 |
| `recall/cli.py` | **无需修改** - 10处使用 `lightweight=True` 参数（后端会兼容旧参数名）+ 读取 `stats['lightweight']`（后端保留该字段） | - ⭐ |
| `recall/server.py` | API 文档 + 配置键名 + 注释 | P0 |

### ✅ 第二类：启动/安装脚本

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `install.ps1` | UI 显示文本 + `$InstallMode` 值 | P0 |
| `install.sh` | UI 显示文本 + `INSTALL_MODE` 值 | P0 |
| `start.ps1` | `install_mode` 文件读取 + 变量名 | P0 |
| `start.sh` | `install_mode` 文件读取 + 变量名 | P0 |
| `manage.ps1` | 模式检查逻辑 | P1 |
| `manage.sh` | 模式检查逻辑 | P1 |

### ✅ 第二类-B：项目配置文件 ⭐新增

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `pyproject.toml` | extras 名称 `lightweight→lite`, `hybrid→cloud`（保留旧名称作为别名） | **P0** ⭐ |

### ✅ 第三类：配置文件模板

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `recall/server.py` (get_default_config_content) | 配置文件模板 | P0 |
| `start.ps1` (默认配置生成) | 默认值 | P0 |
| `start.sh` (默认配置生成) | 默认值 | P0 |

### ✅ 第四类：测试文件

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `tests/test_stress.py` | `lightweight=True` → `lite=True` | P1 |
| `tests/test_phase2.py` | `lightweight=True` + `local_only()` → `rules_only()` | P1 |
| `tests/test_comprehensive.py` | `lightweight=True` + `EmbeddingConfig.*` 方法调用 | P1 |
| `tests/test_embedding_modes.py` | `EmbeddingConfig.lightweight()` → `lite()`, `hybrid_*()` → `cloud_*()` | P1 |
| `tests/test_growth_control.py` | `lightweight=True` | P1 |
| `tests/test.py` | `lightweight=True` | P1 |
| `tests/test_eleven_layer.py` | **无需修改**（检索策略保持不变） | - |
| `tests/test_retrieval_benchmark.py` | **无需修改**（检索策略保持不变） | - |

### ✅ 第五类：文档文件

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `README.md` | 模式说明表格 | P2 |
| `docs/plans/Recall-4.0-Upgrade-Plan.md` | 所有相关描述 | P2 |
| `docs/plans/CHECKLIST-REPORT.md` | 轻量模式引用 | P2 |

### ✅ 第六类：SillyTavern 插件 — **无需修改** ⭐

| 文件 | 说明 | 优先级 |
|------|------|--------|
| `plugins/sillytavern/index.js` | 使用 `stats.lightweight` 显示运行模式（后端 API 响应保留此字段，**无需修改插件**） | - |

---

## 🔄 迁移兼容性

### 向后兼容策略

1. **install_mode 文件**
   - 旧值 `lightweight` → 自动识别为 `lite`
   - 旧值 `hybrid` → 自动识别为 `cloud`
   - 旧值 `full` → **保持 `local` 识别**（未改名）

2. **环境变量（配置模板中）** ⭐说明
   - `SMART_EXTRACTOR_MODE` 目前**未被 Python 代码读取**（仅存在于配置模板）
   - 只需更新 `server.py` 中的配置模板默认值和注释
   - 无需在 Python 代码中添加兼容逻辑

3. **API 参数**
   - `config_preset=fast/default/accurate` → **保持不变**（无需兼容）

4. **RecallEngine 参数**
   - `lightweight=True` → 兼容识别，同时支持 `lite=True`

5. **EmbeddingConfig 方法**
   - `EmbeddingConfig.lightweight()` → 保留别名，同时支持 `lite()`
   - `EmbeddingConfig.full()` → 保留别名，同时支持 `local()` ⭐新增
   - `EmbeddingConfig.hybrid_*()` → 保留别名，同时支持 `cloud_*()`

6. **API 响应字段（/v1/stats）** ⭐新增
   - `stats.lightweight` → 保留用于旧插件兼容
   - 同时添加 `stats.lite` 字段（新插件使用）

7. **Enum 别名实现方案** ⭐新增
   - 使用 `_missing_()` 方法映射旧值到新值
   - 在类定义**后**创建别名属性（如 `ExtractionMode.LOCAL = ExtractionMode.RULES`）
   - 这样 `ExtractionMode.LOCAL` 和 `ExtractionMode("local")` 都能正常工作
   - 实现示例：
     ```python
     class ExtractionMode(str, Enum):
         RULES = "rules"
         ADAPTIVE = "adaptive"
         LLM = "llm"
         
         @classmethod
         def _missing_(cls, value):
             legacy_map = {'local': cls.RULES, 'hybrid': cls.ADAPTIVE}
             return legacy_map.get(value.lower())
     
     # 类定义后添加属性别名
     ExtractionMode.LOCAL = ExtractionMode.RULES
     ExtractionMode.HYBRID = ExtractionMode.ADAPTIVE
     ExtractionMode.LLM_FULL = ExtractionMode.LLM
     ```

8. **图谱后端参数（TemporalKnowledgeGraph）** ⭐新增
   - `backend="local"` → 在代码中兼容，自动映射到 `"file"`
   - 例如：`if backend == "local": backend = "file"`

9. **engine.py strategy_map 完整更新** ⭐新增
   - 当前的 DetectionStrategy 枚举值（不是成员名）已经是简化形式：`"rule"`/`"llm"`/`"hybrid"`
   - 需要更新的是**枚举成员名**：`RULE_ONLY`→`RULE`, `LLM_ONLY`→`LLM`, `HYBRID`→`MIXED`
   - strategy_map 需要兼容环境变量旧值，完整映射：
     ```python
     strategy_map = {
         'EMBEDDING': DetectionStrategy.MIXED,    # 兼容旧配置
         'LLM': DetectionStrategy.LLM,            # 新名称
         'LLM_ONLY': DetectionStrategy.LLM,       # 兼容旧值
         'HYBRID': DetectionStrategy.MIXED,       # 兼容旧值
         'MIXED': DetectionStrategy.MIXED,        # 新名称
         'RULE': DetectionStrategy.RULE,          # 新名称
         'RULE_ONLY': DetectionStrategy.RULE,     # 兼容旧值
         'AUTO': DetectionStrategy.AUTO,
     }
     ```

10. **pyproject.toml extras 别名** ⭐新增（第四轮检查发现）
    - 添加新名称作为旧名称的别名（保持旧名称不变）
    - 实现方式：
      ```toml
      [project.optional-dependencies]
      # 新名称（推荐使用）
      lite = []
      cloud = ["faiss-cpu>=1.7"]
      local = ["sentence-transformers>=2.2", "faiss-cpu>=1.7"]
      
      # 旧名称（向后兼容，指向新名称）
      lightweight = []  # 等同于 lite
      hybrid = ["faiss-cpu>=1.7"]  # 等同于 cloud
      full = ["sentence-transformers>=2.2", "faiss-cpu>=1.7"]  # 等同于 local
      ```

11. **RECALL_EMBEDDING_MODE 环境变量** ⭐新增（第六轮检查确认）
    - factory.py 支持的值：`none`, `custom`, `siliconflow`, `openai`, `local`
    - 其中 `local` 意味着"使用本地模型"，与新命名 `EmbeddingConfig.local()` 一致
    - **无需修改**，用户设置的 `RECALL_EMBEDDING_MODE=local` 仍然有效

12. **budget_manager.suggest_degradation()** ⭐新增（第六轮检查确认）
    - 返回值 `"local"/"hybrid"/"full"` 是部署模式的旧名称
    - **该方法未被任何代码调用**（仅定义未使用）
    - 为保持一致性，仍按计划更新为 `"lite"/"cloud"/"local"`

---

## 📋 执行步骤

### Phase A：核心代码修改

| 步骤 | 文件 | 具体修改 |
|------|------|----------|
| A1 | `recall/config.py` | 类名 `LightweightConfig` → `LiteConfig`，保留别名 |
| A2 | `recall/embedding/base.py` | 方法 `lightweight()` → `lite()`，`full()` → `local()`，`hybrid_*()` → `cloud_*()`，保留别名 |
| A3 | `recall/embedding/factory.py` | 调用改为新方法名（9处 `lightweight()`，3处 `full()`，8处 `hybrid_*()`）⭐修正统计 |
| A4 | `recall/processor/smart_extractor.py` | 枚举值 `LOCAL→RULES, HYBRID→ADAPTIVE, LLM_FULL→LLM` + 方法名，保留别名 |
| A5 | `recall/graph/contradiction_manager.py` | 枚举值 `RULE_ONLY→RULE, LLM_ONLY→LLM, HYBRID→MIXED`，保留别名 |
| A6 | `recall/utils/budget_manager.py` | `suggest_degradation()` 返回值 `local/hybrid/full` → `lite/cloud/local` ⭐ |
| A7 | `recall/graph/temporal_knowledge_graph.py` | 参数默认值 `backend="local"` → `"file"` + **兼容旧值 `"local"`** ⭐ |
| A8 | `recall/engine.py` | 参数 `lightweight→lite` + **strategy_map 更新**（添加 `'MIXED': DetectionStrategy.MIXED`, 修改 `'HYBRID'` 映射到 `MIXED`）+ API响应添加 `lite` 字段（同时保留 `lightweight`）+ 注释更新（`Hybrid模式` → `Cloud模式`） |
| A9 | `recall/server.py` | 配置键、文档字符串、注释、配置模板更新 |
| A10 | `pyproject.toml` | extras 别名：`lite = lightweight`, `cloud = hybrid`（保留旧名称，添加新名称别名）⭐新增 |

### Phase B：脚本文件修改

| 步骤 | 文件 | 具体修改 |
|------|------|----------|
| B1 | `install.ps1` | UI 文本 + `$InstallMode` 值 + `$extras = "[cloud]"` + 兼容旧值 |
| B2 | `install.sh` | UI 文本 + `INSTALL_MODE` 值 + `EXTRAS="[cloud]"` + 兼容旧值 |
| B3 | `start.ps1` | 模式识别逻辑 + 兼容旧值 |
| B4 | `start.sh` | 模式识别逻辑 + 兼容旧值 |
| B5 | `manage.ps1` | 模式检查逻辑 |
| B6 | `manage.sh` | 模式检查逻辑 |

### Phase C：测试文件修改

| 步骤 | 文件 | 具体修改 |
|------|------|----------|
| C1 | `tests/test_stress.py` | 5处 `lightweight=True` → `lite=True` |
| C2 | `tests/test_phase2.py` | 2处 `lightweight=True`, 1处 `local_only()` → `rules_only()` |
| C3 | `tests/test_comprehensive.py` | 2处 `lightweight`, 多处 `hybrid_*()` → `cloud_*()` |
| C4 | `tests/test_embedding_modes.py` | 4处 `lightweight`, 1处 `full()` → `local()`, 4处 `hybrid_*()` |
| C5 | `tests/test_growth_control.py` | 1处 `lightweight=True` |
| C6 | `tests/test.py` | 1处 `lightweight=True` |

### Phase D：文档更新

| 步骤 | 文件 | 具体修改 |
|------|------|----------|
| D1 | `README.md` | 更新模式说明表格 |
| D2 | `docs/plans/Recall-4.0-Upgrade-Plan.md` | 更新所有引用（大量） |
| D3 | `docs/plans/CHECKLIST-REPORT.md` | 更新引用 |

### Phase E：验证

| 步骤 | 操作 |
|------|------|
| E1 | 运行 `pytest tests/` 确保所有测试通过 |
| E2 | 检查 `python -m recall --help` 正常工作 |
| E3 | 检查启动脚本 `start.ps1` / `start.sh` 正常工作 |
| E4 | 检查旧配置文件兼容性 |
| E5 | 检查 `pip install -e ".[cloud]"` 和 `pip install -e ".[hybrid]"` 都能工作 |

---

## 📊 修改统计预估

| 类别 | 文件数 | 预估修改行数 |
|------|--------|-------------|
| 核心代码 | 10 | ~230 行（含 pyproject.toml，factory.py 修正）⭐ |
| 脚本文件 | 6 | ~100 行 |
| 测试文件 | 6 | ~45 行 |
| 文档文件 | 3 | ~50 行 |
| 插件 | 0 | 0 行（无需修改）⭐ |
| **合计** | **25** | **~425 行** |

---

## ✅ 最终命名对照表

### 部署模式（安装时选择）

| 旧值 | 新值 | UI 显示 | pip extras | 说明 |
|------|------|---------|------------|------|
| `lightweight` | `lite` | Lite Mode | `[lite]` | ~100MB，仅关键词 |
| `hybrid` | `cloud` | Cloud Mode | `[cloud]` | ~150MB，云API向量 |
| `full` | `local` | Local Mode | `[local]` | ~1.5GB，本地模型 |

### 抽取模式（SMART_EXTRACTOR_MODE）

| 旧值 | 新值 | 说明 |
|------|------|------|
| `local` | `rules` | 纯规则 spaCy/jieba |
| `hybrid` | `adaptive` | 自适应（规则+LLM） |
| `llm` | `llm` | 纯 LLM |

### 检索策略（config_preset）— **保持不变**

| 值 | 说明 |
|----|------|
| `fast` | L1-L7 |
| `default` | L1-L9 |
| `accurate` | L1-L11 |

### 矛盾检测策略（CONTRADICTION_DETECTION_STRATEGY）

> **注意**：当前枚举**值**已经是简化形式（`"rule"`/`"llm"`/`"hybrid"`），只需改 `"hybrid"`→`"mixed"`

| 旧成员名 | 新成员名 | 值变化 | 说明 |
|----------|----------|--------|------|
| `RULE_ONLY` | `RULE` | `"rule"` → 保持 | 仅规则 |
| `LLM_ONLY` | `LLM` | `"llm"` → 保持 | 仅 LLM |
| `HYBRID` | `MIXED` | `"hybrid"` → `"mixed"` | 规则+LLM |
| `AUTO` | `AUTO` | `"auto"` → 保持 | 自动 |

### 图谱后端（TEMPORAL_GRAPH_BACKEND）

| 旧值 | 新值 | 说明 |
|------|------|------|
| `local` | `file` | 本地 JSON 文件 |
| `neo4j` | `neo4j` | Neo4j 数据库 |
| `falkordb` | `falkordb` | FalkorDB |

### EmbeddingConfig 方法

| 旧方法名 | 新方法名 | 说明 |
|----------|----------|------|
| `lightweight()` | `lite()` | 禁用向量索引 |
| `full()` | `local()` | 本地模型（完整模式）⭐新增 |
| `hybrid_openai()` | `cloud_openai()` | OpenAI API |
| `hybrid_siliconflow()` | `cloud_siliconflow()` | 硅基流动 API |
| `hybrid_custom()` | `cloud_custom()` | 自定义 API |

### SmartExtractorConfig 方法

| 旧方法名 | 新方法名 | 说明 |
|----------|----------|------|
| `local_only()` | `rules_only()` | 纯规则模式 |
| `hybrid()` | `adaptive()` | 自适应模式 |
| `llm_full()` | `llm()` | 纯 LLM 模式 |

---

## ⚠️ 风险点

1. **现有用户配置文件** - 需要兼容旧值
2. **install_mode 文件** - 需要兼容旧值映射
3. **API 请求参数** - ~~需要兼容旧值~~ 检索策略保持不变，无需兼容
4. **文档一致性** - 确保所有文档同步更新
5. **第三方集成** - 确保 SillyTavern 插件正常工作

---

## 🎯 成功标准

- [ ] 所有 21 个测试通过
- [ ] 旧配置文件能正常工作（`lightweight`/`hybrid`/`full` 仍可识别）
- [ ] 新安装使用新命名（`lite`/`cloud`/`local`）
- [ ] EmbeddingConfig 旧方法名仍可使用（别名）
- [ ] 文档全部更新

---

## 📌 与原计划的差异汇总

| 原计划 | 修正后 | 原因 |
|--------|--------|------|
| `full` → `offline` | 保持 `local` | 避免与抽取模式冲突 |
| `LOCAL` → `OFFLINE` | `LOCAL` → `RULES` | 更准确描述功能 |
| 检索策略全部改名 | **保持不变** | 本身无冲突，改了增加成本 |
| 漏了 `base.py` | 已补充 | `EmbeddingConfig` 定义在此 |
| 漏了 `hybrid_*()` 方法 | 已补充 → `cloud_*()` | 方法名也含 hybrid |
| 漏了 `full()` 方法 | 已补充 → `local()` | 5处使用需要兼容 ⭐ |
| 测试文件数 8 | 修正为 6 | 2 个测试无需修改 |
| `budget_manager` 返回值 | 改为 `lite/cloud/local` | 与部署模式对应，非抽取模式 ⭐ |
| 漏了 API 响应兼容 | 保留 `stats.lightweight` 字段 | 避免破坏旧插件 ⭐ |
| 漏了 `cli.py` 说明 | 无需修改（后端兼容） | 10处使用旧参数名 ⭐ |
| 漏了图谱后端兼容 | `backend="local"` 映射到 `"file"` | 需要兼容旧值 ⭐ |
| `SMART_EXTRACTOR_MODE` 环境变量 | 只更新配置模板 | Python 代码未读取该变量 ⭐ |
| SillyTavern 插件需修改 | **无需修改**（后端保留 `stats.lightweight` 字段） | 第三轮检查发现 ⭐ |
| `engine.py` strategy_map | 需明确更新（完整映射见兼容策略#9） | 第三轮检查补充 ⭐ |
| `DetectionStrategy` 枚举值 | 当前值已是简化形式（`"rule"`/`"llm"`），只需改 `"hybrid"`→`"mixed"` | 第三轮检查澄清 ⭐ |
| 漏了 `pyproject.toml` | 需添加新 extras 名称 `lite`/`cloud`/`local`，保留旧名称 | **第四轮检查发现** ⭐ |
