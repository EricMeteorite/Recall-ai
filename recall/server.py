"""Recall API Server - FastAPI HTTP 接口"""

import os
import time
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .version import __version__
from .engine import RecallEngine


# ==================== 请求/响应模型 ====================

class AddMemoryRequest(BaseModel):
    """添加记忆请求"""
    content: str = Field(..., description="记忆内容")
    user_id: str = Field(default="default", description="用户ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")


class AddMemoryResponse(BaseModel):
    """添加记忆响应"""
    id: str
    success: bool
    entities: List[str] = []
    message: str = ""


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="搜索查询")
    user_id: str = Field(default="default", description="用户ID")
    top_k: int = Field(default=10, ge=1, le=100, description="返回数量")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="过滤条件")


class SearchResultItem(BaseModel):
    """搜索结果项"""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = {}
    entities: List[str] = []


class ContextRequest(BaseModel):
    """构建上下文请求"""
    query: str = Field(..., description="当前查询")
    user_id: str = Field(default="default", description="用户ID")
    max_tokens: int = Field(default=2000, description="最大token数")
    include_recent: int = Field(default=5, description="包含的最近对话数")


class ForeshadowingRequest(BaseModel):
    """伏笔请求"""
    content: str = Field(..., description="伏笔内容")
    related_entities: Optional[List[str]] = Field(default=None, description="相关实体")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性")


class ForeshadowingItem(BaseModel):
    """伏笔项"""
    id: str
    content: str
    status: str
    importance: float
    hints: List[str] = []
    resolution: Optional[str] = None


# ==================== 全局引擎 ====================

_engine: Optional[RecallEngine] = None


def get_engine() -> RecallEngine:
    """获取全局引擎实例
    
    根据环境变量 RECALL_EMBEDDING_MODE 自动选择模式：
    - none: 轻量模式
    - local: 完整模式
    - openai: Hybrid-OpenAI
    - siliconflow: Hybrid-硅基流动
    """
    global _engine
    if _engine is None:
        import os
        embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', '').lower()
        
        if embedding_mode == 'none':
            # 轻量模式
            _engine = RecallEngine(lightweight=True)
        else:
            # 其他模式：让 engine 自动选择
            # embedding_config 会根据环境变量自动检测
            _engine = RecallEngine(lightweight=False)
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print(f"[Recall API] 服务启动 v{__version__}")
    get_engine()  # 预初始化
    
    yield
    
    # 关闭时
    if _engine:
        _engine.close()
    print("[Recall API] 服务关闭")


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="Recall API",
    description="Recall - 智能记忆管理系统 API",
    version=__version__,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 健康检查 ====================

@app.get("/", tags=["Health"])
async def root():
    """根路径 - 服务信息"""
    return {
        "service": "Recall API",
        "version": __version__,
        "status": "running"
    }


@app.get("/health", tags=["Health"])
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": time.time()
    }


# ==================== 记忆管理 API ====================

@app.post("/v1/memories", response_model=AddMemoryResponse, tags=["Memories"])
async def add_memory(request: AddMemoryRequest):
    """添加记忆"""
    engine = get_engine()
    result = engine.add(
        content=request.content,
        user_id=request.user_id,
        metadata=request.metadata
    )
    return AddMemoryResponse(
        id=result.id,
        success=result.success,
        entities=result.entities,
        message=result.message
    )


@app.post("/v1/memories/search", response_model=List[SearchResultItem], tags=["Memories"])
async def search_memories(request: SearchRequest):
    """搜索记忆"""
    engine = get_engine()
    results = engine.search(
        query=request.query,
        user_id=request.user_id,
        top_k=request.top_k,
        filters=request.filters
    )
    return [
        SearchResultItem(
            id=r.id,
            content=r.content,
            score=r.score,
            metadata=r.metadata,
            entities=r.entities
        )
        for r in results
    ]


@app.get("/v1/memories", tags=["Memories"])
async def list_memories(
    user_id: str = Query(default="default", description="用户ID"),
    limit: int = Query(default=100, ge=1, le=1000, description="限制数量")
):
    """获取所有记忆"""
    engine = get_engine()
    memories = engine.get_all(user_id=user_id, limit=limit)
    return {"memories": memories, "count": len(memories)}


@app.get("/v1/memories/{memory_id}", tags=["Memories"])
async def get_memory(memory_id: str, user_id: str = Query(default="default")):
    """获取单条记忆"""
    engine = get_engine()
    memories = engine.get_all(user_id=user_id)
    
    for m in memories:
        if m.get('id') == memory_id:
            return m
    
    raise HTTPException(status_code=404, detail="记忆不存在")


@app.delete("/v1/memories/{memory_id}", tags=["Memories"])
async def delete_memory(memory_id: str, user_id: str = Query(default="default")):
    """删除记忆"""
    engine = get_engine()
    success = engine.delete(memory_id, user_id=user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="记忆不存在或删除失败")
    
    return {"success": True, "message": "删除成功"}


@app.put("/v1/memories/{memory_id}", tags=["Memories"])
async def update_memory(
    memory_id: str,
    content: str = Body(...),
    user_id: str = Query(default="default"),
    metadata: Optional[Dict[str, Any]] = Body(default=None)
):
    """更新记忆"""
    engine = get_engine()
    success = engine.update(memory_id, content, user_id=user_id, metadata=metadata)
    
    if not success:
        raise HTTPException(status_code=404, detail="记忆不存在或更新失败")
    
    return {"success": True, "message": "更新成功"}


