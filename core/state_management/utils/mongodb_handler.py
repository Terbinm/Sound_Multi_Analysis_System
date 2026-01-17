"""
MongoDB 處理器
提供 MongoDB 連接和操作功能
"""
import logging
from typing import Dict, Any, List, Optional
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import PyMongoError, ConnectionFailure, OperationFailure
from config import get_config

logger = logging.getLogger(__name__)


class MongoDBHandler:
    """MongoDB 處理器類"""

    _instance = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    def __new__(cls):
        """單例模式"""
        if cls._instance is None:
            cls._instance = super(MongoDBHandler, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化"""
        if self._client is None:
            self._connect()

    def _connect(self):
        """建立 MongoDB 連接"""
        try:
            config = get_config()
            uri = config.get_mongodb_uri()

            self._client = MongoClient(
                uri,
                serverSelectionTimeoutMS=config.MONGODB_CONFIG['server_selection_timeout_ms']
            )

            # 測試連接
            self._client.admin.command('ping')

            # 獲取資料庫
            self._db = self._client[config.MONGODB_CONFIG['database']]

            logger.info(f"MongoDB 連接成功: {config.MONGODB_CONFIG['database']}")

            # 創建索引
            self._create_indexes()

        except ConnectionFailure as e:
            logger.error(f"MongoDB 連接失敗: {e}")
            raise
        except Exception as e:
            logger.error(f"MongoDB 初始化錯誤: {e}")
            raise

    def _ensure_index(self, collection: Collection, keys, name: str, **kwargs):
        """安全建立索引，避免名稱或參數衝突"""
        index_kwargs = {'name': name, 'background': True}
        index_kwargs.update(kwargs)

        # _id 索引不允許 background / unique 參數
        if len(keys) == 1 and keys[0][0] == '_id':
            index_kwargs.pop('background', None)
            index_kwargs.pop('unique', None)

        try:
            collection.create_index(keys, **index_kwargs)
        except OperationFailure as e:
            if e.code in (85, 86):
                logger.warning(
                    "索引衝突，嘗試重新建立 %s: %s",
                    name,
                    e.details.get('errmsg') if hasattr(e, 'details') else str(e)
                )

                existing_name = (
                    name if e.code == 86 else self._find_existing_index(collection, keys)
                )

                if not existing_name:
                    existing_name = self._parse_existing_index_name(e)

                if existing_name:
                    try:
                        collection.drop_index(existing_name)
                        collection.create_index(keys, **index_kwargs)
                        return
                    except Exception as recreate_error:
                        logger.error(
                            "重新建立索引失敗 %s: %s",
                            name,
                            recreate_error
                        )

            logger.warning(f"建立索引失敗 ({name}): {e}")
        except Exception as e:
            logger.warning(f"建立索引失敗 ({name}): {e}")

    def _find_existing_index(self, collection: Collection, keys) -> Optional[str]:
        """尋找與給定 keys 相同的現有索引名稱"""
        key_doc = dict(keys)
        try:
            for index in collection.list_indexes():
                if dict(index['key']) == key_doc:
                    return index['name']
        except Exception as e:
            logger.debug(f"列出索引失敗: {e}")
        return None

    def _parse_existing_index_name(self, error: OperationFailure) -> Optional[str]:
        message = ''
        if hasattr(error, 'details') and error.details:
            message = error.details.get('errmsg', '')
        if not message:
            message = str(error)

        if ':' in message:
            candidate = message.split(':')[-1].strip().strip('.')
            if candidate:
                return candidate
        return None

    def _create_indexes(self):
        """創建必要的索引"""
        try:
            config = get_config()

            # recordings 集合索引
            recordings = self._db[config.COLLECTIONS['recordings']]
            self._ensure_index(
                recordings,
                [('AnalyzeUUID', ASCENDING)],
                name='idx_recordings_analyze_uuid',
                unique=True
            )
            self._ensure_index(
                recordings,
                [('info_features.dataset_UUID', ASCENDING)],
                name='idx_recordings_dataset_uuid'
            )
            self._ensure_index(
                recordings,
                [('info_features.device_id', ASCENDING)],
                name='idx_recordings_device_id'
            )
            self._ensure_index(
                recordings,
                [('info_features.upload_time', DESCENDING)],
                name='idx_recordings_upload_time'
            )
            self._ensure_index(
                recordings,
                [('analyze_features.active_analysis_id', ASCENDING)],
                name='idx_recordings_active_analysis_id'
            )

            # analysis_configs 集合索引
            configs = self._db[config.COLLECTIONS['analysis_configs']]
            self._ensure_index(
                configs,
                [('analysis_method_id', ASCENDING)],
                name='idx_analysis_configs_method_id'
            )
            self._ensure_index(
                configs,
                [('config_id', ASCENDING)],
                name='idx_analysis_configs_config_id',
                unique=True
            )

            # routing_rules 集合索引
            rules = self._db[config.COLLECTIONS['routing_rules']]
            self._ensure_index(
                rules,
                [('rule_id', ASCENDING)],
                name='idx_routing_rules_rule_id',
                unique=True
            )
            self._ensure_index(
                rules,
                [('enabled', ASCENDING)],
                name='idx_routing_rules_enabled'
            )
            self._ensure_index(
                rules,
                [('priority', DESCENDING)],
                name='idx_routing_rules_priority'
            )

            # mongodb_instances 集合索引
            instances = self._db[config.COLLECTIONS['mongodb_instances']]
            self._ensure_index(
                instances,
                [('instance_id', ASCENDING)],
                name='idx_mongodb_instances_instance_id',
                unique=True
            )
            self._ensure_index(
                instances,
                [('enabled', ASCENDING)],
                name='idx_mongodb_instances_enabled'
            )

            # nodes_status 集合索引（取代 Redis）
            nodes_status = self._db[config.COLLECTIONS['node_status']]
            # TTL Index: 自動清理超過設定時間無心跳的節點
            self._ensure_index(
                nodes_status,
                [('last_heartbeat', ASCENDING)],
                name='idx_nodes_status_last_heartbeat',
                expireAfterSeconds=config.NODE_HEARTBEAT_TIMEOUT
            )
            self._ensure_index(
                nodes_status,
                [('created_at', DESCENDING)],
                name='idx_nodes_status_created_at'
            )

            # system_metadata 集合索引
            system_metadata = self._db[config.COLLECTIONS['system_metadata']]
            self._ensure_index(
                system_metadata,
                [('_id', ASCENDING)],
                name='idx_system_metadata_id',
                unique=True
            )

            logger.info("MongoDB 索引創建完成")

        except Exception as e:
            logger.warning(f"創建索引時發生錯誤: {e}")

    def get_database(self) -> Database:
        """獲取資料庫對象"""
        if self._db is None:
            self._connect()
        return self._db

    def get_collection(self, collection_name: str) -> Collection:
        """獲取集合對象"""
        return self.get_database()[collection_name]

    def close(self):
        """關閉連接"""
        if self._client:
            self._client.close()
            logger.info("MongoDB 連接已關閉")


class MultiMongoDBHandler:
    """多 MongoDB instance處理器"""

    def __init__(self):
        self._connections: Dict[str, MongoClient] = {}
        self.logger = logging.getLogger(__name__)

    def connect(self, instance_id: str, instance_config: Dict[str, Any]) -> Database:
        """連接到指定的 MongoDB instance"""
        try:
            # 如果已經存在連接，直接返回
            if instance_id in self._connections:
                client = self._connections[instance_id]
                return client[instance_config['database']]

            # 從 config 獲取超時設定
            from config import get_config
            config = get_config()
            timeout_ms = config.MONGODB_CONFIG.get('server_selection_timeout_ms', 5000)

            # 建立新連接
            uri = f"mongodb://{instance_config['username']}:{instance_config['password']}@" \
                  f"{instance_config['host']}:{instance_config['port']}/admin"

            client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)

            # 測試連接
            client.admin.command('ping')

            # 保存連接
            self._connections[instance_id] = client

            self.logger.info(f"連接到 MongoDB instance: {instance_id}")

            return client[instance_config['database']]

        except Exception as e:
            self.logger.error(f"連接 MongoDB instance {instance_id} 失敗: {e}")
            raise

    def get_connection(self, instance_id: str) -> Optional[MongoClient]:
        """獲取指定instance的連接"""
        return self._connections.get(instance_id)

    def disconnect(self, instance_id: str):
        """斷開指定instance的連接"""
        if instance_id in self._connections:
            self._connections[instance_id].close()
            del self._connections[instance_id]
            self.logger.info(f"斷開 MongoDB instance連接: {instance_id}")

    def disconnect_all(self):
        """斷開所有連接"""
        for instance_id in list(self._connections.keys()):
            self.disconnect(instance_id)

    def __del__(self):
        """析構函數，清理連接"""
        self.disconnect_all()


# 全局單例instance
_handler = None


def get_db() -> Database:
    """獲取默認 MongoDB 資料庫"""
    global _handler
    if _handler is None:
        _handler = MongoDBHandler()
    return _handler.get_database()


def get_handler() -> MongoDBHandler:
    """獲取 MongoDB 處理器instance"""
    global _handler
    if _handler is None:
        _handler = MongoDBHandler()
    return _handler
