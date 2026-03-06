# Recall-AI 配置一致性审计报告

**审计日期:** 2026-02-25  
**项目版本:** v7.0.0 (pyproject.toml & version.py)  
**审计范围:** 全部配置相关文件

---

## 一、总览

| 严重级别 | 数量 | 说明 |
|---------|------|------|
| 🔴 Critical | **8** | 可导致运行时错误或行为不一致 |
| 🟡 Warning | **10** | 可能引起混乱或未来维护问题 |
| 🔵 Info | **6** | 小问题或建议改进项 |

---

## 二、Critical 级别问题

### C1: `RECALL_MODE` 默认值不一致（v7.0 关键问题）

`mode.py` 已升级为 v7.0 统一模式（UNIVERSAL），但多处仍使用旧的 `roleplay` 默认值：

| 文件 | 默认值 | 应为 |
|------|--------|------|
| `recall/mode.py` | `UNIVERSAL` (忽略 RECALL_MODE) | ✅ 正确 |
| `recall/config.py` RecallConfig.recall_mode | `'roleplay'` | ❌ 应为 `'universal'` |
| `recall/server.py` SUPPORTED_CONFIG_KEYS 注释 | `roleplay/general/knowledge_base` | ❌ 应提到 `universal` |
| `recall/server.py` 默认配置模板 | `RECALL_MODE=universal` | ✅ 正确 |
| `start.ps1` 默认配置模板 | `RECALL_MODE=roleplay` | ❌ 应为 `universal` |
| `start.sh` 默认配置模板 | `RECALL_MODE=roleplay` | ❌ 应为 `universal` |
| `manage.ps1` 默认配置模板 | `RECALL_MODE=roleplay` | ❌ 应为 `universal` |
| `manage.sh` 默认配置模板 | `RECALL_MODE=roleplay` | ❌ 应为 `universal` |
| `recall_data/config/api_keys.env` | 无 RECALL_MODE 行 | 🟡 缺失（由 server 默认值补充） |

**影响:** 当用户通过 start.ps1/start.sh 启动时，会设置 `RECALL_MODE=roleplay`，虽然 `mode.py` 忽略此值始终返回 UNIVERSAL，但 `RecallConfig.from_env()` 会读取到 `'roleplay'`，导致下游代码不一致。

---

### C2: `RecallConfig` 多个默认值与 `api_keys.env` 不匹配

| 环境变量 | config.py 默认值 | api_keys.env 值 | 差异说明 |
|----------|------------------|------------------|----------|
| `FORESHADOWING_MAX_RETURN` | `5` | `10` | config.py=5, env=10 |
| `CONTEXT_MAX_PER_TYPE` | `30` | `10` | config.py=30, env=10 |
| `CONTEXT_DECAY_DAYS` | `7` | `14` | config.py=7, env=14 |
| `CONTEXT_DECAY_RATE` | `0.1` | `0.05` | config.py=0.1, env=0.05 |
| `CONTEXT_MIN_CONFIDENCE` | `0.3` | `0.1` | config.py=0.3, env=0.1 |
| `DEDUP_HIGH_THRESHOLD` | `0.92` | `0.85` | config.py=0.92, env=0.85 |
| `DEDUP_LOW_THRESHOLD` | `0.75` | `0.70` | config.py=0.75, env=0.70 |
| `SMART_EXTRACTOR_MODE` | `'RULES'` | `ADAPTIVE` | config.py=RULES, env=ADAPTIVE |
| `CONTRADICTION_MAX_TOKENS` | `2000` | `1000` | config.py=2000, env=1000 |
| `BUILD_CONTEXT_MAX_TOKENS` | `2000` | `4000` | config.py=2000, env=4000 |
| `RETRIEVAL_LLM_MAX_TOKENS` | `2000` | `200` | config.py=2000, env=200 |
| `DEDUP_LLM_MAX_TOKENS` | `2000` | `100` | config.py=2000, env=100 |
| `UNIFIED_ANALYSIS_MAX_TOKENS` | `2000` | `4000` | config.py=2000, env=4000 |
| `EMBEDDING_MODEL` | `'text-embedding-3-small'` | `BAAI/bge-m3` | 默认值不同(env已填写实际值) |

