# 部署檢查清單

## 📦 交付檔案清單

請確認以下 **7 個檔案** 已正確複製到專案根目錄:

- [ ] `train_rf_model.py` (25 KB) - 模型訓練主腳本
- [ ] `evaluate_model.py` (14 KB) - 模型評估工具
- [ ] `step3_classifier_updated.py` (13 KB) - 更新的分類器
- [ ] `quick_start.py` (15 KB) - 快速啟動腳本
- [ ] `RF_MODEL_GUIDE.md` (13 KB) - 完整使用指南
- [ ] `README.md` (11 KB) - 套件說明文件
- [ ] `QUICK_REFERENCE.md` (7 KB) - 快速參考卡

**總大小**: 約 98 KB

---

## 🎯 部署前檢查

### 1. 環境檢查

```bash
# Python 版本
python --version  # 應該 >= 3.8

# MongoDB 連接測試
python -c "
from pymongo import MongoClient
try:
    client = MongoClient('mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin', serverSelectionTimeoutMS=2000)
    client.admin.command('ping')
    print('✅ MongoDB 連接成功')
    client.close()
except Exception as e:
    print(f'❌ MongoDB 連接失敗: {e}')
"

# 檢查現有套件
python -c "
import sys
packages = ['sklearn', 'numpy', 'pymongo']
for pkg in packages:
    try:
        __import__(pkg)
        print(f'✅ {pkg} 已安裝')
    except ImportError:
        print(f'❌ {pkg} 未安裝')
"
```

### 2. 安裝依賴

```bash
# 安裝新增的套件
pip install scikit-learn matplotlib seaborn --break-system-packages

# 驗證安裝
python -c "import sklearn, matplotlib, seaborn; print('✅ 所有套件已安裝')"
```

### 3. 資料檢查

```bash
# 檢查訓練資料數量
python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin')
db = client['web_db']
collection = db['recordings']

query = {
    'current_step': 4,
    'analysis_status': 'completed',
    'info_features.label': {'\$exists': True, '\$ne': 'unknown'}
}

total = collection.count_documents(query)
normal = collection.count_documents({**query, 'info_features.label': 'normal'})
abnormal = collection.count_documents({**query, 'info_features.label': 'abnormal'})

print(f'總資料量: {total} 筆')
print(f'  Normal: {normal} 筆')
print(f'  Abnormal: {abnormal} 筆')

if total >= 200:
    print('✅ 資料充足')
elif total >= 50:
    print('⚠️ 資料偏少,建議增加到 200+ 筆')
else:
    print('❌ 資料不足,需要至少 50 筆')

client.close()
"
```

**最少要求**: 50 筆
**建議**: 200+ 筆

---

## 🚀 執行流程檢查

### 方案 A: 使用快速啟動(推薦)

```bash
# 執行快速啟動腳本
python quick_start.py
```

**檢查點**:
- [ ] 環境檢查通過
- [ ] 資料檢查通過
- [ ] 訓練成功完成
- [ ] 評估效能滿意(準確率 > 70%)
- [ ] 自動部署完成

### 方案 B: 手動執行

#### 步驟 1: 訓練模型

```bash
python train_regrassion_model.py
```

**檢查點**:
- [ ] 載入資料成功
- [ ] 訓練完成無錯誤
- [ ] 生成模型檔案:
  - [ ] `models/rf_classifier.pkl`
  - [ ] `models/feature_scaler.pkl`
  - [ ] `models/model_metadata.json`
- [ ] 生成訓練報告:
  - [ ] `training_reports/confusion_matrix.png`
  - [ ] `training_reports/feature_importance.png`
  - [ ] `training_reports/roc_curve.png`
  - [ ] `training_reports/evaluation_report.json`

#### 步驟 2: 評估模型

```bash
python regrassion_evaluate_model.py
# 選擇選項 1 (跨資料集評估)
```

