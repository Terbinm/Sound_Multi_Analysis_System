"""
節點管理 API
提供分析節點的註冊、心跳和狀態管理
"""
import logging
from flask import Blueprint, request, jsonify
from models.node_status import NodeStatus
from services.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

node_bp = Blueprint('node_api', __name__)


@node_bp.route('/register', methods=['POST'])
def register_node():
    """註冊節點"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 必填欄位
        required_fields = ['node_id', 'capabilities']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必填欄位: {field}'
                }), 400

        node_id = data['node_id']
        node_info = {
            'capabilities': data['capabilities'],
            'version': data.get('version', 'unknown'),
            'max_concurrent_tasks': data.get('max_concurrent_tasks', 1),
            'tags': data.get('tags', [])
        }

        # 註冊節點（使用 MongoDB）
        success = NodeStatus.register_node(node_id, node_info)

        if not success:
            return jsonify({
                'success': False,
                'error': '註冊節點失敗'
            }), 500

        logger.info(f"節點已註冊: {node_id}")

        # 推送節點註冊事件到 WebSocket
        websocket_manager.emit_node_registered({
            'node_id': node_id,
            'status': 'online',
            'capabilities': data['capabilities'],
            'version': node_info.get('version', 'unknown'),
            'max_concurrent_tasks': node_info.get('max_concurrent_tasks', 1),
            'tags': node_info.get('tags', [])
        })

        return jsonify({
            'success': True,
            'data': {
                'node_id': node_id,
                'status': 'online'
            },
            'message': '節點註冊成功'
        }), 201

    except Exception as e:
        logger.error(f"註冊節點失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@node_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """接收節點心跳"""
    try:
        data = request.get_json()

        if not data or 'node_id' not in data:
            return jsonify({
                'success': False,
                'error': '缺少 node_id'
            }), 400

        node_id = data['node_id']
        current_tasks = data.get('current_tasks', 0)

        # 更新心跳（使用 MongoDB）
        success = NodeStatus.update_heartbeat(node_id, current_tasks)

        if not success:
            return jsonify({
                'success': False,
                'error': '更新心跳失敗'
            }), 500

        # 獲取節點信息以計算負載率
        node_info = NodeStatus.get_node_info(node_id)
        max_tasks = node_info.get('max_concurrent_tasks', 1) if node_info else 1
        load_ratio = (current_tasks / max_tasks) * 100 if max_tasks > 0 else 0

        # 推送節點心跳事件到 WebSocket
        websocket_manager.emit_node_heartbeat({
            'node_id': node_id,
            'status': 'online',
            'current_tasks': current_tasks,
            'max_concurrent_tasks': max_tasks,
            'load_ratio': round(load_ratio, 2),
            'timestamp': node_info.get('last_heartbeat') if node_info else None,
            'capability': node_info.get('capability', 'unknown') if node_info else 'unknown'
        })

        return jsonify({
            'success': True,
            'message': '心跳已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新心跳失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@node_bp.route('', methods=['GET'])
def get_all_nodes():
    """獲取所有節點"""
    try:
        nodes = NodeStatus.get_all_nodes()

        return jsonify({
            'success': True,
            'data': nodes,
            'count': len(nodes)
        }), 200

    except Exception as e:
        logger.error(f"獲取節點列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@node_bp.route('/<node_id>', methods=['GET'])
def get_node(node_id):
    """獲取單個節點信息"""
    try:
        node_info = NodeStatus.get_node_info(node_id)

        if not node_info:
            return jsonify({
                'success': False,
                'error': '節點不存在'
            }), 404

        return jsonify({
            'success': True,
            'data': node_info
        }), 200

    except Exception as e:
        logger.error(f"獲取節點信息失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@node_bp.route('/<node_id>', methods=['DELETE'])
def unregister_node(node_id):
    """註銷節點"""
    try:
        # 檢查節點是否存在
        node_info = NodeStatus.get_node_info(node_id)
        if not node_info:
            return jsonify({
                'success': False,
                'error': '節點不存在'
            }), 404

        # 註銷節點
        success = NodeStatus.unregister_node(node_id)

        if not success:
            return jsonify({
                'success': False,
                'error': '註銷節點失敗'
            }), 500

        # 推送節點離線事件到前端
        websocket_manager.emit_node_offline({
            'node_id': node_id,
            'timestamp': node_info.get('last_heartbeat')
        })

        return jsonify({
            'success': True,
            'message': '節點已註銷'
        }), 200

    except Exception as e:
        logger.error(f"註銷節點失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@node_bp.route('/<node_id>/status', methods=['GET'])
def check_node_status(node_id):
    """檢查節點狀態"""
    try:
        is_alive = NodeStatus.is_alive(node_id)

        return jsonify({
            'success': True,
            'data': {
                'node_id': node_id,
                'status': 'online' if is_alive else 'offline',
                'is_alive': is_alive
            }
        }), 200

    except Exception as e:
        logger.error(f"檢查節點狀態失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
