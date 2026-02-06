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

# 设置控制台编码为 UTF-8，解决中文乱码问题
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Recall AI 安装程序"

# ==================== 全局变量 ====================
$ScriptDir = $PSScriptRoot
$VenvPath = Join-Path $ScriptDir "recall-env"
$DataPath = Join-Path $ScriptDir "recall_data"
$PipMirror = ""
$InstallSuccess = $false
$VenvCreated = $false
$InstallMode = "local"  # lite, cloud, local, enterprise (旧值 lightweight/hybrid/full 兼容)
$UseCPU = $false       # 是否使用 CPU 版 PyTorch（无需显卡）

# ==================== 工具函数 ====================

function Write-Header {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║       Recall AI v4.2.0 安装程序           ║" -ForegroundColor Cyan
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
    Write-Host "    [OK] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Error2 {
    param([string]$Message)
    Write-Host "    [X] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Write-Warning2 {
    param([string]$Message)
    Write-Host "    [!] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Info {
    param([string]$Message)
    Write-Host "    -> " -ForegroundColor Cyan -NoNewline
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
    Write-Host "Select installation mode:" -ForegroundColor White
    Write-Host ""
    Write-Host "  1) " -NoNewline; Write-Host "Lite Mode" -ForegroundColor Green -NoNewline; Write-Host "          ~100MB RAM, keyword search only"
    Write-Host "     For: Servers with < 1GB RAM" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  2) " -NoNewline; Write-Host "Cloud Mode" -ForegroundColor Green -NoNewline; Write-Host "        ~150MB RAM, cloud API for vectors " -NoNewline; Write-Host "[Recommended]" -ForegroundColor Yellow
    Write-Host "     For: Any server, full features, needs API Key" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  3) " -NoNewline; Write-Host "Local Mode" -ForegroundColor Green -NoNewline; Write-Host "          ~1.5GB RAM, local vector model"
    Write-Host "     For: High-spec servers, fully offline" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  4) " -NoNewline; Write-Host "Enterprise Mode" -ForegroundColor Magenta -NoNewline; Write-Host "     ~2GB RAM, Phase 3.5 advanced features"
    Write-Host "     For: Large-scale deployments (Kuzu + NetworkX + FAISS IVF)" -ForegroundColor Cyan
    Write-Host ""
    
    $modeChoice = Read-Host "请选择 [1-4，默认2]"
    
    switch ($modeChoice) {
        "1" { $script:InstallMode = "lite" }
        "3" { $script:InstallMode = "local" }
        "4" { $script:InstallMode = "enterprise" }
        default { $script:InstallMode = "cloud" }
    }
    
    Write-Host ""
    Write-Host "已选择: " -NoNewline
    Write-Host "$($script:InstallMode)" -ForegroundColor Green -NoNewline
    Write-Host " 模式"
    
    # 如果是 local 或 enterprise 模式，询问 GPU/CPU（兼容旧名称 full）
    if ($script:InstallMode -in @("local", "full", "enterprise")) {
        Write-Host ""
        Write-Host "─────────────────────────────────────────────" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "PyTorch 版本选择：" -ForegroundColor White
        Write-Host ""
        Write-Host "  1) " -NoNewline; Write-Host "GPU 版本" -ForegroundColor Green -NoNewline; Write-Host "   需要 NVIDIA 显卡，下载约 2.5GB"
        Write-Host "     适合: 有 NVIDIA 显卡，需要加速嵌入计算" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  2) " -NoNewline; Write-Host "CPU 版本" -ForegroundColor Yellow -NoNewline; Write-Host "   无需显卡，下载约 200MB " -NoNewline; Write-Host "[推荐无显卡用户]" -ForegroundColor Yellow
        Write-Host "     适合: 没有显卡或不想下载 CUDA 依赖" -ForegroundColor Cyan
        Write-Host ""
        
        $gpuChoice = Read-Host "请选择 [1-2，默认2 CPU版本]"
        
        if ($gpuChoice -eq "1") {
            $script:UseCPU = $false
            Write-Host ""
            Write-Host "已选择: " -NoNewline; Write-Host "GPU 版本" -ForegroundColor Green
        } else {
            $script:UseCPU = $true
            Write-Host ""
            Write-Host "已选择: " -NoNewline; Write-Host "CPU 版本" -ForegroundColor Yellow -NoNewline; Write-Host " (节省 ~2GB 下载)"
        }
    }
    Write-Host ""
}

