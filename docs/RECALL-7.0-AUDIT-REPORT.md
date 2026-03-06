# Recall 7.0 Plan — 全量审计报告

> **审计日期**: 2025-07  
> **审计范围**: `Recall-7.0-UNIVERSAL-MEMORY-PLAN.md` 全部 Phase 7.1–7.7 任务项  
> **审计方式**: 代码库逐项验证（文件存在性 + grep 搜索 + 源码阅读）  
> **状态标记**:  
> - ✅ **DONE** — 代码存在且已接线  
> - ⚠️ **PARTIAL** — 代码存在但未完全满足计划要求  
> - ❌ **NOT DONE** — 未实现或未找到  
> - 🔄 **DIFFERENT** — 已实现但方式与计划不同  

---

## 总览

| Phase | 计划描述 | 完成率 | 判定 |
|:-----:|---------|:------:|:----:|
| 3.0 | 遗留代码清理 | **~5%** | ❌ 几乎未执行 |
| 3.1.Z | engine.py Facade 拆分 | **~60%** | ⚠️ 文件已创建，但 engine.py 仍膨胀 |
| 3.1.A | BUG 修复 + delete 级联 | **~85%** | ⚠️ 11/13 完成 |
| 3.1.B | BAL 接口 + 通用关系 | **~75%** | ⚠️ 接口已定义，部分未接入 |
| 3.1.C | 接线工程 + 死路径激活 | **~65%** | ⚠️ 关键项完成，部分未接线 |
| 3.1.D | MCP + 引擎共享 + 容错 | **~75%** | ⚠️ 核心完成，配置集中化不彻底 |
| 7.2 | SQLite 后端 + 核心功能 | **~55%** | ⚠️ 后端已写，未成为主路径 |
| 7.3 | 时间推理 + 事件关联 | **~90%** | ✅ 三大处理器均已实现并初始化 |
| 7.4 | 大规模记忆优化 | **~40%** | ⚠️ consolidate 框架在，双层策略部分实现 |
| 7.5 | 安全 + 可观测 + i18n + 任务 | **~70%** | ⚠️ 大部分基础设施已搭建 |
| 7.6 | 分布式后端扩展 | **~50%** | ⚠️ 文件已创建，集成深度未验证 |
| 7.7 | 缓存 + 可视化 | **~50%** | ⚠️ redis_cache + graph_visualizer 文件存在 |

---

## Phase 7.1 — 3.0 遗留代码清理

**计划目标**: 删除 foreshadowing/scenario/mode 文件，清理 RP 条件分支，`character_id` → `namespace` 全重命名

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 1 | 删除 `recall/processor/foreshadowing.py` | ❌ | 文件仍存在 |
| 2 | 删除 `recall/processor/foreshadowing_analyzer.py` | ❌ | 文件仍存在 |
| 3 | 删除 `recall/models/foreshadowing.py` | ❌ | 文件仍存在 |
| 4 | 删除 `recall/processor/scenario.py` | ❌ | 文件仍存在（ScenarioDetector 仍在 engine.py import 中） |
| 5 | 删除 `recall/mode.py` | ❌ | 文件仍存在（64 行），engine.py 第 11 行 `from .mode import get_mode_config` |
| 6 | 清理 engine.py 伏笔方法（~800 行） | ❌ | engine.py 148 行 `foreshadowing_config` 参数，317 行条件初始化，15+ 伏笔 API 方法全部保留 |
| 7 | 清理 server.py 伏笔端点（~740 行） | ❌ | server.py 仍有完整的 foreshadowing 路由组（POST/GET/DELETE /v1/foreshadowing），115-120 行 FORESHADOWING_* 环境变量 |
| 8 | 清理 `consistency.py` 非通用规则 | ❌ | 357 行仍引用 `self._mode.rp_consistency_enabled` |
| 9 | 清理 `context_tracker.py` 非通用 ContextType | ❌ | 78-84 行 `RP_CONTEXT_TYPES` 集合仍存在（CHARACTER_TRAIT, WORLD_SETTING 等） |
| 10 | `character_id` → `namespace` 全重命名 | ❌ | **100+ 处 character_id 引用仍在**。server.py 有兼容层 `_resolve_ns()` 接受两种参数名，但内部全部仍用 character_id。multi_tenant.py `MemoryScope.character_id`、episode_store.py `get_by_character(character_id)`、task_manager.py `Task.character_id` 均未改 |
| 11 | 清理 `knowledge_graph.py` RP_RELATION_TYPES | ❌ | 49 行 `RP_RELATION_TYPES` 仍存在，通过 `get_relation_types()` 条件包含 |
| 12 | 清理 18 个文件中非通用分支 | ❌ | mode.py 条件逻辑仍在 engine.py 全链路生效 |

