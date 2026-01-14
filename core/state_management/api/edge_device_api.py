"""
邊緣設備管理 API

提供邊緣錄音設備的管理、錄音控制和排程設定功能
"""
import logging
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import gridfs
from models.edge_device import EdgeDevice
from models.routing_rule import RoutingRule
from services.websocket_manager import websocket_manager
from services.edge_schedule_service import edge_schedule_service
from services.edge_device_manager import edge_device_manager
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)

# 支援的音訊檔案格式
ALLOWED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac'}

edge_device_bp = Blueprint('edge_device_api', __name__)


# ==================== 設備管理 API ====================

@edge_device_bp.route('', methods=['GET'])
def get_all_devices():
    """
    獲取所有邊緣設備

    Query Parameters:
        status: 過濾狀態（IDLE / OFFLINE / RECORDING）
    """
    try:
        status_filter = request.args.get('status')

        devices = EdgeDevice.get_all()

        # 若有狀態過濾
        if status_filter:
            devices = [d for d in devices if d.get('status') == status_filter]

        return jsonify({
            'success': True,
            'data': devices,
            'count': len(devices)
        }), 200

    except Exception as e:
        logger.error(f"獲取邊緣設備列表失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>', methods=['GET'])
def get_device(device_id):
    """獲取單一邊緣設備詳情"""
    try:
        device = EdgeDevice.get_by_id(device_id)

        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        return jsonify({
            'success': True,
            'data': device
        }), 200

    except Exception as e:
        logger.error(f"獲取邊緣設備失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>', methods=['PUT'])
def update_device(device_id):
    """
    更新邊緣設備資訊

    Request Body:
        device_name: 設備名稱（可選）
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 更新設備名稱
        if 'device_name' in data:
            success = EdgeDevice.update_device_name(device_id, data['device_name'])
            if not success:
                return jsonify({
                    'success': False,
                    'error': '更新設備名稱失敗'
                }), 500

            # 推送更新事件給 Web UI
            websocket_manager.broadcast('edge_device.updated', {
                'device_id': device_id,
                'device_name': data['device_name']
            }, room='edge_devices')

            # 同時通知 Edge Client 更新本地配置
            edge_device_manager.update_device_config(device_id, {
                'device_name': data['device_name']
            })

        # 獲取更新後的設備資訊
        updated_device = EdgeDevice.get_by_id(device_id)

        return jsonify({
            'success': True,
            'data': updated_device,
            'message': '設備資訊已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新邊緣設備失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>', methods=['DELETE'])
def delete_device(device_id):
    """
    刪除邊緣設備

    Query Parameters:
        force: 是否強制刪除（即使設備在線）
        delete_recordings: 是否同時刪除該設備的所有錄音資料
    """
    try:
        force = request.args.get('force', 'false').lower() == 'true'
        delete_recordings = request.args.get('delete_recordings', 'false').lower() == 'true'

        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 若設備在線且非強制刪除，拒絕操作
        if device.get('status') in ('IDLE', 'RECORDING') and not force:
            return jsonify({
                'success': False,
                'error': '無法刪除在線的設備，請先使設備離線或使用 force=true 參數'
            }), 400

        deleted_recordings_count = 0

        logger.info(f"刪除設備請求: device_id={device_id}, delete_recordings={delete_recordings}, force={force}")

        # 若需要刪除錄音資料
        if delete_recordings:
            db = get_db()
            config = get_config()
            collection_name = config.COLLECTIONS.get('recordings', 'recordings')
            recordings_collection = db[collection_name]
            fs = gridfs.GridFS(db)

            # 查詢該設備的所有錄音
            query = {'info_features.device_id': device_id}

            # 先計算數量以便調試
            count_before = recordings_collection.count_documents(query)
            logger.info(f"準備刪除錄音: collection={collection_name}, query={query}, 找到 {count_before} 筆")

            # 如果找不到，嘗試其他查詢方式調試
            if count_before == 0:
                # 檢查是否有任何包含此 device_id 的錄音（可能在不同欄位）
                alt_query = {'$or': [
                    {'info_features.device_id': device_id},
                    {'device_id': device_id},
                    {'info_features.device_id': {'$regex': device_id, '$options': 'i'}}
                ]}
                alt_count = recordings_collection.count_documents(alt_query)
                logger.info(f"替代查詢找到 {alt_count} 筆")

                # 列出所有錄音的 device_id 欄位值（最多 5 筆）
                sample_docs = list(recordings_collection.find({}, {'info_features.device_id': 1, 'device_id': 1}).limit(5))
                for doc in sample_docs:
                    logger.info(f"樣本錄音 device_id: info_features.device_id={doc.get('info_features', {}).get('device_id')}, device_id={doc.get('device_id')}")

            recordings = list(recordings_collection.find(query))

            # 刪除 GridFS 檔案
            for recording in recordings:
                try:
                    file_id = recording.get('files', {}).get('raw', {}).get('fileId')
                    if file_id:
                        fs.delete(file_id)
                except Exception as e:
                    logger.warning(f"刪除 GridFS 檔案失敗 ({recording.get('AnalyzeUUID')}): {e}")

            # 刪除 recordings 集合中的文檔
            result = recordings_collection.delete_many(query)
            deleted_recordings_count = result.deleted_count
            logger.info(f"已刪除設備 {device_id} 的 {deleted_recordings_count} 筆錄音")

        # 刪除設備
        success = EdgeDevice.delete(device_id, force=force)
        if not success:
            return jsonify({
                'success': False,
                'error': '刪除設備失敗'
            }), 500

        # 推送刪除事件
        websocket_manager.broadcast('edge_device.deleted', {
            'device_id': device_id
        }, room='edge_devices')

        return jsonify({
            'success': True,
            'message': '設備已刪除',
            'deleted_recordings': deleted_recordings_count if delete_recordings else None
        }), 200

    except Exception as e:
        logger.error(f"刪除邊緣設備失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/stats', methods=['GET'])
def get_statistics():
    """獲取邊緣設備統計資訊"""
    try:
        stats = EdgeDevice.get_statistics()

        return jsonify({
            'success': True,
            'data': {
                'total_devices': stats.get('total_devices', 0),
                'online_devices': stats.get('online_devices', 0),
                'offline_devices': stats.get('offline_devices', 0),
                'recording_devices': stats.get('recording_devices', 0)
            }
        }), 200

    except Exception as e:
        logger.error(f"獲取邊緣設備統計失敗: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 錄音控制 API ====================

@edge_device_bp.route('/<device_id>/record', methods=['POST'])
def send_record_command(device_id):
    """
    發送錄音命令到邊緣設備

    Request Body:
        duration: 錄音時長（秒）- 必填
        channels: 聲道數（可選，預設使用設備配置）
        sample_rate: 採樣率（可選，預設使用設備配置）
        device_index: 音訊設備索引（可選，預設使用設備配置）
        bit_depth: 位深（可選，預設使用設備配置）
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查必填欄位
        if 'duration' not in data:
            return jsonify({
                'success': False,
                'error': '缺少必填欄位: duration'
            }), 400

        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 檢查設備是否在線
        if device.get('status') == 'OFFLINE':
            return jsonify({
                'success': False,
                'error': '設備離線，無法發送錄音命令'
            }), 400

        # 檢查設備是否正在錄音
        if device.get('status') == 'RECORDING':
            return jsonify({
                'success': False,
                'error': '設備正在錄音中'
            }), 400

        # 組合錄音參數（優先使用請求參數，否則使用設備配置）
        audio_config = device.get('audio_config', {})
        recording_params = {
            'duration': data['duration'],
            'channels': data.get('channels', audio_config.get('channels', 1)),
            'sample_rate': data.get('sample_rate', audio_config.get('sample_rate', 16000)),
            'device_index': data.get('device_index', audio_config.get('default_device_index', 0)),
            'bit_depth': data.get('bit_depth', audio_config.get('bit_depth', 16))
        }

        # 生成錄音 UUID
        recording_uuid = str(uuid.uuid4())

        # 透過 WebSocket 發送錄音命令到設備
        socket_id = device.get('connection_info', {}).get('socket_id')
        if socket_id:
            websocket_manager.socketio.emit('edge.record', {
                'recording_uuid': recording_uuid,
                **recording_params
            }, to=socket_id)
            logger.info(f"已發送錄音命令到設備 {device_id}，recording_uuid: {recording_uuid}")
        else:
            logger.warning(f"設備 {device_id} 的 socket_id 不存在")
            return jsonify({
                'success': False,
                'error': '無法找到設備的連線資訊'
            }), 500

        # 推送錄音狀態更新
        websocket_manager.broadcast('edge_device.recording_started', {
            'device_id': device_id,
            'recording_uuid': recording_uuid,
            'parameters': recording_params
        }, room='edge_devices')

        return jsonify({
            'success': True,
            'data': {
                'device_id': device_id,
                'recording_uuid': recording_uuid,
                'parameters': recording_params
            },
            'message': '錄音命令已發送'
        }), 200

    except Exception as e:
        logger.error(f"發送錄音命令失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/stop', methods=['POST'])
def send_stop_command(device_id):
    """發送停止錄音命令"""
    try:
        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 檢查設備是否正在錄音
        if device.get('status') != 'RECORDING':
            return jsonify({
                'success': False,
                'error': '設備未在錄音中'
            }), 400

        # 獲取當前錄音的 UUID
        current_recording = device.get('connection_info', {}).get('current_recording')

        # 透過 WebSocket 發送停止命令
        socket_id = device.get('connection_info', {}).get('socket_id')
        if socket_id:
            websocket_manager.socketio.emit('edge.stop', {
                'recording_uuid': current_recording
            }, to=socket_id)
            logger.info(f"已發送停止錄音命令到設備 {device_id}")
        else:
            return jsonify({
                'success': False,
                'error': '無法找到設備的連線資訊'
            }), 500

        return jsonify({
            'success': True,
            'message': '停止錄音命令已發送'
        }), 200

    except Exception as e:
        logger.error(f"發送停止錄音命令失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/audio-devices', methods=['GET'])
def query_audio_devices(device_id):
    """查詢設備的可用音訊設備"""
    try:
        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 返回已存儲的音訊設備列表
        audio_devices = device.get('audio_config', {}).get('available_devices', [])

        # 若設備在線，可以發送查詢請求更新
        if device.get('status') in ('IDLE', 'RECORDING'):
            socket_id = device.get('connection_info', {}).get('socket_id')
            if socket_id:
                import uuid
                request_id = str(uuid.uuid4())
                websocket_manager.socketio.emit('edge.query_audio_devices', {
                    'request_id': request_id
                }, to=socket_id)
                logger.info(f"已發送音訊設備查詢請求到設備 {device_id}")

        return jsonify({
            'success': True,
            'data': {
                'device_id': device_id,
                'available_devices': audio_devices,
                'is_online': device.get('status') != 'OFFLINE'
            }
        }), 200

    except Exception as e:
        logger.error(f"查詢音訊設備失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/audio-config', methods=['PUT'])
def update_audio_config(device_id):
    """
    更新設備音訊配置

    Request Body:
        default_device_index: 預設音訊設備索引（可選）
        channels: 聲道數（可選）
        sample_rate: 採樣率（可選）
        bit_depth: 位深（可選）
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 過濾有效的音訊配置欄位
        valid_fields = ['default_device_index', 'channels', 'sample_rate', 'bit_depth']
        audio_config = {k: v for k, v in data.items() if k in valid_fields}

        if not audio_config:
            return jsonify({
                'success': False,
                'error': '沒有有效的音訊配置欄位'
            }), 400

        # 更新音訊配置
        success = EdgeDevice.update_audio_config(device_id, audio_config)
        if not success:
            return jsonify({
                'success': False,
                'error': '更新音訊配置失敗'
            }), 500

        # 若設備在線，發送配置更新通知
        if device.get('status') != 'OFFLINE':
            socket_id = device.get('connection_info', {}).get('socket_id')
            if socket_id:
                websocket_manager.socketio.emit('edge.update_config', {
                    'audio_config': audio_config
                }, to=socket_id)

        # 獲取更新後的設備資訊
        updated_device = EdgeDevice.get_by_id(device_id)

        return jsonify({
            'success': True,
            'data': updated_device.get('audio_config', {}),
            'message': '音訊配置已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新音訊配置失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 排程管理 API ====================

@edge_device_bp.route('/<device_id>/schedule', methods=['GET'])
def get_schedule(device_id):
    """獲取設備排程配置"""
    try:
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        return jsonify({
            'success': True,
            'data': device.get('schedule_config', {})
        }), 200

    except Exception as e:
        logger.error(f"獲取排程配置失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/schedule', methods=['PUT'])
def update_schedule(device_id):
    """
    更新設備排程配置

    Request Body:
        enabled: 是否啟用（可選）
        interval_seconds: 間隔秒數（可選）
        duration_seconds: 錄音時長（可選）
        start_time: 每日開始時間 HH:MM（可選）
        end_time: 每日結束時間 HH:MM（可選）
        max_success_count: 錄製成功數量上限（可選，達到後自動停用排程）
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 過濾有效的排程配置欄位
        valid_fields = ['enabled', 'interval_seconds', 'duration_seconds', 'start_time', 'end_time', 'max_success_count']
        schedule_config = {k: v for k, v in data.items() if k in valid_fields}

        if not schedule_config:
            return jsonify({
                'success': False,
                'error': '沒有有效的排程配置欄位'
            }), 400

        # 驗證排程參數
        if 'interval_seconds' in schedule_config and schedule_config['interval_seconds'] <= 0:
            return jsonify({
                'success': False,
                'error': '間隔時間必須大於 0'
            }), 400

        if 'duration_seconds' in schedule_config and schedule_config['duration_seconds'] < 1:
            return jsonify({
                'success': False,
                'error': '錄音時長必須大於 0'
            }), 400

        # 驗證錄音上限（允許 None 或正整數）
        if 'max_success_count' in schedule_config:
            max_count = schedule_config['max_success_count']
            if max_count is not None and (not isinstance(max_count, int) or max_count < 1):
                return jsonify({
                    'success': False,
                    'error': '錄音上限必須是正整數或留空（無上限）'
                }), 400

        # 更新排程配置
        success = EdgeDevice.update_schedule_config(device_id, schedule_config)
        if not success:
            return jsonify({
                'success': False,
                'error': '更新排程配置失敗'
            }), 500

        # 獲取更新後的設備資訊
        updated_device = EdgeDevice.get_by_id(device_id)
        updated_schedule = updated_device.get('schedule_config', {})

        # 同步更新排程服務
        if updated_schedule.get('enabled'):
            # 啟用狀態：新增或更新排程
            edge_schedule_service.add_device_schedule(
                device_id=device_id,
                interval_seconds=updated_schedule.get('interval_seconds', 3600),
                duration_seconds=updated_schedule.get('duration_seconds', 60),
                start_time=updated_schedule.get('start_time'),
                end_time=updated_schedule.get('end_time')
            )
            logger.info(f"已同步更新設備 {device_id} 的排程任務")
        else:
            # 停用狀態：移除排程
            edge_schedule_service.remove_device_schedule(device_id)
            logger.info(f"已移除設備 {device_id} 的排程任務")

        # 推送排程更新事件
        websocket_manager.broadcast('edge_device.schedule_updated', {
            'device_id': device_id,
            'schedule_config': updated_schedule
        }, room='edge_devices')

        return jsonify({
            'success': True,
            'data': updated_schedule,
            'message': '排程配置已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新排程配置失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/schedule/enable', methods=['POST'])
def enable_schedule(device_id):
    """啟用設備排程"""
    try:
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        success = EdgeDevice.update_schedule_config(device_id, {'enabled': True})
        if not success:
            return jsonify({
                'success': False,
                'error': '啟用排程失敗'
            }), 500

        # 同步新增排程任務到排程服務
        schedule_config = device.get('schedule_config', {})
        edge_schedule_service.add_device_schedule(
            device_id=device_id,
            interval_seconds=schedule_config.get('interval_seconds', 3600),
            duration_seconds=schedule_config.get('duration_seconds', 60),
            start_time=schedule_config.get('start_time'),
            end_time=schedule_config.get('end_time')
        )
        logger.info(f"已新增設備 {device_id} 的排程任務")

        # 推送排程更新事件
        websocket_manager.broadcast('edge_device.schedule_enabled', {
            'device_id': device_id
        }, room='edge_devices')

        return jsonify({
            'success': True,
            'message': '排程已啟用'
        }), 200

    except Exception as e:
        logger.error(f"啟用排程失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/schedule/disable', methods=['POST'])
def disable_schedule(device_id):
    """停用設備排程"""
    try:
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        success = EdgeDevice.update_schedule_config(device_id, {'enabled': False})
        if not success:
            return jsonify({
                'success': False,
                'error': '停用排程失敗'
            }), 500

        # 同步移除排程服務中的任務
        edge_schedule_service.remove_device_schedule(device_id)
        logger.info(f"已移除設備 {device_id} 的排程任務")

        # 推送排程更新事件
        websocket_manager.broadcast('edge_device.schedule_disabled', {
            'device_id': device_id
        }, room='edge_devices')

        return jsonify({
            'success': True,
            'message': '排程已停用'
        }), 200

    except Exception as e:
        logger.error(f"停用排程失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 錄音歷史 API ====================

@edge_device_bp.route('/<device_id>/recordings', methods=['GET'])
def get_recordings(device_id):
    """
    獲取設備錄音歷史（從 recordings 集合）

    Query Parameters:
        limit: 最大返回數量（預設 50）
        skip: 跳過數量（用於分頁，預設 0）
    """
    try:
        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 獲取查詢參數
        limit = int(request.args.get('limit', 50))
        skip = int(request.args.get('skip', 0))

        # 從 recordings 集合查詢該設備的錄音
        db = get_db()
        config = get_config()
        recordings_collection = db[config.COLLECTIONS.get('recordings', 'recordings')]

        query = {'info_features.device_id': device_id}
        total_count = recordings_collection.count_documents(query)

        cursor = recordings_collection.find(query).sort('created_at', -1).skip(skip).limit(limit)

        recordings = []
        for record in cursor:
            recordings.append({
                'analyze_uuid': record.get('AnalyzeUUID'),
                'device_id': record.get('info_features', {}).get('device_id'),
                'device_name': record.get('info_features', {}).get('device_name'),
                'duration': record.get('info_features', {}).get('duration'),
                'file_size': record.get('info_features', {}).get('file_size'),
                'filename': record.get('files', {}).get('raw', {}).get('filename'),
                'assigned_router_ids': record.get('assigned_router_ids', []),
                'created_at': record.get('created_at'),
                'uploaded_at': record.get('info_features', {}).get('uploaded_at')
            })

        return jsonify({
            'success': True,
            'data': recordings,
            'count': len(recordings),
            'total': total_count,
            'pagination': {
                'limit': limit,
                'skip': skip,
                'has_more': skip + len(recordings) < total_count
            }
        }), 200

    except Exception as e:
        logger.error(f"獲取錄音歷史失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/recordings/<recording_uuid>', methods=['GET'])
def get_recording_detail(recording_uuid):
    """獲取單筆錄音詳情（從 recordings 集合）"""
    try:
        db = get_db()
        config = get_config()
        recordings_collection = db[config.COLLECTIONS.get('recordings', 'recordings')]

        recording = recordings_collection.find_one({'AnalyzeUUID': recording_uuid})

        if not recording:
            return jsonify({
                'success': False,
                'error': '錄音記錄不存在'
            }), 404

        result = {
            'analyze_uuid': recording.get('AnalyzeUUID'),
            'files': recording.get('files', {}),
            'info_features': recording.get('info_features', {}),
            'analyze_features': recording.get('analyze_features', {}),
            'assigned_router_ids': recording.get('assigned_router_ids', []),
            'created_at': recording.get('created_at'),
            'updated_at': recording.get('updated_at')
        }

        return jsonify({
            'success': True,
            'data': result
        }), 200

    except Exception as e:
        logger.error(f"獲取錄音詳情失敗 ({recording_uuid}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/recordings/stats', methods=['GET'])
def get_recording_stats(device_id):
    """獲取設備錄音統計（從設備統計資訊）"""
    try:
        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        # 從設備資訊中獲取統計
        stats = device.get('statistics', {})

        return jsonify({
            'success': True,
            'data': {
                'total_recordings': stats.get('total_recordings', 0),
                'success_count': stats.get('success_count', 0),
                'error_count': stats.get('error_count', 0),
                'last_recording_at': stats.get('last_recording_at')
            }
        }), 200

    except Exception as e:
        logger.error(f"獲取錄音統計失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 路由配置 API ====================

@edge_device_bp.route('/<device_id>/routers', methods=['GET'])
def get_device_routers(device_id):
    """獲取設備的路由配置"""
    try:
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        assigned_router_ids = device.get('assigned_router_ids', [])

        # 獲取路由詳細資訊
        routers = []
        for router_id in assigned_router_ids:
            rule = RoutingRule.get_by_id(router_id)
            if rule:
                routers.append({
                    'rule_id': rule.rule_id,
                    'rule_name': rule.rule_name,
                    'description': rule.description,
                    'enabled': rule.enabled
                })

        return jsonify({
            'success': True,
            'data': {
                'assigned_router_ids': assigned_router_ids,
                'routers': routers
            }
        }), 200

    except Exception as e:
        logger.error(f"獲取設備路由配置失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@edge_device_bp.route('/<device_id>/routers', methods=['PUT'])
def update_device_routers(device_id):
    """
    更新設備的路由配置

    Request Body:
        router_ids: 路由 ID 列表
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': '缺少請求數據'
            }), 400

        # 檢查設備是否存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': '設備不存在'
            }), 404

        router_ids = data.get('router_ids', [])

        # 驗證路由是否存在
        valid_router_ids = []
        for router_id in router_ids:
            rule = RoutingRule.get_by_id(router_id)
            if rule:
                valid_router_ids.append(router_id)
            else:
                logger.warning(f"路由規則不存在: {router_id}")

        # 更新設備路由配置
        success = EdgeDevice.update_router_ids(device_id, valid_router_ids)
        if not success:
            return jsonify({
                'success': False,
                'error': '更新路由配置失敗'
            }), 500

        # 推送更新事件
        websocket_manager.broadcast('edge_device.routers_updated', {
            'device_id': device_id,
            'assigned_router_ids': valid_router_ids
        }, room='edge_devices')

        return jsonify({
            'success': True,
            'data': {
                'assigned_router_ids': valid_router_ids
            },
            'message': '路由配置已更新'
        }), 200

    except Exception as e:
        logger.error(f"更新設備路由配置失敗 ({device_id}): {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 錄音上傳 API ====================

@edge_device_bp.route('/upload_recording', methods=['POST'])
def upload_recording():
    """
    接收 Edge Client 上傳的錄音檔案

    Request (multipart/form-data):
        file: 音訊檔案（WAV）
        device_id: 設備唯一識別碼（必填）
        recording_uuid: 錄音 UUID（必填）
        duration: 錄音時長（秒）（必填）
        file_size: 檔案大小（bytes）（可選）
        file_hash: 檔案 MD5 雜湊值（可選）

    Returns:
        成功 (200):
            {
                "success": true,
                "message": "上傳成功",
                "file_id": "GridFS 檔案 ID",
                "device_id": "設備 ID",
                "recording_uuid": "錄音 UUID"
            }
        失敗 (400/404/500):
            {
                "success": false,
                "error": "錯誤訊息"
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

        # 檢查檔案格式
        if '.' in file.filename:
            ext = '.' + file.filename.rsplit('.', 1)[1].lower()
            if ext not in ALLOWED_AUDIO_EXTENSIONS:
                return jsonify({
                    'success': False,
                    'error': f'不支援的檔案格式。允許的格式: {", ".join(ALLOWED_AUDIO_EXTENSIONS)}'
                }), 400

        # 2. 驗證必要參數
        device_id = request.form.get('device_id')
        recording_uuid = request.form.get('recording_uuid')
        duration = request.form.get('duration')

        if not device_id:
            return jsonify({
                'success': False,
                'error': '缺少必填欄位: device_id'
            }), 400

        if not recording_uuid:
            return jsonify({
                'success': False,
                'error': '缺少必填欄位: recording_uuid'
            }), 400

        if not duration:
            return jsonify({
                'success': False,
                'error': '缺少必填欄位: duration'
            }), 400

        # 轉換 duration 為浮點數
        try:
            duration = float(duration)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'duration 必須是數字'
            }), 400

        # 獲取可選參數
        file_size = request.form.get('file_size', 0)
        file_hash = request.form.get('file_hash', '')

        try:
            file_size = int(file_size) if file_size else 0
        except ValueError:
            file_size = 0

        # 3. 驗證設備存在
        device = EdgeDevice.get_by_id(device_id)
        if not device:
            return jsonify({
                'success': False,
                'error': f'設備不存在: {device_id}'
            }), 404

        # 4. 上傳檔案至 GridFS
        db = get_db()
        config = get_config()
        fs = gridfs.GridFS(db)

        # 讀取檔案內容
        file_content = file.read()
        filename = secure_filename(file.filename)

        # 取得檔案副檔名
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'wav'

        # 計算實際檔案大小（如果沒有提供）
        actual_file_size = len(file_content)
        if file_size == 0:
            file_size = actual_file_size

        # 上傳至 GridFS，包含設備識別資訊
        gridfs_file_id = fs.put(
            file_content,
            filename=filename,
            content_type=f'audio/{file_extension}',
            upload_date=datetime.utcnow(),
            metadata={
                'device_id': device_id,
                'recording_uuid': recording_uuid,
                'original_filename': file.filename,
                'file_size': actual_file_size,
                'file_hash': file_hash,
                'duration': duration,
                'source': 'edge_client',
                'uploaded_at': datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Edge 錄音檔案已上傳至 GridFS: {filename} (file_id: {gridfs_file_id}, device_id: {device_id})")

        # 5. 取得設備的路由配置
        device_name = device.get('device_name', device_id)
        assigned_router_ids = device.get('assigned_router_ids', [])

        # 6. 在 recordings 集合建立分析記錄
        recordings_collection = db[config.COLLECTIONS.get('recordings', 'recordings')]

        recordings_document = {
            'AnalyzeUUID': recording_uuid,
            'files': {
                'raw': {
                    'fileId': gridfs_file_id,
                    'filename': filename,
                    'type': file_extension
                }
            },
            'info_features': {
                'source': 'edge_client',
                'device_id': device_id,
                'device_name': device_name,
                'duration': duration,
                'file_size': actual_file_size,
                'file_hash': file_hash,
                'uploaded_at': datetime.utcnow().isoformat()
            },
            'analyze_features': {},
            'assigned_router_ids': assigned_router_ids,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

        recordings_collection.insert_one(recordings_document)
        logger.info(f"已在 recordings 集合建立分析記錄: AnalyzeUUID={recording_uuid}, routers={assigned_router_ids}")

        # 7. 更新設備錄音統計（並檢查是否達到排程上限）
        stats_result = EdgeDevice.increment_recording_stats(device_id, success=True)

        # 若因達到上限而停用排程，推送通知
        if stats_result.get('schedule_disabled'):
            # 同步移除排程服務中的任務
            edge_schedule_service.remove_device_schedule(device_id)
            logger.info(f"設備 {device_id} 已達排程錄音上限，排程已自動停用並移除任務")

            # 推送排程停用事件
            websocket_manager.broadcast('edge_device.schedule_disabled', {
                'device_id': device_id,
                'reason': 'max_success_count_reached',
                'success_count': stats_result.get('new_success_count', 0)
            }, room='edge_devices')

        # 8. 推送上傳完成事件
        websocket_manager.broadcast('edge_device.recording_uploaded', {
            'device_id': device_id,
            'recording_uuid': recording_uuid,
            'filename': filename,
            'duration': duration,
            'file_id': str(gridfs_file_id),
            'assigned_router_ids': assigned_router_ids
        }, room='edge_devices')

        return jsonify({
            'success': True,
            'message': '上傳成功',
            'file_id': str(gridfs_file_id),
            'device_id': device_id,
            'recording_uuid': recording_uuid,
            'analyze_uuid': recording_uuid,
            'assigned_router_ids': assigned_router_ids
        }), 200

    except Exception as e:
        logger.error(f"Edge 錄音上傳失敗: {e}", exc_info=True)

        # 更新設備錄音統計（失敗）
        device_id = request.form.get('device_id')
        if device_id:
            try:
                EdgeDevice.increment_recording_stats(device_id, success=False)
            except Exception:
                pass

        return jsonify({
            'success': False,
            'error': f'上傳失敗: {str(e)}'
        }), 500
