# 批次域轉換使用指南

本指南說明如何使用 `scripts/batch_domain_conversion.py`，針對 MongoDB 中符合 Domain B  (預設為 *BATCH_UPLOAD_Mafaulda*) 查詢條件的所有分析任務，自動將 Step 2 的特徵轉換為 Step 6，並寫回資料庫。

---

## 1. 腳本概要

- 位置：`scripts/batch_domain_conversion.py`
- 功能：批次載入 CycleGAN 檢查點，遍歷符合查詢條件的分析任務，執行 Mafaulda → CPC (B→A) 轉換，再將結果保存為新的 `analyze_features` 步驟。
- 預設來源步驟：Step 2（LEAF 40 維特徵）
- 預設輸出步驟：Step 6（可透過參數覆寫）
- 預設查詢：取自 `config.py` → `DATA_CONFIG["domain_b"]["mongo_query"]`

---

## 2. 先決條件

1. **環境依賴**  
   - 以虛擬環境安裝 `requirements.txt` 中的套件 (`torch`、`pymongo`、`numpy` 等)。

2. **MongoDB 設定**  
   - `config.py` 中的 `MONGODB_CONFIG` 必須正確設定（或以環境變數覆寫）。

3. **CycleGAN 檢查點**  
   - 預設為 `checkpoints/best.ckpt`，可依需要改用其他檔案。

---

## 3. 基本用法

```bash
cd a_sub_system/train/py_cyclegan
python scripts/batch_domain_conversion.py
```

執行時流程：
1. 連線 MongoDB，將 `DATA_CONFIG["domain_b"]["mongo_query"]` 與 Step 2 條件 (`features_step = 2`, `features_state = completed`) 組合查詢。
2. 逐筆檢索符合條件的分析任務。
3. 若尚未存在 Step 6（或指定步驟），使用 CycleGAN 將 Step 2 的特徵轉換為 A-domain。
4. 寫回 `analyze_features`，並附加 metadata（檢查點、轉換時間、來源步驟等）。

完成後會在終端印出統計資訊：
- 總處理數
- 成功寫入數
- 跳過數（例如已存在目標步驟）
- 失敗數（資料格式或模型推論失敗等）

---

## 4. 常用參數

```bash
python scripts/batch_domain_conversion.py \
  --checkpoint checkpoints/best.ckpt \
  --device cuda \
  --input-step 2 \
  --output-step 6 \
  --limit 500 \
  --device-id BATCH_UPLOAD_Mafaulda \
  --overwrite
```

| 參數 | 說明 | 預設 |
|------|------|------|
| `--checkpoint` | CycleGAN 檢查點路徑 | `checkpoints/best.ckpt` |
| `--device` | 推論裝置 (`cpu` / `cuda`) | 取自 `INFERENCE_CONFIG["device"]` |
| `--input-step` | 來源步驟編號 | `2` |
| `--output-step` | 轉換結果寫入的步驟 | `6` |
| `--limit` | 最大處理筆數（None 表示不限） | 取自 `DATA_CONFIG["domain_b"]["max_samples"]` |
| `--device-id` | 覆寫 `info_features.device_id` 查詢 | 留空則沿用 `config.py` |
| `--overwrite` | 若步驟已存在是否覆寫 | 預設跳過 |
| `--dry-run` | 僅顯示計畫處理的任務，不寫入資料庫 | 關閉 |

---

## 5. 常見情境

1. **僅確認會處理哪些任務**  
   使用 `--dry-run`，腳本會列出符合條件的 `AnalyzeUUID`，但不寫入步驟。

2. **重新轉換已存在 Step 6 的任務**  
   加上 `--overwrite`，即可覆蓋原步驟內容。

3. **臨時處理少量任務**  
   使用 `--limit 50` 等限制筆數，避免一次轉換過多資料。

4. **切換目標設備**  
   `--device-id 新設備 ID` 會覆寫 `config.py` 中的 `DOMAIN_B_DEVICE_ID`。

---

## 6. 轉換結果格式

每個成功的分析任務會新增（或覆寫）以下資料片段：

```json
{
  "features_step": 6,
  "features_state": "completed",
  "features_data": [...轉換後的 40 維特徵...],
  "metadata": {
    "source_step": 2,
    "direction": "B→A",
    "checkpoint": "checkpoints/best.ckpt",
    "device": "cuda:0",
    "converted_at": "2025-11-04T03:20:15.123Z",
    "num_samples": 128
  }
}
```

---

## 7. 疑難排解

- **顯示「features_data 為空」或形狀錯誤**  
  - 確認 Step 2 的資料是否完整，並且為 `(seq_len, 40)` 的二維陣列。

- **提示「步驟已存在」**  
  - 預設不覆寫，可使用 `--overwrite` 或先在 MongoDB 中移除指定步驟。

- **CUDA 不可用**  
  - 在沒有 GPU 或驅動的環境會自動切換到 `cpu`，如需 GPU 推論請確認環境設定。

---

如需進一步整合（例如加入自動排程、記錄轉換批次 ID 等），可於腳本內新增自訂 metadata 或包裝成公用模組。祝轉換順利！\n
