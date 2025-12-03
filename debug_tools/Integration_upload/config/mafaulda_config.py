"""
MAFAULDA 資料集配置
機械故障診斷資料集的特定配置
"""

from .base_config import BaseUploadConfig


class MAFAULDAUploadConfig(BaseUploadConfig):
    """MAFAULDA 批次上傳工具的配置"""

    # ==================== 資料來源 ====================
    UPLOAD_DIRECTORY = (
        r"C:\Users\sixsn\PycharmProjects\CPC_server_collectorSYS"
        r"\debug_tools\Integration_upload\upload_data\mafaulda_data"
    )

    # ==================== 標籤對應資料夾名稱 ====================
    LABEL_FOLDERS = {
        'normal': 'normal',
        'imbalance': 'imbalance',
        'horizontal_misalignment': 'horizontal-misalignment',
        'vertical_misalignment': 'vertical-misalignment',
        'underhang': 'underhang',
        'overhang': 'overhang',
    }

    # ==================== 支援檔案格式 ====================
    SUPPORTED_FORMATS = ['.csv']

    # ==================== 資料集固定欄位 ====================
    DATASET_CONFIG = {
        'dataset_UUID': 'mafaulda_batch_upload',
        'obj_ID': '-1',
    }

    # ==================== 分析服務配置 ====================
    ANALYSIS_CONFIG = {
        'target_channel': [7]
    }

    # ==================== CSV 解析配置 ====================
    CSV_CONFIG = {
        'sample_rate_hz': 51200,  # 依據 MAFAULDA 數據手冊
        'expected_channels': 8,   # 預期感測器數量（資料列欄位數）
    }
