"""
日誌管理模組
提供統一的日誌記錄器設置
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any


class BatchUploadLogger:
    """負責建立共用記錄器"""

    @staticmethod
    def setup_logger(
        name: str,
        logging_config: Dict[str, Any]
    ) -> logging.Logger:
        """
        設置日誌記錄器

        Args:
            name: 記錄器名稱
            logging_config: 日誌配置字典，包含：
                - level: 日誌級別 (如 'DEBUG', 'INFO')
                - format: 日誌格式字串
                - log_file: 日誌檔案路徑
                - max_bytes: 單個日誌檔案最大大小
                - backup_count: 備份檔案數量

        Returns:
            配置好的日誌記錄器
        """
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, logging_config['level']))

        # 如果已有處理器，直接返回
        if logger.handlers:
            return logger

        formatter = logging.Formatter(logging_config['format'])

        # 檔案處理器
        log_path = Path(logging_config['log_file'])
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=logging_config['max_bytes'],
            backupCount=logging_config['backup_count'],
            encoding='utf-8',
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        # 控制台處理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger
