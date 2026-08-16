# run.ps1
$ScriptRoot = Split-Path $MyInvocation.MyCommand.Path -Parent
. (Join-Path $ScriptRoot "common.ps1")

$ScriptName = [System.IO.Path]::GetFileNameWithoutExtension($MyInvocation.MyCommand.Name)
$LogDir = Join-Path $ScriptRoot "logs"
$null = New-Item -ItemType Directory -Path $LogDir -Force
$script:LogPath = Join-Path $LogDir "$ScriptName.log"

$distro = "PsyText-WSL"

function Ensure-PsyTextServicesRunning {
    param([string]$DistroName)

    Write-Log -Message "检查 PsyText 服务状态..." -Level "INFO"
    # 检查容器是否 Up
    $status = & wsl -d $DistroName bash -c "docker ps --filter 'name=psytext_analyst' --format '{{.Status}}'" 2>$null
    
    if ($status -match "^Up") {
        Restart-PsyTextServices -DistroName $DistroName
    } else {
        Start-PsyTextServices -DistroName $DistroName
    }
}

function Enter-PsyTextControlLoop {
    param([string]$DistroName = "PsyText-WSL")

    while ($true) {
        Write-Host "`n🚀 PsyText Analyst 控制台" -ForegroundColor Yellow
        Write-Host "请选择操作：" -ForegroundColor White
        Write-Host "  [1] 查看实时日志（按 Ctrl+C 返回）" -ForegroundColor Yellow
        Write-Host "  [2] 打开数据目录" -ForegroundColor Yellow
        Write-Host "  [3] 备份应用数据" -ForegroundColor Yellow
        Write-Host "  [4] 停止服务并退出" -ForegroundColor Red
        Write-Host ""

        $choice = Read-Host "请输入选项 [1-4]"
        switch ($choice.Trim()) {
            "1" { 
                Show-PsyTextRealtimeLogs -DistroName $DistroName
             }
            "2" { 
                Open-PsyTextDataDirectory -DistroName $DistroName
             }
            "3" {
                $backupDir = Join-Path $ScriptRoot "backups"
                $backupOk = $false
                Backup-PsyTextDataFromWsl -BackupDir $backupDir -Success ([ref]$backupOk)
            } 
            "4" {
                Write-Host "`n🛑 正在停止服务..." -ForegroundColor Yellow
                Stop-PsyTextServices -DistroName $DistroName
                Write-Log -Message "用户主动停止服务并退出。" -Level "INFO"
                Write-Host "👋 服务已停止，窗口即将关闭。" -ForegroundColor Green
                Start-Sleep -Seconds 2
                Exit 0
            }
            default {
                Write-Host "⚠️ 无效选项，请输入 1、2 、3或4。" -ForegroundColor Red
            }
        }
    }
}

try {
    Start-LogSession  # 👈 开始日志会话
    Write-Banner -Mode Run
    Write-Log -Message "开始执行服务启动流程..." -Level "INFO"

    Assert-WslDistroExists -DistroName $distro

    Sync-WslTime -DistroName $distro

    # 检查服务状态
    Ensure-PsyTextServicesRunning -DistroName $distro

    # ===== 主控制循环 =====
    Enter-PsyTextControlLoop -DistroName $distro
} catch {
    $errorMessage = $_.Exception.Message
    Write-Log -Message "运行时发生错误: $errorMessage" -Level "ERROR"
    End-LogSession -Status "Failed: $errorMessage"
    Rotate-LogFileBySize -Path $script:LogPath -MaxSizeBytes 50MB

    Write-Host "`n❌ 启动失败！" -ForegroundColor Red
    Write-Host "详细错误信息已记录至：$script:LogPath" -ForegroundColor Yellow
    Write-Host "按 Enter 键退出..." -ForegroundColor Cyan
    Read-Host | Out-Null
    Exit 1
}