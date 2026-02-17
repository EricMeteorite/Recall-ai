# Recall v5.0 功能状态总览

> **生成日期**: 2026-02-15  
> **当前版本**: v5.0.0  
> **定位**: 通用 AI 知识记忆系统（RP / 代码 / 企业 / Agent 全覆盖）

---

## 📊 状态图例

| 状态 | 含义 |
|:----:|------|
| ✅ | 已完成 - 功能完整可用 |
| 🔄 | 进行中 - 正在开发 |
| 📋 | 计划中 - 已规划但未开始 |
| ❌ | 不实现 - 设计决策不做 |

---

## 一、核心架构

### 1.1 设计原则

```
┌─────────────────────────────────────────────────────────────────┐
│                    Recall 核心设计原则                          │
├─────────────────────────────────────────────────────────────────┤
│  1. 零依赖优先 - 无需外部数据库，开箱即用                        │
│  2. 成本可控 - LLM 可选，本地优先                               │
│  3. 场景通用 - RP / 代码 / 企业 / Agent 全覆盖                  │
│  4. 100% 不遗忘 - 任何信息都可追溯                              │
│  5. 性能卓越 - 超越而非追赶竞品                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 部署模式

| 模式 | 内存占用 | 说明 | 状态 |
|------|----------|------|:----:|
| **Lite 模式** | ~80MB | 禁用向量检索，纯规则 | ✅ |
| **Cloud 模式** | ~100MB | 云端 API Embedding，最强质量 | ✅ |
| **Local 模式** | ~500MB | 本地嵌入模型，完整功能 | ✅ |
| **Enterprise 模式** | ~600MB | Kuzu + NetworkX，企业级性能 | ✅ |

---

## 二、功能模块状态

### 2.1 知识图谱系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **三时态知识图谱** | ✅ | `graph/temporal_knowledge_graph.py` | ~2137 | T1事实时间 + T2知识时间 + T3系统时间，超越 Graphiti 的双时态模型 |
| **基础知识图谱 (别名)** | ✅ | `graph/__init__.py` | - | `KnowledgeGraph = TemporalKnowledgeGraph`（v4.0 统一架构，向后兼容） |
| **Relation 数据模型** | ✅ | `graph/knowledge_graph.py` | ~271 | Relation 类 + 旧版 KnowledgeGraph 类（仅 Relation 被导出，供兼容使用） |
| **矛盾检测与管理** | ✅ | `graph/contradiction_manager.py` | ~639 | 四种检测策略（RULE/LLM/MIXED/AUTO），四种解决策略（SUPERSEDE/COEXIST/REJECT/MANUAL） |
| **关系抽取器** | ✅ | `graph/relation_extractor.py` | ~88 | 规则模式，11 个中文 + 3 个英文正则模式 + 共现检测 |
| **LLM关系抽取器** | ✅ | `graph/llm_relation_extractor.py` | ~390 | 三模式（RULES/ADAPTIVE/LLM），支持动态关系类型和时态信息 |
| **社区检测** | ✅ | `graph/community_detector.py` | ~369 | Louvain / Label Propagation / Connected Components |
| **查询规划器** | ✅ | `graph/query_planner.py` | ~376 | 图查询优化与执行计划，6 种 QueryOperation，LRU+TTL 路径缓存 |
| **图遍历查询** | ✅ | `graph/temporal_knowledge_graph.py` | - | BFS/DFS 图遍历，时态过滤，谓词过滤 |

**技术亮点**：
- 三时态模型比 Graphiti 多一层「知识时间」，可追踪"何时得知此事实"
- 零依赖本地存储，无需 Neo4j/FalkorDB
- 可选外部图数据库后端（backends/ 目录）
- **v4.0 统一架构**：`KnowledgeGraph` 和 `TemporalKnowledgeGraph` 共用同一实例，通过 `TEMPORAL_GRAPH_BACKEND` 配置存储后端（file/kuzu）

---

### 2.2 检索系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **11层漏斗检索** | ✅ | `retrieval/eleven_layer.py` | ~1310 | 完整 11 层架构，渐进式过滤 |
| **8层检索（兼容）** | ✅ | `retrieval/eight_layer.py` | ~710 | Phase 3.6 版本，向后兼容 |
| **RRF 融合算法** | ✅ | `retrieval/rrf_fusion.py` | ~105 | Reciprocal Rank Fusion |
| **并行多路召回** | ✅ | `retrieval/parallel_retrieval.py` | ~218 | 向量 + BM25 + 图谱并行 |
| **检索配置** | ✅ | `retrieval/config.py` | ~283 | 检索策略配置（fast/default/accurate） |
| **上下文构建器** | ✅ | `retrieval/context_builder.py` | ~219 | 上下文组装与格式化 |

**11层检索架构详解**：

```
┌─────────────────────────────────────────────────────────────┐
│                    11层漏斗检索架构                          │
├─────────────────────────────────────────────────────────────┤
│         【快速过滤阶段】                                     │
│  L1  │ Bloom Filter 快速否定 (O(1))                         │
│  L2  │ Temporal Filter 时间范围预筛选 (O(log n))            │
├──────┼──────────────────────────────────────────────────────┤
│         【多路召回阶段 - 并行三路召回】                       │
│  L3  │ Inverted Index 倒排索引召回 (~10ms, 100% 精确)       │
│  L4  │ Entity Index 实体关联查找 (O(1))                     │
│  L5  │ Graph Traversal BFS 图遍历扩展                       │
│  L6  │ N-gram Index 模糊匹配                                │
│  L7  │ Vector Coarse 向量粗筛 (ANN/IVF-HNSW)                │
├──────┼──────────────────────────────────────────────────────┤
│         【精排阶段】                                         │
│  L8  │ Vector Fine 向量精排（重计算余弦相似度）              │
│  L9  │ Rerank 多因素重排序（时间衰减 + 置信度 + 来源权重）   │
│ L10  │ Cross-Encoder 精排（可选，默认关闭）                  │
│ L11  │ LLM Filter 语义相关性判断（可选，默认关闭）           │
├──────┼──────────────────────────────────────────────────────┤
│         【兜底保证】                                         │
│      │ N-gram 原文兜底搜索（100% 不遗忘保证）                │
│      │ RRF 融合取并集（多路召回结果合并）                    │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.3 实体处理系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **基础实体抽取** | ✅ | `processor/entity_extractor.py` | ~332 | 6 种策略：已知词典 + spaCy NER + 中文专名 + 英文专有名词 + 混合词 + jieba 词性标注 |
| **智能实体抽取** | ✅ | `processor/smart_extractor.py` | ~689 | 三模式自适应（RULES/ADAPTIVE/LLM），复杂度评估，成本控制 |
| **三阶段去重** | ✅ | `processor/three_stage_deduplicator.py` | ~654 | 阶段1: MinHash+LSH, 阶段2: 语义相似度, 阶段3: 可选LLM |
| **统一分析器** | ✅ | `processor/unified_analyzer.py` | ~305 | v4.2 新增，一次 LLM 调用完成矛盾检测+关系提取+实体摘要 |
| **实体摘要生成** | ✅ | `processor/entity_summarizer.py` | ~180 | 简单规则模式 + LLM模式（事实>3条时），自动回退 |
| **记忆摘要器** | ✅ | `processor/memory_summarizer.py` | ~274 | 记忆压缩与摘要生成，优先级系统（CRITICAL/HIGH/NORMAL/LOW/EPHEMERAL） |
| **场景处理器** | ✅ | `processor/scenario.py` | ~220 | 7 种场景类型（ROLEPLAY/CODE_ASSIST/KNOWLEDGE_QA/CREATIVE/TASK/CHAT/UNKNOWN） |

