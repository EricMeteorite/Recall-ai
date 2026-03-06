"""
Recall v7.7 - Knowledge Graph Visualizer

Simple HTML-based knowledge graph visualization using vis.js (CDN, no build step).
Provides an interactive UI to explore entities and relations.

Endpoint: GET /v1/admin/graph/visualize
"""

from __future__ import annotations

import os
import json
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---- Safe print for Windows GBK ----
def _safe_print(msg: str) -> None:
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


# ==================== Graph Data Extraction ====================

def extract_graph_data(
    engine: Any,
    user_id: str = "default",
    namespace: Optional[str] = None,
    entity_type: Optional[str] = None,
    max_nodes: int = 200,
    max_edges: int = 500,
) -> Dict[str, Any]:
    """Extract nodes and edges from the engine's temporal_graph.

    Returns a dict with 'nodes' and 'edges' lists ready for vis.js.
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen_nodes: set = set()

    graph = getattr(engine, 'temporal_graph', None) or getattr(engine, 'knowledge_graph', None)
    if graph is None:
        return {"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0}}

    # Collect nodes from the graph
    try:
        all_nodes = getattr(graph, 'nodes', {})
        node_count = 0
        for nid, node in all_nodes.items():
            if node_count >= max_nodes:
                break

            node_name = getattr(node, 'name', str(nid))
            node_type_val = getattr(node, 'node_type', None)
            node_type_str = node_type_val.value if hasattr(node_type_val, 'value') else str(node_type_val or 'unknown')

            # Apply filters
            if entity_type and node_type_str.lower() != entity_type.lower():
                continue

            group_id = getattr(node, 'group_id', 'default')
            if namespace and group_id != namespace:
                continue

            # Color by type
            color_map = {
                'entity': '#4A90D9',
                'event': '#E8A838',
                'concept': '#7BC67E',
                'location': '#D96459',
                'person': '#9B59B6',
                'item': '#1ABC9C',
                'unknown': '#95A5A6',
            }
            color = color_map.get(node_type_str.lower(), '#95A5A6')

            node_data = {
                "id": nid,
                "label": node_name,
                "title": _build_node_tooltip(node),
                "group": node_type_str,
                "color": color,
                "shape": "dot",
                "size": 15,
            }
            nodes.append(node_data)
            seen_nodes.add(nid)
            node_count += 1
    except Exception as e:
        logger.warning(f"[GraphViz] 提取节点失败: {e}")

    # Collect edges
    try:
        all_edges = getattr(graph, 'edges', {})
        edge_count = 0
        for eid, edge in all_edges.items():
            if edge_count >= max_edges:
                break

            subject = getattr(edge, 'subject', '')
            object_ = getattr(edge, 'object', '')
            predicate = getattr(edge, 'predicate', '')
            confidence = getattr(edge, 'confidence', 0.5)

            # Try to find node UUIDs from names
            subject_id = _find_node_id(graph, subject, seen_nodes)
            object_id = _find_node_id(graph, object_, seen_nodes)

            if not subject_id or not object_id:
                continue

            edge_data = {
                "from": subject_id,
                "to": object_id,
                "label": predicate,
                "title": _build_edge_tooltip(edge),
                "arrows": "to",
                "width": max(1, int(confidence * 3)),
                "color": {"color": "#848484", "opacity": max(0.3, confidence)},
            }
            edges.append(edge_data)
            edge_count += 1
    except Exception as e:
        logger.warning(f"[GraphViz] 提取边失败: {e}")

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "max_nodes": max_nodes,
            "max_edges": max_edges,
            "truncated": len(nodes) >= max_nodes or len(edges) >= max_edges,
        },
    }


def _find_node_id(graph: Any, name: str, seen_nodes: set) -> Optional[str]:
    """Try to resolve a name to a node UUID that exists in our seen_nodes set."""
    # Direct lookup via get_node_by_name
    node = None
    try:
        node = graph.get_node_by_name(name)
    except Exception:
        pass
    if node and getattr(node, 'uuid', None) in seen_nodes:
        return node.uuid
    # Fallback: check if name itself is a UUID in seen_nodes
    if name in seen_nodes:
        return name
    return None


def _build_node_tooltip(node: Any) -> str:
    """Build HTML tooltip for a node."""
    parts = []
    name = getattr(node, 'name', '?')
    parts.append(f"<b>{name}</b>")
    ntype = getattr(node, 'node_type', None)
    if ntype:
        parts.append(f"Type: {ntype.value if hasattr(ntype, 'value') else ntype}")
    group = getattr(node, 'group_id', None)
    if group:
        parts.append(f"Namespace: {group}")
    created = getattr(node, 'created_at', None)
    if created:
        parts.append(f"Created: {created}")
    aliases = getattr(node, 'aliases', [])
    if aliases:
        parts.append(f"Aliases: {', '.join(aliases[:5])}")
    return "<br>".join(parts)


def _build_edge_tooltip(edge: Any) -> str:
    """Build HTML tooltip for an edge."""
    parts = []
    subject = getattr(edge, 'subject', '?')
    predicate = getattr(edge, 'predicate', '?')
    object_ = getattr(edge, 'object', '?')
    parts.append(f"<b>{subject} → {predicate} → {object_}</b>")
    fact = getattr(edge, 'fact', '')
    if fact:
        parts.append(f"Fact: {fact}")
    conf = getattr(edge, 'confidence', None)
    if conf is not None:
        parts.append(f"Confidence: {conf:.2f}")
    valid_from = getattr(edge, 'valid_from', None)
    valid_until = getattr(edge, 'valid_until', None)
    if valid_from:
        parts.append(f"Valid from: {valid_from}")
    if valid_until:
        parts.append(f"Valid until: {valid_until}")
    return "<br>".join(parts)


# ==================== HTML Generation ====================

def generate_graph_html(
    graph_data: Dict[str, Any],
    title: str = "Recall Knowledge Graph",
) -> str:
    """Generate a self-contained HTML page with vis.js for graph visualization.

    Uses vis-network CDN — no local build step required.
    """
    nodes_json = json.dumps(graph_data.get("nodes", []), ensure_ascii=False)
    edges_json = json.dumps(graph_data.get("edges", []), ensure_ascii=False)
    stats = graph_data.get("stats", {})

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; }}
        #header {{
            background: #16213e; padding: 12px 24px; display: flex; align-items: center; justify-content: space-between;
            border-bottom: 1px solid #0f3460;
        }}
        #header h1 {{ font-size: 18px; color: #e94560; }}
        #header .stats {{ font-size: 13px; color: #aaa; }}
        #controls {{
            background: #16213e; padding: 10px 24px; display: flex; gap: 16px; align-items: center;
            border-bottom: 1px solid #0f3460; flex-wrap: wrap;
        }}
        #controls label {{ font-size: 13px; color: #ccc; }}
        #controls input, #controls select, #controls button {{
            background: #0f3460; border: 1px solid #533483; color: #eee; padding: 5px 10px;
            border-radius: 4px; font-size: 13px;
        }}
        #controls button {{ cursor: pointer; background: #e94560; border: none; font-weight: 600; }}
        #controls button:hover {{ background: #c73650; }}
        #graph-container {{ width: 100%; height: calc(100vh - 100px); }}
        #info-panel {{
            position: fixed; right: 16px; top: 110px; width: 320px; max-height: 60vh;
            background: #16213e; border: 1px solid #0f3460; border-radius: 8px;
            padding: 16px; display: none; overflow-y: auto; z-index: 100;
        }}
        #info-panel h3 {{ color: #e94560; margin-bottom: 8px; }}
        #info-panel .close {{ position: absolute; right: 12px; top: 10px; cursor: pointer; color: #888; font-size: 18px; }}
        #info-panel .field {{ margin: 4px 0; font-size: 13px; }}
        #info-panel .field b {{ color: #7BC67E; }}
        .legend {{
            position: fixed; left: 16px; bottom: 16px; background: #16213e;
            border: 1px solid #0f3460; border-radius: 8px; padding: 12px; z-index: 100;
        }}
        .legend h4 {{ font-size: 13px; margin-bottom: 8px; color: #aaa; }}
        .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 12px; margin: 3px 0; }}
        .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
    </style>
</head>
<body>
    <div id="header">
        <h1>Recall Knowledge Graph</h1>
        <div class="stats">
            Nodes: {stats.get('total_nodes', 0)} &nbsp;|&nbsp;
            Edges: {stats.get('total_edges', 0)}
            {'&nbsp;|&nbsp; <span style="color:#e94560">Truncated</span>' if stats.get('truncated') else ''}
        </div>
    </div>
    <div id="controls">
        <label>Search: <input type="text" id="search-input" placeholder="Entity name..."></label>
        <label>Type:
            <select id="type-filter">
                <option value="">All</option>
                <option value="entity">Entity</option>
                <option value="person">Person</option>
                <option value="location">Location</option>
                <option value="event">Event</option>
                <option value="concept">Concept</option>
                <option value="item">Item</option>
            </select>
        </label>
        <button id="btn-fit">Fit All</button>
        <button id="btn-physics">Toggle Physics</button>
        <button id="btn-reset">Reset</button>
    </div>
    <div id="graph-container"></div>

    <div id="info-panel">
        <span class="close" onclick="document.getElementById('info-panel').style.display='none'">&times;</span>
        <h3 id="info-title">Node Info</h3>
        <div id="info-body"></div>
    </div>

    <div class="legend">
        <h4>Legend</h4>
        <div class="legend-item"><div class="legend-dot" style="background:#4A90D9"></div> Entity</div>
        <div class="legend-item"><div class="legend-dot" style="background:#E8A838"></div> Event</div>
        <div class="legend-item"><div class="legend-dot" style="background:#7BC67E"></div> Concept</div>
        <div class="legend-item"><div class="legend-dot" style="background:#D96459"></div> Location</div>
        <div class="legend-item"><div class="legend-dot" style="background:#9B59B6"></div> Person</div>
        <div class="legend-item"><div class="legend-dot" style="background:#1ABC9C"></div> Item</div>
    </div>

    <script type="text/javascript">
        // --- Data ---
        var nodesData = {nodes_json};
        var edgesData = {edges_json};

        var nodesDS = new vis.DataSet(nodesData);
        var edgesDS = new vis.DataSet(edgesData);

        // --- Network ---
        var container = document.getElementById('graph-container');
        var data = {{ nodes: nodesDS, edges: edgesDS }};
        var options = {{
            nodes: {{
                font: {{ color: '#eee', size: 12 }},
                borderWidth: 2,
                shadow: true,
            }},
            edges: {{
                font: {{ color: '#888', size: 10, align: 'middle' }},
                smooth: {{ type: 'continuous' }},
                shadow: true,
            }},
            physics: {{
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {{
                    gravitationalConstant: -50,
                    centralGravity: 0.01,
                    springLength: 120,
                    springConstant: 0.08,
                    damping: 0.4,
                }},
                stabilization: {{ iterations: 150 }},
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 200,
                navigationButtons: true,
                keyboard: true,
            }},
        }};
        var network = new vis.Network(container, data, options);

        // --- Events ---
        network.on('click', function(params) {{
            if (params.nodes.length > 0) {{
                var nodeId = params.nodes[0];
                var node = nodesDS.get(nodeId);
                if (node) {{
                    var panel = document.getElementById('info-panel');
                    document.getElementById('info-title').textContent = node.label || nodeId;
                    document.getElementById('info-body').innerHTML = node.title || 'No details';
                    panel.style.display = 'block';
                }}
            }}
        }});

        // --- Controls ---
        document.getElementById('search-input').addEventListener('input', function(e) {{
            var q = e.target.value.toLowerCase();
            nodesDS.forEach(function(node) {{
                var match = !q || (node.label && node.label.toLowerCase().includes(q));
                nodesDS.update({{ id: node.id, hidden: !match, opacity: match ? 1 : 0.1 }});
            }});
        }});

        document.getElementById('type-filter').addEventListener('change', function(e) {{
            var t = e.target.value.toLowerCase();
            nodesDS.forEach(function(node) {{
                var match = !t || (node.group && node.group.toLowerCase() === t);
                nodesDS.update({{ id: node.id, hidden: !match }});
            }});
        }});

        var physicsOn = true;
        document.getElementById('btn-physics').addEventListener('click', function() {{
            physicsOn = !physicsOn;
            network.setOptions({{ physics: {{ enabled: physicsOn }} }});
            this.textContent = physicsOn ? 'Toggle Physics' : 'Physics OFF';
        }});

        document.getElementById('btn-fit').addEventListener('click', function() {{
            network.fit();
        }});

        document.getElementById('btn-reset').addEventListener('click', function() {{
            document.getElementById('search-input').value = '';
            document.getElementById('type-filter').value = '';
            nodesDS.forEach(function(node) {{
                nodesDS.update({{ id: node.id, hidden: false }});
            }});
            network.fit();
        }});
    </script>
</body>
</html>"""
    return html
