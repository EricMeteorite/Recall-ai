# Recall 7.0 — 通用记忆系统实施计划

> **日期**: 2026-02-24  
> **定位**: 纯通用记忆系统——存入 → 索引 → 关联 → 检索 → 压缩 → 扩展，任何场景即插即用  
> **原则**: 默认兼容现有主流调用路径；统一 API + metadata 扩展覆盖通用场景；通过显式能力开关控制跨 namespace 检索与高级推理，避免隐式串扰  
> **总工期（人工参考）**: ~83 工作日  
> **总工期（AI 实施）**: ~25-35 天  
> **当前评分**: 54/100 → **目标评分**: 95/100  
> **前置条件**: Phase 7.1 首日拆分 engine.py（facade 模式）+ 清理遗留代码

---

## 一、架构设计——可插拔后端系统（BAL）

### 1.1 核心思想：Backend Abstraction Layer

```
┌─────────────────────────────────────────────────────────────┐
│                       Recall Engine                          │
│                     (业务逻辑不变)                            │
├─────────────────────────────────────────────────────────────┤
│  Independent Services:                                       │
│  ┌─────────────────┐  ┌──────────────────┐                  │
│  │ EmbeddingService│  │  TenantRouter    │                  │
│  │ encode()/batch() │  │ get_backend(uid) │                  │
│  └─────────────────┘  └──────────────────┘                  │
├─────────────────────────────────────────────────────────────┤
│  Backend Abstraction Layer (7 接口):                         │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐ ┌─────────┐  │
│  │ Memory   │ │ Vector   │ │KnowledgeGraph  │ │Keyword  │  │
│  │ Backend  │ │ Backend  │ │   Backend      │ │Search   │  │
│  └──────────┘ └──────────┘ └────────────────┘ └─────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐              │
│  │FullText  │ │ Entity   │ │  Archive       │              │
│  │Search    │ │ Backend  │ │  Backend       │              │
│  └──────────┘ └──────────┘ └────────────────┘              │
├─────────────────────────────────────────────────────────────┤
│  Implementations (按规模自动选择):                            │
│  ┌─────────┐  ┌─────────┐  ┌────────┐  ┌────────┐         │
│  │  JSON   │  │  FAISS  │  │  JSON  │  │ N-gram │ ← Lite  │
│  │ SQLite  │  │IVF-HNSW │  │  Kuzu  │  │ FTS5   │ ← Std   │
│  │PostgreSQL│ │ Qdrant  │  │ Neo4j  │  │  ES    │ ← Scale │
│  │PG集群    │ │Qdrant集群│  │Nebula  │  │ES集群   │ ← Ultra │
│  └─────────┘  └─────────┘  └────────┘  └────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 统一后端接口定义（7 接口 + 2 服务）

```python
# recall/backends/base.py

class MemoryBackend(ABC):          # 14 方法
    add(memory: dict) -> str
    get(id: str) -> dict | None
    get_batch(ids: list[str]) -> list[dict]
    search(filters: dict, offset: int, limit: int) -> list[dict]
    update(id: str, data: dict) -> bool
    delete(id: str) -> bool
    delete_batch(ids: list[str]) -> int
    clear(user_id: str | None) -> int
    count(filters: dict | None) -> int
    list(offset: int, limit: int) -> list[dict]
    exists(id: str) -> bool
    get_by_user(user_id: str) -> list[dict]
    get_by_namespace(namespace: str) -> list[dict]
    get_recent(limit: int, user_id: str | None) -> list[dict]

class VectorBackend(ABC):          # 12 方法
    add(id: str, vector: ndarray) -> None
    add_batch(ids: list[str], vectors: ndarray) -> None
    search(query_vector: ndarray, top_k: int, filters: dict | None) -> list[tuple[str, float]]
    delete(id: str) -> None
    delete_batch(ids: list[str]) -> None
    clear() -> None
    count() -> int
    rebuild() -> None
    save() -> None
    load() -> None
    get(id: str) -> ndarray | None
    update(id: str, vector: ndarray) -> None

class KnowledgeGraphBackend(ABC):  # 9 方法
    add_entity(entity: dict) -> None
    add_relation(relation: dict) -> None
    get_entity(name: str) -> dict | None
    get_relations(entity_name: str) -> list[dict]
    search_entities(query: str) -> list[dict]
    traverse(start: str, depth: int, filters: dict | None) -> dict
    delete_entity(name: str) -> None
    delete_relation(id: str) -> None
    get_contradictions() -> list[dict]

class KeywordSearchBackend(ABC):   # 4 方法
    add(id: str, keywords: list[str]) -> None
    search(keywords: list[str], top_k: int) -> list[tuple[str, float]]
    delete(id: str) -> None
    clear() -> None

class FullTextSearchBackend(ABC):  # 5 方法
    add(id: str, text: str) -> None
    search(query: str, top_k: int) -> list[tuple[str, float]]
    delete(id: str) -> None
    clear() -> None
    rebuild() -> None

