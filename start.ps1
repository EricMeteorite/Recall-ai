<#
.SYNOPSIS
    Recall AI - Windows 服务管理脚本 v2.0

.DESCRIPTION
    功能：
    - 前台/后台运行模式
    - 服务状态查看
    - 日志查看
    - 优雅停止

.EXAMPLE
    .\start.ps1              # 前台运行
    .\start.ps1 -Daemon      # 后台运行
    .\start.ps1 -Stop        # 停止服务
    .\start.ps1 -Status      # 查看状态
    .\start.ps1 -Logs        # 查看日志
    .\start.ps1 -Restart     # 重启服务
#>

param(
    [switch]$Daemon,
    [switch]$Stop,
    [switch]$Status,
    [switch]$Logs,
    [switch]$Restart,
    [switch]$Help,
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 18888
)

$ErrorActionPreference = "SilentlyContinue"

# ==================== 全局变量 ====================
$ScriptDir = $PSScriptRoot
$VenvPath = Join-Path $ScriptDir "recall-env"
$RecallPath = Join-Path $VenvPath "Scripts\recall.exe"
$PidFile = Join-Path $ScriptDir "recall.pid"
$LogDir = Join-Path $ScriptDir "recall_data\logs"
$LogFile = Join-Path $LogDir "recall.log"

# 环境变量优先
if ($env:RECALL_HOST) { $BindHost = $env:RECALL_HOST }
if ($env:RECALL_PORT) { $Port = [int]$env:RECALL_PORT }

# ==================== 工具函数 ====================