**影响:** 当 `api_keys.env` 中的值为空或被删除时，`RecallConfig.from_env()` 将回退到 config.py 的默认值，这些默认值与文档化的 env 文件中的"推荐值"不一致。用户可能得到意外行为。

---

### C3: 版本号不一致

| 文件 | 版本号 | 说明 |
|------|--------|------|
| `recall/version.py` | `7.0.0` | ✅ 当前版本 |
| `pyproject.toml` | `7.0.0` | ✅ 一致 |
| `install.ps1` 显示 | `v4.2.0` | ❌ 过时 |
| `install.sh` 显示 | `v4.2.0` | ❌ 过时 |
| `start.ps1` 显示 | `v4.2.0` | ❌ 过时 |
| `start.sh` 显示 | `v4.2.0` | ❌ 过时 |
| `manage.ps1` 显示 | `v1.0.0` | ❌ 过时 |
| `manage.sh` 显示 | `v1.0.0` | ❌ 过时 |
| `recall/init.py` config version | `'4.0'` | ❌ 过时 |

---

### C4: `TEMPORAL_GRAPH_BACKEND` 默认值不一致

| 文件 | 默认值 |
|------|--------|
| `recall/config.py` RecallConfig | `'file'` |
| `recall/engine.py` os.environ.get | `'file'` |
| `recall_data/config/api_keys.env` (实际) | `kuzu` |
| start.ps1/start.sh/manage.ps1/manage.sh 默认模板 | `file` |
| server.py 默认模板 | `file` |

**影响:** 实际的 api_keys.env 配置了 `kuzu`，但所有默认模板和代码默认都用 `file`。如果用户重置配置或新安装，将从 kuzu 退回到 file 后端，可能导致数据不可读。

---

### C5: `RecallConfig` 缺少多个 env 文件中存在的配置项

以下环境变量在 `api_keys.env` 和 `SUPPORTED_CONFIG_KEYS` 中存在，但 **不在 `RecallConfig` dataclass 中**：

| 缺失配置项 | 使用位置 |
|------------|----------|
| `EMBEDDING_RATE_LIMIT` | server.py |
| `EMBEDDING_RATE_WINDOW` | server.py |
| `CONTRADICTION_DETECTION_ENABLED` | engine.py |
| `CONTRADICTION_AUTO_RESOLVE` | engine.py |
| `CONTRADICTION_DETECTION_STRATEGY` | engine.py |
| `CONTRADICTION_SIMILARITY_THRESHOLD` | engine.py |
| `FULLTEXT_ENABLED` | engine.py |
| `FULLTEXT_K1` | engine.py |
| `FULLTEXT_B` | engine.py |
| `FULLTEXT_WEIGHT` | engine.py |
| `BUDGET_DAILY_LIMIT` | engine.py |
| `BUDGET_HOURLY_LIMIT` | engine.py |
| `BUDGET_RESERVE` | engine.py |
| `BUDGET_ALERT_THRESHOLD` | engine.py |
| `DEDUP_JACCARD_THRESHOLD` | engine.py |
| `DEDUP_SEMANTIC_THRESHOLD` | engine.py |
| `DEDUP_SEMANTIC_LOW_THRESHOLD` | engine.py |
| `DEDUP_LLM_ENABLED` | engine.py |
| `ELEVEN_LAYER_RETRIEVER_ENABLED` | engine.py |
| 所有 `RETRIEVAL_L*` 变量 | retrieval/config.py |
| `QUERY_PLANNER_ENABLED` | engine.py |
| `QUERY_PLANNER_CACHE_SIZE` | engine.py |
| `QUERY_PLANNER_CACHE_TTL` | engine.py |
| `ENTITY_SUMMARY_ENABLED` | engine.py |
| `ENTITY_SUMMARY_MIN_FACTS` | engine.py |

