# common.ps1

# 设置控制台编码为 UTF-8，确保中文和特殊字符正确显示
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$script:EnableDebugLogs = $false  # 默认关闭

# 打印横幅
function Write-Banner {
    param(
        [ValidateSet("Install", "Run", "Uninstall")]
        [string]$Mode = "Run"
    )

    # 默认值
    $title = ""
    $subtitle = ""
    $logoColor = "White"

    switch ($Mode) {
        "Install" {
            $title = "📦 PsyText Analyst Installer"
            $subtitle = "⚙️ 自动配置 WSL2 发行版 · 加载预置服务栈 · 启动分析平台 "
            $logoColor = "Green"
        }
        "Run" {
            $title = "🧠 PsyText Analyst Runner (Start/Restart)"
            $subtitle = "🚀 启动或重启 PsyText 服务（WSL2 + Docker Engine）"
            $logoColor = "Cyan"
        }
        "Uninstall" {
            $title = "🗑️ PsyText Analyst Uninstaller"
            $subtitle = "🔥 完全移除 WSL 发行版和应用数据（谨慎操作！）"
            $logoColor = "Yellow"
        }
    }

    Write-Host ""
    Write-Host "  ██████╗ ██╗   ██╗████████╗███████╗██████╗     ████████╗ █████╗ ██╗  ██╗" -ForegroundColor $logoColor
    Write-Host "  ██╔══██╗██║   ██║╚══██╔══╝██╔════╝██╔══██╗    ╚══██╔══╝██╔══██╗██║ ██╔╝" -ForegroundColor $logoColor
    Write-Host "  ██████╔╝██║   ██║   ██║   █████╗  ██████╔╝       ██║   ███████║█████╔╝ " -ForegroundColor $logoColor
    Write-Host "  ██╔═══╝ ██║   ██║   ██║   ██╔══╝  ██╔══██╗       ██║   ██╔══██║██╔═██╗ " -ForegroundColor $logoColor
    Write-Host "  ██║     ╚██████╔╝   ██║   ███████╗██║  ██║       ██║   ██║  ██║██║  ██╗" -ForegroundColor $logoColor
    Write-Host "  ╚═╝      ╚═════╝    ╚═╝   ╚══════╝╚═╝  ╚═╝       ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝" -ForegroundColor $logoColor
    Write-Host ""
    Write-Host ("        {0}" -f $title) -ForegroundColor Cyan
    Write-Host ("        {0}" -f $subtitle) -ForegroundColor DarkGray
    Write-Host "        ℹ️ Script Version: v1.2.0 (2026-01-04)" -ForegroundColor Gray
    Write-Host "        📄 日志文件: $script:LogPath" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  ───────────────────────────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host ""
}

# 提示用户输入 Y/N 并返回布尔确认结果
function Confirm-Choice($prompt) {
    do { $response = Read-Host "$prompt (Y/N)" } until ($response -match "^[YyNn]$")
    return $response -match "^[Yy]$"
}

function Start-LogSession {
    if (-not (Get-Variable -Name LogPath -Scope Script -ErrorAction SilentlyContinue)) { return }
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $message = "=== [SESSION START] Script started at $timestamp ==="
    Add-Content -Path $script:LogPath -Value $message -Encoding UTF8 -ErrorAction SilentlyContinue
}

