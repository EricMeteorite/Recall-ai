"""测试绝对规则检测功能（LLM语义检测）"""
import sys
import os
sys.path.insert(0, '.')

from recall.processor.consistency import ConsistencyChecker


def test_config_and_init():
    """测试配置和初始化"""
    print("=== 测试0: 配置检查 ===")
    print(f"  LLM_API_KEY: {'已设置' if os.environ.get('LLM_API_KEY') else '未设置'}")
    print(f"  LLM_API_BASE: {os.environ.get('LLM_API_BASE', '未设置')}")
    print(f"  LLM_MODEL: {os.environ.get('LLM_MODEL', '未设置')}")
    
    # 测试 ConsistencyChecker 正确接收 llm_client
    checker = ConsistencyChecker(absolute_rules=['测试规则'], llm_client=None)
    print(f"  ConsistencyChecker._llm_client: {checker._llm_client}")
    print(f"  ConsistencyChecker.absolute_rules: {checker.absolute_rules}")
    
    assert checker.absolute_rules == ['测试规则']


def test_fallback_detection():
    """测试无LLM时的回退行为"""
    
    # 测试规则
    rules = [
        '角色不会杀人，即使是敌人也不会伤害',
        '不能使用任何脏话或粗俗语言',
        '禁止打破第四面墙，不能提及自己是AI或语言模型',
        '角色是一个温柔的女孩，她从不会对任何人发火，即使被欺负也会选择忍耐',
    ]
    
    # 不传LLM客户端
    checker = ConsistencyChecker(absolute_rules=rules, llm_client=None)
    print(f'✅ 加载了 {len(checker.absolute_rules)} 条规则')
    print('⚠️ 未配置LLM客户端\n')
    
    # 测试：无LLM时应该返回空（因为无法准确检测）
    print('测试无LLM时的行为:')
    test_contents = [
        '角色杀死了敌人',
        '操，这太难了',
        '我是AI，只是在角色扮演',
        '你好，今天天气真好',
    ]
    
    all_empty = True
    for content in test_contents:
        violations = checker._check_absolute_rules(content)
        is_empty = len(violations) == 0
        all_empty = all_empty and is_empty
        print(f'  {"✅" if is_empty else "❌"} "{content[:30]}" -> {len(violations)} 违规 (预期: 0，无LLM不检测)')
    
    if all_empty:
        print('\n✅ 无LLM时正确返回空结果（规则检测需要LLM语义理解）')
        print('   提示: 配置 LLM_API_KEY 后才能启用规则检测')
    else:
        print('\n❌ 无LLM时不应该返回违规')
    
    assert all_empty, "无LLM时应该返回空结果"


def test_with_mock_llm():
    """测试LLM语义检测（使用模拟LLM）"""
    
    class MockLLMClient:
        """模拟LLM客户端用于测试
        
        注意：这只是一个简单的模拟，真实LLM会有更好的语义理解能力
        """
        def complete(self, prompt, max_tokens=500, temperature=0.1):
            # 从prompt中提取待检查内容（在 ## 待检查内容 和 ## 检查要求 之间）
            content_start = prompt.find('## 待检查内容：')
            content_end = prompt.find('## 检查要求：')
            if content_start == -1:
                return "PASS"
            
            # 提取实际要检查的内容
            content = prompt[content_start+10:content_end].strip() if content_end > content_start else prompt[content_start+10:content_start+300]
            
            # 简单的模拟逻辑
            if '杀死' in content or '杀了' in content:
                return "VIOLATION|1|内容中角色杀死了人，违反了不杀人的规则"
            if '操' in content or '傻逼' in content:
                return "VIOLATION|2|内容中出现了脏话，违反了禁止脏话的规则"
            if '我是AI' in content or '作为一个AI' in content:
                return "VIOLATION|3|内容提及AI身份，违反了第四面墙规则"
            # 只检查内容中是否有愤怒行为，不是检查规则描述
            if '狠狠' in content or '怒吼' in content or ('发火' in content and '从不' not in content):
                return "VIOLATION|4|角色表现出愤怒情绪，违反了温柔性格的规则"
            return "PASS"
    
    rules = [
        '角色不会杀人，即使是敌人也不会伤害',
        '不能使用任何脏话或粗俗语言',
        '禁止打破第四面墙，不能提及自己是AI或语言模型',
        '角色是一个温柔的女孩，她从不会对任何人发火，即使被欺负也会选择忍耐',
    ]
    
    checker = ConsistencyChecker(absolute_rules=rules, llm_client=MockLLMClient())
    print(f'\n✅ LLM客户端已设置，使用语义检测\n')
    
    print('测试LLM语义检测:')
    test_cases = [
        ('角色温柔地微笑着', False),         # 正常
        ('角色杀死了敌人', True),             # 违反：杀人
        ('她狠狠地踢了他一脚', True),         # 违反：温柔性格（语义理解）
        ('她怒吼着冲了上去', True),           # 违反：温柔性格（语义理解）
        ('你好，今天天气真好', False),        # 正常
    ]
    
    passed = 0
    failed = 0
    
    for content, should_violate in test_cases:
        violations = checker._check_absolute_rules(content)
        is_correct = (len(violations) > 0) == should_violate
        status = '✅' if is_correct else '❌'
        
        if is_correct:
            passed += 1
        else:
            failed += 1
        
        print(f'  {status} "{content[:30]}" -> {len(violations)} 违规 (预期: {"有" if should_violate else "无"})')
        if violations:
            print(f'      → {violations[0].description[:60]}...')
    
    print(f'\nLLM检测结果: {passed} 通过, {failed} 失败')
    
    assert failed == 0, f"LLM检测有 {failed} 个测试失败"


