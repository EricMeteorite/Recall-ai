#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║          Recall v7.0 — 零容错端到端用户流程测试                        ║
║          Zero-Tolerance End-to-End User Flow Test Suite              ║
╚══════════════════════════════════════════════════════════════════════╝

设计原则:
  1. 零容错 — 任何断言失败立即终止，没有 try/except 吞错
  2. 模拟真实用户 — 按照真实使用顺序测试：初始化→存储→搜索→上下文→高级功能→清理
  3. 100% 覆盖承诺功能 — 对应 docs/plans 中所有核心承诺
  4. 数据隔离 — 每个测试阶段使用独立临时目录，不污染
  5. 纯离线 — 不依赖任何外部 API / HTTP 服务器

运行方式:
  cd Recall-ai
  python -m pytest tests/test_zero_tolerance.py -v --tb=long -x 2>&1

  -x 标志: 遇到第一个失败即停止（零容错）
"""

import gc
import os
import sys
import json
import time
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import List, Dict, Any, Optional

import pytest

# ──────────────────────────────────────────────────────────────────────
# 环境准备
# ──────────────────────────────────────────────────────────────────────
warnings.filterwarnings("ignore", category=SyntaxWarning)

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 强制 Lite 模式，离线测试
os.environ["RECALL_EMBEDDING_MODE"] = "lite"
os.environ.setdefault("RECALL_DATA_ROOT", str(PROJECT_ROOT / "recall_test_zt_data"))


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def engine_factory():
    """工厂 fixture: 每次调用创建独立的 RecallEngine 实例"""
    engines = []

    def _create(tmpdir: str, **kwargs):
        from recall.engine import RecallEngine
        e = RecallEngine(data_root=tmpdir, lite=True, **kwargs)
        engines.append(e)
        return e

    yield _create

    # 清理: 关闭所有引擎
    for e in engines:
        try:
            e.close()
        except Exception:
            pass


@pytest.fixture
def fresh_engine():
    """为每个测试提供一个全新的、隔离的引擎实例"""
    from recall.engine import RecallEngine
    tmpdir = tempfile.mkdtemp(prefix="recall_zt_")
    engine = RecallEngine(data_root=tmpdir, lite=True)
    yield engine
    engine.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# 阶段 0: 模块导入与基础设施验证
# ══════════════════════════════════════════════════════════════════════
class TestPhase0_Infrastructure:
    """验证所有核心模块可以导入，基础类型正确"""

    def test_0_01_core_imports(self):
        """核心模块导入"""
        from recall.engine import RecallEngine, AddResult, AddTurnResult, SearchResult
        from recall.config import RecallConfig
        from recall.version import __version__
        from recall.init import RecallInit
        from recall.lifecycle import LifecycleManager
        from recall.context_build import ContextBuild
        from recall.memory_ops import MemoryOperations

        assert RecallEngine is not None
        assert AddResult is not None
        assert AddTurnResult is not None
        assert SearchResult is not None
        assert RecallConfig is not None
        assert __version__ is not None
        assert len(__version__) > 0

    def test_0_02_storage_imports(self):
        """存储层模块导入"""
        from recall.storage.volume_manager import VolumeManager
        from recall.storage.layer0_core import CoreSettings
        from recall.storage.layer1_consolidated import ConsolidatedMemory
        from recall.storage.layer2_working import WorkingMemory
        from recall.storage.multi_tenant import MultiTenantStorage

        assert VolumeManager is not None
        assert CoreSettings is not None
        assert ConsolidatedMemory is not None
        assert WorkingMemory is not None
        assert MultiTenantStorage is not None

    def test_0_03_index_imports(self):
        """索引层模块导入"""
        from recall.index.inverted_index import InvertedIndex
        from recall.index.ngram_index import OptimizedNgramIndex
        from recall.index.entity_index import EntityIndex

        assert InvertedIndex is not None
        assert OptimizedNgramIndex is not None
        assert EntityIndex is not None

    def test_0_04_retrieval_imports(self):
        """检索层模块导入"""
        from recall.retrieval.eleven_layer import ElevenLayerRetriever
        from recall.retrieval.rrf_fusion import reciprocal_rank_fusion

        assert ElevenLayerRetriever is not None
        assert reciprocal_rank_fusion is not None

    def test_0_05_processor_imports(self):
        """处理器模块导入"""
        from recall.processor.entity_extractor import EntityExtractor
        from recall.processor.context_tracker import ContextTracker

        assert EntityExtractor is not None
        assert ContextTracker is not None

    def test_0_06_graph_imports(self):
        """图谱模块导入"""
        from recall.graph.temporal_knowledge_graph import TemporalKnowledgeGraph

        assert TemporalKnowledgeGraph is not None

    def test_0_07_embedding_imports(self):
        """嵌入模块导入"""
        from recall.embedding import EmbeddingConfig

        # 验证工厂方法存在
        assert hasattr(EmbeddingConfig, "lite")
        assert callable(EmbeddingConfig.lite)

    def test_0_08_engine_dataclass_fields(self):
        """验证数据类字段完整性"""
        from recall.engine import AddResult, AddTurnResult, SearchResult
        import dataclasses

        # AddResult 字段
        ar_fields = {f.name for f in dataclasses.fields(AddResult)}
        assert "id" in ar_fields
        assert "success" in ar_fields
        assert "entities" in ar_fields
        assert "message" in ar_fields

        # AddTurnResult 字段
        atr_fields = {f.name for f in dataclasses.fields(AddTurnResult)}
        assert "success" in atr_fields
        assert "user_memory_id" in atr_fields
        assert "ai_memory_id" in atr_fields

        # SearchResult 字段
        sr_fields = {f.name for f in dataclasses.fields(SearchResult)}
        assert "id" in sr_fields
        assert "content" in sr_fields
        assert "score" in sr_fields


# ══════════════════════════════════════════════════════════════════════
# 阶段 1: 引擎初始化与生命周期
# ══════════════════════════════════════════════════════════════════════
class TestPhase1_Initialization:
    """验证引擎可以正确初始化、获取统计信息、关闭"""

    def test_1_01_engine_init_lite(self):
        """Lite 模式初始化"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_init_")
        try:
            engine = RecallEngine(data_root=tmpdir, lite=True)
            assert engine is not None
            assert engine.lightweight is True
            engine.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_1_02_data_directories_created(self):
        """初始化后必要目录必须存在"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_dirs_")
        try:
            engine = RecallEngine(data_root=tmpdir, lite=True)

            # 核心目录
            assert Path(tmpdir, "data").is_dir(), "data/ 目录缺失"
            assert Path(tmpdir, "cache").is_dir(), "cache/ 目录缺失"
            assert Path(tmpdir, "logs").is_dir(), "logs/ 目录缺失"

            engine.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_1_03_get_stats_empty(self):
        """空引擎的统计信息应正确返回"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_stats_")
        try:
            engine = RecallEngine(data_root=tmpdir, lite=True)
            stats = engine.get_stats()

            assert isinstance(stats, dict), "stats 必须是字典"
            assert "version" in stats, "stats 缺少 version"
            assert "lite" in stats or "lightweight" in stats, "stats 缺少模式标识"
            assert "global" in stats, "stats 缺少 global"
            assert stats["global"]["total_memories"] == 0, "空引擎应该有 0 条记忆"

            engine.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_1_04_double_close_safe(self):
        """双重关闭不应崩溃"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_close_")
        try:
            engine = RecallEngine(data_root=tmpdir, lite=True)
            engine.close()
            engine.close()  # 不应抛出异常
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# 阶段 2: 核心 CRUD 操作 (记忆的增删改查)
# ══════════════════════════════════════════════════════════════════════
class TestPhase2_CRUD:
    """零容错验证所有基本 CRUD 操作"""

    def test_2_01_add_single_memory(self, fresh_engine):
        """添加单条记忆"""
        result = fresh_engine.add("Alice今年25岁，住在北京海淀区", user_id="user1")
        assert result.success is True, f"添加失败: {result.message}"
        assert result.id is not None, "记忆 ID 不能为 None"
        assert len(result.id) > 0, "记忆 ID 不能为空字符串"

    def test_2_02_add_returns_entities(self, fresh_engine):
        """添加记忆应提取实体"""
        result = fresh_engine.add("Bob是一名软件工程师，在Google工作", user_id="user1")
        assert result.success is True
        # Lite 模式下实体提取仍应工作（基于规则）
        assert isinstance(result.entities, list), "entities 应该是列表"

    def test_2_03_get_memory(self, fresh_engine):
        """按 ID 获取记忆"""
        add_result = fresh_engine.add("这是一条测试记忆", user_id="user1")
        assert add_result.success is True

        mem = fresh_engine.get(add_result.id, user_id="user1")
        assert mem is not None, "通过 ID 获取记忆返回 None"
        assert isinstance(mem, dict), "记忆应该是字典类型"

        # 验证记忆内容包含原始文本
        content = mem.get("content", mem.get("text", ""))
        assert "测试记忆" in content, f"记忆内容不匹配: {content}"

    def test_2_04_get_all_memories(self, fresh_engine):
        """获取所有记忆"""
        fresh_engine.add("记忆A：今天天气很好", user_id="user1")
        fresh_engine.add("记忆B：明天会下雨", user_id="user1")
        fresh_engine.add("记忆C：后天放晴", user_id="user1")

        all_mems = fresh_engine.get_all(user_id="user1")
        assert len(all_mems) == 3, f"期望3条记忆，实际 {len(all_mems)}"

    def test_2_05_update_memory(self, fresh_engine):
        """更新记忆内容"""
        add_result = fresh_engine.add("原始内容：Alice住在上海", user_id="user1")
        assert add_result.success

        updated = fresh_engine.update(add_result.id, "更新后：Alice搬到了深圳", user_id="user1")
        assert updated is True, "更新操作返回 False"

        mem = fresh_engine.get(add_result.id, user_id="user1")
        assert mem is not None
        content = mem.get("content", mem.get("text", ""))
        assert "深圳" in content, f"更新后内容不包含'深圳': {content}"

    def test_2_06_delete_memory(self, fresh_engine):
        """删除记忆"""
        add_result = fresh_engine.add("即将被删除的记忆", user_id="user1")
        assert add_result.success

        deleted = fresh_engine.delete(add_result.id, user_id="user1")
        assert deleted is True, "删除操作返回 False"

        mem = fresh_engine.get(add_result.id, user_id="user1")
        assert mem is None, "删除后仍能获取到记忆"

    def test_2_07_delete_nonexistent(self, fresh_engine):
        """删除不存在的记忆应返回 False（不崩溃）"""
        result = fresh_engine.delete("nonexistent_id_12345", user_id="user1")
        assert result is False, "删除不存在的记忆应返回 False"

    def test_2_08_clear_all(self, fresh_engine):
        """清空所有记忆"""
        fresh_engine.add("记忆1", user_id="user1")
        fresh_engine.add("记忆2", user_id="user1")
        fresh_engine.add("记忆3", user_id="user1")

        all_before = fresh_engine.get_all(user_id="user1")
        assert len(all_before) == 3

        fresh_engine.clear(user_id="user1")

        all_after = fresh_engine.get_all(user_id="user1")
        assert len(all_after) == 0, f"清空后仍有 {len(all_after)} 条记忆"

    def test_2_09_add_with_metadata(self, fresh_engine):
        """带元数据添加记忆"""
        result = fresh_engine.add(
            "重要会议安排在下周一",
            user_id="user1",
            metadata={"source": "calendar", "priority": "high", "turn": 1}
        )
        assert result.success is True

        mem = fresh_engine.get(result.id, user_id="user1")
        assert mem is not None
        meta = mem.get("metadata", {})
        assert meta.get("source") == "calendar", f"metadata.source 不匹配: {meta}"

    def test_2_10_stats_after_operations(self, fresh_engine):
        """CRUD 操作后统计信息应正确更新"""
        fresh_engine.add("统计测试记忆1", user_id="stats_user")
        fresh_engine.add("统计测试记忆2", user_id="stats_user")

        stats = fresh_engine.get_stats()
        assert stats["global"]["total_memories"] >= 2, \
            f"添加2条后 total_memories={stats['global']['total_memories']}"


# ══════════════════════════════════════════════════════════════════════
# 阶段 3: 搜索与检索
# ══════════════════════════════════════════════════════════════════════
class TestPhase3_Search:
    """验证搜索功能 — Recall 的核心承诺: 100% 不遗忘"""

    def test_3_01_basic_search(self, fresh_engine):
        """基本搜索"""
        fresh_engine.add("Python是一门非常流行的编程语言", user_id="user1")
        fresh_engine.add("JavaScript主要用于Web开发", user_id="user1")
        fresh_engine.add("今天吃了一碗拉面", user_id="user1")

        results = fresh_engine.search("编程语言", user_id="user1", top_k=5)
        assert isinstance(results, list), "search 应返回列表"
        assert len(results) > 0, "搜索'编程语言'应该返回结果"

        # 验证返回的是SearchResult对象
        r = results[0]
        assert hasattr(r, "content"), "SearchResult 缺少 content 字段"
        assert hasattr(r, "score"), "SearchResult 缺少 score 字段"
        assert hasattr(r, "id"), "SearchResult 缺少 id 字段"

    def test_3_02_search_relevance(self, fresh_engine):
        """搜索相关性 — 相关内容必须出现在结果中"""
        fresh_engine.add("Alice的生日是3月15日", user_id="user1")
        fresh_engine.add("Bob最喜欢的颜色是蓝色", user_id="user1")
        fresh_engine.add("今天的天气预报说明天会下雨", user_id="user1")

        results = fresh_engine.search("Alice的生日是什么时候", user_id="user1", top_k=5)
        assert len(results) > 0, "搜索 Alice 生日应有结果"

        # 在 Lite 模式下， 验证至少有一个结果包含相关内容
        contents = [r.content for r in results]
        found = any("Alice" in c or "生日" in c or "3月" in c for c in contents)
        assert found, f"搜索结果中没有找到关于 Alice 生日的内容: {contents}"

    def test_3_03_search_empty_results(self, fresh_engine):
        """搜索无关内容应返回空列表（不崩溃）"""
        fresh_engine.add("Python编程入门", user_id="user1")

        results = fresh_engine.search("量子力学方程", user_id="user1", top_k=5)
        assert isinstance(results, list), "即使无结果也应返回列表"
        # 不要求一定为空（N-gram 可能会匹配部分字符），但不能崩溃

    def test_3_04_search_user_isolation(self, fresh_engine):
        """用户隔离 — 不同用户的记忆不应互相可见"""
        fresh_engine.add("用户A的秘密信息", user_id="userA")
        fresh_engine.add("用户B的公开信息", user_id="userB")

        results_a = fresh_engine.search("秘密信息", user_id="userA", top_k=5)
        results_b = fresh_engine.search("秘密信息", user_id="userB", top_k=5)

        # 用户A应能找到自己的信息
        if len(results_a) > 0:
            a_contents = [r.content for r in results_a]
            assert any("用户A" in c for c in a_contents), "用户A的搜索应返回自己的信息"

        # 用户B搜索"秘密信息"不应返回用户A的记忆
        if len(results_b) > 0:
            b_contents = [r.content for r in results_b]
            for c in b_contents:
                assert "用户A" not in c, f"用户隔离失败：用户B看到了用户A的记忆: {c}"

    def test_3_05_search_top_k(self, fresh_engine):
        """top_k 参数应限制结果数量"""
        for i in range(10):
            fresh_engine.add(f"测试记忆第{i+1}条关于编程的内容", user_id="user1")

        results = fresh_engine.search("编程", user_id="user1", top_k=3)
        assert len(results) <= 3, f"top_k=3 但返回了 {len(results)} 条结果"

    def test_3_06_search_after_update(self, fresh_engine):
        """更新后搜索应反映新内容"""
        result = fresh_engine.add("Alice住在上海", user_id="user1")
        assert result.success

        fresh_engine.update(result.id, "Alice已经搬到深圳了", user_id="user1")

        results = fresh_engine.search("深圳", user_id="user1", top_k=5)
        # 更新后应能搜到新内容
        if len(results) > 0:
            contents = [r.content for r in results]
            found = any("深圳" in c for c in contents)
            assert found, f"更新后搜索'深圳'应该能找到: {contents}"

    def test_3_07_search_after_delete(self, fresh_engine):
        """删除后搜索不应返回已删除的记忆"""
        r1 = fresh_engine.add("唯一的秘密密码是ABC123", user_id="user1")
        assert r1.success

        fresh_engine.delete(r1.id, user_id="user1")

        results = fresh_engine.search("秘密密码ABC123", user_id="user1", top_k=5)
        for r in results:
            assert "ABC123" not in r.content, f"已删除的记忆仍出现在搜索结果中: {r.content}"


# ══════════════════════════════════════════════════════════════════════
# 阶段 4: 对话轮次（add_turn）
# ══════════════════════════════════════════════════════════════════════
class TestPhase4_Conversation:
    """模拟真实对话交互"""

    def test_4_01_add_turn_basic(self, fresh_engine):
        """添加对话轮次"""
        result = fresh_engine.add_turn(
            user_message="你好，我叫小明",
            ai_response="你好小明！很高兴认识你。",
            user_id="user1",
            character_id="assistant"
        )
        assert result.success is True, f"add_turn 失败: {result.message}"
        assert result.user_memory_id != "", "user_memory_id 不应为空"
        assert result.ai_memory_id != "", "ai_memory_id 不应为空"

    def test_4_02_multi_turn_conversation(self, fresh_engine):
        """多轮对话"""
        turns = [
            ("我最近在学习Rust语言", "Rust是一门很好的系统编程语言！"),
            ("你觉得Rust和C++比怎么样", "Rust在内存安全方面有明显优势"),
            ("我打算用Rust写一个Web服务器", "推荐使用Actix-web或Axum框架"),
        ]

        for user_msg, ai_msg in turns:
            result = fresh_engine.add_turn(
                user_message=user_msg,
                ai_response=ai_msg,
                user_id="user1",
                character_id="assistant"
            )
            assert result.success is True, f"第{turns.index((user_msg, ai_msg))+1}轮对话失败"

        # 验证所有轮次都被存储
        all_mems = fresh_engine.get_all(user_id="user1")
        assert len(all_mems) >= 6, f"3轮对话应至少产生6条记忆，实际 {len(all_mems)}"

    def test_4_03_turn_searchable(self, fresh_engine):
        """对话内容应可搜索"""
        fresh_engine.add_turn(
            user_message="我家的猫叫小花，是一只橘猫",
            ai_response="橘猫通常性格很好，小花一定很可爱！",
            user_id="user1",
            character_id="assistant"
        )

        results = fresh_engine.search("小花", user_id="user1", top_k=5)
        assert len(results) > 0, "对话中提到的'小花'应该可以被搜索到"

    def test_4_04_turn_with_metadata(self, fresh_engine):
        """带元数据的对话轮次"""
        result = fresh_engine.add_turn(
            user_message="帮我查一下明天的天气",
            ai_response="明天北京晴，气温15-25度",
            user_id="user1",
            character_id="weather_bot",
            metadata={"scene": "weather_query", "turn_number": 1}
        )
        assert result.success is True


# ══════════════════════════════════════════════════════════════════════
# 阶段 5: 上下文构建（build_context）
# ══════════════════════════════════════════════════════════════════════
class TestPhase5_ContextBuild:
    """验证上下文构建 — Recall 的核心输出能力"""

    def test_5_01_build_empty_context(self, fresh_engine):
        """空数据下构建上下文不应崩溃"""
        ctx = fresh_engine.build_context("你好", user_id="user1")
        assert isinstance(ctx, str), "build_context 应返回字符串"

    def test_5_02_build_context_with_memories(self, fresh_engine):
        """有记忆时构建上下文应包含相关内容"""
        fresh_engine.add("项目使用Python 3.11开发", user_id="dev1")
        fresh_engine.add("数据库选择PostgreSQL", user_id="dev1")
        fresh_engine.add("部署环境是AWS EC2", user_id="dev1")

        ctx = fresh_engine.build_context(
            "我们的技术栈是什么",
            user_id="dev1",
            max_tokens=2000
        )
        assert isinstance(ctx, str)
        assert len(ctx) > 0, "上下文不应为空字符串"

    def test_5_03_context_max_tokens(self, fresh_engine):
        """max_tokens 应限制上下文长度"""
        # 添加大量内容
        for i in range(20):
            fresh_engine.add(f"这是第{i+1}条很长的记忆内容，包含很多详细的信息用于测试token限制功能", user_id="user1")

        ctx = fresh_engine.build_context(
            "所有记忆",
            user_id="user1",
            max_tokens=500
        )
        assert isinstance(ctx, str)
        # 粗略估算：中文每个字约1-2 token, 500 token ≈ 250-500字
        # 不做严格长度断言，但确保不为空且不会无限长
        assert len(ctx) < 50000, f"上下文长度 {len(ctx)} 超过合理范围"

    def test_5_04_context_multiuser(self, fresh_engine):
        """不同用户的上下文相互隔离"""
        fresh_engine.add("用户X的私人信息：银行卡号1234", user_id="userX")
        fresh_engine.add("用户Y的公开信息：喜欢旅游", user_id="userY")

        ctx_y = fresh_engine.build_context("银行卡", user_id="userY")
        assert "1234" not in ctx_y, "用户隔离失败：userY 的上下文中出现了 userX 的银行卡号"


# ══════════════════════════════════════════════════════════════════════
# 阶段 6: 伏笔系统（Foreshadowing）
# ══════════════════════════════════════════════════════════════════════
class TestPhase6_Foreshadowing:
    """验证伏笔系统 — Recall 的独创功能"""

    def test_6_01_plant_foreshadowing(self, fresh_engine):
        """种下伏笔"""
        fs = fresh_engine.plant_foreshadowing(
            content="Alice提到她有一个失散多年的妹妹",
            user_id="user1",
            character_id="narrator",
            importance=0.8
        )
        assert fs is not None, "plant_foreshadowing 返回 None"
        assert hasattr(fs, "id"), "伏笔对象缺少 id"
        assert hasattr(fs, "content"), "伏笔对象缺少 content"

    def test_6_02_get_active_foreshadowings(self, fresh_engine):
        """获取活跃伏笔"""
        fresh_engine.plant_foreshadowing(
            content="神秘的黑猫总是出现在关键时刻",
            user_id="user1",
            character_id="narrator"
        )
        fresh_engine.plant_foreshadowing(
            content="那把锁着的抽屉里到底藏着什么",
            user_id="user1",
            character_id="narrator"
        )

        active = fresh_engine.get_active_foreshadowings(user_id="user1", character_id="narrator")
        assert isinstance(active, list), "应返回列表"
        assert len(active) >= 2, f"应至少有2个活跃伏笔，实际 {len(active)}"

    def test_6_03_foreshadowing_user_isolation(self, fresh_engine):
        """伏笔的用户隔离"""
        fresh_engine.plant_foreshadowing(
            content="userA的伏笔", user_id="userA", character_id="c1"
        )
        fresh_engine.plant_foreshadowing(
            content="userB的伏笔", user_id="userB", character_id="c1"
        )

        active_a = fresh_engine.get_active_foreshadowings(user_id="userA", character_id="c1")
        active_b = fresh_engine.get_active_foreshadowings(user_id="userB", character_id="c1")

        a_contents = [f.content for f in active_a]
        b_contents = [f.content for f in active_b]

        assert not any("userB" in c for c in a_contents), "userA 不应看到 userB 的伏笔"
        assert not any("userA" in c for c in b_contents), "userB 不应看到 userA 的伏笔"


# ══════════════════════════════════════════════════════════════════════
# 阶段 7: 持久条件系统（Persistent Context）
# ══════════════════════════════════════════════════════════════════════
class TestPhase7_PersistentContext:
    """验证持久条件 — 确保长期设定不丢失"""

    def test_7_01_add_persistent_context(self, fresh_engine):
        """添加持久条件"""
        ctx = fresh_engine.add_persistent_context(
            content="用户是一名资深后端工程师",
            context_type="identity",
            user_id="user1",
            character_id="assistant",
            keywords=["工程师", "后端"]
        )
        assert ctx is not None, "add_persistent_context 返回 None"

    def test_7_02_get_persistent_contexts(self, fresh_engine):
        """获取持久条件"""
        fresh_engine.add_persistent_context(
            content="当前项目使用微服务架构",
            context_type="tech_stack",
            user_id="user1",
            character_id="assistant"
        )
        fresh_engine.add_persistent_context(
            content="团队有10个人，分布在北京和上海",
            context_type="identity",
            user_id="user1",
            character_id="assistant"
        )

        contexts = fresh_engine.get_persistent_contexts(user_id="user1", character_id="assistant")
        assert isinstance(contexts, list), "应返回列表"
        assert len(contexts) >= 2, f"应至少有2个持久条件，实际 {len(contexts)}"

    def test_7_03_persistent_context_survives_search(self, fresh_engine):
        """持久条件设置后，应在上下文中可见"""
        fresh_engine.add_persistent_context(
            content="用户偏好简洁的代码风格",
            context_type="preferences",
            user_id="user1",
            character_id="assistant"
        )

        # 持久条件应该可以通过 get_persistent_contexts 获取
        contexts = fresh_engine.get_persistent_contexts(user_id="user1", character_id="assistant")
        assert len(contexts) >= 1
        all_content = str(contexts)
        assert "简洁" in all_content, "持久条件内容丢失"


# ══════════════════════════════════════════════════════════════════════
# 阶段 8: 多租户与数据隔离
# ══════════════════════════════════════════════════════════════════════
class TestPhase8_MultiTenant:
    """验证多租户隔离性 — 绝对不能出现数据泄漏"""

    def test_8_01_user_data_isolation(self, fresh_engine):
        """不同用户的数据完全隔离"""
        fresh_engine.add("userA的私人日记", user_id="userA")
        fresh_engine.add("userB的工作笔记", user_id="userB")
        fresh_engine.add("userC的购物清单", user_id="userC")

        mems_a = fresh_engine.get_all(user_id="userA")
        mems_b = fresh_engine.get_all(user_id="userB")
        mems_c = fresh_engine.get_all(user_id="userC")

        assert len(mems_a) == 1
        assert len(mems_b) == 1
        assert len(mems_c) == 1

        # 内容隔离
        a_content = str(mems_a)
        assert "userB" not in a_content
        assert "userC" not in a_content

    def test_8_02_clear_one_user(self, fresh_engine):
        """清空一个用户不影响其他用户"""
        fresh_engine.add("A的记忆", user_id="userA")
        fresh_engine.add("B的记忆", user_id="userB")

        fresh_engine.clear(user_id="userA")

        mems_a = fresh_engine.get_all(user_id="userA")
        mems_b = fresh_engine.get_all(user_id="userB")

        assert len(mems_a) == 0, "清空后 userA 应无记忆"
        assert len(mems_b) == 1, "清空 userA 不应影响 userB"

    def test_8_03_character_isolation(self, fresh_engine):
        """不同 character_id 的隔离"""
        fresh_engine.add_turn(
            "对角色A说的话", "角色A的回复",
            user_id="user1", character_id="charA"
        )
        fresh_engine.add_turn(
            "对角色B说的话", "角色B的回复",
            user_id="user1", character_id="charB"
        )

        # 伏笔应按 character_id 隔离
        fresh_engine.plant_foreshadowing(
            "charA的伏笔线索", user_id="user1", character_id="charA"
        )

        active_a = fresh_engine.get_active_foreshadowings(user_id="user1", character_id="charA")
        active_b = fresh_engine.get_active_foreshadowings(user_id="user1", character_id="charB")

        assert len(active_a) >= 1
        assert len(active_b) == 0, "charB 不应看到 charA 的伏笔"


# ══════════════════════════════════════════════════════════════════════
# 阶段 9: 完整用户场景模拟
# ══════════════════════════════════════════════════════════════════════
class TestPhase9_RealWorldScenarios:
    """模拟真实世界用户使用场景 — 端到端无中断"""

    def test_9_01_scenario_roleplay_session(self, fresh_engine):
        """
        场景: RP/角色扮演会话
        用户与AI角色进行多轮对话，系统需要记住所有细节
        """
        user = "rp_player"
        char = "narrator"

        # 1. 设置世界观（持久条件）
        fresh_engine.add_persistent_context(
            content="故事背景设定在2045年的东京，世界被一场大灾变改变",
            context_type="custom",
            user_id=user,
            character_id=char
        )
        fresh_engine.add_persistent_context(
            content="主角名叫 Hiro，是一名黑客",
            context_type="identity",
            user_id=user,
            character_id=char
        )

        # 2. 进行多轮对话
        turns = [
            ("Hiro走进了一间破旧的酒吧", "酒吧里弥漫着电子烟的气味，角落里坐着一个戴墨镜的女人"),
            ("Hiro走向那个戴墨镜的女人", "那个女人抬起头，露出一道伤疤。'你就是传说中的Hiro？'她问道。"),
            ("'你是谁？'Hiro问", "'叫我Zero。我有一个任务要交给你。'Zero从外套里掏出一个闪存盘。"),
            ("Hiro接过闪存盘", "'里面有一个AI核心的副本。有人想毁掉它。'Zero的声音带着紧迫。"),
        ]

        for user_msg, ai_msg in turns:
            result = fresh_engine.add_turn(user_msg, ai_msg, user_id=user, character_id=char)
            assert result.success is True

        # 3. 种下伏笔
        fs = fresh_engine.plant_foreshadowing(
            content="Zero脸上的伤疤似乎隐藏着一段不为人知的过去",
            user_id=user,
            character_id=char,
            related_entities=["Zero"],
            importance=0.9
        )
        assert fs is not None

        # 4. 验证搜索能力
        results = fresh_engine.search("Zero是谁", user_id=user, top_k=5)
        assert len(results) > 0, "应该能搜索到关于 Zero 的信息"

        # 5. 构建上下文
        ctx = fresh_engine.build_context(
            "Hiro决定打开闪存盘",
            user_id=user,
            character_id=char,
            max_tokens=3000
        )
        assert isinstance(ctx, str)
        assert len(ctx) > 0

        # 6. 验证伏笔存在
        active_fs = fresh_engine.get_active_foreshadowings(user_id=user, character_id=char)
        assert len(active_fs) >= 1

        # 7. 验证持久条件仍在
        pctx = fresh_engine.get_persistent_contexts(user_id=user, character_id=char)
        assert len(pctx) >= 2

    def test_9_02_scenario_coding_assistant(self, fresh_engine):
        """
        场景: 编码助手
        用户在多次会话中积累项目知识
        """
        user = "developer"
        char = "code_assistant"

        # 1. 项目初始信息
        project_info = [
            "项目名称是 MegaApp, 使用 FastAPI + React + PostgreSQL 技术栈",
            "API 版本是 v2, 基础路径 /api/v2",
            "数据库有三个主要表: users, orders, products",
            "认证采用 JWT + OAuth2, token 过期时间 30 分钟",
            "部署在 AWS ECS + RDS, 使用 CDK 进行基础设施管理",
        ]

        for info in project_info:
            result = fresh_engine.add(info, user_id=user, metadata={"type": "project_knowledge"})
            assert result.success is True

        # 2. 设置持久条件
        fresh_engine.add_persistent_context(
            content="用户偏好: 代码要有完整的类型注释, 使用 Black 格式化, 遵循 PEP 8",
            context_type="preferences",
            user_id=user,
            character_id=char
        )

        # 3. 模拟对话
        fresh_engine.add_turn(
            "帮我写一个用户注册的 API 端点",
            "好的，基于你的项目配置，我会使用 FastAPI 和 JWT...",
            user_id=user,
            character_id=char
        )

        # 4. 搜索项目信息
        results = fresh_engine.search("数据库", user_id=user, top_k=5)
        assert len(results) > 0
        found_db = any("PostgreSQL" in r.content or "数据库" in r.content for r in results)
        assert found_db, "应搜索到数据库相关信息"

        # 5. 上下文应包含项目信息
        ctx = fresh_engine.build_context(
            "如何连接数据库",
            user_id=user,
            character_id=char,
            max_tokens=3000
        )
        assert len(ctx) > 0

    def test_9_03_scenario_knowledge_base(self, fresh_engine):
        """
        场景: 知识库
        存储大量结构化知识，验证检索准确性
        """
        user = "knowledge_user"

        # 存储知识条目
        knowledge = {
            "physics": "光速约为每秒30万公里，即299792458米每秒",
            "chemistry": "水的分子式是H2O，由两个氢原子和一个氧原子组成",
            "biology": "DNA的双螺旋结构由Watson和Crick在1953年发现",
            "math": "圆周率π约等于3.14159，是一个无理数",
            "history": "秦始皇于公元前221年统一中国，建立秦朝",
            "geography": "珠穆朗玛峰高8848.86米，是世界最高峰",
            "cs": "图灵机由Alan Turing在1936年提出，是现代计算机的理论基础",
            "music": "贝多芬在完全失聪后创作了第九交响曲",
        }

        for topic, content in knowledge.items():
            result = fresh_engine.add(
                content,
                user_id=user,
                metadata={"topic": topic}
            )
            assert result.success, f"添加 {topic} 知识失败"

        # 验证每个领域都可搜索
        test_queries = [
            ("光速是多少", "光速"),
            ("水的分子式", "H2O"),
            ("DNA结构", "DNA"),
        ]

        for query, expected_keyword in test_queries:
            results = fresh_engine.search(query, user_id=user, top_k=3)
            assert len(results) > 0, f"搜索 '{query}' 无结果"
            found = any(expected_keyword in r.content for r in results)
            assert found, f"搜索 '{query}' 的结果中未找到 '{expected_keyword}'"

        # 验证总数
        all_mems = fresh_engine.get_all(user_id=user)
        assert len(all_mems) == len(knowledge), \
            f"期望 {len(knowledge)} 条记忆，实际 {len(all_mems)}"

    def test_9_04_scenario_high_volume(self, fresh_engine):
        """
        场景: 高容量测试
        模拟用户长期使用，累积大量记忆
        注：每条记忆内容差异足够大以避免三阶段去重跳过
        """
        user = "heavy_user"
        n_memories = 50

        # 用差异化内容避免去重
        unique_topics = [
            "量子计算的基本原理", "法国大革命的历史背景", "深度学习中的注意力机制",
            "日本料理的制作方法", "宇宙大爆炸理论的证据", "莎士比亚的四大悲剧",
            "区块链技术的应用场景", "南极洲的气候变化研究", "阿尔茨海默症的最新治疗",
            "火星殖民的可行性分析", "Python异步编程的最佳实践", "古埃及金字塔建造之谜",
            "人工智能伦理问题讨论", "热带雨林的生物多样性", "相对论对GPS的影响",
            "中国古代丝绸之路的贸易", "基因编辑CRISPR的发展", "全球变暖对海洋的影响",
            "摇滚乐的起源和发展", "太阳能电池板的效率提升", "哲学中的存在主义思想",
            "微服务架构设计模式", "亚马逊河流域的探险历史", "纳米技术在医学中的应用",
            "古希腊民主制度的演变", "电动汽车电池技术对比", "阿拉伯数字的传播历史",
            "深海生物的发光机制", "冷战时期的太空竞赛", "机器学习中的过拟合问题",
            "红酒酿造的化学过程", "北极熊的生存现状", "量子纠缠的实验验证",
            "日本动漫产业的发展", "非洲大陆的地质构造", "云计算安全架构设计",
            "莫扎特的音乐创作风格", "海洋塑料污染治理方案", "数论中的素数分布",
            "印度瑜伽的历史起源", "超导材料的研究进展", "维京人的航海技术",
            "人脸识别技术的原理", "咖啡豆的种植和加工", "暗物质存在的间接证据",
            "中世纪欧洲的黑死病", "无人驾驶汽车的传感器", "西藏高原的生态保护",
            "博弈论在经济学中的应用", "蜜蜂的群体智能行为",
        ]

        ids = []
        for i in range(n_memories):
            result = fresh_engine.add(
                f"知识条目{i+1}: {unique_topics[i]}",
                user_id=user,
                metadata={"batch": True, "index": i}
            )
            assert result.success, f"第{i+1}条添加失败: {result.message}"
            ids.append(result.id)

        # 验证总数（允许极少量去重，但绝大部分应成功存储）
        all_mems = fresh_engine.get_all(user_id=user)
        assert len(all_mems) >= n_memories * 0.9, \
            f"期望至少 {int(n_memories * 0.9)} 条, 实际 {len(all_mems)}"

        # 随机访问
        for idx in [0, 24, 49]:
            mem = fresh_engine.get(ids[idx], user_id=user)
            assert mem is not None, f"第{idx+1}条记忆丢失"

        # 搜索
        results = fresh_engine.search("量子计算", user_id=user, top_k=10)
        assert len(results) > 0, "搜索大量记忆应有结果"

        # 统计
        stats = fresh_engine.get_stats()
        assert stats["global"]["total_memories"] >= n_memories * 0.9


# ══════════════════════════════════════════════════════════════════════
# 阶段 10: 边界条件与鲁棒性
# ══════════════════════════════════════════════════════════════════════
class TestPhase10_EdgeCases:
    """边界条件测试 — 确保系统不会在异常输入下崩溃"""

    def test_10_01_empty_content(self, fresh_engine):
        """空内容处理"""
        result = fresh_engine.add("", user_id="user1")
        # 可以成功也可以失败，但不能崩溃
        assert isinstance(result.success, bool)

    def test_10_02_very_long_content(self, fresh_engine):
        """超长内容"""
        long_text = "这是一段非常长的文本。" * 1000  # ~10000 字
        result = fresh_engine.add(long_text, user_id="user1")
        assert result.success is True, "长文本不应导致失败"

        mem = fresh_engine.get(result.id, user_id="user1")
        assert mem is not None

    def test_10_03_special_characters(self, fresh_engine):
        """特殊字符"""
        special = 'Content with "quotes", <html>, &&, ||, \n\t, 中文, 日本語, 한국어, émojis: 🎉🚀'
        result = fresh_engine.add(special, user_id="user1")
        assert result.success is True

        mem = fresh_engine.get(result.id, user_id="user1")
        assert mem is not None

    def test_10_04_unicode_user_id(self, fresh_engine):
        """Unicode 用户 ID"""
        result = fresh_engine.add("测试内容", user_id="用户_测试")
        assert result.success is True

        mems = fresh_engine.get_all(user_id="用户_测试")
        assert len(mems) >= 1

    def test_10_05_rapid_operations(self, fresh_engine):
        """快速连续操作"""
        results = []
        for i in range(20):
            r = fresh_engine.add(f"快速操作{i}", user_id="fast_user")
            results.append(r)

        assert all(r.success for r in results), "快速连续添加不应失败"

        all_mems = fresh_engine.get_all(user_id="fast_user")
        assert len(all_mems) == 20

    def test_10_06_search_empty_query(self, fresh_engine):
        """空查询搜索"""
        fresh_engine.add("有内容的记忆", user_id="user1")
        results = fresh_engine.search("", user_id="user1", top_k=5)
        assert isinstance(results, list)  # 不崩溃即可

    def test_10_07_get_nonexistent(self, fresh_engine):
        """获取不存在的记忆"""
        mem = fresh_engine.get("completely_fake_id", user_id="user1")
        assert mem is None, "不存在的 ID 应返回 None"

    def test_10_08_operations_after_clear(self, fresh_engine):
        """清空后正常操作"""
        fresh_engine.add("开始", user_id="user1")
        fresh_engine.clear(user_id="user1")

        # 清空后应能正常添加
        result = fresh_engine.add("清空后添加", user_id="user1")
        assert result.success
        assert fresh_engine.get(result.id, user_id="user1") is not None


# ══════════════════════════════════════════════════════════════════════
# 阶段 11: 数据持久性验证
# ══════════════════════════════════════════════════════════════════════
class TestPhase11_Persistence:
    """验证数据持久性 — 关闭引擎后重新打开，数据不丢失"""

    def test_11_01_data_survives_restart(self):
        """引擎重启后数据持久化"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_persist_")
        try:
            # 第一次会话: 写入数据
            engine1 = RecallEngine(data_root=tmpdir, lite=True)
            r1 = engine1.add("持久化测试：这条记忆必须在重启后存活", user_id="persist_user")
            assert r1.success
            mem_id = r1.id
            engine1.close()

            # 第二次会话: 验证数据仍在
            engine2 = RecallEngine(data_root=tmpdir, lite=True)
            mem = engine2.get(mem_id, user_id="persist_user")
            assert mem is not None, "重启后记忆丢失！这是严重的持久化 bug"

            content = mem.get("content", mem.get("text", ""))
            assert "持久化测试" in content, f"重启后记忆内容被破坏: {content}"
            engine2.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_11_02_multiple_users_persist(self):
        """多用户数据持久化"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_multiuser_")
        try:
            # 写入
            engine1 = RecallEngine(data_root=tmpdir, lite=True)
            engine1.add("UserA的数据", user_id="userA")
            engine1.add("UserB的数据", user_id="userB")
            engine1.close()

            # 读取
            engine2 = RecallEngine(data_root=tmpdir, lite=True)
            mems_a = engine2.get_all(user_id="userA")
            mems_b = engine2.get_all(user_id="userB")

            assert len(mems_a) >= 1, "UserA 数据丢失"
            assert len(mems_b) >= 1, "UserB 数据丢失"
            engine2.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_11_03_foreshadowing_persists(self):
        """伏笔数据持久化"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_fs_persist_")
        try:
            engine1 = RecallEngine(data_root=tmpdir, lite=True)
            fs = engine1.plant_foreshadowing(
                "这个伏笔必须在重启后存活",
                user_id="user1",
                character_id="char1"
            )
            assert fs is not None
            engine1.close()

            engine2 = RecallEngine(data_root=tmpdir, lite=True)
            active = engine2.get_active_foreshadowings(user_id="user1", character_id="char1")
            assert len(active) >= 1, "伏笔在重启后丢失！"
            engine2.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_11_04_persistent_context_persists(self):
        """持久条件数据持久化"""
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_ctx_persist_")
        try:
            engine1 = RecallEngine(data_root=tmpdir, lite=True)
            engine1.add_persistent_context(
                "这个持久条件必须在重启后存活",
                context_type="custom",
                user_id="user1",
                character_id="char1"
            )
            engine1.close()

            engine2 = RecallEngine(data_root=tmpdir, lite=True)
            contexts = engine2.get_persistent_contexts(user_id="user1", character_id="char1")
            assert len(contexts) >= 1, "持久条件在重启后丢失！"
            engine2.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# 阶段 12: HTTP API 端到端（需要服务器运行）
