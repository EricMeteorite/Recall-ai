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


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))




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
        """从字典创建（兼容旧数据和归档数据）"""
        data = data.copy()
        data['status'] = ForeshadowingStatus(data['status'])
        # 向后兼容：旧数据可能没有 _embedding 字段
        if '_embedding' not in data:
            data['_embedding'] = None
        # 移除归档时添加的额外字段（这些字段不是 Foreshadowing 的属性）
        data.pop('archived_at', None)
        data.pop('archive_reason', None)
        return cls(**data)


class ForeshadowingTracker:
    """伏笔追踪器 - 支持多用户/多角色分隔存储
    
    存储结构：{base_path}/{user_id}/{character_id}/foreshadowings.json
    归档结构：{base_path}/{user_id}/{character_id}/archive/foreshadowings.jsonl
    与 MultiTenantStorage 保持一致的路径结构。
    
    三级语义去重策略：
    1. Embedding余弦相似度（快速过滤）- 相似度>=0.85自动合并
    2. 完全相同检测（精确匹配）
    3. 词重叠后备方案（兼容无Embedding场景）
    
    归档机制：
    - resolved/abandoned 状态的伏笔自动归档
    - 超过 MAX_ACTIVE 上限时，按优先级归档低重要性伏笔
    
    配置通过环境变量控制：
    - DEDUP_EMBEDDING_ENABLED: 是否启用Embedding去重
    - DEDUP_HIGH_THRESHOLD: 高相似度阈值（自动合并）
    - DEDUP_LOW_THRESHOLD: 低相似度阈值（视为不同）
    - FORESHADOWING_MAX_RETURN: 伏笔召回数量
    - FORESHADOWING_MAX_ACTIVE: 活跃伏笔数量上限
    """
    
    # 词重叠相似度阈值（后备方案）
    WORD_SIMILARITY_THRESHOLD = 0.6
    # 归档文件最大大小（10MB），超过则分卷
    MAX_ARCHIVE_FILE_SIZE = 10 * 1024 * 1024
    
    @staticmethod
    def _get_limits_config():
        """获取限制配置（每次调用时读取，支持热更新）"""
        return {
            'max_return': int(os.environ.get('FORESHADOWING_MAX_RETURN', '10')),
            'max_active': int(os.environ.get('FORESHADOWING_MAX_ACTIVE', '50')),
        }
    
    def __init__(self, base_path: Optional[str] = None, embedding_backend: Optional[Any] = None,
                 storage_dir: Optional[str] = None):
        """
        Args:
            base_path: 数据根目录路径（新参数，推荐使用）
                      存储结构：{base_path}/{user_id}/{character_id}/foreshadowings.json
            embedding_backend: Embedding后端（可选），用于语义去重
            storage_dir: 旧参数（向后兼容），如果提供则自动迁移到新结构
        """
        # 向后兼容：如果提供了 storage_dir 而非 base_path
        if storage_dir and not base_path:
            # 旧的 storage_dir 格式是 {data_root}/data/foreshadowings
            # 新的 base_path 格式是 {data_root}/data
            if storage_dir.endswith('foreshadowings'):
                base_path = os.path.dirname(storage_dir)
            else:
                base_path = storage_dir
        
        self.base_path = base_path
        self.embedding_backend = embedding_backend
        # 按 {user_id}/{character_id} 分隔的伏笔存储
        self._user_data: Dict[str, Dict[str, Any]] = {}
        
        if base_path:
            os.makedirs(base_path, exist_ok=True)
    
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
    
    def _find_similar(self, content: str, user_id: str, character_id: str = "default",
                     new_embedding: Optional[List[float]] = None) -> Tuple[Optional[Foreshadowing], float, str]:
        """查找语义相似的已有伏笔
        
        Returns:
            Tuple[Optional[Foreshadowing], float, str]: (相似伏笔或None, 相似度, 方法)
        """
        user_data = self._load_user_data(user_id, character_id)
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
                # 优化：直接使用传入的 embedding，不在循环内调用 API
                # emb1: 已有伏笔的 embedding（从存储中读取）
                # new_embedding: 新内容的 embedding（调用方预先计算好）
                emb1 = fsh._embedding
                
                if emb1 is not None and new_embedding is not None:
                    sim = self._compute_embedding_similarity(emb1, new_embedding)
                    method = "embedding"
                else:
                    # 如果任意一方没有 embedding，回退到词重叠
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
    
    def _sanitize_path_component(self, name: str) -> str:
        """清理路径组件中的非法字符"""
        return "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in name)
    
    def _get_cache_key(self, user_id: str, character_id: str) -> str:
        """获取内部缓存键"""
        return f"{user_id}/{character_id}"
    
    def _get_storage_path(self, user_id: str, character_id: str) -> str:
        """获取存储路径
        
        新结构：{base_path}/{user_id}/{character_id}/foreshadowings.json
        """
        safe_user_id = self._sanitize_path_component(user_id)
        safe_char_id = self._sanitize_path_component(character_id)
        return os.path.join(self.base_path, safe_user_id, safe_char_id, 'foreshadowings.json')
    
    def _load_user_data(self, user_id: str, character_id: str = "default") -> Dict[str, Any]:
        """加载用户/角色的伏笔数据"""
        cache_key = self._get_cache_key(user_id, character_id)
        
        if cache_key in self._user_data:
            return self._user_data[cache_key]
        
        data = {
            'id_counter': 0,
            'foreshadowings': {}
        }
        
        if self.base_path:
            path = self._get_storage_path(user_id, character_id)
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
                    _safe_print(f"[Recall] 加载伏笔数据失败 ({user_id}/{character_id}): {e}")
        
        self._user_data[cache_key] = data
        return data
    
    def _save_user_data(self, user_id: str, character_id: str = "default"):
        """保存用户/角色的伏笔数据"""
        if not self.base_path:
            return
        
        cache_key = self._get_cache_key(user_id, character_id)
        data = self._user_data.get(cache_key, {})
        if not data:
            return
        
        path = self._get_storage_path(user_id, character_id)
        # 确保目录存在
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        save_data = {
            'id_counter': data.get('id_counter', 0),
            'foreshadowings': {
                k: v.to_dict() for k, v in data.get('foreshadowings', {}).items()
            }
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
    
    def _get_archive_path(self, user_id: str, character_id: str) -> str:
        """获取归档文件路径
        
        归档结构：{base_path}/{user_id}/{character_id}/archive/foreshadowings.jsonl
        超过 MAX_ARCHIVE_FILE_SIZE 时自动分卷
        """
        safe_user_id = self._sanitize_path_component(user_id)
        safe_char_id = self._sanitize_path_component(character_id)
        archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
        os.makedirs(archive_dir, exist_ok=True)
        
        archive_file = os.path.join(archive_dir, 'foreshadowings.jsonl')
        
        # 检查是否需要分卷
        if os.path.exists(archive_file) and os.path.getsize(archive_file) > self.MAX_ARCHIVE_FILE_SIZE:
            # 重命名为带编号的文件
            index = 1
            while os.path.exists(os.path.join(archive_dir, f'foreshadowings_{index:03d}.jsonl')):
                index += 1
            os.rename(archive_file, os.path.join(archive_dir, f'foreshadowings_{index:03d}.jsonl'))
        
        return archive_file
    
    def _archive_foreshadowing(self, fsh: Foreshadowing, user_id: str, character_id: str,
                                reason: str = None):
        """将伏笔归档到 archive/foreshadowings.jsonl
        
        Args:
            fsh: 要归档的伏笔
            user_id: 用户ID
            character_id: 角色ID
            reason: 归档原因（如果不提供，则根据状态自动判断）
        """
        if not self.base_path:
            return
        
        archive_path = self._get_archive_path(user_id, character_id)
        
        # 准备归档数据
        archive_data = fsh.to_dict()
        archive_data['archived_at'] = time.time()
        # 根据状态自动判断归档原因
        if reason:
            archive_data['archive_reason'] = reason
        elif fsh.status == ForeshadowingStatus.RESOLVED:
            archive_data['archive_reason'] = 'resolved'
        elif fsh.status == ForeshadowingStatus.ABANDONED:
            archive_data['archive_reason'] = 'abandoned'
        else:
            archive_data['archive_reason'] = 'overflow'
        
        # 追加写入 JSONL 格式
        with open(archive_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(archive_data, ensure_ascii=False) + '\n')
    
    def _archive_overflow_foreshadowings(self, user_id: str, character_id: str):
        """当超过上限时，归档优先级最低的伏笔
        
        排序策略：优先归档 importance 最低的，其次是最旧的
        """
        max_active = self._get_limits_config()['max_active']
        
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        # 只计算活跃伏笔
        active_items = [
            (fsh_id, fsh) for fsh_id, fsh in foreshadowings.items()
            if fsh.status in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.DEVELOPING)
        ]
        
        if len(active_items) <= max_active:
            return
        
        # 按优先级排序：importance 升序，planted_at 升序（最旧的优先归档）
        sorted_items = sorted(
            active_items,
            key=lambda x: (x[1].importance, x[1].planted_at)
        )
        
        # 计算需要归档的数量
        to_archive_count = len(active_items) - max_active
        to_archive = sorted_items[:to_archive_count]
        
        # 执行归档
        for fsh_id, fsh in to_archive:
            # 标记为 ABANDONED（因为是被系统自动归档的）
            fsh.status = ForeshadowingStatus.ABANDONED
            fsh.resolution = "[系统自动归档：超出活跃数量上限]"
            self._archive_foreshadowing(fsh, user_id, character_id, reason='overflow')
            del foreshadowings[fsh_id]
        
        self._save_user_data(user_id, character_id)
    
    def get_by_id(self, foreshadowing_id: str, user_id: str = "default",
                  character_id: str = "default") -> Optional[Foreshadowing]:
        """获取伏笔（包括已归档的）
        
        先查活跃伏笔，未找到则查归档文件
        """
        # 1. 先查活跃伏笔
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        if foreshadowing_id in foreshadowings:
            return foreshadowings[foreshadowing_id]
        
        # 2. 查归档文件
        if self.base_path:
            safe_user_id = self._sanitize_path_component(user_id)
            safe_char_id = self._sanitize_path_component(character_id)
            archive_dir = os.path.join(self.base_path, safe_user_id, safe_char_id, 'archive')
            
            if os.path.exists(archive_dir):
                # 搜索所有归档文件
                for filename in os.listdir(archive_dir):
                    if filename.startswith('foreshadowings') and filename.endswith('.jsonl'):
                        archive_path = os.path.join(archive_dir, filename)
                        try:
                            with open(archive_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if line.strip():
                                        fsh_data = json.loads(line)
                                        if fsh_data.get('id') == foreshadowing_id:
                                            return Foreshadowing.from_dict(fsh_data)
                        except Exception:
                            pass
        
        return None

    def get_archived_foreshadowings(
        self,
        user_id: str = "default",
        character_id: str = "default",
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取归档的伏笔列表（分页、搜索、筛选）
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            page: 页码（从1开始）
            page_size: 每页数量
            search: 搜索关键词（搜索内容）
            status: 状态筛选（resolved/abandoned）
            
        Returns:
            Dict: {
                'items': List[Dict],  # 当前页的伏笔列表
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
                    if filename.startswith('foreshadowings') and filename.endswith('.jsonl'):
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
        
        # 筛选：状态
        if status:
            all_archived = [f for f in all_archived if f.get('status') == status]
        
        # 筛选：搜索
        if search:
            search_lower = search.lower()
            all_archived = [f for f in all_archived if search_lower in f.get('content', '').lower()]
        
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
        foreshadowing_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> Optional[Foreshadowing]:
        """从归档恢复伏笔到活跃列表
        
        Args:
            foreshadowing_id: 伏笔ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            Optional[Foreshadowing]: 恢复的伏笔，未找到返回 None
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
            if not (filename.startswith('foreshadowings') and filename.endswith('.jsonl')):
                continue
            
            archive_path = os.path.join(archive_dir, filename)
            lines_to_keep = []
            
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('id') == foreshadowing_id and found_data is None:
                                found_data = data
                            else:
                                lines_to_keep.append(line)
                
                if found_data:
                    # 重写归档文件（移除已恢复的伏笔）
                    with open(archive_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines_to_keep)
                    break
            except Exception as e:
                logger.error(f"[ForeshadowingTracker] 读取归档文件失败: {e}")
        
        if not found_data:
            return None
        
        # 移除归档字段，创建 Foreshadowing 对象
        found_data.pop('archived_at', None)
        found_data.pop('archive_reason', None)
        fsh = Foreshadowing.from_dict(found_data)
        # 恢复为活跃状态
        fsh.status = ForeshadowingStatus.PLANTED
        fsh.resolution = None
        fsh.resolved_at = None
        
        # 添加到活跃列表
        user_data = self._load_user_data(user_id, character_id)
        user_data['foreshadowings'][fsh.id] = fsh
        self._save_user_data(user_id, character_id)
        
        logger.info(f"[ForeshadowingTracker] 已从归档恢复伏笔: {foreshadowing_id}")
        return fsh

    def delete_archived(
        self,
        foreshadowing_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """彻底删除归档中的伏笔
        
        Args:
            foreshadowing_id: 伏笔ID
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
            if not (filename.startswith('foreshadowings') and filename.endswith('.jsonl')):
                continue
            
            archive_path = os.path.join(archive_dir, filename)
            lines_to_keep = []
            
            try:
                with open(archive_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get('id') == foreshadowing_id:
                                deleted = True
                            else:
                                lines_to_keep.append(line)
                
                if deleted:
                    with open(archive_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines_to_keep)
                    logger.info(f"[ForeshadowingTracker] 已彻底删除归档伏笔: {foreshadowing_id}")
                    break
            except Exception as e:
                logger.error(f"[ForeshadowingTracker] 删除归档伏笔失败: {e}")
        
        return deleted

    def clear_archived(
        self,
        user_id: str = "default",
        character_id: str = "default"
    ) -> int:
        """清空所有归档伏笔
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            int: 删除的伏笔数量
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
            if filename.startswith('foreshadowings') and filename.endswith('.jsonl'):
                archive_path = os.path.join(archive_dir, filename)
                try:
                    # 统计行数
                    with open(archive_path, 'r', encoding='utf-8') as f:
                        count += sum(1 for line in f if line.strip())
                    # 删除文件
                    os.remove(archive_path)
                except Exception as e:
                    logger.error(f"[ForeshadowingTracker] 清空归档文件失败: {e}")
        
        logger.info(f"[ForeshadowingTracker] 已清空归档伏笔: {count} 个")
        return count

    def archive_foreshadowing(
        self,
        foreshadowing_id: str,
        user_id: str = "default",
        character_id: str = "default"
    ) -> bool:
        """手动将活跃伏笔归档
        
        Args:
            foreshadowing_id: 伏笔ID
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            bool: 是否成功归档
        """
        import logging
        logger = logging.getLogger(__name__)
        
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        fsh = foreshadowings.pop(foreshadowing_id)
        fsh.status = ForeshadowingStatus.ABANDONED
        fsh.resolution = "[手动归档]"
        
        self._archive_foreshadowing(fsh, user_id, character_id, reason='manual')
        self._save_user_data(user_id, character_id)
        
        logger.info(f"[ForeshadowingTracker] 已手动归档伏笔: {foreshadowing_id}")
        return True

    def update_foreshadowing(
        self,
        foreshadowing_id: str,
        user_id: str = "default",
        character_id: str = "default",
        content: Optional[str] = None,
        status: Optional[str] = None,
        importance: Optional[float] = None,
        hints: Optional[List[str]] = None,
        resolution: Optional[str] = None
    ) -> Optional[Foreshadowing]:
        """更新伏笔的字段
        
        Args:
            foreshadowing_id: 伏笔ID
            user_id: 用户ID
            character_id: 角色ID
            content: 新内容（可选）
            status: 新状态（可选）
            importance: 新重要性（可选）
            hints: 新提示列表（可选）
            resolution: 新解决方案（可选）
            
        Returns:
            Optional[Foreshadowing]: 更新后的伏笔，未找到返回 None
        """
        import logging
        logger = logging.getLogger(__name__)
        
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return None
        
        fsh = foreshadowings[foreshadowing_id]
        
        if content is not None:
            fsh.content = content
            # 更新 embedding
            new_embedding = self._get_embedding(content)
            if new_embedding:
                fsh.embedding = new_embedding
        if status is not None:
            try:
                fsh.status = ForeshadowingStatus(status)
            except ValueError:
                pass  # 保持原状态
        if importance is not None:
            fsh.importance = max(0.0, min(1.0, importance))
        if hints is not None:
            fsh.hints = hints
        if resolution is not None:
            fsh.resolution = resolution
        
        self._save_user_data(user_id, character_id)
        logger.info(f"[ForeshadowingTracker] 已更新伏笔: {foreshadowing_id}")
        return fsh

    def plant(
        self,
        content: str,
        user_id: str = "default",
        character_id: str = "default",
        related_entities: Optional[List[str]] = None,
        importance: float = 0.5
    ) -> Foreshadowing:
        """埋下伏笔
        
        智能处理（三级去重策略）：
        1. 计算新内容的Embedding（如果启用）
        2. 查找语义相似的已有伏笔
        3. 高相似度：增加重要性而非新建
        4. 低相似度或无匹配：创建新伏笔
        
        Args:
            content: 伏笔内容
            user_id: 用户ID
            character_id: 角色ID（RP场景）
            related_entities: 相关实体
            importance: 重要性（0-1）
        
        Returns:
            Foreshadowing: 新建或已存在的伏笔对象
        """
        import logging
        logger = logging.getLogger(__name__)
        
        content_preview = content[:50].replace('\n', ' ') if len(content) > 50 else content.replace('\n', ' ')
        _safe_print(f"[ForeshadowingTracker] 🌱 埋下伏笔: user={user_id}, char={character_id}")
        _safe_print(f"[ForeshadowingTracker]    内容: {content_preview}{'...' if len(content) > 50 else ''}")
        _safe_print(f"[ForeshadowingTracker]    重要性={importance}, 实体={related_entities}")
        
        # 1. 预计算Embedding
        new_embedding = self._get_embedding(content)
        
        # 2. 查找相似伏笔
        similar, sim_score, sim_method = self._find_similar(
            content, user_id, character_id, new_embedding=new_embedding
        )
        
        if similar:
            similar_preview = similar.content[:40].replace('\n', ' ')
            _safe_print(f"[ForeshadowingTracker] 🔄 发现相似伏笔:")
            _safe_print(f"[ForeshadowingTracker]    方法={sim_method}, 相似度={sim_score:.3f}")
            _safe_print(f"[ForeshadowingTracker]    已有: {similar_preview}...")
            
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
            
            self._save_user_data(user_id, character_id)
            return similar
        
        # 3. 创建新伏笔
        user_data = self._load_user_data(user_id, character_id)
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
        self._save_user_data(user_id, character_id)
        
        _safe_print(f"[ForeshadowingTracker] ✅ 新伏笔已创建: id={foreshadowing_id}")
        
        # 检查是否超出活跃伏笔数量限制，如果超出则归档最旧的
        self._archive_overflow_foreshadowings(user_id, character_id)
        
        # 重新加载用户数据，检查伏笔是否仍然存在（可能在溢出归档中被删除）
        # 即使被归档，也返回伏笔对象（包含完整信息），调用者可检查 id 是否仍在活跃列表
        return foreshadowing
    
    def add_hint(self, foreshadowing_id: str, hint: str, user_id: str = "default",
                 character_id: str = "default") -> bool:
        """添加伏笔提示"""
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            return False
        
        fsh = foreshadowings[foreshadowing_id]
        fsh.hints.append(hint)
        
        if fsh.status == ForeshadowingStatus.PLANTED:
            fsh.status = ForeshadowingStatus.DEVELOPING
        
        self._save_user_data(user_id, character_id)
        return True
    
    def resolve(self, foreshadowing_id: str, resolution: str, user_id: str = "default",
                character_id: str = "default") -> bool:
        """解决伏笔"""
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            _safe_print(f"[ForeshadowingTracker] ❌ 解决失败: 伏笔不存在 id={foreshadowing_id}")
            return False
        
        fsh = foreshadowings[foreshadowing_id]
        fsh.status = ForeshadowingStatus.RESOLVED
        fsh.resolution = resolution
        fsh.resolved_at = time.time()
        
        _safe_print(f"[ForeshadowingTracker] ✅ 伏笔已解决: id={foreshadowing_id}")
        _safe_print(f"[ForeshadowingTracker]    内容: {fsh.content[:50]}...")
        _safe_print(f"[ForeshadowingTracker]    解决: {resolution[:50]}..." if len(resolution) > 50 else f"[ForeshadowingTracker]    解决: {resolution}")
        
        # 归档已解决的伏笔并从活跃列表移除
        self._archive_foreshadowing(fsh, user_id, character_id)
        del foreshadowings[foreshadowing_id]
        
        self._save_user_data(user_id, character_id)
        return True
    
    def abandon(self, foreshadowing_id: str, user_id: str = "default",
                character_id: str = "default") -> bool:
        """放弃伏笔"""
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        if foreshadowing_id not in foreshadowings:
            _safe_print(f"[ForeshadowingTracker] ❌ 放弃失败: 伏笔不存在 id={foreshadowing_id}")
            return False
        
        fsh = foreshadowings[foreshadowing_id]
        fsh.status = ForeshadowingStatus.ABANDONED
        
        _safe_print(f"[ForeshadowingTracker] 🗑️ 伏笔已放弃: id={foreshadowing_id}")
        _safe_print(f"[ForeshadowingTracker]    内容: {fsh.content[:50]}...")
        
        # 归档已放弃的伏笔并从活跃列表移除
        self._archive_foreshadowing(fsh, user_id, character_id)
        del foreshadowings[foreshadowing_id]
        
        self._save_user_data(user_id, character_id)
        return True
    
    def get_active(self, user_id: str = "default", character_id: str = "default") -> List[Foreshadowing]:
        """获取活跃的伏笔"""
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        return [
            f for f in foreshadowings.values()
            if f.status in (ForeshadowingStatus.PLANTED, ForeshadowingStatus.DEVELOPING)
        ]
    
    def get_by_entity(self, entity_name: str, user_id: str = "default",
                      character_id: str = "default") -> List[Foreshadowing]:
        """获取与实体相关的伏笔"""
        user_data = self._load_user_data(user_id, character_id)
        foreshadowings = user_data.get('foreshadowings', {})
        
        return [
            f for f in foreshadowings.values()
            if entity_name in f.related_entities
        ]
    
    def get_summary(self, user_id: str = "default", character_id: str = "default") -> str:
        """获取伏笔摘要"""
        active = self.get_active(user_id, character_id)
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
        character_id: str = "default",
        max_count: Optional[int] = None,
        current_turn: Optional[int] = None
    ) -> str:
        """生成用于注入 prompt 的伏笔上下文
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            max_count: 最多返回的伏笔数量（默认从环境变量 FORESHADOWING_MAX_RETURN 读取）
            current_turn: 当前轮次（用于主动提醒判断）
        
        Returns:
            str: 格式化的伏笔上下文，可直接注入 prompt
        """
        # 从环境变量读取默认值
        if max_count is None:
            max_count = self._get_limits_config()['max_return']
        
        active = self.get_active(user_id, character_id)
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
    """伏笔追踪器 - 轻量版（无持久化）
    
    注意：此轻量版不支持多角色分隔存储，character_id 参数被忽略。
    如需多角色支持，请使用 ForeshadowingTracker。
    """
    
    def __init__(self):
        # 按 user_id 分隔
        self._user_foreshadowings: Dict[str, List[Dict[str, Any]]] = {}
    
    def plant(self, content: str, user_id: str = "default", character_id: str = "default",
              **kwargs) -> Dict[str, Any]:
        """埋下伏笔
        
        注意：character_id 在轻量版中被忽略
        """
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
    
    def get_active(self, user_id: str = "default", character_id: str = "default") -> List[Dict[str, Any]]:
        """获取活跃伏笔
        
        注意：character_id 在轻量版中被忽略
        """
        fsh_list = self._user_foreshadowings.get(user_id, [])
        return [f for f in fsh_list if f.get('status') in ('planted', 'developing')]
    
    def resolve(self, foreshadowing_id: str, resolution: str, user_id: str = "default",
                character_id: str = "default") -> bool:
        """解决伏笔
        
        注意：character_id 在轻量版中被忽略
        """
        fsh_list = self._user_foreshadowings.get(user_id, [])
        for fsh in fsh_list:
            if fsh['id'] == foreshadowing_id:
                fsh['status'] = 'resolved'
                fsh['resolution'] = resolution
                return True
        return False

