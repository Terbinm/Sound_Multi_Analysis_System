# 持續部署（CD）完整指南

本文件彙整持續部署（CD）相關指引，涵蓋版本標籤規則、環境準備、Runner 設定、首次接入與驗證流程。

---

## 目錄

1. [目標與架構](#1-目標與架構)
2. [版本標籤規則](#2-版本標籤規則)
3. [環境與 Runner 對照](#3-環境與-runner-對照)
4. [服務說明](#4-服務說明)
5. [GitHub Actions 流程概覽](#5-github-actions-流程概覽)
6. [自託管 Runner 設定](#6-自託管-runner-設定)
7. [環境設定檔（.env）](#7-環境設定檔env)
8. [Staging 環境接入](#8-staging-環境接入)
9. [Production 環境接入](#9-production-環境接入)
10. [驗證與回滾](#10-驗證與回滾)
11. [常見問題](#11-常見問題)

---

## 1. 目標與架構

- 為 **State Management**（核心後端）與 **Analysis Service**（分析節點）建立可重複的標籤式部署流程。
- 以版本前綴決定部署目標環境，並透過自託管 runner 群組落地部署。
- 產出可直接在 Actions 執行的 workflow（`.github/workflows/cd.yml`），並保留 dev 版不做 CD。

---

## 2. 版本標籤規則

CD 流程以 **commit message** 作為觸發依據，格式如下：

`{env}_v{主}.{中}.{次}.{流水}_{說明}`

| 前綴 | 環境 | 行為 |
|------|------|------|
| `dev_v*` | 開發 | **僅 CI，不部署** |
| `staging_v*` | Staging | 部署到 staging runner，執行語法檢查與健康檢查 |
| `server_production_v*` | Server Production | 部署到 server_production runner |
| `edge_production_v*` | Edge Production | 部署到 edge_production runner（僅 Analysis Service） |

**使用方式：**
```bash
# 觸發 staging 部署
git commit -m "staging_v1.4.2.7_rabbitmq-tuning"
git push origin main

# 觸發 production 部署
git commit -m "server_production_v2.0.0.3_hotfix-a"
git push origin main

# 觸發 edge 部署
git commit -m "edge_production_v1.0.0.0_edge-node-1"
git push origin main
```

> **注意**：
> - 只有 commit message **第一行**符合版本格式時才會觸發 CD
> - 一般 commit（不符合格式）不會觸發部署流程
> - `{說明}` 僅用於人類辨識，映像 tag 只使用版本號（避免 Docker tag 非法字元）

---

## 3. 環境與 Runner 對照

| 環境 | Runner 標籤 | 部署內容 |
|------|-------------|----------|
| Staging | `[self-hosted, staging]` | MongoDB + RabbitMQ + State Management + Analysis Service |
| Server Production | `[self-hosted, server_production]` | MongoDB + RabbitMQ + State Management + Analysis Service |
| Edge Production | `[self-hosted, edge_production]` | Analysis Service（連線至遠端核心服務） |

---

## 4. 服務說明

### State Management
- 路徑：`core/state_management/`
- Dockerfile：`python:3.10-slim`
- 入口：`state_management_main.py`（由 docker-compose override 指定）

### Analysis Service
- 路徑：`sub_system/analysis_service/`
- Dockerfile：`python:3.9-slim`
- 入口：`analysis_main.py`

---

## 5. GitHub Actions 流程概覽

Workflow 檔案：`.github/workflows/cd.yml`

### 觸發方式
- Push 到 `main` 或 `master` 分支（commit message 符合版本格式時觸發）
- `workflow_dispatch` 可手動指定版本字串

### 主要 Jobs

```
┌─────────────────┐
│  parse_version  │  解析 commit message，輸出環境/版本/描述
└────────┬────────┘
         │ 不符合格式 or dev_* → 結束（不部署）
         ▼
┌─────────────────┐
│ build_and_push  │  建置並推送 GHCR 映像
└────────┬────────┘
         │
    ┌────┼────┬─────────────────┐
    ▼    ▼    ▼                 ▼
staging  server_production  edge_production
```

### 映像命名
- `ghcr.io/<owner>/sound-state-management:{version}` 與 `{env}-latest`
- `ghcr.io/<owner>/sound-analysis-service:{version}` 與 `{env}-latest`

---

## 6. 自託管 Runner 設定

### 前置需求
- 已安裝 Docker 與 Docker Compose
- 有管理員權限可安裝 runner 服務
- GitHub Repo 的權限允許新增 self-hosted runner

### 在 GitHub 取得註冊指令
1. 打開專案頁 → **Settings** → **Actions** → **Runners**
2. 點選 **New self-hosted runner**
3. 選擇 OS 與架構（Windows / Linux、x64 等）
4. 複製並執行頁面顯示的指令

> **提示**：Runner Group 若提示輸入名稱，直接按 Enter 使用 `Default`（免費版無自訂群組）。

### Linux 安裝

```bash
# 1) 建立與下載（依 GitHub UI 顯示的版本號替換）
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-linux-x64-X.Y.Z.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

# 2) 執行 config（範例為 staging 環境）
./config.sh --url https://github.com/<owner>/<repo> --token <RUNNER_TOKEN> \
  --labels "self-hosted,linux,docker,staging" \
  --name staging-runner-1

# 3) 以服務啟動
sudo ./svc.sh install
sudo ./svc.sh start

# 4) 讓 runner 用戶能操作 Docker
sudo usermod -aG docker <runner_user>
```

### Windows 安裝 (PowerShell)

```powershell
# 1) 建立與下載
mkdir C:\actions-runner
cd C:\actions-runner
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-win-x64-X.Y.Z.zip -OutFile actions-runner-win-x64.zip
Expand-Archive actions-runner-win-x64.zip -DestinationPath .

# 2) 執行 config
.\config.cmd --url https://github.com/<owner>/<repo> --token <RUNNER_TOKEN>
# 互動輸入：
# - Runner group: 按 Enter 使用 Default
# - Runner name: 自訂名稱如 E308-STAGE-SERV
# - 額外標籤: staging（或 server_production / edge_production）
# - Work folder: 按 Enter 使用 _work
# - Run as service?: 輸入 Y

# 3) 啟動服務
.\svc install ; .\svc start
```

---

## 7. 環境設定檔（.env）

`.env` 放置於**專案根目錄**（例如 `/path/to/repo/.env`）。

### Staging / Server Production 範例

```env
MONGODB_HOST=localhost
MONGODB_PORT=55101
MONGODB_USERNAME=web_ui
MONGODB_PASSWORD=hod2iddfsgsrl
MONGODB_DATABASE=web_db

RABBITMQ_HOST=localhost
RABBITMQ_PORT=55102
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=rabbitmq_admin_pass

STATE_MANAGEMENT_PORT=55103
STATE_MANAGEMENT_URL=http://localhost:55103
```

### Edge Production 範例

```env
# 遠端 MongoDB（核心環境提供）
MONGODB_HOST=<core-mongodb-host>
MONGODB_PORT=55101
MONGODB_USERNAME=web_ui
MONGODB_PASSWORD=hod2iddfsgsrl
MONGODB_DATABASE=web_db

# 遠端 RabbitMQ（核心環境提供）
RABBITMQ_HOST=<core-rabbitmq-host>
RABBITMQ_PORT=55102
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=rabbitmq_admin_pass

# 核心狀態管理服務 URL
STATE_MANAGEMENT_PORT=55103
STATE_MANAGEMENT_URL=http://<core-state-host>:55103
```

### 建立 .env

**Linux：**
```bash
cd /path/to/repo
cp docs/cd/env.staging.sample .env  # 或對應環境的 sample
chmod 600 .env
```

**Windows (PowerShell)：**
```powershell
cd C:\path\to\repo
Copy-Item docs\cd\env.staging.sample .env
```

---

## 8. Staging 環境接入

### 首次接入步驟

1. 確認 runner 標籤包含 `self-hosted`、`staging`
2. 在 runner 上 clone 專案並放置 `.env`
3. 使用版本格式的 commit message 並推送：
   ```bash
   git commit -m "staging_v1.0.0.0_first-release"
   git push origin main
   ```
4. 觀察 Actions：`parse_version` → `build_and_push` → `deploy_staging`

### Staging 部署流程
1. 產生 `core/docker-compose.override.ci.yml`
2. `docker compose up -d` 啟動所有服務
3. 執行 `python -m compileall /app` 語法檢查
4. `curl /health` 健康檢查

---

## 9. Production 環境接入

### Server Production

與 Staging 類似，但不執行語法 smoke test。

```bash
git commit -m "server_production_v1.0.0.0_first-prod"
git push origin main
```

### Edge Production

僅部署 Analysis Service，連線至遠端核心服務。

```bash
git commit -m "edge_production_v1.0.0.0_edge-node-1"
git push origin main
```

部署會產生 `core/docker-compose.edge.override.yml`，只啟動 Analysis Service。

---

## 10. 驗證與回滾

### 驗證指令

**Staging / Server Production：**
```bash
docker compose -f core/docker-compose.yml -f core/docker-compose.override.ci.yml ps
curl http://localhost:55103/health
```

**Edge Production：**
```bash
docker compose -f core/docker-compose.edge.override.yml ps
# 檢查 Analysis Service 日誌確認連線狀態
docker logs analysis_service
```

### 回滾方式
- 使用舊版本號的 commit message 重新部署
- 或手動 `docker compose ... up -d` 指定舊映像

---

## 11. 常見問題

### GHCR 拉取失敗
- 確認 runner 能連外
- 確認 `GITHUB_TOKEN` 未被限制 `packages:write/read`

### .env 未讀到
- 確認檔案在 repo 根目錄
- Compose 覆蓋檔使用 `env_file: ../.env`，路徑不可變動

### Docker 權限問題 (Linux)
```bash
sudo usermod -aG docker <runner_user>
# 重新登入後生效
```

### Docker Desktop 權限問題 (Windows)
- Settings > General 勾選允許 WSL2 / 允許非管理員執行

---

## 附錄：範例檔案位置

| 檔案 | 說明 |
|------|------|
| `docs/cd/env.staging.sample` | Staging 環境 .env 範例 |
| `docs/cd/env.server_production.sample` | Server Production 環境 .env 範例 |
| `docs/cd/env.edge_production.sample` | Edge Production 環境 .env 範例 |
| `docs/cd/runner_setup.md` | Runner 詳細設定指南 |
| `docs/cd/staging_onboarding.md` | Staging 接入詳細指引 |
| `docs/cd/production_onboarding.md` | Production 接入詳細指引 |
