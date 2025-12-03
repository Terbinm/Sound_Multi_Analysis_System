"""
分析配置模型
管理分析方法的配置信息
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


class AnalysisConfig:
    """分析配置類"""

    @staticmethod
    def _get_collection():
        config = get_config()
        db = get_db()
        return db[config.COLLECTIONS['analysis_configs']]

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        """初始化"""
        if data:
            self.from_dict(data)
        else:
            # 默認值
            self.analysis_method_id = ""
            self.config_id = ""
            self.config_name = ""
            self.description = ""
            self.parameters = {}
            self.model_files = {}
            self.created_at = datetime.utcnow()
            self.updated_at = datetime.utcnow()
            self.enabled = True
            self.is_system = False

    def from_dict(self, data: Dict[str, Any]):
        """從字典加載"""
        self.analysis_method_id = data.get('analysis_method_id', '')
        self.config_id = data.get('config_id', '')
        self.config_name = data.get('config_name', '')
        self.description = data.get('description', '')
        self.parameters = data.get('parameters', {})
        self.model_files = data.get('model_files', {})
        self.created_at = data.get('created_at', datetime.utcnow())
        self.updated_at = data.get('updated_at', datetime.utcnow())
        self.enabled = data.get('enabled', True)
        self.is_system = data.get('is_system', False)
        return self

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'analysis_method_id': self.analysis_method_id,
            'config_id': self.config_id,
            'config_name': self.config_name,
            'description': self.description,
            'parameters': self.parameters,
            'model_files': self.model_files,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'enabled': self.enabled,
            'is_system': self.is_system
        }

    def update(self, allow_system: bool = False, **update_data) -> bool:
        """實例方法包裝靜態更新"""
        if not update_data:
            return True
        return AnalysisConfig.update(
            self.config_id,
            update_data,
            allow_system=allow_system
        )

    def validate(self) -> tuple[bool, str]:
        """驗證數據"""
        if not self.analysis_method_id:
            return False, "缺少 analysis_method_id"

        if not self.config_id:
            return False, "缺少 config_id"

        if not self.config_name:
            return False, "缺少 config_name"

        return True, ""

    @staticmethod
    def create(config_data: Dict[str, Any]) -> Optional['AnalysisConfig']:
        """
        創建新配置

        Args:
            config_data: 配置數據

        Returns:
            創建的配置對象，失敗返回 None
        """
        try:
            collection = AnalysisConfig._get_collection()

            # 創建配置對象
            analysis_config = AnalysisConfig()
            analysis_config.analysis_method_id = config_data['analysis_method_id']
            analysis_config.config_id = config_data.get('config_id', str(uuid.uuid4()))
            analysis_config.config_name = config_data['config_name']
            analysis_config.description = config_data.get('description', '')
            analysis_config.parameters = config_data.get('parameters', {})
            analysis_config.model_files = config_data.get('model_files', {})
            analysis_config.created_at = datetime.utcnow()
            analysis_config.updated_at = datetime.utcnow()
            analysis_config.enabled = config_data.get('enabled', True)
            analysis_config.is_system = config_data.get('is_system', False)

            # 驗證
            valid, error = analysis_config.validate()
            if not valid:
                logger.error(f"配置驗證失敗: {error}")
                return None

            # 插入資料庫
            result = collection.insert_one(analysis_config.to_dict())

            if result.inserted_id:
                logger.info(f"配置已創建: {analysis_config.config_id}")
                return analysis_config

            return None

        except Exception as e:
            logger.error(f"創建配置失敗: {e}", exc_info=True)
            return None

    @staticmethod
    def get_by_id(config_id: str) -> Optional['AnalysisConfig']:
        """根據 ID 獲取配置"""
        try:
            collection = AnalysisConfig._get_collection()

            data = collection.find_one({'config_id': config_id})
            if data:
                return AnalysisConfig(data)

            return None

        except Exception as e:
            logger.error(f"獲取配置失敗: {e}")
            return None

    @staticmethod
    def get_by_method_id(analysis_method_id: str) -> List['AnalysisConfig']:
        """根據分析方法 ID 獲取所有配置"""
        try:
            collection = AnalysisConfig._get_collection()

            configs = []
            for data in collection.find({'analysis_method_id': analysis_method_id}):
                configs.append(AnalysisConfig(data))

            return configs

        except Exception as e:
            logger.error(f"獲取配置列表失敗: {e}")
            return []

    @staticmethod
    def get_all(
        enabled_only: bool = False,
        limit: Optional[int] = None
    ) -> List['AnalysisConfig']:
        """獲取所有配置"""
        try:
            collection = AnalysisConfig._get_collection()

            query = {'enabled': True} if enabled_only else {}
            cursor = collection.find(query).sort('created_at', -1)

            if limit is not None:
                cursor = cursor.limit(limit)

            return [AnalysisConfig(data) for data in cursor]

        except Exception as e:
            logger.error(f"獲取所有配置失敗: {e}")
            return []

    @staticmethod
    def update(
        config_id: str,
        update_data: Dict[str, Any],
        allow_system: bool = False
    ) -> bool:
        """更新配置"""
        try:
            collection = AnalysisConfig._get_collection()

            existing = collection.find_one({'config_id': config_id})
            if not existing:
                logger.warning(f"配置不存在: {config_id}")
                return False

            if existing.get('is_system') and not allow_system:
                logger.warning(f"禁止修改系統配置: {config_id}")
                return False

            # 更新時間
            update_data['updated_at'] = datetime.utcnow()

            result = collection.update_one(
                {'config_id': config_id},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.info(f"配置已更新: {config_id}")

                # 更新配置版本
                from models.config_version import ConfigVersion
                ConfigVersion.increment()

                return True

            return False

        except Exception as e:
            logger.error(f"更新配置失敗: {e}")
            return False

    @staticmethod
    def delete(config_id: str, allow_system: bool = False) -> bool:
        """刪除配置"""
        try:
            collection = AnalysisConfig._get_collection()

            existing = collection.find_one({'config_id': config_id})
            if not existing:
                logger.warning(f"配置不存在: {config_id}")
                return False

            if existing.get('is_system') and not allow_system:
                logger.warning(f"禁止刪除系統配置: {config_id}")
                return False

            result = collection.delete_one({'config_id': config_id})

            if result.deleted_count > 0:
                logger.info(f"配置已刪除: {config_id}")

                # 更新配置版本
                from models.config_version import ConfigVersion
                ConfigVersion.increment()

                return True

            return False

        except Exception as e:
            logger.error(f"刪除配置失敗: {e}")
            return False

    @staticmethod
    def exists(config_id: str) -> bool:
        """檢查配置是否存在"""
        try:
            collection = AnalysisConfig._get_collection()

            return collection.count_documents({'config_id': config_id}) > 0

        except Exception as e:
            logger.error(f"檢查配置存在失敗: {e}")
            return False

    @staticmethod
    def count_all() -> int:
        """獲取配置總數"""
        try:
            collection = AnalysisConfig._get_collection()
            return collection.count_documents({})
        except Exception as e:
            logger.error(f"統計配置總數失敗: {e}")
            return 0

    @staticmethod
    def count_enabled() -> int:
        """獲取啟用配置數量"""
        try:
            collection = AnalysisConfig._get_collection()
            return collection.count_documents({'enabled': True})
        except Exception as e:
            logger.error(f"統計啟用配置數失敗: {e}")
            return 0
