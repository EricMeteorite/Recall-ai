# Recall MCP Server 开发计划

## 概述

将 Recall 改造为 MCP (Model Context Protocol) Server，实现"一次开发，到处使用"的目标。

### 为什么需要 MCP？

**当前问题：**
- 每个平台需要单独开发插件（SillyTavern 插件、VS Code 扩展...）
- 重复劳动，维护成本高
- 新平台接入需要额外开发

**MCP 方案优势：**
- 一个 MCP Server 适配所有支持 MCP 的 AI 应用
- Claude Desktop、VS Code、Cursor、Cherry Studio 等直接可用
- 标准协议，无需为每个平台单独开发

---

## 架构设计

### 当前架构

```
┌─────────────────┐     HTTP API      ┌─────────────────┐
│  SillyTavern    │ ◄───────────────► │                 │
│  Plugin         │                   │                 │
└─────────────────┘                   │   Recall API    │
                                      │   Server        │
┌─────────────────┐     HTTP API      │   (FastAPI)     │
│  其他客户端      │ ◄───────────────► │                 │
│  (需单独开发)    │                   │   :18888        │
└─────────────────┘                   └─────────────────┘
```

### MCP 架构

```
┌─────────────────┐                   ┌─────────────────┐
│  Claude Desktop │ ◄──── MCP ──────► │                 │
└─────────────────┘                   │                 │
                                      │   Recall MCP    │
┌─────────────────┐                   │   Server        │
│  VS Code        │ ◄──── MCP ──────► │                 │
│  Copilot        │                   │   (stdio/sse)   │
└─────────────────┘                   │                 │
                                      │                 │
┌─────────────────┐                   │                 │
│  Cursor / 其他  │ ◄──── MCP ──────► │                 │
└─────────────────┘                   └────────┬────────┘
                                               │
                                               │ 调用
                                               ▼
                                      ┌─────────────────┐
                                      │  Recall Engine  │
                                      │  (核心逻辑)      │
                                      └─────────────────┘
```

### 双模式运行

保留 HTTP API Server 以兼容现有客户端（如 SillyTavern 插件）：

```
┌─────────────────────────────────────────────────────────────┐
│                      Recall                                  │
│  ┌─────────────────┐           ┌─────────────────┐          │
│  │  MCP Server     │           │  HTTP API Server│          │
│  │  (recall.mcp)   │           │  (recall.server)│          │
│  │                 │           │                 │          │
│  │  stdio / sse    │           │  :18888         │          │
│  └────────┬────────┘           └────────┬────────┘          │
│           │                             │                    │
│           └──────────┬──────────────────┘                    │
│                      ▼                                       │
│           ┌─────────────────────┐                            │
│           │    Recall Engine    │                            │
│           │    (共享核心逻辑)    │                            │
│           └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

---

## MCP Tools 设计

### 核心 Tools

| Tool 名称 | 功能 | 参数 |
|-----------|------|------|
| `recall_add_memory` | 添加记忆 | `content`, `user_id`, `metadata` |
| `recall_search` | 搜索记忆 | `query`, `user_id`, `top_k` |
| `recall_get_context` | 获取上下文 | `query`, `user_id`, `max_tokens` |
| `recall_list_memories` | 列出记忆 | `user_id`, `limit`, `offset` |
| `recall_delete_memory` | 删除记忆 | `memory_id`, `user_id` |

### 伏笔系统 Tools

| Tool 名称 | 功能 | 参数 |
|-----------|------|------|
| `recall_plant_foreshadowing` | 埋下伏笔 | `content`, `user_id`, `importance` |
| `recall_list_foreshadowings` | 列出伏笔 | `user_id` |
| `recall_resolve_foreshadowing` | 解决伏笔 | `foreshadowing_id`, `resolution` |

### 配置管理 Tools

| Tool 名称 | 功能 | 参数 |
|-----------|------|------|
| `recall_get_stats` | 获取统计信息 | `user_id` |
| `recall_clear_memories` | 清空记忆 | `user_id`, `confirm` |

---

## MCP Resources 设计

| Resource URI | 功能 |
|--------------|------|
| `recall://memories/{user_id}` | 获取用户所有记忆 |
| `recall://foreshadowings/{user_id}` | 获取用户所有伏笔 |
| `recall://stats/{user_id}` | 获取用户统计信息 |

---

## 实现计划

### Phase 1: 基础 MCP Server（预计 1-2 天）

