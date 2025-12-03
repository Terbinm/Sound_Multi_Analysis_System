# 配置系統更新說明

**更新日期**: 2025-10-27
**更新原因**: 與 analysis_service 保持配置風格一致

---

## ✅ 完成的更改

### 1. 從 YAML 配置切換到 Python 字典配置

#### 舊方式（已棄用）
```yaml
# configs/train_config.yaml
data:
  source: mongodb
  mongodb:
    uri: "mongodb://..."
```

#### 新方式（現在使用）
```python
# config.py
MONGODB_CONFIG = {
    'host': os.getenv('MONGODB_HOST', 'localhost'),
    'port': int(os.getenv('MONGODB_PORT', '27020')),
    'uri': os.getenv('MONGODB_URI', '...')
}
```

### 2. 與 analysis_service 配置風格完全一致

```python
# 相同的結構和命名風格
MONGODB_CONFIG = {...}
DATA_CONFIG = {...}
LOGGING_CONFIG = {...}
SERVICE_CONFIG = {...}  # 如果需要
```

### 3. 完整的環境變量支持

所有配置項都可以通過環境變量覆蓋：

```bash
export MONGODB_HOST=localhost
export MONGODB_PORT=27020
export DOMAIN_A_DEVICE_ID=device_001
export BATCH_SIZE=32
export MAX_EPOCHS=200
```

---

## 📝 使用方式

### 方式 1: 直接修改 config.py

```python
# 編輯 a_sub_system/train/py_cyclegan/config.py

MONGODB_CONFIG = {
    'host': 'your_host',
    'port': 27020,
    # ...
}

DATA_CONFIG = {
    'domain_a': {
        'mongo_query': {
            'info_features.device_id': 'your_device',
            # ...
        }
    }
}
```

### 方式 2: 使用環境變量（推薦）

```bash
# 設置環境變量
export MONGODB_HOST=your_host
export DOMAIN_A_DEVICE_ID=your_device
export BATCH_SIZE=32

# 運行訓練
python scripts/train.py
```

### 方式 3: 命令行內聯

```bash
BATCH_SIZE=16 MAX_EPOCHS=100 python scripts/train.py
```

---

## 🔧 更新的文件

### 新增/更新
- ✅ `config.py` - 統一配置文件（新增）
- ✅ `utils/config.py` - 配置加載器（重寫，移除 YAML）
- ✅ `utils/__init__.py` - 更新導出
- ✅ `scripts/train.py` - 使用新配置系統
- ✅ `requirements.txt` - 移除 pyyaml 依賴

### 刪除
- ❌ `configs/train_config.yaml` - 不再需要

---

## 🎯 優點

### 1. 配置風格統一
- 與 analysis_service 完全一致
- 團隊成員熟悉的配置方式
- 易於維護

### 2. 環境變量優先
- 生產環境友好
- Docker/K8s 部署友好
- CI/CD 集成簡單

### 3. 類型安全
- Python 原生類型檢查
- IDE 自動完成
- 減少配置錯誤

### 4. 動態配置
- 可以使用 Python 邏輯
- 條件配置
- 配置計算

---

## 📋 遷移檢查清單

如果您之前使用 YAML 配置，請按以下步驟遷移：

### 步驟 1: 備份舊配置
```bash
# 如果存在 YAML 配置，先備份
cp configs/train_config.yaml configs/train_config.yaml.bak
```

### 步驟 2: 轉換配置到 config.py
將 YAML 中的值複製到 `config.py` 對應的字典中：

```yaml
# 舊 YAML
data:
  domain_a:
    mongo_query:
      device_id: "device_001"
```

```python
# 新 config.py
DATA_CONFIG = {
    'domain_a': {
        'mongo_query': {
            'info_features.device_id': 'device_001'
        }
    }
}
```

### 步驟 3: 測試配置
```bash
# 打印配置驗證
python config.py

# 驗證配置有效性
python scripts/train.py --print-config
```

### 步驟 4: 清理舊文件
```bash
# 刪除舊的 YAML 配置
rm configs/train_config.yaml
rm configs/train_config.yaml.bak  # 確認無誤後刪除備份
```

---

## 🔍 配置驗證

### 查看當前配置
```bash
# 方法 1: 直接運行 config.py
python config.py

# 方法 2: 通過訓練腳本
python scripts/train.py --print-config
```

### 測試環境變量覆蓋
```bash
# 設置環境變量
export BATCH_SIZE=16

# 查看是否生效
python config.py | grep batch_size
```

---

## 💡 配置最佳實踐

### 1. 開發環境
```bash
# 直接修改 config.py 中的默認值
# 適合頻繁調整參數的開發階段
```

### 2. 測試環境
```bash
# 使用環境變量文件
cat > .env << EOF
MONGODB_HOST=test-mongodb
BATCH_SIZE=16
MAX_EPOCHS=50
EOF

# 加載並運行
set -a; source .env; set +a
python scripts/train.py
```

### 3. 生產環境
```bash
# 使用 Docker 環境變量
docker run \
  -e MONGODB_HOST=prod-mongodb \
  -e BATCH_SIZE=32 \
  -e MAX_EPOCHS=200 \
  cyclegan:latest python scripts/train.py
```

---

## ❓ 常見問題

### Q1: 為什麼不用 YAML？
A: 為了與 analysis_service 保持一致，使用相同的配置風格有助於：
- 減少學習成本
- 統一代碼風格
- 更好的團隊協作

### Q2: 如何管理多個配置？
A: 使用環境變量或創建多個配置文件：

```python
# config_dev.py
from config import *
TRAINING_CONFIG['max_epochs'] = 10  # 快速測試

# config_prod.py
from config import *
TRAINING_CONFIG['max_epochs'] = 200  # 完整訓練
```

### Q3: 如何在 Jupyter Notebook 中使用？
A:
```python
import sys
sys.path.insert(0, '/path/to/py_cyclegan')

from config import CONFIG
from utils import get_training_config

config = get_training_config()
print(config['batch_size'])
```

---

## 📞 獲取幫助

如有問題：
1. 查看 `config.py` 中的註釋
2. 運行 `python config.py` 查看完整配置
3. 查看 `README.md` 的配置章節
4. 提交 Issue

---

**更新完成**: 2025-10-27
**版本**: 2.0.0 - Python 字典配置
