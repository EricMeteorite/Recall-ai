#!/bin/bash
# 
# Recall AI - Linux/Mac 启动脚本 v2.0
# 
# 用法: 
#   前台运行: ./start.sh
#   后台运行: ./start.sh --daemon 或 ./start.sh -d
#   停止服务: ./start.sh --stop 或 ./start.sh stop
#   重启服务: ./start.sh --restart 或 ./start.sh restart
#   查看状态: ./start.sh --status 或 ./start.sh status
#   查看日志: ./start.sh --logs 或 ./start.sh logs
#   指定端口: ./start.sh --port 8080
#   指定主机: ./start.sh --host 127.0.0.1
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
    echo -e "${CYAN}║${NC}         ${BOLD}Recall AI v7.0.0${NC}                  ${CYAN}║${NC}"
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
    # 包括 v4.2 性能优化配置项
    local supported_keys="EMBEDDING_API_KEY EMBEDDING_API_BASE EMBEDDING_MODEL EMBEDDING_DIMENSION EMBEDDING_RATE_LIMIT EMBEDDING_RATE_WINDOW RECALL_EMBEDDING_MODE LLM_API_KEY LLM_API_BASE LLM_MODEL LLM_TIMEOUT FORESHADOWING_LLM_ENABLED FORESHADOWING_TRIGGER_INTERVAL FORESHADOWING_AUTO_PLANT FORESHADOWING_AUTO_RESOLVE FORESHADOWING_MAX_RETURN FORESHADOWING_MAX_ACTIVE CONTEXT_TRIGGER_INTERVAL CONTEXT_MAX_CONTEXT_TURNS CONTEXT_MAX_PER_TYPE CONTEXT_MAX_TOTAL CONTEXT_DECAY_DAYS CONTEXT_DECAY_RATE CONTEXT_MIN_CONFIDENCE BUILD_CONTEXT_INCLUDE_RECENT PROACTIVE_REMINDER_ENABLED PROACTIVE_REMINDER_TURNS DEDUP_EMBEDDING_ENABLED DEDUP_HIGH_THRESHOLD DEDUP_LOW_THRESHOLD TEMPORAL_GRAPH_ENABLED TEMPORAL_GRAPH_BACKEND KUZU_BUFFER_POOL_SIZE TEMPORAL_DECAY_RATE TEMPORAL_MAX_HISTORY CONTRADICTION_DETECTION_ENABLED CONTRADICTION_AUTO_RESOLVE CONTRADICTION_DETECTION_STRATEGY CONTRADICTION_SIMILARITY_THRESHOLD FULLTEXT_ENABLED FULLTEXT_K1 FULLTEXT_B FULLTEXT_WEIGHT SMART_EXTRACTOR_MODE SMART_EXTRACTOR_COMPLEXITY_THRESHOLD SMART_EXTRACTOR_ENABLE_TEMPORAL BUDGET_DAILY_LIMIT BUDGET_HOURLY_LIMIT BUDGET_RESERVE BUDGET_ALERT_THRESHOLD DEDUP_JACCARD_THRESHOLD DEDUP_SEMANTIC_THRESHOLD DEDUP_SEMANTIC_LOW_THRESHOLD DEDUP_LLM_ENABLED ELEVEN_LAYER_RETRIEVER_ENABLED RETRIEVAL_L1_BLOOM_ENABLED RETRIEVAL_L2_TEMPORAL_ENABLED RETRIEVAL_L3_INVERTED_ENABLED RETRIEVAL_L4_ENTITY_ENABLED RETRIEVAL_L5_GRAPH_ENABLED RETRIEVAL_L6_NGRAM_ENABLED RETRIEVAL_L7_VECTOR_COARSE_ENABLED RETRIEVAL_L8_VECTOR_FINE_ENABLED RETRIEVAL_L9_RERANK_ENABLED RETRIEVAL_L10_CROSS_ENCODER_ENABLED RETRIEVAL_L11_LLM_ENABLED RETRIEVAL_L2_TEMPORAL_TOP_K RETRIEVAL_L3_INVERTED_TOP_K RETRIEVAL_L4_ENTITY_TOP_K RETRIEVAL_L5_GRAPH_TOP_K RETRIEVAL_L6_NGRAM_TOP_K RETRIEVAL_L7_VECTOR_TOP_K RETRIEVAL_L10_CROSS_ENCODER_TOP_K RETRIEVAL_L11_LLM_TOP_K RETRIEVAL_FINE_RANK_THRESHOLD RETRIEVAL_FINAL_TOP_K RETRIEVAL_L5_GRAPH_MAX_DEPTH RETRIEVAL_L5_GRAPH_MAX_ENTITIES RETRIEVAL_L5_GRAPH_DIRECTION RETRIEVAL_L10_CROSS_ENCODER_MODEL RETRIEVAL_L11_LLM_TIMEOUT RETRIEVAL_WEIGHT_INVERTED RETRIEVAL_WEIGHT_ENTITY RETRIEVAL_WEIGHT_GRAPH RETRIEVAL_WEIGHT_NGRAM RETRIEVAL_WEIGHT_VECTOR RETRIEVAL_WEIGHT_TEMPORAL QUERY_PLANNER_ENABLED QUERY_PLANNER_CACHE_SIZE QUERY_PLANNER_CACHE_TTL COMMUNITY_DETECTION_ENABLED COMMUNITY_DETECTION_ALGORITHM COMMUNITY_MIN_SIZE TRIPLE_RECALL_ENABLED TRIPLE_RECALL_RRF_K TRIPLE_RECALL_VECTOR_WEIGHT TRIPLE_RECALL_KEYWORD_WEIGHT TRIPLE_RECALL_ENTITY_WEIGHT VECTOR_IVF_HNSW_M VECTOR_IVF_HNSW_EF_CONSTRUCTION VECTOR_IVF_HNSW_EF_SEARCH FALLBACK_ENABLED FALLBACK_PARALLEL FALLBACK_WORKERS FALLBACK_MAX_RESULTS LLM_RELATION_MODE LLM_RELATION_COMPLEXITY_THRESHOLD LLM_RELATION_ENABLE_TEMPORAL LLM_RELATION_ENABLE_FACT_DESCRIPTION ENTITY_SUMMARY_ENABLED ENTITY_SUMMARY_MIN_FACTS EPISODE_TRACKING_ENABLED LLM_DEFAULT_MAX_TOKENS LLM_RELATION_MAX_TOKENS FORESHADOWING_MAX_TOKENS CONTEXT_EXTRACTION_MAX_TOKENS ENTITY_SUMMARY_MAX_TOKENS SMART_EXTRACTOR_MAX_TOKENS CONTRADICTION_MAX_TOKENS BUILD_CONTEXT_MAX_TOKENS RETRIEVAL_LLM_MAX_TOKENS DEDUP_LLM_MAX_TOKENS EMBEDDING_REUSE_ENABLED UNIFIED_ANALYZER_ENABLED UNIFIED_ANALYSIS_MAX_TOKENS TURN_API_ENABLED RECALL_MODE FORESHADOWING_ENABLED CHARACTER_DIMENSION_ENABLED RP_CONSISTENCY_ENABLED RP_RELATION_TYPES RP_CONTEXT_TYPES RERANKER_BACKEND COHERE_API_KEY RERANKER_MODEL ADMIN_KEY RECALL_BACKEND_TIER RECALL_CORS_ORIGINS RECALL_CORS_METHODS RECALL_RATE_LIMIT_RPM MCP_TRANSPORT MCP_PORT RECALL_DATA_ROOT RECALL_LOG_LEVEL RECALL_LOG_JSON RECALL_LOG_FILE RECALL_PIPELINE_MAX_SIZE RECALL_PIPELINE_RATE_LIMIT RECALL_PIPELINE_WORKERS RECALL_LANG RECALL_LIFECYCLE_ARCHIVE_DAYS RECALL_LIFECYCLE_BACKUP_ENABLED RECALL_LIFECYCLE_BACKUP_DIR RECALL_LIFECYCLE_CLEANUP_TEMP IVF_AUTO_SWITCH_ENABLED IVF_AUTO_SWITCH_THRESHOLD PARALLEL_RETRIEVER_WORKERS PARALLEL_RETRIEVER_TIMEOUT"
    
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
        template_file="$SCRIPT_DIR/recall/config_template.env"
        if [ -f "$template_file" ]; then
            cp "$template_file" "$config_file"
        else
            print_error "Template file not found: $template_file"
            exit 1
        fi
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