class EntitySearchBackend(ABC):    # 6 方法
    add(id: str, entities: list[str]) -> None
    search(entity_name: str, top_k: int) -> list[str]
    delete(id: str) -> None
    clear() -> None
    get_entity_memories(entity_name: str) -> list[str]
    rebuild() -> None

class ArchiveBackend(ABC):         # 6 方法
    archive(memories: list[dict]) -> int
    search(query: str, top_k: int) -> list[dict]
    restore(ids: list[str]) -> list[dict]
    delete(ids: list[str]) -> int
    count() -> int
    get_volumes() -> list[dict]

class EmbeddingService(ABC):       # 2 方法
    encode(text: str) -> ndarray
    encode_batch(texts: list[str]) -> ndarray

class TenantRouter(ABC):           # 1 方法
    get_backend(user_id: str) -> BackendSet
```

### 1.3 统一 API 设计（28 端点）

**核心原则**：无模式区分，`metadata: Dict[str, Any]` 驱动一切场景扩展。`character_id` 统一替换为 `namespace`（可表示项目/频道/话题等任意分组概念）。搜索默认全局，支持多 namespace 过滤。

#### 基础 API（10 端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/memories` | 存入记忆 `{content, metadata?}` |
| `POST` | `/v1/memories/batch` | 批量存入 |
| `POST` | `/v1/memories/search` | 搜索 `{query, filters?, top_k?}` |
| `GET` | `/v1/memories` | 列出（分页） |
| `GET` | `/v1/memories/{id}` | 获取单条 |
| `PUT` | `/v1/memories/{id}` | 更新 |
| `DELETE` | `/v1/memories/{id}` | 删除 |
| `DELETE` | `/v1/memories` | 清空 |
| `POST` | `/v1/context` | 构建上下文 |
| `GET` | `/health` | 健康检查 |

#### 图谱 API（5 端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v1/entities` | 列出实体 |
| `GET` | `/v1/entities/{name}` | 实体详情 |
| `GET` | `/v1/entities/{name}/related` | 关联实体 |
| `POST` | `/v1/graph/traverse` | 图遍历 |
| `GET` | `/v1/contradictions` | 矛盾列表 |

#### 管理 API（5 端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v1/stats` | 统计信息 |
| `GET/PUT` | `/v1/config` | 配置读写 |
| `POST` | `/v1/admin/rebuild-index` | 重建索引 |
| `POST` | `/v1/admin/consolidate` | 触发整合 |
| `GET` | `/v1/users` | 用户/namespace 列表 |

#### 数据管理 API（4 端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/data/export` | 数据导出 |
| `POST` | `/v1/data/import` | 数据导入 |
| `POST` | `/v1/data/backup` | 备份 |
| `POST` | `/v1/data/restore` | 恢复 |

#### 任务 API（4 端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/jobs/import` | 提交异步导入任务 |
| `GET` | `/v1/jobs/{id}` | 查询任务状态 |
| `GET` | `/v1/jobs` | 列出任务 |
| `DELETE` | `/v1/jobs/{id}` | 取消任务 |

---

## 二、实施策略

### 2.1 分批策略

| 批次 | Phase | 外部依赖 | 评分 | AI 时间 |
|:---:|:-----:|:--------:|:---:|:------:|
| **A1** | 7.1+7.2 | 无 | 54→75 | **10-14天** |
| **A2** | 7.3+7.4 | 无 | 75→84 | **7-10天** |
| **A3** | 7.5 | 无 | 84→88 | **4-5天** |
| **B** | 7.6+7.7 | Qdrant/PG/Nebula/ES/Redis | 88→95 | **4-6天** |
| | | | **总计** | **25-35天** |

### 2.2 Round 0 一次编写清单

| 类别 | 新建/修改文件 | 预计行数 |
|------|-------------|:-------:|
| BAL 抽象接口 | `recall/backends/base.py` | ~300 |
| JSON 后端适配 | `recall/backends/json_memory.py` 等 | ~500 |
| SQLite 后端 | `recall/backends/sqlite_memory.py`, `sqlite_fts.py` | ~600 |
| BackendFactory | `recall/backends/factory.py` | ~150 |
| 时间意图解析器 | `recall/processor/time_intent_parser.py` | ~450 |
| Event Linker | `recall/processor/event_linker.py` | ~400 |
| 话题聚类器 | `recall/processor/topic_cluster.py` | ~250 |
| 文档 Chunker | `recall/processor/document_chunker.py` | ~300 |
| 引擎改造 | `recall/engine.py`（精简+facade） | ~400 |
| BUG 修复 | 多文件 | ~100 |
| 死路径激活 | `recall/engine.py` | ~80 |
| consolidate() 实现 | `recall/engine.py` | ~150 |
| 安全中间件 | `recall/middleware/auth.py` + `server.py` | ~200 |
| 迁移工具 | `tools/migrate_backend.py` 等 | ~300 |
| 测试套件 | `tests/test_bal.py`, `test_sqlite.py` 等 | ~800 |
| **合计** | **~17 个新文件 + ~5 个修改文件** | **~5,280 行** |

