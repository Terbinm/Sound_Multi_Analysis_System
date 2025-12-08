# 分析後端 Dockerfile
FROM python:3.9-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴文件（從根目錄）
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir \
    pymongo \
    numpy \
    librosa \
    soundfile \
    gridfs \
    torch --index-url https://download.pytorch.org/whl/cpu || \
    pip install --no-cache-dir pymongo numpy librosa soundfile torch

# 安裝 SpeechBrain (用於 LEAF)
RUN pip install --no-cache-dir speechbrain

# 複製應用程式檔案
COPY sub_system/analysis_service/ .

# 建立日誌目錄
RUN mkdir -p /app/logs

# 設定環境變數
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 啟動應用
CMD ["python", "analysis_main.py"]