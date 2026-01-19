"""语义去重功能测试（无pytest依赖）"""

import os
import sys
import tempfile
import shutil
import traceback

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recall.processor.context_tracker import ContextTracker, ContextType, PersistentContext
from recall.processor.foreshadowing import ForeshadowingTracker, Foreshadowing, ForeshadowingStatus


class MockEmbeddingBackend:
    """模拟Embedding后端，用于测试"""
    
    def __init__(self):
        # 预定义一些文本和它们的"伪向量"
        self.vectors = {
            # 相似的文本使用相似的向量
            "用户失去了左臂": [0.9, 0.1, 0.0, 0.0],
            "用户的左手臂被截断": [0.85, 0.15, 0.05, 0.0],  # 与上面高度相似
            "用户有一把剑": [0.1, 0.9, 0.0, 0.0],  # 完全不同
            "明天要去森林探险": [0.0, 0.0, 0.9, 0.1],
            "计划明天进入森林": [0.05, 0.0, 0.85, 0.15],  # 与上面相似
            "约定下周见面": [0.0, 0.1, 0.0, 0.9],  # 不同
        }
    
    def embed(self, texts):
        """返回伪向量"""
        result = []
        for text in texts:
            if text in self.vectors:
                result.append(self.vectors[text])
            else:
                # 未知文本返回零向量
                result.append([0.0, 0.0, 0.0, 0.0])
        return result


def test_context_tracker_exact_match():
    """测试ContextTracker完全相同的内容去重"""
    temp_dir = tempfile.mkdtemp()
    try:
        tracker = ContextTracker(
            storage_dir=temp_dir,
            llm_client=None,
            embedding_backend=MockEmbeddingBackend()
        )
        
        ctx1 = tracker.add("用户失去了左臂", ContextType.CHARACTER_TRAIT, "test_user")
        initial_use_count = ctx1.use_count
        
        ctx2 = tracker.add("用户失去了左臂", ContextType.CHARACTER_TRAIT, "test_user")
        
        # 应该返回同一个对象
        assert ctx1.id == ctx2.id, f"完全相同的内容应该合并，但得到不同ID: {ctx1.id} vs {ctx2.id}"
        # 使用次数应该增加1（从初始值0变为1）
        assert ctx2.use_count == initial_use_count + 1, f"使用次数应该增加1，但得到: {ctx2.use_count}"
        
        print("✓ ContextTracker完全匹配去重测试通过")
    finally:
        shutil.rmtree(temp_dir)


def test_context_tracker_semantic_similar():
    """测试ContextTracker语义相似内容去重"""
    temp_dir = tempfile.mkdtemp()
    try:
        # 设置低阈值以便测试
        os.environ['DEDUP_HIGH_THRESHOLD'] = '0.75'
        
        tracker = ContextTracker(
            storage_dir=temp_dir,
            llm_client=None,
            embedding_backend=MockEmbeddingBackend()
        )
        
        ctx1 = tracker.add("用户失去了左臂", ContextType.CHARACTER_TRAIT, "test_user")
        ctx2 = tracker.add("用户的左手臂被截断", ContextType.CHARACTER_TRAIT, "test_user")
        
        assert ctx1.id == ctx2.id, f"语义相似的内容应该合并，但得到不同ID: {ctx1.id} vs {ctx2.id}"
        
        print("✓ ContextTracker语义相似去重测试通过")
    finally:
        if 'DEDUP_HIGH_THRESHOLD' in os.environ:
            del os.environ['DEDUP_HIGH_THRESHOLD']
        shutil.rmtree(temp_dir)


def test_context_tracker_different_content():
    """测试ContextTracker不同内容不会被去重"""
    temp_dir = tempfile.mkdtemp()
    try:
        tracker = ContextTracker(
            storage_dir=temp_dir,
            llm_client=None,
            embedding_backend=MockEmbeddingBackend()
        )
        
        ctx1 = tracker.add("用户失去了左臂", ContextType.CHARACTER_TRAIT, "test_user")
        ctx2 = tracker.add("用户有一把剑", ContextType.CHARACTER_TRAIT, "test_user")
        
        assert ctx1.id != ctx2.id, f"不同内容不应该合并，但得到相同ID: {ctx1.id}"
        
        print("✓ ContextTracker不同内容不去重测试通过")
    finally:
        shutil.rmtree(temp_dir)


def test_context_tracker_embedding_persistence():
    """测试Embedding能正确存储和加载"""
    temp_dir = tempfile.mkdtemp()
    try:
        tracker = ContextTracker(
            storage_dir=temp_dir,
            llm_client=None,
            embedding_backend=MockEmbeddingBackend()
        )
        
        ctx = tracker.add("用户失去了左臂", ContextType.CHARACTER_TRAIT, "test_user")
        assert ctx.embedding is not None, "新添加的上下文应该有Embedding"
        
        # 创建新tracker加载数据
        tracker2 = ContextTracker(
            storage_dir=temp_dir,
            llm_client=None,
            embedding_backend=MockEmbeddingBackend()
        )
        
        contexts = tracker2.get_active("test_user")
        assert len(contexts) == 1, f"应该加载1个上下文，但得到: {len(contexts)}"
        assert contexts[0].embedding is not None, "加载的上下文应该有Embedding"
        
        print("✓ ContextTracker Embedding持久化测试通过")
    finally:
        shutil.rmtree(temp_dir)


