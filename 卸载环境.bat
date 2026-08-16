@echo off
:: uninstall.bat —— 通用 WSL & Docker 卸载入口
:: 使用说明：右键此文件 → “以管理员身份运行”

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%uninstall.ps1"

if not exist "%PS_SCRIPT%" (
    echo.
    echo [错误] 未找到 uninstall.ps1 脚本！
    echo        请确保 .bat 与 .ps1 文件在同一目录。
    echo.
    pause
    exit /b 1
)

PowerShell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
if %errorlevel% neq 0 (
    echo.
    echo [提示] 脚本执行出错，请查看上方信息。
    pause
)