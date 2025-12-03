# CycleGAN System Architecture

## 系統概述

本系統是一個基於 PyTorch Lightning 的 CycleGAN 實現，專門用於 40 維 LEAF 音訊特徵的域適應。

## 核心組件

### 1. 模型層 (models/)

#### Generator (生成器)
- **架構**: ResNet-based Encoder-Decoder
- **輸入/輸出**: 40 維 → 40 維
- **特點**:
  - 使用殘差塊保持特徵信息
  - 支持序列和單幀輸入
  - BatchNorm + LeakyReLU + Dropout

#### Discriminator (判別器)
- **架構**: Multi-layer Perceptron
- **功能**: 判別特徵真偽
- **兩種實現**:
  - 標準判別器：適用於一般特徵
  - PatchGAN：適用於序列特徵

#### CycleGANModule (Lightning 模組)
- **訓練邏輯**:
  - Cycle Consistency Loss
  - Adversarial Loss (LSGAN)
  - Identity Loss
- **優化器**: 4 個 Adam 優化器（2 個生成器 + 2 個判別器）

### 2. 數據層 (data/)

#### LEAFDomainDataset
- **功能**: 雙域配對數據集
- **特性**:
  - 自動標準化
  - 數據增強（噪聲、dropout）
  - 序列長度對齊

#### DataLoader
- **MongoDB 加載器**: 直接從 analysis_service 讀取
- **文件加載器**: 支持 JSON 和 NPY 格式

#### Preprocessor
- **功能**: 特徵預處理管道
- **操作**: 標準化、增強、填充/截斷

### 3. 訓練層 (training/)

#### Loss Functions
- **Cycle Loss**: L1 距離，確保循環一致性
- **Adversarial Loss**: MSE (LSGAN)，對抗訓練
- **Identity Loss**: L1 距離，保持身份映射

### 4. 評估層 (evaluation/)

#### Metrics
- **MMD**: Maximum Mean Discrepancy，衡量分布距離
- **Fréchet Distance**: 高斯分布假設下的距離度量

### 5. 工具層 (utils/)

- **Config Manager**: YAML 配置加載
- **Logger**: 統一日誌管理
- **MongoDB Handler**: 數據庫操作（如需要）

## 數據流程

### 訓練流程

```
MongoDB/File → DataLoader → LEAFDomainDataset
                                ↓
                        (feat_A, feat_B)
                                ↓
                        CycleGANModule
                        ├── G_AB(feat_A) → fake_B
                        ├── G_BA(feat_B) → fake_A
                        ├── G_BA(fake_B) → recovered_A
                        ├── G_AB(fake_A) → recovered_B
                        ├── D_A(feat_A, fake_A)
                        └── D_B(feat_B, fake_B)
                                ↓
                        Loss Computation
                        ├── Cycle Loss
                        ├── Adversarial Loss
                        └── Identity Loss
                                ↓
                        Optimizer Step
                                ↓
                        Checkpoint Save
```

### 推理流程

```
Input Features (JSON/NPY)
        ↓
  Load Features
        ↓
  Normalize (if trained with normalization)
        ↓
  Model Inference
  ├── G_AB (A → B)
  └── G_BA (B → A)
        ↓
  Denormalize
        ↓
  Save Converted Features
```

## 訓練策略

### Loss 權重

```
Total Loss = λ_cycle * Cycle Loss
           + λ_adv * Adversarial Loss
           + λ_id * Identity Loss

推薦設置：
- λ_cycle = 10.0
- λ_adv = 1.0
- λ_id = 5.0
```

### 優化器配置

- **學習率**: 0.0002
- **Beta1**: 0.5
- **Beta2**: 0.999
- **調度器**: Cosine Annealing

### 數據增強

- **高斯噪聲**: σ = 0.01
- **特徵 Dropout**: p = 0.1
- **時間扭曲**: 0.8x ~ 1.2x

## 性能優化

### GPU 優化
- Mixed Precision Training (FP16)
- Gradient Accumulation
- DataLoader 多線程

### 內存優化
- Batch Size 調整
- 序列長度限制
- Checkpoint 策略

## 擴展性

### 添加新的生成器

```python
from models import Generator

class CustomGenerator(nn.Module):
    def __init__(self, ...):
        # 自定義架構
        pass
```

### 添加新的損失函數

```python
from training.losses import CycleLoss

class PerceptualLoss(nn.Module):
    def __init__(self):
        # 感知損失
        pass
```

### 添加新的數據源

```python
from data.data_loader import FileLEAFLoader

class CustomDataLoader:
    @staticmethod
    def load_from_source(path):
        # 自定義加載邏輯
        pass
```

## 配置管理

### 配置文件結構

```yaml
data:           # 數據配置
model:          # 模型架構
training:       # 訓練參數
validation:     # 驗證設置
logging:        # 日誌配置
hardware:       # 硬件設置
```

### 配置優先級

1. 命令行參數
2. 配置文件
3. 默認值

## 監控與調試

### TensorBoard 可視化

- Loss 曲線
- 學習率變化
- 特徵分布

### 檢查點管理

- Top-K 模型保存
- 最後模型保存
- 早停機制

## 部署

### 模型導出

```python
# 導出為 TorchScript
scripted = torch.jit.script(model.generator_AB)
torch.jit.save(scripted, "generator_ab.pt")
```

### 推理優化

- 移除訓練相關組件
- Batch Inference
- ONNX 導出（可選）

## 最佳實踐

1. **數據準備**: 確保兩個域的樣本數量相近
2. **超參數調整**: 從推薦值開始，逐步調整
3. **訓練監控**: 定期檢查 TensorBoard
4. **模型評估**: 使用 MMD 和 FD 評估效果
5. **域對齊驗證**: 轉換後使用分類器驗證

---

**版本**: 1.0.0
**最後更新**: 2025-10-27
