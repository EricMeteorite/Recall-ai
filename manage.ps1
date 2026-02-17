<#
.SYNOPSIS
    Recall-ai Unified Management Script
.DESCRIPTION
    Integrate installation, startup, SillyTavern plugin management and other operations
.NOTES
    Version: 1.0.0
    Support: Windows PowerShell 5.1+
#>

param(
    [string]$Action = "",
    [string]$STPath = ""
)

# 设置控制台编码为 UTF-8，解决中文乱码问题
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Recall-ai Manager"

# ==================== Configuration ====================
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$CONFIG_FILE = Join-Path $SCRIPT_DIR "recall_data\config\manager.json"
$VERSION = "1.0.0"
$DEFAULT_PORT = 18888

# ==================== Color Output ====================
function Write-Color {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

function Write-Title {
    param([string]$Text)
    Write-Host ""
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "  $("-" * ($Text.Length + 2))" -ForegroundColor DarkCyan
}

function Write-Success { param([string]$Text) Write-Host "  [OK] $Text" -ForegroundColor Green }
function Write-Error2 { param([string]$Text) Write-Host "  [X] $Text" -ForegroundColor Red }
function Write-Warning2 { param([string]$Text) Write-Host "  [!] $Text" -ForegroundColor Yellow }
function Write-Info { param([string]$Text) Write-Host "  [i] $Text" -ForegroundColor Yellow }
function Write-Dim { param([string]$Text) Write-Host "  $Text" -ForegroundColor DarkGray }

# ==================== Banner ====================
function Show-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║                                                            ║" -ForegroundColor Cyan
    Write-Host "  ║              Recall-ai 管理工具  v$VERSION                     ║" -ForegroundColor Cyan
    Write-Host "  ║                                                            ║" -ForegroundColor Cyan
    Write-Host "  ║         智能记忆管理系统 - 让 AI 拥有持久记忆              ║" -ForegroundColor Cyan
    Write-Host "  ╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

# ==================== Config Management ====================
function Get-ManagerConfig {
    if (Test-Path $CONFIG_FILE) {
        try {
            return Get-Content $CONFIG_FILE -Raw | ConvertFrom-Json
        } catch {
            return @{ st_path = "" }
        }
    }
    return @{ st_path = "" }
}

function Save-ManagerConfig {
    param($Config)
    $configDir = Split-Path -Parent $CONFIG_FILE
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }
    $Config | ConvertTo-Json | Set-Content $CONFIG_FILE -Encoding UTF8
}

