"""
系統預設資源管理
負責建立/同步程式 config 中定義的系統資源
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SystemDefaultsService:
    """保留空殼以兼容匯入，但不再建立任何系統設定"""

    @staticmethod
    def ensure_node_analysis_configs(node_id: str, node_info: Dict[str, Any]):
        return
