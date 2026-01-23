# Recall 4.0 升级计划：全面超越 Graphiti

> 📅 创建日期：2026-01-23
> 🎯 目标：在保持 Recall 所有现有优势的基础上，全面超越 Graphiti，成为通用 AI 知识图谱框架

---

## 📊 竞品分析：Graphiti 核心能力矩阵

基于 [GraphitiAnalysis.md](./GraphitiAnalysis.md) 的深度分析：

| 能力维度 | Graphiti 实现 | 技术细节 |
|----------|---------------|----------|
| **数据模型** | 双时态 (Bi-temporal) | `valid_at/invalid_at` + `expired_at` |
| **节点类型** | 4种 | EntityNode, EpisodicNode, CommunityNode, SagaNode |
| **边类型** | 3种 | EntityEdge, EpisodicEdge, CommunityEdge |
| **LLM 集成** | 6个提供商 | OpenAI, Anthropic, Gemini, Groq, Azure, Ollama |
| **图数据库** | 4种 | Neo4j, FalkorDB, Neptune, Kuzu |
| **检索方法** | 3种 | BM25, Vector, Graph Traversal |
| **重排序器** | 5种 | RRF, MMR, CrossEncoder, NodeDistance, EpisodeMentions |
| **去重机制** | 2阶段 | MinHash+LSH → LLM |
| **MCP 支持** | ✅ | 8个工具 |
| **实体抽取** | 纯 LLM | 强制依赖 |

---

## 🎯 Recall 4.0 超越策略

### 核心原则

```
┌─────────────────────────────────────────────────────────────────┐
│                    Recall 4.0 设计原则                          │
├─────────────────────────────────────────────────────────────────┤
│  1. 零依赖优先 - 无需外部数据库，开箱即用                        │
│  2. 成本可控 - LLM 可选，本地优先                               │
│  3. 向后兼容 - 现有功能 100% 保留                               │
│  4. 场景通用 - RP/代码/企业/Agent 全覆盖                        │
│  5. 性能卓越 - 超越而非追赶                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 功能对比与超越方案

### 1. 时态系统

| 维度 | Graphiti | Recall 4.0 | 超越点 |
|------|----------|------------|--------|
| 时态层数 | 2层 | **3层** | 新增"知识时间" |
| 事实失效 | LLM 检测 | **混合检测** | 规则+LLM，成本更低 |
| 历史回溯 | 支持 | **支持+可视化** | 时间线查询 API |
| 矛盾处理 | 自动失效 | **多策略** | 取代/共存/手动 |

```python
# Recall 4.0 三时态模型
@dataclass
class TemporalFact:
    # T1: 事实时间 (Fact Time) - 事实在现实中何时有效
    valid_from: datetime | None      # "Alice 从 2023-01 开始在 OpenAI 工作"
    valid_until: datetime | None     # "Alice 于 2024-06 离开 OpenAI"
    
    # T2: 知识时间 (Knowledge Time) - 我们何时获知此事实【新增】
    known_at: datetime               # 我们在 2024-07 得知她离职
    superseded_at: datetime | None   # 此知识被更新的信息取代
    
    # T3: 系统时间 (System Time) - 数据库记录生命周期
    created_at: datetime
    expired_at: datetime | None
```

### 2. 数据模型

| 维度 | Graphiti | Recall 4.0 | 超越点 |
|------|----------|------------|--------|
| 节点类型 | 4种固定 | **可扩展** | 插件式节点类型 |
| 边类型 | 3种固定 | **可扩展** | 插件式边类型 |
| 动态属性 | Dict | **类型安全 Dict** | Schema 验证 |
| 向量嵌入 | 可选 | **多向量** | 名称+内容+摘要 |

```python
# Recall 4.0 统一数据模型
class UnifiedNode(BaseModel):
    """统一节点模型 - 超越 Graphiti 的 4 种节点"""
    uuid: str
    name: str
    node_type: NodeType              # 可扩展枚举
    group_id: str                    # 多租户隔离
    
    # 多向量嵌入【超越点】
    name_embedding: List[float] | None
    content_embedding: List[float] | None
    summary_embedding: List[float] | None
    
    # 动态属性 + Schema 验证【超越点】
    attributes: Dict[str, Any]
    _attribute_schema: Dict[str, type] | None  # 运行时类型检查
    
    # 来源追踪【增强】
    source_episodes: List[str]
    confidence: float
    verification_count: int

