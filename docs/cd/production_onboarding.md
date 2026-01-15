# Production（Server / Edge）首次自動化接入指引

> **最後更新**：2025-01

## 1. 環境分工

| 環境 | 標籤格式 | Runner 標籤 | 部署內容 | 驗證步驟 |
|------|----------|-------------|----------|----------|
| Server Production | `server_production_v*` | `[self-hosted, server_production]` | MongoDB + RabbitMQ + State Management + Analysis Service | Smoke Test + 健康檢查 |
| Edge Production | `edge_production_v*` | `[self-hosted, edge_production]` | 僅 Analysis Service | 無自動驗證 |

### 重要更新（2025-01）

- **Server Production 現在與 Staging 具有相同的驗證流程**：
  1. 語法 Smoke Test（`python -m compileall /app`）
  2. 健康檢查（`curl -f http://localhost:<PORT>/health`）
- **移除硬編碼密碼**：`docker-compose.override.ci.yml` 不再包含預設密碼
- **所有敏感資訊由 GitHub Secrets 提供**

## 2. GitHub Secrets 設定（必要）

> ⚠️ **重要**：CD Pipeline 會自動從 GitHub Secrets 產生 `.env` 檔案，不需要手動建立。

### Server Production 必要的 Secrets

在 GitHub → Settings → Secrets and variables → Actions 新增以下 11 個 secrets：

| Secret Name | 說明 |
|-------------|------|
| `PRODUCTION_MONGODB_HOST` | MongoDB 主機名稱（通常為 `mongodb`） |
| `PRODUCTION_MONGODB_PORT` | MongoDB 連接埠 |
| `PRODUCTION_MONGODB_USERNAME` | MongoDB 使用者名稱 |
| `PRODUCTION_MONGODB_PASSWORD` | MongoDB 密碼 |
| `PRODUCTION_MONGODB_DATABASE` | MongoDB 資料庫名稱 |
| `PRODUCTION_RABBITMQ_HOST` | RabbitMQ 主機名稱 |
| `PRODUCTION_RABBITMQ_PORT` | RabbitMQ 連接埠 |
| `PRODUCTION_RABBITMQ_USERNAME` | RabbitMQ 使用者名稱 |
| `PRODUCTION_RABBITMQ_PASSWORD` | RabbitMQ 密碼 |
| `PRODUCTION_STATE_MANAGEMENT_PORT` | State Management 連接埠 |
| `PRODUCTION_STATE_MANAGEMENT_URL` | State Management 完整 URL |

另外還需要通用的管理員 Secrets：
- `ADMIN_PASSWORD`
- `ADMIN_EMAIL`

詳細設定指南請參考 [`github_secrets_setup.md`](github_secrets_setup.md)。

## 3. 首次接入步驟

### 3.1 前置準備

1. 確認自託管 runner 標籤正確：`[self-hosted, server_production]` 或 `[self-hosted, edge_production]`
2. 確保 Docker/Compose 已安裝且能連外拉取 GHCR 映像
3. **設定 GitHub Secrets**（見上方第 2 節）

### 3.2 觸發部署

**方法 A：透過 Commit Message**
```bash
git commit --allow-empty -m "server_production_v1.0.0.1_initial-deployment"
git push origin main
```

**方法 B：透過 GitHub Actions 手動觸發**
1. 前往 GitHub → Actions → CD Pipeline
2. 點選 **Run workflow**
3. 在 `manual_version` 欄位輸入版本字串（例如 `server_production_v1.0.0.1_initial`）

### 3.3 部署流程

CD Pipeline 會依序執行：
1. `parse_version`：解析版本標籤
2. `build_and_push`：建置並推送映像到 GHCR
3. `deploy_server_production`：
   - 建立 `.env` 檔案（從 GitHub Secrets）
   - 產生 `docker-compose.override.ci.yml`
   - 啟動服務（MongoDB、RabbitMQ、State Management、Analysis Service）
   - 等待 MongoDB 就緒
   - 初始化管理員帳號
   - **執行語法 Smoke Test**
   - **執行健康檢查**

## 4. 驗證與監控

### 4.1 自動驗證（CD Pipeline 執行）

Server Production 部署時會自動執行：

```bash
# 語法 Smoke Test
docker run --rm <state_image>:<version> python -m compileall /app
docker run --rm <analysis_image>:<version> python -m compileall /app

# 健康檢查
curl -f http://localhost:${PRODUCTION_STATE_MANAGEMENT_PORT}/health
```

### 4.2 手動驗證

部署完成後，可在 Runner 機器上執行：

```bash
# 檢查容器狀態
docker compose -f core/docker-compose.yml -f core/docker-compose.override.ci.yml ps

# 健康檢查
curl http://localhost:<STATE_MANAGEMENT_PORT>/health

# 查看服務日誌
docker compose -f core/docker-compose.yml logs -f state_management
docker compose -f core/docker-compose.yml logs -f analysis_service
```

### 4.3 回滾

如需回滾到舊版本：

```bash
# 方法 1：推送舊版本號
git commit --allow-empty -m "server_production_v1.0.0.0_rollback"
git push origin main

# 方法 2：手動指定舊映像
docker compose -f core/docker-compose.yml -f core/docker-compose.override.ci.yml up -d
```

## 5. Edge Production

Edge Production 僅部署 Analysis Service，需連線到外部的核心服務。

### 5.1 必要的 Secrets

在 GitHub Secrets 新增以下變數（前綴為 `EDGE_`）：
- `EDGE_MONGODB_HOST`、`EDGE_MONGODB_PORT` 等（指向核心服務位址）
- `EDGE_STATE_MANAGEMENT_URL`（指向 Server Production 的 State Management）

### 5.2 驗證

```bash
# 檢查容器狀態
docker compose -f core/docker-compose.edge.override.yml ps

# 檢查連線狀態
docker logs analysis_service --tail 50
```

## 6. 常見問題

### Q1：部署時出現 `env file .env not found`

**原因**：GitHub Secrets 未正確設定。

**解決**：
1. 確認所有 11 個 `PRODUCTION_*` secrets 都已設定
2. 確認 `ADMIN_PASSWORD` 和 `ADMIN_EMAIL` 已設定

### Q2：健康檢查失敗

**原因**：服務尚未完全啟動，或 Port 設定錯誤。

**解決**：
1. 檢查 `PRODUCTION_STATE_MANAGEMENT_PORT` secret 值是否正確
2. 在 Runner 機器上執行 `docker ps` 確認服務狀態
3. 檢查日誌：`docker logs state_management`

### Q3：MongoDB 連線失敗

**原因**：MongoDB 尚未就緒或認證資訊錯誤。

**解決**：
1. 等待 MongoDB 完全啟動（Pipeline 會自動等待最多 60 秒）
2. 確認 `PRODUCTION_MONGODB_*` secrets 值正確

### Q4：GHCR 映像拉取失敗

**原因**：Runner 無法存取 GHCR 或認證失敗。

**解決**：
1. 確認 Runner 可以連外
2. 檢查 GitHub Token 權限是否包含 `packages:read`