# ==================== Status Detection ====================
function Test-ServiceRunning {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$DEFAULT_PORT/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-Installed {
    $venvPath = Join-Path $SCRIPT_DIR "recall-env"
    return Test-Path $venvPath
}

function Get-STPluginPath {
    $config = Get-ManagerConfig
    if ($config.st_path) {
        return Join-Path $config.st_path "public\scripts\extensions\third-party\recall-memory"
    }
    return $null
}

function Test-STPluginInstalled {
    $pluginPath = Get-STPluginPath
    if ($pluginPath -and (Test-Path $pluginPath)) {
        return $true
    }
    return $false
}

# ==================== Main Menu ====================
function Show-MainMenu {
    $installed = Test-Installed
    $running = Test-ServiceRunning
    $stInstalled = Test-STPluginInstalled
    
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor DarkGray
    Write-Host "  |  当前状态                                               |" -ForegroundColor DarkGray
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor DarkGray
    
    # Recall-ai status
    $recallStatus = if ($installed) { 
        if ($running) { "✓ 已安装，运行中" } else { "✓ 已安装，未运行" }
    } else { "✗ 未安装" }
    $recallColor = if ($installed -and $running) { "Green" } elseif ($installed) { "Yellow" } else { "Red" }
    Write-Host "  |  Recall-ai:        " -NoNewline -ForegroundColor DarkGray
    Write-Host $recallStatus.PadRight(38) -NoNewline -ForegroundColor $recallColor
    Write-Host "|" -ForegroundColor DarkGray
    
    # SillyTavern plugin status
    $stStatus = if ($stInstalled) { "✓ 已安装" } else { "✗ 未安装" }
    $stColor = if ($stInstalled) { "Green" } else { "DarkGray" }
    Write-Host "  |  SillyTavern 插件:" -NoNewline -ForegroundColor DarkGray
    Write-Host $stStatus.PadRight(38) -NoNewline -ForegroundColor $stColor
    Write-Host "|" -ForegroundColor DarkGray
    
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor DarkGray
    
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor White
    Write-Host "  |                       主菜单                              |" -ForegroundColor White
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [1] 🔧 安装 Recall-ai                                  |" -ForegroundColor White
    Write-Host "  |    [2] 🚀 启动服务                                      |" -ForegroundColor White
    Write-Host "  |    [3] 🛑 停止服务                                       |" -ForegroundColor White
    Write-Host "  |    [4] 🔄 重启服务                                      |" -ForegroundColor White
    Write-Host "  |    [5] 📊 查看状态                                      |" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [6] 📦 SillyTavern 插件管理  →                       |" -ForegroundColor White
    Write-Host "  |    [7] ⚙️  配置管理              →                       |" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [8] 🗑️  清空用户数据（保留配置）                     |" -ForegroundColor Red
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [0] 退出                                               |" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor White
    Write-Host ""
}

# ==================== SillyTavern Plugin Menu ====================
function Show-STMenu {
    $stInstalled = Test-STPluginInstalled
    $config = Get-ManagerConfig
    
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    Write-Host "  |              SillyTavern 插件管理                        |" -ForegroundColor Magenta
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    
    if ($config.st_path) {
        Write-Host "  |  ST 路径: " -NoNewline -ForegroundColor Magenta
        $displayPath = if ($config.st_path.Length -gt 45) { $config.st_path.Substring(0, 42) + "..." } else { $config.st_path }
        Write-Host $displayPath.PadRight(47) -NoNewline -ForegroundColor DarkGray
        Write-Host "|" -ForegroundColor Magenta
    }
    
    $statusText = if ($stInstalled) { "✓ 已安装" } else { "✗ 未安装" }
    $statusColor = if ($stInstalled) { "Green" } else { "Yellow" }
    Write-Host "  |  插件状态: " -NoNewline -ForegroundColor Magenta
    Write-Host $statusText.PadRight(41) -NoNewline -ForegroundColor $statusColor
    Write-Host "|" -ForegroundColor Magenta
    
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  |    [1] 📥 安装插件到 SillyTavern                        |" -ForegroundColor Magenta
    Write-Host "  |    [2] 📤 卸载插件                                      |" -ForegroundColor Magenta
    Write-Host "  |    [3] 🔄 更新插件                                      |" -ForegroundColor Magenta
    Write-Host "  |    [4] 📂 设置 SillyTavern 路径                         |" -ForegroundColor Magenta
    Write-Host "  |    [5] 🔍 检查插件状态                                  |" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  |    [0] ← 返回主菜单                                    |" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    Write-Host ""
}

# ==================== Config Menu ====================
function Show-ConfigMenu {
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |                    配置管理                               |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  |    [1] 📝 编辑 API 配置文件                             |" -ForegroundColor Yellow
    Write-Host "  |    [2] 🔄 热更新配置（无需重启）                        |" -ForegroundColor Yellow
    Write-Host "  |    [3] 🧪 测试 Embedding API 连接                       |" -ForegroundColor Yellow
    Write-Host "  |    [4] 🤖 测试 LLM API 连接                             |" -ForegroundColor Yellow
    Write-Host "  |    [5] 📋 查看当前配置                                  |" -ForegroundColor Yellow
    Write-Host "  |    [6] 🗑️  重置配置为默认值                             |" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  |    [0] ← 返回主菜单                                    |" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""
}

# ==================== Operation Functions ====================

function Do-Install {
    Write-Title "安装 Recall-ai"
    
    if (Test-Installed) {
        Write-Info "Recall-ai 已安装"
        $choice = Read-Host "  是否重新安装？(y/N)"
        if ($choice -ne "y" -and $choice -ne "Y") {
            return
        }
    }
    
    $installScript = Join-Path $SCRIPT_DIR "install.ps1"
    if (Test-Path $installScript) {
        Write-Info "正在执行安装脚本..."
        & $installScript
    } else {
        Write-Error2 "找不到安装脚本: $installScript"
    }
}

function Do-Start {
    Write-Title "启动服务"
    
    if (-not (Test-Installed)) {
        Write-Error2 "Recall-ai 未安装，请先安装"
        return
    }
    
    if (Test-ServiceRunning) {
        Write-Info "服务已在运行中"
        return
    }
    
    # Check config file
    $configFile = Join-Path $SCRIPT_DIR "recall_data\config\api_keys.env"
    $modeFile = Join-Path $SCRIPT_DIR "recall_data\config\install_mode"
    $installMode = "local"
    
    if (Test-Path $modeFile) {
        $installMode = Get-Content $modeFile -ErrorAction SilentlyContinue
    }
    
    # If cloud/hybrid mode, check API config
    if ($installMode -in "cloud", "hybrid") {
        $needConfig = $false
        
        if (-not (Test-Path $configFile)) {
            $needConfig = $true
        } else {
            # Check if API Key is configured
            $content = Get-Content $configFile -Raw -ErrorAction SilentlyContinue
            if ($content -match "EMBEDDING_API_KEY=(.*)") {
                $apiKey = $matches[1].Trim()
                if ([string]::IsNullOrEmpty($apiKey) -or $apiKey.StartsWith("your_")) {
                    $needConfig = $true
                }
            } else {
                $needConfig = $true
            }
        }
        
        if ($needConfig) {
            # Ensure config file exists
            if (-not (Test-Path $configFile)) {
                $configDir = Split-Path $configFile -Parent
                if (-not (Test-Path $configDir)) {
                    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
                }
                $defaultConfig = @'
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

# LLM 请求超时时间（秒），复杂请求（如大量实体关系提取）可能需要更长时间
# LLM request timeout (seconds), complex requests may need more time
LLM_TIMEOUT=60

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
FORESHADOWING_LLM_ENABLED=true

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
# ----------------------------------------------------------------------------
# 统一知识图谱配置 (v4.0 统一架构)
# Unified Knowledge Graph Configuration (v4.0 Unified Architecture)
# ----------------------------------------------------------------------------
# 注意：v4.0 后图谱始终启用，此开关仅控制时态增强功能（衰减、历史限制等）
# Note: Graph is always enabled in v4.0, this switch only controls temporal enhancements
TEMPORAL_GRAPH_ENABLED=true

# 图谱存储后端: file(本地JSON文件), kuzu(嵌入式图数据库)
# Graph storage backend: file(local JSON), kuzu(embedded graph database)
# 此配置控制所有图数据的存储位置（包括实体关系）
# This setting controls storage for ALL graph data (including entity relations)
# Kuzu 提供更高的查询性能（需要 pip install kuzu）
TEMPORAL_GRAPH_BACKEND=file

# Kuzu 缓冲池大小（MB），仅当 TEMPORAL_GRAPH_BACKEND=kuzu 时生效
# Kuzu buffer pool size in MB, only used when backend is kuzu
KUZU_BUFFER_POOL_SIZE=256

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
# 注意：0.85较保守，避免误判不同内容为重复
DEDUP_JACCARD_THRESHOLD=0.85

# 语义相似度高阈值（阶段2，超过此值直接合并）
# Semantic similarity high threshold (Stage 2, auto-merge when exceeded)
DEDUP_SEMANTIC_THRESHOLD=0.90

# 语义相似度低阈值（阶段2，低于此值视为不同）
# Semantic similarity low threshold (Stage 2, considered different when below)
DEDUP_SEMANTIC_LOW_THRESHOLD=0.80

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
ELEVEN_LAYER_RETRIEVER_ENABLED=true

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
RETRIEVAL_L10_CROSS_ENCODER_ENABLED=true

# L11: LLM 过滤（大模型最终确认，消耗 API）
RETRIEVAL_L11_LLM_ENABLED=true

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

# ============================================================================
# v4.0 Phase 3.5 企业级性能配置
# v4.0 Phase 3.5 Enterprise Performance Configuration
# ============================================================================

# ----------------------------------------------------------------------------
# 图查询规划器配置 (QueryPlanner)
# Query Planner Configuration
# ----------------------------------------------------------------------------
# 是否启用图查询规划器（优化多跳图查询）
# Enable query planner (optimizes multi-hop graph queries)
QUERY_PLANNER_ENABLED=true

# 路径缓存大小（条）
# Path cache size (entries)
QUERY_PLANNER_CACHE_SIZE=1000

# 缓存过期时间（秒）
# Cache TTL (seconds)
QUERY_PLANNER_CACHE_TTL=300

# ----------------------------------------------------------------------------
# 社区检测配置 (CommunityDetector)
# Community Detection Configuration
# ----------------------------------------------------------------------------
# 是否启用社区检测（发现实体群组）
# Enable community detection (discover entity clusters)
COMMUNITY_DETECTION_ENABLED=false

# 检测算法: louvain | label_propagation | connected
# Detection algorithm
COMMUNITY_DETECTION_ALGORITHM=louvain

# 最小社区大小
# Minimum community size
COMMUNITY_MIN_SIZE=2

# ============================================================================
# v4.0 Phase 3.6 三路并行召回配置 (100% 不遗忘保证)
# v4.0 Phase 3.6 Triple Recall Configuration (100% Memory Guarantee)
# ============================================================================

# ----------------------------------------------------------------------------
# 主开关
# Master Switch
# ----------------------------------------------------------------------------
# 是否启用三路并行召回（IVF-HNSW + 倒排 + 实体，RRF融合）
# Enable triple parallel recall (IVF-HNSW + Inverted + Entity, RRF fusion)
TRIPLE_RECALL_ENABLED=true

# ----------------------------------------------------------------------------
# RRF 融合配置
# RRF (Reciprocal Rank Fusion) Configuration
# ----------------------------------------------------------------------------
# RRF 常数 k（推荐 60，越大排名差异越平滑）
# RRF constant k (recommend 60, higher = smoother rank differences)
TRIPLE_RECALL_RRF_K=60

# 语义召回权重（路径1: IVF-HNSW）
# Semantic recall weight (Path 1: IVF-HNSW)
TRIPLE_RECALL_VECTOR_WEIGHT=1.0

# 关键词召回权重（路径2: 倒排索引，100%召回）
# Keyword recall weight (Path 2: Inverted index, 100% recall)
TRIPLE_RECALL_KEYWORD_WEIGHT=1.2

# 实体召回权重（路径3: 实体索引，100%召回）
# Entity recall weight (Path 3: Entity index, 100% recall)
TRIPLE_RECALL_ENTITY_WEIGHT=1.0

# ----------------------------------------------------------------------------
# IVF-HNSW 参数 (提升召回率至 95-99%)
# IVF-HNSW Parameters (Improve recall to 95-99%)
# ----------------------------------------------------------------------------
# HNSW 图连接数（越大召回越高，内存越大，推荐 32）
# HNSW M parameter (higher = better recall, more memory, recommend 32)
VECTOR_IVF_HNSW_M=32

# HNSW 构建精度（越大索引质量越高，构建越慢，推荐 200）
# HNSW efConstruction (higher = better index quality, slower build, recommend 200)
VECTOR_IVF_HNSW_EF_CONSTRUCTION=200

# HNSW 搜索精度（越大召回越高，搜索越慢，推荐 64）
# HNSW efSearch (higher = better recall, slower search, recommend 64)
VECTOR_IVF_HNSW_EF_SEARCH=64

# ----------------------------------------------------------------------------
# 原文兜底配置 (100% 保证)
# Raw Text Fallback Configuration (100% Guarantee)
# ----------------------------------------------------------------------------
# 是否启用原文兜底（仅在融合结果为空时触发）
# Enable raw text fallback (only when fusion results are empty)
FALLBACK_ENABLED=true

# 是否启用并行兜底扫描（提升大规模数据的兜底速度）
# Enable parallel fallback scan (improve speed for large data)
FALLBACK_PARALLEL=true

# 并行扫描线程数（推荐 4）
# Parallel scan workers (recommend 4)
FALLBACK_WORKERS=4

# 兜底最大结果数
# Max fallback results
FALLBACK_MAX_RESULTS=50

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  v4.1 增强功能配置 - RECALL 4.1 ENHANCED FEATURES                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ----------------------------------------------------------------------------
# LLM 关系提取配置
# LLM Relation Extraction Configuration
# ----------------------------------------------------------------------------
# 模式: rules（纯规则，默认）/ adaptive（自适应）/ llm（纯LLM）
# Mode: rules (pure rules, default) / adaptive / llm
LLM_RELATION_MODE=llm

# 自适应模式下触发 LLM 的复杂度阈值 (0.0-1.0)
# Complexity threshold to trigger LLM in adaptive mode
LLM_RELATION_COMPLEXITY_THRESHOLD=0.5

# 是否提取时态信息
# Enable temporal information extraction
LLM_RELATION_ENABLE_TEMPORAL=true

# 是否生成事实描述
# Enable fact description generation
LLM_RELATION_ENABLE_FACT_DESCRIPTION=true

# ----------------------------------------------------------------------------
# 实体摘要配置
# Entity Summary Configuration
# ----------------------------------------------------------------------------
# 是否启用实体摘要生成
# Enable entity summary generation
ENTITY_SUMMARY_ENABLED=true

# 触发 LLM 摘要的最小事实数
# Minimum facts to trigger LLM summary
ENTITY_SUMMARY_MIN_FACTS=5

# ----------------------------------------------------------------------------
# Episode 追溯配置
# Episode Tracking Configuration
# ----------------------------------------------------------------------------
# 是否启用 Episode 追溯
# Enable episode tracking
EPISODE_TRACKING_ENABLED=true

# ----------------------------------------------------------------------------
# LLM Max Tokens 配置
# LLM Max Tokens Configuration
# ----------------------------------------------------------------------------
# LLM 默认最大输出 tokens（通用默认值）
# Default max tokens for LLM output
LLM_DEFAULT_MAX_TOKENS=2000

# 关系提取最大 tokens（实体多时需要大值）
# Max tokens for relation extraction (need larger value for many entities)
LLM_RELATION_MAX_TOKENS=4000

# 伏笔分析最大 tokens
# Max tokens for foreshadowing analysis
FORESHADOWING_MAX_TOKENS=2000

# 条件提取最大 tokens
# Max tokens for context extraction
CONTEXT_EXTRACTION_MAX_TOKENS=2000

# 实体摘要最大 tokens
# Max tokens for entity summary
ENTITY_SUMMARY_MAX_TOKENS=2000

# 智能抽取最大 tokens
# Max tokens for smart extractor
SMART_EXTRACTOR_MAX_TOKENS=2000

# 矛盾检测最大 tokens
# Max tokens for contradiction detection
CONTRADICTION_MAX_TOKENS=1000

# 上下文构建最大 tokens
# Max tokens for context building
BUILD_CONTEXT_MAX_TOKENS=4000

# 检索 LLM 过滤最大 tokens（只需 yes/no，较小即可）
# Max tokens for retrieval LLM filter (only yes/no, keep small)
RETRIEVAL_LLM_MAX_TOKENS=200

# 去重 LLM 确认最大 tokens（只需 yes/no，较小即可）
# Max tokens for dedup LLM confirmation (only yes/no, keep small)
DEDUP_LLM_MAX_TOKENS=100

# ============================================================================
# v4.2 性能优化配置
# v4.2 Performance Optimization Configuration
# ============================================================================

# Embedding 复用开关（节省2-4秒/轮次）
# Enable embedding reuse (saves 2-4s per turn)
EMBEDDING_REUSE_ENABLED=true

# 统一分析器开关（合并矛盾检测+关系提取，节省15-25秒/轮次）
# Enable unified analyzer (combines contradiction + relation, saves 15-25s per turn)
UNIFIED_ANALYZER_ENABLED=true

# 统一分析器 LLM 最大输出 tokens
# Max tokens for unified analyzer LLM response
UNIFIED_ANALYSIS_MAX_TOKENS=4000

# Turn API 开关（/v1/memories/turn 端点）
# Enable Turn API endpoint (/v1/memories/turn)
TURN_API_ENABLED=true

# ============================================================================
# v5.0 全局模式配置 - RECALL 5.0 MODE CONFIGURATION
# ============================================================================

# ----------------------------------------------------------------------------
# 全局模式开关 / Global Mode Switch
# ----------------------------------------------------------------------------
# 模式: roleplay（角色扮演，默认）/ general（通用）/ knowledge_base（知识库）
# Mode: roleplay (default) / general / knowledge_base
RECALL_MODE=roleplay

# ----------------------------------------------------------------------------
# 模式子开关（自动由 RECALL_MODE 推导，也可手动覆盖）
# Mode Sub-switches (auto-derived from RECALL_MODE, can be overridden)
# ----------------------------------------------------------------------------
# 伏笔系统开关 / Foreshadowing system (roleplay=true, others=false)
FORESHADOWING_ENABLED=true
# 角色维度隔离 / Character dimension isolation (roleplay=true, others=false)
CHARACTER_DIMENSION_ENABLED=true
# RP 一致性检查 / RP consistency check (roleplay=true, others=false)
RP_CONSISTENCY_ENABLED=true
# RP 关系类型 / RP relation types (roleplay=true, others=false)
RP_RELATION_TYPES=true
# RP 上下文类型 / RP context types (roleplay=true, others=false)
RP_CONTEXT_TYPES=true

# ============================================================================
# v5.0 重排序器配置 - RECALL 5.0 RERANKER CONFIGURATION
# ============================================================================
# 重排序后端: builtin（内置）/ cohere / cross-encoder
# Reranker backend: builtin (default) / cohere / cross-encoder
RERANKER_BACKEND=builtin
# Cohere API 密钥（仅 cohere 后端需要）/ Cohere API key (cohere backend only)
COHERE_API_KEY=
# 自定义重排序模型名 / Custom reranker model name
RERANKER_MODEL=
'@
                Set-Content -Path $configFile -Value $defaultConfig -Encoding UTF8
            Write-Info "已创建配置文件: $configFile"
            }
            
            Write-Host ""
            Write-Warning2 "Cloud 模式需要配置 Embedding API"
            Write-Host ""
            Write-Info "请编辑配置文件:"
            Write-Dim "  $configFile"
            Write-Host ""
            Write-Info "配置完成后，再次启动服务"
            return
        }
    }
    
    $startScript = Join-Path $SCRIPT_DIR "start.ps1"
    $startLog = Join-Path $SCRIPT_DIR "recall_data\logs\start.log"
    
    if (Test-Path $startScript) {
        Write-Info "正在启动服务..."
        
        # Ensure log directory exists
        $logDir = Split-Path $startLog -Parent
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        
        # Start in background with log
        $errorLog = Join-Path $SCRIPT_DIR "recall_data\logs\start_error.log"
        Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startScript -WorkingDirectory $SCRIPT_DIR -RedirectStandardOutput $startLog -RedirectStandardError $errorLog -WindowStyle Hidden
        
        # Wait for service to start (up to 60 seconds, model loading can be slow)
        Write-Host "  等待服务启动" -NoNewline
        $maxWait = 60
        $waited = 0
        while ($waited -lt $maxWait) {
            Start-Sleep -Seconds 2
            $waited += 2
            Write-Host "." -NoNewline
            if (Test-ServiceRunning) {
                Write-Host ""
                Write-Success "服务已启动！(${waited}秒)"
                Write-Dim "API 地址: http://127.0.0.1:$DEFAULT_PORT"
                return
            }
            # Check if process is still running
            $proc = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*recall*" }
            if (-not $proc) {
                $proc = Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue
            }
        }
        Write-Host ""
        
        # Check if start failed
        if (-not (Test-ServiceRunning)) {
            Write-Error2 "服务启动超时或失败"
            Write-Host ""
            Write-Info "启动日志:"
            if (Test-Path $startLog) {
                Get-Content $startLog -Tail 20 | ForEach-Object { Write-Dim "  $_" }
            }
            Write-Host ""
            Write-Dim "完整日志: $startLog"
        }
    } else {
        Write-Error2 "找不到启动脚本: $startScript"
    }
}

function Do-Stop {
    Write-Title "停止服务"
    
    if (-not (Test-ServiceRunning)) {
        Write-Info "服务未运行"
        return
    }
    
    Write-Info "正在停止服务..."
    
    # Find and terminate uvicorn process
    $processes = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*recall*" -or $_.CommandLine -like "*recall.server*"
    }
    
    if ($processes) {
        $processes | Stop-Process -Force
        Write-Success "服务已停止"
    } else {
        # Try to find by port
        $netstat = netstat -ano | Select-String ":$DEFAULT_PORT.*LISTENING"
        if ($netstat) {
            $processId = ($netstat -split '\s+')[-1]
            if ($processId -and $processId -ne "0") {
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                Write-Success "服务已停止"
                return
            }
        }
        Write-Info "未找到运行中的服务进程"
    }
}

