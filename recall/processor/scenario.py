"""场景检测器 — v7.0 兼容性存根

原始实现已在 v7.0 中移除（通用记忆系统不区分场景模式）。
此存根保持向后兼容，ScenarioDetector.detect() 总是返回 GENERAL。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any


class ScenarioType(str, Enum):
    """场景类型"""
    GENERAL = "general"
    CONVERSATION = "conversation"
    QUESTION = "question"
    STORY = "story"
    ANALYSIS = "analysis"
    RECALL = "recall"
    SEARCH = "search"


@dataclass
class ScenarioInfo:
    """场景信息"""
    scenario_type: ScenarioType = ScenarioType.GENERAL
    confidence: float = 1.0
    metadata: Dict[str, Any] = None
    suggested_retrieval_strategy: str = "balanced"
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ScenarioDetector:
    """场景检测器（v7.0 兼容性存根 — 永远返回 GENERAL）"""
    
    def __init__(self, **kwargs):
        pass
    
    def detect(self, query: str, context: str = "", **kwargs) -> ScenarioInfo:
        """检测场景类型
        
        v7.0 通用记忆系统不区分场景，始终返回 GENERAL 类型。
        """
        return ScenarioInfo(
            scenario_type=ScenarioType.GENERAL,
            confidence=1.0,
            metadata={'note': 'v7.0 universal memory - scenario detection disabled'}
        )