class NodeType(str, Enum):
    """可扩展节点类型"""
    ENTITY = "entity"           # 实体（人、物、地点）
    EPISODE = "episode"         # 情节/事件
    COMMUNITY = "community"     # 社区/聚类
    CONCEPT = "concept"         # 概念/抽象
    # Recall 独有
    FORESHADOWING = "foreshadowing"  # 伏笔
    CONDITION = "condition"          # 持久条件
    RULE = "rule"                    # 规则
    # 可通过插件扩展...
```

### 3. 智能抽取系统

| 维度 | Graphiti | Recall 4.0 | 超越点 |
|------|----------|------------|--------|
| 抽取方式 | 纯 LLM | **三模式** | Local/Hybrid/LLM |
| 成本 | 高（强制） | **可控** | 预算管理 |
| 速度 | 慢（API） | **自适应** | 简单内容本地处理 |
| 离线 | ❌ | **✅** | 完全本地运行 |

```python
class SmartExtractor:
    """智能抽取器 - 三模式自适应"""
    
    class Mode(Enum):
        LOCAL = "local"       # 纯本地：spaCy + jieba + 规则
        HYBRID = "hybrid"     # 混合：本地初筛 + LLM 精炼
        LLM_FULL = "llm"      # 纯 LLM：最高质量
    
    def __init__(
        self,
        mode: Mode = Mode.HYBRID,
        daily_budget: float = 1.0,      # 每日 LLM 预算（美元）
        complexity_threshold: float = 0.6,  # 复杂度阈值
        local_extractor: EntityExtractor = None,
        llm_client: LLMClient = None
    ):
        self.mode = mode
        self.budget_manager = BudgetManager(daily_budget)
        self.complexity_threshold = complexity_threshold
        self.local = local_extractor or EntityExtractor()
        self.llm = llm_client
    
    async def extract(self, text: str, context: Dict = None) -> ExtractionResult:
        """自适应抽取"""
        # 1. 始终执行本地抽取（免费、快速）
        local_result = self.local.extract(text)
        
        if self.mode == Mode.LOCAL:
            return local_result
        
        # 2. 评估复杂度
        complexity = self._assess_complexity(text, local_result)
        
        # 3. 决策是否需要 LLM
        need_llm = (
            self.mode == Mode.LLM_FULL or
            (self.mode == Mode.HYBRID and complexity >= self.complexity_threshold)
        )
        
        if need_llm and self.budget_manager.can_afford():
            llm_result = await self._llm_extract(text, local_result, context)
            self.budget_manager.record_cost(llm_result.cost)
            return self._merge_results(local_result, llm_result)
        
        return local_result
    
    def _assess_complexity(self, text: str, local_result) -> float:
        """评估文本复杂度"""
        score = 0.0
        
        # 长度
        if len(text) > 500: score += 0.15
        if len(text) > 1000: score += 0.15
        
        # 实体密度
        entity_density = len(local_result.entities) / max(len(text) / 100, 1)
        if entity_density > 0.5: score += 0.2
        
        # 关系复杂度
        if len(local_result.entities) > 3: score += 0.15
        
        # 时态标记
        if self._has_temporal_markers(text): score += 0.15
        
        # 本地抽取置信度低
        if local_result.avg_confidence < 0.6: score += 0.2
        
        return min(1.0, score)
