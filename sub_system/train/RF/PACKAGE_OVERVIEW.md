# RF 模型訓練與部署套件 - 總覽

## 📦 套件資訊

**版本**: v1.0  
**建立日期**: 2025-10-03  
**用途**: 為音頻異常檢測系統訓練和部署隨機森林分類器

---

## 📄 檔案清單

本套件包含 **8 個檔案**,總大小約 **106 KB**:

### 核心腳本 (4 個)

1. **train_rf_model.py** (25 KB)
   - 模型訓練主腳本
   - 從 MongoDB 載入 LEAF 特徵
   - 訓練隨機森林模型
   - 生成評估報告和視覺化

2. **evaluate_model.py** (14 KB)
   - 模型評估工具
   - 跨資料集評估
   - 單一記錄預測測試
   - 模型資訊查詢

3. **step3_classifier_updated.py** (13 KB)
   - 更新的分類器
   - 支援載入 RF 模型
   - 向後相容隨機分類
   - 自動特徵聚合

4. **quick_start.py** (15 KB)
   - 快速啟動助手
   - 一鍵完成訓練與部署
   - 自動環境檢查
   - 智能錯誤處理

### 文件檔案 (4 個)

5. **README.md** (11 KB)
   - 套件總覽
   - 快速開始指南
   - 檔案說明
   - 工作流程範例

6. **RF_MODEL_GUIDE.md** (13 KB)
   - 完整使用指南
   - 詳細配置說明
   - 常見問題解答
   - 最佳實踐

7. **QUICK_REFERENCE.md** (7 KB)
   - 快速參考卡
   - 常用命令
   - 效能標準
   - 故障排除

8. **DEPLOYMENT_CHECKLIST.md** (10 KB)
   - 部署檢查清單
   - 驗證步驟
   - 測試方法
   - 回退計畫

---

## 🎯 核心功能

### 1. 資料載入
- ✅ 從 MongoDB 自動讀取已完成的分析記錄
- ✅ 提取 LEAF 特徵向量
- ✅ 支援多種特徵聚合方式(mean, max, median, all)
- ✅ 自動標籤編碼

### 2. 模型訓練
- ✅ 隨機森林演算法
- ✅ 自動資料分割(訓練/驗證/測試)
- ✅ 特徵標準化
- ✅ 交叉驗證
- ✅ 網格搜尋(可選)
- ✅ 類別權重平衡

### 3. 模型評估
- ✅ 準確率、精確率、召回率、F1分數
- ✅ 混淆矩陣
- ✅ ROC 曲線與 AUC
- ✅ 特徵重要性分析
- ✅ 交叉驗證分數

### 4. 視覺化
- ✅ 混淆矩陣圖
- ✅ ROC 曲線圖
- ✅ 特徵重要性圖
- ✅ 高解析度輸出(300 DPI)

### 5. 模型部署
- ✅ 自動備份原始分類器
- ✅ 更新配置檔案
- ✅ 無縫替換分類器
- ✅ 一鍵部署流程

---

## 🚀 使用流程

### 快速開始(3 步驟)

```bash
# 1. 安裝依賴
pip install scikit-learn matplotlib seaborn --break-system-packages

# 2. 執行快速啟動
python quick_start.py

# 3. 重啟分析服務
cd a_sub_system/analysis_service
python main.py
```

### 手動執行(5 步驟)

```bash
# 1. 訓練模型
python train_regrassion_model.py

# 2. 評估模型
python regrassion_evaluate_model.py

# 3. 備份原始分類器
cp a_sub_system/analysis_service/processors/step3_classifier.py \
   a_sub_system/analysis_service/processors/step3_classifier_backup.py

# 4. 替換分類器並更新配置
cp step3_classifier_updated.py \
   a_sub_system/analysis_service/processors/step3_classifier.py
# 編輯 a_sub_system/analysis_service/config.py

# 5. 重啟分析服務
cd a_sub_system/analysis_service
python main.py
```

---

## 📊 預期輸出

### 訓練階段

```
models/
├── rf_classifier.pkl           # 訓練好的隨機森林模型
├── feature_scaler.pkl          # 特徵標準化器
└── model_metadata.json         # 模型元資料和訓練歷史

training_reports/
├── confusion_matrix.png        # 混淆矩陣視覺化
├── feature_importance.png      # 特徵重要性圖
├── roc_curve.png              # ROC 曲線
└── evaluation_report.json     # 詳細評估報告
```

### 評估階段

```
evaluation_results/
├── cross_dataset_evaluation.json   # 跨資料集評估結果
├── confusion_matrix_eval.png       # 評估用混淆矩陣
└── roc_curve_eval.png             # 評估用 ROC 曲線
```