function Write-Header {
    $title = "Recall AI Server"
    try { $host.UI.RawUI.WindowTitle = $title } catch {}
    
    Write-Host ""
    Write-Host "+============================================+" -ForegroundColor Cyan
    Write-Host "|          Recall AI v3.0.0 Server          |" -ForegroundColor Cyan
    Write-Host "+============================================+" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Success {
    param([string]$Message)
    Write-Host "  [OK] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Error2 {
    param([string]$Message)
    Write-Host "  [X] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Write-Warning2 {
    param([string]$Message)
    Write-Host "  [!] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Info {
    param([string]$Message)
    Write-Host "  -> " -ForegroundColor Cyan -NoNewline
    Write-Host $Message
}

# ==================== 检查安装 ====================

function Test-Installation {
    if (-not (Test-Path $RecallPath)) {
        Write-Header
        Write-Error2 "Recall 未安装"
        Write-Host ""
        Write-Host "  请先运行安装脚本:" -ForegroundColor Yellow
        Write-Host "    .\install.ps1" -ForegroundColor Cyan
        Write-Host ""
        return $false
    }
    return $true
}

# ==================== 获取运行状态 ====================

function Get-RecallProcess {
    if (Test-Path $PidFile) {
        $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($savedPid) {
            $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
            if ($proc -and $proc.ProcessName -like "*python*" -or $proc.ProcessName -like "*recall*") {
                return $proc
            }
        }
    }
    return $null
}

function Test-ApiHealth {
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:$Port/" -TimeoutSec 2 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# ==================== 加载配置文件 ====================

function Import-ApiKeys {
    $configFile = Join-Path $ScriptDir "recall_data\config\api_keys.env"
    
    # 支持的配置项（与 server.py SUPPORTED_CONFIG_KEYS 保持一致）
    $supportedKeys = @(
        # Embedding 配置
        'EMBEDDING_API_KEY', 'EMBEDDING_API_BASE', 'EMBEDDING_MODEL', 'EMBEDDING_DIMENSION',
        'EMBEDDING_RATE_LIMIT', 'EMBEDDING_RATE_WINDOW',
        'RECALL_EMBEDDING_MODE',
        # LLM 配置
        'LLM_API_KEY', 'LLM_API_BASE', 'LLM_MODEL',
        # 伏笔分析器配置
        'FORESHADOWING_LLM_ENABLED', 'FORESHADOWING_TRIGGER_INTERVAL',
        'FORESHADOWING_AUTO_PLANT', 'FORESHADOWING_AUTO_RESOLVE',
        'FORESHADOWING_MAX_RETURN', 'FORESHADOWING_MAX_ACTIVE',
        # 持久条件系统配置
        'CONTEXT_TRIGGER_INTERVAL', 'CONTEXT_MAX_CONTEXT_TURNS',
        'CONTEXT_MAX_PER_TYPE', 'CONTEXT_MAX_TOTAL',
        'CONTEXT_DECAY_DAYS', 'CONTEXT_DECAY_RATE', 'CONTEXT_MIN_CONFIDENCE',
        # 上下文构建配置
        'BUILD_CONTEXT_INCLUDE_RECENT',
        'PROACTIVE_REMINDER_ENABLED', 'PROACTIVE_REMINDER_TURNS',
        # 智能去重配置
        'DEDUP_EMBEDDING_ENABLED', 'DEDUP_HIGH_THRESHOLD', 'DEDUP_LOW_THRESHOLD',
        # ====== v4.0 Phase 1/2 新增配置项 ======
        # 时态知识图谱配置
        'TEMPORAL_GRAPH_ENABLED', 'TEMPORAL_GRAPH_BACKEND', 'TEMPORAL_DECAY_RATE', 'TEMPORAL_MAX_HISTORY',
        # 矛盾检测与管理配置
        'CONTRADICTION_DETECTION_ENABLED', 'CONTRADICTION_AUTO_RESOLVE',
        'CONTRADICTION_DETECTION_STRATEGY', 'CONTRADICTION_SIMILARITY_THRESHOLD',
        # 全文检索配置 (BM25)
        'FULLTEXT_ENABLED', 'FULLTEXT_K1', 'FULLTEXT_B', 'FULLTEXT_WEIGHT',
        # 智能抽取器配置
        'SMART_EXTRACTOR_MODE', 'SMART_EXTRACTOR_COMPLEXITY_THRESHOLD', 'SMART_EXTRACTOR_ENABLE_TEMPORAL',
        # 预算管理配置
        'BUDGET_DAILY_LIMIT', 'BUDGET_HOURLY_LIMIT', 'BUDGET_RESERVE', 'BUDGET_ALERT_THRESHOLD',
        # 三阶段去重配置
        'DEDUP_JACCARD_THRESHOLD', 'DEDUP_SEMANTIC_THRESHOLD', 'DEDUP_SEMANTIC_LOW_THRESHOLD', 'DEDUP_LLM_ENABLED',
        # ====== v4.0 Phase 3 十一层检索器配置项 ======
        'ELEVEN_LAYER_RETRIEVER_ENABLED',
        # 层开关配置
        'RETRIEVAL_L1_BLOOM_ENABLED', 'RETRIEVAL_L2_TEMPORAL_ENABLED', 'RETRIEVAL_L3_INVERTED_ENABLED',
        'RETRIEVAL_L4_ENTITY_ENABLED', 'RETRIEVAL_L5_GRAPH_ENABLED', 'RETRIEVAL_L6_NGRAM_ENABLED',
        'RETRIEVAL_L7_VECTOR_COARSE_ENABLED', 'RETRIEVAL_L8_VECTOR_FINE_ENABLED', 'RETRIEVAL_L9_RERANK_ENABLED',
        'RETRIEVAL_L10_CROSS_ENCODER_ENABLED', 'RETRIEVAL_L11_LLM_ENABLED',
        # Top-K 配置
        'RETRIEVAL_L2_TEMPORAL_TOP_K', 'RETRIEVAL_L3_INVERTED_TOP_K', 'RETRIEVAL_L4_ENTITY_TOP_K',
        'RETRIEVAL_L5_GRAPH_TOP_K', 'RETRIEVAL_L6_NGRAM_TOP_K', 'RETRIEVAL_L7_VECTOR_TOP_K',
        'RETRIEVAL_L10_CROSS_ENCODER_TOP_K', 'RETRIEVAL_L11_LLM_TOP_K',
        # 阈值与最终输出配置
        'RETRIEVAL_FINE_RANK_THRESHOLD', 'RETRIEVAL_FINAL_TOP_K',
        # L5 图遍历配置
        'RETRIEVAL_L5_GRAPH_MAX_DEPTH', 'RETRIEVAL_L5_GRAPH_MAX_ENTITIES', 'RETRIEVAL_L5_GRAPH_DIRECTION',
        # L10 CrossEncoder 配置
        'RETRIEVAL_L10_CROSS_ENCODER_MODEL',
        # L11 LLM 配置
        'RETRIEVAL_L11_LLM_TIMEOUT',
        # 权重配置
        'RETRIEVAL_WEIGHT_INVERTED', 'RETRIEVAL_WEIGHT_ENTITY', 'RETRIEVAL_WEIGHT_GRAPH',
        'RETRIEVAL_WEIGHT_NGRAM', 'RETRIEVAL_WEIGHT_VECTOR', 'RETRIEVAL_WEIGHT_TEMPORAL'
    )
    
    if (Test-Path $configFile) {
        Write-Host "  $([char]0x2192) 加载配置文件: $configFile" -ForegroundColor Cyan
        
        Get-Content $configFile | ForEach-Object {
            $line = $_.Trim()
            # 跳过注释和空行
            if ($line -and -not $line.StartsWith('#')) {
                if ($line -match '^([^=]+)=(.*)$') {
                    $key = $matches[1].Trim()
                    $value = $matches[2].Trim()
                    
                    # 只处理支持的配置项
                    if ($supportedKeys -contains $key -and $value) {
                        Set-Item -Path "env:$key" -Value $value
                        # 敏感信息脱敏显示
                        if ($key -like '*KEY*') {
                            $displayValue = if ($value.Length -gt 8) { $value.Substring(0, 8) + '...' } else { '***' }
                        } else {
                            $displayValue = $value
                        }
                        Write-Host "  $([char]0x2713) 已加载: $key=$displayValue" -ForegroundColor Green
                    }
                }
            }
        }
    } else {
        # 创建默认配置文件
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
'@
        Set-Content -Path $configFile -Value $defaultConfig -Encoding UTF8
        Write-Host "  $([char]0x2192) 已创建配置文件: $configFile" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  ⚠️  首次运行，请先配置 API:" -ForegroundColor Yellow
        Write-Host "     编辑: $configFile" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  至少需要配置 Embedding API（用于语义搜索）:" -ForegroundColor White
        Write-Host "    EMBEDDING_API_KEY=your-api-key" -ForegroundColor Cyan
        Write-Host "    EMBEDDING_API_BASE=https://api.siliconflow.cn/v1" -ForegroundColor Cyan
        Write-Host "    EMBEDDING_MODEL=BAAI/bge-m3" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  配置完成后重新运行: .\manage.ps1" -ForegroundColor White
        Write-Host ""
        return
    }
}

# ==================== Embedding 模式检测 ====================

function Get-EmbeddingMode {
    $modeFile = Join-Path $ScriptDir "recall_data\config\install_mode"
    
    if (Test-Path $modeFile) {
        $installMode = Get-Content $modeFile -ErrorAction SilentlyContinue
        switch ($installMode) {
            { $_ -in "lite", "lightweight" } { return "none" }
            { $_ -in "cloud", "hybrid" } {
                # Cloud 模式需要检查 API Key
                # 排除占位符值
                $key = $env:EMBEDDING_API_KEY
                if ($key -and 
                    $key -ne "your_embedding_api_key_here" -and 
                    $key -ne "your_api_key_here" -and 
                    -not $key.StartsWith("your_")) {
                    return "api"
                } else {
                    return "api_required"
                }
            }
            { $_ -in "local", "full" } { return "local" }
            default { return "local" }
        }
    } else {
        return "local"
    }
}

# ==================== 启动服务 ====================

function Start-RecallService {
    param([bool]$IsDaemon = $false)
    
    Write-Header
    
    # 加载配置文件中的 API Keys
    Import-ApiKeys
    
    # 检查是否已运行
    $existingProc = Get-RecallProcess
    if ($existingProc) {
        Write-Warning2 "服务已在运行 (PID: $($existingProc.Id))"
        Write-Host ""
        Write-Host "  停止服务: " -NoNewline
        Write-Host ".\start.ps1 -Stop" -ForegroundColor Cyan
        Write-Host "  查看状态: " -NoNewline
        Write-Host ".\start.ps1 -Status" -ForegroundColor Cyan
        Write-Host ""
        return
    }
    
    # 获取 Embedding 模式
    $embeddingMode = Get-EmbeddingMode
    
    # 检查 Cloud 模式是否配置了 API Key
    if ($embeddingMode -eq "api_required") {
        Write-Error2 "Cloud 模式需要配置 API Key"
        Write-Host ""
        Write-Host "  请编辑配置文件: " -NoNewline
        Write-Host "recall_data\config\api_keys.env" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  设置以下配置项（OpenAI 兼容格式）：" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "    " -NoNewline; Write-Host 'EMBEDDING_API_KEY=your-api-key' -ForegroundColor Cyan
        Write-Host "    " -NoNewline; Write-Host 'EMBEDDING_API_BASE=https://your-api-provider/v1' -ForegroundColor Cyan
        Write-Host "    " -NoNewline; Write-Host 'EMBEDDING_MODEL=your-embedding-model' -ForegroundColor Cyan
        Write-Host "    " -NoNewline; Write-Host 'EMBEDDING_DIMENSION=1024' -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  然后重新运行: " -NoNewline; Write-Host ".\start.ps1" -ForegroundColor Cyan
        Write-Host ""
        return
    }
    
    # 确保日志目录存在
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
    
    # 显示启动配置
    Write-Success "API 地址: http://${BindHost}:${Port}"
    Write-Success "API 文档: http://localhost:${Port}/docs"
    
    # 显示 Embedding 模式
    switch ($embeddingMode) {
        "none" { Write-Info "Embedding: Lite 模式 (仅关键词搜索)" }
        "api" { Write-Success "Embedding: Cloud 模式 (API 语义搜索)" }
        "local" { Write-Success "Embedding: Local 模式 (本地模型)" }
    }
    Write-Host ""
    
    # 设置环境变量
    $env:RECALL_EMBEDDING_MODE = $embeddingMode
    
    if ($IsDaemon) {
        Write-Info "后台启动中..."
        
        # 后台启动，输出重定向到日志
        $proc = Start-Process -FilePath $RecallPath `
            -ArgumentList "serve","--host",$BindHost,"--port",$Port `
            -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $LogFile `
            -RedirectStandardError "$LogDir\recall_error.log"
        
        $proc.Id | Out-File $PidFile -Force
        
        # 等待启动
        Start-Sleep -Seconds 3
        
        if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
            Write-Host ""
            Write-Success "启动成功!"
            Write-Host ""
            Write-Host "    PID:      $($proc.Id)" -ForegroundColor White
            Write-Host "    日志:     $LogFile" -ForegroundColor White
            Write-Host ""
            Write-Host "  常用命令:" -ForegroundColor White
            Write-Host "    查看状态: .\start.ps1 -Status" -ForegroundColor Cyan
            Write-Host "    查看日志: .\start.ps1 -Logs" -ForegroundColor Cyan
            Write-Host "    停止服务: .\start.ps1 -Stop" -ForegroundColor Cyan
            Write-Host ""
        } else {
            Write-Error2 "启动失败"
            Write-Host ""
            Write-Host "  查看错误日志:" -ForegroundColor Yellow
            Write-Host "    Get-Content '$LogDir\recall_error.log' -Tail 20" -ForegroundColor Cyan
            Write-Host ""
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Info "前台运行模式"
        Write-Info "按 Ctrl+C 停止服务"
        Write-Host ""
        Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
        Write-Host ""
        
        try {
            & $RecallPath serve --host $BindHost --port $Port
        } finally {
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        }
    }
}

# ==================== 停止服务 ====================

function Stop-RecallService {
    Write-Header
    
    $proc = Get-RecallProcess
    
    if ($proc) {
        Write-Info "正在停止服务 (PID: $($proc.Id))..."
        
        # 优雅停止
        $proc | Stop-Process -Force
        
        # 等待停止
        $timeout = 10
        while ($timeout -gt 0 -and (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
            Start-Sleep -Seconds 1
            $timeout--
        }
        
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        
        Write-Host ""
        Write-Success "服务已停止"
    } else {
        Write-Warning2 "服务未运行"
        
        # 清理残留PID文件
        if (Test-Path $PidFile) {
            Remove-Item $PidFile -Force
            Write-Info "已清理残留PID文件"
        }
    }
    Write-Host ""
}

# ==================== 重启服务 ====================

function Restart-RecallService {
    Write-Header
    Write-Info "重启服务..."
    
    $proc = Get-RecallProcess
    if ($proc) {
        $proc | Stop-Process -Force
        Start-Sleep -Seconds 2
    }
    
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    
    Start-RecallService -IsDaemon $true
}

# ==================== 查看状态 ====================

function Show-Status {
    Write-Header
    Write-Host "📊 服务状态" -ForegroundColor White
    Write-Host ""
    
    $proc = Get-RecallProcess
    
    if ($proc) {
        Write-Success "运行状态: 🟢 运行中"
        Write-Host ""
        
        # 详细信息
        Write-Host "    PID:          $($proc.Id)" -ForegroundColor White
        
        # 内存
        $mem = $proc.WorkingSet64 / 1MB
        Write-Host "    内存占用:      $("{0:N1}" -f $mem) MB" -ForegroundColor White
        
        # CPU
        try {
            $cpu = $proc.CPU
            Write-Host "    CPU 时间:      $("{0:N1}" -f $cpu) 秒" -ForegroundColor White
        } catch {}
        
        # 运行时间
        try {
            $uptime = (Get-Date) - $proc.StartTime
            $uptimeStr = ""
            if ($uptime.Days -gt 0) { $uptimeStr += "$($uptime.Days)天 " }
            if ($uptime.Hours -gt 0) { $uptimeStr += "$($uptime.Hours)时 " }
            $uptimeStr += "$($uptime.Minutes)分 $($uptime.Seconds)秒"
            Write-Host "    运行时间:      $uptimeStr" -ForegroundColor White
        } catch {}
        
        # API 健康检查
        Write-Host ""
        if (Test-ApiHealth) {
            Write-Success "API 状态: 🟢 正常"
            Write-Host "    API 地址:      http://localhost:$Port" -ForegroundColor White
        } else {
            Write-Warning2 "API 状态: 🟡 无响应 (可能正在启动)"
        }
        
    } else {
        Write-Warning2 "运行状态: 🔴 未运行"
        
        if (Test-Path $PidFile) {
            Write-Info "存在残留PID文件，可能是异常退出"
        }
    }
    
    Write-Host ""
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  常用命令:" -ForegroundColor White
    Write-Host "    启动服务: .\start.ps1 -Daemon" -ForegroundColor Cyan
    Write-Host "    停止服务: .\start.ps1 -Stop" -ForegroundColor Cyan
    Write-Host "    查看日志: .\start.ps1 -Logs" -ForegroundColor Cyan
    Write-Host ""
}

# ==================== 查看日志 ====================

function Show-Logs {
    Write-Header
    
    if (-not (Test-Path $LogFile)) {
        Write-Warning2 "日志文件不存在: $LogFile"
        Write-Host ""
        Write-Host "  服务可能从未以后台模式运行过" -ForegroundColor Yellow
        Write-Host "  使用 .\start.ps1 -Daemon 启动后台服务" -ForegroundColor Cyan
        Write-Host ""
        return
    }
    
    Write-Info "日志文件: $LogFile"
    Write-Info "按 Ctrl+C 退出日志查看"
    Write-Host ""
    Write-Host "─────────────────────────────────────────────" -ForegroundColor Gray
    Write-Host ""
    
    # 实时显示日志
    Get-Content $LogFile -Tail 50 -Wait
}

# ==================== 显示帮助 ====================

function Show-Help {
    Write-Header
    Write-Host "用法: .\start.ps1 [选项]" -ForegroundColor White
    Write-Host ""
    Write-Host "选项:" -ForegroundColor White
    Write-Host "  (无参数)     前台运行服务"
    Write-Host "  -Daemon      后台运行服务"
    Write-Host "  -Stop        停止服务"
    Write-Host "  -Status      查看服务状态"
    Write-Host "  -Logs        查看实时日志"
    Write-Host "  -Restart     重启服务"
    Write-Host "  -Help        显示帮助"
    Write-Host ""
    Write-Host "参数:" -ForegroundColor White
    Write-Host "  -BindHost    绑定主机 (默认: 0.0.0.0)"
    Write-Host "  -Port        端口号 (默认: 18888)"
    Write-Host ""
    Write-Host "环境变量:" -ForegroundColor White
    Write-Host "  RECALL_HOST  绑定主机"
    Write-Host "  RECALL_PORT  端口号"
    Write-Host ""
    Write-Host "示例:" -ForegroundColor White
    Write-Host "  .\start.ps1                    # 前台运行"
    Write-Host "  .\start.ps1 -Daemon            # 后台运行"
    Write-Host "  .\start.ps1 -Port 8080         # 指定端口"
    Write-Host "  .\start.ps1 -Daemon -Port 8080 # 后台运行指定端口"
    Write-Host ""
}

# ==================== 主入口 ====================

Set-Location $ScriptDir

if (-not (Test-Installation)) {
    exit 1
}

if ($Help) {
    Show-Help
} elseif ($Stop) {
    Stop-RecallService
} elseif ($Status) {
    Show-Status
} elseif ($Logs) {
    Show-Logs
} elseif ($Restart) {
    Restart-RecallService
} elseif ($Daemon) {
    Start-RecallService -IsDaemon $true
} else {
    Start-RecallService -IsDaemon $false
}
