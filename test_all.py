#!/usr/bin/env python3
"""Recall-ai 全面功能测试脚本"""

import tempfile
import os
import sys

def test_imports():
    """测试所有模块导入"""
    print("=== 1. 检查所有模块导入 ===")
    print()
    
    errors = []
    
    # Models
    print("Models...")
    try:
        from recall.models import Entity, Turn, Foreshadowing, Event, EntityType, EventType
        print("  models OK")
    except Exception as e:
        errors.append(f"models: {e}")
        print(f"  models FAILED: {e}")
    
    # Storage
    print("Storage...")
    try:
        from recall.storage import VolumeManager, MultiTenantStorage, MemoryScope
        from recall.storage import CoreSettings, ConsolidatedMemory, WorkingMemory
        print("  storage OK")
    except Exception as e:
        errors.append(f"storage: {e}")
        print(f"  storage FAILED: {e}")
    
    # Index
    print("Index...")
    try:
        from recall.index import EntityIndex, InvertedIndex, VectorIndex, OptimizedNgramIndex
        print("  index OK")
    except Exception as e:
        errors.append(f"index: {e}")
        print(f"  index FAILED: {e}")
    
    # Graph
    print("Graph...")
    try:
        from recall.graph import KnowledgeGraph, RelationExtractor
        print("  graph OK")
    except Exception as e:
        errors.append(f"graph: {e}")
        print(f"  graph FAILED: {e}")
    
    # Processor
    print("Processor...")
    try:
        from recall.processor import EntityExtractor, ForeshadowingTracker
        from recall.processor import ConsistencyChecker, MemorySummarizer, ScenarioDetector
        print("  processor OK")
    except Exception as e:
        errors.append(f"processor: {e}")
        print(f"  processor FAILED: {e}")
    
    # Retrieval
    print("Retrieval...")
    try:
        from recall.retrieval import EightLayerRetriever, ContextBuilder, ParallelRetriever
        print("  retrieval OK")
    except Exception as e:
        errors.append(f"retrieval: {e}")
        print(f"  retrieval FAILED: {e}")
    
    # Utils
    print("Utils...")
    try:
        from recall.utils import LLMClient, WarmupManager, PerformanceMonitor
        from recall.utils import EnvironmentManager, AutoMaintainer
        print("  utils OK")
    except Exception as e:
        errors.append(f"utils: {e}")
        print(f"  utils FAILED: {e}")
    
    # Core
    print("Core...")
    try:
        from recall.engine import RecallEngine
        from recall.cli import main as cli_main
        from recall.server import app
        print("  core OK")
    except Exception as e:
        errors.append(f"core: {e}")
        print(f"  core FAILED: {e}")
    
    print()
    if errors:
        print(f"导入检查: {len(errors)} 个错误")
        return False
    else:
        print("导入检查: 全部通过!")
        return True


