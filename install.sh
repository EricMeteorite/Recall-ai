#!/bin/bash
# 
# Recall AI - Linux/Mac 安装脚本 v2.0
# 
# 功能：
# - 可视化进度显示
# - 支持国内镜像加速
# - 安装失败自动清理
# - 支持重装、修复
#

set -e

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# ==================== 全局变量 ====================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$SCRIPT_DIR/recall-env"
DATA_PATH="$SCRIPT_DIR/recall_data"
PIP_MIRROR=""
INSTALL_SUCCESS=false
INSTALL_MODE="full"  # lightweight, hybrid, full

# ==================== 工具函数 ====================

print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}       ${BOLD}Recall AI v3.0.0 安装程序${NC}           ${CYAN}║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[$1/$2]${NC} ${BOLD}$3${NC}"
}

print_success() {
    echo -e "    ${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "    ${RED}✗${NC} $1"
}

print_warning() {
    echo -e "    ${YELLOW}!${NC} $1"
}

print_info() {
    echo -e "    ${CYAN}→${NC} $1"
}

# 清理函数
cleanup() {
    if [ "$INSTALL_SUCCESS" = false ] && [ "$CLEANUP_ON_FAIL" = true ]; then
        echo ""
        print_error "安装失败，正在清理..."
        
        if [ -d "$VENV_PATH" ] && [ "$VENV_CREATED" = true ]; then
            rm -rf "$VENV_PATH"
            print_info "已删除虚拟环境"
        fi
        
        echo ""
        echo -e "${YELLOW}请检查以下常见问题：${NC}"
        echo "  1. 网络连接是否正常"
        echo "  2. 磁盘空间是否充足 (需要约 2GB)"
        echo "  3. Python 版本是否 >= 3.10"
        echo ""
        echo -e "重试安装: ${CYAN}./install.sh${NC}"
        echo -e "使用国内镜像: ${CYAN}./install.sh --mirror${NC}"
    fi
}

CLEANUP_ON_FAIL=false
VENV_CREATED=false
trap cleanup EXIT

# ==================== 菜单函数 ====================

show_mode_selection() {
    echo ""
    echo -e "${BOLD}请选择安装模式：${NC}"
    echo ""
    echo -e "  1) ${GREEN}轻量模式${NC}     ~100MB 内存，仅关键词搜索"
    echo -e "     ${CYAN}适合: 内存 < 1GB 的服务器${NC}"
    echo ""
    echo -e "  2) ${GREEN}Hybrid模式${NC}   ~150MB 内存，使用云端API进行向量搜索 ${YELLOW}★推荐★${NC}"
    echo -e "     ${CYAN}适合: 任何服务器，全功能，需要API Key${NC}"
    echo ""
    echo -e "  3) ${GREEN}完整模式${NC}     ~1.5GB 内存，本地向量模型"
    echo -e "     ${CYAN}适合: 高配服务器，完全离线${NC}"
    echo ""
    read -p "请选择 [1-3，默认2]: " mode_choice
    
    case "${mode_choice:-2}" in
        1) INSTALL_MODE="lightweight" ;;
        2) INSTALL_MODE="hybrid" ;;
        3) INSTALL_MODE="full" ;;
        *) echo -e "${YELLOW}使用默认 Hybrid 模式${NC}"; INSTALL_MODE="hybrid" ;;
    esac
    
    echo ""
    echo -e "已选择: ${GREEN}$INSTALL_MODE${NC} 模式"
    echo ""
}

show_menu() {
    echo -e "${BOLD}请选择操作：${NC}"
    echo ""
    echo -e "  1) 全新安装"
    echo -e "  2) 全新安装 (使用国内镜像加速) ${GREEN}推荐${NC}"
    echo -e "  3) 修复/重装依赖"
    echo -e "  4) 完全卸载"
    echo -e "  5) 查看状态"
    echo -e "  6) 退出"
    echo ""
    read -p "请输入选项 [1-6]: " choice
    
    case $choice in
        1) show_mode_selection; CLEANUP_ON_FAIL=true; do_install ;;
        2) show_mode_selection; PIP_MIRROR="-i https://pypi.tuna.tsinghua.edu.cn/simple"; CLEANUP_ON_FAIL=true; do_install ;;
        3) do_repair ;;
        4) do_uninstall ;;
        5) show_install_status ;;
        6) exit 0 ;;
        *) echo -e "${RED}无效选项${NC}"; echo ""; show_menu ;;
    esac
}

