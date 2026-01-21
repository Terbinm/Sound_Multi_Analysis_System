# 分析後端 Dockerfile (GPU 版本)
# 使用 NVIDIA CUDA 基礎映像以支援 GPU 加速
FROM nvidia/cuda:12.8.0-runtime-ubuntu22.04

# 設定工作目錄
WORKDIR /app

# 設定非互動模式，避免 apt 安裝時卡住
ENV DEBIAN_FRONTEND=noninteractive

# 安裝 Python 3.11 和系統依賴
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-distutils \
    python3-pip \
    gcc \
    g++ \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# ============ 第一層：ML 大型依賴（很少變動，充分利用快取）============
# PyTorch GPU 版本 + torchaudio (CUDA 12.8)
# 使用 python -m pip 確保安裝到正確的 Python 版本
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
    torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# ============ 第二層：核心依賴（偶爾變動）============
RUN python -m pip install --no-cache-dir \
    pymongo==4.6.1 \
    pika==1.3.2 \
    numpy>=1.24.3 \
    pandas>=2.0.0 \
    librosa==0.10.1 \
    soundfile==0.12.1 \
    python-dotenv==1.0.1 \
    requests==2.31.0 \
    scikit-learn>=1.3.0 \
    pytorch_lightning

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