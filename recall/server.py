"""Recall API Server - FastAPI HTTP 接口"""

import os
import time
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .version import __version__
from .engine import RecallEngine


# ==================== 配置文件管理 ====================

# 支持的配置项（统一使用 OpenAI 兼容格式）
SUPPORTED_CONFIG_KEYS = {
    # Embedding 配置
    'EMBEDDING_API_KEY',
    'EMBEDDING_API_BASE',
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMENSION',
    # Embedding 模式
    'RECALL_EMBEDDING_MODE',
    # LLM 配置（用于伏笔分析器等功能）
    'LLM_API_KEY',
    'LLM_API_BASE',
    'LLM_MODEL',
}


def get_config_file_path() -> Path:
    """获取配置文件路径"""
    # 优先使用环境变量指定的数据目录
    data_root = os.environ.get('RECALL_DATA_ROOT', './recall_data')
    return Path(data_root) / 'config' / 'api_keys.env'


def get_default_config_content() -> str:
    """获取默认配置文件内容"""
    return '''# ============================================================================
# Recall-AI 配置文件
# Recall-AI Configuration File
# ============================================================================

# ----------------------------------------------------------------------------
# Embedding 配置 (自定义 OpenAI 兼容接口)
# Embedding Configuration (Custom OpenAI Compatible API)
# ----------------------------------------------------------------------------
EMBEDDING_API_KEY=your_embedding_api_key_here
EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024

# Embedding 模式: auto(自动检测), local(本地), api(远程API)
# Embedding Mode: auto(auto detect), local(local model), api(remote API)
RECALL_EMBEDDING_MODE=auto

# ----------------------------------------------------------------------------
# LLM 配置 (自定义 OpenAI 兼容接口)
# LLM Configuration (Custom OpenAI Compatible API)
# ----------------------------------------------------------------------------
LLM_API_KEY=your_llm_api_key_here
LLM_API_BASE=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
'''


def load_api_keys_from_file():
    """从配置文件加载配置到环境变量
    
    配置文件位置: recall_data/config/api_keys.env
    用户可以直接编辑这个文件，然后调用热更新接口
    """
    config_file = get_config_file_path()
    
    if not config_file.exists():
        # 创建默认配置文件
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(get_default_config_content(), encoding='utf-8')
        print(f"[Config] 已创建配置文件: {config_file}")
        return
    
    # 先清除所有支持的配置项（热更新时确保旧配置被清除）
    for key in SUPPORTED_CONFIG_KEYS:
        if key in os.environ:
            del os.environ[key]
    
    # 读取配置文件
    loaded_configs = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                # 解析 KEY=VALUE 格式
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # 只设置支持的配置项，且值非空
                    if value and key in SUPPORTED_CONFIG_KEYS:
                        os.environ[key] = value
                        # 敏感信息脱敏显示
                        if 'KEY' in key:
                            display_value = value[:8] + '...' if len(value) > 8 else '***'
                        else:
                            display_value = value
                        loaded_configs.append(f"{key}={display_value}")
        
        if loaded_configs:
            print(f"[Config] 已加载配置: {', '.join(loaded_configs)}")
        else:
            print(f"[Config] 配置文件为空或无有效配置")
    except Exception as e:
        print(f"[Config] 读取配置文件失败: {e}")


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
    user_id: str = Field(default="default", description="用户ID（角色名）")
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


class ForeshadowingAnalysisRequest(BaseModel):
    """伏笔分析请求"""
    content: str = Field(..., description="对话内容")
    role: str = Field(default="user", description="角色（user/assistant）")
    user_id: str = Field(default="default", description="用户ID（角色名）")


class ForeshadowingAnalysisResult(BaseModel):
    """伏笔分析结果"""
    triggered: bool = Field(default=False, description="是否触发了分析")
    new_foreshadowings: List[dict] = Field(default=[], description="新检测到的伏笔")
    potentially_resolved: List[dict] = Field(default=[], description="可能已解决的伏笔")
    error: Optional[str] = Field(default=None, description="错误信息")