**去重系统优势**：
- 比 Graphiti 多一层语义过滤（阶段2），减少 LLM 调用
- MinHash + LSH 实现 O(1) 候选筛选
- 可配置阈值：DEDUP_HIGH_THRESHOLD=0.85, DEDUP_LOW_THRESHOLD=0.70
- v4.2 统一分析器可一次 LLM 调用完成多任务

---

### 2.4 伏笔系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **伏笔追踪器** | ✅ | `processor/foreshadowing.py` | ~1235 | plant/resolve/abandon/get_active，三级语义去重，含 Lite 版本 |
| **伏笔分析器** | ✅ | `processor/foreshadowing_analyzer.py` | ~853 | MANUAL/LLM 双模式，智能检测与解决建议 |
| **主动提醒** | ✅ | `engine.py` | - | build_context 自动注入活跃伏笔 |
| **语义去重** | ✅ | - | - | Embedding 余弦相似度，防止重复伏笔 |

**伏笔状态**：
- PLANTED：已埋下
- DEVELOPING：发展中
- RESOLVED：已解决
- ABANDONED：已放弃

**伏笔功能亮点**：
- 三级语义去重（Embedding 余弦相似度 / 精确匹配 / 词重叠后备）
- 多角色支持，可按实体查询关联伏笔
- ForeshadowingTrackerLite 轻量版可选
- ForeshadowingAnalyzer 支持 MANUAL/LLM 双模式智能分析

---

### 2.5 持久条件系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **持久条件追踪** | ✅ | `processor/context_tracker.py` | ~1918 | 15 种条件类型，自动提取，智能压缩 |
| **语义去重** | ✅ | - | - | Embedding 余弦相似度（≥0.85 自动合并） |
| **置信度衰减** | ✅ | - | - | 长期未使用自动降低优先级 |
| **增长控制** | ✅ | - | - | 每类型最多5条，总共最多30条 |

**15种条件类型**：
用户身份、用户目标、用户偏好、技术环境、项目信息、时间约束、角色特征、世界观设定、关系设定、情绪状态、技能能力、物品道具、假设前提、约束条件、自定义

---

