# 分析服務模型下載與載入流程

本文件說明分析服務如何從雲端下載模型、管理本地快取、以及載入模型進行分析。

---

## 流程概覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                        分析任務觸發                                  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 1. 讀取分析配置 (analysis_configs)                                   │
│    - config_id / analysis_method_id                                 │
│    - model_files.classification_method                              │
│    - model_files.files (各模型的 file_id 和 filename)               │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. ModelCacheManager.ensure_models_for_config()                     │
│    - 根據 classification_method 決定需要哪些模型檔案                  │
│    - 檢查 cache_index.json 中 file_id 是否已存在                     │
│    - 若已快取且檔案存在 → 使用快取                                    │
│    - 若未快取 → 從 GridFS 下載並儲存                                  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. 返回 local_paths 映射                                            │
│    例如: {'rf_model': Path('.../model_cache/abc123/my_model.pkl')}  │
│    ※ 檔名來自配置中的 filename，不是硬編碼                            │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. AudioClassifier.apply_config_with_models()                       │
│    - 將完整檔案路徑存入 config['rf_model_file']                       │
│    - 呼叫 _apply_method_and_model() 載入模型                         │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. 模型載入                                                          │
│    - 必須有 rf_model_file 配置，否則報錯                              │
│    - 檔案必須存在，否則報錯                                           │
│    - 不使用任何硬編碼檔名或自動發現                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三種情況詳解

### 情況 1：新的分析設定被設定好後

**觸發條件**：配置中的 `file_id` 不存在於本地 `cache_index.json`

**系統行為**：

1. `ModelCacheManager.get_cached_path(file_id)` 返回 `None`
2. 呼叫 `download_model(file_id, filename)`
3. 從 GridFS 下載檔案內容
4. 儲存到 `model_cache/{file_id}/{filename}`
   - **檔名使用配置中指定的 filename**
   - 不會使用硬編碼檔名
5. 更新 `cache_index.json`：
   ```json
   {
     "abc123def456": {
       "local_path": "model_cache/abc123def456/mimii_pump_rf_classifier.pkl",
       "filename": "mimii_pump_rf_classifier.pkl",
       "downloaded_at": "2026-01-15T10:30:00Z",
       "size": 84123456
     }
   }
   ```
6. 返回本地路徑給分類器使用

**日誌範例**：
```
INFO - Downloading model from GridFS: mimii_pump_rf_classifier.pkl (abc123def456)
INFO - Model cached: model_cache/abc123def456/mimii_pump_rf_classifier.pkl (84123456 bytes)
INFO - Required model ready: rf_model -> model_cache/abc123def456/mimii_pump_rf_classifier.pkl
```

---

### 情況 2：舊的分析設定的檔案已存在於本地

**觸發條件**：配置中的 `file_id` 已存在於 `cache_index.json` 且本地檔案存在

**系統行為**：

1. `ModelCacheManager.get_cached_path(file_id)` 找到快取記錄
2. 驗證本地檔案確實存在
3. **直接返回快取路徑，不下載**
4. 分類器使用快取的模型檔案

**日誌範例**：
```
DEBUG - Cache hit: mimii_pump_rf_classifier.pkl (abc123def456)
INFO - Required model ready: rf_model -> model_cache/abc123def456/mimii_pump_rf_classifier.pkl
```

**注意**：快取索引以 `file_id` 為鍵，不是檔名。這意味著：
- 相同 `file_id` 的檔案只會下載一次
- 不同 `file_id` 但相同檔名的檔案會分別儲存在不同目錄

---

### 情況 3：雲端模型的檔案類型存在缺失

**觸發條件**：配置中缺少必要的模型檔案（如 `rf_model`）或 `file_id` 為空

**系統行為（必要檔案）**：

1. `ensure_models_for_config()` 檢查必要檔案
2. 若 `rf_model` 不在配置中：
   ```
   ModelNotFoundError: Required model file not configured: rf_model (RF Classification Model)
   ```