function Do-Restart {
    Write-Title "重启服务"
    Do-Stop
    Start-Sleep -Seconds 2
    Do-Start
}

function Do-Status {
    Write-Title "服务状态"
    
    $installed = Test-Installed
    $running = Test-ServiceRunning
    
    Write-Host ""
    if ($installed) {
        Write-Success "Recall-ai 已安装"
        
        # Get version info
        try {
            $venvPython = Join-Path $SCRIPT_DIR "recall-env\Scripts\python.exe"
            $version = & $venvPython -c "from recall.version import __version__; print(__version__)" 2>$null
            if ($version) {
                Write-Dim "版本: v$version"
            }
        } catch {}
    } else {
        Write-Error2 "Recall-ai 未安装"
    }
    
    Write-Host ""
    if ($running) {
        Write-Success "服务运行中"
        Write-Dim "API 地址: http://127.0.0.1:$DEFAULT_PORT"
        
        # Get statistics
        try {
            $stats = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/stats" -TimeoutSec 5
            Write-Dim "记忆总数: $($stats.total_memories)"
            $mode = if ($stats.lite -or $stats.lightweight) { "Lite 模式" } else { "Local 模式" }
            Write-Dim "Embedding 模式: $mode"
        } catch {}
    } else {
        Write-Error2 "服务未运行"
    }
    
    Write-Host ""
    $stInstalled = Test-STPluginInstalled
    if ($stInstalled) {
        Write-Success "SillyTavern 插件已安装"
        $pluginPath = Get-STPluginPath
        Write-Dim "路径: $pluginPath"
    } else {
        Write-Info "SillyTavern 插件未安装"
    }
    
    Write-Host ""
    Read-Host "  按回车继续"
}