function End-LogSession {
    param([string]$Status = "Completed")
    if (-not (Get-Variable -Name LogPath -Scope Script -ErrorAction SilentlyContinue)) { return }
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $message = "=== [SESSION END] Status: $Status | Ended at $timestamp ==="
    Add-Content -Path $script:LogPath -Value $message -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Rotate-LogFileBySize {
    param(
        [Parameter(Mandatory)][string]$Path,
        [long]$MaxSizeBytes = 50MB,   # 默认 50MB
        [double]$KeepRatio = 0.8      # 超出后保留最近 80%
    )
    if (-not (Test-Path $Path)) { return }

    $fileInfo = Get-Item $Path
    if ($fileInfo.Length -le $MaxSizeBytes) { return }

    Write-Log "日志文件 $($fileInfo.Name) 超过 $($MaxSizeBytes / 1MB)MB，正在轮转..." -Level INFO -Prefix "日志管理"

    $content = Get-Content $Path -Raw -Encoding UTF8
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
    
    if ($bytes.Length -le $MaxSizeBytes) { return } # 双重保险

    # 计算需保留的字节数
    $keepBytes = [Math]::Min([long]($bytes.Length * $KeepRatio), $MaxSizeBytes)
    $startIndex = $bytes.Length - $keepBytes

    # 找到最近的换行符作为切割点（避免截断一行）
    $cutIndex = $startIndex
    while ($cutIndex -lt $bytes.Length - 1 -and $bytes[$cutIndex] -ne 10) { # 10 = \n
        $cutIndex++
    }
    if ($cutIndex -ge $bytes.Length) { $cutIndex = $startIndex }

    $trimmedBytes = $bytes[$cutIndex..($bytes.Length - 1)]
    $trimmedText = [System.Text.Encoding]::UTF8.GetString($trimmedBytes)

    Set-Content -Path $Path -Value $trimmedText -Encoding UTF8
    Write-Log "✅ 日志已轮转，保留最近 $(($trimmedBytes.Count / 1KB).ToString("F1")) KB。" -Level SUCCESS -Prefix "日志管理"
}

# 写入带时间戳的日志，并在控制台以颜色输出
function Write-Log {
    param(
        [Parameter(Mandatory)][string]$Message,
        [string]$Level = "INFO",
        [string]$Prefix = ""
    )
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $fullMessage = if ($Prefix) { "[$Prefix] $Message" } else { $Message }
    $line = "$timestamp [$Level] $fullMessage"

    # 控制台输出
    if ($Level -eq "DEBUG" -and -not $script:EnableDebugLogs) {
        return  # 不写日志也不输出
    }
    
    Add-Content -Path $script:LogPath -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    $consoleTime = $timestamp.Substring(11)
    $consoleLine = "$consoleTime [$Level] $fullMessage"

    $Color = switch ($Level) {
        "ERROR"   { "Red" }
        "WARN"    { "Yellow" }
        "SUCCESS" { "Green" }
        "INFO"    { "Cyan" }
        default   { "White" }
    }
    Write-Host $consoleLine -ForegroundColor $Color
}

# 抛出用户可见错误，显示提示信息并等待按键退出
function Throw-UserError($msg, $detail = "") {
    Write-Log -Message $msg -Level "ERROR"
    if ($detail) { Write-Host "       $detail" -ForegroundColor Yellow }
    Write-Host "`n按 Enter 键退出..." -ForegroundColor Cyan
    Read-Host | Out-Null
    exit 1  # ← 立即终止整个 PowerShell 进程
}

# 暂停脚本执行，等待用户按键继续
function Pause-ForUser {
    Write-Host "按任意键继续..." -ForegroundColor Cyan
    $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") | Out-Null
}

function Pause-AfterUninstall {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("Success", "Cancelled", "Failed")]
        [string]$Status,

        [string]$LogPath = $script:LogPath
    )

    Write-Host ""
    switch ($Status) {
        "Success" {
            Write-Host "🎉 卸载已完成！所有 PsyText 相关组件已从系统移除。" -ForegroundColor Green
        }
        "Cancelled" {
            Write-Host "ℹ️  卸载已取消。PsyText 环境未作任何更改。" -ForegroundColor Cyan
        }
        "Failed" {
            Write-Host "❌ 卸载过程中发生错误，部分资源可能未完全清理。" -ForegroundColor Red
            Write-Host "   请查看日志以获取详细信息。"
        }
    }

    if ($LogPath -and (Test-Path $LogPath)) {
        Write-Host ""
        Write-Host "📄 日志文件：" -ForegroundColor DarkGray
        Write-Host "   $LogPath" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "按任意键关闭此窗口..." -ForegroundColor Cyan
    try {
        $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") | Out-Null
    } catch {
        # 如果在非交互环境（如远程会话），降级为 Read-Host
        Read-Host
    }
}

function Copy-FileToWsl {
    param(
        [string]$Distro,
        [string]$LocalSourcePath,
        [string]$RemoteTargetPath  # 目标路径（含文件名）
    )

    if (-not (Test-Path $LocalSourcePath)) {
        throw "本地文件不存在: $LocalSourcePath"
    }

    # 提取远程目录（用于 mkdir -p）
    $remoteDir = Split-Path $RemoteTargetPath -Parent
    & wsl -d $Distro -u root mkdir -p "$remoteDir"

    # 复用你调通的二进制管道方式（type | tee），不经过 PowerShell 字符串
    & cmd /c "type `"$LocalSourcePath`" | wsl -d $Distro -u root tee '$RemoteTargetPath' >nul"

    # 验证文件是否写入成功
    & wsl -d $Distro -u root test -f "$RemoteTargetPath"
    if ($LASTEXITCODE -ne 0) {
        throw "文件写入失败：$RemoteTargetPath 未在 WSL 中创建"
    }
}

# 检查当前是否以管理员权限运行，否则抛出错误
function Assert-AdminPrivilege {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
		Write-Log -Message "必须以管理员身份运行！" -Level "ERROR" -Prefix "权限错误"
		Write-Log -Message "右键点击此脚本 → 选择“以管理员身份运行”" -Level "ERROR" -Prefix "权限错误"
        throw "权限不足"
    }
}

# 获取所有用户安装的 WSL 发行版列表
function Get-WslDistributions {
    [string[]]$distros = @()   # ← 强类型声明
    try {
        # 直接获取 wsl 输出的原始字节流，避免任何文本解析
        $tempFile = [System.IO.Path]::GetTempFileName()
        cmd /c "wsl -l -q --all > `"$tempFile`" 2>nul"

        if (Test-Path $tempFile) {
            # 以二进制读取，手动过滤 \0 和控制字符
            $bytes = [System.IO.File]::ReadAllBytes($tempFile)
            # 移除所有 0x00 字节，然后转为字符串
            $cleanBytes = @($bytes | Where-Object { $_ -ne 0 })
			$text = [System.Text.Encoding]::UTF8.GetString($cleanBytes)
			# $text = [System.Text.Encoding]::Default.GetString($cleanBytes)
            [System.IO.File]::Delete($tempFile)

            $lines = $text -split '\r?\n' | ForEach-Object { $_.Trim() } | Where-Object { 
                $_ -and 
                $_ -ne "NAME"
            }

            foreach ($line in $lines) {
                $distros += [string]$line
            }
        }
    } catch {
        Write-Log -Message "无法获取 WSL 发行版列表" -Level "WARN"
    }
    return $distros
}

