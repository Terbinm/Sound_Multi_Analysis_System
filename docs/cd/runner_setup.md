# 自託管 Docker Runner 註冊與標籤設定指南

## 1. 前置需求
- 已安裝 Docker 與 Docker Compose（Windows 可用 Docker Desktop，Linux 建議使用官方套件）。
- 有管理員權限可安裝 runner 服務。
- GitHub Repo 的權限允許新增 self-hosted runner。

## 2. 在 GitHub 後台取得註冊指令（對應 UI 按鈕）
1. 打開專案頁 → **Settings** → **Actions** → **Runners**。
2. 點選 **New self-hosted runner**（畫面會跳出步驟）。
3. 選擇 OS 與架構（Windows / Linux、x64 等）。
4. 頁面會列出 3 段指令：下載 runner、解壓、執行 `config`。複製這些指令到你的主機執行即可。  
   - 下方提供的指令範例與頁面一致，只需替換版本與 token。  
   - Token 具時效性，生成後請儘快執行。
   - Runner Group 提示：config 途中若提示「Enter the name of the runner group」，直接按 Enter 使用 `Default`。只有在組織層級事先建立 runner group 時才能輸入自訂名稱；若輸入 `staging` 而未建立同名群組會顯示找不到。

## 3. 安裝與註冊（Linux）
```bash
# 1) 建立與下載（依 GitHub UI 顯示的版本號替換）
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-linux-x64-X.Y.Z.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

# 2) 依照 GitHub UI 的 config 指令執行，範例：
./config.sh --url https://github.com/<owner>/<repo> --token <RUNNER_TOKEN> \
  --labels "self-hosted,linux,docker,staging" \
  --name staging-runner-1

# 3) 以服務啟動（建議）
sudo ./svc.sh install
sudo ./svc.sh start
```
- 如果是 server_production / edge_production 環境，請把 `--labels` 改為 `self-hosted,linux,docker,server_production` 或 `self-hosted,linux,docker,edge_production`。
- 需要讓 runner 用戶能操作 Docker：`sudo usermod -aG docker <runner_user>` 後重新登入。

## 4. 安裝與註冊（Windows PowerShell）
```powershell
# 1) 建立與下載（版本號依 GitHub UI）
mkdir C:\actions-runner
cd C:\actions-runner
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-win-x64-X.Y.Z.zip -OutFile actions-runner-win-x64.zip
Expand-Archive actions-runner-win-x64.zip -DestinationPath .

# 2) 依 GitHub UI 的 config 指令執行，範例：
.\config.cmd --url https://github.com/<owner>/<repo> --token <RUNNER_TOKEN> --labels "self-hosted,windows,docker,staging" --name staging-runner-1

# 3) 啟動方式
.\run.cmd                # 互動模式測試
.\svc install ; .\svc start  # 推薦：安裝成服務自動啟動
```
- 標籤依環境替換為 `server_production` 或 `edge_production`。
- 確保 Docker Desktop 已安裝並允許該帳號存取（Settings > General 勾選 WSL2 / 允許非管理員執行）。

## 5. 放置專案與 `.env`
- runner 安裝路徑與 repo 路徑可分開；workflow 會將 repo 檢出到 `<runner_root>/_work/<repo>/<repo>`。只要 `.env` 放在該專案根目錄即可被 compose 覆蓋檔讀到。
- 在 runner 主機上 clone 本專案到慣用路徑（例如 `C:\repo\Sound_Multi_Analysis_System` 或 `/opt/repos/Sound_Multi_Analysis_System`），並放置 `.env`：
  - Staging：`cp docs/cd/env.staging.sample .env`
  - Server Production：`cp docs/cd/env.server_production.sample .env`
  - Edge Production：`cp docs/cd/env.edge_production.sample .env`
- 調整 `.env` 內容符合實際主機/埠。

## 6. 驗證 runner 狀態
- 在 GitHub Actions Runner 列表確認 runner 變為 Online（綠點）。
- 手動觸發 `CD Pipeline` 的 `workflow_dispatch`，填入對應環境 tag（如 `staging_v1.0.0.0_init`）驗證。
- 在 runner 上檢查 `docker ps` / `docker compose ps`，或查看 Actions log 確認 compose 已啟動。
