"""配置验证器 — 启动时校验配置完整性

功能:
- 检查 API 密钥是否设置（当 LLM 功能启用时）
- 检查 Embedding 模型可用性
- 数值范围校验
- 输出 WARNING（不 crash）
"""

from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigValidationResult:
    """校验结果"""

    def __init__(self):
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.info: List[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.is_valid,
            "warnings": self.warnings,
            "errors": self.errors,
            "info": self.info,
        }


def validate_config() -> ConfigValidationResult:
    """验证所有配置项

    检查:
    1. Embedding API 配置
    2. LLM API 配置（当高级功能启用时）
    3. 数值范围
    4. 路径存在性

    Returns:
        ConfigValidationResult
    """
    result = ConfigValidationResult()

    # ---- Embedding 配置 ----
    embedding_mode = os.environ.get('RECALL_EMBEDDING_MODE', 'auto').lower()

    if embedding_mode in ('api', 'auto', ''):
        api_key = os.environ.get('EMBEDDING_API_KEY', '')
        api_base = os.environ.get('EMBEDDING_API_BASE', '')

        if not api_key:
            result.warnings.append(
                "EMBEDDING_API_KEY 未设置 — 如果使用远程 Embedding API，请设置此项"
            )
        if not api_base:
            result.warnings.append(
                "EMBEDDING_API_BASE 未设置 — 如果使用远程 Embedding API，请设置此项"
            )
        if api_key and api_base:
            result.info.append("Embedding API 配置完整")

    if embedding_mode == 'local':
        result.info.append("Embedding 模式: local（本地模型）")

    if embedding_mode == 'none':
        result.info.append("Embedding 模式: none（禁用，使用 Lite 模式）")

    # Embedding 维度
    dim_str = os.environ.get('EMBEDDING_DIMENSION', '1024')
    try:
        dim = int(dim_str)
        if dim <= 0 or dim > 8192:
            result.warnings.append(
                f"EMBEDDING_DIMENSION={dim} 超出常见范围 (1-8192)"
            )
    except ValueError:
        result.warnings.append(
            f"EMBEDDING_DIMENSION='{dim_str}' 不是有效数字"
        )

    # ---- LLM 配置 ----
    llm_features = {
        'FORESHADOWING_LLM_ENABLED': '伏笔分析 (Foreshadowing)',
        'SMART_EXTRACTOR_MODE': '智能抽取 (Smart Extractor) — LLM 模式',
        'DEDUP_LLM_ENABLED': '去重 LLM 确认',
        'CONTRADICTION_DETECTION_ENABLED': '矛盾检测',
    }

    llm_needed = False
    for env_key, feature_name in llm_features.items():
        val = os.environ.get(env_key, '').lower()
        if val in ('true', '1', 'llm', 'adaptive', 'mixed', 'auto'):
            llm_needed = True
            break

    if llm_needed:
        llm_key = os.environ.get('LLM_API_KEY', '')
        llm_base = os.environ.get('LLM_API_BASE', '')

        if not llm_key:
            result.warnings.append(
                "LLM_API_KEY 未设置 — 伏笔分析/矛盾检测/智能抽取等功能将不可用"
            )
        if not llm_base:
            result.warnings.append(
                "LLM_API_BASE 未设置 — LLM 功能将不可用"
            )
        if llm_key and llm_base:
            result.info.append("LLM API 配置完整")

    # ---- 数值范围检查 ----
    _check_range(result, 'FULLTEXT_K1', 0.0, 10.0)
    _check_range(result, 'FULLTEXT_B', 0.0, 1.0)
    _check_range(result, 'FULLTEXT_WEIGHT', 0.0, 1.0)
    _check_range(result, 'TEMPORAL_DECAY_RATE', 0.0, 1.0)
    _check_range(result, 'CONTEXT_DECAY_RATE', 0.0, 1.0)
    _check_range(result, 'BUDGET_RESERVE', 0.0, 1.0)
    _check_range(result, 'BUDGET_ALERT_THRESHOLD', 0.0, 1.0)
    _check_range(result, 'DEDUP_HIGH_THRESHOLD', 0.0, 1.0)
    _check_range(result, 'DEDUP_LOW_THRESHOLD', 0.0, 1.0)
    _check_range(result, 'DEDUP_SEMANTIC_THRESHOLD', 0.0, 1.0)
    _check_range(result, 'DEDUP_JACCARD_THRESHOLD', 0.0, 1.0)
    _check_range(result, 'CONTRADICTION_SIMILARITY_THRESHOLD', 0.0, 1.0)
    _check_range(result, 'SMART_EXTRACTOR_COMPLEXITY_THRESHOLD', 0.0, 1.0)

    # ---- 数据目录 ----
    data_root = os.environ.get('RECALL_DATA_ROOT', './recall_data')
    if os.path.exists(data_root):
        result.info.append(f"数据目录: {os.path.abspath(data_root)}")
    else:
        result.info.append(f"数据目录 {data_root} 不存在，将自动创建")

    # ---- 阈值逻辑检查 ----
    high = _get_float('DEDUP_HIGH_THRESHOLD', 0.85)
    low = _get_float('DEDUP_LOW_THRESHOLD', 0.70)
    if high <= low:
        result.warnings.append(
            f"DEDUP_HIGH_THRESHOLD ({high}) 应大于 DEDUP_LOW_THRESHOLD ({low})"
        )

    # ---- Embedding 速率限制 ----
    rate_limit = _get_int('EMBEDDING_RATE_LIMIT', 10)
    if rate_limit < 0:
        result.warnings.append("EMBEDDING_RATE_LIMIT 不应为负数")

    # ---- LLM 超时 ----
    llm_timeout = _get_int('LLM_TIMEOUT', 60)
    if llm_timeout < 5:
        result.warnings.append(
            f"LLM_TIMEOUT={llm_timeout} 过短，复杂请求可能超时（建议 >= 30）"
        )

    # ---- 总结 ----
    if result.is_valid and not result.warnings:
        result.info.append("所有配置项验证通过")

    return result


def validate_and_log() -> ConfigValidationResult:
    """验证配置并输出日志"""
    result = validate_config()

    for msg in result.info:
        logger.info("[ConfigValidator] %s", msg)
    for msg in result.warnings:
        logger.warning("[ConfigValidator] %s", msg)
    for msg in result.errors:
        logger.error("[ConfigValidator] %s", msg)

    return result


# ==================== 辅助函数 ====================

def _get_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _check_range(
    result: ConfigValidationResult,
    key: str,
    min_val: float,
    max_val: float,
) -> None:
    """检查环境变量数值范围"""
    val_str = os.environ.get(key, '')
    if not val_str:
        return
    try:
        val = float(val_str)
        if val < min_val or val > max_val:
            result.warnings.append(
                f"{key}={val} 超出建议范围 [{min_val}, {max_val}]"
            )
    except ValueError:
        result.warnings.append(f"{key}='{val_str}' 不是有效数字")
