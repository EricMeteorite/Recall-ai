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
| 检索层数 | 3层 | **11层** | 更精细的漏斗 |
| 重排序器 | 5种 | **7种** | 新增时态/伏笔重排 |
| 融合算法 | RRF | **RRF + 自适应权重** | 场景感知融合 |
| 图遍历 | 简单 BFS | **多策略** | BFS/DFS/随机游走 |

```python
class ElevenLayerRetriever:
    """十一层漏斗检索器（概述版，详见 Phase 3）"""
    
    class Layer(Enum):
        L1_BLOOM_FILTER = "bloom"            # 快速否定
        L2_TEMPORAL_FILTER = "temporal"      # 时态过滤【新增】
        L3_INVERTED_INDEX = "inverted"       # 关键词匹配
        L4_ENTITY_INDEX = "entity"           # 实体关联
        L5_GRAPH_TRAVERSAL = "graph"         # 图遍历【新增】
        L6_NGRAM_INDEX = "ngram"             # 模糊匹配
        L7_VECTOR_COARSE = "vector_coarse"   # 向量粗筛
        L8_VECTOR_FINE = "vector_fine"       # 向量精排
        L9_RERANK = "rerank"                 # TF-IDF 重排序
        L10_CROSS_ENCODER = "cross_encoder"  # 交叉编码器【新增】
        L11_LLM_FILTER = "llm_filter"        # LLM 过滤
    
    async def retrieve(
        self,
        query: str,
        config: RetrievalConfig = None,
        temporal_context: TemporalContext = None,
        entities: List[str] = None
    ) -> List[RetrievalResult]:
        """执行十一层检索（详细实现见 Phase 3）"""
        
        config = config or RetrievalConfig.default()
        candidates = set()
        scores = defaultdict(float)
        
        # L1: Bloom Filter - O(1) 快速否定
        if config.l1_enabled:
            keywords = self._extract_keywords(query)
            keywords = [k for k in keywords if k in self.bloom_filter]
        
        # L2: 时态过滤【新增】
        if config.l2_enabled and temporal_context:
            # 预先过滤时间范围外的文档
            temporal_candidates = self._l2_temporal_filter(temporal_context, config)
        
        # L3: 倒排索引 - 关键词匹配
        if config.l3_enabled:
            inverted_results = self.inverted_index.search(keywords)
            for doc_id, score in inverted_results:
                candidates.add(doc_id)
                scores[doc_id] += score * config.weights.inverted
        
        # L4: 实体索引
        if config.l4_enabled:
            for entity in entities or []:
                for doc_id in self.entity_index.get_docs(entity):
                    candidates.add(doc_id)
                    scores[doc_id] += config.weights.entity
        
        # L5: 图遍历【新增】
        if config.l5_enabled and entities:
            self._l5_graph_traversal(entities, candidates, scores, config)
        
        # L6: N-gram 索引 - 模糊匹配
        if config.l6_enabled:
            ngram_results = self.ngram_index.search(query)
            for doc_id in ngram_results:
                candidates.add(doc_id)
                scores[doc_id] += config.weights.ngram
        
        # L7: 向量粗筛
        if config.l7_enabled and self.vector_index:
            vector_results = self.vector_index.search(query, top_k=config.l7_vector_top_k)
            for doc_id, sim in vector_results:
                candidates.add(doc_id)
                scores[doc_id] += sim * config.weights.vector
        
        # L8: 向量精排
        if config.l8_enabled and len(candidates) > config.fine_rank_threshold:
            self._l8_vector_fine(query, candidates, scores, config)
        
        # L9: TF-IDF 重排序
        if config.l9_enabled:
            self._l9_rerank(query, candidates, scores)
        
        # L10: Cross-Encoder 重排序【新增，可选】
        if config.l10_enabled and self.cross_encoder:
            self._l10_cross_encoder(query, candidates, scores, config)
        
        # L11: LLM 重排序【可选，高成本】
        if config.l11_enabled and self.llm_client:
            candidates, scores = await self._l11_llm_filter(query, candidates, scores, config)
        
        # 最终排序
        final_results = sorted(
            [(doc_id, scores[doc_id]) for doc_id in candidates],
            key=lambda x: x[1],
            reverse=True
        )
        
        return [
            RetrievalResult(id=doc_id, score=score, content=self._get_content(doc_id))
            for doc_id, score in final_results[:config.final_top_k]
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
│ │ │SmartExtract │ │  │ │TemporalKnowledgeGraph│ │  │ │ ElevenLayerRetriever│ │ │
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

### Phase 1: 核心基础（3周）✅ 已完成

**目标：三时态数据模型 + 时序知识图谱**

| 周次 | 任务 | 产出 | 状态 |
|------|------|------|------|
| W1 | 数据模型设计 | `TemporalFact`, `UnifiedNode`, `EpisodicNode` | ✅ 完成 |
| W1 | 迁移工具 | v3 → v4 数据迁移脚本 | ✅ 完成 |
| W2 | `TemporalKnowledgeGraph` 实现 | 核心 CRUD + 时态查询 | ✅ 完成 |
| W2 | 索引系统 | `TemporalIndex`, `FullTextIndex` 集成 | ✅ 完成 |
| W3 | 矛盾检测与处理 | `ContradictionManager` | ✅ 完成 |
| W3 | 图遍历 API | BFS/DFS + 时态过滤 | ✅ 完成 |

**已完成的文件：**
```
recall/models/temporal.py          # ~575 行 - 三时态数据模型
recall/index/temporal_index.py     # ~495 行 - 时态索引
recall/index/fulltext_index.py     # ~413 行 - BM25 全文索引
recall/graph/temporal_knowledge_graph.py  # ~1230 行 - 时态知识图谱
recall/graph/contradiction_manager.py     # ~554 行 - 矛盾管理器
tools/migrate_v3_to_v4.py          # ~721 行 - 数据迁移工具
recall/models/__init__.py          # 更新导出
recall/index/__init__.py           # 更新导出
recall/graph/__init__.py           # 更新导出
```

**📊 代码统计：**
| 类别 | 文件数 | 总行数 |
|------|--------|--------|
| 核心模块 | 5 | ~3,267 行 |
| 迁移工具 | 1 | ~721 行 |
| 导出更新 | 3 | ~30 行 |
| **合计** | **9** | **~4,018 行** |

**🔑 关键 API 摘要：**

| 模块 | 核心类/方法 | 功能 |
|------|-------------|------|
| `temporal.py` | `TemporalFact`, `UnifiedNode`, `EpisodicNode` | 三时态数据模型 |
| `temporal.py` | `NodeType`, `EdgeType`, `ContradictionType` | 可扩展枚举类型 |
| `temporal_index.py` | `TemporalIndex.query_at_time()` | 时间点查询 |
| `temporal_index.py` | `TemporalIndex.query_range()` | 时间范围查询 |
| `temporal_index.py` | `TemporalIndex.query_timeline()` | 时间线查询 |
| `fulltext_index.py` | `FullTextIndex.search()` | BM25 全文搜索 |
| `temporal_knowledge_graph.py` | `add_node()`, `add_edge()` | 节点/边 CRUD |
| `temporal_knowledge_graph.py` | `query_at_time()`, `query_timeline()` | 时态查询 |
| `temporal_knowledge_graph.py` | `bfs()`, `dfs()` | 图遍历 |
| `temporal_knowledge_graph.py` | `compare_snapshots()` | 快照对比 |
| `contradiction_manager.py` | `detect()` | 矛盾检测 |
| `contradiction_manager.py` | `resolve()` | 矛盾解决 |
| `migrate_v3_to_v4.py` | `migrate()` | 数据迁移 |

**🌐 通用性说明：**

Phase 1 所有代码都是 **100% 平台无关** 的通用实现：
- ✅ 纯 Python 标准库 + dataclasses
- ✅ JSON 持久化，无外部数据库依赖
- ✅ 无任何 SillyTavern 或其他前端特定代码
- ✅ 可被任何客户端/前端通过 REST API 集成

> 💡 **SillyTavern 集成说明**：Phase 1 是后端基础设施层，SillyTavern 插件需等待 Phase 2 完成 REST API 端点后才能使用新功能。

**验收标准：**
- [x] 所有现有测试通过（RecallEngine, MultiTenantStorage, EntityExtractor 等核心模块正常）
- [x] 时态查询 API 可用（query_at_time, query_timeline, compare_snapshots）
- [x] v3 数据可无损迁移（migrate_v3_to_v4.py 支持自动备份和增量迁移）

**完成日期：** 2026-01-23

### Phase 2: 智能层（2周）✅ 已完成

**目标：混合智能抽取 + 三阶段去重 + REST API 扩展 + 配置系统升级**

| 周次 | 任务 | 产出 | 状态 |
|------|------|------|------|
| W4 | `SmartExtractor` 框架 | 三模式切换 + 复杂度评估 | ✅ 完成 |
| W4 | LLM 抽取 Prompt | 实体/关系/时态抽取提示词 | ✅ 完成 |
| W4 | **配置系统升级** | 统一配置 + Phase 1 模块配置项 | ✅ 完成 |
| W5 | `ThreeStageDeduplicator` | MinHash+LSH → Semantic → LLM | ✅ 完成 |
| W5 | 预算管理系统 | `BudgetManager` | ✅ 完成 |
| W5 | **REST API 扩展** | Phase 1 功能的 HTTP 端点 | ✅ 完成 |
| W5 | **RecallEngine 集成** | 将 Phase 1 模块接入引擎 | ✅ 完成 |

**已完成的文件：**
```
recall/processor/smart_extractor.py        # ~580 行 - 智能抽取器（三模式）
recall/processor/three_stage_deduplicator.py  # ~622 行 - 三阶段去重器
recall/utils/budget_manager.py             # ~445 行 - LLM 预算管理器
recall/server.py                           # 更新 - REST API 端点 + 配置系统
recall/engine.py                           # 更新 - Phase 1 模块集成
recall/utils/environment.py                # 更新 - 废弃 recall.json
recall/processor/__init__.py               # 更新 - 模块导出
recall/utils/__init__.py                   # 更新 - 模块导出
start.ps1                                  # 更新 - 51 个配置项
start.sh                                   # 更新 - 51 个配置项
tests/test_phase2.py                       # 新增 - Phase 2 测试
tools/verify_config.py                     # 新增 - 配置一致性验证
tools/verify_phase2.py                     # 新增 - 验收标准验证
```

**📊 代码统计：**
| 类别 | 文件数 | 总行数 |
|------|--------|--------|
| 核心模块 | 3 | ~1,647 行 |
| 更新文件 | 5 | ~500+ 行修改 |
| 测试/工具 | 3 | ~300 行 |
| **合计** | **11** | **~2,500 行** |

**🔑 关键 API 摘要：**

| 模块 | 核心类/方法 | 功能 |
|------|-------------|------|
| `smart_extractor.py` | `SmartExtractor` | 三模式智能抽取 |
| `smart_extractor.py` | `ExtractionMode.LOCAL/HYBRID/LLM_FULL` | 抽取模式枚举 |
| `smart_extractor.py` | `_assess_complexity()` | 文本复杂度评估 |
| `three_stage_deduplicator.py` | `ThreeStageDeduplicator` | 三阶段去重 |
| `three_stage_deduplicator.py` | `Stage 1: MinHash+LSH` | 确定性快速匹配 |
| `three_stage_deduplicator.py` | `Stage 2: Semantic` | 语义相似度匹配 |
| `three_stage_deduplicator.py` | `Stage 3: LLM` | LLM 确认（可选） |
| `budget_manager.py` | `BudgetManager` | LLM 预算控制 |
| `budget_manager.py` | `can_afford()` | 预算检查 |
| `budget_manager.py` | `record_usage()` | 使用记录 |
| `server.py` | `/v1/temporal/*` | 时态查询 API |
| `server.py` | `/v1/contradictions/*` | 矛盾管理 API |
| `server.py` | `/v1/search/fulltext` | 全文搜索 API |
| `server.py` | `/v1/graph/traverse` | 图遍历 API |

---

#### 📁 配置系统升级

**现状分析：**
| 配置文件 | 位置 | 状态 |
|---------|------|------|
| `api_keys.env` | `recall_data/config/` | ✅ **主配置文件** - 已统一大部分配置 |
| `recall.json` | `recall_data/config/` | ⚠️ **废弃** - v3.0.0 遗留，不再使用 |

**升级方案：将所有配置统一到 `api_keys.env`**

**需要添加的 Phase 1 配置项：**

```env
# ============================================================================
# Recall 4.0 新增配置项
# Recall 4.0 New Configuration
# ============================================================================

# ----------------------------------------------------------------------------
# 时态知识图谱配置
# Temporal Knowledge Graph Configuration
# ----------------------------------------------------------------------------
# 是否启用时态知识图谱 (true/false)
TEMPORAL_GRAPH_ENABLED=true

# 图谱存储后端: local(本地JSON) | neo4j | falkordb
# Graph storage backend
TEMPORAL_GRAPH_BACKEND=local

# 图谱作用域: global(全局共享) | isolated(用户隔离)
# Graph scope
TEMPORAL_GRAPH_SCOPE=global

# ----------------------------------------------------------------------------
# 矛盾检测配置
# Contradiction Detection Configuration
# ----------------------------------------------------------------------------
# 检测策略: rule_only(仅规则) | llm_only(仅LLM) | hybrid(混合) | auto(自动)
# Detection strategy
CONTRADICTION_STRATEGY=rule_only

# 是否自动解决低置信度矛盾 (true/false)
# Auto-resolve low-confidence contradictions
CONTRADICTION_AUTO_RESOLVE=false

# 默认解决策略: supersede(取代) | coexist(共存) | reject(拒绝) | manual(人工)
# Default resolution strategy
CONTRADICTION_DEFAULT_RESOLUTION=manual

# ----------------------------------------------------------------------------
# 全文索引配置 (BM25)
# Full-text Index Configuration (BM25)
# ----------------------------------------------------------------------------
# 是否启用 BM25 全文索引 (true/false)
FULLTEXT_INDEX_ENABLED=true

# BM25 参数 k1 (控制词频饱和度，默认1.5)
FULLTEXT_BM25_K1=1.5

# BM25 参数 b (控制文档长度归一化，默认0.75)
FULLTEXT_BM25_B=0.75

# BM25 参数 delta (IDF 平滑，默认0.5)
FULLTEXT_BM25_DELTA=0.5

# ----------------------------------------------------------------------------
# 时态索引配置
# Temporal Index Configuration
# ----------------------------------------------------------------------------
# 是否启用时态索引 (true/false)
TEMPORAL_INDEX_ENABLED=true

# ----------------------------------------------------------------------------
# 智能抽取配置 (Phase 2 新增)
# Smart Extraction Configuration
# ----------------------------------------------------------------------------
# 抽取模式: local(纯本地) | hybrid(混合) | llm(纯LLM)
SMART_EXTRACTOR_MODE=hybrid

# 复杂度阈值 (0.0-1.0，超过此值使用 LLM)
SMART_EXTRACTOR_COMPLEXITY_THRESHOLD=0.6

# 每日 LLM 预算（美元，0=不限制）
SMART_EXTRACTOR_DAILY_BUDGET=1.0
```

**配置加载优先级：**
1. 环境变量（最高优先级，用于 Docker/CI）
2. `api_keys.env` 文件（用户主配置）
3. 代码内默认值（保底）

**废弃 `recall.json`：**
- Phase 2 完成后，`recall.json` 将不再被读取
- 迁移脚本会自动将 `recall.json` 中的有效配置转移到 `api_keys.env`

---

#### 📜 脚本文件配置同步

**需要更新的文件：**

| 文件 | 类型 | 当前状态 | Phase 2 任务 |
|------|------|---------|-------------|
| `start.ps1` | Windows 启动脚本 | ✅ 已使用 `api_keys.env` | 添加 Phase 1 配置项 |
| `start.sh` | Linux 启动脚本 | ✅ 已使用 `api_keys.env` | 添加 Phase 1 配置项 |
| `manage.ps1` | Windows 管理脚本 | ⚠️ 使用 `manager.json` | 可保留（管理器专用配置） |
| `manage.sh` | Linux 管理脚本 | ⚠️ 使用独立配置 | 可保留（管理器专用配置） |
| `install.ps1` | Windows 安装脚本 | ✅ 无配置依赖 | 无需修改 |
| `install.sh` | Linux 安装脚本 | ✅ 无配置依赖 | 无需修改 |
| `recall/utils/environment.py` | Python 环境管理 | ⚠️ 使用 `recall.json` | **废弃 JSON 配置** |
| `recall/server.py` | API 服务器 | ✅ 已使用 `api_keys.env` | 添加 Phase 1 配置项 |

**具体更新任务：**

1. **`start.ps1` / `start.sh`** - 添加 Phase 1 支持的配置项：
   ```powershell
   # 新增配置项列表
   $supportedKeys = @(
       # ... 现有配置项 ...
       # Phase 1 新增
       'TEMPORAL_GRAPH_ENABLED', 'TEMPORAL_GRAPH_BACKEND', 'TEMPORAL_GRAPH_SCOPE',
       'CONTRADICTION_STRATEGY', 'CONTRADICTION_AUTO_RESOLVE', 'CONTRADICTION_DEFAULT_RESOLUTION',
       'FULLTEXT_INDEX_ENABLED', 'FULLTEXT_BM25_K1', 'FULLTEXT_BM25_B', 'FULLTEXT_BM25_DELTA',
       'TEMPORAL_INDEX_ENABLED',
       'SMART_EXTRACTOR_MODE', 'SMART_EXTRACTOR_COMPLEXITY_THRESHOLD', 'SMART_EXTRACTOR_DAILY_BUDGET'
   )
   ```

2. **`recall/utils/environment.py`** - 废弃 `recall.json` 相关代码：
   ```python
   # 删除 _create_default_config() 中的 recall.json 逻辑
   # 删除 load_config() 和 save_config() 中的 recall.json 引用
   # 改为读取 api_keys.env 或直接使用环境变量
   ```

3. **`recall/server.py`** - 添加 Phase 1 配置项到 `SUPPORTED_CONFIG_KEYS`：
   ```python
   SUPPORTED_CONFIG_KEYS = {
       # ... 现有配置项 ...
       # Phase 1 新增
       'TEMPORAL_GRAPH_ENABLED',
       'TEMPORAL_GRAPH_BACKEND',
       'TEMPORAL_GRAPH_SCOPE',
       'CONTRADICTION_STRATEGY',
       'CONTRADICTION_AUTO_RESOLVE',
       'CONTRADICTION_DEFAULT_RESOLUTION',
       'FULLTEXT_INDEX_ENABLED',
       'FULLTEXT_BM25_K1',
       'FULLTEXT_BM25_B',
       'FULLTEXT_BM25_DELTA',
       'TEMPORAL_INDEX_ENABLED',
       'SMART_EXTRACTOR_MODE',
       'SMART_EXTRACTOR_COMPLEXITY_THRESHOLD',
       'SMART_EXTRACTOR_DAILY_BUDGET',
   }
   ```

4. **默认配置模板** - 更新 `get_default_config_content()` 添加 Phase 1 配置段

---

**📡 需要添加的 REST API 端点（暴露 Phase 1 功能）：**

| 端点 | 方法 | 功能 | 对应模块 |
|------|------|------|----------|
| `/v1/temporal/at` | GET | 时间点快照查询 | `TemporalKnowledgeGraph.query_at_time()` |
| `/v1/temporal/range` | GET | 时间范围查询 | `TemporalIndex.query_range()` |
| `/v1/temporal/timeline` | GET | 实体时间线 | `TemporalKnowledgeGraph.query_timeline()` |
| `/v1/temporal/snapshot` | GET | 获取快照 | `TemporalKnowledgeGraph.get_snapshot()` |
| `/v1/temporal/snapshot/compare` | GET | 快照对比 | `TemporalKnowledgeGraph.compare_snapshots()` |
| `/v1/contradictions` | GET | 矛盾列表 | `ContradictionManager.get_pending()` |
| `/v1/contradictions/{id}/resolve` | POST | 解决矛盾 | `ContradictionManager.resolve()` |
| `/v1/search/fulltext` | GET | BM25 全文搜索 | `FullTextIndex.search()` |
| `/v1/graph/traverse` | POST | 图遍历 | `TemporalKnowledgeGraph.bfs()` |
| `/v1/migrate/v3-to-v4` | POST | 触发迁移 | `migrate_v3_to_v4.migrate()` |

> 💡 **SillyTavern 集成**：上述 API 完成后，SillyTavern 插件可添加「时间线」「矛盾管理」等新功能标签页。

**验收标准：**
- [x] 本地模式可完全离线运行
- [x] 混合模式成本可控
- [x] 去重准确率 ≥95%
- [x] Phase 1 功能的 REST API 全部可用
- [x] 配置系统统一到 `api_keys.env`
- [x] `recall.json` 完全废弃
- [x] Phase 1 模块集成到 RecallEngine
- [x] `start.ps1` / `start.sh` 支持所有 Phase 1 配置项
- [x] `recall/server.py` 的 `SUPPORTED_CONFIG_KEYS` 已更新
- [x] `recall/utils/environment.py` 不再依赖 `recall.json`

**完成日期：** 2026-01-23

### Phase 3: 检索升级（2周）

**目标：十一层漏斗检索器 + 时态/图谱检索能力**

将现有 8 层检索器升级为 11 层，新增：
- **L2 时态过滤**：利用 Phase 1 的 `TemporalIndex` 实现时间范围预筛选
- **L5 图遍历**：利用 Phase 1 的 `TemporalKnowledgeGraph.bfs()` 实现关系扩展检索
- **L10 CrossEncoder**：可选的交叉编码器精排，提升排序质量

同时重构配置系统，从 dict 升级为类型安全的 `RetrievalConfig` dataclass。

| 周次 | 任务 | 产出 | 状态 |
|------|------|------|------|
| W6 | `RetrievalConfig` 配置类 | 可配置的检索策略 | ⏳ 待开始 |
| W6 | `ElevenLayerRetriever` 框架 | 11 层检索器骨架 | ⏳ 待开始 |
| W6 | L2 时态过滤层 | 时间范围预筛选 | ⏳ 待开始 |
| W6 | L5 图遍历层 | BFS 关系扩展 | ⏳ 待开始 |
| W7 | 迁移现有层逻辑 | 从 `EightLayerRetriever` 迁移 | ⏳ 待开始 |
| W7 | Engine 集成 | 替换旧检索器 | ⏳ 待开始 |
| W7 | L10 CrossEncoder（可选） | 交叉编码器重排序 | ⏳ 待开始 |
| W7 | 性能优化 | 缓存 + 并行 | ⏳ 待开始 |

---

#### 📐 现有架构分析

**当前 `EightLayerRetriever` (445 行) - L1 至 L8：**

```
┌─────────────────────────────────────────────────────────────────┐
│                    EightLayerRetriever (现有)                    │
├─────────────────────────────────────────────────────────────────┤
│  L1: Bloom Filter      → 快速否定，O(1) 排除不相关文档           │
│  L2: Inverted Index    → 关键词匹配，BM25 评分                  │
│  L3: Entity Index      → 实体关联，命中实体加分                  │
│  L4: N-gram Index      → 模糊匹配，处理错别字/变体              │
│  L5: Vector Coarse     → 向量粗筛，top_k=200                    │
│  L6: Vector Fine       → 向量精排，重计算相似度                  │
│  L7: Rerank            → TF-IDF 重排序                          │
│  L8: LLM Filter        → LLM 相关性过滤（可选）                 │
└─────────────────────────────────────────────────────────────────┘
```

**现有配置方式：**
```python
# 当前使用 dict 配置
self.config = {
    'l1_enabled': True,   # Bloom Filter
    'l2_enabled': True,   # Inverted Index
    'l3_enabled': True,   # Entity Index
    'l4_enabled': True,   # N-gram Index
    'l5_enabled': True,   # Vector Coarse
    'l6_enabled': True,   # Vector Fine
    'l7_enabled': True,   # Rerank
    'l8_enabled': False,  # LLM Filter (默认关闭)
}
```

**Engine 集成点：**
- 初始化位置：[engine.py#L272](recall/engine.py#L272)
- 调用位置：[engine.py#L862](recall/engine.py#L862) `retriever.retrieve(query, entities, keywords, top_k, filters)`

---

#### 🎯 升级方案：8 层 → 11 层

**升级策略：在现有 8 层基础上插入 3 个新层，保持原有层的相对顺序**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         层级映射：EightLayer → ElevenLayer                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│  旧层号    新层号    名称                    变化                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│  L1    →   L1      Bloom Filter           [保留] 快速否定                       │
│  -     →   L2      Temporal Filter        [新增] 时间范围预筛选                 │
│  L2    →   L3      Inverted Index         [保留] 关键词匹配                     │
│  L3    →   L4      Entity Index           [保留] 实体关联                       │
│  -     →   L5      Graph Traversal        [新增] BFS 图遍历扩展                 │
│  L4    →   L6      N-gram Index           [保留] 模糊匹配                       │
│  L5    →   L7      Vector Coarse          [保留] 向量粗筛                       │
│  L6    →   L8      Vector Fine            [保留] 向量精排                       │
│  L7    →   L9      Rerank                 [保留] TF-IDF 重排序                  │
│  -     →   L10     Cross-Encoder          [新增] 交叉编码器精排（可选）         │
│  L8    →   L11     LLM Filter             [保留] LLM 最终过滤（可选）           │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**新架构 `ElevenLayerRetriever`：**

```
┌─────────────────────────────────────────────────────────────────┐
│                   ElevenLayerRetriever (目标)                    │
├─────────────────────────────────────────────────────────────────┤
│                        === 快速过滤阶段 ===                      │
│  L1:  Bloom Filter       → [保留] O(1) 快速否定                  │
│  L2:  Temporal Filter    → [新增] 时间范围预筛选                 │
│                                                                 │
│                        === 召回阶段 ===                          │
│  L3:  Inverted Index     → [保留] 关键词匹配，BM25              │
│  L4:  Entity Index       → [保留] 实体关联召回                   │
│  L5:  Graph Traversal    → [新增] BFS 图遍历扩展                 │
│  L6:  N-gram Index       → [保留] 模糊匹配召回                   │
│  L7:  Vector Coarse      → [保留] 向量粗筛，ANN                  │
│                                                                 │
│                        === 精排阶段 ===                          │
│  L8:  Vector Fine        → [保留] 向量精排，精确距离             │
│  L9:  Rerank             → [保留] TF-IDF 多因素重排              │
│  L10: Cross-Encoder      → [新增] 交叉编码器精排（可选）         │
│  L11: LLM Filter         → [保留] LLM 语义过滤（可选）           │
└─────────────────────────────────────────────────────────────────┘
```

**设计原则：**
1. **快速过滤在前** - L1-L2 快速排除大量不相关文档
2. **召回在中** - L3-L7 多路召回，确保高召回率
3. **精排在后** - L8-L11 逐步精细化排序，确保高精度
4. **成本递增** - 越往后成本越高，候选数越少

---

#### 📋 详细实施计划

##### 步骤 1: 创建 `RetrievalConfig` 类 (~150 行)

**文件：** `recall/retrieval/config.py` (新建)

```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime

@dataclass
class LayerWeights:
    """各层权重配置"""
    inverted: float = 1.0      # 倒排索引权重
    entity: float = 1.2        # 实体索引权重
    graph: float = 1.0         # 图遍历权重
    ngram: float = 0.8         # N-gram 权重
    vector: float = 1.0        # 向量权重
    temporal: float = 0.5      # 时态权重

@dataclass
class TemporalContext:
    """时态查询上下文"""
    start: Optional[datetime] = None    # 时间范围起点
    end: Optional[datetime] = None      # 时间范围终点
    reference: Optional[datetime] = None  # 参考时间点
    
    def has_time_constraint(self) -> bool:
        """是否有时间约束"""
        return self.start is not None or self.end is not None

@dataclass
class LayerStats:
    """层级执行统计"""
    layer: str                  # 层名称（如 "L2_TEMPORAL_FILTER"）
    input_count: int            # 输入候选数
    output_count: int           # 输出候选数
    time_ms: float              # 耗时（毫秒）

@dataclass
class RetrievalResult:
    """检索结果"""
    id: str                     # 文档 ID
    score: float                # 综合得分
    content: str = ""           # 文档内容（可选填充）

@dataclass
class RetrievalConfig:
    """检索配置 - 类型安全 + 默认值"""
    
    # === 层开关（L1-L11）===
    l1_enabled: bool = True     # Bloom Filter
    l2_enabled: bool = True     # Temporal Filter【新增】
    l3_enabled: bool = True     # Inverted Index
    l4_enabled: bool = True     # Entity Index
    l5_enabled: bool = True     # Graph Traversal【新增】
    l6_enabled: bool = True     # N-gram Index
    l7_enabled: bool = True     # Vector Coarse
    l8_enabled: bool = True     # Vector Fine
    l9_enabled: bool = True     # Rerank
    l10_enabled: bool = False   # Cross-Encoder【新增，默认关闭】
    l11_enabled: bool = False   # LLM Filter【默认关闭】
    
    # === Top-K 配置 ===
    l2_temporal_top_k: int = 500       # 时态层保留数
    l3_inverted_top_k: int = 100
    l4_entity_top_k: int = 50
    l5_graph_top_k: int = 100          # 图遍历保留数
    l6_ngram_top_k: int = 30
    l7_vector_top_k: int = 200
    fine_rank_threshold: int = 100     # 触发 L8 精排的候选数
    l10_cross_encoder_top_k: int = 50  # CrossEncoder 处理数
    l11_llm_top_k: int = 20            # LLM 处理数
    final_top_k: int = 20
    
    # === L5 图遍历配置 ===
    l5_graph_max_depth: int = 2        # BFS 最大深度
    l5_graph_max_entities: int = 3     # 起始实体数量限制
    l5_graph_direction: str = "both"   # out | in | both
    
    # === L11 LLM 配置 ===
    l11_llm_timeout: float = 10.0      # 超时时间（秒）
    
    # === 权重 ===
    weights: LayerWeights = field(default_factory=LayerWeights)
    
    # === 时态上下文 ===
    reference_time: Optional[datetime] = None
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    
    @classmethod
    def default(cls) -> "RetrievalConfig":
        """默认配置 - 禁用高成本层"""
        return cls()
    
    @classmethod
    def fast(cls) -> "RetrievalConfig":
        """快速模式 - 禁用重量级层"""
        return cls(
            l8_enabled=False,      # 跳过向量精排
            l9_enabled=False,      # 跳过重排序
            l10_enabled=False,     # 跳过 CrossEncoder
            l11_enabled=False,     # 跳过 LLM
            l7_vector_top_k=100
        )
    
    @classmethod
    def accurate(cls) -> "RetrievalConfig":
        """精准模式 - 启用所有层"""
        return cls(
            l10_enabled=True,      # 启用 CrossEncoder
            l11_enabled=True,      # 启用 LLM
            l7_vector_top_k=300,
            l10_cross_encoder_top_k=100
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（兼容旧 EightLayerRetriever）"""
        return {
            'l1_enabled': self.l1_enabled,
            'l2_enabled': self.l3_enabled,   # 旧 L2 = 新 L3
            'l3_enabled': self.l4_enabled,   # 旧 L3 = 新 L4
            'l4_enabled': self.l6_enabled,   # 旧 L4 = 新 L6
            'l5_enabled': self.l7_enabled,   # 旧 L5 = 新 L7
            'l6_enabled': self.l8_enabled,   # 旧 L6 = 新 L8
            'l7_enabled': self.l9_enabled,   # 旧 L7 = 新 L9
            'l8_enabled': self.l11_enabled,  # 旧 L8 = 新 L11
        }
```

---

##### 步骤 2: 创建 `ElevenLayerRetriever` 框架 (~700 行)

**文件：** `recall/retrieval/eleven_layer.py` (新建)

```python
import time
import json
import asyncio
import logging
from enum import Enum
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict

from .config import (
    RetrievalConfig, LayerStats, 
    RetrievalResult, TemporalContext
)

logger = logging.getLogger(__name__)


class RetrievalLayer(Enum):
    """检索层级 - 11 层"""
    # === 快速过滤阶段 ===
    L1_BLOOM_FILTER = "bloom_filter"
    L2_TEMPORAL_FILTER = "temporal_filter"    # 新增
    
    # === 召回阶段 ===
    L3_INVERTED_INDEX = "inverted_index"
    L4_ENTITY_INDEX = "entity_index"
    L5_GRAPH_TRAVERSAL = "graph_traversal"    # 新增
    L6_NGRAM_INDEX = "ngram_index"
    L7_VECTOR_COARSE = "vector_coarse"
    
    # === 精排阶段 ===
    L8_VECTOR_FINE = "vector_fine"
    L9_RERANK = "rerank"
    L10_CROSS_ENCODER = "cross_encoder"       # 新增
    L11_LLM_FILTER = "llm_filter"


class ElevenLayerRetriever:
    """十一层漏斗检索器
    
    检索流程（3 阶段 11 层）：
    
    [快速过滤阶段]
    L1:  Bloom Filter      - O(1) 快速否定不可能的候选
    L2:  Temporal Filter   - O(log n) 时间范围预筛选【新增】
    
    [召回阶段]
    L3:  Inverted Index    - O(log n) 关键词匹配
    L4:  Entity Index      - O(1) 实体关联查找
    L5:  Graph Traversal   - O(V+E) BFS 图遍历扩展【新增】
    L6:  N-gram Index      - O(k) 模糊匹配
    L7:  Vector Coarse     - O(n) 近似最近邻
    
    [精排阶段]
    L8:  Vector Fine       - O(k) 精确距离计算
    L9:  Rerank            - O(k log k) 多因素综合排序
    L10: Cross-Encoder     - O(k) 交叉编码器精排【新增，可选】
    L11: LLM Filter        - O(k) 语义相关性判断【可选】
    """
    
    def __init__(
        self,
        # 现有依赖（对应旧 L1-L8，新编号后为 L1, L3-L4, L6-L9, L11）
        bloom_filter=None,
        inverted_index=None,
        entity_index=None,
        ngram_index=None,
        vector_index=None,
        llm_client=None,
        content_store=None,
        # 新增依赖（L2, L5, L10）
        temporal_index=None,           # TemporalIndex (Phase 1)
        knowledge_graph=None,          # TemporalKnowledgeGraph (Phase 1)
        cross_encoder=None,            # CrossEncoder 模型
        # 配置
        config: RetrievalConfig = None
    ):
        # 现有依赖
        self.bloom_filter = bloom_filter
        self.inverted_index = inverted_index
        self.entity_index = entity_index
        self.ngram_index = ngram_index
        self.vector_index = vector_index
        self.llm_client = llm_client
        self.content_store = content_store
        
        # 新增依赖
        self.temporal_index = temporal_index
        self.knowledge_graph = knowledge_graph
        self.cross_encoder = cross_encoder
        
        self.config = config or RetrievalConfig.default()
        
        # 统计
        self.stats: List[LayerStats] = []
    
    async def retrieve(
        self,
        query: str,
        entities: List[str] = None,
        keywords: List[str] = None,
        top_k: int = None,
        filters: Dict = None,
        temporal_context: TemporalContext = None,
        config: RetrievalConfig = None
    ) -> List[RetrievalResult]:
        """执行十一层检索（异步，因 L11 需要）"""
        
        config = config or self.config
        top_k = top_k or config.final_top_k
        
        candidates = set()
        scores = defaultdict(float)
        
        # ========== 快速过滤阶段 ==========
        
        # L1: Bloom Filter - 快速否定
        if config.l1_enabled and self.bloom_filter:
            keywords = self._l1_bloom_filter(keywords)
        
        # L2: Temporal Filter - 时间范围预筛选【新增】
        temporal_candidates = None
        if config.l2_enabled and self.temporal_index and temporal_context:
            temporal_candidates = self._l2_temporal_filter(temporal_context, config)
        
        # ========== 召回阶段 ==========
        
        # L3: Inverted Index - 关键词匹配
        if config.l3_enabled and self.inverted_index:
            self._l3_inverted_index(keywords, candidates, scores, config, temporal_candidates)
        
        # L4: Entity Index - 实体关联
        if config.l4_enabled and self.entity_index:
            self._l4_entity_index(entities, candidates, scores, config, temporal_candidates)
        
        # L5: Graph Traversal - 图遍历扩展【新增】
        if config.l5_enabled and self.knowledge_graph and entities:
            self._l5_graph_traversal(entities, candidates, scores, config)
        
        # L6: N-gram Index - 模糊匹配
        if config.l6_enabled and self.ngram_index:
            self._l6_ngram_index(query, candidates, scores, config, temporal_candidates)
        
        # L7: Vector Coarse - 向量粗筛
        if config.l7_enabled and self.vector_index:
            self._l7_vector_coarse(query, candidates, scores, config)
        
        # ========== 精排阶段 ==========
        
        # L8: Vector Fine - 向量精排
        if config.l8_enabled and len(candidates) > config.fine_rank_threshold:
            self._l8_vector_fine(query, candidates, scores, config)
        
        # L9: Rerank - TF-IDF 重排序
        if config.l9_enabled:
            self._l9_rerank(query, candidates, scores)
        
        # L10: Cross-Encoder - 交叉编码器精排【新增，可选】
        if config.l10_enabled and self.cross_encoder:
            self._l10_cross_encoder(query, candidates, scores, config)
        
        # L11: LLM Filter - LLM 最终过滤【可选】
        if config.l11_enabled and self.llm_client:
            candidates, scores = await self._l11_llm_filter(query, candidates, scores, config)
        
        return self._build_results(candidates, scores, top_k)
```

---

##### 步骤 3: 实现新增层 + 迁移层 (~300 行)

**迁移层说明（L1, L3-L4, L6-L9, L11）：**

以下方法从现有 `EightLayerRetriever` 迁移，逻辑基本不变，仅调整参数签名以支持 `temporal_candidates` 过滤：

```python
# L1: 从 EightLayerRetriever._l1_bloom_filter() 迁移
def _l1_bloom_filter(self, keywords: List[str]) -> List[str]: ...

# L3: 从 EightLayerRetriever._l2_inverted_index() 迁移
# 新增 config 和 temporal_candidates 参数，内部使用 config.l3_inverted_top_k
def _l3_inverted_index(self, keywords, candidates, scores, config, temporal_candidates=None): ...

# L4: 从 EightLayerRetriever._l3_entity_index() 迁移
# 新增 config 参数，内部使用 config.l4_entity_top_k
def _l4_entity_index(self, entities, candidates, scores, config, temporal_candidates=None): ...

# L6: 从 EightLayerRetriever._l4_ngram_index() 迁移
# 新增 config 参数，内部使用 config.l6_ngram_top_k
def _l6_ngram_index(self, query, candidates, scores, config, temporal_candidates=None): ...

# L7: 从 EightLayerRetriever._l5_vector_coarse() 迁移
# 内部使用 config.l7_vector_top_k
def _l7_vector_coarse(self, query, candidates, scores, config): ...

# L8: 从 EightLayerRetriever._l6_vector_fine() 迁移
def _l8_vector_fine(self, query, candidates, scores, config): ...

# L9: 从 EightLayerRetriever._l7_rerank() 迁移
def _l9_rerank(self, query, candidates, scores): ...

# L11: 从 EightLayerRetriever._l8_llm_filter() 迁移，改为 async
# 注意：L11 完整实现已在下方单独给出，此处仅说明迁移来源
async def _l11_llm_filter(self, query, candidates, scores, config) -> Tuple[Set, Dict]: ...
```

> 💡 **迁移策略**：迁移时需在每个方法内部添加 `temporal_candidates` 过滤逻辑：
> ```python
> if temporal_candidates is not None:
>     result_ids = result_ids & temporal_candidates  # 交集过滤
> ```

**辅助方法 `_build_results`：**
```python
def _build_results(
    self,
    candidates: Set[str],
    scores: Dict[str, float],
    top_k: int
) -> List[RetrievalResult]:
    """构建最终检索结果"""
    # 按分数排序
    sorted_candidates = sorted(
        candidates,
        key=lambda x: scores[x],
        reverse=True
    )[:top_k]
    
    return [
        RetrievalResult(
            id=doc_id,
            score=scores[doc_id],
            content=self._get_content(doc_id)
        )
        for doc_id in sorted_candidates
    ]
```

**L2: Temporal Filter（时态过滤）：**
```python
def _l2_temporal_filter(
    self,
    temporal_context: TemporalContext,
    config: RetrievalConfig
) -> Optional[Set[str]]:
    """L2: 时态过滤 - 使用 TemporalIndex 预筛选时间范围内的文档"""
    
    if not temporal_context.has_time_constraint():
        return None  # 无时间约束，跳过此层
    
    start_time = time.perf_counter()
    
    # 使用 Phase 1 实现的 TemporalIndex.query_range()
    results = self.temporal_index.query_range(
        start=temporal_context.start,
        end=temporal_context.end,
        limit=config.l2_temporal_top_k
    )
    
    candidate_ids = {r.episode_id for r in results}
    
    # 记录统计
    self.stats.append(LayerStats(
        layer=RetrievalLayer.L2_TEMPORAL_FILTER.value,
        input_count=-1,  # 全量扫描
        output_count=len(candidate_ids),
        time_ms=(time.perf_counter() - start_time) * 1000
    ))
    
    return candidate_ids
```

**L5: Graph Traversal（图遍历扩展）：**
```python
def _l5_graph_traversal(
    self,
    entities: List[str],
    candidates: Set[str],
    scores: Dict[str, float],
    config: RetrievalConfig
) -> None:
    """L5: 图遍历扩展 - 使用 TemporalKnowledgeGraph.bfs() 发现关联文档"""
    
    start_time = time.perf_counter()
    input_count = len(candidates)
    graph_candidates = []  # 收集图遍历的新候选
    
    for start_entity in entities[:config.l5_graph_max_entities]:  # 使用配置限制起点数量
        # 查找实体在图中的节点 ID
        node_id = self.knowledge_graph.get_node_by_name(start_entity)
        if not node_id:
            continue
        
        # 使用 Phase 1 实现的 BFS
        bfs_results = self.knowledge_graph.bfs(
            start=node_id,
            max_depth=config.l5_graph_max_depth,
            time_filter=config.reference_time,
            direction=config.l5_graph_direction
        )
        
        # 按深度加权添加候选
        for depth, items in bfs_results.items():
            depth_weight = 1.0 / (depth + 1)  # 距离衰减
            for target_node_id, edge in items:
                # 获取边关联的 episode
                for episode_id in edge.source_episodes:
                    graph_candidates.append((episode_id, depth_weight * config.weights.graph))
    
    # 按分数排序并取 top_k
    graph_candidates.sort(key=lambda x: x[1], reverse=True)
    for episode_id, score in graph_candidates[:config.l5_graph_top_k]:
        candidates.add(episode_id)
        scores[episode_id] += score
    
    # 记录统计
    self.stats.append(LayerStats(
        layer=RetrievalLayer.L5_GRAPH_TRAVERSAL.value,
        input_count=input_count,
        output_count=len(candidates),
        time_ms=(time.perf_counter() - start_time) * 1000
    ))
```

**辅助方法 `_get_content`：**
```python
def _get_content(self, doc_id: str) -> str:
    """获取文档内容 - 委托给 content_store"""
    if self.content_store:
        return self.content_store(doc_id)
    return ""
```

**L10: Cross-Encoder（交叉编码器精排）：**
```python
def _l10_cross_encoder(
    self,
    query: str,
    candidates: Set[str],
    scores: Dict[str, float],
    config: RetrievalConfig
) -> None:
    """L10: CrossEncoder 重排序 - 使用交叉编码器计算精确相关性"""
    
    start_time = time.perf_counter()
    
    # 取 top candidates
    sorted_candidates = sorted(
        candidates,
        key=lambda x: scores[x],
        reverse=True
    )[:config.l10_cross_encoder_top_k]
    
    # 准备 query-document pairs
    pairs = [
        (query, self._get_content(doc_id))
        for doc_id in sorted_candidates
    ]
    
    # CrossEncoder 批量评分
    ce_scores = self.cross_encoder.predict(pairs)
    
    # 融合分数：30% 旧分 + 70% CrossEncoder 分
    for doc_id, ce_score in zip(sorted_candidates, ce_scores):
        scores[doc_id] = scores[doc_id] * 0.3 + float(ce_score) * 0.7
    
    # 记录统计
    self.stats.append(LayerStats(
        layer=RetrievalLayer.L10_CROSS_ENCODER.value,
        input_count=len(candidates),
        output_count=len(sorted_candidates),
        time_ms=(time.perf_counter() - start_time) * 1000
    ))
```

**L11: LLM Filter（LLM 语义过滤）：**
```python
async def _l11_llm_filter(
    self,
    query: str,
    candidates: Set[str],
    scores: Dict[str, float],
    config: RetrievalConfig
) -> Tuple[Set[str], Dict[str, float]]:
    """L11: LLM 重排序 - 使用 LLM 进行最终语义相关性判断"""
    
    start_time = time.perf_counter()
    
    # 取 top candidates
    sorted_candidates = sorted(
        candidates,
        key=lambda x: scores[x],
        reverse=True
    )[:config.l11_llm_top_k]
    
    # 构建评分 prompt
    docs_text = "\n\n".join([
        f"[Doc {i+1}] {self._get_content(doc_id)[:500]}"
        for i, doc_id in enumerate(sorted_candidates)
    ])
    
    prompt = f"""请根据查询的相关性对以下文档进行评分（0-10分）。

查询: {query}

文档列表:
{docs_text}

请以 JSON 格式返回评分：{{"scores": [8, 6, 9, ...]}}
只返回 JSON，不要其他内容。"""

    try:
        response = await asyncio.wait_for(
            self.llm_client.complete(prompt=prompt, max_tokens=200, temperature=0.0),
            timeout=config.l11_llm_timeout
        )
        
        result = json.loads(response)
        llm_scores = result.get("scores", [])
        
        # LLM 分数直接覆盖（最终裁判）
        for doc_id, llm_score in zip(sorted_candidates, llm_scores):
            scores[doc_id] = llm_score / 10.0
        
    except Exception as e:
        logger.warning(f"L11 LLM filter failed: {e}, keeping original scores")
    
    # 记录统计
    self.stats.append(LayerStats(
        layer=RetrievalLayer.L11_LLM_FILTER.value,
        input_count=len(candidates),
        output_count=len(sorted_candidates),
        time_ms=(time.perf_counter() - start_time) * 1000
    ))
    
    return set(sorted_candidates), scores
```

---

##### 步骤 4: Engine 集成 (~100 行)

**修改 `recall/engine.py`：**

```python
import os

# 导入新模块
from recall.retrieval.eleven_layer import ElevenLayerRetriever
from recall.retrieval.config import RetrievalConfig, LayerWeights

# 在 __init__ 中替换检索器初始化
self.retriever = ElevenLayerRetriever(
    # 现有依赖（对应旧 L1-L8，新编号后为 L1, L3-L4, L6-L9, L11）
    bloom_filter=self.bloom_filter,
    inverted_index=self.inverted_index,
    entity_index=self.entity_index,
    ngram_index=self.ngram_index,
    vector_index=self.vector_index,
    llm_client=self.llm_client,
    content_store=self._get_content,
    # 新增依赖（L2, L5, L10）
    temporal_index=self.temporal_index,      # Phase 1 模块
    knowledge_graph=self.knowledge_graph,    # Phase 1 模块
    cross_encoder=self._load_cross_encoder() if os.getenv('RETRIEVAL_L10_CROSS_ENCODER_ENABLED', 'false').lower() == 'true' else None,
    # 配置
    config=self._build_retrieval_config()  # 从环境变量构建
)

# 辅助方法：加载 CrossEncoder 模型
def _load_cross_encoder(self):
    """按需加载 CrossEncoder 模型"""
    from sentence_transformers import CrossEncoder
    model_name = os.getenv(
        'RETRIEVAL_L10_CROSS_ENCODER_MODEL',
        'cross-encoder/ms-marco-MiniLM-L-6-v2'
    )
    return CrossEncoder(model_name)

# 辅助方法：从环境变量构建检索配置
def _build_retrieval_config(self) -> RetrievalConfig:
    """从环境变量构建 RetrievalConfig"""
    def get_bool(key: str, default: bool) -> bool:
        return os.getenv(key, str(default)).lower() == 'true'
    
    def get_int(key: str, default: int) -> int:
        return int(os.getenv(key, str(default)))
    
    def get_float(key: str, default: float) -> float:
        return float(os.getenv(key, str(default)))
    
    return RetrievalConfig(
        l1_enabled=get_bool('RETRIEVAL_L1_BLOOM_ENABLED', True),
        l2_enabled=get_bool('RETRIEVAL_L2_TEMPORAL_ENABLED', True),
        l3_enabled=get_bool('RETRIEVAL_L3_INVERTED_ENABLED', True),
        l4_enabled=get_bool('RETRIEVAL_L4_ENTITY_ENABLED', True),
        l5_enabled=get_bool('RETRIEVAL_L5_GRAPH_ENABLED', True),
        l6_enabled=get_bool('RETRIEVAL_L6_NGRAM_ENABLED', True),
        l7_enabled=get_bool('RETRIEVAL_L7_VECTOR_COARSE_ENABLED', True),
        l8_enabled=get_bool('RETRIEVAL_L8_VECTOR_FINE_ENABLED', True),
        l9_enabled=get_bool('RETRIEVAL_L9_RERANK_ENABLED', True),
        l10_enabled=get_bool('RETRIEVAL_L10_CROSS_ENCODER_ENABLED', False),
        l11_enabled=get_bool('RETRIEVAL_L11_LLM_ENABLED', False),
        # Top-K 配置（全部 8 项）
        l2_temporal_top_k=get_int('RETRIEVAL_L2_TEMPORAL_TOP_K', 500),
        l3_inverted_top_k=get_int('RETRIEVAL_L3_INVERTED_TOP_K', 100),
        l4_entity_top_k=get_int('RETRIEVAL_L4_ENTITY_TOP_K', 50),
        l5_graph_top_k=get_int('RETRIEVAL_L5_GRAPH_TOP_K', 100),
        l6_ngram_top_k=get_int('RETRIEVAL_L6_NGRAM_TOP_K', 30),
        l7_vector_top_k=get_int('RETRIEVAL_L7_VECTOR_TOP_K', 200),
        l10_cross_encoder_top_k=get_int('RETRIEVAL_L10_CROSS_ENCODER_TOP_K', 50),
        l11_llm_top_k=get_int('RETRIEVAL_L11_LLM_TOP_K', 20),
        # 阈值配置
        fine_rank_threshold=get_int('RETRIEVAL_FINE_RANK_THRESHOLD', 100),
        final_top_k=get_int('RETRIEVAL_FINAL_TOP_K', 20),
        # L5 图遍历配置
        l5_graph_max_depth=get_int('RETRIEVAL_L5_GRAPH_MAX_DEPTH', 2),
        l5_graph_max_entities=get_int('RETRIEVAL_L5_GRAPH_MAX_ENTITIES', 3),
        l5_graph_direction=os.getenv('RETRIEVAL_L5_GRAPH_DIRECTION', 'both'),
        # L11 LLM 配置
        l11_llm_timeout=get_float('RETRIEVAL_L11_LLM_TIMEOUT', 10.0),
        # 权重配置
        weights=LayerWeights(
            inverted=get_float('RETRIEVAL_WEIGHT_INVERTED', 1.0),
            entity=get_float('RETRIEVAL_WEIGHT_ENTITY', 1.2),
            graph=get_float('RETRIEVAL_WEIGHT_GRAPH', 1.0),
            ngram=get_float('RETRIEVAL_WEIGHT_NGRAM', 0.8),
            vector=get_float('RETRIEVAL_WEIGHT_VECTOR', 1.0),
            temporal=get_float('RETRIEVAL_WEIGHT_TEMPORAL', 0.5),
        ),
    )
```

---

##### 步骤 5: 向后兼容适配器（可选）

**如果需要保持旧 API 兼容：**
```python
import asyncio

class EightLayerRetrieverCompat:
    """向后兼容适配器 - 将旧 8 层同步 API 映射到新 11 层异步"""
    
    def __init__(self, eleven_layer: ElevenLayerRetriever):
        self._impl = eleven_layer
    
    def retrieve(self, query, entities=None, keywords=None, top_k=20, filters=None):
        """旧 API 兼容（同步包装）"""
        # 创建兼容配置（禁用新增层）
        config = RetrievalConfig(
            l2_enabled=False,   # 禁用 Temporal
            l5_enabled=False,   # 禁用 Graph
            l10_enabled=False,  # 禁用 CrossEncoder
            l11_enabled=False,  # 禁用 LLM（异步方法）
        )
        # 同步包装异步调用（兼容 Python 3.7+）
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，创建新的
            return asyncio.run(
                self._impl.retrieve(
                    query=query, entities=entities, keywords=keywords,
                    top_k=top_k, filters=filters, temporal_context=None, config=config
                )
            )
        else:
            # 已有事件循环，使用 run_until_complete
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(
                self._impl.retrieve(
                    query=query, entities=entities, keywords=keywords,
                    top_k=top_k, filters=filters, temporal_context=None, config=config
                )
            )
```

---

#### ⚙️ 配置项扩展

**需要添加到 `api_keys.env`：**

```env
# ============================================================================
# 十一层检索器配置 (Phase 3)
# Eleven-Layer Retriever Configuration
# ============================================================================

# ----------------------------------------------------------------------------
# 层开关配置 (Layer Enable/Disable)
# ----------------------------------------------------------------------------
# L1: Bloom Filter (默认启用)
RETRIEVAL_L1_BLOOM_ENABLED=true

# L2: Temporal Filter - 时态过滤【新增】
RETRIEVAL_L2_TEMPORAL_ENABLED=true

# L3: Inverted Index (默认启用)
RETRIEVAL_L3_INVERTED_ENABLED=true

# L4: Entity Index (默认启用)
RETRIEVAL_L4_ENTITY_ENABLED=true

# L5: Graph Traversal - 图遍历【新增】
RETRIEVAL_L5_GRAPH_ENABLED=true

# L6: N-gram Index (默认启用)
RETRIEVAL_L6_NGRAM_ENABLED=true

# L7: Vector Coarse (默认启用)
RETRIEVAL_L7_VECTOR_COARSE_ENABLED=true

# L8: Vector Fine (默认启用)
RETRIEVAL_L8_VECTOR_FINE_ENABLED=true

# L9: Rerank (默认启用)
RETRIEVAL_L9_RERANK_ENABLED=true

# L10: CrossEncoder - 交叉编码器【新增，默认关闭】
RETRIEVAL_L10_CROSS_ENCODER_ENABLED=false

# L11: LLM Filter (默认关闭，高成本)
RETRIEVAL_L11_LLM_ENABLED=false

# ----------------------------------------------------------------------------
# Top-K 配置 (各层候选数限制)
# ----------------------------------------------------------------------------
# L2: 时态过滤保留数
RETRIEVAL_L2_TEMPORAL_TOP_K=500

# L3: 倒排索引保留数
RETRIEVAL_L3_INVERTED_TOP_K=100

# L4: 实体索引保留数
RETRIEVAL_L4_ENTITY_TOP_K=50

# L5: 图遍历保留数
RETRIEVAL_L5_GRAPH_TOP_K=100

# L6: N-gram 保留数
RETRIEVAL_L6_NGRAM_TOP_K=30

# L7: 向量粗筛保留数
RETRIEVAL_L7_VECTOR_TOP_K=200

# ----------------------------------------------------------------------------
# 阈值与最终输出配置
# ----------------------------------------------------------------------------
# 触发 L8 向量精排的候选数阈值
RETRIEVAL_FINE_RANK_THRESHOLD=100

# 最终返回结果数
RETRIEVAL_FINAL_TOP_K=20

# ----------------------------------------------------------------------------
# L5 图遍历配置
# ----------------------------------------------------------------------------
# BFS 最大深度 (1-5)
RETRIEVAL_L5_GRAPH_MAX_DEPTH=2

# 每次图遍历的最大起始实体数 (1-10)
RETRIEVAL_L5_GRAPH_MAX_ENTITIES=3

# 遍历方向: out(出边) | in(入边) | both(双向)
RETRIEVAL_L5_GRAPH_DIRECTION=both

# ----------------------------------------------------------------------------
# L10 CrossEncoder 配置
# ----------------------------------------------------------------------------
# CrossEncoder 模型名称
RETRIEVAL_L10_CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# CrossEncoder 处理的最大候选数
RETRIEVAL_L10_CROSS_ENCODER_TOP_K=50

# ----------------------------------------------------------------------------
# L11 LLM 配置
# ----------------------------------------------------------------------------
# LLM 处理的最大文档数
RETRIEVAL_L11_LLM_TOP_K=20

# LLM 超时时间（秒）
RETRIEVAL_L11_LLM_TIMEOUT=10.0

# ----------------------------------------------------------------------------
# 权重配置 (可选，高级调优)
# ----------------------------------------------------------------------------
# 倒排索引命中权重
RETRIEVAL_WEIGHT_INVERTED=1.0

# 实体索引命中权重
RETRIEVAL_WEIGHT_ENTITY=1.2

# 图遍历命中权重
RETRIEVAL_WEIGHT_GRAPH=1.0

# N-gram 命中权重
RETRIEVAL_WEIGHT_NGRAM=0.8

# 向量相似度权重
RETRIEVAL_WEIGHT_VECTOR=1.0

# 时态相关性权重
RETRIEVAL_WEIGHT_TEMPORAL=0.5
```

---

#### 🔗 依赖关系

**Phase 1 模块依赖（已完成）：**
- `TemporalIndex.query_range()` → L2 时态过滤
- `TemporalKnowledgeGraph.bfs()` → L5 图遍历

**可选外部依赖：**
- `sentence-transformers` (CrossEncoder) → L10
- `nest_asyncio` → 向后兼容适配器（仅在已有事件循环时需要）

---

**预计产出文件：**
```
recall/retrieval/config.py             # ~150 行 - 检索配置类 + 辅助类
recall/retrieval/eleven_layer.py       # ~700 行 - 十一层检索器
recall/retrieval/__init__.py           # 更新 - 模块导出
recall/engine.py                       # 更新 - 集成新检索器
start.ps1                              # 更新 - Phase 3 配置项
start.sh                               # 更新 - Phase 3 配置项
tests/test_eleven_layer.py             # ~250 行 - 检索器测试
tests/test_retrieval_benchmark.py      # ~150 行 - 性能基准测试
```

**📊 代码统计预估：**
| 类别 | 文件数 | 总行数 |
|------|--------|--------|
| 核心模块 | 2 | ~950 行 |
| 更新文件 | 4 | ~250 行修改 |
| 测试文件 | 2 | ~400 行 |
| **合计** | **8** | **~1,600 行** |

---

**🔑 关键 API 摘要：**

| 模块 | 核心类/方法 | 功能 |
|------|-------------|------|
| `config.py` | `RetrievalConfig` | 类型安全的 11 层检索配置 |
| `config.py` | `RetrievalConfig.default()` | 默认配置（L10/L11 关闭） |
| `config.py` | `RetrievalConfig.fast()` | 快速模式（跳过精排层） |
| `config.py` | `RetrievalConfig.accurate()` | 精准模式（启用所有层） |
| `config.py` | `LayerWeights` | 各层权重配置 |
| `eleven_layer.py` | `ElevenLayerRetriever` | 十一层漏斗检索器 |
| `eleven_layer.py` | `ElevenLayerRetriever.retrieve()` | 主检索方法 |
| `eleven_layer.py` | `_l2_temporal_filter()` | L2 时态过滤 |
| `eleven_layer.py` | `_l5_graph_traversal()` | L5 图遍历扩展 |
| `eleven_layer.py` | `_l10_cross_encoder()` | L10 交叉编码器精排 |
| `eleven_layer.py` | `_l11_llm_filter()` | L11 LLM 语义过滤 |
| `eleven_layer.py` | `RetrievalLayer` | 11 层枚举定义 |

---

**📡 REST API 更新：**

| 端点 | 方法 | 功能 | 说明 |
|------|------|------|------|
| `/v1/search` | POST | 增强搜索 | 新增 `temporal_filter` 和 `graph_expand` 参数 |
| `/v1/search/config` | GET | 获取检索配置 | 返回当前 `RetrievalConfig` |
| `/v1/search/config` | PUT | 更新检索配置 | 动态调整检索策略 |

**搜索 API 参数扩展：**
```json
{
  "query": "Alice 的工作经历",
  "top_k": 20,
  "temporal_filter": {
    "start": "2024-01-01",
    "end": "2024-12-31"
  },
  "graph_expand": {
    "center_entities": ["Alice"],
    "max_depth": 2,
    "direction": "both"
  },
  "config_preset": "accurate"  // default | fast | accurate
}
```

---

**🌐 通用性说明：**

Phase 3 所有代码都是 **100% 平台无关** 的通用实现：
- ✅ 纯 Python 实现，无特定前端依赖
- ✅ 通过 REST API 暴露，任何客户端可调用
- ✅ 配置通过环境变量控制，易于 Docker/K8s 部署
- ✅ CrossEncoder 为可选依赖，不影响基础功能

---

**验收标准：**
- [ ] 检索延迟 < 100ms (p95，不含 LLM 层)
- [ ] 召回率提升 ≥10%（对比 EightLayerRetriever）
- [ ] 所有现有测试通过（向后兼容）
- [ ] L2 时态过滤可正常工作
- [ ] L5 图遍历可正常工作
- [ ] L10 CrossEncoder 可选启用
- [ ] L11 LLM Filter 可选启用
- [ ] Engine 集成完成，旧 `EightLayerRetriever` 平滑替换
- [ ] 向后兼容适配器可用
- [ ] 配置项已添加到 `api_keys.env`
- [ ] `start.ps1` / `start.sh` 支持 Phase 3 配置项
- [ ] REST API `/v1/search` 支持新参数
- [ ] 基准测试脚本可运行

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
| **检索层数** | 3层 | 11层 | 🏆 Recall |
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
