"""Recall 核心引擎 - 统一的记忆管理入口"""
from __future__ import annotations

import os
import time
import uuid
import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

from .version import __version__
from .mode import get_mode_config
# 注意：RecallInit 和 LightweightConfig 保留用于未来扩展
from .init import RecallInit  # noqa: F401 - 保留用于 CLI 等场景
from .config import LightweightConfig, TripleRecallConfig, RecallConfig  # noqa: F401 - 保留用于配置迁移
from .models import Entity, EntityType
from .storage import (
    VolumeManager, ConsolidatedMemory, ConsolidatedEntity,
    MultiTenantStorage, MemoryScope, CoreSettings
)
from .index import EntityIndex, InvertedIndex, VectorIndex, OptimizedNgramIndex, MetadataIndex
# v7.0 C-2: VectorIndexIVF 自动切换
from .index import VectorIndexIVF
# v7.0 B-1: Backend Abstraction Layer
from .backends.factory import BackendFactory, BackendTier
from .graph import RelationExtractor, TemporalKnowledgeGraph
from .processor import (
    EntityExtractor,
    ConsistencyChecker, MemorySummarizer, ScenarioDetector,
    ContextTracker, ContextType
)

# v4.0 Phase 1/2 可选模块（延迟导入以保持向后兼容）
# 这些模块仅在配置启用时才会加载
# v5.0: ForeshadowingTracker, ForeshadowingAnalyzer, ForeshadowingAnalyzerConfig,
#        AnalysisResult, Foreshadowing 改为条件导入（仅 RP 模式加载）
from .retrieval import EightLayerRetriever, ContextBuilder
# Phase 3: ElevenLayerRetriever（v7.0 起默认启用）
from .retrieval import (
    ElevenLayerRetriever, RetrievalConfig, 
    TemporalContext, LayerWeights
)
# v7.0 C-3: ParallelRetriever 接线激活
from .retrieval import ParallelRetriever, RetrievalTask
from .retrieval.parallel_retrieval import RetrievalSource
from .utils import (
    LLMClient, WarmupManager, PerformanceMonitor,
    EnvironmentManager
)
from .utils.perf_monitor import MetricType
from .utils.task_manager import TaskManager, TaskType, get_task_manager
from .embedding import EmbeddingConfig
from .embedding.base import EmbeddingBackendType
from .prompts import PromptManager


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


logger = logging.getLogger(__name__)


@dataclass
class AddResult:
    """添加记忆结果"""
    id: str
    success: bool
    entities: List[str] = field(default_factory=list)
    message: str = ""
    consistency_warnings: List[str] = field(default_factory=list)  # 一致性警告


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    entities: List[str] = field(default_factory=list)


@dataclass
class AddTurnResult:
    """添加对话轮次结果 (v4.2 性能优化)"""
    success: bool
    user_memory_id: str = ""
    ai_memory_id: str = ""
    entities: List[str] = field(default_factory=list)
    message: str = ""
    consistency_warnings: List[str] = field(default_factory=list)
    processing_time_ms: float = 0


