@echo off
chcp 65001 >nul
echo ============================================================
echo   海军标准 RAG 智能体 — Windows 一键初始化脚本
echo ============================================================
echo.

REM 检查 Python
echo [1/5] 检查 Python 环境...
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
echo [2/5] 检查 Docker 环境...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 未检测到 Docker，请安装 Docker Desktop
    echo 下载地址: https://www.docker.com/products/docker-desktop/
    echo 跳过 pgvector 容器启动，请手动启动
) else (
    echo   Docker 环境正常
)
echo.

REM 安装 Tesseract OCR（用于 CID 字体 / 扫描版 PDF 识别）
echo [3/5] 检查 Tesseract OCR...
where tesseract >nul 2>&1
if %errorlevel% neq 0 (
    echo   未检测到 Tesseract，正在安装...
    winget install UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 (
        echo   [警告] Tesseract 安装失败，请手动安装:
        echo   winget install UB-Mannheim.TesseractOCR
        echo   或下载: https://github.com/UB-Mannheim/tesseract/wiki
    ) else (
        echo   Tesseract 安装成功
        REM 下载中文简体语言包
        if not exist "data\tessdata" mkdir data\tessdata
        echo   正在下载中文语言包...
        curl -L -o "data\tessdata\chi_sim.traineddata" "https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata" 2>nul
        if %errorlevel% neq 0 (
            echo   [警告] 中文语言包下载失败，请手动下载到 data\tessdata\chi_sim.traineddata
        ) else (
            echo   中文语言包下载完成
        )
    )
) else (
    echo   Tesseract 已安装
    REM 确保中文语言包存在
    if not exist "data\tessdata" mkdir data\tessdata
    if not exist "data\tessdata\chi_sim.traineddata" (
        echo   正在下载中文语言包...
        curl -L -o "data\tessdata\chi_sim.traineddata" "https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata" 2>nul
    )
)
echo.

REM 安装 Python 依赖
echo [4/5] 安装 Python 依赖包...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [警告] 部分依赖安装失败，请尝试使用默认源: pip install -r requirements.txt
)
echo.

REM 创建必要目录
echo [5/5] 创建必要目录...
if not exist "data\uploads" mkdir data\uploads
if not exist "logs" mkdir logs
if not exist "data\tessdata" mkdir data\tessdata
echo   目录创建完成
echo.

echo ============================================================
echo   初始化完成！
echo.
echo   后续步骤：
echo   1. 启动 pgvector 容器: docker-compose up -d
echo   2. 初始化数据库:   set PYTHONPATH=%%CD%%\src;%%PYTHONPATH%% ^& python -c "from database.schema import init_db; init_db()"
echo   3. 启动应用:       python src/main.py
echo ============================================================
pause
