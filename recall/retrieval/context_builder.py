"""上下文构建器 - 构建优化的LLM上下文"""

import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class BuiltContext:
    """构建的上下文"""
    system_prompt: str
    memory_section: str
    recent_turns: str
    total_tokens: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_prompt(self) -> str:
        """转换为完整提示"""
        parts = []
        if self.system_prompt:
            parts.append(self.system_prompt)
        if self.memory_section:
            parts.append(f"\n<memories>\n{self.memory_section}\n</memories>")
        if self.recent_turns:
            parts.append(f"\n<recent_conversation>\n{self.recent_turns}\n</recent_conversation>")
        return "\n".join(parts)


class ContextBuilder:
    """上下文构建器"""
    
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        
        # Token估算（简化：1字符约0.5token中文，1token英文）
        self.char_per_token_zh = 2
        self.char_per_token_en = 4
    
    def build(
        self,
        memories: List[Dict[str, Any]],
        recent_turns: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        query: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> BuiltContext:
        """构建上下文"""
        config = config or {}
        
        # 计算各部分的token预算
        system_tokens = self._estimate_tokens(system_prompt) if system_prompt else 0
        query_tokens = self._estimate_tokens(query) if query else 0
        
        remaining_tokens = self.max_tokens - system_tokens - query_tokens
        
        # 分配给记忆和对话
        memory_budget = int(remaining_tokens * config.get('memory_ratio', 0.5))
        turns_budget = remaining_tokens - memory_budget
        
        # 构建记忆部分
        memory_section = self._build_memory_section(memories, memory_budget)
        
        # 构建对话部分
        recent_section = self._build_turns_section(recent_turns, turns_budget)
        
        # 计算实际token
        total_tokens = (
            system_tokens +
            self._estimate_tokens(memory_section) +
            self._estimate_tokens(recent_section)
        )
        
        return BuiltContext(
            system_prompt=system_prompt or "",
            memory_section=memory_section,
            recent_turns=recent_section,
            total_tokens=total_tokens,
            metadata={
                'memory_count': len(memories),
                'turns_count': len(recent_turns),
                'build_time': time.time()
            }
        )
    
    def _build_memory_section(
        self,
        memories: List[Dict[str, Any]],
        budget: int
    ) -> str:
        """构建记忆部分"""
        if not memories:
            return ""
        
        lines = []
        current_tokens = 0
        
        # 按相关性排序（假设已排序）
        for memory in memories:
            content = memory.get('content', memory.get('memory', ''))
            
            # 添加元信息
            entities = memory.get('entities', [])
            if entities:
                content = f"[相关: {', '.join(entities[:3])}] {content}"
            
            tokens = self._estimate_tokens(content)
            
            if current_tokens + tokens > budget:
                # 尝试截断
                remaining_chars = (budget - current_tokens) * self.char_per_token_zh
                if remaining_chars > 50:
                    lines.append(content[:int(remaining_chars)] + "...")
                break
            
            lines.append(f"• {content}")
            current_tokens += tokens
        
        return "\n".join(lines)
    
    def _build_turns_section(
        self,
        turns: List[Dict[str, Any]],
        budget: int
    ) -> str:
        """构建对话轮次部分"""
        if not turns:
            return ""
        
        lines = []
        current_tokens = 0
        
        # 从最近的开始（倒序处理后再反转）
        selected = []
        for turn in reversed(turns):
            role = turn.get('role', 'user')
            content = turn.get('content', '')
            
            line = f"{role}: {content}"
            tokens = self._estimate_tokens(line)
            
            if current_tokens + tokens > budget:
                break
            
            selected.append(line)
            current_tokens += tokens
        
        return "\n".join(reversed(selected))
    
    def _estimate_tokens(self, text: Optional[str]) -> int:
        """估算token数量"""
        if not text:
            return 0
        
        # 简单估算：统计中英文字符
        zh_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        en_count = len(text) - zh_count
        
        return zh_count // self.char_per_token_zh + en_count // self.char_per_token_en
    
    def optimize_for_roleplay(
        self,
        character_info: Dict[str, Any],
        memories: List[Dict[str, Any]],
        recent_turns: List[Dict[str, Any]]
    ) -> BuiltContext:
        """针对角色扮演优化的上下文构建"""
        # 角色设定
        character_prompt = self._build_character_prompt(character_info)
        
        # 强调角色相关记忆
        character_name = character_info.get('name', '')
        prioritized_memories = self._prioritize_character_memories(
            memories, character_name
        )
        
        return self.build(
            memories=prioritized_memories,
            recent_turns=recent_turns,
            system_prompt=character_prompt,
            config={'memory_ratio': 0.6}  # 角色扮演给记忆更多空间
        )
    
    def _build_character_prompt(self, character_info: Dict[str, Any]) -> str:
        """构建角色提示"""
        name = character_info.get('name', '角色')
        description = character_info.get('description', '')
        personality = character_info.get('personality', '')
        
        parts = [f"你是{name}。"]
        if description:
            parts.append(f"背景：{description}")
        if personality:
            parts.append(f"性格：{personality}")
        
        return " ".join(parts)
    
    def _prioritize_character_memories(
        self,
        memories: List[Dict[str, Any]],
        character_name: str
    ) -> List[Dict[str, Any]]:
        """优先选择角色相关记忆"""
        if not character_name:
            return memories
        
        # 分类
        character_related = []
        others = []
        
        for memory in memories:
            content = memory.get('content', memory.get('memory', ''))
            entities = memory.get('entities', [])
            
            if character_name in content or character_name in entities:
                character_related.append(memory)
            else:
                others.append(memory)
        
        # 角色相关的优先
        return character_related + others
