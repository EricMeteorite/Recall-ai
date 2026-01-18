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
function Write-Info { param([string]$Text) Write-Host "  [i] $Text" -ForegroundColor Yellow }
function Write-Dim { param([string]$Text) Write-Host "  $Text" -ForegroundColor DarkGray }

# ==================== Banner ====================
function Show-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  +============================================================+" -ForegroundColor Cyan
    Write-Host "  |                                                            |" -ForegroundColor Cyan
    Write-Host "  |              Recall-ai Manager  v$VERSION                     |" -ForegroundColor Cyan
    Write-Host "  |                                                            |" -ForegroundColor Cyan
    Write-Host "  |         Memory Management System for AI Characters         |" -ForegroundColor Cyan
    Write-Host "  +============================================================+" -ForegroundColor Cyan
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
    Write-Host "  |  Current Status                                           |" -ForegroundColor DarkGray
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor DarkGray
    
    # Recall-ai status
    $recallStatus = if ($installed) { 
        if ($running) { "[OK] Installed, Running" } else { "[OK] Installed, Not Running" }
    } else { "[X] Not Installed" }
    $recallColor = if ($installed -and $running) { "Green" } elseif ($installed) { "Yellow" } else { "Red" }
    Write-Host "  |  Recall-ai:        " -NoNewline -ForegroundColor DarkGray
    Write-Host $recallStatus.PadRight(38) -NoNewline -ForegroundColor $recallColor
    Write-Host "|" -ForegroundColor DarkGray
    
    # SillyTavern plugin status
    $stStatus = if ($stInstalled) { "[OK] Installed" } else { "[X] Not Installed" }
    $stColor = if ($stInstalled) { "Green" } else { "DarkGray" }
    Write-Host "  |  SillyTavern Plugin:" -NoNewline -ForegroundColor DarkGray
    Write-Host $stStatus.PadRight(38) -NoNewline -ForegroundColor $stColor
    Write-Host "|" -ForegroundColor DarkGray
    
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor DarkGray
    
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor White
    Write-Host "  |                       Main Menu                           |" -ForegroundColor White
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [1] Install Recall-ai                                  |" -ForegroundColor White
    Write-Host "  |    [2] Start Service                                      |" -ForegroundColor White
    Write-Host "  |    [3] Stop Service                                       |" -ForegroundColor White
    Write-Host "  |    [4] Restart Service                                    |" -ForegroundColor White
    Write-Host "  |    [5] View Status                                        |" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [6] SillyTavern Plugin Management  ->                  |" -ForegroundColor White
    Write-Host "  |    [7] Configuration Management       ->                  |" -ForegroundColor White
    Write-Host "  |                                                           |" -ForegroundColor White
    Write-Host "  |    [0] Exit                                               |" -ForegroundColor White
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
    Write-Host "  |              SillyTavern Plugin Management                |" -ForegroundColor Magenta
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    
    if ($config.st_path) {
        Write-Host "  |  ST Path: " -NoNewline -ForegroundColor Magenta
        $displayPath = if ($config.st_path.Length -gt 45) { $config.st_path.Substring(0, 42) + "..." } else { $config.st_path }
        Write-Host $displayPath.PadRight(47) -NoNewline -ForegroundColor DarkGray
        Write-Host "|" -ForegroundColor Magenta
    }
    
    $statusText = if ($stInstalled) { "[OK] Installed" } else { "[X] Not Installed" }
    $statusColor = if ($stInstalled) { "Green" } else { "Yellow" }
    Write-Host "  |  Plugin Status: " -NoNewline -ForegroundColor Magenta
    Write-Host $statusText.PadRight(41) -NoNewline -ForegroundColor $statusColor
    Write-Host "|" -ForegroundColor Magenta
    
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  |    [1] Install Plugin to SillyTavern                      |" -ForegroundColor Magenta
    Write-Host "  |    [2] Uninstall Plugin                                   |" -ForegroundColor Magenta
    Write-Host "  |    [3] Update Plugin                                      |" -ForegroundColor Magenta
    Write-Host "  |    [4] Set SillyTavern Path                               |" -ForegroundColor Magenta
    Write-Host "  |    [5] Check Plugin Status                                |" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  |    [0] <- Back to Main Menu                               |" -ForegroundColor Magenta
    Write-Host "  |                                                           |" -ForegroundColor Magenta
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Magenta
    Write-Host ""
}

