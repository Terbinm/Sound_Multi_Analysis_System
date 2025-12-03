"""
配置管理 API
提供分析方法配置的 CRUD 操作
"""
import logging
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import gridfs
from models.analysis_config import AnalysisConfig
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)

config_bp = Blueprint('config_api', __name__)


@config_bp.route('', methods=['GET'])
def get_all_configs():
    """獲取所有配置"""
    try:
        enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
        configs = AnalysisConfig.get_all(enabled_only=enabled_only)

        return jsonify({
            'success': True,
            'data': [config.to_dict() for config in configs],
            'count': len(configs)
        }), 200

    except Exception as e:
        logger.error(f"獲取配置列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/<config_id>', methods=['GET'])
def get_config(config_id):
    """獲取單個配置"""
    try:
        config = AnalysisConfig.get_by_id(config_id)

        if not config:
            return jsonify({
                'success': False,
                'error': '配置不存在'
            }), 404

        return jsonify({
            'success': True,
            'data': config.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"獲取配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('', methods=['POST'])
def create_config():
    """創建新配置"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 必填欄位驗證
        required_fields = ['analysis_method_id', 'config_name']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必填欄位: {field}'
                }), 400

        # 創建配置
        config = AnalysisConfig.create(data)

        if not config:
            return jsonify({
                'success': False,
                'error': '創建配置失敗'
            }), 500

        return jsonify({
            'success': True,
            'data': config.to_dict(),
            'message': '配置已創建'
        }), 201

    except Exception as e:
        logger.error(f"創建配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/<config_id>', methods=['PUT'])
def update_config(config_id):
    """更新配置"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查配置是否存在
        config = AnalysisConfig.get_by_id(config_id)
        if not config:
            return jsonify({
                'success': False,
                'error': '配置不存在'
            }), 404

        if config.is_system:
            return jsonify({
                'success': False,
                'error': '系統內建配置不可修改'
            }), 403

        # 不允許修改的欄位
        protected_fields = ['config_id', 'created_at']
        for field in protected_fields:
            if field in data:
                del data[field]

        # 更新配置
        success = AnalysisConfig.update(config_id, data)

        if not success:
            return jsonify({
                'success': False,
                'error': '更新配置失敗'
            }), 500

        # 獲取更新後的配置
        return jsonify({
            'success': True,
            'data': AnalysisConfig.get_by_id(config_id).to_dict(),
            'message': '配置已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/<config_id>', methods=['DELETE'])
def delete_config(config_id):
    """刪除配置"""
    try:
        # 檢查配置是否存在
        config = AnalysisConfig.get_by_id(config_id)
        if not config:
            return jsonify({
                'success': False,
                'error': '配置不存在'
            }), 404

        if config.is_system:
            return jsonify({
                'success': False,
                'error': '系統內建配置不可刪除'
            }), 403

        # 刪除配置
        success = AnalysisConfig.delete(config_id)

        if not success:
            return jsonify({
                'success': False,
                'error': '刪除配置失敗'
            }), 500

        return jsonify({
            'success': True,
            'message': '配置已刪除'
        }), 200

    except Exception as e:
        logger.error(f"刪除配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/methods', methods=['GET'])
def get_all_methods():
    """獲取所有不重複的分析方法 ID"""
    try:
        collection = AnalysisConfig._get_collection()

        # 使用 distinct 獲取所有不重複的 analysis_method_id
        method_ids = collection.distinct('analysis_method_id')

        # 為每個方法 ID 統計配置數量
        methods = []
        for method_id in method_ids:
            count = collection.count_documents({'analysis_method_id': method_id})
            methods.append({
                'analysis_method_id': method_id,
                'config_count': count
            })

        # 按方法 ID 排序
        methods.sort(key=lambda x: x['analysis_method_id'])

        return jsonify({
            'success': True,
            'data': methods,
            'count': len(methods)
        }), 200

    except Exception as e:
        logger.error(f"獲取分析方法列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/method/<analysis_method_id>', methods=['GET'])
def get_configs_by_method(analysis_method_id):
    """根據分析方法 ID 獲取配置"""
    try:
        configs = AnalysisConfig.get_by_method_id(analysis_method_id)

        return jsonify({
            'success': True,
            'data': [config.to_dict() for config in configs],
            'count': len(configs)
        }), 200

    except Exception as e:
        logger.error(f"獲取配置列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/upload_model', methods=['POST'])
def upload_model():
    """上傳模型文件到 GridFS"""
    try:
        # 檢查文件
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': '缺少文件'
            }), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '未選擇文件'
            }), 400

        # 檢查文件擴展名
        config = get_config()
        filename = secure_filename(file.filename)
        file_ext = '.' + filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if file_ext not in config.UPLOAD_EXTENSIONS:
            return jsonify({
                'success': False,
                'error': f'不支援的文件格式。支援的格式: {", ".join(config.UPLOAD_EXTENSIONS)}'
            }), 400

        # 上傳到 GridFS
        db = get_db()
        fs = gridfs.GridFS(db)

        # 讀取文件內容
        file_content = file.read()

        # 存儲文件
        file_id = fs.put(
            file_content,
            filename=filename,
            content_type=file.content_type,
            metadata={
                'original_filename': file.filename,
                'file_type': 'model',
                'size': len(file_content)
            }
        )

        logger.info(f"模型文件已上傳: {filename}, file_id: {file_id}")

        return jsonify({
            'success': True,
            'data': {
                'file_id': str(file_id),
                'filename': filename,
                'size': len(file_content)
            },
            'message': '模型文件已上傳'
        }), 201

    except Exception as e:
        logger.error(f"上傳模型文件失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/download_model/<file_id>', methods=['GET'])
def download_model(file_id):
    """下載模型文件"""
    try:
        from bson.objectid import ObjectId
        from flask import send_file
        import io

        db = get_db()
        fs = gridfs.GridFS(db)

        # 檢查文件是否存在
        if not fs.exists(ObjectId(file_id)):
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404

        # 獲取文件
        grid_out = fs.get(ObjectId(file_id))

        # 創建文件對象
        file_data = io.BytesIO(grid_out.read())
        file_data.seek(0)

        return send_file(
            file_data,
            mimetype=grid_out.content_type,
            as_attachment=True,
            download_name=grid_out.filename
        )

    except Exception as e:
        logger.error(f"下載模型文件失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
