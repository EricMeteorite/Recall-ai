# Recall v4.1 功能状态总览

> **生成日期**: 2026-02-01  
> **当前版本**: v4.1.0  
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
| **三时态知识图谱** | ✅ | `graph/temporal_knowledge_graph.py` | ~2128 | T1事实时间 + T2知识时间 + T3系统时间，超越 Graphiti 的双时态模型 |
| **基础知识图谱 (别名)** | ✅ | `graph/__init__.py` | - | `KnowledgeGraph = TemporalKnowledgeGraph`（v4.0 统一架构，向后兼容） |
| **Relation 数据模型** | ✅ | `graph/knowledge_graph.py` | ~270 | Relation 类定义，供兼容使用 |
| **矛盾检测与管理** | ✅ | `graph/contradiction_manager.py` | ~639 | 四种检测策略（RULE/LLM/MIXED/AUTO），四种解决策略（SUPERSEDE/COEXIST/REJECT/MANUAL） |
| **关系抽取器** | ✅ | `graph/relation_extractor.py` | ~90 | 规则模式，正则 + 共现检测 |
| **LLM关系抽取器** | ✅ | `graph/llm_relation_extractor.py` | ~390 | 三模式（RULES/ADAPTIVE/LLM），支持动态关系类型和时态信息 |
| **社区检测** | ✅ | `graph/community_detector.py` | ~369 | Louvain / Label Propagation / Connected Components |
| **查询规划器** | ✅ | `graph/query_planner.py` | ~375 | 图查询优化与执行计划 |
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
| **11层漏斗检索** | ✅ | `retrieval/eleven_layer.py` | ~1330 | 完整 11 层架构，渐进式过滤 |
| **8层检索（兼容）** | ✅ | `retrieval/eight_layer.py` | ~726 | Phase 3.6 版本，向后兼容 |
| **RRF 融合算法** | ✅ | `retrieval/rrf_fusion.py` | ~115 | Reciprocal Rank Fusion |
| **并行多路召回** | ✅ | `retrieval/parallel_retrieval.py` | ~230 | 向量 + BM25 + 图谱并行 |
| **检索配置** | ✅ | `retrieval/config.py` | ~300 | 检索策略配置（fast/default/accurate） |
| **上下文构建器** | ✅ | `retrieval/context_builder.py` | ~225 | 上下文组装与格式化 |

**11层检索架构详解**：

