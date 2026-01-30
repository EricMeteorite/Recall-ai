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
        # 移除归档时添加的额外字段（这些字段不是 PersistentContext 的属性）
        data.pop('archived_at', None)
        data.pop('archive_reason', None)
        return cls(**data)


class ContextTracker:
    """持久上下文追踪器
    
    增长控制策略：
    1. 每个类型最多保留 max_per_type 个条件（默认10个）
    2. 相似内容自动合并（增加置信度而非新增）- 使用 Embedding 语义相似度
    3. 置信度衰减：长期未被引用的条件置信度下降
    4. 超出数量时，淘汰置信度最低的
    5. 有LLM时，可以智能压缩多个条件
    6. 低置信度条件自动归档到 archive/contexts.jsonl
    
    智能去重机制：
    - 第一级：Embedding 向量余弦相似度（>0.85 直接合并，0.70-0.85 可能相似）
    - 第二级：LLM 提取时判断是否与已有条件重复
    - 第三级：定期批量整理合并
    """
    
    # 配置常量（从环境变量读取，支持热更新）
    @staticmethod
    def _get_limits_config():
        """获取限制配置（每次调用时读取，支持热更新）"""
        return {
            'max_per_type': int(os.environ.get('CONTEXT_MAX_PER_TYPE', '10')),
            'max_total': int(os.environ.get('CONTEXT_MAX_TOTAL', '100')),
            'decay_days': int(os.environ.get('CONTEXT_DECAY_DAYS', '14')),
            'decay_rate': float(os.environ.get('CONTEXT_DECAY_RATE', '0.05')),
            'min_confidence': float(os.environ.get('CONTEXT_MIN_CONFIDENCE', '0.1')),
        }
    
    # 兼容旧代码的属性访问
    @property
    def MAX_PER_TYPE(self) -> int:
        return self._get_limits_config()['max_per_type']
    
    @property
    def MAX_TOTAL(self) -> int:
        return self._get_limits_config()['max_total']
    
    @property
    def DECAY_DAYS(self) -> int:
        return self._get_limits_config()['decay_days']
    
    @property
    def DECAY_RATE(self) -> float:
        return self._get_limits_config()['decay_rate']
    
    @property
    def MIN_CONFIDENCE(self) -> float:
        return self._get_limits_config()['min_confidence']
    
    @property
    def trigger_interval(self) -> int:
        """触发间隔（支持热更新）"""
        return int(os.environ.get('CONTEXT_TRIGGER_INTERVAL', '5'))
    
    @property
    def max_context_turns(self) -> int:
        """最大上下文轮数（支持热更新）"""
        return int(os.environ.get('CONTEXT_MAX_CONTEXT_TURNS', '20'))
    
    SIMILARITY_THRESHOLD = 0.6  # 词重叠相似度阈值（后备方案）
    FLOAT_EPSILON = 1e-9  # 浮点数比较容差
    
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
    
    def __init__(self, base_path: Optional[str] = None, llm_client: Optional[Any] = None, 
                 embedding_backend: Optional[Any] = None, storage_dir: Optional[str] = None,
                 memory_provider: Optional[Any] = None):
        """初始化持久上下文追踪器
        
        存储结构：{base_path}/{user_id}/{character_id}/contexts.json
        与 MultiTenantStorage 和 ForeshadowingTracker 保持一致的路径结构。
        
        Args:
            base_path: 数据根目录（新参数，推荐使用）
            llm_client: LLM 客户端（用于智能提取和压缩）
            embedding_backend: Embedding 后端（用于智能去重），如果为 None 会尝试自动获取
            storage_dir: 旧参数（向后兼容），如果提供则自动迁移到新结构
            memory_provider: 记忆提供回调函数，格式为 (user_id, limit) -> List[Dict]
        """
        # 向后兼容：如果提供了 storage_dir 而非 base_path
        if storage_dir and not base_path:
            # 旧的 storage_dir 格式是 {data_root}/data/contexts
            # 新的 base_path 格式是 {data_root}/data
            if storage_dir.endswith('contexts'):
                base_path = os.path.dirname(storage_dir)
            else:
                base_path = storage_dir
        
        self.base_path = base_path
        self.llm_client = llm_client
        # 按 {user_id}/{character_id} 分隔的上下文存储
        self.contexts: Dict[str, List[PersistentContext]] = {}  # cache_key -> contexts
        
        # Embedding 后端（用于智能去重）
        self.embedding_backend = embedding_backend
        
        # 记忆提供回调（用于获取对话上下文）
        self._memory_provider = memory_provider
        
        # 触发机制（类似 ForeshadowingAnalyzer）
        # 每 N 轮对话触发一次条件提取，避免重复分析相同内容
        # 配置项通过 @property 支持热更新，不再在 __init__ 中缓存
        self._turn_counters: Dict[str, int] = {}  # cache_key -> 当前轮次计数
        self._last_analyzed_turn: Dict[str, int] = {}  # cache_key -> 上次分析时的总轮次
        
        if base_path:
            os.makedirs(base_path, exist_ok=True)
        # 改为按需加载（lazy loading），避免缓存键不一致问题
        # self._load_all()  # 已废弃，改用 _ensure_loaded()
        
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

【重要提示】
1. 只提取对话中**明确提到或确立**的信息
2. 如果对话内容很短或没有明确的背景信息，请返回空数组 []
3. 对于角色扮演/故事场景，要提取角色状态、技能、物品、关系等变化

持久前提条件是指：一旦确立就应该在后续所有对话中默认成立的背景信息。

