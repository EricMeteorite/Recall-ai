#!/bin/bash
# 
# Recall AI - Linux/Mac 一键启动脚本
# 
# 使用方法: ./start.sh
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "========================================"
echo "         Recall AI v3.0.0              "
echo "========================================"
echo ""

VENV_PATH="$SCRIPT_DIR/recall-env"

if [ ! -d "$VENV_PATH" ]; then
    echo "错误: 请先运行 ./install.sh 安装"
    exit 1
fi

source "$VENV_PATH/bin/activate"

echo "API 地址: http://127.0.0.1:18888"
echo "API 文档: http://127.0.0.1:18888/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

recall serve
