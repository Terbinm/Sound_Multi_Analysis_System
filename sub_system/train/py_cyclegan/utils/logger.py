"""Logging Utilities"""

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "cyclegan",
    log_file: str = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志器名称
        log_file: 日志文件路径
        level: 日志级别

    Returns:
        配置好的 Logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 清除现有 handlers
    logger.handlers.clear()

    # 格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件 handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
