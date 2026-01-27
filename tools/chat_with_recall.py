#!/usr/bin/env python3
"""Recall 交互式聊天测试工具

模拟完整的用户体验：
1. 用户输入消息
2. 消息存入 Recall（显示实体提取）
3. 从 Recall 获取相关上下文
4. 调用 LLM 生成回复
5. AI 回复也存入 Recall
6. 详细日志记录每一步

使用方法:
    python tools/chat_with_recall.py
    python tools/chat_with_recall.py --user 角色名
    python tools/chat_with_recall.py --debug  # 更详细的日志

命令:
    /entities  - 查看所有实体
    /relations - 查看实体关系
    /search 关键词 - 搜索记忆
    /context - 查看当前上下文
    /memories - 查看所有记忆
    /stats - 查看统计信息
    /graph - 查看图谱概览
    /clear - 清空当前用户记忆
    /help - 显示帮助
    /quit - 退出

作者: Recall Team
"""

import os
import sys
import json
import time
import logging
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Any, List

# ==================== 配置 ====================

RECALL_API_BASE = "http://localhost:18888"
LOG_DIR = "./recall_data/logs"
LOG_FILE = None  # 运行时设置

# ==================== 颜色定义 ====================

class Colors:
    """终端颜色"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"

# Windows 颜色支持
if sys.platform == "win32":
    os.system("")  # 启用 ANSI 转义序列

# ==================== 日志系统 ====================

class DetailedLogger:
    """详细日志记录器"""
    
    def __init__(self, log_file: str, debug: bool = False):
        self.log_file = log_file
        self.debug_mode = debug
        self.session_start = datetime.now()
        
        # 确保日志目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # 写入会话开始标记
        self._write_log("=" * 80)
        self._write_log(f"SESSION START: {self.session_start.isoformat()}")
        self._write_log("=" * 80)
    
    def _write_log(self, message: str):
        """写入日志文件"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    
    def info(self, message: str, console: bool = True):
        """信息日志"""
        self._write_log(f"[INFO] {message}")
        if console:
            print(f"{Colors.DIM}[INFO]{Colors.RESET} {message}")
    
    def debug(self, message: str, console: bool = None):
        """调试日志"""
        self._write_log(f"[DEBUG] {message}")
        if console is None:
            console = self.debug_mode
        if console:
            print(f"{Colors.DIM}[DEBUG]{Colors.RESET} {message}")
    
    def success(self, message: str):
        """成功日志"""
        self._write_log(f"[SUCCESS] {message}")
        print(f"{Colors.GREEN}[OK]{Colors.RESET} {message}")
    
    def warning(self, message: str):
        """警告日志"""
        self._write_log(f"[WARNING] {message}")
        print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {message}")
    
    def error(self, message: str):
        """错误日志"""
        self._write_log(f"[ERROR] {message}")
        print(f"{Colors.RED}[ERROR]{Colors.RESET} {message}")
    
    def api_call(self, method: str, endpoint: str, data: Any = None):
        """API 调用日志"""
        self._write_log(f"[API] {method} {endpoint}")
        if data:
            self._write_log(f"[API] Request: {json.dumps(data, ensure_ascii=False)}")
    
    def api_response(self, status: int, response: Any, elapsed: float):
        """API 响应日志"""
        self._write_log(f"[API] Status: {status}, Time: {elapsed:.3f}s")
        self._write_log(f"[API] Response: {json.dumps(response, ensure_ascii=False, default=str)}")
    
    def user_input(self, message: str):
        """用户输入日志"""
        self._write_log(f"[USER] {message}")
    
    def ai_response(self, message: str):
        """AI 回复日志"""
        self._write_log(f"[AI] {message}")
    
    def entity_extracted(self, entities: List[str]):
        """实体提取日志"""
        self._write_log(f"[ENTITY] Extracted: {entities}")
    
    def memory_added(self, memory_id: str, content: str):
        """记忆添加日志"""
        self._write_log(f"[MEMORY] Added: id={memory_id}, content={content[:100]}...")
    
    def context_built(self, context: str, tokens: int = 0):
        """上下文构建日志"""
        self._write_log(f"[CONTEXT] Built context: {len(context)} chars, ~{tokens} tokens")
        self._write_log(f"[CONTEXT] Content:\n{context[:500]}...")

