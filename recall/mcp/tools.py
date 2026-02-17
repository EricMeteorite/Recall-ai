"""recall/mcp/tools.py — MCP Tools 注册与桥接"""

import json
from mcp.server import Server
from mcp.types import Tool, TextContent
from recall.engine import RecallEngine


def register_tools(app: Server, engine: RecallEngine):
    """将 Recall API 注册为 MCP Tools"""

    @app.list_tools()
    async def list_tools():
        return [
            Tool(
                name="recall_add",
                description="添加一条记忆到 Recall",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "记忆内容"},
                        "user_id": {"type": "string", "description": "用户ID", "default": "default"},
                        "metadata": {"type": "object", "description": "元数据", "default": {}},
                    },
                    "required": ["content"]
                }
            ),
            Tool(
                name="recall_search",
                description="在 Recall 中搜索相关记忆",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "user_id": {"type": "string", "default": "default"},
                        "top_k": {"type": "integer", "default": 10},
                        "source": {"type": "string", "description": "按来源过滤（可选）"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "按标签过滤"},
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="recall_context",
                description="构建上下文（包含相关记忆 + 实体 + 知识图谱）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string", "default": "default"},
                        "character_id": {"type": "string", "default": "default"},
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="recall_add_batch",
                description="批量添加记忆（高吞吐）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                    "source": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["content"]
                            }
                        },
                        "user_id": {"type": "string", "default": "default"},
                    },
                    "required": ["items"]
                }
            ),
            Tool(
                name="recall_add_turn",
                description="添加一轮对话（用户消息 + AI 回复）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_message": {"type": "string", "description": "用户消息"},
                        "ai_response": {"type": "string", "description": "AI回复"},
                        "user_id": {"type": "string", "default": "default"},
                        "character_id": {"type": "string", "default": "default"},
                        "metadata": {"type": "object", "default": {}},
                    },
                    "required": ["user_message", "ai_response"]
                }
            ),
            Tool(
                name="recall_list",
                description="分页列出记忆",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "default": "default"},
                        "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 1000},
                        "offset": {"type": "integer", "default": 0, "minimum": 0},
                    }
                }
            ),
            Tool(
                name="recall_delete",
                description="删除一条记忆",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string", "description": "记忆ID"},
                        "user_id": {"type": "string", "default": "default"},
                    },
                    "required": ["memory_id"]
                }
            ),
            Tool(
                name="recall_stats",
                description="获取 Recall 系统统计信息",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="recall_entities",
                description="获取实体列表",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "default": "default"},
                        "character_id": {"type": "string", "default": "default"},
                        "entity_type": {"type": "string", "description": "按类型过滤(PERSON/LOCATION等)"},
                        "limit": {"type": "integer", "default": 100},
                    }
                }
            ),
            Tool(
                name="recall_graph_traverse",
                description="从指定实体出发遍历知识图谱",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_entity": {"type": "string", "description": "起始实体名称"},
                        "max_depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
                        "relation_types": {"type": "array", "items": {"type": "string"}, "description": "关系类型过滤"},
                        "user_id": {"type": "string", "default": "default"},
                    },
                    "required": ["start_entity"]
                }
            ),
            Tool(
                name="recall_search_filtered",
                description="按来源/标签过滤搜索记忆（v5.0）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string", "default": "default"},
                        "source": {"type": "string", "description": "按来源过滤"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "top_k": {"type": "integer", "default": 10},
                    },
                    "required": ["query"]
                }
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Tool 调用入口 — 桥接到 RecallEngine"""
        if name == "recall_add":
            result = engine.add(
                content=arguments["content"],
                user_id=arguments.get("user_id", "default"),
                metadata=arguments.get("metadata", {}),
            )
            # AddResult dataclass 字段名是 .id（非 .memory_id）
            return [TextContent(type="text", text=f"已添加记忆: {result.id}")]

        elif name == "recall_search":
            results = engine.search(
                query=arguments["query"],
                user_id=arguments.get("user_id", "default"),
                top_k=arguments.get("top_k", 10),
            )
            # SearchResult 是 dataclass（字段: id, content, score, metadata, entities）
            # source/tags 存于 metadata 字典中，需从 metadata 获取
            if "source" in arguments:
                results = [r for r in results if r.metadata.get("source", "") == arguments["source"]]
            if "tags" in arguments:
                results = [r for r in results if set(arguments["tags"]) & set(r.metadata.get("tags", []))]

            text = "\n\n".join([f"[{r.score:.2f}] {r.content[:200]}" for r in results])
            return [TextContent(type="text", text=text or "未找到相关记忆")]

        elif name == "recall_context":
            context = engine.build_context(
                query=arguments["query"],
                user_id=arguments.get("user_id", "default"),
                character_id=arguments.get("character_id", "default"),
            )
            return [TextContent(type="text", text=context)]

        elif name == "recall_add_batch":
            ids = engine.add_batch(
                items=arguments["items"],
                user_id=arguments.get("user_id", "default"),
            )
            return [TextContent(type="text", text=f"批量添加完成: {len(ids)} 条")]

        elif name == "recall_add_turn":
            result = engine.add_turn(
                user_message=arguments["user_message"],
                ai_response=arguments["ai_response"],
                user_id=arguments.get("user_id", "default"),
                character_id=arguments.get("character_id", "default"),
                metadata=arguments.get("metadata"),
            )
            # AddTurnResult 是 dataclass，需显式格式化
            return [TextContent(type="text", text=f"已添加对话轮次: user={result.user_memory_id}, ai={result.ai_memory_id}")]

        elif name == "recall_list":
            # get_paginated() 返回 tuple: (memories, total_count)
            memories, total = engine.get_paginated(
                user_id=arguments.get("user_id", "default"),
                offset=arguments.get("offset", 0),
                limit=arguments.get("limit", 100),
            )
            # memories 中每条记忆格式为 {'content': ..., 'metadata': {'id': ..., ...}, 'timestamp': ...}
            text = "\n".join([f"[{m.get('metadata', {}).get('id', 'N/A')}] {m['content'][:100]}" for m in memories])
            return [TextContent(type="text", text=text or "暂无记忆")]

        elif name == "recall_delete":
            success = engine.delete(
                arguments["memory_id"],
                user_id=arguments.get("user_id", "default"),
            )
            if success:
                return [TextContent(type="text", text=f"已删除记忆: {arguments['memory_id']}")]
            else:
                return [TextContent(type="text", text=f"记忆不存在: {arguments['memory_id']}")]

        elif name == "recall_stats":
            stats = engine.get_stats()
            return [TextContent(type="text", text=json.dumps(stats, ensure_ascii=False, indent=2))]

        elif name == "recall_entities":
            entities = engine.list_entities(
                user_id=arguments.get("user_id", "default"),
                entity_type=arguments.get("entity_type"),
                limit=arguments.get("limit", 100),
            )
            text = "\n".join([f"{e['name']} ({e['type']}): {e.get('summary', '')[:80]}" for e in entities])
            return [TextContent(type="text", text=text or "暂无实体")]

        elif name == "recall_graph_traverse":
            graph_result = engine.traverse_graph(
                start_entity=arguments["start_entity"],
                max_depth=arguments.get("max_depth", 2),
                relation_types=arguments.get("relation_types"),
                user_id=arguments.get("user_id", "default"),
            )
            return [TextContent(type="text", text=json.dumps(graph_result, ensure_ascii=False, indent=2))]

        elif name == "recall_search_filtered":
            results = engine.search(
                query=arguments["query"],
                user_id=arguments.get("user_id", "default"),
                top_k=arguments.get("top_k", 10),
                source=arguments.get("source"),
                tags=arguments.get("tags"),
            )
            text = "\n\n".join([f"[{r.score:.2f}] {r.content[:200]}" for r in results])
            return [TextContent(type="text", text=text or "未找到相关记忆")]

        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]
