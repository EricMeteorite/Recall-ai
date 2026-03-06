# Recall-AI 全模块深度分析报告 (Storage / Index / Retrieval / Utils / Embedding)

> 生成时间: 2024  
> 覆盖范围: `recall/storage/`, `recall/index/`, `recall/retrieval/`, `recall/utils/`, `recall/embedding/`  
> 共计: **37 个 Python 文件, ~8,500+ 行代码**

---

## 目录

1. [总览表](#1-总览表)
2. [recall/storage/ (7 文件, ~1,254 行)](#2-recallstorage)
3. [recall/index/ (9 文件, ~3,053 行)](#3-recallindex)
4. [recall/retrieval/ (8 文件, ~2,704 行)](#4-recallretrieval)
5. [recall/utils/ (8 文件, ~2,429 行)](#5-recallutils)
6. [recall/embedding/ (5 文件, ~1,029 行)](#6-recallembedding)
7. [横切关注点分析](#7-横切关注点分析)
   - 7.1 [JSON I/O 模式（全量重写 vs 增量追加）](#71-json-io-模式全量重写-vs-增量追加)
   - 7.2 [O(n) 操作清单](#72-on-操作清单)
   - 7.3 [character_id / mode / foreshadowing / RP 引用](#73-character_id--mode--foreshadowing--rp-引用)
   - 7.4 [死代码 / 未使用方法](#74-死代码--未使用方法)
   - 7.5 [Delete Cascade 完整分析（13 存储位置）](#75-delete-cascade-完整分析13-存储位置)
8. [专题分析](#8-专题分析)
   - 8.1 [VolumeManager O(n) 扫描问题](#81-volumemanager-on-扫描问题)
   - 8.2 [InvertedIndex 全量 JSON Dump 问题](#82-invertedindex-全量-json-dump-问题)
   - 8.3 [MetadataIndex 实现](#83-metadataindex-实现)
   - 8.4 [MultiTenantStorage / EnvironmentIsolation](#84-multitenantstorage--environmentisolation)
   - 8.5 [ParallelRetriever（死代码）](#85-parallelretriever死代码)
   - 8.6 [ElevenLayerRetriever 实现](#86-elevenlayerretriever-实现)
   - 8.7 [VectorIndex vs VectorIndexIVF](#87-vectorindex-vs-vectorindexivf)

---

## 1. 总览表

| 目录 | 文件数 | 总行数 | 主要职责 |
|------|--------|--------|----------|
| `storage/` | 7 | ~1,254 | 3层记忆架构 (L0/L1/L2/L3) + 多租户 + 事件存储 |
| `index/` | 9 | ~3,053 | 8种索引类型（实体/倒排/全文/元数据/Ngram/时间/向量/向量IVF） |
| `retrieval/` | 8 | ~2,704 | 11层检索漏斗 + 并行3路召回 + RRF融合 |
| `utils/` | 8 | ~2,429 | LLM客户端/性能监控/任务管理/预热/预算/环境隔离/自动维护 |
| `embedding/` | 5 | ~1,029 | 多后端Embedding（本地/OpenAI/硅基流动/Google/Voyage/Cohere） |

---

## 2. recall/storage/

### 2.1 `__init__.py` (21 行)

- **用途**: 模块导出
- **导出**: `VolumeManager`, `VolumeData`, `CoreSettings`, `ConsolidatedMemory`, `ConsolidatedEntity`, `WorkingMemory`, `WorkingEntity`, `MultiTenantStorage`, `MemoryScope`, `EpisodeStore`

---

### 2.2 `episode_store.py` (161 行)

- **用途**: 事件/回合存储，JSONL 格式
- **存储文件**: `episodes.jsonl`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `EpisodeStore` | `__init__(data_dir)` | ~15 | 初始化 |
| | `_load()` | ~25 | 读取全部 JSONL |
| | `save(episode)` | ~45 | 追加 → `_append_to_file()` |
| | `_append_to_file(episode)` | ~55 | **增量 JSONL 追加** |
| | `get(episode_id)` | ~65 | 按 id 查找 |
| | `get_by_memory_id(memory_id)` | ~72 | ⚠️ **O(n) 扫描** |
| | `get_by_entity_id(entity_id)` | ~79 | ⚠️ **O(n) 扫描** |
| | `get_by_relation_id(relation_id)` | ~86 | ⚠️ **O(n) 扫描** |
| | `get_by_user(user_id)` | ~93 | ⚠️ **O(n) 扫描** |
| | `get_by_character(character_id)` | ~100 | ⚠️ **O(n) 扫描**, 🎭 **character_id 引用** |
| | `update_links()` | ~107 | ⚠️ 触发 `_rewrite_all()` **全量重写** |
| | `_rewrite_all()` | ~120 | 全量重写 JSONL |
| | `clear()` | ~135 | 清空文件 |
| | `clear_user(user_id)` | ~145 | 按用户清空 → **全量重写** |

**关键问题**:
- ❌ **无 delete-by-id 方法** — 无法参与 delete cascade
- ⚠️ 所有 `get_by_*` 方法均为 O(n) 线性扫描
- `update_links()` 触发全量 JSONL 重写

---

### 2.3 `layer0_core.py` (113 行)

- **用途**: 核心设定存储 (L0层)
- **存储文件**: `L0_core/core.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `CoreSettings` (dataclass) | 字段 | ~12-25 | `character_card` 🎭, `world_setting` 🎭, `writing_style` 🎭, `code_standards`, `project_structure`, `domain_context`, `custom_instructions` |
| | `load(data_dir)` | ~35 | JSON 全量读取 |
| | `save(data_dir)` | ~50 | **JSON 全量写入** |
| | `get_injection_text(scenario)` | ~65 | 按场景生成注入文本: `'roleplay'` / `'coding'` / `'general'` |

**RP/character_id 引用**: `character_card` (L15), `world_setting` (L16), `writing_style` (L17), `get_injection_text('roleplay')` 分支

---

### 2.4 `layer1_consolidated.py` (175 行)

- **用途**: 整合记忆存储 (L1层)
- **存储文件**: `L1_consolidated/entities_NNNN.json` (分片, 每片1000条)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `ConsolidatedEntity` (dataclass) | 字段 | ~10-30 | `entity_id`, `name`, `entity_type`, `summary`, `attributes`, `memory_ids`, `last_updated` |
| `ConsolidatedMemory` | `__init__(data_dir)` | ~40 | |
| | `_load()` | ~50 | 加载所有分片 |
| | `_save()` | ~70 | ⚠️ **全量重写所有分片** |
| | `add_or_update(entity)` | ~90 | 每次调用触发 `_save()` → **全量重写** |
| | `get(entity_id)` | ~105 | 按 id O(1) dict 查找 |
| | `get_entity(name)` | ~110 | ⚠️ **O(n) 名称扫描** |
| | `search_by_name(name)` | ~120 | ⚠️ **O(n) 名称模糊匹配** |
| | `get_all_entity_names()` | ~130 | O(n) 遍历所有名称 |
| | `clear()` | ~140 | |
| | `remove_by_memory_ids(memory_ids)` | ~150 | ✅ **Delete cascade 支持** |

**关键问题**:
- ⚠️ `add_or_update()` 每次都全量重写所有分片文件，高频写入时性能极差
- `get_entity(name)` 和 `search_by_name(name)` 为 O(n) 线性扫描

---

### 2.5 `layer2_working.py` (94 行)

- **用途**: 工作记忆 (L2层, 纯内存, 不持久化)
- **存储文件**: 无

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `WorkingEntity` (dataclass) | 字段 | ~10-20 | `name`, `salience`, `last_access`, `activation_count` |
| `WorkingMemory` | `__init__(capacity)` | ~30 | LRU 容量管理 |
| | `update_with_delta_rule(entity_name, ...)` | ~45 | 更新实体显著性 |
| | `_evict_one()` | ~60 | ⚠️ **O(n) 扫描找最小 score** |
| | `get_active_entities()` | ~75 | 获取所有活跃实体 |

**说明**: 纯会话级内存，不参与持久化和 delete cascade。`_evict_one()` 中使用 `min()` 对全量实体列表扫描。

---

### 2.6 `multi_tenant.py` (263 行)

- **用途**: 多租户存储 + 按 user/character/session 路径隔离
- **存储文件**: `{user_id}/{character_id}/{session_id}/memories.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `MemoryScope` (dataclass) | 字段 | ~16 | `user_id`, `session_id`, 🎭 **`character_id`** |
| | `to_path()` | ~25 | 生成路径: `user_id/character_id/session_id` |
| `ScopedMemory` | `__init__(data_dir, scope)` | ~45 | |
| | `_load()` | ~55 | JSON 全量读取 |
| | `_save()` | ~65 | ⚠️ **JSON 全量重写** (每次 add/delete/update 都触发) |
| | `add(memory)` | ~80 | 添加 → `_save()` |
| | `search(query, ...)` | ~95 | ⚠️ **O(n) 关键词扫描** |
| | `get_all()` | ~115 | |
| | `get_paginated(page, size)` | ~125 | |
| | `count()` | ~135 | |
| | `get_recent(limit)` | ~140 | |
| | `delete(memory_id)` | ~150 | ⚠️ **O(n) 线性搜索** → `_save()`, ❌ **不级联到索引** |
| | `update(memory_id, ...)` | ~170 | ⚠️ **O(n)** → `_save()` |
| | `clear()` | ~190 | |
| `MultiTenantStorage` | `get_scope(scope)` | ~210 | 获取 ScopedMemory |
| | `list_users()` | ~220 | |
| | `list_characters(user_id)` | ~230 | |
| | `delete_session(scope)` | ~240 | `shutil.rmtree()` 删除整个会话目录 |
| | `export_memories(scope)` | ~250 | |
| | `import_memories(scope, data)` | ~260 | |

**关键问题**:
- 🎭 `MemoryScope` 核心引用 `character_id` (L16)
- ⚠️ `_save()` 在每次 add/delete/update 时全量重写 `memories.json`
- ❌ `ScopedMemory.delete()` 只删 memories.json 中的条目，**不级联到任何索引**

---

### 2.7 `volume_manager.py` (427 行)

- **用途**: 归档存储 (L3层), JSONL 卷文件
- **存储文件**: `L3_archive/volume_NNNN/*.jsonl` + `memory_id_index.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `VolumeData` | `__init__(volume_dir)` | ~20 | |
| | `get_turn(offset)` | ~35 | O(1) 文件偏移读取 |
| | `append(turn)` | ~50 | 内存追加 |
| | `_persist()` | ~65 | ✅ **增量 JSONL 追加** (仅写未持久化的) |
| | `load_all_to_memory()` | ~80 | 加载全卷到内存 |
| `VolumeManager` | `__init__(data_dir, ...)` | ~100 | |
| | `get_turn(turn_number)` | ~120 | O(1) 通过卷号/文件/偏移计算 |
| | `_load_volume(vol_num)` | ~140 | |
| | `preload_recent(n)` | ~155 | |
| | `append_turn(turn)` | ~165 | JSONL 追加 + 定期 persist |
| | `get_turn_by_memory_id(memory_id)` | ~175-218 | ⚠️ **O(n) 扫描问题** (详见专题 8.1) |
| | `search_content(query)` | ~220-268 | ⚠️ **O(n) 全卷扫描** |
| | `_save_memory_id_index()` | ~280 | ⚠️ **JSON 全量重写** `memory_id_index.json` |
| | `flush()` | ~300 | |
| | `clear()` | ~320 | |

**关键问题**:
- ⚠️ `get_turn_by_memory_id()`: 先查 memory_id_index (O(1)), 失败后 O(n) 扫描全部已加载卷, 再失败则 O(n) 扫描磁盘全部 .jsonl 文件
- ⚠️ `search_content()`: O(n) 扫描全部卷的全部 turn
- ❌ **无 per-memory delete 方法** — 无法参与 delete cascade
- `memory_id_index.json` 每次保存都是全量重写

---

## 3. recall/index/

### 3.1 `__init__.py` (33 行)

- **导出**: `EntityIndex`, `IndexedEntity`, `InvertedIndex`, `VectorIndex`, `VectorIndexIVF`, `FullTextIndex`, `NgramIndex`, `OptimizedNgramIndex`, `TemporalIndex`, `TemporalEntry`, `MetadataIndex`

---

### 3.2 `entity_index.py` (271 行)

- **用途**: 实体索引 — 跟踪实体出现位置和关系
- **存储文件**: `entity_index.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `IndexedEntity` (dataclass) | 字段 | ~10-25 | `entity_id`, `name`, `entity_type`, `turn_references[]`, `occurrence_count`, `last_seen`, `related_entities{}`, `summary`, `attributes{}` |
| `EntityIndex` | `__init__(data_dir)` | ~35 | |
| | `_load()` | ~45 | JSON 全量读取 |
| | `_save()` | ~60 | ⚠️ **JSON 全量重写** |
| | `add(entity)` | ~80 | → `_save()` |
| | `get_by_name(name)` | ~95 | dict O(1) |
| | `get_by_id(entity_id)` | ~105 | dict O(1) |
| | `search(query)` | ~115 | ⚠️ **O(n) 名称扫描** |
| | `all_entities()` | ~130 | |
| | `get_top_entities(limit)` | ~140 | O(n log n) 排序 |
| | `add_entity_occurrence(name, turn_ref)` | ~155 | |
| | `get_related_turns(entity_name)` | ~170 | |
| | `get_entity(entity_name)` | ~180 | |
| | `remove_by_turn_references(turn_refs)` | ~190 | ✅ **Delete cascade**: 移除 turn 引用, 删除孤儿实体 |
| | `clear()` | ~210 | |
| | `update_entity_fields(name, fields)` | ~225 | Recall 4.1: 更新实体字段 |
| | `get_entities_needing_summary()` | ~250 | |

---

### 3.3 `fulltext_index.py` (436 行)

- **用途**: BM25 全文索引
- **存储文件**: `fulltext_index.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `FullTextIndex` | `__init__(data_dir)` | ~20 | |
| | `_load()` | ~35 | JSON 全量读取 |
| | `_save()` | ~55 | ⚠️ **JSON 全量重写** |
| | `tokenize(text)` | ~75 | 中英文混合分词 |
| | `add(doc_id, text, metadata)` | ~100 | |
| | `remove(doc_id)` | ~130 | 单条删除 |
| | `remove_by_doc_ids(doc_ids)` | ~150 | ✅ **Delete cascade 支持** |
| | `search(query, top_k)` | ~170 | BM25 评分 |
| | `flush()` | ~220 | → `_save()` |
| | `clear()` | ~235 | |
| | `get_stats()` | ~250 | |

**数据结构**: `inverted_index` (term → {doc_id → freq}), `doc_info`, `doc_freq`

---

### 3.4 `inverted_index.py` (155 行)

- **用途**: 通用倒排索引 (带 WAL 模式)
- **存储文件**: `inverted_index.json` + `inverted_wal.jsonl`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `InvertedIndex` | `__init__(data_dir)` | ~15 | |
| | `_load()` | ~25 | 加载主文件 + replay WAL |
| | `_save()` | ~45 | 现为 **no-op** (已被 WAL 取代) |
| | `_save_full()` | ~50 | JSON 全量 dump (仅 compact 时用) |
| | `add(key, value)` | ~65 | ✅ **WAL 追加** (增量) |
| | `add_batch(entries)` | ~78 | ✅ **WAL 批量追加** |
| | `search(key)` | ~90 | 精确匹配 |
| | `search_all(keys)` | ~100 | AND 查询 |
| | `search_any(keys)` | ~110 | OR 查询 |
| | `_compact()` | ~120 | ⚠️ **全量重写** (合并 WAL 到主文件) |
| | `flush()` | ~135 | |
| | `clear()` | ~140 | |
| | `remove_by_memory_ids(memory_ids)` | ~145 | ✅ **Delete cascade 支持** |

**WAL 模式**: 日常写入仅追加 `inverted_wal.jsonl`, 达到 10,000 条阈值时触发 `_compact()` 全量重写。详见专题 8.2。

---

### 3.5 `metadata_index.py` (165 行)

- **用途**: 元数据索引 (5 个倒排子索引)
- **存储文件**: `metadata_index.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `MetadataIndex` | `__init__(data_dir)` | ~15 | |
| | `_load()` | ~25 | JSON 全量读取 |
| | `_save()` | ~40 | ⚠️ **JSON 全量重写** (每 100 次脏操作后) |
| | `add(doc_id, metadata)` | ~60 | 添加到 5 个子索引 |
| | `query(conditions)` | ~85 | 多条件 AND 查询 |
| | `remove(doc_id)` | ~110 | 单条删除 |
| | `remove_batch(doc_ids)` | ~125 | ✅ **Delete cascade 支持** |
| | `clear()` | ~140 | |

**5 个子索引**: `by_source`, `by_tag`, `by_category`, `by_content_type`, `by_event_date`  
**批量优化**: dirty_count 计数器, 每 100 次操作才触发一次 `_save()`

---

### 3.6 `ngram_index.py` (418 行)

- **用途**: Ngram 搜索索引 (双层: 名词短语索引 + 原始文本回退)
- **存储文件**: `ngram_index.json` + `ngram_raw_content.jsonl`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `OptimizedNgramIndex` | `__init__(data_dir)` | ~20 | |
| | `_load()` | ~35 | JSON + JSONL 读取 |
| | `save()` | ~55 | ⚠️ **JSON 全量重写** ngram_index.json |
| | `append_raw_content(doc_id, text)` | ~75 | ✅ **增量 JSONL 追加** |
| | `add(doc_id, text)` | ~90 | 名词短语提取 + 添加 |
| | `search(query, top_k)` | ~120 | 2 层: 名词短语索引 → O(n) 原始文本回退 |
| | `_raw_text_fallback_search(query, k)` | ~160 | ⚠️ **O(n) 全量扫描** 原始文本 |
| | `raw_search_parallel(query, k, workers)` | ~190 | 并行版 O(n) 扫描 |
| | `clear()` | ~220 | |
| | `remove_by_memory_ids(memory_ids)` | ~240 | ✅ **Delete cascade 支持** |

---

### 3.7 `temporal_index.py` (553 行)

- **用途**: 时间线索引 — 3 时间模型 (fact_range, known_at, system_range)
- **存储文件**: `temporal_index.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `TemporalEntry` (dataclass) | 字段 | ~15-35 | `entry_id`, `subject`, `content`, `fact_start/end`, `known_at`, `system_start/end`, `confidence`, `source_turn` |
| `TemporalIndex` | `__init__(data_dir)` | ~50 | |
| | `_load()` | ~60 | JSON 全量读取 |
| | `_save()` | ~80 | ⚠️ **JSON 全量重写** |
| | `add(entry)` | ~100 | bisect 插入 O(log n) |
| | `remove(entry_id)` | ~120 | ⚠️ `list.remove()` 内部 O(n) unindex |
| | `get(entry_id)` | ~140 | dict O(1) |
| | `flush()` | ~150 | → `_save()` |
| | `query_at_time(timestamp)` | ~160 | bisect O(log n) |
| | `query_range(start, end)` | ~180 | bisect O(log n) |
| | `query_by_subject(subject)` | ~200 | 子索引 O(1) |
| | `query_timeline(subject)` | ~220 | |
| | `query_before(timestamp, limit)` | ~240 | |
| | `query_after(timestamp, limit)` | ~260 | |
| | `clear()` | ~280 | |

**关键问题**:
- ✅ 有 `remove(entry_id)` 方法
- ❌ **无 `remove_by_memory_ids()` 批量方法** — delete cascade 需要调用方逐个调 `remove()`
- `_unindex_entry()` 内部使用 `list.remove()` → O(n) 线性扫描

---

### 3.8 `vector_index.py` (456 行)

- **用途**: 向量索引 (FAISS IndexFlatIP — 暴力内积搜索)
- **存储文件**: `vector_index.faiss` + `vector_mapping.json` + `vector_config.json`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `VectorIndex` | `__init__(data_dir, embedding_backend)` | ~25 | 3 模式: local/cloud/lite(none) |
| | `_setup()` | ~45 | |
| | `_load()` | ~60 | 加载 FAISS + mapping |
| | `_save()` | ~80 | 保存 FAISS + mapping |
| | `clear()` | ~100 | |
| | `remove_by_doc_ids(doc_ids)` | ~115 | ✅ **Delete cascade**: ⚠️ **重建整个 FAISS 索引** |
| | `encode(text)` | ~140 | |
| | `add(doc_id, embedding)` | ~155 | |
| | `add_text(doc_id, text)` | ~170 | |
| | `search(query, top_k)` | ~190 | |
| | `search_by_embedding(embedding, top_k)` | ~210 | |
| | `get_vector_by_doc_id(doc_id)` | ~230 | ⚠️ **O(n)** `turn_mapping.index()` |
| | `get_vectors_by_doc_ids(doc_ids)` | ~250 | |
| | `close()` | ~270 | |
| | `rebuild_from_memories(memories)` | ~285 | 全量重建 |
| | `get_stats()` | ~310 | |

**关键问题**:
- `remove_by_doc_ids()` 必须重建整个 FAISS Index — IndexFlatIP 不支持单条删除
- `get_vector_by_doc_id()` 使用 `list.index()` → O(n)

---

### 3.9 `vector_index_ivf.py` (566 行)

- **用途**: IVF-HNSW 向量索引 (Phase 3.6)
- **存储文件**: `vector_index_ivf.faiss` + `vector_mapping_ivf.npy` + `vector_metadata_ivf.json` + `vector_pending_ivf.npy`

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `VectorIndexIVF` | `__init__(data_dir, embedding_backend, ...)` | ~25 | |
| | `_load_or_create()` | ~50 | |
| | `_load()` | ~70 | |
| | `_create()` | ~90 | HNSW 或 Flat 量化器 |
| | `add(doc_id, embedding, metadata)` | ~120 | 训练前: 暂存 pending; 训练后: 直接 add |
| | `_train_and_add()` | ~150 | 达到阈值时训练 IVF |
| | `train()` | ~180 | |
| | `search(query_embedding, top_k, user_id)` | ~210 | ✅ **多租户 user_id 过滤** |
| | `_save()` | ~250 | |
| | `flush()` | ~270 | |
| | `remove(doc_ids)` | ~290 | ✅ **软删除** (_deleted 标记) |
| | `rebuild()` | ~320 | 硬删除 → 全量重建 |

**与 VectorIndex 对比**: 详见专题 8.7。

---

## 4. recall/retrieval/

### 4.1 `__init__.py` (46 行)

- **导出**: `EightLayerRetriever`, `ElevenLayerRetriever`, `EightLayerRetrieverCompat`, `RetrievalConfig`, `ParallelRetriever`, `ContextBuilder`, 各种 Config 类

---

### 4.2 `config.py` (283 行)

- **用途**: 检索配置 + 数据类

| 类/函数 | 说明 |
|---------|------|
| `RetrievalConfig` (dataclass) | 全部 11 层开关 + top-k + Phase 3.6 并行召回配置 |
| `RetrievalConfig.default()` | 默认配置 |
| `RetrievalConfig.fast()` | 快速配置 (关闭 LLM 层) |
| `RetrievalConfig.accurate()` | 精准配置 (全开) |
| `RetrievalConfig.from_env()` | 从环境变量读取 |
| `LayerWeights` | 各层权重 |
| `TemporalContext` | 时间上下文 |
| `LayerStats` | 层统计 |
| `RetrievalResultItem` | 检索结果项 |

---

### 4.3 `context_builder.py` (219 行)

- **用途**: LLM 上下文/Prompt 构建
- 🎭 **RP 引用**

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `ContextBuilder` | `__init__(config)` | ~15 | |
| | `build(memories, conversation, ...)` | ~30 | 主构建方法 |
| | `optimize_for_roleplay()` | ~80 | 🎭 RP 优化入口 |
| | `_build_character_prompt()` | ~100 | 🎭 角色 Prompt 构建 |
| | `_prioritize_character_memories()` | ~130 | 🎭 角色记忆优先级 |

预算分配: 在 memory 和 conversation section 之间按 token 预算分配。

---

### 4.4 `eight_layer.py` (710 行)

- **用途**: 8 层检索器 (Phase 3.6 升级: 并行 4 路召回)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `EightLayerRetriever` | `__init__(indexes, config)` | ~25 | |
| | `retrieve(query, ...)` | ~50 | 主入口 → 分派并行/串行 |
| | `_parallel_recall(query, ...)` | ~90 | ThreadPoolExecutor 4 路并行 |
| | `_vector_recall(query, k)` | ~130 | L1: 向量召回 |
| | `_keyword_recall(query, k)` | ~155 | L2: 关键词召回 |
| | `_entity_recall(query, k)` | ~180 | L3: 实体召回 |
| | `_ngram_recall(query, k)` | ~210 | L4: Ngram 召回 |
| | `_raw_text_fallback(query, k)` | ~240 | Ngram 原始文本回退 |
| | `_legacy_retrieve(query, ...)` | ~270 | 原始串行 8 层 |
| | `_vector_fine_ranking(candidates, query)` | ~400 | L6: 精排 |
| | `_rerank(candidates, query)` | ~480 | L7: 重排 |
| | `_llm_filter(candidates, query)` | ~550 | L8: LLM 过滤 |

---

### 4.5 `eleven_layer.py` (1,341 行)

- **用途**: 完整 11 层检索漏斗
- 详见专题 8.6

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `ElevenLayerRetriever` | `__init__(indexes, config, graph_store)` | ~30 | |
| | `retrieve(query, ...)` | ~70 | 主入口 |
| | `_parallel_recall(query, ...)` | ~120 | 并行 3 路召回 |
| | `_legacy_retrieve(query, ...)` | ~180 | 串行 11 层 |
| | `retrieve_async(query, ...)` | ~250 | 异步版 |
| | `_l1_bloom_filter(candidates)` | ~310 | L1: 布隆过滤 |
| | `_l2_temporal_filter(candidates, ctx)` | ~360 | L2: 时间过滤 |
| | `_l3_inverted_index(query)` | ~420 | L3: 倒排索引 |
| | `_l4_entity_index(query)` | ~480 | L4: 实体索引 |
| | `_l5_graph_traversal(seeds)` | ~540 | L5: 图遍历 |
| | `_l6_ngram_index(query)` | ~600 | L6: Ngram 索引 |
| | `_l7_vector_coarse(query)` | ~660 | L7: 向量粗排 |
| | `_l8_vector_fine(candidates, query)` | ~720 | L8: 向量精排 |
| | `_l9_rerank(candidates, query)` | ~800 | L9: 重排 (pluggable RerankerFactory) |
| | `_l10_cross_encoder(candidates, query)` | ~870 | L10: 交叉编码器 |
| | `_l11_llm_filter(candidates, query)` | ~950 | L11: LLM 过滤 (async) |
| | `_fallback_ngram_search(query)` | ~1050 | Ngram 回退 |
| | `_build_results(candidates)` | ~1100 | 结果构建 |
| `EightLayerRetrieverCompat` | 适配器 | ~1200 | 8 层 → 11 层接口兼容适配 |

---

### 4.6 `parallel_retrieval.py` (218 行)

- **用途**: 通用并行检索器
- ⚠️ **可能为死代码** — 详见专题 8.5

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `ParallelRetriever` | `__init__(max_workers)` | ~15 | |
| | `register(name, retriever)` | ~25 | 注册检索源 |
| | `retrieve_parallel(query, ...)` | ~40 | ThreadPoolExecutor 并行检索 |
| | `merge_results(results_dict)` | ~80 | 合并结果 |

---

### 4.7 `reranker.py` (83 行)

- **用途**: 多策略重排器

| 类 | 说明 |
|----|------|
| `RerankerBase` (ABC) | 抽象基类 |
| `BuiltinReranker` | 内置关键词匹配 |
| `CohereReranker` | Cohere API 重排 |
| `CrossEncoderReranker` | 本地 Cross-Encoder 模型 |
| `RerankerFactory` | 工厂方法, 被 `eleven_layer.py` 的 L9 引用 |

---

### 4.8 `rrf_fusion.py` (105 行)

- **用途**: RRF (Reciprocal Rank Fusion) 和加权分数融合

| 函数 | 说明 |
|------|------|
| `reciprocal_rank_fusion(ranked_lists, k=60)` | RRF 融合, 被 eight_layer 和 eleven_layer 使用 |
| `weighted_score_fusion(scored_lists, weights)` | 加权分数融合 |

---

## 5. recall/utils/

### 5.1 `__init__.py` (45 行)

- **导出**: `LLMClient`, `WarmupManager`, `PerformanceMonitor`, `EnvironmentManager`, `AutoMaintainer`, `BudgetManager`, `TaskManager`

---

### 5.2 `auto_maintain.py` (242 行)

- **用途**: 后台自动维护调度器

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `AutoMaintainer` | `__init__()` | ~20 | daemon 线程调度 |
| | `register_task(name, callback, interval)` | ~45 | 注册维护任务 |
| | `start()` | ~70 | 启动调度线程 |
| | `stop()` | ~90 | 停止 |
| | `_run_loop()` | ~110 | 主循环 |
| `create_default_maintainer()` | ~200 | 工厂: consolidate / cleanup / optimize / health_check |

---

### 5.3 `budget_manager.py` (451 行)

- **用途**: LLM API 费用控制
- **存储文件**: `usage.json` (全量重写, 仅保留最近 7 天)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `BudgetManager` | `__init__()` | ~30 | 线程安全 (Lock) |
| | `check_budget(model, tokens)` | ~60 | 预算检查 |
| | `record_usage(model, tokens, cost)` | ~90 | 记录使用 |
| | `get_daily_usage()` | ~120 | |
| | `get_hourly_usage()` | ~140 | |
| | `auto_degrade(model)` | ~160 | 超预算自动降级 |
| | `_save()` | ~200 | ⚠️ **JSON 全量重写** usage.json |
| | `_load()` | ~220 | |
| | `_cleanup_old_data()` | ~250 | 清理 >7 天数据 |

---

### 5.4 `environment.py` (269 行)

- **用途**: 工作区环境隔离

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `EnvironmentManager` | `__init__(workspace_dir)` | ~20 | |
| | `setup()` | ~40 | 设置 HF_HOME / TRANSFORMERS_CACHE / TORCH_HOME / SPACY_DATA |
| | `load_config()` | ~80 | |
| | `save_config()` | ~100 | |
| | `cleanup_temp()` | ~130 | |
| | `cleanup_cache()` | ~150 | |
| | `get_disk_usage()` | ~180 | |

---

### 5.5 `llm_client.py` (509 行)

- **用途**: 多提供商 LLM 客户端 (OpenAI / Anthropic / Google Gemini)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `LLMClient` | `__init__(api_key, api_base, model)` | ~25 | 自动检测提供商 |
| | `complete(prompt)` | ~60 | 简单补全 |
| | `chat(messages)` | ~90 | 聊天 |
| | `achat(messages)` | ~130 | 异步聊天 |
| | `embed(text)` | ~170 | 嵌入 (转发) |
| | `extract_entities(text)` | ~200 | 实体提取 |
| | `summarize(text)` | ~240 | 摘要 |
| | `check_relevance(query, text)` | ~280 | 相关性判断 |
| | `_detect_provider()` | ~330 | 自动检测: openai/anthropic/google |
| | `_call_openai()` | ~370 | |
| | `_call_anthropic()` | ~410 | |
| | `_call_google()` | ~450 | |

---

### 5.6 `perf_monitor.py` (235 行)

- **用途**: 实时性能监控 (CPU/内存/延迟/吞吐/缓存命中/错误率)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `MetricType` (Enum) | | ~13 | LATENCY, THROUGHPUT, MEMORY, CPU, CACHE_HIT, ERROR_RATE |
| `Metric` (dataclass) | | ~24 | |
| `AggregatedMetric` (dataclass) | | ~32 | p50/p95/p99 |
| `PerformanceMonitor` | `__init__(window_size, ...)` | ~47 | deque 滑动窗口 |
| | `record(metric_type, value)` | ~73 | 记录指标 |
| | `timer(metric_type)` | ~82 | 上下文管理器计时器 |
| | `get_stats(metric_type)` | ~86 | 获取统计 (p50/p95/p99) |
| | `get_all_stats()` | ~110 | |
| | `start_collection()` | ~130 | 启动自动收集线程 |
| | `stop_collection()` | ~145 | |
| | `_collect_system_metrics()` | ~160 | psutil 采集 CPU/内存 |
| | `get_health()` | ~172 | 健康判断 |
| | `reset()` | ~200 | |
| `_Timer` | 上下文管理器 | ~207 | |
| `get_monitor()` | | ~228 | 全局单例 |

---

### 5.7 `task_manager.py` (550 行)

- **用途**: 后端任务追踪 (创建/进度/完成/失败/取消 + 订阅推送)
- 🎭 **character_id 引用**: `Task.character_id` 字段 (L71), `create_task(character_id=)` 参数, `get_active_tasks(character_id=)` 过滤
- 🔮 **foreshadowing 引用**: `TaskType.FORESHADOW_ANALYSIS` (L44), `TaskType.CONTEXT_EXTRACTION` (L45)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `TaskStatus` (Enum) | | ~22 | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED |
| `TaskType` (Enum) | | ~30 | 15 种类型, 含 🔮 `FORESHADOW_ANALYSIS`, `CONTEXT_EXTRACTION` |
| `Task` (dataclass) | `to_dict()`, `_elapsed_ms()` | ~60 | 含 🎭 `user_id`, `character_id` |
| `TaskManager` (单例) | `create_task()` | ~145 | |
| | `start_task()` | ~185 | |
| | `update_task()` | ~210 | |
| | `complete_task()` | ~240 | |
| | `fail_task()` | ~280 | |
| | `cancel_task()` | ~315 | |
| | `get_active_tasks(user_id, character_id, task_type)` | ~340 | |
| | `get_recent_tasks(limit)` | ~370 | |
| | `get_task(task_id)` | ~400 | |
| | `subscribe(callback)` | ~415 | |
| | `unsubscribe(callback)` | ~425 | |
| | `clear_completed_tasks()` | ~445 | |
| `TaskContext` | `__enter__/__exit__` | ~465 | with 语句自动管理生命周期 |
| `get_task_manager()` | | ~460 | 全局单例 |

---

### 5.8 `warmup.py` (188 行)

- **用途**: 模型和资源预热管理 (懒加载 + 后台预热 + 优先级)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `WarmupStatus` (Enum) | | ~10 | NOT_STARTED, IN_PROGRESS, COMPLETED, FAILED |
| `WarmupTask` (dataclass) | | ~16 | name, loader, priority, status, result |
| `WarmupManager` | `__init__()` | ~42 | |
| | `register(name, loader, priority)` | ~55 | 注册预热任务 |
| | `get(name)` | ~68 | 懒加载获取 |
| | `_load_now(name)` | ~82 | 立即加载 |
| | `warmup_async(names)` | ~110 | 后台线程预热 |
| | `_warmup_worker(names)` | ~125 | 按优先级排序后加载 |
| | `warmup_sync(names)` | ~140 | 同步预热 |
| | `get_status()` | ~145 | |
| | `is_ready(name)` | ~162 | |
| | `unload(name)` | ~167 | |
| | `unload_all()` | ~177 | |
| `get_warmup_manager()` | | ~185 | 全局单例 |

---

## 6. recall/embedding/

### 6.1 `__init__.py` (20 行)

- **导出**: `EmbeddingBackend`, `EmbeddingConfig`, `EmbeddingBackendType`, `create_embedding_backend`, `get_available_backends`

---

### 6.2 `base.py` (267 行)

- **用途**: Embedding 后端抽象基类 + 配置 + NoneBackend

| 类 | 方法/字段 | 行号 | 说明 |
|----|-----------|------|------|
| `EmbeddingBackendType` (Enum) | | ~12 | LOCAL, OPENAI, SILICONFLOW, CUSTOM, NONE |
| `EmbeddingConfig` (dataclass) | 字段 | ~22-42 | backend, local_model, api_key, api_base, api_model, dimension, batch_size, normalize, cache_embeddings, max_cache_size |
| | `lite()` | ~46 | Lite 模式 (禁用向量) |
| | `cloud_openai(api_key, ...)` | ~76 | OpenAI 配置 |
| | `cloud_siliconflow(api_key, ...)` | ~98 | 硅基流动配置 |
| | `cloud_custom(api_key, api_base, ...)` | ~118 | 自定义 API 配置 |
| | `local()` | ~140 | 本地模型配置 |
| | `hybrid_*()` (3个) | 各处 | ⚠️ **已弃用别名** (向后兼容) |
| `EmbeddingBackend` (ABC) | `__init__(config, cache_dir)` | ~155 | |
| | `_load_disk_cache()` | ~170 | pickle 缓存加载 |
| | `_save_disk_cache()` | ~190 | pickle 全量重写 |
| | `dimension` (abstract) | ~205 | |
| | `is_available` (abstract) | ~210 | |
| | `encode(text)` (abstract) | ~215 | |
| | `encode_batch(texts)` (abstract) | ~220 | |
| | `encode_with_cache(text)` | ~225 | 带缓存编码 (内存 + 磁盘), 每 50 次新缓存保存到磁盘 |
| | `clear_cache()` | ~250 | |
| `NoneBackend` | | ~255 | dimension=0, `encode()` 抛异常 |

**缓存机制**: 内存 dict + pickle 磁盘持久化。LRU 简单实现: 超 max_cache_size 时清空一半。每 50 次新缓存触发一次 `_save_disk_cache()` (pickle 全量重写)。

---

### 6.3 `factory.py` (199 行)

- **用途**: Embedding 后端工厂 + 自动选择

| 函数 | 行号 | 说明 |
|------|------|------|
| `_safe_print(msg)` | ~11 | Windows GBK 兼容打印 |
| `create_embedding_backend(config, cache_dir)` | ~38 | 主工厂方法 (NONE/LOCAL/API) |
| `get_available_backends()` | ~105 | 检测可用后端列表 |
| `auto_select_backend()` | ~135 | 自动选择最佳后端 (优先级: env → API → local → lite) |

**自动选择优先级**:
1. 环境变量 `RECALL_EMBEDDING_MODE` 显式指定
2. `EMBEDDING_API_KEY` + `EMBEDDING_API_BASE` 已配置 → Cloud API
3. `sentence-transformers` 已安装 → Local
4. 回退到 Lite 模式

---

### 6.4 `api_backend.py` (440 行)

- **用途**: API Embedding 后端 (OpenAI / 硅基流动 / Google / Voyage / Cohere)

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `RateLimiter` | `__init__(max_requests, window_seconds)` | ~39 | 滑动窗口速率限制 |
| | `acquire(timeout)` | ~55 | 获取许可 (阻塞) |
| `APIEmbeddingBackend` | `MODEL_DIMENSIONS` (class var) | ~115 | 14 个模型维度映射 |
| | `DEFAULT_BASES` (class var) | ~140 | 默认 API 地址 |
| | `__init__(config)` | ~148 | |
| | `_get_api_key_from_env()` | ~175 | |
| | `dimension` (property) | ~185 | |
| | `is_available` (property) | ~190 | |
| | `_detect_embedding_provider()` | ~195 | v5.0: 自动检测提供商 (openai/google/voyage/cohere) |
| | `client` (property) | ~230 | 懒创建客户端 (自动路由) |
| | `encode(text)` | ~275 | v5.0: 自动路由到对应提供商 |
| | `_encode_openai(text)` | ~285 | 带限流 + 3 次重试 + 指数退避 |
| | `_encode_google(text)` | ~330 | |
| | `_encode_voyage(text)` | ~345 | |
| | `_encode_cohere(text)` | ~360 | |
| | `encode_batch(texts)` | ~375 | 自动路由批量编码 |
| | `_encode_batch_openai(texts)` | ~385 | 分批 (max 100) + 限流 + 重试 |
| | `_encode_batch_google(texts)` | ~415 | 逐条编码 (无原生批量) |
| | `_encode_batch_voyage(texts)` | ~425 | 分批 (max 128) |
| | `_encode_batch_cohere(texts)` | ~435 | 分批 (max 96) |

---

### 6.5 `local_backend.py` (103 行)

- **用途**: 本地 sentence-transformers 后端

| 类 | 方法 | 行号 | 说明 |
|----|------|------|------|
| `LocalEmbeddingBackend` | `__init__(config, cache_dir)` | ~47 | |
| | `dimension` (property) | ~53 | 懒获取 |
| | `is_available` (property) | ~59 | 检查 sentence-transformers |
| | `model` (property) | ~66 | 懒加载模型 (~800MB) |
| | `encode(text)` | ~86 | float32 编码 |
| | `encode_batch(texts)` | ~93 | 批量编码 |

---

## 7. 横切关注点分析

### 7.1 JSON I/O 模式（全量重写 vs 增量追加）

| 文件 | 存储文件 | 写入模式 | 触发频率 | 严重度 |
|------|----------|----------|----------|--------|
| `layer0_core.py` | `core.json` | **全量重写** | 低频 (设定变更) | 🟢 低 |
| `layer1_consolidated.py` | `entities_NNNN.json` | **全量重写** | 每次 add_or_update | 🔴 高 |
| `multi_tenant.py` | `memories.json` | **全量重写** | 每次 add/delete/update | 🔴 高 |
| `volume_manager.py` | `*.jsonl` | ✅ **增量追加** | 每次 append_turn | 🟢 低 |
| `volume_manager.py` | `memory_id_index.json` | **全量重写** | 每次保存索引 | 🟡 中 |
| `episode_store.py` | `episodes.jsonl` | ✅ **增量追加** (save) | 正常写入 | 🟢 低 |
| `episode_store.py` | `episodes.jsonl` | **全量重写** (update_links) | link 更新时 | 🟡 中 |
| `entity_index.py` | `entity_index.json` | **全量重写** | 每次 add | 🔴 高 |
| `fulltext_index.py` | `fulltext_index.json` | **全量重写** | 每次 flush | 🔴 高 |
| `inverted_index.py` | `inverted_wal.jsonl` | ✅ **WAL 追加** | 日常写入 | 🟢 低 |
| `inverted_index.py` | `inverted_index.json` | **全量重写** (compact) | 10K条阈值 | 🟡 中 |
| `metadata_index.py` | `metadata_index.json` | **全量重写** | 每 100 次脏操作 | 🟡 中 |
| `ngram_index.py` | `ngram_index.json` | **全量重写** | 每次 save | 🔴 高 |
| `ngram_index.py` | `ngram_raw_content.jsonl` | ✅ **增量追加** | 每次 append | 🟢 低 |
| `temporal_index.py` | `temporal_index.json` | **全量重写** | 每次 flush | 🔴 高 |
| `vector_index.py` | `vector_index.faiss` | FAISS native save | 每次 _save | 🟡 中 |
| `vector_index.py` | `vector_mapping.json` | **全量重写** | 每次 _save | 🟡 中 |
| `budget_manager.py` | `usage.json` | **全量重写** | 每次记录使用 | 🟢 低 (小文件) |
| `base.py` (embedding) | `embedding_cache.pkl` | **pickle 全量重写** | 每 50 次新缓存 | 🟡 中 |

**总结**: 13 个文件使用全量重写模式, 仅 4 个使用增量追加 (JSONL/WAL)。最严重的是 `ConsolidatedMemory`, `ScopedMemory`, `EntityIndex`, `FullTextIndex` — 每次单条写入都触发全量序列化。

---

### 7.2 O(n) 操作清单

| 位置 | 操作 | 数据规模 | 严重度 |
|------|------|----------|--------|
| `episode_store.py` | `get_by_memory_id()` 等 5 个方法 | 全部 episodes | 🟡 |
| `layer1_consolidated.py` | `get_entity(name)`, `search_by_name()` | 全部实体 | 🟡 |
| `layer2_working.py` | `_evict_one()` min() | 活跃实体 (通常 <100) | 🟢 |
| `multi_tenant.py` | `search()`, `delete()`, `update()` | 单 scope 全部记忆 | 🟡 |
| `volume_manager.py` | `get_turn_by_memory_id()` fallback | **所有卷所有文件** | 🔴 |
| `volume_manager.py` | `search_content()` | **所有卷所有 turn** | 🔴 |
| `entity_index.py` | `search(query)` | 全部实体名 | 🟡 |
| `ngram_index.py` | `_raw_text_fallback_search()` | 全部原始文本 | 🔴 |
| `temporal_index.py` | `_unindex_entry()` list.remove() | 排序列表长度 | 🟡 |
| `vector_index.py` | `get_vector_by_doc_id()` list.index() | turn_mapping 长度 | 🟡 |
| `vector_index.py` | `remove_by_doc_ids()` 重建 FAISS | 全部向量 | 🔴 |

---

### 7.3 character_id / mode / foreshadowing / RP 引用

#### character_id 引用

| 文件 | 位置 | 用途 |
|------|------|------|
| `multi_tenant.py` | `MemoryScope.character_id` (L16) | 路径隔离核心字段 |
| `multi_tenant.py` | `to_path()` | 目录结构: `user_id/character_id/session_id` |
| `multi_tenant.py` | `list_characters()` | 列出角色 |
| `episode_store.py` | `get_by_character(character_id)` (~L100) | 按角色查询事件 |
| `task_manager.py` | `Task.character_id` (L71) | 任务追踪关联角色 |
| `task_manager.py` | `create_task(character_id=)` | 创建任务时指定角色 |
| `task_manager.py` | `get_active_tasks(character_id=)` | 按角色过滤任务 |
| `vector_index_ivf.py` | `search(user_id=)` | 多租户向量搜索过滤 (注: 用 user_id 不是 character_id) |

#### RP/Roleplay 引用

| 文件 | 位置 | 用途 |
|------|------|------|
| `layer0_core.py` | `character_card` (L15) | 角色卡 |
| `layer0_core.py` | `world_setting` (L16) | 世界观设定 |
| `layer0_core.py` | `writing_style` (L17) | 写作风格 |
| `layer0_core.py` | `get_injection_text('roleplay')` | RP 场景注入 |
| `context_builder.py` | `optimize_for_roleplay()` (~L80) | RP 上下文优化 |
| `context_builder.py` | `_build_character_prompt()` (~L100) | 角色 Prompt |
| `context_builder.py` | `_prioritize_character_memories()` (~L130) | 角色记忆优先 |

#### Foreshadowing (伏笔) 引用

| 文件 | 位置 | 用途 |
|------|------|------|
| `task_manager.py` | `TaskType.FORESHADOW_ANALYSIS` (L44) | 伏笔分析任务类型 |
| `task_manager.py` | `TaskType.CONTEXT_EXTRACTION` (L45) | 条件提取任务类型 |

#### Mode 引用

| 文件 | 位置 | 用途 |
|------|------|------|
| `base.py` (embedding) | `EmbeddingBackendType` | LOCAL / OPENAI / SILICONFLOW / CUSTOM / NONE |
| `base.py` (embedding) | `lite()` / `local()` / `cloud_*()` | 3 种运行模式 |
| `factory.py` | `auto_select_backend()` | RECALL_EMBEDDING_MODE 环境变量 |
| `layer0_core.py` | `get_injection_text(scenario)` | 'roleplay' / 'coding' / 'general' 3 场景 |
| `config.py` (retrieval) | `default()` / `fast()` / `accurate()` | 3 种检索模式 |

---

### 7.4 死代码 / 未使用方法

| 项目 | 文件 | 置信度 | 说明 |
|------|------|--------|------|
| **ParallelRetriever** | `parallel_retrieval.py` (218行) | 🔴 高 | EightLayer 和 ElevenLayer 都自己实现了 `_parallel_recall()` + ThreadPoolExecutor, 不使用此类 |
| **EightLayerRetrieverCompat** | `eleven_layer.py` (~L1200) | 🟡 中 | 8层→11层兼容适配器, 可能仅在迁移期使用 |
| `hybrid_*()` 别名 (3个) | `base.py` (embedding) | 🟡 中 | 标记为 `[已弃用]`, 保留仅为向后兼容 |
| `full()` 别名 | `base.py` (embedding) | 🟡 中 | 标记为 `[已弃用]` |
| `lightweight()` 别名 | `base.py` (embedding) | 🟡 中 | 标记为 `[已弃用]` |
| `InvertedIndex._save()` | `inverted_index.py` (~L45) | 🔴 高 | 现为 **no-op**, 已被 WAL 模式取代 |
| `_encode_batch_google()` | `api_backend.py` (~L415) | 🟡 低 | 逐条调用, 未利用任何批量 API (功能正确但命名可能误导) |

---

### 7.5 Delete Cascade 完整分析（13 存储位置）

当调用 `delete(memory_id)` 删除一条记忆时, 必须清理以下 **13 个存储位置**:

| # | 存储位置 | 文件 | Cascade 方法 | 状态 |
|---|----------|------|-------------|------|
| 1 | **ScopedMemory** (memories.json) | `multi_tenant.py` | `delete(memory_id)` | ✅ 有, 但 **不级联到索引** |
| 2 | **ConsolidatedMemory** (L1 entities) | `layer1_consolidated.py` | `remove_by_memory_ids()` | ✅ 有 |
| 3 | **VolumeManager** (L3 archive) | `volume_manager.py` | ❌ **无 per-memory delete** | ❌ 缺失 |
| 4 | **memory_id_index.json** | `volume_manager.py` | ❌ **无 remove 方法** | ❌ 缺失 |
| 5 | **EpisodeStore** (episodes.jsonl) | `episode_store.py` | ❌ **无 delete-by-id** | ❌ 缺失 |
| 6 | **EntityIndex** (entity_index.json) | `entity_index.py` | `remove_by_turn_references()` | ✅ 有 |
| 7 | **FullTextIndex** (fulltext_index.json) | `fulltext_index.py` | `remove_by_doc_ids()` | ✅ 有 |
| 8 | **InvertedIndex** (inverted_index) | `inverted_index.py` | `remove_by_memory_ids()` | ✅ 有 |
| 9 | **MetadataIndex** (metadata_index.json) | `metadata_index.py` | `remove_batch()` | ✅ 有 |
| 10 | **NgramIndex** (ngram_index) | `ngram_index.py` | `remove_by_memory_ids()` | ✅ 有 |
| 11 | **TemporalIndex** (temporal_index.json) | `temporal_index.py` | `remove()` (单条) | ⚠️ 有但无批量方法 |
| 12 | **VectorIndex** (vector_index.faiss) | `vector_index.py` | `remove_by_doc_ids()` | ✅ 有 (需重建FAISS) |
| 13 | **VectorIndexIVF** (vector_index_ivf.faiss) | `vector_index_ivf.py` | `remove()` (软删除) | ✅ 有 (软删除, 需rebuild硬删) |

**级联缺失汇总**:
- ❌ **VolumeManager**: JSONL 文件无法高效删除单条。需要: 标记删除 + 后台 compaction
- ❌ **memory_id_index.json**: 需新增 `remove_from_index(memory_id)` 方法
- ❌ **EpisodeStore**: 需新增 `delete(episode_id)` 或 `delete_by_memory_id(memory_id)` 方法
- ⚠️ **TemporalIndex**: 有单条 `remove()` 但无 `remove_by_memory_ids()` 批量方法, 需要调用方手动遍历
- ⚠️ **ScopedMemory.delete()**: 只删自身, **不调用任何索引的删除方法** — 需要在上游 engine 层统一编排级联

---

## 8. 专题分析

### 8.1 VolumeManager O(n) 扫描问题

**位置**: `volume_manager.py` L175-218 `get_turn_by_memory_id()`

**三级回退策略**:
1. **O(1)**: 查 `memory_id_index` (内存 dict)
2. **O(n) 内存**: 扫描所有已加载 VolumeData 的所有 turn
3. **O(n) 磁盘**: 逐文件读取所有 `*.jsonl` 文件并逐行解析

当 memory_id 不在索引中时(如索引损坏/新数据未刷新), 直接退化为全磁盘扫描。

**`search_content()`** (L220-268): 无任何加速结构, 始终 O(n) 扫描全部卷。

**建议修复**:
- 确保 `memory_id_index` 在每次 `append_turn()` 时同步更新
- 为 `search_content()` 集成 FullTextIndex/NgramIndex 而非直接扫描原始数据
- 考虑 SQLite WAL 替代 JSONL 以支持高效查询

---

### 8.2 InvertedIndex 全量 JSON Dump 问题

**现状**: 已通过 **WAL 模式** 缓解。

- 日常写入: 追加到 `inverted_wal.jsonl` (O(1) append)
- `_save()`: 现为 no-op
- `_compact()`: 当 WAL 达到 10,000 条时触发全量重写, 合并 WAL 到 `inverted_index.json`

**剩余风险**: 
- `_compact()` 仍然是阻塞式全量 JSON dump
- 如果索引体积很大 (>100MB), compact 可能阻塞数秒
- `remove_by_memory_ids()` 操作后需要手动调 compact 或 flush

**建议**: 考虑将 compact 移到后台线程, 或使用 LSM-tree 模式 (分级合并)。

---

### 8.3 MetadataIndex 实现

**结构**: 5 个独立的倒排映射 (dict of dict):
- `by_source`: source → {doc_id → True}
- `by_tag`: tag → {doc_id → True}
- `by_category`: category → {doc_id → True}
- `by_content_type`: content_type → {doc_id → True}
- `by_event_date`: event_date → {doc_id → True}

**查询**: `query(conditions)` 对多条件做集合交集 (AND 语义)。

**性能**: 
- 查询: O(结果集大小) — 利用集合交集
- 写入: O(1) 更新 dict, 但 dirty_count 达 100 时触发全量 JSON 重写
- 删除: O(5 × K) 扫描全部值 (K = 某 doc_id 出现的条目数)

**主要问题**: 全量 JSON 重写。改进方向: 采用 WAL 或 SQLite。

---

### 8.4 MultiTenantStorage / EnvironmentIsolation

**MultiTenantStorage** (`multi_tenant.py`):
- 路径隔离: `{base_dir}/{user_id}/{character_id}/{session_id}/memories.json`
- 每个 scope 独立的 `ScopedMemory` 实例
- `delete_session()` 使用 `shutil.rmtree()` 物理删除整个会话目录
- ❌ 不管理索引 — 索引在 scope 之外, 删除 session 不清理对应索引条目

**EnvironmentManager** (`environment.py`):
- 设置 `HF_HOME`, `TRANSFORMERS_CACHE`, `TORCH_HOME`, `SPACY_DATA` 等环境变量
- 所有模型/缓存隔离到 `recall_data/models/` 下
- `cleanup_temp()`, `cleanup_cache()`, `get_disk_usage()` 运维工具

**隔离缺口**: 索引是全局的 (所有 user/character 共享), 但存储是隔离的。这导致:
1. 删除 session 后索引中仍残留对应记忆的条目 (phantom entries)
2. `VectorIndexIVF` 的 `search(user_id=)` 是唯一在索引层做租户过滤的

---

### 8.5 ParallelRetriever（死代码）

**文件**: `parallel_retrieval.py` (218 行)

**证据**:
1. `EightLayerRetriever._parallel_recall()` 自己使用 `ThreadPoolExecutor(max_workers=4)` 实现 4 路并行召回
2. `ElevenLayerRetriever._parallel_recall()` 同样自己实现 3 路并行召回
3. 两者都不引用 `ParallelRetriever`
4. `ParallelRetriever` 在 `__init__.py` 中被导出, 但无已知消费者

**结论**: **确认为死代码**。两个实际的检索器都内联了并行逻辑。可以安全移除, 或将内联的并行逻辑重构为使用 `ParallelRetriever`。

---

### 8.6 ElevenLayerRetriever 实现

**完整 11 层漏斗**:

| 层 | 名称 | 功能 | 实现状态 |
|----|------|------|----------|
| L1 | Bloom Filter | 快速排除不可能的候选 | ✅ |
| L2 | Temporal Filter | 时间窗口过滤 | ✅ (新增) |
| L3 | Inverted Index | 关键词倒排召回 | ✅ |
| L4 | Entity Index | 实体关联召回 | ✅ |
| L5 | Graph Traversal | 知识图谱遍历 | ✅ (新增) |
| L6 | Ngram Index | N-gram 模糊匹配 | ✅ |
| L7 | Vector Coarse | 向量粗排 (ANN) | ✅ |
| L8 | Vector Fine | 向量精排 (重算分数) | ✅ |
| L9 | Reranker | 可插拔重排 (Builtin/Cohere/CrossEncoder) | ✅ |
| L10 | Cross Encoder | 交叉编码器精排 | ✅ (新增) |
| L11 | LLM Filter | LLM 相关性判断 (async) | ✅ |

**并行模式**: 当 `use_parallel_recall=True` 时, L3/L4/L7 并行执行 + RRF 融合, 然后经过 L8-L11 精排。

**`EightLayerRetrieverCompat`**: 适配器类, 将 8 层接口映射到 11 层实现, 通过配置禁用 L2 (Temporal), L5 (Graph), L10 (CrossEncoder)。

---

### 8.7 VectorIndex vs VectorIndexIVF

| 特性 | VectorIndex | VectorIndexIVF |
|------|-------------|----------------|
| **FAISS 类型** | IndexFlatIP (暴力) | IVF-HNSW (近似) |
| **搜索复杂度** | O(n) | O(nprobe × cluster_size) |
| **训练需求** | 无 | 需要 ≥ 训练阈值的向量 |
| **添加延迟** | O(1) | 训练前暂存, 训练后 O(1) |
| **删除方式** | 全量重建 FAISS | 软删除 (标记) + rebuild 硬删 |
| **多租户** | ❌ 无 | ✅ user_id 过滤 |
| **存储文件** | .faiss + mapping.json + config.json | .faiss + mapping.npy + metadata.json + pending.npy |
| **适用场景** | <10K 向量 | >10K 向量 |
| **代码行数** | 456 | 566 |

**关键差异**:
1. **搜索性能**: IVF-HNSW 在大数据集上快数量级, FlatIP 在小数据集上更精确
2. **删除**: IVF 的软删除避免了每次删除都重建索引的开销
3. **Pending 机制**: IVF 在训练前将向量暂存到 `vector_pending_ivf.npy`, 达到阈值后一次性训练
4. **多租户**: 仅 IVF 版本在 search 时支持 `user_id` 参数过滤

---

## 附录: 代码重复 / DRY 违反

| 重复项 | 出现位置 | 说明 |
|--------|----------|------|
| `_safe_print()` | `factory.py`, `api_backend.py`, `local_backend.py` | 完全相同的 emoji→ASCII 映射函数, 复制了 3 份 |
| 并行召回 (ThreadPoolExecutor) | `eight_layer.py`, `eleven_layer.py` | 各自内联实现, 且有 `ParallelRetriever` 未被使用 |
| JSON 全量重写模式 | 几乎所有 storage/index 文件 | 无统一的持久化抽象层 |

---

*报告结束*
