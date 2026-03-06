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
from recall.mcp.tools import register_tools
from recall.mcp.resources import register_resources


def _get_shared_engine():
    """获取与 HTTP 服务器共享的单例引擎实例。

    优先复用 recall.server.get_engine() 的全局单例，
    若 server 模块不可用则回退到直接创建 RecallEngine。
    """
    try:
        from recall.server import get_engine
        return get_engine()
    except Exception:
        from recall.engine import RecallEngine
        return RecallEngine()


def create_app():
    app = Server("recall-memory")
    engine = _get_shared_engine()
    register_tools(app, engine)
    register_resources(app, engine)
    return app


async def _async_main():
    # v7.0.3: 优先从 RecallConfig 读取（之前直接读 os.environ）
    try:
        from .config import RecallConfig
        _cfg = RecallConfig.from_env()
        transport = getattr(_cfg, 'mcp_transport', None) or os.environ.get('MCP_TRANSPORT', 'stdio')
        mcp_port = getattr(_cfg, 'mcp_port', None) or int(os.environ.get('MCP_PORT', '8765'))
    except Exception:
        transport = os.environ.get('MCP_TRANSPORT', 'stdio')
        mcp_port = int(os.environ.get('MCP_PORT', '8765'))
    
    app = create_app()

    if transport == 'sse':
        import uvicorn
        from recall.mcp.transport import create_sse_app
        sse_app = create_sse_app(app)
        config = uvicorn.Config(sse_app, host="0.0.0.0", port=mcp_port)
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
