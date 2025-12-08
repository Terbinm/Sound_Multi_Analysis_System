# 持續部署規劃（GitHub Actions）

## 1. 目標
- 為 State Management（核心後端）與 Analysis Service（分析節點）建立可重複的標籤式部署流程。
- 以版本前綴決定部署目標環境，並透過自託管 runner 群組落地部署。
- 產出可直接在 Actions 執行的 workflow（`.github/workflows/cd.yml`），並保留 dev 版不做 CD。

## 2. 服務拆解與現況
- **State Management**：`core/state_management/`，Dockerfile 基於 `python:3.10-slim`，預設 CMD 指向不存在的 `app:app`，部署時需改用 `python state_management_main.py`。
- **Analysis Service**：`sub_system/analysis_service/`，Dockerfile 基於 `python:3.9-slim`，實際入口為 `analysis_main.py`（Dockerfile 的 `main.py` 需由流程暫時補上）。
- 依賴檔案目前命名為「`  requirements.txt`」（前置空白），workflow 會複製成標準檔名以供建置使用。
- `.env` 需在 runner 上提供（至少含 MongoDB/RabbitMQ/STATE_MANAGEMENT_* 等連線資訊），Compose 依此注入設定。

## 3. 版本標籤規則（tag）
- `dev_v{主}.{中}.{次}.{流水}_{說明}`：**僅 CI 不部署**。
- `staging_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **staging** runner 群組並執行基本測試。
- `server_production_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **server_production** runner 群組。
- `edge_production_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **edge_production** runner 群組（workflow 同時相容 `edge_productio_v...`）。
- 流水號後的 `{說明}` 僅用於人類辨識，映像 tag 只使用版本號避免 Docker tag 非法字元。
  - 範例：`staging_v1.4.2.7_rabbitmq-tuning`、`server_production_v2.0.0.3_hotfix-a`.

## 4. GitHub Actions 流程概覽（cd.yml）
- **觸發**：上述 tag push；`workflow_dispatch` 可手動指定 tag。
- **Runner 群組對應**：
  - `staging` → `[self-hosted, staging]`
  - `server_production` → `[self-hosted, server_production]`
  - `edge_production` → `[self-hosted, edge_production]`
- **主要 jobs**
  1) `parse_tag`：解析 tag，將環境/版本/描述輸出；`dev_*` 直接跳過後續部署。
  2) `build_and_push`（ubuntu-latest）：準備需求檔（複製 `  requirements.txt`、補上 `main.py` 別名），建置並推送 GHCR 映像：
     - `ghcr.io/<owner>/sound-state-management:{version}` 與 `{env}-latest`
     - `ghcr.io/<owner>/sound-analysis-service:{version}` 與 `{env}-latest`
  3) `deploy_staging`（staging runner）：先拉取映像，產生臨時 Compose override 檔，啟動 MongoDB/RabbitMQ/State Management/Analysis Service，並以容器執行 `python -m compileall` 作為語法 smoke test，最後打 `/health`。
  4) `deploy_server_production`（server_production runner）：同上但不強制 smoke test，預設啟動核心與分析服務。
  5) `deploy_edge_production`（edge_production runner）：僅部署 Analysis Service，假設連線到既有的 MongoDB/RabbitMQ（由 `.env` 提供位址）。

## 5. 部署執行重點
- **依賴檔案修補**：workflow 在建置前會將「`  requirements.txt`」複製成 `requirements.txt`（根目錄與 `core/state_management/` 各一份），並複製 `analysis_main.py` 為 `main.py` 以滿足 Dockerfile。
- **映像命名**：`state_management` 及 `analysis_service` 映像均以版本號與 `{env}-latest` 雙 tag，方便回滾與環境固定。
- **Compose 覆蓋**：部署 job 會動態寫入 `core/docker-compose.override.ci.yml` 以指定映像、修正啟動命令與新增 analysis_service 服務，並沿用 `.env` 中的連線資訊。
- **測試策略**：目前無自動化測試，staging 以 `python -m compileall` 進行語法檢查；若未來補充測試，可在 deploy job 中以 `docker run … pytest` 取代。

## 6. 先決條件與機密
- 自託管 runner 須安裝 Docker / Docker Compose 並能登入 GHCR（預設使用 `GITHUB_TOKEN`，需 packages:write）。
- 每個環境的 runner 需放置對應 `.env`（同 repo 根目錄結構），至少包含：
  ```env
  MONGODB_HOST=...
  MONGODB_PORT=55101
  MONGODB_USERNAME=web_ui
  MONGODB_PASSWORD=hod2iddfsgsrl
  MONGODB_DATABASE=web_db
  RABBITMQ_HOST=...
  RABBITMQ_PORT=55102
  RABBITMQ_USERNAME=admin
  RABBITMQ_PASSWORD=rabbitmq_admin_pass
  STATE_MANAGEMENT_PORT=55103
  STATE_MANAGEMENT_URL=http://<state_host>:55103
  ```
- 若 server/edge 連線至外部 MongoDB 或 RabbitMQ，請在各自 `.env` 內覆寫主機與連接埠。

## 7. 操作步驟
1. 合併程式碼後建立 tag，例如：`git tag staging_v1.0.0.0_first-release` 並 push。
2. 於 Actions 觀察 `CD Pipeline`，確認 `build_and_push` 完成後對應環境的 deploy job 成功。
3. 部署完成後，於目標主機 `docker compose -f core/docker-compose.yml ps`（或 edge 用生成的覆蓋檔）確認容器狀態。

## 8. 已知風險 / 後續優化
- 正式修正檔名：建議將「`  requirements.txt`」更名為標準檔名並放入 `core/state_management/`，以移除 workflow 的臨時複製步驟。
- Docker 入口：調整 `core/state_management/Dockerfile` CMD 指向 `state_management_main:app`（或新增 app.py），並將 Analysis Service Dockerfile CMD 改為 `analysis_main.py` 以免倚賴覆蓋。
- 測試增補：補充最小化整合測試（如 `/health` 檢查、RabbitMQ/Mongo 連線檢測）以取代 compileall。
