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
    
    # 支持的配置项（包括新增的 MODEL 配置）
    local supported_keys="SILICONFLOW_API_KEY SILICONFLOW_MODEL OPENAI_API_KEY OPENAI_API_BASE OPENAI_MODEL EMBEDDING_API_KEY EMBEDDING_API_BASE EMBEDDING_MODEL EMBEDDING_DIMENSION RECALL_EMBEDDING_MODE"
    
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
# ============================================
# Recall API 配置文件
# ============================================
# 
# 使用方法：
# 1. 直接用文本编辑器打开此文件
# 2. 填入你需要的配置（三种方式选一种）
# 3. 保存文件
# 4. 热更新: curl -X POST http://localhost:18888/v1/config/reload
# 5. 测试连接: curl http://localhost:18888/v1/config/test
#
# ============================================


# ============================================
# 方式一：硅基流动（推荐国内用户，便宜快速）
# ============================================
# 获取地址：https://cloud.siliconflow.cn/
SILICONFLOW_API_KEY=
# 模型选择（默认 BAAI/bge-large-zh-v1.5）
# 可选: BAAI/bge-large-zh-v1.5, BAAI/bge-m3, BAAI/bge-large-en-v1.5
SILICONFLOW_MODEL=BAAI/bge-large-zh-v1.5


# ============================================
# 方式二：OpenAI（支持官方和中转站）
# ============================================
# 获取地址：https://platform.openai.com/
OPENAI_API_KEY=
# API 地址（默认官方，可改为中转站地址）
OPENAI_API_BASE=
# 模型选择（默认 text-embedding-3-small）
# 可选: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
OPENAI_MODEL=text-embedding-3-small


# ============================================
# 方式三：自定义 API（Azure/Ollama/其他兼容服务）
# ============================================
# 适用于：Azure OpenAI、本地Ollama、其他OpenAI兼容服务
# 注意：需要同时填写 KEY、BASE、MODEL、DIMENSION
EMBEDDING_API_KEY=
EMBEDDING_API_BASE=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=1536


# ============================================
# 常用 Embedding 模型参考
# ============================================
# 
# OpenAI:
#   text-embedding-3-small   维度:1536  推荐,性价比高
#   text-embedding-3-large   维度:3072  精度更高
#   text-embedding-ada-002   维度:1536  旧版本
# 
# 硅基流动:
#   BAAI/bge-large-zh-v1.5   维度:1024  中文推荐
#   BAAI/bge-m3              维度:1024  多语言
#   BAAI/bge-large-en-v1.5   维度:1024  英文
#
# Ollama (本地):
#   nomic-embed-text         维度:768
#   mxbai-embed-large        维度:1024
#
# ============================================
# 模式说明
# ============================================
# 
# 【轻量模式】不需要填写任何配置
#   - 仅使用关键词搜索，无语义搜索
#   - 内存占用最低（~100MB）
# 
# 【Hybrid模式】需要 API 配置（上面三种方式选一种）
#   - 支持语义搜索
#   - 内存占用低（~150MB）
# 
# 【完整模式】不需要填写任何配置
#   - 使用本地模型，完全离线
#   - 内存占用高（~1.5GB）
#
# ============================================
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
                # Hybrid 模式需要检查 API Key（支持多种配置方式）
                # 优先级：custom > siliconflow > openai
                if [ -n "$EMBEDDING_API_KEY" ] && [ -n "$EMBEDDING_API_BASE" ]; then
                    echo "custom"
                elif [ -n "$SILICONFLOW_API_KEY" ]; then
                    echo "siliconflow"
                elif [ -n "$OPENAI_API_KEY" ]; then
                    echo "openai"
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
        echo -e "  或设置环境变量："
        echo ""
        echo -e "  方式1 - OpenAI:"
        echo -e "    ${CYAN}export OPENAI_API_KEY=sk-xxx${NC}"
        echo ""
        echo -e "  方式2 - 硅基流动 (推荐国内用户):"
        echo -e "    ${CYAN}export SILICONFLOW_API_KEY=sf-xxx${NC}"
        echo ""
        echo -e "  方式3 - 自定义 API (中转站等):"
        echo -e "    ${CYAN}export EMBEDDING_API_KEY=sk-xxx${NC}"
        echo -e "    ${CYAN}export EMBEDDING_API_BASE=https://your-api.com/v1${NC}"
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
        openai)
            local base_info=""
            [ -n "$OPENAI_API_BASE" ] && base_info=" ($OPENAI_API_BASE)"
            print_info "Embedding: ${GREEN}Hybrid-OpenAI${NC}$base_info"
            ;;
        siliconflow)
            print_info "Embedding: ${GREEN}Hybrid-硅基流动${NC}"
            ;;
        custom)
            print_info "Embedding: ${GREEN}Hybrid-自定义${NC} ($EMBEDDING_API_BASE)"
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