class RecallEngine:
    """Recall 核心引擎
    
    主要功能：
    1. 记忆存储和检索
    2. 实体和关系管理
    3. 伏笔追踪
    4. 一致性检查
    5. 上下文构建
    
    使用示例：
    ```python
    from recall import RecallEngine
    
    # 初始化
    engine = RecallEngine()
    
    # 添加记忆
    result = engine.add("用户喜欢喝咖啡", user_id="user1")
    
    # 搜索记忆
    memories = engine.search("咖啡", user_id="user1")
    
    # 构建上下文
    context = engine.build_context(
        query="推荐一些饮品",
        user_id="user1"
    )
    ```
    """
    
    def __init__(
        self,
        data_root: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        lightweight: bool = False,
        lite: bool = None,  # 新名称，与 lightweight 等效
        embedding_config: Optional[EmbeddingConfig] = None,
        auto_warmup: bool = True,
        foreshadowing_config: Optional[ForeshadowingAnalyzerConfig] = None
    ):
        """初始化 Recall 引擎
        
        Args:
            data_root: 数据存储根目录，默认为 ./recall_data
            llm_model: LLM 模型名称，默认为 gpt-3.5-turbo
            llm_api_key: LLM API Key
            lite: 是否使用 Lite 模式（约80MB内存，无语义搜索）
            lightweight: lite 的别名（向后兼容）
            embedding_config: Embedding 配置，支持三种模式：
                - None/自动: 根据环境自动选择
                - EmbeddingConfig.lite(): Lite 模式，~100MB内存
                - EmbeddingConfig.cloud_openai(key): Cloud 模式，~150MB内存
                - EmbeddingConfig.cloud_siliconflow(key): Cloud 模式（国内）
                - EmbeddingConfig.local(): Local 模式，~1.5GB内存
            auto_warmup: 是否自动预热模型
            foreshadowing_config: 伏笔分析器配置（可选）
                - None/默认: 手动模式，不启用自动分析
                - ForeshadowingAnalyzerConfig.llm_based(...): LLM 辅助模式
        """
        # 处理 lite/lightweight 别名
        if lite is not None:
            lightweight = lite
        
        # 1. 初始化环境
        self.env_manager = EnvironmentManager(data_root)
        self.env_manager.setup()
        self.data_root = str(self.env_manager.data_root)
        
        # 2. 加载配置
        self.config = self.env_manager.load_config()
        
        # v7.0 D5: 集中式配置（消除散落的 os.environ.get 默认值不一致问题）
        self.recall_config = RecallConfig.from_env()
        
        # 保存伏笔分析器配置（稍后在 _init_components 中使用）
        self._foreshadowing_config = foreshadowing_config
        
        # 3. 确定 Embedding 配置
        if lightweight:
            self.embedding_config = EmbeddingConfig.lite()
        elif embedding_config:
            self.embedding_config = embedding_config
        else:
            # 自动选择
            from .embedding.factory import auto_select_backend
            self.embedding_config = auto_select_backend()
        
        # 根据最终的 embedding_config 确定是否为 Lite 模式
        self.lightweight = (self.embedding_config.backend == EmbeddingBackendType.NONE)
        
        # 4. 初始化组件
        self._init_components(llm_model, llm_api_key)
        
        # 5. 预热
        if auto_warmup and not lightweight and self.embedding_config.backend == EmbeddingBackendType.LOCAL:
            self._warmup()
        
        # 6. 恢复内容缓存（确保重启后检索能找到内容）
        self._rebuild_content_cache()
        
        # 打印模式信息
        mode = self._get_mode_name()
        _safe_print(f"[Recall v{__version__}] 引擎初始化完成 ({mode})")
    
    def _get_mode_name(self) -> str:
        """获取当前模式名称"""
        backend = self.embedding_config.backend
        
        # 检测是否安装了企业级依赖
        enterprise_features = []
        try:
            import kuzu
            enterprise_features.append("Kuzu")
        except ImportError:
            pass
        try:
            import networkx
            enterprise_features.append("NetworkX")
        except ImportError:
            pass
        
        # 基础模式名称
        if backend == EmbeddingBackendType.NONE:
            base_mode = "Lite 模式"
        elif backend == EmbeddingBackendType.LOCAL:
            base_mode = "Local 模式"
        elif backend == EmbeddingBackendType.OPENAI:
            base_mode = "Cloud 模式-OpenAI"
        elif backend == EmbeddingBackendType.SILICONFLOW:
            base_mode = "Cloud 模式-硅基流动"
        elif backend == EmbeddingBackendType.CUSTOM:
            base_mode = "Cloud 模式-自定义API"
        else:
            base_mode = "未知模式"
        
        # 如果有企业级功能，添加标识
        if enterprise_features:
            return f"{base_mode} + Enterprise ({', '.join(enterprise_features)})"
        return base_mode
    
    def _init_components(
        self,
        llm_model: Optional[str],
        llm_api_key: Optional[str]
    ):
        """初始化各组件"""
        # LLM客户端（优先使用 LLM_API_KEY，兼容旧的 OPENAI_API_KEY）
        rc = self.recall_config  # v7.0 D5: 集中式配置
        model = llm_model or rc.llm_model or self.config.get('llm', {}).get('model', 'gpt-4o-mini')
        api_key = llm_api_key or rc.llm_api_key or None
        api_base = rc.llm_api_base or None
        llm_timeout = rc.llm_timeout  # 默认60秒，避免复杂请求超时
        self.llm_client = LLMClient(model=model, api_key=api_key, api_base=api_base, timeout=llm_timeout) if api_key else None
        
        if self.llm_client:
            _safe_print(f"[Recall] LLM 客户端已初始化 (模型: {model})")
        else:
            _safe_print("[Recall] LLM 客户端未初始化（未配置 LLM_API_KEY）")
        
        # Prompt 模板管理器（v7.0: 统一模式）
        try:
            self.prompt_manager = PromptManager()
        except Exception as e:
            logger.warning(f"[Recall] PromptManager 初始化失败（不影响核心功能）: {e}")
            self.prompt_manager = None
        
        # 存储层
        self.storage = MultiTenantStorage(
            base_path=os.path.join(self.data_root, 'data')
        )
        
        # 分卷存储（Archive原文保存 - 确保100%不遗忘）
        self.volume_manager = VolumeManager(
            data_path=os.path.join(self.data_root, 'data')
        )
        
        # 索引层（Lite 模式延迟加载）
        self._entity_index: Optional[EntityIndex] = None
        self._inverted_index: Optional[InvertedIndex] = None
        self._vector_index: Optional[VectorIndex] = None
        self._ngram_index: Optional[OptimizedNgramIndex] = None
        self._metadata_index: Optional[MetadataIndex] = None
        # v7.0 C-2: VectorIndexIVF（在 _init_indexes 中按需创建）
        self._vector_index_ivf: Optional[VectorIndexIVF] = None
        self._ivf_auto_switch_threshold = self.recall_config.ivf_auto_switch_threshold
        
        if not self.lightweight:
            self._init_indexes()
        
        # 处理器层（需要先初始化，因为图谱层依赖）
        self.entity_extractor = EntityExtractor()
        
        # 获取Embedding后端（用于语义去重）
        embedding_backend_for_trackers = None
        if self._vector_index and self._vector_index.enabled:
            embedding_backend_for_trackers = self._vector_index.embedding_backend
        
        # 保存 embedding_backend 到实例属性（供检索器等使用）
        self.embedding_backend = embedding_backend_for_trackers
        
        # v7.0 B-1: Backend Abstraction Layer — 初始化后端工厂
        self._init_backend_factory()
        
        # v7.0 模式配置（统一模式，全功能启用）
        self._mode = get_mode_config()
        
        # 伏笔追踪器（支持语义去重）— v7.0: 仅在 foreshadowing_enabled 时初始化
        if self._mode.foreshadowing_enabled:
            from .processor import (
                ForeshadowingTracker,
                ForeshadowingAnalyzer, ForeshadowingAnalyzerConfig, AnalysisResult
            )
            from .processor.foreshadowing import Foreshadowing
            self.foreshadowing_tracker = ForeshadowingTracker(
                base_path=os.path.join(self.data_root, 'data'),
                embedding_backend=embedding_backend_for_trackers
            )
            self.foreshadowing_analyzer = ForeshadowingAnalyzer(
                tracker=self.foreshadowing_tracker,
                config=self._foreshadowing_config,
                storage_dir=os.path.join(self.data_root, 'data', 'foreshadowing_analyzer'),
                memory_provider=self._get_recent_memories_for_analysis
            )
            _safe_print("[Recall v7.0] 伏笔系统已初始化")
        else:
            self.foreshadowing_tracker = None
            self.foreshadowing_analyzer = None
            _safe_print("[Recall v7.0] 伏笔系统已禁用 (FORESHADOWING_ENABLED=false)")
        
        # L0 核心设定（角色卡、世界观、规则等）
        # 提前加载，因为 ConsistencyChecker 需要 absolute_rules
        self.core_settings = CoreSettings.load(
            data_path=os.path.join(self.data_root, 'data')
        )
        
        # 一致性检查器（传入用户定义的绝对规则 + LLM客户端用于语义检测）
        self.consistency_checker = ConsistencyChecker(
            absolute_rules=self.core_settings.absolute_rules,
            llm_client=self.llm_client  # 启用LLM语义规则检测
        )
        self.memory_summarizer = MemorySummarizer(llm_client=self.llm_client)
        self.scenario_detector = ScenarioDetector()
        
        # v7.0: 时间意图解析器 / 事件关联器 / 主题聚类器
        self._init_processors()
        
        # 持久上下文追踪器（追踪持久性前提条件）
        # 使用同一个embedding_backend用于语义去重
        # 使用新的 {user_id}/{character_id}/ 存储结构
        # 传入 memory_provider 用于从已保存记忆获取对话上下文，帮助 LLM 更好提取条件
        self.context_tracker = ContextTracker(
            base_path=os.path.join(self.data_root, 'data'),
            llm_client=self.llm_client,
            embedding_backend=embedding_backend_for_trackers,
            memory_provider=self._get_recent_memories_for_analysis
        )
        
        # 长期记忆层（L1 ConsolidatedMemory）
        self.consolidated_memory = ConsolidatedMemory(
            data_path=os.path.join(self.data_root, 'data')
        )
        
        # 图谱层（统一使用 TemporalKnowledgeGraph，支持 file/kuzu 后端）
        # 读取图谱后端配置
        graph_backend = self.recall_config.temporal_graph_backend.lower()
        kuzu_buffer_pool_size = self.recall_config.kuzu_buffer_pool_size
        self._unified_graph = TemporalKnowledgeGraph(
            data_path=os.path.join(self.data_root, 'data'),
            backend=graph_backend,
            kuzu_buffer_pool_size=kuzu_buffer_pool_size
        )
        # 兼容别名：knowledge_graph 和 temporal_graph 都指向同一个实例
        self.knowledge_graph = self._unified_graph
        self.temporal_graph = self._unified_graph
        _safe_print(f"[Recall v4.0] 统一图谱已初始化 (backend={graph_backend})")
        
        self.relation_extractor = RelationExtractor(
            entity_extractor=self.entity_extractor
        )
        
        # 检索层 - 提供内容回调
        # Phase 3.6: 加载三路召回配置
        self.triple_recall_config = TripleRecallConfig.from_env()
        
        # v7.0 C-2: 使用活跃向量索引（可能是 IVF）
        active_vector_index = self.get_active_vector_index()
        
        self.retriever = EightLayerRetriever(
            bloom_filter=self._ngram_index.bloom_filter if self._ngram_index else None,
            inverted_index=self._inverted_index,
            entity_index=self._entity_index,
            ngram_index=self._ngram_index,
            vector_index=active_vector_index,
            llm_client=self.llm_client,
            content_store=self._get_memory_content_by_id,
            # Phase 3.6: 传入 embedding_backend（用于 VectorIndexIVF）
            embedding_backend=self.embedding_backend,
        )
        
        # Phase 3.6: 注入并行召回配置
        if self.triple_recall_config.enabled:
            self.retriever.config.update({
                'parallel_recall_enabled': True,
                'rrf_k': self.triple_recall_config.rrf_k,
                'vector_weight': self.triple_recall_config.vector_weight,
                'keyword_weight': self.triple_recall_config.keyword_weight,
                'entity_weight': self.triple_recall_config.entity_weight,
                'fallback_enabled': self.triple_recall_config.fallback_enabled,
                'fallback_parallel': self.triple_recall_config.fallback_parallel,
                'fallback_workers': self.triple_recall_config.fallback_workers,
            })
        
        self.context_builder = ContextBuilder()
        
        # v7.0 C-3: ParallelRetriever 接线（可用但非默认检索路径）
        self.parallel_retriever = self._init_parallel_retriever()
        
        # 监控
        self.monitor = PerformanceMonitor(auto_collect=False)
        
        # 预加载最近的卷（确保热数据在内存中，支持上万轮RP）
        self.volume_manager.preload_recent()
        
        # 检查并为已有的伏笔/条件补建 VectorIndex 索引（首次升级时执行）
        self._check_and_rebuild_index()
        
        # v4.0 Phase 1 可选模块初始化（基于配置开关）
        self._init_v4_modules()
        
        # v7.0: 记忆 CRUD 操作委托模块
        from .memory_ops import MemoryOperations
        self._memory_ops = MemoryOperations(self)

        # v7.0.2: 注册驱逐回调，确保 ScopedMemory LRU 驱逐时级联清理所有索引
        self.storage.set_evict_callback(self._on_memories_evicted)

        # v7.0: 上下文构建委托模块
        from .context_build import ContextBuild
        self._context_build = ContextBuild(self)
        
        # v7.0: ConsolidationManager 初始化（双层整合：热层摘要 + 冷层原文归档）
        try:
            from .processor.consolidation import ConsolidationManager
            self.consolidation_manager = ConsolidationManager(
                data_path=os.path.join(self.data_root, 'data')
            )
            _safe_print("[Recall v7.0] ConsolidationManager 已初始化")
        except Exception as e:
            self.consolidation_manager = None
            _safe_print(f"[Recall v7.0] ConsolidationManager 初始化失败: {e}")
    
    def _init_v4_modules(self):
        """初始化 v4.0 Phase 1/2 可选模块
        
        这些模块基于配置文件中的开关决定是否启用：
        - TEMPORAL_GRAPH_ENABLED: 时态追踪增强功能（图谱本身已在核心初始化）
        - CONTRADICTION_DETECTION_ENABLED: 矛盾检测
        - FULLTEXT_ENABLED: 全文检索 (BM25)
        
        设计原则：
        1. 默认关闭，不影响现有功能
        2. 即使启用失败也不影响引擎运行
        3. 所有 Phase 1 模块都是可选的增强功能
        
        注意：temporal_graph 已在核心初始化中创建（统一图谱），
        这里只处理额外的时态配置。
        """
        # 初始化为 None，表示未启用
        self.contradiction_manager = None
        self.fulltext_index = None
        
        # 读取配置（从 RecallConfig 集中管理）
        rc = self.recall_config
        temporal_enabled = rc.temporal_graph_enabled
        contradiction_enabled = rc.contradiction_detection_enabled
        fulltext_enabled = rc.fulltext_enabled
        
        # 1. 时态增强配置（temporal_graph 已在核心初始化中创建）
        if temporal_enabled and self.temporal_graph:
            try:
                # 读取衰减率和历史记录限制配置
                decay_rate = rc.temporal_decay_rate
                max_history = rc.temporal_max_history
                # 设置额外配置（如果类支持）
                if hasattr(self.temporal_graph, 'decay_rate'):
                    self.temporal_graph.decay_rate = decay_rate
                if hasattr(self.temporal_graph, 'max_history'):
                    self.temporal_graph.max_history = max_history
                _safe_print(f"[Recall v4.0] 时态增强功能已启用 (decay_rate={decay_rate})")
            except Exception as e:
                _safe_print(f"[Recall v4.0] 时态增强配置失败（不影响核心功能）: {e}")
        
        # 2. 矛盾检测管理器
        if contradiction_enabled:
            try:
                from .graph import ContradictionManager, DetectionStrategy
                # 策略映射：支持新旧名称，默认 MIXED
                strategy_str = rc.contradiction_detection_strategy.upper()
                strategy_map = {
                    # 新名称（推荐）
                    'RULE': DetectionStrategy.RULE,
                    'LLM': DetectionStrategy.LLM,
                    'MIXED': DetectionStrategy.MIXED,
                    'AUTO': DetectionStrategy.AUTO,
                    # 旧名称（向后兼容）
                    'EMBEDDING': DetectionStrategy.MIXED,  # 兼容旧配置
                    'LLM_ONLY': DetectionStrategy.LLM,
                    'RULE_ONLY': DetectionStrategy.RULE,
                    'HYBRID': DetectionStrategy.MIXED,
                }
                strategy = strategy_map.get(strategy_str, DetectionStrategy.MIXED)
                
                # 读取额外配置
                auto_resolve = rc.contradiction_auto_resolve
                similarity_threshold = rc.contradiction_similarity_threshold
                
                self.contradiction_manager = ContradictionManager(
                    data_path=os.path.join(self.data_root, 'data'),
                    strategy=strategy,
                    llm_client=self.llm_client,
                    auto_resolve=auto_resolve
                )
                # 设置相似度阈值（如果类支持）
                if hasattr(self.contradiction_manager, 'similarity_threshold'):
                    self.contradiction_manager.similarity_threshold = similarity_threshold
                _safe_print(f"[Recall v4.0] 矛盾检测已启用 (策略: {strategy.value}, 自动解决: {auto_resolve})")
            except Exception as e:
                _safe_print(f"[Recall v4.0] 矛盾检测初始化失败（不影响核心功能）: {e}")
        
        # 3. 全文检索索引 (BM25)
        if fulltext_enabled:
            try:
                from .index import FullTextIndex, BM25Config
                k1 = rc.fulltext_k1
                b = rc.fulltext_b
                weight = rc.fulltext_weight
                
                self.fulltext_index = FullTextIndex(
                    data_path=os.path.join(self.data_root, 'index', 'fulltext'),
                    config=BM25Config(k1=k1, b=b)
                )
                # 保存权重供检索时使用
                self._fulltext_weight = weight
                _safe_print(f"[Recall v4.0] 全文检索已启用 (BM25 k1={k1}, b={b}, weight={weight})")
            except Exception as e:
                _safe_print(f"[Recall v4.0] 全文检索初始化失败（不影响核心功能）: {e}")
        
        # 4. Phase 3 / v7.0 C-1: 十一层检索器（默认启用，不再受环境变量门控）
        # ElevenLayerRetriever 始终作为默认检索器，如初始化失败自动回退到 EightLayerRetriever
        self._init_eleven_layer_retriever()
        
        # 5. Phase 2: 预算管理器（用于控制 LLM 成本）
        self._init_budget_manager()
        
        # 6. Phase 2: 智能抽取器（替换默认的 EntityExtractor）
        self._init_smart_extractor()
        
        # 7. Phase 2: 三阶段去重器（用于实体/记忆去重）
        self._init_three_stage_deduplicator()
        
        # 8. Phase 3.5: 图查询规划器（用于优化多跳查询）
        self._init_query_planner()
        
        # 9. Phase 3.5: 社区检测器（用于发现实体群组）
        self._init_community_detector()
    
    def _init_backend_factory(self):
        """v7.0 B-1: 初始化 Backend Abstraction Layer 后端工厂
        
        BackendFactory 自动检测可用外部服务（Qdrant/PG/Nebula/ES）,
        并选择最高可用层级:
        - Lite: 纯 SQLite（默认，无需外部服务）
        - Standard: SQLite + Qdrant
        - Scale: PostgreSQL + Qdrant + Elasticsearch
        - Ultra: PostgreSQL + Qdrant + NebulaGraph + Elasticsearch
        
        创建的后端实例与传统索引层并行运行（dual-write），
        确保向后兼容的同时逐步替代 JSON 文件存储。
        """
        try:
            vector_dim = 384  # v7.0.5: 默认匹配本地 embedding 模型维度（paraphrase-multilingual-MiniLM-L12-v2）
            if self.embedding_backend:
                dim_attr = getattr(self.embedding_backend, 'dimension', None)
                if dim_attr is not None:
                    vector_dim = dim_attr() if callable(dim_attr) else dim_attr
                elif hasattr(self.embedding_backend, 'get_dimension'):
                    vector_dim = self.embedding_backend.get_dimension()
            
            db_base = os.path.join(self.data_root, 'data')
            self._backend_factory = BackendFactory(vector_dimension=vector_dim)
            self._storage_backend = self._backend_factory.create_storage_backend(
                db_path=os.path.join(db_base, 'memories.db')
            )
            self._vector_backend = self._backend_factory.create_vector_backend(
                db_path=os.path.join(db_base, 'vectors.db')
            )
            self._text_search_backend = self._backend_factory.create_text_search_backend(
                db_path=os.path.join(db_base, 'fts.db')
            )
            _safe_print(f"[Recall v7.0] BackendFactory 已初始化 (tier={self._backend_factory.tier.value})")
        except Exception as e:
            self._backend_factory = None
            self._storage_backend = None
            self._vector_backend = None
            self._text_search_backend = None
            _safe_print(f"[Recall v7.0] BackendFactory 初始化失败（回退到传统模式）: {e}")
    
    def _init_processors(self):
        """v7.0: 初始化时间意图解析器、事件关联器、主题聚类器
        
        这三个处理器在 add() 流程中被调用：
        - TimeIntentParser: 解析文本中的时间意图，增强时态检索
        - EventLinker: 自动将新事件与已有事件建立因果/时序关系
        - TopicCluster: 提取主题标签，支持按主题搜索
        """
        # 1. 时间意图解析器
        try:
            from .processor import TimeIntentParser
            self._time_intent_parser = TimeIntentParser(llm_client=self.llm_client)
            _safe_print("[Recall v7.0] TimeIntentParser 已初始化")
        except Exception as e:
            self._time_intent_parser = None
            _safe_print(f"[Recall v7.0] TimeIntentParser 初始化失败: {e}")
        
        # 2. 事件关联器
        try:
            from .processor import EventLinker
            self._event_linker = EventLinker()
            _safe_print("[Recall v7.0] EventLinker 已初始化")
        except Exception as e:
            self._event_linker = None
            _safe_print(f"[Recall v7.0] EventLinker 初始化失败: {e}")
        
        # 3. 主题聚类器
        try:
            from .processor import TopicCluster
            self._topic_cluster = TopicCluster(
                data_path=os.path.join(self.data_root, 'data'),
                llm_client=self.llm_client
            )
            _safe_print("[Recall v7.0] TopicCluster 已初始化")
        except Exception as e:
            self._topic_cluster = None
            _safe_print(f"[Recall v7.0] TopicCluster 初始化失败: {e}")

        # 4. 实体消歧器 (v7.0.1)
        try:
            from .processor import EntityResolver
            self._entity_resolver = EntityResolver(
                data_path=os.path.join(self.data_root, 'data')
            )
            _safe_print("[Recall v7.0.1] EntityResolver 已初始化")
        except Exception as e:
            self._entity_resolver = None
            _safe_print(f"[Recall v7.0.1] EntityResolver 初始化失败: {e}")
    
    def _init_query_planner(self):
        """初始化图查询规划器 (Phase 3.5)
        
        用于优化多跳图查询：
        - 索引优先 - 有索引的字段优先使用索引
        - 早期过滤 - 尽早减少候选集
        - 路径缓存 - 缓存常见路径模式
        """
        self.query_planner = None
        
        # 只有当时态图启用时才初始化
        if not self.temporal_graph:
            return
        
        query_planner_enabled = self.recall_config.query_planner_enabled
        if query_planner_enabled:
            try:
                from .graph import QueryPlanner
                self.query_planner = QueryPlanner(self.temporal_graph)
                _safe_print("[Recall v4.0 Phase 3.5] 图查询规划器已启用")
            except Exception as e:
                _safe_print(f"[Recall v4.0] 图查询规划器初始化失败（不影响核心功能）: {e}")
    
    def _init_community_detector(self):
        """初始化社区检测器 (Phase 3.5)
        
        用于发现图中的实体群组：
        - Louvain: 最常用，适合大规模图
        - Label Propagation: 快速，适合动态图
        - Connected Components: 基础连通分量
        
        后端选择策略（确保数据一致性）：
        1. 如果统一图谱启用了 Kuzu，使用相同的 Kuzu 后端
        2. 否则使用统一图谱的 legacy 适配器
        
        注意：knowledge_graph 和 temporal_graph 现在是同一个 TemporalKnowledgeGraph 实例
        """
        self.community_detector = None
        
        community_enabled = self.recall_config.community_detection_enabled
        if community_enabled:
            try:
                from .graph import CommunityDetector
                from .graph.backends import create_graph_backend
                
                backend = None
                backend_type = 'unified_graph'
                
                # 优先使用统一图谱的 Kuzu 后端（确保数据一致性）
                if self._unified_graph and hasattr(self._unified_graph, 'is_kuzu_enabled'):
                    if self._unified_graph.is_kuzu_enabled:
                        backend = self._unified_graph.kuzu_backend
                        backend_type = 'kuzu (shared with unified_graph)'
                
                # 如果没有 Kuzu，使用 legacy 适配器
                if backend is None:
                    backend = create_graph_backend(
                        data_path=os.path.join(self.data_root, 'data'),
                        backend='legacy',
                        existing_knowledge_graph=self._unified_graph
                    )
                
                algorithm = self.recall_config.community_detection_algorithm
                min_size = self.recall_config.community_min_size
                
                self.community_detector = CommunityDetector(
                    graph_backend=backend,
                    algorithm=algorithm,
                    min_community_size=min_size
                )
                _safe_print(f"[Recall v4.0 Phase 3.5] 社区检测器已启用 (算法: {algorithm}, 后端: {backend_type})")
            except Exception as e:
                _safe_print(f"[Recall v4.0] 社区检测器初始化失败（不影响核心功能）: {e}")
        
        # 10. Recall 4.1: LLM 关系提取器
        self._init_llm_relation_extractor()
        
        # 11. Recall 4.1: Episode 追溯
        self._init_episode_store()
        
        # 12. Recall 4.1: 实体摘要生成器
        self._init_entity_summarizer()
        
        # 13. v4.2: 统一 LLM 分析器（合并矛盾检测 + 关系提取）
        self._init_unified_analyzer()
    
    def _init_llm_relation_extractor(self):
        """初始化 LLM 关系提取器 (Recall 4.1)
        
        用于增强关系提取能力，支持：
        - RULES 模式：纯规则（零成本）
        - ADAPTIVE 模式：规则 + LLM 精炼
        - LLM 模式：纯 LLM（最高质量）
        """
        self._llm_relation_extractor = None
        
        llm_relation_mode = self.recall_config.llm_relation_mode.lower()
        if llm_relation_mode != 'rules' and self.llm_client:
            try:
                from .graph.llm_relation_extractor import (
                    LLMRelationExtractor, LLMRelationExtractorConfig, RelationExtractionMode
                )
                mode_map = {
                    'adaptive': RelationExtractionMode.ADAPTIVE,
                    'llm': RelationExtractionMode.LLM,
                }
                
                complexity_threshold = self.recall_config.llm_relation_complexity_threshold
                enable_temporal = self.recall_config.llm_relation_enable_temporal
                enable_fact = self.recall_config.llm_relation_enable_fact_description
                
                self._llm_relation_extractor = LLMRelationExtractor(
                    llm_client=self.llm_client,
                    budget_manager=self.budget_manager if hasattr(self, 'budget_manager') else None,
                    entity_extractor=self.entity_extractor,
                    config=LLMRelationExtractorConfig(
                        mode=mode_map.get(llm_relation_mode, RelationExtractionMode.RULES),
                        complexity_threshold=complexity_threshold,
                        enable_temporal=enable_temporal,
                        enable_fact_description=enable_fact
                    )
                )
                _safe_print(f"[Recall v4.1] LLM 关系提取器已启用 (模式: {llm_relation_mode})")
            except ImportError:
                pass  # 模块不存在时静默跳过
            except Exception as e:
                _safe_print(f"[Recall v4.1] LLM 关系提取器初始化失败: {e}")
    
    def _init_episode_store(self):
        """初始化 Episode 存储 (Recall 4.1)
        
        用于追溯记忆来源：
        - Episode -> Memory 关联
        - Episode -> Entity 关联
        - Episode -> Relation 关联
        """
        self.episode_store = None
        self._episode_tracking_enabled = False
        
        episode_enabled = self.recall_config.episode_tracking_enabled
        if episode_enabled:
            try:
                from .storage.episode_store import EpisodeStore
                self.episode_store = EpisodeStore(
                    data_path=os.path.join(self.data_root, 'data')
                )
                self._episode_tracking_enabled = True
                _safe_print("[Recall v4.1] Episode 追溯已启用")
            except ImportError:
                pass  # 模块不存在时静默跳过
            except Exception as e:
                _safe_print(f"[Recall v4.1] Episode 存储初始化失败: {e}")
    
    def _init_entity_summarizer(self):
        """初始化实体摘要生成器 (Recall 4.1)
        
        为实体自动生成摘要，总结实体的所有已知信息
        """
        self.entity_summarizer = None
        self._entity_summary_enabled = False
        self._entity_summary_min_facts = 5
        
        summary_enabled = self.recall_config.entity_summary_enabled
        if summary_enabled:
            try:
                from .processor.entity_summarizer import EntitySummarizer
                self.entity_summarizer = EntitySummarizer(
                    llm_client=self.llm_client
                )
                self._entity_summary_enabled = True
                self._entity_summary_min_facts = self.recall_config.entity_summary_min_facts
                _safe_print("[Recall v4.1] 实体摘要生成已启用")
            except ImportError:
                pass  # 模块不存在时静默跳过
            except Exception as e:
                _safe_print(f"[Recall v4.1] 实体摘要生成器初始化失败: {e}")
    
    def _init_unified_analyzer(self):
        """初始化统一 LLM 分析器 (v4.2 性能优化)
        
        通过一次 LLM 调用完成多个分析任务：
        - 矛盾检测
        - 关系提取
        - 实体摘要（可选）
        """
        self.unified_analyzer = None
        
        unified_analyzer_enabled = self.recall_config.unified_analyzer_enabled
        if unified_analyzer_enabled and self.llm_client:
            try:
                from .processor.unified_analyzer import UnifiedAnalyzer
                self.unified_analyzer = UnifiedAnalyzer(
                    llm_client=self.llm_client,
                    enabled=True,
                    prompt_manager=self.prompt_manager
                )
                _safe_print("[Recall v4.2] 统一 LLM 分析器已启用")
            except ImportError:
                pass  # 模块不存在时静默跳过
            except Exception as e:
                _safe_print(f"[Recall v4.2] 统一分析器初始化失败（回退到独立模块）: {e}")
    
    def _maybe_update_entity_summary(self, entity_name: str):
        """检查并更新实体摘要（如果需要）- Recall 4.1
        
        只有当实体的事实数量超过阈值时才会触发摘要生成。
        """
        if not self._entity_summary_enabled or not self.entity_summarizer:
            return
        
        # 获取实体
        if not self._entity_index:
            return
        
        entity = self._entity_index.get_entity(entity_name)
        if not entity:
            return
        
        # 检查是否需要更新（事实数量超过阈值且没有摘要）
        fact_count = len(entity.turn_references)
        if fact_count < self._entity_summary_min_facts:
            return
        
        # 如果已有摘要，跳过（可考虑定期更新策略）
        if entity.summary:
            return
        
        try:
            # 获取关系
            relations = []
            if self.knowledge_graph:
                kg_relations = self.knowledge_graph.get_relations_for_entity(entity_name)
                relations = [(r.source_id, r.relation_type, r.target_id) for r in kg_relations]
            
            # 获取事实（从记忆中提取）
            facts = []
            # v7.0.4: 修复 — 使用 O(1) _memory_index 查找替代 O(n) 遍历，且不再硬编码 "default" scope
            for memory_id in entity.turn_references[:10]:  # 限制数量
                content = self._get_memory_content_by_id(memory_id)
                if content:
                    facts.append(content[:100])
                    continue
                # 回退：遍历所有 scope
                found = False
                for uid in self.storage.list_users():
                    scope = self.storage.get_scope(uid)
                    if hasattr(scope, '_memory_index') and memory_id in scope._memory_index:
                        mem = scope._memory_index[memory_id]
                        facts.append(mem.get('content', '')[:100])
                        found = True
                        break
                if not found:
                    # v7.0.5: 修复缩进 — get_all 搜索应在遍历完所有 scope 的 _memory_index 后执行
                    for uid in self.storage.list_users():
                        scope = self.storage.get_scope(uid)
                        for mem in scope.get_all(limit=200):
                            if mem.get('metadata', {}).get('id') == memory_id:
                                facts.append(mem.get('content', '')[:100])
                                found = True
                                break
                        if found:
                            break
            
            if not facts:
                return
            
            # 生成摘要
            summary_result = self.entity_summarizer.generate(
                entity_name=entity_name,
                facts=facts,
                relations=relations
            )
            
            # 更新 EntityIndex
            from datetime import datetime
            self._entity_index.update_entity_fields(
                entity_name=entity_name,
                summary=summary_result.summary,
                last_summary_update=datetime.now().isoformat()
            )
            _safe_print(f"[Recall v4.1] 实体摘要已更新: {entity_name}")
        except Exception as e:
            _safe_print(f"[Recall v4.1] 摘要生成失败 {entity_name}: {e}")

    def _init_budget_manager(self):
        """初始化预算管理器 (Phase 2)
        
        用于控制 LLM API 调用成本，支持：
        - 每日/每小时预算限制
        - 预算预警
        - 超支时自动降级
        """
        self.budget_manager = None
        
        # 检查是否配置了预算限制
        daily_limit = self.recall_config.budget_daily_limit
        hourly_limit = self.recall_config.budget_hourly_limit
        
        # 只有配置了预算才启用
        if daily_limit > 0 or hourly_limit > 0:
            try:
                from .utils.budget_manager import BudgetManager, BudgetConfig
                
                reserve = self.recall_config.budget_reserve
                alert_threshold = self.recall_config.budget_alert_threshold
                
                config = BudgetConfig(
                    daily_budget=daily_limit,
                    hourly_budget=hourly_limit,
                    warning_threshold=alert_threshold,
                    auto_degrade=True  # 超支时自动降级到本地模式
                )
                
                self.budget_manager = BudgetManager(
                    data_path=os.path.join(self.data_root, 'data'),
                    config=config
                )
                _safe_print(f"[Recall v4.0] 预算管理器已启用 (每日=${daily_limit}, 每小时=${hourly_limit})")
            except Exception as e:
                _safe_print(f"[Recall v4.0] 预算管理器初始化失败（不影响核心功能）: {e}")
    
    def _init_smart_extractor(self):
        """初始化智能抽取器 (Phase 2)
        
        替换默认的 EntityExtractor，支持：
        - RULES 模式：纯规则抽取（零 LLM 成本）
        - ADAPTIVE 模式：简单文本用规则，复杂文本用 LLM
        - LLM 模式：全部使用 LLM（最高质量）
        """
        self.smart_extractor = None
        self.entity_schema_registry = None  # Recall 4.1
        
        # 读取配置
        mode_str = self.recall_config.smart_extractor_mode.upper()
        
        try:
            from .processor.smart_extractor import SmartExtractor, SmartExtractorConfig, ExtractionMode
            
            # 模式映射
            mode_map = {
                'RULES': ExtractionMode.RULES,
                'ADAPTIVE': ExtractionMode.ADAPTIVE,
                'LLM': ExtractionMode.LLM,
                # 向后兼容
                'LOCAL': ExtractionMode.RULES,
                'HYBRID': ExtractionMode.ADAPTIVE,
                'LLM_FULL': ExtractionMode.LLM,
            }
            mode = mode_map.get(mode_str, ExtractionMode.RULES)
            
            complexity_threshold = self.recall_config.smart_extractor_complexity_threshold
            enable_temporal = self.recall_config.smart_extractor_enable_temporal
            
            # 构建配置对象
            config = SmartExtractorConfig(
                mode=mode,
                complexity_threshold=complexity_threshold,
                enable_temporal_detection=enable_temporal
            )
            
            # === Recall 4.1: 初始化 Entity Schema Registry ===
            try:
                from .models.entity_schema import EntitySchemaRegistry
                self.entity_schema_registry = EntitySchemaRegistry(
                    data_path=self.data_root
                )
            except ImportError:
                pass  # 模块不存在时跳过
            
            self.smart_extractor = SmartExtractor(
                config=config,
                llm_client=self.llm_client if mode != ExtractionMode.RULES else None,
                budget_manager=self.budget_manager,
                entity_schema_registry=self.entity_schema_registry,  # Recall 4.1
                prompt_manager=self.prompt_manager  # v7.0
            )
            _safe_print(f"[Recall v4.0] 智能抽取器已启用 (模式: {mode.value})")
        except Exception as e:
            _safe_print(f"[Recall v4.0] 智能抽取器初始化失败（使用默认抽取器）: {e}")
    
    def _init_three_stage_deduplicator(self):
        """初始化三阶段去重器 (Phase 2)
        
        用于实体和记忆的智能去重：
        - 阶段1: MinHash + LSH（快速粗筛）
        - 阶段2: Embedding 语义相似度
        - 阶段3: LLM 确认（可选，用于边界情况）
        """
        self.deduplicator = None
        
        try:
            from .processor.three_stage_deduplicator import ThreeStageDeduplicator, DedupConfig
            
            # 读取配置（默认阈值较高以避免误判）
            jaccard_threshold = self.recall_config.dedup_jaccard_threshold
            semantic_high = self.recall_config.dedup_semantic_threshold
            semantic_low = self.recall_config.dedup_semantic_low_threshold
            llm_enabled = self.recall_config.dedup_llm_enabled
            
            # 构建配置对象
            config = DedupConfig(
                jaccard_threshold=jaccard_threshold,
                semantic_threshold=semantic_high,
                semantic_low_threshold=semantic_low,
                llm_enabled=llm_enabled
            )
            
            self.deduplicator = ThreeStageDeduplicator(
                config=config,
                embedding_backend=self.embedding_backend,
                llm_client=self.llm_client if llm_enabled else None,
                budget_manager=self.budget_manager,
                prompt_manager=self.prompt_manager  # v7.0
            )
            _safe_print(f"[Recall v4.0] 三阶段去重器已启用 (Jaccard={jaccard_threshold}, Semantic={semantic_low}-{semantic_high}, LLM={llm_enabled})")
        except Exception as e:
            _safe_print(f"[Recall v4.0] 三阶段去重器初始化失败（使用默认去重）: {e}")
    
    def _init_eleven_layer_retriever(self):
        """初始化 Phase 3 十一层检索器
        
        替换默认的 EightLayerRetriever，启用：
        - L2: 时态过滤（需要 temporal_graph）
        - L5: 图遍历扩展（需要 temporal_graph）
        - L10: CrossEncoder 精排（可选）
        - L11: LLM 过滤（可选）
        
        设计原则：
        1. 通过环境变量 ELEVEN_LAYER_RETRIEVER_ENABLED=true 启用
        2. 即使部分依赖不可用也能降级运行
        3. 不影响现有 API 接口
        """
        try:
            # 构建检索配置
            config = RetrievalConfig.from_env()
            
            # 检查 CrossEncoder 是否需要加载
            cross_encoder = None
            if config.l10_enabled:
                cross_encoder = self._load_cross_encoder()
            
            # 获取时态索引（如果 temporal_graph 启用）
            temporal_index = None
            if self.temporal_graph and hasattr(self.temporal_graph, '_temporal_index'):
                temporal_index = self.temporal_graph._temporal_index
            
            # v7.0 C-2: 使用活跃向量索引（可能是 IVF）
            active_vector_index = self.get_active_vector_index()
            
            # 创建 ElevenLayerRetriever
            self.retriever = ElevenLayerRetriever(
                # 现有依赖（与 EightLayerRetriever 相同）
                bloom_filter=self._ngram_index.bloom_filter if self._ngram_index else None,
                inverted_index=self._inverted_index,
                entity_index=self._entity_index,
                ngram_index=self._ngram_index,
                vector_index=active_vector_index,
                llm_client=self.llm_client,
                content_store=self._get_memory_content_by_id,
                # Phase 3 新增依赖
                temporal_index=temporal_index,
                knowledge_graph=self.temporal_graph,
                cross_encoder=cross_encoder,
                # Phase 3.6: 传入 embedding_backend（用于 VectorIndexIVF）
                embedding_backend=self.embedding_backend,
                # v7.0: QueryPlanner（BFS 查询规划+缓存优化）
                query_planner=getattr(self, 'query_planner', None),
                # v7.0: 重排序器配置（从 RecallConfig 传入）
                reranker_backend=self.recall_config.reranker_backend,
                reranker_api_key=self.recall_config.cohere_api_key,
                reranker_model=self.recall_config.reranker_model,
                # v7.0.1: BM25 全文检索 + 权重
                fulltext_index=getattr(self, 'fulltext_index', None),
                fulltext_weight=getattr(self, '_fulltext_weight', 0.3),
                # 配置
                config=config
            )
            
            # 记录启用状态
            layers_status = []
            # Phase 3.6 状态
            if config.parallel_recall_enabled:
                layers_status.append("Phase3.6:并行三路召回")
            if config.l2_enabled and temporal_index:
                layers_status.append("L2:时态过滤")
            if config.l5_enabled and self.temporal_graph:
                layers_status.append("L5:图遍历")
            if config.l10_enabled and cross_encoder:
                layers_status.append("L10:CrossEncoder")
            if config.l11_enabled:
                layers_status.append("L11:LLM过滤")
            
            status_str = ", ".join(layers_status) if layers_status else "基础模式"
            _safe_print(f"[Recall v4.0 Phase 3] 十一层检索器已启用 ({status_str})")
            
        except Exception as e:
            _safe_print(f"[Recall v4.0 Phase 3] 十一层检索器初始化失败，回退到八层检索器: {e}")
            # 失败时不修改 self.retriever，保持 EightLayerRetriever
    
    def _load_cross_encoder(self):
        """按需加载 CrossEncoder 模型
        
        Returns:
            CrossEncoder 模型实例，或 None（如果加载失败）
        """
        try:
            from sentence_transformers import CrossEncoder
            model_name = self.recall_config.retrieval_l10_cross_encoder_model
            return CrossEncoder(model_name)
        except ImportError:
            _safe_print("[Recall v4.0 Phase 3] sentence-transformers 未安装，CrossEncoder 不可用")
            return None
        except Exception as e:
            _safe_print(f"[Recall v4.0 Phase 3] CrossEncoder 加载失败: {e}")
            return None
    
    def _init_parallel_retriever(self) -> Optional[ParallelRetriever]:
        """v7.0 C-3: 初始化并行检索器并注册检索源
        
        ParallelRetriever 提供独立的并行多源检索框架，
        可用于自定义检索流程。注册 4 种检索源：
        - VECTOR: 语义向量检索
        - KEYWORD: 关键词倒排索引检索
        - ENTITY: 实体索引检索
        - GRAPH: 知识图谱遍历检索
        
        Returns:
            ParallelRetriever 实例，或 None（如果初始化失败）
        """
        try:
            pr = ParallelRetriever(
                max_workers=self.recall_config.parallel_retriever_workers,
                default_timeout=self.recall_config.parallel_retriever_timeout
            )
            
            # 注册向量检索源
            active_vi = self.get_active_vector_index()
            if active_vi and getattr(active_vi, 'enabled', True):
                def _vector_search(query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
                    top_k = params.get('top_k', 20)
                    if hasattr(active_vi, 'encode'):
                        results = active_vi.search(query, top_k=top_k)
                    elif self.embedding_backend:
                        emb = self.embedding_backend.encode(query)
                        results = active_vi.search(emb, top_k=top_k)
                    else:
                        return []
                    return [{'id': doc_id, 'score': score} for doc_id, score in results]
                pr.register(RetrievalSource.VECTOR, _vector_search)
            
            # 注册关键词检索源
            if self._inverted_index:
                def _keyword_search(query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
                    keywords = params.get('keywords', [])
                    if not keywords:
                        keywords = self.entity_extractor.extract_keywords(query)
                    results = []
                    for kw in keywords:
                        # v7.0.5: 修复 — InvertedIndex.search() 返回 List[str] 且不接受 top_k
                        for doc_id in self._inverted_index.search(kw):
                            results.append({'id': doc_id, 'score': 1.0})
                    return results
                pr.register(RetrievalSource.KEYWORD, _keyword_search)
            
            # 注册实体检索源
            if self._entity_index:
                def _entity_search(query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
                    entities = params.get('entities', [])
                    if not entities:
                        entities = [e.name for e in self.entity_extractor.extract(query)]
                    results = []
                    for ent in entities:
                        # v7.0.5: 修复 — EntityIndex.search() 返回 List[IndexedEntity] 而非 tuple
                        for indexed_entity in self._entity_index.search(ent):
                            for ref_id in indexed_entity.turn_references:
                                results.append({'id': ref_id, 'score': indexed_entity.confidence})
                    return results
                pr.register(RetrievalSource.ENTITY, _entity_search)
            
            # 注册图谱检索源
            if self.knowledge_graph:
                def _graph_search(query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
                    entities = params.get('entities', [])
                    if not entities:
                        entities = [e.name for e in self.entity_extractor.extract(query)]
                    results = []
                    for ent in entities:
                        try:
                            # v7.0.5: 修复 — 使用 get_neighbors() 替代不存在的 get_related_entities()
                            neighbors = self.knowledge_graph.get_neighbors(ent, direction='both')
                            for neighbor_info in neighbors[:10]:
                                neighbor_name = neighbor_info[0] if isinstance(neighbor_info, (list, tuple)) else str(neighbor_info)
                                if self._entity_index:
                                    for indexed_entity in self._entity_index.search(neighbor_name):
                                        for ref_id in indexed_entity.turn_references:
                                            results.append({'id': ref_id, 'score': indexed_entity.confidence * 0.8})
                        except Exception:
                            pass
                    return results
                pr.register(RetrievalSource.GRAPH, _graph_search)
            
            source_count = len(pr.retrievers)
            _safe_print(f"[Recall v7.0] ParallelRetriever 已初始化 ({source_count} 个检索源已注册)")
            return pr
            
        except Exception as e:
            logger.warning(f"[Recall v7.0] ParallelRetriever 初始化失败（不影响核心功能）: {e}")
            return None
    
    def search_parallel(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 10,
        sources: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """v7.0 C-3: 使用 ParallelRetriever 执行并行多源检索
        
        Args:
            query: 搜索查询
            user_id: 用户ID
            top_k: 返回数量
            sources: 要使用的检索源列表（默认全部），可选值:
                     'vector', 'keyword', 'entity', 'graph'
            entities: 预提取的实体列表（可选）
            keywords: 预提取的关键词列表（可选）
        
        Returns:
            List[SearchResult]: 搜索结果
        """
        if not self.parallel_retriever:
            _safe_print("[Recall v7.0] ParallelRetriever 不可用，回退到默认搜索")
            return self.search(query, user_id=user_id, top_k=top_k)
        
        # 构建检索任务
        source_map = {
            'vector': RetrievalSource.VECTOR,
            'keyword': RetrievalSource.KEYWORD,
            'entity': RetrievalSource.ENTITY,
            'graph': RetrievalSource.GRAPH,
        }
        
        available_sources = sources or list(source_map.keys())
        tasks = []
        for src_name in available_sources:
            src = source_map.get(src_name)
            if src and src in self.parallel_retriever.retrievers:
                params = {'top_k': top_k * 2}
                if entities:
                    params['entities'] = entities
                if keywords:
                    params['keywords'] = keywords
                tasks.append(RetrievalTask(
                    source=src,
                    query=query,
                    params=params,
                    weight=1.0
                ))
        
        if not tasks:
            return []
        
        # 执行并行检索
        source_results = self.parallel_retriever.retrieve_parallel(tasks)
        merged = self.parallel_retriever.merge_results(source_results, tasks, top_k=top_k * 3)
        
        # 过滤为当前用户的记忆
        scope = self.storage.get_scope(user_id)
        user_memory_ids = set()
        for mem in scope._memories:
            mem_id = mem.get('metadata', {}).get('id', '')
            if mem_id:
                user_memory_ids.add(mem_id)
        
        results = []
        for item in merged:
            item_id = item.get('id', '')
            if item_id in user_memory_ids:
                content = self._get_memory_content_by_id(item_id) or ''
                results.append(SearchResult(
                    id=item_id,
                    content=content,
                    score=item.get('score', 0.0),
                    metadata={},
                    entities=[]
                ))
                if len(results) >= top_k:
                    break
        
        return results
    
    def _check_and_rebuild_index(self):
        """检查并为已有伏笔/条件补建 VectorIndex 索引
        
        使用标记文件 .index_rebuilt_v3 来判断是否已经迁移过。
        v3 版本支持索引归档文件 (archive/*.jsonl)。
        如果没有 VectorIndex 或已禁用，则跳过。
        """
        if not self._vector_index or not self._vector_index.enabled:
            return
        
        marker_file = os.path.join(self.data_root, 'data', '.index_rebuilt_v3')
        if os.path.exists(marker_file):
            return  # 已经迁移过
        
        import glob
        logger.info("[Recall] 检测到首次升级或版本更新，开始为已有伏笔/条件补建 VectorIndex 索引...")
        
        indexed_count = 0
        archived_count = 0
        
        # 1. 索引所有伏笔和条件（包括活跃的和归档的）
        data_path = os.path.join(self.data_root, 'data')
        if os.path.exists(data_path):
            for user_id in os.listdir(data_path):
                user_path = os.path.join(data_path, user_id)
                if not os.path.isdir(user_path) or user_id.startswith('.'):
                    continue
                for character_id in os.listdir(user_path):
                    char_path = os.path.join(user_path, character_id)
                    if not os.path.isdir(char_path):
                        continue
                    
                    # 1.1 索引活跃伏笔 (foreshadowings.json)
                    fsh_file = os.path.join(char_path, 'foreshadowings.json')
                    if os.path.exists(fsh_file):
                        try:
                            import json
                            with open(fsh_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            foreshadowings = data.get('foreshadowings', {})
                            for fsh_id, fsh in foreshadowings.items():
                                content = fsh.get('content', '')
                                if content:
                                    # 注意：fsh_id 已经是 fsh_{counter}_{timestamp} 格式
                                    # 不需要再加 fsh_ 前缀，与 plant_foreshadowing 保持一致
                                    doc_id = f"{user_id}_{character_id}_{fsh_id}"
                                    self._vector_index.add_text(doc_id, content)
                                    indexed_count += 1
                        except Exception as e:
                            logger.warning(f"[Recall] 索引伏笔失败 ({user_id}/{character_id}): {e}")
                    
                    # 1.2 索引活跃条件 (contexts.json)
                    ctx_file = os.path.join(char_path, 'contexts.json')
                    if os.path.exists(ctx_file):
                        try:
                            import json
                            with open(ctx_file, 'r', encoding='utf-8') as f:
                                contexts = json.load(f)
                            for ctx in contexts:
                                if ctx.get('is_active', True):
                                    content = ctx.get('content', '')
                                    ctx_id = ctx.get('id', '')
                                    if content and ctx_id:
                                        doc_id = f"ctx_{user_id}_{character_id}_{ctx_id}"
                                        self._vector_index.add_text(doc_id, content)
                                        indexed_count += 1
                        except Exception as e:
                            logger.warning(f"[Recall] 索引条件失败 ({user_id}/{character_id}): {e}")
                    
                    # 1.3 索引归档伏笔 (archive/foreshadowings*.jsonl)
                    archive_dir = os.path.join(char_path, 'archive')
                    if os.path.isdir(archive_dir):
                        # 匹配 foreshadowings.jsonl 和 foreshadowings_001.jsonl 等
                        fsh_archive_files = glob.glob(os.path.join(archive_dir, 'foreshadowings*.jsonl'))
                        for archive_file in fsh_archive_files:
                            try:
                                with open(archive_file, 'r', encoding='utf-8') as f:
                                    for line in f:
                                        line = line.strip()
                                        if not line:
                                            continue
                                        fsh = json.loads(line)
                                        fsh_id = fsh.get('id', '')
                                        content = fsh.get('content', '')
                                        if content and fsh_id:
                                            doc_id = f"{user_id}_{character_id}_{fsh_id}"
                                            self._vector_index.add_text(doc_id, content)
                                            archived_count += 1
                            except Exception as e:
                                logger.warning(f"[Recall] 索引归档伏笔失败 ({archive_file}): {e}")
                        
                        # 1.4 索引归档条件 (archive/contexts*.jsonl)
                        ctx_archive_files = glob.glob(os.path.join(archive_dir, 'contexts*.jsonl'))
                        for archive_file in ctx_archive_files:
                            try:
                                with open(archive_file, 'r', encoding='utf-8') as f:
                                    for line in f:
                                        line = line.strip()
                                        if not line:
                                            continue
                                        ctx = json.loads(line)
                                        ctx_id = ctx.get('id', '')
                                        content = ctx.get('content', '')
                                        if content and ctx_id:
                                            doc_id = f"ctx_{user_id}_{character_id}_{ctx_id}"
                                            self._vector_index.add_text(doc_id, content)
                                            archived_count += 1
                            except Exception as e:
                                logger.warning(f"[Recall] 索引归档条件失败 ({archive_file}): {e}")
        
        # 创建标记文件
        os.makedirs(os.path.dirname(marker_file), exist_ok=True)
        total_count = indexed_count + archived_count
        with open(marker_file, 'w') as f:
            f.write(f"indexed_at: {time.time()}\n")
            f.write(f"active_count: {indexed_count}\n")
            f.write(f"archived_count: {archived_count}\n")
            f.write(f"total_count: {total_count}\n")
        
        logger.info(f"[Recall] VectorIndex 索引补建完成，共索引 {total_count} 条记录 (活跃: {indexed_count}, 归档: {archived_count})")
        
        return total_count

    def rebuild_foreshadow_index(self, force: bool = False) -> int:
        """手动重建伏笔/条件的 VectorIndex 索引
        
        为所有伏笔和条件重建语义索引。通常不需要手动调用，
        系统会在首次升级时自动重建。
        
        使用场景：
        - 索引数据损坏需要重建
        - 手动导入了数据文件
        - 从备份恢复后需要重建索引
        
        Args:
            force: 是否强制重建（删除标记文件后重建）
            
        Returns:
            int: 索引的记录数量
        """
        if force:
            # 删除 v3 标记文件（当前版本）
            marker_file_v3 = os.path.join(self.data_root, 'data', '.index_rebuilt_v3')
            if os.path.exists(marker_file_v3):
                os.remove(marker_file_v3)
            # 兼容：也删除旧版本标记文件
            marker_file_v2 = os.path.join(self.data_root, 'data', '.index_rebuilt_v2')
            if os.path.exists(marker_file_v2):
                os.remove(marker_file_v2)
        
        return self._check_and_rebuild_index() or 0

    def _get_recent_memories_for_analysis(self, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """获取最近的记忆用于伏笔分析
        
        这是 ForeshadowingAnalyzer 的 memory_provider 回调函数。
        从已保存的记忆中获取对话，确保分析基于已持久化的数据。
        
        Args:
            user_id: 用户/角色ID
            limit: 最大返回数量
            
        Returns:
            List[Dict]: 记忆列表，按时间排序
        """
        try:
            scope = self.storage.get_scope(user_id)
            memories = scope.get_all(limit=limit)
            
            # 按时间戳排序（旧 -> 新）
            memories.sort(key=lambda m: m.get('metadata', {}).get('timestamp', 0))
            
            return memories
        except Exception as e:
            _safe_print(f"[Recall] 获取记忆失败: {e}")
            return []
    
    def _get_memory_content_by_id(self, memory_id: str) -> Optional[str]:
        """通过 ID 获取记忆内容（供检索器回调）
        
        查找顺序：
        1. MultiTenantStorage O(1) 索引查找（最快）
        2. VolumeManager 存档（确保100%不遗忘）
        3. N-gram 索引的原文缓存（兜底）
        """
        # 1. 先从 MultiTenantStorage 的 O(1) 索引中查找（A11 优化）
        for scope_key, scope in self.storage._scopes.items():
            content = scope.get_content_by_id(memory_id)
            if content is not None:
                return content
        
        # 2. 从 VolumeManager 存档中查找（确保100%不遗忘）
        if hasattr(self, 'volume_manager') and self.volume_manager:
            turn_data = self.volume_manager.get_turn_by_memory_id(memory_id)
            if turn_data:
                return turn_data.get('content', '')
        
        # 3. 从 N-gram 索引的原文缓存中查找（兜底）
        if self._ngram_index and hasattr(self._ngram_index, 'get_raw_content'):
            content = self._ngram_index.get_raw_content(memory_id)
            if content:
                return content
        
        return None
    
    def _init_indexes(self):
        """初始化索引"""
        index_path = os.path.join(self.data_root, 'index')
        os.makedirs(index_path, exist_ok=True)
        
        self._entity_index = EntityIndex(data_path=self.data_root)
        self._inverted_index = InvertedIndex(data_path=self.data_root)
        self._vector_index = VectorIndex(
            data_path=self.data_root,
            embedding_config=self.embedding_config
        )
        # N-gram 索引（支持持久化）
        ngram_data_path = os.path.join(self.data_root, 'index', 'ngram')
        self._ngram_index = OptimizedNgramIndex(data_path=ngram_data_path)
        
        # v5.0: 元数据索引（source/tags/category 过滤）
        from .index.metadata_index import MetadataIndex
        self._metadata_index = MetadataIndex(
            data_path=os.path.join(self.data_root, 'indexes')
        )
        
        # v7.0 C-2: VectorIndexIVF 自动切换（检查向量数是否超过阈值）
        self._try_ivf_auto_switch()

    def _on_memories_evicted(self, evicted_ids: list):
        """v7.0.2: ScopedMemory LRU 驱逐回调 — 归档 + 级联清理
        
        当 ScopedMemory 超过 MAX_MEMORIES(5000) 时自动驱逐最旧记忆。
        v7.0.3: 先确保被驱逐记忆已写入 VolumeManager 归档（不遗忘保证），
        然后清理所有索引中的幽灵条目。
        """
        if not evicted_ids:
            return
        evicted_set = set(evicted_ids)
        
        # ===== v7.0.3: 归档保护 — 确保被驱逐数据不会永久丢失 =====
        # 在 add() 流程中已经调用了 volume_manager.append_turn()，
        # 但如果那次调用失败（被 try-except 吞掉），这里做最后的安全网。
        if self.volume_manager:
            try:
                # 从 NgramIndex 获取原文（这里还没清理它）
                for mid in evicted_ids:
                    content = None
                    # 尝试从 ngram_index 获取原文
                    if self._ngram_index and hasattr(self._ngram_index, 'get_raw_content'):
                        content = self._ngram_index.get_raw_content(mid)
                    # 尝试从 retriever 缓存获取
                    if not content and self.retriever and hasattr(self.retriever, '_content_cache'):
                        content = self.retriever._content_cache.get(mid)
                    if content:
                        # 检查 VolumeManager 是否已有此记忆
                        existing = self.volume_manager.get_turn_by_memory_id(mid)
                        if not existing:
                            # v7.0.12: 修复 — 从元数据索引获取实际 user_id，避免跨用户数据泄漏
                            evicted_user_id = 'unknown'
                            if self._metadata_index:
                                try:
                                    meta_entry = self._metadata_index.get(mid)
                                    if meta_entry and isinstance(meta_entry, dict):
                                        evicted_user_id = meta_entry.get('user_id', 'unknown')
                                except Exception:
                                    pass
                            self.volume_manager.append_turn({
                                'memory_id': mid,
                                'user_id': evicted_user_id,
                                'content': content,
                                'entities': [],
                                'keywords': [],
                                'metadata': {'evicted': True},
                                'created_at': __import__('time').time()
                            })
            except Exception as e:
                logger.warning(f"[Recall v7.0.3] 驱逐归档保护失败（数据可能已在 add() 时归档）: {e}")
        
        # ===== 级联清理索引 =====
        try:
            if self._vector_index and hasattr(self._vector_index, 'remove_by_doc_ids'):
                self._vector_index.remove_by_doc_ids(evicted_ids)
        except Exception:
            pass
        try:
            if getattr(self, '_vector_index_ivf', None) and hasattr(self._vector_index_ivf, 'remove'):
                # v7.0.6: 修复 — VectorIndexIVF 没有 remove_by_doc_ids，只有 remove(doc_id)
                for mid in evicted_ids:
                    self._vector_index_ivf.remove(mid)
        except Exception:
            pass
        try:
            if self._inverted_index and hasattr(self._inverted_index, 'remove_by_memory_ids'):
                self._inverted_index.remove_by_memory_ids(evicted_set)
        except Exception:
            pass
        try:
            if self._ngram_index and hasattr(self._ngram_index, 'remove_by_memory_ids'):
                self._ngram_index.remove_by_memory_ids(evicted_set)
        except Exception:
            pass
        try:
            if self.fulltext_index and hasattr(self.fulltext_index, 'remove_by_doc_ids'):
                self.fulltext_index.remove_by_doc_ids(evicted_set)
        except Exception:
            pass
        try:
            if self._entity_index and hasattr(self._entity_index, 'remove_by_turn_references'):
                self._entity_index.remove_by_turn_references(evicted_ids)
        except Exception:
            pass
        try:
            if self._metadata_index:
                self._metadata_index.remove_batch(evicted_set)
        except Exception:
            pass
        try:
            if self.retriever:
                for mid in evicted_ids:
                    if hasattr(self.retriever, '_content_cache') and mid in self.retriever._content_cache:
                        del self.retriever._content_cache[mid]
                    if hasattr(self.retriever, '_metadata_cache') and mid in self.retriever._metadata_cache:
                        del self.retriever._metadata_cache[mid]
                    if hasattr(self.retriever, '_entities_cache') and mid in self.retriever._entities_cache:
                        del self.retriever._entities_cache[mid]
        except Exception:
            pass
        try:
            if getattr(self, '_storage_backend', None):
                for mid in evicted_ids:
                    self._storage_backend.delete(mid)
        except Exception:
            pass
        try:
            if getattr(self, '_vector_backend', None):
                for mid in evicted_ids:
                    self._vector_backend.delete(mid)
        except Exception:
            pass
        try:
            if getattr(self, '_text_search_backend', None):
                for mid in evicted_ids:
                    self._text_search_backend.delete(mid)
        except Exception:
            pass
        # v7.0.8: 以下存储位置之前 _on_memories_evicted 遗漏
        try:
            if self.consolidated_memory is not None and hasattr(self.consolidated_memory, 'remove_by_memory_ids'):
                self.consolidated_memory.remove_by_memory_ids(evicted_ids)
        except Exception:
            pass
        try:
            if self.temporal_graph is not None and hasattr(self.temporal_graph, '_temporal_index'):
                ti = self.temporal_graph._temporal_index
                if ti is not None and hasattr(ti, 'remove'):
                    for mid in evicted_ids:
                        try:
                            ti.remove(mid)
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            if self.context_tracker is not None and hasattr(self.context_tracker, 'invalidate_memory'):
                for mid in evicted_ids:
                    try:
                        self.context_tracker.invalidate_memory(mid)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if self.episode_store is not None and hasattr(self.episode_store, 'remove_memory_references'):
                for mid in evicted_ids:
                    try:
                        self.episode_store.remove_memory_references(mid)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if getattr(self, '_event_linker', None) and hasattr(self._event_linker, 'unlink'):
                for mid in evicted_ids:
                    try:
                        self._event_linker.unlink(mid, engine=self)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if getattr(self, '_topic_cluster', None):
                for mid in evicted_ids:
                    try:
                        if hasattr(self._topic_cluster, 'delete_memory_topics'):
                            self._topic_cluster.delete_memory_topics(mid)
                        elif hasattr(self._topic_cluster, 'remove'):
                            self._topic_cluster.remove(mid)
                    except Exception:
                        pass
        except Exception:
            pass
        logger.info(f"[Recall v7.0] LRU 驱逐级联清理完成: {len(evicted_ids)} 条幽灵索引已移除")
    
    def _try_ivf_auto_switch(self):
        """v7.0 C-2: 检查是否应自动切换到 VectorIndexIVF
        
        当向量索引中的向量数量超过 IVF_AUTO_SWITCH_THRESHOLD（默认 50000）时，
        自动创建 VectorIndexIVF 替代平坦索引，获得更好的大规模检索性能。
        
        VectorIndexIVF 使用 FAISS IVF-HNSW，在大规模数据（>5万）下
        比平坦索引有显著的速度优势，同时保持 95-99% 的召回率。
        """
        try:
            # 检查是否已手动禁用
            if not self.recall_config.ivf_auto_switch_enabled:
                return
            
            # 获取当前向量数
            vector_count = 0
            if self._vector_index and self._vector_index.enabled:
                stats = self._vector_index.get_stats()
                vector_count = stats.get('total_vectors', 0)
            
            if vector_count < self._ivf_auto_switch_threshold:
                return
            
            # 尝试导入 faiss
            from .index.vector_index_ivf import FAISS_AVAILABLE
            if not FAISS_AVAILABLE:
                logger.info("[Recall v7.0] 向量数超过阈值但 faiss 未安装，跳过 IVF 切换")
                return
            
            # 创建 VectorIndexIVF
            ivf_path = os.path.join(self.data_root, 'indexes', 'ivf')
            dimension = self._vector_index.dimension if hasattr(self._vector_index, 'dimension') else 384
            
            # 根据数据量调整 nlist（聚类中心数）
            nlist = min(max(int(vector_count ** 0.5), 100), 4096)
            nprobe = max(nlist // 10, 10)
            
            self._vector_index_ivf = VectorIndexIVF(
                data_path=ivf_path,
                dimension=dimension,
                nlist=nlist,
                nprobe=nprobe,
                use_hnsw_quantizer=True,
            )
            
            # v7.0: 迁移已有向量到 IVF 索引
            if self._vector_index_ivf.index.ntotal == 0 and vector_count > 0:
                self._migrate_vectors_to_ivf(vector_count)
            
            _safe_print(f"[Recall v7.0] VectorIndexIVF 自动启用 "
                       f"(向量数={vector_count} > 阈值={self._ivf_auto_switch_threshold}, "
                       f"nlist={nlist}, nprobe={nprobe})")
            
        except ImportError:
            logger.debug("[Recall v7.0] faiss 未安装，VectorIndexIVF 不可用")
        except Exception as e:
            logger.warning(f"[Recall v7.0] VectorIndexIVF 自动切换失败（不影响核心功能）: {e}")
            self._vector_index_ivf = None
    
    def get_active_vector_index(self):
        """v7.0: 获取当前活跃的向量索引
        
        如果 VectorIndexIVF 已启用则返回它，否则返回普通 VectorIndex。
        """
        if self._vector_index_ivf is not None:
            return self._vector_index_ivf
        return self._vector_index
    
    def _migrate_vectors_to_ivf(self, vector_count: int):
        """v7.0: 从平坦索引迁移向量到 IVF 索引

        从 VectorIndex 的 faiss FlatIP 索引中重建向量并批量导入 IVF，
        确保切换后 IVF 索引不是空的。
        """
        try:
            import numpy as np
            flat_index = self._vector_index.index  # faiss IndexFlatIP
            if flat_index.ntotal == 0:
                return

            # 从 faiss Flat 索引重建全量向量
            import faiss
            vectors = faiss.rev_swig_ptr(flat_index.get_xb(), flat_index.ntotal * flat_index.d)
            vectors = vectors.reshape(flat_index.ntotal, flat_index.d).copy()

            # 获取对应的 doc_id 列表
            doc_ids = list(self._vector_index.turn_mapping)

            if len(doc_ids) != flat_index.ntotal:
                _safe_print(f"[Recall v7.0] 向量迁移跳过: doc_ids({len(doc_ids)}) != vectors({flat_index.ntotal})")
                return

            # 先用向量数据训练 IVF
            self._vector_index_ivf.train(vectors.tolist())

            # 批量添加
            migrated = 0
            for i, doc_id in enumerate(doc_ids):
                if self._vector_index_ivf.add(doc_id, vectors[i].tolist()):
                    migrated += 1

            _safe_print(f"[Recall v7.0] 向量迁移完成: {migrated}/{vector_count} 已导入 IVF 索引")
        except Exception as e:
            _safe_print(f"[Recall v7.0] 向量迁移失败（不影响核心功能，回退到平坦索引）: {e}")
            self._vector_index_ivf = None

    def _rebuild_content_cache(self):
        """重建内容缓存（从持久化存储恢复）"""
        # 扫描所有用户目录
        data_path = os.path.join(self.data_root, 'data')
        if not os.path.exists(data_path):
            return
        
        count = 0
        for user_dir in os.listdir(data_path):
            user_path = os.path.join(data_path, user_dir)
            if not os.path.isdir(user_path):
                continue
            
            # 扫描该用户下的所有角色/会话
            for root, dirs, files in os.walk(user_path):
                if 'memories.json' in files:
                    memories_file = os.path.join(root, 'memories.json')
                    try:
                        with open(memories_file, 'r', encoding='utf-8') as f:
                            memories = __import__('json').load(f)
                            for mem in memories:
                                mem_id = mem.get('metadata', {}).get('id')
                                content = mem.get('content', '')
                                metadata = mem.get('metadata', {})
                                entities = mem.get('entities', [])
                                if mem_id and content:
                                    self.retriever.cache_content(mem_id, content)
                                    # 同时缓存 metadata 和 entities
                                    if hasattr(self.retriever, 'cache_metadata'):
                                        self.retriever.cache_metadata(mem_id, metadata)
                                    if hasattr(self.retriever, 'cache_entities'):
                                        self.retriever.cache_entities(mem_id, entities)
                                    count += 1
                    except Exception as e:
                        _safe_print(f"[Recall] 加载 {memories_file} 失败: {e}")
        
        if count > 0:
            _safe_print(f"[Recall] 已恢复 {count} 条记忆内容到缓存")
    
    def _warmup(self):
        """预热模型（仅 Local 模式）"""
        warmup_manager = WarmupManager()
        
        # 注册预热任务
        warmup_manager.register(
            'entity_extractor',
            lambda: self.entity_extractor.nlp,
            priority=10
        )
        
        # 只有本地模式才预热向量模型
        if self._vector_index and self._vector_index.enabled:
            if self.embedding_config.backend == EmbeddingBackendType.LOCAL:
                warmup_manager.register(
                    'vector_model',
                    lambda: self._vector_index.embedding_backend.model,
                    priority=5
                )
        
        # 后台预热
        warmup_manager.warmup_async()
    
    # ==================== 核心 API ====================
    
    def add(
        self,
        content: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        check_consistency: bool = True
    ) -> AddResult:
        """添加记忆
        
        Args:
            content: 记忆内容
            user_id: 用户ID
            metadata: 元数据
            check_consistency: 是否检查一致性
        
        Returns:
            AddResult: 添加结果
        """
        return self._memory_ops.add(content, user_id=user_id, metadata=metadata, check_consistency=check_consistency)
    
    def add_batch(
        self,
        items: List[Dict[str, Any]],
        user_id: str = "default",
        skip_dedup: bool = False,
        skip_llm: bool = True,
    ) -> List[str]:
        """批量添加记忆（高吞吐）
        
        Args:
            items: [{"content": "...", "source": "bilibili", "tags": [...], "metadata": {...}}, ...]
            user_id: 用户ID
            skip_dedup: 跳过去重检查
            skip_llm: 跳过 LLM 调用（实体提取用规则模式）
        
        Returns:
            List[str]: 成功添加的 memory_id 列表
        """
        return self._memory_ops.add_batch(items, user_id=user_id, skip_dedup=skip_dedup, skip_llm=skip_llm)

    def _add_single_fast(self, content, embedding, metadata, user_id, skip_dedup, skip_llm):
        """单条快速添加（add_batch 内部使用）"""
        return self._memory_ops._add_single_fast(content, embedding, metadata, user_id, skip_dedup, skip_llm)

    def _batch_update_indexes(self, all_keywords, all_entities, all_ngram_data, all_relations=None):
        """批量更新索引 — 合并 IO 操作"""
        return self._memory_ops._batch_update_indexes(all_keywords, all_entities, all_ngram_data, all_relations)

    def list_entities(self, user_id="default", entity_type=None, limit=100):
        """列出实体"""
        if not self._entity_index:
            return []
        entities = self._entity_index.all_entities()
        if entity_type:
            entities = [e for e in entities if getattr(e, 'entity_type', '') == entity_type]
        return [{'name': e.name, 'type': getattr(e, 'entity_type', ''),
                 'summary': getattr(e, 'summary', '')} for e in entities[:limit]]

    def traverse_graph(self, start_entity, max_depth=2, relation_types=None, user_id="default"):
        """图遍历"""
        if not self.knowledge_graph:
            return {"nodes": [], "edges": []}
        from collections import deque
        visited = set()
        queue = deque([(start_entity, 0)])
        nodes, edges = [], []
        while queue:
            entity, depth = queue.popleft()
            if entity in visited or depth > max_depth:
                continue
            visited.add(entity)
            nodes.append({"name": entity, "depth": depth})
            for rel in self.knowledge_graph.get_relations_for_entity(entity):
                if relation_types and rel.relation_type not in relation_types:
                    continue
                edges.append({"source": rel.source_id, "target": rel.target_id,
                             "type": rel.relation_type})
                next_entity = rel.target_id if rel.source_id == entity else rel.source_id
                queue.append((next_entity, depth + 1))
        return {"nodes": nodes, "edges": edges}

    def list_memories(self, limit=100, user_id="default"):
        """列出记忆"""
        memories, total = self.get_paginated(user_id=user_id, offset=0, limit=limit)
        return memories

    def get_entity_detail(self, entity_name, user_id="default"):
        """获取实体详情"""
        if not self._entity_index:
            return {"name": entity_name, "error": "entity index not initialized"}
        entity = self._entity_index.get_entity(entity_name)
        if entity:
            return {"name": entity_name, "type": getattr(entity, 'entity_type', ''),
                    "summary": getattr(entity, 'summary', ''),
                    "facts": [str(f) for f in getattr(entity, 'facts', [])]}
        return {"name": entity_name, "error": "entity not found"}

    def add_turn(
        self,
        user_message: str,
        ai_response: str,
        user_id: str = "default",
        character_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> AddTurnResult:
        """添加对话轮次（v4.2 性能优化版）- 委托给 MemoryOperations"""
        return self._memory_ops.add_turn(user_message, ai_response, user_id=user_id, character_id=character_id, metadata=metadata)

    def search(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        temporal_context: Optional[Any] = None,
        config_preset: Optional[str] = None,
        source: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        content_type: Optional[str] = None,
        event_time_start: Optional[str] = None,
        event_time_end: Optional[str] = None,
    ) -> List[SearchResult]:
        """搜索记忆
        
        Args:
            query: 搜索查询
            user_id: 用户ID
            top_k: 返回数量
            filters: 过滤条件
            temporal_context: 时态上下文（Phase 3 新增，用于 L2 时态检索层）
            config_preset: 配置预设（Phase 3 新增：default/fast/accurate）
            source: v5.0 元数据过滤 - 来源
            tags: v5.0 元数据过滤 - 标签
            category: v5.0 元数据过滤 - 类别
            content_type: v5.0 元数据过滤 - 内容类型
            event_time_start: v5.0 事件时间范围起点（YYYY-MM-DD 或 ISO）
            event_time_end: v5.0 事件时间范围终点（YYYY-MM-DD 或 ISO）
        
        Returns:
            List[SearchResult]: 搜索结果
        """
        # v5.0: 元数据过滤
        if any([source, tags, category, content_type, event_time_start, event_time_end]) and self._metadata_index:
            allowed_ids = self._metadata_index.query(
                source=source, tags=tags, category=category, content_type=content_type,
                event_time_start=event_time_start, event_time_end=event_time_end,
            )
        else:
            allowed_ids = None
        
        # 1. 提取查询实体和关键词
        entities = [e.name for e in self.entity_extractor.extract(query)]
        keywords = self.entity_extractor.extract_keywords(query)
        
        # 2. 检测场景
        scenario = self.scenario_detector.detect(query)
        
        # 3. Phase 3: 构建检索配置
        retrieval_config = None
        if config_preset and hasattr(self.retriever, 'config'):
            from recall.retrieval.config import RetrievalConfig
            if config_preset == 'fast':
                retrieval_config = RetrievalConfig.fast()
            elif config_preset == 'accurate':
                retrieval_config = RetrievalConfig.accurate()
            # default 使用 retriever 的默认配置
        
        # 4. 执行检索（传递 Phase 3 新参数）
        # 【BUG-003 修复】先获取当前用户的所有记忆 ID，用于后续过滤
        scope = self.storage.get_scope(user_id)
        user_memory_ids = set()
        for mem in scope._memories:
            mem_id = mem.get('metadata', {}).get('id', '')
            if mem_id:
                user_memory_ids.add(mem_id)
        
        # 从全局索引检索（可能包含其他用户的结果）
        retrieval_results = self.retriever.retrieve(
            query=query,
            entities=entities,
            keywords=keywords,
            top_k=top_k * 3,  # 多取一些，因为要过滤
            filters=filters,
            temporal_context=temporal_context,
            config=retrieval_config
        )
        
        # 【BUG-003 修复】过滤结果，只保留属于当前用户的记忆
        retrieval_results = [
            r for r in retrieval_results 
            if r.id in user_memory_ids
        ]
        
        # 4.5 补充从存储获取（已经是用户隔离的）
        stored_memories = scope.search(query, limit=top_k)
        
        # 4.6 BAL dual-read: 从 BAL 后端补充搜索结果
        bal_results = []
        bal_seen = set()
        # BAL 向量搜索
        if getattr(self, '_vector_backend', None) and self.embedding_backend:
            try:
                query_vec = self.embedding_backend.encode(query)
                if query_vec is not None:
                    ns = getattr(scope, '_namespace', user_id)
                    bal_vector_hits = self._vector_backend.search(
                        query_vec, top_k=top_k * 2,
                        filters={'namespace': ns}
                    )
                    for hit in bal_vector_hits:
                        if hit.id and hit.id not in bal_seen:
                            bal_results.append((hit.id, hit.score, hit.text or '', hit.metadata or {}))
                            bal_seen.add(hit.id)
            except Exception:
                pass  # BAL VectorBackend search — skip on error
        # BAL 全文搜索
        if getattr(self, '_text_search_backend', None):
            try:
                ns = getattr(scope, '_namespace', user_id)
                bal_fts_hits = self._text_search_backend.search(
                    query, top_k=top_k,
                    filters={'namespace': ns, 'user_id': user_id}
                )
                for hit in bal_fts_hits:
                    if hit.id and hit.id not in bal_seen:
                        bal_results.append((hit.id, hit.score * 0.8, hit.text or '', hit.metadata or {}))
                        bal_seen.add(hit.id)
            except Exception:
                pass  # BAL TextSearchBackend search — skip on error
        
        # 5. 合并结果
        results = []
        seen_ids = set()
        
        for r in retrieval_results:
            if r.id not in seen_ids:
                results.append(SearchResult(
                    id=r.id,
                    content=r.content,
                    score=r.score,
                    metadata=r.metadata,
                    entities=r.entities
                ))
                seen_ids.add(r.id)
        
        for m in stored_memories:
            mem_id = m.get('metadata', {}).get('id', '') or m.get('id', '')
            if mem_id and mem_id not in seen_ids:
                results.append(SearchResult(
                    id=mem_id,
                    content=m.get('content', m.get('memory', '')),
                    score=m.get('score', 0.5),
                    metadata=m.get('metadata', {}),
                    entities=m.get('entities', [])
                ))
                seen_ids.add(mem_id)
        
        # 5.5 合并 BAL 搜索结果（补充旧路径未覆盖的记忆）
        for bal_id, bal_score, bal_text, bal_meta in bal_results:
            if bal_id not in seen_ids and bal_id in user_memory_ids:
                content = bal_text
                if not content and getattr(self, '_storage_backend', None):
                    try:
                        stored = self._storage_backend.load(bal_id)
                        content = stored.get('content', '') if stored else ''
                    except Exception:
                        content = ''
                if content:
                    results.append(SearchResult(
                        id=bal_id, content=content,
                        score=bal_score, metadata=bal_meta, entities=[]
                    ))
                    seen_ids.add(bal_id)
        
        # v5.0: 元数据过滤（后过滤）
        if allowed_ids is not None:
            results = [r for r in results if r.id in allowed_ids]
        
        # v7.0.3: VolumeManager 归档搜索（确保被 LRU 驱逐的记忆仍可搜索）
        # v7.0.7: 移除 `mid in user_memory_ids` 条件（被驱逐记忆不在 scope._memories 中，永远为 False）
        # 改用 user_id 过滤保证隔离
        if len(results) < top_k and self.volume_manager:
            try:
                archive_hits = self.volume_manager.search_content(query, max_results=(top_k - len(results)) * 3)
                for hit in archive_hits:
                    mid = hit.get('memory_id', '')
                    # 用户隔离：通过 user_id 字段过滤
                    hit_user = hit.get('user_id', '')
                    # v7.0.12: 移除 hit_user=='unknown' 宽松匹配，防止跨用户数据泄漏
                    if mid and mid not in seen_ids and (hit_user == user_id):
                        # v7.0.9: 归档结果也需通过 metadata 过滤（allowed_ids）
                        if allowed_ids is not None and mid not in allowed_ids:
                            continue
                        results.append(SearchResult(
                            id=mid,
                            content=hit.get('content', ''),
                            score=0.3,  # 归档数据给较低分数（时效性低）
                            metadata=hit.get('metadata', {}),
                            entities=hit.get('entities', [])
                        ))
                        seen_ids.add(mid)
                        if len(results) >= top_k:
                            break
            except Exception:
                pass  # VolumeManager 搜索失败不影响已有结果
        
        return results[:top_k]
    
    def get_all(
        self,
        user_id: str = "default",
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """获取所有记忆
        
        Args:
            user_id: 用户ID
            limit: 限制数量，None表示返回全部
        
        Returns:
            List[Dict]: 记忆列表
        """
        scope = self.storage.get_scope(user_id)
        return scope.get_all(limit=limit)
    
    def get_paginated(
        self,
        user_id: str = "default",
        offset: int = 0,
        limit: int = 20
    ) -> tuple:
        """分页获取记忆（高效版本）
        
        Args:
            user_id: 用户ID
            offset: 偏移量
            limit: 每页数量
        
        Returns:
            tuple: (memories, total_count)
        """
        scope = self.storage.get_scope(user_id)
        total = scope.count()
        memories = scope.get_paginated(offset=offset, limit=limit)
        return memories, total
    
    def count_memories(self, user_id: str = "default") -> int:
        """获取记忆总数（O(1)操作）
        
        Args:
            user_id: 用户ID
        
        Returns:
            int: 记忆总数
        """
        scope = self.storage.get_scope(user_id)
        return scope.count()
    
    def get(
        self,
        memory_id: str,
        user_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """获取单条记忆 — O(1) 索引查找
        
        Args:
            memory_id: 记忆ID
            user_id: 用户ID
        
        Returns:
            Dict: 记忆数据，如果不存在则返回 None
        """
        # v7.0.3: 使用 _memory_index O(1) 查找替代 O(n) 全量遍历
        scope = self.storage.get_scope(user_id)
        # 先尝试 O(1) 索引查找
        if hasattr(scope, '_memory_index') and memory_id in scope._memory_index:
            memory = scope._memory_index[memory_id]
            return memory
        # 回退到遍历（兼容旧数据格式）
        all_memories = scope.get_all()
        for memory in all_memories:
            if memory.get('metadata', {}).get('id') == memory_id:
                return memory
        # 最终回退：尝试所有 scope（跨用户查找）
        if user_id == "default":
            for uid in self.storage.list_users():
                if uid == user_id:
                    continue
                s = self.storage.get_scope(uid)
                if hasattr(s, '_memory_index') and memory_id in s._memory_index:
                    return s._memory_index[memory_id]
        return None
    
    def clear(
        self,
        user_id: str = "default"
    ) -> bool:
        """清空用户的所有记忆 - 委托给 MemoryOperations"""
        return self._memory_ops.clear(user_id=user_id)

    def clear_all(self) -> bool:
        """清空所有数据（管理员操作）
        
        ⚠️ 危险操作！这将删除所有用户的全部数据，包括：
        - 所有用户的记忆
        - 知识图谱
        - 实体索引
        - L1 整合存储
        - 向量索引
        - IVF 向量索引
        - BAL 后端
        - EventLinker / TopicCluster
        - 检索器缓存 / 矛盾管理器 / 时态索引
        
        Returns:
            bool: 是否成功
        """
        # v7.0.7: 委托到 memory_ops.clear_all()，避免重复实现导致的遗漏和 AttributeError
        # （之前独立实现存在调用不存在的 _analysis_markers 属性导致整个方法失败，
        #  且缺少 IVF/BAL/EventLinker/TopicCluster/检索器缓存/矛盾管理器/时态索引 清理）
        return self._memory_ops.clear_all()
    
    def stats(self) -> Dict[str, Any]:
        """获取统计信息（get_stats 的别名）"""
        return self.get_stats()
    
    # ==================== Phase 3.5 高级 API ====================
    
    def detect_communities(
        self,
        user_id: str = "default",
        min_size: int = 2
    ) -> List[Dict[str, Any]]:
        """检测实体社区/群组 (Phase 3.5)
        
        使用 Louvain 或标签传播算法发现图中的实体群组。
        需要启用 COMMUNITY_DETECTION_ENABLED=true。
        
        Args:
            user_id: 用户ID（用于过滤社区）
            min_size: 最小社区大小
        
        Returns:
            List[Dict]: 社区列表，每个包含：
                - id: 社区ID
                - name: 社区名称
                - member_ids: 成员实体ID列表
                - size: 社区大小
        """
        if self.community_detector is None:
            _safe_print("[Recall] 社区检测器未启用，请设置 COMMUNITY_DETECTION_ENABLED=true")
            return []
        
        try:
            communities = self.community_detector.detect_communities()
            # 过滤最小大小
            result = []
            for comm in communities:
                if comm.size >= min_size:
                    result.append({
                        'id': comm.id,
                        'name': comm.name,
                        'member_ids': comm.member_ids,
                        'size': comm.size,
                        'summary': comm.summary
                    })
            return result
        except Exception as e:
            _safe_print(f"[Recall] 社区检测失败: {e}")
            return []
    
    def get_query_stats(self) -> Dict[str, Any]:
        """获取图查询统计信息 (Phase 3.5)
        
        需要启用 QUERY_PLANNER_ENABLED=true。
        
        Returns:
            Dict: 查询统计，包含：
                - total_queries: 总查询数
                - cache_hits: 缓存命中数
                - cache_hit_rate: 缓存命中率
                - avg_execution_time_ms: 平均执行时间
        """
        if self.query_planner is None:
            return {'enabled': False, 'message': '图查询规划器未启用'}
        
        try:
            stats = self.query_planner.stats
            return {
                'enabled': True,
                'total_queries': stats.total_queries,
                'cache_hits': stats.cache_hits,
                'cache_hit_rate': stats.cache_hit_rate,
                'avg_execution_time_ms': stats.avg_execution_time_ms,
                'total_nodes_visited': stats.total_nodes_visited
            }
        except Exception as e:
            return {'enabled': True, 'error': str(e)}
    
    def delete(
        self,
        memory_id: str,
        user_id: str = "default"
    ) -> bool:
        """删除记忆（级联清理 13 个存储位置）- 委托给 MemoryOperations"""
        return self._memory_ops.delete(memory_id, user_id=user_id)

    def update(
        self,
        memory_id: str,
        content: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新记忆 - 委托给 MemoryOperations"""
        return self._memory_ops.update(memory_id, content, user_id=user_id, metadata=metadata)

    def build_context(
        self,
        query: str,
        user_id: str = "default",
        character_id: str = "default",
        max_tokens: int = 2000,
        include_recent: int = None,
        include_core_facts: bool = True,
        auto_extract_context: bool = False
    ) -> str:
        """构建上下文 - 委托给 ContextBuild"""
        return self._context_build.build_context(
            query, user_id=user_id, character_id=character_id,
            max_tokens=max_tokens, include_recent=include_recent,
            include_core_facts=include_core_facts,
            auto_extract_context=auto_extract_context
        )
    
    def _format_foreshadowings(self, foreshadowings) -> str:
        """格式化伏笔为提示文本"""
        if not foreshadowings:
            return ""
        
        lines = ["\n<foreshadowings>", "以下是尚未解决的伏笔，请在合适时机自然地推进或回收："]
        for f in foreshadowings:
            importance_label = "高" if f.importance > 0.7 else "中" if f.importance > 0.4 else "低"
            lines.append(f"• [{importance_label}] {f.content}")
            if f.related_entities:
                lines.append(f"  相关角色/事物: {', '.join(f.related_entities)}")
        lines.append("</foreshadowings>")
        return "\n".join(lines)
    
    # ==================== 伏笔 API ====================
    
    def _check_foreshadowing_enabled(self):
        """检查伏笔系统是否可用"""
        if not self._mode.foreshadowing_enabled:
            raise RuntimeError("伏笔系统已禁用（设置 FORESHADOWING_ENABLED=true 以启用）")
        if self.foreshadowing_tracker is None:
            raise RuntimeError("伏笔系统未初始化（可能启动时出错）")

    def plant_foreshadowing(
        self,
        content: str,
        user_id: str = "default",
        character_id: str = "default",
        related_entities: Optional[List[str]] = None,
        importance: float = 0.5
    ) -> Foreshadowing:
        """埋下伏笔
        
        同时将伏笔索引到 VectorIndex 以支持语义检索（即使归档后也能搜索）
        """
        self._check_foreshadowing_enabled()
        foreshadowing = self.foreshadowing_tracker.plant(
            content=content,
            user_id=user_id,
            character_id=character_id,
            related_entities=related_entities,
            importance=importance
        )
        
        # 索引到 VectorIndex（确保归档后仍可语义检索）
        # 注意：foreshadowing.id 已经是 fsh_{counter}_{timestamp} 格式，不需要再加 fsh_ 前缀
        if self._vector_index and self._vector_index.enabled:
            doc_id = f"{user_id}_{character_id}_{foreshadowing.id}"
            self._vector_index.add_text(doc_id, content)
        
        return foreshadowing
    
    def resolve_foreshadowing(
        self,
        foreshadowing_id: str,
        resolution: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """解决伏笔"""
        self._check_foreshadowing_enabled()
        return self.foreshadowing_tracker.resolve(foreshadowing_id, resolution, user_id, character_id)
    
    def add_foreshadowing_hint(
        self,
        foreshadowing_id: str,
        hint: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """添加伏笔提示
        
        为伏笔添加进展提示，会将状态从 PLANTED 更新为 DEVELOPING
        
        Args:
            foreshadowing_id: 伏笔ID
            hint: 提示内容
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            bool: 是否成功
        """
        self._check_foreshadowing_enabled()
        return self.foreshadowing_tracker.add_hint(foreshadowing_id, hint, user_id, character_id)
    
    def abandon_foreshadowing(
        self,
        foreshadowing_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """放弃/删除伏笔
        
        将伏笔标记为已放弃状态（不会物理删除，保留历史记录）
        
        Args:
            foreshadowing_id: 伏笔ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            bool: 是否成功
        """
        self._check_foreshadowing_enabled()
        return self.foreshadowing_tracker.delete(foreshadowing_id, user_id=user_id, character_id=character_id)
    
    def get_active_foreshadowings(self, user_id: str = "default", character_id: str = "default") -> List[Foreshadowing]:
        """获取活跃伏笔"""
        self._check_foreshadowing_enabled()
        return self.foreshadowing_tracker.get_active(user_id, character_id)
    
    def get_foreshadowing_by_id(
        self,
        foreshadowing_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> Optional[Foreshadowing]:
        """根据ID获取伏笔（包括已归档的）
        
        用于从 VectorIndex 搜索结果中获取伏笔详情。
        搜索命中归档伏笔时，通过此方法从归档文件读取完整信息。
        
        Args:
            foreshadowing_id: 伏笔ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            Optional[Foreshadowing]: 伏笔对象，未找到返回 None
        """
        self._check_foreshadowing_enabled()
        # v7.0.4: 修复 — ForeshadowingTracker 没有 get_by_id() 方法，只有 get()
        return self.foreshadowing_tracker.get(foreshadowing_id)
    
    def on_foreshadowing_turn(
        self, 
        content: str, 
        role: str = "user", 
        user_id: str = "default",
        character_id: str = "default"
    ) -> AnalysisResult:
        """处理新的一轮对话（用于伏笔分析）
        
        在每轮对话后调用此方法，分析器会：
        - 手动模式：不做任何操作，返回空结果
        - LLM模式：累积对话，达到触发条件时自动分析
        
        Args:
            content: 对话内容
            role: 角色（user/assistant）
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            AnalysisResult: 分析结果
        """
        self._check_foreshadowing_enabled()
        return self.foreshadowing_analyzer.on_new_turn(
            content=content,
            role=role,
            user_id=user_id,
            character_id=character_id
        )
    
    def trigger_foreshadowing_analysis(self, user_id: str = "default", character_id: str = "default") -> AnalysisResult:
        """手动触发伏笔分析
        
        可以在任何时候调用，强制触发 LLM 分析（如果已配置）。
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            AnalysisResult: 分析结果
        """
        self._check_foreshadowing_enabled()
        return self.foreshadowing_analyzer.trigger_analysis(user_id)
    
    def get_foreshadowing_analyzer_config(self) -> Dict[str, Any]:
        """获取伏笔分析器配置"""
        self._check_foreshadowing_enabled()
        return self.foreshadowing_analyzer.config.to_dict()
    
    def update_foreshadowing_analyzer_config(
        self,
        trigger_interval: Optional[int] = None,
        auto_plant: Optional[bool] = None,
        auto_resolve: Optional[bool] = None
    ):
        """更新伏笔分析器配置"""
        self._check_foreshadowing_enabled()
        self.foreshadowing_analyzer.update_config(
            trigger_interval=trigger_interval,
            auto_plant=auto_plant,
            auto_resolve=auto_resolve
        )
    
    def enable_foreshadowing_llm_mode(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None
    ):
        """启用伏笔分析器的 LLM 模式（动态切换，无需重启）"""
        self._check_foreshadowing_enabled()
        self.foreshadowing_analyzer.enable_llm_mode(
            api_key=api_key,
            model=model,
            base_url=base_url
        )
    
    def disable_foreshadowing_llm_mode(self):
        """禁用伏笔分析器的 LLM 模式，切换回手动模式"""
        self._check_foreshadowing_enabled()
        self.foreshadowing_analyzer.disable_llm_mode()
    
    # ==================== 持久条件 API ====================
    
    def add_persistent_context(
        self,
        content: str,
        context_type = "custom",
        user_id: str = "default",
        character_id: str = "default",
        keywords: List[str] = None
    ):
        """添加持久条件
        
        持久条件是一旦确立就应该在后续所有对话中默认成立的背景信息。
        
        Args:
            content: 条件内容，如"用户是大学毕业生想创业"
            context_type: 类型，可以是字符串或 ContextType 枚举，可选值：
                - user_identity: 用户身份
                - user_goal: 用户目标
                - user_preference: 用户偏好
                - environment: 技术环境
                - project: 项目信息
                - character_trait: 角色特征
                - world_setting: 世界观
                - relationship: 关系设定
                - assumption: 假设前提
                - constraint: 约束条件
                - custom: 自定义
            user_id: 用户ID
            character_id: 角色ID
            keywords: 关键词列表
            
        Returns:
            PersistentContext: 创建的条件对象
        """
        from .processor.context_tracker import ContextType
        
        # 支持字符串和枚举两种输入
        if isinstance(context_type, ContextType):
            ctx_type = context_type
        else:
            try:
                ctx_type = ContextType(context_type)
            except ValueError:
                ctx_type = ContextType.CUSTOM
        
        context = self.context_tracker.add(
            content=content,
            context_type=ctx_type,
            user_id=user_id,
            character_id=character_id,
            keywords=keywords
        )
        
        # 索引到 VectorIndex（无论是否活跃，确保即使被淘汰也可语义检索）
        # 被 _enforce_limits() 淘汰的条件仍需可被搜索找回
        if self._vector_index and self._vector_index.enabled:
            doc_id = f"ctx_{user_id}_{character_id}_{context.id}"
            self._vector_index.add_text(doc_id, content)
        
        return context
    
    def get_persistent_contexts(self, user_id: str = "default", character_id: str = "default") -> List[Dict]:
        """获取所有活跃的持久条件"""
        contexts = self.context_tracker.get_active(user_id, character_id)
        return [c.to_dict() for c in contexts]
    
    def get_persistent_context_by_id(
        self,
        context_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> Optional[Dict]:
        """根据ID获取持久条件（包括已归档的）
        
        用于从 VectorIndex 搜索结果中获取条件详情。
        搜索命中归档条件时，通过此方法从归档文件读取完整信息。
        
        Args:
            context_id: 条件ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            Optional[Dict]: 条件数据字典，未找到返回 None
        """
        ctx = self.context_tracker.get_context_by_id(context_id, user_id, character_id)
        return ctx.to_dict() if ctx else None
    
    def remove_persistent_context(self, context_id: str, user_id: str = "default", character_id: str = "default") -> bool:
        """移除（停用）某个持久条件"""
        return self.context_tracker.deactivate(context_id, user_id, character_id)
    
    def extract_contexts_from_text(self, text: str, user_id: str = "default", character_id: str = "default") -> List[Dict]:
        """从文本中自动提取持久条件
        
        使用 LLM（如果可用）或规则从文本中提取应该持久化的条件。
        同时将新提取的条件索引到 VectorIndex 以支持语义检索。
        
        Args:
            text: 要分析的文本
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            List[Dict]: 提取出的条件列表
        """
        contexts = self.context_tracker.extract_from_text(text, user_id, character_id)
        
        # 索引新提取的条件到 VectorIndex（无论活跃状态）
        if self._vector_index and self._vector_index.enabled:
            for ctx in contexts:
                doc_id = f"ctx_{user_id}_{character_id}_{ctx.id}"
                self._vector_index.add_text(doc_id, ctx.content)
        
        return [c.to_dict() for c in contexts]
    
    def consolidate_persistent_contexts(self, user_id: str = "default", character_id: str = "default", force: bool = False) -> Dict:
        """压缩合并持久条件
        
        当持久条件数量过多时，智能合并相似的条件以控制增长。
        如果配置了LLM，会使用LLM进行智能压缩；否则只保留置信度最高的条件。
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            force: 是否强制执行（默认只在超过阈值时执行）
            
        Returns:
            Dict: 压缩结果，包含：
                - reduced: 减少的条件数量
                - before: 压缩前的统计
                - after: 压缩后的统计
        """
        before_stats = self.context_tracker.get_stats(user_id=user_id, character_id=character_id)
        reduced = self.context_tracker.consolidate_contexts(user_id=user_id, character_id=character_id, force=force)
        after_stats = self.context_tracker.get_stats(user_id=user_id, character_id=character_id)
        
        return {
            'reduced': reduced,
            'before': before_stats,
            'after': after_stats
        }
    
    # ==================== 实体 API ====================
    
    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """获取实体信息"""
        if self._entity_index:
            indexed = self._entity_index.get_entity(name)
            if indexed:
                return {
                    'name': indexed.name,
                    'type': indexed.entity_type,
                    'aliases': indexed.aliases,
                    'occurrence_count': len(indexed.turn_references),  # 统一使用 occurrence_count
                    'related_turns': indexed.turn_references[:10]
                }
        return None
    
    def get_related_entities(self, name: str) -> List[Dict[str, str]]:
        """获取相关实体
        
        Args:
            name: 实体名称
            
        Returns:
            [{"name": "目标实体", "relation_type": "关系类型"}, ...]
        """
        if not self.knowledge_graph:
            return []
        neighbors = self.knowledge_graph.get_neighbors(name)
        result = []
        for neighbor_id, relation in neighbors:
            result.append({
                "name": neighbor_id,
                "relation_type": relation.relation_type,
                "confidence": relation.confidence
            })
        return result
    
    # ==================== 管理 API ====================
    
    def rebuild_vector_index(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """重建向量索引
        
        从现有记忆数据重新生成向量索引，用于修复维度不匹配等问题。
        
        Args:
            user_id: 可选，指定只重建某个用户的索引。为 None 时重建所有用户。
            
        Returns:
            Dict: 包含 success, message, indexed_count 等信息
        """
        if self._vector_index is None:
            return {
                'success': False,
                'message': '向量索引未启用',
                'indexed_count': 0
            }
        
        # 收集需要索引的记忆
        memories_to_index = []
        
        if user_id:
            # 只重建指定用户
            scope = self.storage.get_scope(user_id)
            for m in scope.get_all():
                # v7.0.12: 修复 — id 在 metadata 子字典中，不在顶层
                memory_id = m.get('metadata', {}).get('id', '') or m.get('id', '')
                content = m.get('content', m.get('memory', ''))
                if memory_id and content:
                    memories_to_index.append((memory_id, content))
            _safe_print(f"[Recall] 重建向量索引: user={user_id}, 记忆数={len(memories_to_index)}")
        else:
            # 重建所有用户
            for scope_key, scope in self.storage._scopes.items():
                for m in scope.get_all():
                    # v7.0.12: 修复 — id 在 metadata 子字典中，不在顶层
                    memory_id = m.get('metadata', {}).get('id', '') or m.get('id', '')
                    content = m.get('content', m.get('memory', ''))
                    if memory_id and content:
                        memories_to_index.append((memory_id, content))
            _safe_print(f"[Recall] 重建向量索引: 全部用户, 记忆数={len(memories_to_index)}")
        
        if not memories_to_index:
            return {
                'success': True,
                'message': '没有需要索引的记忆',
                'indexed_count': 0
            }
        
        # 调用向量索引的重建方法
        try:
            indexed_count = self._vector_index.rebuild_from_memories(memories_to_index)
            return {
                'success': True,
                'message': f'向量索引重建完成',
                'indexed_count': indexed_count,
                'total_memories': len(memories_to_index)
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'重建失败: {e}',
                'indexed_count': 0
            }
    
    def get_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """获取详细统计信息
        
        Args:
            user_id: 可选的用户ID，指定后返回该用户的详细统计
        
        Returns:
            Dict: 统计信息，包含：
                - total_memories: 总记忆数
                - total_entities: 总实体数
                - total_foreshadowings: 伏笔数
                - 如果指定 user_id，还包含该用户的详细统计
        """
        stats = {
            'version': __version__,
            'data_root': self.data_root,
            'mode': self._get_mode_name(),
            'lightweight': self.lightweight,  # 保留旧字段（向后兼容）
            'lite': self.lightweight,  # 新字段（推荐使用）
        }
        
        # 全局统计
        total_memories = 0
        total_entities_in_memories = 0
        
        # v7.0.7: 使用 count() 替代 get_all() 避免加载全部记忆到内存
        for scope_key, scope in self.storage._scopes.items():
            total_memories += scope.count() if hasattr(scope, 'count') else len(scope.get_all())
        
        stats['global'] = {
            'total_memories': total_memories,
            'total_scopes': len(self.storage._scopes),
            'consolidated_entities': len(self.consolidated_memory.entities) if hasattr(self, 'consolidated_memory') else 0,
            'active_foreshadowings': len(self.foreshadowing_tracker.get_active()) if self.foreshadowing_tracker else 0,
        }
        
        # 索引统计
        stats['indexes'] = {
            'entity_index': self._entity_index is not None,
            'inverted_index': self._inverted_index is not None,
            'vector_index': self._vector_index is not None,
            'ngram_index': self._ngram_index is not None,
            'cached_contents': len(self.retriever._content_cache) if hasattr(self.retriever, '_content_cache') else 0,
        }
        
        # 用户特定统计
        if user_id:
            scope = self.storage.get_scope(user_id)
            user_memories = scope.get_all()
            
            # 统计实体分布
            entity_counts = {}
            for m in user_memories:
                for e in m.get('metadata', {}).get('entities', []):
                    entity_counts[e] = entity_counts.get(e, 0) + 1
            
            # 按出现次数排序
            top_entities = sorted(entity_counts.items(), key=lambda x: -x[1])[:20]
            
            stats['user'] = {
                'user_id': user_id,
                'total_memories': len(user_memories),
                'unique_entities': len(entity_counts),
                'top_entities': dict(top_entities),
                # v7.0.7: 直接传 user_id 给 get_active() 避免全量获取后 O(n) 过滤
                'active_foreshadowings': len(self.foreshadowing_tracker.get_active(user_id=user_id)) if self.foreshadowing_tracker else 0,
                'persistent_contexts': self.context_tracker.get_stats(user_id),
            }
        
        # 性能统计
        try:
            stats['performance'] = self.monitor.get_all_stats() if hasattr(self.monitor, 'get_all_stats') else {}
        except Exception:
            stats['performance'] = {}
        
        return stats
    
    def consolidate(self, user_id: str = "default", force: bool = False) -> Optional[Dict]:
        """执行记忆整合 — 委托给 ConsolidationManager 双层策略
        
        双层策略：
        - Hot layer: 每实体一条结构化摘要（≤4000 tokens），参与常规搜索
        - Cold layer: 原文永不删除，标记为 archived，VolumeManager 分卷存储
        
        触发条件（数据量驱动）：
        - 每 1000 条未整合记忆 → 增量实体摘要更新
        - 每 5000 条 → 全量摘要重建
        - force=True → 强制执行（忽略阈值）
        
        Args:
            user_id: 用户 ID
            force: 强制执行（忽略阈值检查）
            
        Returns:
            ConsolidationResult.to_dict() 或 None（如果整合管理器不可用）
        """
        if self.consolidation_manager is not None:
            try:
                result = self.consolidation_manager.consolidate(
                    engine=self, force=force, user_id=user_id
                )
                result_dict = result.to_dict() if hasattr(result, 'to_dict') else {'status': 'completed'}
                _safe_print(f"[Recall] 整合完成: {result_dict.get('memories_processed', 0)} 条记忆已处理")
                return result_dict
            except Exception as e:
                _safe_print(f"[Recall] 整合失败: {e}")
                return {'status': 'error', 'error': str(e)}
        else:
            # Fallback: 旧版简单整合逻辑（ConsolidationManager 不可用时）
            scope = self.storage.get_scope(user_id)
            working = scope.get_all()
            from .processor.memory_summarizer import MemoryItem, MemoryPriority
            items = [
                MemoryItem(
                    id=m.get('id', ''),
                    content=m.get('content', m.get('memory', '')),
                    user_id=user_id,
                    priority=MemoryPriority.NORMAL
                )
                for m in working
            ]
            merged = self.memory_summarizer.merge_similar(items)
            _safe_print(f"[Recall] 整合完成 (fallback): {len(working)} -> {len(merged)}")
            return {'status': 'completed', 'mode': 'fallback', 'original': len(working), 'merged': len(merged)}
    
    def reset(self, user_id: Optional[str] = None):
        """重置（谨慎使用）"""
        if user_id:
            scope = self.storage.get_scope(user_id)
            scope.clear()
        else:
            # 重置所有
            self.storage = MultiTenantStorage(
                base_path=os.path.join(self.data_root, 'data')
            )
            if not self.lightweight:
                self._init_indexes()
        
        _safe_print(f"[Recall] 重置完成")
    
    def close(self):
        """关闭引擎，释放所有资源（包括 SQLite 连接）"""
        # 0. 关闭 Backend Abstraction Layer
        if hasattr(self, '_backend_factory') and self._backend_factory:
            try:
                self._backend_factory.close()
            except Exception:
                pass
        
        # 0.5 关闭直接持有的 BAL 后端引用
        for attr in ('_storage_backend', '_vector_backend', '_text_search_backend'):
            backend = getattr(self, attr, None)
            if backend and hasattr(backend, 'close'):
                try:
                    backend.close()
                except Exception:
                    pass
        
        # 1. 持久化 VolumeManager（确保所有数据保存）
        if self.volume_manager:
            self.volume_manager.flush()
        
        # 2. 保存 N-gram 索引（原文存储）
        if self._ngram_index:
            self._ngram_index.save()
        
        # 3. 保存并关闭向量索引
        if self._vector_index:
            self._vector_index.close()
        
        # 3.1 v7.0.12: VectorIndexIVF 刷盘（之前遗漏）
        if getattr(self, '_vector_index_ivf', None) is not None:
            try:
                self._vector_index_ivf.flush()
                self._vector_index_ivf._save()
            except Exception:
                pass
        
        # 3.5 v7.0.11: 显式刷盘 — 不依赖 atexit（close() 可能在 atexit 之前被调用）
        for idx_attr in ('_entity_index', '_inverted_index', '_metadata_index'):
            idx = getattr(self, idx_attr, None)
            if idx is not None:
                try:
                    if hasattr(idx, 'flush'):
                        idx.flush()
                except Exception:
                    pass
        
        # 3.6 v7.0.11: 时态索引显式刷盘
        if hasattr(self, 'temporal_graph') and self.temporal_graph is not None:
            ti = getattr(self.temporal_graph, '_temporal_index', None)
            if ti is not None and hasattr(ti, 'flush'):
                try:
                    ti.flush()
                except Exception:
                    pass
        
        # 3.7 v7.0.13: ConsolidatedMemory 显式刷盘（add_or_update 不再自动 save）
        if hasattr(self, 'consolidated_memory') and self.consolidated_memory is not None:
            try:
                self.consolidated_memory.flush()
            except Exception:
                pass
        
        # 4. 关闭 TopicCluster（SQLite 连接）
        if hasattr(self, '_topic_cluster') and self._topic_cluster:
            try:
                self._topic_cluster.close()
            except Exception:
                pass
        
        # 5. 关闭 EntityResolver（如有 SQLite 连接）
        if hasattr(self, '_entity_resolver') and self._entity_resolver:
            closer = getattr(self._entity_resolver, 'close', None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass
        
        # 6. 全文索引刷盘 + 关闭
        if hasattr(self, 'fulltext_index') and self.fulltext_index:
            # v7.0.14: 先 flush() 确保 BM25 缓冲数据持久化
            flusher = getattr(self.fulltext_index, 'flush', None)
            if callable(flusher):
                try:
                    flusher()
                except Exception:
                    pass
            closer = getattr(self.fulltext_index, 'close', None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass
        
        # 7. 关闭存储层
        if hasattr(self, 'storage') and self.storage:
            closer = getattr(self.storage, 'close', None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass
        
        # 8. 时序知识图谱刷盘 + 关闭 Kuzu 后端
        if hasattr(self, '_unified_graph') and self._unified_graph:
            graph = self._unified_graph
            # v7.0.14: 先 flush() 确保脏 nodes/edges/episodes 持久化
            if hasattr(graph, 'flush'):
                try:
                    graph.flush()
                except Exception:
                    pass
            # 尝试关闭 Kuzu 后端
            kuzu_be = getattr(graph, '_kuzu_backend', None)
            if kuzu_be and hasattr(kuzu_be, 'close'):
                try:
                    kuzu_be.close()
                except Exception:
                    pass
            # 尝试关闭 graph 本身（如果有 close 方法）
            closer = getattr(graph, 'close', None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass
        
        _safe_print("[Recall] 引擎已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# 便捷函数
def create_engine(**kwargs) -> RecallEngine:
    """创建引擎的便捷函数"""
    return RecallEngine(**kwargs)