【角色扮演/故事场景适用的条件类型】
- character_trait: 角色性格、身份、外貌等固定特征
- skill_ability: 角色习得的技能或能力（如：入侵神识、剑术）
- item_prop: 角色获得或携带的物品道具
- relationship: 角色之间的关系变化（如：成为师兄妹、结仇）
- world_setting: 世界观设定（如：修仙世界、魔法体系）
- emotional_state: 角色当前情绪状态

【日常对话适用的条件类型】
- user_identity: 用户身份（如：大学毕业生、程序员）
- user_goal: 用户目标（如：想创业、学习Python）
- environment: 技术环境（如：Windows开发、Ubuntu部署）
- project: 项目信息

【提取示例】
- "我用入侵神识的办法扫描记忆" → skill_ability: "主角掌握入侵神识能力"
- "李二狗是邻村的二流子" → character_trait: "李二狗是邻村的二流子"
- "师姐送给了我一把法剑" → item_prop: "主角获得师姐赠送的法剑"
- "我是在修仙界" → world_setting: "故事发生在修仙界"

对话内容：
{content}

请以JSON格式返回提取的条件（如果没有明确的条件则返回空数组 []）：
[
  {{"type": "条件类型", "content": "条件内容（简洁概括）", "keywords": ["关键词1", "关键词2"]}}
]

