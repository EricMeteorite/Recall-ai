"""初始化向导 - 纯本地模式，环境完全隔离"""

import os
import sys
import json
from datetime import datetime


class RecallInit:
    """初始化向导 - 简单3步，无痕安装（所有数据在项目目录内）"""
    
    _data_root = None  # 缓存数据根目录
    
    @classmethod
    def get_data_root(cls, base_path: str = None) -> str:
        """
        获取数据根目录（默认在当前工作目录下）
        
        优先级：
        1. 显式传入的 base_path
        2. 环境变量 RECALL_DATA_ROOT
        3. 当前工作目录下的 recall_data/
        
        这样确保所有数据都在项目目录内，删除项目文件夹即可完全卸载。
        """
        if base_path:
            return os.path.abspath(os.path.join(base_path, 'recall_data'))
        
        # 环境变量（高级用户可自定义）
        custom_root = os.environ.get('RECALL_DATA_ROOT')
        if custom_root:
            return os.path.abspath(custom_root)
        
        # 默认：当前工作目录下的 recall_data/
        return os.path.abspath('./recall_data')
    
    @classmethod
    def ensure_directories(cls, base_path: str = None):
        """确保所有必要目录存在（全部在项目目录内）"""
        root = cls.get_data_root(base_path)
        dirs = [
            root,
            os.path.join(root, 'data'),
            os.path.join(root, 'models'),
            os.path.join(root, 'models', 'spacy'),
            os.path.join(root, 'models', 'sentence-transformers'),
            os.path.join(root, 'models', 'huggingface'),
            os.path.join(root, 'models', 'torch'),
            os.path.join(root, 'cache'),
            os.path.join(root, 'logs'),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
        return root
    
    @classmethod
    def setup_environment(cls, base_path: str = None):
        """
        设置环境变量，确保所有模型和缓存都下载到项目目录内。
        
        这是实现"删除项目文件夹即完全卸载"的关键！
        所有第三方库（sentence-transformers, huggingface, torch, spacy）
        的缓存都被重定向到项目目录内。
        """
        root = cls.get_data_root(base_path)
        models_dir = os.path.join(root, 'models')
        
        # sentence-transformers 模型缓存目录
        os.environ['SENTENCE_TRANSFORMERS_HOME'] = os.path.join(models_dir, 'sentence-transformers')
        
        # HuggingFace 缓存目录（transformers, datasets 等）
        os.environ['HF_HOME'] = os.path.join(models_dir, 'huggingface')
        os.environ['HUGGINGFACE_HUB_CACHE'] = os.path.join(models_dir, 'huggingface', 'hub')
        os.environ['TRANSFORMERS_CACHE'] = os.path.join(models_dir, 'huggingface', 'transformers')
        
        # PyTorch 缓存目录
        os.environ['TORCH_HOME'] = os.path.join(models_dir, 'torch')
        
        # XDG 缓存目录（某些库会用）
        os.environ['XDG_CACHE_HOME'] = os.path.join(root, 'cache')
        
        # 禁止匿名数据收集
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['DO_NOT_TRACK'] = '1'
        os.environ['ANONYMIZED_TELEMETRY'] = 'false'
    
    def run_init_wizard(self, base_path: str = None):
        """交互式初始化"""
        # 先设置环境（确保所有缓存都在项目目录内）
        self.setup_environment(base_path)
        root = self.ensure_directories(base_path)
        
        print("🧠 欢迎使用 Recall - AI永久记忆系统")
        print("=" * 40)
        print(f"\n📂 数据目录：{root}")
        print("📦 所有数据都存储在此目录内，删除项目文件夹即可完全卸载。")
        print("   不会在用户目录或系统目录创建任何文件。")
        print("   你需要自己的 AI API key 来调用大模型。\n")
        
        # 获取 API key
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            print("支持的 API 提供商：")
            print("  - OpenAI (sk-xxx)")
            print("  - Claude (sk-ant-xxx)")
            print("  - 其他兼容 OpenAI 格式的 API\n")
            api_key = input("请输入你的 API key: ").strip()
        
        if not api_key:
            print("⚠️  未设置 API key，Recall 将只提供记忆存储功能，无法自动总结。")
        
        # 保存配置
        config = {
            'api_key': api_key,
            'initialized': True,
            'version': '3.0',
            'data_path': os.path.join(root, 'data'),
        }
        self._save_config(config, root)
        
        print("\n✅ 初始化完成！")
        print(f"   数据目录: {root}")
        print("\n🗑️ 卸载方法：")
        print(f"   1. pip uninstall recall-ai")
        print(f"   2. 删除目录: {root}")
        print("\n现在可以使用 'recall chat' 开始对话了！")
        
        return config
    
    def auto_init_for_st(self):
        """SillyTavern 自动初始化（静默）"""
        self.setup_environment()
        self.ensure_directories()
        # ST 用户在插件设置中配置 API key
        return {
            'api_key': None,  # 由 ST 插件配置
            'initialized': True,
            'st_plugin': True,
        }
    
    def _save_config(self, config, root):
        """保存配置到本地"""
        config_file = os.path.join(root, 'config.json')
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_config(cls, base_path: str = None) -> dict:
        """加载配置"""
        root = cls.get_data_root(base_path)
        config_file = os.path.join(root, 'config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    @classmethod
    def get_uninstall_instructions(cls, base_path: str = None) -> str:
        """返回完整卸载说明"""
        root = cls.get_data_root(base_path)
        return f"""
🗑️ 完整卸载 Recall（最简单的方式）：

方法一：直接删除项目文件夹（推荐）
- 所有数据都在项目目录内，删除整个项目文件夹即可

方法二：只删除 Recall 数据
- 删除数据目录：{root}
- 可选：pip uninstall recall-ai

✅ 卸载后系统完全恢复原状，不会在用户目录或系统目录留下任何文件。
"""
