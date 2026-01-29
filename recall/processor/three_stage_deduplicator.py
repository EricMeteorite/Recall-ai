"""三阶段去重系统 - Recall 4.0 Phase 2

设计理念：
1. 阶段 1: 确定性匹配 - 精确匹配 + MinHash + LSH（O(1) 快速）
2. 阶段 2: 语义匹配 - Embedding 相似度（成本较低）
3. 阶段 3: LLM 确认 - 仅用于边界情况（成本较高）

超越 Graphiti 的两阶段去重，增加语义匹配层，显著降低 LLM 成本。
"""

from __future__ import annotations

import os
import json
import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Optional, Tuple, Any, Callable
from enum import Enum
from collections import defaultdict


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


# 可选导入
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class MatchType(str, Enum):
    """匹配类型"""
    EXACT = "exact"         # 精确匹配
    FUZZY = "fuzzy"         # MinHash/LSH 模糊匹配
    SEMANTIC = "semantic"   # 语义相似
    LLM = "llm"             # LLM 确认
    NEW = "new"             # 新实体


@dataclass
class DedupItem:
    """待去重的项目"""
    id: str
    name: str
    content: str = ""
    item_type: str = "entity"
    attributes: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def get_text(self) -> str:
        """获取用于去重的文本"""
        return self.content or self.name


@dataclass 
class DedupMatch:
    """去重匹配结果"""
    new_item: DedupItem
    matched_item: Optional[DedupItem]
    match_type: MatchType
    confidence: float
    reason: str = ""


@dataclass
class DedupResult:
    """去重结果"""
    matches: List[DedupMatch] = field(default_factory=list)
    new_items: List[DedupItem] = field(default_factory=list)
    pending_items: List[Tuple[DedupItem, List[DedupItem]]] = field(default_factory=list)
    
    # 统计
    total_count: int = 0
    matched_count: int = 0
    new_count: int = 0
    pending_count: int = 0
    
    def add_match(
        self,
        new_item: DedupItem,
        matched_item: DedupItem,
        match_type: MatchType,
        confidence: float,
        reason: str = ""
    ):
        """添加匹配"""
        self.matches.append(DedupMatch(
            new_item=new_item,
            matched_item=matched_item,
            match_type=match_type,
            confidence=confidence,
            reason=reason
        ))
        self.matched_count += 1
    
    def add_new(self, item: DedupItem):
        """添加新项目"""
        self.new_items.append(item)
        self.new_count += 1
    
    def add_pending(self, item: DedupItem, candidates: List[DedupItem]):
        """添加待确认项目"""
        self.pending_items.append((item, candidates))
        self.pending_count += 1
    
    def move_to_match(
        self,
        item: DedupItem,
        matched_item: DedupItem,
        match_type: MatchType
    ):
        """将待确认项移动到匹配列表"""
        # 从 pending 中移除
        self.pending_items = [
            (i, c) for i, c in self.pending_items
            if i.id != item.id
        ]
        self.pending_count = len(self.pending_items)
        
        # 添加到匹配
        self.add_match(item, matched_item, match_type, 0.9, "LLM confirmed")
    
    def move_to_new(self, item: DedupItem):
        """将待确认项移动到新项目列表"""
        self.pending_items = [
            (i, c) for i, c in self.pending_items
            if i.id != item.id
        ]
        self.pending_count = len(self.pending_items)
        self.add_new(item)