**影响:** `RecallConfig.from_env()` 的"集中管理"承诺未兑现——大量配置项仍散落在 `engine.py` 等文件的 `os.environ.get()` 调用中。

---

### C6: engine.py 使用的环境变量不在 `SUPPORTED_CONFIG_KEYS` 中

以下 `os.environ.get()` 调用的环境变量未注册到 `SUPPORTED_CONFIG_KEYS`，因此不会从 `api_keys.env` 加载：

| 环境变量 | engine.py 行 | 默认值 |
|----------|-------------|--------|
| `PARALLEL_RETRIEVER_WORKERS` | L1052 | `'4'` |
| `PARALLEL_RETRIEVER_TIMEOUT` | L1053 | `'5.0'` |
| `IVF_AUTO_SWITCH_ENABLED` | L1451 | `'true'` |

---

### C7: server.py 使用的环境变量不在 `SUPPORTED_CONFIG_KEYS` / `RecallConfig` 中

| 环境变量 | server.py 行 | 默认值 |
|----------|-------------|--------|
| `RECALL_LOG_LEVEL` | L1446 | `'INFO'` |
| `RECALL_LOG_JSON` | L1447 | `''` |
| `RECALL_LOG_FILE` | L1448 | `''` |
| `RECALL_PIPELINE_MAX_SIZE` | L1463 | `'10000'` |
| `RECALL_PIPELINE_RATE_LIMIT` | L1464 | `'0'` |
| `RECALL_PIPELINE_WORKERS` | L1465 | `'2'` |
| `RECALL_CORS_ORIGINS` | L1503 | `'*'` |
| `RECALL_CORS_METHODS` | L1504 | `'GET,POST,PUT,DELETE,OPTIONS'` |
| `RECALL_DATA_ROOT` | L286 | `'./recall_data'` |

这些变量设计上不应放在 api_keys.env 中（属于部署级配置），但也未在 RecallConfig 中记录。

---

### C8: `llm_relation_mode` 在 RecallConfig 中默认 `'llm'`，engine.py 也默认 `'llm'`，但 config.py 注释说 `rules / adaptive / llm`

虽然代码默认值一致（都是 `'llm'`），但 api_keys.env 和所有模板中也设置为 `llm`，当用户认为 "rules" 是默认值时会引起困惑。文档说 "rules（纯规则，默认）"但实际默认是 `llm`。

---

## 三、Warning 级别问题

### W1: start.sh `supported_keys` 缺少某些键

`start.sh` 的 `supported_keys` 是空格分隔字符串，与 `start.ps1` 的数组版本对比：
- start.ps1 的 `$supportedKeys` 有完整的键列表
- start.sh 的 `supported_keys` 缺少一些较小的差异需要逐一核对（两者配置量都是 ~120 项，可能在最新同步后一致）

### W2: `CONTEXT_MAX_PER_TYPE` 注释混乱

- api_keys.env: `CONTEXT_MAX_PER_TYPE=10`（注释说"每类型最大条件数"）
- config.py: `context_max_per_type: int = 30`
- 用户不知道真正的推荐值是 10 还是 30。

### W3: 安装脚本和服务脚本中的旧模式引用

以下文件的默认配置模板中仍使用 v5.0 的模式说明：
- `start.ps1` / `start.sh` / `manage.ps1` / `manage.sh` 都在注释中写：
  ```
  # 模式: roleplay（角色扮演，默认）/ general（通用）/ knowledge_base（知识库）
  ```
  应更新为 v7.0 的说明：`universal（统一模式，默认）`

### W4: `FORESHADOWING_MAX_RETURN` config.py 默认 5，env 文件默认 10

server.py 模板和所有 start/manage 脚本模板中都设为 `10`，但 config.py 的 dataclass 默认值是 `5`。如果 env 中此行被注释或删除，行为会变化。

### W5: init.py 保存的 config version 是 `'4.0'`

`recall/init.py` 的 `run_init_wizard()` 保存：
```python
config = {
    'version': '4.0',
    ...
}
```
应为 `'7.0'`。

