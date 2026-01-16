#!/bin/bash
# 
# Recall AI - Linux/Mac 一键安装脚本
# 
# 使用方法: chmod +x install.sh && ./install.sh
#

set -e

echo ""
echo "========================================"
echo "       Recall AI v3.0.0 安装程序       "
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python
echo "[1/4] 检查 Python 环境..."

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
    echo "错误: 未找到 Python 3.10+ 请先安装 Python"
    echo "Ubuntu/Debian: sudo apt install python3"
    echo "Mac: brew install python3"
    exit 1
fi

echo "  找到 $($PYTHON_CMD --version)"

# 创建虚拟环境
echo ""
echo "[2/4] 创建虚拟环境..."

VENV_PATH="$SCRIPT_DIR/recall-env"

if [ -d "$VENV_PATH" ]; then
    echo "  虚拟环境已存在，跳过创建"
else
    echo "  创建中，请稍候..."
    $PYTHON_CMD -m venv "$VENV_PATH"
    echo "  虚拟环境创建成功"
fi

# 安装依赖
echo ""
echo "[3/4] 安装依赖（可能需要几分钟）..."

source "$VENV_PATH/bin/activate"

pip install --upgrade pip -q 2>/dev/null
pip install -e "$SCRIPT_DIR" -q

echo "  依赖安装完成"

# 初始化
echo ""
echo "[4/4] 初始化 Recall..."

recall init --lightweight 2>/dev/null || true

echo "  初始化完成"

# 完成
echo ""
echo "========================================"
echo "           安装成功！                  "
echo "========================================"
echo ""
echo "启动方式:"
echo "  ./start.sh"
echo ""
echo "安装 SillyTavern 插件:"
echo "  cd plugins/sillytavern && ./install.sh"
echo ""
