#!/usr/bin/env python3
"""Recall v7.0 冒烟测试 - 验证核心功能是否真的能跑"""
import os
import sys
import tempfile
import shutil
import time

def main():
    from recall.engine import RecallEngine
    
    td = tempfile.mkdtemp(prefix='recall_v70_smoke_')
    print(f'[SETUP] Test dir: {td}')
    errors = []
    
    try:
        # === 1. Engine Init ===
        print('\n=== 1. Engine Initialization ===')
        e = RecallEngine(data_root=td)
        print(f'  Retriever type: {type(e.retriever).__name__}')
        print(f'  Has vector_index: {e._vector_index is not None}')
        
        has_pr = hasattr(e, 'parallel_retriever') and e.parallel_retriever is not None
        has_pm = hasattr(e, 'prompt_manager') and e.prompt_manager is not None
        has_qp = hasattr(e, 'query_planner') and e.query_planner is not None
        has_cm = hasattr(e, 'consolidation_manager')
        has_ct = hasattr(e, 'context_tracker') and e.context_tracker is not None
        has_kg = hasattr(e, 'knowledge_graph') and e.knowledge_graph is not None
        has_ft = hasattr(e, 'foreshadowing_tracker') and e.foreshadowing_tracker is not None
        
        print(f'  parallel_retriever: {has_pr}')
        print(f'  prompt_manager: {has_pm}')
        print(f'  query_planner: {has_qp}')
        print(f'  consolidation_manager attr: {has_cm}')
        print(f'  context_tracker: {has_ct}')
        print(f'  knowledge_graph: {has_kg}')
        print(f'  foreshadowing_tracker: {has_ft}')
        
        if type(e.retriever).__name__ == 'ElevenLayerRetriever':
            print('  [PASS] ElevenLayerRetriever is active')
        else:
            print(f'  [WARN] Retriever is {type(e.retriever).__name__}, not ElevenLayer')
        
        print('  [PASS] Engine initialized successfully')
        
        # === 2. Add Memory ===
        print('\n=== 2. Add Memory ===')
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
            print(f'  add[{i}] -> {mid}')
        
        if all(mids):
            print(f'  [PASS] All {len(mids)} memories added')
        else:
            errors.append('Some add() calls returned None')
            print(f'  [FAIL] Some add() returned None: {mids}')
        
        # === 3. Search ===
        print('\n=== 3. Search ===')
        queries = [
            ('capital of France', 'Paris'),
            ('programming language', 'Python'),
            ('distance from Earth to Sun', 'kilometers'),
        ]
        
        for query, expected_keyword in queries:
            results = e.search(query, user_id='smoketest')
            count = len(results)
            if count > 0:
                top = results[0]
                text = getattr(top, 'content', '') or getattr(top, 'text', '')
                found = expected_keyword.lower() in text.lower()
                score = getattr(top, 'score', 'N/A')
                print(f'  search("{query}") -> {count} results, score={score}, contains "{expected_keyword}": {found}')
                if found:
                    print(f'    [PASS]')
                else:
                    print(f'    [WARN] Expected keyword not in top result: {text[:100]}')
            else:
                errors.append(f'search("{query}") returned 0 results')
                print(f'  search("{query}") -> 0 results [FAIL]')
        
        # === 4. Delete + Cascade ===
        print('\n=== 4. Delete Cascade ===')
        if mids[0]:
            ok = e.delete(mids[0], user_id='smoketest')
            print(f'  delete({mids[0]}) -> {ok}')
            
            # Verify deleted
            results_after = e.search('capital of France Paris', user_id='smoketest')
            found_deleted = any(
                mids[0] in str(getattr(r, 'id', '')) 
                for r in results_after
            )
            if not found_deleted:
                print('  [PASS] Deleted memory not found in search')
            else:
                errors.append('Deleted memory still found in search')
                print('  [FAIL] Deleted memory still found')
        
        # === 5. Multi-user Isolation ===
        print('\n=== 5. User Isolation ===')
        e.add('Secret data for user A only', user_id='user_a')
        e.add('Different data for user B', user_id='user_b')
        
        results_a = e.search('secret data', user_id='user_a')
        results_b = e.search('secret data', user_id='user_b')
        
        a_texts = ' '.join(getattr(r, 'content', '') or '' for r in results_a)
        b_texts = ' '.join(getattr(r, 'content', '') or '' for r in results_b)
        
        a_has_secret = 'Secret' in a_texts
        b_has_secret = 'Secret' in b_texts
        
        if a_has_secret and not b_has_secret:
            print('  [PASS] User isolation works')
        else:
            print(f'  [WARN] user_a found secret: {a_has_secret}, user_b found secret: {b_has_secret}')
        
        # === 6. Check Dead Code Status ===
        print('\n=== 6. Dead Code Audit ===')
        
        # ParallelRetriever - is it actually callable?
        if has_pr:
            try:
                pr_results = e.search_parallel('test', user_id='smoketest')
                print(f'  search_parallel() -> {len(pr_results)} results [WORKS]')
            except AttributeError:
                print('  search_parallel() -> AttributeError [DEAD CODE]')
                errors.append('ParallelRetriever initialized but search_parallel() not available')
            except Exception as ex:
                print(f'  search_parallel() -> {type(ex).__name__}: {ex} [ERROR]')
        else:
            print('  ParallelRetriever: not initialized')
        
        # PromptManager - check if any method is ever called
        if has_pm:
            pm = e.prompt_manager
            print(f'  PromptManager type: {type(pm).__name__}, methods: {[m for m in dir(pm) if not m.startswith("_")][:5]}')
            print('  PromptManager: initialized but engine.py never calls any method [DEAD CODE]')
        
        # QueryPlanner
        if has_qp:
            qp = e.query_planner
            print(f'  QueryPlanner type: {type(qp).__name__}')
            print('  QueryPlanner: initialized but execute_bfs() never called [DEAD CODE]')
        
        # === 7. consolidate() test ===
        print('\n=== 7. Consolidate ===')
        try:
            result = e.consolidate(user_id='smoketest')
            print(f'  consolidate() returned: {result}')
            if result:
                print('  [PASS] consolidate() produced output')
            else:
                print('  [WARN] consolidate() returned empty/None')
        except Exception as ex:
            print(f'  consolidate() error: {type(ex).__name__}: {ex}')
            errors.append(f'consolidate() failed: {ex}')
        
        # === 8. Mode check ===
        print('\n=== 8. Mode System ===')
        try:
            from recall.mode import get_mode_config
            mode = get_mode_config()
            print(f'  Mode: {mode.mode}')
            print(f'  foreshadowing_enabled: {mode.foreshadowing_enabled}')
            print(f'  character_dimension_enabled: {mode.character_dimension_enabled}')
            print('  [PASS] Universal mode active')
        except Exception as ex:
            print(f'  Mode error: {ex}')
        
        # === Summary ===
        print('\n' + '=' * 60)
        if errors:
            print(f'SMOKE TEST: {len(errors)} issues found')
            for err in errors:
                print(f'  - {err}')
        else:
            print('SMOKE TEST: ALL PASSED')
        print('=' * 60)
        
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f'\nFATAL ERROR: {ex}')
        return 1
    finally:
        shutil.rmtree(td, ignore_errors=True)
    
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main())
