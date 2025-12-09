# a_sub_system/train/py_cyclegan/config.py - CycleGAN 訓練系統統一配置

import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# ==================== MongoDB 配置 ====================
# 用於從 analysis_service 讀取 LEAF 特徵

_train_mongo_port = os.getenv('TRAIN_MONGODB_PORT')
_mongo_port = int(_train_mongo_port or os.getenv('MONGODB_PORT', '55101'))
_mongo_host = os.getenv('MONGODB_HOST', 'localhost')
_mongo_username = os.getenv('MONGODB_USERNAME', 'web_ui')
_mongo_password = os.getenv('MONGODB_PASSWORD', 'hod2iddfsgsrl')

MONGODB_CONFIG = {
    'host': _mongo_host,
    'port': _mongo_port,
    'username': _mongo_username,
    'password': _mongo_password,
    'database': os.getenv('MONGODB_DATABASE', 'web_db'),
    'collection': os.getenv('MONGODB_COLLECTION', 'recordings'),

    # MongoDB URI（自動組合）
    'uri': os.getenv(
        'MONGODB_URI',
        f'mongodb://{_mongo_username}:{_mongo_password}@{_mongo_host}:{_mongo_port}'
    )
}

# ==================== 數據配置 ====================

DATA_CONFIG = {
    'source': os.getenv('DATA_SOURCE', 'mongodb'),  # mongodb 或 file

    # Domain A 配置（設備 A）
    'domain_a': {
        'mongo_query': {
            'info_features.device_id': os.getenv('DOMAIN_A_DEVICE_ID', 'cpc006'),
            'analysis_status': 'completed'
        },
        'max_samples': int(os.getenv('DOMAIN_A_MAX_SAMPLES', '50000')),  # 增加到 10000
        'file_path': os.getenv('DOMAIN_A_FILE_PATH', 'data/domain_cpc006.json')  # 當使用 file source 時
    },

    # Domain B 配置（設備 B）
    'domain_b': {
        'mongo_query': {
            'info_features.device_id': {
                '$in': [
                    os.getenv('DOMAIN_B_DEVICE_ID_NORMAL', 'BATCH_UPLOAD_NORMAL')
                ]
            },
            'analysis_status': 'completed','info_features.label': 'normal'

        },
        'max_samples': int(os.getenv('DOMAIN_B_MAX_SAMPLES', '50000')),
        #'file_path': os.getenv('DOMAIN_B_FILE_PATH', 'data/domain_mimii.json')
        'file_path': os.getenv('DOMAIN_B_PROD_FILE_PATH', 'data/domain_mimii_prod.json') # <-- 訓練專用
    },

    # 預處理配置
    'preprocessing': {
        'normalize': True,
        'augment': os.getenv('DATA_AUGMENT', 'true').lower() == 'true',
        'max_sequence_length': int(os.getenv('MAX_SEQUENCE_LENGTH', '100'))
    }
}

# ==================== 模型配置 ====================

MODEL_CONFIG = {
    'input_dim': 40,  # LEAF 特徵維度

    # 生成器配置
    'generator': {
        'hidden_dims': [128, 256, 128],
        'n_residual_blocks': 3,
        'dropout': 0.1,
        'use_batch_norm': True
    },

    # 判別器配置
    'discriminator': {
        'hidden_dims': [128, 256, 128],
        'dropout': 0.2,
        'use_batch_norm': True
    }
}

# ==================== 訓練配置 ====================

TRAINING_CONFIG = {
    # 基本參數
    'max_epochs': int(os.getenv('MAX_EPOCHS', '200')),
    'batch_size': int(os.getenv('BATCH_SIZE', '32')),
    'num_workers': int(os.getenv('NUM_WORKERS', '0')),

    # 優化器參數（新增分離學習率）
    'lr_g': float(os.getenv('LR_G', '0.0004')),
    'lr_d': float(os.getenv('LR_D', '0.0001')),
    'beta1': 0.5,
    'beta2': 0.999,

    # 損失權重
    'lambda_cycle': float(os.getenv('LAMBDA_CYCLE', '10.0')),
    'lambda_identity': float(os.getenv('LAMBDA_IDENTITY', '5.0')),
    'use_identity_loss': True,

    # 學習率調度器
    'scheduler': {
        'type': os.getenv('SCHEDULER_TYPE', 'cosine'),
        'warmup_epochs': int(os.getenv('WARMUP_EPOCHS', '10'))
    },

    # 檢查點配置
    'checkpoint': {
        'save_dir': os.getenv('CHECKPOINT_DIR', 'checkpoints'),
        'save_top_k': 3,
        'monitor': 'val/cycle_A',
        'mode': 'min'
    },

    # 早停配置（你目前是關掉的）
    'early_stopping': {
        'enabled': os.getenv('EARLY_STOPPING', 'false').lower() == 'true',
        'patience': int(os.getenv('EARLY_STOPPING_PATIENCE', '80')),
        'monitor': 'val/cycle_A',
        'mode': 'min'
    }
}


