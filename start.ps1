<# 
    Recall AI - Windows 一键启动脚本
    
    双击运行或在 PowerShell 中执行: .\start.ps1
#>

$Host.UI.RawUI.WindowTitle = "Recall AI Server"

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

Write-Host "API 地址: http://127.0.0.1:18888" -ForegroundColor Green
Write-Host "API 文档: http://127.0.0.1:18888/docs" -ForegroundColor Green
Write-Host ""
Write-Host "按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host ""

& $recallPath serve