### 2.6 一致性检测系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **一致性检测器** | ✅ | `processor/consistency.py` | ~1458 | 8 种冲突类型 + 15 种属性检测 + 11 个检测方法 |
| **属性冲突检测** | ✅ | - | - | 15 种属性类型（年龄/身高/体重/外貌/性别等） |
| **关系一致性检查** | ✅ | - | - | 检测"朋友变敌人"类冲突 |
| **状态冲突检测** | ✅ | - | - | 生死/婚姻状态矛盾检测 |
| **时间线检测** | ✅ | - | - | 年龄/日期/事件顺序/时态逻辑检查 |
| **否定句矛盾检测** | ✅ | - | - | 否定语句冲突检测 |
| **绝对规则检测** | ✅ | `storage/layer0_core.py` | - | 用户自定义规则 LLM 语义检测（含降级策略） |

---

### 2.7 数据模型 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **基础模型** | ✅ | `models/base.py` | ~22 | EntityType（5种）/EventType（6种）枚举定义 |
| **实体模型** | ✅ | `models/entity.py` | ~24 | Pydantic Entity + Relation 数据结构 |
| **实体Schema** | ✅ | `models/entity_schema.py` | ~219 | 自定义实体类型 Schema，7 种内置类型 + 注册表 |
| **事件模型** | ✅ | `models/event.py` | ~15 | Pydantic Event 数据结构 |
| **伏笔模型** | ✅ | `models/foreshadowing.py` | ~20 | Pydantic Foreshadowing 数据结构 |
| **时态模型** | ✅ | `models/temporal.py` | ~587 | 三时态 TemporalFact/UnifiedNode/EpisodicNode/Contradiction 等 |
| **轮次模型** | ✅ | `models/turn.py` | ~15 | Pydantic Turn 数据结构 |

---

### 2.8 存储系统 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **L0 核心设定** | ✅ | `storage/layer0_core.py` | ~109 | 角色卡/世界观/代码规范/绝对规则，按场景注入 |
| **L1 整合层** | ✅ | `storage/layer1_consolidated.py` | ~181 | 分片 JSON 存储，每 1000 实体一个文件，级联删除 |
| **L2 工作层** | ✅ | `storage/layer2_working.py` | ~100 | 容量 200 实体，Delta Rule 更新，LRU 淘汰，焦点栏 |
| **容量管理** | ✅ | `storage/volume_manager.py` | ~394 | 分卷存储，O(1) 三级定位，支持 2 亿字规模 |
| **Episode 存储** | ✅ | `storage/episode_store.py` | ~170 | JSONL 格式 Episode 持久化 |
| **多租户** | ✅ | `storage/multi_tenant.py` | ~272 | user/session/character 三级隔离，智能搜索 |

**100% 不遗忘保证**：
- VolumeManager 分卷存档
- N-gram 原文索引持久化（JSONL 增量）
- L11 原文兜底搜索

---

### 2.9 图数据库后端 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **后端基类** | ✅ | `graph/backends/base.py` | ~282 | 统一接口定义（GraphBackend/GraphNode/GraphEdge） |
| **后端工厂** | ✅ | `graph/backends/factory.py` | ~215 | 自动选择后端 |
| **JSON 后端** | ✅ | `graph/backends/json_backend.py` | ~349 | 默认本地 JSON 存储 |
| **Kuzu 后端** | ✅ | `graph/backends/kuzu_backend.py` | ~446 | 可选嵌入式图数据库 |
| **旧版适配器** | ✅ | `graph/backends/legacy_adapter.py` | ~331 | 兼容旧数据格式 |

**设计理念**：
- 默认使用 file 后端（零依赖，JSON 存储）
- 可选 Kuzu 嵌入式图数据库（性能更好，通过 `TEMPORAL_GRAPH_BACKEND=kuzu` 启用）
- **v4.0 统一架构**：`engine.knowledge_graph` 和 `engine.temporal_graph` 指向同一个 `TemporalKnowledgeGraph` 实例
- 配置项：`TEMPORAL_GRAPH_BACKEND`（file/kuzu）、`KUZU_BUFFER_POOL_SIZE`（默认 256MB）
- 未来可扩展 Neo4j/FalkorDB 等企业后端

---

### 2.10 索引系统 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **向量索引 (IVF)** | ✅ | `index/vector_index_ivf.py` | ~566 | IVF-HNSW 聚类加速，95-99% 召回率 |
| **向量索引 (Flat)** | ✅ | `index/vector_index.py` | ~456 | FAISS IndexFlatIP，100% 召回率 |
| **全文索引** | ✅ | `index/fulltext_index.py` | ~436 | BM25 算法 |
| **倒排索引** | ✅ | `index/inverted_index.py` | ~102 | 关键词倒排 |
| **N-gram 索引** | ✅ | `index/ngram_index.py` | ~418 | 原文存储与搜索，100% 不遗忘兆底 |
| **时态索引** | ✅ | `index/temporal_index.py` | ~501 | 三时态范围查询 |
| **实体索引** | ✅ | `index/entity_index.py` | ~271 | 实体快速检索 |

