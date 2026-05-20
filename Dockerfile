FROM python:3.11-slim

WORKDIR /app

# 系统依赖（Tesseract OCR + 中文语言包 + poppler）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 项目代码
COPY . .

# 嵌入模型缓存目录
ENV HF_ENDPOINT=https://hf-mirror.com
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# 暴露端口
EXPOSE 8501

# 启动命令
CMD ["python", "backend_api.py"]
