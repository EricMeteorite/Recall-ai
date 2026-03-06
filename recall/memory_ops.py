"""
Recall v7.0 - Memory Operations Module
Extracted from engine.py for facade pattern.
Handles: add, add_turn, add_batch, delete, update, clear, clear_all
"""
from __future__ import annotations

import os
import time
import uuid
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from .storage import ConsolidatedEntity
from .utils.perf_monitor import MetricType
from .utils.task_manager import TaskType, get_task_manager

if TYPE_CHECKING:
    from .engine import RecallEngine


# Windows GBK 编码兼容的安全打印函数（从 engine.py 复制）
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


class MemoryOperations:
    """Handles all memory CRUD operations, delegated from RecallEngine.

    Every public/private method here was extracted from RecallEngine.
    Engine state is accessed exclusively via ``self._engine``.
    """

    def __init__(self, engine: 'RecallEngine'):
        self._engine = engine

    # ==================== add ====================

    def add(
        self,
        content: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        check_consistency: bool = True
    ):
        """添加记忆（从 RecallEngine.add 提取）"""
        from .engine import AddResult

        engine = self._engine
        start_time = time.time()
        consistency_warnings: List[str] = []

        # v7.0.9: 初始化 relations 变量，避免后续 'relations' in dir() 反模式
        relations: list = []

        # 获取任务管理器
        task_manager = get_task_manager()
        character_id = metadata.get('character_id', 'default') if metadata else 'default'
        # v5.0: 非 RP 模式下强制为 default（不按角色隔离）
        if not engine._mode.character_dimension_enabled:
            character_id = "default"
        role = metadata.get('role', 'unknown') if metadata else 'unknown'

        # 生成消息签名用于追踪
        msg_hash = f"{hash(content[:100]) % 10000:04d}"
        _safe_print(f"[Engine][Add] 开始处理: user={user_id}, char={character_id}, role={role}, hash={msg_hash}")
        _safe_print(f"[Engine][Add]    内容长度={len(content)}")

        # 创建父任务 - 记忆处理流程
        parent_task = task_manager.create_task(
            task_type=TaskType.MEMORY_SAVE,
            name="保存记忆",
            user_id=user_id,
            character_id=character_id,
            metadata={'content_length': len(content)}
        )
        task_manager.start_task(parent_task.id, "开始处理记忆...")

        # === Recall 4.1: Episode 变量声明（创建移到去重检查通过后）===
        current_episode = None

        try:
            # 【升级】去重检查：优先使用三阶段去重器（Phase 2），回退到简单字符串匹配
            # 任务追踪：去重检查
            dedup_task = task_manager.create_task(
                task_type=TaskType.DEDUP_CHECK,
                name="去重检查",
                user_id=user_id,
                character_id=character_id,
                parent_task_id=parent_task.id
            )
            task_manager.start_task(dedup_task.id, "检查重复记忆...")

            scope = engine.storage.get_scope(user_id)
            existing_memories = scope.get_all(limit=100)  # 检查最近100条
            content_normalized = content.strip()

            # ========== v4.2 性能优化：预计算 Embedding ==========
            content_embedding = None
            # v7.0.3: 优先从 RecallConfig 读取（之前直接读 os.environ）
            embedding_reuse_enabled = True
            try:
                from .config import RecallConfig
                _cfg = RecallConfig.from_env()
                embedding_reuse_enabled = getattr(_cfg, 'embedding_reuse_enabled', True)
            except Exception:
                embedding_reuse_enabled = os.environ.get('EMBEDDING_REUSE_ENABLED', 'true').lower() == 'true'

            if embedding_reuse_enabled and engine._vector_index and engine._vector_index.enabled:
                try:
                    content_embedding = engine._vector_index.encode(content_normalized)
                    _safe_print(f"[Recall] Embedding 预计算完成: dim={len(content_embedding)}")
                except Exception as e:
                    _safe_print(f"[Recall] Embedding 预计算失败（回退到独立计算）: {e}")
                    content_embedding = None

            # 尝试使用三阶段去重器
            if engine.deduplicator is not None and existing_memories:
                try:
                    task_manager.update_task(dedup_task.id, progress=0.3, message="三阶段去重分析...")
                    from .processor.three_stage_deduplicator import DedupItem
                    import uuid as uuid_module

                    new_item = DedupItem(
                        id=str(uuid_module.uuid4()),
                        name=content_normalized[:100],
                        content=content_normalized,
                        item_type="memory"
                    )

                    if content_embedding is not None:
                        new_item.embedding = content_embedding.tolist() if hasattr(content_embedding, 'tolist') else list(content_embedding)

                    existing_items = []
                    for mem in existing_memories:
                        mem_content = mem.get('content', '').strip()
                        if mem_content:
                            existing_items.append(DedupItem(
                                id=mem.get('metadata', {}).get('id', str(uuid_module.uuid4())),
                                name=mem_content[:100],
                                content=mem_content,
                                item_type="memory"
                            ))

                    if existing_items:
                        dedup_result = engine.deduplicator.deduplicate([new_item], existing_items)

                        if dedup_result.matches:
                            match = dedup_result.matches[0]
                            _safe_print(f"[Engine][Add] [SKIP] 三阶段去重: type={match.match_type.value}, conf={match.confidence:.2f}")
                            _safe_print(f"[Engine][Add]    reason={match.reason}")
                            task_manager.complete_task(dedup_task.id, "发现重复记忆")
                            task_manager.complete_task(parent_task.id, "记忆已存在，跳过保存")
                            return AddResult(
                                id=match.matched_item.id if match.matched_item else 'unknown',
                                success=False,
                                entities=[],
                                message=f"记忆内容已存在（{match.match_type.value}匹配，置信度{match.confidence:.0%}）"
                            )
                        else:
                            _safe_print(f"[Engine][Add]    三阶段去重: 未发现重复")
                except Exception as e:
                    _safe_print(f"[Engine][Add] [WARN] 三阶段去重失败，回退简单匹配: {e}")

            # 回退：简单字符串精确匹配
            for mem in existing_memories:
                existing_content = mem.get('content', '').strip()
                if existing_content == content_normalized:
                    mem_id = mem.get('metadata', {}).get('id', 'unknown')
                    _safe_print(f"[Engine][Add] [SKIP] 精确匹配去重: mem_id={mem_id}")
                    task_manager.complete_task(dedup_task.id, "发现重复记忆")
                    task_manager.complete_task(parent_task.id, "记忆已存在，跳过保存")
                    return AddResult(
                        id=mem.get('metadata', {}).get('id', 'unknown'),
                        success=False,
                        entities=[],
                        message="记忆内容已存在，跳过重复保存"
                    )

            # 去重检查完成，无重复
            task_manager.complete_task(dedup_task.id, "无重复记忆")

            # === Recall 4.1: 创建 Episode（去重通过后才创建）===
            if engine._episode_tracking_enabled and engine.episode_store:
                try:
                    from .models.temporal import EpisodicNode, EpisodeType
                    current_episode = EpisodicNode(
                        source_type=EpisodeType.MESSAGE,
                        content=content,
                        user_id=user_id,
                        source_description=f"User: {user_id}",
                    )
                    engine.episode_store.save(current_episode)
                    _safe_print(f"[Recall] Episode 已创建: {current_episode.uuid}")
                except Exception as e:
                    _safe_print(f"[Recall] Episode 创建失败（不影响主流程）: {e}")
                    current_episode = None

            # 1. 提取实体
            entity_task = task_manager.create_task(
                task_type=TaskType.ENTITY_EXTRACTION,
                name="实体提取",
                user_id=user_id,
                character_id=character_id,
                parent_task_id=parent_task.id
            )
            task_manager.start_task(entity_task.id, "分析文本实体...")

            extraction_result = None
            if engine.smart_extractor is not None:
                try:
                    task_manager.update_task(entity_task.id, progress=0.3, message="SmartExtractor 分析中...")
                    extraction_result = engine.smart_extractor.extract(content)
                    entities = extraction_result.entities
                    entity_names = [e.name for e in entities]
                    keywords = extraction_result.keywords
                    _safe_print(f"[Recall] SmartExtractor: mode={extraction_result.mode_used.value}, entities={len(entities)}, complexity={extraction_result.complexity_score:.2f}")
                    task_manager.complete_task(entity_task.id, f"提取 {len(entities)} 个实体", {'entities': entity_names, 'mode': extraction_result.mode_used.value})
                except Exception as e:
                    _safe_print(f"[Recall] SmartExtractor 失败，回退到默认抽取器: {e}")
                    extraction_result = None

            if extraction_result is None:
                task_manager.update_task(entity_task.id, progress=0.5, message="规则提取器分析中...")
                entities = engine.entity_extractor.extract(content)
                entity_names = [e.name for e in entities]
                keywords = engine.entity_extractor.extract_keywords(content)
                task_manager.complete_task(entity_task.id, f"提取 {len(entities)} 个实体", {'entities': entity_names, 'mode': 'rule'})

            # 2. 提取关键词（如果 SmartExtractor 未处理）
            if extraction_result is None:
                keywords = engine.entity_extractor.extract_keywords(content)

            # 2.3 Entity Resolution（实体消歧，v7.0.1：之前缺失）
            if entities and hasattr(engine, '_entity_resolver') and engine._entity_resolver:
                try:
                    for ent in entities:
                        resolved_name = engine._entity_resolver.resolve(ent.name)
                        if resolved_name != ent.name:
                            _safe_print(f"[Recall][Add] 实体消歧: '{ent.name}' -> '{resolved_name}'")
                            ent.name = resolved_name
                    entity_names = [e.name for e in entities]
                except Exception as e:
                    _safe_print(f"[Recall][Add] 实体消歧失败（不影响主流程）: {e}")

            # 2.5 v7.0: 时间意图解析 — 提取时间范围并附加到 metadata
            if getattr(engine, '_time_intent_parser', None):
                try:
                    time_range = engine._time_intent_parser.parse(content)
                    if time_range:
                        if metadata is None:
                            metadata = {}
                        metadata['time_range'] = {
                            'start': time_range.start.isoformat() if time_range.start else None,
                            'end': time_range.end.isoformat() if time_range.end else None,
                            'label': getattr(time_range, 'label', None),
                            'confidence': getattr(time_range, 'confidence', 1.0),
                        }
                        _safe_print(f"[Recall v7.0] 时间意图: {metadata['time_range'].get('label', 'unknown')}")
                except Exception as e:
                    _safe_print(f"[Recall v7.0] TimeIntentParser 解析失败: {e}")

            # v4.2: 初始化统一分析器结果变量和控制标志
            unified_analysis_result = None
            use_unified_analyzer = False

            # 3. 一致性检查
            if check_consistency:
                consistency_task = task_manager.create_task(
                    task_type=TaskType.CONSISTENCY_CHECK,
                    name="一致性检查",
                    user_id=user_id,
                    character_id=character_id,
                    parent_task_id=parent_task.id
                )
                task_manager.start_task(consistency_task.id, "检查记忆一致性...")

                existing_memories = engine.search(content, user_id=user_id, top_k=5)
                _safe_print(f"[Recall] 一致性检查: 找到 {len(existing_memories)} 条相关记忆")
                for i, m in enumerate(existing_memories):
                    _safe_print(f"[Recall]   [{i+1}] {m.content[:30]}...")

                task_manager.update_task(consistency_task.id, progress=0.3, message=f"规则检测 {len(existing_memories)} 条相关记忆...")

                # 阶段1：正则规则检测（快速）
                consistency = engine.consistency_checker.check(
                    content,
                    [{'content': m.content} for m in existing_memories]
                )
                _safe_print(f"[Recall] 一致性检查结果: is_consistent={consistency.is_consistent}, violations={len(consistency.violations)}")
                if not consistency.is_consistent:
                    for v in consistency.violations:
                        warning_msg = v.description
                        consistency_warnings.append(warning_msg)
                        _safe_print(f"[Recall] 一致性警告: {warning_msg}")

                    # 将一致性违规存储到矛盾管理器
                    if engine.contradiction_manager is not None:
                        try:
                            from .models.temporal import TemporalFact, Contradiction, ContradictionType
                            from datetime import datetime
                            import uuid as uuid_module

                            for v in consistency.violations:
                                contradiction_type = ContradictionType.DIRECT
                                if hasattr(v, 'type'):
                                    type_str = v.type.value if hasattr(v.type, 'value') else str(v.type)
                                    if 'timeline' in type_str.lower() or 'temporal' in type_str.lower():
                                        contradiction_type = ContradictionType.TEMPORAL
                                    elif 'logic' in type_str.lower():
                                        contradiction_type = ContradictionType.LOGICAL

                                evidence = v.evidence if hasattr(v, 'evidence') and v.evidence else [content]
                                new_text = evidence[0] if len(evidence) > 0 else content
                                old_text = evidence[1] if len(evidence) > 1 else ""

                                new_fact = TemporalFact(
                                    uuid=str(uuid_module.uuid4()),
                                    fact=new_text[:200],
                                    source_text=new_text[:200],
                                    user_id=user_id
                                )
                                old_fact = TemporalFact(
                                    uuid=str(uuid_module.uuid4()),
                                    fact=old_text[:200],
                                    source_text=old_text[:200],
                                    user_id=user_id
                                )

                                contradiction = Contradiction(
                                    uuid=str(uuid_module.uuid4()),
                                    old_fact=old_fact,
                                    new_fact=new_fact,
                                    contradiction_type=contradiction_type,
                                    confidence=v.severity if hasattr(v, 'severity') else 0.8,
                                    detected_at=datetime.now(),
                                    notes=v.description[:200] if hasattr(v, 'description') else ""
                                )
                                engine.contradiction_manager.add_pending(contradiction)
                                _safe_print(f"[Recall] 矛盾已记录: {v.description[:50]}...")
                        except Exception as e:
                            _safe_print(f"[Recall] 矛盾记录失败（不影响主流程）: {e}")

                # === v4.2 优化：使用统一分析器合并矛盾检测和关系提取 ===
                use_unified_analyzer = False
                if engine.unified_analyzer and existing_memories:
                    from .graph import DetectionStrategy
                    if engine.contradiction_manager is None:
                        use_unified_analyzer = True
                    elif engine.contradiction_manager.strategy != DetectionStrategy.RULE:
                        use_unified_analyzer = True
                    else:
                        _safe_print(f"[Recall][v4.2] 矛盾检测策略为 RULE，跳过统一分析器")

                if use_unified_analyzer:
                    try:
                        from .processor.unified_analyzer import UnifiedAnalysisInput, AnalysisTask

                        _safe_print(f"[Recall][v4.2] 使用统一分析器 (合并矛盾检测+关系提取)")

                        unified_task = task_manager.create_task(
                            task_type=TaskType.CONTRADICTION_DETECTION,
                            name="统一LLM分析",
                            user_id=user_id,
                            character_id=character_id,
                            parent_task_id=parent_task.id
                        )
                        task_manager.start_task(unified_task.id, "统一分析器处理中...")

                        existing_texts = [m.content if hasattr(m, 'content') else str(m) for m in existing_memories]

                        unified_analysis_result = engine.unified_analyzer.analyze(UnifiedAnalysisInput(
                            content=content,
                            entities=entity_names,
                            existing_memories=existing_texts,
                            user_id=user_id,
                            tasks=[AnalysisTask.CONTRADICTION, AnalysisTask.RELATION]
                        ))

                        # 处理矛盾检测结果
                        if unified_analysis_result.contradictions:
                            for c in unified_analysis_result.contradictions:
                                old_fact_text = c.get('old_fact', '')[:50] if c.get('old_fact') else ''
                                new_fact_text = c.get('new_fact', '')[:50] if c.get('new_fact') else ''
                                warning_msg = f"[统一分析] {old_fact_text} vs {new_fact_text}"
                                consistency_warnings.append(warning_msg)
                                _safe_print(f"[Recall] 统一分析检测到矛盾: {warning_msg}")

                                if engine.contradiction_manager:
                                    try:
                                        from .models.temporal import TemporalFact, Contradiction, ContradictionType
                                        from datetime import datetime
                                        import uuid as uuid_module

                                        contradiction_type = ContradictionType.DIRECT
                                        if c.get('type', '').lower() in ['temporal', 'timeline', '时态矛盾']:
                                            contradiction_type = ContradictionType.TEMPORAL
                                        elif c.get('type', '').lower() in ['logical', '逻辑矛盾']:
                                            contradiction_type = ContradictionType.LOGICAL

                                        new_fact_obj = TemporalFact(
                                            uuid=str(uuid_module.uuid4()),
                                            fact=c.get('new_fact', '')[:200],
                                            source_text=c.get('new_fact', '')[:200],
                                            user_id=user_id
                                        )
                                        old_fact_obj = TemporalFact(
                                            uuid=str(uuid_module.uuid4()),
                                            fact=c.get('old_fact', '')[:200],
                                            source_text=c.get('old_fact', '')[:200],
                                            user_id=user_id
                                        )

                                        contradiction_obj = Contradiction(
                                            uuid=str(uuid_module.uuid4()),
                                            old_fact=old_fact_obj,
                                            new_fact=new_fact_obj,
                                            contradiction_type=contradiction_type,
                                            confidence=c.get('confidence', 0.8),
                                            detected_at=datetime.now(),
                                            notes=warning_msg[:200]
                                        )
                                        engine.contradiction_manager.add_pending(contradiction_obj)
                                    except Exception as e:
                                        _safe_print(f"[Recall] 矛盾对象创建失败（不影响主流程）: {e}")
                            _safe_print(f"[Recall][v4.2] 统一分析发现 {len(unified_analysis_result.contradictions)} 个矛盾")

                        task_manager.complete_task(unified_task.id, f"分析完成，矛盾={len(unified_analysis_result.contradictions)}，关系={len(unified_analysis_result.relations)}")
                        _safe_print(f"[Recall][v4.2] 统一分析完成: 矛盾={len(unified_analysis_result.contradictions)}, 关系={len(unified_analysis_result.relations)}")
                    except Exception as e:
                        _safe_print(f"[Recall][v4.2] 统一分析器失败，回退到传统模式: {e}")
                        unified_analysis_result = None

                # 回退：传统 LLM 深度矛盾检测
                if not use_unified_analyzer and engine.contradiction_manager is not None and existing_memories:
                    contradiction_task = None  # v7.0.12: 修复 — 防止 NameError
                    try:
                        from .models.temporal import TemporalFact, Contradiction
                        from .graph import DetectionStrategy
                        from datetime import datetime
                        import uuid as uuid_module

                        if engine.contradiction_manager.strategy != DetectionStrategy.RULE:
                            contradiction_task = task_manager.create_task(
                                task_type=TaskType.CONTRADICTION_DETECTION,
                                name="LLM矛盾检测",
                                user_id=user_id,
                                character_id=character_id,
                                parent_task_id=parent_task.id
                            )
                            task_manager.start_task(contradiction_task.id, f"LLM深度矛盾检测 (策略: {engine.contradiction_manager.strategy.value})...")

                            _safe_print(f"[Recall] 启用LLM深度矛盾检测 (策略: {engine.contradiction_manager.strategy.value})")

                            new_fact = TemporalFact(
                                uuid=str(uuid_module.uuid4()),
                                fact=content[:500],
                                source_text=content,
                                user_id=user_id
                            )

                            existing_facts = []
                            for m in existing_memories:
                                existing_facts.append(TemporalFact(
                                    uuid=m.id if hasattr(m, 'id') else str(uuid_module.uuid4()),
                                    fact=m.content[:500] if hasattr(m, 'content') else str(m)[:500],
                                    source_text=m.content if hasattr(m, 'content') else str(m),
                                    user_id=user_id
                                ))

                            task_manager.update_task(contradiction_task.id, progress=0.5, message="调用LLM分析...")

                            llm_contradictions = engine.contradiction_manager.detect(
                                new_fact=new_fact,
                                existing_facts=existing_facts,
                                context=content
                            )

                            for c in llm_contradictions:
                                engine.contradiction_manager.add_pending(c)
                                warning_msg = f"[LLM检测] {c.old_fact.fact[:50]} vs {c.new_fact.fact[:50]}"
                                consistency_warnings.append(warning_msg)
                                _safe_print(f"[Recall] LLM检测到矛盾: {warning_msg}")

                            if llm_contradictions:
                                _safe_print(f"[Recall] LLM深度检测发现 {len(llm_contradictions)} 个额外矛盾")

                            task_manager.complete_task(contradiction_task.id, f"发现 {len(llm_contradictions)} 个矛盾", {'count': len(llm_contradictions)})
                    except Exception as e:
                        _safe_print(f"[Recall] LLM矛盾检测失败（不影响主流程）: {e}")
                        try:
                            if contradiction_task is not None:
                                task_manager.fail_task(contradiction_task.id, str(e))
                        except Exception:
                            pass

                # 一致性检查完成
                task_manager.complete_task(consistency_task.id, f"检查完成，{len(consistency_warnings)} 个警告", {'warnings': len(consistency_warnings)})

            # 4. 生成ID并存储
            memory_id = f"mem_{uuid.uuid4().hex[:12]}"

            memory_data = {
                'id': memory_id,
                'content': content,
                'user_id': user_id,
                'entities': entity_names,
                'keywords': keywords,
                'metadata': metadata or {},
                'created_at': time.time()
            }

            scope = engine.storage.get_scope(user_id)
            scope.add(content, metadata={
                'id': memory_id,
                'entities': entity_names,
                'keywords': keywords,
                **(metadata or {})
            })

            # === 以下操作失败不影响主流程 ===
            try:
                turn_number = engine.volume_manager.append_turn({
                    'memory_id': memory_id,
                    'user_id': user_id,
                    'content': content,
                    'entities': entity_names,
                    'keywords': keywords,
                    'metadata': metadata or {},
                    'created_at': time.time()
                })
            except Exception as e:
                _safe_print(f"[Recall] Archive保存失败（不影响主流程）: {e}")

            # 5. 更新索引
            index_task = task_manager.create_task(
                task_type=TaskType.INDEX_UPDATE,
                name="索引更新",
                user_id=user_id,
                character_id=character_id,
                parent_task_id=parent_task.id
            )
            task_manager.start_task(index_task.id, "更新检索索引...")

            # v7.0.9: 每个索引独立 try/except，一个索引失败不影响其他索引
            if engine._entity_index:
                try:
                    task_manager.update_task(index_task.id, progress=0.2, message="更新实体索引...")
                    for entity in entities:
                        entity_type = getattr(entity, 'entity_type', None)
                        if entity_type is None and hasattr(entity, 'get'):
                            entity_type = entity.get('entity_type', 'UNKNOWN')
                        if entity_type is None:
                            entity_type = 'UNKNOWN'

                        aliases = getattr(entity, 'aliases', None)
                        if aliases is None and hasattr(entity, 'get'):
                            aliases = entity.get('aliases', [])

                        confidence = getattr(entity, 'confidence', None)
                        if confidence is None and hasattr(entity, 'get'):
                            confidence = entity.get('confidence', 0.5)
                        if confidence is None:
                            confidence = 0.5

                        engine._entity_index.add_entity_occurrence(
                            entity_name=entity.name,
                            turn_id=memory_id,
                            context=content[:200],
                            entity_type=entity_type,
                            aliases=aliases,
                            confidence=confidence
                        )
                except Exception as e:
                    _safe_print(f"[Recall] 实体索引更新失败（不影响主流程）: {e}")

            if engine._inverted_index:
                try:
                    task_manager.update_task(index_task.id, progress=0.4, message="更新倒排索引...")
                    engine._inverted_index.add_batch(keywords, memory_id)
                except Exception as e:
                    _safe_print(f"[Recall] 倒排索引更新失败（不影响主流程）: {e}")

            if engine._ngram_index:
                try:
                    task_manager.update_task(index_task.id, progress=0.6, message="更新N-gram索引...")
                    engine._ngram_index.add(memory_id, content)
                except Exception as e:
                    _safe_print(f"[Recall] N-gram索引更新失败（不影响主流程）: {e}")

            if engine._vector_index:
                try:
                    task_manager.update_task(index_task.id, progress=0.8, message="更新向量索引...")
                    if content_embedding is not None:
                        engine._vector_index.add(memory_id, content_embedding)
                        _safe_print(f"[Recall] 向量索引已复用预计算 embedding")
                    else:
                        engine._vector_index.add_text(memory_id, content)
                except Exception as e:
                    _safe_print(f"[Recall] 向量索引更新失败（不影响主流程）: {e}")

            # v7.0.2: 同步写入 IVF 索引（如果已激活）
            if getattr(engine, '_vector_index_ivf', None) is not None:
                try:
                    if content_embedding is not None:
                        vec = content_embedding.tolist() if hasattr(content_embedding, 'tolist') else list(content_embedding)
                    elif engine._vector_index and hasattr(engine._vector_index, 'encode'):
                        vec = engine._vector_index.encode(content)
                        vec = vec.tolist() if hasattr(vec, 'tolist') else list(vec)
                    else:
                        vec = None
                    if vec is not None:
                        engine._vector_index_ivf.add(memory_id, vec)
                        _safe_print(f"[Recall v7.0] IVF 索引同步写入成功")
                except Exception as e:
                    _safe_print(f"[Recall v7.0] IVF 索引同步写入失败（不影响主流程）: {e}")

            # v5.0: 更新元数据索引
            if engine._metadata_index:
                try:
                    engine._metadata_index.add(
                        memory_id=memory_id,
                        source=metadata.get('source', '') if metadata else '',
                        tags=metadata.get('tags', []) if metadata else [],
                        category=metadata.get('category', '') if metadata else '',
                        content_type=metadata.get('content_type', '') if metadata else '',
                        event_time=metadata.get('event_time', '') if metadata else '',
                    )
                except Exception as e:
                    _safe_print(f"[Recall] 元数据索引更新失败（不影响主流程）: {e}")

            # v5.0: 更新时态索引
            if metadata and metadata.get('event_time') and engine.temporal_graph and hasattr(engine.temporal_graph, '_temporal_index'):
                try:
                    from .index.temporal_index import TemporalEntry, TimeRange
                    from datetime import datetime as _dt
                    event_time_str = metadata['event_time']
                    event_dt = None
                    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%f'):
                        try:
                            event_dt = _dt.strptime(event_time_str, fmt)
                            break
                        except ValueError:
                            continue
                    if event_dt:
                        now = _dt.now()
                        entry = TemporalEntry(
                            doc_id=memory_id,
                            fact_range=TimeRange(start=event_dt),
                            known_at=now,
                            system_range=TimeRange(start=now),
                            subject=user_id,
                            predicate='memory'
                        )
                        engine.temporal_graph._temporal_index.add(entry)
                except Exception as e:
                    _safe_print(f"[Recall] 时态索引更新失败（不影响主流程）: {e}")

            # v7.0 B-1: Backend Abstraction Layer — 双写到 SQLite/Qdrant/PG 后端
            # 与传统索引并行写入，确保向后兼容
            if getattr(engine, '_storage_backend', None):
                try:
                    engine._storage_backend.save(memory_id, {
                        'content': content,
                        'metadata': metadata or {},
                        'namespace': character_id,
                        'source': role,
                        'user_id': user_id,
                        'session_id': metadata.get('session_id', '') if metadata else '',
                        'importance': metadata.get('importance', 0.5) if metadata else 0.5,
                    })
                except Exception as e:
                    _safe_print(f"[Recall v7.0] StorageBackend 双写失败: {e}")

            if getattr(engine, '_vector_backend', None) and content_embedding is not None:
                try:
                    vec = content_embedding.tolist() if hasattr(content_embedding, 'tolist') else list(content_embedding)
                    engine._vector_backend.add(
                        memory_id, vec,
                        {'content': content[:200], 'user_id': user_id, 'namespace': character_id}
                    )
                except Exception as e:
                    _safe_print(f"[Recall v7.0] VectorBackend 双写失败: {e}")

            if getattr(engine, '_text_search_backend', None):
                try:
                    engine._text_search_backend.add(
                        memory_id, content,
                        {'user_id': user_id, 'entities': entity_names, 'namespace': character_id}
                    )
                except Exception as e:
                    _safe_print(f"[Recall v7.0] TextSearchBackend 双写失败: {e}")

            task_manager.complete_task(index_task.id, "索引更新完成")

            # 5.5 缓存内容到检索器
            try:
                engine.retriever.cache_content(memory_id, content)
                if hasattr(engine.retriever, 'cache_metadata'):
                    engine.retriever.cache_metadata(memory_id, metadata or {})
                if hasattr(engine.retriever, 'cache_entities'):
                    entity_names = [e.name for e in entities] if entities else []
                    engine.retriever.cache_entities(memory_id, entity_names)
            except Exception as e:
                _safe_print(f"[Recall] 缓存更新失败（不影响主流程）: {type(e).__name__}: {e}")

            # 5.6 更新长期记忆（L1 ConsolidatedMemory）
            try:
                for entity in entities:
                    entity_type = getattr(entity, 'entity_type', None)
                    if entity_type is None and hasattr(entity, 'get'):
                        entity_type = entity.get('entity_type', 'UNKNOWN')
                    if entity_type is None:
                        entity_type = 'UNKNOWN'

                    confidence = getattr(entity, 'confidence', None)
                    if confidence is None and hasattr(entity, 'get'):
                        confidence = entity.get('confidence', 0.5)
                    if confidence is None:
                        confidence = 0.5

                    aliases = getattr(entity, 'aliases', None)
                    if aliases is None and hasattr(entity, 'get'):
                        aliases = entity.get('aliases', [])
                    if aliases is None:
                        aliases = []

                    consolidated_entity = ConsolidatedEntity(
                        id=f"entity_{entity.name.lower().replace(' ', '_')}",
                        name=entity.name,
                        aliases=aliases,
                        entity_type=entity_type,
                        confidence=confidence,
                        source_turns=[memory_id],
                        source_memory_ids=[memory_id],
                        last_verified=time.strftime('%Y-%m-%dT%H:%M:%S')
                    )
                    engine.consolidated_memory.add_or_update(consolidated_entity)
                # v7.0.13: 批量 add_or_update 后统一刷盘
                engine.consolidated_memory.flush()
            except Exception as e:
                _safe_print(f"[Recall] 长期记忆更新失败（不影响主流程）: {e}")

            # 6. 更新知识图谱
            kg_task = task_manager.create_task(
                task_type=TaskType.KNOWLEDGE_GRAPH,
                name="知识图谱更新",
                user_id=user_id,
                character_id=character_id,
                parent_task_id=parent_task.id
            )
            task_manager.start_task(kg_task.id, "提取关系并更新图谱...")

            try:
                if unified_analysis_result is not None:
                    if unified_analysis_result.relations:
                        _safe_print(f"[Recall][v4.2] 使用统一分析器的关系结果, 关系数={len(unified_analysis_result.relations)}")
                        task_manager.update_task(kg_task.id, progress=0.5, message=f"存储 {len(unified_analysis_result.relations)} 条关系...")
                        for rel in unified_analysis_result.relations:
                            engine.knowledge_graph.add_relation(
                                source_id=rel.get('source'),
                                target_id=rel.get('target'),
                                relation_type=rel.get('relation_type'),
                                source_text=content[:200],
                                confidence=rel.get('confidence', 0.8),
                                valid_at=rel.get('valid_at'),
                                invalid_at=rel.get('invalid_at'),
                                fact=rel.get('fact', '')
                            )
                        relations = [(rel.get('source'), rel.get('relation_type'), rel.get('target'), content[:200])
                                     for rel in unified_analysis_result.relations]
                        _safe_print(f"[Recall][v4.2] 关系已存储到知识图谱, 总关系数={sum(len(v) for v in engine.knowledge_graph.outgoing.values())}")
                        task_manager.complete_task(kg_task.id, f"复用统一分析结果 {len(unified_analysis_result.relations)} 条关系", {'relations': len(unified_analysis_result.relations), 'mode': 'unified'})
                    else:
                        _safe_print(f"[Recall][v4.2] 统一分析器未提取到关系")
                        relations = []
                        task_manager.complete_task(kg_task.id, "统一分析器未发现关系", {'relations': 0, 'mode': 'unified'})
                elif engine._llm_relation_extractor:
                    task_manager.update_task(kg_task.id, progress=0.3, message="LLM 关系提取中...")
                    _safe_print(f"[Recall][关系] 使用 LLM 关系提取器, 实体数={len(entities)}")
                    relations_v2 = engine._llm_relation_extractor.extract(content, 0, entities)
                    _safe_print(f"[Recall][关系] LLM 提取完成, 关系数={len(relations_v2)}")
                    task_manager.update_task(kg_task.id, progress=0.7, message=f"存储 {len(relations_v2)} 条关系...")
                    for rel in relations_v2:
                        engine.knowledge_graph.add_relation(
                            source_id=rel.source_id,
                            target_id=rel.target_id,
                            relation_type=rel.relation_type,
                            source_text=rel.source_text,
                            confidence=rel.confidence,
                            valid_at=getattr(rel, 'valid_at', None),
                            invalid_at=getattr(rel, 'invalid_at', None),
                            fact=getattr(rel, 'fact', '')
                        )
                    relations = [rel.to_legacy_tuple() for rel in relations_v2]
                    _safe_print(f"[Recall][关系] 已存储到知识图谱, 总关系数={sum(len(v) for v in engine.knowledge_graph.outgoing.values())}")
                    task_manager.complete_task(kg_task.id, f"提取 {len(relations_v2)} 条关系", {'relations': len(relations_v2), 'mode': 'llm'})
                else:
                    task_manager.update_task(kg_task.id, progress=0.3, message="规则关系提取中...")
                    _safe_print(f"[Recall][关系] 使用规则提取器, 实体数={len(entities)}")
                    relations = engine.relation_extractor.extract(content, 0, entities=entities)
                    _safe_print(f"[Recall][关系] 规则提取完成, 关系数={len(relations)}")
                    task_manager.update_task(kg_task.id, progress=0.7, message=f"存储 {len(relations)} 条关系...")
                    for rel in relations:
                        source_id, relation_type, target_id, source_text = rel
                        engine.knowledge_graph.add_relation(
                            source_id=source_id,
                            target_id=target_id,
                            relation_type=relation_type,
                            source_text=source_text
                        )
                    _safe_print(f"[Recall][关系] 已存储到知识图谱, 总关系数={sum(len(v) for v in engine.knowledge_graph.outgoing.values())}")
                    task_manager.complete_task(kg_task.id, f"提取 {len(relations)} 条关系", {'relations': len(relations), 'mode': 'rule'})
            except Exception as e:
                import traceback
                _safe_print(f"[Recall] 知识图谱更新失败（不影响主流程）: {e}")
                traceback.print_exc()
                relations = []
                task_manager.fail_task(kg_task.id, str(e))

            # 6.5 更新全文索引 BM25
            if engine.fulltext_index is not None:
                try:
                    engine.fulltext_index.add(memory_id, content)
                except Exception as e:
                    _safe_print(f"[Recall] 全文索引更新失败（不影响主流程）: {e}")

            # 6.6 时态图谱更新 - 已整合到统一图谱中

            # 6.7 v7.0: 事件关联 — 自动将新事件关联到已有事件
            if getattr(engine, '_event_linker', None):
                try:
                    event_links = engine._event_linker.link(
                        memory_id=memory_id,
                        content=content,
                        entities=entity_names,
                        engine=engine,
                        user_id=user_id,
                    )
                    if event_links:
                        _safe_print(f"[Recall v7.0] EventLinker 建立 {len(event_links)} 条事件关联")
                except Exception as e:
                    _safe_print(f"[Recall v7.0] EventLinker 关联失败: {e}")

            # 6.8 v7.0: 主题聚类 — 提取主题标签并存储
            if getattr(engine, '_topic_cluster', None):
                try:
                    topics = engine._topic_cluster.extract_topics(
                        content=content,
                        entities=entity_names,
                    )
                    if topics:
                        # 为记忆附加主题标签
                        if metadata is None:
                            metadata = {}
                        metadata['topics'] = topics
                        _safe_print(f"[Recall v7.0] TopicCluster 提取主题: {topics[:5]}")
                        # v7.0.5: 修复 — 使用 link_by_topics() 存入 TopicStore + 图谱边
                        edge_count = engine._topic_cluster.link_by_topics(
                            memory_id=memory_id,
                            topics=topics[:5],
                            engine=engine,
                            user_id=user_id if user_id else "default",
                        )
                        if edge_count:
                            _safe_print(f"[Recall v7.0] TopicCluster 创建 {edge_count} 条主题关联边")
                except Exception as e:
                    _safe_print(f"[Recall v7.0] TopicCluster 提取失败: {e}")

            # 7. 自动提取持久条件（已移至 server.py 中处理）

            # === Recall 4.1: 更新 Episode 关联 ===
            if current_episode and engine.episode_store:
                try:
                    entity_ids = []
                    for e in entities:
                        if hasattr(e, 'id') and e.id:
                            entity_ids.append(e.id)
                        elif hasattr(e, 'name'):
                            entity_ids.append(f"entity_{e.name.lower().replace(' ', '_')}")

                    relation_ids = []
                    if relations:
                        for i, rel in enumerate(relations):
                            if isinstance(rel, tuple) and len(rel) >= 3:
                                source_id, relation_type, target_id = rel[:3]
                                relation_ids.append(f"rel_{source_id}_{relation_type}_{target_id}")

                    engine.episode_store.update_links(
                        episode_uuid=current_episode.uuid,
                        memory_ids=[memory_id] if memory_id else [],
                        entity_ids=entity_ids,
                        relation_ids=relation_ids
                    )
                    _safe_print(f"[Recall] Episode 关联已更新: memories={len([memory_id])}, entities={len(entity_ids)}, relations={len(relation_ids)}")
                except Exception as e:
                    _safe_print(f"[Recall] Episode 关联更新失败（不影响主流程）: {e}")

            # === Recall 4.1: 更新实体摘要 ===
            if engine._entity_summary_enabled and engine.entity_summarizer:
                try:
                    for entity in entities:
                        entity_name = entity.name if hasattr(entity, 'name') else str(entity)
                        engine._maybe_update_entity_summary(entity_name)
                except Exception as e:
                    _safe_print(f"[Recall] 实体摘要更新失败（不影响主流程）: {e}")

            # 记录性能
            try:
                engine.monitor.record(
                    MetricType.LATENCY,
                    (time.time() - start_time) * 1000
                )
            except Exception:
                pass

            elapsed_ms = (time.time() - start_time) * 1000
            task_manager.complete_task(
                parent_task.id,
                f"记忆保存完成 ({elapsed_ms:.0f}ms)",
                {'memory_id': memory_id, 'entities': entity_names, 'elapsed_ms': elapsed_ms}
            )

            _safe_print(f"[Engine][Add] [OK] 保存成功: id={memory_id}, 耗时={elapsed_ms:.1f}ms")
            _safe_print(f"[Engine][Add]    entities={entity_names}, warnings={len(consistency_warnings)}")

            return AddResult(
                id=memory_id,
                success=True,
                entities=entity_names,
                message="记忆添加成功",
                consistency_warnings=consistency_warnings
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            _safe_print(f"[Engine][Add] [FAIL] 添加异常: {type(e).__name__}: {e}, 耗时={elapsed_ms:.1f}ms")
            import traceback
            traceback.print_exc()
            task_manager.fail_task(parent_task.id, str(e))
            return AddResult(
                id="",
                success=False,
                message=f"添加失败: {str(e)}"
            )

    # ==================== add_batch ====================

    def add_batch(
        self,
        items: List[Dict[str, Any]],
        user_id: str = "default",
        skip_dedup: bool = False,
        skip_llm: bool = True,
    ) -> List[str]:
        """批量添加记忆（高吞吐）"""
        import logging

        engine = self._engine
        memory_ids = []

        if not engine.embedding_backend:
            raise RuntimeError("Embedding backend 未初始化（需启用 VECTOR_INDEX），无法执行批量添加")

        # 1. 批量计算 embedding
        contents = [item['content'] for item in items]
        embeddings = engine.embedding_backend.encode_batch(contents)

        # 2. 逐条处理但合并 IO
        all_keywords = []
        all_entities = []
        all_ngram_data = []
        all_relations = []

        errors = []
        for i, (item, embedding) in enumerate(zip(items, embeddings)):
            merged_metadata = {
                **(item.get('metadata', {})),
                'source': item.get('source', ''),
                'tags': item.get('tags', []),
                'category': item.get('category', ''),
                'content_type': item.get('content_type', 'custom'),
            }
            try:
                result = self._add_single_fast(
                    content=item['content'],
                    embedding=embedding,
                    metadata=merged_metadata,
                    user_id=user_id,
                    skip_dedup=skip_dedup,
                    skip_llm=skip_llm,
                )
                if result:
                    memory_id, entities, keywords, relations = result
                    memory_ids.append(memory_id)
                    # v7.0.10: 传递完整实体信息（entity_type, aliases, confidence）以便 _batch_update_indexes 正确写入
                    all_entities.extend([(e, memory_id) for e in entities])
                    all_keywords.extend([(kw, memory_id) for kw in keywords])
                    all_ngram_data.append((memory_id, item['content']))
                    all_relations.extend(relations)
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
                logging.warning(f"add_batch item {i} failed: {e}")

        # 3. 批量更新索引
        self._batch_update_indexes(all_keywords, all_entities, all_ngram_data, all_relations)

        # 4. 补全缺失步骤（与 add() 对齐）

        # 4a. Episode 创建
        if engine._episode_tracking_enabled and engine.episode_store:
            try:
                from .models.temporal import EpisodicNode, EpisodeType
                batch_episode = EpisodicNode(
                    source_type=EpisodeType.MESSAGE,
                    content=f"Batch import: {len(memory_ids)} memories",
                    user_id=user_id,
                    source_description=f"batch_add: {len(items)} items",
                )
                engine.episode_store.save(batch_episode)
                # Link all memories to this episode
                if memory_ids:
                    engine.episode_store.update_links(
                        episode_uuid=batch_episode.uuid,
                        memory_ids=memory_ids,
                        entity_ids=[],
                        relation_ids=[]
                    )
            except Exception as e:
                logging.warning(f"add_batch episode creation failed: {e}")

        # v7.0.8: 预构建 memory_id → entities/keywords 映射（供 4b/4c 共用）
        mid_entities_map = {}
        mid_keywords_map = {}
        for ent_name, mid in all_entities:
            mid_entities_map.setdefault(mid, []).append(ent_name)
        for kw, mid in all_keywords:
            mid_keywords_map.setdefault(mid, []).append(kw)

        # 4b. Archive 保存 (VolumeManager)
        # v7.0.6: 使用 all_entities/all_keywords 中的实际数据（之前硬编码空列表）
        if engine.volume_manager:
            try:
                for mid, item in zip(memory_ids, items[:len(memory_ids)]):
                    engine.volume_manager.append_turn({
                        'memory_id': mid,
                        'user_id': user_id,
                        'content': item['content'],
                        'entities': mid_entities_map.get(mid, []),
                        'keywords': mid_keywords_map.get(mid, []),
                        'metadata': item.get('metadata', {}),
                        'created_at': time.time()
                    })
            except Exception as e:
                logging.warning(f"add_batch archive save failed: {e}")

        # 4c. 事件关联 (EventLinker)
        if hasattr(engine, '_event_linker') and engine._event_linker:
            try:
                if hasattr(engine._event_linker, 'link_batch'):
                    # link_batch 需要 items=[{memory_id, content, entities}], engine, user_id
                    batch_items = []
                    for mid in memory_ids:
                        content = engine._get_memory_content_by_id(mid) if hasattr(engine, '_get_memory_content_by_id') else ''
                        # v7.0.8: 复用 mid_entities_map 中的实体数据（之前传空列表，降低事件关联质量）
                        mid_ents = mid_entities_map.get(mid, [])
                        batch_items.append({'memory_id': mid, 'content': content or '', 'entities': mid_ents})
                    if batch_items:
                        engine._event_linker.link_batch(batch_items, engine=engine, user_id=user_id)
                else:
                    # v7.0.4: 修复 — 之前只传 1 个参数，link() 需要 5 个
                    for mid in memory_ids:
                        try:
                            mid_content = engine._get_memory_content_by_id(mid) if hasattr(engine, '_get_memory_content_by_id') else ''
                            mid_ents = mid_entities_map.get(mid, [])
                            engine._event_linker.link(
                                memory_id=mid,
                                content=mid_content or '',
                                entities=mid_ents,
                                engine=engine,
                                user_id=user_id,
                            )
                        except Exception:
                            pass
            except Exception as e:
                logging.warning(f"add_batch event linking failed: {e}")

        # 4d. 主题聚类 (TopicCluster)
        # v7.0.5: 修复 — 使用 link_by_topics() 存入 TopicStore + 图谱边
        if hasattr(engine, '_topic_cluster') and engine._topic_cluster:
            try:
                for mid, item in zip(memory_ids, items[:len(memory_ids)]):
                    try:
                        # v7.0.9: 使用提取的实体而非 metadata 中的（批量导入通常无 metadata.entities）
                        item_entities = mid_entities_map.get(mid, [])
                        topics = engine._topic_cluster.extract_topics(
                            content=item['content'],
                            entities=item_entities,
                        )
                        if topics:
                            engine._topic_cluster.link_by_topics(
                                memory_id=mid,
                                topics=topics[:5],
                                engine=engine,
                                user_id=user_id if user_id else "default",
                            )
                    except Exception:
                        pass
            except Exception as e:
                logging.warning(f"add_batch topic clustering failed: {e}")

        # 4e. 检索器缓存预填
        if engine.retriever:
            try:
                for mid, item in zip(memory_ids, items[:len(memory_ids)]):
                    engine.retriever.cache_content(mid, item['content'])
                    # v7.0.2: 也缓存 metadata 和 entities（之前遗漏）
                    if hasattr(engine.retriever, 'cache_metadata') and item.get('metadata'):
                        engine.retriever.cache_metadata(mid, item.get('metadata', {}))
                    if hasattr(engine.retriever, 'cache_entities'):
                        entity_names = item.get('metadata', {}).get('entities', []) if item.get('metadata') else []
                        if entity_names:
                            engine.retriever.cache_entities(mid, entity_names)
            except Exception as e:
                logging.warning(f"add_batch retriever cache failed: {e}")

        # 4f. 实体摘要更新（v7.0.4: 修复 — 之前调用不存在的 maybe_update()，改为 _maybe_update_entity_summary()）
        if hasattr(engine, '_maybe_update_entity_summary'):
            try:
                # 收集本批次涉及的所有实体名
                batch_entity_names = set()
                for ent_name, _ in all_entities:
                    batch_entity_names.add(ent_name)
                # 只更新出现频率高的实体（避免批量导入时大量 LLM 调用）
                if batch_entity_names and len(batch_entity_names) <= 50:
                    for ent_name in batch_entity_names:
                        try:
                            engine._maybe_update_entity_summary(ent_name)
                        except Exception:
                            pass
            except Exception as e:
                logging.warning(f"add_batch entity summary update failed: {e}")

        # 注意: 一致性/矛盾检测在批量模式下跳过以保证吞吐量

        if errors:
            logging.warning(f"add_batch: {len(errors)}/{len(items)} 条失败")
        return memory_ids

    # ==================== _add_single_fast ====================

    def _add_single_fast(self, content, embedding, metadata, user_id, skip_dedup, skip_llm):
        """单条快速添加（add_batch 内部使用）"""
        engine = self._engine
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"

        # 去重检查
        if not skip_dedup:
            scope = engine.storage.get_scope(user_id)
            existing_memories, _ = engine.get_paginated(user_id=user_id, offset=0, limit=100)
            for mem in existing_memories:
                if content.strip() == mem.get('content', '').strip():
                    return None

        # 实体提取（v7.0.1: 添加 fallback 到规则提取器）
        extraction_result = None
        entities = []
        keywords = []
        if engine.smart_extractor:
            try:
                if skip_llm:
                    from recall.processor.smart_extractor import ExtractionMode
                    extraction_result = engine.smart_extractor.extract(content, force_mode=ExtractionMode.RULES)
                else:
                    extraction_result = engine.smart_extractor.extract(content)
                entities = extraction_result.entities if extraction_result else []
                keywords = extraction_result.keywords if extraction_result else []
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast SmartExtractor 失败，回退到规则提取器: {e}")
                extraction_result = None
        if not extraction_result and engine.entity_extractor:
            try:
                entities = engine.entity_extractor.extract(content)
                # v7.0.2: 规则 fallback 时也要提取关键词（之前遗漏导致倒排索引空命中）
                if hasattr(engine.entity_extractor, 'extract_keywords'):
                    keywords = engine.entity_extractor.extract_keywords(content)
                else:
                    keywords = []
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast 规则提取器也失败: {e}")
                entities = []

        # v7.0.3: Entity Resolution（实体消歧，与 add() 对齐 — 之前 add_batch 缺失）
        if entities and hasattr(engine, '_entity_resolver') and engine._entity_resolver:
            try:
                for ent in entities:
                    if hasattr(ent, 'name'):
                        resolved_name = engine._entity_resolver.resolve(ent.name)
                        if resolved_name != ent.name:
                            ent.name = resolved_name
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast EntityResolver 失败（不影响主流程）: {e}")

        # 时间意图解析（v7.0.4: 修复 — parse() 返回 Optional[TimeRange]，不是 dict）
        if hasattr(engine, '_time_intent_parser') and engine._time_intent_parser:
            try:
                time_result = engine._time_intent_parser.parse(content)
                if time_result:
                    if metadata is None:
                        metadata = {}
                    if hasattr(time_result, 'start') and time_result.start:
                        metadata['event_time'] = time_result.start.isoformat()
                    if hasattr(time_result, 'label') and time_result.label:
                        metadata['temporal_label'] = time_result.label
            except Exception:
                pass

        character_id = metadata.get('character_id', 'default') if metadata else 'default'

        # 存储记忆
        scope = engine.storage.get_scope(user_id)
        scope.add(content, metadata={
            'id': memory_id,
            'entities': [e.name for e in entities] if entities and hasattr(entities[0], 'name') else [str(e) for e in entities],
            'keywords': keywords,
            **(metadata or {})
        })

        entity_names = [e.name for e in entities] if entities and hasattr(entities[0], 'name') else [str(e) for e in entities]

        # 更新向量索引
        # v7.0.11: 向量索引隔离 try/except（与 add()/add_turn() 对齐）
        try:
            if engine._vector_index and engine._vector_index.enabled:
                engine._vector_index.add(memory_id, embedding)
        except Exception as e:
            import logging
            logging.warning(f"_add_single_fast vector index failed: {e}")

        # v7.0.2: 同步写入 IVF 索引（如果已激活）
        if getattr(engine, '_vector_index_ivf', None) is not None:
            try:
                vec = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
                engine._vector_index_ivf.add(memory_id, vec)
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast IVF 写入失败: {e}")

        # v7.0.11: 元数据索引隔离 try/except（与 add()/add_turn() 对齐）
        try:
            if engine._metadata_index:
                engine._metadata_index.add(
                    memory_id=memory_id,
                    source=metadata.get('source', '') if metadata else '',
                    tags=metadata.get('tags', []) if metadata else [],
                    category=metadata.get('category', '') if metadata else '',
                    content_type=metadata.get('content_type', '') if metadata else '',
                    event_time=metadata.get('event_time', '') if metadata else '',
                )
        except Exception as e:
            import logging
            logging.warning(f"_add_single_fast metadata index failed: {e}")

        # 全文索引由 _batch_update_indexes() 批量处理，此处不再重复写入
        # (Fix: 修复双写 bug — _add_single_fast 和 _batch_update_indexes 均写入全文索引)

        # 更新 ConsolidatedMemory (L1)（v7.0.1: 之前缺失）
        if engine.consolidated_memory is not None:
            try:
                from .storage.layer1_consolidated import ConsolidatedEntity
                for ename in entity_names:
                    ce = ConsolidatedEntity(
                        id=f"entity_{ename.lower().replace(' ', '_')}",
                        name=ename,
                        entity_type="UNKNOWN",
                        current_state={"last_content": content[:200]},
                        confidence=0.5,
                        verification_count=1,
                        source_memory_ids=[memory_id],
                    )
                    engine.consolidated_memory.add_or_update(ce)
                # v7.0.13: 批量 add_or_update 后统一刷盘
                engine.consolidated_memory.flush()
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast consolidated memory update failed: {e}")

        # 更新时态索引
        if metadata and metadata.get('event_time') and engine.temporal_graph and hasattr(engine.temporal_graph, '_temporal_index'):
            try:
                from .index.temporal_index import TemporalEntry, TimeRange
                from datetime import datetime as _dt
                event_time_str = metadata['event_time']
                event_dt = None
                for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%f'):
                    try:
                        event_dt = _dt.strptime(event_time_str, fmt)
                        break
                    except ValueError:
                        continue
                if event_dt:
                    now = _dt.now()
                    entry = TemporalEntry(
                        doc_id=memory_id,
                        fact_range=TimeRange(start=event_dt),
                        known_at=now,
                        system_range=TimeRange(start=now),
                        subject=user_id,
                        predicate='memory'
                    )
                    engine.temporal_graph._temporal_index.add(entry)
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast temporal index update failed: {e}")

        # v7.0.1: BAL 双写（之前缺失）
        role = metadata.get('role', 'unknown') if metadata else 'unknown'
        if getattr(engine, '_storage_backend', None):
            try:
                engine._storage_backend.save(memory_id, {
                    'content': content,
                    'metadata': metadata or {},
                    'namespace': character_id,
                    'source': role,
                    'user_id': user_id,
                    'importance': metadata.get('importance', 0.5) if metadata else 0.5,
                })
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast StorageBackend dual-write failed: {e}")

        if getattr(engine, '_vector_backend', None) and embedding is not None:
            try:
                vec = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
                engine._vector_backend.add(
                    memory_id, vec,
                    {'content': content[:200], 'user_id': user_id, 'namespace': character_id}
                )
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast VectorBackend dual-write failed: {e}")

        if getattr(engine, '_text_search_backend', None):
            try:
                engine._text_search_backend.add(
                    memory_id, content,
                    {'user_id': user_id, 'entities': entity_names, 'namespace': character_id}
                )
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast TextSearchBackend dual-write failed: {e}")

        # 规则级关系提取
        relations = []
        if engine.relation_extractor and entities:
            try:
                relations = engine.relation_extractor.extract(content, 0, entities=entities)
            except Exception as e:
                import logging
                logging.warning(f"_add_single_fast relation extraction failed: {e}")

        return (memory_id, entities, keywords, relations)

    # ==================== _batch_update_indexes ====================

    def _batch_update_indexes(self, all_keywords, all_entities, all_ngram_data, all_relations=None):
        """批量更新索引 — 合并 IO 操作（v7.0.11: 逐索引 try/except 隔离，与 add/add_turn 对齐）"""
        from collections import defaultdict

        engine = self._engine

        # 批量更新倒排索引
        try:
            if engine._inverted_index and all_keywords:
                kw_by_mid = defaultdict(list)
                for kw, mid in all_keywords:
                    kw_by_mid[mid].append(kw)
                for mid, kws in kw_by_mid.items():
                    engine._inverted_index.add_batch(kws, mid)
        except Exception as e:
            import logging
            logging.warning(f"_batch_update_indexes inverted index failed: {e}")

        # 批量更新实体索引（v7.0.10: 传递完整实体参数，与 add()/add_turn() 对齐）
        try:
            if engine._entity_index and all_entities:
                for entity_or_name, mid in all_entities:
                    # 兼容旧格式 (str, mid) 和新格式 (entity_obj, mid)
                    if isinstance(entity_or_name, str):
                        engine._entity_index.add_entity_occurrence(entity_or_name, mid)
                    else:
                        entity = entity_or_name
                        entity_name = entity.name if hasattr(entity, 'name') else str(entity)
                        entity_type = getattr(entity, 'entity_type', 'UNKNOWN')
                        aliases = getattr(entity, 'aliases', [])
                        confidence = getattr(entity, 'confidence', 0.5)
                        engine._entity_index.add_entity_occurrence(
                            entity_name=entity_name,
                            turn_id=mid,
                            context='',
                            entity_type=entity_type,
                            aliases=aliases,
                            confidence=confidence
                        )
        except Exception as e:
            import logging
            logging.warning(f"_batch_update_indexes entity index failed: {e}")

        # 批量更新 N-gram 索引
        try:
            if engine._ngram_index and all_ngram_data:
                for mid, content in all_ngram_data:
                    engine._ngram_index.add(mid, content)
                engine._ngram_index.save()
        except Exception as e:
            import logging
            logging.warning(f"_batch_update_indexes ngram index failed: {e}")

        # 批量更新知识图谱
        try:
            if engine.knowledge_graph and all_relations:
                for rel in all_relations:
                    try:
                        source_id, relation_type, target_id, source_text = rel
                        engine.knowledge_graph.add_relation(
                            source_id=source_id,
                            target_id=target_id,
                            relation_type=relation_type,
                            source_text=source_text,
                        )
                    except Exception as e:
                        import logging
                        logging.warning(f"batch KG relation update failed: {e}")
        except Exception as e:
            import logging
            logging.warning(f"_batch_update_indexes knowledge graph failed: {e}")

        # 批量更新全文索引 BM25
        try:
            if engine.fulltext_index is not None and all_ngram_data:
                for mid, content in all_ngram_data:
                    try:
                        engine.fulltext_index.add(mid, content)
                    except Exception as e:
                        import logging
                        logging.warning(f"batch fulltext index update failed: {e}")
        except Exception as e:
            import logging
            logging.warning(f"_batch_update_indexes fulltext index failed: {e}")

    # ==================== add_turn ====================

    def add_turn(
        self,
        user_message: str,
        ai_response: str,
        user_id: str = "default",
        character_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """添加对话轮次（v4.2 性能优化版）"""
        from .engine import AddTurnResult
        import uuid as uuid_module

        engine = self._engine
        start_time = time.time()
        consistency_warnings: List[str] = []
        all_entities: List[str] = []
        keywords: list = []
        entities: list = []
        relations: list = []

        # v5.0: 非 RP 模式下强制 character_id 为 default
        if not engine._mode.character_dimension_enabled:
            character_id = "default"

        msg_hash = f"{hash(user_message[:100]) % 10000:04d}_{hash(ai_response[:100]) % 10000:04d}"
        _safe_print(f"[Engine][Turn] 开始处理: user_id={user_id}, char={character_id}, hash={msg_hash}")
        _safe_print(f"[Engine][Turn]    用户消息长度={len(user_message)}, AI回复长度={len(ai_response)}")

        # 输入验证
        if not user_message or not user_message.strip():
            _safe_print(f"[Engine][Turn] [FAIL] 用户消息为空")
            return AddTurnResult(success=False, message="用户消息不能为空")
        if not ai_response or not ai_response.strip():
            _safe_print(f"[Engine][Turn] [FAIL] AI回复为空")
            return AddTurnResult(success=False, message="AI回复不能为空")

        combined_content = f"{user_message}\n\n{ai_response}"
        _safe_print(f"[Engine][Turn]    合并内容长度={len(combined_content)}")

        try:
            # 1. 预计算合并内容的 Embedding
            combined_embedding = None
            if engine._vector_index and engine._vector_index.enabled:
                try:
                    combined_embedding = engine._vector_index.encode(combined_content)
                    _safe_print(f"[Recall][Turn] Embedding 预计算完成: dim={len(combined_embedding)}")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] Embedding 计算失败: {e}")

            # 2. 分别检查用户消息和 AI 回复是否已存在
            scope = engine.storage.get_scope(user_id)
            existing_memories = scope.get_all(limit=100)

            user_message_normalized = user_message.strip()
            ai_response_normalized = ai_response.strip()
            user_exists = False
            ai_exists = False

            _safe_print(f"[Engine][Turn]    精确匹配检查: 对比 {len(existing_memories)} 条现有记忆...")
            for mem in existing_memories:
                existing_content = mem.get('content', '').strip()
                if existing_content == user_message_normalized:
                    user_exists = True
                    _safe_print(f"[Engine][Turn]    [DUP] 用户消息精确匹配: mem_id={mem.get('metadata', {}).get('id', 'unknown')}")
                if existing_content == ai_response_normalized:
                    ai_exists = True
                    _safe_print(f"[Engine][Turn]    [DUP] AI回复精确匹配: mem_id={mem.get('metadata', {}).get('id', 'unknown')}")
                if user_exists and ai_exists:
                    break

            if user_exists and ai_exists:
                _safe_print(f"[Engine][Turn] [SKIP] 精确匹配: 用户消息和AI回复都已存在")
                return AddTurnResult(success=False, message="对话轮次已存在（用户消息和AI回复都重复）")

            _safe_print(f"[Engine][Turn]    精确匹配结果: user_exists={user_exists}, ai_exists={ai_exists}")

            # 2.2 语义去重检查
            if engine.deduplicator is not None and existing_memories:
                _safe_print(f"[Engine][Turn]    语义去重检查: 启用三阶段去重器...")
                try:
                    from .processor.three_stage_deduplicator import DedupItem

                    user_item = DedupItem(
                        id=str(uuid_module.uuid4()),
                        name=user_message[:100],
                        content=user_message,
                        item_type="memory"
                    )
                    ai_item = DedupItem(
                        id=str(uuid_module.uuid4()),
                        name=ai_response[:100],
                        content=ai_response,
                        item_type="memory"
                    )

                    existing_items = []
                    for mem in existing_memories:
                        mem_content = mem.get('content', '').strip()
                        if mem_content:
                            existing_items.append(DedupItem(
                                id=mem.get('metadata', {}).get('id', str(uuid_module.uuid4())),
                                name=mem_content[:100],
                                content=mem_content,
                                item_type="memory"
                            ))

                    if existing_items:
                        user_dedup_result = engine.deduplicator.deduplicate([user_item], existing_items)
                        user_is_dup = len(user_dedup_result.matches) > 0

                        ai_dedup_result = engine.deduplicator.deduplicate([ai_item], existing_items)
                        ai_is_dup = len(ai_dedup_result.matches) > 0

                        _safe_print(f"[Engine][Turn]    语义去重结果: user_dup={user_is_dup}, ai_dup={ai_is_dup}")

                        if user_is_dup and ai_is_dup:
                            user_match_type = user_dedup_result.matches[0].match_type.value
                            user_conf = user_dedup_result.matches[0].confidence
                            ai_match_type = ai_dedup_result.matches[0].match_type.value
                            ai_conf = ai_dedup_result.matches[0].confidence
                            _safe_print(f"[Engine][Turn] [SKIP] 语义去重: 用户消息({user_match_type},{user_conf:.2f}) + AI回复({ai_match_type},{ai_conf:.2f})")
                            return AddTurnResult(
                                success=False,
                                message=f"对话轮次已存在（用户消息:{user_match_type}, AI回复:{ai_match_type}）"
                            )
                except Exception as e:
                    _safe_print(f"[Engine][Turn] [WARN] 去重检查失败，继续处理: {e}")
            else:
                _safe_print(f"[Engine][Turn]    跳过语义去重: deduplicator={engine.deduplicator is not None}, existing={len(existing_memories) if existing_memories else 0}")

            # === Recall 4.1: Episode 创建 ===
            current_episode = None
            if engine._episode_tracking_enabled and engine.episode_store:
                try:
                    from .models.temporal import EpisodicNode, EpisodeType
                    current_episode = EpisodicNode(
                        source_type=EpisodeType.MESSAGE,
                        content=combined_content,
                        user_id=user_id,
                        character_id=character_id,
                        source_description=f"Turn: {user_id}",
                    )
                    engine.episode_store.save(current_episode)
                    _safe_print(f"[Recall][Turn] Episode 已创建: {current_episode.uuid}")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] Episode 创建失败（不影响主流程）: {e}")
                    current_episode = None

            # 2.5. 时间意图解析（v7.0.4: 修复 — parse() 返回 Optional[TimeRange]，不是 dict）
            if hasattr(engine, '_time_intent_parser') and engine._time_intent_parser:
                try:
                    time_result = engine._time_intent_parser.parse(combined_content)
                    if time_result:
                        if metadata is None:
                            metadata = {}
                        if hasattr(time_result, 'start') and time_result.start:
                            metadata['event_time'] = time_result.start.isoformat()
                        if hasattr(time_result, 'label') and time_result.label:
                            metadata['temporal_label'] = time_result.label
                        _safe_print(f"[Recall][Turn] 时间意图解析: event_time={metadata.get('event_time')}")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] 时间意图解析失败（不影响主流程）: {e}")

            # 3. 实体提取
            entity_start = time.time()
            if engine.smart_extractor is not None:
                try:
                    _safe_print(f"[Engine][Turn]    实体提取: 使用 SmartExtractor...")
                    extraction_result = engine.smart_extractor.extract(combined_content)
                    entities = extraction_result.entities
                    all_entities = [e.name for e in entities]
                    keywords = extraction_result.keywords
                    _safe_print(f"[Engine][Turn]    实体提取完成: {len(entities)}个实体, {len(keywords)}个关键词, 耗时{(time.time()-entity_start)*1000:.1f}ms")
                except Exception as e:
                    _safe_print(f"[Engine][Turn] [WARN] SmartExtractor 失败，回退: {e}")
                    entities = engine.entity_extractor.extract(combined_content)
                    all_entities = [e.name for e in entities]
                    keywords = engine.entity_extractor.extract_keywords(combined_content)
            else:
                _safe_print(f"[Engine][Turn]    实体提取: 使用基础提取器...")
                entities = engine.entity_extractor.extract(combined_content)
                all_entities = [e.name for e in entities]
                keywords = engine.entity_extractor.extract_keywords(combined_content)
                _safe_print(f"[Engine][Turn]    实体提取完成: {len(entities)}个实体, {len(keywords)}个关键词")

            # 3.5 v7.0.5: 实体消歧 (EntityResolver) — 原地修改实体对象的 .name
            if entities and hasattr(engine, '_entity_resolver') and engine._entity_resolver:
                try:
                    for ent in entities:
                        if hasattr(ent, 'name'):
                            resolved_name = engine._entity_resolver.resolve(ent.name)
                            if resolved_name != ent.name:
                                ent.name = resolved_name
                    all_entities = [e.name for e in entities]  # 重建字符串列表
                    _safe_print(f"[Recall][Turn] EntityResolver 消歧完成: {len(set(all_entities))} 个唯一实体")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] EntityResolver 失败（不影响主流程）: {e}")

            # 4. 统一 LLM 分析
            use_unified_analyzer_turn = False
            if engine.unified_analyzer:
                from .graph import DetectionStrategy
                if engine.contradiction_manager is None:
                    use_unified_analyzer_turn = True
                elif engine.contradiction_manager.strategy != DetectionStrategy.RULE:
                    use_unified_analyzer_turn = True
                else:
                    _safe_print(f"[Recall][Turn] 矛盾检测策略为 RULE，跳过统一分析器")

            if use_unified_analyzer_turn:
                _safe_print(f"[Engine][Turn]    统一分析器: 开始 LLM 分析（矛盾+关系）...")
                analysis_start = time.time()
                try:
                    from .processor.unified_analyzer import UnifiedAnalysisInput, AnalysisTask
                    existing_mems_for_check = engine.search(combined_content, user_id=user_id, top_k=5)
                    _safe_print(f"[Engine][Turn]    统一分析器: 找到 {len(existing_mems_for_check)} 条相关记忆用于对比")

                    analysis_result = engine.unified_analyzer.analyze(UnifiedAnalysisInput(
                        content=combined_content,
                        entities=all_entities,
                        existing_memories=[m.content for m in existing_mems_for_check],
                        tasks=[AnalysisTask.CONTRADICTION, AnalysisTask.RELATION],
                        user_id=user_id,
                        character_id=character_id
                    ))

                    if analysis_result.success:
                        analysis_time = (time.time() - analysis_start) * 1000
                        _safe_print(f"[Engine][Turn]    统一分析器完成: 耗时{analysis_time:.1f}ms, 矛盾={len(analysis_result.contradictions)}, 关系={len(analysis_result.relations)}")
                        for c in analysis_result.contradictions:
                            warning_msg = f"{c.get('old_fact', '')} vs {c.get('new_fact', '')}"
                            consistency_warnings.append(warning_msg)

                            if engine.contradiction_manager is not None:
                                try:
                                    from .models.temporal import TemporalFact, Contradiction, ContradictionType
                                    from datetime import datetime

                                    contradiction_type = ContradictionType.DIRECT
                                    if c.get('type', '').lower() in ['temporal', 'timeline', '时态矛盾']:
                                        contradiction_type = ContradictionType.TEMPORAL
                                    elif c.get('type', '').lower() in ['logical', '逻辑矛盾']:
                                        contradiction_type = ContradictionType.LOGICAL

                                    new_fact = TemporalFact(
                                        uuid=str(uuid_module.uuid4()),
                                        fact=c.get('new_fact', '')[:200],
                                        source_text=c.get('new_fact', '')[:200],
                                        user_id=user_id
                                    )
                                    old_fact = TemporalFact(
                                        uuid=str(uuid_module.uuid4()),
                                        fact=c.get('old_fact', '')[:200],
                                        source_text=c.get('old_fact', '')[:200],
                                        user_id=user_id
                                    )

                                    contradiction = Contradiction(
                                        uuid=str(uuid_module.uuid4()),
                                        old_fact=old_fact,
                                        new_fact=new_fact,
                                        contradiction_type=contradiction_type,
                                        confidence=c.get('confidence', 0.8),
                                        detected_at=datetime.now(),
                                        notes=warning_msg[:200]
                                    )
                                    engine.contradiction_manager.add_pending(contradiction)
                                    _safe_print(f"[Recall][Turn] 矛盾已记录: {warning_msg[:50]}...")
                                except Exception as e:
                                    _safe_print(f"[Recall][Turn] 矛盾记录失败（不影响主流程）: {e}")

                        relations = analysis_result.relations
                        if engine.knowledge_graph and relations:
                            for rel in relations:
                                engine.knowledge_graph.add_relation(
                                    source_id=rel.get('source'),
                                    target_id=rel.get('target'),
                                    relation_type=rel.get('relation_type'),
                                    source_text=combined_content[:200],
                                    confidence=rel.get('confidence', 0.8),
                                    fact=rel.get('fact', '')
                                )
                except Exception as e:
                    analysis_time = (time.time() - analysis_start) * 1000
                    _safe_print(f"[Engine][Turn] [WARN] 统一分析失败(耗时{analysis_time:.1f}ms): {e}")
                    if engine.knowledge_graph and entities:
                        try:
                            if engine._llm_relation_extractor:
                                _safe_print(f"[Recall][Turn] 回退到 LLM 关系提取器")
                                relations_v2 = engine._llm_relation_extractor.extract(combined_content, 0, entities)
                                relations = [rel.to_legacy_tuple() for rel in relations_v2]
                                for rel in relations_v2:
                                    engine.knowledge_graph.add_relation(
                                        source_id=rel.source_id,
                                        target_id=rel.target_id,
                                        relation_type=rel.relation_type,
                                        source_text=rel.source_text,
                                        confidence=rel.confidence,
                                        valid_at=getattr(rel, 'valid_at', None),
                                        invalid_at=getattr(rel, 'invalid_at', None),
                                        fact=getattr(rel, 'fact', '')
                                    )
                            else:
                                _safe_print(f"[Recall][Turn] 回退到规则关系提取器")
                                relations = engine.relation_extractor.extract(combined_content, 0, entities=entities)
                                for rel in relations:
                                    source_id, relation_type, target_id, source_text = rel
                                    engine.knowledge_graph.add_relation(
                                        source_id=source_id,
                                        target_id=target_id,
                                        relation_type=relation_type,
                                        source_text=source_text
                                    )
                        except Exception as fallback_err:
                            _safe_print(f"[Recall][Turn] 回退关系提取也失败: {fallback_err}")

            if not use_unified_analyzer_turn:
                if engine.knowledge_graph and entities:
                    try:
                        if engine._llm_relation_extractor:
                            _safe_print(f"[Recall][Turn] 使用 LLM 关系提取器（无统一分析器）")
                            relations_v2 = engine._llm_relation_extractor.extract(combined_content, 0, entities)
                            relations = [rel.to_legacy_tuple() for rel in relations_v2]
                            for rel in relations_v2:
                                engine.knowledge_graph.add_relation(
                                    source_id=rel.source_id,
                                    target_id=rel.target_id,
                                    relation_type=rel.relation_type,
                                    source_text=rel.source_text,
                                    confidence=rel.confidence,
                                    valid_at=getattr(rel, 'valid_at', None),
                                    invalid_at=getattr(rel, 'invalid_at', None),
                                    fact=getattr(rel, 'fact', '')
                                )
                        else:
                            _safe_print(f"[Recall][Turn] 使用规则关系提取器（无统一分析器）")
                            relations = engine.relation_extractor.extract(combined_content, 0, entities=entities)
                            for rel in relations:
                                source_id, relation_type, target_id, source_text = rel
                                engine.knowledge_graph.add_relation(
                                    source_id=source_id,
                                    target_id=target_id,
                                    relation_type=relation_type,
                                    source_text=source_text
                                )
                    except Exception as e:
                        _safe_print(f"[Recall][Turn] 关系提取失败（无统一分析器）: {e}")

                # 一致性检查回退
                try:
                    existing_mems_for_check = engine.search(combined_content, user_id=user_id, top_k=5)
                    if existing_mems_for_check:
                        consistency = engine.consistency_checker.check(
                            combined_content,
                            [{'content': m.content} for m in existing_mems_for_check]
                        )
                        if not consistency.is_consistent:
                            for v in consistency.violations:
                                warning_msg = v.description
                                consistency_warnings.append(warning_msg)
                                _safe_print(f"[Recall][Turn] 一致性警告: {warning_msg}")

                            if engine.contradiction_manager is not None:
                                try:
                                    from .models.temporal import TemporalFact, Contradiction, ContradictionType
                                    from datetime import datetime

                                    for v in consistency.violations:
                                        contradiction_type = ContradictionType.DIRECT
                                        type_str = v.type.value if hasattr(v.type, 'value') else str(v.type)
                                        if 'timeline' in type_str.lower() or 'temporal' in type_str.lower():
                                            contradiction_type = ContradictionType.TEMPORAL
                                        elif 'logic' in type_str.lower():
                                            contradiction_type = ContradictionType.LOGICAL

                                        evidence = v.evidence if hasattr(v, 'evidence') and v.evidence else [combined_content]
                                        new_text = evidence[0] if len(evidence) > 0 else combined_content
                                        old_text = evidence[1] if len(evidence) > 1 else ""

                                        new_fact = TemporalFact(
                                            uuid=str(uuid_module.uuid4()),
                                            fact=new_text[:200],
                                            source_text=new_text[:200],
                                            user_id=user_id
                                        )
                                        old_fact = TemporalFact(
                                            uuid=str(uuid_module.uuid4()),
                                            fact=old_text[:200],
                                            source_text=old_text[:200],
                                            user_id=user_id
                                        )

                                        contradiction = Contradiction(
                                            uuid=str(uuid_module.uuid4()),
                                            old_fact=old_fact,
                                            new_fact=new_fact,
                                            contradiction_type=contradiction_type,
                                            confidence=v.severity if hasattr(v, 'severity') else 0.8,
                                            detected_at=datetime.now(),
                                            notes=v.description[:200] if hasattr(v, 'description') else ""
                                        )
                                        engine.contradiction_manager.add_pending(contradiction)
                                except Exception as e:
                                    _safe_print(f"[Recall][Turn] 矛盾记录失败: {e}")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] 一致性检查失败（无统一分析器）: {e}")

            # 5. 分别存储两条记忆
            user_memory_id = f"mem_{uuid_module.uuid4().hex[:12]}"
            ai_memory_id = f"mem_{uuid_module.uuid4().hex[:12]}"

            _safe_print(f"[Engine][Turn]    保存记忆: user_mem={user_memory_id}, ai_mem={ai_memory_id}")

            user_scope = engine.storage.get_scope(user_id)
            user_scope.add(user_message, metadata={
                'id': user_memory_id,
                'entities': all_entities,
                'keywords': keywords,
                'role': 'user',
                'character_id': character_id,
                **(metadata or {})
            })

            user_scope.add(ai_response, metadata={
                'id': ai_memory_id,
                'entities': all_entities,
                'keywords': keywords,
                'role': 'assistant',
                'character_id': character_id,
                **(metadata or {})
            })

            # v7.0.9: 预初始化 embedding 缓存变量（在 try 块外，避免 NameError）
            _cached_user_embedding = None
            _cached_ai_embedding = None

            # 6. 批量索引更新（v7.0.10: 每个索引独立 try/except 隔离，防止单个索引失败导致后续索引全部跳过）

            # (6a) 实体索引
            try:
                if engine._entity_index:
                    for entity in entities:
                        entity_type = getattr(entity, 'entity_type', 'UNKNOWN')
                        aliases = getattr(entity, 'aliases', [])
                        confidence = getattr(entity, 'confidence', 0.5)
                        engine._entity_index.add_entity_occurrence(
                            entity_name=entity.name,
                            turn_id=user_memory_id,
                            context=user_message[:200],
                            entity_type=entity_type,
                            aliases=aliases,
                            confidence=confidence
                        )
                        engine._entity_index.add_entity_occurrence(
                            entity_name=entity.name,
                            turn_id=ai_memory_id,
                            context=ai_response[:200],
                            entity_type=entity_type,
                            aliases=aliases,
                            confidence=confidence
                        )
            except Exception as e:
                _safe_print(f"[Recall][Turn] 实体索引更新失败（不影响主流程）: {e}")

            # (6b) 倒排索引
            try:
                if engine._inverted_index:
                    all_keywords_combined = list(set(all_entities + keywords))
                    engine._inverted_index.add_batch(all_keywords_combined, user_memory_id)
                    engine._inverted_index.add_batch(all_keywords_combined, ai_memory_id)
            except Exception as e:
                _safe_print(f"[Recall][Turn] 倒排索引更新失败（不影响主流程）: {e}")

            # (6c) N-gram 索引
            try:
                if engine._ngram_index:
                    engine._ngram_index.add(user_memory_id, user_message)
                    engine._ngram_index.add(ai_memory_id, ai_response)
            except Exception as e:
                _safe_print(f"[Recall][Turn] N-gram 索引更新失败（不影响主流程）: {e}")

            # (6d) 向量索引
            try:
                if engine._vector_index and engine._vector_index.enabled:
                    _cached_user_embedding = engine._vector_index.encode(user_message)
                    engine._vector_index.add(user_memory_id, _cached_user_embedding)
                    _cached_ai_embedding = engine._vector_index.encode(ai_response)
                    engine._vector_index.add(ai_memory_id, _cached_ai_embedding)

                    # v7.0.2: 同步写入 IVF 索引（如果已激活）
                    if getattr(engine, '_vector_index_ivf', None) is not None:
                        try:
                            u_vec = _cached_user_embedding.tolist() if hasattr(_cached_user_embedding, 'tolist') else list(_cached_user_embedding)
                            engine._vector_index_ivf.add(user_memory_id, u_vec)
                            a_vec = _cached_ai_embedding.tolist() if hasattr(_cached_ai_embedding, 'tolist') else list(_cached_ai_embedding)
                            engine._vector_index_ivf.add(ai_memory_id, a_vec)
                        except Exception as e:
                            _safe_print(f"[Recall v7.0] add_turn IVF 同步写入失败: {e}")
            except Exception as e:
                _safe_print(f"[Recall][Turn] 向量索引更新失败（不影响主流程）: {e}")

            # (6e) 检索器缓存
            try:
                if engine.retriever:
                    engine.retriever.cache_content(user_memory_id, user_message)
                    engine.retriever.cache_content(ai_memory_id, ai_response)
                    # v7.0.6: 补充 cache_metadata（之前缺失，导致搜索排序中 importance/recency 退化为默认值）
                    if hasattr(engine.retriever, 'cache_metadata'):
                        user_meta = metadata.copy() if metadata else {}
                        engine.retriever.cache_metadata(user_memory_id, user_meta)
                        ai_meta = metadata.copy() if metadata else {}
                        engine.retriever.cache_metadata(ai_memory_id, ai_meta)
                    if hasattr(engine.retriever, 'cache_entities'):
                        engine.retriever.cache_entities(user_memory_id, all_entities)
                        engine.retriever.cache_entities(ai_memory_id, all_entities)
            except Exception as e:
                _safe_print(f"[Recall][Turn] 检索器缓存更新失败（不影响主流程）: {e}")

            # (6f) 元数据索引
            try:
                if engine._metadata_index:
                    engine._metadata_index.add(
                        memory_id=user_memory_id,
                        source=metadata.get('source', '') if metadata else '',
                        tags=metadata.get('tags', []) if metadata else [],
                        category=metadata.get('category', '') if metadata else '',
                        content_type=metadata.get('content_type', '') if metadata else '',
                        event_time=metadata.get('event_time', '') if metadata else '',
                    )
                    engine._metadata_index.add(
                        memory_id=ai_memory_id,
                        source=metadata.get('source', '') if metadata else '',
                        tags=metadata.get('tags', []) if metadata else [],
                        category=metadata.get('category', '') if metadata else '',
                        content_type=metadata.get('content_type', '') if metadata else '',
                        event_time=metadata.get('event_time', '') if metadata else '',
                    )
            except Exception as e:
                _safe_print(f"[Recall][Turn] 元数据索引更新失败（不影响主流程）: {e}")

            # (6g) 时态索引
            try:
                if metadata and metadata.get('event_time') and engine.temporal_graph and hasattr(engine.temporal_graph, '_temporal_index'):
                    from .index.temporal_index import TemporalEntry, TimeRange
                    from datetime import datetime as _dt
                    event_time_str = metadata['event_time']
                    event_dt = None
                    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%f'):
                        try:
                            event_dt = _dt.strptime(event_time_str, fmt)
                            break
                        except ValueError:
                            continue
                    if event_dt:
                        now = _dt.now()
                        for mid in (user_memory_id, ai_memory_id):
                            entry = TemporalEntry(
                                doc_id=mid,
                                fact_range=TimeRange(start=event_dt),
                                known_at=now,
                                system_range=TimeRange(start=now),
                                subject=user_id,
                                predicate='memory'
                            )
                            engine.temporal_graph._temporal_index.add(entry)
            except Exception as e:
                _safe_print(f"[Recall][Turn] 时态索引更新失败（不影响主流程）: {e}")

            # 7. Archive 原文保存
            if engine.volume_manager:
                try:
                    engine.volume_manager.append_turn({
                        'memory_id': user_memory_id,
                        'user_id': user_id,
                        'content': user_message,
                        'entities': all_entities,
                        'keywords': keywords,
                        'role': 'user',
                        'metadata': metadata or {},
                        'created_at': time.time()
                    })
                    engine.volume_manager.append_turn({
                        'memory_id': ai_memory_id,
                        'user_id': user_id,
                        'content': ai_response,
                        'entities': all_entities,
                        'keywords': keywords,
                        'role': 'assistant',
                        'metadata': metadata or {},
                        'created_at': time.time()
                    })
                except Exception as e:
                    _safe_print(f"[Recall][Turn] Archive保存失败（不影响主流程）: {e}")

            # 8. 全文索引 BM25 更新
            if engine.fulltext_index is not None:
                try:
                    engine.fulltext_index.add(user_memory_id, user_message)
                    engine.fulltext_index.add(ai_memory_id, ai_response)
                except Exception as e:
                    _safe_print(f"[Recall][Turn] 全文索引更新失败（不影响主流程）: {e}")

            # 8.5. BAL 双写（v7.0.1: Turn API 记忆同步到 BAL 后端）
            try:
                character_id_val = character_id or 'default'
                for mid, content_text, role_val in [
                    (user_memory_id, user_message, 'user'),
                    (ai_memory_id, ai_response, 'assistant')
                ]:
                    if getattr(engine, '_storage_backend', None):
                        try:
                            engine._storage_backend.save(mid, {
                                'content': content_text,
                                'metadata': metadata or {},
                                'namespace': character_id_val,
                                'source': role_val,
                                'user_id': user_id,
                                'importance': metadata.get('importance', 0.5) if metadata else 0.5,
                            })
                        except Exception as e:
                            _safe_print(f"[Recall][Turn] StorageBackend 双写失败 ({mid}): {e}")

                    if getattr(engine, '_vector_backend', None):
                        try:
                            # v7.0.8: 复用 step 6 已计算的 embedding，避免冗余编码
                            if mid == user_memory_id and _cached_user_embedding is not None:
                                emb = _cached_user_embedding
                            elif mid == ai_memory_id and _cached_ai_embedding is not None:
                                emb = _cached_ai_embedding
                            else:
                                emb = engine._vector_index.encode(content_text) if engine._vector_index else None
                            if emb is not None:
                                vec = emb.tolist() if hasattr(emb, 'tolist') else list(emb)
                                engine._vector_backend.add(
                                    mid, vec,
                                    {'content': content_text[:200], 'user_id': user_id, 'namespace': character_id_val}
                                )
                        except Exception as e:
                            _safe_print(f"[Recall][Turn] VectorBackend 双写失败 ({mid}): {e}")

                    if getattr(engine, '_text_search_backend', None):
                        try:
                            engine._text_search_backend.add(
                                mid, content_text,
                                {'user_id': user_id, 'entities': all_entities, 'namespace': character_id_val}
                            )
                        except Exception as e:
                            _safe_print(f"[Recall][Turn] TextSearchBackend 双写失败 ({mid}): {e}")
            except Exception as e:
                _safe_print(f"[Recall][Turn] BAL 双写失败（不影响主流程）: {e}")

            # 9. 长期记忆更新
            try:
                for entity in entities:
                    entity_type = getattr(entity, 'entity_type', 'UNKNOWN')
                    confidence = getattr(entity, 'confidence', 0.5)
                    aliases = getattr(entity, 'aliases', [])

                    consolidated_entity = ConsolidatedEntity(
                        id=f"entity_{entity.name.lower().replace(' ', '_')}",
                        name=entity.name,
                        aliases=aliases if aliases else [],
                        entity_type=entity_type if entity_type else 'UNKNOWN',
                        confidence=confidence if confidence else 0.5,
                        source_turns=[user_memory_id, ai_memory_id],
                        source_memory_ids=[user_memory_id, ai_memory_id],
                        last_verified=time.strftime('%Y-%m-%dT%H:%M:%S')
                    )
                    engine.consolidated_memory.add_or_update(consolidated_entity)
                # v7.0.13: 批量 add_or_update 后统一刷盘
                engine.consolidated_memory.flush()
            except Exception as e:
                _safe_print(f"[Recall][Turn] 长期记忆更新失败（不影响主流程）: {e}")

            # 10. Episode 关联更新
            if current_episode and engine.episode_store:
                try:
                    entity_ids = []
                    for e in entities:
                        if hasattr(e, 'id') and e.id:
                            entity_ids.append(e.id)
                        elif hasattr(e, 'name'):
                            entity_ids.append(f"entity_{e.name.lower().replace(' ', '_')}")

                    relation_ids = []
                    if relations:
                        for i, rel in enumerate(relations):
                            if hasattr(rel, 'source_id') and hasattr(rel, 'target_id'):
                                relation_ids.append(f"rel_{rel.source_id}_{rel.relation_type}_{rel.target_id}")
                            elif isinstance(rel, dict):
                                relation_ids.append(f"rel_{rel.get('source')}_{rel.get('relation_type')}_{rel.get('target')}")

                    engine.episode_store.update_links(
                        episode_uuid=current_episode.uuid,
                        memory_ids=[user_memory_id, ai_memory_id],
                        entity_ids=entity_ids,
                        relation_ids=relation_ids
                    )
                    _safe_print(f"[Recall][Turn] Episode 关联已更新: memories=2, entities={len(entity_ids)}, relations={len(relation_ids)}")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] Episode 关联更新失败（不影响主流程）: {e}")

            # 11. 实体摘要更新
            if engine._entity_summary_enabled and engine.entity_summarizer:
                try:
                    for entity in entities:
                        entity_name = entity.name if hasattr(entity, 'name') else str(entity)
                        engine._maybe_update_entity_summary(entity_name)
                except Exception as e:
                    _safe_print(f"[Recall][Turn] 实体摘要更新失败（不影响主流程）: {e}")

            # 11.5. 事件关联 (EventLinker, v7.0.4: 修复参数不匹配)
            if hasattr(engine, '_event_linker') and engine._event_linker:
                try:
                    for mid, content_text in [(user_memory_id, user_message), (ai_memory_id, ai_response)]:
                        engine._event_linker.link(
                            memory_id=mid,
                            content=content_text,
                            entities=all_entities,
                            engine=engine,
                            user_id=user_id,
                        )
                    _safe_print(f"[Recall][Turn] 事件关联完成")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] 事件关联失败（不影响主流程）: {e}")

            # 11.6. 主题聚类 (TopicCluster, v7.0.5: 修复 — 使用 link_by_topics())
            if hasattr(engine, '_topic_cluster') and engine._topic_cluster:
                try:
                    for mid, content_text in [(user_memory_id, user_message), (ai_memory_id, ai_response)]:
                        topics = engine._topic_cluster.extract_topics(
                            content=content_text,
                            entities=all_entities,
                        )
                        if topics:
                            engine._topic_cluster.link_by_topics(
                                memory_id=mid,
                                topics=topics[:5],
                                engine=engine,
                                user_id=user_id if user_id else "default",
                            )
                    _safe_print(f"[Recall][Turn] 主题聚类完成")
                except Exception as e:
                    _safe_print(f"[Recall][Turn] 主题聚类失败（不影响主流程）: {e}")

            # 12. 性能监控
            try:
                engine.monitor.record(
                    MetricType.LATENCY,
                    (time.time() - start_time) * 1000
                )
            except Exception:
                pass

            processing_time = (time.time() - start_time) * 1000

            _safe_print(f"[Engine][Turn] [OK] 处理完成: 总耗时{processing_time:.1f}ms")
            _safe_print(f"[Engine][Turn]    user_mem={user_memory_id}, ai_mem={ai_memory_id}")
            _safe_print(f"[Engine][Turn]    entities={all_entities}, warnings={len(consistency_warnings)}")

            return AddTurnResult(
                success=True,
                user_memory_id=user_memory_id,
                ai_memory_id=ai_memory_id,
                entities=all_entities,
                message="对话轮次添加成功",
                consistency_warnings=consistency_warnings,
                processing_time_ms=processing_time
            )

        except Exception as e:
            _safe_print(f"[Recall][Turn] 添加失败: {e}")
            import traceback
            traceback.print_exc()
            return AddTurnResult(
                success=False,
                message=f"添加失败: {str(e)}"
            )

    # ==================== clear ====================

    def clear(self, user_id: str = "default") -> bool:
        """清空用户的所有记忆（级联删除该用户关联的数据）"""
        engine = self._engine
        try:
            # 1. 先获取该用户的所有记忆 ID
            scope = engine.storage.get_scope(user_id)
            all_memories = scope.get_all()
            memory_ids = [m.get('metadata', {}).get('id', '') for m in all_memories if m.get('metadata', {}).get('id')]

            # 2. 清空该用户的记忆存储
            scope.clear()

            # 3. 清空该用户在时态知识图谱中的数据
            try:
                if engine.temporal_graph is not None and hasattr(engine.temporal_graph, 'clear_user'):
                    engine.temporal_graph.clear_user(user_id)
            except Exception as e:
                _safe_print(f"[Recall][Clear] 时态知识图谱清理失败: {e}")

            # 3.5 v7.0.11: 显式清理 TemporalIndex 中以 memory_id 为 key 的条目
            # （temporal_graph.clear_user 只清理 edge UUID 条目，memory_id 条目需单独清理）
            try:
                ti = None
                if hasattr(engine, 'temporal_graph') and engine.temporal_graph is not None:
                    ti = getattr(engine.temporal_graph, '_temporal_index', None)
                if ti is not None and memory_ids:
                    for mid in memory_ids:
                        if hasattr(ti, 'remove'):
                            ti.remove(mid)
            except Exception as e:
                _safe_print(f"[Recall][Clear] TemporalIndex memory_id 清理失败: {e}")

            # 4. 清理实体索引
            try:
                if memory_ids and engine._entity_index is not None:
                    if hasattr(engine._entity_index, 'remove_by_turn_references'):
                        deleted_entities = engine._entity_index.remove_by_turn_references(memory_ids)
                        if deleted_entities > 0:
                            _safe_print(f"[Recall] 清理了 {deleted_entities} 个无引用实体")
            except Exception as e:
                _safe_print(f"[Recall][Clear] 实体索引清理失败: {e}")

            # 5. 清理向量索引
            try:
                if memory_ids and engine._vector_index is not None:
                    if hasattr(engine._vector_index, 'remove_by_doc_ids'):
                        removed_vectors = engine._vector_index.remove_by_doc_ids(memory_ids)
                        if removed_vectors > 0:
                            _safe_print(f"[Recall] 清理了 {removed_vectors} 个向量")
            except Exception as e:
                _safe_print(f"[Recall][Clear] 向量索引清理失败: {e}")

            # 6. 清理 L1 整合存储
            try:
                if memory_ids and engine.consolidated_memory is not None:
                    if hasattr(engine.consolidated_memory, 'remove_by_memory_ids'):
                        deleted_consolidated = engine.consolidated_memory.remove_by_memory_ids(memory_ids)
                        if deleted_consolidated > 0:
                            _safe_print(f"[Recall] 清理了 {deleted_consolidated} 个整合实体")
            except Exception as e:
                _safe_print(f"[Recall][Clear] L1 整合存储清理失败: {e}")

            # 7. 清理倒排索引
            try:
                if memory_ids and engine._inverted_index is not None:
                    if hasattr(engine._inverted_index, 'remove_by_memory_ids'):
                        removed_inverted = engine._inverted_index.remove_by_memory_ids(set(memory_ids))
                        if removed_inverted > 0:
                            _safe_print(f"[Recall] 清理了 {removed_inverted} 个倒排索引条目")
            except Exception as e:
                _safe_print(f"[Recall][Clear] 倒排索引清理失败: {e}")

            # 8. 清理 n-gram 索引
            try:
                if memory_ids and engine._ngram_index is not None:
                    if hasattr(engine._ngram_index, 'remove_by_memory_ids'):
                        removed_ngram = engine._ngram_index.remove_by_memory_ids(set(memory_ids))
                        if removed_ngram > 0:
                            _safe_print(f"[Recall] 清理了 {removed_ngram} 个 n-gram 原文")
            except Exception as e:
                _safe_print(f"[Recall][Clear] N-gram 索引清理失败: {e}")

            # 9. 清理全文索引
            try:
                if memory_ids and engine.fulltext_index is not None:
                    if hasattr(engine.fulltext_index, 'remove_by_doc_ids'):
                        removed_fulltext = engine.fulltext_index.remove_by_doc_ids(set(memory_ids))
                        if removed_fulltext > 0:
                            _safe_print(f"[Recall] 清理了 {removed_fulltext} 个全文索引文档")
            except Exception as e:
                _safe_print(f"[Recall][Clear] 全文索引清理失败: {e}")

            # 9.5 v5.0: 清理元数据索引
            try:
                if memory_ids and engine._metadata_index is not None:
                    engine._metadata_index.remove_batch(set(memory_ids))
                    _safe_print(f"[Recall] 清理了元数据索引中 {len(memory_ids)} 条记忆的条目")
            except Exception as e:
                _safe_print(f"[Recall][Clear] 元数据索引清理失败: {e}")

            # 10. 清理伏笔追踪器
            try:
                if engine.foreshadowing_tracker is not None:
                    if hasattr(engine.foreshadowing_tracker, 'clear_user'):
                        engine.foreshadowing_tracker.clear_user(user_id, all_characters=True)
            except Exception as e:
                _safe_print(f"[Recall][Clear] 伏笔追踪器清理失败: {e}")

            # 11. 清理上下文系统
            try:
                if engine.context_tracker is not None:
                    if hasattr(engine.context_tracker, 'clear_user'):
                        engine.context_tracker.clear_user(user_id, all_characters=True)
            except Exception as e:
                _safe_print(f"[Recall][Clear] 上下文系统清理失败: {e}")

            # 12. 清理伏笔分析器
            # v7.0.7: ForeshadowingAnalyzer 没有 clear_user()，只有 clear_buffer()
            try:
                if engine.foreshadowing_analyzer is not None:
                    if hasattr(engine.foreshadowing_analyzer, 'clear_buffer'):
                        engine.foreshadowing_analyzer.clear_buffer(user_id)
            except Exception as e:
                _safe_print(f"[Recall][Clear] 伏笔分析器清理失败: {e}")

            # 13. 清理 Episode 存储
            try:
                if engine.episode_store is not None:
                    if hasattr(engine.episode_store, 'clear_user'):
                        deleted_episodes = engine.episode_store.clear_user(user_id)
                        if deleted_episodes > 0:
                            _safe_print(f"[Recall] 清理了 {deleted_episodes} 个 Episode")
            except Exception as e:
                _safe_print(f"[Recall][Clear] Episode 存储清理失败: {e}")

            # v7.0.2: 14. 清理 VolumeManager (L3 archive)
            if hasattr(engine, 'volume_manager') and engine.volume_manager is not None:
                try:
                    if hasattr(engine.volume_manager, 'clear_user'):
                        engine.volume_manager.clear_user(user_id)
                    elif memory_ids:
                        for mid in memory_ids:
                            if hasattr(engine.volume_manager, 'remove_by_memory_id'):
                                engine.volume_manager.remove_by_memory_id(mid)
                    _safe_print(f"[Recall] 清理了 VolumeManager 分卷存储")
                except Exception as e:
                    _safe_print(f"[Recall] VolumeManager 清理失败: {e}")

            # v7.0.2: 15. 清理 IVF 向量索引
            if memory_ids and getattr(engine, '_vector_index_ivf', None) is not None:
                try:
                    if hasattr(engine._vector_index_ivf, 'remove_by_doc_ids'):
                        engine._vector_index_ivf.remove_by_doc_ids(memory_ids)
                    _safe_print(f"[Recall] 清理了 IVF 向量索引")
                except Exception as e:
                    _safe_print(f"[Recall] IVF 向量索引清理失败: {e}")

            # v7.0.2: 16. 清理检索器缓存
            if memory_ids and hasattr(engine, 'retriever') and engine.retriever is not None:
                try:
                    for mid in memory_ids:
                        if hasattr(engine.retriever, '_content_cache') and mid in engine.retriever._content_cache:
                            del engine.retriever._content_cache[mid]
                        if hasattr(engine.retriever, '_metadata_cache') and mid in engine.retriever._metadata_cache:
                            del engine.retriever._metadata_cache[mid]
                        if hasattr(engine.retriever, '_entities_cache') and mid in engine.retriever._entities_cache:
                            del engine.retriever._entities_cache[mid]
                except Exception as e:
                    _safe_print(f"[Recall] 检索器缓存清理失败: {e}")

            # v7.0.2: 17-19. 清理 BAL 后端
            if memory_ids:
                for mid in memory_ids:
                    try:
                        if getattr(engine, '_storage_backend', None):
                            engine._storage_backend.delete(mid)
                    except Exception:
                        pass
                    try:
                        if getattr(engine, '_vector_backend', None):
                            engine._vector_backend.delete(mid)
                    except Exception:
                        pass
                    try:
                        if getattr(engine, '_text_search_backend', None):
                            engine._text_search_backend.delete(mid)
                    except Exception:
                        pass

            # v7.0.2: 20. 清理 EventLinker
            if hasattr(engine, '_event_linker') and engine._event_linker is not None:
                try:
                    if memory_ids and hasattr(engine._event_linker, 'unlink'):
                        for mid in memory_ids:
                            engine._event_linker.unlink(mid, engine=engine)
                except Exception as e:
                    _safe_print(f"[Recall] EventLinker 清理失败: {e}")

            # v7.0.7: 21. 清理 TopicCluster（之前 clear() 遗漏，clear_all() 有但 clear() 没有）
            if getattr(engine, '_topic_cluster', None):
                try:
                    if hasattr(engine._topic_cluster, 'clear_user'):
                        engine._topic_cluster.clear_user(user_id)
                    elif hasattr(engine._topic_cluster, 'clear'):
                        # fallback: 如果没有 clear_user，跳过（不能清全局）
                        pass
                except Exception as e:
                    _safe_print(f"[Recall] TopicCluster 清理失败: {e}")

            # v7.0.8: 22. 清理 ContradictionManager（之前 clear() 遗漏，clear_all() 有但 clear() 没有）
            if getattr(engine, 'contradiction_manager', None):
                try:
                    if hasattr(engine.contradiction_manager, 'clear_user'):
                        engine.contradiction_manager.clear_user(user_id)
                    elif hasattr(engine.contradiction_manager, 'clear'):
                        # fallback: 如果没有 clear_user, 只能全清（单用户场景可接受）
                        engine.contradiction_manager.clear()
                except Exception as e:
                    _safe_print(f"[Recall] ContradictionManager 清理失败: {e}")

            # v7.0.14: 23. 清理 ConsolidationManager（_archived_ids + 实体摘要 source_memory_ids）
            if getattr(engine, 'consolidation_manager', None) is not None:
                try:
                    if memory_ids and hasattr(engine.consolidation_manager, 'remove_memory_references'):
                        affected = engine.consolidation_manager.remove_memory_references(set(memory_ids))
                        if affected > 0:
                            _safe_print(f"[Recall] 清理了 ConsolidationManager 中 {affected} 个摘要引用")
                except Exception as e:
                    _safe_print(f"[Recall] ConsolidationManager 清理失败: {e}")

            return True
        except Exception as e:
            _safe_print(f"[Recall] 清空用户记忆失败: {e}")
            return False

    # ==================== clear_all ====================

    def clear_all(self) -> bool:
        """清空所有数据（管理员操作）"""
        engine = self._engine
        try:
            # 1. 清空所有用户的记忆存储
            try:
                for user_id in engine.storage.list_users():
                    scope = engine.storage.get_scope(user_id)
                    scope.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 用户记忆存储清空失败: {e}")

            # 2. 清空统一图谱
            try:
                if engine._unified_graph is not None:
                    engine._unified_graph.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 统一图谱清空失败: {e}")

            # 3. 清空实体索引
            try:
                if engine._entity_index is not None and hasattr(engine._entity_index, 'clear'):
                    engine._entity_index.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 实体索引清空失败: {e}")

            # 4. 清空 L1 整合存储
            try:
                if engine.consolidated_memory is not None and hasattr(engine.consolidated_memory, 'clear'):
                    engine.consolidated_memory.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] L1 整合存储清空失败: {e}")

            # 5. 清空向量索引
            try:
                if engine._vector_index is not None and hasattr(engine._vector_index, 'clear'):
                    engine._vector_index.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 向量索引清空失败: {e}")

            # 6. 清空倒排索引
            try:
                if engine._inverted_index is not None and hasattr(engine._inverted_index, 'clear'):
                    engine._inverted_index.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 倒排索引清空失败: {e}")

            # 7. 清空 n-gram 索引
            try:
                if engine._ngram_index is not None and hasattr(engine._ngram_index, 'clear'):
                    engine._ngram_index.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] N-gram 索引清空失败: {e}")

            # 8. 清空全文索引
            try:
                if engine.fulltext_index is not None and hasattr(engine.fulltext_index, 'clear'):
                    engine.fulltext_index.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 全文索引清空失败: {e}")

            # 9. 清空伏笔追踪器
            try:
                if engine.foreshadowing_tracker is not None and hasattr(engine.foreshadowing_tracker, 'clear'):
                    engine.foreshadowing_tracker.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 伏笔追踪器清空失败: {e}")

            # 10. 清空上下文系统
            try:
                if engine.context_tracker is not None and hasattr(engine.context_tracker, 'clear'):
                    engine.context_tracker.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 上下文系统清空失败: {e}")

            # 11. 清空伏笔分析器（v7.0.4: 修复 — _analysis_markers 不存在）
            try:
                if engine.foreshadowing_analyzer is not None:
                    if hasattr(engine.foreshadowing_analyzer, '_buffers'):
                        engine.foreshadowing_analyzer._buffers.clear()
                    if hasattr(engine.foreshadowing_analyzer, '_turn_counters'):
                        engine.foreshadowing_analyzer._turn_counters.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 伏笔分析器清空失败: {e}")

            # 12. 清空 Episode 存储
            try:
                if engine.episode_store is not None and hasattr(engine.episode_store, 'clear'):
                    engine.episode_store.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] Episode 存储清空失败: {e}")

            # 13. 清空 L3 存档
            try:
                if engine.volume_manager is not None and hasattr(engine.volume_manager, 'clear'):
                    engine.volume_manager.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] VolumeManager 清空失败: {e}")

            # 14. v5.0: 清空元数据索引
            try:
                if engine._metadata_index is not None:
                    engine._metadata_index.clear()
            except Exception as e:
                _safe_print(f"[Recall][ClearAll] 元数据索引清空失败: {e}")

            # === v7.0.4: 以下存储位置之前 clear_all() 遗漏 ===

            # 15. 清空 IVF 向量索引
            if getattr(engine, '_vector_index_ivf', None) is not None:
                try:
                    if hasattr(engine._vector_index_ivf, 'clear'):
                        engine._vector_index_ivf.clear()
                    elif hasattr(engine._vector_index_ivf, 'reset'):
                        engine._vector_index_ivf.reset()
                except Exception as e:
                    _safe_print(f"[Recall] clear_all IVF 向量索引清空失败: {e}")

            # 16. 清空 BAL 后端
            try:
                if getattr(engine, '_storage_backend', None) and hasattr(engine._storage_backend, 'clear'):
                    engine._storage_backend.clear()
            except Exception as e:
                _safe_print(f"[Recall] clear_all StorageBackend 清空失败: {e}")
            try:
                if getattr(engine, '_vector_backend', None) and hasattr(engine._vector_backend, 'clear'):
                    engine._vector_backend.clear()
            except Exception as e:
                _safe_print(f"[Recall] clear_all VectorBackend 清空失败: {e}")
            try:
                if getattr(engine, '_text_search_backend', None) and hasattr(engine._text_search_backend, 'clear'):
                    engine._text_search_backend.clear()
            except Exception as e:
                _safe_print(f"[Recall] clear_all TextSearchBackend 清空失败: {e}")

            # 17. 清空 EventLinker
            if getattr(engine, '_event_linker', None):
                try:
                    if hasattr(engine._event_linker, 'clear'):
                        engine._event_linker.clear()
                except Exception as e:
                    _safe_print(f"[Recall] clear_all EventLinker 清空失败: {e}")

            # 18. 清空 TopicCluster
            if getattr(engine, '_topic_cluster', None):
                try:
                    if hasattr(engine._topic_cluster, 'clear'):
                        engine._topic_cluster.clear()
                except Exception as e:
                    _safe_print(f"[Recall] clear_all TopicCluster 清空失败: {e}")

            # 19. 清空检索器缓存
            if engine.retriever:
                try:
                    if hasattr(engine.retriever, '_content_cache'):
                        engine.retriever._content_cache.clear()
                    if hasattr(engine.retriever, '_metadata_cache'):
                        engine.retriever._metadata_cache.clear()
                    if hasattr(engine.retriever, '_entities_cache'):
                        engine.retriever._entities_cache.clear()
                except Exception as e:
                    _safe_print(f"[Recall] clear_all 检索器缓存清空失败: {e}")

            # 20. 清空矛盾管理器
            if getattr(engine, 'contradiction_manager', None):
                try:
                    if hasattr(engine.contradiction_manager, 'clear'):
                        engine.contradiction_manager.clear()
                except Exception as e:
                    _safe_print(f"[Recall] clear_all ContradictionManager 清空失败: {e}")

            # 21. 清空时态索引
            # v7.0.8: 修复 — engine.temporal_index 不存在，时态索引在 engine.temporal_graph._temporal_index
            ti = None
            if getattr(engine, 'temporal_index', None):
                ti = engine.temporal_index
            elif getattr(engine, 'temporal_graph', None) and hasattr(engine.temporal_graph, '_temporal_index'):
                ti = engine.temporal_graph._temporal_index
            if ti is not None:
                try:
                    if hasattr(ti, 'clear'):
                        ti.clear()
                except Exception as e:
                    _safe_print(f"[Recall] clear_all TemporalIndex 清空失败: {e}")

            # 22. v7.0.14: 清空 ConsolidationManager（_archived_ids + 实体摘要）
            if getattr(engine, 'consolidation_manager', None) is not None:
                try:
                    if hasattr(engine.consolidation_manager, 'reset_state'):
                        engine.consolidation_manager.reset_state()
                except Exception as e:
                    _safe_print(f"[Recall] clear_all ConsolidationManager 清空失败: {e}")

            _safe_print("[Recall] ✅ 已清空所有数据")
            return True
        except Exception as e:
            _safe_print(f"[Recall] 清空所有数据失败: {e}")
            return False

    # ==================== delete ====================

    def delete(self, memory_id: str, user_id: str = "default") -> bool:
        """删除记忆（级联清理所有 13 个存储位置）"""
        engine = self._engine
        _safe_print(f"[Recall][Delete] 开始级联删除记忆: {memory_id} (user={user_id})")

        # ===== 1. 主存储 =====
        try:
            scope = engine.storage.get_scope(user_id)
            success = scope.delete(memory_id)
            if success:
                _safe_print(f"[Recall][Delete] [1/13] 主存储删除成功")
            else:
                _safe_print(f"[Recall][Delete] [1/13] 主存储删除失败（记忆可能不存在）")
        except Exception as e:
            success = False
            _safe_print(f"[Recall][Delete] [1/13] 主存储删除异常: {e}")

        memory_ids_list = [memory_id]
        memory_ids_set = {memory_id}

        # ===== 2. MetadataIndex =====
        try:
            if engine._metadata_index is not None:
                engine._metadata_index.remove(memory_id)
                _safe_print(f"[Recall][Delete] [2/13] 元数据索引已清理")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [2/13] 元数据索引清理失败: {e}")

        # ===== 3. VectorIndex =====
        try:
            if engine._vector_index is not None:
                if hasattr(engine._vector_index, 'remove_by_doc_ids'):
                    removed = engine._vector_index.remove_by_doc_ids(memory_ids_list)
                    _safe_print(f"[Recall][Delete] [3/13] 向量索引已清理 ({removed} 个向量)")
                elif hasattr(engine._vector_index, 'remove'):
                    engine._vector_index.remove(memory_id)
                    _safe_print(f"[Recall][Delete] [3/13] 向量索引已清理")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [3/13] 向量索引清理失败: {e}")

        # ===== 3b. VectorIndexIVF (v7.0.2: 之前遗漏) =====
        try:
            if getattr(engine, '_vector_index_ivf', None) is not None:
                if hasattr(engine._vector_index_ivf, 'remove_by_doc_ids'):
                    engine._vector_index_ivf.remove_by_doc_ids(memory_ids_list)
                    _safe_print(f"[Recall][Delete] [3b] IVF 向量索引已清理")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [3b] IVF 向量索引清理失败: {e}")

        # ===== 4. EntityIndex =====
        try:
            if engine._entity_index is not None:
                if hasattr(engine._entity_index, 'remove_by_turn_references'):
                    deleted = engine._entity_index.remove_by_turn_references(memory_ids_list)
                    _safe_print(f"[Recall][Delete] [4/13] 实体索引已清理 ({deleted} 个无引用实体被删除)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [4/13] 实体索引清理失败: {e}")

        # ===== 5. InvertedIndex =====
        try:
            if engine._inverted_index is not None:
                if hasattr(engine._inverted_index, 'remove_by_memory_ids'):
                    removed = engine._inverted_index.remove_by_memory_ids(memory_ids_set)
                    _safe_print(f"[Recall][Delete] [5/13] 倒排索引已清理 ({removed} 个条目)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [5/13] 倒排索引清理失败: {e}")

        # ===== 6. NgramIndex =====
        try:
            if engine._ngram_index is not None:
                if hasattr(engine._ngram_index, 'remove_by_memory_ids'):
                    removed = engine._ngram_index.remove_by_memory_ids(memory_ids_set)
                    _safe_print(f"[Recall][Delete] [6/13] N-gram 索引已清理 ({removed} 个条目)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [6/13] N-gram 索引清理失败: {e}")

        # ===== 7. FullTextIndex =====
        try:
            if engine.fulltext_index is not None:
                if hasattr(engine.fulltext_index, 'remove'):
                    engine.fulltext_index.remove(memory_id)
                    _safe_print(f"[Recall][Delete] [7/13] 全文索引已清理")
                elif hasattr(engine.fulltext_index, 'remove_by_doc_ids'):
                    removed = engine.fulltext_index.remove_by_doc_ids(memory_ids_set)
                    _safe_print(f"[Recall][Delete] [7/13] 全文索引已清理 ({removed} 个文档)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [7/13] 全文索引清理失败: {e}")

        # ===== 8. Knowledge/Temporal Graph =====
        try:
            if engine.temporal_graph is not None:
                removed_edges = 0
                if hasattr(engine.temporal_graph, 'edges'):
                    edges_to_expire = []
                    for edge_id, edge in engine.temporal_graph.edges.items():
                        edge_props = getattr(edge, 'properties', {}) or {}
                        if (edge_props.get('memory_id') == memory_id or
                            edge_props.get('source_memory_id') == memory_id):
                            edges_to_expire.append(edge_id)
                            continue
                        # 8b. Topic cluster relations cleanup (v7.0.1: 之前缺失)
                        src = getattr(edge, 'source_id', '')
                        tgt = getattr(edge, 'target_id', '')
                        rel_type = getattr(edge, 'relation_type', '') or edge_props.get('relation_type', '')
                        if (src == memory_id or tgt == memory_id) and rel_type == 'TOPIC_RELATED':
                            edges_to_expire.append(edge_id)
                    for edge_id in edges_to_expire:
                        edge = engine.temporal_graph.edges.get(edge_id)
                        if edge and hasattr(edge, 'expire'):
                            edge.expire()
                            removed_edges += 1
                _safe_print(f"[Recall][Delete] [8/13] 图谱已清理 ({removed_edges} 条边标记过期)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [8/13] 图谱清理失败: {e}")

        # ===== 8b. TemporalIndex cleanup (v7.0.3: 之前缺失，删除后幽灵时态条目) =====
        try:
            if hasattr(engine, 'temporal_graph') and engine.temporal_graph is not None:
                ti = getattr(engine.temporal_graph, '_temporal_index', None)
                if ti is not None and hasattr(ti, 'remove'):
                    removed_temporal = ti.remove(memory_id)
                    _safe_print(f"[Recall][Delete] [8b] 时态索引已清理 (removed={removed_temporal})")
                else:
                    _safe_print(f"[Recall][Delete] [8b] 时态索引无 remove 方法，跳过")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [8b] 时态索引清理失败: {e}")

        # ===== 8c. Event links cleanup (v7.0.1: 之前缺失) =====
        try:
            if hasattr(engine, '_event_linker') and engine._event_linker is not None:
                if hasattr(engine._event_linker, 'unlink'):
                    removed_links = engine._event_linker.unlink(memory_id, engine=engine)
                    _safe_print(f"[Recall][Delete] [8c] 事件关联已清理 (removed={removed_links})")
                elif hasattr(engine, 'temporal_graph') and engine.temporal_graph is not None:
                    # Fallback: clean event link edges from graph directly
                    if hasattr(engine.temporal_graph, 'edges'):
                        event_edges = []
                        for eid, edge in engine.temporal_graph.edges.items():
                            ep = getattr(edge, 'properties', {}) or {}
                            src = getattr(edge, 'source_id', '')
                            tgt = getattr(edge, 'target_id', '')
                            rel_type = getattr(edge, 'relation_type', '') or ep.get('relation_type', '')
                            if (src == memory_id or tgt == memory_id) and rel_type in ('CAUSED', 'FOLLOWS', 'RELATED', 'EVENT_LINK'):
                                event_edges.append(eid)
                        for eid in event_edges:
                            e = engine.temporal_graph.edges.get(eid)
                            if e and hasattr(e, 'expire'):
                                e.expire()
                        _safe_print(f"[Recall][Delete] [8c] 事件关联已清理 ({len(event_edges)} 条)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [8c] 事件关联清理失败: {e}")

        # ===== 8d. TopicCluster cleanup (v7.0.3: 之前缺失) =====
        try:
            if hasattr(engine, '_topic_cluster') and engine._topic_cluster is not None:
                if hasattr(engine._topic_cluster, 'delete_memory_topics'):
                    engine._topic_cluster.delete_memory_topics(memory_id)
                    _safe_print(f"[Recall][Delete] [8d] 话题聚类已清理")
                elif hasattr(engine._topic_cluster, 'remove'):
                    engine._topic_cluster.remove(memory_id)
                    _safe_print(f"[Recall][Delete] [8d] 话题聚类已清理")
                elif hasattr(engine._topic_cluster, 'delete'):
                    engine._topic_cluster.delete(memory_id)
                    _safe_print(f"[Recall][Delete] [8d] 话题聚类已清理")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [8d] 话题聚类清理失败: {e}")

        # ===== 8e. ContradictionManager cleanup (v7.0.13: 之前缺失，防止幽灵矛盾) =====
        try:
            if hasattr(engine, 'contradiction_manager') and engine.contradiction_manager is not None:
                # 收集与被删除记忆关联的 fact UUID
                expired_fact_uuids = set()
                if hasattr(engine, 'temporal_graph') and engine.temporal_graph is not None:
                    if hasattr(engine.temporal_graph, 'edges'):
                        for edge_id, edge in engine.temporal_graph.edges.items():
                            edge_props = getattr(edge, 'properties', {}) or {}
                            if (edge_props.get('memory_id') == memory_id or
                                edge_props.get('source_memory_id') == memory_id):
                                fact_uuid = edge_props.get('fact_uuid') or getattr(edge, 'uuid', None) or edge_id
                                if fact_uuid:
                                    expired_fact_uuids.add(fact_uuid)
                if expired_fact_uuids:
                    removed_contradictions = engine.contradiction_manager.remove_by_fact_uuids(expired_fact_uuids)
                    _safe_print(f"[Recall][Delete] [8e] 矛盾记录已清理 ({removed_contradictions} 条)")
                else:
                    _safe_print(f"[Recall][Delete] [8e] 矛盾记录无需清理（无关联事实）")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [8e] 矛盾记录清理失败: {e}")

        # ===== 9. ConsolidatedMemory (L1) =====
        try:
            if engine.consolidated_memory is not None:
                if hasattr(engine.consolidated_memory, 'remove_by_memory_ids'):
                    deleted = engine.consolidated_memory.remove_by_memory_ids(memory_ids_list)
                    _safe_print(f"[Recall][Delete] [9/13] 整合存储已清理 ({deleted} 个实体)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [9/13] 整合存储清理失败: {e}")

        # ===== 10. VolumeManager (L3 archive) =====
        try:
            if hasattr(engine, 'volume_manager') and engine.volume_manager is not None:
                if hasattr(engine.volume_manager, 'remove_by_memory_id'):
                    removed = engine.volume_manager.remove_by_memory_id(memory_id)
                    _safe_print(f"[Recall][Delete] [10/13] 分卷存储索引已清理 (removed={removed})")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [10/13] 分卷存储清理失败: {e}")

        # ===== 11. ContextTracker =====
        try:
            if hasattr(engine, 'context_tracker') and engine.context_tracker is not None:
                if hasattr(engine.context_tracker, 'invalidate_memory'):
                    engine.context_tracker.invalidate_memory(memory_id)
                    _safe_print(f"[Recall][Delete] [11/13] 上下文追踪器已清理")
                else:
                    _safe_print(f"[Recall][Delete] [11/13] 上下文追踪器无单条清理方法，跳过")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [11/13] 上下文追踪器清理失败: {e}")

        # ===== 12. EpisodeStore =====
        try:
            if hasattr(engine, 'episode_store') and engine.episode_store is not None:
                if hasattr(engine.episode_store, 'remove_memory_references'):
                    modified = engine.episode_store.remove_memory_references(memory_id)
                    _safe_print(f"[Recall][Delete] [12/13] Episode 存储已清理 ({modified} 个 Episode 受影响)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [12/13] Episode 存储清理失败: {e}")

        # ===== 13. Retriever content cache =====
        try:
            if hasattr(engine, 'retriever') and engine.retriever is not None:
                cache_cleared = False
                if hasattr(engine.retriever, '_content_cache') and memory_id in engine.retriever._content_cache:
                    del engine.retriever._content_cache[memory_id]
                    cache_cleared = True
                if hasattr(engine.retriever, '_metadata_cache') and memory_id in engine.retriever._metadata_cache:
                    del engine.retriever._metadata_cache[memory_id]
                    cache_cleared = True
                if hasattr(engine.retriever, '_entities_cache') and memory_id in engine.retriever._entities_cache:
                    del engine.retriever._entities_cache[memory_id]
                    cache_cleared = True
                # ElevenLayerRetriever 代理模式
                if hasattr(engine.retriever, '_impl'):
                    impl = engine.retriever._impl
                    if hasattr(impl, '_content_cache') and memory_id in impl._content_cache:
                        del impl._content_cache[memory_id]
                        cache_cleared = True
                    if hasattr(impl, '_metadata_cache') and memory_id in impl._metadata_cache:
                        del impl._metadata_cache[memory_id]
                        cache_cleared = True
                    if hasattr(impl, '_entities_cache') and memory_id in impl._entities_cache:
                        del impl._entities_cache[memory_id]
                        cache_cleared = True
                _safe_print(f"[Recall][Delete] [13/13] 检索器缓存已清理 (cleared={cache_cleared})")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [13/13] 检索器缓存清理失败: {e}")

        # ===== 14-16. BAL 后端级联删除（v7.0.1: 防止数据泄漏）=====
        try:
            if getattr(engine, '_storage_backend', None):
                engine._storage_backend.delete(memory_id)
                _safe_print(f"[Recall][Delete] [14/16] StorageBackend 已删除")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [14/16] StorageBackend 删除失败: {e}")

        try:
            if getattr(engine, '_vector_backend', None):
                engine._vector_backend.delete(memory_id)
                _safe_print(f"[Recall][Delete] [15/16] VectorBackend 已删除")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [15/16] VectorBackend 删除失败: {e}")

        try:
            if getattr(engine, '_text_search_backend', None):
                engine._text_search_backend.delete(memory_id)
                _safe_print(f"[Recall][Delete] [16/16] TextSearchBackend 已删除")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [16/16] TextSearchBackend 删除失败: {e}")

        # ===== 17. ConsolidationManager cleanup (v7.0.14: 整合状态清理) =====
        try:
            if getattr(engine, 'consolidation_manager', None) is not None:
                if hasattr(engine.consolidation_manager, 'remove_memory_references'):
                    affected = engine.consolidation_manager.remove_memory_references(memory_ids_set)
                    _safe_print(f"[Recall][Delete] [17] ConsolidationManager 已清理 ({affected} 个摘要受影响)")
        except Exception as e:
            _safe_print(f"[Recall][Delete] [17] ConsolidationManager 清理失败: {e}")

        _safe_print(f"[Recall][Delete] 级联删除完成: memory_id={memory_id}, 主存储={'成功' if success else '失败'}")
        return success

    # ==================== update ====================

    def update(
        self,
        memory_id: str,
        content: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新记忆（同步到所有后端）"""
        engine = self._engine
        scope = engine.storage.get_scope(user_id)
        success = scope.update(memory_id, content, metadata)

        if success:
            # v7.0.2: 同步更新传统索引（之前遗漏，导致搜索返回旧内容）
            character_id = getattr(scope, 'character_id', 'default')

            # (1) 向量索引：delete + add
            try:
                new_embedding = None
                if engine._vector_index:
                    if hasattr(engine._vector_index, 'encode'):
                        new_embedding = engine._vector_index.encode(content)
                    if hasattr(engine._vector_index, 'remove_by_doc_ids'):
                        engine._vector_index.remove_by_doc_ids([memory_id])
                    if new_embedding is not None:
                        engine._vector_index.add(memory_id, new_embedding)
                # IVF 索引同步
                if getattr(engine, '_vector_index_ivf', None) is not None:
                    if hasattr(engine._vector_index_ivf, 'remove_by_doc_ids'):
                        engine._vector_index_ivf.remove_by_doc_ids([memory_id])
                    if new_embedding is not None:
                        vec = new_embedding.tolist() if hasattr(new_embedding, 'tolist') else list(new_embedding)
                        engine._vector_index_ivf.add(memory_id, vec)
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() 向量索引同步失败: {e}")

            # (2) 倒排索引：remove + add
            try:
                if engine._inverted_index:
                    if hasattr(engine._inverted_index, 'remove_by_memory_ids'):
                        engine._inverted_index.remove_by_memory_ids({memory_id})
                    # 重新提取关键词
                    new_keywords = []
                    if engine.smart_extractor:
                        try:
                            result = engine.smart_extractor.extract(content)
                            new_keywords = result.keywords if result else []
                        except Exception:
                            pass
                    if not new_keywords:
                        # v7.0.12: 修复 — keyword_extractor 模块不存在，改用简单分词
                        import re as _re
                        new_keywords = [w for w in _re.findall(r'[\w\u4e00-\u9fff]+', content) if len(w) >= 2][:20]
                    engine._inverted_index.add_batch(new_keywords, memory_id)
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() 倒排索引同步失败: {e}")

            # (3) N-gram 索引：remove + add
            try:
                if engine._ngram_index:
                    if hasattr(engine._ngram_index, 'remove_by_memory_ids'):
                        engine._ngram_index.remove_by_memory_ids({memory_id})
                    engine._ngram_index.add(memory_id, content)
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() N-gram 索引同步失败: {e}")

            # (4) 全文 BM25 索引：remove + add
            try:
                if engine.fulltext_index:
                    if hasattr(engine.fulltext_index, 'remove_by_doc_ids'):
                        engine.fulltext_index.remove_by_doc_ids({memory_id})
                    engine.fulltext_index.add(memory_id, content)
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() 全文索引同步失败: {e}")

            # (5) 元数据索引
            try:
                if engine._metadata_index:
                    engine._metadata_index.remove_batch({memory_id})
                    engine._metadata_index.add(
                        memory_id=memory_id,
                        source=metadata.get('source', '') if metadata else '',
                        tags=metadata.get('tags', []) if metadata else [],
                        category=metadata.get('category', '') if metadata else '',
                        content_type=metadata.get('content_type', '') if metadata else '',
                        event_time=metadata.get('event_time', '') if metadata else '',
                    )
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() 元数据索引同步失败: {e}")

            # (6) 检索器缓存：更新缓存内容
            try:
                if engine.retriever:
                    engine.retriever.cache_content(memory_id, content)
                    if hasattr(engine.retriever, 'cache_metadata') and metadata:
                        engine.retriever.cache_metadata(memory_id, metadata)
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() 检索器缓存同步失败: {e}")

            # (7) BAL 后端同步更新
            try:
                if getattr(engine, '_storage_backend', None):
                    engine._storage_backend.save(memory_id, {
                        'content': content,
                        'metadata': metadata or {},
                        'namespace': character_id,
                        'user_id': user_id,
                    })
            except Exception as e:
                _safe_print(f"[Recall v7.0] StorageBackend 同步更新失败: {e}")

            try:
                if getattr(engine, '_vector_backend', None) and engine.embedding_backend:
                    vec = engine.embedding_backend.encode(content)
                    vec_list = vec.tolist() if hasattr(vec, 'tolist') else list(vec)
                    # delete + add（SQLiteVectorBackend 不支持原地更新）
                    try:
                        engine._vector_backend.delete(memory_id)
                    except Exception:
                        pass
                    engine._vector_backend.add(memory_id, vec_list, {'content': content[:200], 'user_id': user_id})
            except Exception as e:
                _safe_print(f"[Recall v7.0] VectorBackend 同步更新失败: {e}")

            try:
                if getattr(engine, '_text_search_backend', None):
                    # 先删后加（FTS5 不支持原地更新）
                    engine._text_search_backend.delete(memory_id)
                    engine._text_search_backend.add(
                        memory_id, content,
                        {'user_id': user_id, 'namespace': character_id}
                    )
            except Exception as e:
                _safe_print(f"[Recall v7.0] TextSearchBackend 同步更新失败: {e}")

            # === v7.0.4: 以下存储位置之前 update() 遗漏 ===

            # (8) 实体重新提取 + 实体索引更新
            try:
                new_entities = []
                new_keywords = []
                if engine.smart_extractor:
                    result = engine.smart_extractor.extract(content)
                    if result:
                        new_entities = result.entities
                        new_keywords = result.keywords
                elif engine.entity_extractor:
                    new_entities = engine.entity_extractor.extract(content)

                if new_entities and engine._entity_index:
                    # v7.0.6: 修复 — 之前使用不存在的 remove_memory_reference/add_entity_reference API
                    # 正确的 API 是 remove_by_turn_references + add_entity_occurrence（与 add()/delete() 一致）
                    
                    # 清理旧实体引用
                    if hasattr(engine._entity_index, 'remove_by_turn_references'):
                        engine._entity_index.remove_by_turn_references([memory_id])
                    
                    # 添加新实体引用
                    for ent in new_entities:
                        ent_name = ent.name if hasattr(ent, 'name') else str(ent)
                        ent_type = getattr(ent, 'entity_type', None) or 'UNKNOWN'
                        ent_aliases = getattr(ent, 'aliases', None) or []
                        ent_confidence = getattr(ent, 'confidence', None) or 0.5
                        
                        if hasattr(engine._entity_index, 'add_entity_occurrence'):
                            engine._entity_index.add_entity_occurrence(
                                entity_name=ent_name,
                                turn_id=memory_id,
                                context=content[:200],
                                entity_type=ent_type,
                                aliases=ent_aliases,
                                confidence=ent_confidence
                            )
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() 实体索引同步失败: {e}")

            # (9) 时态索引更新
            # v7.0.6: 修复 — 之前用 engine.temporal_index（不存在），正确路径是 engine.temporal_graph._temporal_index
            try:
                ti = None
                if hasattr(engine, 'temporal_graph') and engine.temporal_graph is not None:
                    ti = getattr(engine.temporal_graph, '_temporal_index', None)
                if ti is not None:
                    # 先移除旧条目
                    if hasattr(ti, 'remove'):
                        ti.remove(memory_id)
                    # 重新添加（如果有 event_time）
                    event_time = metadata.get('event_time') if metadata else None
                    if event_time and hasattr(ti, 'add'):
                        from .index.temporal_index import TemporalEntry, TimeRange
                        from datetime import datetime as _dt
                        event_dt = None
                        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%f'):
                            try:
                                event_dt = _dt.strptime(event_time, fmt)
                                break
                            except (ValueError, TypeError):
                                continue
                        if event_dt:
                            entry = TemporalEntry(
                                doc_id=memory_id,
                                fact_range=TimeRange(start=event_dt),
                                known_at=_dt.now(),
                                subject=user_id,          # v7.0.14: 修复 U7 — 之前缺失
                                predicate='memory',       # v7.0.14: 修复 U7 — 之前缺失
                            )
                            ti.add(entry)
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() 时态索引同步失败: {e}")

            # (10) TopicCluster 更新
            # v7.0.5: 修复 — 使用 link_by_topics() 确保 TopicStore 得到更新
            try:
                if getattr(engine, '_topic_cluster', None):
                    # 删除旧主题关联
                    if hasattr(engine._topic_cluster, 'delete_memory_topics'):
                        engine._topic_cluster.delete_memory_topics(memory_id)
                    # 重新提取主题并存入 TopicStore
                    entity_names = [e.name if hasattr(e, 'name') else str(e) for e in new_entities] if new_entities else []
                    topics = engine._topic_cluster.extract_topics(content=content, entities=entity_names)
                    if topics:
                        engine._topic_cluster.link_by_topics(
                            memory_id=memory_id,
                            topics=topics[:5],
                            engine=engine,
                            user_id=user_id if user_id else "default",
                        )
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() TopicCluster 同步失败: {e}")

            # (11) EventLinker 重建关联
            try:
                if getattr(engine, '_event_linker', None):
                    if hasattr(engine._event_linker, 'unlink'):
                        engine._event_linker.unlink(memory_id, engine=engine)
                    entity_names = [e.name if hasattr(e, 'name') else str(e) for e in new_entities] if new_entities else []
                    engine._event_linker.link(
                        memory_id=memory_id,
                        content=content,
                        entities=entity_names,
                        engine=engine,
                        user_id=user_id,
                    )
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() EventLinker 同步失败: {e}")

            # (12) ConsolidatedMemory 更新
            # v7.0.12: 修复 — ConsolidatedMemory 没有 update() 方法，改用 add_or_update()
            try:
                if engine.consolidated_memory is not None and hasattr(engine.consolidated_memory, 'add_or_update'):
                    from .storage.layer1_consolidated import ConsolidatedEntity
                    # 使用 step 8 提取的新实体更新整合存储
                    try:
                        update_entities = new_entities if new_entities else []
                    except NameError:
                        update_entities = []
                    for ent in update_entities:
                        ent_name = ent.name if hasattr(ent, 'name') else str(ent)
                        ce = ConsolidatedEntity(
                            id=f"entity_{ent_name.lower().replace(' ', '_')}",
                            name=ent_name,
                            entity_type=getattr(ent, 'entity_type', None) or 'UNKNOWN',
                            current_state={"last_content": content[:200]},
                            confidence=getattr(ent, 'confidence', None) or 0.5,
                            verification_count=1,
                            source_memory_ids=[memory_id],
                        )
                        engine.consolidated_memory.add_or_update(ce)
                    # v7.0.13: 批量 add_or_update 后统一刷盘
                    if update_entities:
                        engine.consolidated_memory.flush()
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() ConsolidatedMemory 同步失败: {e}")

            # === v7.0.11: 以下存储位置之前 update() 遗漏 ===

            # (13) VolumeManager (L3 archive) — 更新归档中的旧内容
            try:
                if hasattr(engine, 'volume_manager') and engine.volume_manager is not None:
                    # v7.0.12: 修复 append_turn 签名 — 它只接受一个 dict 参数
                    existing_turn = engine.volume_manager.get_turn_by_memory_id(memory_id)
                    if existing_turn:
                        # 已有归档，通过删除+重新追加来更新
                        try:
                            if hasattr(engine.volume_manager, 'remove_by_memory_id'):
                                engine.volume_manager.remove_by_memory_id(memory_id)
                        except Exception:
                            pass
                    # v7.0.14: 修复 U4 — 传递实际的 entities 和 keywords（之前硬编码为空列表）
                    try:
                        vol_entities = [e.name if hasattr(e, 'name') else str(e) for e in new_entities] if new_entities else []
                    except NameError:
                        vol_entities = []
                    try:
                        vol_keywords = new_keywords if new_keywords else []
                    except NameError:
                        vol_keywords = []
                    engine.volume_manager.append_turn({
                        'memory_id': memory_id,
                        'user_id': user_id,
                        'content': content,
                        'entities': vol_entities,
                        'keywords': vol_keywords,
                        'metadata': metadata or {},
                    })
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() VolumeManager 同步失败: {e}")

            # (14) KnowledgeGraph 关系更新 — 清理旧关系并重建
            try:
                if engine.knowledge_graph is not None:
                    # v7.0.12: 修复 — 'new_entities' in dir() 永远为 False，改用 try/except 检查局部变量
                    try:
                        new_entities_for_kg = new_entities if new_entities else []
                    except NameError:
                        new_entities_for_kg = []
                    entity_names_for_kg = [e.name if hasattr(e, 'name') else str(e) for e in new_entities_for_kg]
                    
                    if engine.relation_extractor and entity_names_for_kg:
                        new_relations = engine.relation_extractor.extract(content, 0, entities=new_entities_for_kg)
                        for rel in (new_relations or []):
                            try:
                                engine.knowledge_graph.add_relation(
                                    source_id=rel[0] if isinstance(rel, (list, tuple)) else getattr(rel, 'source', ''),
                                    target_id=rel[2] if isinstance(rel, (list, tuple)) else getattr(rel, 'target', ''),
                                    relation_type=rel[1] if isinstance(rel, (list, tuple)) else getattr(rel, 'relation', ''),
                                    source_text=content[:200],
                                )
                            except Exception:
                                pass
            except Exception as e:
                _safe_print(f"[Recall v7.0] update() KnowledgeGraph 同步失败: {e}")

        return success