class ForeshadowingConfigUpdate(BaseModel):
    """伏笔分析器配置更新"""
    trigger_interval: Optional[int] = Field(default=None, ge=1, description="触发间隔（轮次）")
    auto_plant: Optional[bool] = Field(default=None, description="自动埋下伏笔")
    auto_resolve: Optional[bool] = Field(default=None, description="自动解决伏笔")


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
        # 首次启动时加载配置文件
        load_api_keys_from_file()
        
        embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', '').lower()
        
        if embedding_mode == 'none':
            # 轻量模式
            _engine = RecallEngine(lightweight=True)
        else:
            # 其他模式：让 engine 自动选择
            # embedding_config 会根据环境变量自动检测
            _engine = RecallEngine(lightweight=False)
    return _engine


def reload_engine():
    """重新加载引擎（热更新）
    
    用于在修改配置文件后重新初始化引擎
    """
    global _engine
    
    # 关闭旧引擎
    if _engine is not None:
        try:
            _engine.close()
        except:
            pass
        _engine = None
    
    # 重新加载配置
    load_api_keys_from_file()
    
    # 重新创建引擎
    embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', '').lower()
    
    if embedding_mode == 'none':
        _engine = RecallEngine(lightweight=True)
    else:
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
    limit: int = Query(default=100, ge=1, le=1000, description="限制数量"),
    offset: int = Query(default=0, ge=0, description="偏移量，用于分页")
):
    """获取所有记忆
    
    支持分页：
    - limit: 每页数量
    - offset: 跳过的记录数
    
    示例：
    - 第一页: ?limit=20&offset=0
    - 第二页: ?limit=20&offset=20
    """
    engine = get_engine()
    all_memories = engine.get_all(user_id=user_id, limit=limit + offset)
    
    # 应用 offset
    memories = all_memories[offset:offset + limit] if offset > 0 else all_memories[:limit]
    
    return {
        "memories": memories, 
        "count": len(memories),
        "total": len(all_memories),
        "offset": offset,
        "limit": limit
    }


@app.get("/v1/memories/{memory_id}", tags=["Memories"])
async def get_memory(memory_id: str, user_id: str = Query(default="default")):
    """获取单条记忆"""
    engine = get_engine()
    memory = engine.get(memory_id, user_id=user_id)
    
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    
    return memory


@app.delete("/v1/memories/{memory_id}", tags=["Memories"])
async def delete_memory(memory_id: str, user_id: str = Query(default="default")):
    """删除记忆"""
    engine = get_engine()
    success = engine.delete(memory_id, user_id=user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="记忆不存在或删除失败")
    
    return {"success": True, "message": "删除成功"}


