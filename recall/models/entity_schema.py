"""自定义实体类型 Schema - Recall 4.1

支持用户定义自定义实体类型，包括：
1. 类型名称和描述
2. 必需/可选属性
3. 验证规则
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from enum import Enum


class AttributeType(str, Enum):
    """属性类型"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    LIST = "list"


@dataclass
class AttributeDefinition:
    """属性定义"""
    name: str
    attr_type: AttributeType = AttributeType.STRING
    required: bool = False
    default: Any = None
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'type': self.attr_type.value,
            'required': self.required,
            'default': self.default,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AttributeDefinition':
        return cls(
            name=data['name'],
            attr_type=AttributeType(data.get('type', 'string')),
            required=data.get('required', False),
            default=data.get('default'),
            description=data.get('description', '')
        )


@dataclass
class EntityTypeDefinition:
    """实体类型定义"""
    name: str                               # 类型名称（如 PERSON, LOCATION）
    display_name: str = ""                  # 显示名称（如 "人物", "地点"）
    description: str = ""                   # 类型描述
    attributes: List[AttributeDefinition] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)  # 示例实体
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name or self.name,
            'description': self.description,
            'attributes': [a.to_dict() for a in self.attributes],
            'examples': self.examples
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntityTypeDefinition':
        return cls(
            name=data['name'],
            display_name=data.get('display_name', data['name']),
            description=data.get('description', ''),
            attributes=[AttributeDefinition.from_dict(a) for a in data.get('attributes', [])],
            examples=data.get('examples', [])
        )


class EntitySchemaRegistry:
    """实体类型注册表
    
    使用方式：
        registry = EntitySchemaRegistry(data_path)
        
        # 注册自定义类型
        registry.register(EntityTypeDefinition(
            name="CHARACTER",
            display_name="角色",
            description="故事中的角色人物",
            attributes=[
                AttributeDefinition(name="age", attr_type=AttributeType.NUMBER),
                AttributeDefinition(name="occupation", attr_type=AttributeType.STRING),
            ],
            examples=["艾琳", "小明", "老王"]
        ))
        
        # 获取类型
        char_type = registry.get("CHARACTER")
        
        # 获取所有类型（用于 LLM 提示词）
        all_types = registry.get_all_for_prompt()
    """
    
    # 预定义的基础类型
    BUILTIN_TYPES = [
        EntityTypeDefinition(
            name="PERSON",
            display_name="人物",
            description="真实或虚构的人物",
            examples=["张三", "李四"]
        ),
        EntityTypeDefinition(
            name="LOCATION",
            display_name="地点",
            description="地理位置、地名",
            examples=["北京", "东京", "咖啡厅"]
        ),
        EntityTypeDefinition(
            name="ORGANIZATION",
            display_name="组织",
            description="公司、机构、团体",
            examples=["微软", "清华大学"]
        ),
        EntityTypeDefinition(
            name="ITEM",
            display_name="物品",
            description="物品、道具",
            examples=["手机", "魔法剑"]
        ),
        EntityTypeDefinition(
            name="CONCEPT",
            display_name="概念",
            description="抽象概念、术语",
            examples=["AI", "机器学习"]
        ),
        EntityTypeDefinition(
            name="EVENT",
            display_name="事件",
            description="事件、活动",
            examples=["春节", "婚礼"]
        ),
        EntityTypeDefinition(
            name="TIME",
            display_name="时间",
            description="时间点、时间段",
            examples=["2023年", "下午三点"]
        ),
    ]
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.schema_file = os.path.join(data_path, 'config', 'entity_schema.json')
        
        self._types: Dict[str, EntityTypeDefinition] = {}
        
        # 加载内置类型
        for t in self.BUILTIN_TYPES:
            self._types[t.name] = t
        
        # 加载自定义类型
        self._load()
    
    def _load(self):
        """加载自定义类型"""
        if os.path.exists(self.schema_file):
            try:
                with open(self.schema_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data.get('custom_types', []):
                        t = EntityTypeDefinition.from_dict(item)
                        self._types[t.name] = t
            except Exception as e:
                print(f"[EntitySchemaRegistry] 加载失败: {e}")
    
    def _save(self):
        """保存自定义类型"""
        os.makedirs(os.path.dirname(self.schema_file), exist_ok=True)
        
        # 只保存非内置类型
        builtin_names = {t.name for t in self.BUILTIN_TYPES}
        custom_types = [
            t.to_dict() for name, t in self._types.items()
            if name not in builtin_names
        ]
        
        with open(self.schema_file, 'w', encoding='utf-8') as f:
            json.dump({'custom_types': custom_types}, f, ensure_ascii=False, indent=2)
    
    def register(self, entity_type: EntityTypeDefinition):
        """注册自定义类型"""
        self._types[entity_type.name] = entity_type
        self._save()
    
    def get(self, name: str) -> Optional[EntityTypeDefinition]:
        """获取类型定义"""
        return self._types.get(name)
    
    def get_all(self) -> List[EntityTypeDefinition]:
        """获取所有类型"""
        return list(self._types.values())
    
    def get_all_for_prompt(self) -> str:
        """生成用于 LLM 提示词的类型描述"""
        lines = []
        for i, t in enumerate(self._types.values()):
            examples = ", ".join(t.examples[:3]) if t.examples else "无"
            lines.append(f"{i+1}. {t.name}（{t.display_name}）: {t.description}。示例: {examples}")
        return "\n".join(lines)
    
    def get_type_id_map(self) -> Dict[str, int]:
        """获取类型名称到ID的映射（用于 LLM 输出解析）"""
        return {t.name: i for i, t in enumerate(self._types.values())}
