"""伏笔分析器 - LLM 辅助伏笔检测（可选功能）

设计理念：
1. 默认 MANUAL 模式 - 纯手动管理，无需任何配置
2. LLM 模式 - 可选的智能分析辅助（需配置 API key）
3. 手动操作始终可用 - LLM 只是辅助，不是替代

与 ForeshadowingTracker 的关系：
- ForeshadowingTracker: 基础功能，负责伏笔的存储和管理
- ForeshadowingAnalyzer: 可选增强，负责 LLM 智能分析

使用方式：
    # 方式1：默认手动模式（无需任何配置）
    analyzer = ForeshadowingAnalyzer(tracker=tracker)
    
    # 方式2：LLM 辅助模式
    analyzer = ForeshadowingAnalyzer(
        tracker=tracker,
        config=ForeshadowingAnalyzerConfig.llm_based(
            api_key="sk-xxx",
            trigger_interval=10
        )
    )
"""

import json
import time
from enum import Enum
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from .foreshadowing import ForeshadowingTracker


class AnalyzerBackend(Enum):
    """分析器后端类型"""
    MANUAL = "manual"  # 手动模式（默认）- 不做任何自动分析
    LLM = "llm"        # LLM 智能分析（需配置 API）


@dataclass
class ForeshadowingAnalyzerConfig:
    """伏笔分析器配置
    
    配置说明：
    - backend: 后端模式，默认 MANUAL
    - trigger_interval: 每N轮触发一次分析（LLM模式），最小1
    - llm_model: LLM 模型名称
    - llm_api_key: LLM API Key
    - llm_base_url: 自定义 API 地址（可选）
    - auto_plant: 自动埋下检测到的伏笔
    - auto_resolve: 自动标记解决（建议 False）
    - max_context_turns: 发送给 LLM 的最大轮次数
    """
    backend: AnalyzerBackend = AnalyzerBackend.MANUAL
    
    # 触发条件（LLM 模式）
    trigger_interval: int = 10      # 每N轮触发一次分析（最小1=每轮都触发）
    
    # LLM 配置
    llm_model: str = "gpt-4o-mini"  # 默认用便宜的模型
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None  # 支持自定义 API 地址
    
    # 行为配置
    auto_plant: bool = True         # 自动埋下检测到的伏笔
    auto_resolve: bool = False      # 自动标记解决（建议 False，让用户确认）
    include_resolved_check: bool = True  # 同时检查已有伏笔是否被解决
    
    # 高级配置
    max_context_turns: int = 20     # 发送给 LLM 的最大轮次数
    language: str = "zh"            # 提示词语言（zh/en）
    
    def __post_init__(self):
        """验证配置"""
        if self.trigger_interval < 1:
            self.trigger_interval = 1
        if self.max_context_turns < 1:
            self.max_context_turns = 1
    
    @classmethod
    def manual(cls) -> 'ForeshadowingAnalyzerConfig':
        """手动模式（默认）- 用户自己管理伏笔"""
        return cls(backend=AnalyzerBackend.MANUAL)
    
    @classmethod
    def llm_based(
        cls, 
        api_key: str, 
        model: str = "gpt-4o-mini",
        trigger_interval: int = 10,
        base_url: Optional[str] = None,
        auto_plant: bool = True,
        auto_resolve: bool = False
    ) -> 'ForeshadowingAnalyzerConfig':
        """LLM 辅助模式 - 智能分析"""
        return cls(
            backend=AnalyzerBackend.LLM,
            llm_api_key=api_key,
            llm_model=model,
            llm_base_url=base_url,
            trigger_interval=trigger_interval,
            auto_plant=auto_plant,
            auto_resolve=auto_resolve
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            'backend': self.backend.value,
            'trigger_interval': self.trigger_interval,
            'llm_model': self.llm_model,
            'llm_base_url': self.llm_base_url,
            'auto_plant': self.auto_plant,
            'auto_resolve': self.auto_resolve,
            'include_resolved_check': self.include_resolved_check,
            'max_context_turns': self.max_context_turns,
            'language': self.language
            # 注意：不序列化 api_key
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], api_key: Optional[str] = None) -> 'ForeshadowingAnalyzerConfig':
        """从字典创建"""
        backend_str = data.get('backend', 'manual')
        backend = AnalyzerBackend(backend_str) if backend_str in ('manual', 'llm') else AnalyzerBackend.MANUAL
        
        return cls(
            backend=backend,
            trigger_interval=data.get('trigger_interval', 10),
            llm_model=data.get('llm_model', 'gpt-4o-mini'),
            llm_api_key=api_key,
            llm_base_url=data.get('llm_base_url'),
            auto_plant=data.get('auto_plant', True),
            auto_resolve=data.get('auto_resolve', False),
            include_resolved_check=data.get('include_resolved_check', True),
            max_context_turns=data.get('max_context_turns', 20),
            language=data.get('language', 'zh')
        )


