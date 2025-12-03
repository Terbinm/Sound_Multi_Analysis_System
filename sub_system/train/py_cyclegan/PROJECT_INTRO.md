# CycleGAN 音訊特徵域轉換系統 | CycleGAN Audio Feature Domain Transfer System

[![Python](https://img.shields.io/badge/Python-3.10-blue.svg)](https://www.python.org/)
[![PyTorch Lightning](https://img.shields.io/badge/PyTorch%20Lightning-2.0+-purple.svg)](https://lightning.ai/)
[![Docker](https://img.shields.io/badge/Docker-Ready-green.svg)](https://www.docker.com/)
[![R](https://img.shields.io/badge/R-4.0+-276DC3.svg)](https://www.r-project.org/)

---

## 目錄 | Table of Contents

- [專案簡介 | Project Overview](#專案簡介--project-overview)
- [系統架構 | System Architecture](#系統架構--system-architecture)
- [技術棧 | Tech Stack](#技術棧--tech-stack)
- [目錄結構 | Directory Structure](#目錄結構--directory-structure)
- [核心功能 | Core Features](#核心功能--core-features)
- [安裝與部署 | Installation & Deployment](#安裝與部署--installation--deployment)
- [配置說明 | Configuration](#配置說明--configuration)
- [模型訓練指南 | Model Training Guide](#模型訓練指南--model-training-guide)
- [API 文檔 | API Documentation](#api-文檔--api-documentation)
- [使用範例 | Usage Examples](#使用範例--usage-examples)
- [開發指南 | Development Guide](#開發指南--development-guide)
- [故障排除 | Troubleshooting](#故障排除--troubleshooting)
- [維護與升級 | Maintenance](#維護與升級--maintenance)

---

## 專案簡介 | Project Overview

### 繁體中文

本專案是一個基於 **CycleGAN（循環生成對抗網路）** 的音訊特徵域轉換系統，專注於將 **CPC (Component - 主成分分析)** 特徵域轉換到 **MA (Motor Analysis - 馬達分析)** 特徵域。系統結合了深度學習、傳統音訊處理和分散式架構，提供高效、可擴展的音訊分析解決方案。

#### 核心價值

- **無監督域轉換**：利用 CycleGAN 實現無需配對數據的特徵域轉換
- **端到端處理**：從音訊檔案到特徵提取再到域轉換的完整流程
- **分散式架構**：基於 RabbitMQ 的非同步任務處理，支援水平擴展
- **容器化部署**：完整的 Docker 支援，可快速部署到生產環境
- **靈活配置**：豐富的配置選項，適應不同的應用場景

#### 主要應用場景

- 馬達異常檢測的特徵工程
- 音訊信號的跨域分析
- 工業設備健康監測
- 聲學特徵增強與轉換

### English

This project is a **CycleGAN (Cycle-Consistent Generative Adversarial Network)** based audio feature domain transfer system, focusing on converting **CPC (Component - Principal Component Analysis)** features to **MA (Motor Analysis)** features. The system integrates deep learning, traditional audio processing, and distributed architecture to provide an efficient and scalable audio analysis solution.

#### Core Value

- **Unsupervised Domain Transfer**: Leverages CycleGAN for feature domain conversion without paired data
- **End-to-End Processing**: Complete pipeline from audio files to feature extraction to domain transfer
- **Distributed Architecture**: RabbitMQ-based asynchronous task processing with horizontal scalability
- **Containerized Deployment**: Full Docker support for rapid production deployment
- **Flexible Configuration**: Rich configuration options adaptable to various scenarios

#### Main Use Cases

- Feature engineering for motor anomaly detection
- Cross-domain audio signal analysis
- Industrial equipment health monitoring
- Acoustic feature enhancement and transformation

---

## 系統架構 | System Architecture

### 架構圖 | Architecture Diagram

```mermaid
graph TB
    subgraph "客戶端 Client"
        A[音訊檔案<br/>Audio Files]
    end

    subgraph "API 層 API Layer"
        B[Flask REST API<br/>Health Check]
    end

    subgraph "訊息佇列 Message Queue"
        C[RabbitMQ<br/>Exchange: analyze.direct]
        D[Queue: analyze.step.sliced_wav...]
    end

    subgraph "處理服務 Processing Service"
        E[AudioProcessor<br/>音訊處理器]
        F[R Environment<br/>特徵提取]
        G[CycleGAN Model<br/>域轉換]
    end

    subgraph "數據存儲 Data Storage"
        H[(MongoDB)]
        I[(GridFS<br/>檔案存儲)]
    end

    subgraph "模型層 Model Layer"
        J[Generator A→B<br/>生成器]
        K[Generator B→A<br/>生成器]
        L[Discriminator A<br/>判別器]
        M[Discriminator B<br/>判別器]
    end

    A -->|上傳<br/>Upload| I
    B -->|健康檢查<br/>Health Check| B
    C -->|消息路由<br/>Route| D
    D -->|消費消息<br/>Consume| E
    E -->|下載檔案<br/>Download| I
    E -->|R 腳本執行<br/>Execute R| F
    F -->|特徵數據<br/>Features| G
    G -->|轉換結果<br/>Results| H
    E -->|更新狀態<br/>Update Status| H
    G -.使用模型<br/>Use Model.-> J
    G -.使用模型<br/>Use Model.-> K
    J -.訓練<br/>Train.-> L
    K -.訓練<br/>Train.-> M

    style A fill:#e1f5ff
    style B fill:#fff4e1
    style G fill:#ffe1f5
    style H fill:#e1ffe1
    style I fill:#e1ffe1
```

### 數據流程圖 | Data Flow Diagram

```mermaid
sequenceDiagram
    participant Client as 客戶端<br/>Client
    participant MQ as RabbitMQ
    participant API as Flask API
    participant Proc as AudioProcessor
    participant R as R Environment
    participant Model as CycleGAN
    participant DB as MongoDB

    Client->>DB: 1. 上傳音訊檔案到 GridFS<br/>Upload audio to GridFS
    Client->>MQ: 2. 發送分析任務消息<br/>Send analysis task
    MQ->>Proc: 3. 消費任務消息<br/>Consume task
    Proc->>DB: 4. 查詢分析任務<br/>Query analysis task
    Proc->>DB: 5. 從 GridFS 下載檔案<br/>Download from GridFS
    Proc->>R: 6. 設置 R 環境參數<br/>Setup R environment
    R->>R: 7. 執行音訊特徵提取<br/>Extract audio features
    R->>Proc: 8. 返回 CPC 特徵<br/>Return CPC features
    Proc->>Model: 9. 正規化 CPC 特徵<br/>Normalize CPC features
    Model->>Model: 10. Generator A→B 轉換<br/>Transform via Generator
    Model->>Proc: 11. 返回 MA 特徵<br/>Return MA features
    Proc->>DB: 12. 保存轉換結果<br/>Save results
    Proc->>MQ: 13. 發送完成通知<br/>Send completion notification
    Client->>API: 14. 查詢處理狀態<br/>Query status
    API->>DB: 15. 返回分析結果<br/>Return results
```

### 組件說明 | Component Description

#### 繁體中文

1. **Flask REST API**：提供健康檢查和系統狀態查詢介面
2. **RabbitMQ 訊息佇列**：實現非同步任務處理和服務解耦
3. **AudioProcessor**：核心處理邏輯，協調各個組件完成分析任務
4. **R Environment**：使用 rpy2 調用 R 腳本進行音訊特徵提取
5. **CycleGAN Model**：基於 PyTorch Lightning 的域轉換模型
6. **MongoDB + GridFS**：存儲分析結果和音訊檔案

#### English

1. **Flask REST API**: Provides health check and system status query endpoints
2. **RabbitMQ Message Queue**: Enables asynchronous task processing and service decoupling
3. **AudioProcessor**: Core processing logic coordinating components for analysis tasks
4. **R Environment**: Uses rpy2 to invoke R scripts for audio feature extraction
5. **CycleGAN Model**: PyTorch Lightning-based domain transfer model
6. **MongoDB + GridFS**: Stores analysis results and audio files

---

## 技術棧 | Tech Stack

### 深度學習框架 | Deep Learning Framework

- **PyTorch**: 深度學習核心框架
- **PyTorch Lightning**: 簡化訓練流程和實驗管理
- **CycleGAN**: 循環一致性生成對抗網路

### 後端服務 | Backend Services

- **Flask**: REST API 框架
- **Python 3.10**: 主要開發語言
- **rpy2**: Python 與 R 的橋接器
- **R (Base + Libraries)**: 音訊特徵提取

### 數據存儲 | Data Storage

- **MongoDB**: NoSQL 數據庫，存儲分析結果
- **GridFS**: MongoDB 檔案存儲系統，處理大型音訊檔案

### 訊息佇列 | Message Queue

- **RabbitMQ**: AMQP 協議訊息代理，實現非同步任務處理
- **Pika**: Python 的 RabbitMQ 客戶端

### 部署與容器化 | Deployment & Containerization

- **Docker**: 容器化平台
- **Ubuntu 22.04**: 基礎映像
- **PowerShell Scripts**: 自動化部署腳本

### 主要 Python 套件 | Key Python Packages

```
Flask==3.1.0
PyTorch Lightning
pymongo==4.10.1
pika==1.3.2
rpy2==3.5.14
numpy==2.0.2
pandas==2.2.3
```

---

## 目錄結構 | Directory Structure

```
py_cyclegan/
├── cycleGan_model.py          # CycleGAN 模型定義 (Generator & Discriminator)
├── pl_module.py               # PyTorch Lightning 訓練模組
├── cpc_to_ma_converter.py     # CPC 到 MA 域轉換器
├── customer_R_slice_Extract_Features.py  # Flask 服務主程式
├── config.py                  # 配置檔案
├── output_LLM.py              # 專案文件輸出工具
├── test_v2.py                 # 測試腳本
├── requirements.txt           # Python 依賴
├── Dockerfile                 # Docker 映像定義
├── CD.md                      # 部署文檔
├── PROJECT_INTRO.md           # 本文檔
│
├── saves/                     # 模型檢查點
│   └── Batchnorm_version.ckpt
│
├── test_model/                # 測試模型與範例
│   ├── INPUT_FILE/
│   │   └── dsf.json
│   ├── output/
│   │   └── kkk.json
│   ├── cpc_to_ma_converter.py
│   ├── cycleGan_model.py
│   ├── pl_module.py
│   └── saves/
│       └── Batchnorm_version.ckpt
│
└── logs/                      # 日誌目錄 (運行時創建)
```

### 核心檔案說明 | Core File Description

#### `cycleGan_model.py`
定義 CycleGAN 的 Generator 和 Discriminator 模型架構。

**繁體中文**：
- `MotorGeneratorlinear`: 線性自編碼器生成器，將特徵從一個域映射到另一個域
- `MotorDiscriminatorLinear`: 線性判別器，判斷輸入特徵的真偽

**English**:
- `MotorGeneratorlinear`: Linear autoencoder generator for domain mapping
- `MotorDiscriminatorLinear`: Linear discriminator for authenticity classification

#### `pl_module.py`
PyTorch Lightning 模組，實現完整的訓練邏輯。

**Key Features | 關鍵特性**：
- Cycle consistency loss (循環一致性損失)
- Adversarial loss (對抗損失)
- Manual optimization (手動優化)
- TensorBoard logging (訓練日誌記錄)

#### `cpc_to_ma_converter.py`
獨立的轉換器類別，用於將 CPC 特徵轉換為 MA 特徵。

**Pipeline | 流程**：
1. 載入模型
2. 載入輸入數據
3. 正規化 CPC 特徵
4. 添加位置編碼
5. 執行域轉換
6. 反正規化 MA 特徵
7. 保存結果

#### `customer_R_slice_Extract_Features.py`
Flask 服務的主入口，整合所有組件。

**Responsibilities | 職責**：
- Flask API 服務
- RabbitMQ 消息監聽
- 音訊處理協調
- R 環境管理
- 數據庫操作

#### `config.py`
集中管理所有配置參數，支援環境變數覆蓋。

---

## 核心功能 | Core Features

### 1. CycleGAN 模型架構 | CycleGAN Model Architecture

#### 生成器 Generator

**繁體中文**：
生成器採用自編碼器架構，包含編碼器和解碼器兩部分：

```
輸入 (10 維) → Encoder → 潛在空間 (256 維) → Decoder → 輸出 (9 維)

Encoder:
- Linear(10, 64) + LeakyReLU + BatchNorm
- Linear(64, 128) + LeakyReLU + BatchNorm
- Linear(128, 256) + LeakyReLU + BatchNorm

Decoder:
- Linear(256, 128) + LeakyReLU + BatchNorm
- Linear(128, 64) + LeakyReLU + BatchNorm
- Linear(64, 9) + Tanh
```

**English**:
The generator uses an autoencoder architecture with encoder and decoder:

```
Input (10 dim) → Encoder → Latent Space (256 dim) → Decoder → Output (9 dim)
```

#### 判別器 Discriminator

**繁體中文**：
判別器使用多層感知器架構，輸出真偽機率：

```
輸入 (10 維) → Linear(128) → Linear(64) → Linear(32) → Linear(1) → Sigmoid
```

#### 訓練策略 Training Strategy

**Loss Functions | 損失函數**：

1. **Adversarial Loss** (對抗損失)：
   ```python
   BCE_loss = BCEWithLogitsLoss(D(x), real/fake)
   ```

2. **Cycle Consistency Loss** (循環一致性損失)：
   ```python
   Cycle_loss = MSE(G_BA(G_AB(x)), x)
   ```

3. **Total Loss** (總損失)：
   ```python
   Total = 0.1 * MSE_loss + 0.5 * Cycle_loss + 0.4 * Adversarial_loss
   ```

### 2. 音訊特徵提取 | Audio Feature Extraction

#### R 環境整合 | R Environment Integration

**繁體中文**：

系統使用 `rpy2` 橋接 Python 和 R，執行以下步驟：

1. **環境設置**：
   - 設定工作目錄
   - 載入之前步驟的分析數據
   - 配置 R 參數

2. **特徵提取**：
   - 執行 R 腳本 (`util_Analyze.R`, `util.R`, `3.3EF_lite.R`)
   - 從音訊片段提取 9 維 PC 特徵

3. **數據轉換**：
   - 將 R data.frame 轉換為 Python 字典列表
   - 處理不同數據類型 (float, int, string)

**English**:

The system uses `rpy2` to bridge Python and R for:

1. **Environment Setup**: Configure working directories and R parameters
2. **Feature Extraction**: Execute R scripts for audio analysis
3. **Data Conversion**: Transform R data.frame to Python dict list

### 3. CPC 到 MA 域轉換 | CPC to MA Domain Transfer

#### 轉換流程 | Transfer Pipeline

```mermaid
graph LR
    A[CPC 特徵<br/>CPC Features] -->|正規化<br/>Normalize| B[標準化特徵<br/>Normalized]
    B -->|添加位置編碼<br/>Add Position| C[含位置特徵<br/>With Position]
    C -->|Generator A→B<br/>Transfer| D[MA 特徵 正規化<br/>MA Normalized]
    D -->|反正規化<br/>Denormalize| E[MA 特徵<br/>MA Features]

    style A fill:#e1f5ff
    style E fill:#ffe1f5
```

#### 關鍵步驟 | Key Steps

**1. Normalization | 正規化**

```python
cpc_mean = torch.mean(cpc_tensor, dim=0)
cpc_std = torch.std(cpc_tensor, dim=0)
cpc_normalized = (cpc_tensor - cpc_mean) / (cpc_std + 1e-5)
```

**2. Position Encoding | 位置編碼**

```python
position_encoding = torch.linspace(0, 1, len(cpc_normalized)).unsqueeze(1)
cpc_with_position = torch.cat([cpc_normalized, position_encoding], dim=1)
```

**3. Domain Transfer | 域轉換**

```python
with torch.no_grad():
    ma_normalized = model.generator_A_to_B(cpc_with_position)
```

**4. Denormalization | 反正規化**

```python
ma_features = (ma_normalized * ma_std + ma_mean).cpu()
```

### 4. 分散式任務處理 | Distributed Task Processing

#### RabbitMQ 訊息流 | RabbitMQ Message Flow

**繁體中文**：

1. **任務提交**：
   - 客戶端上傳音訊檔案到 GridFS
   - 發送任務消息到 RabbitMQ exchange

2. **任務分發**：
   - Exchange 根據 routing key 路由消息
   - 任務佇列接收消息

3. **任務處理**：
   - Worker 從佇列消費消息
   - 更新任務狀態為 "processing"
   - 執行音訊處理流程

4. **結果通知**：
   - 處理完成後更新狀態為 "completed"
   - 發送完成通知到 state check exchange

**English**:

1. **Task Submission**: Upload audio to GridFS, send task message
2. **Task Distribution**: Exchange routes messages by routing key
3. **Task Processing**: Worker consumes and processes tasks
4. **Result Notification**: Update status and send completion notification

---

## 安裝與部署 | Installation & Deployment

### 環境要求 | Prerequisites

**繁體中文**：

- **作業系統**：Ubuntu 22.04 或 Windows (with Docker)
- **Python**：3.10+
- **R**：4.0+
- **Docker**：20.10+
- **MongoDB**：4.4+
- **RabbitMQ**：3.8+

**English**:

- **OS**: Ubuntu 22.04 or Windows (with Docker)
- **Python**: 3.10+
- **R**: 4.0+
- **Docker**: 20.10+
- **MongoDB**: 4.4+
- **RabbitMQ**: 3.8+

### 本地開發環境設置 | Local Development Setup

#### 1. 安裝 Python 依賴 | Install Python Dependencies

```bash
# 創建虛擬環境 | Create virtual environment
python -m venv .venv

# 啟動虛擬環境 | Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安裝依賴 | Install dependencies
pip install -r requirements.txt
pip install rpy2==3.5.14
```

#### 2. 安裝 R 和相關套件 | Install R and Packages

```bash
# Ubuntu
sudo apt-get update
sudo apt-get install r-base r-base-dev

# 執行 R 套件安裝腳本
Rscript install_r_packages.R
```

#### 3. 配置環境變數 | Configure Environment Variables

創建 `.env` 檔案 | Create `.env` file:

```bash
# MongoDB 配置
MONGO_URI=mongodb://user:password@host:port
MONGO_DB=sound_analysis

# RabbitMQ 配置
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest

# Flask 配置
FLASK_HOST=0.0.0.0
FLASK_PORT=57122
DEBUG=False

# 服務配置
SERVER_NAME=customer_R_slice_Extract_Features
SERVER_VISION=1.0.0
THE_STEP=4
```

#### 4. 運行服務 | Run Service

```bash
python customer_R_slice_Extract_Features.py
```

### Docker 部署 | Docker Deployment

#### 構建 Docker 映像 | Build Docker Image

**使用部署腳本 | Using Deployment Script**:

```powershell
# Windows PowerShell
.\scripts\build.ps1 1.0.6
```

**手動構建 | Manual Build**:

```bash
docker build -t your-registry/py_cyclegan:1.0.6 .
```

#### 運行容器 | Run Container

**使用部署腳本 | Using Deployment Script**:

```powershell
.\scripts\deploy.ps1 1.0.6
```

**手動運行 | Manual Run**:

```bash
docker run -d \
  --name py_cyclegan \
  -p 57122:57122 \
  -e MONGO_URI=mongodb://user:password@host:port \
  -e RABBITMQ_HOST=rabbitmq-host \
  your-registry/py_cyclegan:1.0.6
```

### 集群部署 | Cluster Deployment

#### 部署到 Docker Swarm 或 Kubernetes

**使用集群部署腳本 | Using Cluster Script**:

```powershell
# 部署 | Deploy
.\scripts\docker_sound_analysis_cluster_deploy.ps1 1.0.6

# 刪除 | Remove
.\scripts\docker_sound_analysis_cluster_delete.ps1
```

### 部署腳本詳細說明 | Deployment Scripts Details

#### `build.ps1` - 構建腳本

**繁體中文**：

此腳本負責構建 Docker 映像並推送到 Registry。

**參數**：
- `$VERSION`: Docker 映像版本號 (例如：1.0.6)

**執行內容**：
1. 驗證 Dockerfile 存在
2. 構建 Docker 映像
3. 為映像打上版本標籤和 latest 標籤
4. 推送映像到 Docker Registry

**使用範例**：
```powershell
.\scripts\build.ps1 1.0.6
```

**English**:

This script builds Docker image and pushes to registry.

**Parameters**:
- `$VERSION`: Docker image version (e.g., 1.0.6)

**Actions**:
1. Verify Dockerfile exists
2. Build Docker image
3. Tag with version and latest
4. Push to Docker Registry

#### `deploy.ps1` - 單機部署腳本

**繁體中文**：

此腳本用於在單台機器上部署或更新容器。

**參數**：
- `$VERSION`: Docker 映像版本號 (可選，預設為 latest)

**執行內容**：
1. 停止並刪除現有容器
2. 拉取指定版本的映像
3. 創建並啟動新容器
4. 配置環境變數和端口映射

**使用範例**：
```powershell
# 使用指定版本
.\scripts\deploy.ps1 1.0.6

# 使用最新版本
.\scripts\deploy.ps1
```

**English**:

Deploys or updates container on a single machine.

**Parameters**:
- `$VERSION`: Docker image version (optional, defaults to latest)

**Actions**:
1. Stop and remove existing container
2. Pull specified image version
3. Create and start new container
4. Configure environment variables and port mappings

#### `docker_sound_analysis_cluster_deploy.ps1` - 集群部署腳本

**繁體中文**：

此腳本用於部署服務到 Docker Swarm 集群。

**參數**：
- `$VERSION`: Docker 映像版本號

**執行內容**：
1. 初始化 Docker Swarm (如果尚未初始化)
2. 創建 overlay 網路
3. 部署服務 stack
4. 配置服務副本數和更新策略
5. 設置健康檢查

**配置選項**：
```powershell
$REPLICAS = 3  # 服務副本數
$NETWORK_NAME = "sound_analysis_network"
```

**使用範例**：
```powershell
.\scripts\docker_sound_analysis_cluster_deploy.ps1 1.0.6
```

**English**:

Deploys service to Docker Swarm cluster.

**Parameters**:
- `$VERSION`: Docker image version

**Actions**:
1. Initialize Docker Swarm if needed
2. Create overlay network
3. Deploy service stack
4. Configure replicas and update strategy
5. Setup health checks

#### `docker_sound_analysis_cluster_delete.ps1` - 集群刪除腳本

**繁體中文**：

此腳本用於從集群中刪除服務。

**執行內容**：
1. 停止所有服務副本
2. 刪除服務定義
3. 清理相關資源

**使用範例**：
```powershell
.\scripts\docker_sound_analysis_cluster_delete.ps1
```

**English**:

Removes service from cluster.

**Actions**:
1. Stop all service replicas
2. Remove service definition
3. Clean up resources

---

## 配置說明 | Configuration

### `config.py` 參數詳解 | Parameter Details

#### MongoDB 配置 | MongoDB Configuration

```python
# 連接 URI | Connection URI
MONGO_URI = os.getenv("MONGO_URI", "mongodb://user:password@host:port")

# 數據庫名稱 | Database name
MONGO_DB = os.getenv("MONGO_DB", "sound_analysis")
```

**繁體中文**：
- `MONGO_URI`: MongoDB 連接字串，包含認證資訊
- `MONGO_DB`: 使用的數據庫名稱

**English**:
- `MONGO_URI`: MongoDB connection string with authentication
- `MONGO_DB`: Database name to use

#### RabbitMQ 配置 | RabbitMQ Configuration

```python
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")

EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "analyze.direct")
QUEUE_NAME = os.getenv("QUEUE_NAME", "analyze.step.sliced_wav_to_4col_AE_Features_324a")
ROUTING_KEY = os.getenv("ROUTING_KEY", "analyze.step.sliced_wav_to_4col_AE_Features_324a")
```

**繁體中文**：
- `EXCHANGE_NAME`: 交換機名稱，類型為 direct
- `QUEUE_NAME`: 佇列名稱
- `ROUTING_KEY`: 路由鍵，用於消息路由

**English**:
- `EXCHANGE_NAME`: Exchange name, type is direct
- `QUEUE_NAME`: Queue name
- `ROUTING_KEY`: Routing key for message routing

#### Flask 配置 | Flask Configuration

```python
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "57122"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
```

**繁體中文**：
- `FLASK_HOST`: 服務監聽地址，0.0.0.0 表示監聽所有介面
- `FLASK_PORT`: 服務端口
- `DEBUG`: 是否啟用調試模式 (生產環境應設為 False)

**English**:
- `FLASK_HOST`: Service listening address, 0.0.0.0 for all interfaces
- `FLASK_PORT`: Service port
- `DEBUG`: Enable debug mode (should be False in production)

#### 處理步驟設定 | Processing Step Configuration

```python
THE_STEP = int(os.getenv("THE_STEP", "4"))
```

**繁體中文**：
此服務在分析流程中的步驟編號，用於在 MongoDB 中標識處理階段。

**English**:
Step number in the analysis pipeline, used to identify processing stage in MongoDB.

#### 分析設定 | Analysis Configuration

```python
ANALYZE_CHUNK_SIZE = int(os.getenv("ANALYZE_CHUNK_SIZE", "1000"))
ANALYZE_MAX_RETRIES = int(os.getenv("ANALYZE_MAX_RETRIES", "3"))
ANALYZE_TIMEOUT = int(os.getenv("ANALYZE_TIMEOUT", "3600"))
```

**繁體中文**：
- `ANALYZE_CHUNK_SIZE`: 處理大量數據時的批次大小
- `ANALYZE_MAX_RETRIES`: 處理失敗時的重試次數
- `ANALYZE_TIMEOUT`: 分析超時時間（秒）

**English**:
- `ANALYZE_CHUNK_SIZE`: Batch size for processing large datasets
- `ANALYZE_MAX_RETRIES`: Number of retries on failure
- `ANALYZE_TIMEOUT`: Analysis timeout in seconds

#### 檔案處理設定 | File Processing Configuration

```python
FILE_UPLOAD_MAX_SIZE = int(os.getenv("FILE_UPLOAD_MAX_SIZE", "104857600"))  # 100MB
ALLOWED_EXTENSIONS = os.getenv("ALLOWED_EXTENSIONS", "wav").split(",")
```

**繁體中文**：
- `FILE_UPLOAD_MAX_SIZE`: 限制上傳檔案大小（位元組）
- `ALLOWED_EXTENSIONS`: 允許的檔案類型

**English**:
- `FILE_UPLOAD_MAX_SIZE`: Upload file size limit in bytes
- `ALLOWED_EXTENSIONS`: Allowed file types

#### 路徑設定 | Path Configuration

```python
PYTHON_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.getenv("TEMP_DIR", os.path.join(PYTHON_PROJECT_ROOT, "temp"))
```

**繁體中文**：
- `PYTHON_PROJECT_ROOT`: 專案根目錄
- `TEMP_DIR`: 臨時檔案存放目錄

**English**:
- `PYTHON_PROJECT_ROOT`: Project root directory
- `TEMP_DIR`: Temporary files directory

#### 效能優化設定 | Performance Configuration

```python
WORKERS = int(os.getenv("WORKERS", "4"))
THREADS = int(os.getenv("THREADS", "2"))
```

**繁體中文**：
- `WORKERS`: 處理進程數
- `THREADS`: 每個進程的線程數

**English**:
- `WORKERS`: Number of worker processes
- `THREADS`: Threads per worker process

---

## 模型訓練指南 | Model Training Guide

### 數據準備 | Data Preparation

#### 數據格式 | Data Format

**繁體中文**：

訓練數據應該是兩個域的特徵數據：

1. **Domain A (CPC 特徵)**：
   - 格式：Tensor of shape `(N, 9)`
   - N: 樣本數量
   - 9: PC1-PC9 特徵維度

2. **Domain B (MA 特徵)**：
   - 格式：Tensor of shape `(M, 9)`
   - M: 樣本數量
   - 9: PC1-PC9 特徵維度

**English**:

Training data should be feature data from two domains:

1. **Domain A (CPC Features)**: Tensor of shape `(N, 9)`
2. **Domain B (MA Features)**: Tensor of shape `(M, 9)`

#### 數據加載範例 | Data Loading Example

```python
import torch
from torch.utils.data import Dataset, DataLoader

class DualDomainDataset(Dataset):
    def __init__(self, domain_a_data, domain_b_data):
        """
        domain_a_data: numpy array of shape (N, 9)
        domain_b_data: numpy array of shape (M, 9)
        """
        self.domain_a = torch.FloatTensor(domain_a_data)
        self.domain_b = torch.FloatTensor(domain_b_data)

        # 正規化
        self.a_mean = torch.mean(self.domain_a, dim=0)
        self.a_std = torch.std(self.domain_a, dim=0)
        self.domain_a = (self.domain_a - self.a_mean) / (self.a_std + 1e-5)

        self.b_mean = torch.mean(self.domain_b, dim=0)
        self.b_std = torch.std(self.domain_b, dim=0)
        self.domain_b = (self.domain_b - self.b_mean) / (self.b_std + 1e-5)

        # 添加位置編碼
        pos_a = torch.linspace(0, 1, len(self.domain_a)).unsqueeze(1)
        pos_b = torch.linspace(0, 1, len(self.domain_b)).unsqueeze(1)

        self.domain_a = torch.cat([self.domain_a, pos_a], dim=1)
        self.domain_b = torch.cat([self.domain_b, pos_b], dim=1)

    def __len__(self):
        return min(len(self.domain_a), len(self.domain_b))

    def __getitem__(self, idx):
        return self.domain_a[idx], self.domain_b[idx % len(self.domain_b)]

# 創建 DataLoader
dataset = DualDomainDataset(cpc_features, ma_features)
dataloader = DataLoader(dataset, batch_size=32, shuffle=True, num_workers=4)
```

### 訓練參數設置 | Training Parameters

#### 超參數配置 | Hyperparameter Configuration

```python
# 模型參數 | Model Parameters
input_dim = 9          # PC 特徵維度
hidden_dim = 256       # 潛在空間維度

# 訓練參數 | Training Parameters
learning_rate = 0.0002  # Adam 學習率
batch_size = 32         # 批次大小
max_epochs = 100        # 最大訓練輪數

# 損失權重 | Loss Weights
mse_weight = 0.1        # MSE 損失權重
cycle_weight = 0.5      # 循環一致性損失權重
adversarial_weight = 0.4  # 對抗損失權重
```

### 完整訓練腳本 | Complete Training Script

```python
import pytorch_lightning as pl
from pytorch_lightning.loggers import TensorBoardLogger
from pytorch_lightning.callbacks import ModelCheckpoint, EarlyStopping
from pl_module import PlMotorModule

# 1. 準備數據
train_dataset = DualDomainDataset(train_cpc, train_ma)
val_dataset = DualDomainDataset(val_cpc, val_ma)

train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True, num_workers=4)
val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False, num_workers=4)

# 2. 創建模型
model = PlMotorModule(pl_set_input_dim=9)

# 3. 設置 Logger
logger = TensorBoardLogger("logs", name="cyclegan_training")

# 4. 設置 Callbacks
checkpoint_callback = ModelCheckpoint(
    dirpath="saves",
    filename="cyclegan-{epoch:02d}-{total_loss:.4f}",
    monitor="total_loss",
    mode="min",
    save_top_k=3
)

early_stopping = EarlyStopping(
    monitor="total_loss",
    patience=10,
    mode="min"
)

# 5. 創建 Trainer
trainer = pl.Trainer(
    max_epochs=100,
    accelerator="gpu" if torch.cuda.is_available() else "cpu",
    devices=1,
    logger=logger,
    callbacks=[checkpoint_callback, early_stopping],
    log_every_n_steps=10,
    check_val_every_n_epoch=1
)

# 6. 開始訓練
trainer.fit(model, train_loader, val_loader)

# 7. 保存最終模型
trainer.save_checkpoint("saves/final_model.ckpt")
print("Training completed! Model saved to saves/final_model.ckpt")
```

### 監控訓練過程 | Monitoring Training

#### 使用 TensorBoard

**繁體中文**：

```bash
# 啟動 TensorBoard
tensorboard --logdir=logs

# 在瀏覽器中訪問
# http://localhost:6006
```

**監控指標**：
- `generator_loss/A_to_B`: Generator A→B 損失
- `generator_loss/B_to_A`: Generator B→A 損失
- `generator_loss/A_to_B_to_A`: 循環損失 A→B→A
- `generator_loss/B_to_A_to_B`: 循環損失 B→A→B
- `discriminator_loss/A`: Discriminator A 損失
- `discriminator_loss/B`: Discriminator B 損失
- `discriminator_acc/A`: Discriminator A 準確率
- `discriminator_acc/B`: Discriminator B 準確率

**English**:

```bash
# Start TensorBoard
tensorboard --logdir=logs

# Access in browser at http://localhost:6006
```

**Metrics to Monitor**:
- Generator losses for both directions
- Cycle consistency losses
- Discriminator losses and accuracies

### 模型評估 | Model Evaluation

#### 評估指標 | Evaluation Metrics

```python
import torch
from sklearn.metrics import mean_squared_error, mean_absolute_error
import numpy as np

def evaluate_model(model, test_loader, device):
    model.eval()
    all_predictions = []
    all_targets = []

    with torch.no_grad():
        for cpc_feat, ma_feat in test_loader:
            cpc_feat = cpc_feat.to(device)
            ma_feat = ma_feat.to(device)

            # 預測
            ma_pred = model.generator_A_to_B(cpc_feat)

            all_predictions.append(ma_pred.cpu().numpy())
            all_targets.append(ma_feat[:, :-1].cpu().numpy())  # 移除位置編碼

    predictions = np.concatenate(all_predictions)
    targets = np.concatenate(all_targets)

    # 計算指標
    mse = mean_squared_error(targets, predictions)
    mae = mean_absolute_error(targets, predictions)
    rmse = np.sqrt(mse)

    print(f"Evaluation Results:")
    print(f"  MSE: {mse:.6f}")
    print(f"  MAE: {mae:.6f}")
    print(f"  RMSE: {rmse:.6f}")

    return {"MSE": mse, "MAE": mae, "RMSE": rmse}

# 使用範例
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = PlMotorModule.load_from_checkpoint("saves/Batchnorm_version.ckpt")
model.to(device)

metrics = evaluate_model(model, test_loader, device)
```

### 模型優化技巧 | Model Optimization Tips

**繁體中文**：

1. **學習率調整**：
   - 使用學習率調度器 (LR Scheduler)
   - 建議使用 ReduceLROnPlateau 或 CosineAnnealingLR

2. **正則化技術**：
   - 可以啟用 Dropout (目前註解掉)
   - 使用 Weight Decay

3. **數據增強**：
   - 添加高斯噪聲
   - 特徵尺度變換

4. **損失權重調整**：
   - 根據驗證集表現調整三個損失的權重
   - MSE、Cycle、Adversarial 的平衡很重要

**English**:

1. **Learning Rate Adjustment**: Use LR schedulers
2. **Regularization**: Enable Dropout, use Weight Decay
3. **Data Augmentation**: Add Gaussian noise, feature scaling
4. **Loss Weight Tuning**: Balance MSE, Cycle, and Adversarial losses

---

## API 文檔 | API Documentation

### Health Check Endpoint

#### `GET /health`

**繁體中文**：

檢查服務健康狀態和基本資訊。

**請求**：
```http
GET /health HTTP/1.1
Host: localhost:57122
```

**回應**：
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "server_name": "customer_R_slice_Extract_Features",
  "instance_id": "a3f7b2c1",
  "queues": "analyze.step.sliced_wav_to_4col_AE_Features_324a"
}
```

**English**:

Check service health status and basic information.

**Request**:
```http
GET /health HTTP/1.1
Host: localhost:57122
```

**Response Fields**:
- `status`: Service status ("healthy" or "unhealthy")
- `version`: Service version
- `server_name`: Server identifier
- `instance_id`: Unique instance ID
- `queues`: RabbitMQ queue name being monitored

### 使用範例 | Usage Examples

#### Python Example

```python
import requests

def check_service_health(host="localhost", port=57122):
    """檢查服務健康狀態 | Check service health"""
    try:
        response = requests.get(f"http://{host}:{port}/health", timeout=5)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Service is {data['status']}")
            print(f"   Version: {data['version']}")
            print(f"   Instance: {data['instance_id']}")
            return True
        else:
            print(f"❌ Service returned status code: {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to connect: {e}")
        return False

# 使用 | Usage
check_service_health()
```

#### cURL Example

```bash
# 基本請求 | Basic request
curl http://localhost:57122/health

# 格式化輸出 | Pretty print
curl -s http://localhost:57122/health | python -m json.tool

# 檢查特定主機 | Check specific host
curl http://192.168.1.100:57122/health

# 包含標頭 | Include headers
curl -i http://localhost:57122/health

# 設置超時 | Set timeout
curl --max-time 5 http://localhost:57122/health
```

---

## 使用範例 | Usage Examples

### CPC 到 MA 轉換完整範例 | Complete CPC to MA Conversion Example

#### 準備輸入數據 | Prepare Input Data

**input.json**:
```json
[
  {
    "equID": 1.0,
    "faultID": "normal",
    "faultValue": 0.0,
    "PC1": -10.523,
    "PC2": 0.142,
    "PC3": 0.591,
    "PC4": -0.305,
    "PC5": 0.087,
    "PC6": 0.031,
    "PC7": 0.045,
    "PC8": 0.092,
    "PC9": -0.023
  },
  {
    "equID": 1.0,
    "faultID": "normal",
    "faultValue": 0.0,
    "PC1": -10.489,
    "PC2": 0.138,
    "PC3": 0.578,
    "PC4": -0.318,
    "PC5": 0.095,
    "PC6": 0.027,
    "PC7": 0.053,
    "PC8": 0.089,
    "PC9": -0.019
  }
]
```

#### 執行轉換 | Execute Conversion

```python
from cpc_to_ma_converter import CPCToMAConverter
import json

# 方法 1: 使用預設配置 | Method 1: Use default config
converter = CPCToMAConverter()
converter.config["input_file"] = "input.json"
converter.config["output_file"] = "output.json"
converter.convert()

# 方法 2: 使用自定義配置檔案 | Method 2: Use custom config
config = {
    "model_path": "saves/Batchnorm_version.ckpt",
    "input_file": "input.json",
    "output_file": "output.json",
    "ma_mean": [-10.458, 0.136, 0.583, -0.311, 0.093, 0.025, 0.051, 0.086, -0.018],
    "ma_std": [0.389, 0.991, 0.408, 0.478, 0.519, 0.381, 0.834, 0.710, 1.124],
    "preserve_metadata": True
}

with open("custom_config.json", "w") as f:
    json.dump(config, f, indent=4)

converter = CPCToMAConverter("custom_config.json")
converter.convert()
```

#### 輸出結果 | Output Result

**output.json**:
```json
[
  {
    "equID": 1.0,
    "faultID": "normal",
    "faultValue": 0.0,
    "PC1": -10.501,
    "PC2": 0.145,
    "PC3": 0.586,
    "PC4": -0.308,
    "PC5": 0.091,
    "PC6": 0.028,
    "PC7": 0.049,
    "PC8": 0.090,
    "PC9": -0.021
  }
]
```

### 完整工作流程範例 | Complete Workflow Example

#### 1. 上傳音訊檔案並提交任務 | Upload Audio and Submit Task

```python
import json
import pika
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId
import uuid

# 連接 MongoDB
client = MongoClient("mongodb://user:password@host:port")
db = client["sound_analysis"]
fs = GridFS(db)

# 生成分析 UUID
analyze_uuid = str(uuid.uuid4())

# 1. 上傳音訊檔案到 GridFS
with open("audio_sample.wav", "rb") as audio_file:
    file_id = fs.put(
        audio_file.read(),
        filename="audio_sample.wav",
        metadata={"AnalyzeUUID": analyze_uuid}
    )

print(f"✅ Audio file uploaded. File ID: {file_id}")

# 2. 創建分析任務記錄
analysis_doc = {
    "AnalyzeUUID": analyze_uuid,
    "AnalyzeState": "registered",
    "files": {
        "csv_transform": {
            "fileId": file_id,
            "filename": "audio_sample.wav",
            "type": "wav"
        }
    },
    "analyze_features": [
        {
            "features_step": 4,
            "features_state": "pending",
            "features_data": []
        }
    ]
}

db.analyses.insert_one(analysis_doc)
print(f"✅ Analysis task created. UUID: {analyze_uuid}")

# 3. 發送任務消息到 RabbitMQ
connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host="rabbitmq-host",
        port=5672,
        credentials=pika.PlainCredentials("user", "password")
    )
)
channel = connection.channel()

message = {
    "AnalyzeUUID": analyze_uuid,
    "step": 4
}

channel.basic_publish(
    exchange="analyze.direct",
    routing_key="analyze.step.sliced_wav_to_4col_AE_Features_324a",
    body=json.dumps(message)
)

connection.close()
print(f"✅ Task message sent to RabbitMQ")
```

#### 2. 查詢處理狀態 | Query Processing Status

```python
import time

def check_task_status(analyze_uuid, db):
    """查詢任務處理狀態 | Check task processing status"""

    while True:
        analysis = db.analyses.find_one({"AnalyzeUUID": analyze_uuid})

        if not analysis:
            print("❌ Task not found")
            return None

        step_4 = next((s for s in analysis["analyze_features"] if s["features_step"] == 4), None)

        if not step_4:
            print("❌ Step 4 not found")
            return None

        state = step_4["features_state"]
        print(f"📊 Task status: {state}")

        if state == "completed":
            print("✅ Task completed successfully!")
            return step_4["features_data"]

        elif state == "error":
            error_msg = step_4.get("error_message", "Unknown error")
            print(f"❌ Task failed: {error_msg}")
            return None

        elif state in ["pending", "processing"]:
            print(f"⏳ Task is {state}, waiting...")
            time.sleep(5)
            continue

        else:
            print(f"⚠️ Unknown status: {state}")
            return None

# 使用 | Usage
results = check_task_status(analyze_uuid, db)

if results:
    print(f"📊 Received {len(results)} feature records")
    print(f"Sample result: {results[0]}")
```

#### 3. 執行 CPC 到 MA 轉換 | Execute CPC to MA Conversion

```python
# 將結果轉換為 CPC to MA converter 可以使用的格式
import json

# 保存特徵數據
with open("cpc_features.json", "w") as f:
    json.dump(results, f, indent=4)

# 執行轉換
from cpc_to_ma_converter import CPCToMAConverter

converter = CPCToMAConverter()
converter.config["input_file"] = "cpc_features.json"
converter.config["output_file"] = "ma_features.json"
converter.convert()

# 讀取結果
with open("ma_features.json", "r") as f:
    ma_features = json.load(f)

print(f"✅ Conversion completed!")
print(f"📊 Generated {len(ma_features)} MA features")
```

### 批次處理範例 | Batch Processing Example

```python
import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def process_single_file(input_file):
    """處理單個檔案 | Process single file"""
    try:
        output_file = input_file.replace("input", "output")

        converter = CPCToMAConverter()
        converter.config["input_file"] = input_file
        converter.config["output_file"] = output_file
        converter.convert()

        return {"status": "success", "file": input_file}

    except Exception as e:
        return {"status": "error", "file": input_file, "error": str(e)}

def batch_process_files(input_dir, max_workers=4):
    """批次處理多個檔案 | Batch process multiple files"""

    # 獲取所有輸入檔案
    input_files = glob.glob(os.path.join(input_dir, "*.json"))
    print(f"📁 Found {len(input_files)} files to process")

    results = []

    # 使用線程池處理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_file, f): f for f in input_files}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

            if result["status"] == "success":
                print(f"✅ Processed: {result['file']}")
            else:
                print(f"❌ Failed: {result['file']} - {result['error']}")

    # 統計結果
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = len(results) - success_count

    print(f"\n📊 Batch processing completed:")
    print(f"   Success: {success_count}")
    print(f"   Failed: {error_count}")

    return results

# 使用 | Usage
results = batch_process_files("./input_data", max_workers=4)
```

---

## 開發指南 | Development Guide

### 開發環境配置 | Development Environment Setup

#### 1. IDE 設置 | IDE Setup

**繁體中文**：

推薦使用 PyCharm 或 VS Code：

**PyCharm**:
- 安裝 Python 插件
- 配置 Python 解釋器為虛擬環境
- 啟用 Type Hints 檢查

**VS Code**:
- 安裝 Python 擴展
- 安裝 PyTorch 擴展
- 配置 Pylint 和 Black 格式化

**English**:

Recommended IDEs: PyCharm or VS Code

#### 2. 代碼風格 | Code Style

```python
# 使用 Black 格式化
pip install black
black .

# 使用 Pylint 檢查
pip install pylint
pylint *.py

# 使用 mypy 類型檢查
pip install mypy
mypy *.py
```

### 添加新功能 | Adding New Features

#### 範例：添加新的生成器架構 | Example: Add New Generator Architecture

```python
# 在 cycleGan_model.py 中添加新模型
class MotorGeneratorConv(nn.Module):
    """基於卷積的生成器 | Convolution-based Generator"""

    def __init__(self, input_dim=9, hidden_dim=256):
        super().__init__()
        actual_input_dim = input_dim + 1

        # 將 1D 特徵重塑為 2D 以使用卷積
        self.encoder = nn.Sequential(
            nn.Conv1d(1, 64, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2),
            nn.BatchNorm1d(64),
            nn.Conv1d(64, 128, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2),
            nn.BatchNorm1d(128),
        )

        self.decoder = nn.Sequential(
            nn.ConvTranspose1d(128, 64, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2),
            nn.BatchNorm1d(64),
            nn.ConvTranspose1d(64, 1, kernel_size=3, padding=1),
            nn.Tanh()
        )

    def forward(self, x):
        # x shape: (batch, 10)
        x = x.unsqueeze(1)  # (batch, 1, 10)
        x = self.encoder(x)
        x = self.decoder(x)
        x = x.squeeze(1)  # (batch, 10)
        return x[:, :-1]  # 移除位置編碼

# 在 pl_module.py 中使用新模型
from cycleGan_model import MotorGeneratorConv

class PlMotorModuleConv(pl.LightningModule):
    def __init__(self, pl_set_input_dim=9):
        super().__init__()
        self.automatic_optimization = False

        # 使用新的卷積生成器
        self.generator_A_to_B = MotorGeneratorConv(input_dim=pl_set_input_dim)
        self.generator_B_to_A = MotorGeneratorConv(input_dim=pl_set_input_dim)

        # 其他代碼保持不變
        ...
```

### 調試技巧 | Debugging Tips

#### 1. 啟用詳細日誌 | Enable Verbose Logging

```python
import logging

# 設置日誌級別為 DEBUG
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.debug("This is a debug message")
```

#### 2. 使用 PyTorch 的調試工具 | Use PyTorch Debug Tools

```python
import torch

# 啟用 anomaly detection
torch.autograd.set_detect_anomaly(True)

# 檢查梯度
def check_gradients(model):
    for name, param in model.named_parameters():
        if param.grad is not None:
            print(f"{name}: grad_norm={param.grad.norm()}")
        else:
            print(f"{name}: no gradient")

# 在訓練循環中調用
check_gradients(model)
```

#### 3. 可視化特徵 | Visualize Features

```python
import matplotlib.pyplot as plt
import numpy as np

def visualize_features(cpc_features, ma_features, sample_idx=0):
    """可視化 CPC 和 MA 特徵 | Visualize CPC and MA features"""

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # CPC 特徵
    axes[0].bar(range(9), cpc_features[sample_idx])
    axes[0].set_title("CPC Features")
    axes[0].set_xlabel("Feature Index")
    axes[0].set_ylabel("Value")

    # MA 特徵
    axes[1].bar(range(9), ma_features[sample_idx])
    axes[1].set_title("MA Features")
    axes[1].set_xlabel("Feature Index")
    axes[1].set_ylabel("Value")

    plt.tight_layout()
    plt.savefig("feature_comparison.png")
    plt.show()

# 使用
visualize_features(cpc_data, ma_data, sample_idx=0)
```

---

## 故障排除 | Troubleshooting

### 常見問題 | Common Issues

#### 1. R 環境錯誤 | R Environment Error

**問題 Problem**:
```
Error: R environment initialization failed
```

**解決方案 Solution**:

**繁體中文**:
1. 確認 R 已正確安裝
2. 檢查 rpy2 版本是否兼容
3. 驗證 R 套件是否完整安裝

```bash
# 檢查 R 版本
R --version

# 重新安裝 R 套件
Rscript install_r_packages.R

# 測試 rpy2
python -c "import rpy2.robjects as robjects; print('rpy2 OK')"
```

**English**:
1. Verify R is properly installed
2. Check rpy2 version compatibility
3. Verify R packages are fully installed

#### 2. MongoDB 連接失敗 | MongoDB Connection Failed

**問題 Problem**:
```
pymongo.errors.ServerSelectionTimeoutError
```

**解決方案 Solution**:

```python
# 檢查連接字串
from pymongo import MongoClient

try:
    client = MongoClient("mongodb://user:password@host:port", serverSelectionTimeoutMS=5000)
    client.server_info()
    print("✅ MongoDB connection successful")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
```

**繁體中文檢查清單**:
- [ ] 確認 MongoDB 服務正在運行
- [ ] 檢查連接字串中的用戶名和密碼
- [ ] 驗證網路連接和防火牆設置
- [ ] 檢查 MongoDB 版本兼容性

**English Checklist**:
- [ ] Verify MongoDB service is running
- [ ] Check username and password in connection string
- [ ] Verify network connectivity and firewall settings
- [ ] Check MongoDB version compatibility

#### 3. RabbitMQ 消息未被消費 | RabbitMQ Messages Not Consumed

**問題 Problem**:
```
Messages are queued but not being processed
```

**解決方案 Solution**:

**繁體中文**:

1. 檢查 Consumer 是否正在運行
2. 驗證 Routing Key 是否正確
3. 檢查 Queue 綁定

```bash
# 使用 RabbitMQ 管理介面
# http://rabbitmq-host:15672

# 或使用命令行工具
rabbitmqctl list_queues
rabbitmqctl list_bindings
```

**English**:

1. Check if consumer is running
2. Verify routing key is correct
3. Check queue binding

#### 4. CUDA 記憶體不足 | CUDA Out of Memory

**問題 Problem**:
```
RuntimeError: CUDA out of memory
```

**解決方案 Solution**:

```python
# 方法 1: 減少 batch size
batch_size = 16  # 從 32 減少到 16

# 方法 2: 清理 GPU 緩存
import torch
torch.cuda.empty_cache()

# 方法 3: 使用 CPU
device = torch.device("cpu")
model.to(device)

# 方法 4: 啟用梯度檢查點 (Gradient Checkpointing)
# 在模型中添加
torch.utils.checkpoint.checkpoint(module, input)
```

#### 5. 模型轉換結果異常 | Model Conversion Results Abnormal

**問題 Problem**:
```
Converted features have extreme values or NaN
```

**解決方案 Solution**:

```python
# 檢查數據分佈
import numpy as np

def check_data_quality(data, name="Data"):
    """檢查數據質量 | Check data quality"""
    print(f"\n{name} Quality Check:")
    print(f"  Shape: {data.shape}")
    print(f"  Mean: {np.mean(data, axis=0)}")
    print(f"  Std: {np.std(data, axis=0)}")
    print(f"  Min: {np.min(data, axis=0)}")
    print(f"  Max: {np.max(data, axis=0)}")
    print(f"  NaN count: {np.isnan(data).sum()}")
    print(f"  Inf count: {np.isinf(data).sum()}")

check_data_quality(cpc_features, "CPC Features")
check_data_quality(ma_features, "MA Features")

# 修正異常值
def fix_abnormal_values(data, clip_range=(-100, 100)):
    """修正異常值 | Fix abnormal values"""
    # 替換 NaN 和 Inf
    data = np.nan_to_num(data, nan=0.0, posinf=clip_range[1], neginf=clip_range[0])

    # 裁剪極端值
    data = np.clip(data, clip_range[0], clip_range[1])

    return data

ma_features = fix_abnormal_values(ma_features)
```

### 日誌查看 | Log Viewing

#### 應用程式日誌 | Application Logs

```bash
# Docker 容器日誌
docker logs py_cyclegan

# 持續跟蹤日誌
docker logs -f py_cyclegan

# 查看最近 100 行
docker logs --tail 100 py_cyclegan

# 查看特定時間範圍
docker logs --since 2024-01-01T00:00:00 py_cyclegan
```

#### 訓練日誌 | Training Logs

```bash
# TensorBoard 日誌
tensorboard --logdir=logs --host=0.0.0.0 --port=6006

# 查看 Lightning 日誌
cat logs/cyclegan_training/version_0/metrics.csv
```

---

## 維護與升級 | Maintenance

### 版本更新流程 | Version Update Process

**繁體中文**：

1. **更新代碼**：
   ```bash
   git pull origin master
   ```

2. **更新 Dockerfile 版本**：
   ```dockerfile
   ENV SERVER_VISION=1.0.7
   ```

3. **構建新映像**：
   ```powershell
   .\scripts\build.ps1 1.0.7
   ```

4. **更新部署**：
   ```powershell
   .\scripts\deploy.ps1 1.0.7
   ```

5. **驗證更新**：
   ```bash
   curl http://localhost:57122/health
   ```

**English**:

1. **Update Code**: Pull latest changes
2. **Update Dockerfile Version**: Modify SERVER_VISION
3. **Build New Image**: Run build script
4. **Update Deployment**: Run deploy script
5. **Verify Update**: Check health endpoint

### 數據備份 | Data Backup

#### MongoDB 備份 | MongoDB Backup

```bash
# 完整備份
mongodump --uri="mongodb://user:password@host:port/sound_analysis" --out=/backup/$(date +%Y%m%d)

# 僅備份特定集合
mongodump --uri="mongodb://user:password@host:port/sound_analysis" --collection=analyses --out=/backup/analyses_$(date +%Y%m%d)

# 恢復備份
mongorestore --uri="mongodb://user:password@host:port/sound_analysis" /backup/20240101
```

#### 模型備份 | Model Backup

```bash
# 備份模型檢查點
tar -czf model_backup_$(date +%Y%m%d).tar.gz saves/

# 上傳到雲端存儲 (範例)
aws s3 cp model_backup_20240101.tar.gz s3://my-bucket/backups/
```

### 效能優化 | Performance Optimization

#### 1. 數據庫優化 | Database Optimization

```javascript
// MongoDB 索引創建
db.analyses.createIndex({ "AnalyzeUUID": 1 })
db.analyses.createIndex({ "analyze_features.features_step": 1 })
db.analyses.createIndex({ "AnalyzeState": 1 })

// 檢查索引使用情況
db.analyses.explain("executionStats").find({"AnalyzeUUID": "some-uuid"})
```

#### 2. 模型推理優化 | Model Inference Optimization

```python
# 使用 TorchScript 優化
import torch

model = PlMotorModule.load_from_checkpoint("saves/Batchnorm_version.ckpt")
model.eval()

# 轉換為 TorchScript
scripted_model = torch.jit.script(model.generator_A_to_B)
torch.jit.save(scripted_model, "saves/generator_scripted.pt")

# 載入並使用
scripted_model = torch.jit.load("saves/generator_scripted.pt")
output = scripted_model(input_tensor)
```

#### 3. RabbitMQ 優化 | RabbitMQ Optimization

```python
# 增加 prefetch count 以提高吞吐量
channel.basic_qos(prefetch_count=10)

# 使用批次確認
channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

# 在處理多條消息後批次確認
if message_count % 10 == 0:
    channel.basic_ack(delivery_tag=method.delivery_tag, multiple=True)
```

---

## 貢獻指南 | Contributing

### 如何貢獻 | How to Contribute

**繁體中文**：

1. Fork 本專案
2. 創建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

**English**:

1. Fork the project
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

### 代碼規範 | Code Standards

- 遵循 PEP 8 風格指南
- 添加適當的註解和文檔字串
- 編寫單元測試
- 確保所有測試通過

**Follow PEP 8, add comments, write tests, ensure tests pass**

---

## 授權 | License

本專案採用 MIT 授權。

This project is licensed under the MIT License.

---

## 聯絡方式 | Contact

如有問題或建議，請通過以下方式聯繫：

For questions or suggestions, please contact:

- **Email**: [your-email@example.com](mailto:your-email@example.com)
- **Issue Tracker**: [GitHub Issues](https://github.com/your-repo/issues)

---

**最後更新 Last Updated**: 2025-10-27
**文檔版本 Document Version**: 1.0.0