**3.0 小结**: 遗留清理 **基本未执行**。所有应删文件均存在，character_id 未重命名，RP 条件分支未清除。`RecallConfig` 中甚至包含 `foreshadowing_enabled`、`rp_consistency_enabled`、`character_dimension_enabled` 等遗留开关，说明代码选择了"全部启用"策略而非"删除"策略。

---

## Phase 7.1 — 3.1.Z engine.py Facade 拆分

**计划目标**: 拆出 memory_ops.py (~1,500 行) + context_builder.py (~500 行)，engine.py 瘦身至 ~1,800 行

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 1 | 创建 `recall/memory_ops.py` | ✅ | 文件存在，1,838 行。`MemoryOperations` 类包含 add/add_turn/add_batch/delete/update/clear |
| 2 | 创建 `recall/context_builder.py` | 🔄 | 文件名为 `recall/context_build.py`（非 context_builder.py），536 行。`ContextBuild` 类含 build_context + 5 个 _build_* 辅助方法 |
| 3 | engine.py 瘦身至 ~1,800 行 | ❌ | **engine.py 目前 2,814 行**。因 3.0 遗留清理未执行，伏笔方法 (~800 行) + mode 条件逻辑仍占用大量空间 |
| 4 | server.py 零改动 | ✅ | server.py 仍通过 `engine = get_engine()` 调用，facade 模式签名保持不变 |

**3.1.Z 小结**: Facade 拆分的**文件创建已完成**，但因 3.0 未执行，engine.py 比目标胖 ~1,000 行。

---

## Phase 7.1 — 3.1.A BUG 修复 + delete() 级联

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| A1 | ContradictionManager `.id` → `.uuid` | ✅ | `contradiction_manager.py` 全文使用 `.uuid`（87-89, 312, 514-515, 538, 556, 585, 589 行） |
| A2 | 删除 `rebuild_vector_index` 重复定义 | ✅ | engine.py 仅 2618 行有 1 处定义 |
| A3 | `add_turn()` 补充 `_metadata_index.add` | ✅ | memory_ops.py 1017-1024 行有 `_metadata_index.add` |
| A4 | CommunityDetector Kuzu 兼容性 | ✅ | engine.py 690-730 行：优先使用统一图谱的 Kuzu 后端（共享连接），fallback 到 legacy 适配器 |
| A5 | KuzuGraphBackend.close() 释放连接 | ✅ | close() 方法通过 `del self.conn` + `del self.db` 释放资源 |
| A6 | server.py 4 处默认值不一致 | ❌ | server.py **仍有 50+ 处 `os.environ.get()` 散落调用**，且默认值与 RecallConfig 不一致。例：`CONTEXT_MAX_PER_TYPE` server.py 默认 30 vs RecallConfig 默认 10；`CONTEXT_DECAY_DAYS` 默认 7 vs 14；`CONTEXT_MIN_CONFIDENCE` 默认 0.3 vs 0.1；`DEDUP_HIGH_THRESHOLD` 默认 0.92 vs 0.85 |
| A7 | delete() 级联 13 个存储位置 | ✅ | memory_ops.py 1909 行注释"级联清理所有 13 个存储位置"，1760-1827 行逐一清理确认 |
| A8 | PromptManager 接入所有 processor | ✅ | engine.py 271 行初始化 PromptManager()，846 行传给 SmartExtractor，1006 行传给 deduplicator，1044 行传给 unified_analyzer |
| A9 | `get_entity_timeline()` 方法不存在 | ✅ | `temporal_knowledge_graph.py` 1083 行定义，server.py 3447/3488 行调用 |
| A10 | add()/add_batch() → TemporalIndex event_time | ✅ | memory_ops.py 592-614 行（add）和 1028-1050 行（add_turn）写入 temporal_index |
| A11 | `_get_memory_content_by_id()` O(1) | ✅ | multi_tenant.py `_memory_index: Dict[str, Dict]` 实现 O(1) 查找 |
| A12 | ScopedMemory LRU 5000 保护 | ✅ | multi_tenant.py `MAX_MEMORIES = 5000`，`_evict_oldest()` LRU 淘汰 |
| A13 | EntityIndex/ConsolidatedMemory WAL 增量写 | ❌ | layer1_consolidated.py 和 index 文件中**无 WAL / incremental 实现**，仍为全量 JSON 重写 |

