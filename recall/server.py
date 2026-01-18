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

# 支持的配置项
SUPPORTED_CONFIG_KEYS = {
    # API Keys
    'SILICONFLOW_API_KEY',
    'OPENAI_API_KEY',
    'EMBEDDING_API_KEY',
    # API URLs
    'OPENAI_API_BASE',
    'EMBEDDING_API_BASE',
    # Model settings - 硅基流动
    'SILICONFLOW_MODEL',
    # Model settings - OpenAI
    'OPENAI_MODEL',
    # Model settings - 自定义
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMENSION',
    # Mode
    'RECALL_EMBEDDING_MODE',
}


def get_config_file_path() -> Path:
    """获取配置文件路径"""
    # 优先使用环境变量指定的数据目录
    data_root = os.environ.get('RECALL_DATA_ROOT', './recall_data')
    return Path(data_root) / 'config' / 'api_keys.env'


def get_default_config_content() -> str:
    """获取默认配置文件内容"""
    return '''# ============================================
# Recall API 配置文件
# ============================================
# 
# 使用方法：
# 1. 直接用文本编辑器打开此文件
# 2. 设置 RECALL_EMBEDDING_MODE（必须！）
# 3. 根据选择的模式填写对应的 API 配置
# 4. 保存文件
# 5. 热更新: curl -X POST http://localhost:18888/v1/config/reload
# 6. 测试连接: curl http://localhost:18888/v1/config/test
#
# ============================================


# ============================================
# 【必须】选择 Embedding 模式
# ============================================
# 可选值：
#   none       - 轻量模式，无语义搜索，内存最低（~100MB）
#   siliconflow - 硅基流动 API（推荐国内用户）
#   openai     - OpenAI API（或中转站）
#   custom     - 自定义 API（Azure/Ollama/Gemini等）
#   local      - 本地模型，完全离线，内存最高（~1.5GB）
#
# 示例：使用硅基流动
# RECALL_EMBEDDING_MODE=siliconflow
#
# 示例：使用自定义API（如Gemini中转站）
# RECALL_EMBEDDING_MODE=custom
#
RECALL_EMBEDDING_MODE=none


# ============================================
# 方式一：硅基流动（推荐国内用户，便宜快速）
# ============================================
# 设置 RECALL_EMBEDDING_MODE=siliconflow 后填写以下配置
# 获取地址：https://cloud.siliconflow.cn/
SILICONFLOW_API_KEY=
# 模型选择（默认 BAAI/bge-large-zh-v1.5）
# 可选: BAAI/bge-large-zh-v1.5, BAAI/bge-m3, BAAI/bge-large-en-v1.5
SILICONFLOW_MODEL=BAAI/bge-large-zh-v1.5


# ============================================
# 方式二：OpenAI（支持官方和中转站）
# ============================================
# 设置 RECALL_EMBEDDING_MODE=openai 后填写以下配置
# 获取地址：https://platform.openai.com/
OPENAI_API_KEY=
# API 地址（默认官方，可改为中转站地址，不要带尾部斜杠）
OPENAI_API_BASE=
# 模型选择（默认 text-embedding-3-small）
# 可选: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
OPENAI_MODEL=text-embedding-3-small


# ============================================
# 方式三：自定义 API（Azure/Ollama/Gemini等）
# ============================================
# 设置 RECALL_EMBEDDING_MODE=custom 后填写以下配置
# 适用于：Azure OpenAI、本地Ollama、Gemini中转站、其他OpenAI兼容服务
# 注意：必须同时填写 KEY、BASE、MODEL、DIMENSION 四项
#
# 示例（Gemini中转站）：
# EMBEDDING_API_KEY=sk-your-key
# EMBEDDING_API_BASE=https://your-proxy.com/v1
# EMBEDDING_MODEL=gemini-embedding-exp-03-07
# EMBEDDING_DIMENSION=768
#
EMBEDDING_API_KEY=
EMBEDDING_API_BASE=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=1536


# ============================================
# 常用 Embedding 模型参考
# ============================================
# 
# OpenAI:
#   text-embedding-3-small   维度:1536  推荐,性价比高
#   text-embedding-3-large   维度:3072  精度更高
#   text-embedding-ada-002   维度:1536  旧版本
# 
# 硅基流动:
#   BAAI/bge-large-zh-v1.5   维度:1024  中文推荐
#   BAAI/bge-m3              维度:1024  多语言
#   BAAI/bge-large-en-v1.5   维度:1024  英文
#
# Ollama (本地):
#   nomic-embed-text         维度:768
#   mxbai-embed-large        维度:1024
#
# Gemini (通过中转站):
#   gemini-embedding-exp-03-07  维度:768
#   text-embedding-004          维度:768
#
# ============================================
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
    
    # API Keys
    siliconflow_key = os.environ.get('SILICONFLOW_API_KEY', '')
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    custom_key = os.environ.get('EMBEDDING_API_KEY', '')
    
    # URLs
    openai_base = os.environ.get('OPENAI_API_BASE', '')
    custom_base = os.environ.get('EMBEDDING_API_BASE', '')
    
    # Model settings - 新增模型配置
    siliconflow_model = os.environ.get('SILICONFLOW_MODEL', 'BAAI/bge-large-zh-v1.5')
    openai_model = os.environ.get('OPENAI_MODEL', 'text-embedding-3-small')
    custom_model = os.environ.get('EMBEDDING_MODEL', '')
    custom_dimension = os.environ.get('EMBEDDING_DIMENSION', '')
    
    # Mode
    embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', 'auto')
    
    return {
        "config_file": str(config_file),
        "config_file_exists": config_file.exists(),
        "embedding_mode": embedding_mode,
        "providers": {
            "siliconflow": {
                "api_key": mask_key(siliconflow_key),
                "model": siliconflow_model,
                "status": "已配置" if siliconflow_key else "未配置"
            },
            "openai": {
                "api_key": mask_key(openai_key),
                "api_base": openai_base or "默认 (api.openai.com)",
                "model": openai_model,
                "status": "已配置" if openai_key else "未配置"
            },
            "custom": {
                "api_key": mask_key(custom_key),
                "api_base": custom_base or "未配置",
                "model": custom_model or "未配置",
                "dimension": custom_dimension or "未配置",
                "status": "已配置" if (custom_key and custom_base) else "未配置"
            }
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
