"""Recall MCP Server 入口

支持的 MCP 客户端：
- Claude Desktop
- VS Code / Cursor (Copilot)
- 任何支持 MCP 的 AI 应用

传输方式：
- stdio（默认，本地使用）
- SSE（远程部署，设置 MCP_TRANSPORT=sse）
"""
import asyncio
import os
from mcp.server import Server
from recall.engine import RecallEngine
from recall.mcp.tools import register_tools
from recall.mcp.resources import register_resources


def create_app():
    app = Server("recall-memory")
    engine = RecallEngine()
    register_tools(app, engine)
    register_resources(app, engine)
    return app


async def _async_main():
    transport = os.environ.get('MCP_TRANSPORT', 'stdio')
    app = create_app()

    if transport == 'sse':
        import uvicorn
        from recall.mcp.transport import create_sse_app
        sse_app = create_sse_app(app)
        port = int(os.environ.get('MCP_PORT', '8765'))
        config = uvicorn.Config(sse_app, host="0.0.0.0", port=port)
        server = uvicorn.Server(config)
        await server.serve()
    else:
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())


def main():
    """同步入口 — pyproject.toml console_scripts 指向此函数"""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
