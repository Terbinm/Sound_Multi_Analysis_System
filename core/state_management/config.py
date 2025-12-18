"""
狀態管理系統配置文件
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from env_loader import load_project_env

load_project_env()


def require_env(name: str) -> str:
    """強制取得環境變數，沒有就直接報錯"""
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class Config:
    """只從 .env 讀取的強制配置（無 fallback）"""

    # ==========================
    # Flask
    # ==========================
    SECRET_KEY = require_env('STATE_MANAGEMENT_SECRET_KEY')
    FLASK_ENV = require_env('STATE_MANAGEMENT_FLASK_ENV')
    DEBUG = FLASK_ENV == 'development'

    # ==========================
    # Service
    # ==========================
    HOST = require_env('STATE_MANAGEMENT_HOST')
    PORT = int(require_env('STATE_MANAGEMENT_PORT'))
    LOG_LEVEL = require_env('STATE_MANAGEMENT_LOG_LEVEL')

    # ==========================
    # MongoDB
    # ==========================
    MONGODB_CONFIG: Dict[str, Any] = {
        'host': require_env('MONGODB_HOST'),
        'port': int(require_env('MONGODB_PORT')),
        'username': require_env('MONGODB_USERNAME'),
        'password': require_env('MONGODB_PASSWORD'),
        'database': require_env('MONGODB_DATABASE'),
        'auth_source': 'admin',  # 固定值才可保留
        'server_selection_timeout_ms': 5000,
    }

    # ==========================
    # RabbitMQ
    # ==========================
    RABBITMQ_CONFIG: Dict[str, Any] = {
        'host': require_env('RABBITMQ_HOST'),
        'port': int(require_env('RABBITMQ_PORT')),
        'username': require_env('RABBITMQ_USERNAME'),
        'password': require_env('RABBITMQ_PASSWORD'),
        'virtual_host': require_env('RABBITMQ_VHOST'),
        'exchange': require_env('RABBITMQ_EXCHANGE'),
        'queue': require_env('RABBITMQ_QUEUE'),
        'routing_key_prefix': require_env('RABBITMQ_ROUTING_KEY_PREFIX'),
        'routing_key_binding': require_env('RABBITMQ_ROUTING_KEY_BINDING'),
        'message_ttl_ms': int(require_env('RABBITMQ_MESSAGE_TTL_MS')),
        'heartbeat': int(require_env('RABBITMQ_HEARTBEAT')),
        'blocked_timeout': int(require_env('RABBITMQ_BLOCKED_TIMEOUT')),
    }

    # ==========================
    # Collections（這些是固定常數，可以保留）
    # ==========================
    COLLECTIONS = {
        'recordings': 'recordings',
        'analysis_configs': 'analysis_configs',
        'routing_rules': 'routing_rules',
        'mongodb_instances': 'mongodb_instances',
        'task_execution_logs': 'task_execution_logs',
    }


    # 節點配置
    NODE_HEARTBEAT_INTERVAL = 5   # 秒 - 節點監控檢查間隔（統計更新頻率）
    NODE_HEARTBEAT_TIMEOUT = 30   # 秒 - 節點被視為離線的超時時間

    # WebSocket 配置
    WEBSOCKET_PING_TIMEOUT = 6   # WebSocket ping 超時（秒）
    WEBSOCKET_PING_INTERVAL = 2  # WebSocket ping 間隔（秒）
    WEBSOCKET_ASYNC_MODE = os.environ.get('WEBSOCKET_ASYNC_MODE', 'threading')

    # 日誌配置
    LOG_DIR = 'logs'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    # 日誌管理功能
    CLEAR_LOGS_ON_STARTUP = os.environ.get('CLEAR_LOGS_ON_STARTUP', 'false').lower() == 'true'  # 啟動時清除所有日誌（僅供 debug 使用）
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', '30'))  # 保留的舊日誌檔案數量（自動清理超過此數量的舊日誌）

    # 文件上傳配置
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB
    UPLOAD_EXTENSIONS = {'.pkl', '.pth', '.h5', '.onnx', '.pb'}

    @staticmethod
    def get_mongodb_uri() -> str:
        """獲取 MongoDB 連接 URI"""
        cfg = Config.MONGODB_CONFIG
        return f"mongodb://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['auth_source']}"


class DevelopmentConfig(Config):
    """開發環境配置"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    CLEAR_LOGS_ON_STARTUP = True  # 開發環境預設啟用清除日誌


class ProductionConfig(Config):
    """生產環境配置"""
    DEBUG = False
    LOG_LEVEL = 'INFO'


class TestingConfig(Config):
    """測試環境配置"""
    TESTING = True
    DEBUG = True


# 配置字典
config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}


def get_config() -> Config:
    """獲取當前配置"""
    env = os.environ.get('STATE_MANAGEMENT_FLASK_ENV') or os.environ.get('FLASK_ENV', 'development')
    return config_dict.get(env, DevelopmentConfig)
