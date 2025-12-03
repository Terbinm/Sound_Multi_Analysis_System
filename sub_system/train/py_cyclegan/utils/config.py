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


def validate_config():
    """驗證配置"""
    return default_config.validate_config()


def print_config():
    """打印配置"""
    return default_config.print_config()
