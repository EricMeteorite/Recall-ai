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
    Write-Host "  +============================================================+" -ForegroundColor Cyan
    Write-Host "  |                                                            |" -ForegroundColor Cyan
    Write-Host "  |              Recall-ai Manager  v$VERSION                     |" -ForegroundColor Cyan
    Write-Host "  |                                                            |" -ForegroundColor Cyan
    Write-Host "  |         Memory Management System for AI Characters         |" -ForegroundColor Cyan
    Write-Host "  +============================================================+" -ForegroundColor Cyan
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
    Write-Host "  |  Current Status                                           |" -ForegroundColor DarkGray
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor DarkGray
    
    # Recall-ai status
    $recallStatus = if ($installed) { 
        if ($running) { "[OK] Installed, Running" } else { "[OK] Installed, Not Running" }
    } else { "[X] Not Installed" }
    $recallColor = if ($installed -and $running) { "Green" } elseif ($installed) { "Yellow" } else { "Red" }
    Write-Host "  |  Recall-ai:        " -NoNewline -ForegroundColor DarkGray
    Write-Host $recallStatus.PadRight(38) -NoNewline -ForegroundColor $recallColor
    Write-Host "|" -ForegroundColor DarkGray
    
    # SillyTavern plugin status
    $stStatus = if ($stInstalled) { "[OK] Installed" } else { "[X] Not Installed" }
    $stColor = if ($stInstalled) { "Green" } else { "DarkGray" }
    Write-Host "  |  SillyTavern Plugin:" -NoNewline -ForegroundColor DarkGray
    Write-Host $stStatus.PadRight(38) -NoNewline -ForegroundColor $stColor
    Write-Host "|" -ForegroundColor DarkGray
    
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor DarkGray
    
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor White
    Write-Host "  |                       Main Menu                           |" -ForegroundColor White
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [1] Install Recall-ai                                  |" -ForegroundColor White
    Write-Host "  |    [2] Start Service                                      |" -ForegroundColor White
    Write-Host "  |    [3] Stop Service                                       |" -ForegroundColor White
    Write-Host "  |    [4] Restart Service                                    |" -ForegroundColor White
    Write-Host "  |    [5] View Status                                        |" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [6] SillyTavern Plugin Management  ->                  |" -ForegroundColor White
    Write-Host "  |    [7] Configuration Management       ->                  |" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [8] Clear User Data (Keep Config)                      |" -ForegroundColor Red
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [0] Exit                                               |" -ForegroundColor White
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
    Write-Host "  |              SillyTavern Plugin Management                |" -ForegroundColor Magenta
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    
    if ($config.st_path) {
        Write-Host "  |  ST Path: " -NoNewline -ForegroundColor Magenta
        $displayPath = if ($config.st_path.Length -gt 45) { $config.st_path.Substring(0, 42) + "..." } else { $config.st_path }
        Write-Host $displayPath.PadRight(47) -NoNewline -ForegroundColor DarkGray
        Write-Host "|" -ForegroundColor Magenta
    }
    
    $statusText = if ($stInstalled) { "[OK] Installed" } else { "[X] Not Installed" }
    $statusColor = if ($stInstalled) { "Green" } else { "Yellow" }
    Write-Host "  |  Plugin Status: " -NoNewline -ForegroundColor Magenta
    Write-Host $statusText.PadRight(41) -NoNewline -ForegroundColor $statusColor
    Write-Host "|" -ForegroundColor Magenta
    
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  |    [1] Install Plugin to SillyTavern                      |" -ForegroundColor Magenta
    Write-Host "  |    [2] Uninstall Plugin                                   |" -ForegroundColor Magenta
    Write-Host "  |    [3] Update Plugin                                      |" -ForegroundColor Magenta
    Write-Host "  |    [4] Set SillyTavern Path                               |" -ForegroundColor Magenta
    Write-Host "  |    [5] Check Plugin Status                                |" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  |    [0] <- Back to Main Menu                               |" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    Write-Host ""
}

