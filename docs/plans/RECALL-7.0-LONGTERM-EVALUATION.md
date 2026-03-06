# Recall v7.0 — 长期运行可行性评估报告

> 生成时间: 2025-01  
> 版本: v7.0 (13 个死路径全部修复，59/59 测试通过)  
> 测试环境: Windows + Python 3.12.0 + FAISS + Local Embedding

---

## 一、执行摘要

| 维度 | 评级 | 说明 |
|------|------|------|
| **短期 (0-3 月, <1 万条)** | ✅ 可用 | 所有核心功能正常，性能良好 |
| **中期 (3-12 月, 1-5 万条)** | ⚠️ 需监控 | 内存增长、JSON 序列化延迟开始显现 |
| **长期 (1-3 年, 5 万+条)** | ❌ 需架构升级 | 4 个 CRITICAL 瓶颈必须解决 |

**核心结论**: 当前 v7.0 代码**功能完整、可以正确运行**，但其 **全内存 + JSON 文件** 的存储架构
决定了在数据量超过约 5 万条记忆后将面临内存溢出和 I/O 瓶颈。
这不是 bug，而是架构天花板。

---

## 二、10 项关键模块评估

### 2.1 存储后端 — 🔴 CRITICAL

| 指标 | 值 |
|------|-----|
| 格式 | 纯 JSON 文件 (`memories.json`) |
| 分区 | `{user_id}/{character_id}/{session_id}/` 路径分区 |
| **硬上限** | **ScopedMemory.MAX_MEMORIES = 5000** |
| 超限行为 | **LRU 驱逐最旧记忆 → 数据永久丢失** |
| 原子性 | ❌ 无 WAL/事务，断电可损坏 |

**影响**: 任何用户超过 5000 条将自动丢弃旧记忆。这直接违反"100% 不遗忘"目标。

**修复建议**: ScopedMemory → SQLite (WAL 模式) + 无上限分页查询

---

### 2.2 向量索引 — 🟡 MEDIUM

| 指标 | 值 |
|------|-----|
| 默认 | `faiss.IndexFlatIP` 暴力搜索 |
| IVF | `IndexIVFFlat` + HNSW quantizer (自动切换阈值 50000) |
| 存储 | **全在内存**，启动时 `faiss.read_index()` 全量加载 |
| mmap | ❌ 不支持 |
| 删除 | **全量重建** O(n) |

**内存估算**:

| 向量数 | 内存 (384维) |
|--------|-------------|
| 10 万 | ~150 MB |
| 50 万 | ~750 MB |
| 100 万 | ~1.5 GB |

**容量上限**: Flat 索引 ~50 万向量实用上限，IVF 可达 500 万但仍需全量 RAM。

---

### 2.3 知识图谱 — 🔴 CRITICAL (file) / 🟢 LOW (Kuzu)

| 后端 | 存储方式 | 容量 | 延迟 |
|------|---------|------|------|
| **file** (默认) | 3 个 JSON 文件全量读写 | ~5 万节点后严重退化 | _mark_dirty 每 50 次全量 dump |
| **kuzu** | 嵌入式列存图数据库 | 数百万节点 | 实时事务 |

**file 后端瓶颈**: 10 万节点时 `_save()` 一次序列化:
- 内存: 节点对象 ~1GB + JSON 字符串 ~1GB = **峰值 2GB+**
- 耗时: 5-30 秒 (阻塞当前请求)

**修复建议**: 默认后端切换为 Kuzu，file 仅作 fallback

---

### 2.4 倒排索引 — 🟡 MEDIUM

| 指标 | 值 |
|------|-----|
| 写入模式 | ✅ **WAL (JSONL 追加)** + 原子压缩 |
| 压缩阈值 | 每 10000 条 WAL 全量重写 |
| 存储 | `Dict[str, Set[str]]` **全在内存** |
| 退出安全 | ✅ `atexit.register(flush)` |

**容量**: ~50-100 万文档可用，之后内存压力大 (~1.5 GB)。
WAL 设计良好，是最健壮的写入路径之一。

---

### 2.5 时态索引 — 🔴 HIGH

| 操作 | 复杂度 | 说明 |
|------|--------|------|
| 查询 | O(log n + min(k₁,k₂)) | ✅ 双 bisect 优化 |
| 插入 | O(n) | ⚠️ `bisect.insort` 在 Python list 上需内存复制 |
| 删除 | O(n) | ⚠️ `list.remove()` 线性扫描 |
| 保存 | O(n) | 全量 JSON dump |

