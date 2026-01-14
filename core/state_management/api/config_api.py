"""
配置管理 API
提供分析方法配置的 CRUD 操作
"""
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, session
from werkzeug.utils import secure_filename
import gridfs
from models.analysis_config import AnalysisConfig
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)

config_bp = Blueprint('config_api', __name__)

# ==================== 動態載入 config_schema ====================
# 將 analysis_service 路徑加入 sys.path 以便匯入 config_schema
_ANALYSIS_SERVICE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'sub_system', 'analysis_service')
)
if _ANALYSIS_SERVICE_PATH not in sys.path:
    sys.path.insert(0, _ANALYSIS_SERVICE_PATH)

try:
    from config_schema import (
        get_analysis_config_schema,
        get_all_model_requirements,
        get_method_by_key,
        get_default_parameters,
        get_method_default_params,
        CLASSIFICATION_METHODS,
    )
    _SCHEMA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"無法載入 config_schema: {e}，將使用內建定義")
    _SCHEMA_AVAILABLE = False


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


# ==================== 暫存上傳 API ====================

@config_bp.route('/temp-upload/<file_key>', methods=['POST'])
def temp_upload_model(file_key):
    """
    暫存上傳模型檔案（用於新建配置時）
    檔案會暫存到 GridFS，並帶有 temp: true 的 metadata
    前端需保存返回的 session_id 和 file_id，在儲存配置時一併提交
    """
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

        # 取得或建立 session_id
        session_id = request.form.get('session_id')
        if not session_id:
            session_id = str(uuid.uuid4())

        # 安全處理文件名
        filename = secure_filename(file.filename)

        # 上傳到 GridFS（標記為暫存）
        db = get_db()
        fs = gridfs.GridFS(db)

        # 讀取文件內容
        file_content = file.read()

        # 存儲文件（帶有 temp 標記）
        file_id = fs.put(
            file_content,
            filename=filename,
            content_type=file.content_type,
            metadata={
                'original_filename': file.filename,
                'file_type': 'model',
                'file_key': file_key,
                'session_id': session_id,
                'temp': True,  # 標記為暫存檔案
                'created_at': datetime.now(timezone.utc),
                'expires_at': datetime.now(timezone.utc) + timedelta(hours=24),  # 24小時後過期
                'size': len(file_content)
            }
        )

        logger.info(f"暫存模型文件已上傳: session={session_id}, key={file_key}, file={filename}")

        return jsonify({
            'success': True,
            'data': {
                'file_id': str(file_id),
                'file_key': file_key,
                'filename': filename,
                'size': len(file_content),
                'session_id': session_id
            },
            'message': '模型文件已暫存'
        }), 201

    except Exception as e:
        logger.error(f"暫存上傳模型文件失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/temp-upload/<file_key>', methods=['DELETE'])
def delete_temp_model(file_key):
    """刪除暫存的模型檔案"""
    try:
        from bson.objectid import ObjectId

        session_id = request.args.get('session_id')
        file_id = request.args.get('file_id')

        if not file_id:
            return jsonify({
                'success': False,
                'error': '缺少 file_id'
            }), 400

        db = get_db()
        fs = gridfs.GridFS(db)

        # 驗證檔案存在且是暫存檔案
        try:
            grid_out = fs.get(ObjectId(file_id))
            metadata = grid_out.metadata or {}

            if not metadata.get('temp'):
                return jsonify({
                    'success': False,
                    'error': '此檔案不是暫存檔案'
                }), 400

            if session_id and metadata.get('session_id') != session_id:
                return jsonify({
                    'success': False,
                    'error': 'session_id 不符'
                }), 403

        except gridfs.errors.NoFile:
            return jsonify({
                'success': False,
                'error': '檔案不存在'
            }), 404

        # 刪除檔案
        fs.delete(ObjectId(file_id))

        logger.info(f"暫存模型文件已刪除: file_id={file_id}")

        return jsonify({
            'success': True,
            'message': '暫存檔案已刪除'
        }), 200

    except Exception as e:
        logger.error(f"刪除暫存模型文件失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/temp-files', methods=['GET'])
def get_temp_files():
    """取得指定 session 的所有暫存檔案"""
    try:
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({
                'success': False,
                'error': '缺少 session_id'
            }), 400

        db = get_db()
        # 查詢 fs.files 集合
        files_collection = db['fs.files']

        temp_files = list(files_collection.find({
            'metadata.session_id': session_id,
            'metadata.temp': True
        }))

        result = {}
        for f in temp_files:
            file_key = f.get('metadata', {}).get('file_key')
            if file_key:
                result[file_key] = {
                    'file_id': str(f['_id']),
                    'filename': f.get('filename'),
                    'size': f.get('metadata', {}).get('size', 0),
                    'uploaded_at': f.get('uploadDate')
                }

        return jsonify({
            'success': True,
            'data': result,
            'session_id': session_id
        }), 200

    except Exception as e:
        logger.error(f"取得暫存檔案列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/link-temp-files', methods=['POST'])
def link_temp_files_to_config():
    """
    將暫存檔案關聯到正式配置
    在配置儲存成功後調用此 API
    """
    try:
        from bson.objectid import ObjectId

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        config_id = data.get('config_id')
        session_id = data.get('session_id')
        temp_files = data.get('temp_files', {})  # {file_key: file_id, ...}

        if not config_id:
            return jsonify({
                'success': False,
                'error': '缺少 config_id'
            }), 400

        # 檢查配置是否存在
        config = AnalysisConfig.get_by_id(config_id)
        if not config:
            return jsonify({
                'success': False,
                'error': '配置不存在'
            }), 404

        db = get_db()
        fs = gridfs.GridFS(db)
        files_collection = db['fs.files']

        linked_files = {}
        errors = []

        for file_key, file_id in temp_files.items():
            try:
                # 驗證並更新檔案 metadata
                result = files_collection.update_one(
                    {
                        '_id': ObjectId(file_id),
                        'metadata.temp': True
                    },
                    {
                        '$set': {
                            'metadata.temp': False,
                            'metadata.config_id': config_id,
                            'metadata.linked_at': datetime.now(timezone.utc)
                        },
                        '$unset': {
                            'metadata.expires_at': '',
                            'metadata.session_id': ''
                        }
                    }
                )

                if result.modified_count > 0:
                    # 取得檔案資訊
                    file_doc = files_collection.find_one({'_id': ObjectId(file_id)})
                    if file_doc:
                        file_info = {
                            'file_id': str(file_id),
                            'filename': file_doc.get('filename'),
                            'uploaded_at': datetime.now(timezone.utc),
                            'size': file_doc.get('metadata', {}).get('size', 0)
                        }
                        # 更新配置的 model_files
                        AnalysisConfig.set_model_file(config_id, file_key, file_info)
                        linked_files[file_key] = file_info
                else:
                    errors.append(f'{file_key}: 檔案不存在或已不是暫存狀態')

            except Exception as e:
                errors.append(f'{file_key}: {str(e)}')

        if errors:
            logger.warning(f"關聯暫存檔案時發生錯誤: {errors}")

        return jsonify({
            'success': True,
            'data': {
                'linked_files': linked_files,
                'errors': errors if errors else None
            },
            'message': f'已關聯 {len(linked_files)} 個檔案'
        }), 200

    except Exception as e:
        logger.error(f"關聯暫存檔案失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/cleanup-temp-files', methods=['POST'])
def cleanup_expired_temp_files():
    """清理過期的暫存檔案（可由排程任務調用）"""
    try:
        db = get_db()
        fs = gridfs.GridFS(db)
        files_collection = db['fs.files']

        # 查找過期的暫存檔案
        expired_files = list(files_collection.find({
            'metadata.temp': True,
            'metadata.expires_at': {'$lt': datetime.now(timezone.utc)}
        }))

        deleted_count = 0
        for f in expired_files:
            try:
                fs.delete(f['_id'])
                deleted_count += 1
            except Exception as e:
                logger.warning(f"刪除過期暫存檔案失敗: {f['_id']}, error: {e}")

        logger.info(f"已清理 {deleted_count} 個過期暫存檔案")

        return jsonify({
            'success': True,
            'data': {
                'deleted_count': deleted_count
            },
            'message': f'已清理 {deleted_count} 個過期暫存檔案'
        }), 200

    except Exception as e:
        logger.error(f"清理暫存檔案失敗: {e}", exc_info=True)
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


# ==================== Schema API ====================

@config_bp.route('/schema', methods=['GET'])
def get_schema():
    """
    取得完整的分析配置 Schema。

    前端透過此 API 取得 Schema 後，可動態生成配置表單。
    Schema 包含：
    - schema_version: Schema 版本號
    - schema_hash: Schema 內容雜湊值（用於驗證一致性）
    - classification_methods: 分類方法定義（含模型需求和方法特定參數）
    - model_files: 模型檔案定義
    - parameter_groups: 參數群組定義（含欄位類型、標題、說明、預設值）
    """
    try:
        if _SCHEMA_AVAILABLE:
            schema = get_analysis_config_schema()
        else:
            # 如果無法載入 config_schema，返回內建基本 Schema
            schema = _get_fallback_schema()

        return jsonify({
            'success': True,
            'data': schema
        }), 200

    except Exception as e:
        logger.error(f"取得 Schema 失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/schema/defaults', methods=['GET'])
def get_schema_defaults():
    """取得所有參數的預設值"""
    try:
        if _SCHEMA_AVAILABLE:
            defaults = get_default_parameters()
        else:
            defaults = {}

        return jsonify({
            'success': True,
            'data': defaults
        }), 200

    except Exception as e:
        logger.error(f"取得預設值失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/schema/method/<method_key>/defaults', methods=['GET'])
def get_method_defaults(method_key):
    """取得指定分類方法的預設參數"""
    try:
        if _SCHEMA_AVAILABLE:
            defaults = get_method_default_params(method_key)
        else:
            defaults = {}

        return jsonify({
            'success': True,
            'data': defaults
        }), 200

    except Exception as e:
        logger.error(f"取得方法預設值失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def _get_fallback_schema():
    """當無法載入 config_schema 時返回的內建基本 Schema"""
    return {
        'schema_version': '1.0.0',
        'schema_hash': 'fallback',
        'classification_methods': [
            {
                'key': 'random',
                'label': 'Random Classification',
                'description': 'Random classification without model',
                'version': '1.0.0',
                'required_models': [],
                'optional_models': [],
                'params': [
                    {
                        'name': 'normal_probability',
                        'label': 'Normal Probability',
                        'type': 'number',
                        'description': 'Probability of classifying as normal (0-1)',
                        'default': 0.7,
                        'min': 0,
                        'max': 1,
                        'step': 0.05,
                    },
                ],
            },
            {
                'key': 'rf_model',
                'label': 'Random Forest Classifier',
                'description': 'Classification using Random Forest model',
                'version': '1.0.0',
                'required_models': ['rf_model'],
                'optional_models': ['rf_metadata'],
                'params': [
                    {
                        'name': 'threshold',
                        'label': 'Decision Threshold',
                        'type': 'number',
                        'default': 0.5,
                        'min': 0,
                        'max': 1,
                        'step': 0.05,
                    },
                ],
            },
            {
                'key': 'cyclegan_rf',
                'label': 'CycleGAN + Random Forest',
                'description': 'Feature transformation via CycleGAN then RF classification',
                'version': '1.0.0',
                'required_models': ['cyclegan_checkpoint', 'rf_model'],
                'optional_models': ['cyclegan_normalization', 'rf_metadata'],
                'params': [
                    {
                        'name': 'threshold',
                        'label': 'Decision Threshold',
                        'type': 'number',
                        'default': 0.5,
                        'min': 0,
                        'max': 1,
                        'step': 0.05,
                    },
                ],
            },
        ],
        'model_files': {
            'rf_model': {
                'key': 'rf_model',
                'label': 'RF Model',
                'filename': 'mimii_fan_rf_classifier.pkl',
                'description': 'Random Forest model file',
                'extensions': ['.pkl'],
            },
            'rf_metadata': {
                'key': 'rf_metadata',
                'label': 'Model Metadata',
                'filename': 'model_metadata.json',
                'description': 'Model metadata JSON',
                'extensions': ['.json'],
            },
            'cyclegan_checkpoint': {
                'key': 'cyclegan_checkpoint',
                'label': 'CycleGAN Checkpoint',
                'filename': 'last.ckpt',
                'description': 'CycleGAN model checkpoint',
                'extensions': ['.ckpt', '.pth'],
            },
            'cyclegan_normalization': {
                'key': 'cyclegan_normalization',
                'label': 'CycleGAN Normalization',
                'filename': 'normalization_params.json',
                'description': 'CycleGAN normalization parameters',
                'extensions': ['.json'],
            },
        },
        'parameter_groups': [
            {
                'key': 'classification',
                'label': 'Classification Settings',
                'description': 'Basic classification parameters',
                'collapsed': False,
                'fields': [
                    {
                        'name': 'classes',
                        'label': 'Classification Classes',
                        'type': 'tags',
                        'description': 'Define classification labels',
                        'default': ['normal', 'abnormal'],
                    },
                ],
            },
        ],
    }


# ==================== 模型管理 API ====================

@config_bp.route('/model_requirements', methods=['GET'])
def get_model_requirements():
    """取得所有分類方法的模型需求"""
    try:
        if _SCHEMA_AVAILABLE:
            model_requirements = get_all_model_requirements()
        else:
            # 內建定義作為備用
            model_requirements = {
                'random': {
                    'description': 'Random Classification',
                    'required_files': [],
                    'optional_files': [],
                },
                'rf_model': {
                    'description': 'Random Forest Classifier',
                    'required_files': [
                        {
                            'key': 'rf_model',
                            'filename': 'mimii_fan_rf_classifier.pkl',
                            'description': 'RF Model (.pkl)',
                            'extensions': ['.pkl'],
                        }
                    ],
                    'optional_files': [
                        {
                            'key': 'rf_metadata',
                            'filename': 'model_metadata.json',
                            'description': 'Model Metadata (.json)',
                            'extensions': ['.json'],
                        }
                    ],
                },
                'cyclegan_rf': {
                    'description': 'CycleGAN + Random Forest',
                    'required_files': [
                        {
                            'key': 'cyclegan_checkpoint',
                            'filename': 'last.ckpt',
                            'description': 'CycleGAN Checkpoint (.ckpt)',
                            'extensions': ['.ckpt', '.pth'],
                        },
                        {
                            'key': 'rf_model',
                            'filename': 'mimii_fan_rf_classifier.pkl',
                            'description': 'RF Model (.pkl)',
                            'extensions': ['.pkl'],
                        }
                    ],
                    'optional_files': [
                        {
                            'key': 'cyclegan_normalization',
                            'filename': 'normalization_params.json',
                            'description': 'CycleGAN Normalization (.json)',
                            'extensions': ['.json'],
                        },
                        {
                            'key': 'rf_metadata',
                            'filename': 'model_metadata.json',
                            'description': 'Model Metadata (.json)',
                            'extensions': ['.json'],
                        }
                    ],
                },
            }

        return jsonify({
            'success': True,
            'data': model_requirements
        }), 200

    except Exception as e:
        logger.error(f"取得模型需求失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/<config_id>/method', methods=['PUT'])
def update_classification_method(config_id):
    """更新配置的分類方法"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        method = data.get('method') or data.get('classification_method', 'random')

        # 驗證方法是否有效（從 Schema 取得有效方法列表）
        if _SCHEMA_AVAILABLE:
            valid_methods = [m['key'] for m in CLASSIFICATION_METHODS]
            method_info = get_method_by_key(method)
        else:
            valid_methods = ['random', 'rf_model', 'cyclegan_rf']
            method_info = None

        if method not in valid_methods:
            return jsonify({
                'success': False,
                'error': f'不支援的分類方法: {method}'
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

        # 更新分類方法
        success = AnalysisConfig.set_classification_method(config_id, method)

        if not success:
            return jsonify({
                'success': False,
                'error': '更新分類方法失敗'
            }), 500

        # 取得模型需求
        if _SCHEMA_AVAILABLE:
            from config_schema import get_model_requirements as get_method_model_requirements
            model_req = get_method_model_requirements(method)
            required_files = model_req.get('required_files', [])
            optional_files = model_req.get('optional_files', [])
        else:
            model_requirements = {
                'random': {'required_files': [], 'optional_files': []},
                'rf_model': {
                    'required_files': [{'key': 'rf_model', 'description': 'RF Model (.pkl)'}],
                    'optional_files': [{'key': 'rf_metadata', 'description': 'Model Metadata (.json)'}]
                },
                'cyclegan_rf': {
                    'required_files': [
                        {'key': 'cyclegan_checkpoint', 'description': 'CycleGAN Checkpoint (.ckpt)'},
                        {'key': 'rf_model', 'description': 'RF Model (.pkl)'}
                    ],
                    'optional_files': [
                        {'key': 'cyclegan_normalization', 'description': 'CycleGAN Normalization (.json)'}
                    ]
                }
            }
            required_files = model_requirements[method].get('required_files', [])
            optional_files = model_requirements[method].get('optional_files', [])

        return jsonify({
            'success': True,
            'data': {
                'classification_method': method,
                'method_version': method_info.get('version', '1.0.0') if method_info else '1.0.0',
                'required_files': required_files,
                'optional_files': optional_files,
            },
            'message': f'Classification method updated to: {method}'
        }), 200

    except Exception as e:
        logger.error(f"更新分類方法失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/<config_id>/model/<file_key>', methods=['POST'])
def upload_model_for_config(config_id, file_key):
    """為配置上傳模型檔案"""
    try:
        from bson.objectid import ObjectId
        from datetime import datetime

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

        # 安全處理文件名
        filename = secure_filename(file.filename)

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
                'file_key': file_key,
                'config_id': config_id,
                'size': len(file_content)
            }
        )

        # 更新配置的 model_files
        file_info = {
            'file_id': str(file_id),
            'filename': filename,
            'uploaded_at': datetime.now(timezone.utc),
            'size': len(file_content)
        }

        success = AnalysisConfig.set_model_file(config_id, file_key, file_info)

        if not success:
            # 如果更新配置失敗，刪除已上傳的文件
            fs.delete(file_id)
            return jsonify({
                'success': False,
                'error': '更新配置失敗'
            }), 500

        logger.info(f"模型文件已上傳: {config_id}/{file_key} -> {filename}")

        return jsonify({
            'success': True,
            'data': {
                'file_id': str(file_id),
                'file_key': file_key,
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


@config_bp.route('/<config_id>/model/<file_key>', methods=['DELETE'])
def delete_model_for_config(config_id, file_key):
    """刪除配置的模型檔案"""
    try:
        from bson.objectid import ObjectId

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

        # 取得現有的文件資訊
        file_info = AnalysisConfig.get_model_file(config_id, file_key)
        if not file_info:
            return jsonify({
                'success': False,
                'error': '模型文件不存在'
            }), 404

        file_id = file_info.get('file_id')

        # 從 GridFS 刪除文件
        if file_id:
            try:
                db = get_db()
                fs = gridfs.GridFS(db)
                fs.delete(ObjectId(file_id))
                logger.info(f"已從 GridFS 刪除文件: {file_id}")
            except Exception as e:
                logger.warning(f"從 GridFS 刪除文件失敗 (可能已不存在): {e}")

        # 從配置中移除文件資訊
        success = AnalysisConfig.remove_model_file(config_id, file_key)

        if not success:
            return jsonify({
                'success': False,
                'error': '更新配置失敗'
            }), 500

        logger.info(f"模型文件已刪除: {config_id}/{file_key}")

        return jsonify({
            'success': True,
            'message': '模型文件已刪除'
        }), 200

    except Exception as e:
        logger.error(f"刪除模型文件失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@config_bp.route('/<config_id>/models', methods=['GET'])
def get_config_models(config_id):
    """取得配置的所有模型檔案資訊"""
    try:
        config = AnalysisConfig.get_by_id(config_id)
        if not config:
            return jsonify({
                'success': False,
                'error': '配置不存在'
            }), 404

        model_files = config.model_files or {}

        return jsonify({
            'success': True,
            'data': {
                'classification_method': model_files.get('classification_method', 'random'),
                'files': model_files.get('files', {})
            }
        }), 200

    except Exception as e:
        logger.error(f"取得模型檔案資訊失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
