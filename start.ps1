# UTF-8 Encoding
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  AI图片智能重命名与分类系统 (v2.2.1)" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 检查虚拟环境（在当前目录）
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "[错误] 未找到虚拟环境 .\.venv，请确保已初始化虚拟环境并安装依赖。" -ForegroundColor Red
    Read-Host "按回车键退出..."
    exit
}

# 检查前端依赖
if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "[提示] 未检测到前端依赖，正在尝试自动安装 (npm install)，请稍候..." -ForegroundColor Yellow
    Set-Location frontend
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[错误] 前端依赖安装失败，请手动在 frontend 目录下运行 npm install" -ForegroundColor Red
        Set-Location ..
        Read-Host "按回车键退出..."
        exit
    }
    Set-Location ..
    Write-Host "[成功] 前端依赖安装完成！" -ForegroundColor Green
    Write-Host ""
}

Write-Host "[1/2] 正在启动 FastAPI 后端服务 (端口 8000)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k chcp 65001 >nul && .\.venv\Scripts\python.exe main.py" -WindowStyle Normal

Write-Host "[2/2] 正在启动 Vite 前端服务 (端口 5173)..." -ForegroundColor Green
Start-Process cmd.exe -ArgumentList "/k chcp 65001 >nul && cd /d frontend && npm run dev" -WindowStyle Normal

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "启动指令已发送！" -ForegroundColor Cyan
Write-Host "- 后端 API 文档: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host "- 前端网页界面: http://localhost:5173" -ForegroundColor Gray
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "正在为您在浏览器中打开网页界面..."
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"