**10M 条目时**: 每次插入 ~5-50ms (列表复制 ~40MB)，每次删除 ~10-100ms。
5 个排序列表 × 10M × 16 字节 ≈ **800MB RAM**。

**修复建议**: 替换为 `sortedcontainers.SortedList` (C 扩展, O(log n) 插入/删除)

---

### 2.6 分卷管理器 — 🟢 LOW

| 指标 | 值 |
|------|-----|
| 写入模式 | ✅ JSONL 追加，不修改 |
| 分卷 | 每卷 10 万轮，每文件 1 万轮 |
| 查找 | ✅ O(1) `memory_id_index.json` |
| 加载 | ✅ 懒加载，只加载索引 |

**评价**: 最健壮的存储组件。追加写入 + 分卷 + 懒加载 = 理论无上限 (磁盘足够时)。

---

### 2.7 布隆过滤器 — 🟡 MEDIUM

| 指标 | 值 |
|------|-----|
| 实现 | `pybloom_live.BloomFilter(capacity=1M, error_rate=0.01)` |
| 降级 | 未安装 pybloom_live 时退化为 Python set |
| 持久化 | ❌ 不持久化，重启后需重建 |
| 内存 | 布隆 ~1.2MB / set 降级 ~500MB@100 万条 |

**隐藏问题**: `_raw_content: Dict[str, str]` 将 **所有记忆原文** 存入内存 (~500MB@100 万条)

---

### 2.8 内存泄漏 — 🔴 CRITICAL

**无界增长的内存缓存**:

| 缓存 | 位置 | 上限 | 100K 记忆估算 |
|------|------|------|--------------|
| `_content_cache` | ElevenLayerRetriever | ❌ 无 | ~50-200 MB |
| `_metadata_cache` | ElevenLayerRetriever | ❌ 无 | ~100 MB |
| `_raw_content` | NgramIndex | ❌ 无 | ~50-200 MB |
| `nodes/edges` | KnowledgeGraph (file) | ❌ 无 | ~1-3 GB |
| `index` | InvertedIndex | ❌ 无 | ~800 MB |

**有上限的缓存** (设计良好):

| 缓存 | 上限 | 策略 |
|------|------|------|
| `_cache` (Embedding) | 10000 条 | LRU 清半 |
| `_path_cache` (QueryPlanner) | 1000 条 + TTL 300s | 按大小+时间 |
| `_memories` (ScopedMemory) | 5000 条 | LRU 驱逐 (丢数据) |

**最大风险**: `_rebuild_content_cache()` 在引擎启动时加载 **所有用户所有记忆** 到内存。
10 万条 × 平均 500 字节 = **~50MB**，100 万条 = **~500MB** 仅原文。

---

### 2.9 磁盘 I/O — 🟡 MEDIUM-HIGH

| 组件 | 触发频率 | 写入方式 |
|------|---------|---------|
| ScopedMemory | **每次 add()** | 全量 JSON dump ❌ |
| VolumeManager | 每 100 轮 | JSONL 追加 ✅ |
| VectorIndex | 每 100 次 add() | faiss 全量写 |
| InvertedIndex | 每次 WAL + 每 1 万次压缩 | WAL 追加 ✅ |
| KnowledgeGraph | 每 50 次 _mark_dirty | 全量 JSON dump ❌ |
| EntityIndex | **每次 add()** | 全量 JSON dump ❌ |

**单次 add() 的 I/O 链**: ScopedMemory 全量写 → EntityIndex 全量写 → InvertedIndex WAL 追加 → NgramIndex 追加 → KnowledgeGraph _mark_dirty

在 5 万+记忆后，ScopedMemory 和 EntityIndex 的全量 JSON dump 将成为明显瓶颈 (>100ms/次)。

---

### 2.10 Embedding 模型 — 🟢 LOW

| 模式 | 模型 | 维度 | 内存 | 费用 |
|------|------|------|------|------|
| **local** (推荐) | paraphrase-multilingual-MiniLM-L12-v2 | 384 | ~800MB | **$0** |
| cloud | text-embedding-3-small | varies | ~10MB | ~$0.02/1K 条 |

**Local 模式评价**: 最稳健方案。无网络依赖、无费用、无限速。384 维在当前向量索引下内存效率最优。

---

## 三、容量规划速查表

