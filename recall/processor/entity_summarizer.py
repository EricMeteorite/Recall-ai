"""实体摘要生成器 - Recall 4.1

为实体自动生成摘要，总结实体的所有已知信息。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from ..utils.llm_client import LLMClient


@dataclass
class EntitySummary:
    """实体摘要"""
    entity_name: str
    summary: str
    key_facts: List[str] = field(default_factory=list)
    relation_count: int = 0
    mention_count: int = 0
    last_updated: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'entity_name': self.entity_name,
            'summary': self.summary,
            'key_facts': self.key_facts,
            'relation_count': self.relation_count,
            'mention_count': self.mention_count,
            'last_updated': self.last_updated
        }


SUMMARIZE_PROMPT = '''请为以下实体生成一个简洁的摘要。

## 实体名称：{entity_name}

## 相关事实：
{facts}

## 相关关系：
{relations}

## 输出要求：
1. 生成一个 2-3 句话的摘要，总结实体的核心信息
2. 列出 3-5 个关键事实要点

请用以下格式输出：
摘要：[摘要内容]
关键事实：
- [事实1]
- [事实2]
- [事实3]
'''


class EntitySummarizer:
    """实体摘要生成器
    
    使用方式：
        summarizer = EntitySummarizer(llm_client=llm_client)
        summary = summarizer.generate(
            entity_name="张三",
            facts=["张三是程序员", "张三喜欢喝咖啡"],
            relations=[("张三", "WORKS_AT", "腾讯")]
        )
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
    
    def generate(
        self,
        entity_name: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]],
        force_llm: bool = False
    ) -> EntitySummary:
        """生成实体摘要
        
        Args:
            entity_name: 实体名称
            facts: 相关事实列表
            relations: 相关关系列表 [(source, relation_type, target), ...]
            force_llm: 是否强制使用 LLM
        
        Returns:
            EntitySummary: 生成的摘要
        """
        if self.llm_client and (force_llm or len(facts) > 3):
            return self._generate_with_llm(entity_name, facts, relations)
        else:
            return self._generate_simple(entity_name, facts, relations)
    
    def _generate_simple(
        self,
        entity_name: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]]
    ) -> EntitySummary:
        """简单规则生成"""
        key_facts = facts[:5]
        summary = f"{entity_name}。" + " ".join(key_facts[:2]) if key_facts else f"{entity_name}。"
        
        return EntitySummary(
            entity_name=entity_name,
            summary=summary,
            key_facts=key_facts,
            relation_count=len(relations),
            mention_count=len(facts),
            last_updated=datetime.now().isoformat()
        )
    
    def _generate_with_llm(
        self,
        entity_name: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]]
    ) -> EntitySummary:
        """LLM 生成"""
        facts_str = "\n".join([f"- {f}" for f in facts[:10]])
        relations_str = "\n".join([f"- {s} {r} {t}" for s, r, t in relations[:10]])
        
        prompt = SUMMARIZE_PROMPT.format(
            entity_name=entity_name,
            facts=facts_str or "（无）",
            relations=relations_str or "（无）"
        )
        
        try:
            # 使用 complete() 方法（接受字符串 prompt）
            # 从环境变量读取配置的最大 tokens，或根据内容长度动态计算
            import os
            config_max_tokens = int(os.environ.get('ENTITY_SUMMARY_MAX_TOKENS', '2000'))
            content_length = len(facts_str or '') + len(relations_str or '')
            # 动态计算，但不超过配置的上限
            max_tokens = min(config_max_tokens, max(1000, content_length // 2))
            response = self.llm_client.complete(prompt, max_tokens=max_tokens)
            return self._parse_response(entity_name, response, facts, relations)
        except Exception as e:
            print(f"[EntitySummarizer] LLM 失败: {e}")
            return self._generate_simple(entity_name, facts, relations)
    
    def _parse_response(
        self,
        entity_name: str,
        response: str,
        facts: List[str],
        relations: List[Tuple[str, str, str]]
    ) -> EntitySummary:
        """解析 LLM 响应"""
        summary = ""
        key_facts = []
        
        lines = response.strip().split('\n')
        parsing_facts = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('摘要：') or line.startswith('摘要:'):
                summary = line.split('：', 1)[-1].split(':', 1)[-1].strip()
            elif '关键事实' in line:
                parsing_facts = True
            elif parsing_facts and line.startswith('-'):
                key_facts.append(line[1:].strip())
        
        if not summary:
            summary = response[:200]
        
        return EntitySummary(
            entity_name=entity_name,
            summary=summary,
            key_facts=key_facts or facts[:5],
            relation_count=len(relations),
            mention_count=len(facts),
            last_updated=datetime.now().isoformat()
        )
