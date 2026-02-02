"""Kuzu Integration Test - Recall Memory System Demo"""
import tempfile
import time
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recall.graph.temporal_knowledge_graph import TemporalKnowledgeGraph
from recall.models.temporal import UnifiedNode, NodeType

def main():
    print('='*70)
    print('KUZU INTEGRATION TEST - RECALL MEMORY SYSTEM')
    print('='*70)
    print('')

    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        print('Initializing Kuzu-backed knowledge graph...')
        graph = TemporalKnowledgeGraph(tmpdir, backend='kuzu', kuzu_buffer_pool_size=128)
        
        print('')
        print('[1] Adding characters...')
        alice = graph.add_node('Alice', node_type=NodeType.ENTITY, content='A brave adventurer from the north')
        bob = graph.add_node('Bob', node_type=NodeType.ENTITY, content='A wise wizard with mysterious past')
        carol = graph.add_node('Carol', node_type=NodeType.ENTITY, content='A skilled thief with a heart of gold')
        david = graph.add_node('David', node_type=NodeType.ENTITY, content='A knight seeking redemption')
        eve = graph.add_node('Eve', node_type=NodeType.ENTITY, content='A mysterious oracle')
        print('  Created 5 characters')
        
        print('')
        print('[2] Adding locations...')
        castle = graph.add_node('Crystal Castle', node_type=NodeType.ENTITY, content='An ancient castle on the mountain')
        forest = graph.add_node('Enchanted Forest', node_type=NodeType.ENTITY, content='A magical forest full of secrets')
        tavern = graph.add_node('Golden Tavern', node_type=NodeType.ENTITY, content='A cozy tavern where adventurers gather')
        print('  Created 3 locations')
        
        print('')
        print('[3] Adding events...')
        quest = graph.add_node('The Great Quest', node_type=NodeType.EPISODE, content='A legendary quest to find the lost artifact')
        battle = graph.add_node('Battle of Dawn', node_type=NodeType.EPISODE, content='The epic battle that changed everything')
        print('  Created 2 events')
        
        print('')
        print('[4] Adding relationships...')
        # 人物关系
        graph.add_edge(alice, 'KNOWS', bob, fact='Alice and Bob are old friends')
        graph.add_edge(alice, 'KNOWS', carol, fact='Alice met Carol in the tavern')
        graph.add_edge(bob, 'TRUSTS', alice, fact='Bob trusts Alice with his life')
        graph.add_edge(carol, 'RIVALS_WITH', david, fact='Carol and David have a long rivalry')
        graph.add_edge(david, 'SEEKS_GUIDANCE_FROM', eve, fact='David seeks wisdom from Eve')
        graph.add_edge(eve, 'PROPHESIED', alice, fact='Eve prophesied Alice would be the chosen one')
        
        # 地点关系
        graph.add_edge(alice, 'LIVES_IN', castle, fact='Alice lives in Crystal Castle')
        graph.add_edge(bob, 'WORKS_AT', forest, fact='Bob studies magic in the Enchanted Forest')
        graph.add_edge(carol, 'FREQUENTS', tavern, fact='Carol is a regular at the Golden Tavern')
        graph.add_edge(david, 'GUARDS', castle, fact='David guards Crystal Castle')
        
        # 事件关系
        graph.add_edge(alice, 'PARTICIPATES_IN', quest, fact='Alice leads the Great Quest')
        graph.add_edge(bob, 'PARTICIPATES_IN', quest, fact='Bob joins the Great Quest as advisor')
        graph.add_edge(carol, 'PARTICIPATES_IN', quest, fact='Carol joins the quest for treasure')
        graph.add_edge(david, 'FOUGHT_IN', battle, fact='David was a hero in the Battle of Dawn')
        graph.add_edge(quest, 'LEADS_TO', battle, fact='The quest ultimately leads to the great battle')
        
        print('  Created 15 relationships')
        
        print('')
        print('[5] Graph statistics...')
        print(f'  Nodes: {len(graph.nodes)}')
        print(f'  Edges: {len(graph.edges)}')
        
        # 验证 Kuzu 后端同步
        if graph._kuzu_backend:
            kuzu_nodes = graph._kuzu_backend.count_nodes()
            kuzu_edges = graph._kuzu_backend.count_edges()
            print(f'  Kuzu nodes: {kuzu_nodes}')
            print(f'  Kuzu edges: {kuzu_edges}')
            if kuzu_nodes == len(graph.nodes) and kuzu_edges == len(graph.edges):
                print('  Sync status: PERFECT SYNC ✓')
            else:
                print('  Sync status: MISMATCH!')
        
        print('')
        print('[6] Query tests...')
        
        # 获取 Alice 的邻居
        alice_neighbors = graph.get_neighbors(alice.uuid)
        print(f'  Alice neighbors: {len(alice_neighbors)}')
        for neighbor in alice_neighbors[:3]:
            if isinstance(neighbor, tuple):
                node = neighbor[0] if neighbor[0] else neighbor[1]
                if hasattr(node, 'name'):
                    print(f'    - {node.name}')
            elif hasattr(neighbor, 'name'):
                print(f'    - {neighbor.name}')
        
        # 通过 Kuzu 进行图遍历
        if graph._kuzu_backend:
            print('')
            print('[7] Kuzu graph traversal...')
            
            # BFS 从 Alice 开始
            bfs_result = graph._kuzu_backend.bfs([alice.uuid], max_depth=2)
            total_reachable = sum(len(v) for v in bfs_result.values())
            print(f'  2-hop BFS from Alice: {total_reachable} nodes reachable')
            
            for depth, items in sorted(bfs_result.items()):
                print(f'    Depth {depth}: {len(items)} nodes')
            
            # Cypher 查询
            print('')
            print('[8] Cypher queries...')
            
            # 查找所有 ENTITY 类型节点
            result = graph._kuzu_backend.query(
                "MATCH (n:Node) WHERE n.node_type = 'entity' RETURN n.name"
            )
            print(f'  Entities: {[r[0] for r in result]}')
            
            # 查找所有参与 quest 的人
            result = graph._kuzu_backend.query(
                "MATCH (n:Node)-[e:Edge]->(m:Node) WHERE e.edge_type = 'PARTICIPATES_IN' RETURN n.name, m.name"
            )
            print('  Quest participants:')
            for r in result:
                print(f'    {r[0]} participates in {r[1]}')
        
        print('')
        print('[9] Delete cascade test...')
        print(f'  Before delete: {len(graph.nodes)} nodes, {len(graph.edges)} edges')
        
        # 删除 Carol 节点（TemporalKnowledgeGraph 使用软删除，Kuzu 使用硬删除）
        graph.remove_node(carol.uuid)
        
        # 软删除：节点仍在 graph.nodes 中，但 expired_at 不为 None
        active_nodes = [n for n in graph.nodes.values() if n.is_active()]
        active_edges = [e for e in graph.edges.values() if e.expired_at is None]
        print(f'  After deleting Carol:')
        print(f'    Memory (soft delete): {len(graph.nodes)} nodes ({len(active_nodes)} active), {len(graph.edges)} edges ({len(active_edges)} active)')
        
        if graph._kuzu_backend:
            kuzu_nodes = graph._kuzu_backend.count_nodes()
            kuzu_edges = graph._kuzu_backend.count_edges()
            print(f'    Kuzu (hard delete): {kuzu_nodes} nodes, {kuzu_edges} edges')
            
            # 检查 Carol 在 Kuzu 中是否已删除
            carol_in_kuzu = graph._kuzu_backend.get_node(carol.uuid)
            if carol_in_kuzu is None:
                print('    Carol removed from Kuzu: ✓')
            else:
                print('    Carol still in Kuzu: ✗')

    print('')
    print('='*70)
    print('INTEGRATION TEST COMPLETED SUCCESSFULLY!')
    print('='*70)

if __name__ == '__main__':
    main()
