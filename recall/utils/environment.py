"""环境管理器 - 管理运行环境和隔离"""

import os
import sys
import json
import shutil
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnvironmentInfo:
    """环境信息"""
    python_version: str
    platform: str
    data_root: str
    config_path: str
    is_isolated: bool
    installed_packages: Dict[str, str]


class EnvironmentManager:
    """环境管理器
    
    确保运行环境与系统隔离：
    1. 数据存储在项目目录内
    2. 模型缓存在项目目录内
    3. 配置独立于系统配置
    """
    
    def __init__(self, data_root: Optional[str] = None):
        # 确定数据根目录
        if data_root:
            self.data_root = Path(data_root)
        else:
            # 默认使用当前工作目录下的 recall_data
            self.data_root = Path.cwd() / 'recall_data'
        
        # 各子目录
        self.dirs = {
            'config': self.data_root / 'config',
            'data': self.data_root / 'data',
            'models': self.data_root / 'models',
            'cache': self.data_root / 'cache',
            'logs': self.data_root / 'logs',
            'temp': self.data_root / 'temp'
        }
    
    def setup(self) -> bool:
        """设置环境"""
        try:
            # 创建目录结构
            for dir_path in self.dirs.values():
                dir_path.mkdir(parents=True, exist_ok=True)
            
            # 设置环境变量（重定向缓存）
            self._setup_cache_dirs()
            
            # 创建默认配置
            self._create_default_config()
            
            return True
        
        except Exception as e:
            print(f"[Recall] 环境设置失败: {e}")
            return False
    
    def _setup_cache_dirs(self):
        """设置缓存目录（避免污染系统目录）"""
        cache_dir = str(self.dirs['cache'])
        
        # HuggingFace模型缓存
        os.environ['HF_HOME'] = str(self.dirs['models'] / 'huggingface')
        os.environ['TRANSFORMERS_CACHE'] = str(self.dirs['models'] / 'transformers')
        
        # Torch模型缓存
        os.environ['TORCH_HOME'] = str(self.dirs['models'] / 'torch')
        
        # spaCy模型缓存
        os.environ['SPACY_DATA'] = str(self.dirs['models'] / 'spacy')
        
        # 通用缓存
        os.environ['XDG_CACHE_HOME'] = cache_dir
    
    def _create_default_config(self):
        """创建默认配置文件"""
        config_path = self.dirs['config'] / 'recall.json'
        
        if not config_path.exists():
            default_config = {
                'version': '3.0.0',
                'data_root': str(self.data_root),
                'llm': {
                    'model': 'gpt-4o-mini',
                    'api_key_env': 'LLM_API_KEY'  # 优先使用 LLM_API_KEY，兼容 OPENAI_API_KEY
                },
                'storage': {
                    'max_memories_per_user': 10000,
                    'auto_consolidate': True
                },
                'retrieval': {
                    'default_top_k': 10,
                    'use_vector_search': True
                }
            }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
    
    def get_info(self) -> EnvironmentInfo:
        """获取环境信息"""
        import platform
        
        # 获取已安装包
        packages = self._get_installed_packages()
        
        return EnvironmentInfo(
            python_version=sys.version,
            platform=platform.platform(),
            data_root=str(self.data_root),
            config_path=str(self.dirs['config'] / 'recall.json'),
            is_isolated=self._check_isolated(),
            installed_packages=packages
        )
    
    def _get_installed_packages(self) -> Dict[str, str]:
        """获取已安装的包"""
        packages = {}
        try:
            import pkg_resources
            for pkg in pkg_resources.working_set:
                packages[pkg.key] = pkg.version
        except:
            pass
        return packages
    
    def _check_isolated(self) -> bool:
        """检查是否隔离"""
        # 检查数据目录是否在项目内
        cwd = Path.cwd()
        return str(self.data_root).startswith(str(cwd))
    
    def get_path(self, key: str) -> Path:
        """获取路径"""
        return self.dirs.get(key, self.data_root / key)
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置"""
        config_path = self.dirs['config'] / 'recall.json'
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_config(self, config: Dict[str, Any]):
        """保存配置"""
        config_path = self.dirs['config'] / 'recall.json'
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def cleanup_temp(self):
        """清理临时文件"""
        temp_dir = self.dirs['temp']
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
    
    def cleanup_cache(self, older_than_days: int = 7):
        """清理过期缓存"""
        import time
        
        cache_dir = self.dirs['cache']
        if not cache_dir.exists():
            return
        
        cutoff = time.time() - (older_than_days * 24 * 3600)
        
        for item in cache_dir.rglob('*'):
            if item.is_file():
                if item.stat().st_mtime < cutoff:
                    try:
                        item.unlink()
                    except:
                        pass
    
    def get_disk_usage(self) -> Dict[str, int]:
        """获取磁盘使用情况"""
        usage = {}
        
        for name, path in self.dirs.items():
            if path.exists():
                total_size = sum(
                    f.stat().st_size
                    for f in path.rglob('*')
                    if f.is_file()
                )
                usage[name] = total_size
        
        return usage
    
    def print_status(self):
        """打印环境状态"""
        info = self.get_info()
        usage = self.get_disk_usage()
        
        print("\n=== Recall 环境状态 ===")
        print(f"Python: {info.python_version.split()[0]}")
        print(f"平台: {info.platform}")
        print(f"数据目录: {info.data_root}")
        print(f"隔离模式: {'是' if info.is_isolated else '否'}")
        print("\n磁盘使用:")
        for name, size in usage.items():
            size_mb = size / 1024 / 1024
            print(f"  {name}: {size_mb:.2f} MB")
        print()


# 全局环境管理器
_global_env_manager: Optional[EnvironmentManager] = None


def get_env_manager() -> EnvironmentManager:
    """获取全局环境管理器"""
    global _global_env_manager
    if _global_env_manager is None:
        _global_env_manager = EnvironmentManager()
    return _global_env_manager
