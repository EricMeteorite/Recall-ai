#!/bin/bash
# 
# Recall AI - Linux/Mac 启动脚本 v2.0
# 
# 用法: 
#   前台运行: ./start.sh
#   后台运行: ./start.sh --daemon 或 ./start.sh -d
#   停止服务: ./start.sh --stop 或 ./start.sh stop
#   查看状态: ./start.sh --status 或 ./start.sh status
#   查看日志: ./start.sh --logs 或 ./start.sh logs
#

set -e

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# ==================== 全局变量 ====================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$SCRIPT_DIR/recall-env"
DATA_PATH="$SCRIPT_DIR/recall_data"
PID_FILE="$SCRIPT_DIR/recall.pid"
LOG_FILE="$DATA_PATH/logs/recall.log"

# 配置
HOST="${RECALL_HOST:-0.0.0.0}"
PORT="${RECALL_PORT:-18888}"

# ==================== 工具函数 ====================

print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}         ${BOLD}Recall AI v4.1.0${NC}                  ${CYAN}║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "  ${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "  ${RED}✗${NC} $1"
}

print_warning() {
    echo -e "  ${YELLOW}!${NC} $1"
}

print_info() {
    echo -e "  ${CYAN}→${NC} $1"
}

# ==================== 权限修复 ====================

fix_permissions() {
    local CURRENT_USER=$(whoami)
    local DIR_OWNER=$(stat -c '%U' "$SCRIPT_DIR" 2>/dev/null || stat -f '%Su' "$SCRIPT_DIR" 2>/dev/null)
    
    if [ "$CURRENT_USER" != "root" ] && [ "$DIR_OWNER" = "root" ]; then
        echo -e "${YELLOW}检测到权限问题，正在修复...${NC}"
        if command -v sudo &> /dev/null; then
            sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$SCRIPT_DIR"
            print_success "权限修复成功"
        else
            print_error "无法修复权限，请运行: sudo chown -R $CURRENT_USER:$CURRENT_USER $SCRIPT_DIR"
            exit 1
        fi
    fi
}

# ==================== 检查安装 ====================

check_install() {
    if [ ! -d "$VENV_PATH" ]; then
        print_error "Recall 未安装"
        echo ""
        echo -e "  请先运行安装: ${CYAN}./install.sh${NC}"
        exit 1
    fi
    
    if [ ! -f "$VENV_PATH/bin/recall" ]; then
        print_error "安装不完整"
        echo ""
        echo -e "  请重新安装: ${CYAN}./install.sh --repair${NC}"
        exit 1
    fi
}

# ==================== 获取进程状态 ====================

get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

