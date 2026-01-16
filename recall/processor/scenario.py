"""场景检测器 - 检测对话场景类型"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ScenarioType(Enum):
    """场景类型"""
    ROLEPLAY = "roleplay"           # 角色扮演
    CODE_ASSIST = "code_assist"     # 代码辅助
    KNOWLEDGE_QA = "knowledge_qa"   # 知识问答
    CREATIVE = "creative"           # 创意写作
    TASK = "task"                   # 任务执行
    CHAT = "chat"                   # 闲聊
    UNKNOWN = "unknown"             # 未知


@dataclass
class ScenarioInfo:
    """场景信息"""
    type: ScenarioType
    confidence: float
    features: Dict[str, Any]
    suggested_retrieval_strategy: str
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'type': self.type.value,
            'confidence': self.confidence,
            'features': self.features,
            'suggested_retrieval_strategy': self.suggested_retrieval_strategy
        }


class ScenarioDetector:
    """场景检测器"""
    
    def __init__(self):
        # 场景特征模式
        self.patterns = {
            ScenarioType.ROLEPLAY: {
                'keywords': ['扮演', '角色', '人设', '设定', '*动作*', '（动作）', 
                            'roleplay', 'character', 'persona'],
                'patterns': [
                    r'\*[^*]+\*',           # *动作描述*
                    r'（[^）]+）',           # （动作描述）
                    r'"[^"]+"[^"]*说',       # "对话"他说
                ]
            },
            ScenarioType.CODE_ASSIST: {
                'keywords': ['代码', '编程', '函数', '变量', 'bug', '报错', 'error',
                            'python', 'javascript', 'java', 'code', 'function', 'debug'],
                'patterns': [
                    r'```[\s\S]*```',        # 代码块
                    r'def\s+\w+\s*\(',       # Python函数
                    r'function\s+\w+\s*\(',  # JS函数
                    r'class\s+\w+',          # 类定义
                ]
            },
            ScenarioType.KNOWLEDGE_QA: {
                'keywords': ['什么是', '为什么', '如何', '怎么', '解释', '区别',
                            'what is', 'why', 'how to', 'explain', 'difference'],
                'patterns': [
                    r'[\?？]$',              # 问句
                    r'^(什么|为什么|如何|怎么|谁|哪)',  # 中文疑问词开头
                ]
            },
            ScenarioType.CREATIVE: {
                'keywords': ['写一个', '创作', '故事', '小说', '诗', '文章',
                            'write', 'story', 'creative', 'poem', 'article'],
                'patterns': [
                    r'(写|创作|编)(一个|一篇|一首)',
                ]
            },
            ScenarioType.TASK: {
                'keywords': ['帮我', '请', '需要', '完成', '处理', '分析',
                            'please', 'help', 'need', 'do', 'analyze'],
                'patterns': [
                    r'^(帮我|请|麻烦)',
                ]
            }
        }
        
        # 检索策略映射
        self.retrieval_strategies = {
            ScenarioType.ROLEPLAY: 'entity_focused',      # 实体中心检索
            ScenarioType.CODE_ASSIST: 'keyword_exact',    # 精确关键词检索
            ScenarioType.KNOWLEDGE_QA: 'semantic_broad',  # 语义广泛检索
            ScenarioType.CREATIVE: 'creative_blend',      # 创意混合检索
            ScenarioType.TASK: 'task_relevant',           # 任务相关检索
            ScenarioType.CHAT: 'recent_context',          # 近期上下文检索
            ScenarioType.UNKNOWN: 'hybrid_balanced'       # 混合平衡检索
        }
    
    def detect(self, text: str, context: Optional[List[str]] = None) -> ScenarioInfo:
        """检测场景类型"""
        scores: Dict[ScenarioType, float] = {t: 0.0 for t in ScenarioType}
        features: Dict[str, Any] = {}
        
        text_lower = text.lower()
        
        # 1. 关键词匹配
        for scenario_type, config in self.patterns.items():
            keyword_score = 0
            matched_keywords = []
            
            for keyword in config['keywords']:
                if keyword.lower() in text_lower:
                    keyword_score += 1
                    matched_keywords.append(keyword)
            
            if keyword_score > 0:
                scores[scenario_type] += keyword_score * 0.3
                features[f'{scenario_type.value}_keywords'] = matched_keywords
        
        # 2. 正则模式匹配
        for scenario_type, config in self.patterns.items():
            pattern_score = 0
            
            for pattern in config['patterns']:
                if re.search(pattern, text, re.IGNORECASE):
                    pattern_score += 1
            
            if pattern_score > 0:
                scores[scenario_type] += pattern_score * 0.5
        
        # 3. 上下文分析（如果提供）
        if context:
            context_text = ' '.join(context[-5:])  # 最近5条
            context_lower = context_text.lower()
            
            for scenario_type, config in self.patterns.items():
                for keyword in config['keywords']:
                    if keyword.lower() in context_lower:
                        scores[scenario_type] += 0.1
        
        # 4. 确定最终场景
        if max(scores.values()) == 0:
            # 没有明确匹配，默认为聊天
            detected_type = ScenarioType.CHAT
            confidence = 0.5
        else:
            detected_type = max(scores, key=lambda x: scores[x])
            max_score = scores[detected_type]
            total_score = sum(scores.values())
            confidence = max_score / total_score if total_score > 0 else 0.5
        
        return ScenarioInfo(
            type=detected_type,
            confidence=min(confidence, 1.0),
            features=features,
            suggested_retrieval_strategy=self.retrieval_strategies[detected_type]
        )
    
    def detect_batch(self, texts: List[str]) -> List[ScenarioInfo]:
        """批量检测"""
        return [self.detect(text) for text in texts]
    
    def get_retrieval_config(self, scenario: ScenarioInfo) -> Dict[str, Any]:
        """根据场景获取检索配置"""
        configs = {
            'entity_focused': {
                'use_entity_index': True,
                'entity_weight': 0.6,
                'semantic_weight': 0.3,
                'keyword_weight': 0.1,
                'max_results': 10
            },
            'keyword_exact': {
                'use_entity_index': False,
                'entity_weight': 0.1,
                'semantic_weight': 0.2,
                'keyword_weight': 0.7,
                'max_results': 15
            },
            'semantic_broad': {
                'use_entity_index': True,
                'entity_weight': 0.2,
                'semantic_weight': 0.7,
                'keyword_weight': 0.1,
                'max_results': 20
            },
            'creative_blend': {
                'use_entity_index': True,
                'entity_weight': 0.3,
                'semantic_weight': 0.5,
                'keyword_weight': 0.2,
                'max_results': 15,
                'include_random': True
            },
            'task_relevant': {
                'use_entity_index': False,
                'entity_weight': 0.2,
                'semantic_weight': 0.5,
                'keyword_weight': 0.3,
                'max_results': 10
            },
            'recent_context': {
                'use_entity_index': False,
                'entity_weight': 0.1,
                'semantic_weight': 0.3,
                'keyword_weight': 0.1,
                'time_weight': 0.5,
                'max_results': 8
            },
            'hybrid_balanced': {
                'use_entity_index': True,
                'entity_weight': 0.25,
                'semantic_weight': 0.4,
                'keyword_weight': 0.25,
                'time_weight': 0.1,
                'max_results': 12
            }
        }
        
        return configs.get(scenario.suggested_retrieval_strategy, configs['hybrid_balanced'])
