# CycleGAN for LEAF Feature Domain Adaptation

基於 CycleGAN 的 40 維 LEAF 特徵域適應系統，用於不同設備/環境之間的音訊特徵對齊。

## 專案簡介

本專案實現了一個完整的 CycleGAN 訓練系統，專門用於處理從 `analysis_service` 輸出的 40 維 LEAF 特徵。主要應用於：

- **域適應**：將不同設備採集的 LEAF 特徵對齊到統一域
- **環境補償**：處理溫度、噪聲等環境變化導致的特徵漂移
- **跨設備校正**：使不同設備的特徵具有可比性

## 系統架構

```
py_cyclegan/
├── models/              # 模型定義（Generator, Discriminator, CycleGAN Module）
├── data/                # 數據處理（Dataset, DataLoader, Preprocessing）
├── training/            # 訓練相關（Losses）
├── evaluation/          # 評估指標（MMD, Fréchet Distance）
├── utils/               # 工具函數（Config, Logger）
├── scripts/             # 執行腳本（train.py, evaluate.py, convert.py）
├── config.py            # 統一配置文件（Python字典）
├── checkpoints/         # 模型檢查點（運行時創建）
├── logs/                # 訓練日誌（運行時創建）
└── outputs/             # 轉換結果（運行時創建）
```

## 快速開始

### 1. 環境安裝

```bash
# 創建虛擬環境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 安裝依賴
pip install -r requirements.txt
```

### 2. 配置系統

系統使用 **Python 字典配置 + 環境變量**（與 analysis_service 保持一致）。

#### 方式 1: 修改 `config.py`（默認配置）

```python
# config.py

MONGODB_CONFIG = {
    'host': 'localhost',
    'port': 27020,
    'username': 'web_ui',
    'password': 'your_password',
    'database': 'web_db',
    'collection': 'recordings'
}

DATA_CONFIG = {
    'domain_a': {
        'mongo_query': {
            'info_features.device_id': 'device_001',  # 修改為實際設備 ID
            'analysis_status': 'completed'
        },
        'max_samples': 1000
    },
    'domain_b': {
        'mongo_query': {
            'info_features.device_id': 'device_002',  # 修改為實際設備 ID
            'analysis_status': 'completed'
        },
        'max_samples': 1000
    }
}
```

#### 方式 2: 使用環境變量（推薦）

```bash
# MongoDB 配置
export MONGODB_HOST=localhost
export MONGODB_PORT=27020
export MONGODB_USERNAME=web_ui
export MONGODB_PASSWORD=your_password
export MONGODB_DATABASE=web_db

# 域配置
export DOMAIN_A_DEVICE_ID=device_001
export DOMAIN_B_DEVICE_ID=device_002
export DOMAIN_A_MAX_SAMPLES=1000
export DOMAIN_B_MAX_SAMPLES=1000

# 訓練參數
export MAX_EPOCHS=200
export BATCH_SIZE=32
export LEARNING_RATE=0.0002
export LAMBDA_CYCLE=10.0
export LAMBDA_IDENTITY=5.0

# 硬件配置
export ACCELERATOR=gpu  # 或 cpu
export DEVICES=1
```

### 3. 查看配置

```bash
# 打印當前配置（驗證配置是否正確）
python scripts/train.py --print-config
```

### 4. 訓練模型

```bash
# 使用默認配置訓練
python scripts/train.py
```

```bash
# 從檢查點恢復訓練
python scripts/train.py --resume checkpoints/cyclegan-epoch=85-val/cycle_A=0.6260.ckpt

# 使用環境變量覆蓋配置
#BATCH_SIZE=16 MAX_EPOCHS=100 python scripts/train.py
```

### 5. 監控訓練

```bash
# 啟動 TensorBoard
tensorboard --logdir logs --host 0.0.0.0 --port 6006

# 在瀏覽器中訪問
# http://localhost:6006
```

### 6. 域轉換

```python
import torch
from models import CycleGANModule
from data import FileLEAFLoader
import numpy as np

# 加載模型
model = CycleGANModule.load_from_checkpoint("checkpoints/best.ckpt")
model.eval()

# 加載 Domain A 的特徵
features_a = FileLEAFLoader.load_from_json("data/test_device_a.json")

# 轉換到 Domain B
converted_features = []
for feat in features_a:
    feat_tensor = torch.FloatTensor(feat).unsqueeze(0)
    with torch.no_grad():
        converted = model.convert_A_to_B(feat_tensor)
    converted_features.append(converted.squeeze(0).numpy())

# 保存結果
FileLEAFLoader.save_to_npy(converted_features, "outputs/converted_to_b.npy")
```

### 7. 批次域轉換

- 使用 `scripts/batch_domain_conversion.py` 可一次處理符合 Domain B 查詢條件的所有 `AnalyzeUUID`。
- 支援參數覆寫來源/輸出步驟、處理筆數、裝置等設定。
- 詳細操作請參考《[批次域轉換使用指南](BATCH_CONVERSION_GUIDE.md)》。

## 配置說明

### 主要配置項

#### MongoDB 配置

```python
MONGODB_CONFIG = {
    'host': 'localhost',       # MongoDB 主機
    'port': 27020,             # MongoDB 端口
    'username': 'web_ui',      # 用戶名
    'password': 'password',    # 密碼
    'database': 'web_db',      # 數據庫名
    'collection': 'recordings' # 集合名
}
```

