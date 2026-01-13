"""
裝置群組視圖
顯示並管理錄音/採集裝置
"""
from flask import render_template, request, jsonify, abort
from flask_login import login_required
from views import views_bp
from utils.mongodb_handler import get_db
from config import get_config
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/devices')
@login_required
def devices_list():
    """
    裝置列表/群組首頁
    顯示所有裝置及其統計資訊
    """
    try:
        config = get_config()
        db = get_db()
        recordings_col = db[config.COLLECTIONS.get('recordings', 'recordings')]

        # 聚合查詢：獲取所有 device_id 及其統計
        pipeline = [
            {
                '$group': {
                    '_id': '$info_features.device_id',
                    'total_recordings': {'$sum': 1},
                    'latest_upload': {'$max': '$info_features.upload_time'},
                    'earliest_upload': {'$min': '$info_features.upload_time'},
                    'dataset_uuids': {'$addToSet': '$info_features.dataset_UUID'},
                    'labels': {'$addToSet': '$info_features.label'},
                    'analyzed_count': {
                        '$sum': {
                            '$cond': [
                                {'$ne': ['$analyze_features.latest_analysis_id', None]},
                                1,
                                0
                            ]
                        }
                    }
                }
            },
            {
                '$project': {
                    'device_id': '$_id',
                    'total_recordings': 1,
                    'latest_upload': 1,
                    'earliest_upload': 1,
                    'dataset_count': {'$size': '$dataset_uuids'},
                    'label_count': {'$size': '$labels'},
                    'labels': 1,
                    'analyzed_count': 1,
                    'pending_analysis': {
                        '$subtract': ['$total_recordings', '$analyzed_count']
                    }
                }
            },
            {'$sort': {'total_recordings': -1}}
        ]

        devices = list(recordings_col.aggregate(pipeline))

        # 總體統計
        stats = {
            'total_devices': len(devices),
            'total_recordings': sum(d.get('total_recordings', 0) for d in devices),
            'total_analyzed': sum(d.get('analyzed_count', 0) for d in devices),
            'total_pending': sum(d.get('pending_analysis', 0) for d in devices)
        }

        return render_template(
            'devices/list.html',
            devices=devices,
            stats=stats
        )

    except Exception as e:
        logger.error(f"載入裝置列表失敗: {e}", exc_info=True)
        return render_template(
            'devices/list.html',
            devices=[],
            stats={'total_devices': 0, 'total_recordings': 0, 'total_analyzed': 0, 'total_pending': 0},
            error=str(e)
        )


@views_bp.route('/devices/<path:device_id>')
@login_required
def device_detail(device_id: str):
    """
    裝置詳情頁
    顯示特定裝置的錄音列表與統計
    """
    try:
        config = get_config()
        db = get_db()
        recordings_col = db[config.COLLECTIONS.get('recordings', 'recordings')]

        # 分頁參數
        page = max(request.args.get('page', 1, type=int), 1)
        page_size = request.args.get('page_size', 20, type=int)
        page_size = max(1, min(page_size, 100))
        skip = (page - 1) * page_size

        # 查詢該裝置的錄音
        query = {'info_features.device_id': device_id}
        total = recordings_col.count_documents(query)

        if total == 0:
            abort(404)

        cursor = recordings_col.find(query).sort('created_at', -1).skip(skip).limit(page_size)

        recordings = []
        for doc in cursor:
            recordings.append({
                'analyze_uuid': doc.get('AnalyzeUUID'),
                'filename': doc.get('files', {}).get('raw', {}).get('filename'),
                'upload_time': doc.get('info_features', {}).get('upload_time'),
                'label': doc.get('info_features', {}).get('label'),
                'has_analysis': doc.get('analyze_features', {}).get('latest_analysis_id') is not None
            })

        # 裝置統計
        device_stats_pipeline = [
            {'$match': query},
            {
                '$group': {
                    '_id': None,
                    'total': {'$sum': 1},
                    'labels': {'$addToSet': '$info_features.label'},
                    'datasets': {'$addToSet': '$info_features.dataset_UUID'},
                    'analyzed': {
                        '$sum': {
                            '$cond': [
                                {'$ne': ['$analyze_features.latest_analysis_id', None]},
                                1,
                                0
                            ]
                        }
                    }
                }
            }
        ]

        stats_result = list(recordings_col.aggregate(device_stats_pipeline))
        device_stats = stats_result[0] if stats_result else {}

        pagination = {
            'page': page,
            'page_size': page_size,
            'total': total,
            'pages': (total + page_size - 1) // page_size
        }

        return render_template(
            'devices/detail.html',
            device_id=device_id,
            recordings=recordings,
            device_stats=device_stats,
            pagination=pagination
        )

    except Exception as e:
        if '404' in str(e):
            abort(404)
        logger.error(f"載入裝置詳情失敗: {e}", exc_info=True)
        abort(500)


@views_bp.route('/api/devices/stats')
@login_required
def devices_stats_api():
    """
    裝置統計 API
    提供實時裝置統計資訊
    """
    try:
        config = get_config()
        db = get_db()
        recordings_col = db[config.COLLECTIONS.get('recordings', 'recordings')]

        # 快速統計
        pipeline = [
            {
                '$group': {
                    '_id': '$info_features.device_id',
                    'count': {'$sum': 1}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'total_devices': {'$sum': 1},
                    'total_recordings': {'$sum': '$count'}
                }
            }
        ]

        result = list(recordings_col.aggregate(pipeline))
        stats = result[0] if result else {'total_devices': 0, 'total_recordings': 0}

        return jsonify({
            'success': True,
            'stats': {
                'total_devices': stats.get('total_devices', 0),
                'total_recordings': stats.get('total_recordings', 0)
            }
        })

    except Exception as e:
        logger.error(f"取得裝置統計失敗: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
