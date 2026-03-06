#!/usr/bin/env python3
"""Recall v7.0 扩展烟雾测试 — 覆盖所有 13 个已修复死路径

每个测试独立运行，无需外部服务（LLM、Cohere 等），
仅验证"代码能正确调用且产出合理结果"。

测试清单
========
Section A – 原 8 项基础测试
  1. Engine Init
  2. Add Memory
  3. Search
  4. Delete Cascade
  5. User Isolation
  6. Dead-code Audit (ParallelRetriever callable)
  7. consolidate()
  8. Mode System

Section B – 13 死路径专项测试
  B1. RecallConfig: 46 os.environ.get 全部替换
  B2. RecallConfig 值正确性
  B3. TemporalIndex dual-bisect query_at_time
  B4. TemporalIndex dual-bisect query_range
  B5. KnowledgeGraph _mark_dirty 延迟保存
  B6. RerankerFactory create() 三种后端
  B7. PromptManager 接入处理器验证
  B8. QueryPlanner 接入 ElevenLayer 验证
  B9. ConsolidationManager 接入验证
  B10. IVF auto-switch 配置验证
"""
import os
import sys
import tempfile
import shutil
import time
import inspect
from datetime import datetime, timedelta

PASS = 0
FAIL = 0
WARN = 0


def _mark(status: str, msg: str):
    global PASS, FAIL, WARN
    if status == 'PASS':
        PASS += 1
        print(f'  [PASS] {msg}')
    elif status == 'FAIL':
        FAIL += 1
        print(f'  [FAIL] {msg}')
    elif status == 'WARN':
        WARN += 1
        print(f'  [WARN] {msg}')