function Show-Menu {
    Write-Host "请选择操作：" -ForegroundColor White
    Write-Host ""
    Write-Host "  1) 全新安装"
    Write-Host "  2) 全新安装 (使用国内镜像加速) " -NoNewline
    Write-Host "推荐" -ForegroundColor Green
    Write-Host "  3) 修复/重装依赖"
    Write-Host "  4) " -NoNewline; Write-Host "升级到企业版" -ForegroundColor Magenta -NoNewline; Write-Host " (添加 Kuzu + NetworkX)"
    Write-Host "  5) 完全卸载"
    Write-Host "  6) 查看状态"
    Write-Host "  7) 退出"
    Write-Host ""
    
    $choice = Read-Host "请输入选项 [1-7]"
    
    switch ($choice) {
        "1" { Show-ModeSelection; Invoke-Install }
        "2" { Show-ModeSelection; $script:PipMirror = "-i https://pypi.tuna.tsinghua.edu.cn/simple"; Invoke-Install }
        "3" { Invoke-Repair }
        "4" { Invoke-UpgradeEnterprise }
        "5" { Invoke-Uninstall }
        "6" { Show-Status }
        "7" { exit 0 }
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
        { $_ -in "lite", "lightweight" } {
            Write-Host "    ℹ Lite 模式：下载约 300MB 依赖" -ForegroundColor Cyan
            Write-Host "    ℹ 预计需要 3-5 分钟" -ForegroundColor Cyan
        }
        { $_ -in "cloud", "hybrid" } {
            Write-Host "    ℹ Cloud 模式：下载约 400MB 依赖" -ForegroundColor Cyan
            Write-Host "    ℹ 预计需要 5-8 分钟" -ForegroundColor Cyan
        }
        { $_ -in "local", "full" } {
            if ($UseCPU) {
                Write-Host "    ℹ Local 模式 (CPU)：下载约 500MB 依赖" -ForegroundColor Cyan
                Write-Host "    ℹ 预计需要 5-10 分钟" -ForegroundColor Cyan
            } else {
                Write-Host "    ℹ Local 模式 (GPU)：下载约 2.5GB 依赖 (包含 CUDA)" -ForegroundColor Cyan
                Write-Host "    ℹ 预计需要 15-30 分钟" -ForegroundColor Cyan
            }
        }
        "enterprise" {
            if ($UseCPU) {
                Write-Host "    ℹ Enterprise 模式 (CPU)：下载约 600MB 依赖" -ForegroundColor Cyan
                Write-Host "    ℹ 预计需要 8-15 分钟" -ForegroundColor Cyan
            } else {
                Write-Host "    ℹ Enterprise 模式 (GPU)：下载约 2.8GB 依赖 (包含 CUDA)" -ForegroundColor Cyan
                Write-Host "    ℹ 预计需要 20-40 分钟" -ForegroundColor Cyan
            }
        }
    }
    Write-Host ""
    
    # 升级 pip（使用 python -m pip 避免 Windows 锁定问题）
    Write-Info "升级 pip..."
    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    $pipUpgradeArgs = @("-m", "pip", "install", "--upgrade", "pip", "-q")
    if ($PipMirror) { $pipUpgradeArgs += $PipMirror.Split(" ") }
    & $pythonPath @pipUpgradeArgs 2>$null
    Write-Success "pip 升级完成"
    
    # 如果选择 CPU 版本，先安装 CPU 版 PyTorch
    if ($UseCPU -and $InstallMode -in @("local", "full", "enterprise")) {
        Write-Info "安装 CPU 版 PyTorch (无需 NVIDIA 显卡)..."
        $torchArgs = @("install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cpu")
        if ($PipMirror) { 
            # CPU 版必须从 PyTorch 官方源安装，但其他依赖可以用镜像
            Write-Host "    ℹ 注意：PyTorch CPU 版从官方源下载" -ForegroundColor Yellow
        }
        & $pipPath @torchArgs 2>&1 | ForEach-Object {
            if ($_ -match "Collecting") {
                $pkg = ($_ -replace "Collecting ", "") -split " " | Select-Object -First 1
                Write-Host "    📦 收集: $pkg" -ForegroundColor Cyan
            } elseif ($_ -match "Downloading") {
                Write-Host "    ↓  下载中..." -ForegroundColor Cyan
            } elseif ($_ -match "Successfully installed") {
                Write-Host "    ✓  PyTorch CPU 版安装成功" -ForegroundColor Green
            }
        }
    }
    
    # 安装项目依赖
    Write-Info "安装项目依赖..."
    Write-Host ""
    
    # 根据模式安装不同依赖（兼容新旧名称）
    $extras = ""
    switch ($InstallMode) {
        { $_ -in "lite", "lightweight" } { 
            $extras = ""
            Write-Info "安装 Lite 依赖..."
        }
        { $_ -in "cloud", "hybrid" } { 
            $extras = "[cloud]"
            Write-Info "安装 Cloud 依赖 (FAISS)..."
        }
        { $_ -in "local", "full" } { 
            $extras = "[local]"
            Write-Info "安装 Local 依赖 (sentence-transformers + FAISS)..."
        }
        "enterprise" {
            $extras = "[local,enterprise]"
            Write-Info "安装 Enterprise 依赖 (sentence-transformers + FAISS + Kuzu + NetworkX)..."
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
    
    $spacyArgs = @("-m", "spacy", "download", "zh_core_web_sm")
    & $pythonPath @spacyArgs 2>&1 | Out-Null
    
    # 验证模型是否真正可加载
    $testResult = & $pythonPath -c "import spacy; spacy.load('zh_core_web_sm'); print('OK')" 2>&1
    if ($testResult -eq "OK") {
        Write-Success "spaCy 中文模型下载完成"
    } else {
        Write-Warning2 "spaCy 模型安装不完整，尝试备用方案..."
        
        # 备用方案：从 GitHub 直接安装 (zh-core-web-sm 不在 PyPI 上)
        # 获取已安装的 spaCy 版本的主版本号
        $spacyVer = & $pythonPath -c "import spacy; print('.'.join(spacy.__version__.split('.')[:2]))" 2>&1
        if (-not $spacyVer) { $spacyVer = "3.8" }
        
        $modelUrl = "https://github.com/explosion/spacy-models/releases/download/zh_core_web_sm-${spacyVer}.0/zh_core_web_sm-${spacyVer}.0-py3-none-any.whl"
        
        $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
        & $pipPath install $modelUrl 2>&1 | Out-Null
        
        # 再次验证
        $testResult2 = & $pythonPath -c "import spacy; spacy.load('zh_core_web_sm'); print('OK')" 2>&1
        if ($testResult2 -eq "OK") {
            Write-Success "spaCy 中文模型安装完成 (备用方案)"
        } else {
            Write-Warning2 "模型安装失败，但不影响基本功能"
            Write-Info "可稍后手动安装: pip install $modelUrl"
        }
    }
}

# ==================== 初始化 ====================

function Initialize-Recall {
    Write-Step 5 5 "初始化 Recall"
    
    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    
    Write-Info "运行初始化..."
    
    # 先创建数据目录（确保目录存在）
    $dirs = @("data", "logs", "cache", "models", "config", "temp")
    foreach ($dir in $dirs) {
        $path = Join-Path $DataPath $dir
        if (-not (Test-Path $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
    
    # 根据模式初始化（兼容新旧名称）
    # 使用 Start-Process 完全隔离执行，避免 rich 库的 stderr 输出触发 PowerShell 错误
    $initArgs = if ($InstallMode -in "lite", "lightweight") { "-m recall init --lightweight" } else { "-m recall init" }
    
    Start-Process -FilePath $pythonPath -ArgumentList $initArgs -WorkingDirectory $ScriptDir -WindowStyle Hidden -Wait | Out-Null
    # 不检查退出码，初始化失败不影响使用（目录已创建）
    
    # 保存安装模式
    $modePath = Join-Path $DataPath "config\install_mode"
    Set-Content -Path $modePath -Value $InstallMode
    
    # 保存 CPU/GPU 选择
    $cpuModePath = Join-Path $DataPath "config\use_cpu"
    if ($UseCPU) {
        Set-Content -Path $cpuModePath -Value "true"
    } else {
        Set-Content -Path $cpuModePath -Value "false"
    }
    
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
        
        # 根据模式显示不同提示（兼容新旧名称）
        switch ($InstallMode) {
            { $_ -in "lite", "lightweight" } {
                Write-Host "  安装模式: " -NoNewline; Write-Host "Lite 模式" -ForegroundColor Cyan
                Write-Host "  " -NoNewline; Write-Host "注意: Lite 模式仅支持关键词搜索，无语义搜索" -ForegroundColor Yellow
            }
            { $_ -in "cloud", "hybrid" } {
                Write-Host "  安装模式: " -NoNewline; Write-Host "Cloud 模式" -ForegroundColor Cyan
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
            { $_ -in "local", "full" } {
                Write-Host "  安装模式: " -NoNewline; Write-Host "Local 模式" -ForegroundColor Cyan
                Write-Host "  " -NoNewline; Write-Host "✓ 本地模型，无需API Key，完全离线运行" -ForegroundColor Green
            }
            "enterprise" {
                Write-Host "  安装模式: " -NoNewline; Write-Host "Enterprise 模式" -ForegroundColor Magenta
                Write-Host ""
                Write-Host "  Phase 3.5 企业级性能引擎已启用:" -ForegroundColor Green
                Write-Host "    ✓ Kuzu 嵌入式图数据库 (高性能图存储)"
                Write-Host "    ✓ NetworkX 社区检测 (实体群组发现)"
                Write-Host "    ✓ FAISS IVF 磁盘索引 (百万级向量)"
                Write-Host "    ✓ QueryPlanner 查询优化器"
                Write-Host ""
                Write-Host "  启用 Kuzu 后端:" -ForegroundColor Yellow
                Write-Host "    TEMPORAL_GRAPH_BACKEND=kuzu  # 使用 Kuzu 图数据库"
                Write-Host "    KUZU_BUFFER_POOL_SIZE=256    # Kuzu 内存池大小 (MB)"
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

# ==================== 升级到企业版 ====================

function Invoke-UpgradeEnterprise {
    Write-Header
    Write-Host "🚀 升级到企业版" -ForegroundColor Magenta
    Write-Host ""
    
    if (-not (Test-Path $VenvPath)) {
        Write-Error2 "虚拟环境不存在，请先完整安装"
        Write-Host ""
        $confirm = Read-Host "是否现在安装? [Y/n]"
        if ($confirm -notmatch "^[Nn]$") {
            $script:InstallMode = "enterprise"
            Invoke-Install
        }
        return
    }
    
    # 检查当前安装模式
    $modePath = Join-Path $DataPath "config\install_mode"
    $currentMode = "unknown"
    if (Test-Path $modePath) {
        $currentMode = Get-Content $modePath -ErrorAction SilentlyContinue
    }
    
    if ($currentMode -eq "enterprise") {
        Write-Success "当前已是企业版！"
        Write-Host ""
        Write-Host "  已安装的企业级组件:" -ForegroundColor Green
        
        $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
        $kuzuVer = & $pythonPath -c "import kuzu; print(kuzu.__version__)" 2>&1
        $nxVer = & $pythonPath -c "import networkx; print(networkx.__version__)" 2>&1
        $faissOK = & $pythonPath -c "import faiss; print('OK')" 2>&1
        
        Write-Host "    Kuzu: v$kuzuVer"
        Write-Host "    NetworkX: v$nxVer"
        Write-Host "    FAISS: $faissOK"
        Write-Host ""
        Read-Host "按 Enter 退出"
        return
    }
    
    Write-Host "  当前模式: " -NoNewline
    Write-Host "$currentMode" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  将添加以下企业级组件:" -ForegroundColor Yellow
    Write-Host "    • Kuzu 嵌入式图数据库 (高性能图存储)"
    Write-Host "    • NetworkX 图分析 (社区检测)"
    Write-Host "    • FAISS IVF 磁盘索引 (如果尚未安装)"
    Write-Host ""
    Write-Host "  预计下载: ~50MB (如果已是 Local 模式则更少)" -ForegroundColor Cyan
    Write-Host "  不会影响现有数据和配置" -ForegroundColor Green
    Write-Host ""
    
    $confirm = Read-Host "确认升级? [Y/n]"
    if ($confirm -match "^[Nn]$") {
        Write-Info "已取消升级"
        Read-Host "按 Enter 退出"
        return
    }
    
    Write-Host ""
    Write-Info "正在安装企业版依赖..."
    
    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    $pipArgs = @("-m", "pip", "install", "networkx>=3.0", "kuzu>=0.3", "faiss-cpu>=1.7")
    if ($PipMirror) { $pipArgs += $PipMirror.Split(" ") }
    
    & $pythonPath @pipArgs
    
    if ($LASTEXITCODE -eq 0) {
        # 更新安装模式
        $configDir = Join-Path $DataPath "config"
        if (-not (Test-Path $configDir)) {
            New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        }
        Set-Content -Path $modePath -Value "enterprise"
        
        Write-Host ""
        Write-Success "升级完成！"
        Write-Host ""
        Write-Host "  企业级功能已启用:" -ForegroundColor Green
        Write-Host "    ✓ Kuzu 嵌入式图数据库"
        Write-Host "    ✓ NetworkX 社区检测"
        Write-Host "    ✓ FAISS IVF 磁盘索引"
        Write-Host "    ✓ QueryPlanner 查询优化器"
        Write-Host ""
    } else {
        Write-Error2 "升级失败，请检查网络连接"
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
    
    # 读取之前的安装模式
    $modePath = Join-Path $DataPath "config\install_mode"
    $cpuModePath = Join-Path $DataPath "config\use_cpu"
    
    if (Test-Path $modePath) {
        $script:InstallMode = Get-Content $modePath -ErrorAction SilentlyContinue
        Write-Info "检测到安装模式: $InstallMode"
    } else {
        $script:InstallMode = "cloud"
        Write-Warning2 "未找到安装模式配置，使用默认 cloud 模式"
    }
    
    if (Test-Path $cpuModePath) {
        $cpuSetting = Get-Content $cpuModePath -ErrorAction SilentlyContinue
        $script:UseCPU = ($cpuSetting -eq "true")
        if ($UseCPU) {
            Write-Info "检测到 PyTorch 版本: CPU"
        } else {
            Write-Info "检测到 PyTorch 版本: GPU"
        }
    }
    
    $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
    
    Write-Host ""
    Write-Host "选择修复方式:"
    Write-Host "  1) 快速修复 (只更新 recall)"
    Write-Host "  2) 完整重装 (重新安装所有依赖)"
    Write-Host ""
    $choice = Read-Host "请选择 [1/2]"
    
    # 确定 extras
    $extras = ""
    switch ($InstallMode) {
        { $_ -in "lite", "lightweight" } { $extras = "" }
        { $_ -in "cloud", "hybrid" } { $extras = "[cloud]" }
        { $_ -in "local", "full" } { $extras = "[local]" }
        "enterprise" { $extras = "[local,enterprise]" }
        default { $extras = "[cloud]" }
    }
    
    switch ($choice) {
        "1" {
            Write-Info "快速修复中..."
            $pipArgs = @("install", "-e", "$ScriptDir$extras", "--upgrade")
            if ($PipMirror) { $pipArgs += $PipMirror.Split(" ") }
            & $pipPath @pipArgs
        }
        "2" {
            Write-Info "完整重装中..."
            
            # 如果是 CPU 模式，先安装 CPU 版 PyTorch
            if ($UseCPU -and $InstallMode -in @("local", "full", "enterprise")) {
                Write-Info "重装 CPU 版 PyTorch..."
                $torchArgs = @("install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cpu", "--force-reinstall")
                & $pipPath @torchArgs 2>&1 | Out-Null
            }
            
            $pipArgs = @("install", "-e", "$ScriptDir$extras", "--force-reinstall")
            if ($PipMirror) { $pipArgs += $PipMirror.Split(" ") }
            & $pipPath @pipArgs
            
            # 重新安装 spaCy 模型（与 Install-Models 相同逻辑）
            Write-Info "重新安装 spaCy 模型..."
            $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
            & $pythonPath -m spacy download zh_core_web_sm 2>&1 | Out-Null
            $testResult = & $pythonPath -c "import spacy; spacy.load('zh_core_web_sm'); print('OK')" 2>&1
            if ($testResult -ne "OK") {
                $spacyVer = & $pythonPath -c "import spacy; print('.'.join(spacy.__version__.split('.')[:2]))" 2>&1
                if (-not $spacyVer) { $spacyVer = "3.8" }
                $modelUrl = "https://github.com/explosion/spacy-models/releases/download/zh_core_web_sm-${spacyVer}.0/zh_core_web_sm-${spacyVer}.0-py3-none-any.whl"
                & $pipPath install $modelUrl 2>&1 | Out-Null
            }
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
        $procId = Get-Content $pidFile
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Success "服务状态: 运行中 (PID: $procId)"
        } else {
            Write-Warning2 "服务状态: 已停止 (残留PID文件)"
        }
    } else {
        Write-Info "服务状态: 未运行"
    }
    
    # API 检查
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:18888/" -TimeoutSec 2 -ErrorAction Stop
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
