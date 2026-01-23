基于对 `getzep/graphiti` 项目的全面分析，我为你整理了一份详细的技术文档，这份文档以 AI 可理解的方式描述了项目的所有核心技术细节，便于你后续开发超越该项目的系统。

---

# Graphiti 项目全方位技术分析文档

## ? 项目概述

| 属性 | 值 |
|------|-----|
| **项目名称** | graphiti-core |
| **版本** | 0.26.3 |
| **语言** | Python (>=3.10) |
| **许可证** | Apache 2.0 |
| **Stars** | 22,227 |
| **核心定位** | AI Agent 的时序知识图谱框架 |

**核心价值定位**：为 AI Agent 构建实时、动态、可查询的时序知识图谱，支持增量更新、历史追踪和混合检索。

---

## ?? 系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Graphiti 系统架构                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐               │
│  │  MCP Server   │    │ FastAPI Server│    │  Python SDK   │               │
│  │  (AI助手集成)  │    │  (REST API)   │    │  (直接调用)    │               │
│  └───────┬───────┘    └───────┬───────┘    └───────┬───────┘               │
│          │                    │                    │                        │
│          └────────────────────┼────────────────────┘                        │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         graphiti_core                                │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │                    Graphiti 主类 (graphiti.py)               │    │   │
│  │  │  ? add_episode() - 添加知识片段                              │    │   │
│  │  │  ? search() / _search() - 混合检索                           │    │   │
│  │  │  ? add_episode_bulk() - 批量添加                             │    │   │
│  │  │  ? retrieve_episodes() - 检索历史                            │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                               │                                      │   │
│  │  ┌───────────┬───────────┬────┴────┬────────────┬──────────────┐    │   │
│  │  ▼           ▼           ▼         ▼            ▼              ▼    │   │
│  │ ┌─────┐  ┌───────┐  ┌─────────┐ ┌───────┐  ┌─────────┐  ┌───────┐  │   │
│  │ │Nodes│  │ Edges │  │ Search  │ │Prompts│  │ Driver  │  │Embedder│  │   │
│  │ │节点  │  │ 边    │  │ 检索    │ │ 提示词 │  │ 驱动器  │  │嵌入器  │  │   │
│  │ └─────┘  └───────┘  └─────────┘ └───────┘  └─────────┘  └───────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                               │                                             │
│          ┌────────────────────┼────────────────────┐                        │
│          ▼                    ▼                    ▼                        │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐               │
│  │    Neo4j      │    │   FalkorDB    │    │ Amazon Neptune│               │
│  │  (默认图数据库) │    │ (Redis-based) │    │   (AWS云服务)  │               │
│  └───────────────┘    └───────────────┘    └───────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ? 核心模块详解

### 1. 数据模型层 (`nodes.py`, `edges.py`)

#### 1.1 节点类型 (Nodes)

```python
# 基础节点抽象类
class Node(BaseModel, ABC):
    uuid: str           # 唯一标识
    name: str           # 节点名称
    group_id: str       # 分组ID（用于多租户隔离）
    labels: list[str]   # 标签列表
    created_at: datetime # 创建时间

# 实体节点 - 知识图谱的核心节点
class EntityNode(Node):
    name_embedding: list[float] | None  # 名称的向量嵌入
    summary: str                         # 节点摘要
    attributes: dict[str, Any]           # 动态属性（支持自定义实体类型）

# 情节节点 - 原始数据输入单元
class EpisodicNode(Node):
    source: EpisodeType          # 来源类型: text | message | json
    source_description: str      # 来源描述
    content: str                 # 原始内容
    valid_at: datetime           # 原始文档创建时间
    entity_edges: list[str]      # 关联的实体边UUID列表

# 社区节点 - 用于图聚类
class CommunityNode(Node):
    name_embedding: list[float] | None
    summary: str

# Saga节点 - 用于组织相关情节序列
class SagaNode(Node):
    name_embedding: list[float] | None
```

