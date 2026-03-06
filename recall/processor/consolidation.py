"""双层记忆整合策略 (Dual-Layer Memory Consolidation)

Phase 7.4.B: 数据量驱动的记忆压缩与归档

双层策略：

Hot Layer（热检索层）：
- 每个实体维护一份结构化摘要（≤4000 tokens）
- 摘要拥有自己的向量索引，参与常规搜索
- 命中热层后可自动展开到原文细节

Cold Layer（冷归档层）：
- 原文永远不删除，仅标记为 archived
- VolumeManager 分卷存储，按需加载
- 原文可通过 archive search 搜索

触发策略（数据量驱动）：
- 每 1000 条新增未整合记忆 → 增量实体摘要更新
- 每 5000 条 → 全量摘要重建
- 手动触发：POST /v1/admin/consolidate

压缩比：~15:1（务实但不激进）
保护：importance >= 0.7 的记忆始终保留在热层
"""

from __future__ import annotations

import os
import json
import re
import time
import logging
import hashlib
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

if TYPE_CHECKING:
    from ..engine import RecallEngine

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Windows GBK 安全打印
# ─────────────────────────────────────────────────────────────────

def _safe_print(msg: str) -> None:
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


# ─────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────

@dataclass
class EntitySummary:
    """实体热层摘要"""
    entity_name: str
    summary: str                           # 结构化摘要文本 (≤4000 tokens)
    source_memory_ids: List[str]           # 来源记忆 ID 列表
    token_count: int = 0                   # 摘要 token 数
    created_at: float = 0.0
    updated_at: float = 0.0
    version: int = 1                       # 摘要版本（每次更新 +1）
    importance: float = 0.5                # 实体重要性
    summary_embedding_id: Optional[str] = None  # 摘要的向量索引 ID

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntitySummary':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ConsolidationResult:
    """整合结果"""
    entities_summarized: int = 0           # 已整合的实体数
    memories_archived: int = 0             # 已归档的记忆数
    compression_ratio: float = 0.0         # 压缩比
    duration_seconds: float = 0.0          # 耗时
    errors: List[str] = field(default_factory=list)
    skipped_high_importance: int = 0       # 因高重要性跳过的记忆数
    new_summaries: int = 0                 # 新建摘要数
    updated_summaries: int = 0             # 更新摘要数

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConsolidationStatus:
    """整合状态"""
    total_memories: int = 0
    unconsolidated_count: int = 0
    entity_summary_count: int = 0
    archived_count: int = 0
    last_consolidation_at: Optional[float] = None
    next_trigger_at: int = 0               # 下一次自动触发的记忆数
    is_running: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────
# 配置常量  
# ─────────────────────────────────────────────────────────────────

# 触发阈值
INCREMENTAL_THRESHOLD = 1000   # 每 N 条新增 → 增量更新
FULL_REBUILD_THRESHOLD = 5000  # 每 N 条新增 → 全量重建

# 摘要约束
MAX_SUMMARY_TOKENS = 4000      # 单实体摘要最大 token 数
MAX_MEMORIES_PER_SUMMARY = 200 # 每个摘要最多处理的记忆数

# 保护阈值
IMPORTANCE_PROTECTION_THRESHOLD = 0.7  # 高重要性保护线

# 压缩目标
TARGET_COMPRESSION_RATIO = 15.0  # 目标压缩比


# ─────────────────────────────────────────────────────────────────
# 主类
# ─────────────────────────────────────────────────────────────────

