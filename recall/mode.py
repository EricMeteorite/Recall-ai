"""全局模式管理器 — 控制 RP/通用/知识库 模式切换"""

import os
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class RecallMode(Enum):
    ROLEPLAY = "roleplay"          # RP 模式（默认，向后兼容）
    GENERAL = "general"            # 通用模式（爬虫、知识库、Agent）
    KNOWLEDGE_BASE = "knowledge_base"  # 知识库模式（纯知识管理）


@dataclass
class ModeConfig:
    """模式配置 — 根据模式自动推导子开关"""
    mode: RecallMode

    # RP 特性开关
    foreshadowing_enabled: bool
    character_dimension_enabled: bool
    rp_consistency_enabled: bool
    rp_relation_types: bool
    rp_context_types: bool

    @classmethod
    def from_env(cls) -> 'ModeConfig':
        mode_str = os.getenv('RECALL_MODE', 'roleplay').lower()
        if mode_str not in [m.value for m in RecallMode]:
            logging.getLogger('recall.mode').warning(
                f"未知的 RECALL_MODE 值 '{mode_str}'，已回退到 'roleplay'。"
                f"有效值: {[m.value for m in RecallMode]}")
        mode = RecallMode(mode_str) if mode_str in [m.value for m in RecallMode] else RecallMode.ROLEPLAY

        # 模式默认值
        defaults = {
            RecallMode.ROLEPLAY: dict(foreshadowing=True, character=True, rp_consistency=True, rp_relations=True, rp_context=True),
            RecallMode.GENERAL: dict(foreshadowing=False, character=False, rp_consistency=False, rp_relations=False, rp_context=False),
            RecallMode.KNOWLEDGE_BASE: dict(foreshadowing=False, character=False, rp_consistency=False, rp_relations=False, rp_context=False),
        }
        d = defaults[mode]

        # 允许环境变量手动覆盖任意子开关
        def env_bool(key, default):
            val = os.getenv(key)
            return val.lower() in ('true', '1', 'yes') if val else default

        return cls(
            mode=mode,
            foreshadowing_enabled=env_bool('FORESHADOWING_ENABLED', d['foreshadowing']),
            character_dimension_enabled=env_bool('CHARACTER_DIMENSION_ENABLED', d['character']),
            rp_consistency_enabled=env_bool('RP_CONSISTENCY_ENABLED', d['rp_consistency']),
            rp_relation_types=env_bool('RP_RELATION_TYPES', d['rp_relations']),
            rp_context_types=env_bool('RP_CONTEXT_TYPES', d['rp_context']),
        )


# 全局单例
_mode_config: Optional[ModeConfig] = None


def get_mode_config() -> ModeConfig:
    global _mode_config
    if _mode_config is None:
        _mode_config = ModeConfig.from_env()
    return _mode_config
