# install.ps1

# === 脚本根目录（必须在函数外部定义！）===
$ScriptRoot = Split-Path $MyInvocation.MyCommand.Path -Parent
. (Join-Path $ScriptRoot "common.ps1")  # ← 关键：加载公共函数
# 发行版名称枚举
Set-Variable -Name PSYTEXT_DISTRO -Value "PsyText-WSL" -Option Constant
# === 控制标志：是否已通过一体镜像完成部署（避免后续冗余操作）===
$script:UsedPrebuiltImage = $false

$ScriptName = [System.IO.Path]::GetFileNameWithoutExtension($MyInvocation.MyCommand.Name)
$LogDir = Join-Path $ScriptRoot "logs"
$null = New-Item -ItemType Directory -Path $LogDir -Force
$script:LogPath = Join-Path $LogDir "$ScriptName.log"


# 仅轮询等待某个发行版出现在 wsl -l 列表中
function Wait-WslDistroRegistered {
    param(
        [Parameter(Mandatory)][string]$DistroName,
        [int]$TimeoutSeconds = 600
    )
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        $null = & wsl -l -q 2>$null  # 刷新状态
        if (Test-WslDistributionExists -Name $DistroName) {
            return $true
        }
        if ($elapsed -gt 0 -and $elapsed % 20 -eq 0) {
            $min = [Math]::Floor($elapsed / 60)
            $sec = $elapsed % 60
            $ts = if ($min -gt 0) { "$min 分 $sec 秒" } else { "$sec 秒" }
            Write-Log -Message "仍在等待 '$DistroName' 完成初始化...（已等待 $ts）" -Level "INFO"
        }
        Start-Sleep -Seconds 10
        $elapsed += 10
    }
    return $false
}

# 检查管理员权限并启用 WSL2，必要时提示重启
function Initialize-Environment {
    Write-Log -Message "正在验证管理员权限..." -Level "INFO" -Prefix "环境初始化"
    Assert-AdminPrivilege
    Write-Log -Message "✅ 管理员权限已确认" -Level "SUCCESS" -Prefix "环境初始化"
	
    Write-Log -Message "检查并启用 WSL2 子系统..." -Level "INFO" -Prefix "WSL 启用"
    $wslFunctional = $false
    try {
        $null = wsl -l -q 2>&1
        if ($LASTEXITCODE -eq 0) { $wslFunctional = $true }
    } catch {}

    if (-not $wslFunctional) {
        Write-Log -Message "WSL 功能未启用，正在安装 WSL2 内核..." -Level "WARN" -Prefix "WSL 启用"
        wsl --install --no-distribution
        Write-Log -Message "⚠️ 系统需要重启才能完成 WSL 安装！" -Level "WARN" -Prefix "WSL 启用"
        Write-Host "📌 请保存所有工作，重启计算机后，再次以管理员身份运行本脚本。" -ForegroundColor Yellow
        Write-Host "`n按 Enter 键退出..." -ForegroundColor Cyan
        Read-Host | Out-Null
        exit 1
    }
    wsl --set-default-version 2 2>$null | Out-Null
    Write-Log -Message "✅ WSL2 已启用并设为默认版本" -Level "SUCCESS" -Prefix "WSL 启用"
}

