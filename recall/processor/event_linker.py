"""事件关联器 - Recall 7.3 Phase B

自动将新事件关联到相关的现有事件:
1. 从新事件中提取实体
2. 搜索含有相同实体的现有事件
3. Embedding 预过滤 (>0.7 相似度) → 100 候选 → 5-10
4. LLM 判断关系类型 (CAUSED/FOLLOWS/RELATED/UNRELATED)
5. 自动在知识图谱中添加边

窗口策略: 24h → 7d → 30d → 365d 自动扩展 (候选 < 3 时)
因果链: 预算约束检索 (max_depth<=20, max_nodes<=200, max_latency_ms<=800)
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any, TYPE_CHECKING
from collections import defaultdict

if TYPE_CHECKING:
    from ..engine import RecallEngine

logger = logging.getLogger(__name__)


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


# ==================== 常量 ====================

# 关系类型
RELATION_CAUSED = "CAUSED"          # A 导致了 B
RELATION_FOLLOWS = "FOLLOWS"        # A 在 B 之后发生
RELATION_RELATED = "RELATED_TO"     # A 与 B 相关
RELATION_UNRELATED = "UNRELATED"    # 不相关（不建边）

# 有效的事件关系类型（会写入图谱的）
VALID_EVENT_RELATIONS = {RELATION_CAUSED, RELATION_FOLLOWS, RELATION_RELATED}

# 窗口策略（候选不足时自动扩展）
WINDOW_STAGES = [
    timedelta(hours=24),
    timedelta(days=7),
    timedelta(days=30),
    timedelta(days=365),
]

# 预算约束
DEFAULT_MAX_DEPTH = 20
DEFAULT_MAX_NODES = 200
DEFAULT_MAX_LATENCY_MS = 800

# 预过滤阈值
EMBEDDING_SIMILARITY_THRESHOLD = 0.7
MAX_CANDIDATES_PRE_FILTER = 100
MAX_CANDIDATES_LLM = 10
MIN_CANDIDATES_BEFORE_EXPAND = 3


# ==================== 数据类 ====================

@dataclass
class EventLink:
    """事件关联结果"""
    source_id: str              # 源事件 ID
    target_id: str              # 目标事件 ID
    relation_type: str          # 关系类型: CAUSED/FOLLOWS/RELATED_TO
    confidence: float           # 置信度 (0-1)
    reason: str                 # 关联原因说明
    shared_entities: List[str] = field(default_factory=list)  # 共享实体
    window_stage: int = 0       # 使用的窗口阶段
    created_at: str = ""        # 创建时间

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "shared_entities": self.shared_entities,
            "window_stage": self.window_stage,
            "created_at": self.created_at,
        }


@dataclass
class ChainNode:
    """因果链节点"""
    event_id: str
    content: str
    depth: int
    relation_from_parent: str = ""    # 从父节点到此节点的关系类型
    confidence: float = 0.0
    timestamp: str = ""
    entities: List[str] = field(default_factory=list)
    children: List['ChainNode'] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "content": self.content[:200],
            "depth": self.depth,
            "relation_from_parent": self.relation_from_parent,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "entities": self.entities,
            "children": [c.to_dict() for c in self.children],
        }

    def flatten(self) -> List['ChainNode']:
        """扁平化整棵子树"""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result


@dataclass
class _Candidate:
    """内部: 候选事件"""
    memory_id: str
    content: str
    score: float           # embedding 相似度
    entities: List[str]
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== 主类 ====================

class EventLinker:
    """事件关联器

    自动将新事件与现有事件建立因果/时序/相关关系。
    支持 embedding 预过滤 + LLM 判断 + 知识图谱写入。
    """

    def __init__(
        self,
        embedding_similarity_threshold: float = EMBEDDING_SIMILARITY_THRESHOLD,
        max_candidates_pre_filter: int = MAX_CANDIDATES_PRE_FILTER,
        max_candidates_llm: int = MAX_CANDIDATES_LLM,
        min_candidates_expand: int = MIN_CANDIDATES_BEFORE_EXPAND,
    ):
        self.embedding_threshold = embedding_similarity_threshold
        self.max_pre_filter = max_candidates_pre_filter
        self.max_llm = max_candidates_llm
        self.min_expand = min_candidates_expand

    # ==================== 公共 API ====================

    def link(
        self,
        memory_id: str,
        content: str,
        entities: List[str],
        engine: 'RecallEngine',
        user_id: str = "default",
    ) -> List[EventLink]:
        """将新事件关联到现有事件

        Args:
            memory_id: 新事件的 memory_id
            content: 新事件内容
            entities: 新事件中的实体列表
            engine: RecallEngine 实例
            user_id: 用户 ID

        Returns:
            建立的 EventLink 列表
        """
        start_time = time.time()
        links: List[EventLink] = []

        try:
            # 1. 搜索候选事件（窗口自动扩展）
            candidates = self._search_candidates(
                content=content,
                entities=entities,
                engine=engine,
                user_id=user_id,
                exclude_id=memory_id,
            )

            if not candidates:
                return links

            # 2. LLM 判断关系（如果 LLM 可用）
            if engine.llm_client:
                relations = self._llm_judge_relations(
                    source_content=content,
                    source_entities=entities,
                    candidates=candidates,
                    llm_client=engine.llm_client,
                )
            else:
                # 无 LLM: 基于共享实体和相似度的启发式判断
                relations = self._heuristic_judge(
                    source_entities=entities,
                    candidates=candidates,
                )

            # 3. 写入图谱
            for cand, rel_type, conf, reason in relations:
                if rel_type in VALID_EVENT_RELATIONS:
                    shared = list(set(entities) & set(cand.entities))
                    link = EventLink(
                        source_id=memory_id,
                        target_id=cand.memory_id,
                        relation_type=rel_type,
                        confidence=conf,
                        reason=reason,
                        shared_entities=shared,
                    )
                    self._write_to_graph(link, engine)
                    links.append(link)

            elapsed = (time.time() - start_time) * 1000
            if links:
                _safe_print(
                    f"[EventLinker] 建立 {len(links)} 条事件关联 "
                    f"(candidates={len(candidates)}, {elapsed:.0f}ms)"
                )

        except Exception as e:
            logger.error(f"[EventLinker] link 失败: {e}", exc_info=True)

        return links

    def link_batch(
        self,
        items: List[Dict[str, Any]],
        engine: 'RecallEngine',
        user_id: str = "default",
    ) -> List[EventLink]:
        """批量关联事件

        Args:
            items: 列表，每项包含 { 'memory_id', 'content', 'entities' }
            engine: RecallEngine 实例
            user_id: 用户 ID

        Returns:
            所有建立的 EventLink 列表
        """
        all_links: List[EventLink] = []
        for item in items:
            mid = item.get("memory_id", "")
            content = item.get("content", "")
            entities = item.get("entities", [])
            if mid and content:
                links = self.link(
                    memory_id=mid,
                    content=content,
                    entities=entities,
                    engine=engine,
                    user_id=user_id,
                )
                all_links.extend(links)
        return all_links

    def unlink(
        self,
        memory_id: str,
        engine: Optional['RecallEngine'] = None,
    ) -> int:
        """移除与指定 memory_id 相关的所有事件关联（delete cascade 用）
        
        v7.0.3: 之前缺失此方法，导致 delete() 级联清理时 EventLinker 的关联边
        无法被清理，产生幽灵关联。

        Args:
            memory_id: 要取消关联的 memory_id
            engine: RecallEngine 实例（用于访问图谱）

        Returns:
            清理的关联数量
        """
        removed = 0
        try:
            if engine is None:
                return 0
            
            # 从图谱中清理与此 memory_id 相关的事件关联边
            graph = getattr(engine, 'temporal_graph', None) or getattr(engine, 'knowledge_graph', None)
            if graph is None:
                return 0
            
            edges_to_expire = []
            if hasattr(graph, 'edges'):
                event_relation_types = {'CAUSED', 'FOLLOWS', 'RELATED', 'EVENT_LINK', 
                                       'CAUSED_BY', 'PRECEDED_BY', 'CONCURRENT'}
                for eid, edge in graph.edges.items():
                    ep = getattr(edge, 'properties', {}) or {}
                    src = getattr(edge, 'source_id', '')
                    tgt = getattr(edge, 'target_id', '')
                    rel_type = getattr(edge, 'relation_type', '') or ep.get('relation_type', '')
                    
                    # 匹配 memory_id 作为源或目标
                    if (src == memory_id or tgt == memory_id or
                        ep.get('source_memory_id') == memory_id or 
                        ep.get('target_memory_id') == memory_id):
                        if rel_type in event_relation_types:
                            edges_to_expire.append(eid)
                
                for eid in edges_to_expire:
                    edge = graph.edges.get(eid)
                    if edge and hasattr(edge, 'expire'):
                        edge.expire()
                        removed += 1
            
            if removed > 0:
                logger.info(f"[EventLinker] unlink: memory_id={memory_id}, removed={removed} edges")
        except Exception as e:
            logger.error(f"[EventLinker] unlink 失败: {e}", exc_info=True)
        
        return removed

    def get_event_chain(
        self,
        event_id: str,
        engine: 'RecallEngine',
        user_id: str = "default",
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_latency_ms: int = DEFAULT_MAX_LATENCY_MS,
        relation_types: Optional[Set[str]] = None,
    ) -> List[ChainNode]:
        """获取事件因果链（BFS 遍历）

        Args:
            event_id: 起始事件 ID
            engine: RecallEngine 实例
            user_id: 用户 ID
            max_depth: 最大深度
            max_nodes: 最大节点数
            max_latency_ms: 最大延迟（毫秒）
            relation_types: 要遍历的关系类型集合，None 表示所有事件关系

        Returns:
            根节点列表（森林结构）
        """
        start_time = time.time()
        if relation_types is None:
            relation_types = VALID_EVENT_RELATIONS

        # BFS 遍历
        visited: Set[str] = set()
        nodes_map: Dict[str, ChainNode] = {}
        roots: List[ChainNode] = []

        # 获取起始节点内容
        root_content = self._get_memory_content(event_id, engine, user_id)
        root_node = ChainNode(
            event_id=event_id,
            content=root_content or "",
            depth=0,
            entities=self._get_memory_entities(event_id, engine, user_id),
        )
        nodes_map[event_id] = root_node
        roots.append(root_node)
        visited.add(event_id)

        # BFS 队列: (node, depth)
        queue: List[Tuple[ChainNode, int]] = [(root_node, 0)]
        node_count = 1

        while queue:
            # 预算检查
            elapsed_ms = (time.time() - start_time) * 1000
            if elapsed_ms > max_latency_ms:
                logger.info(
                    f"[EventLinker] 因果链遍历超时 ({elapsed_ms:.0f}ms > {max_latency_ms}ms)"
                )
                break
            if node_count >= max_nodes:
                logger.info(f"[EventLinker] 因果链节点数达上限 ({max_nodes})")
                break

            current_node, current_depth = queue.pop(0)
            if current_depth >= max_depth:
                continue

            # 查找图谱中的出边
            neighbors = self._get_graph_neighbors(
                current_node.event_id, engine, relation_types
            )

            for neighbor_id, rel_type, confidence in neighbors:
                if neighbor_id in visited:
                    continue
                if node_count >= max_nodes:
                    break

                visited.add(neighbor_id)
                neighbor_content = self._get_memory_content(neighbor_id, engine, user_id)
                child = ChainNode(
                    event_id=neighbor_id,
                    content=neighbor_content or "",
                    depth=current_depth + 1,
                    relation_from_parent=rel_type,
                    confidence=confidence,
                    entities=self._get_memory_entities(neighbor_id, engine, user_id),
                )
                current_node.children.append(child)
                nodes_map[neighbor_id] = child
                node_count += 1
                queue.append((child, current_depth + 1))

        elapsed = (time.time() - start_time) * 1000
        _safe_print(
            f"[EventLinker] 因果链: depth_max={max_depth}, "
            f"nodes={node_count}, {elapsed:.0f}ms"
        )
        return roots

    # ==================== 候选搜索 ====================

    def _search_candidates(
        self,
        content: str,
        entities: List[str],
        engine: 'RecallEngine',
        user_id: str,
        exclude_id: str = "",
    ) -> List[_Candidate]:
        """搜索候选事件，窗口自动扩展"""
        all_candidates: List[_Candidate] = []

        for stage_idx, window in enumerate(WINDOW_STAGES):
            # 使用 engine.search 获取候选
            try:
                results = engine.search(
                    query=content[:500],  # 截断过长内容
                    user_id=user_id,
                    top_k=self.max_pre_filter,
                )
            except Exception as e:
                logger.warning(f"[EventLinker] 搜索候选失败: {e}")
                break

            now_ts = time.time()
            window_start_ts = now_ts - window.total_seconds()

            for r in results:
                if r.id == exclude_id:
                    continue
                # 检查时间窗口
                mem_ts = r.metadata.get("timestamp", 0)
                if isinstance(mem_ts, str):
                    try:
                        mem_ts = datetime.fromisoformat(mem_ts).timestamp()
                    except (ValueError, TypeError):
                        mem_ts = 0
                if mem_ts and mem_ts < window_start_ts:
                    continue

                # 相似度门槛
                if r.score >= self.embedding_threshold:
                    cand = _Candidate(
                        memory_id=r.id,
                        content=r.content,
                        score=r.score,
                        entities=r.entities or [],
                        timestamp=mem_ts if isinstance(mem_ts, (int, float)) else 0,
                        metadata=r.metadata,
                    )
                    all_candidates.append(cand)

            # 去重
            seen_ids = set()
            deduped: List[_Candidate] = []
            for c in all_candidates:
                if c.memory_id not in seen_ids:
                    seen_ids.add(c.memory_id)
                    deduped.append(c)
            all_candidates = deduped

            # 候选是否足够
            if len(all_candidates) >= self.min_expand:
                break

        # 按相似度排序，截取 top LLM 候选
        all_candidates.sort(key=lambda c: -c.score)
        return all_candidates[:self.max_llm]

    # ==================== LLM 判断 ====================

    def _llm_judge_relations(
        self,
        source_content: str,
        source_entities: List[str],
        candidates: List[_Candidate],
        llm_client: Any,
    ) -> List[Tuple[_Candidate, str, float, str]]:
        """使用 LLM 判断源事件和候选事件之间的关系

        Returns:
            List of (candidate, relation_type, confidence, reason)
        """
        results: List[Tuple[_Candidate, str, float, str]] = []

        # 构建候选描述
        cand_desc = []
        for i, c in enumerate(candidates):
            entities_str = ", ".join(c.entities[:5]) if c.entities else "无"
            cand_desc.append(f"[{i}] {c.content[:150]}... (实体: {entities_str})")

        prompt = (
            "你是一个事件关联分析专家。请判断「源事件」与每个「候选事件」之间的关系。\n\n"
            f"源事件: {source_content[:300]}\n"
            f"源事件实体: {', '.join(source_entities[:10])}\n\n"
            "候选事件:\n" + "\n".join(cand_desc) + "\n\n"
            "对每个候选，请判断关系类型（只能选以下之一）:\n"
            "- CAUSED: 源事件导致了候选事件（或反之）\n"
            "- FOLLOWS: 源事件在候选事件之后发生（时序关系）\n"
            "- RELATED_TO: 有主题/实体关联但无因果\n"
            "- UNRELATED: 不相关\n\n"
            "请严格按以下格式回答（每行一个，不加其他文字）:\n"
            "[编号] 关系类型 置信度(0-1) 原因\n"
            "例如:\n"
            "[0] CAUSED 0.85 用户搬家导致了地址变更\n"
            "[1] UNRELATED 0.9 两事件无关联\n"
        )

        try:
            response = llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            lines = response.content.strip().split("\n")
            pattern = re.compile(
                r'\[(\d+)\]\s*(CAUSED|FOLLOWS|RELATED_TO|UNRELATED)\s+([\d.]+)\s*(.*)'
            )
            for line in lines:
                m = pattern.match(line.strip())
                if m:
                    idx = int(m.group(1))
                    rel_type = m.group(2)
                    conf = float(m.group(3))
                    reason = m.group(4).strip()
                    if 0 <= idx < len(candidates):
                        results.append((candidates[idx], rel_type, min(conf, 1.0), reason))
        except Exception as e:
            logger.warning(f"[EventLinker] LLM 判断失败: {e}")
            # 回退到启发式
            results = self._heuristic_judge(source_entities, candidates)

        return results

    def _heuristic_judge(
        self,
        source_entities: List[str],
        candidates: List[_Candidate],
    ) -> List[Tuple[_Candidate, str, float, str]]:
        """启发式关系判断（无 LLM 时的回退方案）"""
        results: List[Tuple[_Candidate, str, float, str]] = []
        source_set = set(e.lower() for e in source_entities)

        for cand in candidates:
            cand_set = set(e.lower() for e in cand.entities)
            shared = source_set & cand_set

            if len(shared) == 0 and cand.score < 0.8:
                # 无共享实体且相似度低 → 不关联
                continue

            # 根据共享实体数量和相似度决定关系
            if len(shared) >= 3 and cand.score >= 0.85:
                rel_type = RELATION_FOLLOWS
                conf = min(0.7, cand.score)
                reason = f"共享实体 ({', '.join(list(shared)[:3])}) + 高相似度"
            elif len(shared) >= 1 and cand.score >= 0.75:
                rel_type = RELATION_RELATED
                conf = min(0.6, cand.score)
                reason = f"共享实体 ({', '.join(list(shared)[:3])})"
            elif cand.score >= 0.85:
                rel_type = RELATION_RELATED
                conf = 0.5
                reason = f"高语义相似度 ({cand.score:.2f})"
            else:
                continue

            results.append((cand, rel_type, conf, reason))

        return results

    # ==================== 图谱写入 ====================

    def _write_to_graph(self, link: EventLink, engine: 'RecallEngine') -> bool:
        """将事件关联写入知识图谱"""
        try:
            if hasattr(engine, 'knowledge_graph') and engine.knowledge_graph:
                engine.knowledge_graph.add_relation(
                    source_id=link.source_id,
                    target_id=link.target_id,
                    relation_type=link.relation_type,
                    properties={
                        "link_type": "event_link",
                        "confidence": link.confidence,
                        "reason": link.reason,
                        "shared_entities": link.shared_entities,
                    },
                    confidence=link.confidence,
                    source_text=link.reason,
                )
                return True
        except Exception as e:
            logger.warning(f"[EventLinker] 图谱写入失败: {e}")
        return False

    # ==================== 图谱查询 ====================

    def _get_graph_neighbors(
        self,
        event_id: str,
        engine: 'RecallEngine',
        relation_types: Set[str],
    ) -> List[Tuple[str, str, float]]:
        """获取事件在图谱中的邻居

        Returns:
            List of (neighbor_id, relation_type, confidence)
        """
        neighbors: List[Tuple[str, str, float]] = []
        try:
            if hasattr(engine, 'knowledge_graph') and engine.knowledge_graph:
                graph = engine.knowledge_graph
                # 获取出边
                results = graph.get_neighbors(event_id, direction='out')
                for neighbor_id, rel in results:
                    if rel.relation_type in relation_types:
                        neighbors.append((
                            neighbor_id,
                            rel.relation_type,
                            rel.confidence,
                        ))
                # 同时获取入边（双向遍历）
                results_in = graph.get_neighbors(event_id, direction='in')
                for neighbor_id, rel in results_in:
                    if rel.relation_type in relation_types:
                        neighbors.append((
                            neighbor_id,
                            rel.relation_type,
                            rel.confidence,
                        ))
        except Exception as e:
            logger.debug(f"[EventLinker] 图谱查询失败: {e}")
        return neighbors

    def _get_memory_content(
        self,
        memory_id: str,
        engine: 'RecallEngine',
        user_id: str,
    ) -> Optional[str]:
        """获取记忆内容"""
        try:
            if hasattr(engine, 'storage') and engine.storage:
                scope = engine.storage.get_scope(user_id)
                content = scope.get_content_by_id(memory_id)
                if content:
                    return content
        except Exception:
            pass
        # 回退: 尝试通过内容缓存
        try:
            if hasattr(engine, '_get_memory_content_by_id'):
                return engine._get_memory_content_by_id(memory_id)
        except Exception:
            pass
        return None

    def _get_memory_entities(
        self,
        memory_id: str,
        engine: 'RecallEngine',
        user_id: str,
    ) -> List[str]:
        """获取记忆的实体列表"""
        try:
            if hasattr(engine, 'storage') and engine.storage:
                scope = engine.storage.get_scope(user_id)
                for mem in scope._memories:
                    mid = mem.get('metadata', {}).get('id', '')
                    if mid == memory_id:
                        return mem.get('metadata', {}).get('entities', [])
        except Exception:
            pass
        return []