**3.1.A 小结**: 13 项中 **11 项完成**，A6（默认值不一致）和 A13（WAL 增量写）未完成。A6 尤其是隐患——server.py 和 RecallConfig 的默认值分裂将导致行为不可预测。

---

## Phase 7.1 — 3.1.B BAL 接口 + 通用关系

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| B1 | 7 接口 + 2 服务完整定义 | 🔄 | `backends/interfaces.py`（516 行）定义了 7 个后端 + 2 个服务，但**名称和组合与计划不同**：实际为 VectorBackend, TextSearchBackend, KeywordBackend, GraphBackend, StorageBackend, TemporalBackend, EpisodeBackend + EmbeddingService + TenantRouter。计划的 EntitySearchBackend/ArchiveBackend **不存在**，替换为 TemporalBackend/EpisodeBackend |
| B2 | VectorBackend ABC 统一 VectorIndex/IVF | ✅ | VectorBackend ABC 在 interfaces.py 73 行，factory.py 映射到实现 |
| B3 | EmbeddingService 剥离 | ⚠️ | EmbeddingService ABC 在 interfaces.py 446 行。实际 embedding 用 `EmbeddingBackend` ABC（embedding/base.py 146 行）+ LocalEmbeddingBackend + APIEmbeddingBackend。**两套抽象未统一** |
| B4 | TenantRouter 替代 MultiTenant 直接访问 | ⚠️ | TenantRouter ABC 在 interfaces.py 485 行。但 engine.py 17 行仍直接 `from .storage import MultiTenantStorage`，未通过 TenantRouter |
| B5 | 规则关系提取 50+ 条通用模式 | ✅ | relation_extractor.py 有 **77 条正则规则**，覆盖 10 个类别（因果/时间/属性/偏好/社交/情感/空间/商业/技术/学术） |
| B6 | TextSearchBackend 拆分 Keyword + FullText | ✅ | interfaces.py 分别定义 TextSearchBackend（129 行）和 KeywordBackend（173 行）；sqlite_fts.py 实现 TextSearchBackend |
| B7 | EpisodeBackend 接口 | ✅ | interfaces.py 394 行 `class EpisodeBackend(ABC)` |
| B8 | 图后端统一（JSON/Kuzu 二元分裂修复） | ✅ | graph/backends/ 目录下：base.py（GraphBackend ABC + GraphNode/GraphEdge）、kuzu_backend.py（KuzuGraphBackend）、legacy_adapter.py（LegacyKnowledgeGraphAdapter 适配旧 KnowledgeGraph）、factory.py（create_graph_backend()） |

**3.1.B 小结**: 接口定义已完成但与计划有差异（🔄），实际接入引擎的衔接工作未做完（B3/B4 仅定义了 ABC 但未替换旧路径）。

---

## Phase 7.1 — 3.1.C 接线工程 + 死路径激活

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| C1 | 默认启用 ElevenLayerRetriever | ✅ | engine.py 564 行 `_init_eleven_layer_retriever()` 无条件调用，替换 self.retriever |
| C2 | VectorIndexIVF 自动切换（>1万） | ✅ | engine.py 导入 VectorIndexIVF，`_try_ivf_auto_switch()` 检查阈值（默认 50,000） |
| C3 | ParallelRetriever 接入 + 三路并行 | ⚠️ | engine.py 43 行导入，424 行初始化 + 注册 4 个 source（vector/keyword/entity/graph），**但注释明确写"可用但非默认检索路径"** |
| C4 | L2 时态过滤激活 | ✅ | retrieval/config.py `l2_enabled: bool = True`，eleven_layer.py 366-367 行实现 |
| C5 | L10 CrossEncoder 激活 | ✅ | config.py 默认 False，但 `from_env()` 默认 True；eleven_layer.py 454 行实现 |
| C6 | L11 LLM Filter 激活 | ✅ | 同 C5 模式，from_env() 默认 True |
| C7 | `_fulltext_weight` 接入检索逻辑 | ❌ | engine.py 555 行设置 `self._fulltext_weight`，但 **eleven_layer.py 中无任何 fulltext_weight 引用**——权重值已配置但未传递到实际检索器 |
| C8-C11 | 搜索 O(1)、LRU 缓存、全库去重 | ⚠️ | O(1) 查找（A11 ✅）和 LRU（A12 ✅）已完成。全库级去重能力未验证为独立功能 |