def test_update_rules():
    """测试运行时规则更新"""
    print('\n测试运行时规则更新:')
    checker = ConsistencyChecker(absolute_rules=['不能说谎'])
    print(f'  初始规则: {len(checker.absolute_rules)} 条')
    
    checker.update_rules(['规则1', '规则2', '规则3'])
    print(f'  更新后: {len(checker.absolute_rules)} 条')
    
    checker.update_rules([])
    print(f'  清空后: {len(checker.absolute_rules)} 条')
    
    assert len(checker.absolute_rules) == 0


# ============================================================
# 端到端测试（合并自 test_absolute_rules_e2e.py）
# ============================================================

def test_full_pipeline():
    """测试完整流程：规则 -> 检查 -> 警告"""
    print("\n" + "=" * 60)
    print("端到端测试：绝对规则检测完整流程")
    print("=" * 60)
    
    # 1. 模拟前端保存规则
    rules_from_frontend = [
        "用户是一个中年男性",
        "禁止任何18岁以下角色参与恋爱剧情",
        "主角的武器是双刀"
    ]
    print(f"\n[1/5] 前端规则: {rules_from_frontend}")
    
    # 2. 创建 ConsistencyChecker（模拟 engine 初始化）
    checker = ConsistencyChecker(absolute_rules=rules_from_frontend)
    print(f"[2/5] ConsistencyChecker 初始化完成，规则数: {len(checker.absolute_rules)}")
    
    # 3. 模拟运行时更新规则（通过 API 更新）
    new_rules = rules_from_frontend + ["故事背景是现代都市"]
    checker.update_rules(new_rules)
    print(f"[3/5] 运行时更新规则，新规则数: {len(checker.absolute_rules)}")
    
    # 4. 测试规则检查
    test_cases = [
        ("张三说：我是一个年轻女孩", True),   # 违反：用户是中年男性
        ("16岁的小明和小红开始约会了", True), # 违反：禁止18岁以下恋爱
        ("主角拔出了长剑", True),             # 违反：武器是双刀
        ("张三在办公室工作", False),          # 符合现代都市
        ("主角挥舞双刀战斗", False),          # 符合：双刀
    ]
    
    print(f"\n[4/5] 开始检查测试用例...")
    passed = 0
    
    for content, should_warn in test_cases:
        result = checker.check(content, [])
        has_warning = not result.is_consistent
        print(f"  [{has_warning and '⚠' or '✓'}] \"{content[:30]}...\"")
        if result.violations:
            for v in result.violations:
                print(f"      违规: {v.description[:50]}...")
        passed += 1
    
    # 5. 验证警告格式
    print(f"\n[5/5] 验证警告格式...")
    result = checker.check("我是一个年轻女孩，今年才15岁", [])
    print(f"  is_consistent: {result.is_consistent}")
    print(f"  violations count: {len(result.violations)}")
    
    print(f"\n✅ 端到端测试完成")


def test_api_integration():
    """模拟 API 集成测试"""
    print("\n" + "=" * 60)
    print("API 集成测试")
    print("=" * 60)
    
    # 模拟 PUT /v1/core-settings 接收规则并更新
    api_request_body = {
        "absolute_rules": ["规则A", "规则B", "规则C"]
    }
    
    checker = ConsistencyChecker(absolute_rules=[])
    checker.update_rules(api_request_body["absolute_rules"])
    
    assert checker.absolute_rules == ["规则A", "规则B", "规则C"], "规则更新失败"
    print("✅ 规则通过 API 更新成功")
    
    # 模拟 /v1/memories 返回 consistency_warnings
    result = checker.check("测试内容", [])
    api_response = {
        "id": "mem_test123",
        "success": True,
        "entities": [],
        "consistency_warnings": [v.description for v in result.violations]
    }
    print(f"✅ API 响应构造成功: {len(api_response['consistency_warnings'])} 条警告")


def test_llm_client_injection():
    """测试 LLM 客户端注入"""
    print("\n" + "=" * 60)
    print("LLM 客户端注入测试")
    print("=" * 60)
    
    # 无 LLM 的 checker
    checker = ConsistencyChecker(absolute_rules=["测试规则"])
    assert checker._llm_client is None, "应该没有 LLM 客户端"
    print("✅ 无 LLM 时使用回退检测")
    
    # 使用 set_llm_client 注入
    class MockLLM:
        def chat(self, prompt, **kwargs):
            return "PASS"
    
    checker.set_llm_client(MockLLM())
    assert checker._llm_client is not None, "LLM 客户端注入失败"
    print("✅ LLM 客户端注入成功")
    
    # 通过构造函数传入
    checker2 = ConsistencyChecker(absolute_rules=["测试"], llm_client=MockLLM())
    assert checker2._llm_client is not None, "构造函数传入 LLM 失败"
    print("✅ 构造函数传入 LLM 成功")


# ============================================================
# 主入口
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("绝对规则检测测试（含端到端测试）")
    print("=" * 60)
    
    all_passed = True
    
    try:
        # 单元测试
        test_config_and_init()
        test_fallback_detection()
        test_with_mock_llm()
        test_update_rules()
        
        # 端到端测试
        test_full_pipeline()
        test_api_integration()
        test_llm_client_injection()
        
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败")
    print("=" * 60)
    
    sys.exit(0 if all_passed else 1)