# ==================== 权限修复 ====================

fix_permissions() {
    local CURRENT_USER=$(whoami)
    local DIR_OWNER=$(stat -c '%U' "$SCRIPT_DIR" 2>/dev/null || stat -f '%Su' "$SCRIPT_DIR" 2>/dev/null)
    
    if [ "$CURRENT_USER" != "root" ] && [ "$DIR_OWNER" = "root" ]; then
        print_warning "检测到目录属于 root，当前用户是 $CURRENT_USER"
        print_info "需要修改权限..."
        
        if command -v sudo &> /dev/null; then
            sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$SCRIPT_DIR"
            print_success "权限修复成功"
        else
            print_error "无法使用 sudo，请手动执行:"
            echo "    sudo chown -R $CURRENT_USER:$CURRENT_USER $SCRIPT_DIR"
            exit 1
        fi
    else
        print_success "权限检查通过"
    fi
}

# ==================== 检查 Python ====================

check_python() {
    print_step 1 5 "检查 Python 环境"
    
    PYTHON_CMD=""
    
    # 尝试 python3
    if command -v python3 &> /dev/null; then
        VER=$(python3 --version 2>&1)
        if [[ $VER =~ Python\ 3\.([0-9]+) ]]; then
            MINOR=${BASH_REMATCH[1]}
            if [ "$MINOR" -ge 10 ]; then
                PYTHON_CMD="python3"
            fi
        fi
    fi
    
    # 尝试 python
    if [ -z "$PYTHON_CMD" ] && command -v python &> /dev/null; then
        VER=$(python --version 2>&1)
        if [[ $VER =~ Python\ 3\.([0-9]+) ]]; then
            MINOR=${BASH_REMATCH[1]}
            if [ "$MINOR" -ge 10 ]; then
                PYTHON_CMD="python"
            fi
        fi
    fi
    
    if [ -z "$PYTHON_CMD" ]; then
        print_error "未找到 Python 3.10+"
        echo ""
        echo -e "  ${YELLOW}请先安装 Python 3.10 或更高版本：${NC}"
        echo "    Ubuntu/Debian: sudo apt install python3 python3-venv"
        echo "    Mac: brew install python3"
        exit 1
    fi
    
    print_success "找到 $($PYTHON_CMD --version)"
    
    # 检查 venv 模块
    if ! $PYTHON_CMD -m venv --help &> /dev/null; then
        print_error "Python venv 模块未安装"
        echo "    Ubuntu/Debian: sudo apt install python3-venv"
        exit 1
    fi
}

# ==================== 创建虚拟环境 ====================