- [ ] 创建 `recall/mcp_server.py`
- [ ] 实现 MCP 协议基础（stdio 通信）
- [ ] 实现核心 Tools：
  - [ ] `recall_add_memory`
  - [ ] `recall_search`
  - [ ] `recall_get_context`
- [ ] 本地测试（Claude Desktop）

### Phase 2: 完整 Tools（预计 1 天）

- [ ] 实现记忆管理 Tools：
  - [ ] `recall_list_memories`
  - [ ] `recall_delete_memory`
  - [ ] `recall_clear_memories`
- [ ] 实现伏笔系统 Tools：
  - [ ] `recall_plant_foreshadowing`
  - [ ] `recall_list_foreshadowings`
  - [ ] `recall_resolve_foreshadowing`
- [ ] 实现统计 Tools：
  - [ ] `recall_get_stats`

### Phase 3: Resources 支持（预计 0.5 天）

- [ ] 实现 MCP Resources
- [ ] 支持 `recall://` URI scheme

### Phase 4: 高级特性（预计 1 天）

- [ ] SSE 传输支持（用于远程部署）
- [ ] 多用户/多项目隔离
- [ ] 配置热更新
- [ ] 错误处理和日志

### Phase 5: 文档和发布（预计 0.5 天）

- [ ] 编写使用文档
- [ ] Claude Desktop 配置示例
- [ ] VS Code 配置示例
- [ ] 发布到 npm/pypi（可选）

---

## 文件结构

```
recall/
├── __init__.py
├── engine.py           # 核心引擎（已有）
├── server.py           # HTTP API Server（已有）
├── mcp_server.py       # 【新增】MCP Server 入口
├── mcp/
│   ├── __init__.py
│   ├── tools.py        # 【新增】MCP Tools 定义
│   ├── resources.py    # 【新增】MCP Resources 定义
│   └── transport.py    # 【新增】传输层（stdio/sse）
└── ...
```

---

## 使用示例

### Claude Desktop 配置

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
`%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "recall": {
      "command": "python",
      "args": ["-m", "recall.mcp_server"],
      "env": {
        "RECALL_DATA_ROOT": "/path/to/recall_data"
      }
    }
  }
}
```

### VS Code 配置

`.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "recall": {
      "command": "python",
      "args": ["-m", "recall.mcp_server"]
    }
  }
}
```

### 用户交互示例

```
用户: 记住，我的项目使用 TypeScript + React，喜欢函数式组件

Claude: [调用 recall_add_memory]
        好的，我已经记住了你的技术栈偏好：TypeScript + React，函数式组件。

---（三个月后）---

用户: 帮我写一个按钮组件

Claude: [调用 recall_search: "按钮组件 技术栈"]
        [获取到记忆: "用户使用 TypeScript + React，喜欢函数式组件"]
        
        好的，我用 TypeScript + React 函数式组件来写：
        
        ```tsx
        interface ButtonProps {
          label: string;
          onClick: () => void;
        }
        
        const Button: React.FC<ButtonProps> = ({ label, onClick }) => {
          return <button onClick={onClick}>{label}</button>;
        };
        ```
```

---

## 依赖

```toml
# pyproject.toml 新增
[project.optional-dependencies]
mcp = [
    "mcp>=1.0.0",
]
```

---

## 兼容性

| 平台 | 支持状态 | 说明 |
|------|---------|------|
| Claude Desktop | ✅ 原生支持 | 官方 MCP 支持 |
| VS Code + Copilot | ✅ 原生支持 | 已支持 MCP |
| Cursor | ✅ 原生支持 | 已支持 MCP |
| Cherry Studio | ✅ 原生支持 | 已支持 MCP |
| SillyTavern | ⚠️ 需插件 | 继续使用 HTTP API |
| 其他 | 🔄 看情况 | MCP 生态在扩展中 |

---

## 风险和注意事项

1. **MCP 协议版本**：需关注 MCP 协议更新，保持兼容
2. **性能**：stdio 通信可能有性能开销，需测试
3. **并发**：MCP 单进程模型，需考虑并发访问
4. **向后兼容**：保留 HTTP API，不破坏现有用户

---

## 参考资料

- [MCP 官方文档](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Desktop MCP 配置](https://modelcontextprotocol.io/quickstart/user)

---

## 更新日志

| 日期 | 内容 |
|------|------|
| 2026-01-19 | 创建计划文档 |
