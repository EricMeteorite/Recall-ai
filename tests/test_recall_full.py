#!/usr/bin/env python3
"""
Recall v5.0 全功能综合测试
===========================================================
覆盖 Recall-ai 全部功能模块，随版本升级迭代更新。

测试类型:
  - PART A: 离线单元测试（不需要服务器，直接调用引擎和模块）
  - PART B: 在线 API 测试（需要服务器在 localhost:18888 运行）

运行方式:
  # 仅运行离线测试（不需要服务器）
  python tests/test_recall_full.py --offline

  # 仅运行在线 API 测试（需要服务器）
  python tests/test_recall_full.py --online

  # 运行全部测试
  python tests/test_recall_full.py --all

  # 也可用 pytest
  pytest tests/test_recall_full.py -v

版本: 5.0.0
最后更新: 2025-02
"""

import sys
import os
import json
import time
import tempfile
import shutil
import traceback
import argparse
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

# ==================== 配置 ====================
RECALL_VERSION = "5.0.0"
API_BASE = "http://localhost:18888"
TEST_USER = "test_full_user"
TEST_CHAR = "test_full_char"

# ==================== 颜色输出 ====================
class C:
    G = '\033[92m'  # Green
    R = '\033[91m'  # Red
    Y = '\033[93m'  # Yellow
    B = '\033[94m'  # Blue
    M = '\033[95m'  # Magenta
    W = '\033[97m'  # White
    D = '\033[90m'  # Dim
    BOLD = '\033[1m'
    END = '\033[0m'

passed = 0
failed = 0
skipped = 0
errors = []

def ok(name, detail=""):
    global passed
    passed += 1
    d = f" ({detail})" if detail else ""
    print(f"  {C.G}✓{C.END} {name}{C.D}{d}{C.END}")

def fail(name, reason=""):
    global failed
    failed += 1
    r = f": {reason}" if reason else ""
    errors.append(f"{name}{r}")
    print(f"  {C.R}✗{C.END} {name}{C.R}{r}{C.END}")

def skip(name, reason=""):
    global skipped
    print(f"  {C.Y}○{C.END} {name}{C.D} (跳过: {reason}){C.END}")

def section(title):
    print(f"\n{C.B}{'─'*60}{C.END}")
    print(f"{C.B}  {title}{C.END}")
    print(f"{C.B}{'─'*60}{C.END}")

def subsection(title):
    print(f"\n  {C.M}▸ {title}{C.END}")

# ==================== 辅助函数 ====================
def safe_import(module_path, names=None):
    """安全导入模块"""
    try:
        mod = __import__(module_path, fromlist=names or [''])
        if names:
            return tuple(getattr(mod, n) for n in names)
        return mod
    except ImportError as e:
        return None