# ==================== Clear User Data ====================

function Do-ClearData {
    Write-Title "清空用户数据"
    
    $dataPath = Join-Path $SCRIPT_DIR "recall_data"
    
    if (-not (Test-Path $dataPath)) {
        Write-Info "没有数据目录，无需清理"
        return
    }
    
    # Check if service is running
    if (Test-ServiceRunning) {
        Write-Error2 "服务正在运行中，请先停止服务"
        Write-Host ""
        Write-Host "  运行: " -NoNewline
        Write-Host ".\manage.ps1 stop" -ForegroundColor Cyan
        Write-Host "  或在菜单中选择 [3] 停止服务" -ForegroundColor DarkGray
        return
    }
    
    # Show what will be deleted
    Write-Host ""
    Write-Host "  以下数据将被删除:" -ForegroundColor Yellow
    Write-Host ""
    
    # Check each directory/file
    $dataDir = Join-Path $dataPath "data"
    $cacheDir = Join-Path $dataPath "cache"
    $logsDir = Join-Path $dataPath "logs"
    $tempDir = Join-Path $dataPath "temp"
    $indexDir = Join-Path $dataPath "index"        # ngram, fulltext indexes
    $indexesDir = Join-Path $dataPath "indexes"     # legacy indexes
    $l1Dir = Join-Path $dataPath "L1_consolidated"
    $kgFile = Join-Path $dataPath "knowledge_graph.json"
    $kgFileInData = Join-Path (Join-Path $dataPath "data") "knowledge_graph.json"
    
    $toDelete = @()
    
    if (Test-Path $dataDir) {
        $size = (Get-ChildItem $dataDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] data/           - 所有用户记忆 ($sizeStr)" -ForegroundColor Red
        $toDelete += $dataDir
    }
    
    if (Test-Path $indexDir) {
        $size = (Get-ChildItem $indexDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] index/          - N-gram 和全文索引 ($sizeStr)" -ForegroundColor Red
        $toDelete += $indexDir
    }
    
    if (Test-Path $indexesDir) {
        $size = (Get-ChildItem $indexesDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] indexes/        - 实体和向量索引 ($sizeStr)" -ForegroundColor Red
        $toDelete += $indexesDir
    }
    
    if (Test-Path $l1Dir) {
        $size = (Get-ChildItem $l1Dir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] L1_consolidated/ - 长期记忆 ($sizeStr)" -ForegroundColor Red
        $toDelete += $l1Dir
    }
    
    # Check knowledge_graph.json in both root and data/ directory
    if (Test-Path $kgFile) {
        $size = (Get-Item $kgFile -ErrorAction SilentlyContinue).Length
        $sizeStr = if ($size) { "{0:N2} KB" -f ($size / 1KB) } else { "0 KB" }
        Write-Host "    [x] knowledge_graph.json - 知识图谱 ($sizeStr)" -ForegroundColor Red
        $toDelete += $kgFile
    }
    if ((Test-Path $kgFileInData) -and (-not ($toDelete -contains $dataDir))) {
        # Only show if data/ won't be deleted (which would include this file)
        $size = (Get-Item $kgFileInData -ErrorAction SilentlyContinue).Length
        $sizeStr = if ($size) { "{0:N2} KB" -f ($size / 1KB) } else { "0 KB" }
        Write-Host "    [x] data/knowledge_graph.json - 知识图谱 ($sizeStr)" -ForegroundColor Red
        $toDelete += $kgFileInData
    }
    
    if (Test-Path $cacheDir) {
        $size = (Get-ChildItem $cacheDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] cache/          - Embedding 缓存 ($sizeStr)" -ForegroundColor Red
        $toDelete += $cacheDir
    }
    
    if (Test-Path $logsDir) {
        $size = (Get-ChildItem $logsDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] logs/           - 日志文件 ($sizeStr)" -ForegroundColor Red
        $toDelete += $logsDir
    }
    
    if (Test-Path $tempDir) {
        $size = (Get-ChildItem $tempDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] temp/           - 临时文件 ($sizeStr)" -ForegroundColor Red
        $toDelete += $tempDir
    }
    
    Write-Host ""
    Write-Host "  以下将被保留:" -ForegroundColor Green
    Write-Host "    [✓] config/    - API 密钥、安装模式、配置" -ForegroundColor Green
    Write-Host "    [✓] models/    - 已下载的模型" -ForegroundColor Green
    
    if ($toDelete.Count -eq 0) {
        Write-Host ""
        Write-Info "没有数据需要清理"
        return
    }
    
    Write-Host ""
    Write-Host "  [!] 警告：此操作不可撤销！" -ForegroundColor Yellow
    Write-Host ""
    
    $confirm = Read-Host "  输入 'yes' 确认删除"
    
    if ($confirm -ne "yes") {
        Write-Host ""
        Write-Info "操作已取消"
        return
    }
    
    Write-Host ""
    Write-Info "正在清空用户数据..."
    
    foreach ($dir in $toDelete) {
        try {
            Remove-Item -Path $dir -Recurse -Force -ErrorAction Stop
            $dirName = Split-Path $dir -Leaf
            Write-Success "已删除: $dirName/"
        } catch {
            Write-Error2 "删除失败: $dir"
        }
    }
    
    # Recreate empty directories
    foreach ($dir in $toDelete) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    
    Write-Host ""
    Write-Success "用户数据已清空！"
    Write-Host ""
    Write-Host "  配置文件已保留在: " -NoNewline
    Write-Host "recall_data\config\" -ForegroundColor Cyan
}

