# 隨機森林分類器訓練與部署指南

## 📋 目錄

1. [系統概述](#系統概述)
2. [環境準備](#環境準備)
3. [模型訓練](#模型訓練)
4. [模型評估](#模型評估)
5. [模型部署](#模型部署)
6. [配置說明](#配置說明)
7. [常見問題](#常見問題)

---

## 🎯 系統概述

本系統提供基於隨機森林(Random Forest)的音頻異常檢測分類器,用於替換原有的隨機分類器。

### 工作流程

```
1. 批量上傳音頻 (batch_upload) 
   ↓
2. 分析服務處理 (analysis_service)
   - Step 1: 音訊切割
   - Step 2: LEAF 特徵提取
   - Step 3: 隨機分類 (待替換)
   ↓
3. 訓練 RF 模型 (train_rf_model.py)
   ↓
4. 評估模型效能 (evaluate_model.py)
   ↓
5. 部署模型到分析服務
   - 更新配置
   - 替換分類器
   ↓
6. 使用 RF 模型進行實際分類
```

---

## 🛠️ 環境準備

### 1. 安裝依賴套件

```bash
pip install scikit-learn matplotlib seaborn --break-system-packages
```

### 2. 檢查必要檔案

確保以下檔案存在:
- `train_rf_model.py` - 訓練腳本
- `evaluate_model.py` - 評估腳本  
- `step3_classifier_updated.py` - 更新的分類器

### 3. 檢查 MongoDB 資料

確保 MongoDB 中有足夠的已標記資料:

```python
from pymongo import MongoClient

client = MongoClient("mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin")
db = client['web_db']
collection = db['recordings']

# 檢查資料數量
query = {
    'current_step': 4,
    'analysis_status': 'completed',
    'info_features.label': {'$exists': True, '$ne': 'unknown'}
}

count = collection.count_documents(query)
print(f"可用訓練資料: {count} 筆")

# 檢查標籤分布
normal_count = collection.count_documents({**query, 'info_features.label': 'normal'})
abnormal_count = collection.count_documents({**query, 'info_features.label': 'abnormal'})

print(f"Normal: {normal_count} 筆")
print(f"Abnormal: {abnormal_count} 筆")
```

**建議最少資料量:**
- Normal: 100+ 筆
- Abnormal: 100+ 筆
- 總計: 200+ 筆

---

## 🎓 模型訓練

### 1. 執行訓練腳本

```bash
cd /path/to/project
python train_regrassion_model.py
```

### 2. 訓練過程

訓練腳本會自動完成以下步驟:

#### 步驟 1: 載入訓練資料
- 從 MongoDB 讀取已完成分析的記錄
- 提取 LEAF 特徵和標籤
- 聚合多個切片的特徵 (預設使用平均值)

#### 步驟 2: 準備訓練資料
- 分割資料集: 訓練集(70%) / 驗證集(10%) / 測試集(20%)
- 標準化特徵
- 編碼標籤

#### 步驟 3: 訓練模型
- 使用隨機森林演算法
- 可選擇網格搜尋最佳參數
- 執行交叉驗證

#### 步驟 4: 評估模型
- 計算準確率、精確率、召回率、F1分數
- 生成混淆矩陣
- 繪製 ROC 曲線
- 分析特徵重要性

#### 步驟 5: 儲存模型
- 儲存模型檔案 (`rf_classifier.pkl`)
- 儲存標準化器 (`feature_scaler.pkl`)
- 儲存元資料 (`model_metadata.json`)

#### 步驟 6: 生成視覺化報告
- 混淆矩陣圖
- 特徵重要性圖
- ROC 曲線圖

### 3. 輸出檔案

訓練完成後會生成以下檔案:

```
models/
├── rf_classifier.pkl      # 訓練好的模型
├── feature_scaler.pkl     # 特徵標準化器
└── model_metadata.json    # 模型元資料

training_reports/
├── confusion_matrix.png       # 混淆矩陣
├── feature_importance.png     # 特徵重要性
├── roc_curve.png             # ROC 曲線
└── evaluation_report.json    # 評估報告
```

### 4. 檢視訓練結果

```bash
# 查看評估報告
cat training_reports/evaluation_report.json

# 查看模型元資料
cat models/model_metadata.json

# 查看圖表 (需要圖片檢視器)
# Windows: start training_reports/confusion_matrix.png
# Linux: xdg-open training_reports/confusion_matrix.png
```

---

## 📊 模型評估

### 1. 執行評估腳本

```bash
python regrassion_evaluate_model.py
```

### 2. 評估模式

#### 模式 1: 跨資料集評估
- 從 MongoDB 載入所有可用資料
- 評估模型在完整資料集上的效能
- 生成新的評估報告和視覺化

```
選擇評估模式:
  1. 跨資料集評估（從 MongoDB 載入所有資料）
  2. 單一記錄預測測試
  3. 顯示模型詳細資訊

請輸入選項 (1, 2 或 3): 1
```

#### 模式 2: 單一記錄預測測試
- 測試模型對單一記錄的預測
- 可用於調試和驗證

```
請輸入選項 (1, 2 或 3): 2
請輸入記錄的 AnalyzeUUID: 501a3f22-d326-486e-9550-67feeb898ea0
```

#### 模式 3: 顯示模型詳細資訊
- 查看模型參數
- 查看訓練歷史
- 查看特徵重要性

### 3. 評估指標說明

- **準確率 (Accuracy)**: 預測正確的比例
- **精確率 (Precision)**: 預測為異常的樣本中真正異常的比例
- **召回率 (Recall)**: 實際異常樣本中被正確預測的比例
- **F1分數**: 精確率和召回率的調和平均
- **ROC-AUC**: ROC 曲線下面積,越接近 1 越好

### 4. 混淆矩陣解讀

```
              預測 Normal  預測 Abnormal
實際 Normal       TP_n          FP_a
實際 Abnormal     FN_a          TP_a
```

- **TP (True Positive)**: 正確預測為異常
- **TN (True Negative)**: 正確預測為正常
- **FP (False Positive)**: 誤報 (正常預測為異常)
- **FN (False Negative)**: 漏報 (異常預測為正常)

**理想情況**: 對角線數字大,非對角線數字小

---

## 🚀 模型部署

### 1. 更新分析服務配置

編輯 `a_sub_system/analysis_service/config.py`:

```python
# ==================== 分類配置 ====================
CLASSIFICATION_CONFIG = {
    'method': 'rf_model',  # 改為 'rf_model'
    'classes': ['normal', 'abnormal'],
    
    # 模型路徑 (使用絕對路徑)
    'model_path': '/path/to/project/models',  # 修改為實際路徑
    'threshold': 0.5
}
```

### 2. 替換分類器檔案

```bash
# 備份原始分類器
cp a_sub_system/analysis_service/processors/step3_classifier.py \
   a_sub_system/analysis_service/processors/step3_classifier_backup.py

# 使用新分類器
cp step3_classifier_updated.py \
   a_sub_system/analysis_service/processors/step3_classifier.py
```

### 3. 重啟分析服務

```bash
cd a_sub_system/analysis_service
python main.py
```

### 4. 驗證部署

上傳一個測試音頻並檢查結果:

```python
from pymongo import MongoClient

client = MongoClient("mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin")
db = client['web_db']
collection = db['recordings']

# 查詢最新記錄
latest = collection.find_one(
    {'current_step': 4, 'analysis_status': 'completed'},
    sort=[('created_at', -1)]
)

# 檢查分類結果
classification = latest['analyze_features'][2]  # Step 3 結果
print(f"方法: {classification['classification_results']['method']}")
print(f"預測: {classification['classification_results']['summary']['final_prediction']}")
```

**預期結果**: `method` 應該是 `'rf_model'`

---

## ⚙️ 配置說明

### 訓練配置 (train_rf_model.py)

#### 特徵配置

```python
FEATURE_CONFIG = {
    'feature_dim': 40,           # LEAF 特徵維度
    'normalize': True,           # 是否標準化
    'aggregation': 'mean'        # 聚合方式: mean, max, median, all
}
```

**聚合方式說明:**
- `mean`: 取所有切片特徵的平均值 (推薦)
- `max`: 取最大值
- `median`: 取中位數
- `all`: 使用多種統計量 (mean + std + max + min)

#### 模型配置

```python
MODEL_CONFIG = {
    'rf_params': {
        'n_estimators': 100,         # 樹的數量
        'max_depth': None,           # 樹的最大深度
        'min_samples_split': 2,      # 分裂所需最小樣本數
        'min_samples_leaf': 1,       # 葉節點最小樣本數
        'max_features': 'sqrt',      # 每次分裂考慮的特徵數
        'class_weight': 'balanced'   # 處理類別不平衡
    },
    
    'grid_search': False,            # 是否使用網格搜尋
}
```

**參數調整建議:**
- 如果**過擬合**: 減少 `n_estimators` 或設定 `max_depth`
- 如果**欠擬合**: 增加 `n_estimators` 或減小 `min_samples_split`
- 如果**類別不平衡**: 保持 `class_weight='balanced'`

#### 訓練配置

```python
TRAINING_CONFIG = {
    'test_size': 0.2,              # 測試集比例
    'val_size': 0.1,               # 驗證集比例
    'cross_validation': True,      # 是否交叉驗證
    'cv_folds': 5,                 # 交叉驗證折數
}
```

### 部署配置 (config.py)

```python
CLASSIFICATION_CONFIG = {
    'method': 'rf_model',          # 分類方法: 'random' 或 'rf_model'
    'model_path': '/path/to/models',  # 模型目錄路徑
    'threshold': 0.5,              # 分類閾值
}
```

---

## ❓ 常見問題

### Q1: 訓練時出現 "沒有找到可用的訓練資料"

**原因**: MongoDB 中沒有足夠的已完成分析且有標籤的記錄

**解決方法**:
1. 檢查資料數量:
```python
collection.count_documents({
    'current_step': 4,
    'analysis_status': 'completed',
    'info_features.label': {'$exists': True, '$ne': 'unknown'}
})
```

2. 使用 batch_upload 工具上傳更多已標記的音頻資料

### Q2: 模型準確率很低 (<70%)

**可能原因**:
- 訓練資料不足
- 資料品質不佳
- 特徵聚合方式不適合
- 類別嚴重不平衡

**解決方法**:
1. 增加訓練資料量 (建議 500+ 筆)
2. 檢查資料標籤是否正確
3. 嘗試不同的聚合方式 (`aggregation` 參數)
4. 調整模型參數或使用網格搜尋

### Q3: 部署後分析服務仍使用隨機分類

**檢查清單**:
1. 確認 `config.py` 中 `method='rf_model'`
2. 確認 `model_path` 指向正確的目錄
3. 確認模型檔案存在:
   - `models/rf_classifier.pkl`
   - `models/feature_scaler.pkl`
   - `models/model_metadata.json`
4. 檢查分析服務日誌是否有載入錯誤
5. 確認已重啟分析服務

### Q4: 記憶體不足錯誤

**解決方法**:
1. 減少 `n_estimators` (例如改為 50)
2. 設定 `max_depth` 限制樹的深度
3. 減少並行處理數量 (`n_jobs`)
4. 分批處理資料

### Q5: 如何改善模型效能?

**策略**:
1. **增加資料量**: 更多訓練資料通常能改善效能
2. **平衡資料集**: 確保 normal 和 abnormal 樣本數量接近
3. **特徵工程**: 嘗試不同的聚合方式
4. **超參數調整**: 使用網格搜尋尋找最佳參數
5. **集成學習**: 考慮使用 XGBoost 或其他進階演算法

### Q6: 如何回退到隨機分類器?

```python
# 1. 修改配置
CLASSIFICATION_CONFIG = {
    'method': 'random',  # 改回 'random'
    ...
}

# 2. 恢復原始分類器 (如果有備份)
cp a_sub_system/analysis_service/processors/step3_classifier_backup.py \
   a_sub_system/analysis_service/processors/step3_classifier.py

# 3. 重啟分析服務
```

---

## 📝 使用範例

### 完整工作流程範例

```bash
# 1. 上傳訓練資料 (假設已有標記的資料集)
cd a_sub_system/batch_upload
python batch_upload.py  # 上傳 normal 和 abnormal 資料

# 2. 等待分析服務處理完成
cd ../analysis_service
python main.py

# 3. 訓練模型
cd ../../
python train_regrassion_model.py

# 4. 評估模型
python regrassion_evaluate_model.py
# 選擇選項 1 進行跨資料集評估

# 5. 如果效能滿意,部署模型
# 編輯 a_sub_system/analysis_service/config.py
# 替換分類器檔案
# 重啟分析服務

# 6. 測試新模型
python regrassion_evaluate_model.py
# 選擇選項 2 測試單一記錄
```

### Python API 使用範例

```python
# 載入模型進行預測
from evaluate_model import ModelEvaluator
import numpy as np

# 初始化評估器
evaluator = ModelEvaluator('models')

# 準備特徵 (40 維)
features = np.random.randn(1, 40)

# 預測
prediction = evaluator.model.predict(features)
proba = evaluator.model.predict_proba(features)

print(f"預測類別: {prediction[0]}")  # 0=normal, 1=abnormal
print(f"預測機率: Normal={proba[0][0]:.3f}, Abnormal={proba[0][1]:.3f}")
```

---

## 📚 參考資料

- [Scikit-learn Random Forest 文件](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)
- [LEAF 特徵提取論文](https://arxiv.org/abs/2101.08596)
- [異常檢測最佳實踐](https://scikit-learn.org/stable/modules/outlier_detection.html)

---

## 🔄 更新歷史

- **v1.0** (2025-10-03): 初始版本
  - 隨機森林分類器實作
  - 完整訓練與評估流程
  - 部署指南

---

## 📧 支援

如有問題或建議,請建立 Issue 或聯繫開發團隊。
