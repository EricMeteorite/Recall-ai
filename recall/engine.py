"""Recall 核心引擎 - 统一的记忆管理入口"""

import os
import time
import uuid
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

from .version import __version__
from .init import RecallInit
from .config import LightweightConfig
from .models import Entity, Turn, Foreshadowing, Event, EntityType, EventType
from .storage import (
    VolumeManager, CoreSettings, ConsolidatedMemory,
    WorkingMemory, MultiTenantStorage, MemoryScope
)
from .index import EntityIndex, InvertedIndex, VectorIndex, OptimizedNgramIndex
from .graph import KnowledgeGraph, RelationExtractor
from .processor import (
    EntityExtractor, ForeshadowingTracker,
    ConsistencyChecker, MemorySummarizer, ScenarioDetector
)
from .retrieval import EightLayerRetriever, ContextBuilder, ParallelRetriever
from .utils import (
    LLMClient, WarmupManager, PerformanceMonitor,
    EnvironmentManager, AutoMaintainer
)
from .utils.perf_monitor import MetricType


@dataclass
class AddResult:
    """添加记忆结果"""
    id: str
    success: bool
    entities: List[str] = field(default_factory=list)
    message: str = ""


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    entities: List[str] = field(default_factory=list)


class RecallEngine:
    """Recall 核心引擎
    
    主要功能：
    1. 记忆存储和检索
    2. 实体和关系管理
    3. 伏笔追踪
    4. 一致性检查
    5. 上下文构建
    
    使用示例：
    ```python
    from recall import RecallEngine
    
    # 初始化
    engine = RecallEngine()
    
    # 添加记忆
    result = engine.add("用户喜欢喝咖啡", user_id="user1")
    
    # 搜索记忆
    memories = engine.search("咖啡", user_id="user1")
    
    # 构建上下文
    context = engine.build_context(
        query="推荐一些饮品",
        user_id="user1"
    )
    ```
    """
    
    def __init__(
        self,
        data_root: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        lightweight: bool = False,
        auto_warmup: bool = True
    ):
        """初始化 Recall 引擎
        
        Args:
            data_root: 数据存储根目录，默认为 ./recall_data
            llm_model: LLM 模型名称，默认为 gpt-3.5-turbo
            llm_api_key: LLM API Key
            lightweight: 是否使用轻量模式（约80MB内存）
            auto_warmup: 是否自动预热模型
        """
        # 1. 初始化环境
        self.env_manager = EnvironmentManager(data_root)
        self.env_manager.setup()
        self.data_root = str(self.env_manager.data_root)
        
        # 2. 加载配置
        self.config = self.env_manager.load_config()
        self.lightweight = lightweight
        
        # 3. 初始化组件
        self._init_components(llm_model, llm_api_key)
        
        # 4. 预热
        if auto_warmup and not lightweight:
            self._warmup()
        
        print(f"[Recall v{__version__}] 引擎初始化完成")
    
    def _init_components(
        self,
        llm_model: Optional[str],
        llm_api_key: Optional[str]
    ):
        """初始化各组件"""
        # LLM客户端
        model = llm_model or self.config.get('llm', {}).get('model', 'gpt-3.5-turbo')
        api_key = llm_api_key or os.environ.get('OPENAI_API_KEY')
        self.llm_client = LLMClient(model=model, api_key=api_key) if api_key else None
        
        # 存储层
        self.storage = MultiTenantStorage(
            base_path=os.path.join(self.data_root, 'data')
        )
        
        # 索引层（轻量模式延迟加载）
        self._entity_index: Optional[EntityIndex] = None
        self._inverted_index: Optional[InvertedIndex] = None
        self._vector_index: Optional[VectorIndex] = None
        self._ngram_index: Optional[OptimizedNgramIndex] = None
        
        if not self.lightweight:
            self._init_indexes()
        
        # 处理器层（需要先初始化，因为图谱层依赖）
        self.entity_extractor = EntityExtractor()
        self.foreshadowing_tracker = ForeshadowingTracker(
            storage_path=os.path.join(self.data_root, 'data', 'foreshadowing.json')
        )
        self.consistency_checker = ConsistencyChecker()
        self.memory_summarizer = MemorySummarizer(llm_client=self.llm_client)
        self.scenario_detector = ScenarioDetector()
        
        # 图谱层
        self.knowledge_graph = KnowledgeGraph(
            data_path=os.path.join(self.data_root, 'data')
        )
        self.relation_extractor = RelationExtractor(
            entity_extractor=self.entity_extractor
        )
        
        # 检索层
        self.retriever = EightLayerRetriever(
            inverted_index=self._inverted_index,
            entity_index=self._entity_index,
            ngram_index=self._ngram_index,
            vector_index=self._vector_index,
            llm_client=self.llm_client
        )
        self.context_builder = ContextBuilder()
        
        # 监控
        self.monitor = PerformanceMonitor(auto_collect=False)
    
    def _init_indexes(self):
        """初始化索引"""
        index_path = os.path.join(self.data_root, 'index')
        os.makedirs(index_path, exist_ok=True)
        
        self._entity_index = EntityIndex(data_path=self.data_root)
        self._inverted_index = InvertedIndex(data_path=self.data_root)
        self._vector_index = VectorIndex(data_path=self.data_root)
        self._ngram_index = OptimizedNgramIndex()
    
    def _warmup(self):
        """预热模型"""
        warmup_manager = WarmupManager()
        
        # 注册预热任务
        warmup_manager.register(
            'entity_extractor',
            lambda: self.entity_extractor.nlp,
            priority=10
        )
        
        if self._vector_index:
            warmup_manager.register(
                'vector_model',
                lambda: self._vector_index.model,
                priority=5
            )
        
        # 后台预热
        warmup_manager.warmup_async()
    
    # ==================== 核心 API ====================
    
    def add(
        self,
        content: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        check_consistency: bool = True
    ) -> AddResult:
        """添加记忆
        
        Args:
            content: 记忆内容
            user_id: 用户ID
            metadata: 元数据
            check_consistency: 是否检查一致性
        
        Returns:
            AddResult: 添加结果
        """
        start_time = time.time()
        
        try:
            # 1. 提取实体
            entities = self.entity_extractor.extract(content)
            entity_names = [e.name for e in entities]
            
            # 2. 提取关键词
            keywords = self.entity_extractor.extract_keywords(content)
            
            # 3. 一致性检查
            if check_consistency:
                existing_memories = self.search(content, user_id=user_id, top_k=5)
                consistency = self.consistency_checker.check(
                    content,
                    [{'content': m.content} for m in existing_memories]
                )
                if not consistency.is_consistent:
                    # 记录但不阻止
                    for v in consistency.violations:
                        print(f"[Recall] 一致性警告: {v.description}")
            
            # 4. 生成ID并存储
            memory_id = f"mem_{uuid.uuid4().hex[:12]}"
            
            memory_data = {
                'id': memory_id,
                'content': content,
                'user_id': user_id,
                'entities': entity_names,
                'keywords': keywords,
                'metadata': metadata or {},
                'created_at': time.time()
            }
            
            # 存储到作用域
            scope = self.storage.get_scope(user_id)
            scope.add(content, metadata={
                'id': memory_id,
                'entities': entity_names,
                'keywords': keywords,
                **(metadata or {})
            })
            
            # 5. 更新索引
            if self._entity_index:
                for entity in entities:
                    self._entity_index.add_entity_occurrence(
                        entity_name=entity.name,
                        turn_id=memory_id,
                        context=content[:200]
                    )
            
            if self._inverted_index:
                self._inverted_index.add(memory_id, keywords)
            
            if self._ngram_index:
                # NgamIndex.add 接受 (turn_id, content)
                self._ngram_index.add(memory_id, content)
            
            if self._vector_index:
                # VectorIndex.add_text 接受 (turn_id, text)
                self._vector_index.add_text(memory_id, content)
            
            # 6. 更新知识图谱
            relations = self.relation_extractor.extract(content, 0)  # 传入turn=0
            for rel in relations:
                source_id, relation_type, target_id, source_text = rel
                self.knowledge_graph.add_relation(
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation_type,
                    source_text=source_text
                )
            
            # 记录性能
            try:
                self.monitor.record(
                    MetricType.LATENCY,
                    (time.time() - start_time) * 1000
                )
            except Exception:
                pass  # 忽略性能监控错误
            
            return AddResult(
                id=memory_id,
                success=True,
                entities=entity_names,
                message="记忆添加成功"
            )
        
        except Exception as e:
            return AddResult(
                id="",
                success=False,
                message=f"添加失败: {str(e)}"
            )
    
    def search(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """搜索记忆
        
        Args:
            query: 搜索查询
            user_id: 用户ID
            top_k: 返回数量
            filters: 过滤条件
        
        Returns:
            List[SearchResult]: 搜索结果
        """
        # 1. 提取查询实体和关键词
        entities = [e.name for e in self.entity_extractor.extract(query)]
        keywords = self.entity_extractor.extract_keywords(query)
        
        # 2. 检测场景
        scenario = self.scenario_detector.detect(query)
        
        # 3. 执行检索
        retrieval_results = self.retriever.retrieve(
            query=query,
            entities=entities,
            keywords=keywords,
            top_k=top_k,
            filters=filters
        )
        
        # 4. 补充从存储获取
        scope = self.storage.get_scope(user_id)
        stored_memories = scope.search(query, limit=top_k)
        
        # 5. 合并结果
        results = []
        seen_ids = set()
        
        for r in retrieval_results:
            if r.id not in seen_ids:
                results.append(SearchResult(
                    id=r.id,
                    content=r.content,
                    score=r.score,
                    metadata=r.metadata,
                    entities=r.entities
                ))
                seen_ids.add(r.id)
        
        for m in stored_memories:
            mem_id = m.get('metadata', {}).get('id', '') or m.get('id', '')
            if mem_id and mem_id not in seen_ids:
                results.append(SearchResult(
                    id=mem_id,
                    content=m.get('content', m.get('memory', '')),
                    score=m.get('score', 0.5),
                    metadata=m.get('metadata', {}),
                    entities=m.get('entities', [])
                ))
                seen_ids.add(mem_id)
        
        return results[:top_k]
    
    def get_all(
        self,
        user_id: str = "default",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取所有记忆
        
        Args:
            user_id: 用户ID
            limit: 限制数量
        
        Returns:
            List[Dict]: 记忆列表
        """
        scope = self.storage.get_scope(user_id)
        return scope.get_all(limit=limit)
    
    def get(
        self,
        memory_id: str,
        user_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        """获取单条记忆
        
        Args:
            memory_id: 记忆ID
            user_id: 用户ID
        
        Returns:
            Dict: 记忆数据，如果不存在则返回 None
        """
        scope = self.storage.get_scope(user_id)
        all_memories = scope.get_all()
        for memory in all_memories:
            if memory.get('metadata', {}).get('id') == memory_id:
                return memory
        return None
    
    def clear(
        self,
        user_id: str = "default"
    ) -> bool:
        """清空用户的所有记忆
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否成功
        """
        scope = self.storage.get_scope(user_id)
        scope.clear()
        return True
    
    def stats(self) -> Dict[str, Any]:
        """获取统计信息（get_stats 的别名）"""
        return self.get_stats()
    
    def delete(
        self,
        memory_id: str,
        user_id: str = "default"
    ) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆ID
            user_id: 用户ID
        
        Returns:
            bool: 是否成功
        """
        scope = self.storage.get_scope(user_id)
        return scope.delete(memory_id)
    
    def update(
        self,
        memory_id: str,
        content: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新记忆
        
        Args:
            memory_id: 记忆ID
            content: 新内容
            user_id: 用户ID
            metadata: 新元数据
        
        Returns:
            bool: 是否成功
        """
        scope = self.storage.get_scope(user_id)
        return scope.update(memory_id, content, metadata)
    
    def build_context(
        self,
        query: str,
        user_id: str = "default",
        max_tokens: int = 2000,
        include_recent: int = 5
    ) -> str:
        """构建上下文
        
        Args:
            query: 当前查询
            user_id: 用户ID
            max_tokens: 最大token数
            include_recent: 包含的最近对话数
        
        Returns:
            str: 构建的上下文
        """
        # 1. 搜索相关记忆
        memories = self.search(query, user_id=user_id, top_k=10)
        
        # 2. 获取最近对话
        scope = self.storage.get_scope(user_id)
        recent = scope.get_recent(include_recent)
        
        # 3. 构建上下文
        context = self.context_builder.build(
            memories=[m.__dict__ for m in memories],
            recent_turns=recent,
            query=query,
            config={'memory_ratio': 0.6}
        )
        
        return context.to_prompt()
    
    # ==================== 伏笔 API ====================
    
    def plant_foreshadowing(
        self,
        content: str,
        related_entities: Optional[List[str]] = None,
        importance: float = 0.5
    ) -> Foreshadowing:
        """埋下伏笔"""
        return self.foreshadowing_tracker.plant(
            content=content,
            related_entities=related_entities,
            importance=importance
        )
    
    def resolve_foreshadowing(
        self,
        foreshadowing_id: str,
        resolution: str
    ) -> bool:
        """解决伏笔"""
        return self.foreshadowing_tracker.resolve(foreshadowing_id, resolution)
    
    def get_active_foreshadowings(self) -> List[Foreshadowing]:
        """获取活跃伏笔"""
        return self.foreshadowing_tracker.get_active()
    
    # ==================== 实体 API ====================
    
    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """获取实体信息"""
        if self._entity_index:
            indexed = self._entity_index.get_entity(name)
            if indexed:
                return {
                    'name': indexed.name,
                    'type': indexed.entity_type,
                    'aliases': indexed.aliases,
                    'mention_count': indexed.mention_count,
                    'related_turns': [t.turn_id for t in indexed.turns[:10]]
                }
        return None
    
    def get_related_entities(self, name: str) -> List[str]:
        """获取相关实体"""
        return self.knowledge_graph.get_neighbors(name)
    
    # ==================== 管理 API ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'version': __version__,
            'data_root': self.data_root,
            'lightweight': self.lightweight,
            'storage': {
                'scopes': len(self.storage._scopes)
            },
            'indexes': {
                'entity_index': self._entity_index is not None,
                'vector_index': self._vector_index is not None
            },
            'foreshadowings': {
                'active': len(self.foreshadowing_tracker.get_active())
            },
            'performance': self.monitor.get_all_stats() if hasattr(self.monitor, 'get_all_stats') else {}
        }
    
    def consolidate(self, user_id: str = "default"):
        """执行记忆整合"""
        scope = self.storage.get_scope(user_id)
        
        # 获取工作记忆
        working = scope.get_all()
        
        # 使用摘要器压缩
        from .processor.memory_summarizer import MemoryItem, MemoryPriority
        items = [
            MemoryItem(
                id=m.get('id', ''),
                content=m.get('content', m.get('memory', '')),
                user_id=user_id,
                priority=MemoryPriority.NORMAL
            )
            for m in working
        ]
        
        # 合并相似记忆
        merged = self.memory_summarizer.merge_similar(items)
        
        # 移动到整合层
        # TODO: 实现实际的整合逻辑
        
        print(f"[Recall] 整合完成: {len(working)} -> {len(merged)}")
    
    def reset(self, user_id: Optional[str] = None):
        """重置（谨慎使用）"""
        if user_id:
            scope = self.storage.get_scope(user_id)
            scope.clear()
        else:
            # 重置所有
            self.storage = MultiTenantStorage(
                base_path=os.path.join(self.data_root, 'data')
            )
            if not self.lightweight:
                self._init_indexes()
        
        print(f"[Recall] 重置完成")
    
    def close(self):
        """关闭引擎"""
        # 保存索引
        if self._vector_index:
            self._vector_index.save()
        
        print("[Recall] 引擎已关闭")


# 便捷函数
def create_engine(**kwargs) -> RecallEngine:
    """创建引擎的便捷函数"""
    return RecallEngine(**kwargs)