# ==================== 驗證配置 ====================

VALIDATION_CONFIG = {
    'val_split': float(os.getenv('VAL_SPLIT', '0.1')),
    'check_val_every_n_epoch': int(os.getenv('CHECK_VAL_EVERY_N_EPOCH', '1'))
}

# ==================== 日誌配置 ====================

LOGGING_CONFIG = {
    'log_dir': os.getenv('LOG_DIR', 'logs'),
    'log_every_n_steps': int(os.getenv('LOG_EVERY_N_STEPS', '10')),
    'tensorboard': True,

    # 日誌級別
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'log_file': os.getenv('LOG_FILE', 'logs/train.log'),
    'max_bytes': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5
}

# ==================== 硬件配置 ====================

HARDWARE_CONFIG = {
    'accelerator': os.getenv('ACCELERATOR', 'gpu'),  # gpu 或 cpu
    'devices': int(os.getenv('DEVICES', '1')),
    'precision': os.getenv('PRECISION', '32')  # 32 或 16
}

# ==================== 推理配置 ====================

INFERENCE_CONFIG = {
    'batch_size': int(os.getenv('INFERENCE_BATCH_SIZE', '64')),
    'device': os.getenv('INFERENCE_DEVICE', 'cuda'),
    'output_dir': os.getenv('OUTPUT_DIR', 'outputs')
}

# ==================== 評估配置 ====================

EVALUATION_CONFIG = {
    'metrics': ['mmd', 'frechet_distance'],
    'mmd_kernel': 'rbf',
    'mmd_gamma': 1.0
}

# ==================== 路徑配置 ====================

# 項目根目錄
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / 'data'
MODELS_DIR = PROJECT_ROOT / 'models'
CHECKPOINTS_DIR = PROJECT_ROOT / TRAINING_CONFIG['checkpoint']['save_dir']
LOGS_DIR = PROJECT_ROOT / LOGGING_CONFIG['log_dir']
OUTPUTS_DIR = PROJECT_ROOT / INFERENCE_CONFIG['output_dir']

# 創建必要的目錄
for directory in [DATA_DIR, CHECKPOINTS_DIR, LOGS_DIR, OUTPUTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ==================== 完整配置字典 ====================

CONFIG = {
    'mongodb': MONGODB_CONFIG,
    'data': DATA_CONFIG,
    'model': MODEL_CONFIG,
    'training': TRAINING_CONFIG,
    'validation': VALIDATION_CONFIG,
    'logging': LOGGING_CONFIG,
    'hardware': HARDWARE_CONFIG,
    'inference': INFERENCE_CONFIG,
    'evaluation': EVALUATION_CONFIG,
}


# ==================== 配置驗證函數 ====================

def validate_config():
    """驗證配置的有效性"""
    errors = []

    # 驗證 MongoDB 配置
    if DATA_CONFIG['source'] == 'mongodb':
        if not MONGODB_CONFIG['uri']:
            errors.append("MongoDB URI is required when data source is mongodb")

    # 驗證數據配置
    if DATA_CONFIG['domain_a']['max_samples'] <= 0:
        errors.append("Domain A max_samples must be positive")

    if DATA_CONFIG['domain_b']['max_samples'] <= 0:
        errors.append("Domain B max_samples must be positive")

    # 驗證訓練配置
    if TRAINING_CONFIG['batch_size'] <= 0:
        errors.append("Batch size must be positive")

    if TRAINING_CONFIG['max_epochs'] <= 0:
        errors.append("Max epochs must be positive")

    # 驗證硬件配置
    if HARDWARE_CONFIG['accelerator'] not in ['cpu', 'gpu', 'tpu']:
        errors.append("Accelerator must be one of: cpu, gpu, tpu")

    if errors:
        raise ValueError(f"Configuration validation failed:\n" + "\n".join(f"- {e}" for e in errors))

    return True


def print_config():
    """打印當前配置（用於調試）"""
    import json
    print("=" * 60)
    print("CycleGAN Training Configuration")
    print("=" * 60)

    for section, config in CONFIG.items():
        print(f"\n[{section.upper()}]")
        print(json.dumps(config, indent=2, default=str))

    print("\n" + "=" * 60)


if __name__ == "__main__":
    # 測試配置
    print_config()

    # 驗證配置
    try:
        validate_config()
        print("\n✅ Configuration validation passed!")
    except ValueError as e:
        print(f"\n❌ Configuration validation failed:\n{e}")
