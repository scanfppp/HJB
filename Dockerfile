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

# 预下载嵌入模型到本地（避免运行时联网）
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-base-zh-v1.5', local_dir='/app/models/bge-base-zh-v1.5'); \
print('Model downloaded to /app/models/bge-base-zh-v1.5')"

# 项目代码
COPY . .

# 暴露端口
EXPOSE 8501

# 启动命令
CMD ["python", "backend_api.py"]