```

### 4. 知识图谱存储

| 维度 | Graphiti | Recall 4.0 | 超越点 |
|------|----------|------------|--------|
| 存储后端 | Neo4j 等（必需） | **纯本地** | 零依赖 |
| 查询语言 | Cypher | **多种** | Python API + 类 Cypher DSL |
| 性能 | 依赖数据库 | **内存优化** | 热数据常驻 |
| 可选外部 | - | **✅** | 可选接入 Neo4j |

```python
class TemporalKnowledgeGraph:
    """时序知识图谱 - 无需外部数据库"""
    
    def __init__(
        self, 
        data_path: str,
        backend: str = "local",  # local | neo4j | falkordb
        scope: str = "global"    # global | isolated
    ):
        self.data_path = data_path
        self.scope = scope
        
        # 核心存储
        self.nodes: Dict[str, UnifiedNode] = {}
        self.edges: Dict[str, TemporalFact] = {}
        self.episodes: Dict[str, EpisodicNode] = {}
        
        # 高效索引
        self._indexes = GraphIndexes(
            outgoing=defaultdict(set),      # node_id -> edge_ids
            incoming=defaultdict(set),      # node_id -> edge_ids
            by_type=defaultdict(set),       # node_type -> node_ids
            by_predicate=defaultdict(set),  # predicate -> edge_ids
            temporal=TemporalIndex(),       # 时间范围索引
            fulltext=FullTextIndex(),       # BM25 全文索引
        )
        
        # 可选：向量索引
        self.vector_index: Optional[VectorIndex] = None
        
        # 可选：外部数据库后端
        if backend == "neo4j":
            self._backend = Neo4jBackend(...)
        elif backend == "falkordb":
            self._backend = FalkorDBBackend(...)
        else:
            self._backend = None  # 纯本地
    
    # === 时态查询 API ===
    
    def query_at_time(
        self,
        subject: str,
        as_of: datetime,
        predicate: str = None
    ) -> List[TemporalFact]:
        """查询某时间点的有效事实"""
        results = []
        for edge_id in self._indexes.outgoing.get(subject, []):
            edge = self.edges[edge_id]
            if predicate and edge.predicate != predicate:
                continue
            if self._is_valid_at(edge, as_of):
                results.append(edge)
        return results
    
    def query_timeline(
        self,
        subject: str,
        predicate: str = None,
        start: datetime = None,
        end: datetime = None
    ) -> List[Tuple[datetime, TemporalFact, str]]:
        """获取实体时间线（所有历史状态变化）"""
        timeline = []
        for edge_id in self._indexes.outgoing.get(subject, []):
            edge = self.edges[edge_id]
            if predicate and edge.predicate != predicate:
                continue
            
            # 记录状态变化点
            if edge.valid_from:
                timeline.append((edge.valid_from, edge, "started"))
            if edge.valid_until:
                timeline.append((edge.valid_until, edge, "ended"))
            if edge.superseded_at:
                timeline.append((edge.superseded_at, edge, "superseded"))
        
        # 按时间排序
        timeline.sort(key=lambda x: x[0])
        
        # 应用时间范围过滤
        if start:
            timeline = [t for t in timeline if t[0] >= start]
        if end:
            timeline = [t for t in timeline if t[0] <= end]
        
        return timeline
    
    # === 矛盾检测与处理 ===
    
    def detect_contradictions(
        self,
        new_fact: TemporalFact,
        strategy: str = "auto"  # auto | strict | permissive
    ) -> List[Contradiction]:
        """检测矛盾"""
        contradictions = []
        
        # 查找同主体、同谓词的现有事实
        existing = self.query_at_time(
            new_fact.subject,
            new_fact.valid_from or datetime.now(),
            new_fact.predicate
        )
        
        for old_fact in existing:
            if old_fact.object != new_fact.object:
                contradiction = Contradiction(
                    old_fact=old_fact,
                    new_fact=new_fact,
                    type=self._classify_contradiction(old_fact, new_fact),
                    confidence=self._compute_contradiction_confidence(old_fact, new_fact)
                )
                contradictions.append(contradiction)
        
        return contradictions
    
    def resolve_contradiction(
        self,
        contradiction: Contradiction,
        resolution: str = "supersede"  # supersede | coexist | reject | manual
    ) -> ResolutionResult:
        """解决矛盾"""
        if resolution == "supersede":
            # 新事实取代旧事实
            old = contradiction.old_fact
            old.valid_until = contradiction.new_fact.valid_from
            old.superseded_at = datetime.now()
            return ResolutionResult(success=True, action="superseded")
        
        elif resolution == "coexist":
            # 两个事实共存（可能来自不同视角/来源）
            return ResolutionResult(success=True, action="coexist")
        
        elif resolution == "reject":
            # 拒绝新事实
            return ResolutionResult(success=False, action="rejected")
        
        else:
            # 标记为待人工处理
            self._pending_contradictions.append(contradiction)
            return ResolutionResult(success=True, action="pending_manual")
    
    # === 图遍历 ===
    
    def bfs(
        self,
        start: str,
        max_depth: int = 3,
        predicate_filter: List[str] = None,
        time_filter: datetime = None,
        direction: str = "both"  # out | in | both
    ) -> Dict[int, List[Tuple[str, TemporalFact]]]:
        """广度优先搜索，返回按深度分组的结果"""
        visited = {start}
        queue = [(start, 0)]
        results = defaultdict(list)
        
        while queue:
            node_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            
            # 获取边
            edge_ids = set()
            if direction in ("out", "both"):
                edge_ids.update(self._indexes.outgoing.get(node_id, []))
            if direction in ("in", "both"):
                edge_ids.update(self._indexes.incoming.get(node_id, []))
            
            for edge_id in edge_ids:
                edge = self.edges[edge_id]
                
                # 时态过滤
                if time_filter and not self._is_valid_at(edge, time_filter):
                    continue
                
                # 谓词过滤
                if predicate_filter and edge.predicate not in predicate_filter:
                    continue
                
                # 确定目标节点
                target = edge.object if edge.subject == node_id else edge.subject
                
                results[depth].append((target, edge))
                
                if target not in visited:
                    visited.add(target)
                    queue.append((target, depth + 1))
        
        return results
    
    # === 类 Cypher 查询 DSL ===
    
    def query(self, pattern: str) -> QueryBuilder:
        """
        类 Cypher 查询语法
        
        示例:
            graph.query("(p:PERSON)-[r:WORKS_AT]->(c:COMPANY)")
                 .where(r.valid_at >= "2024-01-01")
                 .return_("p.name", "c.name", "r.fact")
                 .execute()
        """
        return QueryBuilder(self, pattern)
