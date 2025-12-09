# Production（Server / Edge）首次自動化接入指引

## 1. 環境分工
- **Server Production**：標籤 `server_production_v*`，部署到 `[self-hosted, server_production]` runner，啟動 MongoDB、RabbitMQ、State Management、Analysis Service（與 staging 類似，但預設不跑 compileall）。
- **Edge Production**：標籤 `edge_production_v*` 或 `edge_productio_v*`，部署到 `[self-hosted, edge_production]` runner，只啟動 Analysis Service，假設外部已有 MongoDB / RabbitMQ / State Management 可連。

## 2. `.env` 準備（必填）
放在「專案根目錄」（例如 `/path/to/repo/.env`）。`core/docker-compose.yml` 位於 `core/`，覆蓋檔用 `env_file: ../.env` 回到專案根目錄讀取同一份 `.env`。

最小範例（Server）：
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

Edge 請改成可達的核心服務位址（多半是雲端/資料中心 IP）：
```
MONGODB_HOST=<core-mongodb-host>
RABBITMQ_HOST=<core-rabbitmq-host>
STATE_MANAGEMENT_URL=http://<core-state-host>:55103
```

Windows 建立：
```
cd C:\path\to\repo
@'
…環境內容…
'@ | Set-Content -Path .env -Encoding UTF8
Get-Content .env
```

Linux 建立：
```
cd /path/to/repo
cat > .env <<'EOF'
…環境內容…
EOF
cat .env
chmod 600 .env  # 可選
```

## 3. 首次接入步驟
1) 確認自託管 runner 標籤：`[self-hosted, server_production]` 或 `[self-hosted, edge_production]`。  
2) 放置 `.env`（見上），確保 Docker/Compose 已安裝且能連外拉 GHCR。  
3) 建立並推送對應標籤，例如：
   - Server：`git tag server_production_v1.0.0.0_first-prod && git push origin server_production_v1.0.0.0_first-prod`
   - Edge：`git tag edge_production_v1.0.0.0_edge-node-1 && git push origin edge_production_v1.0.0.0_edge-node-1`
   也可在 Actions 的 `CD Pipeline` 以 `workflow_dispatch` 填入 `manual_tag`。  
4) 觀察 Actions：`build_and_push` 建置/推 GHCR → `deploy_server_production` 或 `deploy_edge_production` 執行 Compose。  
   - Server：生成 `core/docker-compose.override.ci.yml`，啟動 MongoDB/RabbitMQ/State Management/Analysis Service。  
   - Edge：生成 `core/docker-compose.edge.override.yml`，只啟動 Analysis Service，連線 `.env` 內指定的遠端服務。

## 4. 驗證與回滾
- Server 驗證：
  - `docker compose -f core/docker-compose.yml -f core/docker-compose.override.ci.yml ps`
  - `curl http://localhost:55103/health`（依 `.env` 調整主機/埠）
- Edge 驗證：
  - `docker compose -f core/docker-compose.edge.override.yml ps`
  - 檢查分析節點是否正常連線：觀察 Analysis Service 日誌與遠端 RabbitMQ/Mongo 連線狀態。
- 回滾：推送舊版本號 tag 重新部署；或手動 `docker compose ... up -d` 指定舊映像。

## 5. 常見問題
- GHCR 認證：預設用 `GITHUB_TOKEN`，若 runner 禁外網需預先快取映像或改用私有鏡像庫。  
- `.env` 路徑錯誤：覆蓋檔使用相對路徑 `../.env`；若調整目錄結構需同步修改 workflow 或覆蓋檔。  
- 需求檔/入口補丁：目前 workflow 會複製「`  requirements.txt`」→`requirements.txt` 並將 `analysis_main.py` 複製為 `main.py` 以符合 Dockerfile；建議日後修正檔名與 CMD，移除補丁步驟。***
