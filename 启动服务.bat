@echo off
chcp 65001 >nul
title 微信自动化平台 - 一键启动
set ROOT=%~dp0
set PROJ=%ROOT%自动化脚本合集
set VENV=%PROJ%\.venv
set VENV_PY=%VENV%\Scripts\python.exe

echo ==================================================
echo  微信自动化平台 一键启动
echo  平台入口 http://localhost:5001（5000 已被 Docker RSS 占用）
echo ==================================================
echo.

rem ---- 1. 准备 Python 环境（首次运行自动建本地 .venv 并装依赖）----
if not exist "%VENV_PY%" goto create_venv

rem .venv 若从别的机器拷贝过来会失效，健康检查不通过则重建
"%VENV_PY%" -c "import flask, flask_cors, requests" >nul 2>nul
if not errorlevel 1 goto deps_ok
echo 检测到 .venv 已失效（可能是从其他机器拷贝的），正在重建...
rmdir /s /q "%VENV%"

:create_venv
echo [1/3] 创建本地虚拟环境 .venv ...
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3 并加入 PATH
    pause
    exit /b 1
)
python -m venv "%VENV%"
if errorlevel 1 (
    echo [错误] 创建虚拟环境失败
    pause
    exit /b 1
)

echo [2/3] 安装依赖（flask / flask-cors / requests）...
"%VENV_PY%" -m pip install -r "%PROJ%\server\requirements.txt"
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
)

:deps_ok
echo [3/3] 启动服务窗口...
echo.

rem ---- 2. 启动主服务（Flask：API + 前端产物托管，端口 5001；5000 已被 Docker RSS 占用）----
start "WxAuto-5001" /D "%PROJ%" cmd /k ""%VENV_PY%" server\app.py"

rem ---- 可选：Mock n8n 接收器（调试用，n8n 正式接入后保持注释即可）----
rem start "Mock-9000" /D "%PROJ%" cmd /k ""%VENV_PY%" server\mock_receiver.py"

rem ---- 可选：前端开发模式（改前端代码时用，需 Node 环境）----
rem start "Vite-5173" /D "%ROOT%wxcheck" cmd /k "npm run dev"

echo 等待服务就绪...
ping 127.0.0.1 -n 6 >nul
start http://localhost:5001

echo.
echo 已启动：
echo   平台入口   http://localhost:5001
echo.
rem ---- 3. 爬虫依赖检查（crawl4ai 装在系统 Python，与 pipeline 探测顺序一致）----
python -c "import crawl4ai" >nul 2>nul
if not errorlevel 1 goto crawl_ok
echo [警告] 系统 Python 未检测到 crawl4ai，爬虫 pipeline（/api/run）将不可用：
echo   python -m pip install crawl4ai ^&^& crawl4ai-setup
goto crawl_done
:crawl_ok
echo crawl4ai 依赖检查通过（系统 Python）。
:crawl_done
echo.
echo 关闭 "WxAuto-5001" 窗口即停止服务。
pause