# 检查指定名称的 WSL 发行版是否存在
function Test-WslDistributionExists { param([string]$Name); return [bool](Get-WslDistributions) -contains $Name }

# 静默注销指定名称的 WSL 发行版（智能处理“不存在”情况）
function Unregister-WslDistribution {
    param([string]$Name)

    Write-Log -Message "正在尝试注销 WSL 发行版（确保环境干净）: $Name" -Level "INFO"
    
    # 直接执行注销命令（不预先检查是否存在）
    & wsl --unregister "$Name" *>$null
    $exitCode = $LASTEXITCODE

    # 分析退出码语义
    if ($exitCode -eq 0) {
        Write-Log -Message "✅ 成功注销 WSL 发行版: $Name" -Level "SUCCESS"
    }
    elseif ($exitCode -eq -1 -or $exitCode -eq 4294967295) {
        # WSL 返回“发行版不存在”的标准错误码
        Write-Log -Message "ℹ️ 发行版 '$Name' 不存在，无需注销。" -Level "INFO"
    }
    else {
        # 其他错误：被占用、权限不足、系统忙等
        Write-Log -Message "⚠️ 注销 '$Name' 失败（退出码: $exitCode）。可能被其他进程占用或权限不足。" -Level "WARN"
    }
}

# 从 tar 文件导入 WSL 发行版到指定路径
function Import-WslDistribution {
    param([string]$Name, [string]$BasePath, [string]$TarFile, [int]$Version = 2)
	# === 1. 输入校验 ===
    if (-not (Test-Path $TarFile -PathType Leaf)) {
        Throw-UserError "WSL 镜像文件不存在" "路径: $TarFile"
    }
	
	$tarSize = (Get-Item $TarFile).Length
    if ($tarSize -lt 10MB) {  # Ubuntu 22.04 至少 ~500MB
        Write-Log -Message "⚠️ 镜像文件过小（仅 $($tarSize / 1MB):F1 MB），可能已损坏。" -Level "WARN" -Prefix "导入发行版镜像"
    }
	
    # 确保目标目录可写
    $parentDir = Split-Path $BasePath -Parent
    if (-not (Test-Path $parentDir)) {
        $null = New-Item -ItemType Directory -Path $parentDir -Force
    }

    if (-not (Test-Path $BasePath)) {
        $null = New-Item -ItemType Directory -Path $BasePath -Force
    }
	
	# === 2. 执行导入 ===
    Write-Log -Message "正在导入 WSL 发行版 '$Name'..." -Level "INFO" -Prefix "导入发行版镜像"
    Write-Log -Message "   源镜像: $(Split-Path $TarFile -Leaf) ($($tarSize / 1MB):F1 MB)" -Level "INFO" -Prefix "导入发行版镜像"
    Write-Log -Message "   目标路径: $BasePath" -Level "INFO" -Prefix "导入发行版镜像"

    # cmd /c "wsl --import `"$Name`" `"$BasePath`" `"$TarFile`" --version $Version >nul 2>&1"
	& wsl --import "$Name" "$BasePath" "$TarFile" --version $Version

    if ($LASTEXITCODE -ne 0) {
        Throw-UserError "WSL 导入失败" "请检查磁盘空间、权限及镜像完整性。退出码: $LASTEXITCODE"
    }
	
	# === 3. 关键：验证是否真的可用 ===
    Write-Log -Message "正在验证发行版 '$Name' 是否可运行..." -Level "INFO" -Prefix "导入发行版镜像"
    if (-not (Test-WslDistroReady  -Name $PSYTEXT_DISTRO)) {
		Throw-UserError "导入成功但无法启动发行版"
	}
    Write-Log -Message "✅ 发行版 '$Name' 导入并验证成功！" -Level "SUCCESS" -Prefix "导入发行版镜像"
}

# （通用）验证 PsyText-WSL 发行版是否处于可用状态
function Test-WslDistroReady {
	param([Parameter(Mandatory)][string]$Name)
    try {
        # 检查当前用户 + 系统级注册表
        $keys = @()
        $keys += Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss\*" -ErrorAction SilentlyContinue
        $keys += Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Lxss\*" -ErrorAction SilentlyContinue

        $regKey = $keys | Where-Object { $_.DistributionName -eq $Name -and $_.BasePath }
        
        if ($regKey -and (Test-Path "$($regKey.BasePath)\ext4.vhdx")) {
            return $true
        }
    } catch {
        return $false
    }
    $null = & wsl -d $Name -u root true 2>$null
    return ($LASTEXITCODE -eq 0)
}

