# 快速參考卡

## 📦 檔案清單

```
您需要將以下 5 個檔案放到專案根目錄:

✅ train_rf_model.py              (30 KB) - 訓練腳本
✅ evaluate_model.py              (15 KB) - 評估工具
✅ step3_classifier_updated.py   (12 KB) - 新分類器
✅ quick_start.py                 (18 KB) - 快速啟動
✅ RF_MODEL_GUIDE.md              (50 KB) - 完整指南
✅ README.md                      (25 KB) - 套件說明
✅ QUICK_REFERENCE.md             (本檔案) - 快速參考
```

---

## ⚡ 快速開始(3 步驟)

### 步驟 1: 安裝依賴

```bash
pip install scikit-learn matplotlib seaborn --break-system-packages
```

### 步驟 2: 確保有訓練資料

```bash
# 檢查 MongoDB 中的資料數量
python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin')
db = client['web_db']
count = db.recordings.count_documents({
    'current_step': 4,
    'analysis_status': 'completed',
    'info_features.label': {'$in': ['normal', 'abnormal']}
})
print(f'可用訓練資料: {count} 筆')
client.close()
"
```

**最少需要 50 筆,建議 200+ 筆**

如果資料不足:
```bash
cd a_sub_system/batch_upload
python batch_upload.py
```

### 步驟 3: 一鍵訓練與部署

```bash
python quick_start.py
```

按照提示完成即可! 🎉

---

## 📝 手動執行步驟

如果不想使用 `quick_start.py`,可以手動執行:

```bash
# 1. 訓練模型
python train_regrassion_model.py

# 2. 評估模型
python regrassion_evaluate_model.py
# 選擇選項 1

# 3. 部署模型
#    a. 備份原始分類器
cp a_sub_system/analysis_service/processors/step3_classifier.py \
   a_sub_system/analysis_service/processors/step3_classifier_backup.py

#    b. 替換分類器
cp step3_classifier_updated.py \
   a_sub_system/analysis_service/processors/step3_classifier.py

#    c. 更新配置
nano a_sub_system/analysis_service/config.py
# 修改:
#   'method': 'rf_model'
#   'model_path': '/絕對路徑/to/models'

# 4. 重啟分析服務
cd a_sub_system/analysis_service
python main.py
```

---

## 🎯 輸出檔案位置

```
專案根目錄/
├── models/                            # 訓練好的模型
│   ├── rf_classifier.pkl              # 模型檔案
│   ├── feature_scaler.pkl             # 標準化器
│   └── model_metadata.json            # 元資料
│
├── training_reports/                  # 訓練報告
│   ├── confusion_matrix.png           # 混淆矩陣圖
│   ├── feature_importance.png         # 特徵重要性
│   ├── roc_curve.png                  # ROC 曲線
│   └── evaluation_report.json         # 評估報告
│
└── evaluation_results/                # 評估結果
    ├── cross_dataset_evaluation.json  # 跨資料集評估
    ├── confusion_matrix_eval.png      # 混淆矩陣
    └── roc_curve_eval.png             # ROC 曲線
```

---

## 🔧 常用命令

### 檢查資料

```bash
# 檢查訓練資料數量
python -c "from pymongo import MongoClient; c=MongoClient('mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin'); print(f'資料數量: {c.web_db.recordings.count_documents({\"current_step\":4,\"analysis_status\":\"completed\",\"info_features.label\":{\"$in\":[\"normal\",\"abnormal\"]}})} 筆'); c.close()"
```

### 訓練模型

```bash
# 完整訓練
python train_regrassion_model.py

# 查看訓練日誌
tail -f batch_upload.log
```

### 評估模型

```bash
# 跨資料集評估
python regrassion_evaluate_model.py
# 選擇選項 1

# 單一記錄預測
python regrassion_evaluate_model.py
# 選擇選項 2
# 輸入 AnalyzeUUID
```

### 部署模型

```bash
# 使用快速腳本
python quick_start.py

# 或手動部署(見上方"手動執行步驟")
```

### 查看結果

