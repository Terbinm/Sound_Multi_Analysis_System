"""
日誌管理模組

負責邊緣客戶端的日誌持久化、輪轉和壓縮
支援長期運作（5年以上）且總空間限制在 20GB 以內
"""
import gzip
import logging
import os
import shutil
import sys
import threading
from logging.handlers import RotatingFileHandler
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config_manager import LoggingConfig

logger = logging.getLogger(__name__)


class CompressingRotatingFileHandler(RotatingFileHandler):
    """
    帶壓縮功能的輪轉日誌處理器

    當日誌檔案達到 maxBytes 時自動輪轉，
    並將舊的日誌檔案壓縮為 .gz 格式以節省空間
    """

    def __init__(
        self,
        filename: str,
        mode: str = 'a',
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
        compress_backup: bool = True
    ):
        """
        初始化壓縮輪轉處理器

        Args:
            filename: 日誌檔案路徑
            mode: 檔案開啟模式
            maxBytes: 單檔最大大小（位元組）
            backupCount: 保留的備份數量
            encoding: 檔案編碼
            delay: 是否延遲開啟檔案
            compress_backup: 是否壓縮備份檔案
        """
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.compress_backup = compress_backup
        self._compress_lock = threading.Lock()

    def doRollover(self):
        """
        執行日誌輪轉

        覆寫父類方法，在輪轉後壓縮舊的備份檔案
        """
        # 先執行標準輪轉
        super().doRollover()

        if self.compress_backup and self.backupCount > 0:
            # 在背景執行緒中壓縮檔案，避免阻塞日誌寫入
            compress_thread = threading.Thread(
                target=self._compress_old_backups,
                daemon=True
            )
            compress_thread.start()

    def _compress_old_backups(self):
        """
        壓縮舊的備份檔案

        保留最新的一個備份不壓縮（.log.1），
        其餘備份壓縮為 .gz 格式
        """
        with self._compress_lock:
            try:
                # 從第 2 個備份開始壓縮（.log.2, .log.3, ...）
                for i in range(2, self.backupCount + 1):
                    source = f"{self.baseFilename}.{i}"
                    target = f"{source}.gz"

                    # 若未壓縮的備份存在，則壓縮它
                    if os.path.exists(source) and not os.path.exists(target):
                        try:
                            with open(source, 'rb') as f_in:
                                with gzip.open(target, 'wb', compresslevel=9) as f_out:
                                    shutil.copyfileobj(f_in, f_out)

                            # 壓縮成功後刪除原檔
                            os.remove(source)

                        except Exception as e:
                            # 壓縮失敗時保留原檔，不中斷程式
                            logging.getLogger(__name__).warning(
                                f"壓縮日誌備份失敗: {source}, 錯誤: {e}"
                            )

            except Exception as e:
                logging.getLogger(__name__).error(
                    f"壓縮備份過程中發生錯誤: {e}"
                )


