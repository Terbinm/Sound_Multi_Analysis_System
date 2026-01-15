# CD 導覽與文件索引

> **最後更新**：2025-01

本資料夾彙整持續部署（CD）相關指引，涵蓋版本標籤規則、環境準備、首次串接與驗證流程。

## 版本與環境對照

| 環境 | 標籤格式 | Runner 標籤 | 驗證步驟 |
|------|----------|-------------|----------|
| Dev | `dev_v*` | N/A | 僅 CI，不部署 |
| Staging | `staging_v*` | `[self-hosted, staging]` | Smoke Test + 健康檢查 |
| Server Production | `server_production_v*` | `[self-hosted, server_production]` | Smoke Test + 健康檢查 |
| Edge Production | `edge_production_v*` | `[self-hosted, edge_production]` | Edge Client (systemd) |

### 驗證步驟說明

**Staging 與 Server Production** 現在具有相同的驗證流程：
1. **語法 Smoke Test**：`python -m compileall /app` 驗證 Python 語法
2. **健康檢查**：`curl -f http://localhost:<PORT>/health` 確認服務正常運行

### 重要安全改進（2025-01）

- **移除硬編碼密碼**：`docker-compose.override.ci.yml` 不再包含預設密碼，所有敏感資訊由 GitHub Secrets 提供
- **環境一致性**：Staging 與 Production 使用相同的部署和驗證流程
- **容器引用改進**：使用 `docker compose exec` 取代硬編碼容器名稱，提高可靠性

## 主要內容

| 文件 | 說明 |
|------|------|
| `staging_onboarding.md` | Staging 首次接入、GitHub Secrets 設定、流程測試 |
| `production_onboarding.md` | Server Production 與 Edge Production 首次接入與驗證 |
| `github_secrets_setup.md` | GitHub Secrets 設定指南（所有環境） |
| `runner_setup.md` | 自託管 Runner 安裝與標籤設定 |
| `env.*.sample` | 環境變數範例檔案 |

## 必要的 GitHub Secrets

部署前必須在 GitHub Settings → Secrets 設定以下變數（詳見 `github_secrets_setup.md`）：

**通用（管理員帳號）：**
- `ADMIN_PASSWORD`
- `ADMIN_EMAIL`

**Staging 環境（11 個）：** `STAGING_MONGODB_*`、`STAGING_RABBITMQ_*`、`STAGING_STATE_MANAGEMENT_*`

**Production 環境（11 個）：** `PRODUCTION_MONGODB_*`、`PRODUCTION_RABBITMQ_*`、`PRODUCTION_STATE_MANAGEMENT_*`

**Edge 環境（1 個）：** `EDGE_SERVER_URL`（Edge Client 連線至核心服務的 URL）
