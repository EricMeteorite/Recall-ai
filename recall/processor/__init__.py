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
from .scenario import ScenarioDetector

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
]
