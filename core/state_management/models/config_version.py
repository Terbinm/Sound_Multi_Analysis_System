"""
配置版本管理
使用 MongoDB 存儲配置版本號,取代 Redis
"""
import logging
from datetime import datetime, timezone
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


class ConfigVersion:
    """配置版本管理類 - 使用 MongoDB 存儲"""

    VERSION_KEY = 'config_version'

    @staticmethod
    def _get_collection_name():
        """從 config 獲取集合名稱"""
        config = get_config()
        return config.COLLECTIONS['system_metadata']

    @staticmethod
    def get_version() -> int:
        """
        獲取當前配置版本號

        Returns:
            版本號
        """
        try:
            db = get_db()
            collection = db[ConfigVersion._get_collection_name()]

            doc = collection.find_one({'_id': ConfigVersion.VERSION_KEY})

            if doc:
                return doc.get('value', 0)
            else:
                # 初始化版本號
                collection.insert_one({
                    '_id': ConfigVersion.VERSION_KEY,
                    'value': 0,
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                })
                return 0

        except Exception as e:
            logger.error(f"獲取配置版本失敗: {e}")
            return 0

    @staticmethod
    def increment() -> int:
        """
        遞增配置版本號（原子操作）

        Returns:
            新的版本號
        """
        try:
            db = get_db()
            collection = db[ConfigVersion._get_collection_name()]

            # 使用 findOneAndUpdate + $inc 確保原子性
            result = collection.find_one_and_update(
                {'_id': ConfigVersion.VERSION_KEY},
                {
                    '$inc': {'value': 1},
                    '$set': {'updated_at': datetime.now(timezone.utc)},
                    '$setOnInsert': {'created_at': datetime.now(timezone.utc)}
                },
                upsert=True,
                return_document=True  # 返回更新後的文檔
            )

            new_version = result.get('value', 1)
            logger.info(f"配置版本已更新: {new_version}")

            return new_version

        except Exception as e:
            logger.error(f"遞增配置版本失敗: {e}")
            return 0

    @staticmethod
    def set_version(version: int) -> bool:
        """
        設置配置版本號（通常用於初始化或遷移）

        Args:
            version: 版本號

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[ConfigVersion._get_collection_name()]

            collection.update_one(
                {'_id': ConfigVersion.VERSION_KEY},
                {
                    '$set': {
                        'value': version,
                        'updated_at': datetime.now(timezone.utc)
                    },
                    '$setOnInsert': {'created_at': datetime.now(timezone.utc)}
                },
                upsert=True
            )

            logger.info(f"配置版本已設置: {version}")
            return True

        except Exception as e:
            logger.error(f"設置配置版本失敗: {e}")
            return False
