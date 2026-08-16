# uninstall.ps1
$ScriptRoot = Split-Path $MyInvocation.MyCommand.Path -Parent
. (Join-Path $ScriptRoot "common.ps1")

$ScriptName = [System.IO.Path]::GetFileNameWithoutExtension($MyInvocation.MyCommand.Name)
$LogDir = Join-Path $ScriptRoot "logs"
$null = New-Item -ItemType Directory -Path $LogDir -Force
$script:LogPath = Join-Path $LogDir "$ScriptName.log"

$PSYTEXT_DISTRO = "PsyText-WSL"

# 获取 WSL 宿主机上的 PsyText-WSL 发行版根目录
function Get-PsyTextWslBaseOnHost {
    # 获取宿主机上的 WSL 发行版根目录（用于最终删除）
    $wslRoot = Load-WslStorageLocation -ScriptRoot $ScriptRoot
    if (-not $wslRoot) {
        $regKey = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss\*" -ErrorAction SilentlyContinue |
                  Where-Object { $_.DistributionName -eq "PsyText-WSL" }
        if ($regKey -and $regKey.BasePath) {
            $wslRoot = Split-Path $regKey.BasePath -Parent
        } else {
            $wslRoot = "C:\wsl"
        }
    }
    return Join-Path $wslRoot "PsyText-WSL"
}

# 删除 WSL 环境
function Remove-PsyTextWslEnvironment {
    param([string]$WslBaseOnHost)

    Write-Log -Message "停止并注销 WSL 发行版..." -Level "INFO"
    & wsl --shutdown "PsyText-WSL" *>$null
    Start-Sleep -Seconds 2
    Unregister-WslDistribution -Name "PsyText-WSL"

    if (Test-Path $WslBaseOnHost) {
        Write-Log -Message "删除 WSL 发行版目录: $WslBaseOnHost" -Level "INFO"
        Remove-Item -Recurse -Force $WslBaseOnHost -ErrorAction Stop
    }

    $locationFile = Get-WslStorageLocationFile -ScriptRoot $ScriptRoot
    if (Test-Path $locationFile) {
        Remove-Item $locationFile -Force
        Write-Log -Message "清理 .wsl_location 记录。" -Level "INFO"
    }
}

# 备份数据
function Invoke-BackupIfUserWants {
    param([string]$ScriptRoot)

    if (-not (Confirm-Choice "是否备份应用数据（/opt/psytext/data）和 Redis 持久化数据？")) {
        return $true  # 用户跳过，视为“可继续”
    }

    $backupDir = Join-Path $ScriptRoot "backups"
    $backupOk = $false

    try {
        Backup-PsyTextDataFromWsl -BackupDir $backupDir -Success ([ref]$backupOk)
        return $backupOk  # 成功 true，空备份也算成功（$backupOk=true）
    } catch {
        Write-Log -Message "备份交互中捕获异常: $_" -Level "ERROR"
        return $false  # 明确表示“备份未成功”
    }
}

# 确认卸载
function Confirm-UninstallWithBackupOption {
    param(
        [string]$DistroName = "PsyText-WSL",
        [string]$ScriptRoot
    )

    # 初始备份（失败可跳过）
    $initialBackupOk = Invoke-BackupIfUserWants -ScriptRoot $ScriptRoot
    if ($initialBackupOk -eq $false) {
        if (-not (Confirm-Choice "初始备份未成功完成，是否仍继续卸载？")) {
            return $false
        }
    }

    while ($true) {
        Write-Host ""
        Write-Host "╔════════════════════════════════════════════════╗" -ForegroundColor Red
        Write-Host "║                ⚠️  警告：永久删除操作！         ║" -ForegroundColor Red
        Write-Host "╠════════════════════════════════════════════════╣" -ForegroundColor Red
        Write-Host "║  此操作将不可逆地删除以下内容：               ║" -ForegroundColor Yellow
        Write-Host "║    • WSL 发行版 'PsyText-WSL'                 ║" -ForegroundColor Yellow
        Write-Host "║    • 所有应用数据、配置、日志                 ║" -ForegroundColor Yellow
        Write-Host "║    • Redis 数据库中的全部内容（无法恢复！）   ║" -ForegroundColor Yellow
        Write-Host "║                                                ║"
        Write-Host "║  🔒 如果您未备份，所有数据将永久丢失！     ║" -ForegroundColor Yellow
        Write-Host "╚════════════════════════════════════════════════╝" -ForegroundColor Red
        Write-Host ""
        Write-Host "💡 操作指南：" -ForegroundColor Cyan
        Write-Host "   • 输入 'YES'     → 立即卸载" -ForegroundColor Gray
        Write-Host "   • 输入 'BACKUP'  → 执行数据备份" -ForegroundColor Gray
        Write-Host "   • 输入其他内容   → 取消卸载" -ForegroundColor Gray
        Write-Host ""

        $confirm = Read-Host "请输入操作指令"
        switch ($confirm.Trim().ToUpper()) {
            "YES" { return $true }
            "BACKUP" {
                $manualBackupOk = Invoke-BackupIfUserWants -ScriptRoot $ScriptRoot
                if ($manualBackupOk -eq $false) {
                    if (-not (Confirm-Choice "备份未成功完成，是否仍继续卸载？")) {
                        return $false
                    }
                }
                # 无论成功失败，都回到确认界面
            }
            default { return $false }
        }
    }
}

$uninstallStatus = "Failed"
$logEndStatus = "Unknown error before initialization"
# 卸载主流程
try {
    Write-Banner -Mode Uninstall
    Start-LogSession
    Write-Log -Message "开始卸载流程..." -Level "INFO"

    Assert-AdminPrivilege
    Write-Log -Message "✅ 管理员权限验证通过。" -Level "SUCCESS"

    $wslBase = Get-PsyTextWslBaseOnHost
    Write-Log -Message "WSL 发行版宿主机路径: $wslBase" -Level "INFO"

    # === 备份 + 确认交互 ===
    if (-not (Confirm-UninstallWithBackupOption -DistroName $PSYTEXT_DISTRO -ScriptRoot $ScriptRoot)) {
        Write-Log -Message "用户取消卸载。" -Level "INFO"
        throw [System.OperationCanceledException]::new("User cancelled.")
    }

    # === 执行卸载 ===
    Remove-PsyTextWslEnvironment -WslBaseOnHost $wslBase
    $uninstallStatus = "Success"
    $logEndStatus = "Success"
} catch [System.OperationCanceledException] {
    $uninstallStatus = "Cancelled"
    $logEndStatus = "Cancelled by user"
} catch {
    Write-Log -Message "卸载失败: $($_.Exception.Message)" -Level "ERROR"
    $uninstallStatus = "Failed"
    $logEndStatus = "Failed: $($_.Exception.Message)"
} finally {
    # === 统一日志收尾 ===
    if ($logEndStatus) {
        End-LogSession -Status $logEndStatus
        Rotate-LogFileBySize -Path $script:LogPath -MaxSizeBytes 50MB
    }

    # === 统一暂停提示 ===
    Pause-AfterUninstall -Status $uninstallStatus
}