# 检查 WSL 发行版中是否包含 PsyText 完整运行所需的核心组件（用于验证一体镜像）
function Test-PsyTextImageIntegrity {
    param(
        [string]$DistroName = $PSYTEXT_DISTRO
    )

    # Step 1: 检查关键文件是否存在
    $filesOk = @(
        & wsl -d $DistroName test -f /opt/psytext/docker-compose.yml
        & wsl -d $DistroName test -f /opt/psytext/cleanup.sh
    ) -notcontains $false

    if (-not $filesOk) {
        return $false
    }

    # Step 2: 获取所有本地镜像的 Repository 列表（格式: "repository"）
    $imageListRaw = & wsl -d $DistroName docker images --format "{{.Repository}}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $false  # Docker 未就绪或命令失败
    }

    # 转为字符串数组，去重、去空
    $repositories = @($imageListRaw -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -ne '<none>' } | Sort-Object -Unique)

    # Step 3: 检查是否包含必需的两个镜像 Repository
    $hasPsyText = $repositories -contains "psytext_analyst"
    $hasRedis   = $repositories -contains "redis"

    return $hasPsyText -and $hasRedis
}

# 在指定 WSL 发行版中执行 docker-compose restart
function Restart-PsyTextServices {
    param(
        [Parameter(Mandatory)][string]$DistroName
    )
    Write-Log -Message "重启 PsyText Analyst 服务..." -Level "INFO" -Prefix "服务"

    Wait-ForDockerReady -DistroName $DistroName

    $dockerCmd = "cd /opt/psytext && docker compose restart"
    $success = Invoke-WslLockedAction -DistroName $DistroName -ShellCommand $dockerCmd

    if (-not $success) {
        Throw-UserError "重启服务失败：docker compose restart 命令执行异常"
    }

    Wait-ForPsyTextAppReady -DistroName $DistroName

    Write-Log -Message "✅ 服务已成功重启！" -Level "SUCCESS" -Prefix "服务"
}

# 停止 PsyText 服务（使用 docker-compose down）
function Stop-PsyTextServices {
    param(
        [Parameter(Mandatory)][string]$DistroName
    )
    Write-Log -Message "停止 PsyText Analyst 服务..." -Level "INFO" -Prefix "服务"

    Wait-ForDockerReady -DistroName $DistroName

    $dockerCmd = "cd /opt/psytext && docker compose down"
    $success = Invoke-WslLockedAction -DistroName $DistroName -ShellCommand $dockerCmd

    if (-not $success) {
        Write-Log "❌ docker compose down 执行失败" -Level "ERROR" -Prefix "服务"
        Throw-UserError "停止服务失败"
    }

    Write-Log -Message "✅ 服务已成功停止。" -Level "SUCCESS" -Prefix "服务"
}

# 显示 PsyText Analyst 服务的实时日志
function Show-PsyTextRealtimeLogs {
    param([string]$DistroName = "PsyText-WSL")

    Write-Host "`n📡 正在连接实时日志流（来自容器 'psytext_analyst'）..." -ForegroundColor Cyan
    Write-Host "   💡 按 Ctrl+C 可返回主菜单" -ForegroundColor Magenta
    Write-Host ""

    try {
        # 启动一个阻塞的实时日志进程（由 WSL 内部执行）
        & wsl -d $DistroName -u root docker logs -f psytext_analyst --timestamps
    } catch {
        Write-Host "⚠️ 实时日志中断或容器未运行。" -ForegroundColor Red
    }

    Write-Host "`n↩️ 已返回主菜单。" -ForegroundColor Green
}

# 启动 PsyText Analyst 服务：在 WSL 中执行 docker-compose up -
function Start-PsyTextServices {
    param(
        [Parameter(Mandatory)][string]$DistroName
    )
    Write-Log -Message "启动 PsyText Analyst 服务..." -Level "INFO" -Prefix "服务"

    Wait-ForDockerReady -DistroName $DistroName

    $dockerCmd = "cd /opt/psytext && docker compose up -d"
    $success = Invoke-WslLockedAction -DistroName $DistroName -ShellCommand $dockerCmd

    if (-not $success) {
        Throw-UserError "启动服务失败：docker compose up -d 命令执行异常"
    }

    Wait-ForPsyTextAppReady -DistroName $DistroName

    Write-Log -Message "✅ 服务已成功启动！" -Level "SUCCESS" -Prefix "服务"
    Write-Host "🔗 访问地址: http://localhost:8000/" -ForegroundColor Magenta
    Write-Host ""
}

# 打开数据目录
function Open-PsyTextDataDirectory {
    param([string]$DistroName = "PsyText-WSL")
    
    $wslPath = "\\wsl$\$DistroName\opt\psytext\data"
    if (Test-Path $wslPath) {
        Write-Host "📁 正在打开数据目录: $wslPath" -ForegroundColor Gray
        Start-Process explorer.exe $wslPath
        Write-Host "📁 数据目录已打开。" -ForegroundColor Green
    } else {
        Write-Host "⚠️ 数据目录不存在: $wslPath" -ForegroundColor Yellow
    }
}

