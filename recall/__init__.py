"""
Recall - AI永久记忆系统

让AI永远不会忘记你说过的每一句话。

使用方式：
    from recall import RecallEngine
    
    engine = RecallEngine()
    engine.process_turn("用户说的话", "AI回复")
    context = engine.build_context("新的问题")
"""

from .version import __version__
from .engine import RecallEngine

__all__ = ['RecallEngine', '__version__']
