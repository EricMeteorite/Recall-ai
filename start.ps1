<# 
    Recall AI - Windows 一键启动脚本
    
    使用方法：
    .\start.ps1              # 前台运行
    .\start.ps1 -Daemon      # 后台运行
    .\start.ps1 -Stop        # 停止服务
#>

param(
    [switch]$Daemon,
    [switch]$Stop,
    [string]$Host = "0.0.0.0",
    [int]$Port = 18888
)

$Host.UI.RawUI.WindowTitle = "Recall AI Server"
$PidFile = Join-Path $PSScriptRoot "recall.pid"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "         Recall AI v3.0.0              " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$recallPath = Join-Path $PSScriptRoot "recall-env\Scripts\recall.exe"

if (-not (Test-Path $recallPath)) {
    Write-Host "错误: 请先运行 install.ps1 安装" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# 停止服务
if ($Stop) {
    if (Test-Path $PidFile) {
        $pid = Get-Content $PidFile
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Remove-Item $PidFile -Force
            Write-Host "服务已停止" -ForegroundColor Green
        } catch {
            Write-Host "服务未运行" -ForegroundColor Yellow
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "服务未运行" -ForegroundColor Yellow
    }
    exit 0
}

# 检查是否已运行
if (Test-Path $PidFile) {
    $existingPid = Get-Content $PidFile
    $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "服务已在运行 (PID: $existingPid)" -ForegroundColor Yellow
        Write-Host "使用 .\start.ps1 -Stop 停止服务" -ForegroundColor Gray
        exit 1
    }
}

Write-Host "API 地址: http://${Host}:${Port}" -ForegroundColor Green
Write-Host "API 文档: http://${Host}:${Port}/docs" -ForegroundColor Green
Write-Host ""

# 后台运行
if ($Daemon) {
    Write-Host "后台启动中..." -ForegroundColor Yellow
    $proc = Start-Process -FilePath $recallPath -ArgumentList "serve","--host",$Host,"--port",$Port -PassThru -WindowStyle Hidden
    $proc.Id | Out-File $PidFile
    Start-Sleep -Seconds 2
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
        Write-Host "启动成功! PID: $($proc.Id)" -ForegroundColor Green
        Write-Host "停止命令: .\start.ps1 -Stop" -ForegroundColor Gray
    } else {
        Write-Host "启动失败" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "前台运行模式，按 Ctrl+C 停止服务" -ForegroundColor Gray
    Write-Host ""
    & $recallPath serve --host $Host --port $Port
}