### 2.3 收敛判定

**Batch A 完成条件：**

- [ ] `pytest tests/` 零失败
- [ ] `python -m recall start` 启动 <2秒
- [ ] add / search / delete / add_batch 端到端正常
- [ ] SillyTavern 插件通信正常（向后兼容）
- [ ] SQLite 后端 1 万条写入+搜索正常
- [ ] ElevenLayerRetriever 默认启用
- [ ] 10,000 条数据 search() <200ms
- [ ] 1 小时运行无内存泄漏

---

## 三、Phase 7.1 — BUG修复+遗留清理+架构拆分+接线（~11天）

**目标**：清理遗留代码，拆分 engine.py，修复全部 BUG，激活死代码

### 3.0 — 遗留代码清理（P0 前置，1天）

在任何其他工作之前，先清理不再需要的遗留代码：

| 操作 | 文件 | 行数变化 |
|------|------|:-------:|
| **删除** `recall/processor/foreshadowing.py` | 伏笔追踪器 | -1,234 |
| **删除** `recall/processor/foreshadowing_analyzer.py` | 伏笔分析器 | -852 |
| **删除** `recall/models/foreshadowing.py` | 伏笔模型 | -24 |
| **删除** `recall/processor/scenario.py` | 场景检测器 | -236 |
| **删除** `recall/mode.py` | 三模式管理 | -68 |
| **清理** `recall/engine.py` 伏笔方法 | 15 个伏笔方法 + 初始化 | -~800 |
| **清理** `recall/server.py` 伏笔端点 | foreshadowing 路由组 | -~740 |
| **清理** `recall/processor/consistency.py` | 移除非通用属性检测规则 | -~300 |
| **清理** `recall/processor/context_tracker.py` | 移除非通用 ContextType | -~200 |
| **重命名** `character_id` → `namespace` | 全项目 ~447 处引用（11个文件） | ~0（重命名） |
| **清理** `recall/graph/knowledge_graph.py` | 移除 RP_RELATION_TYPES | -~25 |
| **清理** 混合模块中零散非通用分支 | 18 个文件中 ~329 行 | -~200 |
| **合计** | | **-~4,679 行** |

清理后代码库从 ~37,658 行 → **~32,979 行**。

### 3.1.Z — engine.py Facade 拆分（2天）

> 原 engine.py 4,598 行、82 方法。清理后约 ~3,800 行。Facade 拆分进一步降低耦合。

| 新文件 | 抽取内容 | 预估行数 |
|--------|---------|:-------:|
| `recall/memory_ops.py` | `add()` + `add_turn()` + `add_batch()` + `delete()` + `update()` + `clear()` | ~1,500 |
| `recall/context_builder.py` | `build_context()` + 全部 `_build_*` 辅助方法 | ~500 |
| `recall/engine.py`（瘦身后） | 初始化 + search + 实体查询 + stats + facade 委托 | ~1,800 |

**关键约束**：RecallEngine 保留所有公开方法签名，内部委托给子模块 → **server.py 零改动、插件零影响**。

### 3.1.A — BUG 修复 + delete() 级联（3天）

| 任务 | 操作 |
|------|------|
| **A1** | 修复 ContradictionManager `.id` → `.uuid` |
| **A2** | 删除 `rebuild_vector_index` 重复定义 |
| **A3** | `add_turn()` 补充 `_metadata_index.add` |
| **A4** | 修复 CommunityDetector Kuzu 兼容性 |
| **A5** | 修复 KuzuGraphBackend.close() 释放连接 |
| **A6** | 修复 server.py 4 处默认值不一致 |
| **A7** | **`delete()` 级联补全（13 个存储位置全清理）** |
| **A8** | PromptManager 接入所有 processor（仅 default 模板） |
| **A9** | 修复 `get_entity_timeline()` 方法不存在 |
| **A10** | `add()`/`add_batch()` 向 TemporalIndex 写入 event_time |
| **A11** | `_get_memory_content_by_id()` O(n) → BAL 查询 |
| **A12** | **ScopedMemory LRU 内存保护**：限制最多 5000 条常驻内存，其余按需从磁盘读取。在 7.2 SQLite 到位前防止 OOM |
| **A13** | EntityIndex / ConsolidatedMemory 改为 WAL 增量写（参照 InvertedIndex 已有方案），消除每操作全量 JSON 重写 |

### 3.1.B — BAL 接口 + 通用关系（3天）

