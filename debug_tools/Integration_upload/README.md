# 批次上傳整合工具 v1.0

整合 CPC、MAFAULDA、MIMII 三種資料集的批次上傳工具，提供統一的 CLI 介面和中斷恢復功能。

## 功能特色

- **多資料集支援**：整合三種資料集（CPC、MAFAULDA、MIMII）
- **靈活組合**：支援 7 種資料集上傳組合
- **中斷恢復**：自動檢測先前的上傳進度並提供繼續或重新開始選項
- **Dry-run 模式**：預覽上傳內容而不實際上傳
- **統計匯總**：顯示各資料集的詳細統計和合併報告
- **並行上傳**：支援多線程並行上傳
- **進度追蹤**：實時顯示上傳進度條

## 目錄結構

```
Integration_upload/
├── main.py                     # CLI 主程序
├── README.md                   # 本文件
├── config/                     # 配置模組
│   ├── __init__.py
│   ├── base_config.py          # 基礎配置
│   ├── cpc_config.py           # CPC 配置
│   ├── mafaulda_config.py      # MAFAULDA 配置
│   └── mimii_config.py         # MIMII 配置
├── core/                       # 核心模組
│   ├── __init__.py
│   ├── logger.py               # 日誌管理
│   ├── mongodb_handler.py      # MongoDB 操作
│   ├── base_uploader.py        # 抽象基礎類別
│   └── utils.py                # 共用函數
├── uploaders/                  # 上傳器模組
│   ├── __init__.py
│   ├── cpc_uploader.py         # CPC 上傳器
│   ├── mafaulda_uploader.py    # MAFAULDA 上傳器
│   └── mimii_uploader.py       # MIMII 上傳器
└── reports/                    # 報告和日誌輸出
    ├── upload_progress.json
    ├── combined_upload_report_*.json
    ├── upload_report_*.json
    ├── dry_run_previews/
    └── logs/
```

## 安裝依賴

```bash
pip install pymongo soundfile tqdm bson
```

## 配置設定

### 1. 修改 MongoDB 連接設定

編輯 `config/base_config.py`：

```python
MONGODB_CONFIG = {
    'host': 'localhost',    # MongoDB 主機
    'port': 27021,          # MongoDB 端口
    'username': 'web_ui',
    'password': 'hod2iddfsgsrl',
    'database': 'web_db',
    'collection': 'recordings'
}
```

### 2. 修改資料集路徑

編輯對應的配置文件：

- `config/cpc_config.py` - CPC 資料集路徑
- `config/mafaulda_config.py` - MAFAULDA 資料集路徑
- `config/mimii_config.py` - MIMII 資料集路徑

範例：
```python
UPLOAD_DIRECTORY = r"C:\path\to\your\dataset"
```

### 3. 調整上傳行為（可選）

在 `config/base_config.py` 中調整：

```python
UPLOAD_BEHAVIOR = {
    'skip_existing': True,          # 是否跳過已存在的檔案
    'check_duplicates': True,       # 是否檢查重複
    'concurrent_uploads': 3,        # 並行上傳數量
    'retry_attempts': 3,            # 重試次數
    'retry_delay': 2,               # 重試延遲（秒）
    'per_label_limit': 0,           # 每個標籤上限（0=不限制）
}
```

## 使用方法

### 基本使用

在 `Integration_upload/` 目錄下執行：

```bash
python main.py
```

### 互動式流程

#### 步驟 1：選擇資料集組合

```
步驟1: 選擇要上傳的資料集
----------------------------------------------------------------------
  1. 全部上傳
  2. 只上傳 CPC
  3. 只上傳 MAFAULDA
  4. 只上傳 MIMII
  5. CPC + MAFAULDA
  6. CPC + MIMII
  7. MAFAULDA + MIMII

請選擇 (1-7):
```

#### 步驟 2：選擇上傳模式

**情況 A：沒有檢測到先前進度**

```
步驟2: 選擇上傳模式
----------------------------------------------------------------------
請選擇上傳模式：
  1. 正式上傳
  2. Dry-run（預覽模式）

請選擇 (1-2):
```

