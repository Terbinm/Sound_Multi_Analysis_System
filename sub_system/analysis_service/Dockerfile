# 分析後端 Dockerfile
# 優化建置時間：使用分層快取，將很少變動的依賴放在前面
FROM python:3.9-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（很少變動）
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# ============ 第一層：ML 大型依賴（很少變動，充分利用快取）============
# PyTorch CPU 版本（約 700MB，很少更新）
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# ============ 第二層：核心依賴（偶爾變動）============
RUN pip install --no-cache-dir \
    pymongo==4.6.1 \
    pika==1.3.2 \
    numpy>=1.24.3 \
    pandas>=2.0.0 \
    librosa==0.10.1 \
    soundfile==0.12.1 \
    python-dotenv==1.0.1 \
    requests==2.31.0 \
    scikit-learn>=1.3.0

# ============ 第三層：應用程式碼（經常變動）============
# 複製應用程式檔案
COPY sub_system/analysis_service/ .

# 複製推論所需的訓練模組
COPY sub_system/train/py_cyclegan/ /app/sub_system/train/py_cyclegan/
COPY sub_system/train/RF/ /app/sub_system/train/RF/

# 建立日誌目錄
RUN mkdir -p /app/logs

# 建立 sub_system 的 __init__.py
RUN touch /app/sub_system/__init__.py && touch /app/sub_system/train/__init__.py

# 設定環境變數
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 啟動應用
CMD ["python", "analysis_main.py"]