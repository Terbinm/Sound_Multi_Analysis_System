# a_sub_system/analysis_service/config.py - 分析服務統一配置（加入 Step 0）

import os
import torch
from dotenv import load_dotenv
from typing import Dict, Any

BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
ENV_PATH = os.path.join(BASE_DIR, ".env")

print(">>> loading env from:", ENV_PATH)
load_dotenv(ENV_PATH, override=True)

MONGODB_CONFIG: Dict[str, Any] = {
    'host': os.getenv("MONGODB_HOST"),
    'port': int(os.getenv("MONGODB_PORT")),
    'username': os.getenv("MONGODB_USERNAME"),
    'password': os.getenv("MONGODB_PASSWORD"),
    'database': os.getenv("MONGODB_DATABASE"),
    'collection': os.getenv("MONGODB_COLLECTION")
}

# ==================== 音訊處理配置 ====================
AUDIO_CONFIG = {
    # 切割參數（參考 V3_multi_dataset）
    'slice_duration': 0.16,  # 切割時長（秒）
    'slice_interval': 0.20,  # 切割間隔（秒）
    'channels': [1],  # 預設處理的通道列表（當 target_channel 未指定時使用）
    'sample_rate': 16000,  # 採樣率（Hz）
    'min_segment_duration': 0.05  # 最小切片長度（秒）
}

# ==================== 轉檔配置（Step 0）====================
CONVERSION_CONFIG = {
    # 支援的輸入格式
    'supported_input_formats': ['.wav', '.csv'],

    # CSV 轉檔設定
    'csv_header': None,  # CSV 檔案是否有標題行（None 表示無標題）
    'csv_normalize': True,  # 是否自動正規化超出範圍的數值

    # 輸出設定
    'output_format': '.wav',
    'output_sample_rate': 16000  # 使用與 AUDIO_CONFIG 相同的採樣率
}

# ==================== LEAF 特徵提取配置 ====================
LEAF_CONFIG = {
    # LEAF 前端參數
    'n_filters': 40,
    'sample_rate': 16000,
    'window_len': 25.0,  # 毫秒
    'window_stride': 10.0,  # 毫秒
    'pcen_compression': True,
    'init_min_freq': 60.0,
    'init_max_freq': 8000.0,

    # 處理參數
    'batch_size': 32,
    'device': 'cuda' if torch.cuda.is_available() else 'cpu',  # 使用 GPU
    'num_workers': 4,

    # 特徵配置
    'feature_dim_expected': 40,
    'normalize_features': False,
    'feature_dtype': 'float32'
}

# ==================== 分類配置 ====================
CLASSIFICATION_CONFIG = {
    'default_method': 'random',  # 預設採用隨機分類（安全模式，不需要模型）
    'support_list': ['random', 'rf_model', 'cyclegan_rf'],
    'use_model': False,  # 預設不啟用模型
    'classes': ['normal', 'abnormal'],
    'normal_probability': 0.7,
    'model_path': None,  # 預設不指定本地路徑，由配置決定
    'threshold': 0.5,
    'cyclegan_checkpoint': None,  # 由配置決定
    'cyclegan_direction': 'AB',
    'cyclegan_device': 'cpu',
    'cyclegan_normalization_path': None,  # 由配置決定
    'apply_normalization': True,
    'scaler_path': None,
    'rf_aggregation': None,
}

# ==================== 模型需求定義 ====================
# 模型需求現在統一由 config_schema.py 管理
# 此處提供向後相容的匯入
from config_schema import get_all_model_requirements, get_analysis_config_schema

# 向後相容：MODEL_REQUIREMENTS 現在從 config_schema 動態生成
MODEL_REQUIREMENTS = get_all_model_requirements()

# ==================== 模型快取配置 ====================
MODEL_CACHE_CONFIG = {
    'cache_dir': os.path.join(BASE_DIR, 'sub_system', 'analysis_service', 'model_cache'),
    'auto_download': True,  # 啟動時自動下載缺失模型
    'max_cache_size_mb': 2048,  # 最大快取大小 (MB)
}

