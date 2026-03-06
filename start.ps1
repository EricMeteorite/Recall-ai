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
    Write-Host "|          Recall AI v7.0.0 Server          |" -ForegroundColor Cyan
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
            if ($proc -and ($proc.ProcessName -like "*python*" -or $proc.ProcessName -like "*recall*")) {
                return $proc
            }
        }
    }
    return $null
}

function Test-ApiHealth {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:${Port}/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
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
        'TURN_API_ENABLED',
        # ====== v5.0 全局模式与重排序配置 ======
        'RECALL_MODE', 'FORESHADOWING_ENABLED', 'CHARACTER_DIMENSION_ENABLED',
        'RP_CONSISTENCY_ENABLED', 'RP_RELATION_TYPES', 'RP_CONTEXT_TYPES',
        'RERANKER_BACKEND', 'COHERE_API_KEY', 'RERANKER_MODEL',
        # ====== v7.0 服务器与安全配置 ======
        'ADMIN_KEY', 'RECALL_BACKEND_TIER', 'RECALL_CORS_ORIGINS',
        'RECALL_CORS_METHODS', 'RECALL_RATE_LIMIT_RPM',
        'MCP_TRANSPORT', 'MCP_PORT',
        # ====== v7.0 日志/管道/生命周期/国际化 ======
        'RECALL_DATA_ROOT', 'RECALL_LOG_LEVEL', 'RECALL_LOG_JSON', 'RECALL_LOG_FILE',
        'RECALL_PIPELINE_MAX_SIZE', 'RECALL_PIPELINE_RATE_LIMIT', 'RECALL_PIPELINE_WORKERS',
        'RECALL_LANG',
        'RECALL_LIFECYCLE_ARCHIVE_DAYS', 'RECALL_LIFECYCLE_BACKUP_ENABLED',
        'RECALL_LIFECYCLE_BACKUP_DIR', 'RECALL_LIFECYCLE_CLEANUP_TEMP',
        'IVF_AUTO_SWITCH_ENABLED', 'IVF_AUTO_SWITCH_THRESHOLD',
        'PARALLEL_RETRIEVER_WORKERS', 'PARALLEL_RETRIEVER_TIMEOUT'
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
        
        $templateFile = Join-Path $ScriptDir "recall\config_template.env"
        if (Test-Path $templateFile) {
            $defaultConfig = Get-Content $templateFile -Raw -Encoding UTF8
        } else {
            Write-Host "  [ERROR] Template file not found: $templateFile" -ForegroundColor Red
            return
        }
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
