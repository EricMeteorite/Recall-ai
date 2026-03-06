#!/bin/bash
#
# Recall-ai 统一管理脚本
# 整合安装、启动、SillyTavern 插件管理等所有操作
#
# 版本: 1.0.0
# 支持: Linux / macOS

set -e

# ==================== 配置 ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/recall_data/config"
CONFIG_FILE="$CONFIG_DIR/manager.json"
VERSION="1.0.0"
DEFAULT_PORT=18888

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# ==================== 输出函数 ====================
print_title() {
    echo ""
    echo -e "  ${CYAN}$1${NC}"
    echo -e "  ${CYAN}$(printf '%*s' "${#1}" '' | tr ' ' '-')${NC}"
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
    echo -e "  ${YELLOW}ℹ${NC} $1"
}

print_dim() {
    echo -e "  ${GRAY}$1${NC}"
}

# ==================== 横幅 ====================
show_banner() {
    clear
    echo ""
    echo -e "  ${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "  ${CYAN}║                                                           ║${NC}"
    echo -e "  ${CYAN}║        🧠  Recall-ai 管理工具  v${VERSION}                    ║${NC}"
    echo -e "  ${CYAN}║                                                           ║${NC}"
    echo -e "  ${CYAN}║        智能记忆管理系统 - 让 AI 拥有持久记忆              ║${NC}"
    echo -e "  ${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ==================== 配置管理 ====================
get_config_value() {
    local key=$1
    if [[ -f "$CONFIG_FILE" ]]; then
        python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c.get('$key', ''))" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

save_config() {
    local key=$1
    local value=$2
    mkdir -p "$CONFIG_DIR"
    
    if [[ -f "$CONFIG_FILE" ]]; then
        python3 -c "
import json
c = json.load(open('$CONFIG_FILE'))
c['$key'] = '$value'
json.dump(c, open('$CONFIG_FILE', 'w'), indent=2)
" 2>/dev/null
    else
        echo "{\"$key\": \"$value\"}" > "$CONFIG_FILE"
    fi
}

# ==================== 状态检测 ====================
test_service_running() {
    curl -s --connect-timeout 3 "http://127.0.0.1:$DEFAULT_PORT/health" > /dev/null 2>&1
    return $?
}

test_installed() {
    [[ -d "$SCRIPT_DIR/recall-env" ]]
    return $?
}

get_st_plugin_path() {
    local st_path=$(get_config_value "st_path")
    if [[ -n "$st_path" ]]; then
        echo "$st_path/public/scripts/extensions/third-party/recall-memory"
    else
        echo ""
    fi
}

test_st_plugin_installed() {
    local plugin_path=$(get_st_plugin_path)
    [[ -n "$plugin_path" && -d "$plugin_path" ]]
    return $?
}

# ==================== 主菜单 ====================
show_main_menu() {
    local installed=$(test_installed && echo "yes" || echo "no")
    local running=$(test_service_running && echo "yes" || echo "no")
    local st_installed=$(test_st_plugin_installed && echo "yes" || echo "no")
    
    echo ""
    echo -e "  ${GRAY}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "  ${GRAY}│  当前状态                                               │${NC}"
    echo -e "  ${GRAY}├─────────────────────────────────────────────────────────┤${NC}"
    
    # Recall-ai 状态
    if [[ "$installed" == "yes" ]]; then
        if [[ "$running" == "yes" ]]; then
            echo -e "  ${GRAY}│  Recall-ai:     ${GREEN}✓ 已安装，运行中${NC}                        ${GRAY}│${NC}"
        else
            echo -e "  ${GRAY}│  Recall-ai:     ${YELLOW}✓ 已安装，未运行${NC}                        ${GRAY}│${NC}"
        fi
    else
        echo -e "  ${GRAY}│  Recall-ai:     ${RED}✗ 未安装${NC}                                  ${GRAY}│${NC}"
    fi
    
    # SillyTavern 插件状态
    if [[ "$st_installed" == "yes" ]]; then
        echo -e "  ${GRAY}│  SillyTavern 插件: ${GREEN}✓ 已安装${NC}                             ${GRAY}│${NC}"
    else
        echo -e "  ${GRAY}│  SillyTavern 插件: ${GRAY}✗ 未安装${NC}                             ${GRAY}│${NC}"
    fi
    
    echo -e "  ${GRAY}└─────────────────────────────────────────────────────────┘${NC}"
    
    echo ""
    echo -e "  ${WHITE}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "  ${WHITE}│                      主菜单                             │${NC}"
    echo -e "  ${WHITE}├─────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${WHITE}│                                                         │${NC}"
    echo -e "  ${WHITE}│    [1] 🔧 安装 Recall-ai                                │${NC}"
    echo -e "  ${WHITE}│    [2] 🚀 启动服务                                      │${NC}"
    echo -e "  ${WHITE}│    [3] 🛑 停止服务                                      │${NC}"
    echo -e "  ${WHITE}│    [4] 🔄 重启服务                                      │${NC}"
    echo -e "  ${WHITE}│    [5] 📊 查看状态                                      │${NC}"
    echo -e "  ${WHITE}│                                                         │${NC}"
    echo -e "  ${WHITE}│    [6] 📦 SillyTavern 插件管理  →                       │${NC}"
    echo -e "  ${WHITE}│    [7] ⚙️  配置管理              →                       │${NC}"
    echo -e "  ${WHITE}│                                                         │${NC}"
    echo -e "  ${RED}│    [8] 🗑️  清空用户数据（保留配置）                     │${NC}"
    echo -e "  ${WHITE}│                                                         │${NC}"
    echo -e "  ${WHITE}│    [0] 退出                                             │${NC}"
    echo -e "  ${WHITE}│                                                         │${NC}"
    echo -e "  ${WHITE}└─────────────────────────────────────────────────────────┘${NC}"
    echo ""
}

# ==================== SillyTavern 插件菜单 ====================
show_st_menu() {
    local st_installed=$(test_st_plugin_installed && echo "yes" || echo "no")
    local st_path=$(get_config_value "st_path")
    
    echo ""
    echo -e "  ${MAGENTA}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "  ${MAGENTA}│              SillyTavern 插件管理                       │${NC}"
    echo -e "  ${MAGENTA}├─────────────────────────────────────────────────────────┤${NC}"
    
    if [[ -n "$st_path" ]]; then
        local display_path="$st_path"
        if [[ ${#display_path} -gt 45 ]]; then
            display_path="${display_path:0:42}..."
        fi
        printf "  ${MAGENTA}│  ST 路径: ${GRAY}%-46s${MAGENTA}│${NC}\n" "$display_path"
    fi
    
    if [[ "$st_installed" == "yes" ]]; then
        echo -e "  ${MAGENTA}│  插件状态: ${GREEN}✓ 已安装${NC}                                     ${MAGENTA}│${NC}"
    else
        echo -e "  ${MAGENTA}│  插件状态: ${YELLOW}✗ 未安装${NC}                                     ${MAGENTA}│${NC}"
    fi
    
    echo -e "  ${MAGENTA}├─────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${MAGENTA}│                                                         │${NC}"
    echo -e "  ${MAGENTA}│    [1] 📥 安装插件到 SillyTavern                        │${NC}"
    echo -e "  ${MAGENTA}│    [2] 📤 卸载插件                                      │${NC}"
    echo -e "  ${MAGENTA}│    [3] 🔄 更新插件                                      │${NC}"
    echo -e "  ${MAGENTA}│    [4] 📂 设置 SillyTavern 路径                         │${NC}"
    echo -e "  ${MAGENTA}│    [5] 🔍 检查插件状态                                  │${NC}"
    echo -e "  ${MAGENTA}│                                                         │${NC}"
    echo -e "  ${MAGENTA}│    [0] ← 返回主菜单                                     │${NC}"
    echo -e "  ${MAGENTA}│                                                         │${NC}"
    echo -e "  ${MAGENTA}└─────────────────────────────────────────────────────────┘${NC}"
    echo ""
}

# ==================== 配置菜单 ====================
show_config_menu() {
    echo ""
    echo -e "  ${YELLOW}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "  ${YELLOW}│                    配置管理                             │${NC}"
    echo -e "  ${YELLOW}├─────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${YELLOW}│                                                         │${NC}"
    echo -e "  ${YELLOW}│    [1] 📝 编辑 API 配置文件                             │${NC}"
    echo -e "  ${YELLOW}│    [2] 🔄 热更新配置（无需重启）                        │${NC}"
    echo -e "  ${YELLOW}│    [3] 🧪 测试 Embedding API 连接                       │${NC}"
    echo -e "  ${YELLOW}│    [4] 🤖 测试 LLM API 连接                             │${NC}"
    echo -e "  ${YELLOW}│    [5] 📋 查看当前配置                                  │${NC}"
    echo -e "  ${YELLOW}│    [6] 🗑️  重置配置为默认值                             │${NC}"
    echo -e "  ${YELLOW}│                                                         │${NC}"
    echo -e "  ${YELLOW}│    [0] ← 返回主菜单                                     │${NC}"
    echo -e "  ${YELLOW}│                                                         │${NC}"
    echo -e "  ${YELLOW}└─────────────────────────────────────────────────────────┘${NC}"
    echo ""
}

# ==================== 操作函数 ====================

do_install() {
    print_title "安装 Recall-ai"
    
    if test_installed; then
        print_info "Recall-ai 已安装"
        read -p "  是否重新安装？(y/N) " choice
        if [[ "$choice" != "y" && "$choice" != "Y" ]]; then
            return
        fi
    fi
    
    local install_script="$SCRIPT_DIR/install.sh"
    if [[ -f "$install_script" ]]; then
        print_info "正在执行安装脚本..."
        bash "$install_script"
    else
        print_error "找不到安装脚本: $install_script"
    fi
}

do_start() {
    print_title "启动服务"
    
    if ! test_installed; then
        print_error "Recall-ai 未安装，请先安装"
        return
    fi
    
    if test_service_running; then
        print_info "服务已在运行中"
        return
    fi
    
    # 检查配置文件
    local config_file="$SCRIPT_DIR/recall_data/config/api_keys.env"
    local mode_file="$SCRIPT_DIR/recall_data/config/install_mode"
    local install_mode="local"
    
    if [[ -f "$mode_file" ]]; then
        install_mode=$(cat "$mode_file")
    fi
    
    # 如果是 cloud/hybrid 模式，检查 API 配置
    if [[ "$install_mode" == "cloud" ]] || [[ "$install_mode" == "hybrid" ]]; then
        local need_config=false
        
        if [[ ! -f "$config_file" ]]; then
            need_config=true
        else
            # 检查是否配置了有效的 API Key
            local api_key=$(grep -E "^EMBEDDING_API_KEY=" "$config_file" 2>/dev/null | cut -d'=' -f2 | xargs)
            if [[ -z "$api_key" ]] || [[ "$api_key" == your_* ]]; then
                need_config=true
            fi
        fi
        
        if [[ "$need_config" == "true" ]]; then
            # 确保配置文件存在
            if [[ ! -f "$config_file" ]]; then
                mkdir -p "$(dirname "$config_file")"
                template_file="$SCRIPT_DIR/recall/config_template.env"
                if [ -f "$template_file" ]; then
                    cp "$template_file" "$config_file"
                else
                    print_error "Template file not found: $template_file"
                    exit 1
                fi
                print_info "已创建配置文件: $config_file"
            fi
            
            echo ""
            print_warning "Cloud 模式需要配置 Embedding API"
            echo ""
            print_info "请编辑配置文件:"
            print_dim "  $config_file"
            echo ""
            print_info "配置完成后，再次启动服务"
            return
        fi
    fi
    
    local start_script="$SCRIPT_DIR/start.sh"
    local start_log="$SCRIPT_DIR/recall_data/logs/start.log"
    
    if [[ -f "$start_script" ]]; then
        print_info "正在启动服务..."
        
        # 确保日志目录存在
        mkdir -p "$(dirname "$start_log")"
        
        # 在后台启动，保存日志
        nohup bash "$start_script" > "$start_log" 2>&1 &
        
        # 等待服务启动（最多 60 秒，因为模型加载可能较慢）
        echo -n "  等待服务启动"
        local max_wait=60
        local waited=0
        while [ $waited -lt $max_wait ]; do
            sleep 2
            waited=$((waited + 2))
            echo -n "."
            if test_service_running; then
                echo ""
                print_success "服务已启动！(${waited}秒)"
                print_dim "API 地址: http://127.0.0.1:$DEFAULT_PORT"
                return
            fi
            # 检查进程是否还在运行
            if ! pgrep -f "uvicorn.*recall" > /dev/null 2>&1 && ! pgrep -f "recall serve" > /dev/null 2>&1; then
                echo ""
                print_error "服务进程已退出"
                break
            fi
        done
        echo ""
        
        # 检查是否启动失败
        if ! test_service_running; then
            print_error "服务启动超时或失败"
            echo ""
            print_info "启动日志:"
            if [[ -f "$start_log" ]]; then
                tail -20 "$start_log" | while read line; do
                    print_dim "  $line"
                done
            fi
            echo ""
            print_dim "完整日志: $start_log"
        fi
    else
        print_error "找不到启动脚本: $start_script"
    fi
}

do_stop() {
    print_title "停止服务"
    
    if ! test_service_running; then
        print_info "服务未在运行"
        return
    fi
    
    print_info "正在停止服务..."
    
    # 查找并终止进程
    local pids=$(pgrep -f "uvicorn.*recall" 2>/dev/null || true)
    
    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        print_success "服务已停止"
    else
        # 尝试通过端口查找
        local pid=$(lsof -ti:$DEFAULT_PORT 2>/dev/null || true)
        if [[ -n "$pid" ]]; then
            kill -9 $pid 2>/dev/null || true
            print_success "服务已停止"
        else
            print_info "未找到运行中的服务进程"
        fi
    fi
}

do_restart() {
    print_title "重启服务"
    do_stop
    sleep 2
    do_start
}

do_status() {
    print_title "服务状态"
    
    local installed=$(test_installed && echo "yes" || echo "no")
    local running=$(test_service_running && echo "yes" || echo "no")
    
    echo ""
    if [[ "$installed" == "yes" ]]; then
        print_success "Recall-ai 已安装"
        
        # 获取版本信息
        local venv_python="$SCRIPT_DIR/recall-env/bin/python"
        if [[ -f "$venv_python" ]]; then
            local version=$($venv_python -c "from recall.version import __version__; print(__version__)" 2>/dev/null || echo "")
            if [[ -n "$version" ]]; then
                print_dim "版本: v$version"
            fi
        fi
    else
        print_error "Recall-ai 未安装"
    fi
    
    echo ""
    if [[ "$running" == "yes" ]]; then
        print_success "服务运行中"
        print_dim "API 地址: http://127.0.0.1:$DEFAULT_PORT"
        
        # 获取统计信息
        local stats=$(curl -s "http://127.0.0.1:$DEFAULT_PORT/v1/stats" 2>/dev/null || echo "")
        if [[ -n "$stats" ]]; then
            local total=$(echo "$stats" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_memories', 'N/A'))" 2>/dev/null || echo "N/A")
            local mode=$(echo "$stats" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Lite 模式' if d.get('lite', False) or d.get('lightweight', False) else 'Local 模式')" 2>/dev/null || echo "N/A")
            print_dim "记忆总数: $total"
            print_dim "Embedding 模式: $mode"
        fi
    else
        print_error "服务未运行"
    fi
    
    echo ""
    if test_st_plugin_installed; then
        print_success "SillyTavern 插件已安装"
        local plugin_path=$(get_st_plugin_path)
        print_dim "路径: $plugin_path"
    else
        print_info "SillyTavern 插件未安装"
    fi
    
    echo ""
    read -p "  按 Enter 返回"
}

# ==================== 清空用户数据 ====================

do_clear_data() {
    print_title "清空用户数据"
    
    local data_path="$SCRIPT_DIR/recall_data"
    
    if [[ ! -d "$data_path" ]]; then
        print_info "未找到数据目录，无需清空"
        return
    fi
    
    # 检查服务是否运行
    if test_service_running; then
        print_error "服务正在运行，请先停止服务"
        echo ""
        echo -e "  运行: ${CYAN}./manage.sh stop${NC}"
        echo -e "  或在菜单中选择 [3] 停止服务"
        return
    fi
    
    # 显示将要删除的内容
    echo ""
    echo -e "  ${YELLOW}将删除以下数据:${NC}"
    echo ""
    
    local data_dir="$data_path/data"
    local cache_dir="$data_path/cache"
    local logs_dir="$data_path/logs"
    local temp_dir="$data_path/temp"
    local index_dir="$data_path/index"        # ngram, fulltext indexes
    local indexes_dir="$data_path/indexes"     # legacy indexes
    # v7.0: L1_consolidated 和 knowledge_graph 均在 data/ 内，删除 data/ 时自动覆盖
    
    local to_delete=()
    
    if [[ -d "$data_dir" ]]; then
        local size=$(du -sh "$data_dir" 2>/dev/null | cut -f1 || echo "0")
        echo -e "    ${RED}[x] data/           - 所有用户记忆 ($size)${NC}"
        to_delete+=("$data_dir")
    fi
    
    if [[ -d "$index_dir" ]]; then
        local size=$(du -sh "$index_dir" 2>/dev/null | cut -f1 || echo "0")
        echo -e "    ${RED}[x] index/          - N-gram 和全文索引 ($size)${NC}"
        to_delete+=("$index_dir")
    fi
    
    if [[ -d "$indexes_dir" ]]; then
        local size=$(du -sh "$indexes_dir" 2>/dev/null | cut -f1 || echo "0")
        echo -e "    ${RED}[x] indexes/        - 综合索引（元数据/向量/全文等） ($size)${NC}"
        to_delete+=("$indexes_dir")
    fi
    
    if [[ -d "$cache_dir" ]]; then
        local size=$(du -sh "$cache_dir" 2>/dev/null | cut -f1 || echo "0")
        echo -e "    ${RED}[x] cache/          - Embedding 缓存 ($size)${NC}"
        to_delete+=("$cache_dir")
    fi
    
    if [[ -d "$logs_dir" ]]; then
        local size=$(du -sh "$logs_dir" 2>/dev/null | cut -f1 || echo "0")
        echo -e "    ${RED}[x] logs/           - 日志文件 ($size)${NC}"
        to_delete+=("$logs_dir")
    fi
    
    if [[ -d "$temp_dir" ]]; then
        local size=$(du -sh "$temp_dir" 2>/dev/null | cut -f1 || echo "0")
        echo -e "    ${RED}[x] temp/           - 临时文件 ($size)${NC}"
        to_delete+=("$temp_dir")
    fi
    
    echo ""
    echo -e "  ${GREEN}将保留以下内容:${NC}"
    echo -e "    ${GREEN}[✓] config/    - API 密钥、安装模式、设置${NC}"
    echo -e "    ${GREEN}[✓] models/    - 已下载的模型（如有）${NC}"
    
    if [[ ${#to_delete[@]} -eq 0 ]]; then
        echo ""
        print_info "没有需要清空的数据"
        return
    fi
    
    echo ""
    echo -e "  ${YELLOW}⚠️  警告: 此操作不可撤销！${NC}"
    echo ""
    
    read -p "  输入 'yes' 确认删除: " confirm
    
    if [[ "$confirm" != "yes" ]]; then
        echo ""
        print_info "操作已取消"
        return
    fi
    
    echo ""
    print_info "正在清空用户数据..."
    
    for dir in "${to_delete[@]}"; do
        if rm -rf "$dir" 2>/dev/null; then
            local dir_name=$(basename "$dir")
            print_success "已删除: $dir_name/"
        else
            print_error "删除失败: $dir"
        fi
    done
    
    # 重新创建空目录（跳过文件如 knowledge_graph.json）
    for dir in "${to_delete[@]}"; do
        if [[ ! "$dir" =~ \.[a-zA-Z]+$ ]]; then
            mkdir -p "$dir"
        fi
    done
    
    echo ""
    print_success "用户数据已清空！"
    echo ""
    echo -e "  配置文件保留在: ${CYAN}recall_data/config/${NC}"
}

# ==================== SillyTavern 插件操作 ====================

set_st_path() {
    print_title "设置 SillyTavern 路径"
    
    local current_path=$(get_config_value "st_path")
    
    if [[ -n "$current_path" ]]; then
        print_dim "当前路径: $current_path"
    fi
    
    echo ""
    print_info "请输入 SillyTavern 的安装路径"
    print_dim "例如: /home/user/SillyTavern 或 ~/SillyTavern"
    echo ""
    
    read -p "  路径: " new_path
    
    if [[ -z "$new_path" ]]; then
        print_info "已取消"
        return
    fi
    
    # 展开 ~
    new_path="${new_path/#\~/$HOME}"
    
    # 验证路径
    if [[ ! -d "$new_path" ]]; then
        print_error "路径不存在: $new_path"
        return
    fi
    
    # 检查是否是有效的 ST 目录
    if [[ ! -f "$new_path/server.js" ]] || [[ ! -d "$new_path/public" ]]; then
        print_error "这不是有效的 SillyTavern 目录"
        print_dim "应该包含 server.js 和 public 文件夹"
        return
    fi
    
    save_config "st_path" "$new_path"
    print_success "路径已保存: $new_path"
}

install_st_plugin() {
    print_title "安装 SillyTavern 插件"
    
    local st_path=$(get_config_value "st_path")
    
    if [[ -z "$st_path" ]]; then
        print_error "未设置 SillyTavern 路径"
        print_info "请先设置路径（菜单选项 4）"
        return
    fi
    
    if [[ ! -d "$st_path" ]]; then
        print_error "SillyTavern 路径不存在: $st_path"
        return
    fi
    
    local source_dir="$SCRIPT_DIR/plugins/sillytavern"
    local target_dir="$st_path/public/scripts/extensions/third-party/recall-memory"
    
    if [[ ! -d "$source_dir" ]]; then
        print_error "找不到插件源文件: $source_dir"
        return
    fi
    
    # 创建目标目录
    if [[ -d "$target_dir" ]]; then
        print_info "插件目录已存在，将更新..."
        rm -rf "$target_dir"
    fi
    
    print_info "正在复制插件文件..."
    mkdir -p "$(dirname "$target_dir")"
    cp -r "$source_dir" "$target_dir"
    
    if [[ -d "$target_dir" ]]; then
        print_success "插件安装成功！"
        echo ""
        print_info "后续步骤："
        print_dim "1. 启动 Recall-ai 服务（主菜单选项 2）"
        print_dim "2. 启动/重启 SillyTavern"
        print_dim "3. 在 ST 扩展面板中找到 'Recall 记忆系统'"
    else
        print_error "插件安装失败"
    fi
}

uninstall_st_plugin() {
    print_title "卸载 SillyTavern 插件"
    
    if ! test_st_plugin_installed; then
        print_info "插件未安装"
        return
    fi
    
    local plugin_path=$(get_st_plugin_path)
    
    echo ""
    print_info "将删除: $plugin_path"
    read -p "  确认卸载？(y/N) " confirm
    
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        print_info "已取消"
        return
    fi
    
    if rm -rf "$plugin_path" 2>/dev/null; then
        print_success "插件已卸载"
        print_dim "重启 SillyTavern 后生效"
    else
        print_error "卸载失败"
    fi
}

update_st_plugin() {
    print_title "更新 SillyTavern 插件"
    
    if ! test_st_plugin_installed; then
        print_info "插件未安装，将执行安装..."
        install_st_plugin
        return
    fi
    
    print_info "正在更新插件..."
    install_st_plugin
}

check_st_plugin_status() {
    print_title "插件状态检查"
    
    local st_path=$(get_config_value "st_path")
    
    echo ""
    
    # ST 路径
    if [[ -n "$st_path" ]]; then
        print_success "SillyTavern 路径已配置"
        print_dim "路径: $st_path"
        
        if [[ -d "$st_path" ]]; then
            print_success "路径存在"
        else
            print_error "路径不存在！"
        fi
    else
        print_error "SillyTavern 路径未配置"
    fi
    
    echo ""
    
    # 插件状态
    if test_st_plugin_installed; then
        print_success "插件已安装"
        local plugin_path=$(get_st_plugin_path)
        print_dim "位置: $plugin_path"
        
        # 检查文件完整性
        local missing=""
        for file in "index.js" "style.css" "manifest.json"; do
            if [[ ! -f "$plugin_path/$file" ]]; then
                missing="$missing $file"
            fi
        done
        
        if [[ -z "$missing" ]]; then
            print_success "文件完整"
        else
            print_error "缺少文件:$missing"
        fi
    else
        print_error "插件未安装"
    fi
    
    echo ""
    
    # Recall 服务状态
    if test_service_running; then
        print_success "Recall 服务运行中"
    else
        print_error "Recall 服务未运行"
        print_dim "插件需要 Recall 服务才能工作"
    fi
    
    echo ""
    read -p "  按 Enter 返回"
}

# ==================== 配置操作 ====================

edit_config() {
    print_title "编辑配置文件"
    
    local config_file="$SCRIPT_DIR/recall_data/config/api_keys.env"
    
    if [[ ! -f "$config_file" ]]; then
        print_info "配置文件不存在，正在创建..."
        local venv_python="$SCRIPT_DIR/recall-env/bin/python"
        if [[ -f "$venv_python" ]]; then
            $venv_python -c "from recall.server import load_api_keys_from_file; load_api_keys_from_file()" 2>/dev/null || true
        fi
    fi
    
    if [[ -f "$config_file" ]]; then
        print_info "正在打开配置文件..."
        print_dim "文件: $config_file"
        
        # 尝试使用不同的编辑器
        if command -v nano &> /dev/null; then
            nano "$config_file"
        elif command -v vim &> /dev/null; then
            vim "$config_file"
        elif command -v vi &> /dev/null; then
            vi "$config_file"
        else
            print_error "未找到可用的文本编辑器"
            print_dim "请手动编辑: $config_file"
        fi
    else
        print_error "无法创建配置文件"
    fi
}

reload_config() {
    print_title "热更新配置"
    
    if ! test_service_running; then
        print_error "服务未运行，无法热更新"
        print_info "请先启动服务"
        return
    fi
    
    print_info "正在重新加载配置..."
    
    local response=$(curl -s -X POST "http://127.0.0.1:$DEFAULT_PORT/v1/config/reload" 2>/dev/null || echo "")
    
    if [[ -n "$response" ]]; then
        print_success "配置已重新加载！"
        
        # 显示当前模式
        local config_info=$(curl -s "http://127.0.0.1:$DEFAULT_PORT/v1/config" 2>/dev/null || echo "")
        if [[ -n "$config_info" ]]; then
            local mode=$(echo "$config_info" | python3 -c "import sys,json; print(json.load(sys.stdin).get('embedding', {}).get('mode', 'unknown'))" 2>/dev/null || echo "unknown")
            print_dim "当前 Embedding 模式: $mode"
        fi
    else
        print_error "热更新失败"
    fi
}

test_embedding_api() {
    print_title "测试 Embedding API"
    
    if ! test_service_running; then
        print_error "服务未运行"
        return
    fi
    
    print_info "正在测试 API 连接..."
    
    local result=$(curl -s "http://127.0.0.1:$DEFAULT_PORT/v1/config/test" 2>/dev/null || echo "")
    
    echo ""
    if [[ -n "$result" ]]; then
        local success=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "False")
        
        if [[ "$success" == "True" ]]; then
            print_success "API 连接成功！"
            local backend=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('backend', 'N/A'))" 2>/dev/null || echo "N/A")
            local model=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model', 'N/A'))" 2>/dev/null || echo "N/A")
            local dimension=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dimension', 'N/A'))" 2>/dev/null || echo "N/A")
            local latency=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('latency_ms', 'N/A'))" 2>/dev/null || echo "N/A")
            print_dim "后端: $backend"
            print_dim "模型: $model"
            print_dim "维度: $dimension"
            print_dim "延迟: ${latency}ms"
        else
            print_error "API 连接失败"
            local message=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message', ''))" 2>/dev/null || echo "")
            if [[ -n "$message" ]]; then
                print_dim "$message"
            fi
        fi
    else
        print_error "测试失败"
    fi
    
    echo ""
    read -p "  按 Enter 返回"
}

test_llm_api() {
    print_title "测试 LLM API"
    
    if ! test_service_running; then
        print_error "服务未运行"
        return
    fi
    
    print_info "正在测试 LLM API 连接..."
    
    local result=$(curl -s "http://127.0.0.1:$DEFAULT_PORT/v1/config/test/llm" 2>/dev/null || echo "")
    
    echo ""
    if [[ -n "$result" ]]; then
        local success=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "False")
        
        if [[ "$success" == "True" ]]; then
            print_success "LLM API 连接成功！"
            local model=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model', 'N/A'))" 2>/dev/null || echo "N/A")
            local api_base=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('api_base', 'N/A'))" 2>/dev/null || echo "N/A")
            local response=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response', 'N/A'))" 2>/dev/null || echo "N/A")
            local latency=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('latency_ms', 'N/A'))" 2>/dev/null || echo "N/A")
            print_dim "模型: $model"
            print_dim "API 地址: $api_base"
            print_dim "响应: $response"
            print_dim "延迟: ${latency}ms"
        else
            print_error "LLM API 连接失败"
            local message=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message', ''))" 2>/dev/null || echo "")
            if [[ -n "$message" ]]; then
                print_dim "$message"
            fi
        fi
    else
        print_error "测试失败"
    fi
    
    echo ""
    read -p "  按 Enter 返回"
}

show_current_config() {
    print_title "当前配置"
    
    if ! test_service_running; then
        print_error "服务未运行，无法获取配置"
        return
    fi
    
    local config=$(curl -s "http://127.0.0.1:$DEFAULT_PORT/v1/config" 2>/dev/null || echo "")
    
    if [[ -n "$config" ]]; then
        echo ""
        local mode=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('embedding', {}).get('mode', 'unknown'))" 2>/dev/null || echo "unknown")
        print_info "Embedding 模式: $mode"
        echo ""
        
        local config_file=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('config_file', ''))" 2>/dev/null || echo "")
        local file_exists=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('config_file_exists', False))" 2>/dev/null || echo "False")
        print_dim "配置文件: $config_file"
        print_dim "文件存在: $file_exists"
        
        echo ""
        print_info "Embedding 配置:"
        local emb_status=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('embedding', {}).get('status', '未配置'))" 2>/dev/null || echo "未配置")
        local emb_base=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('embedding', {}).get('api_base', '未配置'))" 2>/dev/null || echo "未配置")
        local emb_model=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('embedding', {}).get('model', '未配置'))" 2>/dev/null || echo "未配置")
        local emb_dim=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('embedding', {}).get('dimension', '未配置'))" 2>/dev/null || echo "未配置")
        if [[ "$emb_status" == "已配置" ]]; then
            echo -e "  状态: ${GREEN}$emb_status${NC}"
        else
            echo -e "  状态: ${GRAY}$emb_status${NC}"
        fi
        print_dim "  API 地址: $emb_base"
        print_dim "  模型: $emb_model"
        print_dim "  维度: $emb_dim"
        
        echo ""
        print_info "LLM 配置:"
        local llm_status=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('llm', {}).get('status', '未配置'))" 2>/dev/null || echo "未配置")
        local llm_base=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('llm', {}).get('api_base', '未配置'))" 2>/dev/null || echo "未配置")
        local llm_model=$(echo "$config" | python3 -c "import sys,json; print(json.load(sys.stdin).get('llm', {}).get('model', '未配置'))" 2>/dev/null || echo "未配置")
        if [[ "$llm_status" == "已配置" ]]; then
            echo -e "  状态: ${GREEN}$llm_status${NC}"
        else
            echo -e "  状态: ${GRAY}$llm_status${NC}"
        fi
        print_dim "  API 地址: $llm_base"
        print_dim "  模型: $llm_model"
    else
        print_error "获取配置失败"
    fi
    
    echo ""
    read -p "  按 Enter 返回"
}

