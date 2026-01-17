<#
.SYNOPSIS
    Recall AI - Windows 安装脚本 v2.0

.DESCRIPTION
    功能：
    - 可视化进度显示
    - 支持国内镜像加速
    - 安装失败自动清理
    - 支持重装、修复、卸载

.EXAMPLE
    .\install.ps1              # 交互式菜单
    .\install.ps1 -Mirror      # 使用国内镜像
    .\install.ps1 -Repair      # 修复安装
    .\install.ps1 -Uninstall   # 卸载
    .\install.ps1 -Status      # 查看状态
#>

param(
    [switch]$Mirror,
    [switch]$Repair,
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Recall AI 安装程序"

# ==================== 全局变量 ====================
$ScriptDir = $PSScriptRoot
$VenvPath = Join-Path $ScriptDir "recall-env"
$DataPath = Join-Path $ScriptDir "recall_data"
$PipMirror = ""
$InstallSuccess = $false
$VenvCreated = $false
$InstallMode = "full"  # lightweight, hybrid, full

# ==================== 工具函数 ====================

function Write-Header {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║       Recall AI v3.0.0 安装程序           ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([int]$Current, [int]$Total, [string]$Message)
    Write-Host "[$Current/$Total] " -ForegroundColor Blue -NoNewline
    Write-Host $Message -ForegroundColor White
}

function Write-Success {
    param([string]$Message)
    Write-Host "    ✓ " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Error2 {
    param([string]$Message)
    Write-Host "    ✗ " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Write-Warning2 {
    param([string]$Message)
    Write-Host "    ! " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Info {
    param([string]$Message)
    Write-Host "    → " -ForegroundColor Cyan -NoNewline
    Write-Host $Message
}

# ==================== 清理函数 ====================

function Invoke-Cleanup {
    if (-not $InstallSuccess -and $VenvCreated) {
        Write-Host ""
        Write-Error2 "安装失败，正在清理..."
        
        if (Test-Path $VenvPath) {
            Remove-Item -Recurse -Force $VenvPath -ErrorAction SilentlyContinue
            Write-Info "已删除虚拟环境"
        }
        
        Write-Host ""
        Write-Host "请检查以下常见问题：" -ForegroundColor Yellow
        Write-Host "  1. 网络连接是否正常"
        Write-Host "  2. 磁盘空间是否充足 (需要约 2GB)"
        Write-Host "  3. Python 版本是否 >= 3.10"
        Write-Host ""
        Write-Host "重试安装: " -NoNewline
        Write-Host ".\install.ps1" -ForegroundColor Cyan
        Write-Host "使用国内镜像: " -NoNewline
        Write-Host ".\install.ps1 -Mirror" -ForegroundColor Cyan
    }
}

# ==================== 菜单函数 ====================

function Show-ModeSelection {
    Write-Host ""
    Write-Host "请选择安装模式：" -ForegroundColor White
    Write-Host ""
    Write-Host "  1) " -NoNewline; Write-Host "轻量模式" -ForegroundColor Green -NoNewline; Write-Host "     ~100MB 内存，仅关键词搜索"
    Write-Host "     适合: 内存 < 1GB 的服务器" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  2) " -NoNewline; Write-Host "Hybrid模式" -ForegroundColor Green -NoNewline; Write-Host "   ~150MB 内存，使用云端API进行向量搜索 " -NoNewline; Write-Host "★推荐★" -ForegroundColor Yellow
    Write-Host "     适合: 任何服务器，全功能，需要API Key" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  3) " -NoNewline; Write-Host "完整模式" -ForegroundColor Green -NoNewline; Write-Host "     ~1.5GB 内存，本地向量模型"
    Write-Host "     适合: 高配服务器，完全离线" -ForegroundColor Cyan
    Write-Host ""
    
    $modeChoice = Read-Host "请选择 [1-3，默认2]"
    
    switch ($modeChoice) {
        "1" { $script:InstallMode = "lightweight" }
        "3" { $script:InstallMode = "full" }
        default { $script:InstallMode = "hybrid" }
    }
    
    Write-Host ""
    Write-Host "已选择: " -NoNewline
    Write-Host "$($script:InstallMode)" -ForegroundColor Green -NoNewline
    Write-Host " 模式"
    Write-Host ""
}

function Show-Menu {
    Write-Host "请选择操作：" -ForegroundColor White
    Write-Host ""
    Write-Host "  1) 全新安装"
    Write-Host "  2) 全新安装 (使用国内镜像加速) " -NoNewline
    Write-Host "推荐" -ForegroundColor Green
    Write-Host "  3) 修复/重装依赖"
    Write-Host "  4) 完全卸载"
    Write-Host "  5) 查看状态"
    Write-Host "  6) 退出"
    Write-Host ""
    
    $choice = Read-Host "请输入选项 [1-6]"
    
    switch ($choice) {
        "1" { Show-ModeSelection; Invoke-Install }
        "2" { Show-ModeSelection; $script:PipMirror = "-i https://pypi.tuna.tsinghua.edu.cn/simple"; Invoke-Install }
        "3" { Invoke-Repair }
        "4" { Invoke-Uninstall }
        "5" { Show-Status }
        "6" { exit 0 }
        default { 
            Write-Host "无效选项" -ForegroundColor Red
            Write-Host ""
            Show-Menu 
        }
    }
}

# ==================== 检查 Python ====================

function Test-Python {
    Write-Step 1 5 "检查 Python 环境"
    
    $pythonCmd = $null
    $pythonVersion = $null
    
    # 优先使用 py launcher
    try {
        $ver = & py -3.12 --version 2>&1
        if ($ver -match "Python 3\.12") {
            $script:PythonCmd = "py"
            $script:PythonArgs = @("-3.12")
            $pythonVersion = $ver
        }
    } catch {}
    
    # 其次尝试 py launcher 自动选择
    if (-not $pythonVersion) {
        try {
            $ver = & py --version 2>&1
            if ($ver -match "Python 3\.(\d+)") {
                $minor = [int]$Matches[1]
                if ($minor -ge 10) {
                    $script:PythonCmd = "py"
                    $script:PythonArgs = @()
                    $pythonVersion = $ver
                }
            }
        } catch {}
    }
    
    # 最后尝试 python 命令
    if (-not $pythonVersion) {
        try {
            $ver = & python --version 2>&1
            if ($ver -match "Python 3\.(\d+)") {
                $minor = [int]$Matches[1]
                if ($minor -ge 10) {
                    $script:PythonCmd = "python"
                    $script:PythonArgs = @()
                    $pythonVersion = $ver
                }
            }
        } catch {}
    }
    
    if (-not $pythonVersion) {
        Write-Error2 "未找到 Python 3.10+"
        Write-Host ""
        Write-Host "  请先安装 Python 3.10 或更高版本：" -ForegroundColor Yellow
        Write-Host "    下载地址: https://www.python.org/downloads/"
        Write-Host ""
        Read-Host "按 Enter 退出"
        exit 1
    }
    
    Write-Success "找到 $pythonVersion"
}

# ==================== 创建虚拟环境 ====================

function New-VirtualEnv {
    Write-Step 2 5 "创建虚拟环境"
    
    if (Test-Path $VenvPath) {
        Write-Warning2 "虚拟环境已存在"
        $confirm = Read-Host "    是否删除并重新创建? [y/N]"
        if ($confirm -match "^[Yy]$") {
            Remove-Item -Recurse -Force $VenvPath
            Write-Info "已删除旧虚拟环境"
        } else {
            Write-Info "使用现有虚拟环境"
            return
        }
    }
    
    Write-Info "创建中..."
    
    if ($PythonArgs.Count -gt 0) {
        & $PythonCmd @PythonArgs -m venv $VenvPath
    } else {
        & $PythonCmd -m venv $VenvPath
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "创建虚拟环境失败"
    }
    
    $script:VenvCreated = $true
    Write-Success "虚拟环境创建成功"
}

# ==================== 安装依赖 ====================

function Install-Dependencies {
    Write-Step 3 5 "安装依赖"
    
    $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
    
    Write-Host ""
    if ($PipMirror) {
        Write-Host "    ✓ 使用国内镜像加速 (清华源)" -ForegroundColor Green
    } else {
        Write-Host "    ! 使用默认源，如果较慢可用 -Mirror 参数" -ForegroundColor Yellow
    }
    
    # 根据模式显示预计大小
    switch ($InstallMode) {
        "lightweight" {
            Write-Host "    ℹ 轻量模式：下载约 300MB 依赖" -ForegroundColor Cyan
            Write-Host "    ℹ 预计需要 3-5 分钟" -ForegroundColor Cyan
        }
        "hybrid" {
            Write-Host "    ℹ Hybrid模式：下载约 400MB 依赖" -ForegroundColor Cyan
            Write-Host "    ℹ 预计需要 5-8 分钟" -ForegroundColor Cyan
        }
        "full" {
            Write-Host "    ℹ 完整模式：下载约 1.5GB 依赖 (包含 PyTorch)" -ForegroundColor Cyan
            Write-Host "    ℹ 预计需要 10-20 分钟" -ForegroundColor Cyan
        }
    }
    Write-Host ""
    
    # 升级 pip
    Write-Info "升级 pip..."
    $pipArgs = @("install", "--upgrade", "pip", "-q")
    if ($PipMirror) { $pipArgs += $PipMirror.Split(" ") }
    & $pipPath @pipArgs 2>$null
    Write-Success "pip 升级完成"
    
    # 安装项目依赖
    Write-Info "安装项目依赖..."
    Write-Host ""
    
    # 根据模式安装不同依赖
    $extras = ""
    switch ($InstallMode) {
        "lightweight" { 
            $extras = ""
            Write-Info "安装轻量依赖..."
        }
        "hybrid" { 
            $extras = "[hybrid]"
            Write-Info "安装 Hybrid 依赖 (FAISS)..."
        }
        "full" { 
            $extras = "[full]"
            Write-Info "安装完整依赖 (sentence-transformers + FAISS)..."
        }
    }
    
    $pipArgs = @("install", "-e", "$ScriptDir$extras")
    if ($PipMirror) { $pipArgs += $PipMirror.Split(" ") }
    
    # 实时显示进度
    $process = Start-Process -FilePath $pipPath -ArgumentList $pipArgs -NoNewWindow -PassThru -RedirectStandardOutput "$env:TEMP\pip_out.txt" -RedirectStandardError "$env:TEMP\pip_err.txt"
    
    $lastSize = 0
    while (-not $process.HasExited) {
        Start-Sleep -Milliseconds 500
        if (Test-Path "$env:TEMP\pip_out.txt") {
            $content = Get-Content "$env:TEMP\pip_out.txt" -Raw -ErrorAction SilentlyContinue
            if ($content -and $content.Length -gt $lastSize) {
                $newContent = $content.Substring($lastSize)
                $lastSize = $content.Length
                
                # 解析并显示
                $lines = $newContent -split "`n"
                foreach ($line in $lines) {
                    if ($line -match "Collecting (.+)") {
                        Write-Host "    📦 收集: $($Matches[1].Split(' ')[0])" -ForegroundColor Cyan
                    } elseif ($line -match "Downloading") {
                        Write-Host "    ↓  下载中..." -ForegroundColor Cyan
                    } elseif ($line -match "Successfully installed") {
                        Write-Host "    ✓  安装成功" -ForegroundColor Green
                    }
                }
            }
        }
    }
    
    # 清理临时文件
    Remove-Item "$env:TEMP\pip_out.txt" -ErrorAction SilentlyContinue
    Remove-Item "$env:TEMP\pip_err.txt" -ErrorAction SilentlyContinue
    
    Write-Host ""
    
    # 验证安装
    $recallPath = Join-Path $VenvPath "Scripts\recall.exe"
    if (Test-Path $recallPath) {
        $ver = & $recallPath --version 2>&1
        Write-Success "依赖安装完成 ($ver)"
    } else {
        Write-Error2 "依赖安装可能不完整"
        throw "安装验证失败"
    }
}

# ==================== 下载模型 ====================

function Install-Models {
    Write-Step 4 5 "下载 NLP 模型"
    
    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    
    Write-Info "下载 spaCy 中文模型 (约 50MB)..."
    
    $args = @("-m", "spacy", "download", "zh_core_web_sm")
    if ($PipMirror) { $args += $PipMirror.Split(" ") }
    
    & $pythonPath @args 2>&1 | Out-Null
    
    Write-Success "spaCy 中文模型下载完成"
}

# ==================== 初始化 ====================

function Initialize-Recall {
    Write-Step 5 5 "初始化 Recall"
    
    $recallPath = Join-Path $VenvPath "Scripts\recall.exe"
    
    Write-Info "运行初始化..."
    
    # 根据模式初始化
    switch ($InstallMode) {
        "lightweight" {
            & $recallPath init --lightweight 2>&1 | Out-Null
        }
        default {
            & $recallPath init 2>&1 | Out-Null
        }
    }
    
    # 创建数据目录
    $dirs = @("data", "logs", "cache", "models", "config", "temp")
    foreach ($dir in $dirs) {
        $path = Join-Path $DataPath $dir
        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
    
    # 保存安装模式
    $modePath = Join-Path $DataPath "config\install_mode"
    Set-Content -Path $modePath -Value $InstallMode
    
    Write-Success "初始化完成"
}

# ==================== 安装流程 ====================

function Invoke-Install {
    try {
        Write-Header
        
        Write-Step 0 5 "准备安装"
        Write-Success "目录: $ScriptDir"
        
        Test-Python
        New-VirtualEnv
        Install-Dependencies
        Install-Models
        Initialize-Recall
        
        $script:InstallSuccess = $true
        
        Write-Host ""
        Write-Host "╔════════════════════════════════════════════╗" -ForegroundColor Green
        Write-Host "║           🎉 安装成功！                     ║" -ForegroundColor Green
        Write-Host "╚════════════════════════════════════════════╝" -ForegroundColor Green
        Write-Host ""
        
        # 根据模式显示不同提示
        switch ($InstallMode) {
            "lightweight" {
                Write-Host "  安装模式: " -NoNewline; Write-Host "轻量模式" -ForegroundColor Cyan
                Write-Host "  " -NoNewline; Write-Host "注意: 轻量模式仅支持关键词搜索，无语义搜索" -ForegroundColor Yellow
            }
            "hybrid" {
                Write-Host "  安装模式: " -NoNewline; Write-Host "Hybrid模式" -ForegroundColor Cyan
                Write-Host ""
                Write-Host "  ⚠ 重要: 启动前需要配置 API Key!" -ForegroundColor Yellow
                Write-Host ""
                Write-Host "  支持的 API 提供商:"
                Write-Host "    - 硅基流动 (BAAI/bge-large-zh-v1.5) " -NoNewline; Write-Host "推荐国内用户" -ForegroundColor Green
                Write-Host "    - OpenAI (text-embedding-3-small)"
                Write-Host "    - 自定义 API (Azure/Ollama 等)"
                Write-Host ""
                Write-Host "  配置方法:"
                Write-Host "    1. 启动服务后会自动生成配置文件"
                Write-Host "    2. 编辑: " -NoNewline; Write-Host "recall_data\config\api_keys.env" -ForegroundColor Cyan
                Write-Host "    3. 热更新: " -NoNewline; Write-Host "curl -X POST http://localhost:18888/v1/config/reload" -ForegroundColor Cyan
            }
            "full" {
                Write-Host "  安装模式: " -NoNewline; Write-Host "完整模式" -ForegroundColor Cyan
                Write-Host "  " -NoNewline; Write-Host "✓ 本地模型，无需API Key，完全离线运行" -ForegroundColor Green
            }
        }
        
        Write-Host ""
        Write-Host "  启动服务:" -ForegroundColor White
        Write-Host "    前台运行: " -NoNewline; Write-Host ".\start.ps1" -ForegroundColor Cyan
        Write-Host "    后台运行: " -NoNewline; Write-Host ".\start.ps1 -Daemon" -ForegroundColor Cyan
        Write-Host "    停止服务: " -NoNewline; Write-Host ".\start.ps1 -Stop" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  安装 SillyTavern 插件:" -ForegroundColor White
        Write-Host "    " -NoNewline; Write-Host "cd plugins\sillytavern; .\install.ps1" -ForegroundColor Cyan
        Write-Host ""
        
    } catch {
        Write-Host ""
        Write-Error2 "安装过程中发生错误: $_"
        Invoke-Cleanup
    } finally {
        if (-not $InstallSuccess) {
            Invoke-Cleanup
        }
    }
    
    Read-Host "按 Enter 退出"
}

# ==================== 修复安装 ====================

function Invoke-Repair {
    Write-Header
    Write-Host "🔧 修复/重装依赖" -ForegroundColor Yellow
    Write-Host ""
    
    if (-not (Test-Path $VenvPath)) {
        Write-Error2 "虚拟环境不存在，请先完整安装"
        Write-Host ""
        $confirm = Read-Host "是否现在安装? [Y/n]"
        if ($confirm -notmatch "^[Nn]$") {
            Invoke-Install
        }
        return
    }
    
    $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
    
    Write-Host "选择修复方式:"
    Write-Host "  1) 快速修复 (只更新 recall)"
    Write-Host "  2) 完整重装 (重新安装所有依赖)"
    Write-Host ""
    $choice = Read-Host "请选择 [1/2]"
    
    switch ($choice) {
        "1" {
            Write-Info "快速修复中..."
            $args = @("install", "-e", $ScriptDir, "--upgrade")
            if ($PipMirror) { $args += $PipMirror.Split(" ") }
            & $pipPath @args
        }
        "2" {
            Write-Info "完整重装中..."
            $args = @("install", "-e", $ScriptDir, "--force-reinstall")
            if ($PipMirror) { $args += $PipMirror.Split(" ") }
            & $pipPath @args
        }
        default {
            Write-Error2 "无效选项"
            return
        }
    }
    
    $script:InstallSuccess = $true
    Write-Host ""
    Write-Success "修复完成！"
    Read-Host "按 Enter 退出"
}

# ==================== 卸载 ====================

function Invoke-Uninstall {
    Write-Header
    Write-Host "🗑️  完全卸载" -ForegroundColor Red
    Write-Host ""
    
    Write-Host "警告: 这将删除以下内容：" -ForegroundColor Yellow
    Write-Host "  - 虚拟环境 (recall-env\)"
    Write-Host "  - 所有数据 (recall_data\)"
    Write-Host "  - 临时文件"
    Write-Host ""
    $confirm = Read-Host "确定要卸载吗? 输入 'yes' 确认"
    
    if ($confirm -eq "yes") {
        if (Test-Path $VenvPath) {
            Write-Info "删除虚拟环境..."
            Remove-Item -Recurse -Force $VenvPath
        }
        
        if (Test-Path $DataPath) {
            Write-Info "删除数据目录..."
            Remove-Item -Recurse -Force $DataPath
        }
        
        $pidFile = Join-Path $ScriptDir "recall.pid"
        if (Test-Path $pidFile) {
            Remove-Item -Force $pidFile
        }
        
        $script:InstallSuccess = $true
        Write-Host ""
        Write-Success "卸载完成！"
        Write-Host ""
        Write-Host "如需重新安装，运行: .\install.ps1"
    } else {
        Write-Info "已取消卸载"
    }
    
    Read-Host "按 Enter 退出"
}

# ==================== 状态检查 ====================

function Show-Status {
    Write-Header
    Write-Host "📊 系统状态" -ForegroundColor White
    Write-Host ""
    
    # 虚拟环境
    if (Test-Path $VenvPath) {
        Write-Success "虚拟环境: 已安装"
    } else {
        Write-Error2 "虚拟环境: 未安装"
    }
    
    # Recall 版本
    $recallPath = Join-Path $VenvPath "Scripts\recall.exe"
    if (Test-Path $recallPath) {
        $ver = & $recallPath --version 2>&1
        Write-Success "Recall: $ver"
    } else {
        Write-Error2 "Recall: 未安装"
    }
    
    # 数据目录
    if (Test-Path $DataPath) {
        $size = (Get-ChildItem -Path $DataPath -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeStr = if ($size -gt 1GB) { "{0:N2} GB" -f ($size / 1GB) } 
                   elseif ($size -gt 1MB) { "{0:N2} MB" -f ($size / 1MB) }
                   else { "{0:N2} KB" -f ($size / 1KB) }
        Write-Success "数据目录: $sizeStr"
    } else {
        Write-Warning2 "数据目录: 未创建"
    }
    
    # 服务状态
    $pidFile = Join-Path $ScriptDir "recall.pid"
    if (Test-Path $pidFile) {
        $pid = Get-Content $pidFile
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Success "服务状态: 运行中 (PID: $pid)"
        } else {
            Write-Warning2 "服务状态: 已停止 (残留PID文件)"
        }
    } else {
        Write-Info "服务状态: 未运行"
    }
    
    # API 检查
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:18888/" -TimeoutSec 2 -ErrorAction Stop
        Write-Success "API 响应: 正常"
    } catch {
        Write-Info "API 响应: 无法连接"
    }
    
    Write-Host ""
    Read-Host "按 Enter 返回菜单"
    Write-Host ""
    Show-Menu
}

# ==================== 显示帮助 ====================

function Show-Help {
    Write-Header
    Write-Host "用法: .\install.ps1 [选项]"
    Write-Host ""
    Write-Host "选项:"
    Write-Host "  (无参数)     显示交互式菜单"
    Write-Host "  -Mirror      使用国内镜像安装"
    Write-Host "  -Repair      修复/重装依赖"
    Write-Host "  -Uninstall   完全卸载"
    Write-Host "  -Status      查看系统状态"
    Write-Host "  -Help        显示帮助"
    Write-Host ""
}

# ==================== 主入口 ====================

Set-Location $ScriptDir

if ($Help) {
    Show-Help
} elseif ($Mirror) {
    $PipMirror = "-i https://pypi.tuna.tsinghua.edu.cn/simple"
    Invoke-Install
} elseif ($Repair) {
    Invoke-Repair
} elseif ($Uninstall) {
    Invoke-Uninstall
} elseif ($Status) {
    Show-Status
} else {
    Write-Header
    Show-Menu
}
