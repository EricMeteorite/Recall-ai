"""Embedding 后端工厂"""

from typing import List, Optional

from .base import EmbeddingBackend, EmbeddingConfig, EmbeddingBackendType, NoneBackend
from .local_backend import LocalEmbeddingBackend
from .api_backend import APIEmbeddingBackend


def create_embedding_backend(config: Optional[EmbeddingConfig] = None) -> EmbeddingBackend:
    """创建 Embedding 后端
    
    Args:
        config: Embedding 配置，为 None 时使用默认完整模式
    
    Returns:
        对应的 EmbeddingBackend 实例
    
    Examples:
        # 完整模式（默认）
        backend = create_embedding_backend()
        
        # 轻量模式
        backend = create_embedding_backend(EmbeddingConfig.lightweight())
        
        # Hybrid 模式 - OpenAI
        backend = create_embedding_backend(
            EmbeddingConfig.hybrid_openai(api_key="sk-xxx")
        )
        
        # Hybrid 模式 - 硅基流动
        backend = create_embedding_backend(
            EmbeddingConfig.hybrid_siliconflow(api_key="sf-xxx")
        )
    """
    if config is None:
        config = EmbeddingConfig.full()
    
    backend_type = config.backend
    
    if backend_type == EmbeddingBackendType.NONE:
        return NoneBackend(config)
    
    elif backend_type == EmbeddingBackendType.LOCAL:
        backend = LocalEmbeddingBackend(config)
        if not backend.is_available:
            print("[Embedding] 警告: sentence-transformers 未安装，回退到轻量模式")
            return NoneBackend(EmbeddingConfig.lightweight())
        return backend
    
    elif backend_type in (EmbeddingBackendType.OPENAI, EmbeddingBackendType.SILICONFLOW):
        backend = APIEmbeddingBackend(config)
        if not backend.is_available:
            print(f"[Embedding] 警告: {backend_type.value} API key 未配置，回退到轻量模式")
            return NoneBackend(EmbeddingConfig.lightweight())
        return backend
    
    else:
        raise ValueError(f"未知的 Embedding 后端类型: {backend_type}")


def get_available_backends() -> List[str]:
    """获取可用的 Embedding 后端列表
    
    Returns:
        可用后端名称列表
    """
    available = ["none"]  # 轻量模式总是可用
    
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
        
        # 如果有 openai 包，就可以配置使用
        if "openai" not in available and "siliconflow" not in available:
            available.append("openai")  # 可配置
            available.append("siliconflow")  # 可配置
    except ImportError:
        pass
    
    return available


def auto_select_backend() -> EmbeddingConfig:
    """自动选择最佳可用后端
    
    优先级：
    1. 环境变量 RECALL_EMBEDDING_MODE 指定
    2. 硅基流动（国内快）
    3. OpenAI
    4. 本地模型
    5. 轻量模式
    """
    import os
    
    # 检查是否通过环境变量指定模式
    mode = os.environ.get('RECALL_EMBEDDING_MODE', '').lower()
    
    if mode == 'none':
        print("[Embedding] 使用: 轻量模式（仅关键词搜索）")
        return EmbeddingConfig.lightweight()
    
    if mode == 'siliconflow':
        api_key = os.environ.get('SILICONFLOW_API_KEY', '')
        if api_key:
            print("[Embedding] 使用: 硅基流动 API")
            return EmbeddingConfig.hybrid_siliconflow(api_key)
        else:
            print("[Embedding] 警告: SILICONFLOW_API_KEY 未设置，回退到轻量模式")
            return EmbeddingConfig.lightweight()
    
    if mode == 'openai':
        api_key = os.environ.get('OPENAI_API_KEY', '')
        if api_key:
            print("[Embedding] 使用: OpenAI API")
            return EmbeddingConfig.hybrid_openai(api_key)
        else:
            print("[Embedding] 警告: OPENAI_API_KEY 未设置，回退到轻量模式")
            return EmbeddingConfig.lightweight()
    
    if mode == 'local':
        try:
            import sentence_transformers
            print("[Embedding] 使用: 本地模型")
            return EmbeddingConfig.full()
        except ImportError:
            print("[Embedding] 警告: sentence-transformers 未安装，回退到轻量模式")
            return EmbeddingConfig.lightweight()
    
    # 未指定模式，自动检测
    # 优先 API（内存低）
    if os.environ.get('SILICONFLOW_API_KEY'):
        print("[Embedding] 自动选择: 硅基流动 API")
        return EmbeddingConfig.hybrid_siliconflow(
            os.environ['SILICONFLOW_API_KEY']
        )
    
    if os.environ.get('OPENAI_API_KEY'):
        print("[Embedding] 自动选择: OpenAI API")
        return EmbeddingConfig.hybrid_openai(
            os.environ['OPENAI_API_KEY']
        )
    
    # 其次本地
    try:
        import sentence_transformers
        print("[Embedding] 自动选择: 本地模型")
        return EmbeddingConfig.full()
    except ImportError:
        pass
    
    # 最后轻量
    print("[Embedding] 自动选择: 轻量模式（无语义搜索）")
    return EmbeddingConfig.lightweight()