is_running() {
    local pid=$(get_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# ==================== 停止服务 ====================

do_stop() {
    print_header
    echo -e "${BOLD}停止服务${NC}"
    echo ""
    
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_info "正在停止 Recall 服务 (PID: $pid)..."
            kill "$pid"
            
            # 等待进程退出
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 0.5
                count=$((count + 1))
            done
            
            if kill -0 "$pid" 2>/dev/null; then
                print_warning "进程未响应，强制终止..."
                kill -9 "$pid" 2>/dev/null
            fi
            
            rm -f "$PID_FILE"
            print_success "服务已停止"
        else
            rm -f "$PID_FILE"
            print_warning "服务未运行 (已清理残留PID文件)"
        fi
    else
        print_warning "服务未运行"
    fi
}

# ==================== 查看状态 ====================

do_status() {
    print_header
    echo -e "${BOLD}📊 服务状态${NC}"
    echo ""
    
    # 服务状态
    if is_running; then
        local pid=$(get_pid)
        print_success "服务状态: ${GREEN}运行中${NC} (PID: $pid)"
        
        # 内存使用
        if command -v ps &> /dev/null; then
            local mem=$(ps -o rss= -p $pid 2>/dev/null | awk '{print int($1/1024)"MB"}')
            print_info "内存使用: $mem"
        fi
        
        # 运行时间
        if command -v ps &> /dev/null; then
            local uptime=$(ps -o etime= -p $pid 2>/dev/null | xargs)
            print_info "运行时间: $uptime"
        fi
    else
        print_error "服务状态: ${RED}未运行${NC}"
    fi
    
    echo ""
    
    # API 检查
    echo -e "${BOLD}🌐 API 状态${NC}"
    echo ""
    if command -v curl &> /dev/null; then
        local response=$(curl -s --connect-timeout 2 "http://localhost:$PORT/" 2>/dev/null)
        if [ -n "$response" ]; then
            print_success "API 地址: http://localhost:$PORT"
            print_success "API 响应: 正常"
            local ver=$(echo "$response" | grep -oP '"version"\s*:\s*"\K[^"]+' 2>/dev/null || echo "未知")
            print_info "版本: $ver"
        else
            print_error "API 响应: 无法连接"
        fi
    else
        print_warning "无法检查 API (curl 未安装)"
    fi
    
    echo ""
    
    # 日志
    if [ -f "$LOG_FILE" ]; then
        local log_size=$(du -h "$LOG_FILE" 2>/dev/null | cut -f1)
        print_info "日志文件: $LOG_FILE ($log_size)"
    fi
}

# ==================== 查看日志 ====================

do_logs() {
    print_header
    
    if [ ! -f "$LOG_FILE" ]; then
        print_warning "日志文件不存在"
        exit 0
    fi
    
    echo -e "${BOLD}📄 最近日志 (按 Ctrl+C 退出)${NC}"
    echo ""
    
    # 显示最后 50 行，然后实时跟踪
    tail -n 50 -f "$LOG_FILE"
}

# ==================== 加载配置文件 ====================

load_api_keys() {
    # 从配置文件加载配置
    local config_file="$DATA_PATH/config/api_keys.env"
    
    # 支持的配置项（与 server.py SUPPORTED_CONFIG_KEYS 保持一致）
    # 包括 v4.0 Phase 1/2 新增配置项
    # 包括 v4.0 Phase 3 十一层检索器配置项
    # 包括 v4.0 Phase 3.6 三路并行召回配置项（100%不遗忘保证）
    # 包括 v4.1 增强功能配置项
    local supported_keys="EMBEDDING_API_KEY EMBEDDING_API_BASE EMBEDDING_MODEL EMBEDDING_DIMENSION EMBEDDING_RATE_LIMIT EMBEDDING_RATE_WINDOW RECALL_EMBEDDING_MODE LLM_API_KEY LLM_API_BASE LLM_MODEL FORESHADOWING_LLM_ENABLED FORESHADOWING_TRIGGER_INTERVAL FORESHADOWING_AUTO_PLANT FORESHADOWING_AUTO_RESOLVE FORESHADOWING_MAX_RETURN FORESHADOWING_MAX_ACTIVE CONTEXT_TRIGGER_INTERVAL CONTEXT_MAX_CONTEXT_TURNS CONTEXT_MAX_PER_TYPE CONTEXT_MAX_TOTAL CONTEXT_DECAY_DAYS CONTEXT_DECAY_RATE CONTEXT_MIN_CONFIDENCE BUILD_CONTEXT_INCLUDE_RECENT PROACTIVE_REMINDER_ENABLED PROACTIVE_REMINDER_TURNS DEDUP_EMBEDDING_ENABLED DEDUP_HIGH_THRESHOLD DEDUP_LOW_THRESHOLD TEMPORAL_GRAPH_ENABLED TEMPORAL_GRAPH_BACKEND KUZU_BUFFER_POOL_SIZE TEMPORAL_DECAY_RATE TEMPORAL_MAX_HISTORY CONTRADICTION_DETECTION_ENABLED CONTRADICTION_AUTO_RESOLVE CONTRADICTION_DETECTION_STRATEGY CONTRADICTION_SIMILARITY_THRESHOLD FULLTEXT_ENABLED FULLTEXT_K1 FULLTEXT_B FULLTEXT_WEIGHT SMART_EXTRACTOR_MODE SMART_EXTRACTOR_COMPLEXITY_THRESHOLD SMART_EXTRACTOR_ENABLE_TEMPORAL BUDGET_DAILY_LIMIT BUDGET_HOURLY_LIMIT BUDGET_RESERVE BUDGET_ALERT_THRESHOLD DEDUP_JACCARD_THRESHOLD DEDUP_SEMANTIC_THRESHOLD DEDUP_SEMANTIC_LOW_THRESHOLD DEDUP_LLM_ENABLED ELEVEN_LAYER_RETRIEVER_ENABLED RETRIEVAL_L1_BLOOM_ENABLED RETRIEVAL_L2_TEMPORAL_ENABLED RETRIEVAL_L3_INVERTED_ENABLED RETRIEVAL_L4_ENTITY_ENABLED RETRIEVAL_L5_GRAPH_ENABLED RETRIEVAL_L6_NGRAM_ENABLED RETRIEVAL_L7_VECTOR_COARSE_ENABLED RETRIEVAL_L8_VECTOR_FINE_ENABLED RETRIEVAL_L9_RERANK_ENABLED RETRIEVAL_L10_CROSS_ENCODER_ENABLED RETRIEVAL_L11_LLM_ENABLED RETRIEVAL_L2_TEMPORAL_TOP_K RETRIEVAL_L3_INVERTED_TOP_K RETRIEVAL_L4_ENTITY_TOP_K RETRIEVAL_L5_GRAPH_TOP_K RETRIEVAL_L6_NGRAM_TOP_K RETRIEVAL_L7_VECTOR_TOP_K RETRIEVAL_L10_CROSS_ENCODER_TOP_K RETRIEVAL_L11_LLM_TOP_K RETRIEVAL_FINE_RANK_THRESHOLD RETRIEVAL_FINAL_TOP_K RETRIEVAL_L5_GRAPH_MAX_DEPTH RETRIEVAL_L5_GRAPH_MAX_ENTITIES RETRIEVAL_L5_GRAPH_DIRECTION RETRIEVAL_L10_CROSS_ENCODER_MODEL RETRIEVAL_L11_LLM_TIMEOUT RETRIEVAL_WEIGHT_INVERTED RETRIEVAL_WEIGHT_ENTITY RETRIEVAL_WEIGHT_GRAPH RETRIEVAL_WEIGHT_NGRAM RETRIEVAL_WEIGHT_VECTOR RETRIEVAL_WEIGHT_TEMPORAL QUERY_PLANNER_ENABLED QUERY_PLANNER_CACHE_SIZE QUERY_PLANNER_CACHE_TTL COMMUNITY_DETECTION_ENABLED COMMUNITY_DETECTION_ALGORITHM COMMUNITY_MIN_SIZE TRIPLE_RECALL_ENABLED TRIPLE_RECALL_RRF_K TRIPLE_RECALL_VECTOR_WEIGHT TRIPLE_RECALL_KEYWORD_WEIGHT TRIPLE_RECALL_ENTITY_WEIGHT VECTOR_IVF_HNSW_M VECTOR_IVF_HNSW_EF_CONSTRUCTION VECTOR_IVF_HNSW_EF_SEARCH FALLBACK_ENABLED FALLBACK_PARALLEL FALLBACK_WORKERS FALLBACK_MAX_RESULTS LLM_RELATION_MODE LLM_RELATION_COMPLEXITY_THRESHOLD LLM_RELATION_ENABLE_TEMPORAL LLM_RELATION_ENABLE_FACT_DESCRIPTION ENTITY_SUMMARY_ENABLED ENTITY_SUMMARY_MIN_FACTS EPISODE_TRACKING_ENABLED LLM_DEFAULT_MAX_TOKENS LLM_RELATION_MAX_TOKENS FORESHADOWING_MAX_TOKENS CONTEXT_EXTRACTION_MAX_TOKENS ENTITY_SUMMARY_MAX_TOKENS SMART_EXTRACTOR_MAX_TOKENS CONTRADICTION_MAX_TOKENS BUILD_CONTEXT_MAX_TOKENS RETRIEVAL_LLM_MAX_TOKENS DEDUP_LLM_MAX_TOKENS"
    
    if [ -f "$config_file" ]; then
        print_info "加载配置文件: $config_file"
        
        # 读取配置文件
        while IFS='=' read -r key value; do
            # 跳过注释和空行
            [[ "$key" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$key" ]] && continue
            
            # 去除空格
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs)
            
            # 只处理支持的配置项
            if [[ " $supported_keys " =~ " $key " ]]; then
                if [ -n "$value" ]; then
                    export "$key=$value"
                    # 敏感信息脱敏显示
                    if [[ "$key" == *"KEY"* ]]; then
                        local display_value="${value:0:8}..."
                    else
                        local display_value="$value"
                    fi
                    print_success "已加载: $key=$display_value"
                fi
            fi
        done < "$config_file"
    else
        # 创建默认配置文件
        mkdir -p "$DATA_PATH/config"
        cat > "$config_file" << 'EOF'
# ============================================================================
# Recall-AI 配置文件
# Recall-AI Configuration File
# ============================================================================
#
# ⚡ 快速开始 (90%的用户只需要配置这里)
# ⚡ Quick Start (90% users only need to configure this section)
#
# 1. 填写 EMBEDDING_API_KEY 和 EMBEDDING_API_BASE (必须)
# 2. 填写 LLM_API_KEY 和 LLM_API_BASE (可选，用于伏笔/矛盾等高级功能)
# 3. 启动服务: ./start.ps1 或 ./start.sh
#
# 其他所有配置项都有合理的默认值，无需修改！
# All other settings have sensible defaults, no changes needed!
#
# ============================================================================

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  ⭐ 必填配置 - REQUIRED CONFIGURATION                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ----------------------------------------------------------------------------
# Embedding 配置 (OpenAI 兼容接口) - 必填!
# Embedding Configuration (OpenAI Compatible API) - REQUIRED!
# ----------------------------------------------------------------------------
# 示例 (Examples):
#   OpenAI:      https://api.openai.com/v1
#   SiliconFlow: https://api.siliconflow.cn/v1  (推荐国内用户)
#   Ollama:      http://localhost:11434/v1
# ----------------------------------------------------------------------------
EMBEDDING_API_KEY=
EMBEDDING_API_BASE=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=1024

# Embedding 模式: auto(自动检测), local(本地), api(远程API)
# Embedding Mode: auto(auto detect), local(local model), api(remote API)
RECALL_EMBEDDING_MODE=auto

# ----------------------------------------------------------------------------
# LLM 配置 (OpenAI 兼容接口) - 用于伏笔分析、矛盾检测等高级功能
# LLM Configuration (OpenAI Compatible API) - For foreshadowing, contradiction, etc.
# ----------------------------------------------------------------------------
LLM_API_KEY=
LLM_API_BASE=
LLM_MODEL=

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  ⚙️ 可选配置 - OPTIONAL CONFIGURATION (以下内容可保持默认值)              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ----------------------------------------------------------------------------
# Embedding API 速率限制
# Embedding API Rate Limiting
# ----------------------------------------------------------------------------
# 每时间窗口最大请求数（默认10，设为0禁用）
# Max requests per time window (default 10, set 0 to disable)
EMBEDDING_RATE_LIMIT=10

# 速率限制时间窗口（秒，默认60）
# Rate limit time window in seconds (default 60)
EMBEDDING_RATE_WINDOW=60

# ----------------------------------------------------------------------------
# 伏笔分析器配置
# Foreshadowing Analyzer Configuration
# ----------------------------------------------------------------------------
# 是否启用 LLM 伏笔分析 (true/false)
# Enable LLM-based foreshadowing analysis
FORESHADOWING_LLM_ENABLED=true

# 分析触发间隔（每N轮对话触发一次分析，最小1）
# Analysis trigger interval (trigger analysis every N turns, minimum 1)
FORESHADOWING_TRIGGER_INTERVAL=10

# 自动埋下伏笔 (true/false)
# Automatically plant detected foreshadowing
FORESHADOWING_AUTO_PLANT=true

# 自动解决伏笔 (true/false) - 建议保持 false，让用户手动确认
# Automatically resolve detected foreshadowing (recommend false)
FORESHADOWING_AUTO_RESOLVE=false

# 伏笔召回数量（构建上下文时返回的伏笔数量）
# Number of foreshadowings to return when building context
FORESHADOWING_MAX_RETURN=10

# 活跃伏笔数量上限（超出时自动归档低优先级的伏笔）
# Max active foreshadowings (auto-archive low-priority ones when exceeded)
FORESHADOWING_MAX_ACTIVE=50

# ----------------------------------------------------------------------------
# 持久条件系统配置
# Persistent Context Configuration
# ----------------------------------------------------------------------------
# 条件提取触发间隔（每N轮对话触发一次LLM提取，最小1）
# Context extraction trigger interval (trigger every N turns, minimum 1)
CONTEXT_TRIGGER_INTERVAL=5

# 对话获取范围（分析时获取的历史轮数，确保有足够上下文）
# Max context turns for analysis (history turns to fetch for analysis)
CONTEXT_MAX_CONTEXT_TURNS=20

# 每类型最大条件数 / Max conditions per type
CONTEXT_MAX_PER_TYPE=10

# 条件总数上限 / Max total conditions
CONTEXT_MAX_TOTAL=100

# 置信度衰减开始天数 / Days before decay starts
CONTEXT_DECAY_DAYS=14

# 每次衰减比例 (0.0-1.0) / Decay rate per check
CONTEXT_DECAY_RATE=0.05

# 最低置信度（低于此值自动归档）/ Min confidence before archive
CONTEXT_MIN_CONFIDENCE=0.1

# ----------------------------------------------------------------------------
# 上下文构建配置（100%不遗忘保证）
# Context Building Configuration (100% Memory Guarantee)
# ----------------------------------------------------------------------------
# 构建上下文时包含的最近对话数（确保对话连贯性）
# Recent turns to include when building context
BUILD_CONTEXT_INCLUDE_RECENT=10

# 是否启用主动提醒（重要信息长期未提及时主动提醒AI）
# Enable proactive reminders for important info not mentioned for a while
PROACTIVE_REMINDER_ENABLED=true

# 主动提醒阈值（超过多少轮未提及则触发提醒）
# Turns threshold to trigger proactive reminder
PROACTIVE_REMINDER_TURNS=50

# ----------------------------------------------------------------------------
# 智能去重配置（持久条件和伏笔系统）
# Smart Deduplication Configuration (Persistent Context & Foreshadowing)
# ----------------------------------------------------------------------------
# 是否启用 Embedding 语义去重 (true/false)
# 启用后使用向量相似度判断重复，更智能；禁用则使用简单词重叠
# Enable Embedding-based semantic deduplication
DEDUP_EMBEDDING_ENABLED=true

# 高相似度阈值：超过此值直接合并（0.0-1.0，推荐0.85）
# High similarity threshold: auto-merge when exceeded (recommend 0.85)
DEDUP_HIGH_THRESHOLD=0.85

# 低相似度阈值：低于此值视为不相似（0.0-1.0，推荐0.70）
# Low similarity threshold: considered different when below (recommend 0.70)
DEDUP_LOW_THRESHOLD=0.70

# ============================================================================
# v4.0 Phase 1/2 新增配置
# v4.0 Phase 1/2 New Configurations
# ============================================================================

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# 统一知识图谱配置 (v4.0 统一架构)
# Unified Knowledge Graph Configuration (v4.0 Unified Architecture)
# ----------------------------------------------------------------------------
# 注意：v4.0 后图谱始终启用，此开关仅控制时态增强功能（衰减、历史限制等）
# Note: Graph is always enabled in v4.0, this switch only controls temporal enhancements
TEMPORAL_GRAPH_ENABLED=true

# 图谱存储后端: file(本地JSON文件), kuzu(嵌入式图数据库)
# Graph storage backend: file(local JSON), kuzu(embedded graph database)
# 此配置控制所有图数据的存储位置（包括实体关系）
# This setting controls storage for ALL graph data (including entity relations)
# Kuzu 提供更高的查询性能（需要 pip install kuzu）
TEMPORAL_GRAPH_BACKEND=file

# Kuzu 缓冲池大小（MB），仅当 TEMPORAL_GRAPH_BACKEND=kuzu 时生效
# Kuzu buffer pool size in MB, only used when backend is kuzu
KUZU_BUFFER_POOL_SIZE=256

# 时态信息衰减率（0.0-1.0，值越大衰减越快）
# Temporal decay rate (0.0-1.0, higher = faster decay)
TEMPORAL_DECAY_RATE=0.1

# 保留的最大时态历史记录数
# Max temporal history records to keep
TEMPORAL_MAX_HISTORY=1000

# ----------------------------------------------------------------------------
# 矛盾检测与管理配置
# Contradiction Detection & Management Configuration
# ----------------------------------------------------------------------------
# 是否启用矛盾检测
# Enable contradiction detection
CONTRADICTION_DETECTION_ENABLED=true

# 是否自动解决矛盾（推荐 false，让用户确认）
# Auto-resolve contradictions (recommend false, let user confirm)
CONTRADICTION_AUTO_RESOLVE=false

# 检测策略: RULE(规则), LLM(大模型判断), MIXED(混合), AUTO(自动选择)
# Detection strategy: RULE/LLM/MIXED/AUTO (HYBRID is deprecated alias for MIXED)
CONTRADICTION_DETECTION_STRATEGY=MIXED

# 相似度阈值（用于检测潜在矛盾，0.0-1.0）
# Similarity threshold for detecting potential contradictions
CONTRADICTION_SIMILARITY_THRESHOLD=0.8

# ----------------------------------------------------------------------------
# 全文检索配置 (BM25)
# Full-text Search Configuration (BM25)
# ----------------------------------------------------------------------------
# 是否启用 BM25 全文检索
# Enable BM25 full-text search
FULLTEXT_ENABLED=true

# BM25 k1 参数（词频饱和度，推荐 1.2-2.0）
# BM25 k1 parameter (term frequency saturation)
FULLTEXT_K1=1.5

# BM25 b 参数（文档长度归一化，0.0-1.0）
# BM25 b parameter (document length normalization)
FULLTEXT_B=0.75

# 全文检索在混合搜索中的权重（0.0-1.0）
# Full-text search weight in hybrid search
FULLTEXT_WEIGHT=0.3

# ----------------------------------------------------------------------------
# 智能抽取器配置 (SmartExtractor)
# Smart Extractor Configuration
# ----------------------------------------------------------------------------
# 抽取模式: RULES(规则), ADAPTIVE(自适应), LLM(全LLM)
# Extraction mode: RULES/ADAPTIVE/LLM (LOCAL/HYBRID/LLM_FULL are deprecated aliases)
SMART_EXTRACTOR_MODE=ADAPTIVE

# 复杂度阈值（超过此值使用 LLM 辅助抽取，0.0-1.0）
# Complexity threshold (use LLM when exceeded)
SMART_EXTRACTOR_COMPLEXITY_THRESHOLD=0.6

# 是否启用时态检测（识别时间相关信息）
# Enable temporal detection
SMART_EXTRACTOR_ENABLE_TEMPORAL=true

# ----------------------------------------------------------------------------
# 预算管理配置 (BudgetManager)
# Budget Management Configuration
# ----------------------------------------------------------------------------
# 每日预算上限（美元，0=无限制）
# Daily budget limit in USD (0 = unlimited)
BUDGET_DAILY_LIMIT=0

# 每小时预算上限（美元，0=无限制）
# Hourly budget limit in USD (0 = unlimited)
BUDGET_HOURLY_LIMIT=0

# 保留预算比例（为重要操作预留的预算比例，0.0-1.0）
# Reserve budget ratio for critical operations
BUDGET_RESERVE=0.1

# 预算警告阈值（使用量超过此比例时发出警告，0.0-1.0）
# Budget alert threshold (warn when usage exceeds this ratio)
BUDGET_ALERT_THRESHOLD=0.8

# ----------------------------------------------------------------------------
# 三阶段去重配置 (ThreeStageDeduplicator)
# Three-Stage Deduplication Configuration
# ----------------------------------------------------------------------------
# Jaccard 相似度阈值（阶段1 MinHash+LSH，0.0-1.0）
# Jaccard similarity threshold (Stage 1)
# 注意：0.85较保守，避免误判不同内容为重复
DEDUP_JACCARD_THRESHOLD=0.85

# 语义相似度高阈值（阶段2，超过此值直接合并）
# Semantic similarity high threshold (Stage 2, auto-merge when exceeded)
DEDUP_SEMANTIC_THRESHOLD=0.90

# 语义相似度低阈值（阶段2，低于此值视为不同）
# Semantic similarity low threshold (Stage 2, considered different when below)
DEDUP_SEMANTIC_LOW_THRESHOLD=0.80

# 是否启用 LLM 确认（阶段3，用于边界情况）
# Enable LLM confirmation (Stage 3, for borderline cases)
DEDUP_LLM_ENABLED=false

# ============================================================================
# v4.0 Phase 3 十一层检索器配置
# v4.0 Phase 3 Eleven-Layer Retriever Configuration
# ============================================================================

# ----------------------------------------------------------------------------
# 主开关
# Master Switch
# ----------------------------------------------------------------------------
# 是否启用十一层检索器（替代默认的八层检索器）
# Enable eleven-layer retriever (replaces default eight-layer)
ELEVEN_LAYER_RETRIEVER_ENABLED=true

# ----------------------------------------------------------------------------
# 层开关配置
# Layer Enable/Disable Configuration
# ----------------------------------------------------------------------------
# L1: Bloom Filter 快速否定（极低成本排除不相关记忆）
RETRIEVAL_L1_BLOOM_ENABLED=true

# L2: 时态过滤（根据时间范围筛选，需要 TEMPORAL_GRAPH_ENABLED=true）
RETRIEVAL_L2_TEMPORAL_ENABLED=true

# L3: 倒排索引（关键词匹配）
RETRIEVAL_L3_INVERTED_ENABLED=true

# L4: 实体索引（命名实体匹配）
RETRIEVAL_L4_ENTITY_ENABLED=true

# L5: 知识图谱遍历（实体关系扩展，需要 TEMPORAL_GRAPH_ENABLED=true）
RETRIEVAL_L5_GRAPH_ENABLED=true

# L6: N-gram 匹配（模糊文本匹配）
RETRIEVAL_L6_NGRAM_ENABLED=true

# L7: 向量粗排（ANN 近似最近邻）
RETRIEVAL_L7_VECTOR_COARSE_ENABLED=true

# L8: 向量精排（精确相似度计算）
RETRIEVAL_L8_VECTOR_FINE_ENABLED=true

# L9: 重排序（综合评分）
RETRIEVAL_L9_RERANK_ENABLED=true

# L10: CrossEncoder 精排（深度语义匹配，需要 sentence-transformers）
RETRIEVAL_L10_CROSS_ENCODER_ENABLED=true

# L11: LLM 过滤（大模型最终确认，消耗 API）
RETRIEVAL_L11_LLM_ENABLED=true

# ----------------------------------------------------------------------------
# Top-K 配置（每层返回的候选数量）
# Top-K Configuration (candidates returned per layer)
# ----------------------------------------------------------------------------
RETRIEVAL_L2_TEMPORAL_TOP_K=500
RETRIEVAL_L3_INVERTED_TOP_K=100
RETRIEVAL_L4_ENTITY_TOP_K=50
RETRIEVAL_L5_GRAPH_TOP_K=100
RETRIEVAL_L6_NGRAM_TOP_K=30
RETRIEVAL_L7_VECTOR_TOP_K=200
RETRIEVAL_L10_CROSS_ENCODER_TOP_K=50
RETRIEVAL_L11_LLM_TOP_K=20

# ----------------------------------------------------------------------------
# 阈值与最终输出配置
# Thresholds and Final Output Configuration
# ----------------------------------------------------------------------------
# 精排阈值（进入精排阶段的候选数）
RETRIEVAL_FINE_RANK_THRESHOLD=100

# 最终返回的记忆数量
RETRIEVAL_FINAL_TOP_K=20

# ----------------------------------------------------------------------------
# L5 知识图谱遍历配置
# L5 Knowledge Graph Traversal Configuration
# ----------------------------------------------------------------------------
# 图遍历最大深度
RETRIEVAL_L5_GRAPH_MAX_DEPTH=2

# 图遍历起始实体数量
RETRIEVAL_L5_GRAPH_MAX_ENTITIES=3

# 遍历方向: both(双向), outgoing(出边), incoming(入边)
RETRIEVAL_L5_GRAPH_DIRECTION=both

# ----------------------------------------------------------------------------
# L10 CrossEncoder 配置
# L10 CrossEncoder Configuration
# ----------------------------------------------------------------------------
# CrossEncoder 模型名称（需要安装 sentence-transformers）
RETRIEVAL_L10_CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# ----------------------------------------------------------------------------
# L11 LLM 配置
# L11 LLM Configuration
# ----------------------------------------------------------------------------
# LLM 判断超时时间（秒）
RETRIEVAL_L11_LLM_TIMEOUT=10.0

# ----------------------------------------------------------------------------
# 权重配置（调整各检索层的相对权重）
# Weight Configuration (adjust relative weight of each layer)
# ----------------------------------------------------------------------------
RETRIEVAL_WEIGHT_INVERTED=1.0
RETRIEVAL_WEIGHT_ENTITY=1.2
RETRIEVAL_WEIGHT_GRAPH=1.0
RETRIEVAL_WEIGHT_NGRAM=0.8
RETRIEVAL_WEIGHT_VECTOR=1.0
RETRIEVAL_WEIGHT_TEMPORAL=0.5

# ============================================================================
# v4.0 Phase 3.5 企业级性能配置
# v4.0 Phase 3.5 Enterprise Performance Configuration
# ============================================================================

# ----------------------------------------------------------------------------
# 图查询规划器配置 (QueryPlanner)
# Query Planner Configuration
# ----------------------------------------------------------------------------
# 是否启用图查询规划器（优化多跳图查询）
# Enable query planner (optimizes multi-hop graph queries)
QUERY_PLANNER_ENABLED=true

# 路径缓存大小（条）
# Path cache size (entries)
QUERY_PLANNER_CACHE_SIZE=1000

# 缓存过期时间（秒）
# Cache TTL (seconds)
QUERY_PLANNER_CACHE_TTL=300

# ----------------------------------------------------------------------------
# 社区检测配置 (CommunityDetector)
# Community Detection Configuration
# ----------------------------------------------------------------------------
# 是否启用社区检测（发现实体群组）
# Enable community detection (discover entity clusters)
COMMUNITY_DETECTION_ENABLED=false

# 检测算法: louvain | label_propagation | connected
# Detection algorithm
COMMUNITY_DETECTION_ALGORITHM=louvain

# 最小社区大小
# Minimum community size
COMMUNITY_MIN_SIZE=2

# ============================================================================
# v4.0 Phase 3.6 三路并行召回配置（100%不遗忘保证）
# v4.0 Phase 3.6 Triple Parallel Recall (100% Memory Guarantee)
# ============================================================================

# ----------------------------------------------------------------------------
# Triple Recall 主开关与 RRF 融合配置
# Triple Recall Switch and RRF Fusion Configuration
# ----------------------------------------------------------------------------
# 是否启用三路并行召回（语义+关键词+实体）
# Enable triple parallel recall (semantic + keyword + entity)
TRIPLE_RECALL_ENABLED=true

# RRF 常数 k（推荐 60，越大排名越平滑）
# RRF constant k (recommend 60, larger = smoother ranking)
TRIPLE_RECALL_RRF_K=60

# 语义召回权重（路径1）
# Semantic recall weight (path 1)
TRIPLE_RECALL_VECTOR_WEIGHT=1.0

# 关键词召回权重（路径2）
# Keyword recall weight (path 2)
TRIPLE_RECALL_KEYWORD_WEIGHT=1.2

# 实体召回权重（路径3）
# Entity recall weight (path 3)
TRIPLE_RECALL_ENTITY_WEIGHT=1.0

# ----------------------------------------------------------------------------
# IVF-HNSW 向量索引参数
# IVF-HNSW Vector Index Parameters
# ----------------------------------------------------------------------------
# HNSW 图连接数 M（推荐 32，越大精度越高但构建越慢）
# HNSW graph connections M (recommend 32)
VECTOR_IVF_HNSW_M=32

# 构建精度 ef_construction（推荐 200）
# Build precision ef_construction (recommend 200)
VECTOR_IVF_HNSW_EF_CONSTRUCTION=200

# 搜索精度 ef_search（推荐 64，越大精度越高但搜索越慢）
# Search precision ef_search (recommend 64)
VECTOR_IVF_HNSW_EF_SEARCH=64

# ----------------------------------------------------------------------------
# 原文兜底配置
# Raw Text Fallback Configuration
# ----------------------------------------------------------------------------
# 是否启用原文兜底（仅在融合结果为空时触发）
# Enable raw text fallback (only when fusion results are empty)
FALLBACK_ENABLED=true

# 是否启用并行兜底扫描（提升大规模数据的兜底速度）
# Enable parallel fallback scan (improve speed for large data)
FALLBACK_PARALLEL=true

# 并行扫描线程数（推荐 4）
# Parallel scan workers (recommend 4)
FALLBACK_WORKERS=4

# 兜底最大结果数
# Max fallback results
FALLBACK_MAX_RESULTS=50

# ============================================================================
# v4.1 增强功能配置 - RECALL 4.1 ENHANCED FEATURES
# ============================================================================

# ----------------------------------------------------------------------------
# LLM 关系提取配置
# LLM Relation Extraction Configuration
# ----------------------------------------------------------------------------
# 模式: rules（纯规则，默认）/ adaptive（自适应）/ llm（纯LLM）
# Mode: rules (pure rules, default) / adaptive / llm
LLM_RELATION_MODE=llm

# 自适应模式下触发 LLM 的复杂度阈值 (0.0-1.0)
# Complexity threshold to trigger LLM in adaptive mode
LLM_RELATION_COMPLEXITY_THRESHOLD=0.5

# 是否提取时态信息
# Enable temporal information extraction
LLM_RELATION_ENABLE_TEMPORAL=true

# 是否生成事实描述
# Enable fact description generation
LLM_RELATION_ENABLE_FACT_DESCRIPTION=true

# ----------------------------------------------------------------------------
# 实体摘要配置
# Entity Summary Configuration
# ----------------------------------------------------------------------------
# 是否启用实体摘要生成
# Enable entity summary generation
ENTITY_SUMMARY_ENABLED=true

# 触发 LLM 摘要的最小事实数
# Minimum facts to trigger LLM summary
ENTITY_SUMMARY_MIN_FACTS=5

# ----------------------------------------------------------------------------
# Episode 追溯配置
# Episode Tracking Configuration
# ----------------------------------------------------------------------------
# 是否启用 Episode 追溯
# Enable episode tracking
EPISODE_TRACKING_ENABLED=true

# ----------------------------------------------------------------------------
# LLM Max Tokens 配置
# LLM Max Tokens Configuration
# ----------------------------------------------------------------------------
# LLM 默认最大输出 tokens（通用默认值）
# Default max tokens for LLM output
LLM_DEFAULT_MAX_TOKENS=2000

# 关系提取最大 tokens（实体多时需要大值）
# Max tokens for relation extraction (need larger value for many entities)
LLM_RELATION_MAX_TOKENS=4000

# 伏笔分析最大 tokens
# Max tokens for foreshadowing analysis
FORESHADOWING_MAX_TOKENS=2000

# 条件提取最大 tokens
# Max tokens for context extraction
CONTEXT_EXTRACTION_MAX_TOKENS=2000

# 实体摘要最大 tokens
# Max tokens for entity summary
ENTITY_SUMMARY_MAX_TOKENS=2000

# 智能抽取最大 tokens
# Max tokens for smart extractor
SMART_EXTRACTOR_MAX_TOKENS=2000

# 矛盾检测最大 tokens
# Max tokens for contradiction detection
CONTRADICTION_MAX_TOKENS=1000

# 上下文构建最大 tokens
# Max tokens for context building
BUILD_CONTEXT_MAX_TOKENS=4000

# 检索 LLM 过滤最大 tokens（只需 yes/no，较小即可）
# Max tokens for retrieval LLM filter (only yes/no, keep small)
RETRIEVAL_LLM_MAX_TOKENS=200

# 去重 LLM 确认最大 tokens（只需 yes/no，较小即可）
# Max tokens for dedup LLM confirmation (only yes/no, keep small)
DEDUP_LLM_MAX_TOKENS=100
EOF
        print_info "已创建配置文件: $config_file"
        echo ""
        print_warning "首次运行，请先配置 API:"
        echo -e "     编辑: ${CYAN}$config_file${NC}"
        echo ""
        echo -e "  至少需要配置 Embedding API（用于语义搜索）:"
        echo -e "    ${CYAN}EMBEDDING_API_KEY=your-api-key${NC}"
        echo -e "    ${CYAN}EMBEDDING_API_BASE=https://api.siliconflow.cn/v1${NC}"
        echo -e "    ${CYAN}EMBEDDING_MODEL=BAAI/bge-m3${NC}"
        echo ""
        echo -e "  配置完成后重新运行: ${CYAN}./manage.sh${NC}"
        echo ""
        exit 0
    fi
}

# ==================== 检查 Embedding 模式 ====================

get_embedding_mode() {
    # 检查安装模式文件
    local mode_file="$DATA_PATH/config/install_mode"
    
    if [ -f "$mode_file" ]; then
        local install_mode=$(cat "$mode_file")
        case $install_mode in
            lite|lightweight) echo "none" ;;
            cloud|hybrid)
                # Cloud 模式需要检查 Embedding API Key
                # 排除占位符值
                if [ -n "$EMBEDDING_API_KEY" ] && \
                   [ "$EMBEDDING_API_KEY" != "your_embedding_api_key_here" ] && \
                   [ "$EMBEDDING_API_KEY" != "your_api_key_here" ] && \
                   [[ "$EMBEDDING_API_KEY" != your_* ]]; then
                    echo "api"
                else
                    echo "api_required"
                fi
                ;;
            local|full) echo "local" ;;
            *) echo "local" ;;
        esac
    else
        # 默认 Local 模式
        echo "local"
    fi
}

