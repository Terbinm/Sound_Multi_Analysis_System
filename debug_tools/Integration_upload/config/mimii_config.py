"""
MIMII 資料集配置
機器異音檢測資料集的特定配置
"""
from env_loader import load_project_env
load_project_env()

import os
from pathlib import Path
from typing import List

from .base_config import BaseUploadConfig


class MIMIIUploadConfig(BaseUploadConfig):
    """MIMII 批次上傳工具的配置"""

    # ==================== 資料來源 ====================
    _DEFAULT_UPLOAD_DIRECTORY = ()
    UPLOAD_DIRECTORY = os.getenv('MIMII_UPLOAD_DIR', _DEFAULT_UPLOAD_DIRECTORY)

    # ==================== 標籤對應資料夾名稱 ====================
    LABEL_FOLDERS = {
        'normal': 'normal',
        'abnormal': 'abnormal',
    }

    # 支援的機器類型
    MACHINE_TYPES = ['fan']
    # MACHINE_TYPES = ['pump']
    #MACHINE_TYPES = ['slider']
    # MACHINE_TYPES = ['valve']

    # ==================== 支援檔案格式 ====================
    SUPPORTED_FORMATS = ['.wav']

    # ==================== 資料集固定欄位 ====================
    DATASET_CONFIG = {
        'dataset_UUID': 'mimii_batch_upload',
        # obj_ID 將從路徑中自動提取 (id_00, id_02, id_04 等)
    }

    # ==================== 分析服務配置 ====================
    ANALYSIS_CONFIG = {
        'target_channel': [5]
    }

    @classmethod
    def _validate_label_folders(cls, upload_path: Path) -> List[str]:
        """
        MIMII 資料集的標籤資料夾在深層目錄中，不需要檢查
        標籤資料夾結構：{snr}_{machine_type}/{machine_type}/{obj_ID}/{label}/

        Args:
            upload_path: 上傳資料夾路徑（未使用）

        Returns:
            空列表（不執行驗證）
        """
        # MIMII 的標籤資料夾在深層目錄中（如 6_dB_pump/pump/id_00/normal/）
        # 而不是直接在 UPLOAD_DIRECTORY 下，因此跳過標籤資料夾檢查
        return []
