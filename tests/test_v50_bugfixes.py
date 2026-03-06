"""v5.0 三大 BUG 修复验证测试

BUG 1: 搜索 API 未暴露元数据过滤参数 (server.py SearchRequest + 搜索端点)
BUG 2: add_batch() 不写知识图谱/全文索引 (engine.py _add_single_fast + _batch_update_indexes)
BUG 3: MetadataIndex 无删除方法 (metadata_index.py + engine.py delete/clear)
"""

import os
import sys
import json
import tempfile
import shutil

# === 测试 1: MetadataIndex remove / remove_batch / clear ===

def test_metadata_index_crud():
    """测试 MetadataIndex 的增删清操作"""
    from recall.index.metadata_index import MetadataIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        idx = MetadataIndex(tmpdir)
        
        # 添加 3 条记忆
        idx.add("mem_001", source="bilibili", tags=["AI", "热点"], category="科技", content_type="video")
        idx.add("mem_002", source="twitter", tags=["AI"], category="科技", content_type="text")
        idx.add("mem_003", source="bilibili", tags=["游戏"], category="娱乐", content_type="video")
        
        # 验证查询
        assert idx.query(source="bilibili") == {"mem_001", "mem_003"}, "bilibili 来源应有 2 条"
        assert idx.query(tags=["AI"]) == {"mem_001", "mem_002"}, "AI 标签应有 2 条"
        assert idx.query(source="bilibili", tags=["AI"]) == {"mem_001"}, "AND 查询应有 1 条"
        assert idx.query(category="科技") == {"mem_001", "mem_002"}, "科技类别应有 2 条"
        assert idx.query(content_type="video") == {"mem_001", "mem_003"}, "video 类型应有 2 条"
        
        # 测试 remove 单条
        idx.remove("mem_001")
        assert idx.query(source="bilibili") == {"mem_003"}, "删除后 bilibili 应只剩 1 条"
        assert idx.query(tags=["AI"]) == {"mem_002"}, "删除后 AI 标签应只剩 1 条"
        assert idx.query(category="科技") == {"mem_002"}, "删除后科技类别应只剩 1 条"
        assert idx.query(content_type="video") == {"mem_003"}, "删除后 video 类型应只剩 1 条"
        
        # 测试 remove_batch 批量删除
        idx.add("mem_004", source="hackernews", tags=["编程"], category="技术")
        idx.remove_batch({"mem_002", "mem_003"})
        assert idx.query(source="twitter") == set(), "批量删除后 twitter 应为空"
        assert idx.query(source="bilibili") == set(), "批量删除后 bilibili 应为空"
        assert idx.query(source="hackernews") == {"mem_004"}, "未删除的应保留"
        
        # 测试 clear 清空
        idx.clear()
        assert idx.query(source="hackernews") == set(), "清空后应为空"
        assert idx.query(tags=["编程"]) == set(), "清空后标签应为空"
        
        # 测试持久化：添加后 flush，重新加载
        idx.add("mem_010", source="github", tags=["开源"])
        idx.flush()
        idx2 = MetadataIndex(tmpdir)
        assert idx2.query(source="github") == {"mem_010"}, "持久化加载应正确"
        
        # 测试 remove 后持久化
        idx2.remove("mem_010")
        idx2.flush()
        idx3 = MetadataIndex(tmpdir)
        assert idx3.query(source="github") == set(), "删除后持久化应为空"
        
    print("  ✅ test_metadata_index_crud PASSED")


def test_metadata_index_remove_nonexistent():
    """删除不存在的 memory_id 应该不报错"""
    from recall.index.metadata_index import MetadataIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        idx = MetadataIndex(tmpdir)
        idx.add("mem_001", source="bilibili")
        
        # 删除不存在的 ID，不应报错
        idx.remove("nonexistent_id")
        idx.remove_batch({"nonexistent_1", "nonexistent_2"})
        
        # 原有数据应不受影响
        assert idx.query(source="bilibili") == {"mem_001"}, "删除不存在的 ID 不应影响现有数据"
    
    print("  ✅ test_metadata_index_remove_nonexistent PASSED")


# === 测试 2: SearchRequest 元数据过滤字段 ===