```

### 5. 检索系统

| 维度 | Graphiti | Recall 4.0 | 超越点 |
|------|----------|------------|--------|
| 检索层数 | 3层 | **10层** | 更精细的漏斗 |
| 重排序器 | 5种 | **7种** | 新增时态/伏笔重排 |
| 融合算法 | RRF | **RRF + 自适应权重** | 场景感知融合 |
| 图遍历 | 简单 BFS | **多策略** | BFS/DFS/随机游走 |

```python
class TenLayerRetriever:
    """十层漏斗检索器"""
    
    class Layer(Enum):
        L01_BLOOM_FILTER = "bloom"           # 快速否定
        L02_TEMPORAL_FILTER = "temporal"     # 时态过滤【新增】
        L03_INVERTED_INDEX = "inverted"      # 关键词匹配
        L04_ENTITY_INDEX = "entity"          # 实体关联
        L05_GRAPH_TRAVERSAL = "graph"        # 图遍历【新增】
        L06_NGRAM_INDEX = "ngram"            # 模糊匹配
        L07_VECTOR_COARSE = "vector_coarse"  # 向量粗筛
        L08_VECTOR_FINE = "vector_fine"      # 向量精排
        L09_CROSS_ENCODER = "cross_encoder"  # 交叉编码器【新增】
        L10_LLM_RERANK = "llm_rerank"        # LLM 重排序
    
    def retrieve(
        self,
        query: str,
        config: RetrievalConfig = None,
        temporal_context: TemporalContext = None,
        center_nodes: List[str] = None
    ) -> List[RetrievalResult]:
        """执行十层检索"""
        
        config = config or RetrievalConfig.default()
        candidates = set()
        scores = defaultdict(float)
        
        # L1: Bloom Filter - O(1) 快速否定
        if config.enable_bloom:
            keywords = self._extract_keywords(query)
            keywords = [k for k in keywords if k in self.bloom_filter]
        
        # L2: 时态过滤【新增】
        if temporal_context:
            time_range = temporal_context.get_range()
            # 预先过滤时间范围外的文档
        
        # L3: 倒排索引 - 关键词匹配
        if config.enable_inverted:
            inverted_results = self.inverted_index.search(keywords)
            for doc_id, score in inverted_results:
                candidates.add(doc_id)
                scores[doc_id] += score * config.weights.inverted
        
        # L4: 实体索引
        if config.enable_entity:
            entities = self._extract_entities(query)
            for entity in entities:
                for doc_id in self.entity_index.get_docs(entity):
                    candidates.add(doc_id)
                    scores[doc_id] += config.weights.entity
        
        # L5: 图遍历【新增】
        if config.enable_graph and center_nodes:
            graph_results = self.knowledge_graph.bfs(
                start=center_nodes[0],
                max_depth=2,
                time_filter=temporal_context.reference_time if temporal_context else None
            )
            for depth, items in graph_results.items():
                depth_weight = 1.0 / (depth + 1)  # 距离衰减
                for node_id, edge in items:
                    for episode_id in edge.source_episodes:
                        candidates.add(episode_id)
                        scores[episode_id] += depth_weight * config.weights.graph
        
        # L6: N-gram 索引 - 模糊匹配
        if config.enable_ngram:
            ngram_results = self.ngram_index.search(query)
            for doc_id in ngram_results:
                candidates.add(doc_id)
                scores[doc_id] += config.weights.ngram
        
        # L7: 向量粗筛
        if config.enable_vector and self.vector_index:
            vector_results = self.vector_index.search(query, top_k=config.vector_top_k)
            for doc_id, sim in vector_results:
                candidates.add(doc_id)
                scores[doc_id] += sim * config.weights.vector
        
        # L8: 向量精排
        if config.enable_vector_fine and len(candidates) > config.fine_rank_threshold:
            # 对 top candidates 重新计算精确相似度
            top_candidates = sorted(candidates, key=lambda x: scores[x], reverse=True)[:100]
            fine_scores = self.vector_index.rerank(query, top_candidates)
            for doc_id, score in fine_scores.items():
                scores[doc_id] = scores[doc_id] * 0.5 + score * 0.5
        
        # L9: Cross-Encoder 重排序【新增】
        if config.enable_cross_encoder and self.cross_encoder:
            top_candidates = sorted(candidates, key=lambda x: scores[x], reverse=True)[:50]
            ce_scores = self.cross_encoder.score(query, top_candidates)
            for doc_id, score in ce_scores.items():
                scores[doc_id] = scores[doc_id] * 0.3 + score * 0.7
        
        # L10: LLM 重排序（可选，高成本）
        if config.enable_llm_rerank and self.llm_client:
            top_candidates = sorted(candidates, key=lambda x: scores[x], reverse=True)[:20]
            llm_scores = await self._llm_rerank(query, top_candidates)
            for doc_id, score in llm_scores.items():
                scores[doc_id] = score  # LLM 分数直接覆盖
        
        # 最终排序
        final_results = sorted(
            [(doc_id, scores[doc_id]) for doc_id in candidates],
            key=lambda x: x[1],
            reverse=True
        )
        
        return [
            RetrievalResult(id=doc_id, score=score, content=self._get_content(doc_id))
            for doc_id, score in final_results[:config.top_k]
        ]
