# Recall-ai 测试套件与配置分析报告

> 生成日期: 2026-02-25  
> 项目版本: **v5.0.0**  
> 分析范围: `tests/`、`recall/config.py`、`recall/mode.py`、`recall/cli.py`、`recall/init.py`、`recall/__init__.py`、`recall/__main__.py`、`pyproject.toml`、`recall_data/config/`

---

## 目录

1. [版本与入口信息](#1-版本与入口信息)
2. [配置体系总览](#2-配置体系总览)
3. [CLI 命令一览](#3-cli-命令一览)
4. [初始化流程 (init.py)](#4-初始化流程-initpy)
5. [运行时配置文件 (api_keys.env)](#5-运行时配置文件-api_keysenv)
6. [character_id / mode / foreshadowing 引用汇总](#6-character_id--mode--foreshadowing-引用汇总)
7. [测试文件逐一分析](#7-测试文件逐一分析)
8. [Engine/Server 方法覆盖矩阵](#8-engineserver-方法覆盖矩阵)
9. [总结与建议](#9-总结与建议)

---

## 1. 版本与入口信息

| 项目 | 值 |
|------|------|
| `recall/version.py` | `__version__ = '5.0.0'` |
| `pyproject.toml` version | `5.0.0` |
| Python 要求 | `>=3.10` |
| 许可证 | MIT |
| 入口脚本 | `recall = "recall.cli:main"` / `recall-mcp = "recall.mcp_server:main"` |
| `__main__.py` | 直接调用 `recall.cli:main` |
| `__init__.py` 导出 | `RecallEngine`, `__version__`, `LiteConfig`, `LightweightConfig` |
| `__init__.py` 副作用 | 调用 `_setup_isolated_environment()` 设置 JIEBA_CACHE / HF_HOME / TORCH_HOME / SENTENCE_TRANSFORMERS_HOME 环境变量 |

---

## 2. 配置体系总览

### 2.1 `recall/config.py` — 代码级配置

#### LiteConfig（轻量模式）

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_VECTOR_INDEX` | `False` | 不加载 sentence-transformers (~400MB) |
| `ENABLE_SPACY_FULL` | `False` | 不加载完整 spaCy (~50MB) |
| `ENTITY_EXTRACTOR` | `'jieba_rules'` | 用 jieba + 规则替代 spaCy |
| `RETRIEVAL_LAYERS` | `[1,2,3,5,7,8]` | 跳过第4层(向量)和第6层(语义) |
| `MAX_CACHED_TURNS` | `1000` | 减少缓存 |
| `MAX_INDEX_SIZE_MB` | `30` | 限制索引大小 |

别名: `LightweightConfig = LiteConfig`

#### TripleRecallConfig（三路召回配置）

| 选项 | 默认值 | 环境变量 |
|------|--------|----------|
| `enabled` | `True` | `TRIPLE_RECALL_ENABLED` |
| `vector_weight` | `1.0` | `TRIPLE_RECALL_VECTOR_WEIGHT` |
| `keyword_weight` | `1.2` | `TRIPLE_RECALL_KEYWORD_WEIGHT` |
| `entity_weight` | `1.0` | `TRIPLE_RECALL_ENTITY_WEIGHT` |
| `rrf_k` | `60` | `TRIPLE_RECALL_RRF_K` |
| `fallback_enabled` | `True` | `FALLBACK_ENABLED` |
| `fallback_parallel` | `True` | `FALLBACK_PARALLEL` |
| `fallback_workers` | `4` | `FALLBACK_WORKERS` |
| `fallback_max_results` | `50` | `FALLBACK_MAX_RESULTS` |
| `hnsw_m` | `32` | `VECTOR_IVF_HNSW_M` |
| `hnsw_ef_construction` | `200` | `VECTOR_IVF_HNSW_EF_CONSTRUCTION` |
| `hnsw_ef_search` | `64` | `VECTOR_IVF_HNSW_EF_SEARCH` |

工厂方法:
- `TripleRecallConfig.default()` — 平衡模式
- `TripleRecallConfig.max_recall()` — 最大召回（hnsw_m=48, ef_search=128, keyword_weight=1.5）
- `TripleRecallConfig.fast()` — 快速模式（hnsw_m=16, ef_search=32, fallback_workers=2）
- `TripleRecallConfig.from_env()` — 从环境变量加载

#### LightweightEntityExtractor

内置轻量实体提取器，使用正则 + jieba 分词，无 spaCy 依赖。

### 2.2 `recall/mode.py` — 模式管理

```python
class RecallMode(Enum):
    ROLEPLAY = "roleplay"          # RP 模式（默认）
    GENERAL = "general"            # 通用模式
    KNOWLEDGE_BASE = "knowledge_base"  # 知识库模式
```

#### ModeConfig 各开关默认值

| 开关 | ROLEPLAY | GENERAL | KNOWLEDGE_BASE | 覆盖环境变量 |
|------|----------|---------|----------------|--------------|
| `foreshadowing_enabled` | ✅ True | ❌ False | ❌ False | `FORESHADOWING_ENABLED` |
| `character_dimension_enabled` | ✅ True | ❌ False | ❌ False | `CHARACTER_DIMENSION_ENABLED` |
| `rp_consistency_enabled` | ✅ True | ❌ False | ❌ False | `RP_CONSISTENCY_ENABLED` |
| `rp_relation_types` | ✅ True | ❌ False | ❌ False | `RP_RELATION_TYPES` |
| `rp_context_types` | ✅ True | ❌ False | ❌ False | `RP_CONTEXT_TYPES` |

主环境变量: `RECALL_MODE`（默认 `roleplay`）

### 2.3 `pyproject.toml` — 安装模式

| 安装模式 | 含义 | 核心额外依赖 |
|----------|------|-------------|
| `lite` | 无向量搜索 | (无) |
| `cloud` | API Embedding | faiss-cpu |
| `local` | 本地 Embedding (GPU) | sentence-transformers, faiss-cpu |
| `local-cpu` | 本地 Embedding (CPU) | sentence-transformers, faiss-cpu |
| `enterprise` | 企业级 | faiss-cpu, networkx, kuzu |
| `enterprise-cpu` | 企业级 CPU | sentence-transformers, faiss-cpu, networkx, kuzu |
| `mcp` | MCP 服务 | mcp, httpx-sse, uvicorn, starlette |
| `dev` | 开发 | pytest, black, ruff |

旧名称兼容: `lightweight`→`lite`, `hybrid`→`cloud`, `full`→`local`

---

## 3. CLI 命令一览

入口: `recall` (click group)

| 命令 | 参数/选项 | 说明 | Engine 方法 |
|------|----------|------|------------|
| `recall init` | `--data-root`, `--lightweight` | 初始化环境 | `RecallInit.ensure_directories()`, `setup_environment()` |
| `recall add <content>` | `--user`, `--metadata` | 添加记忆 | `engine.add()` |
| `recall search <query>` | `--user`, `--top-k` | 搜索记忆 | `engine.search()` |
| `recall list` | `--user`, `--limit` | 列出记忆 | `engine.get_all()` |
| `recall delete <memory_id>` | `--user` | 删除记忆 | `engine.delete()` |
| `recall stats` | (无) | 显示统计 | `engine.get_stats()` |
| `recall serve` | `--host`, `--port`, `--reload` | 启动 API 服务器 | `uvicorn recall.server:app` |
| `recall consolidate` | `--user` | 执行记忆整合 | `engine.consolidate()` |
| `recall reset` | `--user`, `--confirm` | 重置记忆 | `engine.reset()` |
| `recall foreshadowing plant <content>` | `--importance` | 埋下伏笔 | `engine.plant_foreshadowing()` |
| `recall foreshadowing list` | (无) | 列出活跃伏笔 | `engine.get_active_foreshadowings()` |
| `recall foreshadowing resolve <id> <resolution>` | (无) | 解决伏笔 | `engine.resolve_foreshadowing()` |

**stats 命令引用 `foreshadowings.active` 字段。**

---

## 4. 初始化流程 (init.py)

`RecallInit` 类职责:

1. **`get_data_root()`**: 优先级 base_path > 环境变量 `RECALL_DATA_ROOT` > `./recall_data/`
2. **`ensure_directories()`**: 创建 `data/`, `models/spacy`, `models/sentence-transformers`, `models/huggingface`, `models/torch`, `cache/`, `logs/`
3. **`setup_environment()`**: 重定向所有库缓存到项目目录:
   - `SENTENCE_TRANSFORMERS_HOME`
   - `HF_HOME`, `HUGGINGFACE_HUB_CACHE`, `TRANSFORMERS_CACHE`
   - `TORCH_HOME`
   - `XDG_CACHE_HOME`
   - 禁用 telemetry (`HF_HUB_DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `ANONYMIZED_TELEMETRY`)
4. **`run_init_wizard()`**: 交互式向导，获取 API key（支持 `LLM_API_KEY` / `OPENAI_API_KEY`），保存到 `recall_data/config.json`
5. **`auto_init_for_st()`**: SillyTavern 静默初始化
6. **`load_config()`**: 加载 `recall_data/config.json`

---

## 5. 运行时配置文件 (api_keys.env)

路径: `recall_data/config/api_keys.env` (607行)  
安装模式文件: `recall_data/config/install_mode` → 当前值 `enterprise`

### 5.1 完整配置选项清单（含默认值）

#### 必填配置

| 键 | 当前值 | 说明 |
|----|--------|------|
| `EMBEDDING_API_KEY` | sk-cboq…(已配置) | Embedding API 密钥 |
| `EMBEDDING_API_BASE` | https://api.siliconflow.cn/v1 | Embedding API 地址 |
| `EMBEDDING_MODEL` | BAAI/bge-m3 | Embedding 模型名 |
| `EMBEDDING_DIMENSION` | 1024 | Embedding 维度 |
| `RECALL_EMBEDDING_MODE` | auto | auto/local/api |
| `LLM_API_KEY` | sk-7e71…(已配置) | LLM API 密钥 |
| `LLM_API_BASE` | https://api.deepseek.com/v1 | LLM API 地址 |
| `LLM_MODEL` | deepseek-chat | LLM 模型名 |
| `LLM_TIMEOUT` | 60 | LLM 请求超时(秒) |

#### Embedding 速率限制

| 键 | 默认值 |
|----|--------|
| `EMBEDDING_RATE_LIMIT` | 10 |
| `EMBEDDING_RATE_WINDOW` | 60 |

#### 伏笔分析器 (Foreshadowing)

| 键 | 默认值 | 说明 |
|----|--------|------|
| `FORESHADOWING_LLM_ENABLED` | true | 启用 LLM 伏笔分析 |
| `FORESHADOWING_TRIGGER_INTERVAL` | 10 | 每N轮触发分析 |
| `FORESHADOWING_AUTO_PLANT` | true | 自动埋下伏笔 |
| `FORESHADOWING_AUTO_RESOLVE` | false | 自动解决伏笔 |
| `FORESHADOWING_MAX_RETURN` | 10 | 上下文返回伏笔数 |
| `FORESHADOWING_MAX_ACTIVE` | 50 | 活跃伏笔上限 |
| `FORESHADOWING_MAX_TOKENS` | 2000 | 伏笔分析 LLM tokens |

#### 持久条件系统

| 键 | 默认值 |
|----|--------|
| `CONTEXT_TRIGGER_INTERVAL` | 5 |
| `CONTEXT_MAX_CONTEXT_TURNS` | 20 |
| `CONTEXT_MAX_PER_TYPE` | 10 |
| `CONTEXT_MAX_TOTAL` | 100 |
| `CONTEXT_DECAY_DAYS` | 14 |
| `CONTEXT_DECAY_RATE` | 0.05 |
| `CONTEXT_MIN_CONFIDENCE` | 0.1 |

#### 上下文构建

| 键 | 默认值 |
|----|--------|
| `BUILD_CONTEXT_INCLUDE_RECENT` | 10 |
| `PROACTIVE_REMINDER_ENABLED` | true |
| `PROACTIVE_REMINDER_TURNS` | 50 |
| `BUILD_CONTEXT_MAX_TOKENS` | 4000 |

#### 智能去重

| 键 | 默认值 |
|----|--------|
| `DEDUP_EMBEDDING_ENABLED` | true |
| `DEDUP_HIGH_THRESHOLD` | 0.85 |
| `DEDUP_LOW_THRESHOLD` | 0.70 |
| `DEDUP_JACCARD_THRESHOLD` | 0.85 |
| `DEDUP_SEMANTIC_THRESHOLD` | 0.90 |
| `DEDUP_SEMANTIC_LOW_THRESHOLD` | 0.80 |
| `DEDUP_LLM_ENABLED` | false |
| `DEDUP_LLM_MAX_TOKENS` | 100 |

#### 知识图谱

| 键 | 默认值 |
|----|--------|
| `TEMPORAL_GRAPH_ENABLED` | true |
| `TEMPORAL_GRAPH_BACKEND` | kuzu |
| `KUZU_BUFFER_POOL_SIZE` | 256 (MB) |
| `TEMPORAL_DECAY_RATE` | 0.1 |
| `TEMPORAL_MAX_HISTORY` | 1000 |

#### 矛盾检测

| 键 | 默认值 |
|----|--------|
| `CONTRADICTION_DETECTION_ENABLED` | true |
| `CONTRADICTION_AUTO_RESOLVE` | false |
| `CONTRADICTION_DETECTION_STRATEGY` | MIXED |
| `CONTRADICTION_SIMILARITY_THRESHOLD` | 0.8 |
| `CONTRADICTION_MAX_TOKENS` | 1000 |

#### 全文检索 (BM25)

| 键 | 默认值 |
|----|--------|
| `FULLTEXT_ENABLED` | true |
| `FULLTEXT_K1` | 1.5 |
| `FULLTEXT_B` | 0.75 |
| `FULLTEXT_WEIGHT` | 0.3 |

#### 智能抽取器

| 键 | 默认值 |
|----|--------|
| `SMART_EXTRACTOR_MODE` | ADAPTIVE |
| `SMART_EXTRACTOR_COMPLEXITY_THRESHOLD` | 0.6 |
| `SMART_EXTRACTOR_ENABLE_TEMPORAL` | true |
| `SMART_EXTRACTOR_MAX_TOKENS` | 2000 |

#### 预算管理

| 键 | 默认值 |
|----|--------|
| `BUDGET_DAILY_LIMIT` | 0 (无限) |
| `BUDGET_HOURLY_LIMIT` | 0 (无限) |
| `BUDGET_RESERVE` | 0.1 |
| `BUDGET_ALERT_THRESHOLD` | 0.8 |

#### 十一层检索器

| 键 | 默认值 |
|----|--------|
| `ELEVEN_LAYER_RETRIEVER_ENABLED` | true |
| `RETRIEVAL_L1_BLOOM_ENABLED` | true |
| `RETRIEVAL_L2_TEMPORAL_ENABLED` | true |
| `RETRIEVAL_L3_INVERTED_ENABLED` | true |
| `RETRIEVAL_L4_ENTITY_ENABLED` | true |
| `RETRIEVAL_L5_GRAPH_ENABLED` | true |
| `RETRIEVAL_L6_NGRAM_ENABLED` | true |
| `RETRIEVAL_L7_VECTOR_COARSE_ENABLED` | true |
| `RETRIEVAL_L8_VECTOR_FINE_ENABLED` | true |
| `RETRIEVAL_L9_RERANK_ENABLED` | true |
| `RETRIEVAL_L10_CROSS_ENCODER_ENABLED` | true |
| `RETRIEVAL_L11_LLM_ENABLED` | true |

Top-K 配置:

| 键 | 默认值 |
|----|--------|
| `RETRIEVAL_L2_TEMPORAL_TOP_K` | 500 |
| `RETRIEVAL_L3_INVERTED_TOP_K` | 100 |
| `RETRIEVAL_L4_ENTITY_TOP_K` | 50 |
| `RETRIEVAL_L5_GRAPH_TOP_K` | 100 |
| `RETRIEVAL_L6_NGRAM_TOP_K` | 30 |
| `RETRIEVAL_L7_VECTOR_TOP_K` | 200 |
| `RETRIEVAL_L10_CROSS_ENCODER_TOP_K` | 50 |
| `RETRIEVAL_L11_LLM_TOP_K` | 20 |
| `RETRIEVAL_FINE_RANK_THRESHOLD` | 100 |
| `RETRIEVAL_FINAL_TOP_K` | 20 |

L5 图遍历:

| 键 | 默认值 |
|----|--------|
| `RETRIEVAL_L5_GRAPH_MAX_DEPTH` | 2 |
| `RETRIEVAL_L5_GRAPH_MAX_ENTITIES` | 3 |
| `RETRIEVAL_L5_GRAPH_DIRECTION` | both |

L10/L11:

| 键 | 默认值 |
|----|--------|
| `RETRIEVAL_L10_CROSS_ENCODER_MODEL` | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| `RETRIEVAL_L11_LLM_TIMEOUT` | 10.0 |
| `RETRIEVAL_LLM_MAX_TOKENS` | 200 |

权重:

| 键 | 默认值 |
|----|--------|
| `RETRIEVAL_WEIGHT_INVERTED` | 1.0 |
| `RETRIEVAL_WEIGHT_ENTITY` | 1.2 |
| `RETRIEVAL_WEIGHT_GRAPH` | 1.0 |
| `RETRIEVAL_WEIGHT_NGRAM` | 0.8 |
| `RETRIEVAL_WEIGHT_VECTOR` | 1.0 |
| `RETRIEVAL_WEIGHT_TEMPORAL` | 0.5 |

#### 企业级 (Phase 3.5)

| 键 | 默认值 |
|----|--------|
| `QUERY_PLANNER_ENABLED` | true |
| `QUERY_PLANNER_CACHE_SIZE` | 1000 |
| `QUERY_PLANNER_CACHE_TTL` | 300 |
| `COMMUNITY_DETECTION_ENABLED` | false |
| `COMMUNITY_DETECTION_ALGORITHM` | louvain |
| `COMMUNITY_MIN_SIZE` | 2 |

#### 三路并行召回 (Phase 3.6) — 同 TripleRecallConfig

环境变量见第 2.1 节。

#### v4.1 增强

| 键 | 默认值 |
|----|--------|
| `LLM_RELATION_MODE` | llm |
| `LLM_RELATION_COMPLEXITY_THRESHOLD` | 0.5 |
| `LLM_RELATION_ENABLE_TEMPORAL` | true |
| `LLM_RELATION_ENABLE_FACT_DESCRIPTION` | true |
| `LLM_RELATION_MAX_TOKENS` | 4000 |
| `ENTITY_SUMMARY_ENABLED` | true |
| `ENTITY_SUMMARY_MIN_FACTS` | 5 |
| `ENTITY_SUMMARY_MAX_TOKENS` | 2000 |
| `EPISODE_TRACKING_ENABLED` | true |

#### LLM Max Tokens 汇总

| 键 | 默认值 |
|----|--------|
| `LLM_DEFAULT_MAX_TOKENS` | 2000 |
| `LLM_RELATION_MAX_TOKENS` | 4000 |
| `FORESHADOWING_MAX_TOKENS` | 2000 |
| `CONTEXT_EXTRACTION_MAX_TOKENS` | 2000 |
| `ENTITY_SUMMARY_MAX_TOKENS` | 2000 |
| `SMART_EXTRACTOR_MAX_TOKENS` | 2000 |
| `CONTRADICTION_MAX_TOKENS` | 1000 |
| `BUILD_CONTEXT_MAX_TOKENS` | 4000 |
| `RETRIEVAL_LLM_MAX_TOKENS` | 200 |
| `DEDUP_LLM_MAX_TOKENS` | 100 |
| `UNIFIED_ANALYSIS_MAX_TOKENS` | 4000 |

#### v4.2 性能优化

| 键 | 默认值 |
|----|--------|
| `EMBEDDING_REUSE_ENABLED` | true |
| `UNIFIED_ANALYZER_ENABLED` | true |
| `UNIFIED_ANALYSIS_MAX_TOKENS` | 4000 |
| `TURN_API_ENABLED` | true |

---

## 6. character_id / mode / foreshadowing 引用汇总

### 6.1 `character_id` 引用

| 位置 | 用法 |
|------|------|
| `tests/manual_test.py` | `CHAR_ID = "default"`, 所有 API 调用都传 `character_id` |
| `tests/test_phase1_3.py` | `character_id='luna'` — 用于所有 API 测试 |
| `tests/test_full_user_flow.py` | `TEST_CHAR = "sakura"` — 完整流程测试用 |
| `recall/mode.py` | `character_dimension_enabled` 开关控制角色维度 |
| `recall_data/config/api_keys.env` | 无直接 `character_id` 配置 |

> **注意**: `character_id` 在配置层 **不存在默认值**，由调用方传入。CLI 命令中 **不暴露** `character_id` 参数（CLI 使用 `user_id`）。`character_id` 仅在 API/Server 层使用。

### 6.2 `mode` 引用

| 位置 | 说明 |
|------|------|
| `recall/mode.py` | `RecallMode` 枚举: roleplay / general / knowledge_base |
| `recall/config.py` | re-export `RecallMode`, `get_mode_config` |
| `recall_data/config/api_keys.env` | 无 `RECALL_MODE` 条目（通过环境变量设置） |
| `tests/manual_test.py` | 调用 `GET /v1/mode` 检查当前模式 |

### 6.3 `foreshadowing` 引用

| 位置 | 说明 |
|------|------|
| `recall/cli.py` | `recall foreshadowing` 子命令组 (plant/list/resolve) + stats 显示 `foreshadowings.active` |
| `recall/mode.py` | `foreshadowing_enabled` 开关 + `FORESHADOWING_ENABLED` 环境变量覆盖 |
| `recall_data/config/api_keys.env` | 7个伏笔配置项 (`FORESHADOWING_*`) |
| `tests/test_foreshadowing_analyzer.py` | 451行完整单元测试 |
| `tests/test.py` | 快速测试中调用 `engine.plant_foreshadowing()` |
| `tests/test_full_user_flow.py` | 包含伏笔系统测试 (第04项) |
| `tests/test_recall_full.py` | 包含伏笔功能验证 |
| `tests/test_semantic_dedup.py` | 测试 `ForeshadowingTracker` 去重 |
| `tests/test_phase1_3.py` | 无直接伏笔测试 |

---

## 7. 测试文件逐一分析

### 7.1 `tests/__init__.py`
- 内容: `# Recall-ai Tests`（空包标记）

---

### 7.2 `tests/test.py` (341行)
| 项 | 详情 |
|----|------|
| **测试内容** | 测试入口脚本，4种测试模式: quick/full/stress/api |
| **导入** | `recall.engine.RecallEngine`, `recall.server.app`, `recall.embedding.EmbeddingConfig`, `requests`(可选) |
| **Engine 方法覆盖** | `add()`, `get()`, `search()`, `update()`, `delete()`, `plant_foreshadowing()`, `build_context()`, `stats()` |
| **character_id** | ❌ 未使用 |
| **foreshadowing** | ✅ 调用 `engine.plant_foreshadowing("神秘的盒子", related_entities=["Alice"])` |
| **mode** | ❌ 未引用 |
| **测试类型** | 脚本直执行，非 pytest |
| **已知问题** | 设置 `RECALL_EMBEDDING_MODE=none`；api 测试需服务器运行 |

---

### 7.3 `tests/manual_test.py` (340行)
| 项 | 详情 |
|----|------|
| **测试内容** | 人工交互 API 测试: 模式检查、单条添加、批量添加、过滤搜索、全文搜索、删除、统计 |
| **导入** | `requests`, `json`, `time`, `sys` |
| **Engine 方法覆盖** (通过API) | `POST /v1/memories`, `POST /v1/memories/batch`, `POST /v1/memories/search`, `GET /v1/mode`, `POST /v1/context`, `GET /v1/stats`, `GET /v1/memories`, `DELETE /v1/memories/{id}` |
| **character_id** | ✅ `CHAR_ID = "default"`, 所有 API 调用传入 |
| **foreshadowing** | ❌ |
| **mode** | ✅ `GET /v1/mode` 检查模式 |
| **已知问题** | 需要运行中的服务器；需设置 `RECALL_MODE=general` |

---

### 7.4 `tests/test_absolute_rules.py` (300行)
| 项 | 详情 |
|----|------|
| **测试内容** | 绝对规则检测功能: 配置初始化、无LLM回退、Mock LLM检测、运行时规则更新、端到端完整流程 |
| **导入** | `recall.processor.consistency.ConsistencyChecker` |
| **Engine 方法覆盖** | `ConsistencyChecker._check_absolute_rules()`, `checker.check()`, `checker.update_rules()` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 使用自定义函数执行(非pytest)；端到端测试中 `should_warn` 断言被注释掉（仅检查不报错） |

---

### 7.5 `tests/test_comprehensive.py` (423行)
| 项 | 详情 |
|----|------|
| **测试内容** | 综合检查: 模块导入、Engine方法签名、Server路由、配置系统、Embedding系统、新名称别名 |
| **导入** | `recall.engine.RecallEngine`, `recall.server.app`, `recall.embedding.*`, `recall.server.SUPPORTED_CONFIG_KEYS` |
| **Engine 方法覆盖** | 签名检查: `add`, `search`, `get`, `get_all`, `delete`, `update`, `clear`, `build_context`, `stats`, `get_stats` |
| **Server 路由覆盖** | `/health`, `/v1/memories`, `/v1/memories/search`, `/v1/config/reload`, `/v1/config`, `/v1/config/test`, `/v1/foreshadowing`, `/v1/context`, `/v1/stats` |
| **character_id** | ❌ |
| **foreshadowing** | ✅ 检查路由 `/v1/foreshadowing` 存在 |
| **mode** | ❌ |
| **已知问题** | 脚本直执行; 设置 `RECALL_EMBEDDING_MODE=none` |

---

### 7.6 `tests/test_context_system.py` (约160行)
| 项 | 详情 |
|----|------|
| **测试内容** | 六层上下文系统: 持久条件提取、手动添加、上下文构建、统计信息、实体提取、用户隔离 |
| **导入** | `recall.RecallEngine`, `pytest` |
| **Engine 方法覆盖** | `add()`, `get_persistent_contexts()`, `add_persistent_context()`, `build_context()`, `get_stats()` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **测试类型** | pytest (TestContextSystem 类) |
| **已知问题** | `RECALL_EMBEDDING_MODE=none` |

---

### 7.7 `tests/test_delete_cascade.py` (293行)
| 项 | 详情 |
|----|------|
| **测试内容** | 删除级联 + 数据隔离: 多用户数据隔离、用户级删除、删除后搜索验证 |
| **导入** | `urllib.request`, `urllib.error`, `json` |
| **Engine 方法覆盖** (通过API) | `POST /v1/memories`, `GET /v1/memories`, `POST /v1/memories/search`, `DELETE /v1/memories`, `POST /v1/context` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 需要运行中的服务器 |

---

### 7.8 `tests/test_eleven_layer.py` (517行)
| 项 | 详情 |
|----|------|
| **测试内容** | ElevenLayerRetriever 完整测试: RetrievalConfig预设、TemporalContext、L1-L11各层、EightLayerRetriever兼容性 |
| **导入** | `recall.retrieval.config.*`, `recall.retrieval.eleven_layer.*`, `unittest.mock` |
| **Engine 方法覆盖** | `ElevenLayerRetriever.retrieve()`, `get_stats_summary()`, `RetrievalConfig.default/fast/accurate()`, `to_dict()` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **测试类型** | pytest + Fixtures |
| **已知问题** | 全部使用 Mock 依赖，不需要服务器 |

---

### 7.9 `tests/test_embedding_modes.py` (约170行)
| 项 | 详情 |
|----|------|
| **测试内容** | 三种 Embedding 模式: Lite/Cloud/Local + 自动选择 + VectorIndex禁用 |
| **导入** | `recall.embedding.*`, `recall.index.vector_index.VectorIndex` |
| **Engine 方法覆盖** | `EmbeddingConfig.lite()`, `.cloud_openai()`, `.cloud_siliconflow()`, `.local()`, `auto_select_backend()`, `VectorIndex` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | Cloud 实际调用需要 `EMBEDDING_API_KEY`；Local 需要 `sentence-transformers` |

---

### 7.10 `tests/test_foreshadowing_analyzer.py` (451行)
| 项 | 详情 |
|----|------|
| **测试内容** | ForeshadowingAnalyzer 完整测试: 配置类、手动模式、LLM模式(Mock)、边缘情况、缓冲区 |
| **导入** | `recall.processor.foreshadowing.*`, `recall.processor.foreshadowing_analyzer.*`, `unittest.mock` |
| **Engine 方法覆盖** | `ForeshadowingAnalyzer.on_new_turn()`, `.trigger_analysis()`, `.get_buffer_size()`, `.get_turns_until_analysis()`, `ForeshadowingTracker.plant()`, `.get_active()`, `.resolve()` |
| **character_id** | ❌ |
| **foreshadowing** | ✅ 核心测试文件: 手动/LLM/自动植入/手动触发/缓冲区 |
| **mode** | ❌ |
| **测试类型** | pytest |
| **已知问题** | LLM 测试全部使用 Mock |

---

### 7.11 `tests/test_full_user_flow.py` (3441行)
| 项 | 详情 |
|----|------|
| **测试内容** | **最大的测试文件**, 60项测试覆盖全部功能: 核心CRUD、伏笔、持久条件、图谱、11层检索、RRF融合、IVF-HNSW、Kuzu、社区检测、语义去重、绝对规则、API完整覆盖等 |
| **导入** | `requests`, `json`, `time`, `tempfile`, `shutil`, `datetime` |
| **Engine 方法覆盖** (通过API) | 几乎所有 Engine 和 Server 方法 |
| **character_id** | ✅ `TEST_CHAR = "sakura"` |
| **foreshadowing** | ✅ 第04项: 伏笔系统测试 |
| **mode** | ✅ `GET /v1/mode` (隐含) |
| **已知问题** | 需要运行中的服务器; 脚本直接执行（也支持pytest） |

---

### 7.12 `tests/test_growth_control.py` (约35行)
| 项 | 详情 |
|----|------|
| **测试内容** | 持久条件增长控制: 20条记忆后检查条件数量限制 |
| **导入** | `recall.RecallEngine` |
| **Engine 方法覆盖** | `add()`, `get_persistent_contexts()`, `context_tracker.get_stats()` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 使用临时目录 + `RECALL_DATA_ROOT` 环境变量; 脚本直执行 |

---

### 7.13 `tests/test_ivf_hnsw_recall.py` (231行)
| 项 | 详情 |
|----|------|
| **测试内容** | IVF-HNSW 索引创建、搜索功能、HNSW参数效果对比、stats验证、向后兼容 |
| **导入** | `recall.index.vector_index_ivf.VectorIndexIVF`, `faiss`, `numpy` |
| **Engine 方法覆盖** | `VectorIndexIVF()` 构造, `.add()`, `.flush()`, `.search()`, `.get_stats()` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **测试类型** | unittest, `@skipUnless(check_faiss_available())` |
| **已知问题** | 需要 `faiss-cpu` 安装 |

---

### 7.14 `tests/test_kuzu_demo.py` (约170行)
| 项 | 详情 |
|----|------|
| **测试内容** | Kuzu 集成演示: 知识图谱创建、节点/边/关系、BFS遍历、Cypher查询、删除级联 |
| **导入** | `recall.graph.temporal_knowledge_graph.TemporalKnowledgeGraph`, `recall.models.temporal.UnifiedNode` / `NodeType` |
| **Engine 方法覆盖** | `TemporalKnowledgeGraph()`, `.add_node()`, `.add_edge()`, `.get_neighbors()`, `._kuzu_backend.bfs()`, `.query()`, `.remove_node()` |
| **character_id** | ❌ (但创建了虚拟角色 Alice/Bob/Carol 等作为图节点) |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 需要 `kuzu` 安装; 脚本直执行 |

---

### 7.15 `tests/test_phase1_3.py` (305行)
| 项 | 详情 |
|----|------|
| **测试内容** | Phase 1-3 功能 + 100%不遗忘验证: 唯一记忆检索、N-gram原文搜索、统计、语义去重、绝对规则、上下文、实体关系 |
| **导入** | `pytest`, `requests` |
| **Engine 方法覆盖** (通过API) | `POST /v1/memories`, `POST /v1/memories/search`, `POST /v1/context`, `GET /v1/stats`, `GET /health`, `POST /v1/persistent-contexts`, `PUT /v1/core-settings` |
| **character_id** | ✅ `character_id='luna'` |
| **foreshadowing** | ❌ 无直接测试 |
| **mode** | ❌ |
| **已知问题** | 需要运行中的服务器; `@pytest.mark.skipif` 自动检测 |

---

### 7.16 `tests/test_recall_full.py` (1422行)
| 项 | 详情 |
|----|------|
| **测试内容** | 全功能综合测试，分 PART A(离线) 和 PART B(在线): 版本号、核心导入、Embedding配置、Engine CRUD、模块签名 |
| **导入** | `recall.version`, `recall.engine`, `recall.server`, `recall.embedding.*`, `recall.index.*`, `recall.storage.*`, `recall.processor.*`, `recall.retrieval.*`, `recall.graph.*`, `recall.models.*` |
| **Engine 方法覆盖** | 极其全面: 签名验证 + 实际调用。覆盖所有 Engine 方法、所有 Embedding 配置方法、所有存储和索引方法 |
| **character_id** | ✅ `TEST_CHAR = "test_full_char"` |
| **foreshadowing** | ✅ 包含伏笔功能验证 |
| **mode** | ❌ 未直接检查 |
| **已知问题** | PART B 需要运行中的服务器 |

---

### 7.17 `tests/test_retrieval_benchmark.py` (324行)
| 项 | 详情 |
|----|------|
| **测试内容** | 检索器性能基准: p95延迟 < 100ms 验证、配置预设对比 (default/fast/accurate)、时态过滤性能 |
| **导入** | `recall.retrieval.config.*`, `recall.retrieval.eleven_layer.*`, `unittest.mock` |
| **Engine 方法覆盖** | `ElevenLayerRetriever.retrieve()`, 各配置预设 |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 全部使用 Mock; 脚本直执行 |

---

### 7.18 `tests/test_rrf_fusion.py` (231行)
| 项 | 详情 |
|----|------|
| **测试内容** | RRF融合算法: 基本融合、k参数、权重、空结果、单路、分数计算、多路命中加分 + 加权分数融合 |
| **导入** | `recall.retrieval.rrf_fusion.reciprocal_rank_fusion`, `weighted_score_fusion` |
| **Engine 方法覆盖** | `reciprocal_rank_fusion()`, `weighted_score_fusion()` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **测试类型** | unittest |
| **已知问题** | 无 — 纯算法测试，无外部依赖 ✅ |

---

### 7.19 `tests/test_search.py` (约80行)
| 项 | 详情 |
|----|------|
| **测试内容** | 搜索和上下文构建: 语义搜索、source/category/tags 过滤、上下文构建、统计、记忆列表 |
| **导入** | `requests`, `json` |
| **Engine 方法覆盖** (通过API) | `POST /v1/memories/search`, `POST /v1/context`, `GET /v1/stats`, `GET /v1/memories` |
| **character_id** | ❌ (使用 `user_id='news_collector'`) |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 需要运行中的服务器且有已存在数据 |

---

### 7.20 `tests/test_semantic_dedup.py` (296行)
| 项 | 详情 |
|----|------|
| **测试内容** | 语义去重: ContextTracker精确/语义/不同内容去重、Embedding持久化、向后兼容、ForeshadowingTracker去重 |
| **导入** | `recall.processor.context_tracker.*`, `recall.processor.foreshadowing.*` |
| **Engine 方法覆盖** | `ContextTracker.add()`, `.get_active()`, `ForeshadowingTracker.plant()`, `.get_active()` |
| **character_id** | ❌ |
| **foreshadowing** | ✅ 测试 `ForeshadowingTracker` 精确/语义去重 |
| **mode** | ❌ |
| **已知问题** | 使用 MockEmbeddingBackend; 脚本直执行 |

---

### 7.21 `tests/test_stress.py` (317行)
| 项 | 详情 |
|----|------|
| **测试内容** | 压力测试 4阶段: 写入性能(1500条)、持久化验证(重启)、搜索性能、增量添加 |
| **导入** | `recall.engine.RecallEngine`, `psutil` |
| **Engine 方法覆盖** | `add()`, `get_all()`, `search()`, `build_context()` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 在固定目录 `./recall_stress_test_data` 创建数据; 脚本直执行 |

---

### 7.22 `tests/test_v41_features.py` (544行)
| 项 | 详情 |
|----|------|
| **测试内容** | v4.1 新功能: LLMRelationExtractor三模式、关系时态字段、EntitySchemaRegistry、SmartExtractor集成、EpisodeStore、EntitySummarizer、IndexedEntity扩展 |
| **导入** | `recall.graph.llm_relation_extractor.*`, `recall.graph.knowledge_graph.Relation`, `recall.models.entity_schema.*`, `recall.processor.entity_extractor.EntityExtractor` |
| **Engine 方法覆盖** | `LLMRelationExtractor`, `RelationExtractionMode`, `EntitySchemaRegistry`, `Relation` 时态字段 |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **测试类型** | pytest |
| **已知问题** | 设置 `RECALL_EMBEDDING_MODE=none`, `EPISODE_TRACKING_ENABLED=true`, `ENTITY_SUMMARY_ENABLED=true` |

---

### 7.23 `tests/test_v50_bugfixes.py` (423行)
| 项 | 详情 |
|----|------|
| **测试内容** | v5.0 三大BUG修复验证: MetadataIndex CRUD、SearchRequest元数据字段、engine.search()签名、_add_single_fast返回关系、add_batch收集关系、_batch_update_indexes |
| **导入** | `recall.index.metadata_index.MetadataIndex`, `recall.server.SearchRequest`, `recall.engine.RecallEngine`, `inspect` |
| **Engine 方法覆盖** | `MetadataIndex.add/remove/remove_batch/clear/flush/query`, `RecallEngine.search` 签名, `_add_single_fast`, `add_batch`, `_batch_update_indexes` |
| **character_id** | ❌ |
| **foreshadowing** | ❌ |
| **mode** | ❌ |
| **已知问题** | 部分测试通过 `inspect.getsource()` 检查源码字符串（脆弱测试） |

---

## 8. Engine/Server 方法覆盖矩阵

### Engine 核心方法

| 方法 | 覆盖测试文件 |
|------|-------------|
| `add()` | test.py, test_context_system, test_growth_control, test_stress, test_recall_full, test_full_user_flow |
| `search()` | test.py, test_stress, test_recall_full, test_full_user_flow, test_v50_bugfixes |
| `get()` | test.py, test_recall_full, test_full_user_flow |
| `get_all()` | test_stress, test_recall_full |
| `update()` | test.py, test_recall_full |
| `delete()` | test.py, test_recall_full, test_full_user_flow |
| `clear()` | test_recall_full |
| `build_context()` | test.py, test_context_system, test_stress, test_recall_full, test_full_user_flow |
| `stats()` / `get_stats()` | test.py, test_context_system, test_recall_full, test_full_user_flow |
| `add_batch()` | test_v50_bugfixes, test_full_user_flow |
| `plant_foreshadowing()` | test.py, test_recall_full, test_full_user_flow |
| `get_active_foreshadowings()` | test_recall_full, test_full_user_flow |
| `resolve_foreshadowing()` | test_recall_full, test_full_user_flow |
| `consolidate()` | (仅 CLI 定义，无专门测试) |
| `reset()` | (仅 CLI 定义，无专门测试) |
| `get_persistent_contexts()` | test_context_system, test_growth_control |
| `add_persistent_context()` | test_context_system |

### Server API 路由

| 路由 | 覆盖测试文件 |
|------|-------------|
| `GET /health` | test.py, test_phase1_3, test_delete_cascade, test_full_user_flow |
| `POST /v1/memories` | test.py, manual_test, test_phase1_3, test_delete_cascade, test_full_user_flow |
| `POST /v1/memories/batch` | manual_test, test_full_user_flow |
| `POST /v1/memories/search` | test.py, manual_test, test_phase1_3, test_search, test_delete_cascade, test_full_user_flow |
| `GET /v1/memories` | manual_test, test_search, test_delete_cascade |
| `GET /v1/memories/{id}` | test.py |
| `DELETE /v1/memories/{id}` | test.py, manual_test |
| `DELETE /v1/memories` | test_delete_cascade |
| `POST /v1/context` | manual_test, test_phase1_3, test_search, test_delete_cascade, test_full_user_flow |
| `GET /v1/stats` | test.py, test_phase1_3, test_search, test_full_user_flow |
| `GET /v1/mode` | manual_test |
| `/v1/config` | test_comprehensive (路由检查) |
| `/v1/config/reload` | test_comprehensive (路由检查) |
| `/v1/config/test` | test_comprehensive (路由检查) |
| `/v1/foreshadowing` | test_comprehensive (路由检查), test_full_user_flow |
| `/v1/persistent-contexts` | test_phase1_3 |
| `/v1/core-settings` | test_phase1_3 |

---

## 9. 总结与建议

### 测试覆盖评估

| 维度 | 状态 |
|------|------|
| Engine CRUD | ✅ 充分覆盖 |
| 伏笔系统 | ✅ 充分覆盖 (4个文件) |
| 上下文系统 | ✅ 覆盖 (2个文件) |
| 11层检索器 | ✅ 单元+基准 (2个文件) |
| RRF 融合 | ✅ 充分覆盖 |
| IVF-HNSW | ✅ 覆盖 (需要faiss) |
| Kuzu 图数据库 | ✅ 演示级覆盖 |
| 语义去重 | ✅ 覆盖 |
| 绝对规则 | ✅ 覆盖 |
| v4.1 新功能 | ✅ 覆盖 |
| v5.0 Bug修复 | ✅ 覆盖 |
| Embedding模式 | ✅ 覆盖 |
| 压力/持久化 | ✅ 覆盖 |
| `consolidate()` | ⚠️ 无测试 |
| `reset()` | ⚠️ 无测试 |
| `character_id` 隔离 | ⚠️ 仅API测试中传入，无专门隔离测试 |
| `RecallMode` 切换 | ⚠️ 仅manual_test检查，无模式切换测试 |
| MCP Server | ⚠️ 无测试 |

### 测试类型统计

| 类型 | 文件数 |
|------|--------|
| pytest 测试 | 5 (test_context_system, test_eleven_layer, test_foreshadowing_analyzer, test_v41_features, test_ivf_hnsw_recall, test_rrf_fusion) |
| 脚本直执行 | 11 (其余文件) |
| 需要服务器 | 6 (manual_test, test_delete_cascade, test_phase1_3, test_search, test_full_user_flow, test.py --api) |
| 纯离线 | 10 |

### 配置统计

| 类别 | 配置项数 |
|------|----------|
| api_keys.env 总配置项 | ~100+ |
| 伏笔相关 | 7 |
| 持久条件 | 7 |
| 检索器层配置 | 22 |
| LLM Max Tokens | 11 |
| 去重配置 | 7 |
| 知识图谱 | 5 |
| 三路召回 | 12 |
| 模式相关 | 6 (RECALL_MODE + 5个子开关) |
