<# 
    Recall AI - SillyTavern 插件安装脚本
    
    使用方法：
    1. 右键点击此文件，选择"使用 PowerShell 运行"
    2. 按提示输入你的 SillyTavern 路径
#>

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Recall - SillyTavern 插件安装"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Recall - SillyTavern 插件安装       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 插件源目录（当前脚本所在目录）
$pluginSource = $PSScriptRoot

# 常见的 SillyTavern 路径
$commonPaths = @(
    "$env:USERPROFILE\SillyTavern",
    "$env:USERPROFILE\Documents\SillyTavern",
    "$env:USERPROFILE\Desktop\SillyTavern",
    "C:\SillyTavern",
    "D:\SillyTavern"
)

# 尝试自动检测
$detectedPath = $null
foreach ($path in $commonPaths) {
    # 优先检测新版 SillyTavern (1.12+)
    $newPath = Join-Path $path "data\default-user\extensions"
    if (Test-Path $newPath) {
        $detectedPath = $path
        break
    }
    # 其次检测旧版 SillyTavern
    $oldPath = Join-Path $path "public\scripts\extensions"
    if (Test-Path $oldPath) {
        $detectedPath = $path
        break
    }
}

Write-Host "请输入你的 SillyTavern 安装路径" -ForegroundColor Yellow
if ($detectedPath) {
    Write-Host "检测到可能的路径: $detectedPath" -ForegroundColor Gray
    Write-Host "直接按 Enter 使用检测到的路径，或输入其他路径:" -ForegroundColor Gray
} else {
    Write-Host "例如: C:\SillyTavern 或 D:\Programs\SillyTavern" -ForegroundColor Gray
}
Write-Host ""

$inputPath = Read-Host "SillyTavern 路径"

if ([string]::IsNullOrWhiteSpace($inputPath)) {
    if ($detectedPath) {
        $stPath = $detectedPath
    } else {
        Write-Host "错误: 请输入有效路径" -ForegroundColor Red
        Read-Host "按 Enter 退出"
        exit 1
    }
} else {
    $stPath = $inputPath.Trim('"').Trim("'")
}

# 验证路径并确定扩展目录
$newStylePath = Join-Path $stPath "data\default-user\extensions"
$oldStylePath = Join-Path $stPath "public\scripts\extensions\third-party"
$oldStyleBase = Join-Path $stPath "public\scripts\extensions"

if (Test-Path $newStylePath) {
    # 新版 SillyTavern (1.12+) - 直接放在 extensions/ 下
    $extensionsPath = $newStylePath
    Write-Host "检测到新版 SillyTavern (data/default-user/extensions)" -ForegroundColor Gray
} elseif (Test-Path $oldStylePath) {
    # 旧版 SillyTavern - 放在 third-party/ 下
    $extensionsPath = $oldStylePath
    Write-Host "检测到旧版 SillyTavern (public/scripts/extensions/third-party)" -ForegroundColor Gray
} elseif (Test-Path $oldStyleBase) {
    # 旧版但没有 third-party 目录
    $extensionsPath = $oldStylePath
    Write-Host "检测到旧版 SillyTavern，创建 third-party 目录" -ForegroundColor Gray
    New-Item -ItemType Directory -Path $extensionsPath -Force | Out-Null
} else {
    Write-Host ""
    Write-Host "错误: 这不是有效的 SillyTavern 目录" -ForegroundColor Red
    Write-Host "请确认路径是 SillyTavern 的根目录" -ForegroundColor Gray
    Read-Host "按 Enter 退出"
    exit 1
}

# 创建 third-party 目录（如果不存在）
if (-not (Test-Path $extensionsPath)) {
    New-Item -ItemType Directory -Path $extensionsPath -Force | Out-Null
}

# 目标路径
$targetPath = Join-Path $extensionsPath "recall-memory"

Write-Host ""
Write-Host "安装中..." -ForegroundColor Yellow

# 如果已存在，先删除
if (Test-Path $targetPath) {
    Write-Host "  发现旧版本，正在更新..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $targetPath
}

# 复制插件文件（排除安装脚本本身）
$filesToCopy = @("manifest.json", "index.js", "style.css", "i18n")

New-Item -ItemType Directory -Path $targetPath -Force | Out-Null

foreach ($file in $filesToCopy) {
    $source = Join-Path $pluginSource $file
    $dest = Join-Path $targetPath $file
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination $dest -Recurse -Force
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "           安装成功！                  " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "插件已安装到:" -ForegroundColor Cyan
Write-Host "  $targetPath" -ForegroundColor White
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. 重启 SillyTavern" -ForegroundColor White
Write-Host "  2. 确保 Recall 服务已启动 (运行 start.ps1)" -ForegroundColor White
Write-Host "  3. 在 SillyTavern 扩展面板启用 Recall Memory" -ForegroundColor White
Write-Host ""
Write-Host "默认 API 地址: http://127.0.0.1:18888" -ForegroundColor Gray
Write-Host ""

Read-Host "按 Enter 退出"
