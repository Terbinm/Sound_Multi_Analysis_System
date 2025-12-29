"""
MongoDB 實例模型
管理多個 MongoDB 實例配置
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


class MongoDBInstance:
    """MongoDB 實例類"""

    DEFAULT_INSTANCE_ID = 'default'

    @staticmethod
    def _get_collection():
        config = get_config()
        db = get_db()
        return db[config.COLLECTIONS['mongodb_instances']]

    @classmethod
    def _build_default_instance(cls) -> 'MongoDBInstance':
        """根據配置構建預設實例"""
        config = get_config()
        mongo_cfg = config.MONGODB_CONFIG

        default_data = {
            'instance_id': cls.DEFAULT_INSTANCE_ID,
            'instance_name': 'Default MongoDB',
            'description': '由 config.py 定義的預設 MongoDB 實例',
            'host': mongo_cfg['host'],
            'port': mongo_cfg['port'],
            'username': mongo_cfg['username'],
            'password': mongo_cfg['password'],
            'database': mongo_cfg['database'],
            'collection': config.COLLECTIONS['recordings'],
            'auth_source': mongo_cfg.get('auth_source', 'admin'),
            'enabled': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_system': True
        }

        return MongoDBInstance(default_data)

    @staticmethod
    def _mask_password(instances: List['MongoDBInstance'], include_password: bool):
        if include_password:
            return
        for instance in instances:
            instance.password = ''

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        """初始化"""
        if data:
            self.from_dict(data)
        else:
            # 不提供預設值，必須透過 from_dict 或明確賦值
            config = get_config()
            self.instance_id = ""
            self.instance_name = ""
            self.description = ""
            self.host = ""
            self.port = None  # 必須明確指定
            self.username = ""
            self.password = ""
            self.database = ""
            self.collection = ""  # 必須明確指定
            self.auth_source = ""  # 必須明確指定
            self.enabled = True
            self.created_at = datetime.utcnow()
            self.updated_at = datetime.utcnow()
            self.is_system = False

    def from_dict(self, data: Dict[str, Any]):
        """從字典加載"""
        config = get_config()
        self.instance_id = data.get('instance_id', '')
        self.instance_name = data.get('instance_name', '')
        self.description = data.get('description', '')
        self.host = data.get('host', '')
        self.port = data.get('port')  # 不提供預設值
        self.username = data.get('username', '')
        self.password = data.get('password', '')
        self.database = data.get('database', '')
        self.collection = data.get('collection')  # 不提供預設值
        self.auth_source = data.get('auth_source')  # 不提供預設值
        self.enabled = data.get('enabled', True)
        self.created_at = data.get('created_at', datetime.utcnow())
        self.updated_at = data.get('updated_at', datetime.utcnow())
        self.is_system = data.get('is_system', False)
        return self

    def to_dict(self, include_password: bool = True) -> Dict[str, Any]:
        """
        轉換為字典

        Args:
            include_password: 是否包含密碼（默認 True）
        """
        data = {
            'instance_id': self.instance_id,
            'instance_name': self.instance_name,
            'description': self.description,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'database': self.database,
            'collection': self.collection,
            'auth_source': self.auth_source,
            'enabled': self.enabled,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'is_system': self.is_system
        }

        if include_password:
            data['password'] = self.password

        return data

    def get_connection_config(self) -> Dict[str, Any]:
        """獲取連接配置"""
        return {
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'database': self.database,
            'collection': self.collection,
            'auth_source': self.auth_source
        }

    def get_uri(self) -> str:
        """獲取連接 URI"""
        return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/{self.auth_source}"

    def validate(self) -> tuple[bool, str]:
        """驗證數據"""
        if not self.instance_id:
            return False, "缺少 instance_id"

        if not self.instance_name:
            return False, "缺少 instance_name"

        if not self.host:
            return False, "缺少 host"

        if not self.username:
            return False, "缺少 username"

        if not self.password:
            return False, "缺少 password"

        if not self.database:
            return False, "缺少 database"

        return True, ""

    @staticmethod
    def create(instance_data: Dict[str, Any]) -> Optional['MongoDBInstance']:
        """創建新實例配置"""
        try:
            collection = MongoDBInstance._get_collection()

            # 創建實例對象
            config = get_config()
            instance = MongoDBInstance()
            instance.instance_id = instance_data.get('instance_id', str(uuid.uuid4()))
            if instance.instance_id == MongoDBInstance.DEFAULT_INSTANCE_ID:
                logger.error("instance_id 'default' 為保留值")
                return None
            instance.instance_name = instance_data['instance_name']
            instance.description = instance_data.get('description', '')
            instance.host = instance_data['host']
            instance.port = instance_data.get('port')  # 必須明確提供
            instance.username = instance_data['username']
            instance.password = instance_data['password']
            instance.database = instance_data['database']
            instance.collection = instance_data.get('collection')  # 必須明確提供
            instance.auth_source = instance_data.get('auth_source')  # 必須明確提供
            instance.enabled = instance_data.get('enabled', True)
            instance.created_at = datetime.utcnow()
            instance.updated_at = datetime.utcnow()
            instance.is_system = instance_data.get('is_system', False)

            # 驗證
            valid, error = instance.validate()
            if not valid:
                logger.error(f"實例配置驗證失敗: {error}")
                return None

            # 插入資料庫
            result = collection.insert_one(instance.to_dict())

            if result.inserted_id:
                logger.info(f"實例配置已創建: {instance.instance_id}")
                return instance

            return None

        except Exception as e:
            logger.error(f"創建實例配置失敗: {e}", exc_info=True)
            return None

    def update(self, allow_system: bool = False, **update_data) -> bool:
        """實例方法包裝更新"""
        if not update_data:
            return True
        return MongoDBInstance.update(
            self.instance_id,
            update_data,
            allow_system=allow_system
        )

    @staticmethod
    def get_by_id(
        instance_id: str,
        include_password: bool = True
    ) -> Optional['MongoDBInstance']:
        """根據 ID 獲取實例配置"""
        try:
            collection = MongoDBInstance._get_collection()

            data = collection.find_one({'instance_id': instance_id})

            if data:
                instance = MongoDBInstance(data)
            elif instance_id == MongoDBInstance.DEFAULT_INSTANCE_ID:
                instance = MongoDBInstance._build_default_instance()
            else:
                return None

            if not include_password:
                instance.password = ''

            return instance

        except Exception as e:
            logger.error(f"獲取實例配置失敗: {e}")
            return None

    @staticmethod
    def get_all(
        enabled_only: bool = False,
        include_password: bool = True,
        ensure_default: bool = False
    ) -> List['MongoDBInstance']:
        """獲取所有實例配置"""
        try:
            collection = MongoDBInstance._get_collection()

            query = {'enabled': True} if enabled_only else {}
            instances = [
                MongoDBInstance(data)
                for data in collection.find(query).sort('created_at', -1)
            ]

            if ensure_default and not instances:
                instances = [MongoDBInstance._build_default_instance()]

            MongoDBInstance._mask_password(instances, include_password)
            return instances

        except Exception as e:
            logger.error(f"獲取所有實例配置失敗: {e}")

            if ensure_default:
                fallback = [MongoDBInstance._build_default_instance()]
                MongoDBInstance._mask_password(fallback, include_password)
                return fallback

            return []

    @staticmethod
    def update(
        instance_id: str,
        update_data: Dict[str, Any],
        allow_system: bool = False
    ) -> bool:
        """更新實例配置"""
        try:
            collection = MongoDBInstance._get_collection()

            existing = collection.find_one({'instance_id': instance_id})
            if not existing:
                logger.warning(f"實例配置不存在: {instance_id}")
                return False

            if existing.get('is_system') and not allow_system:
                logger.warning(f"禁止修改系統 MongoDB 實例: {instance_id}")
                return False

            # 更新時間
            update_data['updated_at'] = datetime.utcnow()

            result = collection.update_one(
                {'instance_id': instance_id},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.info(f"實例配置已更新: {instance_id}")

                # 更新配置版本
                from models.config_version import ConfigVersion
                ConfigVersion.increment()

                return True

            return False

        except Exception as e:
            logger.error(f"更新實例配置失敗: {e}")
            return False

    @staticmethod
    def delete(instance_id: str, allow_system: bool = False) -> bool:
        """刪除實例配置"""
        try:
            collection = MongoDBInstance._get_collection()

            existing = collection.find_one({'instance_id': instance_id})
            if not existing:
                logger.warning(f"實例配置不存在: {instance_id}")
                return False

            if existing.get('is_system') and not allow_system:
                logger.warning(f"禁止刪除系統 MongoDB 實例: {instance_id}")
                return False

            result = collection.delete_one({'instance_id': instance_id})

            if result.deleted_count > 0:
                logger.info(f"實例配置已刪除: {instance_id}")

                # 更新配置版本
                from models.config_version import ConfigVersion
                ConfigVersion.increment()

                return True

            return False

        except Exception as e:
            logger.error(f"刪除實例配置失敗: {e}")
            return False

    @staticmethod
    def count_all() -> int:
        """獲取實例總數（包含預設實例）"""
        try:
            collection = MongoDBInstance._get_collection()
            count = collection.count_documents({})
            return count if count > 0 else 1
        except Exception as e:
            logger.error(f"統計實例總數失敗: {e}")
            return 1

    @staticmethod
    def count_enabled() -> int:
        """獲取啟用實例數量（包含預設實例）"""
        try:
            collection = MongoDBInstance._get_collection()
            count = collection.count_documents({'enabled': True})
            return count if count > 0 else 1
        except Exception as e:
            logger.error(f"統計啟用實例數失敗: {e}")
            return 1

    def test_connection(self) -> tuple[bool, str]:
        """以當前實例測試連線"""
        return MongoDBInstance.test_connection_by_id(self.instance_id)

    @staticmethod
    def test_connection_by_id(instance_id: str) -> tuple[bool, str]:
        """
        測試連接

        Returns:
            (是否成功, 錯誤信息)
        """
        try:
            instance = MongoDBInstance.get_by_id(instance_id)
            if not instance:
                return False, "實例配置不存在"

            # 嘗試連接
            from utils.mongodb_handler import MultiMongoDBHandler
            handler = MultiMongoDBHandler()

            db = handler.connect(instance_id, instance.get_connection_config())

            # 測試 ping
            db.command('ping')

            # 測試查詢
            db[instance.collection].count_documents({}, limit=1)

            handler.disconnect(instance_id)

            logger.info(f"實例連接測試成功: {instance_id}")
            return True, "連接成功"

        except Exception as e:
            error_msg = f"連接失敗: {str(e)}"
            logger.error(f"實例連接測試失敗 ({instance_id}): {e}")
            return False, error_msg
