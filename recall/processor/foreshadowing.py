"""伏笔追踪器 - 追踪未解决的叙事线索（支持多角色）

三级语义去重策略：
1. Embedding余弦相似度（快速过滤，~50ms）
2. 完全相同检测（精确匹配）
3. 词重叠后备方案（兼容无Embedding场景）

配置项（通过环境变量）：
- DEDUP_EMBEDDING_ENABLED: 是否启用Embedding去重（默认true）
- DEDUP_HIGH_THRESHOLD: 高相似度阈值，自动合并（默认0.85）
- DEDUP_LOW_THRESHOLD: 低相似度阈值，视为不同（默认0.70）
"""

import time
import os
import json
import numpy as np
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field


class ForeshadowingStatus(Enum):
    """伏笔状态"""
    PLANTED = "planted"        # 已埋下
    DEVELOPING = "developing"  # 发展中
    RESOLVED = "resolved"      # 已解决
    ABANDONED = "abandoned"    # 已放弃


@dataclass
class Foreshadowing:
    """伏笔实体"""
    id: str
    content: str
    status: ForeshadowingStatus = ForeshadowingStatus.PLANTED
    planted_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    related_entities: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    resolution: Optional[str] = None
    importance: float = 0.5  # 0-1
    # Embedding向量（用于语义去重）- 内部存储为List，访问时转为numpy
    _embedding: Optional[List[float]] = field(default=None, repr=False)
    
    @property
    def embedding(self) -> Optional[np.ndarray]:
        """获取Embedding向量（numpy数组形式）"""
        if self._embedding is None:
            return None
        return np.array(self._embedding)
    
    @embedding.setter
    def embedding(self, value: Optional[Any]):
        """设置Embedding向量（接受list或numpy数组）"""
        if value is None:
            self._embedding = None
        elif isinstance(value, np.ndarray):
            self._embedding = value.tolist()
        else:
            self._embedding = list(value)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'content': self.content,
            'status': self.status.value,
            'planted_at': self.planted_at,
            'resolved_at': self.resolved_at,
            'related_entities': self.related_entities,
            'hints': self.hints,
            'resolution': self.resolution,
            'importance': self.importance,
            '_embedding': self._embedding  # 保存原始List
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Foreshadowing':
        """从字典创建（兼容旧数据：无embedding字段）"""
        data = data.copy()
        data['status'] = ForeshadowingStatus(data['status'])
        # 向后兼容：旧数据可能没有 _embedding 字段
        if '_embedding' not in data:
            data['_embedding'] = None
        return cls(**data)


