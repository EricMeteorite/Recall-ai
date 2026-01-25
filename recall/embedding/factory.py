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


def create_embedding_backend(config: Optional[EmbeddingConfig] = None) -> EmbeddingBackend:
    """创建 Embedding 后端
    
    Args:
        config: Embedding 配置，为 None 时使用默认 Local 模式
    
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
        backend = LocalEmbeddingBackend(config)
        if not backend.is_available:
            _safe_print("[Embedding] 警告: sentence-transformers 未安装，回退到 Lite 模式")
            return NoneBackend(EmbeddingConfig.lite())
        return backend
    
    elif backend_type in (EmbeddingBackendType.OPENAI, EmbeddingBackendType.SILICONFLOW, EmbeddingBackendType.CUSTOM):
        backend = APIEmbeddingBackend(config)
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
    available = ["none"]  # Lite 模式总是可用
    
    # 检查本地后端
    try:
        import sentence_transformers
        available.append("local")
    except ImportError:
        pass
    
    # 检查 API 后端（只要有 openai 包即可）
    try:
        import openai
        import os
        
        if os.environ.get('OPENAI_API_KEY'):
            available.append("openai")
        
        if os.environ.get('SILICONFLOW_API_KEY'):
            available.append("siliconflow")
        
        # 检查自定义配置
        if os.environ.get('EMBEDDING_API_KEY') and os.environ.get('EMBEDDING_API_BASE'):
            available.append("custom")
        
        # 如果有 openai 包，就可以配置使用
        if "openai" not in available and "siliconflow" not in available:
            available.append("openai")  # 可配置
            available.append("siliconflow")  # 可配置
            available.append("custom")  # 可配置
    except ImportError:
        pass
    
    return available


def auto_select_backend() -> EmbeddingConfig:
    """自动选择最佳可用后端
    
    优先级：
    1. 环境变量 RECALL_EMBEDDING_MODE 指定
    2. 自定义 API（用户明确配置）
    3. 硅基流动（国内快）
    4. OpenAI
    5. 本地模型
    6. Lite 模式
    """
    import os
    
    # 检查是否通过环境变量指定模式
    mode = os.environ.get('RECALL_EMBEDDING_MODE', '').lower()
    
    if mode == 'none':
        _safe_print("[Embedding] 使用: Lite 模式（仅关键词搜索）")
        return EmbeddingConfig.lite()
    
    if mode == 'custom':
        api_key = os.environ.get('EMBEDDING_API_KEY', '')
        api_base = os.environ.get('EMBEDDING_API_BASE', '')
        api_model = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
        dimension = int(os.environ.get('EMBEDDING_DIMENSION', '1536'))
        
        if api_key and api_base:
            _safe_print(f"[Embedding] 使用: 自定义 Cloud API ({api_base})")
            return EmbeddingConfig.cloud_custom(api_key, api_base, api_model, dimension)
        else:
            _safe_print("[Embedding] 警告: 自定义 API 配置不完整，回退到 Lite 模式")
            return EmbeddingConfig.lite()
    
    if mode == 'siliconflow':
        api_key = os.environ.get('SILICONFLOW_API_KEY', '')
        model = os.environ.get('SILICONFLOW_MODEL', 'BAAI/bge-large-zh-v1.5')
        if api_key:
            _safe_print(f"[Embedding] 使用: 硅基流动 Cloud API (模型: {model})")
            return EmbeddingConfig.cloud_siliconflow(api_key, model=model)
        else:
            _safe_print("[Embedding] 警告: SILICONFLOW_API_KEY 未设置，回退到 Lite 模式")
            return EmbeddingConfig.lite()
    
    if mode == 'openai':
        api_key = os.environ.get('OPENAI_API_KEY', '')
        api_base = os.environ.get('OPENAI_API_BASE', '')  # 支持自定义 base
        model = os.environ.get('OPENAI_MODEL', 'text-embedding-3-small')
        if api_key:
            _safe_print(f"[Embedding] 使用: OpenAI Cloud API (模型: {model})" + (f" ({api_base})" if api_base else ""))
            return EmbeddingConfig.cloud_openai(api_key, api_base if api_base else None, model=model)
        else:
            _safe_print("[Embedding] 警告: OPENAI_API_KEY 未设置，回退到 Lite 模式")
            return EmbeddingConfig.lite()
    
    if mode == 'local':
        try:
            import sentence_transformers
            _safe_print("[Embedding] 使用: Local 模式（本地模型）")
            return EmbeddingConfig.local()
        except ImportError:
            _safe_print("[Embedding] 警告: sentence-transformers 未安装，回退到 Lite 模式")
            return EmbeddingConfig.lite()
    
    # 未指定模式，自动检测
    # 优先检查自定义配置
    if os.environ.get('EMBEDDING_API_KEY') and os.environ.get('EMBEDDING_API_BASE'):
        api_key = os.environ['EMBEDDING_API_KEY']
        api_base = os.environ['EMBEDDING_API_BASE']
        api_model = os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small')
        dimension = int(os.environ.get('EMBEDDING_DIMENSION', '1536'))
        _safe_print(f"[Embedding] 自动选择: 自定义 Cloud API ({api_base})")
        return EmbeddingConfig.cloud_custom(api_key, api_base, api_model, dimension)
    
    # 然后 Cloud API（内存低）
    if os.environ.get('SILICONFLOW_API_KEY'):
        model = os.environ.get('SILICONFLOW_MODEL', 'BAAI/bge-large-zh-v1.5')
        _safe_print(f"[Embedding] 自动选择: 硅基流动 Cloud API (模型: {model})")
        return EmbeddingConfig.cloud_siliconflow(
            os.environ['SILICONFLOW_API_KEY'],
            model=model
        )
    
    if os.environ.get('OPENAI_API_KEY'):
        api_base = os.environ.get('OPENAI_API_BASE', '')
        model = os.environ.get('OPENAI_MODEL', 'text-embedding-3-small')
        _safe_print(f"[Embedding] 自动选择: OpenAI Cloud API (模型: {model})" + (f" ({api_base})" if api_base else ""))
        return EmbeddingConfig.cloud_openai(
            os.environ['OPENAI_API_KEY'],
            api_base if api_base else None,
            model=model
        )
    
    # 其次本地
    try:
        import sentence_transformers
        _safe_print("[Embedding] 自动选择: Local 模式（本地模型）")
        return EmbeddingConfig.local()
    except ImportError:
        pass
    
    # 最后 Lite
    _safe_print("[Embedding] 自动选择: Lite 模式（无语义搜索）")
    return EmbeddingConfig.lite()
