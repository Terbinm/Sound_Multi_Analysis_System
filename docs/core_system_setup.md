# Core System 部署指南

本文件說明如何在新環境中部署並啟動 Sound Multi Analysis System 的核心系統。

## 前置需求

- **Docker Desktop** (Windows/macOS) 或 **Docker Engine** (Linux)
- **Docker Compose** v2.0+
- **Git**

## 目錄結構

```
Sound_Multi_Analysis_System/
├── .env                          # 環境變數設定檔
├── core/
│   ├── docker-compose.yml        # 主要 Docker Compose 設定
│   ├── docker-compose.ci.yml     # CI/CD 覆蓋設定
│   ├── rabbitmq.conf             # RabbitMQ 設定
│   └── state_management/         # 狀態管理系統原始碼
└── docs/
```

## 快速啟動

### 1. 設定環境變數

複製範例環境變數檔案並修改：

```bash
cp .env.example .env
```

確保以下變數已正確設定：

```env
# MongoDB
MONGODB_HOST=127.0.0.1
MONGODB_PORT=55101
MONGODB_USERNAME=web_ui
MONGODB_PASSWORD=your_secure_password
MONGODB_DATABASE=web_db

# RabbitMQ
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=55102
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=your_secure_password
RABBITMQ_MANAGEMENT_PORT=55112

# State Management
STATE_MANAGEMENT_PORT=55103
STATE_MANAGEMENT_SECRET_KEY=your_secret_key

# 管理員初始化
INIT_ADMIN_USERNAME=admin
INIT_ADMIN_EMAIL=admin@example.com
INIT_ADMIN_PASSWORD=your_admin_password
```

### 2. 啟動服務

```bash
cd core
docker compose up -d
```

### 3. 確認服務狀態

```bash
docker compose ps
```

預期輸出：

| 服務 | 狀態 | 端口 |
|------|------|------|
| core_mongodb | Up (healthy) | 55101 |
| core_rabbitmq | Up (healthy) | 55102, 55112 |
| core_state_management | Up | 55103 |

### 4. 初始化管理員帳號

首次啟動時需要建立管理員帳號：

```bash
docker exec core_state_management python init_admin.py \
  --username admin \
  --email admin@example.com \
  --password your_admin_password
```

或使用環境變數（如果已在 .env 設定）：

```bash
docker exec core_state_management python init_admin.py
```

### 5. 驗證服務

- **Web UI**: http://localhost:55103
- **RabbitMQ 管理介面**: http://localhost:55112

## 服務說明

### MongoDB (core_mongodb)

- **用途**: 儲存系統資料、使用者、任務等
- **端口**: 55101
- **資料持久化**: Docker Volume `core_mongodb_data`

### RabbitMQ (core_rabbitmq)

- **用途**: 訊息佇列，用於服務間通訊
- **AMQP 端口**: 55102
- **管理介面端口**: 55112
- **資料持久化**: Docker Volume `core_rabbitmq_data`

### State Management (core_state_management)

- **用途**: 系統狀態管理、Web UI、API
- **端口**: 55103
- **功能**:
  - 使用者認證與授權
  - 任務調度與監控
  - 節點狀態管理
  - WebSocket 即時通訊

## 常用命令

### 查看日誌

```bash
# 查看所有服務日誌
docker compose logs -f

# 查看特定服務日誌
docker compose logs -f state_management
```

### 重新啟動服務

```bash
# 重啟所有服務
docker compose restart

# 重啟特定服務
docker compose restart state_management
```

### 停止服務

```bash
# 停止但保留資料
docker compose down

# 停止並刪除資料（慎用）
docker compose down -v
```

### 重建映像

```bash
# 重建 state_management 映像
docker compose build --no-cache state_management

# 重建並重啟
docker compose up -d --build state_management
```

## 常見問題

### Q: 端口被佔用

```
Error: Bind for 0.0.0.0:55103 failed: port is already allocated
```

**解決方案**:

```bash
# 查看佔用端口的程序
netstat -ano | findstr "55103"

# 停止舊容器
docker ps -a
docker stop <container_id>
docker rm <container_id>
```

### Q: MongoDB 連線失敗

```
MongoDB 連接失敗: Connection refused
```

**解決方案**:

1. 確認 MongoDB 容器正在運行: `docker compose ps`
2. 檢查 `.env` 中的 `MONGODB_HOST` 設定
3. Docker 內部服務應使用 `host.docker.internal` 連接宿主機

### Q: 環境變數未載入

```
EnvironmentError: 必要環境變數 'XXX' 未設定
```

**解決方案**:

1. 確認 `.env` 檔案存在於專案根目錄
2. 確認 `docker-compose.yml` 中有 `env_file: ../.env`
3. 重新建立容器: `docker compose up -d --force-recreate`

### Q: 忘記管理員密碼

```bash
# 進入 MongoDB 容器
docker exec -it core_mongodb mongosh -u web_ui -p your_password --port 55101

# 刪除使用者後重新初始化
use web_db
db.users.deleteOne({username: "admin"})
exit

# 重新建立管理員
docker exec core_state_management python init_admin.py
```

## 進階設定

### 自訂端口

修改 `.env` 檔案中的端口設定，然後重啟服務：

```env
MONGODB_PORT=27017
RABBITMQ_PORT=5672
STATE_MANAGEMENT_PORT=8080
```

### 生產環境建議

1. **修改預設密碼**: 更換所有預設密碼
2. **啟用 HTTPS**: 使用反向代理 (nginx) 處理 SSL
3. **備份策略**: 定期備份 MongoDB 資料
4. **監控**: 設定日誌收集與告警

## 相關文件

- [Edge Device 部署指南](./edge_device_guide.md)
- [CD Pipeline 設定](./cd/runner_setup.md)
- [環境變數說明](./env/)