| 任务 | 操作 |
|------|------|
| **B1** | BAL 7 接口 + 2 服务完整定义 |
| **B2** | VectorBackend ABC 统一 VectorIndex/IVF |
| **B3** | EmbeddingService 剥离 |
| **B4** | TenantRouter 替代 MultiTenant 直接访问 |
| **B5** | 规则关系提取器增加通用模式（50+ 条规则：因果/商业/金融/技术/学术等） |
| **B6** | TextSearchBackend 正确拆分为 Keyword + FullText |
| **B7** | EpisodeBackend 接口 |
| **B8** | 图后端统一（JSON/Kuzu 二元分裂修复） |

### 3.1.C — 接线工程 + 死路径激活（1天）

| 任务 | 操作 |
|------|------|
| **C1** | 默认启用 ElevenLayerRetriever |
| **C2** | 自动切换 VectorIndexIVF（>1万数据时） |
| **C3** | ParallelRetriever 接入 + 三路并行 |
| **C4** | 激活 L2 时态过滤 |
| **C5** | 激活 L10 CrossEncoder |
| **C6** | 激活 L11 LLM Filter |
| **C7** | `_fulltext_weight` 接入检索逻辑 |
| **C8-C11** | 搜索 O(1)、LRU 缓存、全库去重 |

### 3.1.D — MCP + 引擎共享 + 容错（1天）

| 任务 | 操作 |
|------|------|
| **D1** | MCP clear_memories 工具 |
| **D2** | MCP/HTTP 共享单例引擎 |
| **D3** | MCP 错误处理 |
| **D4** | 实体提取降级容错 |
| **D5** | 47 个 `os.environ.get()` 集中到 config |
| **D6** | FEATURE-STATUS.md 修正（标记 13 项虚假声明） |
| **D7** | 版本号统一更新 v7.0 |

### Phase 7.1 验收标准

- [ ] 所有遗留代码已移除（伏笔/模式开关/非通用属性检测）
- [ ] engine.py 拆分完成（facade 模式，server.py 零改动）
- [ ] B01-B08 全部 BUG 已修复
- [ ] `delete()` 级联 13/13 存储位置
- [ ] ElevenLayerRetriever 默认启用
- [ ] BAL 7 接口已定义
- [ ] ParallelRetriever 接入
- [ ] `character_id` 全部重命名为 `namespace`
- [ ] 所有现有测试通过
- [ ] 评分 ≥68/100

---

## 四、Phase 7.2 — SQLite后端+核心功能补全+异步管道（~17天）

**目标**：JSON→SQLite，支持千万级数据，add_batch 完整对齐，异步写入管道

### 4.2.A — SQLiteMemoryBackend + FTS5（4天）

```python
# recall/backends/sqlite_memory.py — Schema
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    external_id TEXT,  -- 外部平台原始 ID（去重+更新用，配合 source+namespace 复合唯一）
    content TEXT NOT NULL,
    metadata JSON,
    user_id TEXT,
    session_id TEXT,
    namespace TEXT NOT NULL, -- 原 character_id
    source TEXT NOT NULL,    -- 数据来源平台（bilibili/twitter/github 等）
    category TEXT,
    event_time TEXT,
    importance REAL DEFAULT 0.5,  -- 重要度评分 0-1
    created_at REAL,
    UNIQUE(source, namespace, external_id),
    INDEX idx_user (user_id),
    INDEX idx_time (created_at),
    INDEX idx_namespace (namespace),
    INDEX idx_source (source),
    INDEX idx_external (external_id),
    INDEX idx_importance (importance),
    INDEX idx_source_namespace_time (source, namespace, created_at)
);
```

**跨 namespace 检索语义**：
- `search(filters={})` 默认仅搜当前 namespace（防止跨项目串扰）
- `search(filters={global: true})` 显式开启全局检索
- `search(filters={namespace: "bilibili"})` 搜单个 namespace
- `search(filters={namespace: ["bilibili", "twitter", "github"]})` 搜多个 namespace
- 全部结果必须返回 `source` + `namespace` + `external_id`，确保可追溯与可回放

```python
# recall/backends/sqlite_fts.py
# 替换 InvertedIndex + NgramIndex + FullTextIndex（三合一）
# 中文方案：jieba 预分词 → 空格分隔插入 FTS5
# 目标：在基准硬件与公开数据集下，P95 <200ms（详见验收基线）
```

### 4.2.B — engine.py BAL 适配（4天）

| 改造类别 | 说明 |
|----------|------|
| `_memories`/`_scopes` 直接访问 → BAL API | ~30 行 |
| JSON 文件直接 I/O → BAL 查询 | ~120 行 |
| 43 处 `dict.get()` 格式假设 → 统一格式 | ~100 行 |
| `delete()` 级联补全 | ~60 行 |
| `add_batch()` 缺失步骤补全 | ~50 行 |
| 初始化路径改造 | ~40 行 |
| **合计** | **~400 行修改** |

### 4.2.C — add_batch 对齐 + 迁移工具 + chunker（4天）

