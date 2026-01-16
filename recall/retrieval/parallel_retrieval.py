"""并行检索器 - 多源并行检索"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed


class RetrievalSource(Enum):
    """检索源"""
    VECTOR = "vector"
    ENTITY = "entity"
    KEYWORD = "keyword"
    GRAPH = "graph"
    RECENT = "recent"


@dataclass
class RetrievalTask:
    """检索任务"""
    source: RetrievalSource
    query: str
    params: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    timeout: float = 5.0


@dataclass
class SourceResult:
    """单源检索结果"""
    source: RetrievalSource
    results: List[Dict[str, Any]]
    time_ms: float
    success: bool
    error: Optional[str] = None


class ParallelRetriever:
    """并行检索器"""
    
    def __init__(
        self,
        max_workers: int = 4,
        default_timeout: float = 5.0
    ):
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        
        # 检索函数注册
        self.retrievers: Dict[RetrievalSource, Callable] = {}
    
    def register(
        self,
        source: RetrievalSource,
        retriever: Callable[[str, Dict[str, Any]], List[Dict[str, Any]]]
    ):
        """注册检索器"""
        self.retrievers[source] = retriever
    
    def retrieve_parallel(
        self,
        tasks: List[RetrievalTask]
    ) -> List[SourceResult]:
        """并行执行多个检索任务"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(
                    self._execute_task,
                    task
                ): task
                for task in tasks
            }
            
            # 收集结果
            for future in as_completed(future_to_task, timeout=self.default_timeout + 1):
                task = future_to_task[future]
                try:
                    result = future.result(timeout=task.timeout)
                    results.append(result)
                except Exception as e:
                    results.append(SourceResult(
                        source=task.source,
                        results=[],
                        time_ms=0,
                        success=False,
                        error=str(e)
                    ))
        
        return results
    
    async def retrieve_parallel_async(
        self,
        tasks: List[RetrievalTask]
    ) -> List[SourceResult]:
        """异步并行执行检索任务"""
        async_tasks = [
            self._execute_task_async(task)
            for task in tasks
        ]
        
        results = await asyncio.gather(*async_tasks, return_exceptions=True)
        
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(SourceResult(
                    source=tasks[i].source,
                    results=[],
                    time_ms=0,
                    success=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def _execute_task(self, task: RetrievalTask) -> SourceResult:
        """执行单个检索任务"""
        start = time.time()
        
        if task.source not in self.retrievers:
            return SourceResult(
                source=task.source,
                results=[],
                time_ms=0,
                success=False,
                error=f"未注册的检索源: {task.source.value}"
            )
        
        try:
            retriever = self.retrievers[task.source]
            results = retriever(task.query, task.params)
            
            return SourceResult(
                source=task.source,
                results=results,
                time_ms=(time.time() - start) * 1000,
                success=True
            )
        except Exception as e:
            return SourceResult(
                source=task.source,
                results=[],
                time_ms=(time.time() - start) * 1000,
                success=False,
                error=str(e)
            )
    
    async def _execute_task_async(self, task: RetrievalTask) -> SourceResult:
        """异步执行单个检索任务"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._execute_task,
            task
        )
    
    def merge_results(
        self,
        source_results: List[SourceResult],
        tasks: List[RetrievalTask],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """合并多源检索结果"""
        # 创建任务权重映射
        task_weights = {task.source: task.weight for task in tasks}
        
        # 收集所有结果并计算加权分数
        scored_results: Dict[str, Dict[str, Any]] = {}
        
        for sr in source_results:
            if not sr.success:
                continue
            
            weight = task_weights.get(sr.source, 1.0)
            
            for result in sr.results:
                result_id = result.get('id', str(hash(str(result))))
                original_score = result.get('score', 0.5)
                
                if result_id in scored_results:
                    # 已存在，合并分数
                    scored_results[result_id]['score'] += original_score * weight
                    scored_results[result_id]['sources'].append(sr.source.value)
                else:
                    scored_results[result_id] = {
                        **result,
                        'score': original_score * weight,
                        'sources': [sr.source.value]
                    }
        
        # 排序并返回
        sorted_results = sorted(
            scored_results.values(),
            key=lambda x: -x['score']
        )
        
        return sorted_results[:top_k]
    
    def get_stats(self, source_results: List[SourceResult]) -> Dict[str, Any]:
        """获取检索统计"""
        total_time = sum(sr.time_ms for sr in source_results)
        successful = sum(1 for sr in source_results if sr.success)
        total_results = sum(len(sr.results) for sr in source_results if sr.success)
        
        return {
            'total_time_ms': total_time,
            'max_time_ms': max((sr.time_ms for sr in source_results), default=0),
            'successful_sources': successful,
            'total_sources': len(source_results),
            'total_results': total_results,
            'by_source': {
                sr.source.value: {
                    'time_ms': sr.time_ms,
                    'count': len(sr.results),
                    'success': sr.success,
                    'error': sr.error
                }
                for sr in source_results
            }
        }