#### 1.2 边类型 (Edges)

```python
# 基础边抽象类
class Edge(BaseModel, ABC):
    uuid: str
    source_node_uuid: str
    target_node_uuid: str
    group_id: str
    created_at: datetime

# 实体边 - 表示实体间的事实关系 ?核心
class EntityEdge(Edge):
    name: str                    # 关系名称 (如 WORKS_AT, LIKES)
    fact: str                    # 自然语言描述的事实
    fact_embedding: list[float]  # 事实的向量嵌入
    episodes: list[str]          # 引用此边的情节列表
    
    # ? 双时态系统 (Bi-temporal)
    expired_at: datetime | None  # 数据库层面：节点失效时间
    valid_at: datetime | None    # 现实层面：事实生效时间
    invalid_at: datetime | None  # 现实层面：事实失效时间
    
    attributes: dict[str, Any]   # 动态属性

# 情节边 - 连接情节节点和实体节点
class EpisodicEdge(Edge):
    pass

# 社区边、Saga边等...
```

**关键技术点**：
- **双时态模型 (Bi-temporal)**：`valid_at/invalid_at` 跟踪现实世界中事实的有效期，`expired_at` 跟踪数据库中记录的生命周期
- **向量嵌入**：每个节点和边都可生成向量用于语义搜索
- **动态属性**：通过 `attributes` 字典支持自定义字段

---

### 2. LLM 集成层 (`llm_client/`)

#### 2.1 支持的 LLM 提供商

| 提供商 | 客户端类 | 配置说明 |
|--------|----------|----------|
| OpenAI | `OpenAIClient` | 默认提供商，支持 GPT-4/4.1 |
| Anthropic | `AnthropicClient` | Claude 系列 |
| Google | `GeminiClient` | Gemini 系列 |
| Groq | `GroqClient` | 高速推理 |
| Azure OpenAI | `AzureOpenAILLMClient` | 企业级部署 |
| Ollama (本地) | `OpenAIGenericClient` | 本地模型如 DeepSeek |

#### 2.2 LLM 配置结构

```python
class LLMConfig:
    api_key: str | None
    model: str | None          # 主模型 (复杂任务)
    small_model: str | None    # 小模型 (简单任务)
    base_url: str | None       # API端点
    temperature: float = 0.1   # 默认低温度保证一致性
    max_tokens: int = 8192
```

#### 2.3 核心 LLM 抽象接口

```python
class LLMClient(ABC):
    @abstractmethod
    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None,  # Pydantic模型用于结构化输出
        max_tokens: int,
        model_size: ModelSize,  # small | medium
    ) -> dict[str, Any]
```

---

### 3. 嵌入层 (`embedder/`)

#### 3.1 支持的嵌入提供商

| 提供商 | 类名 | 默认维度 | 特点 |
|--------|------|----------|------|
| OpenAI | `OpenAIEmbedder` | 1536/3072 | text-embedding-3-small/large |
| Azure OpenAI | `AzureOpenAIEmbedderClient` | 1536 | 企业级 |
| Google Gemini | `GeminiEmbedder` | 可配置 | 支持维度裁剪 |
| Voyage AI | `VoyageEmbedder` | 1024 | 高质量嵌入 |
| Sentence Transformers | `SentenceTransformerEmbedder` | 模型依赖 | 本地运行 |

#### 3.2 嵌入器接口

```python
class EmbedderClient(ABC):
    @abstractmethod
    async def create(
        self, input_data: str | list[str] | Iterable[int]
    ) -> list[float]:
        """生成文本的向量嵌入"""
```

---

### 4. 图数据库驱动层 (`driver/`)

#### 4.1 支持的数据库

