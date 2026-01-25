"""图查询规划器

Phase 3.5: 企业级性能引擎

优化多跳图查询的执行策略。

优化策略：
1. 索引优先 - 有索引的字段优先使用索引
2. 早期过滤 - 尽早减少候选集
3. 路径缓存 - 缓存常见路径模式
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger(__name__)


class QueryOperation(Enum):
    """查询操作类型"""
    SCAN = "scan"           # 全表扫描
    INDEX_LOOKUP = "index"  # 索引查找
    NEIGHBOR = "neighbor"   # 邻居遍历
    FILTER = "filter"       # 过滤
    JOIN = "join"           # 连接
    CACHE_HIT = "cache"     # 缓存命中


@dataclass
class QueryPlan:
    """查询计划"""
    operations: List[Tuple[QueryOperation, Dict[str, Any]]] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_rows: int = 0
    use_cache: bool = False
    cache_key: Optional[str] = None
    
    def add_operation(self, op: QueryOperation, details: Dict[str, Any] = None):
        """添加操作"""
        self.operations.append((op, details or {}))
    
    def __str__(self) -> str:
        ops_str = " -> ".join([op.value for op, _ in self.operations])
        return f"QueryPlan({ops_str}, cost={self.estimated_cost:.2f}ms, rows={self.estimated_rows})"


@dataclass
class QueryStats:
    """查询统计信息"""
    total_queries: int = 0
    cache_hits: int = 0
    avg_execution_time_ms: float = 0.0
    total_nodes_visited: int = 0
    
    def record_query(self, execution_time_ms: float, nodes_visited: int, cache_hit: bool):
        """记录查询统计"""
        self.total_queries += 1
        self.total_nodes_visited += nodes_visited
        
        if cache_hit:
            self.cache_hits += 1
        
        # 更新平均执行时间（滚动平均）
        if self.total_queries == 1:
            self.avg_execution_time_ms = execution_time_ms
        else:
            self.avg_execution_time_ms = (
                self.avg_execution_time_ms * (self.total_queries - 1) + execution_time_ms
            ) / self.total_queries
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        return self.cache_hits / self.total_queries if self.total_queries > 0 else 0.0


class QueryPlanner:
    """图查询规划器
    
    优化策略：
    1. 索引优先 - 有索引的字段优先使用索引
    2. 早期过滤 - 尽早减少候选集
    3. 路径缓存 - 缓存常见路径模式
    
    使用方式：
        planner = QueryPlanner(graph_backend)
        
        # 规划 BFS 查询
        plan = planner.plan_bfs(
            start_ids=["Alice"],
            max_depth=2,
            edge_types=["KNOWS", "WORKS_WITH"]
        )
        print(plan)  # QueryPlan(neighbor -> filter, cost=5.00ms, rows=50)
        
        # 执行优化后的查询
        results = planner.execute_bfs(
            start_ids=["Alice"],
            max_depth=2,
            edge_types=["KNOWS"]
        )
    """
    
    def __init__(
        self,
        graph_backend,
        cache_size: int = 1000,
        cache_ttl_seconds: int = 300,
        stats_cache_ttl_seconds: int = 60
    ):
        """初始化查询规划器
        
        Args:
            graph_backend: GraphBackend 实例
            cache_size: 路径缓存大小（条）
            cache_ttl_seconds: 缓存过期时间（秒）
            stats_cache_ttl_seconds: 统计信息缓存过期时间（秒）
        """
        self.backend = graph_backend
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl_seconds
        
        # 路径缓存：pattern -> (results, timestamp)
        self._path_cache: Dict[str, Tuple[List, float]] = {}
        
        # 统计信息缓存
        self._stats_cache: Dict[str, Any] = {}
        self._stats_cache_time: float = 0
        self._stats_cache_ttl = stats_cache_ttl_seconds
        
        # 查询统计
        self.stats = QueryStats()
    
    def plan_bfs(
        self,
        start_ids: List[str],
        max_depth: int,
        edge_types: Optional[List[str]] = None,
        node_filter: Optional[Dict[str, Any]] = None
    ) -> QueryPlan:
        """规划 BFS 查询
        
        Args:
            start_ids: 起始节点 ID 列表
            max_depth: 最大深度
            edge_types: 边类型过滤列表
            node_filter: 节点属性过滤
            
        Returns:
            QueryPlan 查询计划
        """
        plan = QueryPlan()
        
        # 检查缓存
        cache_key = self._make_cache_key(start_ids, max_depth, edge_types, node_filter)
        if cache_key in self._path_cache:
            cached_result, cached_time = self._path_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                plan.use_cache = True
                plan.cache_key = cache_key
                plan.add_operation(QueryOperation.CACHE_HIT, {"key": cache_key})
                plan.estimated_cost = 0.1  # 缓存命中成本极低
                plan.estimated_rows = len(cached_result) if cached_result else 0
                return plan
        
        # 估算成本
        start_count = len(start_ids)
        avg_degree = self._estimate_avg_degree()
        
        total_rows = start_count
        estimated_cost = 0.0
        
        for depth in range(1, max_depth + 1):
            total_rows *= avg_degree
            
            # 邻居遍历
            neighbor_cost = total_rows * 0.01  # 每个节点 0.01ms
            plan.add_operation(
                QueryOperation.NEIGHBOR,
                {"depth": depth, "estimated_rows": int(total_rows), "cost_ms": neighbor_cost}
            )
            estimated_cost += neighbor_cost
            
            # 边类型过滤
            if edge_types:
                filter_ratio = len(edge_types) / max(self._count_edge_types(), 1)
                total_rows *= filter_ratio
                filter_cost = total_rows * 0.001  # 过滤成本较低
                plan.add_operation(
                    QueryOperation.FILTER,
                    {"edge_types": edge_types, "estimated_rows": int(total_rows), "cost_ms": filter_cost}
                )
                estimated_cost += filter_cost
            
            # 节点属性过滤
            if node_filter:
                filter_cost = total_rows * 0.002
                plan.add_operation(
                    QueryOperation.FILTER,
                    {"node_filter": node_filter, "estimated_rows": int(total_rows * 0.5), "cost_ms": filter_cost}
                )
                total_rows *= 0.5  # 假设过滤掉一半
                estimated_cost += filter_cost
        
        plan.estimated_cost = estimated_cost
        plan.estimated_rows = int(total_rows)
        plan.cache_key = cache_key
        
        return plan
    
    def execute_bfs(
        self,
        start_ids: List[str],
        max_depth: int = 2,
        edge_types: Optional[List[str]] = None,
        node_filter: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
        use_plan: bool = True
    ) -> Dict[int, List[Any]]:
        """执行优化后的 BFS 查询
        
        Args:
            start_ids: 起始节点 ID 列表
            max_depth: 最大深度
            edge_types: 边类型过滤列表
            node_filter: 节点属性过滤
            limit: 结果数量限制
            use_plan: 是否使用查询规划
            
        Returns:
            深度 -> [(节点, 边)] 的字典
        """
        start_time = time.perf_counter()
        cache_hit = False
        
        if use_plan:
            plan = self.plan_bfs(start_ids, max_depth, edge_types, node_filter)
            
            # 检查缓存
            if plan.use_cache and plan.cache_key:
                cached_result, _ = self._path_cache.get(plan.cache_key, (None, 0))
                if cached_result is not None:
                    execution_time = (time.perf_counter() - start_time) * 1000
                    self.stats.record_query(execution_time, 0, cache_hit=True)
                    return cached_result
        
        # 执行实际查询
        results = self.backend.bfs(
            start_ids=start_ids,
            max_depth=max_depth,
            edge_types=edge_types,
            node_filter=node_filter,
            limit=limit
        )
        
        # 缓存结果
        cache_key = self._make_cache_key(start_ids, max_depth, edge_types, node_filter)
        self._cache_result(cache_key, results)
        
        # 记录统计
        nodes_visited = sum(len(v) for v in results.values())
        execution_time = (time.perf_counter() - start_time) * 1000
        self.stats.record_query(execution_time, nodes_visited, cache_hit)
        
        return results
    
    def _make_cache_key(
        self,
        start_ids: List[str],
        max_depth: int,
        edge_types: Optional[List[str]],
        node_filter: Optional[Dict[str, Any]]
    ) -> str:
        """生成缓存键"""
        import hashlib
        import json
        
        key_data = {
            'start_ids': sorted(start_ids),
            'max_depth': max_depth,
            'edge_types': sorted(edge_types) if edge_types else None,
            'node_filter': node_filter
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()[:16]
    
    def _cache_result(self, cache_key: str, result: Any):
        """缓存结果"""
        # 检查缓存大小限制
        if len(self._path_cache) >= self.cache_size:
            # 移除最旧的缓存项
            oldest_key = min(self._path_cache.keys(), key=lambda k: self._path_cache[k][1])
            del self._path_cache[oldest_key]
        
        self._path_cache[cache_key] = (result, time.time())
    
    def _estimate_avg_degree(self) -> float:
        """估算平均度数"""
        # 检查缓存
        now = time.time()
        if now - self._stats_cache_time < self._stats_cache_ttl and 'avg_degree' in self._stats_cache:
            return self._stats_cache['avg_degree']
        
        try:
            node_count = self.backend.count_nodes()
            edge_count = self.backend.count_edges()
            avg = (edge_count * 2) / max(node_count, 1)
            
            # 更新缓存
            self._stats_cache['avg_degree'] = avg
            self._stats_cache['node_count'] = node_count
            self._stats_cache['edge_count'] = edge_count
            self._stats_cache_time = now
            
            return avg
        except Exception as e:
            logger.warning(f"[QueryPlanner] Failed to estimate avg degree: {e}")
            return 5.0  # 默认估计
    
    def _count_edge_types(self) -> int:
        """统计边类型数量"""
        if 'edge_type_count' in self._stats_cache:
            return self._stats_cache['edge_type_count']
        
        # 默认估计，大多数图谱不会超过 20 种边类型
        return 10
    
    def cache_path(self, pattern: str, result: List[str]):
        """手动缓存路径查询结果
        
        Args:
            pattern: 路径模式（如 "Alice-*->*"）
            result: 查询结果
        """
        self._path_cache[pattern] = (result, time.time())
    
    def get_cached_path(self, pattern: str) -> Optional[List[str]]:
        """获取缓存的路径
        
        Args:
            pattern: 路径模式
            
        Returns:
            缓存的结果，如果不存在或过期则返回 None
        """
        if pattern in self._path_cache:
            result, cached_time = self._path_cache[pattern]
            if time.time() - cached_time < self.cache_ttl:
                return result
            else:
                # 过期，删除
                del self._path_cache[pattern]
        return None
    
    def clear_cache(self):
        """清空所有缓存"""
        self._path_cache.clear()
        self._stats_cache.clear()
        self._stats_cache_time = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取查询规划器统计信息"""
        return {
            "total_queries": self.stats.total_queries,
            "cache_hits": self.stats.cache_hits,
            "cache_hit_rate": f"{self.stats.cache_hit_rate:.1%}",
            "avg_execution_time_ms": f"{self.stats.avg_execution_time_ms:.2f}",
            "total_nodes_visited": self.stats.total_nodes_visited,
            "cache_size": len(self._path_cache),
            "cache_max_size": self.cache_size,
        }
