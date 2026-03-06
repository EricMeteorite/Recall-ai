# Recall v7.0.10 长期稳定性审计报告

> 审计日期: 2026-03-02  
> 目标: 1-3 年连续运行、数据持续增长场景下的故障风险评估  
> 审计范围: 内存边界、关机安全、配置一致性、错误恢复、线程安全、clear 完整性

---

## 0. 总览

| 严重级 | 数量 | 说明 |
|--------|------|------|
| **CRITICAL** | 3 | 会导致数据丢失或进程不可用 |
| **HIGH** | 5 | 显著影响长期运行稳定性 |
| **MEDIUM** | 8 | 潜在风险，极端条件下触发 |
| **LOW** | 5 | 代码质量/可维护性问题 |

---

## 1. 内存边界 (Memory Bounds)

### 1.1 ElevenLayerRetriever 缓存 — ✅ 已有 LRU 保护

| 缓存 | 位置 | 上限 | 驱逐策略 |
|------|------|------|---------|
| `_content_cache` | eleven_layer.py:130 | 10,000 条 | 超限时清除最早一半 |
| `_metadata_cache` | eleven_layer.py:131 | 10,000 条 | 同上 |
| `_entities_cache` | eleven_layer.py:132 | 10,000 条 | 同上 |

**评估**: v7.0.2 已添加 `_cache_max_size = 10000` 和 `_evict_cache_if_needed()`。**此项安全**。

### 1.2 EightLayerRetriever._content_cache — ⚠️ 无 LRU 保护

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/retrieval/eight_layer.py | L125 | `_content_cache: Dict[str, str] = {}` 无任何大小限制或驱逐机制 | **HIGH** |

**分析**: `EightLayerRetriever` 的 `_content_cache` 是一个无界 dict。虽然 v7.0 默认使用 `ElevenLayerRetriever`，但 `EightLayerRetriever` 仍然是 engine.py 中实际初始化的检索器（engine.py:414 `self.retriever = EightLayerRetriever(…)`），且 `_rebuild_content_cache()` 在启动时将**所有用户所有记忆**加载到此缓存中。当记忆量达到数万条时，这会导致数百 MB 甚至 GB 级内存占用。

**建议**: 为 `EightLayerRetriever._content_cache` 添加与 `ElevenLayerRetriever` 相同的 LRU 驱逐机制。

### 1.3 NgramIndex._raw_content — ✅ 已有 LRU 保护

| 文件 | 行 | 上限 | 驱逐策略 |
|------|-----|------|---------|
| recall/index/ngram_index.py | L60 | `_raw_content_max_size = 20,000` | 超限时清除最早一半 |

**评估**: v7.0.3 已添加。磁盘 JSONL 兜底搜索确保被驱逐数据仍可检索。**此项安全**。

### 1.4 ScopedMemory.MAX_MEMORIES — ⚠️ 硬上限导致数据丢失

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/storage/multi_tenant.py | L27 | `MAX_MEMORIES = 5000`，超出后最旧记忆被永久驱逐 | **CRITICAL** |

**分析**: `_evict_oldest()` 将记忆从 `_memories` 列表中删除并**写回磁盘**（通过 `_save()`），即 JSON 文件中也会被删除。虽然有 VolumeManager 归档安全网和驱逐回调（v7.0.3），但：
1. 归档仅在 NgramIndex 或 retriever 缓存中仍有原文时才有效
2. 如果这两处都已被 LRU 驱逐，归档内容为空
3. 驱逐回调依赖 `_on_evict_callback` 被正确设置（单元测试外的 ScopedMemory 实例可能遗漏）

**影响**: 1 年+连续运行的 RP 场景，5000 条记忆约 2-4 个月就会触及上限。之后每增加 1 条就丢失 1 条最旧记忆。

**建议**: 迁移到 SQLite (WAL) 后端，彻底移除硬上限。

### 1.5 KnowledgeGraph (JSON backend) nodes/edges — ⚠️ 无内存上限

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/graph/backends/json_backend.py | L68-71 | `nodes: Dict`, `edges: Dict`, `outgoing: Dict`, `incoming: Dict` 无限增长 | **HIGH** |
| recall/graph/temporal_knowledge_graph.py | L168-170 | `nodes: Dict`, `edges: Dict`, `episodes: Dict` 无限增长 | **HIGH** |

**分析**: JSON 图后端将全部节点/边加载到内存中。在 10 万+节点的场景下，内存占用约 1GB+。没有任何 LRU 或分页机制。

