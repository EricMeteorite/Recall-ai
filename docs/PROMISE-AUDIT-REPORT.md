# Recall 历史承诺 vs 7.0 计划覆盖度审计报告

> **审计日期**: 2026-02-24（R7修正: 2026-02-24；UNIVERSAL修正: 2026-02-24）  
> **审计范围**: 3.0 / 4.0 / 4.1 / 4.2 / 5.0 计划全部承诺 → v5.0 代码实现状态 → 7.0 计划覆盖度  
> **审计方法**: 逐文档提取承诺 → 代码验证 → 7.0 交叉比对  
> **R7修正**: 统计表与明细表不一致（X/Y/Z 原报 30/42/6，明细实际 25/46/7）；3 条 Y 标签错误（#29/#42/#61）；A/B/C 汇总偏差（原报 49/13/16，实际 49/14/15）；FEATURE-STATUS 虚假声明补充 6 项（总 13 项）  
> **UNIVERSAL修正**: 方向转变为纯通用记忆系统——移除 RP/热点/爬虫/多模态/推送。4 项承诺标记为 D（放弃）：#2/#28/#63/#64。8 项措辞修改：#1/#14/#26/#48/#62/#65/#66/#67。有效承诺 78→74；主覆盖口径改为 (X+Y)/74=87.8%，附加口径 (X+Y+M)/74=89.2%

---

## 一、状态图例

| v5.0 代码状态 | 含义 |
|:---:|------|
| **A** | 已实现且正常工作 |
| **B** | 代码存在但未接入/死路径 |
| **C** | 代码不存在 |

| 7.0 覆盖度 | 含义 |
|:---:|------|
| **X** | 明确提及并安排任务 |
| **Y** | 通过向后兼容或其他任务隐式覆盖 |
| **Z** | 未提及或推迟到"长期待办" |

---

## 二、完整承诺追踪表

### 2.1 来自 3.0 计划（§十二点五 "最终自查"表 + 环境隔离表 + 额外功能）