# ==================== Config Menu ====================
function Show-ConfigMenu {
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |                  Configuration Management                 |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  |    [1] Edit API Config File                               |" -ForegroundColor Yellow
    Write-Host "  |    [2] Hot Reload Config (No Restart)                     |" -ForegroundColor Yellow
    Write-Host "  |    [3] Test Embedding API Connection                      |" -ForegroundColor Yellow
    Write-Host "  |    [4] Test LLM API Connection                            |" -ForegroundColor Yellow
    Write-Host "  |    [5] View Current Config                                |" -ForegroundColor Yellow
    Write-Host "  |    [6] Reset Config to Default                            |" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  |    [0] <- Back to Main Menu                               |" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""
}

# ==================== Operation Functions ====================

function Do-Install {
    Write-Title "Install Recall-ai"
    
    if (Test-Installed) {
        Write-Info "Recall-ai is already installed"
        $choice = Read-Host "  Reinstall? (y/N)"
        if ($choice -ne "y" -and $choice -ne "Y") {
            return
        }
    }
    
    $installScript = Join-Path $SCRIPT_DIR "install.ps1"
    if (Test-Path $installScript) {
        Write-Info "Running install script..."
        & $installScript
    } else {
        Write-Error2 "Install script not found: $installScript"
    }
}

function Do-Start {
    Write-Title "Start Service"
    
    if (-not (Test-Installed)) {
        Write-Error2 "Recall-ai not installed, please install first"
        return
    }
    
    if (Test-ServiceRunning) {
        Write-Info "Service is already running"
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
QUERY_PLANNER_ENABLED=false

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
'@
                Set-Content -Path $configFile -Value $defaultConfig -Encoding UTF8
                Write-Info "Created config file: $configFile"
            }
            
            Write-Host ""
            Write-Warning2 "Cloud mode requires Embedding API configuration"
            Write-Host ""
            Write-Info "Please edit config file:"
            Write-Dim "  $configFile"
            Write-Host ""
            Write-Info "After configuration, start service again"
            return
        }
    }
    
    $startScript = Join-Path $SCRIPT_DIR "start.ps1"
    $startLog = Join-Path $SCRIPT_DIR "recall_data\logs\start.log"
    
    if (Test-Path $startScript) {
        Write-Info "Starting service..."
        
        # Ensure log directory exists
        $logDir = Split-Path $startLog -Parent
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        
        # Start in background with log
        $errorLog = Join-Path $SCRIPT_DIR "recall_data\logs\start_error.log"
        Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startScript -WorkingDirectory $SCRIPT_DIR -RedirectStandardOutput $startLog -RedirectStandardError $errorLog -WindowStyle Hidden
        
        # Wait for service to start
        Write-Host "  Waiting for service to start" -NoNewline
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Seconds 1
            Write-Host "." -NoNewline
            if (Test-ServiceRunning) {
                Write-Host ""
                Write-Success "Service started!"
                Write-Dim "API Address: http://127.0.0.1:$DEFAULT_PORT"
                return
            }
        }
        Write-Host ""
        
        # Check if start failed
        if (-not (Test-ServiceRunning)) {
            Write-Error2 "Service failed to start"
            Write-Host ""
            Write-Info "Start log:"
            if (Test-Path $startLog) {
                Get-Content $startLog -Tail 20 | ForEach-Object { Write-Dim "  $_" }
            }
            Write-Host ""
            Write-Dim "Full log: $startLog"
        }
    } else {
        Write-Error2 "Start script not found: $startScript"
    }
}

function Do-Stop {
    Write-Title "Stop Service"
    
    if (-not (Test-ServiceRunning)) {
        Write-Info "Service is not running"
        return
    }
    
    Write-Info "Stopping service..."
    
    # Find and terminate uvicorn process
    $processes = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*recall*" -or $_.CommandLine -like "*recall.server*"
    }
    
    if ($processes) {
        $processes | Stop-Process -Force
        Write-Success "Service stopped"
    } else {
        # Try to find by port
        $netstat = netstat -ano | Select-String ":$DEFAULT_PORT.*LISTENING"
        if ($netstat) {
            $processId = ($netstat -split '\s+')[-1]
            if ($processId -and $processId -ne "0") {
                Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                Write-Success "Service stopped"
                return
            }
        }
        Write-Info "No running service process found"
    }
}