#### 訓練參數

```python
TRAINING_CONFIG = {
    'max_epochs': 200,         # 最大訓練輪數
    'batch_size': 32,          # 批次大小
    'learning_rate': 0.0002,   # 學習率
    'lambda_cycle': 10.0,      # Cycle Loss 權重
    'lambda_identity': 5.0,    # Identity Loss 權重
}
```

#### 硬件配置

```python
HARDWARE_CONFIG = {
    'accelerator': 'gpu',      # gpu 或 cpu
    'devices': 1,              # GPU 數量
    'precision': '32'          # 精度：32 或 16
}
```

### 環境變量完整列表

| 變量名 | 說明 | 默認值 |
|--------|------|--------|
| `MONGODB_HOST` | MongoDB 主機 | localhost |
| `MONGODB_PORT` | MongoDB 端口 | 27020 |
| `MONGODB_USERNAME` | MongoDB 用戶名 | web_ui |
| `MONGODB_PASSWORD` | MongoDB 密碼 | - |
| `DOMAIN_A_DEVICE_ID` | Domain A 設備 ID | device_001 |
| `DOMAIN_B_DEVICE_ID` | Domain B 設備 ID | device_002 |
| `MAX_EPOCHS` | 最大訓練輪數 | 200 |
| `BATCH_SIZE` | 批次大小 | 32 |
| `LEARNING_RATE` | 學習率 | 0.0002 |
| `LAMBDA_CYCLE` | Cycle Loss 權重 | 10.0 |
| `LAMBDA_IDENTITY` | Identity Loss 權重 | 5.0 |
| `ACCELERATOR` | 加速器類型 | gpu |

## 與 analysis_service 的集成

### 數據流

```
analysis_service
    ↓ Step 1: Audio Slicing
    ↓ Step 2: LEAF Feature Extraction (40維)
    ↓
MongoDB: analyze_features[1].features_data
    ↓
py_cyclegan (MongoDBLEAFLoader)
    ↓ 域適應訓練
    ↓
Domain-Aligned Features
```

### 從 MongoDB 讀取數據

```python
from data import MongoDBLEAFLoader

loader = MongoDBLEAFLoader(
    mongo_uri="mongodb://user:password@host:port",
    db_name="web_db",
    collection_name="recordings"
)

# 讀取兩個設備的 LEAF 特徵
data = loader.load_dual_domain(
    domain_a_query={"info_features.device_id": "device_001"},
    domain_b_query={"info_features.device_id": "device_002"}
)
```

## 應用場景示例

### 1. 多設備校準

```bash
# 設置環境變量
export DOMAIN_A_DEVICE_ID=motor_sensor_001
export DOMAIN_B_DEVICE_ID=motor_sensor_002

# 訓練
python scripts/train.py
```

### 2. 環境補償（溫度校正）

修改 `config.py` 中的查詢條件：

```python
DATA_CONFIG = {
    'domain_a': {
        'mongo_query': {
            'info_features.temperature_range': {'$lt': 10},  # 低溫環境
            'analysis_status': 'completed'
        }
    },
    'domain_b': {
        'mongo_query': {
            'info_features.temperature_range': {'$gte': 20, '$lte': 30},  # 常溫
            'analysis_status': 'completed'
        }
    }
}
```

### 3. 時間漂移校正

```python
DATA_CONFIG = {
    'domain_a': {
        'mongo_query': {
            'created_at': {'$lt': '2024-01-01'}  # 舊數據
        }
    },
    'domain_b': {
        'mongo_query': {
            'created_at': {'$gte': '2024-06-01'}  # 新數據
        }
    }
}
```

## 評估

```python
from evaluation import compute_mmd, compute_frechet_distance

# 計算 MMD（Maximum Mean Discrepancy）
mmd = compute_mmd(features_a, features_b)
print(f"MMD Distance: {mmd:.4f}")

# 計算 Fréchet Distance
fd = compute_frechet_distance(features_a, features_b)
print(f"Fréchet Distance: {fd:.4f}")
```

## 常見問題

### 1. MongoDB 連接失敗

```bash
# 測試連接
python -c "from pymongo import MongoClient; client = MongoClient('your_uri'); print(client.server_info())"
```

### 2. GPU 內存不足

```bash
# 減少 batch size
export BATCH_SIZE=16
python scripts/train.py
```

### 3. 訓練不穩定

```bash
# 調整損失權重
export LAMBDA_CYCLE=15.0
export LAMBDA_IDENTITY=7.0
python scripts/train.py
```

## 開發

### 測試配置

```bash
# 測試配置是否有效
python config.py
```

### 運行模塊測試

```bash
# 測試模型
python -m models.generator
python -m models.discriminator
python -m models.cyclegan_module

# 測試數據加載
python -m data.leaf_dataset
python -m data.data_loader
```

## 引用

如果使用本項目，請引用：

```
CycleGAN for LEAF Feature Domain Adaptation
用於 LEAF 特徵域適應的 CycleGAN 系統
```

## 授權

MIT License

## 聯繫方式

如有問題或建議，請提交 Issue。

---

**特點**:
- ✅ Python 字典配置（與 analysis_service 保持一致）
- ✅ 支持環境變量覆蓋
- ✅ 40 維 LEAF 特徵
- ✅ 完整的 PyTorch Lightning 實現
- ✅ 與 analysis_service 無縫集成

**最後更新**: 2025-10-27
