# CD 導覽與文件索引

本資料夾彙整持續部署（CD）相關指引，涵蓋版本標籤規則、環境準備、首次串接與驗證流程。

## 版本與環境對照
- `dev_v*`：僅 CI，不部署。
- `staging_v*`：部署到 `[self-hosted, staging]` runner，並在容器內執行 `python -m compileall` + `/health` 檢查。
- `server_production_v*`：部署到 `[self-hosted, server_production]` runner。
- `edge_production_v*` / `edge_productio_v*`：部署到 `[self-hosted, edge_production]` runner（僅 Analysis Service）。

## 主要內容
- `staging_onboarding.md`：Staging 首次接入、.env 建立、流程測試。
- `production_onboarding.md`：Server Production 與 Edge Production 首次接入與驗證。
- 範例環境檔：`env.staging.sample`、`env.server_production.sample`、`env.edge_production.sample`（放在 repo 根目錄後可直接套用）。
- 參考：根目錄 `CD.md` 內有整體流程與設計原則。
