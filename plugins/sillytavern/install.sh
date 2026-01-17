#!/bin/bash
# 
# Recall AI - SillyTavern 插件安装脚本 (Linux/Mac)
# 
# 使用方法: chmod +x install.sh && ./install.sh
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "========================================"
echo "   Recall - SillyTavern 插件安装       "
echo "========================================"
echo ""

# 常见路径
COMMON_PATHS=(
    "$HOME/SillyTavern"
    "$HOME/Documents/SillyTavern"
    "$HOME/Desktop/SillyTavern"
    "/opt/SillyTavern"
    "/home/ProgramFiles/SillyTavern"
)

# 尝试自动检测
DETECTED_PATH=""
for path in "${COMMON_PATHS[@]}"; do
    # 优先检测新版 SillyTavern (1.12+)
    if [ -d "$path/data/default-user/extensions" ]; then
        DETECTED_PATH="$path"
        break
    fi
    # 其次检测旧版 SillyTavern
    if [ -d "$path/public/scripts/extensions" ]; then
        DETECTED_PATH="$path"
        break
    fi
done

echo "请输入你的 SillyTavern 安装路径"
if [ -n "$DETECTED_PATH" ]; then
    echo "检测到可能的路径: $DETECTED_PATH"
    echo "直接按 Enter 使用检测到的路径，或输入其他路径:"
else
    echo "例如: ~/SillyTavern 或 /opt/SillyTavern"
fi
echo ""

read -p "SillyTavern 路径: " INPUT_PATH

if [ -z "$INPUT_PATH" ]; then
    if [ -n "$DETECTED_PATH" ]; then
        ST_PATH="$DETECTED_PATH"
    else
        echo "错误: 请输入有效路径"
        exit 1
    fi
else
    # 展开 ~
    ST_PATH="${INPUT_PATH/#\~/$HOME}"
fi

# 验证路径并确定扩展目录
if [ -d "$ST_PATH/data/default-user/extensions" ]; then
    # 新版 SillyTavern (1.12+) - 直接放在 extensions/ 下
    EXTENSIONS_PATH="$ST_PATH/data/default-user/extensions"
    echo "检测到新版 SillyTavern (data/default-user/extensions)"
elif [ -d "$ST_PATH/public/scripts/extensions/third-party" ]; then
    # 旧版 SillyTavern - 放在 third-party/ 下
    EXTENSIONS_PATH="$ST_PATH/public/scripts/extensions/third-party"
    echo "检测到旧版 SillyTavern (public/scripts/extensions/third-party)"
elif [ -d "$ST_PATH/public/scripts/extensions" ]; then
    # 旧版但没有 third-party 目录
    EXTENSIONS_PATH="$ST_PATH/public/scripts/extensions/third-party"
    echo "检测到旧版 SillyTavern，创建 third-party 目录"
    mkdir -p "$EXTENSIONS_PATH"
else
    echo ""
    echo "错误: 这不是有效的 SillyTavern 目录"
    echo "请确认路径是 SillyTavern 的根目录"
    exit 1
fi

# 目标路径
TARGET_PATH="$EXTENSIONS_PATH/recall-memory"

echo ""
echo "安装中..."

# 如果已存在，先删除
if [ -d "$TARGET_PATH" ]; then
    echo "  发现旧版本，正在更新..."
    rm -rf "$TARGET_PATH"
fi

# 复制插件文件
mkdir -p "$TARGET_PATH"
cp "$SCRIPT_DIR/manifest.json" "$TARGET_PATH/"
cp "$SCRIPT_DIR/index.js" "$TARGET_PATH/"
cp "$SCRIPT_DIR/style.css" "$TARGET_PATH/"
cp -r "$SCRIPT_DIR/i18n" "$TARGET_PATH/"

echo ""
echo "========================================"
echo "           安装成功！                  "
echo "========================================"
echo ""
echo "插件已安装到:"
echo "  $TARGET_PATH"
echo ""
echo "下一步:"
echo "  1. 重启 SillyTavern"
echo "  2. 确保 Recall 服务已启动 (运行 ./start.sh)"
echo "  3. 在 SillyTavern 扩展面板启用 Recall Memory"
echo ""
echo "默认 API 地址: http://127.0.0.1:18888"
echo ""