```
┌─────────────────────────────────────────────────────────────┐
│                    11层漏斗检索架构                          │
├─────────────────────────────────────────────────────────────┤
│  L1  │ 布隆过滤器快速筛选 (O(1))                             │
│  L2  │ 缓存命中检查                                         │
├──────┼──────────────────────────────────────────────────────┤
│  L3  │ 倒排索引粗召回 (~10ms)                               │
│  L4  │ 向量相似度召回 (ANN/IVF/HNSW)                        │
│  L5  │ 图谱 BFS 扩展（关联实体）                             │
│  L6  │ 向量精排（重计算余弦相似度）                          │
│  L7  │ 全文 BM25 召回                                       │
├──────┼──────────────────────────────────────────────────────┤
│  L8  │ LLM 相关性过滤（可选，默认关闭）                      │
│  L9  │ 多因素重排序（时间衰减 + 置信度 + 来源权重）          │
│ L10  │ Cross-Encoder 精排（可选）                           │
│ L11  │ N-gram 原文兜底（100% 不遗忘保证）                    │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.3 实体处理系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **基础实体抽取** | ✅ | `processor/entity_extractor.py` | ~330 | spaCy NER + jieba + 规则 + known_entities |
| **智能实体抽取** | ✅ | `processor/smart_extractor.py` | ~689 | 三模式自适应（RULES/ADAPTIVE/LLM），复杂度评估，成本控制 |
| **三阶段去重** | ✅ | `processor/three_stage_deduplicator.py` | ~654 | 阶段1: MinHash+LSH, 阶段2: 语义相似度, 阶段3: 可选LLM |
| **实体摘要生成** | ✅ | `processor/entity_summarizer.py` | ~180 | 简单模式 + LLM模式，自动生成实体描述 |
| **记忆摘要器** | ✅ | `processor/memory_summarizer.py` | ~275 | 记忆压缩与摘要生成 |
| **场景处理器** | ✅ | `processor/scenario.py` | ~220 | 场景类型识别与处理 |

**去重系统优势**：
- 比 Graphiti 多一层语义过滤（阶段2），减少 LLM 调用
- MinHash + LSH 实现 O(1) 候选筛选
- 可配置阈值：DEDUP_HIGH_THRESHOLD=0.85, DEDUP_LOW_THRESHOLD=0.70

---

### 2.4 伏笔系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **伏笔追踪器** | ✅ | `processor/foreshadowing.py` | ~1230 | plant/resolve/abandon/get_active，语义去重 |
| **伏笔分析器** | ✅ | `processor/foreshadowing_analyzer.py` | ~850 | MANUAL/LLM 双模式，智能检测与解决建议 |
| **主动提醒** | ✅ | `engine.py` | - | build_context 自动注入活跃伏笔 |
| **语义去重** | ✅ | - | - | Embedding 余弦相似度，防止重复伏笔 |

**伏笔类型支持**：
- 明示伏笔：直接提到的未来事件
- 隐示伏笔：暗示性线索
- 悬念伏笔：未解答的问题
- 物品伏笔：重要道具的引入

---

### 2.5 持久条件系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **持久条件追踪** | ✅ | `processor/context_tracker.py` | ~1915 | 15种条件类型，自动提取，智能压缩 |
| **语义去重** | ✅ | - | - | Embedding 余弦相似度（≥0.85 自动合并） |
| **置信度衰减** | ✅ | - | - | 长期未使用自动降低优先级 |
| **增长控制** | ✅ | - | - | 每类型最多5条，总共最多30条 |

**15种条件类型**：
用户身份、用户目标、用户偏好、技术环境、项目信息、时间约束、角色特征、世界观设定、关系设定、情绪状态、技能能力、物品道具、假设前提、约束条件、自定义

---

### 2.6 一致性检测系统 ✅

| 功能 | 状态 | 文件 | 行数 | 技术细节 |
|------|:----:|------|------|----------|
| **一致性检测器** | ✅ | `processor/consistency.py` | ~1460 | 属性/关系/生死/时间线四大检测 |
| **属性冲突检测** | ✅ | - | - | 检测"黑发变金发"类冲突 |
| **关系一致性检查** | ✅ | - | - | 检测"朋友变敌人"类冲突 |
| **生死矛盾检测** | ✅ | - | - | 防止死亡角色继续行动 |
| **时间线检测** | ✅ | - | - | 年龄/日期逻辑检查 |
| **绝对规则检测** | ✅ | `storage/layer0_core.py` | - | 用户自定义规则 LLM 语义检测 |

---

### 2.7 数据模型 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **基础模型** | ✅ | `models/base.py` | 通用基类定义 |
| **实体模型** | ✅ | `models/entity.py` | 实体数据结构 |
| **实体Schema** | ✅ | `models/entity_schema.py` | 自定义实体类型 Schema |
| **事件模型** | ✅ | `models/event.py` | 事件数据结构 |
| **伏笔模型** | ✅ | `models/foreshadowing.py` | 伏笔数据结构 |
| **时态模型** | ✅ | `models/temporal.py` | 三时态数据结构（T1/T2/T3） |
| **轮次模型** | ✅ | `models/turn.py` | 对话轮次数据结构 |

---

### 2.8 存储系统 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **L0 核心设定** | ✅ | `storage/layer0_core.py` | 角色卡/世界观/绝对规则 |
| **L1 整合层** | ✅ | `storage/layer1_consolidated.py` | 压缩后的长期记忆 |
| **L2 工作层** | ✅ | `storage/layer2_working.py` | 近期活跃记忆 |
| **容量管理** | ✅ | `storage/volume_manager.py` | 分卷存储，O(1) 按轮次定位 |
| **Episode 存储** | ✅ | `storage/episode_store.py` | 情节/事件单元存储 |
| **多租户** | ✅ | `storage/multi_tenant.py` | 用户/角色隔离 |

**100% 不遗忘保证**：
- VolumeManager 分卷存档
- N-gram 原文索引持久化（JSONL 增量）
- L11 原文兜底搜索

---

### 2.9 图数据库后端 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **后端基类** | ✅ | `graph/backends/base.py` | 统一接口定义 |
| **后端工厂** | ✅ | `graph/backends/factory.py` | 自动选择后端 |
| **JSON 后端** | ✅ | `graph/backends/json_backend.py` | 默认本地 JSON 存储 |
| **Kuzu 后端** | ✅ | `graph/backends/kuzu_backend.py` | 可选嵌入式图数据库 |
| **旧版适配器** | ✅ | `graph/backends/legacy_adapter.py` | 兼容旧数据格式 |

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
| **向量索引 (IVF)** | ✅ | `index/vector_index_ivf.py` | IVF-Flat 聚类加速 |
| **向量索引 (HNSW)** | ✅ | `index/vector_index.py` | HNSW 图索引 |
| **全文索引** | ✅ | `index/fulltext_index.py` | BM25 算法 |
| **倒排索引** | ✅ | `index/inverted_index.py` | 关键词倒排 |
| **N-gram 索引** | ✅ | `index/ngram_index.py` | 原文存储与搜索 |
| **时态索引** | ✅ | `index/temporal_index.py` | 时间范围查询 |
| **实体索引** | ✅ | `index/entity_index.py` | 实体快速检索 |

---

### 2.11 嵌入系统 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **本地嵌入** | ✅ | `embedding/local_backend.py` | sentence-transformers 本地模型 |
| **API 嵌入** | ✅ | `embedding/api_backend.py` | OpenAI / SiliconFlow / 任何兼容 API |
| **嵌入工厂** | ✅ | `embedding/factory.py` | 自动选择后端 |
| **多模式配置** | ✅ | `embedding/base.py` | lite() / local() / cloud_*() |

**支持的嵌入服务**：
- OpenAI (text-embedding-3-small/large, ada-002)
- SiliconFlow (BAAI/bge-large-zh-v1.5 等)
- Ollama (本地部署)
- 任何 OpenAI 兼容 API

---

### 2.12 工具系统 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **LLM 客户端** | ✅ | `utils/llm_client.py` | 统一接口，支持多提供商 |
| **预算管理** | ✅ | `utils/budget_manager.py` | 日/时预算限制，自动降级 |
| **性能监控** | ✅ | `utils/perf_monitor.py` | 延迟/吞吐量监控 |
| **自动维护** | ✅ | `utils/auto_maintain.py` | 定期清理/压缩 |
| **预热工具** | ✅ | `utils/warmup.py` | 冷启动优化 |
| **环境配置** | ✅ | `utils/environment.py` | 环境变量管理 |

---

### 2.13 接口层 ✅

| 功能 | 状态 | 文件 | 技术细节 |
|------|:----:|------|----------|
| **REST API** | ✅ | `server.py` | FastAPI，完整 OpenAPI 文档 |
| **Python SDK** | ✅ | `engine.py` | RecallEngine 主入口 |
| **CLI 工具** | ✅ | `cli.py` | recall init/add/search/list/delete/stats/serve/consolidate/reset/foreshadowing |
| **初始化模块** | ✅ | `init.py` | 首次运行初始化逻辑 |
| **配置管理** | ✅ | `config.py` | LiteConfig/TripleRecallConfig 等 |
| **版本信息** | ✅ | `version.py` | 版本号管理（v4.1.0） |
| **入口点** | ✅ | `__main__.py` | python -m recall 入口 |
| **SillyTavern 插件** | ✅ | `plugins/sillytavern/` | 完整前端集成 |

**API 端点统计**：89 个 REST API 端点

| 类别 | 端点数 | 说明 |
|------|:------:|------|
| Health | 2 | 健康检查 |
| Memories | 8 | 记忆 CRUD |
| Core Settings | 2 | 核心设定 |
| Context | 1 | 上下文构建 |
| Persistent Contexts | 14 | 持久条件管理 |
| Foreshadowing | 11 | 伏笔管理 |
| Foreshadowing Analysis | 4 | 伏笔分析 |
| Temporal | 6 | 时态查询 |
| Contradictions | 4 | 矛盾检测 |
| Search | 4 | 搜索配置 |
| Graph | 4 | 图谱操作 |
| Entities | 5 | 实体管理 |
| Episodes | 3 | Episode 查询 |
| Admin | 17 | 管理功能 |
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

## 五、代码统计

### 5.1 核心模块代码量

> 📝 **注意**：文件数不含各目录的 `__init__.py`（共 10 个），实际 Python 文件总数为 75 个。

| 模块 | 文件数 | 代码行数 |
|------|:------:|:--------:|
| recall/ (根目录) | 7 | ~8,750 |
| graph/ | 7 | ~4,250 |
| graph/backends/ | 5 | ~1,650 |
| retrieval/ | 6 | ~2,900 |
| processor/ | 10 | ~7,800 |
| storage/ | 6 | ~1,220 |
| index/ | 7 | ~2,800 |
| embedding/ | 4 | ~820 |
| models/ | 7 | ~920 |
| utils/ | 6 | ~1,710 |
| **总计** | **65** | **~32,820** |

### 5.2 插件代码量

| 模块 | 代码行数 |
|------|:--------:|
| SillyTavern 插件 (index.js) | ~6,400 |
| SillyTavern 插件 (style.css) | ~1,950 |
| SillyTavern 插件 (i18n/) | 2 语言文件 |
| **总计** | **~8,350** |

### 5.3 总代码量

| 类别 | 代码行数 |
|------|:--------:|
| Python 核心 | ~32,820 |
| 插件 (JS/CSS) | ~8,350 |
| **总计** | **~41,170** |

---

## 六、开发工具与测试

### 6.1 开发调试工具 (tools/)

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

### 6.2 测试套件 (tests/)

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
| `test_phase1_3.py` | 阶段1-3功能 |
| `test_retrieval_benchmark.py` | 检索性能基准 |
| `test_rrf_fusion.py` | RRF 融合算法 |
| `test_semantic_dedup.py` | 语义去重 |
| `test_stress.py` | 压力测试 |
| `test_v41_features.py` | v4.1 新功能 |

---

## 七、快速链接

### 7.1 计划文档（可归档）

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
| [GraphitiAnalysis.md](plans/GraphitiAnalysis.md) | 📖 参考 | 竞品分析 |

### 7.2 项目根目录文件

| 文件 | 用途 |
|------|------|
| `install.ps1` / `install.sh` | 安装脚本（Windows/Linux） |
| `start.ps1` / `start.sh` | 启动脚本 |
| `manage.ps1` / `manage.sh` | 管理脚本（清理/重建/诊断等） |
| `pyproject.toml` | Python 项目配置 |
| `README.md` | 项目说明文档 |
| `LICENSE` | MIT 开源协议 |
| `.gitignore` | Git 忽略规则 |

### 7.3 运行时数据目录 (recall_data/)

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

### 7.4 环境变量

> 📝 **注意**：系统支持 67+ 个环境变量，这里只列出核心配置。完整列表见 `recall/config.py` 和 `recall/utils/environment.py`。

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

### 7.5 安装模式与依赖

```bash
# Lite 模式 - 无向量搜索，最小依赖
pip install recall-ai