3. 若 `file_id` 為空：
   ```
   ModelNotFoundError: Required model file has no file_id: rf_model
   ```
4. **不會降級到 random 模式，直接報錯**

**系統行為（模型載入階段）**：

即使下載成功，載入時也會嚴格檢查：

1. 若 `rf_model_file` 未設定：
   ```
   FileNotFoundError: 未指定 RF 模型檔案路徑。請確認配置中包含 rf_model_file。
   ```
2. 若檔案不存在：
   ```
   FileNotFoundError: RF 模型檔案不存在: /path/to/model.pkl
   ```

**日誌範例**：
```
ERROR - CycleGAN+RF initialization failed: 未指定 RF 模型檔案路徑 (model_file)。目錄: /path/to/model_cache/xxx
ERROR - 模型載入失敗: [錯誤訊息]
```

---

## 配置結構說明

### MongoDB `analysis_configs` 集合

```json
{
  "config_id": "f8b58498-8d7e-4bea-946c-9f16974aa8a8",
  "analysis_method_id": "WAV_LEAF_RF_v1",
  "enabled": true,
  "model_files": {
    "classification_method": "cyclegan_rf",
    "files": {
      "rf_model": {
        "file_id": "6968b3a04a2c707f541a9fc4",
        "filename": "mimii_pump_rf_classifier.pkl"
      },
      "cyclegan_checkpoint": {
        "file_id": "6968b39b4a2c707f541a9fa4",
        "filename": "cycle_A0.4930.ckpt"
      },
      "rf_metadata": {
        "file_id": "6968b3ab4a2c707f541aa0fb",
        "filename": "model_metadata.json"
      }
    }
  }
}
```

**重要欄位**：

| 欄位 | 說明 |
|------|------|
| `file_id` | GridFS 中的檔案 ID，用於下載和快取索引 |
| `filename` | 實際的檔案名稱，下載後使用此名稱儲存 |
| `classification_method` | 決定需要哪些模型檔案（`rf_model` / `cyclegan_rf`） |

---

## 本地快取結構

```
model_cache/
├── cache_index.json              # 快取索引（file_id → 本地路徑映射）
├── 6968b3a04a2c707f541a9fc4/     # 以 file_id 為目錄名
│   └── mimii_pump_rf_classifier.pkl
├── 6968b39b4a2c707f541a9fa4/
│   └── cycle_A0.4930.ckpt
└── 6968b3ab4a2c707f541aa0fb/
    └── model_metadata.json
```

**cache_index.json 範例**：
```json
{
  "6968b3a04a2c707f541a9fc4": {
    "local_path": "model_cache/6968b3a04a2c707f541a9fc4/mimii_pump_rf_classifier.pkl",
    "filename": "mimii_pump_rf_classifier.pkl",
    "downloaded_at": "2026-01-15T09:30:00+00:00",
    "size": 84123456
  }
}
```

---

## 錯誤處理原則

| 階段 | 錯誤類型 | 行為 |
|------|---------|------|
| 配置檢查 | 必要模型未配置 | `ModelNotFoundError` |
| 配置檢查 | `file_id` 為空 | `ModelNotFoundError` |
| 下載階段 | GridFS 下載失敗 | `ModelDownloadError` |
| 載入階段 | `rf_model_file` 未設定 | `FileNotFoundError` |
| 載入階段 | 模型檔案不存在 | `FileNotFoundError` |

**原則**：所有錯誤直接拋出例外，**不會降級到 random 模式**。

---

## 相關檔案

| 檔案 | 功能 |
|------|------|
| `model_cache_manager.py` | 模型快取管理、下載邏輯 |
| `processors/step3_classifier.py` | 分類器配置套用、模型載入 |
| `sub_system/train/RF/inference.py` | RFClassifier 模型載入 |
| `config.py` | `MODEL_REQUIREMENTS` 定義各方法需要的檔案 |
