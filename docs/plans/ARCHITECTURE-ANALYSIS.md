# Recall-AI 核心架构与实现细节分析报告

> 生成时间: 2026年1月28日  
> 分析版本: Recall 4.0

---

## 目录

1. [系统概览](#1-系统概览)
2. [核心引擎 Engine](#2-核心引擎-engine)
3. [处理器模块 Processor](#3-处理器模块-processor)
4. [图谱模块 Graph](#4-图谱模块-graph)
5. [检索模块 Retrieval](#5-检索模块-retrieval)
6. [索引模块 Index](#6-索引模块-index)
7. [数据流程图](#7-数据流程图)
8. [核心算法与技术](#8-核心算法与技术)
9. [架构问题与不足](#9-架构问题与不足)
10. [优化建议](#10-优化建议)

---

## 1. 系统概览

### 1.1 设计理念

Recall-AI 是一个为角色扮演(RP)场景设计的长期记忆管理系统，核心承诺是 **"100%不遗忘"**。系统采用多层架构设计：

```
┌─────────────────────────────────────────────────────────────┐
│                      RecallEngine                            │
│  (统一入口 - add/search/build_context)                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Processor  │  │    Graph    │  │  Retrieval  │         │
│  │  处理器层    │  │   图谱层     │  │   检索层     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Index 索引层                      │   │
│  │  Entity │ Inverted │ Vector │ N-gram │ Temporal     │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Storage 存储层                     │   │
│  │  MultiTenantStorage │ VolumeManager │ ConsolidatedMemory │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Embedding 模式

系统支持三种 Embedding 模式：

| 模式 | 内存占用 | 特点 |
|------|----------|------|
| **Lite** | ~80MB | 禁用向量索引，纯关键词检索 |
| **Local** | ~1.5GB | 本地 sentence-transformers 模型 |
| **Cloud** | ~150MB | OpenAI/SiliconFlow API |

### 1.3 核心模块

| 模块 | 职责 |
|------|------|
| **Engine** | 统一入口，协调各模块 |
| **Processor** | 实体提取、一致性检查、去重 |
| **Graph** | 知识图谱、关系管理、矛盾检测 |
| **Retrieval** | 八/十一层漏斗检索、RRF融合 |
| **Index** | 多种索引实现 |
| **Storage** | 多租户存储、分卷归档 |

---

## 2. 核心引擎 Engine

### 2.1 RecallEngine 初始化流程

```python
class RecallEngine:
    def __init__(self, ...):
        # 1. 初始化环境
        self.env_manager = EnvironmentManager(data_root)
        
        # 2. 加载配置
        self.config = self.env_manager.load_config()
        
        # 3. 确定 Embedding 配置（Lite/Local/Cloud）
        self.embedding_config = ...
        
        # 4. 初始化组件 (_init_components)
        #    - LLM 客户端
        #    - 存储层（MultiTenantStorage, VolumeManager）
        #    - 索引层（Entity, Inverted, Vector, Ngram）
        #    - 处理器层
        #    - 图谱层
        #    - 检索层
        
        # 5. 预热（仅 Local 模式）
        
        # 6. 恢复内容缓存
        self._rebuild_content_cache()
```

### 2.2 add() 方法完整流程

这是系统最核心的方法，处理记忆添加的完整流程：

```
输入: content, user_id, metadata
        │
        ▼
┌─────────────────────────────────────┐
│ 1. 去重检查                          │
│    - 三阶段去重器（如果启用）          │
│    - 回退：简单字符串精确匹配          │
└─────────────────────────────────────┘
        │ (非重复)
        ▼
┌─────────────────────────────────────┐
│ 2. 实体提取                          │
│    - SmartExtractor（优先）           │
│    - 回退：EntityExtractor           │
│    - 输出：entities, keywords         │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 3. 一致性检查（两阶段）               │
│    阶段1: 正则规则检测（快速）        │
│    阶段2: LLM深度矛盾检测（可选）     │
│    - 将违规存储到 ContradictionManager │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 4. 生成 memory_id 并存储             │
│    - MultiTenantStorage.add()        │
│    - VolumeManager.append_turn()     │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 5. 更新索引（失败不影响主流程）       │
│    - EntityIndex                     │
│    - InvertedIndex                   │
│    - NgramIndex                      │
│    - VectorIndex                     │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ 6. 更新图谱                          │
│    - KnowledgeGraph.add_relation()   │
│    - FullTextIndex（可选）            │
│    - TemporalGraph（可选）            │
└─────────────────────────────────────┘
        │
        ▼
返回: AddResult(id, success, entities, warnings)
```

### 2.3 search() 方法流程

```python
def search(self, query, user_id, top_k, ...):
    # 1. 提取查询实体和关键词
    entities = self.entity_extractor.extract(query)
    keywords = self.entity_extractor.extract_keywords(query)
    
    # 2. 检测场景
    scenario = self.scenario_detector.detect(query)
    
    # 3. 执行检索（八层/十一层检索器）
    retrieval_results = self.retriever.retrieve(
        query=query,
        entities=entities,
        keywords=keywords,
        top_k=top_k * 3,  # 多取用于过滤
    )
    
    # 4. 过滤结果（只保留当前用户的记忆）
    
    # 5. 合并存储中的结果
    
    # 6. 返回 top_k 结果
```

---

## 3. 处理器模块 Processor

### 3.1 EntityExtractor - 实体提取器

**多策略实体提取**，结合多种方法：

| 策略 | 方法 | 置信度 |
|------|------|--------|
| 已知词典 | 预定义平台/品牌名匹配 | 0.9 |
| spaCy NER | 命名实体识别 | 0.8 |
| 引号内容 | 正则提取「」『』内容 | 0.7 |
| 英文专有名词 | 首字母大写/全大写词 | 0.6 |
| jieba词性标注 | nr/ns/nt/nz 标注 | 0.65 |

```python
def extract(self, text):
    entities = []
    
    # 1. 已知实体词典匹配（高优先级）
    for name, entity_type in self.known_entities.items():
        if name.lower() in text.lower():
            entities.append(ExtractedEntity(name, entity_type, 0.9))
    
    # 2. spaCy NER
    doc = self.nlp(text)
    for ent in doc.ents:
        entities.append(ExtractedEntity(ent.text, self._map_spacy_label(ent.label_), 0.8))
    
    # 3. 中文专名提取（引号内容）
    # 4. 英文专有名词
    # 5. jieba 词性标注
    
    # 去重，保留最高置信度
    return deduplicate(entities)
```

### 3.2 SmartExtractor - 智能抽取器 (Phase 2)

**三模式自适应抽取**：

| 模式 | 说明 | 成本 |
|------|------|------|
| **RULES** | 纯规则：spaCy + jieba | 0 |
| **ADAPTIVE** | 规则初筛 + LLM精炼 | 低 |
| **LLM** | 全部使用LLM | 高 |

核心逻辑：
```python
def extract(self, text, force_mode=None):
    # 1. 始终执行本地抽取（免费、快速）
    local_result = self._local_extract(text)
    
    if mode == ExtractionMode.RULES:
        return local_result
    
    # 2. 评估复杂度
    complexity = self._assess_complexity(text, local_result)
    
    # 3. 决策是否需要 LLM
    need_llm = (mode == LLM) or (mode == ADAPTIVE and complexity >= threshold)
    
    if need_llm:
        return self._llm_extract(text, local_result)
    
    return local_result
```

### 3.3 ThreeStageDeduplicator - 三阶段去重器 (Phase 2)

**超越 Graphiti 的两阶段去重**，增加语义匹配层：

```
┌─────────────────────────────────────────────────────────────┐
│ 阶段 1: 确定性匹配 O(1)                                      │
│   - 精确匹配（归一化后）                                      │
│   - MinHash + LSH 近似匹配                                   │
│   → 高于 jaccard_threshold (0.85) → 确定重复                 │
└─────────────────────────────────────────────────────────────┘
        │ (不确定)
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 阶段 2: 语义匹配                                             │
│   - Embedding 向量相似度                                     │
│   → 高于 semantic_threshold (0.90) → 确定重复               │
│   → 低于 semantic_low_threshold (0.70) → 确定不同           │
└─────────────────────────────────────────────────────────────┘
        │ (边界情况: 0.70-0.90)
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 阶段 3: LLM 确认（可选）                                     │
│   - 仅用于边界情况                                           │
│   - 大幅降低 LLM 调用成本                                    │
└─────────────────────────────────────────────────────────────┘
```

**MinHash 实现**：
```python
class MinHasher:
    def __init__(self, num_perm=128):
        # 生成哈希参数
        self.a = np.random.randint(1, max_hash, num_perm)
        self.b = np.random.randint(0, max_hash, num_perm)
    
    def minhash(self, shingles):
        signature = [max_hash] * num_perm
        for shingle in shingles:
            h = hash(shingle)
            for i in range(num_perm):
                hash_val = (a[i] * h + b[i]) % max_hash
                signature[i] = min(signature[i], hash_val)
        return signature
```

### 3.4 ConsistencyChecker - 一致性检查器

**15+ 种属性类型检测**：

| 属性类别 | 类型 |
|----------|------|
| 数值属性 | 年龄、身高、体重 |
| 外貌属性 | 发色、眼色、肤色 |
| 固定属性 | 血型、性别、种族 |
| 状态属性 | 生死、婚姻、职业、位置 |
| 能力属性 | 能力/不能力 |

**检测能力**：
- 数值属性冲突（年龄/身高/体重等）
- 外貌属性冲突（发色/眼色/肤色等）
- 状态属性冲突（生死/婚姻/职业等）
- 关系冲突（朋友vs敌人、亲人vs陌生人）
- 时间线推理（事件顺序、年龄一致性）
- 否定句检测（不会X vs 做了X）

```python
class ConsistencyChecker:
    # 颜色同义词映射
    COLOR_SYNONYMS = {
        'black': {'黑色', '黑', '乌黑', '漆黑', '墨黑'},
        'blonde': {'金色', '金', '金黄', '淡金', '亚麻色'},
        ...
    }
    
    # 状态对立词典
    STATE_OPPOSITES = {
        'alive': ['dead'],
        'single': ['married', 'engaged'],
        ...
    }
    
    def check(self, new_content, existing_memories):
        violations = []
        
        # 1. 提取属性（年龄、发色等）
        new_attrs = self._extract_attributes(new_content)
        
        # 2. 对比现有记忆中的属性
        for memory in existing_memories:
            old_attrs = self._extract_attributes(memory['content'])
            
            # 3. 检测冲突
            conflicts = self._detect_conflicts(new_attrs, old_attrs)
            violations.extend(conflicts)
        
        return ConsistencyResult(is_consistent=len(violations)==0, violations=violations)
```

---

## 4. 图谱模块 Graph

### 4.1 KnowledgeGraph - 知识图谱

**轻量级知识图谱，无需 Neo4j**：

```python
@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict
    confidence: float
    source_text: str

class KnowledgeGraph:
    # 邻接表存储
    outgoing: Dict[str, List[Relation]]   # source → relations
    incoming: Dict[str, List[Relation]]   # target → relations
    relation_index: Dict[str, List[Relation]]  # type → relations
```

**预定义关系类型**：

| 类别 | 关系类型 |
|------|----------|
| 人物关系 | IS_FRIEND_OF, IS_ENEMY_OF, LOVES, HATES, KNOWS |
| 空间关系 | LOCATED_IN, TRAVELS_TO, LIVES_IN |
| 事件关系 | PARTICIPATED_IN, CAUSED, WITNESSED |
| 物品关系 | CARRIES, USES, GAVE_TO |

### 4.2 RelationExtractor - 关系提取器

**基于正则模式 + 共现分析**：

```python
class RelationExtractor:
    PATTERNS = [
        # 中文模式
        (r'(.+)是(.+)的(朋友|敌人|家人)', lambda m: (m[1], 'IS_X_OF', m[2])),
        (r'(.+)爱上了(.+)', lambda m: (m[1], 'LOVES', m[2])),
        (r'(.+)住在(.+)', lambda m: (m[1], 'LIVES_IN', m[2])),
        
        # 英文模式
        (r'(\w+) loves (\w+)', lambda m: (m[1], 'LOVES', m[2])),
    ]
    
    def extract(self, text, entities):
        relations = []
        
        # 1. 模式匹配
        for pattern, extractor in self.PATTERNS:
            for match in re.finditer(pattern, text):
                relations.append(extractor(match))
        
        # 2. 共现分析（同一句话中的实体可能有关系）
        for sentence in sentences:
            entities_in_sentence = [e for e in entities if e in sentence]
            if len(entities_in_sentence) >= 2:
                # 建立弱关系 MENTIONED_WITH
                for e1, e2 in combinations(entities_in_sentence, 2):
                    relations.append((e1, 'MENTIONED_WITH', e2))
        
        return relations
```

### 4.3 TemporalKnowledgeGraph - 时序知识图谱 (Phase 1)

**三时态模型**：

| 时态 | 说明 | 示例 |
|------|------|------|
| **事实时间** (valid_from/until) | 事实在现实中的有效期 | "2023年结婚" |
| **知识时间** (known_at) | 系统获知此事实的时间 | "今天对话中得知" |
| **系统时间** (created_at/expired_at) | 数据库记录的生命周期 | 记录创建/删除时间 |

```python
@dataclass
class TemporalFact:
    uuid: str
    subject: str        # 主体
    predicate: str      # 谓词
    object: str         # 客体
    fact: str           # 事实描述
    
    # 三时态
    valid_from: datetime    # 事实开始时间
    valid_until: datetime   # 事实结束时间
    known_at: datetime      # 获知时间
    created_at: datetime    # 记录创建时间
    expired_at: datetime    # 记录过期时间
```

### 4.4 ContradictionManager - 矛盾检测管理器

**四种检测策略**：

| 策略 | 说明 |
|------|------|
| **RULE** | 仅规则检测（快速） |
| **LLM** | 仅 LLM 检测（高质量） |
| **MIXED** | 规则初筛 + LLM 确认 |
| **AUTO** | 简单矛盾用规则，复杂矛盾用 LLM |

**默认规则**：
```python
def _register_default_rules(self):
    # 规则1：同主体、同谓词、不同客体 = 直接矛盾
    def rule_direct_conflict(old, new):
        if old.subject == new.subject and old.predicate == new.predicate:
            if old.object != new.object and time_overlaps(old, new):
                return ContradictionType.DIRECT
    
    # 规则2：时态冲突
    def rule_temporal_conflict(old, new):
        # 同一事实但时间范围冲突
        ...
    
    # 规则3：互斥谓词（LOVES vs HATES）
    def rule_exclusive_predicates(old, new):
        exclusive_pairs = [
            ('LOVES', 'HATES'),
            ('IS_FRIEND_OF', 'IS_ENEMY_OF'),
            ('ALIVE', 'DEAD'),
        ]
        ...
```

---

## 5. 检索模块 Retrieval

### 5.1 EightLayerRetriever - 八层漏斗检索器

**Phase 3.6 升级为并行四路召回**：

```
┌────────────────────────────────────────────────────────────┐
│                    并行四路召回                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ 路径1: 语义 │  │ 路径2: 关键词│  │ 路径3: 实体 │       │
│  │ VectorIndex │  │ Inverted    │  │ EntityIndex │       │
│  │ (95-99%召回)│  │ (100%召回)  │  │ (100%召回)  │       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │
│         │                │                │               │
│  ┌──────┴────────────────┴────────────────┴──────┐       │
│  │              路径4: N-gram 原文               │       │
│  │              (100%精确匹配保证)               │       │
│  └────────────────────────┬──────────────────────┘       │
└───────────────────────────┼──────────────────────────────┘
                            ▼
              ┌─────────────────────────────┐
              │   RRF 融合 (k=60)           │
              │   score = Σ w/(k + rank)    │
              └─────────────────────────────┘
                            ▼
              ┌─────────────────────────────┐
              │   L7: 重排序                │
              └─────────────────────────────┘
                            ▼
                       返回 top_k
```

**各路权重配置**：
```python
self.config = {
    'vector_weight': 1.0,    # 语义召回
    'keyword_weight': 1.2,   # 关键词召回（100%召回，权重更高）
    'entity_weight': 1.0,    # 实体召回
    'ngram_weight': 1.5,     # N-gram 原文（最高，确保精确匹配优先）
}
```

### 5.2 ElevenLayerRetriever - 十一层检索器 (Phase 3)

**完整11层架构**：

```
[快速过滤阶段]
┌────────────────────────────────────────┐
│ L1: Bloom Filter - O(1) 快速否定       │
│ L2: Temporal Filter - 时间范围预筛选   │  ← Phase 3 新增
└────────────────────────────────────────┘

[召回阶段]
┌────────────────────────────────────────┐
│ L3: Inverted Index - 关键词匹配        │
│ L4: Entity Index - 实体关联查找        │
│ L5: Graph Traversal - BFS图遍历扩展    │  ← Phase 3 新增
│ L6: N-gram Index - 模糊匹配            │
│ L7: Vector Coarse - 近似最近邻         │
└────────────────────────────────────────┘

[精排阶段]
┌────────────────────────────────────────┐
│ L8: Vector Fine - 精确距离计算         │
│ L9: Rerank - TF-IDF 重排序             │
│ L10: Cross-Encoder - 交叉编码器精排    │  ← Phase 3 新增
│ L11: LLM Filter - 语义相关性判断       │
└────────────────────────────────────────┘
```

### 5.3 RRF Fusion - 倒数排名融合

**公式**：
$$score(d) = \sum_{i} \frac{w_i}{k + rank_i(d)}$$

其中 $k$ 通常取 60。

```python
def reciprocal_rank_fusion(results_list, k=60, weights=None):
    rrf_scores = defaultdict(float)
    
    for weight, results in zip(weights, results_list):
        for rank, (doc_id, _) in enumerate(results, start=1):
            rrf_scores[doc_id] += weight * (1.0 / (k + rank))
    
    return sorted(rrf_scores.items(), key=lambda x: -x[1])
```

**优点**：
- 不需要归一化不同检索器的分数
- 对排名靠前的结果给予更高权重
- 自动处理不同召回路径的结果合并

### 5.4 ContextBuilder - 上下文构建器

**Token 预算分配**：

```python
def build(self, memories, recent_turns, system_prompt, query):
    # 计算各部分 token 预算
    system_tokens = estimate_tokens(system_prompt)
    query_tokens = estimate_tokens(query)
    remaining = max_tokens - system_tokens - query_tokens
    
    # 分配（记忆:对话 = 50:50 或 60:40）
    memory_budget = remaining * memory_ratio
    turns_budget = remaining - memory_budget
    
    # 构建各部分
    memory_section = build_memory_section(memories, memory_budget)
    recent_section = build_turns_section(recent_turns, turns_budget)
```

---

## 6. 索引模块 Index

### 6.1 VectorIndex - 向量索引

**使用 FAISS IndexFlatIP（内积相似度）**：

```python
class VectorIndex:
    def __init__(self, data_path, embedding_config):
        # 懒加载 Embedding 后端
        self._embedding_backend = None
        
        # FAISS 索引
        self._index = None  # faiss.IndexFlatIP
        self.turn_mapping = []  # FAISS内部ID → doc_id
    
    def add_text(self, doc_id, text):
        embedding = self.encode(text)
        self.index.add(embedding.reshape(1, -1))
        self.turn_mapping.append(doc_id)
    
    def search(self, query, top_k=20):
        query_embedding = self.encode(query).reshape(1, -1)
        scores, indices = self.index.search(query_embedding, top_k)
        return [(self.turn_mapping[i], scores[0][j]) 
                for j, i in enumerate(indices[0]) if i >= 0]
```

### 6.2 InvertedIndex - 倒排索引

```python
class InvertedIndex:
    # keyword → set of memory_ids
    index: Dict[str, Set[str]]
    
    def add(self, keyword, turn_id):
        self.index[keyword.lower()].add(turn_id)
    
    def search_all(self, keywords):  # AND 逻辑
        result_sets = [self.index.get(kw.lower(), set()) for kw in keywords]
        return list(set.intersection(*result_sets))
    
    def search_any(self, keywords):  # OR 逻辑
        result = set()
        for kw in keywords:
            result.update(self.index.get(kw.lower(), set()))
        return list(result)
```

### 6.3 EntityIndex - 实体索引

```python
@dataclass
class IndexedEntity:
    id: str
    name: str
    aliases: List[str]
    entity_type: str
    turn_references: List[str]  # 出现过的记忆ID
    confidence: float

class EntityIndex:
    entities: Dict[str, IndexedEntity]   # id → entity
    name_index: Dict[str, str]           # name/alias → id
```

### 6.4 OptimizedNgramIndex - N-gram索引

**两层搜索策略**（确保100%不遗忘）：

```python
class OptimizedNgramIndex:
    # 主索引：名词短语 → [memory_ids]
    noun_phrases: Dict[str, List[str]]
    
    # 原文存储：memory_id → content（用于兜底）
    _raw_content: Dict[str, str]
    
    def search(self, query):
        # 第一层：名词短语索引搜索
        phrases = extract_noun_phrases(query)
        candidates = set()
        for phrase in phrases:
            if phrase in self.noun_phrases:
                candidates.update(self.noun_phrases[phrase])
        
        if candidates:
            return list(candidates)
        
        # 第二层：原文兜底（终极兜底，100%不遗忘）
        return self._raw_text_fallback_search(query)
    
    def _raw_text_fallback_search(self, query):
        results = []
        query_lower = query.lower()
        
        for memory_id, content in self._raw_content.items():
            if query_lower in content.lower():
                results.append(memory_id)
        
        return results
```

---

## 7. 数据流程图

### 7.1 添加记忆数据流

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                     RecallEngine.add()                       │
└─────────────────────────────────────────────────────────────┘
    │
    ├──────────────────────────────────────────────────────────┐
    │                                                          │
    ▼                                                          ▼
┌───────────────────┐                              ┌───────────────────┐
│ ThreeStageDedup   │                              │ SmartExtractor    │
│ - MinHash+LSH     │                              │ - EntityExtractor │
│ - Semantic Match  │                              │ - Keywords        │
│ - LLM Confirm     │                              │ - Relations       │
└───────────────────┘                              └───────────────────┘
    │                                                          │
    │ (if not duplicate)                                       │
    │◄─────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────┐
│ ConsistencyCheck  │
│ - Rule Detection  │
│ - LLM Detection   │
└───────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────────┐
│                        存储 & 索引                             │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ MultiTenant │  │ VolumeManager│ │ Consolidated │           │
│  │ Storage     │  │ (Archive)    │ │ Memory       │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ EntityIndex │  │ InvertedIdx │  │ VectorIndex │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ NgramIndex  │  │ KnowledgeGraph│ │ TemporalGraph│          │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└───────────────────────────────────────────────────────────────┘
```

### 7.2 检索数据流

```
Query
    │
    ▼
┌───────────────────────────────────────────────────────────────┐
│                   RecallEngine.search()                        │
└───────────────────────────────────────────────────────────────┘
    │
    ├─────────────────────────────┐
    ▼                             ▼
┌─────────────────┐      ┌─────────────────┐
│ Entity Extract  │      │ Keyword Extract │
└─────────────────┘      └─────────────────┘
    │                             │
    └─────────────┬───────────────┘
                  ▼
┌───────────────────────────────────────────────────────────────┐
│                  ElevenLayerRetriever                          │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           并行四路召回 (ThreadPoolExecutor)            │    │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐     │    │
│  │  │ Vector │  │Keyword │  │ Entity │  │ N-gram │     │    │
│  │  │ Index  │  │ Index  │  │ Index  │  │ Index  │     │    │
│  │  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘     │    │
│  │      └───────────┼───────────┼───────────┘          │    │
│  │                  ▼                                   │    │
│  │           ┌──────────────┐                          │    │
│  │           │  RRF Fusion  │                          │    │
│  │           └──────────────┘                          │    │
│  └──────────────────────────────────────────────────────┘    │
│                           │                                   │
│                           ▼                                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    精排阶段                             │  │
│  │  L8: Vector Fine → L9: Rerank → L10: CrossEncoder     │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  Top-K 结果  │
                    └──────────────┘
```

---

## 8. 核心算法与技术

### 8.1 MinHash + LSH 快速相似度估算

**MinHash**：将集合压缩为固定长度签名，估算 Jaccard 相似度。

时间复杂度：$O(|S| \cdot k)$，其中 $k$ 是排列数（通常128）。

**LSH（局部敏感哈希）**：将相似项目哈希到同一桶中，实现 $O(1)$ 候选检索。

### 8.2 FAISS 向量检索

使用 `IndexFlatIP`（内积相似度），支持：
- 精确 k-NN 搜索
- 向量归一化后等价于余弦相似度

### 8.3 RRF 融合算法

多路召回结果融合，避免分数归一化问题。

### 8.4 BM25 全文检索（可选）

Phase 1 功能，通过 `FullTextIndex` 实现。

### 8.5 图遍历算法

- BFS 查找路径
- 子图提取
- 社区检测（Louvain 算法）

---

## 9. 架构问题与不足

### 9.1 已识别的问题

#### 问题1：索引不一致性风险

**现象**：`add()` 方法中，存储和索引更新是分离的，索引失败不影响主流程。

**风险**：可能导致存储成功但索引未更新，检索时找不到已添加的记忆。

```python
# engine.py 约 1350 行
try:
    # 更新索引
    if self._entity_index:
        ...
except Exception as e:
    _safe_print(f"[Recall] 索引更新失败（不影响主流程）: {e}")
    # 但记忆已经存储成功了！
```

**建议**：增加索引一致性检查机制，或使用事务保证原子性。

#### 问题2：N-gram 原文兜底性能

**现象**：当主索引未命中时，会扫描所有原文。

**风险**：随着数据量增长，兜底搜索会变慢。

```python
def _raw_text_fallback_search(self, query):
    for memory_id, content in self._raw_content.items():  # O(n) 全扫描
        if query_lower in content.lower():
            results.append(memory_id)
```

**建议**：
1. 增加后缀数组/后缀树索引
2. 使用更高效的子串搜索算法（如 Aho-Corasick）
3. 分片并行化（已部分实现）

#### 问题3：用户隔离在检索层

**现象**：检索时先从全局索引查询，再过滤用户。

```python
# 从全局索引检索（可能包含其他用户的结果）
retrieval_results = self.retriever.retrieve(...)

# 【BUG-003 修复】过滤结果，只保留当前用户的记忆
retrieval_results = [r for r in retrieval_results if r.id in user_memory_ids]
```

**风险**：
1. 浪费计算资源（检索了不需要的数据）
2. 隐私风险（虽然后续过滤，但数据已加载到内存）

**建议**：在索引层实现多租户隔离，而不是在检索后过滤。

#### 问题4：LLM 调用缺乏统一管理

**现象**：多个模块独立调用 LLM（SmartExtractor、ConsistencyChecker、ContradictionManager）。

**风险**：
1. 成本难以控制
2. 调用策略不一致
3. 错误处理分散

**建议**：引入统一的 LLM 调用层，集中管理配额、重试、降级策略。

#### 问题5：向量索引维度变更处理

**现象**：当更换 Embedding 模型时，需要重建索引。

```python
if self._index.d != self.dimension:
    _safe_print(f"[VectorIndex] 警告: 索引维度不匹配")
    self._index = faiss.IndexFlatIP(self.dimension)
    self.turn_mapping = []  # 丢失所有历史索引！
```

**建议**：提供平滑迁移机制，在后台异步重建索引。

### 9.2 潜在的性能瓶颈

| 操作 | 复杂度 | 瓶颈场景 |
|------|--------|----------|
| 向量搜索 | O(n) | 数据量 > 10万时 |
| 原文兜底 | O(n×m) | 数据量大 + 长查询 |
| 一致性检查 | O(k²) | 相关记忆多时 |
| 图遍历 | O(V+E) | 图规模大时 |

### 9.3 缺失的功能

1. **增量索引**：当前是全量重建，缺少增量更新
2. **索引压缩**：长期运行后索引文件可能过大
3. **冷热数据分离**：所有数据同等对待
4. **分布式支持**：当前仅支持单机

---

## 10. 优化建议

### 10.1 短期优化（1-2周）

1. **索引一致性保障**
   - 增加索引校验机制
   - 启动时检测并修复不一致

2. **查询优化**
   - 为常用查询增加缓存
   - 实现查询结果预取

3. **监控增强**
   - 添加更细粒度的性能指标
   - 实现慢查询日志

### 10.2 中期优化（1-3月）

1. **索引层多租户隔离**
   - 重构索引结构，按用户分片
   - 避免检索后过滤

2. **向量索引升级**
   - 考虑使用 IVF 或 HNSW 索引
   - 支持增量更新

3. **LLM 调用统一管理**
   - 实现调用配额管理
   - 支持多模型切换和降级

### 10.3 长期优化（3-6月）

1. **分布式架构**
   - 支持水平扩展
   - 实现数据分片

2. **冷热数据分离**
   - 热数据保持内存
   - 冷数据归档压缩

3. **实时更新流水线**
   - 实现事件驱动架构
   - 支持实时索引更新

---

## 附录

### A. 文件结构概览

```
recall/
├── engine.py                 # 核心引擎（3004行）
├── processor/
│   ├── entity_extractor.py   # 实体提取器
│   ├── smart_extractor.py    # 智能抽取器（634行）
│   ├── three_stage_deduplicator.py  # 三阶段去重（643行）
│   ├── consistency.py        # 一致性检查器（1456行）
│   ├── foreshadowing*.py     # 伏笔相关
│   └── context_tracker.py    # 上下文追踪
├── graph/
│   ├── knowledge_graph.py    # 知识图谱
│   ├── relation_extractor.py # 关系提取器
│   ├── temporal_knowledge_graph.py  # 时序图谱（1327行）
│   └── contradiction_manager.py     # 矛盾管理（639行）
├── retrieval/
│   ├── eight_layer.py        # 八层检索器（723行）
│   ├── eleven_layer.py       # 十一层检索器（1312行）
│   ├── rrf_fusion.py         # RRF融合
│   └── context_builder.py    # 上下文构建器
└── index/
    ├── vector_index.py       # 向量索引（461行）
    ├── inverted_index.py     # 倒排索引
    ├── entity_index.py       # 实体索引
    ├── ngram_index.py        # N-gram索引（425行）
    └── temporal_index.py     # 时态索引
```

### B. 配置环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_API_KEY` | LLM API密钥 | - |
| `LLM_MODEL` | LLM模型名称 | gpt-4o-mini |
| `TEMPORAL_GRAPH_ENABLED` | 启用时态图谱 | false |
| `CONTRADICTION_DETECTION_ENABLED` | 启用矛盾检测 | false |
| `FULLTEXT_ENABLED` | 启用全文索引 | false |
| `ELEVEN_LAYER_RETRIEVER_ENABLED` | 启用11层检索 | false |
| `SMART_EXTRACTOR_MODE` | 抽取模式 | RULES |
| `DEDUP_JACCARD_THRESHOLD` | 去重阈值 | 0.85 |

---

*本报告基于 Recall-AI v4.0 代码分析生成*