# ==================== SillyTavern Plugin Operations ====================

function Set-STPath {
    Write-Title "设置 SillyTavern 路径"
    
    $config = Get-ManagerConfig
    
    if ($config.st_path) {
        Write-Dim "当前路径: $($config.st_path)"
    }
    
    Write-Host ""
    Write-Info "请输入 SillyTavern 安装路径"
    Write-Dim "示例: C:\SillyTavern 或 D:\Apps\SillyTavern"
    Write-Host ""
    
    $newPath = Read-Host "  路径"
    
    if (-not $newPath) {
        Write-Info "已取消"
        return
    }
    
    # Validate path
    if (-not (Test-Path $newPath)) {
        Write-Error2 "路径不存在: $newPath"
        return
    }
    
    # Check if valid ST directory
    $serverJs = Join-Path $newPath "server.js"
    $publicDir = Join-Path $newPath "public"
    
    if (-not ((Test-Path $serverJs) -and (Test-Path $publicDir))) {
        Write-Error2 "这不是有效的 SillyTavern 目录"
        Write-Dim "应包含 server.js 和 public 文件夹"
        return
    }
    
    $config.st_path = $newPath
    Save-ManagerConfig $config
    Write-Success "路径已保存: $newPath"
}

function Install-STPlugin {
    Write-Title "安装 SillyTavern 插件"
    
    $config = Get-ManagerConfig
    
    if (-not $config.st_path) {
        Write-Error2 "SillyTavern 路径未设置"
        Write-Info "请先设置路径（菜单选项 4）"
        return
    }
    
    if (-not (Test-Path $config.st_path)) {
        Write-Error2 "SillyTavern 路径不存在: $($config.st_path)"
        return
    }
    
    $sourceDir = Join-Path $SCRIPT_DIR "plugins\sillytavern"
    $targetDir = Join-Path $config.st_path "public\scripts\extensions\third-party\recall-memory"
    
    if (-not (Test-Path $sourceDir)) {
        Write-Error2 "插件源文件未找到: $sourceDir"
        return
    }
    
    # Create target directory
    if (Test-Path $targetDir) {
        Write-Info "插件目录已存在，正在更新..."
        Remove-Item -Path $targetDir -Recurse -Force
    }
    
    Write-Info "正在复制插件文件..."
    Copy-Item -Path $sourceDir -Destination $targetDir -Recurse -Force
    
    if (Test-Path $targetDir) {
        Write-Success "插件安装成功！"
        Write-Host ""
        Write-Info "下一步:"
        Write-Dim "1. 启动 Recall-ai 服务（主菜单选项 2）"
        Write-Dim "2. 启动/重启 SillyTavern"
        Write-Dim "3. 在 ST 扩展面板中找到 'Recall Memory System'"
    } else {
        Write-Error2 "插件安装失败"
    }
}