| # | 计划 | 承诺 | v5.0 状态 | 证据 | 7.0 覆盖 | 7.0 位置 |
|:---:|:---:|------|:---:|------|:---:|------|
| 1 | 3.0 | **上万轮对话** | A | VolumeManager 分卷存储存在可运行 | X | Phase 7.4 专项优化至 50,000 轮（UNIVERSAL: "RP"→"对话"） |
| 2 | 3.0 | ~~**伏笔不遗忘**~~ | A | ForeshadowingTracker + Analyzer 正常工作 | **D** | ❌ UNIVERSAL: 伏笔功能已移除，不再适用 |
| 3 | 3.0 | **几百万字规模** | A | VolumeManager 分卷架构 | X | Phase 7.2 SQLite 扩展至千万级 |
| 4 | 3.0 | **上千文件代码 (CodeIndexer)** | C | 无代码 | Z | 当前 7.0 文档未显式排期（后续 backlog） |
| 5 | 3.0 | **规范100%遵守 (RuleCompiler)** | B | L0 注入+一致性检查存在，RuleCompiler 不存在 | Z | 当前 7.0 文档未显式排期（后续 backlog） |
| 6 | 3.0 | **零配置即插即用** | A | pip install 可用 | Y | 向后兼容 |
| 7 | 3.0 | **100%不遗忘** | B | N-gram 兜底存在，但 IVF-HNSW 未接入，ParallelRetriever 死代码，三路并行未生效 | X | Phase 7.1.C1-C3 接线激活 |
| 8 | 3.0 | **面向大众友好** | A | ST 插件完整 | Y | 向后兼容 |
| 9 | 3.0 | **配置key就能用** | A | API key 机制正常 | Y | 向后兼容 |
| 10 | 3.0 | **pip install即插即用** | A | pyproject.toml 完整 | Y | 向后兼容 |
| 11 | 3.0 | **普通人无门槛** | A | 本地插件+用户API key | Y | 向后兼容 |
| 12 | 3.0 | **3-5秒响应** | A | 小规模下可达（Recall 部分 <1.5s） | X | Phase 7.4 目标 build_context <500ms |
| 13 | 3.0 | **知识图谱** | A | KnowledgeGraph + TemporalKnowledgeGraph 正常 | X | Phase 7.1.B8 统一图后端 |
| 14 | 3.0 | **多用户/多namespace** | A | MultiTenantStorage 正常 | Y | 向后兼容 + namespace 重命名（UNIVERSAL: "角色"→"namespace"） |
| 15 | 3.0 | **低配电脑支持 (~80MB)** | A | Lite 配置存在 | Y | 向后兼容 |
| 16 | 3.0 | **单一数据目录** | A | `./recall_data/` | Y | 向后兼容 |
| 17 | 3.0 | **模型隔离存储** | A | EnvironmentIsolation 类 | Y | 向后兼容 |
| 18 | 3.0 | **无系统级修改** | A | 符合 | Y | 向后兼容 |
| 19 | 3.0 | **环境变量隔离** | A | EnvironmentIsolation.setup() | Y | 向后兼容 |
| 20 | 3.0 | **完整卸载支持** | A | pip uninstall + 删目录 | Y | 向后兼容 |
| 21 | 3.0 | **虚拟环境兼容** | A | venv 支持 | Y | 向后兼容 |
| 22 | 3.0 | **不修改其他应用** | A | ST 插件独立 | Y | 向后兼容 |
| 23 | 3.0 | **离线运行支持** | A | 模型下载后可离线 | Y | 向后兼容 |
| 24 | 3.0 | **跨平台支持** | A | Win/Mac/Linux | Y | 向后兼容 |
| 25 | 3.0 | **配置文件隔离** | A | `./recall_data/config.json` | Y | 向后兼容 |
| 26 | 3.0 | **⭐ 持久条件系统（通用场景）** | A | ContextTracker 1918行 | Y | 向后兼容（UNIVERSAL: 保留通用条件逻辑，RP 专用 ContextType 移除） |
| 27 | 3.0 | **⭐ 配置热更新** | A | reload API 正常 | Y | 向后兼容 |
| 28 | 3.0 | ~~**⭐ 伏笔分析器增强**~~ | A | ForeshadowingAnalyzer 853行 | **D** | ❌ UNIVERSAL: 伏笔功能已移除，不再适用 |
| 29 | 3.0 | **FAISS mmap** | C | 未实现 | X | Phase 7.2 SQLite+BAL 明确替代（R7: Y→X）|
| 30 | 3.0 | **AsyncWritePipeline** | C | 未实现 | X | Phase 7.2.F asyncio.Queue |
| 31 | 3.0 | **AutoTuner** | C | 未实现 | Z | 当前 7.0 文档未显式排期（后续 backlog） |
| 32 | 3.0 | **mem0 兼容层** | C | 未实现 | Z | 当前 7.0 文档未显式排期（后续 backlog） |

### 2.2 来自 4.0 计划

