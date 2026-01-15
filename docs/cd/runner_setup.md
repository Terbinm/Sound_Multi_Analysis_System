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

## 4. 安裝與註冊（Windows PowerShell，含互動提示）
```powershell
# 1) 建立與下載（版本號依 GitHub UI）
mkdir C:\actions-runner
cd C:\actions-runner
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/vX.Y.Z/actions-runner-win-x64-X.Y.Z.zip -OutFile actions-runner-win-x64.zip
Expand-Archive actions-runner-win-x64.zip -DestinationPath .

# 2) 執行 config，示例對應 staging 環境：
.\config.cmd --url https://github.com/<owner>/<repo> --token <RUNNER_TOKEN>
# 互動輸入建議：
# - Runner group: 直接按 Enter 使用 Default（免費版無自訂群組）
# - Runner name: 按 Enter 接受預設或自訂如 E308-STAGE-SERV
# - 額外標籤: 輸入環境標籤，例如 staging（或 server_production / edge_production）
#   最終標籤列表會包含 self-hosted, Windows, X64, staging
# - Work folder: 按 Enter 使用 _work
# - Run as service?: 輸入 Y（建議）並按 Enter，帳號預設 NT AUTHORITY\NETWORK SERVICE

# 3) 服務啟動（若前一步選 Y 會自動安裝服務）
.\svc install ; .\svc start   # 再執行一次保險可啟動服務
# 若僅測試可用互動模式：.\run.cmd
```
- 標籤依環境改為 `staging` / `server_production` / `edge_production`，Workflow 會據此配對。
- 確保 Docker Desktop 已安裝並允許該帳號存取（Settings > General 勾選 WSL2 / 允許非管理員執行）。
- 免費版沒有 Runner Group，請使用 Default，靠標籤區分環境。

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

## 7. 常見問題排除

### 7.1 Windows Docker 權限問題

**錯誤訊息**：
```
permission denied while trying to connect to the docker API at npipe:////./pipe/docker_engine
```

**原因**：GitHub Actions runner 服務帳號沒有權限存取 Docker Desktop。

**解決方式**（以系統管理員身份執行 PowerShell）：

```powershell
# 1) 查看目前 runner 服務用什麼帳號執行
Get-Service actions.runner.* | Select-Object Name, StartType, Status

# 2) 將帳號加入 docker-users 群組（把 USERNAME 換成實際的使用者名稱）
Add-LocalGroupMember -Group "docker-users" -Member "USERNAME"

# 如果 runner 是用 SYSTEM 帳號執行：
Add-LocalGroupMember -Group "docker-users" -Member "NT AUTHORITY\SYSTEM"

# 如果 runner 是用 NETWORK SERVICE 帳號執行：
Add-LocalGroupMember -Group "docker-users" -Member "NT AUTHORITY\NETWORK SERVICE"

# 3) 重啟 runner 服務
Restart-Service actions.runner.*
```

**手動方式**：
1. 開啟「電腦管理」(Computer Management)
2. 展開「本機使用者和群組」→「群組」
3. 找到 `docker-users` 群組，雙擊
4. 點「新增」，加入執行 GitHub Actions runner 的使用者帳號
5. 重新啟動 runner 服務
