"""实体数据模型"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base import EntityType


class Relation(BaseModel):
    """实体关系"""
    target_id: str
    relation_type: str  # e.g., "恋人", "敌人", "拥有", "位于"
    established_turn: int
    is_current: bool = True


class Entity(BaseModel):
    """实体模型"""
    id: str
    name: str
    aliases: List[str] = []
    entity_type: EntityType
    current_state: Dict[str, Any] = {}
    confidence: float = 1.0
    verification_count: int = 1
    source_turns: List[int] = []
    last_verified: datetime = Field(default_factory=datetime.now)
    relations: List[Relation] = []
    embedding: Optional[List[float]] = None  # 语义向量