| # | 计划 | 承诺 | v5.0 状态 | 证据 | 7.0 覆盖 | 7.0 位置 |
|:---:|:---:|------|:---:|------|:---:|------|
| 33 | 4.0 | **三时态模型 (T1/T2/T3)** | A | TemporalFact/UnifiedNode 在 models/temporal.py | Y | 向后兼容 |
| 34 | 4.0 | **可扩展节点类型** | A | NodeType 枚举可扩展 | Y | 向后兼容 |
| 35 | 4.0 | **三模式智能抽取 (三模式)** | A | SmartExtractor RULES/ADAPTIVE/LLM | Y | 向后兼容 |
| 36 | 4.0 | **Kuzu 图数据库后端** | A | KuzuGraphBackend 446行 | Y | 向后兼容 |
| 37 | 4.0 | **IVF-HNSW 95-99% 召回率** | B | VectorIndexIVF 581行完整实现, **engine.py 未 import** | X | Phase 7.1.C2 自动切换 IVF |
| 38 | 4.0 | **11层漏斗检索** | B | ElevenLayerRetriever 1361行, env 默认 true, 但 L2/L10/L11 为死路径 | X | Phase 7.1.C1 默认启用 + C4-C6 激活死路径 |
| 39 | 4.0 | **RRF 融合算法** | B | rrf_fusion.py ~105行存在，ElevenLayer 内部使用但 ParallelRetriever 未接入 | X | Phase 7.1.C3 接入 |
| 40 | 4.0 | **三路并行召回 + N-gram 兜底** | B | ParallelRetriever 228行，**全项目零引用** | X | Phase 7.1.C3 激活 |
| 41 | 4.0 | **社区检测** | A | CommunityDetector 369行 | Y | 向后兼容 |
| 42 | 4.0 | **查询规划器** | B | QueryPlanner 376行, `execute_bfs()` 从未被调用 | Z | execute_bfs()死路径, 7.0无激活计划（R7: Y→Z）|
| 43 | 4.0 | **矛盾检测管理器** | A | ContradictionManager 639行（有 .id→.uuid BUG） | X | Phase 7.1.A1 修复 BUG |
| 44 | 4.0 | **100% 向后兼容** | A | 基本满足 | Y | 7.0 继承此原则 |
| 45 | 4.0 | **亿级数据不遗漏** | C | 当前 JSON 全内存, <10万即瓶颈 | X | Phase 7.6 Qdrant+PG 千亿级 |
| 46 | 4.0 | **1-10亿扩展** | C | 无分布式后端 | X | Phase 7.6 Scale 后端 |
| 47 | 4.0 | **99.5%+ 召回率** | B | 三路召回架构设计完整但未激活 | X | Phase 7.1.C 激活后理论 ≥99% |
| 48 | 4.0 | **Phase 3.5 全部承诺（通用部分）** | B | 核心代码写好，未接入引擎 | X | Phase 7.1 明确"完成 3.5+3.6"（UNIVERSAL: 仅通用检索部分，RP 剥离） |
| 49 | 4.0 | **Phase 3.6 全部承诺** | B | IVF-HNSW + RRF + 并行召回代码存在，未接入 | X | Phase 7.1 明确"完成 3.5+3.6" |
| 50 | 4.0 | **双模型策略 (大+小 LLM)** | C | 未实现 | Z | 当前 7.0 文档未显式排期（后续 backlog） |

### 2.3 来自 4.1 计划

| # | 计划 | 承诺 | v5.0 状态 | 证据 | 7.0 覆盖 | 7.0 位置 |
|:---:|:---:|------|:---:|------|:---:|------|
| 51 | 4.1 | **T1: LLM 关系提取** | A | llm_relation_extractor.py ~390行 | Y | 向后兼容 |
| 52 | 4.1 | **T2: 关系时态信息** | A | valid_at/invalid_at 提取 | Y | 向后兼容 |
| 53 | 4.1 | **T3: 自定义实体 Schema** | A | EntitySchemaRegistry 219行, 7种内置 | Y | 向后兼容 |
| 54 | 4.1 | **T4: LLM 实体提取增强** | A | SmartExtractor 689行 | Y | 向后兼容 |
| 55 | 4.1 | **T5: Episode 模型** | A | EpisodicNode 在 temporal.py | Y | 向后兼容 |
| 56 | 4.1 | **T6: 实体摘要生成** | A | EntitySummarizer 180行 | Y | 向后兼容 |
| 57 | 4.1 | **T7: 全部集成** | A | 声明全部完成 | Y | 向后兼容 |

### 2.4 来自 4.2 计划

| # | 计划 | 承诺 | v5.0 状态 | 证据 | 7.0 覆盖 | 7.0 位置 |
|:---:|:---:|------|:---:|------|:---:|------|
| 58 | 4.2 | **Embedding 一次计算多处复用** | A | engine.py 中预计算逻辑 | Y | 向后兼容 |
| 59 | 4.2 | **统一分析器 (UnifiedAnalyzer)** | A | unified_analyzer.py 305行 | Y | 向后兼容 |
| 60 | 4.2 | **Turn API (add_turn)** | A | engine.py L2347 | Y | 向后兼容 |
| 61 | 4.2 | **40-60% 时间减少** | B | 架构存在，实际效果未验证 | X | Phase 7.4+7.7 明确性能优化（R7: Y→X）|

### 2.5 来自 5.0 计划