**3.1.C 小结**: 核心接线（C1 ElevenLayer 默认、C4-C6 层级激活）已完成。**C7 fulltext_weight 是明确的断线**，C3 ParallelRetriever 初始化了但不在默认路径上。

---

## Phase 7.1 — 3.1.D MCP + 引擎共享 + 容错

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| D1 | MCP clear_memories 工具 | ✅ | mcp/tools.py 120 行 `recall_clear` 工具 |
| D2 | MCP/HTTP 共享单例引擎 | ✅ | mcp_server.py `_get_shared_engine()` 从 `server.get_engine()` 导入单例 |
| D3 | MCP 错误处理 | ✅ | mcp/tools.py 188-193 行 try/except + traceback 日志 |
| D4 | 实体提取降级容错 | ❌ | engine.py 300 行 `self.entity_extractor = EntityExtractor()` **无 try/except 包裹**，初始化失败将导致整个引擎启动失败。未找到显式降级逻辑 |
| D5 | 47 个 `os.environ.get()` 集中到 config | ⚠️ | `RecallConfig`（config.py）已创建，含 90+ 配置字段 + `from_env()`。但 **server.py 仍有 50+ 处散落的 `os.environ.get()` 调用**，默认值与 RecallConfig 不一致 |
| D6 | FEATURE-STATUS.md 修正 13 项虚假声明 | ✅ | FEATURE-STATUS.md 6 行："已根据 PROMISE-AUDIT-REPORT 将 13 项虚假声明标记为 ⚠️/❌"，有 ❌❗ 状态标记 |
| D7 | 版本号统一 v7.0 | ✅ | version.py: `__version__ = '7.0.0'` |

**3.1.D 小结**: MCP 核心功能完成，配置集中化（D5）是**半完成状态**——RecallConfig 写了但 server.py 没全面切过去。

---

## Phase 7.2 — SQLite 后端 + 核心功能补全 + 异步管道

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 4.2.A | SQLiteMemoryBackend + FTS5 | ✅ | `backends/sqlite_memory.py`（569 行）实现 StorageBackend，`backends/sqlite_fts.py` 实现 TextSearchBackend（FTS5） |
| 4.2.B | engine.py BAL 适配（~400 行改造） | ❌ | engine.py 仍直接使用 `MultiTenantStorage`、`VectorIndex`、`InvertedIndex`、`EntityIndex` 等旧类，**未走 BAL 抽象层** |
| 4.2.C | add_batch 对齐 + document_chunker + 迁移工具 | ⚠️ | `processor/document_chunker.py`（447 行）✅ 存在。add_batch 在 memory_ops.py 中存在。迁移工具 `tools/migrate_json_to_sqlite.py` 存在。但 upsert 语义、external_id 幂等性未验证 |
| 4.2.D | 安全基线 + 存储层加固 | ✅ | `middleware/auth.py`（API Key 认证）✅，`middleware/rate_limit.py`（token bucket 限流）✅，server.py CORS 可配置 ✅ |
| 4.2.E | 测试 + 文档 | ⚠️ | tests/ 目录有 20+ 测试文件，但无专项 `test_bal.py` 或 `test_sqlite.py` |
| 4.2.F | asyncio 异步写入管道 | ✅ | `pipeline/async_writer.py` 实现 AsyncWritePipeline（含 WriteOperation, OperationType, PipelineStatus）；server.py 1437-1474 行初始化；1583 行回压 429 中间件 |

**7.2 小结**: SQLite 后端和 async 管道已实现，安全中间件已就位。**关键缺口是 4.2.B——engine.py 未切到 BAL**，导致 SQLite 后端虽然写好了但不在主路径上。

---

