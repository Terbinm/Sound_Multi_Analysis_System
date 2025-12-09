**所有AI必須使用繁體中文回答與思考！**  
**所有AI設計的log任何等級資訊必須使用繁體中文！**  
**所有AI設計的註解資訊必須使用繁體中文！**  
**應該在所有.py檔案的最開頭摘要程式功能與内容**  
**所有文檔都在./docs裡面，請以cpc_integrated_guide.html為主**


## 3. 版本標籤規則（Commit Message）
CD 流程以 **commit message** 作為觸發依據，格式如下：

- `dev_v{主}.{中}.{次}.{流水}_{說明}`：**僅 CI 不部署**。
- `staging_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **staging** runner 群組並執行基本測試。
- `server_production_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **server_production** runner 群組。
- `edge_production_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **edge_production** runner 群組（workflow 同時相容 `edge_productio_v...`）。
- 流水號後的 `{說明}` 僅用於人類辨識，映像 tag 只使用版本號避免 Docker tag 非法字元。
  - 範例：`staging_v1.4.2.7_rabbitmq-tuning`、`server_production_v2.0.0.3_hotfix-a`.

### 使用方式
```bash
git commit -m "staging_v0.0.4.6_add_env"
git push origin main
```

> **注意**：只有 commit message 第一行符合版本格式時才會觸發 CD，一般 commit 不會觸發部署。


STAGING_MONGODB_HOST = mongodb
STAGING_MONGODB_PORT = 55101
STAGING_MONGODB_USERNAME = web_ui
STAGING_MONGODB_PASSWORD = <STAGING_MONGODB_PASSWORD>
STAGING_MONGODB_DATABASE = web_db

STAGING_RABBITMQ_HOST = rabbitmq
STAGING_RABBITMQ_PORT = 55102
STAGING_RABBITMQ_USERNAME = admin
STAGING_RABBITMQ_PASSWORD = STAGING_RABBITMQ_PASSWORD>

STAGING_STATE_MANAGEMENT_PORT = 55103
STAGING_STATE_MANAGEMENT_URL = http://state_management:55103