| 数据库 | 驱动类 | 特点 | 适用场景 |
|--------|--------|------|----------|
| Neo4j | `Neo4jDriver` | 默认，成熟稳定 | 生产环境 |
| FalkorDB | `FalkorDriver` | Redis协议，轻量 | 边缘部署、MCP Server |
| Amazon Neptune | `NeptuneDriver` | AWS托管 | 云原生 |
| Kuzu | `KuzuDriver` | 嵌入式 | 本地测试 |

#### 4.2 驱动抽象接口

```python
class GraphDriver(ABC):
    provider: GraphProvider
    
    @abstractmethod
    async def execute_query(
        self, query: str, routing_: str = 'w', **parameters
    ) -> tuple[list[Record], Any, Any]
    
    @abstractmethod
    def session(self) -> GraphDriverSession
    
    # 搜索接口
    search_interface: SearchInterface | None
    
    # 图操作接口
    graph_operations_interface: GraphOperationsInterface | None
```

---

### 5. 提示工程层 (`prompts/`)

这是 Graphiti 的核心竞争力之一，包含精心设计的 LLM 提示词。

#### 5.1 提示词库结构

```python
class PromptLibrary(Protocol):
    extract_nodes: ExtractNodesPrompt      # 实体抽取
    dedupe_nodes: DedupeNodesPrompt        # 节点去重
    extract_edges: ExtractEdgesPrompt      # 关系/事实抽取
    dedupe_edges: DedupeEdgesPrompt        # 边去重
    invalidate_edges: InvalidateEdgesPrompt # 边失效检测
    extract_edge_dates: ExtractEdgeDatesPrompt # 时间信息抽取
    summarize_nodes: SummarizeNodesPrompt  # 节点摘要生成
    eval: EvalPrompt                       # 评估
```

#### 5.2 核心提示词详解

**实体抽取提示 (extract_nodes.py)**

```python
# 针对不同输入类型有不同的提示：
# - extract_message: 对话消息 → 提取说话者和提及的实体
# - extract_text: 纯文本 → 提取显式/隐式提及的实体
# - extract_json: JSON数据 → 从结构化数据抽取实体

# 输出结构
class ExtractedEntity(BaseModel):
    name: str              # 实体名称
    entity_type_id: int    # 实体类型ID（映射到自定义类型）
```

**关系/事实抽取提示 (extract_edges.py)**

```python
# 输出结构
class Edge(BaseModel):
    relation_type: str     # 关系类型 (SCREAMING_SNAKE_CASE)
    source_entity_id: int  # 源实体ID
    target_entity_id: int  # 目标实体ID
    fact: str              # 自然语言事实描述
    valid_at: str | None   # 事实生效时间 (ISO 8601)
    invalid_at: str | None # 事实失效时间 (ISO 8601)
```

**节点去重提示 (dedupe_nodes.py)**

```python
# 系统消息：判断新实体是否是现有实体的重复
# 输入：新实体 + 候选现有实体列表 + 上下文消息
# 输出：是否重复 + 如果重复则返回现有实体的UUID
```

---

### 6. 搜索与检索层 (`search/`)

这是 Graphiti 的另一核心优势 - 多策略混合检索系统。

#### 6.1 搜索配置体系

```python
# 搜索配置结构
class SearchConfig(BaseModel):
    edge_config: EdgeSearchConfig | None
    node_config: NodeSearchConfig | None
    episode_config: EpisodeSearchConfig | None
    community_config: CommunitySearchConfig | None
    limit: int = 10

# 节点搜索配置
class NodeSearchConfig(BaseModel):
    search_methods: list[NodeSearchMethod]  # 搜索方法组合
    reranker: NodeReranker                  # 重排序器
```

#### 6.2 搜索方法 (Search Methods)

| 类别 | 方法 | 说明 |
|------|------|------|
| **BM25** | `bm25` | 关键词全文搜索 |
| **向量搜索** | `cosine_similarity` | 基于嵌入的语义搜索 |
| **图遍历** | `bfs` | 广度优先遍历 |

