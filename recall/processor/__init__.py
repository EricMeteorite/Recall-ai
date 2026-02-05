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
]
