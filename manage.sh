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
# 时态知识图谱配置
# Temporal Knowledge Graph Configuration
# ----------------------------------------------------------------------------
# 是否启用时态知识图谱（追踪事实随时间的变化）
# Enable temporal knowledge graph (track facts over time)
TEMPORAL_GRAPH_ENABLED=true

# 图谱存储后端: file(本地JSON), neo4j, falkordb
# Graph storage backend: file(local JSON), neo4j, falkordb
TEMPORAL_GRAPH_BACKEND=file

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
DEDUP_JACCARD_THRESHOLD=0.7

# 语义相似度高阈值（阶段2，超过此值直接合并）
# Semantic similarity high threshold (Stage 2, auto-merge when exceeded)
DEDUP_SEMANTIC_THRESHOLD=0.85

# 语义相似度低阈值（阶段2，低于此值视为不同）
# Semantic similarity low threshold (Stage 2, considered different when below)
DEDUP_SEMANTIC_LOW_THRESHOLD=0.70

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
ELEVEN_LAYER_RETRIEVER_ENABLED=false

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
RETRIEVAL_L10_CROSS_ENCODER_ENABLED=false

# L11: LLM 过滤（大模型最终确认，消耗 API）
RETRIEVAL_L11_LLM_ENABLED=false

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
EOF
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
        
        # 等待服务启动
        echo -n "  等待服务启动"
        for i in {1..10}; do
            sleep 1
            echo -n "."
            if test_service_running; then
                echo ""
                print_success "服务已启动！"
                print_dim "API 地址: http://127.0.0.1:$DEFAULT_PORT"
                return
            fi
        done
        echo ""
        
        # 检查是否启动失败
        if ! test_service_running; then
            print_error "服务启动失败"
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
        print_success "配置已重置"
        print_info "下次启动服务时将生成默认配置"
    else
        print_info "配置文件不存在"
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