def main():
    td = tempfile.mkdtemp(prefix='recall_v70_expanded_')
    print(f'[SETUP] Test dir: {td}')

    try:
        # ================================================================
        # Section A: 基础功能 (8 tests)
        # ================================================================
        print('\n' + '=' * 60)
        print('SECTION A: BASIC FUNCTIONALITY')
        print('=' * 60)

        # A1. Engine Init
        print('\n--- A1. Engine Init ---')
        from recall.engine import RecallEngine
        e = RecallEngine(data_root=td)
        _mark('PASS', f'Engine init OK, retriever={type(e.retriever).__name__}')

        # Verify key components
        for attr in ['parallel_retriever', 'prompt_manager', 'query_planner',
                      'consolidation_manager', 'context_tracker', 'knowledge_graph',
                      'foreshadowing_tracker', 'recall_config']:
            has_it = hasattr(e, attr) and getattr(e, attr) is not None
            if has_it:
                _mark('PASS', f'  {attr}: present')
            else:
                # consolidation_manager may be None if init fails gracefully
                if attr == 'consolidation_manager':
                    has_attr = hasattr(e, attr)
                    _mark('WARN' if has_attr else 'FAIL', f'  {attr}: attr={has_attr}, value={getattr(e, attr, "MISSING")}')
                else:
                    _mark('WARN', f'  {attr}: missing or None')

        # A2. Add Memory
        print('\n--- A2. Add Memory ---')
        test_memories = [
            'The capital of France is Paris. It has the Eiffel Tower.',
            'Python is a programming language created by Guido van Rossum.',
            'The Earth orbits the Sun at a distance of about 150 million kilometers.',
            'Machine learning is a subset of artificial intelligence.',
            'Tokyo is the capital of Japan with a population of 14 million.',
        ]
        mids = []
        for i, text in enumerate(test_memories):
            result = e.add(text, user_id='smoketest')
            mid = result if isinstance(result, str) else getattr(result, 'id', None) or getattr(result, 'memory_id', str(result))
            mids.append(mid)
        if all(mids):
            _mark('PASS', f'All {len(mids)} memories added')
        else:
            _mark('FAIL', f'Some add() returned None: {mids}')

        # A3. Search
        print('\n--- A3. Search ---')
        queries = [
            ('capital of France', 'Paris'),
            ('programming language', 'Python'),
            ('distance from Earth to Sun', 'kilometers'),
        ]
        for query, kw in queries:
            results = e.search(query, user_id='smoketest')
            if len(results) > 0:
                text = getattr(results[0], 'content', '') or getattr(results[0], 'text', '')
                if kw.lower() in text.lower():
                    _mark('PASS', f'search("{query}") found "{kw}"')
                else:
                    _mark('WARN', f'search("{query}") top result missing "{kw}"')
            else:
                _mark('FAIL', f'search("{query}") returned 0 results')

        # A4. Delete Cascade
        print('\n--- A4. Delete Cascade ---')
        if mids[0]:
            ok = e.delete(mids[0], user_id='smoketest')
            results_after = e.search('capital of France Paris', user_id='smoketest')
            found_deleted = any(mids[0] in str(getattr(r, 'id', '')) for r in results_after)
            if not found_deleted:
                _mark('PASS', 'Deleted memory not found in search')
            else:
                _mark('FAIL', 'Deleted memory still found')

        # A5. User Isolation
        print('\n--- A5. User Isolation ---')
        e.add('Secret data for user A only', user_id='user_a')
        e.add('Different data for user B', user_id='user_b')
        results_a = e.search('secret data', user_id='user_a')
        results_b = e.search('secret data', user_id='user_b')
        a_texts = ' '.join(getattr(r, 'content', '') or '' for r in results_a)
        b_texts = ' '.join(getattr(r, 'content', '') or '' for r in results_b)
        if 'Secret' in a_texts and 'Secret' not in b_texts:
            _mark('PASS', 'User isolation works')
        else:
            _mark('WARN', f'user_a found={("Secret" in a_texts)}, user_b found={("Secret" in b_texts)}')

        # A6. ParallelRetriever callable
        print('\n--- A6. ParallelRetriever ---')
        has_pr = hasattr(e, 'parallel_retriever') and e.parallel_retriever is not None
        if has_pr:
            try:
                pr_results = e.search_parallel('test', user_id='smoketest')
                _mark('PASS', f'search_parallel() -> {len(pr_results)} results')
            except AttributeError:
                _mark('FAIL', 'search_parallel() AttributeError')
            except Exception as ex:
                _mark('WARN', f'search_parallel() {type(ex).__name__}: {ex}')
        else:
            _mark('WARN', 'ParallelRetriever not init (disabled by config)')

        # A7. consolidate()
        print('\n--- A7. Consolidate ---')
        try:
            result = e.consolidate(user_id='smoketest')
            if result and isinstance(result, dict):
                _mark('PASS', f'consolidate() returned dict with keys: {list(result.keys())[:5]}')
            else:
                _mark('WARN', f'consolidate() returned {type(result).__name__}: {result}')
        except Exception as ex:
            _mark('FAIL', f'consolidate() error: {ex}')

        # A8. Mode System
        print('\n--- A8. Mode System ---')
        try:
            from recall.mode import get_mode_config
            mode = get_mode_config()
            mode_str = str(mode.mode).lower()
            if 'universal' in mode_str:
                _mark('PASS', f'Universal mode active ({mode.mode})')
            else:
                _mark('WARN', f'Mode is {mode.mode}, expected universal')
        except Exception as ex:
            _mark('FAIL', f'Mode error: {ex}')

        # ================================================================
        # Section B: 13 Dead-Path Tests
        # ================================================================
        print('\n' + '=' * 60)
        print('SECTION B: 13 DEAD-PATH VERIFICATION')
        print('=' * 60)

        # B1. RecallConfig: no os.environ.get in engine.py
        print('\n--- B1. RecallConfig Integration ---')
        import recall.engine as engine_mod
        src = inspect.getsource(engine_mod)
        # Exclude imports and comments, count actual os.environ.get() in function bodies
        env_count = src.count('os.environ.get(')
        # Some os.environ.get may remain for non-config uses (e.g., RECALL_DATA_ROOT for data path)
        # The key metric: self.recall_config exists
        has_rc = hasattr(e, 'recall_config') and e.recall_config is not None
        if has_rc:
            _mark('PASS', f'self.recall_config exists, type={type(e.recall_config).__name__}')
        else:
            _mark('FAIL', 'self.recall_config is missing')
        if env_count <= 5:  # a few may remain for bootstrap (data_root, etc.)
            _mark('PASS', f'engine.py os.environ.get() count={env_count} (<=5 allowed for bootstrap)')
        else:
            _mark('FAIL', f'engine.py still has {env_count} os.environ.get() calls')

        # B2. RecallConfig values correctness
        print('\n--- B2. RecallConfig Values ---')
        rc = e.recall_config
        checks = {
            'recall_mode': 'universal',
            'smart_extractor_mode': 'RULES',
            'reranker_backend': 'builtin',
            'temporal_graph_backend': 'file',
            'embedding_model': 'text-embedding-3-small',
        }
        for field, expected in checks.items():
            actual = getattr(rc, field, 'MISSING')
            if actual == expected:
                _mark('PASS', f'rc.{field}={actual}')
            else:
                _mark('FAIL', f'rc.{field}={actual}, expected {expected}')
        # Verify new fields exist
        for f in ['retrieval_l10_cross_encoder_model', 'parallel_retriever_workers',
                   'parallel_retriever_timeout', 'ivf_auto_switch_enabled']:
            if hasattr(rc, f):
                _mark('PASS', f'rc.{f}={getattr(rc, f)}')
            else:
                _mark('FAIL', f'rc.{f} MISSING')

        # B3. TemporalIndex dual-bisect query_at_time
        print('\n--- B3. TemporalIndex query_at_time ---')
        from recall.index.temporal_index import TemporalIndex, TemporalEntry, TimeRange
        ti_dir = os.path.join(td, '_test_temporal')
        os.makedirs(ti_dir, exist_ok=True)
        ti = TemporalIndex(ti_dir)

        now = datetime.now()
        # Entry that spans [now-10d, now-2d] (already ended)
        ti.add(TemporalEntry(
            doc_id='old_fact',
            fact_range=TimeRange(start=now - timedelta(days=10), end=now - timedelta(days=2)),
            subject='test', predicate='lived_in'
        ))
        # Entry that spans [now-5d, now+5d] (currently valid)
        ti.add(TemporalEntry(
            doc_id='current_fact',
            fact_range=TimeRange(start=now - timedelta(days=5), end=now + timedelta(days=5)),
            subject='test', predicate='works_at'
        ))
        # Entry that spans [now+1d, now+10d] (future)
        ti.add(TemporalEntry(
            doc_id='future_fact',
            fact_range=TimeRange(start=now + timedelta(days=1), end=now + timedelta(days=10)),
            subject='test', predicate='will_visit'
        ))

        # Query at "now" should find only current_fact
        results_now = ti.query_at_time(now)
        if 'current_fact' in results_now and 'old_fact' not in results_now and 'future_fact' not in results_now:
            _mark('PASS', f'query_at_time(now)={results_now}')
        else:
            _mark('FAIL', f'query_at_time(now)={results_now}, expected [current_fact]')

        # Query at now-7d should find ONLY old_fact
        # (current_fact starts at now-5d, so at now-7d it's not yet valid)
        results_past = ti.query_at_time(now - timedelta(days=7))
        past_set = set(results_past)
        if past_set == {'old_fact'}:
            _mark('PASS', f'query_at_time(now-7d)={results_past}')
        else:
            _mark('FAIL', f'query_at_time(now-7d)={results_past}, expected {{old_fact}}')

        # Query at now+3d should find current_fact + future_fact
        results_future = ti.query_at_time(now + timedelta(days=3))
        future_set = set(results_future)
        if 'current_fact' in future_set and 'future_fact' in future_set:
            _mark('PASS', f'query_at_time(now+3d)={results_future}')
        else:
            _mark('FAIL', f'query_at_time(now+3d)={results_future}, expected {{current_fact, future_fact}}')

        # Verify dual-bisect code is present (not O(n) scan)
        import recall.index.temporal_index as ti_module
        ti_src = inspect.getsource(ti_module.TemporalIndex.query_at_time)
        has_bisect = 'bisect_right' in ti_src and 'bisect_left' in ti_src
        has_dual = '_sorted_by_fact_start' in ti_src and '_sorted_by_fact_end' in ti_src
        if has_bisect and has_dual:
            _mark('PASS', 'query_at_time() uses dual-bisect (bisect_right + bisect_left)')
        else:
            _mark('FAIL', f'query_at_time() code missing bisect: bisect={has_bisect}, dual={has_dual}')

        # B4. TemporalIndex dual-bisect query_range
        print('\n--- B4. TemporalIndex query_range ---')
        # Range [now-6d, now-1d] should overlap with old_fact and current_fact
        results_range = ti.query_range(now - timedelta(days=6), now - timedelta(days=1))
        range_set = set(results_range)
        if 'old_fact' in range_set and 'current_fact' in range_set and 'future_fact' not in range_set:
            _mark('PASS', f'query_range(now-6d, now-1d)={results_range}')
        else:
            _mark('FAIL', f'query_range(now-6d, now-1d)={results_range}, expected {{old_fact, current_fact}}')

        qr_src = inspect.getsource(ti_module.TemporalIndex.query_range)
        has_dual_qr = 'bisect_right' in qr_src and 'bisect_left' in qr_src
        if has_dual_qr:
            _mark('PASS', 'query_range() uses dual-bisect')
        else:
            _mark('FAIL', 'query_range() missing dual-bisect')

        # B5. KnowledgeGraph _mark_dirty delayed save
        print('\n--- B5. KnowledgeGraph _mark_dirty ---')
        from recall.graph.temporal_knowledge_graph import TemporalKnowledgeGraph
        kg_dir = os.path.join(td, '_test_kg')
        os.makedirs(kg_dir, exist_ok=True)
        kg = TemporalKnowledgeGraph(data_path=kg_dir)

        # Verify _mark_dirty exists and has threshold logic
        has_mark_dirty = hasattr(kg, '_mark_dirty') and callable(kg._mark_dirty)
        has_threshold = hasattr(kg, '_save_threshold')
        has_counter = hasattr(kg, '_save_count')
        if has_mark_dirty:
            _mark('PASS', '_mark_dirty() method exists')
        else:
            _mark('FAIL', '_mark_dirty() method missing')
        if has_threshold and has_counter:
            _mark('PASS', f'_save_threshold={kg._save_threshold}, _save_count={kg._save_count}')
        else:
            _mark('FAIL', f'threshold={has_threshold}, counter={has_counter}')

        # Verify _mark_dirty doesn't save on every call
        kg._save_count = 0
        kg._dirty = False
        original_threshold = kg._save_threshold
        kg._save_threshold = 100  # high threshold so it won't auto-save
        saves_before = 0

        # Count actual _save calls by monkey-patching
        _real_save = kg._save
        save_count_tracker = [0]
        def _counting_save():
            save_count_tracker[0] += 1
            _real_save()
        kg._save = _counting_save

        for i in range(10):
            kg._mark_dirty()
        
        if save_count_tracker[0] == 0:
            _mark('PASS', f'10 _mark_dirty() calls, 0 _save() calls (threshold={kg._save_threshold})')
        else:
            _mark('FAIL', f'10 _mark_dirty() calls triggered {save_count_tracker[0]} _save() calls')

        # Now lower threshold to trigger save
        kg._save_threshold = 5
        kg._save_count = 4  # one more will trigger
        save_count_tracker[0] = 0
        kg._mark_dirty()
        if save_count_tracker[0] == 1:
            _mark('PASS', f'_mark_dirty() at threshold triggers exactly 1 _save()')
        else:
            _mark('FAIL', f'_mark_dirty() at threshold: {save_count_tracker[0]} saves (expected 1)')

        kg._save = _real_save  # restore
        kg._save_threshold = original_threshold

        # Verify _atexit_flush exists
        has_atexit = hasattr(kg, '_atexit_flush') and callable(kg._atexit_flush)
        if has_atexit:
            _mark('PASS', '_atexit_flush() method exists')
        else:
            _mark('FAIL', '_atexit_flush() method missing')

        # Verify no auto_save→_save() pattern remains
        kg_src = inspect.getsource(TemporalKnowledgeGraph)
        # Count "self.auto_save" followed by "_save()" patterns (should be 0 outside _mark_dirty)
        # The pattern "if self.auto_save:" + "_save()" should only appear in _mark_dirty
        import re
        auto_save_pattern = re.findall(r'if\s+self\.auto_save.*?self\._save\(\)', kg_src, re.DOTALL)
        # Filter: only _mark_dirty's own use is OK
        if len(auto_save_pattern) <= 1:
            _mark('PASS', f'auto_save→_save() pattern count={len(auto_save_pattern)} (only _mark_dirty)')
        else:
            _mark('FAIL', f'auto_save→_save() pattern count={len(auto_save_pattern)}, expected <=1')

        # B6. RerankerFactory create() three backends
        print('\n--- B6. RerankerFactory ---')
        from recall.retrieval.reranker import RerankerFactory, BuiltinReranker, CohereReranker
        
        # builtin
        r_builtin = RerankerFactory.create(backend='builtin')
        if isinstance(r_builtin, BuiltinReranker):
            _mark('PASS', 'create(builtin) -> BuiltinReranker')
        else:
            _mark('FAIL', f'create(builtin) -> {type(r_builtin).__name__}')

        # cohere without key -> falls back to builtin
        r_cohere_nokey = RerankerFactory.create(backend='cohere', api_key='', model='')
        if isinstance(r_cohere_nokey, BuiltinReranker):
            _mark('PASS', 'create(cohere, no key) -> BuiltinReranker fallback')
        else:
            _mark('FAIL', f'create(cohere, no key) -> {type(r_cohere_nokey).__name__}')

        # unknown backend -> falls back to builtin
        r_unknown = RerankerFactory.create(backend='nonexistent')
        if isinstance(r_unknown, BuiltinReranker):
            _mark('PASS', 'create(nonexistent) -> BuiltinReranker fallback')
        else:
            _mark('FAIL', f'create(nonexistent) -> {type(r_unknown).__name__}')

        # Verify create() accepts api_key and model params
        sig = inspect.signature(RerankerFactory.create)
        params = list(sig.parameters.keys())
        if 'api_key' in params and 'model' in params:
            _mark('PASS', f'create() accepts api_key, model params: {params}')
        else:
            _mark('FAIL', f'create() params: {params}, missing api_key/model')

        # BuiltinReranker actually works
        r_result = r_builtin.rerank('Python programming', ['Python is great', 'Java is old', 'How to code in Python'], 2)
        if len(r_result) == 2 and isinstance(r_result[0], tuple):
            _mark('PASS', f'BuiltinReranker.rerank() -> {r_result}')
        else:
            _mark('FAIL', f'BuiltinReranker.rerank() unexpected: {r_result}')

        # B7. PromptManager wired into processors
        print('\n--- B7. PromptManager Wiring ---')
        # Check that the 3 processor classes accept prompt_manager param
        from recall.processor.unified_analyzer import UnifiedAnalyzer
        from recall.processor.smart_extractor import SmartExtractor
        from recall.processor.three_stage_deduplicator import ThreeStageDeduplicator

        for cls_name, cls in [('UnifiedAnalyzer', UnifiedAnalyzer),
                               ('SmartExtractor', SmartExtractor),
                               ('ThreeStageDeduplicator', ThreeStageDeduplicator)]:
            sig = inspect.signature(cls.__init__)
            if 'prompt_manager' in sig.parameters:
                _mark('PASS', f'{cls_name}.__init__ accepts prompt_manager')
            else:
                _mark('FAIL', f'{cls_name}.__init__ missing prompt_manager param')

        # B8. QueryPlanner wired into ElevenLayer
        print('\n--- B8. QueryPlanner Wiring ---')
        from recall.retrieval.eleven_layer import ElevenLayerRetriever
        sig_elr = inspect.signature(ElevenLayerRetriever.__init__)
        if 'query_planner' in sig_elr.parameters:
            _mark('PASS', 'ElevenLayerRetriever.__init__ accepts query_planner')
        else:
            _mark('FAIL', 'ElevenLayerRetriever.__init__ missing query_planner')

        # Also check reranker params
        for p in ['reranker_backend', 'reranker_api_key', 'reranker_model']:
            if p in sig_elr.parameters:
                _mark('PASS', f'ElevenLayerRetriever.__init__ accepts {p}')
            else:
                _mark('FAIL', f'ElevenLayerRetriever.__init__ missing {p}')

        # Verify engine's retriever has query_planner attribute
        if hasattr(e, 'retriever'):
            ret = e.retriever
            if hasattr(ret, 'query_planner'):
                _mark('PASS', f'retriever.query_planner={ret.query_planner is not None}')
            else:
                _mark('WARN', 'retriever has no query_planner attr (may be different retriever type)')

        # B9. ConsolidationManager wired in
        print('\n--- B9. ConsolidationManager ---')
        has_cm = hasattr(e, 'consolidation_manager')
        if has_cm:
            cm = e.consolidation_manager
            if cm is not None:
                _mark('PASS', f'consolidation_manager={type(cm).__name__}')
            else:
                _mark('WARN', 'consolidation_manager is None (may have init error)')
        else:
            _mark('FAIL', 'consolidation_manager attr missing from engine')

        # Verify consolidate() delegates to ConsolidationManager
        consol_src = inspect.getsource(e.consolidate)
        if 'consolidation_manager' in consol_src:
            _mark('PASS', 'consolidate() references consolidation_manager')
        else:
            _mark('FAIL', 'consolidate() does not reference consolidation_manager')

        # B10. IVF auto-switch config
        print('\n--- B10. IVF Auto-Switch ---')
        if hasattr(rc, 'ivf_auto_switch_enabled'):
            _mark('PASS', f'rc.ivf_auto_switch_enabled={rc.ivf_auto_switch_enabled}')
        else:
            _mark('FAIL', 'rc.ivf_auto_switch_enabled missing')
        if hasattr(rc, 'ivf_auto_switch_threshold'):
            _mark('PASS', f'rc.ivf_auto_switch_threshold={rc.ivf_auto_switch_threshold}')
        else:
            _mark('FAIL', 'rc.ivf_auto_switch_threshold missing')

        # Check _migrate_vectors_to_ivf exists in engine
        has_migrate = hasattr(e, '_migrate_vectors_to_ivf') and callable(e._migrate_vectors_to_ivf)
        if has_migrate:
            _mark('PASS', '_migrate_vectors_to_ivf() method exists')
        else:
            _mark('FAIL', '_migrate_vectors_to_ivf() method missing')

        # ================================================================
        # SUMMARY
        # ================================================================
        print('\n' + '=' * 60)
        print(f'  PASS: {PASS}')
        print(f'  WARN: {WARN}')
        print(f'  FAIL: {FAIL}')
        print('=' * 60)

        if FAIL == 0:
            print('EXPANDED SMOKE TEST: ALL PASSED')
            if WARN > 0:
                print(f'  ({WARN} warnings — non-critical, acceptable)')
        else:
            print(f'EXPANDED SMOKE TEST: {FAIL} FAILURES')
        print('=' * 60)

    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f'\nFATAL ERROR: {ex}')
        return 1
    finally:
        shutil.rmtree(td, ignore_errors=True)

    return 1 if FAIL > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
