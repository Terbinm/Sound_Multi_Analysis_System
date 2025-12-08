**所有AI必須使用繁體中文回答與思考！**  
**所有AI設計的log任何等級資訊必須使用繁體中文！**  
**所有AI設計的註解資訊必須使用繁體中文！**  
**應該在所有.py檔案的最開頭摘要程式功能與内容**  
**所有文檔都在./docs裡面，請以cpc_integrated_guide.html為主**


## 3. 版本標籤規則（tag）
- `dev_v{主}.{中}.{次}.{流水}_{說明}`：**僅 CI 不部署**。
- `staging_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **staging** runner 群組並執行基本測試。
- `server_production_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **server_production** runner 群組。
- `edge_production_v{主}.{中}.{次}.{流水}_{說明}`：部署到 **edge_production** runner 群組（workflow 同時相容 `edge_productio_v...`）。
- 流水號後的 `{說明}` 僅用於人類辨識，映像 tag 只使用版本號避免 Docker tag 非法字元。
  - 範例：`staging_v1.4.2.7_rabbitmq-tuning`、`server_production_v2.0.0.3_hotfix-a`.
