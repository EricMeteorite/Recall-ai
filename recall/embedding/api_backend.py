"""API Embedding 后端 - 支持 OpenAI 和硅基流动"""

import os
import time
import threading
from typing import List, Optional
import numpy as np

from .base import EmbeddingBackend, EmbeddingConfig, EmbeddingBackendType


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


class RateLimiter:
    """简单的速率限制器
    
    限制单位时间内的请求次数，超限时自动等待。
    """
    
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        """
        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口长度（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: List[float] = []
        self._lock = threading.Lock()
    
    def acquire(self, timeout: float = 120.0) -> bool:
        """获取许可，超限时阻塞等待
        
        Args:
            timeout: 最大等待时间（秒）
        
        Returns:
            bool: 是否成功获取许可
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                now = time.time()
                
                # 清理过期的请求记录
                self.requests = [t for t in self.requests if now - t < self.window_seconds]
                
                # 检查是否可以发送
                if len(self.requests) < self.max_requests:
                    self.requests.append(now)
                    return True
                
                # 计算需要等待的时间
                oldest = min(self.requests) if self.requests else now
                wait_time = self.window_seconds - (now - oldest) + 0.1
            
            # 检查是否超时
            if time.time() - start_time + wait_time > timeout:
                _safe_print(f"[Embedding] 速率限制等待超时 ({timeout}秒)")
                return False
            
            # 等待
            _safe_print(f"[Embedding] API 限流，等待 {wait_time:.1f} 秒...")
            time.sleep(min(wait_time, 10))  # 最多等待10秒后重新检查