@dataclass
class AnalysisResult:
    """分析结果"""
    triggered: bool = False                      # 是否触发了分析
    new_foreshadowings: List[Dict[str, Any]] = field(default_factory=list)  # 新检测到的伏笔
    potentially_resolved: List[Dict[str, Any]] = field(default_factory=list)  # 可能已解决的伏笔
    error: Optional[str] = None                  # 错误信息
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'triggered': self.triggered,
            'new_foreshadowings': self.new_foreshadowings,
            'potentially_resolved': self.potentially_resolved,
            'error': self.error
        }


class ForeshadowingAnalyzer:
    """伏笔分析器 - 手动模式 / LLM 智能辅助
    
    核心功能：
    1. on_new_turn(): 每轮对话后调用，LLM模式会在达到触发条件时自动分析
    2. trigger_analysis(): 手动触发分析（任何模式下都可用）
    
    LLM 分析功能：
    - 检测新的伏笔
    - 识别可能已解决的伏笔
    - 可配置自动埋下/解决
    """
    
    # 中文提示词模板
    ANALYSIS_PROMPT_ZH = '''你是一个专业的叙事分析师。请分析以下对话内容，识别其中的伏笔（foreshadowing）。

## 什么是伏笔？
伏笔是故事中埋下的线索，暗示未来会发生的事情，包括：
- 神秘的暗示或预言
- 未解释的事件或现象
- 角色提到的"有一天会..."、"总有一天..."
- 隐藏的秘密或谜团
- 不祥的征兆
- 未完成的承诺或约定

## 当前活跃的伏笔（如果有）：
{active_foreshadowings}

## 最近的对话内容：
{conversation}

## 请输出 JSON 格式：
```json
{{
  "new_foreshadowings": [
    {{
      "content": "伏笔内容描述（简洁概括）",
      "importance": 0.8,
      "evidence": "原文依据（引用对话中的关键句子）",
      "related_entities": ["角色A", "物品B"]
    }}
  ],
  "potentially_resolved": [
    {{
      "foreshadowing_id": "fsh_xxx",
      "evidence": "解决的依据（引用对话）",
      "confidence": 0.9
    }}
  ]
}}
```

重要提示：
1. 只输出 JSON，不要其他内容
2. 如果没有检测到伏笔，返回空数组
3. 只识别真正的叙事伏笔，不要把普通对话当伏笔
4. importance 范围 0-1，越重要越高
5. confidence 范围 0-1，越确定越高'''

    # 英文提示词模板
    ANALYSIS_PROMPT_EN = '''You are a professional narrative analyst. Please analyze the following conversation and identify foreshadowing elements.

## What is foreshadowing?
Foreshadowing is a narrative device that hints at future events:
- Mysterious hints or prophecies
- Unexplained events or phenomena
- Characters saying "someday..." or "one day..."
- Hidden secrets or mysteries
- Ominous signs
- Unfulfilled promises or agreements

## Currently active foreshadowings (if any):
{active_foreshadowings}

## Recent conversation:
{conversation}

## Output in JSON format:
```json
{{
  "new_foreshadowings": [
    {{
      "content": "Brief description of the foreshadowing",
      "importance": 0.8,
      "evidence": "Quote from the conversation",
      "related_entities": ["Character A", "Item B"]
    }}
  ],
  "potentially_resolved": [
    {{
      "foreshadowing_id": "fsh_xxx",
      "evidence": "Quote showing resolution",
      "confidence": 0.9
    }}
  ]
}}
```

Important:
1. Output JSON only, no other text
2. Return empty arrays if no foreshadowing detected
3. Only identify genuine narrative foreshadowing
4. importance range: 0-1, higher = more important
5. confidence range: 0-1, higher = more certain'''

    def __init__(
        self, 
        tracker: 'ForeshadowingTracker',
        config: Optional[ForeshadowingAnalyzerConfig] = None
    ):
        """初始化分析器
        
        Args:
            tracker: ForeshadowingTracker 实例（必需）
            config: 分析器配置（可选，默认为手动模式）
        """
        if tracker is None:
            raise ValueError("tracker 参数不能为 None")
        
        self.tracker = tracker
        self.config = config or ForeshadowingAnalyzerConfig.manual()
        
        # 对话缓冲区（按用户分隔）
        self._buffers: Dict[str, List[Dict[str, Any]]] = {}
        # 轮次计数器（按用户分隔）
        self._turn_counters: Dict[str, int] = {}
        
        # LLM 客户端（懒加载）
        self._llm_client = None
        
        # 初始化 LLM 客户端（如果是 LLM 模式）
        if self.config.backend == AnalyzerBackend.LLM:
            self._init_llm_client()
    
    def _init_llm_client(self):
        """初始化 LLM 客户端"""
        if not self.config.llm_api_key:
            print("[Recall] 警告：LLM 模式需要配置 API key")
            return
        
        try:
            from ..utils.llm_client import LLMClient
            self._llm_client = LLMClient(
                model=self.config.llm_model,
                api_key=self.config.llm_api_key,
                api_base=self.config.llm_base_url
            )
        except ImportError as e:
            print(f"[Recall] 警告：LLM 客户端初始化失败: {e}")
            self._llm_client = None
    
    @property
    def is_llm_enabled(self) -> bool:
        """检查 LLM 功能是否可用"""
        return (
            self.config.backend == AnalyzerBackend.LLM and 
            self._llm_client is not None
        )
    
    def on_new_turn(
        self, 
        content: str,
        role: str = "user",
        user_id: str = "default"
    ) -> AnalysisResult:
        """处理新的一轮对话
        
        在每轮对话后调用此方法。LLM 模式下会累积对话并在达到触发条件时分析。
        
        Args:
            content: 对话内容
            role: 角色（user/assistant）
            user_id: 用户ID
            
        Returns:
            AnalysisResult: 分析结果（如果触发了分析）
        """
        # 添加到缓冲区
        if user_id not in self._buffers:
            self._buffers[user_id] = []
        
        self._buffers[user_id].append({
            'role': role,
            'content': content,
            'timestamp': time.time()
        })
        
        # 限制缓冲区大小
        max_size = self.config.max_context_turns * 2  # 考虑 user + assistant
        if len(self._buffers[user_id]) > max_size:
            self._buffers[user_id] = self._buffers[user_id][-max_size:]
        
        # 增加轮次计数
        if user_id not in self._turn_counters:
            self._turn_counters[user_id] = 0
        self._turn_counters[user_id] += 1
        
        # 检查是否应该触发分析（仅 LLM 模式）
        if self.config.backend == AnalyzerBackend.LLM:
            if self._turn_counters[user_id] >= self.config.trigger_interval:
                self._turn_counters[user_id] = 0
                return self._trigger_llm_analysis(user_id)
        
        # 手动模式不做任何分析
        return AnalysisResult(triggered=False)
    
    def trigger_analysis(self, user_id: str = "default") -> AnalysisResult:
        """手动触发分析
        
        可以在任何模式下调用。如果是 LLM 模式且有配置，会使用 LLM 分析。
        否则返回空结果。
        
        Args:
            user_id: 用户ID
            
        Returns:
            AnalysisResult: 分析结果
        """
        if self.is_llm_enabled:
            return self._trigger_llm_analysis(user_id)
        
        return AnalysisResult(
            triggered=False,
            error="LLM 分析未启用（需配置 API key）"
        )
    
    def _trigger_llm_analysis(self, user_id: str) -> AnalysisResult:
        """触发 LLM 分析"""
        if not self.is_llm_enabled:
            return AnalysisResult(
                triggered=False,
                error="LLM 客户端未初始化"
            )
        
        buffer = self._buffers.get(user_id, [])
        if not buffer:
            return AnalysisResult(
                triggered=True,
                error="对话缓冲区为空"
            )
        
        try:
            # 构建对话文本
            conversation = self._format_conversation(
                buffer[-self.config.max_context_turns * 2:]
            )
            
            # 获取当前活跃的伏笔
            active = self.tracker.get_active(user_id)
            active_text = self._format_active_foreshadowings(active)
            
            # 选择提示词
            prompt_template = (
                self.ANALYSIS_PROMPT_ZH 
                if self.config.language == 'zh' 
                else self.ANALYSIS_PROMPT_EN
            )
            
            # 构建提示词
            prompt = prompt_template.format(
                active_foreshadowings=active_text or "（暂无）" if self.config.language == 'zh' else "(None)",
                conversation=conversation
            )
            
            # 调用 LLM
            response = self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # 低温度，更确定性
                max_tokens=1000
            )
            
            # 解析结果
            result = self._parse_llm_response(response.content)
            result.triggered = True
            
            # 处理结果：自动埋下伏笔
            if self.config.auto_plant and result.new_foreshadowings:
                for fsh_data in result.new_foreshadowings:
                    try:
                        self.tracker.plant(
                            content=fsh_data.get('content', ''),
                            user_id=user_id,
                            importance=fsh_data.get('importance', 0.5),
                            related_entities=fsh_data.get('related_entities', [])
                        )
                    except Exception as e:
                        print(f"[Recall] 自动埋下伏笔失败: {e}")
            
            # 处理结果：自动解决伏笔
            if self.config.auto_resolve and result.potentially_resolved:
                for resolved_data in result.potentially_resolved:
                    fsh_id = resolved_data.get('foreshadowing_id')
                    confidence = resolved_data.get('confidence', 0)
                    evidence = resolved_data.get('evidence', '')
                    
                    # 只有置信度高于0.8才自动解决
                    if fsh_id and confidence >= 0.8:
                        try:
                            self.tracker.resolve(
                                foreshadowing_id=fsh_id,
                                resolution=f"[自动检测] {evidence}",
                                user_id=user_id
                            )
                        except Exception as e:
                            print(f"[Recall] 自动解决伏笔失败: {e}")
            
            # 清空已分析的缓冲区
            self._buffers[user_id] = []
            
            return result
            
        except Exception as e:
            return AnalysisResult(
                triggered=True,
                error=f"LLM 分析失败: {str(e)}"
            )
    
    def _format_conversation(self, turns: List[Dict[str, Any]]) -> str:
        """格式化对话内容"""
        lines = []
        for t in turns:
            role_name = "用户" if t['role'] == 'user' else "AI"
            if self.config.language != 'zh':
                role_name = "User" if t['role'] == 'user' else "AI"
            lines.append(f"[{role_name}]: {t['content']}")
        return "\n\n".join(lines)
    
    def _format_active_foreshadowings(self, foreshadowings) -> str:
        """格式化活跃伏笔列表"""
        if not foreshadowings:
            return ""
        
        lines = []
        for f in foreshadowings:
            # 兼容 Foreshadowing 对象和字典
            if hasattr(f, 'id'):
                fsh_id = f.id
                content = f.content
                importance = f.importance
            else:
                fsh_id = f.get('id', '')
                content = f.get('content', '')
                importance = f.get('importance', 0.5)
            
            lines.append(f"- [{fsh_id}] {content} (重要性: {importance})")
        return "\n".join(lines)
    
    def _parse_llm_response(self, response: str) -> AnalysisResult:
        """解析 LLM 返回的 JSON"""
        result = AnalysisResult()
        
        try:
            # 尝试提取 JSON（处理可能的 markdown 代码块）
            json_str = response
            
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            
            data = json.loads(json_str.strip())
            
            result.new_foreshadowings = data.get('new_foreshadowings', [])
            result.potentially_resolved = data.get('potentially_resolved', [])
            
        except json.JSONDecodeError as e:
            result.error = f"JSON 解析失败: {e}"
        except Exception as e:
            result.error = f"解析失败: {e}"
        
        return result
    
    def get_buffer_size(self, user_id: str = "default") -> int:
        """获取当前缓冲区大小"""
        return len(self._buffers.get(user_id, []))
    
    def get_turns_until_analysis(self, user_id: str = "default") -> int:
        """获取距离下次分析还需要多少轮"""
        if self.config.backend != AnalyzerBackend.LLM:
            return -1  # 手动模式不会自动分析
        
        current = self._turn_counters.get(user_id, 0)
        return self.config.trigger_interval - current
    
    def clear_buffer(self, user_id: str = "default"):
        """清空对话缓冲区"""
        if user_id in self._buffers:
            self._buffers[user_id] = []
        if user_id in self._turn_counters:
            self._turn_counters[user_id] = 0
    
    def update_config(
        self,
        trigger_interval: Optional[int] = None,
        auto_plant: Optional[bool] = None,
        auto_resolve: Optional[bool] = None,
        max_context_turns: Optional[int] = None
    ):
        """更新配置（不重新初始化 LLM 客户端）"""
        if trigger_interval is not None:
            self.config.trigger_interval = max(1, trigger_interval)
        if auto_plant is not None:
            self.config.auto_plant = auto_plant
        if auto_resolve is not None:
            self.config.auto_resolve = auto_resolve
        if max_context_turns is not None:
            self.config.max_context_turns = max(1, max_context_turns)
