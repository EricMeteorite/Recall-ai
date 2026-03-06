"""实体消解器 — Entity Resolution

将同一实体的不同表达形式（大小写、空格、别名等）统一为规范名称。

功能:
- 大小写归一化 (OpenAI → openai)
- 空格归一化 (Open AI → openai)
- 别名管理 (openai / open ai / OPENAI → OpenAI)
- 自动消解: 入库时检查并统一
- API: /v1/entities/resolve, /v1/entities/{name}/aliases
"""

from __future__ import annotations

import json
import os
import re
import threading
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Any

logger = logging.getLogger(__name__)


def _normalize_key(name: str) -> str:
    """生成用于匹配的归一化键: 小写 + 去除多余空格 + 去除特殊字符"""
    s = name.strip().lower()
    s = re.sub(r'[\s_\-]+', '', s)  # 合并所有空白/下划线/连字符
    return s


class EntityResolver:
    """实体消解器

    维护一个 alias → canonical 映射表。
    当新实体名进入系统时，自动查找是否已有规范名。

    存储: JSON 文件持久化到 data_path/entity_aliases.json
    """

    def __init__(self, data_path: str = ""):
        self._lock = threading.Lock()
        # canonical_name → set of aliases (normalized keys)
        self._canonical_to_aliases: Dict[str, Set[str]] = defaultdict(set)
        # normalized_key → canonical_name
        self._alias_to_canonical: Dict[str, str] = {}
        # 原始显示名映射: normalized_key → display_name (保留大小写)
        self._display_names: Dict[str, str] = {}

        self._data_path = data_path
        self._file_path = os.path.join(data_path, 'entity_aliases.json') if data_path else ''

        # 内建规则 (常见缩写/变体)
        self._builtin_aliases: Dict[str, List[str]] = {
            'OpenAI': ['openai', 'open ai', 'open_ai', 'OPENAI', 'Open AI'],
            'GPT-4': ['gpt4', 'gpt 4', 'GPT4', 'gpt-4'],
            'GPT-3.5': ['gpt3.5', 'gpt 3.5', 'GPT3.5', 'gpt-3.5', 'gpt-3.5-turbo'],
            'ChatGPT': ['chatgpt', 'chat gpt', 'Chat GPT', 'CHATGPT'],
            'Claude': ['claude', 'CLAUDE', 'Anthropic Claude'],
            'Anthropic': ['anthropic', 'ANTHROPIC'],
            'LLaMA': ['llama', 'LLAMA', 'Llama', 'LLama'],
            'GitHub': ['github', 'Github', 'GITHUB', 'git hub'],
            'JavaScript': ['javascript', 'js', 'JS', 'Javascript'],
            'TypeScript': ['typescript', 'ts', 'TS', 'Typescript'],
            'Python': ['python', 'PYTHON', 'py'],
            'PostgreSQL': ['postgresql', 'postgres', 'Postgres', 'POSTGRESQL', 'pg', 'PG'],
            'MySQL': ['mysql', 'MYSQL', 'My SQL'],
            'MongoDB': ['mongodb', 'MONGODB', 'Mongo', 'mongo'],
            'Redis': ['redis', 'REDIS'],
            'Docker': ['docker', 'DOCKER'],
            'Kubernetes': ['kubernetes', 'k8s', 'K8S', 'K8s'],
            'AWS': ['aws', 'Amazon Web Services', 'amazon web services'],
            'Azure': ['azure', 'AZURE', 'Microsoft Azure'],
            'GCP': ['gcp', 'Google Cloud', 'google cloud', 'Google Cloud Platform'],
        }

        self._load()
        self._register_builtins()

    # ==================== 公共 API ====================

    def resolve(self, name: str) -> str:
        """解析名称为规范形式

        Args:
            name: 原始实体名

        Returns:
            规范名称（如无匹配则返回原名并注册为新规范名）
        """
        if not name or not name.strip():
            return name

        key = _normalize_key(name)
        with self._lock:
            canonical = self._alias_to_canonical.get(key)
            if canonical:
                return canonical

            # 尝试模糊匹配（编辑距离 <= 1 且长度 >= 4）
            if len(key) >= 4:
                for existing_key, existing_canonical in self._alias_to_canonical.items():
                    if len(existing_key) >= 4 and self._edit_distance_le1(key, existing_key):
                        # 注册这个新别名
                        self._alias_to_canonical[key] = existing_canonical
                        self._canonical_to_aliases[existing_canonical].add(key)
                        self._display_names[key] = name.strip()
                        self._save()
                        return existing_canonical

            # 未找到：注册为新的规范名
            display = name.strip()
            self._alias_to_canonical[key] = display
            self._canonical_to_aliases[display].add(key)
            self._display_names[key] = display
            self._save()
            return display

    def resolve_batch(self, names: List[str]) -> List[str]:
        """批量解析实体名"""
        return [self.resolve(n) for n in names]

    def add_alias(self, alias: str, canonical: str) -> bool:
        """添加别名映射

        Args:
            alias: 别名
            canonical: 规范名

        Returns:
            是否成功添加
        """
        if not alias or not canonical:
            return False

        alias_key = _normalize_key(alias)
        canonical_key = _normalize_key(canonical)

        with self._lock:
            # 如果别名已经指向其他规范名，拒绝
            existing = self._alias_to_canonical.get(alias_key)
            if existing and _normalize_key(existing) != canonical_key:
                logger.warning(
                    "别名 '%s' 已指向 '%s'，无法重新指向 '%s'",
                    alias, existing, canonical,
                )
                return False

            # 确保规范名自身也在映射中
            if canonical_key not in self._alias_to_canonical:
                self._alias_to_canonical[canonical_key] = canonical
                self._canonical_to_aliases[canonical].add(canonical_key)
                self._display_names[canonical_key] = canonical

            self._alias_to_canonical[alias_key] = canonical
            self._canonical_to_aliases[canonical].add(alias_key)
            self._display_names[alias_key] = alias.strip()
            self._save()
            return True

    def remove_alias(self, alias: str) -> bool:
        """移除别名"""
        alias_key = _normalize_key(alias)
        with self._lock:
            canonical = self._alias_to_canonical.pop(alias_key, None)
            if canonical:
                self._canonical_to_aliases[canonical].discard(alias_key)
                self._display_names.pop(alias_key, None)
                self._save()
                return True
            return False

    def get_canonical(self, name: str) -> Optional[str]:
        """获取名称的规范形式（不自动注册）"""
        key = _normalize_key(name)
        with self._lock:
            return self._alias_to_canonical.get(key)

    def get_aliases(self, canonical: str) -> List[str]:
        """获取规范名的所有别名"""
        with self._lock:
            alias_keys = self._canonical_to_aliases.get(canonical, set())
            return [
                self._display_names.get(k, k) for k in alias_keys
                if self._display_names.get(k, k) != canonical
            ]

    def get_all_canonicals(self) -> List[Dict[str, Any]]:
        """获取所有规范名及其别名列表"""
        with self._lock:
            result = []
            for canonical, alias_keys in self._canonical_to_aliases.items():
                aliases = [
                    self._display_names.get(k, k) for k in alias_keys
                    if self._display_names.get(k, k) != canonical
                ]
                result.append({
                    "canonical": canonical,
                    "aliases": aliases,
                    "alias_count": len(aliases),
                })
            return result

    def merge_entities(self, source: str, target: str) -> int:
        """将 source 实体合并到 target（所有 source 的别名转移到 target）

        Returns:
            合并的别名数量
        """
        with self._lock:
            source_aliases = self._canonical_to_aliases.pop(source, set())
            count = 0
            for key in source_aliases:
                self._alias_to_canonical[key] = target
                self._canonical_to_aliases[target].add(key)
                count += 1
            # source 自身也变成 target 的别名
            source_key = _normalize_key(source)
            self._alias_to_canonical[source_key] = target
            self._canonical_to_aliases[target].add(source_key)
            self._display_names[source_key] = source
            self._save()
            return count

    def stats(self) -> Dict[str, Any]:
        """统计信息"""
        with self._lock:
            return {
                "canonical_count": len(self._canonical_to_aliases),
                "alias_count": len(self._alias_to_canonical),
                "display_names_count": len(self._display_names),
            }

    # ==================== 内部方法 ====================

    @staticmethod
    def _edit_distance_le1(a: str, b: str) -> bool:
        """判断两个字符串编辑距离是否 <= 1"""
        if abs(len(a) - len(b)) > 1:
            return False
        if a == b:
            return True
        if len(a) == len(b):
            diff = sum(1 for x, y in zip(a, b) if x != y)
            return diff <= 1
        # 长度差1: 检查是否只有一次插入/删除
        short, long_ = (a, b) if len(a) < len(b) else (b, a)
        i = j = diff = 0
        while i < len(short) and j < len(long_):
            if short[i] != long_[j]:
                diff += 1
                if diff > 1:
                    return False
                j += 1
            else:
                i += 1
                j += 1
        return True

    def _register_builtins(self) -> None:
        """注册内建别名"""
        with self._lock:
            for canonical, aliases in self._builtin_aliases.items():
                canonical_key = _normalize_key(canonical)
                if canonical_key not in self._alias_to_canonical:
                    self._alias_to_canonical[canonical_key] = canonical
                    self._canonical_to_aliases[canonical].add(canonical_key)
                    self._display_names[canonical_key] = canonical
                for alias in aliases:
                    alias_key = _normalize_key(alias)
                    if alias_key not in self._alias_to_canonical:
                        self._alias_to_canonical[alias_key] = canonical
                        self._canonical_to_aliases[canonical].add(alias_key)
                        self._display_names[alias_key] = alias

    def _load(self) -> None:
        """从 JSON 文件加载别名表"""
        if not self._file_path or not os.path.exists(self._file_path):
            return
        try:
            with open(self._file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item in data.get('mappings', []):
                canonical = item['canonical']
                for alias_info in item.get('aliases', []):
                    key = alias_info['key']
                    display = alias_info.get('display', key)
                    self._alias_to_canonical[key] = canonical
                    self._canonical_to_aliases[canonical].add(key)
                    self._display_names[key] = display
                # 规范名自身
                canonical_key = _normalize_key(canonical)
                self._alias_to_canonical[canonical_key] = canonical
                self._canonical_to_aliases[canonical].add(canonical_key)
                self._display_names[canonical_key] = canonical
            logger.info("EntityResolver: 加载 %d 个规范名", len(self._canonical_to_aliases))
        except Exception as e:
            logger.warning("EntityResolver: 加载失败 %s: %s", self._file_path, e)

    def _save(self) -> None:
        """持久化到 JSON 文件"""
        if not self._file_path:
            return
        try:
            os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
            data = {"mappings": []}
            for canonical, alias_keys in self._canonical_to_aliases.items():
                aliases = []
                for key in alias_keys:
                    if key != _normalize_key(canonical):
                        aliases.append({
                            "key": key,
                            "display": self._display_names.get(key, key),
                        })
                data["mappings"].append({
                    "canonical": canonical,
                    "aliases": aliases,
                })
            from recall.utils.atomic_write import atomic_json_dump
            atomic_json_dump(data, self._file_path, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("EntityResolver: 保存失败: %s", e)


# ==================== 单例 ====================

_resolver: Optional[EntityResolver] = None
_resolver_lock = threading.Lock()


def get_entity_resolver(data_path: str = "") -> EntityResolver:
    """获取全局 EntityResolver 实例"""
    global _resolver
    if _resolver is None:
        with _resolver_lock:
            if _resolver is None:
                _resolver = EntityResolver(data_path=data_path)
    return _resolver