reset_config() {
    print_title "重置配置"
    
    local config_file="$SCRIPT_DIR/recall_data/config/api_keys.env"
    
    echo ""
    print_info "这将删除当前配置文件并重新生成默认配置"
    read -p "  确认重置？(y/N) " confirm
    
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        print_info "已取消"
        return
    fi
    
    if [[ -f "$config_file" ]]; then
        rm -f "$config_file"
    fi
    
    # 从统一模板重新生成配置文件
    local template_file="$SCRIPT_DIR/recall/config_template.env"
    mkdir -p "$(dirname "$config_file")"
    if [[ -f "$template_file" ]]; then
        cp "$template_file" "$config_file"
        print_success "配置已重置（已从模板重新生成）"
        print_info "配置文件: $config_file"
    else
        print_success "配置已删除"
        print_info "下次启动服务时将自动重新生成"
    fi
}

# ==================== 菜单循环 ====================

run_st_menu() {
    while true; do
        show_banner
        show_st_menu
        
        read -p "  请选择: " choice
        
        case $choice in
            1) install_st_plugin; read -p "  按 Enter 继续" ;;
            2) uninstall_st_plugin; read -p "  按 Enter 继续" ;;
            3) update_st_plugin; read -p "  按 Enter 继续" ;;
            4) set_st_path; read -p "  按 Enter 继续" ;;
            5) check_st_plugin_status ;;
            0) return ;;
            *) print_error "无效选择" ;;
        esac
    done
}