create_venv() {
    print_step 2 5 "创建虚拟环境"
    
    if [ -d "$VENV_PATH" ]; then
        print_warning "虚拟环境已存在"
        read -p "    是否删除并重新创建? [y/N]: " confirm
        if [[ $confirm =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_PATH"
            print_info "已删除旧虚拟环境"
        else
            print_info "使用现有虚拟环境"
            return
        fi
    fi
    
    print_info "创建中..."
    $PYTHON_CMD -m venv "$VENV_PATH"
    VENV_CREATED=true
    print_success "虚拟环境创建成功"
}

# ==================== 安装依赖 ====================

install_deps() {
    print_step 3 5 "安装依赖"
    
    source "$VENV_PATH/bin/activate"
    
    echo ""
    if [ -n "$PIP_MIRROR" ]; then
        echo -e "    ${GREEN}✓ 使用国内镜像加速 (清华源)${NC}"
    else
        echo -e "    ${YELLOW}! 使用默认源，如果较慢可用 --mirror 参数${NC}"
    fi
    
    # 根据模式显示预计大小
    case $INSTALL_MODE in
        lightweight)
            echo -e "    ${CYAN}ℹ 轻量模式：下载约 300MB 依赖${NC}"
            echo -e "    ${CYAN}ℹ 预计需要 3-5 分钟${NC}"
            ;;
        hybrid)
            echo -e "    ${CYAN}ℹ Hybrid模式：下载约 400MB 依赖${NC}"
            echo -e "    ${CYAN}ℹ 预计需要 5-8 分钟${NC}"
            ;;
        full)
            echo -e "    ${CYAN}ℹ 完整模式：下载约 1.5GB 依赖 (包含 PyTorch)${NC}"
            echo -e "    ${CYAN}ℹ 预计需要 10-20 分钟${NC}"
            ;;
    esac
    echo ""
    
    # 升级 pip
    print_info "升级 pip..."
    pip install --upgrade pip $PIP_MIRROR -q 2>&1
    print_success "pip 升级完成"
    
    # 根据模式安装不同依赖
    local EXTRAS=""
    case $INSTALL_MODE in
        lightweight)
            EXTRAS=""
            print_info "安装轻量依赖..."
            ;;
        hybrid)
            EXTRAS="[hybrid]"
            print_info "安装 Hybrid 依赖 (FAISS)..."
            ;;
        full)
            EXTRAS="[full]"
            print_info "安装完整依赖 (sentence-transformers + FAISS)..."
            ;;
    esac
    
    echo ""
    
    # 直接显示 pip 输出，让用户看到进度
    # 使用临时文件保存退出码
    pip install -e "$SCRIPT_DIR$EXTRAS" $PIP_MIRROR 2>&1 | while IFS= read -r line; do
        # 过滤并美化输出
        if [[ $line == *"Collecting"* ]]; then
            pkg=$(echo "$line" | sed 's/Collecting //' | cut -d' ' -f1)
            echo -e "    ${CYAN}📦${NC} 收集: $pkg"
        elif [[ $line == *"Downloading"* ]]; then
            echo -e "    ${CYAN}↓${NC}  下载中..."
        elif [[ $line == *"Installing collected"* ]]; then
            echo -e "    ${CYAN}⚙${NC}  安装中..."
        elif [[ $line == *"Successfully installed"* ]]; then
            echo -e "    ${GREEN}✓${NC}  安装成功"
        elif [[ $line == *"error"* ]] || [[ $line == *"Error"* ]] || [[ $line == *"ERROR"* ]]; then
            echo -e "    ${RED}✗${NC}  $line"
        fi
    done
    
    echo ""
    
    # 验证安装 - 检查 recall 命令是否存在
    if [ -f "$VENV_PATH/bin/recall" ]; then
        # 尝试获取版本，但不因为失败而退出
        local ver=$("$VENV_PATH/bin/recall" --version 2>&1 || echo "已安装")
        print_success "依赖安装完成 ($ver)"
    else
        print_error "依赖安装可能不完整"
        print_info "尝试手动检查: $VENV_PATH/bin/pip list | grep recall"
        
        # 额外检查是否 recall-ai 包存在
        if "$VENV_PATH/bin/pip" show recall-ai &> /dev/null; then
            print_warning "recall-ai 包已安装，但 CLI 可能有问题"
            print_info "继续安装流程..."
        else
            exit 1
        fi
    fi
}

# ==================== 下载模型 ====================

download_models() {
    print_step 4 5 "下载 NLP 模型"
    
    source "$VENV_PATH/bin/activate"
    
    print_info "下载 spaCy 中文模型 (约 50MB)..."
    
    # spacy download 不支持 pip 镜像参数
    if python -m spacy download zh_core_web_sm 2>&1 | tee /dev/stderr | grep -qE "(✔|successfully|already)"; then
        print_success "spaCy 中文模型下载完成"
    else
        print_warning "模型下载可能不完整，但不影响基本功能"
        print_info "可稍后手动下载: python -m spacy download zh_core_web_sm"
    fi
}

# ==================== 初始化 ====================

