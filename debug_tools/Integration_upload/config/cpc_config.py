"""
CPC 資料集配置
工廠環境音訊資料集的特定配置
"""

import os

from .base_config import BaseUploadConfig


class CPCUploadConfig(BaseUploadConfig):
    """CPC 批次上傳工具的配置"""

    # ==================== 資料來源 ====================
    _DEFAULT_UPLOAD_DIRECTORY = r"D:\cillab\training_data\cpc_server_collector_data\upload_data\cpc_broken"
    UPLOAD_DIRECTORY = os.getenv('CPC_UPLOAD_DIR', _DEFAULT_UPLOAD_DIRECTORY)

    # CPC 錄音沒有分類子資料夾，全部檔案使用同一標籤與裝置代碼
    LABEL_FOLDERS = {}
    DEFAULT_LABEL = "factory_ambient"
    DEVICE_ID = "cpc006"

    # ==================== 支援檔案格式 ====================
    SUPPORTED_FORMATS = ['.wav']

    # ==================== 資料集固定欄位 ====================
    DATASET_CONFIG = {
        'dataset_UUID': 'cpc_batch_upload',
        'obj_ID': '-1',  # CPC 工廠音訊統一使用 -1
    }

    # CPC 音訊為單聲道
    TARGET_CHANNEL = [0]

    AUDIO_CONFIG = {
        'expected_sample_rate_hz': 16000,  # CPC 錄音為 16 kHz
        'allow_mono_only': True,
    }