def test_search_request_model():
    """测试 SearchRequest 模型包含 v5.0 元数据字段"""
    from recall.server import SearchRequest
    
    # 测试基本创建（无元数据过滤）
    req = SearchRequest(query="test")
    assert req.source is None, "默认 source 应为 None"
    assert req.tags is None, "默认 tags 应为 None"
    assert req.category is None, "默认 category 应为 None"
    assert req.content_type is None, "默认 content_type 应为 None"
    
    # 测试带元数据过滤
    req2 = SearchRequest(
        query="AI 热点",
        source="bilibili",
        tags=["AI", "热点"],
        category="科技",
        content_type="video"
    )
    assert req2.source == "bilibili"
    assert req2.tags == ["AI", "热点"]
    assert req2.category == "科技"
    assert req2.content_type == "video"
    
    # 测试 JSON 序列化/反序列化
    data = req2.model_dump()
    assert data["source"] == "bilibili"
    assert data["tags"] == ["AI", "热点"]
    
    # 确保不破坏原有字段
    req3 = SearchRequest(query="test", top_k=20, config_preset="fast")
    assert req3.top_k == 20
    assert req3.config_preset == "fast"
    assert req3.source is None
    
    print("  ✅ test_search_request_model PASSED")


# === 测试 3: engine.search() 元数据过滤参数签名 ===

def test_engine_search_signature():
    """验证 engine.search() 接受 v5.0 元数据过滤参数"""
    import inspect
    from recall.engine import RecallEngine
    
    sig = inspect.signature(RecallEngine.search)
    params = list(sig.parameters.keys())
    
    assert "source" in params, "search() 应有 source 参数"
    assert "tags" in params, "search() 应有 tags 参数"
    assert "category" in params, "search() 应有 category 参数"
    assert "content_type" in params, "search() 应有 content_type 参数"
    
    # 确保默认值都是 None
    assert sig.parameters["source"].default is None
    assert sig.parameters["tags"].default is None
    assert sig.parameters["category"].default is None
    assert sig.parameters["content_type"].default is None
    
    print("  ✅ test_engine_search_signature PASSED")


# === 测试 4: _add_single_fast 返回关系 ===

def test_add_single_fast_returns_relations():
    """验证 _add_single_fast 返回值包含 relations（4 元素元组）"""
    import inspect
    from recall.memory_ops import MemoryOperations
    
    # 通过 source code 验证返回值格式（实现在 MemoryOperations 中）
    source = inspect.getsource(MemoryOperations._add_single_fast)
    assert "return (memory_id, entities, keywords, relations)" in source, \
        "_add_single_fast 应返回 (memory_id, entities, keywords, relations)"
    assert "relation_extractor.extract" in source, \
        "_add_single_fast 应调用 relation_extractor.extract"
    
    print("  ✅ test_add_single_fast_returns_relations PASSED")


# === 测试 5: add_batch 收集 relations 并传给 _batch_update_indexes ===

def test_add_batch_collects_relations():
    """验证 add_batch 正确解包 4 元素结果并传递 all_relations"""
    import inspect
    from recall.memory_ops import MemoryOperations
    
    source = inspect.getsource(MemoryOperations.add_batch)
    assert "all_relations" in source, "add_batch 应声明 all_relations 列表"
    assert "memory_id, entities, keywords, relations = result" in source, \
        "add_batch 应解包 4 元素元组"
    assert "all_relations.extend(relations)" in source, \
        "add_batch 应收集 relations"
    assert "_batch_update_indexes(all_keywords, all_entities, all_ngram_data, all_relations)" in source, \
        "add_batch 应将 all_relations 传给 _batch_update_indexes"
    
    print("  ✅ test_add_batch_collects_relations PASSED")


# === 测试 6: _batch_update_indexes 包含 KG 和全文索引更新 ===

def test_batch_update_indexes_has_kg_and_fulltext():
    """验证 _batch_update_indexes 包含知识图谱和全文索引更新"""
    import inspect
    from recall.memory_ops import MemoryOperations
    
    source = inspect.getsource(MemoryOperations._batch_update_indexes)
    sig = inspect.signature(MemoryOperations._batch_update_indexes)
    
    # 验证签名
    assert "all_relations" in sig.parameters, "_batch_update_indexes 应有 all_relations 参数"
    
    # 验证包含知识图谱更新（MemoryOperations 中使用 engine. 前缀）
    assert "knowledge_graph" in source, "应包含知识图谱更新逻辑"
    assert "knowledge_graph.add_relation" in source, "应调用 knowledge_graph.add_relation"
    
    # 验证包含全文索引更新
    assert "fulltext_index" in source, "应包含全文索引更新逻辑"
    assert "fulltext_index.add" in source, "应调用 fulltext_index.add"
    
    print("  ✅ test_batch_update_indexes_has_kg_and_fulltext PASSED")