---

### 2.11 嵌入系统 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **本地嵌入** | ✅ | `embedding/local_backend.py` | ~103 | paraphrase-multilingual-MiniLM-L12-v2，384维 |
| **API 嵌入** | ✅ | `embedding/api_backend.py` | ~266 | OpenAI / SiliconFlow / Google / 任何兼容 API，滑动窗口限流 |
| **嵌入工厂** | ✅ | `embedding/factory.py` | ~196 | auto_select_backend()，4 级优先自动选择 |
| **嵌入基类** | ✅ | `embedding/base.py` | ~262 | lite()/local()/cloud_*()，内存+磁盘双缓存 |

**支持的嵌入服务**：
- OpenAI (text-embedding-3-small/large, ada-002)
- SiliconFlow (BAAI/bge-large-zh-v1.5, bge-large-en-v1.5, bge-m3)
- Google 兼容 (text-embedding-004, embedding-001)
- Ollama (本地部署)
- 任何 OpenAI 兼容 API（中转、Azure、vLLM 等）

---

### 2.12 工具系统 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **LLM 客户端** | ✅ | `utils/llm_client.py` | ~296 | 统一接口，支持 OpenAI/硅基流动/Ollama/任何兼容 API，429 指数退避 |
| **预算管理** | ✅ | `utils/budget_manager.py` | ~465 | 日/时预算限制，自动降级，保留预算，模型价格表 |
| **性能监控** | ✅ | `utils/perf_monitor.py` | ~235 | 6 种指标，P50/P95/P99，自动采集，健康判断 |
| **任务管理器** | ✅ | `utils/task_manager.py` | ~550 | 14 种任务类型，pub/sub 通知，单例模式，TaskContext 上下文管理器 |
| **自动维护** | ✅ | `utils/auto_maintain.py` | ~254 | 5 种维护操作，后台调度（6/12/24小时周期） |
| **预热工具** | ✅ | `utils/warmup.py` | ~188 | 资源预加载/懒加载管理器，优先级排序 |
| **环境配置** | ✅ | `utils/environment.py` | ~281 | 缓存隔离（HF/Torch/spaCy），配置迁移，磁盘用量统计 |

---

### 2.13 接口层 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **REST API** | ✅ | `server.py` | ~5107 | FastAPI，CORS 中间件，完整 OpenAPI 文档 |
| **Python SDK** | ✅ | `engine.py` | ~4259 | RecallEngine 主入口，七层上下文构建 |
| **CLI 工具** | ✅ | `cli.py` | ~317 | recall init/add/search/list/delete/stats/serve/consolidate/reset/foreshadowing |
| **初始化模块** | ✅ | `init.py` | ~194 | RecallInit 类方法，项目目录隔离，卸载即删目录 |
| **配置管理** | ✅ | `config.py` | ~230 | LiteConfig/LightweightEntityExtractor/TripleRecallConfig |
| **版本信息** | ✅ | `version.py` | 版本号管理（v4.2.0） |
| **入口点** | ✅ | `__main__.py` | python -m recall 入口 |
| **SillyTavern 插件** | ✅ | `plugins/sillytavern/` | 完整前端集成，双语言 i18n |

**API 端点统计**：97 个 REST API 端点（GET 39 / POST 33 / PUT 8 / DELETE 17）

| 类别 | 端点数 | 说明 |
|------|:------:|------|
| Health | 2 | 健康检查 |
| Logging | 1 | 日志记录 |
| Tasks | 6 | 后台任务追踪（v4.2 新增） |
| Memories | 9 | 记忆 CRUD |
| Core Settings | 2 | 核心设定 |
| Context | 1 | 上下文构建 |
| Persistent Contexts | 14 | 持久条件管理 |
| Foreshadowing | 12 | 伏笔管理 |
| Foreshadowing Analysis | 4 | 伏笔分析 |
| Temporal | 6 | 时态查询 |
| Contradictions | 4 | 矛盾检测 |
| Search | 4 | 搜索配置 |
| Graph | 4 | 图谱操作 |
| Entities | 5 | 实体管理 |
| Episodes | 3 | Episode 查询 |
| Admin | 16 | 管理功能 |
| mem0 Compatible | 4 | mem0 兼容 API |

---

## 三、未完成功能

### 3.1 MCP Server 📋

| 功能 | 状态 | 计划文件 | 说明 |
|------|:----:|----------|------|
| **MCP Server 核心** | 📋 | `recall/mcp_server.py` | Model Context Protocol 支持 |
| **MCP Tools** | 📋 | `recall/mcp/tools.py` | 10+ 个 MCP 工具 |
| **MCP Resources** | 📋 | `recall/mcp/resources.py` | recall:// URI 方案 |
| **SSE 传输** | 📋 | `recall/mcp/transport.py` | 远程部署支持 |

**预计工作量**：3-4 天

