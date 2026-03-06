"""Recall 7.0 — 统一模式配置（无模式切换，全部功能始终可用）

v7.0 变更：移除 RP/通用/知识库 三模式切换。
所有功能（伏笔、关系类型、上下文类型等）在任何场景下默认启用。
环境变量仍可单独关闭某项功能（向后兼容）。
RecallMode 枚举保留 UNIVERSAL 一个值，兼容已有 .mode.value 引用。
"""

import os
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class RecallMode(Enum):
    """v7.0: 仅保留一个通用模式，旧值映射到 UNIVERSAL"""
    UNIVERSAL = "universal"
    # 向后兼容别名（均解析为 UNIVERSAL）
    ROLEPLAY = "universal"
    GENERAL = "universal"
    KNOWLEDGE_BASE = "universal"


@dataclass
class ModeConfig:
    """模式配置 — v7.0: 所有功能默认启用，可通过环境变量单独禁用"""
    mode: RecallMode

    # 功能开关（全部默认 True，任何场景即插即用）
    foreshadowing_enabled: bool
    character_dimension_enabled: bool
    rp_consistency_enabled: bool
    rp_relation_types: bool
    rp_context_types: bool

    @classmethod
    def from_env(cls) -> 'ModeConfig':
        # v7.0: 忽略 RECALL_MODE 环境变量，始终使用 UNIVERSAL
        def env_bool(key: str, default: bool = True) -> bool:
            val = os.getenv(key)
            if val is not None:
                return val.lower() in ('true', '1', 'yes')
            return default

        return cls(
            mode=RecallMode.UNIVERSAL,
            foreshadowing_enabled=env_bool('FORESHADOWING_ENABLED', True),
            character_dimension_enabled=env_bool('CHARACTER_DIMENSION_ENABLED', True),
            rp_consistency_enabled=env_bool('RP_CONSISTENCY_ENABLED', True),
            rp_relation_types=env_bool('RP_RELATION_TYPES', True),
            rp_context_types=env_bool('RP_CONTEXT_TYPES', True),
        )


# 全局单例
_mode_config: Optional[ModeConfig] = None


def get_mode_config() -> ModeConfig:
    global _mode_config
    if _mode_config is None:
        _mode_config = ModeConfig.from_env()
    return _mode_config