| 任务 | 说明 |
|------|------|
| `add_batch()` 完整性对齐 | 去重 + Episode + Archive + 缓存 |
| `add_batch()` upsert 语义 | `external_id` 已存在则更新，不重复插入 |
| **通用文档 chunker** | 见下方详细设计 |
| 数据导出/导入 API | `/v1/data/export`, `/v1/data/import` |
| 备份/恢复 API | `/v1/data/backup`, `/v1/data/restore` |
| JSON→SQLite 迁移工具 | 一键迁移 |
| v5→v7 综合迁移工具 | 含 namespace 重命名 |

**数据契约与幂等约束（必须项）**：
- 导入写入必须提供 `source` 与 `namespace`
- 当提供 `external_id` 时，按 `UNIQUE(source, namespace, external_id)` 执行 upsert
- 当无 `external_id` 时，使用 `content_hash + event_time` 作为幂等后备键
- 导入重放 3 次后总记录增量必须为 0（只允许更新，不允许重复新增）
- 时间字段统一 UTC ISO8601，缺失时回填 `created_at` 并标记 `metadata.time_inferred=true`

**通用文档 Chunker 详细设计**：

```python
# recall/processor/document_chunker.py
class DocumentChunker:
    """
    将长文本智能切片为可索引的记忆单元。
    
    切片策略（按数据类型自动选择）：
    - 对话记录: 按对话轮次切片，每 chunk 含完整一轮对话
    - 文章/网页: 按段落切片，大段落按 token 截断
    - 视频转录稿: 按时间戳段落切片（每 2-5 分钟一个 chunk）
    - 结构化数据: 按条目/记录切片
    
    Overlap 策略:
    - 相邻 chunk 重叠最后 2 句（~50-100 tokens）
    - 确保跨 chunk 边界的语义不丢失
    
    Parent-Child 关系:
    - 每个 chunk 记录 parent_id（原始文档 ID）
    - 搜索命中 chunk 后可展开到原文
    - metadata: {parent_id, chunk_index, total_chunks, source_type}
    
    参数:
    - max_chunk_tokens: 512 (默认)
    - overlap_tokens: 64 (默认)
    - source_type: auto | conversation | article | transcript | structured
    """
```

### 4.2.D — 安全基线 + 存储层加固（2天）

| 任务 | 说明 |
|------|------|
| API Key 可选认证 | FastAPI 中间件 |
| CORS 可配置 | 不再 `allow_origins=["*"]` |
| 危险端点保护 | `/v1/reset` 需认证 |
| Rate limiting | 基于 IP/API Key 限流 |
| 原子写入 | tmp + rename + fsync |
| 读写锁 | threading.RLock |

### 4.2.E — 测试+文档（1天）

| 任务 | 说明 |
|------|------|
| SQLite 后端全量测试 | 全部测试在 SQLite 模式通过 |
| 10K/100K 规模压力测试 | benchmark 套件 |
| CI 管道 | 无需手动启动服务器 |
| README 增加通用场景示例 | 不再以 RP 为主示例 |
| pyproject.toml 更新 | 入口点 + scale 依赖组 |

### 4.2.F — asyncio 异步写入管道（2天）

> **从 Phase 7.7 前移**：批量导入场景不能等到 7.7 才有异步写入，否则导入期间所有搜索请求被阻塞。

| 任务 | 说明 |
|------|------|
| `asyncio.Queue` 异步写入管道 | 非阻塞入库，写入排队不影响搜索 |
| 写入速率限制 | 可配置写入 QPS 上限，防止批量导入压垂系统 |
| 优雅停机 | 确保队列排空后再关闭 |
| 缓冲溢出处理 | 队列满时写入磁盘暂存，恢复后重放 |

### Phase 7.2 验收标准

- [ ] SQLite 后端通过全部测试
- [ ] JSON→SQLite 迁移工具可用  
- [ ] 基准环境压测通过：写入吞吐、搜索 P95/P99、峰值内存均达标（报告可复现）
- [ ] 启动 <2秒（标准配置）
- [ ] add_batch 功能与 add 完全对齐
- [ ] `external_id` upsert 语义正确工作
- [ ] 跨 namespace 搜索正常（全局/单个/多个）
- [ ] 数据导入/导出/备份/恢复 API 可用
- [ ] asyncio 异步写入管道工作正常
- [ ] 原子写入 + 读写锁全覆盖
- [ ] API Key 认证 + CORS + 限流工作
- [ ] 幂等回放测试通过（同批数据重放 3 次无重复写入）
- [ ] 回压策略生效（队列水位 >80% 返回 429 + Retry-After）
- [ ] 前台搜索在批量导入时退化 ≤20%（P95）
- [ ] 评分 ≥75/100

---

## 五、Phase 7.3 — 时间推理+事件关联+话题聚类（~14天）

**目标**：让系统能“用时间思考”——时间意图解析、事件自动关联、话题级聚类

> 这是通用记忆系统的核心能力：任何场景都需要理解"上周"、"去年"、"之前提到过"。

### 7.3.A — 时间意图解析器 + build_context 时间感知（4天）

