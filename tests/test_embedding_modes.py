#!/usr/bin/env python3
"""测试三种 Embedding 模式

运行方式:
    python test_embedding_modes.py
"""

import os
import sys

def test_lightweight_mode():
    """测试轻量模式"""
    print("=" * 50)
    print("测试 1: 轻量模式")
    print("=" * 50)
    
    from recall.embedding import EmbeddingConfig, create_embedding_backend
    from recall.embedding.base import EmbeddingBackendType
    
    config = EmbeddingConfig.lightweight()
    assert config.backend == EmbeddingBackendType.NONE
    
    backend = create_embedding_backend(config)
    assert backend.dimension == 0
    
    # 轻量模式调用 encode 应该抛出错误
    try:
        backend.encode("test")
        assert False, "应该抛出 RuntimeError"
    except RuntimeError as e:
        assert "轻量模式不支持向量编码" in str(e)
    
    print("[OK] Lightweight mode config correct")
    print("[OK] Backend dimension is 0")
    print("[OK] Encode correctly throws error")
    print()


def test_hybrid_mode():
    """测试 Hybrid 模式（需要 API key）"""
    print("=" * 50)
    print("测试 2: Hybrid 模式")
    print("=" * 50)
    
    from recall.embedding import EmbeddingConfig, create_embedding_backend
    from recall.embedding.base import EmbeddingBackendType
    
    # 测试 OpenAI 配置
    config = EmbeddingConfig.hybrid_openai("sk-test")
    assert config.backend == EmbeddingBackendType.OPENAI
    assert config.api_model == "text-embedding-3-small"
    print("[OK] OpenAI config correct")
    
    # 测试硅基流动配置
    config = EmbeddingConfig.hybrid_siliconflow("sf-test")
    assert config.backend == EmbeddingBackendType.SILICONFLOW
    assert config.api_model == "BAAI/bge-large-zh-v1.5"
    print("[OK] SiliconFlow config correct")
    
    # 如果有真实 API key，测试实际调用
    if os.environ.get('OPENAI_API_KEY'):
        config = EmbeddingConfig.hybrid_openai(os.environ['OPENAI_API_KEY'])
        backend = create_embedding_backend(config)
        vec = backend.encode("你好世界")
        print(f"[OK] OpenAI actual call succeeded, vector dim: {vec.shape}")
    
    if os.environ.get('SILICONFLOW_API_KEY'):
        config = EmbeddingConfig.hybrid_siliconflow(os.environ['SILICONFLOW_API_KEY'])
        backend = create_embedding_backend(config)
        vec = backend.encode("你好世界")
        print(f"[OK] SiliconFlow actual call succeeded, vector dim: {vec.shape}")
    
    print()


def test_full_mode():
    """测试完整模式（需要 sentence-transformers）"""
    print("=" * 50)
    print("测试 3: 完整模式")
    print("=" * 50)
    
    from recall.embedding import EmbeddingConfig, create_embedding_backend
    from recall.embedding.base import EmbeddingBackendType
    
    config = EmbeddingConfig.full()
    assert config.backend == EmbeddingBackendType.LOCAL
    print("[OK] Full mode config correct")
    
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
        config = EmbeddingConfig.lightweight()
        vi = VectorIndex(tmpdir, embedding_config=config)
        
        assert vi.enabled == False
        assert vi.search("test") == []
        print("[OK] Vector index correctly disabled in lightweight mode")
    
    print()


def main():
    print()
    print("=== Recall AI Embedding Mode Test ===")
    print("================================")
    print()
    
    tests = [
        test_lightweight_mode,
        test_hybrid_mode,
        test_full_mode,
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