@app.delete("/v1/memories", tags=["Memories"])
async def clear_memories(
    user_id: str = Query(..., description="用户ID（角色名），必填"),
    confirm: bool = Query(default=False, description="确认删除，必须为 true")
):
    """清空指定角色的所有记忆
    
    ⚠️ 危险操作！这将删除该角色的全部记忆数据，无法恢复。
    
    使用场景：
    - 删除角色卡后清理对应的记忆数据
    - 重置某个角色的所有记忆
    
    示例:
        DELETE /v1/memories?user_id=角色名&confirm=true
    """
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="请添加 confirm=true 参数确认删除操作"
        )
    
    if user_id == "default":
        raise HTTPException(
            status_code=400,
            detail="不能删除 default 用户的记忆，请指定具体的角色名"
        )
    
    engine = get_engine()
    
    # 先获取数量
    memories = engine.get_all(user_id=user_id, limit=10000)
    count = len(memories)
    
    if count == 0:
        return {"success": True, "message": "该角色没有记忆数据", "deleted_count": 0}
    
    # 清空
    success = engine.clear(user_id=user_id)
    
    if success:
        return {
            "success": True, 
            "message": f"已清空角色 '{user_id}' 的所有记忆",
            "deleted_count": count
        }
    else:
        raise HTTPException(status_code=500, detail="清空失败")


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
        user_id=request.user_id,
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
async def list_foreshadowing(user_id: str = Query(default="default", description="用户ID（角色名）")):
    """获取活跃伏笔"""
    engine = get_engine()
    active = engine.get_active_foreshadowings(user_id)
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
    resolution: str = Body(..., embed=True),
    user_id: str = Query(default="default", description="用户ID（角色名）")
):
    """解决伏笔"""
    engine = get_engine()
    success = engine.resolve_foreshadowing(foreshadowing_id, resolution, user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    
    return {"success": True, "message": "伏笔已解决"}


# ==================== 伏笔分析 API ====================

@app.post("/v1/foreshadowing/analyze/turn", response_model=ForeshadowingAnalysisResult, tags=["Foreshadowing Analysis"])
async def analyze_foreshadowing_turn(request: ForeshadowingAnalysisRequest):
    """处理新的一轮对话（用于伏笔分析）
    
    在每轮对话后调用此端点，分析器会根据配置决定是否触发分析：
    - 手动模式：不做任何操作，返回空结果
    - LLM模式：累积对话，达到触发条件时自动分析
    """
    engine = get_engine()
    result = engine.on_foreshadowing_turn(
        content=request.content,
        role=request.role,
        user_id=request.user_id
    )
    return ForeshadowingAnalysisResult(
        triggered=result.triggered,
        new_foreshadowings=result.new_foreshadowings,
        potentially_resolved=result.potentially_resolved,
        error=result.error
    )


@app.post("/v1/foreshadowing/analyze/trigger", response_model=ForeshadowingAnalysisResult, tags=["Foreshadowing Analysis"])
async def trigger_foreshadowing_analysis(
    user_id: str = Query(default="default", description="用户ID（角色名）")
):
    """手动触发伏笔分析
    
    强制触发 LLM 分析（如果已配置）。可以在任何时候调用。
    """
    engine = get_engine()
    result = engine.trigger_foreshadowing_analysis(user_id)
    return ForeshadowingAnalysisResult(
        triggered=result.triggered,
        new_foreshadowings=result.new_foreshadowings,
        potentially_resolved=result.potentially_resolved,
        error=result.error
    )


@app.get("/v1/foreshadowing/analyzer/config", tags=["Foreshadowing Analysis"])
async def get_foreshadowing_analyzer_config():
    """获取伏笔分析器配置"""
    engine = get_engine()
    return engine.get_foreshadowing_analyzer_config()


@app.put("/v1/foreshadowing/analyzer/config", tags=["Foreshadowing Analysis"])
async def update_foreshadowing_analyzer_config(config: ForeshadowingConfigUpdate):
    """更新伏笔分析器配置
    
    注意：此端点只能更新部分配置，不能更改后端模式或 API key。
    要更改后端模式，需要重启服务器。
    """
    engine = get_engine()
    engine.update_foreshadowing_analyzer_config(
        trigger_interval=config.trigger_interval,
        auto_plant=config.auto_plant,
        auto_resolve=config.auto_resolve
    )
    return {"success": True, "config": engine.get_foreshadowing_analyzer_config()}


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


@app.get("/v1/users", tags=["Admin"])
async def list_users():
    """列出所有用户（角色）
    
    返回所有有记忆数据的角色列表，以及每个角色的记忆数量。
    用于管理和清理不再需要的角色数据。
    """
    engine = get_engine()
    users = engine.storage.list_users()
    
    result = []
    for user_id in users:
        memories = engine.get_all(user_id=user_id, limit=10000)
        result.append({
            "user_id": user_id,
            "memory_count": len(memories)
        })
    
    return {
        "users": result,
        "total": len(result)
    }


@app.post("/v1/config/reload", tags=["Admin"])
async def reload_config():
    """热更新配置
    
    重新加载 recall_data/config/api_keys.env 配置文件。
    修改 API Key 后调用此接口即可生效，无需重启服务。
    
    使用方法：
    1. 编辑 recall_data/config/api_keys.env 文件
    2. 调用此接口: curl -X POST http://localhost:18888/v1/config/reload
    """
    try:
        engine = reload_engine()
        stats = engine.get_stats()
        
        # 获取当前 embedding 模式
        embedding_info = "轻量模式" if stats.get('lightweight') else "完整/Hybrid模式"
        
        return {
            "success": True,
            "message": "配置已重新加载",
            "embedding_mode": embedding_info,
            "config_file": str(get_config_file_path())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新加载失败: {str(e)}")


@app.get("/v1/config", tags=["Admin"])
async def get_config():
    """获取当前配置信息
    
    显示配置文件路径和当前配置状态（敏感信息脱敏）
    """
    config_file = get_config_file_path()
    
    # 检查各种配置状态
    def mask_key(key: str) -> str:
        """脱敏显示 API Key"""
        if not key:
            return "未配置"
        if len(key) > 8:
            return key[:4] + '****' + key[-4:]
        return '****'
    
    # Embedding 配置
    embedding_key = os.environ.get('EMBEDDING_API_KEY', '')
    embedding_base = os.environ.get('EMBEDDING_API_BASE', '')
    embedding_model = os.environ.get('EMBEDDING_MODEL', '')
    embedding_dimension = os.environ.get('EMBEDDING_DIMENSION', '')
    embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', 'auto')
    
    # LLM 配置
    llm_key = os.environ.get('LLM_API_KEY', '')
    llm_base = os.environ.get('LLM_API_BASE', '')
    llm_model = os.environ.get('LLM_MODEL', '')
    
    return {
        "config_file": str(config_file),
        "config_file_exists": config_file.exists(),
        "embedding": {
            "api_key": mask_key(embedding_key),
            "api_base": embedding_base or "未配置",
            "model": embedding_model or "未配置",
            "dimension": embedding_dimension or "未配置",
            "mode": embedding_mode,
            "status": "已配置" if (embedding_key and embedding_base) else "未配置"
        },
        "llm": {
            "api_key": mask_key(llm_key),
            "api_base": llm_base or "未配置",
            "model": llm_model or "未配置",
            "status": "已配置" if llm_key else "未配置"
        },
        "hint": "编辑配置文件后调用 POST /v1/config/reload 热更新，测试连接 GET /v1/config/test"
    }


@app.get("/v1/config/test", tags=["Admin"])
async def test_connection():
    """测试 Embedding API 连接
    
    测试当前配置的 Embedding API 是否可以正常连接。
    会实际调用 API 生成一个测试向量来验证。
    
    使用方法：
    curl http://localhost:18888/v1/config/test
    
    返回：
    - success: true/false
    - message: 测试结果描述
    - backend: 当前使用的后端类型
    - model: 当前使用的模型
    - dimension: 向量维度
    - latency_ms: API 调用延迟（毫秒）
    """
    engine = get_engine()
    
    # 检查是否是轻量模式
    config = engine.embedding_config
    if engine.lightweight or not config or config.backend.value == "none":
        return {
            "success": True,
            "message": "轻量模式无需测试 API 连接",
            "backend": "none",
            "model": None,
            "dimension": None,
            "latency_ms": 0
        }
    
    # 从引擎获取当前配置
    backend_type = config.backend.value if config.backend else "unknown"
    model = config.api_model or config.local_model or "unknown"
    dimension = config.dimension
    
    # 获取 embedding 后端并测试
    try:
        # 实际测试 embedding 调用
        start_time = time.time()
        test_text = "Hello, this is a test."
        
        # 尝试获取 embedding
        if engine._vector_index and engine._vector_index.embedding_backend:
            embedding_backend = engine._vector_index.embedding_backend
            embedding = embedding_backend.encode(test_text)
            actual_dimension = len(embedding)
            elapsed_ms = (time.time() - start_time) * 1000
            
            return {
                "success": True,
                "message": f"API 连接成功！模型 {model} 工作正常",
                "backend": backend_type,
                "model": model,
                "dimension": actual_dimension,
                "latency_ms": round(elapsed_ms, 2)
            }
        else:
            return {
                "success": False,
                "message": "Embedding 后端未初始化（可能是轻量模式或索引未加载）",
                "backend": backend_type,
                "model": model,
                "dimension": dimension,
                "latency_ms": 0
            }
            
    except Exception as e:
        error_msg = str(e)
        
        # 友好的错误提示
        if "API key" in error_msg.lower() or "unauthorized" in error_msg.lower() or "401" in error_msg:
            friendly_msg = "API Key 无效或未配置"
        elif "connection" in error_msg.lower() or "network" in error_msg.lower():
            friendly_msg = "网络连接失败，请检查网络或 API 地址"
        elif "model" in error_msg.lower() or "404" in error_msg:
            friendly_msg = "模型不存在或不可用"
        else:
            friendly_msg = f"连接失败: {error_msg}"
        
        # 尝试获取当前配置信息用于错误响应
        try:
            cfg = engine.embedding_config
            current_backend = cfg.backend.value if cfg and cfg.backend else 'unknown'
            current_model = (cfg.api_model or cfg.local_model) if cfg else None
        except:
            current_backend = os.environ.get('RECALL_EMBEDDING_MODE', 'auto')
            current_model = None
        
        return {
            "success": False,
            "message": friendly_msg,
            "error": error_msg,
            "backend": current_backend,
            "model": current_model,
            "dimension": None,
            "latency_ms": 0
        }


@app.get("/v1/config/test/llm", tags=["Admin"])
async def test_llm_connection():
    """测试 LLM API 连接
    
    测试当前配置的 LLM API 是否可以正常连接。
    会实际调用 API 生成一个简短回复来验证。
    
    使用方法：
    curl http://localhost:18888/v1/config/test/llm
    
    返回：
    - success: true/false
    - message: 测试结果描述
    - model: 当前配置的模型
    - latency_ms: API 调用延迟（毫秒）
    """
    # 获取 LLM 配置
    llm_api_key = os.environ.get('LLM_API_KEY', '')
    llm_api_base = os.environ.get('LLM_API_BASE', '')
    llm_model = os.environ.get('LLM_MODEL', 'gpt-3.5-turbo')
    
    # 如果没有 LLM_API_KEY，尝试使用 OPENAI_API_KEY
    if not llm_api_key:
        llm_api_key = os.environ.get('OPENAI_API_KEY', '')
    
    if not llm_api_key:
        return {
            "success": False,
            "message": "LLM API Key 未配置",
            "model": llm_model,
            "api_base": llm_api_base or "默认",
            "latency_ms": 0,
            "hint": "请在 api_keys.env 中设置 LLM_API_KEY 或 OPENAI_API_KEY"
        }
    
    try:
        from .utils.llm_client import LLMClient
        
        start_time = time.time()
        
        # 创建 LLM 客户端
        client = LLMClient(
            model=llm_model,
            api_key=llm_api_key,
            api_base=llm_api_base if llm_api_base else None,
            timeout=15.0,
            max_retries=1
        )
        
        # 发送简单的测试请求
        response = client.chat(
            messages=[{"role": "user", "content": "Say 'Hello' in one word."}],
            max_tokens=10,
            temperature=0
        )
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            "success": True,
            "message": f"LLM 连接成功！模型 {response.model} 工作正常",
            "model": response.model,
            "api_base": llm_api_base or "默认",
            "response": response.content[:50] if response.content else "",
            "latency_ms": round(elapsed_ms, 2),
            "usage": response.usage
        }
        
    except Exception as e:
        error_msg = str(e)
        
        # 友好的错误提示
        if "API key" in error_msg.lower() or "unauthorized" in error_msg.lower() or "401" in error_msg:
            friendly_msg = "API Key 无效或未授权"
        elif "connection" in error_msg.lower() or "network" in error_msg.lower():
            friendly_msg = "网络连接失败，请检查网络或 API 地址"
        elif "model" in error_msg.lower() or "404" in error_msg:
            friendly_msg = f"模型 {llm_model} 不存在或不可用"
        elif "timeout" in error_msg.lower():
            friendly_msg = "请求超时，请检查网络连接"
        else:
            friendly_msg = f"连接失败: {error_msg}"
        
        return {
            "success": False,
            "message": friendly_msg,
            "error": error_msg,
            "model": llm_model,
            "api_base": llm_api_base or "默认",
            "latency_ms": 0
        }


class ConfigUpdateRequest(BaseModel):
    """配置更新请求（统一使用 OpenAI 兼容格式）"""
    # Embedding 配置
    embedding_api_key: Optional[str] = Field(default=None, description="Embedding API Key")
    embedding_api_base: Optional[str] = Field(default=None, description="Embedding API 地址")
    embedding_model: Optional[str] = Field(default=None, description="Embedding 模型")
    embedding_dimension: Optional[int] = Field(default=None, description="向量维度")
    recall_embedding_mode: Optional[str] = Field(default=None, description="Embedding 模式")
    # LLM 配置
    llm_api_key: Optional[str] = Field(default=None, description="LLM API Key")
    llm_api_base: Optional[str] = Field(default=None, description="LLM API 地址")
    llm_model: Optional[str] = Field(default=None, description="LLM 模型")


@app.put("/v1/config", tags=["Admin"])
async def update_config(request: ConfigUpdateRequest):
    """更新配置文件
    
    更新 api_keys.env 中的配置项。只会更新请求中包含的非空字段。
    更新后会自动重新加载配置。
    
    使用方法：
    curl -X PUT http://localhost:18888/v1/config \\
         -H "Content-Type: application/json" \\
         -d '{"siliconflow_api_key": "sk-xxx", "llm_api_key": "sk-yyy"}'
    """
    config_file = get_config_file_path()
    
    # 读取当前配置
    current_config = {}
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    current_config[key.strip()] = value.strip()
    
    # 映射请求字段到配置键（统一使用 OpenAI 兼容格式）
    field_to_key = {
        'embedding_api_key': 'EMBEDDING_API_KEY',
        'embedding_api_base': 'EMBEDDING_API_BASE',
        'embedding_model': 'EMBEDDING_MODEL',
        'embedding_dimension': 'EMBEDDING_DIMENSION',
        'recall_embedding_mode': 'RECALL_EMBEDDING_MODE',
        'llm_api_key': 'LLM_API_KEY',
        'llm_api_base': 'LLM_API_BASE',
        'llm_model': 'LLM_MODEL',
    }
    
    # 更新配置
    updated_fields = []
    request_dict = request.model_dump(exclude_none=True)
    
    for field, config_key in field_to_key.items():
        if field in request_dict:
            value = request_dict[field]
            if value is not None:
                # 转换为字符串
                str_value = str(value) if not isinstance(value, str) else value
                current_config[config_key] = str_value
                # 同时更新环境变量
                os.environ[config_key] = str_value
                updated_fields.append(config_key)
    
    if not updated_fields:
        return {
            "success": False,
            "message": "没有提供需要更新的配置项"
        }
    
    # 写回配置文件（保留注释和格式）
    try:
        # 确保目录存在
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取原文件保留注释
        lines = []
        existing_keys = set()
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    original_line = line.rstrip('\n\r')
                    stripped = original_line.strip()
                    
                    if stripped and not stripped.startswith('#') and '=' in stripped:
                        key = stripped.split('=')[0].strip()
                        if key in current_config:
                            # 更新这行的值
                            lines.append(f"{key}={current_config[key]}")
                            existing_keys.add(key)
                        else:
                            lines.append(original_line)
                    else:
                        lines.append(original_line)
        
        # 添加新的配置项
        for key, value in current_config.items():
            if key not in existing_keys and key in SUPPORTED_CONFIG_KEYS:
                lines.append(f"{key}={value}")
        
        # 写入文件
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            if not lines[-1].endswith('\n'):
                f.write('\n')
        
        # 重新加载引擎配置
        try:
            reload_engine()
        except Exception as reload_err:
            # 配置已保存，但重新加载失败
            return {
                "success": True,
                "message": f"配置已保存，但重新加载失败: {str(reload_err)}",
                "updated_fields": updated_fields,
                "hint": "请手动重启服务或调用 POST /v1/config/reload"
            }
        
        return {
            "success": True,
            "message": "配置已更新并重新加载",
            "updated_fields": updated_fields
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")


@app.get("/v1/config/full", tags=["Admin"])
async def get_full_config():
    """获取完整配置信息（供插件使用）
    
    返回 Embedding 和 LLM 的完整配置状态，包括脱敏后的 API Key。
    专为 SillyTavern 插件设计。
    """
    def mask_key(key: str) -> str:
        """脱敏显示 API Key"""
        if not key:
            return ""
        if len(key) > 12:
            return key[:4] + '*' * 8 + key[-4:]
        elif len(key) > 4:
            return key[:2] + '*' * (len(key) - 2)
        return '****'
    
    def get_key_status(key: str) -> str:
        """获取 API Key 状态"""
        if not key:
            return "未配置"
        return "已配置"
    
    # Embedding 配置（统一使用 OpenAI 兼容格式）
    embedding_key = os.environ.get('EMBEDDING_API_KEY', '')
    
    embedding_config = {
        "api_key": mask_key(embedding_key),
        "api_key_status": get_key_status(embedding_key),
        "api_base": os.environ.get('EMBEDDING_API_BASE', ''),
        "model": os.environ.get('EMBEDDING_MODEL', ''),
        "dimension": os.environ.get('EMBEDDING_DIMENSION', '1024'),
        "mode": os.environ.get('RECALL_EMBEDDING_MODE', 'auto'),
    }
    
    # LLM 配置
    llm_key = os.environ.get('LLM_API_KEY', '')
    llm_config = {
        "api_key": mask_key(llm_key),
        "api_key_status": get_key_status(llm_key),
        "api_base": os.environ.get('LLM_API_BASE', ''),
        "model": os.environ.get('LLM_MODEL', 'gpt-3.5-turbo'),
    }
    
    return {
        "embedding": embedding_config,
        "llm": llm_config,
        "config_file": str(get_config_file_path()),
    }


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