function Uninstall-STPlugin {
    Write-Title "卸载 SillyTavern 插件"
    
    if (-not (Test-STPluginInstalled)) {
        Write-Info "插件未安装"
        return
    }
    
    $pluginPath = Get-STPluginPath
    
    Write-Host ""
    Write-Info "将删除: $pluginPath"
    $confirm = Read-Host "  确认卸载？(y/N)"
    
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Info "已取消"
        return
    }
    
    try {
        Remove-Item -Path $pluginPath -Recurse -Force
        Write-Success "插件已卸载"
        Write-Dim "重启 SillyTavern 生效"
    } catch {
        Write-Error2 "卸载失败: $_"
    }
}

function Update-STPlugin {
    Write-Title "更新 SillyTavern 插件"
    
    if (-not (Test-STPluginInstalled)) {
        Write-Info "插件未安装，将直接安装..."
        Install-STPlugin
        return
    }
    
    Write-Info "正在更新插件..."
    Install-STPlugin
}

function Check-STPluginStatus {
    Write-Title "插件状态检查"
    
    $config = Get-ManagerConfig
    
    Write-Host ""
    
    # ST path
    if ($config.st_path) {
        Write-Success "SillyTavern 路径已配置"
        Write-Dim "路径: $($config.st_path)"
        
        if (Test-Path $config.st_path) {
            Write-Success "路径存在"
        } else {
            Write-Error2 "路径不存在！"
        }
    } else {
        Write-Error2 "SillyTavern 路径未配置"
    }
    
    Write-Host ""
    
    # Plugin status
    if (Test-STPluginInstalled) {
        Write-Success "插件已安装"
        $pluginPath = Get-STPluginPath
        Write-Dim "位置: $pluginPath"
        
        # Check file integrity
        $requiredFiles = @("index.js", "style.css", "manifest.json")
        $missing = @()
        foreach ($file in $requiredFiles) {
            $filePath = Join-Path $pluginPath $file
            if (-not (Test-Path $filePath)) {
                $missing += $file
            }
        }
        
        if ($missing.Count -eq 0) {
            Write-Success "所有文件完整"
        } else {
            Write-Error2 "缺少文件: $($missing -join ', ')"
        }
    } else {
        Write-Error2 "插件未安装"
    }
    
    Write-Host ""
    
    # Recall service status
    if (Test-ServiceRunning) {
        Write-Success "Recall 服务运行中"
    } else {
        Write-Error2 "Recall 服务未运行"
        Write-Dim "插件需要 Recall 服务运行"
    }
    
    Write-Host ""
    Read-Host "  按回车继续"
}

