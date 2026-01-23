"""一致性检查器 - 检测记忆中的矛盾（增强版 v3.1）

增强功能：
- 15+ 种属性类型检测（数值、外貌、状态、关系等）
- 完整时间线推理（事件链、年龄一致性、生死矛盾）
- 否定句检测和矛盾关系识别
- 模糊匹配（语义近似词汇合并）
"""

import re
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum


class ViolationType(Enum):
    """违规类型"""
    FACT_CONFLICT = "fact_conflict"           # 事实冲突
    TIMELINE_CONFLICT = "timeline_conflict"   # 时间线冲突
    CHARACTER_CONFLICT = "character_conflict" # 角色设定冲突
    LOCATION_CONFLICT = "location_conflict"   # 地点冲突
    LOGIC_ERROR = "logic_error"               # 逻辑错误
    RELATIONSHIP_CONFLICT = "relationship_conflict"  # 关系冲突
    STATE_CONFLICT = "state_conflict"         # 状态冲突（活/死、单身/已婚）
    AGE_INCONSISTENCY = "age_inconsistency"   # 年龄时间线不一致


class AttributeType(Enum):
    """属性类型"""
    # 数值属性
    AGE = "age"
    HEIGHT = "height"
    WEIGHT = "weight"
    # 外貌属性
    HAIR_COLOR = "hair_color"
    EYE_COLOR = "eye_color"
    SKIN_COLOR = "skin_color"
    # 固定属性
    BLOOD_TYPE = "blood_type"
    GENDER = "gender"
    SPECIES = "species"
    # 状态属性
    VITAL_STATUS = "vital_status"  # 活着/死亡
    MARITAL_STATUS = "marital_status"  # 婚姻状态
    OCCUPATION = "occupation"  # 职业
    LOCATION = "location"  # 当前位置
    # 能力属性
    ABILITY = "ability"  # 能力/技能
    INABILITY = "inability"  # 不能做的事


@dataclass
class Violation:
    """违规/冲突记录"""
    type: ViolationType
    description: str
    evidence: List[str]
    severity: float  # 0-1
    suggested_resolution: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'type': self.type.value,
            'description': self.description,
            'evidence': self.evidence,
            'severity': self.severity,
            'suggested_resolution': self.suggested_resolution,
            'created_at': self.created_at
        }


@dataclass
class ConsistencyResult:
    """一致性检查结果"""
    is_consistent: bool
    violations: List[Violation] = field(default_factory=list)
    confidence: float = 1.0
    checked_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'is_consistent': self.is_consistent,
            'violations': [v.to_dict() for v in self.violations],
            'confidence': self.confidence,
            'checked_at': self.checked_at
        }


@dataclass
class TimelineEvent:
    """时间线事件"""
    entity: str
    event_type: str  # birth, death, action, state_change
    description: str
    timestamp: Optional[float] = None  # 绝对时间戳
    relative_time: Optional[str] = None  # "三年前", "之后"
    source: str = ""
    turn_id: int = 0