**檢查點**:
- [ ] 模型載入成功
- [ ] 準確率 >= 0.70
- [ ] 精確率 >= 0.70
- [ ] 召回率 >= 0.70
- [ ] F1 分數 >= 0.70
- [ ] 混淆矩陣合理(對角線數字大)

#### 步驟 3: 手動部署

```bash
# 3.1 備份原始分類器
cp a_sub_system/analysis_service/processors/step3_classifier.py \
   a_sub_system/analysis_service/processors/step3_classifier_backup.py

# 3.2 替換分類器
cp step3_classifier_updated.py \
   a_sub_system/analysis_service/processors/step3_classifier.py

# 3.3 更新配置
# 編輯 a_sub_system/analysis_service/config.py
# 修改以下內容:

CLASSIFICATION_CONFIG = {
    'method': 'rf_model',  # 從 'random' 改為 'rf_model'
    'classes': ['normal', 'abnormal'],
    'model_path': '/絕對路徑/to/models',  # 設定模型目錄的絕對路徑
    'threshold': 0.5
}
```

**檢查點**:
- [ ] 原始分類器已備份
- [ ] 新分類器已替換
- [ ] config.py 中 `method='rf_model'`
- [ ] config.py 中 `model_path` 設定正確

---

## ✅ 部署後驗證

### 1. 重啟分析服務

```bash
cd a_sub_system/analysis_service
python main.py
```

**檢查點**:
- [ ] 服務啟動無錯誤
- [ ] 日誌顯示 "✓ 模型載入成功"
- [ ] 日誌顯示 "method=rf_model"

### 2. 測試單一記錄預測

```bash
# 在另一個終端執行
python regrassion_evaluate_model.py
# 選擇選項 2
# 輸入任一已完成的 AnalyzeUUID
```

**檢查點**:
- [ ] 預測成功執行
- [ ] 返回預測結果(normal/abnormal)
- [ ] 顯示信心度(0-1 之間)
- [ ] 顯示機率分布

### 3. 上傳新音頻測試

```bash
# 使用 batch_upload 或 Web UI 上傳一個測試音頻
# 等待分析完成後查詢結果

python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin')
db = client['web_db']

# 查詢最新記錄
latest = db.recordings.find_one(
    {'current_step': 4, 'analysis_status': 'completed'},
    sort=[('created_at', -1)]
)

if latest:
    # 檢查分類結果
    classification = latest['analyze_features'][2]
    method = classification['classification_results']['method']
    prediction = classification['classification_results']['summary']['final_prediction']
    
    print(f'方法: {method}')
    print(f'預測: {prediction}')
    
    if method == 'rf_model':
        print('✅ 使用 RF 模型')
    else:
        print('❌ 仍使用隨機分類')
else:
    print('❌ 沒有找到完成的記錄')

client.close()
"
```

**檢查點**:
- [ ] 方法顯示為 'rf_model'
- [ ] 有預測結果
- [ ] 有信心度資訊

---

## 🔍 常見問題檢查

### 問題 1: 訓練時出現 "沒有找到可用的訓練資料"

**檢查**:
```bash
python -c "
from pymongo import MongoClient
c = MongoClient('mongodb://web_ui:hod2iddfsgsrl@localhost:27020/admin')
count = c.web_db.recordings.count_documents({
    'current_step': 4,
    'analysis_status': 'completed',
    'info_features.label': {'\$in': ['normal', 'abnormal']}
})
print(f'資料數量: {count}')
c.close()
"
```

**解決**: 使用 batch_upload 上傳更多已標記的音頻

### 問題 2: 模型準確率很低 (<70%)

**檢查**:
- [ ] 訓練資料是否足夠(>200 筆)
- [ ] 資料標籤是否正確
- [ ] 類別是否平衡(比例不超過 3:1)

**解決**:
1. 增加訓練資料
2. 檢查並修正標籤
3. 嘗試不同的 `aggregation` 設定
4. 調整模型參數或使用網格搜尋

### 問題 3: 部署後仍使用隨機分類

