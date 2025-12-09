# GitHub Secrets 設定指南

> **最後更新**：2025-12
> **適用對象**：專案管理員
> **預計耗時**：約 10-15 分鐘

---

## 目錄

1. [為什麼需要設定 GitHub Secrets](#1-為什麼需要設定-github-secrets)
2. [設定 Staging 環境的 Secrets](#2-設定-staging-環境的-secrets)
3. [設定 Production 環境的 Secrets](#3-設定-production-環境的-secrets)
4. [驗證設定](#4-驗證設定)
5. [安全最佳實踐](#5-安全最佳實踐)

---

## 1. 為什麼需要設定 GitHub Secrets

### 問題背景

CD Pipeline 在部署時會從 GitHub Clone 專案程式碼，但 `.env` 檔案因為包含敏感資訊（如資料庫密碼），通常會加入 `.gitignore` 不上傳到 Git。

這導致 GitHub Runner 執行部署時會遇到錯誤：
```
env file /path/to/.env not found: no such file or directory
```

### 解決方案

將環境變數儲存在 **GitHub Secrets** 中，CD Pipeline 會在部署前自動產生 `.env` 檔案。

**優點**：
- ✅ 敏感資訊加密儲存在 GitHub
- ✅ 不需要在 Runner 機器上手動維護 `.env` 檔案
- ✅ 可透過 GitHub UI 集中管理所有環境的設定
- ✅ 符合 GitOps 最佳實踐

---

## 2. 設定 Staging 環境的 Secrets

### 步驟 1：開啟 GitHub Settings

1. 前往專案頁面：https://github.com/Terbinm/Sound_Multi_Analysis_System
2. 點選 **Settings**（設定）
3. 左側選單選擇 **Secrets and variables** → **Actions**
4. 點選 **New repository secret**

![GitHub Secrets 設定頁面](https://docs.github.com/assets/cb-28008/images/help/settings/actions-secrets-new-secret-button.png)

### 步驟 2：新增 Staging 的 Secrets

依序新增以下 11 個 secrets（點選 **New repository secret** 後逐一新增）：

#### MongoDB 設定（5 個）

| Secret Name                      | Value 範例      | 說明                       |
| -------------------------------- | --------------- | -------------------------- |
| `STAGING_MONGODB_HOST`         | `mongodb`     | MongoDB 主機名稱           |
| `STAGING_MONGODB_PORT`         | `55101`       | MongoDB 連接埠             |
| `STAGING_MONGODB_USERNAME`     | `web_ui`      | MongoDB 使用者名稱         |
| `STAGING_MONGODB_PASSWORD`     | `your_password` | MongoDB 密碼（請替換）     |
| `STAGING_MONGODB_DATABASE`     | `web_db`      | MongoDB 資料庫名稱         |

#### RabbitMQ 設定（4 個）

| Secret Name                      | Value 範例      | 說明                   |
| -------------------------------- | --------------- | ---------------------- |
| `STAGING_RABBITMQ_HOST`        | `rabbitmq`    | RabbitMQ 主機名稱      |
| `STAGING_RABBITMQ_PORT`        | `55102`       | RabbitMQ 連接埠        |
| `STAGING_RABBITMQ_USERNAME`    | `admin`       | RabbitMQ 使用者名稱    |
| `STAGING_RABBITMQ_PASSWORD`    | `your_password` | RabbitMQ 密碼（請替換） |

#### State Management 設定（2 個）

| Secret Name                           | Value 範例                                 | 說明                         |
| ------------------------------------- | ------------------------------------------ | ---------------------------- |
| `STAGING_STATE_MANAGEMENT_PORT`     | `55103`                                  | State Management 連接埠      |
| `STAGING_STATE_MANAGEMENT_URL`      | `http://state_management:55103`        | State Management 完整 URL    |

### 步驟 3：驗證已新增的 Secrets

在 **Secrets and variables → Actions** 頁面，應該看到以下 11 個 secrets：

```
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

> 💡 **提示**：Secrets 一旦儲存後，無法再檢視內容，只能更新。請確認輸入正確。

---

## 3. 設定 Production 環境的 Secrets

### 3.1 Server Production（伺服器生產環境）

依照相同步驟，新增以下 secrets（前綴改為 `PRODUCTION_`）：

#### MongoDB 設定

| Secret Name                          | Value 範例      |
| ------------------------------------ | --------------- |
| `PRODUCTION_MONGODB_HOST`          | `mongodb`     |
| `PRODUCTION_MONGODB_PORT`          | `55101`       |
| `PRODUCTION_MONGODB_USERNAME`      | `web_ui`      |
| `PRODUCTION_MONGODB_PASSWORD`      | `your_password` |
| `PRODUCTION_MONGODB_DATABASE`      | `web_db`      |

#### RabbitMQ 設定

| Secret Name                          | Value 範例      |
| ------------------------------------ | --------------- |
| `PRODUCTION_RABBITMQ_HOST`         | `rabbitmq`    |
| `PRODUCTION_RABBITMQ_PORT`         | `55102`       |
| `PRODUCTION_RABBITMQ_USERNAME`     | `admin`       |
| `PRODUCTION_RABBITMQ_PASSWORD`     | `your_password` |

#### State Management 設定

| Secret Name                               | Value 範例                          |
| ----------------------------------------- | ----------------------------------- |
| `PRODUCTION_STATE_MANAGEMENT_PORT`      | `55103`                           |
| `PRODUCTION_STATE_MANAGEMENT_URL`       | `http://state_management:55103` |

### 3.2 Edge Production（邊緣設備生產環境）

新增以下 secrets（前綴改為 `EDGE_`）：

#### MongoDB 設定

| Secret Name                     | Value 範例      |
| ------------------------------- | --------------- |
| `EDGE_MONGODB_HOST`           | `mongodb`     |
| `EDGE_MONGODB_PORT`           | `55101`       |
| `EDGE_MONGODB_USERNAME`       | `web_ui`      |
| `EDGE_MONGODB_PASSWORD`       | `your_password` |
| `EDGE_MONGODB_DATABASE`       | `web_db`      |

#### RabbitMQ 設定

| Secret Name                     | Value 範例      |
| ------------------------------- | --------------- |
| `EDGE_RABBITMQ_HOST`          | `rabbitmq`    |
| `EDGE_RABBITMQ_PORT`          | `55102`       |
| `EDGE_RABBITMQ_USERNAME`      | `admin`       |
| `EDGE_RABBITMQ_PASSWORD`      | `your_password` |

#### State Management 設定

| Secret Name                          | Value 範例                          |
| ------------------------------------ | ----------------------------------- |
| `EDGE_STATE_MANAGEMENT_PORT`       | `55103`                           |
| `EDGE_STATE_MANAGEMENT_URL`        | `http://state_management:55103` |

---

## 4. 驗證設定

### 方法 1：檢視 Secrets 列表

在 GitHub → Settings → Secrets and variables → Actions，確認所有 secrets 都已新增。

**Staging 環境應有 11 個 secrets：**
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

**Server Production 環境應有 11 個 secrets：**
```
PRODUCTION_MONGODB_HOST
PRODUCTION_MONGODB_PORT
...（以此類推）
```

**Edge Production 環境應有 11 個 secrets：**
```
EDGE_MONGODB_HOST
EDGE_MONGODB_PORT
...（以此類推）
```

### 方法 2：觸發部署測試

設定完成後，執行一次部署測試：

```bash
# 在本地開發機器執行
git commit --allow-empty -m "staging_v0.0.5.7_test-secrets-config"
git push origin main
```

前往 GitHub → Actions，觀察 workflow 執行：

1. **解析版本標籤** → ✅ 應該成功
2. **建置並推送映像** → ✅ 應該成功
3. **部署到 Staging** → ✅ 應該成功（不再出現 `.env not found` 錯誤）

### 方法 3：檢查 Runner 上的 .env 檔案

部署成功後，在 Staging Runner 機器上檢查：

```bash
# 在 WSL2 中執行
cd /home/user/staging_repo/actions-runner/_work/Sound_Multi_Analysis_System/Sound_Multi_Analysis_System

# 檢查 .env 檔案是否存在
ls -la .env

# 查看內容（不顯示密碼）
grep -v PASSWORD .env
```

預期輸出類似：
```
MONGODB_HOST=mongodb
MONGODB_PORT=55101
MONGODB_USERNAME=web_ui
...
```

---

## 5. 安全最佳實踐

### 5.1 密碼管理

- ✅ **使用強密碼**：至少 16 字元，包含大小寫字母、數字、特殊符號
- ✅ **不同環境使用不同密碼**：Staging 和 Production 的密碼應該不同
- ✅ **定期更換密碼**：建議每 3-6 個月更換一次

### 5.2 存取控制

- ✅ **限制 GitHub 存取權限**：只有管理員能修改 Secrets
- ✅ **啟用 2FA**：GitHub 帳號應啟用雙因素驗證
- ✅ **審核 Workflow 變更**：任何修改 `.github/workflows/` 的 PR 都應仔細審查

### 5.3 監控與稽核

- ✅ **定期檢查 Secrets 使用狀況**：前往 Settings → Security → Actions
- ✅ **監控 Actions 執行記錄**：異常的部署應立即調查
- ✅ **備份重要設定**：將 secrets 列表（不含值）記錄在安全的地方

### 5.4 如果懷疑 Secrets 洩漏

**立即執行以下步驟：**

1. **撤銷所有受影響的密碼**（MongoDB、RabbitMQ 等）
2. **更新 GitHub Secrets**
3. **重新部署所有環境**
4. **檢查 Actions 執行記錄**，確認是否有未授權的存取
5. **檢視 GitHub Audit Log**（Settings → Security → Audit log）

---

## 6. 常見問題

### Q1：忘記某個 Secret 的值怎麼辦？

**A：** GitHub Secrets 無法檢視，只能更新。建議：
1. 前往 Runner 機器檢查實際使用的值（如果有）
2. 或直接重新產生新密碼並更新 Secret

### Q2：可以在多個環境共用同一個 Secret 嗎？

**A：** 技術上可以，但**不建議**。不同環境應使用不同的密碼以降低風險。

### Q3：如何批次更新 Secrets？

**A：** GitHub UI 目前不支援批次更新，需逐一更新。或使用 GitHub CLI：

```bash
# 使用 GitHub CLI 批次更新（需先安裝 gh）
gh secret set STAGING_MONGODB_PASSWORD --body "new_password"
```

### Q4：Secrets 有大小限制嗎？

**A：** 單個 Secret 最大 64KB，總數無上限。環境變數值通常不會超過此限制。

---

## 7. 附錄：快速設定腳本（選用）

如果您熟悉 GitHub CLI，可以使用以下腳本快速設定 Staging 環境的 secrets：

```bash
#!/bin/bash
# 檔案：setup_staging_secrets.sh
# 用途：批次設定 Staging 環境的 GitHub Secrets

# 請先修改以下變數為實際值
MONGODB_PASSWORD="your_mongodb_password"
RABBITMQ_PASSWORD="your_rabbitmq_password"

# 執行批次設定（需先安裝並登入 gh CLI）
gh secret set STAGING_MONGODB_HOST --body "mongodb"
gh secret set STAGING_MONGODB_PORT --body "55101"
gh secret set STAGING_MONGODB_USERNAME --body "web_ui"
gh secret set STAGING_MONGODB_PASSWORD --body "$MONGODB_PASSWORD"
gh secret set STAGING_MONGODB_DATABASE --body "web_db"

gh secret set STAGING_RABBITMQ_HOST --body "rabbitmq"
gh secret set STAGING_RABBITMQ_PORT --body "55102"
gh secret set STAGING_RABBITMQ_USERNAME --body "admin"
gh secret set STAGING_RABBITMQ_PASSWORD --body "$RABBITMQ_PASSWORD"

gh secret set STAGING_STATE_MANAGEMENT_PORT --body "55103"
gh secret set STAGING_STATE_MANAGEMENT_URL --body "http://state_management:55103"

echo "✅ Staging Secrets 設定完成"
```

**使用方式：**

```bash
# 安裝 GitHub CLI（如果尚未安裝）
# Ubuntu/Debian:
sudo apt install gh

# Windows (使用 winget):
winget install GitHub.cli

# 登入 GitHub
gh auth login

# 執行腳本
chmod +x setup_staging_secrets.sh
./setup_staging_secrets.sh
```

---

> 📝 **文件維護**：如有問題或建議，請聯繫專案維護者。
> 🔒 **安全提醒**：絕不要將實際的密碼提交到 Git 或任何公開位置。