initialize() {
    print_step 5 5 "初始化 Recall"
    
    source "$VENV_PATH/bin/activate"
    
    print_info "运行初始化..."
    
    # 根据模式初始化
    case $INSTALL_MODE in
        lightweight)
            recall init --lightweight 2>&1 || true
            ;;
        *)
            recall init 2>&1 || true
            ;;
    esac
    
    # 创建数据目录
    mkdir -p "$DATA_PATH"/{data,logs,cache,models,config,temp}
    
    # 保存安装模式
    echo "$INSTALL_MODE" > "$DATA_PATH/config/install_mode"
    
    print_success "初始化完成"
}

# ==================== 安装流程 ====================

do_install() {
    print_header
    
    print_step 0 5 "检查目录权限"
    fix_permissions
    
    check_python
    create_venv
    install_deps
    download_models
    initialize
    
    INSTALL_SUCCESS=true
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}           ${BOLD}🎉 安装成功！${NC}                     ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    
    # 根据模式显示不同提示
    case $INSTALL_MODE in
        lightweight)
            echo -e "  ${BOLD}安装模式:${NC} ${CYAN}轻量模式${NC}"
            echo -e "  ${YELLOW}注意: 轻量模式仅支持关键词搜索，无语义搜索${NC}"
            ;;
        hybrid)
            echo -e "  ${BOLD}安装模式:${NC} ${CYAN}Hybrid模式${NC}"
            echo ""
            echo -e "  ${YELLOW}⚠ 重要: 启动前需要配置 API Key!${NC}"
            echo ""
            echo -e "  支持的 API 提供商:"
            echo -e "    - OpenAI (text-embedding-3-small)"
            echo -e "    - 硅基流动 (BAAI/bge-large-zh-v1.5) ${GREEN}推荐国内用户${NC}"
            echo ""
            echo -e "  配置方式 (二选一):"
            echo -e "    ${CYAN}export OPENAI_API_KEY=sk-xxx${NC}"
            echo -e "    ${CYAN}export SILICONFLOW_API_KEY=sf-xxx${NC}"
            ;;
        full)
            echo -e "  ${BOLD}安装模式:${NC} ${CYAN}完整模式${NC}"
            echo -e "  ${GREEN}✓ 本地模型，无需API Key，完全离线运行${NC}"
            ;;
    esac
    
    echo ""
    echo -e "  ${BOLD}启动服务:${NC}"
    echo -e "    前台运行: ${CYAN}./start.sh${NC}"
    echo -e "    后台运行: ${CYAN}./start.sh --daemon${NC}"
    echo -e "    停止服务: ${CYAN}./start.sh --stop${NC}"
    echo ""
    echo -e "  ${BOLD}安装 SillyTavern 插件:${NC}"
    echo -e "    ${CYAN}cd plugins/sillytavern && ./install.sh${NC}"
    echo ""
}

# ==================== 修复安装 ====================

do_repair() {
    print_header
    echo -e "${YELLOW}🔧 修复/重装依赖${NC}"
    echo ""
    
    if [ ! -d "$VENV_PATH" ]; then
        print_error "虚拟环境不存在，请先完整安装"
        echo ""
        read -p "是否现在安装? [Y/n]: " confirm
        if [[ ! $confirm =~ ^[Nn]$ ]]; then
            do_install
        fi
        return
    fi
    
    source "$VENV_PATH/bin/activate"
    
    echo "选择修复方式:"
    echo "  1) 快速修复 (只更新 recall)"
    echo "  2) 完整重装 (重新安装所有依赖)"
    echo ""
    read -p "请选择 [1/2]: " repair_choice
    
    case $repair_choice in
        1)
            print_info "快速修复中..."
            pip install -e "$SCRIPT_DIR" $PIP_MIRROR --upgrade
            ;;
        2)
            print_info "完整重装中..."
            pip install -e "$SCRIPT_DIR" $PIP_MIRROR --force-reinstall
            python -m spacy download zh_core_web_sm 2>&1 || true
            ;;
        *)
            print_error "无效选项"
            return
            ;;
    esac
    
    INSTALL_SUCCESS=true
    echo ""
    print_success "修复完成！"
}

