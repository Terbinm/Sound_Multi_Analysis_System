"""
MongoDB 實例管理 API
提供 MongoDB 實例配置的 CRUD 操作
"""
import logging
from flask import Blueprint, request, jsonify
from models.mongodb_instance import MongoDBInstance

logger = logging.getLogger(__name__)

instance_bp = Blueprint('instance_api', __name__)


@instance_bp.route('', methods=['GET'])
def get_all_instances():
    """獲取所有 MongoDB 實例"""
    try:
        enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
        include_password = request.args.get('include_password', 'false').lower() == 'true'

        instances = MongoDBInstance.get_all(
            enabled_only=enabled_only,
            include_password=include_password,
            ensure_default=True
        )

        return jsonify({
            'success': True,
            'data': [
                instance.to_dict(include_password=include_password)
                for instance in instances
            ],
            'count': len(instances)
        }), 200

    except Exception as e:
        logger.error(f"獲取實例列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@instance_bp.route('/<instance_id>', methods=['GET'])
def get_instance(instance_id):
    """獲取單個 MongoDB 實例"""
    try:
        include_password = request.args.get('include_password', 'false').lower() == 'true'

        instance = MongoDBInstance.get_by_id(instance_id)

        if not instance:
            return jsonify({
                'success': False,
                'error': '實例配置不存在'
            }), 404

        return jsonify({
            'success': True,
            'data': instance.to_dict(include_password=include_password)
        }), 200

    except Exception as e:
        logger.error(f"獲取實例失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@instance_bp.route('', methods=['POST'])
def create_instance():
    """創建新 MongoDB 實例"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 必填欄位驗證
        required_fields = ['instance_name', 'host', 'username', 'password', 'database']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必填欄位: {field}'
                }), 400

        # 創建實例
        instance = MongoDBInstance.create(data)

        if not instance:
            return jsonify({
                'success': False,
                'error': '創建實例配置失敗'
            }), 500

        return jsonify({
            'success': True,
            'data': instance.to_dict(include_password=False),
            'message': '實例配置已創建'
        }), 201

    except Exception as e:
        logger.error(f"創建實例配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@instance_bp.route('/<instance_id>', methods=['PUT'])
def update_instance(instance_id):
    """更新 MongoDB 實例"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查實例是否存在
        instance = MongoDBInstance.get_by_id(instance_id)
        if not instance:
            return jsonify({
                'success': False,
                'error': '實例配置不存在'
            }), 404

        if instance.is_system:
            return jsonify({
                'success': False,
                'error': '系統內建實例不可修改'
            }), 403

        # 不允許修改的欄位
        protected_fields = ['instance_id', 'created_at']
        for field in protected_fields:
            if field in data:
                del data[field]

        # 更新實例
        success = MongoDBInstance.update(instance_id, data)

        if not success:
            return jsonify({
                'success': False,
                'error': '更新實例配置失敗'
            }), 500

        # 獲取更新後的實例
        return jsonify({
            'success': True,
            'data': MongoDBInstance.get_by_id(instance_id).to_dict(include_password=False),
            'message': '實例配置已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新實例配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@instance_bp.route('/<instance_id>', methods=['DELETE'])
def delete_instance(instance_id):
    """刪除 MongoDB 實例"""
    try:
        # 檢查實例是否存在
        instance = MongoDBInstance.get_by_id(instance_id)
        if not instance:
            return jsonify({
                'success': False,
                'error': '實例配置不存在'
            }), 404

        if instance.is_system:
            return jsonify({
                'success': False,
                'error': '系統內建實例不可刪除'
            }), 403

        # 刪除實例
        success = MongoDBInstance.delete(instance_id)

        if not success:
            return jsonify({
                'success': False,
                'error': '刪除實例配置失敗'
            }), 500

        return jsonify({
            'success': True,
            'message': '實例配置已刪除'
        }), 200

    except Exception as e:
        logger.error(f"刪除實例配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@instance_bp.route('/<instance_id>/test', methods=['POST'])
def test_connection(instance_id):
    """測試 MongoDB 實例連接"""
    try:
        # 測試連接
        success, message = MongoDBInstance.test_connection_by_id(instance_id)

        if success:
            return jsonify({
                'success': True,
                'message': message
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400

    except Exception as e:
        logger.error(f"測試連接失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