@dataclass
class DedupConfig:
    """去重配置"""
    # 阶段 1: 确定性匹配
    exact_match_enabled: bool = True
    fuzzy_match_enabled: bool = True
    jaccard_threshold: float = 0.7          # Jaccard 相似度阈值
    minhash_num_perm: int = 128             # MinHash 排列数
    lsh_threshold: float = 0.5              # LSH 阈值
    
    # 阶段 2: 语义匹配
    semantic_enabled: bool = True
    semantic_threshold: float = 0.85        # 语义相似度阈值（高于此视为相同）
    semantic_low_threshold: float = 0.70    # 语义低阈值（低于此视为不同）
    
    # 阶段 3: LLM 确认
    llm_enabled: bool = False               # 是否启用 LLM 确认
    llm_threshold: float = 0.75             # 进入 LLM 确认的阈值范围（0.70-0.85 之间）
    llm_batch_size: int = 5                 # LLM 批量确认大小
    
    @classmethod
    def default(cls) -> 'DedupConfig':
        """默认配置"""
        return cls()
    
    @classmethod
    def strict(cls) -> 'DedupConfig':
        """严格模式（更高阈值）"""
        return cls(
            jaccard_threshold=0.8,
            semantic_threshold=0.90,
            semantic_low_threshold=0.75
        )
    
    @classmethod
    def lenient(cls) -> 'DedupConfig':
        """宽松模式（更低阈值）"""
        return cls(
            jaccard_threshold=0.6,
            semantic_threshold=0.80,
            semantic_low_threshold=0.65
        )


class MinHasher:
    """MinHash 实现（用于快速相似度估算）"""
    
    def __init__(self, num_perm: int = 128, seed: int = 42):
        self.num_perm = num_perm
        self.seed = seed
        
        # 生成哈希参数
        if HAS_NUMPY:
            np.random.seed(seed)
            max_hash = 2**32 - 1
            self.a = np.random.randint(1, max_hash, num_perm, dtype=np.uint64)
            self.b = np.random.randint(0, max_hash, num_perm, dtype=np.uint64)
        else:
            import random
            random.seed(seed)
            max_hash = 2**32 - 1
            self.a = [random.randint(1, max_hash) for _ in range(num_perm)]
            self.b = [random.randint(0, max_hash) for _ in range(num_perm)]
        
        self.max_hash = 2**32 - 1
    
    def get_shingles(self, text: str, k: int = 3) -> Set[str]:
        """获取 k-shingles"""
        text = text.lower().strip()
        if len(text) < k:
            return {text}
        return {text[i:i+k] for i in range(len(text) - k + 1)}
    
    def minhash(self, shingles: Set[str]) -> List[int]:
        """计算 MinHash 签名"""
        signature = [self.max_hash] * self.num_perm
        
        for shingle in shingles:
            h = int(hashlib.md5(shingle.encode()).hexdigest(), 16) % self.max_hash
            
            for i in range(self.num_perm):
                if HAS_NUMPY:
                    hash_val = int((self.a[i] * h + self.b[i]) % self.max_hash)
                else:
                    hash_val = (self.a[i] * h + self.b[i]) % self.max_hash
                signature[i] = min(signature[i], hash_val)
        
        return signature
    
    def jaccard_from_signatures(
        self,
        sig1: List[int],
        sig2: List[int]
    ) -> float:
        """从签名估算 Jaccard 相似度"""
        if len(sig1) != len(sig2):
            raise ValueError("签名长度不一致")
        
        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        return matches / len(sig1)


