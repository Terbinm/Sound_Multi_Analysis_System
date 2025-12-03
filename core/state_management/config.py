"""
狀態管理系統配置文件
"""
import os
from typing import Dict, Any

class Config:
    """基礎配置"""

    # Flask 配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    DEBUG = FLASK_ENV == 'development'

    # 服務配置
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 55103))  # 核心服務狀態管理端口
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # MongoDB 配置
    MONGODB_CONFIG: Dict[str, Any] = {
        'host': os.environ.get('MONGODB_HOST', 'localhost'),
        'port': int(os.environ.get('MONGODB_PORT', 55101)),  # 核心服務 MongoDB 端口
        'username': os.environ.get('MONGODB_USERNAME', 'web_ui'),
        'password': os.environ.get('MONGODB_PASSWORD', 'hod2iddfsgsrl'),
        'database': os.environ.get('MONGODB_DATABASE', 'web_db'),
        'auth_source': 'admin',
        'server_selection_timeout_ms': 5000,
    }

    # RabbitMQ 配置
    RABBITMQ_CONFIG: Dict[str, Any] = {
        'host': os.environ.get('RABBITMQ_HOST', 'localhost'),
        'port': int(os.environ.get('RABBITMQ_PORT', 55102)),  # 核心服務 RabbitMQ 端口
        'username': os.environ.get('RABBITMQ_USERNAME', 'admin'),
        'password': os.environ.get('RABBITMQ_PASSWORD', 'rabbitmq_admin_pass'),
        'virtual_host': os.environ.get('RABBITMQ_VHOST', '/'),
        'exchange': os.environ.get('RABBITMQ_EXCHANGE', 'analysis_tasks_exchange'),
        'queue': os.environ.get('RABBITMQ_QUEUE', 'analysis_tasks_queue'),
        'routing_key_prefix': os.environ.get('RABBITMQ_ROUTING_KEY_PREFIX', 'analysis'),
        'routing_key_binding': os.environ.get('RABBITMQ_ROUTING_KEY_BINDING', 'analysis.#'),
        'message_ttl_ms': int(os.environ.get('RABBITMQ_MESSAGE_TTL_MS', '86400000')),
        'heartbeat': int(os.environ.get('RABBITMQ_HEARTBEAT', '600')),
        'blocked_timeout': int(os.environ.get('RABBITMQ_BLOCKED_TIMEOUT', '300')),
    }

    # MongoDB Collections
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
    env = os.environ.get('FLASK_ENV', 'development')
    return config_dict.get(env, DevelopmentConfig)
