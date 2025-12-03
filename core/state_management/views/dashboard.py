"""
儀表板視圖
顯示系統概覽與統計資訊
"""
from flask import render_template
from flask_login import login_required
from views import views_bp
from models.analysis_config import AnalysisConfig
from models.routing_rule import RoutingRule
from models.mongodb_instance import MongoDBInstance
from models.node_status import NodeStatus
from models.user import User
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/')
@views_bp.route('/dashboard')
@login_required
def dashboard():
    """
    儀表板首頁
    顯示系統整體狀態與統計資訊
    """
    try:
        # 取得統計資料
        stats = {
            'configs': {
                'total': AnalysisConfig.count_all(),
                'enabled': AnalysisConfig.count_enabled()
            },
            'routing_rules': {
                'total': RoutingRule.count_all(),
                'enabled': RoutingRule.count_enabled()
            },
            'mongodb_instances': {
                'total': MongoDBInstance.count_all(),
                'enabled': MongoDBInstance.count_enabled()
            },
            'nodes': {
                'total': NodeStatus.count_all(),
                'online': NodeStatus.count_online()
            },
            'users': {
                'total': User.get_all(include_inactive=True).__len__(),
                'active': User.get_all(include_inactive=False).__len__()
            }
        }

        # 取得最近更新的設定（前5筆）
        recent_configs = AnalysisConfig.get_all(limit=5)

        # 取得在線節點列表
        online_nodes = NodeStatus.get_online_nodes()

        return render_template(
            'dashboard.html',
            stats=stats,
            recent_configs=recent_configs,
            online_nodes=online_nodes
        )

    except Exception as e:
        logger.error(f"載入儀表板資料失敗: {str(e)}")
        return render_template(
            'dashboard.html',
            stats={},
            recent_configs=[],
            online_nodes=[],
            error="載入資料失敗"
        )
