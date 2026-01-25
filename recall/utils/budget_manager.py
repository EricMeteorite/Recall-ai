"""LLM 预算管理器 - Recall 4.0 Phase 2

设计理念：
1. 控制 LLM API 调用成本
2. 支持每日/每小时预算限制
3. 自动降级策略（预算耗尽时切换到本地模式）
4. 持久化预算使用记录
"""

from __future__ import annotations

import os
import json
import time
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from threading import Lock
from enum import Enum


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


class BudgetPeriod(str, Enum):
    """预算周期"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class UsageRecord:
    """单次使用记录"""
    timestamp: float
    operation: str          # 操作类型: extraction, dedup, rerank, etc.
    tokens_in: int = 0      # 输入 token 数
    tokens_out: int = 0     # 输出 token 数
    cost: float = 0.0       # 估算成本（美元）
    model: str = ""         # 使用的模型
    success: bool = True    # 是否成功
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UsageRecord':
        return cls(**data)


@dataclass
class BudgetConfig:
    """预算配置"""
    daily_budget: float = 1.0           # 每日预算（美元）
    hourly_budget: float = 0.1          # 每小时预算（美元）
    warning_threshold: float = 0.8      # 警告阈值（80% 时警告）
    auto_degrade: bool = True           # 预算耗尽时自动降级
    
    # 模型价格配置（每 1K tokens，美元）
    price_per_1k_input: float = 0.0015  # 默认 GPT-4o-mini 输入价格
    price_per_1k_output: float = 0.006  # 默认 GPT-4o-mini 输出价格
    
    # 预留配额（确保关键操作总是可以执行）
    reserved_budget: float = 0.1        # 保留预算（紧急操作用）


class BudgetManager:
    """LLM 预算管理器
    
    功能：
    1. 跟踪 LLM API 调用成本
    2. 根据预算限制决定是否允许 LLM 调用
    3. 支持预算预估（在调用前检查）
    4. 提供降级策略（预算耗尽时返回降级建议）
    
    使用方式：
        manager = BudgetManager(data_path)
        
        # 检查是否可以执行操作
        if manager.can_afford(estimated_cost=0.01):
            # 执行 LLM 调用
            result = llm_client.call(...)
            # 记录实际成本
            manager.record_usage(
                operation="extraction",
                tokens_in=100,
                tokens_out=50,
                model="gpt-4o-mini"
            )
    """
    
    def __init__(
        self,
        data_path: str,
        config: Optional[BudgetConfig] = None
    ):
        """初始化预算管理器
        
        Args:
            data_path: 数据存储路径
            config: 预算配置
        """
        self.data_path = data_path
        self.config = config or BudgetConfig()
        
        # 存储路径
        self.budget_dir = os.path.join(data_path, 'budget')
        self.usage_file = os.path.join(self.budget_dir, 'usage.json')
        self.stats_file = os.path.join(self.budget_dir, 'stats.json')
        
        # 内存缓存
        self._usage_records: List[UsageRecord] = []
        self._daily_cost: float = 0.0
        self._hourly_cost: float = 0.0
        self._current_day: date = date.today()
        self._current_hour: int = datetime.now().hour
        
        # 线程安全
        self._lock = Lock()
        
        # 回调函数（预算耗尽时调用）
        self._on_budget_exhausted: Optional[Callable] = None
        self._on_budget_warning: Optional[Callable] = None
        
        # 加载历史数据
        self._load()
    
    def _load(self):
        """加载历史使用数据"""
        os.makedirs(self.budget_dir, exist_ok=True)
        
        if os.path.exists(self.usage_file):
            try:
                with open(self.usage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 只加载今天的记录
                today = date.today()
                current_hour = datetime.now().hour
                
                for record_data in data.get('records', []):
                    record = UsageRecord.from_dict(record_data)
                    record_time = datetime.fromtimestamp(record.timestamp)
                    
                    if record_time.date() == today:
                        self._usage_records.append(record)
                        self._daily_cost += record.cost
                        
                        if record_time.hour == current_hour:
                            self._hourly_cost += record.cost
                
                self._current_day = today
                self._current_hour = current_hour
            except Exception as e:
                _safe_print(f"[BudgetManager] 加载使用记录失败: {e}")
    
    def _save(self):
        """保存使用数据"""
        try:
            # 只保存最近 7 天的记录
            cutoff = time.time() - 7 * 24 * 3600
            recent_records = [
                r for r in self._usage_records
                if r.timestamp > cutoff
            ]
            
            data = {
                'last_updated': datetime.now().isoformat(),
                'records': [r.to_dict() for r in recent_records]
            }
            
            with open(self.usage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _safe_print(f"[BudgetManager] 保存使用记录失败: {e}")
    
    def _refresh_period(self):
        """刷新周期（检查是否需要重置计数器）"""
        now = datetime.now()
        today = now.date()
        current_hour = now.hour
        
        # 新的一天，重置日预算
        if today != self._current_day:
            self._daily_cost = 0.0
            self._hourly_cost = 0.0
            self._current_day = today
            self._current_hour = current_hour
            # 清理旧记录
            self._usage_records = [
                r for r in self._usage_records
                if datetime.fromtimestamp(r.timestamp).date() == today
            ]
        
        # 新的一小时，重置小时预算
        elif current_hour != self._current_hour:
            self._hourly_cost = 0.0
            self._current_hour = current_hour
    
    def estimate_cost(
        self,
        tokens_in: int,
        tokens_out: int,
        model: str = None
    ) -> float:
        """估算成本
        
        Args:
            tokens_in: 预估输入 token 数
            tokens_out: 预估输出 token 数
            model: 模型名称（用于查找价格）
            
        Returns:
            float: 估算成本（美元）
        """
        # 可以根据模型调整价格
        price_in = self.config.price_per_1k_input
        price_out = self.config.price_per_1k_output
        
        # 模型特定价格
        model_prices = {
            'gpt-4o-mini': (0.00015, 0.0006),  # 输入/输出 per 1K
            'gpt-4o': (0.005, 0.015),
            'gpt-4-turbo': (0.01, 0.03),
            'gpt-3.5-turbo': (0.0005, 0.0015),
            'deepseek-chat': (0.00014, 0.00028),
            'qwen-turbo': (0.0002, 0.0006),
        }
        
        if model and model in model_prices:
            price_in, price_out = model_prices[model]
        
        cost = (tokens_in / 1000 * price_in) + (tokens_out / 1000 * price_out)
        return cost
    
    def can_afford(
        self,
        estimated_cost: float = 0.01,
        operation: str = "general",
        use_reserved: bool = False
    ) -> bool:
        """检查是否有足够预算
        
        Args:
            estimated_cost: 估算成本
            operation: 操作类型
            use_reserved: 是否允许使用保留预算
            
        Returns:
            bool: 是否可以执行
        """
        with self._lock:
            self._refresh_period()
            
            available_daily = self.config.daily_budget - self._daily_cost
            available_hourly = self.config.hourly_budget - self._hourly_cost
            
            if use_reserved:
                available_daily += self.config.reserved_budget
            
            # 检查日预算和小时预算
            if estimated_cost > available_daily:
                return False
            if estimated_cost > available_hourly:
                return False
            
            return True
    
    def get_remaining_budget(self, period: BudgetPeriod = BudgetPeriod.DAILY) -> float:
        """获取剩余预算
        
        Args:
            period: 预算周期
            
        Returns:
            float: 剩余预算（美元）
        """
        with self._lock:
            self._refresh_period()
            
            if period == BudgetPeriod.HOURLY:
                return max(0, self.config.hourly_budget - self._hourly_cost)
            else:
                return max(0, self.config.daily_budget - self._daily_cost)
    
    def get_usage_percentage(self, period: BudgetPeriod = BudgetPeriod.DAILY) -> float:
        """获取预算使用百分比
        
        Args:
            period: 预算周期
            
        Returns:
            float: 使用百分比 (0-1)
        """
        with self._lock:
            self._refresh_period()
            
            if period == BudgetPeriod.HOURLY:
                if self.config.hourly_budget <= 0:
                    return 0.0
                return self._hourly_cost / self.config.hourly_budget
            else:
                if self.config.daily_budget <= 0:
                    return 0.0
                return self._daily_cost / self.config.daily_budget
    
    def record_usage(
        self,
        operation: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = None,
        model: str = "",
        success: bool = True
    ) -> UsageRecord:
        """记录 API 使用
        
        Args:
            operation: 操作类型
            tokens_in: 输入 token 数
            tokens_out: 输出 token 数
            cost: 实际成本（None 则自动计算）
            model: 使用的模型
            success: 是否成功
            
        Returns:
            UsageRecord: 使用记录
        """
        if cost is None:
            cost = self.estimate_cost(tokens_in, tokens_out, model)
        
        record = UsageRecord(
            timestamp=time.time(),
            operation=operation,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            model=model,
            success=success
        )
        
        with self._lock:
            self._refresh_period()
            
            self._usage_records.append(record)
            self._daily_cost += cost
            self._hourly_cost += cost
            
            # 检查是否触发警告
            usage_pct = self._daily_cost / self.config.daily_budget if self.config.daily_budget > 0 else 0
            if usage_pct >= self.config.warning_threshold:
                if self._on_budget_warning:
                    self._on_budget_warning(self._daily_cost, self.config.daily_budget)
            
            # 检查是否预算耗尽
            if self._daily_cost >= self.config.daily_budget:
                if self._on_budget_exhausted:
                    self._on_budget_exhausted()
            
            # 保存
            self._save()
        
        return record
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            self._refresh_period()
            
            # 按操作类型统计
            by_operation: Dict[str, Dict] = {}
            for record in self._usage_records:
                if record.operation not in by_operation:
                    by_operation[record.operation] = {
                        'count': 0,
                        'total_cost': 0.0,
                        'total_tokens_in': 0,
                        'total_tokens_out': 0
                    }
                stats = by_operation[record.operation]
                stats['count'] += 1
                stats['total_cost'] += record.cost
                stats['total_tokens_in'] += record.tokens_in
                stats['total_tokens_out'] += record.tokens_out
            
            return {
                'daily_cost': round(self._daily_cost, 6),
                'hourly_cost': round(self._hourly_cost, 6),
                'daily_budget': self.config.daily_budget,
                'hourly_budget': self.config.hourly_budget,
                'daily_remaining': round(self.config.daily_budget - self._daily_cost, 6),
                'hourly_remaining': round(self.config.hourly_budget - self._hourly_cost, 6),
                'daily_usage_pct': round(self._daily_cost / self.config.daily_budget * 100, 2) if self.config.daily_budget > 0 else 0,
                'hourly_usage_pct': round(self._hourly_cost / self.config.hourly_budget * 100, 2) if self.config.hourly_budget > 0 else 0,
                'record_count': len(self._usage_records),
                'by_operation': by_operation
            }
    
    def set_budget(
        self,
        daily_budget: float = None,
        hourly_budget: float = None
    ):
        """动态设置预算
        
        Args:
            daily_budget: 新的每日预算
            hourly_budget: 新的每小时预算
        """
        with self._lock:
            if daily_budget is not None:
                self.config.daily_budget = daily_budget
            if hourly_budget is not None:
                self.config.hourly_budget = hourly_budget
    
    def on_budget_exhausted(self, callback: Callable):
        """设置预算耗尽回调"""
        self._on_budget_exhausted = callback
    
    def on_budget_warning(self, callback: Callable[[float, float], None]):
        """设置预算警告回调"""
        self._on_budget_warning = callback
    
    def suggest_degradation(self) -> str:
        """建议降级策略
        
        Returns:
            str: 降级建议 (lite/cloud/local)
        """
        remaining = self.get_remaining_budget()
        
        if remaining <= 0:
            return "lite"       # 完全切换到 Lite 模式
        elif remaining < 0.1:
            return "cloud"      # Cloud 模式，减少 LLM 使用
        else:
            return "local"      # Local 模式（本地模型）
    
    def reset_daily(self):
        """手动重置每日预算（用于测试或特殊情况）"""
        with self._lock:
            self._daily_cost = 0.0
            self._hourly_cost = 0.0
            self._current_day = date.today()
            self._current_hour = datetime.now().hour
