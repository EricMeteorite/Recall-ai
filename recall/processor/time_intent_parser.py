"""时间意图解析器 - Recall 7.3 Phase A

混合策略: 正则优先 → LLM 兜底
- Layer 1: 正则匹配 (<1ms) — 覆盖 90% 常见时间表达式
  * 中文: 昨天/上周/过去N天/这个月/去年/前天/大前天
  * 英文: yesterday/last week/past N days/this month/3 days ago
  * ISO: YYYY-MM-DD..YYYY-MM-DD 或 YYYY-MM-DD to YYYY-MM-DD
  * 相对: N天前/N hours ago/N周前/N months ago
- Layer 2: LLM 兜底 (~300ms) — 处理复杂/模糊表达
"""

from __future__ import annotations

import re
import logging
import threading
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


# Windows GBK 编码兼容的安全打印函数
def _safe_print(msg: str) -> None:
    """安全打印函数，替换 emoji 为 ASCII 等价物以避免 Windows GBK 编码错误"""
    emoji_map = {
        '📥': '[IN]', '📤': '[OUT]', '🔍': '[SEARCH]', '✅': '[OK]', '❌': '[FAIL]',
        '⚠️': '[WARN]', '💾': '[SAVE]', '🗃️': '[DB]', '🧹': '[CLEAN]', '📊': '[STATS]',
        '🔄': '[SYNC]', '📦': '[PKG]', '🚀': '[START]', '🎯': '[TARGET]', '💡': '[HINT]',
        '🔧': '[FIX]', '📝': '[NOTE]', '🎉': '[DONE]', '⏱️': '[TIME]', '🌐': '[NET]',
        '🧠': '[BRAIN]', '💬': '[CHAT]', '🏷️': '[TAG]', '📁': '[DIR]', '🔒': '[LOCK]',
        '🌱': '[PLANT]', '🗑️': '[DEL]', '💫': '[MAGIC]', '🎭': '[MASK]', '📖': '[BOOK]',
        '⚡': '[FAST]', '🔥': '[HOT]', '💎': '[GEM]', '🌟': '[STAR]', '🎨': '[ART]'
    }
    for emoji, ascii_equiv in emoji_map.items():
        msg = msg.replace(emoji, ascii_equiv)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


# ==================== 数据类 ====================