# ==================== Config Menu ====================
function Show-ConfigMenu {
    Write-Host ""
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |                  Configuration Management                 |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  |    [1] Edit API Config File                               |" -ForegroundColor Yellow
    Write-Host "  |    [2] Hot Reload Config (No Restart)                     |" -ForegroundColor Yellow
    Write-Host "  |    [3] Test Embedding API Connection                      |" -ForegroundColor Yellow
    Write-Host "  |    [4] Test LLM API Connection                            |" -ForegroundColor Yellow
    Write-Host "  |    [5] View Current Config                                |" -ForegroundColor Yellow
    Write-Host "  |    [6] Reset Config to Default                            |" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  |    [0] <- Back to Main Menu                               |" -ForegroundColor Yellow
    Write-Host "  |                                                           |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""
}

# ==================== Operation Functions ====================

function Do-Install {
    Write-Title "Install Recall-ai"
    
    if (Test-Installed) {
        Write-Info "Recall-ai is already installed"
        $choice = Read-Host "  Reinstall? (y/N)"
        if ($choice -ne "y" -and $choice -ne "Y") {
            return
        }
    }
    
    $installScript = Join-Path $SCRIPT_DIR "install.ps1"
    if (Test-Path $installScript) {
        Write-Info "Running install script..."
        & $installScript
    } else {
        Write-Error2 "Install script not found: $installScript"
    }
}

function Do-Start {
    Write-Title "Start Service"
    
    if (-not (Test-Installed)) {
        Write-Error2 "Recall-ai not installed, please install first"
        return
    }
    
    if (Test-ServiceRunning) {
        Write-Info "Service is already running"
        return
    }
    
    $startScript = Join-Path $SCRIPT_DIR "start.ps1"
    if (Test-Path $startScript) {
        Write-Info "Starting service..."
        Start-Process powershell -ArgumentList "-NoExit", "-File", $startScript -WorkingDirectory $SCRIPT_DIR
        
        # Wait for service to start
        Write-Host "  Waiting for service to start" -NoNewline
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Seconds 1
            Write-Host "." -NoNewline
            if (Test-ServiceRunning) {
                Write-Host ""
                Write-Success "Service started!"
                Write-Dim "API Address: http://127.0.0.1:$DEFAULT_PORT"
                return
            }
        }
        Write-Host ""
        Write-Info "Service is starting in background, please check status later"
    } else {
        Write-Error2 "Start script not found: $startScript"
    }
}

function Do-Stop {
    Write-Title "Stop Service"
    
    if (-not (Test-ServiceRunning)) {
        Write-Info "Service is not running"
        return
    }
    
    Write-Info "Stopping service..."
    
    # Find and terminate uvicorn process
    $processes = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*recall*" -or $_.CommandLine -like "*recall.server*"
    }
    
    if ($processes) {
        $processes | Stop-Process -Force
        Write-Success "Service stopped"
    } else {
        # Try to find by port
        $netstat = netstat -ano | Select-String ":$DEFAULT_PORT.*LISTENING"
        if ($netstat) {
            $pid = ($netstat -split '\s+')[-1]
            if ($pid -and $pid -ne "0") {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Write-Success "Service stopped"
                return
            }
        }
        Write-Info "No running service process found"
    }
}

function Do-Restart {
    Write-Title "Restart Service"
    Do-Stop
    Start-Sleep -Seconds 2
    Do-Start
}