#### 6.3 重排序器 (Rerankers)

| 重排序器 | 说明 |
|----------|------|
| `rrf` | Reciprocal Rank Fusion - 融合多个检索结果 |
| `mmr` | Maximal Marginal Relevance - 多样性优化 |
| `cross_encoder` | 交叉编码器重排序 - 高质量但慢 |
| `node_distance` | 基于图距离的重排序 |
| `episode_mentions` | 基于情节提及次数的重排序 |

#### 6.4 预定义搜索配方 (Search Recipes)

```python
# 组合搜索配方示例
COMBINED_HYBRID_SEARCH_RRF = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.bm25, EdgeSearchMethod.cosine_similarity],
        reranker=EdgeReranker.rrf,
    ),
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.bm25, NodeSearchMethod.cosine_similarity],
        reranker=NodeReranker.rrf,
    ),
    community_config=CommunitySearchConfig(
        search_methods=[CommunitySearchMethod.bm25, CommunitySearchMethod.cosine_similarity],
        reranker=CommunityReranker.rrf,
    ),
)

# 节点专用搜索
NODE_HYBRID_SEARCH_RRF = SearchConfig(...)
NODE_HYBRID_SEARCH_CROSS_ENCODER = SearchConfig(...)

# 社区搜索
COMMUNITY_HYBRID_SEARCH_RRF = SearchConfig(...)
```

#### 6.5 混合搜索核心实现

```python
async def hybrid_node_search(
    queries: list[str],
    embeddings: list[list[float]],
    driver: GraphDriver,
    search_filter: SearchFilters,
    group_ids: list[str] | None = None,
    limit: int = RELEVANT_SCHEMA_LIMIT,
) -> list[EntityNode]:
    """
    执行流程：
    1. 并行执行全文搜索 (每个query)
    2. 并行执行向量搜索 (每个embedding)
    3. 合并结果并去重
    4. 使用RRF融合排序
    5. 返回top-k结果
    """
    results = await semaphore_gather(
        *[node_fulltext_search(driver, q, ...) for q in queries],
        *[node_similarity_search(driver, e, ...) for e in embeddings],
    )
    ranked_uuids, _ = rrf(result_uuids)  # Reciprocal Rank Fusion
    return [node_uuid_map[uuid] for uuid in ranked_uuids[:limit]]
```

---

### 7. 实体去重系统 (`utils/maintenance/`)

Graphiti 的去重系统采用**两阶段策略**：

#### 7.1 第一阶段：确定性匹配

```python
def _resolve_with_similarity(
    extracted_nodes: list[EntityNode],
    indexes: DedupCandidateIndexes,
    state: DedupResolutionState,
) -> None:
    """
    使用以下启发式规则：
    1. 精确名称匹配（标准化后）
    2. MinHash + LSH 近似匹配（Jaccard相似度）
    """
    # 精确匹配
    normalized = _normalize_string_exact(node.name)
    exact_match = ...
    
    # 模糊匹配 (MinHash + LSH)
    signature = _minhash_signature(shingles)
    for band in _lsh_bands(signature):
        candidate_ids.update(indexes.lsh_buckets.get((band_index, band), []))
    
    # 计算Jaccard相似度
    score = _jaccard_similarity(shingles, candidate_shingles)
    if score >= _FUZZY_JACCARD_THRESHOLD:
        # 匹配成功
```

#### 7.2 第二阶段：LLM 判断

对于第一阶段无法确定的实体，使用 LLM 进行最终判断：

```python
async def _resolve_with_llm(
    llm_client: LLMClient,
    extracted_nodes: list[EntityNode],
    indexes: DedupCandidateIndexes,
    state: DedupResolutionState,
    episode: EpisodicNode,
    previous_episodes: list[EpisodicNode],
    entity_types: dict[str, type[BaseModel]],
) -> None:
    """
    LLM提示包含：
    - 当前消息
    - 前序消息
    - 新抽取的实体
    - 候选现有实体列表
    - 实体类型描述
    """
```