# 创建或复用专用的 PsyText-WSL 发行版，支持从本地或官方源获取镜像
function Provision-PsyTextWslDistro {
    param([string]$WslRoot)

    # 重置标志（防止残留）
    $script:UsedPrebuiltImage = $false

    $distroPath = "$WslRoot\$PSYTEXT_DISTRO"
    $fullImageTar = Join-Path $ScriptRoot "images\tool-images\linux\psytext-full.tar"
    $localWslTar = Join-Path $ScriptRoot "images\tool-images\linux\ubuntu-22.04-wsl.tar"

    # === 检查是否已完全就绪（包括服务）===
    if (Test-WslDistroReady -Name $PSYTEXT_DISTRO) {
        try {
            $regKey = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss\*" -ErrorAction SilentlyContinue |
                Where-Object { $_.DistributionName -eq $PSYTEXT_DISTRO -and $_.BasePath }
            if ($regKey) {
                $curr = (Resolve-Path "$($regKey.BasePath)\ext4.vhdx" -EA SilentlyContinue).Path
                $exp = (Resolve-Path "$distroPath\ext4.vhdx" -EA SilentlyContinue).Path
                if ($curr -eq $exp) {
                    Write-Log "发行版已存在，跳过创建。" -Level INFO -Prefix "发行版创建"
                    return
                }
            }
        } catch { }
    }

    # === 清理旧实例 ===
    Write-Log "正在清理现有发行版（如有）并准备重建..." -Level INFO -Prefix "发行版创建"
    Unregister-WslDistribution $PSYTEXT_DISTRO
    if (Test-Path $distroPath) { Remove-Item $distroPath -Recurse -Force -EA SilentlyContinue }
    $null = New-Item -ItemType Directory -Path $distroPath -Force

    # === 尝试使用一体镜像 ===
    if (Test-Path $fullImageTar) {
        Write-Log "检测到一体式镜像包 'psytext-full.tar'，正在导入..." -Level INFO -Prefix "发行版创建"
        Import-WslDistribution -Name $PSYTEXT_DISTRO -BasePath $distroPath -TarFile $fullImageTar

        if (Test-PsyTextImageIntegrity -DistroName $PSYTEXT_DISTRO) {
            Write-Log "✅ 一体镜像验证通过：关键文件与容器镜像均存在。" -Level SUCCESS -Prefix "发行版创建"
            $script:UsedPrebuiltImage = $true
            return
        } else {
            Write-Log "❌ 一体镜像服务未响应，回退到基础镜像流程..." -Level ERROR -Prefix "发行版创建"
            Unregister-WslDistribution $PSYTEXT_DISTRO
        }
    }

    # === 回退到完整流程===
    if (-not (Test-Path $localWslTar)) {
        Write-Log "未找到预置的 Ubuntu-22.04 基础镜像（$localWslTar）" -Level WARN -Prefix "发行版创建"
        $systemDistro = "Ubuntu-22.04"
        $shouldUnregisterAfterExport = $false

        if (Test-WslDistributionExists $systemDistro -and (Test-WslDistroReady -Name $systemDistro)) {
            Write-Log "✅ 复用系统中已有的 '$systemDistro' 进行导出..." -Level INFO -Prefix "发行版创建"
            $shouldUnregisterAfterExport = $false
        } else {
            Write-Log "系统中无可用 '$systemDistro'，正在安装官方版本用于导出..." -Level INFO -Prefix "发行版创建"
            Unregister-WslDistribution $systemDistro
            Start-Process -FilePath "wsl.exe" -ArgumentList "--install", "-d", $systemDistro -WindowStyle Hidden -Wait:$false

            if (-not (Wait-WslDistroRegistered -DistroName $systemDistro -TimeoutSeconds 600)) {
                Throw-UserError "超时：无法安装 '$systemDistro' 用于导出。"
            }
            $shouldUnregisterAfterExport = $true
        }

        $linuxImageDir = Join-Path $ScriptRoot "images\tool-images\linux"
        $null = New-Item -ItemType Directory -Path $linuxImageDir -Force
        Write-Log "正在导出基础镜像并缓存到工具包目录：$localWslTar" -Level INFO -Prefix "发行版创建"
        & wsl --export "$systemDistro" "$localWslTar"
        if ($LASTEXITCODE -ne 0) {
            Throw-UserError "导出发行版失败（退出码: $LASTEXITCODE）"
        }
        Write-Log "✅ 已缓存 $systemDistro 镜像至：$localWslTar" -Level SUCCESS -Prefix "发行版创建"

        if ($shouldUnregisterAfterExport) {
            Unregister-WslDistribution $systemDistro
            Write-Log "已清理临时安装的 '$systemDistro'。" -Level INFO -Prefix "发行版创建"
        }
    }

    Import-WslDistribution -Name $PSYTEXT_DISTRO -BasePath $distroPath -TarFile $localWslTar
    Write-Log "专用发行版 '$PSYTEXT_DISTRO' 已基于基础镜像准备就绪。" -Level INFO -Prefix "发行版创建"
    # 注意：此处不设置 $script:UsedPrebuiltImage = $true，保持为 false
}