# ==================== 启动服务 ====================

do_start() {
    local daemon_mode=$1
    
    print_header
    
    # 检查权限
    fix_permissions
    
    # 检查安装
    check_install
    
    # 加载配置文件中的 API Keys
    load_api_keys
    
    # 检查是否已运行
    if is_running; then
        local pid=$(get_pid)
        print_warning "服务已在运行 (PID: $pid)"
        echo ""
        echo -e "  停止服务: ${CYAN}./start.sh --stop${NC}"
        echo -e "  查看状态: ${CYAN}./start.sh --status${NC}"
        exit 1
    fi
    
    # 获取 Embedding 模式
    local embedding_mode=$(get_embedding_mode)
    
    # 检查 Cloud 模式是否配置了 API Key
    if [ "$embedding_mode" = "api_required" ]; then
        print_error "Cloud 模式需要配置 API"
        echo ""
        echo -e "  ${YELLOW}请编辑配置文件: ${CYAN}$DATA_PATH/config/api_keys.env${NC}"
        echo ""
        echo -e "  设置以下配置项（OpenAI 兼容格式）:"
        echo -e "    ${CYAN}EMBEDDING_API_KEY=your-api-key${NC}"
        echo -e "    ${CYAN}EMBEDDING_API_BASE=https://your-api-provider/v1${NC}"
        echo -e "    ${CYAN}EMBEDDING_MODEL=your-embedding-model${NC}"
        echo -e "    ${CYAN}EMBEDDING_DIMENSION=1024${NC}"
        echo ""
        echo -e "  然后重新运行: ${CYAN}./start.sh${NC}"
        exit 1
    fi
    
    # 激活虚拟环境
    source "$VENV_PATH/bin/activate"
    
    # 确保日志目录存在
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # 显示启动配置
    echo -e "${BOLD}启动配置${NC}"
    echo ""
    print_info "监听地址: $HOST:$PORT"
    print_info "API 文档: http://localhost:$PORT/docs"
    
    # 显示 Embedding 模式
    case $embedding_mode in
        none)
            print_info "Embedding: ${YELLOW}Lite 模式${NC} (仅关键词搜索)"
            ;;
        api)
            local base_info=""
            [ -n "$EMBEDDING_API_BASE" ] && base_info=" ($EMBEDDING_API_BASE)"
            print_info "Embedding: ${GREEN}Cloud 模式${NC}$base_info"
            ;;
        local)
            print_info "Embedding: ${GREEN}Local 模式${NC} (本地模型)"
            ;;
    esac
    echo ""
    
    # 设置 Embedding 环境变量
    export RECALL_EMBEDDING_MODE="$embedding_mode"
    
    if [ "$daemon_mode" = true ]; then
        # 后台运行
        echo -e "${BOLD}🚀 后台启动${NC}"
        echo ""
        
        nohup recall serve --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
        local pid=$!
        echo $pid > "$PID_FILE"
        
        # 等待服务真正可用（最多 60 秒）
        print_info "启动中..."
        local max_wait=60
        local waited=0
        while [ $waited -lt $max_wait ]; do
            sleep 2
            waited=$((waited + 2))
            echo -n "."
            # 检查进程是否还存在
            if ! kill -0 $pid 2>/dev/null; then
                echo ""
                print_error "启动失败！进程已退出"
                rm -f "$PID_FILE"
                echo ""
                echo "查看日志获取详细错误:"
                echo -e "  ${CYAN}cat $LOG_FILE${NC}"
                exit 1
            fi
            # 检查服务是否可用
            if curl -s --connect-timeout 2 "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
                echo ""
                print_success "启动成功！(${waited}秒)"
                echo ""
                print_info "PID: $pid"
                print_info "日志: $LOG_FILE"
                echo ""
                echo -e "  查看日志: ${CYAN}./start.sh --logs${NC}"
                echo -e "  查看状态: ${CYAN}./start.sh --status${NC}"
                echo -e "  停止服务: ${CYAN}./start.sh --stop${NC}"
                return
            fi
        done
        
        # 超时但进程还在
        echo ""
        print_warning "启动超时，但进程仍在运行 (PID: $pid)"
        print_info "服务可能正在加载模型，请稍后检查状态"
        echo ""
        echo -e "  查看状态: ${CYAN}./start.sh --status${NC}"
        echo -e "  查看日志: ${CYAN}./start.sh --logs${NC}"
    else
        # 前台运行
        echo -e "${BOLD}🚀 前台运行 (按 Ctrl+C 停止)${NC}"
        echo ""
        
        recall serve --host "$HOST" --port "$PORT"
    fi
}