**价值**：一次开发，适配所有支持 MCP 的 AI 应用（Claude Desktop、VS Code、Cursor 等）

---

### 3.2 命名重构 ✅ 已完成

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **部署模式命名统一** | ✅ | `LiteConfig`（保留 `LightweightConfig` 兼容别名） |
| **抽取模式命名统一** | ✅ | `RULES/ADAPTIVE/LLM`（保留 `LOCAL/HYBRID/LLM_FULL` 兼容别名） |
| **矛盾检测策略统一** | ✅ | `RULE/LLM/MIXED/AUTO`（保留旧别名） |
| **嵌入配置方法统一** | ✅ | `lite()/local()/cloud_*()` |

**向后兼容**：所有旧命名保留为别名，现有代码无需修改

---

### 3.3 多数据库支持 📋

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **PostgreSQL 后端** | 📋 | 企业场景需求 |
| **Neo4j 后端** | 📋 | 可选外部图数据库 |
| **FalkorDB 后端** | 📋 | 高性能图数据库 |

**设计原则**：可选插件，不破坏零配置原则

```python
# 默认（零配置）
engine = RecallEngine()

# 企业可选
engine = RecallEngine(
    storage_backend="postgresql",
    connection_string="postgresql://..."
)
```

---

### 3.4 其他计划功能 📋

| 功能 | 状态 | 优先级 | 说明 |
|------|:----:|:------:|------|
| 提示工程系统化 | 📋 | 中 | 创建 `recall/prompts/` 集中管理 |
| 更多 LLM 提供商 | 📋 | 中 | Anthropic / Gemini 直接支持 |
| 重排序器多样性 | 📋 | 低 | Cohere Rerank / 自定义模型 |
| CodeIndexer | 📋 | 低 | 代码场景专用索引 |

---

## 四、与 Graphiti 对比

| 维度 | Recall | Graphiti | 胜负 |
|------|--------|----------|:----:|
| **易用性** | 零配置开箱即用 | 需要配置 Neo4j | ✅ Recall |
| **时态模型** | 三时态 | 双时态 | ✅ Recall |
| **检索深度** | 11层漏斗 | 混合检索 | ✅ Recall |
| **去重效率** | 三阶段（语义层） | 两阶段 | ✅ Recall |
| **成本控制** | LLM 可选，本地优先 | LLM 强依赖 | ✅ Recall |
| **中文支持** | jieba + spaCy 原生优化 | 通用 LLM | ✅ Recall |
| **企业后端** | 📋 计划中 | ✅ 多数据库 | ❌ Graphiti |
| **MCP 支持** | 📋 计划中 | ✅ 已实现 | ❌ Graphiti |
| **社区成熟度** | 新项目 | 22K+ stars | ❌ Graphiti |

---

## 五、数据规模与准确率保证

### 设计目标：100% 不遗忘

Recall 的核心设计目标是**在任意数据规模下保持高召回率**，通过以下机制保证：

### 多路召回 + RRF 融合策略

```
┌─────────────────────────────────────────────────────────────┐
│                  Phase 3.6 三路并行召回                      │
├─────────────────────────────────────────────────────────────┤
│  路径1: 语义向量召回 (Vector Search)     - 语义相似匹配      │
│  路径2: 关键词倒排索引召回               - 100% 精确匹配     │
│  路径3: 实体索引召回                     - 实体关联查找      │
├─────────────────────────────────────────────────────────────┤
│  ↓ RRF (Reciprocal Rank Fusion) 融合                       │
│  ↓ 取并集，保证不遗漏                                      │
│  ↓ 原文兜底搜索（终极保证）                                 │
└─────────────────────────────────────────────────────────────┘
```

### 各组件召回率保证

| 组件 | 数据规模 | 召回率 | 说明 |
|------|----------|:------:|------|
| 倒排索引 | 任意 | **100%** | 精确关键词匹配 |
| 实体索引 | 任意 | **100%** | O(1) 哈希查找 |
| N-gram 原文兜底 | 任意 | **100%** | 全文扫描兜底 |
| VectorIndex (Flat) | < 50万 | **100%** | 暴力搜索 |
| VectorIndexIVF (HNSW) | 50万-10亿 | **95-99%** | 近似最近邻 |

### 向量索引召回率配置

```python
# 提高 HNSW 召回率的配置（在 api_keys.env 中）
# 默认值已经是高召回率设置
hnsw_m=32              # HNSW 图连接数（越大召回越高）
hnsw_ef_construction=200  # 构建精度
hnsw_ef_search=64      # 搜索精度（越大召回越高）

# 最大召回模式配置
TRIPLE_RECALL_KEYWORD_WEIGHT=1.2  # 关键词召回权重更高
FALLBACK_ENABLED=true             # 启用原文兜底
```

### 结论

**在正常配置下，即使数据量增长到百万级甚至千万级，Recall 的记忆提取准确率应保持在 95% 以上**，因为：