# ==================== 上下文构建 API ====================

@app.post("/v1/context", tags=["Context"])
async def build_context(request: ContextRequest):
    """构建上下文"""
    engine = get_engine()
    context = engine.build_context(
        query=request.query,
        user_id=request.user_id,
        max_tokens=request.max_tokens,
        include_recent=request.include_recent
    )
    return {"context": context}


# ==================== 伏笔 API ====================

@app.post("/v1/foreshadowing", response_model=ForeshadowingItem, tags=["Foreshadowing"])
async def plant_foreshadowing(request: ForeshadowingRequest):
    """埋下伏笔"""
    engine = get_engine()
    fsh = engine.plant_foreshadowing(
        content=request.content,
        related_entities=request.related_entities,
        importance=request.importance
    )
    return ForeshadowingItem(
        id=fsh.id,
        content=fsh.content,
        status=fsh.status.value,
        importance=fsh.importance,
        hints=fsh.hints,
        resolution=fsh.resolution
    )


@app.get("/v1/foreshadowing", response_model=List[ForeshadowingItem], tags=["Foreshadowing"])
async def list_foreshadowing():
    """获取活跃伏笔"""
    engine = get_engine()
    active = engine.get_active_foreshadowings()
    return [
        ForeshadowingItem(
            id=f.id,
            content=f.content,
            status=f.status.value,
            importance=f.importance,
            hints=f.hints,
            resolution=f.resolution
        )
        for f in active
    ]


@app.post("/v1/foreshadowing/{foreshadowing_id}/resolve", tags=["Foreshadowing"])
async def resolve_foreshadowing(
    foreshadowing_id: str,
    resolution: str = Body(..., embed=True)
):
    """解决伏笔"""
    engine = get_engine()
    success = engine.resolve_foreshadowing(foreshadowing_id, resolution)
    
    if not success:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    
    return {"success": True, "message": "伏笔已解决"}


# ==================== 实体 API ====================

@app.get("/v1/entities/{name}", tags=["Entities"])
async def get_entity(name: str):
    """获取实体信息"""
    engine = get_engine()
    entity = engine.get_entity(name)
    
    if not entity:
        raise HTTPException(status_code=404, detail="实体不存在")
    
    return entity


@app.get("/v1/entities/{name}/related", tags=["Entities"])
async def get_related_entities(name: str):
    """获取相关实体"""
    engine = get_engine()
    related = engine.get_related_entities(name)
    return {"entity": name, "related": related}


# ==================== 管理 API ====================

@app.get("/v1/stats", tags=["Admin"])
async def get_stats():
    """获取统计信息"""
    engine = get_engine()
    return engine.get_stats()


@app.post("/v1/consolidate", tags=["Admin"])
async def consolidate(user_id: str = Query(default="default")):
    """执行记忆整合"""
    engine = get_engine()
    engine.consolidate(user_id=user_id)
    return {"success": True, "message": "整合完成"}


@app.post("/v1/reset", tags=["Admin"])
async def reset(
    user_id: Optional[str] = Query(default=None),
    confirm: bool = Query(default=False)
):
    """重置记忆（危险操作）"""
    if not confirm:
        raise HTTPException(status_code=400, detail="需要 confirm=true 确认")
    
    engine = get_engine()
    engine.reset(user_id=user_id)
    return {"success": True, "message": "重置完成"}


# ==================== mem0 兼容 API ====================
# 提供与 mem0 API 格式兼容的接口

@app.post("/v1/memory/", tags=["mem0 Compatible"])
async def mem0_add(
    messages: List[Dict[str, str]] = Body(...),
    user_id: str = Body(default="default"),
    metadata: Optional[Dict[str, Any]] = Body(default=None)
):
    """mem0 兼容 - 添加记忆"""
    engine = get_engine()
    
    results = []
    for msg in messages:
        content = msg.get('content', '')
        if content:
            result = engine.add(content, user_id=user_id, metadata=metadata)
            results.append({"id": result.id, "success": result.success})
    
    return {"results": results}


@app.get("/v1/memory/", tags=["mem0 Compatible"])
async def mem0_get_all(
    user_id: str = Query(default="default"),
    limit: int = Query(default=100)
):
    """mem0 兼容 - 获取所有记忆"""
    engine = get_engine()
    memories = engine.get_all(user_id=user_id, limit=limit)
    
    # 转换为 mem0 格式
    return {
        "memories": [
            {
                "id": m.get('id'),
                "memory": m.get('content', m.get('memory', '')),
                "user_id": user_id,
                "metadata": m.get('metadata', {}),
                "created_at": m.get('created_at')
            }
            for m in memories
        ]
    }


@app.post("/v1/memory/search/", tags=["mem0 Compatible"])
async def mem0_search(
    query: str = Body(...),
    user_id: str = Body(default="default"),
    limit: int = Body(default=10)
):
    """mem0 兼容 - 搜索记忆"""
    engine = get_engine()
    results = engine.search(query, user_id=user_id, top_k=limit)
    
    return {
        "memories": [
            {
                "id": r.id,
                "memory": r.content,
                "score": r.score,
                "user_id": user_id,
                "metadata": r.metadata
            }
            for r in results
        ]
    }


@app.delete("/v1/memory/{memory_id}/", tags=["mem0 Compatible"])
async def mem0_delete(memory_id: str, user_id: str = Query(default="default")):
    """mem0 兼容 - 删除记忆"""
    engine = get_engine()
    success = engine.delete(memory_id, user_id=user_id)
    return {"success": success}