@dataclass
class TimeRange:
    """时间范围结果"""
    start: datetime
    end: datetime
    confidence: float = 1.0           # 置信度 (0-1)
    source: str = "regex"             # 来源: 'regex' 或 'llm'
    matched_text: str = ""            # 匹配到的原文片段
    pattern_name: str = ""            # 匹配到的模式名称

    def duration_seconds(self) -> float:
        """返回时间范围的持续秒数"""
        return (self.end - self.start).total_seconds()

    def contains(self, dt: datetime) -> bool:
        """判断某个时间点是否在范围内"""
        return self.start <= dt <= self.end

    def overlaps(self, other: 'TimeRange') -> bool:
        """判断两个时间范围是否有重叠"""
        return self.start <= other.end and other.start <= self.end

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典"""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "confidence": self.confidence,
            "source": self.source,
            "matched_text": self.matched_text,
            "pattern_name": self.pattern_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeRange':
        """从字典恢复"""
        return cls(
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            confidence=data.get("confidence", 1.0),
            source=data.get("source", "regex"),
            matched_text=data.get("matched_text", ""),
            pattern_name=data.get("pattern_name", ""),
        )


# ==================== 辅助函数 ====================

def _start_of_day(dt: datetime) -> datetime:
    """返回当天 00:00:00"""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_day(dt: datetime) -> datetime:
    """返回当天 23:59:59"""
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def _start_of_week(dt: datetime) -> datetime:
    """返回本周一 00:00:00 (ISO 周一为周首)"""
    days_since_monday = dt.weekday()  # 0=Monday
    monday = dt - timedelta(days=days_since_monday)
    return _start_of_day(monday)


def _end_of_week(dt: datetime) -> datetime:
    """返回本周日 23:59:59"""
    days_until_sunday = 6 - dt.weekday()
    sunday = dt + timedelta(days=days_until_sunday)
    return _end_of_day(sunday)


def _start_of_month(dt: datetime) -> datetime:
    """返回本月 1 日 00:00:00"""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _end_of_month(dt: datetime) -> datetime:
    """返回本月最后一天 23:59:59"""
    import calendar
    last_day = calendar.monthrange(dt.year, dt.month)[1]
    return dt.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)


def _start_of_year(dt: datetime) -> datetime:
    """返回本年 1 月 1 日 00:00:00"""
    return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def _end_of_year(dt: datetime) -> datetime:
    """返回本年 12 月 31 日 23:59:59"""
    return dt.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)


# 中文数字到阿拉伯数字映射
_CN_NUM_MAP: Dict[str, int] = {
    '零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '百': 100, '千': 1000, '万': 10000,
}


def _cn_to_int(cn_str: str) -> int:
    """将中文数字字符串转换为整数（支持到万位）。
    
    Examples:
        '三' -> 3, '十二' -> 12, '二十' -> 20, '一百二十三' -> 123
    """
    if not cn_str:
        return 0

    # 如果已经是阿拉伯数字
    if cn_str.isdigit():
        return int(cn_str)

    result = 0
    current = 0
    for char in cn_str:
        val = _CN_NUM_MAP.get(char, None)
        if val is None:
            continue
        if val >= 10:
            if current == 0:
                current = 1
            result += current * val
            current = 0
        else:
            current = val
    result += current
    return result if result > 0 else 0


# ==================== 正则模式 ====================

class _RegexPatterns:
    """编译好的正则模式集合（线程安全、一次性编译）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._compiled = False
        self.patterns: List[Tuple[str, re.Pattern, str]] = []  # (name, pattern, category)

    def ensure_compiled(self):
        """确保所有模式已编译（双重检查锁定）"""
        if self._compiled:
            return
        with self._lock:
            if self._compiled:
                return
            self._build_patterns()
            self._compiled = True

    def _build_patterns(self):
        """构建全部正则模式"""
        P = self.patterns

        # ============ 1. ISO 日期范围 ============
        P.append((
            "iso_range_dotdot",
            re.compile(
                r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s*(?:\.\.|\.{3}|~|至|到|to)\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
                re.IGNORECASE
            ),
            "iso_range"
        ))

        # 单个 ISO 日期
        P.append((
            "iso_single",
            re.compile(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'),
            "iso_single"
        ))

        # ============ 2. 中文绝对日期 ============
        # "今天" / "今日"
        P.append(("cn_today", re.compile(r'今[天日]'), "cn_abs"))
        P.append(("cn_yesterday", re.compile(r'昨[天日]'), "cn_abs"))
        P.append(("cn_day_before_yesterday", re.compile(r'前[天日]'), "cn_abs"))
        P.append(("cn_day_before_before", re.compile(r'大前[天日]'), "cn_abs"))
        P.append(("cn_tomorrow", re.compile(r'明[天日]'), "cn_abs"))
        P.append(("cn_day_after_tomorrow", re.compile(r'后[天日]'), "cn_abs"))

        # "这周/本周" "上周/上个星期" "下周"
        P.append(("cn_this_week", re.compile(r'(?:这|本)(?:周|星期|礼拜)'), "cn_abs"))
        P.append(("cn_last_week", re.compile(r'上(?:个?(?:周|星期|礼拜))'), "cn_abs"))
        P.append(("cn_next_week", re.compile(r'下(?:个?(?:周|星期|礼拜))'), "cn_abs"))

        # "这个月/本月" "上个月/上月" "下个月"
        P.append(("cn_this_month", re.compile(r'(?:这个?|本)月'), "cn_abs"))
        P.append(("cn_last_month", re.compile(r'上(?:个?)月'), "cn_abs"))
        P.append(("cn_next_month", re.compile(r'下(?:个?)月'), "cn_abs"))

        # "今年" "去年" "前年" "明年"
        P.append(("cn_this_year", re.compile(r'今年'), "cn_abs"))
        P.append(("cn_last_year", re.compile(r'去年'), "cn_abs"))
        P.append(("cn_year_before_last", re.compile(r'前年'), "cn_abs"))
        P.append(("cn_next_year", re.compile(r'明年'), "cn_abs"))

        # ============ 3. 中文相对时间 ============
        # "N天前" / "N天以前" / "N日前"
        P.append((
            "cn_n_days_ago",
            re.compile(r'(\d+|[一二两三四五六七八九十百千万]+)[天日](?:以?)前'),
            "cn_rel"
        ))
        # "N小时前"
        P.append((
            "cn_n_hours_ago",
            re.compile(r'(\d+|[一二两三四五六七八九十百千万]+)(?:个?小时|钟头)(?:以?)前'),
            "cn_rel"
        ))
        # "N分钟前"
        P.append((
            "cn_n_minutes_ago",
            re.compile(r'(\d+|[一二两三四五六七八九十百千万]+)(?:分钟|分)(?:以?)前'),
            "cn_rel"
        ))
        # "N周前" / "N个星期前"
        P.append((
            "cn_n_weeks_ago",
            re.compile(r'(\d+|[一二两三四五六七八九十百千万]+)(?:个?(?:周|星期|礼拜))(?:以?)前'),
            "cn_rel"
        ))
        # "N个月前"
        P.append((
            "cn_n_months_ago",
            re.compile(r'(\d+|[一二两三四五六七八九十百千万]+)个?月(?:以?)前'),
            "cn_rel"
        ))
        # "N年前"
        P.append((
            "cn_n_years_ago",
            re.compile(r'(\d+|[一二两三四五六七八九十百千万]+)年(?:以?)前'),
            "cn_rel"
        ))
        # "过去N天" / "最近N天"
        P.append((
            "cn_past_n_days",
            re.compile(r'(?:过去|最近|近)(\d+|[一二两三四五六七八九十百千万]+)[天日]'),
            "cn_rel"
        ))
        # "过去N周"
        P.append((
            "cn_past_n_weeks",
            re.compile(r'(?:过去|最近|近)(\d+|[一二两三四五六七八九十百千万]+)(?:个?(?:周|星期|礼拜))'),
            "cn_rel"
        ))
        # "过去N个月" / "最近N个月"
        P.append((
            "cn_past_n_months",
            re.compile(r'(?:过去|最近|近)(\d+|[一二两三四五六七八九十百千万]+)个?月'),
            "cn_rel"
        ))
        # "过去N年" / "最近N年"
        P.append((
            "cn_past_n_years",
            re.compile(r'(?:过去|最近|近)(\d+|[一二两三四五六七八九十百千万]+)年'),
            "cn_rel"
        ))

        # ============ 4. 英文绝对日期 ============
        P.append(("en_today", re.compile(r'\btoday\b', re.I), "en_abs"))
        P.append(("en_yesterday", re.compile(r'\byesterday\b', re.I), "en_abs"))
        P.append(("en_tomorrow", re.compile(r'\btomorrow\b', re.I), "en_abs"))

        P.append(("en_this_week", re.compile(r'\bthis\s+week\b', re.I), "en_abs"))
        P.append(("en_last_week", re.compile(r'\blast\s+week\b', re.I), "en_abs"))
        P.append(("en_next_week", re.compile(r'\bnext\s+week\b', re.I), "en_abs"))

        P.append(("en_this_month", re.compile(r'\bthis\s+month\b', re.I), "en_abs"))
        P.append(("en_last_month", re.compile(r'\blast\s+month\b', re.I), "en_abs"))
        P.append(("en_next_month", re.compile(r'\bnext\s+month\b', re.I), "en_abs"))

        P.append(("en_this_year", re.compile(r'\bthis\s+year\b', re.I), "en_abs"))
        P.append(("en_last_year", re.compile(r'\blast\s+year\b', re.I), "en_abs"))
        P.append(("en_next_year", re.compile(r'\bnext\s+year\b', re.I), "en_abs"))

        # ============ 5. 英文相对时间 ============
        # "N days ago"
        P.append((
            "en_n_days_ago",
            re.compile(r'(\d+)\s+days?\s+ago\b', re.I),
            "en_rel"
        ))
        # "N hours ago"
        P.append((
            "en_n_hours_ago",
            re.compile(r'(\d+)\s+hours?\s+ago\b', re.I),
            "en_rel"
        ))
        # "N minutes ago"
        P.append((
            "en_n_minutes_ago",
            re.compile(r'(\d+)\s+minutes?\s+ago\b', re.I),
            "en_rel"
        ))
        # "N weeks ago"
        P.append((
            "en_n_weeks_ago",
            re.compile(r'(\d+)\s+weeks?\s+ago\b', re.I),
            "en_rel"
        ))
        # "N months ago"
        P.append((
            "en_n_months_ago",
            re.compile(r'(\d+)\s+months?\s+ago\b', re.I),
            "en_rel"
        ))
        # "N years ago"
        P.append((
            "en_n_years_ago",
            re.compile(r'(\d+)\s+years?\s+ago\b', re.I),
            "en_rel"
        ))

        # "past N days" / "last N days"
        P.append((
            "en_past_n_days",
            re.compile(r'(?:past|last)\s+(\d+)\s+days?\b', re.I),
            "en_rel"
        ))
        P.append((
            "en_past_n_weeks",
            re.compile(r'(?:past|last)\s+(\d+)\s+weeks?\b', re.I),
            "en_rel"
        ))
        P.append((
            "en_past_n_months",
            re.compile(r'(?:past|last)\s+(\d+)\s+months?\b', re.I),
            "en_rel"
        ))
        P.append((
            "en_past_n_years",
            re.compile(r'(?:past|last)\s+(\d+)\s+years?\b', re.I),
            "en_rel"
        ))


# 全局单例
_PATTERNS = _RegexPatterns()


# 时间关键词列表（用于判断是否需要 LLM 兜底）
_TIME_HINT_WORDS_CN = {
    '时', '时候', '时间', '何时', '什么时候', '那时', '当时', '此后',
    '期间', '以来', '以后', '之后', '之前', '以前', '年初', '年底',
    '月初', '月底', '月末', '周初', '周末', '上午', '下午', '晚上',
    '清晨', '早上', '中午', '傍晚', '凌晨', '夜里', '春天', '夏天',
    '秋天', '冬天', '春节', '元旦', '圣诞', '国庆', '中秋',
}
_TIME_HINT_WORDS_EN = {
    'when', 'time', 'during', 'since', 'after', 'before', 'until',
    'morning', 'afternoon', 'evening', 'night', 'noon', 'midnight',
    'spring', 'summer', 'autumn', 'fall', 'winter',
    'christmas', 'new year', 'weekend', 'weekday',
    'dawn', 'dusk', 'recently', 'earlier', 'later', 'sometime',
}


# ==================== 主类 ====================

class TimeIntentParser:
    """时间意图解析器

    混合策略: regex 优先 → LLM 兜底
    线程安全、无外部依赖（正则层）
    """

    def __init__(self, llm_client: Optional['LLMClient'] = None):
        """初始化时间意图解析器

        Args:
            llm_client: 可选的 LLM 客户端，用于 Layer 2 兜底
        """
        self.llm_client = llm_client
        _PATTERNS.ensure_compiled()

    # ==================== 公共 API ====================

    def parse(
        self,
        text: str,
        reference_time: Optional[datetime] = None,
        allow_llm_fallback: bool = True,
    ) -> Optional[TimeRange]:
        """解析文本中的时间意图

        Args:
            text: 待解析文本
            reference_time: 参考时间，默认为当前时间
            allow_llm_fallback: 是否允许 LLM 兜底

        Returns:
            TimeRange 或 None（无法识别时间意图）
        """
        if not text or not text.strip():
            return None

        now = reference_time or datetime.now()

        # Layer 1: 正则匹配
        result = self._regex_parse(text, now)
        if result is not None:
            return result

        # Layer 2: LLM 兜底（仅在文本含时间暗示词时触发）
        if allow_llm_fallback and self.llm_client and self._contains_time_hint(text):
            try:
                return self._llm_parse(text, now)
            except Exception as e:
                logger.warning(f"[TimeIntentParser] LLM 兜底失败: {e}")

        return None

    def parse_all(
        self,
        text: str,
        reference_time: Optional[datetime] = None,
    ) -> List[TimeRange]:
        """解析文本中的所有时间表达式（仅正则层，用于批量场景）

        Args:
            text: 待解析文本
            reference_time: 参考时间

        Returns:
            所有匹配的 TimeRange 列表
        """
        if not text or not text.strip():
            return []

        now = reference_time or datetime.now()
        results: List[TimeRange] = []

        for name, pattern, category in _PATTERNS.patterns:
            for match in pattern.finditer(text):
                tr = self._match_to_timerange(name, category, match, now)
                if tr is not None:
                    results.append(tr)

        # 按 start 排序，去重重叠
        results.sort(key=lambda r: r.start)
        return self._deduplicate_ranges(results)

    # ==================== Layer 1: 正则 ====================

    def _regex_parse(self, text: str, now: datetime) -> Optional[TimeRange]:
        """正则匹配，返回第一个匹配结果"""
        for name, pattern, category in _PATTERNS.patterns:
            match = pattern.search(text)
            if match:
                tr = self._match_to_timerange(name, category, match, now)
                if tr is not None:
                    return tr
        return None

    def _match_to_timerange(
        self, name: str, category: str, match: re.Match, now: datetime
    ) -> Optional[TimeRange]:
        """将正则匹配转换为 TimeRange"""
        try:
            start, end = self._resolve_match(name, match, now)
            if start is None or end is None:
                return None
            # 确保 start <= end
            if start > end:
                start, end = end, start
            return TimeRange(
                start=start,
                end=end,
                confidence=0.95,
                source="regex",
                matched_text=match.group(0),
                pattern_name=name,
            )
        except Exception as e:
            logger.debug(f"[TimeIntentParser] 模式 {name} 解析失败: {e}")
            return None

    def _resolve_match(
        self, name: str, match: re.Match, now: datetime
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """根据模式名称和匹配结果计算时间范围"""

        # --- ISO 日期范围 ---
        if name == "iso_range_dotdot":
            d1 = self._parse_iso_date(match.group(1))
            d2 = self._parse_iso_date(match.group(2))
            if d1 and d2:
                return _start_of_day(d1), _end_of_day(d2)
            return None, None

        if name == "iso_single":
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            try:
                dt = datetime(y, m, d)
                return _start_of_day(dt), _end_of_day(dt)
            except ValueError:
                return None, None

        # --- 中文 / 英文绝对日期 ---
        abs_map = {
            # 中文
            "cn_today": lambda: (_start_of_day(now), _end_of_day(now)),
            "cn_yesterday": lambda: (_start_of_day(now - timedelta(days=1)), _end_of_day(now - timedelta(days=1))),
            "cn_day_before_yesterday": lambda: (_start_of_day(now - timedelta(days=2)), _end_of_day(now - timedelta(days=2))),
            "cn_day_before_before": lambda: (_start_of_day(now - timedelta(days=3)), _end_of_day(now - timedelta(days=3))),
            "cn_tomorrow": lambda: (_start_of_day(now + timedelta(days=1)), _end_of_day(now + timedelta(days=1))),
            "cn_day_after_tomorrow": lambda: (_start_of_day(now + timedelta(days=2)), _end_of_day(now + timedelta(days=2))),
            "cn_this_week": lambda: (_start_of_week(now), _end_of_week(now)),
            "cn_last_week": lambda: (_start_of_week(now - timedelta(weeks=1)), _end_of_week(now - timedelta(weeks=1))),
            "cn_next_week": lambda: (_start_of_week(now + timedelta(weeks=1)), _end_of_week(now + timedelta(weeks=1))),
            "cn_this_month": lambda: (_start_of_month(now), _end_of_month(now)),
            "cn_last_month": lambda: self._month_offset(now, -1),
            "cn_next_month": lambda: self._month_offset(now, 1),
            "cn_this_year": lambda: (_start_of_year(now), _end_of_year(now)),
            "cn_last_year": lambda: (_start_of_year(now.replace(year=now.year - 1)), _end_of_year(now.replace(year=now.year - 1))),
            "cn_year_before_last": lambda: (_start_of_year(now.replace(year=now.year - 2)), _end_of_year(now.replace(year=now.year - 2))),
            "cn_next_year": lambda: (_start_of_year(now.replace(year=now.year + 1)), _end_of_year(now.replace(year=now.year + 1))),
            # 英文
            "en_today": lambda: (_start_of_day(now), _end_of_day(now)),
            "en_yesterday": lambda: (_start_of_day(now - timedelta(days=1)), _end_of_day(now - timedelta(days=1))),
            "en_tomorrow": lambda: (_start_of_day(now + timedelta(days=1)), _end_of_day(now + timedelta(days=1))),
            "en_this_week": lambda: (_start_of_week(now), _end_of_week(now)),
            "en_last_week": lambda: (_start_of_week(now - timedelta(weeks=1)), _end_of_week(now - timedelta(weeks=1))),
            "en_next_week": lambda: (_start_of_week(now + timedelta(weeks=1)), _end_of_week(now + timedelta(weeks=1))),
            "en_this_month": lambda: (_start_of_month(now), _end_of_month(now)),
            "en_last_month": lambda: self._month_offset(now, -1),
            "en_next_month": lambda: self._month_offset(now, 1),
            "en_this_year": lambda: (_start_of_year(now), _end_of_year(now)),
            "en_last_year": lambda: (_start_of_year(now.replace(year=now.year - 1)), _end_of_year(now.replace(year=now.year - 1))),
            "en_next_year": lambda: (_start_of_year(now.replace(year=now.year + 1)), _end_of_year(now.replace(year=now.year + 1))),
        }
        if name in abs_map:
            return abs_map[name]()

        # --- 相对时间（N xxx ago / 过去 N xxx） ---
        return self._resolve_relative(name, match, now)

    def _resolve_relative(
        self, name: str, match: re.Match, now: datetime
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """解析相对时间表达式"""
        raw_num = match.group(1)
        n = int(raw_num) if raw_num.isdigit() else _cn_to_int(raw_num)
        if n <= 0:
            return None, None

        # "N xxx 前" → [now - N*unit, now]
        ago_map = {
            "cn_n_days_ago": lambda: timedelta(days=n),
            "cn_n_hours_ago": lambda: timedelta(hours=n),
            "cn_n_minutes_ago": lambda: timedelta(minutes=n),
            "cn_n_weeks_ago": lambda: timedelta(weeks=n),
            "cn_n_months_ago": lambda: timedelta(days=n * 30),
            "cn_n_years_ago": lambda: timedelta(days=n * 365),
            "en_n_days_ago": lambda: timedelta(days=n),
            "en_n_hours_ago": lambda: timedelta(hours=n),
            "en_n_minutes_ago": lambda: timedelta(minutes=n),
            "en_n_weeks_ago": lambda: timedelta(weeks=n),
            "en_n_months_ago": lambda: timedelta(days=n * 30),
            "en_n_years_ago": lambda: timedelta(days=n * 365),
        }
        if name in ago_map:
            delta = ago_map[name]()
            return (now - delta, now)

        # "过去/past N xxx" → [now - N*unit, now]
        past_map = {
            "cn_past_n_days": lambda: timedelta(days=n),
            "cn_past_n_weeks": lambda: timedelta(weeks=n),
            "cn_past_n_months": lambda: timedelta(days=n * 30),
            "cn_past_n_years": lambda: timedelta(days=n * 365),
            "en_past_n_days": lambda: timedelta(days=n),
            "en_past_n_weeks": lambda: timedelta(weeks=n),
            "en_past_n_months": lambda: timedelta(days=n * 30),
            "en_past_n_years": lambda: timedelta(days=n * 365),
        }
        if name in past_map:
            delta = past_map[name]()
            return (now - delta, now)

        return None, None

    # ==================== Layer 2: LLM 兜底 ====================

    def _contains_time_hint(self, text: str) -> bool:
        """检查文本是否包含时间暗示词"""
        text_lower = text.lower()
        for w in _TIME_HINT_WORDS_CN:
            if w in text:
                return True
        for w in _TIME_HINT_WORDS_EN:
            if w in text_lower:
                return True
        return False

    def _llm_parse(self, text: str, now: datetime) -> Optional[TimeRange]:
        """使用 LLM 解析时间意图"""
        if not self.llm_client:
            return None

        prompt = (
            f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"请从以下文本中提取时间范围。如果文本不包含明确的时间意图，返回 NONE。\n"
            f"文本: {text}\n\n"
            f"请严格按以下 JSON 格式回答（不加任何其他文字）:\n"
            f'{{"start": "YYYY-MM-DD HH:MM:SS", "end": "YYYY-MM-DD HH:MM:SS", "confidence": 0.0-1.0}}\n'
            f"如果无法提取，返回: NONE"
        )

        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150,
            )
            content = response.content.strip()
            if content.upper() == "NONE" or not content.startswith("{"):
                return None

            import json
            data = json.loads(content)
            start = datetime.strptime(data["start"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(data["end"], "%Y-%m-%d %H:%M:%S")
            confidence = float(data.get("confidence", 0.7))

            return TimeRange(
                start=start,
                end=end,
                confidence=min(confidence, 0.9),  # LLM 最高置信度 cap 为 0.9
                source="llm",
                matched_text=text[:100],
                pattern_name="llm_fallback",
            )
        except Exception as e:
            logger.debug(f"[TimeIntentParser] LLM 解析失败: {e}")
            return None

    # ==================== 辅助方法 ====================

    @staticmethod
    def _parse_iso_date(s: str) -> Optional[datetime]:
        """解析 ISO 日期字符串 (YYYY-MM-DD 或 YYYY/MM/DD)"""
        s = s.replace('/', '-')
        try:
            parts = s.split('-')
            return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _month_offset(now: datetime, offset: int) -> Tuple[datetime, datetime]:
        """计算月偏移后的月份范围"""
        import calendar
        year = now.year
        month = now.month + offset
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        first_day = datetime(year, month, 1)
        last_day_num = calendar.monthrange(year, month)[1]
        last_day = datetime(year, month, last_day_num, 23, 59, 59, 999999)
        return first_day, last_day

    @staticmethod
    def _deduplicate_ranges(ranges: List[TimeRange]) -> List[TimeRange]:
        """去重重叠的时间范围，保留置信度更高的"""
        if len(ranges) <= 1:
            return ranges
        result: List[TimeRange] = [ranges[0]]
        for tr in ranges[1:]:
            if tr.overlaps(result[-1]):
                # 保留置信度更高的
                if tr.confidence > result[-1].confidence:
                    result[-1] = tr
            else:
                result.append(tr)
        return result