# === 测试 7: engine.delete() 调用 metadata_index.remove ===

def test_engine_delete_cleans_metadata():
    """验证 engine.delete() 调用 metadata_index.remove()"""
    import inspect
    from recall.memory_ops import MemoryOperations
    
    source = inspect.getsource(MemoryOperations.delete)
    assert "_metadata_index" in source, "delete() 应检查 _metadata_index"
    assert "_metadata_index.remove(memory_id)" in source, "delete() 应调用 _metadata_index.remove"
    
    print("  ✅ test_engine_delete_cleans_metadata PASSED")


# === 测试 8: clear (per-user) 和 clear_all 包含 MetadataIndex 清理 ===

def test_clear_includes_metadata_cleanup():
    """验证 clear() 和 clear_all() 包含 MetadataIndex 清理"""
    import inspect
    from recall.memory_ops import MemoryOperations
    from recall.engine import RecallEngine
    
    # per-user clear（实现在 MemoryOperations 中）
    clear_source = inspect.getsource(MemoryOperations.clear)
    assert "_metadata_index" in clear_source, "clear() 应包含 _metadata_index 清理"
    assert "remove_batch" in clear_source, "clear() 应调用 remove_batch"
    
    # clear_all（v7.0.7: 已委托到 MemoryOperations.clear_all()）
    clear_all_source = inspect.getsource(MemoryOperations.clear_all)
    assert "_metadata_index" in clear_all_source, "clear_all() 应包含 _metadata_index 清理"
    
    # 验证 engine.clear_all 正确委托
    engine_clear_all_source = inspect.getsource(RecallEngine.clear_all)
    assert "_memory_ops" in engine_clear_all_source, "engine.clear_all() 应委托到 _memory_ops"
    
    print("  ✅ test_clear_includes_metadata_cleanup PASSED")


# === 测试 9: MCP recall_search_filtered 使用引擎原生过滤 ===

