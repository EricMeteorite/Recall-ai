"""持久上下文追踪器 - 追踪和管理持久性前提条件

这个模块解决的问题：
- 某些信息一旦确立，就应该成为后续所有对话的"默认前提条件"
- 比如"用户是大学毕业生想创业" —— 后续所有建议都基于这个前提
- 比如"Windows开发，Ubuntu部署" —— 后续所有代码建议都基于这个环境

核心概念：
- PersistentContext: 持久性上下文/条件
- 不同于伏笔（未解决的线索），这是已确立的背景设定
- 不同于普通记忆（需要检索），这是每次对话都应该自动包含的前提

智能去重机制（v3.0.1 新增）：
- 第一级：Embedding 向量余弦相似度快速筛选
- 第二级：LLM 提取时顺带判断是否与已有条件重复
- 第三级：定期批量整理合并
"""

import os
import json
import time
import re
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


class ContextType(Enum):
    """上下文类型"""
    # 用户身份相关
    USER_IDENTITY = "user_identity"      # 用户身份（如：大学毕业生、程序员）
    USER_GOAL = "user_goal"              # 用户目标（如：想创业、学习Python）
    USER_PREFERENCE = "user_preference"  # 用户偏好（如：喜欢简洁的解释）
    
    # 环境相关
    ENVIRONMENT = "environment"          # 技术环境（如：Windows开发、Ubuntu部署）
    PROJECT = "project"                  # 项目信息（如：正在开发Recall-ai）
    TIME_CONSTRAINT = "time_constraint"  # 时间约束（如：截止日期、特定时间段）
    
    # 角色扮演相关
    CHARACTER_TRAIT = "character_trait"  # 角色特征（如：角色性格设定）
    WORLD_SETTING = "world_setting"      # 世界观设定（如：魔法世界）
    RELATIONSHIP = "relationship"        # 关系设定（如：用户是角色的朋友）
    EMOTIONAL_STATE = "emotional_state"  # 情绪状态（如：角色当前心情）
    SKILL_ABILITY = "skill_ability"      # 技能能力（如：角色会什么技能）
    ITEM_PROP = "item_prop"              # 物品道具（如：角色携带的物品）
    
    # 通用
    ASSUMPTION = "assumption"            # 假设前提
    CONSTRAINT = "constraint"            # 约束条件
    CUSTOM = "custom"                    # 自定义


@dataclass
class PersistentContext:
    """持久性上下文/条件"""
    id: str
    content: str                         # 条件内容
    context_type: ContextType            # 条件类型
    user_id: str = "default"
    
    # 元信息
    created_at: float = field(default_factory=time.time)
    source_turn: Optional[str] = None    # 来源记忆ID
    confidence: float = 0.8              # 置信度
    
    # 生命周期
    is_active: bool = True               # 是否活跃
    expires_at: Optional[float] = None   # 过期时间（None=永不过期）
    last_used: float = field(default_factory=time.time)
    use_count: int = 0
    
    # 关联
    related_entities: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    # 智能去重 - Embedding 向量缓存（可选字段，向后兼容）
    # 存储为 list 以便 JSON 序列化，使用时转换为 numpy array
    _embedding: Optional[List[float]] = field(default=None, repr=False)
    
    @property
    def embedding(self) -> Optional[np.ndarray]:
        """获取 embedding 向量（numpy array）"""
        if self._embedding is not None:
            return np.array(self._embedding, dtype='float32')
        return None
    
    @embedding.setter
    def embedding(self, value):
        """设置 embedding 向量"""
        if value is not None:
            if isinstance(value, np.ndarray):
                self._embedding = value.tolist()
            else:
                self._embedding = list(value)
        else:
            self._embedding = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['context_type'] = self.context_type.value
        # _embedding 字段在 asdict 中会自动包含
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PersistentContext':
        data = data.copy()  # 避免修改原始数据
        data['context_type'] = ContextType(data['context_type'])
        # 兼容旧数据（没有 _embedding 字段）
        if '_embedding' not in data:
            data['_embedding'] = None
        return cls(**data)


