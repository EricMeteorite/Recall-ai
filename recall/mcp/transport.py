"""recall/mcp/transport.py — SSE 传输层

在 stdio（本地）之外，提供 HTTP+SSE 远程传输。
MCP SDK 已内置 SSE server，此处做配置封装。
"""

from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse


def create_sse_app(mcp_server):
    """将 MCP Server 包装为 SSE HTTP 应用

    Args:
        mcp_server: 已注册好 tools/resources 的 mcp.server.Server 实例

    Returns:
        Starlette ASGI 应用，可用 uvicorn 启动
    """
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        """SSE 端点 — 客户端在此建立长连接"""
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1],
                mcp_server.create_initialization_options()
            )

    async def health(request):
        return JSONResponse({"status": "ok", "server": "recall-mcp"})

    return Starlette(
        routes=[
            Route("/health", health),
            Mount("/sse", app=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
        ]
    )
