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
    echo -e "${CYAN}║${NC}         ${BOLD}Recall AI v3.0.0${NC}                  ${CYAN}║${NC}"
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
    local supported_keys="EMBEDDING_API_KEY EMBEDDING_API_BASE EMBEDDING_MODEL EMBEDDING_DIMENSION RECALL_EMBEDDING_MODE LLM_API_KEY LLM_API_BASE LLM_MODEL FORESHADOWING_LLM_ENABLED FORESHADOWING_TRIGGER_INTERVAL FORESHADOWING_AUTO_PLANT FORESHADOWING_AUTO_RESOLVE FORESHADOWING_MAX_RETURN FORESHADOWING_MAX_ACTIVE CONTEXT_TRIGGER_INTERVAL CONTEXT_MAX_PER_TYPE CONTEXT_MAX_TOTAL CONTEXT_DECAY_DAYS CONTEXT_DECAY_RATE CONTEXT_MIN_CONFIDENCE DEDUP_EMBEDDING_ENABLED DEDUP_HIGH_THRESHOLD DEDUP_LOW_THRESHOLD CONTEXT_MAX_CONTEXT_TURNS BUILD_CONTEXT_INCLUDE_RECENT PROACTIVE_REMINDER_ENABLED PROACTIVE_REMINDER_TURNS"
    
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

# ----------------------------------------------------------------------------
# Embedding 配置 (OpenAI 兼容接口)
# Embedding Configuration (OpenAI Compatible API)
# ----------------------------------------------------------------------------
# 示例 (Examples):
#   OpenAI:      https://api.openai.com/v1
#   SiliconFlow: https://api.siliconflow.cn/v1
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
# LLM 配置 (OpenAI 兼容接口)
# LLM Configuration (OpenAI Compatible API)
# ----------------------------------------------------------------------------
LLM_API_KEY=
LLM_API_BASE=
LLM_MODEL=

# ----------------------------------------------------------------------------
# 伏笔分析器配置
# Foreshadowing Analyzer Configuration
# ----------------------------------------------------------------------------
# 是否启用 LLM 伏笔分析 (true/false)
# Enable LLM-based foreshadowing analysis
FORESHADOWING_LLM_ENABLED=false

# 分析触发间隔（每N轮对话触发一次分析，最小1）
# Analysis trigger interval (trigger analysis every N turns, minimum 1)
FORESHADOWING_TRIGGER_INTERVAL=10

# 自动埋下伏笔 (true/false)
# Automatically plant detected foreshadowing
FORESHADOWING_AUTO_PLANT=true

# 自动解决伏笔 (true/false) - 建议保持 false，让用户手动确认
# Automatically resolve detected foreshadowing (recommend false)
FORESHADOWING_AUTO_RESOLVE=false

# 获取伏笔时返回的最大数量 / Max foreshadowings returned per query
FORESHADOWING_MAX_RETURN=10

# 活跃伏笔上限（超出后自动归档最旧的） / Max active foreshadowings (auto-archive oldest)
FORESHADOWING_MAX_ACTIVE=50

# ----------------------------------------------------------------------------
# 持久条件配置
# Persistent Context Configuration
# ----------------------------------------------------------------------------
# 条件提取触发间隔（每N轮对话触发一次LLM提取，最小1）
# Context extraction trigger interval (trigger every N turns, minimum 1)
CONTEXT_TRIGGER_INTERVAL=5

# 每种类型最大条件数 / Max contexts per type
CONTEXT_MAX_PER_TYPE=10

# 总条件数上限 / Max total contexts
CONTEXT_MAX_TOTAL=100

# 置信度衰减开始天数 / Days before decay starts
CONTEXT_DECAY_DAYS=14

# 每次衰减比例 (0.0-1.0) / Decay rate per check
CONTEXT_DECAY_RATE=0.05

# 最低置信度阈值（低于此值自动归档） / Min confidence (below this auto-archive)
CONTEXT_MIN_CONFIDENCE=0.1

# ----------------------------------------------------------------------------
# 智能去重配置
# Smart Deduplication Configuration
# ----------------------------------------------------------------------------
# 是否启用 Embedding 去重 (true/false) / Enable embedding-based deduplication
DEDUP_EMBEDDING_ENABLED=true

# 高相似度阈值（>=此值自动合并） / High similarity threshold (auto-merge)
DEDUP_HIGH_THRESHOLD=0.85

# 低相似度阈值（<此值视为不同） / Low similarity threshold (treat as different)
DEDUP_LOW_THRESHOLD=0.70

# ----------------------------------------------------------------------------
# 上下文构建配置（100%不遗忘保证）
# Context Build Configuration (100% Memory Guarantee)
# ----------------------------------------------------------------------------
# 对话提取最大轮次（用于持久条件提取和伏笔分析）
# Max conversation turns for extraction (persistent context and foreshadowing analysis)
CONTEXT_MAX_CONTEXT_TURNS=20

# build_context 默认包含最近对话轮次
# Default recent turns included in build_context
BUILD_CONTEXT_INCLUDE_RECENT=10

# 启用主动提醒（长期未提及的重要信息会主动提醒）
# Enable proactive reminder for long-unmentioned important information
PROACTIVE_REMINDER_ENABLED=true

# 主动提醒触发轮次阈值（高重要性减半）
# Proactive reminder threshold turns (halved for high importance)
PROACTIVE_REMINDER_TURNS=50
EOF
        print_info "已创建配置文件: $config_file"
    fi
}

# ==================== 检查 Embedding 模式 ====================

get_embedding_mode() {
    # 检查安装模式文件
    local mode_file="$DATA_PATH/config/install_mode"
    
    if [ -f "$mode_file" ]; then
        local install_mode=$(cat "$mode_file")
        case $install_mode in
            lightweight) echo "none" ;;
            hybrid)
                # Hybrid 模式需要检查 Embedding API Key
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
            full) echo "local" ;;
            *) echo "local" ;;
        esac
    else
        # 默认完整模式
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
    
    # 检查 Hybrid 模式是否配置了 API Key
    if [ "$embedding_mode" = "api_required" ]; then
        print_error "Hybrid 模式需要配置 API"
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
            print_info "Embedding: ${YELLOW}轻量模式${NC} (仅关键词搜索)"
            ;;
        api)
            local base_info=""
            [ -n "$EMBEDDING_API_BASE" ] && base_info=" ($EMBEDDING_API_BASE)"
            print_info "Embedding: ${GREEN}Hybrid-API${NC}$base_info"
            ;;
        local)
            print_info "Embedding: ${GREEN}完整模式${NC} (本地模型)"
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
        
        # 等待启动
        print_info "启动中..."
        sleep 2
        
        if kill -0 $pid 2>/dev/null; then
            print_success "启动成功！"
            echo ""
            print_info "PID: $pid"
            print_info "日志: $LOG_FILE"
            echo ""
            echo -e "  查看日志: ${CYAN}./start.sh --logs${NC}"
            echo -e "  查看状态: ${CYAN}./start.sh --status${NC}"
            echo -e "  停止服务: ${CYAN}./start.sh --stop${NC}"
        else
            print_error "启动失败！"
            rm -f "$PID_FILE"
            echo ""
            echo "查看日志获取详细错误:"
            echo -e "  ${CYAN}cat $LOG_FILE${NC}"
            exit 1
        fi
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
