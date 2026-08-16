@echo off
set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%run.ps1"
if not exist "%PS_SCRIPT%" (
    echo.
    echo [错误] 未找到 run.ps1 脚本！
    echo        请先运行“安装环境.bat”完成部署。
    echo.
    pause
    exit /b 1
)

PowerShell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
if %errorlevel% neq 0 (
    echo.
    echo [提示] 启动过程中出错，请查看上方信息。
    pause
)