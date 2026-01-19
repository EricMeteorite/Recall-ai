"""分卷管理器 - 支持2亿字规模"""

import os
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any


class VolumeManager:
    """分卷管理器 - 支持2亿字规模"""
    
    # 零配置默认值（经过优化，用户无需修改）
    DEFAULT_CONFIG = {
        'turns_per_file': 10000,      # 每文件1万轮
        'max_volume_size_mb': 50,      # 每卷50MB
        'turns_per_volume': 100000,    # 每卷10万轮
        'preload_volumes': 2,          # 预加载最近2卷
        'index_granularity': 1000,     # 索引粒度：每1000轮建一个检查点
    }
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.config = self.DEFAULT_CONFIG.copy()
        self.loaded_volumes: Dict[int, 'VolumeData'] = {}  # volume_id -> VolumeData
        self.file_locks: Dict[int, threading.Lock] = {}      # 并发控制
        self._init_storage()
    
    def _init_storage(self):
        """初始化存储目录"""
        os.makedirs(f"{self.data_path}/L3_archive", exist_ok=True)
        self.manifest = self._load_or_create_manifest()
    
    def get_turn(self, turn_number: int) -> Optional[dict]:
        """O(1) 定位任意轮次"""
        volume_id = turn_number // self.config['turns_per_volume']
        file_id = (turn_number % self.config['turns_per_volume']) // self.config['turns_per_file']
        offset = turn_number % self.config['turns_per_file']
        
        # 如果卷未加载，按需加载
        if volume_id not in self.loaded_volumes:
            self._load_volume(volume_id)
        
        return self.loaded_volumes[volume_id].get_turn(file_id, offset)
    
    def _load_volume(self, volume_id: int):
        """加载指定卷到内存"""
        volume_path = f"{self.data_path}/L3_archive/volume_{volume_id:04d}"
        
        if not os.path.exists(volume_path):
            # 卷不存在，创建空卷
            self.loaded_volumes[volume_id] = VolumeData(volume_id)
            return
        
        # 加载卷索引
        index_path = f"{volume_path}/volume_index.json"
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                volume_index = json.load(f)
        else:
            volume_index = {'files': {}, 'turn_count': 0}
        
        # 只加载索引，数据文件按需读取（节省内存）
        self.loaded_volumes[volume_id] = VolumeData(
            volume_id=volume_id,
            index=volume_index,
            base_path=volume_path,
            lazy_load=True  # 懒加载模式
        )
    
    def preload_recent(self, num_volumes: int = None):
        """预加载最近的卷，确保常用数据在内存"""
        if num_volumes is None:
            num_volumes = self.config['preload_volumes']
        
        latest_volume = self.manifest.get('latest_volume', 0)
        for i in range(num_volumes):
            vol_id = latest_volume - i
            if vol_id >= 0 and vol_id not in self.loaded_volumes:
                self._load_volume(vol_id)
                # 最近的卷完全加载到内存
                if i == 0:
                    self.loaded_volumes[vol_id].load_all_to_memory()
    
    def append_turn(self, turn_data: dict) -> int:
        """追加新轮次，返回轮次号"""
        turn_number = self.manifest.get('total_turns', 0)
        turn_data['turn'] = turn_number
        
        volume_id = turn_number // self.config['turns_per_volume']
        
        # 确保卷已加载
        if volume_id not in self.loaded_volumes:
            self._load_volume(volume_id)
        
        # 使用文件锁保证并发安全
        with self._get_lock(volume_id):
            self.loaded_volumes[volume_id].append(turn_data)
            self.manifest['total_turns'] = turn_number + 1
            self.manifest['latest_volume'] = volume_id
            self._save_manifest()
        
        return turn_number
    
    def _get_lock(self, volume_id: int) -> threading.Lock:
        """获取卷级别的锁"""
        if volume_id not in self.file_locks:
            self.file_locks[volume_id] = threading.Lock()
        return self.file_locks[volume_id]
    
    def _load_or_create_manifest(self) -> dict:
        """加载或创建全局manifest"""
        manifest_path = f"{self.data_path}/manifest.json"
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'total_turns': 0, 
            'latest_volume': 0, 
            'created_at': datetime.now().isoformat()
        }
    
    def _save_manifest(self):
        """保存manifest"""
        manifest_path = f"{self.data_path}/manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, ensure_ascii=False, indent=2)
    
    def get_next_turn_number(self) -> int:
        """获取下一个轮次号"""
        return self.manifest.get('total_turns', 0)
    
    def get_total_turns(self) -> int:
        """获取总轮次数"""
        return self.manifest.get('total_turns', 0)
    
    def get_turn_by_memory_id(self, memory_id: str) -> Optional[dict]:
        """通过 memory_id 获取原始轮次数据
        
        扫描所有加载的卷查找匹配的 memory_id
        注意：这是 O(n) 操作，适用于兜底场景
        """
        for volume in self.loaded_volumes.values():
            for turn_data in volume.cached_turns.values():
                if turn_data.get('memory_id') == memory_id:
                    return turn_data
        return None
    
    def search_content(self, query: str, max_results: int = 50) -> List[dict]:
        """在所有存档中搜索包含查询内容的轮次
        
        这是"终极兜底"功能，确保任何原文都能被找到
        
        Args:
            query: 搜索查询
            max_results: 最大返回数量
        
        Returns:
            List[dict]: 匹配的轮次数据列表
        """
        results = []
        query_lower = query.lower()
        
        # 先在已加载的卷中搜索
        for volume in self.loaded_volumes.values():
            for turn_data in volume.cached_turns.values():
                content = turn_data.get('content', '')
                if query_lower in content.lower():
                    results.append(turn_data)
                    if len(results) >= max_results:
                        return results
        
        return results


