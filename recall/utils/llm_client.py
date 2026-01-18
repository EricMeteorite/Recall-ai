"""LLM客户端 - 统一的LLM调用接口"""

import os
import time
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass


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
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        self.api_base = api_base
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 初始化 OpenAI 客户端
        self._client = None
    
    @property
    def client(self):
        """获取 OpenAI 客户端"""
        if self._client is None:
            try:
                from openai import OpenAI
                
                # 创建客户端
                client_kwargs = {
                    "api_key": self.api_key,
                    "timeout": self.timeout,
                }
                
                # 设置自定义 API 地址
                if self.api_base:
                    client_kwargs["base_url"] = self.api_base
                
                self._client = OpenAI(**client_kwargs)
                    
            except ImportError:
                raise ImportError(
                    "openai 未安装。请运行: pip install openai"
                )
        return self._client
    
    def complete(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None
    ) -> str:
        """简单文本补全"""
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
        max_tokens: int = 500,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> LLMResponse:
        """聊天补全 - 使用 OpenAI SDK"""
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
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(1 * (attempt + 1))  # 指数退避
        
        raise RuntimeError("LLM调用失败")
    
    async def achat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 500,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """异步聊天补全"""
        from openai import AsyncOpenAI
        
        start_time = time.time()
        
        # 创建异步客户端
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
    
    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None
    ) -> List[List[float]]:
        """获取嵌入向量"""
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
        
        response = self.complete(prompt, max_tokens=200, temperature=0)
        
        try:
            import json
            return json.loads(response)
        except:
            return []
    
    def summarize(self, text: str, max_length: int = 100) -> str:
        """使用LLM摘要"""
        prompt = f"""请用{max_length}字以内摘要以下内容，保留关键信息：

{text}

摘要："""
        
        return self.complete(prompt, max_tokens=max_length, temperature=0.3)
    
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
        
        response = self.complete(prompt, max_tokens=50, temperature=0)
        
        try:
            scores = [float(s.strip()) for s in response.split(',')]
            return scores[:len(documents)]
        except:
            return [0.5] * len(documents)