function Do-Restart {
    Write-Title "Restart Service"
    Do-Stop
    Start-Sleep -Seconds 2
    Do-Start
}

function Do-Status {
    Write-Title "Service Status"
    
    $installed = Test-Installed
    $running = Test-ServiceRunning
    
    Write-Host ""
    if ($installed) {
        Write-Success "Recall-ai is installed"
        
        # Get version info
        try {
            $venvPython = Join-Path $SCRIPT_DIR "recall-env\Scripts\python.exe"
            $version = & $venvPython -c "from recall.version import __version__; print(__version__)" 2>$null
            if ($version) {
                Write-Dim "Version: v$version"
            }
        } catch {}
    } else {
        Write-Error2 "Recall-ai not installed"
    }
    
    Write-Host ""
    if ($running) {
        Write-Success "Service is running"
        Write-Dim "API Address: http://127.0.0.1:$DEFAULT_PORT"
        
        # Get statistics
        try {
            $stats = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/stats" -TimeoutSec 5
            Write-Dim "Total Memories: $($stats.total_memories)"
            $mode = if ($stats.lite -or $stats.lightweight) { "Lite 模式" } else { "Local 模式" }
            Write-Dim "Embedding Mode: $mode"
        } catch {}
    } else {
        Write-Error2 "Service is not running"
    }
    
    Write-Host ""
    $stInstalled = Test-STPluginInstalled
    if ($stInstalled) {
        Write-Success "SillyTavern plugin is installed"
        $pluginPath = Get-STPluginPath
        Write-Dim "Path: $pluginPath"
    } else {
        Write-Info "SillyTavern plugin not installed"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

# ==================== Clear User Data ====================

function Do-ClearData {
    Write-Title "Clear User Data"
    
    $dataPath = Join-Path $SCRIPT_DIR "recall_data"
    
    if (-not (Test-Path $dataPath)) {
        Write-Info "No data directory found, nothing to clear"
        return
    }
    
    # Check if service is running
    if (Test-ServiceRunning) {
        Write-Error2 "Service is running. Please stop it first."
        Write-Host ""
        Write-Host "  Run: " -NoNewline
        Write-Host ".\manage.ps1 stop" -ForegroundColor Cyan
        Write-Host "  Or select option [3] Stop Service from menu" -ForegroundColor DarkGray
        return
    }
    
    # Show what will be deleted
    Write-Host ""
    Write-Host "  This will DELETE the following data:" -ForegroundColor Yellow
    Write-Host ""
    
    # Check each directory/file
    $dataDir = Join-Path $dataPath "data"
    $cacheDir = Join-Path $dataPath "cache"
    $logsDir = Join-Path $dataPath "logs"
    $tempDir = Join-Path $dataPath "temp"
    $indexesDir = Join-Path $dataPath "indexes"
    $l1Dir = Join-Path $dataPath "L1_consolidated"
    $kgFile = Join-Path $dataPath "knowledge_graph.json"
    $kgFileInData = Join-Path $dataPath "data" "knowledge_graph.json"
    
    $toDelete = @()
    
    if (Test-Path $dataDir) {
        $size = (Get-ChildItem $dataDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] data/           - All user memories ($sizeStr)" -ForegroundColor Red
        $toDelete += $dataDir
    }
    
    if (Test-Path $indexesDir) {
        $size = (Get-ChildItem $indexesDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] indexes/        - Entity and vector indexes ($sizeStr)" -ForegroundColor Red
        $toDelete += $indexesDir
    }
    
    if (Test-Path $l1Dir) {
        $size = (Get-ChildItem $l1Dir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] L1_consolidated/ - Long-term memory ($sizeStr)" -ForegroundColor Red
        $toDelete += $l1Dir
    }
    
    # Check knowledge_graph.json in both root and data/ directory
    if (Test-Path $kgFile) {
        $size = (Get-Item $kgFile -ErrorAction SilentlyContinue).Length
        $sizeStr = if ($size) { "{0:N2} KB" -f ($size / 1KB) } else { "0 KB" }
        Write-Host "    [x] knowledge_graph.json - Knowledge graph ($sizeStr)" -ForegroundColor Red
        $toDelete += $kgFile
    }
    if ((Test-Path $kgFileInData) -and (-not ($toDelete -contains $dataDir))) {
        # Only show if data/ won't be deleted (which would include this file)
        $size = (Get-Item $kgFileInData -ErrorAction SilentlyContinue).Length
        $sizeStr = if ($size) { "{0:N2} KB" -f ($size / 1KB) } else { "0 KB" }
        Write-Host "    [x] data/knowledge_graph.json - Knowledge graph ($sizeStr)" -ForegroundColor Red
        $toDelete += $kgFileInData
    }
    
    if (Test-Path $cacheDir) {
        $size = (Get-ChildItem $cacheDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] cache/          - Embedding cache ($sizeStr)" -ForegroundColor Red
        $toDelete += $cacheDir
    }
    
    if (Test-Path $logsDir) {
        $size = (Get-ChildItem $logsDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] logs/           - Log files ($sizeStr)" -ForegroundColor Red
        $toDelete += $logsDir
    }
    
    if (Test-Path $tempDir) {
        $size = (Get-ChildItem $tempDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size) { "{0:N2} MB" -f ($size / 1MB) } else { "0 MB" }
        Write-Host "    [x] temp/           - Temporary files ($sizeStr)" -ForegroundColor Red
        $toDelete += $tempDir
    }
    
    Write-Host ""
    Write-Host "  The following will be KEPT:" -ForegroundColor Green
    Write-Host "    [OK] config/    - API keys, install mode, settings" -ForegroundColor Green
    Write-Host "    [OK] models/    - Downloaded models (if any)" -ForegroundColor Green
    
    if ($toDelete.Count -eq 0) {
        Write-Host ""
        Write-Info "No data to clear"
        return
    }
    
    Write-Host ""
    Write-Host "  [!] WARNING: This action cannot be undone!" -ForegroundColor Yellow
    Write-Host ""
    
    $confirm = Read-Host "  Type 'yes' to confirm deletion"
    
    if ($confirm -ne "yes") {
        Write-Host ""
        Write-Info "Operation cancelled"
        return
    }
    
    Write-Host ""
    Write-Info "Clearing user data..."
    
    foreach ($dir in $toDelete) {
        try {
            Remove-Item -Path $dir -Recurse -Force -ErrorAction Stop
            $dirName = Split-Path $dir -Leaf
            Write-Success "Deleted: $dirName/"
        } catch {
            Write-Error2 "Failed to delete: $dir"
        }
    }
    
    # Recreate empty directories
    foreach ($dir in $toDelete) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    
    Write-Host ""
    Write-Success "User data cleared successfully!"
    Write-Host ""
    Write-Host "  Your config files are preserved in: " -NoNewline
    Write-Host "recall_data\config\" -ForegroundColor Cyan
}

# ==================== SillyTavern Plugin Operations ====================

function Set-STPath {
    Write-Title "Set SillyTavern Path"
    
    $config = Get-ManagerConfig
    
    if ($config.st_path) {
        Write-Dim "Current path: $($config.st_path)"
    }
    
    Write-Host ""
    Write-Info "Please enter the SillyTavern installation path"
    Write-Dim "Example: C:\SillyTavern or D:\Apps\SillyTavern"
    Write-Host ""
    
    $newPath = Read-Host "  Path"
    
    if (-not $newPath) {
        Write-Info "Cancelled"
        return
    }
    
    # Validate path
    if (-not (Test-Path $newPath)) {
        Write-Error2 "Path does not exist: $newPath"
        return
    }
    
    # Check if valid ST directory
    $serverJs = Join-Path $newPath "server.js"
    $publicDir = Join-Path $newPath "public"
    
    if (-not ((Test-Path $serverJs) -and (Test-Path $publicDir))) {
        Write-Error2 "This is not a valid SillyTavern directory"
        Write-Dim "Should contain server.js and public folder"
        return
    }
    
    $config.st_path = $newPath
    Save-ManagerConfig $config
    Write-Success "Path saved: $newPath"
}

function Install-STPlugin {
    Write-Title "Install SillyTavern Plugin"
    
    $config = Get-ManagerConfig
    
    if (-not $config.st_path) {
        Write-Error2 "SillyTavern path not set"
        Write-Info "Please set the path first (menu option 4)"
        return
    }
    
    if (-not (Test-Path $config.st_path)) {
        Write-Error2 "SillyTavern path does not exist: $($config.st_path)"
        return
    }
    
    $sourceDir = Join-Path $SCRIPT_DIR "plugins\sillytavern"
    $targetDir = Join-Path $config.st_path "public\scripts\extensions\third-party\recall-memory"
    
    if (-not (Test-Path $sourceDir)) {
        Write-Error2 "Plugin source not found: $sourceDir"
        return
    }
    
    # Create target directory
    if (Test-Path $targetDir) {
        Write-Info "Plugin directory exists, updating..."
        Remove-Item -Path $targetDir -Recurse -Force
    }
    
    Write-Info "Copying plugin files..."
    Copy-Item -Path $sourceDir -Destination $targetDir -Recurse -Force
    
    if (Test-Path $targetDir) {
        Write-Success "Plugin installed successfully!"
        Write-Host ""
        Write-Info "Next steps:"
        Write-Dim "1. Start Recall-ai service (main menu option 2)"
        Write-Dim "2. Start/restart SillyTavern"
        Write-Dim "3. Find 'Recall Memory System' in ST extensions panel"
    } else {
        Write-Error2 "Plugin installation failed"
    }
}

function Uninstall-STPlugin {
    Write-Title "Uninstall SillyTavern Plugin"
    
    if (-not (Test-STPluginInstalled)) {
        Write-Info "Plugin is not installed"
        return
    }
    
    $pluginPath = Get-STPluginPath
    
    Write-Host ""
    Write-Info "Will delete: $pluginPath"
    $confirm = Read-Host "  Confirm uninstall? (y/N)"
    
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Info "Cancelled"
        return
    }
    
    try {
        Remove-Item -Path $pluginPath -Recurse -Force
        Write-Success "Plugin uninstalled"
        Write-Dim "Restart SillyTavern to take effect"
    } catch {
        Write-Error2 "Uninstall failed: $_"
    }
}

function Update-STPlugin {
    Write-Title "Update SillyTavern Plugin"
    
    if (-not (Test-STPluginInstalled)) {
        Write-Info "Plugin not installed, will install..."
        Install-STPlugin
        return
    }
    
    Write-Info "Updating plugin..."
    Install-STPlugin
}

function Check-STPluginStatus {
    Write-Title "Plugin Status Check"
    
    $config = Get-ManagerConfig
    
    Write-Host ""
    
    # ST path
    if ($config.st_path) {
        Write-Success "SillyTavern path configured"
        Write-Dim "Path: $($config.st_path)"
        
        if (Test-Path $config.st_path) {
            Write-Success "Path exists"
        } else {
            Write-Error2 "Path does not exist!"
        }
    } else {
        Write-Error2 "SillyTavern path not configured"
    }
    
    Write-Host ""
    
    # Plugin status
    if (Test-STPluginInstalled) {
        Write-Success "Plugin is installed"
        $pluginPath = Get-STPluginPath
        Write-Dim "Location: $pluginPath"
        
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
            Write-Success "All files present"
        } else {
            Write-Error2 "Missing files: $($missing -join ', ')"
        }
    } else {
        Write-Error2 "Plugin not installed"
    }
    
    Write-Host ""
    
    # Recall service status
    if (Test-ServiceRunning) {
        Write-Success "Recall service is running"
    } else {
        Write-Error2 "Recall service is not running"
        Write-Dim "Plugin requires Recall service to work"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

# ==================== Config Operations ====================

function Edit-Config {
    Write-Title "Edit Config File"
    
    $configFile = Join-Path $SCRIPT_DIR "recall_data\config\api_keys.env"
    
    if (-not (Test-Path $configFile)) {
        Write-Info "Config file does not exist, creating..."
        $venvPython = Join-Path $SCRIPT_DIR "recall-env\Scripts\python.exe"
        if (Test-Path $venvPython) {
            & $venvPython -c "from recall.server import load_api_keys_from_file; load_api_keys_from_file()" 2>$null
        }
    }
    
    if (Test-Path $configFile) {
        Write-Info "Opening config file..."
        Write-Dim "File: $configFile"
        Start-Process notepad.exe -ArgumentList $configFile
    } else {
        Write-Error2 "Cannot create config file"
    }
}

function Reload-Config {
    Write-Title "Hot Reload Config"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running, cannot hot reload"
        Write-Info "Please start the service first"
        return
    }
    
    Write-Info "Reloading config..."
    
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/reload" -Method POST -TimeoutSec 10
        Write-Success "Config reloaded!"
        
        # Show current mode
        $configInfo = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config" -TimeoutSec 5
        Write-Dim "Current Embedding Mode: $($configInfo.embedding.mode)"
    } catch {
        Write-Error2 "Hot reload failed: $_"
    }
}

