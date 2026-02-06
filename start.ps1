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

# 设置控制台编码为 UTF-8，解决中文乱码问题
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

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
    Write-Host "|          Recall AI v4.2.0 Server          |" -ForegroundColor Cyan
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
        'LLM_API_KEY', 'LLM_API_BASE', 'LLM_MODEL', 'LLM_TIMEOUT',
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
        'TEMPORAL_GRAPH_ENABLED', 'TEMPORAL_GRAPH_BACKEND', 'KUZU_BUFFER_POOL_SIZE',
        'TEMPORAL_DECAY_RATE', 'TEMPORAL_MAX_HISTORY',
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
        'RETRIEVAL_WEIGHT_NGRAM', 'RETRIEVAL_WEIGHT_VECTOR', 'RETRIEVAL_WEIGHT_TEMPORAL',
        # ====== v4.0 Phase 3.5 QueryPlanner & CommunityDetector 配置 ======
        'QUERY_PLANNER_ENABLED', 'QUERY_PLANNER_CACHE_SIZE', 'QUERY_PLANNER_CACHE_TTL',
        'COMMUNITY_DETECTION_ENABLED', 'COMMUNITY_DETECTION_ALGORITHM', 'COMMUNITY_MIN_SIZE',
        # ====== v4.0 Phase 3.6 三路并行召回配置（100%不遗忘保证）======
        # Triple Recall 主开关与 RRF 融合
        'TRIPLE_RECALL_ENABLED', 'TRIPLE_RECALL_RRF_K',
        'TRIPLE_RECALL_VECTOR_WEIGHT', 'TRIPLE_RECALL_KEYWORD_WEIGHT', 'TRIPLE_RECALL_ENTITY_WEIGHT',
        # IVF-HNSW 向量索引参数
        'VECTOR_IVF_HNSW_M', 'VECTOR_IVF_HNSW_EF_CONSTRUCTION', 'VECTOR_IVF_HNSW_EF_SEARCH',
        # 原文兜底配置
        'FALLBACK_ENABLED', 'FALLBACK_PARALLEL', 'FALLBACK_WORKERS', 'FALLBACK_MAX_RESULTS',
        # ====== v4.1 增强功能配置 ======
        # LLM 关系提取配置
        'LLM_RELATION_MODE', 'LLM_RELATION_COMPLEXITY_THRESHOLD',
        'LLM_RELATION_ENABLE_TEMPORAL', 'LLM_RELATION_ENABLE_FACT_DESCRIPTION',
        # 实体摘要配置
        'ENTITY_SUMMARY_ENABLED', 'ENTITY_SUMMARY_MIN_FACTS',
        # Episode 追溯配置
        'EPISODE_TRACKING_ENABLED',
        # ====== v4.1 LLM Max Tokens 配置 ======
        'LLM_DEFAULT_MAX_TOKENS', 'LLM_RELATION_MAX_TOKENS', 'FORESHADOWING_MAX_TOKENS',
        'CONTEXT_EXTRACTION_MAX_TOKENS', 'ENTITY_SUMMARY_MAX_TOKENS', 'SMART_EXTRACTOR_MAX_TOKENS',
        'CONTRADICTION_MAX_TOKENS', 'BUILD_CONTEXT_MAX_TOKENS', 'RETRIEVAL_LLM_MAX_TOKENS',
        'DEDUP_LLM_MAX_TOKENS',
        # ====== v4.2 性能优化配置 ======
        'EMBEDDING_REUSE_ENABLED', 'UNIFIED_ANALYZER_ENABLED', 'UNIFIED_ANALYSIS_MAX_TOKENS',
        'TURN_API_ENABLED'
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
        
        # 等待服务真正可用（最多 60 秒）
        Write-Host "  启动中" -NoNewline
        $maxWait = 60
        $waited = 0
        $started = $false
        
        while ($waited -lt $maxWait) {
            Start-Sleep -Seconds 2
            $waited += 2
            Write-Host "." -NoNewline
            
            # 检查进程是否还存在
            $running = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
            if (-not $running) {
                Write-Host ""
                Write-Error2 "启动失败！进程已退出"
                Write-Host ""
                Write-Host "  查看错误日志:" -ForegroundColor Yellow
                Write-Host "    Get-Content '$LogDir\recall_error.log' -Tail 20" -ForegroundColor Cyan
                Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
                return
            }
            
            # 检查服务是否可用
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
                if ($response.StatusCode -eq 200) {
                    $started = $true
                    break
                }
            } catch {
                # 继续等待
            }
        }
        
        Write-Host ""
        
        if ($started) {
            Write-Success "启动成功! (${waited}秒)"
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
            Write-Warning "启动超时，但进程仍在运行 (PID: $($proc.Id))"
            Write-Info "服务可能正在加载模型，请稍后检查状态"
            Write-Host ""
            Write-Host "    查看状态: .\start.ps1 -Status" -ForegroundColor Cyan
            Write-Host "    查看日志: .\start.ps1 -Logs" -ForegroundColor Cyan
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
