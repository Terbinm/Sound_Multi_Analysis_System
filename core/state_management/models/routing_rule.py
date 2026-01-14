"""
路由規則模型
管理資料路由規則
"""
import copy
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import logging
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


class RoutingRule:
    """路由規則類"""

    @staticmethod
    def _get_collection():
        config = get_config()
        db = get_db()
        return db[config.COLLECTIONS['routing_rules']]

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        """初始化"""
        if data:
            self.from_dict(data)
        else:
            # 默認值
            self.rule_id = ""
            self.rule_name = ""
            self.description = ""
            self.priority = 0
            self.conditions = {}
            self.actions = []
            self.enabled = True
            self.router_ids = []  # routerID 列表，用於上傳方指定
            self.backfill_enabled = False  # 是否追溯歷史資料
            self.created_at = datetime.now(timezone.utc)
            self.updated_at = datetime.now(timezone.utc)

    def from_dict(self, data: Dict[str, Any]):
        """從字典加載"""
        self.rule_id = data.get('rule_id', '')
        self.rule_name = data.get('rule_name', '')
        self.description = data.get('description', '')
        self.priority = data.get('priority', 0)
        self.conditions = data.get('conditions', {})
        self.actions = data.get('actions', [])
        self.enabled = data.get('enabled', True)
        self.router_ids = data.get('router_ids', [])
        self.backfill_enabled = data.get('backfill_enabled', False)
        self.created_at = data.get('created_at', datetime.now(timezone.utc))
        self.updated_at = data.get('updated_at', datetime.now(timezone.utc))
        return self

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'rule_id': self.rule_id,
            'rule_name': self.rule_name,
            'description': self.description,
            'priority': self.priority,
            'conditions': self.conditions,
            'actions': self.actions,
            'enabled': self.enabled,
            'router_ids': self.router_ids,
            'backfill_enabled': self.backfill_enabled,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def validate(self) -> tuple[bool, str]:
        """驗證數據"""
        if not self.rule_id:
            return False, "缺少 rule_id"

        if not self.rule_name:
            return False, "缺少 rule_name"

        if not self.actions:
            return False, "缺少 actions"

        # 驗證 actions 格式
        for action in self.actions:
            if 'analysis_method_id' not in action:
                return False, "action 缺少 analysis_method_id"
            if 'config_id' not in action:
                return False, "action 缺少 config_id"
            if 'mongodb_instance' not in action:
                return False, "action 缺少 mongodb_instance"

        return True, ""

    def match(self, info_features: Dict[str, Any]) -> bool:
        """
        檢查 info_features 是否符合此規則的條件

        Args:
            info_features: 資料的 info_features

        Returns:
            是否匹配
        """
        try:
            # 遍歷所有條件
            for key, expected_value in self.conditions.items():
                # 支援巢狀欄位（例如 info_features.dataset_UUID 或 mimii_metadata.machine_type）
                actual_value = self._resolve_value(info_features, key)

                # 支持多種匹配方式
                if isinstance(expected_value, list):
                    # 列表匹配（IN 操作）
                    if actual_value not in expected_value:
                        return False
                elif isinstance(expected_value, dict):
                    # 複雜匹配（例如範圍、正則等）
                    if not self._match_complex(actual_value, expected_value):
                        return False
                else:
                    # 精確匹配
                    if actual_value != expected_value:
                        return False

            return True

        except Exception as e:
            logger.error(f"匹配規則失敗: {e}")
            return False

    def _resolve_value(self, info_features: Dict[str, Any], key: str):
        """解析巢狀欄位值，支援 info_features.xx、mimii_metadata.xx 等寫法"""
        if not key:
            return None

        parts = key.split('.')

        # 如果明確包含 info_features 前綴，移除後以內層欄位搜尋
        if parts[0] == 'info_features':
            parts = parts[1:]

        value = info_features
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    def _match_complex(self, actual_value: Any, condition: Dict[str, Any]) -> bool:
        """複雜條件匹配"""
        # $eq - 等於
        if '$eq' in condition:
            return actual_value == condition['$eq']

        # $ne - 不等於
        if '$ne' in condition:
            return actual_value != condition['$ne']

        # $gt - 大於
        if '$gt' in condition:
            return actual_value > condition['$gt']

        # $gte - 大於等於
        if '$gte' in condition:
            return actual_value >= condition['$gte']

        # $lt - 小於
        if '$lt' in condition:
            return actual_value < condition['$lt']

        # $lte - 小於等於
        if '$lte' in condition:
            return actual_value <= condition['$lte']

        # $in - 在列表中
        if '$in' in condition:
            return actual_value in condition['$in']

        # $nin - 不在列表中
        if '$nin' in condition:
            return actual_value not in condition['$nin']

        # 默認返回 False
        return False

    def build_mongodb_query(self) -> Dict[str, Any]:
        """
        將規則的 conditions 轉換為 MongoDB query 格式
        用於查詢符合條件的資料

        Returns:
            MongoDB query dict
        """
        query = {}

        for key, expected_value in self.conditions.items():
            # 處理巢狀欄位路徑
            if key.startswith('info_features.'):
                # 已經包含 info_features 前綴
                field_path = key
            else:
                # 自動添加 info_features 前綴
                field_path = f'info_features.{key}'

            # 根據值類型生成 query
            if isinstance(expected_value, list):
                # 列表匹配（IN 操作）
                query[field_path] = {'$in': expected_value}
            elif isinstance(expected_value, dict):
                # 複雜匹配（已經是運算子格式）
                query[field_path] = expected_value
            else:
                # 精確匹配
                query[field_path] = expected_value

        return query

    @staticmethod
    def create(rule_data: Dict[str, Any]) -> Optional['RoutingRule']:
        """創建新規則"""
        try:
            collection = RoutingRule._get_collection()

            # 創建規則對象
            rule = RoutingRule()
            rule.rule_id = rule_data.get('rule_id', str(uuid.uuid4()))
            rule.rule_name = rule_data['rule_name']
            rule.description = rule_data.get('description', '')
            rule.priority = rule_data.get('priority', 0)
            # 空 conditions 代表匹配所有資料
            rule.conditions = rule_data.get('conditions', {}) or {}
            rule.actions = rule_data['actions']
            rule.enabled = rule_data.get('enabled', True)

            # 處理 router_ids：如果未提供或為空，使用 rule_id 作為預設值
            rule.router_ids = rule_data.get('router_ids', [])
            if not rule.router_ids:
                rule.router_ids = [rule.rule_id]

            rule.backfill_enabled = rule_data.get('backfill_enabled', False)
            rule.created_at = datetime.now(timezone.utc)
            rule.updated_at = datetime.now(timezone.utc)

            # 驗證
            valid, error = rule.validate()
            if not valid:
                logger.error(f"規則驗證失敗: {error}")
                return None

            # 插入資料庫
            result = collection.insert_one(rule.to_dict())

            if result.inserted_id:
                logger.info(f"規則已創建: {rule.rule_id}")
                return rule

            return None

        except Exception as e:
            logger.error(f"創建規則失敗: {e}", exc_info=True)
            return None

    @staticmethod
    def get_by_id(rule_id: str) -> Optional['RoutingRule']:
        """根據 ID 獲取規則"""
        try:
            collection = RoutingRule._get_collection()

            data = collection.find_one({'rule_id': rule_id})
            if data:
                return RoutingRule(data)

            return None

        except Exception as e:
            logger.error(f"獲取規則失敗: {e}")
            return None

    @staticmethod
    def get_by_router_id(router_id: str) -> Optional['RoutingRule']:
        """
        根據 router_id 獲取規則

        Args:
            router_id: routerID（可能是 rule_id 或 router_ids 列表中的任一值）

        Returns:
            匹配的規則，若找不到則返回 None
        """
        try:
            collection = RoutingRule._get_collection()

            # 查找 router_ids 陣列中包含此 router_id 的規則
            data = collection.find_one({'router_ids': router_id})
            if data:
                return RoutingRule(data)

            return None

        except Exception as e:
            logger.error(f"根據 router_id 獲取規則失敗: {e}")
            return None

    @staticmethod
    def get_all(enabled_only: bool = True) -> List['RoutingRule']:
        """獲取所有規則"""
        try:
            collection = RoutingRule._get_collection()

            query = {'enabled': True} if enabled_only else {}
            rules = []

            # 按優先級排序
            for data in collection.find(query).sort('priority', -1):
                rules.append(RoutingRule(data))

            return rules

        except Exception as e:
            logger.error(f"獲取所有規則失敗: {e}")
            return []

    @staticmethod
    def update(rule_id: str, update_data: Dict[str, Any]) -> bool:
        """更新規則"""
        try:
            collection = RoutingRule._get_collection()

            # 更新時間
            update_data['updated_at'] = datetime.now(timezone.utc)

            result = collection.update_one(
                {'rule_id': rule_id},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.info(f"規則已更新: {rule_id}")

                # 更新配置版本
                from models.config_version import ConfigVersion
                ConfigVersion.increment()

                return True

            return False

        except Exception as e:
            logger.error(f"更新規則失敗: {e}")
            return False

    @staticmethod
    def delete(rule_id: str) -> bool:
        """刪除規則"""
        try:
            collection = RoutingRule._get_collection()

            result = collection.delete_one({'rule_id': rule_id})

            if result.deleted_count > 0:
                logger.info(f"規則已刪除: {rule_id}")

                # 更新配置版本
                from models.config_version import ConfigVersion
                ConfigVersion.increment()

                return True

            return False

        except Exception as e:
            logger.error(f"刪除規則失敗: {e}")
            return False

    @staticmethod
    def count_all() -> int:
        """獲取規則總數"""
        try:
            collection = RoutingRule._get_collection()
            return collection.count_documents({})
        except Exception as e:
            logger.error(f"統計規則總數失敗: {e}")
            return 0

    @staticmethod
    def count_enabled() -> int:
        """獲取啟用規則數量"""
        try:
            collection = RoutingRule._get_collection()
            return collection.count_documents({'enabled': True})
        except Exception as e:
            logger.error(f"統計啟用規則數失敗: {e}")
            return 0

    @staticmethod
    def find_matching_rules(info_features: Dict[str, Any]) -> List['RoutingRule']:
        """
        查找所有匹配的規則

        Args:
            info_features: 資料的 info_features

        Returns:
            匹配的規則列表（按優先級排序）
        """
        try:
            # 獲取所有啟用的規則
            all_rules = RoutingRule.get_all(enabled_only=True)

            # 篩選匹配的規則
            matching_rules = [
                rule for rule in all_rules
                if rule.match(info_features)
            ]

            # 已經按優先級排序
            return matching_rules

        except Exception as e:
            logger.error(f"查找匹配規則失敗: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """
        統計符合條件的資料筆數與分析狀態

        Returns:
            dict: {
                'total': int,
                'status_counts': Dict[str, int],
                'generated_at': datetime
            }
        """
        stats = {
            'total': 0,
            'status_counts': {},
            'generated_at': datetime.now(timezone.utc)
        }

        try:
            config = get_config()
            db = get_db()
            collection = db[config.COLLECTIONS['recordings']]

            query = copy.deepcopy(self.conditions) if self.conditions else {}

            stats['total'] = collection.count_documents(query)

            pipeline = [
                {'$match': query},
                {
                    '$group': {
                        '_id': '$analysis_status',
                        'count': {'$sum': 1}
                    }
                }
            ]

            status_counts = {}
            for doc in collection.aggregate(pipeline):
                key = doc.get('_id') or 'unknown'
                status_counts[key] = doc.get('count', 0)

            stats['status_counts'] = status_counts

        except Exception as e:
            logger.error(f"統計路由規則資料失敗 ({self.rule_id}): {e}", exc_info=True)

        return stats
