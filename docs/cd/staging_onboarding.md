# Staging 首次自動化接入與測試指引

## 1. 目標與前提
- 目標：讓 `[self-hosted, staging]` runner 接手 `staging_v*` 標籤的 CD 部署。
- 前提：runner 主機已安裝 Docker、Docker Compose，可存取Github repo與GHCR（預設用 `GITHUB_TOKEN`）。
- 版本觸發：`staging_v{主}.{中}.{次}.{流水}_{說明}` 標籤（說明只做標記，映像 tag 只用版本號）。

## 2. 建立 `.env`（必填）
將 `.env` 放在「專案根目錄」（例如 `/path/to/repo/.env`）。`core/docker-compose.yml` 在 `core/` 子目錄，workflow 產生的覆蓋檔使用 `env_file: ../.env`，會回到專案根目錄讀取同一份 `.env`。

最小範例（請依實際服務位置調整主機/埠）：
```
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


Windows（PowerShell）建立：
```
cd C:\path\to\repo
@'
…以上內容…
'@ | Set-Content -Path .env -Encoding UTF8
Get-Content .env
```

Linux 建立：
```
cd /path/to/repo
cat > .env <<'EOF'
…以上內容…
EOF
cat .env
chmod 600 .env  # 可選，確保 runner 帳號可讀
```

## 3. 首次串接步驟
1) 在 runner 上準備目錄：`git clone` 到工作路徑並放好 `.env`。  
2) 確認 runner 標籤含 `self-hosted`、`staging`。  
3) 建立並推送 tag，例如：
   ```
   git tag staging_v1.0.0.0_first-release
   git push origin staging_v1.0.0.0_first-release
   ```
   或在 Actions 的 `CD Pipeline` 用 `workflow_dispatch` 輸入同格式 `manual_tag`。  
4) 觀察 Actions：`parse_tag` → `build_and_push`（建置/推 GHCR）→ `deploy_staging`。  
5) `deploy_staging` 會：
   - 產生 `core/docker-compose.override.ci.yml`
   - `docker compose up -d` 啟動 MongoDB、RabbitMQ、State Management、Analysis Service
   - 在映像內跑 `python -m compileall /app`
   - `curl` 核心 `/health`

## 4. 驗證與回滾
- 驗證：
  - `docker compose -f core/docker-compose.yml -f core/docker-compose.override.ci.yml ps`
  - `curl http://localhost:55103/health`（或 `.env` 中的實際埠）
- 回滾：改推舊版本號的 staging tag，即可用舊映像重新部署；或手動 `docker compose ... up -d` 指定舊 tag。

## 5. 常見問題
- GHCR 拉取失敗：確認 runner 能連外且 `GITHUB_TOKEN` 未被限制 packages:write/read。  
- `.env` 未讀到：確認檔案在 repo 根目錄，Compose 覆蓋檔路徑 `../.env` 未被移動。  
- 需求檔或入口：workflow 會臨時複製 `  requirements.txt` 與 `analysis_main.py -> main.py`，避免 Dockerfile 失敗。後續建議修正檔名與 CMD 以移除補丁步驟。***
