"""
節點監控視圖
顯示並管理分析節點狀態
"""
from flask import render_template, redirect, url_for, flash, jsonify
from flask_login import login_required
from views import views_bp
from auth.decorators import admin_required
from models.node_status import NodeStatus
from services.websocket_manager import websocket_manager
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/nodes')
@login_required
def nodes_list():
    """
    節點列表頁面
    顯示所有註冊節點的狀態
    """
    try:
        # 取得所有節點
        all_nodes = NodeStatus.get_all()

        # 分類節點
        online_nodes = [node for node in all_nodes if node.is_online()]
        offline_nodes = [node for node in all_nodes if not node.is_online()]

        # 統計資訊
        stats = {
            'total': len(all_nodes),
            'online': len(online_nodes),
            'offline': len(offline_nodes)
        }

        return render_template(
            'nodes/list.html',
            online_nodes=online_nodes,
            offline_nodes=offline_nodes,
            stats=stats
        )

    except Exception as e:
        logger.error(f"載入節點列表失敗: {str(e)}")
        flash('載入節點列表失敗', 'danger')
        return render_template(
            'nodes/list.html',
            online_nodes=[],
            offline_nodes=[],
            stats={'total': 0, 'online': 0, 'offline': 0}
        )


@views_bp.route('/nodes/<node_id>')
@login_required
def node_detail(node_id):
    """
    節點詳情頁面
    """
    try:
        node = NodeStatus.get_by_id(node_id)
        if not node:
            flash('節點不存在', 'danger')
            return redirect(url_for('views.nodes_list'))

        return render_template('nodes/detail.html', node=node)

    except Exception as e:
        logger.error(f"載入節點詳情失敗: {str(e)}")
        flash('載入節點詳情失敗', 'danger')
        return redirect(url_for('views.nodes_list'))


@views_bp.route('/nodes/<node_id>/delete', methods=['POST'])
@admin_required
def node_delete(node_id):
    """
    刪除（註銷）節點
    """
    try:
        # 獲取節點信息（刪除前）
        node_info = NodeStatus.get_node_info(node_id)

        success = NodeStatus.delete(node_id)

        if success:
            logger.info(f"節點刪除成功: {node_id}")
            flash('節點刪除成功', 'success')

            # 推送節點離線事件到前端
            websocket_manager.emit_node_offline({
                'node_id': node_id,
                'timestamp': node_info.get('last_heartbeat') if node_info else None
            })
        else:
            flash('節點刪除失敗', 'danger')

    except Exception as e:
        logger.error(f"刪除節點失敗: {str(e)}")
        flash(f'刪除節點失敗: {str(e)}', 'danger')

    return redirect(url_for('views.nodes_list'))


@views_bp.route('/api/nodes/stats')
@login_required
def nodes_stats_api():
    """
    節點統計資訊 API（供前端輪詢）
    """
    try:
        all_nodes = NodeStatus.get_all()
        online_count = sum(1 for node in all_nodes if node.is_online())

        return jsonify({
            'success': True,
            'stats': {
                'total': len(all_nodes),
                'online': online_count,
                'offline': len(all_nodes) - online_count
            }
        })

    except Exception as e:
        logger.error(f"取得節點統計資訊失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@views_bp.route('/api/nodes/list')
@login_required
def nodes_list_api():
    """
    節點列表 API（供前端輪詢）
    """
    try:
        all_nodes = NodeStatus.get_all()

        nodes_data = [
            {
                'node_id': node.node_id,
                'capabilities': node.capabilities,
                'version': node.version,
                'max_concurrent_tasks': node.max_concurrent_tasks,
                'current_tasks': node.current_tasks,
                'last_heartbeat': node.last_heartbeat.isoformat() if node.last_heartbeat else None,
                'is_online': node.is_online(),
                'tags': node.tags
            }
            for node in all_nodes
        ]

        return jsonify({
            'success': True,
            'nodes': nodes_data
        })

    except Exception as e:
        logger.error(f"取得節點列表失敗: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
