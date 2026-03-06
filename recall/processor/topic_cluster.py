"""主题聚类器 - Recall 7.3 Phase C

主题级关联层:
1. 在 ingestion 时提取 2-5 个主题标签 (关键词 + 可选 LLM)
2. 拥有相同主题标签的记忆自动建立 TOPIC_RELATED 边
3. 支持层级概念扩展
4. 主题搜索: 检索某主题下的所有记忆
"""

from __future__ import annotations

import os
import re
import json
import logging
import sqlite3
import threading
import math
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any, TYPE_CHECKING
from collections import Counter, defaultdict

if TYPE_CHECKING:
    from ..engine import RecallEngine
    from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


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


# ==================== 常量 ====================

TOPIC_RELATION_TYPE = "TOPIC_RELATED"
MIN_TOPIC_LENGTH = 2
MAX_TOPIC_LENGTH = 20
DEFAULT_MAX_TOPICS = 5
DEFAULT_MIN_TOPICS = 2

# 中文停用词（主题提取时过滤）
_CN_STOP_WORDS: Set[str] = {
    '的', '了', '是', '在', '和', '有', '这', '那', '就', '都', '也', '还', '要',
    '我', '你', '他', '她', '它', '我们', '你们', '他们', '这个', '那个', '什么',
    '怎么', '为什么', '可以', '能够', '应该', '比如', '然后', '所以', '因为',
    '但是', '如果', '虽然', '不过', '而且', '或者', '以及', '通过', '一个',
    '一些', '很多', '非常', '特别', '其实', '基本上', '大概', '可能', '已经',
    '正在', '没有', '不是', '不会', '不能', '不要', '自己', '这样', '那样',
    '一直', '只是', '作为', '关于', '对于', '需要', '使用', '进行', '请',
    '好的', '好吧', '嗯', '哦', '呢', '吗', '啊', '吧', '呀', '哈',
}

# 英文停用词
_EN_STOP_WORDS: Set[str] = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'this', 'that', 'these', 'those', 'it', 'its', 'i', 'me', 'my',
    'you', 'your', 'he', 'him', 'his', 'she', 'her', 'we', 'us', 'our',
    'they', 'them', 'their', 'and', 'or', 'but', 'if', 'then', 'else',
    'when', 'where', 'how', 'why', 'what', 'which', 'who', 'whom',
    'for', 'to', 'from', 'with', 'by', 'at', 'in', 'on', 'of', 'about',
    'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further',
    'not', 'no', 'nor', 'so', 'very', 'just', 'also', 'than', 'too',
    'only', 'own', 'same', 'as', 'both', 'each', 'all', 'any', 'such',
}


# ==================== 数据类 ====================

@dataclass
class TopicInfo:
    """主题信息"""
    name: str                 # 主题名称
    memory_count: int = 0     # 关联记忆数量
    last_updated: str = ""    # 最后更新时间
    parent_topic: str = ""    # 父主题（层级概念）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "memory_count": self.memory_count,
            "last_updated": self.last_updated,
            "parent_topic": self.parent_topic,
        }


# ==================== SQLite 存储 ====================