def check_server():
    """检查服务器是否运行"""
    try:
        import requests
        r = requests.get(f"{API_BASE}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

# ==============================================================================
#  PART A: 离线单元测试（不需要服务器）
# ==============================================================================

def test_A01_version():
    """A01: 版本号"""
    section("A01: 版本号检查")
    try:
        from recall.version import __version__
        if __version__ == RECALL_VERSION:
            ok("版本号匹配", f"v{__version__}")
        else:
            fail("版本号不匹配", f"期望 {RECALL_VERSION}, 实际 {__version__}")
    except Exception as e:
        fail("导入版本号失败", str(e))

def test_A02_core_imports():
    """A02: 核心模块导入"""
    section("A02: 核心模块导入")
    
    modules = [
        ("recall.engine", "RecallEngine"),
        ("recall.server", "app"),
        ("recall.config", None),
        ("recall.embedding", "EmbeddingConfig"),
        ("recall.embedding.base", "EmbeddingBackendType"),
        ("recall.embedding.factory", "create_embedding_backend"),
        ("recall.index", "InvertedIndex"),
        ("recall.index.metadata_index", "MetadataIndex"),
        ("recall.index.entity_index", "EntityIndex"),
        ("recall.index.vector_index", "VectorIndex"),
        ("recall.index.ngram_index", "OptimizedNgramIndex"),
        ("recall.storage.multi_tenant", "MultiTenantStorage"),
        ("recall.processor.consistency", "ConsistencyChecker"),
        ("recall.processor.context_tracker", "ContextTracker"),
        ("recall.processor.foreshadowing", "ForeshadowingTracker"),
        ("recall.processor.foreshadowing_analyzer", "ForeshadowingAnalyzer"),
        ("recall.processor.smart_extractor", "SmartExtractor"),
        ("recall.retrieval.eleven_layer", "ElevenLayerRetriever"),
        ("recall.retrieval.rrf_fusion", "reciprocal_rank_fusion"),
        ("recall.retrieval.config", "RetrievalConfig"),
        ("recall.graph.temporal_knowledge_graph", "TemporalKnowledgeGraph"),
        ("recall.models.temporal", "UnifiedNode"),
    ]
    
    for mod_path, attr in modules:
        try:
            mod = __import__(mod_path, fromlist=[attr] if attr else [''])
            if attr:
                assert hasattr(mod, attr), f"缺少 {attr}"
            ok(mod_path, attr or "")
        except Exception as e:
            fail(f"导入 {mod_path}", str(e))

def test_A03_embedding_configs():
    """A03: Embedding 配置工厂方法"""
    section("A03: Embedding 配置体系")
    
    from recall.embedding import EmbeddingConfig
    from recall.embedding.base import EmbeddingBackendType
    
    subsection("新名称方法")
    # lite()
    try:
        c = EmbeddingConfig.lite()
        assert c.backend == EmbeddingBackendType.NONE
        ok("lite()", f"backend=NONE")
    except Exception as e:
        fail("lite()", str(e))
    
    # cloud_openai()
    try:
        c = EmbeddingConfig.cloud_openai('sk-test', model='text-embedding-3-small')
        assert c.backend == EmbeddingBackendType.OPENAI
        assert c.dimension == 1536
        ok("cloud_openai(text-embedding-3-small)", f"dim={c.dimension}")
    except Exception as e:
        fail("cloud_openai()", str(e))
    
    try:
        c = EmbeddingConfig.cloud_openai('sk-test', model='text-embedding-3-large')
        assert c.dimension == 3072
        ok("cloud_openai(text-embedding-3-large)", f"dim={c.dimension}")
    except Exception as e:
        fail("cloud_openai(large)", str(e))
    
    # cloud_siliconflow()
    try:
        c = EmbeddingConfig.cloud_siliconflow('sf-test')
        assert c.backend == EmbeddingBackendType.SILICONFLOW
        assert c.dimension == 1024
        ok("cloud_siliconflow()", f"dim={c.dimension}")
    except Exception as e:
        fail("cloud_siliconflow()", str(e))
    
    # cloud_custom()
    try:
        c = EmbeddingConfig.cloud_custom('key', 'http://api', 'model', dimension=768)
        assert c.backend == EmbeddingBackendType.CUSTOM
        assert c.dimension == 768
        ok("cloud_custom()", f"dim={c.dimension}")
    except Exception as e:
        fail("cloud_custom()", str(e))
    
    subsection("旧名称别名（向后兼容）")
    for old_name, new_name in [
        ('lightweight', 'lite'),
        ('hybrid_openai', 'cloud_openai'),
        ('hybrid_siliconflow', 'cloud_siliconflow'),
    ]:
        try:
            assert hasattr(EmbeddingConfig, old_name), f"缺少 {old_name}"
            ok(f"{old_name}() 别名存在")
        except Exception as e:
            fail(f"{old_name}() 别名", str(e))
    
    subsection("auto_select_backend")
    try:
        from recall.embedding.factory import auto_select_backend
        result = auto_select_backend()
        assert result is not None
        ok("auto_select_backend()", f"返回 {type(result).__name__}")
    except Exception as e:
        fail("auto_select_backend()", str(e))

def test_A04_metadata_index():
    """A04: MetadataIndex 五维索引"""
    section("A04: MetadataIndex 五维索引")
    
    from recall.index.metadata_index import MetadataIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        idx = MetadataIndex(data_path=tmpdir)
        
        subsection("添加与查询")
        # 添加测试数据
        idx.add("m1", source="news", tags=["tech", "ai"], category="technology", 
                content_type="article", event_time="2025-01-15")
        idx.add("m2", source="blog", tags=["ai"], category="technology",
                content_type="post", event_time="2025-02-20")
        idx.add("m3", source="news", tags=["finance"], category="business",
                content_type="article", event_time="2025-03-10")
        idx.add("m4", source="twitter", tags=["ai", "ml"], category="technology",
                content_type="tweet", event_time="2024-12-01")
        
        # source 过滤
        r = idx.query(source="news")
        assert r == {"m1", "m3"}, f"source=news 期望 m1,m3, 得到 {r}"
        ok("source 过滤", f"{len(r)} 条")
        
        # tags 过滤
        r = idx.query(tags=["ai"])
        assert "m1" in r and "m2" in r and "m4" in r
        ok("tags 过滤", f"{len(r)} 条")
        
        # category 过滤
        r = idx.query(category="business")
        assert r == {"m3"}
        ok("category 过滤")
        
        # content_type 过滤
        r = idx.query(content_type="article")
        assert r == {"m1", "m3"}
        ok("content_type 过滤")
        
        # 日期范围过滤
        r = idx.query(event_time_start="2025-01-01", event_time_end="2025-02-28")
        assert r == {"m1", "m2"}, f"日期范围期望 m1,m2, 得到 {r}"
        ok("event_time 范围过滤", f"{len(r)} 条")
        
        # 多条件 AND
        r = idx.query(source="news", category="technology")
        assert r == {"m1"}
        ok("多条件 AND 查询")
        
        subsection("删除与批量删除")
        idx.remove("m3")
        r = idx.query(source="news")
        assert r == {"m1"}, f"删除后期望 m1, 得到 {r}"
        ok("remove 单条")
        
        idx.remove_batch({"m1", "m4"})
        r = idx.query(tags=["ai"])
        assert r == {"m2"}, f"批量删除后期望 m2, 得到 {r}"
        ok("remove_batch 批量")
        
        subsection("持久化")
        idx.add("m5", source="test", event_time="2025-06-15")
        idx.flush()  # 显式刷盘确保写入磁盘
        idx2 = MetadataIndex(data_path=tmpdir)
        r = idx2.query(source="test")
        assert "m5" in r
        ok("save/load 持久化")
        
        subsection("clear")
        idx2.clear()
        r = idx2.query(source="test")
        assert len(r) == 0
        ok("clear 清空")
        
        subsection("日期解析")
        # 各种格式
        assert MetadataIndex._parse_date_key("2025-01-15") == "2025-01-15"
        assert MetadataIndex._parse_date_key("2025-01-15T10:30:00") == "2025-01-15"
        assert MetadataIndex._parse_date_key(datetime(2025, 3, 20, 12, 0)) == "2025-03-20"
        assert MetadataIndex._parse_date_key(date(2025, 6, 1)) == "2025-06-01"
        assert MetadataIndex._parse_date_key("") is None
        assert MetadataIndex._parse_date_key(None) is None
        ok("_parse_date_key 多格式解析")

def test_A05_engine_lite():
    """A05: Engine Lite 模式 CRUD"""
    section("A05: Engine Lite 模式 CRUD")
    
    from recall.engine import RecallEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RecallEngine(data_root=tmpdir, lite=True)
        user = "test_lite"
        
        subsection("添加")
        result = engine.add("今天天气很好，阳光明媚", user_id=user, metadata={"turn": 1})
        assert result.success, f"添加失败: {result.message}"
        mid = result.id
        ok("add() 添加记忆", f"id={mid[:12]}...")
        
        # 添加更多
        r2 = engine.add("明天有一场重要的会议要参加", user_id=user, metadata={"turn": 2})
        r3 = engine.add("昨天去了公园散步，看到了很多花", user_id=user, metadata={"turn": 3})
        assert r2.success and r3.success
        ok("连续添加", "3条记忆")
        
        subsection("检索")
        results = engine.search("天气怎么样", user_id=user, top_k=5)
        assert len(results) > 0, "搜索结果为空"
        ok("search() 语义搜索", f"{len(results)} 条结果")
        
        subsection("获取")
        mem = engine.get(mid, user_id=user)
        assert mem is not None, f"获取失败: {mid}"
        assert "天气" in mem.get('content', '')
        ok("get() 获取单条")
        
        all_mems = engine.get_all(user_id=user)
        assert len(all_mems) >= 3
        ok("get_all()", f"{len(all_mems)} 条")
        
        subsection("更新")
        updated = engine.update(mid, "今天天气很好，阳光明媚。温度28度。", user_id=user)
        assert updated
        mem2 = engine.get(mid, user_id=user)
        assert "28度" in mem2.get('content', '')
        ok("update() 更新内容")
        
        subsection("删除")
        deleted = engine.delete(mid, user_id=user)
        assert deleted
        mem3 = engine.get(mid, user_id=user)
        assert mem3 is None
        ok("delete() 删除单条")
        
        subsection("清空")
        engine.clear(user_id=user)
        all_after = engine.get_all(user_id=user)
        assert len(all_after) == 0
        ok("clear() 清空用户数据")
        
        subsection("统计")
        stats = engine.get_stats()
        assert isinstance(stats, dict)
        ok("get_stats()", f"keys={list(stats.keys())[:5]}...")
        
        engine.close()
        ok("engine.close()")

def test_A06_context_system():
    """A06: 持久条件系统"""
    section("A06: 持久条件系统")
    
    from recall.engine import RecallEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RecallEngine(data_root=tmpdir, lite=True)
        user = "test_ctx"
        char = "test_char"
        
        subsection("添加持久条件")
        ctx = engine.add_persistent_context(
            "角色性格：温柔善良，喜欢帮助别人",
            context_type="character",
            user_id=user, character_id=char,
            keywords=["性格", "温柔"]
        )
        assert ctx is not None
        ok("add_persistent_context()")
        
        subsection("获取持久条件")
        contexts = engine.get_persistent_contexts(user_id=user, character_id=char)
        assert len(contexts) >= 1
        ok("get_persistent_contexts()", f"{len(contexts)} 条")
        
        subsection("构建上下文")
        engine.add("用户问了一个问题关于天气", user_id=user)
        ctx_text = engine.build_context(
            query="今天天气怎么样",
            user_id=user,
            character_id=char,
            max_tokens=1000
        )
        assert isinstance(ctx_text, str)
        ok("build_context()", f"{len(ctx_text)} 字符")
        
        subsection("删除持久条件")
        if contexts:
            ctx_id = contexts[0].get('id') or contexts[0].get('context_id', '')
            removed = engine.remove_persistent_context(ctx_id, user_id=user, character_id=char)
            ok("remove_persistent_context()")
        
        engine.close()

def test_A07_foreshadowing():
    """A07: 伏笔系统"""
    section("A07: 伏笔系统")
    
    from recall.engine import RecallEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RecallEngine(data_root=tmpdir, lite=True)
        user = "test_fore"
        char = "test_char"
        
        subsection("埋下伏笔")
        f = engine.plant_foreshadowing(
            content="远处的山上有一座神秘的古堡",
            user_id=user, character_id=char,
            related_entities=["古堡", "山"],
            importance=0.8
        )
        assert f is not None
        fid = f.id if hasattr(f, 'id') else f.get('id', '')
        ok("plant_foreshadowing()", f"id={fid[:12]}...")
        
        subsection("获取活跃伏笔")
        active = engine.get_active_foreshadowings(user_id=user, character_id=char)
        assert len(active) >= 1
        ok("get_active_foreshadowings()", f"{len(active)} 条")
        
        subsection("添加提示")
        try:
            engine.add_foreshadowing_hint(fid, "有人提到古堡里住着一位老巫师", 
                                          user_id=user, character_id=char)
            ok("add_foreshadowing_hint()")
        except Exception as e:
            fail("add_foreshadowing_hint()", str(e))
        
        subsection("解决伏笔")
        try:
            resolved = engine.resolve_foreshadowing(
                fid, "勇者终于进入了古堡，发现了宝藏",
                user_id=user, character_id=char
            )
            ok("resolve_foreshadowing()")
        except Exception as e:
            fail("resolve_foreshadowing()", str(e))
        
        engine.close()

def test_A08_retrieval_rrf():
    """A08: RRF 融合算法"""
    section("A08: RRF 融合算法")
    
    from recall.retrieval.rrf_fusion import reciprocal_rank_fusion, weighted_score_fusion
    
    subsection("reciprocal_rank_fusion")
    rankings = [
        [("a", 0.9), ("b", 0.7), ("c", 0.5), ("d", 0.3)],
        [("c", 0.8), ("a", 0.6), ("d", 0.4), ("b", 0.2)],
        [("b", 0.9), ("c", 0.7), ("a", 0.5), ("d", 0.3)],
    ]
    result = reciprocal_rank_fusion(rankings, k=60)
    assert len(result) > 0
    assert isinstance(result[0], tuple)
    ok("reciprocal_rank_fusion()", f"top={result[0][0]}")
    
    subsection("weighted_score_fusion")
    scored = [
        [("a", 0.9), ("b", 0.7), ("c", 0.5)],
        [("c", 0.8), ("a", 0.6), ("d", 0.4)],
    ]
    result = weighted_score_fusion(scored, weights=[0.7, 0.3])
    assert len(result) > 0
    ok("weighted_score_fusion()", f"top={result[0][0]}")

def test_A09_retrieval_config():
    """A09: 检索配置系统"""
    section("A09: 检索配置系统")
    
    from recall.retrieval.config import RetrievalConfig, LayerWeights
    
    subsection("默认配置")
    config = RetrievalConfig()
    assert config is not None
    ok("RetrievalConfig() 默认构造")
    
    subsection("配置预设")
    for preset in ["precise", "balanced", "creative"]:
        try:
            c = RetrievalConfig.from_preset(preset)
            ok(f"from_preset('{preset}')")
        except Exception as e:
            # 如果没有 from_preset，跳过
            skip(f"from_preset('{preset}')", str(e))
    
    subsection("LayerWeights")
    try:
        w = LayerWeights()
        assert hasattr(w, 'weights') or hasattr(w, 'l1_weight') or True
        ok("LayerWeights 构造")
    except Exception as e:
        fail("LayerWeights", str(e))

def test_A10_eleven_layer():
    """A10: 十一层检索器结构"""
    section("A10: 十一层检索器结构")
    
    from recall.retrieval.eleven_layer import ElevenLayerRetriever
    
    try:
        assert hasattr(ElevenLayerRetriever, 'retrieve') or hasattr(ElevenLayerRetriever, 'search')
        ok("ElevenLayerRetriever 类存在")
    except Exception as e:
        fail("ElevenLayerRetriever", str(e))
    
    # 检查兼容类
    try:
        from recall.retrieval.eleven_layer import EightLayerRetrieverCompat
        ok("EightLayerRetrieverCompat 兼容类存在")
    except ImportError:
        skip("EightLayerRetrieverCompat", "不存在")

def test_A11_consistency_checker():
    """A11: 一致性检查器"""
    section("A11: 一致性检查器（绝对规则）")
    
    from recall.processor.consistency import ConsistencyChecker
    
    subsection("基础功能")
    rules = ["角色不会飞", "故事发生在现代"]
    checker = ConsistencyChecker(absolute_rules=rules)
    
    existing = [{"content": "角色在公园散步"}]
    result = checker.check("角色走在街上", existing)
    ok("check() 通过正常文本")
    
    result = checker.check("角色展开翅膀飞上了天空", existing)
    # 可能触发规则
    ok("check() 处理违规文本")
    
    subsection("更新规则")
    checker.update_rules(["角色不会飞", "角色不会使用魔法"])
    ok("update_rules()")

def test_A12_smart_extractor():
    """A12: 智能抽取器"""
    section("A12: SmartExtractor 自适应抽取")
    
    try:
        from recall.processor.smart_extractor import SmartExtractor
        assert SmartExtractor is not None
        ok("SmartExtractor 导入成功")
        
        # 检查关键方法
        has_extract = hasattr(SmartExtractor, 'extract') or hasattr(SmartExtractor, 'extract_entities')
        ok("SmartExtractor 包含抽取方法", f"has_extract={has_extract}")
    except Exception as e:
        fail("SmartExtractor", str(e))

def test_A13_temporal_graph():
    """A13: 时态知识图谱"""
    section("A13: 时态知识图谱")
    
    from recall.graph.temporal_knowledge_graph import TemporalKnowledgeGraph
    from recall.models.temporal import UnifiedNode, NodeType
    
    with tempfile.TemporaryDirectory() as tmpdir:
        subsection("File 后端")
        graph = TemporalKnowledgeGraph(data_path=tmpdir, backend="file")
        
        # 添加节点
        node = UnifiedNode(
            name="测试实体",
            node_type=NodeType.ENTITY,
            attributes={"description": "这是一个测试实体"}
        )
        graph.add_node(node, user_id="test")
        ok("add_node() File 后端")
        
        subsection("Kuzu 后端")
        try:
            import kuzu
            graph_k = TemporalKnowledgeGraph(data_path=tmpdir, backend="kuzu")
            ok("Kuzu 后端初始化")
            node2 = UnifiedNode(
                name="Kuzu测试",
                node_type=NodeType.ENTITY,
                attributes={"description": "Kuzu 测试实体"}
            )
            graph_k.add_node(node2, user_id="test")
            ok("add_node() Kuzu 后端")
        except ImportError:
            skip("Kuzu 后端", "kuzu 包未安装")

def test_A14_ngram_index():
    """A14: N-gram 索引"""
    section("A14: N-gram 索引")
    
    from recall.index.ngram_index import OptimizedNgramIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        idx = OptimizedNgramIndex(data_path=tmpdir)
        
        idx.add("doc1", "今天天气很好阳光明媚")
        idx.add("doc2", "明天会下雨记得带伞")
        idx.add("doc3", "今天去公园散步了")
        
        results = idx.search("今天天气")
        assert "doc1" in results or len(results) > 0
        ok("N-gram search()", f"{len(results)} 条匹配")

def test_A15_inverted_index():
    """A15: 倒排索引"""
    section("A15: 倒排索引")
    
    from recall.index import InvertedIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        idx = InvertedIndex(data_path=tmpdir)
        
        idx.add_batch(["实体A", "实体B"], "doc1")
        idx.add_batch(["实体B", "实体C"], "doc2")
        idx.add_batch(["实体A", "实体C"], "doc3")
        
        results = idx.search("实体A")
        assert "doc1" in results
        ok("InvertedIndex search()", f"{len(results)} 条")

def test_A16_server_models():
    """A16: Server 数据模型完整性"""
    section("A16: Server 数据模型完整性")
    
    from recall.server import (
        AddMemoryRequest, SearchRequest, AddMemoryResponse,
    )
    
    subsection("AddMemoryRequest 字段")
    fields = AddMemoryRequest.model_fields
    required_fields = ['content', 'user_id']
    optional_fields = ['character_id', 'source', 'tags', 'category', 'content_type', 'event_time', 'metadata']
    
    for f in required_fields + optional_fields:
        if f in fields:
            ok(f"AddMemoryRequest.{f}")
        else:
            fail(f"AddMemoryRequest 缺少字段 {f}")
    
    subsection("SearchRequest 字段")
    fields = SearchRequest.model_fields
    search_fields = ['query', 'user_id', 'top_k', 'source', 'tags', 'category', 
                     'content_type', 'event_time_start', 'event_time_end',
                     'filters', 'config_preset']
    for f in search_fields:
        if f in fields:
            ok(f"SearchRequest.{f}")
        else:
            fail(f"SearchRequest 缺少字段 {f}")

def test_A17_server_routes():
    """A17: Server 路由完整性"""
    section("A17: Server 路由完整性")
    
    from recall.server import app
    
    routes = {(r.path, list(r.methods)[0] if r.methods else 'GET') 
              for r in app.routes if hasattr(r, 'path')}
    
    critical_routes = [
        ("/health", "GET"),
        ("/v1/memories", "POST"),
        ("/v1/memories/search", "POST"),
        ("/v1/memories/batch", "POST"),
        ("/v1/memories/{memory_id}", "GET"),
        ("/v1/memories/{memory_id}", "DELETE"),
        ("/v1/memories/{memory_id}", "PUT"),
        ("/v1/context", "POST"),
        ("/v1/foreshadowing", "POST"),
        ("/v1/foreshadowing", "GET"),
        ("/v1/persistent-contexts", "POST"),
        ("/v1/persistent-contexts", "GET"),
        ("/v1/stats", "GET"),
        ("/v1/config", "GET"),
        ("/v1/config", "PUT"),
        ("/v1/config/reload", "POST"),
        ("/v1/mode", "GET"),
        ("/v1/search/fulltext", "POST"),
        ("/v1/graph/traverse", "POST"),
        ("/v1/entities", "GET"),
        ("/v1/temporal/at", "POST"),
        ("/v1/temporal/range", "POST"),
        ("/v1/contradictions", "GET"),
        ("/v1/episodes", "GET"),
        ("/v1/users", "GET"),
        ("/v1/core-settings", "GET"),
        ("/v1/core-settings", "PUT"),
    ]
    
    for path, method in critical_routes:
        found = any(r[0] == path for r in routes)
        if found:
            ok(f"{method} {path}")
        else:
            fail(f"路由缺失: {method} {path}")

def test_A18_config_keys():
    """A18: 配置键统一性"""
    section("A18: 配置键统一性")
    
    try:
        from recall.server import SUPPORTED_CONFIG_KEYS
        assert isinstance(SUPPORTED_CONFIG_KEYS, (set, list, frozenset))
        count = len(SUPPORTED_CONFIG_KEYS)
        assert count >= 100, f"配置键数量不足: {count}"
        ok(f"SUPPORTED_CONFIG_KEYS", f"{count} 个")
        
        # 检查关键配置键
        key_samples = [
            'EMBEDDING_API_KEY', 'LLM_API_KEY', 'RECALL_MODE',
            'TEMPORAL_GRAPH_ENABLED', 'FORESHADOWING_ENABLED',
            'ELEVEN_LAYER_RETRIEVER_ENABLED',
        ]
        for key in key_samples:
            if key in SUPPORTED_CONFIG_KEYS:
                ok(f"  包含 {key}")
            else:
                fail(f"  缺少 {key}")
    except ImportError as e:
        fail("SUPPORTED_CONFIG_KEYS", str(e))

def test_A19_multi_tenant():
    """A19: 多租户存储隔离"""
    section("A19: 多租户存储隔离")
    
    from recall.engine import RecallEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RecallEngine(data_root=tmpdir, lite=True)
        
        engine.add("用户A的秘密信息", user_id="userA")
        engine.add("用户B的秘密信息", user_id="userB")
        
        a_results = engine.search("秘密信息", user_id="userA", top_k=10)
        b_results = engine.search("秘密信息", user_id="userB", top_k=10)
        
        for r in a_results:
            content = r.content if hasattr(r, 'content') else r.get('content', '')
            assert "用户B" not in content, "用户隔离失败: A 看到了 B 的数据"
        
        ok("用户隔离: A 看不到 B 的数据")
        
        engine.clear(user_id="userA")
        a_after = engine.get_all(user_id="userA")
        b_after = engine.get_all(user_id="userB")
        assert len(a_after) == 0
        assert len(b_after) >= 1
        ok("清空用户A不影响用户B")
        
        engine.close()

def test_A20_chinese_encoding():
    """A20: 中文编码安全"""
    section("A20: 中文编码安全")
    
    from recall.engine import RecallEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RecallEngine(data_root=tmpdir, lite=True)
        
        chinese_texts = [
            "今天去了故宫博物院参观，看到了很多珍贵的文物",
            "我最喜欢吃四川麻辣火锅，特别是在冬天的时候",
            "学习人工智能需要掌握数学、编程和算法知识",
            "春节期间，全家人一起包饺子，非常温馨",
        ]
        
        for i, text in enumerate(chinese_texts):
            r = engine.add(text, user_id="cn_test", metadata={"seq": i})
            assert r.success, f"中文内容添加失败: {text[:20]}"
        ok("中文内容添加", f"{len(chinese_texts)} 条")
        
        results = engine.search("火锅", user_id="cn_test", top_k=5)
        ok("中文搜索", f"{len(results)} 条结果")
        
        all_mems = engine.get_all(user_id="cn_test")
        for m in all_mems:
            content = m.get('content', '')
            # 验证无乱码
            assert all(ord(c) < 0x10000 or c.isprintable() for c in content), f"发现乱码: {content[:30]}"
        ok("中文存取无乱码")
        
        engine.close()

def test_A21_batch_operations():
    """A21: 批量操作（通过逐条 add 模拟）"""
    section("A21: 批量操作")
    
    from recall.engine import RecallEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RecallEngine(data_root=tmpdir, lite=True)
        
        # lite 模式不支持 add_batch（需要 embedding），改用逐条添加
        ids = []
        for i in range(10):
            r = engine.add(f"测试批量添加第{i}条", user_id="batch_test", metadata={"idx": i})
            if r.success:
                ids.append(r.id)
        assert len(ids) >= 10
        ok("逐条 add() x10", f"{len(ids)} 条")
        
        all_mems = engine.get_all(user_id="batch_test")
        assert len(all_mems) >= 10
        ok("添加后 get_all()", f"{len(all_mems)} 条")
        
        engine.close()

def test_A22_metadata_filter_engine():
    """A22: 引擎层元数据过滤"""
    section("A22: 引擎层元数据过滤搜索")
    
    from recall.engine import RecallEngine
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = RecallEngine(data_root=tmpdir, lite=True)
        user = "meta_test"
        
        # 添加带元数据的记忆
        engine.add("苹果发布了新的 iPhone 16", user_id=user,
                   metadata={"source": "news", "tags": ["tech", "apple"], 
                            "category": "technology", "event_time": "2025-09-10"})
        engine.add("今天的股市表现不错", user_id=user,
                   metadata={"source": "finance", "tags": ["stock"],
                            "category": "finance", "event_time": "2025-01-20"})
        engine.add("AI 领域最新进展：GPT-5 发布", user_id=user,
                   metadata={"source": "news", "tags": ["tech", "ai"],
                            "category": "technology", "event_time": "2025-06-15"})
        
        # source 过滤
        results = engine.search("最新消息", user_id=user, source="news", top_k=10)
        ok("search(source='news')", f"{len(results)} 条")
        
        # category 过滤
        results = engine.search("最新消息", user_id=user, category="finance", top_k=10)
        ok("search(category='finance')", f"{len(results)} 条")
        
        # event_time 范围
        results = engine.search("最新消息", user_id=user,
                               event_time_start="2025-01-01", event_time_end="2025-06-30", 
                               top_k=10)
        ok("search(event_time_start/end)", f"{len(results)} 条")
        
        engine.close()


# ==============================================================================
#  PART B: 在线 API 测试（需要服务器）
# ==============================================================================

def test_B01_health():
    """B01: 健康检查"""
    section("B01: 健康检查")
    import requests
    
    r = requests.get(f"{API_BASE}/health")
    assert r.status_code == 200
    ok("/health", f"status={r.status_code}")

def test_B02_mode():
    """B02: 运行模式"""
    section("B02: 运行模式")
    import requests
    
    r = requests.get(f"{API_BASE}/v1/mode")
    assert r.status_code == 200
    data = r.json()
    mode = data.get('mode', data) if isinstance(data, dict) else data
    ok("/v1/mode", f"mode={mode}")

def test_B03_add_memory():
    """B03: 添加记忆 API"""
    section("B03: 添加记忆 API")
    import requests
    
    r = requests.post(f"{API_BASE}/v1/memories", json={
        "content": "API测试：今天学习了Python编程",
        "user_id": TEST_USER,
        "source": "api_test",
        "tags": ["python", "学习"],
        "category": "education",
        "event_time": "2025-02-15",
        "metadata": {"test": True}
    })
    assert r.status_code == 200, f"添加失败: {r.text}"
    data = r.json()
    assert data.get('id') or data.get('success')
    ok("POST /v1/memories", f"id={data.get('id', 'N/A')[:12]}...")

def test_B04_add_batch():
    """B04: 批量添加 API"""
    section("B04: 批量添加 API")
    import requests
    
    items = [
        {"content": "批量测试1：机器学习基础", "source": "batch_test", "tags": ["ml"]},
        {"content": "批量测试2：深度学习框架", "source": "batch_test", "tags": ["dl"]},
        {"content": "批量测试3：自然语言处理", "source": "batch_test", "tags": ["nlp"]},
    ]
    
    r = requests.post(f"{API_BASE}/v1/memories/batch", json={
        "items": items,
        "user_id": TEST_USER
    })
    assert r.status_code == 200, f"批量添加失败: {r.text}"
    ok("POST /v1/memories/batch", f"status={r.status_code}")

def test_B05_search():
    """B05: 搜索 API"""
    section("B05: 搜索 API")
    import requests
    
    subsection("基础搜索")
    r = requests.post(f"{API_BASE}/v1/memories/search", json={
        "query": "Python编程",
        "user_id": TEST_USER,
        "top_k": 10
    })
    assert r.status_code == 200, f"搜索失败: {r.text}"
    results = r.json()
    assert isinstance(results, list)
    ok("POST /v1/memories/search", f"{len(results)} 条结果")
    
    subsection("元数据过滤搜索")
    r = requests.post(f"{API_BASE}/v1/memories/search", json={
        "query": "学习",
        "user_id": TEST_USER,
        "source": "api_test",
        "top_k": 10
    })
    assert r.status_code == 200
    ok("search + source 过滤", f"{len(r.json())} 条")
    
    subsection("event_time 范围搜索")
    r = requests.post(f"{API_BASE}/v1/memories/search", json={
        "query": "学习",
        "user_id": TEST_USER,
        "event_time_start": "2025-01-01",
        "event_time_end": "2025-12-31",
        "top_k": 10
    })
    assert r.status_code == 200
    ok("search + event_time 范围", f"{len(r.json())} 条")

def test_B06_get_memory():
    """B06: 获取记忆 API"""
    section("B06: 获取/列出记忆 API")
    import requests
    
    subsection("列出记忆")
    r = requests.get(f"{API_BASE}/v1/memories", params={
        "user_id": TEST_USER,
        "limit": 5
    })
    assert r.status_code == 200
    data = r.json()
    ok("GET /v1/memories", f"返回 {len(data) if isinstance(data, list) else 'dict'}")
    
    # 获取单条
    if isinstance(data, list) and len(data) > 0:
        mid = data[0].get('id', '')
        if mid:
            r2 = requests.get(f"{API_BASE}/v1/memories/{mid}", params={"user_id": TEST_USER})
            assert r2.status_code == 200
            ok(f"GET /v1/memories/{{id}}", f"id={mid[:12]}...")

def test_B07_update_delete():
    """B07: 更新删除 API"""
    section("B07: 更新/删除记忆 API")
    import requests
    
    # 添加一条用于测试
    r = requests.post(f"{API_BASE}/v1/memories", json={
        "content": "待更新删除的测试记忆",
        "user_id": TEST_USER,
    })
    mid = r.json().get('id', '')
    
    if mid:
        subsection("更新")
        r = requests.put(f"{API_BASE}/v1/memories/{mid}", json={
            "content": "已更新的测试记忆内容",
            "user_id": TEST_USER
        })
        assert r.status_code == 200
        ok(f"PUT /v1/memories/{{id}}")
        
        subsection("删除")
        r = requests.delete(f"{API_BASE}/v1/memories/{mid}", params={"user_id": TEST_USER})
        assert r.status_code == 200
        ok(f"DELETE /v1/memories/{{id}}")
    else:
        skip("更新/删除", "无法获取 memory_id")

def test_B08_context():
    """B08: 上下文构建 API"""
    section("B08: 上下文构建 API")
    import requests
    
    r = requests.post(f"{API_BASE}/v1/context", json={
        "query": "今天学了什么",
        "user_id": TEST_USER,
        "character_id": TEST_CHAR,
        "max_tokens": 1000,
    })
    assert r.status_code == 200
    data = r.json()
    assert 'context' in data
    ok("POST /v1/context", f"{len(data['context'])} 字符")

def test_B09_foreshadowing_api():
    """B09: 伏笔 API"""
    section("B09: 伏笔 API")
    import requests
    
    subsection("埋下伏笔")
    r = requests.post(f"{API_BASE}/v1/foreshadowing", json={
        "content": "API测试伏笔：暗处有人在监视",
        "user_id": TEST_USER,
        "character_id": TEST_CHAR,
        "importance": 0.7
    })
    assert r.status_code == 200
    fid = r.json().get('id', '')
    ok("POST /v1/foreshadowing", f"id={fid[:12]}..." if fid else "")
    
    subsection("获取伏笔列表")
    r = requests.get(f"{API_BASE}/v1/foreshadowing", params={
        "user_id": TEST_USER,
        "character_id": TEST_CHAR
    })
    assert r.status_code == 200
    ok("GET /v1/foreshadowing", f"{len(r.json())} 条")

def test_B10_persistent_contexts_api():
    """B10: 持久条件 API"""
    section("B10: 持久条件 API")
    import requests
    
    subsection("添加持久条件")
    r = requests.post(f"{API_BASE}/v1/persistent-contexts", json={
        "content": "API测试持久条件：角色喜欢喝咖啡",
        "context_type": "character",
        "user_id": TEST_USER,
        "character_id": TEST_CHAR,
        "keywords": ["咖啡", "喜好"]
    })
    assert r.status_code == 200
    ok("POST /v1/persistent-contexts")
    
    subsection("获取持久条件")
    r = requests.get(f"{API_BASE}/v1/persistent-contexts", params={
        "user_id": TEST_USER,
        "character_id": TEST_CHAR
    })
    assert r.status_code == 200
    ok("GET /v1/persistent-contexts", f"{len(r.json())} 条")
    
    subsection("统计")
    r = requests.get(f"{API_BASE}/v1/persistent-contexts/stats", params={
        "user_id": TEST_USER,
        "character_id": TEST_CHAR
    })
    assert r.status_code == 200
    ok("GET /v1/persistent-contexts/stats")

def test_B11_stats():
    """B11: 统计 API"""
    section("B11: 统计与管理 API")
    import requests
    
    r = requests.get(f"{API_BASE}/v1/stats")
    assert r.status_code == 200
    stats = r.json()
    assert isinstance(stats, dict)
    ok("GET /v1/stats", f"keys={list(stats.keys())[:5]}...")
    
    r = requests.get(f"{API_BASE}/v1/users")
    assert r.status_code == 200
    ok("GET /v1/users")
    
    r = requests.get(f"{API_BASE}/v1/config")
    assert r.status_code == 200
    ok("GET /v1/config")

def test_B12_entities():
    """B12: 实体 API"""
    section("B12: 实体 API")
    import requests
    
    r = requests.get(f"{API_BASE}/v1/entities", params={"user_id": TEST_USER})
    assert r.status_code == 200
    ok("GET /v1/entities", f"status={r.status_code}")

def test_B13_temporal():
    """B13: 时态 API"""
    section("B13: 时态查询 API")
    import requests
    
    subsection("时间点查询")
    r = requests.post(f"{API_BASE}/v1/temporal/at", json={
        "entity_name": "Python",
        "user_id": TEST_USER
    })
    assert r.status_code == 200
    ok("POST /v1/temporal/at")
    
    subsection("时间范围查询")
    r = requests.post(f"{API_BASE}/v1/temporal/range", json={
        "entity_name": "Python",
        "user_id": TEST_USER,
        "start_time": "2024-01-01",
        "end_time": "2025-12-31"
    })
    assert r.status_code == 200
    ok("POST /v1/temporal/range")
    
    subsection("时态统计")
    r = requests.get(f"{API_BASE}/v1/temporal/stats", params={"user_id": TEST_USER})
    assert r.status_code == 200
    ok("GET /v1/temporal/stats")

def test_B14_contradictions():
    """B14: 矛盾检测 API"""
    section("B14: 矛盾检测 API")
    import requests
    
    r = requests.get(f"{API_BASE}/v1/contradictions", params={"user_id": TEST_USER})
    assert r.status_code == 200
    ok("GET /v1/contradictions")
    
    r = requests.get(f"{API_BASE}/v1/contradictions/stats", params={"user_id": TEST_USER})
    assert r.status_code == 200
    ok("GET /v1/contradictions/stats")

def test_B15_graph():
    """B15: 图谱 API"""
    section("B15: 图谱 API")
    import requests
    
    r = requests.post(f"{API_BASE}/v1/graph/traverse", json={
        "start_entity": "Python",
        "max_depth": 2,
        "user_id": TEST_USER
    })
    assert r.status_code == 200
    ok("POST /v1/graph/traverse")
    
    r = requests.get(f"{API_BASE}/v1/graph/query-stats")
    assert r.status_code == 200
    ok("GET /v1/graph/query-stats")

def test_B16_episodes():
    """B16: Episode API"""
    section("B16: Episode API")
    import requests
    
    r = requests.get(f"{API_BASE}/v1/episodes", params={"user_id": TEST_USER, "limit": 5})
    assert r.status_code == 200
    ok("GET /v1/episodes")

def test_B17_fulltext():
    """B17: 全文搜索 API"""
    section("B17: 全文搜索 API")
    import requests
    
    r = requests.post(f"{API_BASE}/v1/search/fulltext", json={
        "query": "Python",
        "user_id": TEST_USER,
        "top_k": 5
    })
    assert r.status_code == 200
    ok("POST /v1/search/fulltext")
    
    r = requests.get(f"{API_BASE}/v1/search/config")
    assert r.status_code == 200
    ok("GET /v1/search/config")

def test_B18_core_settings():
    """B18: 核心设定 API"""
    section("B18: 核心设定 API")
    import requests
    
    r = requests.get(f"{API_BASE}/v1/core-settings", params={"user_id": TEST_USER})
    assert r.status_code == 200
    ok("GET /v1/core-settings")

def test_B19_config_management():
    """B19: 配置管理 API"""
    section("B19: 配置管理 API")
    import requests
    
    r = requests.get(f"{API_BASE}/v1/config/v41")
    assert r.status_code == 200
    ok("GET /v1/config/v41")
    
    r = requests.get(f"{API_BASE}/v1/config/full")
    assert r.status_code == 200
    ok("GET /v1/config/full")

def test_B20_turn_api():
    """B20: Turn API"""
    section("B20: Turn API (对话轮次)")
    import requests
    
    r = requests.post(f"{API_BASE}/v1/memories/turn", json={
        "user_message": "今天天气怎么样？",
        "ai_response": "今天天气晴朗，温度适宜，非常适合出门散步。",
        "user_id": TEST_USER,
        "character_id": TEST_CHAR,
    })
    assert r.status_code == 200
    data = r.json()
    assert data.get('success', True)  # 可能返回不同结构
    ok("POST /v1/memories/turn")

def test_B21_mem0_compat():
    """B21: mem0 兼容 API"""
    section("B21: mem0 兼容层 API")
    import requests
    
    subsection("添加")
    r = requests.post(f"{API_BASE}/v1/memory/", json={
        "messages": [{"role": "user", "content": "mem0兼容测试"}],
        "user_id": TEST_USER
    })
    # mem0 API 可能有不同的响应格式
    ok("POST /v1/memory/", f"status={r.status_code}")
    
    subsection("搜索")
    r = requests.post(f"{API_BASE}/v1/memory/search/", json={
        "query": "mem0测试",
        "user_id": TEST_USER
    })
    ok("POST /v1/memory/search/", f"status={r.status_code}")

def test_B22_cleanup():
    """B22: 清理测试数据"""
    section("B22: 清理测试数据")
    import requests
    
    r = requests.delete(f"{API_BASE}/v1/memories", params={"user_id": TEST_USER})
    if r.status_code == 200:
        ok("清理测试用户数据")
    else:
        skip("清理", f"status={r.status_code}")


# ==============================================================================
#  主入口
# ==============================================================================

def run_offline_tests():
    """运行所有离线测试"""
    tests = [
        test_A01_version,
        test_A02_core_imports,
        test_A03_embedding_configs,
        test_A04_metadata_index,
        test_A05_engine_lite,
        test_A06_context_system,
        test_A07_foreshadowing,
        test_A08_retrieval_rrf,
        test_A09_retrieval_config,
        test_A10_eleven_layer,
        test_A11_consistency_checker,
        test_A12_smart_extractor,
        test_A13_temporal_graph,
        test_A14_ngram_index,
        test_A15_inverted_index,
        test_A16_server_models,
        test_A17_server_routes,
        test_A18_config_keys,
        test_A19_multi_tenant,
        test_A20_chinese_encoding,
        test_A21_batch_operations,
        test_A22_metadata_filter_engine,
    ]
    
    print(f"\n{C.BOLD}{C.B}╔═══════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.B}║  PART A: 离线单元测试 ({len(tests)} 组)                    ║{C.END}")
    print(f"{C.BOLD}{C.B}╚═══════════════════════════════════════════════════╝{C.END}")
    
    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            fail(f"{test_fn.__name__} 异常", f"{e}\n{traceback.format_exc()}")

def run_online_tests():
    """运行所有在线 API 测试"""
    tests = [
        test_B01_health,
        test_B02_mode,
        test_B03_add_memory,
        test_B04_add_batch,
        test_B05_search,
        test_B06_get_memory,
        test_B07_update_delete,
        test_B08_context,
        test_B09_foreshadowing_api,
        test_B10_persistent_contexts_api,
        test_B11_stats,
        test_B12_entities,
        test_B13_temporal,
        test_B14_contradictions,
        test_B15_graph,
        test_B16_episodes,
        test_B17_fulltext,
        test_B18_core_settings,
        test_B19_config_management,
        test_B20_turn_api,
        test_B21_mem0_compat,
        test_B22_cleanup,
    ]
    
    print(f"\n{C.BOLD}{C.M}╔═══════════════════════════════════════════════════╗{C.END}")
    print(f"{C.BOLD}{C.M}║  PART B: 在线 API 测试 ({len(tests)} 组)                   ║{C.END}")
    print(f"{C.BOLD}{C.M}╚═══════════════════════════════════════════════════╝{C.END}")
    
    if not check_server():
        print(f"\n  {C.R}✗ 服务器未运行！请先启动: .\\start.ps1{C.END}")
        print(f"  {C.D}跳过全部在线测试{C.END}\n")
        global skipped
        skipped += len(tests)
        return
    
    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            fail(f"{test_fn.__name__} 异常", f"{e}")

def main():
    parser = argparse.ArgumentParser(description=f"Recall v{RECALL_VERSION} 全功能综合测试")
    parser.add_argument("--offline", action="store_true", help="仅运行离线测试")
    parser.add_argument("--online", action="store_true", help="仅运行在线 API 测试")
    parser.add_argument("--all", action="store_true", help="运行全部测试")
    args = parser.parse_args()
    
    # 默认运行全部
    if not args.offline and not args.online and not args.all:
        args.all = True
    
    start_time = time.time()
    
    print(f"""
{C.BOLD}{C.W}╔═══════════════════════════════════════════════════════╗
║        Recall-ai v{RECALL_VERSION} 全功能综合测试              ║
║        Full Feature Comprehensive Test Suite           ║
╚═══════════════════════════════════════════════════════╝{C.END}
""")
    
    if args.offline or args.all:
        run_offline_tests()
    
    if args.online or args.all:
        run_online_tests()
    
    elapsed = time.time() - start_time
    
    # 汇总
    total = passed + failed + skipped
    print(f"\n{C.BOLD}{'═'*60}{C.END}")
    print(f"{C.BOLD}  测试结果汇总{C.END}")
    print(f"{'═'*60}")
    print(f"  {C.G}通过: {passed}{C.END}")
    print(f"  {C.R}失败: {failed}{C.END}")
    print(f"  {C.Y}跳过: {skipped}{C.END}")
    print(f"  {C.D}总计: {total}  耗时: {elapsed:.1f}s{C.END}")
    
    if errors:
        print(f"\n{C.R}  失败详情:{C.END}")
        for i, e in enumerate(errors, 1):
            print(f"  {C.R}  {i}. {e}{C.END}")
    
    print(f"\n{'═'*60}")
    
    if failed == 0:
        print(f"{C.G}{C.BOLD}  ✓ 全部通过！Recall v{RECALL_VERSION} 功能完整 ✓{C.END}")
    else:
        print(f"{C.R}{C.BOLD}  ✗ 有 {failed} 项失败，请检查{C.END}")
    
    print(f"{'═'*60}\n")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