# ==================== API 客户端 ====================

class RecallAPIClient:
    """Recall API 客户端"""
    
    def __init__(self, base_url: str, logger: DetailedLogger):
        self.base_url = base_url.rstrip("/")
        self.logger = logger
    
    def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """发送 HTTP 请求"""
        url = f"{self.base_url}{endpoint}"
        self.logger.api_call(method, endpoint, data)
        
        start_time = time.time()
        
        try:
            if data:
                body = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(url, data=body, method=method)
                req.add_header("Content-Type", "application/json")
            else:
                req = urllib.request.Request(url, method=method)
            
            with urllib.request.urlopen(req, timeout=1200) as response:
                result = json.loads(response.read().decode("utf-8"))
                elapsed = time.time() - start_time
                self.logger.api_response(response.status, result, elapsed)
                return result
                
        except urllib.error.HTTPError as e:
            elapsed = time.time() - start_time
            error_body = e.read().decode("utf-8") if e.fp else ""
            self.logger.api_response(e.code, {"error": error_body}, elapsed)
            raise Exception(f"API Error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            self.logger.error(f"Connection error: {e.reason}")
            raise Exception(f"Connection error: {e.reason}")
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            result = self._request("GET", "/health")
            return result.get("status") == "healthy"
        except Exception:
            return False
    
    def add_memory(self, content: str, user_id: str, role: str = "user") -> Dict:
        """添加记忆"""
        return self._request("POST", "/v1/memories", {
            "content": content,
            "user_id": user_id,
            "metadata": {"role": role, "timestamp": time.time()}
        })
    
    def search_memories(self, query: str, user_id: str, top_k: int = 10) -> List[Dict]:
        """搜索记忆"""
        result = self._request("POST", "/v1/memories/search", {
            "query": query,
            "user_id": user_id,
            "top_k": top_k
        })
        return result.get("results", result) if isinstance(result, dict) else result
    
    def get_entities(self, user_id: str) -> List[Dict]:
        """获取实体列表"""
        return self._request("GET", f"/v1/entities?user_id={user_id}")
    
    def get_related_entities(self, name: str) -> Dict:
        """获取相关实体"""
        return self._request("GET", f"/v1/entities/{urllib.parse.quote(name)}/related")
    
    def build_context(self, query: str, user_id: str) -> str:
        """构建上下文"""
        result = self._request("POST", "/v1/context", {
            "query": query,
            "user_id": user_id,
            "include_recent": 10
        })
        return result.get("context", "")
    
    def get_memories(self, user_id: str, limit: int = 50) -> List[Dict]:
        """获取记忆列表"""
        result = self._request("GET", f"/v1/memories?user_id={user_id}&limit={limit}")
        # API 返回 {"memories": [...], "count": ..., "total": ...}
        if isinstance(result, dict) and "memories" in result:
            return result["memories"]
        return result if isinstance(result, list) else []
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self._request("GET", "/v1/stats")
    
    def clear_memories(self, user_id: str) -> Dict:
        """清空记忆"""
        return self._request("DELETE", f"/v1/memories?user_id={user_id}&confirm=true")
    
    def get_foreshadowings(self, user_id: str) -> List[Dict]:
        """获取伏笔"""
        result = self._request("GET", f"/v1/foreshadowing?user_id={user_id}")
        # API 可能返回列表或包装对象
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "foreshadowings" in result:
            return result["foreshadowings"]
        return []


class LLMClient:
    """LLM 客户端"""
    
    def __init__(self, api_key: str, api_base: str, model: str, logger: DetailedLogger):
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.logger = logger
    
    def chat(self, messages: List[Dict], system_prompt: str = None) -> str:
        """调用 LLM 聊天"""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        self.logger.debug(f"LLM Request: model={self.model}, messages={len(full_messages)}")
        
        url = f"{self.api_base}/chat/completions"
        data = {
            "model": self.model,
            "messages": full_messages,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        
        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=1200) as response:
                result = json.loads(response.read().decode("utf-8"))
                elapsed = time.time() - start_time
                
                content = result["choices"][0]["message"]["content"]
                self.logger.debug(f"LLM Response: {elapsed:.2f}s, {len(content)} chars")
                return content
        except Exception as e:
            self.logger.error(f"LLM Error: {e}")
            raise

# ==================== 主聊天应用 ====================

class RecallChatApp:
    """Recall 交互式聊天应用"""
    
    def __init__(self, user_id: str, debug: bool = False):
        self.user_id = user_id
        self.debug = debug
        self.turn_count = 0
        
        # 初始化日志
        log_file = os.path.join(
            LOG_DIR, 
            f"chat_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        self.logger = DetailedLogger(log_file, debug)
        self.logger.info(f"日志文件: {log_file}")
        
        # 初始化 API 客户端
        self.recall = RecallAPIClient(RECALL_API_BASE, self.logger)
        
        # 加载 LLM 配置
        self.llm = None
        self._init_llm()
        
        # 对话历史（用于 LLM 上下文）
        self.conversation_history = []
    
    def _init_llm(self):
        """初始化 LLM 客户端"""
        # 从环境变量或配置文件加载
        config_file = "./recall_data/config/api_keys.env"
        config = {}
        
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip()
        
        api_key = config.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY")
        api_base = config.get("LLM_API_BASE") or os.environ.get("LLM_API_BASE") or "https://api.openai.com/v1"
        model = config.get("LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
        
        if api_key:
            self.llm = LLMClient(api_key, api_base, model, self.logger)
            self.logger.success(f"LLM 已配置: {model} @ {api_base}")
        else:
            self.logger.warning("未配置 LLM_API_KEY，将无法生成 AI 回复")
    
    def _print_header(self):
        """打印欢迎信息"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}  Recall 交互式聊天测试工具{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"  用户ID: {Colors.GREEN}{self.user_id}{Colors.RESET}")
        print(f"  调试模式: {Colors.YELLOW}{'开启' if self.debug else '关闭'}{Colors.RESET}")
        print(f"  LLM: {Colors.GREEN if self.llm else Colors.RED}{'已配置' if self.llm else '未配置'}{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"  输入 {Colors.YELLOW}/help{Colors.RESET} 查看命令，{Colors.YELLOW}/quit{Colors.RESET} 退出")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    def _print_entities(self, entities: List[str]):
        """打印提取的实体"""
        if entities:
            entity_str = ", ".join(f"{Colors.MAGENTA}{e}{Colors.RESET}" for e in entities)
            print(f"  {Colors.DIM}├─ 提取实体:{Colors.RESET} {entity_str}")
    
    def _print_separator(self):
        """打印分隔线"""
        print(f"{Colors.DIM}{'─'*60}{Colors.RESET}")
    
    def cmd_help(self):
        """显示帮助"""
        print(f"""
{Colors.CYAN}可用命令:{Colors.RESET}
  {Colors.YELLOW}/entities{Colors.RESET}      - 查看所有提取的实体
  {Colors.YELLOW}/relations{Colors.RESET}     - 查看实体关系图谱
  {Colors.YELLOW}/search <词>{Colors.RESET}   - 搜索记忆
  {Colors.YELLOW}/context{Colors.RESET}       - 查看当前构建的上下文
  {Colors.YELLOW}/memories{Colors.RESET}      - 查看所有记忆
  {Colors.YELLOW}/stats{Colors.RESET}         - 查看统计信息
  {Colors.YELLOW}/graph{Colors.RESET}         - 查看图谱概览（实体+关系）
  {Colors.YELLOW}/foreshadowing{Colors.RESET} - 查看伏笔
  {Colors.YELLOW}/clear{Colors.RESET}         - 清空当前用户记忆（需确认）
  {Colors.YELLOW}/debug{Colors.RESET}         - 切换调试模式
  {Colors.YELLOW}/help{Colors.RESET}          - 显示此帮助
  {Colors.YELLOW}/quit{Colors.RESET}          - 退出
""")
    
    def cmd_entities(self):
        """查看实体"""
        try:
            entities = self.recall.get_entities(self.user_id)
            if not entities:
                print(f"  {Colors.YELLOW}暂无实体{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}实体列表 ({len(entities)}个):{Colors.RESET}")
            for e in entities[:30]:
                name = e.get("name", "?")
                etype = e.get("type", "UNKNOWN")
                count = e.get("occurrence_count", 0)
                print(f"  • {Colors.MAGENTA}{name}{Colors.RESET} [{etype}] - 出现 {count} 次")
            
            if len(entities) > 30:
                print(f"  {Colors.DIM}... 还有 {len(entities)-30} 个{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取实体失败: {e}")
    
    def cmd_relations(self):
        """查看关系"""
        try:
            entities = self.recall.get_entities(self.user_id)
            if not entities:
                print(f"  {Colors.YELLOW}暂无实体{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}实体关系图谱:{Colors.RESET}")
            shown_relations = 0
            shown_entities = 0
            
            for e in entities[:15]:  # 显示前15个实体
                name = e.get("name", "")
                if not name:
                    continue
                
                try:
                    result = self.recall.get_related_entities(name)
                    # API 返回 {"entity": "xxx", "related": [...]}
                    relations = result.get("related", []) if isinstance(result, dict) else result
                    
                    print(f"\n  {Colors.MAGENTA}{name}{Colors.RESET}:")
                    shown_entities += 1
                    
                    if relations:
                        for r in relations[:5]:
                            if isinstance(r, dict):
                                target = r.get("name", r.get("target", "?"))
                                rtype = r.get("relation_type", r.get("type", "RELATED"))
                            else:
                                target = str(r)
                                rtype = "RELATED"
                            print(f"    └─[{rtype}]─→ {Colors.CYAN}{target}{Colors.RESET}")
                            shown_relations += 1
                        if len(relations) > 5:
                            print(f"    ... 还有 {len(relations) - 5} 个关系")
                    else:
                        print(f"    {Colors.DIM}(暂无关系){Colors.RESET}")
                except Exception as ex:
                    print(f"    {Colors.DIM}(获取关系失败: {ex}){Colors.RESET}")
            
            print(f"\n  {Colors.DIM}共显示 {shown_entities} 个实体, {shown_relations} 条关系{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取关系失败: {e}")
    
    def cmd_search(self, query: str):
        """搜索记忆"""
        if not query:
            print(f"  {Colors.YELLOW}请指定搜索词: /search <关键词>{Colors.RESET}")
            return
        
        try:
            results = self.recall.search_memories(query, self.user_id, top_k=10)
            
            if not results:
                print(f"  {Colors.YELLOW}未找到相关记忆{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}搜索结果 \"{query}\" ({len(results)}条):{Colors.RESET}")
            for i, r in enumerate(results[:10], 1):
                content = r.get("content", "")[:60]
                score = r.get("score", 0)
                print(f"  {i}. [{score:.2f}] {content}...")
        except Exception as e:
            self.logger.error(f"搜索失败: {e}")
    
    def cmd_context(self):
        """查看上下文"""
        try:
            context = self.recall.build_context("总结我们的对话", self.user_id)
            
            if not context:
                print(f"  {Colors.YELLOW}上下文为空{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}构建的上下文 ({len(context)}字符):{Colors.RESET}")
            print(f"{Colors.DIM}{'─'*50}{Colors.RESET}")
            # 分行显示，限制长度
            lines = context.split("\n")
            for line in lines[:30]:
                print(f"  {line[:80]}")
            if len(lines) > 30:
                print(f"  {Colors.DIM}... 还有 {len(lines)-30} 行{Colors.RESET}")
            print(f"{Colors.DIM}{'─'*50}{Colors.RESET}")
            
            self.logger.context_built(context)
        except Exception as e:
            self.logger.error(f"获取上下文失败: {e}")
    
    def cmd_memories(self):
        """查看记忆"""
        try:
            memories = self.recall.get_memories(self.user_id, limit=20)
            
            if not memories:
                print(f"  {Colors.YELLOW}暂无记忆{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}记忆列表 ({len(memories)}条):{Colors.RESET}")
            for m in memories:
                content = m.get("content", "")[:50]
                role = m.get("metadata", {}).get("role", "?")
                role_color = Colors.GREEN if role == "user" else Colors.BLUE
                print(f"  [{role_color}{role}{Colors.RESET}] {content}...")
        except Exception as e:
            self.logger.error(f"获取记忆失败: {e}")
    
    def cmd_stats(self):
        """查看统计"""
        try:
            stats = self.recall.get_stats()
            
            print(f"\n{Colors.CYAN}Recall 统计信息:{Colors.RESET}")
            print(f"  版本: {stats.get('version', '?')}")
            print(f"  模式: {stats.get('embedding_mode', '?')}")
            print(f"  存储: {stats.get('storage', {})}")
            print(f"  伏笔: {stats.get('foreshadowings', {})}")
        except Exception as e:
            self.logger.error(f"获取统计失败: {e}")
    
    def cmd_graph(self):
        """图谱概览"""
        print(f"\n{Colors.CYAN}=== 图谱概览 ==={Colors.RESET}")
        self.cmd_entities()
        self.cmd_relations()
    
    def cmd_foreshadowing(self):
        """查看伏笔"""
        try:
            foreshadowings = self.recall.get_foreshadowings(self.user_id)
            
            if not foreshadowings:
                print(f"  {Colors.YELLOW}暂无伏笔{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}伏笔列表 ({len(foreshadowings)}条):{Colors.RESET}")
            for f in foreshadowings:
                content = f.get("content", "")[:50]
                status = f.get("status", "?")
                print(f"  • [{status}] {content}...")
        except Exception as e:
            self.logger.error(f"获取伏笔失败: {e}")
    
    def cmd_clear(self):
        """清空记忆"""
        confirm = input(f"  {Colors.RED}确定要清空用户 {self.user_id} 的所有记忆吗？(yes/no): {Colors.RESET}")
        if confirm.lower() == "yes":
            try:
                self.recall.clear_memories(self.user_id)
                self.conversation_history.clear()
                self.turn_count = 0
                self.logger.success(f"已清空用户 {self.user_id} 的记忆")
            except Exception as e:
                self.logger.error(f"清空失败: {e}")
        else:
            print("  已取消")
    
    def cmd_debug(self):
        """切换调试模式"""
        self.debug = not self.debug
        self.logger.debug_mode = self.debug
        print(f"  调试模式: {Colors.GREEN if self.debug else Colors.RED}{'开启' if self.debug else '关闭'}{Colors.RESET}")
    
    def process_user_message(self, message: str):
        """处理用户消息"""
        self.turn_count += 1
        self.logger.user_input(message)
        
        # 1. 保存用户消息到 Recall
        print(f"\n{Colors.DIM}[Turn {self.turn_count}] 处理中...{Colors.RESET}")
        
        try:
            result = self.recall.add_memory(message, self.user_id, role="user")
            memory_id = result.get("id", "?")
            entities = result.get("entities", [])
            
            self.logger.memory_added(memory_id, message)
            self.logger.entity_extracted(entities)
            
            print(f"  {Colors.DIM}├─ 记忆ID:{Colors.RESET} {memory_id[:12]}...")
            self._print_entities(entities)
            
            # 一致性警告
            warnings = result.get("consistency_warnings", [])
            if warnings:
                for w in warnings:
                    print(f"  {Colors.YELLOW}├─ 一致性警告: {w}{Colors.RESET}")
                    self.logger.warning(f"Consistency: {w}")
            
        except Exception as e:
            self.logger.error(f"保存记忆失败: {e}")
            print(f"  {Colors.RED}├─ 保存失败: {e}{Colors.RESET}")
        
        # 2. 获取上下文并调用 LLM
        if self.llm:
            try:
                # 构建上下文
                context = self.recall.build_context(message, self.user_id)
                self.logger.context_built(context, len(context) // 4)
                
                if self.debug:
                    print(f"  {Colors.DIM}├─ 上下文长度: {len(context)} 字符{Colors.RESET}")
                
                # 准备系统提示词（包含 Recall 上下文）
                system_prompt = f"""你是一个友好的AI助手。

以下是关于用户的记忆和背景信息：
{context}

请基于以上信息回答用户的问题。如果信息不足，可以询问用户。"""
                
                # 调用 LLM
                self.conversation_history.append({"role": "user", "content": message})
                
                # 只保留最近10轮对话
                recent_history = self.conversation_history[-20:]
                
                ai_response = self.llm.chat(recent_history, system_prompt)
                self.logger.ai_response(ai_response)
                
                # 保存 AI 回复到 Recall
                try:
                    ai_result = self.recall.add_memory(ai_response, self.user_id, role="assistant")
                    ai_entities = ai_result.get("entities", [])
                    if self.debug and ai_entities:
                        print(f"  {Colors.DIM}├─ AI回复实体: {ai_entities}{Colors.RESET}")
                except Exception:
                    pass
                
                self.conversation_history.append({"role": "assistant", "content": ai_response})
                
                # 打印 AI 回复
                self._print_separator()
                print(f"{Colors.BLUE}AI:{Colors.RESET} {ai_response}")
                
            except Exception as e:
                self.logger.error(f"LLM 调用失败: {e}")
                print(f"  {Colors.RED}├─ LLM 调用失败: {e}{Colors.RESET}")
        else:
            self._print_separator()
            print(f"{Colors.YELLOW}[未配置 LLM，仅记录记忆]{Colors.RESET}")
    
    def run(self):
        """运行主循环"""
        # 健康检查
        if not self.recall.health_check():
            self.logger.error("无法连接到 Recall 服务，请确保服务已启动")
            print(f"{Colors.RED}错误: 无法连接到 Recall 服务 ({RECALL_API_BASE}){Colors.RESET}")
            print("请先启动服务: python -m recall.server 或 .\\start.ps1")
            return
        
        self._print_header()
        
        while True:
            try:
                # 获取输入
                user_input = input(f"{Colors.GREEN}你:{Colors.RESET} ").strip()
                
                if not user_input:
                    continue
                
                # 处理命令
                if user_input.startswith("/"):
                    cmd_parts = user_input[1:].split(maxsplit=1)
                    cmd = cmd_parts[0].lower()
                    arg = cmd_parts[1] if len(cmd_parts) > 1 else ""
                    
                    if cmd in ("quit", "exit", "q"):
                        self.logger.info("用户退出")
                        print(f"\n{Colors.CYAN}再见！日志已保存。{Colors.RESET}\n")
                        break
                    elif cmd == "help":
                        self.cmd_help()
                    elif cmd == "entities":
                        self.cmd_entities()
                    elif cmd == "relations":
                        self.cmd_relations()
                    elif cmd == "search":
                        self.cmd_search(arg)
                    elif cmd == "context":
                        self.cmd_context()
                    elif cmd == "memories":
                        self.cmd_memories()
                    elif cmd == "stats":
                        self.cmd_stats()
                    elif cmd == "graph":
                        self.cmd_graph()
                    elif cmd == "foreshadowing":
                        self.cmd_foreshadowing()
                    elif cmd == "clear":
                        self.cmd_clear()
                    elif cmd == "debug":
                        self.cmd_debug()
                    else:
                        print(f"  {Colors.YELLOW}未知命令: {cmd}，输入 /help 查看帮助{Colors.RESET}")
                else:
                    # 处理普通消息
                    self.process_user_message(user_input)
                
            except KeyboardInterrupt:
                self.logger.info("用户中断")
                print(f"\n\n{Colors.CYAN}已中断，日志已保存。{Colors.RESET}\n")
                break
            except EOFError:
                break
            except Exception as e:
                self.logger.error(f"未处理的错误: {e}")
                print(f"{Colors.RED}错误: {e}{Colors.RESET}")


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(description="Recall 交互式聊天测试工具")
    parser.add_argument("--user", "-u", default="chat_test", help="用户ID")
    parser.add_argument("--debug", "-d", action="store_true", help="开启调试模式")
    parser.add_argument("--api", default="http://localhost:18888", help="Recall API 地址")
    
    args = parser.parse_args()
    
    global RECALL_API_BASE
    RECALL_API_BASE = args.api
    
    app = RecallChatApp(user_id=args.user, debug=args.debug)
    app.run()


if __name__ == "__main__":
    main()