**情況 B：檢測到先前進度**

```
步驟2: 選擇上傳模式
----------------------------------------------------------------------
⚠️  檢測到先前的上傳進度！

請選擇處理方式：
  1. 刪除進度並重新開始正式上傳
  2. 刪除進度並重新開始 Dry-run
  3. 繼續先前的進度並正式上傳
  4. 繼續先前的進度並 Dry-run

請選擇 (1-4):
```

#### 步驟 3：執行上傳

程序會依序處理選定的資料集，顯示進度條和即時統計。

#### 步驟 4：查看統計匯總

上傳完成後會顯示：
- 總計統計
- 各資料集明細
- 標籤分佈

## 輸出文件

### 1. 進度文件
- 位置：`reports/upload_progress.json`
- 用途：記錄已上傳檔案的雜湊值，支援中斷恢復

### 2. 資料集報告
- 位置：`reports/upload_report_<資料集>_<時間戳>.json`
- 內容：單一資料集的詳細統計

### 3. 合併報告
- 位置：`reports/combined_upload_report_<時間戳>.json`
- 內容：所有選定資料集的統計匯總

### 4. 日誌文件
- 位置：`reports/logs/batch_upload.log`
- 內容：詳細的執行日誌

### 5. Dry-run 預覽
- 位置：`reports/dry_run_previews/dry_run_<資料集>_<時間戳>/`
- 內容：每個標籤的樣本文檔 JSON

## 使用範例

### 範例 1：上傳所有資料集

```bash
$ python main.py
# 選擇 1（全部上傳）
# 選擇 1（正式上傳）
```

### 範例 2：預覽 MAFAULDA 資料集

```bash
$ python main.py
# 選擇 3（只上傳 MAFAULDA）
# 選擇 2（Dry-run）
```

### 範例 3：繼續中斷的上傳

```bash
$ python main.py
# 選擇之前的組合
# 選擇 3（繼續先前的進度並正式上傳）
```

### 範例 4：重新開始上傳

```bash
$ python main.py
# 選擇任意組合
# 選擇 1（刪除進度並重新開始正式上傳）
```

## 資料集說明

### CPC（工廠環境音訊）
- 格式：WAV
- 結構：簡單，所有檔案使用相同標籤
- 特點：單聲道、16kHz 取樣率

### MAFAULDA（機械故障診斷）
- 格式：CSV
- 結構：多層故障層級（故障類型/變異/條件）
- 特點：8 通道、51.2kHz 取樣率

### MIMII（機器異音檢測）
- 格式：WAV
- 結構：4 層（SNR/機器類型/obj_ID/標籤）
- 特點：支援多種機器類型（pump、fan、slider、valve）

## 故障排除

### 配置錯誤

如果出現配置錯誤，程序會顯示具體的錯誤訊息：

```
❌ CPC 配置錯誤：
  - 找不到上傳資料夾：C:\path\to\cpc_data
```

解決方法：檢查並修正對應的配置文件。

### MongoDB 連接失敗

檢查：
1. MongoDB 服務是否運行
2. 連接參數是否正確（主機、端口、帳號、密碼）
3. 網路連接是否正常

### 記憶體不足

如果處理大量檔案時出現記憶體問題：
1. 減少 `concurrent_uploads` 數量
2. 使用 `per_label_limit` 限制每次上傳的檔案數量

## 保留原有上傳器

原有的三個獨立上傳器仍然保留在：
- `debug_tools/batch_upload/cpc_upload/`
- `debug_tools/batch_upload/mafaulda_upload/`
- `debug_tools/batch_upload/mimii_upload/`

可作為備份或獨立使用。

## 技術架構

- **設計模式**：策略模式 + 模板方法模式
- **模組化**：核心功能與資料集特定邏輯分離
- **可擴展性**：易於添加新的資料集上傳器

## 授權

本工具為內部使用，請勿外傳。

## 更新日誌

### v1.0.0 (2025-11-10)
- 初始版本
- 整合三種資料集上傳功能
- 實現互動式 CLI
- 支援中斷恢復和 Dry-run 模式
