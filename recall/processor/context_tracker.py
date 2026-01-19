"""持久上下文追踪器 - 追踪和管理持久性前提条件

这个模块解决的问题：
- 某些信息一旦确立，就应该成为后续所有对话的"默认前提条件"
- 比如"用户是大学毕业生想创业" —— 后续所有建议都基于这个前提
- 比如"Windows开发，Ubuntu部署" —— 后续所有代码建议都基于这个环境

核心概念：
- PersistentContext: 持久性上下文/条件
- 不同于伏笔（未解决的线索），这是已确立的背景设定
- 不同于普通记忆（需要检索），这是每次对话都应该自动包含的前提
"""

import os
import json
import time
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
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
    
    # 角色扮演相关
    CHARACTER_TRAIT = "character_trait"  # 角色特征（如：角色性格设定）
    WORLD_SETTING = "world_setting"      # 世界观设定（如：魔法世界）
    RELATIONSHIP = "relationship"        # 关系设定（如：用户是角色的朋友）
    
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
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['context_type'] = self.context_type.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PersistentContext':
        data['context_type'] = ContextType(data['context_type'])
        return cls(**data)


class ContextTracker:
    """持久上下文追踪器
    
    增长控制策略：
    1. 每个类型最多保留 max_per_type 个条件（默认5个）
    2. 相似内容自动合并（增加置信度而非新增）
    3. 置信度衰减：长期未被引用的条件置信度下降
    4. 超出数量时，淘汰置信度最低的
    5. 有LLM时，可以智能压缩多个条件
    """
    
    # 配置常量
    MAX_PER_TYPE = 5          # 每类型最多保留5个条件
    MAX_TOTAL = 30            # 总数最多30个
    DECAY_DAYS = 7            # 7天未使用开始衰减
    DECAY_RATE = 0.1          # 每次衰减10%置信度
    MIN_CONFIDENCE = 0.2      # 最低置信度，低于此自动删除
    SIMILARITY_THRESHOLD = 0.6  # 相似度阈值（用于合并判断）
    
    def __init__(self, storage_dir: str, llm_client: Optional[Any] = None):
        self.storage_dir = storage_dir
        self.llm_client = llm_client
        self.contexts: Dict[str, List[PersistentContext]] = {}  # user_id -> contexts
        
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

对话内容：
{content}

请以JSON格式返回提取的条件（如果没有则返回空数组）：
[
  {{"type": "user_identity|user_goal|environment|project|character_trait|world_setting|relationship|assumption|constraint", "content": "条件内容", "keywords": ["关键词1", "关键词2"]}}
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
    
    def _compute_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度（简单实现：词重叠）"""
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
    
    def _find_similar(self, content: str, user_id: str, context_type: ContextType) -> Optional[PersistentContext]:
        """查找相似的已有条件"""
        if user_id not in self.contexts:
            return None
        
        for existing in self.contexts[user_id]:
            if existing.context_type != context_type:
                continue
            if not existing.is_active:
                continue
            
            # 完全相同
            if existing.content.lower() == content.lower():
                return existing
            
            # 相似度检查
            sim = self._compute_similarity(existing.content, content)
            if sim >= self.SIMILARITY_THRESHOLD:
                return existing
        
        return None
    
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
        
        智能处理：
        1. 如果有相似条件，合并（增加置信度）而非新增
        2. 超出数量限制时，淘汰置信度最低的
        
        注意：如果该类型已达到上限且新条件置信度不够高，
        新条件可能会被立即淘汰（但仍会返回该对象，is_active=False）
        """
        import uuid
        
        if user_id not in self.contexts:
            self.contexts[user_id] = []
        
        # 检查是否有相似的已有条件
        similar = self._find_similar(content, user_id, context_type)
        if similar:
            # 合并：增加置信度，更新时间
            similar.confidence = min(1.0, similar.confidence + 0.1)
            similar.use_count += 1
            similar.last_used = time.time()
            # 如果新内容更长/更详细，用新内容替换
            if len(content) > len(similar.content):
                similar.content = content
            self._save_user(user_id)
            return similar
        
        # 创建新条件
        ctx = PersistentContext(
            id=f"ctx_{uuid.uuid4().hex[:12]}",
            content=content,
            context_type=context_type,
            user_id=user_id,
            source_turn=source_turn,
            keywords=keywords or [],
            related_entities=related_entities or []
        )
        
        self.contexts[user_id].append(ctx)
        
        # 强制执行数量限制
        self._enforce_limits(user_id)
        
        # 检查新条件是否被淘汰了
        if ctx not in self.contexts[user_id]:
            # 条件被淘汰了（因为置信度不够高），标记为不活跃
            ctx.is_active = False
            print(f"[ContextTracker] 新条件因数量限制被淘汰: {content[:50]}...")
        
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
            ContextType.CHARACTER_TRAIT: "角色特征",
            ContextType.WORLD_SETTING: "世界观",
            ContextType.RELATIONSHIP: "关系设定",
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