# ==================== Config Operations ====================

function Edit-Config {
    Write-Title "编辑配置文件"
    
    $configFile = Join-Path $SCRIPT_DIR "recall_data\config\api_keys.env"
    
    if (-not (Test-Path $configFile)) {
        Write-Info "配置文件不存在，正在创建..."
        $venvPython = Join-Path $SCRIPT_DIR "recall-env\Scripts\python.exe"
        if (Test-Path $venvPython) {
            & $venvPython -c "from recall.server import load_api_keys_from_file; load_api_keys_from_file()" 2>$null
        }
    }
    
    if (Test-Path $configFile) {
        Write-Info "正在打开配置文件..."
        Write-Dim "文件: $configFile"
        Start-Process notepad.exe -ArgumentList $configFile
    } else {
        Write-Error2 "无法创建配置文件"
    }
}

function Reload-Config {
    Write-Title "热更新配置"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "服务未运行，无法热更新"
        Write-Info "请先启动服务"
        return
    }
    
    Write-Info "正在重新加载配置..."
    
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/reload" -Method POST -TimeoutSec 10
        Write-Success "配置已重新加载！"
        
        # Show current mode
        $configInfo = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config" -TimeoutSec 5
        Write-Dim "当前 Embedding 模式: $($configInfo.embedding.mode)"
    } catch {
        Write-Error2 "热更新失败: $_"
    }
}

function Test-EmbeddingAPI {
    Write-Title "测试 Embedding API"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "服务未运行"
        return
    }
    
    Write-Info "正在测试 Embedding API 连接..."
    
    try {
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/test" -TimeoutSec 30
        
        Write-Host ""
        if ($result.success) {
            Write-Success "Embedding API 连接成功！"
            Write-Dim "后端: $($result.backend)"
            Write-Dim "模型: $($result.model)"
            Write-Dim "维度: $($result.dimension)"
            Write-Dim "延迟: $($result.latency_ms)ms"
        } else {
            Write-Error2 "Embedding API 连接失败"
            Write-Dim $result.message
        }
    } catch {
        Write-Error2 "测试失败: $_"
    }
    
    Write-Host ""
    Read-Host "  按回车继续"
}

function Test-LlmAPI {
    Write-Title "测试 LLM API"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "服务未运行"
        return
    }
    
    Write-Info "正在测试 LLM API 连接..."
    
    try {
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/test/llm" -TimeoutSec 30
        
        Write-Host ""
        if ($result.success) {
            Write-Success "LLM API 连接成功！"
            Write-Dim "模型: $($result.model)"
            Write-Dim "API 地址: $($result.api_base)"
            Write-Dim "响应: $($result.response)"
            Write-Dim "延迟: $($result.latency_ms)ms"
        } else {
            Write-Error2 "LLM API 连接失败"
            Write-Dim $result.message
        }
    } catch {
        Write-Error2 "测试失败: $_"
    }
    
    Write-Host ""
    Read-Host "  按回车继续"
}

