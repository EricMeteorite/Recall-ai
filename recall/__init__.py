"""
Recall - AI永久记忆系统

让AI永远不会忘记你说过的每一句话。

使用方式：
    from recall import RecallEngine
    
    engine = RecallEngine()
    engine.add("用户说的话", user_id="user1")
    context = engine.build_context("新的问题", user_id="user1")
"""

import os as _os

# 确保所有缓存都在项目目录内，不污染系统环境
def _setup_isolated_environment():
    """设置隔离的环境变量，确保缓存不污染系统"""
    # 获取项目数据目录
    data_root = _os.environ.get('RECALL_DATA_ROOT') or _os.path.abspath('./recall_data')
    cache_dir = _os.path.join(data_root, 'cache')
    _os.makedirs(cache_dir, exist_ok=True)
    
    # jieba 缓存目录
    jieba_cache = _os.path.join(cache_dir, 'jieba.cache')
    _os.environ.setdefault('JIEBA_CACHE', jieba_cache)
    
    # HuggingFace 缓存目录
    hf_cache = _os.path.join(data_root, 'models', 'huggingface')
    _os.environ.setdefault('HF_HOME', hf_cache)
    _os.environ.setdefault('TRANSFORMERS_CACHE', hf_cache)
    
    # Torch 缓存目录
    torch_cache = _os.path.join(data_root, 'models', 'torch')
    _os.environ.setdefault('TORCH_HOME', torch_cache)
    
    # Sentence Transformers 缓存
    st_cache = _os.path.join(data_root, 'models', 'sentence-transformers')
    _os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', st_cache)

_setup_isolated_environment()

from .version import __version__
from .engine import RecallEngine

__all__ = ['RecallEngine', '__version__']
