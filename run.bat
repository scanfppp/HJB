@echo off
chcp 65001 >nul
echo ============================================================
echo   海军标准 RAG 智能体 — 启动脚本
echo ============================================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 启动 pgvector
echo [1/3] 启动 pgvector 容器...
docker-compose up -d
if %errorlevel% neq 0 (
    echo [警告] pgvector 启动失败，请确保 Docker Desktop 正在运行
)

REM 等待数据库就绪
echo [2/3] 等待数据库就绪...
timeout /t 3 /nobreak >nul

REM 初始化数据库
echo 正在初始化数据库表...
python -c "from database.schema import init_db; print('数据库初始化完成' if init_db() else '数据库初始化失败')"

REM 启动 FastAPI 服务
echo.
echo [3/3] 启动 FastAPI 服务...
echo ============================================================
echo   浏览器访问: http://localhost:8501
echo   按 Ctrl+C 停止应用
echo ============================================================
timeout /t 2 /nobreak >nul

python backend_api.py
