"""事件数据模型"""

from pydantic import BaseModel
from typing import List, Optional

from .base import EventType


class Event(BaseModel):
    """事件模型"""
    id: str
    turn: int
    event_type: EventType
    summary: str
    detail: str
    entities_involved: List[str]
    keywords: List[str]
    priority: str = "P2"  # P0, P1, P2, P3
    embedding: Optional[List[float]] = None
