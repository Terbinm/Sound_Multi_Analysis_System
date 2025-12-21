"""
基礎配置模組
定義所有資料集共同的配置結構
"""

import os
from abc import ABC
from pathlib import Path
from typing import Dict, Any, List

from dotenv import load_dotenv
from env_loader import load_project_env
load_project_env()


class BaseUploadConfig(ABC):
    """批次上傳工具的基礎配置類別"""

    # ==================== MongoDB 連線設定 ====================
    # 強制從 .env 讀取（覆蓋外部環境變數）
    load_dotenv(override=True)

    MONGODB_CONFIG: Dict[str, Any] = {
        'host': os.getenv("MONGODB_HOST"),
        'port': int(os.getenv("MONGODB_PORT")),
        'username': os.getenv("MONGODB_USERNAME"),
        'password': os.getenv("MONGODB_PASSWORD"),
        'database': os.getenv("MONGODB_DATABASE"),
        'collection': os.getenv("MONGODB_COLLECTION")
    }

    # ==================== 上傳行為配置 ====================
    UPLOAD_BEHAVIOR: Dict[str, Any] = {
        'skip_existing': True,          # 是否跳過已存在的檔案（根據雜湊值判斷）
        'check_duplicates': True,       # 是否檢查重複檔案
        'concurrent_uploads': 3,        # 並行上傳數量
        'retry_attempts': 3,            # 失敗重試次數
        'retry_delay': 2,               # 重試延遲（秒）
        # 'per_label_limit': 0,           # 限制每個 label 上傳數量，0 為不限制
        # 'per_label_limit': 2,           # 限制每個 label 上傳數量，0 為不限制
        'per_label_limit': 3001,           # 限制每個 label 上傳數量，0 為不限制
        # 'per_label_limit': 200,           # 限制每個 label 上傳數量，0 為不限制
    }

    # ==================== 日誌配置 ====================
    LOGGING_CONFIG: Dict[str, str | int] = {
        'level': 'INFO',
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'log_file': os.path.join('reports', 'logs', 'batch_upload.log'),
        'max_bytes': 10 * 1024 * 1024,  # 10MB
        'backup_count': 5,
    }

    # ==================== 進度追蹤 ====================
    PROGRESS_FILE: str = os.path.join('reports', 'upload_progress.json')

    # ==================== 報告輸出 ====================
    REPORT_OUTPUT: Dict[str, Any] = {
        'save_report': True,
        'report_directory': 'reports',
        'report_format': 'json',
    }

    # ==================== GridFS 配置 ====================
    USE_GRIDFS: bool = True

    # ==================== Dry Run 預覽輸出 ====================
    DRY_RUN_PREVIEW: Dict[str, Any] = {
        'enable_preview': True,
        'output_directory': os.path.join('reports', 'dry_run_previews'),
    }

    # ==================== 路由規則觸發配置 ====================
    ROUTING_TRIGGER: Dict[str, Any] = {
        'enabled': True,                    # 是否啟用自動觸發
        'state_management_url': 'http://192.168.71.43:55103',  # 狀態管理系統 URL
        'router_ids': [],                   # 預設 router_ids（可在子類別中覆蓋）
        'sequential': True,                 # 是否依序執行
        'trigger_on_completion': True,      # 上傳完成後是否觸發
        'batch_trigger': False,             # 是否批次觸發（False: 每個檔案觸發，True: 批次結束後觸發）
        'retry_attempts': 3,                # 觸發失敗重試次數
        'retry_delay': 2,                   # 重試延遲（秒）
    }

    # ==================== 資料集特定配置（由子類別定義） ====================
    UPLOAD_DIRECTORY: str = ""
    LABEL_FOLDERS: Dict[str, str] = {}
    SUPPORTED_FORMATS: List[str] = []
    DATASET_CONFIG: Dict[str, str] = {
        'dataset_UUID': '',
        'obj_ID': '-1',
    }

    @classmethod
    def get_upload_path(cls) -> Path:
        """取得上傳資料夾路徑"""
        return Path(cls.UPLOAD_DIRECTORY)

    @classmethod
    def validate_base_config(cls) -> List[str]:
        """
        驗證基礎配置

        Returns:
            錯誤訊息列表
        """
        errors: List[str] = []

        # 檢查 MongoDB 配置
        required_mongo_keys = ['host', 'port', 'username', 'password', 'database', 'collection']
        for key in required_mongo_keys:
            if key not in cls.MONGODB_CONFIG:
                errors.append(f"MongoDB 配置缺少欄位：{key}")

        # 檢查上傳資料夾
        if cls.UPLOAD_DIRECTORY:
            upload_path = cls.get_upload_path()
            if not upload_path.exists():
                errors.append(f"找不到上傳資料夾：{upload_path}")
            elif not any(upload_path.glob('**/*')):
                errors.append(f"上傳資料夾沒有檔案：{upload_path}")

            # 檢查標籤資料夾（可被子類別覆寫）
            errors.extend(cls._validate_label_folders(upload_path))

        return errors

    @classmethod
    def _validate_label_folders(cls, upload_path: Path) -> List[str]:
        """
        驗證標籤資料夾是否存在
        子類別可以覆寫此方法以跳過或自訂驗證邏輯

        Args:
            upload_path: 上傳資料夾路徑

        Returns:
            錯誤訊息列表
        """
        errors: List[str] = []
        for label, folder_name in cls.LABEL_FOLDERS.items():
            folder_path = upload_path / folder_name
            if not folder_path.is_dir():
                errors.append(f"找不到標籤「{label}」對應的資料夾：{folder_path}")
        return errors

    @classmethod
    def get_config_summary(cls) -> Dict[str, Any]:
        """
        取得配置摘要

        Returns:
            配置摘要字典
        """
        return {
            'dataset_uuid': cls.DATASET_CONFIG.get('dataset_UUID', 'N/A'),
            'upload_directory': cls.UPLOAD_DIRECTORY,
            'mongodb_host': cls.MONGODB_CONFIG['host'],
            'mongodb_port': cls.MONGODB_CONFIG['port'],
            'mongodb_database': cls.MONGODB_CONFIG['database'],
            'mongodb_collection': cls.MONGODB_CONFIG['collection'],
            'use_gridfs': cls.USE_GRIDFS,
            'concurrent_uploads': cls.UPLOAD_BEHAVIOR['concurrent_uploads'],
            'per_label_limit': cls.UPLOAD_BEHAVIOR['per_label_limit'],
            'supported_formats': cls.SUPPORTED_FORMATS,
            'labels': list(cls.LABEL_FOLDERS.keys()) if cls.LABEL_FOLDERS else ['default'],
        }
