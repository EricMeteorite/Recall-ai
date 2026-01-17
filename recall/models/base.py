"""基础数据模型定义"""

from enum import Enum


class EntityType(str, Enum):
    """实体类型"""
    CHARACTER = "CHARACTER"
    ITEM = "ITEM"
    LOCATION = "LOCATION"
    CONCEPT = "CONCEPT"
    CODE_SYMBOL = "CODE_SYMBOL"


class EventType(str, Enum):
    """事件类型"""
    STATE_CHANGE = "STATE_CHANGE"
    RELATIONSHIP = "RELATIONSHIP"
    ITEM_TRANSFER = "ITEM_TRANSFER"
    FORESHADOWING = "FORESHADOWING"
    PLOT_POINT = "PLOT_POINT"
    CODE_CHANGE = "CODE_CHANGE"


class ForeshadowingStatus(str, Enum):
    """伏笔状态"""
    UNRESOLVED = "UNRESOLVED"
    POSSIBLY_TRIGGERED = "POSSIBLY_TRIGGERED"
    RESOLVED = "RESOLVED"
