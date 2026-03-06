"""
Recall v7.0 - Context Build Module
Extracted from engine.py for facade pattern.
Handles: build_context() + all _build_* helper methods

Note: Named 'ContextBuild' (not 'ContextBuilder') to avoid collision with
recall.retrieval.context_builder.ContextBuilder which serves a different purpose.
"""
from __future__ import annotations

import os as _os
import time as _time
from typing import TYPE_CHECKING, Dict, Any, Optional, List

if TYPE_CHECKING:
    from .engine import RecallEngine


# Windows GBK 编码兼容的安全打印函数
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


class ContextBuild:
    """Engine facade for build_context and all _build_* helpers.

    All engine state is accessed via ``self._engine``.
    """

    def __init__(self, engine: 'RecallEngine') -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_context(
        self,
        query: str,
        user_id: str = "default",
        character_id: str = "default",
        max_tokens: int = 2000,
        include_recent: int = None,  # 从配置读取默认值
        include_core_facts: bool = True,
        auto_extract_context: bool = False,  # 默认关闭，避免每次生成都提取条件
        adaptive_tokens: bool = True  # Phase 7.4: 自适应 token 预算
    ) -> str:
        """构建上下文 - 全方位记忆策略，确保100%不遗漏任何细节

        七层上下文策略（100%不遗忘保证）：
        1. 持久条件层 - 已确立的背景设定（如用户身份、环境、目标）
        2. 核心事实层 - 压缩的实体知识 + 关系图谱
        3. 相关记忆层 - 与查询相关的详细记忆
        4. 关键实体补充层 - 从持久条件和伏笔中提取关键词，补充检索（新增）
        5. 最近对话层 - 保持对话连贯性
        6. 伏笔层 - 所有活跃伏笔 + 主动提醒
        7. 场景优化层 - 根据场景调整检索策略

        Args:
            query: 当前查询
            user_id: 用户ID
            character_id: 角色ID
            max_tokens: 最大token数（越大能注入越多细节）
            include_recent: 包含的最近对话数（None 时从配置读取 BUILD_CONTEXT_INCLUDE_RECENT）
            include_core_facts: 是否包含核心事实摘要
            auto_extract_context: 是否自动从查询中提取持久条件（默认False，条件提取在保存记忆时进行）
            adaptive_tokens: 是否启用自适应 token 预算（Phase 7.4）

        Returns:
            str: 构建的上下文
        """
        start_time = _time.time()
        engine = self._engine

        # Phase 7.4: 自适应 token 预算
        if adaptive_tokens:
            max_tokens = self._adaptive_token_budget(query, max_tokens, engine)

        # v7.0.5: 修复 — 从 RecallConfig 读取配置，不再直接读取 os.environ
        if include_recent is None:
            if hasattr(engine, 'recall_config') and engine.recall_config:
                include_recent = getattr(engine.recall_config, 'build_context_include_recent', 10)
            else:
                include_recent = int(_os.environ.get('BUILD_CONTEXT_INCLUDE_RECENT', '10'))
        if hasattr(engine, 'recall_config') and engine.recall_config:
            proactive_enabled = getattr(engine.recall_config, 'proactive_reminder_enabled', True)
            proactive_turns = getattr(engine.recall_config, 'proactive_reminder_turns', 50)
        else:
            proactive_enabled = _os.environ.get('PROACTIVE_REMINDER_ENABLED', 'true').lower() in ('true', '1', 'yes')
            proactive_turns = int(_os.environ.get('PROACTIVE_REMINDER_TURNS', '50'))

        # v5.0: 非 RP 模式下 character_id 强制为 default
        if not engine._mode.character_dimension_enabled:
            character_id = "default"

        query_preview = query[:50].replace('\n', ' ') if len(query) > 50 else query.replace('\n', ' ')
        _safe_print(f"[Recall][Engine] 📦 构建上下文: user={user_id}, char={character_id}")
        _safe_print(f"[Recall][Engine]    查询: {query_preview}{'...' if len(query) > 50 else ''}")
        _safe_print(f"[Recall][Engine]    参数: max_tokens={max_tokens}, recent={include_recent}, proactive={proactive_enabled}")
        parts = []

        # ========== 0. 场景检测（决定检索策略）==========
        scenario = engine.scenario_detector.detect(query)
        retrieval_strategy = scenario.suggested_retrieval_strategy

        # ========== 0.5 L0 核心设定注入（角色卡/世界观/规则 - 最高优先级）==========
        if hasattr(engine, 'core_settings') and engine.core_settings:
            # 根据场景类型获取对应的核心设定
            scenario_type = 'roleplay' if scenario.scenario_type.value in ['roleplay', 'novel_writing', 'worldbuilding'] else 'coding' if scenario.scenario_type.value == 'coding' else 'general'
            injection_text = engine.core_settings.get_injection_text(scenario_type)
            if injection_text:
                parts.append(f"【核心设定】\n{injection_text}")

        # ========== 1. 持久条件层（已确立的背景设定）==========
        # 这是最重要的层 - 用户说"我是大学生想创业"，后续所有对话都应基于此
        active_contexts = engine.context_tracker.get_active(user_id, character_id)
        if active_contexts:
            # 批量标记所有被使用的条件（更新 last_used 和 use_count，只写一次文件）
            context_ids = [ctx.id for ctx in active_contexts]
            engine.context_tracker.mark_used_batch(context_ids, user_id, character_id)

            persistent_context = engine.context_tracker.format_for_prompt(user_id, character_id)
            if persistent_context:
                parts.append(persistent_context)

        # 自动从当前查询中提取新的持久条件
        if auto_extract_context and query:
            engine.context_tracker.extract_from_text(query, user_id, character_id)

        # ========== 2. 核心事实层 + 关系图谱 ==========
        if include_core_facts:
            core_facts = self._build_core_facts_section(user_id, max_tokens // 5)
            if core_facts:
                parts.append(core_facts)

            # 利用知识图谱扩展相关实体
            graph_context = self._build_graph_context(query, user_id, max_tokens // 10)
            if graph_context:
                parts.append(graph_context)

        # ========== 3. 相关记忆层（详细记忆）==========
        # 根据场景和 token 预算动态调整检索数量
        top_k = self._calculate_top_k(max_tokens, retrieval_strategy)

        # Phase 7.3: 时间意图解析 → 激活 L2 时态检索
        temporal_context = None
        if hasattr(engine, '_time_intent_parser') and engine._time_intent_parser and query:
            try:
                time_result = engine._time_intent_parser.parse(query)
                if time_result and time_result.start and time_result.end:
                    from recall.retrieval.config import TemporalContext
                    temporal_context = TemporalContext(
                        start=time_result.start,
                        end=time_result.end,
                    )
            except Exception:
                pass

        memories = engine.search(query, user_id=user_id, top_k=top_k, temporal_context=temporal_context)

        if memories:
            memory_section = self._build_memory_section(memories, max_tokens // 3)
            if memory_section:
                parts.append(memory_section)

        # ========== 3.5 关键实体补充检索层（100%不遗忘保证）==========
        # 从持久条件和伏笔中提取关键词，进行补充检索
        # 确保即使 query 中没有直接提及，重要信息也能被召回
        supplementary_keywords = self._extract_supplementary_keywords(user_id, character_id, active_contexts)
        if supplementary_keywords:
            supplementary_memories = self._search_by_keywords(supplementary_keywords, user_id, top_k=5)
            if supplementary_memories:
                # 过滤掉已经在 memories 中的记忆
                existing_ids = {m.id for m in memories} if memories else set()
                new_supplementary = [m for m in supplementary_memories if m.id not in existing_ids]
                if new_supplementary:
                    supplementary_section = self._build_supplementary_section(new_supplementary)
                    if supplementary_section:
                        parts.append(supplementary_section)

        # ========== 4. 最近对话层 ==========
        scope = engine.storage.get_scope(user_id)
        recent = scope.get_recent(include_recent)

        if recent:
            recent_section = self._build_recent_section(recent)
            if recent_section:
                parts.append(recent_section)

        # ========== 5. 伏笔层（所有活跃伏笔 + 主动提醒）==========
        # v5.0: 仅 RP 模式启用伏笔层
        if engine._mode.foreshadowing_enabled and engine.foreshadowing_tracker:
            # 使用 tracker 的专用方法，包含主动提醒逻辑（重要伏笔长期未推进会提醒 AI）
            foreshadowing_context = engine.foreshadowing_tracker.get_context_for_prompt(
                user_id=user_id,
                character_id=character_id,
                max_count=5,
                current_turn=engine.volume_manager.get_total_turns() if engine.volume_manager else None
            )
            if foreshadowing_context:
                parts.append(foreshadowing_context)

        # ========== 5.5 主动提醒层（100%不遗忘保证）==========
        # 对长期未提及的重要持久条件进行主动提醒
        if proactive_enabled and active_contexts:
            proactive_reminders = self._build_proactive_reminders(
                active_contexts, proactive_turns, user_id
            )
            if proactive_reminders:
                parts.append(proactive_reminders)

        elapsed = _time.time() - start_time
        total_len = sum(len(p) for p in parts)
        _safe_print(f"[Recall][Engine] ✅ 构建完成: 耗时={elapsed:.3f}s")
        _safe_print(f"[Recall][Engine]    层数={len(parts)}, 总长度={total_len}字符")
        if parts:
            _safe_print(f"[Recall][Engine]    包含: {[p[:20] + '...' for p in parts]}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _adaptive_token_budget(self, query: str, base_max_tokens: int, engine: 'RecallEngine') -> int:
        """Phase 7.4: 自适应 token 预算
        
        根据以下因素动态调整 max_tokens：
        1. LLM 模型的上下文窗口大小
        2. 查询本身的长度（留出回复空间）
        3. 当前记忆库大小（记忆多时需要更大预算）
        4. 场景类型
        
        Args:
            query: 查询文本
            base_max_tokens: 用户指定的基础 max_tokens
            engine: RecallEngine 实例
            
        Returns:
            调整后的 max_tokens
        """
        # v7.0.3: 优先从 RecallConfig 读取（之前散落在 os.environ，默认值未集中管理）
        try:
            from .config import RecallConfig
            _cfg = RecallConfig.from_env()
            llm_context_window = _cfg.llm_context_window
            max_response_tokens = _cfg.llm_max_response_tokens
            adaptive_enabled = _cfg.adaptive_tokens_enabled
            system_prompt_reserve = _cfg.system_prompt_tokens
        except Exception:
            # fallback: 直接读环境变量
            llm_context_window = int(_os.environ.get('LLM_CONTEXT_WINDOW', '8192'))
            max_response_tokens = int(_os.environ.get('LLM_MAX_RESPONSE_TOKENS', '2048'))
            adaptive_enabled = _os.environ.get('ADAPTIVE_TOKENS_ENABLED', 'true').lower() in ('true', '1', 'yes')
            system_prompt_reserve = int(_os.environ.get('SYSTEM_PROMPT_TOKENS', '500'))
        
        if not adaptive_enabled:
            return base_max_tokens
        
        # 1. 估算查询消耗的 token（粗略：中文 ~2 chars/token，英文 ~4 chars/token）
        query_tokens = len(query) // 3  # 取折中值
        
        # 2. 可用预算 = 上下文窗口 - 查询 token - 回复预留 - 系统提示预留
        available = llm_context_window - query_tokens - max_response_tokens - system_prompt_reserve
        
        # 3. 根据记忆库大小调整
        memory_count = 0
        try:
            if hasattr(engine, 'storage'):
                scope = engine.storage.get_scope('default')
                mems = scope.get_all()
                memory_count = len(mems) if mems else 0
        except Exception:
            pass
        
        # 记忆越多，允许更大的预算（但不超过 available）
        if memory_count > 500:
            memory_bonus = min(1000, memory_count // 5)
        elif memory_count > 100:
            memory_bonus = min(500, memory_count // 2)
        else:
            memory_bonus = 0
        
        # 4. 综合计算
        adaptive_budget = max(
            base_max_tokens,                    # 不低于用户指定值
            min(
                available,                      # 不超过可用窗口
                base_max_tokens + memory_bonus  # 基础 + 记忆加成
            )
        )
        
        # 5. 硬性上下限
        MIN_TOKENS = 500
        MAX_TOKENS = min(16000, llm_context_window // 2)
        
        result = max(MIN_TOKENS, min(MAX_TOKENS, adaptive_budget))
        
        if result != base_max_tokens:
            _safe_print(f"[Recall][Adaptive] token 预算: {base_max_tokens} -> {result} "
                       f"(窗口={llm_context_window}, 记忆={memory_count}条)")
        
        return result

    def _calculate_top_k(self, max_tokens: int, strategy: str) -> int:
        """根据策略和token预算计算检索数量"""
        base_k = max(10, min(50, max_tokens // 100))

        # 根据场景调整
        strategy_multipliers = {
            'entity_focused': 1.5,      # 角色扮演需要更多实体信息
            'keyword_exact': 0.8,       # 代码场景精确匹配，不需要太多
            'semantic_broad': 1.2,      # 知识问答需要广泛检索
            'creative_blend': 1.3,      # 创意写作需要多样性
            'task_relevant': 0.7,       # 任务执行聚焦相关
            'recent_context': 0.5,      # 闲聊主要靠最近上下文
            'hybrid_balanced': 1.0,     # 默认平衡
        }

        multiplier = strategy_multipliers.get(strategy, 1.0)
        return int(base_k * multiplier)

    def _build_graph_context(self, query: str, user_id: str, budget: int) -> str:
        """利用知识图谱构建关系上下文"""
        engine = self._engine
        # v7.0.5: 空值守卫 — knowledge_graph 可能为 None
        if not engine.knowledge_graph:
            return ""
        # 从查询中提取实体
        entities = [e.name for e in engine.entity_extractor.extract(query)]
        if not entities:
            return ""

        # 获取当前用户的记忆 ID 集合，用于过滤图谱关系
        user_memory_ids = set()
        try:
            scope = engine.storage.get_scope(user_id)
            for m in scope._memories:
                mid = m.get('metadata', {}).get('id', '')
                if mid:
                    user_memory_ids.add(mid)
        except Exception:
            pass

        lines = []
        current_length = 0

        for entity_name in entities[:5]:  # 最多处理5个实体
            # 获取该实体的关系
            neighbors = engine.knowledge_graph.get_neighbors(entity_name, direction='both')
            if neighbors:
                for neighbor_id, relation in neighbors[:3]:  # 每个实体最多3个关系
                    # 用户隔离：过滤掉不属于当前用户的关系
                    rel_user = getattr(relation, 'user_id', None)
                    rel_memory_ids = getattr(relation, 'memory_ids', None) or getattr(relation, 'source_memory_ids', None)
                    if rel_user and rel_user != user_id and rel_user != 'default':
                        continue
                    if user_memory_ids and rel_memory_ids and not any(mid in user_memory_ids for mid in rel_memory_ids):
                        continue
                    rel_text = f"• {entity_name} --[{relation.relation_type}]--> {neighbor_id}"
                    if current_length + len(rel_text) > budget:
                        break
                    lines.append(rel_text)
                    current_length += len(rel_text)

        if lines:
            return "<relationships>\n【关系图谱】\n" + "\n".join(lines) + "\n</relationships>"
        return ""

    def _build_core_facts_section(self, user_id: str, budget: int) -> str:
        """构建核心事实部分 - 从 L1 ConsolidatedMemory 获取压缩知识

        注意：只返回与当前用户记忆关联的实体，确保用户隔离。
        """
        engine = self._engine

        # 1. 先获取该用户的所有记忆 ID
        user_memory_ids = set()
        try:
            scope = engine.storage.get_scope(user_id)
            all_memories = scope.get_all()
            user_memory_ids = {m.get('metadata', {}).get('id', '') for m in all_memories if m.get('metadata', {}).get('id')}
        except Exception:
            pass

        # 2. 获取所有实体，但只保留与用户记忆关联的
        all_entities = list(engine.consolidated_memory.entities.values()) if hasattr(engine, 'consolidated_memory') else []

        # 过滤：只保留 source_memory_ids 与用户记忆有交集的实体
        if user_memory_ids:
            filtered_entities = [
                e for e in all_entities
                if hasattr(e, 'source_memory_ids') and e.source_memory_ids and
                   any(mid in user_memory_ids for mid in e.source_memory_ids)
            ]
        else:
            # 用户没有记忆，不应该有实体
            filtered_entities = []

        if not filtered_entities:
            # 如果没有整合的记忆，尝试生成摘要
            return self._generate_memory_summary(user_id, budget)

        lines = ["<core_facts>", "【核心知识库】以下是已确认的关键信息："]
        current_length = 0

        # 按置信度排序，优先高置信度的
        sorted_entities = sorted(filtered_entities, key=lambda e: -e.confidence)

        for entity in sorted_entities:
            fact_line = f"• {entity.name}"
            if entity.entity_type != "UNKNOWN":
                fact_line += f" ({entity.entity_type})"
            if entity.current_state:
                states = [f"{k}:{v}" for k, v in list(entity.current_state.items())[:3]]
                fact_line += f": {', '.join(states)}"

            if current_length + len(fact_line) > budget:
                break
            lines.append(fact_line)
            current_length += len(fact_line)

        lines.append("</core_facts>")
        return "\n".join(lines) if len(lines) > 3 else ""

    def _generate_memory_summary(self, user_id: str, budget: int) -> str:
        """生成记忆摘要 - 当没有整合记忆时使用"""
        engine = self._engine
        scope = engine.storage.get_scope(user_id)
        all_memories = scope.get_all(limit=100)  # 获取最多100条

        if not all_memories or len(all_memories) < 5:
            return ""

        # 如果有 LLM，使用 LLM 生成摘要
        if engine.llm_client and engine.memory_summarizer:
            try:
                from .processor.memory_summarizer import MemoryItem
                memory_items = []
                for m in all_memories:
                    memory_items.append(MemoryItem(
                        id=m.get('metadata', {}).get('id', ''),
                        content=m.get('content', ''),
                        user_id=user_id
                    ))
                summary = engine.memory_summarizer.summarize_memories(memory_items, max_length=budget)
                if summary:
                    return f"<memory_summary>\n【历史摘要】\n{summary}\n</memory_summary>"
            except Exception as e:
                pass  # 静默失败，使用备用方案

        # 备用方案：简单提取关键词和实体
        entities_set = set()
        for m in all_memories:
            entities = m.get('metadata', {}).get('entities', [])
            entities_set.update(entities)

        if entities_set:
            return f"<memory_summary>\n【涉及的角色/事物】{', '.join(list(entities_set)[:20])}\n</memory_summary>"

        return ""

    def _build_memory_section(self, memories, budget: int) -> str:
        """构建详细记忆部分（自动去重）"""
        if not memories:
            return ""

        lines = ["<memories>", "【相关记忆】"]
        current_length = 0
        seen_contents = set()  # 用于去重

        for m in memories:
            content = m.content if hasattr(m, 'content') else m.get('content', '')

            # 去重：跳过已经添加过的相同内容
            content_key = content.strip().lower()
            if content_key in seen_contents:
                continue
            seen_contents.add(content_key)

            entities = m.entities if hasattr(m, 'entities') else m.get('entities', [])

            line = f"• {content}"
            if entities:
                line = f"• [涉及: {', '.join(entities[:3])}] {content}"

            if current_length + len(line) > budget:
                lines.append("...")
                break
            lines.append(line)
            current_length += len(line)

        lines.append("</memories>")
        return "\n".join(lines) if len(lines) > 3 else ""

    def _build_recent_section(self, recent) -> str:
        """构建最近对话部分"""
        if not recent:
            return ""

        lines = ["<recent_conversation>"]
        for turn in recent:
            role = turn.get('metadata', {}).get('role', 'user')
            content = turn.get('content', '')
            lines.append(f"{role}: {content}")
        lines.append("</recent_conversation>")
        return "\n".join(lines)

    def _extract_supplementary_keywords(
        self,
        user_id: str,
        character_id: str,
        active_contexts: List
    ) -> List[str]:
        """从持久条件和伏笔中提取关键词用于补充检索

        确保重要信息即使在当前 query 中未提及也能被召回

        Args:
            user_id: 用户ID
            character_id: 角色ID
            active_contexts: 活跃的持久条件列表

        Returns:
            List[str]: 关键词列表
        """
        engine = self._engine
        keywords = set()

        # 从持久条件中提取关键词
        if active_contexts:
            for ctx in active_contexts:
                # 获取关键词
                ctx_keywords = ctx.keywords if hasattr(ctx, 'keywords') else ctx.get('keywords', [])
                if ctx_keywords:
                    keywords.update(ctx_keywords[:3])  # 每个条件最多取3个关键词

        # 从活跃伏笔中提取关键实体
        try:
            foreshadowings = engine.foreshadowing_tracker.get_active(user_id, character_id)
            for fsh in foreshadowings[:5]:  # 最多5个伏笔
                entities = fsh.related_entities if hasattr(fsh, 'related_entities') else []
                if entities:
                    keywords.update(entities[:2])  # 每个伏笔最多取2个实体
        except Exception:
            pass

        return list(keywords)[:10]  # 总共最多10个关键词

    def _search_by_keywords(
        self,
        keywords: List[str],
        user_id: str,
        top_k: int = 5
    ) -> List:
        """根据关键词列表进行补充检索

        Args:
            keywords: 关键词列表
            user_id: 用户ID
            top_k: 返回的最大记忆数

        Returns:
            List: 相关记忆列表
        """
        engine = self._engine
        if not keywords:
            return []

        all_memories = []
        seen_ids = set()

        for keyword in keywords[:5]:  # 最多使用5个关键词
            try:
                memories = engine.search(keyword, user_id=user_id, top_k=2)
                for m in memories:
                    mem_id = m.id if hasattr(m, 'id') else m.get('id', '')
                    if mem_id and mem_id not in seen_ids:
                        seen_ids.add(mem_id)
                        all_memories.append(m)
                        if len(all_memories) >= top_k:
                            return all_memories
            except Exception:
                continue

        return all_memories

    def _build_supplementary_section(self, memories) -> str:
        """构建补充检索记忆部分

        Args:
            memories: 补充检索到的记忆列表

        Returns:
            str: 格式化的补充记忆文本
        """
        if not memories:
            return ""

        lines = ["<supplementary_memories>", "【相关背景（补充召回）】"]

        for m in memories[:5]:  # 最多5条
            content = m.content if hasattr(m, 'content') else m.get('content', '')
            entities = m.entities if hasattr(m, 'entities') else m.get('entities', [])

            line = f"• {content}"
            if entities:
                line = f"• [涉及: {', '.join(entities[:3])}] {content}"
            lines.append(line)

        lines.append("</supplementary_memories>")
        return "\n".join(lines) if len(lines) > 3 else ""

    def _build_proactive_reminders(
        self,
        active_contexts: List,
        threshold_turns: int,
        user_id: str
    ) -> str:
        """构建主动提醒文本（对长期未提及的重要持久条件）

        类似于伏笔的主动提醒机制，确保重要背景信息不会被遗忘

        Args:
            active_contexts: 活跃的持久条件列表
            threshold_turns: 触发提醒的轮次阈值
            user_id: 用户ID

        Returns:
            str: 主动提醒文本，如果没有需要提醒的内容则返回空字符串
        """
        engine = self._engine
        if not active_contexts:
            return ""

        # 获取当前总轮次
        current_turn = 0
        if engine.volume_manager:
            current_turn = engine.volume_manager.get_total_turns()

        reminders = []

        for ctx in active_contexts:
            # 获取最后提及轮次 - PersistentContext 是 dataclass，使用 getattr
            last_mentioned = getattr(ctx, 'last_mentioned_turn', None) or getattr(ctx, 'use_count', 0)
            importance = getattr(ctx, 'importance', None) or getattr(ctx, 'confidence', 0.5)
            content = getattr(ctx, 'content', '')

            # 计算未提及的轮次数
            turns_since_mention = current_turn - last_mentioned if last_mentioned else current_turn

            # 高重要性条件阈值减半
            effective_threshold = threshold_turns // 2 if importance > 0.7 else threshold_turns

            if turns_since_mention >= effective_threshold and importance >= 0.5:
                reminders.append({
                    'content': content,
                    'importance': importance,
                    'turns_since': turns_since_mention
                })

        if not reminders:
            return ""

        # 按重要性和未提及时长排序
        reminders.sort(key=lambda x: (x['importance'], x['turns_since']), reverse=True)

        lines = [
            "<proactive_reminders>",
            "【重要背景提醒】以下是你可能需要注意的重要背景信息（长期未在对话中涉及）："
        ]

        for r in reminders[:3]:  # 最多提醒3条
            importance_label = "高" if r['importance'] > 0.7 else "中"
            lines.append(f"• [{importance_label}重要性，{r['turns_since']}轮未提及] {r['content']}")

        lines.append("</proactive_reminders>")
        return "\n".join(lines)