function Show-CurrentConfig {
    Write-Title "当前配置"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "服务未运行，无法获取配置"
        return
    }
    
    try {
        $config = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config" -TimeoutSec 5
        
        Write-Host ""
        Write-Info "Embedding 模式: $($config.embedding.mode)"
        Write-Host ""
        
        Write-Dim "配置文件: $($config.config_file)"
        Write-Dim "文件存在: $($config.config_file_exists)"
        
        Write-Host ""
        Write-Info "Embedding 配置:"
        $embStatus = $config.embedding.status
        $statusColor = if ($embStatus -eq "Configured") { "Green" } else { "DarkGray" }
        Write-Host "  状态: " -NoNewline
        Write-Host $embStatus -ForegroundColor $statusColor
        Write-Dim "  API 地址: $($config.embedding.api_base)"
        Write-Dim "  模型: $($config.embedding.model)"
        Write-Dim "  维度: $($config.embedding.dimension)"
        
        Write-Host ""
        Write-Info "LLM 配置:"
        $llmStatus = $config.llm.status
        $statusColor = if ($llmStatus -eq "Configured") { "Green" } else { "DarkGray" }
        Write-Host "  状态: " -NoNewline
        Write-Host $llmStatus -ForegroundColor $statusColor
        Write-Dim "  API 地址: $($config.llm.api_base)"
        Write-Dim "  模型: $($config.llm.model)"
    } catch {
        Write-Error2 "获取配置失败: $_"
    }
    
    Write-Host ""
    Read-Host "  按回车继续"
}

function Reset-Config {
    Write-Title "重置配置"
    
    $configFile = Join-Path $SCRIPT_DIR "recall_data\config\api_keys.env"
    
    Write-Host ""
    Write-Info "这将删除当前配置并重新生成默认配置"
    $confirm = Read-Host "  确认重置？(y/N)"
    
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Info "已取消"
        return
    }
    
    if (Test-Path $configFile) {
        Remove-Item $configFile -Force
        Write-Success "配置已重置"
        Write-Info "下次启动服务时将生成默认配置"
    } else {
        Write-Info "配置文件不存在"
    }
}

# ==================== Menu Loops ====================

function Run-STMenu {
    while ($true) {
        Show-Banner
        Show-STMenu
        
        $choice = Read-Host "  请选择"
        
        switch ($choice) {
            "1" { Install-STPlugin; Read-Host "  按回车继续" }
            "2" { Uninstall-STPlugin; Read-Host "  按回车继续" }
            "3" { Update-STPlugin; Read-Host "  按回车继续" }
            "4" { Set-STPath; Read-Host "  按回车继续" }
            "5" { Check-STPluginStatus }
            "0" { return }
            default { Write-Error2 "无效选择" }
        }
    }
}

function Run-ConfigMenu {
    while ($true) {
        Show-Banner
        Show-ConfigMenu
        
        $choice = Read-Host "  请选择"
        
        switch ($choice) {
            "1" { Edit-Config; Read-Host "  按回车继续" }
            "2" { Reload-Config; Read-Host "  按回车继续" }
            "3" { Test-EmbeddingAPI }
            "4" { Test-LlmAPI }
            "5" { Show-CurrentConfig }
            "6" { Reset-Config; Read-Host "  按回车继续" }
            "0" { return }
            default { Write-Error2 "无效选择" }
        }
    }
}

function Run-MainMenu {
    while ($true) {
        Show-Banner
        Show-MainMenu
        
        $choice = Read-Host "  请选择"
        
        switch ($choice) {
            "1" { Do-Install; Read-Host "  按回车继续" }
            "2" { Do-Start; Read-Host "  按回车继续" }
            "3" { Do-Stop; Read-Host "  按回车继续" }
            "4" { Do-Restart; Read-Host "  按回车继续" }
            "5" { Do-Status }
            "6" { Run-STMenu }
            "7" { Run-ConfigMenu }
            "8" { Do-ClearData; Read-Host "  按回车继续" }
            "0" { 
                Write-Host ""
                Write-Color "  再见！" "Cyan"
                Write-Host ""
                exit 0
            }
            default { Write-Error2 "无效选择" }
        }
    }
}

# ==================== Command Line Mode ====================

function Run-CommandLine {
    param([string]$Action)
    
    switch ($Action.ToLower()) {
        "install" { Do-Install }
        "start" { Do-Start }
        "stop" { Do-Stop }
        "restart" { Do-Restart }
        "status" { Do-Status }
        "st-install" { Install-STPlugin }
        "st-uninstall" { Uninstall-STPlugin }
        "st-update" { Update-STPlugin }
        "clear-data" { Do-ClearData }
        default {
            Write-Host ""
            Write-Host "Recall-ai 管理工具" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "用法: .\manage.ps1 [命令]" -ForegroundColor White
            Write-Host ""
            Write-Host "命令:" -ForegroundColor Yellow
            Write-Host "  install      安装 Recall-ai"
            Write-Host "  start        启动服务"
            Write-Host "  stop         停止服务"
            Write-Host "  restart      重启服务"
            Write-Host "  status       查看状态"
            Write-Host "  st-install   安装 SillyTavern 插件"
            Write-Host "  st-uninstall 卸载 SillyTavern 插件"
            Write-Host "  st-update    更新 SillyTavern 插件"
            Write-Host "  clear-data   清空用户数据（保留配置）"
            Write-Host ""
            Write-Host "无参数运行进入交互式菜单" -ForegroundColor DarkGray
            Write-Host ""
        }
    }
}

# ==================== Main Entry ====================

if ($Action) {
    Run-CommandLine -Action $Action
} else {
    Run-MainMenu
}