# ==================== 显示帮助 ====================

do_help() {
    print_header
    echo "用法: ./start.sh [命令] [选项]"
    echo ""
    echo "命令:"
    echo "  (无参数)        前台运行服务"
    echo "  -d, --daemon    后台运行服务"
    echo "  stop, --stop    停止服务"
    echo "  status, --status 查看服务状态"
    echo "  logs, --logs    查看实时日志"
    echo "  -h, --help      显示帮助"
    echo ""
    echo "环境变量:"
    echo "  RECALL_HOST     监听地址 (默认: 0.0.0.0)"
    echo "  RECALL_PORT     监听端口 (默认: 18888)"
    echo ""
    echo "示例:"
    echo "  ./start.sh              # 前台运行"
    echo "  ./start.sh -d           # 后台运行"
    echo "  ./start.sh stop         # 停止服务"
    echo "  RECALL_PORT=9000 ./start.sh -d  # 指定端口"
    echo ""
}

# ==================== 主入口 ====================

cd "$SCRIPT_DIR"

case "${1:-}" in
    -d|--daemon)
        do_start true
        ;;
    stop|--stop|-stop)
        do_stop
        ;;
    status|--status|-status|-s)
        do_status
        ;;
    logs|--logs|-logs|-l)
        do_logs
        ;;
    -h|--help|help)
        do_help
        ;;
    "")
        do_start false
        ;;
    *)
        echo "未知命令: $1"
        echo ""
        do_help
        exit 1
        ;;
esac
