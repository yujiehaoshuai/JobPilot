@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 只使用项目现有环境，不下载 Python，也不重新安装依赖。
if not exist ".venv\Scripts\python.exe" (
    echo 未找到项目解释器 .venv\Scripts\python.exe，请检查环境目录是否完整。
    pause
    exit /b 1
)
set "PYTHONIOENCODING=utf-8"
".venv\Scripts\python.exe" -m app.server --open-browser %*
if errorlevel 1 (
    echo 启动失败，请查看上方提示。若端口被占用，可运行 start.cmd --port 8001。
    pause
    exit /b 1
)
endlocal