run_config_menu() {
    while true; do
        show_banner
        show_config_menu
        
        read -p "  请选择: " choice
        
        case $choice in
            1) edit_config; read -p "  按 Enter 继续" ;;
            2) reload_config; read -p "  按 Enter 继续" ;;
            3) test_embedding_api ;;
            4) test_llm_api ;;
            5) show_current_config ;;
            6) reset_config; read -p "  按 Enter 继续" ;;
            0) return ;;
            *) print_error "无效选择" ;;
        esac
    done
}

run_main_menu() {
    while true; do
        show_banner
        show_main_menu
        
        read -p "  请选择: " choice
        
        case $choice in
            1) do_install; read -p "  按 Enter 继续" ;;
            2) do_start; read -p "  按 Enter 继续" ;;
            3) do_stop; read -p "  按 Enter 继续" ;;
            4) do_restart; read -p "  按 Enter 继续" ;;
            5) do_status ;;
            6) run_st_menu ;;
            7) run_config_menu ;;
            8) do_clear_data; read -p "  按 Enter 继续" ;;
            0)
                echo ""
                echo -e "  ${CYAN}再见！👋${NC}"
                echo ""
                exit 0
                ;;
            *) print_error "无效选择" ;;
        esac
    done
}

# ==================== 命令行模式 ====================

