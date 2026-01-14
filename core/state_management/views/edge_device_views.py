"""
邊緣設備管理視圖
顯示並管理邊緣錄音設備，包括即時錄音控制與排程管理
"""
from flask import render_template, request, jsonify, abort
from flask_login import login_required
from views import views_bp
from models.edge_device import EdgeDevice
from models.routing_rule import RoutingRule
from utils.mongodb_handler import get_db
from config import get_config
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/edge-devices')
@login_required
def edge_devices_list():
    """
    邊緣設備列表頁
    顯示所有邊緣設備及其狀態統計
    """
    try:
        # 取得所有設備
        devices = EdgeDevice.get_all()

        # 統計資訊
        stats = {
            'total_devices': len(devices),
            'online_devices': sum(1 for d in devices if d.get('status') == 'IDLE'),
            'offline_devices': sum(1 for d in devices if d.get('status') == 'OFFLINE'),
            'recording_devices': sum(1 for d in devices if d.get('status') == 'RECORDING')
        }

        return render_template(
            'edge_devices/list.html',
            devices=devices,
            stats=stats
        )

    except Exception as e:
        logger.error(f"載入邊緣設備列表失敗: {e}", exc_info=True)
        return render_template(
            'edge_devices/list.html',
            devices=[],
            stats={
                'total_devices': 0,
                'online_devices': 0,
                'offline_devices': 0,
                'recording_devices': 0
            },
            error=str(e)
        )


@views_bp.route('/edge-devices/<device_id>')
@login_required
def edge_device_detail(device_id: str):
    """
    邊緣設備詳情頁
    顯示設備詳細資訊、音訊配置、排程設定及近期錄音
    """
    try:
        # 取得設備資訊
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            abort(404)

        # 從 recordings 集合取得近期錄音歷史（最近 10 筆）
        db = get_db()
        config = get_config()
        recordings_collection = db[config.COLLECTIONS.get('recordings', 'recordings')]

        cursor = recordings_collection.find(
            {'info_features.device_id': device_id}
        ).sort('created_at', -1).limit(10)

        recent_recordings = []
        for record in cursor:
            recent_recordings.append({
                'analyze_uuid': record.get('AnalyzeUUID'),
                'duration': record.get('info_features', {}).get('duration'),
                'filename': record.get('files', {}).get('raw', {}).get('filename'),
                'assigned_router_ids': record.get('assigned_router_ids', []),
                'created_at': record.get('created_at')
            })

        # 取得設備統計
        device_stats = device.get('statistics', {})

        # 取得所有可用的路由規則
        available_routers = RoutingRule.get_all(enabled_only=True)
        routers_data = [
            {
                'rule_id': r.rule_id,
                'rule_name': r.rule_name,
                'description': r.description,
                'priority': r.priority
            }
            for r in available_routers
        ]

        return render_template(
            'edge_devices/detail.html',
            device=device,
            recent_recordings=recent_recordings,
            device_stats=device_stats,
            available_routers=routers_data
        )

    except Exception as e:
        if '404' in str(e):
            abort(404)
        logger.error(f"載入邊緣設備詳情失敗: {e}", exc_info=True)
        abort(500)


@views_bp.route('/edge-devices/<device_id>/recordings')
@login_required
def edge_device_recordings(device_id: str):
    """
    邊緣設備錄音歷史頁
    顯示設備的完整錄音歷史記錄（從 recordings 集合）
    """
    try:
        # 取得設備資訊
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            abort(404)

        # 分頁參數
        page = max(request.args.get('page', 1, type=int), 1)
        page_size = request.args.get('page_size', 20, type=int)
        page_size = max(1, min(page_size, 100))

        # 從 recordings 集合取得錄音歷史
        db = get_db()
        config = get_config()
        recordings_collection = db[config.COLLECTIONS.get('recordings', 'recordings')]

        query = {'info_features.device_id': device_id}
        total = recordings_collection.count_documents(query)

        skip = (page - 1) * page_size
        cursor = recordings_collection.find(query).sort('created_at', -1).skip(skip).limit(page_size)

        recordings = []
        for record in cursor:
            recordings.append({
                'analyze_uuid': record.get('AnalyzeUUID'),
                'duration': record.get('info_features', {}).get('duration'),
                'file_size': record.get('info_features', {}).get('file_size'),
                'filename': record.get('files', {}).get('raw', {}).get('filename'),
                'assigned_router_ids': record.get('assigned_router_ids', []),
                'created_at': record.get('created_at')
            })

        pagination = {
            'page': page,
            'page_size': page_size,
            'total': total,
            'pages': (total + page_size - 1) // page_size if total > 0 else 1
        }

        return render_template(
            'edge_devices/recordings.html',
            device=device,
            recordings=recordings,
            pagination=pagination
        )

    except Exception as e:
        if '404' in str(e):
            abort(404)
        logger.error(f"載入邊緣設備錄音歷史失敗: {e}", exc_info=True)
        abort(500)


@views_bp.route('/api/edge-devices/stats')
@login_required
def edge_devices_stats_api():
    """
    邊緣設備統計 API
    提供即時統計資訊供前端輪詢或 WebSocket 備用
    """
    try:
        devices = EdgeDevice.get_all()

        stats = {
            'total_devices': len(devices),
            'online_devices': sum(1 for d in devices if d.get('status') == 'IDLE'),
            'offline_devices': sum(1 for d in devices if d.get('status') == 'OFFLINE'),
            'recording_devices': sum(1 for d in devices if d.get('status') == 'RECORDING'),
            'schedule_enabled': sum(1 for d in devices if d.get('schedule_config', {}).get('enabled'))
        }

        return jsonify({
            'success': True,
            'stats': stats
        })

    except Exception as e:
        logger.error(f"取得邊緣設備統計失敗: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