class ForeshadowingTracker:
    """伏笔追踪器 - 支持多角色分隔存储
    
    三级语义去重策略：
    1. Embedding余弦相似度（快速过滤）- 相似度>=0.85自动合并
    2. 完全相同检测（精确匹配）
    3. 词重叠后备方案（兼容无Embedding场景）
    
    配置通过环境变量控制：
    - DEDUP_EMBEDDING_ENABLED: 是否启用Embedding去重
    - DEDUP_HIGH_THRESHOLD: 高相似度阈值（自动合并）
    - DEDUP_LOW_THRESHOLD: 低相似度阈值（视为不同）
    """
    
    # 词重叠相似度阈值（后备方案）
    WORD_SIMILARITY_THRESHOLD = 0.6
    
    def __init__(self, storage_dir: Optional[str] = None, embedding_backend: Optional[Any] = None):
        """
        Args:
            storage_dir: 存储目录路径，每个角色的伏笔存储在单独的文件中
            embedding_backend: Embedding后端（可选），用于语义去重
        """
        self.storage_dir = storage_dir
        self.embedding_backend = embedding_backend
        # 按 user_id 分隔的伏笔存储
        self._user_data: Dict[str, Dict[str, Any]] = {}
        
        if storage_dir:
            os.makedirs(storage_dir, exist_ok=True)
    
    @staticmethod
    def _get_dedup_config() -> Dict[str, Any]:
        """获取去重配置（从环境变量）"""
        return {
            'enabled': os.environ.get('DEDUP_EMBEDDING_ENABLED', 'true').lower() in ('true', '1', 'yes'),
            'high_threshold': float(os.environ.get('DEDUP_HIGH_THRESHOLD', '0.85')),
            'low_threshold': float(os.environ.get('DEDUP_LOW_THRESHOLD', '0.70'))
        }
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本的Embedding向量"""
        if not self.embedding_backend:
            return None
        
        try:
            embeddings = self.embedding_backend.embed([text])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"获取Embedding失败: {e}")
        
        return None
    
    def _compute_embedding_similarity(self, emb1: List[float], emb2: List[float]) -> float:
        """计算两个Embedding向量的余弦相似度"""
        if not emb1 or not emb2:
            return 0.0
        
        vec1 = np.array(emb1)
        vec2 = np.array(emb2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def _compute_word_similarity(self, text1: str, text2: str) -> float:
        """计算词重叠相似度（后备方案）"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if len(words1) <= 2:
            words1 = set(text1.lower())
            words2 = set(text2.lower())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0
    
    def _find_similar(self, content: str, user_id: str, 
                     new_embedding: Optional[List[float]] = None) -> Tuple[Optional[Foreshadowing], float, str]:
        """查找语义相似的已有伏笔
        
        Returns:
            Tuple[Optional[Foreshadowing], float, str]: (相似伏笔或None, 相似度, 方法)
        """
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        dedup_config = self._get_dedup_config()
        best_match: Optional[Foreshadowing] = None
        best_sim = 0.0
        best_method = "none"
        
        for fsh in foreshadowings.values():
            # 只检查活跃的伏笔
            if fsh.status not in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.DEVELOPING):
                continue
            
            # 完全相同
            if fsh.content.lower().strip() == content.lower().strip():
                return (fsh, 1.0, "exact")
            
            # 计算相似度
            if dedup_config['enabled']:
                # 尝试获取缺失的Embedding
                emb1 = fsh._embedding
                emb2 = new_embedding
                if emb2 is None:
                    emb2 = self._get_embedding(content)
                
                if emb1 is not None and emb2 is not None:
                    sim = self._compute_embedding_similarity(emb1, emb2)
                    method = "embedding"
                else:
                    sim = self._compute_word_similarity(fsh.content, content)
                    method = "word"
            else:
                sim = self._compute_word_similarity(fsh.content, content)
                method = "word"
            
            if sim > best_sim:
                best_sim = sim
                best_match = fsh
                best_method = method
        
        # 判断是否达到合并阈值
        if best_match:
            if best_method == "embedding":
                if best_sim >= dedup_config['high_threshold']:
                    return (best_match, best_sim, best_method)
                elif best_sim < dedup_config['low_threshold']:
                    return (None, best_sim, best_method)
                else:
                    return (best_match, best_sim, best_method + "_uncertain")
            else:
                if best_sim >= self.WORD_SIMILARITY_THRESHOLD:
                    return (best_match, best_sim, best_method)
        
        return (None, best_sim, best_method)
    
    def _get_user_storage_path(self, user_id: str) -> str:
        """获取用户的存储路径"""
        # 清理文件名中的非法字符
        safe_user_id = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in user_id)
        return os.path.join(self.storage_dir, f"foreshadowing_{safe_user_id}.json")
    
    def _load_user_data(self, user_id: str) -> Dict[str, Any]:
        """加载用户的伏笔数据"""
        if user_id in self._user_data:
            return self._user_data[user_id]
        
        data = {
            'id_counter': 0,
            'foreshadowings': {}
        }
        
        if self.storage_dir:
            path = self._get_user_storage_path(user_id)
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                    data['id_counter'] = loaded.get('id_counter', 0)
                    data['foreshadowings'] = {
                        k: Foreshadowing.from_dict(v)
                        for k, v in loaded.get('foreshadowings', {}).items()
                    }
                except Exception as e:
                    print(f"[Recall] 加载伏笔数据失败 ({user_id}): {e}")
        
        self._user_data[user_id] = data
        return data
    
    def _save_user_data(self, user_id: str):
        """保存用户的伏笔数据"""
        if not self.storage_dir:
            return
        
        data = self._user_data.get(user_id, {})
        if not data:
            return
        
        path = self._get_user_storage_path(user_id)
        save_data = {
            'id_counter': data.get('id_counter', 0),
            'foreshadowings': {
                k: v.to_dict() for k, v in data.get('foreshadowings', {}).items()
            }
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    def plant(
        self,
        content: str,
        user_id: str = "default",
        related_entities: Optional[List[str]] = None,
        importance: float = 0.5
    ) -> Foreshadowing:
        """埋下伏笔
        
        智能处理（三级去重策略）：
        1. 计算新内容的Embedding（如果启用）
        2. 查找语义相似的已有伏笔
        3. 高相似度：增加重要性而非新建
        4. 低相似度或无匹配：创建新伏笔
        
        Returns:
            Foreshadowing: 新建或已存在的伏笔对象
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 1. 预计算Embedding
        new_embedding = self._get_embedding(content)
        
        # 2. 查找相似伏笔
        similar, sim_score, sim_method = self._find_similar(
            content, user_id, new_embedding=new_embedding
        )
        
        if similar:
            logger.debug(f"[ForeshadowingTracker] 发现相似伏笔 (方法={sim_method}, 相似度={sim_score:.3f}): "
                        f"'{content[:30]}...' ≈ '{similar.content[:30]}...'")
            
            # 合并策略：增加重要性
            if sim_method == "exact":
                # 完全相同，只增加重要性
                similar.importance = min(1.0, similar.importance + 0.1)
            elif sim_method.endswith("_uncertain"):
                # 中等相似度，小幅增加
                similar.importance = min(1.0, similar.importance + 0.05)
                # 如果新内容更详细，更新内容
                if len(content) > len(similar.content) * 1.2:
                    similar.content = content
                    if new_embedding:
                        similar.embedding = new_embedding
            else:
                # 高度相似，正常增加
                similar.importance = min(1.0, similar.importance + 0.1)
                if len(content) > len(similar.content):
                    similar.content = content
                    if new_embedding:
                        similar.embedding = new_embedding
            
            # 合并相关实体
            if related_entities:
                for entity in related_entities:
                    if entity not in similar.related_entities:
                        similar.related_entities.append(entity)
            
            self._save_user_data(user_id)
            return similar
        
        # 3. 创建新伏笔
        user_data = self._load_user_data(user_id)
        user_data['id_counter'] += 1
        
        foreshadowing_id = f"fsh_{user_data['id_counter']}_{int(time.time())}"
        
        foreshadowing = Foreshadowing(
            id=foreshadowing_id,
            content=content,
            status=ForeshadowingStatus.PLANTED,
            related_entities=related_entities or [],
            importance=importance
        )
        
        # 存储Embedding
        if new_embedding:
            foreshadowing.embedding = new_embedding
        
        user_data['foreshadowings'][foreshadowing_id] = foreshadowing
        self._save_user_data(user_id)
        
        return foreshadowing
    
    def add_hint(self, foreshadowing_id: str, hint: str, user_id: str = "default") -> bool:
        """添加伏笔提示"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        fsh = foreshadowings[foreshadowing_id]
        fsh.hints.append(hint)
        
        if fsh.status == ForeshadowingStatus.PLANTED:
            fsh.status = ForeshadowingStatus.DEVELOPING
        
        self._save_user_data(user_id)
        return True
    
    def resolve(self, foreshadowing_id: str, resolution: str, user_id: str = "default") -> bool:
        """解决伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        fsh = foreshadowings[foreshadowing_id]
        fsh.status = ForeshadowingStatus.RESOLVED
        fsh.resolution = resolution
        fsh.resolved_at = time.time()
        
        self._save_user_data(user_id)
        return True
    
    def abandon(self, foreshadowing_id: str, user_id: str = "default") -> bool:
        """放弃伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        foreshadowings[foreshadowing_id].status = ForeshadowingStatus.ABANDONED
        self._save_user_data(user_id)
        return True
    
    def get_active(self, user_id: str = "default") -> List[Foreshadowing]:
        """获取活跃的伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        return [
            f for f in foreshadowings.values()
            if f.status in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.DEVELOPING)
        ]
    
    def get_by_entity(self, entity_name: str, user_id: str = "default") -> List[Foreshadowing]:
        """获取与实体相关的伏笔"""
        user_data = self._load_user_data(user_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        return [
            f for f in foreshadowings.values()
            if entity_name in f.related_entities
        ]
    
    def get_summary(self, user_id: str = "default") -> str:
        """获取伏笔摘要"""
        active = self.get_active(user_id)
        if not active:
            return "当前没有活跃的伏笔。"
        
        lines = ["活跃的伏笔："]
        for f in sorted(active, key=lambda x: -x.importance):
            status_emoji = "🌱" if f.status == ForeshadowingStatus.PLANTED else "🌿"
            lines.append(f"  {status_emoji} {f.content[:50]}{'...' if len(f.content) > 50 else ''}")
            if f.hints:
                lines.append(f"     提示: {len(f.hints)} 条")
        
        return "\n".join(lines)
    
    def get_context_for_prompt(
        self,
        user_id: str = "default",
        max_count: int = 5,
        current_turn: Optional[int] = None
    ) -> str:
        """生成用于注入 prompt 的伏笔上下文
        
        Args:
            user_id: 用户ID
            max_count: 最多返回的伏笔数量
            current_turn: 当前轮次（用于主动提醒判断）
        
        Returns:
            str: 格式化的伏笔上下文，可直接注入 prompt
        """
        active = self.get_active(user_id)
        if not active:
            return ""
        
        # 按重要性排序，取前 max_count 个
        active = sorted(active, key=lambda x: -x.importance)[:max_count]
        
        lines = ["<foreshadowings>", "【活跃伏笔 - AI需要在适当时机推进或解决这些伏笔】"]
        
        for i, f in enumerate(active, 1):
            status = "埋下" if f.status == ForeshadowingStatus.PLANTED else "发展中"
            lines.append(f"{i}. [{status}] {f.content}")
            if f.hints:
                lines.append(f"   已有提示: {', '.join(f.hints[-3:])}")  # 只显示最近3条提示
            
            # 主动提醒逻辑：如果伏笔很重要且长时间未发展，提醒AI
            if current_turn and f.importance >= 0.7:
                age = (time.time() - f.planted_at) / 3600  # 小时
                if age > 2 and f.status == ForeshadowingStatus.PLANTED:
                    lines.append(f"   ⚠️ 这个重要伏笔已埋下较长时间，考虑推进或给出提示")
        
        lines.append("</foreshadowings>")
        return "\n".join(lines)


class ForeshadowingTrackerLite:
    """伏笔追踪器 - 轻量版（无持久化，支持多角色）"""
    
    def __init__(self):
        # 按 user_id 分隔
        self._user_foreshadowings: Dict[str, List[Dict[str, Any]]] = {}
    
    def plant(self, content: str, user_id: str = "default", **kwargs) -> Dict[str, Any]:
        """埋下伏笔"""
        if user_id not in self._user_foreshadowings:
            self._user_foreshadowings[user_id] = []
        
        fsh_list = self._user_foreshadowings[user_id]
        fsh = {
            'id': f"fsh_{len(fsh_list)}_{int(time.time())}",
            'content': content,
            'status': 'planted',
            'planted_at': time.time(),
            'importance': kwargs.get('importance', 0.5),
            'related_entities': kwargs.get('related_entities', []),
            'hints': [],
            'resolution': None
        }
        fsh_list.append(fsh)
        return fsh
    
    def get_active(self, user_id: str = "default") -> List[Dict[str, Any]]:
        """获取活跃伏笔"""
        fsh_list = self._user_foreshadowings.get(user_id, [])
        return [f for f in fsh_list if f.get('status') in ('planted', 'developing')]
    
    def resolve(self, foreshadowing_id: str, resolution: str, user_id: str = "default") -> bool:
        """解决伏笔"""
        fsh_list = self._user_foreshadowings.get(user_id, [])
        for fsh in fsh_list:
            if fsh['id'] == foreshadowing_id:
                fsh['status'] = 'resolved'
                fsh['resolution'] = resolution
                return True
        return False