# ==================== 服務配置 ====================
SERVICE_CONFIG = {
    # Change Stream 配置
    'use_change_stream': False,
    'polling_interval': 5,  # 輪詢間隔（秒），當 Change Stream 不可用時
    'analysis_Method_ID': "WAV_LEAF_RF_v1",  # 輪詢間隔（秒），當 Change Stream 不可用時

    # 處理配置
    'max_concurrent_tasks': 3,  # 最大並行處理任務數
    'retry_attempts': 3,  # 失敗重試次數
    'retry_delay': 2,  # 重試延遲（秒）

    # 超時配置
    'conversion_timeout': 60,  # 轉檔超時（秒）
    'slice_timeout': 60,  # 切割超時（秒）
    'leaf_timeout': 120,  # LEAF 提取超時（秒）
    'classify_timeout': 30  # 分類超時（秒）
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== 日誌配置 ====================
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(levelname)s - AnalyzeUUID:%(analyze_uuid)s - %(message)s',
    'log_file': 'analysis_service.log',
    'log_dir': os.path.join(BASE_DIR, 'logs'),
    'max_bytes': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5,
    'timestamp_format': '%Y%m%d_%H%M%S'
}

# ==================== 處理步驟定義 ====================
PROCESSING_STEPS = {
    0: {'name': 'Audio Conversion', 'description': '音訊轉檔（CSV->WAV）'},
    1: {'name': 'Audio Slicing', 'description': '音訊切割'},
    2: {'name': 'LEAF Features', 'description': 'LEAF 特徵提取'},
    3: {'name': 'Classification', 'description': '分類預測'},
    4: {'name': 'Completed', 'description': '處理完成'}
}

# ==================== GridFS 配置 ====================
# 分析服務使用 GridFS 讀取音頻文件
USE_GRIDFS = True  # 啟用 GridFS 模式

# ==================== 檔案路徑配置（已棄用，保留用於向後相容） ====================
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')

# ==================== 資料庫索引 ====================
DATABASE_INDEXES = [
    'AnalyzeUUID',
    'info_features.device_id',
    'analyze_features.active_analysis_id'  # 用於查找待處理記錄
]

# ==================== RabbitMQ 配置 (V2) ====================
RABBITMQ_CONFIG = {
    'host': os.getenv('RABBITMQ_HOST', 'localhost'),
    'port': int(os.getenv('RABBITMQ_PORT', '55102')),  # 核心服務 RabbitMQ 端口
    'username': os.getenv('RABBITMQ_USERNAME', 'admin'),
    'password': os.getenv('RABBITMQ_PASSWORD', 'rabbitmq_admin_pass'),
    'virtual_host': os.getenv('RABBITMQ_VHOST', '/'),
    'exchange': os.getenv('RABBITMQ_EXCHANGE', 'analysis_tasks_exchange'),
    'queue': os.getenv('RABBITMQ_QUEUE', 'analysis_tasks_queue'),
    'routing_key': os.getenv('RABBITMQ_ROUTING_KEY', 'analysis.#'),
    'message_ttl_ms': int(os.getenv('RABBITMQ_MESSAGE_TTL_MS', '86400000')),
    'prefetch_count': 1,  # 每次只處理一個任務
    'max_retries': 3  # 最大重試次數
}

# ==================== 狀態管理系統配置 (V2) ====================
STATE_MANAGEMENT_CONFIG = {
    'url': os.getenv('STATE_MANAGEMENT_URL', 'http://localhost:55103'),  # 核心服務狀態管理端口
    'timeout': int(os.getenv('STATE_MANAGEMENT_TIMEOUT', '10')),
    # 可透過環境變數指定固定節點 ID（優先於自動生成）
    'node_id': os.getenv('STATE_MANAGEMENT_NODE_ID') or os.getenv('ANALYSIS_NODE_ID'),
    # 可選：覆寫節點 ID 儲存檔案路徑
    'node_id_file': os.getenv('STATE_MANAGEMENT_NODE_ID_FILE')
}