# 检查指定 WSL 发行版是否存在
function Assert-WslDistroExists {
    param(
        [Parameter(Mandatory)][string]$DistroName
    )

    $existing = Get-WslDistributions
    if ($DistroName -notin $existing) {
        Throw-UserError "未找到 WSL 发行版：$DistroName" "请先运行“安装环境.bat”完成部署。"
    }
}

# 加载镜像文件
function Load-PsyTextContainerImages {
    param(
        [Parameter(Mandatory)][string]$DistroName,
        [Parameter(Mandatory)][string]$HostScriptRoot
    )
    $hostImageDir = Join-Path $HostScriptRoot "images\tool-images\windows"
    if (-not (Test-Path $hostImageDir)) {
        Throw-UserError "镜像目录不存在" "请确认工具包结构完整。路径: $hostImageDir"
    }

    $requiredImages = @("psytext_analyst_latest.tar", "redis_7_alpine.tar")
    foreach ($img in $requiredImages) {
        if (-not (Test-Path "$hostImageDir\$img")) {
            Throw-UserError "缺少镜像文件" "$img 未找到"
        }
    }

    Write-Log -Message "正在将镜像文件复制到 WSL 内部..." -Level "INFO" -Prefix "镜像加载"
    $wslImageDir = "/opt/psytext/images"
    & wsl -d $DistroName -u root mkdir -p $wslImageDir

    foreach ($imgFile in Get-ChildItem "$hostImageDir\*.tar") {
        Write-Host " 📦 $($imgFile.Name)" -ForegroundColor Gray
        # 使用二进制管道安全复制（避免文本编码问题）
        & cmd /c "type `"$($imgFile.FullName)`" | wsl -d $DistroName -u root tee '$wslImageDir/$($imgFile.Name)' >nul"
        if ($LASTEXITCODE -ne 0) {
            Throw-UserError "镜像文件复制失败" "无法将 $($imgFile.Name) 写入 WSL"
        }
    }

    Write-Log -Message "正在通过 WSL 内部 Docker 加载容器镜像..." -Level "INFO" -Prefix "镜像加载"
    foreach ($img in $requiredImages) {
        & wsl -d $DistroName -u root sh -c "docker load -i '$wslImageDir/$img'"
        if ($LASTEXITCODE -ne 0) {
            Throw-UserError "WSL 内 Docker 镜像加载失败" "请检查磁盘空间或镜像完整性。"
        }
    }
    Write-Log -Message "✅ 所有容器镜像已成功加载到 WSL 内部 Docker。" -Level "SUCCESS" -Prefix "镜像加载"
}

# 设置 WSL 时区
function Set-WslTimezone {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$DistroName
    )

    Write-Log "正在配置 WSL 时区..." -Level INFO -Prefix "时区设置"

    $tz = (Get-TimeZone).Id
    $ianaTzMap = @{
        "China Standard Time"           = "Asia/Shanghai"
        "Pacific Standard Time"         = "America/Los_Angeles"
        "Eastern Standard Time"         = "America/New_York"
        "GMT Standard Time"             = "Europe/London"
        "Central Europe Standard Time"  = "Europe/Berlin"
        "Tokyo Standard Time"           = "Asia/Tokyo"
        "Korea Standard Time"           = "Asia/Seoul"
        "AUS Eastern Standard Time"     = "Australia/Sydney"
        # 可按需扩展
    }

    $ianaTz = $ianaTzMap[$tz]
    if (-not $ianaTz) {
        Write-Log "⚠️ 未知 Windows 时区 '$tz'，默认使用 UTC" -Level WARN -Prefix "时区设置"
        $ianaTz = "UTC"
    }

    # 设置 /etc/localtime 和 /etc/timezone
    & wsl -d $DistroName -u root ln -sf "/usr/share/zoneinfo/$ianaTz" /etc/localtime 2>$null | Out-Null
    & wsl -d $DistroName -u root sh -c "echo '$ianaTz' > /etc/timezone" 2>$null | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Log "✅ WSL 时区已设为: $ianaTz" -Level SUCCESS -Prefix "时区设置"
    } else {
        Write-Log "❌ 设置 WSL 时区失败" -Level ERROR -Prefix "时区设置"
        Throw-UserError "无法配置 WSL 时区，请确保 WSL 已正确安装并运行。"
    }
}

# 同步 WSL 系统时间
function Sync-WslTime {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$DistroName
    )

    Write-Log "正在同步 WSL 系统时间..." -Level INFO -Prefix "时间同步"

    # 方法1: 使用 hwclock（推荐）
    & wsl -d $DistroName -u root hwclock --hctosys *>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "✅ 时间已通过 hwclock 同步" -Level SUCCESS -Prefix "时间同步"
        return
    }

    # 方法2: 回退到 date -s（需要 GNU coreutils）
    Write-Log "hwclock 失败，尝试使用 date 命令回退..." -Level WARN -Prefix "时间同步"
    $unixTime = [int](Get-Date -UFormat %s)
    & wsl -d $DistroName -u root date -s "@$unixTime" *>$null

    if ($LASTEXITCODE -eq 0) {
        Write-Log "✅ 时间已通过 date 命令同步" -Level SUCCESS -Prefix "时间同步"
    } else {
        Write-Log "⚠️ 时间同步失败（不影响服务启动，但日志时间可能不准）" -Level WARN -Prefix "时间同步"
    }
}

# 重启 Docker 服务
function Restart-DockerService {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$DistroName
    )

    Write-Log "正在重启 WSL 内的 Docker 服务..." -Level INFO -Prefix "Docker"

    & wsl -d $DistroName -u root systemctl restart docker

    if ($LASTEXITCODE -eq 0) {
        Start-Sleep -Seconds 3
        Write-Log "✅ Docker 服务已重启" -Level SUCCESS -Prefix "Docker"
    } else {
        Write-Log "❌ 无法重启 Docker 服务。请确认 Docker 已在 WSL 中安装并启用。" -Level ERROR -Prefix "Docker"
        Throw-UserError "Docker 服务重启失败"
    }
}

# 等待 Docker 就绪
function Wait-ForDockerReady {
    param(
        [Parameter(Mandatory)][string]$DistroName,
        [int]$TimeoutSeconds = 30,
        [int]$RetryIntervalSeconds = 1
    )

    Write-Log -Message "⏳ 等待 WSL 发行版 '$DistroName' 中的 Docker daemon 就绪..." -Level "DEBUG" -Prefix "Docker"

    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        # 在 appuser 下执行 docker info，避免权限问题
        & wsl -d $DistroName -u appuser docker info --format '{{.ServerVersion}}' 2>$null | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Log -Message "✅ Docker daemon 已就绪（版本: $(wsl -d $DistroName -u appuser docker version --format '{{.Server.Version}}' 2>$null))" -Level "SUCCESS" -Prefix "Docker"
            return
        }

        Start-Sleep -Seconds $RetryIntervalSeconds
        $elapsed += $RetryIntervalSeconds
        Write-Log -Message "⏳ 仍在等待 Docker... ($elapsed/$TimeoutSeconds 秒)" -Level "DEBUG" -Prefix "Docker"
    }

    Throw-UserError "❌ 超时：WSL 发行版 '$DistroName' 中的 Docker daemon 在 $TimeoutSeconds 秒内未就绪。请检查 systemd 是否启用、Docker 是否安装。"
}

# 等待 PsyText 应用 HTTP 服务真正可用（应用层就绪）
function Wait-ForPsyTextAppReady {
    <#
    .SYNOPSIS
        等待 PsyText 应用业务层就绪（通过 http://localhost:8000/api/healthz 判断）
    .DESCRIPTION
        直接从 Windows 宿主机发起 HTTP 请求，避免 WSL 内部 curl 的环境依赖问题。
        仅当响应状态码为 200 且 JSON 体包含 {"status": "ready"} 时视为就绪。
    .PARAMETER DistroName
        WSL 发行版名称（仅用于日志，实际检测不依赖它）
    .PARAMETER TimeoutSeconds
        最大等待时间（秒），默认 60
    .PARAMETER QuickCheckOnly
        若为 $true，则只做一次快速检查（不循环等待），用于保活脚本的轻量探测
    .OUTPUTS
        [bool] - 仅当 QuickCheckOnly=$true 时返回布尔值；否则无返回（成功则静默，超时则警告）
    #>
    param(
        [Parameter(Mandatory)][string]$DistroName,
        [int]$TimeoutSeconds = 60,
        [switch]$QuickCheckOnly
    )

    # 👇 显式加载 System.Net.Http 程序集（PowerShell 5.1 必需）
    Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue

    $healthUrl = "http://localhost:8000/api/healthz"
    $httpClient = New-Object System.Net.Http.HttpClient
    $httpClient.Timeout = New-TimeSpan -Seconds 5

    if ($QuickCheckOnly) {
        try {
            $response = $httpClient.GetAsync($healthUrl).Result
            if ($response.StatusCode -eq 200) {
                $content = $response.Content.ReadAsStringAsync().Result
                if ($content -match '"status"\s*:\s*"ready"') {
                    return $true
                }
            }
        } catch {
            # Ignore all errors in quick check
        } finally {
            $httpClient.Dispose()
        }
        return $false
    }

    # === 正常等待模式 ===
    Write-Log -Message "⏳ 等待 PsyText 应用初始化完成（通过 /healthz 检查业务就绪）..." -Level "INFO" -Prefix "应用就绪"

    $startTime = Get-Date
    $timeoutTime = $startTime.AddSeconds($TimeoutSeconds)
    $intervalMs = 500  # 高频轮询

    while ((Get-Date) -lt $timeoutTime) {
        try {
            $response = $httpClient.GetAsync($healthUrl).Result
            if ($response.StatusCode -eq 200) {
                $content = $response.Content.ReadAsStringAsync().Result
                if ($content -match '"status"\s*:\s*"ready"') {
                    Write-Log -Message "✅ PsyText 应用已完全就绪！" -Level "SUCCESS" -Prefix "应用就绪"
                    $httpClient.Dispose()
                    return
                }
            }
        } catch {
            # Silent retry on any error (connection refused, timeout, etc.)
        }

        Start-Sleep -Milliseconds $intervalMs
    }

    # 超时不抛错，仅警告
    Write-Log -Message "⚠️ 超时：应用在 $TimeoutSeconds 秒内未通过 /healthz 就绪检查" -Level "WARN" -Prefix "应用就绪"
    $httpClient.Dispose()
}

# WSL 锁
function Invoke-WslLockedAction {
    <#
    .SYNOPSIS
        在 WSL 内通过 flock 执行带锁的 Shell 命令，避免并发
    .PARAMETER DistroName
        WSL 发行版名称
    .PARAMETER ShellCommand
        要执行的 Shell 命令
    .PARAMETER LockFile
        锁文件路径（默认在 runtime 目录）
    .OUTPUTS
        [bool] - 成功获取锁并执行返回 $true，否则 $false
    #>
    param(
        [Parameter(Mandatory)][string]$DistroName,
        [Parameter(Mandatory)][string]$ShellCommand,
        [string]$LockFile = "/opt/psytext/runtime/service.lock"
    )
    # 确保 runtime 目录存在且 appuser 可写（兜底）
    & wsl -d $DistroName -u root mkdir -p "/opt/psytext/runtime" | Out-Null
    & wsl -d $DistroName -u root chown appuser:appuser "/opt/psytext/runtime" | Out-Null

    # 构造 flock 命令（已验证无转义问题）
    $flockCmd = "exec 200>'$LockFile'`n" +
                "if ! flock -n 200; then`n" +
                "    echo 'ERROR: Failed to acquire lock' >&2`n" +
                "    exit 1`n" +
                "fi`n" +
                "$ShellCommand`n" +
                "EXIT_CODE=`$?`n" +
                "flock -u 200`n" +
                "exit `$EXIT_CODE"

    # Base64 编码确保安全传输
    $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($flockCmd))
    $decodeAndRun = "echo '$b64' | base64 -d | bash"

    & wsl -d $DistroName -u appuser bash -c $decodeAndRun
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Log "⚠️ WSL 命令执行失败（ExitCode: $exitCode）" -Level WARN -Prefix "WSL"
    }
    return ($exitCode -eq 0)
}