#### 7.3 去重数据结构

```python
@dataclass
class DedupCandidateIndexes:
    """预计算的查找结构"""
    existing_nodes: list[EntityNode]
    nodes_by_uuid: dict[str, EntityNode]
    normalized_existing: defaultdict[str, list[EntityNode]]  # 名称→节点
    shingles_by_candidate: dict[str, set[str]]              # MinHash shingles
    lsh_buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]]  # LSH桶

@dataclass
class DedupResolutionState:
    """去重状态"""
    resolved_nodes: list[EntityNode | None]
    uuid_map: dict[str, str]  # 旧UUID → 新UUID映射
    unresolved_indices: list[int]
    duplicate_pairs: list[tuple[EntityNode, EntityNode]]
```

---

### 8. MCP Server 集成

MCP (Model Context Protocol) 服务器使 Graphiti 可以与 Claude、Cursor 等 AI 助手集成。

#### 8.1 MCP 工具列表

| 工具名 | 功能 |
|--------|------|
| `add_memory` | 添加知识到图谱 |
| `search_memory_facts` | 搜索事实关系 |
| `search_memory_nodes` | 搜索实体节点 |
| `get_entity_edge` | 获取特定边 |
| `get_episodes` | 获取情节列表 |
| `delete_episode` | 删除情节 |
| `delete_entity_edge` | 删除边 |
| `clear_graph` | 清空图谱 |

#### 8.2 MCP 配置结构

```yaml
# config.yaml
server:
  transport: http  # http | stdio
  port: 8000
  
llm:
  provider: openai
  model: gpt-4.1-mini
  temperature: 0.0
  
embedder:
  provider: openai
  model: text-embedding-3-small
  dimensions: 1536
  
database:
  provider: falkordb
  providers:
    falkordb:
      uri: redis://localhost:6379

graphiti:
  group_id: main
  entity_types: []
```

---

## ? 核心工作流程

### Episode 添加流程

```
                     add_episode(content, type)
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   1. 创建 EpisodicNode               │
           │   - 设置 source, content, valid_at   │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   2. 检索前序 Episodes (上下文)       │
           │   - retrieve_episodes()              │
           └─────────??────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   3. 实体抽取 (LLM)                  │
           │   - extract_nodes()                  │
           │   - 根据 source 类型选择提示词        │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   4. 实体去重                        │
           │   - resolve_extracted_nodes()        │
           │   - 确定性匹配 + LLM判断             │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   5. 关系/事实抽取 (LLM)             │
           │   - extract_edges()                  │
           │   - 提取实体间的事实关系             │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   6. 边去重 & 时序处理               │
           │   - resolve_extracted_edges()        │
           │   - 处理矛盾信息，更新时态字段       │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   7. 批量持久化                      │
           │   - add_nodes_and_edges_bulk()       │
           │   - 生成嵌入，保存到图数据库         │
           └──────────────────────────────────────┘
```

### 搜索流程

```
                       search(query)
                            │
                            ▼
           ┌────────────────────────────────────┐
           │   1. 生成查询嵌入                   │
           │   - embedder.create(query)         │
           └────────────────────────────────────┘
                            │
                            ▼
           ┌────────────────────────────────────┐
           │   2. 并行执行多种搜索               │
           │   ├─ BM25 全文搜索                 │
           │   └─ 向量相似度搜索                │
           └────────────────────────────────────┘
                            │
                            ▼
           ┌────────────────────────────────────┐
           │   3. 结果融合 (RRF/MMR)             │
           │   - 合并去重                       │
           │   - 重排序                         │
           └────────────────────────────────────┘
                            │
                            ▼
           ┌────────────────────────────────────┐
           │   4. 可选：中心节点重排序           │
           │   - 基于图距离调整排名              │
           └────────────────────────────────────┘
                            │
                            ▼
                     返回 top-k 结果
```

