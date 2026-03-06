"""处理器层模块"""

from .entity_extractor import EntityExtractor, ExtractedEntity
from .foreshadowing import ForeshadowingTracker, ForeshadowingTrackerLite, Foreshadowing
from .foreshadowing_analyzer import (
    ForeshadowingAnalyzer, 
    ForeshadowingAnalyzerConfig,
    AnalyzerBackend,
    AnalysisResult
)
from .consistency import ConsistencyChecker, ConsistencyResult, Violation
from .memory_summarizer import MemorySummarizer, MemoryItem
from .scenario import ScenarioDetector, ScenarioType, ScenarioInfo
from .context_tracker import ContextTracker, PersistentContext, ContextType

# v4.0 Phase 2 新增: 智能抽取器与三阶段去重
from .smart_extractor import (
    SmartExtractor,
    SmartExtractorConfig,
    ExtractionMode,
    ExtractionResult,
    ExtractedRelation
)
from .three_stage_deduplicator import (
    ThreeStageDeduplicator,
    DedupConfig,
    DedupItem,
    DedupMatch,
    DedupResult,
    MatchType
)

# === Recall 4.1 新增: 实体摘要生成器 ===
from .entity_summarizer import EntitySummarizer, EntitySummary

# === Recall 4.2 性能优化: 统一 LLM 分析器 ===
from .unified_analyzer import (
    UnifiedAnalyzer,
    UnifiedAnalysisInput,
    UnifiedAnalysisResult,
    AnalysisTask
)

# === Recall 7.0 新增: 文档分块器 ===
from .document_chunker import (
    chunk as document_chunk,
    needs_chunking,
    detect_source_type,
    ChunkResult,
    SourceType,
)

# === Recall 7.3 新增: 时间意图解析 / 事件关联 / 主题聚类 ===
from .time_intent_parser import TimeIntentParser, TimeRange
from .event_linker import EventLinker, EventLink, ChainNode
from .topic_cluster import TopicCluster, TopicInfo, TopicStore

# === Recall 7.0.1 新增: 实体消歧 ===
from .entity_resolver import EntityResolver

__all__ = [
    'EntityExtractor',
    'ExtractedEntity',
    'ForeshadowingTracker',
    'ForeshadowingTrackerLite',
    'Foreshadowing',
    'ForeshadowingAnalyzer',
    'ForeshadowingAnalyzerConfig',
    'AnalyzerBackend',
    'AnalysisResult',
    'ConsistencyChecker',
    'ConsistencyResult',
    'Violation',
    'MemorySummarizer',
    'MemoryItem',
    'ScenarioDetector',
    'ScenarioType',
    'ScenarioInfo',
    'ContextTracker',
    'PersistentContext',
    'ContextType',
    
    # v4.0 Phase 2 新增导出
    'SmartExtractor',
    'SmartExtractorConfig',
    'ExtractionMode',
    'ExtractionResult',
    'ExtractedRelation',
    'ThreeStageDeduplicator',
    'DedupConfig',
    'DedupItem',
    'DedupMatch',
    'DedupResult',
    'MatchType',
    
    # === Recall 4.1 新增导出 ===
    'EntitySummarizer',
    'EntitySummary',
    
    # === Recall 4.2 性能优化导出 ===
    'UnifiedAnalyzer',
    'UnifiedAnalysisInput',
    'UnifiedAnalysisResult',
    'AnalysisTask',
    
    # === Recall 7.0 文档分块器导出 ===
    'document_chunk',
    'needs_chunking',
    'detect_source_type',
    'ChunkResult',
    'SourceType',

    # === Recall 7.3 新增导出 ===
    'TimeIntentParser',
    'TimeRange',
    'EventLinker',
    'EventLink',
    'ChainNode',
    'TopicCluster',
    'TopicInfo',
    'TopicStore',

    # === Recall 7.0.1 新增导出 ===
    'EntityResolver',
]