**檢查**:
```bash
# 1. 檢查配置檔案
grep -A 5 "CLASSIFICATION_CONFIG" a_sub_system/analysis_service/config.py

# 2. 檢查模型檔案
ls -lh models/

# 3. 檢查分析服務日誌
tail -50 a_sub_system/analysis_service/analysis_service.log | grep -i model
```

**解決**:
1. 確認 config.py 中 `method='rf_model'`
2. 確認 `model_path` 是絕對路徑且正確
3. 確認模型檔案存在且可讀
4. 重啟分析服務

### 問題 4: ImportError 或 ModuleNotFoundError

**檢查**:
```bash
python -c "
required = ['sklearn', 'numpy', 'pandas', 'matplotlib', 'seaborn', 'pymongo']
for pkg in required:
    try:
        __import__(pkg)
        print(f'✅ {pkg}')
    except ImportError as e:
        print(f'❌ {pkg}: {e}')
"
```

**解決**:
```bash
pip install scikit-learn numpy pandas matplotlib seaborn pymongo --break-system-packages
```

---

## 📊 效能基準

訓練完成後,模型應該達到以下基準:

| 指標 | 最低要求 | 建議 | 優秀 |
|------|----------|------|------|
| 訓練資料量 | 50 筆 | 200 筆 | 500+ 筆 |
| 準確率 | 70% | 80% | 90%+ |
| 精確率 | 70% | 85% | 95%+ |
| 召回率 | 70% | 85% | 95%+ |
| F1 分數 | 70% | 80% | 90%+ |
| ROC-AUC | 0.70 | 0.85 | 0.95+ |
| 訓練時間 | - | < 5 分鐘 | < 2 分鐘 |

---

## 📝 部署記錄

部署完成後,請填寫以下資訊以便追蹤:

```
部署日期: _______________
部署人員: _______________
模型版本: v1.0

訓練資料:
- 總數量: _______ 筆
- Normal: _______ 筆
- Abnormal: _______ 筆

模型效能:
- 準確率: _______
- 精確率: _______
- 召回率: _______
- F1分數: _______
- ROC-AUC: _______

配置:
- 聚合方式: _______
- 樹數量: _______
- 最大深度: _______

備註:
________________________
________________________
```

---

## 🔄 回退計畫

如果新模型出現問題,可以快速回退:

```bash
# 1. 停止分析服務 (Ctrl+C)

# 2. 恢復原始分類器
cp a_sub_system/analysis_service/processors/step3_classifier_backup.py \
   a_sub_system/analysis_service/processors/step3_classifier.py

# 3. 修改配置
# 編輯 a_sub_system/analysis_service/config.py
# 將 'method' 改回 'random'

# 4. 重啟分析服務
cd a_sub_system/analysis_service
python main.py
```

---

## 📚 文件索引

完成部署後,可參考以下文件:

1. **README.md** - 套件總覽和快速開始
2. **RF_MODEL_GUIDE.md** - 完整使用指南和技術細節
3. **QUICK_REFERENCE.md** - 常用命令和快速參考
4. **DEPLOYMENT_CHECKLIST.md** - 本文件,部署檢查清單

---

## ✅ 最終檢查

部署完成前,請確認:

- [ ] 所有檔案已複製到正確位置
- [ ] 依賴套件已安裝
- [ ] 訓練資料充足(>50 筆)
- [ ] 模型訓練成功
- [ ] 模型效能滿意(準確率 >70%)
- [ ] 分類器已替換
- [ ] 配置已更新
- [ ] 分析服務已重啟
- [ ] 測試預測成功
- [ ] 日誌確認使用 RF 模型
- [ ] 原始檔案已備份
- [ ] 部署記錄已填寫

**全部完成? 恭喜部署成功! 🎉**

---

## 📞 支援資訊

如遇問題:
1. 查看 **RF_MODEL_GUIDE.md** 的常見問題章節
2. 檢查日誌檔案: `analysis_service.log`
3. 使用 `evaluate_model.py` 進行診斷
4. 聯繫開發團隊

---

**檢查清單版本**: v1.0
**最後更新**: 2025-10-03