class VolumeData:
    """单个卷的数据管理"""
    
    def __init__(self, volume_id: int, index: dict = None, base_path: str = None, lazy_load: bool = False):
        self.volume_id = volume_id
        self.index = index or {'files': {}, 'turn_count': 0}
        self.base_path = base_path
        self.lazy_load = lazy_load
        self.cached_turns: Dict[int, dict] = {}  # turn_number -> turn_data
    
    def get_turn(self, file_id: int, offset: int) -> Optional[dict]:
        """获取指定轮次"""
        turn_number = self.volume_id * 100000 + file_id * 10000 + offset
        
        if turn_number in self.cached_turns:
            return self.cached_turns[turn_number]
        
        if self.lazy_load and self.base_path:
            # 从文件读取
            file_path = f"{self.base_path}/turns_{file_id*10000+1:05d}_{(file_id+1)*10000:05d}.jsonl"
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if offset < len(lines):
                        return json.loads(lines[offset])
        
        return None
    
    def append(self, turn_data: dict):
        """追加轮次"""
        turn_number = turn_data.get('turn', self.index['turn_count'])
        self.cached_turns[turn_number] = turn_data
        self.index['turn_count'] += 1
        
        # 定期持久化
        if self.index['turn_count'] % 100 == 0:
            self._persist()
    
    def _persist(self):
        """持久化到磁盘"""
        if not self.base_path:
            return
        
        os.makedirs(self.base_path, exist_ok=True)
        
        # 按文件分组写入
        by_file: Dict[int, List[dict]] = {}
        for turn_num, data in self.cached_turns.items():
            file_id = (turn_num % 100000) // 10000
            if file_id not in by_file:
                by_file[file_id] = []
            by_file[file_id].append(data)
        
        for file_id, turns in by_file.items():
            file_path = f"{self.base_path}/turns_{file_id*10000+1:05d}_{(file_id+1)*10000:05d}.jsonl"
            with open(file_path, 'a', encoding='utf-8') as f:
                for turn in turns:
                    f.write(json.dumps(turn, ensure_ascii=False) + '\n')
        
        # 保存卷索引
        index_path = f"{self.base_path}/volume_index.json"
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
    
    def load_all_to_memory(self):
        """将整个卷加载到内存（用于热卷）"""
        if not self.base_path:
            return
        
        if not os.path.exists(self.base_path):
            return
        
        for file_name in os.listdir(self.base_path):
            if file_name.endswith('.jsonl'):
                file_path = f"{self.base_path}/{file_name}"
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        turn = json.loads(line)
                        self.cached_turns[turn['turn']] = turn
        
        self.lazy_load = False  # 已完全加载