class ContextTracker:
    """持久上下文追踪器
    
    增长控制策略：
    1. 每个类型最多保留 max_per_type 个条件（默认5个）
    2. 相似内容自动合并（增加置信度而非新增）- 使用 Embedding 语义相似度
    3. 置信度衰减：长期未被引用的条件置信度下降
    4. 超出数量时，淘汰置信度最低的
    5. 有LLM时，可以智能压缩多个条件
    
    智能去重机制：
    - 第一级：Embedding 向量余弦相似度（>0.85 直接合并，0.70-0.85 可能相似）
    - 第二级：LLM 提取时判断是否与已有条件重复
    - 第三级：定期批量整理合并
    """
    
    # 配置常量
    MAX_PER_TYPE = 5          # 每类型最多保留5个条件
    MAX_TOTAL = 30            # 总数最多30个
    DECAY_DAYS = 7            # 7天未使用开始衰减
    DECAY_RATE = 0.1          # 每次衰减10%置信度
    MIN_CONFIDENCE = 0.2      # 最低置信度，低于此自动删除
    SIMILARITY_THRESHOLD = 0.6  # 词重叠相似度阈值（后备方案）
    
    # 智能去重配置（从环境变量读取，支持热更新）
    @staticmethod
    def _get_dedup_config() -> Dict[str, Any]:
        """获取去重配置（每次调用时读取，支持热更新）
        
        Returns:
            Dict with keys: enabled, high_threshold, low_threshold
        """
        return {
            'enabled': os.environ.get('DEDUP_EMBEDDING_ENABLED', 'true').lower() in ('true', '1', 'yes'),
            'high_threshold': float(os.environ.get('DEDUP_HIGH_THRESHOLD', '0.85')),
            'low_threshold': float(os.environ.get('DEDUP_LOW_THRESHOLD', '0.70'))
        }
    
    def __init__(self, storage_dir: str, llm_client: Optional[Any] = None, 
                 embedding_backend: Optional[Any] = None):
        """初始化持久上下文追踪器
        
        Args:
            storage_dir: 存储目录
            llm_client: LLM 客户端（用于智能提取和压缩）
            embedding_backend: Embedding 后端（用于智能去重），如果为 None 会尝试自动获取
        """
        self.storage_dir = storage_dir
        self.llm_client = llm_client
        self.contexts: Dict[str, List[PersistentContext]] = {}  # user_id -> contexts
        
        # Embedding 后端（用于智能去重）
        self.embedding_backend = embedding_backend
        
        os.makedirs(storage_dir, exist_ok=True)
        self._load_all()
        
        # 条件检测模式（用于自动从对话中提取条件）
        # 使用更精确的模式，避免误匹配
        self.detection_patterns = {
            ContextType.USER_IDENTITY: [
                r'我是(?:一个|一名|一位)?([^，。,.\n]{2,20}?)(?:，|。|,|\.|$)',  # 我是XXX
                r'我目前是(?:一个|一名)?([^，。,.\n]{2,20}?)(?:，|。|,|\.|$)',   # 我目前是XXX
            ],
            ContextType.USER_GOAL: [
                r'我想(?:要)?(?:学习|做|开发|创建|实现|完成)([^，。,.\n]{2,30}?)(?:，|。|,|\.|$)',  # 我想做XXX
                r'我的目标是([^，。,.\n]{2,30}?)(?:，|。|,|\.|$)',  # 我的目标是XXX
                r'我(?:正在|打算|准备)(?:学习|做|开发|创建)([^，。,.\n]{2,30}?)(?:，|。|,|\.|$)',
            ],
            ContextType.ENVIRONMENT: [
                r'(?:我)?在(Windows|Linux|Mac|Ubuntu|CentOS|MacOS)(?:上|系统)?(?:开发|部署|运行)',  # 在Windows上开发
                r'(?:开发|部署|运行)(?:环境|平台)(?:是|用的是)(Windows|Linux|Mac|Ubuntu)',
                r'(Windows|Linux|Mac|Ubuntu)(?:上)?开发.{0,10}?(Windows|Linux|Mac|Ubuntu)(?:上)?部署',  # Windows开发Ubuntu部署
            ],
            ContextType.PROJECT: [
                r'(?:我|我们)(?:正在|在)?(?:开发|做|写)(?:一个|这个)?([^，。,.\n]{2,20}?)(?:项目|系统|程序|应用)',
                r'这个项目(?:是|叫)([^，。,.\n]{2,20}?)(?:，|。|,|\.|$)',
            ],
        }
        
        # 最小匹配长度（避免匹配太短的无意义片段）
        self.min_content_length = 5
        
        # LLM 提取提示
        self.extraction_prompt = """分析以下对话内容，提取出应该作为"持久前提条件"的信息。

持久前提条件是指：一旦确立就应该在后续所有对话中默认成立的背景信息。

例如：
- "我是一个大学毕业生，想创业" → 后续所有建议都应基于这个身份
- "我在Windows上开发，但要部署到Ubuntu" → 后续所有代码建议都应考虑这个环境
- "这个角色是一个冷酷的剑士" → 后续角色行为都应符合这个设定
- "截止日期是下周五" → 所有建议都应考虑这个时间约束
- "角色目前处于愤怒状态" → 后续对话应体现这个情绪
- "角色会治愈魔法" → 后续可以使用这个技能
- "角色携带一把魔法剑" → 后续可以使用这个道具

对话内容：
{content}

请以JSON格式返回提取的条件（如果没有则返回空数组）：
[
  {{"type": "user_identity|user_goal|user_preference|environment|project|time_constraint|character_trait|world_setting|relationship|emotional_state|skill_ability|item_prop|assumption|constraint|custom", "content": "条件内容", "keywords": ["关键词1", "关键词2"]}}
]

只返回JSON，不要其他解释。"""
    
    def _load_all(self):
        """加载所有用户的上下文"""
        if not os.path.exists(self.storage_dir):
            return
        
        for filename in os.listdir(self.storage_dir):
            if filename.endswith('_contexts.json'):
                user_id = filename[:-14]  # 去掉 _contexts.json
                self._load_user(user_id)
    
    def _load_user(self, user_id: str):
        """加载用户的上下文"""
        filepath = os.path.join(self.storage_dir, f'{user_id}_contexts.json')
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.contexts[user_id] = [
                    PersistentContext.from_dict(item) for item in data
                ]
    
    def _save_user(self, user_id: str):
        """保存用户的上下文"""
        filepath = os.path.join(self.storage_dir, f'{user_id}_contexts.json')
        contexts = self.contexts.get(user_id, [])
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump([c.to_dict() for c in contexts], f, ensure_ascii=False, indent=2)
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本的Embedding向量
        
        使用embedding_backend获取向量，失败时返回None
        """
        if not self.embedding_backend:
            return None
        
        try:
            # embedding_backend.embed() 返回 List[List[float]]
            embeddings = self.embedding_backend.embed([text])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"获取Embedding失败: {e}")
        
        return None
    
    def _compute_embedding_similarity(self, emb1: List[float], emb2: List[float]) -> float:
        """计算两个Embedding向量的余弦相似度
        
        使用numpy高效计算，范围 [-1, 1]，通常正常文本相似度在 [0, 1]
        """
        if emb1 is None or emb2 is None:
            return 0.0
        if len(emb1) == 0 or len(emb2) == 0:
            return 0.0
        
        vec1 = np.array(emb1)
        vec2 = np.array(emb2)
        
        # 余弦相似度 = dot(a, b) / (norm(a) * norm(b))
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def _compute_word_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的词重叠相似度（后备方案）
        
        基于Jaccard相似度，支持中英文
        """
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        # 对于中文，按字符
        if len(words1) <= 2:  # 可能是中文
            words1 = set(text1.lower())
            words2 = set(text2.lower())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0
    
    def _compute_similarity(self, text1: str, text2: str, 
                           emb1: Optional[List[float]] = None, 
                           emb2: Optional[List[float]] = None) -> Tuple[float, str]:
        """计算两个文本的语义相似度
        
        三级策略：
        1. 如果两边都有Embedding，使用余弦相似度（最准确）
        2. 如果只有一边有Embedding，尝试获取另一边的
        3. 后备：使用词重叠（兼容旧数据）
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
            emb1: text1的Embedding向量（可选）
            emb2: text2的Embedding向量（可选）
            
        Returns:
            Tuple[float, str]: (相似度, 使用的方法 "embedding"/"word")
        """
        dedup_config = self._get_dedup_config()
        
        # 如果启用了Embedding去重
        if dedup_config['enabled']:
            # 尝试获取缺失的Embedding
            if emb1 is None:
                emb1 = self._get_embedding(text1)
            if emb2 is None:
                emb2 = self._get_embedding(text2)
            
            # 如果两边都有Embedding，使用余弦相似度
            if emb1 is not None and emb2 is not None:
                sim = self._compute_embedding_similarity(emb1, emb2)
                return (sim, "embedding")
        
        # 后备：词重叠
        sim = self._compute_word_similarity(text1, text2)
        return (sim, "word")
    
    def _find_similar(self, content: str, user_id: str, context_type: ContextType,
                     new_embedding: Optional[List[float]] = None) -> Tuple[Optional[PersistentContext], float, str]:
        """查找语义相似的已有条件
        
        使用三级策略：
        1. 完全相同：直接返回
        2. Embedding相似度 >= HIGH_THRESHOLD：高度相似，可自动合并
        3. Embedding相似度 < LOW_THRESHOLD：明显不同，跳过
        4. 中间区域：返回但标记，可能需要LLM判断
        
        Args:
            content: 新条件内容
            user_id: 用户ID
            context_type: 条件类型
            new_embedding: 新条件的Embedding向量（可选，如果提供则避免重复计算）
            
        Returns:
            Tuple[Optional[PersistentContext], float, str]: 
                (相似条件或None, 相似度, 方法 "exact"/"embedding"/"word")
        """
        if user_id not in self.contexts:
            return (None, 0.0, "none")
        
        dedup_config = self._get_dedup_config()
        best_match: Optional[PersistentContext] = None
        best_sim = 0.0
        best_method = "none"
        
        for existing in self.contexts[user_id]:
            if existing.context_type != context_type:
                continue
            if not existing.is_active:
                continue
            
            # 1. 完全相同（快速路径）
            if existing.content.lower().strip() == content.lower().strip():
                return (existing, 1.0, "exact")
            
            # 2. 计算相似度
            sim, method = self._compute_similarity(
                existing.content, content,
                emb1=existing.embedding,  # 使用已存储的Embedding
                emb2=new_embedding
            )
            
            # 使用动态阈值（Embedding方法用配置的阈值，词重叠用固定阈值）
            if method == "embedding":
                threshold = dedup_config['high_threshold']
            else:
                threshold = self.SIMILARITY_THRESHOLD
            
            # 记录最佳匹配
            if sim > best_sim:
                best_sim = sim
                best_match = existing
                best_method = method
        
        # 判断是否达到合并阈值
        if best_match:
            if best_method == "embedding":
                if best_sim >= dedup_config['high_threshold']:
                    return (best_match, best_sim, best_method)
                elif best_sim < dedup_config['low_threshold']:
                    return (None, best_sim, best_method)  # 明显不同
                else:
                    # 中间区域，返回匹配但需要进一步判断
                    return (best_match, best_sim, best_method + "_uncertain")
            else:
                # 词重叠方法，使用固定阈值
                if best_sim >= self.SIMILARITY_THRESHOLD:
                    return (best_match, best_sim, best_method)
        
        return (None, best_sim, best_method)
    
    def _enforce_limits(self, user_id: str):
        """强制执行数量限制"""
        if user_id not in self.contexts:
            return
        
        contexts = self.contexts[user_id]
        
        # 1. 应用置信度衰减
        now = time.time()
        decay_threshold = now - (self.DECAY_DAYS * 24 * 3600)
        
        for ctx in contexts:
            if ctx.is_active and ctx.last_used < decay_threshold:
                ctx.confidence = max(self.MIN_CONFIDENCE, ctx.confidence - self.DECAY_RATE)
        
        # 2. 删除置信度太低且不活跃的，以及置信度低于阈值的（即使活跃也标记为不活跃）
        for ctx in contexts:
            if ctx.confidence < self.MIN_CONFIDENCE:
                ctx.is_active = False
        
        # 只保留活跃的
        contexts = [c for c in contexts if c.is_active]
        
        # 3. 每类型数量限制
        by_type: Dict[ContextType, List[PersistentContext]] = {}
        for ctx in contexts:
            if ctx.context_type not in by_type:
                by_type[ctx.context_type] = []
            by_type[ctx.context_type].append(ctx)
        
        # 每类型只保留置信度最高的 MAX_PER_TYPE 个
        kept = []
        for ctx_type, type_contexts in by_type.items():
            # 按置信度排序
            type_contexts.sort(key=lambda c: -c.confidence)
            kept.extend(type_contexts[:self.MAX_PER_TYPE])
        
        # 4. 总数限制
        if len(kept) > self.MAX_TOTAL:
            kept.sort(key=lambda c: -c.confidence)
            kept = kept[:self.MAX_TOTAL]
        
        self.contexts[user_id] = kept
    
    def add(self, content: str, context_type: ContextType, user_id: str = "default",
            source_turn: str = None, keywords: List[str] = None,
            related_entities: List[str] = None) -> PersistentContext:
        """添加持久上下文
        
        智能处理（三级去重策略）：
        1. 计算新内容的Embedding（如果启用）
        2. 查找语义相似的已有条件
        3. 高相似度：自动合并（增加置信度）
        4. 中等相似度：谨慎合并（如果内容更详细则更新）
        5. 低相似度或无匹配：创建新条件
        6. 超出数量限制时，淘汰置信度最低的
        
        注意：如果该类型已达到上限且新条件置信度不够高，
        新条件可能会被立即淘汰（但仍会返回该对象，is_active=False）
        """
        import uuid
        import logging
        logger = logging.getLogger(__name__)
        
        if user_id not in self.contexts:
            self.contexts[user_id] = []
        
        # 1. 预计算新内容的Embedding（避免重复计算）
        new_embedding = self._get_embedding(content)
        
        # 2. 检查是否有语义相似的已有条件
        similar, sim_score, sim_method = self._find_similar(
            content, user_id, context_type, new_embedding=new_embedding
        )
        
        if similar:
            # 记录合并日志
            logger.debug(f"[ContextTracker] 发现相似条件 (方法={sim_method}, 相似度={sim_score:.3f}): "
                        f"'{content[:30]}...' ≈ '{similar.content[:30]}...'")
            
            # 合并策略
            if sim_method == "exact":
                # 完全相同，只更新使用信息
                similar.use_count += 1
                similar.last_used = time.time()
            elif sim_method.endswith("_uncertain"):
                # 中等相似度，谨慎合并
                similar.confidence = min(1.0, similar.confidence + 0.05)  # 较小增量
                similar.use_count += 1
                similar.last_used = time.time()
                # 如果新内容明显更长/更详细，用新内容替换
                if len(content) > len(similar.content) * 1.2:
                    similar.content = content
                    # 更新Embedding
                    if new_embedding:
                        similar.embedding = new_embedding
            else:
                # 高度相似，正常合并
                similar.confidence = min(1.0, similar.confidence + 0.1)
                similar.use_count += 1
                similar.last_used = time.time()
                # 如果新内容更长/更详细，用新内容替换
                if len(content) > len(similar.content):
                    similar.content = content
                    # 更新Embedding
                    if new_embedding:
                        similar.embedding = new_embedding
            
            self._save_user(user_id)
            return similar
        
        # 3. 创建新条件
        ctx = PersistentContext(
            id=f"ctx_{uuid.uuid4().hex[:12]}",
            content=content,
            context_type=context_type,
            user_id=user_id,
            source_turn=source_turn,
            keywords=keywords or [],
            related_entities=related_entities or []
        )
        
        # 存储Embedding（如果有）
        if new_embedding:
            ctx.embedding = new_embedding
        
        self.contexts[user_id].append(ctx)
        
        # 4. 强制执行数量限制
        self._enforce_limits(user_id)
        
        # 检查新条件是否被淘汰了
        if ctx not in self.contexts[user_id]:
            # 条件被淘汰了（因为置信度不够高），标记为不活跃
            ctx.is_active = False
            logger.debug(f"[ContextTracker] 新条件因数量限制被淘汰: {content[:50]}...")
        
        self._save_user(user_id)
        return ctx
    
    def get_active(self, user_id: str = "default") -> List[PersistentContext]:
        """获取所有活跃的持久上下文"""
        if user_id not in self.contexts:
            return []
        
        now = time.time()
        active = []
        
        for ctx in self.contexts[user_id]:
            if not ctx.is_active:
                continue
            if ctx.expires_at and ctx.expires_at < now:
                ctx.is_active = False
                continue
            active.append(ctx)
        
        # 按类型和置信度排序
        active.sort(key=lambda c: (-c.confidence, c.context_type.value))
        return active
    
    def get_by_type(self, context_type: ContextType, user_id: str = "default") -> List[PersistentContext]:
        """按类型获取上下文"""
        return [c for c in self.get_active(user_id) if c.context_type == context_type]
    
    def deactivate(self, context_id: str, user_id: str = "default") -> bool:
        """停用某个上下文"""
        if user_id not in self.contexts:
            return False
        
        for ctx in self.contexts[user_id]:
            if ctx.id == context_id:
                ctx.is_active = False
                self._save_user(user_id)
                return True
        return False
    
    def mark_used(self, context_id: str, user_id: str = "default", save: bool = True):
        """标记上下文被使用
        
        Args:
            context_id: 条件ID
            user_id: 用户ID
            save: 是否立即保存（批量操作时设为False，最后统一保存）
        """
        if user_id not in self.contexts:
            return
        
        for ctx in self.contexts[user_id]:
            if ctx.id == context_id:
                ctx.last_used = time.time()
                ctx.use_count += 1
                if save:
                    self._save_user(user_id)
                return
    
    def mark_used_batch(self, context_ids: List[str], user_id: str = "default"):
        """批量标记上下文被使用（只保存一次）"""
        if user_id not in self.contexts or not context_ids:
            return
        
        now = time.time()
        id_set = set(context_ids)  # 转成 set 提高查找效率
        for ctx in self.contexts[user_id]:
            if ctx.id in id_set:
                ctx.last_used = now
                ctx.use_count += 1
        
        self._save_user(user_id)
    
    def extract_from_text(self, text: str, user_id: str = "default") -> List[PersistentContext]:
        """从文本中自动提取持久上下文
        
        优先使用 LLM，如果没有 LLM 则使用规则
        """
        if self.llm_client:
            return self._extract_with_llm(text, user_id)
        else:
            return self._extract_with_rules(text, user_id)
    
    def _extract_with_rules(self, text: str, user_id: str) -> List[PersistentContext]:
        """使用规则提取"""
        extracted = []
        seen_contents = set()  # 避免重复
        
        for context_type, patterns in self.detection_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    # 尝试获取捕获组的内容，否则用整个匹配
                    content = match.group(0).strip()
                    
                    # 清理内容：去除首尾标点
                    content = content.strip('，。,. ')
                    
                    # 跳过太短或重复的内容
                    if len(content) < self.min_content_length:
                        continue
                    
                    content_key = content.lower()
                    if content_key in seen_contents:
                        continue
                    seen_contents.add(content_key)
                    
                    # 对于环境类型，特殊处理：完整记录开发和部署环境
                    if context_type == ContextType.ENVIRONMENT:
                        # 检查是否是"Windows开发Ubuntu部署"这种模式
                        env_match = re.search(
                            r'(Windows|Linux|Mac|Ubuntu)(?:上)?开发.{0,10}?(Windows|Linux|Mac|Ubuntu)(?:上)?部署',
                            text, re.IGNORECASE
                        )
                        if env_match:
                            content = f"开发环境: {env_match.group(1)}, 部署环境: {env_match.group(2)}"
                    
                    ctx = self.add(
                        content=content,
                        context_type=context_type,
                        user_id=user_id
                    )
                    extracted.append(ctx)
        
        return extracted
    
    def _extract_with_llm(self, text: str, user_id: str) -> List[PersistentContext]:
        """使用 LLM 提取"""
        try:
            prompt = self.extraction_prompt.format(content=text)
            response = self.llm_client.complete(prompt, max_tokens=500)
            
            # 解析 JSON
            import json
            # 尝试找到 JSON 数组
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                items = json.loads(json_match.group(0))
                
                extracted = []
                for item in items:
                    try:
                        ctx = self.add(
                            content=item['content'],
                            context_type=ContextType(item['type']),
                            user_id=user_id,
                            keywords=item.get('keywords', [])
                        )
                        extracted.append(ctx)
                    except (KeyError, ValueError):
                        continue
                
                return extracted
        except Exception as e:
            print(f"[ContextTracker] LLM提取失败，回退到规则提取: {e}")
        
        # 回退到规则提取
        return self._extract_with_rules(text, user_id)
    
    def format_for_prompt(self, user_id: str = "default") -> str:
        """格式化为提示词注入"""
        active = self.get_active(user_id)
        if not active:
            return ""
        
        lines = ["<persistent_context>", "【持久前提条件】以下是已确立的背景设定，请在所有回复中默认遵守："]
        
        # 按类型分组
        by_type: Dict[ContextType, List[PersistentContext]] = {}
        for ctx in active:
            if ctx.context_type not in by_type:
                by_type[ctx.context_type] = []
            by_type[ctx.context_type].append(ctx)
        
        type_names = {
            ContextType.USER_IDENTITY: "用户身份",
            ContextType.USER_GOAL: "用户目标",
            ContextType.USER_PREFERENCE: "用户偏好",
            ContextType.ENVIRONMENT: "技术环境",
            ContextType.PROJECT: "项目信息",
            ContextType.TIME_CONSTRAINT: "时间约束",
            ContextType.CHARACTER_TRAIT: "角色特征",
            ContextType.WORLD_SETTING: "世界观",
            ContextType.RELATIONSHIP: "关系设定",
            ContextType.EMOTIONAL_STATE: "情绪状态",
            ContextType.SKILL_ABILITY: "技能能力",
            ContextType.ITEM_PROP: "物品道具",
            ContextType.ASSUMPTION: "假设前提",
            ContextType.CONSTRAINT: "约束条件",
            ContextType.CUSTOM: "其他",
        }
        
        for ctx_type, contexts in by_type.items():
            type_name = type_names.get(ctx_type, ctx_type.value)
            lines.append(f"\n[{type_name}]")
            for ctx in contexts:
                lines.append(f"• {ctx.content}")
        
        lines.append("</persistent_context>")
        return "\n".join(lines)
    
    def get_relevant(self, query: str, user_id: str = "default", top_k: int = 5) -> List[PersistentContext]:
        """获取与查询最相关的上下文"""
        active = self.get_active(user_id)
        if not active:
            return []
        
        query_lower = query.lower()
        scored = []
        
        for ctx in active:
            score = 0
            
            # 关键词匹配
            for kw in ctx.keywords:
                if kw.lower() in query_lower:
                    score += 0.3
            
            # 内容匹配
            if any(word in ctx.content.lower() for word in query_lower.split()):
                score += 0.2
            
            # 实体匹配
            for entity in ctx.related_entities:
                if entity.lower() in query_lower:
                    score += 0.4
            
            # 基础分（所有活跃条件都有一定相关性）
            score += 0.1
            
            scored.append((ctx, score))
        
        # 排序并返回
        scored.sort(key=lambda x: -x[1])
        return [ctx for ctx, score in scored[:top_k]]
    
    def consolidate_contexts(self, user_id: str = "default", force: bool = False) -> int:
        """智能压缩合并相似的持久条件
        
        当条件数量超过阈值或强制执行时，使用LLM将相似条件合并
        
        Returns:
            减少的条件数量
        """
        if user_id not in self.contexts:
            return 0
        
        contexts = [c for c in self.contexts[user_id] if c.is_active]
        original_count = len(contexts)
        
        # 只有条件数量超过阈值或强制执行时才压缩
        if not force and original_count < self.MAX_TOTAL * 0.8:
            return 0
        
        # 按类型分组
        by_type: Dict[ContextType, List[PersistentContext]] = {}
        for ctx in contexts:
            if ctx.context_type not in by_type:
                by_type[ctx.context_type] = []
            by_type[ctx.context_type].append(ctx)
        
        # 对每个类型进行压缩
        for ctx_type, type_contexts in by_type.items():
            if len(type_contexts) <= 2:  # 2个以下不压缩
                continue
            
            if self.llm_client:
                # 使用 LLM 压缩
                self._consolidate_with_llm(type_contexts, ctx_type, user_id)
            else:
                # 简单压缩：保留置信度最高的几个
                type_contexts.sort(key=lambda c: -c.confidence)
                for ctx in type_contexts[self.MAX_PER_TYPE:]:
                    ctx.is_active = False
        
        self._save_user(user_id)
        
        # 计算减少的数量
        new_count = len([c for c in self.contexts[user_id] if c.is_active])
        return original_count - new_count
    
    def _consolidate_with_llm(self, contexts: List[PersistentContext], 
                              ctx_type: ContextType, user_id: str):
        """使用 LLM 压缩合并同类型的条件"""
        try:
            # 构建条件列表
            conditions = "\n".join([f"- {ctx.content}" for ctx in contexts])
            
            prompt = f"""你需要将以下同类型的条件合并压缩，保留关键信息，去除冗余。

条件类型: {ctx_type.value}
当前条件：
{conditions}

请将这些条件合并成不超过{self.MAX_PER_TYPE}条核心条件。
输出格式（JSON数组）:
[
  "合并后的条件1",
  "合并后的条件2"
]

只输出JSON数组，不要其他内容。"""
            
            response = self.llm_client.complete(prompt, max_tokens=300)
            
            # 解析结果
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                merged = json.loads(json_match.group(0))
                
                # 停用旧条件
                for ctx in contexts:
                    ctx.is_active = False
                
                # 添加合并后的条件
                for content in merged[:self.MAX_PER_TYPE]:
                    if content.strip():
                        self.add(
                            content=content.strip(),
                            context_type=ctx_type,
                            user_id=user_id
                        )
                        
        except Exception as e:
            print(f"[ContextTracker] LLM压缩失败: {e}")
            # 回退：简单保留置信度最高的
            contexts.sort(key=lambda c: -c.confidence)
            for ctx in contexts[self.MAX_PER_TYPE:]:
                ctx.is_active = False
    
    def get_stats(self, user_id: str = "default") -> Dict[str, Any]:
        """获取持久条件的统计信息"""
        if user_id not in self.contexts:
            return {
                "total": 0,
                "active": 0,
                "by_type": {},
                "avg_confidence": 0.0,
                "oldest_days": 0
            }
        
        contexts = self.contexts[user_id]
        active = [c for c in contexts if c.is_active]
        
        # 按类型统计
        by_type = {}
        for ctx in active:
            type_name = ctx.context_type.value
            if type_name not in by_type:
                by_type[type_name] = 0
            by_type[type_name] += 1
        
        # 计算平均置信度
        avg_conf = sum(c.confidence for c in active) / len(active) if active else 0.0
        
        # 计算最老的条件
        now = time.time()
        oldest_days = 0
        if active:
            oldest = min(c.created_at for c in active)
            oldest_days = (now - oldest) / (24 * 3600)
        
        return {
            "total": len(contexts),
            "active": len(active),
            "by_type": by_type,
            "avg_confidence": round(avg_conf, 2),
            "oldest_days": round(oldest_days, 1),
            "limits": {
                "max_per_type": self.MAX_PER_TYPE,
                "max_total": self.MAX_TOTAL
            }
        }