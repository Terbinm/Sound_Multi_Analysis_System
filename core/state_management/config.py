"""
狀態管理系統配置文件

所有配置項都必須透過環境變數設定，不提供預設值。
若環境變數缺失，系統將在啟動時報錯並列出缺失項目。

使用方式：
1. 複製 .env.example 為 .env
2. 根據實際環境填寫所有必要的環境變數
3. 啟動服務前確保所有必要環境變數已設定
"""
import os
import sys
from typing import Dict, Any, List
from dotenv import load_dotenv, find_dotenv

# 先行載入 .env 方便後續配置取用
load_dotenv(find_dotenv())


def _get_required_env(key: str, value_type=str) -> Any:
    """
    獲取必要的環境變數，若不存在則拋出錯誤
    
    Args:
        key: 環境變數名稱
        value_type: 期望的值類型（str, int, float, bool）
        
    Returns:
        轉換後的環境變數值
        
    Raises:
        EnvironmentError: 當環境變數不存在時
    """
    value = os.environ.get(key)
    if value is None:
        raise EnvironmentError(f"必要環境變數 '{key}' 未設定")
    
    try:
        if value_type == int:
            return int(value)
        elif value_type == float:
            return float(value)
        elif value_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        else:
            return value
    except ValueError as e:
        raise EnvironmentError(f"環境變數 '{key}' 的值 '{value}' 無法轉換為 {value_type.__name__}: {e}")