# 备份
function Backup-PsyTextDataFromWsl {
    param(
        [string]$BackupDir,
        [ref]$Success
    )
    $Success.Value = $false

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupFileName = "psytext-data-backup-$timestamp.tar"
    $hostBackupPath = Join-Path $BackupDir $backupFileName
    $null = New-Item -ItemType Directory -Path $BackupDir -Force

    Write-Host "`n💾 正在从 WSL 备份应用数据和 Redis 数据..." -ForegroundColor Cyan
    Write-Log -Message "开始执行 WSL 数据备份（.tar 格式）..." -Level "INFO"

    try {
        # 构造 WSL 中的输出路径（/mnt/c/...）
        $drive = $BackupDir.Substring(0, 1).ToLower()
        $pathInWsl = $BackupDir.Substring(2).Replace('\', '/')
        $wslOutputPath = "/mnt/$drive/$pathInWsl/$backupFileName"

        # 使用单引号 Here-String 避免 PowerShell 展开 $(...)
        # 用 {0} 占位，后续安全注入路径
        $scriptTemplate = @'
#!/bin/sh
set -e

out_file='{0}'

# 创建唯一临时目录（不依赖 mktemp）
temp_dir="/tmp/psytext_backup_$(date +%s)_$$"
mkdir -p "$temp_dir"
chmod 700 "$temp_dir"
trap 'rm -rf "$temp_dir"' EXIT

# 备份应用数据
if [ -d /opt/psytext/data ] && [ -n "$(ls -A /opt/psytext/data 2>/dev/null)" ]; then
    cp -r /opt/psytext/data "$temp_dir/"
fi

# 备份 Redis 持久化数据
redis_vol=/var/lib/docker/volumes/psytext_redis_data/_data
if [ -d "$redis_vol" ] && [ -n "$(ls -A "$redis_vol" 2>/dev/null)" ]; then
    mkdir -p "$temp_dir/redis-data"
    cp -r "$redis_vol"/. "$temp_dir/redis-data/"
fi

# 打包：如果有数据就打包，否则创建空 tar
if [ -d "$temp_dir/data" ] || [ -d "$temp_dir/redis-data" ]; then
    tar -cf "$out_file" -C "$temp_dir" .
else
    tar -cf "$out_file" -T /dev/null
fi

chmod 644 "$out_file"
echo "Backup completed to $out_file"
'@

        # 安全转义单引号（防止路径注入破坏 shell 脚本）
        $safeWslPath = $wslOutputPath -replace "'", "'\''"
        $scriptContent = $scriptTemplate -f $safeWslPath

        # 写入临时脚本到 WSL
        $tempScript = "/tmp/backup_script_$timestamp.sh"
        $scriptBytes = [System.Text.Encoding]::UTF8.GetBytes($scriptContent)
        $base64Script = [Convert]::ToBase64String($scriptBytes)
        & wsl -d PsyText-WSL -u root sh -c "echo '$base64Script' | base64 -d > '$tempScript' && chmod +x '$tempScript'"

        # 执行备份脚本，并捕获真实输出
        $output = & wsl -d PsyText-WSL -u root sh -c "$tempScript" 2>&1
        $exitCode = $LASTEXITCODE

        # 清理临时脚本
        & wsl -d PsyText-WSL -u root rm -f "$tempScript" *>$null

        if ($exitCode -eq 0 -and (Test-Path $hostBackupPath)) {
            $size = (Get-Item $hostBackupPath).Length
            if ($size -gt 100) {
                Write-Log -Message "✅ 备份成功: $hostBackupPath ($([math]::Round($size / 1KB, 1)) KB)" -Level "SUCCESS"
            } else {
                Write-Log -Message "⚠️ 备份完成，但无有效数据（空备份）" -Level "WARN"
            }
            $Success.Value = $true
        } else {
            $errorMessage = ($output | Out-String).Trim()
            throw "WSL 备份失败。退出码: $exitCode。详细错误: $errorMessage"
        }
    } catch {
        Write-Log -Message "WSL 数据备份失败: $_" -Level "ERROR"
        if (Test-Path $hostBackupPath) {
            Remove-Item $hostBackupPath -ErrorAction SilentlyContinue
        }
        throw
    }
}

# === WSL 存储位置管理 ===
# 获取用于记录 WSL 存储路径的隐藏文件路径（.wsl_location）
function Get-WslStorageLocationFile {
    param([string]$ScriptRoot)
    return Join-Path $ScriptRoot ".wsl_location"
}

# 将选定的 WSL 根目录路径持久化保存到 .wsl_location 文件
function Save-WslStorageLocation {
    param(
        [Parameter(Mandatory)][string]$ScriptRoot,
        [Parameter(Mandatory)][string]$WslRootPath
    )
    $locationFile = Get-WslStorageLocationFile -ScriptRoot $ScriptRoot
    Set-Content -Path $locationFile -Value $WslRootPath.Trim() -Encoding UTF8
    Write-Log -Message "已保存 WSL 存储路径: $WslRootPath" -Level "INFO" -Prefix "存储路径持久化"
}

# 从 .wsl_location 文件加载之前保存的 WSL 存储路径（若存在且有效）
function Load-WslStorageLocation {
    param([string]$ScriptRoot)
    $locationFile = Get-WslStorageLocationFile -ScriptRoot $ScriptRoot
    if (Test-Path $locationFile) {
        $path = (Get-Content $locationFile -Raw).Trim()
        if (Test-Path $path) {
            return $path
        } else {
            Write-Log -Message "记录的 WSL 路径不存在: $path" -Level "WARN" -Prefix "存储加载"
        }
    }
    return $null
}

# 在预设驱动器列表中查找满足最小空间要求的非系统盘
function Find-AvailableDrive {
    param(
        [string[]]$PreferredDrives = @("D", "E", "F", "G", "H", "I"),
        [long]$MinFreeBytes = 20GB
    )
    foreach ($driveLetter in $PreferredDrives) {
        try {
            $vol = Get-Volume -DriveLetter $driveLetter -ErrorAction SilentlyContinue
            if ($vol -and $vol.DriveLetter -and $vol.SizeRemaining -ge $MinFreeBytes) {
                return "$($vol.DriveLetter):"
            }
        } catch {}
    }
    return "C:"
}

# 自动选择 WSL 存储根目录（优先复用历史记录，否则自动选择并保存）
function Select-WslStorageRoot {
    param(
        [Parameter(Mandatory)][string]$ScriptRoot,
        [long]$MinFreeBytes = 20GB
    )
	Write-Log -Message "正在选定存储位置..." -Level "INFO" -Prefix "存储选择"
    # 先尝试加载已有记录
    $existing = Load-WslStorageLocation -ScriptRoot $ScriptRoot
    if ($existing) {
        Write-Log -Message "复用已记录的 WSL 存储路径: $existing" -Level "INFO" -Prefix "存储选择"
        return $existing
    }

    # 否则自动选择
    $drive = Find-AvailableDrive -MinFreeBytes $MinFreeBytes
    $wslRoot = "$drive\wsl"

    if ($drive -eq "C:") {
        Write-Log -Message "未找到满足 $($MinFreeBytes / 1GB) GB 的非系统盘，使用 C:\wsl" -Level "WARN" -Prefix "存储选择"
    } else {
        $freeGB = [math]::Round((Get-Volume -DriveLetter $drive.TrimEnd(":")).SizeRemaining / 1GB, 1)
        Write-Log -Message "选定存储位置: $wslRoot （可用空间: $freeGB GB）" -Level "SUCCESS" -Prefix "存储选择"
    }

    # 保存选择结果
    Save-WslStorageLocation -ScriptRoot $ScriptRoot -WslRootPath $wslRoot
    return $wslRoot
}