function Do-Status {
    Write-Title "Service Status"
    
    $installed = Test-Installed
    $running = Test-ServiceRunning
    
    Write-Host ""
    if ($installed) {
        Write-Success "Recall-ai is installed"
        
        # Get version info
        try {
            $venvPython = Join-Path $SCRIPT_DIR "recall-env\Scripts\python.exe"
            $version = & $venvPython -c "from recall.version import __version__; print(__version__)" 2>$null
            if ($version) {
                Write-Dim "Version: v$version"
            }
        } catch {}
    } else {
        Write-Error2 "Recall-ai not installed"
    }
    
    Write-Host ""
    if ($running) {
        Write-Success "Service is running"
        Write-Dim "API Address: http://127.0.0.1:$DEFAULT_PORT"
        
        # Get statistics
        try {
            $stats = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/stats" -TimeoutSec 5
            Write-Dim "Total Memories: $($stats.total_memories)"
            $mode = if ($stats.lightweight) { "轻量模式" } else { "完整模式" }
            Write-Dim "Embedding Mode: $mode"
        } catch {}
    } else {
        Write-Error2 "Service is not running"
    }
    
    Write-Host ""
    $stInstalled = Test-STPluginInstalled
    if ($stInstalled) {
        Write-Success "SillyTavern plugin is installed"
        $pluginPath = Get-STPluginPath
        Write-Dim "Path: $pluginPath"
    } else {
        Write-Info "SillyTavern plugin not installed"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

# ==================== SillyTavern Plugin Operations ====================

function Set-STPath {
    Write-Title "Set SillyTavern Path"
    
    $config = Get-ManagerConfig
    
    if ($config.st_path) {
        Write-Dim "Current path: $($config.st_path)"
    }
    
    Write-Host ""
    Write-Info "Please enter the SillyTavern installation path"
    Write-Dim "Example: C:\SillyTavern or D:\Apps\SillyTavern"
    Write-Host ""
    
    $newPath = Read-Host "  Path"
    
    if (-not $newPath) {
        Write-Info "Cancelled"
        return
    }
    
    # Validate path
    if (-not (Test-Path $newPath)) {
        Write-Error2 "Path does not exist: $newPath"
        return
    }
    
    # Check if valid ST directory
    $serverJs = Join-Path $newPath "server.js"
    $publicDir = Join-Path $newPath "public"
    
    if (-not ((Test-Path $serverJs) -and (Test-Path $publicDir))) {
        Write-Error2 "This is not a valid SillyTavern directory"
        Write-Dim "Should contain server.js and public folder"
        return
    }
    
    $config.st_path = $newPath
    Save-ManagerConfig $config
    Write-Success "Path saved: $newPath"
}

function Install-STPlugin {
    Write-Title "Install SillyTavern Plugin"
    
    $config = Get-ManagerConfig
    
    if (-not $config.st_path) {
        Write-Error2 "SillyTavern path not set"
        Write-Info "Please set the path first (menu option 4)"
        return
    }
    
    if (-not (Test-Path $config.st_path)) {
        Write-Error2 "SillyTavern path does not exist: $($config.st_path)"
        return
    }
    
    $sourceDir = Join-Path $SCRIPT_DIR "plugins\sillytavern"
    $targetDir = Join-Path $config.st_path "public\scripts\extensions\third-party\recall-memory"
    
    if (-not (Test-Path $sourceDir)) {
        Write-Error2 "Plugin source not found: $sourceDir"
        return
    }
    
    # Create target directory
    if (Test-Path $targetDir) {
        Write-Info "Plugin directory exists, updating..."
        Remove-Item -Path $targetDir -Recurse -Force
    }
    
    Write-Info "Copying plugin files..."
    Copy-Item -Path $sourceDir -Destination $targetDir -Recurse -Force
    
    if (Test-Path $targetDir) {
        Write-Success "Plugin installed successfully!"
        Write-Host ""
        Write-Info "Next steps:"
        Write-Dim "1. Start Recall-ai service (main menu option 2)"
        Write-Dim "2. Start/restart SillyTavern"
        Write-Dim "3. Find 'Recall Memory System' in ST extensions panel"
    } else {
        Write-Error2 "Plugin installation failed"
    }
}

function Uninstall-STPlugin {
    Write-Title "Uninstall SillyTavern Plugin"
    
    if (-not (Test-STPluginInstalled)) {
        Write-Info "Plugin is not installed"
        return
    }
    
    $pluginPath = Get-STPluginPath
    
    Write-Host ""
    Write-Info "Will delete: $pluginPath"
    $confirm = Read-Host "  Confirm uninstall? (y/N)"
    
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Info "Cancelled"
        return
    }
    
    try {
        Remove-Item -Path $pluginPath -Recurse -Force
        Write-Success "Plugin uninstalled"
        Write-Dim "Restart SillyTavern to take effect"
    } catch {
        Write-Error2 "Uninstall failed: $_"
    }
}

function Update-STPlugin {
    Write-Title "Update SillyTavern Plugin"
    
    if (-not (Test-STPluginInstalled)) {
        Write-Info "Plugin not installed, will install..."
        Install-STPlugin
        return
    }
    
    Write-Info "Updating plugin..."
    Install-STPlugin
}

function Check-STPluginStatus {
    Write-Title "Plugin Status Check"
    
    $config = Get-ManagerConfig
    
    Write-Host ""
    
    # ST path
    if ($config.st_path) {
        Write-Success "SillyTavern path configured"
        Write-Dim "Path: $($config.st_path)"
        
        if (Test-Path $config.st_path) {
            Write-Success "Path exists"
        } else {
            Write-Error2 "Path does not exist!"
        }
    } else {
        Write-Error2 "SillyTavern path not configured"
    }
    
    Write-Host ""
    
    # Plugin status
    if (Test-STPluginInstalled) {
        Write-Success "Plugin is installed"
        $pluginPath = Get-STPluginPath
        Write-Dim "Location: $pluginPath"
        
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
            Write-Success "All files present"
        } else {
            Write-Error2 "Missing files: $($missing -join ', ')"
        }
    } else {
        Write-Error2 "Plugin not installed"
    }
    
    Write-Host ""
    
    # Recall service status
    if (Test-ServiceRunning) {
        Write-Success "Recall service is running"
    } else {
        Write-Error2 "Recall service is not running"
        Write-Dim "Plugin requires Recall service to work"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

# ==================== Config Operations ====================

function Edit-Config {
    Write-Title "Edit Config File"
    
    $configFile = Join-Path $SCRIPT_DIR "recall_data\config\api_keys.env"
    
    if (-not (Test-Path $configFile)) {
        Write-Info "Config file does not exist, creating..."
        $venvPython = Join-Path $SCRIPT_DIR "recall-env\Scripts\python.exe"
        if (Test-Path $venvPython) {
            & $venvPython -c "from recall.server import load_api_keys_from_file; load_api_keys_from_file()" 2>$null
        }
    }
    
    if (Test-Path $configFile) {
        Write-Info "Opening config file..."
        Write-Dim "File: $configFile"
        Start-Process notepad.exe -ArgumentList $configFile
    } else {
        Write-Error2 "Cannot create config file"
    }
}

function Reload-Config {
    Write-Title "Hot Reload Config"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running, cannot hot reload"
        Write-Info "Please start the service first"
        return
    }
    
    Write-Info "Reloading config..."
    
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/reload" -Method POST -TimeoutSec 10
        Write-Success "Config reloaded!"
        
        # Show current mode
        $configInfo = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config" -TimeoutSec 5
        Write-Dim "Current Embedding Mode: $($configInfo.embedding.mode)"
    } catch {
        Write-Error2 "Hot reload failed: $_"
    }
}

