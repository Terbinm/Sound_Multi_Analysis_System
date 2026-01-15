# Staging 環境 Onboarding 完整指南（從重灌 Windows 開始）

> **最後更新**：2025-01
> **適用環境**：Staging Server
> **預計耗時**：約 60-90 分鐘（含下載時間）

---

## 目錄

1. [前言與預設條件](#1-前言與預設條件)
2. [WSL2 安裝與設定](#2-wsl2-安裝與設定)
3. [Docker Desktop 安裝與設定](#3-docker-desktop-安裝與設定)
4. [GitHub Self-Hosted Runner 安裝](#4-github-self-hosted-runner-安裝)
5. [設定 GitHub Secrets（重要）](#5-設定-github-secrets重要)
6. [專案 Clone 與環境設定](#6-專案-clone-與環境設定)
7. [首次部署測試](#7-首次部署測試)
8. [常見問題排查](#8-常見問題排查)
9. [附錄：路徑總覽](#9-附錄路徑總覽)

---

## 1. 前言與預設條件

### 重要更新（2025-01）

- **移除硬編碼密碼**：CD Pipeline 的 `docker-compose.override.ci.yml` 不再包含預設密碼
- **所有敏感資訊由 GitHub Secrets 提供**：包括連接埠設定
- **容器引用改進**：使用 `docker compose exec` 取代硬編碼容器名稱

### 1.1 本指南的目標

將一台剛重灌的 Windows 電腦設定為 **Staging 環境的 GitHub Self-Hosted Runner**，能夠：

- 接收 GitHub Actions 的 CD Pipeline 任務
- 自動拉取 Docker 映像並部署服務
- 執行健康檢查與 Smoke Test

### 1.2 唯一前提條件

- ✅ 您擁有 GitHub 專案 `Terbinm/Sound_Multi_Analysis_System` 的存取權限
- ✅ 您的 GitHub 帳號具備 **Settings → Actions → Runners** 的管理權限

### 1.3 推薦路徑清單（可自訂）

| 用途          | Windows 路徑                     | WSL2 內部路徑                                   | 可否修改                    |
| ------------- | -------------------------------- | ----------------------------------------------- | --------------------------- |
| WSL2 設定檔   | `C:\Users\<用戶名>\.wslconfig` | N/A                                             | ❌ 固定位置                 |
| GitHub Runner | N/A                              | `/opt/actions-runner`                         | ✅ 可修改                   |
| 專案程式碼    | N/A                              | `/opt/repos/Sound_Multi_Analysis_System`      | ✅ 可修改                   |
| 環境設定檔    | N/A                              | `/opt/repos/Sound_Multi_Analysis_System/.env` | ✅ 可修改（需與專案同目錄） |

> 💡 **提示**：本指南使用上述推薦路徑。如需修改，請在執行指令時替換對應路徑。

### 1.4 名詞解釋

| 名詞               | 說明                                                                  |
| ------------------ | --------------------------------------------------------------------- |
| WSL2               | Windows Subsystem for Linux 2，在 Windows 上執行 Linux 的虛擬化技術   |
| Self-Hosted Runner | 由您自行管理的 GitHub Actions 執行器，相對於 GitHub 提供的雲端 Runner |
| GHCR               | GitHub Container Registry，GitHub 的 Docker 映像倉庫                  |

---

## 2. WSL2 安裝與設定

### 2.1 啟用 WSL2（以系統管理員身份執行）

**步驟 1**：開啟 PowerShell（系統管理員）

1. 按下 `Win + X`
2. 選擇「Windows 終端機（系統管理員）」或「PowerShell（系統管理員）」

[[此處建議加入截圖：Win+X 選單]]

**步驟 2**：執行 WSL 安裝指令

```powershell
wsl --install
```

此指令會自動：

- 啟用「虛擬機器平台」功能
- 啟用「Windows 子系統 Linux 版」功能
- 下載並安裝 WSL2 Linux 核心
- 安裝預設的 Ubuntu 發行版

**步驟 3**：重新啟動電腦

```powershell
Restart-Computer
```

> ⚠️ **重要**：必須重新啟動才能完成 WSL2 啟用。

### 2.2 初始化 Ubuntu

**步驟 1**：重新開機後，Ubuntu 會自動啟動並要求設定

等待約 1-2 分鐘，系統會提示：

```
Installing, this may take a few minutes...
Please create a default UNIX user account...
Enter new UNIX username:
```

[[此處建議加入截圖：Ubuntu 初始化畫面]]

**步驟 2**：設定 Linux 使用者

```
Enter new UNIX username: soundadmin
New password: ********
Retype new password: ********
```

> 💡 **建議**：
>
> - 使用者名稱：`soundadmin`（或您偏好的名稱）
> - 密碼：請記住此密碼，後續 `sudo` 指令需要使用

**步驟 3**：驗證安裝成功

```bash
# 檢查 Ubuntu 版本
lsb_release -a

# 預期輸出類似：
# Distributor ID: Ubuntu
# Description:    Ubuntu 22.04.x LTS
# Release:        22.04
```

### 2.3 設定 WSL2 資源限制

為避免 WSL2 佔用過多系統資源，建議設定上限。

**步驟 1**：在 Windows PowerShell 中建立設定檔

```powershell
# 建立 .wslconfig 檔案
@'
[wsl2]
memory=4GB
processors=2
swap=2GB
localhostForwarding=true
'@ | Set-Content -Path "$env:USERPROFILE\.wslconfig" -Encoding UTF8

# 驗證檔案內容
Get-Content "$env:USERPROFILE\.wslconfig"
```

> 💡 **資源建議**：
>
> - `memory`：建議設為實體記憶體的 50%（最少 4GB）
> - `processors`：建議設為 CPU 核心數的 50%（最少 2 核）
> - 若主機記憶體 ≥16GB，可調整為 `memory=8GB`

**步驟 2**：重新啟動 WSL 以套用設定

```powershell
wsl --shutdown
wsl
```

**步驟 3**：驗證資源限制

```bash
# 在 WSL2 Ubuntu 中執行
free -h
nproc

# 預期輸出：
# 記憶體約 4GB（或您設定的值）
# CPU 核心數 2（或您設定的值）
```

### 2.4 設定 Windows 自動登入（Staging Server 必要）

由於 WSL2 需要使用者登入後才能啟動，Staging Server 需要設定為開機自動登入。

**步驟 1**：開啟自動登入設定工具

在 Windows PowerShell 中執行：

```powershell
control userpasswords2
```

[[此處建議加入截圖：使用者帳戶視窗]]

**步驟 2**：設定自動登入

1. 取消勾選「必須輸入使用者名稱和密碼，才能使用這台電腦」
2. 點選「套用」
3. 在彈出的視窗中輸入您的密碼兩次
4. 點選「確定」

> ⚠️ **安全提醒**：密碼會以加密形式儲存在 Windows 登錄中。請確保實體存取控制良好。

**步驟 3**：驗證設定

```powershell
# 檢查登錄設定（可選）
$RegPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Get-ItemProperty -Path $RegPath -Name "AutoAdminLogon"

# 應顯示 AutoAdminLogon : 1
```

### 2.5 設定 WSL2 開機自動啟動

確保 Windows 自動登入後，WSL2 也會自動啟動。

**步驟 1**：建立 WSL2 啟動批次檔

在 Windows PowerShell 中執行：

```powershell
# 建立批次檔（使用英文訊息避免編碼問題）
@'
@echo off
REM Auto-start WSL2 Ubuntu on Windows login
wsl -d Ubuntu -- echo "WSL2 started"
exit
'@ | Out-File -FilePath "$env:USERPROFILE\start-wsl.cmd" -Encoding ASCII -Force

# 確認檔案已建立
Get-Content "$env:USERPROFILE\start-wsl.cmd"
```

**步驟 2**：測試批次檔

```powershell
# 手動執行測試
& "$env:USERPROFILE\start-wsl.cmd"

# 檢查 WSL 狀態
wsl -l -v

# 應該看到 Ubuntu 的 STATE 為 Running
```

**步驟 3**：建立工作排程器任務（使用者登入時自動執行）

```powershell
# 刪除舊任務（如果存在）
Unregister-ScheduledTask -TaskName "AutoStartWSL2" -Confirm:$false -ErrorAction SilentlyContinue

# 建立新的排程任務
$TaskName = "AutoStartWSL2"
$TaskDescription = "Automatically start WSL2 Ubuntu when user logs in"
$ScriptPath = "$env:USERPROFILE\start-wsl.cmd"

# 使用者登入時觸發（配合自動登入，等同開機啟動）
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Trigger.Delay = "PT10S"  # 登入後延遲 10 秒執行

# 執行批次檔
$Action = New-ScheduledTaskAction -Execute $ScriptPath

# 設定：允許使用電池、不要因為閒置而停止
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# 使用當前使用者身份，最高權限
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

# 註冊任務
Register-ScheduledTask -TaskName $TaskName -Description $TaskDescription -Trigger $Trigger -Action $Action -Settings $Settings -Principal $Principal

Write-Host "✅ 已建立工作排程器任務：$TaskName"
```

**步驟 4**：測試排程任務

```powershell
# 關閉 WSL
wsl --shutdown

# 等待幾秒
Start-Sleep -Seconds 3

# 手動執行排程任務測試
Start-ScheduledTask -TaskName "AutoStartWSL2"

# 等待任務執行
Start-Sleep -Seconds 5

# 檢查 WSL 狀態
wsl -l -v

# 應該看到 Ubuntu 狀態為 Running
```

**步驟 5**：驗證工作排程器設定

```powershell
# 開啟工作排程器圖形介面
taskschd.msc
```

[[此處建議加入截圖：工作排程器中的 AutoStartWSL2 任務]]

在工作排程器中應該看到：
- 任務名稱：**AutoStartWSL2**
- 狀態：**就緒**
- 觸發程序：**登入時**
- 動作：執行 `C:\Users\<用戶名>\start-wsl.cmd`

**步驟 6**：完整測試（重新啟動電腦）

```powershell
# 重新啟動電腦
Restart-Computer
```

重開機後，Windows 會自動登入，工作排程器會在登入後 10 秒啟動 WSL2。

驗證方式：
```powershell
# 開機完成後（不要手動執行 wsl 指令），直接檢查狀態
wsl -l -v

# 如果 Ubuntu 狀態為 Running，表示設定成功 ✅
```

> 💡 **提示**：如果重開機後 WSL2 未啟動，請檢查：
> 1. 工作排程器中的任務歷程記錄
> 2. `$env:USERPROFILE\start-wsl.cmd` 檔案是否存在
> 3. 自動登入是否正常運作

---

## 3. Docker Desktop 安裝與設定

> ⚠️ **重要**：本章節在 **Windows** 中執行，不是 WSL2。

### 3.1 下載並安裝 Docker Desktop

**步驟 1**：下載 Docker Desktop

1. 開啟瀏覽器，前往：https://www.docker.com/products/docker-desktop/
2. 點選 **Download for Windows**
3. 下載完成後，執行安裝程式 `Docker Desktop Installer.exe`

[[此處建議加入截圖：Docker Desktop 下載頁面]]

**步驟 2**：執行安裝程式

1. 雙擊執行 `Docker Desktop Installer.exe`
2. 在安裝選項中，確保勾選：
   - ✅ **Use WSL 2 instead of Hyper-V (recommended)**
   - ✅ **Add shortcut to desktop**（可選）
3. 點選 **Ok** 開始安裝
4. 等待安裝完成（約 3-5 分鐘）
5. 安裝完成後，點選 **Close and restart**

[[此處建議加入截圖：Docker Desktop 安裝選項畫面]]

> ⚠️ **重要**：電腦會重新啟動（因為已設定自動登入，會自動進入桌面）。

**步驟 3**：首次啟動 Docker Desktop

重開機後，Docker Desktop 會自動啟動（或從開始功能表手動啟動）。

1. 接受 **Service Agreement**（服務條款）
2. 選擇 **Skip survey**（或填寫問卷）
3. 等待 Docker Engine 啟動（右下角圖示會從橘色變為綠色）

[[此處建議加入截圖：Docker Desktop 主畫面]]

### 3.2 設定 WSL2 整合

**步驟 1**：開啟 Docker Desktop 設定

1. 點選 Docker Desktop 視窗右上角的 **齒輪圖示（Settings）**
2. 左側選單選擇 **Resources** → **WSL Integration**

[[此處建議加入截圖：Docker Desktop WSL Integration 設定頁面]]

**步驟 2**：啟用 Ubuntu 整合

1. 確認 **Enable integration with my default WSL distro** 已勾選
2. 在 **Enable integration with additional distros** 區域，找到 **Ubuntu**
3. 開啟 Ubuntu 的開關（切換為啟用狀態）
4. 點選右下角 **Apply & restart**

[[此處建議加入截圖：啟用 Ubuntu 整合的開關]]

> 💡 **說明**：此設定會讓 Docker Desktop 自動在 WSL2 的 Ubuntu 中安裝 Docker CLI，無需手動安裝。

**步驟 3**：驗證 WSL2 中的 Docker

在 Windows PowerShell 中執行：

```powershell
# 進入 WSL2
wsl

# 檢查 Docker 版本
docker --version

# 預期輸出：
# Docker version 24.x.x, build xxxxxxx

# 測試 Docker 運作
docker run hello-world
```

[[此處建議加入截圖：docker run hello-world 成功輸出]]

預期輸出：
```
Hello from Docker!
This message shows that your installation appears to be working correctly.
...
```

**步驟 4**：驗證 Docker Compose

```bash
# 在 WSL2 中執行
docker compose version

# 預期輸出類似：
# Docker Compose version v2.24.x
```

**步驟 5**：修正 WSL2 的 Docker 憑證設定

> ⚠️ **重要**：此步驟解決 GitHub Actions 部署時無法登入 GHCR 的問題。

在 WSL2 中執行：

```bash
# 建立或編輯 Docker 配置檔
mkdir -p ~/.docker
nano ~/.docker/config.json
```

將內容修改為：
```
{
  "credsStore": ""
}
```

驗證
```
# 驗證設定
cat ~/.docker/config.json
```

預期輸出：
```json
{
  "credsStore": ""
}
```

> 💡 **說明**：WSL2 內的 Docker CLI 預設會嘗試使用 Windows Docker Desktop 的憑證管理器 (`docker-credential-desktop.exe`)，但在 GitHub Runner 執行時會找不到該執行檔。此設定將憑證改為儲存在 `~/.docker/config.json` 檔案中。

### 3.3 設定 Docker Desktop 開機自動啟動

**步驟 1**：開啟 Docker Desktop 設定

1. 點選 Docker Desktop 視窗右上角的 **齒輪圖示（Settings）**
2. 左側選單選擇 **General**

**步驟 2**：啟用開機自動啟動

1. 勾選 **Start Docker Desktop when you log in**
2. 點選 **Apply & restart**

[[此處建議加入截圖：General 設定頁面，顯示 Start Docker Desktop when you log in 選項]]

> 💡 **說明**：此設定配合 Windows 自動登入，可實現電腦開機後自動啟動 Docker。

**步驟 3**：（可選）調整資源限制

如果主機資源有限，可以調整 Docker Desktop 的資源使用：

1. 在 Settings 中選擇 **Resources**
2. 調整以下設定：
   - **CPUs**：建議設為總核心數的 50-75%
   - **Memory**：建議設為總記憶體的 50-75%
   - **Swap**：建議設為記憶體的 50%
   - **Disk image size**：根據需求調整（預設 60GB）
3. 點選 **Apply & restart**

[[此處建議加入截圖：Resources 設定頁面]]

> 💡 **建議設定**（假設主機有 16GB RAM、8 核 CPU）：
> - CPUs: 4-6
> - Memory: 8GB
> - Swap: 4GB

### 3.4 驗證完整設定

**步驟 1**：重新啟動電腦測試

```powershell
# 在 Windows PowerShell 中重新啟動
Restart-Computer
```

**步驟 2**：重開機後驗證（無需手動操作）

等待電腦自動登入和 Docker Desktop 自動啟動（約 1-2 分鐘），然後在 PowerShell 中執行：

```powershell
# 檢查 Docker Desktop 是否執行中
Get-Process "Docker Desktop" -ErrorAction SilentlyContinue

# 應該看到 Docker Desktop 程序

# 進入 WSL2 檢查
wsl

# 在 WSL2 中執行
docker ps

# 應該能正常顯示容器列表（即使是空的）
```

如果一切正常，表示設定成功 ✅：
- ✅ Windows 自動登入
- ✅ WSL2 自動啟動
- ✅ Docker Desktop 自動啟動
- ✅ WSL2 Ubuntu 可以使用 Docker

---

## 4. GitHub Self-Hosted Runner 安裝

### 4.1 取得 Runner 註冊 Token

**步驟 1**：登入 GitHub 並前往專案設定

1. 開啟瀏覽器，前往：https://github.com/Terbinm/Sound_Multi_Analysis_System
2. 點選 **Settings**（設定）
3. 左側選單選擇 **Actions** → **Runners**
4. 點選 **New self-hosted runner**

[[此處建議加入截圖：GitHub Settings → Actions → Runners 頁面]]

**步驟 2**：選擇執行環境

- Operating system：選擇 **Linux**
- Architecture：選擇 **x64**

[[此處建議加入截圖：選擇 Linux x64 的畫面]]

**步驟 3**：複製 Token

頁面會顯示類似以下的指令，**記下其中的 Token**（以 `A` 開頭的字串）：

```bash
./config.sh --url https://github.com/Terbinm/Sound_Multi_Analysis_System --token AXXXXXXXXXXXXXXXXXXXXXXXXXX
```

> ⚠️ **重要**：Token 具有時效性（約 1 小時），請在取得後儘快完成設定。

### 4.2 下載並設定 Runner

**步驟 1**：建立 Runner 目錄

```bash
# 在 WSL2 Ubuntu 中執行
sudo mkdir -p /opt/actions-runner
sudo chown $USER:$USER /opt/actions-runner
cd /opt/actions-runner
```

**步驟 2**：下載 Runner 套件

前往 https://github.com/actions/runner/releases 確認最新版本號（例如 `2.311.0`），然後執行：

```bash
# 下載（請將版本號替換為最新版）
RUNNER_VERSION="2.311.0"
curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz -L \
  https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

# 解壓縮
tar xzf actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
```

**步驟 3A**：執行設定(建議用3B的操作)

```bash
# 將 <YOUR_TOKEN> 替換為步驟 4.1 取得的 Token
./config.sh --url https://github.com/Terbinm/Sound_Multi_Analysis_System \
  --token <YOUR_TOKEN> \
  --name staging-runner \
  --labels self-hosted,staging,linux \
  --work _work \
  --runasservice
```

參數說明：

| 參數         | 值                            | 說明                                              |
| ------------ | ----------------------------- | ------------------------------------------------- |
| `--name`   | `staging-runner`            | Runner 顯示名稱，可自訂                           |
| `--labels` | `self-hosted,staging,linux` | **重要**：必須包含 `staging` 和 `linux` |
| `--work`   | `_work`                     | 工作目錄，預設即可                                |

**步驟 3B**：互動式設定（若未使用上述參數）

如果執行 `./config.sh` 時沒有帶參數，會進入互動模式：

```
Enter the name of the runner group to add this runner to: [按 Enter 使用 Default]
Enter the name of runner: [輸入 staging-runner]
Enter any additional labels: [輸入 staging,linux]
Enter name of work folder: [按 Enter 使用 _work]
```

### 4.3 安裝為系統服務

```bash
# 安裝服務（需要 sudo）
sudo ./svc.sh install

# 啟動服務
sudo ./svc.sh start

# 檢查服務狀態
sudo ./svc.sh status
```

預期輸出：

```
● actions.runner.Terbinm-Sound_Multi_Analysis_System.staging-runner.service
   Active: active (running)
```

[[此處建議加入截圖：svc.sh status 顯示 active (running)]]

### 4.4 驗證 Runner 上線

**步驟 1**：在 GitHub 確認 Runner 狀態

1. 回到 GitHub → Settings → Actions → Runners
2. 應該看到名為 `staging-runner` 的 Runner，狀態為 **Idle**（綠色圓點）

[[此處建議加入截圖：GitHub Runners 頁面顯示 staging-runner 為 Idle]]

**步驟 2**：確認標籤正確

Runner 應該顯示以下標籤：

- `self-hosted`
- `staging`
- `linux`

> ⚠️ **重要**：CD Pipeline 使用 `runs-on: [self-hosted, staging, linux]` 來選擇 Runner，標籤必須完全匹配。

---

## 5. 設定 GitHub Secrets（重要）

> ⚠️ **新增步驟**：CD Pipeline 現在會從 GitHub Secrets 自動產生 `.env` 檔案，不再需要在 Runner 上手動建立。

### 5.1 為什麼需要設定 GitHub Secrets

由於 `.env` 檔案包含敏感資訊（如資料庫密碼），通常不會提交到 Git。CD Pipeline 在部署時會從 GitHub Secrets 讀取環境變數，動態產生 `.env` 檔案。

**優點**：
- ✅ 敏感資訊加密儲存在 GitHub
- ✅ 不需要在 Runner 機器上手動維護 `.env` 檔案
- ✅ 可透過 GitHub UI 集中管理所有環境的設定

### 5.2 設定 Staging 環境的 Secrets

**步驟 1**：開啟 GitHub Settings

1. 前往專案頁面：https://github.com/Terbinm/Sound_Multi_Analysis_System
2. 點選 **Settings**（設定）
3. 左側選單選擇 **Secrets and variables** → **Actions**
4. 點選 **New repository secret**

**步驟 2**：新增通用 Secrets（2 個）

| Secret Name | Value 範例 | 說明 |
|-------------|------------|------|
| `ADMIN_PASSWORD` | `your_admin_password` | 管理員帳號密碼 |
| `ADMIN_EMAIL` | `admin@example.com` | 管理員帳號電子郵件 |

**步驟 3**：新增以下 11 個 Staging Secrets

依序新增（每次點選 **New repository secret**）：

#### MongoDB 設定（5 個）

| Secret Name                      | Value 範例      | 說明                       |
| -------------------------------- | --------------- | -------------------------- |
| `STAGING_MONGODB_HOST`         | `mongodb`     | MongoDB 主機名稱           |
| `STAGING_MONGODB_PORT`         | `55101`       | MongoDB 連接埠             |
| `STAGING_MONGODB_USERNAME`     | `web_ui`      | MongoDB 使用者名稱         |
| `STAGING_MONGODB_PASSWORD`     | `your_password` | **請替換為實際密碼**       |
| `STAGING_MONGODB_DATABASE`     | `web_db`      | MongoDB 資料庫名稱         |

#### RabbitMQ 設定（4 個）

| Secret Name                      | Value 範例      | 說明                   |
| -------------------------------- | --------------- | ---------------------- |
| `STAGING_RABBITMQ_HOST`        | `rabbitmq`    | RabbitMQ 主機名稱      |
| `STAGING_RABBITMQ_PORT`        | `55102`       | RabbitMQ 連接埠        |
| `STAGING_RABBITMQ_USERNAME`    | `admin`       | RabbitMQ 使用者名稱    |
| `STAGING_RABBITMQ_PASSWORD`    | `your_password` | **請替換為實際密碼**   |

#### State Management 設定（2 個）

| Secret Name                           | Value 範例                          | 說明                         |
| ------------------------------------- | ----------------------------------- | ---------------------------- |
| `STAGING_STATE_MANAGEMENT_PORT`     | `55103`                           | State Management 連接埠      |
| `STAGING_STATE_MANAGEMENT_URL`      | `http://state_management:55103` | State Management 完整 URL    |

**步驟 4**：驗證 Secrets 已新增

在 **Secrets and variables → Actions** 頁面，應該看到以下 13 個 secrets：

```
✅ ADMIN_PASSWORD（通用）
✅ ADMIN_EMAIL（通用）
✅ STAGING_MONGODB_HOST
✅ STAGING_MONGODB_PORT
✅ STAGING_MONGODB_USERNAME
✅ STAGING_MONGODB_PASSWORD
✅ STAGING_MONGODB_DATABASE
✅ STAGING_RABBITMQ_HOST
✅ STAGING_RABBITMQ_PORT
✅ STAGING_RABBITMQ_USERNAME
✅ STAGING_RABBITMQ_PASSWORD
✅ STAGING_STATE_MANAGEMENT_PORT
✅ STAGING_STATE_MANAGEMENT_URL
```

> 💡 **提示**：Secrets 一旦儲存後無法再檢視，只能更新。請確認輸入正確。

> 📖 **詳細說明**：完整的 GitHub Secrets 設定指南（包含 Production 環境）請參考 [`docs/cd/github_secrets_setup.md`](github_secrets_setup.md)

---

## 6. 專案 Clone 與環境設定

> ⚠️ **注意**：第 5 節設定 GitHub Secrets 後，本節的 `.env` 檔案建立步驟已不再需要。保留此節僅供參考。

### 6.1 設定 GitHub Personal Access Token（私有倉庫必要）

由於本專案為私有倉庫，需要先設定 Personal Access Token (PAT) 才能 clone。

**步驟 1**：在 GitHub 建立 Personal Access Token

1. 登入 GitHub，點選右上角頭像 → **Settings**
2. 左側選單最下方選擇 **Developer settings**
3. 選擇 **Personal access tokens** → **Tokens (classic)**
4. 點選 **Generate new token** → **Generate new token (classic)**

[[此處建議加入截圖：GitHub Personal Access Token 建立頁面]]

**步驟 2**：設定 Token 權限

填寫以下資訊：

- **Note**：填寫用途說明，例如 `staging-runner-access`
- **Expiration**：建議選擇 **No expiration**（或根據組織政策選擇期限）
- **Select scopes**：勾選以下權限
  - ✅ `repo`（完整存取私有倉庫）
  - ✅ `read:packages`（讀取 GHCR 映像）

點選 **Generate token** 產生 Token。

> ⚠️ **重要**：Token 僅顯示一次，請立即複製並妥善保管！

**步驟 3**：在 WSL2 中設定 Git 認證

```bash
# 設定 Git 使用認證快取
git config --global credential.helper store

# 設定您的 Git 使用者資訊
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### 6.2 Clone 專案

```bash
# 建立專案目錄
sudo mkdir -p /opt/repos
sudo chown $USER:$USER /opt/repos
cd /opt/repos

# Clone 專案（會提示輸入帳號密碼）
git clone https://github.com/Terbinm/Sound_Multi_Analysis_System.git
```

當提示輸入認證時：

```
Username for 'https://github.com': 輸入您的 GitHub 帳號
Password for 'https://your-username@github.com': 貼上您的 Personal Access Token
```

> 💡 **提示**：密碼欄位貼上的是 **Personal Access Token**，不是 GitHub 密碼。

```bash
# 進入專案目錄
cd Sound_Multi_Analysis_System
```

### 6.3 建立 .env 環境設定檔（選用）

> ⚠️ **重要變更**：如果您已在第 5 節設定 GitHub Secrets，則**不需要**執行本步驟。CD Pipeline 會自動產生 `.env` 檔案。

> 💡 **何時需要手動建立 .env**：僅在需要在 Runner 機器上手動執行 `docker compose` 測試時才需要。

**步驟 1**：從範例檔案複製

```bash
cp docs/cd/env.staging.sample .env
```

**步驟 2**：編輯 .env 檔案

```bash
nano .env
```

**步驟 3**：根據實際環境修改內容（使用與 GitHub Secrets 相同的值）

```bash
# Staging 環境範例 .env
# 說明：放置於 repo 根目錄，供 docker compose 讀取核心服務與分析服務連線設定。

# MongoDB 設定
MONGODB_HOST=mongodb
MONGODB_PORT=55101
MONGODB_USERNAME=web_ui
MONGODB_PASSWORD=<請設定您的密碼>
MONGODB_DATABASE=web_db

# RabbitMQ 設定
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=55102
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=<請設定您的密碼>

# State Management 設定
STATE_MANAGEMENT_PORT=55103
STATE_MANAGEMENT_URL=http://state_management:55103
```

> ⚠️ **重要**：
>
> - 請將 `<請設定您的密碼>` 替換為與 GitHub Secrets 相同的密碼
> - 容器間通訊使用服務名稱（如 `mongodb`、`rabbitmq`），不是 `localhost`

**步驟 4**：儲存並離開

- 按 `Ctrl + O` 儲存
- 按 `Enter` 確認檔名
- 按 `Ctrl + X` 離開

**步驟 5**：設定檔案權限

```bash
chmod 600 .env
```

### 6.4 驗證檔案結構

```bash
# 確認目錄結構
ls -la /opt/repos/Sound_Multi_Analysis_System/

# 應該看到：
# .env（如果手動建立）
# core/
# sub_system/
# docs/
# requirements.txt
# ...
```

```bash
# 確認 .env 內容（不顯示密碼）- 僅在手動建立時執行
grep -v PASSWORD .env
```

---

## 7. 首次部署測試

> ⚠️ **前提條件**：確保已完成第 5 節的 GitHub Secrets 設定。

### 6.1 觸發 CD Pipeline

**方法 A：透過 Commit Message 觸發（推薦）**

在您的開發機器上：

```bash
# 建立一個測試 commit
git commit --allow-empty -m "staging_v1.0.0.1_initial-deployment"
git push origin main
```

**方法 B：透過 GitHub Actions 手動觸發**

1. 前往 GitHub → Actions → CD Pipeline
2. 點選 **Run workflow**
3. 在 `manual_tag` 欄位輸入：`staging_v1.0.0.1_initial-deployment`
4. 點選 **Run workflow**

[[此處建議加入截圖：GitHub Actions Run workflow 對話框]]

### 6.2 監控部署進度

**步驟 1**：在 GitHub Actions 查看執行狀態

1. 前往 GitHub → Actions
2. 點選最新的 workflow run
3. 觀察各 job 的執行狀態：
   - `parse_version`：解析版本號 ✅
   - `build_and_push`：建置並推送映像到 GHCR ✅
   - `deploy_staging`：部署到 Staging 環境 ✅

[[此處建議加入截圖：GitHub Actions workflow 執行成功畫面]]

**步驟 2**：在 Runner 主機查看容器狀態

```bash
# 在 WSL2 中執行
docker ps

# 預期看到以下容器：
# - mongodb
# - rabbitmq
# - state_management（或 sound-state-management）
# - analysis_service（或 sound-analysis-service）
```

### 6.3 健康檢查

**步驟 1**：檢查 State Management 服務

```bash
curl -f http://localhost:55103/health

# 預期輸出：
# {"status": "healthy", ...}
```

**步驟 2**：檢查容器日誌

```bash
# 查看 State Management 日誌
docker logs state_management --tail 50

# 查看 Analysis Service 日誌
docker logs analysis_service --tail 50
```

**步驟 3**：使用 Docker Compose 檢查整體狀態

```bash
cd /opt/repos/Sound_Multi_Analysis_System
docker compose -f core/docker-compose.yml ps
```

---

## 8. 常見問題排查

### 8.1 部署相關問題

#### 問題：部署時顯示 `env file .env not found`

**錯誤訊息範例**：
```
env file /path/to/.env not found: stat /path/to/.env: no such file or directory
Error: Process completed with exit code 1
```

**原因**：GitHub Secrets 未正確設定，或部署 workflow 未包含建立 `.env` 檔案的步驟。

**解決方案**：

**步驟 1**：確認 GitHub Secrets 已設定

1. 前往 GitHub → Settings → Secrets and variables → Actions
2. 確認以下 11 個 Staging secrets 都存在：
   ```
   STAGING_MONGODB_HOST
   STAGING_MONGODB_PORT
   STAGING_MONGODB_USERNAME
   STAGING_MONGODB_PASSWORD
   STAGING_MONGODB_DATABASE
   STAGING_RABBITMQ_HOST
   STAGING_RABBITMQ_PORT
   STAGING_RABBITMQ_USERNAME
   STAGING_RABBITMQ_PASSWORD
   STAGING_STATE_MANAGEMENT_PORT
   STAGING_STATE_MANAGEMENT_URL
   ```

**步驟 2**：檢查 CD workflow 是否包含建立 `.env` 的步驟

查看 `.github/workflows/cd.yml` 中的 `deploy_staging` job，應該包含：

```yaml
- name: 建立 .env 檔案
  shell: bash
  run: |
    cat <<'EOF' > .env
    # MongoDB 設定
    MONGODB_HOST=${{ secrets.STAGING_MONGODB_HOST }}
    ...
    EOF
```

**步驟 3**：重新觸發部署

```bash
git commit --allow-empty -m "staging_v0.0.5.7_fix-env-config"
git push origin main
```

> 📖 **參考文件**：詳細的 GitHub Secrets 設定指南請參考 [`docs/cd/github_secrets_setup.md`](github_secrets_setup.md)

### 8.2 WSL2 相關問題

#### 問題：`wsl --install` 失敗

**可能原因**：BIOS 未啟用虛擬化技術

**解決方案**：

1. 重新啟動電腦，進入 BIOS
2. 找到 Virtualization Technology（VT-x / AMD-V）選項
3. 設定為 Enabled
4. 儲存並重新啟動

#### 問題：WSL 啟動後立即關閉

**可能原因**：.wslconfig 設定錯誤或資源不足

**解決方案**：

```powershell
# 刪除設定檔重新開始
Remove-Item "$env:USERPROFILE\.wslconfig"
wsl --shutdown
wsl
```

### 8.3 Docker 相關問題

#### 問題：`docker: permission denied`

**可能原因**：使用者未加入 docker 群組，或未重新登入

**解決方案**：

```bash
# 確認使用者已在 docker 群組
groups $USER

# 如果沒有 docker，重新加入
sudo usermod -aG docker $USER

# 重新登入 WSL
exit
# 然後在 PowerShell 執行：wsl
```

#### 問題：Docker 服務未啟動

**解決方案**：

```bash
# 手動啟動
sudo service docker start

# 檢查狀態
sudo service docker status
```

### 8.4 GitHub Runner 相關問題

#### 問題：Runner 顯示 Offline

**可能原因 1**：服務未執行

**解決方案**：

```bash
cd /opt/actions-runner
sudo ./svc.sh status
sudo ./svc.sh start
```

**可能原因 2**：Token 過期

**解決方案**：

```bash
# 移除舊設定
cd /opt/actions-runner
sudo ./svc.sh stop
sudo ./svc.sh uninstall
./config.sh remove --token <REMOVE_TOKEN>

# 重新取得 Token 並設定（參考 4.1-4.3 節）
```

#### 問題：Runner 標籤不正確

**解決方案**：

1. 前往 GitHub → Settings → Actions → Runners
2. 點選該 Runner
3. 點選 **Edit** 修改標籤
4. 確保包含：`self-hosted`、`staging`、`linux`

### 8.5 Git 與認證問題

#### 問題：Clone 時提示 `Authentication failed`

**可能原因**：Personal Access Token 過期或權限不足

**解決方案**：

```bash
# 清除舊的認證
rm ~/.git-credentials

# 重新設定
git config --global credential.helper store

# 重新 clone
cd /opt/repos
rm -rf Sound_Multi_Analysis_System
git clone https://github.com/Terbinm/Sound_Multi_Analysis_System.git
# 輸入正確的 Token
```

#### 問題：後續 `git pull` 無法自動認證

**解決方案**：

```bash
# 確認認證快取已啟用
git config --global credential.helper

# 應輸出：store

# 檢查認證檔案
cat ~/.git-credentials

# 應包含類似內容：
# https://username:ghp_xxxxxxxxxxxx@github.com
```

### 8.6 映像拉取問題

#### 問題：無法從 GHCR 拉取映像

**錯誤訊息**：`unauthorized: authentication required`

**解決方案**：

```bash
# 在 WSL2 中手動登入 GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_ACTOR --password-stdin
```

> 💡 **注意**：正常情況下，CD Pipeline 會自動處理認證。如果持續失敗，請確認專案的 Workflow 權限設定。

#### 問題：Docker 登入時提示 `docker-credential-desktop.exe` 找不到

**錯誤訊息**：
```
Error: error saving credentials: error storing credentials - err: exec: "docker-credential-desktop.exe": executable file not found in $PATH
```

**原因**：WSL2 內的 Docker CLI 嘗試使用 Windows Docker Desktop 的憑證管理器，但路徑不正確。

**解決方案**：

```bash
# 方法 1：修改 Docker 配置使用檔案儲存憑證（推薦）
mkdir -p ~/.docker
cat > ~/.docker/config.json <<'EOF'
{
  "credsStore": ""
}
EOF

# 重新啟動 GitHub Runner 服務
cd /opt/actions-runner
sudo ./svc.sh restart

# 驗證設定
cat ~/.docker/config.json
```

**方法 2**（如果方法 1 不生效）：

```bash
# 為 Runner 服務設定環境變數
cd /opt/actions-runner
sudo ./svc.sh stop

# 建立環境變數設定檔
echo "DOCKER_CONFIG=/home/$USER/.docker" | sudo tee /opt/actions-runner/.env

# 重新啟動服務
sudo ./svc.sh start
```

**驗證修復**：

```bash
# 手動測試 Docker 登入（替換為實際的 GitHub Token）
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u Terbinm --password-stdin

# 應顯示：Login Succeeded
```

### 8.7 部署後服務異常

#### 問題：容器不斷重啟

**診斷步驟**：

```bash
# 查看容器狀態
docker ps -a

# 查看日誌
docker logs <container_name>

# 常見原因：
# - .env 設定錯誤
# - 依賴服務（MongoDB/RabbitMQ）未啟動
# - Port 被佔用
```

#### 問題：健康檢查失敗

**解決方案**：

```bash
# 檢查服務是否在監聽
netstat -tlnp | grep 55103

# 檢查防火牆（如果有）
sudo ufw status
```

---

## 9. 附錄：路徑總覽

### 8.1 完整路徑清單

| 項目            | 路徑                                                               | 說明                      |
| --------------- | ------------------------------------------------------------------ | ------------------------- |
| WSL 設定        | `C:\Users\<用戶名>\.wslconfig`                                   | WSL2 資源限制設定         |
| WSL 啟動腳本    | `/etc/wsl.conf`                                                  | WSL 啟動時執行的設定      |
| Docker 啟動腳本 | `/etc/wsl.d/docker-start.sh`                                     | 自動啟動 Docker 服務      |
| GitHub Runner   | `/opt/actions-runner/`                                           | Runner 程式與服務         |
| Runner 工作目錄 | `/opt/actions-runner/_work/`                                     | Pipeline 執行時的暫存目錄 |
| 專案程式碼      | `/opt/repos/Sound_Multi_Analysis_System/`                        | Git Clone 的專案          |
| 環境設定        | `/opt/repos/Sound_Multi_Analysis_System/.env`                    | Docker Compose 環境變數   |
| Docker Compose  | `/opt/repos/Sound_Multi_Analysis_System/core/docker-compose.yml` | 服務編排定義              |

### 9.2 重要指令速查

```bash
# === WSL 管理 ===
wsl --shutdown                    # 關閉 WSL
wsl                               # 進入 WSL
wsl -l -v                         # 列出已安裝的發行版

# === Docker 管理 ===
sudo service docker start         # 啟動 Docker
sudo service docker status        # 檢查 Docker 狀態
docker ps                         # 列出執行中的容器
docker logs <container>           # 查看容器日誌

# === GitHub Runner 管理 ===
cd /opt/actions-runner
sudo ./svc.sh status              # 檢查 Runner 狀態
sudo ./svc.sh start               # 啟動 Runner
sudo ./svc.sh stop                # 停止 Runner
sudo ./svc.sh uninstall           # 移除服務

# === 專案管理 ===
cd /opt/repos/Sound_Multi_Analysis_System
git pull                          # 更新程式碼
docker compose -f core/docker-compose.yml ps    # 檢查服務狀態
docker compose -f core/docker-compose.yml logs  # 查看所有服務日誌
```

### 9.3 版本觸發格式

CD Pipeline 透過 commit message 觸發，格式為：

```
{環境}_v{主版本}.{次版本}.{修訂版}.{流水號}_{說明}
```

範例：

- `staging_v1.0.0.1_initial-setup` → 部署到 Staging
- `staging_v1.0.1.0_fix-login-bug` → 部署修正版到 Staging

> 💡 **注意**：只有 `staging_v*` 開頭的 commit message 才會觸發 Staging 部署。

---

## 📋 檢查清單

完成本指南後，請確認以下項目：

- [ ] WSL2 已安裝且 Ubuntu 可正常啟動
- [ ] `.wslconfig` 已設定資源限制
- [ ] Docker Desktop 已安裝且可執行 `docker run hello-world`
- [ ] Docker 服務會在 WSL 啟動時自動啟動
- [ ] GitHub Runner 已安裝且狀態為 Idle（綠色）
- [ ] Runner 標籤包含 `self-hosted`、`staging`、`linux`
- [ ] **GitHub Secrets 已設定（2 個通用 + 11 個 STAGING_* secrets）** ⭐ 重要
- [ ] 專案已 Clone 到 `/opt/repos/Sound_Multi_Analysis_System`
- [ ] 首次部署測試成功（不再出現 `.env not found` 錯誤）
- [ ] 健康檢查 `curl http://localhost:55103/health` 回傳正常

---

> 📝 **文件維護**：如有問題或建議，請聯繫專案維護者或提交 Issue。
> 📖 **相關文件**：[GitHub Secrets 設定指南](github_secrets_setup.md)
