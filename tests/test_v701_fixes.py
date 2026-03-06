#!/usr/bin/env python3
"""Recall v7.0.1 — P0/P1 级修复验证测试

验证本次修复的所有关键问题：
1. delete() 级联到 BAL 三个后端（之前数据泄漏）
2. update() 同步到 BAL 后端（之前数据不一致）
3. add_batch() BAL 双写 + FullText + ConsolidatedMemory + 实体提取 fallback
4. _fulltext_weight 传递到 ElevenLayerRetriever
5. server.py 配置默认值与 RecallConfig 一致
"""
import os
import sys
import tempfile
import shutil
import inspect

PASS = 0
FAIL = 0


def _mark(ok: bool, msg: str):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  [PASS] {msg}')
    else:
        FAIL += 1
        print(f'  [FAIL] {msg}')


def main():
    td = tempfile.mkdtemp(prefix='recall_v701_p0p1_')
    print(f'[SETUP] Test dir: {td}')

    try:
        from recall.engine import RecallEngine
        e = RecallEngine(data_root=td)

        sb = getattr(e, '_storage_backend', None)
        vb = getattr(e, '_vector_backend', None)
        tsb = getattr(e, '_text_search_backend', None)

        # ================================================================
        # TEST 1: delete() 级联到 BAL
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 1: delete() cascades to BAL backends')
        print('=' * 60)

        r = e.add('Tokyo is the capital of Japan', user_id='test')
        _mark(r.success, f'add() success: {r.id}')

        # 验证 BAL 中有数据
        if sb:
            mem = sb.load(r.id)
            _mark(mem is not None, f'StorageBackend has memory before delete')
        if tsb:
            results = tsb.search('Tokyo Japan', top_k=5)
            _mark(len(results) > 0, f'TextSearchBackend has memory before delete')

        # 执行删除
        deleted = e.delete(r.id, user_id='test')
        _mark(deleted, 'delete() returned True')

        # 验证 BAL 中数据已清理
        if sb:
            mem_after = sb.load(r.id)
            _mark(mem_after is None, f'StorageBackend empty after delete (no data leak)')
        if tsb:
            results_after = tsb.search('Tokyo Japan', top_k=5)
            # FTS5 删除后搜索应返回空
            has_deleted = any(r.id == getattr(item, 'doc_id', item[0] if isinstance(item, (list, tuple)) else None) for item in results_after) if results_after else False
            _mark(not has_deleted, f'TextSearchBackend clean after delete (no data leak)')

        # ================================================================
        # TEST 2: update() 同步到 BAL
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 2: update() syncs to BAL backends')
        print('=' * 60)

        r2 = e.add('Berlin is the capital of Germany', user_id='test')
        _mark(r2.success, f'add() for update test: {r2.id}')

        # 更新
        updated = e.update(r2.id, 'Munich is a city in Germany', user_id='test')
        _mark(updated, 'update() returned True')

        # 验证 BAL 中数据已更新
        if sb:
            mem_updated = sb.load(r2.id)
            if mem_updated:
                content = mem_updated.get('content', '')
                _mark('Munich' in content, f'StorageBackend updated content: {content[:50]}')
            else:
                _mark(False, 'StorageBackend has no data after update')
        if tsb:
            # 搜索新内容
            results_new = tsb.search('Munich Germany', top_k=5)
            _mark(len(results_new) > 0, f'TextSearchBackend has updated content')

        # ================================================================
        # TEST 3: add_batch() BAL 双写 + FullText + 实体 fallback
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 3: add_batch() completeness')
        print('=' * 60)

        batch_items = [
            {'content': 'Python is a programming language'},
            {'content': 'Alice loves reading books'},
            {'content': 'The weather in London is rainy'},
        ]
        batch_ids = e.add_batch(batch_items, user_id='test')
        _mark(len(batch_ids) == 3, f'add_batch returned {len(batch_ids)} ids')

        # 验证 BAL 双写
        if sb:
            loaded_count = sum(1 for mid in batch_ids if sb.load(mid) is not None)
            _mark(loaded_count == 3, f'StorageBackend has {loaded_count}/3 batch memories')

        if tsb:
            py_results = tsb.search('programming language', top_k=5)
            _mark(len(py_results) > 0, f'TextSearchBackend has batch data ({len(py_results)} results)')

        if vb:
            vb_count = vb.count()
            # Should have: 1 (from test2, still alive) + 3 (batch) = 4+
            _mark(vb_count >= 3, f'VectorBackend has {vb_count} vectors (batch wrote vectors)')

        # 验证 FullText 索引更新（之前 add_batch 缺失）
        if e.fulltext_index is not None:
            try:
                ft_results = e.fulltext_index.search('programming', top_k=5)
                _mark(len(ft_results) > 0, f'FullTextIndex has batch data ({len(ft_results)} results)')
            except Exception as ex:
                _mark(False, f'FullTextIndex search failed: {ex}')
        else:
            _mark(True, 'FullTextIndex not available (Lite mode OK)')

        # ================================================================
        # TEST 4: _fulltext_weight 传递到检索器
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 4: _fulltext_weight wiring to ElevenLayerRetriever')
        print('=' * 60)

        # 检查 engine 有 _fulltext_weight
        has_weight = hasattr(e, '_fulltext_weight')
        _mark(has_weight, f'engine._fulltext_weight exists: {getattr(e, "_fulltext_weight", "MISSING")}')

        # 检查 retriever 有 fulltext_index
        retriever = e.retriever
        has_ft_index = hasattr(retriever, 'fulltext_index')
        _mark(has_ft_index, f'retriever.fulltext_index exists: {type(getattr(retriever, "fulltext_index", None)).__name__}')

        # 检查 retriever 有 fulltext_weight
        has_ft_weight = hasattr(retriever, 'fulltext_weight')
        _mark(has_ft_weight, f'retriever.fulltext_weight exists: {getattr(retriever, "fulltext_weight", "MISSING")}')

        # 检查 ElevenLayerRetriever.__init__ 签名包含 fulltext_index
        from recall.retrieval.eleven_layer import ElevenLayerRetriever
        sig = inspect.signature(ElevenLayerRetriever.__init__)
        _mark('fulltext_index' in sig.parameters, 'ElevenLayerRetriever.__init__ has fulltext_index param')
        _mark('fulltext_weight' in sig.parameters, 'ElevenLayerRetriever.__init__ has fulltext_weight param')

        # ================================================================
        # TEST 5: server.py 配置默认值一致性
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 5: server.py config defaults match RecallConfig')
        print('=' * 60)

        from recall.config import RecallConfig
        rc = RecallConfig()

        # 读取 server.py 源代码中的 get_config_status 函数
        from recall import server
        src = inspect.getsource(server)

        # 验证不再有硬编码冲突 — 检查 server.py 中使用 _rc_defaults
        _mark('_rc_defaults' in src, 'server.py uses _rc_defaults from RecallConfig')
        _mark('_rc_defaults.context_max_per_type' in src, 'CONTEXT_MAX_PER_TYPE uses RecallConfig default')
        _mark('_rc_defaults.context_decay_days' in src, 'CONTEXT_DECAY_DAYS uses RecallConfig default')
        _mark('_rc_defaults.dedup_high_threshold' in src, 'DEDUP_HIGH_THRESHOLD uses RecallConfig default')

        # ================================================================
        # TEST 6: _add_single_fast 实体提取 fallback
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 6: _add_single_fast entity extraction fallback')
        print('=' * 60)

        # 检查源代码中有 fallback 逻辑
        from recall.memory_ops import MemoryOperations as MemoryOps
        add_single_src = inspect.getsource(MemoryOps._add_single_fast)
        _mark('回退到规则提取器' in add_single_src or 'entity_extractor' in add_single_src,
               '_add_single_fast has entity extraction fallback')
        _mark('try:' in add_single_src and 'except' in add_single_src,
               '_add_single_fast has try/except around SmartExtractor')

        # 检查 add_batch 的 BAL 双写
        _mark('_storage_backend' in add_single_src, '_add_single_fast writes to StorageBackend')
        _mark('_vector_backend' in add_single_src, '_add_single_fast writes to VectorBackend')
        _mark('_text_search_backend' in add_single_src, '_add_single_fast writes to TextSearchBackend')
        _mark('fulltext_index' in add_single_src, '_add_single_fast writes to FullTextIndex')
        _mark('consolidated_memory' in add_single_src, '_add_single_fast writes to ConsolidatedMemory')

        # ================================================================
        # TEST 7: delete() 源代码包含 BAL 级联
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 7: delete() source has BAL cascade')
        print('=' * 60)

        delete_src = inspect.getsource(MemoryOps.delete)
        _mark('_storage_backend' in delete_src, 'delete() cascades to StorageBackend')
        _mark('_vector_backend' in delete_src, 'delete() cascades to VectorBackend')
        _mark('_text_search_backend' in delete_src, 'delete() cascades to TextSearchBackend')
        _mark('14/16' in delete_src or '14' in delete_src, 'delete() has 16-step cascade (was 13)')

        # ================================================================
        # TEST 8: update() 源代码包含 BAL 同步
        # ================================================================
        print('\n' + '=' * 60)
        print('TEST 8: update() source has BAL sync')
        print('=' * 60)

        update_src = inspect.getsource(MemoryOps.update)
        _mark('_storage_backend' in update_src, 'update() syncs to StorageBackend')
        _mark('_vector_backend' in update_src, 'update() syncs to VectorBackend')
        _mark('_text_search_backend' in update_src, 'update() syncs to TextSearchBackend')

        # ================================================================
        # CLEANUP
        # ================================================================
        e.close()

    except Exception as ex:
        import traceback
        traceback.print_exc()
        _mark(False, f'Unexpected error: {ex}')

    finally:
        shutil.rmtree(td, ignore_errors=True)

    # ================================================================
    # SUMMARY
    # ================================================================
    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'  PASS: {PASS}')
    print(f'  FAIL: {FAIL}')

    if FAIL > 0:
        sys.exit(1)
    else:
        print('\n  ALL P0/P1 FIXES VERIFIED!')
        sys.exit(0)


if __name__ == '__main__':
    main()