1. ✅ 关键词倒排索引保证 100% 精确匹配
2. ✅ 三路并行召回取并集不遗漏
3. ✅ N-gram 原文兜底搜索作为终极保证
4. ✅ IVF-HNSW 向量索引提供 95-99% 召回率
5. ✅ RRF 融合算法对多路命中结果加权提升

---

## 六、代码统计

### 6.1 核心模块代码量

> 📝 **注意**：文件数包含各目录的 `__init__.py`（共 10 个），Python 文件总数为 77 个。

| 模块 | 文件数 | 代码行数 |
|------|:------:|:--------:|
| recall/ (根目录) | 8 | ~10,159 |
| graph/ | 8 | ~4,329 |
| graph/backends/ | 6 | ~1,714 |
| retrieval/ | 7 | ~2,968 |
| processor/ | 12 | ~8,196 |
| storage/ | 7 | ~1,244 |
| index/ | 8 | ~2,841 |
| embedding/ | 5 | ~842 |
| models/ | 8 | ~988 |
| utils/ | 8 | ~2,311 |
| **总计** | **77** | **~35,592** |

### 6.2 插件代码量

| 模块 | 代码行数 |
|------|:--------:|
| SillyTavern 插件 (index.js) | ~9,452 |
| SillyTavern 插件 (style.css) | ~2,193 |
| SillyTavern 插件 (i18n/) | 2 语言文件 |
| **总计** | **~11,645** |

### 6.3 总代码量

| 类别 | 代码行数 |
|------|:--------:|
| Python 核心 | ~35,592 |
| 插件 (JS/CSS) | ~11,645 |
| **总计** | **~47,237** |

---

## 七、开发工具与测试

### 7.1 开发调试工具 (tools/)

| 工具 | 用途 |
|------|------|
| `chat_with_recall.py` | 交互式对话测试 |
| `check_v41.py` | v4.1 功能验证 |
| `diagnose_entity.py` | 实体诊断工具 |
| `final_config_check.py` | 配置最终检查 |
| `inspect_graph.py` | 知识图谱可视化检查 |
| `migrate_ivf_to_hnsw.py` | IVF→HNSW 索引迁移 |
| `migrate_v3_to_v4.py` | v3→v4 数据迁移 |
| `rebuild_relations.py` | 重建关系索引 |
| `verify_config.py` | 配置验证工具 |

### 7.2 测试套件 (tests/)

| 测试文件 | 覆盖功能 |
|----------|----------|
| `test.py` | 基础功能测试 |
| `test_absolute_rules.py` | 绝对规则系统 |
| `test_comprehensive.py` | 综合功能测试 |
| `test_context_system.py` | 持久条件系统 |
| `test_delete_cascade.py` | 级联删除 |
| `test_eleven_layer.py` | 11层检索架构 |
| `test_embedding_modes.py` | 嵌入模式切换 |
| `test_foreshadowing_analyzer.py` | 伏笔分析器 |
| `test_full_user_flow.py` | 完整用户流程 |
| `test_growth_control.py` | 增长控制 |
| `test_ivf_hnsw_recall.py` | IVF/HNSW 召回率 |
| `test_kuzu_demo.py` | Kuzu 图数据库后端 |
| `test_phase1_3.py` | 阶段1-3功能 |
| `test_retrieval_benchmark.py` | 检索性能基准 |
| `test_rrf_fusion.py` | RRF 融合算法 |
| `test_semantic_dedup.py` | 语义去重 |
| `test_stress.py` | 压力测试 |
| `test_v41_features.py` | v4.1 新功能 |

---

## 八、快速链接

### 8.1 计划文档（可归档）

| 文档 | 状态 | 说明 |
|------|:----:|------|
| [Recall-ai-plan.md](plans/Recall-ai-plan.md) | 📦 历史 | v3 原始计划 |
| [Recall-4.0-Upgrade-Plan.md](plans/Recall-4.0-Upgrade-Plan.md) | 📦 历史 | v4.0 升级计划 |
| [Recall4.0AdditionUpgradePlan.md](plans/Recall4.0AdditionUpgradePlan.md) | 📦 历史 | v4.1 补充升级 |
| [CHECKLIST-REPORT.md](plans/CHECKLIST-REPORT.md) | 📦 历史 | 自查报告 |
| [COMPREHENSIVE-FIX-PLAN.md](plans/COMPREHENSIVE-FIX-PLAN.md) | 📦 历史 | 综合修复计划 |
| [ARCHITECTURE-ANALYSIS.md](plans/ARCHITECTURE-ANALYSIS.md) | 📦 历史 | 架构分析 |
| [semantic-dedup-implementation.md](plans/semantic-dedup-implementation.md) | ✅ 已完成 | 语义去重实现 |
| [NAMING-REFACTOR-PLAN.md](plans/NAMING-REFACTOR-PLAN.md) | ✅ 已完成 | 命名重构计划 |
| [MCP-PLAN.md](plans/MCP-PLAN.md) | 📋 待实施 | MCP Server 计划 |
| [PERFORMANCE-OPTIMIZATION-PLAN.md](plans/PERFORMANCE-OPTIMIZATION-PLAN.md) | ✅ 已完成 | 性能优化计划（v4.2 已实施） |
| [GraphitiAnalysis.md](plans/GraphitiAnalysis.md) | 📖 参考 | 竞品分析 |

