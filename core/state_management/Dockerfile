# 使用 Python 3.10 作為基礎映像
FROM python:3.10-slim

# 設置工作目錄
WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴文件（從根目錄）
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式代碼
COPY core/state_management/ .

# 複製共用模組
COPY env_loader.py .

# 創建日誌目錄
RUN mkdir -p logs

# 暴露端口
EXPOSE 55103

# 設置環境變數
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=state_management_main.py

# 啟動命令（使用 gunicorn）
CMD ["gunicorn", "--bind", "0.0.0.0:55103", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "state_management_main:app"]