| # | 计划 | 承诺 | v5.0 状态 | 证据 | 7.0 覆盖 | 7.0 位置 |
|:---:|:---:|------|:---:|------|:---:|------|
| 62 | 5.0 | ~~**全局模式开关 (RP/通用/知识库)**~~ → **统一通用模式** | A→N/A | mode.py 将被删除 | **M** | UNIVERSAL: 不再需要模式切换，统一为通用模式 |
| 63 | 5.0 | ~~**伏笔条件化**~~ | A | `_mode.foreshadowing_enabled` 检查 | **D** | ❌ UNIVERSAL: 伏笔功能已移除，条件开关无意义 |
| 64 | 5.0 | ~~**character_id 条件化**~~ → **namespace 统一替代** | A | `_mode.character_dimension_enabled` 检查 | **D** | ❌ UNIVERSAL: character_id 重命名为 namespace，无需条件化 |
| 65 | 5.0 | **一致性检查器（通用化）** | A | `rp_consistency_enabled` 在 consistency.py L357 检查 | Y | 向后兼容（UNIVERSAL: 保留通用一致性逻辑，移除 RP 属性检测规则） |
| 66 | 5.0 | **关系类型通用化** | B | GENERAL_RELATION_TYPES 声明在计划中, 代码中 `rp_relation_types`/`rp_context_types` **从未被检查** | X | Phase 7.1.B5 直接替换为 50+ 通用规则（UNIVERSAL: RP 关系类型全部移除） |
| 67 | 5.0 | **MCP Server** | A | mcp_server.py + 11 个 MCP 工具 | X | Phase 7.1.D 补齐 clear 工具（UNIVERSAL: 移除伏笔 MCP 工具） |
| 68 | 5.0 | **TemporalIndex O(n) 修复** | C | 仍为 O(n) 全扫描 | X | Phase 7.3.A bisect 修正 |
| 69 | 5.0 | **InvertedIndex 全量 dump 修复** | C | 每次写仍全量 JSON dump | X | Phase 7.2 SQLite FTS5 替代 |
| 70 | 5.0 | **JSON 后端全量 dump 修复** | C | graph 每次写仍触发全量 save | X | Phase 7.2 SQLite 后端 |
| 71 | 5.0 | **批量写入 API (add_batch)** | B | 存在但功能远不及 add()：无去重/一致性/Episode/Archive | X | Phase 7.2.C 完整对齐 |
| 72 | 5.0 | **元数据索引** | A | MetadataIndex 存在并工作 | Y | 向后兼容 |
| 73 | 5.0 | **Prompt 工程系统化** | B | PromptManager ~1500行存在, **engine.py 零引用** → 100% 死代码 | X | Phase 7.1.A8 接入 |
| 74 | 5.0 | **多 LLM 提供商 (Anthropic/Gemini 原生 SDK)** | C | 仅 OpenAI 兼容 API, 无原生 SDK | Z | 仅 FEATURE-STATUS §3.4 "📋 中" |
| 75 | 5.0 | **重排序器多样性 (Cohere Rerank)** | C | 无专业重排序器 | Z | 仅 FEATURE-STATUS §3.4 "📋 低" |
| 76 | 5.0 | **CoreSettings 通用场景** | A | `general` 分支存在 | Y | 向后兼容 |
| 77 | 5.0 | **VolumeManager O(全磁盘) 修复** | C | 仍为逐行扫描 | X | Phase 7.4.B 搜索接入 |
| 78 | 5.0 | **通用关系类型 (因果/商业/金融)** | C | 仅 11 条中文 RP 正则 | X | Phase 7.1.B5 增加 50+ 通用规则 |

---

## 三、FEATURE-STATUS.md 虚假声明审计

