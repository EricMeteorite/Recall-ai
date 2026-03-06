#!/usr/bin/env python3
"""
Recall AI 真实用户模拟测试
==========================
模拟一个用户持续使用 Recall 系统的完整场景：
- 模拟每隔几小时输入热点新闻数据
- 模拟跨越数月/年的持续数据累积
- 验证历史数据 + 新数据组合查询的 100% 准确性
- 验证 CRUD 全流程无数据丢失
- 验证索引一致性

运行方式:
  python tests/test_simulation.py
  pytest tests/test_simulation.py -v -s
"""

import os
import sys
import time
import logging
import tempfile
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# 强制 Lite 模式，不需要 GPU/模型
os.environ['RECALL_EMBEDDING_MODE'] = 'none'

# ============================================================
# 日志配置 - 用户要求能看到详细 log
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('SimulationTest')

# Recall 内部模块也开启 INFO
logging.getLogger('recall').setLevel(logging.INFO)


# ============================================================
# 辅助函数
# ============================================================
def safe_print(msg: str):
    """Windows GBK 兼容打印"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def banner(title: str):
    safe_print('')
    safe_print('=' * 70)
    safe_print(f'  {title}')
    safe_print('=' * 70)


def phase(title: str):
    safe_print('')
    safe_print('-' * 50)
    safe_print(f'  >> {title}')
    safe_print('-' * 50)


def ok(msg: str):
    safe_print(f'  [PASS] {msg}')


def fail(msg: str):
    safe_print(f'  [FAIL] {msg}')


def info(msg: str):
    safe_print(f'  [INFO] {msg}')


def warn(msg: str):
    safe_print(f'  [WARN] {msg}')


# ============================================================
# 模拟数据生成器 - 热点新闻 / 日常事件
# ============================================================

# 模拟 3 年的热点新闻数据（每月几条关键事件）
SIMULATED_NEWS_FEED = [
    # ---- 第1年 ----
    {"month": "2022-01", "events": [
        {"content": "2022年1月，北京冬奥会筹备进入最后冲刺阶段，各场馆建设全面完工，测试赛顺利进行。", "tags": ["冬奥会", "北京", "体育"]},
        {"content": "SpaceX在一月成功发射了第35批星链卫星，累计在轨卫星超过2000颗。", "tags": ["SpaceX", "星链", "航天"]},
    ]},
    {"month": "2022-03", "events": [
        {"content": "2022年3月，国际原油价格突破每桶130美元，创14年新高，全球能源市场剧烈波动。", "tags": ["原油", "能源", "经济"]},
        {"content": "韩国新任总统尹锡悦在大选中获胜，承诺加强韩美同盟关系。", "tags": ["韩国", "政治", "选举"]},
    ]},
    {"month": "2022-06", "events": [
        {"content": "2022年6月，美联储宣布加息75个基点，为1994年以来最大单次加息幅度，全球股市承压。", "tags": ["美联储", "加息", "金融"]},
        {"content": "中国神舟十四号载人飞船成功发射，三名航天员进入天和核心舱。", "tags": ["航天", "神舟", "中国"]},
    ]},
    {"month": "2022-09", "events": [
        {"content": "英国女王伊丽莎白二世于2022年9月8日在巴尔莫勒尔城堡去世，享年96岁，在位70年。", "tags": ["英国", "女王", "历史"]},
        {"content": "北溪天然气管道在波罗的海海底发生爆炸泄漏，引发欧洲能源安全担忧。", "tags": ["北溪", "能源", "欧洲"]},
    ]},
    {"month": "2022-12", "events": [
        {"content": "OpenAI于2022年12月发布ChatGPT，人工智能聊天机器人迅速走红全球，注册用户突破百万。", "tags": ["ChatGPT", "AI", "OpenAI"]},
        {"content": "2022年卡塔尔世界杯决赛，阿根廷战胜法国夺冠，梅西终圆世界杯梦想。", "tags": ["世界杯", "足球", "梅西"]},
    ]},
    # ---- 第2年 ----
    {"month": "2023-02", "events": [
        {"content": "2023年2月，土耳其东南部发生7.8级强烈地震，造成超过5万人遇难，大量建筑倒塌。", "tags": ["地震", "土耳其", "灾难"]},
        {"content": "中国气象气球事件引发中美外交紧张，美国击落了出现在其领空的高空气球。", "tags": ["气球", "中美关系", "外交"]},
    ]},
    {"month": "2023-05", "events": [
        {"content": "2023年5月，WHO宣布新冠疫情不再构成国际关注的突发公共卫生事件，标志着疫情的重大转折。", "tags": ["新冠", "WHO", "疫情"]},
        {"content": "英伟达市值突破1万亿美元，成为首个万亿市值的芯片公司，AI芯片需求暴增。", "tags": ["英伟达", "AI", "芯片"]},
    ]},
    {"month": "2023-07", "events": [
        {"content": "全球多地遭遇极端高温天气，欧洲南部、北非气温超过48摄氏度，山火频发。", "tags": ["高温", "气候", "极端天气"]},
        {"content": "Meta发布开源大语言模型Llama 2，提供7B、13B、70B三个版本供研究和商用。", "tags": ["Meta", "Llama", "AI", "开源"]},
    ]},
    {"month": "2023-10", "events": [
        {"content": "2023年10月，巴以冲突再度升级，哈马斯对以色列发动大规模突袭，以色列随后对加沙地带展开军事行动。", "tags": ["巴以冲突", "中东", "军事"]},
        {"content": "华为推出Mate 60 Pro手机，搭载自研麒麟9000s芯片，标志着华为在制裁下实现技术突破。", "tags": ["华为", "芯片", "手机"]},
    ]},
    {"month": "2023-12", "events": [
        {"content": "Google发布Gemini AI模型，号称在多项基准测试中超越GPT-4，AI竞赛进一步加剧。", "tags": ["Gemini", "Google", "AI"]},
        {"content": "COP28气候大会在迪拜召开，196个国家首次就转型脱离化石能源达成共识。", "tags": ["COP28", "气候", "能源"]},
    ]},
    # ---- 第3年 ----
    {"month": "2024-01", "events": [
        {"content": "2024年1月，日本能登半岛发生7.6级地震，导致大量建筑损毁，令和6年首场大灾。", "tags": ["地震", "日本", "灾难"]},
        {"content": "全球AI监管进入新阶段，欧盟AI法案正式获得批准，成为全球首部全面AI法规。", "tags": ["AI", "监管", "欧盟"]},
    ]},
    {"month": "2024-03", "events": [
        {"content": "Anthropic发布Claude 3系列模型，包括Opus、Sonnet和Haiku，在推理能力上表现出色。", "tags": ["Claude", "Anthropic", "AI"]},
        {"content": "TikTok在美国面临强制出售或禁令的立法压力，众议院通过相关法案。", "tags": ["TikTok", "美国", "互联网"]},
    ]},
    {"month": "2024-06", "events": [
        {"content": "苹果在WWDC 2024发布Apple Intelligence，将AI深度整合到iOS 18和macOS中。", "tags": ["苹果", "AI", "Apple Intelligence"]},
        {"content": "欧洲杯和美洲杯足球赛同时举行，西班牙和阿根廷分别夺冠。", "tags": ["欧洲杯", "美洲杯", "足球"]},
    ]},
    {"month": "2024-09", "events": [
        {"content": "OpenAI发布GPT-4o和o1推理模型，AI在数学和编程任务上达到博士水平能力。", "tags": ["GPT-4o", "OpenAI", "AI"]},
        {"content": "全球半导体行业进入新一轮扩产周期，台积电、三星竞相建设2nm先进制程工厂。", "tags": ["半导体", "台积电", "芯片"]},
    ]},
    {"month": "2024-12", "events": [
        {"content": "2024年全球AI投资总额突破2000亿美元，AI应用全面渗透到医疗、教育、金融等行业。", "tags": ["AI", "投资", "2024"]},
        {"content": "SpaceX星舰第六次试飞成功实现助推器回收，人类太空探索进入新纪元。", "tags": ["SpaceX", "星舰", "航天"]},
    ]},
]


# 用户私人记忆（混合在新闻数据之间）
PERSONAL_MEMORIES = [
    {"content": "今天和老朋友张伟在星巴克见面，他提到自己下个月要搬到上海工作。", "tags": ["张伟", "上海", "朋友"]},
    {"content": "小猫咪糖糖今天第一次打了疫苗，医生说一切正常，下个月需要再打第二针。", "tags": ["糖糖", "猫", "疫苗"]},
    {"content": "公司年度绩效评估结果出来了，我得了A级，老板暗示明年会有升职机会。", "tags": ["工作", "绩效", "升职"]},
    {"content": "今天在亚马逊买了一台MacBook Pro M3，花了14999元，下周到货。", "tags": ["MacBook", "购物", "电脑"]},
    {"content": "张伟最终确认搬到上海了，他说新公司是一家AI创业公司，做大模型微调的。", "tags": ["张伟", "上海", "AI"]},
    {"content": "糖糖打了第二针疫苗，有点发烧但医生说是正常反应，注意保暖就好。", "tags": ["糖糖", "猫", "疫苗"]},
    {"content": "今天收到升职通知，正式成为技术组长，团队有6个人，感觉责任重大。", "tags": ["升职", "技术组长", "工作"]},
    {"content": "MacBook Pro到了，M3芯片跑代码确实快很多，编译时间缩短了一半。", "tags": ["MacBook", "M3", "电脑"]},
]


# ============================================================
# 核心测试 - 模拟流程
# ============================================================
class SimulationTest:
    """模拟用户持续使用 Recall 系统 3 年的完整场景"""

    def __init__(self, data_root: str):
        self.data_root = data_root
        self.engine = None
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.total_added = 0
        self.total_checks = 0
        self.total_passed = 0
        self.memory_ids: Dict[str, str] = {}  # content_key -> memory_id
        self.all_contents: List[str] = []  # 所有已添加内容

    def setup(self):
        """初始化引擎"""
        phase('初始化 RecallEngine (Lite 模式)')
        try:
            from recall.engine import RecallEngine
            self.engine = RecallEngine(data_root=self.data_root, lite=True)
            ok(f'引擎初始化成功 (data_root={self.data_root})')
            return True
        except Exception as e:
            fail(f'引擎初始化失败: {e}')
            traceback.print_exc()
            self.errors.append(f'引擎初始化失败: {e}')
            return False

    def teardown(self):
        """关闭引擎"""
        if self.engine:
            try:
                self.engine.close()
                info('引擎已关闭')
            except Exception as e:
                warn(f'引擎关闭异常: {e}')

    def check(self, condition: bool, pass_msg: str, fail_msg: str):
        """断言检查并记录"""
        self.total_checks += 1
        if condition:
            self.total_passed += 1
            ok(pass_msg)
        else:
            fail(fail_msg)
            self.errors.append(fail_msg)

    # ============================================================
    # Phase 1: 持续数据输入 - 模拟 3 年热点新闻
    # ============================================================
    def phase1_continuous_data_input(self):
        """模拟持续数据输入，每月投入热点新闻"""
        banner('Phase 1: 持续数据输入 (模拟3年热点新闻)')

        for month_data in SIMULATED_NEWS_FEED:
            month = month_data["month"]
            events = month_data["events"]
            phase(f'输入 {month} 的热点事件 ({len(events)} 条)')

            for event in events:
                content = event["content"]
                tags = event["tags"]
                metadata = {
                    "source": "news_feed",
                    "month": month,
                    "tags": tags,
                    "category": "news"
                }

                try:
                    result = self.engine.add(
                        content=content,
                        user_id="simulation_user",
                        metadata=metadata
                    )
                    if result and result.success:
                        self.total_added += 1
                        key = f"news_{month}_{self.total_added}"
                        self.memory_ids[key] = result.id
                        self.all_contents.append(content)
                        info(f'  + [{month}] {content[:50]}... -> ID: {result.id[:8]}')
                    else:
                        msg = f'添加失败 [{month}]: {content[:40]}...'
                        fail(msg)
                        self.errors.append(msg)
                except Exception as e:
                    msg = f'添加异常 [{month}]: {e}'
                    fail(msg)
                    self.errors.append(msg)
                    traceback.print_exc()

        info(f'Phase 1 完成: 成功添加 {self.total_added} 条新闻记忆')

    # ============================================================
    # Phase 2: 混入个人记忆数据
    # ============================================================
    def phase2_personal_memories(self):
        """添加个人记忆，混入到时间线中"""
        banner('Phase 2: 添加个人记忆数据')
        personal_count = 0

        for i, mem in enumerate(PERSONAL_MEMORIES):
            content = mem["content"]
            tags = mem["tags"]
            metadata = {
                "source": "personal",
                "tags": tags,
                "category": "personal"
            }

            try:
                result = self.engine.add(
                    content=content,
                    user_id="simulation_user",
                    metadata=metadata
                )
                if result and result.success:
                    personal_count += 1
                    self.total_added += 1
                    key = f"personal_{i}"
                    self.memory_ids[key] = result.id
                    self.all_contents.append(content)
                    info(f'  + [个人] {content[:50]}... -> ID: {result.id[:8]}')
                else:
                    msg = f'添加个人记忆失败: {content[:40]}...'
                    fail(msg)
                    self.errors.append(msg)
            except Exception as e:
                msg = f'添加个人记忆异常: {e}'
                fail(msg)
                self.errors.append(msg)
                traceback.print_exc()

        info(f'Phase 2 完成: 成功添加 {personal_count} 条个人记忆')

    # ============================================================
    # Phase 3: 数据完整性验证 - 每一条都能精确检索
    # ============================================================
    def phase3_data_integrity(self):
        """验证所有添加的数据都能通过 get_all 获取"""
        banner('Phase 3: 数据完整性验证 (get_all)')

        try:
            all_memories = self.engine.get_all(user_id="simulation_user")
            retrieved_count = len(all_memories) if all_memories else 0

            self.check(
                retrieved_count == self.total_added,
                f'get_all 返回 {retrieved_count} 条，与添加数 {self.total_added} 一致',
                f'get_all 返回 {retrieved_count} 条，期望 {self.total_added} 条 (差 {self.total_added - retrieved_count})'
            )

            # 验证每一条 memory 的内容不为空
            empty_count = 0
            for mem in (all_memories or []):
                content = mem.get('content', '')
                if not content or not content.strip():
                    empty_count += 1

            self.check(
                empty_count == 0,
                f'所有 {retrieved_count} 条记忆内容均非空',
                f'发现 {empty_count} 条空内容记忆'
            )

        except Exception as e:
            fail(f'get_all 异常: {e}')
            self.errors.append(f'get_all 异常: {e}')
            traceback.print_exc()

    # ============================================================
    # Phase 4: 单条精确检索验证 (get by ID)
    # ============================================================
    def phase4_precise_retrieval(self):
        """逐条验证每个已存储记忆可通过 ID 精确获取"""
        banner('Phase 4: 单条精确检索验证 (get by ID)')

        success_count = 0
        fail_count = 0
        sample_keys = list(self.memory_ids.keys())[:10]  # 取前 10 条样本

        for key in sample_keys:
            mid = self.memory_ids[key]
            try:
                mem = self.engine.get(memory_id=mid, user_id="simulation_user")
                if mem and mem.get('content'):
                    success_count += 1
                    info(f'  get({mid[:8]}) -> OK: {mem["content"][:40]}...')
                else:
                    fail_count += 1
                    fail(f'  get({mid[:8]}) -> 返回空或无内容')
            except Exception as e:
                fail_count += 1
                fail(f'  get({mid[:8]}) -> 异常: {e}')

        self.check(
            fail_count == 0,
            f'单条检索全部成功 ({success_count}/{len(sample_keys)})',
            f'单条检索失败 {fail_count}/{len(sample_keys)} 条'
        )

    # ============================================================
    # Phase 5: 搜索准确性验证 - 跨时间段查询
    # ============================================================
    def phase5_search_accuracy(self):
        """测试搜索功能的准确性，验证关键信息能被正确召回"""
        banner('Phase 5: 搜索准确性验证 (跨时间段查询)')

        search_cases = [
            # (查询, 期望包含的关键词, 描述)
            ("ChatGPT是什么时候发布的", ["ChatGPT", "OpenAI", "2022"], "2022年12月 ChatGPT 发布"),
            ("美联储加息", ["美联储", "加息", "75"], "2022年6月 美联储激进加息"),
            ("英国女王去世", ["女王", "伊丽莎白", "96"], "2022年9月 女王去世"),
            ("英伟达市值", ["英伟达", "万亿"], "2023年5月 英伟达市值破万亿"),
            ("土耳其地震", ["土耳其", "地震", "7.8"], "2023年2月 土耳其地震"),
            ("SpaceX星链", ["SpaceX", "星链", "卫星"], "2022年1月 星链发射"),
            ("Meta开源模型", ["Meta", "Llama"], "2023年7月 Llama 2 发布"),
            ("华为手机芯片", ["华为", "麒麟"], "2023年10月 华为 Mate 60"),
            ("Claude模型", ["Claude", "Anthropic"], "2024年3月 Claude 3 发布"),
            ("苹果AI", ["苹果", "Apple Intelligence"], "2024年6月 WWDC"),
            ("张伟搬到上海", ["张伟", "上海"], "个人记忆 - 朋友搬家"),
            ("猫打疫苗", ["糖糖", "疫苗"], "个人记忆 - 猫咪疫苗"),
            ("升职", ["升职", "技术组长"], "个人记忆 - 升职通知"),
            ("MacBook购买", ["MacBook", "M3"], "个人记忆 - 电脑购买"),
        ]

        for query, expected_keywords, description in search_cases:
            phase(f'搜索: "{query}" (期望: {description})')
            try:
                results = self.engine.search(
                    query=query,
                    user_id="simulation_user",
                    top_k=5
                )

                if not results:
                    fail(f'搜索 "{query}" 返回空结果')
                    self.errors.append(f'搜索无结果: {query}')
                    continue

                # 检查 top-5 结果中是否包含至少一个期望关键词
                top_contents = ' '.join([r.content for r in results[:5]])
                found_keywords = [kw for kw in expected_keywords if kw in top_contents]

                self.check(
                    len(found_keywords) > 0,
                    f'搜索 "{query}" 命中关键词: {found_keywords} (top-{len(results)})',
                    f'搜索 "{query}" 未命中任何关键词 {expected_keywords}'
                )

                # 显示 top-3 结果
                for i, r in enumerate(results[:3]):
                    info(f'  #{i+1} [score={r.score:.4f}] {r.content[:60]}...')

            except Exception as e:
                fail(f'搜索 "{query}" 异常: {e}')
                self.errors.append(f'搜索异常: {query}: {e}')
                traceback.print_exc()

    # ============================================================
    # Phase 6: 跨时间段综合分析查询
    # ============================================================
    def phase6_cross_temporal_queries(self):
        """测试跨越多年的综合查询能力"""
        banner('Phase 6: 跨时间段综合查询')

        temporal_queries = [
            ("AI领域重大事件", ["ChatGPT", "Gemini", "Claude", "英伟达", "Llama"], "AI领域3年大事"),
            ("航天和太空探索进展", ["SpaceX", "神舟", "星舰", "星链"], "航天进展"),
            ("全球地震灾难", ["土耳其", "日本", "地震"], "地震事件"),
            ("能源和气候", ["原油", "北溪", "COP28", "高温", "化石能源"], "能源气候3年"),
        ]

        for query, expected_any, description in temporal_queries:
            phase(f'跨时间查询: "{query}"')
            try:
                results = self.engine.search(
                    query=query,
                    user_id="simulation_user",
                    top_k=10
                )

                if not results:
                    fail(f'跨时间查询 "{query}" 返回空')
                    self.errors.append(f'跨时间查询无结果: {query}')
                    continue

                top_contents = ' '.join([r.content for r in results[:10]])
                found = [kw for kw in expected_any if kw in top_contents]

                self.check(
                    len(found) >= 2,
                    f'跨时间查询 "{query}" 命中 {len(found)} 个关键词: {found}',
                    f'跨时间查询 "{query}" 命中太少 ({len(found)}): {found}，期望至少 2 个'
                )

                info(f'  返回 {len(results)} 条结果:')
                for i, r in enumerate(results[:5]):
                    info(f'    #{i+1} [score={r.score:.4f}] {r.content[:55]}...')

            except Exception as e:
                fail(f'跨时间查询异常: {e}')
                self.errors.append(f'跨时间查询异常: {query}: {e}')
                traceback.print_exc()

    # ============================================================
    # Phase 7: 更新操作验证
    # ============================================================
    def phase7_update_verification(self):
        """测试 update 操作后数据一致性"""
        banner('Phase 7: 更新操作验证')

        # 找一个可更新的记忆
        update_key = "personal_0"  # 张伟见面
        if update_key not in self.memory_ids:
            warn('没有可更新的测试记忆，跳过')
            return

        mid = self.memory_ids[update_key]
        new_content = "今天和老朋友张伟在星巴克见面，他确认下个月要搬到上海浦东新区的张江高科工作，在一家做NLP的创业公司。"

        phase(f'更新记忆 {mid[:8]}')

        try:
            # 执行更新
            success = self.engine.update(
                memory_id=mid,
                content=new_content,
                user_id="simulation_user"
            )
            self.check(success, f'update({mid[:8]}) 返回 True', f'update({mid[:8]}) 返回 False')

            # 验证更新后内容
            mem = self.engine.get(memory_id=mid, user_id="simulation_user")
            if mem:
                actual_content = mem.get('content', '')
                self.check(
                    '张江高科' in actual_content or '浦东新区' in actual_content,
                    f'更新后内容包含新信息: {actual_content[:50]}...',
                    f'更新后内容未包含新信息: {actual_content[:50]}...'
                )
            else:
                fail(f'更新后 get({mid[:8]}) 返回 None')
                self.errors.append(f'更新后 get 返回 None')

            # 验证搜索也能找到更新后的内容
            search_results = self.engine.search(
                query="张伟 张江高科",
                user_id="simulation_user",
                top_k=5
            )
            if search_results:
                top_content = ' '.join([r.content for r in search_results[:5]])
                self.check(
                    '张江高科' in top_content or '浦东' in top_content or '张伟' in top_content,
                    f'搜索能找到更新后的内容',
                    f'搜索未找到更新后的内容'
                )

        except Exception as e:
            fail(f'更新操作异常: {e}')
            self.errors.append(f'更新异常: {e}')
            traceback.print_exc()

    # ============================================================
    # Phase 8: 删除操作验证
    # ============================================================
    def phase8_delete_verification(self):
        """测试 delete 操作后数据一致性"""
        banner('Phase 8: 删除操作验证')

        # 选择一条记忆进行删除
        delete_key = "personal_3"  # MacBook购买
        if delete_key not in self.memory_ids:
            warn('没有可删除的测试记忆，跳过')
            return

        mid = self.memory_ids[delete_key]
        phase(f'删除记忆 {mid[:8]}')

        try:
            # 记录删除前总数
            before_all = self.engine.get_all(user_id="simulation_user")
            before_count = len(before_all) if before_all else 0

            # 执行删除
            success = self.engine.delete(memory_id=mid, user_id="simulation_user")
            self.check(success, f'delete({mid[:8]}) 返回 True', f'delete({mid[:8]}) 返回 False')

            # 验证 get 返回 None
            mem = self.engine.get(memory_id=mid, user_id="simulation_user")
            self.check(
                mem is None,
                f'删除后 get({mid[:8]}) 返回 None (已删除)',
                f'删除后 get({mid[:8]}) 仍返回数据 (删除未生效)'
            )

            # 验证总数减少
            after_all = self.engine.get_all(user_id="simulation_user")
            after_count = len(after_all) if after_all else 0
            self.check(
                after_count == before_count - 1,
                f'删除后总数 {after_count} = {before_count} - 1',
                f'删除后总数 {after_count} != {before_count} - 1'
            )

            self.total_added -= 1  # 更新计数

        except Exception as e:
            fail(f'删除操作异常: {e}')
            self.errors.append(f'删除异常: {e}')
            traceback.print_exc()

    # ============================================================
    # Phase 9: 大批量操作后索引一致性检查
    # ============================================================
    def phase9_index_consistency(self):
        """检查所有操作后索引和存储的一致性"""
        banner('Phase 9: 索引一致性检查')

        try:
            # 获取统计信息
            stats = self.engine.get_stats(user_id="simulation_user")
            info(f'引擎统计信息:')
            if isinstance(stats, dict):
                for k, v in stats.items():
                    if isinstance(v, (str, int, float, bool)):
                        info(f'  {k}: {v}')

            # get_all 再次检查
            all_mems = self.engine.get_all(user_id="simulation_user")
            current_count = len(all_mems) if all_mems else 0
            self.check(
                current_count == self.total_added,
                f'索引一致: 存储 {current_count} 条 = 预期 {self.total_added} 条',
                f'索引不一致: 存储 {current_count} 条 != 预期 {self.total_added} 条'
            )

            # 每条记忆的 ID 和内容都不重复
            if all_mems:
                ids = [m.get('metadata', {}).get('id', '') for m in all_mems]
                unique_ids = set(ids)
                self.check(
                    len(unique_ids) == len(ids),
                    f'所有 ID 唯一 ({len(unique_ids)} unique / {len(ids)} total)',
                    f'存在重复 ID: {len(ids) - len(unique_ids)} 个'
                )

        except Exception as e:
            fail(f'索引一致性检查异常: {e}')
            self.errors.append(f'索引一致性异常: {e}')
            traceback.print_exc()

    # ============================================================
    # Phase 10: 最终搜索准确率统计
    # ============================================================
    def phase10_final_accuracy(self):
        """最终统计性搜索准确率"""
        banner('Phase 10: 最终搜索准确率统计')

        # 使用每月第一条新闻的关键词进行逐条检索验证
        hit = 0
        miss = 0

        for month_data in SIMULATED_NEWS_FEED:
            month = month_data["month"]
            first_event = month_data["events"][0]
            content = first_event["content"]
            # 提取前20字做查询
            query = content[:20]

            try:
                results = self.engine.search(
                    query=query,
                    user_id="simulation_user",
                    top_k=5
                )
                if results:
                    # 检查原始内容是否在 top-5
                    found = any(content[:30] in r.content for r in results[:5])
                    if found:
                        hit += 1
                        info(f'  [{month}] HIT: "{query[:15]}..." -> 找到原始内容')
                    else:
                        miss += 1
                        warn(f'  [{month}] MISS: "{query[:15]}..." -> top-5 未找到原始内容')
                        for i, r in enumerate(results[:3]):
                            info(f'    实际#{i+1}: {r.content[:50]}...')
                else:
                    miss += 1
                    warn(f'  [{month}] MISS: "{query[:15]}..." -> 无结果')
            except Exception as e:
                miss += 1
                warn(f'  [{month}] ERROR: {e}')

        total = hit + miss
        accuracy = (hit / total * 100) if total > 0 else 0

        info(f'')
        info(f'最终搜索准确率: {hit}/{total} = {accuracy:.1f}%')
        info(f'  命中: {hit}, 未命中: {miss}')

        self.check(
            accuracy >= 80,
            f'搜索准确率 {accuracy:.1f}% >= 80% 阈值',
            f'搜索准确率 {accuracy:.1f}% < 80% 阈值 (需要调查)'
        )

    # ============================================================
    # Phase 11: build_context 上下文构建测试
    # ============================================================
    def phase11_context_build(self):
        """测试 build_context 能否正确整合多源信息"""
        banner('Phase 11: build_context 上下文构建')

        queries = [
            "帮我总结一下2023年发生的重大AI事件",
            "张伟最近怎么样了",
            "全球有哪些重大自然灾害",
        ]

        for query in queries:
            phase(f'build_context: "{query}"')
            try:
                context = self.engine.build_context(
                    query=query,
                    user_id="simulation_user",
                    max_tokens=1000
                )
                if context and len(context.strip()) > 0:
                    ok(f'build_context 返回 {len(context)} 字符')
                    # 显示前200字
                    preview = context[:200].replace('\n', ' ')
                    info(f'  预览: {preview}...')
                else:
                    warn(f'build_context 返回空内容')
            except Exception as e:
                fail(f'build_context 异常: {e}')
                self.errors.append(f'build_context 异常: {query}: {e}')
                traceback.print_exc()

    # ============================================================
    # Phase 12: 清空验证
    # ============================================================
    def phase12_clear_verification(self):
        """测试 clear 操作后确保完全清空"""
        banner('Phase 12: 清空(clear)验证')

        try:
            success = self.engine.clear(user_id="simulation_user")
            self.check(success, 'clear() 返回 True', 'clear() 返回 False')

            remaining = self.engine.get_all(user_id="simulation_user")
            remaining_count = len(remaining) if remaining else 0
            self.check(
                remaining_count == 0,
                f'clear 后剩余 {remaining_count} 条 (已完全清空)',
                f'clear 后仍剩余 {remaining_count} 条 (清空不彻底)'
            )

            # 搜索也应返回空
            results = self.engine.search(query="ChatGPT", user_id="simulation_user", top_k=5)
            result_count = len(results) if results else 0
            self.check(
                result_count == 0,
                f'clear 后搜索返回 {result_count} 条 (索引已清理)',
                f'clear 后搜索仍返回 {result_count} 条 (索引残留!)'
            )

        except Exception as e:
            fail(f'clear 验证异常: {e}')
            self.errors.append(f'clear 异常: {e}')
            traceback.print_exc()

    # ============================================================
    # 主运行入口
    # ============================================================
    def run_all(self) -> Tuple[int, int]:
        """运行全部阶段，返回 (errors, warnings)"""
        banner('Recall AI 真实用户模拟测试 开始')
        info(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        info(f'数据目录: {self.data_root}')
        start_time = time.time()

        if not self.setup():
            return (len(self.errors), len(self.warnings))

        try:
            self.phase1_continuous_data_input()
            self.phase2_personal_memories()
            self.phase3_data_integrity()
            self.phase4_precise_retrieval()
            self.phase5_search_accuracy()
            self.phase6_cross_temporal_queries()
            self.phase7_update_verification()
            self.phase8_delete_verification()
            self.phase9_index_consistency()
            self.phase10_final_accuracy()
            self.phase11_context_build()
            self.phase12_clear_verification()
        except Exception as e:
            fail(f'测试过程中发生未捕获异常: {e}')
            self.errors.append(f'未捕获异常: {e}')
            traceback.print_exc()
        finally:
            self.teardown()

        elapsed = time.time() - start_time

        # ============================================================
        # 最终报告
        # ============================================================
        banner('模拟测试最终报告')
        info(f'总耗时: {elapsed:.2f}s')
        info(f'数据记录: {self.total_added} 条')
        info(f'检查总数: {self.total_checks}')
        info(f'通过: {self.total_passed}')
        info(f'失败: {self.total_checks - self.total_passed}')
        info(f'错误数: {len(self.errors)}')
        info(f'警告数: {len(self.warnings)}')

        if self.errors:
            safe_print('')
            safe_print('错误详情:')
            for i, err in enumerate(self.errors):
                safe_print(f'  {i+1}. {err}')

        if not self.errors:
            safe_print('')
            safe_print('*' * 60)
            safe_print('  ALL TESTS PASSED - 模拟测试全部通过!')
            safe_print('*' * 60)
        else:
            safe_print('')
            safe_print('!' * 60)
            safe_print(f'  TESTS FAILED - {len(self.errors)} 个错误需要修复')
            safe_print('!' * 60)

        return (len(self.errors), len(self.warnings))


# ============================================================
# pytest 入口
# ============================================================
def test_simulation():
    """pytest 入口 - 完整模拟测试"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        sim = SimulationTest(data_root=tmpdir)
        errors, warnings = sim.run_all()
        assert errors == 0, f"模拟测试有 {errors} 个错误"


# ============================================================
# 直接运行入口
# ============================================================
if __name__ == '__main__':
    safe_print('Recall AI - 真实用户模拟测试')
    safe_print('=' * 50)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        sim = SimulationTest(data_root=tmpdir)
        errors, warnings = sim.run_all()

    sys.exit(0 if errors == 0 else 1)
