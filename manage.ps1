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
                $templateFile = Join-Path $ScriptDir "recall\config_template.env"
                if (Test-Path $templateFile) {
                    $defaultConfig = Get-Content $templateFile -Raw -Encoding UTF8
                } else {
                    Write-Host "  [ERROR] Template file not found: $templateFile" -ForegroundColor Red
                    return
                }
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
    # v7.0: L1_consolidated 和 knowledge_graph 均在 data/ 内，删除 data/ 时自动覆盖
    
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
        Write-Host "    [x] indexes/        - 综合索引（元数据/向量/全文等） ($sizeStr)" -ForegroundColor Red
        $toDelete += $indexesDir
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
    
    # Recreate empty directories (skip files like knowledge_graph.json)
    foreach ($dir in $toDelete) {
        if ($dir -notmatch '\.[a-zA-Z]+$') {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
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
    }
    
    # 从统一模板重新生成配置文件
    $templateFile = Join-Path $SCRIPT_DIR "recall\config_template.env"
    $configDir = Split-Path $configFile -Parent
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }
    if (Test-Path $templateFile) {
        $content = Get-Content $templateFile -Raw -Encoding UTF8
        Set-Content -Path $configFile -Value $content -Encoding UTF8
        Write-Success "配置已重置（已从模板重新生成）"
        Write-Info "配置文件: $configFile"
    } else {
        Write-Success "配置已删除"
        Write-Info "下次启动服务时将自动重新生成"
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