# ==================== 重启服务 ====================

do_restart() {
    print_header
    echo -e "${BOLD}重启服务${NC}"
    echo ""
    
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            print_info "正在停止 Recall 服务 (PID: $pid)..."
            kill "$pid"
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 0.5
                count=$((count + 1))
            done
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
            rm -f "$PID_FILE"
            sleep 2
        else
            rm -f "$PID_FILE"
        fi
    fi
    
    do_start true
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
    echo "  restart, --restart 重启服务"
    echo "  status, --status 查看服务状态"
    echo "  logs, --logs    查看实时日志"
    echo "  -h, --help      显示帮助"
    echo ""
    echo "选项:"
    echo "  --host ADDR     监听地址 (默认: 0.0.0.0)"
    echo "  --port PORT     监听端口 (默认: 18888)"
    echo ""
    echo "环境变量:"
    echo "  RECALL_HOST     监听地址 (默认: 0.0.0.0)"
    echo "  RECALL_PORT     监听端口 (默认: 18888)"
    echo ""
    echo "示例:"
    echo "  ./start.sh                        # 前台运行"
    echo "  ./start.sh -d                     # 后台运行"
    echo "  ./start.sh --port 8080            # 指定端口"
    echo "  ./start.sh -d --port 8080         # 后台运行指定端口"
    echo "  ./start.sh restart                # 重启服务"
    echo "  ./start.sh stop                   # 停止服务"
    echo ""
}

# ==================== 主入口 ====================

cd "$SCRIPT_DIR"

# 解析命令行参数
COMMAND=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            COMMAND="$1"
            shift
            ;;
    esac
done

case "${COMMAND:-}" in
    -d|--daemon)
        do_start true
        ;;
    stop|--stop|-stop)
        do_stop
        ;;
    restart|--restart|-restart)
        do_restart
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
        echo "未知命令: $COMMAND"
        echo ""
        do_help
        exit 1
        ;;
esac