# ===================================================================
# 部署并启用 PsyText 自动清理任务（每 8 小时）
# ===================================================================
function Deploy-CleanupScript {
    param(
        [string]$DistroName,
        [string]$HostScriptRoot
    )

    $remoteCleanupPath = "/opt/psytext/cleanup.sh"
    & wsl -d $DistroName test -f $remoteCleanupPath
    if ($LASTEXITCODE -ne 0) {
        Write-Log -Message "⚠️ cleanup.sh 未部署，跳过 cron 配置。" -Level "WARN" -Prefix "清理脚本"
        return
    }

    # 启动 cron 并配置任务（逻辑不变）
    & wsl -d $DistroName sudo service cron start 2>$null | Out-Null

    $currentCrontabRaw = & wsl -d $DistroName crontab -l 2>$null | Out-String
    $currentLines = @($currentCrontabRaw -split "`n" | ForEach-Object { $_.TrimEnd() } | Where-Object { $_ -ne '' })

    $jobExists = $false
    foreach ($line in $currentLines) {
        if ($line -match [regex]::Escape($remoteCleanupPath)) {
            $jobExists = $true
            break
        }
    }

    if (-not $jobExists) {
        $allLines = $currentLines + "0 */8 * * * $remoteCleanupPath >> /dev/null 2>&1"
        $cronText = ($allLines -join "`n") + "`n"

        $bytes = [System.Text.Encoding]::UTF8.GetBytes($cronText)
        $b64 = [Convert]::ToBase64String($bytes)
        $remoteCronFile = "/tmp/psytext_cron_job.txt"
        $installCmd = "echo '$b64' | base64 -d > '$remoteCronFile' && crontab '$remoteCronFile'"
        & wsl -d $DistroName sh -c $installCmd

        if ($LASTEXITCODE -eq 0) {
            Write-Log -Message "✅ 自动清理任务已配置：每 8 小时执行一次" -Level "SUCCESS" -Prefix "清理脚本"
        } else {
            Write-Log -Message "❌ 自动清理任务配置失败" -Level "ERROR" -Prefix "清理脚本"
        }
    } else {
        Write-Log -Message "自动清理任务已存在，跳过重复配置。" -Level "INFO" -Prefix "清理脚本"
    }
}

# 安装原生 Docker Engine
function Install-DockerInWsl {
    param([string]$DistroName)
    Write-Log -Message "正在 WSL2 发行版 '$DistroName' 中安装原生 Docker Engine..." -Level "INFO"
    
    $setupScript = @'
set -e
export DEBIAN_FRONTEND=noninteractive

if ! id -u appuser >/dev/null 2>&1; then
    useradd -m -s /bin/bash appuser
    echo 'appuser ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
fi

apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

usermod -aG docker appuser

if ! pgrep -x dockerd > /dev/null; then
    nohup dockerd --data-root /var/lib/docker > /var/log/docker.log 2>&1 &
    sleep 5
fi
'@

    $tempScript = "/tmp/setup_docker.sh"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($setupScript)
    $b64 = [Convert]::ToBase64String($bytes)
    & wsl -d $DistroName -u root sh -c "echo '$b64' | base64 -d > '$tempScript' && chmod +x '$tempScript' && '$tempScript'"
    
    if ($LASTEXITCODE -ne 0) {
        Throw-UserError "WSL 内 Docker 安装或启动失败"
    }
    Write-Log -Message "✅ 原生 Docker Engine 已在 '$DistroName' 中安装并启动。" -Level "SUCCESS"
}

