@echo off
chcp 65001 >nul
title AI图片智能重命名与分类系统 启动器
echo =======================================================
echo   AI图片智能重命名与分类系统 (v2.2.1)
echo =======================================================
echo.

:: 检查 Python 虚拟环境（在当前目录）
if not exist ".\.venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 .\.venv，请确保已初始化虚拟环境并安装依赖。
    echo 请在当前目录下运行: python -m venv .venv
    pause
    exit /b
)

:: 检查前端 node_modules
if not exist "frontend\node_modules" (
    echo [提示] 未检测到前端依赖，正在尝试自动安装 npm install ，请稍候...
    cd /d frontend
    call npm install
    if %errorlevel% neq 0 (
        echo [错误] 前端依赖安装失败，请手动在 frontend 目录下运行 npm install
        cd /d ..
        pause
        exit /b
    )
    cd /d ..
    echo [成功] 前端依赖安装完成！
    echo.
)

echo [1/2] 正在启动 FastAPI 后端服务 (端口 8000)...
start "AI图片重命名后端" cmd /k "chcp 65001 >nul && .\.venv\Scripts\python.exe main.py"

echo [2/2] 正在启动 Vite 前端服务 (端口 5173)...
start "AI图片重命名前端" cmd /k "chcp 65001 >nul && cd /d frontend && npm run dev"

echo.
echo ===================================================
echo 启动指令已发送！
echo - 后端 API 文档: http://localhost:8000/docs (若端口被占用会自动顺延至 8001/8002 等)
echo - 前端网页界面: http://localhost:5173
echo ===================================================
echo 正在为您在浏览器中打开网页界面...
timeout /t 3 >nul
start http://localhost:5173
