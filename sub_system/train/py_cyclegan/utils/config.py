"""Configuration Management

使用 Python 字典配置，與 analysis_service 保持一致
"""

from pathlib import Path
import sys

# 添加項目根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import config as default_config


def get_config():
    """
    獲取配置字典

    Returns:
        完整的配置字典
    """
    return default_config.CONFIG


def get_mongodb_config():
    """獲取 MongoDB 配置"""
    return default_config.MONGODB_CONFIG


def get_data_config():
    """獲取數據配置"""
    return default_config.DATA_CONFIG


def get_model_config():
    """獲取模型配置"""
    return default_config.MODEL_CONFIG


def get_training_config():
    """獲取訓練配置"""
    return default_config.TRAINING_CONFIG


def get_validation_config():
    """獲取驗證配置"""
    return default_config.VALIDATION_CONFIG


def get_logging_config():
    """獲取日誌配置"""
    return default_config.LOGGING_CONFIG


def get_hardware_config():
    """獲取硬件配置"""
    return default_config.HARDWARE_CONFIG


def get_inference_config():
    """獲取推理配置"""
    return default_config.INFERENCE_CONFIG


def get_evaluation_config():
    """獲取評估配置"""
    return default_config.EVALUATION_CONFIG

def get_runtime_config():
    """取得執行時服務配置"""
    return default_config.RUNTIME_CONFIG


def get_server_metadata():
    """取得服務基礎資訊"""
    return default_config.SERVER_METADATA


def get_worker_config():
    """取得工作者參數"""
    return default_config.WORKER_CONFIG


def get_file_storage_config():
    """取得檔案處理配置"""
    return default_config.FILE_STORAGE_CONFIG


def get_rabbitmq_config():
    """取得 RabbitMQ 配置"""
    return default_config.RABBITMQ_CONFIG


def get_flask_config():
    """取得 Flask 服務配置"""
    return default_config.FLASK_CONFIG


def get_processing_step_config():
    """取得目標步驟配置"""
    return default_config.PROCESSING_STEP_CONFIG


def get_service_logging_config():
    """取得服務日誌配置"""
    return default_config.SERVICE_LOGGING_CONFIG



def validate_config():
    """驗證配置"""
    return default_config.validate_config()


def print_config():
    """打印配置"""
    return default_config.print_config()