def test_context_tracker_backward_compatibility():
    """测试向后兼容：无Embedding时使用词重叠"""
    temp_dir = tempfile.mkdtemp()
    try:
        tracker = ContextTracker(
            storage_dir=temp_dir,
            llm_client=None,
            embedding_backend=None  # 无Embedding
        )
        
        ctx1 = tracker.add("用户失去了左臂", ContextType.CHARACTER_TRAIT, "test_user")
        ctx2 = tracker.add("用户有一把剑", ContextType.CHARACTER_TRAIT, "test_user")
        
        assert ctx1.id != ctx2.id, "不同内容不应该合并"
        assert ctx1.embedding is None, "无Embedding后端时，embedding应该为None"
        
        print("✓ ContextTracker向后兼容测试通过")
    finally:
        shutil.rmtree(temp_dir)


def test_foreshadowing_tracker_exact_match():
    """测试ForeshadowingTracker完全相同的伏笔去重"""
    temp_dir = tempfile.mkdtemp()
    try:
        tracker = ForeshadowingTracker(
            storage_dir=temp_dir,
            embedding_backend=MockEmbeddingBackend()
        )
        
        fsh1 = tracker.plant("明天要去森林探险", "test_user")
        fsh2 = tracker.plant("明天要去森林探险", "test_user")
        
        assert fsh1.id == fsh2.id, f"完全相同的伏笔应该合并，但得到不同ID: {fsh1.id} vs {fsh2.id}"
        assert fsh2.importance > 0.5, f"重要性应该增加，但得到: {fsh2.importance}"
        
        print("✓ ForeshadowingTracker完全匹配去重测试通过")
    finally:
        shutil.rmtree(temp_dir)


def test_foreshadowing_tracker_semantic_similar():
    """测试ForeshadowingTracker语义相似伏笔去重"""
    temp_dir = tempfile.mkdtemp()
    try:
        os.environ['DEDUP_HIGH_THRESHOLD'] = '0.75'
        
        tracker = ForeshadowingTracker(
            storage_dir=temp_dir,
            embedding_backend=MockEmbeddingBackend()
        )
        
        fsh1 = tracker.plant("明天要去森林探险", "test_user")
        fsh2 = tracker.plant("计划明天进入森林", "test_user")
        
        assert fsh1.id == fsh2.id, f"语义相似的伏笔应该合并，但得到不同ID: {fsh1.id} vs {fsh2.id}"
        
        print("✓ ForeshadowingTracker语义相似去重测试通过")
    finally:
        if 'DEDUP_HIGH_THRESHOLD' in os.environ:
            del os.environ['DEDUP_HIGH_THRESHOLD']
        shutil.rmtree(temp_dir)


def test_foreshadowing_tracker_different_content():
    """测试ForeshadowingTracker不同伏笔不会被去重"""
    temp_dir = tempfile.mkdtemp()
    try:
        tracker = ForeshadowingTracker(
            storage_dir=temp_dir,
            embedding_backend=MockEmbeddingBackend()
        )
        
        fsh1 = tracker.plant("明天要去森林探险", "test_user")
        fsh2 = tracker.plant("约定下周见面", "test_user")
        
        assert fsh1.id != fsh2.id, f"不同伏笔不应该合并，但得到相同ID: {fsh1.id}"
        
        print("✓ ForeshadowingTracker不同内容不去重测试通过")
    finally:
        shutil.rmtree(temp_dir)


def test_config_management():
    """测试配置管理"""
    # 清理环境变量
    for key in ['DEDUP_EMBEDDING_ENABLED', 'DEDUP_HIGH_THRESHOLD', 'DEDUP_LOW_THRESHOLD']:
        if key in os.environ:
            del os.environ[key]
    
    # 测试默认值
    config = ContextTracker._get_dedup_config()
    assert config['enabled'] == True, f"默认应该启用，但得到: {config['enabled']}"
    assert config['high_threshold'] == 0.85, f"默认高阈值应该是0.85，但得到: {config['high_threshold']}"
    assert config['low_threshold'] == 0.70, f"默认低阈值应该是0.70，但得到: {config['low_threshold']}"
    
    # 测试自定义值
    os.environ['DEDUP_EMBEDDING_ENABLED'] = 'false'
    os.environ['DEDUP_HIGH_THRESHOLD'] = '0.90'
    os.environ['DEDUP_LOW_THRESHOLD'] = '0.60'
    
    config = ContextTracker._get_dedup_config()
    assert config['enabled'] == False, f"应该禁用，但得到: {config['enabled']}"
    assert config['high_threshold'] == 0.90, f"高阈值应该是0.90，但得到: {config['high_threshold']}"
    assert config['low_threshold'] == 0.60, f"低阈值应该是0.60，但得到: {config['low_threshold']}"
    
    # 清理
    for key in ['DEDUP_EMBEDDING_ENABLED', 'DEDUP_HIGH_THRESHOLD', 'DEDUP_LOW_THRESHOLD']:
        if key in os.environ:
            del os.environ[key]
    
    print("✓ 配置管理测试通过")


def run_all_tests():
    """运行所有测试"""
    tests = [
        test_context_tracker_exact_match,
        test_context_tracker_semantic_similar,
        test_context_tracker_different_content,
        test_context_tracker_embedding_persistence,
        test_context_tracker_backward_compatibility,
        test_foreshadowing_tracker_exact_match,
        test_foreshadowing_tracker_semantic_similar,
        test_foreshadowing_tracker_different_content,
        test_config_management,
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 60)
    print("语义去重功能测试")
    print("=" * 60)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test_func.__name__} 失败:")
            traceback.print_exc()
    
    print("=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