function Test-EmbeddingAPI {
    Write-Title "Test Embedding API"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running"
        return
    }
    
    Write-Info "Testing Embedding API connection..."
    
    try {
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/test" -TimeoutSec 30
        
        Write-Host ""
        if ($result.success) {
            Write-Success "Embedding API connection successful!"
            Write-Dim "Backend: $($result.backend)"
            Write-Dim "Model: $($result.model)"
            Write-Dim "Dimension: $($result.dimension)"
            Write-Dim "Latency: $($result.latency_ms)ms"
        } else {
            Write-Error2 "Embedding API connection failed"
            Write-Dim $result.message
        }
    } catch {
        Write-Error2 "Test failed: $_"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

function Test-LlmAPI {
    Write-Title "Test LLM API"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running"
        return
    }
    
    Write-Info "Testing LLM API connection..."
    
    try {
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/test/llm" -TimeoutSec 30
        
        Write-Host ""
        if ($result.success) {
            Write-Success "LLM API connection successful!"
            Write-Dim "Model: $($result.model)"
            Write-Dim "API Base: $($result.api_base)"
            Write-Dim "Response: $($result.response)"
            Write-Dim "Latency: $($result.latency_ms)ms"
        } else {
            Write-Error2 "LLM API connection failed"
            Write-Dim $result.message
        }
    } catch {
        Write-Error2 "Test failed: $_"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

function Show-CurrentConfig {
    Write-Title "Current Config"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running, cannot get config"
        return
    }
    
    try {
        $config = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config" -TimeoutSec 5
        
        Write-Host ""
        Write-Info "Embedding Mode: $($config.embedding.mode)"
        Write-Host ""
        
        Write-Dim "Config File: $($config.config_file)"
        Write-Dim "File Exists: $($config.config_file_exists)"
        
        Write-Host ""
        Write-Info "Embedding Config:"
        $embStatus = $config.embedding.status
        $statusColor = if ($embStatus -eq "Configured") { "Green" } else { "DarkGray" }
        Write-Host "  Status: " -NoNewline
        Write-Host $embStatus -ForegroundColor $statusColor
        Write-Dim "  API Base: $($config.embedding.api_base)"
        Write-Dim "  Model: $($config.embedding.model)"
        Write-Dim "  Dimension: $($config.embedding.dimension)"
        
        Write-Host ""
        Write-Info "LLM Config:"
        $llmStatus = $config.llm.status
        $statusColor = if ($llmStatus -eq "Configured") { "Green" } else { "DarkGray" }
        Write-Host "  Status: " -NoNewline
        Write-Host $llmStatus -ForegroundColor $statusColor
        Write-Dim "  API Base: $($config.llm.api_base)"
        Write-Dim "  Model: $($config.llm.model)"
    } catch {
        Write-Error2 "Failed to get config: $_"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

function Reset-Config {
    Write-Title "Reset Config"
    
    $configFile = Join-Path $SCRIPT_DIR "recall_data\config\api_keys.env"
    
    Write-Host ""
    Write-Info "This will delete current config and regenerate default"
    $confirm = Read-Host "  Confirm reset? (y/N)"
    
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Info "Cancelled"
        return
    }
    
    if (Test-Path $configFile) {
        Remove-Item $configFile -Force
        Write-Success "Config reset"
        Write-Info "Default config will be generated on next service start"
    } else {
        Write-Info "Config file does not exist"
    }
}

# ==================== Menu Loops ====================

function Run-STMenu {
    while ($true) {
        Show-Banner
        Show-STMenu
        
        $choice = Read-Host "  Select"
        
        switch ($choice) {
            "1" { Install-STPlugin; Read-Host "  Press Enter to continue" }
            "2" { Uninstall-STPlugin; Read-Host "  Press Enter to continue" }
            "3" { Update-STPlugin; Read-Host "  Press Enter to continue" }
            "4" { Set-STPath; Read-Host "  Press Enter to continue" }
            "5" { Check-STPluginStatus }
            "0" { return }
            default { Write-Error2 "Invalid selection" }
        }
    }
}

function Run-ConfigMenu {
    while ($true) {
        Show-Banner
        Show-ConfigMenu
        
        $choice = Read-Host "  Select"
        
        switch ($choice) {
            "1" { Edit-Config; Read-Host "  Press Enter to continue" }
            "2" { Reload-Config; Read-Host "  Press Enter to continue" }
            "3" { Test-EmbeddingAPI }
            "4" { Test-LlmAPI }
            "5" { Show-CurrentConfig }
            "6" { Reset-Config; Read-Host "  Press Enter to continue" }
            "0" { return }
            default { Write-Error2 "Invalid selection" }
        }
    }
}

function Run-MainMenu {
    while ($true) {
        Show-Banner
        Show-MainMenu
        
        $choice = Read-Host "  Select"
        
        switch ($choice) {
            "1" { Do-Install; Read-Host "  Press Enter to continue" }
            "2" { Do-Start; Read-Host "  Press Enter to continue" }
            "3" { Do-Stop; Read-Host "  Press Enter to continue" }
            "4" { Do-Restart; Read-Host "  Press Enter to continue" }
            "5" { Do-Status }
            "6" { Run-STMenu }
            "7" { Run-ConfigMenu }
            "8" { Do-ClearData; Read-Host "  Press Enter to continue" }
            "0" { 
                Write-Host ""
                Write-Color "  Goodbye!" "Cyan"
                Write-Host ""
                exit 0
            }
            default { Write-Error2 "Invalid selection" }
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
            Write-Host "Recall-ai Manager" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "Usage: .\manage.ps1 [command]" -ForegroundColor White
            Write-Host ""
            Write-Host "Commands:" -ForegroundColor Yellow
            Write-Host "  install      Install Recall-ai"
            Write-Host "  start        Start service"
            Write-Host "  stop         Stop service"
            Write-Host "  restart      Restart service"
            Write-Host "  status       View status"
            Write-Host "  st-install   Install SillyTavern plugin"
            Write-Host "  st-uninstall Uninstall SillyTavern plugin"
            Write-Host "  st-update    Update SillyTavern plugin"
            Write-Host "  clear-data   Clear all user data (keep config)"
            Write-Host ""
            Write-Host "Run without arguments for interactive menu" -ForegroundColor DarkGray
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