### W6: `_safe_print` 函数在多个文件中重复定义

以下文件都有完全相同的 `_safe_print` 函数：
- `recall/config.py`
- `recall/init.py`
- `recall/embedding/factory.py`
- （可能还有其他）

应提取到 `recall/utils/` 中共用。

### W7: `RP_RELATION_TYPES` 和 `RP_CONTEXT_TYPES` 类型不一致

- `recall/config.py` RecallConfig: `rp_relation_types: str = ''` / `rp_context_types: str = ''` (字符串)
- `recall/mode.py` ModeConfig: `rp_relation_types: bool` / `rp_context_types: bool` (布尔)
- api_keys.env: `RP_RELATION_TYPES=true` / `RP_CONTEXT_TYPES=true`

RecallConfig 从 env 读取的是字符串 `'true'`，但 ModeConfig 解析为 bool `True`。

### W8: `EMBEDDING_DIMENSION` 默认值差异

| 文件 | 默认值 |
|------|--------|
| config.py RecallConfig | `0` (自动查表) |
| api_keys.env (实际) | `1024` |
| 所有默认模板 | `1024` |
| embedding/factory.py | `None` (未指定维度则自动) |

实际环境和默认模板都写 `1024`，但代码默认是 `0`/`None`。

### W9: `MCP_TRANSPORT` 和 `MCP_PORT` 在 RecallConfig 中但不在 SUPPORTED_CONFIG_KEYS 中

config.py 定义了：
```python
mcp_transport: str = 'stdio'
mcp_port: int = 8765
```
但 server.py 的 `SUPPORTED_CONFIG_KEYS` 里并没有 `MCP_TRANSPORT` 和 `MCP_PORT`。

### W10: `ADMIN_KEY` 在 RecallConfig 中但不在 SUPPORTED_CONFIG_KEYS 和 api_keys.env 中

config.py 定义了 `admin_key: str = ''`，server.py 在 L2239 通过 `os.environ.get('ADMIN_KEY', '')` 读取，但 `ADMIN_KEY` 不在 `SUPPORTED_CONFIG_KEYS` 中，也不在 api_keys.env 中。用户无法通过配置文件设置管理密钥。

---

## 四、Info 级别问题

### I1: pyproject.toml 中 keywords 仍包含 `"roleplay"`

```toml
keywords = ["ai", "memory", "recall", "llm", "roleplay", "sillytavern"]
```
v7.0 已不再以 roleplay 为核心定位，可考虑更新。

### I2: 多处 `RECALL_EMBEDDING_MODE` 值域不一致

| 文件 | 说明的可选值 |
|------|-------------|
| config.py | `auto / lite / local / cloud / none` |
| api_keys.env | `auto / local / api` |
| embedding/factory.py | `auto / api / local / none` |
| start.ps1 检测逻辑 | `none / api / api_required / local` |

`cloud` vs `api` vs `none` vs `lite` — 术语不统一。

### I3: `OPENAI_API_KEY` 兼容回退

- `recall/config.py` L305: `d.llm_api_key = g('LLM_API_KEY', '') or g('OPENAI_API_KEY', d.llm_api_key)`
- `recall/engine.py` L253: `api_key = ... or os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')`
- `recall/init.py` L112: `api_key = os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')`

三处都支持 `OPENAI_API_KEY` 回退，行为一致。但未在文档或 api_keys.env 中说明。

### I4: `IVF_AUTO_SWITCH_THRESHOLD` 在 RecallConfig 中但不在 env 文件模板中

config.py 默认 `50000`，engine.py 默认 `'50000'`，一致。但用户无法通过 api_keys.env 配置此项。

### I5: tools 检查脚本目标版本过时

- `tools/verify_config.py`: 标题写 "Recall v4.2 完整版"
- `tools/final_config_check.py`: 标题写 "配置同步最终验证报告 (v4.2)"

两个工具都还检查 v4.2 的配置，未更新到 v7.0。