---

## 📈 效能指標

### 訓練資料要求
- **最少**: 50 筆(Normal + Abnormal)
- **建議**: 200+ 筆
- **理想**: 500+ 筆
- **類別平衡**: Normal/Abnormal 比例建議在 1:3 到 3:1 之間

### 模型效能標準

| 指標 | 可接受 | 良好 | 優秀 |
|------|--------|------|------|
| 準確率 | ≥ 70% | ≥ 80% | ≥ 90% |
| 精確率 | ≥ 70% | ≥ 85% | ≥ 95% |
| 召回率 | ≥ 70% | ≥ 85% | ≥ 95% |
| F1分數 | ≥ 70% | ≥ 80% | ≥ 90% |
| ROC-AUC | ≥ 0.70 | ≥ 0.85 | ≥ 0.95 |

---

## 🔧 可配置參數

### 特徵配置
- `feature_dim`: LEAF 特徵維度(預設: 40)
- `normalize`: 是否標準化(預設: True)
- `aggregation`: 聚合方式(預設: 'mean')

### 模型參數
- `n_estimators`: 樹的數量(預設: 100)
- `max_depth`: 最大深度(預設: None)
- `min_samples_split`: 分裂最小樣本(預設: 2)
- `min_samples_leaf`: 葉節點最小樣本(預設: 1)
- `class_weight`: 類別權重(預設: 'balanced')

### 訓練配置
- `test_size`: 測試集比例(預設: 0.2)
- `val_size`: 驗證集比例(預設: 0.1)
- `cross_validation`: 是否交叉驗證(預設: True)
- `cv_folds`: 交叉驗證折數(預設: 5)

---

## 🛡️ 安全特性

- ✅ 自動備份原始檔案
- ✅ 向後相容設計
- ✅ 錯誤自動降級(模型載入失敗時使用隨機分類)
- ✅ 完整的日誌記錄
- ✅ 異常處理機制

---

## 📞 技術支援

### 文件參考順序

1. **首次使用**: 閱讀 `README.md`
2. **快速參考**: 查看 `QUICK_REFERENCE.md`
3. **詳細指南**: 參考 `RF_MODEL_GUIDE.md`
4. **部署檢查**: 使用 `DEPLOYMENT_CHECKLIST.md`

### 常見問題

詳見 `RF_MODEL_GUIDE.md` 中的「常見問題」章節

### 日誌檔案

- 分析服務: `a_sub_system/analysis_service/analysis_service.log`
- 批量上傳: `a_sub_system/batch_upload/batch_upload.log`

---

## 🔄 更新與維護

### 模型更新

當有新的訓練資料時:
```bash
python train_regrassion_model.py  # 重新訓練
# 模型檔案會自動覆蓋
# 重啟分析服務即可使用新模型
```

### 參數調優

編輯 `train_rf_model.py` 中的 `ModelConfig` 類,然後重新訓練。

### 版本管理

建議使用 Git 管理:
```bash
git add models/ training_reports/
git commit -m "Update RF model - accuracy: 85%"
```

---

## 🎓 學習資源

- **Scikit-learn 官方文件**: https://scikit-learn.org/stable/
- **隨機森林演算法**: https://en.wikipedia.org/wiki/Random_forest
- **LEAF 論文**: https://arxiv.org/abs/2101.08596
- **模型評估指標**: https://scikit-learn.org/stable/modules/model_evaluation.html

---

## 📝 變更歷史

### v1.0 (2025-10-03)
- ✅ 初始版本發布
- ✅ 隨機森林分類器實作
- ✅ 自動訓練與評估流程
- ✅ 一鍵部署功能
- ✅ 完整文件套件

---

## 💡 最佳實踐

1. **定期重訓**: 每累積 1000 筆新資料時重新訓練
2. **效能監控**: 記錄每批資料的準確率趨勢
3. **A/B 測試**: 新舊模型並行比較效能
4. **資料清洗**: 定期檢查並修正錯誤標籤
5. **版本控制**: 保存每個版本的模型和報告

---

## 🎯 下一步

部署完成後:

1. ✅ 上傳測試音頻驗證模型
2. ✅ 監控預測結果和效能
3. ✅ 收集更多訓練資料
4. ✅ 定期重新訓練模型
5. ✅ 考慮進階優化(XGBoost, 深度學習等)

---

## 📄 授權

本套件為內部工具,請遵循專案授權規範使用。

---

**套件版本**: v1.0  
**建立日期**: 2025-10-03  
**維護狀態**: Active  

**祝使用順利! 🎉**
