"""优化的N-gram索引 - 支持名词短语索引 + 原文全文兜底搜索

Phase 3.6 更新：添加并行分片扫描支持，提升大规模数据的兜底速度
"""

import os
import re
import json
from typing import List, Dict, Set, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed


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


class OptimizedNgramIndex:
    """优化的N-gram索引 - 名词短语索引 + 原文兜底
    
    设计原则（按计划十二点五"100%不遗忘"要求）：
    1. 主索引：只索引名词短语，避免空间爆炸
    2. 原文存储：保留完整原文，支持"终极兜底"搜索
    3. 两层搜索：先查名词短语索引，无结果时扫描原文
    """
    
    def __init__(self, data_path: str = None):
        # 数据目录
        self.data_path = data_path
        self._index_file = os.path.join(data_path, "ngram_index.json") if data_path else None
        self._raw_content_file = os.path.join(data_path, "ngram_raw_content.jsonl") if data_path else None
        
        # 主索引：名词短语 → [memory_ids]
        self.noun_phrases: Dict[str, List[str]] = {}
        
        # 原文存储：memory_id → content（用于兜底搜索）
        self._raw_content: Dict[str, str] = {}
        
        # 可选的布隆过滤器
        self._bloom_filter = None
        
        # 从磁盘加载已有数据
        if data_path:
            self._load()
    
    @property
    def bloom_filter(self):
        """懒加载布隆过滤器"""
        if self._bloom_filter is None:
            try:
                from pybloom_live import BloomFilter
                self._bloom_filter = BloomFilter(capacity=1000000, error_rate=0.01)
            except ImportError:
                # 如果没有安装 pybloom_live，使用简单 set 替代
                self._bloom_filter = set()
        return self._bloom_filter
    
    def add(self, turn: str, content: str):
        """添加索引（名词短语索引 + 原文存储 + 增量持久化）
        
        Args:
            turn: memory_id（如 mem_xxx）
            content: 记忆内容
        """
        # 1. 存储原文（用于兜底搜索）
        self._raw_content[turn] = content
        
        # 1.5 增量持久化原文（避免重启丢失）
        self.append_raw_content(turn, content)
        
        # 2. 提取并索引名词短语（主索引）
        phrases = self._extract_noun_phrases(content)
        
        for phrase in phrases:
            # 添加到布隆过滤器
            if isinstance(self.bloom_filter, set):
                self.bloom_filter.add(phrase)
            else:
                self.bloom_filter.add(phrase)
            
            if phrase not in self.noun_phrases:
                self.noun_phrases[phrase] = []
            self.noun_phrases[phrase].append(turn)
        
        # 3. 定期保存名词短语索引（每 100 条保存一次）
        if len(self._raw_content) % 100 == 0:
            self._save_noun_phrases()
    
    def _save_noun_phrases(self):
        """只保存名词短语索引（轻量级操作）"""
        if not self._index_file:
            return
        try:
            os.makedirs(os.path.dirname(self._index_file), exist_ok=True)
            with open(self._index_file, 'w', encoding='utf-8') as f:
                json.dump(self.noun_phrases, f, ensure_ascii=False)
        except Exception as e:
            _safe_print(f"[NgramIndex] 保存名词短语索引失败: {e}")
    
    def _extract_noun_phrases(self, content: str) -> List[str]:
        """提取名词短语（而非所有n-gram）"""
        # 使用简单规则：2-4字的中文词组 + 英文单词
        chinese_phrases = re.findall(r'[\u4e00-\u9fa5]{2,4}', content)
        english_words = re.findall(r'[a-zA-Z]{3,}', content)
        
        # 过滤停用词
        stopwords = {
            '的', '了', '是', '在', '和', '有', '这', '那', 
            'the', 'a', 'is', 'are', 'to', 'and', 'of', 'in'
        }
        phrases = [p for p in chinese_phrases + english_words if p.lower() not in stopwords]
        
        return phrases
    
    def search(self, query: str) -> List[str]:
        """搜索（先查名词短语索引，无结果时原文兜底）
        
        Returns:
            List[str]: 匹配的 memory_id 列表
        """
        # 第一层：名词短语索引搜索
        phrases = self._extract_noun_phrases(query)
        
        candidate_turns: Set[str] = set()
        for phrase in phrases:
            # 先用布隆过滤器快速排除（使用 in 运算符）
            if phrase not in self.bloom_filter:
                continue
            
            if phrase in self.noun_phrases:
                candidate_turns.update(self.noun_phrases[phrase])
        
        if candidate_turns:
            return list(candidate_turns)
        
        # 第二层：原文兜底搜索（"终极兜底"，确保100%不遗忘）
        return self._raw_text_fallback_search(query)
    
    def _raw_text_fallback_search(self, query: str, max_results: int = 50) -> List[str]:
        """原文兜底搜索 - 扫描所有原文寻找包含查询子串的记忆
        
        这是"终极兜底"机制，确保即使名词短语索引未命中，
        只要原文中包含查询内容就能找到。
        
        Args:
            query: 搜索查询
            max_results: 最大返回数量（避免返回太多）
        
        Returns:
            List[str]: 匹配的 memory_id 列表
        """
        results = []
        query_lower = query.lower()
        
        # 提取查询中的关键子串（2-6字符）
        search_terms = self._extract_search_terms(query)
        
        for memory_id, content in self._raw_content.items():
            content_lower = content.lower()
            
            # 直接子串匹配
            if query_lower in content_lower:
                results.append(memory_id)
                continue
            
            # 检查任一关键子串是否匹配
            for term in search_terms:
                if term in content_lower:
                    results.append(memory_id)
                    break
            
            if len(results) >= max_results:
                break
        
        return results
    
    def _extract_search_terms(self, query: str) -> List[str]:
        """从查询中提取搜索词（用于兜底搜索）"""
        terms = []
        query_lower = query.lower()
        
        # 中文：2-6字符子串
        for length in [4, 3, 2, 5, 6]:
            for i in range(len(query) - length + 1):
                substr = query[i:i+length]
                if re.match(r'^[\u4e00-\u9fa5]+$', substr):
                    terms.append(substr.lower())
        
        # 英文：3-8字符单词
        english_words = re.findall(r'[a-zA-Z]{3,8}', query)
        terms.extend([w.lower() for w in english_words])
        
        return list(set(terms))[:10]  # 去重并限制数量
    
    def raw_search(self, query: str, max_results: int = 50) -> List[str]:
        """直接进行原文搜索（跳过名词短语索引）
        
        用于需要精确原文匹配的场景
        """
        return self._raw_text_fallback_search(query, max_results)
    
    def raw_search_parallel(
        self,
        query: str,
        max_results: int = 50,
        num_workers: int = 4
    ) -> List[str]:
        """Phase 3.6: 并行分片扫描原文
        
        将原文数据分成多个分片，并行扫描，显著提升大规模数据的兜底速度。
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            num_workers: 并行线程数
            
        Returns:
            匹配的 memory_id 列表
        """
        items = list(self._raw_content.items())
        if not items:
            return []
        
        # 数据量小于 1000 时，直接单线程搜索更快
        if len(items) < 1000:
            return self._raw_text_fallback_search(query, max_results)
        
        # 分片
        chunk_size = max(1, len(items) // num_workers)
        chunks = [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]
        
        # 预提取搜索词（避免在每个线程中重复计算）
        search_terms = self._extract_search_terms(query)
        query_lower = query.lower()
        
        # 并行扫描
        all_results: List[str] = []
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(self._scan_chunk, query_lower, search_terms, chunk)
                for chunk in chunks
            ]
            
            for future in as_completed(futures):
                try:
                    chunk_results = future.result()
                    all_results.extend(chunk_results)
                    if len(all_results) >= max_results:
                        break
                except Exception as e:
                    _safe_print(f"[NgramIndex] 并行扫描失败: {e}")
                    continue
        
        return all_results[:max_results]
    
    def _scan_chunk(
        self,
        query_lower: str,
        search_terms: List[str],
        chunk: List[Tuple[str, str]]
    ) -> List[str]:
        """扫描单个分片（用于并行搜索）"""
        results = []
        
        for memory_id, content in chunk:
            content_lower = content.lower()
            
            # 直接子串匹配
            if query_lower in content_lower:
                results.append(memory_id)
                continue
            
            # 检查关键子串
            for term in search_terms:
                if term in content_lower:
                    results.append(memory_id)
                    break
        
        return results
    
    def get_raw_content(self, memory_id: str) -> Optional[str]:
        """获取原文内容"""
        return self._raw_content.get(memory_id)
    
    # ========== 持久化方法 ==========
    
    def _load(self):
        """从磁盘加载索引数据"""
        # 加载名词短语索引
        if self._index_file and os.path.exists(self._index_file):
            try:
                with open(self._index_file, 'r', encoding='utf-8') as f:
                    self.noun_phrases = json.load(f)
                _safe_print(f"[NgramIndex] 已加载 {len(self.noun_phrases)} 个名词短语索引")
            except Exception as e:
                _safe_print(f"[NgramIndex] 加载索引失败: {e}")
        
        # 加载原文内容（JSONL 格式，支持增量写入）
        if self._raw_content_file and os.path.exists(self._raw_content_file):
            try:
                with open(self._raw_content_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                item = json.loads(line)
                                self._raw_content[item['id']] = item['content']
                            except json.JSONDecodeError:
                                continue
                _safe_print(f"[NgramIndex] 已加载 {len(self._raw_content)} 条原文内容")
            except Exception as e:
                _safe_print(f"[NgramIndex] 加载原文失败: {e}")
    
    def save(self):
        """保存索引数据到磁盘"""
        if not self.data_path:
            return
        
        os.makedirs(self.data_path, exist_ok=True)
        
        # 保存名词短语索引
        if self._index_file:
            try:
                with open(self._index_file, 'w', encoding='utf-8') as f:
                    json.dump(self.noun_phrases, f, ensure_ascii=False)
            except Exception as e:
                _safe_print(f"[NgramIndex] 保存索引失败: {e}")
        
        # 保存原文内容（完全重写，避免重复）
        if self._raw_content_file:
            try:
                with open(self._raw_content_file, 'w', encoding='utf-8') as f:
                    for memory_id, content in self._raw_content.items():
                        f.write(json.dumps({'id': memory_id, 'content': content}, ensure_ascii=False) + '\n')
            except Exception as e:
                _safe_print(f"[NgramIndex] 保存原文失败: {e}")
    
    def append_raw_content(self, memory_id: str, content: str):
        """增量追加原文（高效写入，不用每次全量保存）"""
        if self._raw_content_file:
            try:
                # 确保目录存在
                os.makedirs(os.path.dirname(self._raw_content_file), exist_ok=True)
                with open(self._raw_content_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'id': memory_id, 'content': content}, ensure_ascii=False) + '\n')
            except Exception as e:
                _safe_print(f"[NgramIndex] 追加原文失败: {e}")
    
    def clear(self):
        """清空所有索引和原文内容"""
        self.noun_phrases.clear()
        self._raw_content.clear()
        
        # 重置布隆过滤器
        if self._bloom_filter is not None:
            if isinstance(self._bloom_filter, set):
                self._bloom_filter.clear()
            else:
                self._bloom_filter = None
        
        # 删除磁盘文件
        if self._index_file and os.path.exists(self._index_file):
            try:
                os.remove(self._index_file)
            except Exception:
                pass
        
        if self._raw_content_file and os.path.exists(self._raw_content_file):
            try:
                os.remove(self._raw_content_file)
            except Exception:
                pass
    
    def remove_by_memory_ids(self, memory_ids: Set[str]) -> int:
        """根据 memory_id 删除索引项
        
        Args:
            memory_ids: 要删除的 memory_id 集合
        
        Returns:
            int: 清理的原文数量
        """
        removed_count = 0
        
        # 从原文存储中删除
        for mid in memory_ids:
            if mid in self._raw_content:
                del self._raw_content[mid]
                removed_count += 1
        
        # 从名词短语索引中删除
        empty_phrases = []
        for phrase, mids in self.noun_phrases.items():
            self.noun_phrases[phrase] = [m for m in mids if m not in memory_ids]
            if len(self.noun_phrases[phrase]) == 0:
                empty_phrases.append(phrase)
        
        for phrase in empty_phrases:
            del self.noun_phrases[phrase]
        
        # 保存更新
        if removed_count > 0:
            self.save()
        
        return removed_count
    
    def __len__(self) -> int:
        """返回索引的原文数量"""
        return len(self._raw_content)