### 8.2 项目根目录文件

| 文件 | 用途 |
|------|------|
| `install.ps1` / `install.sh` | 安装脚本（Windows/Linux） |
| `start.ps1` / `start.sh` | 启动脚本 |
| `manage.ps1` / `manage.sh` | 管理脚本（清理/重建/诊断等） |
| `pyproject.toml` | Python 项目配置（依赖/入口点/工具配置） |
| `package.json` | Node.js 开发依赖（jsdom 用于插件测试） |
| `README.md` | 项目说明文档 |
| `LICENSE` | MIT 开源协议 |
| `.gitignore` | Git 忽略规则 |

### 8.3 运行时数据目录 (recall_data/)

| 目录 | 用途 |
|------|------|
| `cache/` | 嵌入向量缓存、查询缓存 |
| `config/` | 配置文件（api_keys.env 等） |
| `data/` | 持久化数据（记忆、实体、图谱） |
| `index/` | 索引文件（向量/倒排/N-gram） |
| `indexes/` | 索引备份 |
| `logs/` | 运行日志 |
| `models/` | 本地嵌入模型缓存 |
| `temp/` | 临时文件 |

### 8.4 环境变量

> 📝 **注意**：系统支持 **101** 个环境变量（通过 `SUPPORTED_CONFIG_KEYS` 定义），这里只列出核心配置。完整列表见 `recall/server.py` 中的 `SUPPORTED_CONFIG_KEYS`。

**Embedding 配置**：
| 变量 | 说明 |
|------|------|
| `EMBEDDING_API_KEY` | Embedding API 密钥 |
| `EMBEDDING_API_BASE` | Embedding API 地址 |
| `EMBEDDING_MODEL` | Embedding 模型名称 |
| `EMBEDDING_DIMENSION` | 向量维度 |
| `RECALL_EMBEDDING_MODE` | auto/lite/local/cloud |

**LLM 配置**：
| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | LLM API 密钥 |
| `LLM_API_BASE` | LLM API 地址 |
| `LLM_MODEL` | LLM 模型（默认 gpt-4o-mini） |
| `LLM_RELATION_MODE` | 关系抽取模式 |

**伏笔分析配置**：
| 变量 | 说明 |
|------|------|
| `FORESHADOWING_LLM_ENABLED` | 启用 LLM 伏笔分析 |
| `FORESHADOWING_TRIGGER_INTERVAL` | 触发间隔（轮） |
| `FORESHADOWING_AUTO_PLANT` | 自动埋伏笔 |
| `FORESHADOWING_AUTO_RESOLVE` | 自动解决伏笔 |

**知识图谱配置**（v4.0 统一架构）：
| 变量 | 说明 |
|------|------|
| `TEMPORAL_GRAPH_ENABLED` | 启用时态增强功能（图谱始终启用） |
| `TEMPORAL_GRAPH_BACKEND` | 存储后端：`file`（默认）或 `kuzu` |
| `KUZU_BUFFER_POOL_SIZE` | Kuzu 缓冲池大小（MB，默认 256） |
| `TEMPORAL_DECAY_RATE` | 时态衰减率（默认 0.1） |
| `TEMPORAL_MAX_HISTORY` | 最大历史记录数（默认 1000） |

**系统配置**：
| 变量 | 说明 |
|------|------|
| `RECALL_DATA_ROOT` | 数据根目录 |
| `ADMIN_KEY` | 管理 API 密钥 |
| `CONTEXT_TRIGGER_INTERVAL` | 上下文提取间隔 |

### 8.5 安装模式与依赖

```bash
# Lite 模式 - 无向量搜索，最小依赖
pip install recall-ai

# Cloud 模式 - 使用 API Embedding
pip install "recall-ai[cloud]"

# Local 模式 - 本地 Embedding 模型（GPU 版 PyTorch）
pip install "recall-ai[local]"

# Local-CPU 模式 - 本地 Embedding 模型（CPU 版 PyTorch，无需显卡）
pip install "recall-ai[local-cpu]"

# Enterprise 模式 - 企业级性能引擎
pip install "recall-ai[enterprise]"

# Enterprise-CPU 模式 - 企业级 + CPU 版 PyTorch
pip install "recall-ai[enterprise-cpu]"
```

| 模式 | 依赖 | 内存占用 |
|------|------|:--------:|
| lite | 无额外依赖 | ~80MB |
| cloud | faiss-cpu | ~100MB |
| local | sentence-transformers, faiss-cpu | ~500MB |
| local-cpu | sentence-transformers (CPU), faiss-cpu | ~500MB |
| enterprise | faiss-cpu, networkx, kuzu | ~600MB |
| enterprise-cpu | sentence-transformers (CPU), faiss-cpu, networkx, kuzu | ~600MB |