**影响**: 长期使用后图谱持续膨胀，导致 OOM 或启动耗时过长。

### 1.6 ConsistencyChecker — ⚠️ 无界内存字典

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/processor/consistency.py | L333 | `entity_facts: Dict` — 随对话增长无限积累 | **MEDIUM** |
| recall/processor/consistency.py | L335 | `relationships: Dict` — 同上 | **MEDIUM** |
| recall/processor/consistency.py | L337 | `timelines: Dict` — 同上 | **MEDIUM** |
| recall/processor/consistency.py | L338 (推断) | `negations: Dict` — 同上 | **MEDIUM** |

**分析**: 这些字典在每次 `check()` 时从 `existing_memories` 重新构建，**不是**进程生命周期内的持久缓存。但 `check()` 传入的 `existing_memories` 可能包含大量条目（最多 5000 条 ScopedMemory），每次 check 都要遍历全部，性能会随数据量线性退化。

**影响**: 非 OOM 风险，但性能退化风险（每次 add 操作伴随一个 O(n) check）。

### 1.7 InvertedIndex.index — ⚠️ 无界增长

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/inverted_index.py | L19 | `index: Dict[str, Set[str]]` — 关键词→记忆ID 映射无限增长 | **MEDIUM** |

**分析**: 倒排索引的关键词集合随语料增长而线性增长。10 万条记忆可能产生 50 万+关键词条目。由于使用 `defaultdict(set)`，内存占用可控（~100MB/10 万条）。WAL compaction 确保磁盘写入受控。

### 1.8 FullTextIndex — ⚠️ 无界增长

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/fulltext_index.py | L90-96 | `inverted_index`, `doc_info`, `doc_freq` 全部无界 | **MEDIUM** |

**分析**: BM25 索引的三个核心字典随文档数线性增长。与 InvertedIndex 类似的增长模式。

### 1.9 _rebuild_content_cache() — ⚠️ 启动时加载全部记忆到内存

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/engine.py | L1864-1901 | 启动时遍历所有用户的 `memories.json` 并全部加载到 `retriever._content_cache` | **CRITICAL** |

**分析**: 此方法在引擎启动时执行（engine.py:212）。它遍历**全部用户目录**下的所有 `memories.json`，将每条记忆的 content、metadata、entities 全部缓存到 `self.retriever.cache_content()`（EightLayerRetriever，无 LRU 限制）。

在 10 万条记忆（平均每条 500 字符）的场景下，仅 content 缓存就约 200MB+。加上 metadata 和 entities 缓存，总计可达 500MB-1GB。

**影响**: 启动时间随数据量线性增长（可能达到分钟级），且内存占用不可控。

---

## 2. 关机安全 (Shutdown Safety — atexit)

| 组件 | 文件 | atexit | 状态 | 严重级 |
|------|------|--------|------|--------|
| EntityIndex | recall/index/entity_index.py:51 | `atexit.register(self._shutdown_flush)` | ✅ v7.0.10 已添加 | — |
| InvertedIndex | recall/index/inverted_index.py:27 | `atexit.register(self.flush)` | ✅ | — |
| MetadataIndex | recall/index/metadata_index.py:26 | `atexit.register(self.flush)` | ✅ | — |
| TemporalIndex | recall/index/temporal_index.py:161 | `atexit.register(self._atexit_flush)` | ✅ v7.0.9 已添加 | — |
| FullTextIndex | recall/index/fulltext_index.py:110 | `atexit.register(self._atexit_flush)` | ✅ v7.0.8 已添加 | — |
| TemporalKnowledgeGraph | recall/graph/temporal_knowledge_graph.py:190 | `atexit.register(self._atexit_flush)` | ✅ | — |
| JSONGraphBackend | recall/graph/backends/json_backend.py:78 | `atexit.register(self.flush)` | ✅ | — |
| **VectorIndex** | recall/index/vector_index.py | **无 atexit** | ❌ | **HIGH** |
| **NgramIndex** | recall/index/ngram_index.py | **无 atexit** | ❌ | **MEDIUM** |
| **EpisodeStore** | recall/storage/episode_store.py | **无 atexit** | ❌ | **LOW** |
| **ContradictionManager** | recall/graph/contradiction_manager.py | **无 atexit** | ❌ | **LOW** |
| **ConsolidationManager** | recall/processor/consolidation.py | **无 atexit** | ❌ | **LOW** |

### 2.1 VectorIndex 无 atexit — ⚠️

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/vector_index.py | 全文件 | `VectorIndex` 没有注册 `atexit`，仅在 `add()` 每 100 条时保存 | **HIGH** |

