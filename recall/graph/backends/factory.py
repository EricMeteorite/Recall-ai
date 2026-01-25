"""图后端工厂

Phase 3.5: 企业级性能引擎

提供统一的后端创建接口，支持自动选择最优后端。

选择策略（向后兼容优先）：
1. 如果已有 knowledge_graph.json，使用 legacy 适配器（默认）
2. 如果已有 kuzu/ 或 nodes.json，使用对应后端
3. 如果节点数量 >10万 且 Kuzu 已安装，使用 Kuzu
4. **默认使用 legacy（现有 KnowledgeGraph）确保 100% 向后兼容**
"""

import os
import logging
from typing import Optional, TYPE_CHECKING

from .base import GraphBackend


if TYPE_CHECKING:
    from ..knowledge_graph import KnowledgeGraph


logger = logging.getLogger(__name__)


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def create_graph_backend(
    data_path: str,
    backend: str = "auto",
    node_count_hint: Optional[int] = None,
    existing_knowledge_graph: Optional["KnowledgeGraph"] = None
) -> GraphBackend:
    """创建图后端
    
    Args:
        data_path: 数据存储路径
        backend: 后端类型
            - "auto": 自动选择（推荐）
            - "legacy": 使用现有 KnowledgeGraph（默认，确保向后兼容）
            - "json": 新 JSON 文件后端
            - "kuzu": Kuzu 嵌入式（高性能，可选依赖）
            - "neo4j": Neo4j（分布式，需配置）
        node_count_hint: 预估节点数量（用于自动选择）
        existing_knowledge_graph: 现有 KnowledgeGraph 实例（用于 legacy 适配）
    
    Returns:
        GraphBackend 实例
    
    Examples:
        # 自动选择（默认使用 legacy 确保兼容）
        backend = create_graph_backend("./recall_data/data")
        
        # 强制使用 Kuzu（需要安装 kuzu）
        backend = create_graph_backend("./recall_data/data", backend="kuzu")
        
        # 使用现有 KnowledgeGraph
        kg = KnowledgeGraph("./recall_data/data")
        backend = create_graph_backend("./recall_data/data", backend="legacy", existing_knowledge_graph=kg)
    """
    
    if backend == "auto":
        backend = _auto_select_backend(data_path, node_count_hint)
        logger.info(f"[GraphBackend] Auto-selected backend: {backend}")
    
    # 优先使用现有 KnowledgeGraph 适配器（确保向后兼容）
    if backend == "legacy":
        return _create_legacy_backend(data_path, existing_knowledge_graph)
    
    if backend == "json":
        return _create_json_backend(data_path)
    
    if backend == "kuzu":
        return _create_kuzu_backend(data_path)
    
    if backend == "neo4j":
        return _create_neo4j_backend(data_path)
    
    raise ValueError(f"Unknown backend: {backend}. Supported: auto, legacy, json, kuzu, neo4j")


