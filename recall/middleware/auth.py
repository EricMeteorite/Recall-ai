"""
Recall v7.0 - API Key Authentication Middleware

Optional API key authentication.
- Enabled when the ``RECALL_API_KEY`` environment variable is set.
- Key can be supplied via ``X-API-Key`` header **or** ``api_key`` query parameter.
- ``/health`` and ``/v1/mode`` are always exempt.

Dangerous endpoints (``/v1/reset``, ``/v1/data/restore``, ``DELETE /v1/memories``)
require the API key **even when global authentication is disabled**.  Import
``require_api_key`` and use it as a dependency for those routes.
"""
from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

# Paths that never require authentication
_EXEMPT_PATHS: set[str] = {"/", "/health", "/v1/mode", "/docs", "/redoc", "/openapi.json"}

# Dangerous paths that always require an API key (even when global auth is off)
DANGEROUS_PATHS: dict[str, set[str]] = {
    "/v1/reset": {"POST"},
    "/v1/data/restore": {"POST"},
    "/v1/memories": {"DELETE"},       # clear by user_id
    "/v1/memories/all": {"DELETE"},   # clear all
}


def _get_api_key() -> Optional[str]:
    """Return the configured API key, or ``None`` if auth is disabled."""
    return os.environ.get("RECALL_API_KEY") or None


def _extract_key(request: Request) -> Optional[str]:
    """Try to pull the API key from the request."""
    # Header first
    key = request.headers.get("x-api-key")
    if key:
        return key
    # Query param fallback
    key = request.query_params.get("api_key")
    return key or None


def _is_dangerous(path: str, method: str) -> bool:
    """Check whether *path* + *method* is a dangerous endpoint."""
    methods = DANGEROUS_PATHS.get(path)
    if methods and method.upper() in methods:
        return True
    return False


class APIKeyMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces API key authentication.

    * If ``RECALL_API_KEY`` is **not** set, all requests pass through
      **except** those hitting a dangerous endpoint.
    * Dangerous endpoints **always** require the key.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path.rstrip("/") or "/"
        method = request.method.upper()
        expected_key = _get_api_key()

        # Always let exempt paths through
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        # Dangerous endpoints – require key unconditionally
        if _is_dangerous(path, method):
            if not expected_key:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "此端点需要配置 RECALL_API_KEY 环境变量才能使用"},
                )
            supplied = _extract_key(request)
            if not supplied or not secrets.compare_digest(supplied, expected_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "API key 无效或缺失"},
                )
            return await call_next(request)

        # Global auth – if key is configured, enforce it everywhere
        if expected_key:
            supplied = _extract_key(request)
            if not supplied or not secrets.compare_digest(supplied, expected_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "API key 无效或缺失。请通过 X-API-Key 头或 api_key 查询参数提供密钥。"},
                )

        return await call_next(request)