**分析**: `VectorIndex.add()` 在 `len(turn_mapping) % 100 == 0` 时才调用 `_save()`。如果进程在第 50 次 add 后被杀死，最多丢失 99 条向量。FAISS 索引文件本身不支持增量写入，只能全量 dump。

**建议**: 添加 `atexit.register(self._save)` 或 `atexit.register(self.close)`。

### 2.2 NgramIndex 无 atexit — ⚠️

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/ngram_index.py | 全文件 | 名词短语索引仅在 `len(_raw_content) % 100 == 0` 时保存 | **MEDIUM** |

**分析**: 原文通过 `append_raw_content()` 增量写入 JSONL（不丢数据），但名词短语索引 `noun_phrases` 仅周期性保存。最多丢失 99 次 add 的名词短语索引（原文不丢）。

**建议**: 添加 `atexit.register(self.save)`。

### 2.3 EpisodeStore / ContradictionManager / ConsolidationManager 无 atexit — LOW

**分析**: 
- `EpisodeStore` 每次 `save()` 后立即追加到 JSONL 文件，实际丢失风险低。
- `ContradictionManager` 的 `_save()` 在每次 `detect()` 后调用。
- `ConsolidationManager` 是触发式操作，非增量写入。

这三者丢失数据的影响相对较小。

---

## 3. 配置一致性 (Configuration Consistency)

### 3.1 RecallConfig.from_env() — ✅ 全面覆盖

`RecallConfig` 在 `config.py:164-664` 中定义了 100+ 个配置项，并在 `from_env()` 中通过 `os.environ.get()` 一一读取。每个字段都有明确的默认值。

### 3.2 RECALL_RATE_LIMIT_RPM 一致性 — ✅ 一致

| 位置 | 环境变量 | 默认值 |
|------|---------|--------|
| config.py:308 | `RECALL_RATE_LIMIT_RPM` | `60` |
| middleware/rate_limit.py:69 | `RECALL_RATE_LIMIT_RPM` (fallback `RECALL_RATE_LIMIT`) | `0` (禁用) |

**注意**: `RateLimitMiddleware` 读取 `RECALL_RATE_LIMIT_RPM` 的默认值是 `0`（禁用），而 `RecallConfig` 的默认值是 `60`。但中间件直接从 `os.environ` 读取，不走 `RecallConfig`。这意味着：
- 如果用户不设置环境变量，中间件默认**禁用**限速，而 RecallConfig 报告默认 60 RPM
- 这不是 bug（中间件的"默认禁用"是有意为之），但可能造成混淆

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/middleware/rate_limit.py:69 | vs config.py:308 | 默认值不一致 (0 vs 60) | **LOW** |

### 3.3 TripleRecallConfig.from_env() 绕过 RecallConfig — ⚠️

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/config.py:615-637 | `TripleRecallConfig.from_env()` | 直接使用 `os.getenv()` + 自己的默认值，绕过 `RecallConfig` | **LOW** |

**分析**: `TripleRecallConfig.from_env()` 和 `RecallConfig.from_env()` 都读取 `TRIPLE_RECALL_*` 环境变量，但默认值在两处分别定义。目前默认值一致，但未来修改一处时可能遗漏另一处。

---

## 4. 错误恢复 (Error Recovery)

### 4.1 JSON 文件损坏恢复

| 组件 | 恢复策略 | 严重级 |
|------|---------|--------|
| EntityIndex | 快照损坏 → `except` 吞掉异常，空索引启动。WAL 回放时跳过损坏行。**WAL 可部分恢复** | **MEDIUM** |
| InvertedIndex | 主文件 `json.load` **无 try-except**，损坏直接崩溃 | **HIGH** |
| MetadataIndex | 主文件 `json.load` **无 try-except**，损坏直接崩溃 | **HIGH** |
| ScopedMemory | `_load()` 有 `except`，损坏时空列表启动 | ✅ |
| JSONGraphBackend | `json.load` 有 `except`，损坏时空图启动 + 警告 | ✅ |
| EpisodeStore | `json.loads` per line，单行损坏不影响其他 | ✅ |
| TemporalKnowledgeGraph | `_load()` 有 `except`，损坏时空图启动 | ✅ |
| FullTextIndex | `_load()` 有 `except`，损坏时空索引启动 | ✅ |

#### **InvertedIndex._load() — 主文件损坏无保护**

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/inverted_index.py | L33-37 | `json.load(f)` 无 try-except，`inverted_index.json` 损坏时抛 `JSONDecodeError` 导致引擎初始化失败 | **HIGH** |

