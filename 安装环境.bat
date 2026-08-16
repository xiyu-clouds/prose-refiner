@echo off
set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%install.ps1"
if not exist "%PS_SCRIPT%" (
    echo.
    echo [错误] 未找到 install.ps1 脚本！
    echo        请确保 .bat 与 .ps1 文件在同一目录。
    echo.
    pause
    exit /b 1
)

PowerShell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
if %errorlevel% neq 0 (
    echo.
    echo [提示] 安装过程中出错，请查看上方信息。
    pause
)