class TopicStore:
    """主题存储 (SQLite)"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        """线程本地连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        """初始化数据库表"""
        conn = self._conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                name TEXT PRIMARY KEY,
                parent_topic TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                last_updated TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS memory_topics (
                memory_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                user_id TEXT DEFAULT 'default',
                created_at TEXT DEFAULT '',
                PRIMARY KEY (memory_id, topic)
            );

            CREATE INDEX IF NOT EXISTS idx_memory_topics_topic
                ON memory_topics(topic);
            CREATE INDEX IF NOT EXISTS idx_memory_topics_user
                ON memory_topics(user_id);
            CREATE INDEX IF NOT EXISTS idx_memory_topics_memory
                ON memory_topics(memory_id);
        """)
        conn.commit()

    def add_topic(self, name: str, parent_topic: str = "") -> None:
        """添加或更新主题"""
        now = datetime.now().isoformat()
        self._conn.execute(
            """INSERT INTO topics (name, parent_topic, created_at, last_updated)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET last_updated=?, parent_topic=COALESCE(NULLIF(?, ''), parent_topic)""",
            (name, parent_topic, now, now, now, parent_topic)
        )
        self._conn.commit()

    def link_memory(self, memory_id: str, topic: str, user_id: str = "default") -> None:
        """将记忆关联到主题"""
        now = datetime.now().isoformat()
        self._conn.execute(
            """INSERT OR IGNORE INTO memory_topics (memory_id, topic, user_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (memory_id, topic, user_id, now)
        )
        self._conn.commit()
        # 更新主题的 last_updated
        self.add_topic(topic)

    def get_memories_by_topic(
        self, topic: str, user_id: Optional[str] = None, limit: int = 50
    ) -> List[str]:
        """获取某个主题下的所有记忆 ID"""
        if user_id:
            rows = self._conn.execute(
                "SELECT memory_id FROM memory_topics WHERE topic=? AND user_id=? ORDER BY created_at DESC LIMIT ?",
                (topic, user_id, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT memory_id FROM memory_topics WHERE topic=? ORDER BY created_at DESC LIMIT ?",
                (topic, limit)
            ).fetchall()
        return [r[0] for r in rows]

    def get_topics_by_memory(self, memory_id: str) -> List[str]:
        """获取记忆的所有主题"""
        rows = self._conn.execute(
            "SELECT topic FROM memory_topics WHERE memory_id=?",
            (memory_id,)
        ).fetchall()
        return [r[0] for r in rows]

    def get_all_topics(self, user_id: Optional[str] = None) -> List[TopicInfo]:
        """获取所有主题及其统计"""
        if user_id:
            rows = self._conn.execute(
                """SELECT t.name, t.parent_topic, t.last_updated,
                          COUNT(mt.memory_id) as cnt
                   FROM topics t
                   LEFT JOIN memory_topics mt ON t.name = mt.topic AND mt.user_id = ?
                   GROUP BY t.name
                   ORDER BY cnt DESC""",
                (user_id,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT t.name, t.parent_topic, t.last_updated,
                          COUNT(mt.memory_id) as cnt
                   FROM topics t
                   LEFT JOIN memory_topics mt ON t.name = mt.topic
                   GROUP BY t.name
                   ORDER BY cnt DESC"""
            ).fetchall()
        return [
            TopicInfo(
                name=r[0],
                parent_topic=r[1] or "",
                last_updated=r[2] or "",
                memory_count=r[3],
            )
            for r in rows
        ]

    def get_memories_with_shared_topics(
        self, memory_id: str, user_id: Optional[str] = None, limit: int = 50
    ) -> List[Tuple[str, List[str]]]:
        """获取与某记忆共享主题的其他记忆

        Returns:
            List of (other_memory_id, shared_topics)
        """
        topics = self.get_topics_by_memory(memory_id)
        if not topics:
            return []

        placeholders = ",".join("?" * len(topics))
        params: list = list(topics)
        query = f"""
            SELECT memory_id, GROUP_CONCAT(topic, ',') as shared
            FROM memory_topics
            WHERE topic IN ({placeholders})
              AND memory_id != ?
        """
        params.append(memory_id)

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        query += " GROUP BY memory_id ORDER BY COUNT(*) DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [(r[0], r[1].split(",")) for r in rows]

    def delete_memory_topics(self, memory_id: str) -> int:
        """删除记忆的所有主题关联"""
        cursor = self._conn.execute(
            "DELETE FROM memory_topics WHERE memory_id=?",
            (memory_id,)
        )
        self._conn.commit()
        return cursor.rowcount

    def close(self):
        """关闭连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# ==================== 主题提取 ====================

class TopicCluster:
    """主题聚类器

    职责:
    1. 从记忆内容中提取主题标签 (2-5 个)
    2. 将记忆与主题关联，创建 TOPIC_RELATED 图谱边
    3. 支持按主题搜索记忆
    4. 主题层级扩展
    """

    def __init__(
        self,
        data_path: Optional[str] = None,
        llm_client: Optional['LLMClient'] = None,
        max_topics: int = DEFAULT_MAX_TOPICS,
        min_topics: int = DEFAULT_MIN_TOPICS,
    ):
        """初始化主题聚类器

        Args:
            data_path: 数据存储路径 (SQLite)
            llm_client: 可选的 LLM 客户端
            max_topics: 每条记忆最多提取的主题数
            min_topics: 每条记忆最少提取的主题数
        """
        self.llm_client = llm_client
        self.max_topics = max_topics
        self.min_topics = min_topics

        # 初始化 SQLite 存储
        self._store: Optional[TopicStore] = None
        if data_path:
            db_dir = os.path.join(data_path, 'topics')
            os.makedirs(db_dir, exist_ok=True)
            db_file = os.path.join(db_dir, 'topics.db')
            self._store = TopicStore(db_file)

        # 全局词频表 (TF-IDF-like)
        self._doc_count = 0
        self._doc_freq: Counter = Counter()  # word → number of docs containing it
        self._lock = threading.Lock()

    # ==================== 公共 API ====================

    def extract_topics(
        self,
        content: str,
        entities: Optional[List[str]] = None,
        use_llm: bool = False,
    ) -> List[str]:
        """从内容中提取 2-5 个主题标签

        策略:
        1. 关键词提取 (TF-IDF-like)
        2. 实体作为候选主题
        3. 可选 LLM 精修

        Args:
            content: 记忆内容
            entities: 预提取的实体列表
            use_llm: 是否使用 LLM 精修

        Returns:
            2-5 个主题标签列表
        """
        if not content or not content.strip():
            return []

        # Step 1: 关键词提取
        keyword_topics = self._extract_keywords(content)

        # Step 2: 实体作为候选
        entity_topics = []
        if entities:
            for e in entities:
                normalized = e.strip().lower()
                if MIN_TOPIC_LENGTH <= len(normalized) <= MAX_TOPIC_LENGTH:
                    entity_topics.append(normalized)

        # 合并候选
        candidates = keyword_topics + entity_topics

        # Step 3: 去重 + 排序
        seen: Set[str] = set()
        unique: List[str] = []
        for t in candidates:
            t_lower = t.lower().strip()
            if t_lower and t_lower not in seen and len(t_lower) >= MIN_TOPIC_LENGTH:
                seen.add(t_lower)
                unique.append(t_lower)

        # Step 4: LLM 精修（可选）
        if use_llm and self.llm_client and len(unique) > self.max_topics:
            try:
                unique = self._llm_refine_topics(content, unique)
            except Exception as e:
                logger.debug(f"[TopicCluster] LLM 精修失败: {e}")

        # 截取范围
        result = unique[:self.max_topics]

        # 更新全局词频
        self._update_doc_freq(result)

        return result

    def link_by_topics(
        self,
        memory_id: str,
        topics: List[str],
        engine: 'RecallEngine',
        user_id: str = "default",
    ) -> int:
        """将记忆与主题关联，并创建 TOPIC_RELATED 图谱边

        Args:
            memory_id: 记忆 ID
            topics: 主题标签列表
            engine: RecallEngine 实例
            user_id: 用户 ID

        Returns:
            创建的边数量
        """
        if not topics:
            return 0

        edge_count = 0

        # 1. 存储主题关联
        if self._store:
            for topic in topics:
                self._store.add_topic(topic)
                self._store.link_memory(memory_id, topic, user_id)

        # 2. 查找共享主题的其他记忆，创建图谱边
        if self._store and hasattr(engine, 'knowledge_graph') and engine.knowledge_graph:
            shared_memories = self._store.get_memories_with_shared_topics(
                memory_id, user_id=user_id, limit=20
            )
            for other_id, shared_topics in shared_memories:
                try:
                    engine.knowledge_graph.add_relation(
                        source_id=memory_id,
                        target_id=other_id,
                        relation_type=TOPIC_RELATION_TYPE,
                        properties={
                            "shared_topics": shared_topics,
                            "link_type": "topic_cluster",
                        },
                        confidence=min(0.5 + len(shared_topics) * 0.1, 0.9),
                        source_text=f"共享主题: {', '.join(shared_topics)}",
                    )
                    edge_count += 1
                except Exception as e:
                    logger.debug(f"[TopicCluster] 创建图谱边失败: {e}")

        if edge_count > 0:
            _safe_print(f"[TopicCluster] 为记忆 {memory_id[:8]}... 创建 {edge_count} 条主题关联边")

        return edge_count

    def search_by_topic(
        self,
        topic: str,
        engine: 'RecallEngine',
        user_id: str = "default",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """按主题搜索记忆

        Args:
            topic: 主题名称
            engine: RecallEngine 实例
            user_id: 用户 ID
            limit: 最大返回数

        Returns:
            记忆列表（包含 id, content, metadata）
        """
        if not self._store:
            return []

        memory_ids = self._store.get_memories_by_topic(
            topic.lower().strip(), user_id=user_id, limit=limit
        )
        if not memory_ids:
            return []

        results: List[Dict[str, Any]] = []
        for mid in memory_ids:
            content = self._get_memory_content(mid, engine, user_id)
            if content is not None:
                topics = self._store.get_topics_by_memory(mid)
                results.append({
                    "id": mid,
                    "content": content,
                    "topics": topics,
                    "metadata": {"topic_match": topic},
                })

        return results

    def get_all_topics(self, user_id: Optional[str] = None) -> List[TopicInfo]:
        """获取所有主题及统计

        Args:
            user_id: 可选用户 ID 过滤

        Returns:
            TopicInfo 列表
        """
        if self._store:
            return self._store.get_all_topics(user_id=user_id)
        return []

    def get_topics_for_memory(self, memory_id: str) -> List[str]:
        """获取某条记忆的所有主题"""
        if self._store:
            return self._store.get_topics_by_memory(memory_id)
        return []

    def delete_memory_topics(self, memory_id: str) -> int:
        """删除记忆的所有主题关联"""
        if self._store:
            return self._store.delete_memory_topics(memory_id)
        return 0

    # ==================== 关键词提取 ====================

    def _extract_keywords(self, content: str) -> List[str]:
        """基于 TF-IDF-like 方法提取关键词作为主题候选"""
        # 分词
        words = self._tokenize(content)
        if not words:
            return []

        # 计算词频 (TF)
        word_count = Counter(words)
        total_words = len(words)

        # 计算 TF-IDF-like 分数
        scored: List[Tuple[str, float]] = []
        for word, count in word_count.items():
            tf = count / total_words
            # IDF: 使用全局文档频率（如果有）
            doc_freq = self._doc_freq.get(word, 0)
            if self._doc_count > 0 and doc_freq > 0:
                idf = math.log(self._doc_count / (1 + doc_freq))
            else:
                idf = 1.0  # 首次见到的词给予中等权重
            score = tf * idf
            scored.append((word, score))

        # 按分数排序
        scored.sort(key=lambda x: -x[1])

        # 过滤：长度、是否为停用词
        filtered: List[str] = []
        for word, score in scored:
            if self._is_valid_topic(word):
                filtered.append(word)
                if len(filtered) >= self.max_topics * 2:  # 取双倍候选
                    break

        return filtered

    def _tokenize(self, content: str) -> List[str]:
        """分词 (支持中英文混合)"""
        words: List[str] = []

        # 尝试使用 jieba 分词（中文）
        try:
            import jieba
            cn_text = re.sub(r'[a-zA-Z0-9\s]+', ' ', content)
            if cn_text.strip():
                cn_words = jieba.lcut(cn_text)
                for w in cn_words:
                    w = w.strip()
                    if w and len(w) >= 2 and w not in _CN_STOP_WORDS:
                        words.append(w)
        except ImportError:
            # jieba 不可用，用简单的中文分割
            cn_chars = re.findall(r'[\u4e00-\u9fff]{2,}', content)
            for chars in cn_chars:
                if chars not in _CN_STOP_WORDS:
                    words.append(chars)

        # 英文词提取
        en_words = re.findall(r'\b[a-zA-Z]{3,}\b', content.lower())
        for w in en_words:
            if w not in _EN_STOP_WORDS:
                words.append(w)

        return words

    def _is_valid_topic(self, word: str) -> bool:
        """检查词是否适合作为主题"""
        if len(word) < MIN_TOPIC_LENGTH or len(word) > MAX_TOPIC_LENGTH:
            return False
        if word in _CN_STOP_WORDS or word.lower() in _EN_STOP_WORDS:
            return False
        # 过滤纯数字
        if word.isdigit():
            return False
        return True

    def _update_doc_freq(self, topics: List[str]) -> None:
        """更新全局文档频率"""
        with self._lock:
            self._doc_count += 1
            for t in set(topics):
                self._doc_freq[t] += 1

    # ==================== LLM 精修 ====================

    def _llm_refine_topics(self, content: str, candidates: List[str]) -> List[str]:
        """使用 LLM 从候选中精选最佳主题"""
        if not self.llm_client:
            return candidates

        prompt = (
            "从以下候选主题中，选出最能代表文本核心内容的 2-5 个主题标签。\n"
            "要求: 简洁、具体、有区分度。\n\n"
            f"文本: {content[:300]}\n\n"
            f"候选主题: {', '.join(candidates[:15])}\n\n"
            "请仅返回选中的主题，每行一个，不加序号或其他文字:"
        )

        try:
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )
            lines = response.content.strip().split("\n")
            refined = []
            for line in lines:
                topic = line.strip().lower()
                if topic and self._is_valid_topic(topic):
                    refined.append(topic)
            if len(refined) >= self.min_topics:
                return refined[:self.max_topics]
        except Exception as e:
            logger.debug(f"[TopicCluster] LLM 精修失败: {e}")

        return candidates

    # ==================== 辅助方法 ====================

    @staticmethod
    def _get_memory_content(
        memory_id: str,
        engine: 'RecallEngine',
        user_id: str,
    ) -> Optional[str]:
        """获取记忆内容"""
        try:
            if hasattr(engine, 'storage') and engine.storage:
                scope = engine.storage.get_scope(user_id)
                content = scope.get_content_by_id(memory_id)
                if content:
                    return content
        except Exception:
            pass
        try:
            if hasattr(engine, '_get_memory_content_by_id'):
                return engine._get_memory_content_by_id(memory_id)
        except Exception:
            pass
        return None
