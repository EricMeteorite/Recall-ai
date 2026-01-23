"""Recall 核心引擎 - 统一的记忆管理入口"""

import os
import time
import uuid
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

from .version import __version__
# 注意：RecallInit 和 LightweightConfig 保留用于未来扩展
from .init import RecallInit  # noqa: F401 - 保留用于 CLI 等场景
from .config import LightweightConfig  # noqa: F401 - 保留用于配置迁移
from .models import Entity, EntityType
from .storage import (
    VolumeManager, ConsolidatedMemory, ConsolidatedEntity,
    MultiTenantStorage, MemoryScope, CoreSettings
)
from .index import EntityIndex, InvertedIndex, VectorIndex, OptimizedNgramIndex
from .graph import KnowledgeGraph, RelationExtractor
from .processor import (
    EntityExtractor, ForeshadowingTracker,
    ConsistencyChecker, MemorySummarizer, ScenarioDetector,
    ForeshadowingAnalyzer, ForeshadowingAnalyzerConfig, AnalysisResult,
    ContextTracker, ContextType
)

# v4.0 Phase 1/2 可选模块（延迟导入以保持向后兼容）
# 这些模块仅在配置启用时才会加载
from .processor.foreshadowing import Foreshadowing
from .retrieval import EightLayerRetriever, ContextBuilder
from .utils import (
    LLMClient, WarmupManager, PerformanceMonitor,
    EnvironmentManager
)
from .utils.perf_monitor import MetricType
from .embedding import EmbeddingConfig
from .embedding.base import EmbeddingBackendType


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
        embedding_config: Optional[EmbeddingConfig] = None,
        auto_warmup: bool = True,
        foreshadowing_config: Optional[ForeshadowingAnalyzerConfig] = None
    ):
        """初始化 Recall 引擎
        
        Args:
            data_root: 数据存储根目录，默认为 ./recall_data
            llm_model: LLM 模型名称，默认为 gpt-3.5-turbo
            llm_api_key: LLM API Key
            lightweight: 是否使用轻量模式（约80MB内存，无语义搜索）
            embedding_config: Embedding 配置，支持三种模式：
                - None/自动: 根据环境自动选择
                - EmbeddingConfig.lightweight(): 轻量模式，~100MB内存
                - EmbeddingConfig.hybrid_openai(key): Hybrid模式，~150MB内存
                - EmbeddingConfig.hybrid_siliconflow(key): Hybrid模式（国内）
                - EmbeddingConfig.full(): 完整模式，~1.5GB内存
            auto_warmup: 是否自动预热模型
            foreshadowing_config: 伏笔分析器配置（可选）
                - None/默认: 手动模式，不启用自动分析
                - ForeshadowingAnalyzerConfig.llm_based(...): LLM 辅助模式
        """
        # 1. 初始化环境
        self.env_manager = EnvironmentManager(data_root)
        self.env_manager.setup()
        self.data_root = str(self.env_manager.data_root)
        
        # 2. 加载配置
        self.config = self.env_manager.load_config()
        
        # 保存伏笔分析器配置（稍后在 _init_components 中使用）
        self._foreshadowing_config = foreshadowing_config
        
        # 3. 确定 Embedding 配置
        if lightweight:
            self.embedding_config = EmbeddingConfig.lightweight()
        elif embedding_config:
            self.embedding_config = embedding_config
        else:
            # 自动选择
            from .embedding.factory import auto_select_backend
            self.embedding_config = auto_select_backend()
        
        # 根据最终的 embedding_config 确定是否为轻量模式
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
        print(f"[Recall v{__version__}] 引擎初始化完成 ({mode})")
    
    def _get_mode_name(self) -> str:
        """获取当前模式名称"""
        backend = self.embedding_config.backend
        if backend == EmbeddingBackendType.NONE:
            return "轻量模式"
        elif backend == EmbeddingBackendType.LOCAL:
            return "完整模式"
        elif backend == EmbeddingBackendType.OPENAI:
            return "Hybrid模式-OpenAI"
        elif backend == EmbeddingBackendType.SILICONFLOW:
            return "Hybrid模式-硅基流动"
        elif backend == EmbeddingBackendType.CUSTOM:
            return "Hybrid模式-自定义API"
        return "未知模式"
    
    def _init_components(
        self,
        llm_model: Optional[str],
        llm_api_key: Optional[str]
    ):
        """初始化各组件"""
        # LLM客户端（优先使用 LLM_API_KEY，兼容旧的 OPENAI_API_KEY）
        model = llm_model or os.environ.get('LLM_MODEL') or self.config.get('llm', {}).get('model', 'gpt-4o-mini')
        api_key = llm_api_key or os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')
        api_base = os.environ.get('LLM_API_BASE')
        self.llm_client = LLMClient(model=model, api_key=api_key, api_base=api_base) if api_key else None
        
        if self.llm_client:
            print(f"[Recall] LLM 客户端已初始化 (模型: {model})")
        else:
            print("[Recall] LLM 客户端未初始化（未配置 LLM_API_KEY）")
        
        # 存储层
        self.storage = MultiTenantStorage(
            base_path=os.path.join(self.data_root, 'data')
        )
        
        # 分卷存储（Archive原文保存 - 确保100%不遗忘）
        self.volume_manager = VolumeManager(
            data_path=os.path.join(self.data_root, 'data')
        )
        
        # 索引层（轻量模式延迟加载）
        self._entity_index: Optional[EntityIndex] = None
        self._inverted_index: Optional[InvertedIndex] = None
        self._vector_index: Optional[VectorIndex] = None
        self._ngram_index: Optional[OptimizedNgramIndex] = None
        
        if not self.lightweight:
            self._init_indexes()
        
        # 处理器层（需要先初始化，因为图谱层依赖）
        self.entity_extractor = EntityExtractor()
        
        # 获取Embedding后端（用于语义去重）
        embedding_backend_for_trackers = None
        if self._vector_index and self._vector_index.enabled:
            embedding_backend_for_trackers = self._vector_index.embedding_backend
        
        # 伏笔追踪器（支持语义去重）
        # 使用新的 {user_id}/{character_id}/ 存储结构
        self.foreshadowing_tracker = ForeshadowingTracker(
            base_path=os.path.join(self.data_root, 'data'),
            embedding_backend=embedding_backend_for_trackers
        )
        
        # 伏笔分析器（可选功能，默认手动模式）
        # 传入 memory_provider 用于从已保存记忆获取对话，提高可靠性
        # 传入 storage_dir 用于持久化分析状态，服务器重启不丢失
        self.foreshadowing_analyzer = ForeshadowingAnalyzer(
            tracker=self.foreshadowing_tracker,
            config=self._foreshadowing_config,  # 可能是 None，会使用默认手动模式
            storage_dir=os.path.join(self.data_root, 'data', 'foreshadowing_analyzer'),
            memory_provider=self._get_recent_memories_for_analysis
        )
        
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
        
        # 图谱层
        self.knowledge_graph = KnowledgeGraph(
            data_path=os.path.join(self.data_root, 'data')
        )
        self.relation_extractor = RelationExtractor(
            entity_extractor=self.entity_extractor
        )
        
        # 检索层 - 提供内容回调
        self.retriever = EightLayerRetriever(
            bloom_filter=self._ngram_index.bloom_filter if self._ngram_index else None,
            inverted_index=self._inverted_index,
            entity_index=self._entity_index,
            ngram_index=self._ngram_index,
            vector_index=self._vector_index,
            llm_client=self.llm_client,
            content_store=self._get_memory_content_by_id
        )
        self.context_builder = ContextBuilder()
        
        # 监控
        self.monitor = PerformanceMonitor(auto_collect=False)
        
        # 预加载最近的卷（确保热数据在内存中，支持上万轮RP）
        self.volume_manager.preload_recent()
        
        # 检查并为已有的伏笔/条件补建 VectorIndex 索引（首次升级时执行）
        self._check_and_rebuild_index()
        
        # v4.0 Phase 1 可选模块初始化（基于配置开关）
        self._init_v4_modules()
    
    def _init_v4_modules(self):
        """初始化 v4.0 Phase 1/2 可选模块
        
        这些模块基于配置文件中的开关决定是否启用：
        - TEMPORAL_GRAPH_ENABLED: 时态知识图谱
        - CONTRADICTION_DETECTION_ENABLED: 矛盾检测
        - FULLTEXT_ENABLED: 全文检索 (BM25)
        
        设计原则：
        1. 默认关闭，不影响现有功能
        2. 即使启用失败也不影响引擎运行
        3. 所有 Phase 1 模块都是可选的增强功能
        """
        # 初始化为 None，表示未启用
        self.temporal_graph = None
        self.contradiction_manager = None
        self.fulltext_index = None
        
        # 读取配置（从环境变量）
        temporal_enabled = os.environ.get('TEMPORAL_GRAPH_ENABLED', 'false').lower() == 'true'
        contradiction_enabled = os.environ.get('CONTRADICTION_DETECTION_ENABLED', 'false').lower() == 'true'
        fulltext_enabled = os.environ.get('FULLTEXT_ENABLED', 'false').lower() == 'true'
        
        # 1. 时态知识图谱
        if temporal_enabled:
            try:
                from .graph import TemporalKnowledgeGraph
                self.temporal_graph = TemporalKnowledgeGraph(
                    data_path=os.path.join(self.data_root, 'data')
                )
                print("[Recall v4.0] 时态知识图谱已启用")
            except Exception as e:
                print(f"[Recall v4.0] 时态知识图谱初始化失败（不影响核心功能）: {e}")
        
        # 2. 矛盾检测管理器
        if contradiction_enabled:
            try:
                from .graph import ContradictionManager, DetectionStrategy
                # 策略映射：EMBEDDING->HYBRID, LLM->LLM_ONLY, 默认 HYBRID
                strategy_str = os.environ.get('CONTRADICTION_DETECTION_STRATEGY', 'HYBRID').upper()
                strategy_map = {
                    'EMBEDDING': DetectionStrategy.HYBRID,  # 兼容旧配置
                    'LLM': DetectionStrategy.LLM_ONLY,
                    'HYBRID': DetectionStrategy.HYBRID,
                    'RULE': DetectionStrategy.RULE_ONLY,
                    'AUTO': DetectionStrategy.AUTO,
                }
                strategy = strategy_map.get(strategy_str, DetectionStrategy.HYBRID)
                
                self.contradiction_manager = ContradictionManager(
                    data_path=os.path.join(self.data_root, 'data'),
                    strategy=strategy,
                    llm_client=self.llm_client
                )
                print(f"[Recall v4.0] 矛盾检测已启用 (策略: {strategy.value})")
            except Exception as e:
                print(f"[Recall v4.0] 矛盾检测初始化失败（不影响核心功能）: {e}")
        
        # 3. 全文检索索引 (BM25)
        if fulltext_enabled:
            try:
                from .index import FullTextIndex, BM25Config
                k1 = float(os.environ.get('FULLTEXT_K1', '1.5'))
                b = float(os.environ.get('FULLTEXT_B', '0.75'))
                
                self.fulltext_index = FullTextIndex(
                    data_path=os.path.join(self.data_root, 'index', 'fulltext'),
                    config=BM25Config(k1=k1, b=b)
                )
                print(f"[Recall v4.0] 全文检索已启用 (BM25 k1={k1}, b={b})")
            except Exception as e:
                print(f"[Recall v4.0] 全文检索初始化失败（不影响核心功能）: {e}")
    
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
        
        import logging
        import glob
        logger = logging.getLogger(__name__)
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

    def rebuild_vector_index(self, force: bool = False) -> int:
        """手动重建 VectorIndex 索引
        
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
            print(f"[Recall] 获取记忆失败: {e}")
            return []
    
    def _get_memory_content_by_id(self, memory_id: str) -> Optional[str]:
        """通过 ID 获取记忆内容（供检索器回调）
        
        查找顺序：
        1. MultiTenantStorage 内存缓存（最快）
        2. VolumeManager 存档（确保100%不遗忘）
        3. N-gram 索引的原文缓存（兜底）
        """
        # 1. 先从 MultiTenantStorage 内存中查找（最快）
        for scope_key, scope in self.storage._scopes.items():
            for memory in scope._memories:
                if memory.get('metadata', {}).get('id') == memory_id:
                    return memory.get('content', '')
        
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
                                if mem_id and content:
                                    self.retriever.cache_content(mem_id, content)
                                    count += 1
                    except Exception as e:
                        print(f"[Recall] 加载 {memories_file} 失败: {e}")
        
        if count > 0:
            print(f"[Recall] 已恢复 {count} 条记忆内容到缓存")
    
    def _warmup(self):
        """预热模型（仅完整模式）"""
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
        start_time = time.time()
        consistency_warnings = []  # 收集一致性警告
        
        try:
            # 【新增】去重检查：检查是否已存在完全相同内容的记忆
            scope = self.storage.get_scope(user_id)
            existing_memories = scope.get_all(limit=100)  # 检查最近100条
            content_normalized = content.strip()
            for mem in existing_memories:
                existing_content = mem.get('content', '').strip()
                if existing_content == content_normalized:
                    print(f"[Recall] 跳过重复记忆: content_len={len(content)}, user={user_id}")
                    return AddResult(
                        id=mem.get('metadata', {}).get('id', 'unknown'),
                        success=False,
                        entities=[],
                        message="记忆内容已存在，跳过重复保存"
                    )
            
            # 1. 提取实体
            entities = self.entity_extractor.extract(content)
            entity_names = [e.name for e in entities]
            
            # 2. 提取关键词
            keywords = self.entity_extractor.extract_keywords(content)
            
            # 3. 一致性检查
            if check_consistency:
                existing_memories = self.search(content, user_id=user_id, top_k=5)
                consistency = self.consistency_checker.check(
                    content,
                    [{'content': m.content} for m in existing_memories]
                )
                if not consistency.is_consistent:
                    # 收集警告并记录
                    for v in consistency.violations:
                        warning_msg = v.description
                        consistency_warnings.append(warning_msg)
                        print(f"[Recall] 一致性警告: {warning_msg}")
            
            # 4. 生成ID并存储
            memory_id = f"mem_{uuid.uuid4().hex[:12]}"
            
            memory_data = {
                'id': memory_id,
                'content': content,
                'user_id': user_id,
                'entities': entity_names,
                'keywords': keywords,
                'metadata': metadata or {},
                'created_at': time.time()
            }
            
            # 存储到作用域（核心存储）
            scope = self.storage.get_scope(user_id)
            scope.add(content, metadata={
                'id': memory_id,
                'entities': entity_names,
                'keywords': keywords,
                **(metadata or {})
            })
            
            # === 以下操作失败不影响主流程 ===
            try:
                # 4.5 Archive原文保存（确保100%不遗忘）
                # 将完整对话存入分卷存储，支持任意轮次的O(1)定位
                turn_number = self.volume_manager.append_turn({
                    'memory_id': memory_id,
                    'user_id': user_id,
                    'content': content,
                    'entities': entity_names,
                    'keywords': keywords,
                    'metadata': metadata or {},
                    'created_at': time.time()
                })
            except Exception as e:
                print(f"[Recall] Archive保存失败（不影响主流程）: {e}")
            
            # 5. 更新索引（失败不影响主流程）
            try:
                if self._entity_index:
                    for entity in entities:
                        self._entity_index.add_entity_occurrence(
                            entity_name=entity.name,
                            turn_id=memory_id,
                            context=content[:200]
                        )
                
                if self._inverted_index:
                    self._inverted_index.add_batch(keywords, memory_id)
                
                if self._ngram_index:
                    # NgamIndex.add 接受 (turn_id, content)
                    self._ngram_index.add(memory_id, content)
                
                if self._vector_index:
                    # VectorIndex.add_text 接受 (turn_id, text)
                    self._vector_index.add_text(memory_id, content)
            except Exception as e:
                # 打印更详细的错误信息
                import traceback
                print(f"[Recall] 索引更新失败（不影响主流程）: {type(e).__name__}: {e}")
                traceback.print_exc()
            
            # 5.5 缓存内容到检索器（确保检索时能获取内容）
            try:
                self.retriever.cache_content(memory_id, content)
            except Exception as e:
                print(f"[Recall] 缓存更新失败（不影响主流程）: {type(e).__name__}: {e}")
            
            # 5.6 更新长期记忆（L1 ConsolidatedMemory）
            # 每个实体都会被自动整合和验证
            try:
                for entity in entities:
                    consolidated_entity = ConsolidatedEntity(
                        id=f"entity_{entity.name.lower().replace(' ', '_')}",
                    name=entity.name,
                    entity_type=entity.entity_type if hasattr(entity, 'entity_type') else "UNKNOWN",
                    source_turns=[memory_id],
                    last_verified=time.strftime('%Y-%m-%dT%H:%M:%S')
                )
                self.consolidated_memory.add_or_update(consolidated_entity)
            except Exception as e:
                print(f"[Recall] 长期记忆更新失败（不影响主流程）: {e}")
            
            # 6. 更新知识图谱（失败不影响主流程）
            try:
                relations = self.relation_extractor.extract(content, 0)  # 传入turn=0
                for rel in relations:
                    source_id, relation_type, target_id, source_text = rel
                    self.knowledge_graph.add_relation(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type=relation_type,
                        source_text=source_text
                    )
            except Exception as e:
                print(f"[Recall] 知识图谱更新失败（不影响主流程）: {e}")
            
            # 7. 自动提取持久条件（已移至 server.py 中处理，避免 character_id 传递问题）
            # 注意：之前这里调用 extract_from_text 时没有传递 character_id，
            # 导致所有条件都存储到 "default" 角色下，与其他角色数据混淆。
            # 现在由 server.py 在添加记忆后正确传递 character_id 来提取条件。
            
            # 记录性能
            try:
                self.monitor.record(
                    MetricType.LATENCY,
                    (time.time() - start_time) * 1000
                )
            except Exception:
                pass  # 忽略性能监控错误
            
            return AddResult(
                id=memory_id,
                success=True,
                entities=entity_names,
                message="记忆添加成功",
                consistency_warnings=consistency_warnings
            )
        
        except Exception as e:
            print(f"[Recall] 添加记忆异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return AddResult(
                id="",
                success=False,
                message=f"添加失败: {str(e)}"
            )
    
    def search(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """搜索记忆
        
        Args:
            query: 搜索查询
            user_id: 用户ID
            top_k: 返回数量
            filters: 过滤条件
        
        Returns:
            List[SearchResult]: 搜索结果
        """
        # 1. 提取查询实体和关键词
        entities = [e.name for e in self.entity_extractor.extract(query)]
        keywords = self.entity_extractor.extract_keywords(query)
        
        # 2. 检测场景
        scenario = self.scenario_detector.detect(query)
        
        # 3. 执行检索
        retrieval_results = self.retriever.retrieve(
            query=query,
            entities=entities,
            keywords=keywords,
            top_k=top_k,
            filters=filters
        )
        
        # 4. 补充从存储获取
        scope = self.storage.get_scope(user_id)
        stored_memories = scope.search(query, limit=top_k)
        
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
        """获取单条记忆
        
        Args:
            memory_id: 记忆ID
            user_id: 用户ID
        
        Returns:
            Dict: 记忆数据，如果不存在则返回 None
        """
        scope = self.storage.get_scope(user_id)
        all_memories = scope.get_all()
        for memory in all_memories:
            if memory.get('metadata', {}).get('id') == memory_id:
                return memory
        return None
    
    def clear(
        self,
        user_id: str = "default"
    ) -> bool:
        """清空用户的所有记忆
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否成功
        """
        scope = self.storage.get_scope(user_id)
        scope.clear()
        return True
    
    def stats(self) -> Dict[str, Any]:
        """获取统计信息（get_stats 的别名）"""
        return self.get_stats()
    
    def delete(
        self,
        memory_id: str,
        user_id: str = "default"
    ) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆ID
            user_id: 用户ID
        
        Returns:
            bool: 是否成功
        """
        scope = self.storage.get_scope(user_id)
        return scope.delete(memory_id)
    
    def update(
        self,
        memory_id: str,
        content: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新记忆
        
        Args:
            memory_id: 记忆ID
            content: 新内容
            user_id: 用户ID
            metadata: 新元数据
        
        Returns:
            bool: 是否成功
        """
        scope = self.storage.get_scope(user_id)
        return scope.update(memory_id, content, metadata)
    
    def build_context(
        self,
        query: str,
        user_id: str = "default",
        character_id: str = "default",
        max_tokens: int = 2000,
        include_recent: int = None,  # 从配置读取默认值
        include_core_facts: bool = True,
        auto_extract_context: bool = False  # 默认关闭，避免每次生成都提取条件
    ) -> str:
        """构建上下文 - 全方位记忆策略，确保100%不遗漏任何细节
        
        七层上下文策略（100%不遗忘保证）：
        1. 持久条件层 - 已确立的背景设定（如用户身份、环境、目标）
        2. 核心事实层 - 压缩的实体知识 + 关系图谱
        3. 相关记忆层 - 与查询相关的详细记忆
        4. 关键实体补充层 - 从持久条件和伏笔中提取关键词，补充检索（新增）
        5. 最近对话层 - 保持对话连贯性
        6. 伏笔层 - 所有活跃伏笔 + 主动提醒
        7. 场景优化层 - 根据场景调整检索策略
        
        Args:
            query: 当前查询
            user_id: 用户ID
            character_id: 角色ID
            max_tokens: 最大token数（越大能注入越多细节）
            include_recent: 包含的最近对话数（None 时从配置读取 BUILD_CONTEXT_INCLUDE_RECENT）
            include_core_facts: 是否包含核心事实摘要
            auto_extract_context: 是否自动从查询中提取持久条件（默认False，条件提取在保存记忆时进行）
        
        Returns:
            str: 构建的上下文
        """
        import time as _time
        import os as _os
        start_time = _time.time()
        
        # 从配置读取默认值
        if include_recent is None:
            include_recent = int(_os.environ.get('BUILD_CONTEXT_INCLUDE_RECENT', '10'))
        proactive_enabled = _os.environ.get('PROACTIVE_REMINDER_ENABLED', 'true').lower() in ('true', '1', 'yes')
        proactive_turns = int(_os.environ.get('PROACTIVE_REMINDER_TURNS', '50'))
        
        query_preview = query[:50].replace('\n', ' ') if len(query) > 50 else query.replace('\n', ' ')
        print(f"[Recall][Engine] 📦 构建上下文: user={user_id}, char={character_id}")
        print(f"[Recall][Engine]    查询: {query_preview}{'...' if len(query) > 50 else ''}")
        print(f"[Recall][Engine]    参数: max_tokens={max_tokens}, recent={include_recent}, proactive={proactive_enabled}")
        parts = []
        
        # ========== 0. 场景检测（决定检索策略）==========
        scenario = self.scenario_detector.detect(query)
        retrieval_strategy = scenario.suggested_retrieval_strategy
        
        # ========== 0.5 L0 核心设定注入（角色卡/世界观/规则 - 最高优先级）==========
        if hasattr(self, 'core_settings') and self.core_settings:
            # 根据场景类型获取对应的核心设定
            scenario_type = 'roleplay' if scenario.type.value in ['roleplay', 'novel_writing', 'worldbuilding'] else 'coding' if scenario.type.value == 'coding' else 'general'
            injection_text = self.core_settings.get_injection_text(scenario_type)
            if injection_text:
                parts.append(f"【核心设定】\n{injection_text}")
        
        # ========== 1. 持久条件层（已确立的背景设定）==========
        # 这是最重要的层 - 用户说"我是大学生想创业"，后续所有对话都应基于此
        active_contexts = self.context_tracker.get_active(user_id, character_id)
        if active_contexts:
            # 批量标记所有被使用的条件（更新 last_used 和 use_count，只写一次文件）
            context_ids = [ctx.id for ctx in active_contexts]
            self.context_tracker.mark_used_batch(context_ids, user_id, character_id)
            
            persistent_context = self.context_tracker.format_for_prompt(user_id, character_id)
            if persistent_context:
                parts.append(persistent_context)
        
        # 自动从当前查询中提取新的持久条件
        if auto_extract_context and query:
            self.context_tracker.extract_from_text(query, user_id, character_id)
        
        # ========== 2. 核心事实层 + 关系图谱 ==========
        if include_core_facts:
            core_facts = self._build_core_facts_section(user_id, max_tokens // 5)
            if core_facts:
                parts.append(core_facts)
            
            # 利用知识图谱扩展相关实体
            graph_context = self._build_graph_context(query, user_id, max_tokens // 10)
            if graph_context:
                parts.append(graph_context)
        
        # ========== 3. 相关记忆层（详细记忆）==========
        # 根据场景和 token 预算动态调整检索数量
        top_k = self._calculate_top_k(max_tokens, retrieval_strategy)
        memories = self.search(query, user_id=user_id, top_k=top_k)
        
        if memories:
            memory_section = self._build_memory_section(memories, max_tokens // 3)
            if memory_section:
                parts.append(memory_section)
        
        # ========== 3.5 关键实体补充检索层（100%不遗忘保证）==========
        # 从持久条件和伏笔中提取关键词，进行补充检索
        # 确保即使 query 中没有直接提及，重要信息也能被召回
        supplementary_keywords = self._extract_supplementary_keywords(user_id, character_id, active_contexts)
        if supplementary_keywords:
            supplementary_memories = self._search_by_keywords(supplementary_keywords, user_id, top_k=5)
            if supplementary_memories:
                # 过滤掉已经在 memories 中的记忆
                existing_ids = {m.id for m in memories} if memories else set()
                new_supplementary = [m for m in supplementary_memories if m.id not in existing_ids]
                if new_supplementary:
                    supplementary_section = self._build_supplementary_section(new_supplementary)
                    if supplementary_section:
                        parts.append(supplementary_section)
        
        # ========== 4. 最近对话层 ==========
        scope = self.storage.get_scope(user_id)
        recent = scope.get_recent(include_recent)
        
        if recent:
            recent_section = self._build_recent_section(recent)
            if recent_section:
                parts.append(recent_section)
        
        # ========== 5. 伏笔层（所有活跃伏笔 + 主动提醒）==========
        # 使用 tracker 的专用方法，包含主动提醒逻辑（重要伏笔长期未推进会提醒 AI）
        foreshadowing_context = self.foreshadowing_tracker.get_context_for_prompt(
            user_id=user_id,
            character_id=character_id,
            max_count=5,
            current_turn=self.volume_manager.get_total_turns() if self.volume_manager else None
        )
        if foreshadowing_context:
            parts.append(foreshadowing_context)
        
        # ========== 5.5 主动提醒层（100%不遗忘保证）==========
        # 对长期未提及的重要持久条件进行主动提醒
        if proactive_enabled and active_contexts:
            proactive_reminders = self._build_proactive_reminders(
                active_contexts, proactive_turns, user_id
            )
            if proactive_reminders:
                parts.append(proactive_reminders)
        
        elapsed = _time.time() - start_time
        total_len = sum(len(p) for p in parts)
        print(f"[Recall][Engine] ✅ 构建完成: 耗时={elapsed:.3f}s")
        print(f"[Recall][Engine]    层数={len(parts)}, 总长度={total_len}字符")
        if parts:
            print(f"[Recall][Engine]    包含: {[p[:20] + '...' for p in parts]}")
        
        return "\n".join(parts)
    
    def _calculate_top_k(self, max_tokens: int, strategy: str) -> int:
        """根据策略和token预算计算检索数量"""
        base_k = max(10, min(50, max_tokens // 100))
        
        # 根据场景调整
        strategy_multipliers = {
            'entity_focused': 1.5,      # 角色扮演需要更多实体信息
            'keyword_exact': 0.8,       # 代码场景精确匹配，不需要太多
            'semantic_broad': 1.2,      # 知识问答需要广泛检索
            'creative_blend': 1.3,      # 创意写作需要多样性
            'task_relevant': 0.7,       # 任务执行聚焦相关
            'recent_context': 0.5,      # 闲聊主要靠最近上下文
            'hybrid_balanced': 1.0,     # 默认平衡
        }
        
        multiplier = strategy_multipliers.get(strategy, 1.0)
        return int(base_k * multiplier)
    
    def _build_graph_context(self, query: str, user_id: str, budget: int) -> str:
        """利用知识图谱构建关系上下文"""
        # 从查询中提取实体
        entities = [e.name for e in self.entity_extractor.extract(query)]
        if not entities:
            return ""
        
        lines = []
        current_length = 0
        
        for entity_name in entities[:5]:  # 最多处理5个实体
            # 获取该实体的关系
            neighbors = self.knowledge_graph.get_neighbors(entity_name, direction='both')
            if neighbors:
                for neighbor_id, relation in neighbors[:3]:  # 每个实体最多3个关系
                    rel_text = f"• {entity_name} --[{relation.relation_type}]--> {neighbor_id}"
                    if current_length + len(rel_text) > budget:
                        break
                    lines.append(rel_text)
                    current_length += len(rel_text)
        
        if lines:
            return "<relationships>\n【关系图谱】\n" + "\n".join(lines) + "\n</relationships>"
        return ""
    
    def _build_core_facts_section(self, user_id: str, budget: int) -> str:
        """构建核心事实部分 - 从 L1 ConsolidatedMemory 获取压缩知识"""
        # 获取所有已验证的实体和核心事实
        all_entities = list(self.consolidated_memory.entities.values()) if hasattr(self, 'consolidated_memory') else []
        
        if not all_entities:
            # 如果没有整合的记忆，尝试生成摘要
            return self._generate_memory_summary(user_id, budget)
        
        lines = ["<core_facts>", "【核心知识库】以下是已确认的关键信息："]
        current_length = 0
        
        # 按置信度排序，优先高置信度的
        sorted_entities = sorted(all_entities, key=lambda e: -e.confidence)
        
        for entity in sorted_entities:
            fact_line = f"• {entity.name}"
            if entity.entity_type != "UNKNOWN":
                fact_line += f" ({entity.entity_type})"
            if entity.current_state:
                states = [f"{k}:{v}" for k, v in list(entity.current_state.items())[:3]]
                fact_line += f": {', '.join(states)}"
            
            if current_length + len(fact_line) > budget:
                break
            lines.append(fact_line)
            current_length += len(fact_line)
        
        lines.append("</core_facts>")
        return "\n".join(lines) if len(lines) > 3 else ""
    
    def _generate_memory_summary(self, user_id: str, budget: int) -> str:
        """生成记忆摘要 - 当没有整合记忆时使用"""
        scope = self.storage.get_scope(user_id)
        all_memories = scope.get_all(limit=100)  # 获取最多100条
        
        if not all_memories or len(all_memories) < 5:
            return ""
        
        # 如果有 LLM，使用 LLM 生成摘要
        if self.llm_client and self.memory_summarizer:
            try:
                from .processor.memory_summarizer import MemoryItem
                memory_items = []
                for m in all_memories:
                    memory_items.append(MemoryItem(
                        id=m.get('metadata', {}).get('id', ''),
                        content=m.get('content', ''),
                        user_id=user_id
                    ))
                summary = self.memory_summarizer.summarize_memories(memory_items, max_length=budget)
                if summary:
                    return f"<memory_summary>\n【历史摘要】\n{summary}\n</memory_summary>"
            except Exception as e:
                pass  # 静默失败，使用备用方案
        
        # 备用方案：简单提取关键词和实体
        entities_set = set()
        for m in all_memories:
            entities = m.get('metadata', {}).get('entities', [])
            entities_set.update(entities)
        
        if entities_set:
            return f"<memory_summary>\n【涉及的角色/事物】{', '.join(list(entities_set)[:20])}\n</memory_summary>"
        
        return ""
    
    def _build_memory_section(self, memories, budget: int) -> str:
        """构建详细记忆部分（自动去重）"""
        if not memories:
            return ""
        
        lines = ["<memories>", "【相关记忆】"]
        current_length = 0
        seen_contents = set()  # 用于去重
        
        for m in memories:
            content = m.content if hasattr(m, 'content') else m.get('content', '')
            
            # 去重：跳过已经添加过的相同内容
            content_key = content.strip().lower()
            if content_key in seen_contents:
                continue
            seen_contents.add(content_key)
            
            entities = m.entities if hasattr(m, 'entities') else m.get('entities', [])
            
            line = f"• {content}"
            if entities:
                line = f"• [涉及: {', '.join(entities[:3])}] {content}"
            
            if current_length + len(line) > budget:
                lines.append("...")
                break
            lines.append(line)
            current_length += len(line)
        
        lines.append("</memories>")
        return "\n".join(lines) if len(lines) > 3 else ""
    
    def _build_recent_section(self, recent) -> str:
        """构建最近对话部分"""
        if not recent:
            return ""
        
        lines = ["<recent_conversation>"]
        for turn in recent:
            role = turn.get('metadata', {}).get('role', 'user')
            content = turn.get('content', '')
            lines.append(f"{role}: {content}")
        lines.append("</recent_conversation>")
        return "\n".join(lines)
    
    def _extract_supplementary_keywords(
        self,
        user_id: str,
        character_id: str,
        active_contexts: List
    ) -> List[str]:
        """从持久条件和伏笔中提取关键词用于补充检索
        
        确保重要信息即使在当前 query 中未提及也能被召回
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            active_contexts: 活跃的持久条件列表
            
        Returns:
            List[str]: 关键词列表
        """
        keywords = set()
        
        # 从持久条件中提取关键词
        if active_contexts:
            for ctx in active_contexts:
                # 获取关键词
                ctx_keywords = ctx.keywords if hasattr(ctx, 'keywords') else ctx.get('keywords', [])
                if ctx_keywords:
                    keywords.update(ctx_keywords[:3])  # 每个条件最多取3个关键词
        
        # 从活跃伏笔中提取关键实体
        try:
            foreshadowings = self.foreshadowing_tracker.get_active(user_id, character_id)
            for fsh in foreshadowings[:5]:  # 最多5个伏笔
                entities = fsh.related_entities if hasattr(fsh, 'related_entities') else []
                if entities:
                    keywords.update(entities[:2])  # 每个伏笔最多取2个实体
        except Exception:
            pass
        
        return list(keywords)[:10]  # 总共最多10个关键词
    
    def _search_by_keywords(
        self,
        keywords: List[str],
        user_id: str,
        top_k: int = 5
    ) -> List:
        """根据关键词列表进行补充检索
        
        Args:
            keywords: 关键词列表
            user_id: 用户ID
            top_k: 返回的最大记忆数
            
        Returns:
            List: 相关记忆列表
        """
        if not keywords:
            return []
        
        all_memories = []
        seen_ids = set()
        
        for keyword in keywords[:5]:  # 最多使用5个关键词
            try:
                memories = self.search(keyword, user_id=user_id, top_k=2)
                for m in memories:
                    mem_id = m.id if hasattr(m, 'id') else m.get('id', '')
                    if mem_id and mem_id not in seen_ids:
                        seen_ids.add(mem_id)
                        all_memories.append(m)
                        if len(all_memories) >= top_k:
                            return all_memories
            except Exception:
                continue
        
        return all_memories
    
    def _build_supplementary_section(self, memories) -> str:
        """构建补充检索记忆部分
        
        Args:
            memories: 补充检索到的记忆列表
            
        Returns:
            str: 格式化的补充记忆文本
        """
        if not memories:
            return ""
        
        lines = ["<supplementary_memories>", "【相关背景（补充召回）】"]
        
        for m in memories[:5]:  # 最多5条
            content = m.content if hasattr(m, 'content') else m.get('content', '')
            entities = m.entities if hasattr(m, 'entities') else m.get('entities', [])
            
            line = f"• {content}"
            if entities:
                line = f"• [涉及: {', '.join(entities[:3])}] {content}"
            lines.append(line)
        
        lines.append("</supplementary_memories>")
        return "\n".join(lines) if len(lines) > 3 else ""
    
    def _build_proactive_reminders(
        self,
        active_contexts: List,
        threshold_turns: int,
        user_id: str
    ) -> str:
        """构建主动提醒文本（对长期未提及的重要持久条件）
        
        类似于伏笔的主动提醒机制，确保重要背景信息不会被遗忘
        
        Args:
            active_contexts: 活跃的持久条件列表
            threshold_turns: 触发提醒的轮次阈值
            user_id: 用户ID
            
        Returns:
            str: 主动提醒文本，如果没有需要提醒的内容则返回空字符串
        """
        if not active_contexts:
            return ""
        
        # 获取当前总轮次
        current_turn = 0
        if self.volume_manager:
            current_turn = self.volume_manager.get_total_turns()
        
        reminders = []
        
        for ctx in active_contexts:
            # 获取最后提及轮次 - PersistentContext 是 dataclass，使用 getattr
            last_mentioned = getattr(ctx, 'last_mentioned_turn', None) or getattr(ctx, 'use_count', 0)
            importance = getattr(ctx, 'importance', None) or getattr(ctx, 'confidence', 0.5)
            content = getattr(ctx, 'content', '')
            
            # 计算未提及的轮次数
            turns_since_mention = current_turn - last_mentioned if last_mentioned else current_turn
            
            # 高重要性条件阈值减半
            effective_threshold = threshold_turns // 2 if importance > 0.7 else threshold_turns
            
            if turns_since_mention >= effective_threshold and importance >= 0.5:
                reminders.append({
                    'content': content,
                    'importance': importance,
                    'turns_since': turns_since_mention
                })
        
        if not reminders:
            return ""
        
        # 按重要性和未提及时长排序
        reminders.sort(key=lambda x: (x['importance'], x['turns_since']), reverse=True)
        
        lines = [
            "<proactive_reminders>",
            "【重要背景提醒】以下是你可能需要注意的重要背景信息（长期未在对话中涉及）："
        ]
        
        for r in reminders[:3]:  # 最多提醒3条
            importance_label = "高" if r['importance'] > 0.7 else "中"
            lines.append(f"• [{importance_label}重要性，{r['turns_since']}轮未提及] {r['content']}")
        
        lines.append("</proactive_reminders>")
        return "\n".join(lines)
    
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
        return self.foreshadowing_tracker.abandon(foreshadowing_id, user_id, character_id)
    
    def get_active_foreshadowings(self, user_id: str = "default", character_id: str = "default") -> List[Foreshadowing]:
        """获取活跃伏笔"""
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
        return self.foreshadowing_tracker.get_by_id(foreshadowing_id, user_id, character_id)
    
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
        return self.foreshadowing_analyzer.trigger_analysis(user_id, character_id)
    
    def get_foreshadowing_analyzer_config(self) -> Dict[str, Any]:
        """获取伏笔分析器配置"""
        return self.foreshadowing_analyzer.config.to_dict()
    
    def update_foreshadowing_analyzer_config(
        self,
        trigger_interval: Optional[int] = None,
        auto_plant: Optional[bool] = None,
        auto_resolve: Optional[bool] = None
    ):
        """更新伏笔分析器配置"""
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
        self.foreshadowing_analyzer.enable_llm_mode(
            api_key=api_key,
            model=model,
            base_url=base_url
        )
    
    def disable_foreshadowing_llm_mode(self):
        """禁用伏笔分析器的 LLM 模式，切换回手动模式"""
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
                    'mention_count': len(indexed.turn_references),
                    'related_turns': indexed.turn_references[:10]
                }
        return None
    
    def get_related_entities(self, name: str) -> List[str]:
        """获取相关实体"""
        neighbors = self.knowledge_graph.get_neighbors(name)
        return [neighbor_id for neighbor_id, _ in neighbors]
    
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
                memory_id = m.get('id', '')
                content = m.get('content', m.get('memory', ''))
                if memory_id and content:
                    memories_to_index.append((memory_id, content))
            print(f"[Recall] 重建向量索引: user={user_id}, 记忆数={len(memories_to_index)}")
        else:
            # 重建所有用户
            for scope_key, scope in self.storage._scopes.items():
                for m in scope.get_all():
                    memory_id = m.get('id', '')
                    content = m.get('content', m.get('memory', ''))
                    if memory_id and content:
                        memories_to_index.append((memory_id, content))
            print(f"[Recall] 重建向量索引: 全部用户, 记忆数={len(memories_to_index)}")
        
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
            'lightweight': self.lightweight,
        }
        
        # 全局统计
        total_memories = 0
        total_entities_in_memories = 0
        
        for scope_key, scope in self.storage._scopes.items():
            memories = scope.get_all()
            total_memories += len(memories)
            for m in memories:
                entities = m.get('metadata', {}).get('entities', [])
                total_entities_in_memories += len(entities)
        
        stats['global'] = {
            'total_memories': total_memories,
            'total_scopes': len(self.storage._scopes),
            'consolidated_entities': len(self.consolidated_memory.entities) if hasattr(self, 'consolidated_memory') else 0,
            'active_foreshadowings': len(self.foreshadowing_tracker.get_active()),
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
                'active_foreshadowings': len([f for f in self.foreshadowing_tracker.get_active() 
                                              if hasattr(f, 'user_id') and f.user_id == user_id]),
                'persistent_contexts': self.context_tracker.get_stats(user_id),
            }
        
        # 性能统计
        try:
            stats['performance'] = self.monitor.get_all_stats() if hasattr(self.monitor, 'get_all_stats') else {}
        except:
            stats['performance'] = {}
        
        return stats
    
    def consolidate(self, user_id: str = "default"):
        """执行记忆整合"""
        scope = self.storage.get_scope(user_id)
        
        # 获取工作记忆
        working = scope.get_all()
        
        # 使用摘要器压缩
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
        
        # 合并相似记忆
        merged = self.memory_summarizer.merge_similar(items)
        
        # 移动到整合层
        # TODO: 实现实际的整合逻辑
        
        print(f"[Recall] 整合完成: {len(working)} -> {len(merged)}")
    
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
        
        print(f"[Recall] 重置完成")
    
    def close(self):
        """关闭引擎"""
        # 1. 持久化 VolumeManager（确保所有数据保存）
        if self.volume_manager:
            self.volume_manager.flush()
        
        # 2. 保存 N-gram 索引（原文存储）
        if self._ngram_index:
            self._ngram_index.save()
        
        # 3. 保存并关闭向量索引
        if self._vector_index:
            self._vector_index.close()
        
        print("[Recall] 引擎已关闭")


# 便捷函数
def create_engine(**kwargs) -> RecallEngine:
    """创建引擎的便捷函数"""
    return RecallEngine(**kwargs)
