"""实体索引 - 支持名称和别名的快速查找"""

import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


@dataclass
class IndexedEntity:
    """索引中的实体"""
    id: str
    name: str
    aliases: List[str]
    entity_type: str
    turn_references: List[str]  # 出现过的记忆ID (如 mem_xxx)
    confidence: float = 0.5  # 置信度 (0-1)
    # === Recall 4.1 新增字段 ===
    summary: str = ""                           # 实体摘要
    attributes: Dict[str, Any] = field(default_factory=dict)  # 动态属性
    last_summary_update: Optional[str] = None   # 摘要最后更新时间


class EntityIndex:
    """实体索引
    
    v7.0.3: WAL 增量写入模式
    - 每次 add/update 只追加到 WAL 文件（entity_index.wal.jsonl）
    - 通过脏标记控制全量快照频率（每 100 次变更或 flush 时执行）
    - 启动时先加载快照再回放 WAL
    - 快照使用原子写入保护
    """
    
    WAL_COMPACT_THRESHOLD = 100  # 每 100 次变更后合并 WAL 到快照
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.index_dir = os.path.join(data_path, 'indexes')
        self.index_file = os.path.join(self.index_dir, 'entity_index.json')
        self._wal_file = os.path.join(self.index_dir, 'entity_index.wal.jsonl')
        
        # 内存索引
        self.entities: Dict[str, IndexedEntity] = {}   # id → entity
        self.name_index: Dict[str, str] = {}           # name/alias → id
        self._dirty: bool = False
        self._wal_count: int = 0  # WAL 中未合并的变更数
        
        self._load()
        
        # v7.0.10: atexit 注册 — 进程退出时确保 WAL 被合并到快照
        import atexit
        atexit.register(self._shutdown_flush)
    
    def _load(self):
        """加载索引：先加载快照，再回放 WAL"""
        # 1. 加载快照
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        entity = IndexedEntity(**item)
                        self.entities[entity.id] = entity
                        self.name_index[entity.name.lower()] = entity.id
                        for alias in entity.aliases:
                            self.name_index[alias.lower()] = entity.id
            except Exception:
                pass
        
        # 2. 回放 WAL（追加在快照之后的增量变更）
        if os.path.exists(self._wal_file):
            wal_entries = 0
            try:
                with open(self._wal_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            entity = IndexedEntity(**item)
                            self.entities[entity.id] = entity
                            self.name_index[entity.name.lower()] = entity.id
                            for alias in entity.aliases:
                                self.name_index[alias.lower()] = entity.id
                            wal_entries += 1
                        except (json.JSONDecodeError, TypeError):
                            continue
            except Exception:
                pass
            # WAL 有内容说明需要合并
            if wal_entries > 0:
                self._dirty = True
                self._wal_count = wal_entries
    
    def _save(self):
        """保存索引（WAL 增量 + 周期性原子快照）
        
        v7.0.3: 每次变更只追加 WAL 行（O(1)），
        累计超过 WAL_COMPACT_THRESHOLD 次变更后执行全量原子快照。
        """
        if not self._dirty:
            return
        # 如果 WAL 累积足够多，做一次全量快照并清空 WAL
        if self._wal_count >= self.WAL_COMPACT_THRESHOLD:
            self._compact()
    
    def _shutdown_flush(self):
        """v7.0.10: 进程退出时强制刷盘（atexit 回调）"""
        try:
            if self._dirty:
                self._compact()
        except Exception:
            pass  # atexit 中不抛异常
    
    def _append_wal(self, entity: 'IndexedEntity'):
        """追加单条变更到 WAL 文件（O(1) 操作）"""
        try:
            os.makedirs(self.index_dir, exist_ok=True)
            with open(self._wal_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(entity), ensure_ascii=False) + '\n')
            self._wal_count += 1
        except Exception:
            pass  # WAL 写入失败不影响内存索引
    
    def _compact(self):
        """合并 WAL 到快照：原子写入全量快照，然后清空 WAL"""
        from recall.utils.atomic_write import atomic_json_dump
        os.makedirs(self.index_dir, exist_ok=True)
        atomic_json_dump([asdict(e) for e in self.entities.values()], self.index_file)
        # 清空 WAL
        try:
            if os.path.exists(self._wal_file):
                os.remove(self._wal_file)
        except Exception:
            pass
        self._dirty = False
        self._wal_count = 0
    
    def _mark_dirty(self):
        """标记数据已变更，需要写入"""
        self._dirty = True
    
    def flush(self):
        """强制将脏数据写入磁盘（执行全量快照 + 清空 WAL）"""
        if self._dirty:
            self._compact()
    
    def add(self, entity: IndexedEntity):
        """添加实体"""
        if entity.id in self.entities:
            # 合并引用
            existing = self.entities[entity.id]
            existing.turn_references = list(set(existing.turn_references + entity.turn_references))
            existing.aliases = list(set(existing.aliases + entity.aliases))
            # 如果已有实体类型是 UNKNOWN 且新实体类型有效，则更新类型
            if existing.entity_type == "UNKNOWN" and entity.entity_type != "UNKNOWN":
                existing.entity_type = entity.entity_type
        else:
            self.entities[entity.id] = entity
        
        # 更新名称索引
        self.name_index[entity.name.lower()] = entity.id
        for alias in entity.aliases:
            self.name_index[alias.lower()] = entity.id
        
        self._mark_dirty()
        # WAL 增量写入：只追加变更行，不做全量快照
        self._append_wal(self.entities[entity.id])
        self._save()  # 检查是否需要 compact
    
    def get_by_name(self, name: str) -> Optional[IndexedEntity]:
        """通过名称或别名查找"""
        entity_id = self.name_index.get(name.lower())
        if entity_id:
            return self.entities.get(entity_id)
        return None
    
    def get_by_id(self, entity_id: str) -> Optional[IndexedEntity]:
        """通过ID查找"""
        return self.entities.get(entity_id)
    
    def search(self, query: str) -> List[IndexedEntity]:
        """模糊搜索"""
        query_lower = query.lower()
        results = []
        seen_ids = set()
        
        for name, entity_id in self.name_index.items():
            if query_lower in name and entity_id not in seen_ids:
                entity = self.entities[entity_id]
                results.append(entity)
                seen_ids.add(entity_id)
        
        return results
    
    def all_entities(self) -> List[IndexedEntity]:
        """返回所有实体"""
        return list(self.entities.values())
    
    def get_top_entities(self, limit: int = 100) -> List[IndexedEntity]:
        """获取最常引用的实体（用于预热缓存）"""
        sorted_entities = sorted(
            self.entities.values(),
            key=lambda e: len(e.turn_references),
            reverse=True
        )
        return sorted_entities[:limit]
    
    def add_entity_occurrence(self, entity_name: str, turn_id: str, context: str = "", 
                              entity_type: str = "UNKNOWN", aliases: List[str] = None,
                              confidence: float = 0.5) -> None:
        """添加实体出现记录
        
        Args:
            entity_name: 实体名称
            turn_id: 轮次/记忆ID
            context: 上下文文本
            entity_type: 实体类型 (PERSON, LOCATION, ITEM, ORG, CODE_SYMBOL 等)
            aliases: 实体别名列表
            confidence: 置信度 (0-1)
        """
        # 查找或创建实体
        existing = self.get_by_name(entity_name)
        
        if existing:
            # 更新已有实体
            if turn_id not in existing.turn_references:
                existing.turn_references.append(turn_id)
            # 如果已有实体类型是 UNKNOWN 且新传入的类型有效，则更新类型
            if existing.entity_type == "UNKNOWN" and entity_type != "UNKNOWN":
                existing.entity_type = entity_type
            # 合并别名
            if aliases:
                existing.aliases = list(set(existing.aliases + aliases))
                # 同时更新别名索引
                for alias in aliases:
                    self.name_index[alias.lower()] = existing.id
            # 更新置信度（取较高值）
            if confidence > existing.confidence:
                existing.confidence = confidence
            self._mark_dirty()
            self._append_wal(existing)
            self._save()  # 检查是否需要 compact
        else:
            # 创建新实体
            import uuid
            entity = IndexedEntity(
                id=f"ent_{uuid.uuid4().hex[:8]}",
                name=entity_name,
                aliases=aliases or [],
                entity_type=entity_type,
                turn_references=[turn_id],
                confidence=confidence
            )
            self.add(entity)
    
    def get_related_turns(self, entity_name: str) -> List[IndexedEntity]:
        """获取实体相关的轮次
        
        Args:
            entity_name: 实体名称
        
        Returns:
            List[IndexedEntity]: 包含该实体的实体列表（携带 turn_references）
        """
        results = self.search(entity_name)
        return results
    
    def get_entity(self, name: str) -> Optional[IndexedEntity]:
        """通过名称获取实体（get_by_name 的别名）"""
        return self.get_by_name(name)
    
    def remove_by_turn_references(self, turn_ids: List[str]) -> int:
        """移除与指定记忆ID关联的实体引用
        
        遍历所有实体，从 turn_references 中移除指定的记忆ID。
        如果实体的 turn_references 变为空，则删除该实体。
        
        Args:
            turn_ids: 要移除的记忆ID列表
        
        Returns:
            int: 被完全删除的实体数量
        """
        if not turn_ids:
            return 0
        
        turn_id_set = set(turn_ids)
        entities_to_delete = []
        
        for entity_id, entity in self.entities.items():
            # 过滤掉被删除的记忆引用
            remaining_refs = [
                ref for ref in entity.turn_references 
                if ref not in turn_id_set
            ]
            
            if not remaining_refs:
                # 没有剩余引用，标记删除
                entities_to_delete.append(entity_id)
            elif len(remaining_refs) != len(entity.turn_references):
                # 有部分引用被移除，更新
                entity.turn_references = remaining_refs
        
        # 删除无引用的实体
        for entity_id in entities_to_delete:
            entity = self.entities[entity_id]
            # v7.0.6: 清理名称索引时，必须校验索引条目确实指向本实体
            # （之前直接 del，会误删共享同名/别名的其他实体的索引条目）
            if self.name_index.get(entity.name.lower()) == entity_id:
                del self.name_index[entity.name.lower()]
            for alias in entity.aliases:
                if self.name_index.get(alias.lower()) == entity_id:
                    del self.name_index[alias.lower()]
            del self.entities[entity_id]
        
        if entities_to_delete or turn_ids:
            self._mark_dirty()
            self._compact()  # 删除操作直接做全量快照（WAL 不支持删除语义）
        
        return len(entities_to_delete)
    
    def clear(self):
        """清空所有实体索引"""
        self.entities.clear()
        self.name_index.clear()
        self._mark_dirty()
        self._compact()  # 清空操作直接做全量快照
    
    # === Recall 4.1 新增方法 ===
    
    def update_entity_fields(
        self,
        entity_name: str,
        summary: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        last_summary_update: Optional[str] = None
    ) -> bool:
        """更新实体的扩展字段 (Recall 4.1)
        
        Args:
            entity_name: 实体名称
            summary: 实体摘要
            attributes: 动态属性字典
            last_summary_update: 摘要最后更新时间
        
        Returns:
            bool: 是否成功
        """
        entity = self.get_entity(entity_name)
        if not entity:
            return False
        
        if summary is not None:
            entity.summary = summary
        if attributes is not None:
            entity.attributes.update(attributes)
        if last_summary_update is not None:
            entity.last_summary_update = last_summary_update
        
        self._mark_dirty()
        self._append_wal(entity)
        self._save()  # 检查是否需要 compact
        return True
    
    def get_entities_needing_summary(self, min_facts: int = 5) -> List[IndexedEntity]:
        """获取需要生成摘要的实体 (Recall 4.1)
        
        Args:
            min_facts: 最小事实数阈值
        
        Returns:
            List[IndexedEntity]: 需要摘要的实体列表
        """
        return [
            entity for entity in self.entities.values()
            if len(entity.turn_references) >= min_facts and not entity.summary
        ]
