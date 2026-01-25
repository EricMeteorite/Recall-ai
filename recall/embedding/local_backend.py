"""本地 Embedding 后端 - 使用 sentence-transformers"""

from typing import List
import numpy as np

from .base import EmbeddingBackend, EmbeddingConfig


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


class LocalEmbeddingBackend(EmbeddingBackend):
    """本地 sentence-transformers 后端
    
    优点：
    - 无需网络，完全离线
    - 无 API 费用
    - 隐私保护
    
    缺点：
    - 需要 ~800MB 内存（PyTorch + 模型）
    - 首次加载较慢
    """
    
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._model = None
        self._dimension = None
    
    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = self.model.get_sentence_embedding_dimension()
        return self._dimension
    
    @property
    def is_available(self) -> bool:
        """检查 sentence-transformers 是否可用"""
        try:
            import sentence_transformers
            return True
        except ImportError:
            return False
    
    @property
    def model(self):
        """懒加载模型"""
        if self._model is None:
            if not self.is_available:
                raise ImportError(
                    "sentence-transformers 未安装。\n"
                    "Local 模式需要安装: pip install sentence-transformers\n"
                    "或者切换到 Cloud 模式使用 API。"
                )
            
            from sentence_transformers import SentenceTransformer
            
            # 设置缓存目录
            import os
            cache_dir = os.environ.get('SENTENCE_TRANSFORMERS_HOME')
            
            _safe_print(f"[Embedding] 加载本地模型: {self.config.local_model}")
            self._model = SentenceTransformer(
                self.config.local_model,
                cache_folder=cache_dir
            )
        return self._model
    
    def encode(self, text: str) -> np.ndarray:
        """编码单个文本"""
        embedding = self.model.encode(
            text,
            normalize_embeddings=self.config.normalize
        )
        return embedding.astype('float32')
    
    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """批量编码"""
        embeddings = self.model.encode(
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=self.config.normalize,
            show_progress_bar=False
        )
        return embeddings.astype('float32')