| 记忆数 | 总内存估算 | JSON I/O 延迟 | 可用性 |
|--------|-----------|--------------|--------|
| 1,000 | ~200 MB | <10ms | ✅ 流畅 |
| 10,000 | ~400 MB | ~50ms | ✅ 良好 |
| 50,000 | ~1.5 GB | ~500ms | ⚠️ 可感知延迟 |
| 100,000 | ~3 GB | ~2s | ⚠️ 操作卡顿 |
| 500,000 | ~10 GB | ~10s | ❌ 不可用 |
| 1,000,000 | ~20 GB+ | ~30s+ | ❌ OOM |

> 注: 以上为单用户在 file 后端下的估算。多用户数据分隔存储，互不影响。

---

## 四、准确率评估

### 搜索准确率

| 检索层 | 方法 | 准确率贡献 |
|--------|------|-----------|
| L1 | Bloom/Ngram 过滤 | 高召回率，低精度 (初筛) |
| L2 | 时态索引 | 时间相关查询精确 |
| L3 | 倒排索引 (BM25) | 关键词匹配准确 |
| L4 | 实体索引 | 实体级别精确 |
| L5 | 图谱遍历 | 关系推理能力 |
| L7-L8 | 向量粗排+精排 | 语义理解核心 |
| L9 | Reranker | 重排序精度提升 |
| L10-L11 | Cross-Encoder/LLM | 最高精度 (可选) |

**实际搜索准确率估算**:
- 简单关键词查询: **>95%** (BM25 + 向量足够)
- 语义模糊查询: **80-90%** (依赖 embedding 质量)
- 时间关联查询: **>90%** (dual-bisect 准确)
- 关系推理查询: **70-85%** (受 LLM 质量影响)

**注意**: "近 100% 准确率" 需要:
1. 高质量 embedding 模型 (local 384 维有限制)
2. LLM 辅助层启用 (L11，需 API key)
3. 数据量在可用范围内 (不触发 5000 上限)

---

## 五、v8.0 升级路线图 (解决长期运行瓶颈)

### 优先级 P0 — 阻塞长期运行

| # | 改动 | 工作量 | 效果 |
|---|------|--------|------|
| 1 | ScopedMemory → SQLite (WAL) | 2-3 天 | 消除 5000 上限 + 原子写入 |
| 2 | `_content_cache` 添加 LRU 上限或改为按需查询 | 1 天 | 消除 OOM 风险 |
| 3 | KnowledgeGraph 默认切换 Kuzu | 1 天 (已有代码) | 消除图谱 OOM |
| 4 | EntityIndex 改为增量写入 | 1 天 | 消除每次 add() 全量 dump |

### 优先级 P1 — 中期性能

| # | 改动 | 工作量 | 效果 |
|---|------|--------|------|
| 5 | 时态索引 → `sortedcontainers.SortedList` | 0.5 天 | 插入/删除 O(n)→O(log n) |
| 6 | NgramIndex `_raw_content` 添加 LRU | 0.5 天 | 减少内存占用 |
| 7 | 向量索引删除改为标记删除 + 定期重建 | 1 天 | 删除从 O(n) 降为 O(1) |

### 优先级 P2 — 极限规模

| # | 改动 | 工作量 | 效果 |
|---|------|--------|------|
| 8 | FAISS mmap 支持 | 2 天 | 向量不需全部驻留 RAM |
| 9 | 倒排索引分片 | 1 天 | 百万级后内存可控 |
| 10 | 多进程架构 (写入/查询分离) | 3-5 天 | 消除 GIL 写入阻塞查询 |

---

## 六、结论

### ✅ v7.0 做到了什么
- 13 个死路径 **全部修复并通过测试** (59/59 PASS)
- 11 层检索漏斗完整工作
- add / search / delete / consolidate 全链路正确
- RecallConfig 统一配置、PromptManager 接入、QueryPlanner 接入、RerankerFactory 可插拔
- temporal_index 双 bisect、knowledge_graph 延迟保存、IVF 向量迁移 全部实现

### ⚠️ v7.0 的架构天花板
- 全内存数据结构 + JSON 序列化 = **5 万条记忆是实用上限**
- ScopedMemory 5000 条硬上限 = **长期必丢数据**
- 要达到 1-3 年连续运行，需要 P0 的 4 项改动 (约 5-6 天工作量)

### 🎯 建议
1. **短期** (现在): 使用 v7.0，设置合理的用户记忆预期 (<5000 条)
2. **中期** (1-2 周内): 完成 P0 四项改动，消除硬性瓶颈
3. **长期** (1-2 月内): 完成 P1 + P2，实现百万级记忆支持