# Cloud 模式 - 使用 API Embedding
pip install "recall-ai[cloud]"

# Local 模式 - 本地 Embedding 模型
pip install "recall-ai[local]"

# Enterprise 模式 - 企业级性能引擎
pip install "recall-ai[enterprise]"
```

| 模式 | 依赖 | 内存占用 |
|------|------|:--------:|
| lite | 无额外依赖 | ~80MB |
| cloud | faiss-cpu | ~100MB |
| local | sentence-transformers, faiss-cpu | ~500MB |
| enterprise | faiss-cpu, networkx, kuzu | ~600MB |

**核心依赖**（所有模式必装）：
- pydantic, spacy, jieba（NLP）
- litellm, openai, httpx（LLM）
- fastapi, uvicorn（Web）
- click, rich, numpy, psutil, schedule, pybloom-live

---

## 八、版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v4.1.0 | 2026-01-28 | LLM 关系/实体抽取增强，Episode 概念，实体摘要 |
| v4.0.0 | 2026-01-23 | 三时态模型，11层检索，矛盾检测系统 |
| v3.6.0 | 2026-01-20 | 语义去重，绝对规则系统，CoreSettings |
| v3.0.0 | 2026-01-18 | 8层检索，伏笔系统，持久条件 |

---

> 📝 **本文档自动生成于 2026-02-01，基于代码审计和计划文档综合整理**