**代码**:
```python
def _load(self):
    if os.path.exists(self.index_file):
        with open(self.index_file, 'r', encoding='utf-8') as f:
            data = json.load(f)  # <-- 无保护
```

WAL 回放部分有 `try-except`（跳过损坏行），但主文件加载没有。

#### **MetadataIndex._load() — 同样无保护**

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/metadata_index.py | L160-170 | `json.load(f)` 无 try-except | **HIGH** |

### 4.2 FAISS 索引损坏恢复 — ⚠️

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/vector_index.py | L149-152 | `faiss.read_index()` 失败时无恢复机制 | **MEDIUM** |

**分析**: `VectorIndex._load()` 中 `faiss.read_index()` 如果文件损坏会抛异常。外层没有 try-except，但实际上由于 `_load()` 被 `self.index` property 懒加载调用，异常会传播到搜索/添加操作。此时整个向量索引不可用。

**建议**: 捕获异常建空索引，并记录警告。

### 4.3 WAL 部分写入恢复 — ✅ 安全

**EntityIndex WAL**: JSONL 格式，每行一条 JSON。部分写入的最后一行会在 `json.loads()` 时产生 `JSONDecodeError`，被 `except` 跳过。**不影响已有数据**。

**InvertedIndex WAL**: 同上，单行损坏跳过。

### 4.4 进程在写入期间被杀死 — ⚠️

| 场景 | 保护机制 | 风险 |
|------|---------|------|
| 原子写入（tmp+replace）| `atomic_json_dump()` 使用 tmp + fsync + `os.replace()` | ✅ 安全 |
| FAISS 写入 | `faiss.write_index()` 不是原子的 | **MEDIUM** — 断电时 `.faiss` 文件可能损坏 |
| JSONL 追加 | append 模式写入，部分写入只影响最后一行 | ✅ 安全 |
| ScopedMemory `_save()` | 通过 `atomic_json_dump()` | ✅ 安全 |

**FAISS 写入非原子**:

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/index/vector_index.py | L173 | `faiss.write_index(self._index, self.index_file)` 非原子操作 | **MEDIUM** |

**建议**: 先写到 `.tmp` 文件再 `os.replace()`。

---

## 5. 线程安全 (Thread Safety)

### 5.1 RecallEngine 无锁保护 — ⚠️

| 文件 | 行 | 问题 | 严重级 |
|------|-----|------|--------|
| recall/engine.py | 全文件 | `RecallEngine` 及 `MemoryOperations` 没有任何锁。所有共享可变状态（索引、缓存、图谱）在并发访问时可能 race | **CRITICAL** |

**分析**: Recall 的 HTTP 服务通过 FastAPI + uvicorn 运行，uvicorn 默认单线程事件循环。但：
1. `add()` 中调用 `ThreadPoolExecutor`（如 NgramIndex.raw_search_parallel）
2. 如果用户配置 `--workers > 1` 或使用多进程部署，所有索引/缓存都不安全
3. `ElevenLayerRetriever._content_cache` 等 dict 在 CPython 中有 GIL 保护单线程写安全，但在多线程读写重叠时仍可能出问题

**具体 race condition**:
- `InvertedIndex.add()` 写入 WAL + 内存 dict，`search()` 同时读取 dict
- `ScopedMemory.add()` + `_evict_oldest()` + `search()` 同时操作 `_memories` list
- `EntityIndex._append_wal()` + `_compact()` 都对 WAL 文件和快照文件操作

**影响**: 在 FastAPI 单线程 async 模式下通常安全（同步操作阻塞事件循环），但：
- 如果使用 `run_in_executor()` 或后台线程调用 engine 方法，会有 race
- NgramIndex 的 `ThreadPoolExecutor` 仅读取 `_raw_content`（read-only），相对安全

**评估**: 当前部署模式（单 worker + async）下风险较低，但多 worker 部署会出问题。

### 5.2 RateLimitMiddleware — ✅ 线程安全

`RateLimitMiddleware._buckets` 通过 `self._lock = threading.Lock()` 保护。定期清理 stale buckets。**此项安全**。

### 5.3 TaskManager — ✅ 线程安全

`TaskManager` 使用 `self._task_lock = threading.Lock()` 保护所有操作。**此项安全**。

---

## 6. clear() 完整性 (Clear Completeness)

### 6.1 clear(user_id) — 覆盖 22 个存储位置

