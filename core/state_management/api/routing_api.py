"""
路由規則 API
提供路由規則的 CRUD 操作與任務派送功能
"""
import logging
from flask import Blueprint, request, jsonify
from models.routing_rule import RoutingRule
from models.task_execution_log import TaskExecutionLog
from utils.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)

routing_bp = Blueprint('routing_api', __name__)
dispatcher = TaskDispatcher()


@routing_bp.route('', methods=['GET'])
def get_all_rules():
    """獲取所有路由規則"""
    try:
        enabled_only = request.args.get('enabled_only', 'true').lower() == 'true'
        rules = RoutingRule.get_all(enabled_only=enabled_only)

        return jsonify({
            'success': True,
            'data': [rule.to_dict() for rule in rules],
            'count': len(rules)
        }), 200

    except Exception as e:
        logger.error(f"獲取路由規則列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/<rule_id>', methods=['GET'])
def get_rule(rule_id):
    """獲取單個路由規則"""
    try:
        rule = RoutingRule.get_by_id(rule_id)

        if not rule:
            return jsonify({
                'success': False,
                'error': '路由規則不存在'
            }), 404

        return jsonify({
            'success': True,
            'data': rule.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"獲取路由規則失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('', methods=['POST'])
def create_rule():
    """創建新路由規則"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 必填欄位驗證
        required_fields = ['rule_name', 'conditions', 'actions']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必填欄位: {field}'
                }), 400

        # 創建規則
        rule = RoutingRule.create(data)

        if not rule:
            return jsonify({
                'success': False,
                'error': '創建路由規則失敗'
            }), 500

        return jsonify({
            'success': True,
            'data': rule.to_dict(),
            'message': '路由規則已創建'
        }), 201

    except Exception as e:
        logger.error(f"創建路由規則失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/<rule_id>', methods=['PUT'])
def update_rule(rule_id):
    """更新路由規則"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查規則是否存在
        rule = RoutingRule.get_by_id(rule_id)
        if not rule:
            return jsonify({
                'success': False,
                'error': '路由規則不存在'
            }), 404

        # 不允許修改的欄位
        protected_fields = ['rule_id', 'created_at']
        for field in protected_fields:
            if field in data:
                del data[field]

        # 更新規則
        success = RoutingRule.update(rule_id, data)

        if not success:
            return jsonify({
                'success': False,
                'error': '更新路由規則失敗'
            }), 500

        # 獲取更新後的規則
        rule = RoutingRule.get_by_id(rule_id)

        return jsonify({
            'success': True,
            'data': rule.to_dict(),
            'message': '路由規則已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新路由規則失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/<rule_id>', methods=['DELETE'])
def delete_rule(rule_id):
    """刪除路由規則"""
    try:
        # 檢查規則是否存在
        rule = RoutingRule.get_by_id(rule_id)
        if not rule:
            return jsonify({
                'success': False,
                'error': '路由規則不存在'
            }), 404

        # 刪除規則
        success = RoutingRule.delete(rule_id)

        if not success:
            return jsonify({
                'success': False,
                'error': '刪除路由規則失敗'
            }), 500

        return jsonify({
            'success': True,
            'message': '路由規則已刪除'
        }), 200

    except Exception as e:
        logger.error(f"刪除路由規則失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/test', methods=['POST'])
def test_rule():
    """測試路由規則匹配"""
    try:
        data = request.get_json()

        if not data or 'info_features' not in data:
            return jsonify({
                'success': False,
                'error': '缺少 info_features'
            }), 400

        info_features = data['info_features']

        # 查找匹配的規則
        matching_rules = RoutingRule.find_matching_rules(info_features)

        return jsonify({
            'success': True,
            'data': {
                'matching_rules': [rule.to_dict() for rule in matching_rules],
                'match_count': len(matching_rules)
            }
        }), 200

    except Exception as e:
        logger.error(f"測試路由規則失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/trigger', methods=['POST'])
def trigger_task():
    """
    觸發任務派送
    上傳工具呼叫此 API 來派送任務
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        analyze_uuid = data.get('analyze_uuid')
        router_ids = data.get('router_ids', [])

        if not analyze_uuid:
            return jsonify({
                'success': False,
                'error': '缺少 analyze_uuid'
            }), 400

        if not router_ids:
            return jsonify({
                'success': False,
                'error': '缺少 router_ids'
            }), 400

        if not isinstance(router_ids, list):
            router_ids = [router_ids]

        # 判斷是否依序執行（預設為 True）
        sequential = data.get('sequential', True)

        # 派送任務
        result = dispatcher.dispatch_by_router_ids(
            analyze_uuid=analyze_uuid,
            router_ids=router_ids,
            sequential=sequential
        )

        if result['success']:
            return jsonify({
                'success': True,
                'data': {
                    'analyze_uuid': analyze_uuid,
                    'router_ids': router_ids,
                    'tasks_created': result['tasks_created'],
                    'task_count': len(result['tasks_created'])
                },
                'message': f"成功創建 {len(result['tasks_created'])} 個任務"
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': '任務派送失敗',
                'details': result.get('errors', [])
            }), 500

    except Exception as e:
        logger.error(f"觸發任務失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/<router_id>/backfill', methods=['POST'])
def backfill_by_router_id(router_id):
    """
    追溯歷史資料
    為符合規則條件的所有歷史記錄派送任務
    """
    try:
        data = request.get_json() or {}
        limit = data.get('limit', None)

        # 驗證 router_id 是否存在
        rule = RoutingRule.get_by_router_id(router_id)
        if not rule:
            return jsonify({
                'success': False,
                'error': f'找不到 router_id: {router_id}'
            }), 404

        # 執行追溯
        result = dispatcher.backfill_by_router_id(
            router_id=router_id,
            limit=limit
        )

        if result['success']:
            return jsonify({
                'success': True,
                'data': {
                    'router_id': router_id,
                    'rule_name': rule.rule_name,
                    'total_matched': result['total_matched'],
                    'tasks_created': result['tasks_created'],
                    'errors': result.get('errors', [])
                },
                'message': f"成功創建 {result['tasks_created']} 個任務（符合條件: {result['total_matched']} 筆）"
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '追溯失敗'),
                'details': result.get('errors', [])
            }), 500

    except Exception as e:
        logger.error(f"追溯歷史資料失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/preview', methods=['POST'])
def preview_matching_records():
    """
    預覽符合條件的資料
    用於規則建立時即時查看符合條件的記錄
    """
    try:
        data = request.get_json()

        if not data or 'conditions' not in data:
            return jsonify({
                'success': False,
                'error': '缺少 conditions'
            }), 400

        conditions = data['conditions']
        limit = data.get('limit', 100)

        # 預覽符合條件的記錄
        result = dispatcher.preview_matching_records(
            conditions=conditions,
            limit=limit
        )

        if result['success']:
            return jsonify({
                'success': True,
                'data': {
                    'total': result['total'],
                    'records': result['records'],
                    'sample': result['sample'],
                    'limit': limit
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '預覽失敗')
            }), 500

    except Exception as e:
        logger.error(f"預覽符合條件的記錄失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/<router_id>/stats', methods=['GET'])
def get_router_stats(router_id):
    """
    獲取 router_id 的執行統計
    包含總數、成功率、失敗數等資訊
    """
    try:
        # 驗證 router_id 是否存在
        rule = RoutingRule.get_by_router_id(router_id)
        if not rule:
            return jsonify({
                'success': False,
                'error': f'找不到 router_id: {router_id}'
            }), 404

        # 獲取統計資訊
        stats = TaskExecutionLog.get_statistics(router_id)

        return jsonify({
            'success': True,
            'data': {
                'router_id': router_id,
                'rule_id': rule.rule_id,
                'rule_name': rule.rule_name,
                'statistics': stats
            }
        }), 200

    except Exception as e:
        logger.error(f"獲取統計資訊失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@routing_bp.route('/<router_id>/monitor', methods=['GET'])
def monitor_router_execution(router_id):
    """
    監控 router_id 的執行狀態
    返回最近的任務執行記錄
    """
    try:
        # 驗證 router_id 是否存在
        rule = RoutingRule.get_by_router_id(router_id)
        if not rule:
            return jsonify({
                'success': False,
                'error': f'找不到 router_id: {router_id}'
            }), 404

        # 獲取查詢參數
        limit = request.args.get('limit', 50, type=int)
        skip = request.args.get('skip', 0, type=int)

        # 獲取最近的執行記錄
        logs = TaskExecutionLog.get_by_router_id(
            router_id=router_id,
            limit=limit,
            skip=skip
        )

        # 獲取統計資訊
        stats = TaskExecutionLog.get_statistics(router_id)

        return jsonify({
            'success': True,
            'data': {
                'router_id': router_id,
                'rule_id': rule.rule_id,
                'rule_name': rule.rule_name,
                'recent_tasks': [log.to_dict() for log in logs],
                'statistics': stats,
                'pagination': {
                    'limit': limit,
                    'skip': skip,
                    'returned': len(logs)
                }
            }
        }), 200

    except Exception as e:
        logger.error(f"監控執行狀態失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