```python
# recall/processor/time_intent_parser.py
class TimeIntentParser:
    """
    混合方案（正则优先 → LLM fallback）
    
    - 第一层: 正则模式匹配（<1ms）— 覆盖90%常见时间表达
      * 中/英文: 昨天/last week/过去N天/this month
      * ISO: YYYY-MM-DD..YYYY-MM-DD
    - 第二层: LLM fallback（~300ms）— 复杂/模糊表达
    
    预估 ~400-500 行
    """
```

| 任务 | 说明 |
|------|------|
| 时间意图解析器核心 | 从自然语言提取时间范围 |
| build_context() 传递 temporal_context | 激活 L2 时态过滤 |
| 图谱结果按时间排序 | 时间感知的图遍历 |
| TemporalIndex 性能修复 | O(n) → O(log n) bisect |

### 7.3.B — Event Linker（6天）

```python
# recall/processor/event_linker.py
class EventLinker:
    """
    新事件入库时自动搜索关联事件:
    1. 提取实体
    2. 搜索含相同实体的已有事件
    3. Embedding 预过滤（>0.7 才进入 LLM）→ 100候选→5-10个
    4. LLM 判定关联类型（CAUSED/FOLLOWS/RELATED/UNRELATED）
    5. 自动在图谱中添加边
    
    窗口策略: 24h→7d→30d→365d 自动扩展（候选<3时升级）
    因果链: 预算约束检索（max_depth<=20, max_nodes<=200, max_latency_ms<=800）
    清理: FOLLOWS 90天 + 低 importance → 归档
    
    link_batch() 批量关联:
    - 支持批量导入场景（每2小时导入10000条）
    - 先批量 Embedding 编码 → 先批量候选筛选 → 再批量 LLM 判定
    - 避免逐条调用 LLM 的巨大开销
    """
```

### 7.3.C — 话题聚类关联层（3天）

> **审计发现的关键缺口**：EventLinker 仅基于“实体重叠 + Embedding 相似度”关联。两条内容讨论同一话题但无共同实体时不会被关联。

```python
# recall/processor/topic_cluster.py
class TopicCluster:
    """
    话题级关联层：
    1. 入库时 LLM 提取 2-5 个话题标签（如 "AI行业"/"裁员"/"融资"）
    2. 相同话题标签的记忆自动建立 TOPIC_RELATED 关联
    3. 支持上下位概念扩展（"OpenAI" is-a "AI公司" is-a "科技公司"）
    4. 话题检索：搜索某话题下的所有相关记忆
    
    此能力让系统能关联：
    - "OpenAI 裁员" 和 "AI 行业寒冬" (无共同实体但话题相关)
    - "张三辞职" 和 "张三创业" (同一话题线)
    """
```

| 任务 | 说明 |
|------|------|
| 话题标签提取 | LLM 提取 + 关键词 fallback |
| 话题索引 | SQLite 表 `memory_topics(memory_id, topic)` |
| 话题检索 API | `/v1/memories/search` 支持 `filters.topics` |
| 全局关联扫描 | 每周一次低开销全局话题关联，解决 >365天数据孤岛问题 |

### Phase 7.3 验收标准

- [ ] "上周"/"yesterday"/"过去3天" 正确解析
- [ ] Event Linker 正确关联相关事件（关联准确率 ≥80%）
- [ ] `link_batch()` 支持 5000 条批量关联 <60秒
- [ ] 窗口策略扩展至 365 天，跨年事件可关联
- [ ] 话题聚类层正确工作（无共同实体的相关内容可关联）
- [ ] Embedding 预过滤将候选从 100→5-10
- [ ] build_context 包含时间相关记忆
- [ ] TemporalIndex O(log n) 查询
- [ ] 评分 ≥80/100

---

## 六、Phase 7.4 — 大规模记忆优化（~6天）

**目标**：图遍历提升、记忆压缩整合、importance 加权

### 6.4.A — 检索优化（2天）

| 任务 | 说明 |
|------|------|
| 图遍历 2-3跳 + 50 条关系上限 | 图谱推理 |
| MMR 多样性选择（λ=0.7） | 去冗余 |
| metadata 预过滤 | 检索前按 metadata 筛选 |
| build_context max_tokens 自适应 | 自适应上下文长度 |
| importance 加权检索 | `score = relevance*0.5 + importance*0.3 + recency*0.2` |

**importance 全链路**：
1. `add()` 新增 `importance` 可选参数（用户显式标记）
2. LLM 自动评估（prompt: "此信息的长期参考价值 0-1"）
3. SQLite 字段 `importance REAL DEFAULT 0.5`
4. 检索时融合 importance 到排序分数
5. 用户 API `PUT /v1/memories/{id}` 可更新 importance

### 6.4.B — consolidate() 实现（双层策略）（4天）

> **审计修正**：原方案“压缩 50:1”会不可逆丢失低 importance 记忆细节，违反“100%不遗忘”承诺。改为双层策略：摘要辅助热检索 + 原文永久保留。

