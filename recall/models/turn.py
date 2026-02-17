"""对话轮次数据模型"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class Turn(BaseModel):
    """对话轮次（v5.0 通用化）
    
    兼容 RP 模式（user/assistant）和通用模式（content）。
    """
    turn: int
    timestamp: datetime
    
    # RP 模式字段（保留，设为可选以支持通用模式）
    user: str = ""
    assistant: str = ""
    
    # v5.0 通用模式新增字段
    content: str = ""                         # 通用内容（非对话场景：网页、文档等）
    source: str = ""                          # 来源标识（如 url、文件名）
    content_type: str = "chat"                # 内容类型: chat, document, webpage, note
    title: str = ""                           # 标题（网页/文档）
    url: str = ""                             # 来源URL
    tags: List[str] = []                      # 标签
    category: str = ""                        # 分类
    
    metadata: Dict[str, Any] = {}
    entities_mentioned: List[str] = []
    events_detected: List[str] = []
    ngrams_3: List[str] = []
    keywords: List[str] = []
    
    @property
    def effective_content(self) -> str:
        """返回有效内容：优先 content，否则拼接 user+assistant"""
        if self.content:
            return self.content
        parts = []
        if self.user:
            parts.append(self.user)
        if self.assistant:
            parts.append(self.assistant)
        return "\n".join(parts)