class LSHIndex:
    """LSH 索引（用于快速候选检索）"""
    
    def __init__(self, num_bands: int = 16, rows_per_band: int = 8):
        self.num_bands = num_bands
        self.rows_per_band = rows_per_band
        self.buckets: Dict[int, Dict[int, Set[str]]] = defaultdict(lambda: defaultdict(set))
    
    def add(self, item_id: str, signature: List[int]):
        """添加项目到索引"""
        for band_idx in range(self.num_bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            band = tuple(signature[start:end])
            bucket_hash = hash(band)
            self.buckets[band_idx][bucket_hash].add(item_id)
    
    def query(self, signature: List[int]) -> Set[str]:
        """查询候选项"""
        candidates = set()
        
        for band_idx in range(self.num_bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            band = tuple(signature[start:end])
            bucket_hash = hash(band)
            
            if bucket_hash in self.buckets[band_idx]:
                candidates.update(self.buckets[band_idx][bucket_hash])
        
        return candidates


class ThreeStageDeduplicator:
    """三阶段去重系统
    
    阶段 1: 确定性匹配
        - 精确匹配（归一化后）
        - MinHash + LSH 近似匹配
        
    阶段 2: 语义匹配
        - Embedding 向量相似度
        
    阶段 3: LLM 确认
        - 仅用于边界情况（semantic_low < sim < semantic_high）
    
    使用方式：
        dedup = ThreeStageDeduplicator(embedding_backend=backend)
        result = dedup.deduplicate(new_items, existing_items)
    """
    
    # LLM 确认 Prompt
    DEDUP_PROMPT = '''请判断以下两个实体/概念是否指代同一事物。

实体 A：{item_a}
实体 B：{item_b}

请回答：
- 如果是同一事物，回答 "YES"
- 如果不是同一事物，回答 "NO"
- 如果不确定，回答 "UNCERTAIN"

只回答 YES、NO 或 UNCERTAIN，不要解释。'''

    def __init__(
        self,
        config: Optional[DedupConfig] = None,
        embedding_backend: Any = None,      # EmbeddingBackend 实例
        llm_client: Any = None,             # LLMClient 实例
        budget_manager: Any = None          # BudgetManager 实例
    ):
        """初始化去重器
        
        Args:
            config: 去重配置
            embedding_backend: Embedding 后端（用于语义匹配）
            llm_client: LLM 客户端（用于边界情况确认）
            budget_manager: 预算管理器
        """
        self.config = config or DedupConfig.default()
        self.embedding_backend = embedding_backend
        self.llm_client = llm_client
        self.budget_manager = budget_manager
        
        # MinHash 和 LSH
        self.minhasher = MinHasher(num_perm=self.config.minhash_num_perm)
        self.lsh_index = LSHIndex()
        
        # 索引存储
        self._exact_map: Dict[str, DedupItem] = {}          # 归一化名称 -> 项目
        self._signature_map: Dict[str, List[int]] = {}      # ID -> MinHash 签名
        self._item_map: Dict[str, DedupItem] = {}           # ID -> 项目
    
    def _normalize(self, text: str) -> str:
        """文本归一化"""
        if not text:
            return ""
        
        # 转小写
        text = text.lower()
        
        # 移除标点和多余空白
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def build_index(self, items: List[DedupItem]):
        """构建索引
        
        Args:
            items: 现有项目列表
        """
        for item in items:
            # 精确匹配索引
            normalized = self._normalize(item.name)
            if normalized:
                self._exact_map[normalized] = item
            
            # MinHash + LSH 索引
            if self.config.fuzzy_match_enabled:
                shingles = self.minhasher.get_shingles(item.get_text())
                signature = self.minhasher.minhash(shingles)
                self._signature_map[item.id] = signature
                self.lsh_index.add(item.id, signature)
            
            # 项目映射
            self._item_map[item.id] = item
    
    def deduplicate(
        self,
        new_items: List[DedupItem],
        existing_items: Optional[List[DedupItem]] = None
    ) -> DedupResult:
        """执行去重
        
        Args:
            new_items: 新项目列表
            existing_items: 现有项目列表（如果未预先构建索引）
            
        Returns:
            DedupResult: 去重结果
        """
        # 如果提供了现有项目，构建索引
        if existing_items:
            self.build_index(existing_items)
        
        result = DedupResult()
        result.total_count = len(new_items)
        
        for item in new_items:
            match = self._deduplicate_single(item)
            
            if match.match_type == MatchType.NEW:
                result.add_new(item)
            elif match.match_type in (MatchType.EXACT, MatchType.FUZZY, MatchType.SEMANTIC, MatchType.LLM):
                result.matches.append(match)
                result.matched_count += 1
            else:
                # 待确认
                result.add_pending(item, [match.matched_item] if match.matched_item else [])
        
        # 阶段 3: LLM 批量确认待确认项
        if result.pending_items and self.config.llm_enabled and self.llm_client:
            self._llm_batch_confirm(result)
        
        return result
    
    def _deduplicate_single(self, item: DedupItem) -> DedupMatch:
        """对单个项目进行去重"""
        # === 阶段 1: 确定性匹配 ===
        
        # 1.1 精确匹配
        if self.config.exact_match_enabled:
            normalized = self._normalize(item.name)
            if normalized in self._exact_map:
                matched = self._exact_map[normalized]
                return DedupMatch(
                    new_item=item,
                    matched_item=matched,
                    match_type=MatchType.EXACT,
                    confidence=1.0,
                    reason="精确匹配（归一化后）"
                )
        
        # 1.2 MinHash + LSH 模糊匹配
        if self.config.fuzzy_match_enabled:
            shingles = self.minhasher.get_shingles(item.get_text())
            signature = self.minhasher.minhash(shingles)
            
            candidates = self.lsh_index.query(signature)
            
            if candidates:
                best_match = None
                best_jaccard = 0.0
                
                for candidate_id in candidates:
                    if candidate_id in self._signature_map:
                        candidate_sig = self._signature_map[candidate_id]
                        jaccard = self.minhasher.jaccard_from_signatures(signature, candidate_sig)
                        
                        if jaccard > best_jaccard:
                            best_jaccard = jaccard
                            best_match = self._item_map.get(candidate_id)
                
                if best_match and best_jaccard >= self.config.jaccard_threshold:
                    return DedupMatch(
                        new_item=item,
                        matched_item=best_match,
                        match_type=MatchType.FUZZY,
                        confidence=best_jaccard,
                        reason=f"MinHash+LSH 匹配 (Jaccard={best_jaccard:.3f})"
                    )
        
        # === 阶段 2: 语义匹配 ===
        if self.config.semantic_enabled and self.embedding_backend:
            semantic_match = self._semantic_match(item)
            if semantic_match:
                return semantic_match
        
        # 没有找到匹配
        return DedupMatch(
            new_item=item,
            matched_item=None,
            match_type=MatchType.NEW,
            confidence=0.0,
            reason="未找到匹配"
        )
    
    def _semantic_match(self, item: DedupItem) -> Optional[DedupMatch]:
        """语义匹配"""
        if not self.embedding_backend or not self._item_map:
            return None
        
        try:
            # 获取新项目的 embedding（使用缓存）
            if item.embedding:
                item_embedding = item.embedding
            else:
                # 使用带缓存的编码，减少 API 调用
                if hasattr(self.embedding_backend, 'encode_with_cache'):
                    item_embedding = self.embedding_backend.encode_with_cache(item.get_text())
                else:
                    item_embedding = self.embedding_backend.encode(item.get_text())
                if hasattr(item_embedding, 'tolist'):
                    item_embedding = item_embedding.tolist()
            
            # 与所有现有项目计算相似度
            best_match = None
            best_similarity = 0.0
            
            for existing_id, existing_item in self._item_map.items():
                # 获取现有项目的 embedding（优先使用缓存）
                if existing_item.embedding:
                    existing_embedding = existing_item.embedding
                else:
                    # 使用带缓存的编码，减少 API 调用
                    if hasattr(self.embedding_backend, 'encode_with_cache'):
                        existing_embedding = self.embedding_backend.encode_with_cache(existing_item.get_text())
                    else:
                        existing_embedding = self.embedding_backend.encode(existing_item.get_text())
                    if hasattr(existing_embedding, 'tolist'):
                        existing_embedding = existing_embedding.tolist()
                    existing_item.embedding = existing_embedding
                
                # 计算余弦相似度
                similarity = self._cosine_similarity(item_embedding, existing_embedding)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = existing_item
            
            # 根据阈值判断
            if best_similarity >= self.config.semantic_threshold:
                # 高相似度，直接匹配
                return DedupMatch(
                    new_item=item,
                    matched_item=best_match,
                    match_type=MatchType.SEMANTIC,
                    confidence=best_similarity,
                    reason=f"语义匹配 (similarity={best_similarity:.3f})"
                )
            elif best_similarity >= self.config.semantic_low_threshold:
                # 边界情况，需要 LLM 确认
                if self.config.llm_enabled:
                    return DedupMatch(
                        new_item=item,
                        matched_item=best_match,
                        match_type=MatchType.NEW,  # 暂时标记为新，等待 LLM 确认
                        confidence=best_similarity,
                        reason=f"边界情况，需 LLM 确认 (similarity={best_similarity:.3f})"
                    )
            
            # 低相似度，视为新项目
            return None
        
        except Exception as e:
            _safe_print(f"[ThreeStageDeduplicator] 语义匹配失败: {e}")
            return None
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if HAS_NUMPY:
            a = np.array(vec1)
            b = np.array(vec2)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
        else:
            dot = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5
            return dot / (norm1 * norm2 + 1e-8)
    
    def _llm_batch_confirm(self, result: DedupResult):
        """LLM 批量确认边界情况"""
        if not self.llm_client or not result.pending_items:
            return
        
        # 检查预算
        if self.budget_manager:
            estimated_cost = len(result.pending_items) * 0.001  # 粗略估算
            if not self.budget_manager.can_afford(estimated_cost, operation="dedup"):
                _safe_print("[ThreeStageDeduplicator] 预算不足，跳过 LLM 确认")
                # 将所有待确认项标记为新项目
                for item, _ in result.pending_items[:]:
                    result.move_to_new(item)
                return
        
        confirmed = []
        
        for item, candidates in result.pending_items[:]:
            if not candidates:
                result.move_to_new(item)
                continue
            
            candidate = candidates[0]
            
            try:
                prompt = self.DEDUP_PROMPT.format(
                    item_a=f"{item.name}: {item.content[:100]}" if item.content else item.name,
                    item_b=f"{candidate.name}: {candidate.content[:100]}" if candidate.content else candidate.name
                )
                
                response = self.llm_client.complete(
                    prompt=prompt,
                    max_tokens=10,
                    temperature=0
                ).strip().upper()
                
                if response == "YES":
                    result.move_to_match(item, candidate, MatchType.LLM)
                else:
                    result.move_to_new(item)
                
                # 记录预算
                if self.budget_manager:
                    self.budget_manager.record_usage(
                        operation="dedup_confirm",
                        tokens_in=len(prompt) // 4,
                        tokens_out=5,
                        model=self.llm_client.model
                    )
                    
            except Exception as e:
                _safe_print(f"[ThreeStageDeduplicator] LLM 确认失败: {e}")
                result.move_to_new(item)
    
    def add_to_index(self, item: DedupItem):
        """将项目添加到索引（用于增量更新）"""
        # 精确匹配索引
        normalized = self._normalize(item.name)
        if normalized:
            self._exact_map[normalized] = item
        
        # MinHash + LSH 索引
        if self.config.fuzzy_match_enabled:
            shingles = self.minhasher.get_shingles(item.get_text())
            signature = self.minhasher.minhash(shingles)
            self._signature_map[item.id] = signature
            self.lsh_index.add(item.id, signature)
        
        # 项目映射
        self._item_map[item.id] = item
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_indexed': len(self._item_map),
            'exact_index_size': len(self._exact_map),
            'signature_index_size': len(self._signature_map),
            'config': {
                'jaccard_threshold': self.config.jaccard_threshold,
                'semantic_threshold': self.config.semantic_threshold,
                'semantic_low_threshold': self.config.semantic_low_threshold,
                'llm_enabled': self.config.llm_enabled
            }
        }
