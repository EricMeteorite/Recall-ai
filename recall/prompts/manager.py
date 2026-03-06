"""Prompt 模板管理器

支持：
1. YAML 模板定义 + Python str.format() 变量渲染
2. 多语言支持（zh/en）— 通过 RECALL_LANG 环境变量切换
3. v7.0: 统一通用模式（不再按 RP/通用/知识库 区分 prompt）
4. 用户自定义覆盖（在 recall_data/prompts/ 中放同名文件）

注意：使用 Python 原生 str.format() 渲染变量（非 Jinja2），
模板中 JSON 的 { } 需要写成 {{ }}。
"""

import os
from recall.mode import RecallMode


class PromptManager:
    """Prompt 模板管理器"""

    def __init__(self, mode: RecallMode = RecallMode.UNIVERSAL, lang: str = ""):
        self.mode = mode
        self.lang = lang or os.environ.get('RECALL_LANG', 'zh')
        self._templates = {}
        self._load_templates()

    def render(self, template_name: str, **kwargs) -> str:
        """渲染 prompt 模板"""
        if template_name not in self._templates:
            raise ValueError(f"模板 '{template_name}' 不存在，可用: {list(self._templates.keys())}")
        template = self._templates[template_name]
        # v7.0: 优先使用 'universal' 变体，回退到 'default'，再回退到 'roleplay'（向后兼容旧模板）
        variant = (template.get('universal') 
                   or template.get('default') 
                   or template.get('roleplay')
                   or template.get(self.mode.value))
        if variant is None:
            raise ValueError(
                f"模板 '{template_name}' 缺少可用变体，"
                f"可用 key: {list(template.keys())}"
            )
        return variant.format(**kwargs)

    def _load_templates(self):
        """从 YAML 加载模板，优先用户自定义覆盖

        加载顺序 (后加载覆盖先前):
        1. 内置中文模板 (templates/*.yaml)
        2. 内置英文模板 (templates/en/*.yaml) — 当 RECALL_LANG=en 时覆盖
        3. 用户自定义 (recall_data/prompts/*.yaml)
        """
        import yaml

        # 1. 加载内置模板（默认中文）
        builtin_dir = os.path.join(os.path.dirname(__file__), 'templates')
        if os.path.exists(builtin_dir):
            for f in os.listdir(builtin_dir):
                if f.endswith('.yaml'):
                    name = f[:-5]  # 去掉 .yaml
                    with open(os.path.join(builtin_dir, f), 'r', encoding='utf-8') as fh:
                        self._templates[name] = yaml.safe_load(fh)

        # 2. 语言覆盖: 加载 templates/{lang}/*.yaml
        if self.lang and self.lang != 'zh':
            lang_dir = os.path.join(builtin_dir, self.lang)
            if os.path.exists(lang_dir):
                for f in os.listdir(lang_dir):
                    if f.endswith('.yaml'):
                        name = f[:-5]
                        with open(os.path.join(lang_dir, f), 'r', encoding='utf-8') as fh:
                            data = yaml.safe_load(fh)
                            if data:
                                self._templates[name] = data

        # 3. 用户覆盖（recall_data/prompts/ 中的同名文件优先）
        user_dir = os.path.join(os.environ.get('RECALL_DATA_ROOT', 'recall_data'), 'prompts')
        if os.path.exists(user_dir):
            for f in os.listdir(user_dir):
                if f.endswith('.yaml'):
                    name = f[:-5]
                    with open(os.path.join(user_dir, f), 'r', encoding='utf-8') as fh:
                        self._templates[name] = yaml.safe_load(fh)
