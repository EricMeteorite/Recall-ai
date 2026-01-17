"""对话轮次数据模型"""

from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime


class Turn(BaseModel):
    """对话轮次"""
    turn: int
    timestamp: datetime
    user: str
    assistant: str
    metadata: Dict[str, Any] = {}
    entities_mentioned: List[str] = []
    events_detected: List[str] = []
    ngrams_3: List[str] = []
    keywords: List[str] = []
