"""
分析子系統儀表板視圖
顯示分析配置、路由規則、節點狀態等統計資訊
"""
from datetime import datetime, timedelta, timezone
from flask import render_template
from flask_login import login_required
from views import views_bp
from models.analysis_config import AnalysisConfig
from models.routing_rule import RoutingRule
from models.node_status import NodeStatus
from utils.mongodb_handler import get_db
from config import get_config
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/analysis/dashboard')
@login_required
def analysis_dashboard():
    """
    分析子系統首頁
    顯示配置統計、規則統計、節點狀態、最近分析記錄
    """
    try:
        config = get_config()
        db = get_db()

        # 配置統計
        config_stats = {
            'total': AnalysisConfig.count_all(),
            'enabled': AnalysisConfig.count_enabled()
        }

        # 路由規則統計
        routing_stats = {
            'total': RoutingRule.count_all(),
            'enabled': RoutingRule.count_enabled()
        }

        # 節點統計
        all_nodes = NodeStatus.get_all()
        online_nodes = [n for n in all_nodes if n.is_online()]
        node_stats = {
            'total': len(all_nodes),
            'online': len(online_nodes),
            'offline': len(all_nodes) - len(online_nodes)
        }

        # 最近分析任務統計 (從 task_execution_logs 聚合)
        logs_col = db[config.COLLECTIONS.get('task_execution_logs', 'task_execution_logs')]
        recent_analysis_stats = _get_recent_analysis_stats(logs_col)

        # 最近更新的配置
        recent_configs = AnalysisConfig.get_all(limit=5)

        # 最近啟用的路由規則（取前5筆）
        recent_rules = RoutingRule.get_all(enabled_only=True)[:5]

        return render_template(
            'analysis/dashboard.html',
            config_stats=config_stats,
            routing_stats=routing_stats,
            node_stats=node_stats,
            recent_analysis_stats=recent_analysis_stats,
            recent_configs=recent_configs,
            recent_rules=recent_rules,
            online_nodes=online_nodes[:5]
        )

    except Exception as e:
        logger.error(f"載入分析子系統儀表板失敗: {e}", exc_info=True)
        return render_template(
            'analysis/dashboard.html',
            config_stats={'total': 0, 'enabled': 0},
            routing_stats={'total': 0, 'enabled': 0},
            node_stats={'total': 0, 'online': 0, 'offline': 0},
            recent_analysis_stats={'total': 0, 'completed': 0, 'failed': 0, 'pending': 0, 'processing': 0},
            recent_configs=[],
            recent_rules=[],
            online_nodes=[],
            error="載入資料失敗"
        )


def _get_recent_analysis_stats(logs_col) -> dict:
    """
    獲取最近分析任務統計
    統計最近24小時的任務狀態分布
    """
    try:
        yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

        pipeline = [
            {'$match': {'created_at': {'$gte': yesterday}}},
            {'$group': {
                '_id': '$status',
                'count': {'$sum': 1}
            }}
        ]

        stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'pending': 0,
            'processing': 0
        }

        for doc in logs_col.aggregate(pipeline):
            status = doc['_id']
            count = doc['count']
            stats['total'] += count
            if status in stats:
                stats[status] = count

        return stats

    except Exception as e:
        logger.error(f"獲取分析任務統計失敗: {e}")
        return {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'pending': 0,
            'processing': 0
        }