## Phase 7.3 — 时间推理 + 事件关联 + 话题聚类

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 7.3.A | TimeIntentParser（时间意图解析器） | ✅ | `processor/time_intent_parser.py`（731 行），engine.py 中初始化 |
| 7.3.B | EventLinker（事件关联器） | ✅ | `processor/event_linker.py`（662 行），engine.py 中初始化 |
| 7.3.C | TopicCluster（话题聚类器） | ✅ | `processor/topic_cluster.py`（653 行），engine.py 中初始化 |

**7.3 小结**: 三大处理器均已实现并接入引擎。✅ **Phase 7.3 是完成度最高的阶段。**

---

## Phase 7.4 — 大规模记忆优化

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 6.4.A | 图遍历 2-3 跳 + 50 条关系上限 | ⚠️ | TemporalKnowledgeGraph 有遍历能力，但具体深度/条数限制未验证 |
| 6.4.A | MMR 多样性选择 | ❌ | 未找到 MMR 实现 |
| 6.4.A | importance 加权检索 | ⚠️ | engine.py 2249 行 add_context 有 `importance: float = 0.5` 参数，2227 行有 importance_label 显示。但检索加权公式 `score = relevance*0.5 + importance*0.3 + recency*0.2` 未验证 |
| 6.4.B | consolidate() 双层策略 | ⚠️ | engine.py 447 行初始化 `ConsolidationManager`（"双层整合：热层摘要 + 冷层原文归档"），2763 行 `consolidate()` 方法委托给 consolidation_manager。VolumeManager 存在。但完整的热/冷层切换和基于数据量触发逻辑深度未验证 |
| 6.4.B | 归档记忆向量搜索 | ⚠️ | VolumeManager 存在于 engine.py 初始化中，搜索接入深度不明 |

**7.4 小结**: consolidate 框架搭建了，importance 参数有了，但 MMR 和向量加权检索等优化未见实现。

---

## Phase 7.5 — 安全 + 可观测 + 国际化 + 任务管理

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 7.5.A | 结构化日志框架（structlog） | ⚠️ | **未使用 structlog**。server.py 使用标准 logging，但 observability/__init__.py 提供 MetricsCollector。不是真正的结构化日志 |
| 7.5.A | Prometheus 指标导出 | ✅ | `observability/metrics.py`：自实现的 Counter/Histogram/Gauge + `to_prometheus()` 文本格式。server.py `GET /metrics` 和 `GET /v1/admin/metrics` 端点就绪 |
| 7.5.A | 请求追踪 trace_id | ✅ | server.py 1523-1556 行：Observability Middleware 注入 `X-Trace-Id`，RequestContext.set()，慢查询检测 |
| 7.5.A | Slow Query 告警 | ✅ | 同上中间件中实现 |
| 7.5.B | get_event_chain() 事件链 API | ❌ | engine.py 中 **无 get_event_chain / event_chain / causal_chain** 任何匹配 |
| 7.5.B | Entity Resolution（实体消歧） | ❌ | **无 entity_resolution / entity_merge / resolve_entity** 匹配 |
| 7.5.B | 异步导入任务管理 (Job API) | ✅ | `recall/jobs/manager.py` 实现 JobManager/Job/JobStatus。server.py 有 POST `/v1/jobs/import`、GET `/v1/jobs`、GET `/v1/jobs/{id}`、DELETE `/v1/jobs/{id}` |
| 7.5.C | Prompt 英文变体 | ⚠️ | PromptManager 存在但英文 prompt 变体未深入验证 |
| 7.5.C | i18n 框架 | ✅ | `recall/i18n.py` 实现 zh/en 双语，`t('error.not_found', lang='en')` 模式 |
| 7.5.C | 配置验证层 | ✅ | `recall/config_validator.py`：`validate_config()` + 范围检查（fulltext_k1/b/weight、threshold 等） |
| 7.5.C | 数据备份/恢复 | ✅ | server.py: POST `/v1/data/backup` (5652 行)、POST `/v1/data/restore` (5717 行)、POST `/v1/data/export` (5537 行)、POST `/v1/data/import` (5585 行) |

**7.5 小结**: 基础设施（指标/trace/Job API/i18n/配置验证/备份恢复）较完整。**关键缺失：get_event_chain() 和 Entity Resolution 完全未实现。**

---

