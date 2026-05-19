@echo off
chcp 65001 >nul
echo ============================================================
echo   海军标准 RAG 智能体 — Windows 一键初始化脚本
echo ============================================================
echo.

REM 检查 Python
echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   Python 环境正常
echo.

REM 检查 Docker
echo [2/4] 检查 Docker 环境...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 未检测到 Docker，请安装 Docker Desktop
    echo 下载地址: https://www.docker.com/products/docker-desktop/
    echo 跳过 pgvector 容器启动，请手动启动
) else (
    echo   Docker 环境正常
)
echo.

REM 安装 Python 依赖
echo [3/4] 安装 Python 依赖包...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [警告] 部分依赖安装失败，请尝试使用默认源: pip install -r requirements.txt
)
echo.

REM 创建必要目录
echo [4/4] 创建必要目录...
if not exist "data\uploads" mkdir data\uploads
if not exist "logs" mkdir logs
echo   目录创建完成
echo.

echo ============================================================
echo   初始化完成！
echo.
echo   后续步骤：
echo   1. 启动 pgvector 容器: docker-compose up -d
echo   2. 初始化数据库:   python -c "from database.schema import init_db; init_db()"
echo   3. 启动应用:       streamlit run ui/app.py
echo ============================================================
pause
