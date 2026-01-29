#!/usr/bin/env python3
"""
Recall-ai 持久化与压力测试

测试内容：
1. 大量数据写入（模拟数百/数千轮对话）
2. 数据持久化（重启后数据不丢失）
3. 搜索性能
4. 内存占用
"""

import os
import sys
import time
import random
import string
import psutil
from pathlib import Path

# 测试配置
TEST_DATA_DIR = Path("./recall_stress_test_data")
TOTAL_TURNS = 500  # 模拟500轮对话
MEMORIES_PER_TURN = 3  # 每轮添加3条记忆
TOTAL_MEMORIES = TOTAL_TURNS * MEMORIES_PER_TURN  # 总共1500条


def get_memory_usage():
    """获取当前内存使用(MB)"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def generate_test_content(turn: int, idx: int) -> str:
    """生成测试内容 - 确保唯一性避免语义去重
    
    重要：使用随机字符串确保每条记忆的 Jaccard 相似度低于去重阈值(0.85)
    """
    import hashlib
    
    names = ["Alice", "Bob", "Charlie", "David", "Eva", "Frank", "Grace", "Henry"]
    locations = ["北京", "上海", "纽约", "东京", "伦敦", "巴黎", "柏林", "悉尼"]
    actions = ["去了", "住在", "工作于", "旅行到", "搬到", "访问了"]
    topics = ["编程", "音乐", "电影", "美食", "运动", "读书", "旅行", "摄影"]
    verbs = ["学习", "研究", "探索", "发现", "创造", "设计", "开发", "构建"]
    adjectives = ["精彩的", "有趣的", "神奇的", "独特的", "创新的", "经典的", "现代的", "传统的"]
    
    # 使用 turn 和 idx 创建确定性索引
    name1 = names[(turn + idx) % len(names)]
    name2 = names[(turn * 3 + idx + 2) % len(names)]
    location = locations[(turn * 2 + idx) % len(locations)]
    action = actions[(turn + idx * 2) % len(actions)]
    topic = topics[(turn * idx + 1) % len(topics)]
    verb = verbs[(turn + idx) % len(verbs)]
    adj = adjectives[(turn * 2 + idx) % len(adjectives)]
    
    # 生成唯一哈希作为额外区分符
    unique_hash = hashlib.md5(f"stress_test_{turn}_{idx}".encode()).hexdigest()[:8]
    
    # 根据 idx 选择不同模板，使用更多差异化内容
    if idx == 0:
        return f"[U{unique_hash}] {name1}在{location}{action}，{verb}了{adj}{topic}项目，记录编号T{turn}"
    elif idx == 1:
        return f"[U{unique_hash}] {name1}热爱{topic}，在{location}与{name2}{verb}了一个{adj}作品，时间点{turn}"
    else:
        return f"[U{unique_hash}] {name1}和{name2}成为好友，他们在{location}共同{action}，一起{verb}{adj}{topic}，序号{turn}"


def test_write_performance():
    """测试写入性能"""
    print("=" * 60)
    print("阶段 1: 写入性能测试")
    print("=" * 60)
    print(f"目标: 写入 {TOTAL_MEMORIES} 条记忆 ({TOTAL_TURNS} 轮对话)")
    print()
    
    from recall.engine import RecallEngine
    
    # 清理旧数据
    if TEST_DATA_DIR.exists():
        import shutil
        shutil.rmtree(TEST_DATA_DIR)
    
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # 初始化引擎（使用持久化存储）
    print("初始化引擎...")
    start_mem = get_memory_usage()
    engine = RecallEngine(data_root=str(TEST_DATA_DIR), lite=True, auto_warmup=False)
    
    # 写入测试
    print(f"开始写入 (初始内存: {start_mem:.1f}MB)...")
    print()
    
    start_time = time.time()
    success_count = 0
    fail_count = 0
    
    for turn in range(1, TOTAL_TURNS + 1):
        for idx in range(MEMORIES_PER_TURN):
            content = generate_test_content(turn, idx)
            result = engine.add(content, metadata={"turn": turn, "idx": idx})
            if result.success:
                success_count += 1
            else:
                fail_count += 1
        
        # 每100轮打印进度
        if turn % 100 == 0:
            elapsed = time.time() - start_time
            current_mem = get_memory_usage()
            rate = success_count / elapsed
            print(f"  轮次 {turn}/{TOTAL_TURNS} | "
                  f"成功: {success_count} | "
                  f"速率: {rate:.1f}/s | "
                  f"内存: {current_mem:.1f}MB")
    
    end_time = time.time()
    end_mem = get_memory_usage()
    
    print()
    print(f"写入完成!")
    print(f"  - 成功: {success_count}")
    print(f"  - 失败: {fail_count}")
    print(f"  - 耗时: {end_time - start_time:.2f}s")
    print(f"  - 平均速率: {success_count / (end_time - start_time):.1f} 条/秒")
    print(f"  - 内存增长: {start_mem:.1f}MB -> {end_mem:.1f}MB (+{end_mem - start_mem:.1f}MB)")
    
    # 验证数量
    all_memories = engine.get_all()
    print(f"  - 实际存储: {len(all_memories)} 条")
    
    assert success_count == TOTAL_MEMORIES, f"写入失败: 期望 {TOTAL_MEMORIES}, 实际 {success_count}"
    assert len(all_memories) == TOTAL_MEMORIES, f"存储不一致: 期望 {TOTAL_MEMORIES}, 实际 {len(all_memories)}"


def test_persistence():
    """测试持久化（模拟重启）"""
    print()
    print("=" * 60)
    print("阶段 2: 持久化测试 (模拟重启)")
    print("=" * 60)
    print()
    
    from recall.engine import RecallEngine
    
    # 重新加载引擎（模拟程序重启）
    print("重新加载引擎（模拟重启）...")
    engine = RecallEngine(data_root=str(TEST_DATA_DIR), lite=True, auto_warmup=False)
    
    # 检查数据是否还在
    all_memories = engine.get_all()
    print(f"重启后记忆数量: {len(all_memories)}")
    
    if len(all_memories) == TOTAL_MEMORIES:
        print(f"✅ 持久化测试通过! 所有 {TOTAL_MEMORIES} 条记忆完好无损")
    else:
        print(f"❌ 持久化测试失败! 期望 {TOTAL_MEMORIES} 条，实际 {len(all_memories)} 条")
        print(f"   丢失了 {TOTAL_MEMORIES - len(all_memories)} 条记忆")
    
    assert len(all_memories) == TOTAL_MEMORIES, f"持久化失败: 丢失了 {TOTAL_MEMORIES - len(all_memories)} 条记忆"


def test_search_performance():
    """测试搜索性能"""
    print()
    print("=" * 60)
    print("阶段 3: 搜索性能测试")
    print("=" * 60)
    print()
    
    from recall.engine import RecallEngine
    
    engine = RecallEngine(data_root=str(TEST_DATA_DIR), lite=True, auto_warmup=False)
    
    queries = ["Alice", "北京", "朋友", "编程", "第100轮", "Turn 250"]
    
    print("搜索测试:")
    for query in queries:
        start = time.time()
        results = engine.search(query, top_k=10)
        elapsed = (time.time() - start) * 1000
        print(f"  '{query}' -> {len(results)} 结果, {elapsed:.1f}ms")
    
    # 测试 build_context
    print()
    print("上下文构建测试:")
    start = time.time()
    context = engine.build_context("告诉我关于Alice在北京的事情")
    elapsed = (time.time() - start) * 1000
    print(f"  构建上下文: {len(context)} 字符, {elapsed:.1f}ms")
    
    assert len(context) > 0, "上下文构建失败: 返回空内容"


def test_incremental_add():
    """测试增量添加（在已有大量数据基础上继续添加）"""
    print()
    print("=" * 60)
    print("阶段 4: 增量添加测试")
    print("=" * 60)
    print()
    
    from recall.engine import RecallEngine
    
    engine = RecallEngine(data_root=str(TEST_DATA_DIR), lite=True, auto_warmup=False)
    
    before_count = len(engine.get_all())
    print(f"当前记忆数: {before_count}")
    
    # 再添加100条
    print("添加100条新记忆...")
    import hashlib
    incremental_topics = ["量子计算", "人工智能", "区块链", "虚拟现实", "云原生", "边缘计算", "物联网", "大数据"]
    incremental_verbs = ["研发", "部署", "测试", "优化", "迭代", "重构", "监控", "分析"]
    for i in range(100):
        topic = incremental_topics[i % len(incremental_topics)]
        verb = incremental_verbs[(i * 3) % len(incremental_verbs)]
        unique_id = hashlib.md5(f"incremental_{i}_{time.time()}".encode()).hexdigest()[:10]
        engine.add(f"[INC{unique_id}] 增量记忆#{i}: 关于{topic}的{verb}工作，详细编号{i * 17 + 31}")
    
    after_count = len(engine.get_all())
    print(f"添加后记忆数: {after_count}")
    
    # 再次模拟重启
    print("再次重启验证...")
    engine2 = RecallEngine(data_root=str(TEST_DATA_DIR), lite=True, auto_warmup=False)
    final_count = len(engine2.get_all())
    print(f"重启后记忆数: {final_count}")
    
    expected = TOTAL_MEMORIES + 100
    if final_count == expected:
        print(f"✅ 增量添加测试通过! 总计 {final_count} 条")
    else:
        print(f"❌ 增量添加测试失败! 期望 {expected}, 实际 {final_count}")
    
    assert final_count == expected, f"增量添加失败: 期望 {expected}, 实际 {final_count}"


def cleanup():
    """Clean up test data"""
    print()
    print("=" * 60)
    print("Cleanup Test Data")
    print("=" * 60)
    
    if TEST_DATA_DIR.exists():
        import shutil
        shutil.rmtree(TEST_DATA_DIR)
        print(f"Deleted: {TEST_DATA_DIR}")
    else:
        print("Nothing to clean")


def main():
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║         Recall-ai 持久化与压力测试                         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"测试配置:")
    print(f"  - 模拟对话轮次: {TOTAL_TURNS}")
    print(f"  - 每轮记忆数: {MEMORIES_PER_TURN}")
    print(f"  - 总记忆数: {TOTAL_MEMORIES}")
    print(f"  - 数据目录: {TEST_DATA_DIR.absolute()}")
    print()
    
    results = []
    
    try:
        # 阶段1: 写入测试
        results.append(("写入性能", test_write_performance()))
        
        # 阶段2: 持久化测试
        results.append(("持久化", test_persistence()))
        
        # 阶段3: 搜索性能测试
        results.append(("搜索性能", test_search_performance()))
        
        # 阶段4: 增量添加测试
        results.append(("增量添加", test_incremental_add()))
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        results.append(("异常", False))
    
    # 汇总
    print()
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 All tests passed!")
    else:
        print("[WARN] Some tests failed, please check the output above")
    
    # 自动清理测试数据
    print()
    print("Auto cleanup test data...")
    cleanup()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
