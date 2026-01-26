#!/usr/bin/env python3
"""测试三种 Embedding 模式

运行方式:
    python test_embedding_modes.py
"""

import os
import sys

def test_lite_mode():
    """测试 Lite 模式"""
    print("=" * 50)
    print("测试 1: Lite 模式")
    print("=" * 50)
    
    from recall.embedding import EmbeddingConfig, create_embedding_backend
    from recall.embedding.base import EmbeddingBackendType
    
    config = EmbeddingConfig.lite()  # 也可以用 lightweight()
    assert config.backend == EmbeddingBackendType.NONE
    
    backend = create_embedding_backend(config)
    assert backend.dimension == 0
    
    # Lite 模式调用 encode 应该抛出错误
    try:
        backend.encode("test")
        assert False, "应该抛出 RuntimeError"
    except RuntimeError as e:
        assert "Lite 模式不支持向量编码" in str(e) or "轻量模式不支持向量编码" in str(e)
    
    print("[OK] Lite mode config correct")
    print("[OK] Backend dimension is 0")
    print("[OK] Encode correctly throws error")
    print()


def test_cloud_mode():
    """测试 Cloud 模式（需要 API key）"""
    print("=" * 50)
    print("测试 2: Cloud 模式")
    print("=" * 50)
    
    from recall.embedding import EmbeddingConfig, create_embedding_backend
    from recall.embedding.base import EmbeddingBackendType
    
    # 测试 OpenAI 配置
    config = EmbeddingConfig.cloud_openai("sk-test")  # 也可以用 hybrid_openai()
    assert config.backend == EmbeddingBackendType.OPENAI
    assert config.api_model == "text-embedding-3-small"
    print("[OK] OpenAI config correct")
    
    # 测试硅基流动配置
    config = EmbeddingConfig.cloud_siliconflow("sf-test")  # 也可以用 hybrid_siliconflow()
    assert config.backend == EmbeddingBackendType.SILICONFLOW
    assert config.api_model == "BAAI/bge-large-zh-v1.5"
    print("[OK] SiliconFlow config correct")
    
    # 如果有真实 API key，测试实际调用（使用统一的 EMBEDDING_API_KEY）
    if os.environ.get('EMBEDDING_API_KEY') and os.environ.get('EMBEDDING_API_BASE'):
        config = EmbeddingConfig.cloud_custom(
            os.environ['EMBEDDING_API_KEY'],
            os.environ['EMBEDDING_API_BASE'],
            os.environ.get('EMBEDDING_MODEL', 'text-embedding-3-small'),
            int(os.environ.get('EMBEDDING_DIMENSION', '1024'))
        )
        backend = create_embedding_backend(config)
        vec = backend.encode("你好世界")
        print(f"[OK] Cloud API actual call succeeded, vector dim: {vec.shape}")
    
    print()


def test_local_mode():
    """测试 Local 模式（需要 sentence-transformers）"""
    print("=" * 50)
    print("测试 3: Local 模式")
    print("=" * 50)
    
    from recall.embedding import EmbeddingConfig, create_embedding_backend
    from recall.embedding.base import EmbeddingBackendType
    
    config = EmbeddingConfig.local()  # 也可以用 full()
    assert config.backend == EmbeddingBackendType.LOCAL
    print("[OK] Local mode config correct")
    
    try:
        import sentence_transformers
        backend = create_embedding_backend(config)
        vec = backend.encode("你好世界")
        print(f"[OK] Local model loaded, vector dim: {vec.shape}")
    except ImportError:
        print("! sentence-transformers 未安装，跳过实际测试")
    
    print()


def test_auto_select():
    """测试自动选择"""
    print("=" * 50)
    print("测试 4: 自动选择后端")
    print("=" * 50)
    
    from recall.embedding.factory import auto_select_backend
    
    config = auto_select_backend()
    print(f"[OK] Auto select result: {config.backend.value}")
    print()


def test_vector_index_disabled():
    """测试向量索引禁用模式"""
    print("=" * 50)
    print("测试 5: 向量索引禁用")
    print("=" * 50)
    
    import tempfile
    from recall.embedding import EmbeddingConfig
    from recall.index.vector_index import VectorIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = EmbeddingConfig.lite()  # 也可以用 lightweight()
        vi = VectorIndex(tmpdir, embedding_config=config)
        
        assert vi.enabled == False
        assert vi.search("test") == []
        print("[OK] Vector index correctly disabled in lite mode")
    
    print()


def main():
    print()
    print("=== Recall AI Embedding Mode Test ===")
    print("================================")
    print()
    
    tests = [
        test_lite_mode,
        test_cloud_mode,
        test_local_mode,
        test_auto_select,
        test_vector_index_disabled,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__} failed: {e}")
            failed += 1
    
    print()
    print("=" * 50)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
