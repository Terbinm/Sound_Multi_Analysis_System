"""
配置管理器
管理系統配置的加載、緩存和更新
"""
import logging
from typing import Dict, Any, Optional, List

from models.analysis_config import AnalysisConfig
from models.routing_rule import RoutingRule
from models.mongodb_instance import MongoDBInstance
from models.config_version import ConfigVersion
from config import get_config

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器類"""

    def __init__(self):
        """初始化"""
        self.config = get_config()
        self._cache: Dict[str, Any] = {}
        self._version = 0

    def get_config_version(self) -> int:
        """獲取配置版本號"""
        return ConfigVersion.get_version()

    def check_version_changed(self) -> bool:
        """檢查配置版本是否變更"""
        current_version = self.get_config_version()
        if current_version != self._version:
            logger.info(f"配置版本已變更: {self._version} -> {current_version}")
            self._version = current_version
            return True
        return False

    def reload_all_configs(self) -> bool:
        """重新加載所有配置"""
        try:
            logger.info("重新加載所有配置...")

            # 清空緩存
            self._cache = {}

            # 加載分析配置
            self._cache['analysis_configs'] = self._load_analysis_configs()

            # 加載路由規則
            self._cache['routing_rules'] = self._load_routing_rules()

            # 加載 MongoDB 實例
            self._cache['mongodb_instances'] = self._load_mongodb_instances()

            # 更新版本
            self._version = self.get_config_version()

            logger.info("配置重新加載完成")
            return True

        except Exception as e:
            logger.error(f"重新加載配置失敗: {e}", exc_info=True)
            return False

    def _load_analysis_configs(self) -> List[Dict[str, Any]]:
        """加載分析配置"""
        configs = AnalysisConfig.get_all(enabled_only=True)
        return [config.to_dict() for config in configs]

    def _load_routing_rules(self) -> List[Dict[str, Any]]:
        """加載路由規則"""
        rules = RoutingRule.get_all(enabled_only=True)
        return [rule.to_dict() for rule in rules]

    def _load_mongodb_instances(self) -> List[Dict[str, Any]]:
        """加載 MongoDB 實例配置"""
        instances = MongoDBInstance.get_all(
            enabled_only=True,
            ensure_default=True
        )
        return [instance.to_dict() for instance in instances]

    def get_analysis_config(self, config_id: str) -> Optional[Dict[str, Any]]:
        """獲取分析配置"""
        # 檢查緩存
        if 'analysis_configs' in self._cache:
            for config in self._cache['analysis_configs']:
                if config['config_id'] == config_id:
                    return config

        # 從資料庫獲取
        config = AnalysisConfig.get_by_id(config_id)
        if config:
            return config.to_dict()

        return None

    def get_routing_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """獲取路由規則"""
        # 檢查緩存
        if 'routing_rules' in self._cache:
            for rule in self._cache['routing_rules']:
                if rule['rule_id'] == rule_id:
                    return rule

        # 從資料庫獲取
        rule = RoutingRule.get_by_id(rule_id)
        if rule:
            return rule.to_dict()

        return None

    def get_mongodb_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """獲取 MongoDB 實例配置"""
        # 檢查緩存
        if 'mongodb_instances' in self._cache:
            for instance in self._cache['mongodb_instances']:
                if instance['instance_id'] == instance_id:
                    return instance

        # 從資料庫獲取
        instance = MongoDBInstance.get_by_id(instance_id)
        if instance:
            return instance.to_dict()

        return None

    def get_all_analysis_configs(self) -> List[Dict[str, Any]]:
        """獲取所有分析配置"""
        if 'analysis_configs' not in self._cache:
            self._cache['analysis_configs'] = self._load_analysis_configs()

        return self._cache['analysis_configs']

    def get_all_routing_rules(self) -> List[Dict[str, Any]]:
        """獲取所有路由規則"""
        if 'routing_rules' not in self._cache:
            self._cache['routing_rules'] = self._load_routing_rules()

        return self._cache['routing_rules']

    def get_all_mongodb_instances(self) -> List[Dict[str, Any]]:
        """獲取所有 MongoDB 實例配置"""
        if 'mongodb_instances' not in self._cache:
            self._cache['mongodb_instances'] = self._load_mongodb_instances()

        return self._cache['mongodb_instances']


# 全局單例
_manager = None


def get_manager() -> ConfigManager:
    """獲取配置管理器實例"""
    global _manager
    if _manager is None:
        _manager = ConfigManager()
        _manager.reload_all_configs()
    return _manager