run_command_line() {
    local action=$1
    
    case $action in
        install) do_install ;;
        start) do_start ;;
        stop) do_stop ;;
        restart) do_restart ;;
        status) do_status ;;
        st-install) install_st_plugin ;;
        st-uninstall) uninstall_st_plugin ;;
        st-update) update_st_plugin ;;
        clear-data) do_clear_data ;;
        *)
            echo ""
            echo -e "${CYAN}Recall-ai 管理工具${NC}"
            echo ""
            echo -e "${WHITE}用法: ./manage.sh [命令]${NC}"
            echo ""
            echo -e "${YELLOW}命令:${NC}"
            echo "  install      安装 Recall-ai"
            echo "  start        启动服务"
            echo "  stop         停止服务"
            echo "  restart      重启服务"
            echo "  status       查看状态"
            echo "  st-install   安装 SillyTavern 插件"
            echo "  st-uninstall 卸载 SillyTavern 插件"
            echo "  st-update    更新 SillyTavern 插件"
            echo "  clear-data   清空所有用户数据（保留配置）"
            echo ""
            echo -e "${GRAY}不带参数运行将启动交互式菜单${NC}"
            echo ""
            ;;
    esac
}

# ==================== 主入口 ====================

if [[ $# -gt 0 ]]; then
    run_command_line "$1"
else
    run_main_menu
fi
