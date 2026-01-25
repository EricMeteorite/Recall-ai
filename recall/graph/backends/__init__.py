"""图存储后端模块

Phase 3.5: 企业级性能引擎

提供统一的图存储抽象层，支持多种后端：
- legacy: 现有 KnowledgeGraph 适配器（默认，确保100%向后兼容）
- json: 新的 JSON 文件后端（零依赖）
- kuzu: Kuzu 嵌入式图数据库（高性能，可选）
- neo4j: Neo4j 分布式数据库（企业级，可选）

使用方式：
    from recall.graph.backends import create_graph_backend, GraphBackend
    
    # 自动选择后端（默认使用 legacy 确保兼容）
    backend = create_graph_backend(data_path="./recall_data")
    
    # 强制使用特定后端
    backend = create_graph_backend(data_path, backend="kuzu")
"""

from .base import GraphBackend, GraphNode, GraphEdge
from .factory import create_graph_backend

__all__ = [
    'GraphBackend',
    'GraphNode',
    'GraphEdge',
    'create_graph_backend',
]