`MemoryOperations.clear()` (memory_ops.py:2214-2413) 级联清理 22 个存储位置：

| # | 组件 | 方法 | 状态 |
|---|------|------|------|
| 1 | ScopedMemory | `scope.clear()` | ✅ |
| 2 | TemporalKnowledgeGraph | `clear_user(user_id)` | ✅ |
| 3 | EntityIndex | `remove_by_turn_references()` | ✅ |
| 4 | VectorIndex | `remove_by_doc_ids()` | ✅ |
| 5 | ConsolidatedMemory | `remove_by_memory_ids()` | ✅ |
| 6 | InvertedIndex | `remove_by_memory_ids()` | ✅ |
| 7 | NgramIndex | `remove_by_memory_ids()` | ✅ |
| 8 | FullTextIndex | `remove_by_doc_ids()` | ✅ |
| 9 | MetadataIndex | `remove_batch()` | ✅ (v5.0) |
| 10 | ForeshadowingTracker | `clear_user()` | ✅ |
| 11 | ContextTracker | `clear_user()` | ✅ |
| 12 | ForeshadowingAnalyzer | `clear_buffer()` | ✅ |
| 13 | EpisodeStore | `clear_user()` | ✅ |
| 14 | VolumeManager | `clear_user()` or `remove_by_memory_id()` | ✅ (v7.0.2) |
| 15 | VectorIndexIVF | `remove_by_doc_ids()` | ✅ (v7.0.2) |
| 16 | Retriever 缓存 | `del _content_cache[mid]` 等 | ✅ (v7.0.2) |
| 17-19 | BAL 后端 | `delete(mid)` | ✅ (v7.0.2) |
| 20 | EventLinker | `unlink(mid)` | ✅ (v7.0.2) |
| 21 | TopicCluster | `clear_user()` | ✅ (v7.0.7) |
| 22 | ContradictionManager | `clear_user()` | ✅ (v7.0.8) |

**遗漏项**:

| 问题 | 严重级 |
|------|--------|
| `clear(user_id)` 不清理 `TemporalIndex`（时态索引。TemporalIndex 没有 `clear_user()` 方法，只有全清 `clear()`）| **MEDIUM** |
| `clear(user_id)` 不清理 `FullTextIndex` 内的 BM25 全局统计（doc_count, avg_doc_length 等仍包含已删除文档的贡献）| **LOW** |

### 6.2 clear_all() — 覆盖 21 个存储位置

`MemoryOperations.clear_all()` (memory_ops.py:2416-2614) 级联清理：

| # | 组件 | 状态 |
|---|------|------|
| 1 | 所有用户 ScopedMemory | ✅ |
| 2 | 统一图谱 | ✅ |
| 3 | EntityIndex | ✅ |
| 4 | ConsolidatedMemory | ✅ |
| 5 | VectorIndex | ✅ |
| 6 | InvertedIndex | ✅ |
| 7 | NgramIndex | ✅ |
| 8 | FullTextIndex | ✅ |
| 9 | ForeshadowingTracker | ✅ |
| 10 | ContextTracker | ✅ |
| 11 | ForeshadowingAnalyzer | ✅ |
| 12 | EpisodeStore | ✅ |
| 13 | VolumeManager | ✅ |
| 14 | MetadataIndex | ✅ (v5.0) |
| 15 | VectorIndexIVF | ✅ (v7.0.4) |
| 16 | BAL 后端 | ✅ (v7.0.4) |
| 17 | EventLinker | ✅ (v7.0.4) |
| 18 | TopicCluster | ✅ (v7.0.4) |
| 19 | Retriever 缓存 | ✅ (v7.0.4) |
| 20 | ContradictionManager | ✅ (v7.0.4) |
| 21 | TemporalIndex | ✅ (v7.0.8，通过 `temporal_graph._temporal_index.clear()`) |

**clear_all() 看起来完整**。

---

## 7. 问题汇总（按严重级排序）

### CRITICAL (3)

| # | 文件 | 行 | 问题 | 影响 |
|---|------|-----|------|------|
| C1 | recall/storage/multi_tenant.py | L27 | `ScopedMemory.MAX_MEMORIES = 5000` 硬上限导致长期运行丢失最旧记忆 | 1年+RP场景必触发数据丢失 |
| C2 | recall/engine.py | L1864 | `_rebuild_content_cache()` 启动时加载全部记忆到无界缓存 | 数据量大时 OOM 或启动耗时分钟级 |
| C3 | recall/engine.py | 全文件 | `RecallEngine` + `MemoryOperations` 无锁保护、多 worker 部署不安全 | 并发写入导致数据不一致或崩溃 |

