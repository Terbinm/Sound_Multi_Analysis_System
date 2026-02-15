"""
路由規則客戶端
用於從 MongoDB 查詢最新的路由規則，確保分析服務使用最新的 config_id
"""
from typing import Optional
from utils.logger import logger  # 使用分析服務的 logger


class RoutingRuleClient:
    """路由規則查詢客戶端"""

    COLLECTION_NAME = 'routing_rules'

    def __init__(self, mongodb_handler):
        """
        初始化

        Args:
            mongodb_handler: MongoDB 處理器實例
        """
        self.mongodb = mongodb_handler

    def get_config_id_by_router_id(
        self,
        router_id: str,
        analysis_method_id: Optional[str] = None
    ) -> Optional[str]:
        """
        根據 router_id 獲取最新的 config_id

        Args:
            router_id: 路由 ID
            analysis_method_id: 可選的分析方法 ID，用於匹配特定 action

        Returns:
            config_id 或 None
        """
        try:
            collection = self.mongodb.get_collection(self.COLLECTION_NAME)

            # 方式 1：用 router_id 在 router_ids 陣列中查詢
            rule = collection.find_one({
                'router_ids': router_id,
                'enabled': True
            })

            # 方式 2：如果找不到，用 router_id 作為 rule_id 查詢
            if not rule:
                rule = collection.find_one({
                    'rule_id': router_id,
                    'enabled': True
                })

            if not rule:
                logger.info(f"找不到啟用的路由規則: router_id={router_id}")
                return None

            logger.info(f"找到路由規則: rule_id={rule.get('rule_id')}, rule_name={rule.get('rule_name')}")

            actions = rule.get('actions', [])
            if not actions:
                logger.warning(f"路由規則沒有 actions: router_id={router_id}")
                return None

            # 如果指定了 analysis_method_id，尋找匹配的 action
            if analysis_method_id:
                for action in actions:
                    if action.get('analysis_method_id') == analysis_method_id:
                        return action.get('config_id')

            # 否則返回第一個 action 的 config_id
            return actions[0].get('config_id')

        except Exception as e:
            logger.error(f"查詢路由規則失敗: {e}")
            return None
