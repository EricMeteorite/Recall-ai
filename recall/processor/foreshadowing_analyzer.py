"""伏笔分析器 — v7.0 兼容性实现

提供 ForeshadowingAnalyzer 功能：
  - 手动模式（MANUAL）：不自动分析，仅提供缓冲和手动触发接口
  - LLM 模式：基于 LLM 的自动伏笔检测与分析
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
import os, json, re


class AnalyzerBackend(str, Enum):
    """分析器后端类型"""
    MANUAL = "manual"
    LLM = "llm"


@dataclass
class AnalysisResult:
    """分析结果"""
    triggered: bool = False
    new_foreshadowings: List[Dict[str, Any]] = field(default_factory=list)
    potentially_resolved: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'triggered': self.triggered,
            'new_foreshadowings': self.new_foreshadowings,
            'potentially_resolved': self.potentially_resolved,
            'error': self.error,
        }


@dataclass
class ForeshadowingAnalyzerConfig:
    """分析器配置"""
    backend: AnalyzerBackend = AnalyzerBackend.MANUAL
    trigger_interval: int = 10
    auto_plant: bool = True
    auto_resolve: bool = False
    llm_model: str = "gpt-4o-mini"
    llm_api_key: Optional[str] = None
    llm_api_base: Optional[str] = None

    def __post_init__(self):
        if self.trigger_interval < 1:
            self.trigger_interval = 1
        if isinstance(self.backend, str):
            try:
                self.backend = AnalyzerBackend(self.backend)
            except ValueError:
                self.backend = AnalyzerBackend.MANUAL

    @classmethod
    def manual(cls) -> 'ForeshadowingAnalyzerConfig':
        return cls(backend=AnalyzerBackend.MANUAL)

    @classmethod
    def llm_based(cls, api_key: str = None, model: str = "gpt-4o-mini",
                  base_url: str = None,
                  trigger_interval: int = 10, auto_plant: bool = True,
                  auto_resolve: bool = False) -> 'ForeshadowingAnalyzerConfig':
        return cls(
            backend=AnalyzerBackend.LLM,
            trigger_interval=trigger_interval,
            auto_plant=auto_plant,
            auto_resolve=auto_resolve,
            llm_model=model,
            llm_api_key=api_key,
            llm_api_base=base_url,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            'backend': self.backend.value if isinstance(self.backend, AnalyzerBackend) else self.backend,
            'trigger_interval': self.trigger_interval,
            'auto_plant': self.auto_plant,
            'auto_resolve': self.auto_resolve,
            'llm_model': self.llm_model,
        }
        # 不序列化 API key / base_url
        if self.llm_api_base:
            d['llm_api_base'] = self.llm_api_base
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any], api_key: str = None) -> 'ForeshadowingAnalyzerConfig':
        backend = data.get('backend', 'manual')
        if isinstance(backend, str):
            try:
                backend = AnalyzerBackend(backend)
            except ValueError:
                backend = AnalyzerBackend.MANUAL
        return cls(
            backend=backend,
            trigger_interval=data.get('trigger_interval', 10),
            auto_plant=data.get('auto_plant', True),
            auto_resolve=data.get('auto_resolve', False),
            llm_model=data.get('llm_model', 'gpt-4o-mini'),
            llm_api_key=api_key,
            llm_api_base=data.get('llm_api_base'),
        )


class ForeshadowingAnalyzer:
    """伏笔分析器"""

    def __init__(self, tracker=None, config: ForeshadowingAnalyzerConfig = None,
                 storage_dir: str = None, memory_provider=None, **kwargs):
        if tracker is None:
            raise ValueError("tracker 不能为 None")
        self.tracker = tracker
        self.config = config if isinstance(config, ForeshadowingAnalyzerConfig) else ForeshadowingAnalyzerConfig()
        # v7.0.5: 显式接收 storage_dir 和 memory_provider（之前被 **kwargs 静默吞掉）
        self.storage_dir = storage_dir
        self.memory_provider = memory_provider
        self._buffers: Dict[str, List[Dict[str, Any]]] = {}
        self._turn_counters: Dict[str, int] = {}
        self._llm_client = None

        if self.config.backend == AnalyzerBackend.LLM and self.config.llm_api_key:
            self._init_llm_client()

    @property
    def is_llm_enabled(self) -> bool:
        return self.config.backend == AnalyzerBackend.LLM and self._llm_client is not None

    def _init_llm_client(self):
        """初始化 LLM 客户端"""
        # v7.0.6: 实现 LLM 客户端初始化（之前为空 pass，导致 LLM 伏笔分析完全不可用）
        try:
            from ..utils.llm_client import LLMClient
            self._llm_client = LLMClient(
                model=self.config.llm_model,
                api_key=self.config.llm_api_key,
                api_base=self.config.llm_api_base,
            )
        except Exception as e:
            import logging
            logging.warning(f"[ForeshadowingAnalyzer] LLM 客户端初始化失败: {e}")
            self._llm_client = None

    def on_new_turn(self, content: str, role: str = "user",
                    user_id: str = "default", **kwargs) -> AnalysisResult:
        """处理新的对话轮次"""
        if user_id not in self._buffers:
            self._buffers[user_id] = []
            self._turn_counters[user_id] = 0
        self._buffers[user_id].append({
            'content': content,
            'role': role,
        })
        self._turn_counters[user_id] += 1

        # 手动模式不分析
        if self.config.backend == AnalyzerBackend.MANUAL:
            return AnalysisResult(triggered=False)

        # LLM 模式：检查是否达到分析间隔
        if self._turn_counters[user_id] >= self.config.trigger_interval:
            if self._llm_client:
                result = self._do_analysis(user_id)
                self._turn_counters[user_id] = 0
                return result

        return AnalysisResult(triggered=False)

    def trigger_analysis(self, user_id: str = "default") -> AnalysisResult:
        """手动触发分析"""
        if self.config.backend == AnalyzerBackend.MANUAL:
            return AnalysisResult(triggered=False, error="手动模式不支持 LLM 分析")

        buf = self._buffers.get(user_id, [])
        if not buf:
            return AnalysisResult(triggered=False, error="缓冲区为空 (empty buffer)")

        if not self._llm_client:
            return AnalysisResult(triggered=False, error="LLM 客户端未初始化")

        return self._do_analysis(user_id)

    def _do_analysis(self, user_id: str) -> AnalysisResult:
        """执行 LLM 分析"""
        buf = self._buffers.get(user_id, [])
        if not buf:
            return AnalysisResult(triggered=False, error="缓冲区为空")

        try:
            prompt = self._build_analysis_prompt(buf, user_id)
            response = self._llm_client.chat(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            result = self._parse_llm_response(response_text)

            # 自动埋下伏笔
            if self.config.auto_plant and result.new_foreshadowings:
                for fsh_data in result.new_foreshadowings:
                    self.tracker.plant(
                        content=fsh_data.get('content', ''),
                        user_id=user_id,
                        importance=fsh_data.get('importance', 0.5),
                        related_entities=fsh_data.get('related_entities', []),
                    )

            return result
        except Exception as e:
            return AnalysisResult(triggered=False, error=str(e))

    def _build_analysis_prompt(self, buffer: List[Dict], user_id: str) -> str:
        """构建分析提示"""
        conversation = "\n".join(
            f"[{turn['role']}]: {turn['content']}" for turn in buffer
        )
        active = self.tracker.get_active(user_id)
        existing = "\n".join(f"- {f.content}" for f in active) if active else "无"
        return f"分析以下对话中的伏笔：\n{conversation}\n\n已有伏笔：\n{existing}"

    def _parse_llm_response(self, response: str) -> AnalysisResult:
        """解析 LLM 响应"""
        try:
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_str = response.strip()

            data = json.loads(json_str)
            return AnalysisResult(
                triggered=True,
                new_foreshadowings=data.get('new_foreshadowings', []),
                potentially_resolved=data.get('potentially_resolved', []),
            )
        except (json.JSONDecodeError, Exception) as e:
            return AnalysisResult(
                triggered=False,
                new_foreshadowings=[],
                potentially_resolved=[],
                error=f"JSON 解析失败: {e}",
            )

    def get_buffer_size(self, user_id: str = "default") -> int:
        return len(self._buffers.get(user_id, []))

    def get_turns_until_analysis(self, user_id: str = "default") -> int:
        current = self._turn_counters.get(user_id, 0)
        return max(0, self.config.trigger_interval - current)

    def clear_buffer(self, user_id: str = "default"):
        self._buffers.pop(user_id, None)
        self._turn_counters.pop(user_id, None)

    def update_config(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        if self.config.trigger_interval < 1:
            self.config.trigger_interval = 1

    def enable_llm_mode(self, api_key: str, model: str = "gpt-4o-mini",
                        base_url: str = None):
        """启用 LLM 模式（动态切换，无需重启）
        
        v7.0.7: 新增方法 — engine.enable_foreshadowing_llm_mode() 需要此方法
        """
        self.config.backend = AnalyzerBackend.LLM
        self.config.llm_api_key = api_key
        self.config.llm_model = model
        if base_url is not None:
            self.config.llm_api_base = base_url
        self._init_llm_client()

    def disable_llm_mode(self):
        """禁用 LLM 模式，切换回手动模式
        
        v7.0.7: 新增方法 — engine.disable_foreshadowing_llm_mode() 需要此方法
        """
        self.config.backend = AnalyzerBackend.MANUAL
        self._llm_client = None

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_buffers': len(self._buffers),
            'enabled': self.is_llm_enabled,
        }