# === 创建统一数据目录 ===
function Setup-PsyTextAppEnv {
    param(
        [string]$DistroName,
        [string]$HostScriptRoot
    )
    Write-Log -Message "正在部署 PsyText 运行时环境到 WSL..." -Level "INFO" -Prefix "应用环境"

    & wsl -d $DistroName -u root mkdir -p /opt/psytext
    if ($LASTEXITCODE -ne 0) {
        Throw-UserError "无法创建 WSL 中的 /opt/psytext 目录"
    }

    & wsl -d $DistroName -u root mkdir -p /opt/psytext/runtime
    if ($LASTEXITCODE -ne 0) {
        Throw-UserError "无法创建 WSL 中的 /opt/psytext/runtime 目录"
    }
    & wsl -d $DistroName -u root chown appuser:appuser /opt/psytext/runtime

    # 1. docker-compose.yml
    $ComposeSource = Join-Path $HostScriptRoot "scripts\start\windows\docker-compose.yml"
    if (-not (Test-Path $ComposeSource)) {
        Throw-UserError "缺失关键文件: docker-compose.yml 未在 scripts/start/windows/ 中找到！"
    }
    Copy-FileToWsl -Distro $DistroName -LocalSourcePath $ComposeSource -RemoteTargetPath "/opt/psytext/docker-compose.yml"
    Write-Log -Message "✅ 已部署 docker-compose.yml 到 /opt/psytext/" -Level "SUCCESS" -Prefix "应用环境"

    # 2. cleanup.sh（直接用通用函数 + 单独加执行权限）
    $CleanupSource = Join-Path $HostScriptRoot "scripts\cleanup\cleanup.sh"
    if (Test-Path $CleanupSource) {
        Copy-FileToWsl -Distro $DistroName -LocalSourcePath $CleanupSource -RemoteTargetPath "/opt/psytext/cleanup.sh"
        & wsl -d $DistroName -u root chmod +x "/opt/psytext/cleanup.sh"
        Write-Log -Message "✅ 已部署 cleanup.sh 到 /opt/psytext/" -Level "SUCCESS" -Prefix "应用环境"
    } else {
        Write-Log -Message "⚠️ cleanup.sh 未找到，跳过部署。" -Level "WARN" -Prefix "应用环境"
    }

    # 3. data 目录
    $dirs = @("logs", "logs_fallback", "audio", "sqlite", "video", "model", "image", "lyric")
    $mkdirCmd = ($dirs | ForEach-Object { "mkdir -p /opt/psytext/data/$_" }) -join " && "
    & wsl -d $DistroName -u root sh -c "$mkdirCmd && chown -R appuser:appuser /opt/psytext/data && chmod -R u+w /opt/psytext/data"
    Write-Log -Message "✅ 已创建 8 个数据子目录并设置 appuser 权限。" -Level "SUCCESS" -Prefix "应用环境"

    # 4. 采集物理机信息并写入 data 目录（用于设备授权判定）
    Write-Log -Message "正在采集物理机信息..." -Level "INFO" -Prefix "设备授权"

    # 4.1 获取物理机名称
    $machineName = ""
    try {
        $machineName = $env:COMPUTERNAME
        if ([string]::IsNullOrEmpty($machineName)) {
            $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
            if ($cs) { $machineName = $cs.Name }
        }
    } catch {
        $machineName = $env:HOSTNAME
    }
    if ([string]::IsNullOrEmpty($machineName)) { $machineName = "未知主机" }
    Write-Log -Message "物理机名称: $machineName" -Level "INFO" -Prefix "设备授权"

    # 4.2 获取 system_machine_id（使用 Windows MachineGuid，跨 WSL 重装稳定）
    # 这是物理机的唯一稳定标识，WSL 重装后此值不变
    $machineId = ""
    try {
        $regPath = "HKLM:\SOFTWARE\Microsoft\Cryptography"
        if (Test-Path $regPath) {
            $props = Get-ItemProperty $regPath -ErrorAction SilentlyContinue
            if ($props -and $props.MachineGuid) {
                $machineId = $props.MachineGuid.Replace('-', '').ToLower()
            }
        }
    } catch {}

    # 兜底：生成基于硬件特征的稳定 ID
    if ([string]::IsNullOrEmpty($machineId)) {
        try {
            $cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
            $board = Get-CimInstance Win32_BaseBoard -ErrorAction SilentlyContinue
            $cpuId = if ($cpu -and $cpu.ProcessorId) { $cpu.ProcessorId } else { "unknown" }
            $boardId = if ($board -and $board.SerialNumber -and $board.SerialNumber -ne "To be filled by O.E.M.") { $board.SerialNumber } else { "unknown" }
            $hashInput = "$cpuId-$boardId"
            $md5 = [System.Security.Cryptography.MD5]::Create()
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($hashInput)
            $hashBytes = $md5.ComputeHash($bytes)
            $machineId = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
        } catch {
            # 最终兜底：生成 UUID
            $machineId = [guid]::NewGuid().ToString("N")
        }
    }
    Write-Log -Message "system_machine_id (Windows MachineGuid): $machineId" -Level "INFO" -Prefix "设备授权"

    # 4.2.1 获取 WSL boot_id 用于硬件绑定（防复制校验）
    # boot_id 在 WSL2 中对于同一发行版是稳定的，但跨发行版/跨机器会不同
    $wslBootId = ""
    try {
        $bootIdOutput = & wsl -d $DistroName -u root sh -c "cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo 'unknown'" 2>&1
        if ($LASTEXITCODE -eq 0 -and $bootIdOutput) {
            $wslBootId = $bootIdOutput.ToString().Trim()
        }
    } catch {
        Write-Log -Message "⚠️ 无法获取 WSL boot_id，将使用弱绑定模式" -Level "WARN" -Prefix "设备授权"
    }

    # 组合 machine-id：{MachineGuid}|{bootId}
    # 如果 boot_id 不可用，保持原格式（弱绑定）
    if (-not [string]::IsNullOrEmpty($wslBootId) -and $wslBootId -ne "unknown") {
        $machineId = "$machineId|$wslBootId"
        Write-Log -Message "机器 ID（含硬件绑定）: $machineId" -Level "INFO" -Prefix "设备授权"
    } else {
        Write-Log -Message "机器 ID（无硬件绑定）: $machineId" -Level "INFO" -Prefix "设备授权"
    }

    # 4.3 写入到 WSL 的 data 目录
    $machineIdContent = $machineId
    $machineNameContent = $machineName

    # 构造 base64 编码的写入命令
    $idB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($machineIdContent))
    $nameB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($machineNameContent))

    & wsl -d $DistroName -u root sh -c "echo '$idB64' | base64 -d > /opt/psytext/data/.machine-id && chmod 644 /opt/psytext/data/.machine-id"
    if ($LASTEXITCODE -eq 0) {
        Write-Log -Message "✅ 已写入 machine-id 到 data 目录" -Level "SUCCESS" -Prefix "设备授权"
    } else {
        Write-Log -Message "⚠️ 写入 machine-id 失败" -Level "WARN" -Prefix "设备授权"
    }

    & wsl -d $DistroName -u root sh -c "echo '$nameB64' | base64 -d > /opt/psytext/data/.machine-name && chmod 644 /opt/psytext/data/.machine-name"
    if ($LASTEXITCODE -eq 0) {
        Write-Log -Message "✅ 已写入 machine-name 到 data 目录" -Level "SUCCESS" -Prefix "设备授权"
    } else {
        Write-Log -Message "⚠️ 写入 machine-name 失败" -Level "WARN" -Prefix "设备授权"
    }

    & wsl -d $DistroName -u root chown -R appuser:appuser /opt/psytext/data
    Write-Log -Message "✅ 物理机信息采集完成" -Level "SUCCESS" -Prefix "设备授权"
}


