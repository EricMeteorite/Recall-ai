"""记忆摘要器 - 记忆压缩与摘要生成"""

import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class MemoryPriority(Enum):
    """记忆优先级"""
    CRITICAL = "critical"     # 关键（永不遗忘）
    HIGH = "high"             # 高优先级
    NORMAL = "normal"         # 普通
    LOW = "low"               # 低优先级
    EPHEMERAL = "ephemeral"   # 临时（可快速遗忘）


@dataclass
class MemoryItem:
    """记忆项（mem0兼容格式）"""
    id: str
    content: str
    user_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # Recall扩展字段
    priority: MemoryPriority = MemoryPriority.NORMAL
    access_count: int = 0
    last_accessed: Optional[float] = None
    embedding: Optional[List[float]] = None
    entities: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（mem0兼容）"""
        return {
            'id': self.id,
            'memory': self.content,  # mem0使用'memory'字段
            'user_id': self.user_id,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            # 扩展字段
            'priority': self.priority.value,
            'access_count': self.access_count,
            'entities': self.entities,
            'keywords': self.keywords
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryItem':
        """从字典创建"""
        # 兼容mem0格式
        content = data.get('content', data.get('memory', ''))
        
        return cls(
            id=data['id'],
            content=content,
            user_id=data.get('user_id', 'default'),
            metadata=data.get('metadata', {}),
            created_at=data.get('created_at', time.time()),
            updated_at=data.get('updated_at', time.time()),
            priority=MemoryPriority(data.get('priority', 'normal')),
            access_count=data.get('access_count', 0),
            entities=data.get('entities', []),
            keywords=data.get('keywords', [])
        )


class MemorySummarizer:
    """记忆摘要器"""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        
        # 摘要模板
        self.summary_prompt = """请对以下记忆内容进行摘要，保留关键信息：

记忆内容：
{memories}

要求：
1. 保留所有人名、地名、数字等关键信息
2. 合并相似或重复的内容
3. 按时间或主题组织
4. 输出简洁但完整的摘要

摘要："""
    
    def summarize_memories(
        self,
        memories: List[MemoryItem],
        max_length: int = 500
    ) -> str:
        """对多条记忆进行摘要"""
        if not memories:
            return ""
        
        # 如果没有LLM客户端，使用简单拼接
        if not self.llm_client:
            return self._simple_summarize(memories, max_length)
        
        # 使用LLM摘要
        return self._llm_summarize(memories, max_length)
    
    def _simple_summarize(
        self,
        memories: List[MemoryItem],
        max_length: int
    ) -> str:
        """简单摘要（无LLM时使用）"""
        # 按优先级排序
        priority_order = {
            MemoryPriority.CRITICAL: 0,
            MemoryPriority.HIGH: 1,
            MemoryPriority.NORMAL: 2,
            MemoryPriority.LOW: 3,
            MemoryPriority.EPHEMERAL: 4
        }
        sorted_memories = sorted(
            memories,
            key=lambda m: (priority_order[m.priority], -m.access_count)
        )
        
        # 拼接直到达到长度限制
        result = []
        current_length = 0
        
        for memory in sorted_memories:
            content = memory.content
            if current_length + len(content) + 2 <= max_length:
                result.append(content)
                current_length += len(content) + 2
            elif current_length == 0:
                # 第一条太长，截断
                result.append(content[:max_length - 3] + "...")
                break
        
        return "\n".join(result)
    
    def _llm_summarize(
        self,
        memories: List[MemoryItem],
        max_length: int
    ) -> str:
        """使用LLM进行摘要"""
        # 准备输入
        memory_texts = [f"- {m.content}" for m in memories]
        prompt = self.summary_prompt.format(memories="\n".join(memory_texts))
        
        try:
            # 调用LLM
            response = self.llm_client.complete(prompt, max_tokens=max_length)
            return response.strip()
        except Exception as e:
            # LLM失败，回退到简单摘要
            print(f"[Recall] LLM摘要失败，使用简单摘要: {e}")
            return self._simple_summarize(memories, max_length)
    
    def merge_similar(
        self,
        memories: List[MemoryItem],
        similarity_threshold: float = 0.8
    ) -> List[MemoryItem]:
        """合并相似记忆"""
        if len(memories) <= 1:
            return memories
        
        # 简单的基于关键词重叠的相似度
        merged = []
        used = set()
        
        for i, m1 in enumerate(memories):
            if i in used:
                continue
            
            # 查找相似的记忆
            similar_group = [m1]
            for j, m2 in enumerate(memories[i+1:], i+1):
                if j in used:
                    continue
                
                similarity = self._compute_similarity(m1, m2)
                if similarity >= similarity_threshold:
                    similar_group.append(m2)
                    used.add(j)
            
            # 合并组
            if len(similar_group) > 1:
                merged_content = self._merge_contents(similar_group)
                merged_item = MemoryItem(
                    id=m1.id,
                    content=merged_content,
                    user_id=m1.user_id,
                    metadata=m1.metadata,
                    priority=max(m.priority for m in similar_group),
                    entities=list(set(sum([m.entities for m in similar_group], []))),
                    keywords=list(set(sum([m.keywords for m in similar_group], [])))
                )
                merged.append(merged_item)
            else:
                merged.append(m1)
            
            used.add(i)
        
        return merged
    
    def _compute_similarity(self, m1: MemoryItem, m2: MemoryItem) -> float:
        """计算两条记忆的相似度"""
        # 基于关键词重叠
        k1 = set(m1.keywords) if m1.keywords else set(m1.content.split())
        k2 = set(m2.keywords) if m2.keywords else set(m2.content.split())
        
        if not k1 or not k2:
            return 0.0
        
        intersection = len(k1 & k2)
        union = len(k1 | k2)
        
        return intersection / union if union > 0 else 0.0
    
    def _merge_contents(self, memories: List[MemoryItem]) -> str:
        """合并多条记忆的内容"""
        # 简单拼接去重
        seen_sentences = set()
        merged_parts = []
        
        for m in memories:
            sentences = m.content.split('。')
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence and sentence not in seen_sentences:
                    seen_sentences.add(sentence)
                    merged_parts.append(sentence)
        
        return '。'.join(merged_parts) + ('。' if merged_parts else '')
    
    def compress_for_context(
        self,
        memories: List[MemoryItem],
        max_tokens: int = 2000
    ) -> str:
        """压缩记忆以适应上下文窗口"""
        # 估算每个字符约0.5个token（中文）
        max_chars = max_tokens * 2
        
        # 先合并相似
        merged = self.merge_similar(memories)
        
        # 再摘要
        return self.summarize_memories(merged, max_chars)
