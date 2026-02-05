"""统一分析器 - Recall 性能优化 (v4.2)

设计理念：
1. 一次 LLM 调用完成多个分析任务（矛盾检测、关系提取、实体摘要）
2. 提供完整上下文，提升分析质量
3. 向后兼容：可选启用，不影响现有功能
4. 智能回退：LLM 失败时自动回退到独立模块
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from ..utils.llm_client import LLMClient


class AnalysisTask(str, Enum):
    """分析任务类型"""
    CONTRADICTION = "contradiction"     # 矛盾检测
    RELATION = "relation"               # 关系提取
    ENTITY_SUMMARY = "entity_summary"   # 实体摘要


@dataclass
class UnifiedAnalysisInput:
    """统一分析输入"""
    content: str                                # 当前内容
    entities: List[str] = field(default_factory=list)  # 已识别实体
    existing_memories: List[str] = field(default_factory=list)  # 已有记忆（用于矛盾检测）
    tasks: List[AnalysisTask] = field(default_factory=list)  # 要执行的任务
    
    # 可选上下文
    user_id: str = "default"
    character_id: str = "default"


@dataclass
class UnifiedAnalysisResult:
    """统一分析结果"""
    success: bool = False
    
    # 矛盾检测结果
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    
    # 关系提取结果
    relations: List[Dict[str, Any]] = field(default_factory=list)
    
    # 实体摘要结果
    entity_summaries: Dict[str, str] = field(default_factory=dict)
    
    # 错误信息
    error: Optional[str] = None
    
    # 执行的任务
    tasks_executed: List[str] = field(default_factory=list)
    
    # 原始 LLM 响应（调试用）
    raw_response: Optional[str] = None


# 统一分析 Prompt 模板
UNIFIED_ANALYSIS_PROMPT = '''你是一个专业的知识图谱和记忆分析专家。请对以下对话内容进行综合分析。

## 当前对话内容
{content}

## 已识别的实体列表
{entities}

## 已有的记忆内容（用于矛盾检测）
{existing_memories}

## 分析任务
请完成以下分析任务：{tasks_description}

## 输出格式
请严格按照以下 JSON 格式输出分析结果：

```json
{{
  "contradictions": [
    {{
      "type": "直接矛盾|时态矛盾|逻辑矛盾",
      "old_fact": "已有记忆中的内容",
      "new_fact": "新内容中的矛盾点",
      "confidence": 0.8,
      "explanation": "矛盾说明"
    }}
  ],
  "relations": [
    {{
      "source": "实体A",
      "target": "实体B",
      "relation_type": "RELATION_TYPE",
      "fact": "自然语言描述",
      "confidence": 0.8
    }}
  ],
  "entity_summaries": {{
    "实体名": "该实体的简洁摘要（2-3句话）"
  }}
}}
```

## 重要说明
1. 只分析要求的任务，未要求的任务输出空数组/对象
2. 关系类型使用 SCREAMING_SNAKE_CASE 格式（如 WORKS_AT, FRIENDS_WITH）
3. 只提取实体列表中存在的实体之间的关系
4. 矛盾检测只在发现明确矛盾时才添加记录
5. 请直接输出 JSON，不要包含其他文字说明'''


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


class UnifiedAnalyzer:
    """统一分析器
    
    通过一次 LLM 调用完成多个分析任务：
    - 矛盾检测
    - 关系提取
    - 实体摘要
    
    使用方式：
        analyzer = UnifiedAnalyzer(llm_client=llm_client)
        
        result = analyzer.analyze(UnifiedAnalysisInput(
            content="用户说的话...",
            entities=["张三", "李四"],
            existing_memories=["之前的记忆1", "之前的记忆2"],
            tasks=[AnalysisTask.CONTRADICTION, AnalysisTask.RELATION]
        ))
        
        if result.success:
            print(f"矛盾: {result.contradictions}")
            print(f"关系: {result.relations}")
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        enabled: bool = True
    ):
        """初始化统一分析器
        
        Args:
            llm_client: LLM 客户端
            enabled: 是否启用（False 时所有调用直接返回空结果）
        """
        self.llm_client = llm_client
        self.enabled = enabled
        
        # 从环境变量读取配置
        self.max_tokens = int(os.environ.get('UNIFIED_ANALYSIS_MAX_TOKENS', '4000'))
    
    def analyze(self, input: UnifiedAnalysisInput) -> UnifiedAnalysisResult:
        """执行统一分析
        
        Args:
            input: 分析输入
            
        Returns:
            UnifiedAnalysisResult: 分析结果
        """
        if not self.enabled or not self.llm_client:
            return UnifiedAnalysisResult(
                success=False,
                error="统一分析器未启用或 LLM 客户端未配置"
            )
        
        if not input.tasks:
            return UnifiedAnalysisResult(
                success=False,
                error="未指定分析任务"
            )
        
        try:
            # 构建 Prompt
            prompt = self._build_prompt(input)
            
            # 调用 LLM
            response = self.llm_client.complete(prompt, max_tokens=self.max_tokens)
            
            # 解析结果
            result = self._parse_response(response, input.tasks)
            result.raw_response = response
            
            return result
            
        except Exception as e:
            _safe_print(f"[Recall][UnifiedAnalyzer] 分析失败: {e}")
            return UnifiedAnalysisResult(
                success=False,
                error=f"统一分析失败: {str(e)}"
            )
    
    def _build_prompt(self, input: UnifiedAnalysisInput) -> str:
        """构建分析 Prompt"""
        # 任务描述
        task_descriptions = []
        if AnalysisTask.CONTRADICTION in input.tasks:
            task_descriptions.append("1. 矛盾检测：检查新内容是否与已有记忆存在矛盾")
        if AnalysisTask.RELATION in input.tasks:
            task_descriptions.append("2. 关系提取：提取实体之间的关系")
        if AnalysisTask.ENTITY_SUMMARY in input.tasks:
            task_descriptions.append("3. 实体摘要：为主要实体生成简洁摘要")
        
        tasks_description = "\n".join(task_descriptions) if task_descriptions else "无"
        
        # 格式化实体列表
        entities_str = ", ".join(input.entities) if input.entities else "（无）"
        
        # 格式化已有记忆
        if input.existing_memories:
            memories_str = "\n".join([f"- {m[:200]}..." if len(m) > 200 else f"- {m}" 
                                      for m in input.existing_memories[:10]])
        else:
            memories_str = "（无）"
        
        return UNIFIED_ANALYSIS_PROMPT.format(
            content=input.content,
            entities=entities_str,
            existing_memories=memories_str,
            tasks_description=tasks_description
        )
    
    def _parse_response(
        self,
        response: str,
        tasks: List[AnalysisTask]
    ) -> UnifiedAnalysisResult:
        """解析 LLM 响应"""
        result = UnifiedAnalysisResult(success=True)
        
        try:
            # 提取 JSON 部分
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            
            # 解析矛盾检测结果
            if AnalysisTask.CONTRADICTION in tasks:
                result.contradictions = data.get('contradictions', [])
                result.tasks_executed.append('contradiction')
            
            # 解析关系提取结果
            if AnalysisTask.RELATION in tasks:
                result.relations = data.get('relations', [])
                result.tasks_executed.append('relation')
            
            # 解析实体摘要结果
            if AnalysisTask.ENTITY_SUMMARY in tasks:
                result.entity_summaries = data.get('entity_summaries', {})
                result.tasks_executed.append('entity_summary')
            
        except json.JSONDecodeError as e:
            result.success = False
            result.error = f"JSON 解析失败: {str(e)}"
        except Exception as e:
            result.success = False
            result.error = f"响应解析失败: {str(e)}"
        
        return result
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        # 尝试直接解析
        text = text.strip()
        if text.startswith('{'):
            return text
        
        # 尝试提取 ```json ... ``` 块
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1).strip()
        
        # 尝试找到第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        
        raise ValueError("无法从响应中提取 JSON")