**核心依赖**（所有模式必装）：
- pydantic, spacy, jieba（NLP）
- litellm, openai, httpx（LLM）
- fastapi, uvicorn（Web）
- click, rich, numpy, psutil, schedule, pybloom-live
- pyyaml（Prompt 模板）

---

## v5.0 新增功能

### 全局模式管理 ✅

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **RECALL_MODE 环境变量** | ✅ | roleplay / general / knowledge_base 三模式，默认 roleplay |
| **ModeConfig 数据类** | ✅ | 6 个子开关：foreshadowing / character / rp_consistency / rp_relation_types / rp_context_types |
| **环境变量子开关覆盖** | ✅ | 如 FORESHADOWING_ENABLED=true 可在 general 模式下启用伏笔 |
| **无效值安全回退** | ✅ | 未知 RECALL_MODE 值 → warning + 回退 roleplay |
| **/v1/mode 端点** | ✅ | 返回当前模式和所有子开关状态 |
| **条件化 foreshadowing 导入** | ✅ | 非 RP 模式不加载伏笔模块，减少内存占用 |

### 批量写入与元数据索引 ✅

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **add_batch() API** | ✅ | 批量添加记忆，支持 source/tags/category/content_type 元数据 |
| **MetadataIndex** | ✅ | 元数据索引，支持按 source/tags/category/content_type 过滤 |
| **search() 元数据过滤** | ✅ | search(source="bilibili", tags=["热点"]) |
| **POST /v1/memories/batch** | ✅ | REST API 批量添加端点 |

### MCP Server ✅

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **11 个 MCP Tools** | ✅ | recall_add/search/delete/list/add_batch/stats 等 |
| **3+2 个 MCP Resources** | ✅ | recall://memories, recall://entities, recall://stats + 动态资源 |
| **stdio/SSE 双传输** | ✅ | 支持 Claude Desktop 和 Web 客户端 |
| **recall-mcp 命令行入口** | ✅ | pyproject.toml console_scripts |

### 多 LLM/Embedding 自适应 ✅

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **LLM 提供商自动检测** | ✅ | 按 api_base 域名检测 OpenAI/Anthropic/Google，零新增配置变量 |
| **Embedding 提供商自动检测** | ✅ | 支持 Google/Voyage AI/Cohere 等，按域名自动路由 |
| **MODEL_DIMENSIONS 自动查表** | ✅ | 未设 EMBEDDING_DIMENSION 时自动按模型名查表 |
| **中转站场景兼容** | ✅ | 非官方域名一律走 OpenAI SDK，不受模型名影响 |

### Prompt 模板化 ✅

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **PromptManager** | ✅ | YAML 模板 + str.format() 渲染，支持模式感知 |
| **8 个内置模板** | ✅ | entity_extraction/relation_extraction/consistency 等 |
| **用户自定义覆盖** | ✅ | recall_data/prompts/ 下同名 YAML 覆盖内置模板 |

### 可插拔重排序器 ✅

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **RerankerFactory** | ✅ | builtin / cohere / cross-encoder 三种后端 |
| **内置重排序器** | ✅ | 默认 builtin，与 v4.2 行为 100% 一致 |
| **Cohere Rerank** | ✅ | 使用 Cohere Rerank API |
| **Cross-Encoder** | ✅ | 使用本地 sentence-transformers Cross-Encoder 模型 |

### 性能优化 ✅

| 功能 | 状态 | 说明 |
|------|:----:|------|
| **temporal_index bisect 优化** | ✅ | query_at_time/query_range 从 O(n) 降至 O(log n + k) |
| **inverted_index WAL** | ✅ | 追加写入 + 原子压缩，崩溃安全 |
| **json_backend 延迟保存** | ✅ | 脏数据计数 + atexit flush，减少磁盘 IO |
| **volume_manager O(1) 索引** | ✅ | memory_id 索引字典，O(1) 查找 |

---

## 九、版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v5.0.0 | 2026-02-15 | 通用化升级：全局模式管理(RECALL_MODE)、批量写入+元数据索引、MCP Server、多LLM/Embedding自适应、可插拔重排序器、Prompt模板化 |
| v4.2.0 | 2026-02-06 | 统一LLM分析器，Turn API批量保存，任务管理器，性能优化 |
| v4.1.0 | 2026-01-28 | LLM 关系/实体抽取增强，Episode 概念，实体摘要 |
| v4.0.0 | 2026-01-23 | 三时态模型，11层检索，矛盾检测系统 |
| v3.6.0 | 2026-01-20 | 语义去重，绝对规则系统，CoreSettings |
| v3.0.0 | 2026-01-18 | 8层检索，伏笔系统，持久条件 |

---

> 📝 **本文档更新于 2026-02-15，基于代码审计和计划文档综合整理**
