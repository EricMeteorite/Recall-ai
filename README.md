# Recall

**通用 AI 知识记忆系统**

```
┌─────────────────────────────────────────────────────────────┐
│                      设计原则                               │
├─────────────────────────────────────────────────────────────┤
│  零依赖优先 - 无需外部数据库，开箱即用                       │
│  成本可控 - LLM 可选，本地优先                              │
│  场景通用 - RP / 代码 / 企业 / Agent 全覆盖                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# Windows
.\manage.ps1

# Linux / Mac  
./manage.sh
```

选择菜单 `[1] Install` 安装，`[2] Start` 启动。

服务地址: `http://localhost:18888`  
API 文档: `http://localhost:18888/docs`

---

## 配置

配置文件位置: `recall_data/config/api_keys.env`

```bash
# Embedding（必填，支持 OpenAI 兼容接口）
EMBEDDING_API_KEY=your-key
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small

# LLM（可选，用于伏笔分析、矛盾检测等高级功能）
LLM_API_KEY=your-key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

支持的 Embedding 服务: OpenAI / SiliconFlow / Ollama / 任何 OpenAI 兼容 API

---

## 核心功能

### REST API（推荐）

启动服务后通过 HTTP 调用：

```bash
# 添加记忆
curl -X POST http://localhost:18888/api/v1/memories \
  -H "Content-Type: application/json" \
  -d '{"content": "Alice住在北京，是一名程序员"}'

# 搜索记忆
curl -X POST http://localhost:18888/api/v1/memories/search \
  -d '{"query": "Alice的职业是什么？"}'

# 构建上下文
curl -X POST http://localhost:18888/api/v1/context/build \
  -d '{"query": "介绍一下Alice"}'
```

### Python SDK

```bash
pip install recall-ai
```

```python
from recall import RecallEngine

engine = RecallEngine()

# 添加记忆
engine.add("Alice住在北京，是一名程序员")

# 搜索记忆（语义搜索 + 全文检索）
results = engine.search("Alice的职业是什么？")

# 构建上下文（自动整合记忆、伏笔、持久条件）
context = engine.build_context("介绍一下Alice")
```

### 伏笔系统

追踪未解决的线索、承诺、TODO，在相关时机自动提醒。

```python
# 埋下伏笔
engine.plant_foreshadowing(
    content="Alice说下周要去上海出差",
    keywords=["Alice", "上海", "出差"]
)

# 获取活跃伏笔
foreshadowings = engine.get_active_foreshadowings()

# 解决伏笔
engine.resolve_foreshadowing(foreshadowing_id, "Alice已完成上海出差")
```

### 持久条件

贯穿对话的背景信息：用户身份、环境、目标、偏好等。

```python
# 添加持久条件
engine.add_persistent_context(
    content="用户是一名资深Python开发者",
    context_type="user_identity"
)

# 获取持久条件（自动包含在 build_context 结果中）
contexts = engine.get_persistent_contexts()
```

### 核心设定 (L0)

角色、世界观、规则等永久设定，100% 不遗忘。

```python
# 添加核心设定
engine.add_core_setting("Alice的人设", "性格开朗，喜欢编程和旅行")

# 获取核心设定（自动包含在 build_context 结果中）
settings = engine.get_core_settings()
```

### 一致性检查

自动检测记忆中的矛盾。

```python
# 检测矛盾
contradictions = engine.detect_contradictions("Alice住在上海")
```

### 多租户隔离

用户/角色级别数据隔离。

```python
engine = RecallEngine(user_id="user1", character_id="alice")
```

---

## REST API

80+ 个 API 端点，主要类别：

| 类别 | 端点示例 | 说明 |
|------|---------|------|
| 记忆 | `POST /api/v1/memories` | 添加/搜索/删除记忆 |
| 伏笔 | `POST /api/v1/foreshadowings` | 伏笔管理 |
| 条件 | `POST /api/v1/persistent-contexts` | 持久条件管理 |
| 设定 | `POST /api/v1/core-settings` | 核心设定管理 |
| 上下文 | `POST /api/v1/context/build` | 构建完整上下文 |
| 实体 | `GET /api/v1/entities` | 实体管理 |

完整 API 文档: `http://localhost:18888/docs`

---

## SillyTavern 插件

通过管理脚本安装：

```bash
.\manage.ps1  # 选择 [6] SillyTavern Plugin Management
```

---

## 项目结构

```
recall/
├── engine.py          # 核心引擎
├── server.py          # REST API 服务
├── embedding/         # Embedding 后端（本地/API）
├── graph/             # 知识图谱
├── index/             # 索引系统（向量/倒排/N-gram）
├── processor/         # 处理器（实体抽取/伏笔分析/摘要）
├── retrieval/         # 检索系统（多层检索/上下文构建）
├── storage/           # 存储层（L0核心/L1整合/L2工作/多租户）
└── utils/             # 工具（LLM客户端/性能监控）
```

---

## 许可证

[MIT License](LICENSE)
