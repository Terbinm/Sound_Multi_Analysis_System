"""
邊緣設備管理服務

處理邊緣設備的 WebSocket 事件、設備註冊、心跳管理等
"""
import logging
import uuid
from typing import Dict, Any, Optional
from flask import request
from flask_socketio import SocketIO

from models.edge_device import EdgeDevice, OfflineReason
from services.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


class EdgeDeviceManager:
    """邊緣設備管理器"""

    def __init__(self):
        """初始化邊緣設備管理器"""
        self.socketio: Optional[SocketIO] = None
        logger.info("邊緣設備管理器初始化")

    def init_socketio(self, socketio: SocketIO):
        """
        初始化 SocketIO 並註冊事件處理器

        Args:
            socketio: SocketIO instance
        """
        self.socketio = socketio
        self._register_handlers()
        logger.info("邊緣設備管理器已綁定 SocketIO")

    def _register_handlers(self):
        """註冊 WebSocket 事件處理器"""

        @self.socketio.on('edge.register')
        def handle_edge_register(data):
            """
            處理邊緣設備註冊事件

            Args:
                data: {
                    device_id: 設備 ID（可選，為空則分配新 ID）
                    device_name: 設備名稱
                    platform: 平台（linux / win32 / darwin）
                    audio_devices: 可用的音訊設備列表
                }
            """
            try:
                socket_id = request.sid
                client_ip = request.remote_addr

                device_id = data.get('device_id')
                device_name = data.get('device_name', f'Device_{socket_id[:8]}')
                platform = data.get('platform', 'unknown')
                audio_devices = data.get('audio_devices', [])

                logger.info(f"收到邊緣設備註冊請求: device_id={device_id}, name={device_name}, platform={platform}")

                # 註冊設備
                result = EdgeDevice.register(
                    device_id=device_id,
                    device_name=device_name,
                    platform=platform,
                    audio_devices=audio_devices,
                    socket_id=socket_id,
                    ip_address=client_ip
                )

                if result.get('success'):
                    assigned_device_id = result.get('device_id')
                    is_new = result.get('is_new', False)

                    # 發送分配的 ID 回客戶端
                    self.socketio.emit('edge.registered', {
                        'device_id': assigned_device_id,
                        'is_new': is_new
                    }, to=socket_id)

                    # 獲取完整的設備資訊
                    device_info = EdgeDevice.get_by_id(assigned_device_id)

                    # 推送設備註冊事件到 Web UI
                    websocket_manager.emit_edge_device_registered({
                        'device_id': assigned_device_id,
                        'device_name': device_name,
                        'platform': platform,
                        'status': 'IDLE',
                        'is_new': is_new,
                        'audio_config': device_info.get('audio_config', {}) if device_info else {}
                    })

                    # 更新統計
                    self._emit_stats_update()

                    logger.info(f"邊緣設備已註冊: {assigned_device_id} (新設備: {is_new})")
                else:
                    logger.error(f"邊緣設備註冊失敗: {result.get('error')}")
                    self.socketio.emit('edge.error', {
                        'error': '註冊失敗',
                        'message': result.get('error')
                    }, to=socket_id)

            except Exception as e:
                logger.error(f"處理邊緣設備註冊失敗: {e}", exc_info=True)

        @self.socketio.on('edge.heartbeat')
        def handle_edge_heartbeat(data):
            """
            處理邊緣設備心跳事件

            Args:
                data: {
                    device_id: 設備 ID
                    status: 當前狀態
                    current_recording: 當前錄音 UUID（可選）
                }
            """
            try:
                device_id = data.get('device_id')
                status = data.get('status', 'IDLE')
                current_recording = data.get('current_recording')

                if not device_id:
                    logger.warning("收到心跳但缺少 device_id")
                    return

                # 更新心跳
                success = EdgeDevice.update_heartbeat(
                    device_id=device_id,
                    status=status,
                    current_recording=current_recording
                )

                if success:
                    # 推送心跳事件
                    websocket_manager.emit_edge_device_heartbeat({
                        'device_id': device_id,
                        'status': status,
                        'current_recording': current_recording
                    })
                else:
                    logger.warning(f"更新邊緣設備心跳失敗: {device_id}")

            except Exception as e:
                logger.error(f"處理邊緣設備心跳失敗: {e}", exc_info=True)

        @self.socketio.on('edge.audio_devices_response')
        def handle_audio_devices_response(data):
            """
            處理音訊設備查詢回應

            Args:
                data: {
                    device_id: 設備 ID
                    request_id: 請求 ID
                    devices: 音訊設備列表
                }
            """
            try:
                device_id = data.get('device_id')
                devices = data.get('devices', [])

                if not device_id:
                    logger.warning("收到音訊設備回應但缺少 device_id")
                    return

                # 更新設備的音訊設備列表
                success = EdgeDevice.update_available_audio_devices(device_id, devices)

                if success:
                    logger.info(f"已更新設備 {device_id} 的音訊設備列表，共 {len(devices)} 個設備")

                    # 推送更新事件
                    websocket_manager.broadcast('edge_device.audio_devices_updated', {
                        'device_id': device_id,
                        'devices': devices
                    }, room='edge_devices')
                else:
                    logger.warning(f"更新音訊設備列表失敗: {device_id}")

            except Exception as e:
                logger.error(f"處理音訊設備回應失敗: {e}", exc_info=True)

        @self.socketio.on('edge.recording_started')
        def handle_recording_started(data):
            """
            處理錄音開始事件

            Args:
                data: {
                    device_id: 設備 ID
                    recording_uuid: 錄音 UUID
                }
            """
            try:
                device_id = data.get('device_id')
                recording_uuid = data.get('recording_uuid')

                if not device_id or not recording_uuid:
                    logger.warning("收到錄音開始事件但缺少必要參數")
                    return

                # 更新設備狀態為錄音中
                EdgeDevice.update_status(device_id, 'RECORDING')
                EdgeDevice.update_heartbeat(device_id, status='RECORDING', current_recording=recording_uuid)

                # 推送事件
                websocket_manager.emit_edge_device_recording_started({
                    'device_id': device_id,
                    'recording_uuid': recording_uuid
                })

                websocket_manager.emit_edge_device_status_changed({
                    'device_id': device_id,
                    'status': 'RECORDING'
                })

                logger.info(f"邊緣設備 {device_id} 開始錄音: {recording_uuid}")

            except Exception as e:
                logger.error(f"處理錄音開始事件失敗: {e}", exc_info=True)

        @self.socketio.on('edge.recording_progress')
        def handle_recording_progress(data):
            """
            處理錄音進度事件

            Args:
                data: {
                    device_id: 設備 ID
                    recording_uuid: 錄音 UUID
                    progress_percent: 進度百分比
                }
            """
            try:
                device_id = data.get('device_id')
                recording_uuid = data.get('recording_uuid')
                progress_percent = data.get('progress_percent', 0)

                # 推送進度事件
                websocket_manager.emit_edge_device_recording_progress({
                    'device_id': device_id,
                    'recording_uuid': recording_uuid,
                    'progress_percent': progress_percent
                })

            except Exception as e:
                logger.error(f"處理錄音進度事件失敗: {e}", exc_info=True)

        @self.socketio.on('edge.recording_completed')
        def handle_recording_completed(data):
            """
            處理錄音完成事件

            Args:
                data: {
                    device_id: 設備 ID
                    recording_uuid: 錄音 UUID
                    filename: 檔案名稱
                    file_size: 檔案大小
                    file_hash: 檔案雜湊值
                    actual_duration: 實際錄音時長
                }
            """
            try:
                device_id = data.get('device_id')
                recording_uuid = data.get('recording_uuid')

                if not device_id or not recording_uuid:
                    logger.warning("收到錄音完成事件但缺少必要參數")
                    return

                # 更新設備狀態為在線
                EdgeDevice.update_status(device_id, 'IDLE')
                EdgeDevice.update_heartbeat(device_id, status='IDLE', current_recording=None)

                # 注意：錄音統計在 upload_recording API 中更新，避免重複計算

                # 錄音結果資訊
                result = {
                    'filename': data.get('filename'),
                    'file_size': data.get('file_size'),
                    'file_hash': data.get('file_hash'),
                    'actual_duration': data.get('actual_duration')
                }

                # 推送事件
                websocket_manager.emit_edge_device_recording_completed({
                    'device_id': device_id,
                    'recording_uuid': recording_uuid,
                    'result': result
                })

                websocket_manager.emit_edge_device_status_changed({
                    'device_id': device_id,
                    'status': 'IDLE'
                })

                logger.info(f"邊緣設備 {device_id} 錄音完成: {recording_uuid}")

            except Exception as e:
                logger.error(f"處理錄音完成事件失敗: {e}", exc_info=True)

        @self.socketio.on('edge.recording_failed')
        def handle_recording_failed(data):
            """
            處理錄音失敗事件

            Args:
                data: {
                    device_id: 設備 ID
                    recording_uuid: 錄音 UUID
                    error: 錯誤訊息
                }
            """
            try:
                device_id = data.get('device_id')
                recording_uuid = data.get('recording_uuid')
                error = data.get('error', '未知錯誤')

                if not device_id:
                    logger.warning("收到錄音失敗事件但缺少 device_id")
                    return

                # 更新設備狀態為在線
                EdgeDevice.update_status(device_id, 'IDLE')
                EdgeDevice.update_heartbeat(device_id, status='IDLE', current_recording=None)

                # 增加錄音統計（失敗）
                EdgeDevice.increment_recording_stats(device_id, success=False)

                # 推送事件
                websocket_manager.emit_edge_device_recording_failed({
                    'device_id': device_id,
                    'recording_uuid': recording_uuid,
                    'error': error
                })

                websocket_manager.emit_edge_device_status_changed({
                    'device_id': device_id,
                    'status': 'IDLE'
                })

                logger.error(f"邊緣設備 {device_id} 錄音失敗: {error}")

            except Exception as e:
                logger.error(f"處理錄音失敗事件失敗: {e}", exc_info=True)

        @self.socketio.on('edge.status_changed')
        def handle_status_changed(data):
            """
            處理設備狀態變更事件

            Args:
                data: {
                    device_id: 設備 ID
                    status: 新狀態
                }
            """
            try:
                device_id = data.get('device_id')
                status = data.get('status')

                if not device_id or not status:
                    return

                # 更新設備狀態
                EdgeDevice.update_status(device_id, status)

                # 推送事件
                websocket_manager.emit_edge_device_status_changed({
                    'device_id': device_id,
                    'status': status
                })

                logger.info(f"邊緣設備 {device_id} 狀態變更為: {status}")

            except Exception as e:
                logger.error(f"處理狀態變更事件失敗: {e}", exc_info=True)

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """處理客戶端斷開連接"""
            try:
                socket_id = request.sid

                # 查找與此 socket_id 關聯的設備
                device = EdgeDevice.get_by_socket_id(socket_id)

                if device:
                    device_id = device.get('device_id')

                    # 設定設備為離線，原因為連線中斷
                    EdgeDevice.set_offline(device_id, reason=OfflineReason.CONNECTION_LOST)

                    # 推送離線事件（包含離線原因）
                    websocket_manager.emit_edge_device_offline({
                        'device_id': device_id,
                        'device_name': device.get('device_name'),
                        'offline_reason': OfflineReason.CONNECTION_LOST,
                        'offline_reason_display': OfflineReason.get_display_text(OfflineReason.CONNECTION_LOST)
                    })

                    # 更新統計
                    self._emit_stats_update()

                    logger.info(f"邊緣設備已離線: {device_id}，原因: 連線中斷")

            except Exception as e:
                logger.error(f"處理斷開連接事件失敗: {e}", exc_info=True)

    def _emit_stats_update(self):
        """推送統計更新"""
        try:
            stats = EdgeDevice.get_statistics()
            websocket_manager.emit_edge_device_stats_updated({
                'total_devices': stats.get('total_devices', 0),
                'online_devices': stats.get('online_devices', 0),
                'offline_devices': stats.get('offline_devices', 0),
                'recording_devices': stats.get('recording_devices', 0)
            })
        except Exception as e:
            logger.error(f"推送統計更新失敗: {e}")

    def send_record_command(
        self,
        device_id: str,
        duration: int,
        channels: int = 1,
        sample_rate: int = 16000,
        device_index: int = 0,
        bit_depth: int = 16,
        recording_uuid: Optional[str] = None
    ) -> Optional[str]:
        """
        發送錄音命令到邊緣設備

        Args:
            device_id: 設備 ID
            duration: 錄音時長（秒）
            channels: 聲道數
            sample_rate: 採樣率
            device_index: 音訊設備索引
            bit_depth: 位深
            recording_uuid: 錄音 UUID（可選，為空則自動生成）

        Returns:
            錄音 UUID，失敗返回 None
        """
        try:
            device = EdgeDevice.get_by_id(device_id)
            if not device:
                logger.error(f"設備不存在: {device_id}")
                return None

            if device.get('status') == 'OFFLINE':
                logger.error(f"設備離線: {device_id}")
                return None

            socket_id = device.get('connection_info', {}).get('socket_id')
            if not socket_id:
                logger.error(f"設備無連線資訊: {device_id}")
                return None

            # 生成錄音 UUID
            if not recording_uuid:
                recording_uuid = str(uuid.uuid4())

            # 發送錄音命令
            self.socketio.emit('edge.record', {
                'recording_uuid': recording_uuid,
                'duration': duration,
                'channels': channels,
                'sample_rate': sample_rate,
                'device_index': device_index,
                'bit_depth': bit_depth
            }, to=socket_id)

            logger.info(f"已發送錄音命令到設備 {device_id}: {recording_uuid}")
            return recording_uuid

        except Exception as e:
            logger.error(f"發送錄音命令失敗: {e}", exc_info=True)
            return None

    def send_stop_command(self, device_id: str, recording_uuid: Optional[str] = None) -> bool:
        """
        發送停止錄音命令

        Args:
            device_id: 設備 ID
            recording_uuid: 錄音 UUID（可選）

        Returns:
            是否成功發送
        """
        try:
            device = EdgeDevice.get_by_id(device_id)
            if not device:
                logger.error(f"設備不存在: {device_id}")
                return False

            socket_id = device.get('connection_info', {}).get('socket_id')
            if not socket_id:
                logger.error(f"設備無連線資訊: {device_id}")
                return False

            # 發送停止命令
            self.socketio.emit('edge.stop', {
                'recording_uuid': recording_uuid
            }, to=socket_id)

            logger.info(f"已發送停止錄音命令到設備 {device_id}")
            return True

        except Exception as e:
            logger.error(f"發送停止錄音命令失敗: {e}", exc_info=True)
            return False

    def query_audio_devices(self, device_id: str) -> bool:
        """
        查詢設備的音訊設備

        Args:
            device_id: 設備 ID

        Returns:
            是否成功發送查詢
        """
        try:
            device = EdgeDevice.get_by_id(device_id)
            if not device:
                logger.error(f"設備不存在: {device_id}")
                return False

            if device.get('status') == 'OFFLINE':
                logger.error(f"設備離線: {device_id}")
                return False

            socket_id = device.get('connection_info', {}).get('socket_id')
            if not socket_id:
                logger.error(f"設備無連線資訊: {device_id}")
                return False

            import uuid
            request_id = str(uuid.uuid4())

            # 發送查詢請求
            self.socketio.emit('edge.query_audio_devices', {
                'request_id': request_id
            }, to=socket_id)

            logger.info(f"已發送音訊設備查詢到設備 {device_id}")
            return True

        except Exception as e:
            logger.error(f"發送音訊設備查詢失敗: {e}", exc_info=True)
            return False

    def update_device_config(self, device_id: str, config: Dict[str, Any]) -> bool:
        """
        更新設備配置

        Args:
            device_id: 設備 ID
            config: 配置數據

        Returns:
            是否成功發送
        """
        try:
            device = EdgeDevice.get_by_id(device_id)
            if not device:
                logger.error(f"設備不存在: {device_id}")
                return False

            if device.get('status') == 'OFFLINE':
                logger.warning(f"設備離線，無法即時更新配置: {device_id}")
                return False

            socket_id = device.get('connection_info', {}).get('socket_id')
            if not socket_id:
                logger.error(f"設備無連線資訊: {device_id}")
                return False

            # 發送配置更新
            self.socketio.emit('edge.update_config', config, to=socket_id)

            logger.info(f"已發送配置更新到設備 {device_id}")
            return True

        except Exception as e:
            logger.error(f"發送配置更新失敗: {e}", exc_info=True)
            return False


# 全局邊緣設備管理器instance
edge_device_manager = EdgeDeviceManager()