| 功能 | 声称状态 | 实际状态 | 判定 |
|------|:-------:|:-------:|:----:|
| **向量索引 (IVF) ✅** | 已完成 | 代码 581 行完整，但 engine.py **未 import**，不可用 | ⚠️ 误导 |
| **并行多路召回 ✅** | 已完成 | ParallelRetriever 228 行完整，但 **全项目零引用** | ❌ 虚假 |
| **11层漏斗检索 ✅** | 已完成 | 默认 env=true，但 L2(时态)/L10(CrossEncoder)/L11(LLM Filter) 为死路径 | ⚠️ 部分误导 |
| **RRF 融合算法 ✅** | 已完成 | 代码存在，ElevenLayer 内部使用，但 ParallelRetriever 死路径 | ⚠️ 部分误导 |
| **consolidate() CLI** | 已完成 | 方法存在但内含 `# TODO: 实现实际的整合逻辑` | ❌ 虚假 |
| **delete() 级联** | 隐含已完成 | 仅清理 scope + MetadataIndex，**忽略 11/13 存储位置** | ❌ 严重虚假 |
| **100% 不遗忘保证** | ✅ 核心声明 | N-gram 兜底存在但三路并行未激活，IVF 未接入，实际无法保证 | ⚠️ 理论有但实际断路 |
| **temporal_index bisect 优化** | ✅ 已完成 | 声称 O(n)→O(log n+k)，实际仍为 O(n) 全扫描 | ❌ 虚假（R7补充）|
| **inverted_index WAL** | ✅ 已完成 | 声称追加写入+原子压缩，实际仍每次全量 JSON dump | ❌ 虚假（R7补充）|
| **json_backend 延迟保存** | ✅ 已完成 | 声称脏数据计数+atexit flush，实际 graph 每次写仍触发全量 save | ❌ 虚假（R7补充）|
| **volume_manager O(1) 索引** | ✅ 已完成 | 声称 O(1) 查找，实际仍为逐行扫描 | ❌ 虚假（R7补充）|
| **查询规划器 (QueryPlanner)** | ✅ 已完成 | 376行代码存在，但 execute_bfs() 从未被调用 | ❌ 虚假（R7补充）|
| **Cohere Rerank** | ✅ 已完成 | 声称使用 Cohere Rerank API，实际无专业重排序器代码 | ❌ 虚假（R7补充）|
---

## 四、统计汇总

### 4.1 按计划统计

