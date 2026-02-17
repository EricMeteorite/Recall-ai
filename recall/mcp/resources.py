"""recall/mcp/resources.py — MCP Resources 注册"""

from mcp.server import Server
from mcp.types import Resource, TextContent
from recall.engine import RecallEngine
from urllib.parse import unquote
import json


def register_resources(app: Server, engine: RecallEngine):

    @app.list_resources()
    async def list_resources():
        return [
            Resource(uri="recall://memories", name="所有记忆", mimeType="application/json"),
            Resource(uri="recall://entities", name="所有实体", mimeType="application/json"),
            Resource(uri="recall://stats", name="统计信息", mimeType="application/json"),
        ]

    @app.read_resource()
    async def read_resource(uri: str):
        if uri == "recall://memories":
            memories = engine.list_memories(limit=100)
            return [TextContent(type="text", text=json.dumps(memories, ensure_ascii=False, indent=2))]
        elif uri == "recall://entities":
            entities = engine.list_entities()
            return [TextContent(type="text", text=json.dumps(entities, ensure_ascii=False, indent=2))]
        elif uri == "recall://stats":
            stats = engine.get_stats()
            return [TextContent(type="text", text=json.dumps(stats, ensure_ascii=False, indent=2))]
        elif uri.startswith("recall://memories/"):
            memory_id = unquote(uri.split("/")[-1])
            memory = engine.get(memory_id)
            return [TextContent(type="text", text=json.dumps(memory, ensure_ascii=False, indent=2))]
        elif uri.startswith("recall://entities/"):
            entity_name = unquote(uri.split("/")[-1])
            entity = engine.get_entity_detail(entity_name)
            return [TextContent(type="text", text=json.dumps(entity, ensure_ascii=False, indent=2))]
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown resource: {uri}"}))]