```

### 6. 去重系统

| 维度 | Graphiti | Recall 4.0 | 超越点 |
|------|----------|------------|--------|
| 阶段数 | 2阶段 | **3阶段** | 新增语义层 |
| 第一阶段 | MinHash+LSH | **相同** | 保持 |
| 第二阶段 | LLM | **Embedding** | 成本更低 |
| 第三阶段 | - | **LLM（可选）** | 仅高价值场景 |

```python
class ThreeStageDeduplicator:
    """三阶段去重系统"""
    
    async def deduplicate(
        self,
        new_items: List[Entity],
        existing_items: List[Entity],
        config: DedupConfig = None
    ) -> DedupResult:
        
        config = config or DedupConfig.default()
        result = DedupResult()
        
        # 构建索引
        indexes = self._build_indexes(existing_items)
        
        for item in new_items:
            # === 阶段 1: 确定性匹配 O(1) ===
            # 1.1 精确匹配
            normalized = self._normalize(item.name)
            if normalized in indexes.exact_map:
                result.add_match(item, indexes.exact_map[normalized], "exact", 1.0)
                continue
            
            # 1.2 MinHash + LSH 近似匹配
            shingles = self._get_shingles(item.name)
            signature = self._minhash(shingles)
            candidates = self._lsh_query(signature, indexes.lsh_buckets)
            
            if candidates:
                best_match, jaccard = self._best_jaccard_match(shingles, candidates, indexes)
                if jaccard >= config.jaccard_threshold:
                    result.add_match(item, best_match, "fuzzy", jaccard)
                    continue
            
            # === 阶段 2: 语义匹配【新增】 ===
            if config.enable_semantic and self.embedding_backend:
                item_embedding = await self.embedding_backend.embed(item.name)
                
                # 在向量索引中搜索
                similar = self.entity_vectors.search(item_embedding, top_k=5)
                
                for candidate_id, similarity in similar:
                    if similarity >= config.semantic_threshold:
                        candidate = indexes.by_id[candidate_id]
                        result.add_match(item, candidate, "semantic", similarity)
                        break
                else:
                    # 没有找到足够相似的，进入阶段3或标记为新实体
                    if config.enable_llm and similarity >= config.llm_threshold:
                        # 边界情况，需要 LLM 确认
                        result.add_pending(item, similar[:3])
                    else:
                        result.add_new(item)
                continue
            
            # === 阶段 3: LLM 确认（可选）===
            # 仅处理阶段2中的边界情况
        
        # 批量 LLM 确认
        if result.pending and config.enable_llm and self.llm_client:
            llm_results = await self._llm_batch_confirm(result.pending)
            for item, is_dup, match in llm_results:
                if is_dup:
                    result.move_to_match(item, match, "llm")
                else:
                    result.move_to_new(item)
        
        return result