| 计划 | 承诺总数 | v5.0 A (已实现) | v5.0 B (死路径) | v5.0 C (不存在) | v5.0 N/A |
|------|:------:|:-----------:|:----------:|:----------:|:-------:|
| 3.0 | 32 | 25 (78%) | 2 (6%) | 5 (16%) | 0 |
| 4.0 | 18 | 7 (39%) | 8 (44%) | 3 (17%) | 0 |
| 4.1 | 7 | 7 (100%) | 0 (0%) | 0 (0%) | 0 |
| 4.2 | 4 | 3 (75%) | 1 (25%) | 0 (0%) | 0 |
| 5.0 | 17 | 6 (35%) | 3 (18%) | 7 (41%) | 1 (#62 A→N/A) |
| **总计** | **78** | **48 (62%)** | **14 (18%)** | **15 (19%)** | **1 (1%)** |

### 4.2 7.0 覆盖度统计

| 7.0 覆盖 | 数量 | 占比 |
|:---:|:---:|:---:|
| **X** (明确安排) | 27 | 35% |
| **Y** (隐式覆盖/向后兼容) | 38 | 49% |
| **Z** (未提及/推迟) | 8 | 10% |
| **D** (UNIVERSAL方向放弃) | 4 | 5% |
| **M** (UNIVERSAL措辞修改) | 1 | 1% |
| **总计** | **78** | **100%** |

> **UNIVERSAL 注**: 4 项 D 类承诺（#2/#28/#63/#64）不再计入有效基数。有效承诺 74 项，主口径覆盖 **(X+Y)=65/74=87.8%**；若将 M 计入覆盖，则 **(X+Y+M)=66/74=89.2%**。

### 4.3 核心数字

| 指标 | 数值 |
|------|:----:|
| 3.0-5.0 计划总承诺数 | **78** |
| v5.0 已完全实现 (A) | **48** (62%) |
| v5.0 代码存在但断路 (B) | **14** (18%) |
| v5.0 代码不存在 (C) | **15** (19%) |
| v5.0 N/A（方向变更） | **1** (1%) |
| 7.0 明确覆盖 (X) | **27** |
| 7.0 隐式覆盖 (Y) | **38** |
| 7.0 **未覆盖 (Z)** | **8** |
| 7.0 覆盖率（主口径） | **87.8%** (65/74, 排除 4 项 D) |
| 7.0 覆盖率（含 M） | **89.2%** (66/74, 排除 4 项 D) |

---

## 五、7.0 未覆盖的承诺清单（8 项）

| # | 原始计划 | 承诺 | 未覆盖原因 | 风险 |
|:---:|:---:|------|------|:---:|
| 4 | 3.0 | **CodeIndexer (上千文件代码索引)** | 当前 7.0 文档未显式排期（后续 backlog） | 低 |
| 5 | 3.0 | **RuleCompiler (规则编译器)** | 当前 7.0 文档未显式排期（后续 backlog） | 低 |
| 31 | 3.0 | **AutoTuner (自动参数调优)** | 当前 7.0 文档未显式排期（后续 backlog） | 低 |
| 32 | 3.0 | **mem0 兼容层** | 当前 7.0 文档未显式排期（后续 backlog） | 低 |
| 42 | 4.0 | **查询规划器 (QueryPlanner execute_bfs)** | 代码存在但 execute_bfs() 死路径，7.0 无激活计划（R7新增）| 中 |
| 50 | 4.0 | **双模型策略 (大+小 LLM)** | 当前 7.0 文档未显式排期（后续 backlog） | 中 |
| 74 | 5.0 | **Anthropic/Gemini 原生 SDK** | FEATURE-STATUS §3.4 “📋 中” 但 7.0 无任务 | 中 |
| 75 | 5.0 | **Cohere Rerank 重排序器** | FEATURE-STATUS 声称 ✅ 但代码不存在，7.0 无任务（R7新增）| 中 |

> **注**：R7审计新增 2 项未覆盖：#42 QueryPlanner（原误标为 Y）、#75 Cohere Rerank（原未计入汇总）。

---

## 六、判定

### VERDICT: **PARTIALLY — 87.8%**（UNIVERSAL主口径：排除 4 项 RP 专属承诺后 65/74）

7.0-UNIVERSAL 计划覆盖了 3.0-5.0 计划中 **74 项有效承诺中的 65 项**（87.8% 主口径），其中 27 项明确安排任务，38 项通过向后兼容隐式保留。4 项 RP 专属承诺（#2 伏笔不遗忘、#28 伏笔分析器、#63 伏笔条件化、#64 character_id 条件化）因方向转变标记为 D（放弃）。若将 1 项 M（措辞修改）计入覆盖，则为 66/74（89.2%）。

**8 项未覆盖的承诺**：
- CodeIndexer / RuleCompiler / AutoTuner / mem0 兼容层 → 3.0 计划中已标记为 v3.1 或可选
- QueryPlanner execute_bfs() → 代码存在但死路径，7.0 无激活计划（R7 新增）
- 双模型策略 → 优化项，非核心
- Anthropic/Gemini 原生 SDK → 当前 OpenAI 兼容 API 可覆盖大部分场景
- Cohere Rerank → FEATURE-STATUS 声称 ✅ 但代码不存在（R7 新增）

### 关键发现

1. **7.0 最大贡献**：将 13 个 "死路径" (B 类) 承诺激活——这些是已写好但从未接入引擎的代码（IVF-HNSW、11层检索、ParallelRetriever、PromptManager、RRF 融合等）。这是 v5.0 最大的技术债。

2. **7.0 诚实度高**：计划开篇承认之前的评分只有 54.25/100，承认 Phase 3.5/3.6 "代码写好了但没接入引擎"，承认 delete() 只清理 2/13 存储位置。这种诚实态度确保了 7.0 能正确定位问题。

3. **FEATURE-STATUS.md 存在严重误导**：至少 8 项虚假声明（并行多路召回 ✅、consolidate ✅、temporal_index bisect ✅、inverted_index WAL ✅、json_backend 延迟保存 ✅、volume_manager O(1) ✅、QueryPlanner ✅、Cohere Rerank ✅）+ 5 项部分误导（IVF ✅、11层 ✅、RRF ✅、100%不遗忘 ✅、40-60%时间减少）。共计 **13 项**。7.0 计划 7.1.D6 任务已安排修正。

4. **推迟项合理**：6 项未覆盖的承诺中，没有任何一项影响核心记忆功能。它们要么是辅助优化（AutoTuner），要么是特定场景扩展（CodeIndexer），要么是生态兼容（mem0）。推迟决策可接受。

### 风险提示

- 7.0-UNIVERSAL 计划当前口径为 83 工作日 / AI 25-35 天，Phase 7.6-7.7 依赖外部分布式服务（Qdrant/PG/NebulaGraph/ES/Redis），实施风险较高
- ~~Phase 7.3.D 爬虫框架和 7.3.E 多模态处理~~ → UNIVERSAL 已删除
- 千亿级承诺（Phase 7.6）需要完整的分布式基础设施，对个人/小团队项目来说实际部署门槛很高