def _auto_select_backend(data_path: str, node_count_hint: Optional[int] = None) -> str:
    """自动选择最优后端
    
    选择策略（向后兼容优先）：
    1. 如果已有 knowledge_graph.json，使用 legacy 适配器
    2. 如果已有 kuzu/ 或 nodes.json，使用对应后端
    3. 如果节点数量 >10万 且 Kuzu 已安装，使用 Kuzu
    4. **默认使用 legacy（现有 KnowledgeGraph）确保 100% 向后兼容**
    
    Args:
        data_path: 数据存储路径
        node_count_hint: 预估节点数量
        
    Returns:
        后端类型字符串
    """
    
    # 优先检测现有 KnowledgeGraph 数据（确保向后兼容！）
    legacy_file = os.path.join(data_path, "knowledge_graph.json")
    if os.path.exists(legacy_file):
        logger.debug(f"[GraphBackend] Found existing knowledge_graph.json, using legacy backend")
        return "legacy"
    
    # 检测 Kuzu 数据目录
    kuzu_db = os.path.join(data_path, "kuzu")
    if os.path.exists(kuzu_db) and os.path.isdir(kuzu_db):
        try:
            import kuzu
            logger.debug(f"[GraphBackend] Found existing kuzu/ directory, using kuzu backend")
            return "kuzu"
        except ImportError:
            logger.warning("[GraphBackend] Found kuzu/ directory but kuzu not installed")
    
    # 检测新格式 JSON 数据
    json_nodes = os.path.join(data_path, "nodes.json")
    if os.path.exists(json_nodes):
        logger.debug(f"[GraphBackend] Found existing nodes.json, using json backend")
        return "json"
    
    # 大规模场景优化
    auto_kuzu_threshold = int(os.environ.get("AUTO_KUZU_THRESHOLD", "100000"))
    auto_neo4j_threshold = int(os.environ.get("AUTO_NEO4J_THRESHOLD", "1000000"))
    
    if node_count_hint and node_count_hint > auto_kuzu_threshold:
        try:
            import kuzu
            logger.info(f"[GraphBackend] Large dataset ({node_count_hint} nodes), using kuzu backend")
            return "kuzu"
        except ImportError:
            _safe_print("[Recall] [WARN] Large dataset expected but Kuzu not installed")
            _safe_print("[Recall] [HINT] Install with: pip install kuzu")
    
    if node_count_hint and node_count_hint > auto_neo4j_threshold:
        neo4j_uri = os.environ.get("NEO4J_URI")
        if neo4j_uri:
            logger.info(f"[GraphBackend] Very large dataset ({node_count_hint} nodes), using neo4j backend")
            return "neo4j"
    
    # 默认使用 legacy（现有 KnowledgeGraph），确保向后兼容！
    return "legacy"


def _create_legacy_backend(
    data_path: str,
    existing_knowledge_graph: Optional["KnowledgeGraph"] = None
) -> GraphBackend:
    """创建 Legacy 适配器后端"""
    from .legacy_adapter import LegacyKnowledgeGraphAdapter
    
    if existing_knowledge_graph is None:
        from ..knowledge_graph import KnowledgeGraph
        existing_knowledge_graph = KnowledgeGraph(data_path)
    
    return LegacyKnowledgeGraphAdapter(existing_knowledge_graph)


def _create_json_backend(data_path: str) -> GraphBackend:
    """创建 JSON 后端"""
    from .json_backend import JSONGraphBackend
    
    # JSON 后端使用子目录
    graph_data_path = os.path.join(data_path, "graph_json")
    return JSONGraphBackend(graph_data_path)


def _create_kuzu_backend(data_path: str) -> GraphBackend:
    """创建 Kuzu 后端"""
    try:
        from .kuzu_backend import KuzuGraphBackend
        
        # Kuzu 后端使用子目录
        kuzu_data_path = os.path.join(data_path, "kuzu")
        buffer_pool_size = int(os.environ.get("KUZU_BUFFER_POOL_SIZE", "256"))
        
        return KuzuGraphBackend(kuzu_data_path, buffer_pool_size=buffer_pool_size)
    except ImportError as e:
        _safe_print(f"[Recall] [WARN] Kuzu not installed: {e}")
        _safe_print("[Recall] [HINT] Install with: pip install kuzu")
        _safe_print("[Recall] [HINT] Falling back to JSON backend")
        return _create_json_backend(data_path)


def _create_neo4j_backend(data_path: str) -> GraphBackend:
    """创建 Neo4j 后端"""
    try:
        # Neo4j 后端暂未实现，回退到 Kuzu 或 JSON
        _safe_print("[Recall] [WARN] Neo4j backend not yet implemented")
        _safe_print("[Recall] [HINT] Falling back to kuzu or json backend")
        
        try:
            return _create_kuzu_backend(data_path)
        except ImportError:
            return _create_json_backend(data_path)
    except Exception as e:
        _safe_print(f"[Recall] [FAIL] Failed to create Neo4j backend: {e}")
        return _create_json_backend(data_path)


def get_available_backends() -> list:
    """获取当前可用的后端列表"""
    backends = ["legacy", "json"]  # 这两个始终可用
    
    try:
        import kuzu
        backends.append("kuzu")
    except ImportError:
        pass
    
    try:
        import neo4j
        backends.append("neo4j")
    except ImportError:
        pass
    
    return backends
