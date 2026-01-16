<# 
    Recall AI - Windows 一键安装脚本
    
    使用方法：
    1. 右键点击此文件，选择"使用 PowerShell 运行"
    2. 或在 PowerShell 中执行: .\install.ps1
#>

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Recall AI 安装程序"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       Recall AI v3.0.0 安装程序       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
Write-Host "[1/4] 检查 Python 环境..." -ForegroundColor Yellow

$pythonCmd = $null
$pythonVersion = $null

# 优先使用 py launcher 指定 3.12
try {
    $ver = & py -3.12 --version 2>&1
    if ($ver -match "Python 3\.12") {
        $pythonCmd = "py -3.12"
        $pythonVersion = $ver
    }
} catch {}

# 其次尝试 py launcher 自动选择
if (-not $pythonCmd) {
    try {
        $ver = & py --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $pythonCmd = "py"
                $pythonVersion = $ver
            }
        }
    } catch {}
}

# 最后尝试 python 命令
if (-not $pythonCmd) {
    try {
        $ver = & python --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $pythonCmd = "python"
                $pythonVersion = $ver
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "错误: 未找到 Python 3.10+ 请先安装 Python" -ForegroundColor Red
    Write-Host "下载地址: https://www.python.org/downloads/" -ForegroundColor Gray
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host "  找到 $pythonVersion" -ForegroundColor Green

# 创建虚拟环境
Write-Host ""
Write-Host "[2/4] 创建虚拟环境..." -ForegroundColor Yellow

$venvPath = Join-Path $PSScriptRoot "recall-env"

if (Test-Path $venvPath) {
    Write-Host "  虚拟环境已存在，跳过创建" -ForegroundColor Gray
} else {
    Write-Host "  创建中，请稍候..."
    & $pythonCmd -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误: 创建虚拟环境失败" -ForegroundColor Red
        Read-Host "按 Enter 退出"
        exit 1
    }
    Write-Host "  虚拟环境创建成功" -ForegroundColor Green
}

# 安装依赖
Write-Host ""
Write-Host "[3/4] 安装依赖（可能需要几分钟）..." -ForegroundColor Yellow

$pipPath = Join-Path $venvPath "Scripts\pip.exe"

# 升级 pip
& $pipPath install --upgrade pip -q 2>$null

# 安装项目
& $pipPath install -e $PSScriptRoot -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 安装依赖失败" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host "  依赖安装完成" -ForegroundColor Green

# 初始化
Write-Host ""
Write-Host "[4/4] 初始化 Recall..." -ForegroundColor Yellow

$recallPath = Join-Path $venvPath "Scripts\recall.exe"
& $recallPath init --lightweight 2>$null

Write-Host "  初始化完成" -ForegroundColor Green

# 完成
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "           安装成功！                  " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "启动方式:" -ForegroundColor Cyan
Write-Host "  双击 start.ps1 或运行:" -ForegroundColor White
Write-Host "  .\start.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "安装 SillyTavern 插件:" -ForegroundColor Cyan
Write-Host "  进入 plugins\sillytavern 目录运行 install.ps1" -ForegroundColor White
Write-Host ""

Read-Host "按 Enter 退出"