# === 主程序入口 ===
try {
    Start-LogSession  # 👈 开始日志会话

    Write-Banner -Mode Install

    # 初始化环境（权限 + WSL）
    Initialize-Environment

    # 选择存储位置
    $wslRoot = Select-WslStorageRoot -ScriptRoot $ScriptRoot -MinFreeBytes 20GB

    # 配置专用 WSL 发行版
    Provision-PsyTextWslDistro -WslRoot $wslRoot

    # === 关键：根据标志决定是否执行后续步骤 ===
    if (-not $script:UsedPrebuiltImage) {
        # 在 WSL 中安装原生 Docker Engine
        Install-DockerInWsl -DistroName $PSYTEXT_DISTRO
        
        # 配置应用环境
        Setup-PsyTextAppEnv -DistroName $PSYTEXT_DISTRO -HostScriptRoot $ScriptRoot
        
        # 加载镜像
        Load-PsyTextContainerImages -DistroName $PSYTEXT_DISTRO -HostScriptRoot $ScriptRoot

        # 配置自动清理定时任务
        Deploy-CleanupScript -DistroName $PSYTEXT_DISTRO -HostScriptRoot $ScriptRoot
    } else {
        Write-Log "检测到一体镜像，跳过 Docker 安装及应用环境部署。" -Level INFO -Prefix "部署策略"
    }

    Set-WslTimezone -DistroName $PSYTEXT_DISTRO
    Sync-WslTime -DistroName $PSYTEXT_DISTRO

    Write-Log -Message "安装流程已完成。服务需手动启动。" -Level "INFO" -Prefix "部署完成"

    $startScriptPath = Join-Path $ScriptRoot "启动服务.bat"
    if (Test-Path $startScriptPath) {
        Write-Host "`n🚀 PsyText Analyst 已成功部署！" -ForegroundColor Green
        Write-Host "👉 请双击运行以下脚本来启动服务：" -ForegroundColor Cyan
        Write-Host "   $startScriptPath" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "💡 重要提示：启动后出现的黑色窗口 + 实时展示日志 = 保活服务进程，请勿关闭！" -ForegroundColor Yellow
        Write-Host "   关闭窗口或停止日志将导致 wsl 环境自动终止进程并停止服务，网页无法访问。" -ForegroundColor Yellow
    } else {
        Write-Host "`n⚠️ 警告：未找到 '启动服务.bat'，请从项目根目录获取。" -ForegroundColor Red
        Write-Log -Message "缺失启动脚本：启动服务.bat" -Level "WARN" -Prefix "部署完成"
    }

    End-LogSession -Status "Success"
    Rotate-LogFileBySize -Path $script:LogPath -MaxSizeBytes 50MB

    Write-Host "按 Enter 键退出..." -ForegroundColor Cyan
    Read-Host | Out-Null
    Exit 0
} catch {
    Write-Log -Message "脚本执行发生未预期错误: $($_.Exception.Message)" -Level "ERROR"
    End-LogSession -Status "Failed: $($_.Exception.Message)"  # 👈 异常结束
    Rotate-LogFileBySize -Path $script:LogPath -MaxSizeBytes 50MB
    Write-Host "`n❌ 安装失败！详细信息请查看日志文件：$script:LogPath" -ForegroundColor Red
    Write-Host "`n按 Enter 键退出..." -ForegroundColor Cyan
	Read-Host | Out-Null
    Exit 1
}