---

## ? 关键依赖库

```toml
# 核心依赖
pydantic>=2.11.5           # 数据验证和序列化
neo4j>=5.26.0              # 默认图数据库驱动
openai>=1.91.0             # 默认LLM/嵌入
tenacity>=9.0.0            # 重试机制
numpy>=1.0.0               # 数值计算
diskcache>=5.6.3           # 本地缓存

# 可选依赖
anthropic>=0.49.0          # Claude
groq>=0.2.0                # Groq
google-genai>=1.8.0        # Gemini
falkordb>=1.1.2            # FalkorDB
voyageai>=0.2.3            # Voyage嵌入
sentence-transformers>=3.2.1  # 本地嵌入

# MCP Server
mcp>=1.9.4                 # Model Context Protocol
fastapi>=0.115.0           # REST API
uvicorn>=0.30.6            # ASGI服务器
```

---

## ? 技术优势与潜在超越点

### Graphiti 的优势

1. **双时态数据模型** - 同时追踪数据库时间和现实世界时间
2. **混合检索系统** - BM25 + 向量 + 图遍历的组合
3. **增量更新** - 无需重建整个图
4. **自定义实体类型** - 灵活的 schema
5. **多 LLM/数据库支持** - 可插拔架构
6. **MCP 集成** - 与 AI 助手无缝协作

### 潜在超越方向

| 方向 | 当前状态 | 改进机会 |
|------|----------|----------|
| **推理能力** | 基于检索，无推理 | 添加因果推理、多跳推理 |
| **实时流处理** | 批处理为主 | 真正的流式知识更新 |
| **知识压缩** | 无明确机制 | 自动知识合并和压缩 |
| **分布式架构** | 单节点为主 | 分布式图处理 |
| **向量索引** | 依赖数据库 | 专用 ANN 索引 (HNSW, IVF) |
| **知识验证** | 基本的 LLM 判断 | 事实核查、置信度评分 |
| **多模态** | 纯文本 | 支持图像、音频的知识抽取 |
| **本体管理** | 松散的类型系统 | 完整的本体定义和推理 |

---

## ? 代码结构参考

```
graphiti/
├── graphiti_core/           # 核心库
│   ├── graphiti.py          # 主入口类
│   ├── nodes.py             # 节点数据模型
│   ├── edges.py             # 边数据模型
│   ├── driver/              # 数据库驱动
│   │   ├── driver.py        # 抽象接口
│   │   ├── neo4j_driver.py
│   │   ├── falkordb_driver.py
│   │   └── neptune_driver.py
│   ├── llm_client/          # LLM客户端
│   │   ├── client.py        # 抽象接口
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   └── gemini_client.py
│   ├── embedder/            # 嵌入器
│   │   ├── client.py        # 抽象接口
│   │   ├── openai.py
│   │   └── gemini.py
│   ├── search/              # 搜索系统
│   │   ├── search_config.py
│   │   ├── search_config_recipes.py
│   │   └── search_utils.py
│   ├── prompts/             # LLM提示词
│   │   ├── extract_nodes.py
│   │   ├── extract_edges.py
│   │   ├── dedupe_nodes.py
│   │   └── dedupe_edges.py
│   └── utils/               # 工具函数
│       ├── bulk_utils.py    # 批量操作
│       └── maintenance/     # 维护操作
├── server/                  # FastAPI服务
│   └── graph_service/
│       ├── main.py
│       └── routers/
├── mcp_server/              # MCP服务
│   └── src/
│       └── graphiti_mcp_server.py
└── examples/                # 示例代码
```

---

此文档全面涵盖了 Graphiti 的技术实现细节。如需进一步了解特定模块的实现，可以访问 [GitHub 仓库](https://github.com/getzep/graphiti) 查看完整代码（搜索结果可能不完整，建议直接浏览仓库获取完整信息）。