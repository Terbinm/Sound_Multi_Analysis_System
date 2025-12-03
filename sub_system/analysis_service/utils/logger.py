# utils/logger.py - 日誌管理工具

import logging
import os
from contextlib import contextmanager
import contextvars
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional
from config import LOGGING_CONFIG


_ANALYZE_UUID_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    'analyze_uuid',
    default='-'
)


def _normalize_uuid(value: Optional[str]) -> str:
    """確保 AnalyzeUUID 以字串形式輸出。"""
    if value is None:
        return '-'
    value = str(value).strip()
    return value or '-'


class AnalyzeUUIDFilter(logging.Filter):
    """將 AnalyzeUUID 注入 log record，確保格式化時可用。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.analyze_uuid = _ANALYZE_UUID_CONTEXT.get('-')
        return True


@contextmanager
def analyze_uuid_context(analyze_uuid: Optional[str]):
    """提供 context manager，用於在區塊內綁定 AnalyzeUUID。"""
    token = _ANALYZE_UUID_CONTEXT.set(_normalize_uuid(analyze_uuid))
    try:
        yield
    finally:
        _ANALYZE_UUID_CONTEXT.reset(token)


def set_analyze_uuid(analyze_uuid: Optional[str]) -> None:
    """直接設定當前執行緒（context）的 AnalyzeUUID。"""
    _ANALYZE_UUID_CONTEXT.set(_normalize_uuid(analyze_uuid))


def clear_analyze_uuid() -> None:
    """清除當前設定的 AnalyzeUUID。"""
    _ANALYZE_UUID_CONTEXT.set('-')


def get_analyze_uuid() -> str:
    """取得當前設定的 AnalyzeUUID。"""
    return _ANALYZE_UUID_CONTEXT.get('-')


def _resolve_log_file_path() -> str:
    """計算本次執行的日誌檔案路徑，並確保目錄存在。"""
    log_dir = LOGGING_CONFIG.get('log_dir')
    if not log_dir:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
        log_dir = os.path.normpath(log_dir)

    os.makedirs(log_dir, exist_ok=True)

    base_filename = LOGGING_CONFIG.get('log_file', 'analysis_service.log')
    base_name, ext = os.path.splitext(base_filename)
    ext = ext or '.log'

    timestamp_format = LOGGING_CONFIG.get('timestamp_format', '%Y%m%d_%H%M%S')
    timestamp = datetime.now().strftime(timestamp_format)

    log_filename = f"{base_name}_{timestamp}{ext}"
    return os.path.join(log_dir, log_filename)


def setup_logger(name: str = 'analysis_service') -> logging.Logger:
    """
    設置日誌記錄器
    
    Args:
        name: 日誌記錄器名稱
        
    Returns:
        配置好的日誌記錄器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOGGING_CONFIG['level']))

    if not any(isinstance(f, AnalyzeUUIDFilter) for f in logger.filters):
        logger.addFilter(AnalyzeUUIDFilter())
    
    # 避免重複添加 handler
    if logger.handlers:
        return logger
    
    # 格式化器
    formatter = logging.Formatter(LOGGING_CONFIG['format'])

    log_file_path = _resolve_log_file_path()
    
    # 檔案處理器（使用 RotatingFileHandler）
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=LOGGING_CONFIG['max_bytes'],
        backupCount=LOGGING_CONFIG['backup_count'],
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # 控制台處理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # 添加處理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # 方便偵錯與測試取得當前日誌路徑
    logger.log_file_path = log_file_path
    
    return logger


# 建立全域 logger
logger = setup_logger()