```python
# 记忆双层策略（保证 100% 不遗忘）
#
# 热层（热检索）:
#   - 每实体一条结构化摘要（≤ 4000 tokens）
#   - 摘要有独立向量索引，参与常规搜索
#   - 热层命中后自动展开到原文细节
#
# 冷层（原文存档）:
#   - **原文永远不删除**，只标记为 archived
#   - VolumeManager 分卷存储，按需加载
#   - 原文可通过 archive search 检索
#
# 触发策略（基于数据量，非固定轮次）:
#   - 每累积 1000 条未压缩记忆触发一次实体摘要更新
#   - 每累积 5000 条触发一次全量摘要重建
#   - 手动: POST /v1/admin/consolidate
#
# 摘要压缩比: ~15:1 (实测合理值，原 50:1 信息损失太大)
# 保护: importance ≥ 0.7 的记忆保留在热层，不参与压缩
```

| 任务 | 说明 |
|------|------|
| consolidate() 双层架构 | 热层摘要 + 冷层原文，原文永不删除 |
| 基于数据量的触发逻辑 | 每 1000 条增量更新，每 5000 条全量重建 |
| LLM 摘要生成 | 保留关键事实、因果关系、时间节点 |
| 归档记忆向量搜索 | VolumeManager 搜索接入，热层命中可展开 |
| importance 保护机制 | 高重要性记忆保留在热层 |

### Phase 7.4 验收标准

- [ ] build_context 使用 importance 加权
- [ ] consolidate() 双层策略工作（原文永不删除）
- [ ] 热层摘要命中后可展开到原文
- [ ] 归档数据可搜索
- [ ] MMR 去冗余生效
- [ ] 评分 ≥84/100

---

## 七、Phase 7.5 — 安全+可观测+国际化+任务管理（~10天）

**目标**：生产级安全、监控、日志、Entity Resolution、异步导入任务管理

### 7.5.A — 可观测性（3天）

| 任务 | 说明 |
|------|------|
| 结构化日志框架 | logging → structlog |
| Prometheus 指标导出 | 请求量/延迟/错误率 |
| 请求追踪（trace_id） | 分布式追踪基础 |
| Slow Query 告警 | >200ms 的查询自动记录 |

### 7.5.B — 高级能力（4天）

| 任务 | 说明 |
|------|------|
| **事件链 API `get_event_chain()`** | 给定事件返回因果链，深度限制 `max_depth=20`，置信度沿链衰减（每跳 ×0.9） |
| **Entity Resolution（实体消歧）** | 合并 "OpenAI"/"openai"/"Open AI" |
| 时间衰减加权检索 | 近期记忆权重更高 |
| **异步导入任务管理 (Job API)** | 见下方详设 |

