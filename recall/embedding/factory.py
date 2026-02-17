"""Embedding 后端工厂"""

from typing import List, Optional

from .base import EmbeddingBackend, EmbeddingConfig, EmbeddingBackendType, NoneBackend
from .local_backend import LocalEmbeddingBackend
from .api_backend import APIEmbeddingBackend


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def create_embedding_backend(config: Optional[EmbeddingConfig] = None, cache_dir: str = None) -> EmbeddingBackend:
    """创建 Embedding 后端
    
    Args:
        config: Embedding 配置，为 None 时使用默认 Local 模式
        cache_dir: 持久化缓存目录，用于存储 embedding 缓存以减少 API 调用
    
    Returns:
        对应的 EmbeddingBackend 实例
    
    Examples:
        # Local 模式（默认，本地模型）
        backend = create_embedding_backend()
        
        # Lite 模式（禁用向量）
        backend = create_embedding_backend(EmbeddingConfig.lite())
        
        # Cloud 模式 - OpenAI
        backend = create_embedding_backend(
            EmbeddingConfig.cloud_openai(api_key="sk-xxx")
        )
        
        # Cloud 模式 - 硅基流动
        backend = create_embedding_backend(
            EmbeddingConfig.cloud_siliconflow(api_key="sf-xxx")
        )
        
        # Cloud 模式 - 自定义 API（中转站等）
        backend = create_embedding_backend(
            EmbeddingConfig.cloud_custom(
                api_key="sk-xxx",
                api_base="https://your-proxy.com/v1",
                api_model="text-embedding-3-small",
                dimension=1536
            )
        )
    """
    if config is None:
        config = EmbeddingConfig.local()
    
    backend_type = config.backend
    
    if backend_type == EmbeddingBackendType.NONE:
        return NoneBackend(config)
    
    elif backend_type == EmbeddingBackendType.LOCAL:
        backend = LocalEmbeddingBackend(config, cache_dir=cache_dir)
        if not backend.is_available:
            _safe_print("[Embedding] 警告: sentence-transformers 未安装，回退到 Lite 模式")
            return NoneBackend(EmbeddingConfig.lite())
        return backend
    
    elif backend_type in (EmbeddingBackendType.OPENAI, EmbeddingBackendType.SILICONFLOW, EmbeddingBackendType.CUSTOM):
        backend = APIEmbeddingBackend(config, cache_dir=cache_dir)
        if not backend.is_available:
            _safe_print(f"[Embedding] 警告: {backend_type.value} API key 未配置，回退到 Lite 模式")
            return NoneBackend(EmbeddingConfig.lite())
        return backend
    
    else:
        raise ValueError(f"未知的 Embedding 后端类型: {backend_type}")


def get_available_backends() -> List[str]:
    """获取可用的 Embedding 后端列表
    
    Returns:
        可用后端名称列表
    """
    import os
    
    available = ["none"]  # Lite 模式总是可用
    
    # 检查本地后端
    try:
        import sentence_transformers
        available.append("local")
    except ImportError:
        pass
    
    # 检查 API 后端（使用统一的 EMBEDDING_* 配置）
    try:
        import openai
        
        # 只检查统一的 EMBEDDING_API_KEY 和 EMBEDDING_API_BASE
        if os.environ.get('EMBEDDING_API_KEY') and os.environ.get('EMBEDDING_API_BASE'):
            available.append("api")  # 统一的 API 后端
        else:
            # 如果有 openai 包但未配置，标记为可配置
            available.append("api (未配置)")
    except ImportError:
        pass
    
    return available


def auto_select_backend() -> EmbeddingConfig:
    """自动选择最佳可用后端
    
    优先级：
    1. 环境变量 RECALL_EMBEDDING_MODE 指定模式
    2. EMBEDDING_API_KEY + EMBEDDING_API_BASE 配置（Cloud API）
    3. 本地模型（sentence-transformers）
    4. Lite 模式（仅关键词搜索）
    
    配置变量说明（全部使用 server.py 定义的标准配置名）：
    - RECALL_EMBEDDING_MODE: 模式选择 (auto/api/local/none)
    - EMBEDDING_API_KEY: API 密钥
    - EMBEDDING_API_BASE: API 地址（如 https://api.siliconflow.cn/v1）
    - EMBEDDING_MODEL: 模型名称
    - EMBEDDING_DIMENSION: 向量维度
    """
    import os
    
    # 获取统一的配置项
    mode = os.environ.get('RECALL_EMBEDDING_MODE', '').lower()
    api_key = os.environ.get('EMBEDDING_API_KEY', '')
    api_base = os.environ.get('EMBEDDING_API_BASE', '')
    api_model = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
    dimension_str = os.environ.get('EMBEDDING_DIMENSION', '')
    
    if dimension_str.strip():
        try:
            dimension = int(dimension_str)
        except ValueError:
            dimension = None
    else:
        dimension = None
    
    # 根据模式选择后端
    if mode == 'none':
        _safe_print("[Embedding] 使用: Lite 模式（仅关键词搜索）")
        return EmbeddingConfig.lite()
    
    if mode == 'local':
        try:
            import sentence_transformers
            _safe_print("[Embedding] 使用: Local 模式（本地模型）")
            return EmbeddingConfig.local()
        except ImportError:
            _safe_print("[Embedding] 警告: sentence-transformers 未安装，回退到 Lite 模式")
            return EmbeddingConfig.lite()
    
    if mode == 'api':
        if api_key and api_base:
            _safe_print(f"[Embedding] 使用: Cloud API ({api_base}, 模型: {api_model})")
            return EmbeddingConfig.cloud_custom(api_key, api_base, api_model, dimension)
        else:
            _safe_print("[Embedding] 警告: EMBEDDING_API_KEY 或 EMBEDDING_API_BASE 未设置，回退到 Lite 模式")
            return EmbeddingConfig.lite()
    
    # mode == 'auto' 或未指定：自动检测最佳后端
    
    # 优先检查 Cloud API 配置（低内存占用）
    if api_key and api_base:
        _safe_print(f"[Embedding] 自动选择: Cloud API ({api_base}, 模型: {api_model})")
        return EmbeddingConfig.cloud_custom(api_key, api_base, api_model, dimension)
    
    # 其次检查本地模型
    try:
        import sentence_transformers
        _safe_print("[Embedding] 自动选择: Local 模式（本地模型）")
        return EmbeddingConfig.local()
    except ImportError:
        pass
    
    # 最后回退到 Lite 模式
    _safe_print("[Embedding] 自动选择: Lite 模式（无语义搜索）")
    return EmbeddingConfig.lite()
