FROM python:3.11-slim

WORKDIR /app

# 系统依赖（Tesseract OCR + 中文语言包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖 — 先装轻量的 torch CPU 版（比 CUDA 版小 5 倍）
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 项目代码
COPY . .

# 嵌入模型缓存目录
ENV HF_ENDPOINT=https://hf-mirror.com

# 暴露端口
EXPOSE 8501

# 启动命令
CMD ["python", "backend_api.py"]
