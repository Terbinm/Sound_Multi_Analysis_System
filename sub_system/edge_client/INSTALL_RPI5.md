# Edge Client 手動安裝指南 (Raspberry Pi 5 / Armbian)

本文件說明如何在 Raspberry Pi 5 (Armbian) 上手動安裝 Edge Client，並設定開機自動啟動。

## 系統需求

- Raspberry Pi 5 (或相容的 ARM64 Linux 系統)
- Armbian 或 Raspberry Pi OS
- 網路連線
- 音訊輸入裝置 (麥克風)

---

## 前置準備 (Armbian 系統設定)

### 步驟 0-1：更新系統套件

```bash
# 更新套件清單
sudo apt update

# 升級已安裝的套件
sudo apt upgrade -y
```

### 步驟 0-2：安裝必要套件

```bash
# 安裝 Git、Python 及相關工具
sudo apt install -y \
    git \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev

# 安裝音訊相關套件 (sounddevice 依賴)
sudo apt install -y \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    libasound2-dev

# 安裝其他工具
sudo apt install -y \
    curl \
    wget
```

### 步驟 0-3：驗證安裝

```bash
# 檢查 Git 版本
git --version

# 檢查 Python 版本 (需要 3.9+)
python3 --version

# 檢查 pip
python3 -m pip --version
```

### 步驟 0-4：設定音訊權限 (選用)

如果遇到音訊裝置權限問題，將當前使用者加入 `audio` 群組：

```bash
sudo usermod -aG audio $(whoami)

# 重新登入以套用變更
logout
```

---

## 安裝 Edge Client

### 步驟 1：取得程式碼

**方法一：Git Clone (推薦)**

```bash
cd ~
git clone https://github.com/your-org/Sound_Multi_Analysis_System.git
cd Sound_Multi_Analysis_System/sub_system/edge_client
```

**方法二：複製現有程式碼**

```bash
# 將程式碼複製到 RPi5 後進入目錄
cd /path/to/Sound_Multi_Analysis_System/sub_system/edge_client
```

### 步驟 2：建立 Python 虛擬環境

```bash
# 建立虛擬環境
python3 -m venv venv

# 升級 pip
./venv/bin/pip install --upgrade pip

# 安裝依賴套件
./venv/bin/pip install --upgrade -r requirements.txt

# 驗證安裝結果
./venv/bin/pip list
```

### 步驟 3：建立設定檔

建立 `device_config.json`：

```bash
cat > device_config.json << 'EOF'
{
  "server_url": "http://YOUR_SERVER_IP:PORT",
  "audio_config": {
    "default_device_index": 0,
    "channels": 1,
    "sample_rate": 16000,
    "bit_depth": 32
  },
  "heartbeat_interval": 30,
  "reconnect_delay": 5,
  "max_reconnect_delay": 60,
  "temp_wav_dir": "temp_wav"
}
EOF
```

**重要**：請將 `server_url` 中的 `YOUR_SERVER_IP:PORT` 替換為實際的 State Management 伺服器地址。

#### 自動獲取的欄位

以下欄位**無需手動設定**，程式會自動處理：

| 欄位 | 自動獲取方式 |
|------|-------------|
| `device_id` | 首次連線時由**伺服器自動分配**，並保存至設定檔 |
| `device_name` | 若未設定，自動生成 `Device_{8位隨機碼}` 格式的名稱 |

#### 設定檔參數說明

| 參數 | 說明 | 必填 |
|------|------|------|
| `server_url` | State Management 伺服器地址 | **是** |
| `device_id` | 裝置唯一識別碼 (由伺服器分配) | 否 (自動) |
| `device_name` | 裝置名稱 | 否 (自動) |
| `audio_config.default_device_index` | 音訊裝置索引，0 為預設裝置 | 否 |
| `audio_config.channels` | 音訊通道數 | 否 |
| `audio_config.sample_rate` | 取樣率 (Hz) | 否 |
| `audio_config.bit_depth` | 位元深度 | 否 |
| `heartbeat_interval` | 心跳間隔 (秒) | 否 |
| `reconnect_delay` | 重連延遲 (秒) | 否 |
| `max_reconnect_delay` | 最大重連延遲 (秒) | 否 |
| `temp_wav_dir` | 暫存音訊檔案目錄 | 否 |

