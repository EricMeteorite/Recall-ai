"""配置管理 - 包含 Lite 模式配置 + Phase 3.6 三路召回配置"""

import os
import re
from typing import List
from dataclasses import dataclass

# v5.0 便捷 re-export
from .mode import RecallMode, get_mode_config  # noqa: F401


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


class LiteConfig:
    """Lite 模式 - 适合低配电脑（原 LightweightConfig）"""
    
    # 禁用重型组件
    ENABLE_VECTOR_INDEX = False      # 不加载 sentence-transformers (~400MB)
    ENABLE_SPACY_FULL = False        # 不加载完整 spaCy 模型 (~50MB)
    
    # 使用轻量替代
    ENTITY_EXTRACTOR = 'jieba_rules'  # 用 jieba + 规则替代 spaCy
    RETRIEVAL_LAYERS = [1, 2, 3, 5, 7, 8]  # 跳过第4层(向量)和第6层(语义)
    
    # 内存限制
    MAX_CACHED_TURNS = 1000          # 减少缓存
    MAX_INDEX_SIZE_MB = 30           # 限制索引大小
    
    @classmethod
    def apply(cls, engine):
        """应用轻量配置"""
        engine.config = engine.config or {}
        engine.config.update({
            'vector_enabled': False,
            'spacy_model': 'blank',
            'retrieval_layers': cls.RETRIEVAL_LAYERS,
            'max_cache': cls.MAX_CACHED_TURNS,
        })
        _safe_print("[Recall] Lite 模式已启用，内存占用约 ~80MB")


@dataclass
class LightweightExtractedEntity:
    """轻量版提取实体"""
    name: str
    entity_type: str
    confidence: float = 0.5
    source_text: str = ""