### HIGH (5)

| # | 文件 | 行 | 问题 | 影响 |
|---|------|-----|------|------|
| H1 | recall/retrieval/eight_layer.py | L125 | `EightLayerRetriever._content_cache` 无 LRU 限制 | 与 C2 相同的 OOM 风险 |
| H2 | recall/graph/backends/json_backend.py | L68 | JSON 图后端 nodes/edges 无内存上限 | 10万+节点时 OOM |
| H3 | recall/graph/temporal_knowledge_graph.py | L168 | TemporalKnowledgeGraph 内存存储无上限 | 同 H2 |
| H4 | recall/index/inverted_index.py | L33 | `_load()` 主文件 JSON 解析无 try-except | 文件损坏导致引擎无法启动 |
| H5 | recall/index/vector_index.py | 全文件 | 无 atexit 注册，最多丢失 99 条向量 | 进程异常退出时丢失数据 |

### MEDIUM (8)

| # | 文件 | 行 | 问题 | 影响 |
|---|------|-----|------|------|
| M1 | recall/index/metadata_index.py | L160 | `_load()` JSON 解析无 try-except | 文件损坏导致引擎无法启动 |
| M2 | recall/index/vector_index.py | L173 | `faiss.write_index()` 非原子操作 | 断电时 .faiss 文件损坏 |
| M3 | recall/index/vector_index.py | L149 | `faiss.read_index()` 失败无恢复 | FAISS 文件损坏后向量索引永久不可用 |
| M4 | recall/index/ngram_index.py | 全文件 | 无 atexit，名词短语索引最多丢 99 条 | 进程退出后索引不完整（原文不丢） |
| M5 | recall/processor/consistency.py | L333-338 | `entity_facts`/`relationships`/`timelines` 无界增长 | 性能退化 |
| M6 | recall/index/inverted_index.py | L19 | `index` dict 无界增长 | 百万级记忆时内存占用显著 |
| M7 | recall/index/fulltext_index.py | L90 | BM25 索引无界增长 | 同 M6 |
| M8 | recall/memory_ops.py | L2214 | `clear(user_id)` 不清理 `TemporalIndex` | 时态索引残留幽灵条目 |

### LOW (5)

| # | 文件 | 行 | 问题 | 影响 |
|---|------|-----|------|------|
| L1 | recall/middleware/rate_limit.py | L69 | `RECALL_RATE_LIMIT_RPM` 默认值与 RecallConfig 不一致 (0 vs 60) | 配置混淆 |
| L2 | recall/config.py | L615 | `TripleRecallConfig.from_env()` 绕过 RecallConfig | 未来默认值不一致风险 |
| L3 | recall/storage/episode_store.py | 全文件 | 无 atexit（但写入模式安全） | 极端场景微量数据丢失 |
| L4 | recall/graph/contradiction_manager.py | 全文件 | 无 atexit（但每次操作后保存） | 极端场景微量数据丢失 |
| L5 | recall/index/fulltext_index.py | clear 相关 | `clear()` 后 `doc_count`/`avg_doc_length` 被为 0 但之前删除的单文档不更新全局统计 | 统计精度轻微偏差 |

---

## 8. 建议修复优先级

| 优先级 | 任务 | 预计工时 | 影响 |
|--------|------|---------|------|
| P0 | **InvertedIndex/MetadataIndex `_load()` 添加 try-except** | 0.5h | 防止文件损坏导致引擎不可用 |
| P0 | **VectorIndex 添加 atexit** | 0.5h | 防止进程退出丢失向量 |
| P0 | **NgramIndex 添加 atexit** | 0.5h | 防止进程退出丢失索引 |
| P1 | **EightLayerRetriever._content_cache 添加 LRU** | 1h | 防止 OOM |
| P1 | **_rebuild_content_cache() 添加数量上限** | 1h | 防止启动 OOM |
| P1 | **FAISS 写入改为原子操作** | 1h | 防止断电损坏 |
| P2 | RecallEngine 添加全局读写锁（可 RLock） | 2-3h | 防止并发 race |
| P2 | `clear(user_id)` 补充 TemporalIndex 清理 | 0.5h | 消除幽灵条目 |
| P3 | ScopedMemory → SQLite (WAL) | 2-3 天 | 彻底消除 5000 上限 |
| P3 | JSON 图后端添加分页/懒加载 | 1-2 天 | 支持大规模图谱 |
