# 快速修復：部署時 .env 檔案找不到

> **錯誤訊息**：`env file .env not found: stat /path/to/.env: no such file or directory`
> **發生時機**：GitHub Actions CD Pipeline 部署到 Staging/Production 時
> **修復時間**：約 5-10 分鐘

---

## 問題原因

`.env` 檔案包含敏感資訊（如資料庫密碼），通常不會提交到 Git。當 GitHub Runner 從 GitHub Clone 專案時，不會包含這個檔案，導致 Docker Compose 啟動時找不到環境變數。

---

## 解決方案：設定 GitHub Secrets

### 步驟 1：前往 GitHub Settings

1. 開啟專案頁面：https://github.com/Terbinm/Sound_Multi_Analysis_System
2. 點選 **Settings** → **Secrets and variables** → **Actions**
3. 點選 **New repository secret**

### 步驟 2：新增以下 11 個 Secrets

**對於 Staging 環境**，依序新增：

| Secret Name（必須精確） | 範例值 | 說明 |
|-------------------------|--------|------|
| `STAGING_MONGODB_HOST` | `mongodb` | MongoDB 容器名稱 |
| `STAGING_MONGODB_PORT` | `55101` | MongoDB 連接埠 |
| `STAGING_MONGODB_USERNAME` | `web_ui` | MongoDB 使用者 |
| `STAGING_MONGODB_PASSWORD` | `your_password` | **請替換為實際密碼** |
| `STAGING_MONGODB_DATABASE` | `web_db` | MongoDB 資料庫名稱 |
| `STAGING_RABBITMQ_HOST` | `rabbitmq` | RabbitMQ 容器名稱 |
| `STAGING_RABBITMQ_PORT` | `55102` | RabbitMQ 連接埠 |
| `STAGING_RABBITMQ_USERNAME` | `admin` | RabbitMQ 使用者 |
| `STAGING_RABBITMQ_PASSWORD` | `your_password` | **請替換為實際密碼** |
| `STAGING_STATE_MANAGEMENT_PORT` | `55103` | State Management 連接埠 |
| `STAGING_STATE_MANAGEMENT_URL` | `http://state_management:55103` | State Management URL |

> 💡 **提示**：點選 **New repository secret** 後，在 **Name** 欄位填寫 secret 名稱（例如 `STAGING_MONGODB_HOST`），在 **Secret** 欄位填寫對應的值，然後點選 **Add secret**。

### 步驟 3：驗證 Secrets 已新增

回到 **Secrets and variables → Actions** 頁面，確認顯示：

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

### 步驟 4：重新觸發部署

在本地開發機器執行：

```bash
git commit --allow-empty -m "staging_v0.0.5.7_fix-env-config"
git push origin main
```

前往 GitHub → Actions，觀察部署流程應該會成功完成，不再出現 `.env not found` 錯誤。

---

## Production 環境設定

如果需要部署到 **Server Production** 或 **Edge Production**，請使用對應的前綴：

- **Server Production**：`PRODUCTION_*`（例如 `PRODUCTION_MONGODB_HOST`）
- **Edge Production**：`EDGE_*`（例如 `EDGE_MONGODB_HOST`）

其他步驟相同，詳細說明請參考 [`github_secrets_setup.md`](github_secrets_setup.md)。

---

## 常見問題

### Q1：我已經在 Runner 機器上建立了 .env 檔案，為什麼還是不行？

**A：** GitHub Runner 每次執行時都會在**臨時工作目錄**（`_work/`）重新 Clone 專案，不會使用您手動放置的檔案。必須透過 GitHub Secrets 讓 CD Pipeline 自動產生。

### Q2：忘記某個 Secret 的值怎麼辦？

**A：** GitHub Secrets 無法檢視，只能更新。您可以：
1. 查看 Runner 機器上是否有手動建立的 `.env` 檔案參考
2. 或重新產生新密碼並同時更新 Secret 和實際環境

### Q3：可以多個環境共用同一個 Secret 嗎？

**A：** 技術上可以，但**強烈不建議**。不同環境（Staging/Production）應使用不同的密碼以降低安全風險。

---

## 相關文件

- 📖 [完整的 GitHub Secrets 設定指南](github_secrets_setup.md)
- 📖 [Staging 環境 Onboarding 完整指南](staging_onboarding.md)
- 📖 [CD Pipeline 使用說明](README.md)

---

> ✅ **修復確認**：完成上述步驟後，下次部署應該會在日誌中看到「✅ .env 檔案已建立」訊息，並且不再出現錯誤。
