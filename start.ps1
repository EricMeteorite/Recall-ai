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
        $response = Invoke-WebRequest -Uri "http://localhost:$Port/" -TimeoutSec 2 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# ==================== 加载配置文件 ====================

function Load-ApiKeys {
    $configFile = Join-Path $ScriptDir "recall_data\config\api_keys.env"
    
    # 支持的配置项
    $supportedKeys = @(
        'SILICONFLOW_API_KEY', 'SILICONFLOW_MODEL',
        'OPENAI_API_KEY', 'OPENAI_API_BASE', 'OPENAI_MODEL',
        'EMBEDDING_API_KEY', 'EMBEDDING_API_BASE', 'EMBEDDING_MODEL', 'EMBEDDING_DIMENSION',
        'RECALL_EMBEDDING_MODE'
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
# ============================================
# Recall API 配置文件
# ============================================
# 
# 使用方法：
# 1. 直接用文本编辑器打开此文件
# 2. 填入你需要的配置（三种方式选一种）
# 3. 保存文件
# 4. 热更新: curl -X POST http://localhost:18888/v1/config/reload
# 5. 测试连接: curl http://localhost:18888/v1/config/test
#
# ============================================


# ============================================
# 方式一：硅基流动（推荐国内用户，便宜快速）
# ============================================
# 获取地址：https://cloud.siliconflow.cn/
SILICONFLOW_API_KEY=
# 模型选择（默认 BAAI/bge-large-zh-v1.5）
# 可选: BAAI/bge-large-zh-v1.5, BAAI/bge-m3, BAAI/bge-large-en-v1.5
SILICONFLOW_MODEL=BAAI/bge-large-zh-v1.5


# ============================================
# 方式二：OpenAI（支持官方和中转站）
# ============================================
# 获取地址：https://platform.openai.com/
OPENAI_API_KEY=
# API 地址（默认官方，可改为中转站地址）
OPENAI_API_BASE=
# 模型选择（默认 text-embedding-3-small）
# 可选: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
OPENAI_MODEL=text-embedding-3-small


# ============================================
# 方式三：自定义 API（Azure/Ollama/其他兼容服务）
# ============================================
# 适用于：Azure OpenAI、本地Ollama、其他OpenAI兼容服务
# 注意：需要同时填写 KEY、BASE、MODEL、DIMENSION
EMBEDDING_API_KEY=
EMBEDDING_API_BASE=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=1536


# ============================================
# 常用 Embedding 模型参考
# ============================================
# 
# OpenAI:
#   text-embedding-3-small   维度:1536  推荐,性价比高
#   text-embedding-3-large   维度:3072  精度更高
#   text-embedding-ada-002   维度:1536  旧版本
# 
# 硅基流动:
#   BAAI/bge-large-zh-v1.5   维度:1024  中文推荐
#   BAAI/bge-m3              维度:1024  多语言
#   BAAI/bge-large-en-v1.5   维度:1024  英文
#
# Ollama (本地):
#   nomic-embed-text         维度:768
#   mxbai-embed-large        维度:1024
#
# ============================================
# 模式说明
# ============================================
# 
# 【轻量模式】不需要填写任何配置
#   - 仅使用关键词搜索，无语义搜索
#   - 内存占用最低（~100MB）
# 
# 【Hybrid模式】需要 API 配置（上面三种方式选一种）
#   - 支持语义搜索
#   - 内存占用低（~150MB）
# 
# 【完整模式】不需要填写任何配置
#   - 使用本地模型，完全离线
#   - 内存占用高（~1.5GB）
#
# ============================================
'@
        Set-Content -Path $configFile -Value $defaultConfig -Encoding UTF8
        Write-Host "  $([char]0x2192) 已创建配置文件: $configFile" -ForegroundColor Cyan
    }
}

# ==================== Embedding 模式检测 ====================

function Get-EmbeddingMode {
    $modeFile = Join-Path $ScriptDir "recall_data\config\install_mode"
    
    if (Test-Path $modeFile) {
        $installMode = Get-Content $modeFile -ErrorAction SilentlyContinue
        switch ($installMode) {
            "lightweight" { return "none" }
            "hybrid" {
                # Hybrid 模式需要检查 API Key
                # 优先检查自定义配置
                if ($env:EMBEDDING_API_KEY -and $env:EMBEDDING_API_BASE) {
                    return "custom"
                } elseif ($env:SILICONFLOW_API_KEY) {
                    return "siliconflow"
                } elseif ($env:OPENAI_API_KEY) {
                    return "openai"
                } else {
                    return "api_required"
                }
            }
            "full" { return "local" }
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
    Load-ApiKeys
    
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
    
    # 检查 Hybrid 模式是否配置了 API Key
    if ($embeddingMode -eq "api_required") {
        Write-Error2 "Hybrid 模式需要配置 API Key"
        Write-Host ""
        Write-Host "  请编辑配置文件: " -NoNewline
        Write-Host "recall_data\config\api_keys.env" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  或设置以下环境变量之一：" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  OpenAI:" -ForegroundColor White
        Write-Host "    " -NoNewline; Write-Host '$env:OPENAI_API_KEY = "sk-xxx"' -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  硅基流动 (推荐国内用户):" -ForegroundColor White
        Write-Host "    " -NoNewline; Write-Host '$env:SILICONFLOW_API_KEY = "sf-xxx"' -ForegroundColor Cyan
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
        "none" { Write-Info "Embedding: 轻量模式 (仅关键词搜索)" }
        "openai" { Write-Success "Embedding: Hybrid-OpenAI (API 语义搜索)" }
        "siliconflow" { Write-Success "Embedding: Hybrid-硅基流动 (API 语义搜索)" }
        "local" { Write-Success "Embedding: 完整模式 (本地模型)" }
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
