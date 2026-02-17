# Recall MCP Server 配置指南

## 概述

Recall v5.0 支持 Model Context Protocol (MCP)，可作为 MCP Server 为以下客户端提供记忆服务：

- **Claude Desktop**
- **VS Code / Cursor (GitHub Copilot)**
- **任何支持 MCP 的 AI 应用**

## 安装

```bash
# 安装 MCP 可选依赖
pip install recall-ai[mcp]

# 或手动安装
pip install mcp>=1.0.0 httpx-sse>=0.4.0 uvicorn>=0.30.0 starlette>=0.38.0
```

## Claude Desktop 配置

编辑 Claude Desktop 配置文件：

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "recall": {
      "command": "recall-mcp",
      "args": [],
      "env": {
        "LLM_API_KEY": "your-api-key",
        "LLM_API_BASE": "https://api.siliconflow.cn/v1",
        "LLM_MODEL": "deepseek-chat",
        "EMBEDDING_API_KEY": "your-embedding-key",
        "EMBEDDING_API_BASE": "https://api.siliconflow.cn/v1",
        "EMBEDDING_MODEL": "BAAI/bge-large-zh-v1.5",
        "RECALL_MODE": "general"
      }
    }
  }
}
```

## 可用工具

| Tool 名称 | 说明 |
|-----------|------|
| `recall_add` | 添加一条记忆 |
| `recall_search` | 搜索相关记忆 |
| `recall_context` | 构建上下文（记忆 + 实体 + 知识图谱） |
| `recall_add_batch` | 批量添加记忆（高吞吐） |
| `recall_add_turn` | 添加对话轮次 |
| `recall_list` | 分页列出记忆 |
| `recall_delete` | 删除记忆 |
| `recall_stats` | 系统统计信息 |
| `recall_entities` | 实体列表 |
| `recall_graph_traverse` | 知识图谱遍历 |
| `recall_search_filtered` | 按来源/标签过滤搜索 |

## 可用资源

| URI | 说明 |
|-----|------|
| `recall://memories` | 所有记忆 |
| `recall://entities` | 所有实体 |
| `recall://stats` | 统计信息 |
| `recall://memories/{id}` | 单条记忆详情 |
| `recall://entities/{name}` | 实体详情 |

## SSE 远程模式

对于远程部署场景，可使用 SSE 传输：

```bash
# 设置环境变量后启动
MCP_TRANSPORT=sse MCP_PORT=8765 recall-mcp
```

客户端连接地址：`http://your-server:8765/sse`

## 模式说明

通过 `RECALL_MODE` 环境变量控制行为模式：

| 模式 | 说明 |
|------|------|
| `roleplay` | 角色扮演模式（默认，完全兼容 SillyTavern） |
| `general` | 通用模式（适合数据聚合、知识管理等） |
| `knowledge_base` | 知识库模式（纯知识管理） |
