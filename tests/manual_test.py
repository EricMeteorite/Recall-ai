"""
Recall v5.0 人工交互测试脚本
=============================
用法：
  1. 先启动 Recall 服务器（general 模式）
  2. 运行本脚本：python tools/manual_test.py

会依次测试：
  - 模式确认
  - 单条添加（带元数据）
  - 批量添加（模拟多平台爬虫数据）
  - 按来源过滤搜索
  - 按标签过滤搜索
  - 全文搜索
  - 删除
  - 统计信息
"""

import requests
import json
import time
import sys

BASE = "http://127.0.0.1:18888"
USER_ID = "test_user"
CHAR_ID = "default"

# ─── 颜色输出 ───────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def fail(msg):
    print(f"  {RED}✗{RESET} {msg}")

def info(msg):
    print(f"  {CYAN}ℹ{RESET} {msg}")

def header(title):
    print(f"\n{BOLD}{YELLOW}{'='*60}{RESET}")
    print(f"{BOLD}{YELLOW}  {title}{RESET}")
    print(f"{BOLD}{YELLOW}{'='*60}{RESET}")

def section(title):
    print(f"\n{BOLD}── {title} ──{RESET}")


# ─── 工具函数 ───────────────────────────────────
def api(method, path, **kwargs):
    """调用 API 并返回 JSON"""
    url = f"{BASE}{path}"
    try:
        resp = getattr(requests, method)(url, timeout=30, **kwargs)
        return resp.status_code, resp.json() if resp.text else {}
    except requests.ConnectionError:
        print(f"\n{RED}错误: 无法连接到 {BASE}")
        print(f"请先启动服务器（设置 RECALL_MODE=general）：")
        print(f"  $env:RECALL_MODE='general'; python -m recall serve{RESET}")
        sys.exit(1)
    except Exception as e:
        return 500, {"error": str(e)}