class APIEmbeddingBackend(EmbeddingBackend):
    """API Embedding 后端
    
    支持：
    - OpenAI text-embedding-3-small / text-embedding-3-large
    - 硅基流动 BAAI/bge-large-zh-v1.5
    - 自定义 OpenAI 兼容 API（中转站、Azure、Ollama 等）
    
    优点：
    - 内存占用极低 (~50MB)
    - 无需下载大模型
    - 支持最新模型
    
    缺点：
    - 需要网络连接
    - 有 API 费用（很便宜）
    """
    
    # 模型维度映射
    MODEL_DIMENSIONS = {
        # OpenAI
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
        # 硅基流动
        "BAAI/bge-large-zh-v1.5": 1024,
        "BAAI/bge-large-en-v1.5": 1024,
        "BAAI/bge-m3": 1024,
        # Google (通过兼容接口)
        "text-embedding-004": 768,
        "embedding-001": 768,
        # v5.0 新增
        "voyage-3": 1024,
        "voyage-3-lite": 512,
        "voyage-code-3": 1024,
        "embed-multilingual-v3.0": 1024,
        "embed-english-v3.0": 1024,
        "embed-multilingual-light-v3.0": 384,
    }
    
    # 默认 API 基地址
    DEFAULT_BASES = {
        EmbeddingBackendType.OPENAI: "https://api.openai.com/v1",
        EmbeddingBackendType.SILICONFLOW: "https://api.siliconflow.cn/v1",
        EmbeddingBackendType.CUSTOM: None,  # 必须指定
    }
    
    def __init__(self, config: EmbeddingConfig, cache_dir: str = None):
        super().__init__(config, cache_dir=cache_dir)
        self._client = None
        
        # 确定 API 基地址（优先使用配置，然后环境变量，最后默认值）
        self.api_base = (
            config.api_base or 
            os.environ.get('EMBEDDING_API_BASE') or
            self.DEFAULT_BASES.get(config.backend, "https://api.openai.com/v1")
        )
        
        # 获取 API key
        self.api_key = config.api_key or self._get_api_key_from_env()
        
        # 确定维度（优先使用配置，然后查表）
        self._dimension = config.dimension or self.MODEL_DIMENSIONS.get(
            config.api_model, 
            1536  # 默认
        )
        
        # 【新增】速率限制器 - 从环境变量读取配置
        rate_limit = int(os.environ.get('EMBEDDING_RATE_LIMIT', '10'))  # 默认每分钟10次
        rate_window = int(os.environ.get('EMBEDDING_RATE_WINDOW', '60'))  # 默认60秒窗口
        self._rate_limiter = RateLimiter(max_requests=rate_limit, window_seconds=rate_window)
        # v5.0: 自动检测 Embedding 提供商
        self._embedding_provider = self._detect_embedding_provider()
    
    def _get_api_key_from_env(self) -> Optional[str]:
        """从环境变量获取 API key
        
        统一使用 EMBEDDING_API_KEY，与 server.py 配置一致
        """
        return os.environ.get('EMBEDDING_API_KEY')
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def is_available(self) -> bool:
        """检查是否有 API key"""
        return bool(self.api_key)
    
    def _detect_embedding_provider(self) -> str:
        """根据 api_base 域名和模型名称自动检测 Embedding 提供商"""
        if self.api_base:
            from urllib.parse import urlparse
            hostname = urlparse(self.api_base.lower()).hostname or ''
            if hostname.endswith('.googleapis.com') or 'generativelanguage' in hostname:
                return 'google'
            if hostname.endswith('.voyageai.com') or 'voyage' in hostname:
                return 'voyage'
            if hostname.endswith('.cohere.com') or 'cohere' in hostname:
                return 'cohere'
            return 'openai'
        if self.config.api_model:
            model_lower = self.config.api_model.lower()
            if model_lower.startswith('voyage'):
                return 'voyage'
            if model_lower.startswith('embed-') and ('multilingual' in model_lower or 'english' in model_lower):
                return 'cohere'
            if model_lower.startswith('text-embedding-004') or model_lower.startswith('embedding-001'):
                return 'google'
        return 'openai'
    
    @property
    def client(self):
        """获取 Embedding 客户端（v5.0: 自动选择后端）"""
        if self._client is None:
            if not self.is_available:
                raise ValueError(
                    f"未配置 API key。\n"
                    f"请在配置文件 recall_data/config/api_keys.env 中设置:\n"
                    f"  EMBEDDING_API_KEY=your-api-key\n"
                    f"  EMBEDDING_API_BASE=https://api.openai.com/v1"
                )
            if self._embedding_provider == 'google':
                self._client = self._create_google_embedding_client()
            elif self._embedding_provider == 'voyage':
                self._client = self._create_voyage_client()
            elif self._embedding_provider == 'cohere':
                self._client = self._create_cohere_client()
            else:
                self._client = self._create_openai_embedding_client()
        return self._client
    
    def _create_openai_embedding_client(self):
        """创建 OpenAI Embedding 客户端"""
        from openai import OpenAI
        return OpenAI(api_key=self.api_key, base_url=self.api_base)
    
    def _create_google_embedding_client(self):
        """创建 Google Embedding 客户端"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            return genai
        except ImportError:
            raise ImportError("使用 Google Embedding 需要安装 google-generativeai: pip install google-generativeai")
    
    def _create_voyage_client(self):
        """创建 Voyage AI 客户端"""
        try:
            import voyageai
            return voyageai.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError("使用 Voyage Embedding 需要安装 voyageai: pip install voyageai")
    
    def _create_cohere_client(self):
        """创建 Cohere 客户端"""
        try:
            import cohere
            return cohere.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError("使用 Cohere Embedding 需要安装 cohere: pip install cohere")
    
    def encode(self, text: str) -> np.ndarray:
        """编码单个文本（v5.0: 自动路由到对应提供商）"""
        if self._embedding_provider == 'google':
            return self._encode_google(text)
        elif self._embedding_provider == 'voyage':
            return self._encode_voyage(text)
        elif self._embedding_provider == 'cohere':
            return self._encode_cohere(text)
        else:
            return self._encode_openai(text)
    
    def _encode_openai(self, text: str) -> np.ndarray:
        """OpenAI Embedding 编码（带速率限制和重试）"""
        max_retries = 3
        
        for attempt in range(max_retries):
            # 等待速率限制许可
            if not self._rate_limiter.acquire():
                raise RuntimeError("Embedding API 速率限制超时")
            
            try:
                response = self.client.embeddings.create(
                    model=self.config.api_model,
                    input=text
                )
                embedding = np.array(response.data[0].embedding, dtype='float32')
                
                if self.config.normalize:
                    embedding = embedding / np.linalg.norm(embedding)
                
                return embedding
                
            except Exception as e:
                error_str = str(e).lower()
                
                # 处理 429 错误（速率限制）
                if '429' in error_str or 'rate limit' in error_str:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 3  # 更快退避: 3, 6, 9 秒（总共最多18秒）
                        _safe_print(f"[Embedding] API 限流 (429)，等待 {wait_time} 秒后重试 ({attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                
                # 其他错误直接抛出
                raise
        
        raise RuntimeError(f"Embedding API 调用失败，已重试 {max_retries} 次")
    
    def _encode_google(self, text: str) -> np.ndarray:
        """Google Embedding 编码"""
        if not self._rate_limiter.acquire():
            raise RuntimeError("Embedding API 速率限制超时")
        result = self.client.embed_content(
            model=f"models/{self.config.api_model}",
            content=text
        )
        embedding = np.array(result['embedding'], dtype='float32')
        if self.config.normalize:
            embedding = embedding / np.linalg.norm(embedding)
        return embedding
    
    def _encode_voyage(self, text: str) -> np.ndarray:
        """Voyage AI Embedding 编码"""
        if not self._rate_limiter.acquire():
            raise RuntimeError("Embedding API 速率限制超时")
        result = self.client.embed([text], model=self.config.api_model)
        embedding = np.array(result.embeddings[0], dtype='float32')
        if self.config.normalize:
            embedding = embedding / np.linalg.norm(embedding)
        return embedding
    
    def _encode_cohere(self, text: str) -> np.ndarray:
        """Cohere Embedding 编码"""
        if not self._rate_limiter.acquire():
            raise RuntimeError("Embedding API 速率限制超时")
        result = self.client.embed(
            texts=[text],
            model=self.config.api_model,
            input_type="search_document"
        )
        embedding = np.array(result.embeddings[0], dtype='float32')
        if self.config.normalize:
            embedding = embedding / np.linalg.norm(embedding)
        return embedding
    
    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """批量编码（v5.0: 自动路由到对应提供商）"""
        if self._embedding_provider == 'google':
            return self._encode_batch_google(texts)
        elif self._embedding_provider == 'voyage':
            return self._encode_batch_voyage(texts)
        elif self._embedding_provider == 'cohere':
            return self._encode_batch_cohere(texts)
        else:
            return self._encode_batch_openai(texts)
    
    def _encode_batch_openai(self, texts: List[str]) -> np.ndarray:
        """OpenAI 批量编码（带速率限制和重试）"""
        # API 通常有批量限制，分批处理
        all_embeddings = []
        batch_size = min(self.config.batch_size, 100)  # OpenAI 限制
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            max_retries = 3
            for attempt in range(max_retries):
                # 等待速率限制许可
                if not self._rate_limiter.acquire():
                    raise RuntimeError("Embedding API 速率限制超时")
                
                try:
                    response = self.client.embeddings.create(
                        model=self.config.api_model,
                        input=batch
                    )
                    
                    for item in response.data:
                        embedding = np.array(item.embedding, dtype='float32')
                        if self.config.normalize:
                            embedding = embedding / np.linalg.norm(embedding)
                        all_embeddings.append(embedding)
                    
                    break  # 成功，跳出重试循环
                    
                except Exception as e:
                    error_str = str(e).lower()
                    
                    # 处理 429 错误
                    if '429' in error_str or 'rate limit' in error_str:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 3  # 更快退避: 3, 6, 9 秒
                            _safe_print(f"[Embedding] API 限流 (429)，等待 {wait_time} 秒后重试")
                            time.sleep(wait_time)
                            continue
                    
                    raise
        
        return np.array(all_embeddings)
    
    def _encode_batch_google(self, texts: List[str]) -> np.ndarray:
        """Google Embedding 批量编码"""
        all_embeddings = []
        for text in texts:
            if not self._rate_limiter.acquire():
                raise RuntimeError("Embedding API 速率限制超时")
            result = self.client.embed_content(
                model=f"models/{self.config.api_model}",
                content=text
            )
            embedding = np.array(result['embedding'], dtype='float32')
            if self.config.normalize:
                embedding = embedding / np.linalg.norm(embedding)
            all_embeddings.append(embedding)
        return np.array(all_embeddings)
    
    def _encode_batch_voyage(self, texts: List[str]) -> np.ndarray:
        """Voyage AI Embedding 批量编码"""
        all_embeddings = []
        batch_size = min(self.config.batch_size, 128)
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            if not self._rate_limiter.acquire():
                raise RuntimeError("Embedding API 速率限制超时")
            result = self.client.embed(batch, model=self.config.api_model)
            for emb in result.embeddings:
                embedding = np.array(emb, dtype='float32')
                if self.config.normalize:
                    embedding = embedding / np.linalg.norm(embedding)
                all_embeddings.append(embedding)
        return np.array(all_embeddings)
    
    def _encode_batch_cohere(self, texts: List[str]) -> np.ndarray:
        """Cohere Embedding 批量编码"""
        all_embeddings = []
        batch_size = min(self.config.batch_size, 96)
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            if not self._rate_limiter.acquire():
                raise RuntimeError("Embedding API 速率限制超时")
            result = self.client.embed(
                texts=batch,
                model=self.config.api_model,
                input_type="search_document"
            )
            for emb in result.embeddings:
                embedding = np.array(emb, dtype='float32')
                if self.config.normalize:
                    embedding = embedding / np.linalg.norm(embedding)
                all_embeddings.append(embedding)
        return np.array(all_embeddings)
