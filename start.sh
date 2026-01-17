#!/bin/bash
# 
# Recall AI - Linux/Mac 一键启动脚本
# 
# 使用方法: 
#   前台运行: ./start.sh
#   后台运行: ./start.sh --daemon
#   停止服务: ./start.sh --stop
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/recall.pid"
LOG_FILE="$SCRIPT_DIR/recall.log"

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

# 停止服务
if [ "$1" == "--stop" ]; then
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "停止 Recall 服务 (PID: $PID)..."
            kill "$PID"
            rm -f "$PID_FILE"
            echo "已停止"
        else
            echo "服务未运行"
            rm -f "$PID_FILE"
        fi
    else
        echo "服务未运行"
    fi
    exit 0
fi

# 检查是否已运行
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Recall 服务已在运行 (PID: $PID)"
        echo "使用 ./start.sh --stop 停止服务"
        exit 1
    fi
fi

source "$VENV_PATH/bin/activate"

HOST="${RECALL_HOST:-0.0.0.0}"
PORT="${RECALL_PORT:-18888}"

echo "API 地址: http://$HOST:$PORT"
echo "API 文档: http://$HOST:$PORT/docs"
echo ""

# 后台运行
if [ "$1" == "--daemon" ] || [ "$1" == "-d" ]; then
    echo "后台启动中..."
    nohup recall serve --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "启动成功! PID: $(cat $PID_FILE)"
        echo "日志文件: $LOG_FILE"
        echo "停止命令: ./start.sh --stop"
    else
        echo "启动失败，请查看日志: $LOG_FILE"
        exit 1
    fi
else
    echo "前台运行模式，按 Ctrl+C 停止服务"
    echo ""
    recall serve --host "$HOST" --port "$PORT"
fi
