"""LLM客户端 - 统一的LLM调用接口"""

import os
import time
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass


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


@dataclass
class LLMResponse:
    """LLM响应"""
    content: str
    model: str
    usage: Dict[str, int]
    latency_ms: float
    raw_response: Optional[Any] = None


class LLMClient:
    """统一LLM客户端
    
    支持 OpenAI 兼容接口：
    - OpenAI (gpt-4, gpt-3.5-turbo)
    - 硅基流动 (DeepSeek, Qwen 等)
    - Ollama 本地
    - 其他 OpenAI 兼容 API
    """
    
    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        self.model = model
        # 优先使用 LLM_API_KEY，兼容旧的 OPENAI_API_KEY
        self.api_key = api_key or os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')
        self.api_base = api_base or os.environ.get('LLM_API_BASE')
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 初始化客户端
        self._client = None
        # v5.0: 自动检测提供商（零新增配置）
        self._provider = self._detect_provider()
    
    def _detect_provider(self) -> str:
        """根据 api_base 域名和 model 名称自动检测提供商"""
        if self.api_base:
            from urllib.parse import urlparse
            hostname = urlparse(self.api_base.lower()).hostname or ''
            if hostname.endswith('.anthropic.com') or hostname == 'api.anthropic.com':
                return 'anthropic'
            if hostname.endswith('.googleapis.com') or 'generativelanguage' in hostname:
                return 'google'
            return 'openai'
        if self.model:
            model_lower = self.model.lower()
            if model_lower.startswith('claude'):
                return 'anthropic'
            if model_lower.startswith('gemini'):
                return 'google'
        return 'openai'
    
    @property
    def client(self):
        """获取 LLM 客户端（v5.0: 自动选择后端）"""
        if self._client is None:
            if self._provider == 'anthropic':
                self._client = self._create_anthropic_client()
            elif self._provider == 'google':
                self._client = self._create_google_client()
            else:
                self._client = self._create_openai_client()
        return self._client
    
    def _create_openai_client(self):
        """创建 OpenAI 客户端"""
        try:
            from openai import OpenAI
            client_kwargs = {
                "api_key": self.api_key,
                "timeout": self.timeout,
            }
            if self.api_base:
                client_kwargs["base_url"] = self.api_base
            return OpenAI(**client_kwargs)
        except ImportError:
            raise ImportError("openai 未安装。请运行: pip install openai")
    
    def _create_anthropic_client(self):
        """创建 Anthropic 客户端"""
        try:
            from anthropic import Anthropic
            return Anthropic(api_key=self.api_key, timeout=self.timeout)
        except ImportError:
            raise ImportError("使用 Claude 模型需要安装 anthropic: pip install anthropic")
    
    def _create_google_client(self):
        """创建 Google Generative AI 客户端"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            return genai
        except ImportError:
            raise ImportError("使用 Gemini 模型需要安装 google-generativeai: pip install google-generativeai")
    
    def complete(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None
    ) -> str:
        """简单文本补全
        
        Args:
            prompt: 提示词
            max_tokens: 最大输出 token 数，默认从 LLM_DEFAULT_MAX_TOKENS 环境变量读取（默认 2000）
            temperature: 温度参数
            stop: 停止词
        """
        if max_tokens is None:
            max_tokens = int(os.environ.get('LLM_DEFAULT_MAX_TOKENS', '2000'))
        response = self.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop
        )
        return response.content
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> LLMResponse:
        """聊天补全 - v5.0: 自动路由到对应提供商"""
        if max_tokens is None:
            max_tokens = int(os.environ.get('LLM_DEFAULT_MAX_TOKENS', '2000'))
        if self._provider == 'anthropic':
            return self._chat_anthropic(messages, max_tokens, temperature, stop)
        elif self._provider == 'google':
            return self._chat_google(messages, max_tokens, temperature, stop)
        else:
            return self._chat_openai(messages, max_tokens, temperature, stop, **kwargs)
    
    def _chat_openai(self, messages, max_tokens, temperature, stop, **kwargs):
        """OpenAI 聊天补全 - 带速率限制处理"""
        start_time = time.time()
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop,
                    **kwargs
                )
                
                latency = (time.time() - start_time) * 1000
                
                return LLMResponse(
                    content=response.choices[0].message.content,
                    model=response.model,
                    usage={
                        'prompt_tokens': response.usage.prompt_tokens,
                        'completion_tokens': response.usage.completion_tokens,
                        'total_tokens': response.usage.total_tokens
                    },
                    latency_ms=latency,
                    raw_response=response
                )
                
            except Exception as e:
                error_str = str(e).lower()
                
                # 特殊处理 429 错误（API 限流）
                if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
                    if attempt < self.max_retries - 1:
                        # 指数退避：15, 30, 45 秒
                        wait_time = (attempt + 1) * 15
                        _safe_print(f"[LLM] API 限流 (429)，等待 {wait_time} 秒后重试 ({attempt + 1}/{self.max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(f"LLM API 限流，已重试 {self.max_retries} 次: {e}")
                
                # 其他错误
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(1 * (attempt + 1))  # 普通重试间隔
        
        raise RuntimeError("LLM调用失败")
    
    def _chat_anthropic(self, messages, max_tokens, temperature, stop):
        """Anthropic 聊天补全"""
        start_time = time.time()
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg += msg['content'] + "\n"
            else:
                chat_messages.append(msg)
        kwargs = {}
        if system_msg.strip():
            kwargs['system'] = system_msg.strip()
        if stop:
            kwargs['stop_sequences'] = stop if isinstance(stop, list) else [stop]
        response = self.client.messages.create(
            model=self.model,
            messages=chat_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        latency = (time.time() - start_time) * 1000
        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            usage={
                'prompt_tokens': response.usage.input_tokens,
                'completion_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.input_tokens + response.usage.output_tokens
            },
            latency_ms=latency,
            raw_response=response
        )
    
    def _chat_google(self, messages, max_tokens, temperature, stop):
        """Google 聊天补全"""
        start_time = time.time()
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg += msg['content'] + "\n"
            else:
                chat_messages.append(msg)
        model_kwargs = {}
        if system_msg.strip():
            model_kwargs['system_instruction'] = system_msg.strip()
        model = self.client.GenerativeModel(self.model, **model_kwargs)
        contents = [{'role': 'user' if m['role'] == 'user' else 'model',
                     'parts': [m['content']]} for m in chat_messages]
        response = model.generate_content(
            contents,
            generation_config={
                'max_output_tokens': max_tokens,
                'temperature': temperature,
                'stop_sequences': stop or [],
            }
        )
        latency = (time.time() - start_time) * 1000
        return LLMResponse(
            content=response.text,
            model=self.model,
            usage={
                'prompt_tokens': getattr(response.usage_metadata, 'prompt_token_count', 0),
                'completion_tokens': getattr(response.usage_metadata, 'candidates_token_count', 0),
                'total_tokens': getattr(response.usage_metadata, 'total_token_count', 0),
            },
            latency_ms=latency,
            raw_response=response
        )
    
    async def achat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """异步聊天补全 - v5.0: 自动路由到对应提供商
        
        Args:
            max_tokens: 最大输出 token 数，默认从 LLM_DEFAULT_MAX_TOKENS 环境变量读取
        """
        if max_tokens is None:
            max_tokens = int(os.environ.get('LLM_DEFAULT_MAX_TOKENS', '2000'))
        if self._provider == 'anthropic':
            return await self._achat_anthropic(messages, max_tokens, temperature, **kwargs)
        elif self._provider == 'google':
            return await self._achat_google(messages, max_tokens, temperature, **kwargs)
        else:
            return await self._achat_openai(messages, max_tokens, temperature, **kwargs)
    
    async def _achat_openai(self, messages, max_tokens, temperature, **kwargs):
        """异步 OpenAI 聊天补全"""
        from openai import AsyncOpenAI
        
        start_time = time.time()
        
        client_kwargs = {
            "api_key": self.api_key,
            "timeout": self.timeout,
        }
        if self.api_base:
            client_kwargs["base_url"] = self.api_base
        
        async_client = AsyncOpenAI(**client_kwargs)
        
        response = await async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
        
        latency = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            },
            latency_ms=latency,
            raw_response=response
        )
    
    async def _achat_anthropic(self, messages, max_tokens, temperature, **kwargs):
        """异步 Anthropic 聊天补全"""
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("使用 Claude 模型需要安装 anthropic: pip install anthropic")
        
        start_time = time.time()
        
        async_client = AsyncAnthropic(api_key=self.api_key, timeout=self.timeout)
        
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg += msg['content'] + "\n"
            else:
                chat_messages.append(msg)
        
        ak = {}
        if system_msg.strip():
            ak['system'] = system_msg.strip()
        stop = kwargs.get('stop')
        if stop:
            ak['stop_sequences'] = stop if isinstance(stop, list) else [stop]
        
        response = await async_client.messages.create(
            model=self.model,
            messages=chat_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **ak,
        )
        
        latency = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            usage={
                'prompt_tokens': response.usage.input_tokens,
                'completion_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.input_tokens + response.usage.output_tokens
            },
            latency_ms=latency,
            raw_response=response
        )
    
    async def _achat_google(self, messages, max_tokens, temperature, **kwargs):
        """异步 Google 聊天补全"""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("使用 Gemini 模型需要安装 google-generativeai: pip install google-generativeai")
        
        start_time = time.time()
        
        genai.configure(api_key=self.api_key)
        
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_msg += msg['content'] + "\n"
            else:
                chat_messages.append(msg)
        
        model_kwargs = {}
        if system_msg.strip():
            model_kwargs['system_instruction'] = system_msg.strip()
        
        model = genai.GenerativeModel(self.model, **model_kwargs)
        
        contents = [{'role': 'user' if m['role'] == 'user' else 'model',
                     'parts': [m['content']]} for m in chat_messages]
        
        stop = kwargs.get('stop')
        response = await model.generate_content_async(
            contents,
            generation_config={
                'max_output_tokens': max_tokens,
                'temperature': temperature,
                'stop_sequences': stop or [],
            }
        )
        
        latency = (time.time() - start_time) * 1000
        
        return LLMResponse(
            content=response.text,
            model=self.model,
            usage={
                'prompt_tokens': getattr(response.usage_metadata, 'prompt_token_count', 0),
                'completion_tokens': getattr(response.usage_metadata, 'candidates_token_count', 0),
                'total_tokens': getattr(response.usage_metadata, 'total_token_count', 0),
            },
            latency_ms=latency,
            raw_response=response
        )
    
    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None
    ) -> List[List[float]]:
        """获取嵌入向量"""
        if self._provider != 'openai':
            raise NotImplementedError("请使用 APIEmbeddingBackend 进行 Embedding")
        if isinstance(texts, str):
            texts = [texts]
        
        embed_model = model or "text-embedding-ada-002"
        
        response = self.client.embeddings.create(
            model=embed_model,
            input=texts
        )
        
        return [item.embedding for item in response.data]
    
    def extract_entities(self, text: str) -> List[Dict[str, str]]:
        """使用LLM提取实体"""
        prompt = f"""从以下文本中提取实体（人名、地名、组织、物品等）。
以JSON格式返回：[{{"name": "实体名", "type": "类型"}}]

文本：{text}

实体："""
        
        # 实体提取输出相对固定，使用较小的默认值
        response = self.complete(prompt, temperature=0)
        
        try:
            import json
            return json.loads(response)
        except Exception:
            return []
    
    def summarize(self, text: str, max_length: int = 100) -> str:
        """使用LLM摘要"""
        prompt = f"""请用{max_length}字以内摘要以下内容，保留关键信息：

{text}

摘要："""
        
        return self.complete(prompt, max_tokens=max_length * 2, temperature=0.3)
    
    def check_relevance(
        self,
        query: str,
        documents: List[str]
    ) -> List[float]:
        """检查文档与查询的相关性"""
        prompt = f"""对以下文档与查询的相关性评分（0-1）。

查询：{query}

文档：
{chr(10).join([f"{i+1}. {d[:100]}" for i, d in enumerate(documents)])}

请只返回分数，用逗号分隔："""
        
        # 相关性评分输出很短，使用较小的默认值
        response = self.complete(prompt, max_tokens=100, temperature=0)
        
        try:
            scores = [float(s.strip()) for s in response.split(',')]
            return scores[:len(documents)]
        except Exception:
            return [0.5] * len(documents)