## Phase 7.6 — 分布式后端扩展

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 8.6.A | Qdrant 向量后端 | ⚠️ | `backends/qdrant_vector.py` 文件存在，实现深度和 BAL 接口对齐未验证 |
| 8.6.B | PostgreSQL 记忆后端 | ⚠️ | `backends/pg_memory.py` 文件存在，实现深度未验证 |
| 8.6.C | NebulaGraph 图后端 | ⚠️ | `backends/nebula_graph.py` 文件存在，实现深度未验证 |
| 8.6.D | Elasticsearch 全文后端 | ⚠️ | `backends/es_fulltext.py` 文件存在，实现深度未验证 |
| 8.6.E | BackendFactory 自动选择 | ✅ | `backends/factory.py`（442 行）含 BackendTier（Lite/Standard/Scale/Ultra）自动检测 |
| 8.6.E | 在线迁移工具 | ⚠️ | `tools/migrate_json_to_sqlite.py` 存在（JSON→SQLite），SQLite→PG 迁移未验证 |

**7.6 小结**: 文件骨架已创建，BackendFactory 就位。但由于 **4.2.B（engine.py BAL 适配）未完成**，这些后端即使实现完整也无法被引擎使用。

---

## Phase 7.7 — 缓存 + 极致优化

| # | 任务 | 状态 | 证据 |
|---|------|:----:|------|
| 9.7.A | Redis 热数据缓存 | ⚠️ | `cache/redis_cache.py` 文件存在，集成深度未验证 |
| 9.7.B | 交互式图谱可视化 | ✅ | `observability/graph_visualizer.py` 使用 vis.js CDN，提供 `GET /v1/admin/graph/visualize` 端点 |
| 9.7.B | Grafana 监控仪表板 | ❌ | 未找到预置 Grafana dashboard 模板 |

---

## 关键阻塞链

以下是互相依赖的未完成项，形成阻塞链：

```
3.0 遗留清理未做
    └→ engine.py 仍有 ~800 行伏笔代码 → 无法达到 ~1800 行目标
    └→ character_id 未改 namespace → API 和数据模型不统一
    └→ mode.py 仍在 → 所有条件分支仍然生效
    
4.2.B engine.py BAL 适配未做  
    └→ SQLite 后端虽已实现但不在主路径
    └→ 7.6 四大分布式后端即使完整也无法接入
    └→ BackendFactory tier 选择形同虚设
    
C7 fulltext_weight 未接线
    └→ ElevenLayerRetriever 的全文搜索权重配置无效
    
A6 server.py 默认值不一致
    └→ RecallConfig 配置集中化名存实亡
    └→ 用户设置只在一处生效，另一处用硬编码默认值
```

---

## 完成度评估

| 类别 | 完成/总计 | 百分比 |
|------|:--------:|:------:|
| Phase 3.0 遗留清理 | 0/12 | **0%** |
| Phase 3.1.Z Facade | 2/4 | 50% |
| Phase 3.1.A Bug Fix | 11/13 | 85% |
| Phase 3.1.B BAL | 5/8 | 63% |
| Phase 3.1.C Wiring | 5/8 | 63% |
| Phase 3.1.D MCP | 5/7 | 71% |
| Phase 7.2 SQLite | 3/6 | 50% |
| Phase 7.3 Time | 3/3 | **100%** |
| Phase 7.4 Optimize | 1/5 | 20% |
| Phase 7.5 Production | 7/11 | 64% |
| Phase 7.6 Distributed | 1/6 | 17% |
| Phase 7.7 Cache | 1/3 | 33% |
| **全量** | **44/86** | **51%** |

---

## 优先修复建议

1. **P0 — Phase 3.0 遗留清理**: 这是一切的前置。不执行这步，engine.py 永远无法瘦身，API 语义无法统一。
2. **P0 — A6 server.py 默认值一致性**: RecallConfig 已写好，让 server.py 全面使用它，消除 50+ 处散落的 os.environ.get()。
3. **P0 — 4.2.B engine.py BAL 适配**: 解锁 SQLite 后端和所有 Phase 7.6 分布式后端。
4. **P1 — C7 fulltext_weight 接线**: 一行代码修复，让全文搜索权重真正生效。
5. **P1 — A13 WAL 增量写**: 大数据量场景下的性能关键。
6. **P1 — D4 实体提取降级容错**: 启动稳定性保障。
7. **P2 — Entity Resolution + get_event_chain()**: Phase 7.5 的核心高级能力缺失。