class ConsolidationManager:
    """双层记忆整合管理器
    
    Hot layer（热检索层）:
    - 一个实体对应一份结构化摘要（≤4000 tokens）
    - 摘要有自己的向量索引，参与常规搜索
    - 命中热层后自动展开到原文细节
    
    Cold layer（冷归档层）:
    - 原文永远不删除，仅标记为 archived
    - VolumeManager 分卷存储，按需加载
    - 原文可通过 archive search 搜索
    
    触发策略（数据量驱动）：
    - 每 1000 条新增未整合记忆 → 增量实体摘要更新
    - 每 5000 条 → 全量摘要重建
    - 手动：POST /v1/admin/consolidate
    
    压缩比: ~15:1（务实但不激进）
    保护: importance >= 0.7 始终保留在热层
    """

    def __init__(self, data_path: str = "recall_data/data"):
        self.data_path = data_path
        self._summaries_dir = os.path.join(data_path, "consolidation")
        self._summaries_file = os.path.join(self._summaries_dir, "entity_summaries.json")
        self._status_file = os.path.join(self._summaries_dir, "consolidation_status.json")
        self._archived_ids_file = os.path.join(self._summaries_dir, "archived_ids.json")

        # 内存状态
        self._entity_summaries: Dict[str, EntitySummary] = {}
        self._archived_ids: Set[str] = set()
        self._unconsolidated_count: int = 0
        self._last_consolidation_at: Optional[float] = None
        self._is_running: bool = False

        # 确保目录存在
        os.makedirs(self._summaries_dir, exist_ok=True)

        # 加载持久化状态
        self._load_state()

    # ─────────────────────────────────────────────────────────────
    # 持久化
    # ─────────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        """从磁盘加载整合状态"""
        # 加载实体摘要
        if os.path.exists(self._summaries_file):
            try:
                with open(self._summaries_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._entity_summaries = {
                    name: EntitySummary.from_dict(d)
                    for name, d in data.items()
                }
                _safe_print(f"[Recall][Consolidation] 📦 加载 {len(self._entity_summaries)} 个实体摘要")
            except Exception as e:
                logger.warning(f"加载实体摘要失败: {e}")
                self._entity_summaries = {}

        # 加载归档 ID
        if os.path.exists(self._archived_ids_file):
            try:
                with open(self._archived_ids_file, 'r', encoding='utf-8') as f:
                    self._archived_ids = set(json.load(f))
                _safe_print(f"[Recall][Consolidation] 🗃️ 加载 {len(self._archived_ids)} 个归档记忆")
            except Exception as e:
                logger.warning(f"加载归档 ID 失败: {e}")
                self._archived_ids = set()

        # 加载状态
        if os.path.exists(self._status_file):
            try:
                with open(self._status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                self._unconsolidated_count = status_data.get('unconsolidated_count', 0)
                self._last_consolidation_at = status_data.get('last_consolidation_at')
            except Exception as e:
                logger.warning(f"加载整合状态失败: {e}")

    def _save_state(self) -> None:
        """持久化整合状态到磁盘（v7.0.10: 原子写入）"""
        try:
            from recall.utils.atomic_write import atomic_json_dump

            # 保存实体摘要
            summaries_data = {
                name: s.to_dict()
                for name, s in self._entity_summaries.items()
            }
            atomic_json_dump(summaries_data, self._summaries_file, ensure_ascii=False, indent=2)

            # 保存归档 ID
            atomic_json_dump(list(self._archived_ids), self._archived_ids_file)

            # 保存状态
            atomic_json_dump({
                'unconsolidated_count': self._unconsolidated_count,
                'last_consolidation_at': self._last_consolidation_at,
            }, self._status_file)
        except Exception as e:
            logger.error(f"保存整合状态失败: {e}")

    # ─────────────────────────────────────────────────────────────
    # 公开 API
    # ─────────────────────────────────────────────────────────────

    def should_consolidate(self, engine: 'RecallEngine') -> bool:
        """检查是否需要执行整合
        
        基于数据量触发：
        - unconsolidated_count >= 1000 → 增量更新
        - unconsolidated_count >= 5000 → 全量重建
        
        Args:
            engine: RecallEngine 实例
            
        Returns:
            是否需要整合
        """
        if self._is_running:
            return False

        # 统计未整合的记忆数
        total = self._count_total_memories(engine)
        consolidated = len(self._archived_ids)
        self._unconsolidated_count = max(0, total - consolidated)

        return self._unconsolidated_count >= INCREMENTAL_THRESHOLD

    def consolidate(
        self,
        engine: 'RecallEngine',
        force: bool = False,
        user_id: str = "default"
    ) -> ConsolidationResult:
        """执行记忆整合
        
        策略：
        1. 收集所有未整合的记忆
        2. 按实体分组
        3. 对每个实体生成/更新摘要（Hot layer）
        4. 将已整合的原文标记为 archived（Cold layer）
        5. importance >= 0.7 的记忆不归档，保留在热层
        
        Args:
            engine: RecallEngine 实例
            force: 是否强制执行（忽略阈值检查）
            user_id: 用户 ID
            
        Returns:
            ConsolidationResult 整合结果
        """
        if self._is_running:
            return ConsolidationResult(
                errors=["整合正在进行中，请稍后再试"]
            )

        if not force and not self.should_consolidate(engine):
            return ConsolidationResult(
                errors=[f"未达到整合阈值 (当前: {self._unconsolidated_count}, 阈值: {INCREMENTAL_THRESHOLD})"]
            )

        self._is_running = True
        start_time = time.time()
        result = ConsolidationResult()

        try:
            _safe_print(f"[Recall][Consolidation] 🚀 开始记忆整合 (未整合: {self._unconsolidated_count})")

            # 判断整合模式
            full_rebuild = self._unconsolidated_count >= FULL_REBUILD_THRESHOLD
            mode = "全量重建" if full_rebuild else "增量更新"
            _safe_print(f"[Recall][Consolidation] 📊 整合模式: {mode}")

            # 1. 收集记忆并按实体分组
            entity_memories = self._collect_entity_memories(engine, user_id, full_rebuild)

            if not entity_memories:
                _safe_print("[Recall][Consolidation] ⚠️ 没有需要整合的记忆")
                result.duration_seconds = time.time() - start_time
                return result

            total_original_chars = 0
            total_summary_chars = 0

            # 2. 对每个实体生成/更新摘要
            for entity_name, memories in entity_memories.items():
                try:
                    summary_result = self._process_entity(
                        engine, entity_name, memories, full_rebuild
                    )

                    if summary_result['is_new']:
                        result.new_summaries += 1
                    else:
                        result.updated_summaries += 1

                    result.entities_summarized += 1
                    total_original_chars += summary_result['original_chars']
                    total_summary_chars += summary_result['summary_chars']

                    # 3. 标记低重要性记忆为 archived
                    for mem_info in memories:
                        mem_id = mem_info.get('id', '')
                        mem_importance = mem_info.get('importance', 0.5)

                        if mem_importance >= IMPORTANCE_PROTECTION_THRESHOLD:
                            result.skipped_high_importance += 1
                            continue

                        if mem_id and mem_id not in self._archived_ids:
                            self._archived_ids.add(mem_id)
                            result.memories_archived += 1

                except Exception as e:
                    error_msg = f"实体 '{entity_name}' 整合失败: {e}"
                    logger.warning(error_msg)
                    result.errors.append(error_msg)

            # 4. 计算压缩比
            if total_summary_chars > 0 and total_original_chars > 0:
                result.compression_ratio = total_original_chars / total_summary_chars
            else:
                result.compression_ratio = 0.0

            # 5. 更新状态
            self._last_consolidation_at = time.time()
            self._unconsolidated_count = 0
            self._save_state()

            result.duration_seconds = time.time() - start_time
            _safe_print(
                f"[Recall][Consolidation] ✅ 整合完成: "
                f"实体={result.entities_summarized}, "
                f"归档={result.memories_archived}, "
                f"压缩比={result.compression_ratio:.1f}:1, "
                f"耗时={result.duration_seconds:.2f}s"
            )

        except Exception as e:
            result.errors.append(f"整合失败: {e}")
            logger.error(f"整合失败: {e}", exc_info=True)
        finally:
            self._is_running = False

        return result

    def get_summary(self, entity_name: str, engine: 'RecallEngine' = None) -> Optional[str]:
        """获取实体摘要文本
        
        Args:
            entity_name: 实体名称
            engine: RecallEngine（当前未使用，预留扩展）
            
        Returns:
            摘要文本，如果不存在返回 None
        """
        summary = self._entity_summaries.get(entity_name)
        if summary:
            return summary.summary
        return None

    def expand_to_original(
        self,
        entity_name: str,
        engine: 'RecallEngine',
        user_id: str = "default",
        limit: int = 50
    ) -> List[Dict]:
        """展开摘要到原始记忆列表
        
        从 Cold layer 加载指定实体关联的所有原始记忆。
        
        Args:
            entity_name: 实体名称（对应摘要的 entity_name）
            engine: RecallEngine 实例
            user_id: 用户 ID
            limit: 最大返回数
            
        Returns:
            原始记忆列表
        """
        summary = self._entity_summaries.get(entity_name)
        if not summary:
            return []

        # 从存储中获取原始记忆
        originals: List[Dict] = []
        scope = engine.storage.get_scope(user_id)

        try:
            all_memories = scope.get_all()
            for mem in all_memories:
                mem_id = mem.get('metadata', {}).get('id', '')
                if mem_id in summary.source_memory_ids:
                    originals.append({
                        'id': mem_id,
                        'content': mem.get('content', ''),
                        'metadata': mem.get('metadata', {}),
                        'is_archived': mem_id in self._archived_ids,
                    })
                    if len(originals) >= limit:
                        break
        except Exception as e:
            logger.warning(f"展开原始记忆失败: {e}")

        return originals

    def get_status(self, engine: 'RecallEngine' = None) -> ConsolidationStatus:
        """获取整合状态
        
        Args:
            engine: RecallEngine 实例（可选，用于实时统计）
            
        Returns:
            ConsolidationStatus 状态对象
        """
        total = 0
        if engine:
            total = self._count_total_memories(engine)
            self._unconsolidated_count = max(0, total - len(self._archived_ids))

        # 计算下一次触发点
        current = self._unconsolidated_count
        next_trigger = INCREMENTAL_THRESHOLD
        if current >= INCREMENTAL_THRESHOLD:
            next_trigger = ((current // INCREMENTAL_THRESHOLD) + 1) * INCREMENTAL_THRESHOLD

        return ConsolidationStatus(
            total_memories=total,
            unconsolidated_count=self._unconsolidated_count,
            entity_summary_count=len(self._entity_summaries),
            archived_count=len(self._archived_ids),
            last_consolidation_at=self._last_consolidation_at,
            next_trigger_at=next_trigger,
            is_running=self._is_running,
        )

    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """获取所有实体摘要（字典形式）"""
        return {
            name: s.to_dict()
            for name, s in self._entity_summaries.items()
        }

    def is_archived(self, memory_id: str) -> bool:
        """检查记忆是否已归档"""
        return memory_id in self._archived_ids

    def notify_new_memory(self) -> None:
        """通知有新记忆写入（用于计数触发）"""
        self._unconsolidated_count += 1

    def remove_memory_references(self, memory_ids: set) -> int:
        """v7.0.14: 从整合状态中清除指定 memory_id 的所有引用
        
        清理：
        1. _archived_ids 中移除
        2. 所有 EntitySummary.source_memory_ids 中移除
        3. 移除后如果 source_memory_ids 为空，删除整个摘要
        
        Args:
            memory_ids: 需要移除的 memory_id 集合
            
        Returns:
            受影响的摘要数量
        """
        if not memory_ids:
            return 0
        
        affected = 0
        
        # 1. 清理归档 ID
        before_count = len(self._archived_ids)
        self._archived_ids -= memory_ids
        removed_archived = before_count - len(self._archived_ids)
        
        # 2. 清理实体摘要中的 source_memory_ids
        empty_summaries = []
        for name, summary in self._entity_summaries.items():
            before = len(summary.source_memory_ids)
            summary.source_memory_ids = [
                mid for mid in summary.source_memory_ids
                if mid not in memory_ids
            ]
            if len(summary.source_memory_ids) < before:
                affected += 1
            # 如果摘要不再引用任何记忆，标记删除
            if not summary.source_memory_ids:
                empty_summaries.append(name)
        
        # 3. 删除空摘要
        for name in empty_summaries:
            del self._entity_summaries[name]
        
        # 持久化
        if affected > 0 or removed_archived > 0:
            self._save_state()
        
        return affected

    def reset_state(self) -> None:
        """v7.0.14: 完全重置整合状态（用于 clear_all）"""
        self._entity_summaries.clear()
        self._archived_ids.clear()
        self._unconsolidated_count = 0
        self._last_consolidation_at = None
        self._save_state()

    # ─────────────────────────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────────────────────────

    def _count_total_memories(self, engine: 'RecallEngine') -> int:
        """统计所有用户的总记忆数"""
        try:
            # 尝试获取用户列表
            users = []
            if hasattr(engine.storage, 'list_users'):
                users = engine.storage.list_users()
            if not users:
                users = ['default']

            total = 0
            for uid in users:
                try:
                    scope = engine.storage.get_scope(uid)
                    memories = scope.get_all()
                    total += len(memories) if memories else 0
                except Exception:
                    pass
            return total
        except Exception:
            return 0

    def _collect_entity_memories(
        self,
        engine: 'RecallEngine',
        user_id: str,
        full_rebuild: bool
    ) -> Dict[str, List[Dict]]:
        """收集并按实体分组记忆
        
        Args:
            engine: RecallEngine 实例
            user_id: 用户 ID
            full_rebuild: 是否全量重建（True = 包含已归档的）
            
        Returns:
            实体名 -> 记忆列表 的映射
        """
        entity_memories: Dict[str, List[Dict]] = defaultdict(list)

        try:
            scope = engine.storage.get_scope(user_id)
            all_memories = scope.get_all()

            for mem in (all_memories or []):
                mem_id = mem.get('metadata', {}).get('id', '')

                # 增量模式下跳过已归档的
                if not full_rebuild and mem_id in self._archived_ids:
                    continue

                entities = mem.get('metadata', {}).get('entities', [])
                importance = mem.get('metadata', {}).get('importance', 0.5)
                content = mem.get('content', '')

                if not content:
                    continue

                mem_info = {
                    'id': mem_id,
                    'content': content,
                    'entities': entities,
                    'importance': importance,
                    'created_at': mem.get('metadata', {}).get('created_at', 0),
                    'metadata': mem.get('metadata', {}),
                }

                if entities:
                    for entity in entities:
                        entity_memories[entity].append(mem_info)
                else:
                    # 无实体的记忆归入 "_general" 类别
                    entity_memories['_general'].append(mem_info)

        except Exception as e:
            logger.warning(f"收集记忆失败: {e}")

        return dict(entity_memories)

    def _process_entity(
        self,
        engine: 'RecallEngine',
        entity_name: str,
        memories: List[Dict],
        full_rebuild: bool
    ) -> Dict[str, Any]:
        """处理单个实体的摘要生成/更新
        
        Args:
            engine: RecallEngine 实例
            entity_name: 实体名称
            memories: 该实体关联的记忆列表
            full_rebuild: 是否全量重建
            
        Returns:
            {'is_new': bool, 'original_chars': int, 'summary_chars': int}
        """
        existing = self._entity_summaries.get(entity_name)
        is_new = existing is None or full_rebuild

        # 限制处理数量
        memories_to_process = memories[:MAX_MEMORIES_PER_SUMMARY]

        # 收集所有原文
        all_contents = [m['content'] for m in memories_to_process]
        original_chars = sum(len(c) for c in all_contents)
        memory_ids = [m['id'] for m in memories_to_process if m.get('id')]

        # 计算平均重要性
        importances = [m.get('importance', 0.5) for m in memories_to_process]
        avg_importance = sum(importances) / len(importances) if importances else 0.5

        # 生成摘要
        if is_new or full_rebuild:
            summary_text = self._generate_summary(
                engine, entity_name, all_contents
            )
        else:
            # 增量更新：合并新记忆到已有摘要
            new_contents = [m['content'] for m in memories_to_process if m['id'] not in (existing.source_memory_ids if existing else [])]
            if new_contents:
                summary_text = self._update_summary(
                    engine, entity_name, existing.summary if existing else "", new_contents
                )
            else:
                summary_text = existing.summary if existing else ""

        summary_chars = len(summary_text)

        # 更新/创建摘要记录
        now = time.time()
        if is_new:
            self._entity_summaries[entity_name] = EntitySummary(
                entity_name=entity_name,
                summary=summary_text,
                source_memory_ids=memory_ids,
                token_count=self._estimate_tokens(summary_text),
                created_at=now,
                updated_at=now,
                version=1,
                importance=avg_importance,
            )
        else:
            existing_summary = self._entity_summaries[entity_name]
            # 合并 source_memory_ids（去重）
            all_ids = list(set(existing_summary.source_memory_ids + memory_ids))
            existing_summary.summary = summary_text
            existing_summary.source_memory_ids = all_ids
            existing_summary.token_count = self._estimate_tokens(summary_text)
            existing_summary.updated_at = now
            existing_summary.version += 1
            existing_summary.importance = max(existing_summary.importance, avg_importance)

        # 为摘要建立向量索引（如果引擎支持）
        self._index_summary(engine, entity_name, summary_text)

        return {
            'is_new': is_new,
            'original_chars': original_chars,
            'summary_chars': summary_chars,
        }

    def _generate_summary(
        self,
        engine: 'RecallEngine',
        entity_name: str,
        contents: List[str]
    ) -> str:
        """使用 LLM 生成实体摘要，失败时回退到抽取式摘要
        
        Args:
            engine: RecallEngine 实例
            entity_name: 实体名称
            contents: 原文列表
            
        Returns:
            摘要文本
        """
        # 合并原文（限制总长度）
        combined = "\n---\n".join(contents)
        max_input_chars = MAX_SUMMARY_TOKENS * 4  # 粗略估算
        if len(combined) > max_input_chars:
            combined = combined[:max_input_chars] + "\n... (已截断)"

        # 尝试 LLM 摘要
        if hasattr(engine, 'llm_client') and engine.llm_client:
            try:
                prompt = self._build_summary_prompt(entity_name, combined)
                response = engine.llm_client.complete(
                    prompt=prompt,
                    max_tokens=MAX_SUMMARY_TOKENS,
                    temperature=0.3
                )
                if response and len(response.strip()) > 20:
                    return response.strip()
            except Exception as e:
                logger.warning(f"LLM 摘要生成失败，回退到抽取式: {e}")

        # 回退：抽取式摘要
        return self._extractive_summary(entity_name, contents)

    def _update_summary(
        self,
        engine: 'RecallEngine',
        entity_name: str,
        existing_summary: str,
        new_contents: List[str]
    ) -> str:
        """增量更新实体摘要
        
        Args:
            engine: RecallEngine 实例
            entity_name: 实体名称
            existing_summary: 现有摘要
            new_contents: 新增原文列表
            
        Returns:
            更新后的摘要
        """
        new_combined = "\n---\n".join(new_contents)
        max_input_chars = MAX_SUMMARY_TOKENS * 2
        if len(new_combined) > max_input_chars:
            new_combined = new_combined[:max_input_chars] + "\n... (已截断)"

        # 尝试 LLM 增量更新
        if hasattr(engine, 'llm_client') and engine.llm_client:
            try:
                prompt = self._build_update_prompt(entity_name, existing_summary, new_combined)
                response = engine.llm_client.complete(
                    prompt=prompt,
                    max_tokens=MAX_SUMMARY_TOKENS,
                    temperature=0.3
                )
                if response and len(response.strip()) > 20:
                    return response.strip()
            except Exception as e:
                logger.warning(f"LLM 增量更新失败，回退到拼接: {e}")

        # 回退：简单拼接
        new_extract = self._extractive_summary(entity_name, new_contents)
        return f"{existing_summary}\n\n[增量补充]\n{new_extract}"

    def _extractive_summary(self, entity_name: str, contents: List[str]) -> str:
        """抽取式摘要（LLM 不可用时的回退方案）
        
        策略：
        1. 选取首尾句
        2. 保留含实体名称的句子
        3. 去重
        4. 控制总长度
        
        Args:
            entity_name: 实体名称
            contents: 原文列表
            
        Returns:
            抽取式摘要
        """
        selected_sentences: List[str] = []
        seen_hashes: Set[str] = set()
        max_chars = MAX_SUMMARY_TOKENS * 3  # ~3 chars/token 估算

        entity_lower = entity_name.lower()
        current_chars = 0

        for content in contents:
            # 分句
            sentences = self._split_sentences(content)

            for sent in sentences:
                sent_stripped = sent.strip()
                if not sent_stripped or len(sent_stripped) < 10:
                    continue

                # 去重
                sent_hash = hashlib.md5(sent_stripped.encode()).hexdigest()[:8]
                if sent_hash in seen_hashes:
                    continue

                # 优先包含实体名称的句子
                is_relevant = entity_lower in sent_stripped.lower()
                
                if is_relevant or len(selected_sentences) < 5:
                    seen_hashes.add(sent_hash)
                    selected_sentences.append(sent_stripped)
                    current_chars += len(sent_stripped)

                    if current_chars >= max_chars:
                        break

            if current_chars >= max_chars:
                break

        if not selected_sentences:
            # 至少返回前几条内容的截断
            for c in contents[:5]:
                if c.strip():
                    selected_sentences.append(c[:200])

        header = f"[{entity_name}] 摘要（抽取式）:\n"
        return header + "\n".join(f"- {s}" for s in selected_sentences)

    def _split_sentences(self, text: str) -> List[str]:
        """简单分句"""
        # 中文/英文分句
        sentences = re.split(r'[。！？.!?\n]+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _build_summary_prompt(self, entity_name: str, combined_text: str) -> str:
        """构建 LLM 摘要 prompt"""
        return f"""请为实体「{entity_name}」生成一份结构化摘要。

要求：
1. 保留所有关键事实、属性、关系、事件
2. 使用简洁的条目格式
3. 按时间顺序或逻辑关系组织
4. 总长度控制在 2000 字以内
5. 不要遗漏任何重要信息

以下是关于「{entity_name}」的所有原始记录：

{combined_text}

请输出结构化摘要："""

    def _build_update_prompt(self, entity_name: str, existing_summary: str, new_text: str) -> str:
        """构建增量更新 prompt"""
        return f"""以下是实体「{entity_name}」的现有摘要，请将新信息整合进去。

要求：
1. 保留现有摘要中的所有信息
2. 将新信息无缝整合
3. 如有矛盾，以新信息为准
4. 总长度控制在 2000 字以内

现有摘要：
{existing_summary}

新增信息：
{new_text}

请输出更新后的完整摘要："""

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数"""
        # 中文约 2 chars/token，英文约 4 chars/token
        # 取折中值 ~3 chars/token
        return len(text) // 3 if text else 0

    def _index_summary(self, engine: 'RecallEngine', entity_name: str, summary_text: str) -> None:
        """为摘要建立向量索引"""
        try:
            if not hasattr(engine, 'vector_index') or not engine.vector_index:
                return

            summary_id = f"summary_{hashlib.md5(entity_name.encode()).hexdigest()[:12]}"
            
            # 使用 embedding_backend 编码
            if hasattr(engine, 'embedding_backend') and engine.embedding_backend:
                embedding = engine.embedding_backend.encode(summary_text[:2000])
                if hasattr(engine.vector_index, 'add'):
                    engine.vector_index.add(summary_id, embedding)
                    self._entity_summaries[entity_name].summary_embedding_id = summary_id
            elif hasattr(engine.vector_index, 'add_text'):
                engine.vector_index.add_text(summary_id, summary_text[:2000])
                self._entity_summaries[entity_name].summary_embedding_id = summary_id
        except Exception as e:
            logger.warning(f"摘要向量索引失败 (不影响主流程): {e}")


# ─────────────────────────────────────────────────────────────────
# 模块导出
# ─────────────────────────────────────────────────────────────────

__all__ = [
    'ConsolidationManager',
    'ConsolidationResult',
    'ConsolidationStatus',
    'EntitySummary',
    'INCREMENTAL_THRESHOLD',
    'FULL_REBUILD_THRESHOLD',
    'IMPORTANCE_PROTECTION_THRESHOLD',
]
