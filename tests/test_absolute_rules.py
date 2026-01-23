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


if __name__ == '__main__':
    print("=" * 60)
    print("绝对规则检测测试")
    print("=" * 60)
    
    success0 = test_config_and_init()
    success1 = test_fallback_detection()
    success2 = test_with_mock_llm()
    success3 = test_update_rules()
    
    print("\n" + "=" * 60)
    if success0 and success1 and success2 and success3:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败")
    print("=" * 60)
    
    sys.exit(0 if (success0 and success1 and success2 and success3) else 1)