```bash
# 查看模型元資料
cat models/model_metadata.json

# 查看訓練報告
cat training_reports/evaluation_report.json | python -m json.tool

# 查看圖表(Windows)
start training_reports/confusion_matrix.png

# 查看圖表(Linux)
xdg-open training_reports/confusion_matrix.png
```

---

## 📊 效能標準

| 指標 | 可接受 | 良好 | 優秀 |
|------|--------|------|------|
| 準確率 | > 70% | > 80% | > 90% |
| 精確率 | > 70% | > 85% | > 95% |
| 召回率 | > 70% | > 85% | > 95% |
| F1 分數 | > 70% | > 80% | > 90% |
| ROC-AUC | > 0.7 | > 0.85 | > 0.95 |

---

## 🐛 快速故障排除

| 問題 | 解決方案 |
|------|----------|
| ImportError: sklearn | `pip install scikit-learn --break-system-packages` |
| MongoDB 連接失敗 | 檢查服務是否運行、連接字串、使用者權限 |
| 訓練資料不足 | 使用 `batch_upload` 上傳更多資料 |
| 記憶體不足 | 減少 `n_estimators`, 設定 `max_depth` |
| 準確率太低 | 增加資料量、檢查標籤、調整參數 |
| 部署後仍用隨機分類 | 檢查 config.py 設定、模型路徑、重啟服務 |
| 圖表無法生成 | `pip install --upgrade matplotlib seaborn` |

---

## 📞 獲取幫助

1. **查看完整指南**: `RF_MODEL_GUIDE.md`
2. **查看套件說明**: `README.md`
3. **檢查日誌檔案**: `analysis_service.log`
4. **聯繫開發團隊**: 建立 Issue

---

## 🔄 更新模型

當有新資料時:

```bash
# 1. 重新訓練(會自動覆蓋舊模型)
python train_regrassion_model.py

# 2. 評估新模型
python regrassion_evaluate_model.py

# 3. 重啟分析服務(無需重新部署)
cd a_sub_system/analysis_service
python main.py
```

---

## 🎯 重要提醒

### ✅ 訓練前

- [ ] 已安裝所有依賴套件
- [ ] MongoDB 服務正常運行
- [ ] 至少有 50+ 筆訓練資料
- [ ] 資料標籤正確(normal/abnormal)

### ✅ 訓練後

- [ ] 檢查訓練報告
- [ ] 確認準確率 > 70%
- [ ] 查看混淆矩陣
- [ ] 分析特徵重要性

### ✅ 部署前

- [ ] 模型效能滿意
- [ ] 備份原始分類器
- [ ] 更新配置檔案
- [ ] 測試單一記錄預測

### ✅ 部署後

- [ ] 重啟分析服務
- [ ] 上傳測試音頻
- [ ] 確認使用新模型
- [ ] 監控預測結果

---

## 📈 效能優化建議

### 資料層面
- ✨ 增加訓練資料量(>500 筆)
- ✨ 平衡 normal/abnormal 比例
- ✨ 確保資料標籤正確
- ✨ 移除噪音資料

### 模型層面
- ✨ 嘗試不同聚合方式(mean/max/all)
- ✨ 使用網格搜尋最佳參數
- ✨ 調整樹的數量和深度
- ✨ 使用交叉驗證

### 系統層面
- ✨ 使用更強的硬體
- ✨ 增加記憶體配置
- ✨ 使用 GPU 加速(未來)
- ✨ 優化特徵提取流程

---

## 💡 最佳實踐

1. **定期重新訓練** - 當累積足夠新資料時(例如每 1000 筆)
2. **監控模型效能** - 記錄每批資料的準確率趨勢
3. **保存訓練歷史** - 保留每次訓練的報告和模型
4. **A/B 測試** - 新舊模型並行比較效能
5. **版本控制** - 使用 Git 管理模型和配置

---

## 📚 進階主題

詳見 **RF_MODEL_GUIDE.md**:
- 配置詳解
- 超參數調整
- 處理類別不平衡
- 特徵工程
- 集成學習
- 模型解釋性

---

**最後更新**: 2025-10-03
**版本**: v1.0