function Test-EmbeddingAPI {
    Write-Title "Test Embedding API"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running"
        return
    }
    
    Write-Info "Testing Embedding API connection..."
    
    try {
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/test" -TimeoutSec 30
        
        Write-Host ""
        if ($result.success) {
            Write-Success "Embedding API connection successful!"
            Write-Dim "Backend: $($result.backend)"
            Write-Dim "Model: $($result.model)"
            Write-Dim "Dimension: $($result.dimension)"
            Write-Dim "Latency: $($result.latency_ms)ms"
        } else {
            Write-Error2 "Embedding API connection failed"
            Write-Dim $result.message
        }
    } catch {
        Write-Error2 "Test failed: $_"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

function Test-LlmAPI {
    Write-Title "Test LLM API"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running"
        return
    }
    
    Write-Info "Testing LLM API connection..."
    
    try {
        $result = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config/test/llm" -TimeoutSec 30
        
        Write-Host ""
        if ($result.success) {
            Write-Success "LLM API connection successful!"
            Write-Dim "Model: $($result.model)"
            Write-Dim "API Base: $($result.api_base)"
            Write-Dim "Response: $($result.response)"
            Write-Dim "Latency: $($result.latency_ms)ms"
        } else {
            Write-Error2 "LLM API connection failed"
            Write-Dim $result.message
        }
    } catch {
        Write-Error2 "Test failed: $_"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

function Show-CurrentConfig {
    Write-Title "Current Config"
    
    if (-not (Test-ServiceRunning)) {
        Write-Error2 "Service not running, cannot get config"
        return
    }
    
    try {
        $config = Invoke-RestMethod -Uri "http://127.0.0.1:$DEFAULT_PORT/v1/config" -TimeoutSec 5
        
        Write-Host ""
        Write-Info "Embedding Mode: $($config.embedding.mode)"
        Write-Host ""
        
        Write-Dim "Config File: $($config.config_file)"
        Write-Dim "File Exists: $($config.config_file_exists)"
        
        Write-Host ""
        Write-Info "Embedding Config:"
        $embStatus = $config.embedding.status
        $statusColor = if ($embStatus -eq "已配置") { "Green" } else { "DarkGray" }
        Write-Host "  Status: " -NoNewline
        Write-Host $embStatus -ForegroundColor $statusColor
        Write-Dim "  API Base: $($config.embedding.api_base)"
        Write-Dim "  Model: $($config.embedding.model)"
        Write-Dim "  Dimension: $($config.embedding.dimension)"
        
        Write-Host ""
        Write-Info "LLM Config:"
        $llmStatus = $config.llm.status
        $statusColor = if ($llmStatus -eq "已配置") { "Green" } else { "DarkGray" }
        Write-Host "  Status: " -NoNewline
        Write-Host $llmStatus -ForegroundColor $statusColor
        Write-Dim "  API Base: $($config.llm.api_base)"
        Write-Dim "  Model: $($config.llm.model)"
    } catch {
        Write-Error2 "Failed to get config: $_"
    }
    
    Write-Host ""
    Read-Host "  Press Enter to continue"
}

function Reset-Config {
    Write-Title "Reset Config"
    
    $configFile = Join-Path $SCRIPT_DIR "recall_data\config\api_keys.env"
    
    Write-Host ""
    Write-Info "This will delete current config and regenerate default"
    $confirm = Read-Host "  Confirm reset? (y/N)"
    
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Info "Cancelled"
        return
    }
    
    if (Test-Path $configFile) {
        Remove-Item $configFile -Force
        Write-Success "Config reset"
        Write-Info "Default config will be generated on next service start"
    } else {
        Write-Info "Config file does not exist"
    }
}

# ==================== Menu Loops ====================

function Run-STMenu {
    while ($true) {
        Show-Banner
        Show-STMenu
        
        $choice = Read-Host "  Select"
        
        switch ($choice) {
            "1" { Install-STPlugin; Read-Host "  Press Enter to continue" }
            "2" { Uninstall-STPlugin; Read-Host "  Press Enter to continue" }
            "3" { Update-STPlugin; Read-Host "  Press Enter to continue" }
            "4" { Set-STPath; Read-Host "  Press Enter to continue" }
            "5" { Check-STPluginStatus }
            "0" { return }
            default { Write-Error2 "Invalid selection" }
        }
    }
}

function Run-ConfigMenu {
    while ($true) {
        Show-Banner
        Show-ConfigMenu
        
        $choice = Read-Host "  Select"
        
        switch ($choice) {
            "1" { Edit-Config; Read-Host "  Press Enter to continue" }
            "2" { Reload-Config; Read-Host "  Press Enter to continue" }
            "3" { Test-EmbeddingAPI }
            "4" { Test-LlmAPI }
            "5" { Show-CurrentConfig }
            "6" { Reset-Config; Read-Host "  Press Enter to continue" }
            "0" { return }
            default { Write-Error2 "Invalid selection" }
        }
    }
}

function Run-MainMenu {
    while ($true) {
        Show-Banner
        Show-MainMenu
        
        $choice = Read-Host "  Select"
        
        switch ($choice) {
            "1" { Do-Install; Read-Host "  Press Enter to continue" }
            "2" { Do-Start; Read-Host "  Press Enter to continue" }
            "3" { Do-Stop; Read-Host "  Press Enter to continue" }
            "4" { Do-Restart; Read-Host "  Press Enter to continue" }
            "5" { Do-Status }
            "6" { Run-STMenu }
            "7" { Run-ConfigMenu }
            "0" { 
                Write-Host ""
                Write-Color "  Goodbye!" "Cyan"
                Write-Host ""
                exit 0
            }
            default { Write-Error2 "Invalid selection" }
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
        default {
            Write-Host ""
            Write-Host "Recall-ai Manager" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "Usage: .\manage.ps1 [command]" -ForegroundColor White
            Write-Host ""
            Write-Host "Commands:" -ForegroundColor Yellow
            Write-Host "  install      Install Recall-ai"
            Write-Host "  start        Start service"
            Write-Host "  stop         Stop service"
            Write-Host "  restart      Restart service"
            Write-Host "  status       View status"
            Write-Host "  st-install   Install SillyTavern plugin"
            Write-Host "  st-uninstall Uninstall SillyTavern plugin"
            Write-Host "  st-update    Update SillyTavern plugin"
            Write-Host ""
            Write-Host "Run without arguments for interactive menu" -ForegroundColor DarkGray
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
