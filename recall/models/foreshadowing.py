"""伏笔数据模型"""

from pydantic import BaseModel
from typing import List, Optional

from .base import ForeshadowingStatus


class Foreshadowing(BaseModel):
    """伏笔模型"""
    id: str
    created_turn: int
    content: str
    summary: str
    trigger_keywords: List[str]
    trigger_combinations: List[List[str]] = []
    trigger_entities: List[str] = []
    content_embedding: Optional[List[float]] = None
    status: ForeshadowingStatus = ForeshadowingStatus.UNRESOLVED
    resolution_turn: Optional[int] = None
    resolution_content: Optional[str] = None
    remind_after_turns: int = 100
    last_reminded: Optional[int] = None
    importance: str = "MEDIUM"  # HIGH, MEDIUM, LOW
