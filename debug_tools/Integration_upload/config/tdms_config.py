"""
TDMS 資料集配置
沖壓模具振動訊號資料集的特定配置
"""
from env_loader import load_project_env
load_project_env()

import os
from pathlib import Path
from typing import List

from .base_config import BaseUploadConfig


class TDMSUploadConfig(BaseUploadConfig):
    """TDMS 批次上傳工具的配置"""

    # ==================== 資料來源 ====================
    # 強制從 .env 讀取，不設定預設值
    UPLOAD_DIRECTORY = os.getenv('TDMS_UPLOAD_DIR', '')

    # ==================== 標籤處理 ====================
    # TDMS 資料結構沒有 normal/abnormal 子資料夾
    # 使用預設標籤，不需要 LABEL_FOLDERS
    LABEL_FOLDERS = {}
    DEFAULT_LABEL = 'normal'  # 所有檔案預設標籤

    # ==================== 支援檔案格式 ====================
    SUPPORTED_FORMATS = ['.tdms']

    # ==================== 資料集固定欄位 ====================
    DATASET_CONFIG = {
        'dataset_UUID': 'TDMS_Stamping_Die',
        # obj_ID 將從資料夾名稱自動提取（產品編號）
    }

    # ==================== TDMS 特定配置 ====================
    TDMS_CONFIG = {
        'default_channel': 5,        # 預設讀取的通道索引
        'sample_rate': 10000,        # 取樣率 (Hz)
        'channels_to_read': ['Ch0-T1', 'Ch1-T5', 'Ch4-T3'],  # 可選：指定通道名稱
    }

    # ==================== 分析服務配置 ====================
    ANALYSIS_CONFIG = {
        'target_channel': [5],  # 分析服務要處理的通道
    }

    # ==================== 路由規則觸發配置 ====================
    ROUTING_TRIGGER = {
        **BaseUploadConfig.ROUTING_TRIGGER,
        'router_ids': ['Stamping_Die_LEAF_RF'],  # TDMS 專用路由
    }

    @classmethod
    def _validate_label_folders(cls, upload_path: Path) -> List[str]:
        """
        TDMS 資料集不使用標籤資料夾結構，跳過驗證

        Returns:
            空列表（不執行驗證）
        """
        return []