# ==================== 卸载 ====================

do_uninstall() {
    print_header
    echo -e "${RED}🗑️  完全卸载${NC}"
    echo ""
    
    echo -e "${YELLOW}警告: 这将删除以下内容：${NC}"
    echo "  - 虚拟环境 (recall-env/)"
    echo "  - 所有数据 (recall_data/)"
    echo "  - 临时文件"
    echo ""
    read -p "确定要卸载吗? 输入 'yes' 确认: " confirm
    
    if [ "$confirm" = "yes" ]; then
        if [ -d "$VENV_PATH" ]; then
            print_info "删除虚拟环境..."
            rm -rf "$VENV_PATH"
        fi
        
        if [ -d "$DATA_PATH" ]; then
            print_info "删除数据目录..."
            rm -rf "$DATA_PATH"
        fi
        
        print_info "删除临时文件..."
        rm -f "$SCRIPT_DIR/recall.pid"
        rm -f "$SCRIPT_DIR/recall.log"
        
        INSTALL_SUCCESS=true
        echo ""
        print_success "卸载完成！"
        echo ""
        echo "如需重新安装，运行: ./install.sh"
    else
        print_info "已取消卸载"
    fi
}

# ==================== 状态检查 (安装脚本内) ====================

show_install_status() {
    print_header
    echo -e "${BOLD}📊 系统状态${NC}"
    echo ""
    
    # 虚拟环境
    if [ -d "$VENV_PATH" ]; then
        print_success "虚拟环境: 已安装"
    else
        print_error "虚拟环境: 未安装"
    fi
    
    # Recall 版本
    if [ -f "$VENV_PATH/bin/recall" ]; then
        ver=$("$VENV_PATH/bin/recall" --version 2>&1 || echo "未知")
        print_success "Recall: $ver"
    else
        print_error "Recall: 未安装"
    fi
    
    # 数据目录
    if [ -d "$DATA_PATH" ]; then
        size=$(du -sh "$DATA_PATH" 2>/dev/null | cut -f1)
        print_success "数据目录: $size"
    else
        print_warning "数据目录: 未创建"
    fi
    
    # 服务状态
    if [ -f "$SCRIPT_DIR/recall.pid" ]; then
        pid=$(cat "$SCRIPT_DIR/recall.pid")
        if kill -0 "$pid" 2>/dev/null; then
            print_success "服务状态: 运行中 (PID: $pid)"
        else
            print_warning "服务状态: 已停止 (残留PID文件)"
        fi
    else
        print_info "服务状态: 未运行"
    fi
    
    # API 检查
    if command -v curl &> /dev/null; then
        if curl -s --connect-timeout 2 http://localhost:18888/health &> /dev/null; then
            print_success "API 响应: 正常"
        else
            print_info "API 响应: 无法连接"
        fi
    fi
    
    echo ""
    read -p "按 Enter 返回菜单..." 
    echo ""
    show_menu
}

# ==================== 主入口 ====================

cd "$SCRIPT_DIR"

# 解析命令行参数
case "${1:-}" in
    --mirror|-m)
        PIP_MIRROR="-i https://pypi.tuna.tsinghua.edu.cn/simple"
        CLEANUP_ON_FAIL=true
        do_install
        ;;
    --repair|-r)
        do_repair
        ;;
    --uninstall|-u)
        do_uninstall
        ;;
    --status|-s)
        show_install_status
        ;;
    --help|-h)
        print_header
        echo "用法: ./install.sh [选项]"
        echo ""
        echo "选项:"
        echo "  (无参数)       显示交互式菜单"
        echo "  --mirror, -m   使用国内镜像安装"
        echo "  --repair, -r   修复/重装依赖"
        echo "  --uninstall, -u 完全卸载"
        echo "  --status, -s   查看系统状态"
        echo "  --help, -h     显示帮助"
        echo ""
        ;;
    "")
        # 无参数时显示菜单
        print_header
        show_menu
        ;;
    *)
        echo "未知选项: $1"
        echo "使用 --help 查看帮助"
        exit 1
        ;;
esac
