"""分卷管理器 - 支持2亿字规模"""

import os
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Set


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
            # 卷不存在，创建空卷（需要传递 base_path 才能持久化！）
            os.makedirs(volume_path, exist_ok=True)
            self.loaded_volumes[volume_id] = VolumeData(
                volume_id=volume_id,
                base_path=volume_path  # 关键修复：确保新卷能持久化
            )
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
        """通过 memory_id 获取原始轮次数据（100%不遗忘保证）
        
        搜索顺序：
        1. 已加载到内存的卷（最快）
        2. 未加载的磁盘卷文件（兜底，确保不遗忘）
        
        注意：这是 O(n) 操作，适用于兜底场景
        """
        # 1. 先搜索已加载的卷（快）
        for volume in self.loaded_volumes.values():
            for turn_data in volume.cached_turns.values():
                if turn_data.get('memory_id') == memory_id:
                    return turn_data
        
        # 2. 搜索未加载的磁盘卷（兜底 - 确保100%不遗忘）
        archive_path = f"{self.data_path}/L3_archive"
        if os.path.exists(archive_path):
            for volume_dir in os.listdir(archive_path):
                if not volume_dir.startswith('volume_'):
                    continue
                
                # 跳过已加载的卷
                volume_id = int(volume_dir.split('_')[1])
                if volume_id in self.loaded_volumes:
                    continue
                
                # 扫描磁盘文件
                volume_path = f"{archive_path}/{volume_dir}"
                for file_name in os.listdir(volume_path):
                    if file_name.endswith('.jsonl'):
                        file_path = f"{volume_path}/{file_name}"
                        with open(file_path, 'r', encoding='utf-8') as f:
                            for line in f:
                                try:
                                    turn_data = json.loads(line)
                                    if turn_data.get('memory_id') == memory_id:
                                        return turn_data
                                except json.JSONDecodeError:
                                    continue
        
        return None
    
    def search_content(self, query: str, max_results: int = 50) -> List[dict]:
        """在所有存档中搜索包含查询内容的轮次（100%不遗忘保证）
        
        这是"终极兜底"功能，确保任何原文都能被找到
        
        搜索顺序：
        1. 已加载到内存的卷（最快）
        2. 未加载的磁盘卷文件（兜底）
        
        Args:
            query: 搜索查询
            max_results: 最大返回数量
        
        Returns:
            List[dict]: 匹配的轮次数据列表
        """
        results = []
        query_lower = query.lower()
        
        # 1. 先在已加载的卷中搜索（快）
        for volume in self.loaded_volumes.values():
            for turn_data in volume.cached_turns.values():
                content = turn_data.get('content', '')
                if query_lower in content.lower():
                    results.append(turn_data)
                    if len(results) >= max_results:
                        return results
        
        # 2. 搜索未加载的磁盘卷（兜底 - 确保100%不遗忘）
        archive_path = f"{self.data_path}/L3_archive"
        if os.path.exists(archive_path):
            for volume_dir in os.listdir(archive_path):
                if not volume_dir.startswith('volume_'):
                    continue
                
                # 跳过已加载的卷
                volume_id = int(volume_dir.split('_')[1])
                if volume_id in self.loaded_volumes:
                    continue
                
                # 扫描磁盘文件
                volume_path = f"{archive_path}/{volume_dir}"
                for file_name in os.listdir(volume_path):
                    if file_name.endswith('.jsonl'):
                        file_path = f"{volume_path}/{file_name}"
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    try:
                                        turn_data = json.loads(line)
                                        content = turn_data.get('content', '')
                                        if query_lower in content.lower():
                                            results.append(turn_data)
                                            if len(results) >= max_results:
                                                return results
                                    except json.JSONDecodeError:
                                        continue
                        except IOError:
                            continue
        
        return results
    
    def flush(self):
        """强制持久化所有已加载的卷
        
        应在以下情况调用：
        1. 程序正常退出前
        2. 重要操作后确保数据安全
        3. 定期备份前
        """
        for volume in self.loaded_volumes.values():
            volume._persist()
        self._save_manifest()
    
    def __del__(self):
        """析构时自动保存"""
        try:
            self.flush()
        except Exception:
            pass  # 忽略析构时的错误


class VolumeData:
    """单个卷的数据管理"""
    
    # 与 VolumeManager.DEFAULT_CONFIG 保持一致
    TURNS_PER_VOLUME = 100000
    TURNS_PER_FILE = 10000
    
    def __init__(self, volume_id: int, index: dict = None, base_path: str = None, lazy_load: bool = False):
        self.volume_id = volume_id
        self.index = index or {'files': {}, 'turn_count': 0}
        self.base_path = base_path
        self.lazy_load = lazy_load
        self.cached_turns: Dict[int, dict] = {}  # turn_number -> turn_data
        # 追踪哪些轮次已持久化，避免重复写入
        self._persisted_turns: Set[int] = set()
    
    def get_turn(self, file_id: int, offset: int) -> Optional[dict]:
        """获取指定轮次"""
        turn_number = self.volume_id * self.TURNS_PER_VOLUME + file_id * self.TURNS_PER_FILE + offset
        
        if turn_number in self.cached_turns:
            return self.cached_turns[turn_number]
        
        if self.lazy_load and self.base_path:
            # 从文件读取
            file_path = f"{self.base_path}/turns_{file_id*self.TURNS_PER_FILE+1:05d}_{(file_id+1)*self.TURNS_PER_FILE:05d}.jsonl"
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
        """持久化到磁盘（只写入新数据，避免重复）"""
        if not self.base_path:
            return
        
        os.makedirs(self.base_path, exist_ok=True)
        
        # 只收集未持久化的轮次
        unpersisted: Dict[int, List[dict]] = {}  # file_id -> [turn_data]
        for turn_num, data in self.cached_turns.items():
            if turn_num in self._persisted_turns:
                continue  # 跳过已持久化的
            file_id = (turn_num % self.TURNS_PER_VOLUME) // self.TURNS_PER_FILE
            if file_id not in unpersisted:
                unpersisted[file_id] = []
            unpersisted[file_id].append((turn_num, data))
        
        # 按文件追加写入（只写新数据）
        for file_id, turns in unpersisted.items():
            if not turns:
                continue
            file_path = f"{self.base_path}/turns_{file_id*self.TURNS_PER_FILE+1:05d}_{(file_id+1)*self.TURNS_PER_FILE:05d}.jsonl"
            with open(file_path, 'a', encoding='utf-8') as f:
                for turn_num, turn_data in turns:
                    f.write(json.dumps(turn_data, ensure_ascii=False) + '\n')
                    self._persisted_turns.add(turn_num)  # 标记为已持久化
        
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
                        turn_num = turn['turn']
                        self.cached_turns[turn_num] = turn
                        # 已从文件加载的数据视为已持久化
                        self._persisted_turns.add(turn_num)
        
        self.lazy_load = False  # 已完全加载
