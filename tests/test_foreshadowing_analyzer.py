"""伏笔分析器单元测试

测试 ForeshadowingAnalyzer 的所有功能，确保：
1. 与现有 ForeshadowingTracker 完全兼容
2. 手动模式不影响任何现有功能
3. LLM 模式正确工作（需要 mock）
4. 配置系统正确工作
"""

import pytest
import time
import json
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

# 导入被测试的模块
from recall.processor.foreshadowing import (
    ForeshadowingTracker, 
    Foreshadowing, 
    ForeshadowingStatus
)
from recall.processor.foreshadowing_analyzer import (
    ForeshadowingAnalyzer,
    ForeshadowingAnalyzerConfig,
    AnalyzerBackend,
    AnalysisResult
)


class TestForeshadowingAnalyzerConfig:
    """测试配置类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ForeshadowingAnalyzerConfig()
        assert config.backend == AnalyzerBackend.MANUAL
        assert config.trigger_interval == 10
        assert config.auto_plant == True
        assert config.auto_resolve == False
        assert config.llm_model == "gpt-4o-mini"
        assert config.llm_api_key is None
    
    def test_manual_factory(self):
        """测试手动模式工厂方法"""
        config = ForeshadowingAnalyzerConfig.manual()
        assert config.backend == AnalyzerBackend.MANUAL
    
    def test_llm_factory(self):
        """测试 LLM 模式工厂方法"""
        config = ForeshadowingAnalyzerConfig.llm_based(
            api_key="test-key",
            model="gpt-4",
            trigger_interval=5
        )
        assert config.backend == AnalyzerBackend.LLM
        assert config.llm_api_key == "test-key"
        assert config.llm_model == "gpt-4"
        assert config.trigger_interval == 5
    
    def test_trigger_interval_validation(self):
        """测试 trigger_interval 最小值验证"""
        config = ForeshadowingAnalyzerConfig(trigger_interval=0)
        assert config.trigger_interval == 1  # 应该被修正为 1
        
        config = ForeshadowingAnalyzerConfig(trigger_interval=-5)
        assert config.trigger_interval == 1
    
    def test_to_dict(self):
        """测试序列化"""
        config = ForeshadowingAnalyzerConfig.llm_based(
            api_key="secret",
            model="gpt-4"
        )
        data = config.to_dict()
        
        assert data['backend'] == 'llm'
        assert data['llm_model'] == 'gpt-4'
        assert 'llm_api_key' not in data  # API key 不应该被序列化
    
    def test_from_dict(self):
        """测试反序列化"""
        data = {
            'backend': 'llm',
            'trigger_interval': 15,
            'llm_model': 'claude-3',
            'auto_plant': False
        }
        config = ForeshadowingAnalyzerConfig.from_dict(data, api_key="new-key")
        
        assert config.backend == AnalyzerBackend.LLM
        assert config.trigger_interval == 15
        assert config.llm_model == 'claude-3'
        assert config.llm_api_key == "new-key"
        assert config.auto_plant == False


class TestForeshadowingAnalyzerManualMode:
    """测试手动模式"""
    
    @pytest.fixture
    def tracker(self, tmp_path):
        """创建临时 tracker"""
        return ForeshadowingTracker(storage_dir=str(tmp_path / "foreshadowings"))
    
    @pytest.fixture
    def manual_analyzer(self, tracker):
        """创建手动模式分析器"""
        return ForeshadowingAnalyzer(
            tracker=tracker,
            config=ForeshadowingAnalyzerConfig.manual()
        )
    
    def test_manual_mode_no_analysis(self, manual_analyzer):
        """手动模式不应该触发任何分析"""
        result = manual_analyzer.on_new_turn(
            content="这是一个测试对话",
            role="user",
            user_id="test_user"
        )
        
        assert result.triggered == False
        assert result.new_foreshadowings == []
        assert result.potentially_resolved == []
        assert result.error is None
    
    def test_manual_mode_multiple_turns(self, manual_analyzer):
        """手动模式多轮对话不触发分析"""
        for i in range(20):  # 超过默认的 trigger_interval
            result = manual_analyzer.on_new_turn(
                content=f"对话 {i}",
                role="user" if i % 2 == 0 else "assistant",
                user_id="test_user"
            )
            assert result.triggered == False
    
    def test_manual_mode_trigger_analysis_no_llm(self, manual_analyzer):
        """手动模式下手动触发分析返回错误"""
        result = manual_analyzer.trigger_analysis(user_id="test_user")
        
        assert result.triggered == False
        assert "LLM" in result.error
    
    def test_tracker_operations_still_work(self, manual_analyzer, tracker):
        """确保 tracker 操作仍然正常"""
        # 埋下伏笔
        fsh = tracker.plant(
            content="神秘的盒子",
            user_id="test_user",
            importance=0.8
        )
        assert fsh.id is not None
        assert fsh.content == "神秘的盒子"
        
        # 获取活跃伏笔
        active = tracker.get_active("test_user")
        assert len(active) == 1
        
        # 解决伏笔
        success = tracker.resolve(fsh.id, "盒子打开了", "test_user")
        assert success == True
        
        # 确认已解决
        active = tracker.get_active("test_user")
        assert len(active) == 0


class TestForeshadowingAnalyzerLLMMode:
    """测试 LLM 模式（使用 mock）"""
    
    @pytest.fixture
    def tracker(self, tmp_path):
        """创建临时 tracker"""
        return ForeshadowingTracker(storage_dir=str(tmp_path / "foreshadowings"))
    
    @pytest.fixture
    def mock_llm_response(self):
        """模拟 LLM 响应"""
        return Mock(
            content=json.dumps({
                "new_foreshadowings": [
                    {
                        "content": "神秘人提到的三年之约",
                        "importance": 0.9,
                        "evidence": "三年之约将至",
                        "related_entities": ["神秘人"]
                    }
                ],
                "potentially_resolved": []
            })
        )
    
    def test_llm_mode_buffer_accumulation(self, tracker):
        """测试 LLM 模式对话缓冲累积"""
        with patch('recall.processor.foreshadowing_analyzer.ForeshadowingAnalyzer._init_llm_client'):
            analyzer = ForeshadowingAnalyzer(
                tracker=tracker,
                config=ForeshadowingAnalyzerConfig.llm_based(
                    api_key="test-key",
                    trigger_interval=5
                )
            )
            # 由于没有真正的 LLM 客户端，is_llm_enabled 为 False
            analyzer._llm_client = None
        
        # 添加对话
        for i in range(3):
            analyzer.on_new_turn(f"对话 {i}", "user", "test_user")
        
        # 检查缓冲区
        assert analyzer.get_buffer_size("test_user") == 3
        assert analyzer.get_turns_until_analysis("test_user") == 2
    
    def test_llm_mode_trigger_on_interval(self, tracker, mock_llm_response):
        """测试 LLM 模式在达到间隔时触发分析"""
        with patch('recall.processor.foreshadowing_analyzer.ForeshadowingAnalyzer._init_llm_client'):
            analyzer = ForeshadowingAnalyzer(
                tracker=tracker,
                config=ForeshadowingAnalyzerConfig.llm_based(
                    api_key="test-key",
                    trigger_interval=3,
                    auto_plant=False  # 不自动埋下
                )
            )
        
        # 模拟 LLM 客户端
        mock_client = Mock()
        mock_client.chat.return_value = mock_llm_response
        analyzer._llm_client = mock_client
        
        # 前两轮不触发
        for i in range(2):
            result = analyzer.on_new_turn(f"对话 {i}", "user", "test_user")
            assert result.triggered == False
        
        # 第三轮触发
        result = analyzer.on_new_turn("黑衣人说：三年之约将至", "assistant", "test_user")
        assert result.triggered == True
        assert len(result.new_foreshadowings) == 1
        assert result.new_foreshadowings[0]['content'] == "神秘人提到的三年之约"
    
    def test_llm_mode_auto_plant(self, tracker, mock_llm_response):
        """测试 LLM 模式自动埋下伏笔"""
        with patch('recall.processor.foreshadowing_analyzer.ForeshadowingAnalyzer._init_llm_client'):
            analyzer = ForeshadowingAnalyzer(
                tracker=tracker,
                config=ForeshadowingAnalyzerConfig.llm_based(
                    api_key="test-key",
                    trigger_interval=1,  # 每轮触发
                    auto_plant=True
                )
            )
        
        # 模拟 LLM 客户端
        mock_client = Mock()
        mock_client.chat.return_value = mock_llm_response
        analyzer._llm_client = mock_client
        
        # 触发分析
        result = analyzer.on_new_turn("黑衣人说：三年之约将至", "assistant", "test_user")
        
        # 检查是否自动埋下了伏笔
        active = tracker.get_active("test_user")
        assert len(active) == 1
        assert "三年之约" in active[0].content
    
    def test_llm_mode_manual_trigger(self, tracker, mock_llm_response):
        """测试 LLM 模式手动触发"""
        with patch('recall.processor.foreshadowing_analyzer.ForeshadowingAnalyzer._init_llm_client'):
            analyzer = ForeshadowingAnalyzer(
                tracker=tracker,
                config=ForeshadowingAnalyzerConfig.llm_based(
                    api_key="test-key",
                    trigger_interval=100,  # 高间隔，不会自动触发
                    auto_plant=False
                )
            )
        
        # 模拟 LLM 客户端
        mock_client = Mock()
        mock_client.chat.return_value = mock_llm_response
        analyzer._llm_client = mock_client
        
        # 添加一些对话
        analyzer.on_new_turn("对话1", "user", "test_user")
        analyzer.on_new_turn("对话2", "assistant", "test_user")
        
        # 手动触发
        result = analyzer.trigger_analysis("test_user")
        assert result.triggered == True


class TestForeshadowingAnalyzerEdgeCases:
    """测试边缘情况"""
    
    @pytest.fixture
    def tracker(self, tmp_path):
        """创建临时 tracker"""
        return ForeshadowingTracker(storage_dir=str(tmp_path / "foreshadowings"))
    
    def test_none_tracker_raises(self):
        """tracker 为 None 应该报错"""
        with pytest.raises(ValueError) as excinfo:
            ForeshadowingAnalyzer(tracker=None)
        assert "tracker" in str(excinfo.value)
    
    def test_empty_buffer_analysis(self, tracker):
        """空缓冲区分析"""
        with patch('recall.processor.foreshadowing_analyzer.ForeshadowingAnalyzer._init_llm_client'):
            analyzer = ForeshadowingAnalyzer(
                tracker=tracker,
                config=ForeshadowingAnalyzerConfig.llm_based(api_key="test")
            )
            mock_client = Mock()
            analyzer._llm_client = mock_client
        
        # 直接触发分析（没有添加对话）
        result = analyzer.trigger_analysis("test_user")
        assert "空" in result.error or "empty" in result.error.lower()
    
    def test_clear_buffer(self, tracker):
        """测试清空缓冲区"""
        analyzer = ForeshadowingAnalyzer(
            tracker=tracker,
            config=ForeshadowingAnalyzerConfig.manual()
        )
        
        # 添加对话
        for i in range(5):
            analyzer.on_new_turn(f"对话 {i}", "user", "test_user")
        
        assert analyzer.get_buffer_size("test_user") == 5
        
        # 清空
        analyzer.clear_buffer("test_user")
        assert analyzer.get_buffer_size("test_user") == 0
    
    def test_update_config(self, tracker):
        """测试更新配置"""
        analyzer = ForeshadowingAnalyzer(
            tracker=tracker,
            config=ForeshadowingAnalyzerConfig(trigger_interval=10, auto_plant=True)
        )
        
        assert analyzer.config.trigger_interval == 10
        assert analyzer.config.auto_plant == True
        
        # 更新配置
        analyzer.update_config(trigger_interval=5, auto_plant=False)
        
        assert analyzer.config.trigger_interval == 5
        assert analyzer.config.auto_plant == False
    
    def test_multiple_users(self, tracker):
        """测试多用户隔离"""
        analyzer = ForeshadowingAnalyzer(
            tracker=tracker,
            config=ForeshadowingAnalyzerConfig.manual()
        )
        
        # 不同用户添加对话
        analyzer.on_new_turn("用户1的对话", "user", "user1")
        analyzer.on_new_turn("用户2的对话", "user", "user2")
        analyzer.on_new_turn("用户1的另一条对话", "user", "user1")
        
        # 检查缓冲区隔离
        assert analyzer.get_buffer_size("user1") == 2
        assert analyzer.get_buffer_size("user2") == 1
    
    def test_llm_response_parsing_markdown(self, tracker):
        """测试 LLM 响应解析（markdown 格式）"""
        analyzer = ForeshadowingAnalyzer(
            tracker=tracker,
            config=ForeshadowingAnalyzerConfig.manual()
        )
        
        # 带 markdown 代码块的响应
        response = '''这是分析结果：
```json
{
  "new_foreshadowings": [{"content": "测试伏笔", "importance": 0.5}],
  "potentially_resolved": []
}
```
'''
        result = analyzer._parse_llm_response(response)
        assert len(result.new_foreshadowings) == 1
        assert result.new_foreshadowings[0]['content'] == "测试伏笔"
    
    def test_llm_response_parsing_invalid_json(self, tracker):
        """测试 LLM 响应解析（无效 JSON）"""
        analyzer = ForeshadowingAnalyzer(
            tracker=tracker,
            config=ForeshadowingAnalyzerConfig.manual()
        )
        
        # 无效的 JSON
        result = analyzer._parse_llm_response("这不是JSON")
        assert result.error is not None
        assert result.new_foreshadowings == []


class TestBackwardCompatibility:
    """测试向后兼容性 - 确保不影响现有功能"""
    
    @pytest.fixture
    def tracker(self, tmp_path):
        """创建临时 tracker"""
        return ForeshadowingTracker(storage_dir=str(tmp_path / "foreshadowings"))
    
    def test_tracker_works_without_analyzer(self, tracker):
        """ForeshadowingTracker 可以独立工作"""
        # 这个测试确保 tracker 不依赖 analyzer
        fsh = tracker.plant("独立测试", "user1", importance=0.7)
        assert fsh is not None
        
        tracker.add_hint(fsh.id, "一个提示", "user1")
        
        active = tracker.get_active("user1")
        assert len(active) == 1
        assert len(active[0].hints) == 1
        
        tracker.resolve(fsh.id, "解决了", "user1")
        active = tracker.get_active("user1")
        assert len(active) == 0
    
    def test_analyzer_with_existing_foreshadowings(self, tracker):
        """分析器可以与已有伏笔一起工作"""
        # 先添加一些伏笔（使用明显不同的内容以避免语义去重）
        tracker.plant("神秘信件藏在书架后面", "user1", importance=0.8)
        tracker.plant("窗外的黑影是谁派来的", "user1", importance=0.5)
        
        # 创建分析器
        analyzer = ForeshadowingAnalyzer(
            tracker=tracker,
            config=ForeshadowingAnalyzerConfig.manual()
        )
        
        # 分析器应该能看到已有伏笔
        active = analyzer.tracker.get_active("user1")
        assert len(active) == 2
    
    def test_default_analyzer_is_manual(self, tracker):
        """默认分析器应该是手动模式"""
        analyzer = ForeshadowingAnalyzer(tracker=tracker)
        assert analyzer.config.backend == AnalyzerBackend.MANUAL
        assert analyzer.is_llm_enabled == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