class LoggerManager:
    """
    日誌管理器

    負責初始化日誌系統、監控空間使用、自動清理舊日誌
    """

    _instance: Optional['LoggerManager'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if LoggerManager._initialized:
            return

        self.log_dir: Optional[str] = None
        self.config: Optional['LoggingConfig'] = None
        self._cleanup_lock = threading.Lock()
        self._fallback_to_console: bool = False

        LoggerManager._initialized = True

    @classmethod
    def setup(
        cls,
        config: 'LoggingConfig',
        base_dir: Optional[str] = None
    ) -> logging.Logger:
        """
        設定日誌系統

        Args:
            config: 日誌配置
            base_dir: 基礎目錄（預設為程式所在目錄）

        Returns:
            配置好的根日誌記錄器
        """
        instance = cls()
        instance.config = config

        # 決定基礎目錄
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        # 設定日誌目錄
        if os.path.isabs(config.log_dir):
            instance.log_dir = config.log_dir
        else:
            instance.log_dir = os.path.join(base_dir, config.log_dir)

        # 取得根 logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, config.level.upper(), logging.DEBUG))

        # 清除現有的 handler（避免重複添加）
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

        # 建立格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # 建立控制台處理器
        if config.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(
                getattr(logging, config.console_level.upper(), logging.INFO)
            )
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)

        # 建立檔案處理器（如果啟用）
        if config.enabled:
            try:
                instance._setup_file_handler(root_logger, formatter)
            except Exception as e:
                instance._fallback_to_console = True
                logging.getLogger(__name__).warning(
                    f"無法建立日誌檔案，降級為僅控制台輸出: {e}"
                )

        # 執行初始空間檢查和清理
        if config.enabled and not instance._fallback_to_console:
            instance._check_and_cleanup()

        return root_logger

    def _setup_file_handler(
        self,
        root_logger: logging.Logger,
        formatter: logging.Formatter
    ):
        """
        設定檔案處理器

        Args:
            root_logger: 根日誌記錄器
            formatter: 日誌格式化器
        """
        # 確保 log_dir 和 config 已設定
        if self.log_dir is None or self.config is None:
            raise ValueError("日誌目錄或配置未初始化")

        # 確保日誌目錄存在
        os.makedirs(self.log_dir, exist_ok=True)

        # 檢查目錄是否可寫
        test_file = os.path.join(self.log_dir, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            raise IOError(f"日誌目錄無法寫入: {self.log_dir}") from e

        # 建立日誌檔案路徑
        log_file_path = os.path.join(self.log_dir, self.config.log_file)

        # 建立壓縮輪轉處理器
        file_handler = CompressingRotatingFileHandler(
            log_file_path,
            maxBytes=self.config.max_bytes,
            backupCount=self.config.backup_count,
            encoding='utf-8',
            compress_backup=self.config.compress_backup
        )
        file_handler.setLevel(getattr(logging, self.config.level.upper(), logging.DEBUG))
        file_handler.setFormatter(formatter)

        root_logger.addHandler(file_handler)

        # 記錄日誌檔案路徑供外部使用
        root_logger.log_file_path = log_file_path

    def _check_and_cleanup(self):
        """
        檢查空間使用並在需要時清理舊日誌
        """
        with self._cleanup_lock:
            try:
                if self.log_dir is None or self.config is None:
                    return

                if not os.path.exists(self.log_dir):
                    return

                # 計算當前日誌總大小
                total_size = self._get_logs_total_size()

                # 計算閾值（以位元組為單位）
                max_size_bytes = self.config.max_total_size_gb * 1024 * 1024 * 1024
                threshold_bytes = max_size_bytes * (self.config.cleanup_threshold_percent / 100)

                if total_size > threshold_bytes:
                    self._cleanup_old_logs(total_size, max_size_bytes)

            except Exception as e:
                logging.getLogger(__name__).error(
                    f"檢查和清理日誌時發生錯誤: {e}"
                )

    def _get_logs_total_size(self) -> int:
        """
        計算日誌目錄中所有日誌檔案的總大小

        Returns:
            總大小（位元組）
        """
        total_size = 0

        if self.log_dir is None:
            return total_size

        for filename in os.listdir(self.log_dir):
            file_path = os.path.join(self.log_dir, filename)
            if os.path.isfile(file_path):
                # 只計算日誌相關檔案
                if filename.endswith(('.log', '.log.gz')) or '.log.' in filename:
                    total_size += os.path.getsize(file_path)

        return total_size

    def _cleanup_old_logs(self, current_size: int, max_size: int):
        """
        清理舊的日誌檔案直到空間低於限制

        Args:
            current_size: 當前日誌總大小
            max_size: 最大允許大小
        """
        if self.log_dir is None or self.config is None:
            return

        log = logging.getLogger(__name__)
        log.info(
            f"日誌空間超過閾值，開始清理: "
            f"當前 {current_size / 1024 / 1024:.2f} MB, "
            f"限制 {max_size / 1024 / 1024:.2f} MB"
        )

        # 收集所有日誌備份檔案（不含當前日誌檔案）
        log_files = []
        current_log = self.config.log_file

        for filename in os.listdir(self.log_dir):
            file_path = os.path.join(self.log_dir, filename)
            if not os.path.isfile(file_path):
                continue

            # 跳過當前使用中的日誌檔案
            if filename == current_log:
                continue

            # 只處理日誌相關檔案
            if filename.startswith(current_log.replace('.log', '')):
                stat = os.stat(file_path)
                log_files.append({
                    'path': file_path,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                })

        # 按修改時間排序（最舊的在前）
        log_files.sort(key=lambda x: x['mtime'])

        # 逐一刪除最舊的檔案直到空間足夠
        target_size = max_size * 0.7  # 目標降到 70%
        freed_space = 0

        for log_file in log_files:
            if current_size - freed_space <= target_size:
                break

            try:
                os.remove(log_file['path'])
                freed_space += log_file['size']
                log.debug(f"已刪除舊日誌: {log_file['path']}")
            except Exception as e:
                log.warning(f"刪除日誌失敗: {log_file['path']}, 錯誤: {e}")

        log.info(f"清理完成，釋放空間: {freed_space / 1024 / 1024:.2f} MB")

    @classmethod
    def get_instance(cls) -> Optional['LoggerManager']:
        """取得日誌管理器實例"""
        return cls._instance

    def get_log_dir(self) -> Optional[str]:
        """取得日誌目錄路徑"""
        return self.log_dir

    def get_logs_info(self) -> dict:
        """
        取得日誌系統資訊

        Returns:
            包含日誌目錄、總大小、檔案數量等資訊的字典
        """
        info = {
            'log_dir': self.log_dir,
            'enabled': self.config.enabled if self.config else False,
            'fallback_to_console': self._fallback_to_console,
            'total_size_mb': 0,
            'file_count': 0,
            'max_size_gb': self.config.max_total_size_gb if self.config else 0
        }

        if self.log_dir and os.path.exists(self.log_dir):
            total_size = self._get_logs_total_size()
            info['total_size_mb'] = round(total_size / 1024 / 1024, 2)

            file_count = sum(
                1 for f in os.listdir(self.log_dir)
                if os.path.isfile(os.path.join(self.log_dir, f))
                and (f.endswith(('.log', '.log.gz')) or '.log.' in f)
            )
            info['file_count'] = file_count

        return info


def setup_logging(
    config: 'LoggingConfig',
    base_dir: Optional[str] = None
) -> logging.Logger:
    """
    設定日誌系統的便捷函數

    Args:
        config: 日誌配置
        base_dir: 基礎目錄（預設為程式所在目錄）

    Returns:
        配置好的根日誌記錄器
    """
    return LoggerManager.setup(config, base_dir)