def test_mcp_search_filtered_uses_engine_params():
    """验证 MCP recall_search_filtered 使用 engine.search(source=, tags=) 而非 Python 后过滤"""
    source_path = os.path.join(os.path.dirname(__file__), '..', 'recall', 'mcp', 'tools.py')
    with open(source_path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    # 找到 recall_search_filtered 部分
    idx = source.find('elif name == "recall_search_filtered"')
    assert idx >= 0, "应存在 recall_search_filtered handler"
    
    # 在该部分内，engine.search 应传递 source 和 tags 参数
    handler_section = source[idx:idx+500]
    assert 'source=arguments.get("source")' in handler_section, \
        "recall_search_filtered 应将 source 传给 engine.search()"
    assert 'tags=arguments.get("tags")' in handler_section, \
        "recall_search_filtered 应将 tags 传给 engine.search()"
    
    # 确保没有 Python 后过滤
    assert "r.metadata.get" not in handler_section, \
        "recall_search_filtered 不应再做 Python 级后过滤"
    
    print("  ✅ test_mcp_search_filtered_uses_engine_params PASSED")


# === 测试 10: 现有功能不受影响 ===

def test_no_regression_search_request():
    """确保原有 SearchRequest 字段和行为不受影响"""
    from recall.server import SearchRequest
    
    # 原有字段仍可用
    req = SearchRequest(
        query="hello",
        user_id="u1",
        top_k=5,
        filters={"key": "value"},
        config_preset="fast"
    )
    assert req.query == "hello"
    assert req.user_id == "u1"
    assert req.top_k == 5
    assert req.filters == {"key": "value"}
    assert req.config_preset == "fast"
    
    # 新字段可选，不提供时为 None
    assert req.source is None
    assert req.tags is None
    assert req.category is None
    assert req.content_type is None
    
    print("  ✅ test_no_regression_search_request PASSED")


def test_no_regression_metadata_index():
    """确保原有 MetadataIndex 功能不受影响"""
    from recall.index.metadata_index import MetadataIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        idx = MetadataIndex(tmpdir)
        
        # 原有 add + query 不变
        idx.add("m1", source="s1", tags=["t1", "t2"], category="c1", content_type="ct1")
        idx.add("m2", source="s1", tags=["t2"], category="c2", content_type="ct1")
        
        assert idx.query(source="s1") == {"m1", "m2"}
        assert idx.query(tags=["t1"]) == {"m1"}
        assert idx.query(tags=["t2"]) == {"m1", "m2"}
        assert idx.query(source="s1", tags=["t2"]) == {"m1", "m2"}
        assert idx.query(category="c1") == {"m1"}
        
        # flush + 重新加载
        idx.flush()
        idx2 = MetadataIndex(tmpdir)
        assert idx2.query(source="s1") == {"m1", "m2"}
        assert idx2.query(tags=["t1"]) == {"m1"}
    
    print("  ✅ test_no_regression_metadata_index PASSED")


def test_no_regression_batch_update_indexes():
    """确保 _batch_update_indexes 不带 all_relations 参数时仍正常工作（向后兼容）"""
    import inspect
    from recall.engine import RecallEngine
    
    sig = inspect.signature(RecallEngine._batch_update_indexes)
    param = sig.parameters["all_relations"]
    assert param.default is None, "all_relations 默认值应为 None（向后兼容）"
    
    print("  ✅ test_no_regression_batch_update_indexes PASSED")


# === 测试 11: 中文编码正确性 ===

def test_chinese_encoding():
    """验证中文内容在 MetadataIndex 序列化/反序列化中不会乱码"""
    from recall.index.metadata_index import MetadataIndex
    
    with tempfile.TemporaryDirectory() as tmpdir:
        idx = MetadataIndex(tmpdir)
        idx.add("mem_cn", source="小红书", tags=["热点分析", "人工智能"], category="科技新闻")
        idx.flush()
        
        # 验证 JSON 文件内的中文不是 unicode 转义
        json_path = os.path.join(tmpdir, 'metadata_index.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            raw = f.read()
        
        assert "小红书" in raw, "JSON 文件应包含中文原文，非 unicode 转义"
        assert "热点分析" in raw, "JSON 文件应包含中文标签"
        assert "科技新闻" in raw, "JSON 文件应包含中文分类"
        
        # 重新加载后查询
        idx2 = MetadataIndex(tmpdir)
        assert idx2.query(source="小红书") == {"mem_cn"}, "中文来源查询应正确"
        assert idx2.query(tags=["热点分析"]) == {"mem_cn"}, "中文标签查询应正确"
        assert idx2.query(category="科技新闻") == {"mem_cn"}, "中文分类查询应正确"
    
    print("  ✅ test_chinese_encoding PASSED")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Recall v5.0 三大 BUG 修复验证测试")
    print("="*60)
    
    tests = [
        # BUG 3: MetadataIndex 删除
        ("BUG3", "MetadataIndex CRUD", test_metadata_index_crud),
        ("BUG3", "MetadataIndex remove 不存在的 ID", test_metadata_index_remove_nonexistent),
        
        # BUG 1: 搜索 API 元数据过滤
        ("BUG1", "SearchRequest 模型字段", test_search_request_model),
        ("BUG1", "engine.search() 参数签名", test_engine_search_signature),
        
        # BUG 2: add_batch 知识图谱/全文索引
        ("BUG2", "_add_single_fast 返回 relations", test_add_single_fast_returns_relations),
        ("BUG2", "add_batch 收集 relations", test_add_batch_collects_relations),
        ("BUG2", "_batch_update_indexes KG+fulltext", test_batch_update_indexes_has_kg_and_fulltext),
        
        # BUG 3: engine 端删除清理
        ("BUG3", "engine.delete() 清理 metadata", test_engine_delete_cleans_metadata),
        ("BUG3", "clear/clear_all 包含 metadata 清理", test_clear_includes_metadata_cleanup),
        
        # MCP 优化
        ("BUG1", "MCP search_filtered 引擎原生过滤", test_mcp_search_filtered_uses_engine_params),
        
        # 回归测试
        ("回归", "SearchRequest 原有功能不变", test_no_regression_search_request),
        ("回归", "MetadataIndex 原有功能不变", test_no_regression_metadata_index),
        ("回归", "_batch_update_indexes 向后兼容", test_no_regression_batch_update_indexes),
        
        # 编码测试
        ("编码", "中文内容编码正确", test_chinese_encoding),
    ]
    
    passed = 0
    failed = 0
    
    for bug_id, name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"  ❌ [{bug_id}] {name} FAILED: {e}")
            traceback.print_exc()
    
    print("\n" + "="*60)
    print(f"  结果: {passed} 通过, {failed} 失败 / 共 {passed + failed} 项")
    print("="*60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("  🎉 全部通过！")
        sys.exit(0)