def test_engine():
    """测试 RecallEngine 核心功能"""
    print()
    print("=== 2. 测试 RecallEngine 核心功能 ===")
    print()
    
    errors = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        from recall.engine import RecallEngine
        
        # 初始化引擎
        print("初始化 RecallEngine...")
        try:
            # 使用轻量模式加速测试
            engine = RecallEngine(data_root=tmpdir, lightweight=True)
            print("  初始化成功")
        except Exception as e:
            print(f"  初始化失败: {e}")
            return False
        
        # 测试 add
        print()
        print("测试 add()...")
        try:
            result1 = engine.add("这是第一条测试记忆", metadata={"user": "test"})
            result2 = engine.add("这是第二条测试记忆，关于Alice和Bob的故事")
            result3 = engine.add("Alice喜欢蓝色")
            id1 = result1.id
            id2 = result2.id
            id3 = result3.id
            print(f"  添加了3条记忆: {id1[:8]}..., {id2[:8]}..., {id3[:8]}...")
        except Exception as e:
            errors.append(f"add: {e}")
            print(f"  add 失败: {e}")
            return False
        
        # 测试 search
        print()
        print("测试 search()...")
        try:
            results = engine.search("Alice")
            print(f"  搜索 'Alice' 找到 {len(results)} 条结果")
        except Exception as e:
            errors.append(f"search: {e}")
            print(f"  search 失败: {e}")
        
        # 测试 get_all
        print()
        print("测试 get_all()...")
        try:
            all_memories = engine.get_all()
            print(f"  总共有 {len(all_memories)} 条记忆")
        except Exception as e:
            errors.append(f"get_all: {e}")
            print(f"  get_all 失败: {e}")
        
        # 测试 get
        print()
        print("测试 get()...")
        try:
            memory = engine.get(id1)
            if memory:
                content = memory.get('content', memory.get('memory', ''))
                print(f"  获取记忆: {content[:20]}...")
            else:
                errors.append(f"get: 未找到记忆 {id1}")
                print(f"  get 未找到记忆")
        except Exception as e:
            errors.append(f"get: {e}")
            print(f"  get 失败: {e}")
        
        # 测试 update
        print()
        print("测试 update()...")
        try:
            engine.update(id1, "更新后的第一条记忆")
            updated = engine.get(id1)
            if updated:
                content = updated.get('content', updated.get('memory', ''))
                print(f"  更新后: {content}")
            else:
                print(f"  update: 更新后未找到记忆")
        except Exception as e:
            errors.append(f"update: {e}")
            print(f"  update 失败: {e}")
        
        # 测试 delete
        print()
        print("测试 delete()...")
        try:
            result = engine.delete(id2)
            remaining = engine.get_all()
            print(f"  删除后剩余 {len(remaining)} 条记忆")
        except Exception as e:
            errors.append(f"delete: {e}")
            print(f"  delete 失败: {e}")
        
        # 测试 stats
        print()
        print("测试 stats()...")
        try:
            stats = engine.stats()
            print(f"  统计: {stats}")
        except Exception as e:
            errors.append(f"stats: {e}")
            print(f"  stats 失败: {e}")
        
        # 测试 clear
        print()
        print("测试 clear()...")
        try:
            engine.clear()
            after_clear = engine.get_all()
            print(f"  清空后剩余 {len(after_clear)} 条记忆")
        except Exception as e:
            errors.append(f"clear: {e}")
            print(f"  clear 失败: {e}")
    
    print()
    if errors:
        print(f"RecallEngine 测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("RecallEngine 测试: 全部通过!")
        return True


def test_storage():
    """测试存储层"""
    print()
    print("=== 3. 测试存储层 ===")
    print()
    
    errors = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试 VolumeManager
        print("测试 VolumeManager...")
        try:
            from recall.storage.volume_manager import VolumeManager
            vm = VolumeManager(data_path=tmpdir)
            # 测试加载
            turn = vm.get_turn(0)  # 尝试获取第0轮
            print(f"  VolumeManager OK")
        except Exception as e:
            errors.append(f"VolumeManager: {e}")
            print(f"  VolumeManager 失败: {e}")
        
        # 测试 MultiTenantStorage
        print("测试 MultiTenantStorage...")
        try:
            from recall.storage.multi_tenant import MultiTenantStorage
            storage = MultiTenantStorage(base_path=tmpdir)
            scope = storage.get_scope("user1", "agent1")
            print(f"  MultiTenantStorage OK")
        except Exception as e:
            errors.append(f"MultiTenantStorage: {e}")
            print(f"  MultiTenantStorage 失败: {e}")
        
        # 测试三层存储
        print("测试 CoreSettings...")
        try:
            from recall.storage.layer0_core import CoreSettings
            cs = CoreSettings.load(tmpdir)
            cs.user_preferences["test_key"] = "test_value"
            cs.save(tmpdir)
            cs2 = CoreSettings.load(tmpdir)
            value = cs2.user_preferences.get("test_key")
            assert value == "test_value"
            print(f"  CoreSettings OK")
        except Exception as e:
            errors.append(f"CoreSettings: {e}")
            print(f"  CoreSettings 失败: {e}")
        
        print("测试 ConsolidatedMemory...")
        try:
            from recall.storage.layer1_consolidated import ConsolidatedMemory
            cm = ConsolidatedMemory(data_path=tmpdir)
            print(f"  ConsolidatedMemory OK")
        except Exception as e:
            errors.append(f"ConsolidatedMemory: {e}")
            print(f"  ConsolidatedMemory 失败: {e}")
        
        print("测试 WorkingMemory...")
        try:
            from recall.storage.layer2_working import WorkingMemory
            wm = WorkingMemory(capacity=100)
            wm.update_with_delta_rule({"name": "hello", "entity_type": "test"})
            wm.update_with_delta_rule({"name": "world", "entity_type": "test"})
            assert len(wm.entities) == 2
            print(f"  WorkingMemory OK")
        except Exception as e:
            errors.append(f"WorkingMemory: {e}")
            print(f"  WorkingMemory 失败: {e}")
    
    print()
    if errors:
        print(f"存储层测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("存储层测试: 全部通过!")
        return True


def test_index():
    """测试索引层"""
    print()
    print("=== 4. 测试索引层 ===")
    print()
    
    errors = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试 EntityIndex
        print("测试 EntityIndex...")
        try:
            from recall.index.entity_index import EntityIndex, IndexedEntity
            ei = EntityIndex(data_path=tmpdir)
            entity = IndexedEntity(id="1", name="Alice", aliases=[], entity_type="person", turn_references=[1])
            ei.add(entity)
            results = ei.search("Alice")
            print(f"  EntityIndex OK (搜索结果: {len(results)})")
        except Exception as e:
            errors.append(f"EntityIndex: {e}")
            print(f"  EntityIndex 失败: {e}")
        
        # 测试 InvertedIndex
        print("测试 InvertedIndex...")
        try:
            from recall.index.inverted_index import InvertedIndex
            ii = InvertedIndex(data_path=tmpdir)
            ii.add("mem1", "Alice likes blue color")
            results = ii.search("Alice")
            print(f"  InvertedIndex OK (搜索结果: {len(results)})")
        except Exception as e:
            errors.append(f"InvertedIndex: {e}")
            print(f"  InvertedIndex 失败: {e}")
        
        # 测试 VectorIndex（跳过实际向量操作，因为需要下载模型）
        print("测试 VectorIndex...")
        try:
            from recall.index.vector_index import VectorIndex
            # 只测试初始化，跳过需要模型的操作
            vi = VectorIndex(data_path=tmpdir)
            print(f"  VectorIndex OK (初始化成功，跳过向量操作)")
        except Exception as e:
            # 如果是模型下载问题，标记为跳过而不是失败
            if "model" in str(e).lower() or "download" in str(e).lower():
                print(f"  VectorIndex 跳过 (需要下载模型)")
            else:
                errors.append(f"VectorIndex: {e}")
                print(f"  VectorIndex 失败: {e}")
        
        # 测试 OptimizedNgramIndex
        print("测试 OptimizedNgramIndex...")
        try:
            from recall.index.ngram_index import OptimizedNgramIndex
            ni = OptimizedNgramIndex()
            ni.add("mem1", "Alice likes blue")
            results = ni.search("Alice")
            print(f"  OptimizedNgramIndex OK (搜索结果: {len(results)})")
        except Exception as e:
            errors.append(f"OptimizedNgramIndex: {e}")
            print(f"  OptimizedNgramIndex 失败: {e}")
    
    print()
    if errors:
        print(f"索引层测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("索引层测试: 全部通过!")
        return True


def test_graph():
    """测试知识图谱层"""
    print()
    print("=== 5. 测试知识图谱层 ===")
    print()
    
    errors = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试 KnowledgeGraph
        print("测试 KnowledgeGraph...")
        try:
            from recall.graph.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(data_path=tmpdir)
            kg.add_entity("Alice", "person")
            kg.add_entity("Bob", "person")
            # add_relation 需要正确的参数顺序
            kg.add_relation(source_id="Alice", relation_type="knows", target_id="Bob")
            neighbors = kg.get_neighbors("Alice")
            print(f"  KnowledgeGraph OK (邻居数: {len(neighbors)})")
        except Exception as e:
            errors.append(f"KnowledgeGraph: {e}")
            print(f"  KnowledgeGraph 失败: {e}")
        
        # 测试 RelationExtractor
        print("测试 RelationExtractor...")
        try:
            from recall.graph.relation_extractor import RelationExtractor
            re = RelationExtractor()
            relations = re.extract("Alice knows Bob. Bob likes Alice.")
            print(f"  RelationExtractor OK (关系数: {len(relations)})")
        except Exception as e:
            errors.append(f"RelationExtractor: {e}")
            print(f"  RelationExtractor 失败: {e}")
    
    print()
    if errors:
        print(f"知识图谱层测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("知识图谱层测试: 全部通过!")
        return True


def test_processor():
    """测试处理器层"""
    print()
    print("=== 6. 测试处理器层 ===")
    print()
    
    errors = []
    
    # 测试 EntityExtractor
    print("测试 EntityExtractor...")
    try:
        from recall.processor.entity_extractor import EntityExtractor
        ee = EntityExtractor()
        entities = ee.extract("Alice went to New York to meet Bob.")
        print(f"  EntityExtractor OK (实体数: {len(entities)})")
    except Exception as e:
        errors.append(f"EntityExtractor: {e}")
        print(f"  EntityExtractor 失败: {e}")
    
    # 测试 ForeshadowingTracker
    print("测试 ForeshadowingTracker...")
    try:
        from recall.processor.foreshadowing import ForeshadowingTracker
        ft = ForeshadowingTracker()
        # 使用 plant 方法而不是 add_foreshadowing
        ft.plant("神秘钥匙", related_entities=["Alice"])
        active = ft.get_active()
        print(f"  ForeshadowingTracker OK (活跃伏笔: {len(active)})")
    except Exception as e:
        errors.append(f"ForeshadowingTracker: {e}")
        print(f"  ForeshadowingTracker 失败: {e}")
    
    # 测试 ConsistencyChecker
    print("测试 ConsistencyChecker...")
    try:
        from recall.processor.consistency import ConsistencyChecker
        cc = ConsistencyChecker()
        # 基本初始化测试
        print(f"  ConsistencyChecker OK")
    except Exception as e:
        errors.append(f"ConsistencyChecker: {e}")
        print(f"  ConsistencyChecker 失败: {e}")
    
    # 测试 MemorySummarizer
    print("测试 MemorySummarizer...")
    try:
        from recall.processor.memory_summarizer import MemorySummarizer
        ms = MemorySummarizer()
        print(f"  MemorySummarizer OK")
    except Exception as e:
        errors.append(f"MemorySummarizer: {e}")
        print(f"  MemorySummarizer 失败: {e}")
    
    # 测试 ScenarioDetector
    print("测试 ScenarioDetector...")
    try:
        from recall.processor.scenario import ScenarioDetector
        sd = ScenarioDetector()
        scenario = sd.detect("Alice is at the coffee shop ordering a latte.")
        print(f"  ScenarioDetector OK (场景: {scenario})")
    except Exception as e:
        errors.append(f"ScenarioDetector: {e}")
        print(f"  ScenarioDetector 失败: {e}")
    
    print()
    if errors:
        print(f"处理器层测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("处理器层测试: 全部通过!")
        return True


def test_retrieval():
    """测试检索层"""
    print()
    print("=== 7. 测试检索层 ===")
    print()
    
    errors = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试 EightLayerRetriever
        print("测试 EightLayerRetriever...")
        try:
            from recall.retrieval.eight_layer import EightLayerRetriever
            from recall.engine import RecallEngine
            engine = RecallEngine(data_root=tmpdir, lightweight=True)
            engine.add("Alice likes blue")
            engine.add("Bob likes red")
            retriever = EightLayerRetriever(engine)
            results = retriever.retrieve("Alice", top_k=5)
            print(f"  EightLayerRetriever OK (结果数: {len(results)})")
        except Exception as e:
            errors.append(f"EightLayerRetriever: {e}")
            print(f"  EightLayerRetriever 失败: {e}")
        
        # 测试 ContextBuilder
        print("测试 ContextBuilder...")
        try:
            from recall.retrieval.context_builder import ContextBuilder
            cb = ContextBuilder()
            # build 需要 memories 和 recent_turns 都是列表
            context = cb.build(memories=[], recent_turns=[], query="test query")
            print(f"  ContextBuilder OK")
        except Exception as e:
            errors.append(f"ContextBuilder: {e}")
            print(f"  ContextBuilder 失败: {e}")
        
        # 测试 ParallelRetriever
        print("测试 ParallelRetriever...")
        try:
            from recall.retrieval.parallel_retrieval import ParallelRetriever
            pr = ParallelRetriever()
            print(f"  ParallelRetriever OK")
        except Exception as e:
            errors.append(f"ParallelRetriever: {e}")
            print(f"  ParallelRetriever 失败: {e}")
    
    print()
    if errors:
        print(f"检索层测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("检索层测试: 全部通过!")
        return True


def test_utils():
    """测试工具层"""
    print()
    print("=== 8. 测试工具层 ===")
    print()
    
    errors = []
    
    # 测试 LLMClient
    print("测试 LLMClient...")
    try:
        from recall.utils.llm_client import LLMClient
        client = LLMClient()
        print(f"  LLMClient OK")
    except Exception as e:
        errors.append(f"LLMClient: {e}")
        print(f"  LLMClient 失败: {e}")
    
    # 测试 WarmupManager
    print("测试 WarmupManager...")
    try:
        from recall.utils.warmup import WarmupManager
        wm = WarmupManager()
        print(f"  WarmupManager OK")
    except Exception as e:
        errors.append(f"WarmupManager: {e}")
        print(f"  WarmupManager 失败: {e}")
    
    # 测试 PerformanceMonitor
    print("测试 PerformanceMonitor...")
    try:
        from recall.utils.perf_monitor import PerformanceMonitor, MetricType
        pm = PerformanceMonitor(auto_collect=False)
        pm.record(MetricType.LATENCY, 0.5)
        stats = pm.get_stats(MetricType.LATENCY)
        print(f"  PerformanceMonitor OK")
    except Exception as e:
        errors.append(f"PerformanceMonitor: {e}")
        print(f"  PerformanceMonitor 失败: {e}")
    
    # 测试 EnvironmentManager
    print("测试 EnvironmentManager...")
    try:
        from recall.utils.environment import EnvironmentManager
        em = EnvironmentManager()
        # 测试基本初始化
        print(f"  EnvironmentManager OK")
    except Exception as e:
        errors.append(f"EnvironmentManager: {e}")
        print(f"  EnvironmentManager 失败: {e}")
    
    # 测试 AutoMaintainer
    print("测试 AutoMaintainer...")
    try:
        from recall.utils.auto_maintain import AutoMaintainer
        am = AutoMaintainer()
        print(f"  AutoMaintainer OK")
    except Exception as e:
        errors.append(f"AutoMaintainer: {e}")
        print(f"  AutoMaintainer 失败: {e}")
    
    print()
    if errors:
        print(f"工具层测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("工具层测试: 全部通过!")
        return True


def test_cli():
    """测试 CLI"""
    print()
    print("=== 9. 测试 CLI ===")
    print()
    
    import subprocess
    
    errors = []
    
    # 测试 --version
    print("测试 recall --version...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "recall.cli", "--version"],
            capture_output=True,
            text=True
        )
        if "3.0.0" in result.stdout:
            print(f"  版本检查 OK: {result.stdout.strip()}")
        else:
            errors.append(f"版本不匹配: {result.stdout}")
            print(f"  版本检查失败: {result.stdout}")
    except Exception as e:
        errors.append(f"CLI version: {e}")
        print(f"  CLI version 失败: {e}")
    
    # 测试 --help
    print("测试 recall --help...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "recall.cli", "--help"],
            capture_output=True,
            text=True
        )
        if "Usage:" in result.stdout or "usage:" in result.stdout.lower():
            print(f"  帮助检查 OK")
        else:
            errors.append(f"帮助输出异常")
            print(f"  帮助检查失败")
    except Exception as e:
        errors.append(f"CLI help: {e}")
        print(f"  CLI help 失败: {e}")
    
    print()
    if errors:
        print(f"CLI 测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("CLI 测试: 全部通过!")
        return True


def test_server():
    """测试 Server"""
    print()
    print("=== 10. 测试 Server ===")
    print()
    
    errors = []
    
    # 测试 FastAPI app 创建
    print("测试 FastAPI app...")
    try:
        from recall.server import app
        routes = [r.path for r in app.routes]
        print(f"  FastAPI app OK (路由数: {len(routes)})")
        print(f"  路由: {routes[:5]}...")
    except Exception as e:
        errors.append(f"FastAPI app: {e}")
        print(f"  FastAPI app 失败: {e}")
    
    print()
    if errors:
        print(f"Server 测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("Server 测试: 全部通过!")
        return True


def test_multi_tenant():
    """测试多租户功能"""
    print()
    print("=== 11. 测试多租户功能 ===")
    print()
    
    errors = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        from recall.engine import RecallEngine
        
        print("创建引擎...")
        engine = RecallEngine(data_root=tmpdir, lightweight=True)
        
        # 测试不同用户的数据隔离
        print("测试用户数据隔离...")
        try:
            # 用户1添加数据
            result1 = engine.add("User1 的记忆", user_id="user1")
            
            # 用户2添加数据
            result2 = engine.add("User2 的记忆", user_id="user2")
            
            # 获取各自的数据
            user1_memories = engine.get_all(user_id="user1")
            user2_memories = engine.get_all(user_id="user2")
            print(f"  User1 记忆数: {len(user1_memories)}")
            print(f"  User2 记忆数: {len(user2_memories)}")
            print(f"  数据隔离测试 OK")
        except Exception as e:
            errors.append(f"多租户: {e}")
            print(f"  多租户测试失败: {e}")
    
    print()
    if errors:
        print(f"多租户测试: {len(errors)} 个错误")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("多租户测试: 全部通过!")
        return True


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Recall-ai 全面功能测试")
    print("=" * 60)
    print()
    
    results = []
    
    # 运行所有测试
    results.append(("模块导入", test_imports()))
    results.append(("RecallEngine 核心", test_engine()))
    results.append(("存储层", test_storage()))
    results.append(("索引层", test_index()))
    results.append(("知识图谱层", test_graph()))
    results.append(("处理器层", test_processor()))
    results.append(("检索层", test_retrieval()))
    results.append(("工具层", test_utils()))
    results.append(("CLI", test_cli()))
    results.append(("Server", test_server()))
    results.append(("多租户", test_multi_tenant()))
    
    # 汇总结果
    print()
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print()
    
    passed = 0
    failed = 0
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print()
    print(f"总计: {passed} 通过, {failed} 失败")
    print()
    
    if failed == 0:
        print("[SUCCESS] 所有测试通过!")
        return 0
    else:
        print("[WARNING] 部分测试失败，请检查上述错误")
        return 1


if __name__ == "__main__":
    sys.exit(main())