class ConsistencyChecker:
    """一致性检查器（增强版）
    
    支持的检测能力：
    1. 数值属性冲突（年龄/身高/体重等）
    2. 外貌属性冲突（发色/眼色/肤色等）
    3. 状态属性冲突（生死/婚姻/职业等）
    4. 关系冲突（朋友vs敌人、亲人vs陌生人）
    5. 时间线推理（事件顺序、年龄一致性、生死矛盾）
    6. 否定句检测（不会X vs 做了X）
    """
    
    # ========== 颜色同义词映射 ==========
    COLOR_SYNONYMS = {
        'black': {'黑色', '黑', '乌黑', '漆黑', '墨黑', '黢黑', '黑亮'},
        'white': {'白色', '白', '雪白', '银白', '纯白', '洁白', '苍白'},
        'brown': {'棕色', '棕', '褐色', '褐', '茶色', '栗色', '咖啡色'},
        'red': {'红色', '红', '赤红', '绯红', '猩红', '酒红', '暗红'},
        'blonde': {'金色', '金', '金黄', '淡金', '亚麻色', '蜂蜜色'},
        'blue': {'蓝色', '蓝', '湛蓝', '深蓝', '碧蓝', '天蓝', '宝蓝'},
        'green': {'绿色', '绿', '翠绿', '碧绿', '墨绿', '草绿'},
        'purple': {'紫色', '紫', '紫罗兰', '淡紫', '深紫', '葡萄紫'},
        'pink': {'粉色', '粉', '粉红', '桃红', '淡粉'},
        'gray': {'灰色', '灰', '银灰', '铁灰', '烟灰'},
        'orange': {'橙色', '橙', '橘色', '橘红'},
    }
    
    # ========== 关系对立词典 ==========
    RELATIONSHIP_OPPOSITES = {
        '朋友': ['敌人', '仇人', '对手', '死敌'],
        '敌人': ['朋友', '盟友', '同伴', '挚友', '好友'],
        '恋人': ['仇人', '敌人', '陌生人', '前任'],
        '夫妻': ['陌生人', '前夫', '前妻', '离婚'],
        '亲人': ['陌生人', '外人'],
        '主人': ['仆人', '奴隶'],  # 如果A是B的主人，则B不是A的主人
        '同盟': ['敌对', '对立', '敌方'],
        '信任': ['背叛', '欺骗', '不信任'],
    }
    
    # ========== 状态对立词典 ==========
    STATE_OPPOSITES = {
        # 生死状态 (使用标准化值)
        'alive': ['dead'],
        'dead': ['alive'],
        # 婚姻状态
        'single': ['married', 'engaged'],
        'married': ['single', 'divorced', 'widowed'],
        # 健康状态
        'healthy': ['sick', 'injured', 'disabled'],
        'injured': ['healed', 'recovered'],
        # 意识状态
        'awake': ['unconscious', 'asleep'],
        'unconscious': ['awake'],
    }
    
    # 中文状态映射到标准化值
    STATE_NORMALIZATION = {
        # 生死
        '活着': 'alive', '生还': 'alive', '复活': 'alive', '重生': 'alive', '苏醒': 'alive',
        '死亡': 'dead', '死了': 'dead', '去世': 'dead', '身亡': 'dead', 
        '遇难': 'dead', '牺牲': 'dead', '阵亡': 'dead',
        # 婚姻
        '单身': 'single', '未婚': 'single',
        '已婚': 'married', '结婚': 'married', '订婚': 'engaged',
        '离婚': 'divorced', '丧偶': 'widowed',
        # 健康
        '健康': 'healthy', '生病': 'sick', '受伤': 'injured', '残疾': 'disabled',
        '痊愈': 'healed', '康复': 'recovered',
        # 意识
        '清醒': 'awake', '昏迷': 'unconscious', '晕倒': 'unconscious', 
        '睡着': 'asleep', '醒来': 'awake',
    }
    
    def __init__(self, absolute_rules: Optional[List[str]] = None, llm_client = None):
        """初始化一致性检查器
        
        Args:
            absolute_rules: 绝对规则列表，用户定义的必须遵守的规则
            llm_client: LLM客户端，用于语义规则检测（可选，无则回退到关键词检测）
        """
        # ========== 绝对规则（用户自定义）==========
        # 过滤空字符串、纯空白规则，并去重（保持顺序）
        raw_rules = absolute_rules or []
        self.absolute_rules = self._dedupe_rules(raw_rules)
        self._llm_client = llm_client
        
        # ========== 数值属性模式 ==========
        self.number_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(岁|年|天|米|厘米|公里|kg|斤|个|次|%)')
        self.date_pattern = re.compile(r'(\d{4})[年/-](\d{1,2})[月/-]?(\d{1,2})?')
        
        # 中文名字模式（2-4个汉字，或英文名）- 使用非捕获组内置
        # 注意：中文角色名通常2-4字，要避免贪婪匹配
        NAME = r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+(?:\s[A-Za-z]+)?)'
        
        # ========== 扩展的属性提取模式 ==========
        self.attribute_patterns = {
            # 数值属性 - 年龄提取需要更精确的模式
            AttributeType.AGE: [
                (rf'{NAME}(?:今年|现在|已经)?(\d+)岁', 2),  # 小明今年25岁
                (rf'{NAME}的年龄(?:是|为)?(\d+)', 2),      # 小明的年龄是25
                (rf'(\d+)岁的{NAME}', 1),                  # 25岁的小明 -> 小明, 25
            ],
            AttributeType.HEIGHT: [
                (rf'{NAME}(?:的)?身高(?:是|为|有)?(\d+(?:\.\d+)?)\s*(?:cm|厘米)', 2),
                (rf'{NAME}(?:的)?身高(?:是|为|有)?(\d+(?:\.\d+)?)\s*米(?!厘)', 2),
                (rf'身高(\d+(?:\.\d+)?)\s*(?:cm|厘米|m|米)的{NAME}', 1),
            ],
            AttributeType.WEIGHT: [
                (rf'{NAME}(?:的)?体重(?:是|为|有)?(\d+(?:\.\d+)?)\s*(?:kg|公斤)', 2),
                (rf'{NAME}(?:的)?体重(?:是|为|有)?(\d+(?:\.\d+)?)\s*斤', 2),
            ],
            # 外貌属性 - 使用中文名模式
            AttributeType.HAIR_COLOR: [
                (rf'{NAME}的(?:头发|发色|发丝|秀发)(?:是|为)?([\u4e00-\u9fa5]{{1,4}}色?)', 2),
                (rf'{NAME}(?:有|长着|拥有)一头([\u4e00-\u9fa5]{{1,4}}色?)(?:的)?(?:头发|长发|短发|发丝)', 2),
                (rf'([\u4e00-\u9fa5]{{1,4}}色?)(?:头发|发色|长发|短发)的{NAME}', 1),
            ],
            AttributeType.EYE_COLOR: [
                (rf'{NAME}的(?:眼睛|眼眸|眼瞳|瞳孔)(?:是|为)?([\u4e00-\u9fa5]{{1,4}}色?)', 2),
                (rf'{NAME}(?:有|长着)一双([\u4e00-\u9fa5]{{1,4}}色?)(?:的)?(?:眼睛|眼眸)', 2),
                (rf'([\u4e00-\u9fa5]{{1,4}}色?)(?:眼睛|眼眸)的{NAME}', 1),
            ],
            # 固定属性
            AttributeType.BLOOD_TYPE: [
                (rf'{NAME}的血型(?:是|为)?(A|B|AB|O)型?', 2),
                (rf'{NAME}(?:是)?(A|B|AB|O)型血', 2),
            ],
            AttributeType.GENDER: [
                (rf'{NAME}是(?:一个|一名|一位)?(男性|女性|男人|女人|男孩|女孩|男生|女生)', 2),
                (rf'(男性|女性|男人|女人){NAME}', 1),
            ],
            AttributeType.SPECIES: [
                (rf'{NAME}是(?:一个|一名|一只|一头)?(人类|精灵|矮人|兽人|吸血鬼|狼人|龙|恶魔|天使|妖精|人鱼)', 2),
                (rf'(人类|精灵|矮人|兽人|吸血鬼|狼人){NAME}', 1),
            ],
        }
        
        # ========== 状态变化模式 ==========
        self.state_patterns = {
            AttributeType.VITAL_STATUS: [
                (rf'{NAME}(?:已经|已|终于)?(?:死亡|死了|去世|身亡|遇难|牺牲|阵亡)', 'dead'),
                (rf'{NAME}(?:还|仍然)?(?:活着|生还|幸存)', 'alive'),
                (rf'(?:杀死|杀害|消灭)了?{NAME}', 'dead'),
            ],
            AttributeType.MARITAL_STATUS: [
                (rf'{NAME}(?:已经)?(?:结婚|成婚|订婚)', 'married'),
                (rf'{NAME}(?:是|仍是)?单身', 'single'),
                (rf'{NAME}(?:和|与){NAME}(?:结婚|成婚)', 'married'),  # 双方都标记
            ],
        }
        
        # ========== 关系模式 ==========
        self.relationship_patterns = [
            (rf'{NAME}(?:和|与){NAME}(?:是|成为了?|变成了?)([\u4e00-\u9fa5]{{1,4}})', 3),  # A和B是朋友
            (rf'{NAME}(?:是){NAME}的([\u4e00-\u9fa5]{{1,4}})', 3),  # A是B的朋友
            (rf'{NAME}(?:把){NAME}(?:当作|视为|看作)([\u4e00-\u9fa5]{{1,4}})', 3),  # A把B当作朋友
        ]
        
        # ========== 否定句模式 ==========
        self.negation_patterns = [
            (rf'{NAME}(?:不会|不能|无法|从不|绝不|永远不会?)([\u4e00-\u9fa5]{{2,8}})', 'cannot'),
            (rf'{NAME}(?:不是|并非|并不是)([\u4e00-\u9fa5]{{2,8}})', 'is_not'),
            (rf'{NAME}(?:没有|从未|从来没有?)([\u4e00-\u9fa5]{{2,8}})', 'never'),
        ]
        
        # ========== 时间表达模式 ==========
        self.time_patterns = {
            'absolute': [
                (r'(\d{4})年(\d{1,2})月(\d{1,2})日?', 'date'),
                (r'(\d{4})年(\d{1,2})月', 'month'),
                (r'(\d{4})年', 'year'),
            ],
            'relative_past': [
                (r'(\d+)年前', 'years_ago'),
                (r'(\d+)个?月前', 'months_ago'),
                (r'(\d+)天前', 'days_ago'),
                (r'去年', 'last_year'),
                (r'上个?月', 'last_month'),
                (r'昨天', 'yesterday'),
                (r'前天', 'day_before'),
                (r'之前|以前|过去|曾经', 'past'),
            ],
            'relative_future': [
                (r'(\d+)年后', 'years_later'),
                (r'(\d+)个?月后', 'months_later'),
                (r'(\d+)天后', 'days_later'),
                (r'明年', 'next_year'),
                (r'下个?月', 'next_month'),
                (r'明天', 'tomorrow'),
                (r'后天', 'day_after'),
                (r'之后|以后|将来|未来', 'future'),
            ],
            'sequence': [
                (r'在.*之前', 'before'),
                (r'在.*之后', 'after'),
                (r'先.*然后|先.*再', 'then'),
                (r'首先.*接着|首先.*然后', 'sequence'),
            ],
        }
        
        # ========== 缓存 ==========
        # 属性缓存：entity -> {attribute -> [(value, timestamp, source, turn_id)]}
        self.entity_facts: Dict[str, Dict[str, List[Tuple[str, float, str, int]]]] = {}
        # 关系缓存：(entity1, entity2) -> [(relationship, timestamp, source, turn_id)]
        self.relationships: Dict[Tuple[str, str], List[Tuple[str, float, str, int]]] = {}
        # 时间线缓存：entity -> [TimelineEvent]
        self.timelines: Dict[str, List[TimelineEvent]] = {}
        # 否定声明缓存：entity -> {action -> source}
        self.negations: Dict[str, Dict[str, str]] = {}
        # 当前轮次
        self.current_turn: int = 0
    
    def check(self, new_content: str, existing_memories: List[Dict[str, Any]], turn_id: int = 0) -> ConsistencyResult:
        """检查新内容与现有记忆的一致性（增强版）
        
        检测内容：
        1. 数值属性冲突（年龄/身高/体重等）
        2. 外貌属性冲突（发色/眼色等，支持颜色同义词）
        3. 状态冲突（生死/婚姻状态）
        4. 关系冲突（朋友vs敌人等对立关系）
        5. 时间线冲突（事件顺序、年龄一致性）
        6. 否定句违反（声称不会X但做了X）
        """
        self.current_turn = turn_id
        violations = []
        
        # 1. 提取新内容中的各类信息
        new_attributes = self._extract_all_attributes(new_content)
        new_states = self._extract_states(new_content)
        new_relationships = self._extract_relationships(new_content)
        new_negations = self._extract_negations(new_content)
        new_events = self._extract_timeline_events(new_content, turn_id)
        
        # 2. 构建现有记忆的事实库
        # 注意：使用 AttributeType 作为 key，保持类型一致性
        existing_attributes: Dict[str, Dict[AttributeType, List[Tuple[str, str]]]] = {}
        existing_states: Dict[str, Dict[AttributeType, List[Tuple[str, str]]]] = {}
        existing_relationships: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
        existing_negations: Dict[str, Dict[str, str]] = {}
        
        for memory in existing_memories:
            memory_content = memory.get('content', memory.get('text', ''))
            source = memory_content[:50] + '...' if len(memory_content) > 50 else memory_content
            
            # 提取属性
            mem_attrs = self._extract_all_attributes(memory_content)
            for entity, attrs in mem_attrs.items():
                if entity not in existing_attributes:
                    existing_attributes[entity] = {}
                for attr_type, value in attrs.items():
                    if attr_type not in existing_attributes[entity]:
                        existing_attributes[entity][attr_type] = []
                    existing_attributes[entity][attr_type].append((value, source))
            
            # 提取状态
            mem_states = self._extract_states(memory_content)
            for entity, states in mem_states.items():
                if entity not in existing_states:
                    existing_states[entity] = {}
                for state_type, value in states.items():
                    if state_type not in existing_states[entity]:
                        existing_states[entity][state_type] = []
                    existing_states[entity][state_type].append((value, source))
            
            # 提取关系
            mem_rels = self._extract_relationships(memory_content)
            for (e1, e2), rel in mem_rels.items():
                key = (e1, e2)
                if key not in existing_relationships:
                    existing_relationships[key] = []
                existing_relationships[key].append((rel, source))
            
            # 提取否定声明
            mem_negs = self._extract_negations(memory_content)
            for entity, actions in mem_negs.items():
                if entity not in existing_negations:
                    existing_negations[entity] = {}
                existing_negations[entity].update(actions)
        
        # 3. 检测属性冲突
        violations.extend(self._check_attribute_conflicts(
            new_attributes, existing_attributes, new_content
        ))
        
        # 4. 检测状态冲突
        violations.extend(self._check_state_conflicts(
            new_states, existing_states, new_content
        ))
        
        # 5. 检测关系冲突
        violations.extend(self._check_relationship_conflicts(
            new_relationships, existing_relationships, new_content
        ))
        
        # 6. 检测否定句违反
        violations.extend(self._check_negation_violations(
            new_content, existing_negations
        ))
        
        # 7. 检测时间线冲突（完整版）
        violations.extend(self._check_timeline_full(
            new_content, new_events, existing_memories
        ))
        
        # 8. 检测生死矛盾（角色死后不能行动）
        violations.extend(self._check_death_consistency(
            new_content, existing_states
        ))
        
        # 9. 检测绝对规则违反（用户自定义规则）
        violations.extend(self._check_absolute_rules(new_content))
        
        return ConsistencyResult(
            is_consistent=len(violations) == 0,
            violations=violations,
            confidence=max(0.5, 1.0 - len(violations) * 0.1)
        )
    
    # ========== 属性提取方法（分步提取，避免贪婪匹配问题）==========
    
    def _extract_name_from_prefix(self, prefix: str, max_len: int = 4) -> Optional[str]:
        """从前缀中提取名字（取最后2-4个中文字符或完整英文词）
        
        用于处理如 "张三今年" 这样的匹配结果，提取出 "张三"
        """
        if not prefix:
            return None
        
        # 尝试提取中文名字
        chinese_chars = re.findall(r'[\u4e00-\u9fa5]', prefix)
        if chinese_chars:
            # 取最后2-4个字符作为名字
            name_len = min(len(chinese_chars), max_len)
            if name_len >= 2:
                return ''.join(chinese_chars[-name_len:])
        
        # 尝试提取英文名字
        english_match = re.search(r'([A-Za-z]+(?:\s[A-Za-z]+)?)\s*$', prefix)
        if english_match:
            return english_match.group(1)
        
        return None
    
    def _extract_all_attributes(self, text: str) -> Dict[str, Dict[AttributeType, str]]:
        """从文本提取所有类型的属性（增强版，使用分步提取避免贪婪匹配）"""
        results: Dict[str, Dict[AttributeType, str]] = {}
        
        # ========== 年龄提取（分步法）==========
        # 模式1: X今年/现在Y岁
        for match in re.finditer(r'([\u4e00-\u9fa5A-Za-z]+?)(?:今年|现在|已经)(\d+)岁', text):
            name = self._extract_name_from_prefix(match.group(1))
            if name:
                if name not in results:
                    results[name] = {}
                results[name][AttributeType.AGE] = match.group(2)
        
        # 模式2: X的年龄是Y
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)的年龄(?:是|为)?(\d+)', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.AGE] = match.group(2)
        
        # 模式3: Y岁的X
        for match in re.finditer(r'(\d+)岁的([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)', text):
            name = match.group(2)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.AGE] = match.group(1)
        
        # 模式4: X + 数字 + 岁了 （例如: 小明30岁了）
        # 注意: 排除时间词如"今年25岁"，应由模式1处理
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)(\d+)岁了?(?!的)', text):
            name = match.group(1)
            # 排除时间词
            if name in {'今年', '现在', '已经', '去年', '明年'}:
                continue
            # 检查名字是否以时间词结尾（如"小明今年"）
            time_words = ['今年', '现在', '已经', '去年', '明年']
            skip = False
            for tw in time_words:
                if name.endswith(tw):
                    skip = True
                    break
            if skip:
                continue
            if name not in results:
                results[name] = {}
            results[name][AttributeType.AGE] = match.group(2)
        
        # ========== 身高提取 ==========
        # 模式: X的身高是Ycm/米  (注意：名字后面不要包含"的")
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)的身高(?:是|为|有)?(\d+(?:\.\d+)?)\s*(?:cm|厘米|米)', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.HEIGHT] = match.group(2)
        
        # 模式: X身高Ycm (无"的", 使用负向前瞻排除"的")
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)(?<!的)身高(?:是|为|有)?(\d+(?:\.\d+)?)\s*(?:cm|厘米|米)', text):
            name = match.group(1)
            # 确保名字不以"的"结尾
            if name.endswith('的'):
                continue
            if name not in results:
                results[name] = {}
            results[name][AttributeType.HEIGHT] = match.group(2)
        
        # 模式: 身高Ycm的X
        for match in re.finditer(r'身高(\d+(?:\.\d+)?)\s*(?:cm|厘米|米)的([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)', text):
            name = match.group(2)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.HEIGHT] = match.group(1)
        
        # ========== 体重提取 ==========
        # 模式: X的体重是Ykg
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)的体重(?:是|为|有)?(\d+(?:\.\d+)?)\s*(?:kg|公斤|斤)', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.WEIGHT] = match.group(2)
        
        # 模式: X体重Ykg (无"的")
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)体重(?:是|为|有)?(\d+(?:\.\d+)?)\s*(?:kg|公斤|斤)', text):
            name = match.group(1)
            # 确保名字不以"的"结尾
            if name.endswith('的'):
                continue
            if name not in results:
                results[name] = {}
            results[name][AttributeType.WEIGHT] = match.group(2)
        
        # ========== 发色提取 ==========
        # 模式: X有一头Y色的头发
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)(?:有|长着|拥有)一头([\u4e00-\u9fa5]{1,4})(?:色)?(?:的)?(?:头发|长发|短发)', text):
            name = match.group(1)
            color = self._normalize_color(match.group(2))
            if name not in results:
                results[name] = {}
            results[name][AttributeType.HAIR_COLOR] = color
        
        # 模式: X的头发是Y色
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)的(?:头发|发色)(?:是|为)?([\u4e00-\u9fa5]{1,4})(?:色)?', text):
            name = match.group(1)
            color = self._normalize_color(match.group(2))
            if name not in results:
                results[name] = {}
            results[name][AttributeType.HAIR_COLOR] = color
        
        # ========== 眼色提取 ==========
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)(?:有|长着)?一双([\u4e00-\u9fa5]{1,4})(?:色)?(?:的)?(?:眼睛|眼眸)', text):
            name = match.group(1)
            color = self._normalize_color(match.group(2))
            if name not in results:
                results[name] = {}
            results[name][AttributeType.EYE_COLOR] = color
        
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)的(?:眼睛|眼眸|眼瞳)(?:是|为)?([\u4e00-\u9fa5]{1,4})(?:色)?', text):
            name = match.group(1)
            color = self._normalize_color(match.group(2))
            if name not in results:
                results[name] = {}
            results[name][AttributeType.EYE_COLOR] = color
        
        # ========== 血型提取 ==========
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)(?:的)?血型(?:是|为)?(A|B|AB|O)型?', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.BLOOD_TYPE] = match.group(2)
        
        # ========== 性别提取 ==========
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)是(?:一个|一名|一位)?(男性|女性|男人|女人|男孩|女孩|男生|女生)', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.GENDER] = match.group(2)
        
        # ========== 种族提取 ==========
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4}|[A-Za-z]+)是(?:一个|一名|一只|一头)?(人类|精灵|矮人|兽人|吸血鬼|狼人|龙|恶魔|天使|妖精|人鱼)', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.SPECIES] = match.group(2)
        
        return results
    
    def _normalize_color(self, color: str) -> str:
        """颜色标准化（合并同义词）"""
        color = color.lower().strip()
        for standard, synonyms in self.COLOR_SYNONYMS.items():
            if color in synonyms or any(syn in color for syn in synonyms):
                return standard
        return color
    
    def _extract_states(self, text: str) -> Dict[str, Dict[AttributeType, str]]:
        """提取状态信息（生死、婚姻等）- 使用分步提取"""
        results: Dict[str, Dict[AttributeType, str]] = {}
        
        # 名字提取辅助：排除常见状态词
        exclude_words = {'已经', '已', '终于', '不', '还', '仍然', '是', '仍是'}
        
        def clean_name(raw_name: str) -> str:
            """清理名字，移除状态词后缀"""
            for word in exclude_words:
                if raw_name.endswith(word):
                    raw_name = raw_name[:-len(word)]
            return raw_name if len(raw_name) >= 2 else ""
        
        # ========== 生死状态 ==========
        # 死亡模式 - 使用更精确的边界
        death_patterns = [
            r'([\u4e00-\u9fa5]{2,4}?)(?:已经|已|终于)(?:死亡|死了|去世|身亡|遇难|牺牲|阵亡)',
            r'([\u4e00-\u9fa5]{2,4})(?:死亡|死了|去世|身亡|遇难|牺牲|阵亡)',
            r'(?:杀死|杀害|消灭)了?([\u4e00-\u9fa5]{2,4})',
        ]
        for pattern in death_patterns:
            for match in re.finditer(pattern, text):
                name = clean_name(match.group(1))
                if name and len(name) >= 2:
                    if name not in results:
                        results[name] = {}
                    results[name][AttributeType.VITAL_STATUS] = 'dead'
        
        # 存活模式
        alive_patterns = [
            r'([\u4e00-\u9fa5]{2,4}?)(?:还|仍然)(?:活着|生还|幸存)',
            r'([\u4e00-\u9fa5]{2,4})(?:活着|生还|幸存)',
        ]
        for pattern in alive_patterns:
            for match in re.finditer(pattern, text):
                name = clean_name(match.group(1))
                if name and len(name) >= 2:
                    if name not in results:
                        results[name] = {}
                    results[name][AttributeType.VITAL_STATUS] = 'alive'
        
        # ========== 婚姻状态 ==========
        # 已婚
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4})(?:已经)?(?:结婚|成婚|订婚)', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.MARITAL_STATUS] = 'married'
        
        # 双人结婚
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4})(?:和|与)([\u4e00-\u9fa5]{2,4})(?:结婚|成婚)', text):
            for name in [match.group(1), match.group(2)]:
                if name not in results:
                    results[name] = {}
                results[name][AttributeType.MARITAL_STATUS] = 'married'
        
        # 单身
        for match in re.finditer(r'([\u4e00-\u9fa5]{2,4})(?:是|仍是)?单身', text):
            name = match.group(1)
            if name not in results:
                results[name] = {}
            results[name][AttributeType.MARITAL_STATUS] = 'single'
        
        return results
    
    def _extract_relationships(self, text: str) -> Dict[Tuple[str, str], str]:
        """提取关系信息"""
        results: Dict[Tuple[str, str], str] = {}
        
        for pattern, rel_group in self.relationship_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) >= 3:
                    e1, e2, relationship = match[0].strip(), match[1].strip(), match[2].strip()
                    # 双向存储
                    results[(e1, e2)] = relationship
                    results[(e2, e1)] = relationship
        
        return results
    
    def _extract_negations(self, text: str) -> Dict[str, Dict[str, str]]:
        """提取否定声明（不会/不能/从不）"""
        results: Dict[str, Dict[str, str]] = {}
        
        for pattern, neg_type in self.negation_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    entity, action = match[0].strip(), match[1].strip()
                    if entity not in results:
                        results[entity] = {}
                    results[entity][action] = f"{neg_type}:{text[:50]}"
        
        return results
    
    def _extract_timeline_events(self, text: str, turn_id: int) -> List[TimelineEvent]:
        """提取时间线事件"""
        events = []
        
        # 提取死亡事件
        death_patterns = [
            (r'(\w{1,10})(?:已经|已)?(?:死亡|死了|去世|身亡|遇难|牺牲)', 'death'),
            (r'(?:杀死|杀害|消灭)了?(\w{1,10})', 'death'),
        ]
        
        for pattern, event_type in death_patterns:
            matches = re.findall(pattern, text)
            for entity in matches:
                events.append(TimelineEvent(
                    entity=entity.strip(),
                    event_type=event_type,
                    description=f"{entity}死亡",
                    source=text[:100],
                    turn_id=turn_id
                ))
        
        # 提取出生/年龄声明（用于年龄一致性检查）
        age_patterns = [
            (r'(\w{1,10})(?:今年|现在)?(\d+)岁', 'age_declaration'),
            (r'(\d+)年前.*(\w{1,10})(\d+)岁', 'past_age'),  # N年前X是M岁
        ]
        
        for pattern, event_type in age_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if event_type == 'age_declaration' and len(match) >= 2:
                    events.append(TimelineEvent(
                        entity=match[0].strip(),
                        event_type='age',
                        description=f"年龄:{match[1]}",
                        source=text[:100],
                        turn_id=turn_id
                    ))
        
        return events
    
    # ========== 冲突检测方法 ==========
    
    def _check_attribute_conflicts(
        self,
        new_attrs: Dict[str, Dict[AttributeType, str]],
        existing_attrs: Dict[str, Dict[AttributeType, List[Tuple[str, str]]]],
        new_content: str
    ) -> List[Violation]:
        """检测属性冲突（支持颜色同义词合并）"""
        violations = []
        
        for entity, attrs in new_attrs.items():
            if entity not in existing_attrs:
                continue
            
            for attr_type, new_value in attrs.items():
                if attr_type not in existing_attrs[entity]:
                    continue
                
                attr_name = attr_type.value if isinstance(attr_type, AttributeType) else str(attr_type)
                
                for old_value, source in existing_attrs[entity][attr_type]:
                    # 颜色类属性使用标准化比较
                    if attr_type in [AttributeType.HAIR_COLOR, AttributeType.EYE_COLOR, AttributeType.SKIN_COLOR]:
                        new_normalized = self._normalize_color(new_value)
                        old_normalized = self._normalize_color(old_value)
                        if new_normalized != old_normalized:
                            violations.append(Violation(
                                type=ViolationType.CHARACTER_CONFLICT,
                                description=f"【{entity}】的{attr_name}存在冲突：新值'{new_value}'({new_normalized}) vs 旧值'{old_value}'({old_normalized})",
                                evidence=[new_content[:100], source],
                                severity=0.8,
                                suggested_resolution=f"确认{entity}的{attr_name}应该是{new_value}还是{old_value}"
                            ))
                    else:
                        # 其他属性直接比较
                        if new_value != old_value:
                            violations.append(Violation(
                                type=ViolationType.FACT_CONFLICT,
                                description=f"【{entity}】的{attr_name}存在冲突：新值'{new_value}' vs 旧值'{old_value}'",
                                evidence=[new_content[:100], source],
                                severity=0.7,
                                suggested_resolution=f"确认{entity}的{attr_name}应该是{new_value}还是{old_value}"
                            ))
        
        return violations
    
    def _check_state_conflicts(
        self,
        new_states: Dict[str, Dict[AttributeType, str]],
        existing_states: Dict[str, Dict[AttributeType, List[Tuple[str, str]]]],
        new_content: str
    ) -> List[Violation]:
        """检测状态冲突（生死、婚姻等）"""
        violations = []
        
        for entity, states in new_states.items():
            if entity not in existing_states:
                continue
            
            for state_type, new_value in states.items():
                if state_type not in existing_states[entity]:
                    continue
                
                state_name = state_type.value if isinstance(state_type, AttributeType) else str(state_type)
                
                for old_value, source in existing_states[entity][state_type]:
                    # 检查是否是对立状态
                    if self._are_opposite_states(old_value, new_value):
                        violations.append(Violation(
                            type=ViolationType.STATE_CONFLICT,
                            description=f"【{entity}】状态冲突：之前'{old_value}' → 现在'{new_value}'",
                            evidence=[new_content[:100], source],
                            severity=0.9,
                            suggested_resolution=f"请确认{entity}的状态变化是否有合理解释（如复活情节）"
                        ))
        
        return violations
    
    def _are_opposite_states(self, state1: str, state2: str) -> bool:
        """检查两个状态是否对立"""
        for key, opposites in self.STATE_OPPOSITES.items():
            if state1 == key or state1 in opposites:
                if state2 in opposites or state2 == key:
                    if state1 != state2:
                        return True
        return False
    
    def _check_relationship_conflicts(
        self,
        new_rels: Dict[Tuple[str, str], str],
        existing_rels: Dict[Tuple[str, str], List[Tuple[str, str]]],
        new_content: str
    ) -> List[Violation]:
        """检测关系冲突（朋友vs敌人等）"""
        violations = []
        
        for (e1, e2), new_rel in new_rels.items():
            if (e1, e2) not in existing_rels:
                continue
            
            for old_rel, source in existing_rels[(e1, e2)]:
                # 检查是否是对立关系
                if self._are_opposite_relationships(old_rel, new_rel):
                    violations.append(Violation(
                        type=ViolationType.RELATIONSHIP_CONFLICT,
                        description=f"【{e1}】和【{e2}】的关系冲突：之前'{old_rel}' → 现在'{new_rel}'",
                        evidence=[new_content[:100], source],
                        severity=0.75,
                        suggested_resolution=f"请确认{e1}和{e2}的关系变化是否有情节支持"
                    ))
        
        return violations
    
    def _are_opposite_relationships(self, rel1: str, rel2: str) -> bool:
        """检查两个关系是否对立"""
        for key, opposites in self.RELATIONSHIP_OPPOSITES.items():
            if key in rel1 or rel1 in [key]:
                if any(opp in rel2 for opp in opposites):
                    return True
            if key in rel2 or rel2 in [key]:
                if any(opp in rel1 for opp in opposites):
                    return True
        return False
    
    def _check_negation_violations(
        self,
        new_content: str,
        existing_negations: Dict[str, Dict[str, str]]
    ) -> List[Violation]:
        """检测否定句违反（声称不会X但做了X）"""
        violations = []
        
        # 提取新内容中的动作
        action_patterns = [
            (r'(\w{1,10})(?:开始|正在)?(\S{2,6})(?:了|着|过)', 'did'),  # X做了Y
            (r'(\w{1,10})(\S{2,6})了(\S+)', 'did'),  # X杀了Y
        ]
        
        for pattern, _ in action_patterns:
            matches = re.findall(pattern, new_content)
            for match in matches:
                entity = match[0].strip()
                action = match[1].strip() if len(match) > 1 else ""
                
                if entity in existing_negations:
                    for negated_action, source in existing_negations[entity].items():
                        # 检查动作是否匹配否定声明
                        if self._action_matches_negation(action, negated_action):
                            violations.append(Violation(
                                type=ViolationType.LOGIC_ERROR,
                                description=f"【{entity}】违反了之前的声明：曾说'{negated_action}'，现在却'{action}'",
                                evidence=[new_content[:100], source],
                                severity=0.85,
                                suggested_resolution=f"请确认{entity}的行为是否有特殊原因"
                            ))
        
        return violations
    
    def _action_matches_negation(self, action: str, negated_action: str) -> bool:
        """检查动作是否与否定声明冲突"""
        # 简单匹配：动作包含否定声明中的关键词
        if len(action) < 2 or len(negated_action) < 2:
            return False
        return action in negated_action or negated_action in action
    
    # ========== 时间线检测方法（完整版）==========
    
    def _check_timeline_full(
        self,
        new_content: str,
        new_events: List[TimelineEvent],
        existing_memories: List[Dict[str, Any]]
    ) -> List[Violation]:
        """完整版时间线检查
        
        检测内容：
        1. 时态冲突（同一事件的过去/将来描述冲突）
        2. 年龄一致性（N年前X岁 → 现在应该X+N岁）
        3. 事件顺序（声称A在B之前，但描述顺序相反）
        4. 日期矛盾（具体日期的冲突）
        """
        violations = []
        
        # 1. 时态冲突检测
        violations.extend(self._check_tense_conflicts(new_content, existing_memories))
        
        # 2. 年龄一致性检测
        violations.extend(self._check_age_consistency(new_content, existing_memories))
        
        # 3. 事件顺序检测
        violations.extend(self._check_event_sequence(new_content, existing_memories))
        
        return violations
    
    def _check_tense_conflicts(
        self,
        new_content: str,
        existing_memories: List[Dict[str, Any]]
    ) -> List[Violation]:
        """检测时态冲突"""
        violations = []
        
        # 提取新内容的时间表达
        new_dates = self.date_pattern.findall(new_content)
        past_indicators = ['之前', '以前', '去年', '上个月', '昨天', '曾经', '年前', '月前', '天前']
        future_indicators = ['之后', '以后', '明年', '下个月', '明天', '将来', '年后', '月后', '天后']
        
        new_has_past = any(ind in new_content for ind in past_indicators)
        new_has_future = any(ind in new_content for ind in future_indicators)
        
        for memory in existing_memories:
            memory_content = memory.get('content', memory.get('text', ''))
            memory_dates = self.date_pattern.findall(memory_content)
            
            if not memory_dates and not new_dates:
                continue
            
            mem_has_past = any(ind in memory_content for ind in past_indicators)
            mem_has_future = any(ind in memory_content for ind in future_indicators)
            
            # 检测具体日期的时态冲突
            for new_date in new_dates:
                for mem_date in memory_dates:
                    if new_date == mem_date:
                        if (new_has_past and mem_has_future) or (new_has_future and mem_has_past):
                            violations.append(Violation(
                                type=ViolationType.TIMELINE_CONFLICT,
                                description=f"时间线冲突：日期 {'-'.join(filter(None, new_date))} 的时态描述矛盾",
                                evidence=[new_content[:100], memory_content[:100]],
                                severity=0.6,
                                suggested_resolution="请确认该日期是过去还是将来"
                            ))
        
        return violations
    
    def _check_age_consistency(
        self,
        new_content: str,
        existing_memories: List[Dict[str, Any]]
    ) -> List[Violation]:
        """检测年龄一致性
        
        规则：
        - 如果之前说"N年前X是M岁"，现在X应该是M+N岁
        - 如果之前说"X今年M岁"，后面再说"X今年K岁"且K≠M，则冲突
        """
        violations = []
        
        # 提取新内容中的年龄声明
        current_age_pattern = r'(\w{1,10})(?:今年|现在)?(\d+)岁'
        past_age_pattern = r'(\d+)年前.*?(\w{1,10}).*?(\d+)岁'
        
        new_ages = {}
        for match in re.findall(current_age_pattern, new_content):
            entity, age = match[0].strip(), int(match[1])
            new_ages[entity] = age
        
        # 检查与历史记录的一致性
        for memory in existing_memories:
            memory_content = memory.get('content', memory.get('text', ''))
            
            # 检查历史年龄声明
            for match in re.findall(current_age_pattern, memory_content):
                entity, old_age = match[0].strip(), int(match[1])
                if entity in new_ages and new_ages[entity] != old_age:
                    # 允许1岁的差异（可能是生日经过）
                    age_diff = abs(new_ages[entity] - old_age)
                    if age_diff > 1:
                        violations.append(Violation(
                            type=ViolationType.AGE_INCONSISTENCY,
                            description=f"【{entity}】的年龄不一致：之前'{old_age}岁' → 现在'{new_ages[entity]}岁'（差{age_diff}岁）",
                            evidence=[new_content[:100], memory_content[:100]],
                            severity=0.7,
                            suggested_resolution=f"请确认{entity}的实际年龄，或说明时间流逝"
                        ))
            
            # 检查"N年前M岁"的推算
            for match in re.findall(past_age_pattern, memory_content):
                years_ago, entity, past_age = int(match[0]), match[1].strip(), int(match[2])
                expected_current_age = past_age + years_ago
                
                if entity in new_ages:
                    actual_age = new_ages[entity]
                    # 允许2岁的误差
                    if abs(actual_age - expected_current_age) > 2:
                        violations.append(Violation(
                            type=ViolationType.AGE_INCONSISTENCY,
                            description=f"【{entity}】年龄推算不一致：{years_ago}年前{past_age}岁 → 现在应该约{expected_current_age}岁，但实际是{actual_age}岁",
                            evidence=[new_content[:100], memory_content[:100]],
                            severity=0.65,
                            suggested_resolution=f"请确认时间线或{entity}的年龄"
                        ))
        
        return violations
    
    def _check_event_sequence(
        self,
        new_content: str,
        existing_memories: List[Dict[str, Any]]
    ) -> List[Violation]:
        """检测事件顺序冲突"""
        violations = []
        
        # 提取"在X之前/之后"的表述
        sequence_pattern = r'在(.{2,20})(之前|之后).*?(.{2,20})'
        
        for match in re.findall(sequence_pattern, new_content):
            event_a, relation, event_b = match[0], match[1], match[2]
            
            # 在历史记录中查找相反的顺序声明
            for memory in existing_memories:
                memory_content = memory.get('content', memory.get('text', ''))
                
                # 检查是否有相反的顺序声明
                opposite_relation = '之后' if relation == '之前' else '之前'
                reverse_pattern = rf'在{re.escape(event_b)}.*?{opposite_relation}.*?{re.escape(event_a)}'
                
                if re.search(reverse_pattern, memory_content):
                    violations.append(Violation(
                        type=ViolationType.TIMELINE_CONFLICT,
                        description=f"事件顺序冲突：新内容说'{event_a}在{event_b}{relation}'，但之前说的是相反顺序",
                        evidence=[new_content[:100], memory_content[:100]],
                        severity=0.7,
                        suggested_resolution="请确认事件的实际发生顺序"
                    ))
        
        return violations
    
    def _check_death_consistency(
        self,
        new_content: str,
        existing_states: Dict[str, Dict[str, List[Tuple[str, str]]]]
    ) -> List[Violation]:
        """检测生死矛盾（角色死后不能行动）"""
        violations = []
        
        # 找出已知死亡的角色
        dead_entities = set()
        for entity, states in existing_states.items():
            vital_key = AttributeType.VITAL_STATUS.value
            if vital_key in states:
                for value, _ in states[vital_key]:
                    if value == 'dead':
                        dead_entities.add(entity)
        
        # 检查新内容中死亡角色是否有行动
        action_patterns = [
            r'(\w{1,10})(?:说|说道|问|回答|走|跑|站|坐|笑|哭|看|听|想|做|拿|给|打|杀|吃|喝)',
            r'(\w{1,10})的(?:声音|脚步|身影|笑声)',
        ]
        
        for pattern in action_patterns:
            matches = re.findall(pattern, new_content)
            for entity in matches:
                entity = entity.strip()
                if entity in dead_entities:
                    # 检查是否是回忆/闪回场景
                    flashback_indicators = ['回忆', '想起', '记得', '曾经', '以前', '那时', '生前']
                    is_flashback = any(ind in new_content for ind in flashback_indicators)
                    
                    if not is_flashback:
                        violations.append(Violation(
                            type=ViolationType.LOGIC_ERROR,
                            description=f"【{entity}】已死亡，但仍在行动",
                            evidence=[new_content[:100], f"{entity}之前被记录为死亡"],
                            severity=0.95,
                            suggested_resolution=f"如果是回忆场景请明确说明，否则请确认{entity}是否复活"
                        ))
        
        return violations
    
    # ========== 兼容旧接口 ==========
    
    def _extract_facts(self, text: str) -> Dict[str, Dict[str, str]]:
        """从文本中提取事实（兼容旧接口）"""
        attrs = self._extract_all_attributes(text)
        facts: Dict[str, Dict[str, str]] = {}
        for entity, attr_dict in attrs.items():
            facts[entity] = {
                attr_type.value if isinstance(attr_type, AttributeType) else str(attr_type): value
                for attr_type, value in attr_dict.items()
            }
        return facts
    
    def _check_timeline(
        self,
        new_content: str,
        existing_memories: List[Dict[str, Any]]
    ) -> List[Violation]:
        """检查时间线一致性（兼容旧接口，调用完整版）"""
        new_events = self._extract_timeline_events(new_content, self.current_turn)
        return self._check_timeline_full(new_content, new_events, existing_memories)
    
    def record_fact(
        self,
        entity: str,
        attribute: str,
        value: str,
        source: str,
        turn_id: int = 0
    ):
        """记录事实到缓存"""
        if entity not in self.entity_facts:
            self.entity_facts[entity] = {}
        if attribute not in self.entity_facts[entity]:
            self.entity_facts[entity][attribute] = []
        
        self.entity_facts[entity][attribute].append((value, time.time(), source, turn_id))
    
    def record_relationship(
        self,
        entity1: str,
        entity2: str,
        relationship: str,
        source: str,
        turn_id: int = 0
    ):
        """记录关系到缓存"""
        key = (entity1, entity2)
        if key not in self.relationships:
            self.relationships[key] = []
        self.relationships[key].append((relationship, time.time(), source, turn_id))
        
        # 双向存储
        key_reverse = (entity2, entity1)
        if key_reverse not in self.relationships:
            self.relationships[key_reverse] = []
        self.relationships[key_reverse].append((relationship, time.time(), source, turn_id))
    
    def record_state(
        self,
        entity: str,
        state_type: str,
        value: str,
        source: str,
        turn_id: int = 0
    ):
        """记录状态到缓存"""
        if entity not in self.entity_facts:
            self.entity_facts[entity] = {}
        if state_type not in self.entity_facts[entity]:
            self.entity_facts[entity][state_type] = []
        
        self.entity_facts[entity][state_type].append((value, time.time(), source, turn_id))
    
    def record_negation(
        self,
        entity: str,
        action: str,
        source: str
    ):
        """记录否定声明"""
        if entity not in self.negations:
            self.negations[entity] = {}
        self.negations[entity][action] = source
    
    def get_conflicts(self, entity: str) -> List[str]:
        """获取某实体的冲突"""
        if entity not in self.entity_facts:
            return []
        
        conflicts = []
        for attr, values in self.entity_facts[entity].items():
            if len(values) > 1:
                unique_values = set(v[0] for v in values)
                if len(unique_values) > 1:
                    conflicts.append(f"{attr}: {unique_values}")
        
        return conflicts
    
    def get_entity_profile(self, entity: str) -> Dict[str, Any]:
        """获取实体的完整档案"""
        profile = {
            'entity': entity,
            'attributes': {},
            'states': {},
            'relationships': [],
            'negations': [],
            'conflicts': []
        }
        
        # 属性
        if entity in self.entity_facts:
            for attr, values in self.entity_facts[entity].items():
                if values:
                    # 取最新的值
                    latest = max(values, key=lambda x: x[1])
                    profile['attributes'][attr] = latest[0]
                    
                    # 检查冲突
                    unique_values = set(v[0] for v in values)
                    if len(unique_values) > 1:
                        profile['conflicts'].append({
                            'attribute': attr,
                            'values': list(unique_values)
                        })
        
        # 关系
        for (e1, e2), rels in self.relationships.items():
            if e1 == entity and rels:
                latest = max(rels, key=lambda x: x[1])
                profile['relationships'].append({
                    'target': e2,
                    'relationship': latest[0]
                })
        
        # 否定声明
        if entity in self.negations:
            profile['negations'] = list(self.negations[entity].keys())
        
        return profile
    
    def get_summary(self) -> Dict[str, Any]:
        """获取一致性检查摘要"""
        total_entities = len(self.entity_facts)
        entities_with_conflicts = 0
        total_conflicts = 0
        
        for entity, attrs in self.entity_facts.items():
            has_conflict = False
            for attr, values in attrs.items():
                unique_values = set(v[0] for v in values)
                if len(unique_values) > 1:
                    has_conflict = True
                    total_conflicts += 1
            if has_conflict:
                entities_with_conflicts += 1
        
        return {
            'total_entities': total_entities,
            'entities_with_conflicts': entities_with_conflicts,
            'total_conflicts': total_conflicts,
            'total_relationships': len(self.relationships) // 2,  # 双向存储，除以2
            'total_negations': sum(len(v) for v in self.negations.values()),
            'health_score': 1.0 - (entities_with_conflicts / max(total_entities, 1)),
            'absolute_rules_count': len(self.absolute_rules),
            'capabilities': [
                '数值属性检测 (年龄/身高/体重)',
                '外貌属性检测 (发色/眼色/肤色)',
                '状态冲突检测 (生死/婚姻)',
                '关系冲突检测 (朋友vs敌人)',
                '时间线检测 (年龄一致性/事件顺序)',
                '否定句违反检测 (不会X但做了X)',
                '生死矛盾检测 (死后行动)',
                '绝对规则检测 (LLM语义理解)',
            ]
        }

    # ========== 绝对规则检测（LLM语义理解）==========
    
    def set_llm_client(self, llm_client) -> None:
        """设置LLM客户端用于规则检测
        
        Args:
            llm_client: LLMClient实例
        """
        self._llm_client = llm_client
        print(f"[ConsistencyChecker] LLM客户端已设置，绝对规则检测已启用")
    
    def _check_absolute_rules(self, content: str) -> List[Violation]:
        """使用LLM检测内容是否违反绝对规则
        
        这是真正的语义理解检测，支持任意复杂的自然语言规则。
        """
        # 没有规则或没有LLM客户端，跳过
        if not self.absolute_rules:
            return []
        
        if not hasattr(self, '_llm_client') or self._llm_client is None:
            # 没有LLM客户端，回退到简单的关键词检测（作为兜底）
            return self._check_absolute_rules_fallback(content)
        
        try:
            return self._check_rules_with_llm(content)
        except Exception as e:
            print(f"[ConsistencyChecker] LLM规则检测失败: {e}，回退到关键词检测")
            return self._check_absolute_rules_fallback(content)
    
    def _check_rules_with_llm(self, content: str) -> List[Violation]:
        """使用LLM进行语义规则检测"""
        violations = []
        
        # 构建规则列表文本
        rules_text = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(self.absolute_rules)])
        
        prompt = f"""你是一个严格的规则检查器。请检查以下内容是否违反了任何规则。

## 规则列表（用户定义的绝对规则，必须严格遵守）：
{rules_text}

## 待检查内容：
{content[:2000]}

## 检查要求：
1. 仔细理解每条规则的含义（可能是一长段描述）
2. 判断内容是否违反了任何规则
3. 考虑语义等价（如"发火"="生气"="愤怒"）
4. 考虑隐含违反（如规则是"角色温柔"，内容是"她狠狠地踢了他一脚"就是违反）

## 输出格式（严格遵守）：
如果没有违反任何规则，只输出：
PASS

如果违反了规则，按以下格式输出（每个违反一行）：
VIOLATION|规则编号|违反说明

示例输出：
VIOLATION|1|内容中角色表现出愤怒情绪，违反了"角色从不发火"的规则
VIOLATION|3|内容中出现了脏话"XXX"，违反了禁止脏话的规则

请开始检查："""

        try:
            response = self._llm_client.complete(
                prompt=prompt,
                max_tokens=500,
                temperature=0.1  # 低温度保证一致性
            )
            
            # 解析响应
            response_text = response.strip()
            
            if response_text == "PASS" or response_text.startswith("PASS"):
                return []
            
            # 解析违规
            for line in response_text.split('\n'):
                line = line.strip()
                if line.startswith('VIOLATION|'):
                    parts = line.split('|', 2)
                    if len(parts) >= 3:
                        try:
                            rule_num = int(parts[1]) - 1
                            description = parts[2]
                            rule_text = self.absolute_rules[rule_num] if 0 <= rule_num < len(self.absolute_rules) else "未知规则"
                            
                            violations.append(Violation(
                                type=ViolationType.LOGIC_ERROR,
                                description=f"违反规则「{rule_text[:50]}{'...' if len(rule_text) > 50 else ''}」：{description}",
                                evidence=[content[:200]],
                                severity=0.9,
                                suggested_resolution=f"请修改内容以符合规则"
                            ))
                        except (ValueError, IndexError):
                            continue
            
            return violations
            
        except Exception as e:
            print(f"[ConsistencyChecker] LLM调用失败: {e}")
            return []
    
    def _check_absolute_rules_fallback(self, content: str) -> List[Violation]:
        """无 LLM 时的回退处理
        
        由于用户定义的绝对规则通常是复杂的自然语言描述（如"角色性格温柔"、
        "故事背景是古代"），简单的关键词匹配无法准确检测。
        
        因此，当没有 LLM 时，我们只返回一个提示性警告，建议用户配置 LLM。
        """
        # 如果有规则但没有 LLM，首次调用时提示一次
        if self.absolute_rules and not hasattr(self, '_fallback_warned'):
            self._fallback_warned = True
            print(f"[ConsistencyChecker] ⚠️ 检测到 {len(self.absolute_rules)} 条绝对规则，但未配置 LLM")
            print(f"[ConsistencyChecker]    绝对规则需要语义理解才能准确检测")
            print(f"[ConsistencyChecker]    建议在 api_keys.env 中配置 LLM_API_KEY 以启用语义检测")
        
        # 不做误导性的关键词检测，直接返回空
        # 用户自定义的规则（如"角色温柔"）无法通过关键词匹配
        return []
    
    def update_rules(self, rules: List[str]) -> None:
        """更新绝对规则（运行时更新）"""
        # 过滤空字符串、纯空白规则，并去重
        self.absolute_rules = self._dedupe_rules(rules)
        llm_status = "LLM语义检测" if self._llm_client else "⚠️ 无LLM（规则检测未生效）"
        print(f"[ConsistencyChecker] 已更新 {len(self.absolute_rules)} 条绝对规则（{llm_status}）")
    
    def _dedupe_rules(self, rules: List[str]) -> List[str]:
        """去重规则列表，保持顺序"""
        seen = set()
        result = []
        for r in rules:
            if not r or not r.strip():
                continue
            normalized = r.strip()
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