### 步驟 4：建立暫存目錄

```bash
mkdir -p temp_wav
chmod 755 temp_wav
```

### 步驟 5：手動執行測試

在安裝為系統服務之前，建議先手動執行確認程式能正常運作：

```bash
# 啟動 Edge Client (前景執行)
./venv/bin/python edge_client.py
```

若看到類似以下輸出，表示正常運作：

```
邊緣客戶端初始化完成: device_id=None, name=Device_xxxxxxxx
嘗試連線至伺服器: http://YOUR_SERVER_IP:PORT
已連線至伺服器
已發送設備註冊請求: device_id=None
已獲得伺服器分配的 device_id: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

按 `Ctrl+C` 停止程式後，可繼續安裝為系統服務。

---

### 步驟 6：安裝 systemd 服務

此步驟設定 Edge Client 為系統服務，實現開機自動啟動。

```bash
# 取得完整路徑
WORK_DIR="$(pwd)"
VENV_PYTHON="${WORK_DIR}/venv/bin/python"

# 建立 service 檔案
cat > /tmp/edge-client.service << EOF
[Unit]
Description=Sound Analysis Edge Client
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${WORK_DIR}
ExecStart=${VENV_PYTHON} edge_client.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 安裝到 systemd
sudo cp /tmp/edge-client.service /etc/systemd/system/edge-client.service

# 重新載入 systemd 設定
sudo systemctl daemon-reload
```

### 步驟 7：啟用並啟動服務

```bash
# 啟用開機自動啟動
sudo systemctl enable edge-client

# 立即啟動服務
sudo systemctl start edge-client

# 檢查服務狀態
sudo systemctl status edge-client
```

## 服務管理指令

| 操作 | 指令 |
|------|------|
| 查看服務狀態 | `sudo systemctl status edge-client` |
| 啟動服務 | `sudo systemctl start edge-client` |
| 停止服務 | `sudo systemctl stop edge-client` |
| 重啟服務 | `sudo systemctl restart edge-client` |
| 啟用開機自啟 | `sudo systemctl enable edge-client` |
| 停用開機自啟 | `sudo systemctl disable edge-client` |
| 即時查看日誌 | `sudo journalctl -u edge-client -f` |
| 查看最近 50 筆日誌 | `sudo journalctl -u edge-client -n 50` |
| 查看今日日誌 | `sudo journalctl -u edge-client --since today` |

## 驗證安裝

### 檢查服務是否設為開機自啟

```bash
systemctl is-enabled edge-client
# 預期輸出: enabled
```

### 檢查服務是否正在運行

```bash
systemctl is-active edge-client
# 預期輸出: active
```

### 測試重啟後自動恢復

```bash
# 重啟系統
sudo reboot

# 重啟後檢查服務狀態
sudo systemctl status edge-client
```

## 故障排除

### 服務無法啟動

1. 檢查日誌：
   ```bash
   sudo journalctl -u edge-client -n 100 --no-pager
   ```

2. 手動執行測試：
   ```bash
   cd /path/to/edge_client
   ./venv/bin/python edge_client.py
   ```

3. 檢查設定檔格式：
   ```bash
   python3 -c "import json; json.load(open('device_config.json'))"
   ```

### 音訊裝置問題

1. 列出可用音訊裝置：
   ```bash
   ./venv/bin/python -c "import sounddevice; print(sounddevice.query_devices())"
   ```

2. 根據輸出調整 `device_config.json` 中的 `default_device_index`。

### 網路連線問題

1. 確認伺服器地址可達：
   ```bash
   curl -f http://YOUR_SERVER_IP:PORT/health
   ```

2. 檢查防火牆設定。

### 更新程式碼後重新部署

```bash
# 停止服務
sudo systemctl stop edge-client

# 更新程式碼
cd /path/to/Sound_Multi_Analysis_System
git pull

# 更新依賴
cd sub_system/edge_client
./venv/bin/pip install --upgrade -r requirements.txt

# 重啟服務
sudo systemctl start edge-client
```

## 解除安裝

```bash
# 停止並停用服務
sudo systemctl stop edge-client
sudo systemctl disable edge-client

# 移除 service 檔案
sudo rm /etc/systemd/system/edge-client.service
sudo systemctl daemon-reload

# (可選) 移除程式碼
rm -rf /path/to/edge_client
```