class LightweightEntityExtractor:
    """轻量级实体提取器 - 不依赖 spaCy"""
    
    def __init__(self):
        self.re = re
        self._jieba = None  # 懒加载
        
        # 简单的命名实体模式
        self.patterns = {
            'PERSON': r'[「『"]([\u4e00-\u9fa5]{2,4})[」』"]说|(\w{2,10})先生|(\w{2,10})女士',
            'LOCATION': r'在([\u4e00-\u9fa5]{2,10})|去([\u4e00-\u9fa5]{2,10})',
            'ITEM': r'[「『"]([\u4e00-\u9fa5a-zA-Z]{2,20})[」』"]',
        }
        
        # 停用词
        self.stopwords = {
            '的', '了', '是', '在', '和', '有', '这', '那', '就', '都', 
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would'
        }
    
    @property
    def jieba(self):
        """懒加载 jieba"""
        if self._jieba is None:
            import jieba
            self._jieba = jieba
        return self._jieba
    
    def extract(self, text: str) -> List[LightweightExtractedEntity]:
        """提取实体（轻量版），返回与 EntityExtractor 兼容的对象"""
        entities = []
        seen_names = set()
        
        # 1. 正则模式匹配
        for entity_type, pattern in self.patterns.items():
            for match in self.re.finditer(pattern, text):
                name = next((g for g in match.groups() if g), None)
                if name and len(name) >= 2 and name not in seen_names:
                    entities.append(LightweightExtractedEntity(
                        name=name,
                        entity_type=entity_type,
                        confidence=0.6,
                        source_text=text[max(0, match.start()-20):match.end()+20]
                    ))
                    seen_names.add(name)
        
        # 2. jieba 分词 + 词性标注
        try:
            import jieba.posseg as pseg
            words = pseg.cut(text[:5000])  # 限制长度
            for word, flag in words:
                if flag in ('nr', 'ns', 'nt', 'nz') and len(word) >= 2 and word not in seen_names:
                    entity_type = {
                        'nr': 'PERSON', 
                        'ns': 'LOCATION', 
                        'nt': 'ORG', 
                        'nz': 'ITEM'
                    }.get(flag, 'MISC')
                    entities.append(LightweightExtractedEntity(
                        name=word,
                        entity_type=entity_type,
                        confidence=0.5,
                        source_text=""
                    ))
                    seen_names.add(word)
        except ImportError:
            pass  # jieba 未安装时跳过
        
        return entities
    
    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词（轻量版）"""
        # 中文词组
        chinese = self.re.findall(r'[\u4e00-\u9fa5]{2,6}', text)
        # 英文单词
        english = self.re.findall(r'[a-zA-Z]{3,}', text.lower())
        # 过滤停用词
        return [w for w in chinese + english if w not in self.stopwords]


# ============================================================================
# 向后兼容别名
# ============================================================================
LightweightConfig = LiteConfig  # 兼容旧代码


# ============================================================================
# v7.0 D5: 环境变量集中配置（消除散落的 os.environ.get 默认值不一致问题）
# ============================================================================
@dataclass
class RecallConfig:
    """Recall 全局配置 — 所有 os.environ.get() 散落的默认值集中管理。

    v7.0: 单一 universal 模式，所有默认值与 api_keys.env 模板保持 100% 一致。

    用法::

        cfg = RecallConfig.from_env()   # 一次性读取所有环境变量
        cfg.llm_model                   # 'gpt-4o-mini'
    """

    # ── 数据 & 系统 ──
    recall_data_root: str = './recall_data'
    recall_mode: str = 'universal'           # v7.0: 唯一模式 universal
    admin_key: str = ''

    # ── Embedding ──
    embedding_api_key: str = ''
    embedding_api_base: str = ''
    embedding_model: str = 'text-embedding-3-small'
    embedding_dimension: int = 0             # 0 = 自动查表
    recall_embedding_mode: str = 'auto'      # auto / lite / local / cloud / none
    embedding_rate_limit: int = 10
    embedding_rate_window: int = 60

    # ── LLM ──
    llm_api_key: str = ''
    llm_api_base: str = ''
    llm_model: str = 'gpt-4o-mini'
    llm_timeout: float = 60.0
    llm_default_max_tokens: int = 2000
    llm_relation_max_tokens: int = 4000
    llm_relation_mode: str = 'llm'          # rules / adaptive / llm

    # ── Smart Extractor ──
    smart_extractor_mode: str = 'RULES'   # RULES / ADAPTIVE / LLM (RULES=零LLM成本)   # RULES / ADAPTIVE / LLM
    smart_extractor_complexity_threshold: float = 0.6
    smart_extractor_enable_temporal: bool = True
    smart_extractor_max_tokens: int = 2000

    # ── Context ──
    context_trigger_interval: int = 5
    context_max_context_turns: int = 20
    context_max_per_type: int = 10
    context_max_total: int = 100
    context_decay_days: int = 14
    context_decay_rate: float = 0.05
    context_min_confidence: float = 0.1
    context_extraction_max_tokens: int = 2000
    build_context_include_recent: int = 10
    build_context_max_tokens: int = 4000

    # ── Proactive Reminder ──
    proactive_reminder_enabled: bool = True
    proactive_reminder_turns: int = 50

    # ── Foreshadowing ──
    foreshadowing_llm_enabled: bool = True
    foreshadowing_trigger_interval: int = 10
    foreshadowing_auto_plant: bool = True
    foreshadowing_auto_resolve: bool = False
    foreshadowing_max_return: int = 10
    foreshadowing_max_active: int = 50
    foreshadowing_max_tokens: int = 2000
    foreshadowing_enabled: bool = True

    # ── Dedup ──
    dedup_embedding_enabled: bool = True
    dedup_high_threshold: float = 0.85
    dedup_low_threshold: float = 0.70
    dedup_llm_max_tokens: int = 100
    embedding_reuse_enabled: bool = True
    dedup_jaccard_threshold: float = 0.85
    dedup_semantic_threshold: float = 0.90
    dedup_semantic_low_threshold: float = 0.80
    dedup_llm_enabled: bool = False

    # ── Graph ──
    temporal_graph_enabled: bool = True
    temporal_graph_backend: str = 'file'     # file / kuzu
    kuzu_buffer_pool_size: int = 1024
    temporal_decay_rate: float = 0.1
    temporal_max_history: int = 1000
    community_detection_enabled: bool = False
    community_detection_algorithm: str = 'louvain'
    community_min_size: int = 2
    llm_relation_complexity_threshold: float = 0.5
    llm_relation_enable_temporal: bool = True
    llm_relation_enable_fact_description: bool = True

    # ── Contradiction ──
    contradiction_detection_enabled: bool = True
    contradiction_auto_resolve: bool = False
    contradiction_detection_strategy: str = 'MIXED'
    contradiction_similarity_threshold: float = 0.8
    contradiction_max_tokens: int = 1000

    # ── Full-text Search ──
    fulltext_enabled: bool = True
    fulltext_k1: float = 1.5
    fulltext_b: float = 0.75
    fulltext_weight: float = 0.3

    # ── Budget ──
    budget_daily_limit: float = 0.0
    budget_hourly_limit: float = 0.0
    budget_reserve: float = 0.1
    budget_alert_threshold: float = 0.8

    # ── Index / IVF ──
    ivf_auto_switch_threshold: int = 50000

    # ── Eleven Layer Retriever ──
    eleven_layer_retriever_enabled: bool = True
    retrieval_l1_bloom_enabled: bool = True
    retrieval_l2_temporal_enabled: bool = True
    retrieval_l3_inverted_enabled: bool = True
    retrieval_l4_entity_enabled: bool = True
    retrieval_l5_graph_enabled: bool = True
    retrieval_l6_ngram_enabled: bool = True
    retrieval_l7_vector_coarse_enabled: bool = True
    retrieval_l8_vector_fine_enabled: bool = True
    retrieval_l9_rerank_enabled: bool = True
    retrieval_l10_cross_encoder_enabled: bool = True
    retrieval_l11_llm_enabled: bool = True
    retrieval_final_top_k: int = 20
    retrieval_fine_rank_threshold: int = 100
    retrieval_llm_max_tokens: int = 200

    # ── Query Planner / Community ──
    query_planner_enabled: bool = True
    query_planner_cache_size: int = 1000
    query_planner_cache_ttl: int = 300

    # ── Triple Recall ──
    triple_recall_enabled: bool = True
    triple_recall_rrf_k: int = 60
    triple_recall_vector_weight: float = 1.0
    triple_recall_keyword_weight: float = 1.2
    triple_recall_entity_weight: float = 1.0

    # ── Entity Summary ──
    entity_summary_enabled: bool = True
    entity_summary_min_facts: int = 5
    entity_summary_max_tokens: int = 2000

    # ── Turn API / Unified Analyzer ──
    turn_api_enabled: bool = True
    unified_analyzer_enabled: bool = True
    unified_analysis_max_tokens: int = 4000
    episode_tracking_enabled: bool = True

    # ── v7.0 模式开关（universal 模式下全部启用） ──
    character_dimension_enabled: bool = True
    rp_consistency_enabled: bool = True
    rp_relation_types: str = ''
    rp_context_types: str = ''

    # ── Reranker ──
    reranker_backend: str = 'builtin'       # builtin / cohere / cross-encoder
    cohere_api_key: str = ''
    reranker_model: str = ''

    # ── MCP ──
    mcp_transport: str = 'stdio'
    mcp_port: int = 8765

    # ── v7.0 Backend Tier ──
    backend_tier: str = ''                  # lite / standard / scale / ultra (空=自动检测)

    # ── v7.0 Security ──
    recall_cors_origins: str = '*'
    recall_cors_methods: str = '*'
    recall_rate_limit_rpm: int = 60

    # ── v7.0 Additional (from engine.py audit) ──
    retrieval_l10_cross_encoder_model: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
    parallel_retriever_workers: int = 4
    parallel_retriever_timeout: float = 5.0
    ivf_auto_switch_enabled: bool = True

    # === Logging ===
    recall_log_level: str = 'INFO'
    recall_log_json: bool = False
    recall_log_file: str = 'auto'  # 'auto' = recall_data/logs/recall.log（按天轮转）

    # === Pipeline ===
    recall_pipeline_max_size: int = 10000
    recall_pipeline_rate_limit: float = 0.0
    recall_pipeline_workers: int = 2

    # === i18n ===
    recall_lang: str = 'auto'

    # === Lifecycle ===
    recall_lifecycle_archive_days: int = 90
    recall_lifecycle_backup_enabled: bool = False
    recall_lifecycle_backup_dir: str = ''
    recall_lifecycle_cleanup_temp: bool = True

    # === LLM Context (v7.0.3: 之前散落在 context_build.py 未集中管理) ===
    llm_context_window: int = 8192
    llm_max_response_tokens: int = 2048
    adaptive_tokens_enabled: bool = True
    system_prompt_tokens: int = 500

    @classmethod
    def from_env(cls) -> 'RecallConfig':
        """从环境变量读取全部配置，缺省时使用此类定义的默认值。"""
        def _bool(val: str, default: bool) -> bool:
            if not val:
                return default
            return val.strip().lower() in ('true', '1', 'yes')

        def _int(val: str, default: int) -> int:
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def _float(val: str, default: float) -> float:
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        d = cls()
        g = os.environ.get

        # ── 数据 & 系统 ──
        d.recall_data_root = g('RECALL_DATA_ROOT', d.recall_data_root)
        d.recall_mode = g('RECALL_MODE', d.recall_mode)
        d.admin_key = g('ADMIN_KEY', d.admin_key)

        # ── Embedding ──
        d.embedding_api_key = g('EMBEDDING_API_KEY', d.embedding_api_key)
        d.embedding_api_base = g('EMBEDDING_API_BASE', d.embedding_api_base)
        d.embedding_model = g('EMBEDDING_MODEL', d.embedding_model)
        d.embedding_dimension = _int(g('EMBEDDING_DIMENSION', ''), d.embedding_dimension)
        d.recall_embedding_mode = g('RECALL_EMBEDDING_MODE', d.recall_embedding_mode)
        d.embedding_rate_limit = _int(g('EMBEDDING_RATE_LIMIT', ''), d.embedding_rate_limit)
        d.embedding_rate_window = _int(g('EMBEDDING_RATE_WINDOW', ''), d.embedding_rate_window)

        # ── LLM ──
        d.llm_api_key = g('LLM_API_KEY', '') or g('OPENAI_API_KEY', d.llm_api_key)
        d.llm_api_base = g('LLM_API_BASE', d.llm_api_base)
        d.llm_model = g('LLM_MODEL', d.llm_model)
        d.llm_timeout = _float(g('LLM_TIMEOUT', ''), d.llm_timeout)
        d.llm_default_max_tokens = _int(g('LLM_DEFAULT_MAX_TOKENS', ''), d.llm_default_max_tokens)
        d.llm_relation_max_tokens = _int(g('LLM_RELATION_MAX_TOKENS', ''), d.llm_relation_max_tokens)
        d.llm_relation_mode = g('LLM_RELATION_MODE', d.llm_relation_mode)

        # ── Smart Extractor ──
        d.smart_extractor_mode = g('SMART_EXTRACTOR_MODE', d.smart_extractor_mode)
        d.smart_extractor_complexity_threshold = _float(g('SMART_EXTRACTOR_COMPLEXITY_THRESHOLD', ''), d.smart_extractor_complexity_threshold)
        d.smart_extractor_enable_temporal = _bool(g('SMART_EXTRACTOR_ENABLE_TEMPORAL', ''), d.smart_extractor_enable_temporal)
        d.smart_extractor_max_tokens = _int(g('SMART_EXTRACTOR_MAX_TOKENS', ''), d.smart_extractor_max_tokens)

        # ── Context ──
        d.context_trigger_interval = _int(g('CONTEXT_TRIGGER_INTERVAL', ''), d.context_trigger_interval)
        d.context_max_context_turns = _int(g('CONTEXT_MAX_CONTEXT_TURNS', ''), d.context_max_context_turns)
        d.context_max_per_type = _int(g('CONTEXT_MAX_PER_TYPE', ''), d.context_max_per_type)
        d.context_max_total = _int(g('CONTEXT_MAX_TOTAL', ''), d.context_max_total)
        d.context_decay_days = _int(g('CONTEXT_DECAY_DAYS', ''), d.context_decay_days)
        d.context_decay_rate = _float(g('CONTEXT_DECAY_RATE', ''), d.context_decay_rate)
        d.context_min_confidence = _float(g('CONTEXT_MIN_CONFIDENCE', ''), d.context_min_confidence)
        d.context_extraction_max_tokens = _int(g('CONTEXT_EXTRACTION_MAX_TOKENS', ''), d.context_extraction_max_tokens)
        d.build_context_include_recent = _int(g('BUILD_CONTEXT_INCLUDE_RECENT', ''), d.build_context_include_recent)
        d.build_context_max_tokens = _int(g('BUILD_CONTEXT_MAX_TOKENS', ''), d.build_context_max_tokens)

        # ── Proactive Reminder ──
        d.proactive_reminder_enabled = _bool(g('PROACTIVE_REMINDER_ENABLED', ''), d.proactive_reminder_enabled)
        d.proactive_reminder_turns = _int(g('PROACTIVE_REMINDER_TURNS', ''), d.proactive_reminder_turns)

        # ── Foreshadowing ──
        d.foreshadowing_llm_enabled = _bool(g('FORESHADOWING_LLM_ENABLED', ''), d.foreshadowing_llm_enabled)
        d.foreshadowing_trigger_interval = _int(g('FORESHADOWING_TRIGGER_INTERVAL', ''), d.foreshadowing_trigger_interval)
        d.foreshadowing_auto_plant = _bool(g('FORESHADOWING_AUTO_PLANT', ''), d.foreshadowing_auto_plant)
        d.foreshadowing_auto_resolve = _bool(g('FORESHADOWING_AUTO_RESOLVE', ''), d.foreshadowing_auto_resolve)
        d.foreshadowing_max_return = _int(g('FORESHADOWING_MAX_RETURN', ''), d.foreshadowing_max_return)
        d.foreshadowing_max_active = _int(g('FORESHADOWING_MAX_ACTIVE', ''), d.foreshadowing_max_active)
        d.foreshadowing_max_tokens = _int(g('FORESHADOWING_MAX_TOKENS', ''), d.foreshadowing_max_tokens)
        d.foreshadowing_enabled = _bool(g('FORESHADOWING_ENABLED', ''), d.foreshadowing_enabled)

        # ── Dedup ──
        d.dedup_embedding_enabled = _bool(g('DEDUP_EMBEDDING_ENABLED', ''), d.dedup_embedding_enabled)
        d.dedup_high_threshold = _float(g('DEDUP_HIGH_THRESHOLD', ''), d.dedup_high_threshold)
        d.dedup_low_threshold = _float(g('DEDUP_LOW_THRESHOLD', ''), d.dedup_low_threshold)
        d.dedup_llm_max_tokens = _int(g('DEDUP_LLM_MAX_TOKENS', ''), d.dedup_llm_max_tokens)
        d.embedding_reuse_enabled = _bool(g('EMBEDDING_REUSE_ENABLED', ''), d.embedding_reuse_enabled)
        d.dedup_jaccard_threshold = _float(g('DEDUP_JACCARD_THRESHOLD', ''), d.dedup_jaccard_threshold)
        d.dedup_semantic_threshold = _float(g('DEDUP_SEMANTIC_THRESHOLD', ''), d.dedup_semantic_threshold)
        d.dedup_semantic_low_threshold = _float(g('DEDUP_SEMANTIC_LOW_THRESHOLD', ''), d.dedup_semantic_low_threshold)
        d.dedup_llm_enabled = _bool(g('DEDUP_LLM_ENABLED', ''), d.dedup_llm_enabled)

        # ── Graph ──
        d.temporal_graph_enabled = _bool(g('TEMPORAL_GRAPH_ENABLED', ''), d.temporal_graph_enabled)
        d.temporal_graph_backend = g('TEMPORAL_GRAPH_BACKEND', d.temporal_graph_backend)
        d.kuzu_buffer_pool_size = _int(g('KUZU_BUFFER_POOL_SIZE', ''), d.kuzu_buffer_pool_size)
        d.temporal_decay_rate = _float(g('TEMPORAL_DECAY_RATE', ''), d.temporal_decay_rate)
        d.temporal_max_history = _int(g('TEMPORAL_MAX_HISTORY', ''), d.temporal_max_history)
        d.community_detection_enabled = _bool(g('COMMUNITY_DETECTION_ENABLED', ''), d.community_detection_enabled)
        d.community_detection_algorithm = g('COMMUNITY_DETECTION_ALGORITHM', d.community_detection_algorithm)
        d.community_min_size = _int(g('COMMUNITY_MIN_SIZE', ''), d.community_min_size)
        d.llm_relation_complexity_threshold = _float(g('LLM_RELATION_COMPLEXITY_THRESHOLD', ''), d.llm_relation_complexity_threshold)
        d.llm_relation_enable_temporal = _bool(g('LLM_RELATION_ENABLE_TEMPORAL', ''), d.llm_relation_enable_temporal)
        d.llm_relation_enable_fact_description = _bool(g('LLM_RELATION_ENABLE_FACT_DESCRIPTION', ''), d.llm_relation_enable_fact_description)

        # ── Contradiction ──
        d.contradiction_detection_enabled = _bool(g('CONTRADICTION_DETECTION_ENABLED', ''), d.contradiction_detection_enabled)
        d.contradiction_auto_resolve = _bool(g('CONTRADICTION_AUTO_RESOLVE', ''), d.contradiction_auto_resolve)
        d.contradiction_detection_strategy = g('CONTRADICTION_DETECTION_STRATEGY', d.contradiction_detection_strategy)
        d.contradiction_similarity_threshold = _float(g('CONTRADICTION_SIMILARITY_THRESHOLD', ''), d.contradiction_similarity_threshold)
        d.contradiction_max_tokens = _int(g('CONTRADICTION_MAX_TOKENS', ''), d.contradiction_max_tokens)

        # ── Full-text Search ──
        d.fulltext_enabled = _bool(g('FULLTEXT_ENABLED', ''), d.fulltext_enabled)
        d.fulltext_k1 = _float(g('FULLTEXT_K1', ''), d.fulltext_k1)
        d.fulltext_b = _float(g('FULLTEXT_B', ''), d.fulltext_b)
        d.fulltext_weight = _float(g('FULLTEXT_WEIGHT', ''), d.fulltext_weight)

        # ── Budget ──
        d.budget_daily_limit = _float(g('BUDGET_DAILY_LIMIT', ''), d.budget_daily_limit)
        d.budget_hourly_limit = _float(g('BUDGET_HOURLY_LIMIT', ''), d.budget_hourly_limit)
        d.budget_reserve = _float(g('BUDGET_RESERVE', ''), d.budget_reserve)
        d.budget_alert_threshold = _float(g('BUDGET_ALERT_THRESHOLD', ''), d.budget_alert_threshold)

        # ── Index / IVF ──
        d.ivf_auto_switch_threshold = _int(g('IVF_AUTO_SWITCH_THRESHOLD', ''), d.ivf_auto_switch_threshold)

        # ── Eleven Layer Retriever ──
        d.eleven_layer_retriever_enabled = _bool(g('ELEVEN_LAYER_RETRIEVER_ENABLED', ''), d.eleven_layer_retriever_enabled)
        d.retrieval_l1_bloom_enabled = _bool(g('RETRIEVAL_L1_BLOOM_ENABLED', ''), d.retrieval_l1_bloom_enabled)
        d.retrieval_l2_temporal_enabled = _bool(g('RETRIEVAL_L2_TEMPORAL_ENABLED', ''), d.retrieval_l2_temporal_enabled)
        d.retrieval_l3_inverted_enabled = _bool(g('RETRIEVAL_L3_INVERTED_ENABLED', ''), d.retrieval_l3_inverted_enabled)
        d.retrieval_l4_entity_enabled = _bool(g('RETRIEVAL_L4_ENTITY_ENABLED', ''), d.retrieval_l4_entity_enabled)
        d.retrieval_l5_graph_enabled = _bool(g('RETRIEVAL_L5_GRAPH_ENABLED', ''), d.retrieval_l5_graph_enabled)
        d.retrieval_l6_ngram_enabled = _bool(g('RETRIEVAL_L6_NGRAM_ENABLED', ''), d.retrieval_l6_ngram_enabled)
        d.retrieval_l7_vector_coarse_enabled = _bool(g('RETRIEVAL_L7_VECTOR_COARSE_ENABLED', ''), d.retrieval_l7_vector_coarse_enabled)
        d.retrieval_l8_vector_fine_enabled = _bool(g('RETRIEVAL_L8_VECTOR_FINE_ENABLED', ''), d.retrieval_l8_vector_fine_enabled)
        d.retrieval_l9_rerank_enabled = _bool(g('RETRIEVAL_L9_RERANK_ENABLED', ''), d.retrieval_l9_rerank_enabled)
        d.retrieval_l10_cross_encoder_enabled = _bool(g('RETRIEVAL_L10_CROSS_ENCODER_ENABLED', ''), d.retrieval_l10_cross_encoder_enabled)
        d.retrieval_l11_llm_enabled = _bool(g('RETRIEVAL_L11_LLM_ENABLED', ''), d.retrieval_l11_llm_enabled)
        d.retrieval_final_top_k = _int(g('RETRIEVAL_FINAL_TOP_K', ''), d.retrieval_final_top_k)
        d.retrieval_fine_rank_threshold = _int(g('RETRIEVAL_FINE_RANK_THRESHOLD', ''), d.retrieval_fine_rank_threshold)
        d.retrieval_llm_max_tokens = _int(g('RETRIEVAL_LLM_MAX_TOKENS', ''), d.retrieval_llm_max_tokens)

        # ── Query Planner / Community ──
        d.query_planner_enabled = _bool(g('QUERY_PLANNER_ENABLED', ''), d.query_planner_enabled)
        d.query_planner_cache_size = _int(g('QUERY_PLANNER_CACHE_SIZE', ''), d.query_planner_cache_size)
        d.query_planner_cache_ttl = _int(g('QUERY_PLANNER_CACHE_TTL', ''), d.query_planner_cache_ttl)

        # ── Triple Recall ──
        d.triple_recall_enabled = _bool(g('TRIPLE_RECALL_ENABLED', ''), d.triple_recall_enabled)
        d.triple_recall_rrf_k = _int(g('TRIPLE_RECALL_RRF_K', ''), d.triple_recall_rrf_k)
        d.triple_recall_vector_weight = _float(g('TRIPLE_RECALL_VECTOR_WEIGHT', ''), d.triple_recall_vector_weight)
        d.triple_recall_keyword_weight = _float(g('TRIPLE_RECALL_KEYWORD_WEIGHT', ''), d.triple_recall_keyword_weight)
        d.triple_recall_entity_weight = _float(g('TRIPLE_RECALL_ENTITY_WEIGHT', ''), d.triple_recall_entity_weight)

        # ── Entity Summary ──
        d.entity_summary_enabled = _bool(g('ENTITY_SUMMARY_ENABLED', ''), d.entity_summary_enabled)
        d.entity_summary_min_facts = _int(g('ENTITY_SUMMARY_MIN_FACTS', ''), d.entity_summary_min_facts)
        d.entity_summary_max_tokens = _int(g('ENTITY_SUMMARY_MAX_TOKENS', ''), d.entity_summary_max_tokens)

        # ── Turn API / Unified Analyzer ──
        d.turn_api_enabled = _bool(g('TURN_API_ENABLED', ''), d.turn_api_enabled)
        d.unified_analyzer_enabled = _bool(g('UNIFIED_ANALYZER_ENABLED', ''), d.unified_analyzer_enabled)
        d.unified_analysis_max_tokens = _int(g('UNIFIED_ANALYSIS_MAX_TOKENS', ''), d.unified_analysis_max_tokens)
        d.episode_tracking_enabled = _bool(g('EPISODE_TRACKING_ENABLED', ''), d.episode_tracking_enabled)

        # ── v7.0 模式开关 ──
        d.character_dimension_enabled = _bool(g('CHARACTER_DIMENSION_ENABLED', ''), d.character_dimension_enabled)
        d.rp_consistency_enabled = _bool(g('RP_CONSISTENCY_ENABLED', ''), d.rp_consistency_enabled)
        d.rp_relation_types = g('RP_RELATION_TYPES', d.rp_relation_types)
        d.rp_context_types = g('RP_CONTEXT_TYPES', d.rp_context_types)

        # ── Reranker ──
        d.reranker_backend = g('RERANKER_BACKEND', d.reranker_backend)
        d.cohere_api_key = g('COHERE_API_KEY', d.cohere_api_key)
        d.reranker_model = g('RERANKER_MODEL', d.reranker_model)

        # ── MCP ──
        d.mcp_transport = g('MCP_TRANSPORT', d.mcp_transport)
        d.mcp_port = _int(g('MCP_PORT', ''), d.mcp_port)

        # ── v7.0 Backend Tier ──
        d.backend_tier = g('RECALL_BACKEND_TIER', d.backend_tier)

        # ── v7.0 Security ──
        d.recall_cors_origins = g('RECALL_CORS_ORIGINS', d.recall_cors_origins)
        d.recall_cors_methods = g('RECALL_CORS_METHODS', d.recall_cors_methods)
        d.recall_rate_limit_rpm = _int(g('RECALL_RATE_LIMIT_RPM', ''), d.recall_rate_limit_rpm)

        # ── v7.0 Additional ──
        d.retrieval_l10_cross_encoder_model = g('RETRIEVAL_L10_CROSS_ENCODER_MODEL', d.retrieval_l10_cross_encoder_model)
        d.parallel_retriever_workers = _int(g('PARALLEL_RETRIEVER_WORKERS', ''), d.parallel_retriever_workers)
        d.parallel_retriever_timeout = _float(g('PARALLEL_RETRIEVER_TIMEOUT', ''), d.parallel_retriever_timeout)
        d.ivf_auto_switch_enabled = _bool(g('IVF_AUTO_SWITCH_ENABLED', ''), d.ivf_auto_switch_enabled)

        # === Logging ===
        d.recall_log_level = g('RECALL_LOG_LEVEL', d.recall_log_level)
        d.recall_log_json = _bool(g('RECALL_LOG_JSON', ''), d.recall_log_json)
        d.recall_log_file = g('RECALL_LOG_FILE', d.recall_log_file)

        # === Pipeline ===
        d.recall_pipeline_max_size = _int(g('RECALL_PIPELINE_MAX_SIZE', ''), d.recall_pipeline_max_size)
        d.recall_pipeline_rate_limit = _float(g('RECALL_PIPELINE_RATE_LIMIT', ''), d.recall_pipeline_rate_limit)
        d.recall_pipeline_workers = _int(g('RECALL_PIPELINE_WORKERS', ''), d.recall_pipeline_workers)

        # === i18n ===
        d.recall_lang = g('RECALL_LANG', d.recall_lang)

        # === Lifecycle ===
        d.recall_lifecycle_archive_days = _int(g('RECALL_LIFECYCLE_ARCHIVE_DAYS', ''), d.recall_lifecycle_archive_days)
        d.recall_lifecycle_backup_enabled = _bool(g('RECALL_LIFECYCLE_BACKUP_ENABLED', ''), d.recall_lifecycle_backup_enabled)
        d.recall_lifecycle_backup_dir = g('RECALL_LIFECYCLE_BACKUP_DIR', d.recall_lifecycle_backup_dir)
        d.recall_lifecycle_cleanup_temp = _bool(g('RECALL_LIFECYCLE_CLEANUP_TEMP', ''), d.recall_lifecycle_cleanup_temp)

        # === LLM Context (v7.0.3) ===
        d.llm_context_window = _int(g('LLM_CONTEXT_WINDOW', ''), d.llm_context_window)
        d.llm_max_response_tokens = _int(g('LLM_MAX_RESPONSE_TOKENS', ''), d.llm_max_response_tokens)
        d.adaptive_tokens_enabled = _bool(g('ADAPTIVE_TOKENS_ENABLED', ''), d.adaptive_tokens_enabled)
        d.system_prompt_tokens = _int(g('SYSTEM_PROMPT_TOKENS', ''), d.system_prompt_tokens)

        return d


# ============================================================================
# Phase 3.6: 三路召回配置
# ============================================================================
@dataclass
class TripleRecallConfig:
    """Phase 3.6: 三路召回配置
    
    支持三种预设模式:
    - default(): 平衡模式
    - max_recall(): 最大召回模式（100% 不遗忘优先）
    - fast(): 快速模式（速度优先）
    """
    
    # 并行召回开关
    enabled: bool = True
    
    # 路径权重（用于 RRF 融合）
    vector_weight: float = 1.0       # 语义召回权重
    keyword_weight: float = 1.2      # 关键词召回权重（100%召回，权重更高）
    entity_weight: float = 1.0       # 实体召回权重
    
    # RRF 参数
    rrf_k: int = 60                  # RRF 常数
    
    # 原文兜底配置
    fallback_enabled: bool = True    # 启用原文兜底
    fallback_parallel: bool = True   # 并行扫描
    fallback_workers: int = 4        # 并行线程数
    fallback_max_results: int = 50   # 兜底最大结果数
    
    # IVF-HNSW 参数
    hnsw_m: int = 32                 # HNSW 图连接数
    hnsw_ef_construction: int = 200  # 构建精度
    hnsw_ef_search: int = 64         # 搜索精度
    
    @classmethod
    def default(cls) -> 'TripleRecallConfig':
        """默认配置（平衡模式）"""
        return cls()
    
    @classmethod
    def max_recall(cls) -> 'TripleRecallConfig':
        """最大召回模式（100% 不遗忘优先）"""
        return cls(
            hnsw_m=48,
            hnsw_ef_construction=300,
            hnsw_ef_search=128,
            keyword_weight=1.5,
        )
    
    @classmethod
    def fast(cls) -> 'TripleRecallConfig':
        """快速模式（速度优先）"""
        return cls(
            hnsw_m=16,
            hnsw_ef_construction=100,
            hnsw_ef_search=32,
            fallback_workers=2,
        )
    
    @classmethod
    def from_env(cls) -> 'TripleRecallConfig':
        """从环境变量加载配置"""
        return cls(
            enabled=os.getenv('TRIPLE_RECALL_ENABLED', 'true').lower() == 'true',
            vector_weight=float(os.getenv('TRIPLE_RECALL_VECTOR_WEIGHT', '1.0')),
            keyword_weight=float(os.getenv('TRIPLE_RECALL_KEYWORD_WEIGHT', '1.2')),
            entity_weight=float(os.getenv('TRIPLE_RECALL_ENTITY_WEIGHT', '1.0')),
            rrf_k=int(os.getenv('TRIPLE_RECALL_RRF_K', '60')),
            hnsw_m=int(os.getenv('VECTOR_IVF_HNSW_M', '32')),
            hnsw_ef_construction=int(os.getenv('VECTOR_IVF_HNSW_EF_CONSTRUCTION', '200')),
            hnsw_ef_search=int(os.getenv('VECTOR_IVF_HNSW_EF_SEARCH', '64')),
            fallback_enabled=os.getenv('FALLBACK_ENABLED', 'true').lower() == 'true',
            fallback_parallel=os.getenv('FALLBACK_PARALLEL', 'true').lower() == 'true',
            fallback_workers=int(os.getenv('FALLBACK_WORKERS', '4')),
            fallback_max_results=int(os.getenv('FALLBACK_MAX_RESULTS', '50')),
        )