class Config:
    """
    基礎配置類別
    
    所有配置項均從環境變數載入，無預設值。
    常數配置（如日誌格式、角色名稱等）定義在此處，但不應在業務邏輯中硬編碼。
    """

    # ==================== Flask 配置 ====================
    # 必須從環境變數設定，用於 session 加密等安全功能
    SECRET_KEY = _get_required_env('STATE_MANAGEMENT_SECRET_KEY')
    FLASK_ENV = _get_required_env('STATE_MANAGEMENT_FLASK_ENV')
    DEBUG = FLASK_ENV == 'development'

    # ==================== 服務配置 ====================
    # 服務監聽位址與端口，生產環境務必正確設定
    HOST = _get_required_env('STATE_MANAGEMENT_HOST')
    PORT = _get_required_env('STATE_MANAGEMENT_PORT', int)
    LOG_LEVEL = _get_required_env('STATE_MANAGEMENT_LOG_LEVEL')

    # ==================== MongoDB 配置 ====================
    # 主要資料庫連線設定，所有參數必須提供
    MONGODB_CONFIG: Dict[str, Any] = {
        'host': _get_required_env('MONGODB_HOST'),
        'port': _get_required_env('MONGODB_PORT', int),
        'username': _get_required_env('MONGODB_USERNAME'),
        'password': _get_required_env('MONGODB_PASSWORD'),
        'database': _get_required_env('MONGODB_DATABASE'),
        'auth_source': _get_required_env('MONGODB_AUTH_SOURCE'),
        'server_selection_timeout_ms': _get_required_env('MONGODB_SERVER_SELECTION_TIMEOUT_MS', int),
    }

    # ==================== RabbitMQ 配置 ====================
    # 訊息佇列連線設定，用於任務分發
    RABBITMQ_CONFIG: Dict[str, Any] = {
        'host': _get_required_env('RABBITMQ_HOST'),
        'port': _get_required_env('RABBITMQ_PORT', int),
        'username': _get_required_env('RABBITMQ_USERNAME'),
        'password': _get_required_env('RABBITMQ_PASSWORD'),
        'virtual_host': _get_required_env('RABBITMQ_VHOST'),
        'exchange': _get_required_env('RABBITMQ_EXCHANGE'),
        'queue': _get_required_env('RABBITMQ_QUEUE'),
        'routing_key_prefix': _get_required_env('RABBITMQ_ROUTING_KEY_PREFIX'),
        'routing_key_binding': _get_required_env('RABBITMQ_ROUTING_KEY_BINDING'),
        'message_ttl_ms': _get_required_env('RABBITMQ_MESSAGE_TTL_MS', int),
        'heartbeat': _get_required_env('RABBITMQ_HEARTBEAT', int),
        'blocked_timeout': _get_required_env('RABBITMQ_BLOCKED_TIMEOUT', int),
    }

    # ==================== MongoDB 集合名稱配置 ====================
    # 各資料表名稱，允許不同環境使用不同集合名稱
    COLLECTIONS = {
        'recordings': _get_required_env('MONGODB_COLLECTION_RECORDINGS'),
        'analysis_configs': _get_required_env('MONGODB_COLLECTION_ANALYSIS_CONFIGS'),
        'routing_rules': _get_required_env('MONGODB_COLLECTION_ROUTING_RULES'),
        'mongodb_instances': _get_required_env('MONGODB_COLLECTION_INSTANCES'),
        'task_execution_logs': _get_required_env('MONGODB_COLLECTION_TASK_LOGS'),
        'node_status': _get_required_env('MONGODB_COLLECTION_NODES_STATUS'),
        'config_version': _get_required_env('MONGODB_COLLECTION_SYSTEM_METADATA'),
        'users': _get_required_env('MONGODB_COLLECTION_USERS'),
    }

    # ==================== 節點監控配置 ====================
    # 節點心跳與健康檢查參數
    NODE_HEARTBEAT_INTERVAL = _get_required_env('NODE_HEARTBEAT_INTERVAL', int)
    NODE_HEARTBEAT_TIMEOUT = _get_required_env('NODE_HEARTBEAT_TIMEOUT', int)

    # ==================== WebSocket 配置 ====================
    # WebSocket 連線參數，影響即時通訊穩定性
    WEBSOCKET_PING_TIMEOUT = _get_required_env('WEBSOCKET_PING_TIMEOUT', int)
    WEBSOCKET_PING_INTERVAL = _get_required_env('WEBSOCKET_PING_INTERVAL', int)
    WEBSOCKET_ASYNC_MODE = _get_required_env('WEBSOCKET_ASYNC_MODE')
    WEBSOCKET_CORS_ALLOWED_ORIGINS = _get_required_env('WEBSOCKET_CORS_ALLOWED_ORIGINS')

    # ==================== 初始化管理員帳號配置 ====================
    # 用於首次部署時建立預設管理員帳號
    INIT_ADMIN_USERNAME = _get_required_env('INIT_ADMIN_USERNAME')
    INIT_ADMIN_EMAIL = _get_required_env('INIT_ADMIN_EMAIL')
    INIT_ADMIN_PASSWORD = _get_required_env('INIT_ADMIN_PASSWORD')

    # ==================== 日誌配置 ====================
    # 日誌儲存路徑與管理參數
    LOG_DIR = _get_required_env('LOG_DIR')
    LOG_BACKUP_COUNT = _get_required_env('LOG_BACKUP_COUNT', int)
    CLEAR_LOGS_ON_STARTUP = _get_required_env('CLEAR_LOGS_ON_STARTUP', bool)
    
    # 日誌格式常數（程式碼層級定義，不需環境變數）
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    # ==================== 檔案上傳配置 ====================
    # 模型檔案上傳限制
    MAX_CONTENT_LENGTH = _get_required_env('MAX_UPLOAD_FILE_SIZE_MB', int) * 1024 * 1024
    # 允許的模型檔案副檔名（常數定義）
    UPLOAD_EXTENSIONS = {'.pkl', '.pth', '.h5', '.onnx', '.pb'}

    # ==================== 系統常數定義 ====================
    # 這些是系統層級的常數，不應透過環境變數修改，也不應在業務邏輯中硬編碼
    
    # 使用者角色常數
    ROLE_ADMIN = 'admin'
    ROLE_USER = 'user'
    
    # 預設 MongoDB 實例 ID（系統保留）
    DEFAULT_MONGODB_INSTANCE_ID = 'default'
    
    # 配置版本鍵名（系統保留）
    CONFIG_VERSION_KEY = 'config_version'

    @staticmethod
    def get_mongodb_uri() -> str:
        """
        獲取 MongoDB 連接 URI
        
        Returns:
            MongoDB 連接字串，格式：mongodb://username:password@host:port/auth_source
        """
        cfg = Config.MONGODB_CONFIG
        return f"mongodb://{cfg['username']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['auth_source']}"

    @staticmethod
    def validate() -> None:
        """
        驗證所有必要配置是否已正確載入
        
        此方法應在應用程式啟動時呼叫，確保所有必要的環境變數都已設定。
        若有任何配置缺失或無效，將拋出詳細錯誤訊息。
        
        Raises:
            EnvironmentError: 當有配置缺失或無效時
        """
        missing_vars = []
        errors = []
        
        # 檢查所有必要的環境變數
        required_vars = [
            'STATE_MANAGEMENT_SECRET_KEY',
            'STATE_MANAGEMENT_FLASK_ENV',
            'STATE_MANAGEMENT_HOST',
            'STATE_MANAGEMENT_PORT',
            'STATE_MANAGEMENT_LOG_LEVEL',
            'MONGODB_HOST',
            'MONGODB_PORT',
            'MONGODB_USERNAME',
            'MONGODB_PASSWORD',
            'MONGODB_DATABASE',
            'MONGODB_AUTH_SOURCE',
            'MONGODB_SERVER_SELECTION_TIMEOUT_MS',
            'MONGODB_COLLECTION_RECORDINGS',
            'MONGODB_COLLECTION_ANALYSIS_CONFIGS',
            'MONGODB_COLLECTION_ROUTING_RULES',
            'MONGODB_COLLECTION_INSTANCES',
            'MONGODB_COLLECTION_TASK_LOGS',
            'MONGODB_COLLECTION_NODES_STATUS',
            'MONGODB_COLLECTION_SYSTEM_METADATA',
            'MONGODB_COLLECTION_USERS',
            'RABBITMQ_HOST',
            'RABBITMQ_PORT',
            'RABBITMQ_USERNAME',
            'RABBITMQ_PASSWORD',
            'RABBITMQ_VHOST',
            'RABBITMQ_EXCHANGE',
            'RABBITMQ_QUEUE',
            'RABBITMQ_ROUTING_KEY_PREFIX',
            'RABBITMQ_ROUTING_KEY_BINDING',
            'RABBITMQ_MESSAGE_TTL_MS',
            'RABBITMQ_HEARTBEAT',
            'RABBITMQ_BLOCKED_TIMEOUT',
            'NODE_HEARTBEAT_INTERVAL',
            'NODE_HEARTBEAT_TIMEOUT',
            'WEBSOCKET_PING_TIMEOUT',
            'WEBSOCKET_PING_INTERVAL',
            'WEBSOCKET_ASYNC_MODE',
            'WEBSOCKET_CORS_ALLOWED_ORIGINS',
            'INIT_ADMIN_USERNAME',
            'INIT_ADMIN_EMAIL',
            'INIT_ADMIN_PASSWORD',
            'LOG_DIR',
            'LOG_BACKUP_COUNT',
            'CLEAR_LOGS_ON_STARTUP',
            'MAX_UPLOAD_FILE_SIZE_MB',
        ]
        
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            error_msg = (
                "\n" + "="*80 + "\n"
                "錯誤：缺少必要的環境變數\n"
                "="*80 + "\n"
                "以下環境變數未設定：\n"
                + "\n".join(f"  - {var}" for var in missing_vars) + "\n\n"
                "請執行以下步驟：\n"
                "1. 檢查專案根目錄的 .env 檔案是否存在\n"
                "2. 參考 docs/env/env_configuration_guide.md 文件\n"
                "3. 確保所有必要的環境變數都已正確設定\n"
                "="*80 + "\n"
            )
            raise EnvironmentError(error_msg)
        
        # 驗證數值型別配置的合理性
        try:
            if Config.PORT < 1 or Config.PORT > 65535:
                errors.append(f"STATE_MANAGEMENT_PORT 必須在 1-65535 範圍內，目前值：{Config.PORT}")
            
            if Config.MONGODB_CONFIG['port'] < 1 or Config.MONGODB_CONFIG['port'] > 65535:
                errors.append(f"MONGODB_PORT 必須在 1-65535 範圍內，目前值：{Config.MONGODB_CONFIG['port']}")
            
            if Config.RABBITMQ_CONFIG['port'] < 1 or Config.RABBITMQ_CONFIG['port'] > 65535:
                errors.append(f"RABBITMQ_PORT 必須在 1-65535 範圍內，目前值：{Config.RABBITMQ_CONFIG['port']}")
            
            if Config.NODE_HEARTBEAT_INTERVAL < 1:
                errors.append(f"NODE_HEARTBEAT_INTERVAL 必須大於 0，目前值：{Config.NODE_HEARTBEAT_INTERVAL}")
            
            if Config.NODE_HEARTBEAT_TIMEOUT < Config.NODE_HEARTBEAT_INTERVAL:
                errors.append(f"NODE_HEARTBEAT_TIMEOUT ({Config.NODE_HEARTBEAT_TIMEOUT}) 必須大於 NODE_HEARTBEAT_INTERVAL ({Config.NODE_HEARTBEAT_INTERVAL})")
            
            if Config.WEBSOCKET_PING_TIMEOUT < 1:
                errors.append(f"WEBSOCKET_PING_TIMEOUT 必須大於 0，目前值：{Config.WEBSOCKET_PING_TIMEOUT}")
            
            if Config.WEBSOCKET_PING_INTERVAL < 1:
                errors.append(f"WEBSOCKET_PING_INTERVAL 必須大於 0，目前值：{Config.WEBSOCKET_PING_INTERVAL}")
                
        except Exception as e:
            errors.append(f"配置驗證過程發生錯誤：{str(e)}")
        
        if errors:
            error_msg = (
                "\n" + "="*80 + "\n"
                "錯誤：環境變數配置不合理\n"
                "="*80 + "\n"
                + "\n".join(f"  - {err}" for err in errors) + "\n"
                "="*80 + "\n"
            )
            raise EnvironmentError(error_msg)


class DevelopmentConfig(Config):
    """
    開發環境配置
    
    繼承基礎配置，開發環境特定的覆寫設定
    """
    DEBUG = True


class ProductionConfig(Config):
    """
    生產環境配置
    
    繼承基礎配置，生產環境應額外注意安全性設定
    """
    DEBUG = False


class TestingConfig(Config):
    """
    測試環境配置
    
    繼承基礎配置，用於單元測試與整合測試
    """
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
    """
    獲取當前配置
    
    根據 STATE_MANAGEMENT_FLASK_ENV 環境變數決定使用哪個配置類別
    
    Returns:
        對應環境的配置類別實例
    """
    try:
        env = _get_required_env('STATE_MANAGEMENT_FLASK_ENV')
    except EnvironmentError:
        # 若環境變數未設定，使用開發環境配置
        env = 'development'
    
    return config_dict.get(env, DevelopmentConfig)