def main():
    added_ids = []

    # ═══════════════════════════════════════════════
    header("Recall v5.0 交互测试")
    # ═══════════════════════════════════════════════

    # ── 0. 连接检查 ──
    section("0. 连接 & 模式检查")
    code, data = api("get", "/v1/mode")
    if code == 200:
        ok(f"服务器已连接")
        info(f"当前模式: {data.get('mode', '?')}")
        info(f"特性: {json.dumps(data.get('features', {}), ensure_ascii=False, indent=2)}")
    else:
        fail(f"GET /v1/mode 失败: {code}")

    # ── 1. 单条添加（带元数据）──
    section("1. 单条添加 —— 模拟 B站热点")
    code, data = api("post", "/v1/memories", json={
        "content": "DeepSeek R1 模型在 AI 圈引起巨大关注，B站科技区多个视频播放破百万，成为2025年开年最热的AI话题。",
        "user_id": USER_ID,
        "character_id": CHAR_ID,
        "source": "bilibili",
        "tags": ["AI", "DeepSeek", "热点"],
        "category": "tech",
        "content_type": "video_transcript",
        "metadata": {
            "platform_url": "https://bilibili.com/video/BV1xxx",
            "author": "科技分享官",
            "views": 1500000,
            "crawl_time": "2025-02-16T10:00:00Z"
        }
    })
    if code == 200:
        mid = data.get("memory_id") or data.get("id") or data.get("data", {}).get("memory_id")
        ok(f"添加成功, memory_id={mid}")
        if mid:
            added_ids.append(mid)
        info(f"响应: {json.dumps(data, ensure_ascii=False)[:200]}")
    else:
        fail(f"POST /v1/memories 失败: {code} - {data}")

    # ── 2. 批量添加（多平台模拟）──
    section("2. 批量添加 —— 模拟多平台爬虫数据（6条）")
    batch_items = [
        {
            "content": "OpenAI 宣布 GPT-5 将在2025年Q2发布，支持多模态实时推理，推理速度提升10倍。",
            "user_id": USER_ID,
            "character_id": CHAR_ID,
            "source": "twitter",
            "tags": ["AI", "OpenAI", "GPT-5"],
            "category": "tech",
            "content_type": "text"
        },
        {
            "content": "小红书上一位博主分享了用 DeepSeek 编程助手写了一个完整的电商网站，全程仅用了3小时。",
            "user_id": USER_ID,
            "character_id": CHAR_ID,
            "source": "xiaohongshu",
            "tags": ["AI", "DeepSeek", "编程"],
            "category": "tech",
            "content_type": "text"
        },
        {
            "content": "抖音热门：AI生成的短视频正在取代真人出镜，多个MCN机构已全面转向AI内容创作。",
            "user_id": USER_ID,
            "character_id": CHAR_ID,
            "source": "douyin",
            "tags": ["AI", "短视频", "内容创作"],
            "category": "entertainment",
            "content_type": "video_transcript"
        },
        {
            "content": "GitHub Trending: 一个名为 bolt.new 的开源项目在24小时内获得5000星，号称替代所有低代码平台。",
            "user_id": USER_ID,
            "character_id": CHAR_ID,
            "source": "github",
            "tags": ["开源", "低代码", "热门项目"],
            "category": "tech",
            "content_type": "text"
        },
        {
            "content": "HackerNews 头条：Rust 语言在2024年 Stack Overflow 调查中连续第9年成为最受喜爱的编程语言。",
            "user_id": USER_ID,
            "character_id": CHAR_ID,
            "source": "hackernews",
            "tags": ["Rust", "编程语言", "调查"],
            "category": "tech",
            "content_type": "text"
        },
        {
            "content": "DeepSeek 团队宣布开源 R1 模型的全部权重和训练代码，GitHub仓库12小时突破2万星。",
            "user_id": USER_ID,
            "character_id": CHAR_ID,
            "source": "github",
            "tags": ["AI", "DeepSeek", "开源"],
            "category": "tech",
            "content_type": "text"
        }
    ]

    code, data = api("post", "/v1/memories/batch", json={
        "memories": batch_items
    })
    if code == 200:
        results = data.get("results") or data.get("data", {}).get("results", [])
        ok(f"批量添加成功, 共 {len(results)} 条")
        for r in results:
            rid = r.get("memory_id") or r.get("id", "?")
            added_ids.append(rid)
            info(f"  → {rid}")
    else:
        fail(f"POST /v1/memories/batch 失败: {code} - {json.dumps(data, ensure_ascii=False)[:300]}")

    # 等索引更新
    time.sleep(1)

    # ── 3. 普通搜索 ──
    section("3. 按关键词搜索 'DeepSeek'")
    code, data = api("post", "/v1/memories/search", json={
        "query": "DeepSeek 最新进展",
        "user_id": USER_ID,
        "character_id": CHAR_ID,
        "top_k": 10
    })
    if code == 200:
        results = data.get("results") or data.get("data", {}).get("results", [])
        ok(f"搜索返回 {len(results)} 条结果")
        for i, r in enumerate(results):
            score = r.get("score", 0)
            content = r.get("content", "")[:80]
            source = r.get("metadata", {}).get("source", "?")
            info(f"  [{i+1}] score={score:.3f} source={source} | {content}...")
    else:
        fail(f"搜索失败: {code}")

    # ── 4. 按来源过滤搜索 ──
    section("4. 按来源过滤 —— 只看 GitHub")
    code, data = api("post", "/v1/memories/search", json={
        "query": "开源项目",
        "user_id": USER_ID,
        "character_id": CHAR_ID,
        "source": "github",
        "top_k": 10
    })
    if code == 200:
        results = data.get("results") or data.get("data", {}).get("results", [])
        ok(f"搜索返回 {len(results)} 条结果")
        all_github = True
        for i, r in enumerate(results):
            source = r.get("metadata", {}).get("source", "?")
            content = r.get("content", "")[:80]
            if source != "github":
                all_github = False
            info(f"  [{i+1}] source={source} | {content}...")
        if all_github and results:
            ok("全部来自 GitHub ✓")
        elif not results:
            info("无结果（可能索引未就绪）")
        else:
            fail("包含非 GitHub 来源 ✗")
    else:
        fail(f"搜索失败: {code}")

    # ── 5. 按标签过滤搜索 ──
    section("5. 按标签过滤 —— tags=['AI']")
    code, data = api("post", "/v1/memories/search", json={
        "query": "人工智能最新动态",
        "user_id": USER_ID,
        "character_id": CHAR_ID,
        "tags": ["AI"],
        "top_k": 10
    })
    if code == 200:
        results = data.get("results") or data.get("data", {}).get("results", [])
        ok(f"搜索返回 {len(results)} 条结果")
        for i, r in enumerate(results):
            tags = r.get("metadata", {}).get("tags", [])
            content = r.get("content", "")[:80]
            info(f"  [{i+1}] tags={tags} | {content}...")
    else:
        fail(f"搜索失败: {code}")

    # ── 6. 按 category 过滤 ──
    section("6. 按分类过滤 —— category='entertainment'")
    code, data = api("post", "/v1/memories/search", json={
        "query": "短视频内容",
        "user_id": USER_ID,
        "character_id": CHAR_ID,
        "category": "entertainment",
        "top_k": 10
    })
    if code == 200:
        results = data.get("results") or data.get("data", {}).get("results", [])
        ok(f"搜索返回 {len(results)} 条结果")
        for i, r in enumerate(results):
            cat = r.get("metadata", {}).get("category", "?")
            info(f"  [{i+1}] category={cat} | {r.get('content', '')[:80]}...")
    else:
        fail(f"搜索失败: {code}")

    # ── 7. 获取记忆列表 ──
    section("7. 获取记忆列表")
    code, data = api("get", f"/v1/memories?user_id={USER_ID}&character_id={CHAR_ID}&limit=20")
    if code == 200:
        memories = data.get("memories") or data.get("data", {}).get("memories", [])
        total = data.get("total", len(memories))
        ok(f"共 {total} 条记忆")
        for m in memories[:5]:
            mid = m.get("id") or m.get("memory_id", "?")
            content = m.get("content", "")[:60]
            source = m.get("metadata", {}).get("source", "?")
            info(f"  {mid[:12]}... source={source} | {content}...")
        if total > 5:
            info(f"  ... 还有 {total - 5} 条")
    else:
        fail(f"获取列表失败: {code}")

    # ── 8. 统计信息 ──
    section("8. 系统统计")
    code, data = api("get", "/v1/stats")
    if code == 200:
        ok(f"统计获取成功")
        info(f"  {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
    else:
        fail(f"获取统计失败: {code}")

    # ── 9. 删除一条记忆 ──
    if added_ids:
        section("9. 删除一条记忆")
        del_id = added_ids[0]
        code, data = api("delete", f"/v1/memories/{del_id}?user_id={USER_ID}&character_id={CHAR_ID}")
        if code == 200:
            ok(f"删除成功: {del_id}")
        else:
            fail(f"删除失败: {code} - {data}")

    # ── 10. 清空测试数据 ──
    section("10. 是否清空测试数据？")
    choice = input(f"  输入 y 清空 user={USER_ID} 的所有数据，其他键跳过: ").strip().lower()
    if choice == "y":
        code, data = api("delete", f"/v1/memories/clear?user_id={USER_ID}&character_id={CHAR_ID}")
        if code == 200:
            ok("已清空测试数据")
        else:
            # 尝试另一种清除方式
            code, data = api("post", f"/v1/memories/clear", json={
                "user_id": USER_ID,
                "character_id": CHAR_ID
            })
            if code == 200:
                ok("已清空测试数据")
            else:
                fail(f"清空失败: {code} - {data}")
    else:
        info("跳过清空，测试数据保留")

    # ── 总结 ──
    header("测试完成")
    print(f"  共添加 {len(added_ids)} 条记忆")
    print(f"  可以继续用以下方式交互：")
    print(f"  - 浏览器打开 {BOLD}http://127.0.0.1:18888/docs{RESET} (Swagger UI)")
    print(f"  - curl / httpie / Postman 调用 API")
    print(f"  - 运行 {BOLD}python tools/chat_with_recall.py{RESET} 进行对话式测试")
    print()


if __name__ == "__main__":
    main()
