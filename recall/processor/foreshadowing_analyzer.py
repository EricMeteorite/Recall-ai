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
import os
import time
import threading
from enum import Enum
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Callable
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
    max_context_turns: int = field(default_factory=lambda: int(os.environ.get('CONTEXT_MAX_CONTEXT_TURNS', '20')))     # 发送给 LLM 的最大轮次数（从环境变量读取，与持久条件统一）
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
        
        # 从环境变量读取默认值，保持一致性
        default_max_context_turns = int(os.environ.get('CONTEXT_MAX_CONTEXT_TURNS', '20'))
        
        return cls(
            backend=backend,
            trigger_interval=data.get('trigger_interval', 10),
            llm_model=data.get('llm_model', 'gpt-4o-mini'),
            llm_api_key=api_key,
            llm_base_url=data.get('llm_base_url'),
            auto_plant=data.get('auto_plant', True),
            auto_resolve=data.get('auto_resolve', False),
            include_resolved_check=data.get('include_resolved_check', True),
            max_context_turns=data.get('max_context_turns', default_max_context_turns),
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
        config: Optional[ForeshadowingAnalyzerConfig] = None,
        storage_dir: Optional[str] = None,
        memory_provider: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None
    ):
        """初始化分析器
        
        Args:
            tracker: ForeshadowingTracker 实例（必需）
            config: 分析器配置（可选，默认为手动模式）
            storage_dir: 持久化目录（可选，用于保存分析状态）
            memory_provider: 获取记忆的回调函数（可选），签名: (user_id, limit) -> List[Dict]
                           用于从已保存的记忆构建对话，提高可靠性
        """
        if tracker is None:
            raise ValueError("tracker 参数不能为 None")
        
        self.tracker = tracker
        self.config = config or ForeshadowingAnalyzerConfig.manual()
        self._storage_dir = storage_dir
        self._memory_provider = memory_provider
        
        # 对话缓冲区（按用户分隔）
        self._buffers: Dict[str, List[Dict[str, Any]]] = {}
        # 轮次计数器（按用户分隔）
        self._turn_counters: Dict[str, int] = {}
        
        # 【新增】分析锁（按用户分隔，防止并发分析冲突）
        self._analysis_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()  # 保护 _analysis_locks 字典本身
        
        # 【新增】最后分析位置记录（按用户分隔）
        # 格式: {user_id: {'last_memory_id': str, 'last_timestamp': float}}
        self._analysis_markers: Dict[str, Dict[str, Any]] = {}
        
        # 【新增】从持久化文件加载分析状态
        if storage_dir:
            os.makedirs(storage_dir, exist_ok=True)
            self._load_analysis_markers()
        
        # LLM 客户端（懒加载）
        self._llm_client = None
        
        # 初始化 LLM 客户端（如果是 LLM 模式）
        if self.config.backend == AnalyzerBackend.LLM:
            self._init_llm_client()
    
    def _get_user_lock(self, user_id: str) -> threading.Lock:
        """获取指定用户的分析锁（线程安全）"""
        with self._locks_lock:
            if user_id not in self._analysis_locks:
                self._analysis_locks[user_id] = threading.Lock()
            return self._analysis_locks[user_id]
    
    def _get_markers_file_path(self) -> Optional[str]:
        """获取分析标记文件路径"""
        if not self._storage_dir:
            return None
        return os.path.join(self._storage_dir, 'analysis_markers.json')
    
    def _load_analysis_markers(self):
        """从文件加载分析标记（服务器重启时恢复状态）"""
        markers_file = self._get_markers_file_path()
        if not markers_file or not os.path.exists(markers_file):
            return
        
        try:
            with open(markers_file, 'r', encoding='utf-8') as f:
                self._analysis_markers = json.load(f)
            print(f"[Recall] 已加载伏笔分析状态（{len(self._analysis_markers)} 个用户）")
        except Exception as e:
            print(f"[Recall] 加载分析标记失败: {e}")
            self._analysis_markers = {}
    
    def _save_analysis_markers(self):
        """保存分析标记到文件"""
        markers_file = self._get_markers_file_path()
        if not markers_file:
            return
        
        try:
            with open(markers_file, 'w', encoding='utf-8') as f:
                json.dump(self._analysis_markers, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Recall] 保存分析标记失败: {e}")
    
    def _update_analysis_marker(self, user_id: str, memory_id: Optional[str] = None):
        """更新指定用户的分析标记"""
        self._analysis_markers[user_id] = {
            'last_memory_id': memory_id,
            'last_timestamp': time.time()
        }
        self._save_analysis_markers()

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
        user_id: str = "default",
        character_id: str = "default"
    ) -> AnalysisResult:
        """处理新的一轮对话
        
        在每轮对话后调用此方法。LLM 模式下会累积对话并在达到触发条件时分析。
        
        Args:
            content: 对话内容
            role: 角色（user/assistant）
            user_id: 用户ID
            character_id: 角色ID（用于多角色场景）
            
        Returns:
            AnalysisResult: 分析结果（如果触发了分析）
        """
        # 使用复合键区分不同用户/角色
        cache_key = f"{user_id}/{character_id}"
        
        # 添加到缓冲区
        if cache_key not in self._buffers:
            self._buffers[cache_key] = []
        
        self._buffers[cache_key].append({
            'role': role,
            'content': content,
            'timestamp': time.time()
        })
        
        # 限制缓冲区大小
        max_size = self.config.max_context_turns * 2  # 考虑 user + assistant
        if len(self._buffers[cache_key]) > max_size:
            self._buffers[cache_key] = self._buffers[cache_key][-max_size:]
        
        # 增加轮次计数
        if cache_key not in self._turn_counters:
            self._turn_counters[cache_key] = 0
        self._turn_counters[cache_key] += 1
        
        # 检查是否应该触发分析（仅 LLM 模式）
        if self.config.backend == AnalyzerBackend.LLM:
            current_count = self._turn_counters[cache_key]
            if current_count >= self.config.trigger_interval:
                print(f"[ForeshadowAnalyzer] 🔄 触发分析: user={cache_key}")
                print(f"[ForeshadowAnalyzer]    轮次={current_count}, 间隔={self.config.trigger_interval}")
                self._turn_counters[cache_key] = 0
                return self._trigger_llm_analysis(user_id, character_id)
        
        # 手动模式不做任何分析
        return AnalysisResult(triggered=False)
    
    def trigger_analysis(self, user_id: str = "default", character_id: str = "default") -> AnalysisResult:
        """手动触发分析
        
        可以在任何模式下调用。如果是 LLM 模式且有配置，会使用 LLM 分析。
        否则返回空结果。
        
        Args:
            user_id: 用户ID
            character_id: 角色ID（用于多角色场景）
            
        Returns:
            AnalysisResult: 分析结果
        """
        if self.is_llm_enabled:
            return self._trigger_llm_analysis(user_id, character_id)
        
        return AnalysisResult(
            triggered=False,
            error="LLM 分析未启用（需配置 API key）"
        )
    
    def _get_conversation_from_memories(self, user_id: str, character_id: str = "default") -> List[Dict[str, Any]]:
        """从已保存的记忆中获取对话内容
        
        这是对 buffer 的补充/替代，确保即使 buffer 丢失也能从记忆恢复。
        优先使用 memory_provider（如果配置），否则使用 buffer。
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
            
        Returns:
            List[Dict]: 对话列表，格式与 buffer 相同
        """
        cache_key = f"{user_id}/{character_id}"
        
        if not self._memory_provider:
            # 没有配置 memory_provider，使用原有的 buffer
            return self._buffers.get(cache_key, [])
        
        try:
            # 获取最近的记忆（限制数量）
            limit = self.config.max_context_turns * 2
            memories = self._memory_provider(user_id, limit)
            
            if not memories:
                # 记忆为空，回退到 buffer
                return self._buffers.get(cache_key, [])
            
            # 转换记忆格式为对话格式
            conversations = []
            for mem in memories:
                metadata = mem.get('metadata', {})
                role = metadata.get('role', 'user')
                content = mem.get('content', '')
                timestamp = metadata.get('timestamp', 0)
                
                if content:
                    conversations.append({
                        'role': role,
                        'content': content,
                        'timestamp': timestamp,
                        'memory_id': metadata.get('id')  # 保留记忆ID用于标记
                    })
            
            # 按时间戳排序（确保顺序正确）
            conversations.sort(key=lambda x: x.get('timestamp', 0))
            
            return conversations
            
        except Exception as e:
            print(f"[Recall] 从记忆获取对话失败: {e}，回退到 buffer")
            return self._buffers.get(cache_key, [])
    
    def _trigger_llm_analysis(self, user_id: str, character_id: str = "default") -> AnalysisResult:
        """触发 LLM 分析（带锁保护）
        
        Args:
            user_id: 用户ID
            character_id: 角色ID
        """
        if not self.is_llm_enabled:
            return AnalysisResult(
                triggered=False,
                error="LLM 客户端未初始化"
            )
        
        cache_key = f"{user_id}/{character_id}"
        
        # 【新增】获取用户/角色锁，防止同一用户/角色的并发分析
        user_lock = self._get_user_lock(cache_key)
        
        # 尝试获取锁，如果已经有分析在进行则跳过
        if not user_lock.acquire(blocking=False):
            print(f"[ForeshadowAnalyzer] ⏭️ 跳过: 用户 {cache_key} 的分析正在进行中")
            return AnalysisResult(
                triggered=False,
                error="分析正在进行中"
            )
        
        try:
            # 【改进】优先从已保存的记忆获取对话
            conversations = self._get_conversation_from_memories(user_id, character_id)
            
            if not conversations:
                return AnalysisResult(
                    triggered=True,
                    error="对话缓冲区为空"
                )
            
            # 限制对话数量
            conversations = conversations[-self.config.max_context_turns * 2:]
            
            # 构建对话文本
            conversation_text = self._format_conversation(conversations)
            
            # 获取当前活跃的伏笔
            active = self.tracker.get_active(user_id, character_id)
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
                conversation=conversation_text
            )
            
            # 调用 LLM
            print(f"[ForeshadowAnalyzer] 🤖 调用 LLM 分析...")
            print(f"[ForeshadowAnalyzer]    用户={cache_key}, 对话数={len(conversations)}, 活跃伏笔={len(active)}")
            response = self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # 低温度，更确定性
                max_tokens=1000
            )
            print(f"[ForeshadowAnalyzer]    LLM 响应: {len(response.content)} 字符")
            
            # 解析结果
            result = self._parse_llm_response(response.content)
            result.triggered = True
            
            # 处理结果：自动埋下伏笔
            if self.config.auto_plant and result.new_foreshadowings:
                print(f"[ForeshadowAnalyzer] 🌱 自动埋下 {len(result.new_foreshadowings)} 个新伏笔")
                for fsh_data in result.new_foreshadowings:
                    try:
                        content = fsh_data.get('content', '')
                        print(f"[ForeshadowAnalyzer]    埋下: {content[:50]}..." if len(content) > 50 else f"[ForeshadowAnalyzer]    埋下: {content}")
                        self.tracker.plant(
                            content=content,
                            user_id=user_id,
                            character_id=character_id,
                            importance=fsh_data.get('importance', 0.5),
                            related_entities=fsh_data.get('related_entities', [])
                        )
                    except Exception as e:
                        print(f"[ForeshadowAnalyzer] ❌ 埋下失败: {e}")
            
            # 处理结果：自动解决伏笔
            if self.config.auto_resolve and result.potentially_resolved:
                print(f"[ForeshadowAnalyzer] ✅ 检测到 {len(result.potentially_resolved)} 个可能解决的伏笔")
                for resolved_data in result.potentially_resolved:
                    fsh_id = resolved_data.get('foreshadowing_id')
                    confidence = resolved_data.get('confidence', 0)
                    evidence = resolved_data.get('evidence', '')
                    
                    print(f"[ForeshadowAnalyzer]    检测: id={fsh_id}, 置信度={confidence:.2f}")
                    
                    # 只有置信度高于0.8才自动解决
                    if fsh_id and confidence >= 0.8:
                        try:
                            print(f"[ForeshadowAnalyzer]    自动解决: {evidence[:50]}..." if len(evidence) > 50 else f"[ForeshadowAnalyzer]    自动解决: {evidence}")
                            self.tracker.resolve(
                                foreshadowing_id=fsh_id,
                                resolution=f"[自动检测] {evidence}",
                                user_id=user_id,
                                character_id=character_id
                            )
                        except Exception as e:
                            print(f"[ForeshadowAnalyzer] ❌ 自动解决失败: {e}")
                    else:
                        print(f"[ForeshadowAnalyzer]    跳过: 置信度不足 ({confidence:.2f} < 0.8)")
            
            # 【改进】更新分析标记（记录最后分析的记忆ID）
            cache_key = f"{user_id}/{character_id}"
            last_memory_id = None
            if conversations and 'memory_id' in conversations[-1]:
                last_memory_id = conversations[-1]['memory_id']
            self._update_analysis_marker(cache_key, last_memory_id)
            
            # 清空已分析的缓冲区
            self._buffers[cache_key] = []
            
            print(f"[ForeshadowAnalyzer] ✅ 分析完成: 新伏笔={len(result.new_foreshadowings)}, 可能解决={len(result.potentially_resolved)}")
            
            return result
            
        except Exception as e:
            print(f"[ForeshadowAnalyzer] ❌ LLM 分析异常: {e}")
            import traceback
            traceback.print_exc()
            return AnalysisResult(
                triggered=True,
                error=f"LLM 分析失败: {str(e)}"
            )
        finally:
            # 【重要】确保释放锁
            user_lock.release()
    
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
    
    def get_buffer_size(self, user_id: str = "default", character_id: str = "default") -> int:
        """获取当前缓冲区大小"""
        cache_key = f"{user_id}/{character_id}"
        return len(self._buffers.get(cache_key, []))
    
    def get_turns_until_analysis(self, user_id: str = "default", character_id: str = "default") -> int:
        """获取距离下次分析还需要多少轮"""
        if self.config.backend != AnalyzerBackend.LLM:
            return -1  # 手动模式不会自动分析
        
        cache_key = f"{user_id}/{character_id}"
        current = self._turn_counters.get(cache_key, 0)
        return self.config.trigger_interval - current
    
    def clear_buffer(self, user_id: str = "default", character_id: str = "default"):
        """清空对话缓冲区"""
        cache_key = f"{user_id}/{character_id}"
        if cache_key in self._buffers:
            self._buffers[cache_key] = []
        if cache_key in self._turn_counters:
            self._turn_counters[cache_key] = 0
    
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
    
    def enable_llm_mode(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None
    ):
        """动态启用 LLM 模式（无需重启服务）
        
        Args:
            api_key: LLM API Key
            model: 模型名称
            base_url: API Base URL（可选）
        """
        # 更新配置
        self.config.backend = AnalyzerBackend.LLM
        self.config.llm_api_key = api_key
        self.config.llm_model = model
        self.config.llm_base_url = base_url
        
        # 重新初始化 LLM 客户端
        self._init_llm_client()
        
        if self._llm_client:
            print(f"[Recall] 伏笔分析器已切换到 LLM 模式 (model={model})")
        else:
            print("[Recall] 警告：LLM 客户端初始化失败")
    
    def disable_llm_mode(self):
        """动态禁用 LLM 模式，切换回手动模式（无需重启服务）"""
        self.config.backend = AnalyzerBackend.MANUAL
        self._llm_client = None
        print("[Recall] 伏笔分析器已切换到手动模式")
