"""
檔案上傳 API
提供檔案上傳與路由選擇功能
"""
import logging
import uuid
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import gridfs
from models.routing_rule import RoutingRule
from utils.task_dispatcher import TaskDispatcher
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)

upload_bp = Blueprint('upload_api', __name__)


# 支援的音訊檔案格式
ALLOWED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac'}


def allowed_file(filename):
    """檢查檔案是否為允許的格式"""
    if '.' not in filename:
        return False
    ext = '.' + filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_AUDIO_EXTENSIONS


@upload_bp.route('/submit', methods=['POST'])
@login_required
def submit_upload():
    """
    提交檔案上傳並觸發路由分析
    
    Request:
        - file: 上傳的檔案（multipart/form-data）
        - router_ids: 路由規則 ID 列表（可多選）
        - info_features: 自訂 metadata（JSON 字串）
        - sequential: 是否串行執行（true/false，預設 true）
        
    Returns:
        {
            "success": true,
            "analyze_uuid": "uuid",
            "tasks_created": 3,
            "message": "上傳成功"
        }
    """
    try:
        # 1. 驗證檔案
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': '缺少檔案'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '未選擇檔案'
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': f'不支援的檔案格式。允許的格式: {", ".join(ALLOWED_AUDIO_EXTENSIONS)}'
            }), 400
        
        # 2. 解析表單資料
        router_ids = request.form.getlist('router_ids')
        
        if not router_ids:
            return jsonify({
                'success': False,
                'error': '請至少選擇一個路由規則'
            }), 400
        
        # 驗證路由規則是否存在且啟用
        invalid_routers = []
        for router_id in router_ids:
            rule = RoutingRule.get_by_id(router_id)
            if not rule:
                invalid_routers.append(router_id)
            elif not rule.enabled:
                invalid_routers.append(f"{router_id} (已停用)")
        
        if invalid_routers:
            return jsonify({
                'success': False,
                'error': f'無效的路由規則: {", ".join(invalid_routers)}'
            }), 400
        
        # 解析 info_features
        info_features_str = request.form.get('info_features', '{}')
        try:
            info_features = json.loads(info_features_str)
        except json.JSONDecodeError as e:
            return jsonify({
                'success': False,
                'error': f'info_features JSON 格式錯誤: {str(e)}'
            }), 400
        
        # 添加上傳者資訊
        info_features.update({
            'uploaded_by': current_user.username,
            'uploaded_at': datetime.now(timezone.utc).isoformat(),
            'upload_source': 'web_ui'
        })
        
        sequential = request.form.get('sequential', 'true').lower() == 'true'
        
        # 3. 上傳檔案至 GridFS
        config = get_config()
        db = get_db()
        fs = gridfs.GridFS(db)
        
        # 讀取檔案內容
        file_content = file.read()
        filename = secure_filename(file.filename)
        
        # 取得檔案副檔名
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        # 上傳至 GridFS
        file_id = fs.put(
            file_content,
            filename=filename,
            content_type=file.content_type,
            upload_date=datetime.now(timezone.utc),
            metadata={
                'uploaded_by': current_user.username,
                'original_filename': file.filename,
                'file_size': len(file_content),
                'file_type': file_extension
            }
        )
        
        logger.info(f"檔案已上傳至 GridFS: {filename} (file_id: {file_id})")
        
        # 4. 創建 MongoDB 記錄
        analyze_uuid = str(uuid.uuid4())
        
        document = {
            'AnalyzeUUID': analyze_uuid,
            'files': {
                'raw': {
                    'fileId': file_id,
                    'filename': filename,
                    'type': file_extension
                }
            },
            'info_features': info_features,
            'analyze_features': {},
            'assigned_router_ids': [],  # 將由 TaskDispatcher 更新
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        result = db['recordings'].insert_one(document)
        logger.info(f"已創建分析記錄: AnalyzeUUID={analyze_uuid}")
        
        # 5. 派送任務
        dispatcher = TaskDispatcher()
        dispatch_result = dispatcher.dispatch_by_router_ids(
            analyze_uuid=analyze_uuid,
            router_ids=router_ids,
            sequential=sequential
        )
        
        logger.info(f"任務派送完成: {dispatch_result['tasks_created']} 個任務已創建")
        
        return jsonify({
            'success': True,
            'analyze_uuid': analyze_uuid,
            'tasks_created': dispatch_result['tasks_created'],
            'message': '上傳成功，分析任務已建立'
        }), 201
        
    except Exception as e:
        logger.error(f"檔案上傳失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'上傳失敗: {str(e)}'
        }), 500


@upload_bp.route('/recent', methods=['GET'])
@login_required
def get_recent_uploads():
    """
    獲取最近的上傳記錄
    
    Query Parameters:
        - limit: 返回數量限制（預設 50）
        - user_only: 僅顯示當前用戶的上傳（true/false，預設 false）
    
    Returns:
        {
            "success": true,
            "data": [...],
            "count": 10
        }
    """
    try:
        limit = int(request.args.get('limit', 50))
        user_only = request.args.get('user_only', 'false').lower() == 'true'
        
        db = get_db()
        
        # 構建查詢條件
        query = {}
        if user_only:
            query['info_features.uploaded_by'] = current_user.username
        
        # 僅查詢通過 web_ui 上傳的記錄
        query['info_features.upload_source'] = 'web_ui'
        
        # 查詢並排序
        cursor = db['recordings'].find(query).sort('created_at', -1).limit(limit)
        
        uploads = []
        for doc in cursor:
            # 將 ObjectId 轉為字串
            doc['_id'] = str(doc['_id'])
            if 'files' in doc and 'raw' in doc['files'] and 'fileId' in doc['files']['raw']:
                doc['files']['raw']['fileId'] = str(doc['files']['raw']['fileId'])
            
            uploads.append(doc)
        
        return jsonify({
            'success': True,
            'data': uploads,
            'count': len(uploads)
        }), 200
        
    except Exception as e:
        logger.error(f"獲取上傳記錄失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@upload_bp.route('/config', methods=['GET'])
@login_required
def get_upload_config():
    """
    獲取上傳配置資訊
    
    Returns:
        {
            "success": true,
            "config": {
                "allowed_extensions": [...],
                "max_file_size_mb": 100
            }
        }
    """
    try:
        config = get_config()
        
        # 從環境變數獲取最大檔案大小（bytes），轉換為 MB
        max_size_bytes = getattr(config, 'MAX_CONTENT_LENGTH', 100 * 1024 * 1024)
        max_size_mb = max_size_bytes / (1024 * 1024)
        
        return jsonify({
            'success': True,
            'config': {
                'allowed_extensions': list(ALLOWED_AUDIO_EXTENSIONS),
                'max_file_size_mb': max_size_mb
            }
        }), 200
        
    except Exception as e:
        logger.error(f"獲取上傳配置失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