### I6: `RECALL_HOST` / `RECALL_PORT` 环境变量

start.ps1 和 start.sh 都支持 `RECALL_HOST` 和 `RECALL_PORT` 环境变量覆盖默认主机/端口。二者行为一致（默认 `0.0.0.0:18888`）。

---

## 五、完整环境变量交叉对照表

> 仅列出存在差异的关键变量。所有文件一致的变量已省略。

| 环境变量 | config.py 默认 | api_keys.env | server.py 模板 | start.ps1 模板 | engine.py 默认 | 状态 |
|----------|---------------|-------------|---------------|---------------|---------------|------|
| `RECALL_MODE` | `'roleplay'` | ❌缺失 | `universal` | `roleplay` | - | 🔴 不一致 |
| `FORESHADOWING_MAX_RETURN` | `5` | `10` | `10` | `10` | - | 🔴 config.py 偏低 |
| `CONTEXT_MAX_PER_TYPE` | `30` | `10` | `10` | `10` | - | 🔴 config.py 偏高 |
| `CONTEXT_DECAY_DAYS` | `7` | `14` | `14` | `14` | - | 🔴 config.py 偏低 |
| `CONTEXT_DECAY_RATE` | `0.1` | `0.05` | `0.05` | `0.05` | - | 🔴 config.py 偏高 |
| `CONTEXT_MIN_CONFIDENCE` | `0.3` | `0.1` | `0.1` | `0.1` | - | 🔴 config.py 偏高 |
| `DEDUP_HIGH_THRESHOLD` | `0.92` | `0.85` | `0.85` | `0.85` | - | 🔴 config.py 偏高 |
| `DEDUP_LOW_THRESHOLD` | `0.75` | `0.70` | `0.70` | `0.70` | - | 🔴 config.py 偏高 |
| `SMART_EXTRACTOR_MODE` | `'RULES'` | `ADAPTIVE` | `ADAPTIVE` | `ADAPTIVE` | `'RULES'` | 🔴 code vs env |
| `CONTRADICTION_MAX_TOKENS` | `2000` | `1000` | `1000` | `1000` | - | 🔴 config.py 偏高 |
| `BUILD_CONTEXT_MAX_TOKENS` | `2000` | `4000` | `4000` | `4000` | - | 🔴 config.py 偏低 |
| `RETRIEVAL_LLM_MAX_TOKENS` | `2000` | `200` | `200` | `200` | - | 🔴 config.py 偏高 |
| `DEDUP_LLM_MAX_TOKENS` | `2000` | `100` | `100` | `100` | - | 🔴 config.py 偏高 |
| `UNIFIED_ANALYSIS_MAX_TOKENS` | `2000` | `4000` | `4000` | `4000` | - | 🔴 config.py 偏低 |
| `TEMPORAL_GRAPH_BACKEND` | `'file'` | `kuzu` | `file` | `file` | `'file'` | ⚠️ 实际 env 不同 |
| `EMBEDDING_DIMENSION` | `0` | `1024` | `1024` | `1024` | - | ℹ️ 有效（0=自动） |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | `BAAI/bge-m3` | 空 | 空 | - | ℹ️ env 已自定义 |

---

## 六、文件完整性对比

### 6.1 install.ps1 vs install.sh

| 项目 | install.ps1 | install.sh | 一致 |
|------|------------|-----------|------|
| 版本号显示 | v4.2.0 | v4.2.0 | ✅ |
| 安装模式 | lite/cloud/local/enterprise | 同 | ✅ |
| 旧名称兼容 | lightweight/hybrid/full | 同 | ✅ |
| CPU/GPU 选择 | 有 | 有 | ✅ |
| 创建的目录 | data,logs,cache,models,config,temp | 同 | ✅ |
| spaCy 模型安装 | 有备用方案 | 有备用方案 | ✅ |
| 保存安装模式 | install_mode 文件 | 同 | ✅ |
| 保存 CPU 选择 | use_cpu 文件 | 同 | ✅ |