```

### 7. MCP Server

| 维度 | Graphiti | Recall 4.0 | 超越点 |
|------|----------|------------|--------|
| 工具数量 | 8个 | **15+** | 更丰富的功能 |
| Recall 独有 | - | **✅** | 伏笔/条件/规则 |
| 时态查询 | 基础 | **完整** | 时间线/历史/快照 |

```python
class RecallMCPServer:
    """Recall MCP Server - 超越 Graphiti 的工具集"""
    
    def _register_tools(self):
        # === 基础工具（对标 Graphiti）===
        
        @self.server.tool()
        async def add_memory(content: str, user_id: str = "default", ...) -> dict:
            """添加记忆/知识"""
            ...
        
        @self.server.tool()
        async def search_facts(query: str, top_k: int = 10, ...) -> list:
            """搜索事实关系"""
            ...
        
        @self.server.tool()
        async def search_nodes(query: str, node_type: str = None, ...) -> list:
            """搜索实体节点"""
            ...
        
        @self.server.tool()
        async def get_episodes(user_id: str, limit: int = 20, ...) -> list:
            """获取情节列表"""
            ...
        
        @self.server.tool()
        async def delete_episode(episode_id: str) -> bool:
            """删除情节"""
            ...
        
        @self.server.tool()
        async def clear_graph(user_id: str, confirm: bool = False) -> bool:
            """清空图谱"""
            ...
        
        # === 时态查询工具【超越点】===
        
        @self.server.tool()
        async def query_at_time(
            entity: str,
            as_of: str,  # ISO 8601 时间
            predicate: str = None
        ) -> list:
            """查询某时间点的有效事实"""
            ...
        
        @self.server.tool()
        async def get_timeline(
            entity: str,
            predicate: str = None,
            start: str = None,
            end: str = None
        ) -> list:
            """获取实体的完整时间线"""
            ...
        
        @self.server.tool()
        async def compare_snapshots(
            entity: str,
            time1: str,
            time2: str
        ) -> dict:
            """对比两个时间点的状态差异"""
            ...
        
        # === Recall 独有工具【差异化优势】===
        
        @self.server.tool()
        async def plant_foreshadowing(
            content: str,
            keywords: list,
            importance: float = 0.5,
            user_id: str = "default",
            character_id: str = "default"
        ) -> dict:
            """埋下伏笔（叙事场景）"""
            ...
        
        @self.server.tool()
        async def get_active_foreshadowings(
            user_id: str,
            character_id: str,
            relevance_query: str = None
        ) -> list:
            """获取活跃伏笔（可按相关性过滤）"""
            ...
        
        @self.server.tool()
        async def resolve_foreshadowing(
            foreshadowing_id: str,
            resolution: str
        ) -> bool:
            """解决伏笔"""
            ...
        
        @self.server.tool()
        async def add_persistent_context(
            content: str,
            context_type: str,  # user_identity | environment | character_trait | ...
            user_id: str = "default"
        ) -> dict:
            """添加持久条件"""
            ...
        
        @self.server.tool()
        async def get_persistent_contexts(
            user_id: str,
            context_type: str = None,
            active_only: bool = True
        ) -> list:
            """获取持久条件"""
            ...
        
        @self.server.tool()
        async def build_context(
            query: str,
            user_id: str = "default",
            character_id: str = "default",
            max_tokens: int = 2000,
            include_foreshadowing: bool = True,
            include_conditions: bool = True,
            include_graph_context: bool = True
        ) -> str:
            """构建完整上下文（Recall 核心能力）"""
            ...