**Job API 设计**（支撑“每2小时批量导入”场景）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/jobs/import` | 提交异步导入任务，返回 `job_id` |
| `GET` | `/v1/jobs/{id}` | 查询任务状态（pending/running/done/failed） |
| `GET` | `/v1/jobs` | 列出所有任务（分页） |
| `DELETE` | `/v1/jobs/{id}` | 取消进行中的任务 |

任务特性：
- 状态追踪：pending → running → done/failed/partial
- 断点续传：记录已导入的偏移量，中断后可从上次位置继续
- 导入去重：基于 `external_id` 或 `content_hash` 自动去重
- 重试机制：单条失败不影响整批，记录失败明细

### 7.5.C — 国际化+加固（2天）

| 任务 | 说明 |
|------|------|
| Prompt 英文变体 | default + en 双语 |
| 错误信息 i18n 框架 | 中/英 |
| 配置验证层 | 启动时检查所有配置项 |
| 数据备份/恢复策略 | 定期自动备份 |

### Phase 7.5 验收标准

- [ ] structlog 输出结构化 JSON 日志
- [ ] Prometheus /metrics 端点可用
- [ ] Entity Resolution 合并准确率 ≥90%
- [ ] 事件链 API 返回正确因果序列（深度≤20跳）
- [ ] Job API 支持异步导入 + 状态追踪 + 断点续传
- [ ] 英文 prompt 可用
- [ ] 评分 ≥88/100

---

## 八、Phase 7.6 — 分布式后端扩展（目标容量：10亿-100亿级，~20天）

**目标**：Qdrant/PostgreSQL/NebulaGraph/ES 全套分布式后端与分层 SLO 落地

### 8.6.A — Qdrant 向量后端（5天）

```python
# recall/backends/qdrant_vector.py
# 实现 VectorBackend ABC
# 支持: 过滤搜索、批量写入、在线扩容
# 目标：分层 SLO（P50/P95/P99）按压测基线达标
```

### 8.6.B — PostgreSQL 记忆后端（5天）

```python
# recall/backends/pg_memory.py
# 实现 MemoryBackend ABC
# 支持: 分区表、读写分离、连接池
# JSONB metadata + GIN 索引
```

### 8.6.C — NebulaGraph 图后端（5天）

```python
# recall/backends/nebula_graph.py
# 实现 KnowledgeGraphBackend ABC
# 目标：图遍历延迟按压测基线达标，并给出可复现实验脚本
```

### 8.6.D — Elasticsearch 全文后端（3天）

```python
# recall/backends/es_fulltext.py
# 实现 FullTextSearchBackend + KeywordSearchBackend ABC
# 中文分词: ik_analyzer
```

### 8.6.E — BackendFactory + 迁移（2天）

| 任务 | 说明 |
|------|------|
| BackendFactory 自动选择 | 检测环境自动选 Lite/Std/Scale/Ultra |
| 在线迁移工具 | SQLite→PG 灰度迁移（允许秒级只读窗口，RTO/RPO 有明确指标） |
| 后端健康检查 | 自动降级（PG 不可用→回退 SQLite） |

### Phase 7.6 验收标准

- [ ] 四大后端全部通过 BAL 接口测试
- [ ] BackendFactory 自动选择正确
- [ ] 分层 SLO 达标（P50/P95/P99 + 写入吞吐 + 恢复时长）
- [ ] SQLite→PG 迁移工具可用
- [ ] 月度恢复演练达标（RTO ≤30min，RPO ≤5min）
- [ ] 评分 ≥92/100

---

## 九、Phase 7.7 — 缓存+极致优化（~3天）

**目标**：Redis 缓存层、可视化

> 注：asyncio 异步写入管道已前移至 Phase 7.2.F

### 9.7.A — Redis 缓存（2天）

| 任务 | 说明 |
|------|------|
| Redis 热数据缓存 | 最近搜索结果 + 频繁访问实体 |
| 缓存失效策略 | 记忆更新/删除时清除相关缓存 |
| 缓存内存预算 | 可配置最大缓存内存（默认 256MB） |
| 数据生命周期管理 | 自动归档、过期策略 |
| 连接池管理 | aioredis 连接复用 |

### 9.7.B — 监控+可视化（2天）

| 任务 | 说明 |
|------|------|
| Grafana 监控仪表板 | 预置 dashboard 模板 |
| 交互式图谱可视化 | 浏览器端知识图谱探索 |

### Phase 7.7 验收标准

- [ ] Redis 缓存命中率 >80%（热数据）
- [ ] 缓存失效策略正确（更新/删除后缓存清除）
- [ ] Grafana 可用
- [ ] 评分 ≥95/100

---

## 十、里程碑评分表

| 阶段 | 记忆完整性 | 可发现性 | 时间关联 | 因果关联 | 扩展性 | 容错性 | 集成性 | 总分 |
|------|:---------:|:-------:|:------:|:------:|:-----:|:-----:|:-----:|:----:|
| v5.0 当前 | 52 | 72 | 55 | 62 | 35 | 38 | 72 | **54** |
| 7.1 后 | 70 | 80 | 55 | 62 | 40 | 55 | 78 | **68** |
| 7.2 后 | 85 | 82 | 58 | 62 | 68 | 72 | 82 | **75** |
| 7.3 后 | 88 | 88 | 82 | 82 | 68 | 74 | 85 | **82** |
| 7.4 后 | 92 | 90 | 84 | 84 | 70 | 78 | 88 | **85** |
| 7.5 后 | 94 | 92 | 86 | 86 | 72 | 86 | 92 | **89** |
| 7.6 后 | 94 | 94 | 86 | 86 | 95 | 90 | 95 | **93** |
| 7.7 后 | 96 | 96 | 88 | 88 | 98 | 95 | 98 | **95** |

> 注：7.2 后扩展性由 65→68（async管道前移），容错性由 70→72（LRU内存保护）；7.3 后因果关联由 80→82（话题聚类加分）；7.4 后记忆完整性由 90→92（双层策略保证不遗忘）

---

## 十一、风险评估

| 风险 | 严重度 | 缓解措施 |
|------|:-----:|---------|
| engine.py 拆分引入回归 | **高** | Facade 模式保持签名不变 + 全量测试 |
| consolidate() 从零实现质量风险 | **高** | 双层策略（原文永不删除）保证安全网 |
| Entity Resolution 精度不足 | **中** | 先用简单规则（大小写+别名表），后加 LLM |
| SillyTavern 插件兼容性 | **中** | 旧端点返回空数组而非 404 |
| SQLite 并发写入限制 | **低** | WAL 模式 + 写入队列 |
| EventLinker 话题聚类准确率 | **中** | 先用关键词提取，迭代加 LLM |
| 跨后端事务一致性（Phase 7.6） | **高** | add 同时写 PG+Qdrant+ES，部分失败时采用补偿重试机制 |
| Phase 7.6 工期过于乐观 | **中** | 4大后端可分批交付，不必一次性全部完成 |
| 批量导入压垂系统 | **中** | asyncio 管道 + 写入速率限制 + 队列溢出磁盘暂存 |
