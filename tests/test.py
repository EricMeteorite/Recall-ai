#!/usr/bin/env python3
"""
Recall-ai 测试入口

用法:
    python tests/test.py           # 运行快速测试
    python tests/test.py --full    # 运行完整测试
    python tests/test.py --stress  # 运行压力测试
    python tests/test.py --api     # 测试 API 服务
"""

import os
import sys
import time
import argparse
import tempfile

# 确保可以导入 recall
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 默认使用轻量模式
os.environ.setdefault('RECALL_EMBEDDING_MODE', 'none')


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def ok(msg):
    print(f"  {Colors.GREEN}[OK]{Colors.END} {msg}")


def fail(msg):
    print(f"  {Colors.RED}[FAIL]{Colors.END} {msg}")


def warn(msg):
    print(f"  {Colors.YELLOW}[WARN]{Colors.END} {msg}")


def header(title):
    print()
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")
    print(f" {title}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")


def run_quick_test():
    """快速测试 - 验证核心功能"""
    header("快速测试")
    errors = []
    
    # 1. 导入测试
    print("\n[1/5] 模块导入...")
    try:
        from recall.engine import RecallEngine
        from recall.server import app
        from recall.embedding import EmbeddingConfig
        ok("核心模块导入成功")
    except Exception as e:
        fail(f"导入失败: {e}")
        errors.append(str(e))
        return errors
    
    # 2. 引擎初始化
    print("\n[2/5] 引擎初始化...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = RecallEngine(data_root=tmpdir, lite=True)  # 也可以用 lightweight=True
            ok("引擎初始化成功")
            
            # 3. CRUD 测试
            print("\n[3/5] CRUD 操作...")
            
            # Add
            result = engine.add("Alice喜欢喝咖啡", user_id="test")
            assert result.success, f"add failed: {result.message}"
            memory_id = result.id
            ok(f"add() -> {memory_id[:20]}...")
            
            # Get
            mem = engine.get(memory_id, user_id="test")
            assert mem is not None, "get returned None"
            ok("get() 成功")
            
            # Search
            results = engine.search("咖啡", user_id="test")
            assert len(results) >= 1, "search returned no results"
            ok(f"search() -> {len(results)} 条结果")
            
            # Update
            engine.update(memory_id, "Alice喜欢喝茶", user_id="test")
            mem2 = engine.get(memory_id, user_id="test")
            assert "茶" in mem2.get("content", ""), "update failed"
            ok("update() 成功")
            
            # Delete
            deleted = engine.delete(memory_id, user_id="test")
            assert deleted, "delete returned False"
            ok("delete() 成功")
            
            # 4. 高级功能
            print("\n[4/5] 高级功能...")
            
            # 伏笔
            fsh = engine.plant_foreshadowing("神秘的盒子", user_id="test", related_entities=["Alice"])
            assert fsh.id, "foreshadowing failed"
            ok("伏笔功能正常")
            
            # 上下文
            engine.add("Bob住在上海", user_id="test")
            ctx = engine.build_context("谁住在哪里", user_id="test")
            assert len(ctx) > 0, "context empty"
            ok("上下文构建正常")
            
            # 统计
            stats = engine.stats()
            assert stats["version"], "stats failed"
            ok(f"统计信息: v{stats['version']}")
            
            # 5. 边界条件
            print("\n[5/5] 边界条件...")
            
            # 不存在的 ID
            none_result = engine.get("nonexistent", user_id="test")
            assert none_result is None, "should return None"
            ok("get(不存在) -> None")
            
            # 空字符串
            empty_result = engine.add("", user_id="test")
            ok(f"add('') -> success={empty_result.success}")
            
    except Exception as e:
        fail(f"测试失败: {e}")
        errors.append(str(e))
        import traceback
        traceback.print_exc()
    
    return errors


def run_full_test():
    """完整测试 - 运行 test_comprehensive.py"""
    header("完整测试")
    
    test_file = os.path.join(os.path.dirname(__file__), "test_comprehensive.py")
    if os.path.exists(test_file):
        print(f"运行 {test_file}...\n")
        os.system(f'python "{test_file}"')
    else:
        fail("test_comprehensive.py 不存在")


def run_stress_test():
    """压力测试"""
    header("压力测试")
    
    test_file = os.path.join(os.path.dirname(__file__), "test_stress.py")
    if os.path.exists(test_file):
        print(f"运行 {test_file}...\n")
        os.system(f'python "{test_file}"')
    else:
        fail("test_stress.py 不存在")


def run_api_test():
    """测试 API 服务（需要服务正在运行）"""
    header("API 测试")
    
    try:
        import requests
    except ImportError:
        fail("需要安装 requests: pip install requests")
        return
    
    base_url = os.environ.get("RECALL_API_URL", "http://localhost:18888")
    errors = []
    
    print(f"\n目标: {base_url}")
    
    # 1. Health check
    print("\n[1/5] 健康检查...")
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        if resp.status_code == 200:
            ok(f"GET /health -> {resp.json()}")
        else:
            fail(f"状态码: {resp.status_code}")
            errors.append("health check failed")
    except requests.exceptions.ConnectionError:
        fail(f"无法连接到 {base_url}")
        print(f"\n  {Colors.YELLOW}提示: 请先启动服务{Colors.END}")
        print(f"    Windows: .\\start.ps1")
        print(f"    Linux:   ./start.sh")
        return errors
    except Exception as e:
        fail(str(e))
        errors.append(str(e))
        return errors
    
    # 2. Add memory
    print("\n[2/5] 添加记忆...")
    try:
        resp = requests.post(
            f"{base_url}/v1/memories",
            json={"content": "API测试记忆", "user_id": "api_test"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            memory_id = data.get("id") or data.get("memory_id")
            ok(f"POST /v1/memories -> {memory_id}")
        else:
            fail(f"状态码: {resp.status_code}")
            errors.append("add failed")
            memory_id = None
    except Exception as e:
        fail(str(e))
        errors.append(str(e))
        memory_id = None
    
    # 3. Search
    print("\n[3/5] 搜索...")
    try:
        resp = requests.post(
            f"{base_url}/v1/memories/search",
            json={"query": "API测试", "user_id": "api_test"},
            timeout=10
        )
        if resp.status_code == 200:
            results = resp.json()
            count = len(results) if isinstance(results, list) else results.get("count", 0)
            ok(f"POST /v1/memories/search -> {count} 条结果")
        else:
            fail(f"状态码: {resp.status_code}")
            errors.append("search failed")
    except Exception as e:
        fail(str(e))
        errors.append(str(e))
    
    # 4. Get memory
    if memory_id:
        print("\n[4/5] 获取记忆...")
        try:
            resp = requests.get(
                f"{base_url}/v1/memories/{memory_id}",
                params={"user_id": "api_test"},
                timeout=5
            )
            if resp.status_code == 200:
                ok(f"GET /v1/memories/{memory_id[:15]}...")
            else:
                fail(f"状态码: {resp.status_code}")
                errors.append("get failed")
        except Exception as e:
            fail(str(e))
            errors.append(str(e))
    
    # 5. Stats
    print("\n[5/5] 统计信息...")
    try:
        resp = requests.get(f"{base_url}/v1/stats", timeout=5)
        if resp.status_code == 200:
            stats = resp.json()
            ok(f"GET /v1/stats -> v{stats.get('version', '?')}")
        else:
            fail(f"状态码: {resp.status_code}")
            errors.append("stats failed")
    except Exception as e:
        fail(str(e))
        errors.append(str(e))
    
    # 清理
    if memory_id:
        try:
            requests.delete(
                f"{base_url}/v1/memories/{memory_id}",
                params={"user_id": "api_test"},
                timeout=5
            )
        except Exception:
            pass
    
    return errors


def main():
    parser = argparse.ArgumentParser(description="Recall-ai 测试工具")
    parser.add_argument("--full", action="store_true", help="运行完整测试")
    parser.add_argument("--stress", action="store_true", help="运行压力测试")
    parser.add_argument("--api", action="store_true", help="测试 API 服务")
    parser.add_argument("--all", action="store_true", help="运行所有测试")
    
    args = parser.parse_args()
    
    print(f"""
{Colors.BLUE}╔══════════════════════════════════════════════╗
║          Recall-ai 测试工具 v4.1.0           ║
╚══════════════════════════════════════════════╝{Colors.END}
""")
    
    start_time = time.time()
    all_errors = []
    
    if args.all:
        # 运行所有测试
        all_errors.extend(run_quick_test())
        run_full_test()
        run_api_test()
    elif args.full:
        run_full_test()
    elif args.stress:
        run_stress_test()
    elif args.api:
        all_errors.extend(run_api_test() or [])
    else:
        # 默认运行快速测试
        all_errors.extend(run_quick_test())
    
    # 结果汇总
    elapsed = time.time() - start_time
    header("测试完成")
    print(f"\n  耗时: {elapsed:.2f}s")
    
    if all_errors:
        print(f"  {Colors.RED}错误: {len(all_errors)}{Colors.END}")
        for e in all_errors:
            print(f"    - {e}")
        sys.exit(1)
    else:
        print(f"  {Colors.GREEN}✅ 所有测试通过！{Colors.END}")
        sys.exit(0)


if __name__ == "__main__":
    main()