```

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Recall 4.0 系统架构                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│   │ MCP Server  │  │ REST API   │  │ Python SDK  │  │ CLI 工具    │           │
│   │ (AI助手)    │  │ (FastAPI)  │  │ (直接调用)  │  │ (命令行)    │           │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘           │
│          │                │                │                │                   │
│          └────────────────┼────────────────┼────────────────┘                   │
│                           ▼                                                     │
│   ┌─────────────────────────────────────────────────────────────────────────┐  │
│   │                         RecallEngine (核心引擎)                          │  │
│   │  ┌─────────────────────────────────────────────────────────────────┐    │  │
│   │  │  add() | search() | build_context() | query_timeline() | ...    │    │  │
│   │  └─────────────────────────────────────────────────────────────────┘    │  │
│   └───────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                             │
│   ┌───────────────────────────────┼───────────────────────────────┐            │
│   │                               │                               │            │
│   ▼                               ▼                               ▼            │
│ ┌─────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐ │
│ │   智能抽取层    │  │      知识图谱层          │  │       检索层            │ │
│ │ ┌─────────────┐ │  │ ┌─────────────────────┐ │  │ ┌─────────────────────┐ │ │
│ │ │SmartExtract │ │  │ │TemporalKnowledgeGraph│ │  │ │ TenLayerRetriever   │ │ │
│ │ │ - Local     │ │  │ │ - Nodes (Unified)   │ │  │ │ - Bloom Filter     │ │ │
│ │ │ - Hybrid    │ │  │ │ - Edges (Temporal)  │ │  │ │ - Temporal Filter  │ │ │
│ │ │ - LLM       │ │  │ │ - Episodes          │ │  │ │ - Inverted Index   │ │ │
│ │ └─────────────┘ │  │ │ - Temporal Index    │ │  │ │ - Entity Index     │ │ │
│ │ ┌─────────────┐ │  │ │ - Vector Index      │ │  │ │ - Graph Traversal  │ │ │
│ │ │RelationExt  │ │  │ └─────────────────────┘ │  │ │ - N-gram Index     │ │ │
│ │ └─────────────┘ │  │ ┌─────────────────────┐ │  │ │ - Vector Search    │ │ │
│ │ ┌─────────────┐ │  │ │ ContradictionMgr    │ │  │ │ - Cross-Encoder    │ │ │
│ │ │ 3-Stage     │ │  │ │ - Detect            │ │  │ │ - LLM Rerank       │ │ │
│ │ │ Deduplicator│ │  │ │ - Resolve           │ │  │ └─────────────────────┘ │ │
│ │ └─────────────┘ │  │ └─────────────────────┘ │  │ ┌─────────────────────┐ │ │
│ └─────────────────┘  └─────────────────────────┘  │ │ ContextBuilder      │ │ │
│                                                   │ └─────────────────────┘ │ │
│                                                   └─────────────────────────┘ │
│                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────┐ │
│   │                         Recall 独有模块（完整保留）                       │ │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│   │  │Foreshadowing│  │ContextTrack │  │ CoreSettings│  │ VolumeManager│     │ │
│   │  │ Tracker     │  │ er          │  │ (L0)        │  │ (100%不遗忘) │     │ │
│   │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │ │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                      │ │
│   │  │Consistency  │  │ Memory      │  │ Multi-Tenant│                      │ │
│   │  │ Checker     │  │ Summarizer  │  │ Storage     │                      │ │
│   │  └─────────────┘  └─────────────┘  └─────────────┘                      │ │
│   └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│   ┌─────────────────────────────────────────────────────────────────────────┐ │
│   │                           存储层                                         │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐    │ │
│   │  │  本地存储（默认，零依赖）                                         │    │ │
│   │  │  - JSON 文件（节点、边、索引）                                    │    │ │
│   │  │  - FAISS 向量索引                                                │    │ │
│   │  │  - SQLite（可选，大规模场景）                                     │    │ │
│   │  └─────────────────────────────────────────────────────────────────┘    │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐    │ │
│   │  │  可选外部后端                                                     │    │ │
│   │  │  - Neo4j | FalkorDB | Neptune（企业级场景）                       │    │ │
│   │  └─────────────────────────────────────────────────────────────────┘    │ │
│   └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📅 实施计划

### Phase 1: 核心基础（3周）

**目标：三时态数据模型 + 时序知识图谱**

| 周次 | 任务 | 产出 |
|------|------|------|
| W1 | 数据模型设计 | `TemporalFact`, `UnifiedNode`, `EpisodicNode` |
| W1 | 迁移工具 | v3 → v4 数据迁移脚本 |
| W2 | `TemporalKnowledgeGraph` 实现 | 核心 CRUD + 时态查询 |
| W2 | 索引系统 | `TemporalIndex`, `FullTextIndex` 集成 |
| W3 | 矛盾检测与处理 | `ContradictionManager` |
| W3 | 图遍历 API | BFS/DFS + 时态过滤 |

**验收标准：**
- [ ] 所有现有测试通过
- [ ] 时态查询 API 可用
- [ ] v3 数据可无损迁移

### Phase 2: 智能层（2周）

**目标：混合智能抽取 + 三阶段去重**

| 周次 | 任务 | 产出 |
|------|------|------|
| W4 | `SmartExtractor` 框架 | 三模式切换 + 复杂度评估 |
| W4 | LLM 抽取 Prompt | 实体/关系/时态抽取提示词 |
| W5 | `ThreeStageDeduplicator` | MinHash+LSH → Semantic → LLM |
| W5 | 预算管理系统 | `BudgetManager` |

**验收标准：**
- [ ] 本地模式可完全离线运行
- [ ] 混合模式成本可控
- [ ] 去重准确率 ≥95%

### Phase 3: 检索升级（2周）

**目标：十层漏斗检索器**

| 周次 | 任务 | 产出 |
|------|------|------|
| W6 | `TenLayerRetriever` 重构 | 新增 L2 时态 + L5 图遍历 + L9 CrossEncoder |
| W6 | `RetrievalConfig` | 可配置的检索策略 |
| W7 | RRF 融合优化 | 自适应权重 |
| W7 | 性能优化 | 缓存 + 并行 |

**验收标准：**
- [ ] 检索延迟 < 100ms (p95)
- [ ] 召回率提升 ≥10%

### Phase 4: 集成层（2周）

**目标：MCP Server + API 扩展**

| 周次 | 任务 | 产出 |
|------|------|------|
| W8 | `RecallMCPServer` | 15+ 工具实现 |
| W8 | MCP 配置系统 | YAML 配置 + 环境变量 |
| W9 | REST API 扩展 | 时态查询、图遍历端点 |
| W9 | SDK 封装 | 异步 API + 同步包装 |

**验收标准：**
- [ ] Claude Desktop 可正常连接
- [ ] Cursor 集成测试通过

### Phase 5: 文档与生态（1周）

| 周次 | 任务 | 产出 |
|------|------|------|
| W10 | API 文档 | OpenAPI Spec + 示例 |
| W10 | 使用指南 | 快速开始 + 场景指南 |
| W10 | 迁移指南 | v3 → v4 升级说明 |

---

## 🎯 最终对比：Recall 4.0 vs Graphiti

| 能力维度 | Graphiti | Recall 4.0 | 胜者 |
|----------|----------|------------|------|
| **时态系统** | 双时态 | 三时态 | 🏆 Recall |
| **图数据库依赖** | 必需 | 可选 | 🏆 Recall |
| **智能抽取** | 纯 LLM | 三模式自适应 | 🏆 Recall |
| **运行成本** | 高 | 可控 | 🏆 Recall |
| **检索层数** | 3层 | 10层 | 🏆 Recall |
| **去重阶段** | 2阶段 | 3阶段 | 🏆 Recall |
| **MCP 工具数** | 8个 | 15+个 | 🏆 Recall |
| **离线运行** | ❌ | ✅ | 🏆 Recall |
| **伏笔追踪** | ❌ | ✅ | 🏆 Recall |
| **持久条件** | ❌ | ✅ | 🏆 Recall |
| **100%不遗忘** | ❌ | ✅ | 🏆 Recall |
| **部署复杂度** | 高 | 零配置 | 🏆 Recall |
| **多租户** | ✅ | ✅ | 平 |
| **向量嵌入** | 单向量 | 多向量 | 🏆 Recall |
| **场景覆盖** | Agent | 全场景 | 🏆 Recall |

---

## 📝 注意事项

### 向后兼容保证

1. **API 兼容**
   - 所有 v3 API 保持不变
   - 新功能通过新 API 暴露
   - 废弃 API 保留至少 2 个版本

2. **数据兼容**
   - 自动检测数据版本
   - 首次启动自动迁移
   - 保留原始数据备份

3. **配置兼容**
   - 现有配置继续有效
   - 新配置使用合理默认值

### 风险控制

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 迁移数据损坏 | 低 | 高 | 自动备份 + 回滚机制 |
| 性能回退 | 中 | 中 | 基准测试 + 性能监控 |
| API 不兼容 | 低 | 高 | 版本化 API + 兼容层 |

---

## ✅ 成功标准

1. **功能完整性**
   - [ ] 所有 Graphiti 核心功能已覆盖
   - [ ] 所有 Recall 独有功能保留
   - [ ] 新增功能全部可用

2. **性能指标**
   - [ ] 添加延迟 < 200ms (无 LLM)
   - [ ] 检索延迟 < 100ms
   - [ ] 内存占用 < 500MB (轻量模式)

3. **质量指标**
   - [ ] 测试覆盖率 ≥ 80%
   - [ ] 无严重 Bug
   - [ ] 文档完整

---

**准备好开始实施 Phase 1 了吗？**
