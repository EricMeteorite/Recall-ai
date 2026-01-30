#!/usr/bin/env python3
"""Recall 交互式聊天测试工具 v2.0

模拟完整的用户体验：
1. 用户输入消息
2. 消息存入 Recall（显示实体提取）
3. 从 Recall 获取相关上下文
4. 调用 LLM 生成回复
5. AI 回复也存入 Recall
6. 详细日志记录每一步

使用方法:
    python tools/chat_with_recall.py              # 交互模式
    python tools/chat_with_recall.py --user 角色名
    python tools/chat_with_recall.py --debug      # 更详细的日志
    python tools/chat_with_recall.py --auto-test  # 自动化功能测试
    python tools/chat_with_recall.py --character Alice  # 设置角色

命令:
    === 基础功能 ===
    /entities  - 查看所有实体
    /relations - 查看实体关系
    /search 关键词 - 搜索记忆
    /hsearch 关键词 - 混合搜索 (向量+关键词)
    /context - 查看当前上下文
    /memories - 查看所有记忆
    /stats - 查看统计信息
    
    === 图谱功能 ===
    /graph - 查看图谱概览
    /neighbors 实体名 - 查看实体邻居
    /traverse 实体名 - 图遍历
    /communities - 查看社区
    
    === 伏笔系统 ===
    /foreshadowing - 查看活跃伏笔
    /plant 内容 - 埋下新伏笔
    /resolve 伏笔ID 原因 - 解决伏笔
    /hint 伏笔ID 线索 - 添加伏笔线索
    /analyze - 触发伏笔分析
    
    === 时间查询 ===
    /timeline 实体名 - 查看实体时间线
    /temporal 时间描述 - 按时间查询
    
    === Recall 4.1 ===
    /episodes - 查看 Episode 追踪
    /contradictions - 查看矛盾检测
    /conditions - 查看持久条件
    /summary 实体名 - 查看实体摘要
    /v41 - 查看 4.1 功能状态
    /retrieval - 查看检索配置
    
    === 管理 ===
    /switch 角色名 - 切换角色
    /users - 查看所有用户
    /clear - 清空当前用户记忆
    /test - 运行自动化功能测试
    /debug - 切换调试模式
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
    
    # === Recall 4.1 新增 API ===
    
    def get_episodes(self, user_id: str, limit: int = 20) -> Dict:
        """获取 Episode 列表"""
        return self._request("GET", f"/v1/episodes?user_id={user_id}&limit={limit}")
    
    def get_contradictions(self, status: str = "pending") -> Dict:
        """获取矛盾列表"""
        return self._request("GET", f"/v1/contradictions?status={status}")
    
    def get_persistent_contexts(self, user_id: str) -> List[Dict]:
        """获取持久条件"""
        result = self._request("GET", f"/v1/persistent-contexts?user_id={user_id}")
        return result if isinstance(result, list) else []
    
    def get_entity_summary(self, name: str) -> Dict:
        """获取实体摘要"""
        return self._request("GET", f"/v1/entities/{urllib.parse.quote(name)}/summary")
    
    def get_v41_config(self) -> Dict:
        """获取 Recall 4.1 配置状态"""
        return self._request("GET", "/v1/config/v41")
    
    # === 伏笔系统扩展 API ===
    
    def plant_foreshadowing(self, content: str, user_id: str, importance: float = 0.5) -> Dict:
        """埋下伏笔"""
        return self._request("POST", "/v1/foreshadowing", {
            "content": content,
            "user_id": user_id,
            "character_id": user_id,
            "importance": importance
        })
    
    def resolve_foreshadowing(self, foreshadowing_id: str, user_id: str, resolution: str = None) -> Dict:
        """解决伏笔"""
        url = f"/v1/foreshadowing/{foreshadowing_id}/resolve?user_id={user_id}&character_id={user_id}"
        if resolution:
            url += f"&resolution={urllib.parse.quote(resolution)}"
        return self._request("POST", url)
    
    def add_foreshadowing_hint(self, foreshadowing_id: str, user_id: str, hint: str) -> Dict:
        """添加伏笔线索"""
        return self._request("POST", f"/v1/foreshadowing/{foreshadowing_id}/hint?user_id={user_id}&character_id={user_id}", {
            "hint": hint
        })
    
    def trigger_foreshadowing_analysis(self, user_id: str) -> Dict:
        """触发伏笔分析"""
        return self._request("POST", f"/v1/foreshadowing/analyze/trigger?user_id={user_id}&character_id={user_id}")
    
    # === 时间查询 API ===
    
    def query_temporal_at(self, time_point: str, user_id: str) -> Dict:
        """按时间点查询"""
        return self._request("POST", "/v1/temporal/at", {
            "time_point": time_point,
            "user_id": user_id
        })
    
    def get_entity_timeline(self, entity_name: str, user_id: str = None) -> Dict:
        """获取实体时间线"""
        url = f"/v1/temporal/timeline/{urllib.parse.quote(entity_name)}"
        if user_id:
            url += f"?user_id={user_id}"
        return self._request("GET", url)
    
    # === 搜索扩展 API ===
    
    def hybrid_search(self, query: str, user_id: str, top_k: int = 10) -> Dict:
        """混合搜索"""
        return self._request("POST", "/v1/search/hybrid", {
            "query": query,
            "user_id": user_id,
            "top_k": top_k
        })
    
    def fulltext_search(self, query: str, user_id: str, top_k: int = 10) -> Dict:
        """全文搜索"""
        return self._request("POST", "/v1/search/fulltext", {
            "query": query,
            "user_id": user_id,
            "top_k": top_k
        })
    
    def get_retrieval_config(self) -> Dict:
        """获取检索配置"""
        return self._request("GET", "/v1/search/config")
    
    # === 图谱扩展 API ===
    
    def get_entity_neighbors(self, entity_name: str, depth: int = 1) -> Dict:
        """获取实体邻居"""
        return self._request("GET", f"/v1/graph/entity/{urllib.parse.quote(entity_name)}/neighbors?depth={depth}")
    
    def graph_traverse(self, start_entity: str, relation_types: List[str] = None, max_depth: int = 2) -> Dict:
        """图遍历"""
        data = {
            "start_entity": start_entity,
            "max_depth": max_depth
        }
        if relation_types:
            data["relation_types"] = relation_types
        return self._request("POST", "/v1/graph/traverse", data)
    
    def get_communities(self) -> Dict:
        """获取社区"""
        return self._request("GET", "/v1/graph/communities")
    
    # === 管理 API ===
    
    def get_users(self) -> List[Dict]:
        """获取用户列表"""
        return self._request("GET", "/v1/users")
    
    def generate_entity_summary(self, entity_name: str) -> Dict:
        """生成实体摘要"""
        return self._request("POST", f"/v1/entities/{urllib.parse.quote(entity_name)}/generate-summary")


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
    
    def __init__(self, user_id: str, character_id: str = None, debug: bool = False):
        self.user_id = user_id
        self.character_id = character_id or user_id
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
        print(f"{Colors.BOLD}{Colors.CYAN}  Recall 交互式聊天测试工具 v2.0{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"  用户ID: {Colors.GREEN}{self.user_id}{Colors.RESET}")
        print(f"  角色ID: {Colors.GREEN}{self.character_id}{Colors.RESET}")
        print(f"  调试模式: {Colors.YELLOW}{'开启' if self.debug else '关闭'}{Colors.RESET}")
        print(f"  LLM: {Colors.GREEN if self.llm else Colors.RED}{'已配置' if self.llm else '未配置'}{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"  输入 {Colors.YELLOW}/help{Colors.RESET} 查看命令，{Colors.YELLOW}/quit{Colors.RESET} 退出")
        print(f"  输入 {Colors.YELLOW}/test{Colors.RESET} 运行自动化功能测试")
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
{Colors.CYAN}=== 基础功能 ==={Colors.RESET}
  {Colors.YELLOW}/entities{Colors.RESET}       - 查看所有提取的实体
  {Colors.YELLOW}/relations{Colors.RESET}      - 查看实体关系图谱
  {Colors.YELLOW}/search <词>{Colors.RESET}    - 语义搜索记忆
  {Colors.YELLOW}/hsearch <词>{Colors.RESET}   - 混合搜索 (向量+关键词)
  {Colors.YELLOW}/context{Colors.RESET}        - 查看构建的上下文
  {Colors.YELLOW}/memories{Colors.RESET}       - 查看所有记忆
  {Colors.YELLOW}/stats{Colors.RESET}          - 查看统计信息

{Colors.CYAN}=== 图谱功能 ==={Colors.RESET}
  {Colors.YELLOW}/graph{Colors.RESET}          - 查看图谱概览
  {Colors.YELLOW}/neighbors <名>{Colors.RESET} - 查看实体邻居
  {Colors.YELLOW}/traverse <名>{Colors.RESET}  - 从实体开始图遍历
  {Colors.YELLOW}/communities{Colors.RESET}    - 查看社区检测结果

{Colors.CYAN}=== 伏笔系统 ==={Colors.RESET}
  {Colors.YELLOW}/foreshadowing{Colors.RESET}  - 查看活跃伏笔
  {Colors.YELLOW}/plant <内容>{Colors.RESET}   - 埋下新伏笔
  {Colors.YELLOW}/resolve <ID> [原因]{Colors.RESET} - 解决伏笔
  {Colors.YELLOW}/hint <ID> <线索>{Colors.RESET} - 添加伏笔线索
  {Colors.YELLOW}/analyze{Colors.RESET}        - 触发伏笔分析

{Colors.CYAN}=== 时间查询 ==={Colors.RESET}
  {Colors.YELLOW}/timeline <实体名>{Colors.RESET} - 查看实体时间线
  {Colors.YELLOW}/temporal <时间描述>{Colors.RESET} - 按时间点查询

{Colors.CYAN}=== Recall 4.1 ==={Colors.RESET}
  {Colors.YELLOW}/episodes{Colors.RESET}       - 查看 Episode 追踪
  {Colors.YELLOW}/contradictions{Colors.RESET} - 查看矛盾检测结果
  {Colors.YELLOW}/conditions{Colors.RESET}     - 查看持久条件
  {Colors.YELLOW}/summary <名>{Colors.RESET}   - 查看实体摘要
  {Colors.YELLOW}/v41{Colors.RESET}            - 查看 4.1 功能状态
  {Colors.YELLOW}/retrieval{Colors.RESET}      - 查看11层检索配置

{Colors.CYAN}=== 管理功能 ==={Colors.RESET}
  {Colors.YELLOW}/switch <角色>{Colors.RESET}  - 切换角色
  {Colors.YELLOW}/users{Colors.RESET}          - 查看所有用户
  {Colors.YELLOW}/clear{Colors.RESET}          - 清空当前用户记忆
  {Colors.YELLOW}/test{Colors.RESET}           - 运行自动化功能测试
  {Colors.YELLOW}/debug{Colors.RESET}          - 切换调试模式
  {Colors.YELLOW}/help{Colors.RESET}           - 显示此帮助
  {Colors.YELLOW}/quit{Colors.RESET}           - 退出
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
                print(f"  {Colors.YELLOW}暂无活跃伏笔{Colors.RESET}")
                print(f"  {Colors.DIM}使用 /plant <内容> 埋下新伏笔{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}活跃伏笔 ({len(foreshadowings)}条):{Colors.RESET}")
            for f in foreshadowings:
                fsh_id = f.get("id", "?")[:8]
                content = f.get("content", "")[:50]
                status = f.get("status", "active")
                importance = f.get("importance", 0.5)
                hints = f.get("hints", [])
                
                status_color = Colors.GREEN if status == "active" else Colors.BLUE
                print(f"  • [{status_color}{status}{Colors.RESET}] {Colors.DIM}[{fsh_id}...]{Colors.RESET} {content}...")
                print(f"    {Colors.DIM}重要性: {importance:.0%}, 线索: {len(hints)}条{Colors.RESET}")
            
            print(f"\n  {Colors.DIM}命令: /plant /resolve /hint /analyze{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取伏笔失败: {e}")
    
    def cmd_clear(self):
        """清空记忆"""
        print(f"\n{Colors.YELLOW}将删除以下数据:{Colors.RESET}")
        print(f"  • 所有记忆")
        print(f"  • 实体和关系")
        print(f"  • 伏笔数据")
        print(f"  • 持久条件")
        print(f"  • 向量索引")
        print(f"  • 时态知识图谱")
        print(f"\n{Colors.GREEN}配置文件会保留{Colors.RESET}")
        print()
        
        confirm = input(f"  {Colors.RED}确定要清空用户 {self.user_id} 的所有数据吗？输入 'yes' 确认: {Colors.RESET}")
        if confirm.lower() == "yes":
            try:
                result = self.recall.clear_memories(self.user_id)
                deleted_count = result.get("deleted_count", 0)
                self.conversation_history.clear()
                self.turn_count = 0
                self.logger.success(f"已清空用户 {self.user_id} 的所有数据 (记忆: {deleted_count}条)")
            except Exception as e:
                self.logger.error(f"清空失败: {e}")
        else:
            print("  已取消")
    
    def cmd_debug(self):
        """切换调试模式"""
        self.debug = not self.debug
        self.logger.debug_mode = self.debug
        print(f"  调试模式: {Colors.GREEN if self.debug else Colors.RED}{'开启' if self.debug else '关闭'}{Colors.RESET}")
    
    # === Recall 4.1 新增命令 ===
    
    def cmd_episodes(self):
        """查看 Episode 追踪"""
        try:
            result = self.recall.get_episodes(self.user_id)
            
            if not result.get("enabled", False):
                print(f"  {Colors.YELLOW}Episode 追踪未启用{Colors.RESET}")
                print(f"  {Colors.DIM}提示: 设置 EPISODE_TRACKING_ENABLED=true 启用{Colors.RESET}")
                return
            
            episodes = result.get("episodes", [])
            if not episodes:
                print(f"  {Colors.YELLOW}暂无 Episode{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}Episode 列表 ({result.get('count', 0)}/{result.get('total', 0)}):{Colors.RESET}")
            for ep in episodes[:15]:
                uuid_short = ep.get("uuid", "")[:8]
                content = ep.get("content", "")[:40]
                mem_count = len(ep.get("memory_ids", []))
                ent_count = len(ep.get("entity_ids", []))
                print(f"  • [{uuid_short}...] {content}...")
                print(f"    {Colors.DIM}├─ 关联: {mem_count} 记忆, {ent_count} 实体{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取 Episode 失败: {e}")
    
    def cmd_contradictions(self):
        """查看矛盾检测结果"""
        try:
            result = self.recall.get_contradictions("all")
            
            contradictions = result.get("contradictions", [])
            if not contradictions:
                print(f"  {Colors.GREEN}未检测到矛盾{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}矛盾列表 ({len(contradictions)}条):{Colors.RESET}")
            for c in contradictions[:10]:
                ctype = c.get("type", "?")
                status = c.get("status", "pending")
                old_fact = c.get("old_fact", {}).get("fact", "")[:30]
                new_fact = c.get("new_fact", {}).get("fact", "")[:30]
                status_color = Colors.YELLOW if status == "pending" else Colors.GREEN
                print(f"  • [{status_color}{status}{Colors.RESET}] [{ctype}]")
                print(f"    {Colors.DIM}旧: {old_fact}...{Colors.RESET}")
                print(f"    {Colors.DIM}新: {new_fact}...{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取矛盾失败: {e}")
    
    def cmd_conditions(self):
        """查看持久条件"""
        try:
            contexts = self.recall.get_persistent_contexts(self.user_id)
            
            if not contexts:
                print(f"  {Colors.YELLOW}暂无持久条件{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}持久条件 ({len(contexts)}条):{Colors.RESET}")
            for ctx in contexts[:15]:
                content = ctx.get("content", "")[:50]
                ctype = ctx.get("type", "?")
                conf = ctx.get("confidence", 0)
                print(f"  • [{ctype}] {content}... (置信度: {conf:.0%})")
        except Exception as e:
            self.logger.error(f"获取持久条件失败: {e}")
    
    def cmd_summary(self, entity_name: str):
        """查看实体摘要"""
        if not entity_name:
            print(f"  {Colors.YELLOW}请指定实体名: /summary <实体名>{Colors.RESET}")
            return
        
        try:
            result = self.recall.get_entity_summary(entity_name)
            
            print(f"\n{Colors.CYAN}实体摘要: {entity_name}{Colors.RESET}")
            print(f"  摘要: {result.get('summary', '(无)')}")
            print(f"  事实数: {result.get('fact_count', 0)}")
            
            attrs = result.get('attributes', {})
            if attrs:
                print(f"  属性: {attrs}")
            
            last_update = result.get('last_summary_update')
            if last_update:
                print(f"  {Colors.DIM}最后更新: {last_update}{Colors.RESET}")
            
            if not result.get('summary_enabled'):
                print(f"  {Colors.YELLOW}提示: 实体摘要功能未启用，设置 ENTITY_SUMMARY_ENABLED=true{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取实体摘要失败: {e}")
    
    def cmd_v41(self):
        """查看 Recall 4.1 功能状态"""
        try:
            config = self.recall.get_v41_config()
            
            print(f"\n{Colors.CYAN}Recall 4.1 功能状态:{Colors.RESET}")
            
            # LLM 关系提取
            llm_rel = config.get("llm_relation_extractor", {})
            status = Colors.GREEN + "✓" if llm_rel.get("enabled") else Colors.RED + "✗"
            print(f"  {status}{Colors.RESET} LLM 关系提取: 模式={llm_rel.get('mode', 'rules')}")
            
            # 实体 Schema
            schema = config.get("entity_schema_registry", {})
            status = Colors.GREEN + "✓" if schema.get("enabled") else Colors.RED + "✗"
            print(f"  {status}{Colors.RESET} 实体 Schema 注册表: {schema.get('builtin_types', 0)} 内置类型")
            
            # Episode 追踪
            episode = config.get("episode_tracking", {})
            status = Colors.GREEN + "✓" if episode.get("enabled") else Colors.RED + "✗"
            print(f"  {status}{Colors.RESET} Episode 追踪")
            
            # 实体摘要
            summary = config.get("entity_summary", {})
            status = Colors.GREEN + "✓" if summary.get("enabled") else Colors.RED + "✗"
            print(f"  {status}{Colors.RESET} 实体摘要: min_facts={summary.get('min_facts', 5)}")
            
        except Exception as e:
            self.logger.error(f"获取 v4.1 配置失败: {e}")

    # === 新增命令：伏笔系统扩展 ===
    
    def cmd_plant(self, content: str):
        """埋下新伏笔"""
        if not content:
            print(f"  {Colors.YELLOW}请指定伏笔内容: /plant <内容>{Colors.RESET}")
            return
        
        try:
            result = self.recall.plant_foreshadowing(content, self.user_id)
            fsh_id = result.get("id", "?")[:8]
            print(f"  {Colors.GREEN}✓ 伏笔已埋下: [{fsh_id}...] {content[:40]}...{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"埋下伏笔失败: {e}")
    
    def cmd_resolve(self, args: str):
        """解决伏笔"""
        parts = args.split(maxsplit=1)
        if not parts:
            print(f"  {Colors.YELLOW}用法: /resolve <伏笔ID> [解决原因]{Colors.RESET}")
            return
        
        fsh_id = parts[0]
        resolution = parts[1] if len(parts) > 1 else None
        
        try:
            self.recall.resolve_foreshadowing(fsh_id, self.user_id, resolution)
            print(f"  {Colors.GREEN}✓ 伏笔已解决: {fsh_id}{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"解决伏笔失败: {e}")
    
    def cmd_hint(self, args: str):
        """添加伏笔线索"""
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            print(f"  {Colors.YELLOW}用法: /hint <伏笔ID> <线索内容>{Colors.RESET}")
            return
        
        fsh_id, hint = parts
        
        try:
            self.recall.add_foreshadowing_hint(fsh_id, self.user_id, hint)
            print(f"  {Colors.GREEN}✓ 线索已添加: {hint[:40]}...{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"添加线索失败: {e}")
    
    def cmd_analyze(self):
        """触发伏笔分析"""
        try:
            result = self.recall.trigger_foreshadowing_analysis(self.user_id)
            new_fsh = result.get("new_foreshadowings", [])
            resolved = result.get("resolved_foreshadowings", [])
            
            print(f"\n{Colors.CYAN}伏笔分析结果:{Colors.RESET}")
            if new_fsh:
                print(f"  {Colors.GREEN}发现 {len(new_fsh)} 个新伏笔{Colors.RESET}")
                for f in new_fsh[:5]:
                    print(f"    • {f.get('content', '')[:40]}...")
            if resolved:
                print(f"  {Colors.BLUE}解决 {len(resolved)} 个伏笔{Colors.RESET}")
            if not new_fsh and not resolved:
                print(f"  {Colors.DIM}未发现新伏笔或解决{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"伏笔分析失败: {e}")
    
    # === 新增命令：时间查询 ===
    
    def cmd_timeline(self, entity_name: str):
        """查看实体时间线"""
        if not entity_name:
            print(f"  {Colors.YELLOW}请指定实体名: /timeline <实体名>{Colors.RESET}")
            return
        
        try:
            result = self.recall.get_entity_timeline(entity_name, self.user_id)
            events = result.get("events", result.get("timeline", []))
            
            print(f"\n{Colors.CYAN}实体时间线: {entity_name}{Colors.RESET}")
            if not events:
                print(f"  {Colors.YELLOW}暂无时间线事件{Colors.RESET}")
                return
            
            for event in events[:15]:
                time_str = event.get("time", event.get("timestamp", "?"))
                content = event.get("content", event.get("description", ""))[:50]
                print(f"  • [{time_str}] {content}...")
        except Exception as e:
            self.logger.error(f"获取时间线失败: {e}")
    
    def cmd_temporal(self, time_query: str):
        """按时间点查询"""
        if not time_query:
            print(f"  {Colors.YELLOW}请指定时间描述: /temporal <时间描述>{Colors.RESET}")
            print(f"  {Colors.DIM}例如: /temporal 昨天 或 /temporal 2025年1月{Colors.RESET}")
            return
        
        try:
            result = self.recall.query_temporal_at(time_query, self.user_id)
            memories = result.get("memories", result.get("results", []))
            
            print(f"\n{Colors.CYAN}时间查询: {time_query}{Colors.RESET}")
            if not memories:
                print(f"  {Colors.YELLOW}未找到相关记忆{Colors.RESET}")
                return
            
            for m in memories[:10]:
                content = m.get("content", "")[:50]
                print(f"  • {content}...")
        except Exception as e:
            self.logger.error(f"时间查询失败: {e}")
    
    # === 新增命令：搜索扩展 ===
    
    def cmd_hsearch(self, query: str):
        """混合搜索"""
        if not query:
            print(f"  {Colors.YELLOW}请指定搜索词: /hsearch <关键词>{Colors.RESET}")
            return
        
        try:
            result = self.recall.hybrid_search(query, self.user_id, top_k=10)
            results = result.get("results", result) if isinstance(result, dict) else result
            
            if not results:
                print(f"  {Colors.YELLOW}未找到相关记忆{Colors.RESET}")
                return
            
            print(f"\n{Colors.CYAN}混合搜索 \"{query}\" ({len(results)}条):{Colors.RESET}")
            for i, r in enumerate(results[:10], 1):
                content = r.get("content", "")[:60]
                score = r.get("score", r.get("combined_score", 0))
                print(f"  {i}. [{score:.3f}] {content}...")
        except Exception as e:
            self.logger.error(f"混合搜索失败: {e}")
    
    # === 新增命令：图谱扩展 ===
    
    def cmd_neighbors(self, entity_name: str):
        """查看实体邻居"""
        if not entity_name:
            print(f"  {Colors.YELLOW}请指定实体名: /neighbors <实体名>{Colors.RESET}")
            return
        
        try:
            result = self.recall.get_entity_neighbors(entity_name)
            neighbors = result.get("neighbors", [])
            
            print(f"\n{Colors.CYAN}实体邻居: {entity_name}{Colors.RESET}")
            if not neighbors:
                print(f"  {Colors.YELLOW}暂无邻居{Colors.RESET}")
                return
            
            for n in neighbors[:20]:
                name = n.get("name", "?")
                relation = n.get("relation_type", n.get("relation", "?"))
                direction = n.get("direction", "->")
                print(f"  • {direction} [{relation}] {Colors.MAGENTA}{name}{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取邻居失败: {e}")
    
    def cmd_traverse(self, entity_name: str):
        """图遍历"""
        if not entity_name:
            print(f"  {Colors.YELLOW}请指定起始实体: /traverse <实体名>{Colors.RESET}")
            return
        
        try:
            result = self.recall.graph_traverse(entity_name)
            nodes = result.get("nodes", [])
            edges = result.get("edges", result.get("relations", []))
            
            print(f"\n{Colors.CYAN}图遍历: {entity_name} (深度=2){Colors.RESET}")
            print(f"  节点: {len(nodes)}, 边: {len(edges)}")
            
            if nodes:
                print(f"\n  {Colors.DIM}发现的节点:{Colors.RESET}")
                for n in nodes[:15]:
                    name = n.get("name", n) if isinstance(n, dict) else n
                    print(f"    • {Colors.MAGENTA}{name}{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"图遍历失败: {e}")
    
    def cmd_communities(self):
        """查看社区检测结果"""
        try:
            result = self.recall.get_communities()
            
            if not result.get("enabled", True):
                print(f"  {Colors.YELLOW}社区检测未启用{Colors.RESET}")
                print(f"  {Colors.DIM}设置 COMMUNITY_DETECTION_ENABLED=true 启用{Colors.RESET}")
                return
            
            communities = result.get("communities", [])
            print(f"\n{Colors.CYAN}社区检测结果 ({len(communities)}个社区):{Colors.RESET}")
            
            for i, comm in enumerate(communities[:10], 1):
                members = comm.get("members", comm.get("entities", []))
                label = comm.get("label", comm.get("name", f"社区{i}"))
                print(f"  {i}. {label} ({len(members)}个成员)")
                member_str = ", ".join(str(m)[:10] for m in members[:5])
                if len(members) > 5:
                    member_str += f" ... +{len(members)-5}"
                print(f"     {Colors.DIM}{member_str}{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取社区失败: {e}")
    
    # === 新增命令：检索配置 ===
    
    def cmd_retrieval(self):
        """查看检索配置"""
        try:
            config = self.recall.get_retrieval_config()
            
            print(f"\n{Colors.CYAN}11层检索器配置:{Colors.RESET}")
            
            layers = config.get("layers", config.get("config", {}))
            if isinstance(layers, dict):
                for layer_name, layer_config in layers.items():
                    enabled = layer_config.get("enabled", True)
                    status = Colors.GREEN + "✓" if enabled else Colors.RED + "✗"
                    weight = layer_config.get("weight", 1.0)
                    print(f"  {status}{Colors.RESET} {layer_name}: weight={weight}")
            else:
                print(f"  {Colors.DIM}配置: {config}{Colors.RESET}")
        except Exception as e:
            self.logger.error(f"获取检索配置失败: {e}")
    
    # === 新增命令：管理功能 ===
    
    def cmd_switch(self, character: str):
        """切换角色"""
        if not character:
            print(f"  {Colors.YELLOW}请指定角色名: /switch <角色名>{Colors.RESET}")
            return
        
        self.character_id = character
        self.conversation_history.clear()
        self.turn_count = 0
        print(f"  {Colors.GREEN}✓ 已切换到角色: {character}{Colors.RESET}")
    
    def cmd_users(self):
        """查看所有用户"""
        try:
            users = self.recall.get_users()
            users_list = users.get("users", users) if isinstance(users, dict) else users
            
            print(f"\n{Colors.CYAN}用户列表:{Colors.RESET}")
            if not users_list:
                print(f"  {Colors.YELLOW}暂无用户{Colors.RESET}")
                return
            
            for u in users_list[:20]:
                if isinstance(u, dict):
                    uid = u.get("user_id", u.get("id", "?"))
                    count = u.get("memory_count", "?")
                    print(f"  • {uid} ({count} 条记忆)")
                else:
                    print(f"  • {u}")
        except Exception as e:
            self.logger.error(f"获取用户列表失败: {e}")

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
    
    def run_auto_test(self):
        """运行自动化功能测试"""
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}  Recall 自动化功能测试{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
        
        # 健康检查
        if not self.recall.health_check():
            print(f"{Colors.RED}✗ 健康检查失败，无法连接到服务{Colors.RESET}")
            return False
        print(f"{Colors.GREEN}✓ 健康检查通过{Colors.RESET}")
        
        test_results = []
        test_user = f"auto_test_{int(time.time())}"
        
        # === 测试 1: 记忆基础功能 ===
        print(f"\n{Colors.CYAN}[1/10] 测试记忆基础功能...{Colors.RESET}")
        try:
            # 添加记忆
            result = self.recall.add_memory("我叫张三，今年25岁，住在北京海淀区。我喜欢编程和读书。", test_user)
            mem_id = result.get("id")
            entities = result.get("entities", [])
            
            if mem_id:
                print(f"  {Colors.GREEN}✓ 添加记忆成功: {mem_id[:12]}...{Colors.RESET}")
                if entities:
                    print(f"    提取实体: {entities}")
                test_results.append(("记忆存储", True))
            else:
                test_results.append(("记忆存储", False))
            
            # 搜索记忆
            results = self.recall.search_memories("张三在哪里", test_user)
            if results:
                print(f"  {Colors.GREEN}✓ 搜索记忆成功: 找到 {len(results)} 条{Colors.RESET}")
                test_results.append(("记忆搜索", True))
            else:
                test_results.append(("记忆搜索", False))
            
            # 获取记忆列表
            memories = self.recall.get_memories(test_user)
            print(f"  {Colors.GREEN}✓ 获取记忆列表: {len(memories)} 条{Colors.RESET}")
            test_results.append(("记忆列表", True))
        except Exception as e:
            print(f"  {Colors.RED}✗ 记忆基础功能测试失败: {e}{Colors.RESET}")
            test_results.append(("记忆基础", False))
        
        # === 测试 2: 实体和关系 ===
        print(f"\n{Colors.CYAN}[2/10] 测试实体和关系...{Colors.RESET}")
        try:
            # 添加更多记忆以建立关系
            self.recall.add_memory("张三的女朋友叫李四，他们在大学认识的。", test_user)
            self.recall.add_memory("李四是一名设计师，在阿里巴巴工作。", test_user)
            
            entities = self.recall.get_entities(test_user)
            print(f"  {Colors.GREEN}✓ 获取实体: {len(entities)} 个{Colors.RESET}")
            if entities:
                entity_names = [e.get("name", "") for e in entities[:5]]
                print(f"    实体: {entity_names}")
            test_results.append(("实体提取", len(entities) > 0))
            
            # 获取关系
            if entities:
                first_entity = entities[0].get("name", "")
                if first_entity:
                    related = self.recall.get_related_entities(first_entity)
                    relations = related.get("related", []) if isinstance(related, dict) else related
                    print(f"  {Colors.GREEN}✓ 实体关系: {first_entity} 有 {len(relations)} 个关系{Colors.RESET}")
                    test_results.append(("关系图谱", True))
        except Exception as e:
            print(f"  {Colors.RED}✗ 实体关系测试失败: {e}{Colors.RESET}")
            test_results.append(("实体关系", False))
        
        # === 测试 3: 上下文构建 ===
        print(f"\n{Colors.CYAN}[3/10] 测试上下文构建...{Colors.RESET}")
        try:
            context = self.recall.build_context("告诉我关于张三的信息", test_user)
            if context:
                print(f"  {Colors.GREEN}✓ 上下文构建成功: {len(context)} 字符{Colors.RESET}")
                test_results.append(("上下文构建", True))
            else:
                print(f"  {Colors.YELLOW}⚠ 上下文为空{Colors.RESET}")
                test_results.append(("上下文构建", False))
        except Exception as e:
            print(f"  {Colors.RED}✗ 上下文构建失败: {e}{Colors.RESET}")
            test_results.append(("上下文构建", False))
        
        # === 测试 4: 伏笔系统 ===
        print(f"\n{Colors.CYAN}[4/10] 测试伏笔系统...{Colors.RESET}")
        try:
            # 埋下伏笔
            fsh = self.recall.plant_foreshadowing("张三计划明年去日本旅行", test_user)
            fsh_id = fsh.get("id")
            if fsh_id:
                print(f"  {Colors.GREEN}✓ 埋下伏笔成功: {fsh_id[:12]}...{Colors.RESET}")
                test_results.append(("伏笔埋下", True))
                
                # 获取伏笔列表
                foreshadowings = self.recall.get_foreshadowings(test_user)
                print(f"  {Colors.GREEN}✓ 获取伏笔: {len(foreshadowings)} 条{Colors.RESET}")
                test_results.append(("伏笔列表", True))
            else:
                test_results.append(("伏笔系统", False))
        except Exception as e:
            print(f"  {Colors.RED}✗ 伏笔系统测试失败: {e}{Colors.RESET}")
            test_results.append(("伏笔系统", False))
        
        # === 测试 5: 混合搜索 ===
        print(f"\n{Colors.CYAN}[5/10] 测试混合搜索...{Colors.RESET}")
        try:
            result = self.recall.hybrid_search("北京 编程", test_user)
            results = result.get("results", result) if isinstance(result, dict) else result
            if results:
                print(f"  {Colors.GREEN}✓ 混合搜索成功: {len(results)} 条结果{Colors.RESET}")
                test_results.append(("混合搜索", True))
            else:
                print(f"  {Colors.YELLOW}⚠ 混合搜索无结果{Colors.RESET}")
                test_results.append(("混合搜索", False))
        except Exception as e:
            print(f"  {Colors.RED}✗ 混合搜索测试失败: {e}{Colors.RESET}")
            test_results.append(("混合搜索", False))
        
        # === 测试 6: 持久条件 ===
        print(f"\n{Colors.CYAN}[6/10] 测试持久条件...{Colors.RESET}")
        try:
            contexts = self.recall.get_persistent_contexts(test_user)
            print(f"  {Colors.GREEN}✓ 获取持久条件: {len(contexts)} 条{Colors.RESET}")
            test_results.append(("持久条件", True))
        except Exception as e:
            print(f"  {Colors.RED}✗ 持久条件测试失败: {e}{Colors.RESET}")
            test_results.append(("持久条件", False))
        
        # === 测试 7: Episode 追踪 ===
        print(f"\n{Colors.CYAN}[7/10] 测试 Episode 追踪...{Colors.RESET}")
        try:
            result = self.recall.get_episodes(test_user)
            enabled = result.get("enabled", False)
            episodes = result.get("episodes", [])
            if enabled:
                print(f"  {Colors.GREEN}✓ Episode 追踪已启用: {len(episodes)} 个 Episode{Colors.RESET}")
            else:
                print(f"  {Colors.YELLOW}⚠ Episode 追踪未启用{Colors.RESET}")
            test_results.append(("Episode追踪", True))
        except Exception as e:
            print(f"  {Colors.RED}✗ Episode 追踪测试失败: {e}{Colors.RESET}")
            test_results.append(("Episode追踪", False))
        
        # === 测试 8: 矛盾检测 ===
        print(f"\n{Colors.CYAN}[8/10] 测试矛盾检测...{Colors.RESET}")
        try:
            # 添加矛盾信息
            self.recall.add_memory("张三今年25岁", test_user)
            self.recall.add_memory("张三今年30岁了", test_user)
            
            result = self.recall.get_contradictions("all")
            contradictions = result.get("contradictions", [])
            print(f"  {Colors.GREEN}✓ 矛盾检测: {len(contradictions)} 条{Colors.RESET}")
            test_results.append(("矛盾检测", True))
        except Exception as e:
            print(f"  {Colors.RED}✗ 矛盾检测测试失败: {e}{Colors.RESET}")
            test_results.append(("矛盾检测", False))
        
        # === 测试 9: 检索配置 ===
        print(f"\n{Colors.CYAN}[9/10] 测试检索配置...{Colors.RESET}")
        try:
            config = self.recall.get_retrieval_config()
            print(f"  {Colors.GREEN}✓ 获取检索配置成功{Colors.RESET}")
            test_results.append(("检索配置", True))
        except Exception as e:
            print(f"  {Colors.RED}✗ 检索配置测试失败: {e}{Colors.RESET}")
            test_results.append(("检索配置", False))
        
        # === 测试 10: v4.1 功能状态 ===
        print(f"\n{Colors.CYAN}[10/10] 测试 v4.1 功能状态...{Colors.RESET}")
        try:
            config = self.recall.get_v41_config()
            print(f"  {Colors.GREEN}✓ 获取 v4.1 配置成功{Colors.RESET}")
            
            # 显示各功能状态
            llm_rel = config.get("llm_relation_extractor", {})
            summary = config.get("entity_summary", {})
            episode = config.get("episode_tracking", {})
            
            print(f"    - LLM关系提取: {'启用' if llm_rel.get('enabled') else '禁用'}")
            print(f"    - 实体摘要: {'启用' if summary.get('enabled') else '禁用'}")
            print(f"    - Episode追踪: {'启用' if episode.get('enabled') else '禁用'}")
            test_results.append(("v4.1功能", True))
        except Exception as e:
            print(f"  {Colors.RED}✗ v4.1 功能测试失败: {e}{Colors.RESET}")
            test_results.append(("v4.1功能", False))
        
        # === 清理测试数据 ===
        print(f"\n{Colors.CYAN}清理测试数据...{Colors.RESET}")
        try:
            self.recall.clear_memories(test_user)
            print(f"  {Colors.GREEN}✓ 测试数据已清理{Colors.RESET}")
        except Exception as e:
            print(f"  {Colors.YELLOW}⚠ 清理失败: {e}{Colors.RESET}")
        
        # === 测试结果汇总 ===
        print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}  测试结果汇总{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
        
        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)
        
        for name, result in test_results:
            status = Colors.GREEN + "✓ PASS" if result else Colors.RED + "✗ FAIL"
            print(f"  {status}{Colors.RESET} {name}")
        
        print(f"\n{Colors.CYAN}{'─'*60}{Colors.RESET}")
        color = Colors.GREEN if passed == total else Colors.YELLOW
        print(f"  {color}通过率: {passed}/{total} ({passed/total*100:.0f}%){Colors.RESET}")
        print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
        
        return passed == total
    
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
                    # === 伏笔系统扩展 ===
                    elif cmd == "plant":
                        self.cmd_plant(arg)
                    elif cmd == "resolve":
                        self.cmd_resolve(arg)
                    elif cmd == "hint":
                        self.cmd_hint(arg)
                    elif cmd == "analyze":
                        self.cmd_analyze()
                    # === 时间查询 ===
                    elif cmd == "timeline":
                        self.cmd_timeline(arg)
                    elif cmd == "temporal":
                        self.cmd_temporal(arg)
                    # === 搜索扩展 ===
                    elif cmd == "hsearch":
                        self.cmd_hsearch(arg)
                    # === 图谱扩展 ===
                    elif cmd == "neighbors":
                        self.cmd_neighbors(arg)
                    elif cmd == "traverse":
                        self.cmd_traverse(arg)
                    elif cmd == "communities":
                        self.cmd_communities()
                    # === 管理功能 ===
                    elif cmd == "switch":
                        self.cmd_switch(arg)
                    elif cmd == "users":
                        self.cmd_users()
                    elif cmd == "retrieval":
                        self.cmd_retrieval()
                    elif cmd == "test":
                        self.run_auto_test()
                    # === Recall 4.1 新增命令 ===
                    elif cmd == "episodes":
                        self.cmd_episodes()
                    elif cmd == "contradictions":
                        self.cmd_contradictions()
                    elif cmd == "conditions":
                        self.cmd_conditions()
                    elif cmd == "summary":
                        self.cmd_summary(arg)
                    elif cmd == "v41":
                        self.cmd_v41()
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
    parser.add_argument("--character", "-c", default=None, help="角色ID (默认与用户ID相同)")
    parser.add_argument("--debug", "-d", action="store_true", help="开启调试模式")
    parser.add_argument("--api", default="http://localhost:18888", help="Recall API 地址")
    parser.add_argument("--auto-test", action="store_true", help="运行自动化功能测试")
    
    args = parser.parse_args()
    
    global RECALL_API_BASE
    RECALL_API_BASE = args.api
    
    app = RecallChatApp(
        user_id=args.user, 
        character_id=args.character or args.user,
        debug=args.debug
    )
    
    if args.auto_test:
        app.run_auto_test()
    else:
        app.run()


if __name__ == "__main__":
    main()