### 6.2 start.ps1 vs start.sh

| 项目 | start.ps1 | start.sh | 一致 |
|------|----------|---------|------|
| 默认端口 | 18888 | 18888 | ✅ |
| 默认主机 | 0.0.0.0 | 0.0.0.0 | ✅ |
| 配置加载 | `Import-ApiKeys` | `load_api_keys` | ✅ |
| 支持的 keys 列表 | ~120 项 | ~120 项 | ✅ |
| 默认配置模板 | 完整 | 完整 | ✅ |
| RECALL_MODE 默认 | `roleplay` | `roleplay` | ❌ 应为 universal |
| Daemon 模式 | 有 | 有 | ✅ |
| 健康检查 | /health | /health | ✅ |

### 6.3 manage.ps1 vs manage.sh

| 项目 | manage.ps1 | manage.sh | 一致 |
|------|-----------|----------|------|
| 菜单项 | 8个 + 退出 | 8个 + 退出 | ✅ |
| ST 插件管理 | 有 | 有 | ✅ |
| 配置管理子菜单 | 有 | 有 | ✅ |
| 默认端口 | 18888 | 18888 | ✅ |
| Embedding 模式检测 | 有 | 有 | ✅ |
| 默认配置模板 | 有(内嵌) | 有(heredoc) | ✅ |
| RECALL_MODE 默认 | `roleplay` | `roleplay` | ❌ 应为 universal |

---

## 七、工具检查脚本分析

### 7.1 tools/verify_config.py 检查项

1. server.py `SUPPORTED_CONFIG_KEYS` 与 start.ps1/start.sh 的 key 列表对比
2. 默认配置模板一致性（server.py vs start.ps1 vs manage.ps1 vs manage.sh）
3. 模板覆盖度（模板中的 key 是否都在 SUPPORTED_CONFIG_KEYS 中）
4. factory.py 环境变量与 server.py 一致性
5. 热更新支持情况
6. Phase 2/3.5/4.1 功能集成状态

**缺失:** 未检查 RecallConfig 与散落 os.environ.get 的一致性。未检查 v7.0 模式更新。

### 7.2 tools/final_config_check.py 检查项

1. 配置模板文件中 8 个目标配置的值
2. Python os.environ.get 默认值
3. v4.2 性能配置同步
4. Windows/Linux 脚本一致性
5. 热更新机制

**缺失:** 未检查 v5.0+ / v7.0 配置项。TARGET_CONFIGS 仅有 8 项。

---

## 八、修复建议优先级

### 立即修复 (Critical)

1. **`config.py` RecallConfig 默认值对齐**: 将 `recall_mode` 改为 `'universal'`，其他数值默认值全部对齐 api_keys.env 模板。
2. **脚本模板 RECALL_MODE**: 将 start.ps1/start.sh/manage.ps1/manage.sh 的默认模板中 `RECALL_MODE=roleplay` 改为 `RECALL_MODE=universal`。
3. **版本号统一**: install.ps1/install.sh/start.ps1/start.sh 的显示版本改为 v7.0.0。
4. **RecallConfig 补全**: 将所有 SUPPORTED_CONFIG_KEYS 中的变量都加入 RecallConfig，engine.py 引用 RecallConfig 而非直接 os.environ.get。
5. **注册缺失的 env 变量**: `PARALLEL_RETRIEVER_WORKERS`、`PARALLEL_RETRIEVER_TIMEOUT`、`IVF_AUTO_SWITCH_ENABLED` 加入 SUPPORTED_CONFIG_KEYS。

### 后续修复 (Warning)

6. 统一 embedding mode 术语（`api` vs `cloud` vs `none` vs `lite`）
7. `RP_RELATION_TYPES`/`RP_CONTEXT_TYPES` 类型不匹配
8. 提取公共 `_safe_print` 到 utils
9. init.py config version 改为 7.0
10. 更新工具脚本到 v7.0

---

*审计完成。建议按优先级逐步修复，每次修复后运行 `tools/verify_config.py` 回归验证。*