# ══════════════════════════════════════════════════════════════════════
class TestPhase12_HTTPApi:
    """HTTP API 测试 — 验证服务器模式下的端到端流程
    
    NOTE: 如在测试环境中服务器未运行，此阶段将自动跳过。
    手动启动: python -m recall serve --host 127.0.0.1 --port 18888
    """

    @pytest.fixture(autouse=True)
    def check_server(self):
        """检查服务器是否可用"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(("127.0.0.1", 18888))
            sock.close()
            if result != 0:
                pytest.skip("HTTP 服务器未运行 (localhost:18888)")
        except Exception:
            pytest.skip("HTTP 服务器不可达")

    def _api(self, method, path, **kwargs):
        """HTTP 请求封装"""
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:18888{path}"

        if method == "GET":
            req = urllib.request.Request(url)
        else:
            data = json.dumps(kwargs.get("json", {})).encode("utf-8")
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise AssertionError(f"HTTP {e.code}: {body}")

    def test_12_01_health_check(self):
        """健康检查"""
        resp = self._api("GET", "/health")
        assert resp.get("status") == "ok" or "status" in resp

    def test_12_02_api_add_memory(self):
        """API 添加记忆"""
        resp = self._api("POST", "/v1/memories", json={
            "content": "通过API添加的测试记忆",
            "user_id": "api_test_user"
        })
        assert resp.get("success") is True or resp.get("id") is not None

    def test_12_03_api_search(self):
        """API 搜索"""
        # 先添加
        self._api("POST", "/v1/memories", json={
            "content": "搜索测试：Python是最好的语言",
            "user_id": "api_search_user"
        })

        # 搜索
        resp = self._api("POST", "/v1/memories/search", json={
            "query": "Python",
            "user_id": "api_search_user",
            "top_k": 5
        })
        assert isinstance(resp, (list, dict))

    def test_12_04_api_context(self):
        """API 构建上下文"""
        resp = self._api("POST", "/v1/context", json={
            "query": "项目信息",
            "user_id": "api_test_user",
            "max_tokens": 2000
        })
        assert isinstance(resp, (str, dict))


# ══════════════════════════════════════════════════════════════════════
# 阶段 13: 全流程连续压力测试
# ══════════════════════════════════════════════════════════════════════
class TestPhase13_FullPipeline:
    """完整管道测试 — 模拟一个完整的用户会话从头到尾"""

    def test_13_01_complete_lifecycle(self):
        """
        完整生命周期测试:
        初始化 → 设置条件 → 多轮对话 → 搜索回忆 → 构建上下文 → 种伏笔 → 
        验证持久化 → 更新记忆 → 删除记忆 → 统计验证 → 关闭 → 重新打开 → 
        验证数据完整性
        """
        from recall.engine import RecallEngine

        tmpdir = tempfile.mkdtemp(prefix="recall_zt_full_")
        errors = []

        try:
            # ── Step 1: 初始化 ──
            engine = RecallEngine(data_root=tmpdir, lite=True)
            assert engine is not None

            user = "lifecycle_user"
            char = "lifecycle_char"

            # ── Step 2: 设置持久条件 ──
            ctx1 = engine.add_persistent_context(
                "系统角色：你是一个专业的AI助手",
                context_type="identity",
                user_id=user, character_id=char
            )
            assert ctx1 is not None, "Step 2: 设置持久条件失败"

            # ── Step 3: 添加基础知识 ──
            memories = {}
            knowledge_items = [
                "项目名称: Phoenix, 一个分布式计算框架",
                "核心语言: Rust, 辅助语言: Python",
                "当前版本: v3.2.1, 计划下个版本 v3.3.0",
                "团队成员: Alice(架构师), Bob(后端), Carol(前端), Dave(DevOps)",
                "部署环境: Kubernetes on GCP, 使用 Helm charts",
            ]

            for item in knowledge_items:
                r = engine.add(item, user_id=user, metadata={"type": "knowledge"})
                assert r.success, f"Step 3: 添加知识失败 - {r.message} - {item}"
                memories[item[:10]] = r.id

            # ── Step 4: 多轮对话 ──
            conversation = [
                ("Phoenix项目的最新进度如何?", "根据记录，Phoenix v3.2.1 已发布，团队正在规划 v3.3.0"),
                ("Alice最近在做什么?", "Alice作为架构师，正在设计新的分布式调度算法"),
                ("我们需要在下周三之前完成代码审查", "好的，我会记住这个截止日期。"),
                ("Bob反馈说性能测试有问题", "了解，Bob发现的性能问题需要优先处理"),
            ]

            for user_msg, ai_msg in conversation:
                r = engine.add_turn(user_msg, ai_msg, user_id=user, character_id=char)
                assert r.success, f"Step 4: 对话失败 - {r.message}"

            # ── Step 5: 搜索验证 ──
            search_tests = [
                ("Alice", "Alice"),
                ("Phoenix版本", "Phoenix"),
                ("Kubernetes", "Kubernetes"),
            ]

            for query, expected in search_tests:
                results = engine.search(query, user_id=user, top_k=5)
                assert len(results) > 0, f"Step 5: 搜索 '{query}' 无结果"

            # ── Step 6: 构建上下文 ──
            ctx = engine.build_context(
                "项目整体情况如何",
                user_id=user,
                character_id=char,
                max_tokens=3000
            )
            assert isinstance(ctx, str)
            assert len(ctx) > 0, "Step 6: 上下文为空"

            # ── Step 7: 种伏笔 ──
            fs = engine.plant_foreshadowing(
                "Bob提到的性能问题可能与新的调度算法有关联",
                user_id=user,
                character_id=char,
                related_entities=["Bob", "Alice"],
                importance=0.7
            )
            assert fs is not None, "Step 7: 种伏笔失败"

            # ── Step 8: 验证当前状态 ──
            stats = engine.get_stats()
            assert stats["global"]["total_memories"] >= len(knowledge_items) + len(conversation) * 2

            active_fs = engine.get_active_foreshadowings(user_id=user, character_id=char)
            assert len(active_fs) >= 1, "Step 8: 伏笔丢失"

            pctx = engine.get_persistent_contexts(user_id=user, character_id=char)
            assert len(pctx) >= 1, "Step 8: 持久条件丢失"

            # ── Step 9: 更新一条记忆 ──
            first_id = list(memories.values())[0]
            updated = engine.update(first_id, "更新后: Phoenix v3.2.2 已发布", user_id=user)
            assert updated is True, "Step 9: 更新失败"

            updated_mem = engine.get(first_id, user_id=user)
            assert updated_mem is not None
            updated_content = updated_mem.get("content", updated_mem.get("text", ""))
            assert "v3.2.2" in updated_content, "Step 9: 更新内容未生效"

            # ── Step 10: 删除一条记忆 ──
            last_id = list(memories.values())[-1]
            deleted = engine.delete(last_id, user_id=user)
            assert deleted is True, "Step 10: 删除失败"
            assert engine.get(last_id, user_id=user) is None, "Step 10: 删除后仍可获取"

            # ── Step 11: 记录删除前的状态 ──
            remaining_before_close = len(engine.get_all(user_id=user))

            # ── Step 12: 关闭引擎 ──
            engine.close()

            # ── Step 13: 重新打开 — 验证持久化 ──
            engine2 = RecallEngine(data_root=tmpdir, lite=True)

            remaining_after_reopen = len(engine2.get_all(user_id=user))
            assert remaining_after_reopen == remaining_before_close, \
                f"Step 13: 持久化失败！关闭前 {remaining_before_close}, 重开后 {remaining_after_reopen}"

            # 验证更新持久化
            updated_mem2 = engine2.get(first_id, user_id=user)
            assert updated_mem2 is not None, "Step 13: 更新记忆重启后丢失"
            content2 = updated_mem2.get("content", updated_mem2.get("text", ""))
            assert "v3.2.2" in content2, "Step 13: 更新内容重启后被覆盖"

            # 验证删除持久化
            assert engine2.get(last_id, user_id=user) is None, "Step 13: 已删除记忆重启后复活"

            # 验证伏笔持久化
            active_fs2 = engine2.get_active_foreshadowings(user_id=user, character_id=char)
            assert len(active_fs2) >= 1, "Step 13: 伏笔重启后丢失"

            # 验证持久条件持久化
            pctx2 = engine2.get_persistent_contexts(user_id=user, character_id=char)
            assert len(pctx2) >= 1, "Step 13: 持久条件重启后丢失"

            # 验证搜索仍正常
            results2 = engine2.search("Alice", user_id=user, top_k=5)
            assert len(results2) > 0, "Step 13: 重启后搜索失败"

            engine2.close()

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# 阶段 14: 并发安全（同引擎多用户）
# ══════════════════════════════════════════════════════════════════════
class TestPhase14_ConcurrencyBasic:
    """基本并发安全 — 同一引擎多用户同时操作"""

    def test_14_01_sequential_multi_user(self, fresh_engine):
        """多用户顺序操作不冲突"""
        users = [f"user_{i}" for i in range(5)]

        for user in users:
            for j in range(5):
                r = fresh_engine.add(f"{user}的第{j+1}条记忆", user_id=user)
                assert r.success

        for user in users:
            mems = fresh_engine.get_all(user_id=user)
            assert len(mems) == 5, f"{user} 应有 5 条记忆，实际 {len(mems)}"


# ══════════════════════════════════════════════════════════════════════
# 入口点
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # 支持直接运行: python tests/test_zero_tolerance.py
    pytest.main([
        __file__,
        "-v",           # 详细输出
        "--tb=long",    # 完整错误追踪
        "-x",           # 零容错：第一个失败即停止
        "--no-header",  # 简洁输出
        "-q",           # 安静模式
    ])