只返回JSON数组，不要其他解释。如果没有找到明确的条件，返回 []。"""
    
    def _sanitize_path_component(self, name: str) -> str:
        """清理路径组件中的非法字符"""
        return "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in name)
    
    def _get_cache_key(self, user_id: str, character_id: str) -> str:
        """获取内部缓存键"""
        return f"{user_id}/{character_id}"
    
    def _get_storage_path(self, user_id: str, character_id: str) -> str:
        """获取存储路径
        
        新结构：{base_path}/{user_id}/{character_id}/contexts.json
        """
        safe_user_id = self._sanitize_path_component(user_id)
        safe_char_id = self._sanitize_path_component(character_id)
        return os.path.join(self.base_path, safe_user_id, safe_char_id, 'contexts.json')
    
    def _load_all(self):
        """[已废弃] 预加载所有数据 - 不再使用
        
        问题：预加载时使用文件夹名（已清理）作为 user_id，
        但前端请求时使用原始 ID，导致缓存键不匹配。
        改用 _ensure_loaded() 按需加载。
        """
        pass  # 不再预加载
    
    def _ensure_loaded(self, user_id: str, character_id: str = "default"):
        """确保用户/角色的数据已加载（按需加载）
        
        类似 ForeshadowingTracker 的按需加载方式，
        使用原始 user_id 作为缓存键，保证一致性。
        """
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key in self.contexts:
            return  # 已加载
        
        # 尝试从文件加载
        self._load_user(user_id, character_id)
    
    def _load_user(self, user_id: str, character_id: str = "default"):
        """加载用户/角色的上下文"""
        cache_key = self._get_cache_key(user_id, character_id)
        filepath = self._get_storage_path(user_id, character_id)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.contexts[cache_key] = [
                        PersistentContext.from_dict(item) for item in data
                    ]
            except Exception as e:
                _safe_print(f"[Recall] 加载上下文数据失败 ({user_id}/{character_id}): {e}")
                self.contexts[cache_key] = []
    
    def _save_user(self, user_id: str, character_id: str = "default"):
        """保存用户/角色的上下文"""
        cache_key = self._get_cache_key(user_id, character_id)
        filepath = self._get_storage_path(user_id, character_id)
        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        contexts = self.contexts.get(cache_key, [])
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump([c.to_dict() for c in contexts], f, ensure_ascii=False, indent=2)
    
    def set_memory_provider(self, provider):
        """设置记忆提供回调函数
        
        Args:
            provider: 回调函数，格式为 (user_id, limit) -> List[Dict]
                     返回格式：[{'content': '...', 'metadata': {'role': 'user/assistant', ...}}]
        """
        self._memory_provider = provider
        _safe_print(f"[ContextTracker] 🔗 已设置 memory_provider")
    
    def on_turn(self, user_id: str = "default", character_id: str = "default") -> Dict[str, Any]:
        """通知一轮对话完成，检查是否应该触发条件提取
        
        类似 ForeshadowingAnalyzer.on_turn()，每 N 轮触发一次分析。
        这避免了每轮都重复分析相同对话历史的问题。
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            Dict: 包含触发状态和提取结果
        """
        cache_key = f"{user_id}/{character_id}"
        
        # 增加轮次计数
        if cache_key not in self._turn_counters:
            self._turn_counters[cache_key] = 0
        self._turn_counters[cache_key] += 1
        current_count = self._turn_counters[cache_key]
        
        # 检查是否应该触发分析
        if current_count >= self.trigger_interval:
            _safe_print(f"[ContextTracker] [SYNC] 触发条件提取: user={user_id}, char={character_id}")
            _safe_print(f"[ContextTracker]    轮次={current_count}, 间隔={self.trigger_interval}")
            
            # 重置计数
            self._turn_counters[cache_key] = 0
            
            # 执行提取（使用对话上下文）
            if self.llm_client and self._memory_provider:
                extracted = self._extract_from_conversation(user_id, character_id)
                return {
                    'triggered': True,
                    'extracted_count': len(extracted),
                    'extracted': [{'id': ctx.id, 'content': ctx.content, 'type': ctx.context_type.value} for ctx in extracted]
                }
            else:
                _safe_print(f"[ContextTracker]    [SKIP] LLM 或 memory_provider 未配置，跳过")
                return {'triggered': False, 'reason': 'LLM or memory_provider not configured'}
        
        return {
            'triggered': False,
            'turns_until_next': self.trigger_interval - current_count
        }
    
    def _extract_from_conversation(self, user_id: str, character_id: str = "default") -> List['PersistentContext']:
        """从对话历史中提取条件
        
        获取最近的对话历史，然后使用 LLM 提取持久条件。
        与 extract_from_text 不同，这个方法专门用于批量分析对话历史。
        
        使用 CONTEXT_MAX_CONTEXT_TURNS 配置控制获取范围，与伏笔分析器统一。
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            List[PersistentContext]: 提取的条件列表
        """
        # 使用 max_context_turns * 2 作为获取范围（与伏笔分析器保持一致）
        conversation_context = self._get_conversation_context(user_id, character_id, max_turns=self.max_context_turns * 2)
        
        if not conversation_context:
            _safe_print(f"[ContextTracker] [SKIP] 无对话上下文，跳过提取")
            return []
        
        _safe_print(f"[ContextTracker] [SEARCH] 从对话历史提取条件")
        _safe_print(f"[ContextTracker]    对话长度: {len(conversation_context)} 字符")
        
        # 使用 LLM 提取
        return self._extract_with_llm("", user_id, character_id, conversation_context)
    
    def _get_conversation_context(self, user_id: str, character_id: str = "default", 
                                   max_turns: int = 10) -> str:
        """获取最近的对话上下文
        
        从已保存的记忆中获取最近的对话，用于条件提取时提供更多上下文。
        
        Args:
            user_id: 用户ID
            character_id: 角色ID  
            max_turns: 最大轮数
            
        Returns:
            格式化的对话内容字符串
        """
        if not self._memory_provider:
            return ""
        
        try:
            # 获取最近的记忆
            memories = self._memory_provider(user_id, max_turns * 2)
            
            if not memories:
                return ""
            
            # 转换为对话格式
            conversations = []
            for mem in memories:
                metadata = mem.get('metadata', {})
                role = metadata.get('role', 'user')
                content = mem.get('content', '')
                timestamp = metadata.get('timestamp', 0)
                
                if content:
                    conversations.append({
                        'role': role,
                        'content': content,
                        'timestamp': timestamp
                    })
            
            # 按时间戳排序
            conversations.sort(key=lambda x: x.get('timestamp', 0))
            
            # 格式化为文本
            lines = []
            for conv in conversations:
                role_label = "用户" if conv['role'] == 'user' else "AI"
                lines.append(f"{role_label}: {conv['content']}")
            
            return "\n".join(lines)
            
        except Exception as e:
            _safe_print(f"[ContextTracker] ⚠️ 获取对话上下文失败: {e}")
            return ""

    # =========================
    # 归档机制（低置信度条件自动归档）
    # =========================
    
    MAX_ARCHIVE_FILE_SIZE = 10 * 1024 * 1024  # 10MB 归档文件大小上限
    
    def _get_archive_path(self, user_id: str, character_id: str) -> str:
        """获取归档文件路径
        
        路径格式：{base_path}/{user_id}/{character_id}/archive/contexts.jsonl
        """
        safe_user_id = self._sanitize_path_component(user_id)
        safe_char_id = self._sanitize_path_component(character_id)
        archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
        os.makedirs(archive_dir, exist_ok=True)
        return os.path.join(archive_dir, 'contexts.jsonl')
    
    def _archive_context(self, ctx: 'PersistentContext', user_id: str, character_id: str,
                         reason: str = 'low_confidence') -> bool:
        """将单个条件归档到 JSONL 文件
        
        归档格式：每行一个 JSON 对象，包含完整条件数据和归档时间
        
        Args:
            ctx: 要归档的条件
            user_id: 用户ID
            character_id: 角色ID
            reason: 归档原因 ('low_confidence', 'type_overflow', 'total_overflow')
        
        Returns:
            bool: 归档是否成功
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            archive_path = self._get_archive_path(user_id, character_id)
            
            # 检查文件大小，如果超过上限则轮转
            if os.path.exists(archive_path):
                file_size = os.path.getsize(archive_path)
                if file_size >= self.MAX_ARCHIVE_FILE_SIZE:
                    # 轮转文件：contexts.jsonl -> contexts_001.jsonl
                    base_name = archive_path.rsplit('.', 1)[0]
                    suffix = 1
                    while os.path.exists(f"{base_name}_{suffix:03d}.jsonl"):
                        suffix += 1
                    os.rename(archive_path, f"{base_name}_{suffix:03d}.jsonl")
                    logger.info(f"[ContextTracker] 归档文件轮转: contexts.jsonl -> contexts_{suffix:03d}.jsonl")
            
            # 准备归档数据
            archive_data = ctx.to_dict()
            archive_data['archived_at'] = time.time()
            archive_data['archive_reason'] = reason
            
            # 追加写入 JSONL
            with open(archive_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(archive_data, ensure_ascii=False) + '\n')
            
            logger.debug(f"[ContextTracker] 已归档条件: {ctx.id} (置信度={ctx.confidence:.2f}, 原因={reason})")
            return True
            
        except Exception as e:
            logger.error(f"[ContextTracker] 归档条件失败: {e}")
            return False
    
    def get_context_by_id(self, context_id: str, user_id: str = "default", 
                          character_id: str = "default") -> Optional['PersistentContext']:
        """根据ID获取条件（包括已归档的）
        
        优先从活跃条件中查找，找不到再去归档中找（包括分卷文件）
        """
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        # 先从活跃条件中找
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key in self.contexts:
            for ctx in self.contexts[cache_key]:
                if ctx.id == context_id:
                    return ctx
        
        # 再从归档中找（搜索所有归档文件，包括分卷）
        if self.base_path:
            safe_user_id = self._sanitize_path_component(user_id)
            safe_char_id = self._sanitize_path_component(character_id)
            archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
            
            if os.path.exists(archive_dir):
                for filename in os.listdir(archive_dir):
                    if filename.startswith('contexts') and filename.endswith('.jsonl'):
                        archive_path = os.path.join(archive_dir, filename)
                        try:
                            with open(archive_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if line.strip():
                                        data = json.loads(line)
                                        if data.get('id') == context_id:
                                            return PersistentContext.from_dict(data)
                        except Exception:
                            pass
        
        return None

    def get_archived_contexts(
        self,
        user_id: str = "default",
        character_id: str = "default",
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        context_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取归档的持久条件列表（分页、搜索、筛选）
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            page: 页码（从1开始）
            page_size: 每页数量
            search: 搜索关键词（搜索内容）
            context_type: 类型筛选
            
        Returns:
            Dict: {
                'items': List[Dict],  # 当前页的条件列表
                'total': int,         # 总数量
                'page': int,          # 当前页
                'page_size': int,     # 每页数量
                'total_pages': int    # 总页数
            }
        """
        all_archived = []
        
        if self.base_path:
            safe_user_id = self._sanitize_path_component(user_id)
            safe_char_id = self._sanitize_path_component(character_id)
            archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
            
            if os.path.exists(archive_dir):
                # 读取所有归档文件
                for filename in sorted(os.listdir(archive_dir), reverse=True):
                    if filename.startswith('contexts') and filename.endswith('.jsonl'):
                        archive_path = os.path.join(archive_dir, filename)
                        try:
                            with open(archive_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if line.strip():
                                        data = json.loads(line)
                                        all_archived.append(data)
                        except Exception:
                            pass
        
        # 按归档时间倒序排列
        all_archived.sort(key=lambda x: x.get('archived_at', 0), reverse=True)
        
        # 筛选：类型
        if context_type:
            all_archived = [c for c in all_archived if c.get('context_type') == context_type]
        
        # 筛选：搜索
        if search:
            search_lower = search.lower()
            all_archived = [c for c in all_archived if search_lower in c.get('content', '').lower()]
        
        # 分页
        total = len(all_archived)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        items = all_archived[start_idx:end_idx]
        
        return {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages
        }

    def restore_from_archive(
        self,
        context_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> Optional['PersistentContext']:
        """从归档恢复条件到活跃列表
        
        Args:
            context_id: 条件ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            Optional[PersistentContext]: 恢复的条件，未找到返回 None
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.base_path:
            return None
        
        safe_user_id = self._sanitize_path_component(user_id)
        safe_char_id = self._sanitize_path_component(character_id)
        archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
        
        if not os.path.exists(archive_dir):
            return None
        
        # 在所有归档文件中查找并移除
        found_data = None
        for filename in os.listdir(archive_dir):
            if not (filename.startswith('contexts') and filename.endswith('.jsonl')):
                continue
            
            archive_path = os.path.join(archive_dir, filename)
            lines_to_keep = []
            
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('id') == context_id and found_data is None:
                                found_data = data
                            else:
                                lines_to_keep.append(line)
                
                if found_data:
                    # 重写归档文件（移除已恢复的条件）
                    with open(archive_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines_to_keep)
                    break
            except Exception as e:
                logger.error(f"[ContextTracker] 读取归档文件失败: {e}")
        
        if not found_data:
            return None
        
        # 移除归档字段，创建 PersistentContext 对象
        found_data.pop('archived_at', None)
        found_data.pop('archive_reason', None)
        ctx = PersistentContext.from_dict(found_data)
        ctx.is_active = True
        
        # 添加到活跃列表
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            self.contexts[cache_key] = []
        self.contexts[cache_key].append(ctx)
        self._save_user(user_id, character_id)
        
        logger.info(f"[ContextTracker] 已从归档恢复条件: {context_id}")
        return ctx

    def delete_archived(
        self,
        context_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """彻底删除归档中的条件
        
        Args:
            context_id: 条件ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            bool: 是否成功删除
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.base_path:
            return False
        
        safe_user_id = self._sanitize_path_component(user_id)
        safe_char_id = self._sanitize_path_component(character_id)
        archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
        
        if not os.path.exists(archive_dir):
            return False
        
        deleted = False
        for filename in os.listdir(archive_dir):
            if not (filename.startswith('contexts') and filename.endswith('.jsonl')):
                continue
            
            archive_path = os.path.join(archive_dir, filename)
            lines_to_keep = []
            
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('id') == context_id:
                                deleted = True
                            else:
                                lines_to_keep.append(line)
                
                if deleted:
                    with open(archive_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines_to_keep)
                    logger.info(f"[ContextTracker] 已彻底删除归档条件: {context_id}")
                    break
            except Exception as e:
                logger.error(f"[ContextTracker] 删除归档条件失败: {e}")
        
        return deleted

    def clear_archived(
        self,
        user_id: str = "default",
        character_id: str = "default"
    ) -> int:
        """清空所有归档条件
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            int: 删除的条件数量
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.base_path:
            return 0
        
        safe_user_id = self._sanitize_path_component(user_id)
        safe_char_id = self._sanitize_path_component(character_id)
        archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
        
        if not os.path.exists(archive_dir):
            return 0
        
        count = 0
        for filename in os.listdir(archive_dir):
            if filename.startswith('contexts') and filename.endswith('.jsonl'):
                archive_path = os.path.join(archive_dir, filename)
                try:
                    # 统计行数
                    with open(archive_path, 'r', encoding='utf-8') as f:
                        count += sum(1 for line in f if line.strip())
                    # 删除文件
                    os.remove(archive_path)
                except Exception as e:
                    logger.error(f"[ContextTracker] 清空归档文件失败: {e}")
        
        logger.info(f"[ContextTracker] 已清空归档条件: {count} 个")
        return count

    def clear_user(
        self,
        user_id: str = "default",
        character_id: str = "default",
        all_characters: bool = False
    ) -> bool:
        """清空指定用户的所有上下文数据
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            all_characters: 如果为 True，清空该用户的所有角色数据
            
        Returns:
            bool: 是否成功
        """
        import logging
        import shutil
        logger = logging.getLogger(__name__)
        
        try:
            safe_user_id = self._sanitize_path_component(user_id)
            
            if all_characters:
                # 清空该用户所有角色的内存数据
                keys_to_delete = [k for k in self._user_data.keys() if k.startswith(f"{user_id}/")]
                for key in keys_to_delete:
                    del self._user_data[key]
                
                # 清空该用户目录下所有角色的磁盘数据
                if self.base_path:
                    user_path = os.path.join(self.base_path, safe_user_id)
                    if os.path.exists(user_path):
                        shutil.rmtree(user_path)
                        logger.info(f"[ContextTracker] 已清空用户所有角色数据: {user_id}")
            else:
                # 清空内存中的数据
                cache_key = f"{user_id}/{character_id}"
                if cache_key in self._user_data:
                    del self._user_data[cache_key]
                
                # 清空磁盘数据
                if self.base_path:
                    safe_char_id = self._sanitize_path_component(character_id)
                    user_path = os.path.join(self.base_path, safe_user_id, safe_char_id)
                    
                    if os.path.exists(user_path):
                        shutil.rmtree(user_path)
                        logger.info(f"[ContextTracker] 已清空用户数据: {user_id}/{character_id}")
            
            return True
        except Exception as e:
            logger.error(f"[ContextTracker] 清空用户数据失败: {e}")
            return False
    
    def clear(self) -> bool:
        """清空所有上下文数据（全局）
        
        Returns:
            bool: 是否成功
        """
        import logging
        import shutil
        logger = logging.getLogger(__name__)
        
        try:
            # 清空内存中的所有数据
            self._user_data.clear()
            
            # 清空磁盘上的所有数据
            if self.base_path and os.path.exists(self.base_path):
                for item in os.listdir(self.base_path):
                    item_path = os.path.join(self.base_path, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                logger.info("[ContextTracker] 已清空所有上下文数据")
            
            return True
        except Exception as e:
            logger.error(f"[ContextTracker] 清空所有数据失败: {e}")
            return False

    def archive_context(
        self,
        context_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """手动将活跃条件归档
        
        Args:
            context_id: 条件ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            bool: 是否成功归档
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            return False
        
        # 查找并移除
        ctx_to_archive = None
        for i, ctx in enumerate(self.contexts[cache_key]):
            if ctx.id == context_id:
                ctx_to_archive = self.contexts[cache_key].pop(i)
                break
        
        if not ctx_to_archive:
            return False
        
        # 归档
        success = self._archive_context(ctx_to_archive, user_id, character_id, reason='manual')
        if success:
            self._save_user(user_id, character_id)
            logger.info(f"[ContextTracker] 已手动归档条件: {context_id}")
        
        return success

    def update_context(
        self,
        context_id: str,
        user_id: str = "default",
        character_id: str = "default",
        content: Optional[str] = None,
        context_type: Optional[str] = None,
        confidence: Optional[float] = None,
        keywords: Optional[List[str]] = None
    ) -> Optional['PersistentContext']:
        """更新持久条件的字段
        
        Args:
            context_id: 条件ID
            user_id: 用户ID
            character_id: 角色ID
            content: 新内容（可选）
            context_type: 新类型（可选）
            confidence: 新置信度（可选）
            keywords: 新关键词（可选）
            
        Returns:
            Optional[PersistentContext]: 更新后的条件，未找到返回 None
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            return None
        
        for ctx in self.contexts[cache_key]:
            if ctx.id == context_id:
                if content is not None:
                    ctx.content = content
                    # 更新 embedding
                    new_embedding = self._get_embedding(content)
                    if new_embedding:
                        ctx.embedding = new_embedding
                if context_type is not None:
                    try:
                        ctx.context_type = ContextType(context_type)
                    except ValueError:
                        ctx.context_type = ContextType.CUSTOM
                if confidence is not None:
                    ctx.confidence = max(0.0, min(1.0, confidence))
                if keywords is not None:
                    ctx.keywords = keywords
                
                self._save_user(user_id, character_id)
                logger.info(f"[ContextTracker] 已更新条件: {context_id}")
                return ctx
        
        return None

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
            # 优化：只有当新内容的 embedding 已经计算好时，才使用 embedding 比较
            # 不要为旧数据（没有存储 embedding）调用 API，避免 N 次调用
            # emb2 是新内容的 embedding（调用方应该预先计算好）
            # emb1 是现有条件的 embedding（应该从存储中读取，如果没有就跳过）
            
            # 如果两边都有Embedding，使用余弦相似度
            if emb1 is not None and emb2 is not None:
                sim = self._compute_embedding_similarity(emb1, emb2)
                return (sim, "embedding")
        
        # 后备：词重叠
        sim = self._compute_word_similarity(text1, text2)
        return (sim, "word")
    
    def _find_similar(self, content: str, user_id: str, character_id: str,
                     context_type: ContextType,
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
            character_id: 角色ID
            context_type: 条件类型
            new_embedding: 新条件的Embedding向量（可选，如果提供则避免重复计算）
            
        Returns:
            Tuple[Optional[PersistentContext], float, str]: 
                (相似条件或None, 相似度, 方法 "exact"/"embedding"/"word")
        """
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            return (None, 0.0, "none")
        
        dedup_config = self._get_dedup_config()
        best_match: Optional[PersistentContext] = None
        best_sim = 0.0
        best_method = "none"
        
        for existing in self.contexts[cache_key]:
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
    
    def _enforce_limits(self, user_id: str, character_id: str = "default"):
        """强制执行数量限制
        
        处理流程：
        1. 应用置信度衰减
        2. 归档并删除低置信度条件
        3. 按类型限制数量（溢出的归档）
        4. 按总数限制数量（溢出的归档）
        """
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            return
        
        contexts = self.contexts[cache_key]
        
        # 1. 应用置信度衰减（指数衰减）
        now = time.time()
        decay_threshold = now - (self.DECAY_DAYS * 24 * 3600)
        
        for ctx in contexts:
            if ctx.is_active and ctx.last_used < decay_threshold:
                # 乘法衰减（指数衰减）：每次衰减 DECAY_RATE 比例
                # 例如 DECAY_RATE=0.05 时，每次衰减后保留 95% 的置信度
                # 低于 MIN_CONFIDENCE 时会被下面的逻辑归档
                ctx.confidence = max(0, ctx.confidence * (1 - self.DECAY_RATE))
        
        # 2. 归档并删除低置信度条件
        to_archive = []
        for ctx in contexts:
            if ctx.confidence <= self.MIN_CONFIDENCE + self.FLOAT_EPSILON:  # 使用类常量容差
                ctx.is_active = False
                to_archive.append(ctx)
        
        # 归档低置信度条件
        for ctx in to_archive:
            self._archive_context(ctx, user_id, character_id, reason='low_confidence')
        
        # 只保留活跃的
        contexts = [c for c in contexts if c.is_active]
        
        # 3. 每类型数量限制
        by_type: Dict[ContextType, List[PersistentContext]] = {}
        for ctx in contexts:
            if ctx.context_type not in by_type:
                by_type[ctx.context_type] = []
            by_type[ctx.context_type].append(ctx)
        
        # 每类型只保留置信度最高的 MAX_PER_TYPE 个，超出的归档
        kept = []
        for ctx_type, type_contexts in by_type.items():
            # 按置信度排序
            type_contexts.sort(key=lambda c: -c.confidence)
            kept.extend(type_contexts[:self.MAX_PER_TYPE])
            # 超出的归档
            for ctx in type_contexts[self.MAX_PER_TYPE:]:
                self._archive_context(ctx, user_id, character_id, reason='type_overflow')
        
        # 4. 总数限制
        if len(kept) > self.MAX_TOTAL:
            kept.sort(key=lambda c: -c.confidence)
            # 超出的归档
            for ctx in kept[self.MAX_TOTAL:]:
                self._archive_context(ctx, user_id, character_id, reason='total_overflow')
            kept = kept[:self.MAX_TOTAL]
        
        self.contexts[cache_key] = kept
        
        # 保存更改（确保归档后的状态持久化）
        self._save_user(user_id, character_id)
    
    def add(self, content: str, context_type: ContextType, user_id: str = "default",
            character_id: str = "default",
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
        
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            self.contexts[cache_key] = []
        
        # 1. 预计算新内容的Embedding（避免重复计算）
        new_embedding = self._get_embedding(content)
        
        # 2. 检查是否有语义相似的已有条件
        similar, sim_score, sim_method = self._find_similar(
            content, user_id, character_id, context_type, new_embedding=new_embedding
        )
        
        if similar:
            # 发现相似条件，进行合并而不是创建新条件
            content_preview = content[:35].replace('\n', ' ')
            similar_preview = similar.content[:35].replace('\n', ' ')
            _safe_print(f"[ContextTracker] 🔄 去重合并:")
            _safe_print(f"[ContextTracker]    新: {content_preview}...")
            _safe_print(f"[ContextTracker]    旧: {similar_preview}...")
            _safe_print(f"[ContextTracker]    方法={sim_method}, 相似度={sim_score:.3f}")
            
            # 合并策略
            if sim_method == "exact":
                # 完全相同，只更新使用信息
                similar.use_count += 1
                similar.last_used = time.time()
                _safe_print(f"[ContextTracker]    ✅ 完全相同，更新使用计数: {similar.use_count}")
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
            
            self._save_user(user_id, character_id)
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
        
        self.contexts[cache_key].append(ctx)
        
        # 4. 强制执行数量限制
        self._enforce_limits(user_id, character_id)
        
        # 检查新条件是否被淘汰了
        if ctx not in self.contexts[cache_key]:
            # 条件被淘汰了（因为置信度不够高），标记为不活跃
            ctx.is_active = False
            _safe_print(f"[ContextTracker] 新条件因数量限制被淘汰: {content[:50]}...")
        else:
            _safe_print(f"[ContextTracker] 创建新条件: type={context_type.value}, content={content[:50]}...")
        
        self._save_user(user_id, character_id)
        return ctx
    
    def get_active(self, user_id: str = "default", character_id: str = "default") -> List[PersistentContext]:
        """获取所有活跃的持久上下文"""
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            return []
        
        now = time.time()
        active = []
        
        for ctx in self.contexts[cache_key]:
            if not ctx.is_active:
                continue
            if ctx.expires_at and ctx.expires_at < now:
                ctx.is_active = False
                continue
            active.append(ctx)
        
        # 按类型和置信度排序
        active.sort(key=lambda c: (-c.confidence, c.context_type.value))
        return active
    
    def get_by_type(self, context_type: ContextType, user_id: str = "default",
                    character_id: str = "default") -> List[PersistentContext]:
        """按类型获取上下文"""
        return [c for c in self.get_active(user_id, character_id) if c.context_type == context_type]
    
    def deactivate(self, context_id: str, user_id: str = "default",
                   character_id: str = "default") -> bool:
        """停用某个上下文"""
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            return False
        
        for ctx in self.contexts[cache_key]:
            if ctx.id == context_id:
                ctx.is_active = False
                self._save_user(user_id, character_id)
                return True
        return False
    
    def mark_used(self, context_id: str, user_id: str = "default", character_id: str = "default",
                  save: bool = True):
        """标记上下文被使用
        
        Args:
            context_id: 条件ID
            user_id: 用户ID
            character_id: 角色ID
            save: 是否立即保存（批量操作时设为False，最后统一保存）
        """
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts:
            return
        
        for ctx in self.contexts[cache_key]:
            if ctx.id == context_id:
                ctx.last_used = time.time()
                ctx.use_count += 1
                if save:
                    self._save_user(user_id, character_id)
                return
    
    def mark_used_batch(self, context_ids: List[str], user_id: str = "default",
                        character_id: str = "default"):
        """批量标记上下文被使用（只保存一次）"""
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        if cache_key not in self.contexts or not context_ids:
            return
        
        now = time.time()
        id_set = set(context_ids)  # 转成 set 提高查找效率
        for ctx in self.contexts[cache_key]:
            if ctx.id in id_set:
                ctx.last_used = now
                ctx.use_count += 1
        
        self._save_user(user_id, character_id)
    
    def extract_from_text(self, text: str, user_id: str = "default",
                          character_id: str = "default", 
                          use_conversation_context: bool = True) -> List[PersistentContext]:
        """从文本中自动提取持久上下文
        
        优先使用 LLM，如果没有 LLM 则使用规则。
        如果启用了 memory_provider 且 use_conversation_context=True，
        会自动获取最近的对话历史作为上下文，帮助 LLM 更好地理解和提取条件。
        
        Args:
            text: 当前消息文本
            user_id: 用户ID
            character_id: 角色ID
            use_conversation_context: 是否获取对话历史作为上下文（默认True）
        """
        text_preview = text[:60].replace('\n', ' ') if len(text) > 60 else text.replace('\n', ' ')
        _safe_print(f"[ContextTracker] 🔍 开始提取: user={user_id}, char={character_id}")
        _safe_print(f"[ContextTracker]    文本({len(text)}字): {text_preview}{'...' if len(text) > 60 else ''}")
        
        # 获取对话上下文（如果配置了 memory_provider）
        conversation_context = ""
        if use_conversation_context and self.llm_client and self._memory_provider:
            conversation_context = self._get_conversation_context(user_id, character_id, max_turns=10)
            if conversation_context:
                _safe_print(f"[ContextTracker]    📜 获取到对话上下文: {len(conversation_context)} 字符")
        
        _safe_print(f"[ContextTracker]    模式: {'LLM' if self.llm_client else '规则'}")
        
        if self.llm_client:
            # 传入对话上下文以帮助 LLM 更好地理解
            result = self._extract_with_llm(text, user_id, character_id, conversation_context)
        else:
            result = self._extract_with_rules(text, user_id, character_id)
        
        if result:
            _safe_print(f"[ContextTracker] ✅ 提取完成: 新增 {len(result)} 条条件")
            for ctx in result:
                _safe_print(f"[ContextTracker]    🌱 [{ctx.context_type.value}] {ctx.content[:50]}{'...' if len(ctx.content) > 50 else ''}")
        else:
            _safe_print(f"[ContextTracker] ⏭️ 提取完成: 未发现新条件")
        
        return result
    
    def _extract_with_rules(self, text: str, user_id: str,
                            character_id: str = "default") -> List[PersistentContext]:
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
                        user_id=user_id,
                        character_id=character_id
                    )
                    extracted.append(ctx)
        
        return extracted
    
    def _extract_with_llm(self, text: str, user_id: str,
                          character_id: str = "default",
                          conversation_context: str = "") -> List[PersistentContext]:
        """使用 LLM 提取
        
        Args:
            text: 当前消息文本
            user_id: 用户ID
            character_id: 角色ID
            conversation_context: 对话历史上下文（可选，帮助 LLM 更好理解）
        """
        try:
            _safe_print(f"[ContextTracker] 🤖 调用 LLM 提取条件...")
            
            # 构建提取内容：如果有对话上下文，则合并
            if conversation_context:
                # 使用对话上下文 + 当前消息
                extract_content = f"""【最近对话历史】
{conversation_context}

【当前消息】
{text}"""
                _safe_print(f"[ContextTracker]    📝 提取内容: 对话历史 + 当前消息 = {len(extract_content)} 字符")
            else:
                extract_content = text
            
            prompt = self.extraction_prompt.format(content=extract_content)
            # 从环境变量读取配置的最大 tokens，或根据内容长度动态计算
            config_max_tokens = int(os.environ.get('CONTEXT_EXTRACTION_MAX_TOKENS', '2000'))
            content_len = len(extract_content)
            # 动态计算，但不超过配置的上限
            max_tokens = min(config_max_tokens, max(1500, content_len // 3))
            response = self.llm_client.complete(prompt, max_tokens=max_tokens)
            _safe_print(f"[ContextTracker]    LLM 响应: {len(response)} 字符")
            
            # 解析 JSON
            import json
            # 尝试找到 JSON 数组
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                items = json.loads(json_match.group(0))
                _safe_print(f"[ContextTracker]    解析到 {len(items)} 条候选条件")
                
                extracted = []
                for item in items:
                    try:
                        ctx = self.add(
                            content=item['content'],
                            context_type=ContextType(item['type']),
                            user_id=user_id,
                            character_id=character_id,
                            keywords=item.get('keywords', [])
                        )
                        extracted.append(ctx)
                    except (KeyError, ValueError) as e:
                        _safe_print(f"[ContextTracker]    ⚠️ 跳过无效条件: {e}")
                        continue
                
                return extracted
            else:
                _safe_print(f"[ContextTracker]    ⚠️ LLM 响应中未找到 JSON 数组")
        except Exception as e:
            _safe_print(f"[ContextTracker] ❌ LLM提取失败，回退到规则: {e}")
        
        # 回退到规则提取
        return self._extract_with_rules(text, user_id, character_id)
    
    def format_for_prompt(self, user_id: str = "default", character_id: str = "default") -> str:
        """格式化为提示词注入
        
        注意：本方法不再自动调用 _enforce_limits()，避免重复衰减检查。
        调用方（如 engine.build_context）应负责在适当时机调用衰减检查。
        """
        active = self.get_active(user_id, character_id)
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
    
    def get_relevant(self, query: str, user_id: str = "default", character_id: str = "default",
                     top_k: int = 5) -> List[PersistentContext]:
        """获取与查询最相关的上下文"""
        active = self.get_active(user_id, character_id)
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
    
    def consolidate_contexts(self, user_id: str = "default", character_id: str = "default",
                             force: bool = False) -> int:
        """智能压缩合并相似的持久条件
        
        当条件数量超过阈值或强制执行时，使用LLM将相似条件合并
        
        Returns:
            减少的条件数量
        """
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        
        if cache_key not in self.contexts:
            return 0
        
        contexts = [c for c in self.contexts[cache_key] if c.is_active]
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
                self._consolidate_with_llm(type_contexts, ctx_type, user_id, character_id)
            else:
                # 简单压缩：保留置信度最高的几个
                type_contexts.sort(key=lambda c: -c.confidence)
                for ctx in type_contexts[self.MAX_PER_TYPE:]:
                    ctx.is_active = False
        
        self._save_user(user_id, character_id)
        
        # 计算减少的数量
        new_count = len([c for c in self.contexts[cache_key] if c.is_active])
        return original_count - new_count
    
    def _consolidate_with_llm(self, contexts: List[PersistentContext], 
                              ctx_type: ContextType, user_id: str,
                              character_id: str = "default"):
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
            
            # 合并输出通常较小，使用默认 max_tokens 或配置的一半
            merge_max_tokens = int(os.environ.get('CONTEXT_EXTRACTION_MAX_TOKENS', '2000')) // 4
            response = self.llm_client.complete(prompt, max_tokens=max(300, merge_max_tokens))
            
            # 解析结果
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                merged = json.loads(json_match.group(0))
                
                # 过滤有效内容
                valid_contents = [c.strip() for c in merged[:self.MAX_PER_TYPE] if c and c.strip()]
                
                # 如果 LLM 返回空结果，使用回退策略
                if not valid_contents:
                    raise ValueError("LLM 返回空结果")
                
                # 停用旧条件（只在确认有新条件后再停用）
                for ctx in contexts:
                    ctx.is_active = False
                
                # 添加合并后的条件
                for content in valid_contents:
                    self.add(
                        content=content,
                        context_type=ctx_type,
                        user_id=user_id,
                        character_id=character_id
                    )
            else:
                raise ValueError("LLM 响应格式无效")
                        
        except Exception as e:
            _safe_print(f"[ContextTracker] LLM压缩失败: {e}")
            # 回退：简单保留置信度最高的
            contexts.sort(key=lambda c: -c.confidence)
            for ctx in contexts[self.MAX_PER_TYPE:]:
                ctx.is_active = False
    
    # get_by_id 是 get_context_by_id 的别名，保持API一致性
    def get_by_id(self, context_id: str, user_id: str = "default", 
                  character_id: str = "default") -> Optional[PersistentContext]:
        """get_context_by_id 的别名，保持与 ForeshadowingTracker 的 API 一致"""
        return self.get_context_by_id(context_id, user_id, character_id)
    
    def get_stats(self, user_id: str = "default", character_id: str = "default") -> Dict[str, Any]:
        """获取持久条件的统计信息"""
        # 确保数据已加载
        self._ensure_loaded(user_id, character_id)
        
        cache_key = self._get_cache_key(user_id, character_id)
        
        if cache_key not in self.contexts:
            return {
                "total": 0,
                "active": 0,
                "by_type": {},
                "avg_confidence": 0.0,
                "oldest_days": 0
            }
        
        contexts = self.contexts[cache_key]
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