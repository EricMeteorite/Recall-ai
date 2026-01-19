"""L0核心设定 - 完整实现"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class CoreSettings:
    """核心设定 - 用户一次配置，永久生效"""
    
    # RP场景
    character_card: str = ""          # 角色卡（≤2000字）
    world_setting: str = ""           # 世界观（≤1000字）
    writing_style: str = ""           # 写作风格要求
    
    # 代码场景
    code_standards: str = ""          # 代码规范
    project_structure: str = ""       # 项目结构说明
    naming_conventions: str = ""      # 命名规范
    
    # 通用
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    absolute_rules: List[str] = field(default_factory=list)  # 绝对不能违反的规则
    
    # 内部使用：存储data_path以便save()时无需传参
    _data_path: Optional[str] = field(default=None, repr=False)
    
    @classmethod
    def load(cls, data_path: str) -> 'CoreSettings':
        """从文件加载核心设定"""
        config_file = os.path.join(data_path, 'L0_core', 'core.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 移除可能存在的旧的 _data_path
                data.pop('_data_path', None)
                instance = cls(**data)
                instance._data_path = data_path
                return instance
        instance = cls()  # 返回默认空设定
        instance._data_path = data_path
        return instance
    
    def save(self, data_path: Optional[str] = None):
        """保存核心设定
        
        Args:
            data_path: 可选，如果不提供则使用 load() 时保存的路径
        """
        path = data_path or self._data_path
        if not path:
            raise ValueError("data_path 未指定，请在 save() 时传入或确保通过 load() 加载")
        
        config_dir = os.path.join(path, 'L0_core')
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(config_dir, 'core.json')
        
        # 保存时排除 _data_path 字段
        data = asdict(self)
        data.pop('_data_path', None)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_injection_text(self, scenario: str) -> str:
        """根据场景返回需要注入的核心设定"""
        if scenario == 'roleplay':
            parts = [self.character_card, self.world_setting, self.writing_style]
            return '\n\n'.join(p for p in parts if p)
        elif scenario == 'coding':
            parts = [self.code_standards, self.naming_conventions]
            return '\n\n'.join(p for p in parts if p)
        else:
            return self._get_universal_rules()
    
    def _get_universal_rules(self) -> str:
        """获取通用规则"""
        if not self.absolute_rules:
            return ""
        return "【必须遵守的规则】\n" + "\n".join(f"- {r}" for r in self.absolute_rules)
