"""国际化模块 — i18n

简单的 dict-based 多语言翻译:
- t('error.not_found', lang='en') → "Memory not found"
- t('error.not_found', lang='zh') → "记忆未找到"

支持语言: zh (中文, 默认), en (英文)
通过环境变量 RECALL_LANG 设置默认语言。
"""

from __future__ import annotations

import os
from typing import Optional, Dict

# 默认语言
# v7.0.3: 优先从 RecallConfig 读取，保证默认值一致性
def _get_default_lang() -> str:
    """Get default language, prioritizing RecallConfig."""
    try:
        from .config import RecallConfig
        cfg = RecallConfig.from_env()
        lang = cfg.recall_lang
        if lang and lang != 'auto':
            return lang
    except Exception:
        pass
    # fallback: 从环境变量读取，默认 zh
    return os.environ.get('RECALL_LANG', 'zh')

DEFAULT_LANG = _get_default_lang()

# 翻译字典: key → { lang → text }
_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ---- 通用错误 ----
    'error.not_found': {
        'zh': '记忆未找到',
        'en': 'Memory not found',
    },
    'error.user_not_found': {
        'zh': '用户未找到',
        'en': 'User not found',
    },
    'error.invalid_request': {
        'zh': '无效请求',
        'en': 'Invalid request',
    },
    'error.internal': {
        'zh': '内部服务器错误',
        'en': 'Internal server error',
    },
    'error.empty_content': {
        'zh': '内容不能为空',
        'en': 'Content cannot be empty',
    },
    'error.rate_limited': {
        'zh': '请求过于频繁，请稍后重试',
        'en': 'Rate limited, please try again later',
    },
    'error.unauthorized': {
        'zh': '未授权的请求',
        'en': 'Unauthorized',
    },
    'error.forbidden': {
        'zh': '无权访问',
        'en': 'Forbidden',
    },

    # ---- 记忆操作 ----
    'memory.added': {
        'zh': '记忆已添加',
        'en': 'Memory added',
    },
    'memory.deleted': {
        'zh': '记忆已删除',
        'en': 'Memory deleted',
    },
    'memory.updated': {
        'zh': '记忆已更新',
        'en': 'Memory updated',
    },
    'memory.not_found': {
        'zh': '记忆 {id} 未找到',
        'en': 'Memory {id} not found',
    },
    'memory.search_failed': {
        'zh': '搜索失败: {detail}',
        'en': 'Search failed: {detail}',
    },
    'memory.add_failed': {
        'zh': '添加记忆失败: {detail}',
        'en': 'Failed to add memory: {detail}',
    },

    # ---- 配置 ----
    'config.reload_success': {
        'zh': '配置已重载',
        'en': 'Configuration reloaded',
    },
    'config.reload_failed': {
        'zh': '配置重载失败: {detail}',
        'en': 'Configuration reload failed: {detail}',
    },
    'config.invalid_key': {
        'zh': '不支持的配置项: {key}',
        'en': 'Unsupported configuration key: {key}',
    },
    'config.missing_api_key': {
        'zh': '缺少 API 密钥: {key}',
        'en': 'Missing API key: {key}',
    },
    'config.embedding_not_configured': {
        'zh': 'Embedding 未配置',
        'en': 'Embedding not configured',
    },

    # ---- 实体 ----
    'entity.not_found': {
        'zh': '实体 {name} 未找到',
        'en': 'Entity {name} not found',
    },
    'entity.resolved': {
        'zh': '实体已解析: {original} → {canonical}',
        'en': 'Entity resolved: {original} → {canonical}',
    },
    'entity.alias_added': {
        'zh': '别名已添加: {alias} → {canonical}',
        'en': 'Alias added: {alias} → {canonical}',
    },
    'entity.alias_conflict': {
        'zh': '别名 {alias} 已指向 {existing}',
        'en': 'Alias {alias} already points to {existing}',
    },

    # ---- 任务 ----
    'job.submitted': {
        'zh': '任务已提交: {job_id}',
        'en': 'Job submitted: {job_id}',
    },
    'job.not_found': {
        'zh': '任务 {job_id} 未找到',
        'en': 'Job {job_id} not found',
    },
    'job.cancelled': {
        'zh': '任务已取消: {job_id}',
        'en': 'Job cancelled: {job_id}',
    },
    'job.cannot_cancel': {
        'zh': '无法取消任务 {job_id} (状态: {status})',
        'en': 'Cannot cancel job {job_id} (status: {status})',
    },

    # ---- 整合 ----
    'consolidation.started': {
        'zh': '记忆整合已开始',
        'en': 'Memory consolidation started',
    },
    'consolidation.completed': {
        'zh': '记忆整合已完成',
        'en': 'Memory consolidation completed',
    },
    'consolidation.failed': {
        'zh': '记忆整合失败: {detail}',
        'en': 'Memory consolidation failed: {detail}',
    },

    # ---- 启动信息 ----
    'startup.server_starting': {
        'zh': '服务启动 v{version}',
        'en': 'Server starting v{version}',
    },
    'startup.server_stopped': {
        'zh': '服务已停止',
        'en': 'Server stopped',
    },
    'startup.config_loaded': {
        'zh': '配置已加载',
        'en': 'Configuration loaded',
    },

    # ---- 验证 ----
    'validation.api_key_missing': {
        'zh': '[警告] {key} 未设置 — {feature} 功能将不可用',
        'en': '[WARNING] {key} not set — {feature} will be unavailable',
    },
    'validation.embedding_unavailable': {
        'zh': '[警告] Embedding 模型不可用，向量检索将降级',
        'en': '[WARNING] Embedding model unavailable, vector search will be degraded',
    },
    'validation.all_ok': {
        'zh': '配置验证通过',
        'en': 'Configuration validation passed',
    },
}


def t(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """翻译函数

    Args:
        key: 翻译键 (如 'error.not_found')
        lang: 语言代码 ('zh'/'en'), 默认使用 RECALL_LANG 环境变量
        **kwargs: 格式化参数 (如 id="abc")

    Returns:
        翻译后的字符串。如未找到返回 key 本身。
    """
    if lang is None:
        lang = os.environ.get('RECALL_LANG', DEFAULT_LANG)

    translations = _TRANSLATIONS.get(key)
    if translations is None:
        return key

    text = translations.get(lang) or translations.get('zh') or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


def register_translations(key: str, translations: Dict[str, str]) -> None:
    """注册自定义翻译

    Args:
        key: 翻译键
        translations: { 'zh': '中文', 'en': 'English' }
    """
    _TRANSLATIONS[key] = translations


def get_available_keys() -> list:
    """获取所有可用的翻译键"""
    return sorted(_TRANSLATIONS.keys())


def get_supported_languages() -> list:
    """获取支持的语言列表"""
    return ['zh', 'en']
